#!/usr/bin/env python3
"""Create this batch's DirectorIR candidate and evidence, without formal promotion."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
REL = 'runtime/v6/candidates/TASK_bf0865334b4a88be570a164a/2'
OUT = ROOT / REL
MODREL = 'runtime/modules/1a3d2e6d95e35195499b2c81ea8f04f979d537bc0fb0522d698c4dc96870d9c1/director-grammar'
MOD = ROOT / MODREL
TASK = json.loads((ROOT / 'runtime/tasks/TASK_bf0865334b4a88be570a164a.json').read_text())
OLD = ROOT / 'runtime/v6/candidates/TASK_bf0865334b4a88be570a164a/1'
SCRIPT_HANDOFF = ROOT / 'runtime/v6/candidates/TASK_206f1e43fe2d38c84f3fcb2c/1/compiled/director-handoff.json'

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()

def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
    return path

def filehash(path):
    return sha256(Path(path).read_bytes()).hexdigest()

def pointer(value, path):
    for key in path.strip('/').split('/') if path else []:
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value

assert TASK['task_id'] == 'TASK_bf0865334b4a88be570a164a'
assert TASK['module']['sha256'] == '1a3d2e6d95e35195499b2c81ea8f04f979d537bc0fb0522d698c4dc96870d9c1'
reads = []
for item in TASK['module']['required_reads']:
    path = Path(item['path'])
    actual = filehash(path)
    assert actual == item['sha256'], (path, actual, item['sha256'])
    reads.append({'path': str(path), 'sha256': actual})
assert TASK['module']['skill_sha256'] == reads[0]['sha256']
frozen_inputs = [
    ('canon:project:project:Canon', 'runtime/v6/candidates/TASK_44ed8445ba9b638fcd7e9fe8/2/canon.json', '0cc4aebffda6a714d5c58695c11f7d70b96359d930125b04edb8fe14abfc4ef9'),
    ('screenplay:project:project:ScriptIR', 'runtime/v6/candidates/TASK_206f1e43fe2d38c84f3fcb2c/1/script-ir.json', '8e51d23ea14ac97ebdbba754d2be77e8694dbc9bb1a3a89d3b9cb1ca5d3d6c93'),
    ('frozen_task', 'runtime/tasks/TASK_bf0865334b4a88be570a164a.json', 'a435e4354848649326798f614c5af4748f081481623597804228cde9892970ec'),
]
verified_inputs = []
for slot, uri, expected in frozen_inputs:
    actual = filehash(ROOT / uri)
    assert actual == expected, (uri, actual, expected)
    verified_inputs.append({'slot': slot, 'uri': uri, 'sha256': actual})
assert filehash(SCRIPT_HANDOFF) == '4db00070e002faaf1ba1adef6db77f612b4ed17cb41f53dfe4b1ae096f6a7685'
canon = json.loads((ROOT / frozen_inputs[0][1]).read_text())
script = json.loads((ROOT / frozen_inputs[1][1]).read_text())
assert script['review']['status'] == 'PASS'
assert script['narrative']['reveal_order'] == [e['id'] for e in canon['event_order']]
assert [b['id'] for b in script['scenes'][0]['blocks']] == ['B_HANDOFF', 'B_SEAL_CHECK', 'B_STOW']
assert not any(b['kind'] == 'dialogue' for b in script['scenes'][0]['blocks'])
write('evidence/module-receipt.json', {'status': 'PASS', 'module': {'name': 'director-grammar', 'version': TASK['module']['version'], 'sha256': TASK['module']['sha256'], 'skill_sha256': reads[0]['sha256']}, 'reads': reads, 'inputs': verified_inputs, 'meaning': '冻结输入和模块资源的字节完整性；不代表媒体验收。'})

# The earlier director design is a read-only reference. This batch checks it against
# the newly frozen ScriptIR and writes its own native candidate and review stamp.
ir = json.loads((OLD / 'director-ir.json').read_text())
old_canon = 'runtime/v6/candidates/TASK_5ae2734678bb041b76474d34/1/canon.json'
old_script = 'runtime/v6/candidates/TASK_20dbe9991f545d5fe05e55e7/2/script-ir.json'
text = json.dumps(ir, ensure_ascii=False)
text = text.replace(old_canon, frozen_inputs[0][1]).replace(old_script, frozen_inputs[1][1])
text = text.replace('SCRIPT_V16', 'SCRIPT_V15')
text = text.replace('design://LETTER_FULL_DEMO/director-current-b1', 'design://LETTER_FULL_DEMO/director-current-b2')
ir = json.loads(text)
ir['revision'] = 2
ir['canon_ref'] = str(ROOT / frozen_inputs[0][1])
# Formal batch-1 reviewer found this terminal camera description contradicted
# the explicit 8500-9000 ms settled composition and state samples.
old_end = ir['timeline']['camera_operations'][2]['end_framing']
old_start = ir['timeline']['camera_operations'][2]['start_framing']
assert old_end == old_start == '乙手、信和背包口同框的中近景'
# Fixed camera keeps one image boundary while the subject's visibility changes.
fixed_frame = '乙手与背包口同框的中近景；同一封信入包前可见，入包后完全遮挡不外露'
ir['timeline']['camera_operations'][2]['start_framing'] = fixed_frame
ir['timeline']['camera_operations'][2]['end_framing'] = fixed_frame
assert '信已完全在包内' in ir['shots'][2]['camera']['framing_end']
assert all('N_PROP_LETTER' not in [subject['node_id'] for subject in track['subjects']] for track in ir['timeline']['composition_tracks'] if track['start_ms'] >= 8500)
assert all(sample['entities']['PROP_LETTER']['contacts'] == ['PROP_BACKPACK.interior'] for sample in ir['timeline']['state_samples'] if sample['shot_id'] == 'S_STOW' and sample['at_ms'] >= 8500)

assert [x['id'] for x in ir['beats']] == [b['id'] for b in script['scenes'][0]['blocks']]
assert [x['semantic_id'] for x in ir['timeline']['actions']] == script['narrative']['reveal_order']
assert all(not shot['phases'] for shot in ir['shots'])
assert all('SCRIPT_V15' in shot['source_refs'] for shot in ir['shots'])
assert [x['id'] for x in ir['sources']] == ['SRC_69a71adcfaca', 'CANON_V12', 'SCRIPT_V15', 'DESIGN_D1']
assert all(a['shot_ids'] == [ir['shots'][i]['id']] for i,a in enumerate(ir['timeline']['actions']))
assert ir['timeline']['actions'][2]['changes'][-1] == {'after': '收纳同一封信', 'at_ms': 8500, 'before': '待收纳信', 'entity_id': 'PROP_BACKPACK', 'field': 'condition'}
assert ir['timeline']['state_samples'][5]['entities']['PROP_LETTER']['contacts'] == ['PROP_BACKPACK.interior']
assert ir['timeline']['state_samples'][6]['entities']['PROP_LETTER']['contacts'] == ['PROP_BACKPACK.interior']
assert 'PROP_LETTER' not in ir['shots'][2]['composition']['attention_order']
assert all(s['entity_id'] != 'PROP_LETTER' for s in ir['shots'][2]['composition']['subjects'])
assert [x['end_ms'] for x in ir['timeline']['composition_tracks']] == [3000,6000,8500,9000]
assert all('N_PROP_LETTER' not in x['subjects'][0]['node_id'] for x in ir['timeline']['composition_tracks'][3:])

sys.path.insert(0, str(MOD / 'scripts'))
from detail_runtime import content_hash as detail_hash
from screenplay_protocol import content_hash as screenplay_hash, load_handoff, validate_mapping
handoff, checked_script = load_handoff(SCRIPT_HANDOFF)
assert handoff['ready'] and checked_script['project_id'] == ir['project_id']
assert handoff['content_sha256'] == script['review']['content_sha256']
assert {r['id']: r['source_fingerprint'] for r in handoff['requirements']} == {r['id']: r['source_fingerprint'] for r in TASK['handoff']['required_handoffs']}
findings = [
    '本批逐条对照冻结 Canon 与已通过当前语义复核的 ScriptIR：雨夜、同一封未拆信及交接→验封→入包顺序均有原生视听字段承载。',
    'DirectorIR 1.2 的三项动作位于 timeline.actions，shots[].phases 保持空；入包动作在8500毫秒更新信件接触、支撑、控制权及背包状态，终帧信完全在包内且不再外露。',
    '三镜九秒、机位和左右站位属于导演设计；具体地点、室内外、角色外观及背包样式仍未指定。静态设计未作为实际媒体审片。',
    '按上一批独立审阅返修：9000毫秒镜头终帧仅见乙手与背包口，同一封信已完全在包内且不外露；与8500至9000毫秒构图和显式物理状态一致。',
]
ir['timeline']['semantic_review'] = {'status': 'PASS', 'reviewer': 'current-agent / TASK_bf0865334b4a88be570a164a / batch 2', 'input_sha256': detail_hash(ir), 'findings': findings}
ir_path = write('director-ir.json', ir)
assert ir['timeline']['semantic_review']['input_sha256'] == detail_hash(ir)

old_map = json.loads((OLD / 'screenplay-map.json').read_text())
required = {r['id']: r for r in TASK['handoff']['required_handoffs']}
clauses = {c['id']: c for c in ir['contract']['clauses']}
mappings = deepcopy(old_map['mappings'])
for row in mappings:
    row['source_fingerprint'] = required[row['requirement_id']]['source_fingerprint']
    clause = clauses[row['target_clause']]
    assert clause['priority'] == 'hard'
    for check in row['target_checks']:
        actual = pointer(ir, check['path'])
        assert actual == check['value'] if check['op'] == 'equals' else check['value'] in actual
map_data = {'schema': 'screenplay-director-map/1.0', 'screenplay_sha256': handoff['content_sha256'], 'director_sha256': screenplay_hash(ir), 'reviewer': 'current-agent / TASK_bf0865334b4a88be570a164a / batch 2', 'findings': findings, 'mappings': mappings}
assert not validate_mapping(ir, handoff['requirements'], map_data, handoff['content_sha256'])
map_path = write('screenplay-map.json', map_data)

# Use the locked native validator. Its exact status becomes RoleResult.validator.status.
py_path = ':'.join([
    '/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/src',
])
cmd = [sys.executable, str(MOD / 'scripts/dg.py'), 'validate', str(ir_path), '--screenplay-handoff', str(SCRIPT_HANDOFF), '--screenplay-map', str(map_path)]
proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, 'PYTHONPATH': py_path}, text=True, capture_output=True)
write('evidence/native-validator.json', {'command_argv': cmd, 'exit_code': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr, 'module': MODREL + '/scripts/dg.py'})
assert proc.returncode == 0, proc.stdout + proc.stderr
report = json.loads(proc.stdout)
assert report['status'] == 'STATIC_VALID' and report['errors'] == []
assert report['screenplay_binding']['status'] == 'REVIEW_ATTESTED'

from spatial_runtime import panel_state
panels = []
for at in (6000,8500,9000):
    p = panel_state(ir, 'S_STOW', at)
    letter = p['state']['PROP_LETTER']
    panels.append({'at_ms': at, 'status': p['status'], 'composition_id': p['composition']['id'], 'subject_nodes': [x['node_id'] for x in p['composition']['subjects']], 'letter_contacts': letter['contacts'], 'letter_supports': letter['supports'], 'letter_visible_parts': letter['visible_parts'], 'physical_interpolation': p['physical_interpolation']})
assert panels[0]['status'] == 'EXPLICIT' and 'N_PROP_LETTER' in panels[0]['subject_nodes']
assert all(p['status'] == 'EXPLICIT' and 'N_PROP_LETTER' not in p['subject_nodes'] and p['letter_contacts'] == p['letter_supports'] == ['PROP_BACKPACK.interior'] and not p['letter_visible_parts'] and not p['physical_interpolation'] for p in panels[1:])
write('evidence/stow-continuity.json', {'status': 'PASS', 'director_sha256': filehash(ir_path), 'module_source': MODREL + '/scripts/spatial_runtime.py panel_state', 'panel_samples': panels, 'semantic_finding': '8500至9000毫秒，同一封信已经完全入包；镜头末段只保留乙手与包口，不再把信绘为外露主体。', 'media': 'NOT_RUN'})

canon_mappings = [
    {'source_pointer': '/source_requirements/0', 'target_pointers': ['/contract/clauses/0', '/scenes/0/space', '/timeline/audio_events/0/text']},
    {'source_pointer': '/source_requirements/1', 'target_pointers': ['/contract/clauses/1', '/entities/2', '/timeline/actions/0', '/timeline/actions/1', '/timeline/actions/2']},
    {'source_pointer': '/source_requirements/2', 'target_pointers': ['/contract/clauses/2', '/beats', '/timeline/actions']},
]
assert [pointer(canon, x['source_pointer'])['id'] for x in canon_mappings] == [r['id'] for r in canon['source_requirements']]
assert all(pointer(ir, path) is not None for x in canon_mappings for path in x['target_pointers'])
canon_handoff = {'requirement_id': 'UP_45d4c22d9b47d4c769367b04', 'channel': 'artifact', 'source_slot': frozen_inputs[0][0], 'source_version': 12, 'source_uri': frozen_inputs[0][1], 'source_sha256': frozen_inputs[0][2], 'target_slot': 'director:project:project:DirectorIR', 'target_pointer': '', 'target_uri': REL + '/director-ir.json', 'target_sha256': filehash(ir_path), 'mapping': canon_mappings, 'finding': '三项 Canon 硬要求进入原生 DirectorIR 的合同、动作和关键状态。'}
write('evidence/handoff-canon.json', canon_handoff)
script_handoff = {'requirement_id': 'UP_beaf9e05cc9e0aa9e036f59b', 'channel': 'artifact', 'source_slot': frozen_inputs[1][0], 'source_version': 15, 'source_uri': frozen_inputs[1][1], 'source_sha256': frozen_inputs[1][2], 'target_slot': 'director:project:project:DirectorIR', 'target_pointer': '', 'target_uri': REL + '/director-ir.json', 'target_sha256': filehash(ir_path), 'screenplay_map_uri': REL + '/screenplay-map.json', 'screenplay_map_sha256': filehash(map_path), 'mapping': mappings, 'finding': '六条 ScriptIR 交接逐项对应原生 hard clause 与实际视听字段。'}
write('evidence/handoff-screenplay.json', script_handoff)
write('evidence/handoff-check.json', {'status': 'PASS', 'canon_source_requirements': len(canon_mappings), 'screenplay_required_handoffs': len(required), 'screenplay_mapped_handoffs': len(mappings), 'native_hard_clauses': [x['target_clause'] for x in mappings], 'script_review_status': script['review']['status'], 'script_review_content_sha256': script['review']['content_sha256'], 'director_semantic_review_sha256': detail_hash(ir), 'native_screenplay_binding': report['screenplay_binding']['status'], 'art_event_pointer_compatibility': {'director_schema_version': ir['schema_version'], 'supported_pointer_examples': ['/timeline/actions/0', '/timeline/actions/1', '/timeline/actions/2'], 'shot_ids': [a['shot_ids'][0] for a in ir['timeline']['actions']], 'note': '原生动作位于 timeline.actions；美术事件需引用这一组有效指针而不是空 phases。'}, 'media': 'NOT_RUN'})

art_archive = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/assets/bundled-skills/production-design-grammar.skill')
art_archive_hash = filehash(art_archive)
assert art_archive_hash == '6e83e075da45785541fce62f9fcc6ebc8666f48466c382af5980f292613fb5f9'
import zipfile
with zipfile.ZipFile(art_archive) as z:
    art_compiler = z.read('production-design-grammar/scripts/art_compile.py').decode()
assert 'Event must cite a Director timeline action' in art_compiler
assert 'Event must match a Director action state change' in art_compiler
write('evidence/art-compatibility.json', {
    'status': 'PASS', 'art_module_archive': str(art_archive), 'art_module_archive_sha256': art_archive_hash,
    'art_module_version': '1.3.3', 'art_compiler_member': 'production-design-grammar/scripts/art_compile.py',
    'director_schema_version': ir['schema_version'],
    'contract': 'For DirectorIR 1.1/1.2, ArtIR events cite /timeline/actions/N; the cited action must include the shot ID and the asset entity/field/before/after state change.',
    'available_actions': [{'pointer': f'/timeline/actions/{i}', 'shot_ids': a['shot_ids'], 'changes': a['changes']} for i,a in enumerate(ir['timeline']['actions'])],
    'note': 'This checks the available director pointers and locked compiler contract. The ArtIR creator must still author matching events and run its own native validator.'
})

# Preserve the previous independent failure and show why both endpoints were
# changed: locked camera operations require identical start/end framing text.
prior_review_uri = 'runtime/v6/reviews/TASK_bf0865334b4a88be570a164a/1/native-validator.review.json'
prior_record_uri = 'runtime/v6/reviews/TASK_bf0865334b4a88be570a164a/1/review-record.json'
prior_review = json.loads((ROOT / prior_review_uri).read_text())
prior_record = json.loads((ROOT / prior_record_uri).read_text())
assert prior_review['status'] == 'FAIL' and prior_record['checks'][1]['status'] == 'FAIL'
assert prior_review['timeline_camera_end_framing'] == old_end
camera = ir['timeline']['camera_operations'][2]
settled = next(track for track in ir['timeline']['composition_tracks'] if track['id'] == 'COMP_S_STOW_SETTLED')
assert camera['operation'] == 'locked' and camera['start_framing'] == camera['end_framing']
assert camera['start_position'] == camera['end_position']
assert settled['start_ms'] == 8500 and settled['end_ms'] == 9000
assert 'N_PROP_LETTER' not in [subject['node_id'] for subject in settled['subjects']]
assert all(sample['entities']['PROP_LETTER']['contacts'] == ['PROP_BACKPACK.interior'] and sample['entities']['PROP_BACKPACK']['condition'] == '收纳同一封信' for sample in ir['timeline']['state_samples'] if sample['shot_id'] == 'S_STOW' and sample['at_ms'] >= 8500)
write('evidence/repair-b1.json', {
    'status': 'PASS',
    'previous_review_uri': prior_review_uri,
    'previous_review_sha256': filehash(ROOT / prior_review_uri),
    'previous_record_uri': prior_record_uri,
    'previous_record_sha256': filehash(ROOT / prior_record_uri),
    'failed_check': 'native_validator',
    'defect': prior_review['finding'],
    'old_camera_start_framing': old_start,
    'old_camera_end_framing': old_end,
    'new_camera_start_framing': camera['start_framing'],
    'new_camera_end_framing': camera['end_framing'],
    'repair_reason': '固定机位原生校验要求 start_framing 与 end_framing 相同；因此将两端写成相同的时间条件描述，仍明确终段信已完全入包不外露。',
    'locked_camera_positions_equal': camera['start_position'] == camera['end_position'],
    'settled_interval_ms': [settled['start_ms'], settled['end_ms']],
    'settled_subject_nodes': [subject['node_id'] for subject in settled['subjects']],
    'terminal_letter_contacts': [sample['entities']['PROP_LETTER']['contacts'] for sample in ir['timeline']['state_samples'] if sample['shot_id'] == 'S_STOW' and sample['at_ms'] >= 8500],
    'native_status': report['status'],
    'previous_defect_gone': True,
    'media': 'NOT_RUN',
})

checks = [
    {'id': 'module_receipt', 'status': 'PASS', 'finding': '冻结输入和四份锁定模块资源哈希吻合。', 'evidence': [REL + '/evidence/module-receipt.json']},
    {'id': 'native_validator', 'status': 'PASS', 'finding': '锁定 DirectorIR 1.2 原生校验返回 STATIC_VALID；编剧绑定 REVIEW_ATTESTED；终态显式样本信在包内不外露。', 'evidence': [REL + '/evidence/native-validator.json', REL + '/evidence/stow-continuity.json', REL + '/evidence/repair-b1.json']},
    {'id': 'handoff', 'status': 'PASS', 'finding': 'Canon 三项硬要求与 ScriptIR 六条交接已映射到原生字段；新锁 Art 事件指针可定位三项 timeline.actions。', 'evidence': [REL + '/evidence/handoff-canon.json', REL + '/evidence/handoff-screenplay.json', REL + '/evidence/handoff-check.json', REL + '/evidence/art-compatibility.json']},
]
review_stamp = {k: deepcopy(map_data[k]) for k in ('screenplay_sha256','director_sha256','reviewer','findings')}
native_handoff = [{**deepcopy(row), 'review': deepcopy(review_stamp)} for row in mappings]
assert len(native_handoff) == 6 and {x['requirement_id'] for x in native_handoff} == set(required)
role = {'schema': 'role-result/5.1', 'task_id': TASK['task_id'], 'context_fingerprint': TASK['context_fingerprint'], 'artifact': str(ir_path), 'artifact_sha256': filehash(ir_path), 'checks': checks, 'complete': True, 'conflicts': [], 'unresolved': [], 'handoff': native_handoff, 'module_receipt': {'name': 'director-grammar', 'version': TASK['module']['version'], 'skill_sha256': reads[0]['sha256'], 'reads': reads}, 'validator': {'status': report['status'], 'errors': report['errors'], 'semantic_review': 'REVIEW_ATTESTED', 'screenplay_binding': report['screenplay_binding']['status'], 'media': 'NOT_RUN'}}
role_path = write('role-result.json', role)

def short_handoff(row, evidence):
    return {k: row[k] for k in ('requirement_id','channel','source_slot','source_version','target_slot','target_pointer')} | {'evidence': evidence}
handoffs = [
    short_handoff(canon_handoff, [REL + '/evidence/handoff-canon.json', REL + '/evidence/handoff-check.json']),
    short_handoff(script_handoff, [REL + '/evidence/handoff-screenplay.json', REL + '/evidence/handoff-check.json']),
]
candidate = {'schema': 'candidate-result/6.0', 'task_id': TASK['task_id'], 'batch': 2, 'agent_id': '/root/host_bridge/full_rehearsal/v6_ae88af1ac4163d4e37222aa4', 'input_digest': '85b2bcd4414232835001b6218d902ef7db0f4872571ef5c617e2e41e417bb6ac', 'result_uri': REL + '/role-result.json', 'result_sha256': filehash(role_path), 'artifacts': [{'slot': 'director:project:project:DirectorIR', 'kind': 'DirectorIR', 'uri': REL + '/director-ir.json', 'sha256': filehash(ir_path)}], 'checks': [{k:c[k] for k in ('id','status','evidence')} for c in checks], 'handoffs': handoffs, 'module_receipts': [{'name': 'director-grammar', 'version': TASK['module']['version'], 'sha256': TASK['module']['sha256']}], 'unresolved': []}
write('candidate-result.json', candidate)
print(json.dumps({'status': 'SUBMITTED_CANDIDATE', 'candidate': REL + '/candidate-result.json', 'director_sha256': filehash(ir_path), 'native_status': report['status'], 'screenplay_binding': report['screenplay_binding']['status']}, ensure_ascii=False))
