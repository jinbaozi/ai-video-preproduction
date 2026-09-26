import hashlib
import json
from pathlib import Path

ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_4de99276d376cc50c61527d6/1'
PRIOR = ROOT / 'runtime/v6/candidates/TASK_f43c3388a29f02af7a8fc90a/1/art-ir.json'
TASK = json.loads((ROOT / 'runtime/tasks/TASK_4de99276d376cc50c61527d6.json').read_text())
VENVELOPE = json.loads((ROOT / 'runtime/v6/state.json').read_text())['tasks'][TASK['task_id']]['envelope']

# The cancelled, unaccepted Art draft is a read-only visual-design source. Its old
# state chain and old bindings are discarded; this task binds and checks the new
# frozen inputs and locked module afresh.
art = json.loads(PRIOR.read_text())
director_v6 = next(x for x in VENVELOPE['inputs'] if x['slot'].startswith('director:'))
canon_v6 = next(x for x in VENVELOPE['inputs'] if x['slot'].startswith('canon:'))
director_path = ROOT / director_v6['uri']
canon_path = ROOT / canon_v6['uri']
assert hashlib.sha256(director_path.read_bytes()).hexdigest() == director_v6['sha256']
assert hashlib.sha256(canon_path.read_bytes()).hexdigest() == canon_v6['sha256']
director = json.loads(director_path.read_text())
canon = json.loads(canon_path.read_text())
assert director['canon_ref'] == str(canon_path)
assert director['project_id'] == canon['project_id'] == art['project_id']
assert [x['id'] for x in director['shots']] == [x['id'] for x in art['shots']]
assert [(a['semantic_id'], a['shot_ids']) for a in director['timeline']['actions']] == [
    ('EVT_HANDOFF', ['S_HANDOFF']),
    ('EVT_SEAL_CHECK', ['S_SEAL']),
    ('EVT_STOW', ['S_STOW']),
]

art['revision'] = 2
art['canon'] = {'uri': str(canon_path), 'revision': str(canon['revision'])}
art['director'] = {
    'uri': str(director_path),
    'sha256': director_v6['sha256'],
    'project_id': director['project_id'],
    'revision': director['revision'],
}
art['sources'][0]['uri'] = str(canon_path)
art['sources'][1]['uri'] = str(director_path)
art['sources'][2]['uri'] = 'local:LETTER_FULL_DEMO/art/SCENE_HANDOFF/revision-2'
art['sources'][2]['claim'] = (
    '旧取消候选只作只读色材与场景设计参考；本批重新核对当前 Canon、DirectorIR 1.2、'
    '锁定 Art 1.3.3 契约并重建离散状态事件。所有美术色材、衣装、平整承托面和参考计划仍为提案。'
)

assets = {a['id']: a for a in art['assets']}
assets['CHAR_YI']['initial_state']['condition'] = '尚未确认封口'
assets['CHAR_YI']['state_rules'] = [{
    'field': 'condition',
    'allowed_values': ['尚未确认封口', '已确认同一封信封口完整'],
}]
assets['PROP_BACKPACK']['initial_state']['condition'] = '待收纳信'
assets['PROP_BACKPACK']['state_rules'] = [{
    'field': 'condition',
    'allowed_values': ['待收纳信', '收纳同一封信'],
}]
assets['PROP_BACKPACK']['identity_locks'] = [
    '同一实体 PROP_BACKPACK 外观与包口位置连续',
    '包口可被乙右手触及；EVENT_STOW 后 condition 为收纳同一封信，信由包内承托且不外露',
]

seal_action = director['timeline']['actions'][1]
stow_action = director['timeline']['actions'][2]
def matched_change(action, entity, field):
    found = [c for c in action['changes'] if c['entity_id'] == entity and c['field'] == field]
    assert len(found) == 1 and isinstance(found[0]['before'], str) and isinstance(found[0]['after'], str)
    return found[0]
seal = matched_change(seal_action, 'CHAR_YI', 'condition')
stow = matched_change(stow_action, 'PROP_BACKPACK', 'condition')
assert seal['before'] == assets['CHAR_YI']['initial_state']['condition']
assert stow['before'] == assets['PROP_BACKPACK']['initial_state']['condition']
art['events'] = [
    {
        'id': 'ART_SEAL_CONFIRMED', 'shot_id': 'S_SEAL', 'order': 0,
        'asset_id': 'CHAR_YI', 'field': 'condition',
        'before': seal['before'], 'after': seal['after'],
        'director_pointer': '/timeline/actions/1',
        'source_refs': ['CANON', 'DIRECTOR'],
        'trigger': '冻结导演 EVENT_SEAL_CHECK 的乙确认封口完整终态；美术只读镜像，不改变演出决定。',
    },
    {
        'id': 'ART_BACKPACK_STOWED', 'shot_id': 'S_STOW', 'order': 0,
        'asset_id': 'PROP_BACKPACK', 'field': 'condition',
        'before': stow['before'], 'after': stow['after'],
        'director_pointer': '/timeline/actions/2',
        'source_refs': ['CANON', 'DIRECTOR'],
        'trigger': '冻结导演 EVENT_STOW 在 8500 毫秒完成；包内承托同一封未拆信。',
    },
]

for clause in art['contract']['clauses']:
    if clause['id'] == 'ART_SEAL':
        clause['paths'] += ['/events/0', '/assets/1/initial_state/condition', '/assets/1/state_rules/0']
        clause['requirement'] += ' 美术状态链在本镜记录乙确认封口完整。'
    elif clause['id'] == 'ART_STOW':
        clause['paths'] += ['/events/1', '/assets/3/initial_state/condition', '/assets/3/state_rules/0']
        clause['requirement'] += ' 美术状态链在本镜记录背包由待收纳转为收纳同一封信。'

# Record precisely where Art can bind native string changes and where the
# director retains contact/control arrays. This is not an invented Art event.
evidence = {
    'prior_cancelled_art_uri': str(PRIOR),
    'prior_cancelled_art_sha256': hashlib.sha256(PRIOR.read_bytes()).hexdigest(),
    'reuse_scope': 'Only previously proposed color, materials, clothing, set, asset cards and shot support were reconsidered as design proposals.',
    'current_canon': {'uri': str(canon_path), 'sha256': canon_v6['sha256']},
    'current_director': {'uri': str(director_path), 'sha256': director_v6['sha256']},
    'director_actions': [
        {'pointer': f'/timeline/actions/{i}', 'id': a['id'], 'semantic_id': a['semantic_id'],
         'shot_ids': a['shot_ids'], 'start_ms': a['start_ms'], 'end_ms': a['end_ms'],
         'state_change_fields': [{'entity_id': c['entity_id'], 'field': c['field'],
                                  'value_types': [type(c['before']).__name__, type(c['after']).__name__]}
                                 for c in a['changes']]}
        for i, a in enumerate(director['timeline']['actions'])
    ],
    'art_events': art['events'],
    'handoff_owner': 'Director retains handoff contacts, supports and controllers; Art preserves S_HANDOFF readability and same-asset identity without mutating those array-valued fields.',
    'media_review': 'NOT_RUN',
}
(OUT/'evidence/action-bindings.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
(OUT/'art-ir.json').write_text(json.dumps(art, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
print(json.dumps({'art_uri': str(OUT/'art-ir.json'), 'art_sha256': hashlib.sha256((OUT/'art-ir.json').read_bytes()).hexdigest(), 'art_events': art['events']}, ensure_ascii=False))
