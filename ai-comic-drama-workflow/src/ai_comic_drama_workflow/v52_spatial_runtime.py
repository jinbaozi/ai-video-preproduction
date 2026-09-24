"""Spatial 1.2 semantics; planned geometry is distinct from observed media."""
from copy import deepcopy
from pathlib import Path
import importlib.util,json,math
from jsonschema import Draft202012Validator
_path=Path(__file__).with_name('detail_runtime.py')
if not _path.exists():_path=Path(__file__).with_name('v51_detail_runtime.py')
_spec=importlib.util.spec_from_file_location('spatial_legacy_'+str(_path),_path);legacy=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(legacy)
VERSION='1.2.0';FIELDS=('spatial_nodes','motion_tracks','spatial_relations','composition_tracks');EPS=1e-6
encoded,digest,pointer,leaves,ms,bounds,overlap,issue,content_hash,semantic_status=(getattr(legacy,n) for n in ('encoded','digest','pointer','leaves','ms','bounds','overlap','issue','content_hash','semantic_status'))
STATE_FIELDS={'position':'position','orientation':'body_facing','gaze':'gaze'}
CAMERA_CHANNELS={'locked':{'position','orientation'},'dolly_in':{'position'},'dolly_out':{'position'},'truck':{'position'},'pedestal':{'position'},'orbit':{'position','orientation'},'tracking':{'position'},'handheld':{'position','orientation'},'pan':{'orientation'},'tilt':{'orientation'},'zoom':{'zoom'},'rack_focus':{'focus'},'unknown':set()}

def nodes(ir):return {n['id']:n for n in ir['timeline']['spatial_nodes']}
def scope_bounds(scope):return (scope['at_ms'],scope['at_ms']) if scope['kind']=='point' else (scope['start_ms'],scope['end_ms'])
def active(x,at,end=False):return x['start_ms']<=at<x['end_ms'] or (end and at==x['end_ms'])
def evaluate_track(track,at):
 keys=track['keyframes']
 for key in keys:
  if key['at_ms']==at:return {'status':'EXPLICIT','value':deepcopy(key['value']),'track_id':track['id'],'at_ms':at}
 for a,b in zip(keys,keys[1:]):
  if a['at_ms']<at<b['at_ms']:
   if a['transition']=='hold':return {'status':'DERIVED_HOLD','value':deepcopy(a['value']),'track_id':track['id'],'at_ms':at}
   if a['transition']=='linear' and a['value']['mode']==b['value']['mode']=='numeric':
    v,w=a['value']['value'],b['value']['value'];ratio=(at-a['at_ms'])/(b['at_ms']-a['at_ms'])
    if isinstance(v,list)!=isinstance(w,list):return {'status':'INVALID_VALUES','value':None,'track_id':track['id'],'at_ms':at}
    result=[x+(y-x)*ratio for x,y in zip(v,w)] if isinstance(v,list) and isinstance(w,list) else v+(w-v)*ratio
    value=deepcopy(a['value']);value['value']=result;value['description']='按已声明线性变化计算的计划值，不代表身体姿态或实际媒体测量'
    return {'status':'DERIVED_LINEAR','value':value,'track_id':track['id'],'at_ms':at}
 return {'status':'NEEDS_KEY_STATE','value':None,'track_id':track['id'],'at_ms':at}

def value_at(ir,node_id,prop,at):
 tracks=[t for t in ir['timeline']['motion_tracks'] if t['node_id']==node_id and t['property']==prop and active(t,at)]
 if not tracks:tracks=[t for t in ir['timeline']['motion_tracks'] if t['node_id']==node_id and t['property']==prop and t['end_ms']==at]
 return evaluate_track(tracks[0],at) if len(tracks)==1 else {'status':'CONFLICT' if tracks else 'UNDETERMINED','value':None}

def position_at(ir,node_id,at,frame='world'):
 n=nodes(ir)[node_id];value=value_at(ir,node_id,'position',at)
 if not value['value'] or value['value']['mode']!='numeric':return None
 p=value['value']['value']
 if frame not in ('world','screen'):return None
 if n['frame']['kind']=='world' and n['frame']['unit']!='m':return None
 if n['frame']['kind']=='screen' and n['frame']['unit']!='normalized':return None
 if not isinstance(p,list):return None
 if n['frame']['kind']==frame:return p
 if frame=='world' and n['frame']['kind'] in ('local','anatomical'):
  transform=next((x for x in n['frame']['transforms'] if x['at_ms']==at),None)
  if transform:
   return [transform['origin'][j]+sum(p[i]*transform['basis'][i][j] for i in range(3)) for j in range(3)]
 return None

