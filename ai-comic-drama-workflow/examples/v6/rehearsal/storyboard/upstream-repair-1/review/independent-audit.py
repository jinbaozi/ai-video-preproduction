from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_comic_drama_workflow.v5_handoff import validate_handoff
from ai_comic_drama_workflow.v51_detail_runtime import content_hash, semantic_status
from ai_comic_drama_workflow.v6_protocol import (
    candidate_digest, envelope_digest, envelope_input_digest,
    expected_review_dispatch_id, validate_v6_protocol,
)

ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
REVIEW = ROOT / 'runtime/v6/reviews/TASK_4f81cc62bc1b268a8f8be7b0/1'
CAND = ROOT / 'runtime/v6/candidates/TASK_4f81cc62bc1b268a8f8be7b0/1'
action = json.loads(Path('/private/tmp/ai-video-v6-real-efKlQy/storyrepair-candidate-submit-output.json').read_text())['actions'][0]
message = action['arguments']['message']
envelope = json.JSONDecoder().raw_decode(message.split('Frozen task envelope:\n', 1)[1])[0]
submitted = json.loads((CAND / 'candidate-result.json').read_text())
role_result = json.loads((CAND / 'role-result.json').read_text())
ir = json.loads((CAND / 'storyboard-ir.json').read_text())
director = json.loads((ROOT / envelope['inputs'][1]['uri']).read_text())
art = json.loads((ROOT / envelope['inputs'][2]['uri']).read_text())
canon = json.loads((ROOT / envelope['inputs'][0]['uri']).read_text())
task = json.loads((ROOT / envelope['inputs'][3]['uri']).read_text())
results = []

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check(name, passed, detail):
    results.append({'name': name, 'status': 'PASS' if passed else 'FAIL', 'detail': detail})

for protocol, document in [('task-envelope', envelope), ('candidate-result', submitted)]:
    try:
        validate_v6_protocol(protocol, document)
        check('protocol:' + protocol, True, 'strict schema accepted')
    except Exception as exc:
        check('protocol:' + protocol, False, str(exc))
check('frozen_dispatch', envelope_digest(envelope) == action['task_digest'] and
      envelope_input_digest(envelope) == submitted['input_digest'] and
      expected_review_dispatch_id(envelope) == action['dispatch_id'],
      {'task_digest': action['task_digest'], 'input_digest': submitted['input_digest'],
       'review_dispatch_id': action['dispatch_id']})
for row in envelope['inputs'] + envelope['resources']:
    path = ROOT / row['uri']
    check('frozen_sha256:' + row['uri'], path.is_file() and sha(path) == row['sha256'],
          {'declared': row['sha256'], 'observed': sha(path) if path.is_file() else None})
check('candidate_artifact_sha256', sha(CAND / 'storyboard-ir.json') == submitted['artifacts'][0]['sha256'] == role_result['artifact_sha256'],
      {'sha256': sha(CAND / 'storyboard-ir.json')})
check('candidate_role_result_sha256', sha(CAND / 'role-result.json') == submitted['result_sha256'],
      {'sha256': sha(CAND / 'role-result.json')})
check('candidate_digest', candidate_digest(submitted) == candidate_digest(json.JSONDecoder().raw_decode(message.split('\nCandidate:\n', 1)[1])[0]),
      {'digest': candidate_digest(submitted)})
receipt = role_result['module_receipt']
expected_reads = {(ROOT / row['uri']).resolve(): row['sha256'] for row in envelope['resources']}
received_reads = {Path(row['path']).resolve(): row['sha256'] for row in receipt['reads']}
check('module_receipt', receipt['name'] == envelope['module']['name'] and
      receipt['version'] == envelope['module']['version'] and
      receipt['skill_sha256'] == envelope['resources'][0]['sha256'] and
      received_reads == expected_reads and submitted['module_receipts'] == [envelope['module']],
      {'module': receipt['name'], 'version': receipt['version'], 'read_count': len(received_reads)})
