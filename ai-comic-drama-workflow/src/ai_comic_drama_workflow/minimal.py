"""A small host view/result adapter; native tasks, IR and acceptance stay authoritative.

Only redundant presentation/provenance is omitted. The host must acknowledge the
presented reads and author every semantic/visual finding. No success is inferred.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from .v5_adapters import digest
from .v5_modules import read, digest_file

POLICY = 'minimal-core/1.0'
RESULT = 'core-result/1.0'


def enabled(project):
    return project.get('context_policy') == POLICY


def craft_view(plan):
    """Keep every selected/inherited instruction, scope and actual source passage.

    The omitted fields are retrieval diagnostics and machine provenance. Exact
    originals remain in the immutable task envelope, not another sidecar.
    """
    result = deepcopy(plan)
    for key in ('plan_sha256', 'input_sha256', 'source_sha256', 'input_artifacts',
                'alternatives', 'rejected', 'sources', 'selection_basis'):
        result.pop(key, None)
    # One required-rule table; no repeated provenance in each inherited copy.
    for row in result.get('rules', []) + result.get('inherited', []):
        if 'source' in row:
            source = row['source']
            row['source'] = {k: v for k, v in source.items()
                             if k not in ('sha256', 'catalog_sha256', 'section_sha256', 'upstream')}
    selected = result.get('prompt_methods')
    if not isinstance(selected, dict):
        return result
    for key in ('catalog_sha256', 'runtime_sha256', 'capability_sha256', 'plan_sha256',
                'selection_basis', 'source', 'candidates'):
        selected.pop(key, None)
    own = {r['id']: r for r in plan.get('rules', [])}
    role = selected.get('role')
    for category in ('methods', 'templates'):
        for row in selected.get(category, []):
            identifier = str(role) + ':prompt:' + row['id']
            original = own.get(identifier)
            if original and all(original.get(k) == row.get(k) for k in ('instruction', 'check')):
                # Other fields (especially writing_pattern) are never removed.
                row['rule_id'] = identifier
                for key in ('instruction', 'check', 'source'):
                    row.pop(key, None)
    community = selected.get('community', {})
    for key in ('catalog_sha256', 'runtime_sha256', 'capability_sha256', 'plan_sha256'):
        community.pop(key, None)
    for card in community.get('cards', []):
        identifier = str(role) + ':community:' + card['id']
        original = own.get(identifier)
        if original and all(original.get(k) == card.get(k) for k in ('instruction', 'check')):
            card['rule_id'] = identifier
            card.pop('instruction', None); card.pop('check', None)
        # Keep text, source IDs, file and section; hashes are program-verified.
        reading = card.get('reading', {})
        for key in ('file_sha256', 'section_sha256', 'external_response_hash'):
            reading.pop(key, None)
    return result


def packet(task):
    """Materialize only this task's reads. Do not execute source-file contents."""
    if not enabled(task.get('project') or {}):
        raise ValueError('Minimal context is not enabled for this frozen project')
    view = deepcopy(task)
    view.pop('context_fingerprint', None)  # Task ID and immutable envelope bind this.
    view['schema'] = 'core-task/1.0'
    view['expected_result'] = RESULT
    view['output_contract'] = {'kind': task['kind'], 'format': 'native artifact + ' + RESULT}
    view['audit_task_schema'] = task['schema']
    if view.get('brief', {}).get('inputs') == view.get('inputs'):
        view['brief'].pop('inputs')
        view['brief']['inputs_ref'] = 'task.inputs'
    view['readings'] = []
    seen = set()
    module = task.get('module')
    if module:
        for item in module.get('required_reads', []):
            path = Path(item['path'])
            data = path.read_bytes()
            import hashlib
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Required read changed: ' + item['relative'])
            if item['sha256'] not in seen:
                view['readings'].append({'path': item['relative'], 'text': data.decode('utf-8')})
                seen.add(item['sha256'])
        view['module'] = {k: module[k] for k in ('name', 'version', 'path') if k in module}
    if task.get('craft'):
        view['craft'] = craft_view(task['craft'])
    view['result_instruction'] = (
        'Return core-result/1.0 with task_id, read_ack:true after reading this packet and its readings, '
        'checks, conflicts, unresolved and the native result fields. Author actual semantics/visual findings. '
        'Hashes, module receipts and native validator reports are computed by the runtime. '
        'Never assert a pass without review.')
    if task.get('craft'):
        view['result_instruction'] += (' craft_review requires rationale, semantic_review:true and applications OR groups with explicit '
        'rule_ids, status, reason, check, pointer/quote (or not_applicable condition). '
        'Different scope/findings must not share a group.')
    elif task.get('project', {}).get('craft_policy') == 'off':
        view['result_instruction'] += (' This project explicitly disables mandatory method routing. '
            'Module method libraries are optional references; do not add craft_context or craft_review paperwork. '
            'Native content, dialogue locks, continuity and media checks still apply.')
    if task['kind']=='compile-review':
        view['delivery_audit_contract'] = {
            'optional':True, 'build_id':task['build']['build_id'],
            'required_hard_clauses':task.get('hard_clauses',[]),
            'instruction':'After reviewing this SAME build, optionally provide delivery_audit {build_id, passed:true, checks:[actual findings covering every hard clause]}. The runtime still issues and validates a separate native QA task. Missing or failing audit never implies success; unsupported extra reads stop batching.'}
    return view


