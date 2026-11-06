"""Separate A42 scenario. Monaco remains the default, unchanged request."""
import hashlib,json,re,shutil,subprocess,sys
from pathlib import Path
import poc
ROOT=Path(__file__).resolve().parents[1]
SOURCE=json.loads((ROOT/'a42-source.json').read_text())
URL='https://github.com/NogeomHub/valhalla-routing-poc/releases/download/a42-pilot-20261102-v1/a42-meximieux-amberieu.osm.pbf'
EXPECTED='e5912f17f620535e9b3be7dbd2e2b9963c778a7d1a873614b6ae901d1b793235'
poc.source=lambda:SOURCE
OUT=poc.O
ENDPOINTS=[{'lat':45.904129,'lon':5.197079},{'lat':45.958414,'lon':5.368862}]
# Existing OSM node 309487296, way 477698628, northbound A42.
# A synthetic midpoint inserted by route breaks edge_walk 3.9.1 check_shape.
VIA={'lat':45.9134166,'lon':5.2498414,'type':'through'}
def requests():
 common={'costing':'auto','units':'kilometers','shape_format':'polyline6'}
 return {'via-a42':{**common,'locations':[ENDPOINTS[0],VIA,ENDPOINTS[1]],'costing_options':{'auto':{'use_tolls':1.,'use_highways':1.}}},'no-motorway':{**common,'locations':ENDPOINTS,'costing_options':{'auto':{'use_tolls':0.,'use_highways':0.}}}}
def prepare():
 if SOURCE['url']!=URL or SOURCE['bytes']!=1064733 or SOURCE['sha256']!=EXPECTED:raise RuntimeError('A42_SOURCE_NOT_APPROVED')
 manifest=ROOT/SOURCE['extractionManifest']
 if poc.sha(manifest)!=SOURCE['extractionManifestSHA256']:raise RuntimeError('EXTRACTION_MANIFEST_CHANGED')
 m=json.loads(manifest.read_text())
 if m['pilot']['sha256']!=EXPECTED or m['missingDependencies'] or m['outputMissingReferences']:raise RuntimeError('EXTRACT_INTEGRITY_UNPROVEN')
 poc.prepare(approved_url=URL)
 shutil.copy2(manifest,OUT/'extraction-manifest.json')
def at_case(case):
 poc.O=OUT/case;poc.O.mkdir(parents=True,exist_ok=True)
 for name in ('config.json','build-success.json','graph-files.json'):
  if not (poc.O/name).exists():shutil.copy2(OUT/name,poc.O/name)
def criteria(case,audit):
 if audit['topologyStatus']!='PROVEN':raise RuntimeError('OSM_TOPOLOGY_OR_DIRECTION_UNPROVEN')
 if audit['forbiddenRestrictions']:raise RuntimeError('APPLICABLE_RESTRICTION_FORBIDDEN')
 if case=='via-a42' and not audit['a42Edges']:raise RuntimeError('A42_NOT_OBSERVED')
 if case=='no-motorway' and audit['motorwayEdges']:raise RuntimeError('ALTERNATIVE_CONTAINS_MOTORWAY')
def probe():
 poc.check_build();results={};errors={}
 for case,payload in requests().items():
  try:
   at_case(case);poc.probe(payload)
   command=[str(poc.W/'osm-env/bin/python'),str(ROOT/'scripts/audit_route.py'),str(poc.W/'pilot.osm.pbf'),str(poc.O)]
   subprocess.run(command,check=True)
   a=poc.load('osm-audit.json');criteria(case,a)
   poc.report()
   results[case]={'auditSHA256':poc.sha(poc.O/'osm-audit.json'),'smokeSHA256':poc.sha(poc.O/'smoke-result.json')}
  except (RuntimeError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
   errors[case]={'type':type(error).__name__,'reason':str(error),'status':'INCOMPLETE'}
   poc.dump('case-failure.json',errors[case])
 poc.O=OUT;poc.dump('a42-results.json',results);poc.dump('a42-failures.json',errors)
 if errors:raise RuntimeError('A42_CASES_FAILED: '+','.join(errors))

def report():
 poc.O=OUT;b=poc.check_build();results=poc.load('a42-results.json');summaries={}
 if set(results)!=set(requests()):raise RuntimeError('SCENARIO_RESULTS_MISSING')
 for case in requests():
  at_case(case);poc.report();a=poc.load('osm-audit.json');criteria(case,a)
  if a['pbfSHA256']!=b['actualSHA256'] or poc.sha(poc.O/'osm-audit.json')!=results[case]['auditSHA256'] or poc.sha(poc.O/'smoke-result.json')!=results[case]['smokeSHA256']:raise RuntimeError('CASE_PROOF_CHANGED')
  summaries[case]={k:a[k] for k in ('topologyStatus','a42Edges','motorwayEdges','movements','demonstratedRestrictions','unknownRestrictions','permissionUnknowns')}
 poc.O=OUT
 poc.dump('manifest.json',{'stage':'SMOKE_TEST_PASSED','scenario':'a42-pilot','routingTest':'PASSED_TWO_ROUTES','geometricEdgeCoverage':'COMPLETE','sourcePbf':SOURCE,'actualPbfSHA256':b['actualSHA256'],'actualPbfBytes':b['actualBytes'],'image':poc.IMAGE,'graphManifestSHA256':b['graphManifestSHA256'],'configSHA256':b['configSHA256'],'routes':summaries,'globalCertificate':'INCOMPLETE','restrictionsGloballyCertified':False,'timingsCombined':False,'tariffs':False})
 (OUT/'REPORT.md').write_text('# A42 routing smoke test\n\nTwo routes share one graph and one PBF. See manifest and per-route raw evidence.\n\nNo global certificate; restrictions/boundaries remain INCOMPLETE. No tariff calculated.\n\n© OpenStreetMap contributors — ODbL 1.0. Parent: Geofabrik.\n')
if __name__=='__main__':{'prepare':prepare,'built':poc.built,'probe':probe,'report':report}[sys.argv[1]]()
