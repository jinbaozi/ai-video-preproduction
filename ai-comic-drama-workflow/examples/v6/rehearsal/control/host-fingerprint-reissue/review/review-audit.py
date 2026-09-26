import collections
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from ai_comic_drama_workflow.v5_adapters import encoded, storyboard_to_avir
from ai_comic_drama_workflow.v5_protocol import validate_protocol as validate_v5
from ai_comic_drama_workflow.v6_protocol import candidate_digest, validate_v6_protocol


ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
TASK = 'TASK_f2d0f9805f575ed23ebfdb6d'
REVIEWER = '/root/host_bridge/v6_92b84faa63ee0c7816752382'
DISPATCH = 'review-5d0ef8d940c1a4f3bc57622c'
BASE = Path(__file__).parent
PREFIX = f'runtime/v6/reviews/{TASK}/1/'
OUT = ROOT / f'runtime/v6/candidates/{TASK}/1'
PACK = OUT / 'control-pack'
MODULE = ROOT / 'runtime/modules/ff88d829cbbcb9c724b7afa3e1c85b0310deeb635284241230e3439fb6c41d4b/video-prompt-compiler'
ACTION = ROOT / 'runtime/v6/host-inputs/hostfix-control-review-action.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def put(name, value):
    path = BASE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
    return path


def run(*arguments):
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = subprocess.run([sys.executable, *map(str, arguments)], capture_output=True,
                          text=True, env=env)
    assert proc.returncode == 0, {'arguments': [str(x) for x in arguments],
                                  'stdout': proc.stdout, 'stderr': proc.stderr}
    return json.loads(proc.stdout)


action = load(ACTION)
assert action['dispatch_id'] == DISPATCH and action['task_id'] == TASK
state = load(ROOT / 'runtime/v6/state.json')
env = state['tasks'][TASK]['envelope']
assert env['task_id'] == TASK and env['batch'] == 1 and env['role'] == 'control'
assert env['input_digest'] == '31b81c547956ff58bf81e2542c429da8b4542d07ac46af34587b3e34a6aeba7b'
candidate = load(OUT / 'candidate-result.json')
validate_v6_protocol('candidate-result', candidate)
assert candidate['agent_id'] != REVIEWER
assert candidate['task_id'] == TASK and candidate['batch'] == 1
assert candidate['input_digest'] == env['input_digest']
assert candidate['module_receipts'] == [env['module']]
assert {row['id'] for row in candidate['checks']} == {row['id'] for row in env['validators']}
assert all(row['status'] == 'PASS' for row in candidate['checks'])
assert candidate['unresolved'] == []
digest = candidate_digest(candidate)
assert candidate['artifacts'] == [{
    'slot': env['expected_artifacts'][0]['slot'], 'kind': 'ShotControlPack',
    'uri': f'runtime/v6/candidates/{TASK}/1/control-pack/package-manifest.json',
    'sha256': sha(PACK / 'package-manifest.json')}]
assert candidate['result_sha256'] == sha(ROOT / candidate['result_uri'])
validate_v5('role-result', load(ROOT / candidate['result_uri']))

frozen_rows = []
for item in env['inputs'] + env['resources']:
    actual = sha(ROOT / item['uri'])
    assert actual == item['sha256'], (item['uri'], actual, item['sha256'])
    frozen_rows.append({'uri': item['uri'], 'sha256': actual})
evidence_rows = []
for check in candidate['checks']:
    for uri in check['evidence']:
        assert uri.startswith(f'runtime/v6/candidates/{TASK}/1/evidence/')
        evidence_rows.append({'uri': uri, 'sha256': sha(ROOT / uri)})
evidence_rows = list({row['uri']: row for row in evidence_rows}.values())

task5 = load(ROOT / env['inputs'][1]['uri'])
source = load(ROOT / env['inputs'][0]['uri'])
promoted_path = Path(task5['inputs'][0]['uri'])
assert sha(promoted_path) == task5['inputs'][0]['sha256']
promoted = load(promoted_path)
differences = []


def compare(left, right, pointer=''):
    if type(left) is not type(right):
        differences.append(pointer)
    elif isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            sub = pointer + '/' + key
            if key not in left or key not in right:
                differences.append(sub)
            else:
                compare(left[key], right[key], sub)
    elif isinstance(left, list):
        if len(left) != len(right):
            differences.append(pointer + '/length')
        for index, (a, b) in enumerate(zip(left, right)):
            compare(a, b, pointer + '/' + str(index))
    elif left != right:
        differences.append(pointer)


compare(source, promoted)
allowed = {f'/sources/{index}/uri' for index in range(5)}
allowed.add('/timeline/semantic_review/input_sha256')
allowed |= {f'/upstreams/{index}/{key}' for index in range(len(source['upstreams']))
            for key in ('sha256', 'uri')}
