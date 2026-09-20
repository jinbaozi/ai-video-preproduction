"""Frame-authoritative timing with checked, deterministically derived second views."""
from copy import deepcopy
from fractions import Fraction

TRACK_FIELDS = ('character_tracks', 'camera_track', 'audio_track', 'director_track', 'spatial_track', 'scene_fixed_track', 'prop_tracks')


def _fraction(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


def _frame(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def normalize_timing(shot, *, fps=24):
    result = deepcopy(shot)
    timing = result.get('timing')
    if timing:
        fps = timing['fps']
        duration = Fraction(timing['frame_count'], fps)
        if abs(float(duration) - float(result['duration_s'])) > 1e-9:
            raise ValueError('duration_s is inconsistent with authoritative frame_count')
    else:
        frames = Fraction(str(result['duration_s'])) * fps
        if frames.denominator != 1:
            raise ValueError('Shot duration must be an exact frame count at the selected rate')
        result['timing'] = {'fps': fps, 'frame_count': frames.numerator, 'authority': 'frames',
                            'origin': 'validated-seconds-import'}
    if not isinstance(fps, int) or not 1 <= fps <= 120:
        raise ValueError('Frame rate must be an integer from 1 to 120')
    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for second_key, frame_key in [('time_s', 'at_frame'), ('start_s', 'start_frame'), ('end_s', 'end_frame')]:
                if frame_key in value:
                    seconds = _fraction(value[frame_key]) / fps
                    if second_key in value and abs(float(seconds)-float(value[second_key])) > 1e-9:
                        raise ValueError('Derived seconds conflict with frame time')
                    value[second_key] = float(seconds)
                elif second_key in value:
                    value[frame_key] = _frame(Fraction(str(value[second_key]))*fps)
            for key, child in list(value.items()):
                if key not in {'at_frame', 'start_frame', 'end_frame'}:
                    visit(child)
    for field in TRACK_FIELDS:
        visit(result.get(field, []))
    return result


def validate_timing(shot):
    if 'timing' not in shot:
        raise ValueError('Canonical ShotTimelineSpec needs authoritative frame timing')
    normalized = normalize_timing(shot)
    for field in TRACK_FIELDS:
        if normalized.get(field) != shot.get(field):
            raise ValueError('Canonical timing is incomplete; missing frame keys or derived seconds')
    return normalized
