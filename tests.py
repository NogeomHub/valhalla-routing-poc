"""Offline synthetic checks; do not execute Docker or contact any API."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('poc', Path(__file__).parent/'scripts/poc.py')
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


def encode(points):
    result = ''; previous = [0, 0]
    for point in points:
        for i, value in enumerate(point):
            value = round(value*1e6); delta = value-previous[i]; previous[i] = value
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 32: result += chr((32 | (v & 31))+63); v >>= 5
            result += chr(v+63)
    return result


class Checks(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        root = Path(self.t.name)
        for key, val in [('ROOT', root), ('W', root/'work'), ('O', root/'work/out')]:
            p = patch.object(poc, key, val); p.start(); self.addCleanup(p.stop)
        poc.O.mkdir(parents=True); (poc.W/'tiles').mkdir()
        self.src = {'url':'https://download.geofabrik.de/europe/monaco-261102.osm.pbf','bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
        (root/'source.json').write_text(json.dumps(self.src));(poc.W/'pilot.osm.pbf').write_bytes(b'abc')
        (poc.W/'tiles/0.gph').write_bytes(b'SYNTHETIC_GRAPH_NOT_REAL')
        poc.dump('config.json',{'httpd':{'service':{'listen':'tcp://*:8002'}},'mjolnir':{'tile_dir':'/work/tiles','tile_extract':''}})
        self.shape = encode([(43,7),(43.001,7)])
        self.route = {'trip':{'status':0,'legs':[{'shape':self.shape}]}}
        self.trace = {'shape':self.shape,'edges':[{'way_id':42,'begin_shape_index':0,'end_shape_index':1,'toll':False,'length':.111,'end_node':{'elapsed_time':10}}]}
    def request(self, action, payload=None, **kw):
        return {'version':'3.9.1-SYNTHETIC'} if action=='status' else copy.deepcopy(self.route if action=='route' else self.trace)
    def success(self):
        poc.built()
        with patch.object(poc,'request',self.request): poc.probe()
        poc.report()
    def test_synthetic_success_never_global(self):
        self.success();d=poc.load('manifest.json');self.assertEqual(d['stage'],'SMOKE_TEST_PASSED');self.assertEqual(d['globalCertificate'],'INCOMPLETE');self.assertEqual(d['actualPbfSHA256'],hashlib.sha256(b'abc').hexdigest())
    def test_wrong_download_size(self):
        (poc.W/'pilot.osm.pbf').write_bytes(b'ab')
        with self.assertRaisesRegex(RuntimeError,'PBF_SIZE_MISMATCH'):poc.check_source_file()
    def test_wrong_download_hash(self):
        (poc.W/'pilot.osm.pbf').write_bytes(b'xyz')
        with self.assertRaisesRegex(RuntimeError,'PBF_SHA256_MISMATCH'):poc.check_source_file()
    def test_download_truncated(self):
        with patch.object(poc.urllib.request,'urlopen',return_value=io.BytesIO(b'ab')),self.assertRaisesRegex(RuntimeError,'PBF_SIZE_MISMATCH'):poc.prepare()
    def test_download_oversized(self):
        with patch.object(poc.urllib.request,'urlopen',return_value=io.BytesIO(b'abcd')),self.assertRaisesRegex(RuntimeError,'PBF_SIZE_MISMATCH'):poc.prepare()
    def test_missing_way_id(self):
        self.trace['edges'][0].pop('way_id');poc.built()
        with patch.object(poc,'request',self.request),self.assertRaisesRegex(RuntimeError,'WAY_IDS_MISSING'):poc.probe()
    def test_bad_edge_coverage(self):
        self.trace['edges'][0]['begin_shape_index']=1
        with self.assertRaisesRegex(RuntimeError,'TRACE_COVERAGE_UNPROVEN'):poc.verify_trace(self.route['trip']['legs'][0],self.trace)
    def test_missing_elapsed_time(self):
        self.trace['edges'][0]['end_node']={}
        with self.assertRaisesRegex(RuntimeError,'TIMING'):poc.verify_trace(self.route['trip']['legs'][0],self.trace)
    def test_micro_rounding_accepted_geometrically(self):
        changed=encode([(43.000001,7),(43.001,7)])
        d=poc.coherent(self.shape,changed);self.assertLess(d['maxErrorMetres'],.2);self.assertFalse(d['topologyCertified'])
    def test_geometry_mismatch(self):
        with self.assertRaisesRegex(RuntimeError,'GEOMETRY_MISMATCH'):poc.coherent(self.shape,encode([(43.00001,7),(43.001,7)]))
    def test_geometry_resampling_unproven(self):
        with self.assertRaisesRegex(RuntimeError,'CORRESPONDENCE_UNPROVEN'):poc.coherent(self.shape,encode([(43,7),(43.0005,7),(43.001,7)]))
    def test_bad_polyline(self):
        with self.assertRaisesRegex(RuntimeError,'GEOMETRY_INVALID'):poc.decode('~')
    def test_wrong_port(self):
        c=poc.load('config.json');c['httpd']['service']['listen']='tcp://*:8080';poc.dump('config.json',c)
        with self.assertRaisesRegex(RuntimeError,'PORT_MISMATCH'):poc.built()
    def test_missing_tiles(self):
        (poc.W/'tiles/0.gph').unlink()
        with self.assertRaisesRegex(RuntimeError,'NO_GRAPH_TILES'):poc.built()
    def test_probe_requires_build(self):
        with self.assertRaises(FileNotFoundError):poc.probe()
    def test_report_requires_build(self):
        with self.assertRaises(FileNotFoundError):poc.report()
    def test_report_requires_smoke(self):
        poc.built()
        with self.assertRaises(FileNotFoundError):poc.report()
    def test_failed_routing(self):
        poc.built();self.route['trip']['status']=1
        with patch.object(poc,'request',self.request),self.assertRaisesRegex(RuntimeError,'ROUTING_NOT_SUCCESSFUL'):poc.probe()
    def test_report_rechecks_way_ids(self):
        self.success();self.trace['edges'][0]['way_id']=None;poc.dump('trace-0.json',self.trace)
        with self.assertRaisesRegex(RuntimeError,'WAY_IDS_MISSING'):poc.report()
    def test_report_rechecks_graph_hashes(self):
        self.success();(poc.W/'tiles/0.gph').write_bytes(b'MODIFIED')
        with self.assertRaisesRegex(RuntimeError,'BUILD_ARTIFACT_CHANGED'):poc.report()
    def test_report_rechecks_pbf(self):
        self.success();(poc.W/'pilot.osm.pbf').write_bytes(b'xyz')
        with self.assertRaisesRegex(RuntimeError,'SHA256_MISMATCH'):poc.report()
    def test_report_cli_failure_exits_nonzero(self):
        script=Path(__file__).parent/'scripts/poc.py';target=poc.ROOT/'scripts';target.mkdir();shutil.copy(script,target/'poc.py')
        r=subprocess.run([os.sys.executable,str(target/'poc.py'),'report'],capture_output=True)
        self.assertNotEqual(r.returncode,0)
    def test_shell_propagates_mandatory_failure(self):
        target=poc.ROOT/'scripts';target.mkdir();shutil.copy(Path(__file__).parent/'scripts/run.sh',target/'run.sh')
        binpath=poc.ROOT/'fakebin';binpath.mkdir()
        for name, code in [('python3','17'),('docker','0')]:
            f=binpath/name;f.write_text('#!/bin/sh\nexit '+code+'\n');f.chmod(0o755)
        env=dict(os.environ,PATH=str(binpath)+':'+os.environ['PATH'])
        r=subprocess.run(['bash',str(target/'run.sh')],env=env,capture_output=True)
        self.assertEqual(r.returncode,17)

if __name__=='__main__':unittest.main()
