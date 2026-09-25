"""Project-level acceptance. Observation status stays OBSERVATIONS_RECORDED."""
import hashlib
import json

REMEDIES = ('换执行通道', '补资产', '调整允许变化的镜头设计', '交由后期完成')


def _sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def freeze_plan(contract):
    items = []
    for clause in contract:
        items.append({
            'id': clause['id'],
            'requirement': clause.get('requirement'),
            'acceptance': clause.get('acceptance'),
            'hard': clause.get('level') == 'hard',
            'checks': clause.get('checks', []),
            'shot_ids': clause.get('shot_ids') or [],
        })
    plan = {'schema': 'acceptance-plan/1.0', 'items': items}
    plan['sha256'] = _sha(plan['items'])
    return plan


def decide(plan, observations, *, frozen_sha256):
    if plan['sha256'] != frozen_sha256:
        raise ValueError('Frozen acceptance thresholds cannot be relaxed')
    by_id = {item['id']: item for item in observations}
    rows = []
    for item in plan['items']:
        observed = by_id.get(item['id'])
        if observed is None:
            result = 'UNDETERMINED'
        else:
            result = observed['result']
            if result not in ('PASS', 'FAIL', 'UNDETERMINED'):
                raise ValueError('Invalid observation result')
        rows.append({'id': item['id'], 'result': result, 'hard': item['hard']})
    hard_fail = any(r['hard'] and r['result'] == 'FAIL' for r in rows)
    undetermined = any(r['result'] == 'UNDETERMINED' for r in rows)
    if hard_fail:
        status = 'FAIL'
    elif undetermined or any(r['hard'] and r['result'] != 'PASS' for r in rows):
        status = 'INCOMPLETE'
    else:
        status = 'PASS'
    return {'items': rows, 'status': status, 'plan_sha256': frozen_sha256,
            'observation_status': 'OBSERVATIONS_RECORDED'}


def shot_decision(plan, observations, shot_id, frozen_sha256):
    scoped = dict(plan)
    scoped_items = [i for i in plan['items'] if not i['shot_ids'] or shot_id in i['shot_ids']]
    scoped = {'schema': plan['schema'], 'items': scoped_items, 'sha256': plan['sha256']}
    decision = decide(plan, observations, frozen_sha256=frozen_sha256)
    decision['items'] = [r for r in decision['items'] if r['id'] in {i['id'] for i in scoped_items}]
    hard_fail = any(r['hard'] and r['result'] == 'FAIL' for r in decision['items'])
    undetermined = any(r['result'] == 'UNDETERMINED' for r in decision['items'])
    decision['status'] = 'FAIL' if hard_fail else 'INCOMPLETE' if undetermined or any(r['hard'] and r['result'] != 'PASS' for r in decision['items']) else 'PASS'
    decision['level'] = 'shot'
    decision['shot_id'] = shot_id
    return decision


def adjacent_decision(plan, observations, left_id, right_id, frozen_sha256):
    decision = shot_decision(plan, observations, left_id, frozen_sha256)
    right = shot_decision(plan, observations, right_id, frozen_sha256)
    items = decision['items'] + right['items']
    hard_fail = any(r['hard'] and r['result'] == 'FAIL' for r in items)
    undetermined = any(r['result'] == 'UNDETERMINED' for r in items)
    return {
        'level': 'adjacent', 'left': left_id, 'right': right_id, 'items': items,
        'plan_sha256': frozen_sha256,
        'status': 'FAIL' if hard_fail else 'INCOMPLETE' if undetermined else 'PASS',
        'checks': ('手别', '朝向', '道具归属', '台词重复', '情绪延续'),
    }


def sequence_blocks(decisions):
    if any(d['status'] != 'PASS' for d in decisions):
        return ['Sequence requires every shot and adjacent check to pass']
    if any(i['result'] == 'UNDETERMINED' for d in decisions for i in d['items']):
        return ['Undetermined item blocks sequence completion']
    return []


def repair_task(repairs, hypothesis, attempts_used, max_attempts):
    if attempts_used >= max_attempts:
        return {'status': 'BLOCKED_BUDGET', 'hypothesis': hypothesis, 'remedies': list(REMEDIES), 'repairs': repairs}
    return {
        'status': 'OPEN', 'hypothesis': hypothesis, 'repairs': repairs,
        'attempts_remaining': max_attempts - attempts_used,
        'scope': [r.get('owner') for r in repairs],
    }
