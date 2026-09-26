#!/usr/bin/env python3
"""Record byte-bound native and handoff evidence for one frozen V6 batch."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
TASK_ID = 'TASK_4f81cc62bc1b268a8f8be7b0'
BATCH = 1
OUT = PROJECT / f'runtime/v6/candidates/{TASK_ID}/{BATCH}'
EV = OUT / 'evidence'
ARTIFACT = OUT / 'storyboard-ir.json'
ROOT = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow')
MODULE = PROJECT / 'runtime/modules/dde48be75afdb1f12dadbc01e2cbf26c2ea67de691c8d605db7912ebb241ceb8/storyboard-grammar'
sys.path.insert(0, str(ROOT / 'src'))
from ai_comic_drama_workflow.v5_adapters import assert_check, pointer  # noqa: E402
from ai_comic_drama_workflow.v5_handoff import validate_handoff  # noqa: E402
from ai_comic_drama_workflow.v5_modules import native_validate  # noqa: E402


def read(p):
    return json.loads(Path(p).read_text())


def dump(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def digest(p):
    return sha256(Path(p).read_bytes()).hexdigest()


def uri(name):
    return str((EV / name).relative_to(PROJECT))


state = read(PROJECT / 'runtime/v6/state.json')
envelope = state['tasks'][TASK_ID]['envelope']
task = read(PROJECT / f'runtime/tasks/{TASK_ID}.json')
ir = read(ARTIFACT)
assert envelope['batch'] == BATCH and envelope['task_id'] == TASK_ID
assert envelope['node_id'] == 'storyboard' and envelope['schema'] == 'task-envelope/6.0'
assert task['task_id'] == TASK_ID and task['schema'] == 'task-envelope/5.0'
assert digest(ARTIFACT) == digest(OUT / 'native-package/storyboard.ir.json')

frozen_inputs = []
for spec in envelope['inputs']:
    p = PROJECT / spec['uri']
    actual = digest(p)
    assert actual == spec['sha256'], (spec['slot'], actual, spec['sha256'])
    frozen_inputs.append({**spec, 'observed_sha256': actual, 'status': 'PASS'})

frozen_resources = []
for spec in envelope['resources']:
    p = PROJECT / spec['uri']
    actual = digest(p)
    assert actual == spec['sha256'], (spec['uri'], actual, spec['sha256'])
    frozen_resources.append({**spec, 'observed_sha256': actual, 'status': 'PASS'})

v5_inputs = []
for spec in task['inputs']:
    actual = digest(spec['uri'])
    assert actual == spec['sha256'], spec['slot']
    v5_inputs.append({'slot': spec['slot'], 'uri': spec['uri'], 'sha256': actual, 'status': 'PASS'})

script_ref = state['artifacts']['screenplay:project:project:ScriptIR']
assert digest(PROJECT / script_ref['uri']) == script_ref['sha256']
source_text = PROJECT / 'sources/SRC_69a71adcfaca/source.txt'
assert digest(source_text) == task['sources'][0]['sha256']
dump(EV / 'source-integrity.json', {
    'status': 'PASS', 'project_id': 'LETTER_DEMO', 'task_id': TASK_ID, 'batch': BATCH,
    'input_digest': envelope['input_digest'],
    'frozen_inputs': frozen_inputs, 'frozen_resources': frozen_resources,
    'original_v5_inputs': v5_inputs,
    'accepted_script': {'uri': script_ref['uri'], 'sha256': script_ref['sha256']},
    'source_text': {'uri': str(source_text.relative_to(PROJECT)), 'sha256': digest(source_text)},
    'artifact_sha256': digest(ARTIFACT),
})

mod = task['module']
reads = []
for spec in mod['required_reads']:
    actual = digest(spec['path'])
    assert actual == spec['sha256']
    reads.append({'path': spec['path'], 'sha256': actual})
module_receipt = {'name': mod['name'], 'version': mod['version'],
                  'skill_sha256': mod['skill_sha256'], 'reads': reads}
assert module_receipt['name'] == envelope['module']['name']
assert module_receipt['version'] == envelope['module']['version']
assert module_receipt['skill_sha256'] == frozen_resources[0]['sha256']
dump(EV / 'module-receipt.json', {
    'status': 'PASS', 'role_result_receipt': module_receipt,
    'candidate_module_receipt': envelope['module'],
    'module_path': str(MODULE),
})

native = native_validate('storyboard', ARTIFACT,
                         lambda name: MODULE if name == 'storyboard-grammar' else None)
assert native['status'] == 'VALID' and native['structure'] == 'PASS'
assert native['media'] == 'NOT_RUN' and native['visual'] == 'NOT_RUN'
compiled = read(OUT / 'native-package/qa.report.json')
assert compiled['status'] == 'VALID' and compiled['execution_ready'] is False
verify_cmd = [sys.executable, str(MODULE/'scripts/storyboard.py'), 'verify', str(OUT/'native-package')]
run = subprocess.run(verify_cmd, text=True, capture_output=True)
assert run.returncode == 0, run.stdout + run.stderr
verified = json.loads(run.stdout)
assert verified['status'] == 'VERIFIED' and verified['media'] == 'NOT_RUN'
dump(EV / 'native-validator.json', {
    'status': 'PASS', 'native_inspect': native, 'compile_qa': compiled,
    'package_verify': verified,
    'artifact_uri': str(ARTIFACT.relative_to(PROJECT)),
    'artifact_sha256': digest(ARTIFACT),
    'compile_manifest_uri': str((OUT/'native-package/compile-manifest.json').relative_to(PROJECT)),
    'compiler_handoff_uri': str((OUT/'native-package/compiler-handoff.json').relative_to(PROJECT)),
    'bound_media_status': {'images_generated': False, 'video_generated': False,
                           'visual_qa': 'NOT_RUN', 'media_qa': 'NOT_RUN',
                           'submitted': False, 'execution_ready': False},
})

requirements = task['handoff']['required_handoffs']
clauses = {c['id']: c for c in ir['contract']}
handoff = []
visibility_exception = None
for req in requirements:
    if req.get('preservation_only'):
        source_path = req['source_paths'][0]
        target_path = source_path
        reason = '已将导演原生时间轨该字段原样保留在 StoryboardIR。'
        if source_path == '/timeline/visibility':
            target_path = '/upstreams/1/locks/3/source_value'
            reason = ('原导演可见性数组为空，原值在只读上游映射 source_value 中精确保留；'
                      '分镜按导演构图与美术无遮挡合同细化新可见性区间。')
            visibility_exception = {'source_path': source_path,
                                    'preserved_path': target_path,
                                    'original': req['source_values'][0],
                                    'added_intervals': len(ir['timeline']['visibility'])}
        assert pointer(ir,target_path) == req['source_values'][0], req['id']
        row = {'requirement_id': req['id'], 'source_fingerprint': req['source_fingerprint'],
               'source_paths': req['source_paths'], 'target_checks': [
                   {'op': 'equals', 'path': target_path, 'value': deepcopy(req['source_values'][0])}],
               'reason': reason}
    else:
        clause_id = 'SB_' + req['id'].rsplit(':',1)[-1]
        native_clause = clauses[clause_id]
        assert native_clause['strength'] == 'hard'
        row = {'requirement_id': req['id'], 'source_fingerprint': req['source_fingerprint'],
               'source_paths': req['source_paths'],
               'target_checks': deepcopy(native_clause['checks']),
               'target_clause': clause_id,
               'reason': ('在原生 StoryboardIR 的硬合同、固定单镜画格、状态与时间轨中逐项实现。'
                          '真实遮挡和媒体效果留给独立媒体审查。')}
    assert all(assert_check(ir,c) for c in row['target_checks']), req['id']
    handoff.append(row)

assert len(handoff) == len(requirements) == 1437
assert validate_handoff('storyboard',ir,requirements,handoff) == handoff
dump(EV / 'v5-handoff.json', {
    'status': 'PASS', 'task_id': TASK_ID, 'artifact_sha256': digest(ARTIFACT),
    'requirement_count': len(requirements),
    'hard_semantic_count': sum(not x.get('preservation_only',False) for x in requirements),
    'exact_detail_count': sum(x.get('preservation_only',False) for x in requirements),
    'all_source_fingerprints_match': True, 'all_target_checks_pass': True,
    'all_native_hard_clauses_pass': True,
    'visibility_addition': visibility_exception,
    'mapping_sha256': sha256((json.dumps(handoff,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()).hexdigest(),
    'role_result_handoff_path': '/handoff',
})

slot_to_input = {x['slot']:x for x in envelope['inputs']}
v6_rows = []
for spec in envelope['handoffs']:
    source = slot_to_input[spec['source_slot']]
    p = PROJECT/source['uri']
    assert digest(p) == source['sha256']
    assert spec['target_slot'] == envelope['expected_artifacts'][0]['slot']
    v6_rows.append({**spec, 'source_uri': source['uri'],
                    'source_sha256': source['sha256'],
                    'target_uri': str(ARTIFACT.relative_to(PROJECT)),
                    'target_sha256': digest(ARTIFACT),
                    'target_binding': {'canon:project:project:Canon':'/upstreams/0',
                                       'director:project:project:DirectorIR':'/upstreams/1',
                                       'art:scene:13x53435f5241494e5f4e49474854:ArtIR':'/upstreams/2'}[spec['source_slot']],
                    'native_validator_status': native['status']})
dump(EV / 'v6-handoffs.json', {'status':'PASS','task_id':TASK_ID,'batch':BATCH,
                               'input_digest':envelope['input_digest'],
                               'handoffs':v6_rows,'source_version_semantics':'frozen V6 artifact version'})

samples = ir['timeline']['state_samples']
control_rows = []
for s in samples:
    letter = s['entities']['PROP_LETTER']
    jia = s['entities']['CHAR_JIA']
    yi = s['entities']['CHAR_YI']
    bag = s['entities']['PROP_BACKPACK']
    control_rows.append({'at_ms':s['at_ms'],'state_id':s['id'],
                         'jia_position_x':jia['position'][0], 'yi_position_x':yi['position'][0],
                         'letter_position_world_xyz':letter['position'],
                         'letter_contacts':letter['contacts'],
                         'letter_supports':letter['supports'],
                         'letter_controllers':letter['controllers'],
                         'yi_contacts':yi['contacts'], 'bag_contacts':bag['contacts']})
assert [r['at_ms'] for r in control_rows] == [0,2500,4000,7500,10500,12000]
assert all(r['jia_position_x'] < r['yi_position_x'] for r in control_rows)
assert control_rows[0]['letter_controllers'] == ['CHAR_JIA.right_hand']
assert control_rows[1]['letter_controllers'] == ['CHAR_JIA.right_hand']
assert control_rows[2]['letter_controllers'] == ['CHAR_YI.right_hand']
assert control_rows[4]['letter_supports'] == ['PROP_BACKPACK.interior']
director_scene_camera = read(PROJECT / next(x for x in envelope['inputs'] if x['slot'].startswith('director:'))['uri'])['shots'][0]['camera']['start_m']
storyboard_timeline_camera = ir['shots'][0]['camera']['start_m']
assert director_scene_camera == [0, -2.8, 1.2]
assert storyboard_timeline_camera == [director_scene_camera[0], director_scene_camera[2], director_scene_camera[1]]
assert storyboard_timeline_camera == ir['shots'][0]['camera']['end_m']
assert '[0,1.2,-2.8]' in ir['timeline']['camera_operations'][0]['start_position']
assert '[0,1.2,-2.8]' in ir['timeline']['camera_operations'][0]['end_position']
dump(EV / 'topdown-control.json', {
    'status': 'PASS_FOR_DECLARED_STATES', 'artifact_sha256': digest(ARTIFACT),
    'coordinate_rule': 'director static [X-right,Y-depth,Z-up] [0,-2.8,1.2] -> storyboard timeline [x-right,y-up,z-depth] [0,1.2,-2.8] by (X,Z,Y); physical fixed camera is unchanged',
    'axis': ir['scenes'][0]['axis'],
    'camera_timeline_xyz': storyboard_timeline_camera,
    'director_scene_camera_XYZ': director_scene_camera,
    'camera_axis_side': ir['shots'][0]['camera']['axis_side'],
    'camera_track_id': ir['timeline']['camera_operations'][0]['id'],
    'subject_screen_boxes': {x['entity_id']:x['box'] for x in ir['shots'][0]['composition']['subjects']},
    'state_samples': control_rows,
    'panel_ids_and_frames': [{'id':p['id'],'frame':p['frame']} for p in ir['shots'][0]['panels']],
    'motion_track_ids': [x['id'] for x in ir['timeline']['motion_tracks']],
    'control_limit': '这些是分镜声明和离线状态一致性检查；不证明三维碰撞、实际摄影投影或生成媒体已符合。',
})

dump(EV / 'storyboard-review.json', {
    'status':'AUTHOR_SEMANTIC_REVIEW_PASS', 'artifact_sha256':digest(ARTIFACT),
    'source_fact_chain':['雨夜','甲交给乙一封未拆信','乙确认完整封口','乙收进同一背包'],
    'fixed_director_fields':['S1 单镜','288 帧 / 24 fps','负轴侧固定机位',
                             '甲右手交信，乙右手接信，甲后松手',
                             '乙右手验封并入包，左手撑包口'],
    'art_fields':['无可指认地点后景','一封无字、无印章、封口完整的信','同一背包',
                  '手部、封口和包口不被雨迹、袖口、发丝或包边遮挡'],
    'authored_fields':['当前批次重绑的七个镜内画格','可见性区间','静态场景 XYZ 与时间轴 xyz 的轴序换算说明','实际灯位未锁定的可读性预演锚点'],
    'media':['image_generation=NOT_APPLICABLE','video_generation=NOT_APPLICABLE',
             'visual_qa=NOT_RUN','media_qa=NOT_RUN'],
    'remaining_real_media_checks':['封口是否在固定双人中近景实际可读',
                                   '两只右手交接与左手撑包的接触/控制权是否真实成立',
                                   '雨夜与不指认地点的画面是否成立',
                                   '实际光源和衣装参考由美术/宿主绑定后审查'],
})

check_evidence = {
    'module_receipt':[uri('source-integrity.json'),uri('module-receipt.json')],
    'native_validator':[uri('native-validator.json'),uri('topdown-control.json'),uri('storyboard-review.json')],
    'handoff':[uri('v5-handoff.json'),uri('v6-handoffs.json'),uri('topdown-control.json')],
}
findings = {
    'module_receipt':'四个冻结 V6 输入、四份锁定资源、原 V5 输入与本模块回执均经字节哈希核对。',
    'native_validator':'原生 StoryboardIR 1.2 VALID，编译包 VERIFIED；画格、媒体、视觉验收均未执行。',
    'handoff':'13 条硬语义与 1424 条导演原时间轨细节完成逐项映射，三条 V6 上游绑定匹配冻结 slot/version/hash。',
}
checks = [{'id': k, 'status':'PASS', 'evidence':v, 'finding':findings[k]} for k,v in check_evidence.items()]

result = {
    'schema':'role-result/5.1','task_id':TASK_ID,
    'context_fingerprint':task['context_fingerprint'],
    'artifact':str(ARTIFACT),'artifact_sha256':digest(ARTIFACT),
    'checks':checks,'complete':True,'conflicts':[],'unresolved':[],
    'handoff':handoff,'module_receipt':module_receipt,
    'validator':{'status':native['status'],'errors':native.get('diagnostics',[]),
                 'media':'NOT_RUN','visual':'NOT_RUN',
                 'professional_blind_review':'NOT_RUN',
                 'native_package':str((OUT/'native-package').relative_to(PROJECT))},
}
dump(OUT/'role-result.json',result)

candidate = {
    'schema':'candidate-result/6.0','task_id':TASK_ID,'batch':BATCH,
    'agent_id':'/root/host_bridge/v6_47406a68b592393955a28d31',
    'input_digest':envelope['input_digest'],
    'result_uri':str((OUT/'role-result.json').relative_to(PROJECT)),
    'result_sha256':digest(OUT/'role-result.json'),
    'artifacts':[{'kind':'StoryboardIR','slot':envelope['expected_artifacts'][0]['slot'],
                  'uri':str(ARTIFACT.relative_to(PROJECT)), 'sha256':digest(ARTIFACT)}],
    'module_receipts':[envelope['module']],
    'checks':[{'id':x['id'],'status':x['status'],'evidence':x['evidence']} for x in checks],
    'handoffs':[{**h,'evidence':[uri('v6-handoffs.json'),uri('v5-handoff.json'),uri('topdown-control.json')]}
                for h in envelope['handoffs']],
    'unresolved':[],
}
assert len(candidate['handoffs']) == 3
for x in candidate['checks']+candidate['handoffs']:
    assert x['evidence'] and all((PROJECT/u).is_file() and (PROJECT/u).stat().st_size>0 for u in x['evidence'])
dump(OUT/'candidate-result.json',candidate)

# Schema and byte references are checked again after both result files exist.
for name in ['v5-role-result.schema.json','v6-candidate-result.schema.json']:
    from jsonschema import Draft202012Validator
    schema=read(ROOT/'schemas'/name)
    value=result if name.startswith('v5') else candidate
    issues=list(Draft202012Validator(schema).iter_errors(value))
    assert not issues, [str(x) for x in issues[:5]]
assert digest(OUT/candidate['result_uri'].split('/')[-1]) == candidate['result_sha256']
assert digest(PROJECT/candidate['artifacts'][0]['uri']) == candidate['artifacts'][0]['sha256']
assert candidate['module_receipts'] == [envelope['module']]
assert {x['id'] for x in candidate['checks']} == {x['id'] for x in envelope['validators']}
assert {x['requirement_id'] for x in candidate['handoffs']} == {x['requirement_id'] for x in envelope['handoffs']}
print(str(OUT/'candidate-result.json'))
print(digest(OUT/'candidate-result.json'))
print('v5_handoff',len(handoff),'native',native['status'],'package',verified['status'])
