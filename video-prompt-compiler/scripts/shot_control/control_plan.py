"""Read-only derivation, event keyframes and three-view review from frozen AVIR."""
from copy import deepcopy
from pathlib import Path
import math
import shutil
import os
import tempfile

from .common import read, write, sha, schema_check
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
            try:
                # Basis validation precedes readiness, even if there are no visible points.
                project(camera['position'], camera['position'], camera['forward'], camera['fov'],
                        lens['aspect'], shot['camera'].get('roll_deg', 0), lens.get('crop'))
                camera['status'] = 'PLANNED_PROJECTION'
            except ValueError as e:
                camera['reason'] = str(e)
    width, height = map(int, ir['output']['aspect_ratio'].split(':'))
    aspect = lens.get('aspect', width/height)
    crop = lens.get('crop', [0, 0, 1, 1])
    camera['output_aspect'] = aspect*crop[2]/crop[3]
    camera['crop'] = crop
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
        if sample['shot_id'] == shot['id'] and shot['start_ms'] <= sample['at_ms'] <= shot['end_ms']:
            times.add(sample['at_ms'])
    for track in ir['timeline']['motion_tracks']:
        if shot['id'] in track['shot_ids']:
            # Track onsets/offsets are events even for relative/held values.
            # This samples declared intent; it does not invent intermediate poses.
            times.update(t for t in (track['start_ms'], track['end_ms'])
                         if shot['start_ms'] <= t <= shot['end_ms'])
            times.update(k['at_ms'] for k in track['keyframes'] if shot['start_ms'] <= k['at_ms'] <= shot['end_ms'])
    return sorted(times)


def keyframe_acceptance(ir, shot, at, config):
    """Read-only, source-scoped review obligations; not model API parameters.

    A still image can validate a focus state, not prove a temporal rack focus.
    Final temporal/color acceptance still requires observations of real media.
    """
    checks = ['保持主身份与场景母版', '核对本时刻姿态、手别、视线和构图', '不得出现箭头、ID、时码或面板']
    focus, color = [], []
    for index, track in enumerate(ir['timeline']['motion_tracks']):
        if shot['id'] not in track['shot_ids'] or not track['start_ms'] <= at <= track['end_ms']:
            continue
        source = f'/timeline/motion_tracks/{index}'
        if track['property'] == 'focus':
            focus.append(source)
        elif track['property'] in ('light', 'color', 'material', 'atmosphere'):
            color.append(source)
    if focus:
        checks += [
            '焦点依据 '+', '.join(focus)+'：核对本时刻主体清晰层次和构图可读性；目标不明则记 UNDETERMINED，不补造焦点对象。',
            '单帧不证明转焦成功；实收视频另验原轨道规定的交接顺序、起止与停留，不以切镜、变焦或换脸替代转焦。',
        ]
    look = config.get('look_design') or {}
    for index, item in enumerate(look.get('material_palette', [])):
        if shot['id'] in item['shot_ids']:
            color.append('control-config.json:/look_design/material_palette/'+str(index))
    for index, item in enumerate(look.get('grading_plan', [])):
        if shot['id'] == item['shot_id']:
            color.append('control-config.json:/look_design/grading_plan/'+str(index))
    if color:
        checks += [
            '光色依据 '+', '.join(color)+'：核对已冻结的光色来源；静态色板不自动产生情绪目标，不能把计划当作实收画面的证据。',
            '分开核对肤色、服装固有色、背景受光；不得用情绪调色改写身份或服装。后期调色仍为 POST_PRODUCTION_NOT_MODEL_PARAMETER，不能用首帧代替成片调色验收。',
        ]
        performances = [f'/timeline/performances/{index}'
                        for index, performance in enumerate(ir['timeline']['performances'])
                        if shot['id'] in performance['shot_ids']
                        and performance['start_ms'] <= at <= performance['end_ms']]
        if performances:
            checks.append('光色与表演依据 '+', '.join(performances)+
                          '：按已冻结的触发与反应核对情绪表达，不额外增加情绪转折；'
                          '没有明确情绪意图时只核对来源，不追加情绪目标，必要依据缺失则记 UNDETERMINED。')
    return checks


def build(source, out, config=None):
    out = Path(out).resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('Output directory must be empty')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.control-build-', dir=out.parent) as temporary:
        staged = Path(temporary)/'package'
        result = _build_into(source, staged, config)
        if out.exists(): out.rmdir()
        os.replace(staged, out)
    return {**result, 'out': str(out)}


