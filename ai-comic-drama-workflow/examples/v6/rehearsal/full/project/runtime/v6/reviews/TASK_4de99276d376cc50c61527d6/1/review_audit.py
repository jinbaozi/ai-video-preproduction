import hashlib
import json
import pathlib
import subprocess
from datetime import datetime, timezone

ROOT = pathlib.Path('/private/tmp/ai-video-v6-full-demo/project')
TASK = 'TASK_4de99276d376cc50c61527d6'
BATCH = 1
REVIEWER = '/root/host_bridge/full_rehearsal/v6_87ae54bf4025a9468a875864'
CAND = ROOT / 'runtime/v6/candidates' / TASK / str(BATCH)
OUT = ROOT / 'runtime/v6/reviews' / TASK / str(BATCH)
MODULE = ROOT / 'runtime/modules/6e83e075da45785541fce62f9fcc6ebc8666f48466c382af5980f292613fb5f9/production-design-grammar'
PYTHON = '/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/.venv/bin/python'

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def csha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def resolve(uri):
    path = pathlib.Path(uri)
    return path if path.is_absolute() else ROOT / path

def pointer(obj, path):
    for token in path.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        obj = obj[int(token)] if isinstance(obj, list) else obj[token]
    return obj

def write(name, data):
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return 'runtime/v6/reviews/' + TASK + '/' + str(BATCH) + '/' + name

state = read(ROOT / 'runtime/v6/state.json')['tasks']
row = state[TASK]
env = row['envelope']
candidate = read(CAND / 'candidate-result.json')
role = read(CAND / 'role-result.json')
art = read(CAND / 'art-ir.json')
frozen = read(ROOT / 'runtime/tasks' / (TASK + '.json'))
director = read(resolve(env['inputs'][1]['uri']))
canon = read(resolve(env['inputs'][0]['uri']))
assert row['state'] == 'REVIEW_REQUIRED', row['state']
assert row['review_dispatch']['agent_id'] == REVIEWER
assert row['review_dispatch']['status'] == 'RUNNING'
assert candidate == row['candidate']
assert candidate['task_id'] == TASK and candidate['batch'] == BATCH
assert candidate['agent_id'] != REVIEWER
assert candidate['input_digest'] == env['input_digest']
assert candidate['artifacts'] == [{'kind': 'ArtIR', 'sha256': sha(CAND / 'art-ir.json'), 'slot': env['expected_artifacts'][0]['slot'], 'uri': 'runtime/v6/candidates/' + TASK + '/1/art-ir.json'}]
assert candidate['result_sha256'] == sha(CAND / 'role-result.json')
assert role['artifact_sha256'] == sha(CAND / 'art-ir.json')
assert role['artifact'] == str(CAND / 'art-ir.json')
assert role['context_fingerprint'] == frozen['context_fingerprint']
assert role['task_id'] == TASK and role['schema'] == 'role-result/5.1'
assert role['complete'] is True and role['unresolved'] == [] and role['conflicts'] == []
assert [item['id'] for item in candidate['checks']] == [item['id'] for item in env['validators']]
assert all(item['status'] == 'PASS' for item in candidate['checks'])
assert role['checks'] and [(x['id'], x['status']) for x in role['checks']] == [(x['id'], x['status']) for x in candidate['checks']]
for item in candidate['checks']:
    for uri in item['evidence']:
        path = resolve(uri)
        assert path.is_file(), uri
        assert row['evidence_hashes'][uri] == sha(path), uri
for item in env['inputs'] + env['resources']:
    assert sha(resolve(item['uri'])) == item['sha256'], item['uri']
assert env['module'] == candidate['module_receipts'][0]
assert env['module']['name'] == role['module_receipt']['name']
assert env['module']['version'] == role['module_receipt']['version']
assert role['module_receipt']['skill_sha256'] == sha(MODULE / 'SKILL.md')
assert set((x['path'], x['sha256']) for x in role['module_receipt']['reads']) == set((str(resolve(x['uri'])), x['sha256']) for x in env['resources'])
assert all(sha(pathlib.Path(x['path'])) == x['sha256'] for x in role['module_receipt']['reads'])
assert all(state[dep['task_id']]['state'] == 'ACCEPTED' for dep in env['dependencies'])
module_evidence = {
    'check': 'module_receipt', 'status': 'PASS',
    'module': env['module'], 'candidate_digest': csha(candidate),
    'frozen_inputs_verified': [x['uri'] for x in env['inputs']],
    'resource_files_verified': [x['uri'] for x in env['resources']],
    'creator_result_sha256': sha(CAND / 'role-result.json'),
    'art_sha256': sha(CAND / 'art-ir.json'),
    'finding': 'Frozen Canon, DirectorIR, V5 task and four locked Art resources match the declared hashes; the creator receipt and candidate/result/artifact bindings agree.'
}

