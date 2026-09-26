import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from ai_comic_drama_workflow.v5_adapters import encoded, storyboard_to_avir
from ai_comic_drama_workflow.v5_protocol import validate_protocol as validate_v5
from ai_comic_drama_workflow.v6_protocol import validate_v6_protocol

ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
TASK = 'TASK_f2d0f9805f575ed23ebfdb6d'
AGENT = '/root/host_bridge/v6_360635fbdf384545b917078b'
OUT = ROOT / 'runtime/v6/candidates' / TASK / '1'
EV = OUT / 'evidence'
PACK = OUT / 'control-pack'
PREFIX = f'runtime/v6/candidates/{TASK}/1/'
MODULE = ROOT / 'runtime/modules/ff88d829cbbcb9c724b7afa3e1c85b0310deeb635284241230e3439fb6c41d4b/video-prompt-compiler'
ENV = json.loads((ROOT / 'runtime/v6/state.json').read_text())['tasks'][TASK]['envelope']
TASK5 = json.loads((ROOT / ENV['inputs'][1]['uri']).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
    return path


def euri(name):
    return PREFIX + 'evidence/' + name


def run(*args):
    environment = os.environ.copy()
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    result = subprocess.run([sys.executable, *map(str, args)], capture_output=True,
                            text=True, env=environment)
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


assert ENV['task_id'] == TASK and ENV['role'] == 'control' and ENV['batch'] == 1
assert all(sha(ROOT / item['uri']) == item['sha256'] for item in ENV['inputs'] + ENV['resources'])
source = json.loads((ROOT / ENV['inputs'][0]['uri']).read_text())
promoted_path = Path(TASK5['inputs'][0]['uri'])
assert sha(promoted_path) == TASK5['inputs'][0]['sha256']
promoted = json.loads(promoted_path.read_text())
expected, report = storyboard_to_avir(promoted, ROOT)
actual = json.loads((PACK / 'production-specification.json').read_text())
assert actual == expected
assert sha(PACK / 'production-specification.json') == sha(OUT / 'native-av-ir.json')
assert sha(PACK / 'production-specification.json') == report['target_hash']
assert report['status'] == 'MAPPED' and not report['losses']
assert (OUT / 'control-config.json').read_bytes() == (PACK / 'control-config.json').read_bytes()

native = run(MODULE / 'scripts/vpc.py', 'validate', OUT / 'native-av-ir.json')
assert native['status'] == 'VALID' and native['diagnostics'] == []
put('evidence/native-av-validation.json', {
    'command': 'locked scripts/vpc.py validate native-av-ir.json',
    'status': native['status'], 'diagnostics': native['diagnostics'],
    'avir_sha256': sha(OUT / 'native-av-ir.json'),
    'adapter_status': report['status'], 'losses': len(report['losses'])})

fresh = run(MODULE / 'scripts/control_cli.py', 'verify', PACK)
assert fresh['status'] == 'VERIFIED' and fresh['media_review'] == 'NOT_RUN'
frames = json.loads((PACK / 'review/frames.json').read_text())
counts = dict(collections.Counter(row['camera']['status'] for row in frames))
assert len(frames) == 121 and counts == {'PLANNED_PROJECTION': 121}
assert all(row['camera']['position'] == [0, 1.2, -2.8] for row in frames)
requests = json.loads((PACK / 'keyframe-requests.json').read_text())
assert len(requests) == 14
assert all(row['status'] == 'DRAFT_REQUIRES_HOST_REVIEW'
           and row['generated'] is False and row['visual_review'] == 'NOT_RUN'
           for row in requests)
manifest_path = PACK / 'package-manifest.json'
manifest_sha = sha(manifest_path)
manifest = json.loads(manifest_path.read_text())
assert all(sha(PACK / name) == value for name, value in manifest['files'].items())
assert len(json.loads((PACK / 'control-coverage.json').read_text())) == 17
end_state = next(row for row in actual['shots'][0]['end_state'] if row['entity_id'] == 'PROP_LETTER')
end_sample = next(row for row in actual['timeline']['state_samples'] if row['at_ms'] == 12000)
frame_end = next(row for row in frames if row['at_ms'] == 12000)
assert end_state['visible_parts'] == []
assert end_sample['entities']['PROP_LETTER']['visible_parts'] == []
assert frame_end['state']['state']['PROP_LETTER']['visible_parts'] == []
assert all(row['entity_id'] != 'PROP_LETTER' or row['end_ms'] <= 10500
           for row in actual['timeline']['visibility'])
put('evidence/control-build.json', {
    'command': 'locked scripts/control_cli.py build native-av-ir.json --config control-config.json --out control-pack',
    'status': 'DERIVED', 'manifest_sha256': manifest_sha,
    'keyframe_requests': len(requests), 'projection_unresolved_frames': 0,
    'video_generated': False, 'execution': 'NOT_RUN'})
put('evidence/control-verify.json', {
    'command': 'locked scripts/control_cli.py verify control-pack',
    'status': fresh['status'], 'media_review': fresh['media_review'],
    'manifest_sha256': manifest_sha, 'file_count': len(manifest['files']),
    'frame_count': len(frames), 'camera_status_counts': counts,
    'keyframe_requests': len(requests), 'coverage_items': 17,
    'production_specification_equals_current_storyboard_conversion': True,
    'production_specification_bytes_match_native_avir': True,
    'letter_12000ms_shot_end_visible_parts': end_state['visible_parts'],
    'letter_12000ms_timeline_visible_parts': end_sample['entities']['PROP_LETTER']['visible_parts'],
    'letter_12000ms_control_frame_visible_parts': frame_end['state']['state']['PROP_LETTER']['visible_parts'],
    'model_submitted': False, 'visual_review': 'NOT_RUN'})

camera = source['shots'][0]['camera']
director_file = Path(source['upstreams'][1]['uri'])
assert sha(director_file) == source['upstreams'][1]['sha256']
director = json.loads(director_file.read_text())
director_camera = director['shots'][0]['camera']
assert director_camera['start_m'] == director_camera['end_m'] == [0, -2.8, 1.2]
assert camera['start_m'] == camera['end_m'] == [0, 1.2, -2.8]
assert [director_camera['start_m'][0], director_camera['start_m'][2],
        director_camera['start_m'][1]] == camera['start_m']
put('evidence/coordinate-consistency.json', {
    'schema': 'control-coordinate-evidence/1.0',
    'director_sha256': sha(director_file),
    'director_coordinate_system': director['scenes'][0]['coordinate_system'],
    'director_scene_camera_m': director_camera['start_m'],
    'storyboard_coordinate_system': source['scenes'][0]['coordinates'],
    'storyboard_timeline_camera_m': camera['start_m'],
    'mapping': 'storyboard [x,y,z] = director [X,Z,Y]',
    'camera_operation_id': source['timeline']['camera_operations'][0]['id'],
    'camera_operation_start_position': source['timeline']['camera_operations'][0]['start_position'],
    'camera_operation_end_position': source['timeline']['camera_operations'][0]['end_position'],
    'result': 'CONSISTENT_PLANNING_INTENT',
    'actual_model_trajectory': 'NOT_RUN'})

prior_review_path = ROOT / 'runtime/v6/candidates/TASK_ede3a3425d547d3569e53ec4/1/compile-review.json'
prior_review = json.loads(prior_review_path.read_text())
assert prior_review['finding_code'] == 'AVIR_END_VISIBILITY_CONFLICT'
old = prior_review['visibility_conflict']
assert old['avir_shot_end_value'] == ['body', 'prop']
assert old['avir_timeline_value'] == []
put('evidence/prior-defect-closure.json', {
    'schema': 'control-defect-closure/1.0',
    'prior_compile_review_uri': str(prior_review_path.relative_to(ROOT)),
    'prior_compile_review_sha256': sha(prior_review_path),
    'finding_code': prior_review['finding_code'],
    'old_avir_sha256': old['avir_sha256'],
    'old_shot_end_visible_parts': old['avir_shot_end_value'],
    'current_avir_sha256': sha(OUT / 'native-av-ir.json'),
    'current_shot_end_visible_parts': end_state['visible_parts'],
    'current_timeline_12000ms_visible_parts': end_sample['entities']['PROP_LETTER']['visible_parts'],
    'current_control_frame_12000ms_visible_parts': frame_end['state']['state']['PROP_LETTER']['visible_parts'],
    'exact_changed_fields': [
        '/shots/0/start_state/3/visible_parts',
        '/shots/0/start_state/4/visible_parts',
        '/shots/0/end_state/3/visible_parts',
        '/shots/0/end_state/4/visible_parts'],
    'mapping_rule': 'STATE_SAMPLE.BOUNDARY_VISIBILITY.1.1',
    'closure': 'BOUNDARY_FIELDS_NOW_MATCH_AUTHORITATIVE_SAMPLES',
    'new_compiled_prompt_review': 'NOT_RUN',
    'media_review': 'NOT_RUN'})
put('evidence/projection-limit.json', {
    'schema': 'control-projection-limit/1.0',
    'status': 'PLANNED_PROJECTION', 'planned_frames': len(frames),
    'undetermined_camera_frames': 0,
    'camera_position_m': [0, 1.2, -2.8],
    'lens_basis': 'authored_proxy', 'vertical_fov_deg': 50,
    'control_assets': [], 'keyframe_requests': len(requests),
    'generated_images': False, 'generated_video': False,
    'actual_camera_trajectory_validation': 'NOT_RUN',
    'actual_character_motion_review': 'NOT_RUN',
    'actual_contact_review': 'NOT_RUN',
    'actual_media_review': 'NOT_RUN'})

handoff = ENV['handoffs'][0]
put('evidence/handoff.json', {
    'schema': 'control-handoff/1.0',
    'requirement_id': handoff['requirement_id'],
    'source_slot': handoff['source_slot'], 'source_version': handoff['source_version'],
    'source_candidate_sha256': sha(ROOT / ENV['inputs'][0]['uri']),
    'source_promoted_sha256': sha(promoted_path),
    'source_promotion_diff': euri('promotion-diff.json'),
    'target_slot': handoff['target_slot'], 'target_pointer': handoff['target_pointer'],
    'target_manifest_uri': PREFIX + 'control-pack/package-manifest.json',
    'target_manifest_sha256': manifest_sha,
    'target_avir_sha256': sha(OUT / 'native-av-ir.json'),
    'source_boundary_mapping_evidence': euri('boundary-visibility.json'),
    'scope': 'S1 / 0–12000 ms fixed camera and action planning',
    'media': 'NOT_RUN'})

checks = [
    {'id': 'module_receipt', 'status': 'PASS',
     'evidence': [euri('source-integrity.json'), euri('module-receipt.json'),
                  euri('promotion-diff.json')],
     'finding': 'Frozen inputs and locked resource bytes match; V5 promotion changes only source/review binding metadata.'},
    {'id': 'control_verify', 'status': 'PASS',
     'evidence': [euri('adapter-report.json'), euri('native-av-validation.json'),
                  euri('boundary-visibility.json'), euri('prior-defect-closure.json'),
                  euri('coordinate-consistency.json'), euri('control-build.json'),
                  euri('control-verify.json'), euri('projection-limit.json')],
     'finding': 'Current locked adapter MAPPED with zero loss; native AVIR VALID, new control pack VERIFIED, exact 12000ms letter visibility matches timeline; media NOT_RUN.'},
    {'id': 'handoff', 'status': 'PASS',
     'evidence': [euri('handoff.json'), euri('promotion-diff.json'),
                  euri('boundary-visibility.json'), euri('coordinate-consistency.json')],
     'finding': 'Accepted StoryboardIR maps into current ShotControlPack with exact boundary visibility and stable camera point.'},
]
role = {
    'schema': 'role-result/5.1', 'task_id': TASK,
    'context_fingerprint': TASK5['context_fingerprint'],
    'complete': True, 'reused': False,
    'checks': checks, 'conflicts': [], 'unresolved': [], 'handoff': [],
    'config': str(OUT / 'control-config.json'),
    'module_receipt': {
        'name': TASK5['module']['name'],
        'version': TASK5['module']['version'],
        'skill_sha256': TASK5['module']['skill_sha256'],
        'reads': [{'path': row['path'], 'sha256': row['sha256']}
                  for row in TASK5['module']['required_reads']]},
    'validator': {
        'status': fresh['status'],
        'projection_status': 'PLANNED_PROJECTION',
        'projection_unresolved_frames': 0,
        'camera_trajectory_media_review': 'NOT_RUN',
        'visual_review': 'NOT_RUN', 'media_review': fresh['media_review']}}
validate_v5('role-result', role)
put('role-result.json', role)
candidate = {
    'schema': 'candidate-result/6.0', 'task_id': TASK, 'batch': ENV['batch'],
    'agent_id': AGENT, 'input_digest': ENV['input_digest'],
    'result_uri': PREFIX + 'role-result.json',
    'result_sha256': sha(OUT / 'role-result.json'),
    'artifacts': [{
        'slot': ENV['expected_artifacts'][0]['slot'],
        'kind': 'ShotControlPack',
        'uri': PREFIX + 'control-pack/package-manifest.json',
        'sha256': manifest_sha}],
    'module_receipts': [ENV['module']],
    'checks': [{key: row[key] for key in ('id', 'status', 'evidence')} for row in checks],
    'handoffs': [dict(handoff, evidence=[euri('handoff.json'), euri('promotion-diff.json'),
                                         euri('boundary-visibility.json'),
                                         euri('coordinate-consistency.json')])],
    'unresolved': []}
validate_v6_protocol('candidate-result', candidate)
put('candidate-result.json', candidate)
print(json.dumps({
    'candidate_uri': PREFIX + 'candidate-result.json',
    'candidate_sha256': sha(OUT / 'candidate-result.json'),
    'role_sha256': sha(OUT / 'role-result.json'),
    'manifest_sha256': manifest_sha,
    'avir_sha256': sha(OUT / 'native-av-ir.json'),
    'native_status': native['status'],
    'control_status': fresh['status'],
    'camera_status_counts': counts,
    'letter_end_visible_parts': end_state['visible_parts'],
    'keyframe_requests': len(requests),
    'media_review': fresh['media_review']}, ensure_ascii=False))