def normalize(kernel, submitted):
    """Bind host-authored findings to current bytes, not a claim of host cognition."""
    if not enabled(kernel.project):
        raise ValueError('core-result requires a new lean minimal-core project')
    if not isinstance(submitted, dict) or submitted.get('schema') != RESULT:
        raise ValueError('Expected core-result/1.0')
    state = kernel.state
    task_id = submitted.get('task_id')
    if task_id != state.get('active_task'):
        raise ValueError('Core result is not for the active task')
    task = read(kernel.path('runtime/tasks/' + task_id + '.json'))
    if digest(task) != state.get('active_task_sha256') or not kernel.dependencies_valid(task['dependencies']):
        raise ValueError('Stale or changed core task')
    if not (submitted.get('conflicts') or submitted.get('unresolved')) and submitted.get('read_ack') is not True:
        raise ValueError('Core result needs explicit read_ack of the presented task and readings')
    # Re-read exact bytes, including the locked module integrity check in modules().
    if task.get('module'):
        kernel.modules(task['module']['name'])
    view = packet(task)
    result = deepcopy(submitted)
    if 'core_audit' in result:
        raise ValueError('Core audit provenance is generated by the runtime')
    if 'delivery_audit' in result and task['kind']!='compile-review':
        raise ValueError('Only the compile review can batch a final audit')
    for key in ('read_ack', 'core_audit'):
        result.pop(key, None)
    # Never accept caller-supplied automatic evidence or contradictory bindings.
    for key in ('module_receipt', 'validator', 'context_fingerprint'):
        if key in result:
            raise ValueError('Core result must not author runtime field: ' + key)
    result.update(schema=task['expected_result'], context_fingerprint=task['context_fingerprint'])
    result['core_audit'] = {'policy': POLICY, 'host_input_sha256': digest(submitted),
                          'view_sha256': digest(view), 'read_ack': submitted.get('read_ack') is True,
                          'semantic_assessment': 'HOST_DECLARED', 'media_quality': 'NOT_RUN'}
    if submitted.get('conflicts') or submitted.get('unresolved'):
        return task, result
    if result.get('artifact'):
        path = Path(result['artifact']).expanduser().resolve()
        actual = digest_file(path)
        if result.get('artifact_sha256', actual) != actual:
            raise ValueError('Declared native artifact bytes changed')
        result['artifact_sha256'] = actual
        result['artifact'] = str(path)
    if result.get('manifest'):
        actual = digest_file(Path(result['manifest']))
        if result.get('manifest_sha256', actual) != actual:
            raise ValueError('Declared manifest bytes changed')
        result['manifest_sha256'] = actual
    module = task.get('module')
    if module:
        result['module_receipt'] = {k: module[k] for k in ('name', 'version', 'skill_sha256')}
        result['module_receipt']['reads'] = [{'path': r['path'], 'sha256': r['sha256']}
                                           for r in module.get('required_reads', [])]
    if task['kind'] == 'canon' and isinstance(result.get('craft_context'), dict):
        from .craft_runtime import source_hash
        context = result['craft_context']
        actual = source_hash(kernel)
        if context.get('source_sha256', actual) != actual:
            raise ValueError('Declared craft source changed')
        context['source_sha256'] = actual
    if result.get('craft_review'):
        from . import craft_runtime, craft_router
        artifact = craft_runtime.evidence_artifact(kernel, task, result)
        result['craft_review'] = craft_router.bind_review(task['craft'], result['craft_review'], artifact)
    return task, result


