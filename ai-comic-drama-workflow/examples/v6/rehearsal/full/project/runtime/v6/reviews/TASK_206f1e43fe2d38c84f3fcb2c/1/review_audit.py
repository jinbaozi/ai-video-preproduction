"""Independent, read-only audit of the frozen V6 screenplay candidate."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from jsonschema import Draft202012Validator, FormatChecker


PROJECT = Path('/private/tmp/ai-video-v6-full-demo/project')
REPO = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow')
TASK_ID = 'TASK_206f1e43fe2d38c84f3fcb2c'
AGENT_ID = '/root/host_bridge/full_rehearsal/v6_0a3e7de03e6af972fb4ce021'
ROOT = PROJECT / f'runtime/v6/candidates/{TASK_ID}/1'
OUT = PROJECT / f'runtime/v6/reviews/{TASK_ID}/1'
MODULE = PROJECT / 'runtime/modules/a2cb49a9096ba696e1db059663fcecbb61c3c102c5c10bcd91047704edafe5d4/screenplay-grammar'
sys.path.insert(0, str(MODULE / 'scripts'))
import screenplay_protocol as native  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def check_schema(name, value):
    schema = read(REPO / f'schemas/v6-{name}.schema.json')
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
                    key=lambda e: str(e.absolute_path))
    assert not errors, [e.message for e in errors]


state = read(PROJECT / 'runtime/v6/state.json')
task = state['tasks'][TASK_ID]
envelope = task['envelope']
candidate = read(ROOT / 'candidate-result.json')
role = read(ROOT / 'role-result.json')
script = native.read(ROOT / 'script-ir.json')
receipt = read(ROOT / 'evidence/module-receipt.json')
canon_input = envelope['inputs'][0]
canon_path = PROJECT / canon_input['uri']
canon = read(canon_path)
frozen_task_input = envelope['inputs'][1]

assert task['state'] == 'REVIEW_REQUIRED'
assert task['review_dispatch']['agent_id'] == AGENT_ID
assert candidate == task['candidate']
assert candidate['agent_id'] != AGENT_ID
assert candidate['task_id'] == TASK_ID and candidate['batch'] == 1
assert candidate['input_digest'] == envelope['input_digest']
assert sha(ROOT / 'script-ir.json') == candidate['artifacts'][0]['sha256'] == role['artifact_sha256']
assert sha(ROOT / 'role-result.json') == candidate['result_sha256']
check_schema('task-envelope', envelope)
check_schema('candidate-result', candidate)

for item in envelope['inputs'] + envelope['resources']:
    assert sha(PROJECT / item['uri']) == item['sha256'], item['uri']
assert receipt['frozen_inputs'] == [
    {'uri': x['uri'], 'sha256': x['sha256']} for x in envelope['inputs']
]
assert receipt['archive_sha256'] == envelope['module']['sha256']
assert receipt['name'] == envelope['module']['name']
assert receipt['version'] == envelope['module']['version']
assert read(PROJECT / 'modules.lock.json')['modules'][receipt['name']]['sha256'] == receipt['archive_sha256']
assert candidate['module_receipts'] == [envelope['module']]
assert role['module_receipt']['skill_sha256'] == receipt['skill_sha256']
assert role['module_receipt']['reads'] == receipt['reads']
assert len(receipt['reads']) == len(envelope['resources']) == 4
for got, expected in zip(receipt['reads'], envelope['resources']):
    assert Path(got['path']) == PROJECT / expected['uri']
    assert got['sha256'] == expected['sha256'] == sha(got['path'])

now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
digest = compact_hash(candidate)
module_evidence = {
    'check': 'module_receipt', 'status': 'PASS', 'reviewed_at': now,
    'candidate_digest': digest,
    'method': 'Independently verified the frozen V6 schemas, input and resource file bytes, module lock and creator read receipt.',
    'module': envelope['module'], 'resource_files_verified': len(envelope['resources']),
    'frozen_inputs_verified': [canon_input['uri'], frozen_task_input['uri']],
    'creator_result_sha256': sha(ROOT / 'role-result.json'),
    'script_sha256': sha(ROOT / 'script-ir.json'),
    'finding': 'The ScriptIR and role result are byte-bound to this candidate; all required module resources and frozen inputs match their declared SHA-256 values.'
}
write('module-receipt.review.json', module_evidence)

env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
process = subprocess.run([sys.executable, str(MODULE / 'scripts/sg.py'), 'validate',
                          str(ROOT / 'script-ir.json'), '--final'],
                         capture_output=True, text=True, env=env, check=True)
report = json.loads(process.stdout)
assert report == {'errors': [], 'semantic_review': 'REVIEW_ATTESTED', 'status': 'STATIC_VALID'}
assert report == role['validator']
assert report == read(ROOT / 'evidence/native-validator.json')
assert report == read(ROOT / 'evidence/native-validator-refresh.json')
assert native.content_hash(script) == script['review']['content_sha256']
assert native.content_hash(script) == read(ROOT / 'evidence/semantic-review.json')['content_sha256']
assert script['review']['status'] == 'PASS' and script['review']['findings']

manifest_path = ROOT / 'compiled/compile-manifest.json'
manifest = read(manifest_path)
for relative, metadata in manifest['files'].items():
    path = ROOT / 'compiled' / relative
    assert path.stat().st_size == metadata['bytes'], relative
    assert sha(path) == metadata['sha256'], relative
assert manifest['input_content_sha256'] == native.content_hash(script)
assert manifest['status'] == 'READY'
compiled_checks = read(ROOT / 'compiled/checks.json')
assert compiled_checks['status'] == 'STATIC_VALID' and compiled_checks['delivery'] == 'READY'
assert compiled_checks['media'] == 'NOT_RUN'
handoff = read(ROOT / 'compiled/director-handoff.json')
assert handoff['ready'] is True and handoff['content_sha256'] == native.content_hash(script)
assert sha(ROOT / 'compiled' / handoff['script_ref']['uri']) == handoff['script_ref']['sha256']
static_checks = {}
for check in script['contract']['checks']:
    if check['method'] == 'static':
        static_checks[check['id']] = all(native.assert_check(script, row) for row in check['assertions'])
assert static_checks == {'RAIN_STATIC': True, 'LETTER_STATIC': True, 'ORDER_STATIC': True}
native_evidence = {
    'check': 'native_validator', 'status': 'PASS', 'reviewed_at': now,
    'method': 'Reran the frozen sg.py validate --final, checked the content fingerprint and every compiled manifest byte size and SHA-256, and evaluated all static contract assertions.',
    'native_final_report': report, 'script_uri': str((ROOT / 'script-ir.json').relative_to(PROJECT)),
    'script_sha256': sha(ROOT / 'script-ir.json'), 'content_sha256': native.content_hash(script),
    'compiled_manifest_uri': str(manifest_path.relative_to(PROJECT)),
    'compiled_manifest_sha256': sha(manifest_path),
    'compiled_files_verified': len(manifest['files']),
    'compiled_status': manifest['status'], 'director_handoff_ready': handoff['ready'],
    'compiled_script_ref_hash_matches': True, 'static_contract_assertions': static_checks,
    'professional_blind_review': 'THIS_REVIEW', 'media': 'NOT_RUN',
    'finding': 'The native final validator returns STATIC_VALID with no errors; review fingerprint, static clauses and all compiled files are current. No media was generated.'
}
write('native-validator.review.json', native_evidence)

assert sha(canon_path) == canon_input['sha256']
assert task['envelope']['handoffs'] == candidate['handoffs'][:1] or all(
    all(row[key] == expected[key] for key in ('channel', 'requirement_id', 'source_slot',
                                             'source_version', 'target_pointer', 'target_slot'))
    for row, expected in zip(candidate['handoffs'], envelope['handoffs']))
assert task['envelope']['handoffs'] and len(candidate['handoffs']) == 1
assert task['envelope']['dependencies'] == [{'task_id': 'TASK_44ed8445ba9b638fcd7e9fe8'}]
assert state['tasks']['TASK_44ed8445ba9b638fcd7e9fe8']['state'] == 'ACCEPTED'
assert script['project_id'] == canon['project_id'] == envelope['project_id']
formal = PROJECT / 'artifacts/canon/f3c90f6c20dd218a854fa67548b296692d71fd08bc62e2ca5076a27667809b18/native/0cc4aebffda6a714_canon.json'
assert sha(formal) == script['canon']['ref']['sha256'] == receipt['formal_canon']['sha256']
assert read(formal) == canon and receipt['formal_canon']['json_equal_to_frozen'] is True
assert sha(script['sources'][0]['uri']) == script['sources'][0]['sha256']
assert script['sources'][0]['excerpt'] == canon['content']
assert script['sources'][1]['sha256'] == sha(formal)

mapping = read(ROOT / 'evidence/handoff.json')['mapping']
assert len(mapping) == len(canon['source_requirements']) == 3
for i, row in enumerate(mapping):
    source_req = native.pointer(canon, row['source_pointer'])
    assert source_req['id'] == script['contract']['clauses'][i]['id']
    for pointer in row['target_pointers']:
        native.pointer(script, pointer)
source_event_ids = [x['id'] for x in canon['event_order']]
target_event_ids = [x['id'] for x in script['narrative']['events']]
assert source_event_ids == target_event_ids == script['narrative']['reveal_order']
assert [x['id'] for x in script['scenes'][0]['blocks']] == ['B_HANDOFF', 'B_SEAL_CHECK', 'B_STOW']
assert [x['id'] for x in script['characters']] == ['CHAR_JIA', 'CHAR_YI']
assert '雨夜' in script['scenes'][0]['heading']
assert '未拆的信交给乙' in script['scenes'][0]['blocks'][0]['text']
assert '确认封口完整' in script['scenes'][0]['blocks'][1]['text']
assert '信仍未拆开' in script['scenes'][0]['blocks'][1]['text']
assert '同一封信收进背包' in script['scenes'][0]['blocks'][2]['text']
assert not any(block['kind'] == 'dialogue' for block in script['scenes'][0]['blocks'])
assert '地点未指定' in script['scenes'][0]['heading']

handoff_evidence = {
    'check': 'handoff', 'status': 'PASS', 'reviewed_at': now,
    'method': 'Compared frozen Canon, formal native Canon, CandidateResult and RoleResult handoff tuples; resolved every source and target pointer and independently read event and action semantics.',
    'binding': envelope['handoffs'][0],
    'source_uri': canon_input['uri'], 'source_sha256': sha(canon_path),
    'target_uri': candidate['artifacts'][0]['uri'], 'target_sha256': sha(ROOT / 'script-ir.json'),
    'dependency_state': 'ACCEPTED', 'mapping_pointers_exist': True,
    'source_requirement_ids': [x['id'] for x in canon['source_requirements']],
    'target_clause_ids': [x['id'] for x in script['contract']['clauses']],
    'source_event_ids': source_event_ids, 'target_event_ids': target_event_ids,
    'registered_canon_json_matches_frozen': True,
    'source_semantics': {
        'rainy_night_retained': True,
        'same_unopened_letter_retained': True,
        'seal_confirmation_before_stow': True,
        'canon_character_ids_reused': True,
        'invented_dialogue_or_motive': False,
        'invented_location_or_indoor_outdoor_state': False,
    },
    'finding': 'The three Canon hard requirements reach clauses and scene/event content. Rainy night and the same unopened letter persist through handoff, seal confirmation and backpack stow in that order.'
}
write('handoff.review.json', handoff_evidence)

record = {
    'schema': 'review-record/6.0', 'task_id': TASK_ID, 'batch': 1,
    'reviewer_agent_id': AGENT_ID,
    'reviewer_dispatch_id': task['review_dispatch']['dispatch_id'],
    'candidate_digest': digest,
    'checks': [
        {'id': 'module_receipt', 'status': 'PASS', 'evidence': [str((OUT / 'module-receipt.review.json').relative_to(PROJECT))]},
        {'id': 'native_validator', 'status': 'PASS', 'evidence': [str((OUT / 'native-validator.review.json').relative_to(PROJECT))]},
        {'id': 'handoff', 'status': 'PASS', 'evidence': [str((OUT / 'handoff.review.json').relative_to(PROJECT))]},
    ],
    'failure_owner': None, 'at': now,
}
check_schema('review-record', record)
write('review-record.json', record)
print(json.dumps({'review_uri': str((OUT / 'review-record.json').relative_to(PROJECT)),
                  'review_sha256': sha(OUT / 'review-record.json'),
                  'candidate_digest': digest,
                  'native': report,
                  'compiled_files_verified': len(manifest['files']),
                  'checks': record['checks']}, ensure_ascii=False, indent=2))