def _build_into(source, out, config=None):
    from .package import validate_source, validate_config
    source, out = Path(source).resolve(), Path(out).resolve()
    ir = read(source)
    validate_source(ir, source.parent)
    config = config or {'schema': 'shot-control-config/0.2', 'lenses': {}, 'controls': []}
    validate_config(ir, config)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty')
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out/'production-specification.json')
    plan = {'schema': 'shot-control/0.2', 'source': {'kind': 'avir/1.2', 'path': 'production-specification.json', 'sha256': sha(source)},
            'shot_ids': list(s['id'] for s in ir['shots']), 'controls': [], 'video_generated': False, 'video_qa': 'NOT_RUN'}
    for control in config['controls']:
        plan['controls'].append({**control, 'status': 'PLANNED'})
    frames, requests = derive(ir, config, plan)
    write(out/'control-plan.json', plan)
    write(out/'control-config.json', config)
    write(out/'keyframe-requests.json', requests)
    write(out/'review/frames.json', frames)
    from .media_review import evaluation_plan
    write(out/'evaluation-plan.json', evaluation_plan(ir, frames))
    from .render_blocking import export_review
    export_review(out, frames)
    coverage = [{'requirement_id': c['id'], 'source_pointers': [x['path'] for x in c['checks']],
                 'control_ids': [r['id'] for r in plan['controls'] if r['requirement_id'] == c['id']],
                 'level': c['level'], 'execution_status': 'PLANNED', 'media_review': 'NOT_RUN'} for c in ir['contract']]
    for request in requests:
        schema_check(request, 'keyframe-request')
    write(out/'control-coverage.json', coverage)
    write(out/'artifact-manifest.json', {'schema': 'control-artifacts/0.2', 'artifacts': [], 'submitted': False})
    write(out/'package-manifest.json', {'schema': 'control-package/0.2', 'files': {
        p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
    return {'status': 'DERIVED', 'out': str(out), 'keyframe_requests': len(requests), 'video_generated': False,
            'execution': 'NOT_RUN', 'projection_unresolved_frames': sum(f['camera']['status'] == 'UNDETERMINED' for f in frames)}


def derive(ir, config, plan):
    frames, requests = [], []
    for index, shot in enumerate(ir['shots']):
        lens = config['lenses'].get(shot['id'], {})
        events = event_times(ir, shot)
        # Uniform review samples supplement event boundaries; no interpolated poses are invented.
        count = math.ceil((shot['end_ms']-shot['start_ms'])/100)
        times = sorted(set(events)|{shot['start_ms']+i*100 for i in range(count)})
        by_time = {at: frame(ir, shot, at, lens) for at in times}
        frames.extend(by_time.values())
        for at in events:
            state = by_time[at]
            requests.append({'schema': 'keyframe-request/0.2', 'id': f'K{index+1:03d}_{at}',
                'source': plan['source'], 'shot_id': shot['id'], 'at_ms': at,
                'source_pointers': [f'/shots/{index}', '/timeline'], 'camera_state': state['camera'],
                'subject_state': state['state'], 'references': [deepcopy(b) for b in ir['bindings'] if shot['id'] in b['shot_ids']],
                'master_anchors': [], 'generation_mode': 'UNRESOLVED', 'base_asset_id': None, 'edit_delta': None,
                'status': 'DRAFT_REQUIRES_HOST_REVIEW',
                'acceptance': keyframe_acceptance(ir, shot, at, config),
                'generated': False, 'visual_review': 'NOT_RUN'})
            if 'look_design' in config:
                from .craft import look_for_shot
                requests[-1]['craft_state'] = {
                    'look_design': look_for_shot(config, shot['id']),
                    'lighting_intent': next(s['lighting'] for s in ir['scenes'] if s['id']==shot['scene_id']),
                    'performances': [deepcopy(p) for p in ir['timeline']['performances']
                                     if shot['id'] in p['shot_ids'] and p['start_ms'] <= at <= p['end_ms']],
                    'audio_events': [deepcopy(e) for e in ir['timeline']['audio_events']
                                     if shot['id'] in e['shot_ids'] and e['start_ms'] <= at < e['end_ms']],
                    'grading_execution': 'POST_PRODUCTION_NOT_MODEL_PARAMETER'}
    return frames, requests
