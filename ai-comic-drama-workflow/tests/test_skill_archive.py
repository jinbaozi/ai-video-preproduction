"""Release identity must not depend on editable installation metadata."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    'archive_regression', Path(__file__).resolve().parents[1] / 'scripts' / 'skill_archive.py')
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class SkillArchiveTests(unittest.TestCase):
    def test_install_metadata_cannot_change_release_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'demo'
            root.mkdir()
            (root / 'SKILL.md').write_text('---\nname: demo\nmetadata:\n  version: "1.0.0"\n---\n')
            source = root / 'src' / 'demo'
            source.mkdir(parents=True)
            (source / '__init__.py').write_text('VALUE = 1\n')
            with patch.object(archive, 'ROOT', root), patch.object(archive, 'NAME', 'demo'):
                archive.build(base / 'before')
                for name in ('demo.egg-info', 'demo-1.0.dist-info', '__pycache__'):
                    generated = root / 'src' / name
                    generated.mkdir()
                    (generated / 'metadata.txt').write_text('machine-specific metadata')
                archive.build(base / 'after')
                for suffix in ('.skill', '.skill-manifest.json', '.skill.sha256'):
                    self.assertEqual((base / 'before' / ('demo' + suffix)).read_bytes(),
                                     (base / 'after' / ('demo' + suffix)).read_bytes())
                self.assertEqual(len(archive.files()), 2)
