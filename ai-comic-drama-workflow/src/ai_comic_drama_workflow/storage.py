from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .schema import validate_artifact
from .transactions import before_write, transaction
from .layout import P13
from .utils import (
    SCHEMA_VERSION,
    atomic_write,
    canonical_json,
    ensure_relative_path,
    markdown_view,
    read_json,
    sha256_bytes,
    sha256_file,
    stable_id,
)


class ProjectStore:
    """The only persistence service used by WorkflowKernel."""

    def __init__(self, project_dir: Path | str):
        self.root = Path(project_dir).expanduser().resolve()

    def transaction(self, *, savepoint: bool = False):
        return transaction(self.root, savepoint=savepoint)

    def path(self, relative: str) -> Path:
        candidate = self.root / ensure_relative_path(relative)
        if not candidate.resolve().is_relative_to(self.root):
            raise ValueError(f"Project path escapes through a symbolic link: {relative}")
        return candidate

    def exists(self, relative: str) -> bool:
        return self.path(relative).exists()

    def read(self, relative: str) -> dict[str, Any]:
        return read_json(self.path(relative))

    def revision_for(self, relative: str) -> int:
        if not self.exists(relative):
            return 1
        return int(self.read(relative).get("revision", 0)) + 1

    def commit(self, relative: str, value: dict[str, Any], *, validate_schema: bool = True) -> str:
        target = self.path(relative)
        if target.suffix.lower() != ".json":
            raise ValueError(f"Canonical artifact must be JSON: {relative}")
        if validate_schema:
            validate_artifact(value)
        before_write(self.root, target)
        before_write(self.root, target.with_suffix(".md"))
        if target.exists():
            old = read_json(target)
            old_revision = int(old.get("revision", 0))
            history = self.path(
                f".history/{target.relative_to(self.root).with_suffix('').as_posix()}"
                f".r{old_revision}.{sha256_file(target)[:12]}.json"
            )
            history.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, history)
        payload = canonical_json(value).encode("utf-8")
        atomic_write(target, payload)
        digest = sha256_bytes(payload)
        markdown = markdown_view(relative, digest, value).encode("utf-8")
        atomic_write(target.with_suffix(".md"), markdown)
        return digest

    def copy_source(self, source: Path, relative: str) -> str:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or sha256_file(target) != sha256_file(source):
            before_write(self.root, target)
            shutil.copy2(source, target)
        return sha256_file(target)

    def write_text(self, relative: str, text: str) -> str:
        target = self.path(relative)
        before_write(self.root, target)
        payload = text.encode("utf-8")
        atomic_write(target, payload)
        return sha256_bytes(payload)

    def rebuild_manifest(self) -> dict[str, Any]:
        project = self.read("project.json")
        files: list[dict[str, Any]] = []
        excluded_roots = {".history", "runtime", "delivery"}
        delivery_prefix = tuple(Path(f"{P13}/delivery").parts)
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if relative.parts and relative.parts[0] in excluded_roots:
                continue
            if relative.parts[: len(delivery_prefix)] == delivery_prefix:
                continue
            if relative.as_posix() in {"manifest.json", "manifest.md"}:
                continue
            if "__pycache__" in relative.parts or path.name.startswith("."):
                continue
            record: dict[str, Any] = {
                "path": relative.as_posix(),
                "sha256": sha256_file(path),
            }
            if path.suffix == ".json":
                try:
                    payload = read_json(path)
                except (ValueError, json.JSONDecodeError):
                    payload = {}
                for key in ("artifact_type", "stage_id", "role_provenance", "revision"):
                    if key in payload:
                        record[key] = payload[key]
            files.append(record)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "manifest",
            "manifest_id": stable_id("manifest", project["project_id"]),
            "project_id": project["project_id"],
            "revision": self.revision_for("manifest.json"),
            "files": files,
        }
        self.commit("manifest.json", manifest)
        return manifest

    def artifact_base(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        project_id: str,
        revision: int,
        stage_id: str,
        role: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "project_id": project_id,
            "revision": revision,
            "stage_id": stage_id,
            "role_provenance": role,
        }
