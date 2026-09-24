#!/usr/bin/env python3
"""Run pinned VACE frame selection and pixel preprocessing, without model inference.

FFprobe supplies actual decoded frame timestamps and FFmpeg supplies RGB pixels.
This deliberately does not claim to exercise VACE's decord loader or model weights.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()


def run(args):
    import numpy as np
    import torch
    import torchvision

    start = time.monotonic()
    upstream, media, out = map(lambda p: Path(p).resolve(), (args.upstream, args.media, args.out))
    lock = json.loads((ROOT/'upstream-lock.json').read_text())
    head = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if head != lock['commit']:
        raise ValueError('VACE checkout differs from pinned commit')
    for name, expected in lock['files'].items():
        if sha(upstream/name) != expected:
            raise ValueError('VACE source differs from pinned content: '+name)
    if out.exists():
        raise ValueError('Use a new experiment output directory')
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_streams', '-show_frames',
        '-show_entries', 'stream=width,height,avg_frame_rate,duration,sample_aspect_ratio:frame=best_effort_timestamp_time,duration_time',
        '-of', 'json', str(media)]))
    stream = metadata['streams'][0]
    width, height = stream['width'], stream['height']
    timestamps = np.array([[float(f['best_effort_timestamp_time']),
        float(f['best_effort_timestamp_time'])+float(f['duration_time'])] for f in metadata['frames']], dtype=np.float32)
    if not len(timestamps) or np.any(timestamps[:, 1] <= timestamps[:, 0]):
        raise ValueError('Actual frame durations required')
    if stream.get('sample_aspect_ratio') not in (None, 'N/A', '1:1'):
        raise ValueError('Experiment requires square pixels')
    numerator, denominator = map(int, stream['avg_frame_rate'].split('/'))
    fps = numerator/denominator
    module_path = upstream/'vace/models/utils/preprocessor.py'
    spec = importlib.util.spec_from_file_location('pinned_vace_preprocessor', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    processor = module.VaceVideoProcessor(**lock['processor'])
    indices, crop, shape, reported_fps = processor._get_frameid_bbox(
        fps, timestamps, height, width, None, np.random.default_rng(2024))
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(media), '-map', '0:v:0',
        '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'])
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width, 3)
    if len(frames) != len(timestamps):
        raise ValueError('Decode and timestamp frame counts differ')
    x1, x2, y1, y2 = crop
    selected = torch.from_numpy(frames[indices, y1:y2, x1:x2].copy())
    processed = processor._video_preprocess(selected, *shape)
    # Encode the actual transformed tensor for inspection; this is not generated media.
    pixels = ((processed.permute(1, 2, 3, 0).clamp(-1, 1)+1)*127.5).round().byte().numpy()
    out.mkdir(parents=True)
    video = out/'preprocessed-preview.mp4'
    save_fps = lock['inference_save_fps']
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
        '-video_size', f'{shape[1]}x{shape[0]}', '-framerate', str(save_fps), '-i', 'pipe:0',
        '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], input=pixels.tobytes(), check=True)
    output_probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-count_frames', '-show_entries', 'stream=width,height,duration,avg_frame_rate,nb_read_frames', '-of', 'json', str(video)]))['streams'][0]
    mapping = [{'output_frame': i, 'source_frame': int(k), 'source_pts_ms': float(timestamps[k, 0])*1000,
                'saved_pts_ms': i/save_fps*1000} for i, k in enumerate(indices)]
    source_duration = float(stream['duration'])
    output_duration = float(output_probe['duration'])
    reasons = []
    if abs(output_duration-source_duration) > 1/save_fps:
        reasons.append('OUTPUT_DURATION_CHANGED')
    if max(abs(x['saved_pts_ms']-x['source_pts_ms']) for x in mapping) > 1000/save_fps:
        reasons.append('EVENT_TIME_MAP_CHANGED')
    if abs(shape[1]/shape[0]-width/height) > 1e-6:
        reasons.append('CENTER_CROP_CHANGES_PROJECTION')
    report = {'schema':'vace-preprocessing-experiment/0.1', 'status':'BLOCKED' if reasons else 'PREPROCESSING_ONLY',
        'reasons':reasons, 'source_commit':head, 'source_file_sha256':lock['files'],
        'media_sha256':sha(media), 'script_sha256':sha(__file__), 'processor':lock['processor'],
        'input':{'width':width,'height':height,'frames':len(frames),'fps':fps,'duration_seconds':source_duration},
        'output':{**output_probe,'sha256':sha(video),'path':video.name}, 'frame_map':mapping,
        'processor_reported_fps':float(reported_fps), 'inference_save_fps':save_fps,
        'max_timestamp_error_ms':max(abs(x['saved_pts_ms']-x['source_pts_ms']) for x in mapping),
        'runtime':{'torch':torch.__version__,'torchvision':torchvision.__version__,'cuda_available':torch.cuda.is_available(),
                   'mps_available':torch.backends.mps.is_available()},
        'elapsed_seconds':time.monotonic()-start, 'weights_loaded':False,'model_inference':'NOT_RUN',
        'model_quality':'NOT_EVALUATED','generation_cost':None,'submitted':False,
        'limitations':['Official frame selection and pixel transform executed unchanged on CPU',
                       'FFprobe timestamps and FFmpeg decoding substituted for the decord loader; decord not tested',
                       'Preview encoded from the control tensor; not a VACE model result',
                       'No AVIR time map, camera crop or acceptance criteria automatically changed']}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','reasons','max_timestamp_error_ms','model_inference')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream','media','out'):
        parser.add_argument('--'+name, required=True)
    run(parser.parse_args())
