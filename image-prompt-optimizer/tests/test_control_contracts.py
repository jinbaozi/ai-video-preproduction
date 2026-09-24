"""Image-only install validates edit contracts without a sibling video runtime."""
from pathlib import Path
import sys
import unittest
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from shot_control.control_lowering import validate_delta


class ControlContractsTests(unittest.TestCase):
    def test_native_control_package_without_sibling_runtime(self):
        from shot_control.control_plan import build
        from shot_control.package import verify_package
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            build(root/'fixtures/control.avir.json', tmp)
            result = verify_package(tmp)
            self.assertEqual(result['plan']['shot_ids'], ['S1', 'S2', 'S3'])
            self.assertTrue(result['requests'])
            from shot_control.repair import plan_repairs
            repair = plan_repairs(tmp, tmp, Path(tmp)/'artifact-manifest.json')
            self.assertEqual(repair['status'], 'UNCHANGED')
            self.assertEqual(repair['tasks'], [])

    def test_standalone_edit_contract_and_conflict(self):
        value = {'schema':'edit-delta/0.1','keyframe_id':'K1',
                 'source':{'kind':'avir/1.2','path':'source.json','sha256':'0'*64},
                 'base_asset_sha256':'1'*64,'master_anchor_ids':['identity-master','scene-master'],
                 'allow_changes':['/A/head/gaze'],'preserve':['/A/identity','/scene','/camera'],
                 'acceptance':['保持身份和机位，只核对指定视线变化']}
        self.assertEqual(validate_delta(value)['status'], 'STATIC_VALID')
        value['preserve'].append('/A/head')
        with self.assertRaises(ValueError): validate_delta(value)


if __name__ == '__main__': unittest.main()
