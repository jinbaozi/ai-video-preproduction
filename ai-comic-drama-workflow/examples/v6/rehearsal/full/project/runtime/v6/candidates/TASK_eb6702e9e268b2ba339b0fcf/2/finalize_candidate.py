#!/usr/bin/env python3
"""Write only candidate evidence and the V6 candidate submission record."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
REL = 'runtime/v6/candidates/TASK_eb6702e9e268b2ba339b0fcf/2'
OUT = ROOT / REL
MODREL = 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
MOD = ROOT / MODREL
TASK = json.loads((ROOT / 'runtime/tasks/TASK_eb6702e9e268b2ba339b0fcf.json').read_text())
IR = json.loads((OUT / 'director-ir.json').read_text())
MAP = json.loads((OUT / 'screenplay-map.json').read_text())

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()

def write(rel, value):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
    return path

def filehash(path):
    return sha256(path.read_bytes()).hexdigest()

def pointer(value, path):
    for key in path.strip('/').split('/') if path else []:
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value

reads = []
for item in TASK['module']['required_reads']:
    path = Path(item['path'])
    actual = filehash(path)
    assert actual == item['sha256'], (path, actual, item['sha256'])
    reads.append({'path': str(path), 'sha256': actual})
frozen_inputs = [
    ('canon:project:project:Canon', 'runtime/v6/candidates/TASK_5ae2734678bb041b76474d34/1/canon.json', '0cc4aebffda6a714d5c58695c11f7d70b96359d930125b04edb8fe14abfc4ef9'),
    ('screenplay:project:project:ScriptIR', 'runtime/v6/candidates/TASK_20dbe9991f545d5fe05e55e7/2/script-ir.json', '256bd6ad450cc44f312453fa58e93fcccc8af15dfd0069c4bb765746d6faedeb'),
    ('frozen_task', 'runtime/tasks/TASK_eb6702e9e268b2ba339b0fcf.json', '7a838c5a39714a38f6bd1f8a93bb3a3bc3fc4c52ba0649dccfa895715e9ff710'),
]
verified_inputs = []
for slot, uri, expected in frozen_inputs:
    actual = filehash(ROOT / uri)
    assert actual == expected, (uri, actual, expected)
    verified_inputs.append({'slot': slot, 'uri': uri, 'sha256': actual})
assert TASK['module']['sha256'] == '0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64'
assert TASK['module']['skill_sha256'] == reads[0]['sha256']
receipt = {'module': {'name': 'director-grammar', 'version': '1.4.2',
                      'sha256': TASK['module']['sha256'], 'skill_sha256': reads[0]['sha256']},
           'reads': reads, 'inputs': verified_inputs, 'status': 'PASS',
           'meaning': '只证明冻结输入与模块资源的字节完整性。'}
write('evidence/module-receipt.json', receipt)

# Current-agent semantic checks are distinct from media review.
actions = IR['timeline']['actions']
assert [a['semantic_id'] for a in actions] == ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW']
assert [a['start_ms'] for a in actions] == [0, 3000, 6000]
assert all(a['target_id'] == 'PROP_LETTER' for a in actions)
assert all('未拆' in s['entities']['PROP_LETTER']['condition'] for s in IR['timeline']['state_samples'])
assert all(not shot['dialogue'] for shot in IR['shots'])
assert not any(a['kind'] in ('dialogue', 'narration', 'internal_voice') for a in IR['timeline']['audio_events'])
assert '雨夜' in IR['scenes'][0]['space'] and '雨' in IR['timeline']['audio_events'][0]['text']
assert 'PROP_BACKPACK.interior' in IR['timeline']['state_samples'][-1]['entities']['PROP_LETTER']['contacts']
assert IR['timeline']['semantic_review']['status'] == 'PASS'

py_path = ':'.join([
    '/Users/godxu/.cache/uv/archive-v0/TK02J0RuK_nOFXOAGDYJR',
    '/Users/godxu/.cache/uv/archive-v0/xQSC8Tqop6tuPc9NFMkra',
    '/Users/godxu/.cache/uv/archive-v0/L20ORuYbRsszl9aKe6zvO',
    '/Users/godxu/.cache/uv/archive-v0/k16g8eF2x-kfTzzctmJoS',
    '/Users/godxu/.cache/uv/archive-v0/AHGrvaVLuv5UvdY7lailf',
])
probe_script = '''import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from spatial_runtime import panel_state
ir = json.loads(Path(sys.argv[2]).read_text())
samples = []
for at in (6000, 8500, 9000):
    panel = panel_state(ir, 'S_STOW', at)
    letter = panel['state']['PROP_LETTER']
    samples.append({'at_ms': at, 'status': panel['status'],
                    'composition_id': panel['composition']['id'],
                    'subject_nodes': [s['node_id'] for s in panel['composition']['subjects']],
                    'letter_contacts': letter['contacts'], 'letter_supports': letter['supports'],
                    'letter_visible_parts': letter['visible_parts'],
                    'physical_interpolation': panel['physical_interpolation']})
print(json.dumps(samples, ensure_ascii=False))'''
probe_cmd = ['python3.12', '-B', '-c', probe_script, str(MOD / 'scripts'), str(OUT / 'director-ir.json')]
probe_process = subprocess.run(probe_cmd, cwd=ROOT, env={**os.environ, 'PYTHONPATH': py_path}, text=True, capture_output=True)
assert probe_process.returncode == 0, probe_process.stdout + probe_process.stderr
panel_samples = json.loads(probe_process.stdout)
assert panel_samples[0]['status'] == 'EXPLICIT' and 'N_PROP_LETTER' in panel_samples[0]['subject_nodes']
assert panel_samples[1]['status'] == panel_samples[2]['status'] == 'EXPLICIT'
assert all('N_PROP_LETTER' not in s['subject_nodes'] for s in panel_samples[1:])
assert all(s['letter_contacts'] == s['letter_supports'] == ['PROP_BACKPACK.interior'] for s in panel_samples[1:])
assert all(not s['letter_visible_parts'] and not s['physical_interpolation'] for s in panel_samples[1:])
assert 'PROP_LETTER' not in IR['shots'][2]['composition']['attention_order']
assert all(s['entity_id'] != 'PROP_LETTER' for s in IR['shots'][2]['composition']['subjects'])
assert '信已完全在包内' in IR['shots'][2]['camera']['framing_end']
continuity = {'status': 'PASS',
    'prior_review_uri': 'runtime/v6/reviews/TASK_eb6702e9e268b2ba339b0fcf/1/native-validator.review.json',
    'prior_defect': '9000毫秒信已在包内，构图仍把信列为无遮挡可见前景。',
    'resolution': '8500毫秒完成入包并建立显式关键状态；6000至8500毫秒显示送信，8500至9000毫秒只显示乙与背包；终帧摘要也不把信列为可见主体。',
    'source': MODREL + '/scripts/spatial_runtime.py panel_state and composition validation',
    'source_check': 'runtime requires adjacent nonoverlapping composition intervals with full shot coverage; panel_state uses the explicit endpoint state.',
    'target_pointers': ['/shots/2/composition', '/shots/2/camera/framing_end', '/timeline/actions/2/changes', '/timeline/state_samples/5', '/timeline/state_samples/6', '/timeline/composition_tracks/2', '/timeline/composition_tracks/3'],
    'panel_samples': panel_samples, 'director_sha256': filehash(OUT / 'director-ir.json')}
write('evidence/stow-continuity.json', continuity)
cmd = ['python3.12', str(MOD / 'scripts/dg.py'), 'validate', str(OUT / 'director-ir.json'),
       '--screenplay-handoff', str(ROOT / 'runtime/v6/candidates/TASK_20dbe9991f545d5fe05e55e7/2/compiled/director-handoff.json'),
       '--screenplay-map', str(OUT / 'screenplay-map.json')]
process = subprocess.run(cmd, cwd=ROOT, env={**os.environ, 'PYTHONPATH': py_path}, text=True, capture_output=True)
assert process.returncode == 0, process.stdout + process.stderr
report = json.loads(process.stdout)
assert report['status'] == 'STATIC_VALID' and report['errors'] == []
assert report['screenplay_binding']['status'] == 'REVIEW_ATTESTED'
native = {'status': 'PASS', 'validator': MODREL + '/scripts/dg.py validate',
          'command_argv': cmd, 'exit_code': process.returncode, 'report': report,
          'director_sha256': filehash(OUT / 'director-ir.json'),
          'screenplay_map_sha256': filehash(OUT / 'screenplay-map.json'),
          'semantic_review': 'CURRENT_AGENT_ATTESTED',
          'media': 'NOT_RUN', 'professional_blind_review': 'NOT_RUN',
          'note': '原生静态校验及当前 Agent 语义复核；8500/9000毫秒 panel_state 连续性见 stow-continuity.json。真实媒体尚未执行。'}
write('evidence/native-validator.json', native)

canon = json.loads((ROOT / frozen_inputs[0][1]).read_text())
canon_mappings = [
    {'source_pointer': '/source_requirements/0', 'target_pointers': ['/contract/clauses/0', '/scenes/0/space', '/timeline/audio_events/0/text']},
    {'source_pointer': '/source_requirements/1', 'target_pointers': ['/contract/clauses/1', '/entities/2', '/timeline/actions/0', '/timeline/actions/1', '/timeline/actions/2']},
    {'source_pointer': '/source_requirements/2', 'target_pointers': ['/contract/clauses/2', '/beats', '/timeline/actions']},
]
assert [pointer(canon, m['source_pointer'])['id'] for m in canon_mappings] == [x['id'] for x in canon['source_requirements']]
for mapping in canon_mappings:
    for path in mapping['target_pointers']:
        assert pointer(IR, path) is not None
canon_handoff = {'requirement_id': 'UP_9574ea9e1502535dcd879c58', 'channel': 'artifact',
    'source_slot': 'canon:project:project:Canon', 'source_version': 12,
    'source_uri': frozen_inputs[0][1], 'source_sha256': frozen_inputs[0][2],
    'target_slot': 'director:project:project:DirectorIR', 'target_pointer': '',
    'target_uri': REL + '/director-ir.json', 'target_sha256': native['director_sha256'],
    'mapping': canon_mappings,
    'finding': '雨夜、同一封未拆信及交接→验封→入包顺序进入原生导演合同、动作和关键状态。'}
write('evidence/handoff-canon.json', canon_handoff)

required = {r['id']: r for r in TASK['handoff']['required_handoffs']}
clauses = {c['id']: c for c in IR['contract']['clauses']}
for mapping in MAP['mappings']:
    assert mapping['source_fingerprint'] == required[mapping['requirement_id']]['source_fingerprint']
    clause = clauses[mapping['target_clause']]
    assert clause['priority'] == 'hard'
    for check in mapping['target_checks']:
        actual = pointer(IR, check['path'])
        assert actual == check['value'] if check['op'] == 'equals' else check['value'] in actual
script_handoff = {'requirement_id': 'UP_84941d3b7d9370ab514cb086', 'channel': 'artifact',
    'source_slot': 'screenplay:project:project:ScriptIR', 'source_version': 16,
    'source_uri': frozen_inputs[1][1], 'source_sha256': frozen_inputs[1][2],
    'target_slot': 'director:project:project:DirectorIR', 'target_pointer': '',
    'target_uri': REL + '/director-ir.json', 'target_sha256': native['director_sha256'],
    'screenplay_map_uri': REL + '/screenplay-map.json',
    'screenplay_map_sha256': native['screenplay_map_sha256'],
    'mapping': MAP['mappings'],
    'finding': '六条编剧交接逐项映射至原生 hard clause 和实际视听字段；dg.py 校验返回 REVIEW_ATTESTED。'}
write('evidence/handoff-screenplay.json', script_handoff)
handoff_check = {'status': 'PASS', 'canon_source_requirements': len(canon_mappings),
                 'screenplay_required_handoffs': len(required), 'screenplay_mapped_handoffs': len(MAP['mappings']),
                 'native_hard_clauses': [m['target_clause'] for m in MAP['mappings']],
                 'semantic_finding': '雨夜未指定地点；同一信件 ID 贯穿；先交接、后验封、8500毫秒入包并在9000毫秒保持不可见；无新增对白。',
                 'media': 'NOT_RUN'}
write('evidence/handoff-check.json', handoff_check)

checks = [
    {'id': 'module_receipt', 'status': 'PASS', 'finding': '冻结模块四份必读资源和三项冻结输入哈希吻合。',
     'evidence': [REL + '/evidence/module-receipt.json']},
    {'id': 'native_validator', 'status': 'PASS', 'finding': 'DirectorIR 1.2 原生静态校验无错误，编剧绑定为 REVIEW_ATTESTED；9000毫秒信不外露的旧缺陷已按 panel_state 显式复核，媒体未执行。',
     'evidence': [REL + '/evidence/native-validator.json', REL + '/evidence/stow-continuity.json']},
    {'id': 'handoff', 'status': 'PASS', 'finding': 'Canon 三项硬要求与 ScriptIR 六条交接均映射到原生导演字段。',
     'evidence': [REL + '/evidence/handoff-canon.json', REL + '/evidence/handoff-screenplay.json', REL + '/evidence/handoff-check.json']},
]
handoffs = []
for row, evidence in [
    (canon_handoff, [REL + '/evidence/handoff-canon.json', REL + '/evidence/handoff-check.json']),
    (script_handoff, [REL + '/evidence/handoff-screenplay.json', REL + '/evidence/handoff-check.json'])]:
    handoffs.append({k: row[k] for k in ('requirement_id', 'channel', 'source_slot', 'source_version', 'target_slot', 'target_pointer')} | {'evidence': evidence})

role_result = {'schema': 'role-result/5.1', 'task_id': 'TASK_eb6702e9e268b2ba339b0fcf',
    'context_fingerprint': TASK['context_fingerprint'], 'artifact': str(OUT / 'director-ir.json'),
    'artifact_sha256': native['director_sha256'], 'checks': checks, 'complete': True,
    'conflicts': [], 'unresolved': [], 'handoff': handoffs,
    'module_receipt': {'name': 'director-grammar', 'version': '1.4.2',
                       'skill_sha256': reads[0]['sha256'], 'reads': reads},
    'validator': {'status': 'STATIC_VALID', 'errors': [], 'semantic_review': 'REVIEW_ATTESTED',
                  'screenplay_binding': 'REVIEW_ATTESTED', 'media': 'NOT_RUN'}}
role_path = write('role-result.json', role_result)
candidate = {'schema': 'candidate-result/6.0', 'task_id': role_result['task_id'], 'batch': 2,
    'agent_id': '/root/host_bridge/full_rehearsal/v6_55931af0cddf390b43ba149a',
    'input_digest': 'baba5e856c1602d63e4280c1712db8e6e0814a59170f18f0aaa4e3bbfbdd5d28',
    'result_uri': REL + '/role-result.json', 'result_sha256': filehash(role_path),
    'artifacts': [{'slot': 'director:project:project:DirectorIR', 'kind': 'DirectorIR',
                   'uri': REL + '/director-ir.json', 'sha256': native['director_sha256']}],
    'checks': [{k: c[k] for k in ('id', 'status', 'evidence')} for c in checks],
    'handoffs': handoffs,
    'module_receipts': [{'name': 'director-grammar', 'version': '1.4.2', 'sha256': TASK['module']['sha256']}],
    'unresolved': []}
write('candidate-result.json', candidate)
print(json.dumps({'status': 'SUBMITTED_CANDIDATE', 'candidate': REL + '/candidate-result.json',
                  'director_sha256': native['director_sha256'], 'native_status': report['status']}, ensure_ascii=False))