def projection(ir):
 """Compatibility view solely for unchanged temporal checks; never exported as source."""
 out=deepcopy(ir);out['schema' if 'schema' in out else 'schema_version']={'avir/1.2':'avir/1.1','storyboard-ir/1.2':'storyboard-ir/1.1','1.2':'1.1'}[ir.get('schema',ir.get('schema_version'))]
 t=out['timeline'];t['schema']='detail-timeline/1.1'
 for name in FIELDS:t.pop(name)
 # Dynamic composition owns visibility; each interval is explicit, no geometric guess.
 t['visibility']=[]
 for c in ir['timeline']['composition_tracks']:
  for subject in c['subjects']:
   n=nodes(ir)[subject['node_id']]
   if not n['entity_id'] or subject['presence']=='outside':continue
   for sid in c['shot_ids']:
    start,end=bounds(ir)[sid];a=max(start,c['start_ms']);b=min(end,c['end_ms'])
    if a<b:t['visibility'].append({'shot_id':sid,'entity_id':n['entity_id'],'start_ms':a,'end_ms':b,'parts':subject['visible_parts'],'readability':subject['readability'],'reason':subject['occlusion']})
 # Position tracks are checked against actual snapshots separately; exclude their
 # derived fields from discrete legacy replay to avoid a second motion authority.
 owners={nodes(ir)[tr['node_id']]['entity_id'] for tr in ir['timeline']['motion_tracks'] if tr['property']=='position' and nodes(ir)[tr['node_id']]['kind']=='entity'}
 for sample in t['state_samples']:
  for eid in owners:
   if eid in sample['entities']:sample['entities'][eid]['position']=[0,0,0]
 for a in t['actions']:a['changes']=[c for c in a['changes'] if not(c['entity_id'] in owners and c['field']=='position')]
 for shot in out['shots']:
  for edge in ('start','end'):
   raw=shot.get('state_'+edge,shot.get(edge+'_state',{}));rows=raw.items() if isinstance(raw,dict) else ((x['entity_id'],x) for x in raw)
   for eid,st in rows:
    if eid in owners:st['position_m' if 'position_m' in st else 'position']=[0,0,0]
 return out

def geometry_checks(ir):
 results=[];ns=nodes(ir)
 for r in ir['timeline']['spatial_relations']:
  start,end=scope_bounds(r['scope']);times={start,end}
  for tr in ir['timeline']['motion_tracks']:
   if tr['node_id'] in (r['subject_node_id'],r['object_node_id']):times.update(k['at_ms'] for k in tr['keyframes'] if start<=k['at_ms']<=end)
  if r['predicate']=='far' and r['frame']=='world' and r['distance_m'] is not None:
   for lo,hi in zip(sorted(times),sorted(times)[1:]):
    left=[position_at(ir,n,lo) for n in (r['subject_node_id'],r['object_node_id'])];right=[position_at(ir,n,math.nextafter(hi,lo)) for n in (r['subject_node_id'],r['object_node_id'])]
    if all(x is not None for x in left+right):
     delta=[left[0][i]-left[1][i] for i in range(3)];change=[right[0][i]-right[1][i]-delta[i] for i in range(3)];den=sum(x*x for x in change)
     if den:
      fraction=max(0,min(1,-sum(a*b for a,b in zip(delta,change))/den));times.add(lo+(hi-lo)*fraction)
  checks=[];why=[]
  for at in sorted(times):
   if r['scope']['kind']=='interval' and at==end:at=math.nextafter(end,start)
   a=position_at(ir,r['subject_node_id'],at,r['frame']);b=position_at(ir,r['object_node_id'],at,r['frame']);p=r['predicate'];ok=None
   if a is not None and b is not None:
    if p in ('world_left_of','screen_left_of'):ok=a[0]<b[0]
    elif p in ('world_right_of','screen_right_of'):ok=a[0]>b[0]
    elif p=='above':ok=a[1]>b[1] if r['frame']!='screen' else a[1]<b[1]
    elif p=='below':ok=a[1]<b[1] if r['frame']!='screen' else a[1]>b[1]
    elif p=='world_in_front_of':ok=a[2]<b[2]
    elif p=='world_behind':ok=a[2]>b[2]
    elif p in ('near','far') and r['distance_m'] is not None:
     distance=math.dist(a,b);ok=distance<=r['distance_m'] if p=='near' else distance>=r['distance_m']
    elif p=='attached_to' and r['attachment'] and r['attachment']['relative_offset'] is not None:
     ok=all(abs((a[i]-b[i])-r['attachment']['relative_offset'][i])<=EPS for i in range(3))
    elif p=='contains' and ns[r['subject_node_id']]['bounds'] and ns[r['object_node_id']]['bounds']:
     x,y=ns[r['subject_node_id']]['bounds'],ns[r['object_node_id']]['bounds']
     # Bounds are world-aligned offsets; rotating/nonrigid bounds cannot be assumed.
     rotating=any(t['node_id'] in (r['subject_node_id'],r['object_node_id']) and t['property'] in ('rotation','orientation','deformation') and active(t,at) for t in ir['timeline']['motion_tracks'])
     if not rotating:ok=all(a[i]+x['min'][i]<=b[i]+y['min'][i] and b[i]+y['max'][i]<=a[i]+x['max'][i] for i in range(3))
   checks.append({'at_ms':at,'status':'UNDETERMINED' if ok is None else 'PASS' if ok else 'FAIL'})
  # Sampling proves checkpoints only, never entire nonlinear paths or occlusion.
  results.append({'id':r['id'],'status':'FAIL' if any(c['status']=='FAIL' for c in checks) else 'UNDETERMINED' if any(c['status']=='UNDETERMINED' for c in checks) else 'CHECKPOINTS_PASS','checks':checks,'continuous_geometry':'NOT_PROVEN','reason':'仅计算有明确坐标和阈值的关系；接触、朝向、遮挡等仍需语义或真实媒体复核'})
 return results

