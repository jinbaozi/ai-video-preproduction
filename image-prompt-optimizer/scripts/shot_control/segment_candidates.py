"""Event-based split proposals; existing duration-only delivery remains unchanged."""


def propose(ir, spatial, limits):
    from segment_delivery import _boundary_reasons
    total = ir['output']['duration_ms']
    candidates = {0, total}
    for name in ('actions', 'performances', 'camera_operations', 'composition_tracks'):
        for item in ir['timeline'][name]:
            candidates.update((item['start_ms'], item['end_ms']))
    candidates.update(s['at_ms'] for s in ir['timeline']['state_samples'])
    times = sorted(candidates)
    maximum = limits['max']
    if not maximum:
        return {'status': 'BLOCKED', 'reasons': ['DURATION_CAP_UNVERIFIED'], 'parts': []}
    minimum = limits['min'] or 1
    def legal(duration):
        return minimum <= duration <= maximum and (not limits['allowed'] or duration in limits['allowed']) and (not limits['step'] or duration % limits['step'] == 0)
    best = {0: []}
    for end in times[1:]:
        options = []
        for start in times:
            if start >= end or start not in best or not legal(end-start):
                continue
            reasons = _boundary_reasons(ir, spatial, start, end)
            if not reasons:
                options.append(best[start]+[{'start_ms': start, 'end_ms': end}])
        if options:
            best[end] = min(options, key=lambda parts: (len(parts), tuple(-p['end_ms'] for p in parts)))
    return {'status': 'DRAFT_REQUIRES_TARGET_CHECK' if total in best else 'BLOCKED',
            'reasons': [] if total in best else ['NO_EVENT_PARTITION_WITH_EXPLICIT_STATES'],
            'parts': best.get(total, []), 'candidate_times_ms': times,
            'control_assets': 'REQUIRE_PER_SEGMENT_TIME_MAPPING', 'applied_to_existing_delivery': False}
