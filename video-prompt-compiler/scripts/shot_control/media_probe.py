"""Probe actual local media without treating decode success as visual QA."""
from fractions import Fraction
from pathlib import Path
import json
import subprocess
from .common import sha, digest


def video_timeline(path):
    """Decode the selected video stream and retain its original presentation clock."""
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-err_detect', 'explode',
                              '-i', str(path), '-map', '0:v:0', '-fps_mode', 'passthrough', '-f', 'null', '-'],
                             capture_output=True, text=True, timeout=120)
    if decoded.returncode or decoded.stderr.strip():
        raise ValueError('Video decode failed: '+decoded.stderr[:500])
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
                             '-show_entries', 'frame=best_effort_timestamp,duration,pkt_duration:stream=time_base',
                             '-of', 'json', str(path)], capture_output=True, text=True, timeout=120)
    if result.returncode or result.stderr.strip():
        raise ValueError('Video frame probe failed: '+result.stderr[:500])
    data = json.loads(result.stdout)
    try:
        time_base = Fraction(data['streams'][0]['time_base'])
        if time_base <= 0: raise ValueError('Non-positive time base')
    except (KeyError, IndexError, ValueError, ZeroDivisionError):
        raise ValueError('Video time base unavailable') from None
    frames, ticks = [], []
    for frame in data.get('frames', []):
        try:
            pts = frame['best_effort_timestamp']
            length = frame.get('duration', frame.get('pkt_duration'))
            if type(pts) is not int or type(length) is not int: raise ValueError('Non-integer frame clock')
            at, duration = pts*time_base*1000, length*time_base*1000
        except (KeyError, TypeError, ValueError):
            raise ValueError('Video frame timing unavailable') from None
        if duration <= 0:
            raise ValueError('Invalid video frame timing')
        # Permit only millisecond timestamp quantization, not missing intervals or retiming.
        if frames and (at <= frames[-1][0] or abs(at-frames[-1][1]) > 1):
            raise ValueError('Video frame timeline has gaps or overlaps')
        frames.append([at, at+duration])
        ticks.append([pts, length])
    if not frames:
        raise ValueError('Video contains no decoded frames')
    if abs(frames[0][0]) > 1:
        raise ValueError('Video starts outside the frozen zero-based media clock')
    return {'start_ms': float(frames[0][0]), 'end_ms': float(frames[-1][1]),
            'start_ms_exact': str(frames[0][0]), 'end_ms_exact': str(frames[-1][1]),
            'duration_ms': float(frames[-1][1]-frames[0][0]), 'frame_count': len(frames),
            'time_base': str(time_base), 'frame_timing_format': 'integer_pts_and_duration_ticks',
            'frame_timing_sha256': digest({'time_base': str(time_base), 'frames': ticks}),
            'decode': 'FULL_SELECTED_VIDEO_STREAM'}


def probe(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Media file missing')
    command = ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode or result.stderr.strip():
        raise ValueError('Media probe failed: '+result.stderr[:500])
    data = json.loads(result.stdout)
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    audio = any(s['codec_type'] == 'audio' for s in data['streams'])
    duration = data.get('format', {}).get('duration')
    rate = video.get('avg_frame_rate', '0/0') if video else '0/0'
    fps = float(Fraction(rate)) if rate not in ('0/0', '0') else None
    format_name = data.get('format', {}).get('format_name', '')
    still_formats = {'image2', 'png_pipe', 'jpeg_pipe', 'webp_pipe', 'bmp_pipe', 'tiff_pipe'}
    kind = 'image' if video and format_name in still_formats and duration is None else 'video' if video else 'audio' if audio else 'unknown'
    rotation = int(next((x.get('rotation', 0) for x in (video or {}).get('side_data_list', []) if 'rotation' in x), (video or {}).get('tags', {}).get('rotate', 0))) % 360
    width, height = (video or {}).get('width'), (video or {}).get('height')
    if video and (not width or not height):
        raise ValueError('Media has no positive video dimensions')
    if kind == 'image':
        # Header metadata alone does not prove that the returned pixels decode.
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-err_detect', 'explode',
                                  '-i', str(path), '-map', '0:v:0', '-f', 'null', '-'],
                                 capture_output=True, text=True, timeout=30)
        if decoded.returncode or decoded.stderr.strip():
            raise ValueError('Image decode failed: '+decoded.stderr[:500])
    display_width, display_height = (height, width) if rotation in (90, 270) else (width, height)
    return {'rotation_deg': rotation, 'display_width': display_width, 'display_height': display_height, 'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
            'detected_kind': kind, 'format': format_name,
            'sample_aspect_ratio': (video or {}).get('sample_aspect_ratio'),
            'width': video.get('width') if video else None, 'height': video.get('height') if video else None,
            'duration_ms': round(float(duration)*1000) if duration else None, 'fps': fps,
            'codec': video.get('codec_name') if video else None, 'audio': audio, 'visual_review': 'NOT_RUN'}
