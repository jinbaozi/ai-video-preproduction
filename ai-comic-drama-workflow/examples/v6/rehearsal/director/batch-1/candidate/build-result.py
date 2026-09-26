"""Package this DirectorIR as the frozen V5 and V6 candidate contracts."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_b1e7ff7ce83d7a32bfa09935/1'
EVIDENCE = OUT / 'evidence'
PREFIX = 'runtime/v6/candidates/TASK_b1e7ff7ce83d7a32bfa09935/1/'
MODULE = ROOT / 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
HANDOFF = ROOT / 'runtime/v6/candidates/TASK_1b94794070565f70c7f697a7/1/compiled/director-handoff.json'
V5_TASK = ROOT / 'runtime/tasks/TASK_b1e7ff7ce83d7a32bfa09935.json'
ACTION_FILE = ROOT.parent / 'screenplay-review-submit-output.json'
WORKFLOW_SRC = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/src')
sys.path.insert(0, str(WORKFLOW_SRC))
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_handoff import validate_handoff
from ai_comic_drama_workflow.v5_modules import native_validate
from ai_comic_drama_workflow.v5_protocol import validate_protocol as validate_v5
from ai_comic_drama_workflow.v6_protocol import envelope_input_digest, validate_v6_protocol

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

screenplay_protocol = load_module('screenplay_protocol_for_result', MODULE / 'scripts/screenplay_protocol.py')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')

def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()

def rel(path):
    return str(Path(path).relative_to(ROOT))

def evidence_uri(name):
    return PREFIX + 'evidence/' + name

action = read(ACTION_FILE)['actions'][0]
message = action['arguments']['message']
envelope = json.loads(message.split('Frozen task envelope:\n', 1)[1])
assert action['candidate_dir'] == str(OUT)
assert envelope['task_id'] == 'TASK_b1e7ff7ce83d7a32bfa09935'
assert envelope['input_digest'] == envelope_input_digest(envelope)
task = read(V5_TASK)
ir_path = OUT / 'director-ir.json'
map_path = OUT / 'screenplay-map.json'
ir = read(ir_path)
mapping = read(map_path)
script_path = ROOT / 'runtime/v6/candidates/TASK_1b94794070565f70c7f697a7/1/script-ir.json'
script = read(script_path)
handoff = read(HANDOFF)

input_rows=[]
for item in envelope['inputs']:
    path = ROOT / item['uri']
    actual = digest(path)
    assert actual == item['sha256'], (item['slot'], actual, item['sha256'])
    input_rows.append({**item, 'actual_sha256':actual, 'verified':True})
resource_rows=[]
for item in envelope['resources']:
    path = ROOT / item['uri']
    actual = digest(path)
    assert actual == item['sha256'], item['uri']
    resource_rows.append({**item, 'actual_sha256':actual, 'verified':True})
assert task['module']['name'] == envelope['module']['name']
assert task['module']['version'] == envelope['module']['version']
assert task['module']['sha256'] == envelope['module']['sha256']
assert task['context_fingerprint'] == 'b1e7ff7ce83d7a32bfa0993532a1fdf7f529653d03ea535d009294c751121012'
assert handoff['ready'] and handoff['content_sha256'] == mapping['screenplay_sha256']

write(EVIDENCE / 'source-integrity.json', {
    'status':'PASS','action_id':action['action_id'],'task_id':envelope['task_id'],
    'input_digest':envelope['input_digest'],'input_revision':envelope['input_revision'],
    'inputs':input_rows,'resources':resource_rows,
    'canon_facts':['FACT_RAIN_NIGHT','FACT_HANDOFF','FACT_SEAL','FACT_STOW'],
    'script_events':['EVT_HANDOFF','EVT_SEAL_CHECK','EVT_STOW'],
    'script_review_status':script['review']['status'],
    'scope_boundary':'来源未给具体地点/内外、人物外观关系、动机、信件内容、对白、时长或后续。'})

reads=[]
for required in task['module']['required_reads']:
    actual=digest(required['path'])
    assert actual == required['sha256']
    reads.append({'path':required['path'],'sha256':actual})
receipt={'name':task['module']['name'],'version':task['module']['version'],
         'skill_sha256':task['module']['skill_sha256'],'reads':reads}
assert receipt['skill_sha256'] == digest(MODULE/'SKILL.md')
write(EVIDENCE/'module-receipt.json', {
    'status':'PASS','module_receipt':receipt,'v6_module_receipt':envelope['module'],
    'read_count':len(reads),'source_integrity_evidence':evidence_uri('source-integrity.json'),
    'meaning':'收据只证明锁定版本和资源字节已读取，不代表独立专业盲评。'})

venv_python = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/.venv/bin/python')
command=[str(venv_python),str(MODULE/'scripts/dg.py'),'validate',str(ir_path),
         '--screenplay-handoff',str(HANDOFF),'--screenplay-map',str(map_path)]
proc=subprocess.run(command,capture_output=True,text=True,check=False)
report=json.loads(proc.stdout)
assert proc.returncode == 0 and report['status']=='STATIC_VALID' and not report['errors'], report
native_report=native_validate('director',ir_path,lambda name: MODULE)
assert native_report['status']=='STATIC_VALID' and not native_report['errors'], native_report
assert mapping['director_sha256'] == screenplay_protocol.content_hash(ir)
assert not screenplay_protocol.validate_mapping(ir,handoff['requirements'],mapping,handoff['content_sha256'])
write(EVIDENCE/'native-validator.json', {
    'status':'PASS','validator':'locked director-grammar/scripts/dg.py validate',
    'command':command,'returncode':proc.returncode,'report':report,
    'v5_native_validate':native_report,'artifact_uri':rel(ir_path),'artifact_sha256':digest(ir_path),
    'screenplay_map_uri':rel(map_path),'screenplay_map_sha256':digest(map_path),
    'actual_media':'NOT_RUN','professional_blind_review':'NOT_RUN'})

required={item['id']:item for item in task['handoff']['required_handoffs']}
assert set(required)=={item['requirement_id'] for item in mapping['mappings']}
stamp={key:mapping[key] for key in ('screenplay_sha256','director_sha256','reviewer','findings')}
v5_handoff=[{**row,'review':stamp} for row in mapping['mappings']]
validate_handoff('director',ir,task['handoff']['required_handoffs'],v5_handoff,
                 screenplay=(script,screenplay_protocol))
write(EVIDENCE/'v5-handoff.json', {
    'status':'PASS','schema':'screenplay-director-map/1.0',
    'screenplay_sha256':mapping['screenplay_sha256'],'director_sha256':mapping['director_sha256'],
    'requirements':[{'requirement_id':row['requirement_id'],
                     'source_fingerprint':row['source_fingerprint'],
                     'target_clause':row['target_clause'],
                     'target_checks':row['target_checks'],'reason':row['reason']}
                    for row in mapping['mappings']],
    'validation':'V5 validate_handoff and locked screenplay_protocol.validate_mapping returned no errors',
    'semantic_review_owner':'current director agent; no independent blind review claimed'})

v6_handoffs=[]
for h in envelope['handoffs']:
    source=next(x for x in envelope['inputs'] if x['slot']==h['source_slot'])
    mapping_pointers=([
        {'source_pointer':'/source_requirements/0','target_pointers':['/scenes/0/space','/contract/clauses/0']},
        {'source_pointer':'/source_requirements/1','target_pointers':['/entities/2','/timeline/actions','/contract/clauses/1']},
        {'source_pointer':'/source_requirements/2','target_pointers':['/beats','/timeline/actions','/contract/clauses/2']}
    ] if h['source_slot'].startswith('canon:') else [
        {'source_pointer':'/contract/clauses','target_pointers':['/contract/clauses','/timeline/actions','/shots/0/narrative']},
        {'source_pointer':'/narrative/reveal_order','target_pointers':['/beats','/timeline/actions/4/depends_on']},
        {'source_pointer':'/narrative/ending','target_pointers':['/shots/0/narrative/audience_after/2','/shots/0/end_state/2']}
    ])
    v6_handoffs.append({**h,'source_uri':source['uri'],'source_sha256':source['sha256'],
                        'target_uri':rel(ir_path),'target_sha256':digest(ir_path),
                        'mapping':mapping_pointers,
                        'evidence':[evidence_uri('v5-handoff.json'),evidence_uri('native-validator.json')]})
write(EVIDENCE/'v6-handoffs.json', {'status':'PASS','handoffs':v6_handoffs,
                                   'frozen_handoff_fields':['requirement_id','source_slot','source_version',
                                                            'target_slot','target_pointer','channel'],
                                   'target_is_candidate_artifact':True})

write(EVIDENCE/'director-review.json', {
    'status':'SOURCE_BOUND_STATIC_REVIEW','artifact_sha256':digest(ir_path),
    'reviewer':'/root/host_bridge/v6_06e72da81da7989f0b415f37',
    'source_facts_preserved':[
        {'fact':'雨夜','target':['/scenes/0/space','/shots/0/sound/ambience','/contract/clauses/0']},
        {'fact':'甲交一封未拆信给乙','target':['/timeline/actions/0','/timeline/actions/1','/timeline/actions/2','/contract/clauses/1']},
        {'fact':'乙确认该信封口完整','target':['/timeline/actions/3','/timeline/performances/2','/contract/clauses/2']},
        {'fact':'乙确认后把同一封信收进背包','target':['/timeline/actions/4','/shots/0/end_state/2','/contract/clauses/3']}],
    'design_additions':['单镜固定机位','甲乙相对站位','右手交接和乙左手保持背包开口',
                        '12 秒/24fps/16:9 暂定预算','用于预演的世界坐标和画面框'],
    'boundary_checks':['未补地点或室内外','未补人物外观与关系','未补动机和信件内容',
                       '无对白、开封、额外人物和后续事件'],
    'state_checkpoints_ms':[0,2500,4000,7500,10500,12000],
    'actual_video_or_audio':'NOT_RUN','G3':'NOT_RUN','G4':'NOT_RUN',
    'limitation':'静态合同与语义复核不证明生成媒体已经满足镜头。'})

write(EVIDENCE/'contract-assistance.json', {
    'agent_id':'/root/host_bridge/v6_06e72da81da7989f0b415f37/contracts',
    'role':'只读契约核对；未写候选或正式状态，未担任独立 reviewer',
    'original_advice_summary':[
        'V5 RoleResult 需六条 screenplay 语义 handoff，逐条包含源指纹、原生 hard clause、target_checks、reason 和相同 review stamp。',
        'V6 candidate-result 需两条冻结 predecessor handoff；module_receipts 必须逐字段等于冻结 V6 module。',
        'V5 module_receipt 需 name/version/skill_sha256 和四份必读资源的 path/sha256；原生 dg.py validate 应带 screenplay handoff/map。',
        'V5 native_validate 与 V5 validate_handoff 是两个不同检查；V6 result URI/hash、输出 slot 和 evidence 需与 envelope 绑定。'],
    'reported_sources':[
        'locked director-grammar/references/cooperation-v5.md:15-25',
        'locked director-grammar/references/screenplay-handoff.md:5-17',
        'locked director-grammar/scripts/screenplay_protocol.py:212-245',
        'ai_comic_drama_workflow/v5_handoff.py:73-84',
        'ai_comic_drama_workflow/v5.py:684-700',
        'ai_comic_drama_workflow/v6_kernel.py:481-490'],
    'my_verification':[
        '我亲自读取上述锁定契约、V5/V6 代码和两个 Schema；字段要求相符。',
        '我独自编写 DirectorIR 和两层交接；原生 dg.py 与 V5 handoff 检查已返回通过。',
        'contracts 辅代理建议仅用于契约核对，不作为独立专业盲评证据。'],
    'status':'READ_ONLY_ADVICE_VERIFIED_BY_AUTHOR'})

check_evidence={
    'module_receipt':[evidence_uri('source-integrity.json'),evidence_uri('module-receipt.json')],
    'native_validator':[evidence_uri('native-validator.json'),evidence_uri('director-review.json')],
    'handoff':[evidence_uri('v5-handoff.json'),evidence_uri('v6-handoffs.json')]}
role_checks=[{'id':cid,'status':'PASS','evidence':uris,
              'finding':{'module_receipt':'锁定模块版本、必读资源和输入字节哈希一致。',
                         'native_validator':'锁定 DirectorIR 1.2 原生验证及 screenplay handoff/map 均为 STATIC_VALID。',
                         'handoff':'六条 V5 编剧语义映射及两条 V6 冻结上游绑定已逐项核对。'}[cid]}
             for cid,uris in check_evidence.items()]
role={
    'schema':'role-result/5.1','task_id':envelope['task_id'],
    'context_fingerprint':task['context_fingerprint'],
    'artifact':str(ir_path),'artifact_sha256':digest(ir_path),
    'checks':role_checks,'complete':True,'conflicts':[],'unresolved':[],
    'handoff':v5_handoff,'module_receipt':receipt,
    'validator':{'status':'STATIC_VALID','errors':[],
                 'screenplay_binding':report['screenplay_binding'],
                 'media':'NOT_RUN','professional_blind_review':'NOT_RUN'}}
validate_v5('role-result',role)

class ReceiptAuditShim:
    audit_required = lambda self: True
    receipt_audit = V5Kernel.receipt_audit

assert ReceiptAuditShim().receipt_audit(task,role)=='audited'
write(OUT/'role-result.json',role)

candidate={
    'schema':'candidate-result/6.0','task_id':envelope['task_id'],'batch':envelope['batch'],
    'agent_id':'/root/host_bridge/v6_06e72da81da7989f0b415f37',
    'input_digest':envelope['input_digest'],
    'result_uri':rel(OUT/'role-result.json'),
    'result_sha256':digest(OUT/'role-result.json'),
    'artifacts':[{'slot':'director:project:project:DirectorIR','kind':'DirectorIR',
                  'uri':rel(ir_path),'sha256':digest(ir_path)}],
    'module_receipts':[envelope['module']],
    'checks':[{'id':cid,'status':'PASS','evidence':uris} for cid,uris in check_evidence.items()],
    'handoffs':[{**h,'evidence':[evidence_uri('v6-handoffs.json'),evidence_uri('v5-handoff.json')]}
                for h in envelope['handoffs']],
    'unresolved':[]}
validate_v6_protocol('candidate-result',candidate)
assert candidate['module_receipts']==[envelope['module']]
assert {h['requirement_id'] for h in candidate['handoffs']}=={h['requirement_id'] for h in envelope['handoffs']}
assert {c['id'] for c in candidate['checks']}=={v['id'] for v in envelope['validators']}
write(OUT/'candidate-result.json',candidate)

write(EVIDENCE/'package-check.json', {
    'status':'PASS','v5_role_schema':'PASS','v5_module_receipt':'audited',
    'v5_native_validator':native_report['status'],'v5_handoff':'PASS',
    'v6_candidate_schema':'PASS','v6_input_digest':'PASS','v6_check_ids':'PASS',
    'v6_handoff_ids':'PASS','v6_module_receipts':'PASS',
    'artifact_sha256':digest(ir_path),'role_result_sha256':digest(OUT/'role-result.json'),
    'candidate_result_sha256':digest(OUT/'candidate-result.json'),
    'formal_project_state_modified':False})
print(json.dumps({'candidate':str(OUT/'candidate-result.json'),
                  'candidate_sha256':digest(OUT/'candidate-result.json'),
                  'director_ir_sha256':digest(ir_path),
                  'role_result_sha256':digest(OUT/'role-result.json')},ensure_ascii=False))
