#!/usr/bin/env python3
"""Explicit source-preserving StoryboardIR upgrade draft, never a semantic approval."""
from copy import deepcopy
import json
from pathlib import Path
from detail_runtime import ms,digest


def specified(text):return {'status':'specified','text':str(text)} if text else {'status':'not_applicable','text':'来源未指定此项；不得推断新行为'}
def state(raw):
 return {eid:{'position':v['position_m'],'pose':v['pose'],'body_facing':f"yaw={v['yaw_deg']}",
  'head_facing':f"yaw={v['head_yaw_deg']},pitch={v['head_pitch_deg']}",'gaze':v['gaze_target'] or '无指定目标',
  'contacts':v['contacts'],'supports':[v['support']],'controllers':[v['holder']] if v['holder'] else [],
  'visible_parts':[],'condition':v['condition']} for eid,v in raw.items()}

def upgrade(ir):
 if ir.get('schema_version')!='storyboard-ir/1.0':raise ValueError('Expected StoryboardIR 1.0')
 out=deepcopy(ir);out['schema_version']='storyboard-ir/1.1';out['revision']+=1;fps=ir['delivery']['fps']
 def origin(refs,locator):return {'kind':'design','source_refs':refs,'locator':'Legacy source '+locator+'; source content retained, detail completeness requires review'}
 t={'schema':'detail-timeline/1.1','coordinate_system':'x-right,y-up,z-depth; screen and anatomical directions are separate','action_groups':[],'actions':[],'performances':[],'camera_operations':[],'audio_events':[],'state_samples':[],'visibility':[],'segments':[],'source_time_maps':[],'extensions':[],
    'semantic_review':{'status':'PENDING','reviewer':None,'input_sha256':None,'findings':[]}}
 for i,s in enumerate(ir['shots']):
  sid=s['id'];start=ms(s['start_frame'],fps);end=ms(s['end_frame'],fps);orig=origin(s['source_refs'],f'/shots/{i}')
  t['action_groups'].append({'id':'GROUP_'+sid,'parent_id':None,'purpose':s['purpose'],'beat_ids':s['beat_ids'],'origin':orig})
  raw=deepcopy(s['state_start']);samples={start:state(raw)}
  for j,e in enumerate(s['events']):
   before=state(raw)
   for c in e['changes']:raw[c['entity_id']][c['field']]=deepcopy(c['after'])
   after=state(raw);at=ms(e['end_frame'],fps)
   changes=[{'entity_id':eid,'field':k,'before':before[eid][k],'after':v,'at_ms':at} for eid,st in after.items() for k,v in st.items() if v!=before[eid][k]]
   samples[at]=after
   t['actions'].append({'id':e['id'],'semantic_id':e['id'],'parent_id':'GROUP_'+sid,'actor_id':e['actor_id'],'target_id':e['target_id'],
    'start_ms':ms(e['start_frame'],fps),'end_ms':at,'shot_ids':[sid],'origin':origin(e['source_refs'],f'/shots/{i}/events/{j}'),
    'effector':specified(e['effector']),'operation':e['action'],'trigger':e['trigger'],'path':{'status':'unknown','text':'旧版没有独立路径字段；从原动作补齐后复核'},
    'speed':{'status':'unknown','text':'旧版没有独立速度字段；需复核'},'support':specified('；'.join(st['support'] for st in raw.values())),
    'contact':specified(e['kind']+'；目标='+str(e['target_id'])),'feedback':e['feedback'],'settle':json.dumps(e['changes'],ensure_ascii=False),
    'depends_on':[{'action_id':aid,'relation':'after_end','marker':None,'offset_ms':0} for aid in e['depends_on']],
    'markers':[{'id':'END_'+e['id'],'at_ms':at,'meaning':'原事件完成'}],'changes':changes})
  samples[end]=state(s['state_end'])
  for at,st in sorted(samples.items()):t['state_samples'].append({'id':f'STATE_{sid}_{at}','shot_id':sid,'at_ms':at,'entities':st,'origin':orig})
  for j,p in enumerate(s['performance']):
   t['performances'].append({'id':p['id'],'shot_ids':[sid],'start_ms':ms(p['start_frame'],fps),'end_ms':ms(p['end_frame'],fps),'actor_id':p['actor_id'],
    'action_ids':[e['id'] for e in s['events'] if e['actor_id']==p['actor_id'] and max(e['start_frame'],p['start_frame'])<min(e['end_frame'],p['end_frame'])],
    'origin':origin(p['source_refs'],f'/shots/{i}/performance/{j}'),'face':specified('；'.join(x for x in (p['face'],p['micro_expression']) if x)),
    'eyes':specified(p['eyes']),'hands':specified(p['hands']),'body':specified(p['body']),'breathing':{'status':'not_applicable','text':'原文未指定呼吸变化'},
    'voice':specified(p['voice']),'behavior':p['action'],'trigger':p['trigger'],'feedback':p['feedback'],'settle':p['settle'],
    'needed_parts':p['needed_parts'],'readability':'face' if p['micro_expression'] else 'body','psychology':p['psychology']})
  for sub in s['composition']['subjects']:t['visibility'].append({'shot_id':sid,'entity_id':sub['entity_id'],'start_ms':start,'end_ms':end,'parts':sub['visible_parts'],'readability':'face' if s['camera']['size'] in ('close','extreme_close') else 'body','reason':'旧构图静态声明，转身与遮挡需细化'})
  c=s['camera'];t['camera_operations'].append({'id':'CAM_'+sid,'shot_ids':[sid],'start_ms':start,'end_ms':end,'origin':orig,
   'operation':'locked' if c['start_m']==c['end_m'] and ('固定' in c['movement'] or '静止' in c['path']) else 'unknown',
   'start_position':str(c['start_m']),'end_position':str(c['end_m']),'start_framing':c['size']+'；'+s['composition']['rule'],'end_framing':c['size']+'；'+s['composition']['rule'],
   'height':str(c['start_m'][1])+' → '+str(c['end_m'][1]),'orientation':f"pitch={c['pitch_deg']},roll={c['roll_deg']}",
   'path':c['movement']+'；'+c['path'],'speed':'旧版未独立指定速度；需复核','look_at':str(c['look_at_m']),'focus':c['focus'],
   'axis':c['axis_side']+'；'+c['axis_strategy']+'；'+str(c['axis_reason']),'sync_action_ids':[],'precision':'intent'})
  out['shots'][i]['events']=[];out['shots'][i]['performance']=[]
 for u in ir['audio']['utterances']:
  t['audio_events'].append({'id':u['id'],'shot_ids':[u['shot_id']],'start_ms':ms(u['start_frame'],fps),'end_ms':ms(u['end_frame'],fps),'origin':origin([u['source_id']],'/audio/utterances/'+u['id']),
   'kind':u['kind'],'speaker_id':u['speaker_id'],'text':u['text'],'placement':u['placement'],'lip_sync':u['lip_sync'],'route':u['route'],'delivery':u['delivery'],'mix':'对白清楚可辨',
   'overlap_reason':u['overlap_reason'],'source_utterance_id':u['source_utterance_id'],'sync':None,'phrases':[]})
 for c in ir['audio']['cues']:
  t['audio_events'].append({'id':c['id'],'shot_ids':c['shot_ids'],'start_ms':ms(c['start_frame'],fps),'end_ms':ms(c['end_frame'],fps),'origin':origin(c['source_refs'],'/audio/cues/'+c['id']),
   'kind':c['kind'],'speaker_id':None,'text':c['description'],'placement':'environment','lip_sync':False,'route':c['route'],'delivery':'保留原声音设计','mix':c['mix'],
   'overlap_reason':None,'source_utterance_id':None,'sync':{'action_id':c['sync_event'],'anchor':'end','marker_id':None,'offset_ms':0} if c['sync_event'] else None,'phrases':[]})
 out['audio']={'utterances':[],'cues':[]};out['timeline']=t
 # Never fabricate a new assertion for a moved field. Explicit remapping is required.
 affected=[c['id'] for c in ir['contract'] if any('/events/' in x['path'] or '/performance/' in x['path'] or '/audio/' in x['path'] for x in c['checks'])]
 return out,{'schema':'detail-upgrade/1.1','source_sha256':digest(ir),'status':'NEEDS_REVIEW','moved_contracts':affected,'source_original':ir,
             'unknown_details':['path','speed','dynamic visibility','intermediate key poses'],'semantic_review':'PENDING'}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out)
 if out.exists() and any(out.iterdir()):p.error('Output directory must be new')
 ir=json.loads(Path(a.input).read_text());value,report=upgrade(ir);out.mkdir(parents=True,exist_ok=True)
 for n,x in [('storyboard.ir.json',value),('upgrade-report.json',report)]: (out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 print('NEEDS_REVIEW: original retained; no semantic approval created')
