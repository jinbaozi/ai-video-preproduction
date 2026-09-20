# L0 Orchestration

Read only `project.json`, `state.json`, `manifest.json`, `phase-index.json`, and the active request
before routing.
The kernel selects exactly one ready stage. Never load all role references at once.

- `awaiting_choice`: read the active DecisionRequest and ask only those fields.
- `awaiting_agent_result`: read the TaskEnvelope, its listed inputs, and listed resources.
- `blocked`: read the active finding and recovery reference; do not continue silently.
- `complete`: run final validation and report the concrete delivery status.

Only the kernel commits canonical artifacts or changes stage state. Agent work is a draft
`AgentResult` until accepted against the active context fingerprint.

Each TaskEnvelope names one phase folder, that phase's compact rule file, the necessary upstream
artifacts and Schema, one specialist role, and a quality rubric only when applicable. Adapter and
diagnostic resources load only at their gates. A v1/v2 project routes to an explicit migration request
before any Schema 3.0 stage can run.
