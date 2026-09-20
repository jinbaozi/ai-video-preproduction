"""Explicit v2 migration: preserve evidence, validate upstream, invalidate visual approvals."""
from copy import deepcopy
from pathlib import Path

from .layout import PHASES, P01, P07
from .schema import validate, validate_artifact, ARTIFACT_SCHEMAS
from .transactions import before_write
from .utils import PACKAGE_ROOT, SCHEMA_VERSION, canonical_json, read_json, sha256_file, stable_id, aggregate_hash


def migrate_v2(kernel, *, action, source_root):
    store = kernel.store
    project, state = deepcopy(kernel.project), deepcopy(kernel.state)
    old_id = project['project_id']
    for entry in store.read('manifest.json')['files']:
        if not store.exists(entry['path']) or sha256_file(store.path(entry['path'])) != entry['sha256']:
            raise ValueError('Legacy manifest is stale; repair/confirm original evidence before migration')
    originals = [p for p in store.root.rglob('*') if p.is_file()
                 and p.relative_to(store.root).parts[0] not in {'.git', '.history', 'runtime'}]
    snapshot_entries = []
    for path in originals:
        relative = path.relative_to(store.root).as_posix()
        digest = store.copy_source(path, '.history/migrations/v2/tree/' + relative)
        snapshot_entries.append((relative, digest))
    legacy_schemas = read_json(PACKAGE_ROOT / 'schemas/legacy-v2-schemas.json')
    retained, rejected = [], []
    for path in originals:
        relative = path.relative_to(store.root).as_posix()
        phase = next((p for p in PHASES if relative.startswith(p['folder'] + '/')), None)
        if not phase:
            continue
        if phase['index'] <= 6 and path.suffix == '.json':
            value = read_json(path)
            if value.get('artifact_type') in {'approval-record', 'decision-request'}:
                before_write(store.root, path)
                path.unlink()
                before_write(store.root, path.with_suffix('.md'))
                path.with_suffix('.md').unlink(missing_ok=True)
                continue
            schema_name = ARTIFACT_SCHEMAS.get(value.get('artifact_type'), 'artifact.schema.json')
            try:
                validate(value, legacy_schemas.get(schema_name, legacy_schemas['artifact.schema.json']))
                value['migration_source_sha256'] = sha256_file(path)
                value['schema_version'] = SCHEMA_VERSION
                value['revision'] += 1
                if 'workflow_id' in value:
                    value['workflow_id'] = kernel.graph.workflow_id
                validate_artifact(value)
                store.commit(relative, value)
                retained.append(relative)
            except ValueError as error:
                rejected.append({'path': relative, 'reason': str(error)})
                before_write(store.root, path)
                path.unlink(missing_ok=True)
                before_write(store.root, path.with_suffix('.md'))
                path.with_suffix('.md').unlink(missing_ok=True)
        elif phase['index'] >= 7:
            # Preserve real images as explicit migration candidates, never as approved references.
            if phase['index'] == 7 and path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}:
                store.copy_source(path, f'{P07}/migration-candidates/{sha256_file(path)}{path.suffix.lower()}')
            before_write(store.root, path)
            path.unlink()
    for path in list(store.path('runtime').rglob('*')):
        if path.is_file() and not path.is_relative_to(store.path('runtime/transactions')):
            before_write(store.root, path)
            path.unlink()
    decisions = {k: v for k, v in state.get('decisions', {}).items()
                 if k in {'work_depth', 'adaptation_policy', 'rights_status', 'chapter_batch_size', 'segment_duration_s'}}
    report_path = f'{P01}/migration-report.json'
    report = {'schema_version': SCHEMA_VERSION, 'artifact_type': 'migration-report',
              'artifact_id': stable_id('migration', old_id, '3.0'), 'project_id': old_id, 'revision': 1,
              'stage_id': 'project_setup', 'role_provenance': 'kernel', 'action': action,
              'source_schema': '2.0', 'target_schema': SCHEMA_VERSION, 'source_root': str(source_root),
              'retained': retained, 'rejected': rejected, 'snapshot': '.history/migrations/v2/tree',
              'snapshot_hash': aggregate_hash(snapshot_entries), 'old_visual_approvals_accepted': False}
    store.commit(report_path, report)
    project.update(schema_version=SCHEMA_VERSION, revision=project['revision']+1,
                   workflow_id=kernel.graph.workflow_id, selected_config=decisions,
                   migration={'from_schema': '2.0', 'action': action, 'report': report_path})
    store.commit('project.json', project)
    stages = {stage.id: 'complete' if stage.output in retained else 'pending' for stage in kernel.graph.stages}
    stages['project_setup'] = 'complete'
    stages['project_configuration'] = 'pending'  # New delivery-scope choice may not be inferred.
    for stage_id in state.get('skipped_stages', []):
        if stage_id in stages:
            stages[stage_id] = 'complete'
    state.update(schema_version=SCHEMA_VERSION, revision=state['revision']+1, stage_status=stages,
                 status='running', current_stage=None, active_task=None, active_decision=None,
                 decisions=decisions, decision_approvals={k: report_path for k in decisions},
                 decision_stages={k: 'project_setup' for k in decisions}, failure_counts={},
                 invalidated_stages=[s for s in stages if stages[s] != 'complete'])
    store.commit('state.json', state)
    index = store.read('phase-index.json')
    index.update(schema_version=SCHEMA_VERSION, revision=index['revision']+1, workflow_id=kernel.graph.workflow_id)
    index['phases'] = [{**phase, 'stage_ids': [s.id for s in kernel.graph.stages if s.phase_id == phase['id']]} for phase in PHASES]
    store.commit('phase-index.json', index)
    store.rebuild_manifest()
    kernel._legacy_v1 = False
