"""Explicit spatial 1.2 handoff; no old relation enum in the execution path."""
from copy import deepcopy
from .v52_spatial_runtime import bounds,ms,pointer,leaves,digest,content_hash,semantic_status,panel_state
from .v51_adapters import storyboard_to_avir as temporal_static_conversion

def storyboard_to_avir(ir,base,overrides,legacy):
 # Established static fields still use the tested adapter. All spatial content
 # and its contracts bypass the old enums and are transferred separately.
 proxy=deepcopy(ir);proxy['schema_version']='storyboard-ir/1.1';proxy['timeline']['schema']='detail-timeline/1.1'
 for name in ('spatial_nodes','motion_tracks','spatial_relations','composition_tracks'):proxy['timeline'].pop(name)
 extra=[c for c in proxy['contract'] if any(x['path'].startswith('/timeline/') for x in c['checks'])]
 proxy['contract']=[c for c in proxy['contract'] if c not in extra]
 avir,report=temporal_static_conversion(proxy,base,overrides,legacy)
 avir['schema']='avir/1.2';avir['timeline']=deepcopy(ir['timeline'])
 for clause in extra:
  checks=[]
  for check in clause['checks']:
   if check['path'].startswith('/timeline/'):
    checks.append(deepcopy(check));continue
   target=report['field_mapping'].get(check['path'])
   if target:
    mapped={'path':target,'op':'exists' if check['op']=='exists' else 'equals'}
    if check['op']!='exists':mapped['value']=deepcopy(pointer(avir,target))
    checks.append(mapped)
   else:checks.append(deepcopy(check))
  avir['contract'].append({'id':clause['id'],'level':clause['strength'],'requirement':clause['statement'],'source_refs':clause['source_refs'],'shot_ids':clause['shot_ids'],'checks':checks,'channel':clause['channel'],'execution':clause['execution'],'acceptance':{'method':'media','criterion':'；'.join(a['criterion'] for a in clause['acceptance'])},'on_unsupported':'block' if clause['strength']=='hard' else 'warn'})
 if semantic_status(ir) and report['status']!='BLOCKED':avir['timeline']['semantic_review']['input_sha256']=content_hash(avir)
 coverage=[]
 for path,value in leaves(ir['timeline'],'/timeline'):
  report['field_mapping'][path]=path;target=pointer(avir,path)
  coverage.append({'source_path':path,'source_sha256':digest(value),'object_id':None,'target_path':path,'target_sha256':digest(target),'disposition':'direct' if value==target else 'derived','rule':'SPATIAL.IDENTITY.1.2' if value==target else 'REVIEW.REBIND.1.2'})
 report.update(adapter='1.2.0',source_hash=digest(ir),target_hash=digest(avir),sidecar=deepcopy(ir),detail_coverage=coverage,semantic_review='INHERITED_DETERMINISTICALLY' if semantic_status(ir) and report['status']!='BLOCKED' else 'PENDING')
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
