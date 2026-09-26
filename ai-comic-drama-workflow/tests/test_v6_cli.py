"""V6 CLI entry and bypass checks; no agent or media tools are invoked."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_comic_drama_workflow.v5_cli import main
from ai_comic_drama_workflow.v6_graph import graph_to_mermaid, load_graph


class V6CliTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def call(self, *args):
        output = StringIO()
        with redirect_stdout(output):
            code = main(list(args))
        return code, json.loads(output.getvalue())

    def test_new_project_defaults_to_v6_and_direct_submit_is_rejected(self):
        project = self.root/'new'
        code, result = self.call('init', '原创资料', '--project', str(project),
                                 '--delivery', 'text-only', '--no-run')
        self.assertEqual(code, 0)
        self.assertEqual(result['orchestration_protocol'], '6.0')
        self.assertEqual(json.loads((project/'project.json').read_text())['orchestration_protocol'], '6.0')

        code, result = self.call('submit', str(project), '--result', str(self.root/'fake.json'))
        self.assertEqual(code, 1)
        self.assertIn('requires a V6 candidate', result['error'])

    def test_host_command_rejects_extra_wrapper_fields(self):
        project = self.root/'new'
        self.call('init', '原创资料', '--project', str(project), '--no-run')
        payload = self.root/'command.json'
        payload.write_text(json.dumps({'command_id': 'COMMAND_1', 'expected_revision': 0,
                                       'receipt': {}, 'status': 'ACCEPTED'}), encoding='utf-8')
        code, result = self.call('agent-event', str(project), '--file', str(payload))
        self.assertEqual(code, 1)
        self.assertIn('wrapper fields differ', result['error'])

        payload.write_text(json.dumps({'command_id': 'COMMAND_2', 'expected_revision': 0,
                                       'task_id': 'TASK_A', 'ack_message_id': None,
                                       'status': 'CANCELLED'}), encoding='utf-8')
        code, result = self.call('agent-cancel', str(project), '--file', str(payload))
        self.assertEqual(code, 1)
        self.assertIn('wrapper fields differ', result['error'])

    def test_legacy_mode_requires_explicit_opt_in(self):
        project = self.root/'legacy'
        code, result = self.call('init', '原创资料', '--project', str(project),
                                 '--delivery', 'text-only', '--orchestration',
                                 'current-agent', '--no-run')
        self.assertEqual(code, 0)
        self.assertNotIn('orchestration_protocol', result)
        self.assertNotIn('orchestration_protocol', json.loads((project/'project.json').read_text()))

    def test_graph_diagram_and_cli_stage_list_come_from_executable_graph(self):
        graph = load_graph()
        output = StringIO()
        with redirect_stdout(output):
            code = main(['graph'])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), graph_to_mermaid(graph))

        code, result = self.call('graph', '--format', 'json')
        self.assertEqual(code, 0)
        self.assertEqual(result['nodes'], graph['nodes'])
        self.assertEqual(result['mermaid'], output.getvalue())


if __name__ == '__main__':
    unittest.main()
