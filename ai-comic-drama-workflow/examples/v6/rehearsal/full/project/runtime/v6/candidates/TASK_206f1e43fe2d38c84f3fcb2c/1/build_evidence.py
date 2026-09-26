import hashlib
import json
from pathlib import Path


ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
REL = 'runtime/v6/candidates/TASK_206f1e43fe2d38c84f3fcb2c/1'
BASE = ROOT / REL
EVIDENCE = BASE / 'evidence'
MODULE_REL = 'runtime/modules/a2cb49a9096ba696e1db059663fcecbb61c3c102c5c10bcd91047704edafe5d4/screenplay-grammar'
SOURCE_REL = 'runtime/v6/candidates/TASK_44ed8445ba9b638fcd7e9fe8/2/canon.json'
FORMAL_REL = 'artifacts/canon/f3c90f6c20dd218a854fa67548b296692d71fd08bc62e2ca5076a27667809b18/native/0cc4aebffda6a714_canon.json'
TASK_REL = 'runtime/tasks/TASK_206f1e43fe2d38c84f3fcb2c.json'
SOURCE_SHA = '0cc4aebffda6a714d5c58695c11f7d70b96359d930125b04edb8fe14abfc4ef9'
FORMAL_SHA = 'ec1a717dc3c8059122916da8f3207437393d9a0cbc4a00cb342dd1b46a94a7a5'
REQ = 'UP_10aaee2a8411c3ed15da2c11'
SOURCE_SLOT = 'canon:project:project:Canon'
TARGET_SLOT = 'screenplay:project:project:ScriptIR'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def pointer(value, path):
    for part in path.split('/')[1:]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


module_files = [
    ('SKILL.md', '04f9f9b6fbb66c097bb9f5c520270d701a8f0bc5d0d00cf0b102f5221db6368e'),
    ('references/contract.md', '20b11441224c6580ed72e95a34a55b974e51f796c03fc1ca6424b7335bc5dfd7'),
    ('references/cooperation.md', '284750ee9f1a18d6647067e08dbcea74fe68e44d259e031cfaaeaa3b4c194e36'),
    ('references/writing.md', '45d2c8ec96d4f6ad686f38e4f7ca798ce5006dd4b66608d6f36c0cc3addc4bef'),
]
reads = []
for rel, expected in module_files:
    path = ROOT / MODULE_REL / rel
    actual = sha(path)
    assert actual == expected, (rel, expected, actual)
    reads.append({'path': str(path), 'sha256': actual})
inputs = [
    (SOURCE_REL, SOURCE_SHA),
    (TASK_REL, '565de82ac95f0f5d62d21cf126c4ae91987d26f329cd3c6fa1d16be6fa0f9523'),
]
input_reads = []
for rel, expected in inputs:
    actual = sha(ROOT / rel)
    assert actual == expected, (rel, expected, actual)
    input_reads.append({'uri': rel, 'sha256': actual})
assert sha(ROOT / FORMAL_REL) == FORMAL_SHA
source = json.loads((ROOT / SOURCE_REL).read_text())
formal = json.loads((ROOT / FORMAL_REL).read_text())
assert source == formal
target = json.loads((BASE / 'script-ir.json').read_text())
target_sha = sha(BASE / 'script-ir.json')
assert target['canon']['ref'] == {'uri': str(ROOT / FORMAL_REL), 'sha256': FORMAL_SHA}
assert target['sources'][1]['sha256'] == FORMAL_SHA
assert target['review']['status'] == 'PASS'
native = json.loads((EVIDENCE / 'native-validator.json').read_text())
assert native == {'errors': [], 'semantic_review': 'REVIEW_ATTESTED', 'status': 'STATIC_VALID'}
compiled = json.loads((EVIDENCE / 'native-compile.json').read_text())
assert compiled['status'] == 'READY' and compiled['media'] == 'NOT_RUN'

module_receipt = {
    'name': 'screenplay-grammar',
    'version': '1.0.2',
    'archive_sha256': 'a2cb49a9096ba696e1db059663fcecbb61c3c102c5c10bcd91047704edafe5d4',
    'skill_sha256': reads[0]['sha256'],
    'reads': reads,
    'frozen_inputs': input_reads,
    'formal_canon': {'uri': FORMAL_REL, 'sha256': FORMAL_SHA, 'json_equal_to_frozen': True},
}
write('module-receipt.json', module_receipt)

