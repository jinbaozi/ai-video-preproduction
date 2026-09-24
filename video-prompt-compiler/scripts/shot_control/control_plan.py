"""Read-only derivation, event keyframes and three-view review from frozen AVIR."""
from copy import deepcopy
from pathlib import Path
import math
import shutil

from .common import read, write, sha, pointer, schema_check
from .camera_projection import project, sub


def shot_view(ir, shot_id):
    """Restrict tracks at a cut so the preceding endpoint never borrows the next shot."""
    view = deepcopy(ir)
    for collection in ('motion_tracks', 'composition_tracks', 'camera_operations'):
        view['timeline'][collection] = [x for x in view['timeline'][collection] if shot_id in x['shot_ids']]
    return view


def frame(ir, shot, at, lens):
    import spatial_runtime as spatial
    view = shot_view(ir, shot['id'])
    ns = spatial.nodes(view)
    positions = {n: spatial.position_at(view, n, at) for n in ns}
    camera_ids = [n for n in ns if ns[n]['kind'] == 'camera' and positions[n] is not None]
    camera = {'status': 'UNDETERMINED', 'position': None, 'forward': None, 'fov': lens.get('vertical_fov_deg'),
              'intrinsics_basis': lens.get('basis', 'UNRESOLVED'), 'focus': [], 'zoom': []}
    if len(camera_ids) == 1:
        cid = camera_ids[0]; camera['position'] = positions[cid]
        direction = spatial.value_at(view, cid, 'orientation', at)
        value = direction.get('value')
        if value and value['mode'] == 'numeric' and ns[cid]['frame']['kind'] == 'world':
            camera['forward'] = value['value']
        elif not any(t['node_id'] == cid and t['property'] == 'orientation' for t in view['timeline']['motion_tracks']):
            # A static compatibility camera is usable only when explicitly locked.
            ops = [x for x in view['timeline']['camera_operations'] if x['start_ms'] <= at <= x['end_ms']]
            if ops and all(x['operation'] == 'locked' for x in ops) and shot['camera'].get('look_at') is not None:
                camera['forward'] = sub(shot['camera']['look_at'], camera['position'])
        for prop in ('focus', 'zoom'):
            camera[prop] = [spatial.evaluate_track(t, at) for t in view['timeline']['motion_tracks']
                            if t['node_id'] == cid and t['property'] == prop and t['start_ms'] <= at <= t['end_ms']]
        # Unknown zoom units are not silently interpreted as focal length/FOV.
        if camera['zoom']:
            camera['fov'] = None
        if camera['forward'] is not None and camera['fov'] is not None:
            camera['status'] = 'PLANNED_PROJECTION'
    aspect = lens.get('aspect', 16/9)
    points = []
    for nid, pos in positions.items():
        row = {'id': nid, 'label': ns[nid]['label'], 'kind': ns[nid]['kind'], 'position': pos,
               'projection': {'status': 'UNDETERMINED', 'xy': None}}
        if pos is not None and camera['status'] == 'PLANNED_PROJECTION':
            try:
                row['projection'] = project(pos, camera['position'], camera['forward'], camera['fov'], aspect,
                                            shot['camera'].get('roll_deg', 0), lens.get('crop'))
            except ValueError as e:
                row['projection']['reason'] = str(e)
        points.append(row)
    return {'shot_id': shot['id'], 'at_ms': at, 'camera': camera, 'points': points,
            'state': spatial.panel_state(view, shot['id'], at), 'geometry': 'ROOT_POINTS_ONLY',
            'physical_interpolation': False, 'occlusion': 'NOT_EVALUATED'}


def event_times(ir, shot):
    times = {shot['start_ms'], shot['end_ms']}
    for collection in ('actions', 'performances', 'camera_operations', 'composition_tracks'):
        for item in ir['timeline'][collection]:
            if shot['id'] in item['shot_ids']:
                times.update(t for t in (item['start_ms'], item['end_ms']) if shot['start_ms'] <= t <= shot['end_ms'])
    for sample in ir['timeline']['state_samples']:
        if sample['shot_id'] == shot['id']:
            times.add(sample['at_ms'])
    for track in ir['timeline']['motion_tracks']:
        if shot['id'] in track['shot_ids']:
            times.update(k['at_ms'] for k in track['keyframes'] if shot['start_ms'] <= k['at_ms'] <= shot['end_ms'])
    return sorted(times)


