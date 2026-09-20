from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable


_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_INSTALLED_ROOT = Path(sys.prefix) / "share" / "ai-comic-drama-workflow"
PACKAGE_ROOT = _SOURCE_ROOT if (_SOURCE_ROOT / "workflow-graph.json").exists() else _INSTALLED_ROOT
SCHEMA_VERSION = "3.0"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{sha256_bytes(payload)[:length]}"


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def ensure_relative_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Project path must be relative and contained: {value}")
    return candidate


def markdown_view(source_path: str, source_sha256: str, payload: dict[str, Any]) -> str:
    title = str(payload.get("artifact_type") or payload.get("stage_id") or "artifact")
    return (
        f"# {title}\n\n"
        f"Canonical source: `{source_path}`  \n"
        f"Canonical SHA-256: `{source_sha256}`\n\n"
        "```json\n"
        f"{canonical_json(payload)}"
        "```\n"
    )


def aggregate_hash(entries: Iterable[tuple[str, str]]) -> str:
    normalized = "".join(f"{path}\0{digest}\n" for path, digest in sorted(entries))
    return sha256_bytes(normalized.encode("utf-8"))


def deterministic_zip(output: Path, root: Path, paths: Iterable[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
                relative = path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
