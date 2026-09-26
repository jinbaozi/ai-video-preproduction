"""Explicit spatial 1.2 handoff; no old relation enum in the execution path."""
from copy import deepcopy
from math import isfinite
from .v52_spatial_runtime import bounds,ms,pointer,leaves,digest,content_hash,semantic_status,panel_state
from .v51_adapters import storyboard_to_avir as temporal_static_conversion,lower_contract

def _locked_camera_tracks(ir, avir):
 """Lower an already fixed camera point; do not infer a moving path."""
 nodes=[(i,n) for i,n in enumerate(ir['timeline']['spatial_nodes']) if n['kind']=='camera']
 if len(nodes)!=1:return [],[]
 node_index,node=nodes[0]
 if node['frame']['kind']!='world' or node['frame']['unit']!='m':return [],[]
 used={x['id'] for collection in ('spatial_nodes','motion_tracks','spatial_relations','composition_tracks') for x in ir['timeline'][collection]}
 coverage=[];derived=[]
 for shot_index,shot in enumerate(ir['shots']):
  start,end=bounds(ir)[shot['id']];camera=shot['camera']
  scene=next((s for s in ir['scenes'] if s['id']==shot['scene_id']),None)
  if not scene or scene['coordinates']['axes']!='x=world-right,y=up,z=depth':continue
  point=camera['start_m']
  if not (isinstance(point,list) and len(point)==3 and all(type(x) in (int,float) and isfinite(x) for x in point)
          and camera['end_m']==point):continue
  target_shot=avir['shots'][shot_index]
  if target_shot['camera']['position']!=point:continue
  look_at=target_shot['camera']['look_at']
  if not (isinstance(look_at,list) and len(look_at)==3 and all(type(x) in (int,float) and isfinite(x) for x in look_at)
          and look_at!=point):continue
  if any(t['node_id']==node['id'] and t['property']=='position' and t['start_ms']<end and start<t['end_ms']
         for t in ir['timeline']['motion_tracks']):continue
  operations=[(i,o) for i,o in enumerate(ir['timeline']['camera_operations']) if shot['id'] in o['shot_ids']
              and o['start_ms']<end and start<o['end_ms']]
  if len(operations)!=1:continue
  operation_index,operation=operations[0]
  if operation['operation']!='locked' or operation['start_ms']>start or operation['end_ms']<end:continue
  track_id='CAMERA_POSITION_'+shot['id']
  if track_id in used:continue
  used.add(track_id)
  track_index=len(avir['timeline']['motion_tracks'])
  avir['timeline']['motion_tracks'].append({'id':track_id,'node_id':node['id'],'property':'position',
   'start_ms':start,'end_ms':end,'shot_ids':[shot['id']],'action_ids':[],
   'camera_operation_ids':[operation['id']],'unit':'m','axis':None,
   'path':operation['path'],'speed':operation['speed'],
   'keyframes':[{'at_ms':at,'value':{'mode':'numeric','value':deepcopy(point),
     'description':'冻结分镜 /shots/'+str(shot_index)+'/camera/'+field,'target_node_id':None},
     'transition':transition} for at,field,transition in ((start,'start_m','hold'),(end,'end_m','none'))],
   'origin':{**deepcopy(operation['origin']),'locator':'StoryboardIR /shots/'+str(shot_index)
     +'/camera/start_m, /shots/'+str(shot_index)+'/camera/end_m; /timeline/camera_operations/'
     +str(operation_index)+'; /timeline/spatial_nodes/'+str(node_index)}})
  mappings=[('/shots/'+str(shot_index)+'/camera/start_m',f'/timeline/motion_tracks/{track_index}/keyframes/0/value/value'),
   ('/shots/'+str(shot_index)+'/camera/end_m',f'/timeline/motion_tracks/{track_index}/keyframes/1/value/value'),
   (f'/timeline/camera_operations/{operation_index}/id',f'/timeline/motion_tracks/{track_index}/camera_operation_ids/0'),
   (f'/timeline/spatial_nodes/{node_index}/id',f'/timeline/motion_tracks/{track_index}/node_id')]
  for source,target in mappings:
   coverage.append({'source_path':source,'source_sha256':digest(pointer(ir,source)),'object_id':shot['id'],
    'target_path':target,'target_sha256':digest(pointer(avir,target)),'disposition':'derived','rule':'CAMERA.LOCKED.HOLD.1.2'})
  derived.append({'shot_id':shot['id'],'track_id':track_id,'source_paths':[source for source,_ in mappings],
   'target_paths':[target for _,target in mappings],'rule':'CAMERA.LOCKED.HOLD.1.2'})
 return coverage,derived

