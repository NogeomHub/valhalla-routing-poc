import osmium,json,sys,math
from pathlib import Path
pbf=Path(sys.argv[1]);wid=int(sys.argv[2]);ways={};nodes={}
class Ways(osmium.SimpleHandler):
 def way(self,w):
  if w.id==wid:ways[w.id]={'id':w.id,'version':w.version,'nodes':[n.ref for n in w.nodes],'tags':dict(w.tags)}
Ways().apply_file(str(pbf))
wanted={n for w in ways.values() for n in w['nodes']}
class Nodes(osmium.SimpleHandler):
 def node(self,n):
  if n.id in wanted:nodes[n.id]={'lat':n.location.lat,'lon':n.location.lon,'version':n.version}
Nodes().apply_file(str(pbf))
print(json.dumps({'way':ways[wid],'nodes':nodes}))
