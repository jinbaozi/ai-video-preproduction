"""Observed 2D tracking: missing/occluded samples stay in the coverage denominator."""
import math
from .common import schema_check


def evaluate(review):
    schema_check(review, 'control-media-review')
    for p in review['planned_points']+review['observed_points']:
        if p['xy'] is not None and not all(math.isfinite(v) for v in p['xy']):
            raise ValueError('Non-finite observation')
    if any(f['start_ms'] > f['end_ms'] for f in review['findings']):
        raise ValueError('Reversed finding interval')
    expected = {(p['node_id'], p['at_ms']): p for p in review['planned_points']}
    if len(expected) != len(review['planned_points']):
        raise ValueError('Duplicate planned sample')
    observed = {(p['node_id'], p['at_ms']): p for p in review['observed_points']}
    if len(observed) != len(review['observed_points']) or set(observed)-set(expected):
        raise ValueError('Duplicate or unmatched observation; time warping is not allowed')
    errors, missing = [], []
    width, height = review['width'], review['height']
    for key, planned in expected.items():
        actual = observed.get(key)
        if actual is None or actual['visibility'] != 'visible' or actual['xy'] is None:
            missing.append({'node_id': key[0], 'at_ms': key[1], 'reason': actual['visibility'] if actual else 'missing'})
            continue
        dx, dy = [(a-b)*size for a, b, size in zip(actual['xy'], planned['xy'], (width, height))]
        errors.append({'node_id': key[0], 'at_ms': key[1], 'error': math.hypot(dx, dy)/math.hypot(width, height)})
    events = [{'id': e['id'], 'error_ms': None if e['observed_ms'] is None else e['observed_ms']-e['planned_ms']} for e in review['events']]
    return {'schema': 'control-media-evaluation/0.1', 'media_sha256': review['media_sha256'],
            'coverage': len(errors)/len(expected) if expected else 0, 'missing': missing, 'samples': errors,
            'mean_error': sum(e['error'] for e in errors)/len(errors) if errors else None,
            'max_error': max((e['error'] for e in errors), default=None), 'event_errors': events,
            'findings': review['findings'], 'status': 'OBSERVATIONS_RECORDED', 'world_distance': 'NOT_INFERRED',
            'repairs': [{'owner': f['owner'], 'source_pointers': f['source_pointers'], 'start_ms': f['start_ms'],
                         'end_ms': f['end_ms'], 'issue': f['issue']} for f in review['findings'] if f['result'] == 'FAIL']}
