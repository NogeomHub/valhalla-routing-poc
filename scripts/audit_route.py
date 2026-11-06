"""Read-only PBF proofs, including movements internal to Valhalla edges.
Semantic decisions are relative to this extract, never global authorization.
"""
import hashlib,json,sqlite3,sys
from pathlib import Path
from types import SimpleNamespace
import osmium
from proof_geometry import align_edge,decode,distance
from proof_restrictions import directed_segment,turn_status
RULES={'no_left_turn','no_right_turn','no_u_turn','no_straight_on','only_left_turn','only_right_turn','only_straight_on','only_u_turn'}

def run(pbf,folder):
 db=sqlite3.connect(':memory:');db.executescript('CREATE TABLE nodes(id INTEGER PRIMARY KEY,lon REAL,lat REAL);CREATE TABLE way_nodes(way_id INTEGER,seq INTEGER,node_id INTEGER);CREATE INDEX way_nodes_by_way ON way_nodes(way_id,seq);')
 top=SimpleNamespace(nodes={},ways={},restrictions=[])
 class Read(osmium.SimpleHandler):
  def node(self,n):
   top.nodes[n.id]={'lon':n.location.lon,'lat':n.location.lat,'tags':dict(n.tags),'version':n.version};db.execute('INSERT INTO nodes VALUES(?,?,?)',(n.id,n.location.lon,n.location.lat))
  def way(self,w):
   ids=[n.ref for n in w.nodes];top.ways[w.id]={'nodes':ids,'tags':dict(w.tags),'version':w.version};db.executemany('INSERT INTO way_nodes VALUES(?,?,?)',[(w.id,i,n) for i,n in enumerate(ids)])
  def relation(self,r):
   top.restrictions.append({'id':r.id,'tags':dict(r.tags),'members':[{'type':{'n':'node','w':'way','r':'relation'}[m.type],'ref':m.ref,'role':m.role} for m in r.members],'version':r.version})
 Read().apply_file(str(pbf))
 route=json.loads((folder/'route.json').read_text());sequence=[];failures=[];demonstrated=[];unknown=[];forbidden=[];permissions=[];a42=[];motorway=[];matchedways=set();allmoves=[];candidates={}
 for leg_index,_ in enumerate(route['trip']['legs']):
  chunks=[json.loads((folder/f'trace-{leg_index}.json').read_text())]
  tail=folder/f'terminal-trace-{leg_index}.json'
  if tail.exists():chunks.append(json.loads(tail.read_text()))
  legseq=[]
  for trace in chunks:
   points=decode(trace['shape'])
   for edge in trace['edges']:
    wid=edge['way_id'];matchedways.add(wid);w=top.ways.get(wid)
    if not w:failures.append({'reason':'WAY_ABSENT','way':wid});continue
    tags=w['tags']
    if any(k.startswith('oneway:') for k in tags):failures.append({'way':wid,'reason':'SPECIFIC_DIRECTION_OVERRIDE_UNPROVEN'})
    ref=tags.get('ref','').replace(' ','').split(';')
    if 'A42' in ref:a42.append(wid)
    if tags.get('highway') in ('motorway','motorway_link'):motorway.append(wid)
    access=next((tags[k] for k in ('motorcar','motor_vehicle','vehicle','access') if k in tags),None)
    if access is not None and access not in ('yes','designated','permissive'):permissions.append({'way':wid,'reason':'ACCESS_CONTEXT_UNPROVEN','value':access})
    if any('conditional' in k and not k.startswith(('maxspeed','parking')) for k in tags):permissions.append({'way':wid,'reason':'CONDITIONAL_PERMISSION_UNPROVEN'})
    proof=align_edge(db,edge,points)
    if proof['status']!='PROVEN':failures.append(proof);continue
    for s in proof['segments']:
     if not directed_segment(top,wid,s,s['to_node'],True):failures.append({'reason':'DIRECTED_SEGMENT_UNPROVEN','segment':s})
     key=(wid,s['segment_index'],s['from_node'],s['to_node'])
     record={**s,'traceStart':points[s['shapeChordIndex']],'traceEnd':points[s['shapeChordIndex']+1]}
     if legseq and key==legseq[-1]['key']:legseq[-1]['traceEnd']=record['traceEnd'];continue
     legseq.append({**record,'key':key})
  for i,(a,b) in enumerate(zip(legseq,legseq[1:])):
   node=a['to_node'];coord=top.nodes.get(node)
   if node!=b['from_node'] or not coord:
    # Explicit node identity first; coordinates are checked separately below.
    failures.append({'reason':'SHARED_NODE_UNPROVEN','a':a,'b':b});continue
   # proof_geometry.decode and distance both use longitude/latitude.
   ll=[coord['lon'],coord['lat']]
   if distance(a['traceEnd'],ll)>.2 or distance(b['traceStart'],ll)>.2:
    failures.append({'reason':'TRACE_NOT_AT_SHARED_NODE','node':node});continue
   relevant=[]
   for r in top.restrictions:
    ms=r['members'];froms=[m for m in ms if m['role']=='from'];vias=[m for m in ms if m['role']=='via']
    if any(m['type']=='way' and m['ref'] in (a['way_id'],b['way_id']) for m in vias):
     candidates[r['id']]=r;unknown.append({'relation':r['id'],'reason':'VIA_WAY_PATH_UNPROVEN','leg':leg_index,'movement':i})
    if not any(m['type']=='way' and m['ref']==a['way_id'] for m in froms):continue
    if any(m['type']=='way' for m in vias):
     candidates[r['id']]=r;unknown.append({'relation':r['id'],'reason':'VIA_WAY_PATH_UNPROVEN','leg':leg_index,'movement':i});continue
    if not any(m['type']=='node' and m['ref']==node for m in vias):continue
    candidates[r['id']]=r;tags=r['tags'];rule=tags.get('restriction:motorcar',tags.get('restriction:motor_vehicle',tags.get('restriction')))
    valid=tags.get('type')=='restriction' and len(ms)==3 and len(vias)==1 and len(froms)==1 and sum(m['role']=='to' and m['type']=='way' for m in ms)==1
    if not valid or rule not in RULES or tags.get('except') or any('conditional' in k for k in tags):unknown.append({'relation':r['id'],'reason':'SEMANTICS_OR_CONTEXT_UNPROVEN','leg':leg_index,'movement':i});continue
    one=SimpleNamespace(ways=top.ways,nodes=top.nodes,restrictions=[r]);status=turn_status(one,a['way_id'],b['way_id'],node,a,b)
    record={'relation':r['id'],'decision':status,'leg':leg_index,'movement':i,'node':node}
    (demonstrated if status=='ALLOWED' else forbidden if status=='FORBIDDEN' else unknown).append(record)
   clean=SimpleNamespace(ways=top.ways,nodes=top.nodes,restrictions=[])
   if turn_status(clean,a['way_id'],b['way_id'],node,a,b)!='ALLOWED':failures.append({'reason':'MOVEMENT_OR_DIRECTION_UNPROVEN','node':node})
   node_tags=coord.get('tags',{})
   if any(k in node_tags for k in ('barrier','access','motor_vehicle','motorcar')):permissions.append({'node':node,'reason':'NODE_PERMISSION_CONTEXT_REQUIRED','tags':node_tags})
   allmoves.append({'leg':leg_index,'index':i,'junction':node,'incoming':a,'outgoing':b})
  sequence.extend(legseq)
 result={'pbfSHA256':hashlib.sha256(pbf.read_bytes()).hexdigest(),'topologyStatus':'UNPROVEN' if failures else 'PROVEN','failures':failures,'a42Edges':a42,'motorwayEdges':motorway,'movements':len(allmoves),'movementProofs':allmoves,'segmentProofs':sequence,'demonstratedRestrictions':demonstrated,'unknownRestrictions':unknown,'forbiddenRestrictions':forbidden,'permissionUnknowns':permissions,'restrictionSourceRecords':list(candidates.values()),'usedWayRecords':{str(w):top.ways[w] for w in sorted(matchedways)},'usedNodeRecords':{str(n):top.nodes[n] for w in matchedways for n in top.ways[w]['nodes']},'restrictionInventoryScope':'relative_to_pilot_PBF','globalCertificate':'INCOMPLETE'}
 (folder/'osm-audit.json').write_text(json.dumps(result,indent=2));db.close();return result
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
