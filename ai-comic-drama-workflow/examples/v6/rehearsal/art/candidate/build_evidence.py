import hashlib
import json
import subprocess
from pathlib import Path

root=Path('/private/tmp/ai-video-v6-real-efKlQy/project')
base=root/'runtime/v6/candidates/TASK_0560d46ecc764c68ee9a590e/1'
evd=base/'evidence'
art_path=base/'art-ir.json'
art=json.loads(art_path.read_text())
task=json.loads((root/'runtime/tasks/TASK_0560d46ecc764c68ee9a590e.json').read_text())
state=json.loads((root/'runtime/v6/state.json').read_text())
env=state['tasks'][task['task_id']]['envelope']
module_root=root/'runtime/modules/34f6b460f4db70acbed406b82edf53b55240fb3f476afd81daeb5c9ac72a8019/production-design-grammar'
python='/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/.venv/bin/python'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p): return str(Path(p).relative_to(root))
def dump(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
def pointer(obj,path):
    if path=='': return obj
    for x in path[1:].split('/'):
        x=x.replace('~1','/').replace('~0','~')
        obj=obj[int(x)] if isinstance(obj,list) else obj[x]
    return obj

# Verify the V6 input bytes, frozen task, and every locked resource anew.
inputs=[]
for i in env['inputs']:
    p=root/i['uri']; actual=sha(p); assert actual==i['sha256'],i['uri']
    inputs.append({**i,'actual_sha256':actual,'verified':True})
resources=[]
for i in env['resources']:
    p=root/i['uri']; actual=sha(p); assert actual==i['sha256'],i['uri']
    resources.append({**i,'actual_sha256':actual,'verified':True})
assert env['scope']=={'kind':'scene','ids':['SC_RAIN_NIGHT']}
assert env['module']=={'name':'production-design-grammar','sha256':'34f6b460f4db70acbed406b82edf53b55240fb3f476afd81daeb5c9ac72a8019','version':'1.3.1'}
assert sha(art['director']['uri'])==art['director']['sha256']
canon=json.loads(Path(art['canon']['uri']).read_text())
director=json.loads(Path(art['director']['uri']).read_text())
assert director['canon_ref']==art['canon']['uri']
assert canon['revision']==int(art['canon']['revision'])
assert director['revision']==art['director']['revision']
assert [x['id'] for x in director['timeline']['actions']]==['ACT_EXTEND','ACT_GRIP','ACT_RELEASE','ACT_CONFIRM_SEAL','ACT_STOW']
assert director['shots'][0]['phases']==[]
assert art['events']==[]
assert director['shots'][0]['dialogue']==[]
assert art['set']['scene_id']=='SC_RAIN_NIGHT'
assert [a['id'] for a in art['assets']].count('PROP_LETTER')==1
assert all(x['status']=='planned' and x['file'] is None and x['sha256'] is None for x in art['references'])
source_file=root/'sources/SRC_69a71adcfaca/source.txt'
source_integrity={'status':'PASS','scope':'SC_RAIN_NIGHT','v6_input_revision':env['input_revision'],
                  'v6_input_digest':env['input_digest'],'inputs':inputs,'resources':resources,
                  'v5_formal_inputs':[{'slot':i['slot'],'uri':i['uri'],'expected_sha256':i['sha256'],'actual_sha256':sha(i['uri']),'verified':sha(i['uri'])==i['sha256']} for i in task['inputs']],
                  'original_source':{'uri':rel(source_file),'sha256':sha(source_file)},
                  'binding':{'canon_uri':art['canon']['uri'],'canon_revision':art['canon']['revision'],
                             'director_uri':art['director']['uri'],'director_sha256':art['director']['sha256'],
                             'director_revision':art['director']['revision']},
                  'notes':['V5 formal input bytes and V6 candidate input bytes are separately frozen; ArtIR binds the V6 candidate inputs from this dispatch.',
                           'DirectorIR has no shot phases; art events are empty and the action sequence remains in the bound DirectorIR timeline.']}
assert all(x['verified'] for x in source_integrity['v5_formal_inputs'])
dump(evd/'source-integrity.json',source_integrity)

module_receipt={'name':env['module']['name'],'version':env['module']['version'],
                'skill_sha256':resources[0]['sha256'],
                'reads':[{'path':str(root/x['uri']),'sha256':x['sha256']} for x in env['resources']]}
dump(evd/'module-receipt.json',module_receipt)

# Retain the two observed setup/contract failures, then record a fresh native success.
command=[python,str(module_root/'scripts/art_compile.py'),'validate',str(art_path)]
p=subprocess.run(command,text=True,capture_output=True)
assert p.returncode==0,(p.stdout,p.stderr)
native=json.loads(p.stdout)
assert native['status']=='STATIC_VALID'
compiled=base/'compiled-generic-video'
receipt=json.loads((compiled/'receipt.json').read_text())
assert receipt['validation']=='STATIC_VALID' and receipt['status']=='PLANNED' and receipt['media_acceptance']=='NOT_RUN' and receipt['submitted'] is False
assert receipt['art_sha256']==native['art_sha256']
dump(evd/'native-validator.json',{
 'status':'PASS','module_version':'1.3.1',
 'attempts':[
  {'interpreter':'/opt/homebrew/opt/python@3.12/libexec/bin/python3','exit_code':1,'result':'ModuleNotFoundError: No module named jsonschema','stage':'dependency_import'},
  {'interpreter':python,'exit_code':2,'result':'INVALID: Contract does not bind visible shot/asset: S1 /shots/0','stage':'initial_candidate'},
  {'interpreter':python,'exit_code':p.returncode,'command':command,'stdout':p.stdout,'stderr':p.stderr,'stage':'final_candidate'}],
 'art_file_sha256':sha(art_path),'art_object_sha256':native['art_sha256'],
 'compiled_package':{'uri':rel(compiled),'receipt_sha256':sha(compiled/'receipt.json'),
                     'status':receipt['status'],'submitted':receipt['submitted'],
                     'media_acceptance':receipt['media_acceptance'],'blockers':receipt['blockers']},
 'limitations':['STATIC_VALID validates structure and specified bindings; it does not observe images or video.',
                'The native ArtIR event schema requires DirectorIR shot phases; none exist, so DirectorIR timeline remains the sole action authority.']})

# Map each frozen V5 director semantic requirement to native ArtIR fields.
clause_ids={'D_RAIN':'A_RAIN','D_SINGLE_LETTER':'A_SINGLE_LETTER','D_ACTION_ORDER':'A_ORDER',
            'D_ENDING':'A_ENDING','D_EVENTS':'A_EVENTS','D_REVEAL_ORDER':'A_REVEAL'}
checks={
 'D_RAIN':[{'op':'contains','path':'/set/atmosphere','value':'雨夜'},{'op':'contains','path':'/world/region','value':'室内外'}],
 'D_SINGLE_LETTER':[{'op':'equals','path':'/assets/2/id','value':'PROP_LETTER'},{'op':'contains','path':'/assets/2/identity_locks/0','value':'只有 PROP_LETTER'}],
 'D_ACTION_ORDER':[{'op':'contains','path':'/contract/clauses/2/requirement','value':'交信完成后乙确认完整封口，确认后才收进'},{'op':'equals','path':'/shots/0/id','value':'S1'}],
 'D_ENDING':[{'op':'contains','path':'/contract/clauses/3/requirement','value':'收进乙背包即结束'},{'op':'contains','path':'/assets/2/design','value':'无字'}],
 'D_EVENTS':[{'op':'contains','path':'/contract/clauses/4/requirement','value':'三项来源事件'},{'op':'equals','path':'/shots/0/director_pointer','value':'/shots/0'}],
 'D_REVEAL_ORDER':[{'op':'contains','path':'/contract/clauses/5/requirement','value':'先见交接，再见封口完整，最后见'},{'op':'contains','path':'/shots/0/composition_support/occlusion','value':'关键时间点'}]
}
for group in checks.values():
    for c in group:
        actual=pointer(art,c['path'])
        assert (actual==c['value'] if c['op']=='equals' else c['value'] in actual),(c,actual)
handoffs=[]
for h in task['handoff']['required_handoffs']:
    suffix=h['id'].split(':',1)[1]
    assert suffix in clause_ids
    target_clause=clause_ids[suffix]
    assert target_clause in [c['id'] for c in art['contract']['clauses']]
    handoffs.append({'requirement_id':h['id'],'source_fingerprint':h['source_fingerprint'],
                     'target_clause':target_clause,'target_checks':checks[suffix],
                     'reason':'在原生 ArtIR 合同与资产/场景/逐镜支持字段保留导演硬要求；动作时点、控制权与结果继续以只读绑定的 DirectorIR /timeline/actions 为准。',
                     'source_paths':h['source_paths']})
dump(evd/'v5-handoff.json',{'status':'PASS','handoffs':handoffs,
                           'source_task_uri':rel(root/'runtime/tasks/TASK_0560d46ecc764c68ee9a590e.json'),
                           'director_v6_sha256':art['director']['sha256'],
                           'semantic_boundary':'No story event, camera, performance, or dialogue is authored by ArtIR.'})

# Exact V6 frozen slots/versions; mappings are evidence inside each artifact-level handoff.
source_for={i['slot']:i for i in env['inputs'] if i['slot']!='frozen_task'}
map_for={
 'canon:project:project:Canon':[
  {'source_pointer':'/content','target_pointers':['/sources/1','/contract/clauses/0']},
  {'source_pointer':'/entities/2/id','target_pointers':['/assets/2/entity_id','/contract/clauses/1']},
  {'source_pointer':'/event_order','target_pointers':['/contract/clauses/2','/contract/clauses/5']}],
 'director:project:project:DirectorIR':[
  {'source_pointer':'/scenes/0','target_pointers':['/set','/shots/0']},
  {'source_pointer':'/shots/0','target_pointers':['/shots/0']},
  {'source_pointer':'/timeline/actions','target_pointers':['/contract/clauses/2','/contract/clauses/4','/contract/clauses/5']}]
}
v6=[]
for h in env['handoffs']:
    source=source_for[h['source_slot']]
    src_obj=json.loads((root/source['uri']).read_text())
    mapping=map_for[h['source_slot']]
    for m in mapping:
        pointer(src_obj,m['source_pointer'])
        for tp in m['target_pointers']: pointer(art,tp)
    v6.append({**h,'source_uri':source['uri'],'source_sha256':source['sha256'],
               'target_uri':rel(art_path),'target_sha256':sha(art_path),
               'mapping':mapping,
               'evidence':[rel(evd/'source-integrity.json'),rel(evd/'v5-handoff.json'),rel(evd/'native-validator.json')]})
dump(evd/'v6-handoffs.json',{'status':'PASS','target_is_candidate_artifact':True,
                             'frozen_handoff_fields':['requirement_id','source_slot','source_version','target_slot','target_pointer','channel'],
                             'handoffs':v6})

check_evidence={
 'module_receipt':['source-integrity.json','module-receipt.json'],
 'native_validator':['native-validator.json'],
 'handoff':['v5-handoff.json','v6-handoffs.json','native-validator.json']}
check_findings={
 'module_receipt':'锁定模块版本、四份必读资源、V6 三份输入和 V5 原始输入字节哈希均一致。',
 'native_validator':'ArtIR 1.0 原生校验 STATIC_VALID；离线 generic-video 编译 PLANNED，媒体验收 NOT_RUN。',
 'handoff':'六条 V5 导演硬要求在 ArtIR 原生合同中保留；两条 V6 冻结上游按精确 slot/version 和候选 SHA 映射。'}
role_checks=[]; candidate_checks=[]
for v in env['validators']:
    id=v['id']; evidence=[rel(evd/n) for n in check_evidence[id]]
    role_checks.append({'id':id,'status':'PASS','finding':check_findings[id],'evidence':evidence})
    candidate_checks.append({'id':id,'status':'PASS','evidence':evidence})
role={
 'schema':'role-result/5.1','task_id':task['task_id'],'context_fingerprint':task['context_fingerprint'],
 'artifact':str(art_path),'artifact_sha256':sha(art_path),'complete':True,
 'checks':role_checks,'conflicts':[],'unresolved':[],
 'handoff':handoffs,'module_receipt':module_receipt,
 'validator':{'status':'STATIC_VALID','errors':[],'media':'NOT_RUN','professional_blind_review':'NOT_RUN'}
}
role_path=base/'role-result.json';dump(role_path,role)
result={
 'schema':'candidate-result/6.0','task_id':task['task_id'],'batch':env['batch'],
 'agent_id':'/root/host_bridge/v6_2dea6a2a9ca676085285dc07','input_digest':env['input_digest'],
 'artifacts':[{'kind':'ArtIR','slot':env['expected_artifacts'][0]['slot'],'uri':rel(art_path),'sha256':sha(art_path)}],
 'module_receipts':[{'name':env['module']['name'],'version':env['module']['version'],'sha256':env['module']['sha256']}],
 'checks':candidate_checks,
 'handoffs':[{'requirement_id':h['requirement_id'],'source_slot':h['source_slot'],'source_version':h['source_version'],
              'target_slot':h['target_slot'],'target_pointer':h['target_pointer'],'channel':h['channel'],
              'evidence':[rel(evd/'v6-handoffs.json'),rel(evd/'v5-handoff.json')]} for h in env['handoffs']],
 'result_uri':rel(role_path),'result_sha256':sha(role_path),'unresolved':[]
}
result_path=base/'candidate-result.json';dump(result_path,result)
print(json.dumps({'status':'READY_FOR_REVIEW','result_uri':rel(result_path),'result_sha256':sha(result_path),
                  'role_result_sha256':sha(role_path),'art_sha256':sha(art_path),
                  'native':native['status'],'compiled_status':receipt['status'],'media':receipt['media_acceptance']},ensure_ascii=False,indent=2))