def validate(ir,root,kind,base=None):
 from referencing import Registry,Resource
 root=Path(root);schema=json.loads((root/'schemas'/f'{kind}-1.2.schema.json').read_text())
 registry=Registry().with_resources((d['$id'],Resource.from_contents(d)) for p in (root/'schemas').glob('*.json') if '$id' in (d:=json.loads(p.read_text())))
 errors=[issue('E_SCHEMA','/'+ '/'.join(map(str,e.absolute_path)),e.message) for e in Draft202012Validator(schema,registry=registry).iter_errors(ir)]
 if errors:return errors
 def err(code,path,msg,severity='error'):errors.append(issue(code,path,msg,severity))
 t=ir['timeline'];ns=nodes(ir);entities={e['id'] for e in ir['entities']};shots=bounds(ir);duration=max(b[1] for b in shots.values());sources={x['id'] for x in ir['sources']}
 if len(ns)!=len(t['spatial_nodes']):err('E_NODE_ID','/timeline/spatial_nodes','空间节点 ID 重复')
 ids=set()
 for col in FIELDS:
  for i,x in enumerate(t[col]):
   path=f'/timeline/{col}/{i}'
   if x['id'] in ids:err('E_SPATIAL_ID',path,'空间对象 ID 重复')
   ids.add(x['id'])
   if not set(x['origin']['source_refs'])<=sources:err('E_SOURCE',path,'来源不存在')
   if col!='spatial_nodes':
    a,b=scope_bounds(x['scope']) if col=='spatial_relations' else (x['start_ms'],x['end_ms'])
    if not 0<=a<=b<=duration or (a==b and (col!='spatial_relations' or x['scope']['kind']=='interval')):err('E_SPATIAL_TIME',path,'时间范围无效')
    expected=[sid for sid,span in shots.items() if overlap((a,b),span)] if a!=b else [sid for sid,span in shots.items() if span[0]<=a<span[1] or a==duration==span[1]]
    if x['shot_ids']!=expected:err('E_SPATIAL_SCOPE',path,'镜头范围与时间不一致')
 for n in ns.values():
  path='/timeline/spatial_nodes/'+n['id'];seen={n['id']};parent=n['parent_id']
  if n['entity_id'] is not None and n['entity_id'] not in entities:err('E_NODE_ENTITY',path,'所属实体不存在')
  if n['kind']!='camera' and n['entity_id'] is None:err('E_NODE_ENTITY',path,'非摄影机节点必须绑定项目实体')
  if n['kind']=='part' and not n['part']:err('E_PART',path,'部位节点需明确部位及适用手别')
  while parent:
   if parent not in ns or parent in seen:err('E_NODE_PARENT',path,'父节点不存在或成环');break
   seen.add(parent);parent=ns[parent]['parent_id']
  frame=n['frame']
  if frame['kind'] in ('local','anatomical') and frame['anchor_node_id'] not in ns:err('E_FRAME_ANCHOR',path,'局部坐标缺少有效锚点')
  if frame['anchor_node_id']==n['id']:err('E_FRAME_ANCHOR',path,'局部坐标不得自锚定')
  if frame['kind'] in ('world','screen') and frame['transforms']:err('E_FRAME_TRANSFORM',path,'变换仅用于有锚点的局部坐标')
  if len({x['at_ms'] for x in frame['transforms']})!=len(frame['transforms']):err('E_FRAME_TRANSFORM',path,'同一时刻坐标基重复')
  if n['bounds'] and any(a>b for a,b in zip(n['bounds']['min'],n['bounds']['max'])):err('E_NODE_BOUNDS',path,'范围上下界颠倒')
  for tr in frame['transforms']:
   if not 0<=tr['at_ms']<=duration:err('E_TRANSFORM_TIME',path,'坐标变换时间越界')
   matrix=tr['basis']
   if any(abs(sum(a*b for a,b in zip(matrix[i],matrix[j]))-(1 if i==j else 0))>EPS for i in range(3) for j in range(3)):err('E_FRAME_BASIS',path,'坐标基必须正交归一')
   anchor=frame['anchor_node_id']
   if anchor and anchor in ns:
    # Evidence requires a co-timed explicit anchor, not inferred pose interpolation.
    av=value_at(ir,anchor,'position',tr['at_ms'])
    if av['status']!='EXPLICIT':err('B_FRAME_EVIDENCE',path,'数值坐标变换缺少同刻明确锚点','blocker')
    elif ns[anchor]['frame']['kind']!='world' or av['value']['mode']!='numeric' or not isinstance(av['value']['value'],list):err('B_FRAME_EVIDENCE',path,'世界转换需要锚点的明确世界坐标','blocker')
    elif any(abs(a-b)>EPS for a,b in zip(av['value']['value'],tr['origin'])):err('E_FRAME_ORIGIN',path,'坐标原点与同刻锚点位置不一致')
 actions={a['id'] for a in t['actions']};cameras={c['id']:c for c in t['camera_operations']}
 for i,tr in enumerate(t['motion_tracks']):
  path=f'/timeline/motion_tracks/{i}';n=ns.get(tr['node_id'])
  if not n:err('E_TRACK_NODE',path,'运动节点不存在');continue
  if not set(tr['action_ids'])<=actions or not set(tr['camera_operation_ids'])<=set(cameras):err('E_TRACK_LINK',path,'关联动作或摄影机操作不存在')
  keys=tr['keyframes'];times=[k['at_ms'] for k in keys]
  if times!=sorted(set(times)) or times[0]!=tr['start_ms'] or times[-1]!=tr['end_ms']:err('E_TRACK_KEYS',path,'节点时间须严格递增并覆盖轨道起止')
  for k in keys:
   v=k['value']
   if tr['axis'] is not None and abs(sum(x*x for x in tr['axis'])-1)>EPS:err('E_ROTATION_AXIS',path,'旋转轴必须为单位向量')
   if tr['property']=='rotation' and v['mode']=='numeric' and (tr['axis'] is None or tr['unit']!='degrees' or isinstance(v['value'],list)):err('E_ROTATION_AXIS',path,'数值旋转需角度标量与明确旋转轴')
   if tr['property'] in ('orientation','gaze') and v['mode']=='numeric' and isinstance(v['value'],list) and abs(sum(x*x for x in v['value'])-1)>EPS:err('E_DIRECTION',path,'数值朝向必须为单位方向向量')
   if v['mode']=='numeric' and v['value'] is None or v['mode']=='relative' and v['value'] is not None:err('E_TRACK_VALUE',path,'数值与相对描述模式不一致')
   if v['mode']=='numeric' and tr['property'] in ('position','orientation','gaze') and not isinstance(v['value'],list):err('E_TRACK_VALUE',path,'位置或方向数值必须是三维向量')
   if v['target_node_id'] and v['target_node_id'] not in ns:err('E_TRACK_TARGET',path,'观察或朝向目标不存在')
   if k['transition']=='linear' and (v['mode']!='numeric' or tr['property'] in ('orientation','gaze','rotation','deformation','material','atmosphere','group_motion')):err('E_INTERPOLATION',path,'仅支持明确数值位置或标量属性的线性求值，不能推导姿态')
  for a,b in zip(keys,keys[1:]):
   if a['transition']=='linear' and (b['value']['mode']!='numeric' or isinstance(a['value']['value'],list)!=isinstance(b['value']['value'],list)):err('E_INTERPOLATION',path,'线性节点数值类型不一致')
  for other in t['motion_tracks'][i+1:]:
   if (tr['node_id'],tr['property'])==(other['node_id'],other['property']) and overlap((tr['start_ms'],tr['end_ms']),(other['start_ms'],other['end_ms'])):err('E_TRACK_CONFLICT',path,'同一对象的同一动态属性存在重叠权威')
 for r in t['spatial_relations']:
  path='/timeline/spatial_relations/'+r['id']
  if r['subject_node_id'] not in ns or r['object_node_id'] not in ns:err('E_RELATION_NODE',path,'关系对象不存在')
  if r['predicate'].startswith('world_') and r['frame']!='world' or r['predicate'].startswith('screen_') and r['frame']!='screen':err('E_RELATION_FRAME',path,'世界与画面关系不能混用')
  if r['distance_m'] is not None and r['frame']!='world':err('E_DISTANCE_UNIT',path,'米制距离只用于明确世界坐标')
  if r['predicate']=='attached_to' and r['attachment'] is None:err('E_ATTACHMENT',path,'附着须明确连接双方部位和解除时点')
  opposites={'world_left_of':'world_right_of','screen_left_of':'screen_right_of','world_in_front_of':'world_behind','above':'below'}
  for other in t['spatial_relations']:
   a,b=scope_bounds(r['scope']);c,d=scope_bounds(other['scope']);same_time=(a==b and c<=a<d) or (c==d and a<=c<b) or (a==b==c==d) or overlap((a,b),(c,d))
   if same_time and (r['subject_node_id'],r['object_node_id'],r['frame'])==(other['subject_node_id'],other['object_node_id'],other['frame']) and opposites.get(r['predicate'])==other['predicate']:err('E_RELATION_CONFLICT',path,'同一时段相对关系互相矛盾')
  if r['attachment'] and r['attachment']['release_at_ms'] is not None and r['attachment']['release_at_ms']!=scope_bounds(r['scope'])[1]:err('E_ATTACHMENT_TIME',path,'解除时点需等于附着区间末端')
 for c in t['composition_tracks']:
  path='/timeline/composition_tracks/'+c['id']
  if not set(c['attention_order'])<=set(ns):err('E_COMPOSITION_NODE',path,'注意顺序引用未知节点')
  for sub in c['subjects']:
   if sub['node_id'] not in ns:err('E_COMPOSITION_NODE',path,'构图主体不存在')
   if sub['box'] and (sub['box'][2]<=0 or sub['box'][3]<=0):err('E_SCREEN_BOX',path,'画面区域宽高必须为正，可允许部分画外')
   if sub['box'] and sub['box'][2]>0 and sub['box'][3]>0:
    x,y,w,h=sub['box'];outside=x+w<=0 or y+h<=0 or x>=1 or y>=1;inside=0<=x and 0<=y and x+w<=1 and y+h<=1
    expected='outside' if outside else 'inside' if inside else 'partial'
    if sub['presence']!=expected:err('E_SCREEN_PRESENCE',path,'画面区域与入出画状态不一致')
   if sub['presence']=='outside' and sub['visible_parts']:err('E_VISIBLE_OUTSIDE',path,'画外主体不能同时声明可见部位')
  for other in t['composition_tracks']:
   if c['id']!=other['id'] and overlap((c['start_ms'],c['end_ms']),(other['start_ms'],other['end_ms'])):err('E_COMPOSITION_CONFLICT',path,'同一时段只能有一个明确构图状态')
 for sid,(start,end) in shots.items():
  cur=start
  for c in sorted((c for c in t['composition_tracks'] if sid in c['shot_ids']),key=lambda x:x['start_ms']):
   if c['start_ms']>cur:err('E_COMPOSITION_GAP','/timeline/composition_tracks',sid+' 构图区间未覆盖')
   cur=max(cur,c['end_ms'])
  if cur<end:err('E_COMPOSITION_GAP','/timeline/composition_tracks',sid+' 缺少构图状态')
 if errors:return errors
 common=legacy.validate(projection(ir),root,kind,base)
 errors.extend(e for e in common if e['code'] not in ('E_CAMERA_CONFLICT','E_CONTRACT','E_CONTRACT_PATH'))
 clauses=ir['contract'] if isinstance(ir['contract'],list) else ir['contract']['clauses']
 for clause in clauses:
  for path in clause.get('paths',[]):
   try:pointer(ir,path)
   except (KeyError,IndexError,TypeError):err('E_CONTRACT_PATH',path,'合同字段不存在')
  for check in clause.get('checks',[]):
   try:
    value=pointer(ir,check['path']);ok=check['op']=='exists' or check['op']=='equals' and value==check['value'] or check['op']=='contains' and check['value'] in value
   except (KeyError,IndexError,TypeError):ok=False
   if not ok:err('E_CONTRACT',check['path'],'合同断言失败')

 # Property-level camera conflict checks; axes of pan and tilt are independent.
 for i,c in enumerate(t['camera_operations']):
  for d in t['camera_operations'][i+1:]:
   if not overlap((c['start_ms'],c['end_ms']),(d['start_ms'],d['end_ms'])):continue
   channels=CAMERA_CHANNELS[c['operation']]&CAMERA_CHANNELS[d['operation']]
   if channels and {c['operation'],d['operation']}!={'pan','tilt'}:err('E_CAMERA_CHANNEL','/timeline/camera_operations','摄影机同一属性发生冲突：'+c['id']+' / '+d['id'])
 # Compatibility endpoints remain checks; a track must not hide a changed old view.
 samples={(x['shot_id'],x['at_ms']):x for x in t['state_samples']}
 previous=None
 for shot in ir['shots']:
  for edge,at in zip(('start','end'),shots[shot['id']]):
   sample=samples.get((shot['id'],at))
   if not sample:continue
   raw=shot.get('state_'+edge,shot.get(edge+'_state',{}));rows=raw.items() if isinstance(raw,dict) else ((x['entity_id'],x) for x in raw)
   for eid,st in rows:
    pos=st.get('position_m',st.get('position'))
    if kind=='director-ir' and pos is not None:pos=[pos[0],pos[2],pos[1]]
    if eid in sample['entities'] and pos!=sample['entities'][eid]['position']:err('E_BOUNDARY_VIEW','/shots/'+shot['id'],'兼容位置与明确关键状态冲突：'+eid)
  transition=shot.get('transition',{});typ=transition.get('type') if isinstance(transition,dict) else transition
  if previous and previous['scene_id']==shot['scene_id'] and typ not in ('time_jump','subjective'):
   a=samples.get((previous['id'],shots[previous['id']][1]));b=samples.get((shot['id'],shots[shot['id']][0]))
   if a and b:
    for eid in a['entities'].keys() & b['entities'].keys():
     if a['entities'][eid]['position']!=b['entities'][eid]['position']:err('E_CONTINUITY','/timeline/state_samples',eid+'跨镜位置不连续')
  previous=shot
 # Snapshot checks preserve the existing complete pose; only declared positions derive.
 for sample in t['state_samples']:
  for n in ns.values():
   if n['kind']!='entity' or n['entity_id'] not in sample['entities']:continue
   pos=position_at(ir,n['id'],sample['at_ms'])
   if pos is not None and sample['entities'][n['entity_id']]['position'] is not None and any(abs(a-b)>EPS for a,b in zip(pos,sample['entities'][n['entity_id']]['position'])):err('E_TRACK_STATE','/timeline/state_samples/'+sample['id'],'明确轨道位置与关键姿态冲突：'+n['label'])
 for action in t['actions']:
  for change in action['changes']:
   if change['field']!='position':continue
   entity_nodes=[n for n in ns.values() if n['kind']=='entity' and n['entity_id']==change['entity_id']]
   for n in entity_nodes:
    pos=position_at(ir,n['id'],change['at_ms'])
    if pos is not None and change['after']!=pos:err('E_TRACK_CHANGE','/timeline/actions/'+action['id'],'兼容动作位置与运动轨道冲突')
 for r in geometry_checks(ir):
  if r['status']=='FAIL':err('E_GEOMETRY','/timeline/spatial_relations/'+r['id'],'明确数值关系不成立')
 return errors

