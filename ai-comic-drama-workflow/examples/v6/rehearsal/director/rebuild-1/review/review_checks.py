"""Independent read-only check for one frozen V6 Director candidate."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
REPO = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow')
TASK = 'TASK_ae94f4322a77ebd18dbb635d'
BATCH = 1
REVIEWER = '/root/host_bridge/v6_2f376a7f208dfc8de4329c5c'
BASE = ROOT / 'runtime/v6/candidates' / TASK / str(BATCH)
OUT = ROOT / 'runtime/v6/reviews' / TASK / str(BATCH)
ACTION = Path('/private/tmp/ai-video-v6-real-efKlQy/director-rebuild-candidate-output.json')
LOCKED = ROOT / 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
PYTHON = REPO / '.venv/bin/python'

sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(LOCKED / 'scripts'))
from ai_comic_drama_workflow.v6_protocol import candidate_digest, validate_v6_protocol  # noqa: E402
import detail_runtime as detail  # noqa: E402
import screenplay_protocol as screenplay  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def hash_file(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


action = read(ACTION)['actions'][0]
assert action['action_id'] == 'review-b3f83e98b868ad4066b4cdf1'
review_dispatch_id = action['dispatch_id']
text = action['arguments']['message']
envelope = json.loads(text.split('Frozen task envelope:\n', 1)[1].split('\nCandidate:\n', 1)[0])
dispatched_candidate = json.loads(text.split('\nCandidate:\n', 1)[1])
candidate = read(BASE / 'candidate-result.json')
assert candidate == dispatched_candidate
assert candidate['task_id'] == TASK and candidate['batch'] == BATCH
assert candidate['agent_id'] != REVIEWER and candidate['input_digest'] == envelope['input_digest']
validate_v6_protocol('candidate-result', candidate, REPO)
digest = candidate_digest(candidate)
assert digest == 'e6e8e0e4f7e57a20dfc62f067c9e25bca67a20290abc5f368ec06745c9d8c10c'
assert envelope['task_id'] == TASK and envelope['batch'] == BATCH
assert envelope['role'] == 'director'
assert {x['id'] for x in envelope['validators']} == {'module_receipt', 'native_validator', 'handoff'}

ir_path = ROOT / candidate['artifacts'][0]['uri']
ir = read(ir_path)
assert candidate['artifacts'] == [{
    'kind': 'DirectorIR', 'sha256': hash_file(ir_path),
    'slot': 'director:project:project:DirectorIR',
    'uri': 'runtime/v6/candidates/' + TASK + '/1/director-ir.json'}]
assert hash_file(ROOT / candidate['result_uri']) == candidate['result_sha256']
assert all(hash_file(ROOT / x['uri']) == x['sha256'] for x in envelope['inputs'])
assert all(hash_file(ROOT / x['uri']) == x['sha256'] for x in envelope['resources'])
assert candidate['module_receipts'] == [envelope['module']]
receipt = read(BASE / 'evidence/module-receipt.json')['module_receipt']
assert receipt['name'] == envelope['module']['name'] and receipt['version'] == envelope['module']['version']
assert receipt['skill_sha256'] == envelope['resources'][0]['sha256']
assert {(x['path'], x['sha256']) for x in receipt['reads']} == {
    (str(ROOT / x['uri']), x['sha256']) for x in envelope['resources']}
for row in candidate['checks']:
    assert row['status'] == 'PASS' and row['evidence']
    assert all((ROOT / uri).is_file() and (ROOT / uri).stat().st_size > 0 for uri in row['evidence'])

stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
module_evidence = {
    'status': 'PASS', 'check': 'module_receipt', 'reviewer_agent_id': REVIEWER,
    'reviewed_at': stamp, 'candidate_digest': digest,
    'candidate_sha256': hash_file(BASE / 'candidate-result.json'),
    'artifact_sha256': hash_file(ir_path),
    'input_digest': envelope['input_digest'],
    'input_hashes': [{'uri': row['uri'], 'sha256': hash_file(ROOT / row['uri'])} for row in envelope['inputs']],
    'resource_hashes': [{'uri': row['uri'], 'sha256': hash_file(ROOT / row['uri'])} for row in envelope['resources']],
    'module': envelope['module'],
    'finding': 'Frozen input, four locked resource bytes, result bytes and V6 candidate schema agree with the dispatch envelope. Module receipt records resources only.'}
save('module-receipt.review.json', module_evidence)

command = [str(PYTHON), str(LOCKED / 'scripts/dg.py'), 'validate', str(ir_path),
           '--screenplay-handoff', str(BASE / 'screenplay-handoff.json'),
           '--screenplay-map', str(BASE / 'screenplay-map.json')]
run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
report = json.loads(run.stdout)
assert run.returncode == 0 and run.stderr == ''
assert report['status'] == 'STATIC_VALID' and report['errors'] == []
assert report['screenplay_binding']['status'] == 'REVIEW_ATTESTED'
assert detail.semantic_status(ir)
assert ir['timeline']['semantic_review']['input_sha256'] == detail.content_hash(ir)
assert ir['schema_version'] == '1.2' and ir['timeline']['schema'] == 'detail-timeline/1.2'
assert len(ir['shots']) == 1 and ir['shots'][0]['id'] == 'S1'
assert ir['shots'][0]['frames'] == ir['format']['total_frames'] == 288
assert ir['format']['fps'] == 24

actions = ir['timeline']['actions']
assert [(x['id'], x['semantic_id'], x['start_ms'], x['end_ms']) for x in actions] == [
    ('ACT_EXTEND', 'EVT_HANDOFF', 500, 1800),
    ('ACT_GRIP', 'EVT_HANDOFF', 2000, 2800),
    ('ACT_RELEASE', 'EVT_HANDOFF', 2800, 4000),
    ('ACT_CONFIRM_SEAL', 'EVT_SEAL_CHECK', 4500, 7500),
    ('ACT_STOW', 'EVT_STOW', 8000, 11000),
]
assert sum(len(x['changes']) for x in actions) == 31
samples = ir['timeline']['state_samples']
assert [s['at_ms'] for s in samples] == [0, 2500, 4000, 7500, 10500, 12000]
for action in actions:
    for change in action['changes']:
        later = [s for s in samples if s['at_ms'] >= change['at_ms']]
        assert later, (action['id'], change)
        # Each declared change must hold at the first observed sample after its timestamp
        # unless another explicit change to the same field supersedes it before that sample.
        first = later[0]
        other = [c for a in actions for c in a['changes']
                 if c is not change and c['entity_id'] == change['entity_id'] and c['field'] == change['field']
                 and change['at_ms'] < c['at_ms'] <= first['at_ms']]
        if not other:
            assert first['entities'][change['entity_id']][change['field']] == change['after'], (action['id'], change)

shot = ir['shots'][0]
start = samples[0]['entities']
end = samples[-1]['entities']
for static, dynamic in ((shot['start_state'], start), (shot['end_state'], end)):
    for row in static:
        entity = dynamic[row['entity_id']]
        assert row['pose'] == entity['pose']
        assert row['position_m'] == [entity['position'][0], entity['position'][2], entity['position'][1]]
        if row['entity_id'] == 'PROP_LETTER':
            assert row['contact'] in entity['contacts'] and row['support'] in entity['supports']

ownership = []
for sample in samples:
    t = sample['at_ms']; e = sample['entities']; letter = e['PROP_LETTER']
    for hand in letter['contacts']:
        if hand.startswith('CHAR_JIA.'):
            assert 'PROP_LETTER.body' in e['CHAR_JIA']['contacts']
        elif hand.startswith('CHAR_YI.'):
            assert 'PROP_LETTER.body' in e['CHAR_YI']['contacts']
        elif hand == 'PROP_BACKPACK.interior':
            assert 'PROP_LETTER.body' in e['PROP_BACKPACK']['contacts']
        else:
            raise AssertionError((t, hand))
    expected = ['CHAR_JIA.right_hand'] if t < 4000 else ['CHAR_YI.right_hand'] if t < 10500 else []
    assert letter['controllers'] == expected, (t, letter['controllers'])
    ownership.append({'at_ms': t, 'controllers': letter['controllers'], 'contacts': letter['contacts'],
                      'letter_pose': letter['pose'], 'jia_pose': e['CHAR_JIA']['pose'], 'yi_pose': e['CHAR_YI']['pose']})
assert len([x for x in ir['entities'] if x['id'] == 'PROP_LETTER']) == 1
assert end['PROP_LETTER']['visible_parts'] == []
assert end['PROP_LETTER']['supports'] == ['PROP_BACKPACK.interior']
assert '不再持信' in end['CHAR_JIA']['pose'] and '信在包内' in end['CHAR_YI']['pose']
end_comp = next(c for c in ir['timeline']['composition_tracks'] if c['id'] == 'COMP_END')
end_subject = next(s for s in end_comp['subjects'] if s['node_id'] == 'N_LETTER')
assert end_subject['visible_parts'] == [] and '背包内部遮住' in end_subject['occlusion']
assert ir['timeline']['audio_events'][0]['route'] == 'post'
assert ir['contract']['execution']['mode'] == 'plan_only'

native_evidence = {
    'status': 'PASS', 'check': 'native_validator', 'reviewer_agent_id': REVIEWER,
    'reviewed_at': stamp, 'candidate_digest': digest, 'artifact_sha256': hash_file(ir_path),
    'command': command, 'returncode': run.returncode, 'stdout': report, 'stderr': run.stderr,
    'semantic_content_sha256': detail.content_hash(ir), 'action_changes_replayed': 31,
    'state_samples_checked': [s['at_ms'] for s in samples], 'custody_samples': ownership,
    'legacy_coordinate_conversion': 'Static X-right,Y-depth,Z-up [x,y,z] equals timeline x-right,y-up,z-depth [x,z,y] at shot start and end.',
    'actual_media': 'NOT_RUN',
    'finding': 'Locked native DirectorIR 1.2 check and screenplay binding pass. Six key states and 31 action deltas agree; final letter is inside backpack and occluded, with neither person holding it. This is static review only.'}
save('native-validator.review.json', native_evidence)

handoff, script = screenplay.load_handoff(BASE / 'screenplay-handoff.json')
mapping = read(BASE / 'screenplay-map.json')
assert screenplay.validate_mapping(ir, handoff['requirements'], mapping, handoff['content_sha256']) == []
assert handoff['content_sha256'] == screenplay.content_hash(script)
assert mapping['director_sha256'] == screenplay.content_hash(ir)
assert len(handoff['requirements']) == len(mapping['mappings']) == 6
clauses = {c['id']: c for c in ir['contract']['clauses']}
mapped = []
for req in handoff['requirements']:
    row = next(x for x in mapping['mappings'] if x['requirement_id'] == req['id'])
    assert row['source_fingerprint'] == req['source_fingerprint']
    assert row['target_clause'] in clauses and clauses[row['target_clause']]['priority'] == 'hard'
    assert all(screenplay.assert_check(ir, c) for c in row['target_checks'])
    mapped.append({'id': req['id'], 'source_fingerprint': req['source_fingerprint'],
                   'native_hard_clause': row['target_clause'],
                   'checked_target_pointers': [c['path'] for c in row['target_checks']]})
assert [e['id'] for e in script['narrative']['events']] == ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW']
assert script['narrative']['reveal_order'] == ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW']
assert ir['shots'][0]['dialogue'] == []
assert [b['id'] for b in ir['beats']] == ['BEAT_HANDOFF', 'BEAT_CONFIRM', 'BEAT_STOW']
assert [a['semantic_id'] for a in actions] == ['EVT_HANDOFF'] * 3 + ['EVT_SEAL_CHECK', 'EVT_STOW']
assert '雨夜' in ir['scenes'][0]['space'] and '具体地点和室内外未指定' in ir['scenes'][0]['space']

expected = {(h['requirement_id'], h['source_slot'], h['source_version'], h['target_slot'], h['channel'], h['target_pointer'])
            for h in envelope['handoffs']}
actual = {(h['requirement_id'], h['source_slot'], h['source_version'], h['target_slot'], h['channel'], h['target_pointer'])
          for h in candidate['handoffs']}
assert expected == actual and len(actual) == 2
v6 = read(BASE / 'evidence/v6-handoffs.json')
assert len(v6['handoffs']) == 2
assert v6['bound_artifact_sha256'] == hash_file(ir_path)
assert v6['bound_input_digest'] == envelope['input_digest']
v6_rows = []
for row in v6['handoffs']:
    source = next(x for x in envelope['inputs'] if x['slot'] == row['source_slot'])
    assert row['source_uri'] == source['uri'] and row['source_sha256'] == source['sha256']
    assert row['source_version'] == source['version']
    assert row['target_sha256'] == hash_file(ir_path) and row['target_uri'] == candidate['artifacts'][0]['uri']
    assert row['target_pointers'] and all(screenplay.pointer(ir, p) is not None for p in row['target_pointers'])
    assert row['evidence'] and all((ROOT / uri).stat().st_size > 0 for uri in row['evidence'])
    v6_rows.append({'id': row['requirement_id'], 'source_sha256': row['source_sha256'],
                    'source_version': row['source_version'], 'target_pointers': row['target_pointers']})

prior = read(BASE / 'evidence/prior-stamp-difference.json')
prior_ir = read(ROOT / prior['prior_promoted_uri'])
assert prior['prior_promoted_semantic_review_input_sha256'] == prior_ir['timeline']['semantic_review']['input_sha256']
assert prior['prior_promoted_current_semantic_content_sha256'] == detail.content_hash(prior_ir)
assert prior['prior_promoted_semantic_review_input_sha256'] != prior['prior_promoted_current_semantic_content_sha256']
assert prior['current_candidate_map_sha256'] == mapping['director_sha256']
assert prior['current_candidate_map_sha256'] != prior['prior_mapping_director_sha256']
assert ir['timeline']['semantic_review']['input_sha256'] == detail.content_hash(ir)
assert ir['timeline']['semantic_review']['input_sha256'] != prior_ir['timeline']['semantic_review']['input_sha256']

handoff_evidence = {
    'status': 'PASS', 'check': 'handoff', 'reviewer_agent_id': REVIEWER,
    'reviewed_at': stamp, 'candidate_digest': digest, 'artifact_sha256': hash_file(ir_path),
    'source_text': (ROOT / 'sources/SRC_69a71adcfaca/source.txt').read_text(encoding='utf-8'),
    'v5_screenplay_content_sha256': handoff['content_sha256'], 'v5_mappings': mapped,
    'v6_handoffs': v6_rows,
    'prior_promoted_stamp': prior['prior_promoted_semantic_review_input_sha256'],
    'prior_promoted_actual_content': prior['prior_promoted_current_semantic_content_sha256'],
    'current_semantic_stamp': ir['timeline']['semantic_review']['input_sha256'],
    'current_screenplay_mapping_content': mapping['director_sha256'],
    'action_order': 'Handoff complete by 4000 ms, seal check 4500–7500 ms, stow 8000–11000 ms.',
    'actual_media': 'NOT_RUN',
    'finding': 'All six V5 screenplay requirements retain source fingerprints and are asserted against native hard clauses. Both V6 handoffs bind frozen source versions and this exact artifact. The old V5 relocated snapshot has a historical stale stamp; current candidate stamps and mapping are freshly bound and valid.'}
save('handoff.review.json', handoff_evidence)

review = {
    'schema': 'review-record/6.0', 'task_id': TASK, 'batch': BATCH,
    'reviewer_agent_id': REVIEWER, 'reviewer_dispatch_id': review_dispatch_id,
    'candidate_digest': digest, 'at': stamp,
    'checks': [{'id': name, 'status': 'PASS', 'evidence': [f'runtime/v6/reviews/{TASK}/{BATCH}/{filename}.review.json']}
               for name, filename in (('module_receipt', 'module-receipt'),
                                      ('native_validator', 'native-validator'),
                                      ('handoff', 'handoff'))],
    'failure_owner': None}
validate_v6_protocol('review-record', review, REPO)
assert all((ROOT / uri).is_file() and (ROOT / uri).stat().st_size > 0
           for row in review['checks'] for uri in row['evidence'])
save('review-record.json', review)
print(json.dumps({'review_uri': f'runtime/v6/reviews/{TASK}/{BATCH}/review-record.json',
                  'review_sha256': hash_file(OUT / 'review-record.json'),
                  'candidate_digest': digest, 'checks': [x['id'] + ':' + x['status'] for x in review['checks']]},
                 ensure_ascii=False))
