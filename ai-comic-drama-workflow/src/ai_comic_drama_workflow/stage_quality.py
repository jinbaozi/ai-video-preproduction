"""Evidence coverage for studio stages; never an automatic semantic reviewer.

Lives in native task/result receipts, not a parallel story IR. Only newly
configured projects opt in; existing projects retain their frozen contract.
"""
from pathlib import Path
from .v5_adapters import digest
from .v5_modules import read, digest_file
from .craft_router import pointer

POLICY = 'studio-quality/1.0'
CHECKS = {
    'screenplay': {
        'knowledge_trigger': 'What the character knows before/after this event, and the visible information that changes it.',
        'motivation': 'Why this action follows from that knowledge and goal; distinguish a plausible option from an established fact.',
        'time_order': 'Prior action, elapsed time and ellipsis; no future knowledge or unprepared consequence.',
        'resource_origin': 'Origin, preparation, availability and custody of props/food/clothes; explain offscreen preparation or why none is involved.'},
    'director': {
        'causal_realization': 'Realize upstream causality in observable performance; do not fix story facts by silent staging changes.',
        'camera_and_eyeline': 'Separate world/screen/body left-right; show the information from an achievable viewpoint.',
        'action_and_sound': 'Readable contact, action/reaction order and sound trigger; duration is provisional until actual audio.'},
    'art': {
        'identity_and_reference': 'Stable identity, costume variables and momentary state; each real reference has a responsibility and exclusions.',
        'space_and_prop_origin': 'Topology, light sources, material, prop custody and narrative preparation; no unexplained breakfast.',
        'visible_detail': 'Complete visible useful detail, not vague realism labels; no invented observation of unread references.'},
    'storyboard': {
        'purpose_camera': 'Purpose, framing, camera height/direction, eyeline and separate camera/subject trajectories.',
        'start_action_end': 'Start state, ordered contact/actions, end state and legal cut, including hand/prop state.',
        'sound_time_continuity': 'Speaker, exact line, sound trigger, timing evidence and adjacent continuity; no silent upstream rewrite.'},
    'image-prompt': {
        'identity_reference_scope': 'Identity anchors, reference duties/exclusions, visible costume and momentary expression.',
        'composition_contact_light': 'Single visible instant, framing, viewpoint, gaze, hands/contact, occlusion and physically motivated light.',
        'prompt_parameter_boundary': 'Executable text separate from parameters and attachment bindings; unread reference remains blocked.'},
    'avir': {
        'native_preservation': 'Preserve frozen identity, dialogue, hand, prop, start/end and causal constraints.',
        'entry_and_bindings': 'Exact target/mode and supported reference/audio responsibilities; unknown capabilities remain blocked.',
        'segments_and_timing': 'Complete per-segment prompts, legal cuts, duration and audio evidence; no invented submission.'},
}

CHECKS['compile-review'] = CHECKS['avir']

def enabled(project):
    return project.get('quality_policy') == POLICY


def contract(kind):
    return {'policy': POLICY, 'status': 'HOST_REVIEW_REQUIRED', 'checks': CHECKS[kind],
            'scope_rule': 'screenplay: every /narrative/events/N; director/storyboard: every /shots/N (or /scenes/N if no shots); other kinds: root (empty string).',
            'result_shape': {'policy': POLICY, 'artifact_sha256': 'runtime binds bytes for core-result',
                'findings': [{'scope': 'native pointer', 'check': 'required check id', 'status': 'PASS or FAIL',
                    'finding': 'actual explanation, including non-applicability if appropriate',
                    'evidence': [{'pointer': 'non-root native pointer', 'quote': 'exact nonempty text at that pointer'}]}]},
            'limits': 'Coverage and byte binding only. A host PASS is not proof of real-world plausibility or media quality. No word-count quota.'}


def scopes(kind, artifact):
    if kind == 'screenplay':
        events = (artifact.get('narrative') or {}).get('events')
        if not isinstance(events, list) or not events:
            raise ValueError('Studio quality needs native screenplay events, including non-dramatic steps')
        return ['/narrative/events/'+str(i) for i in range(len(events))]
    if kind in ('director', 'storyboard'):
        key = 'shots' if artifact.get('shots') else 'scenes'
        if not isinstance(artifact.get(key), list) or not artifact[key]:
            raise ValueError('Studio quality needs native scene/shot scope')
        return ['/'+key+'/'+str(i) for i in range(len(artifact[key]))]
    return ['']


def validate(kind, artifact, review, sha):
    if not isinstance(review, dict) or review.get('policy') != POLICY or review.get('artifact_sha256') != sha:
        raise ValueError('Missing or stale quality_review bound to the current native artifact')
    expected = {(scope, key) for scope in scopes(kind, artifact) for key in CHECKS[kind]}
    findings = review.get('findings')
    if not isinstance(findings, list):
        raise ValueError('Quality findings must cover every scoped check')
    seen = set()
    for row in findings:
        if not isinstance(row, dict):raise ValueError('Quality finding must be an object')
        pair = (row.get('scope'), row.get('check'))
        if pair not in expected or pair in seen:raise ValueError('Unknown or duplicate quality scope/check')
        seen.add(pair)
        if row.get('status') != 'PASS':raise ValueError('Failed quality finding blocks stage acceptance: '+str(pair))
        if not isinstance(row.get('finding'), str) or not row['finding'].strip():raise ValueError('Quality finding needs an actual explanation')
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or not evidence:raise ValueError('Quality finding needs native evidence')
        for item in evidence:
            if not isinstance(item, dict):raise ValueError('Quality evidence must be an object')
            path, quote = item.get('pointer'), item.get('quote')
            if not isinstance(path, str) or not path.startswith('/') or not isinstance(quote, str) or not quote.strip():
                raise ValueError('Quality evidence needs a non-root pointer and a nonempty quote')
            if any(part in {'id','source_refs','sha256','schema','schema_version','style_id'} for part in path.split('/')):
                raise ValueError('Quality evidence must cite substantive native text, not identifiers or metadata')
            try:text = pointer(artifact, path)
            except (KeyError, IndexError, TypeError, ValueError) as error:raise ValueError('Quality evidence pointer is invalid') from error
            if not isinstance(text, str) or quote not in text:raise ValueError('Quality quote is absent from native text')
        # Every row must cite its own event/shot, not an unrelated scene or only a global assertion.
        if pair[0] and not any(e['pointer'].startswith(pair[0]+'/') for e in evidence):
            raise ValueError('Quality evidence must include its own event/shot scope')
    if seen != expected:raise ValueError('Missing scoped quality checks: '+str(sorted(expected-seen)))


def material(task, result, kernel=None):
    if task['kind'] == 'compile-review':
        path=kernel.path(task['build']['uri']+'/avir.json')
        return read(path), digest_file(path)
    if task['kind'] == 'image-prompt':
        artifact = {'prompt': result.get('prompt'), 'params': result.get('params'), 'understanding': result.get('understanding')}
        return artifact, digest(artifact)
    path = Path(result.get('artifact') or '')
    return read(path), digest_file(path)


def check(kernel, task, result):
    if not enabled(kernel.project) or task['kind'] not in CHECKS:return
    if task.get('quality_contract') != contract(task['kind']):raise ValueError('Missing frozen quality contract')
    artifact, sha = material(task, result, kernel)
    review = result.get('quality_review')
    validate(task['kind'], artifact, review, sha)


def record(kernel, task, result, state):
    if not enabled(kernel.project) or task['kind'] not in CHECKS:return
    target = state.get('compile_review') if task['kind']=='compile-review' else (state['prompts'] if task['kind']=='image-prompt' else state['artifacts']).get(task['slot'])
    if target is not None:
        from .workspace import relative
        target['quality_proof'] = {'uri': relative(kernel.project, 'runtime/results/'+task['task_id']+'.json'),
                                   'sha256': digest(result), 'policy': POLICY}


def proof_valid(kernel, record):
    if not enabled(kernel.project) or record.get('kind') not in CHECKS:return True
    try:
        proof = record['quality_proof'];result = read(kernel.path(proof['uri']))
        if digest(result)!=proof['sha256'] or kernel.state['completed_tasks'].get(result['task_id'])!=proof['sha256']:return False
        # Native promotion can rebase references. Validate quotes on the current authoritative artifact,
        # while the immutable receipt retains the submitted-byte hash.
        validate(record['kind'], kernel.data(record['slot']), result['quality_review'], result['quality_review']['artifact_sha256'])
        return True
    except (OSError, KeyError, TypeError, ValueError, IndexError):return False


def prompt_proof_valid(kernel, record):
    if not enabled(kernel.project):return True
    try:
        proof=record['quality_proof'];result=read(kernel.path(proof['uri']))
        if digest(result)!=proof['sha256'] or kernel.state['completed_tasks'].get(result['task_id'])!=proof['sha256']:return False
        task=read(kernel.path('runtime/tasks/'+result['task_id']+'.json'))
        if not kernel.dependencies_valid(task['dependencies']):return False
        if kernel.path(record['uri']).read_text()!=result['prompt']:return False
        if record.get('params')!=result.get('params') or record.get('understanding')!=result.get('understanding'):return False
        artifact,sha=material(task,result);validate('image-prompt',artifact,result['quality_review'],sha)
        return True
    except (OSError,KeyError,TypeError,ValueError,IndexError):return False


