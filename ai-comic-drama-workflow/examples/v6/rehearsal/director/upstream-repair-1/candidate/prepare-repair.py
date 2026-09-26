"""Repair Director camera coordinates against the frozen Compile review."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path


ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_19a3cd14f25bf90e50215d4d/1'
OLD = ROOT / 'runtime/v6/candidates/TASK_ae94f4322a77ebd18dbb635d/1'
MODULE = ROOT / 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
ACTION = Path('/private/tmp/ai-video-v6-real-efKlQy/director-repair-run.json')
TASK = ROOT / 'runtime/tasks/TASK_19a3cd14f25bf90e50215d4d.json'
AGENT = '/root/host_bridge/v6_859d227c7d730ab3b9722469'


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
assert action['action_id'] == 'dispatch-b2675e0a86b84995c72fed2c'
assert action['task_id'] == 'TASK_19a3cd14f25bf90e50215d4d'
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
ir['revision'] = 5
assert file_hash(ir['canon_ref']) == file_hash(canon_path)
for row in ir['sources']:
    if row['id'] == 'SRC_69a71adcfaca':
        row['uri'] = str(ROOT / 'sources/SRC_69a71adcfaca/source.txt')
    elif row['id'] == 'CANON_INPUT':
        assert file_hash(row['uri']) == file_hash(canon_path)
    elif row['id'] == 'SCRIPT_INPUT':
        assert file_hash(row['uri']) == file_hash(script_path)
    elif row['id'] == 'DIRECTOR_DESIGN':
        row['uri'] = 'design://TASK_19a3cd14f25bf90e50215d4d/director'
        row['locator'] = '本次候选 /scenes/0、/shots/0 与 /timeline；修正锁定 Compile 独立复核发现的坐标冲突'
    else:
        raise ValueError('Unexpected source ID: ' + row['id'])

# DirectorIR 1.2 requires the static [x, depth, height] axis declaration.
# The detail timeline requires [x, height, depth]. They are two ordered
# representations of the same physical geometry. Convert explicitly at the
# boundary, and write the camera-operation text in the timeline axis order
# consumed by downstream AVIR and prompt compilation.
assert ir['scenes'][0]['coordinate_system'] == 'right-handed:X-right,Y-depth,Z-up;meters'
shot = ir['shots'][0]
assert shot['camera']['start_m'] == shot['camera']['end_m'] == [0, -2.8, 1.2]
assert shot['camera']['look_at_m'] == [0, 0, 1.0]
assert [shot['camera']['start_m'][0], shot['camera']['start_m'][2], shot['camera']['start_m'][1]] == [0, 1.2, -2.8]
assert [shot['camera']['look_at_m'][0], shot['camera']['look_at_m'][2], shot['camera']['look_at_m'][1]] == [0, 1.0, 0]
samples = {row['at_ms']: row['entities'] for row in ir['timeline']['state_samples']}
assert sorted(samples) == [0, 2500, 4000, 7500, 10500, 12000]
for key, at_ms in (('start_state', 0), ('end_state', 12000)):
    for row in shot[key]:
        x, y, z = samples[at_ms][row['entity_id']]['position']
        assert row['position_m'] == [x, z, y]
for camera in ir['timeline']['camera_operations']:
    if camera['id'] != 'CAM_LOCKED':
        continue
    for key in ('start_position', 'end_position'):
        assert '[0,-2.8,1.2]' in camera[key]
        camera[key] = camera[key].replace('[0,-2.8,1.2]', '[0,1.2,-2.8]') + '（时间轴坐标：x右、y上、z深）'
    camera['axis'] = '甲至乙为动作轴；固定机位在负 Z 深度同侧。'
assert ir['timeline']['coordinate_system'].startswith('x-right,y-up,z-depth')

# The independent review and exact failed-check evidence are part of the
# frozen upstream-repair input. Both must be examined before authoring.
repair = read(ROOT / next(item['uri'] for item in envelope['inputs'] if item['slot'] == 'upstream_repair'))
review_path = ROOT / repair['review']['uri']
assert file_hash(review_path) == repair['review']['sha256']
review = read(review_path)
assert review['failure_owner'] == 'director'
assert review['candidate_digest'] == repair['candidate_digest']
failed = [row for row in review['checks'] if row['status'] == 'FAIL']
assert [row['id'] for row in failed] == ['compile_manifest']
failed_evidence_path = ROOT / repair['failed_checks'][0]['evidence'][0]
failed_evidence = read(failed_evidence_path)
assert failed_evidence['semantic_consistency']['error_code'] == 'CAMERA_COORDINATE_CONFLICT'
assert failed_evidence['semantic_consistency']['status'] == 'FAIL'
assert failed_evidence['semantic_consistency']['director_camera_start_m'] == [0, -2.8, 1.2]
assert failed_evidence['semantic_consistency']['storyboard_camera_start_m'] == [0, 1.2, -2.8]
write(OUT / 'evidence/upstream-repair.json', {
    'status': 'CORRECTED_IN_CANDIDATE',
    'route_id': repair['route_id'],
    'review_uri': repair['review']['uri'],
    'review_sha256': repair['review']['sha256'],
    'failed_evidence_uri': repair['failed_checks'][0]['evidence'][0],
    'failed_evidence_sha256': file_hash(failed_evidence_path),
    'error_code': 'CAMERA_COORDINATE_CONFLICT',
    'changed_fields': [
        '/timeline/camera_operations/0/start_position',
        '/timeline/camera_operations/0/end_position',
        '/timeline/camera_operations/0/axis',
    ],
    'static_schema_axes': 'X-right,Y-depth,Z-up',
    'timeline_axes': 'x-right,y-up,z-depth',
    'conversion_static_to_timeline': '[x,y,z] -> [x,z,y]',
    'static_camera_at_all_times_m': [0, -2.8, 1.2],
    'timeline_camera_at_all_times_m': [0, 1.2, -2.8],
    'static_look_at_m': [0, 0, 1.0],
    'timeline_look_at_m': [0, 1.0, 0],
    'all_six_state_samples_checked': True,
    'downstream_status': 'Storyboard, control and Compile remain subject to new versions and independent review.',
})
ir['timeline']['semantic_review'] = {
    'status': 'PASS',
    'reviewer': AGENT + ' / creator source-bound semantic check; independent V6 review pending',
    'input_sha256': detail.content_hash(ir),
    'findings': [
        '当前 V6 冻结 Canon 与 V5 Canon 字节一致；当前 V6 冻结 ScriptIR 与 V5 编剧快照语义摘要一致，编剧复核摘要仍有效。',
        '逐项核对雨夜、甲交一封未拆信、乙在收存前确认同一封信封口完整、乙随后收入背包；不补地点、人物关系、动机、信件内容、对白或后续。',
        '复用上次导演已验动作设计；锁定静态 Schema 的 [x,深,高] 与时间轴 [x,高,深] 做显式换算，物理固定机位一致。',
        '进入下游正文的时间轴文字机位已修为 [0,1.2,-2.8] 米；静态数值 [0,-2.8,1.2] 米按两套轴序换算为同一位置。',
        '镜头起止态的位置与 0/12000 ms 样本逐项换算一致；六个时间样本及动作轨按时间轴序核对。',
        '逐样本核对起止姿态、双向接触、道具控制权与动作顺序；信件在收存完成后由背包内部承托，画面不可见。',
        'G3/G4 实际媒体检查仍 NOT_RUN；此记录仅为导演候选的来源语义复核。',
    ],
}
assert ir['timeline']['semantic_review']['input_sha256'] == detail.content_hash(ir)
write(OUT / 'director-ir.json', ir)

mapping = deepcopy(read(OLD / 'screenplay-map.json'))
mapping['screenplay_sha256'] = handoff['content_sha256']
mapping['director_sha256'] = screenplay.content_hash(ir)
mapping['reviewer'] = AGENT + ' / creator screenplay mapping check; independent V6 review pending'
mapping['findings'] = [
    '六条当前 V5 编剧要求及源指纹与锁定编剧交接逐条相同。',
    '雨夜、唯一未拆信、交接→验封→收存、结尾边界落入原生 hard clause 与目标字段断言。',
    '按上游独立失败证据显式核对原生静态轴序与时间轴换算，并修正进入正文的时间轴机位文字；重新绑定当前 V5 编剧快照和本次 DirectorIR 语义摘要。',
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
    'reuse_scope': '保留上一候选的剧情动作与锁定静态坐标；修正时间轴机位文字，并重核静态与时间轴的坐标换算、当前来源和六条编剧映射。',
    'upstream_repair_uri': next(item['uri'] for item in envelope['inputs'] if item['slot'] == 'upstream_repair'),
})
print(json.dumps({'director_ir_sha256': file_hash(OUT / 'director-ir.json'),
                  'director_content_hash': detail.content_hash(ir),
                  'screenplay_map_sha256': file_hash(OUT / 'screenplay-map.json'),
                  'screenplay_handoff_sha256': file_hash(OUT / 'screenplay-handoff.json')}, ensure_ascii=False))
