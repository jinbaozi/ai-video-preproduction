"""Validate and package this Director candidate without changing formal state."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_ae94f4322a77ebd18dbb635d/1'
EVIDENCE = OUT / 'evidence'
OLD = ROOT / 'runtime/v6/candidates/TASK_b1e7ff7ce83d7a32bfa09935/3'
PREFIX = 'runtime/v6/candidates/TASK_ae94f4322a77ebd18dbb635d/1/'
MODULE = ROOT / 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
V5_TASK = ROOT / 'runtime/tasks/TASK_ae94f4322a77ebd18dbb635d.json'
AGENT = '/root/host_bridge/v6_ce1e26fc5f43d8275517e59e'
WORKFLOW_SRC = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/src')
VENV_PYTHON = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/.venv/bin/python')
sys.path.insert(0, str(WORKFLOW_SRC))
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_handoff import validate_handoff
from ai_comic_drama_workflow.v5_modules import native_validate
from ai_comic_drama_workflow.v5_protocol import validate_protocol as validate_v5
from ai_comic_drama_workflow.v6_protocol import envelope_input_digest, validate_v6_protocol


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).relative_to(ROOT))


def evidence(name):
    return PREFIX + 'evidence/' + name


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


screenplay = module('locked_screenplay_protocol_for_result', MODULE / 'scripts/screenplay_protocol.py')
detail = module('locked_detail_runtime_for_result', MODULE / 'scripts/detail_runtime.py')
state = read(ROOT / 'runtime/v6/state.json')['tasks']['TASK_ae94f4322a77ebd18dbb635d']
envelope = state['envelope']
receipt = state['receipt']
task = read(V5_TASK)
assert state['state'] == 'RUNNING'
assert envelope['batch'] == receipt['batch'] == 1
assert receipt['action_id'] == receipt['dispatch_id'] == 'dispatch-b3f83e98b868ad4066b4cdf1'
assert receipt['agent_id'] == AGENT and receipt['status'] == 'RUNNING'
assert envelope['input_digest'] == envelope_input_digest(envelope)
assert envelope['task_id'] == task['task_id']
for item in envelope['inputs'] + envelope['resources']:
    assert file_hash(ROOT / item['uri']) == item['sha256'], item['uri']
assert read(EVIDENCE / 'source-integrity.json')['input_digest'] == envelope['input_digest']

ir_path = OUT / 'director-ir.json'
map_path = OUT / 'screenplay-map.json'
handoff_path = OUT / 'screenplay-handoff.json'
ir = read(ir_path)
mapping = read(map_path)
handoff = read(handoff_path)
script = read(next(item['uri'] for item in task['brief']['inputs'] if item['slot'] == 'screenplay'))
assert screenplay.review_valid(script)
assert handoff['ready'] and handoff['content_sha256'] == screenplay.content_hash(script)
assert detail.semantic_status(ir)
assert mapping['director_sha256'] == screenplay.content_hash(ir)
assert not screenplay.validate_mapping(ir, handoff['requirements'], mapping, handoff['content_sha256'])
assert {row['id']: row['source_fingerprint'] for row in handoff['requirements']} == {
    row['id']: row['source_fingerprint'] for row in task['handoff']['required_handoffs']
}

reads = []
for item in task['module']['required_reads']:
    actual = file_hash(item['path'])
    assert actual == item['sha256']
    reads.append({'path': item['path'], 'sha256': actual})
module_receipt = {
    'name': task['module']['name'], 'version': task['module']['version'],
    'skill_sha256': task['module']['skill_sha256'], 'reads': reads,
}
assert module_receipt['skill_sha256'] == file_hash(MODULE / 'SKILL.md')
write(EVIDENCE / 'module-receipt.json', {
    'status': 'PASS', 'module_receipt': module_receipt,
    'v6_module_receipt': envelope['module'],
    'meaning': '仅证明锁定字节对应；具体落实另由原生校验和独立审阅检查。',
})

command = [str(VENV_PYTHON), str(MODULE / 'scripts/dg.py'), 'validate', str(ir_path),
           '--screenplay-handoff', str(handoff_path), '--screenplay-map', str(map_path)]
process = subprocess.run(command, capture_output=True, text=True, check=False)
report = json.loads(process.stdout)
assert process.returncode == 0 and report['status'] == 'STATIC_VALID' and not report['errors'], report
native = native_validate('director', ir_path, lambda name: MODULE)
assert native['status'] == 'STATIC_VALID' and not native['errors'], native
write(EVIDENCE / 'native-validator.json', {
    'status': 'PASS', 'command': command, 'returncode': process.returncode,
    'locked_report': report, 'v5_native_report': native,
    'artifact_uri': relative(ir_path), 'artifact_sha256': file_hash(ir_path),
    'screenplay_handoff_uri': relative(handoff_path), 'screenplay_handoff_sha256': file_hash(handoff_path),
    'screenplay_map_uri': relative(map_path), 'screenplay_map_sha256': file_hash(map_path),
    'actual_media': 'NOT_RUN', 'independent_review': 'PENDING',
})

review_stamp = {key: mapping[key] for key in ('screenplay_sha256', 'director_sha256', 'reviewer', 'findings')}
v5_handoff = [{**row, 'review': review_stamp} for row in mapping['mappings']]
validate_handoff('director', ir, task['handoff']['required_handoffs'], v5_handoff,
                 screenplay=(script, screenplay))
write(EVIDENCE / 'v5-handoff.json', {
    'status': 'PASS', 'requirement_count': len(v5_handoff),
    'requirement_ids': [row['requirement_id'] for row in v5_handoff],
    'screenplay_sha256': mapping['screenplay_sha256'],
    'director_sha256': mapping['director_sha256'],
    'target_assertions': [{'requirement_id': row['requirement_id'],
                           'source_fingerprint': row['source_fingerprint'],
                           'target_clause': row['target_clause'],
                           'target_checks': row['target_checks'], 'reason': row['reason']}
                          for row in mapping['mappings']],
    'validation': 'V5 validate_handoff and locked screenplay validate_mapping passed.',
    'independent_review': 'PENDING',
})

samples = {row['at_ms']: row['entities'] for row in ir['timeline']['state_samples']}
assert sorted(samples) == [0, 2500, 4000, 7500, 10500, 12000]
contact_pairs = [
    ('CHAR_JIA', 'PROP_LETTER', 'PROP_LETTER.body', 'CHAR_JIA.right_hand'),
    ('CHAR_YI', 'PROP_LETTER', 'PROP_LETTER.body', 'CHAR_YI.right_hand'),
    ('CHAR_YI', 'PROP_BACKPACK', 'PROP_BACKPACK.body', 'CHAR_YI.body'),
    ('CHAR_YI', 'PROP_BACKPACK', 'PROP_BACKPACK.opening', 'CHAR_YI.left_hand'),
    ('PROP_LETTER', 'PROP_BACKPACK', 'PROP_BACKPACK.interior', 'PROP_LETTER.body'),
]
state_rows = []
for at in sorted(samples):
    entities = samples[at]
    for left, right, left_contact, right_contact in contact_pairs:
        assert (left_contact in entities[left]['contacts']) == (right_contact in entities[right]['contacts']), (at, left, right)
    letter = entities['PROP_LETTER']
    assert len(letter['controllers']) <= 1
    assert all(controller in letter['contacts'] for controller in letter['controllers'])
    state_rows.append({'at_ms': at, 'jia_pose': entities['CHAR_JIA']['pose'],
                       'yi_pose': entities['CHAR_YI']['pose'],
                       'letter_pose': letter['pose'],
                       'letter_contacts': letter['contacts'],
                       'letter_supports': letter['supports'],
                       'letter_controllers': letter['controllers'],
                       'reciprocal_contact': 'PASS'})
assert samples[0]['PROP_LETTER']['controllers'] == ['CHAR_JIA.right_hand']
assert samples[2500]['PROP_LETTER']['controllers'] == ['CHAR_JIA.right_hand']
assert samples[4000]['PROP_LETTER']['controllers'] == ['CHAR_YI.right_hand']
assert samples[7500]['PROP_LETTER']['controllers'] == ['CHAR_YI.right_hand']
for at in (10500, 12000):
    assert samples[at]['PROP_LETTER']['controllers'] == []
    assert samples[at]['PROP_LETTER']['supports'] == ['PROP_BACKPACK.interior']
    assert samples[at]['PROP_LETTER']['visible_parts'] == []
    assert '不再持信' in samples[at]['CHAR_JIA']['pose']
changes = sorted((delta for action in ir['timeline']['actions'] for delta in action['changes']),
                 key=lambda delta: delta['at_ms'])
replay = deepcopy(samples[0])
index = 0
for at in sorted(samples):
    while index < len(changes) and changes[index]['at_ms'] <= at:
        delta = changes[index]
        entity = replay[delta['entity_id']]
        assert entity[delta['field']] == delta['before'], (at, delta)
        entity[delta['field']] = deepcopy(delta['after'])
        index += 1
    assert replay == samples[at], at
assert index == len(changes)
for label, at in (('start_state', 0), ('end_state', 12000)):
    legacy = {row['entity_id']: row for row in ir['shots'][0][label]}
    assert set(legacy) == set(samples[at])
    for entity_id, value in samples[at].items():
        x, y, z = value['position']
        assert legacy[entity_id]['position_m'] == [x, z, y]
        assert legacy[entity_id]['pose'] == value['pose']
        assert legacy[entity_id]['contact'] == ('；'.join(value['contacts']) or '无接触')
        assert legacy[entity_id]['support'] == ('；'.join(value['supports']) or '不适用')
assert script['narrative']['reveal_order'] == ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW']
assert [a['semantic_id'] for a in ir['timeline']['actions']] == [
    'EVT_HANDOFF', 'EVT_HANDOFF', 'EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW'
]
write(EVIDENCE / 'state-consistency.json', {
    'status': 'PASS', 'artifact_uri': relative(ir_path), 'artifact_sha256': file_hash(ir_path),
    'samples': state_rows, 'action_delta_replay': 'PASS',
    'shot_start_matches_0_ms': True, 'shot_end_matches_12000_ms': True,
    'one_unopened_letter_in_backpack_at_end': True,
    'script_reveal_order': script['narrative']['reveal_order'],
    'independent_review': 'PENDING',
})

previous = task['previous']
promoted_path = ROOT / previous['uri']
promoted_ir = read(promoted_path)
old_map = read(OLD / 'screenplay-map.json')
old_map_stamp = old_map['director_sha256']
old_promoted_map_hash = screenplay.content_hash(promoted_ir)
old_promoted_semantic_hash = detail.content_hash(promoted_ir)
old_promoted_review_hash = promoted_ir['timeline']['semantic_review']['input_sha256']
assert old_map_stamp == old_promoted_map_hash
assert old_promoted_review_hash != old_promoted_semantic_hash
write(EVIDENCE / 'prior-stamp-difference.json', {
    'status': 'OBSERVED', 'prior_candidate_uri': relative(OLD / 'director-ir.json'),
    'prior_candidate_sha256': file_hash(OLD / 'director-ir.json'),
    'prior_mapping_director_sha256': old_map_stamp,
    'prior_promoted_uri': previous['uri'],
    'prior_promoted_sha256': file_hash(promoted_path),
    'prior_promoted_mapping_content_sha256': old_promoted_map_hash,
    'prior_promoted_semantic_review_input_sha256': old_promoted_review_hash,
    'prior_promoted_current_semantic_content_sha256': old_promoted_semantic_hash,
    'difference': 'V5 snapshot relocated source URIs; the old promoted DirectorIR retained its pre-promotion semantic-review stamp.',
    'current_candidate_map_sha256': mapping['director_sha256'],
    'current_candidate_ir_sha256': file_hash(ir_path),
    'note': '当前候选的 stamp 仅绑定本次候选；未预造未来 V5 snapshot 的 hash。',
})

v6_handoffs = []
for item in envelope['handoffs']:
    source = next(row for row in envelope['inputs'] if row['slot'] == item['source_slot'])
    target_pointers = (
        ['/scenes/0/space', '/contract/clauses/0', '/timeline/actions', '/shots/0/end_state']
        if item['source_slot'].startswith('canon:') else
        ['/contract/clauses', '/beats', '/timeline/actions', '/shots/0/narrative']
    )
    v6_handoffs.append({**item, 'source_uri': source['uri'], 'source_sha256': source['sha256'],
                        'target_uri': relative(ir_path), 'target_sha256': file_hash(ir_path),
                        'target_pointers': target_pointers,
                        'evidence': [evidence('source-integrity.json'), evidence('v5-handoff.json'),
                                     evidence('state-consistency.json')]})
write(EVIDENCE / 'v6-handoffs.json', {
    'status': 'PASS', 'handoffs': v6_handoffs,
    'bound_input_digest': envelope['input_digest'], 'bound_artifact_sha256': file_hash(ir_path),
})

check_evidence = {
    'module_receipt': [evidence('source-integrity.json'), evidence('module-receipt.json')],
    'native_validator': [evidence('native-validator.json'), evidence('state-consistency.json')],
    'handoff': [evidence('v5-handoff.json'), evidence('v6-handoffs.json'),
                evidence('prior-stamp-difference.json')],
}
role_checks = [{'id': check_id, 'status': 'PASS', 'evidence': uris,
                'finding': {'module_receipt': '当前冻结输入和锁定模块字节验证通过。',
                            'native_validator': '锁定 DirectorIR 1.2 校验与当前编剧交接为 STATIC_VALID。',
                            'handoff': '当前六条 V5 编剧映射及两条 V6 上游交接逐项核对。'}[check_id]}
               for check_id, uris in check_evidence.items()]
role = {
    'schema': 'role-result/5.1', 'task_id': task['task_id'],
    'context_fingerprint': task['context_fingerprint'],
    'artifact': str(ir_path), 'artifact_sha256': file_hash(ir_path),
    'checks': role_checks, 'complete': True, 'conflicts': [], 'unresolved': [],
    'handoff': v5_handoff, 'module_receipt': module_receipt,
    'validator': {'status': report['status'], 'errors': report['errors'],
                  'screenplay_binding': report['screenplay_binding'],
                  'media': 'NOT_RUN', 'independent_review': 'PENDING'},
}
validate_v5('role-result', role)


class ReceiptAuditShim:
    audit_required = lambda self: True
    receipt_audit = V5Kernel.receipt_audit


assert ReceiptAuditShim().receipt_audit(task, role) == 'audited'
write(OUT / 'role-result.json', role)

candidate = {
    'schema': 'candidate-result/6.0', 'task_id': task['task_id'],
    'batch': envelope['batch'], 'agent_id': AGENT,
    'input_digest': envelope['input_digest'],
    'result_uri': relative(OUT / 'role-result.json'),
    'result_sha256': file_hash(OUT / 'role-result.json'),
    'artifacts': [{'slot': 'director:project:project:DirectorIR', 'kind': 'DirectorIR',
                   'uri': relative(ir_path), 'sha256': file_hash(ir_path)}],
    'module_receipts': [envelope['module']],
    'checks': [{'id': check_id, 'status': 'PASS', 'evidence': uris}
               for check_id, uris in check_evidence.items()],
    'handoffs': [{**item, 'evidence': [evidence('v6-handoffs.json'), evidence('v5-handoff.json')]}
                 for item in envelope['handoffs']],
    'unresolved': [],
}
validate_v6_protocol('candidate-result', candidate)
assert {row['id'] for row in candidate['checks']} == {row['id'] for row in envelope['validators']}
assert {row['requirement_id'] for row in candidate['handoffs']} == {
    row['requirement_id'] for row in envelope['handoffs']
}
write(OUT / 'candidate-result.json', candidate)
write(EVIDENCE / 'package-check.json', {
    'status': 'PASS', 'v5_role_schema': 'PASS', 'v5_module_receipt': 'audited',
    'v5_native_validator': native['status'], 'v5_handoff': 'PASS',
    'v6_candidate_schema': 'PASS', 'v6_input_digest': 'PASS',
    'v6_check_ids': 'PASS', 'v6_handoff_ids': 'PASS',
    'director_ir_sha256': file_hash(ir_path),
    'role_result_sha256': file_hash(OUT / 'role-result.json'),
    'candidate_result_sha256': file_hash(OUT / 'candidate-result.json'),
    'formal_state_modified': False, 'actual_media': 'NOT_RUN',
})
print(json.dumps({'candidate': str(OUT / 'candidate-result.json'),
                  'candidate_sha256': file_hash(OUT / 'candidate-result.json'),
                  'director_ir_sha256': file_hash(ir_path),
                  'role_result_sha256': file_hash(OUT / 'role-result.json')}, ensure_ascii=False))
