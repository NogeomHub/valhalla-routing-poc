"""Offline proof composition for a single missing terminal OSM segment.
Neither raw response is modified. No timings are added, no global certificate.
"""
import json,sys,math
from pathlib import Path
import poc

def encode(points):
 out='';previous=[0,0]
 for p in points:
  for k,x in enumerate(p):
   x=round(x*1e6);delta=x-previous[k];previous[k]=x;v=~(delta<<1) if delta<0 else delta<<1
   while v>=32:out+=chr((v&31|32)+63);v>>=5
   out+=chr(v+63)
 return out

def distance(a,b):
 la,lo,lb,ln=map(math.radians,(*a,*b));h=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((ln-lo)/2)**2
 return 2*6371000*math.asin(min(1,math.sqrt(h)))

def complete(leg,primary,terminal,osm):
 a,b=poc.decode(leg['shape']),poc.decode(primary['shape'])
 if len(a)!=len(b)+1 or a[:-1]!=b:raise RuntimeError('NOT_A_PROVEN_SINGLE_SEGMENT_PREFIX')
 base=poc.verify_trace({'shape':encode(a[:-1])},primary)
 tail=poc.verify_trace({'shape':encode(a[-2:])},terminal)
 way=osm['way'];wid=way['id']
 if primary['edges'][-1]['way_id']!=wid or len(terminal['edges'])!=1 or terminal['edges'][0]['way_id']!=wid:raise RuntimeError('TERMINAL_WAY_UNPROVEN')
 # Three traversed positions, unique OSM IDs AND ordered adjacent segments.
 nodes=osm['nodes'];ids=way['nodes'];matched=[]
 for point in a[-3:]:
  candidates=[(i,n) for i,n in enumerate(ids) if distance(point,(nodes[str(n)]['lat'],nodes[str(n)]['lon']))<=.2]
  if len(candidates)!=1:raise RuntimeError('NODE_IDENTITY_UNPROVEN')
  matched.append(candidates[0])
 i,j,k=[x[0] for x in matched];direction=j-i
 if direction not in (-1,1) or k-j!=direction:raise RuntimeError('DIRECTED_OSM_CONTINUITY_UNPROVEN')
 tags=way['tags']
 if any('conditional' in key for key in tags):raise RuntimeError('CONDITIONAL_PERMISSION_UNPROVEN')
 allowed={'no':{-1,1},'yes':{1},'-1':{-1}}.get(tags.get('oneway'))
 if allowed is None or direction not in allowed:raise RuntimeError('DIRECTION_UNPROVEN')
 q=poc.coherent(leg['shape'],encode(b+poc.decode(terminal['shape'])[1:]))
 return {'status':'COMPLETE_GEOMETRIC_EDGE_COVERAGE','globalCertificate':'INCOMPLETE','coverage':[{'source':'primary','routeShapeRange':[0,len(b)-1],'edgeCount':base['edgeCount']},{'source':'terminal','routeShapeRange':[len(b)-1,len(a)-1],'edgeCount':tail['edgeCount'],'way_id':wid,'segment_index':min(j,k),'from_node':matched[1][1],'to_node':matched[2][1]}],'directedContinuityNodes':[x[1] for x in matched],'geometry':q,'timingCombined':False,'rawPrimaryTraceStillIncomplete':True,'notATollTransaction':True}

