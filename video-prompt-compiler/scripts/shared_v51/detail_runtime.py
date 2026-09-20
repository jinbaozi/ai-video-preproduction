"""V5.1 temporal semantics. Distributed verbatim; source: video-prompt-compiler.
No sibling imports, model calls, hidden interpolation or media success claims.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from jsonschema import Draft202012Validator

VERSION='1.1.0'
COLLECTIONS=('actions','performances','camera_operations','audio_events')
def encoded(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def digest(x):return sha256(encoded(x)).hexdigest()
def is_new(ir):return ir.get('schema')=='avir/1.1' or ir.get('schema_version') in ('1.1','storyboard-ir/1.1')
def issue(code,path,message,severity='error'):return dict(code=code,path=path,message=message,severity=severity)
def pointer(x,p):
 for k in p.strip('/').split('/') if p else []:
  k=k.replace('~1','/').replace('~0','~');x=x[int(k)] if isinstance(x,list) else x[k]
 return x

def ms(frame,fps):
 x=Fraction(str(frame))*1000/Fraction(str(fps));return (2*x.numerator+x.denominator)//(2*x.denominator)
def bounds(ir):
 fps=ir.get('delivery',ir.get('format',{})).get('fps',1)
 result={};cursor=0
 for s in ir['shots']:
  start=s.get('start_ms',ms(s.get('start_frame',cursor),fps));end=s.get('end_ms',ms(s.get('end_frame',cursor+s.get('frames',0)),fps))
  result[s['id']]=(start,end);cursor+=s.get('frames',0)
 return result
def overlap(a,b):return max(a[0],b[0])<min(a[1],b[1])
def content_hash(ir):
 d=deepcopy(ir);d['timeline'].pop('semantic_review',None)
 # Source-preserving relocation changes file paths, not reviewed creative content.
 for source in d.get('sources',[]):
  if source.get('sha256') or source.get('file_sha256'):source.pop('uri',None)
 for asset in d.get('assets',[]):
  if asset.get('sha256'):asset.pop('path',None);asset.pop('public_url',None)
 for upstream in d.get('upstreams',[]):
  if upstream.get('sha256'):upstream.pop('uri',None);upstream.pop('path',None)
 return digest(d)
def temporal_hash(ir):
 d=deepcopy(ir['timeline']);d.pop('semantic_review',None);return digest(d)
def semantic_status(ir):
 r=ir['timeline']['semantic_review']
 return r['status']=='PASS' and r['input_sha256']==content_hash(ir) and bool(r['reviewer'] and r['findings'])

def validate(ir,root,kind,base=None):
 schema=json.loads((Path(root)/'schemas'/f'{kind}-1.1.schema.json').read_text())
 from referencing import Registry, Resource
 resources=[]
 for p in (Path(root)/'schemas').glob('*.json'):
  value=json.loads(p.read_text())
  if '$id' in value:resources.append((value['$id'], Resource.from_contents(value)))
 validator=Draft202012Validator(schema,registry=Registry().with_resources(resources))
 errors=[issue('E_SCHEMA','/'+ '/'.join(map(str,e.absolute_path)),e.message) for e in validator.iter_errors(ir)]
 if errors:return errors
 def err(code,path,msg):errors.append(issue(code,path,msg))
 t=ir['timeline'];shots=bounds(ir);entities={e['id'] for e in ir['entities']};sources={s['id']:s for s in ir['sources']}
 scenes={s['id'] for s in ir['scenes']};allids={};actions={a['id']:a for a in t['actions']}
 groups={g['id']:g for g in t['action_groups']};beats={b['id'] for b in ir.get('beats',[])}
 for collection in ('sources','entities','scenes','shots','assets','bindings'):
  rows=ir.get(collection,[])
  if len({x['id'] for x in rows})!=len(rows):err('E_DUPLICATE_ID','/'+collection,'ID重复')
 cursor=0
 for s in ir['shots']:
  start,end=shots[s['id']]
  if start!=cursor or end<=start:err('E_TIMELINE','/shots/'+s['id'],'镜头需连续覆盖项目时轴')
  if s['scene_id'] not in scenes:err('E_SCENE','/shots/'+s['id'],'未知场景')
  cursor=end
 expected=ir.get('output',{}).get('duration_ms')
 if expected is None:
  f=ir.get('delivery',ir.get('format',{}));expected=ms(f['total_frames'],f['fps'])
 if cursor!=expected:err('E_DURATION','/shots','镜头总时长不匹配')
 def origin(value,path):
  if isinstance(value,dict):
   for ref in value.get('source_refs',[]):
    if ref not in sources:err('E_SOURCE',path,'未知来源 '+ref)
   for k,v in value.items():origin(v,path+'/'+k)
  elif isinstance(value,list):
   for i,v in enumerate(value):origin(v,path+'/'+str(i))
 origin(ir,'')
 for sid,s in sources.items():
  uri=s.get('uri','');h=s.get('file_sha256',s.get('sha256'))
  if h and '://' not in uri and base is not None:
   p=Path(base)/uri
   if not p.is_file() or sha256(p.read_bytes()).hexdigest()!=h:err('E_SOURCE_HASH','/sources/'+sid,'源文件缺失或哈希变化')
 for asset in ir.get('assets',[]):
  path=asset.get('path');checksum=asset.get('sha256')
  if path and checksum and base is not None:
   file=Path(base)/path
   if not file.is_file() or sha256(file.read_bytes()).hexdigest()!=checksum:err('E_ASSET_HASH','/assets/'+asset['id'],'素材缺失或字节哈希变化')
 for col in ('action_groups',*COLLECTIONS,'state_samples','segments'):
  for i,x in enumerate(t[col]):
   path=f'/timeline/{col}/{i}'
   if x['id'] in allids:err('E_DUPLICATE_ID',path,'时间对象ID重复')
   allids[x['id']]=path
   if col in COLLECTIONS or col=='segments':
    start,end=x['start_ms'],x['end_ms']
    if not 0<=start<end<=cursor:err('E_TIME',path,'事件时段越界或为空')
    actual=[sid for sid,b in shots.items() if overlap((start,end),b)]
    if x['shot_ids']!=actual:err('E_SHOT_SCOPE',path,'shot_ids必须对应实际覆盖镜头并按时序排列')
   if 'actor_id' in x and x['actor_id'] not in entities:err('E_ENTITY',path,'执行者不存在')
   if x.get('target_id') and x['target_id'] not in entities:err('E_ENTITY',path,'目标不存在')
   if col=='action_groups' and beats and not set(x['beat_ids'])<=beats:err('E_BEAT',path,'未知节拍')
 for x in [*groups.values(),*actions.values()]:
  seen={x['id']};parent=x['parent_id']
  while parent:
   node=groups.get(parent) or actions.get(parent)
   if not node or parent in seen:err('E_ACTION_TREE','/timeline','动作层级悬空或成环');break
   seen.add(parent);parent=node['parent_id']
 children={a['parent_id'] for a in actions.values()}
 for a in actions.values():
  path=allids[a['id']]
  if a['id'] in children and a['changes']:err('E_PARENT_EXECUTION',path,'父级动作不能重复写入叶级状态')
  parent=actions.get(a['parent_id'])
  if parent and not parent['start_ms']<=a['start_ms']<a['end_ms']<=parent['end_ms']:err('E_PARENT_TIME',path,'子动作超出父动作时段')
  for marker in a['markers']:
   if not a['start_ms']<=marker['at_ms']<=a['end_ms']:err('E_MARKER',path,'标记点越界')
  if len({m['id'] for m in a['markers']})!=len(a['markers']):err('E_MARKER',path,'标记点重复')
  for dep in a['depends_on']:
   other=actions.get(dep['action_id'])
   if not other or other['id']==a['id']:err('E_DEPENDENCY',path,'动作依赖悬空或自引用');continue
   r=dep['relation'];off=dep['offset_ms'];anchor=None
   if r=='after_end':anchor=other['end_ms']
   elif r=='after_start':anchor=other['start_ms']
   elif r=='at_marker':anchor=next((m['at_ms'] for m in other['markers'] if m['id']==dep['marker']),None)
   if r=='overlaps':valid=overlap((a['start_ms'],a['end_ms']),(other['start_ms'],other['end_ms']))
   else:valid=anchor is not None and (a['start_ms']==anchor+off if r=='at_marker' else a['start_ms']>=anchor+off)
   if not valid:err('E_DEPENDENCY_TIME',path,'时序依赖不成立')
 # Causal edges must be acyclic; overlap relations are symmetric, not causal edges.
 def visit(aid,stack,done):
  if aid in stack:err('E_DEPENDENCY_CYCLE',allids[aid],'因果依赖成环');return
  if aid in done:return
  for dep in actions[aid]['depends_on']:
   if dep['relation']!='overlaps' and dep['action_id'] in actions:visit(dep['action_id'],stack|{aid},done)
  done.add(aid)
 done=set()
 for aid in actions:visit(aid,set(),done)
 # Explicit state samples are key poses, not inferred interpolation.
 samplemap={}
 for sample in t['state_samples']:
  sid=sample['shot_id'];path=allids[sample['id']]
  if sid not in shots or not shots[sid][0]<=sample['at_ms']<=shots[sid][1]:err('E_STATE_TIME',path,'状态样本越界');continue
  if (sid,sample['at_ms']) in samplemap:err('E_STATE_DUPLICATE',path,'同镜同刻只能有一个状态样本')
  samplemap[sid,sample['at_ms']]=sample
  if not set(sample['entities'])<=entities:err('E_STATE_ENTITY',path,'样本包含未知实体')
 for sid,(start,end) in shots.items():
  if (sid,start) not in samplemap or (sid,end) not in samplemap:err('E_BOUNDARY_STATE','/timeline/state_samples','缺少 '+sid+' 起止状态');continue
  state=deepcopy(samplemap[sid,start]['entities']);writes=[]
  for a in actions.values():
   for j,c in enumerate(a['changes']):
    definition=schema['properties']['timeline']['properties']['state_samples']['items']['properties']['entities']['additionalProperties']['properties'][c['field']]
    if any(Draft202012Validator(definition).iter_errors(c['before'])) or any(Draft202012Validator(definition).iter_errors(c['after'])):err('E_STATE_TYPE',allids[a['id']],'状态变化值类型不符合字段')
    if not a['start_ms']<=c['at_ms']<=a['end_ms']:err('E_CHANGE_TIME',allids[a['id']],'状态变化不在动作内')
    if sid in a['shot_ids'] and start<c['at_ms']<=end:writes.append((c['at_ms'],a['id'],j,c))
  occupied={}
  for at,aid,j,c in sorted(writes):
   k=(c['entity_id'],c['field']);a=actions[aid];path=allids[aid]+f'/changes/{j}'
   prev=occupied.get(k)
   if prev and prev[3]!=aid and max(prev[0],a['start_ms'])<min(prev[1],a['end_ms']):err('E_STATE_CONFLICT',path,'并行动作竞争同一状态字段')
   if prev and prev[2]==at:err('E_STATE_CONFLICT',path,'同刻对同一状态多次写入，不能靠数组顺序确定')
   occupied[k]=(a['start_ms'],a['end_ms'],at,aid)
   if c['entity_id'] not in state or state[c['entity_id']].get(c['field'])!=c['before']:err('E_STATE_BEFORE',path,'前置状态不成立')
   else:state[c['entity_id']][c['field']]=deepcopy(c['after'])
  if state!=samplemap[sid,end]['entities']:err('E_STATE_REPLAY','/timeline/state_samples','逐动作终态与 '+sid+' 镜尾不同')
  # Intermediate samples must reflect all discrete changes completed at that time.
  for (ss,at),sample in samplemap.items():
   if ss!=sid or at in (start,end):continue
   mid=deepcopy(samplemap[sid,start]['entities'])
   for tm,aid,j,c in sorted(writes):
    if tm<=at and c['entity_id'] in mid:mid[c['entity_id']][c['field']]=deepcopy(c['after'])
   if mid!=sample['entities']:err('E_STATE_SAMPLE','/timeline/state_samples','中间关键状态未由动作变化说明')
  for eid,st in state.items():
   if not set(st['controllers'])<=set(st['contacts']):err('E_CONTROL_CONTACT','/timeline/state_samples','控制部位必须已接触')
 # Legacy boundary views cannot contradict the authoritative temporal key poses.
 for shot in ir['shots']:
  sid=shot['id']
  for edge,at in zip(('start','end'),shots[sid]):
   sample=samplemap.get((sid,at))
   if not sample:continue
   raw=shot.get('state_'+edge,shot.get(edge+'_state',{}))
   rows=raw.items() if isinstance(raw,dict) else ((v['entity_id'],v) for v in raw)
   for eid,old in rows:
    current=sample['entities'].get(eid)
    if not current:err('E_BOUNDARY_VIEW','/shots/'+sid,'兼容边界实体缺少新版关键状态');continue
    position=old.get('position_m',old.get('position'))
    if kind=='director-ir' and position is not None:position=[position[0],position[2],position[1]]
    if position!=current['position']:err('E_BOUNDARY_VIEW','/shots/'+sid,'兼容边界位置与时间轨冲突：'+eid)
    pose=old['pose']
    if kind=='avir':pose=pose.split('；状态=',1)[0]
    if pose!=current['pose']:err('E_BOUNDARY_VIEW','/shots/'+sid,'兼容边界姿态与时间轨冲突：'+eid)
 previous=None
 for shot in ir['shots']:
  sid=shot['id'];start,end=shots[sid]
  transition=shot.get('transition',{})
  typ=transition.get('type') if isinstance(transition,dict) else transition
  if previous and previous['scene_id']==shot['scene_id'] and typ not in ('time_jump','subjective'):
   old=samplemap.get((previous['id'],shots[previous['id']][1]));new=samplemap.get((sid,start))
   if old and new:
    for eid in set(old['entities']) & set(new['entities']):
     a={k:v for k,v in old['entities'][eid].items() if k!='visible_parts'};b={k:v for k,v in new['entities'][eid].items() if k!='visible_parts'}
     if a!=b:err('E_CONTINUITY','/timeline/state_samples',eid+'跨镜物理状态不连续')
  previous=shot
 def visible(actor,start,end,parts,readability):
  intervals=sorted((v['start_ms'],v['end_ms']) for v in t['visibility'] if v['entity_id']==actor and set(parts)<=set(v['parts']) and (readability=='body' or v['readability'] in ('face','detail')))
  cursor=start
  for a,b in intervals:
   if a<=cursor<b:cursor=b
  return cursor>=end
 for v in t['visibility']:
  if v['shot_id'] not in shots or v['entity_id'] not in entities or not shots[v['shot_id']][0]<=v['start_ms']<v['end_ms']<=shots[v['shot_id']][1]:err('E_VISIBILITY','/timeline/visibility','可见性区间或实体无效')
 for p in t['performances']:
  if not set(p['action_ids'])<=set(actions):err('E_PERFORMANCE_ACTION',allids[p['id']],'表演动作引用不存在')
  if not visible(p['actor_id'],p['start_ms'],p['end_ms'],p['needed_parts'],p['readability']):err('E_DYNAMIC_VISIBILITY',allids[p['id']],'表演发生区间所需部位不可见或景别不可读')
  psy=p['psychology']
  if psy and psy['audibility']=='silent' and psy['utterance_id']:err('E_SILENT_VOICE',allids[p['id']],'静默心理不能绑定声音')
  if psy and psy['audibility']=='internal_voice' and not any(u['id']==psy['utterance_id'] and u['kind']=='internal_voice' and u['speaker_id']==p['actor_id'] for u in t['audio_events']):err('E_INNER_VOICE',allids[p['id']],'内心独白缺少对应原文')
 for i,c in enumerate(t['camera_operations']):
  if c['operation']=='unknown':errors.append(issue('B_CAMERA_UNKNOWN',allids[c['id']],'运镜类型需 Agent 对照原件确认','blocker'))
  if c['operation']=='locked' and (c['start_position']!=c['end_position'] or c['start_framing']!=c['end_framing']):err('E_CAMERA_LOCKED',allids[c['id']],'固定机位的起止机位与构图矛盾')
  for other in t['camera_operations'][i+1:]:
   if overlap((c['start_ms'],c['end_ms']),(other['start_ms'],other['end_ms'])) and (c['operation']==other['operation'] or ('locked' in (c['operation'],other['operation']) and not {'rack_focus','zoom'} & {c['operation'],other['operation']})):err('E_CAMERA_CONFLICT',allids[c['id']],'同时存在互斥摄影机操作')
  if not set(c['sync_action_ids'])<=set(actions):err('E_CAMERA_ACTION',allids[c['id']],'摄影机同步动作不存在')
  if c['precision']!='intent':errors.append(issue('B_CAMERA_EVIDENCE',allids[c['id']],'精确摄影控制需对应参考或受控执行证据','blocker'))
 for sid,b in shots.items():
  intervals=sorted((max(c['start_ms'],b[0]),min(c['end_ms'],b[1])) for c in t['camera_operations'] if sid in c['shot_ids'])
  cur=b[0]
  for a,z in intervals:
   if a>cur:err('E_CAMERA_GAP','/timeline/camera_operations','摄影机操作有未说明时段')
   cur=max(cur,z)
  if cur<b[1]:err('E_CAMERA_GAP','/timeline/camera_operations','摄影机未覆盖镜头')
 source_lines={u['id']:u for source in ir['sources'] for u in source.get('utterances',[])}
 spoken=[]
 for a in t['audio_events']:
  path=allids[a['id']]
  if a['speaker_id'] and a['speaker_id'] not in entities:err('E_SPEAKER',path,'发声实体不存在')
  if a['lip_sync'] and (a['kind']!='dialogue' or a['placement']!='on_screen'):err('E_LIP_ROLE',path,'只有画内对白可要求口型')
  if a['lip_sync'] and not visible(a['speaker_id'],a['start_ms'],a['end_ms'],['mouth'],'body'):err('E_LIP_VISIBILITY',path,'口型时段嘴部不可见')
  if a['source_utterance_id']:
   spoken.append(a['source_utterance_id']);u=source_lines.get(a['source_utterance_id'])
   if source_lines and (not u or any(a[k]!=u[k] for k in ('text','speaker_id','kind'))):err('E_DIALOGUE_FIDELITY',path,'原文、说话人或声音类别变化')
  for phrase in a['phrases']:
   if not a['start_ms']<=phrase['start_ms']<phrase['end_ms']<=a['end_ms']:err('E_PHRASE_TIME',path,'短语时段越界')
  if a['phrases'] and ''.join(p['text'] for p in a['phrases'])!=a['text']:err('E_PHRASE_TEXT',path,'分句必须原样拼回原文')
  sync=a['sync']
  if sync:
   act=actions.get(sync['action_id']);anchor=None
   if act:anchor=act['start_ms'] if sync['anchor']=='start' else act['end_ms'] if sync['anchor']=='end' else next((m['at_ms'] for m in act['markers'] if m['id']==sync['marker_id']),None)
   if anchor is None or not a['start_ms']<=anchor+sync['offset_ms']<=a['end_ms']:err('E_AUDIO_ANCHOR',path,'同步锚点不存在或不在声音区间')
 for uid in set(spoken):
  if spoken.count(uid)>1:err('E_DIALOGUE_DUPLICATE','/timeline/audio_events','同一原文被重复表达')
 excluded={x['id'] for x in ir.get('scope',{}).get('excluded_utterance_ids',[])}
 for uid in source_lines:
  if uid not in excluded and uid not in spoken:err('E_DIALOGUE_MISSING','/timeline/audio_events','遗漏原文 '+uid)
 for i,a in enumerate(t['audio_events']):
  if a['kind']!='dialogue':continue
  for b in t['audio_events'][i+1:]:
   if b['kind']=='dialogue' and overlap((a['start_ms'],a['end_ms']),(b['start_ms'],b['end_ms'])) and not(a['overlap_reason'] or b['overlap_reason']):err('E_AUDIO_OVERLAP',allids[b['id']],'重叠对白缺少依据')
 for e in t['extensions']:
  if not e['supported'] and e['channel']!='review':err('E_EXTENSION_UNSUPPORTED','/timeline/extensions','扩展缺少明确执行支持：'+e['name'])
 for mapping in t['source_time_maps']:
  if mapping['source_id'] not in sources or mapping['source_end_ms']<=mapping['source_start_ms'] or not 0<=mapping['project_start_ms']<mapping['project_end_ms']<=cursor:
   err('E_SOURCE_TIME_MAP','/timeline/source_time_maps','来源时间或项目映射无效')
 for a in t['actions']:
  for field in ('effector','path','speed','support','contact'):
   if a[field]['status']=='unknown':errors.append(issue('B_DETAIL_UNKNOWN',allids[a['id']]+'/'+field,'执行细节尚待补齐','blocker'))
 # Native contracts keep their original fields and assertions.
 clauses=ir.get('contract',[])
 if isinstance(clauses,dict):clauses=clauses.get('clauses',[])
 for c in clauses:
  for path in c.get('paths',[]):
   try:
    if pointer(ir,path) in (None,[]):err('E_CONTRACT_PATH',path,'合同指向空的旧字段，必须显式重映射')
   except (KeyError,IndexError,TypeError):err('E_CONTRACT_PATH',path,'合同路径不存在')
  for check in c.get('checks',[]):
   if not isinstance(check,dict):continue
   try:
    val=pointer(ir,check['path']);ok=check['op']=='exists' or check['op']=='equals' and val==check['value'] or check['op']=='contains' and check['value'] in val
   except (KeyError,IndexError,ValueError,TypeError):ok=False
   if not ok:err('E_CONTRACT',check['path'],'原生合同断言失败')
 return errors


def leaves(value,path=''):
 if isinstance(value,dict):
  for k,v in value.items():yield from leaves(v,path+'/'+k.replace('~','~0').replace('/','~1'))
 elif isinstance(value,list):
  if not value:yield path,[]
  for i,v in enumerate(value):yield from leaves(v,path+'/'+str(i))
 else:yield path,value

LABELS={'effector':'执行部位','operation':'动作','trigger':'触发','path':'路径','speed':'速度与节奏','support':'支撑与重心','contact':'接触','feedback':'反馈','settle':'收束','face':'面部','eyes':'视线','hands':'手部','body':'身体','breathing':'呼吸','voice':'发声表现','behavior':'表演作用（依附动作，不重复执行）','start_position':'起始机位','end_position':'结束机位','start_framing':'起始构图','end_framing':'结束构图','height':'机位高度','orientation':'摄影朝向','look_at':'观察目标','focus':'焦点','axis':'轴线','text':'内容','delivery':'发声节奏','mix':'声音层次','placement':'声音归属','lip_sync':'口型','route':'执行渠道','depends_on':'时序关系','changes':'状态变化','markers':'关键时点','sync':'同步点','phrases':'分句节奏','purpose':'目的与保持条件','entities':'人物与物件状态','visible_translation':'可见心理表现','action_ids':'关联动作','sync_action_ids':'同步动作','position':'世界位置（右、上、深，米）','pose':'姿态','body_facing':'身体朝向','head_facing':'头部朝向','gaze':'视线目标','contacts':'接触部位','supports':'支撑','controllers':'控制部位','visible_parts':'可见部位','condition':'状态','framing':'构图原则','layers':'前中后景','screen_positions':'画面位置','required_visible':'必须可见','rule':'构图原则','attention_order':'注意顺序','negative_space':'留白','safe_area':'安全区域','depth_layers':'前中后景','subjects':'主体布局','entity_id':'主体','box':'归一化画面区域（左、上、宽、高）','screen_side':'画面侧别','depth_rank':'景深层次','orientation':'朝向','parts':'部位','instruction':'指令','readability':'可读尺度','reason':'说明','shot_id':'所属镜头'}
WORDS={'not_applicable':'不适用','not_visible':'画外约束','unknown':'待明确','locked':'固定机位','dolly_in':'摄影机推近','dolly_out':'摄影机拉远','truck':'横向移机','pan':'水平摇摄','tilt':'上下摇摄','pedestal':'升降机位','orbit':'环绕移动','tracking':'跟随移动','handheld':'手持移动','zoom':'变焦','rack_focus':'转移焦点','on_screen':'画内','off_screen':'画外','voice_over':'旁白/内心声轨','environment':'环境','native':'模型音频','post':'后期声音','dialogue':'对白','narration':'旁白','internal_voice':'内心独白','sfx':'动作音效','ambience':'环境声','music':'音乐','silence':'静默','right_hand':'右手','left_hand':'左手','face':'面部','eyes':'眼睛','hands':'手部','mouth':'嘴部','body':'身体','detail':'细部','left':'左侧','right':'右侧','center':'中央'}
LABELS.update({'target_id':'作用对象','color':'光色','position_m':'世界位置（右、上、深，米）','quality':'光质','world_source':'世界光源','depth':'景深层次','occlusion':'遮挡','subject':'主体','object':'对象','relation':'空间关系','description':'具体说明','kind':'声音类型','field':'状态字段','before':'变化前','after':'变化后','head_yaw_deg':'头部水平朝向角','head_pitch_deg':'头部俯仰角','yaw_deg':'身体水平朝向角','gaze_target':'视线目标','holder':'持有部位','payload':'执行细节'})
WORDS.update({'foreground':'前景','midground':'中景','background':'后景','world_left_of':'位于世界坐标左侧','cut':'切镜','dissolve':'叠化','time_jump':'时间跳跃','none':'无','head':'头部'})
def readable(x):
 if isinstance(x,dict) and 'status' in x and 'text' in x:
  return readable(x['text']) if x['status']=='specified' else WORDS.get(x['status'],x['status'])+'：'+x['text']
 if isinstance(x,str):
  if x.startswith(('{','[')):
   try:return readable(json.loads(x))
   except (ValueError,TypeError):pass
  return WORDS.get(x,x).replace('.right_hand','的右手').replace('.left_hand','的左手').replace('.top','的上表面').replace('yaw=','水平朝向角=').replace('pitch=','俯仰角=')
 if x is None:return '无'
 if isinstance(x,bool):return '需要' if x else '不需要'
 if isinstance(x,list):return '、'.join(readable(v) for v in x) or '无'
 if isinstance(x,dict):return '；'.join(LABELS.get(k,k)+'：'+readable(v) for k,v in x.items())
 return str(x)


def render(ir,start_ms=0,end_ms=None):
 """Each operation has its own block; execution fields get deterministic wording."""
 t=ir['timeline'];end_ms=end_ms if end_ms is not None else max(b[1] for b in bounds(ir).values())
 names={e['id']:e.get('name',e.get('label',e['id'])) for e in ir['entities']};blocks=[];coverage=[]
 children={x['parent_id'] for x in t['actions']}
 def sec(at):return f'{(at-start_ms)/1000:g}秒'
 def field_text(field,value):
  if field=='changes':return '\n'.join(f"{sec(c['at_ms'])}，{names.get(c['entity_id'],c['entity_id'])}的{LABELS.get(c['field'],c['field'])}从“{readable(c['before'])}”变为“{readable(c['after'])}”。" for c in value)
  if field=='depends_on':return '；'.join(d['action_id']+{'after_end':'完成后开始','after_start':'开始后执行','overlaps':'同时发生','at_marker':'到达标记 '+str(d['marker'])+' 时开始'}[d['relation']]+(f"；偏移{d['offset_ms']/1000:g}秒" if d['offset_ms'] else '') for d in value)
  if field=='markers':return '；'.join(sec(m['at_ms'])+'：'+m['meaning'] for m in value)
  if field=='sync':return value['action_id']+' 的 '+({'start':'开始','end':'结束','marker':'标记 '+str(value['marker_id'])}[value['anchor']])+f"，偏移{value['offset_ms']/1000:g}秒"
  if field=='phrases':return '\n'.join(sec(p['start_ms'])+'–'+sec(p['end_ms'])+'：“'+p['text']+'”；'+p['delivery'] for p in value)
  if field=='target_id':return names.get(value,value)
  if field=='entities':return '\n'.join(names.get(eid,eid)+'：'+readable(st) for eid,st in value.items())
  return readable(value)
 def block(title,node,path,fields,channel='prompt'):
  lines=[title];emitted=[]
  for field in fields:
   if field not in node or node[field] is None or node[field]==[]:continue
   value=node[field]
   if isinstance(value,dict) and value.get('status')=='not_applicable':continue
   lines.append(LABELS.get(field,field)+'：'+field_text(field,value));emitted.append(field)
  text='\n'.join(lines);idx=len(blocks);blocks.append({'text':text,'channel':channel,'id':node.get('id'),'path':path})
  for p,v in leaves(node,path):
   field=p[len(path)+1:].split('/')[0]
   emitted_here=field in emitted or field in ('id','start_ms','end_ms','actor_id','speaker_id') or (field=='text' and 'audio_events' in path)
   coverage.append({'source_path':p,'source_sha256':digest(v),'object_id':node.get('id'),'disposition':'emitted' if emitted_here else 'retained','channel':channel if emitted_here else 'review','block':idx if emitted_here else None,'text_sha256':digest(text) if emitted_here else None,'reason':'执行字段进入对应条目' if emitted_here else '不适用项、来源与结构关联完整保留在制作包，不作为额外行为'})
 active_parents={a['parent_id'] for a in t['actions'] if overlap((a['start_ms'],a['end_ms']),(start_ms,end_ms))}
 for _ in range(len(t['action_groups'])+len(t['actions'])):
  active_parents.update(x['parent_id'] for x in [*t['action_groups'],*t['actions']] if x['id'] in active_parents)
 for i,g in enumerate(t['action_groups']):
  if g['id'] in active_parents:block('【动作组目的与保持条件；按子动作执行】',g,f'/timeline/action_groups/{i}',('purpose',))
 for col in COLLECTIONS:
  label={'actions':'动作','performances':'表演','camera_operations':'摄影机操作','audio_events':'对白与声音'}[col]
  for i,x in enumerate(t[col]):
   if not overlap((x['start_ms'],x['end_ms']),(start_ms,end_ms)):continue
   path=f'/timeline/{col}/{i}'
   if col=='actions' and x['id'] in children:
    block('【父动作目的；不另执行一遍】',x,path,('operation','trigger','effector','path','speed','support','contact','feedback','settle','depends_on','markers'))
    continue
   a=max(x['start_ms'],start_ms)-start_ms;b=min(x['end_ms'],end_ms)-start_ms
   actor=names.get(x.get('actor_id',x.get('speaker_id')), '')
   title=f"【{label} {x['id']}｜{a/1000:g}–{b/1000:g}秒】"+(actor and '\n主体：'+actor)
   if col=='actions':fields=('target_id','trigger','effector','operation','path','speed','support','contact','feedback','settle','depends_on','markers','changes')
   elif col=='performances':fields=('action_ids','trigger','behavior','face','eyes','hands','body','breathing','voice','feedback','settle')
   elif col=='camera_operations':fields=('operation','start_position','end_position','start_framing','end_framing','height','orientation','path','speed','look_at','focus','axis','sync_action_ids')
   else:fields=('kind','placement','lip_sync','delivery','mix','sync','phrases','overlap_reason','route')
   if col=='audio_events' and x['kind'] not in ('dialogue','narration','internal_voice'):fields=('text',)+fields
   channel=x.get('route','prompt');channel='prompt' if channel=='native' else channel
   if col=='audio_events' and x['kind'] in ('dialogue','narration','internal_voice'):title+='\n'+actor+'：“'+x['text']+'”'
   block(title,x,path,fields,channel)
   if col=='performances' and x['psychology']:
    psy=x['psychology'];block('【可见心理表现】',psy,path+'/psychology',('visible_translation',))
 for i,sample in enumerate(t['state_samples']):
  if start_ms<=sample['at_ms']<=end_ms:
   block(f"【状态 {sample['id']}｜{sec(sample['at_ms'])}】",sample,f'/timeline/state_samples/{i}',('entities',))
 for i,v in enumerate(t['visibility']):
  if overlap((v['start_ms'],v['end_ms']),(start_ms,end_ms)):block('【表演可见范围｜'+sec(max(v['start_ms'],start_ms))+'–'+sec(min(v['end_ms'],end_ms))+'】',v,f'/timeline/visibility/{i}',('entity_id','parts','readability','reason'))
 for i,e in enumerate(t['extensions']):block('【扩展要求】',e,f'/timeline/extensions/{i}',('instruction','payload'),'prompt' if e['channel']=='prompt' else e['channel'])
 covered={r['source_path'] for r in coverage}
 for path,value in leaves(t,'/timeline'):
  if path not in covered:coverage.append({'source_path':path,'source_sha256':digest(value),'object_id':None,'disposition':'retained','channel':'review','block':None,'text_sha256':None,'reason':'非当前执行条目的来源映射、拆段方案或复核记录保留在制作包'})
 return blocks,coverage


def verify_coverage(ir,blocks,coverage):
 errors=[]
 for row in coverage:
  try:
   if digest(pointer(ir,row['source_path']))!=row['source_sha256']:raise ValueError('source changed')
   if row['disposition']=='emitted' and digest(blocks[row['block']]['text'])!=row['text_sha256']:raise ValueError('text changed')
  except (KeyError,IndexError,TypeError,ValueError):errors.append(issue('E_DETAIL_COVERAGE',row['source_path'],'字段或执行正文变化，需重新编译与审查'))
 expected={p for p,v in (leaves(ir) if any(not r['source_path'].startswith('/timeline') for r in coverage) else leaves(ir['timeline'],'/timeline'))}
 covered={r['source_path'] for r in coverage}
 for p in sorted(expected-covered):errors.append(issue('E_DETAIL_MISSING',p,'细节没有覆盖记录'))
 return errors


def panel_state(ir,shot_id,at_ms):
 t=ir['timeline'];samples=[s for s in t['state_samples'] if s['shot_id']==shot_id and s['at_ms']==at_ms]
 active=lambda col:[deepcopy(x) for x in t[col] if shot_id in x['shot_ids'] and x['start_ms']<=at_ms<x['end_ms']]
 return {'at_ms':at_ms,'state':deepcopy(samples[0]['entities']) if samples else None,
         'status':'EXPLICIT' if samples else 'NEEDS_KEY_POSE','interpolated':False,
         'performance':active('performances'),'camera':active('camera_operations'),'actions':active('actions')}


def affected_shots(ir,shot_id):
 t=ir['timeline'];selected={shot_id};changed=True
 while changed:
  changed=False;action_ids={a['id'] for a in t['actions'] if selected.intersection(a['shot_ids'])}
  for col in COLLECTIONS:
   for x in t[col]:
    refs=set(x.get('action_ids',x.get('sync_action_ids',[])))|{d['action_id'] for d in x.get('depends_on',[])}
    if x.get('sync'):refs.add(x['sync']['action_id'])
    if (col=='actions' and selected.intersection(x['shot_ids'])) or refs&action_ids:
     old=len(selected);selected.update(x['shot_ids']);changed|=old!=len(selected)
 return [s['id'] for s in ir['shots'] if s['id'] in selected]


def segment_plan(ir):
 """Lower only explicit accepted intervals; never invent a mid-action phase."""
 results=[]
 for segment in ir['timeline']['segments']:
  if segment['status']!='accepted':continue
  start,end=segment['start_ms'],segment['end_ms'];reasons=[]
  for boundary in (start,end):
   if not any(s['at_ms']==boundary for s in ir['timeline']['state_samples']):reasons.append('NEEDS_KEY_POSE:'+str(boundary))
  for col in ('actions','camera_operations','audio_events'):
   for x in ir['timeline'][col]:
    if not overlap((start,end),(x['start_ms'],x['end_ms'])):continue
    crosses=x['start_ms']<start or x['end_ms']>end
    if not crosses:continue
    if col=='camera_operations' and x['operation']=='locked':continue
    if col=='audio_events' and x['route']=='post':continue
    reasons.append('NEEDS_EXPLICIT_PHASE_SLICE:'+x['id'])
  blocks,coverage=render(ir,start,end)
  # Post soundtrack remains a single project track, not regenerated per clip.
  text='\n\n'.join(b['text'] for b in blocks if b['channel']=='prompt')
  results.append({'id':segment['id'],'status':'BLOCKED' if reasons else 'DRAFT_REQUIRES_TARGET_CHECK',
    'project_start_ms':start,'project_end_ms':end,'time_origin_ms':start,'prompt':text,
    'continuity':deepcopy(segment),'reasons':reasons,'detail_coverage':coverage,
    'soundtrack':'Use original project sound track once; do not regenerate crossing post audio.',
    'execution':'NOT_RUN','seamless_media':'NOT_VERIFIED'})
 return results


def changed_shots(before,after):
 """Temporal edits must obey the same task scope as native shot edits."""
 changed=set()
 for col in (*COLLECTIONS,'state_samples','visibility','segments','action_groups'):
  def keyed(ir):
   return {x.get('id',str(i)):x for i,x in enumerate(ir.get('timeline',{}).get(col,[]))}
  old,new=keyed(before),keyed(after)
  for key in old.keys()|new.keys():
   if old.get(key)==new.get(key):continue
   for value,ir in ((old.get(key),before),(new.get(key),after)):
    if value is None:continue
    changed.update(value.get('shot_ids',[]))
    if value.get('shot_id'):changed.add(value['shot_id'])
    if col=='action_groups':
     parents={value['id']}
     for _ in range(len(ir['timeline']['actions'])+len(ir['timeline']['action_groups'])):
      parents.update(x['id'] for x in [*ir['timeline']['actions'],*ir['timeline']['action_groups']] if x['parent_id'] in parents)
     changed.update(s for a in ir['timeline']['actions'] if a['id'] in parents for s in a['shot_ids'])
 for field in ('extensions','coordinate_system'):
  if before.get('timeline',{}).get(field)!=after.get('timeline',{}).get(field):changed.update(s['id'] for s in after['shots'])
 return sorted(changed)
