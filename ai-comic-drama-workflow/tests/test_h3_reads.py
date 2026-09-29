"""H3 additions must not inflate unrelated model task contexts."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import zipfile
from ai_comic_drama_workflow.v5 import V5Kernel

ROOT = Path(__file__).resolve().parents[2]

class H3ReadTests(unittest.TestCase):
    def conditions(self, target, kind):
        stub = SimpleNamespace(project={'target':target}, valid=lambda _:False,
            control_applicable=lambda _:False, has_dialogue=lambda _:False)
        return V5Kernel.read_conditions(stub, kind)

    def test_only_h3_compile_related_stages_load_the_router(self):
        for target in ('minimax-h3','runninghub-h3-fl2va','runninghub-h3-ref2va'):
            for kind in ('avir','compile-review','qa'):
                self.assertIn('h3', self.conditions(target,kind))
            for kind in ('canon','visual','storyboard','control'):
                self.assertNotIn('h3', self.conditions(target,kind))
        for target in ('seedance2.5','agnes-video-2.5','kling-v3','unknown'):
            self.assertNotIn('h3',self.conditions(target,'avir'))

    def test_router_is_conditional_and_bundled_source_exists(self):
        module=ROOT/'video-prompt-compiler'
        if module.is_dir():
            manifest=json.loads((module/'references/v5-reads.json').read_text())
            self.assertTrue((module/'references/models/minimax-h3.md').is_file())
        else:
            archive=Path(__file__).resolve().parents[1]/'assets/bundled-skills/video-prompt-compiler.skill'
            with zipfile.ZipFile(archive) as bundle:
                manifest=json.loads(bundle.read('video-prompt-compiler/references/v5-reads.json'))
                self.assertIsNotNone(bundle.getinfo('video-prompt-compiler/references/models/minimax-h3.md'))
        self.assertEqual(manifest['when']['h3'],['references/models/minimax-h3.md'])
        self.assertNotIn('references/models/minimax-h3.md',manifest['always'])