mapping = [
    {'source_pointer': '/source_requirements/0', 'target_pointers': ['/contract/clauses/0', '/scenes/0/heading', '/scenes/0/blocks/0/text']},
    {'source_pointer': '/source_requirements/1', 'target_pointers': ['/contract/clauses/1', '/scenes/0/blocks/0/text', '/scenes/0/blocks/1/text', '/scenes/0/blocks/2/text']},
    {'source_pointer': '/source_requirements/2', 'target_pointers': ['/contract/clauses/2', '/narrative/events', '/narrative/reveal_order', '/scenes/0/blocks']},
]
for row in mapping:
    requirement = pointer(source, row['source_pointer'])
    clause = pointer(target, row['target_pointers'][0])
    assert requirement['id'] == clause['id'] and requirement['strength'] == 'hard'
    for path in row['target_pointers']:
        assert pointer(target, path) is not None
source_events = [x['id'] for x in source['event_order']]
target_events = [x['id'] for x in target['narrative']['events']]
assert source_events == target_events == target['narrative']['reveal_order']
assert {x['id'] for x in source['entities'] if x['kind'] == 'character'} == {x['id'] for x in target['characters']}
binding = {
    'channel': 'artifact',
    'requirement_id': REQ,
    'source_slot': SOURCE_SLOT,
    'source_version': 12,
    'target_pointer': '',
    'target_slot': TARGET_SLOT,
}
handoff = {
    **binding,
    'source_uri': SOURCE_REL,
    'source_sha256': SOURCE_SHA,
    'target_uri': f'{REL}/script-ir.json',
    'target_sha256': target_sha,
    'mapping': mapping,
    'finding': '冻结 V6 Canon 的三项硬要求逐项落在 ScriptIR；原生 Canon 引用使用当前正式 V5 字节哈希。',
}
write('handoff.json', handoff)
write('handoff-check.json', {
    'status': 'PASS',
    'binding': binding,
    'source_sha256': SOURCE_SHA,
    'target_sha256': target_sha,
    'registered_canon_uri': FORMAL_REL,
    'registered_canon_sha256': FORMAL_SHA,
    'registered_canon_matches_frozen_content': True,
    'mapping_pointers_exist': True,
    'source_requirement_ids': [x['id'] for x in source['source_requirements']],
    'target_clause_ids': [x['id'] for x in target['contract']['clauses']],
    'source_event_ids': source_events,
    'target_event_ids': target_events,
    'finding': '冻结 Canon 与正式 Canon 的 JSON 内容一致；来源硬要求、角色 ID 和事件顺序可在剧本中逐项定位。',
})
write('semantic-review.json', {
    'status': target['review']['status'],
    'content_sha256': target['review']['content_sha256'],
    'reviewer': target['review']['reviewer'],
    'findings': target['review']['findings'],
    'scope': '创作者当前语义复核；独立专业审阅仍由宿主另派。',
})

result = {
    'schema': 'role-result/5.1',
    'task_id': 'TASK_206f1e43fe2d38c84f3fcb2c',
    'context_fingerprint': '206f1e43fe2d38c84f3fcb2cada6556d365c708dfd641417531f23e23a5f5b1b',
    'artifact': str(BASE / 'script-ir.json'),
    'artifact_sha256': target_sha,
    'complete': True,
    'module_receipt': {
        'name': 'screenplay-grammar',
        'version': '1.0.2',
        'skill_sha256': reads[0]['sha256'],
        'reads': reads,
    },
    'validator': native,
    'checks': [
        {
            'id': 'module_receipt',
            'status': 'PASS',
            'finding': '新锁 Skill 与四份必读资源、冻结 Canon 和冻结 V5 任务字节哈希相符；正式 Canon 字节哈希单独核对。',
            'evidence': [f'{REL}/evidence/module-receipt.json'],
        },
        {
            'id': 'native_validator',
            'status': 'PASS',
            'finding': '锁定原生终验 STATIC_VALID、零错误、当前执行者语义复核已绑定内容指纹；编译包 READY，媒体未运行。',
            'evidence': [f'{REL}/evidence/native-validator.json', f'{REL}/evidence/native-compile.json', f'{REL}/evidence/semantic-review.json'],
        },
        {
            'id': 'handoff',
            'status': 'PASS',
            'finding': '冻结 Canon 的三项硬要求、角色和事件顺序映射到 ScriptIR，并保留正式 Canon 的原生字节哈希。',
            'evidence': [f'{REL}/evidence/handoff.json', f'{REL}/evidence/handoff-check.json'],
        },
    ],
    'handoff': [{
        **binding,
        'evidence': [f'{REL}/evidence/handoff.json', f'{REL}/evidence/handoff-check.json'],
    }],
    'conflicts': [],
    'unresolved': [],
}
(BASE / 'role-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'artifact_sha256': target_sha, 'validator_status': native['status'], 'handoff_status': 'PASS'}, ensure_ascii=False))
