"""Traceable image bindings and the dual-reference delivery gate."""
from copy import deepcopy

from .layout import ASSET_REGISTRY, P09, SCENE_SPACE_PLAN
from .media_bridge import check_reference
from .utils import canonical_json, sha256_bytes


class ReferenceCapacityError(ValueError):
    pass


def current_approval(store, path):
    if not path or not store.exists(path):
        raise ValueError('Required human approval record is absent')
    record = store.read(path)
    if record.get('valid') is False:
        raise ValueError('Required approval has been invalidated')
    from .utils import sha256_file
    for item in record.get('approved_inputs', []):
        if not store.exists(item['path']) or sha256_file(store.path(item['path'])) != item['sha256']:
            raise ValueError('Approval no longer matches current input versions')
    return record


def character_bindings(store, shot, state):
    assets = store.read(ASSET_REGISTRY)['assets']
    bindings = []
    for track in shot.get('character_tracks', []):
        character_id = track['character_id']
        visible = track.get('visible_interval')
        if visible and visible['start_s'] == visible['end_s']:
            continue  # Explicit offscreen world state is not a visible identity requirement.
        if track.get('identity_required', True) is False:
            raise ValueError('Named character tracks cannot bypass identity references; only entity-free shots are exempt')
        candidates = [a for a in assets if a['asset_type'] == 'character-reference'
                      and character_id in a.get('entity_ids', []) and a.get('media_path')
                      and (not shot.get('required_asset_ids') or a['asset_id'] in shot['required_asset_ids'])
                      and (not track.get('identity_asset_id') or a['asset_id'] == track['identity_asset_id'])]
        if not candidates:
            raise ValueError(f'Missing approved character reference: {character_id}')
        if len(candidates) != 1:
            raise ValueError(f'Ambiguous character wardrobe/identity reference: {character_id}; choose identity_asset_id')
        asset = candidates[0]
        binding = {'reference_id': asset['asset_id'], 'role': 'character_identity',
                   'entity_ids': [character_id], 'revision': asset['version'],
                   'path': asset['media_path'], 'sha256': asset['sha256'],
                   'approval_ref': state.get('decision_approvals', {}).get('asset_review_decision'),
                   'allowed_inheritance': ['identity', 'approved wardrobe'],
                   'forbidden_inheritance': ['background', 'composition', 'unrelated pose', *asset.get('forbidden_inheritance', [])]}
        if state.get('decisions', {}).get('asset_review_decision') != 'approve' or not binding['approval_ref']:
            raise ValueError('Character reference needs current human approval')
        check_reference(store, binding)
        current_approval(store, binding['approval_ref'])
        bindings.append(binding)
    return bindings


def dual_bindings(store, shot, state, *, require_storyboard_approval=True):
    bindings = character_bindings(store, shot, state)
    expected = {(b['reference_id'], b['sha256'], b['revision']) for b in bindings}
    boards = store.read(f'{P09}/reference-image-index.json')['references']
    package = store.read(f'{P09}/storyboard-package.json')
    records = [s for s in package['shots'] if s['shot_id'] == shot['shot_id']]
    if len(records) != 1 or records[0].get('timeline_sha256') != sha256_bytes(canonical_json(shot).encode()):
        raise ValueError('Storyboard package does not match the current shot revision')
    moments = {m['moment_id']: m for m in records[0]['key_moments']}
    moment_ids = set(moments)
    scene = next(s for s in store.read(SCENE_SPACE_PLAN)['scenes'] if s['scene_id'] == shot['scene_id'])
    source_hash = sha256_bytes(canonical_json({'scene': scene, 'shot': shot}).encode())
    found = set()
    for board in boards:
        if board['shot_id'] != shot['shot_id']:
            continue
        if not board.get('path') or board.get('image_role') != 'finished_storyboard':
            raise ValueError('Missing finished storyboard; whitebox or prompt cannot satisfy dual references')
        if (board['moment_id'] not in moments or board['moment_id'] in found
                or board['time_s'] != moments[board['moment_id']]['time_s']
                or board.get('evaluated_source_hash') != source_hash):
            raise ValueError('Storyboard image is stale or refers to the wrong key moment; revise storyboard')
        actual = {(b['reference_id'], b['sha256'], b['revision']) for b in board.get('generation_reference_bindings', []) if b['role'] == 'character_identity'}
        if expected != actual:
            raise ValueError('Storyboard was not made with the current character versions; revise storyboard')
        if require_storyboard_approval and state.get('decisions', {}).get('storyboard_review_decision') != 'approve':
            raise ValueError('Storyboard requires current human approval')
        binding = {'reference_id': board['reference_id'], 'role': 'storyboard_frame',
                   'entity_ids': [t['character_id'] for t in shot.get('character_tracks', [])],
                   'revision': board.get('version', 1), 'path': board['path'], 'sha256': board['sha256'],
                   'shot_id': shot['shot_id'], 'time_s': board['time_s'],
                   'approval_ref': state.get('decision_approvals', {}).get('storyboard_review_decision'),
                   'allowed_inheritance': ['composition', 'blocking', 'momentary action and expression'],
                   'forbidden_inheritance': ['freeze the entire shot', 'overwrite approved narrative']}
        if require_storyboard_approval and not binding['approval_ref']:
            raise ValueError('Storyboard approval is absent')
        check_reference(store, binding)
        if require_storyboard_approval:
            current_approval(store, binding['approval_ref'])
        bindings.append(binding)
        found.add(board['moment_id'])
    if not moment_ids or not moment_ids <= found:
        raise ValueError('Required storyboard key moments are missing')
    if len(bindings) > 5:
        raise ReferenceCapacityError('Reference slots exceed five; choose shot/reference changes or pause; no images were dropped')
    return [{**binding, 'slot': index} for index, binding in enumerate(bindings, 1)]


def fact_coverage(shot):
    """Exact serialized controls are part of the executable package, not just a hash."""
    fields = ['narrative_purpose', 'character_tracks', 'camera_track', 'audio_track', 'director_track',
              'spatial_track', 'scene_fixed_track', 'environment', 'lighting', 'continuity', 'negative_constraints']
    if 'prop_tracks' in shot:
        fields.append('prop_tracks')
    if 'timing' in shot:
        fields.append('timing')
    rows = []
    controls = {}
    for field in fields:
        if field not in shot:
            raise ValueError(f'Missing required prompt fact: {field}')
        controls[field] = deepcopy(shot[field])
        rows.append({'source_pointer': '/' + field, 'destination_pointer': '/execution_controls/' + field,
                     'sha256': sha256_bytes(canonical_json(shot[field]).encode()), 'status': 'transferred'})
    return controls, rows


def prompt_controls(store, shot):
    controls, rows = fact_coverage(shot)
    scenes = store.read(SCENE_SPACE_PLAN)['scenes']
    scene_index = next(i for i, scene in enumerate(scenes) if scene['scene_id'] == shot['scene_id'])
    controls['space_context'] = deepcopy(scenes[scene_index])
    rows.append({'source_artifact': SCENE_SPACE_PLAN, 'source_pointer': f'/scenes/{scene_index}',
                 'destination_pointer': '/execution_controls/space_context',
                 'sha256': sha256_bytes(canonical_json(controls['space_context']).encode()), 'status': 'transferred'})
    return controls, rows
