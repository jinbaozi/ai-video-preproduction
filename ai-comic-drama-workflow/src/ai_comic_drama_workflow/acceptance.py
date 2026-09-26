"""Project-level acceptance. Observation status stays OBSERVATIONS_RECORDED."""
import hashlib
import json

REMEDIES = ('换执行通道', '补资产', '调整允许变化的镜头设计', '交由后期完成')


def _sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def verify_plan(plan, frozen_sha256):
    if (not isinstance(plan, dict) or set(plan) != {'schema', 'items', 'sha256'} or
        plan.get('schema') != 'acceptance-plan/1.0' or not isinstance(plan.get('items'), list)):
        raise ValueError('Invalid acceptance plan')
    for item in plan['items']:
        if (not isinstance(item, dict) or set(item) != {'id', 'requirement', 'acceptance',
                'hard', 'checks', 'shot_ids'} or not isinstance(item.get('hard'), bool) or
            not isinstance(item.get('checks'), list) or
            any(not isinstance(check, str) or not check for check in item['checks']) or
            not isinstance(item.get('shot_ids'), list) or
            any(not isinstance(shot, str) or not shot for shot in item['shot_ids']) or
            len(set(item['shot_ids'])) != len(item['shot_ids']) or
            any(item.get(field) is not None and not isinstance(item[field], str)
                for field in ('requirement', 'acceptance'))):
            raise ValueError('Acceptance plan item has invalid fields')
    identifiers = [item.get('id') for item in plan['items']]
    if any(not isinstance(identifier, str) or not identifier for identifier in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError('Acceptance plan has missing or duplicate item IDs')
    actual = _sha(plan['items'])
    if actual != plan.get('sha256') or actual != frozen_sha256:
        raise ValueError('Frozen acceptance plan content differs from its hash')
    return True


def freeze_plan(contract):
    if not isinstance(contract, list) or not contract:
        raise ValueError('Acceptance contract must contain checks')
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
    verify_plan(plan, plan['sha256'])
    return plan


def decide(plan, observations, *, frozen_sha256):
    verify_plan(plan, frozen_sha256)
    if not isinstance(observations, list):
        raise ValueError('Observations must be a list')
    observed_ids = [item.get('id') for item in observations]
    if len(set(observed_ids)) != len(observed_ids):
        raise ValueError('Duplicate observation IDs')
    expected_ids = {item['id'] for item in plan['items']}
    if set(observed_ids) - expected_ids:
        raise ValueError('Observation is outside the frozen acceptance plan')
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
        row = {'id': item['id'], 'result': result, 'hard': item['hard']}
        if observed is not None and observed.get('evidence'):
            row['evidence'] = observed['evidence']
        rows.append(row)
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
    verify_plan(plan, frozen_sha256)
    scoped_items = [i for i in plan['items'] if not i['shot_ids'] or shot_id in i['shot_ids']]
    decision = decide(plan, observations, frozen_sha256=frozen_sha256)
    decision['items'] = [r for r in decision['items'] if r['id'] in {i['id'] for i in scoped_items}]
    hard_fail = any(r['hard'] and r['result'] == 'FAIL' for r in decision['items'])
    undetermined = any(r['result'] == 'UNDETERMINED' for r in decision['items'])
    decision['status'] = 'FAIL' if hard_fail else 'INCOMPLETE' if undetermined or any(r['hard'] and r['result'] != 'PASS' for r in decision['items']) else 'PASS'
    decision['level'] = 'shot'
    decision['shot_id'] = shot_id
    return decision


def adjacent_decision(plan, observations, left_id, right_id, frozen_sha256):
    if left_id == right_id:
        raise ValueError('Adjacent shots must be different')
    decision = shot_decision(plan, observations, left_id, frozen_sha256)
    right = shot_decision(plan, observations, right_id, frozen_sha256)
    by_id = {item['id']: item for item in decision['items']}
    for item in right['items']:
        previous = by_id.get(item['id'])
        if previous and previous != item:
            raise ValueError('Adjacent observations conflict for a shared check')
        by_id[item['id']] = item
    items = list(by_id.values())
    hard_fail = any(r['hard'] and r['result'] == 'FAIL' for r in items)
    undetermined = any(r['result'] == 'UNDETERMINED' for r in items)
    return {
        'level': 'adjacent', 'left': left_id, 'right': right_id, 'items': items,
        'plan_sha256': frozen_sha256,
        'status': 'FAIL' if hard_fail else 'INCOMPLETE' if undetermined else 'PASS',
        'checks': ['手别', '朝向', '道具归属', '台词重复', '情绪延续'],
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
