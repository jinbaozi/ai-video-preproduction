"""Frozen source-derived evaluation baseline; observers provide measurements only."""
import math
from fractions import Fraction
from .common import schema_check, digest, pointer


def evaluation_plan(ir, frames):
    # Exclude exact shot end: it is a cut/end boundary, not a decodable frame in that shot.
    ends = {s['id']: s['end_ms'] for s in ir['shots']}
    points = [{'shot_id': f['shot_id'], 'node_id': p['id'], 'at_ms': f['at_ms'],
               'xy': p['projection']['xy'], 'status': p['projection']['status']}
              for f in frames if f['at_ms'] < ends[f['shot_id']]
              for p in f['points'] if p['kind'] != 'camera']
    events = [{'id': kind+':'+e['id']+':'+edge, 'planned_ms': e[edge+'_ms']}
              for kind in ('actions', 'performances', 'camera_operations', 'audio_events')
              for e in ir['timeline'][kind] for edge in ('start', 'end')]
    return {'schema': 'control-evaluation-plan/0.2', 'duration_ms': ir['output']['duration_ms'],
            'time_map': 'identity_milliseconds', 'points': points, 'events': events,
            'aspects': {f['shot_id']: f['camera']['output_aspect'] for f in frames}}


def evaluate(review, package, media):
    from .package import verify_package
    from .media_probe import probe, video_timeline
    bundle = verify_package(package); baseline = bundle['evaluation']
    schema_check(review, 'control-media-review')
    if review['evaluation_plan_sha256'] != digest(baseline):
        raise ValueError('Evaluation plan mismatch')
    scope = review.get('execution_range', {'start_ms': 0, 'end_ms': baseline['duration_ms']})
    start, end = scope['start_ms'], scope['end_ms']
    if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= baseline['duration_ms']:
        raise ValueError('Invalid execution range in frozen project time')
    shot_ids = [s['id'] for s in bundle['ir']['shots'] if s['start_ms'] < end and s['end_ms'] > start]
    info = probe(media)
    if info['detected_kind'] != 'video' or not info['width'] or not info['height']:
        raise ValueError('Review requires decodable video')
    if info['sha256'] != review['media_sha256']: raise ValueError('Observed media hash mismatch')
    if info['rotation_deg'] not in (0, 90, 180, 270): raise ValueError('Unsupported display rotation')
    if info['sample_aspect_ratio'] not in (None, 'N/A', '1:1'):
        raise ValueError('Non-square pixels require an explicit display transform')
    width, height = info['display_width'], info['display_height']
    # No implicit retiming, crop or aspect stretch. A different output needs a new explicit plan.
    timeline = video_timeline(media)
    info['video_timeline'] = timeline
    start_exact, end_exact = Fraction(str(start)), Fraction(str(end))
    video_end = Fraction(timeline['end_ms_exact'])
    if abs(video_end-(end_exact-start_exact)) > 1:
        raise ValueError('Media duration differs from frozen time map')
    if any(abs(width/height-baseline['aspects'][sid]) > 2/max(height, 1) for sid in shot_ids):
        raise ValueError('Media aspect differs from frozen projection')
    def key(p): return (p['shot_id'], p['node_id'], p['at_ms'])
    expected = {key(p): p for p in baseline['points'] if start <= p['at_ms'] < end}
    observed = {key(p): p for p in review['observed_points']}
    if len(observed) != len(review['observed_points']) or set(observed)-set(expected):
        raise ValueError('Duplicate or unmatched observation; time warping is not allowed')
    errors, missing, unresolved = [], [], []
    for k, planned in expected.items():
        actual = observed.get(k)
        if Fraction(str(k[2]))-start_exact >= video_end+1: raise ValueError('Sample outside video duration')
        if planned['status'] != 'IN_FRAME' or planned['xy'] is None:
            unresolved.append({'shot_id': k[0], 'node_id': k[1], 'at_ms': k[2], 'reason': planned['status']})
            continue
        if actual is None or actual['visibility'] != 'visible' or actual['xy'] is None:
            missing.append({'shot_id': k[0], 'node_id': k[1], 'at_ms': k[2], 'reason': actual['visibility'] if actual else 'missing'})
            continue
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in actual['xy']): raise ValueError('Invalid normalized observation')
        dx, dy = [(a-b)*size for a, b, size in zip(actual['xy'], planned['xy'], (width, height))]
        errors.append({'shot_id': k[0], 'node_id': k[1], 'at_ms': k[2], 'error': math.hypot(dx, dy)/math.hypot(width, height)})
    # A cut belongs to the outgoing event's end and incoming event's start,
    # not both neighboring clips. Keep original event IDs and absolute times.
    planned_events = [e for e in baseline['events'] if
                      (start <= e['planned_ms'] < end if e['id'].endswith(':start')
                       else start < e['planned_ms'] <= end)]
    actual_events = {e['id']: e for e in review['events']}
    if len(actual_events) != len(review['events']) or set(actual_events)-{e['id'] for e in planned_events}:
        raise ValueError('Duplicate or unmatched event')
    events = []
    # The decoded endpoint already matches this boundary within 1 ms quantization.
    media_end = end_exact
    for e in planned_events:
        at = actual_events.get(e['id'], {}).get('observed_ms')
        if at is not None and not start_exact <= Fraction(str(at)) <= media_end: raise ValueError('Event outside video')
        events.append({'id': e['id'], 'error_ms': None if at is None else float(Fraction(str(at))-Fraction(str(e['planned_ms'])))})
    for f in review['findings']:
        if not start_exact <= Fraction(str(f['start_ms'])) <= Fraction(str(f['end_ms'])) <= media_end: raise ValueError('Finding outside video')
        for p in f['source_pointers']: pointer(bundle['ir'], p)
    return {'schema': 'control-media-evaluation/0.2', 'media_sha256': info['sha256'],
            'evaluation_plan_sha256': digest(baseline), 'media_probe': info,
            'execution_range': scope, 'media_time_offset_ms': start, 'shot_ids': shot_ids,
            'complete_project_scope': start == 0 and end == baseline['duration_ms'],
            'mapping_evidence': 'OBSERVER_DECLARED_NOT_SUBMISSION_PROOF',
            'project_expected_count': len(baseline['points']),
            'coverage': len(errors)/len(expected) if expected else 0, 'expected_count': len(expected),
            'missing': missing, 'unresolved': unresolved, 'samples': errors,
            'mean_error': sum(e['error'] for e in errors)/len(errors) if errors else None,
            'max_error': max((e['error'] for e in errors), default=None), 'event_errors': events,
            'findings': review['findings'], 'status': 'OBSERVATIONS_RECORDED', 'world_distance': 'NOT_INFERRED',
            'repairs': [{'owner': f['owner'], 'source_pointers': f['source_pointers'], 'start_ms': f['start_ms'],
                         'end_ms': f['end_ms'], 'issue': f['issue']} for f in review['findings'] if f['result'] == 'FAIL']}