LABELS={'position':'位置','orientation':'朝向','gaze':'视线','rotation':'旋转','zoom':'变焦','focus':'焦点','deformation':'形态变化','extent':'范围变化','group_motion':'群体运动','light':'光线','color':'色彩','material':'材质','atmosphere':'环境氛围','world':'世界坐标（右、上、深）','screen':'画面坐标（右、下、深）','local':'对象局部坐标','anatomical':'人体自身坐标','world_left_of':'位于世界左侧','world_right_of':'位于世界右侧','world_in_front_of':'位于世界前方','world_behind':'位于世界后方','screen_left_of':'位于画面左侧','screen_right_of':'位于画面右侧','above':'位于上方','below':'位于下方','near':'靠近','far':'远离','faces':'朝向','touching':'接触','supports':'支撑','contains':'包含','occludes':'遮挡','attached_to':'保持附着','m':'米','normalized':'归一化画面单位','degrees':'度','unitless':'无量纲','relative':'相对描述','kelvin':'开尔文','none':'中间状态未指定','hold':'保持此值至下一节点','linear':'至下一节点按明确线性变化','inside':'在画内','partial':'部分出画','outside':'在画外'}
readable=legacy.readable;sha256=legacy.sha256;temporal_hash=legacy.temporal_hash

def motion_text(ir,tr,start_ms=0,end_ms=None):
 original=tr;tr=deepcopy(tr);stop=tr['end_ms'] if end_ms is None else min(end_ms,tr['end_ms']);begin=max(start_ms,tr['start_ms'])
 tr['keyframes']=[k for k in tr['keyframes'] if begin<=k['at_ms']<=stop]
 for at in (begin,stop):
  if not any(k['at_ms']==at for k in tr['keyframes']):
   evaluated=evaluate_track(original,at);tr['keyframes'].append({'at_ms':at,'value':evaluated['value'] or {'mode':'relative','value':None,'description':'此拆段边界缺少明确运动状态，待补齐，不可执行','target_node_id':None},'transition':'none'})
 tr['keyframes'].sort(key=lambda k:k['at_ms']);tr.update(start_ms=begin,end_ms=stop)
 ns=nodes(ir);n=ns[tr['node_id']];frame=n['frame'];anchor=ns.get(frame['anchor_node_id'],{}).get('label')
 lines=[n['label']+'的'+LABELS[tr['property']]+f"｜{(tr['start_ms']-start_ms)/1000:g}–{(tr['end_ms']-start_ms)/1000:g}秒",'坐标依据：'+LABELS[frame['kind']]+('；锚点：'+anchor if anchor else ''),'路径：'+tr['path'],'速度与节奏：'+tr['speed']]
 for key in tr['keyframes']:
  value=key['value'];text=value['description']
  if value['mode']=='numeric':text+='；数值 '+readable(value['value'])+' '+LABELS[tr['unit']]
  if value['target_node_id']:text+='；目标：'+ns[value['target_node_id']]['label']
  lines.append(f"{(key['at_ms']-start_ms)/1000:g}秒："+text+('；'+LABELS[key['transition']] if key!=tr['keyframes'][-1] else ''))
 if tr['axis'] is not None:lines.append('旋转轴：'+readable(tr['axis']))
 return '\n'.join(lines)

