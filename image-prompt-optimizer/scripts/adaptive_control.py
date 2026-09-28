"""Deterministic, shot-scoped routing over native IR; no new content authority.

Call after native validation. Missing semantic facts block, not lower the level.
This module is shared verbatim with the coordinator and image Skill.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math

POLICY = 'adaptive-control/1.0'
CAMERA_MOTION = {'dolly_in', 'dolly_out', 'truck', 'pan', 'tilt', 'pedestal',
                 'orbit', 'tracking', 'handheld'}
OPTICAL = {'zoom', 'rack_focus'}
SPATIAL = {'position', 'orientation', 'rotation', 'deformation', 'extent', 'group_motion'}
CONTACT = {'touching', 'attached_to'}
COLLECTIONS = ('actions', 'camera_operations', 'motion_tracks', 'composition_tracks',
               'spatial_relations', 'state_samples', 'performances')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite native value')
    if isinstance(value, dict):
        for child in value.values(): _finite(child)
    elif isinstance(value, list):
        for child in value: _finite(child)


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Time/coordinate must be a finite number, not a boolean')
    return value


def _bounds(ir, shot):
    if ir.get('schema') == 'avir/1.2':
        start, end = shot['start_ms'], shot['end_ms']
    else:
        fps = _number(ir['delivery']['fps'])
        if fps <= 0: raise ValueError('Invalid frame rate')
        start, end = (float(Fraction(str(_number(shot[k])))*1000/Fraction(str(fps)))
                      for k in ('start_frame', 'end_frame'))
    if not 0 <= _number(start) < _number(end): raise ValueError('Invalid shot range')
    return start, end


def _value(key):
    value = key['value']
    if value['mode'] == 'numeric':
        numeric = value['value']
        for item in numeric if isinstance(numeric, list) else [numeric]: _number(item)
        return ('numeric', numeric, value.get('target_node_id'))
    if value['mode'] == 'relative':
        return ('relative', value.get('target_node_id'), value.get('description'))
    raise ValueError('Unknown motion value mode')


def _moving(track, start, end):
    """Ignore description changes on numeric holds; use only this shot's intervals."""
    keys = track['keyframes']
    if not keys: return None
    times = [_number(k['at_ms']) for k in keys]
    if any(a >= b for a, b in zip(times, times[1:])): raise ValueError('Unordered track keys')
    active = [(a, b) for a, b in zip(keys, keys[1:])
              if a['at_ms'] < end and b['at_ms'] > start]
    # A single explicit held sample may cover an interval in the native evaluator.
    if not active: return False if len(keys) == 1 and keys[0]['transition'] == 'hold' else None
    if any(a['transition'] == 'none' for a, b in active): return None
    return any(_value(a) != _value(b) for a, b in active)