assert set(differences) == allowed
assert load(OUT / 'evidence/promotion-diff.json')['diff_count'] == len(differences)
module_receipt = {
    'schema': 'control-module-review/1.0',
    'candidate_digest': digest,
    'result': 'PASS',
    'module': env['module'],
    'frozen_input_revision': env['input_revision'],
    'frozen_input_digest': env['input_digest'],
    'frozen_inputs_and_resources': frozen_rows,
    'candidate_evidence_hashes': evidence_rows,
    'result_sha256': candidate['result_sha256'],
    'manifest_sha256': candidate['artifacts'][0]['sha256'],
    'promotion_diff_pointers': sorted(differences),
    'promotion_changed_only_rebinding_metadata': True,
}
put('module-receipt.review.json', module_receipt)

expected_avir, adapter_report = storyboard_to_avir(promoted, ROOT)
assert adapter_report['status'] == 'MAPPED' and adapter_report['losses'] == []
assert adapter_report['semantic_review'] == 'INHERITED_DETERMINISTICALLY'
assert expected_avir == load(OUT / 'native-av-ir.json')
assert expected_avir == load(PACK / 'production-specification.json')
assert sha(OUT / 'native-av-ir.json') == sha(PACK / 'production-specification.json')
assert (OUT / 'control-config.json').read_bytes() == (PACK / 'control-config.json').read_bytes()
native = run(MODULE / 'scripts/vpc.py', 'validate', OUT / 'native-av-ir.json')
assert native['status'] == 'VALID' and native['diagnostics'] == []
verified = run(MODULE / 'scripts/control_cli.py', 'verify', PACK)
assert verified['status'] == 'VERIFIED' and verified['media_review'] == 'NOT_RUN'

rebuild = BASE / 'independent-control-build'
assert not rebuild.exists()
built = run(MODULE / 'scripts/control_cli.py', 'build', OUT / 'native-av-ir.json',
            '--config', OUT / 'control-config.json', '--out', rebuild)
reverified = run(MODULE / 'scripts/control_cli.py', 'verify', rebuild)
assert reverified['status'] == 'VERIFIED' and reverified['media_review'] == 'NOT_RUN'
manifest = load(PACK / 'package-manifest.json')
rebuild_manifest = load(rebuild / 'package-manifest.json')
assert manifest == rebuild_manifest
assert all(sha(PACK / name) == value for name, value in manifest['files'].items())
assert all((PACK / name).read_bytes() == (rebuild / name).read_bytes()
           for name in manifest['files'])
assert sha(PACK / 'package-manifest.json') == sha(rebuild / 'package-manifest.json')
frames = load(PACK / 'review/frames.json')
assert len(frames) == 121
camera_counts = dict(collections.Counter(row['camera']['status'] for row in frames))
assert camera_counts == {'PLANNED_PROJECTION': 121}
assert all(row['camera']['position'] == [0, 1.2, -2.8] for row in frames)
requests = load(PACK / 'keyframe-requests.json')
assert len(requests) == 14
assert all(row['status'] == 'DRAFT_REQUIRES_HOST_REVIEW' and row['generated'] is False
           and row['visual_review'] == 'NOT_RUN' for row in requests)
assert len(load(PACK / 'control-coverage.json')) == 17
sample_10500 = next(row for row in promoted['timeline']['state_samples'] if row['at_ms'] == 10500)
sample_12000 = next(row for row in promoted['timeline']['state_samples'] if row['at_ms'] == 12000)
end = next(row for row in expected_avir['shots'][0]['end_state']
           if row['entity_id'] == 'PROP_LETTER')
end_sample = next(row for row in expected_avir['timeline']['state_samples']
                  if row['at_ms'] == 12000)
frame_end = next(row for row in frames if row['at_ms'] == 12000)
letter_values = {
    'storyboard_10500ms': sample_10500['entities']['PROP_LETTER']['visible_parts'],
    'storyboard_12000ms': sample_12000['entities']['PROP_LETTER']['visible_parts'],
    'avir_shot_end': end['visible_parts'],
    'avir_timeline_12000ms': end_sample['entities']['PROP_LETTER']['visible_parts'],
    'control_frame_12000ms': frame_end['state']['state']['PROP_LETTER']['visible_parts'],
}
assert all(value == [] for value in letter_values.values()), letter_values
assert all(row['entity_id'] != 'PROP_LETTER' or row['end_ms'] <= 10500
           for row in expected_avir['timeline']['visibility'])
