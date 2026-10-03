"""Default-on professional method routing over native tasks, not another content IR.

Canon's RoleResult carries host-authored semantic retrieval features. Decisions
live in frozen task envelopes; adoption evidence lives in existing RoleResults.
The kernel checks provenance and coverage, not artistic merit.
"""
from __future__ import annotations

from pathlib import Path
from . import craft_router as router
from .v5_modules import read, digest_file
from .v5_adapters import digest

POLICY = router.POLICY
CREATORS = set(router.ROLES)
CONSUMERS = {'image-prompt', 'avir', 'compile-review'}
PRIMARY_PATHS = {'screenplay': '/task/style_request', 'director': '/intent/style_request',
                 'art': '/brief/locked_style', 'storyboard': '/style/primary'}


def enabled(kernel):
    return kernel.project.get('craft_policy') == POLICY


def corpus(kernel):
    """Use real source text or registered reviewed observations; never decode images as text."""
    rows = {}
    for item in kernel.state['sources']:
        path = kernel.path(item['uri'])
        if digest_file(path) != item['sha256']:
            raise ValueError('Craft source bytes changed')
        if path.suffix.lower() in ('.txt', '.md', '.json', '.csv', '.yaml', '.yml', '.srt'):
            try:
                rows[item['id']] = path.read_text(encoding='utf-8')
            except UnicodeError as error:
                raise ValueError('Craft source needs a verified text extraction') from error
    for item in kernel.observation_status():
        for record in item.get('records', []):
            rows[item['source_id']] = (rows.get(item['source_id'], '') + '\n' +
                                      router.encoded(record['review']).decode())
    return rows


def source_hash(kernel):
    return digest(kernel.source_fingerprint_inputs())


def check_context(kernel, context, observed_artifact=None):
    if not isinstance(context, dict) or context.get('source_sha256') != source_hash(kernel):
        raise ValueError('Missing or stale craft_context in Canon RoleResult')
    if set(context.get('roles', {})) != CREATORS:
        raise ValueError('craft_context must cover the four creative responsibilities')
    actual = corpus(kernel)
    for role, entry in context['roles'].items():
        if not isinstance(entry, dict):
            raise ValueError('Craft role analysis must be an object')
        features = router.features(entry.get('features'))
        if not features.get('goal') or not features.get('tags'):
            raise ValueError('Craft role analysis needs a goal and semantic tags')
        evidence = entry.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('Craft role features need source evidence')
        for row in evidence:
            if not isinstance(row, dict) or not isinstance(row.get('quote'), str) or not row['quote'].strip():
                raise ValueError('Craft feature evidence needs a nonempty quote')
            kind = row.get('kind', 'source')
            if kind == 'observation':
                original = next((r for r in kernel.state['sources'] if r['id'] == row.get('source_id')), None)
                if (not original or row.get('source_sha256') != original['sha256']
                        or not isinstance(row.get('inspection_ref'), str) or not row['inspection_ref'].strip()
                        or row.get('pointer') != '/content' or not isinstance(observed_artifact, dict)):
                    raise ValueError('Observed craft evidence needs frozen source bytes, actual inspection reference and Canon content')
                text = observed_artifact.get('content', '')
            elif kind == 'source':
                text = actual.get(row.get('source_id'), '')
            else:
                raise ValueError('Unknown craft source evidence kind')
            if not isinstance(text, str) or row['quote'] not in text:
                raise ValueError('Craft feature evidence is not in its registered source/observation')
        # A named override is a user constraint, not an unexplained hidden author preference.
        requested = features.get('requested')
        if requested:
            text = '\n'.join(actual.values()).casefold()
            aliases = [requested.casefold()]
            cards = router.catalog(kernel.modules(router.ROLES[role]), role)
            for card in cards:
                for person in card['practitioners']:
                    if requested.casefold() in (person['name'].casefold(), person['alias'].casefold()):
                        aliases.extend([person['name'].casefold(), person['alias'].casefold()])
            if not any(a and a in text for a in aliases):
                raise ValueError('Explicit craft override needs an actual user-source reference')
    return context


def proof_result(kernel, record):
    proof = record.get('craft_proof') or {}
    if not proof.get('uri') or digest_file(kernel.path(proof['uri'])) != proof.get('sha256'):
        raise ValueError('Accepted craft evidence is missing or changed')
    result = read(kernel.path(proof['uri']))
    if kernel.state['completed_tasks'].get(result.get('task_id')) != digest(result):
        raise ValueError('Craft evidence has no accepted task receipt')
    return result


def context_for(kernel):
    record = kernel.state['artifacts'].get('canon') or {}
    return check_context(kernel, proof_result(kernel, record).get('craft_context'), kernel.data('canon'))


