import hashlib
import json
from pathlib import Path


ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
TASK_ID = 'TASK_6cac2b25585760d16bce096d'
AGENT_ID = '/root/host_bridge/v6_af960c7614b2f0ebf91c02d9'
CAND = ROOT / f'runtime/v6/candidates/{TASK_ID}/1'
EVIDENCE = CAND / 'evidence'
COMPILE = ROOT / 'runtime/v6/candidates/V6_compile_297e4d54680b970deaed/1'
OLD_REVIEW = ROOT / 'runtime/v6/candidates/TASK_ede3a3425d547d3569e53ec4/1/compile-review.json'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def uri(path):
    return path.relative_to(ROOT).as_posix()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


action = read(Path('/private/tmp/ai-video-v6-real-efKlQy/reviewfix-compile-review-submit-out.json'))['actions'][0]
envelope = json.loads(action['arguments']['message'].split('Frozen task envelope:\n', 1)[1])
task = read(ROOT / f'runtime/tasks/{TASK_ID}.json')
avir = read(COMPILE / 'avir.json')
manifest = read(COMPILE / 'compile-manifest.json')
compiled = Path(manifest['asset_base']) / 'compiled'
artifact = read(compiled / 'artifact.json')
delivery = read(compiled / 'segment-delivery.json')
post = read(compiled / 'post-production.json')
coverage = read(compiled / 'constraint-coverage.json')
prompt_file = compiled / 'prompt-001_000000-012000ms.txt'
prompt = prompt_file.read_text()
storyboard_path = Path(task['brief']['inputs'][0]['uri'])
storyboard = read(storyboard_path)
source_path = ROOT / 'sources/SRC_69a71adcfaca/source.txt'
source_text = source_path.read_text().strip()
old_review = read(OLD_REVIEW)
old_avir_path = ROOT / 'runtime/v6/candidates/V6_compile_3d390e1ba62af9b653ce/1/avir.json'
old_avir = read(old_avir_path)
compile_reviewer_path = ROOT / 'runtime/v6/reviews/V6_compile_297e4d54680b970deaed/1/review-record.json'
compile_reviewer = read(compile_reviewer_path)
validator = read(EVIDENCE / 'avir-validator.stdout.json')
verifier = read(EVIDENCE / 'build-verify.stdout.json')

assert action['task_id'] == TASK_ID and action['batch'] == envelope['batch'] == 1
assert action['dispatch_id'] == 'dispatch-e6f4239baff8a457126610ec'
assert envelope['role'] == 'compiler_reviewer' and envelope['node_id'] == 'compile_review'
assert task['context_fingerprint'] == envelope['task_id'].removeprefix('TASK_') + '0c48382f815e5f8b69c841215d691c7968fdfc94'
for item in envelope['inputs'] + envelope['resources']:
    assert sha(ROOT / item['uri']) == item['sha256'], item['uri']
assert sha(storyboard_path) == task['brief']['inputs'][0]['sha256']
assert sha(source_path) == task['sources'][0]['sha256']
assert source_text == '雨夜，甲把一封未拆的信交给乙；乙确认封口完整后收进背包。'
assert manifest['build_id'] == task['build']['build_id']
assert sha(COMPILE / 'avir.json') == manifest['input_hash']
assert sha(COMPILE / 'compile-manifest.json') == envelope['inputs'][1]['sha256']
for name, expected in manifest['files'].items():
    assert sha(compiled / name) == expected, name
assert {check['status'] for check in compile_reviewer['checks']} == {'PASS'}
assert compile_reviewer['task_id'] == 'V6_compile_297e4d54680b970deaed'
assert validator == {'status': 'VALID', 'diagnostics': []}
assert verifier == {'status': 'VERIFIED', 'build_id': manifest['build_id']}

