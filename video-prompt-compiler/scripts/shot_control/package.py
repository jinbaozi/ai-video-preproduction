"""One fail-closed verifier for every consumer of a derived control package."""
from pathlib import Path
from copy import deepcopy
import math
from .common import read, sha, digest, schema_check, pointer, confined

ROOT = Path(__file__).resolve().parents[2]


def projection_frames_match(frozen, derived):
    """Permit libm roundoff only in calculated projection xy/depth, never source/time/status."""
    def scalar(a, b):
        return (type(a) in (int, float) and type(b) in (int, float)
                and math.isfinite(a) and math.isfinite(b)
                and abs(a-b) <= 8*max(math.ulp(a), math.ulp(b)))
    actual = deepcopy(frozen)
    if not isinstance(actual, list) or len(actual) != len(derived): return False
    for a, b in zip(actual, derived):
        if not isinstance(a, dict) or not isinstance(a.get('points'), list) or len(a['points']) != len(b['points']): return False
        for p, q in zip(a['points'], b['points']):
            if not isinstance(p, dict) or not isinstance(p.get('projection'), dict): return False
            x, y = p['projection'], q['projection']
            if 'depth' in y:
                if not scalar(x.get('depth'), y['depth']): return False
                x['depth'] = y['depth']
            if y.get('xy') is not None:
                if not isinstance(x.get('xy'), list) or len(x['xy']) != 2: return False
                if not all(scalar(v, w) for v, w in zip(x['xy'], y['xy'])): return False
                x['xy'] = y['xy']
    return actual == derived


def frozen_values_in_derived_order(frozen, derived):
    # JSON storage sorts keys; the existing HTML renderer uses construction order.
    if isinstance(derived, dict):
        return {k: frozen_values_in_derived_order(frozen[k], v) for k, v in derived.items()}
    if isinstance(derived, list):
        return [frozen_values_in_derived_order(a, b) for a, b in zip(frozen, derived)]
    return frozen


def validate_source(ir, base=None):
    import spatial_runtime
    if ir.get('schema') != 'avir/1.2':
        raise ValueError('Requires native AVIR 1.2')
    errors = spatial_runtime.validate(ir, ROOT, 'avir', base)
    if any(e['severity'] in ('error', 'blocker') for e in errors):
        raise ValueError('Invalid native AVIR: '+str(errors))


def validate_config(ir, config):
    schema_check(config, 'shot-control-config')
    if 'proxy_scene' in config:
        from .previs import validate_geometry
        validate_geometry(ir, config['proxy_scene'])
    if 'look_design' in config:
        from .craft import validate_look
        validate_look(ir, config['look_design'])
    shots = {s['id'] for s in ir['shots']}
    if set(config['lenses'])-shots:
        raise ValueError('Unknown lens shot')
    for lens in config['lenses'].values():
        crop = lens.get('crop', [0, 0, 1, 1])
        if min(crop[:2]) < 0 or min(crop[2:]) <= 0 or crop[0]+crop[2] > 1 or crop[1]+crop[3] > 1:
            raise ValueError('Invalid normalized crop')
        width, height = map(int, ir['output']['aspect_ratio'].split(':'))
        if not math.isclose(lens['aspect']*crop[2]/crop[3], width/height, rel_tol=1e-9):
            raise ValueError('Cropped lens aspect differs from native delivery aspect')
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
        if clause['channel'] not in ('prompt', 'reference'):
            raise ValueError('Media cannot discharge a parameter or post-production obligation')
        if c['channel'] == 'deterministic_composite':
            raise ValueError('Post-production requires a post-production obligation, not a media reference')
        for sid, scope in c.get('reference_scopes', {}).items():
            if c['channel'] != 'image_reference' or sid not in c['shot_ids']:
                raise ValueError('Reference scope requires an owned image-reference shot')
            shot = next(s for s in ir['shots'] if s['id'] == sid)
            if not shot['start_ms'] <= scope['start_ms'] < scope['end_ms'] <= shot['end_ms']:
                raise ValueError('Reference scope is outside its shot')


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
    frozen_frames = read(package/'review/frames.json')
    if not projection_frames_match(frozen_frames, frames):
        raise ValueError('Derived data mismatch: review/frames.json')
    # Keep the byte-verified producer values as the frozen evaluation/recipe basis.
    # Replacing them with host-recomputed floats would silently change existing hashes.
    frames = frozen_values_in_derived_order(frozen_frames, frames)
    from .media_review import evaluation_plan
    expected = {'review/frames.json': frames, 'keyframe-requests.json': requests,
                'evaluation-plan.json': evaluation_plan(ir, frames),
                'control-coverage.json': [{'requirement_id': c['id'], 'source_pointers': [x['path'] for x in c['checks']],
                    'control_ids': [r['id'] for r in plan['controls'] if r['requirement_id'] == c['id']],
                    'level': c['level'], 'execution_status': 'PLANNED', 'media_review': 'NOT_RUN'} for c in ir['contract']]}
    for name, value in expected.items():
        if read(package/name) != value: raise ValueError('Derived data mismatch: '+name)
    from .render_blocking import review_files
    review_html = (package/'review/index.html').read_text(encoding='utf-8')
    layout = 2 if review_html.startswith('<!doctype html><html lang="zh" data-label-layout="2">') else 1
    for name, value in review_files(frames, label_layout=layout).items():
        if (package/name).read_text(encoding='utf-8') != value:
            raise ValueError('Derived review mismatch: '+name)
    schema_check(read(package/'artifact-manifest.json'), 'control-artifacts')
    return {'ir': ir, 'config': config, 'plan': plan, 'frames': frames, 'requests': requests,
            'evaluation': expected['evaluation-plan.json']}


