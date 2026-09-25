"""Explicit timelines and frame-accurate assembly. No implicit retiming or crop."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

FORBIDDEN = ('setpts', 'scale', 'crop', 'stretch', 'atempo', 'fps')


def validate_edl(edl):
    if not edl:
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
    return True


def _probe(path):
    if shutil.which('ffprobe') is None:
        raise ValueError('ffprobe is required')
    raw = subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,avg_frame_rate,duration',
        '-of', 'json', str(path),
    ], text=True)
    info = json.loads(raw)['streams'][0]
    num, den = info['avg_frame_rate'].split('/')
    fps = float(num) / float(den)
    return {
        'width': info['width'], 'height': info['height'], 'fps': fps,
        'duration_ms': int(round(float(info['duration']) * 1000)),
        'aspect': f"{info['width']}:{info['height']}",
    }


def assemble_ffmpeg(edl, output, spec, *, runner=None, probe_fn=None):
    validate_edl(edl)
    output = Path(output)
    if runner is None:
        if shutil.which('ffmpeg') is None:
            return {'status': 'TOOL_UNAVAILABLE', 'tool': 'ffmpeg'}

        def runner(cmd):
            subprocess.check_call(cmd)
    list_file = output.with_suffix('.concat.txt')
    lines = []
    for index, row in enumerate(edl):
        clip = output.parent / f'clip-{index}.mp4'
        frames = row['src_out_frame'] - row['src_in_frame']
        runner([
            'ffmpeg', '-y', '-i', row['source'],
            '-vf', f"trim=start_frame={row['src_in_frame']}:end_frame={row['src_out_frame']},setpts=PTS-STARTPTS",
            '-an', str(clip),
        ])
        # setpts=PTS-STARTPTS resets the clip clock after an explicit frame trim.
        # It is not a speed change. Speed remains 1 and is rejected if the EDL asks otherwise.
        lines.append(f"file '{clip}'")
        row['frames'] = frames
    list_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    runner(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_file), '-c', 'copy', str(output)])
    probe = (probe_fn or _probe)(output)
    if spec.get('width') and probe['width'] != spec['width']:
        raise ValueError('Assembly width differs from spec')
    if spec.get('height') and probe['height'] != spec['height']:
        raise ValueError('Assembly height differs from spec')
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
