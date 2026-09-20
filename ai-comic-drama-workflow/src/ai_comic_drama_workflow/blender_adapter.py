"""Local Blender execution with staged output and state read-back evidence."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .spatial import evaluate_state, world_position
from .utils import canonical_json, sha256_bytes, sha256_file


class BlenderUnavailable(ValueError):
    pass


def find_blender():
    candidates = [shutil.which('blender'), '/Applications/Blender.app/Contents/MacOS/Blender']
    return next((str(Path(p)) for p in candidates if p and Path(p).is_file()), None)


def version_probe():
    binary = find_blender()
    if not binary:
        return {'available': False, 'reason': 'Blender not found; no automatic installation'}
    process = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=15)
    version = next((line for line in process.stdout.splitlines() if line.startswith('Blender ')), None)
    return {'available': process.returncode == 0 and bool(version), 'binary': binary, 'version': version,
            'execution_verified': False}


def overview_shot(scene):
    system = scene['coordinate_system']
    bounds = system.get('world_bounds', system['bounds'])
    center = {axis: sum(bounds[axis])/2 for axis in 'xyz'}
    camera = {'full_shot': True, 'position': {**center, 'z': bounds['z'][1] + max(bounds['x'][1]-bounds['x'][0], bounds['y'][1]-bounds['y'][0])},
              'target': {**center, 'z': bounds['z'][0]}, 'up': {'x': 0, 'y': 1, 'z': 0},
              'projection': 'orthographic', 'ortho_scale_m': max(bounds['x'][1]-bounds['x'][0], bounds['y'][1]-bounds['y'][0])*1.3,
              'focal_length_mm': 35, 'sensor_width_mm': 36, 'interpolation': 'hold'}
    return {'shot_id': scene['scene_id'] + '-technical-overview', 'duration_s': 1,
            'camera_track': [camera], 'audio_track': [], 'director_track': [],
            'character_tracks': [{'character_id': actor['character_id'], 'visible_interval': {'start_s': 0, 'end_s': 1},
                                  'trajectory': [{'time_s': 0, 'position': actor['position'], 'rotation_quaternion': actor.get('rotation_quaternion', [1, 0, 0, 0]),
                                                  'pose': 'technical rest proxy', 'facing': actor['facing'], 'gaze': actor['gaze'], 'interpolation': 'hold'}],
                                  'action_events': [], 'emotion_events': []} for actor in scene['character_placements']]}


def render_shot(store, scene, shot, *, folder, fps=24, size=(640, 360), animate=False, key_times=None):
    probe = version_probe()
    if not probe['available']:
        raise BlenderUnavailable(probe.get('reason', 'Blender version probe failed'))
    frame_count = max(1, round(float(shot['duration_s']) * fps))
    if shot.get('timing'):
        from .timing import validate_timing
        shot = validate_timing(shot)
        fps = shot['timing']['fps']
        frame_count = shot['timing']['frame_count']
    times = [n/fps for n in range(frame_count)] if animate else (key_times or [0, float(shot['duration_s'])/2, float(shot['duration_s'])])
    payload = {'fps': fps, 'size': list(size), 'scene_id': scene['scene_id'],
               'frames': [evaluate_state(scene, shot, t, aspect=size[0]/size[1], fps=fps, _timing_checked=True) for t in times],
               'fixed_geometry': [{**item, 'position': world_position(scene, item['position'])}
                                  for item in scene.get('fixed_elements', []) if item.get('size_m')],
               'animate': animate}
    digest = sha256_bytes(canonical_json({'payload': payload, 'version': probe['version'],
                                        'renderer_hash': sha256_file(Path(__file__).with_name('blender_scene.py'))}).encode())
    receipt_path = f'runtime/blender-receipts/{digest}.json'
    if store.exists(receipt_path):
        receipt = store.read(receipt_path)
        if all(store.exists(f['path']) and sha256_file(store.path(f['path'])) == f['sha256'] for f in receipt['files']):
            return receipt
    with tempfile.TemporaryDirectory(prefix='ai-comic-blender-') as temporary:
        root = Path(temporary)
        # Temporary input is also retained by the Kernel as a deterministic derived view.
        input_path = f'runtime/blender-inputs/{digest}.json'
        store.write_text(input_path, canonical_json(payload))
        process = subprocess.run([probe['binary'], '--background', '--factory-startup', '--python',
                                  str(Path(__file__).with_name('blender_scene.py')), '--',
                                  str(store.path(input_path)), str(root)], capture_output=True, text=True, timeout=900)
        store.write_text(f'runtime/blender-logs/{digest}.txt', process.stdout + '\n' + process.stderr)
        if process.returncode or not (root / 'readback.json').exists():
            raise BlenderUnavailable('Blender build/render/read-back failed; no 3D success recorded: ' + (process.stdout + process.stderr)[-4000:])
        readback = json.loads((root / 'readback.json').read_text())
        if len(readback['frames']) != len(times):
            raise ValueError('Blender read-back frame count mismatch')
        for expected, actual in zip(payload['frames'], readback['frames']):
            for entity, observed in zip(expected['characters'], actual['characters']):
                projection = entity['screen_position']
                if any(abs(entity['position'][axis] - observed['position'][i]) > .0001 for i, axis in enumerate('xyz')):
                    raise ValueError('Blender evaluated world position differs from Canonical state')
                if projection['x'] is not None and any(abs(projection[axis]-observed['projection'][i]) > .0001 for i, axis in enumerate('xy')):
                    raise ValueError('Blender camera projection differs from shared evaluator')
        from .pipeline import inspect_image, inspect_video
        files = []
        for source in sorted(root.iterdir()):
            if source.suffix == '.blend1':
                continue
            if source.suffix == '.png' and not inspect_image(source)['verified']:
                raise ValueError('Blender image file failed inspection')
            relative = f'{folder}/{digest[:20]}/{source.name}'
            files.append({'path': relative, 'sha256': store.copy_source(source, relative)})
        video = None
        if animate:
            ffmpeg = shutil.which('ffmpeg')
            if not ffmpeg:
                raise ValueError('FFmpeg required to assemble the rendered motion frames')
            output = root / 'previs.mp4'
            result = subprocess.run([ffmpeg, '-y', '-v', 'error', '-framerate', str(fps), '-i', str(root / '%04d.png'),
                                     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output)], capture_output=True, text=True, timeout=120)
            inspection = inspect_video(output) if result.returncode == 0 else {'verified': False}
            if not inspection['verified']:
                raise ValueError('Rendered motion preview failed file validation')
            relative = f'{folder}/{digest[:20]}/previs.mp4'
            video = {'path': relative, 'sha256': store.copy_source(output, relative), **inspection,
                     'media_kind': 'three-dimensional-motion-previsualization'}
            files.append({'path': relative, 'sha256': video['sha256']})
        receipt = {'source_hash': digest, 'canonical_source_hash': payload['frames'][0]['source_hash'],
                   'engine': probe['version'], 'execution_verified': True,
                   'files': files, 'video': video, 'readback': readback,
                   'boundary': 'Proxy geometry and root/joint targets, not identity renders or final AI video; sampled checks only.'}
        store.write_text(receipt_path, canonical_json(receipt))
        return receipt