def inherited_rules(kernel, dependencies):
    """Direct edges retain source references. Transitive design stays in native handoffs."""
    rows = []
    seen = set()
    for dependency in dependencies:
        slot = dependency['slot']
        record = kernel.state['artifacts'].get(slot)
        if not record or record['kind'] not in CREATORS:
            continue
        result = proof_result(kernel, record)
        task = read(kernel.path('runtime/tasks/' + result['task_id'] + '.json'))
        plan = task.get('craft') or {}
        if plan.get('plan_sha256') != (result.get('craft_review') or {}).get('plan_sha256'):
            raise ValueError('Upstream craft proof differs from its frozen task')
        own_ids = {r['id'] for r in plan.get('rules', [])}
        by_id = {r['id']: r for r in plan.get('rules', []) + plan.get('inherited', [])}
        for application in result['craft_review']['applications']:
            if application['status'] != 'applied' or application['id'] not in by_id:
                continue
            rule = by_id[application['id']]
            identifier = slot + '/' + application['id'] if application['id'] in own_ids else application['id']
            if identifier in seen:
                continue
            seen.add(identifier)
            rows.append({'id': identifier, 'instruction': rule['instruction'],
                         'check': application['check'], 'source_slot': slot,
                         'source_artifact_sha256': record['sha256'],
                         'source_pointer': application['pointer'], 'scope': record.get('scope', {})})
    return rows


def combine_features(base, local):
    # Explicit user requests/negative constraints win over local creative suggestions.
    merged = {**base, **local}
    if base.get('requested'):
        merged['requested'] = base['requested']
    for key in ('forbidden_profiles', 'forbidden_techniques'):
        merged[key] = sorted(set(base.get(key, [])) | set(local.get(key, [])))
    return router.features(merged)


def scene_query(director, scene_id):
    scene = next(s for s in director['scenes'] if s['id'] == scene_id)
    return router.encoded({'scene': scene, 'shots': [s for s in director.get('shots', [])
                                                  if s.get('scene_id') == scene_id]}).decode()


def check_scene_routes(kernel, artifact, result):
    routes = result.get('craft_scene_routes')
    scenes = {s['id']: i for i, s in enumerate(artifact.get('scenes', []))}
    if not isinstance(routes, dict) or set(routes) != set(scenes):
        raise ValueError('Director result needs craft_scene_routes for every native scene')
    context = context_for(kernel)
    groups = {}
    for sid, entry in routes.items():
        if not isinstance(entry, dict) or not isinstance(entry.get('continuity_group'), str) or not entry['continuity_group'].strip():
            raise ValueError('Scene craft route needs a continuity_group')
        if set(entry.get('features', {})) != {'art', 'storyboard'}:
            raise ValueError('Scene routing describes art/storyboard needs, not new story facts')
        evidence = entry.get('evidence') or {}
        pointer = evidence.get('pointer', '')
        if not pointer.startswith('/scenes/' + str(scenes[sid]) + '/'):
            raise ValueError('Scene routing evidence must refer to its own native scene')
        try:
            actual = router.pointer(artifact, pointer)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError('Scene routing evidence pointer is invalid') from error
        if (not isinstance(actual, str) or not isinstance(evidence.get('quote'), str)
                or len(evidence['quote'].strip()) < 2 or evidence['quote'] not in actual):
            raise ValueError('Scene routing quote is absent from its scene')
        for role, local in entry['features'].items():
            router.features(local)
            if not local.get('goal') or not local.get('tags') or local.get('requested'):
                raise ValueError('Scene routing needs semantic goals/tags; named requests belong to user context')
            features = combine_features(context['roles'][role]['features'], local)
            plan = router.route(kernel.modules(router.ROLES[role]), role, scene_query(artifact, sid), features)
            # An unbroken set keeps its material/world grammar; different action beats
            # may legitimately use different storyboard grammar inside that same set.
            if role == 'art':
                group = entry['continuity_group']
                signature = (plan['primary'], features.get('world_mode'), features.get('medium'))
                if group in groups and groups[group] != signature:
                    raise ValueError('Art grammar conflicts inside one continuity group')
                groups[group] = signature
    return routes


def scene_routes_for(kernel):
    record = kernel.state['artifacts'].get('director')
    if not record:
        return {}, None
    result = proof_result(kernel, record)
    director = kernel.data('director')
    return check_scene_routes(kernel, director, result), director