clause_ids = task['hard_clauses']
assert len(clause_ids) == len(set(clause_ids)) == 17
assert set(clause_ids) == {c['id'] for c in storyboard['contract']}
assert set(clause_ids) == {c['id'] for c in avir['contract'] if c['level'] == 'hard'}
assert set(clause_ids) == {c['id'] for c in coverage}
assert all(c['static_assertions'] == 'PASS' and c['realization'] == 'NOT_RUN' for c in coverage)
assert avir['project_id'] == storyboard['project_id'] == task['project_id'] == 'LETTER_DEMO'
assert len(avir['shots']) == 1 and avir['shots'][0]['id'] == 'S1'
assert avir['shots'][0]['start_ms'] == 0 and avir['shots'][0]['end_ms'] == 12000
assert [e['id'] for e in avir['entities']] == ['CHAR_JIA', 'CHAR_YI', 'PROP_LETTER', 'PROP_BACKPACK', 'ENV_RAIN_NIGHT']
assert avir['assets'] == avir['bindings'] == []
assert avir['audio'] == {'cues': [], 'utterances': []}
assert '雨夜' in avir['scenes'][0]['description'] and '未指定' in avir['scenes'][0]['description']
assert '雨夜' in prompt and '具体地点、年代与室内外未指定' in prompt
assert '只使用 PROP_LETTER 这一封未拆且封口完整的信' in prompt
assert '不出现额外剧情' in prompt and '不延伸后续' in prompt

actions = [(a['id'], a['start_ms'], a['end_ms']) for a in avir['timeline']['actions']]
assert actions == [('ACT_EXTEND', 500, 1800), ('ACT_GRIP', 2000, 2800),
                   ('ACT_RELEASE', 2800, 4000), ('ACT_CONFIRM_SEAL', 4500, 7500),
                   ('ACT_STOW', 8000, 11000)]
assert actions == [(a['id'], a['start_ms'], a['end_ms']) for a in storyboard['timeline']['actions']]
panels = avir['timeline']['extensions'][0]['payload']['panels'][0]['items']
panel_points = [(p['id'], p['frame']) for p in panels]
assert panel_points == [('P_OPEN', 0), ('P_GRIP', 60), ('P_RELEASE', 84),
                        ('P_SEAL', 144), ('P_BAG_OPEN', 204), ('P_STOWED', 252), ('P_END', 287)]
assert prompt.index('【动作 第3项动作｜2.8–4秒】') < prompt.index('【动作 第4项动作｜4.5–7.5秒】')
assert prompt.index('【动作 第4项动作｜4.5–7.5秒】') < prompt.index('【动作 第5项动作｜8–11秒】')
assert '2.5秒：两只右手同时接触一封信' in prompt
assert '3.5秒：信的控制权由甲转给乙' in prompt
assert '6秒：封口完整可读且乙正在确认' in prompt
assert '10.5秒：同一封信完成收存，控制权解除' in prompt

samples = {s['at_ms']: s['entities']['PROP_LETTER'] for s in avir['timeline']['state_samples']}
source_samples = {s['at_ms']: s['entities']['PROP_LETTER'] for s in storyboard['timeline']['state_samples']}
assert samples[2500]['contacts'] == ['CHAR_JIA.right_hand', 'CHAR_YI.right_hand']
assert samples[2500]['controllers'] == ['CHAR_JIA.right_hand']
assert samples[4000]['controllers'] == ['CHAR_YI.right_hand']
assert samples[7500]['visible_parts'] == ['body', 'seal'] and '封口' in samples[7500]['pose']
for ms in (10500, 12000):
    assert samples[ms]['visible_parts'] == source_samples[ms]['visible_parts'] == []
    assert samples[ms]['contacts'] == samples[ms]['supports'] == ['PROP_BACKPACK.interior']
    assert samples[ms]['controllers'] == []
current_end = next(x for x in avir['shots'][0]['end_state'] if x['entity_id'] == 'PROP_LETTER')
old_end = next(x for x in old_avir['shots'][0]['end_state'] if x['entity_id'] == 'PROP_LETTER')
assert old_review['finding_code'] == 'AVIR_END_VISIBILITY_CONFLICT'
assert old_end['visible_parts'] == ['body', 'prop']
assert current_end['visible_parts'] == samples[12000]['visible_parts'] == []
assert '10.5秒，同一封信的可见部位从“身体、seal”变为“无”。' in prompt
assert '同一封信：接触部位：PROP_BACKPACK.interior；控制部位：无' in prompt
assert '同一封信：信已经入包，由包体遮住；画面不呈现后续；在画内；中景；可见部位：无' in prompt

