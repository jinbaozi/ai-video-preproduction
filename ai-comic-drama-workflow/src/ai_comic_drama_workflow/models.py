"""Public data contracts used by the kernel and stage experts.

Canonical JSON remains the persisted contract.  These TypedDicts make the same
boundary visible to Python callers without creating a second serialization
model.
"""

from typing import Literal, NotRequired, TypedDict


StageStatus = Literal[
    "pending", "running", "awaiting_choice", "blocked", "complete", "failed", "invalidated"
]
CapabilityStatus = Literal[
    "available", "unavailable", "requires_account", "requires_payment", "unknown"
]


class SourceRecord(TypedDict):
    source_id: str
    kind: str
    stored_path: str
    sha256: str
    rights_status: str
    authority: str
    original_path: NotRequired[str]
    text_path: NotRequired[str]
    extraction_status: NotRequired[str]


class ProjectConfig(TypedDict):
    title: str
    format: str
    work_depth: str
    adaptation_policy: str
    selected_config: dict[str, object]
    external_generation_blocked: bool


class StageState(TypedDict):
    status: str
    current_stage: str | None
    active_task: str | None
    active_decision: str | None
    stage_status: dict[str, StageStatus]
    decisions: dict[str, object]
    failure_counts: dict[str, int]


class TaskEnvelope(TypedDict):
    task_id: str
    project_id: str
    stage_id: str
    phase_id: str
    phase_folder: str
    context_fingerprint: str
    input_artifacts: list[str]
    loaded_resources: list[str]
    output_contract: dict[str, object]
    constraints: dict[str, object]
    shot_batch: NotRequired[dict[str, object] | None]
    source_batch: NotRequired[dict[str, object] | None]


class AgentResult(TypedDict):
    result_id: str
    project_id: str
    stage_id: str
    context_fingerprint: str
    status: Literal["draft", "approved", "needs_decision", "failed"]
    artifact: dict[str, object]
    findings: list[dict[str, object]]
    provenance: list[dict[str, object]]
    next_action: NotRequired[str | None]


class DecisionRequest(TypedDict):
    request_id: str
    stage_id: str
    status: Literal["open", "resolved"]
    fields: list[dict[str, object]]


class ApprovalRecord(TypedDict):
    approval_id: str
    request_id: str
    stage_id: str
    selections: dict[str, object]
    context_fingerprint: str


class GenerationSegment(TypedDict):
    segment_id: str
    index: int
    target_duration_s: float
    source_refs: list[str]
    shot_ids: NotRequired[list[str]]


class VisualAssetRegistry(TypedDict):
    assets: list[dict[str, object]]
    execution_status: Literal["prompt_ready", "media_partial", "media_verified"]
    degradations: list[dict[str, object]]


class SceneSpacePlan(TypedDict):
    representation: Literal["2d-blocking", "2.5d-structured-previsualization", "verified-3d"]
    scenes: list[dict[str, object]]


class ShotTimelineSpec(TypedDict):
    shot_id: str
    index: int
    segment_id: str
    scene_id: str
    duration_s: float
    narrative_purpose: str
    character_tracks: list[dict[str, object]]
    camera_track: list[dict[str, object]]
    audio_track: list[dict[str, object]]
    director_track: list[dict[str, object]]
    spatial_track: list[dict[str, object]]
    scene_fixed_track: list[dict[str, object]]
    environment: dict[str, object]
    lighting: dict[str, object]
    continuity: dict[str, object]
    required_asset_ids: list[str]
    selected_reference_ids: list[str]
    negative_constraints: list[str]


class StoryboardPackage(TypedDict):
    depth: Literal["narrative", "blocking", "action", "full-dimensional"]
    views: list[str]
    shots: list[dict[str, object]]
    previsualization_status: str


class CapabilitySnapshot(TypedDict):
    capabilities: dict[str, dict[str, str]]


class PromptPackage(TypedDict):
    package_id: str
    adapter_id: str
    shot_ids: list[str]
    prompts: list[dict[str, object]]
    warnings: list[dict[str, object]]
    degradations: list[dict[str, object]]


class ArtifactRecord(TypedDict):
    path: str
    sha256: str
    artifact_type: NotRequired[str]
    stage_id: NotRequired[str]
    role_provenance: NotRequired[str]
    revision: NotRequired[int]
    delivery_status: NotRequired[str]


class FinalDeliveryIndex(TypedDict):
    delivery_id: str
    status: Literal["prompt_ready", "media_partial", "media_verified", "export_ready"]
    artifacts: list[ArtifactRecord]
    boundaries: list[str]
    package_status: NotRequired[Literal["export_ready"]]