def assess(ir: dict, minimum_levels: dict | None = None) -> dict:
    """Return requirements and source pointers, never fabricated tracks or media PASS.

    L0 static; L1 identity/performance; L2 spatial or optical control;
    L3 contact/occlusion geometry; L4 coupled continuous motion. These are
    decision labels, not weighted quality scores or model-native parameters.
    """
    if not isinstance(ir, dict) or not (ir.get('schema') == 'avir/1.2'
            or ir.get('schema_version') == 'storyboard-ir/1.2'):
        raise ValueError('Adaptive control requires native AVIR/StoryboardIR 1.2')
    _finite(ir)
    timeline = ir['timeline']
    for name in (*COLLECTIONS, 'spatial_nodes'):
        if not isinstance(timeline.get(name), list): raise ValueError('Missing native timeline: '+name)
    shots = ir['shots']
    ids = [shot['id'] for shot in shots]
    if not ids or len(set(ids)) != len(ids): raise ValueError('Empty or duplicate shot scope')
    minimum_levels = {} if minimum_levels is None else minimum_levels
    if not isinstance(minimum_levels, dict) or set(minimum_levels)-set(ids):
        raise ValueError('Unknown minimum-level shot')
    if any(type(v) is not int or not 0 <= v <= 4 for v in minimum_levels.values()):
        raise ValueError('Minimum level must be an integer 0..4, not a boolean')
    nodes = {n['id']: n for n in timeline['spatial_nodes']}
    if len(nodes) != len(timeline['spatial_nodes']): raise ValueError('Duplicate spatial node')
    people = {e['id'] for e in ir['entities'] if e['kind'] == 'person'}
    def owner(nid):
        seen = set()
        while nid:
            if nid not in nodes or nid in seen: raise ValueError('Unknown/cyclic spatial node')
            seen.add(nid); node = nodes[nid]
            if node.get('entity_id'): return node['entity_id']
            nid = node.get('parent_id')
        return None
    rows = []
    for index, shot in enumerate(shots):
        sid = shot['id']; start, end = _bounds(ir, shot)
        scoped = {name: [(i, item) for i, item in enumerate(timeline[name])
                        if sid in item.get('shot_ids', [item.get('shot_id')])]
                  for name in COLLECTIONS}
        reasons, blockers, needs, gaps = [], [], set(), []
        level, critical = 0, {start, end}
        def require(n, code, path, *assets):
            nonlocal level
            level = max(level, n)
            reasons.append({'code': code, 'source_pointer': path})
            needs.update(assets)
        visible = {owner(s['node_id']) for _, c in scoped['composition_tracks']
                   for s in c.get('subjects', []) if s.get('presence') != 'outside'}
        if not scoped['composition_tracks']:
            blockers.append({'code': 'COMPOSITION_UNRESOLVED', 'source_pointer': f'/shots/{index}/composition'})
        if visible & people:
            require(1, 'VISIBLE_IDENTITY', f'/shots/{index}/composition', 'identity_anchor')
        camera_motion = []
        operations = scoped['camera_operations']
        if not operations:
            blockers.append({'code': 'CAMERA_UNRESOLVED', 'source_pointer': f'/shots/{index}/camera'})
        for i, op in operations:
            path = f'/timeline/camera_operations/{i}'
            kind = op['operation']
            if kind == 'unknown': blockers.append({'code': 'CAMERA_UNRESOLVED', 'source_pointer': path})
            elif kind in CAMERA_MOTION:
                require(2, 'CAMERA_MOTION', path, 'blocking_map', 'camera_actor_tracks')
                camera_motion.append((op['start_ms'], op['end_ms']))
            elif kind in OPTICAL:
                require(2, 'OPTICAL_CHANGE', path, 'event_keyframes', 'temporal_focus_review')
            elif kind != 'locked': raise ValueError('Unknown camera operation')
        movers, motion_intervals = set(), []
        for i, track in scoped['motion_tracks']:
            path = f'/timeline/motion_tracks/{i}'
            if track['node_id'] not in nodes: raise ValueError('Unknown track node')
            status = _moving(track, max(start, track['start_ms']), min(end, track['end_ms']))
            prop = track['property']
            if prop in ('focus', 'zoom'):
                if status is not False: require(2, 'FOCUS_TRACK', path, 'event_keyframes', 'temporal_focus_review')
            elif prop in ('light', 'color', 'material', 'atmosphere'):
                require(1, 'LOOK_TRACK', path, 'color_review')
            elif prop in SPATIAL and status is not False:
                require(2, 'SPATIAL_MOTION', path, 'blocking_map', 'camera_actor_tracks')
                if status is True:
                    changed = [(max(start, track['start_ms'], a['at_ms']),
                                min(end, track['end_ms'], b['at_ms']))
                               for a,b in zip(track['keyframes'],track['keyframes'][1:])
                               if max(start,track['start_ms'],a['at_ms']) < min(end,track['end_ms'],b['at_ms'])
                               and _value(a) != _value(b)]
                    if nodes[track['node_id']]['kind'] == 'camera':
                        camera_motion.extend(changed)
                    else:
                        who = owner(track['node_id']); movers.add(who or track['node_id'])
                        motion_intervals.extend((a,b,who) for a,b in changed)
            if status is None and prop in SPATIAL | {'focus', 'zoom'}:
                gaps.append({'code': 'CONTINUOUS_MOTION_UNRESOLVED', 'source_pointer': path})
        contacts, contact_people = [], []
        critical.update(sample['at_ms'] for _, sample in scoped['state_samples'])
        for i, action in scoped['actions']:
            path = f'/timeline/actions/{i}'
            require(1, 'ACTION', path, 'event_keyframes')
            for field in ('path', 'effector', 'contact', 'support'):
                value = action.get(field)
                if not isinstance(value, dict) or value.get('status') == 'unknown':
                    blockers.append({'code': 'ACTION_UNRESOLVED', 'source_pointer': path+'/'+field})
            contact = action.get('contact') or {}
            changes = [x for x in action.get('changes', []) if x['field'] in ('contacts', 'controllers', 'supports')
                       and x.get('before') != x.get('after')]
            if contact.get('status') == 'specified' or changes:
                require(3, 'CONTACT_OR_CUSTODY', path, 'blocking_map', 'camera_actor_tracks', 'proxy_keyframes')
                contacts.append((action['start_ms'], action['end_ms']))
                contact_people.append((action['start_ms'], action['end_ms'],
                                       {action.get('actor_id'), action.get('target_id')} & people))
                critical.update((action['start_ms'], action['end_ms']))
                critical.update(x['at_ms'] for x in changes)
            if any(x['field'] in ('position', 'orientation', 'rotation') and x.get('before') != x.get('after')
                   for x in action.get('changes', [])):
                require(2, 'EXPLICIT_SPATIAL_CHANGE', path+'/changes', 'blocking_map', 'camera_actor_tracks')
            if (action.get('path') or {}).get('status') == 'specified':
                require(2, 'ACTION_PATH', path+'/path', 'blocking_map', 'camera_actor_tracks')
        for i, relation in scoped['spatial_relations']:
            predicate = relation['predicate']; path = f'/timeline/spatial_relations/{i}'
            if predicate in CONTACT | {'occludes'}:
                require(3, 'CONTACT_OR_OCCLUSION', path, 'blocking_map', 'proxy_keyframes')
                scope = relation['scope']
                if predicate in CONTACT and scope.get('kind') == 'interval':
                    contacts.append((scope['start_ms'], scope['end_ms']))
                    contact_people.append((scope['start_ms'], scope['end_ms'],
                        {owner(relation['subject_node_id']), owner(relation['object_node_id'])} & people))
                critical.update(scope[k] for k in ('start_ms', 'end_ms', 'at_ms') if k in scope)
            elif predicate in {'world_left_of', 'world_right_of', 'screen_left_of', 'screen_right_of'}:
                require(2, 'SPATIAL_RELATION', path, 'blocking_map', 'camera_actor_tracks')
        # Coupling, not character count or shot length, justifies a temporal preview.
        overlap = lambda a, b: max(start, a[0], b[0]) < min(end, a[1], b[1])
        if (any(overlap(a,b) for a in camera_motion for b in contacts)
            or any(a[2] in people and b[2] in people and a[2] != b[2]
                   and max(start,c[0],a[0],b[0]) < min(end,c[1],a[1],b[1])
                   for c in camera_motion for i,a in enumerate(motion_intervals) for b in motion_intervals[i+1:])
            or any(a[2] != b[2] and {a[2],b[2]} <= participants
                   and max(start,c0,a[0],b[0]) < min(end,c1,a[1],b[1])
                   for c0,c1,participants in contact_people
                   for i,a in enumerate(motion_intervals) for b in motion_intervals[i+1:])):
            require(4, 'COUPLED_CONTINUOUS_MOTION', f'/shots/{index}', 'clay_previs')
        # No fixed asset count; a full preview already includes its event frames.
        inferred = level; level = max(level, minimum_levels.get(sid, 0))
        if level > inferred: reasons.append({'code':'EXPLICIT_MINIMUM', 'source_pointer': f'/shots/{index}'})
        if level >= 2 and level > inferred: needs.update(('blocking_map', 'camera_actor_tracks'))
        if level >= 3: needs.add('proxy_keyframes')
        if level == 2: blockers.extend(gaps)
        if level >= 4:
            needs.discard('proxy_keyframes'); needs.add('clay_previs')
            blockers.extend(gaps)
        if any(not start <= _number(t) <= end for t in critical):
            # Cross-shot actions are clipped to the current shot; no other shot's endpoints leak.
            critical = {t for t in critical if start <= t <= end}
        # Only referenced nodes and their ancestors belong to this shot's dependency slice.
        used = set()
        def references(value):
            if isinstance(value,dict):
                for child in value.values(): references(child)
            elif isinstance(value,list):
                for child in value: references(child)
            elif isinstance(value,str) and value in nodes: used.add(value)
        references(shot)
        references({name:[x for _,x in scoped[name]] for name in COLLECTIONS})
        pending=list(used)
        while pending:
            node=nodes[pending.pop()]; parent=node.get('parent_id')
            if parent and parent not in used:
                if parent not in nodes: raise ValueError('Unknown parent node')
                used.add(parent);pending.append(parent)
        rows.append({'shot_id': sid, 'level': level, 'inferred_level': inferred,
                     'status': 'BLOCKED' if blockers else 'PLANNED', 'reasons': reasons,
                     'required_assets': sorted(needs), 'critical_times_ms': sorted(critical),
                     'blockers': blockers, 'continuous_motion_gaps': gaps, 'source_fingerprint': digest({'shot': shot, 'timeline':
                         {name:[x for _,x in scoped[name]] for name in COLLECTIONS},
                         'nodes': [n for n in timeline['spatial_nodes'] if n['id'] in used], 'entities':[e for e in ir['entities'] if e['id'] in visible]})})
    return {'policy': POLICY, 'status': 'BLOCKED' if any(r['blockers'] for r in rows) else 'PLANNED',
            'shots': rows, 'control_required': any(r['level'] >= 2 or r['blockers'] for r in rows),
            'generated': False, 'media_review': 'NOT_RUN'}
