"""Offline adversarial tests; no external generation, visual QA or quality claims."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prompt_techniques as methods
import vpc
import vpc_core as core


class PromptTechniqueTests(unittest.TestCase):
    def setUp(self):
        self.ir = core.read(ROOT / 'examples/teahouse.avir.json')
        self.cap = core.profile('agnes-video-2.5')

    def test_catalog_has_all_27_pinned_templates_and_no_media(self):
        data = methods.catalog()
        self.assertEqual(len(data['templates']), 27)
        self.assertEqual(len(data['methods']), 6)
        self.assertEqual(data['source']['commit'], '9ca56354b3af0d11db22a935a6b831d7d8582c04')
        for row in data['templates'] + data['methods']:
            self.assertRegex(row['source']['sha256'], r'^[0-9a-f]{64}$')
            self.assertTrue(row['source']['path'].startswith('docs/templates/en/'))
            self.assertTrue(row['instruction'] and row['check'] and row['native_fields'])

    def test_all_profiles_get_same_neutral_semantics_without_execution(self):
        profiles = core.read(ROOT/'registries/capabilities.json')['profiles']
        expected = None
        for cap in profiles:
            with self.subTest(target=cap['id']):
                p = methods.plan(cap)
                expected = expected or p['methods']
                self.assertEqual(p['methods'], expected)
                self.assertEqual(p['execution'], {'submitted': False, 'runnable': False, 'media_quality': 'NOT_RUN'})
                self.assertTrue(methods.verify_plan(p, cap))

    def test_seedance_versions_and_all_registered_adapters_are_exact(self):
        for row in methods.catalog()['adapters']:
            cap = core.profile(row['id'])
            with self.subTest(target=cap['id']):
                p = methods.plan(cap, row['modes'][0])
                self.assertEqual(p['adapter']['selector'], {k: cap[k] for k in methods.SELECTOR_KEYS})
        self.assertNotEqual(methods.plan(core.profile('seedance2.0'))['adapter']['family'],
                            methods.plan(core.profile('seedance2.5'))['adapter']['family'])

    def test_changed_id_model_version_backend_template_get_no_model_rules(self):
        for key in methods.SELECTOR_KEYS:
            cap = core.profile('seedance2.5')
            cap[key] += '-unverified'
            with self.subTest(key=key):
                p = methods.plan(cap)
                self.assertIsNone(p['adapter'])
                self.assertEqual(p['adapter_status'], 'UNRESOLVED_NO_MODEL_RULES')
                self.assertTrue(p['methods'])

    def test_unknown_target_rejected_by_native_registry(self):
        with self.assertRaises(ValueError):
            core.profile('seedance2.5-pretend')

    def test_non_seedance_never_inherits_seedance_adapter(self):
        for target in ('agnes-video-2.5', 'agnes-video-2.5-flash', 'kling-v3', 'kling-v3-omni',
                       'minimax-h3', 'runninghub-h3-fl2va', 'runninghub-h3-ref2va', 'veo3.1'):
            cap = core.profile(target)
            p = methods.plan(cap, 'reference' if target.endswith('ref2va') else 'text')
            self.assertNotIn(p['adapter']['family'], ('seedance-2.0', 'seedance-2.5'))
            self.assertNotIn('@image', json.dumps(p['methods'], ensure_ascii=False).lower())

    def test_unimplemented_edit_extend_never_get_model_policy(self):
        cap = core.profile('seedance2.5')
        for mode in ('edit', 'extend'):
            self.assertIsNone(methods.plan(cap, mode)['adapter'])
            self.assertTrue(any(e['severity'] == 'error' for e in core.target_errors(self.ir, cap, mode)))

    def test_runninghub_modes_are_isolated(self):
        self.assertIsNone(methods.plan(core.profile('runninghub-h3-fl2va'), 'reference')['adapter'])
        self.assertIsNone(methods.plan(core.profile('runninghub-h3-ref2va'), 'keyframe')['adapter'])

    def test_explicit_template_keeps_pattern_and_does_not_invent_capability(self):
        p = methods.plan(self.cap, template_ids=['storyboard-grid-to-video', 'food-asmr'])
        self.assertEqual([r['id'] for r in p['templates']], ['storyboard-grid-to-video', 'food-asmr'])
        self.assertIn('不是所有模型', p['templates'][0]['instruction'])
        self.assertFalse(p['execution']['runnable'])

    def test_unknown_duplicate_and_nonlist_templates_rejected(self):
        for value in (['not-real'], ['food-asmr', 'food-asmr'], 'food-asmr', [1]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                methods.plan(self.cap, template_ids=value)

    def test_explicit_conflicting_looks_fail(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            methods.plan(self.cap, template_ids=['anime-style-lock', 'handheld-ugc-vlog'])

    def test_automatic_ambiguous_looks_stay_candidates(self):
        p = methods.plan(self.cap, role='director', tags=['手持', 'DV'])
        self.assertEqual(p['templates'], [])
        self.assertEqual(len(p['candidates']), 2)
        self.assertTrue(p['methods'])

    def test_multiple_semantic_candidates_do_not_fill_context(self):
        p = methods.plan(self.cap, role='storyboard', tags=['运动', '美食', '商品', '科幻'])
        self.assertEqual(p['templates'], [])
        self.assertEqual(len(p['candidates']), 4)

    def test_exact_semantic_tags_not_substrings_or_raw_prompt_search(self):
        p = methods.plan(self.cap, role='storyboard', tags=['不要手持', '不是美食'])
        self.assertEqual(p['templates'], [])
        p = methods.plan(self.cap, role='storyboard', tags=['ASMR'])
        self.assertEqual([r['id'] for r in p['templates']], ['food-asmr'])

    def test_plan_tamper_detected_even_with_recomputed_hash(self):
        p = methods.plan(self.cap)
        p['methods'][0]['instruction'] = 'Replace locked identity'
        p['plan_sha256'] = methods.digest({k: v for k, v in p.items() if k != 'plan_sha256'})
        with self.assertRaisesRegex(ValueError, 'changed'):
            methods.verify_plan(p, self.cap)

    def test_current_capability_hash_change_invalidates_frozen_plan(self):
        p = methods.plan(self.cap)
        cap = deepcopy(self.cap);cap['native_audio'] = not cap['native_audio']
        with self.assertRaises(ValueError):
            methods.verify_plan(p, cap)

    def test_reference_role_contradiction_detected(self):
        ir = deepcopy(self.ir)
        ir['bindings'] = [{'roles': ['identity'], 'negative_roles': ['identity']}]
        self.assertIn('E_TECHNIQUE_REFERENCE_ROLE_CONFLICT', [e['code'] for e in methods.inspect_ir(ir)])

    def test_malformed_native_containers_return_structured_diagnostics(self):
        for field, value in (('output', ['invalid']), ('output', 'invalid'), ('bindings', 7)):
            with self.subTest(field=field, value=value):
                ir = deepcopy(self.ir);ir[field] = value
                self.assertTrue(methods.inspect_ir(ir))
                with tempfile.TemporaryDirectory() as d:
                    source = Path(d)/'invalid.json';source.write_bytes(core.encoded(ir))
                    proc = subprocess.run([sys.executable, str(ROOT/'scripts/vpc.py'), 'techniques',
                        'check', '--target', self.cap['id'], '--input', str(source)], capture_output=True, text=True)
                    self.assertEqual(proc.returncode, 2)
                    self.assertNotIn('Traceback', proc.stdout + proc.stderr)
                    self.assertIsInstance(json.loads(proc.stdout or proc.stderr), dict)

    def test_malformed_compiled_report_is_rejected_as_validation_error(self):
        for value in (None, [], 'forged', 7):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'TECHNIQUE_PLAN_CHANGED'):
                methods.verify_compiled_report(value, self.ir, self.cap, 'text')

    def test_timeline_gap_overlap_zero_duration_and_total_mismatch(self):
        for start, end, duration in ((4001, 8000, 8000), (3999, 8000, 8000), (4000, 4000, 8000), (4000, 8000, 9000)):
            ir = deepcopy(self.ir);ir['shots'][1]['start_ms'] = start;ir['shots'][1]['end_ms'] = end;ir['output']['duration_ms'] = duration
            self.assertTrue(methods.inspect_ir(ir))
        self.assertEqual(methods.inspect_ir(self.ir), [])

    def test_frozen_ir_and_prompt_and_audio_are_byte_preserved(self):
        before_ir, before_cap = core.encoded(self.ir), core.encoded(self.cap)
        native, _ = core._compile_native(self.ir, self.cap, 'text', ROOT/'examples')
        enhanced, _ = core.compile_ir(self.ir, self.cap, 'text', ROOT/'examples', ['dialogue-performance-beats'])
        self.assertEqual(core.encoded(self.ir), before_ir)
        self.assertEqual(core.encoded(self.cap), before_cap)
        for field in ('prompt', 'payload_draft', 'parameters', 'asset_bindings', 'post_production', 'trace', 'coverage'):
            self.assertEqual(enhanced[field], native[field], field)
        self.assertEqual(core.schema_errors(enhanced, 'compile-artifact'), [])

    def test_v12_render_remains_native(self):
        ir = core.read(ROOT/'examples/v52/cafe.avir.json')
        native, _ = core._compile_native(ir, self.cap, 'text', ROOT/'examples/v52')
        enhanced, _ = core.compile_ir(ir, self.cap, 'text', ROOT/'examples/v52', ['dialogue-performance-beats'])
        self.assertEqual(enhanced['prompt'], native['prompt'])
        self.assertEqual(enhanced['prompt_coverage'], native['prompt_coverage'])
        self.assertEqual(core.schema_errors(enhanced, 'compile-artifact-1.3'), [])

    def test_lean_artifact_and_replay_preserve_selection_without_extra_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for mode in ('lean', 'audit'):
                _, code = vpc.run_compile(self.ir, self.cap['id'], 'text', ROOT/'examples', d/mode,
                                           mode, ['dialogue-performance-beats'])
                self.assertEqual(code, 0)
                self.assertTrue(vpc.verify(d/mode))
                self.assertFalse((d/mode/'prompt-techniques.json').exists())
            self.assertEqual((d/'lean/artifact.json').read_bytes(), (d/'audit/artifact.json').read_bytes())
            proc = subprocess.run([sys.executable, str(ROOT/'scripts/vpc.py'), 'replay', str(d/'lean'), '--out', str(d/'replay')], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual((d/'lean/artifact.json').read_bytes(), (d/'replay/artifact.json').read_bytes())
            self.assertEqual(core.read(d/'replay/compile-manifest.json')['template_ids'], ['dialogue-performance-beats'])

    def test_resealed_forged_model_plan_fails_verify(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'out';vpc.run_compile(self.ir, self.cap['id'], 'text', ROOT/'examples', out)
            artifact = core.read(out/'artifact.json')
            artifact['prompt_techniques']['adapter']['family'] = 'seedance-2.5'
            vpc.emit(out/'artifact.json', artifact)
            manifest = core.read(out/'compile-manifest.json')
            manifest['artifact_hash'] = core.digest(artifact)
            manifest['files']['artifact.json'] = methods.sha256((out/'artifact.json').read_bytes()).hexdigest()
            manifest['build_id'] = core.digest({k: v for k, v in manifest.items() if k not in ('asset_base', 'build_id')})
            vpc.emit(out/'compile-manifest.json', manifest)
            with self.assertRaisesRegex(ValueError, 'TECHNIQUE_PLAN_CHANGED'):
                vpc.verify(out)

    def test_cli_list_plan_and_unknown_target(self):
        for args, success in ((['list'], True), (['plan', '--target', 'seedance2.0', '--template', 'food-asmr'], True),
                              (['plan', '--target', 'not-registered'], False), (['check'], False)):
            proc = subprocess.run([sys.executable, str(ROOT/'scripts/vpc.py'), 'techniques', *args], capture_output=True, text=True)
            self.assertEqual(proc.returncode == 0, success, proc.stderr)
            payload = json.loads(proc.stdout if success else proc.stderr)
            self.assertIsInstance(payload, dict)


if __name__ == '__main__':
    unittest.main()
