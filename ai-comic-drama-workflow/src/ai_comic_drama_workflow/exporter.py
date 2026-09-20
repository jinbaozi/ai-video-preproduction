from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from .layout import P13, FINAL_DELIVERY_INDEX
from .storage import ProjectStore
from .utils import SCHEMA_VERSION, aggregate_hash, atomic_write, deterministic_zip, sha256_file, stable_id


def delivery_paths(store: ProjectStore) -> list[Path]:
    paths: list[Path] = []
    delivery_prefix = tuple(Path(f"{P13}/delivery").parts)
    for path in store.root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(store.root)
        if relative.parts and relative.parts[0] in {".history", "delivery", "runtime"}:
            continue
        if relative.parts[: len(delivery_prefix)] == delivery_prefix:
            continue
        if "__pycache__" in relative.parts or path.name.startswith("."):
            continue
        paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(store.root).as_posix())


def build_delivery_archive(store: ProjectStore, *, draft: bool = False) -> dict[str, Any]:
    from .validation import validate_project
    with store.transaction():
        report = validate_project(store.root, final=not draft, check_archive=False)
        if not report["valid"] and not draft:
            raise ValueError(f"Cannot export an invalid project: {report['errors']}")
        if draft:
            # A detached archive snapshot cannot reuse live final success reports. It does
            # not mutate or approve the working project, and is never a resume target.
            with tempfile.TemporaryDirectory(prefix='ai-comic-draft-') as directory:
                snapshot = ProjectStore(directory)
                excluded = {FINAL_DELIVERY_INDEX, FINAL_DELIVERY_INDEX.replace('.json', '.md'),
                            f'{P13}/final-validation.json', f'{P13}/final-validation.md', 'manifest.json', 'manifest.md'}
                for path in delivery_paths(store):
                    relative = path.relative_to(store.root).as_posix()
                    if relative not in excluded:
                        snapshot.copy_source(path, relative)
                project_id = store.read('project.json')['project_id']
                base = {'schema_version': SCHEMA_VERSION, 'project_id': project_id, 'revision': 1,
                        'stage_id': 'export', 'role_provenance': 'kernel', 'delivery_scope': 'explicit-draft',
                        'snapshot_only': True}
                snapshot.commit(f'{P13}/final-validation.json', {**base, 'artifact_type': 'final-validation',
                    'artifact_id': stable_id('draft-validation', project_id), **report,
                    'formal_delivery_approved': False})
                files = [{'path': p.relative_to(snapshot.root).as_posix(), 'sha256': sha256_file(p)}
                         for p in delivery_paths(snapshot)]
                snapshot.commit(FINAL_DELIVERY_INDEX, {**base, 'artifact_type': 'final-delivery-index',
                    'artifact_id': stable_id('draft-index', project_id), 'delivery_id': stable_id('draft', project_id),
                    'status': 'draft', 'artifacts': files, 'dual_reference_status': 'not_accepted',
                    'boundaries': ['Inspection snapshot only; no final approval. Resume the original project, not this archive.']})
                snapshot.rebuild_manifest()
                result = _build_delivery_archive(snapshot, draft=True)
                archive = result['archive']
                store.copy_source(snapshot.path(archive), archive)
                store.copy_source(snapshot.path(archive + '.sha256'), archive + '.sha256')
        else:
            result = _build_delivery_archive(store)
        return {**result, 'delivery_scope': 'explicit-draft' if draft else 'validated-declared-scope',
                'validation_errors': report['errors']}


def _build_delivery_archive(store: ProjectStore, *, draft: bool = False) -> dict[str, Any]:
    project = store.read("project.json")
    archive = store.path(f"{P13}/delivery/{project['project_id']}{'-DRAFT' if draft else ''}.zip")
    paths = delivery_paths(store)
    from .transactions import before_write
    before_write(store.root, archive)
    before_write(store.root, archive.with_suffix('.zip.sha256'))
    deterministic_zip(archive, store.root, paths)
    archive_hash = sha256_file(archive)
    atomic_write(archive.with_suffix(".zip.sha256"), f"{archive_hash}  {archive.name}\n".encode("utf-8"))
    entries = [(path.relative_to(store.root).as_posix(), sha256_file(path)) for path in paths]
    return {
        "archive": archive.relative_to(store.root).as_posix(),
        "sha256": archive_hash,
        "aggregate_hash": aggregate_hash(entries),
        "file_count": len(paths),
    }
