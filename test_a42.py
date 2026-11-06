"""Offline scenario tests, executed separately from Monaco tests."""
import sys,unittest,json,sqlite3
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parent/'scripts'))
import a42
from proof_geometry import align_edge,transition
from proof_restrictions import directed_segment,turn_status
class A42Tests(unittest.TestCase):
 def audit(self):return {'topologyStatus':'PROVEN','forbiddenRestrictions':[],'a42Edges':[1],'motorwayEdges':[1],'unknownRestrictions':[]}
 def test_reference_default_kept(self):
  s=(Path(__file__).parent/'.github/workflows/valhalla-poc.yml').read_text();self.assertIn('default: monaco',s);self.assertIn('- a42-pilot',s)
 def test_exact_endpoints(self):
  p=a42.requests();self.assertEqual(p['via-a42']['locations'][0],p['no-motorway']['locations'][0]);self.assertEqual(p['via-a42']['locations'][-1],p['no-motorway']['locations'][-1])
 def test_avoidance_is_soft_preference(self):self.assertEqual(a42.requests()['no-motorway']['costing_options']['auto']['use_highways'],0)
 def test_a42_absent_rejected(self):
  a=self.audit();a['a42Edges']=[]
  with self.assertRaisesRegex(RuntimeError,'A42_NOT_OBSERVED'):a42.criteria('via-a42',a)
 def test_motorway_on_alternative_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'CONTAINS_MOTORWAY'):a42.criteria('no-motorway',self.audit())
 def test_forbidden_restriction_rejected(self):
  a=self.audit();a['forbiddenRestrictions']=[{'id':1}]
  with self.assertRaisesRegex(RuntimeError,'RESTRICTION_FORBIDDEN'):a42.criteria('via-a42',a)
 def test_unknown_topology_rejected(self):
  a=self.audit();a['topologyStatus']='UNPROVEN'
  with self.assertRaisesRegex(RuntimeError,'TOPOLOGY_OR_DIRECTION'):a42.criteria('via-a42',a)
 def test_restriction_unknown_never_claimed_global(self):
  a=self.audit();a['unknownRestrictions']=[{'reason':'CONTEXT_MISSING'}];a42.criteria('via-a42',a)
  self.assertIn("'globalCertificate':'INCOMPLETE'",(Path(__file__).parent/'scripts/a42.py').read_text())
 def test_source_is_frozen(self):
  self.assertEqual(a42.SOURCE['sha256'],a42.EXPECTED);self.assertEqual(a42.SOURCE['bytes'],1064733);self.assertIn('/releases/download/a42-pilot-20261102-v1/',a42.URL)
 def test_opposing_direction_rejected(self):
  top=SimpleNamespace(ways={1:{'nodes':[1,2],'tags':{'oneway':'yes'}}},nodes={1:{'lon':5.,'lat':46.},2:{'lon':5.001,'lat':46.}})
  self.assertIsNone(directed_segment(top,1,{'way_id':1,'segment_index':0,'from_node':2,'to_node':1},1,True))
 def test_same_way_uturn_is_forbidden(self):
  t=SimpleNamespace(ways={1:{'nodes':[1,2],'tags':{'oneway':'no'}}},nodes={1:{'lon':5.,'lat':46.},2:{'lon':5.001,'lat':46.}},restrictions=[{'tags':{'restriction':'no_u_turn'},'members':[{'type':'way','ref':1,'role':'from'},{'type':'node','ref':2,'role':'via'},{'type':'way','ref':1,'role':'to'}]}])
  a={'way_id':1,'segment_index':0,'from_node':1,'to_node':2};b={**a,'from_node':2,'to_node':1};self.assertEqual(turn_status(t,1,1,2,a,b),'FORBIDDEN')
 def test_coincident_coordinates_do_not_connect(self):
  db=sqlite3.connect(':memory:');db.executescript('CREATE TABLE nodes(id INTEGER,lon REAL,lat REAL);CREATE TABLE way_nodes(way_id INTEGER,seq INTEGER,node_id INTEGER);INSERT INTO nodes VALUES(1,5.,46.),(2,5.001,46.),(3,5.001,46.),(4,5.002,46.);INSERT INTO way_nodes VALUES(1,0,1),(1,1,2),(2,0,3),(2,1,4);')
  p=[[5.,46.],[5.001,46.],[5.002,46.]];a={'way_id':1,'begin_shape_index':0,'end_shape_index':1};b={'way_id':2,'begin_shape_index':1,'end_shape_index':2}
  r=transition(db,a,b,p,align_edge(db,a,p),align_edge(db,b,p));self.assertEqual(r['status'],'UNKNOWN');db.close()
class Real443Regression(unittest.TestCase):
 def setUp(self):
  self.f=json.loads((Path(__file__).parent/'tests_data/a42-v553-real.json').read_text())
 def test_actual_443_is_edge_walk_failure(self):
  self.assertEqual(self.f['originalError']['error_code'],443);self.assertEqual(self.f['originalError']['status_code'],400)
 def test_only_inserted_vertex_removed(self):
  a=a42.poc.decode(self.f['originalLeg']['shape']);b=a42.poc.decode(self.f['correctedLeg']['shape'])
  self.assertEqual(len(a),627);self.assertEqual(len(b),626);self.assertEqual(a[:214]+a[215:],b)
  self.assertEqual(self.f['originalSummary'],self.f['correctedSummary'])
 def test_real_corrected_trace_complete_and_coherent(self):
  r=a42.poc.verify_trace(self.f['correctedLeg'],self.f['correctedTrace']);self.assertEqual(r['edgeCount'],160);self.assertEqual(r['geometry']['maxErrorMetres'],0);self.assertFalse(r['geometry']['topologyCertified'])
 def test_waypoint_is_existing_directed_way_node(self):
  self.assertEqual(a42.VIA,self.f['correctedRequest']['locations'][1]);n=self.f['osm']['nodes']['309487296']
  self.assertEqual((a42.VIA['lat'],a42.VIA['lon']),(n['lat'],n['lon']));self.assertEqual(self.f['osm']['way']['tags']['oneway'],'yes')
 def test_corrected_trace_not_substituted_for_original_route(self):
  with self.assertRaisesRegex(RuntimeError,'GEOMETRY_CORRESPONDENCE_UNPROVEN'):a42.poc.verify_trace(self.f['originalLeg'],self.f['correctedTrace'])

if __name__=='__main__':unittest.main()
