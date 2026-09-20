"""Six-shot, 24-second synthetic director fixture. No human approval is implied."""
from copy import deepcopy
from .test_v3_contracts import physical_fixture
from ai_comic_drama_workflow.timing import normalize_timing


def director_scene():
    scene, template = physical_fixture()
    scene['coordinate_system'].update(units='meters', bounds={'x': [0, 6], 'y': [0, 5], 'z': [0, 3]})
    scene['coordinate_system'].pop('world_bounds', None)
    scene['fixed_elements'] = [
        {'element_id': 'WALL-N', 'position': {'x': 3, 'y': 5, 'z': 1.5}, 'size_m': {'x': 6, 'y': .1, 'z': 3}},
        {'element_id': 'WALL-E', 'position': {'x': 6, 'y': 2.5, 'z': 1.5}, 'size_m': {'x': .1, 'y': 5, 'z': 3}},
    ]
    positions = [{'x': 2.4, 'y': 2.5, 'z': 0}, {'x': 3.2, 'y': 2.5, 'z': 0}]
    for actor, position in zip(scene['character_placements'], positions):
        actor['position'] = position
    left_rest = {'x': 2.65, 'y': 2.35, 'z': 1.0}
    right_rest = {'x': 3.0, 'y': 2.35, 'z': 1.0}
    contact = {'x': 2.8, 'y': 2.5, 'z': 1.2}
    chest = {'x': 3.05, 'y': 2.45, 'z': 1.35}
    scene['prop_placements'] = [{'asset_id': 'ASSET-PROP-001', 'position': left_rest, 'holder_id': 'CHAR-001', 'holder_joint': 'right_hand', 'state': 'sealed'}]
    purposes = ['establish guarded encounter', 'Lin decides to offer sealed letter', 'receiver accepts the letter',
                'Lin releases as receiver secures it', 'Lin reaction confirms relief', 'receiver holds sealed letter; exchange concludes']
    hand_states = [(left_rest, left_rest, right_rest, right_rest),
                   (left_rest, contact, right_rest, right_rest),
                   (contact, contact, right_rest, contact),
                   (contact, left_rest, contact, chest),
                   (left_rest, left_rest, chest, chest),
                   (left_rest, left_rest, chest, chest)]
    shots = []
    for index, (a0, a1, b0, b1) in enumerate(hand_states):
        shot = deepcopy(template)
        shot.update(shot_id=f'SHOT-{index+1:03d}', index=index+1, segment_id=f'SEG-{index+1:03d}', narrative_purpose=purposes[index])
        shot['continuity'] = {'start_state': {'beat': index}, 'end_state': {'beat': index+1},
                              'transition': {'type': 'continuous'}, 'prop_state': 'sealed throughout'}
        for actor_index, track in enumerate(shot['character_tracks']):
            start, end = (a0, a1) if actor_index == 0 else (b0, b1)
            joint = 'right_hand' if actor_index == 0 else 'left_hand'
            first, last = deepcopy(track['trajectory'][0]), deepcopy(track['trajectory'][-1])
            for key, time_s, hand in [(first, 0, start), (last, 4, end)]:
                key.update(time_s=time_s, position=positions[actor_index], pose=purposes[index], joint_targets={joint: hand},
                           gaze='letter', gaze_target_id='ASSET-PROP-001')
            if index == 2 and actor_index == 1:
                middle = {**deepcopy(last), 'time_s': 2}
                track['trajectory'] = [first, middle, last]
            else:
                track['trajectory'] = [first, last]
            track['action_events'] = [{'event_id': f'S{index+1}-C{actor_index+1}', 'start_s': 0, 'end_s': 4,
                'channel': joint, 'phase': 'key' if index == 2 else 'development', 'description': purposes[index],
                'interaction_target': 'CHAR-002' if actor_index == 0 else 'CHAR-001', 'prop_ids': ['ASSET-PROP-001']}]
        holder = 'CHAR-001' if index < 2 else 'CHAR-002'
        prop_start, prop_end = (a0, a1) if index < 2 else (b0, b1)
        if index == 2:
            keys = [{'time_s': 0, 'position': contact, 'holder_id': 'CHAR-001', 'holder_joint': 'right_hand'},
                    {'time_s': 2, 'position': contact, 'holder_id': 'CHAR-002', 'holder_joint': 'left_hand', 'handoff_from': 'CHAR-001'},
                    {'time_s': 4, 'position': contact, 'holder_id': 'CHAR-002', 'holder_joint': 'left_hand'}]
        else:
            keys = [{'time_s': time_s, 'position': position, 'holder_id': holder,
                     'holder_joint': 'right_hand' if holder == 'CHAR-001' else 'left_hand'} for time_s, position in [(0, prop_start), (4, prop_end)]]
        shot['prop_tracks'] = [{'asset_id': 'ASSET-PROP-001', 'trajectory': [{**key, 'state': 'sealed', 'interpolation': 'linear'} for key in keys]}]
        camera = shot['camera_track'][0]
        camera.update(position={'x': 2.8, 'y': -1.5, 'z': 1.8}, target={'x': 2.8, 'y': 2.5, 'z': 1.1}, focal_length_mm=[35, 50, 65, 50, 135, 35][index])
        if index == 4:
            camera['target'] = {'x': 2.4, 'y': 2.5, 'z': 1.55}
            shot['character_tracks'][1]['visible_interval'] = {'start_s': 0, 'end_s': 0}
        shot['audio_track'] = [{'time_mode': 'full_shot', 'kind': 'ambience', 'description': 'quiet room tone'}]
        shot['director_track'] = [{'time_mode': 'full_shot', 'intent': purposes[index]}]
        shot['environment'] = {'location': 'room', 'weather': 'not visible'}
        shot['scene_fixed_track'] = [{'time_mode': 'full_shot', 'fixed_element_ids': ['WALL-N', 'WALL-E']}]
        shots.append(normalize_timing(shot))
    return scene, shots
