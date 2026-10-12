"""Route, provenance and native compile regression. No visual quality claim."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prompt_techniques as pt
import vpc
import vpc_core as core


class NaturalFaceRealismTests(unittest.TestCase):
    def test_plan_loads_by_file_path_without_compiler_on_sys_path(self):
        script = (
            "import importlib.util; "
            f"spec=importlib.util.spec_from_file_location('isolated_methods', {str(ROOT / 'scripts/prompt_techniques.py')!r}); "
            "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
            "plan=module.plan(role='image-prompt',tags=['真人感']); "
            "assert [t['id'] for t in plan['templates']]==['natural-face-realism']"
        )
        result = subprocess.run([sys.executable, '-I', '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_positive_tags_route_all_intended_roles_and_negative_tags_do_not(self):
        for role in ('director', 'art', 'storyboard', 'image-prompt', 'avir', 'compile-review'):
            plan = pt.plan(role=role, tags=['真人感'])
            self.assertEqual([t['id'] for t in plan['templates']], ['natural-face-realism'])
            self.assertEqual(plan['templates'][0]['source']['kind'], 'local_user_analysis')
            self.assertFalse(plan['execution']['submitted'])
            self.assertEqual(plan['execution']['media_quality'], 'NOT_RUN')
        for tags in ([], ['不要真人感'], ['不是写实人像'], ['水墨']):
            self.assertNotIn('natural-face-realism', [t['id'] for t in pt.plan(tags=tags)['templates']])

    def test_detail_method_can_coexist_with_approved_handheld_look(self):
        plan = pt.plan(role='director', tags=['真人感', '手持'])
        self.assertEqual({t['id'] for t in plan['templates']}, {'natural-face-realism', 'handheld-ugc-vlog'})
        self.assertEqual(plan['candidates'], [])

    def test_local_note_missing_tampered_or_escaping_path_blocks_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('registries', 'references', 'scripts'):
                shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
            source = root / 'references/natural-face-realism.md'
            original = source.read_bytes()
            source.write_bytes(original + b'\nChanged')
            with self.assertRaisesRegex(ValueError, 'source bytes'):
                pt.plan(template_ids=['natural-face-realism'], root=root)
            source.unlink()
            with self.assertRaises(ValueError):
                pt.catalog(root)
            source.write_bytes(original)
            registry = root / 'registries/prompt-techniques.json'
            data = core.read(registry)
            row = next(t for t in data['templates'] if t['id'] == 'natural-face-realism')
            row['source']['path'] = '../outside.md'
            registry.write_bytes(core.encoded(data))
            with self.assertRaises(ValueError):
                pt.catalog(root)

    def test_selected_method_preserves_native_ir_prompt_audio_parameters_and_replay(self):
        cap = core.profile('agnes-video-2.5')
        ir = core.read(ROOT / 'examples/teahouse.avir.json')
        before = core.encoded(ir)
        native, _ = core._compile_native(ir, cap, 'text', ROOT / 'examples')
        enhanced, _ = core.compile_ir(ir, cap, 'text', ROOT / 'examples', ['natural-face-realism'])
        self.assertEqual(before, core.encoded(ir))
        for key in ('prompt', 'payload_draft', 'parameters', 'asset_bindings', 'post_production', 'trace', 'coverage'):
            self.assertEqual(native[key], enhanced[key], key)
        self.assertTrue(pt.verify_compiled_report(enhanced['prompt_techniques'], ir, cap, 'text'))
        with tempfile.TemporaryDirectory() as folder:
            out, replay = Path(folder) / 'first', Path(folder) / 'replay'
            _, code = vpc.run_compile(ir, cap['id'], 'text', ROOT / 'examples', out, 'lean', ['natural-face-realism'])
            self.assertEqual(code, 0)
            self.assertTrue(vpc.verify(out))
            self.assertIn('references/natural-face-realism.md', core.read(out / 'compile-manifest.json')['runtime_files'])
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/vpc.py'), 'replay', str(out), '--out', str(replay)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((out / 'artifact.json').read_bytes(), (replay / 'artifact.json').read_bytes())
            self.assertEqual(core.read(replay / 'compile-manifest.json')['template_ids'], ['natural-face-realism'])


if __name__ == '__main__':
    unittest.main()
