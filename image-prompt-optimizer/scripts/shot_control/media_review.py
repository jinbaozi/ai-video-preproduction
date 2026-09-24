"""Frozen source-derived evaluation baseline; observers provide measurements only."""
import math
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
    from .media_probe import probe
    bundle = verify_package(package); baseline = bundle['evaluation']
    schema_check(review, 'control-media-review')
    if review['evaluation_plan_sha256'] != digest(baseline):
        raise ValueError('Evaluation plan mismatch')
    info = probe(media)
    if info['detected_kind'] != 'video' or info['duration_ms'] is None or not info['width'] or not info['height']:
        raise ValueError('Review requires decodable video')
    if info['sha256'] != review['media_sha256']: raise ValueError('Observed media hash mismatch')
    if info['rotation_deg'] not in (0, 90, 180, 270): raise ValueError('Unsupported display rotation')
    if info['sample_aspect_ratio'] not in (None, 'N/A', '1:1'):
        raise ValueError('Non-square pixels require an explicit display transform')
    width, height = info['display_width'], info['display_height']
    # No implicit retiming, crop or aspect stretch. A different output needs a new explicit plan.
    if abs(info['duration_ms']-baseline['duration_ms']) > max(1, 1000/(info['fps'] or 1)):
        raise ValueError('Media duration differs from frozen time map')
    if any(abs(width/height-a) > 2/max(height, 1) for a in baseline['aspects'].values()):
        raise ValueError('Media aspect differs from frozen projection')
    def key(p): return (p['shot_id'], p['node_id'], p['at_ms'])
    expected = {key(p): p for p in baseline['points']}
    observed = {key(p): p for p in review['observed_points']}
    if len(observed) != len(review['observed_points']) or set(observed)-set(expected):
        raise ValueError('Duplicate or unmatched observation; time warping is not allowed')
    errors, missing, unresolved = [], [], []
    for k, planned in expected.items():
        actual = observed.get(k)
        if k[2] >= info['duration_ms']: raise ValueError('Sample outside video duration')
        if planned['status'] != 'IN_FRAME' or planned['xy'] is None:
            unresolved.append({'shot_id': k[0], 'node_id': k[1], 'at_ms': k[2], 'reason': planned['status']})
            continue
        if actual is None or actual['visibility'] != 'visible' or actual['xy'] is None:
            missing.append({'shot_id': k[0], 'node_id': k[1], 'at_ms': k[2], 'reason': actual['visibility'] if actual else 'missing'})
            continue
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in actual['xy']): raise ValueError('Invalid normalized observation')
        dx, dy = [(a-b)*size for a, b, size in zip(actual['xy'], planned['xy'], (width, height))]
        errors.append({'shot_id': k[0], 'node_id': k[1], 'at_ms': k[2], 'error': math.hypot(dx, dy)/math.hypot(width, height)})
    actual_events = {e['id']: e for e in review['events']}
    if len(actual_events) != len(review['events']) or set(actual_events)-{e['id'] for e in baseline['events']}:
        raise ValueError('Duplicate or unmatched event')
    events = []
    for e in baseline['events']:
        at = actual_events.get(e['id'], {}).get('observed_ms')
        if at is not None and not 0 <= at <= info['duration_ms']: raise ValueError('Event outside video')
        events.append({'id': e['id'], 'error_ms': None if at is None else at-e['planned_ms']})
    for f in review['findings']:
        if not 0 <= f['start_ms'] <= f['end_ms'] <= info['duration_ms']: raise ValueError('Finding outside video')
        for p in f['source_pointers']: pointer(bundle['ir'], p)
    return {'schema': 'control-media-evaluation/0.2', 'media_sha256': info['sha256'],
            'evaluation_plan_sha256': digest(baseline), 'media_probe': info,
            'coverage': len(errors)/len(expected) if expected else 0, 'expected_count': len(expected),
            'missing': missing, 'unresolved': unresolved, 'samples': errors,
            'mean_error': sum(e['error'] for e in errors)/len(errors) if errors else None,
            'max_error': max((e['error'] for e in errors), default=None), 'event_errors': events,
            'findings': review['findings'], 'status': 'OBSERVATIONS_RECORDED', 'world_distance': 'NOT_INFERRED',
            'repairs': [{'owner': f['owner'], 'source_pointers': f['source_pointers'], 'start_ms': f['start_ms'],
                         'end_ms': f['end_ms'], 'issue': f['issue']} for f in review['findings'] if f['result'] == 'FAIL']}
