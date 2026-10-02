"""Opt-in adapter for the separately installed, pinned Jianying Headless core.

Nothing from that repository is imported by this module. Static setup inspection
and plan creation do not execute it. Every core command, including doctor, is
behind an explicit, commit/backend-scoped execution authorization. The core is
source-available, not part of this package, and is never downloaded automatically.

``native`` produces an offline macOS draft pending UI/registration acceptance.
``portable-ffmpeg`` invokes upstream's windows-ffmpeg backend on any compatible
host: its editable artifact is JSON plus owned media, never a native draft.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import uuid
from fractions import Fraction
from pathlib import Path

from .assembly import validate_edl

CORE_REPOSITORY = 'https://github.com/jinbaozi/jianying-headless.git'
PINNED_COMMIT = '42b3d75b15bd9f3a9bb4c11b2f5205f7b4312252'
LICENSE_SHA256 = '107d928e6cc3848b651c4e026d247693c03f7bed5372ce48788baa72f1cf54f8'
LICENSE_URL = CORE_REPOSITORY[:-4] + '/blob/' + PINNED_COMMIT + '/LICENSE'
PLAN_SCHEMA = 'jy14-headless-plan/v1'
BACKENDS = ('native', 'portable-ffmpeg')


def _digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def canonical_json_sha256(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _backend(backend):
    if backend == 'windows-ffmpeg':
        return 'portable-ffmpeg'
    if backend not in BACKENDS:
        raise ValueError('Backend must be native or portable-ffmpeg')
    return backend


def _core_root(core_root):
    raw = core_root or os.environ.get('JIANYING_HEADLESS_ROOT')
    if not raw:
        raise ValueError('Set JIANYING_HEADLESS_ROOT to the separately authorized core checkout')
    path = Path(raw).expanduser()
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError('Core root must be an absolute, non-symlink checkout directory')
    return path.resolve()


def _verify_core(root):
    """Verify Git object identity and every tracked byte without importing code."""
    git = shutil.which('git')
    if not git:
        raise ValueError('git is required to verify the pinned core checkout')
    command = [git, '--no-pager', '-c', 'core.fsmonitor=false', '-c',
               'core.hooksPath=/dev/null', '-C', str(root)]
    def read_git(*args):
        return subprocess.check_output(command + list(args), stderr=subprocess.PIPE,
                                       timeout=30)
    head = read_git('rev-parse', '--verify', 'HEAD').decode().strip()
    if head != PINNED_COMMIT:
        raise ValueError('Core HEAD differs from the reviewed pinned commit: ' + head)
    entries = read_git('ls-tree', '-rz', '--full-tree', PINNED_COMMIT)
    tracked = set()
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        mode, kind, digest = metadata.split()
        name = raw_name.decode('utf-8')
        if kind != b'blob' or mode not in (b'100644', b'100755'):
            raise ValueError('Core contains unsupported symlink/submodule: ' + name)
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Pinned core file is missing or unsafe: ' + name)
        data = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual != digest.decode():
            raise ValueError('Pinned core file changed: ' + name)
        tracked.add(name)
    # Python can load untracked sibling modules, extension modules or bytecode.
    for directory in ('engine', 'bridge', 'skills/yichen-jianying-edit/scripts'):
        for path in (root / directory).rglob('*'):
            if path.is_symlink():
                raise ValueError('Symlink in core execution directory: ' + str(path))
            if path.is_file() and path.suffix.lower() in {'.py', '.pyc', '.pyo', '.so', '.pyd'}:
                if path.relative_to(root).as_posix() not in tracked:
                    raise ValueError('Untracked executable module in core: ' + str(path))
    identity = _read(root / 'project.json')
    if identity.get('id') != 'jianying-headless' or identity.get('schema') != 'jianying-headless-project/v1':
        raise ValueError('Core project identity is invalid')
    if _digest(root / 'LICENSE') != LICENSE_SHA256:
        raise ValueError('Core license differs from the reviewed license')
    return {'commit': head, 'tracked_files_verified': len(tracked), 'license_sha256': LICENSE_SHA256}


def inspect_setup(core_root=None, backend='portable-ffmpeg'):
    """Read-only checks; READY_FOR_AUTHORIZATION is not runtime acceptance."""
    backend = _backend(backend)
    result = {'status': 'BLOCKED_SETUP', 'tool': 'jianying-headless', 'backend': backend,
              'core_repository': CORE_REPOSITORY, 'core_commit': PINNED_COMMIT,
              'license_url': LICENSE_URL, 'runtime_executed': False,
              'native_editable_draft': False, 'reasons': []}
    try:
        root = _core_root(core_root)
        result['core_root'] = str(root)
        result['core_verification'] = _verify_core(root)
        for name in ('ffmpeg', 'ffprobe'):
            if not shutil.which(name):
                result['reasons'].append(name + ' is required')
        if backend == 'native':
            if platform.system() != 'Darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
                result['reasons'].append('Native backend requires an Apple Silicon Mac')
            if not Path('/Applications/VideoFusion-macOS.app').is_dir():
                result['reasons'].append('Matching Jianying 11.5.0/11.4.2 application is required')
            if not (root / 'bridge/jy14_codec_hardened_11_4').is_file():
                result['reasons'].append('Pinned native codec must be built separately with approval')
        if not result['reasons']:
            result['status'] = 'READY_FOR_AUTHORIZATION'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result['reasons'].append(str(error))
    return result


def _validate_authorization(authorization, backend, usage, *, action='execute-jianying-headless'):
    if not isinstance(authorization, dict):
        raise ValueError('Recorded per-action execution approval is required')
    expected = {'decision': 'APPROVED', 'action': action,
                'core_commit': PINNED_COMMIT, 'backend': backend, 'usage': usage}
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise ValueError('Execution approval must identify this action, commit, backend and usage')
    if authorization.get('license_accepted') is not True:
        raise ValueError('Explicit acceptance of the pinned core license is required')
    for key in ('actor', 'evidence'):
        if not isinstance(authorization.get(key), str) or not authorization[key].strip():
            raise ValueError('Execution approval needs a nonempty ' + key)
    if usage not in ('personal-noncommercial', 'commercial'):
        raise ValueError('Declare personal-noncommercial or commercial usage')
    if usage == 'commercial':
        permission = authorization.get('commercial_permission', {})
        if (not isinstance(permission, dict) or permission.get('scope') != 'commercial' or
                any(not isinstance(permission.get(key), str) or not permission[key].strip()
                    for key in ('copyright_holder', 'written_permission'))):
            raise ValueError('Commercial use needs explicit written copyright-holder permission')
    return hashlib.sha256(json.dumps(authorization, sort_keys=True, allow_nan=False).encode()).hexdigest()



def install_core(destination, authorization=None, *, usage='personal-noncommercial', runner=None):
    """Install only the reviewed source commit after destination-scoped approval.

    Uses Git's official client to fetch that exact commit, never current HEAD.
    No pip install, upstream Python, native build, doctor or dependency download
    runs here. Approval action is ``install-jianying-headless`` and additionally
    includes ``destination`` (absolute path); execution needs separate approval.
    The backend field remains ``portable-ffmpeg`` or ``native`` to record intent.
    """
    destination = Path(destination).expanduser().absolute()
    identity = {'tool': 'jianying-headless', 'core_commit': PINNED_COMMIT,
                'core_repository': CORE_REPOSITORY, 'destination': str(destination),
                'runtime_executed': False, 'license_url': LICENSE_URL}
    try:
        if not isinstance(authorization, dict):
            raise ValueError('Recorded per-action installation approval is required')
        backend = _backend(authorization.get('backend'))
        approval_hash = _validate_authorization(authorization, backend, usage,
                                                action='install-jianying-headless')
        if authorization.get('destination') != str(destination):
            raise ValueError('Installation approval must identify the exact absolute destination')
    except (ValueError, TypeError) as error:
        return dict(identity, status='BLOCKED_AUTHORIZATION', reasons=[str(error)])
    if destination.exists() or destination.is_symlink():
        raise ValueError('Core install destination already exists; do not overwrite a checkout')
    git = shutil.which('git')
    if not git:
        return dict(identity, status='BLOCKED_SETUP', reasons=['git is required'])
    prefix = [git, '--no-pager', '-c', 'core.hooksPath=/dev/null', '-c',
              'core.autocrlf=false', '-c', 'core.fsmonitor=false']
    commands = [prefix + ['init', '--', str(destination)],
                prefix + ['-C', str(destination), 'remote', 'add', 'origin', CORE_REPOSITORY],
                prefix + ['-C', str(destination), 'fetch', '--depth=1', 'origin', PINNED_COMMIT],
                prefix + ['-C', str(destination), 'checkout', '--detach', PINNED_COMMIT]]
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        for command in commands:
            result = runner(command) if runner is not None else subprocess.run(
                command, capture_output=True, text=True, timeout=180)
            if result is not None:
                code = result.get('returncode', 0) if isinstance(result, dict) else result.returncode
                stderr = result.get('stderr', '') if isinstance(result, dict) else result.stderr
                if code:
                    raise ValueError('Pinned core installation failed: ' + (stderr or '')[-2000:])
        verification = _verify_core(destination)
        return dict(identity, status='SOURCE_INSTALLED', core_verification=verification,
                    authorization_sha256=approval_hash, commands=commands,
                    next_step='Obtain separate execute-jianying-headless approval before any core command')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return dict(identity, status='FAILED', reasons=[str(error)], commands=commands,
                    partial_artifacts_retained=True, authorization_sha256=approval_hash)


def _regular_source(value):
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError('Media source must be a local file')
    path = Path(value).expanduser()
    if not path.is_file() or path.is_symlink():
        raise ValueError('Media source must be a non-symlink local file: ' + str(path))
    return path.resolve()


def probe_media(path):
    """ffprobe evidence for either audio or video; never runs the external core."""
    executable = shutil.which('ffprobe')
    if not executable:
        raise ValueError('ffprobe is required')
    result = subprocess.run([executable, '-v', 'error', '-count_frames', '-show_streams',
                             '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError('ffprobe failed: ' + result.stderr[-2000:])
    raw = json.loads(result.stdout)
    videos = [row for row in raw.get('streams', []) if row.get('codec_type') == 'video'
              and not row.get('disposition', {}).get('attached_pic')]
    audios = [row for row in raw.get('streams', []) if row.get('codec_type') == 'audio']
    if len(videos) > 1 or len(audios) > 1 or not (videos or audios):
        raise ValueError('Core supports at most one video and one audio stream per source')
    primary = (videos or audios)[0]
    duration = float(primary.get('duration') or raw.get('format', {}).get('duration') or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Media duration must be finite and positive')
    info = {'duration_us': round(duration * 1_000_000), 'duration_ms': round(duration * 1000),
            'audio_streams': len(audios), 'video_streams': len(videos), 'raw': raw}
    if videos:
        rate = Fraction(primary.get('avg_frame_rate', '0/1'))
        info.update(width=primary['width'], height=primary['height'], fps=float(rate),
                    frames=int(primary['nb_read_frames']) if
                    str(primary.get('nb_read_frames', '')).isdigit() else None,
                    codec_name=primary.get('codec_name'), pix_fmt=primary.get('pix_fmt'))
    return info


def _micros(frame, fps):
    return round(Fraction(frame * 1_000_000, fps))


def build_headless_plan(edl, spec, *, name='AI video assembly', probe_fn=None):
    """Compile continuous frame EDL and frozen post audio into the real core plan.

    Native audio is retained at unity gain. Post audio is explicitly end-trimmed
    to the picture duration, matching assembly's duration=first mix contract.
    Scaling, cropping, speed changes and fractional FPS are rejected.
    """
    validate_edl(edl)
    if not isinstance(spec, dict):
        raise ValueError('Assembly spec must be an object')
    allowed_spec = {'width', 'height', 'fps', 'preserve_native_audio', 'require_audio', 'post_audio', 'project', 'media', 'post'}
    if set(spec) - allowed_spec:
        raise ValueError('Unsupported editing output parameters: ' + ', '.join(sorted(set(spec) - allowed_spec)))
    for flag in ('preserve_native_audio', 'require_audio'):
        if flag in spec and type(spec[flag]) is not bool:
            raise ValueError(flag + ' must be boolean')
    if spec.get('preserve_native_audio', True) is not True:
        raise ValueError('This adapter preserves native audio; muting requires a supported explicit editing plan')
    canvas = {key: spec.get(key) for key in ('width', 'height', 'fps')}
    if any(type(canvas[key]) is not int or not 16 <= canvas[key] <= 8192 for key in ('width', 'height')):
        raise ValueError('Canvas dimensions must be integers in 16..8192')
    if type(canvas['fps']) is not int or canvas['fps'] not in {24, 25, 30, 50, 60}:
        raise ValueError('Pinned core supports only integer FPS: 24, 25, 30, 50, 60')
    if (not isinstance(name, str) or not name.strip() or name.strip() != name or name.startswith('.')
            or len(name.encode()) >= 200 or any(char in name for char in '/\\\x00\r\n')):
        raise ValueError('Draft name must be a visible single directory component')
    probe = probe_fn or probe_media
    videos, native_audio, cache = [], False, {}
    record_end = 0
    for row in edl:
        allowed_row = {'take_id', 'shot_id', 'source', 'sha256', 'src_in_frame', 'src_out_frame', 'fps', 'record_in_frame', 'speed'}
        if set(row) - allowed_row:
            raise ValueError('Unsupported editing EDL parameters: ' + ', '.join(sorted(set(row) - allowed_row)))
        if type(row.get('speed', 1)) not in (int, float) or row.get('speed', 1) != 1:
            raise ValueError('Unsupported editing speed')
        if any(type(row[key]) is not int for key in ('src_in_frame', 'src_out_frame', 'record_in_frame')):
            raise ValueError('EDL frame positions must be integers, not booleans')
        if row['fps'] != canvas['fps'] or type(row['fps']) not in (int, float):
            raise ValueError('EDL FPS differs from output canvas')
        if row['record_in_frame'] != record_end:
            raise ValueError('Main EDL must be continuous, ordered and start at zero')
        source = _regular_source(row.get('source'))
        if row.get('sha256') and _digest(source) != row['sha256']:
            raise ValueError('Source media differs from its frozen hash')
        observed = cache.setdefault(str(source), None)
        if observed is None:
            observed = cache[str(source)] = probe(source)
        if any(observed.get(key) != value for key, value in canvas.items()):
            raise ValueError('Source media differs from assembly dimensions or FPS')
        frames = observed.get('frames')
        if type(frames) is not int:
            raise ValueError('Source decoded frame count is required')
        if row['src_out_frame'] > frames:
            raise ValueError('EDL extends beyond source decoded frames')
        native_audio = native_audio or bool(observed.get('audio_streams', 0))
        end = record_end + row['src_out_frame'] - row['src_in_frame']
        videos.append({'source': str(source), 'start_us': _micros(record_end, canvas['fps']),
                       'duration_us': _micros(end, canvas['fps']) - _micros(record_end, canvas['fps']),
                       'source_start_us': _micros(row['src_in_frame'], canvas['fps']),
                       'source_duration_us': _micros(row['src_out_frame'], canvas['fps']) -
                                             _micros(row['src_in_frame'], canvas['fps']),
                       'speed': 1, 'volume': 1})
        record_end = end
    tracks = [{'type': 'video', 'name': 'Main picture and original audio', 'segments': videos}]
    post_audio = spec.get('post_audio', [])
    if not isinstance(post_audio, list):
        raise ValueError('post_audio must be a list')
    duration_us = _micros(record_end, canvas['fps'])
    for index, audio in enumerate(post_audio):
        if not isinstance(audio, dict):
            raise ValueError('Post audio track must be an object')
        if set(audio) - {'source', 'sha256', 'start_ms', 'gain'}:
            raise ValueError('Unsupported post audio parameters')
        source = _regular_source(audio.get('source'))
        if audio.get('sha256') != _digest(source):
            raise ValueError('Post audio bytes differ from frozen hash')
        if type(audio.get('start_ms')) is not int or audio['start_ms'] < 0:
            raise ValueError('Post audio start_ms must be a non-negative integer')
        start = audio['start_ms'] * 1000
        gain = audio.get('gain', 1)
        if type(gain) not in (int, float) or not math.isfinite(gain) or not 0 <= gain <= 4:
            raise ValueError('Pinned core post audio gain must be finite and in 0..4')
        info = probe(source)
        if not info.get('audio_streams') or info.get('video_streams', 0) or info.get('width'):
            raise ValueError('Post audio must be an audio-only source')
        source_duration = info.get('duration_us', int(info.get('duration_ms', 0) * 1000))
        if type(source_duration) is not int or source_duration <= 0 or start >= duration_us:
            raise ValueError('Post audio must overlap the picture timeline with known duration')
        span = min(source_duration, duration_us - start)
        tracks.append({'type': 'audio', 'name': 'Post audio ' + str(index + 1), 'segments': [
            {'source': str(source), 'start_us': start, 'duration_us': span,
             'source_start_us': 0, 'source_duration_us': span, 'speed': 1, 'volume': gain}]})
    if spec.get('require_audio') and not (native_audio or post_audio):
        raise ValueError('Required audio is absent; a silent bed is not a soundtrack')
    return {'schema': PLAN_SCHEMA, 'name': name, 'canvas': canvas, 'tracks': tracks}



def canonical_assembly_probe(media):
    """Match assembly._probe exactly for the production ledger's revalidation."""
    return {key: media[key] for key in
            ('width', 'height', 'fps', 'duration_ms', 'audio_streams', 'frames')} | {
                'aspect': str(media['width']) + ':' + str(media['height'])}

