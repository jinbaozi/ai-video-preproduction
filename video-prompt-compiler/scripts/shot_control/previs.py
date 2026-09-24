"""Explicit geometry preview. AVIR owns every animated position and direction."""
from fractions import Fraction
from pathlib import Path
import math
import shutil
import subprocess

from .common import read, write, sha, digest, schema_check, confined
from .camera_projection import vector, unit, cross, project
from .control_plan import frame, event_times, shot_view
from .package import verify_package, recipe


def validate_geometry(ir, geometry):
    schema_check(geometry, 'previs-geometry')
    nodes = {n['id']: n for n in ir['timeline']['spatial_nodes']}
    shots = {s['id'] for s in ir['shots']}
    ids = set()
    for obj in geometry['objects']:
        if obj['id'] in ids: raise ValueError('Duplicate proxy object ID')
        ids.add(obj['id'])
        if not set(obj['shot_ids']) <= shots: raise ValueError('Unknown proxy shot')
        refs = [obj['node_id']] + ([obj['end_node_id']] if obj['shape'] == 'bone' else [])
        if any(n not in nodes or nodes[n]['kind'] == 'camera' for n in refs):
            raise ValueError('Unknown or camera geometry node')
        if obj['shape'] == 'bone' and obj['node_id'] == obj['end_node_id']:
            raise ValueError('Bone requires distinct endpoint nodes')
    w, h = geometry['resolution']
    if w % 2 or h % 2: raise ValueError('Video dimensions must be even')


def geometry_for_shot(config, shot_id):
    geometry = config.get('proxy_scene')
    if geometry is None: return None
    return {**geometry, 'objects': [o for o in geometry['objects'] if shot_id in o['shot_ids']]}


def derive(bundle, shot_id, keyframe_id=None):
    """Evaluate all frames before starting Blender; gaps never become interpolation."""
    import spatial_runtime as spatial
    ir, config = bundle['ir'], bundle['config']
    shot = next((s for s in ir['shots'] if s['id'] == shot_id), None)
    if shot is None: raise ValueError('Unknown previs shot')
    geometry = geometry_for_shot(config, shot_id)
    if geometry is None or not geometry['objects']: raise ValueError('Explicit proxy geometry required')
    # JSON Schema integer accepts 24.0 as well as 24; renderer APIs need Python ints.
    geometry = {**geometry, 'fps':int(geometry['fps']), 'resolution':[int(v) for v in geometry['resolution']]}
    fps = geometry['fps']
    start, end = Fraction(str(shot['start_ms'])), Fraction(str(shot['end_ms']))
    if keyframe_id is None:
        frame_count = (end-start)*fps/1000
        if frame_count.denominator != 1: raise ValueError('Shot duration must contain a whole number of frames; no retiming')
        movie_times = [start + Fraction(i*1000, fps) for i in range(frame_count.numerator)]
        event_ms = event_times(ir, shot)
    else:
        request = next((r for r in bundle['requests'] if r['id']==keyframe_id and r['shot_id']==shot_id), None)
        if request is None: raise ValueError('Unknown keyframe in this shot')
        movie_times = []; event_ms = [request['at_ms']]
    all_times = sorted(set(movie_times) | {Fraction(str(t)) for t in event_ms})
    view = shot_view(ir, shot_id)
    nodes = {n['id']: n for n in ir['timeline']['spatial_nodes']}
    required = {x['entity_id'] for x in shot['composition']['required_visible']}
    represented = {nodes[o['node_id']]['entity_id'] for o in geometry['objects']}
    if required-represented: raise ValueError('Visible entities lack proxy geometry: '+str(sorted(required-represented)))
    samples = []
    for at in all_times:
        time = int(at) if at.denominator == 1 else float(at)
        state = frame(ir, shot, time, config['lenses'].get(shot_id, {}))
        camera = state['camera']
        if camera['status'] != 'PLANNED_PROJECTION': raise ValueError(f'Unknown camera at {time} ms')
        unit(cross([0, 1, 0], unit(vector(camera['forward']))))
        w, h = geometry['resolution']
        if abs(w/h-camera['output_aspect']) > 1e-8:
            raise ValueError('Proxy resolution must match camera output aspect including crop')
        if camera['focus']: raise ValueError('Focus tracks require an explicit optical renderer; preview does not model depth of field')
        positions = {p['id']: p['position'] for p in state['points']}
        objects = []
        for obj in geometry['objects']:
            pos = positions[obj['node_id']]
            if pos is None: raise ValueError(f"Unknown position {obj['node_id']} at {time} ms")
            value = {**obj, 'position': [x+y for x,y in zip(vector(pos), obj.get('offset_world', [0,0,0]))]}
            if obj['shape'] == 'bone':
                end = positions[obj['end_node_id']]
                if end is None: raise ValueError(f"Unknown position {obj['end_node_id']} at {time} ms")
                value['end_position'] = vector(end)
                if math.dist(value['position'], end) < 1e-8: raise ValueError('Zero length bone')
            elif obj['orientation'] == 'node_direction':
                direction = spatial.value_at(view, obj['node_id'], 'orientation', time).get('value')
                if nodes[obj['node_id']]['frame']['kind'] != 'world' or not direction or direction['mode'] != 'numeric':
                    raise ValueError(f"Unknown world orientation {obj['node_id']} at {time} ms")
                value['forward'] = unit(vector(direction['value']))
                unit(cross([0,1,0], value['forward']))
            objects.append(value)
        sample = {'at_ms': time, 'camera': {**camera, 'roll_deg': shot['camera'].get('roll_deg', 0),
                  'aspect': config['lenses'][shot_id]['aspect']}, 'objects': objects,
                  'source_points': [{'id': p['id'], 'position': p['position'], 'projection': p['projection']}
                                    for p in state['points'] if p['position'] is not None]}
        samples.append(sample)
    index = {at: i for i,at in enumerate(all_times)}
    plan = {'schema': 'previs-render-plan/0.1', 'shot_id': shot_id, 'source_sha256': bundle['plan']['source']['sha256'],
            'geometry': geometry, 'start_ms': shot['start_ms'], 'end_ms': shot['end_ms'], 'fps': fps,
            'samples': samples, 'video_samples': [index[t] for t in movie_times],
            'event_samples': [index[Fraction(str(t))] for t in event_ms],
            'fidelity': 'EXPLICIT_GEOMETRY_ONLY', 'appearance': 'NEUTRAL_CLAY',
            'limitations': ['No invented gait, anatomy, facial performance or contact solving',
                            'No depth of field, material palette, or production lighting',
                            'Proxy geometry and projection do not prove model compliance']}
    if keyframe_id is not None:
        plan.update(keyframe_id=keyframe_id, render_kind='keyframe', start_ms=request['at_ms'], end_ms=request['at_ms'])
    return plan