def storyboard_to_avir(ir,base,overrides,legacy):
 # Established static fields still use the tested adapter. All spatial content
 # and its contracts bypass the old enums and are transferred separately.
 proxy=deepcopy(ir);proxy['schema_version']='storyboard-ir/1.1';proxy['timeline']['schema']='detail-timeline/1.1'
 for name in ('spatial_nodes','motion_tracks','spatial_relations','composition_tracks'):proxy['timeline'].pop(name)
 proxy['contract']=[]
 avir,report=temporal_static_conversion(proxy,base,overrides,legacy)
 avir['schema']='avir/1.2';avir['timeline']=deepcopy(ir['timeline'])
 camera_coverage,derived_camera_tracks=_locked_camera_tracks(ir,avir)
 coverage=[deepcopy(row) for row in report.get('detail_coverage',[])
  if row.get('rule')=='STATE_SAMPLE.BOUNDARY_VISIBILITY.1.1']
 for path,value in leaves(ir['timeline'],'/timeline'):
  report['field_mapping'][path]=path;target=pointer(avir,path)
  coverage.append({'source_path':path,'source_sha256':digest(value),'object_id':None,'target_path':path,'target_sha256':digest(target),'disposition':'direct' if value==target else 'derived','rule':'SPATIAL.IDENTITY.1.2' if value==target else 'REVIEW.REBIND.1.2'})
 coverage.extend(camera_coverage)
 for clause in ir['contract']:lower_contract(ir,avir,report,clause,overrides)
 report['status']='BLOCKED' if any(x['severity']=='error' for x in report['losses']) else 'MAPPED'
 if semantic_status(ir) and report['status']!='BLOCKED':avir['timeline']['semantic_review']['input_sha256']=content_hash(avir)
 report.update(adapter='1.2.0',source_hash=digest(ir),target_hash=digest(avir),sidecar=deepcopy(ir),detail_coverage=coverage,derived_camera_tracks=derived_camera_tracks,semantic_review='INHERITED_DETERMINISTICALLY' if semantic_status(ir) and report['status']!='BLOCKED' else 'PENDING')
 return avir,report

def image_briefs(ir):
 from .v51_adapters import image_briefs as old_briefs
 rows=old_briefs(ir)
 for row in rows:
  state=panel_state(ir,row['shot_id'],ms(row['frame'],ir['delivery']['fps']))
  row.update(state_evaluation=state,composition=state['composition'],state_start=state['state'],motion_values=state['motion_values'],spatial_relations=state['spatial_relations'])
  # Full input files remain available. Dependency selectors are consumed values
  # at this instant; unrelated changes elsewhere in a track do not invalidate it.
  row['dependency_paths']=[p for p in row['dependency_paths'] if '/panels/' in p or p.startswith('/bindings/')]
  row['events']=[]
  row['camera']=[v for v in state['motion_values'] if next(tr for tr in ir['timeline']['motion_tracks'] if tr['id']==v['track_id'])['node_id'] in {n['id'] for n in ir['timeline']['spatial_nodes'] if n['kind']=='camera'}]
  row['state_evaluation']=spatial_panel_dependency(state)
  shot=next(s for s in ir['shots'] if s['id']==row['shot_id']);row['lens_intent']=shot['camera']['lens_intent']
  row['dependency_paths'].append('/shots/'+str(ir['shots'].index(shot))+'/camera/lens_intent')
  row['spatial_dependency']={'shot_id':row['shot_id'],'at_ms':state['at_ms'],'value':spatial_panel_dependency(state)}
 return rows

def spatial_panel_dependency(state):
 value={k:deepcopy(state[k]) for k in ('at_ms','state','status','composition','motion_values','spatial_relations','nodes','performance')}
 # Evidence provenance remains in native inputs; it is not an image-content change.
 for row in value['nodes']:
  row.pop('origin',None);row['frame']['transforms']=[f for f in row['frame']['transforms'] if f['at_ms']==state['at_ms']]
 if value['composition']:value['composition'].pop('origin',None)
 return value