def build(source, out, config=None):
    from vpc_core import validate
    source, out = Path(source).resolve(), Path(out).resolve()
    ir = read(source)
    if ir.get('schema') != 'avir/1.2':
        raise ValueError('shot-control requires AVIR 1.2; migrate explicitly')
    errors = validate(ir, source.parent)
    if any(e['severity'] in ('error', 'blocker') for e in errors):
        raise ValueError('Invalid source AVIR: '+str(errors))
    config = config or {'schema': 'shot-control-config/0.1', 'lenses': {}, 'controls': []}
    schema_check(config, 'shot-control-config')
    shot_ids = {s['id'] for s in ir['shots']}
    if set(config['lenses'])-shot_ids:
        raise ValueError('Unknown lens shot')
    for control in config['controls']:
        if not set(control['shot_ids']) <= shot_ids:
            raise ValueError('Unknown control shot')
        for path in control['source_pointers']:
            pointer(ir, path)
    if len({c['id'] for c in config['controls']}) != len(config['controls']):
        raise ValueError('Duplicate control IDs')
    unknown = {c['requirement_id'] for c in config['controls']}-{c['id'] for c in ir['contract']}
    if unknown:
        raise ValueError('Unknown requirement IDs: '+str(unknown))
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty')
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out/'production-specification.json')
    plan = {'schema': 'shot-control/0.1', 'source': {'kind': 'avir/1.2', 'path': 'production-specification.json', 'sha256': sha(source)},
            'shot_ids': list(s['id'] for s in ir['shots']), 'controls': [], 'video_generated': False, 'video_qa': 'NOT_RUN'}
    for control in config['controls']:
        plan['controls'].append({**control, 'status': 'PLANNED'})
    frames, requests = [], []
    for index, shot in enumerate(ir['shots']):
        lens = config['lenses'].get(shot['id'], {})
        events = event_times(ir, shot)
        # Uniform review samples supplement event boundaries; no interpolated poses are invented.
        times = sorted(set(events)|set(range(shot['start_ms'], shot['end_ms'], 100)))
        by_time = {at: frame(ir, shot, at, lens) for at in times}
        frames.extend(by_time.values())
        for at in events:
            state = by_time[at]
            requests.append({'schema': 'keyframe-request/0.1', 'id': f'K{index+1:03d}_{at}',
                'source': plan['source'], 'shot_id': shot['id'], 'at_ms': at,
                'source_pointers': [f'/shots/{index}', '/timeline'], 'camera_state': state['camera'],
                'subject_state': state['state'], 'references': [deepcopy(b) for b in ir['bindings'] if shot['id'] in b['shot_ids']],
                'master_anchors': [], 'generation_mode': 'UNRESOLVED',
                'status': 'DRAFT_REQUIRES_HOST_REVIEW',
                'acceptance': ['保持主身份与场景母版', '核对本时刻姿态、手别、视线和构图', '不得出现箭头、ID、时码或面板'],
                'generated': False, 'visual_review': 'NOT_RUN'})
    write(out/'control-plan.json', plan)
    write(out/'control-config.json', config)
    write(out/'keyframe-requests.json', requests)
    write(out/'review/frames.json', frames)
    from .render_blocking import export_review
    export_review(out, frames)
    coverage = [{'requirement_id': c['id'], 'source_pointers': [x['path'] for x in c['checks']],
                 'control_ids': [r['id'] for r in plan['controls'] if r['requirement_id'] == c['id']],
                 'level': c['level'], 'execution_status': 'PLANNED', 'media_review': 'NOT_RUN'} for c in ir['contract']]
    for request in requests:
        schema_check(request, 'keyframe-request')
    write(out/'control-coverage.json', coverage)
    write(out/'artifact-manifest.json', {'schema': 'control-artifacts/0.1', 'artifacts': [], 'submitted': False})
    write(out/'package-manifest.json', {'schema': 'control-package/0.1', 'files': {
        p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
    return {'status': 'DERIVED', 'out': str(out), 'keyframe_requests': len(requests), 'video_generated': False,
            'execution': 'NOT_RUN', 'projection_unresolved_frames': sum(f['camera']['status'] == 'UNDETERMINED' for f in frames)}
