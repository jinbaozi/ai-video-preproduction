"""One fail-closed verifier for every consumer of a derived control package."""
from pathlib import Path
from .common import read, sha, digest, schema_check, pointer, confined

ROOT = Path(__file__).resolve().parents[2]


def validate_source(ir, base=None):
    import spatial_runtime
    if ir.get('schema') != 'avir/1.2':
        raise ValueError('Requires native AVIR 1.2')
    errors = spatial_runtime.validate(ir, ROOT, 'avir', base)
    if any(e['severity'] in ('error', 'blocker') for e in errors):
        raise ValueError('Invalid native AVIR: '+str(errors))


def validate_config(ir, config):
    schema_check(config, 'shot-control-config')
    shots = {s['id'] for s in ir['shots']}
    if set(config['lenses'])-shots:
        raise ValueError('Unknown lens shot')
    for lens in config['lenses'].values():
        crop = lens.get('crop', [0, 0, 1, 1])
        if min(crop[:2]) < 0 or min(crop[2:]) <= 0 or crop[0]+crop[2] > 1 or crop[1]+crop[3] > 1:
            raise ValueError('Invalid normalized crop')
    clauses = {c['id']: c for c in ir['contract']}
    ids = set()
    for c in config['controls']:
        if c['id'] in ids: raise ValueError('Duplicate control IDs')
        ids.add(c['id'])
        clause = clauses.get(c['requirement_id'])
        if clause is None: raise ValueError('Unknown requirement ID')
        if not set(c['shot_ids']) <= set(clause['shot_ids'] or shots):
            raise ValueError('Control outside requirement shot scope')
        if not set(c['source_pointers']) <= {x['path'] for x in clause['checks']}:
            raise ValueError('Control pointers must name original requirement assertions')
        for path in c['source_pointers']: pointer(ir, path)
        if c['hardness'] != clause['level']: raise ValueError('Control hardness differs from requirement')
        if clause['channel'] != 'prompt':
            raise ValueError('Media cannot discharge a parameter or post-production obligation')
        if c['channel'] == 'deterministic_composite':
            raise ValueError('Post-production requires a post-production obligation, not a media reference')


def verify_package(package):
    package = Path(package).resolve()
    manifest = read(package/'package-manifest.json'); schema_check(manifest, 'control-package')
    ir = read(package/'production-specification.json'); validate_source(ir)
    config = read(package/'control-config.json'); validate_config(ir, config)
    plan = read(package/'control-plan.json'); schema_check(plan, 'shot-control')
    required = {'production-specification.json', 'control-config.json', 'control-plan.json',
                'keyframe-requests.json', 'review/frames.json', 'review/index.html',
                'evaluation-plan.json', 'control-coverage.json', 'artifact-manifest.json'}
    required.update(f'review/blocking-{i+1:03d}.svg' for i in range(len(ir['shots'])))
    if set(manifest['files']) != required:
        raise ValueError('Incomplete or unexpected package file set')
    for name, expected in manifest['files'].items():
        if sha(confined(package, name)) != expected: raise ValueError('Package changed: '+name)
    source = {'kind': 'avir/1.2', 'path': 'production-specification.json',
              'sha256': sha(package/'production-specification.json')}
    if plan['source'] != source or plan['shot_ids'] != [s['id'] for s in ir['shots']]:
        raise ValueError('Plan source or shot scope mismatch')
    if plan['controls'] != [{**c, 'status': 'PLANNED'} for c in config['controls']]:
        raise ValueError('Plan and config controls differ')
    from .control_plan import derive
    frames, requests = derive(ir, config, plan)
    from .media_review import evaluation_plan
    expected = {'review/frames.json': frames, 'keyframe-requests.json': requests,
                'evaluation-plan.json': evaluation_plan(ir, frames),
                'control-coverage.json': [{'requirement_id': c['id'], 'source_pointers': [x['path'] for x in c['checks']],
                    'control_ids': [r['id'] for r in plan['controls'] if r['requirement_id'] == c['id']],
                    'level': c['level'], 'execution_status': 'PLANNED', 'media_review': 'NOT_RUN'} for c in ir['contract']]}
    for name, value in expected.items():
        if read(package/name) != value: raise ValueError('Derived data mismatch: '+name)
    schema_check(read(package/'artifact-manifest.json'), 'control-artifacts')
    return {'ir': ir, 'config': config, 'plan': plan, 'frames': frames, 'requests': requests,
            'evaluation': expected['evaluation-plan.json']}


def recipe(ir, config, control, shot_id, role, start_ms, end_ms):
    """Master references depend on their assertion slices, temporal assets on evaluated shot state."""
    slices = {p: pointer(ir, p) for p in control['source_pointers']}
    value = {'schema': 'control-asset-recipe/0.2', 'role': role, 'slices': slices}
    if role not in ('identity', 'appearance', 'style', 'scene'):
        from .control_plan import frame, event_times
        shot = next(s for s in ir['shots'] if s['id'] == shot_id)
        lens = config['lenses'].get(shot_id, {})
        times = sorted({start_ms, end_ms}|{t for t in event_times(ir, shot) if start_ms <= t <= end_ms})
        timeline = {}
        for name, items in ir['timeline'].items():
            if isinstance(items, list):
                timeline[name] = [x for x in items if not isinstance(x, dict) or
                                  (shot_id in x['shot_ids'] if 'shot_ids' in x else x.get('shot_id', shot_id) == shot_id)]
        value.update(shot=shot, timeline=timeline, entities=ir['entities'],
                     scene=next(x for x in ir['scenes'] if x['id'] == shot['scene_id']),
                     shot_id=shot_id, start_ms=start_ms, end_ms=end_ms, lens=lens,
                     states=[frame(ir, shot, t, lens) for t in times])
    return digest(value)