camera = avir['shots'][0]['camera']
assert camera['position'] == [0, 1.2, -2.8] and camera['axis_side'] == 'A'
assert '固定' in camera['movement'] and prompt.count('[0,1.2,-2.8]') >= 2
assert '固定机位在负 Z 深度同侧' in prompt
assert '完整封口、乙眼部及右手在固定画幅中可读' in prompt

assert artifact['status'] == 'COMPILED'
assert artifact['execution']['submitted'] is False
assert artifact['execution']['runnable'] is False
assert artifact['execution']['media_qa'] == 'NOT_RUN'
assert delivery['status'] == 'DRAFT_REQUIRES_TARGET_CHECK'
assert delivery['execution'] == 'NOT_RUN'
assert [(p['project_start_ms'], p['project_end_ms']) for p in delivery['parts']] == [(0, 12000)]
assert delivery['parts'][0]['prompt_sha256'] == sha(prompt_file)
assert delivery['parts'][0]['reference_files'] == []
assert [(p['id'], p['status']) for p in post] == [('AUD_RAIN', 'PLANNED'), ('SB_MEDIA_BOUNDARY', 'PLANNED')]

findings = {
    'SB_A_RAIN': ('源文雨夜进入场景与正文；未指定具体地点、年代或室内外。', ['/scenes/0/description', 'prompt:雨夜']),
    'SB_A_SINGLE_LETTER': ('AVIR 唯一 PROP_LETTER；正文锁定同一封未拆且完整封口的信。', ['/entities/2/id', 'prompt:PROP_LETTER']),
    'SB_A_ORDER': ('交接在 0.5–4 秒，验封在 4.5–7.5 秒，收存从 8 秒开始。', ['/timeline/actions/0-4', 'prompt:动作1-5']),
    'SB_A_ENDING': ('10.5 秒信入同一背包，12 秒仅保持结果；无后续剧情。', ['/timeline/state_samples/4-5', 'prompt:10.5秒']),
    'SB_A_EVENTS': ('P_GRIP、P_SEAL、P_STOWED 均有相应动作和计划画格。', ['/timeline/extensions/0/payload/panels/0/items', 'prompt:扩展要求']),
    'SB_A_REVEAL': ('交接控制权、完整封口、入包证据按 84、144、252 帧展开。', ['/timeline/extensions/0/payload/panels/0/items/2-5', 'prompt:动作3-5']),
    'SB_A_ASSET_LOCKS': ('甲乙、唯一信、同一背包和雨夜连续性作为制作约束；参考未生成或审图。', ['/entities', '/assets', '/bindings']),
    'SB_D_RAIN': ('正文保留雨夜且未增补具体地点或室内外事实。', ['/scenes/0/description', 'prompt:场景']),
    'SB_D_SINGLE_LETTER': ('同一信从甲右手转乙右手，最终进入同一背包；封口未拆。', ['/timeline/state_samples', 'prompt:同一封信']),
    'SB_D_ACTION_ORDER': ('ACT_RELEASE 在 ACT_CONFIRM_SEAL 前，后者在 ACT_STOW 前。', ['/timeline/actions/2-4', 'prompt:动作3-5']),
    'SB_D_ENDING': ('终态为信在背包内，镜头只保持结果。', ['/shots/0/end_state/4', 'prompt:10.5–12秒']),
    'SB_D_EVENTS': ('三项原故事事件各有动作和反馈；未增加对白或后续事件。', ['/timeline/actions', '/audio']),
    'SB_D_REVEAL_ORDER': ('P_RELEASE 84 帧、P_SEAL 144 帧、P_STOWED 252 帧与正文顺序相同。', ['/timeline/extensions/0/payload/panels/0/items', 'prompt:动作3-5']),
    'SB_FIXED_AXIS': ('固定机位 [0,1.2,-2.8] 与正文起止机位一致，位于负 Z 同侧。', ['/shots/0/camera', 'prompt:摄影机操作']),
    'SB_CONTACT_CONTROL': ('2.5 秒双右手共同接触而甲仍控制；3.5 秒乙独占，早于验封。', ['/timeline/state_samples/1-2', 'prompt:2.5秒、3.5秒']),
    'SB_SEAL_VISIBILITY': ('验封时封口、乙眼部和右手规划为可读；真实媒体尚未验证。', ['/timeline/state_samples/3', 'prompt:4–8秒构图']),
    'SB_MEDIA_BOUNDARY': ('无真实参考或媒体执行；雨声和媒体义务仍为后期 PLANNED。', ['/assets', '/bindings', 'compiled:post-production.json']),
}
assert set(findings) == set(clause_ids)
clause_findings = [{'id': id_, 'finding': findings[id_][0], 'evidence_pointers': findings[id_][1]}
                   for id_ in clause_ids]
