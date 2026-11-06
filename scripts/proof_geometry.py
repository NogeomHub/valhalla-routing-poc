"""Offline evidence derivation from archived edge.way_id and the SAME SQLite way.
No nearest-way search, no missing-index defaults, no route or pricing computation.
Only unique trace-chord/OSM-segment matches within the existing .2m rounding
budget are usable. Missing intermediate geometry stays UNKNOWN.
"""
import math
TOLERANCE_METRES=.2

def metric_delta(a,b,lat):return ((b[0]-a[0])*111195*math.cos(math.radians(lat)),(b[1]-a[1])*111195)
def distance(a,b):
 x,y=metric_delta(a,b,(a[1]+b[1])/2);return math.hypot(x,y)
def project(p,a,b):
 dx,dy=metric_delta(a,b,p[1]);px,py=metric_delta(a,p,p[1]);q=dx*dx+dy*dy
 t=max(0,min(1,(px*dx+py*dy)/q)) if q else 0
 return math.hypot(px-t*dx,py-t*dy),t,math.sqrt(q)
def decode(polyline):
 out=[];last=[0,0];i=0
 while i<len(polyline):
  for k in (0,1):
   n=shift=0
   while True:
    v=ord(polyline[i])-63;i+=1;n|=(v&31)<<shift;shift+=5
    if v<32:break
   last[k]+=~(n>>1) if n&1 else n>>1
  out.append([last[1]/1e6,last[0]/1e6])
 return out

def align_edge(db,edge,points):
 wid=edge.get('way_id');base={'way_id':wid,'shapeRange':[edge.get('begin_shape_index'),edge.get('end_shape_index')]}
 if type(wid)!=int:return {**base,'status':'UNKNOWN','reason':'ARCHIVE_WAY_ID_MISSING'}
 rows=db.execute('SELECT w.seq,w.node_id,n.lon,n.lat FROM way_nodes w LEFT JOIN nodes n ON n.id=w.node_id WHERE w.way_id=? ORDER BY w.seq',(wid,)).fetchall()
 if len(rows)<2 or any(r[2] is None or r[3] is None for r in rows):return {**base,'status':'UNKNOWN','reason':'SQLITE_GEOMETRY_MISSING'}
 a,b=base['shapeRange']
 if type(a)!=int or type(b)!=int or not 0<=a<b<len(points):return {**base,'status':'UNKNOWN','reason':'ARCHIVE_SHAPE_RANGE_INVALID'}
 mappings=[]
 for k in range(a,b):
  p,q=points[k:k+2]
  if p==q:continue
  if distance(p,q)<=TOLERANCE_METRES:return {**base,'status':'UNKNOWN','reason':'INSUFFICIENT_CHORD_PROGRESS','chordIndex':k}
  candidates=[]
  for i,(u,v) in enumerate(zip(rows,rows[1:])):
   x,y=[u[2],u[3]],[v[2],v[3]];dp,tp,length=project(p,x,y);dq,tq,_=project(q,x,y)
   if dp<=TOLERANCE_METRES and dq<=TOLERANCE_METRES and abs(tq-tp)*length>TOLERANCE_METRES:
    sign=1 if tq>tp else -1
    candidates.append({'way_id':wid,'segment_index':i,'from_node':u[1] if sign==1 else v[1],'to_node':v[1] if sign==1 else u[1],'sign':sign,'startFraction':tp,'endFraction':tq,'shapeChordIndex':k,'projectionErrorsMetres':[dp,dq]})
  if len(candidates)!=1:return {**base,'status':'UNKNOWN','reason':'CHORD_SEGMENT_AMBIGUOUS' if candidates else 'TRACE_CHORD_NOT_PROVEN_ON_SOURCE_SEGMENT','chordIndex':k,'candidates':candidates}
  current=candidates[0]
  if mappings:
   prev=mappings[-1]
   if prev['segment_index']==current['segment_index']:
    if prev['sign']!=current['sign'] or abs(prev['endFraction']-current['startFraction'])*distance([rows[current['segment_index']][2],rows[current['segment_index']][3]],[rows[current['segment_index']+1][2],rows[current['segment_index']+1][3]])>TOLERANCE_METRES:return {**base,'status':'UNKNOWN','reason':'INTRA_EDGE_PROGRESS_UNPROVEN'}
   elif prev['to_node']!=current['from_node'] or prev['sign']!=current['sign'] or not (abs(prev['segment_index']-current['segment_index'])==1 or rows[0][1]==rows[-1][1] and {prev['segment_index'],current['segment_index']}=={0,len(rows)-2}):return {**base,'status':'UNKNOWN','reason':'INTRA_EDGE_TOPOLOGY_UNPROVEN'}
   if prev['segment_index']!=current['segment_index']:
    coord=db.execute('SELECT lon,lat FROM nodes WHERE id=?',(prev['to_node'],)).fetchone()
    if not coord or distance(points[k],list(coord))>TOLERANCE_METRES or distance(points[prev['shapeChordIndex']+1],list(coord))>TOLERANCE_METRES:return {**base,'status':'UNKNOWN','reason':'INTRA_EDGE_SHARED_NODE_NOT_AT_TRACE_JOINT'}
  mappings.append(current)
 if not mappings:return {**base,'status':'UNKNOWN','reason':'INSUFFICIENT_TRACE_PROGRESS'}
 return {**base,'status':'PROVEN','segments':mappings,'basis':'unique_ordered_chords_on_archived_way_id_no_spatial_way_reassignment'}

def transition(db,ea,eb,points,aa,ab):
 kind='BETWEEN_OSM_WAYS' if ea.get('way_id')!=eb.get('way_id') else 'WITHIN_SAME_OSM_WAY'
 base={'kind':kind,'incomingWay':ea.get('way_id'),'outgoingWay':eb.get('way_id')}
 if aa['status']!='PROVEN' or ab['status']!='PROVEN':return {**base,'status':'UNKNOWN','reason':'EDGE_ALIGNMENT_UNPROVEN','details':[x['reason'] for x in (aa,ab) if x['status']!='PROVEN']}
 if ea['end_shape_index']!=eb['begin_shape_index']:return {**base,'status':'UNKNOWN','reason':'ARCHIVE_EDGES_NOT_CONTIGUOUS'}
 incoming=aa['segments'][-1];outgoing=ab['segments'][0];node=incoming['to_node']
 if node!=outgoing['from_node']:return {**base,'status':'UNKNOWN','reason':'SHARED_OSM_JUNCTION_UNPROVEN'}
 row=db.execute('SELECT lon,lat FROM nodes WHERE id=?',(node,)).fetchone();point=points[ea['end_shape_index']]
 if not row or distance(point,list(row))>TOLERANCE_METRES:return {**base,'status':'UNKNOWN','reason':'TRACE_JUNCTION_NOT_PROVEN_AT_OSM_NODE'}
 clean=lambda x:{k:x[k] for k in ['way_id','segment_index','from_node','to_node']}
 return {**base,'status':'PROVEN','junction':node,'incoming':clean(incoming),'outgoing':clean(outgoing),'shapeIndex':ea['end_shape_index'],'junctionErrorMetres':distance(point,list(row))}