inspect = json.loads((REVIEW / 'native-inspect.review.json').read_text())
compile_result = json.loads((REVIEW / 'native-compile.review.json').read_text())
verify = json.loads((REVIEW / 'native-verify.review.json').read_text())
check('native_inspect_compile_verify', inspect['status'] == compile_result['status'] == 'VALID' and
      verify['status'] == 'VERIFIED' and inspect['structure'] == 'PASS' and
      inspect['media'] == inspect['visual'] == verify['media'] == 'NOT_RUN',
      {'inspect': inspect['status'], 'compile': compile_result['status'], 'verify': verify['status'],
       'media': verify['media']})
native = CAND / 'native-package'
independent = REVIEW / 'independent-native-package'
source_files = {p.name for p in native.iterdir() if p.is_file()}
independent_files = {p.name for p in independent.iterdir() if p.is_file()}
changed = [name for name in sorted(source_files | independent_files) if
           not (native / name).is_file() or not (independent / name).is_file() or
           (native / name).read_bytes() != (independent / name).read_bytes()]
check('native_package_reproducible', not changed and len(source_files) == 9,
      {'files': len(source_files), 'different': changed})
check('semantic_review_byte_binding', semantic_status(ir) and
      ir['timeline']['semantic_review']['input_sha256'] == content_hash(ir),
      {'declared': ir['timeline']['semantic_review']['input_sha256'], 'observed': content_hash(ir)})
required = task['handoff']['required_handoffs']
mapped = role_result['handoff']
try:
    validate_handoff('storyboard', ir, required, mapped)
    handoff_valid = True
    reason = 'native validate_handoff accepted'
except Exception as exc:
    handoff_valid = False
    reason = str(exc)
required_ids = {r['id'] for r in required}
mapped_ids = {m['requirement_id'] for m in mapped}
detail_count = sum(bool(r.get('preservation_only')) for r in required)
check('v5_handoffs', handoff_valid and required_ids == mapped_ids and
      len(required) == len(mapped) == 1437 and detail_count == 1424,
      {'reason': reason, 'required': len(required), 'mapped': len(mapped),
       'preservation_only': detail_count, 'hard_semantic': len(required) - detail_count})
v6 = json.loads((CAND / 'evidence/v6-handoffs.json').read_text())
expected_v6 = {(r['requirement_id'], r['source_slot'], r['source_version'], r['target_slot']) for r in envelope['handoffs']}
actual_v6 = {(r['requirement_id'], r['source_slot'], r['source_version'], r['target_slot']) for r in submitted['handoffs']}
source_by_slot = {r['slot']: r for r in envelope['inputs']}
valid_v6 = all(r['source_sha256'] == source_by_slot[r['source_slot']]['sha256'] and
               r['source_uri'] == source_by_slot[r['source_slot']]['uri'] and
               r['target_sha256'] == submitted['artifacts'][0]['sha256'] and
               r['target_uri'] == submitted['artifacts'][0]['uri'] and
               r['target_binding'] in ('/upstreams/0', '/upstreams/1', '/upstreams/2')
               for r in v6['handoffs'])
check('v6_handoffs', len(expected_v6) == len(actual_v6) == len(v6['handoffs']) == 3 and
      expected_v6 == actual_v6 and valid_v6 and v6['input_digest'] == envelope['input_digest'],
      {'count': len(v6['handoffs']), 'requirements': sorted(r['requirement_id'] for r in v6['handoffs'])})
source_timeline = {k: v for k, v in director['timeline'].items() if k not in ('semantic_review', 'visibility')}
target_timeline = {k: ir['timeline'].get(k) for k in source_timeline}
check('director_timeline_preserved', source_timeline == target_timeline and
      len(ir['timeline']['state_samples']) == 6 and len(ir['timeline']['visibility']) == 6,
      {'state_samples': [r['at_ms'] for r in ir['timeline']['state_samples']],
       'visibility_additions': len(ir['timeline']['visibility'])})
