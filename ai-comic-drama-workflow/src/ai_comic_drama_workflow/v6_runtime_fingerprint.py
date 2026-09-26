"""Content fingerprints for the first-party runtime that lowers V5 IR."""
from __future__ import annotations

from pathlib import Path

from .v5_modules import digest_file


RUNTIME_CODE_FILES = (
    "v5.py",
    "v5_adapters.py",
    "v51_adapters.py",
    "v52_adapters.py",
    "v51_detail_runtime.py",
    "v52_spatial_runtime.py",
    "v5_protocol.py",
    "v5_handoff.py",
    "v6_runtime.py",
    "v6_kernel.py",
    "v6_protocol.py",
    "v6_graph.py",
    "v6_stage_adapter.py",
    "v6_codex_host.py",
    "v6_runtime_fingerprint.py",
)


def runtime_code_hashes(root: Path | None = None) -> dict[str, str]:
    source_root = Path(root) if root is not None else Path(__file__).resolve().parent
    result = {}
    for name in RUNTIME_CODE_FILES:
        path = source_root / name
        if not path.is_file():
            raise FileNotFoundError(f"Required runtime source is missing: {path}")
        result[name] = digest_file(path)
    return result


def runtime_resources_changed(node_id: str, resources: list[dict],
                              root: Path | None = None) -> bool:
    if node_id not in ("control", "compile", "compile_review"):
        return False
    try:
        expected = runtime_code_hashes(root)
    except (OSError, ValueError):
        return True
    frozen = {}
    for item in resources:
        path = Path(item["uri"])
        if path.parent.parent.name == "runtime-resources":
            frozen[path.name] = item["sha256"]
    return frozen != expected
