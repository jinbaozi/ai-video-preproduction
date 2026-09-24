"""Build self-contained, target-duration prompt files from AVIR 1.2.

The full-project prompt remains an audit draft. A split is only a usable
production draft when its boundary state and every crossing action are known.
"""
from collections import Counter
from functools import lru_cache
from hashlib import sha256
import json


def _seconds(ms):
    return f'{ms / 1000:g}'


def _durations(total, limits):
    maximum = limits['max']
    if maximum is None or maximum <= 0:
        return None, 'DURATION_CAP_UNVERIFIED'
    minimum = limits['min'] if limits['min'] is not None else 1
    allowed = limits['allowed']
    step = limits['step']
    if allowed or step:
        choices = sorted((d for d in (allowed or range(step, maximum + 1, step))
                          if 0 < d and minimum <= d <= maximum and (not step or d % step == 0)), reverse=True)

        @lru_cache(None)
        def solve(remaining):
            if remaining == 0:
                return ()
            best = None
            for duration in choices:
                if duration > remaining:
                    continue
                tail = solve(remaining - duration)
                if tail is None:
                    continue
                candidate = (duration,) + tail
                if best is None or len(candidate) < len(best) or (len(candidate) == len(best) and candidate > best):
                    best = candidate
            return best

        result = solve(total)
        return (list(result), None) if result is not None else (None, 'NO_SUPPORTED_DURATION_PARTITION')

    count = (total + maximum - 1) // maximum
    if count == 0 or total < count * minimum:
        return None, 'NO_SUPPORTED_DURATION_PARTITION'
    result = [maximum] * (count - 1) + [total - maximum * (count - 1)]
    deficit = max(0, minimum - result[-1])
    for index in range(count - 1):
        moved = min(deficit, result[index] - minimum)
        result[index] -= moved
        result[-1] += moved
        deficit -= moved
    return (result, None) if deficit == 0 else (None, 'NO_SUPPORTED_DURATION_PARTITION')


def _boundary_reasons(ir, spatial, start, end):
    reasons = []
    shot_bounds = spatial.bounds(ir)
    for at in (start, end):
        for shot_id, (a, b) in shot_bounds.items():
            if a <= at <= b and spatial.panel_state(ir, shot_id, at)['status'] != 'EXPLICIT':
                reasons.append(f'NEEDS_KEY_POSE:{shot_id}:{at}')
    for collection in ('actions', 'performances', 'camera_operations', 'audio_events', 'motion_tracks'):
        for item in ir['timeline'][collection]:
            if not spatial.overlap((item['start_ms'], item['end_ms']), (start, end)):
                continue
            if collection == 'audio_events' and item['route'] == 'post':
                continue
            if collection == 'camera_operations' and item['operation'] == 'locked':
                continue
            for at in (start, end):
                if item['start_ms'] < at < item['end_ms']:
                    reasons.append(f'NEEDS_EXPLICIT_PHASE_SLICE:{item["id"]}:{at}')
    return reasons


