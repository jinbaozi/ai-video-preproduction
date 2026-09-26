import hashlib
import json
import subprocess
import sys
from pathlib import Path
from ai_comic_drama_workflow.v5_handoff import validate_handoff

ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
OUT = ROOT/'runtime/v6/candidates/TASK_4de99276d376cc50c61527d6/1'
EVID = OUT/'evidence'
TASK = json.loads((ROOT/'runtime/tasks/TASK_4de99276d376cc50c61527d6.json').read_text())
VENVELOPE = json.loads((ROOT/'runtime/v6/state.json').read_text())['tasks'][TASK['task_id']]['envelope']
ART = OUT/'art-ir.json'
art = json.loads(ART.read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
write = lambda p,x: Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
uri = lambda p: Path(p).relative_to(ROOT).as_posix()
base = 'runtime/v6/candidates/'+TASK['task_id']+'/1/'

reads = []
for item in TASK['module']['required_reads']:
    actual = sha(item['path'])
    if actual != item['sha256']: raise RuntimeError('locked read changed: '+item['relative'])
    reads.append({'path':item['path'],'sha256':actual})
module_receipt = {
    'name':TASK['module']['name'],
    'version':TASK['module']['version'],
    'skill_sha256':TASK['module']['skill_sha256'],
    'reads':reads,
}
v6_inputs=[]
for x in VENVELOPE['inputs']:
    path=ROOT/x['uri']
    actual=sha(path)
    if actual != x['sha256']: raise RuntimeError('V6 input changed: '+x['slot'])
    v6_inputs.append({'slot':x['slot'],'uri':x['uri'],'sha256':actual})
v5_inputs=[]
for x in TASK['inputs']:
    actual=sha(x['uri'])
    if actual != x['sha256']: raise RuntimeError('V5 input changed: '+x['slot'])
    v5_inputs.append({'slot':x['slot'],'uri':x['uri'],'sha256':actual})
write(EVID/'frozen-inputs.json',{'status':'PASS','module_receipt':module_receipt,'v6_inputs':v6_inputs,'v5_inputs':v5_inputs})

script = Path(TASK['module']['path'])/'scripts/art_compile.py'
command=[sys.executable,str(script),'validate',str(ART)]
proc=subprocess.run(command,capture_output=True,text=True)
if proc.returncode: raise RuntimeError('native validator failed: '+proc.stderr+proc.stdout)
report=json.loads(proc.stdout)
if report.get('art_sha256') != sha(ART) or report.get('status') != 'STATIC_VALID':
    raise RuntimeError('unexpected native report: '+proc.stdout)
write(EVID/'native-validator.json',{'command':command,'exit_code':proc.returncode,'stdout':report,
    'stderr':proc.stderr,'artifact_uri':uri(ART),'artifact_sha256':sha(ART)})

compiled=OUT/'compiled'
handoff_compiled=json.loads((compiled/'handoff.json').read_text())
qa=json.loads((compiled/'qa-report.json').read_text())
assert handoff_compiled['status']=='PLANNED' and handoff_compiled['submitted'] is False
assert qa['status']=='NOT_RUN' and all(r['result']=='NOT_RUN' for r in qa['records'])
shot_states={s['id']:s for s in handoff_compiled['shots']}
assert shot_states['S_HANDOFF']['state_after']['PROP_LETTER']['condition']=='同一封未拆、封口完整'
assert shot_states['S_SEAL']['state_after']['CHAR_YI']['condition']=='已确认同一封信封口完整'
assert shot_states['S_STOW']['state_after']['PROP_BACKPACK']['condition']=='收纳同一封信'
assert shot_states['S_STOW']['state_after']['PROP_LETTER']['condition']=='同一封未拆、封口完整'
assert shot_states['S_STOW']['events'][0]['director_pointer']=='/timeline/actions/2'
write(EVID/'state-chain-audit.json',{
    'status':'PASS_STATIC',
    'compiled_handoff_uri':uri(compiled/'handoff.json'),'compiled_handoff_sha256':sha(compiled/'handoff.json'),
    'compiled_qa_uri':uri(compiled/'qa-report.json'),'compiled_qa_sha256':sha(compiled/'qa-report.json'),
    'shot_terminal_states':{
      sid:{'PROP_LETTER':shot_states[sid]['state_after'].get('PROP_LETTER'),
           'CHAR_YI':shot_states[sid]['state_after'].get('CHAR_YI'),
           'PROP_BACKPACK':shot_states[sid]['state_after'].get('PROP_BACKPACK'),
           'events':[e['id'] for e in shot_states[sid]['events']]}
      for sid in ['S_HANDOFF','S_SEAL','S_STOW']},
    'director_handoff_ownership':'EVENT_HANDOFF contact/support/controller arrays are retained in frozen DirectorIR. Art shot support keeps hands and same letter readable; no fake string event is invented.',
    'media_review':'NOT_RUN',
})

spec={r['id']:r for r in TASK['handoff']['required_handoffs']}
mapping={
 'director:REQ_RAIN_NIGHT':(
    '雨夜写入世界、美术环境和逐镜背景，地点及室内外仍开放。','ART_WORLD',[
        {'op':'contains','path':'/world/thesis','value':'雨夜'},
        {'op':'contains','path':'/set/atmosphere','value':'具体室内外'}]),
 'director:REQ_SAME_UNOPENED_LETTER':(
    '同一 PROP_LETTER 资产绑定三个镜头，封口持续完整且验封不拆。','ART_CONTINUITY',[
        {'op':'contains','path':'/assets/2/identity_locks/0','value':'同一实体 PROP_LETTER'},
        {'op':'contains','path':'/shots/1/composition_support/occlusion','value':'未拆信'},
        {'op':'equals','path':'/assets/2/initial_state/condition','value':'同一封未拆、封口完整'}]),
 'director:REQ_EVENT_ORDER':(
    '三镜按交接、验封、入包排序；两个原生离散终态事件只读绑定冻结导演动作，交接控制权归导演。','ART_MAPPING',[
        {'op':'equals','path':'/shots/0/id','value':'S_HANDOFF'},
        {'op':'equals','path':'/shots/1/id','value':'S_SEAL'},
        {'op':'equals','path':'/shots/2/id','value':'S_STOW'},
        {'op':'equals','path':'/events/0/director_pointer','value':'/timeline/actions/1'},
        {'op':'equals','path':'/events/1/director_pointer','value':'/timeline/actions/2'}]),
 'director:REQ_ENDING':(
    '终镜 Art 原生状态链把背包从待收纳信改为收纳同一封信，导演8500毫秒后信在包内且终帧不外露。','ART_STOW',[
        {'op':'equals','path':'/events/1/after','value':'收纳同一封信'},
        {'op':'contains','path':'/shots/2/composition_support/background','value':'8500毫秒后信完全在背包内'},
        {'op':'contains','path':'/shots/2/composition_support/occlusion','value':'终帧只见乙手退出与背包口'}]),
 'director:REQ_SCRIPT_EVENTS':(
    '三个原生事件按冻结导演时轴承接：交信归导演接触控制权、验封确认与收包写入 Art 逐镜离散状态。','ART_MAPPING',[
        {'op':'contains','path':'/shots/0/composition_support/occlusion','value':'EVT_HANDOFF'},
        {'op':'equals','path':'/events/0/shot_id','value':'S_SEAL'},
        {'op':'equals','path':'/events/1/shot_id','value':'S_STOW'},
        {'op':'equals','path':'/events/0/after','value':'已确认同一封信封口完整'},
        {'op':'equals','path':'/events/1/after','value':'收纳同一封信'}]),
 'director:REQ_REVEAL_ORDER':(
    '交接镜不提前展示验封/入包，验封镜不提前展示入包，最后镜才呈现收存结果。','ART_MAPPING',[
        {'op':'contains','path':'/shots/0/composition_support/negative_space','value':'不提前展示验封或入包结果'},
        {'op':'contains','path':'/shots/1/composition_support/negative_space','value':'不提前显示入包'},
        {'op':'contains','path':'/shots/2/composition_support/negative_space','value':'只在验封之后出现'}]),
}
handoff=[]
for key,req in spec.items():
    reason,target_clause,checks=mapping[key]
    handoff.append({'requirement_id':key,'source_fingerprint':req['source_fingerprint'],
        'reason':reason,'target_checks':checks,'target_clause':target_clause})
validated=validate_handoff('art',art,TASK['handoff']['required_handoffs'],handoff)
write(EVID/'handoff-v5.json',{'status':'PASS_STATIC','mappings':validated,
    'scope':'V5 native target assertions; semantic and media review remain independent'})
for specrow,source_slot,proof in zip(VENVELOPE['handoffs'],
    ['canon:project:project:Canon','director:project:project:DirectorIR'],
    ['handoff-v6-canon.json','handoff-v6-director.json']):
    inputrow=next(i for i in v6_inputs if i['slot']==source_slot)
    native_binding=art['canon'] if source_slot.startswith('canon:') else art['director']
    write(EVID/proof,{'requirement_id':specrow['requirement_id'],'source_slot':source_slot,
        'input':inputrow,'native_binding':native_binding,'static_checks':['frozen input hash matched',
        'same scene and entity IDs retained','hard source requirements mapped into ArtIR'],'media_review':'NOT_RUN'})

checks=[
 {'id':'module_receipt','status':'PASS','finding':'四份锁定 Art 资源和 V5/V6 冻结输入均逐字节核对。',
  'evidence':[base+'evidence/frozen-inputs.json']},
 {'id':'native_validator','status':'PASS','finding':'锁定 Art 1.3.3 原生校验新鲜返回 STATIC_VALID；编译为 PLANNED，实际媒体 NOT_RUN。',
  'evidence':[base+'evidence/native-validator.json',base+'compiled/receipt.json',base+'compiled/qa-report.json']},
 {'id':'handoff','status':'PASS','finding':'六条 V5 静态目标断言通过，V6 Canon/Director 来源逐条绑定；编译状态链在验封和入包完成，交信接触控制权留于导演。',
  'evidence':[base+'evidence/handoff-v5.json',base+'evidence/handoff-v6-canon.json',base+'evidence/handoff-v6-director.json',base+'evidence/state-chain-audit.json',base+'evidence/action-bindings.json']},
]
role={
 'schema':'role-result/5.1',
 'task_id':TASK['task_id'],
 'context_fingerprint':TASK['context_fingerprint'],
 'artifact':str(ART),
 'artifact_sha256':sha(ART),
 'module_receipt':module_receipt,
 'checks':checks,
 'handoff':handoff,
 'complete':True,
 'conflicts':[],
 'unresolved':[],
 'validator':report,
}
write(OUT/'role-result.json',role)

v6_handoffs=[]
for specrow,proof in zip(VENVELOPE['handoffs'],['handoff-v6-canon.json','handoff-v6-director.json']):
    row=dict(specrow)
    row['evidence']=[base+'evidence/'+proof,base+'evidence/handoff-v5.json',base+'evidence/state-chain-audit.json']
    v6_handoffs.append(row)
candidate={
 'schema':'candidate-result/6.0',
 'task_id':TASK['task_id'],
 'batch':VENVELOPE['batch'],
 'agent_id':'/root/host_bridge/full_rehearsal/v6_ef7e68da05761cf96b9008e1',
 'input_digest':VENVELOPE['input_digest'],
 'result_uri':base+'role-result.json',
 'result_sha256':sha(OUT/'role-result.json'),
 'artifacts':[{'slot':VENVELOPE['expected_artifacts'][0]['slot'],'kind':'ArtIR',
               'uri':base+'art-ir.json','sha256':sha(ART)}],
 'module_receipts':[VENVELOPE['module']],
 'checks':[{'id':c['id'],'status':c['status'],'evidence':c['evidence']} for c in checks],
 'handoffs':v6_handoffs,
 'unresolved':[],
}
write(OUT/'candidate-result.json',candidate)
print(json.dumps({'candidate_uri':base+'candidate-result.json','candidate_sha256':sha(OUT/'candidate-result.json'),
  'art_sha256':sha(ART),'validator_status':report['status'],'compiled_status':handoff_compiled['status'],
  'media_review':qa['status'],'art_event_ids':[e['id'] for e in art['events']]},ensure_ascii=False))
