"""V6 graph shape and skip/ordering gates; no media or model calls."""
import copy
import unittest

from ai_comic_drama_workflow.v6_graph import (
    graph_to_mermaid, load_graph, ready_stages, stage_applicability, stage_by_id,
    validate_graph, validate_skip_record,
)


CONTEXT = {
    "delivery": "text-only", "production_target": "none",
    "observation_required": False, "control_required": False,
}


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = load_graph()

    def test_graph_covers_six_skills_and_both_delivery_paths(self):
        skills = {n["locked_skill"] for n in self.graph["nodes"] if n["locked_skill"]}
        self.assertEqual(skills, set(self.graph["locked_skills"]))
        self.assertEqual(len(skills), 6)
        self.assertEqual(self.graph["nodes"][0]["id"], "sources")
        self.assertEqual(self.graph["nodes"][-1]["id"], "video_delivery")
        self.assertEqual(stage_by_id(self.graph, "art")["scope"], "scene")
        self.assertEqual(stage_by_id(self.graph, "adjacent_acceptance")["scope"], "project")
        self.assertEqual(stage_by_id(self.graph, "visual_media")["executor_kind"], "host")
        self.assertEqual(stage_by_id(self.graph, "compile_review")["review"], "none")

    def test_schema_rejects_unknown_fields_and_graph_errors(self):
        altered = copy.deepcopy(self.graph)
        altered["nodes"][0]["unchecked"] = True
        with self.assertRaisesRegex(ValueError, "keys differ"):
            validate_graph(altered)
        altered = copy.deepcopy(self.graph)
        altered["nodes"][1]["depends_on"] = ["video_delivery"]
        with self.assertRaisesRegex(ValueError, "future or cyclic"):
            validate_graph(altered)
        altered = copy.deepcopy(self.graph)
        altered["nodes"][3]["checkers"] = ["fictional_checker"]
        with self.assertRaisesRegex(ValueError, "unknown checker"):
            validate_graph(altered)
        altered = copy.deepcopy(self.graph)
        altered["nodes"][13]["review"] = "independent"
        with self.assertRaisesRegex(ValueError, "cannot recurse"):
            validate_graph(altered)
        altered = copy.deepcopy(self.graph)
        altered["locked_skills"].pop()
        with self.assertRaisesRegex(ValueError, "invalid locked Skill"):
            validate_graph(altered)

    def test_skip_requires_actual_fact_and_evidence_and_is_exact(self):
        stage = stage_by_id(self.graph, "visual_media")
        with self.assertRaisesRegex(ValueError, "Missing applicability fact"):
            stage_applicability(stage, {})
        with self.assertRaisesRegex(ValueError, "evidence_ref"):
            stage_applicability(stage, CONTEXT)
        record = stage_applicability(stage, CONTEXT, evidence_ref="project:rev1:delivery")
        self.assertEqual(record["status"], "NOT_APPLICABLE")
        self.assertEqual(record["affected_outputs"], ["ReferenceImage"])
        validate_skip_record(stage, CONTEXT, record)
        changed = dict(record, observed_value="full")
        with self.assertRaisesRegex(ValueError, "Invalid or stale"):
            validate_skip_record(stage, CONTEXT, changed)
        with self.assertRaisesRegex(ValueError, "Invalid or stale"):
            validate_skip_record(stage, dict(CONTEXT, delivery="full", visual_jobs_present=True), record)

    def test_ready_requires_explicit_skip_and_completed_dependencies(self):
        self.assertEqual([n["id"] for n in ready_stages(self.graph, {}, CONTEXT)], ["sources"])
        states = {"sources": {"status": "ACCEPTED"}}
        self.assertEqual([n["id"] for n in ready_stages(self.graph, states, CONTEXT)], ["reference_observation"])
        states["reference_observation"] = stage_applicability(
            stage_by_id(self.graph, "reference_observation"), CONTEXT, evidence_ref="sources:rev1:observation"
        )
        self.assertEqual([n["id"] for n in ready_stages(self.graph, states, CONTEXT)], ["canon"])
        states["canon"] = {"status": "PENDING"}
        self.assertEqual([n["id"] for n in ready_stages(self.graph, states, CONTEXT)], ["canon"])
        states["canon"] = {"status": "ACCEPTED"}
        self.assertEqual([n["id"] for n in ready_stages(self.graph, states, CONTEXT)], ["screenplay"])
        states["video_delivery"] = {"status": "ACCEPTED"}
        with self.assertRaisesRegex(ValueError, "stale under current applicability"):
            ready_stages(self.graph, states, CONTEXT)

    def test_skip_record_must_match_current_graph_rule(self):
        stage = stage_by_id(self.graph, "control")
        skip = stage_applicability(stage, CONTEXT, evidence_ref="storyboard:sha256")
        self.assertEqual(skip["rule"], {"field": "control_required", "equals": True})
        skip["reason_code"] = "UNSUPPORTED_USER_OVERRIDE"
        with self.assertRaisesRegex(ValueError, "Invalid or stale"):
            validate_skip_record(stage, CONTEXT, skip)

    def test_complete_graph_walk_records_every_conditional_branch(self):
        for context, expected_skips in (
            (CONTEXT, {
                "reference_observation", "visual_prompts", "visual_media", "control",
                "board_prompts", "board_media", *(
                    n["id"] for n in self.graph["nodes"] if n["id"].startswith("video_")
                    or n["id"] in {"take_recovery", "shot_acceptance", "take_selection",
                                    "adjacent_acceptance", "assembly", "whole_acceptance"}
                ),
            }),
            ({"delivery": "full", "production_target": "video",
              "observation_required": True, "control_required": True,
              "visual_jobs_present": True, "board_jobs_present": True}, set()),
        ):
            with self.subTest(context=context):
                states = {}
                while len(states) < len(self.graph["nodes"]):
                    ready = ready_stages(self.graph, states, context)
                    self.assertTrue(ready)
                    for node in ready:
                        result = stage_applicability(node, context, evidence_ref="frozen-input:sha256")
                        states[node["id"]] = (result if result["status"] == "NOT_APPLICABLE"
                                              else {"status": "ACCEPTED"})
                self.assertEqual({key for key, value in states.items()
                                  if value["status"] == "NOT_APPLICABLE"}, expected_skips)
                self.assertEqual(ready_stages(self.graph, states, context), [])

    def test_full_delivery_without_image_jobs_has_explicit_skip_reason(self):
        visual = stage_by_id(self.graph, 'visual_prompts')
        board = stage_by_id(self.graph, 'board_media')
        context = dict(CONTEXT, delivery='full', visual_jobs_present=False,
                       board_jobs_present=False)
        for node in (visual, board):
            record = stage_applicability(node, context, evidence_ref='project.json')
            self.assertEqual(record['reason_code'], 'NO_APPLICABLE_ASSETS')
            validate_skip_record(node, context, record)

    def test_mermaid_is_generated_from_validated_nodes_and_edges(self):
        diagram = graph_to_mermaid(self.graph)
        self.assertEqual(diagram, graph_to_mermaid(self.graph))
        self.assertTrue(diagram.startswith('flowchart TD\n'))
        self.assertEqual(diagram.count(' --> '), sum(len(n['depends_on']) for n in self.graph['nodes']))
        self.assertIn('n0 --> n1', diagram)
        self.assertIn('角色: screenplay', diagram)
        self.assertIn('Skill: screenplay-grammar', diagram)
        self.assertIn('条件: delivery=full', diagram)
        changed = copy.deepcopy(self.graph)
        changed['nodes'][0]['label'] = '资料 & 来源 "核对"'
        self.assertIn('资料 &amp; 来源 &quot;核对&quot;', graph_to_mermaid(changed))
        changed['nodes'][0]['unchecked'] = True
        with self.assertRaisesRegex(ValueError, 'keys differ'):
            graph_to_mermaid(changed)


if __name__ == "__main__":
    unittest.main()
