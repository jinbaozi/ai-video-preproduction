from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .utils import PACKAGE_ROOT, read_json


@dataclass(frozen=True, slots=True)
class Stage:
    id: str
    phase_id: str
    kind: str
    role: str
    resources: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    output: str | None = None
    artifact_type: str | None = None
    required_decisions: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Stage":
        return cls(
            id=value["id"],
            phase_id=value["phase_id"],
            kind=value["kind"],
            role=value["role"],
            resources=tuple(value.get("resources", [])),
            inputs=tuple(value.get("inputs", [])),
            output=value.get("output"),
            artifact_type=value.get("artifact_type"),
            required_decisions=tuple(value.get("required_decisions", [])),
            depends_on=tuple(value.get("depends_on", [])),
        )


@dataclass(frozen=True, slots=True)
class Phase:
    id: str
    index: int
    name: str
    folder: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Phase":
        return cls(
            id=str(value["id"]),
            index=int(value["index"]),
            name=str(value["name"]),
            folder=str(value["folder"]),
        )


class WorkflowGraph:
    def __init__(self) -> None:
        payload = read_json(PACKAGE_ROOT / "legacy-workflow-graph.json")
        self.workflow_id = str(payload["workflow_id"])
        self.max_shots_per_task = int(payload["max_shots_per_task"])
        self.phases = tuple(Phase.from_dict(item) for item in payload["phases"])
        self._phase_by_id = {phase.id: phase for phase in self.phases}
        self.stages = tuple(Stage.from_dict(item) for item in payload["stages"])
        self._by_id = {stage.id: stage for stage in self.stages}
        self._producer = {stage.output: stage.id for stage in self.stages if stage.output}
        self._dependencies: dict[str, set[str]] = {}
        for stage in self.stages:
            dependencies = set(stage.depends_on)
            dependencies.update(
                producer
                for artifact in stage.inputs
                if (producer := self._producer.get(artifact)) is not None
            )
            self._dependencies[stage.id] = dependencies
        self._validate()

    def _validate(self) -> None:
        if len(self._by_id) != len(self.stages):
            raise ValueError("Workflow stage IDs must be unique")
        if len(self._phase_by_id) != len(self.phases):
            raise ValueError("Workflow phase IDs must be unique")
        if [phase.index for phase in self.phases] != list(range(1, len(self.phases) + 1)):
            raise ValueError("Workflow phase indexes must be contiguous from 1")
        positions = {stage.id: index for index, stage in enumerate(self.stages)}
        for stage in self.stages:
            if stage.phase_id not in self._phase_by_id:
                raise ValueError(f"Unknown phase {stage.phase_id!r} for stage {stage.id!r}")
            unknown = self._dependencies[stage.id] - set(self._by_id)
            if unknown:
                raise ValueError(f"Unknown dependencies for {stage.id}: {sorted(unknown)}")
            late = [item for item in self._dependencies[stage.id] if positions[item] >= positions[stage.id]]
            if late:
                raise ValueError(f"Workflow is not topological at {stage.id}: {sorted(late)}")

    def get(self, stage_id: str) -> Stage:
        try:
            return self._by_id[stage_id]
        except KeyError as error:
            raise ValueError(f"Unknown workflow stage: {stage_id}") from error

    def index(self, stage_id: str) -> int:
        return next(index for index, stage in enumerate(self.stages) if stage.id == stage_id)

    def phase(self, phase_id: str) -> Phase:
        try:
            return self._phase_by_id[phase_id]
        except KeyError as error:
            raise ValueError(f"Unknown workflow phase: {phase_id}") from error

    def phase_for_stage(self, stage_id: str) -> Phase:
        return self.phase(self.get(stage_id).phase_id)

    def dependencies(self, stage_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._dependencies[stage_id], key=self.index))

    def downstream(self, stage_id: str, *, include_self: bool = False) -> tuple[Stage, ...]:
        affected = {stage_id} if include_self else set()
        frontier = {stage_id}
        while frontier:
            current = frontier.pop()
            for candidate in self.stages:
                if current in self._dependencies[candidate.id] and candidate.id not in affected:
                    affected.add(candidate.id)
                    frontier.add(candidate.id)
        return tuple(stage for stage in self.stages if stage.id in affected)

    def producer_for(self, artifact_path: str) -> str | None:
        return self._producer.get(artifact_path)

    def first_incomplete(self, stage_status: dict[str, str], skipped: Iterable[str] = ()) -> Stage | None:
        skip_set = set(skipped)
        for stage in self.stages:
            if stage.id in skip_set:
                continue
            if stage_status.get(stage.id) == "complete":
                continue
            if all(
                dependency in skip_set or stage_status.get(dependency) == "complete"
                for dependency in self._dependencies[stage.id]
            ):
                return stage
        return None


ENTRY_SKIPS: dict[str, tuple[str, ...]] = {
    "novel": (),
    "screenplay": ("adaptation_plan",),
    "storyboard": (
        "adaptation_plan",
        "screenplay",
        "screenplay_enhance",
        "story_quality_gate",
    ),
    "mixed": (),
    "reference-only": (),
    "legacy-project": (),
}
