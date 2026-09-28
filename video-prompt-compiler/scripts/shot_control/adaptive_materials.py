"""Check selected local controls using existing render verifiers, not declared PASS.

The evidence lives in the native role result/state, not another parallel ledger.
Local renders remain preparation assets; model attachments use existing lowering.
"""
from pathlib import Path

from adaptive_control import POLICY
from .common import read, sha, digest, confined
from .package import verify_package, same_json_value

CRITERIA = {'layout', 'camera', 'scope_limitations'}


def check(package, evidence, base=None, shot_ids=None):
    """Revalidate bytes, source, scope and human/host review for each required render.

    Review records are host assertions, not provider signatures. This function
    does not claim anatomy, actual image observation or model compliance.
    """
    bundle = verify_package(package)
    plan = bundle['plan'].get('adaptive')
    if not plan or plan['policy'] != POLICY:
        raise ValueError('Frozen adaptive policy required')
    if isinstance(evidence, (str, Path)):
        evidence_path = Path(evidence).resolve()
        base = Path(base).resolve() if base else evidence_path.parent
        evidence = read(evidence_path)
    base = Path(base or '.').resolve()
    # Full RoleResult is accepted as the envelope, but each evidence item is closed.
    if not isinstance(evidence, dict): raise ValueError('Evidence envelope required')
    entries = evidence.get('adaptive_evidence', [])
    if not isinstance(entries, list): raise ValueError('Adaptive evidence must be an array')
    selected = set(shot_ids) if shot_ids is not None else {row['shot_id'] for row in plan['shots']}
    if not selected or selected-{row['shot_id'] for row in plan['shots']}:
        raise ValueError('Invalid adaptive material shot scope')
    blockers = [f"{row['shot_id']}:{b['code']}:{b['source_pointer']}"
                for row in plan['shots'] if row['shot_id'] in selected for b in row['blockers']]
    proven, seen = {}, set()
    from .previs import derive, verify_render
    from .previs_frame import verify as verify_frame
    required_by_id = {row['shot_id']:row for row in plan['shots']}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {'shot_id','kind','package','review'}:
            raise ValueError('Unexpected render evidence fields')
        sid, kind = item['shot_id'], item['kind']
        if sid not in required_by_id or kind not in ('proxy_keyframe', 'clay_previs'):
            raise ValueError('Unknown render evidence scope/kind')
        if sid not in selected: continue
        folder = confined(base, item['package'])
        manifest_sha = sha(folder/'render-manifest.json')
        unique = (sid,kind,str(folder))
        if unique in seen: raise ValueError('Duplicate render evidence')
        seen.add(unique)
        if kind == 'clay_previs': verify_render(folder)
        else: verify_frame(folder)
        actual = read(folder/'render-plan.json')
        if actual['shot_id'] != sid: raise ValueError('Render belongs to another shot')
        if kind == 'clay_previs' and actual.get('render_kind') == 'keyframe':
            raise ValueError('A still cannot stand in for continuous previs')
        current = derive(bundle, sid, actual.get('keyframe_id') if kind == 'proxy_keyframe' else None)
        # A change to another shot does not discard a byte-verified, identical render plan.
        portable = lambda value: {k:v for k,v in value.items() if k != 'source_sha256'}
        if not same_json_value(portable(actual), portable(current)):
            raise ValueError('Render no longer matches this shot, geometry or camera')
        review = item['review']
        if not isinstance(review,dict) or set(review) != {'reviewer','render_manifest_sha256','checks'}:
            raise ValueError('Render review fields differ')
        if not isinstance(review['reviewer'],str) or not review['reviewer'].strip() or review['render_manifest_sha256'] != manifest_sha:
            raise ValueError('Render review is missing or stale')
        required_checks = CRITERIA | ({'timing'} if kind == 'clay_previs' else {'key_pose'})
        checks = review['checks']
        if not isinstance(checks,list) or len(checks) != len(required_checks):
            raise ValueError('Incomplete render review')
        names = set()
        for row in checks:
            if (not isinstance(row,dict) or set(row) != {'criterion','result','observation'}
                    or row['criterion'] in names or row['criterion'] not in required_checks
                    or not isinstance(row['observation'],str) or not row['observation'].strip()):
                raise ValueError('Invalid/duplicate render review criterion')
            names.add(row['criterion'])
            if row['result'] not in ('PASS','FAIL','UNDETERMINED'): raise ValueError('Unknown review result')
            if row['result'] != 'PASS': blockers.append(sid+':RENDER_REVIEW_'+row['result'])
        frames = []
        for index in actual['event_samples']:
            sample=actual['samples'][index]
            path = folder/('keyframe.png' if kind=='proxy_keyframe' else f'frames/{index:06d}.png')
            frames.append({'at_ms':sample['at_ms'], 'path':str(path), 'sha256':sha(path)})
        at = actual['start_ms'] if kind == 'proxy_keyframe' else None
        proven.setdefault(sid, []).append({'kind':kind, 'at_ms':at, 'manifest_sha256':manifest_sha, 'frames':frames})
    for row in plan['shots']:
        sid, needs = row['shot_id'], row['required_assets']
        if sid not in selected: continue
        if 'blocking_map' in needs:
            frames = [f for f in bundle['frames'] if f['shot_id'] == sid]
            if not frames or any(f['camera']['status'] != 'PLANNED_PROJECTION' for f in frames):
                blockers.append(sid+':UNRESOLVED_BLOCKING_PROJECTION')
            for frame in frames:
                if row['level']==3 and frame['at_ms'] not in row['critical_times_ms']:continue
                composition=frame['state'].get('composition') or {}
                visible={s['node_id'] for s in composition.get('subjects',[]) if s.get('presence')!='outside'}
                known={p['id'] for p in frame['points'] if p['position'] is not None}
                if visible-known: blockers.append(f'{sid}:UNRESOLVED_VISIBLE_POSITION:{frame["at_ms"]}')
        supplied = proven.get(sid, [])
        if 'clay_previs' in needs and not any(p['kind']=='clay_previs' for p in supplied):
            blockers.append(sid+':MISSING_CLAY_PREVIS')
        if 'proxy_keyframes' in needs:
            # A verified full preview is an admissible superset, not an extra mandatory asset.
            if not any(p['kind']=='clay_previs' for p in supplied):
                times = {p['at_ms'] for p in supplied if p['kind']=='proxy_keyframe'}
                for at in row['critical_times_ms']:
                    if at not in times: blockers.append(f'{sid}:MISSING_PROXY_KEYFRAME:{at}')
    return {'status':'BLOCKED' if blockers else 'CONTROL_MATERIALS_VERIFIED',
            'blockers':blockers, 'evidence_sha256':digest(entries), 'renders':proven,
            'model_execution':'NOT_RUN', 'video_quality':'NOT_RUN'}