def verify_mp4(output, edl, spec, *, probe_fn=None, require_audio=False):
    """Independent decoded-frame/dimensions/audio/hash checks on the actual MP4."""
    output = _regular_source(output)
    if output.suffix.lower() != '.mp4' or output.stat().st_size == 0:
        raise ValueError('Expected a nonempty MP4 file')
    probe = (probe_fn or probe_media)(output)
    for key in ('width', 'height', 'fps'):
        if probe.get(key) != spec.get(key):
            raise ValueError('Assembly output differs from spec: ' + key)
    expected_frames = sum(row['src_out_frame'] - row['src_in_frame'] for row in edl)
    if type(probe.get('frames')) is not int or probe['frames'] != expected_frames:
        raise ValueError('Assembly output decoded frame count differs from EDL')
    expected_ms = expected_frames / spec['fps'] * 1000
    if abs(probe.get('duration_ms', -1) - expected_ms) > 1000 / spec['fps'] + 1:
        raise ValueError('Assembly output duration differs from EDL')
    if (require_audio or spec.get('require_audio') or spec.get('post_audio')) and not probe.get('audio_streams'):
        raise ValueError('Assembly output has lost required audio')
    if probe.get('codec_name') not in (None, 'h264') or probe.get('pix_fmt') not in (None, 'yuv420p'):
        raise ValueError('Expected H.264/yuv420p output')
    return {'probe': canonical_assembly_probe(probe), 'output_sha256': _digest(output),
            'expected_frames': expected_frames}


