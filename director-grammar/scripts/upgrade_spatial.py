#!/usr/bin/env python3
"""Source-preserving 1.1 -> 1.2 draft. Missing trajectories are not invented."""
from copy import deepcopy
from pathlib import Path
import json,argparse,hashlib
from spatial_runtime import digest,encoded,bounds

def upgrade(ir):
 key='schema' if 'schema' in ir else 'schema_version';versions={'avir/1.1':'avir/1.2','storyboard-ir/1.1':'storyboard-ir/1.2','1.1':'1.2'}
 if ir.get(key) not in versions:raise ValueError('First explicitly upgrade native 1.0 to 1.1; source file is never overwritten')
 out=deepcopy(ir);out[key]=versions[ir[key]];out['revision']+=1;t=out['timeline'];t['schema']='detail-timeline/1.2';t.update(spatial_nodes=[],motion_tracks=[],spatial_relations=[],composition_tracks=[])
 source=out['sources'][0]['id'];origin={'kind':'design','source_refs':[source],'locator':'Source-preserving upgrade draft; inherited fields require review, not new observed evidence'}
 def node(id,eid,label,kind='entity',part=None,parent=None):
  return {'id':id,'entity_id':eid,'kind':kind,'label':label,'part':part,'parent_id':parent,'frame':{'kind':'world','anchor_node_id':None,'unit':'m','transforms':[]},'bounds':None,'origin':deepcopy(origin)}
 for entity in out['entities']:t['spatial_nodes'].append(node('N_'+entity['id'],entity['id'],entity.get('name',entity.get('label',entity['id']))))
 t['spatial_nodes'].append(node('N_CAMERA',None,'摄影机','camera'))
 mapping={}
 for shot in out['shots']:
  sid=shot['id'];start,end=bounds(out)[sid]
  samples=[s for s in t['state_samples'] if s['shot_id']==sid]
  for entity in out['entities']:
   eid=entity['id'];keys=[]
   for sample in sorted(samples,key=lambda s:s['at_ms']):
    if eid in sample['entities'] and sample['entities'][eid]['position'] is not None:
     keys.append({'at_ms':sample['at_ms'],'value':{'mode':'numeric','value':sample['entities'][eid]['position'],'description':sample['entities'][eid]['pose'],'target_node_id':None},'transition':'none'})
   if len(keys)>=2 and keys[0]['at_ms']==start and keys[-1]['at_ms']==end:
    t['motion_tracks'].append({'id':'POS_'+sid+'_'+eid,'node_id':'N_'+eid,'property':'position','start_ms':start,'end_ms':end,'shot_ids':[sid],'action_ids':[a['id'] for a in t['actions'] if a['actor_id']==eid and sid in a['shot_ids']],'camera_operation_ids':[],'unit':'m','axis':None,'path':'继承原件已明确的关键位置；节点之间不自动插值','speed':'继承原件动作节奏；未指定中间速度不补数值','keyframes':keys,'origin':deepcopy(origin)})
  composition=shot['composition'];subjects=composition.get('subjects')
  if subjects is None and composition.get('screen_positions','').startswith('{'):
   native=json.loads(composition['screen_positions']);subjects=native.get('subjects');composition=native
  if subjects is None:
   subjects=[{'entity_id':v['entity_id'],'visible_parts':v['parts'],'box':None,'depth':'unspecified','occlusion':'旧版未提供动态遮挡；待补齐'} for v in composition.get('required_visible',[])]
  if not subjects:subjects=[{'entity_id':out['entities'][0]['id'],'visible_parts':[],'box':None,'depth':'unspecified','occlusion':'待核对原构图'}]
  for sub in subjects:
   box=sub.get('box')
   if isinstance(box,dict):box=list(box.values())
  t['composition_tracks'].append({'id':'COMP_'+sid,'shot_ids':[sid],'start_ms':start,'end_ms':end,'framing':composition.get('rule',composition.get('framing','继承原构图，待逐时段审查')),'attention_order':['N_'+x for x in composition.get('attention_order',[subjects[0]['entity_id']])],'negative_space':composition.get('negative_space','继承原构图留白，动态变化待审查'),'safe_area':composition.get('safe_area','继承原安全区，动态变化待审查'),'depth_layers':composition.get('depth_layers',composition.get('layers','继承原前中后景')),'subjects':[{'node_id':'N_'+s['entity_id'],'box':s.get('box') if isinstance(s.get('box'),list) else None,'depth':s.get('depth','unspecified'),'visible_parts':s.get('visible_parts',s.get('parts',[])),'occlusion':s.get('occlusion','原件未单独声明遮挡变化'),'readability':next((v['readability'] for v in t['visibility'] if v['entity_id']==s['entity_id'] and v['shot_id']==sid),'body'),'presence':'inside','description':'继承原件主体构图；需确认本区间内是否发生变化'} for s in subjects],'origin':deepcopy(origin)})
  for j,r in enumerate(shot.get('relations',[])):
   at=r.get('at','both');scope={'kind':'interval','start_ms':start,'end_ms':end} if at=='both' else {'kind':'point','at_ms':start if at=='start' else end}
   # A cut boundary belongs to the next half-open shot; the point is still original evidence.
   related=[ss for ss,(a,b) in bounds(out).items() if a<=scope.get('at_ms',start)<b or scope.get('at_ms')==b==max(z[1] for z in bounds(out).values())] if at!='both' else [sid]
   predicate={'facing':'faces'}.get(r['relation'],r['relation']);idx=len(t['spatial_relations'])
   t['spatial_relations'].append({'id':'REL_'+sid+'_'+str(j),'subject_node_id':'N_'+r['subject'],'object_node_id':'N_'+r['object'],'predicate':predicate,'frame':'screen' if predicate.startswith('screen_') else 'world','scope':scope,'shot_ids':related,'criterion':r.get('criterion',r.get('description','保留原相对关系')),'distance_m':r.get('max_distance_m'),'attachment':None,'origin':deepcopy(origin)})
   mapping[f"/shots/{out['shots'].index(shot)}/relations/{j}"]=f'/timeline/spatial_relations/{idx}'
  shot['relations']=[]
 t['semantic_review']={'status':'PENDING','reviewer':None,'input_sha256':None,'findings':[]}
 return out,{'schema':'spatial-upgrade/1.2','source_sha256':digest(ir),'status':'NEEDS_REVIEW','mapping':mapping,'missing':['逐时段核对构图、关系范围、部位轨迹、朝向和坐标依据','原文缺少的信息保持待补齐；不能声称无损恢复连续运动','合同 Pointer 需按字段映射逐项审查'],'source_unchanged':True,'media':'NOT_RUN'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--out',required=True);a=p.parse_args();dest=Path(a.out)
 if dest.exists() and any(dest.iterdir()):p.error('Use a new empty output directory')
 source=Path(a.input).resolve();ir,report=upgrade(json.loads(source.read_text()));
 report['source_file_sha256']=hashlib.sha256(source.read_bytes()).hexdigest();report['file_rebindings']=[]
 for collection,key in (('sources','uri'),('assets','path')):
  for index,ref in enumerate(ir.get(collection,[])):
   value=ref.get(key)
   if value and '://' not in value and not Path(value).is_absolute():
    resolved=(source.parent/value).resolve();ref[key]=str(resolved);report['file_rebindings'].append({'path':f'/{collection}/{index}/{key}','original':value,'resolved':str(resolved),'exists':resolved.is_file()})
 dest.mkdir(parents=True,exist_ok=True)
 (dest/'original.json').write_bytes(source.read_bytes());(dest/'draft-1.2.json').write_bytes(encoded(ir));(dest/'upgrade-report.json').write_bytes(encoded(report));print(report['status'])
if __name__=='__main__':main()