def task_plan(kernel, kind, slot, dependencies, scope):
    if not enabled(kernel) or kind not in CREATORS | CONSUMERS | {'canon'}:
        return None
    if kind == 'canon':
        return {'policy': POLICY, 'status': 'SEMANTIC_ANALYSIS_REQUIRED',
                'source_sha256': source_hash(kernel), 'roles': sorted(CREATORS),
                'instruction': 'In craft_context, supply source_sha256 and roles: each role has features '
                '(goal, tags, optional task/world_mode/medium/requested/forbidden_profiles/forbidden_techniques) '
                'and evidence [{source_id, quote}]. For non-text sources, use kind=observation, source_sha256, '
                'pointer=/content, quote from actual Canon observations and inspection_ref for the real host read; '
                'these are host-declared observations, never original quotations or media-quality proof. '
                'Interpret the real brief; do not force narrative on tutorials. '
                'requested is only an explicit user reference. No new facts, no full-library read, no quality claim.'}
    context = context_for(kernel)
    inherited = inherited_rules(kernel, dependencies)
    if kind in CREATORS:
        observations = {e['quote'] for entry in context['roles'].values() for e in entry['evidence'] if e.get('kind') == 'observation'}
        query = '\n'.join([*corpus(kernel).values(), *sorted(observations)])
        features = context['roles'][kind]['features']
        scenes, director = scene_routes_for(kernel) if kind in ('art', 'storyboard') else ({}, None)
        scene_ids = (scope or {}).get('scene_ids') or list(scenes)
        if (scope or {}).get('shot_ids') and director:
            scene_ids = sorted({s['scene_id'] for s in director.get('shots', []) if s['id'] in scope['shot_ids']})
        if kind == 'art':
            if len(scene_ids) != 1 or scene_ids[0] not in scenes:
                raise ValueError('Art craft routing requires one known frozen scene')
            features = combine_features(features, scenes[scene_ids[0]]['features']['art'])
            query = scene_query(director, scene_ids[0])
        # Context chooses the stable project grammar. Scoped native inputs govern its implementation,
        # not random rerouting from a single incidental word in a late scene.
        plan = router.route(kernel.modules(router.ROLES[kind]), kind, query, features,
                            scope=scope, inherited=inherited)
        if kind == 'storyboard':
            plan['scene_profiles'] = []
            for sid in scene_ids:
                local = combine_features(features, scenes[sid]['features']['storyboard'])
                scoped = router.route(kernel.modules(router.ROLES[kind]), kind, scene_query(director, sid), local, scope={'scene_ids': [sid]})
                plan['scene_profiles'].append({'scene_id': sid, 'primary': scoped['primary'], 'goal': local['goal']})
                if scoped['primary'] != plan['primary']:
                    for rule in scoped['rules']:
                        plan['rules'].append({**rule, 'id': 'scene:' + sid + '/' + rule['id'], 'scope': {'scene_ids': [sid]}})
                    plan['sources'].extend(scoped['sources'])
        if kind == 'art':
            plan['continuity_group'] = scenes[scene_ids[0]]['continuity_group']
        if kind == 'director':
            plan['scene_route_instruction'] = ('Set scenes[].style_id consistently with the native primary grammar. Return craft_scene_routes keyed by every native scene id. Each entry has continuity_group, '
                'features {art: {goal,tags,...}, storyboard: {goal,tags,...}}, and evidence {pointer,quote} in that native scene. '
                'Describe the scene needs; downstream roles select their methods. Same unbroken set uses the same art grammar.')
        plan['native_primary_pointer'] = PRIMARY_PATHS[kind]
        plan['instruction'] = ('Apply this grammar within the frozen task scope. Keep one project primary; '
                               'specialize the techniques to this scene/shot without changing upstream locks. '
                               'If unsuitable, return a scoped conflict to the Canon/creative owner, not a silent override. '
                               'The person is a project reference, not a verified quote or a rendering instruction.')
    else:
        plan = {'policy': POLICY, 'role': kind, 'scope': scope or {}, 'rules': [],
                'inherited': inherited, 'status': 'INHERIT_NOT_REROUTE', 'media_quality': 'NOT_RUN',
                'instruction': 'Preserve upstream methods in the actual prompt/AVIR; do not invent a new style. '
                'Image tasks may mark narrative timing not_applicable with scope evidence. '
                'Compile review pointers target the frozen build avir.json, not review prose.'}
    from . import prompt_methods
    prompt_methods.attach(kernel, kind, plan, features if kind in CREATORS else None)
    plan['source_sha256'] = source_hash(kernel)
    plan['input_artifacts'] = [{k: v for k, v in d.items()} for d in dependencies]
    plan.pop('plan_sha256', None)
    plan['plan_sha256'] = router.digest(plan)
    return plan


