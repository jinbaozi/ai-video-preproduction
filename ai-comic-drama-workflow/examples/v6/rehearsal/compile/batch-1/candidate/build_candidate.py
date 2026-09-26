"""Freeze one V6 compile candidate from the exact accepted native build."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
TASK_ID = 'V6_compile_8cb5698095d1a70e0b6b'
HERE = ROOT / 'runtime/v6/candidates' / TASK_ID / '1'
EVIDENCE = HERE / 'evidence'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(name, value):
    path = EVIDENCE / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return path.relative_to(ROOT).as_posix()

def recursive_diff(left, right, pointer=''):
    if type(left) is not type(right):
        return [pointer]
    if isinstance(left, dict):
        out = []
        for key in sorted(set(left) | set(right)):
            at = pointer + '/' + key
            if key not in left or key not in right:
                out.append(at)
            else:
                out.extend(recursive_diff(left[key], right[key], at))
        return out
    if isinstance(left, list):
        out = []
        if len(left) != len(right):
            out.append(pointer + '/length')
        for i, (a, b) in enumerate(zip(left, right)):
            out.extend(recursive_diff(a, b, pointer + '/' + str(i)))
        return out
    return [] if left == right else [pointer]

state = read(ROOT / 'runtime/v6/state.json')
task = state['tasks'][TASK_ID]
envelope = task['envelope']
assert task['state'] == 'RUNNING'
assert envelope['schema'] == 'task-envelope/6.0' and envelope['batch'] == 1
assert task['receipt']['agent_id'] == '/root/host_bridge/v6_28e4632f6a12c66dc9ad12ef'
assert envelope['node_id'] == 'compile' and envelope['role'] == 'compiler'
assert len(envelope['inputs']) == 27 and len(envelope['resources']) == 5
assert len(envelope['expected_artifacts']) == 2
input_audit = []
for item in envelope['inputs']:
    path = ROOT / item['uri']
    observed = sha(path)
    assert observed == item['sha256'], item['uri']
    input_audit.append({'slot': item['slot'], 'uri': item['uri'], 'sha256': observed,
                        'version': item['version'], 'bytes': path.stat().st_size})
resource_audit = []
for item in envelope['resources']:
    path = ROOT / item['uri']
    observed = sha(path)
    assert observed == item['sha256'], item['uri']
    resource_audit.append({'uri': item['uri'], 'sha256': observed, 'bytes': path.stat().st_size})
module_root = (ROOT / envelope['resources'][0]['uri']).parent
module_report_uri = write('module-receipt.json', {
    'status': 'PASS', 'module': envelope['module'], 'input_digest': envelope['input_digest'],
    'inputs': input_audit, 'locked_resources': resource_audit,
})

brief = read(ROOT / envelope['inputs'][2]['uri'])
build_root = ROOT / brief['build_uri']
compiled = build_root / 'compiled'
assert brief['node_id'] == 'compile' and len(brief['files']) == 24
assert {x['uri']: x['sha256'] for x in envelope['inputs'][3:]} == brief['files']
v5 = read(ROOT / 'state.json')
assert v5['build']['files'] == brief['files']
assert v5['build']['build_id'] == brief['build_id']
assert v5['build']['uri'] == brief['build_uri']
manifest = read(compiled / 'compile-manifest.json')
assert manifest['build_id'] == brief['build_id']
assert manifest['target'] == 'seedance2.0' and manifest['mode'] == 'text'
assert manifest['compiler'] == 'video-prompt-compiler@1.17.6'
assert len(manifest['files']) == 20
assert all(sha(compiled / name) == expected for name, expected in manifest['files'].items())
assert all(sha(module_root / name) == expected for name, expected in manifest['runtime_files'].items())
assert sha(module_root / 'SKILL.md') == envelope['resources'][0]['sha256']
attachments = read(build_root / 'attachments.json')
assert attachments == {'attachments': [], 'submitted': False}
capability = read(compiled / 'capability-snapshot.json')
assert capability['id'] == manifest['target']
assert capability['backend'] == 'prompt_plan'
assert capability['entry_point'] == 'model_prompt_plan; current transport unresolved'
assert capability['account_verified'] is False
routing_path = ROOT / 'runtime/v6/host-inputs/target-routing-evidence.json'
routing = read(routing_path)
assert routing['target'] == manifest['target']
assert routing['profile_backend'] == capability['backend']
assert routing['profile_entry_point'] == capability['entry_point']
assert routing['locked_module_sha256'] == envelope['module']['sha256']
assert sha(module_root / 'registries/capabilities.json') == routing['locked_registry_sha256']

# Use the locked native CLI for both IR and package verification.
env = os.environ.copy()
env['PYTHONDONTWRITEBYTECODE'] = '1'
cli = [sys.executable, str(module_root / 'scripts/vpc.py')]
validation = subprocess.run(cli + ['validate', str(build_root / 'avir.json')],
                            text=True, capture_output=True, env=env)
assert validation.returncode == 0, validation.stderr + validation.stdout
validation_json = json.loads(validation.stdout)
assert validation_json == {'status': 'VALID', 'diagnostics': []}
verify = subprocess.run(cli + ['verify', str(compiled)],
                        text=True, capture_output=True, env=env)
assert verify.returncode == 0, verify.stderr + verify.stdout
verify_json = json.loads(verify.stdout)
assert verify_json == {'status': 'VERIFIED', 'build_id': manifest['build_id']}
assert (build_root / 'avir.json').read_bytes() == (compiled / 'avir.json').read_bytes()
assert (build_root / 'avir.json').read_bytes() == (compiled / 'production-specification.json').read_bytes()
shutil.copyfile(build_root / 'avir.json', HERE / 'avir.json')
shutil.copyfile(compiled / 'compile-manifest.json', HERE / 'compile-manifest.json')
native_report_uri = write('native-validator.json', {
    'status': 'PASS', 'command': 'locked scripts/vpc.py validate frozen avir.json',
    'exit_code': validation.returncode, 'result': validation_json,
    'input_sha256': sha(build_root / 'avir.json'),
})

artifact = read(compiled / 'artifact.json')
segment = read(compiled / 'segment-delivery.json')
post = read(compiled / 'post-production.json')
losses = read(compiled / 'loss-report.json')
constraint = read(compiled / 'constraint-coverage.json')
detail = read(compiled / 'detail-coverage.json')
prompt_coverage = read(compiled / 'prompt-coverage.json')
prompt_review = read(compiled / 'prompt-review.json')
spatial = read(compiled / 'spatial-checks.json')
mapping = read(build_root / 'mapping.json')
assert artifact['status'] == 'COMPILED' and artifact['target'] == manifest['target']
assert artifact['execution']['submitted'] is False and artifact['execution']['runnable'] is False
assert artifact['execution']['media_qa'] == 'NOT_RUN'
assert mapping['status'] == 'MAPPED' and mapping['losses'] == []
assert mapping['submitted'] is False and mapping['media_qa'] == 'NOT_RUN'
assert losses == []
assert segment['status'] == 'DRAFT_REQUIRES_TARGET_CHECK'
assert segment['execution'] == 'NOT_RUN'
assert all(x['status'] == 'DRAFT_REQUIRES_TARGET_CHECK' and x['execution'] == 'NOT_RUN' for x in segment['parts'])
assert prompt_review['status'] == 'PENDING_AGENT_REVIEW'
assert all(x['status'] == 'PLANNED' for x in post)
assert len(post) == 2 and {x['id'] for x in post} == {'AUD_RAIN', 'SB_MEDIA_BOUNDARY'}
assert len(artifact['coverage']) == len(constraint)
assert all(x['level'] == 'hard' and x['static_assertions'] == 'PASS' for x in constraint)
assert {x['status'] for x in constraint} == {'EMITTED', 'PLANNED'}
assert [x['id'] for x in constraint if x['status'] == 'PLANNED'] == ['SB_MEDIA_BOUNDARY']
assert len(detail) == len(artifact['detail_coverage'])
assert len(prompt_coverage) == len(artifact['prompt_coverage'])
assert all(x['status'] == 'CHECKPOINTS_PASS' and x['continuous_geometry'] == 'NOT_PROVEN' for x in spatial)
manifest_report_uri = write('compile-manifest.json', {
    'status': 'PASS', 'command': 'locked scripts/vpc.py verify frozen compiled package',
    'exit_code': verify.returncode, 'result': verify_json,
    'build_id': manifest['build_id'], 'build_files_verified': len(brief['files']),
    'compiled_files_verified': len(manifest['files']),
    'locked_runtime_files_verified': len(manifest['runtime_files']),
    'attachments': attachments, 'target_routing_evidence_uri': routing_path.relative_to(ROOT).as_posix(),
    'target_routing_evidence_sha256': sha(routing_path),
    'capability_snapshot_sha256': sha(compiled / 'capability-snapshot.json'),
    'capability_backend': capability['backend'], 'entry_point': capability['entry_point'],
    'account_verified': capability['account_verified'],
    'artifact_status': artifact['status'], 'segment_status': segment['status'],
    'segment_count': len(segment['parts']), 'prompt_review_status': prompt_review['status'],
    'loss_count': len(losses), 'constraint_count': len(constraint),
    'constraint_statuses': {status: sum(x['status'] == status for x in constraint)
                            for status in ('EMITTED', 'PLANNED')},
    'constraint_static_assertions_pass': len(constraint),
    'planned_post_constraint_ids': [x['id'] for x in constraint if x['status'] == 'PLANNED'],
    'detail_coverage_count': len(detail), 'prompt_coverage_count': len(prompt_coverage),
    'post_obligations': [{'id': x['id'], 'status': x['status'], 'channel': x['channel']} for x in post],
    'spatial_statuses': [{'id': x['id'], 'status': x['status'],
                          'continuous_geometry': x['continuous_geometry']} for x in spatial],
    'execution': artifact['execution'],
    'media_qa': mapping['media_qa'],
    'note': 'PASS proves frozen static package integrity; target submission, prompt body review, geometry in media and post audio remain separate gates.',
})

story_item, control_item = envelope['inputs'][:2]
v6_story = read(ROOT / story_item['uri'])
v5_story_record = v5['artifacts']['storyboard']
v5_story = read(ROOT / v5_story_record['uri'])
assert v5_story_record['original_sha256'] == story_item['sha256']
assert sha(ROOT / v5_story_record['uri']) == v5_story_record['sha256']
assert mapping['source_hash'] == v5_story_record['sha256']
assert mapping['sidecar'] == v5_story
changed = recursive_diff(v6_story, v5_story)
assert len(changed) == 12, changed
assert all(x.startswith('/sources/') and x.endswith('/uri')
           or x.startswith('/upstreams/') and (x.endswith('/uri') or x.endswith('/sha256'))
           or x == '/timeline/semantic_review/input_sha256' for x in changed), changed
control_manifest = read(ROOT / control_item['uri'])
control_spec = (ROOT / control_item['uri']).parent / 'production-specification.json'
assert control_manifest['files']['production-specification.json'] == sha(control_spec)
assert control_spec.read_bytes() == (build_root / 'avir.json').read_bytes()
assert mapping['target_hash'] == sha(build_root / 'avir.json')
assert state['artifacts'][story_item['slot']]['sha256'] == story_item['sha256']
assert state['artifacts'][control_item['slot']]['sha256'] == control_item['sha256']
assert state['tasks'][state['artifacts'][story_item['slot']]['task_id']]['state'] == 'ACCEPTED'
assert state['tasks'][state['artifacts'][control_item['slot']]['task_id']]['state'] == 'ACCEPTED'
assert all(state['tasks'][x['task_id']]['state'] in ('ACCEPTED', 'NOT_APPLICABLE') for x in envelope['dependencies'])
handoff_report_uri = write('handoff.json', {
    'status': 'PASS',
    'storyboard': {'source_slot': story_item['slot'], 'source_version': story_item['version'],
                   'candidate_sha256': story_item['sha256'], 'accepted': True,
                   'promoted_uri': v5_story_record['uri'],
                   'promoted_sha256': v5_story_record['sha256'],
                   'promotion_difference_paths': changed,
                   'adapter_source_hash': mapping['source_hash'],
                   'adapter_sidecar_matches_promoted_storyboard': True},
    'control': {'source_slot': control_item['slot'], 'source_version': control_item['version'],
                'manifest_sha256': control_item['sha256'], 'accepted': True,
                'production_specification_sha256': sha(control_spec)},
    'target': {'AVIR_sha256': sha(build_root / 'avir.json'),
               'equals_control_production_specification': True,
               'equals_compiler_input': True,
               'mapping_status': mapping['status'], 'mapping_losses': len(mapping['losses'])},
    'dependency_states': {x['task_id']: state['tasks'][x['task_id']]['state'] for x in envelope['dependencies']},
    'note': 'V5 promotion rebased only administrative source URIs, upstream URI/hash, and the dependent semantic stamp. The compiler adapter sidecar exactly equals the promoted StoryboardIR.',
})

artifact_by_kind = {
    'AVIR': HERE / 'avir.json',
    'CompilePackage': HERE / 'compile-manifest.json',
}
candidate = {
    'schema': 'candidate-result/6.0', 'task_id': TASK_ID, 'batch': 1,
    'agent_id': task['receipt']['agent_id'], 'input_digest': envelope['input_digest'],
    'result_uri': None, 'result_sha256': None,
    'artifacts': [{'slot': spec['slot'], 'kind': spec['kind'],
                   'uri': artifact_by_kind[spec['kind']].relative_to(ROOT).as_posix(),
                   'sha256': sha(artifact_by_kind[spec['kind']])}
                  for spec in envelope['expected_artifacts']],
    'module_receipts': [envelope['module']],
    'checks': [
        {'id': 'module_receipt', 'status': 'PASS', 'evidence': [module_report_uri]},
        {'id': 'native_validator', 'status': 'PASS', 'evidence': [native_report_uri]},
        {'id': 'compile_manifest', 'status': 'PASS', 'evidence': [manifest_report_uri]},
        {'id': 'handoff', 'status': 'PASS', 'evidence': [handoff_report_uri]},
    ],
    'handoffs': [{**h, 'evidence': [handoff_report_uri]} for h in envelope['handoffs']],
    'unresolved': [],
}
(HERE / 'candidate-result.json').write_text(
    json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
    encoding='utf-8')
print(json.dumps({'candidate': (HERE / 'candidate-result.json').relative_to(ROOT).as_posix(),
                  'sha256': sha(HERE / 'candidate-result.json'),
                  'AVIR_sha256': sha(HERE / 'avir.json'),
                  'CompilePackage_sha256': sha(HERE / 'compile-manifest.json'),
                  'checks': [x['id'] for x in candidate['checks']],
                  'segment_status': segment['status'],
                  'prompt_review_status': prompt_review['status']}, ensure_ascii=False))
