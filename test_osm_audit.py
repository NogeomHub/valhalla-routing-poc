"""Synthetic PBF audit tests; run using the isolated osmium environment."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'scripts'))
import osmium
from terminal import encode
from audit_route import run
class AuditTests(unittest.TestCase):
 def fixture(self,root,rule=None,conditional=False,disconnected=False,reverse=False,internal=False):
  pbf=root/'pilot.pbf';w=osmium.SimpleWriter(str(pbf))
  for i,lon in [(1,5.),(2,5.001),(3,5.002),(4,5.001)]:w.add_node(osmium.osm.mutable.Node(id=i,location=osmium.osm.Location(lon,46.)))
  w.add_way(osmium.osm.mutable.Way(id=10,nodes=[1,2,3] if internal else [1,2],tags={'highway':'primary','oneway':'-1' if reverse else 'no'}))
  if not internal:w.add_way(osmium.osm.mutable.Way(id=20,nodes=[4 if disconnected else 2,3],tags={'highway':'primary','oneway':'no'}))
  if rule:
   tags={'type':'restriction','restriction':rule}
   if conditional:tags['restriction:conditional']=rule+' @ (Mo-Fr)'
   w.add_relation(osmium.osm.mutable.Relation(id=100,tags=tags,members=[('w',10,'from'),('n',2,'via'),('w',10 if internal else 20,'to')]))
  w.close();shape=encode([(46.,5.),(46.,5.001),(46.,5.002)])
  edges=[{'way_id':10,'begin_shape_index':0,'end_shape_index':2}] if internal else [{'way_id':10,'begin_shape_index':0,'end_shape_index':1},{'way_id':20,'begin_shape_index':1,'end_shape_index':2}]
  (root/'route.json').write_text(json.dumps({'trip':{'legs':[{'shape':shape}]}}));(root/'trace-0.json').write_text(json.dumps({'shape':shape,'edges':edges}));return run(pbf,root)
 def case(self,**kw):
  with tempfile.TemporaryDirectory() as t:return self.fixture(Path(t),**kw)
 def test_real_node_connection(self):self.assertEqual(self.case()['topologyStatus'],'PROVEN')
 def test_coincident_nodes_not_connection(self):self.assertEqual(self.case(disconnected=True)['topologyStatus'],'UNPROVEN')
 def test_reverse_direction_refused(self):self.assertEqual(self.case(reverse=True)['topologyStatus'],'UNPROVEN')
 def test_forbidden_restriction_detected(self):self.assertEqual(len(self.case(rule='no_left_turn')['forbiddenRestrictions']),1)
 def test_conditional_unknown_not_allowed(self):
  r=self.case(rule='no_left_turn',conditional=True);self.assertTrue(r['unknownRestrictions']);self.assertFalse(r['demonstratedRestrictions']);self.assertFalse(r['forbiddenRestrictions'])
 def test_internal_movement_not_omitted(self):self.assertEqual(len(self.case(rule='no_straight_on',internal=True)['forbiddenRestrictions']),1)
if __name__=='__main__':unittest.main()