def attach(kernel, kind, slot, dependencies, scope, extra, reads):
    plan = task_plan(kernel, kind, slot, dependencies, scope)
    if plan is None:
        return
    extra['craft'] = plan
    from .workspace import enabled as compact_workspace
    if kind == 'canon' or compact_workspace(kernel.project):
        return
    # One selected excerpt, not every referenced full registry. The source hashes are
    # validated against the locked module; the host reads the actual selected rule text.
    relative = 'runtime/craft/' + plan['plan_sha256'] + '.json'
    kernel.write(relative, plan)
    reads.append({'path': str(kernel.path(relative)), 'relative': 'craft:selected-methods',
                  'sha256': digest_file(kernel.path(relative))})


def evidence_artifact(kernel, task, result):
    if task['kind'] == 'image-prompt':
        return {'prompt': result.get('prompt')}
    if task['kind'] == 'compile-review':
        return read(kernel.path(task['build']['uri'] + '/avir.json'))
    path = Path(result.get('artifact') or '')
    if not path.is_file() or digest_file(path) != result.get('artifact_sha256'):
        raise ValueError('Craft review needs the current native artifact and its hash')
    return read(path)


def check(kernel, task, result):
    if not enabled(kernel) or task['kind'] not in CREATORS | CONSUMERS | {'canon'}:
        return
    plan = task.get('craft')
    if not isinstance(plan, dict) or plan.get('policy') != POLICY:
        raise ValueError('Craft routing is required for this task')
    if plan.get('source_sha256') != source_hash(kernel):
        raise ValueError('Craft source context changed since task dispatch')
    if task['kind'] == 'canon':
        check_context(kernel, result.get('craft_context'), evidence_artifact(kernel, task, result))
        return
    if task['kind'] in CREATORS:
        module_root = kernel.modules(router.ROLES[task['kind']])
        for source in plan['sources']:
            path = (module_root / source['path']).resolve()
            if not path.is_relative_to(module_root.resolve()) or digest_file(path) != source['sha256']:
                raise ValueError('Selected craft source bytes changed')
            if source.get('locator'):
                router.pointer(read(path), source['locator'])
    from . import prompt_methods
    prompt_methods.check(kernel, plan)
    artifact = evidence_artifact(kernel, task, result)
    if task['kind'] in CREATORS:
        try:
            primary = router.pointer(artifact, plan['native_primary_pointer'])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError('Native primary grammar is missing') from error
        if primary != plan['primary']:
            raise ValueError('Native primary grammar differs from the selected craft plan; request rerouting')
    router.validate_review(plan, result.get('craft_review'), artifact)
    if task['kind'] == 'director':
        check_scene_routes(kernel, artifact, result)
    if task['kind'] == 'storyboard':
        rules = {r['id']: r for r in plan['rules']}
        for row in result['craft_review']['applications']:
            required_scenes = (rules.get(row['id'], {}).get('scope') or {}).get('scene_ids', [])
            if required_scenes and row['status'] == 'applied':
                parts = row['pointer'].split('/')
                if len(parts) < 4 or parts[1] not in ('shots', 'scenes'):
                    raise ValueError('Scene craft evidence must point to its scene or shot')
                owner = router.pointer(artifact, '/' + '/'.join(parts[1:3]))
                sid = owner.get('scene_id') if parts[1] == 'shots' else owner.get('id')
                if sid not in required_scenes:
                    raise ValueError('Scene craft evidence points to another scene')


def record(kernel, task, result, state):
    if not enabled(kernel) or task['kind'] not in CREATORS | {'canon'}:
        return
    target = state['artifacts'].get(task['slot'])
    if target is None:
        raise ValueError('Craft proof needs an accepted native artifact')
    from .workspace import relative
    target['craft_proof'] = {'uri': relative(kernel.project, 'runtime/results/' + task['task_id'] + '.json'),
                             'sha256': digest(result), 'policy': POLICY}


def proof_valid(kernel, record):
    if not enabled(kernel) or record['kind'] not in CREATORS | {'canon'}:
        return True
    try:
        result = proof_result(kernel, record)
        task = read(kernel.path('runtime/tasks/' + result['task_id'] + '.json'))
        if task['kind'] == 'canon':
            check_context(kernel, result.get('craft_context'), kernel.data(record['slot']))
        else:
            plan = task['craft']
            if plan.get('source_sha256') != source_hash(kernel):
                return False
            # Snapshot rebasing can change external paths; bind quoted implementation strings,
            # not absolute originals. Native artifact hash is already checked by V5Kernel.valid.
            from . import prompt_methods
            prompt_methods.check(kernel, plan)
            router.validate_review(plan, result.get('craft_review'), kernel.data(record['slot']))
        return True
    except (OSError, KeyError, TypeError, ValueError, IndexError):
        return False