def build(ir, cap, mode, artifact, spatial, render_prompt, verify_prompt, canonical_count, layout):
    """Return a manifest and exact file contents; never submit or truncate."""
    total = ir['output']['duration_ms']
    durations, failure = _durations(total, cap['duration_ms'])
    manifest = {'schema': 'model-prompt-delivery/1.0', 'target': cap['id'], 'mode': mode,
                'project_duration_ms': total, 'max_duration_ms': cap['duration_ms']['max'],
                'status': 'BLOCKED' if failure else 'DRAFT_REQUIRES_TARGET_CHECK',
                'reasons': [failure] if failure else [], 'parts': [], 'execution': 'NOT_RUN'}
    if failure:
        return manifest, {}

    files = {}
    assets = {asset['id']: asset for asset in ir['assets']}
    post = {item['id']: item for item in artifact['post_production']}
    # Full-project duration, reference count and text budget are rechecked per file.
    per_file_checks = {'E_TARGET_DURATION', 'E_REF_LIMIT', 'E_BUDGET'}
    project_blockers = sorted({item['code'] for item in artifact['diagnostics']
                               if item['severity'] in ('error', 'blocker') and item['code'] not in per_file_checks})
    start = 0
    for number, duration in enumerate(durations, 1):
        end = start + duration
        blocks, audit_coverage = spatial.render(ir, start, end)
        prompt, coverage, _, gaps = render_prompt(
            ir, artifact['asset_bindings'], cap['id'], mode, spatial, blocks, audit_coverage,
            start, end, layout=layout)
        reasons = _boundary_reasons(ir, spatial, start, end)
        reasons += [f'PROJECT_BLOCKER:{code}' for code in project_blockers]
        reasons += [f'PROMPT_COVERAGE:{path}' for path in gaps]
        reasons += [f'PROMPT_COVERAGE:{item["path"]}' for item in verify_prompt(ir, prompt, coverage, spatial)]
        refs = []
        active_shots = {shot['id'] for shot in ir['shots']
                        if spatial.overlap(spatial.bounds(ir)[shot['id']], (start, end))}
        for binding in ir['bindings']:
            if not active_shots.intersection(binding['shot_ids']):
                continue
            asset = assets[binding['asset_id']]
            refs.append({'asset_id': asset['id'], 'filename': asset['filename'],
                         'kind': asset['kind'], 'roles': binding['roles'],
                         'target_id': binding['target_id']})
            if asset['filename'] not in prompt:
                reasons.append('REFERENCE_MISSING:' + asset['filename'])
        # Several AVIR asset IDs may point to the same physical reference file.
        reference_files = {}
        for ref in refs:
            asset = assets[ref['asset_id']]
            key = (asset['kind'], asset['path'] or asset['filename'])
            reference_files.setdefault(key, {'filename': asset['filename'], 'kind': asset['kind']})
        counts = Counter(row['kind'] for row in reference_files.values())
        for kind in ('image', 'audio', 'video'):
            limit = cap['max_refs'][kind]
            if limit is not None and counts[kind] > limit:
                reasons.append(f'REFERENCE_LIMIT:{kind}:{counts[kind]}>{limit}')
        limit = cap['max_refs']['total']
        if limit is not None and sum(counts.values()) > limit:
            reasons.append(f'REFERENCE_LIMIT:total:{sum(counts.values())}>{limit}')
        if cap['max_prompt_chars'] is not None and len(prompt) > cap['max_prompt_chars']:
            reasons.append('PROMPT_CHAR_BUDGET_EXCEEDED')
        budget = ir['policy']['max_canonical_units']
        if budget is not None and canonical_count(prompt) > budget:
            reasons.append('PROMPT_CANONICAL_BUDGET_EXCEEDED')
        name = ('BLOCKED-' if reasons else '') + f'prompt-{number:03d}_{start:06d}-{end:06d}ms.txt'
        files[name] = prompt + '\n'
        coverage_name = f'prompt-coverage-{number:03d}_{start:06d}-{end:06d}ms.json'
        files[coverage_name] = json.dumps(coverage, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        relevant_post = [event for event in ir['timeline']['audio_events']
                         if event['route'] == 'post' and
                         spatial.overlap((event['start_ms'], event['end_ms']), (start, end))]
        post_name = None
        if relevant_post:
            post_name = f'post-{number:03d}_{start:06d}-{end:06d}ms.txt'
            lines = [f'项目片段 {_seconds(start)}–{_seconds(end)}秒；以下声音走后期渠道，不当作模型原生对白。']
            for event in relevant_post:
                lines.append(f'项目 {_seconds(event["start_ms"])}–{_seconds(event["end_ms"])}秒，'
                             f'本片段 {_seconds(max(start, event["start_ms"])-start)}–'
                             f'{_seconds(min(end, event["end_ms"])-start)}秒：\n'
                             + post[event['id']]['instruction'])
            files[post_name] = '\n\n'.join(lines) + '\n'
        part = {'number': number, 'project_start_ms': start, 'project_end_ms': end,
                'duration_ms': duration, 'prompt_file': name,
                'prompt_sha256': sha256(files[name].encode('utf-8')).hexdigest(),
                'prompt_coverage_file': coverage_name, 'prompt_coverage_count': len(coverage),
                'references': refs, 'reference_files': list(reference_files.values()),
                'post_file': post_name, 'status': 'BLOCKED' if reasons else 'DRAFT_REQUIRES_TARGET_CHECK',
                'reasons': list(dict.fromkeys(reasons)), 'execution': 'NOT_RUN'}
        manifest['parts'].append(part)
        start = end
    if any(part['status'] == 'BLOCKED' for part in manifest['parts']):
        manifest['status'] = 'BLOCKED'
    return manifest, files
