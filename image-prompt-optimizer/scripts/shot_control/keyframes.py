"""Validate a host-prepared request against immutable package state and real anchors."""
from pathlib import Path
from .common import read, schema_check, sha, digest, confined
from .package import verify_package, recipe
from .media_probe import probe


def check_request(request, package, manifest_path):
    from .control_lowering import validate_delta
    from .repair import invalidated_use
    schema_check(request, 'keyframe-request')
    bundle = verify_package(package)
    original = next((r for r in bundle['requests'] if r['id'] == request['id']), None)
    if original is None: raise ValueError('Unknown keyframe request')
    mutable = {'generation_mode', 'master_anchors', 'base_asset_id', 'edit_delta'}
    if any(request[k] != v for k, v in original.items() if k not in mutable):
        raise ValueError('Keyframe state differs from frozen source')
    manifest_path = Path(manifest_path).resolve()
    manifest = read(manifest_path); schema_check(manifest, 'control-artifacts')
    assets = {a['id']: a for a in manifest['artifacts']}
    if len(assets) != len(manifest['artifacts']): raise ValueError('Duplicate asset ID')
    controls = {c['id']: c for c in bundle['plan']['controls']}
    reasons = []
    if not request['master_anchors']: reasons.append('MASTER_ANCHORS_UNRESOLVED')
    if len(set(request['master_anchors'])) != len(request['master_anchors']): reasons.append('DUPLICATE_MASTER_ANCHOR')
    if request['generation_mode'] == 'UNRESOLVED': reasons.append('GENERATION_MODE_UNRESOLVED')
    if request['camera_state'].get('status') != 'PLANNED_PROJECTION': reasons.append('EXPLICIT_CAMERA_REQUIRED')
    if request['subject_state'].get('status') != 'EXPLICIT': reasons.append('EXPLICIT_POSE_REQUIRED')
    identities, scenes = set(), set()
    source_assets = {a['id']: a for a in bundle['ir']['assets']}
    selected = request['master_anchors']+[request['base_asset_id']] if request['base_asset_id'] else request['master_anchors']
    for ident in selected:
        a = assets.get(ident)
        if not a:
            reasons.append('MISSING_ANCHOR:'+ident); continue
        if a['kind'] != 'image' or a['role'] not in ('identity', 'appearance', 'style', 'scene', 'clean_keyframe'):
            reasons.append('INVALID_ANCHOR_ROLE:'+ident); continue
        if ident in request['master_anchors']:
            roles = {'identity':'identity','appearance':'wardrobe','style':'style','scene':'scene'}
            required_role = roles.get(a['role'])
            refs = [b for b in request['references'] if b['asset_id']==ident and required_role in b['roles']]
            original_asset = source_assets.get(ident)
            if not refs or not original_asset or original_asset['kind'] != 'image' or original_asset['sha256'] != a['sha256'] or original_asset['filename'] != Path(a['path']).name or original_asset['inspection'] != 'observed':
                reasons.append('MASTER_SOURCE_RESPONSIBILITY_UNRESOLVED:'+ident)
            else:
                if required_role=='identity': identities.update(b['target_id'] for b in refs)
                if required_role=='scene': scenes.update(b['target_id'] for b in refs)
        path = confined(manifest_path.parent, a['path'])
        if not path.is_file() or sha(path) != a['sha256']:
            reasons.append('MISSING_OR_CHANGED_ANCHOR:'+ident); continue
        if probe(path)['detected_kind'] != 'image': reasons.append('ANCHOR_MUST_BE_IMAGE:'+ident)
        review = a['review']
        repair_base = (request['generation_mode'] == 'edit' and ident == request['base_asset_id']
                       and ident not in request['master_anchors'] and a['role'] == 'clean_keyframe')
        if review is None or (review['result'] != 'PASS' and not repair_base) or review['sha256'] != a['sha256'] or review['uses_sha256'] != digest(a['uses']):
            reasons.append('ANCHOR_REVIEW_REQUIRED:'+ident)
        uses = [u for u in a['uses'] if u['shot_id'] == request['shot_id']]
        if not uses: reasons.append('ANCHOR_SHOT_SCOPE:'+ident)
        for u in uses:
            shot = next(s for s in bundle['ir']['shots'] if s['id'] == request['shot_id'])
            if not shot['start_ms'] <= u['start_ms'] <= u['end_ms'] <= shot['end_ms']:
                reasons.append('ANCHOR_TIME_SCOPE:'+ident); continue
            if ident in request['master_anchors'] and not u['start_ms'] <= request['at_ms'] <= u['end_ms']:
                reasons.append('ANCHOR_NOT_REVIEWED_FOR_KEYFRAME_TIME:'+ident)
            if invalidated_use(manifest,ident,u): reasons.append('ANCHOR_USE_INVALIDATED:'+ident)
            c = controls.get(u['control_id'])
            if c is None or ident not in c['artifact_ids'] or u['shot_id'] not in c['shot_ids']:
                reasons.append('ANCHOR_RESPONSIBILITY_UNRESOLVED:'+ident); continue
            if u['recipe_sha256'] != recipe(bundle['ir'], bundle['config'], c, u['shot_id'], a['role'], u['start_ms'], u['end_ms']):
                reasons.append('STALE_ANCHOR_RECIPE:'+ident)
    nodes = {n['id']:n for n in bundle['ir']['timeline']['spatial_nodes']}
    people = {e['id'] for e in bundle['ir']['entities'] if e['kind']=='person'}
    visible = set()
    for subject in (request['subject_state'].get('composition') or {}).get('subjects', []):
        if subject['presence']=='outside': continue
        node = nodes[subject['node_id']]
        while not node['entity_id'] and node['parent_id']: node = nodes[node['parent_id']]
        if node['entity_id'] in people: visible.add(node['entity_id'])
    for person in sorted(visible-identities): reasons.append('IDENTITY_MASTER_REQUIRED:'+person)
    scene = next(s['scene_id'] for s in bundle['ir']['shots'] if s['id']==request['shot_id'])
    if scene not in scenes: reasons.append('SCENE_MASTER_REQUIRED:'+scene)
    if request['generation_mode'] == 'edit':
        delta = request['edit_delta']; base = assets.get(request['base_asset_id'])
        if base is None or delta is None:
            reasons.append('EDIT_BASE_AND_DELTA_REQUIRED')
        else:
            validate_delta(delta)
            if delta['keyframe_id'] != request['id'] or delta['source'] != request['source'] or delta['base_asset_sha256'] != base['sha256'] or set(delta['master_anchor_ids']) != set(request['master_anchors']):
                reasons.append('EDIT_DELTA_BINDING_MISMATCH')
    elif request['base_asset_id'] is not None or request['edit_delta'] is not None:
        reasons.append('EDIT_FIELDS_REQUIRE_EDIT_MODE')
    return {'status': 'BLOCKED' if reasons else 'DRAFT_REQUIRES_HOST_REVIEW', 'reasons': sorted(set(reasons)),
            'generated': False, 'visual_review': 'NOT_RUN'}
