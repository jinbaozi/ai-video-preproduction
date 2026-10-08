"""Explicit timelines and frame-accurate assembly. No implicit retiming or crop."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import math
from collections import OrderedDict
from pathlib import Path

FORBIDDEN = ('setpts', 'scale', 'crop', 'stretch', 'atempo')
_PROBE_CACHE = OrderedDict()


def _media_digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_edl(edl):
    if not isinstance(edl, list) or not edl:
        raise ValueError('EDL is empty')
    for row in edl:
        if row.get('speed', 1) != 1:
            raise ValueError('Implicit retiming is not allowed')
        for flag in FORBIDDEN:
            if flag in row:
                raise ValueError('Implicit ' + flag + ' is not allowed')
        for key in ('take_id', 'src_in_frame', 'src_out_frame', 'fps', 'record_in_frame'):
            if key not in row:
                raise ValueError('EDL row missing ' + key)
        if row['src_out_frame'] <= row['src_in_frame']:
            raise ValueError('EDL range is empty')
        if any(not isinstance(row[key], int) or row[key] < 0 for key in ('src_in_frame', 'src_out_frame', 'record_in_frame')):
            raise ValueError('EDL frame positions must be non-negative integers')
        if not isinstance(row['fps'], (int, float)) or row['fps'] <= 0:
            raise ValueError('EDL fps must be positive')
    return True


def _decode(path):
    """Decode all video/audio bytes. ffprobe metadata alone can miss corruption."""
    if shutil.which('ffmpeg') is None:
        raise ValueError('ffmpeg is required for full media decoding')
    try:
        result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror',
                                 '-i', str(path), '-map', '0:v?', '-map', '0:a?',
                                 '-f', 'null', '-'], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Media decode did not complete') from exc
    if result.returncode or result.stderr.strip():
        raise ValueError('Media decode failed: ' + result.stderr[-1000:])


def _probe(path):
    if shutil.which('ffprobe') is None:
        raise ValueError('ffprobe is required')
    digest = _media_digest(path)
    if digest in _PROBE_CACHE:
        _PROBE_CACHE.move_to_end(digest)
        return dict(_PROBE_CACHE[digest])
    _decode(path)
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-count_frames', '-show_entries',
            'stream=codec_type,width,height,avg_frame_rate,duration,nb_read_frames:format=duration',
            '-of', 'json', str(path),
        ], text=True, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Media probe did not complete') from exc
    if result.returncode or result.stderr.strip():
        raise ValueError('Media probe failed: ' + result.stderr[-1000:])
    raw = result.stdout
    data = json.loads(raw)
    videos = [stream for stream in data['streams'] if stream['codec_type'] == 'video']
    if not videos:
        raise ValueError('Media has no video stream')
    info = videos[0]
    num, den = info['avg_frame_rate'].split('/')
    if float(den) == 0:
        raise ValueError('Media frame rate is unknown')
    fps = float(num) / float(den)
    duration = float(info.get('duration') or data['format']['duration'])
    if not math.isfinite(fps) or fps <= 0 or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Media timing is invalid')
    observed = {
        'width': info['width'], 'height': info['height'], 'fps': fps,
        'duration_ms': int(round(duration * 1000)),
        'aspect': f"{info['width']}:{info['height']}",
        'audio_streams': sum(stream['codec_type'] == 'audio' for stream in data['streams']),
        'frames': int(info['nb_read_frames']) if str(info.get('nb_read_frames', '')).isdigit() else None,
    }
    if _media_digest(path) != digest:
        raise ValueError('Media bytes changed while probing')
    # Same-byte rechecks need hashing, not another full decode. Process-local,
    # bounded cache never stores semantic/visual approval or crosses restarts.
    _PROBE_CACHE[digest] = dict(observed)
    while len(_PROBE_CACHE) > 128:
        _PROBE_CACHE.popitem(last=False)
    return observed


def assemble_ffmpeg(edl, output, spec, *, runner=None, probe_fn=None):
    validate_edl(edl)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if runner is None:
        if shutil.which('ffmpeg') is None:
            return {'status': 'TOOL_UNAVAILABLE', 'tool': 'ffmpeg'}

        def runner(cmd):
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                raise ValueError('ffmpeg failed: ' + result.stderr[-2000:])
    source_probe = probe_fn or _probe
    sources = [source_probe(row['source']) for row in edl]
    for row, observed in zip(edl, sources):
        for key in ('width', 'height', 'fps'):
            if key in spec and observed[key] != spec[key]:
                raise ValueError('Source media differs from assembly spec: ' + key)
        if row['fps'] != observed['fps']:
            raise ValueError('EDL frame rate differs from source')
        if row['src_out_frame'] > round(observed['duration_ms'] * row['fps'] / 1000):
            raise ValueError('EDL extends beyond source media')
    post_audio = spec.get('post_audio', [])
    if not isinstance(post_audio, list):
        raise ValueError('post_audio must be a list')
    for track in post_audio:
        if not isinstance(track, dict) or not Path(track.get('source', '')).is_file() or not isinstance(track.get('start_ms'), int) or track['start_ms'] < 0:
            raise ValueError('Post audio track needs a local source and non-negative start_ms')
        if track.get('sha256') != hashlib.sha256(Path(track['source']).read_bytes()).hexdigest():
            raise ValueError('Post audio bytes differ from frozen hash')
        if not isinstance(track.get('gain', 1), (int, float)) or track.get('gain', 1) < 0:
            raise ValueError('Post audio gain must be non-negative')
    needs_audio = any(source.get('audio_streams', 0) for source in sources) or spec.get('require_audio', False) or bool(post_audio)
    with tempfile.TemporaryDirectory(prefix='assembly-', dir=output.parent) as work:
        clips = []
        for index, (row, observed) in enumerate(zip(edl, sources)):
            clip = Path(work) / f'clip-{index:04d}.mp4'
            start = row['src_in_frame'] / row['fps']
            end = row['src_out_frame'] / row['fps']
            video = f"[0:v]trim=start_frame={row['src_in_frame']}:end_frame={row['src_out_frame']},setpts=PTS-STARTPTS[v]"
            cmd = ['ffmpeg', '-y', '-i', row['source']]
            if needs_audio and not observed.get('audio_streams', 0):
                cmd += ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000']
            if needs_audio:
                source = '[0:a]' if observed.get('audio_streams', 0) else '[1:a]'
                audio = f'{source}atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS[a]'
                cmd += ['-filter_complex', video + ';' + audio, '-map', '[v]', '-map', '[a]',
                        '-c:v', 'libx264', '-c:a', 'aac', '-ar', '48000', '-ac', '2']
            else:
                cmd += ['-filter_complex', video, '-map', '[v]', '-an', '-c:v', 'libx264']
            runner(cmd + [str(clip)])
            clips.append(clip)
        list_file = Path(work) / 'concat.txt'
        list_file.write_text(''.join("file '" + str(clip) + "'\n" for clip in clips), encoding='utf-8')
        joined = Path(work) / 'joined.mp4' if post_audio else output
        concat = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_file)]
        if needs_audio:
            concat += ['-c:v', 'copy', '-c:a', 'aac', '-af', 'aresample=async=1:first_pts=0']
        else:
            concat += ['-c', 'copy']
        runner(concat + [str(joined)])
        if post_audio:
            filters = ['[0:a]asetpts=PTS-STARTPTS[a0]']
            for index, track in enumerate(post_audio, start=1):
                filters.append(f"[{index}:a]asetpts=PTS-STARTPTS,volume={track.get('gain', 1)},adelay={track['start_ms']}|{track['start_ms']}[a{index}]")
            labels = ''.join(f'[a{index}]' for index in range(len(post_audio) + 1))
            filters.append(labels + f'amix=inputs={len(post_audio) + 1}:duration=first:dropout_transition=0[aout]')
            cmd = ['ffmpeg', '-y', '-i', str(joined)]
            for track in post_audio:
                cmd += ['-i', track['source']]
            runner(cmd + ['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[aout]',
                          '-c:v', 'copy', '-c:a', 'aac', str(output)])
    probe = (probe_fn or _probe)(output)
    if spec.get('width') and probe['width'] != spec['width']:
        raise ValueError('Assembly width differs from spec')
    if spec.get('height') and probe['height'] != spec['height']:
        raise ValueError('Assembly height differs from spec')
    if spec.get('fps') and probe['fps'] != spec['fps']:
        raise ValueError('Assembly frame rate differs from spec')
    if needs_audio and not probe.get('audio_streams', 0):
        raise ValueError('Assembly output has lost required audio')
    if probe.get('frames') != sum(row['src_out_frame'] - row['src_in_frame'] for row in edl):
        raise ValueError('Assembly output decoded frame count differs from EDL')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {'status': 'CHECKED', 'tool': 'ffmpeg', 'probe': probe, 'output_sha256': digest}


def timelines(project_ranges, media_ranges, post_ranges):
    return {
        'project_timeline': {'ranges': project_ranges, 'unit': 'project_ms'},
        'media_timeline': {'ranges': media_ranges, 'unit': 'media_frame'},
        'post_timeline': {'ranges': post_ranges, 'unit': 'post_ms'},
    }


def export_jianying(edl, out_dir):
    validate_edl(edl)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {'schema': 'jianying-handoff/1.0', 'tool': 'jianying', 'edl': edl, 'assembled': False}
    (out / 'jianying-handoff.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def export_hypit(edl, out_dir):
    validate_edl(edl)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {'schema': 'hypit-handoff/1.0', 'tool': 'hypit', 'edl': edl, 'submitted': False}
    (out / 'hypit-handoff.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload
