"""Static contract tests for autonomous media finishing stages."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AutonomousDeliveryContractTests(unittest.TestCase):
    def test_v6_routes_images_through_flow_2k_before_consumers(self):
        graph=json.loads((ROOT/"workflow-v6.json").read_text(encoding="utf-8"))
        nodes={n["id"]:n for n in graph["nodes"]}
        self.assertIn("reference_2k",nodes)
        self.assertIn("board_reference_2k",nodes)
        self.assertIn("reference_2k",nodes["storyboard"]["depends_on"])
        self.assertNotIn("visual_media",nodes["storyboard"]["depends_on"])
        self.assertIn("board_reference_2k",nodes["compile"]["depends_on"])
        self.assertNotIn("board_media",nodes["compile"]["depends_on"])

    def test_v6_requires_jianying_before_whole_acceptance(self):
        graph=json.loads((ROOT/"workflow-v6.json").read_text(encoding="utf-8"))
        nodes={n["id"]:n for n in graph["nodes"]}
        self.assertEqual(nodes["jianying_edit"]["depends_on"],["assembly"])
        self.assertEqual(nodes["whole_acceptance"]["depends_on"],["jianying_edit"])

    def test_skill_exposes_progressive_contracts(self):
        skill=(ROOT/"SKILL.md").read_text(encoding="utf-8")
        for name in ("autonomous-until-blocked.md","flow-2k-reference.md","jianying-postproduction.md"):
            self.assertIn(name,skill)

    def test_no_account_identifier_is_committed(self):
        for path in [
            ROOT/"SKILL.md",
            ROOT/"references"/"flow-2k-reference.md",
            ROOT/"references"/"autonomous-until-blocked.md",
            ROOT/"references"/"jianying-postproduction.md",
        ]:
            text=path.read_text(encoding="utf-8")
            self.assertNotIn("@gmail.com",text)

if __name__=="__main__":
    unittest.main()
