"""Sampled proxy-space diagnostics, with explicit limits rather than physics claims."""
import math

from .spatial import AXES, evaluate_state, vector, world_position


def _bounds(scene):
    for item in scene.get('fixed_elements', []):
        if not item.get('size_m') or item.get('collision') is False:
            continue
        center = vector(world_position(scene, item['position']))
        size = vector(item['size_m'])
        if any(s <= 0 for s in size):
            raise ValueError('Fixed geometry size must be positive')
        yield item['element_id'], tuple(c-s/2 for c, s in zip(center, size)), tuple(c+s/2 for c, s in zip(center, size))


def _inside(position, low, high):
    return all(a < x < b for x, a, b in zip(position, low, high))


def _blocked(start, end, low, high):
    minimum, maximum = 0.001, 0.999
    for a, b, left, right in zip(start, end, low, high):
        delta = b-a
        if abs(delta) < 1e-10:
            if not left <= a <= right:
                return False
            continue
        near, far = sorted(((left-a)/delta, (right-a)/delta))
        minimum, maximum = max(minimum, near), min(maximum, far)
        if minimum > maximum:
            return False
    return True


def audit_shot(scene, shot, *, fps=24, aspect=16/9):
    if shot.get('timing'):
        from .timing import validate_timing
        shot = validate_timing(shot)
        fps = shot['timing']['fps']
    errors, warnings = [], []
    boxes = list(_bounds(scene))
    tracked_props = {p['asset_id'] for p in shot.get('prop_tracks', [])}
    interaction_props = {p for actor in shot.get('character_tracks', []) for action in actor.get('action_events', []) for p in action.get('prop_ids', [])}
    for prop_id in sorted(interaction_props - tracked_props):
        errors.append({'code': 'missing-prop-interaction-track', 'asset_id': prop_id})
    seen = set()
    prior_holders = {}
    def report(target, code, time_s, **details):
        signature = (code, tuple(sorted((k, str(v)) for k, v in details.items())))
        if signature not in seen:
            target.append({'code': code, 'time_s': time_s, **details})
            seen.add(signature)
    count = math.ceil(shot['duration_s'] * fps)
    for frame_index in range(count + 1):
        t = min(frame_index/fps, shot['duration_s'])
        frame = evaluate_state(scene, shot, t, fps=fps, aspect=aspect, _timing_checked=True)
        camera = vector(frame['camera']['position'])
        actors = {a['character_id']: a for a in frame['characters']}
        for element_id, low, high in boxes:
            if _inside(camera, low, high):
                report(errors, 'camera-inside-fixed-geometry', t, element_id=element_id)
        for actor in actors.values():
            position = vector(actor['position'])
            target = vector(actor.get('joint_targets', {}).get('head', {**actor['position'], 'z': actor['position']['z'] + 1.6}))
            key_action = any(a.get('phase') == 'key' for a in actor['actions'])
            for element_id, low, high in boxes:
                if _inside(position, low, high):
                    report(errors, 'character-inside-fixed-geometry', t, character_id=actor['character_id'], element_id=element_id)
                if actor['visible'] and _blocked(camera, target, low, high):
                    report(errors if key_action else warnings, 'action-occluded' if key_action else 'character-occluded', t,
                           character_id=actor['character_id'], element_id=element_id)
            if key_action and actor['visible'] and not actor['screen_position']['in_frame']:
                report(warnings, 'key-action-root-out-of-frame', t, character_id=actor['character_id'])
        for prop in frame['props']:
            prop_id, holder = prop['asset_id'], prop.get('holder_id')
            if holder and holder not in actors:
                report(errors, 'invalid-prop-holder', t, asset_id=prop_id, holder_id=holder)
            if holder in actors:
                hand = actors[holder].get('joint_targets', {}).get(prop.get('holder_joint', 'right_hand'))
                if hand is None:
                    report(warnings, 'prop-contact-not-verifiable', t, asset_id=prop_id, holder_id=holder)
                elif math.dist(vector(hand), vector(prop['position'])) > .25:
                    report(errors, 'prop-hand-contact-gap', t, asset_id=prop_id, holder_id=holder)
            previous = prior_holders.get(prop_id)
            if previous and holder and holder != previous and prop.get('handoff_from') != previous:
                report(errors, 'untracked-prop-transfer', t, asset_id=prop_id, from_holder=previous, to_holder=holder)
            prior_holders[prop_id] = holder
    return {'passed': not errors, 'errors': errors, 'warnings': warnings, 'samples': count+1, 'fps': fps,
            'boundary': 'Sampled point/AABB and explicit hand-target checks, not mesh collision, anatomical IK or human director approval.'}


def audit_handoff(previous_scene, previous_shot, scene, shot):
    transition = shot.get('continuity', {}).get('transition')
    if not transition:
        return ['Missing explicit shot handoff transition']
    if transition['type'] in {'time_jump', 'scene_change'}:
        return [] if transition.get('reason') and transition.get('approval_ref') else ['Jump/cut needs explicit reason and approval reference']
    if transition['type'] != 'continuous' or previous_scene['scene_id'] != scene['scene_id']:
        return ['Continuous transition cannot change scene coordinate systems']
    before = evaluate_state(previous_scene, previous_shot, previous_shot['duration_s'])
    after = evaluate_state(scene, shot, 0)
    previous = {a['character_id']: a for a in before['characters']}
    issues = []
    for actor in after['characters']:
        if actor['character_id'] in previous and math.dist(vector(actor['position']), vector(previous[actor['character_id']]['position'])) > .02:
            issues.append(f"Unexplained continuous-shot teleport: {actor['character_id']}")
    holders = {p['asset_id']: p.get('holder_id') for p in before['props']}
    for prop in after['props']:
        if prop['asset_id'] in holders and prop.get('holder_id') != holders[prop['asset_id']]:
            issues.append(f"Unexplained cross-shot prop transfer: {prop['asset_id']}")
    return issues
