"""Adapter tests never execute the downloaded Jianying Headless repository."""
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_comic_drama_workflow import jianying as j
from ai_comic_drama_workflow.assembly import _probe


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.core = self.root / 'core'
        self.core.mkdir()
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'local fixture video, not an actual MP4')
        self.audio = self.root / 'music.wav'
        self.audio.write_bytes(b'local fixture audio')
        self.output = self.root / 'delivered' / 'final.mp4'
        self.spec = {'width': 64, 'height': 64, 'fps': 30}
        self.edl = [{'take_id': 'TAKE_1', 'source': str(self.source), 'src_in_frame': 6,
                     'src_out_frame': 36, 'fps': 30, 'record_in_frame': 0}]
        self.approval = {'decision': 'APPROVED', 'action': 'execute-jianying-headless',
                         'core_commit': j.PINNED_COMMIT, 'backend': 'portable-ffmpeg',
                         'usage': 'personal-noncommercial', 'license_accepted': True,
                         'actor': 'test user', 'evidence': 'test-only explicit approval'}
        self.calls = []
        self.export_change = None
        self.video_audio = 1
        self.output_frames = 30

    def test_unsupported_parameters_fail_closed(self):
        for spec in (dict(self.spec, transition='fade'), dict(self.spec, preserve_native_audio=False),
                     dict(self.spec, require_audio=1)):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                j.build_headless_plan(self.edl, spec, probe_fn=self.probe)
        for field, value in [('volume', 0), ('transition', 'fade'), ('speed', True)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                j.build_headless_plan([dict(self.edl[0], **{field: value})], self.spec, probe_fn=self.probe)

    def probe(self, path):
        if Path(path).suffix == '.wav':
            return {'duration_ms': 2000, 'duration_us': 2_000_000,
                    'audio_streams': 1, 'video_streams': 0}
        output = Path(path).name in ('render.mp4', 'final.mp4')
        return {'width': 64, 'height': 64, 'fps': 30, 'frames': self.output_frames if output else 60,
                'duration_ms': 1000 if output else 2000, 'duration_us': 1_000_000 if output else 2_000_000,
                'audio_streams': self.video_audio, 'video_streams': 1,
                'codec_name': 'h264', 'pix_fmt': 'yuv420p'}

    def setup_report(self, core_root, backend):
        return {'status': 'READY_FOR_AUTHORIZATION', 'core_root': str(self.core), 'reasons': []}

    def runner(self, command):
        self.calls.append(command)
        if 'build' in command:
            build = Path(command[command.index('--out') + 1])
            plan = Path(command[command.index('--plan') + 1])
            native = self.approval['backend'] == 'native'
            build.mkdir()
            shutil.copyfile(plan, build / 'plan.json')
            write(build / 'build.json', {'schema': 'jy14-headless-build/v1' if native else
                                        'jy14-windows-render-build/v1'})
            write(build / ('draft/draft_info.json' if native else 'render/render-timeline.json'),
                  {'schema': 'fixture-only', 'tracks': json.loads(plan.read_text())['tracks']})
            media = build / ('draft/Resources/video.mp4' if native else 'render/Resources/video.mp4')
            media.parent.mkdir(exist_ok=True)
            shutil.copyfile(self.source, media)
        elif '--out' in command:
            export = Path(command[command.index('--out') + 1])
            export.mkdir()
            (export / 'render.mp4').write_bytes(b'test-only fake render')
            native = self.approval['backend'] == 'native'
            receipt = {'schema': 'jy14-native-export/v1' if native else 'jy14-ffmpeg-export/v2',
                       'backend': 'native' if native else 'windows-ffmpeg',
                       'native_editable_draft': native, 'status': 'encoded-and-decoded',
                       'full_decode_passed': True, 'source_build_unchanged': True,
                       'output_sha256': sha(export / 'render.mp4')}
            if self.export_change:
                self.export_change(receipt, export)
            write(export / 'result.json', receipt)
        return {'returncode': 0, 'stdout': '{}', 'stderr': ''}

    def assemble(self, **kwargs):
        options = dict(core_root=self.core, authorization=self.approval,
                       backend=self.approval['backend'], runner=self.runner, probe_fn=self.probe)
        options.update(kwargs)
        with patch.object(j, 'inspect_setup', side_effect=self.setup_report), \
             patch.object(j, '_verify_core', return_value={'commit': j.PINNED_COMMIT}):
            return j.assemble_jianying(self.edl, self.output, self.spec, **options)

    def test_missing_approval_never_inspects_or_runs_core(self):
        with patch.object(j, 'inspect_setup') as inspect:
            result = j.assemble_jianying(self.edl, self.output, self.spec, runner=self.runner)
        self.assertEqual(result['status'], 'BLOCKED_AUTHORIZATION')
        inspect.assert_not_called()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output.parent.exists())

    def test_commit_backend_actor_license_and_usage_must_be_explicit(self):
        for key, value in [('core_commit', 'wrong'), ('backend', 'native'), ('actor', ''),
                           ('license_accepted', False), ('usage', 'anything'), ('evidence', '')]:
            approval = dict(self.approval, **{key: value})
            with self.subTest(key=key):
                result = self.assemble(authorization=approval, backend='portable-ffmpeg')
                self.assertEqual(result['status'], 'BLOCKED_AUTHORIZATION')
        self.assertFalse(self.calls)

    def test_commercial_requires_specific_written_permission(self):
        self.approval['usage'] = 'commercial'
        result = self.assemble(usage='commercial')
        self.assertEqual(result['status'], 'BLOCKED_AUTHORIZATION')
        self.assertIn('copyright-holder', result['reasons'][0])
        self.assertFalse(self.calls)
        self.approval['commercial_permission'] = {
            'scope': 'commercial', 'copyright_holder': 'test copyright holder',
            'written_permission': 'test-only specific written permission'}
        self.assertEqual(self.assemble(usage='commercial')['status'], 'CHECKED')

    def test_static_setup_failure_does_not_invoke_core(self):
        with patch.object(j, 'inspect_setup', return_value={'status': 'BLOCKED_SETUP', 'reasons': ['missing']}):
            result = j.assemble_jianying(self.edl, self.output, self.spec,
                                         authorization=self.approval, runner=self.runner)
        self.assertEqual(result['status'], 'BLOCKED_SETUP')
        self.assertFalse(self.calls)

    def test_plan_compiles_actual_trims_original_audio_and_post_audio(self):
        self.spec['post_audio'] = [{'source': str(self.audio), 'sha256': sha(self.audio),
                                   'start_ms': 200, 'gain': 0.5}]
        plan = j.build_headless_plan(self.edl, self.spec, probe_fn=self.probe)
        self.assertEqual(plan['schema'], 'jy14-headless-plan/v1')
        video = plan['tracks'][0]['segments'][0]
        self.assertEqual(video['source_start_us'], 200000)
        self.assertEqual(video['duration_us'], 1_000_000)
        self.assertEqual(video['source_duration_us'], 1_000_000)
        self.assertEqual(video['volume'], 1)
        audio = plan['tracks'][1]['segments'][0]
        self.assertEqual((audio['start_us'], audio['duration_us'], audio['volume']), (200000, 800000, .5))

    def test_microsecond_rounding_preserves_frame_boundary_continuity(self):
        self.edl[0]['src_in_frame'], self.edl[0]['src_out_frame'] = 0, 1
        self.edl.append(dict(self.edl[0], src_in_frame=1, src_out_frame=3, record_in_frame=1))
        plan = j.build_headless_plan(self.edl, self.spec, probe_fn=self.probe)
        first, second = plan['tracks'][0]['segments']
        self.assertEqual(first['start_us'] + first['duration_us'], second['start_us'])
        self.assertEqual(second['start_us'] + second['duration_us'], 100000)

    def test_rejects_gaps_overlap_retime_fractional_fps_boolean_and_source_overrun(self):
        cases = [('record_in_frame', 2), ('src_out_frame', 61), ('speed', 2),
                 ('record_in_frame', True), ('fps', 29.97)]
        for key, value in cases:
            edl = copy.deepcopy(self.edl)
            edl[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                j.build_headless_plan(edl, self.spec, probe_fn=self.probe)
        self.spec['fps'] = 29.97
        with self.assertRaises(ValueError):
            j.build_headless_plan(self.edl, self.spec, probe_fn=self.probe)

    def test_rejects_implicit_resize_and_missing_source_frame_evidence(self):
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            j.build_headless_plan(self.edl, dict(self.spec, width=128), probe_fn=self.probe)
        with self.assertRaisesRegex(ValueError, 'frame count'):
            j.build_headless_plan(self.edl, self.spec,
                                 probe_fn=lambda p: dict(self.probe(p), frames=None))

    def test_rejects_changed_post_audio_hash_or_unsupported_gain(self):
        self.spec['post_audio'] = [{'source': str(self.audio), 'sha256': 'bad', 'start_ms': 0}]
        with self.assertRaisesRegex(ValueError, 'hash'):
            j.build_headless_plan(self.edl, self.spec, probe_fn=self.probe)
        self.spec['post_audio'][0].update(sha256=sha(self.audio), gain=float('nan'))
        with self.assertRaisesRegex(ValueError, 'gain'):
            j.build_headless_plan(self.edl, self.spec, probe_fn=self.probe)

    def test_required_audio_is_not_replaced_with_fake_silence(self):
        self.video_audio = 0
        self.spec['require_audio'] = True
        with self.assertRaisesRegex(ValueError, 'Required audio is absent'):
            j.build_headless_plan(self.edl, self.spec, probe_fn=self.probe)

    def test_portable_execution_emits_real_entrypoints_and_integrity_manifest(self):
        result = self.assemble()
        self.assertEqual(result['status'], 'CHECKED', result)
        self.assertEqual(result['tool'], 'jianying')
        self.assertEqual(result['renderer_backend'], 'windows-ffmpeg')
        self.assertFalse(result['native_editable_draft'])
        self.assertEqual(result['project_kind'], 'portable-json-timeline')
        self.assertEqual(result['output_sha256'], sha(self.output))
        self.assertEqual(set(result['probe']), {'width', 'height', 'fps', 'duration_ms',
                                               'aspect', 'audio_streams', 'frames'})
        self.assertEqual(len(self.calls), 5)
        self.assertTrue(self.calls[0][4].endswith('engine/windows_portable.py'))
        self.assertTrue(self.calls[3][4].endswith('engine/windows_export.py'))
        self.assertFalse(any('publish' in command for command in self.calls))
        editing = result['editing']
        self.assertEqual(editing['core_commit'], j.PINNED_COMMIT)
        self.assertFalse(editing['native_editable'])
        self.assertTrue({'project', 'plan', 'receipt', 'adapter-manifest'} <=
                        {row['role'] for row in editing['files']})
        self.assertTrue(any(row['path'].endswith('Resources/video.mp4') for row in editing['files']))
        for row in editing['files']:
            self.assertTrue(Path(row['path']).is_absolute())
            self.assertEqual(row['sha256'], sha(row['path']))

    def test_adapter_manifest_binds_exact_inputs_project_receipt_and_output(self):
        result = self.assemble()
        editing = result['editing']
        files = {row['role']: row for row in editing['files'] if row['role'] != 'project_asset'}
        manifest = json.loads(Path(files['adapter-manifest']['path']).read_text())
        self.assertEqual(manifest['schema'], 'jianying-adapter-manifest/1.0')
        self.assertEqual(manifest['edl'], self.edl)
        self.assertEqual(manifest['spec'], self.spec)
        self.assertEqual(manifest['edl_sha256'], j.canonical_json_sha256(self.edl))
        self.assertEqual(manifest['spec_sha256'], j.canonical_json_sha256(self.spec))
        self.assertEqual(manifest['source_sha256'], {str(self.source): sha(self.source)})
        self.assertEqual(manifest['output_sha256'], result['output_sha256'])
        for kind in ('project', 'plan', 'receipt'):
            self.assertEqual(manifest[kind + '_sha256'], sha(files[kind]['path']))
        for relative, digest in manifest['project_files'].items():
            self.assertEqual(digest, sha(Path(result['project_root']) / relative))
        self.assertEqual(Path(files['receipt']['path']).read_bytes(),
                         Path(result['core_result']).read_bytes())
        self.assertNotEqual(manifest['edl_sha256'],
                            j.canonical_json_sha256([dict(self.edl[0], src_in_frame=5)]))
        self.assertNotEqual(manifest['spec_sha256'], j.canonical_json_sha256(dict(self.spec, width=128)))

    def test_native_uses_wrapper_and_never_claims_ui_acceptance(self):
        self.approval['backend'] = 'native'
        result = self.assemble()
        self.assertEqual(result['status'], 'CHECKED', result)
        self.assertTrue(result['native_editable_draft'])
        self.assertEqual(result['native_ui_acceptance'], 'pending')
        self.assertFalse(result['native_registered'])
        self.assertIn('--backend', self.calls[3])
        self.assertTrue(self.calls[0][4].endswith('scripts/headless_draft.py'))
        self.assertFalse(any('publish' in command for command in self.calls))

    def test_failed_core_command_keeps_logs_and_never_falls_back(self):
        result = self.assemble(runner=lambda cmd: {'returncode': 2, 'stdout': '', 'stderr': 'bad runtime'})
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(len(result['commands']), 1)
        self.assertTrue((Path(result['work_dir']) / 'command-01.stderr.log').is_file())
        self.assertFalse(self.output.exists())

    def test_fake_native_identity_or_failed_receipt_cannot_pass(self):
        for key, value in [('native_editable_draft', True), ('full_decode_passed', False),
                           ('source_build_unchanged', False), ('status', 'preparing'),
                           ('schema', 'handoff-only'), ('output_sha256', 'incorrect')]:
            with self.subTest(key=key):
                self.export_change = lambda r, p, key=key, value=value: r.update({key: value})
                result = self.assemble()
                self.assertEqual(result['status'], 'FAILED', result)
                self.assertFalse(self.output.exists())

    def test_decoded_frame_count_and_native_audio_are_required(self):
        self.output_frames = 29
        result = self.assemble()
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('frame count', result['reasons'][0])
        self.output_frames = 30
        probe = self.probe
        result = self.assemble(probe_fn=lambda p: dict(probe(p), audio_streams=0)
                               if Path(p).name == 'render.mp4' else probe(p))
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('audio', result['reasons'][0])

    def test_source_mutation_between_core_commands_stops_delivery(self):
        def mutate(receipt, export):
            self.source.write_bytes(b'changed source bytes')
        self.export_change = mutate
        result = self.assemble()
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('changed before execution', result['reasons'][0])
        self.assertFalse(self.output.exists())

    def test_existing_destination_never_overwritten(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.assemble()
        self.assertEqual(self.output.read_bytes(), b'keep')
        self.assertFalse(self.calls)

    def test_setup_missing_core_and_native_host_are_actionable(self):
        with patch.dict('os.environ', {}, clear=True):
            result = j.inspect_setup()
        self.assertEqual(result['status'], 'BLOCKED_SETUP')
        self.assertIn('JIANYING_HEADLESS_ROOT', result['reasons'][0])
        with patch.object(j, '_verify_core', return_value={}), \
             patch.object(j.platform, 'system', return_value='Linux'):
            result = j.inspect_setup(self.core, backend='native')
        self.assertTrue(any('Apple Silicon' in reason for reason in result['reasons']))
        self.assertFalse(result['runtime_executed'])


class InstallerTests(unittest.TestCase):
    def test_install_requires_separate_destination_scoped_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'installed-core'
            calls = []
            result = j.install_core(destination, runner=lambda cmd: calls.append(cmd))
            self.assertEqual(result['status'], 'BLOCKED_AUTHORIZATION')
            self.assertFalse(calls)
            approval = {'decision': 'APPROVED', 'action': 'execute-jianying-headless',
                        'core_commit': j.PINNED_COMMIT, 'backend': 'portable-ffmpeg',
                        'usage': 'personal-noncommercial', 'license_accepted': True,
                        'actor': 'fixture', 'evidence': 'fixture-only approval',
                        'destination': str(destination)}
            result = j.install_core(destination, approval, runner=lambda cmd: calls.append(cmd))
            self.assertEqual(result['status'], 'BLOCKED_AUTHORIZATION')
            approval.update(action='install-jianying-headless', destination='/wrong')
            result = j.install_core(destination, approval, runner=lambda cmd: calls.append(cmd))
            self.assertEqual(result['status'], 'BLOCKED_AUTHORIZATION')
            self.assertFalse(calls)

    def test_install_fetches_only_exact_pin_and_never_executes_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'installed-core'
            calls = []
            approval = {'decision': 'APPROVED', 'action': 'install-jianying-headless',
                        'core_commit': j.PINNED_COMMIT, 'backend': 'portable-ffmpeg',
                        'usage': 'personal-noncommercial', 'license_accepted': True,
                        'actor': 'fixture', 'evidence': 'fixture-only approval',
                        'destination': str(destination)}
            with patch.object(j, '_verify_core', return_value={'commit': j.PINNED_COMMIT}):
                result = j.install_core(destination, approval, runner=lambda cmd: calls.append(cmd))
            self.assertEqual(result['status'], 'SOURCE_INSTALLED')
            self.assertFalse(result['runtime_executed'])
            self.assertEqual(len(calls), 4)
            self.assertTrue(all(Path(cmd[0]).name == 'git' for cmd in calls))
            self.assertEqual(calls[2][-4:], ['fetch', '--depth=1', 'origin', j.PINNED_COMMIT])
            self.assertEqual(calls[3][-3:], ['checkout', '--detach', j.PINNED_COMMIT])
            self.assertIn(j.CORE_REPOSITORY, calls[1])


@unittest.skipUnless(shutil.which('git'), 'git unavailable')
class StaticPinTests(unittest.TestCase):
    def test_tracked_bytes_and_untracked_imports_are_verified_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / 'project.json', {'schema': 'jianying-headless-project/v1', 'id': 'jianying-headless'})
            (root / 'LICENSE').write_text('test fixture license')
            (root / 'engine').mkdir()
            (root / 'engine/test.py').write_text('# inert fixture, never executed\n')
            subprocess.run(['git', 'init', '-q', tmp], check=True)
            subprocess.run(['git', '-C', tmp, 'add', '.'], check=True)
            subprocess.run(['git', '-C', tmp, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                            'commit', '-qm', 'inert fixture'], check=True)
            commit = subprocess.check_output(['git', '-C', tmp, 'rev-parse', 'HEAD'], text=True).strip()
            with patch.object(j, 'PINNED_COMMIT', commit), patch.object(j, 'LICENSE_SHA256', sha(root / 'LICENSE')):
                self.assertEqual(j._verify_core(root)['tracked_files_verified'], 3)
                (root / 'engine/untracked.py').write_text('# never executed')
                with self.assertRaisesRegex(ValueError, 'Untracked executable'):
                    j._verify_core(root)
                (root / 'engine/untracked.py').unlink()
                (root / 'engine/test.py').write_text('# changed')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    j._verify_core(root)
            with self.assertRaisesRegex(ValueError, 'pinned commit'):
                j._verify_core(root)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools unavailable')
class FFmpegEvidenceTests(unittest.TestCase):
    def test_real_mp4_probe_audio_frames_hash_and_plan_without_upstream_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'generated.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=30:d=1',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(output)],
                           capture_output=True, check=True, timeout=60)
            edl = [{'take_id': 'SYNTHETIC', 'source': str(output), 'src_in_frame': 0,
                    'src_out_frame': 30, 'fps': 30, 'record_in_frame': 0}]
            spec = {'width': 64, 'height': 64, 'fps': 30, 'require_audio': True}
            plan = j.build_headless_plan(edl, spec)
            self.assertEqual(plan['tracks'][0]['segments'][0]['duration_us'], 1_000_000)
            result = j.verify_mp4(output, edl, spec)
            self.assertEqual(result['probe']['frames'], 30)
            self.assertEqual(result['probe']['audio_streams'], 1)
            self.assertEqual(result['output_sha256'], sha(output))
            self.assertEqual(result['probe'], _probe(output))
            with self.assertRaisesRegex(ValueError, 'frame count'):
                j.verify_mp4(output, [dict(edl[0], src_out_frame=29)], spec)


if __name__ == '__main__':
    unittest.main()