old_review = load(ROOT / 'runtime/v6/candidates/TASK_ede3a3425d547d3569e53ec4/1/compile-review.json')
assert old_review['finding_code'] == 'AVIR_END_VISIBILITY_CONFLICT'
assert old_review['visibility_conflict']['avir_shot_end_value'] == ['body', 'prop']
assert old_review['visibility_conflict']['avir_timeline_value'] == []
control_review = {
    'schema': 'control-verification-review/1.0',
    'candidate_digest': digest,
    'result': 'PASS',
    'independent_native_validation': native,
    'independent_locked_control_verify': verified,
    'independent_locked_control_rebuild': built,
    'independent_rebuild_verify': reverified,
    'manifest_member_hashes_match': True,
    'independent_rebuild_matches_all_candidate_files': True,
    'manifest_file_count': len(manifest['files']),
    'frame_count': len(frames),
    'camera_status_counts': camera_counts,
    'camera_position_m': [0, 1.2, -2.8],
    'keyframe_request_count': len(requests),
    'coverage_count': 17,
    'letter_boundary_visible_parts': letter_values,
    'prior_defect': old_review['finding_code'],
    'prior_wrong_end_visible_parts': ['body', 'prop'],
    'current_end_visible_parts': [],
    'adapter_status': adapter_report['status'],
    'adapter_losses': adapter_report['losses'],
    'semantic_review': adapter_report['semantic_review'],
    'lens_basis': 'authored_proxy',
    'actual_media_review': 'NOT_RUN',
    'actual_model_camera_trajectory_validation': 'NOT_RUN',
    'actual_contact_review': 'NOT_RUN',
    'generated_images': False,
    'generated_video': False,
}
put('control-verify.review.json', control_review)

director_path = Path(source['upstreams'][1]['uri'])
assert sha(director_path) == source['upstreams'][1]['sha256']
director = load(director_path)
director_camera = director['shots'][0]['camera']
story_camera = source['shots'][0]['camera']
assert director_camera['start_m'] == director_camera['end_m'] == [0, -2.8, 1.2]
assert story_camera['start_m'] == story_camera['end_m'] == [0, 1.2, -2.8]
assert [director_camera['start_m'][0], director_camera['start_m'][2],
        director_camera['start_m'][1]] == story_camera['start_m']
assert '[0,1.2,-2.8]' in source['timeline']['camera_operations'][0]['start_position']
assert '[0,1.2,-2.8]' in source['timeline']['camera_operations'][0]['end_position']
handoff = env['handoffs'][0]
assert candidate['handoffs'] == [dict(handoff, evidence=candidate['handoffs'][0]['evidence'])]
assert sha(ROOT / env['inputs'][0]['uri']) == env['inputs'][0]['sha256']
handoff_review = {
    'schema': 'control-handoff-review/1.0',
    'candidate_digest': digest,
    'result': 'PASS',
    'requirement_id': handoff['requirement_id'],
    'source_slot': handoff['source_slot'],
    'source_version': handoff['source_version'],
    'source_sha256': env['inputs'][0]['sha256'],
    'source_task_id': env['dependencies'][0]['task_id'],
    'target_slot': handoff['target_slot'],
    'target_manifest_sha256': sha(PACK / 'package-manifest.json'),
    'target_avir_sha256': sha(OUT / 'native-av-ir.json'),
    'storyboard_coordinate_system': source['scenes'][0]['coordinates'],
    'director_coordinate_system': director['scenes'][0]['coordinate_system'],
    'director_camera_m': director_camera['start_m'],
    'storyboard_camera_m': story_camera['start_m'],
    'mapping': 'storyboard [x,y,z] = director [X,Z,Y]',
    'camera_track_matches_locked_operation': True,
    'letter_boundary_visible_parts': letter_values,
    'media': 'NOT_RUN',
}
put('handoff.review.json', handoff_review)

review = {
    'schema': 'review-record/6.0', 'task_id': TASK, 'batch': 1,
    'reviewer_agent_id': REVIEWER, 'reviewer_dispatch_id': DISPATCH,
    'candidate_digest': digest, 'at': datetime.now(timezone.utc).isoformat(),
    'checks': [
        {'id': 'module_receipt', 'status': 'PASS',
         'evidence': [PREFIX + 'module-receipt.review.json']},
        {'id': 'control_verify', 'status': 'PASS',
         'evidence': [PREFIX + 'control-verify.review.json']},
        {'id': 'handoff', 'status': 'PASS',
         'evidence': [PREFIX + 'handoff.review.json']},
    ],
    'failure_owner': None,
}
validate_v6_protocol('review-record', review)
path = put('review-record.json', review)
print(json.dumps({'review_uri': PREFIX + path.name, 'review_sha256': sha(path),
                  'candidate_digest': digest, 'checks': [x['id'] for x in review['checks']],
                  'media': 'NOT_RUN'}, ensure_ascii=False))
