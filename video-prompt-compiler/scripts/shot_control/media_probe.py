"""Probe actual local media without treating decode success as visual QA."""
from fractions import Fraction
from pathlib import Path
import json
import subprocess
from .common import sha


def probe(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Media file missing')
    command = ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
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
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
            'detected_kind': kind, 'format': format_name,
            'width': video.get('width') if video else None, 'height': video.get('height') if video else None,
            'duration_ms': round(float(duration)*1000) if duration else None, 'fps': fps,
            'codec': video.get('codec_name') if video else None, 'audio': audio, 'visual_review': 'NOT_RUN'}