semantic_clauses = [{'id': item['id'], 'finding': item['finding']} for item in clause_findings]
module_reads = [x for x in envelope['resources'] if x['uri'].startswith('runtime/modules/')]
write(EVIDENCE / 'module-receipt.evidence.json', {
    'module': envelope['module'],
    'frozen_inputs': [{**x, 'verified': True} for x in envelope['inputs']],
    'locked_reads': [{**x, 'verified': True} for x in module_reads],
    'runtime_resources': [{**x, 'verified': True} for x in envelope['resources'] if x not in module_reads],
})
prior_defect = {
    'finding_code': 'AVIR_END_VISIBILITY_CONFLICT',
    'old_build_id': old_review['build_id'], 'old_review_uri': uri(OLD_REVIEW),
    'old_review_sha256': sha(OLD_REVIEW), 'old_end_visible_parts': old_end['visible_parts'],
    'current_avir_end_visible_parts': current_end['visible_parts'],
    'current_timeline_end_visible_parts': samples[12000]['visible_parts'],
    'source_storyboard_end_visible_parts': source_samples[12000]['visible_parts'],
    'status': 'CLOSED_IN_CURRENT_BUILD',
}
boundaries = {
    'compiled_status': artifact['status'], 'segment_status': delivery['status'],
    'target': manifest['target'], 'transport': 'unresolved',
    'post_obligations': [{'id': p['id'], 'status': p['status']} for p in post],
    'media_qa': artifact['execution']['media_qa'],
    'submitted': artifact['execution']['submitted'], 'runnable': artifact['execution']['runnable'],
}
write(EVIDENCE / 'compile-semantics.evidence.json', {
    'reviewer_agent_id': AGENT_ID,
    'review_scope': 'static preproduction compile semantics',
    'source': {'uri': uri(source_path), 'sha256': sha(source_path), 'text': source_text},
    'storyboard': {'uri': uri(storyboard_path), 'sha256': sha(storyboard_path)},
    'current_build': {
        'build_id': manifest['build_id'], 'manifest_uri': uri(COMPILE / 'compile-manifest.json'),
        'manifest_sha256': sha(COMPILE / 'compile-manifest.json'),
        'avir_uri': uri(COMPILE / 'avir.json'), 'avir_sha256': sha(COMPILE / 'avir.json'),
        'files_checked': len(manifest['files']), 'manifest_files_match': True,
        'compile_review_uri': uri(compile_reviewer_path),
        'compile_review_sha256': sha(compile_reviewer_path),
    },
    'native_validation': {'avir_validator': validator, 'compiled_package_verifier': verifier,
                          'validator_stdout_uri': uri(EVIDENCE / 'avir-validator.stdout.json'),
                          'verify_stdout_uri': uri(EVIDENCE / 'build-verify.stdout.json')},
    'prior_defect': prior_defect,
    'actions': [{'id': id_, 'start_ms': start, 'end_ms': end} for id_, start, end in actions],
    'key_panels': [{'id': id_, 'frame': frame} for id_, frame in panel_points],
    'camera': {'position': camera['position'], 'axis_side': camera['axis_side'],
               'prompt_start_end': '[0,1.2,-2.8]'},
    'hard_clauses': clause_findings, 'boundaries': boundaries, 'equivalent': True,
})
write(CAND / 'compile-review.json', {
    'project_id': 'LETTER_DEMO', 'build_id': manifest['build_id'],
    'equivalent': True, 'review_scope': 'static preproduction compile semantics',
    'finding': '源文、StoryboardIR、当前 AVIR、逐段正文与 17 条硬要求在静态制作语义上一致；信件终态可见性旧缺陷已关闭。媒体与后期义务仍待真实执行。',
    'prior_defect': prior_defect, 'hard_clauses': semantic_clauses,
    'other_boundaries': boundaries,
    'source_evidence': {'compile_manifest_uri': uri(COMPILE / 'compile-manifest.json'),
                        'compile_manifest_sha256': sha(COMPILE / 'compile-manifest.json'),
                        'semantic_evidence_uri': uri(EVIDENCE / 'compile-semantics.evidence.json'),
                        'semantic_evidence_sha256': sha(EVIDENCE / 'compile-semantics.evidence.json')},
})
write(CAND / 'role-result.json', {
    'schema': 'role-result/5.1', 'task_id': TASK_ID,
    'context_fingerprint': task['context_fingerprint'],
    'artifact': str(CAND / 'compile-review.json'),
    'artifact_sha256': sha(CAND / 'compile-review.json'),
    'checks': [
        {'id': 'module_receipt', 'finding': '冻结输入与锁定资源的 SHA-256 全部匹配。'},
        {'id': 'compile_semantics', 'finding': '17 项硬条款逐项核对，当前静态语义一致，历史可见性冲突已关闭。'},
    ],
    'conflicts': [], 'unresolved': [], 'complete': True,
    'validator': {'status': validator['status'], 'diagnostics': validator['diagnostics'],
                  'evidence': uri(EVIDENCE / 'avir-validator.stdout.json')},
    'module_receipt': {'name': envelope['module']['name'], 'version': envelope['module']['version'],
                       'skill_sha256': module_reads[0]['sha256'],
                       'reads': [{'path': str(ROOT / x['uri']), 'sha256': x['sha256']} for x in module_reads]},
    'semantic_review': {'build_id': manifest['build_id'], 'equivalent': True,
                        'clauses': semantic_clauses, 'blocked': [],
                        'evidence': uri(CAND / 'compile-review.json')},
})
write(CAND / 'candidate-result.json', {
    'schema': 'candidate-result/6.0', 'task_id': TASK_ID, 'batch': 1,
    'agent_id': AGENT_ID, 'input_digest': envelope['input_digest'],
    'result_uri': uri(CAND / 'role-result.json'), 'result_sha256': sha(CAND / 'role-result.json'),
    'artifacts': [{'slot': 'compile_review:project:project:CompileReview', 'kind': 'CompileReview',
                   'uri': uri(CAND / 'compile-review.json'), 'sha256': sha(CAND / 'compile-review.json')}],
    'module_receipts': [envelope['module']],
    'checks': [
        {'id': 'module_receipt', 'status': 'PASS', 'evidence': [uri(EVIDENCE / 'module-receipt.evidence.json')]},
        {'id': 'compile_semantics', 'status': 'PASS',
         'evidence': [uri(EVIDENCE / 'compile-semantics.evidence.json'),
                      uri(EVIDENCE / 'avir-validator.stdout.json'),
                      uri(EVIDENCE / 'build-verify.stdout.json')]},
    ],
    'handoffs': [], 'unresolved': [],
})
print(json.dumps({'candidate_uri': uri(CAND / 'candidate-result.json'),
                  'candidate_sha256': sha(CAND / 'candidate-result.json'),
                  'role_result_sha256': sha(CAND / 'role-result.json'),
                  'artifact_sha256': sha(CAND / 'compile-review.json'),
                  'hard_clause_count': len(clause_ids), 'build_id': manifest['build_id']}, ensure_ascii=False))