def compile_proof_valid(kernel):
    if not enabled(kernel.project):return True
    try:
        record=kernel.state['compile_review'];proof=record['quality_proof'];result=read(kernel.path(proof['uri']))
        if digest(result)!=proof['sha256'] or kernel.state['completed_tasks'].get(result['task_id'])!=proof['sha256']:return False
        task=read(kernel.path('runtime/tasks/'+result['task_id']+'.json'))
        if not kernel.dependencies_valid(task['dependencies']) or task['build']['build_id']!=kernel.state['build']['build_id']:return False
        artifact,sha=material(task,result,kernel);validate('compile-review',artifact,result['quality_review'],sha)
        return True
    except (OSError,KeyError,TypeError,ValueError,IndexError):return False


def report(kernel):
    """Read-only projection. A selected plan without an accepted receipt is never adoption."""
    state=kernel.state;rows=[]
    for slot, record in state['artifacts'].items():
        task_id=None;result=None;task={}
        proof=record.get('quality_proof') or record.get('craft_proof')
        if proof:
            try:
                candidate=read(kernel.path(proof['uri']))
                if digest(candidate)==proof['sha256'] and state['completed_tasks'].get(candidate.get('task_id'))==proof['sha256']:
                    result=candidate;task_id=result['task_id'];task=read(kernel.path('runtime/tasks/'+task_id+'.json'))
            except (OSError,ValueError,KeyError):pass
        plan=task.get('craft') or {}
        valid=kernel.valid(slot)
        rows.append({'slot':slot,'kind':record['kind'],'native_status':'ACCEPTED' if valid else 'STALE_OR_UNREVIEWED',
            'task_id':task_id,'result_file':str(kernel.path(proof['uri'])) if proof else None,'primary':plan.get('primary'),'practitioner':plan.get('practitioner'),
            'method_evidence':'ACCEPTED_HOST_DECLARED' if valid and result and result.get('craft_review') else 'NOT_RECORDED',
            'quality_evidence':'ACCEPTED_HOST_DECLARED' if valid and result and result.get('quality_review') else 'NOT_RECORDED'})
    for slot, record in state.get('prompts', {}).items():
        proof=record.get('quality_proof');result=None;plan={}
        if proof:
            try:
                candidate=read(kernel.path(proof['uri']))
                if digest(candidate)==proof['sha256'] and state['completed_tasks'].get(candidate.get('task_id'))==proof['sha256']:
                    result=candidate;task=read(kernel.path('runtime/tasks/'+result['task_id']+'.json'));plan=task.get('craft') or {}
            except (OSError,ValueError,KeyError):pass
        valid=kernel.prompt_valid(record)
        rows.append({'slot':slot,'kind':'image-prompt','native_status':'ACCEPTED' if valid else 'STALE_OR_UNREVIEWED',
            'task_id':result.get('task_id') if result else None,'result_file':str(kernel.path(proof['uri'])) if proof else None,'primary':plan.get('primary'),'practitioner':plan.get('practitioner'),
            'method_evidence':'ACCEPTED_HOST_DECLARED' if valid and result and result.get('craft_review') else 'NOT_RECORDED',
            'quality_evidence':'ACCEPTED_HOST_DECLARED' if valid and result and result.get('quality_review') else 'NOT_RECORDED'})
    compile_record=state.get('compile_review') or {}
    if compile_record.get('quality_proof'):
        try:
            result=read(kernel.path(compile_record['quality_proof']['uri']))
            task=read(kernel.path('runtime/tasks/'+result['task_id']+'.json'));plan=task.get('craft') or {}
            valid=compile_proof_valid(kernel)
            rows.append({'slot':'compile-review','kind':'compile-review','native_status':'ACCEPTED' if valid else 'STALE_OR_UNREVIEWED',
                'task_id':result['task_id'],'result_file':str(kernel.path(compile_record['quality_proof']['uri'])),'primary':plan.get('primary'),'practitioner':plan.get('practitioner'),
                'method_evidence':'ACCEPTED_HOST_DECLARED' if valid and result.get('craft_review') else 'NOT_RECORDED',
                'quality_evidence':'ACCEPTED_HOST_DECLARED' if valid else 'NOT_RECORDED'})
        except (OSError,KeyError,ValueError):rows.append({'kind':'compile-review','native_status':'STALE_OR_UNREVIEWED'})
    active=None
    if state.get('active_task'):
        try:
            task=read(kernel.path('runtime/tasks/'+state['active_task']+'.json'));plan=task.get('craft') or {}
            active={'task_id':task['task_id'],'kind':task['kind'],'primary':plan.get('primary'),
                    'practitioner':plan.get('practitioner'),'status':'SELECTED_NOT_ADOPTED' if plan.get('primary') else 'AWAITING_NATIVE_RESULT'}
        except (OSError,ValueError,KeyError):active={'status':'MISSING_TASK'}
    return {'craft_policy':kernel.project.get('craft_policy'), 'quality_policy':kernel.project.get('quality_policy'),
        'expected_roles':['canon','screenplay','director','art','image-prompt','image','storyboard','compile-review','qa'],'stages':rows,'active':active,'limits':'Host-declared semantics; selection is not adoption; native acceptance is not video delivery.'}
