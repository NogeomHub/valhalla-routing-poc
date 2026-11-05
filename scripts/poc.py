"""Bounded local routing smoke test. Never a topological or tariff certificate."""
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'work'
O = W / 'out'
IMAGE = 'ghcr.io/valhalla/valhalla@sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a'
ATTRIBUTES = ['shape', 'edge.way_id', 'edge.begin_shape_index', 'edge.end_shape_index', 'edge.toll', 'edge.length', 'node.elapsed_time']


def dump(name, value):
    (O / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def load(name):
    return json.loads((O / name).read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source():
    return json.loads((ROOT / 'source.json').read_text())


def check_source_file():
    src = source()
    if (W / 'pilot.osm.pbf').stat().st_size != src['bytes']:
        raise RuntimeError('PBF_SIZE_MISMATCH')
    actual = sha(W / 'pilot.osm.pbf')
    if actual != src['sha256']:
        raise RuntimeError('PBF_SHA256_MISMATCH')
    return {'actualBytes': src['bytes'], 'actualSHA256': actual}


def prepare():
    # Dedicated ephemeral workspace only: stale success files cannot survive a retry.
    if W.exists():
        shutil.rmtree(W)
    O.mkdir(parents=True)
    (W / 'tiles').mkdir()
    src = source()
    dump('manifest.json', {'stage': 'PREPARING', 'source': src, 'globalCertificate': 'INCOMPLETE'})
    free = shutil.disk_usage(ROOT).free
    ram = int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemTotal:'))) * 1024
    dump('resources.json', {'freeBytes': free, 'ramBytes': ram, 'cpu': os.cpu_count(), 'imageOS': os.environ.get('ImageOS'), 'imageVersion': os.environ.get('ImageVersion')})
    if free < 4 * 1024**3 or ram < 7 * 1024**3:
        raise RuntimeError('RESOURCE_BUDGET_INSUFFICIENT')
    if src['url'] != 'https://download.geofabrik.de/europe/monaco-261102.osm.pbf' or not re.fullmatch('[0-9a-f]{64}', src['sha256']):
        raise RuntimeError('SOURCE_NOT_APPROVED')
    if type(src['bytes']) is not int or not 0 < src['bytes'] <= 2 * 1024**2:
        raise RuntimeError('SOURCE_SIZE_INVALID')
    with urllib.request.urlopen(src['url'], timeout=45) as response, (W / 'pilot.osm.pbf').open('wb') as out:
        n = 0
        while block := response.read(65536):
            n += len(block)
            if n > src['bytes']:
                raise RuntimeError('PBF_SIZE_MISMATCH')
            out.write(block)
    verified = check_source_file()
    dump('source-verified.json', {**verified, 'source': src, 'cropped': False, 'restrictionBoundaryCoverage': 'INCOMPLETE'})


def graph_files():
    files = [{'path': str(p.relative_to(W)), 'sha256': sha(p), 'bytes': p.stat().st_size}
             for p in sorted((W / 'tiles').rglob('*')) if p.is_file()]
    if not any(f['path'].endswith('.gph') and f['bytes'] > 0 for f in files):
        raise RuntimeError('NO_GRAPH_TILES')
    return files


def built():
    # Called by run.sh ONLY after docker build command returns zero.
    verified = check_source_file()
    config = load('config.json')
    if config['httpd']['service']['listen'] != 'tcp://*:8002':
        raise RuntimeError('SERVICE_PORT_MISMATCH')
    if config['mjolnir']['tile_dir'] != '/work/tiles' or config['mjolnir']['tile_extract'] != '':
        raise RuntimeError('GRAPH_CONFIGURATION_MISMATCH')
    dump('graph-files.json', graph_files())
    dump('build-success.json', {**verified, 'stage': 'BUILD_COMMAND_SUCCEEDED', 'configSHA256': sha(O / 'config.json'), 'graphManifestSHA256': sha(O / 'graph-files.json'), 'image': IMAGE})


def check_build():
    b = load('build-success.json')
    verified = check_source_file()
    if b['stage'] != 'BUILD_COMMAND_SUCCEEDED' or b['image'] != IMAGE or any(b[k] != v for k, v in verified.items()):
        raise RuntimeError('BUILD_PROOF_INVALID')
    if b['configSHA256'] != sha(O / 'config.json') or b['graphManifestSHA256'] != sha(O / 'graph-files.json') or load('graph-files.json') != graph_files():
        raise RuntimeError('BUILD_ARTIFACT_CHANGED')
    return b


def request(action, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request('http://127.0.0.1:8002/' + action, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def decode(shape):
    if not isinstance(shape, str) or not shape:
        raise RuntimeError('GEOMETRY_MISSING')
    coordinates, previous, i = [], [0, 0], 0
    try:
        while i < len(shape):
            for axis in (0, 1):
                number = shift = 0
                while True:
                    value = ord(shape[i]) - 63
                    i += 1
                    if not 0 <= value <= 63 or shift > 35:
                        raise ValueError('invalid polyline')
                    number |= (value & 31) << shift
                    shift += 5
                    if value < 32:
                        break
                previous[axis] += ~(number >> 1) if number & 1 else number >> 1
            lat, lon = previous[0] / 1e6, previous[1] / 1e6
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError('invalid coordinate')
            coordinates.append((lat, lon))
    except (IndexError, ValueError):
        raise RuntimeError('GEOMETRY_INVALID') from None
    if len(coordinates) < 2:
        raise RuntimeError('GEOMETRY_INSUFFICIENT')
    return coordinates


def coherent(route_shape, trace_shape):
    a, b = decode(route_shape), decode(trace_shape)
    if len(a) != len(b):
        raise RuntimeError('GEOMETRY_CORRESPONDENCE_UNPROVEN')
    maximum = 0.0
    for (la, lo), (lb, ln) in zip(a, b):
        dlat, dlon = math.radians(lb - la), math.radians(ln - lo)
        h = math.sin(dlat / 2)**2 + math.cos(math.radians(la)) * math.cos(math.radians(lb)) * math.sin(dlon / 2)**2
        maximum = max(maximum, 2 * 6371000 * math.asin(min(1.0, math.sqrt(h))))
    if maximum > .2:
        raise RuntimeError('GEOMETRY_MISMATCH')
    return {'method': 'polyline6_ordered_points', 'maxErrorMetres': maximum, 'pointCount': len(a), 'topologyCertified': False}


def verify_trace(leg, trace):
    geometry = coherent(leg['shape'], trace.get('shape'))
    edges = trace.get('edges')
    if not edges:
        raise RuntimeError('TRACE_EDGES_MISSING')
    end = 0
    elapsed = 0.0
    for edge in edges:
        if type(edge.get('way_id')) is not int or edge['way_id'] <= 0:
            raise RuntimeError('WAY_IDS_MISSING')
        begin, finish = edge.get('begin_shape_index'), edge.get('end_shape_index')
        if type(begin) is not int or type(finish) is not int or begin != end or not begin < finish < geometry['pointCount']:
            raise RuntimeError('TRACE_COVERAGE_UNPROVEN')
        if type(edge.get('toll')) is not bool or type(edge.get('length')) not in (int, float) or not math.isfinite(edge['length']) or edge['length'] < 0:
            raise RuntimeError('TRACE_ATTRIBUTES_MISSING')
        value = edge.get('end_node', {}).get('elapsed_time')
        if type(value) not in (int, float) or not math.isfinite(value) or value < elapsed:
            raise RuntimeError('TRACE_TIMING_MISSING_OR_INVALID')
        end, elapsed = finish, value
    if end != geometry['pointCount'] - 1:
        raise RuntimeError('TRACE_COVERAGE_UNPROVEN')
    return {'edgeCount': len(edges), 'geometry': geometry}


def verified_outputs():
    route = load('route.json')
    if route.get('trip', {}).get('status') != 0 or not route['trip'].get('legs'):
        raise RuntimeError('ROUTING_NOT_SUCCESSFUL')
    return [verify_trace(leg, load(f'trace-{i}.json')) for i, leg in enumerate(route['trip']['legs'])]


def probe():
    check_build()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            status = request('status', timeout=2)
            break
        except (OSError, ValueError):
            time.sleep(2)
    else:
        raise RuntimeError('SERVICE_NOT_READY')
    dump('status.json', status)
    if not re.fullmatch(r'3\.9\.1(?:[-+].*)?', str(status.get('version', ''))):
        raise RuntimeError('VALHALLA_VERSION_UNEXPECTED')
    payload = {'locations': [{'lat': 43.7311, 'lon': 7.4206}, {'lat': 43.7391, 'lon': 7.4267}], 'costing': 'auto', 'costing_options': {'auto': {'use_tolls': .5}}, 'units': 'kilometers', 'shape_format': 'polyline6'}
    dump('route-request.json', payload)
    route = request('route', payload)
    dump('route.json', route)
    legs = route.get('trip', {}).get('legs')
    if route.get('trip', {}).get('status') != 0 or not legs:
        raise RuntimeError('ROUTING_NOT_SUCCESSFUL')
    for i, leg in enumerate(legs):
        p = {'encoded_polyline': leg['shape'], 'shape_match': 'edge_walk', 'costing': 'auto', 'costing_options': payload['costing_options'], 'units': 'kilometers', 'filters': {'action': 'include', 'attributes': ATTRIBUTES}}
        dump(f'trace-request-{i}.json', p)
        dump(f'trace-{i}.json', request('trace_attributes', p))
    legs = verified_outputs()
    dump('smoke-result.json', {'status': 'ROUTING_SMOKE_TEST_PASSED', 'legs': legs, 'buildProofSHA256': sha(O / 'build-success.json'), 'globalCertificate': 'INCOMPLETE'})


def report():
    b = check_build()
    result = load('smoke-result.json')
    if result['status'] != 'ROUTING_SMOKE_TEST_PASSED' or result['buildProofSHA256'] != sha(O / 'build-success.json') or result['legs'] != verified_outputs():
        raise RuntimeError('SMOKE_PROOF_INVALID')
    dump('manifest.json', {'stage': 'SMOKE_TEST_PASSED', 'sourcePbf': source(), 'actualPbfSHA256': b['actualSHA256'], 'actualPbfBytes': b['actualBytes'], 'image': IMAGE, 'graphManifestSHA256': b['graphManifestSHA256'], 'configSHA256': b['configSHA256'], 'status': load('status.json'), 'runnerCommit': os.environ.get('GITHUB_SHA'), 'coverage': {'geometry': 'COHERENT_NOT_TOPOLOGICALLY_CERTIFIED', 'restrictions': 'INCOMPLETE', 'boundaries': 'INCOMPLETE'}, 'globalCertificate': 'INCOMPLETE', 'tariffs': False})
    (O / 'REPORT.md').write_text('# Valhalla smoke test\n\nBuild, routing, geometric coherence and way_id retrieval succeeded.\n\nNo global topology certificate. Restrictions and boundaries INCOMPLETE. No APRR data.\n\n© OpenStreetMap contributors — ODbL 1.0. Extract: Geofabrik.\n', encoding='utf-8')


if __name__ == '__main__':
    {'prepare': prepare, 'built': built, 'probe': probe, 'report': report}[sys.argv[1]]()