def submit_final(kernel, submitted):
    """Two native review receipts, one explicit host response, atomic local writes."""
    from .transactions import transaction
    if not enabled(kernel.project) or submitted.get('schema') != RESULT:
        raise ValueError('Batched final audit requires minimal core results')
    if submitted.get('conflicts') or submitted.get('unresolved'):
        return kernel.submit(submitted), None
    audit = deepcopy(submitted.get('delivery_audit'))
    if not isinstance(audit, dict) or audit.get('passed') is not True or not audit.get('checks'):
        raise ValueError('Final audit must be host-authored, passing and contain actual findings')
    with transaction(kernel.root):
        task = read(kernel.path('runtime/tasks/' + str(submitted.get('task_id')) + '.json'))
        if task.get('kind') != 'compile-review' or audit.get('build_id') != task['build']['build_id']:
            raise ValueError('Final audit must bind the compile review of the same build')
        receipt = kernel.submit(submitted)
        if receipt['status'] not in ('ACCEPTED', 'ALREADY_ACCEPTED'):
            return receipt, None
        value = kernel.run()
        if receipt['status']=='ALREADY_ACCEPTED' and kernel.valid('qa'):
            if kernel.state['build']['build_id'] != audit['build_id']:
                raise ValueError('Cannot reuse final audit for a changed build')
            return receipt, value
        qa = value.get('task') or {}
        if qa.get('kind') != 'qa' or qa.get('build', {}).get('build_id') != audit['build_id']:
            raise ValueError('Final audit batching stopped: next native task/build changed')
        read_hashes={r['sha256'] for r in (task.get('module') or {}).get('required_reads', [])}
        if any(r['sha256'] not in read_hashes for r in (qa.get('module') or {}).get('required_reads', [])):
            raise ValueError('Final audit batching needs additional reads; submit separate QA')
        for key, expected in [('project_id', kernel.project['project_id']),
                              ('compile_review_build_id', audit['build_id'])]:
            if audit.get(key,expected) != expected:
                raise ValueError('Final audit identity differs: '+key)
            audit[key]=expected
        # Use the native proposed output path; never overwrite an accepted artifact.
        path = Path(qa.get('output_file') or kernel.path('artifacts/qa-draft-'+qa['task_id']+'.json'))
        kernel.write(str(path.relative_to(kernel.root)), audit)
        qa_result={'schema':RESULT, 'task_id':qa['task_id'], 'read_ack':True,
                   'artifact':str(path), 'checks':deepcopy(audit['checks']),
                   'conflicts':[], 'unresolved':[],
                   'review_origin':{'type':'host-batched-final-audit','task_id':task['task_id']}}
        qa_receipt=kernel.submit(qa_result)
        if qa_receipt['status'] not in ('ACCEPTED','ALREADY_ACCEPTED'):
            raise ValueError('Native final audit did not pass')
        receipt['final_audit_receipt']=qa_receipt
        return receipt, kernel.run()