def validate_readback(plan, data):
    """Compare Blender's camera projections and evaluated mesh transforms to the plan."""
    if len(data.get('samples', [])) != len(plan['samples']): raise ValueError('Incomplete Blender readback')
    error = 0.0
    for planned, actual in zip(plan['samples'], data['samples']):
        if actual['at_ms'] != planned['at_ms']: raise ValueError('Blender time mapping mismatch')
        if actual['resolution'] != plan['geometry']['resolution']: raise ValueError('Blender resolution mismatch')
        if set(actual['objects']) != {o['id'] for o in planned['objects']}: raise ValueError('Blender geometry mismatch')
        for obj in planned['objects']:
            got = actual['objects'][obj['id']]
            # Every geometric vertex is a real evaluated mesh vertex, not a plan copy.
            if not got['vertices'] or any(not all(math.isfinite(v) for v in p) for p in got['vertices']):
                raise ValueError('Invalid mesh readback')
            center = [(x+y)/2 for x,y in zip(obj['position'],obj['end_position'])] if obj['shape'] == 'bone' else obj['position']
            if math.dist(got['center'], center) > 1e-5: raise ValueError('Blender object position mismatch')
            axes = got['basis_vectors']
            if obj['shape'] == 'bone':
                expected_z = [y-x for x,y in zip(obj['position'],obj['end_position'])]
                if math.dist(axes[2],expected_z) > 1e-5 or any(abs(math.sqrt(sum(v*v for v in axis))-obj['radius']) > 1e-5 for axis in axes[:2]):
                    raise ValueError('Blender bone geometry mismatch')
            else:
                f = obj.get('forward',[0,0,1]); r = unit(cross([0,1,0],f)); u = cross(f,r)
                scale = 2 if obj['shape'] == 'ellipsoid' else 1
                expected_axes = [[v*d/scale for v in axis] for axis,d in zip((r,f,u), (obj['dimensions'][0],obj['dimensions'][2],obj['dimensions'][1]))]
                if any(math.dist(a,b) > 1e-5 for a,b in zip(axes,expected_axes)):
                    raise ValueError('Blender geometry scale or orientation mismatch')
        expected = {p['id']: p for p in planned['source_points'] if p['projection']['xy'] is not None}
        if set(actual['projections']) != set(expected): raise ValueError('Blender projection sample set mismatch')
        for ident, point in expected.items():
            difference = math.dist(actual['projections'][ident], point['projection']['xy'])
            error = max(error, difference)
            if difference > 1e-5: raise ValueError(f'Blender camera projection mismatch: {ident} {difference}')
    return {'status': 'PASS', 'samples': len(plan['samples']), 'max_normalized_projection_error': error}


def _render_plan(plan, out, blender):
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('Output directory must be empty')
    executable = shutil.which(blender)
    if executable is None: raise ValueError('Blender executable unavailable')
    out.mkdir(parents=True, exist_ok=True)
    write(out/'render-plan.json', plan)
    script = Path(__file__).with_name('blender_previs.py')
    command = [executable, '--background', '--factory-startup', '--disable-autoexec', '--threads', '2',
               '--python-exit-code', '1', '--python', str(script), '--', str(out/'render-plan.json'), str(out)]
    with (out/'blender.log').open('w') as log:
        run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    if run.returncode: raise ValueError('Blender rendering failed: '+(out/'blender.log').read_text()[-1800:])
    readback = read(out/'blender-readback.json'); checks = validate_readback(plan, readback)
    return checks, readback, script


