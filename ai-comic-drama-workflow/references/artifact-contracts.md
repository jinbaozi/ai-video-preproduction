# Artifact Contracts

Canonical artifacts are UTF-8 JSON with `schema_version`, stable artifact/project IDs, revision,
stage ID, role provenance, and source/provenance fields. The paired Markdown view names the JSON
path and exact SHA-256. Markdown must never be edited as the machine source.

Authority is: explicit approved user decision; approved downstream artifact within its scope;
untouched upstream source; labeled inference/adaptation; platform compromise. Platform data cannot
write facts back into Canonical artifacts.

Every AgentResult must match the active TaskEnvelope's project, stage, and context fingerprint.
For `shot_timeline_specs`, return `artifact.shots`; each ShotTimelineSpec is 1–12 seconds, has a
stable global index, references a valid SceneSpace and asset registry, and selects no more than five
upload references. All trajectory/event times must be ordered and inside the shot. The unbounded
`required_asset_ids` list is distinct from platform upload slots.

Use this envelope shape; omit formal artifact metadata from `artifact` because the kernel assigns
and validates it:

```json
{
  "schema_version": "3.0",
  "result_id": "stable-result-id",
  "project_id": "project-id-from-task",
  "stage_id": "stage-id-from-task",
  "context_fingerprint": "64-character-fingerprint-from-task",
  "status": "draft",
  "artifact": {},
  "findings": [],
  "provenance": [{"source": "listed/input/path.json"}],
  "next_action": null
}
```

Use `status: approved` for review gates, `needs_decision` with a structured `decision_request` for
missing authority, and `failed` only with concrete evidence. A formal JSON artifact and its derived
Markdown are committed together; standalone text prompts always cite the current JSON hash.
