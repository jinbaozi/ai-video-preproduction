from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from .utils import PACKAGE_ROOT, read_json


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    path: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.message}"


class SchemaValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("; ".join(issue.render() for issue in issues))


def load_schema(name: str) -> dict[str, Any]:
    if '/' in name or '\\' in name or not name.endswith('.schema.json'):
        raise ValueError('Schema must be a registered local filename')
    path = PACKAGE_ROOT / 'schemas' / name
    if not path.is_file():
        raise FileNotFoundError(f'Unknown schema: {name}')
    return read_json(path)


def _deny_remote(uri):
    raise NoSuchResource(ref=uri)


@lru_cache(maxsize=64)
def _validator(encoded: str, resources: tuple[str, ...]):
    registry = Registry(retrieve=_deny_remote)
    for raw in resources:
        value = json.loads(raw)
        if '$id' in value:
            registry = registry.with_resource(value['$id'], Resource.from_contents(value))
    schema = json.loads(encoded)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry)


def _finite_issues(value, path):
    if isinstance(value, float) and not math.isfinite(value):
        return [ValidationIssue(path, 'number must be finite')]
    if isinstance(value, (dict, list)):
        items = value.items() if isinstance(value, dict) else enumerate(value)
        return [issue for key, item in items for issue in _finite_issues(item, f'{path}.{key}')]
    return []


def collect_issues(value: Any, schema: dict[str, Any], path: str = '$') -> list[ValidationIssue]:
    # Resource contents, not filenames, key the cache: edited references never stay stale.
    resources = tuple(p.read_text() for p in sorted((PACKAGE_ROOT / 'schemas').glob('*.schema.json')))
    validator = _validator(json.dumps(schema, sort_keys=True), resources)
    issues = _finite_issues(value, path)
    for error in validator.iter_errors(value):
        location = path + ''.join(f'[{p}]' if isinstance(p, int) else f'.{p}' for p in error.absolute_path)
        issues.append(ValidationIssue(location, error.message))
    return issues


def validate(value: Any, schema: dict[str, Any]) -> None:
    issues = collect_issues(value, schema)
    if issues:
        raise SchemaValidationError(issues)


ARTIFACT_SCHEMAS = {kind: f'{kind}.schema.json' for kind in (
    'project', 'phase-index', 'workflow-state', 'source-registry', 'task-envelope',
    'decision-request', 'approval-record', 'generation-segment-plan', 'shot-timeline-spec',
    'scene-space-plan', 'visual-asset-registry', 'storyboard-package', 'capability-snapshot',
    'prompt-package', 'final-delivery-index', 'director-treatment', 'evaluated-frame-state',
    'media-job', 'media-result', 'asset-plan', 'edit-plan',
)}


def validate_artifact(value: dict[str, Any]) -> None:
    if value.get('schema_version') == '4.0':
        validate(value, load_schema('v4-artifact.schema.json'))
        from .v4_contracts import validate_payload
        validate_payload(value)
        return
    kind = value.get('artifact_type')
    if kind == 'manifest':
        validate(value, load_schema('manifest.schema.json'))
        return
    validate(value, load_schema('artifact.schema.json'))
    if kind in ARTIFACT_SCHEMAS:
        validate(value, load_schema(ARTIFACT_SCHEMAS[kind]))