static_camera = director['shots'][0]['camera']['start_m']
timeline_camera = [static_camera[0], static_camera[2], static_camera[1]]
operation = ir['timeline']['camera_operations'][0]
shot_camera = ir['shots'][0]['camera']
check('camera_axis_conversion',
      director['scenes'][0]['coordinate_system'] == 'right-handed:X-right,Y-depth,Z-up;meters' and
      static_camera == director['shots'][0]['camera']['end_m'] == [0, -2.8, 1.2] and
      timeline_camera == shot_camera['start_m'] == shot_camera['end_m'] == [0, 1.2, -2.8] and
      '[0,1.2,-2.8]' in operation['start_position'] and
      '[0,1.2,-2.8]' in operation['end_position'] and
      '[0,-2.8,1.2]' in ir['scenes'][0]['coordinates']['origin'] and
      '[0,1.2,-2.8]' in ir['scenes'][0]['coordinates']['origin'],
      {'director_static_XYZ': static_camera, 'storyboard_timeline_xyz': timeline_camera,
       'text_start': operation['start_position'], 'text_end': operation['end_position']})
end_by_id = {r['entity_id']: r for r in director['shots'][0]['end_state']}
end_positions = all(ir['shots'][0]['state_end'][entity_id]['position_m'] ==
                    [row['position_m'][0], row['position_m'][2], row['position_m'][1]] and
                    ir['shots'][0]['state_end'][entity_id]['pose'] == row['pose']
                    for entity_id, row in end_by_id.items())
letter = ir['shots'][0]['state_end']['PROP_LETTER']
bag = ir['shots'][0]['state_end']['PROP_BACKPACK']
check('end_pose_and_props', end_positions and '未拆' in letter['pose'] and
      letter['support'] == 'PROP_BACKPACK.interior' and
      'PROP_LETTER.body' in bag['contacts'] and
      ir['shots'][0]['state_end']['CHAR_JIA']['holder'] is None,
      {'end_positions_transformed': end_positions, 'letter_pose': letter['pose'],
       'letter_support': letter['support'], 'bag_contacts': bag['contacts']})
panels = ir['shots'][0]['panels']
check('seven_panels', len(panels) == 7 and
      [(p['id'], p['frame']) for p in panels] ==
      [('P_OPEN', 0), ('P_GRIP', 60), ('P_RELEASE', 84), ('P_SEAL', 144),
       ('P_BAG_OPEN', 204), ('P_STOWED', 252), ('P_END', 287)] and
      ir['delivery']['total_frames'] == director['format']['total_frames'] == 288,
      {'panels': [(p['id'], p['frame']) for p in panels], 'total_frames': ir['delivery']['total_frames']})
check('story_and_media_boundary', canon['content'].startswith('雨夜') and
      len(ir['beats']) == 3 and ir['audio']['utterances'] == [] and
      inspect['execution_ready'] is False and
      inspect['submitted'] is False and
      all(json.loads((CAND / 'evidence/native-validator.json').read_text())['bound_media_status'][key] == value
          for key, value in {'images_generated': False, 'video_generated': False,
                             'visual_qa': 'NOT_RUN', 'media_qa': 'NOT_RUN'}.items()),
      {'beats': [r['id'] for r in ir['beats']], 'utterances': len(ir['audio']['utterances']),
       'execution_ready': inspect['execution_ready'], 'submitted': inspect['submitted']})
report = {'schema': 'independent-storyboard-review/1.0', 'task_id': envelope['task_id'],
          'batch': envelope['batch'], 'candidate_digest': candidate_digest(submitted),
          'checks': results, 'overall': 'PASS' if all(r['status'] == 'PASS' for r in results) else 'FAIL',
          'scope_limit': 'Static native IR, hash, ownership, timeline and package review only; no generated media or real camera execution examined.'}
(REVIEW / 'independent-audit.review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'overall': report['overall'], 'checks': len(results),
                  'failed': [r for r in results if r['status'] == 'FAIL']}, ensure_ascii=False, indent=2))
