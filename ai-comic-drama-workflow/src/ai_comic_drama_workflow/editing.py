"""Execute an approved Edit Plan, never infer sequence from filenames."""
from pathlib import Path
import shutil
import subprocess
import tempfile

from .utils import canonical_json, sha256_bytes


def validate_edit_plan(plan, *, shot_ids=None, subtitle_language=None):
    timeline = plan['timeline']
    if not timeline:
        raise ValueError('Edit Plan has no timeline')
    total = 0.0
    for index, cut in enumerate(timeline):
        duration = float(cut['duration_s'])
        if duration <= 0 or float(cut.get('in_s', 0)) < 0:
            raise ValueError('Edit source range must be positive')
        if shot_ids is not None and cut['shot_id'] not in shot_ids:
            raise ValueError('Edit Plan references an unknown shot')
        transition = cut.get('transition_in', {'type': 'cut'})
        if transition['type'] == 'dissolve':
            overlap = float(transition['duration_s'])
            if not index or not 0 < overlap < min(duration, timeline[index-1]['duration_s']):
                raise ValueError('Dissolve must fit both neighboring clips')
            total -= overlap
        elif transition['type'] != 'cut':
            raise ValueError('Unsupported transition; no silent substitution')
        total += duration
    line_ids = [line['line_id'] for line in plan['dialogue_table']]
    if len(set(line_ids)) != len(line_ids):
        raise ValueError('Dialogue line IDs must be unique')
    for line in plan['dialogue_table']:
        start = float(line['start_s'])
        end = float(line['end_s']) if 'end_s' in line else start + float(line['duration_s'])
        if not 0 <= start < end <= total:
            raise ValueError('Dialogue interval falls outside the assembled edit')
    if subtitle_language is not None and plan.get('subtitle_language') != subtitle_language:
        raise ValueError('Edit Plan must preserve the selected subtitle language')
    return total


def subtitle_text(lines):
    def stamp(seconds):
        milliseconds = round(float(seconds) * 1000)
        if milliseconds < 0:
            raise ValueError('Subtitle time cannot be negative')
        hours, rest = divmod(milliseconds, 3600000)
        minutes, rest = divmod(rest, 60000)
        seconds, millis = divmod(rest, 1000)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}'
    blocks = []
    for index, line in enumerate(lines, 1):
        start = float(line['start_s'])
        end = float(line['end_s']) if 'end_s' in line else start + float(line['duration_s'])
        if end <= start or not line['text'].strip():
            raise ValueError('Dialogue needs nonempty text and an explicit positive subtitle interval')
        blocks.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{line['text'].strip()}\n")
    return '\n'.join(blocks)


