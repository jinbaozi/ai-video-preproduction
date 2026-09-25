from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_INSTALLED_ROOT = Path(sys.prefix) / "share" / "ai-comic-drama-workflow"
PACKAGE_ROOT = _SOURCE_ROOT if (_SOURCE_ROOT / "SKILL.md").exists() else _INSTALLED_ROOT


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def ensure_relative_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Project path must be relative and contained: {value}")
    return candidate