def render(ir,start_ms=0,end_ms=None):
 t=ir['timeline'];ns=nodes(ir);end_ms=max(b[1] for b in bounds(ir).values()) if end_ms is None else end_ms
 base,oldcoverage=legacy.render(ir,start_ms,end_ms);blocks=[];coverage=[];consumed=set()
 def append(text,path,node,paths=None):
  idx=len(blocks);blocks.append({'text':text,'path':path,'id':node.get('id'),'channel':'prompt'})
  for p,v in leaves(node,path):
   metadata=any(p==path+'/'+f or p.startswith(path+'/'+f+'/') for f in ('origin','id','shot_ids','action_ids','camera_operation_ids'))
   outside=False
   relative=p[len(path)+1:].split('/')
   if relative[0]=='keyframes':outside=not start_ms<=node['keyframes'][int(relative[1])]['at_ms']<=end_ms
   if len(relative)>2 and relative[:2]==['frame','transforms']:outside=not start_ms<=node['frame']['transforms'][int(relative[2])]['at_ms']<=end_ms
   metadata=metadata or outside or v is None
   coverage.append({'source_path':p,'source_sha256':digest(v),'object_id':node.get('id'),'disposition':'not_applicable' if metadata else 'equivalent_conversion','channel':'review' if metadata else 'prompt','block':None if metadata else idx,'text_sha256':None if metadata else digest(text),'reason':'来源和结构标识保留于制作包' if metadata else '按类型及时间逐项转为正文；语义复核独立记录','rule':'SPATIAL.LOWER.1.2'})
  return idx
 for i,c in enumerate(t['composition_tracks']):
  if not overlap((c['start_ms'],c['end_ms']),(start_ms,end_ms)):continue
  lines=[f"【空间与构图｜{(max(start_ms,c['start_ms'])-start_ms)/1000:g}–{(min(end_ms,c['end_ms'])-start_ms)/1000:g}秒】",c['framing'],'前中后景：'+c['depth_layers'],'注意顺序：'+' → '.join(ns[x]['label'] for x in c['attention_order']),'留白：'+c['negative_space'],'安全区：'+c['safe_area']]
  for sub in c['subjects']:
   lines.append(ns[sub['node_id']]['label']+'：'+sub['description']+'；'+LABELS[sub['presence']]+'；'+readable(sub['depth'])+'；可见部位：'+readable(sub['visible_parts'])+'；可读尺度：'+readable(sub['readability'])+'；遮挡：'+sub['occlusion']+('；画面区域（左、上、宽、高）：'+readable(sub['box']) if sub['box'] else ''))
  append('\n'.join(lines),f'/timeline/composition_tracks/{i}',c)
 for i,r in enumerate(t['spatial_relations']):
  a,b=scope_bounds(r['scope'])
  if not ((start_ms<=a<end_ms or a==end_ms==max(span[1] for span in bounds(ir).values())) if a==b else overlap((a,b),(start_ms,end_ms))):continue
  time=f'{(a-start_ms)/1000:g}秒' if a==b else f'{(max(a,start_ms)-start_ms)/1000:g}–{(min(b,end_ms)-start_ms)/1000:g}秒'
  text=f"【相对位置与连接｜{time}】\n"+ns[r['subject_node_id']]['label']+' '+LABELS[r['predicate']]+' '+ns[r['object_node_id']]['label']+'；依据：'+LABELS[r['frame']]+'。\n'+r['criterion']
  if r['distance_m'] is not None:text+=f"\n距离阈值：{r['distance_m']:g}米。"
  if r['attachment']:
   a=r['attachment'];text+='\n连接部位：'+a['subject_part']+' ↔ '+a['object_part']
   if a['relative_offset'] is not None:text+='；相对偏移：'+readable(a['relative_offset'])
   if a['release_at_ms'] is not None:text+=f"；{(a['release_at_ms']-start_ms)/1000:g}秒解除连接"
  append(text,f'/timeline/spatial_relations/{i}',r)
 for oldidx,b in enumerate(base):
  if b['path'].startswith('/timeline/visibility'):continue
  idx=len(blocks);blocks.append(deepcopy(b))
  for row in oldcoverage:
   if row['block']!=oldidx or any(row['source_path'].startswith('/timeline/'+f) for f in FIELDS):continue
   row=deepcopy(row);row['block']=idx;row['disposition']='direct_output' if row['disposition']=='emitted' else 'not_applicable';coverage.append(row)
  for i,tr in enumerate(t['motion_tracks']):
   if tr['id'] in consumed or not overlap((tr['start_ms'],tr['end_ms']),(start_ms,end_ms)):continue
   if b['id'] not in tr['action_ids']+tr['camera_operation_ids']:continue
   append('【本项的运动细节；随原动作执行】\n'+motion_text(ir,tr,start_ms,end_ms),f'/timeline/motion_tracks/{i}',tr);consumed.add(tr['id'])
 for i,tr in enumerate(t['motion_tracks']):
  if tr['id'] not in consumed and overlap((tr['start_ms'],tr['end_ms']),(start_ms,end_ms)):
   append('【场景或物件变化】\n'+motion_text(ir,tr,start_ms,end_ms),f'/timeline/motion_tracks/{i}',tr);consumed.add(tr['id'])
 # Node coordinate and part definitions are executable context, not hidden metadata.
 for i,n in enumerate(t['spatial_nodes']):
  used=any(tr['node_id']==n['id'] and tr['id'] in consumed for tr in t['motion_tracks']) or any(n['id'] in [x['node_id'] for x in c['subjects']] and overlap((c['start_ms'],c['end_ms']),(start_ms,end_ms)) for c in t['composition_tracks']) or any(n['id'] in (r['subject_node_id'],r['object_node_id']) for r in t['spatial_relations'])
  if used:
   text='【对象与部位】\n'+n['label']+'；'+(n['part'] or '整体')+'；类型：'+readable(n['kind'])+'；'+LABELS[n['frame']['kind']]+'；单位：'+LABELS[n['frame']['unit']]
   if n['parent_id']:text+='；所属：'+ns[n['parent_id']]['label']
   if n['entity_id']:text+='；对应实体：'+n['entity_id']
   if n['frame']['anchor_node_id']:text+='；坐标锚点：'+ns[n['frame']['anchor_node_id']]['label']
   for frame in n['frame']['transforms']:
    if start_ms<=frame['at_ms']<=end_ms:text+=f"\n{(frame['at_ms']-start_ms)/1000:g}秒坐标基："+readable(frame['basis'])+'；原点：'+readable(frame['origin'])
   if n['bounds']:text+='\n世界轴对齐范围偏移：'+readable(n['bounds'])
   append(text,f'/timeline/spatial_nodes/{i}',n)
 # Render human names in place of internal IDs, then bind final block fingerprints.
 names={e['id']:e.get('name',e.get('label',e['id'])) for e in ir['entities']}
 names.update({x['id']:f"第{i+1}项动作" for i,x in enumerate(t['actions'])});names.update({x['id']:f"第{i+1}项摄影机操作" for i,x in enumerate(t['camera_operations'])})
 import re
 for b in blocks:
  for ident,label in sorted(names.items(),key=lambda kv:-len(kv[0])):
   b['text']=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(ident)+r'(?![A-Za-z0-9_])',lambda _:label,b['text'])
 for row in coverage:
  if row['block'] is not None:row['text_sha256']=digest(blocks[row['block']]['text'])
 covered={x['source_path'] for x in coverage}
 for p,v in leaves(t,'/timeline'):
  if p not in covered:coverage.append({'source_path':p,'source_sha256':digest(v),'object_id':None,'disposition':'not_applicable','channel':'review','block':None,'text_sha256':None,'reason':'来源、兼容视图或非本片段范围保留；不能抵充执行覆盖','rule':'SPATIAL.SCOPE.1.2'})
 return blocks,coverage