def render(package, shot_id, out, blender):
    from .media_probe import probe
    bundle = verify_package(package); plan = derive(bundle, shot_id)
    out = Path(out).resolve()
    checks, readback, script = _render_plan(plan, out, blender)
    (out/'video-frames').mkdir()
    for index, sample_id in enumerate(plan['video_samples']):
        shutil.copyfile(out/f'frames/{sample_id:06d}.png', out/f'video-frames/{index:06d}.png')
    command = ['ffmpeg', '-v', 'error', '-framerate', str(plan['fps']), '-i', str(out/'video-frames/%06d.png'),
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out/'clay.mp4')]
    run = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if run.returncode: raise ValueError('Video encoding failed: '+run.stderr[:500])
    info = probe(out/'clay.mp4')
    if (info['width'], info['height']) != tuple(plan['geometry']['resolution']) or info['duration_ms'] != plan['end_ms']-plan['start_ms'] or info['fps'] != plan['fps']:
        raise ValueError('Rendered media timing or dimensions mismatch')
    artifacts = []
    for control in bundle['config']['controls']:
        if control['channel'] != 'clay_video_reference' or shot_id not in control['shot_ids']: continue
        if len(control['artifact_ids']) != 1: continue  # Multi-asset controls require explicit host registration.
        artifacts.append({'id': control['artifact_ids'][0], 'kind': 'video', 'role': 'clay', 'path': 'clay.mp4',
            'sha256': sha(out/'clay.mp4'), 'source_sha256': plan['source_sha256'], 'review': None, 'binding': None,
            'uses': [{'control_id': control['id'], 'shot_id': shot_id, 'start_ms': plan['start_ms'], 'end_ms': plan['end_ms'],
                      'recipe_sha256': recipe(bundle['ir'], bundle['config'], control, shot_id, 'clay', plan['start_ms'], plan['end_ms'], frames=bundle['frames'])}]})
    # Merge one generated file's responsibilities without duplicate asset IDs.
    merged = {}
    for artifact in artifacts:
        if artifact['id'] in merged: merged[artifact['id']]['uses'].extend(artifact['uses'])
        else: merged[artifact['id']] = artifact
    write(out/'artifact-manifest.json', {'schema': 'control-artifacts/0.2', 'submitted': False, 'artifacts': list(merged.values())})
    receipt = {'schema': 'previs-render-receipt/0.1', 'status': 'RENDERED_LOCAL', 'source_package': str(Path(package).resolve()),
               'source_package_sha256': sha(Path(package)/'package-manifest.json'), 'plan_sha256': digest(plan),
               'renderer_script_sha256': sha(script), 'renderer': readback['renderer'], 'projection_check': checks,
               'media': info, 'scene': 'scene.blend', 'event_frames': [{'at_ms': plan['samples'][i]['at_ms'], 'path': f'frames/{i:06d}.png'} for i in plan['event_samples']],
               'visual_review': 'NOT_RUN', 'model_execution': 'NOT_RUN', 'submitted': False}
    write(out/'render-receipt.json', receipt)
    write(out/'render-manifest.json', {'schema': 'previs-render-manifest/0.1', 'files': {
        p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
    return {'status': 'RENDERED_LOCAL', 'out': str(out), 'frames': len(plan['video_samples']), 'projection_check': checks,
            'visual_review': 'NOT_RUN', 'model_execution': 'NOT_RUN'}


def verify_render(out):
    from .media_probe import probe
    out = Path(out).resolve(); manifest = read(out/'render-manifest.json')
    if manifest.get('schema') != 'previs-render-manifest/0.1': raise ValueError('Invalid render manifest')
    required = {'render-plan.json','render-receipt.json','blender-readback.json','scene.blend','blender.log','clay.mp4','artifact-manifest.json'}
    plan = read(out/'render-plan.json'); receipt = read(out/'render-receipt.json')
    required.update(f'frames/{i:06d}.png' for i in range(len(plan['samples'])))
    required.update(f'video-frames/{i:06d}.png' for i in range(len(plan['video_samples'])))
    if set(manifest['files']) != required: raise ValueError('Incomplete render file set')
    for name, expected in manifest['files'].items():
        if sha(confined(out,name)) != expected: raise ValueError('Rendered file changed: '+name)
    package = Path(receipt['source_package']); bundle = verify_package(package)
    if sha(package/'package-manifest.json') != receipt['source_package_sha256'] or plan != derive(bundle,plan['shot_id']) or digest(plan) != receipt['plan_sha256']:
        raise ValueError('Stale render source or plan')
    checks = validate_readback(plan,read(out/'blender-readback.json'))
    info = probe(out/'clay.mp4')
    if any(info[k] != receipt['media'][k] for k in ('sha256','width','height','duration_ms','fps','detected_kind')):
        raise ValueError('Rendered media receipt mismatch')
    schema_check(read(out/'artifact-manifest.json'), 'control-artifacts')
    return {'status': 'VERIFIED_LOCAL_RENDER', 'projection_check': checks, 'visual_review': 'NOT_RUN', 'model_execution': 'NOT_RUN'}