def execute_edit_plan(store, plan, media, *, audio_assets=(), aspect='16:9', fps=24, voice_strategy='original-audio'):
    validate_edit_plan(plan, shot_ids={m['shot_id'] for m in media})
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('FFmpeg unavailable; retain edit checklist, do not claim rendered video')
    source_map = {m['shot_id']: m for m in media}
    timeline = plan['timeline']
    if not timeline:
        raise ValueError('Edit Plan has no timeline')
    from .pipeline import inspect_video, inspect_audio
    audio_assets = tuple(audio_assets)
    width, height = map(float, aspect.split(':'))
    size = (640, max(2, round(640*height/width/2)*2))
    argv = [ffmpeg, '-y', '-v', 'error']
    filters, durations = [], []
    for index, cut in enumerate(timeline):
        if cut['shot_id'] not in source_map:
            raise ValueError(f"Edit Plan source missing: {cut['shot_id']}")
        media_file = store.path(source_map[cut['shot_id']]['path'])
        info = inspect_video(media_file)
        if not info['verified']:
            raise ValueError(f'Unreadable edit source: {media_file.name}')
        start, duration = float(cut.get('in_s', 0)), float(cut['duration_s'])
        if duration <= 0 or start < 0 or start+duration > float(info['duration_s']) + 1/fps:
            raise ValueError('Edit in/out range exceeds actual source duration')
        argv += ['-i', str(media_file)]
        filters.append(f'[{index}:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS,fps={fps},scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease,pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{index}]')
        has_audio = any(s.get('codec_type') == 'audio' for s in info.get('streams', []))
        if has_audio and voice_strategy == 'original-audio':
            filters.append(f'[{index}:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{index}]')
        else:
            filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration}[a{index}]')
        durations.append(duration)
    video, audio, total = 'v0', 'a0', durations[0]
    for index in range(1, len(timeline)):
        transition = timeline[index].get('transition_in', {'type': 'cut'})
        next_video, next_audio = f'joinv{index}', f'joina{index}'
        if transition['type'] == 'cut':
            filters.append(f'[{video}][{audio}][v{index}][a{index}]concat=n=2:v=1:a=1[{next_video}][{next_audio}]')
            total += durations[index]
        elif transition['type'] == 'dissolve':
            duration = float(transition['duration_s'])
            if not 0 < duration < min(durations[index-1], durations[index]):
                raise ValueError('Dissolve must fit both neighboring clips')
            filters.append(f'[{video}][v{index}]xfade=transition=fade:duration={duration}:offset={total-duration}[{next_video}]')
            filters.append(f'[{audio}][a{index}]acrossfade=d={duration}[{next_audio}]')
            total += durations[index]-duration
        else:
            raise ValueError('Unsupported transition; explicitly revise the plan, no silent replacement')
        video, audio = next_video, next_audio
    dialogue = {line['line_id']: line for line in plan['dialogue_table']}
    mixed_ids = []
    audio_labels = [audio]
    for index, item in enumerate(audio_assets, len(timeline)):
        line = dialogue[item['line_id']]
        argv += ['-i', str(store.path(item['path']))]
        delay = round(float(line['start_s'])*1000)
        if delay < 0 or float(line['start_s']) >= total:
            raise ValueError('Dialogue falls outside edit timeline')
        info = inspect_audio(store.path(item['path']))
        end = float(line['end_s']) if 'end_s' in line else float(line['start_s']) + float(line['duration_s'])
        if not info['verified'] or end > total + 1/fps or info['duration_s'] > end - float(line['start_s']) + 1/fps:
            raise ValueError('Voice exceeds its approved dialogue interval; revise timing or voice, do not silently truncate')
        label = f'voice{index}'
        filters.append(f'[{index}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}|{delay}[{label}]')
        audio_labels.append(label)
        mixed_ids.append(item['line_id'])
    if len(audio_labels) > 1:
        filters.append(''.join(f'[{label}]' for label in audio_labels) + f'amix=inputs={len(audio_labels)}:normalize=0,alimiter=limit=0.95,atrim=duration={total}[mixed]')
        audio = 'mixed'
    fingerprint = sha256_bytes(canonical_json({'plan': plan, 'media': media, 'audio': list(audio_assets), 'aspect': aspect, 'fps': fps, 'voice_strategy': voice_strategy}).encode())
    folder = f'stages/12-配音字幕与剪辑/media/render/{fingerprint[:20]}'
    subtitles = subtitle_text(plan['dialogue_table']) if plan.get('subtitle_language') != 'none' else ''
    store.write_text(f'{folder}/subtitles.srt', subtitles)
    subtitle_index = len(timeline) + len(audio_assets)
    if subtitles:
        argv += ['-i', str(store.path(f'{folder}/subtitles.srt'))]
    with tempfile.TemporaryDirectory(prefix='ai-comic-edit-') as temporary:
        target = Path(temporary) / 'preview.mp4'
        command = argv + ['-filter_complex', ';'.join(filters), '-map', f'[{video}]', '-map', f'[{audio}]',
                          '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac']
        if subtitles:
            command += ['-map', f'{subtitle_index}:s', '-c:s', 'mov_text']
        command += ['-t', str(total), '-movflags', '+faststart', str(target)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if process.returncode:
            raise ValueError('Edit Plan execution failed: ' + process.stderr[-3000:])
        inspection = inspect_video(target, require_audio=True)
        if not inspection['verified'] or abs(inspection['duration_s']-total) > 2/fps:
            raise ValueError('Rendered edit failed duration/decode validation')
        relative = f'{folder}/preview.mp4'
        digest = store.copy_source(target, relative)
    return {'path': relative, 'sha256': digest, **inspection, 'edit_plan_executed': True,
            'shot_order': [item['shot_id'] for item in timeline], 'expected_duration_s': total,
            'mixed_line_ids': mixed_ids, 'subtitle_status': 'muxed' if subtitles else 'not_requested',
            'boundary': 'Imported footage or 3D preview edit; not a cloud-generated AI video'}