def verify_coverage(ir,blocks,coverage,start_ms=0,end_ms=None):
 expected=render(ir,start_ms,end_ms)[1];actual={r['source_path']:r for r in coverage};errors=[]
 for row in expected:
  current=actual.get(row['source_path'])
  if row['disposition'] in ('direct_output','equivalent_conversion') and current and (current['disposition'] not in ('direct_output','equivalent_conversion','emitted') or current['channel']!=row['channel']):errors.append(issue('E_DETAIL_CHANNEL',row['source_path'],'适用执行细节不能仅保存在伴随文件或其他渠道'))
 mapped=deepcopy(coverage)
 for row in mapped:
  row['disposition']='emitted' if row['disposition'] in ('direct_output','equivalent_conversion','emitted') else 'retained'
 return errors+legacy.verify_coverage(ir,blocks,mapped)

def panel_state(ir,shot_id,at_ms):
 result=legacy.panel_state(ir,shot_id,at_ms);t=ir['timeline'];end=bounds(ir)[shot_id][1]==at_ms
 compositions=[c for c in t['composition_tracks'] if shot_id in c['shot_ids'] and active(c,at_ms,end)]
 if len(compositions)>1:compositions=[c for c in compositions if c['start_ms']==at_ms] or compositions[-1:]
 tracks=[tr for tr in t['motion_tracks'] if shot_id in tr['shot_ids'] and active(tr,at_ms,end)]
 values=[evaluate_track(tr,at_ms) for tr in tracks]
 relations=[r for r in t['spatial_relations'] if shot_id in r['shot_ids'] and (scope_bounds(r['scope'])[0]==at_ms if r['scope']['kind']=='point' else scope_bounds(r['scope'])[0]<=at_ms<scope_bounds(r['scope'])[1] or (end and at_ms==scope_bounds(r['scope'])[1]))]
 result.update(composition=deepcopy(compositions[0]) if compositions else None,motion_values=values,spatial_relations=deepcopy(relations),nodes=[deepcopy(n) for n in t['spatial_nodes'] if any(tr['node_id']==n['id'] for tr in tracks)],derived_properties=[v['track_id'] for v in values if v['status'].startswith('DERIVED')],physical_interpolation=False)
 if not compositions or any(v['status']=='NEEDS_KEY_STATE' for v in values):result['status']='NEEDS_KEY_POSE'
 return result

