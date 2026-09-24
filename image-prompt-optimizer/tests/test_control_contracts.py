"""Image-only install validates edit contracts without a sibling video runtime."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from shot_control.control_lowering import validate_delta


class ControlContractsTests(unittest.TestCase):
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
