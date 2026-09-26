"""Strict V6 orchestration wire contracts and deterministic fingerprints."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .utils import PACKAGE_ROOT
from .v5_modules import read


SCHEMA_NAMES = frozenset({
    "task-envelope", "dispatch-receipt", "agent-message", "candidate-result",
    "review-record", "state-event", "image-host-action", "image-host-record",
    "observation-register", "repair-brief", "upstream-repair-brief",
    "compile-semantic-failure",
})


class V6ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def compact_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(compact_json(value)).hexdigest()


def envelope_input_digest(envelope: dict) -> str:
    """Fingerprint exactly the frozen input and assignment fields."""
    return sha256_json({key: envelope[key] for key in (
        "project_id", "input_revision", "inputs", "scope", "module",
        "resources", "dependencies",
    )})


def envelope_semantic_digest(envelope: dict) -> str:
    """Compare retry inputs without the bookkeeping revision number."""
    return sha256_json({key: envelope[key] for key in (
        "project_id", "inputs", "scope", "module", "resources", "dependencies",
    )})


def envelope_digest(envelope: dict) -> str:
    return sha256_json(envelope)


def candidate_digest(candidate: dict) -> str:
    return sha256_json(candidate)


def expected_dispatch_id(envelope: dict) -> str:
    return "dispatch-" + hashlib.sha256((envelope["task_id"] + ":" +
        str(envelope["batch"]) + ":" + envelope_digest(envelope)).encode()).hexdigest()[:24]


def expected_review_dispatch_id(envelope: dict) -> str:
    return "review-" + hashlib.sha256((envelope["task_id"] + ":" +
        str(envelope["batch"]) + ":" + envelope_digest(envelope)).encode()).hexdigest()[:24]


def validate_v6_protocol(name: str, value: object,
                         schema_root: Path = PACKAGE_ROOT) -> None:
    if name not in SCHEMA_NAMES:
        raise V6ProtocolError("SCHEMA_NAME", f"Unknown V6 protocol: {name}")
    path = Path(schema_root) / "schemas" / f"v6-{name}.schema.json"
    schema = read(path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value),
                    key=lambda error: (list(map(str, error.absolute_path)), error.message))
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.absolute_path)) or "$"
        raise V6ProtocolError("SCHEMA_INVALID", f"{name} {location}: {error.message}")


validate_protocol = validate_v6_protocol