def recipe(ir, config, control, shot_id, role, start_ms, end_ms, *, frames=None):
    """Master references depend on their assertion slices, temporal assets on evaluated shot state."""
    slices = {p: pointer(ir, p) for p in control['source_pointers']}
    value = {'schema': 'control-asset-recipe/0.2', 'role': role, 'slices': slices}
    def state_at(shot, at, lens):
        from .control_plan import frame
        frozen = next((f for f in (frames or []) if f['shot_id'] == shot_id and f['at_ms'] == at), None)
        return frozen if frozen is not None else frame(ir, shot, at, lens)
    if role == 'clean_keyframe' and start_ms == end_ms:
        if shot_id in control.get('reference_scopes', {}):
            value['reference_scope'] = control['reference_scopes'][shot_id]
        shot = next(s for s in ir['shots'] if s['id'] == shot_id)
        state = state_at(shot, start_ms, config['lenses'].get(shot_id, {}))
        # An instantaneous frame consumes the evaluated state, not future action feedback.
        nodes = {n['id']:n for n in ir['timeline']['spatial_nodes']}
        relevant = {p['id'] for p in state['points'] if p['position'] is not None}
        relevant.update(s['node_id'] for s in (state['state'].get('composition') or {}).get('subjects', [])
                        if s['presence'] != 'outside')
        entities = set((state['state'].get('state') or {}).keys())
        for ident in relevant:
            node = nodes[ident]
            while node:
                if node['entity_id']: entities.add(node['entity_id'])
                node = nodes.get(node['parent_id'])
        consumed_entities = [e for e in ir['entities'] if e['id'] in entities]
        scene = next(s for s in ir['scenes'] if s['id'] == shot['scene_id'])
        active_tracks = {v['track_id'] for v in state['state']['motion_values']}
        motion_intent = [{k:v for k,v in t.items() if k not in ('keyframes','start_ms','end_ms')}
                         for t in ir['timeline']['motion_tracks'] if t['id'] in active_tracks]
        for path in slices:
            root = path.split('/')[1]
            if root == 'entities': slices[path] = consumed_entities
            elif root == 'timeline': slices[path] = state['state']
            elif root == 'shots': slices[path] = {'id':shot_id, 'scene_id':shot['scene_id'], 'camera':shot['camera']}
            elif root == 'scenes': slices[path] = scene
        value.update(shot_id=shot_id, at_ms=start_ms, state=state, entities=consumed_entities,
                     scene=scene, motion_intent=motion_intent, lens=config['lenses'].get(shot_id, {}))
        if 'proxy_scene' in config:
            from .previs import geometry_for_shot
            value['proxy_scene'] = geometry_for_shot(config, shot_id)
        if 'look_design' in config:
            from .craft import look_for_shot
            value['look_design'] = look_for_shot(config, shot_id)
        return digest(value)
    if role not in ('identity', 'appearance', 'style', 'scene') or control['channel'] not in ('image_reference', 'keyframe_input'):
        from .control_plan import event_times
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
                     states=[state_at(shot, t, lens) for t in times])
        if 'proxy_scene' in config:
            from .previs import geometry_for_shot
            value['proxy_scene'] = geometry_for_shot(config, shot_id)
        if 'look_design' in config:
            from .craft import look_for_shot
            value['look_design'] = look_for_shot(config, shot_id)
    return digest(value)