cmd = [PYTHON, str(MODULE / 'scripts/art_compile.py'), 'validate', str(CAND / 'art-ir.json')]
proc = subprocess.run(cmd, capture_output=True, text=True)
assert proc.returncode == 0, (proc.stdout, proc.stderr)
native = json.loads(proc.stdout)
assert native == {'art_sha256': sha(CAND / 'art-ir.json'), 'status': 'STATIC_VALID'}
assert read(CAND / 'evidence/native-validator.json')['stdout'] == native
assert role['validator'] == native
comp = CAND / 'compiled'
recomp = OUT / 'native-recompile'
files = sorted(str(x.relative_to(comp)) for x in comp.rglob('*') if x.is_file())
refiles = sorted(str(x.relative_to(recomp)) for x in recomp.rglob('*') if x.is_file())
assert files == refiles and len(files) == 14
for name in files:
    assert sha(comp / name) == sha(recomp / name), name
receipt = read(comp / 'receipt.json')
qa = read(comp / 'qa-report.json')
assert receipt['validation'] == 'STATIC_VALID'
assert receipt['status'] == 'PLANNED' and receipt['submitted'] is False
assert receipt['media_acceptance'] == 'NOT_RUN' and receipt['coverage'] == 'EXPLICIT_MAPPING_NOT_VISUAL_PASS'
assert receipt['blockers'] == [] and qa['status'] == 'NOT_RUN'
assert all(x['result'] == 'NOT_RUN' for x in qa['records'])
assert art['contract']['execution']['mode'] == 'plan_only' and art['contract']['execution']['budget_amount'] == 0
assert all(x['status'] == 'planned' and x['file'] is None and x['sha256'] is None for x in art['references'])
native_evidence = {
    'check': 'native_validator', 'status': 'PASS', 'command': cmd,
    'native_validation': native, 'candidate_compiled_files_reproduced': len(files),
    'compiled_receipt_sha256': sha(comp / 'receipt.json'),
    'compiled_qa_sha256': sha(comp / 'qa-report.json'),
    'compiled_status': receipt['status'], 'media_acceptance': receipt['media_acceptance'],
    'finding': 'The locked Art 1.3.3 validator independently returns STATIC_VALID, and all 14 compiled files match a fresh independent compile byte for byte. Static handoff remains PLANNED; media QA is NOT_RUN.'
}

assert [x['id'] for x in art['shots']] == ['S_HANDOFF', 'S_SEAL', 'S_STOW']
assert [x['director_pointer'] for x in art['shots']] == ['/shots/0', '/shots/1', '/shots/2']
assert [x['id'] for x in director['shots']] == [x['id'] for x in art['shots']]
assert art['canon']['uri'] == str(resolve(env['inputs'][0]['uri']))
assert art['director']['uri'] == str(resolve(env['inputs'][1]['uri']))
assert art['director']['sha256'] == env['inputs'][1]['sha256']
assert {x['id'] for x in canon['entities']} == {x['id'] for x in art['assets']}
assert all(x['id'] == x['entity_id'] for x in art['assets'])
assert art['set']['scene_id'] == env['scope']['ids'][0]
assert len(art['events']) == 2
for event in art['events']:
    action = pointer(director, event['director_pointer'])
    assert event['shot_id'] in action['shot_ids']
    assert any(change['entity_id'] == event['asset_id'] and change['field'] == event['field'] and change['before'] == event['before'] and change['after'] == event['after'] for change in action['changes'])
assert [x['id'] for x in director['timeline']['actions']] == ['EVENT_HANDOFF', 'EVENT_SEAL_CHECK', 'EVENT_STOW']
assert art['events'][0]['director_pointer'] == '/timeline/actions/1'
assert art['events'][1]['director_pointer'] == '/timeline/actions/2'
assert art['events'][0]['after'] == '已确认同一封信封口完整'
assert art['events'][1]['after'] == '收纳同一封信'
assert '雨夜' in art['world']['thesis'] and '具体室内外' in art['set']['atmosphere']
assert '不提前展示验封或入包结果' in art['shots'][0]['composition_support']['negative_space']
assert '不提前显示入包' in art['shots'][1]['composition_support']['negative_space']
assert '8500毫秒后信完全在背包内' in art['shots'][2]['composition_support']['background']
assert '终帧只见乙手退出与背包口' in art['shots'][2]['composition_support']['occlusion']
assert all(not shot['dialogue'] for shot in director['shots'])
assert not any(x.get('kind') == 'dialogue' for x in director['timeline'].get('audio_events', []))
required = {x['id']: x for x in frozen['handoff']['required_handoffs']}
assert set(required) == {x['requirement_id'] for x in role['handoff']}
for mapping in role['handoff']:
    assert mapping['source_fingerprint'] == required[mapping['requirement_id']]['source_fingerprint']
    assert mapping['target_clause'] in {x['id'] for x in art['contract']['clauses']}
    for check in mapping['target_checks']:
        value = pointer(art, check['path'])
        assert (value == check['value']) if check['op'] == 'equals' else (check['value'] in value), check
