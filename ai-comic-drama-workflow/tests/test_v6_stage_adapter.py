"""Graph task expansion and scope coverage without filesystem or media calls."""
import unittest

from ai_comic_drama_workflow.v6_graph import load_graph
from ai_comic_drama_workflow.v6_stage_adapter import (
    graph_envelope_fields, predecessor_task_ids, slot_for,
)


PROJECT = {"kind": "project", "ids": []}
SCENE_A = {"kind": "scene", "ids": ["S_A"]}
SCENE_B = {"kind": "scene", "ids": ["S_B"]}
ASSET_A = {"kind": "asset", "ids": ["A_A"]}
ASSET_B = {"kind": "asset", "ids": ["A_B"]}


def row(node, scope, task_id, state="ACCEPTED", revision=1, batch=1):
    return {"state": state, "version": 3, "envelope": {
        "node_id": node, "scope": scope, "task_id": task_id,
        "input_revision": revision, "batch": batch,
        "expected_artifacts": [{"slot": slot_for(node, scope, "Output"), "kind": "Output"}],
    }}


class StageAdapterTests(unittest.TestCase):
    def setUp(self):
        self.graph = load_graph()

    def test_project_consumer_requires_every_scene_and_asset(self):
        catalogue = {"storyboard": [PROJECT], "canon": [PROJECT], "director": [PROJECT],
                     "art": [SCENE_A, SCENE_B], "visual_media": [ASSET_A, ASSET_B]}
        rows = [row("canon", PROJECT, "CANON"), row("director", PROJECT, "DIRECTOR"),
                row("art", SCENE_A, "ART_A"), row("art", SCENE_B, "ART_B"),
                row("visual_media", ASSET_A, "VIS_A", state="NOT_APPLICABLE"),
                row("visual_media", ASSET_B, "VIS_B", state="NOT_APPLICABLE")]
        self.assertEqual(predecessor_task_ids(self.graph, "storyboard", PROJECT, rows, catalogue),
                         ["CANON", "DIRECTOR", "ART_A", "ART_B", "VIS_A", "VIS_B"])
        with self.assertRaisesRegex(ValueError, "Missing predecessor task"):
            predecessor_task_ids(self.graph, "storyboard", PROJECT, rows[:-2] + rows[-1:], catalogue)

    def test_cross_scope_edge_needs_explicit_binding(self):
        catalogue = {"visual_prompts": [ASSET_A], "art": [SCENE_A, SCENE_B]}
        rows = [row("art", SCENE_A, "ART_A"), row("art", SCENE_B, "ART_B")]
        with self.assertRaisesRegex(ValueError, "needs frozen scope links"):
            predecessor_task_ids(self.graph, "visual_prompts", ASSET_A, rows, catalogue)
        self.assertEqual(predecessor_task_ids(self.graph, "visual_prompts", ASSET_A, rows,
                                              catalogue, {"art": [SCENE_A]}), ["ART_A"])
        with self.assertRaisesRegex(ValueError, "invalid instance links"):
            predecessor_task_ids(self.graph, "visual_prompts", ASSET_A, rows,
                                 {"visual_prompts": [ASSET_A], "art": [SCENE_A]},
                                 {"art": [SCENE_B]})

    def test_newer_incomplete_predecessor_blocks_old_accepted_result(self):
        catalogue = {"visual_prompts": [ASSET_A], "art": [SCENE_A]}
        rows = [row("art", SCENE_A, "ART_OLD", revision=1),
                row("art", SCENE_A, "ART_NEW", state="RUNNING", revision=2)]
        with self.assertRaisesRegex(ValueError, "not complete"):
            predecessor_task_ids(self.graph, "visual_prompts", ASSET_A, rows, catalogue,
                                 {"art": [SCENE_A]})

    def test_envelope_fields_have_exact_graph_outputs_and_handoff_versions(self):
        catalogue = {"art": [SCENE_A], "canon": [PROJECT], "director": [PROJECT]}
        rows = [row("canon", PROJECT, "CANON"), row("director", PROJECT, "DIRECTOR")]
        output = slot_for("art", SCENE_A, "ArtIR")
        bindings = [{"requirement_id": f"REQ_{index}", "source_slot": source,
                     "source_version": 3, "target_slot": output, "target_pointer": "/contract",
                     "channel": "artifact"}
                    for index, source in enumerate((slot_for("canon", PROJECT, "Output"),
                                                    slot_for("director", PROJECT, "Output")), 1)]
        fields = graph_envelope_fields(self.graph, "art", SCENE_A, "TASK_ART_A", 1,
                                       rows, catalogue, handoff_bindings=bindings)
        self.assertEqual(fields["scope"], SCENE_A)
        self.assertEqual(fields["execution_class"], "professional")
        self.assertEqual(fields["dependencies"], [{"task_id": "CANON"}, {"task_id": "DIRECTOR"}])
        self.assertEqual(fields["expected_artifacts"], [{"slot": output, "kind": "ArtIR",
            "uri_prefix": "runtime/v6/candidates/TASK_ART_A/1/"}])
        self.assertEqual({item["id"] for item in fields["validators"]},
                         {"module_receipt", "native_validator", "handoff"})
        with self.assertRaisesRegex(ValueError, "cover every accepted predecessor output"):
            graph_envelope_fields(self.graph, "art", SCENE_A, "TASK_ART_A", 1,
                                  rows, catalogue, handoff_bindings=bindings[:1])

    def test_slots_encode_ordered_scope_without_collision(self):
        self.assertNotEqual(slot_for("adjacent_acceptance", {"kind": "adjacent_pair", "ids": ["S_A", "S_B"]}, "AdjacentDecision"),
                            slot_for("adjacent_acceptance", {"kind": "adjacent_pair", "ids": ["S_B", "S_A"]}, "AdjacentDecision"))
        self.assertNotEqual(slot_for("art", SCENE_A, "ArtIR"), slot_for("art", SCENE_B, "ArtIR"))


if __name__ == "__main__":
    unittest.main()