def assemble_jianying(edl, output, spec, *, core_root=None, backend='portable-ffmpeg',
                       authorization=None, usage='personal-noncommercial', runner=None, probe_fn=None):
    """Build, verify and export via approved pinned core CLI entry points.

    ``runner(command)`` is an injectable process runner for tests. Production
    callers omit it. Approval/setup failures return BLOCKED_*; execution failures
    return FAILED and preserve the isolated job. No automatic fallback or retry.
    Existing output and project directories are never overwritten. A CHECKED
    result covers technical media checks, not visual/audio or native UI review.
    """
    backend = _backend(backend)
    identity = {'tool': 'jianying', 'backend': backend,
                'renderer_backend': 'native' if backend == 'native' else 'windows-ffmpeg',
                'core_repository': CORE_REPOSITORY, 'core_commit': PINNED_COMMIT,
                'native_editable_draft': False, 'assembled': False}
    try:
        approval_hash = _validate_authorization(authorization, backend, usage)
    except (ValueError, TypeError) as error:
        return dict(identity, status='BLOCKED_AUTHORIZATION', reasons=[str(error)], license_url=LICENSE_URL)
    setup = inspect_setup(core_root, backend)
    if setup['status'] != 'READY_FOR_AUTHORIZATION':
        return dict(identity, status='BLOCKED_SETUP', reasons=setup['reasons'], setup=setup)
    root = Path(setup['core_root'])
    output = Path(output).expanduser().absolute()
    project = output.with_suffix('.jianying-project')
    if output.exists() or output.is_symlink() or project.exists() or project.is_symlink():
        raise ValueError('Assembly output/project already exists; use a new destination')
    if output.suffix.lower() != '.mp4':
        raise ValueError('Assembly output must have an .mp4 suffix')
    # Freeze before probing too: a source must not change between source
    # verification and the external builder's copy of those bytes.
    validate_edl(edl)
    if not isinstance(spec, dict):
        raise ValueError('Assembly spec must be an object')
    edl = json.loads(json.dumps(edl, ensure_ascii=False, allow_nan=False))
    spec = json.loads(json.dumps(spec, ensure_ascii=False, allow_nan=False))
    raw_sources = [row.get('source') for row in edl]
    if isinstance(spec.get('post_audio', []), list):
        raw_sources += [row.get('source') for row in spec.get('post_audio', []) if isinstance(row, dict)]
    source_hashes = {str(_regular_source(source)): _digest(_regular_source(source)) for source in raw_sources}
    plan = build_headless_plan(edl, spec, probe_fn=probe_fn)
    if any(_digest(path) != digest for path, digest in source_hashes.items()):
        raise ValueError('Source media changed while preparing the headless plan')
    if (root / 'work').is_symlink():
        raise ValueError('Core work directory must not be a symlink')
    job = root / 'work' / ('workflow-' + uuid.uuid4().hex)
    job.mkdir(parents=True, exist_ok=False)
    _write_new(job / 'plan.json', plan)
    _write_new(job / 'inputs.json', {'edl': edl, 'spec': spec, 'source_sha256': source_hashes,
                                   'authorization_sha256': approval_hash,
                                   'license_sha256': LICENSE_SHA256})
    plan_hash = _digest(job / 'plan.json')
    commands = []
    env = dict(os.environ, JIANYING_HEADLESS_ROOT=str(root), PYTHONDONTWRITEBYTECODE='1')
    for key in list(env):
        if key.startswith('PYTHON') and key != 'PYTHONDONTWRITEBYTECODE':
            del env[key]
    def execute(arguments):
        # Recheck before every launch, including the doctor and verifier.
        _verify_core(root)
        if _digest(job / 'plan.json') != plan_hash or any(_digest(p) != h for p, h in source_hashes.items()):
            raise ValueError('Frozen plan or source media changed before execution')
        command = [sys.executable, '-E', '-s', '-B', *map(str, arguments)]
        commands.append(command)
        result = runner(command) if runner is not None else subprocess.run(
            command, cwd=str(root), env=env, capture_output=True, text=True, timeout=900)
        number = len(commands)
        if result is not None:
            code = result.get('returncode', 0) if isinstance(result, dict) else result.returncode
            stdout = result.get('stdout', '') if isinstance(result, dict) else result.stdout
            stderr = result.get('stderr', '') if isinstance(result, dict) else result.stderr
            (job / ('command-%02d.stdout.log' % number)).write_text(stdout or '', encoding='utf-8')
            (job / ('command-%02d.stderr.log' % number)).write_text(stderr or '', encoding='utf-8')
            if code:
                raise ValueError('Pinned core command failed (%s): %s' % (code, (stderr or '')[-2000:]))
    build, export = job / 'build', job / 'export'
    try:
        if backend == 'native':
            entry = root / 'skills/yichen-jianying-edit/scripts/headless_draft.py'
            execute([entry, 'doctor'])
            execute([entry, 'build', '--plan', job / 'plan.json', '--out', build])
            execute([entry, 'verify-build', '--build', build])
            execute([entry, 'export', '--backend', 'native', '--build', build, '--out', export])
        else:
            # The wrapper dispatches build by OS, so directly use the reviewed
            # public portable CLI on Linux/macOS rather than pretending to be Windows.
            entry = root / 'engine/windows_portable.py'
            execute([entry, 'doctor'])
            execute([entry, 'build', '--plan', job / 'plan.json', '--out', build])
            execute([entry, 'verify-build', '--build', build])
            execute([root / 'engine/windows_export.py', '--build', build, '--out', export])
        receipt_bytes = (export / 'result.json').read_bytes()
        receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
        result = json.loads(receipt_bytes)
        expected_schema = 'jy14-native-export/v1' if backend == 'native' else 'jy14-ffmpeg-export/v2'
        if (result.get('schema') != expected_schema or result.get('status') != 'encoded-and-decoded'
                or result.get('full_decode_passed') is not True
                or result.get('source_build_unchanged') is not True):
            raise ValueError('Core did not provide successful unchanged-build/full-decode evidence')
        if backend != 'native' and (result.get('backend') != 'windows-ffmpeg'
                                    or result.get('native_editable_draft') is not False):
            raise ValueError('Portable renderer identity is invalid')
        rendered = export / 'render.mp4'
        native_audio = any((probe_fn or probe_media)(row['source']).get('audio_streams', 0) for row in edl)
        verified = verify_mp4(rendered, edl, spec, probe_fn=probe_fn, require_audio=native_audio)
        if result.get('output_sha256') != verified['output_sha256']:
            raise ValueError('Export bytes differ from core result hash')
        execute([entry, 'verify-build', '--build', build])
        build_record = _read(build / 'build.json')
        if build_record.get('schema') != ('jy14-headless-build/v1' if backend == 'native' else
                                         'jy14-windows-render-build/v1'):
            raise ValueError('Editable project has an unexpected schema')
        relative_editable = Path('draft') if backend == 'native' else Path('render/render-timeline.json')
        if not (build / relative_editable).exists():
            raise ValueError('Editable project artifact is missing')
        # Deliver the verified owned-media project alongside the final MP4.
        output.parent.mkdir(parents=True, exist_ok=True)
        source_project_files = {}
        for path in sorted(build.rglob('*')):
            if path.is_symlink():
                raise ValueError('Verified project contains a symlink')
            if path.is_file():
                source_project_files[path.relative_to(build).as_posix()] = _digest(path)
        shutil.copytree(build, project, symlinks=False)
        for relative, digest in source_project_files.items():
            if _digest(project / relative) != digest:
                raise ValueError('Delivered project differs from verified build: ' + relative)
        shutil.copyfile(export / 'result.json', project / 'export-receipt.json')
        if _digest(project / 'export-receipt.json') != receipt_hash:
            raise ValueError('Export receipt changed while delivering the project')
        manifest = {'schema': 'jianying-adapter-manifest/1.0', 'executor': 'jianying-headless',
                    'core_commit': PINNED_COMMIT, 'backend': backend,
                    'source_sha256': source_hashes, 'edl': edl, 'spec': spec,
                    'edl_sha256': canonical_json_sha256(edl),
                    'spec_sha256': canonical_json_sha256(spec),
                    'plan_sha256': _digest(project / 'plan.json'),
                    'project_sha256': _digest(project / 'build.json'),
                    'receipt_sha256': receipt_hash, 'output_sha256': verified['output_sha256'],
                    'project_files': dict(source_project_files, **{'export-receipt.json': receipt_hash})}
        _write_new(project / 'adapter-manifest.json', manifest)
        files = []
        for path in sorted(project.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(project).as_posix()
            role = ('adapter-manifest' if relative == 'adapter-manifest.json' else
                    'plan' if relative == 'plan.json' else
                    'receipt' if relative == 'export-receipt.json' else
                    'project' if relative == 'build.json' else 'project_asset')
            files.append({'role': role, 'path': str(path), 'sha256': _digest(path)})
        editing = {'executor': 'jianying-headless', 'backend': backend,
                   'core_commit': PINNED_COMMIT, 'native_editable': backend == 'native',
                   'files': files, 'license_sha256': LICENSE_SHA256,
                   **{key: manifest[key] for key in ('source_sha256', 'edl_sha256', 'spec_sha256',
                      'plan_sha256', 'project_sha256', 'receipt_sha256', 'output_sha256')},
                   'authorization_sha256': approval_hash,
                   'native_ui_acceptance': 'pending' if backend == 'native' else 'not-applicable'}
        with rendered.open('rb') as source, output.open('xb') as destination:
            shutil.copyfileobj(source, destination)
        if _digest(output) != verified['output_sha256']:
            raise ValueError('Delivered MP4 copy differs from verified bytes')
        response = dict(identity, status='CHECKED', assembled=True, output=str(output), **verified,
                        editable_project=str(project / relative_editable), project_root=str(project),
                        project_kind='native-offline-draft' if backend == 'native' else 'portable-json-timeline',
                        native_editable_draft=backend == 'native',
                        native_ui_acceptance='pending' if backend == 'native' else 'not-applicable',
                        native_registered=False, visual_audio_acceptance='pending',
                        full_decode_passed=True, source_build_unchanged=True,
                        work_dir=str(job), core_result=str(export / 'result.json'),
                        authorization_sha256=approval_hash, license_sha256=LICENSE_SHA256,
                        commands=commands, editing=editing)
        _write_new(project / 'adapter-result.json', response)
        return response
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        response = dict(identity, status='FAILED', reasons=[str(error)], work_dir=str(job),
                        partial_artifacts_retained=True, commands=commands,
                        authorization_sha256=approval_hash)
        _write_new(job / 'adapter-failure.json', response)
        return response