assert role['handoff'] == read(CAND / 'evidence/handoff-v5.json')['mappings']
assert [(x['requirement_id'], x['source_slot'], x['source_version'], x['target_slot'], x['target_pointer']) for x in candidate['handoffs']] == [(x['requirement_id'], x['source_slot'], x['source_version'], x['target_slot'], x['target_pointer']) for x in env['handoffs']]
for handoff in candidate['handoffs']:
    ev = read(resolve(handoff['evidence'][0]))
    source = next(x for x in env['inputs'] if x['slot'] == handoff['source_slot'])
    assert ev['requirement_id'] == handoff['requirement_id']
    assert ev['input'] == {k: source[k] for k in ['sha256', 'slot', 'uri']}
    assert ev['media_review'] == 'NOT_RUN'
compiled_handoff = read(comp / 'handoff.json')
shots = {x['id']: x for x in compiled_handoff['shots']}
assert shots['S_HANDOFF']['state_after']['CHAR_YI']['condition'] == '尚未确认封口'
assert shots['S_SEAL']['state_after']['CHAR_YI']['condition'] == '已确认同一封信封口完整'
assert shots['S_STOW']['state_after']['PROP_BACKPACK']['condition'] == '收纳同一封信'
assert all(x['state_after']['PROP_LETTER']['condition'] == '同一封未拆、封口完整' for x in shots.values())
assert [[e['id'] for e in x['events']] for x in compiled_handoff['shots']] == [[], ['ART_SEAL_CONFIRMED'], ['ART_BACKPACK_STOWED']]
assert compiled_handoff['runnable'] is False and compiled_handoff['execution_implemented'] is False and compiled_handoff['api_submission_allowed'] is False
samples = {x['at_ms']: x['entities'] for x in director['timeline']['state_samples']}
assert samples[9000]['PROP_BACKPACK']['condition'] == '收纳同一封信'
assert 'PROP_BACKPACK.interior' in samples[9000]['PROP_LETTER']['contacts']
assert 'PROP_BACKPACK.interior' in samples[9000]['PROP_LETTER']['supports']
assert samples[9000]['PROP_LETTER']['controllers'] == []
assert 'N_PROP_LETTER' not in director['timeline']['composition_tracks'][-1]['attention_order']
handoff_evidence = {
    'check': 'handoff', 'status': 'PASS',
    'source_requirements_verified': sorted(required),
    'source_fingerprints_match': True,
    'v5_target_assertions_verified': sum(len(x['target_checks']) for x in role['handoff']),
    'v6_handoffs_verified': [x['requirement_id'] for x in candidate['handoffs']],
    'art_events_bound_to_director_actions': [x['director_pointer'] for x in art['events']],
    'compiled_terminal_states': {
        'handoff_unconfirmed': shots['S_HANDOFF']['state_after']['CHAR_YI']['condition'],
        'seal_confirmed': shots['S_SEAL']['state_after']['CHAR_YI']['condition'],
        'backpack_stowed': shots['S_STOW']['state_after']['PROP_BACKPACK']['condition'],
        'letter_unopened': shots['S_STOW']['state_after']['PROP_LETTER']['condition']
    },
    'media_review': 'NOT_RUN',
    'finding': 'All six frozen Director hard requirements map to native Art clauses and pass their target assertions. Both discrete Art events match the same shot/entity/field/before/after in Director timeline actions. The compiler advances seal and backpack states in order while keeping handoff control with Director. No generated media was reviewed.'
}
now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
for evidence in [module_evidence, native_evidence, handoff_evidence]:
    evidence['reviewed_at'] = now
module_uri = write('module-receipt.review.json', module_evidence)
native_uri = write('native-validator.review.json', native_evidence)
handoff_uri = write('handoff.review.json', handoff_evidence)
record = {
    'schema': 'review-record/6.0', 'task_id': TASK, 'batch': BATCH,
    'reviewer_agent_id': REVIEWER,
    'reviewer_dispatch_id': row['review_dispatch']['dispatch_id'],
    'candidate_digest': csha(candidate),
    'checks': [
        {'id': 'module_receipt', 'status': 'PASS', 'evidence': [module_uri]},
        {'id': 'native_validator', 'status': 'PASS', 'evidence': [native_uri]},
        {'id': 'handoff', 'status': 'PASS', 'evidence': [handoff_uri]}
    ],
    'failure_owner': None, 'at': now
}
write('review-record.json', record)
print(json.dumps({'review_uri': 'runtime/v6/reviews/' + TASK + '/1/review-record.json', 'review_sha256': sha(OUT / 'review-record.json'), 'candidate_digest': record['candidate_digest'], 'checks': [x['id'] + ':' + x['status'] for x in record['checks']]}, ensure_ascii=False))
