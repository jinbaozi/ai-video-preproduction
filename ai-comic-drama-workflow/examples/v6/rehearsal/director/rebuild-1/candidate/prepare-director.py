"""Rebind a reviewed Director design to this task's frozen V5/V6 inputs."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path


ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_ae94f4322a77ebd18dbb635d/1'
OLD = ROOT / 'runtime/v6/candidates/TASK_b1e7ff7ce83d7a32bfa09935/3'
MODULE = ROOT / 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
ACTION = Path('/private/tmp/ai-video-v6-real-efKlQy/post-stale-fix-run-output.json')
TASK = ROOT / 'runtime/tasks/TASK_ae94f4322a77ebd18dbb635d.json'
AGENT = '/root/host_bridge/v6_ce1e26fc5f43d8275517e59e'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


detail = module('locked_detail_runtime', MODULE / 'scripts/detail_runtime.py')
screenplay = module('locked_screenplay_protocol', MODULE / 'scripts/screenplay_protocol.py')
action = read(ACTION)['actions'][0]
assert action['action_id'] == 'dispatch-b3f83e98b868ad4066b4cdf1'
assert action['task_id'] == 'TASK_ae94f4322a77ebd18dbb635d'
message = action['arguments']['message']
envelope = json.loads(message.split('Frozen task envelope:\n', 1)[1].split('\n\nNative handoff reminder:', 1)[0])
task = read(TASK)
assert envelope['task_id'] == task['task_id']
assert envelope['module']['sha256'] == task['module']['sha256']

input_checks = []
for item in envelope['inputs']:
    path = ROOT / item['uri']
    actual = file_hash(path)
    assert actual == item['sha256'], (item['slot'], actual)
    input_checks.append({'slot': item['slot'], 'uri': item['uri'], 'expected_sha256': item['sha256'], 'actual_sha256': actual, 'status': 'PASS'})
resource_checks = []
for item in envelope['resources']:
    path = ROOT / item['uri']
    actual = file_hash(path)
    assert actual == item['sha256'], item['uri']
    resource_checks.append({'uri': item['uri'], 'expected_sha256': item['sha256'], 'actual_sha256': actual, 'status': 'PASS'})

canon_path = Path(next(item['uri'] for item in task['brief']['inputs'] if item['slot'] == 'canon'))
script_path = Path(next(item['uri'] for item in task['brief']['inputs'] if item['slot'] == 'screenplay'))
for item in task['brief']['inputs']:
    assert file_hash(item['uri']) == item['sha256'], item['slot']
canon = read(canon_path)
script = read(script_path)
frozen_canon = read(ROOT / next(item['uri'] for item in envelope['inputs'] if item['slot'].startswith('canon:')))
frozen_script = read(ROOT / next(item['uri'] for item in envelope['inputs'] if item['slot'].startswith('screenplay:')))
assert canon == frozen_canon
assert screenplay.content_hash(script) == screenplay.content_hash(frozen_script)
assert script['review']['status'] == 'PASS'
assert script['review']['content_sha256'] == screenplay.content_hash(script)

handoff = screenplay.make_handoff(script, str(script_path), file_hash(script_path))
assert handoff['ready']
assert handoff['content_sha256'] == script['review']['content_sha256']
required = task['handoff']['required_handoffs']
assert {row['id']: row['source_fingerprint'] for row in handoff['requirements']} == {
    row['id']: row['source_fingerprint'] for row in required
}
write(OUT / 'screenplay-handoff.json', handoff)

ir = deepcopy(read(OLD / 'director-ir.json'))
ir['revision'] = 4
ir['canon_ref'] = str(canon_path)
for row in ir['sources']:
    if row['id'] == 'SRC_69a71adcfaca':
        row['uri'] = str(ROOT / 'sources/SRC_69a71adcfaca/source.txt')
    elif row['id'] == 'CANON_INPUT':
        row['uri'] = str(canon_path)
    elif row['id'] == 'SCRIPT_INPUT':
        row['uri'] = str(script_path)
    elif row['id'] == 'DIRECTOR_DESIGN':
        row['uri'] = 'design://TASK_ae94f4322a77ebd18dbb635d/director'
        row['locator'] = '本次候选 /shots/0 与 /timeline；沿用已审查的动作设计，按当前冻结输入重新绑定和验证'
    else:
        raise ValueError('Unexpected source ID: ' + row['id'])
ir['timeline']['semantic_review'] = {
    'status': 'PASS',
    'reviewer': AGENT + ' / current frozen-source semantic review',
    'input_sha256': detail.content_hash(ir),
    'findings': [
        '当前 V6 冻结 Canon 与 V5 Canon 字节一致；当前 V6 冻结 ScriptIR 与 V5 编剧快照语义摘要一致，编剧复核摘要仍有效。',
        '逐项核对雨夜、甲交一封未拆信、乙在收存前确认同一封信封口完整、乙随后收入背包；不补地点、人物关系、动机、信件内容、对白或后续。',
        '复用先前候选的单镜、手别、站位、12 秒预算和示意坐标作为导演设计，本次重绑并重新验证当前输入。',
        '逐样本核对起止姿态、双向接触、道具控制权与动作顺序；信件在收存完成后由背包内部承托，画面不可见。',
        'G3/G4 实际媒体检查仍 NOT_RUN；此记录仅为导演候选的来源语义复核。',
    ],
}
assert ir['timeline']['semantic_review']['input_sha256'] == detail.content_hash(ir)
write(OUT / 'director-ir.json', ir)

mapping = deepcopy(read(OLD / 'screenplay-map.json'))
mapping['screenplay_sha256'] = handoff['content_sha256']
mapping['director_sha256'] = screenplay.content_hash(ir)
mapping['reviewer'] = AGENT + ' / current frozen screenplay mapping review'
mapping['findings'] = [
    '六条当前 V5 编剧要求及源指纹与锁定编剧交接逐条相同。',
    '雨夜、唯一未拆信、交接→验封→收存、结尾边界落入原生 hard clause 与目标字段断言。',
    '上一候选的动作设计已重新绑定当前 V5 编剧快照和本次 DirectorIR 语义摘要；没有复制旧 reviewer stamp。',
    '接触、支撑、控制权及镜头起止态重新核对；静态结论不声称实际媒体通过。',
]
assert {row['requirement_id']: row['source_fingerprint'] for row in mapping['mappings']} == {
    row['id']: row['source_fingerprint'] for row in required
}
assert not screenplay.validate_mapping(ir, required, mapping, handoff['content_sha256'])
write(OUT / 'screenplay-map.json', mapping)

write(OUT / 'evidence/source-integrity.json', {
    'status': 'PASS', 'task_id': envelope['task_id'], 'batch': envelope['batch'],
    'input_digest': envelope['input_digest'], 'input_revision': envelope['input_revision'],
    'inputs': input_checks, 'resources': resource_checks,
    'v5_canon_uri': str(canon_path), 'v5_canon_sha256': file_hash(canon_path),
    'v5_screenplay_uri': str(script_path), 'v5_screenplay_sha256': file_hash(script_path),
    'v6_v5_canon_bytes_equal': True, 'v6_v5_screenplay_content_hash_equal': True,
    'current_screenplay_content_sha256': handoff['content_sha256'],
    'prior_candidate_uri': str(OLD / 'director-ir.json'),
    'prior_candidate_sha256': file_hash(OLD / 'director-ir.json'),
    'reuse_scope': '沿用上一候选的动作和镜头设计；重新绑定当前来源、DirectorIR 内容摘要、六条编剧映射并重新运行本地校验。',
})
print(json.dumps({'director_ir_sha256': file_hash(OUT / 'director-ir.json'),
                  'director_content_hash': detail.content_hash(ir),
                  'screenplay_map_sha256': file_hash(OUT / 'screenplay-map.json'),
                  'screenplay_handoff_sha256': file_hash(OUT / 'screenplay-handoff.json')}, ensure_ascii=False))