def affected(ir,node_id=None,track_id=None):
 ns=nodes(ir);selected={node_id} if node_id else set();tracks=set()
 if track_id:
  tr=next((x for x in ir['timeline']['motion_tracks'] if x['id']==track_id),None)
  if not tr:raise ValueError('Unknown motion track')
  tracks.add(track_id)
 if node_id and node_id not in ns:raise ValueError('Unknown spatial node')
 # A node definition change affects descendants; an individual track does not
 # invalidate every other property merely because it shares the same subject.
 for _ in range(len(ns)):
  selected.update(n['id'] for n in ns.values() if n['parent_id'] in selected or n['frame']['anchor_node_id'] in selected)
 tracks.update(tr['id'] for tr in ir['timeline']['motion_tracks'] if tr['node_id'] in selected)
 rows=[tr for tr in ir['timeline']['motion_tracks'] if tr['id'] in tracks];node_refs=selected|{tr['node_id'] for tr in rows};actions={a for tr in rows for a in tr['action_ids']};shots={s for tr in rows for s in tr['shot_ids']}
 changed=True
 while changed:
  old=set(actions)
  actions.update(a['id'] for a in ir['timeline']['actions'] if any(d['action_id'] in actions and d['relation']!='overlaps' for d in a['depends_on']))
  changed=actions!=old
 shots.update(s for a in ir['timeline']['actions'] if a['id'] in actions for s in a['shot_ids'])
 relations=[r['id'] for r in ir['timeline']['spatial_relations'] if {r['subject_node_id'],r['object_node_id']}&node_refs and (node_id or any(overlap(scope_bounds(r['scope']),(tr['start_ms'],tr['end_ms'])) or scope_bounds(r['scope'])[0] in (tr['start_ms'],tr['end_ms']) for tr in rows))]
 shots.update(s for r in ir['timeline']['spatial_relations'] if r['id'] in relations for s in r['shot_ids'])
 if node_id:shots.update(s for c in ir['timeline']['composition_tracks'] if selected & ({x['node_id'] for x in c['subjects']}|set(c['attention_order'])) for s in c['shot_ids'])
 audio=[a['id'] for a in ir['timeline']['audio_events'] if a['sync'] and a['sync']['action_id'] in actions]
 shots.update(s for a in ir['timeline']['audio_events'] if a['id'] in audio for s in a['shot_ids'])
 return {'node_ids':sorted(selected),'track_ids':sorted(tracks),'action_ids':sorted(actions),'relation_ids':relations,'audio_ids':audio,'shot_ids':[s['id'] for s in ir['shots'] if s['id'] in shots]}

