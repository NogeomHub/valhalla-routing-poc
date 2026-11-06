"""Offline restriction semantics prototype. No pricing/routing integration.
Optional movement evidence identifies the actually traversed OSM segments by
way ID, ordered segment index and directed endpoint node IDs. Coordinates or
bearings never establish connectivity. ALLOWED is relative to known relations,
not a certificate that the relation inventory is complete.
"""
import math

def directed_segment(top,way_id,segment,via,incoming):
 if not segment or segment.get('way_id')!=way_id:return None
 way=getattr(top,'ways',{}).get(way_id);nodes=getattr(top,'nodes',{})
 if not way:return None
 ids=way.get('nodes',[]);idx=segment.get('segment_index')
 if type(idx)!=int or not 0<=idx<len(ids)-1:return None
 a,b=segment.get('from_node'),segment.get('to_node');u,v=ids[idx:idx+2]
 if a==b or u==v:return None
 direction=1 if (a,b)==(u,v) else -1 if (a,b)==(v,u) else None
 if direction is None or (b if incoming else a)!=via:return None
 for n in (a,b):
  p=nodes.get(n)
  if not p or any(not isinstance(p.get(k),(float,int)) or not math.isfinite(p[k]) for k in ('lon','lat')):return None
 if nodes[a]['lon']==nodes[b]['lon'] and nodes[a]['lat']==nodes[b]['lat']:return None
 tags=way.get('tags',{})
 if any('conditional' in k and 'oneway' in k for k in tags):return None
 one=tags.get('oneway','yes' if tags.get('highway') in ('motorway','motorway_link') or tags.get('junction')=='roundabout' else 'no')
 allowed={'yes':{1},'1':{1},'true':{1},'-1':{-1},'no':{1,-1},'0':{1,-1},'false':{1,-1}}.get(one)
 if allowed is None or direction not in allowed:return None
 occurrence=idx+(1 if direction==1 else 0) if incoming else idx+(0 if direction==1 else 1)
 return {'segment_index':idx,'from_node':a,'to_node':b,'direction':direction,'via_occurrence':occurrence}

def same_way_movement(top,way_id,via,incoming=None,outgoing=None):
 a=directed_segment(top,way_id,incoming,via,True);b=directed_segment(top,way_id,outgoing,via,False)
 if not a or not b:return 'UNKNOWN'
 if a['segment_index']==b['segment_index'] and (a['from_node'],a['to_node'])==(b['to_node'],b['from_node']):return 'U_TURN'
 ids=top.ways[way_id]['nodes'];i,j=a['via_occurrence'],b['via_occurrence']
 # First/last occurrence can be the same explicit closure node, never an
 # arbitrary repeated interior occurrence or merely coincident coordinates.
 same_occurrence=i==j or ids[0]==ids[-1]==via and {i,j}=={0,len(ids)-1} and ids.count(via)==2
 if same_occurrence and a['direction']==b['direction']:return 'CONTINUATION'
 return 'UNKNOWN'

def turn_status(top,previous,current,node,incoming=None,outgoing=None):
 movement=None
 if previous==current:
  movement=same_way_movement(top,previous,node,incoming,outgoing)
  if movement=='UNKNOWN':return 'UNPROVEN_SAME_WAY_MOVEMENT'
 elif incoming is not None or outgoing is not None:
  if not directed_segment(top,previous,incoming,node,True) or not directed_segment(top,current,outgoing,node,False):return 'UNPROVEN_DIRECTED_MOVEMENT'
 for r in getattr(top,'restrictions',[]):
  members=r.get('members',[]);f=[m for m in members if m.get('role')=='from'];to=[m for m in members if m.get('role')=='to'];via=[m for m in members if m.get('role')=='via']
  if not any(m['ref']==previous for m in f):continue
  if any(m.get('type')=='way' for m in via):return 'UNPROVEN_VIA_WAY_RESTRICTION'
  if not any(m.get('type')=='node' and m['ref']==node for m in via):continue
  tags=r.get('tags',{});rule=tags.get('restriction:motorcar',tags.get('restriction:motor_vehicle',tags.get('restriction','')))
  if any('conditional' in k for k in tags):return 'UNPROVEN_CONDITIONAL_RESTRICTION'
  if tags.get('except'):return 'UNPROVEN_EXCEPTION_CONTEXT'
  target=any(m.get('type')=='way' and m['ref']==current for m in to)
  if previous==current and target:
   if rule=='no_u_turn':
    if movement=='U_TURN':return 'FORBIDDEN'
    continue
   if rule=='no_straight_on':
    if movement=='CONTINUATION':return 'FORBIDDEN'
    continue
   if rule=='only_straight_on':
    if movement!='CONTINUATION':return 'FORBIDDEN'
    continue
   if rule=='only_u_turn':
    if movement!='U_TURN':return 'FORBIDDEN'
    continue
   return 'UNPROVEN_SAME_WAY_RESTRICTION_SEMANTICS'
  if rule.startswith('no_') and target or rule.startswith('only_') and not target:return 'FORBIDDEN'
  if not rule.startswith(('no_','only_')):return 'UNPROVEN_RESTRICTION_TYPE'
 return 'ALLOWED'
