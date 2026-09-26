"""Independent Art reviewer audit for the frozen V6 candidate."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ai_comic_drama_workflow.v5_adapters import assert_check, digest, pointer
from ai_comic_drama_workflow.v6_protocol import (
    candidate_digest,
    envelope_input_digest,
    validate_v6_protocol,
)


ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
TASK_ID = 'TASK_71abb1f14640b94809ef3db2'
CANDIDATE = ROOT / 'runtime/v6/candidates' / TASK_ID / '1'
REVIEW = ROOT / 'runtime/v6/reviews' / TASK_ID / '1'
STATE = json.loads((ROOT / 'runtime/v6/state.json').read_text())
TASK = STATE['tasks'][TASK_ID]
ENVELOPE = TASK['envelope']
RESULT = json.loads((CANDIDATE / 'candidate-result.json').read_text())
ROLE = json.loads((CANDIDATE / 'role-result.json').read_text())
ART = json.loads((CANDIDATE / 'art-ir.json').read_text())
DIRECTOR = json.loads((ROOT / ENVELOPE['inputs'][1]['uri']).read_text())
V5_TASK = json.loads((ROOT / ENVELOPE['inputs'][2]['uri']).read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name: str, value: object) -> str:
    path = REVIEW / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    return str(path.relative_to(ROOT))


assert TASK['state'] == 'REVIEW_REQUIRED'
assert TASK['review_dispatch']['agent_id'] == '/root/host_bridge/v6_ac99209e150410231f8e3c21'
assert TASK['review_dispatch']['dispatch_id'] == 'review-ffdb83201c4ee1a7a6058f6d'
assert TASK['receipt']['agent_id'] == RESULT['agent_id'] != TASK['review_dispatch']['agent_id']
assert TASK['candidate'] == RESULT
validate_v6_protocol('candidate-result', RESULT)
validate_v6_protocol('task-envelope', ENVELOPE)
assert envelope_input_digest(ENVELOPE) == RESULT['input_digest']
assert ROLE['task_id'] == TASK_ID and ROLE['complete'] is True
assert ROLE['unresolved'] == [] and RESULT['unresolved'] == []
assert RESULT['module_receipts'] == [ENVELOPE['module']]
assert RESULT['artifacts'] == [{
    'slot': ENVELOPE['expected_artifacts'][0]['slot'],
    'kind': 'ArtIR',
    'uri': str((CANDIDATE / 'art-ir.json').relative_to(ROOT)),
    'sha256': sha(CANDIDATE / 'art-ir.json'),
}]
assert RESULT['result_sha256'] == sha(CANDIDATE / 'role-result.json')
assert ROLE['artifact_sha256'] == sha(CANDIDATE / 'art-ir.json')
assert Path(ROLE['artifact']).resolve() == (CANDIDATE / 'art-ir.json').resolve()

input_audit = []
for row in ENVELOPE['inputs']:
    actual = sha(ROOT / row['uri'])
    assert actual == row['sha256']
    input_audit.append({**row, 'observed_sha256': actual})
resource_audit = []
for row in ENVELOPE['resources']:
    actual = sha(ROOT / row['uri'])
    assert actual == row['sha256']
    resource_audit.append({**row, 'observed_sha256': actual})
assert ROLE['module_receipt']['name'] == ENVELOPE['module']['name']
assert ROLE['module_receipt']['version'] == ENVELOPE['module']['version']
assert ROLE['module_receipt']['skill_sha256'] == ENVELOPE['resources'][0]['sha256']
assert [
    (Path(row['path']).resolve(), row['sha256'])
    for row in ROLE['module_receipt']['reads']
] == [
    ((ROOT / row['uri']).resolve(), row['sha256'])
    for row in ENVELOPE['resources']
]

integrity = json.loads((CANDIDATE / 'evidence/source-integrity.json').read_text())
receipt = json.loads((CANDIDATE / 'evidence/module-receipt.json').read_text())
assert integrity['status'] == receipt['status'] == 'PASS'
assert integrity['v6_input_digest'] == RESULT['input_digest']
assert integrity['v6_input_revision'] == ENVELOPE['input_revision']
assert integrity['inputs'] == [{**row, 'actual_sha256': row['sha256'], 'verified': True} for row in ENVELOPE['inputs']]
assert integrity['resources'] == [{**row, 'actual_sha256': row['sha256'], 'verified': True} for row in ENVELOPE['resources']]
assert receipt['module_receipt'] == ROLE['module_receipt']
assert receipt['resource_count'] == len(ENVELOPE['resources'])
for row in integrity['v5_formal_inputs']:
    assert sha(Path(row['uri'])) == row['expected_sha256'] == row['actual_sha256']
assert sha(ROOT / integrity['original_source']['uri']) == integrity['original_source']['sha256']

v6_canon = json.loads((ROOT / ENVELOPE['inputs'][0]['uri']).read_text())
native_canon = json.loads(Path(integrity['binding']['canon_native_uri']).read_text())
assert v6_canon == native_canon
assert integrity['binding']['canon_same_json_object'] is True
assert integrity['binding']['canon_v6_uri'] == str((ROOT / ENVELOPE['inputs'][0]['uri']).resolve())
assert integrity['binding']['canon_native_sha256'] == sha(Path(integrity['binding']['canon_native_uri']))
assert ART['canon']['uri'] == DIRECTOR['canon_ref'] == integrity['binding']['canon_native_uri']
assert ART['sources'][1]['uri'] == ART['canon']['uri']
assert ART['director']['uri'] == str((ROOT / ENVELOPE['inputs'][1]['uri']).resolve())
assert ART['director']['sha256'] == ENVELOPE['inputs'][1]['sha256']
assert ART['project_id'] == ENVELOPE['project_id'] == DIRECTOR['project_id']
assert ART['set']['scene_id'] == ENVELOPE['scope']['ids'][0]

evidence_rows = []
required_evidence = {uri for check in RESULT['checks'] for uri in check['evidence']}
required_evidence |= {uri for handoff in RESULT['handoffs'] for uri in handoff['evidence']}
assert required_evidence == set(TASK['evidence_hashes'])
for uri in sorted(required_evidence):
    actual = sha(ROOT / uri)
    assert actual == TASK['evidence_hashes'][uri]
    evidence_rows.append({'uri': uri, 'sha256': actual})

module_evidence = save('module-receipt.review.json', {
    'status': 'PASS', 'task_id': TASK_ID, 'candidate_digest': candidate_digest(RESULT),
    'input_digest': RESULT['input_digest'], 'frozen_inputs': input_audit,
    'locked_resources': resource_audit, 'candidate_evidence': evidence_rows,
    'v5_promoted_canon_sha256': sha(Path(ART['canon']['uri'])),
    'v6_frozen_canon_sha256': ENVELOPE['inputs'][0]['sha256'],
    'canon_json_object_equal': True,
    'art_canon_uri_matches_director_canon_ref': True,
    'source_integrity_sha256': sha(CANDIDATE / 'evidence/source-integrity.json'),
    'module_receipt_sha256': sha(CANDIDATE / 'evidence/module-receipt.json'),
})

skill_script = ROOT / 'runtime/modules' / ENVELOPE['module']['sha256'] / ENVELOPE['module']['name'] / 'scripts/art_compile.py'
run = subprocess.run([
    '/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/.venv/bin/python',
    str(skill_script), 'validate', str(CANDIDATE / 'art-ir.json'),
], capture_output=True, text=True)
native = json.loads(run.stdout)
assert run.returncode == 0 and native['status'] == ROLE['validator']['status'] == 'STATIC_VALID'
assert ROLE['validator']['errors'] == []
assert ROLE['validator']['media'] == ROLE['validator']['professional_blind_review'] == 'NOT_RUN'
creator_native = json.loads((CANDIDATE / 'evidence/native-validator.json').read_text())
assert creator_native['status'] == 'PASS'
assert creator_native['art_file_sha256'] == sha(CANDIDATE / 'art-ir.json')
assert creator_native['art_object_sha256'] == native['art_sha256']
compiled = CANDIDATE / 'compiled-generic-video'
compiled_receipt = json.loads((compiled / 'receipt.json').read_text())
compiled_qa = json.loads((compiled / 'qa-report.json').read_text())
compiled_handoff = json.loads((compiled / 'handoff.json').read_text())
assert sha(compiled / 'receipt.json') == creator_native['compiled_package']['receipt_sha256']
assert compiled_receipt['status'] == compiled_handoff['status'] == 'PLANNED'
assert compiled_receipt['submitted'] is compiled_handoff['submitted'] is False
assert compiled_handoff['runnable'] is False
assert compiled_receipt['media_acceptance'] == compiled_qa['status'] == 'NOT_RUN'
assert compiled_receipt['art_sha256'] == compiled_qa['art_sha256'] == native['art_sha256']
compiled_file_audit = []
for name, expected in sorted(compiled_receipt['files'].items()):
    actual = sha(compiled / name)
    assert actual == expected
    compiled_file_audit.append({'file': name, 'sha256': actual})
assert len(ART['events']) == 0 and len(DIRECTOR['timeline']['actions']) == 5
assert DIRECTOR['shots'][0]['phases'] == []
native_evidence = save('native-validator.review.json', {
    'status': 'PASS', 'task_id': TASK_ID, 'candidate_digest': candidate_digest(RESULT),
    'command': [str(skill_script), 'validate', str(CANDIDATE / 'art-ir.json')],
    'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr,
    'role_result_validator': ROLE['validator'],
    'compiled_receipt_sha256': sha(compiled / 'receipt.json'),
    'compiled_qa_sha256': sha(compiled / 'qa-report.json'),
    'compiled_handoff_sha256': sha(compiled / 'handoff.json'),
    'compiled_declared_files': compiled_file_audit,
    'compiled_status': 'PLANNED', 'media_review': 'NOT_RUN',
    'director_action_count': len(DIRECTOR['timeline']['actions']),
    'director_phase_count': len(DIRECTOR['shots'][0]['phases']),
    'art_event_count': len(ART['events']),
})

frozen_handoffs = V5_TASK['handoff']['required_handoffs']
mapped = ROLE['handoff']
handoff_evidence = json.loads((CANDIDATE / 'evidence/v5-handoff.json').read_text())
assert handoff_evidence['status'] == 'PASS'
assert handoff_evidence['requirement_count'] == len(frozen_handoffs) == len(mapped) == 6
assert handoff_evidence['handoffs'] == mapped
assert {item['id'] for item in frozen_handoffs} == {item['requirement_id'] for item in mapped}
v5_rows = []
for req in frozen_handoffs:
    match = next(item for item in mapped if item['requirement_id'] == req['id'])
    source_values = [pointer(DIRECTOR, path) for path in req['source_paths']]
    assert source_values == req['source_values']
    assert digest(source_values) == req['source_fingerprint'] == match['source_fingerprint']
    assert match['source_paths'] == req['source_paths']
    assert match['reason']
    assert all(assert_check(ART, check) for check in match['target_checks'])
    clause = next(item for item in ART['contract']['clauses'] if item['id'] == match['target_clause'])
    assert clause['priority'] == 'hard'
    v5_rows.append({
        'requirement_id': req['id'], 'source_fingerprint': req['source_fingerprint'],
        'source_paths': req['source_paths'], 'target_clause': match['target_clause'],
        'target_checks': match['target_checks'], 'all_target_checks_pass': True,
    })

v6_handoffs = json.loads((CANDIDATE / 'evidence/v6-handoffs.json').read_text())
assert v6_handoffs['status'] == 'PASS'
assert len(v6_handoffs['handoffs']) == len(ENVELOPE['handoffs']) == len(RESULT['handoffs']) == 2
v6_rows = []
for required, actual, recorded in zip(ENVELOPE['handoffs'], RESULT['handoffs'], v6_handoffs['handoffs']):
    for field in ('requirement_id', 'source_slot', 'source_version', 'target_slot', 'target_pointer', 'channel'):
        assert actual[field] == recorded[field] == required[field]
    source = next(item for item in ENVELOPE['inputs'] if item['slot'] == required['source_slot'])
    assert source['version'] == required['source_version']
    assert recorded['source_uri'] == source['uri']
    assert recorded['source_sha256'] == source['sha256'] == sha(ROOT / source['uri'])
    assert recorded['target_uri'] == RESULT['artifacts'][0]['uri']
    assert recorded['target_sha256'] == RESULT['artifacts'][0]['sha256']
    assert recorded['evidence'] == actual['evidence']
    for mapping in recorded['mapping']:
        assert pointer(json.loads((ROOT / source['uri']).read_text()), mapping['source_pointer']) is not None
        for path in mapping['target_pointers']:
            assert pointer(ART, path) is not None
    v6_rows.append({
        'requirement_id': required['requirement_id'], 'source_slot': required['source_slot'],
        'source_version': required['source_version'], 'source_uri': source['uri'],
        'source_sha256': source['sha256'], 'target_slot': required['target_slot'],
        'target_uri': recorded['target_uri'], 'target_sha256': recorded['target_sha256'],
        'channel': required['channel'], 'mapping': recorded['mapping'],
    })
assert ART['sources'][1]['uri'] == DIRECTOR['canon_ref']
assert json.loads(Path(ART['sources'][1]['uri']).read_text()) == v6_canon
handoff_review = save('handoff.review.json', {
    'status': 'PASS', 'task_id': TASK_ID, 'candidate_digest': candidate_digest(RESULT),
    'v5_handoffs': v5_rows, 'v6_handoffs': v6_rows,
    'v6_canon_to_v5_promoted_canon_json_object_equal': True,
    'art_canon_ref_equals_director_canon_ref': True,
    'media_review': 'NOT_RUN',
})

record = {
    'schema': 'review-record/6.0', 'task_id': TASK_ID, 'batch': ENVELOPE['batch'],
    'reviewer_agent_id': TASK['review_dispatch']['agent_id'],
    'reviewer_dispatch_id': TASK['review_dispatch']['dispatch_id'],
    'candidate_digest': candidate_digest(RESULT),
    'checks': [
        {'id': 'module_receipt', 'status': 'PASS', 'evidence': [module_evidence]},
        {'id': 'native_validator', 'status': 'PASS', 'evidence': [native_evidence]},
        {'id': 'handoff', 'status': 'PASS', 'evidence': [handoff_review]},
    ],
    'failure_owner': None,
    'at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
}
validate_v6_protocol('review-record', record)
save('review-record.json', record)
print(json.dumps({
    'review_record': str((REVIEW / 'review-record.json').relative_to(ROOT)),
    'sha256': sha(REVIEW / 'review-record.json'),
    'candidate_digest': candidate_digest(RESULT),
    'checks': [item['status'] for item in record['checks']],
}, ensure_ascii=False))