def affected_shots(ir,shot_id):return legacy.affected_shots(ir,shot_id)
def changed_shots(before,after):
 result=set(legacy.changed_shots(before,after))
 for col in FIELDS:
  old={x['id']:x for x in before['timeline'][col]};new={x['id']:x for x in after['timeline'][col]}
  for ident in old.keys()|new.keys():
   if old.get(ident)==new.get(ident):continue
   for ir,value in ((before,old.get(ident)),(after,new.get(ident))):
    if value is None:continue
    if col=='spatial_nodes':result.update(affected(ir,node_id=ident)['shot_ids'])
    else:result.update(value['shot_ids'])
 return sorted(result)

def segment_plan(ir):
 results=legacy.segment_plan(ir)
 for result in results:
  start,end=result['project_start_ms'],result['project_end_ms'];reasons=result['reasons']
  for tr in ir['timeline']['motion_tracks']:
   if overlap((start,end),(tr['start_ms'],tr['end_ms'])) and (tr['start_ms']<start or tr['end_ms']>end):
    reasons.append('NEEDS_EXPLICIT_MOTION_SLICE:'+tr['id'])
  for at in (start,end):
   sid=next(s for s,(a,b) in bounds(ir).items() if a<=at<b or at==end==b)
   p=panel_state(ir,sid,at)
   if p['status']=='NEEDS_KEY_POSE':reasons.append('NEEDS_SPATIAL_BOUNDARY:'+str(at))
  result['spatial_continuity']={'start':panel_state(ir,result['continuity']['shot_ids'][0],start),'end':panel_state(ir,result['continuity']['shot_ids'][-1],end)}
  blocks,coverage=render(ir,start,end);result['prompt']='\n\n'.join(b['text'] for b in blocks if b['channel']=='prompt');result['detail_coverage']=coverage
  result['status']='BLOCKED' if reasons else 'DRAFT_REQUIRES_TARGET_CHECK'
 return results
