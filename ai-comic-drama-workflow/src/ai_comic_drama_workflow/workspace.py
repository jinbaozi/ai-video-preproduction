"""Opt-in ordered storage, reference-only context and deduplicated native snapshots.

No second content IR and no garbage collection of user files or accepted evidence.
The policy is frozen at creation; legacy and audited projects retain their layout.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

POLICY = 'compact-workspace/1.0'
STAGES = {
    1: ('01-source', '资料与项目事实'), 2: ('02-screenplay', '故事与剧本'),
    3: ('03-director', '导演方案'), 4: ('04-art', '美术与服化道'),
    5: ('05-assets', '视觉资产'), 6: ('06-storyboard', '分镜与控制素材'),
    7: ('07-boards', '分镜图片'), 8: ('08-video-prompts', '视频提示词'),
    9: ('09-delivery', '验收与交付'), 10: ('10-video', '真实视频制作'),
    11: ('11-edit', '剪辑与整片验收'),
}
KINDS = {'canon': 1, 'screenplay': 2, 'director': 3, 'art': 4,
         'storyboard': 6, 'control': 6, 'avir': 8, 'qa': 9}


def enabled(project: dict) -> bool:
    return project.get('output_policy') == POLICY


def configuration(root: Path) -> dict:
    path = root / 'project.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def relative(project: dict, uri: str) -> str:
    """Map old logical names to real paths; already-real paths are unchanged."""
    if not enabled(project):
        return uri
    parts = Path(uri).parts
    if not parts:
        return uri
    first, *rest = parts
    if first == 'runtime':
        if len(rest) >= 2 and rest[0] == 'production' and rest[1] in ('outputs','editing') and project.get('editing_backend'):
            return '/'.join(['11-edit', rest[1], *rest[2:]])
        if len(rest) >= 2 and rest[0] == 'production' and rest[1] in ('media', 'outputs'):
            return '/'.join(['10-video', rest[1], *rest[2:]])
        return '/'.join(['.runtime', *rest])
    if first in ('history', 'imports'):
        return '/'.join(['.runtime', first, *rest])
    if first == 'sources':
        return '/'.join(['01-source', *rest])
    if first == 'observations':
        return '/'.join(['01-source', 'observations', *rest])
    if first == 'artifacts' and rest and rest[0] in KINDS:
        return '/'.join([STAGES[KINDS[rest[0]]][0], *rest])
    if first in ('assets', 'prompts'):
        stage = 7 if rest and rest[0].startswith('BOARD_') else 5
        return '/'.join([STAGES[stage][0], first, *rest])
    if first == 'builds':
        return '/'.join(['08-video-prompts', *rest])
    if first == 'delivery':
        return '/'.join(['09-delivery', *rest])
    return uri


def physical(root: Path, uri: str) -> Path:
    return root / relative(configuration(root), uri)


def slim_handoff(handoff: dict) -> dict:
    """Keep requirements/coordinates; field values live only in the native artifact."""
    for entry in handoff.get('inputs', []):
        for field in entry.get('fields', {}).values():
            field.pop('value', None)
    handoff['context_mode'] = 'native-pointers'
    handoff['context_instruction'] = (
        'Read inputs[].native_uri at fields[].pointer only as needed. Verify native_sha256. '
        'These pointers are not summaries: the full native content remains authoritative. '
        'All required_handoffs, coordinates, locks and craft rules still apply.')
    return handoff



def next_artifact_uri(kernel, kind, slot):
    """One reserved native output location; the host need not write a second draft."""
    prefix = STAGES[KINDS[kind]][0]
    if slot != kind:
        prefix += '/' + quote(slot.removeprefix(kind+':'), safe='_-')
    revision = kernel.state['artifacts'].get(slot, {}).get('revision', 0) + 1
    return f'{prefix}/v{revision:03d}/{kind}.json'


def snapshot(kernel, kind: str, path: Path, slot=None):
    """Deduplicate each dependency, rather than recursively cloning an entire closure.

    A promoted project file is reused only with its recorded byte hash. External
    dependencies are copied into a content-addressed store. Original bytes are
    preserved once when rebasing changes a native document. Nothing is deleted.
    """
    from .v5_modules import read, digest_file
    from .v5_adapters import encoded, digest
    path = path.resolve()
    state = kernel.state
    registered = {}
    for row in state['sources'] + list(state['media'].values()):
        registered[row['uri']] = row['sha256']
    for row in state['artifacts'].values():
        registered.update(row['files'])
        registered[row['uri']] = row['sha256']
    by_path = {kernel.path(uri): (uri, sha) for uri, sha in registered.items()}
    by_hash = {}
    for uri, sha in registered.items():
        by_hash.setdefault(sha, []).append(uri)
    cache, files, visiting = {}, {}, set()

    def reuse(source):
        record = by_path.get(source)
        if record:
            uri, sha = record
            if digest_file(source) != sha:
                raise ValueError('Registered snapshot dependency changed: ' + uri)
            files[uri] = sha
            # Include the native file's transitive dependency closure in the new record.
            for row in state['artifacts'].values():
                if row['uri'] == uri:
                    for dependency, expected in row['files'].items():
                        if digest_file(kernel.path(dependency)) != expected:
                            raise ValueError('Registered snapshot dependency changed: ' + dependency)
                        files[dependency] = expected
            return str(source)
        return None

    def store(uri, data, authored_source=None):
        dest = kernel.path(uri)
        if dest.exists() and dest.read_bytes() != data:
            # The host may write at the reserved output_file. Only that as-yet
            # unregistered draft may be rebased, with its original preserved.
            if dest != authored_source or dest in by_path:
                raise ValueError('Content-addressed snapshot was modified: ' + uri)
        kernel.write(uri, data)
        sha = hashlib.sha256(data).hexdigest()
        files[uri] = sha
        if '/objects/' in uri and uri not in by_hash.get(sha, []):
            by_hash.setdefault(sha, []).append(uri)
        return str(dest)

    def blob(source):
        source = source.resolve()
        found = reuse(source)
        if found:
            return found
        data = source.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        # Immutable byte assets may be shared even when original filenames differ.
        for uri in by_hash.get(sha, []):
            candidate = kernel.path(uri)
            if digest_file(candidate) != sha:
                raise ValueError('Registered snapshot dependency changed: ' + uri)
            files[uri] = sha
            return str(candidate)
        uri = '.runtime/objects/' + sha + '/' + source.name
        return store(uri, data)

    def capture(source, native_kind=None):
        source = source.resolve()
        if source in visiting:
            raise ValueError('Cyclic native snapshot dependency')
        if source in cache:
            return cache[source]
        found = reuse(source)
        if found:
            cache[source] = found
            return found
        visiting.add(source)
        raw = source.read_bytes()
        obj = read(source)
        review_valid = False
        if isinstance(obj.get('timeline'), dict) and isinstance(obj['timeline'].get('semantic_review'), dict):
            from .v51_detail_runtime import semantic_status
            review_valid = semantic_status(obj)
        refs = []
        for entries, field, nested in [('sources', 'uri', False), ('assets', 'path', False),
                                       ('references', 'file', False), ('upstreams', 'uri', True)]:
            for entry in obj.get(entries, []):
                old = entry.get(field)
                if old and '://' not in old:
                    if entries == 'sources' and not (source.parent / old).is_file():
                        continue
                    refs.append((entry, field, nested))
        if obj.get('schema') == 'script-ir/1.0' and obj.get('canon', {}).get('ref'):
            refs.append((obj['canon']['ref'], 'uri', True))
        if isinstance(obj.get('director'), dict):
            refs.append((obj['director'], 'uri', True))
        changed = False
        for entry, field, nested in refs:
            old = entry[field]
            if '://' in old:
                continue
            dest = capture(source.parent / old) if nested else blob(source.parent / old)
            if dest != old:
                changed = True
            entry[field] = dest
            if nested and 'sha256' in entry:
                entry['sha256'] = digest_file(dest)
        if review_valid:
            from .v51_detail_runtime import content_hash
            obj['timeline']['semantic_review']['input_sha256'] = content_hash(obj)
        data = encoded(obj) if changed else raw
        content_sha = hashlib.sha256(data).hexdigest()
        # Native roots are organized by their actual stage; shared nested imports
        # stay internal unless they are already an accepted stage artifact.
        if native_kind:
            ident = slot or ('art:' + obj['set']['scene_id'] if native_kind == 'art' else native_kind)
            uri = next_artifact_uri(kernel, native_kind, ident)
        else:
            # Reuse an accepted canonical native node after resolving all its refs.
            for existing in by_hash.get(content_sha, []):
                found = reuse(kernel.path(existing))
                if found:
                    visiting.remove(source)
                    cache[source] = found
                    return found
            uri = f'.runtime/objects/{content_sha}/native.json'
        if changed and data != raw:
            original = '.runtime/originals/' + hashlib.sha256(raw).hexdigest() + '.json'
            store(original, raw)
        cache[source] = store(uri, data, source if native_kind else None)
        visiting.remove(source)
        return cache[source]

    result = Path(capture(path, kind))
    return result.relative_to(kernel.root).as_posix(), files


def progress(kernel, outcome=None) -> dict:
    """A derived view, never an authority used to advance a state gate."""
    from .v5_modules import read, digest_file
    from .v5_adapters import digest
    state = kernel.state
    outcome = outcome or state.get('workspace_notice') or {}
    task = outcome.get('task')
    if not isinstance(task, dict) and state.get('active_task'):
        file = kernel.path('runtime/tasks/' + state['active_task'] + '.json')
        try:
            task = read(file) if file.is_file() else None
        except (ValueError, OSError):
            task = None
    valid = {slot: kernel.valid(slot, state) for slot in state['artifacts']}
    integrity = []
    for source in state['sources']:
        path = kernel.path(source['uri'])
        if not path.is_file() or digest_file(path)!=source['sha256']:
            integrity.append('Source file missing or changed: '+source['id'])
    if state.get('active_task') and (not isinstance(task, dict) or digest(task)!=state.get('active_task_sha256')):
        integrity.append('Task envelope is missing, unreadable or changed')
    if not isinstance(task, dict):
        task = None
    build = state.get('build') or {}
    build_valid = False
    if build:
        try:
            build_valid = build['input_fingerprint']==kernel.build_fingerprint() and all(
                kernel.path(p).is_file() and digest_file(kernel.path(p))==h for p,h in build['files'].items())
        except (ValueError, OSError, KeyError):
            pass
        if not build_valid:integrity.append('Compiled build is stale or changed')
    from .stage_quality import compile_proof_valid
    if state.get('compile_review', {}).get('status') == 'ACCEPTED' and not compile_proof_valid(kernel):
        integrity.append('Compile review evidence is stale or changed')
    for key,prompt in state.get('prompts', {}).items():
        if not kernel.prompt_valid(prompt):integrity.append('Image prompt evidence is stale or changed: '+key)
    rows = []
    for stage, (directory, name) in STAGES.items():
        if stage == 11 and not kernel.project.get('editing_backend'):continue
        if stage in (10,11) and kernel.production_target() != 'video':
            continue
        records = [(slot, r) for slot, r in state['artifacts'].items() if r['stage'] == stage]
        done = bool(records) and all(valid[slot] for slot, _ in records)
        status = '待执行'
        if stage in (5, 7):
            if kernel.project['delivery'] == 'text-only':
                status = '不适用（仅文字交付）'
            else:
                try:
                    jobs = kernel.image_jobs(stage) if (stage == 5 and valid.get('director') or stage == 7 and valid.get('storyboard')) else None
                    if jobs is not None:
                        done = all(j['key'] in state['media'] and kernel.media_valid(state['media'][j['key']], state)
                                   and (not kernel.project.get('flow_refinement') or bool(state['media'][j['key']].get('flow_refinement')))
                                   and state['media'][j['key']]['input_fingerprint'] == j['fingerprint']
                                   and (state['media'][j['key']]['role'] != 'identity'
                                        or state['approvals'].get(j['key'], {}).get('token') == kernel.approval_token(state['media'][j['key']]))
                                   for j in jobs)
                        if not jobs:
                            status = '不适用（无必需素材）'
                except (ValueError, OSError, KeyError):
                    status = '待处理'
        if stage == 4 and valid.get('director'):
            done = all(valid.get('art:' + scene['id']) for scene in kernel.data('director')['scenes'])
        if stage == 6 and done and kernel.current_release():
            control = state.get('control') or {}
            done = control.get('storyboard_sha256') == state['artifacts']['storyboard']['sha256'] and control.get('status') in ('READY', 'NOT_APPLICABLE')
        if stage == 8:
            build = state.get('build') or {}
            review = state.get('compile_review') or {}
            from .stage_quality import compile_proof_valid
            done = build_valid and review.get('status') == 'ACCEPTED' and review.get('build_id') == build.get('build_id') and compile_proof_valid(kernel)
        if stage == 9:
            done = state['status'] in ('DELIVERED', 'VIDEO_DELIVERED') and valid.get('qa', False) and build_valid and not integrity
        if stage in (10,11):
            done = state['status'] == 'VIDEO_DELIVERED'
            if stage==10 and kernel.project.get('editing_backend'):
                manifest=kernel.path('runtime/production/delivery-manifest.json')
                if manifest.is_file():
                    shots=read(manifest).get('shot_ids',[])
                    done=bool(shots) and all(kernel.path('runtime/production/selections/'+shot+'.json').is_file() for shot in shots)
        if done and status == '待执行':
            status = '已完成'
        if records and not all(valid[slot] for slot, _ in records):
            status = '待修订'
        if task and task.get('stage') == stage:
            status = '当前执行'
        rows.append({'stage': stage, 'directory': directory, 'name': name, 'status': status,
                     'artifacts': [{'slot': slot, 'uri': row['uri'], 'valid': valid[slot]} for slot, row in records]})
    current = next((row for row in rows if row['status'] == '当前执行'), None)
    if not current:
        current = next((row for row in rows if row['status'] in ('待执行', '待修订', '待处理')), rows[-1])
    status = outcome.get('status', state['status'])
    if integrity:status = 'BLOCKED'
    elif status in ('DELIVERED','VIDEO_DELIVERED') and not all(valid.values()):status = 'STALE'
    if status in ('ACCEPTED','ALREADY_ACCEPTED','COMPILED','UPDATED','REGISTERED'):status = state['status']
    return {'status': status, 'stage': current['stage'], 'stage_name': current['name'], 'stages': rows,
            'task_id': state.get('active_task'), 'task_file': str(kernel.path('runtime/tasks/' + state['active_task'] + '.json')) if state.get('active_task') else None,
            'decision': outcome.get('decision') or state.get('active_decision'),
            'reason': '; '.join(integrity) or outcome.get('reason') or outcome.get('error') or '; '.join((outcome.get('validation') or {}).get('errors', [])) or (str(outcome.get('conflicts') or outcome.get('unresolved')) if outcome.get('conflicts') or outcome.get('unresolved') else None),
            'index': str(kernel.root / '00-progress.md'), 'video_complete': status == 'VIDEO_DELIVERED'}


def update_progress(kernel, outcome=None):
    if not enabled(kernel.project):
        return None
    view = progress(kernel, outcome)
    def link(path):
        return quote(str(path), safe='/._-')
    lines = [f"# {kernel.project['project_id']} · {view['status']}",
             f"当前：{view['stage']:02d} · {view['stage_name']}。此页是状态投影，不是验收依据。",
             '| 阶段 | 状态 | 产物 |', '|---|---|---|']
    for row in view['stages']:
        folder = row['directory']
        label = f"{row['stage']:02d} {row['name']}"
        if (kernel.root / folder).is_dir():
            label = f'[{label}]({link(folder)}/)'
        outputs = '、'.join(f"[{r['slot']}]({link(r['uri'])})" for r in row['artifacts']) or '—'
        lines.append(f"| {label} | {row['status']} | {outputs} |")
    if view['reason']:
        lines.append('\n阻塞：' + str(view['reason']))
    if view['decision']:
        lines.append('\n待决定：' + str(view['decision'].get('question', view['decision'])))
    if view['task_file']:
        relative_task = Path(view['task_file']).relative_to(kernel.root).as_posix()
        lines.append(f'\n下一步：读取[当前任务]({link(relative_task)})及其必读项，提交本轮原生结果。不要遍历全部历史文件。')
    elif kernel.state['status'] == 'DELIVERED':
        lines.append('\n[前期交付入口](09-delivery/index.md)。' + ('继续真实视频制作与验收。' if kernel.production_target() == 'video' else '视频未生成，视频验收 NOT_RUN。'))
    lines.append('\n完整机器上下文：[state.json](state.json)；配置：[project.json](project.json)；模块锁：[modules.lock.json](modules.lock.json)。.runtime/ 保存必要收据、原件、模块及失败恢复证据，不作为默认阅读入口。')
    kernel.write('00-progress.md', ('\n'.join(lines) + '\n').encode())
    return {key: view[key] for key in ('status', 'stage', 'stage_name', 'index')}


def context(kernel, slot=None, pointer=''):
    """Read exact, hash-checked native values on demand; never write a context copy."""
    from .v5_adapters import pointer as resolve
    kernel.require_v5()
    if slot is None:
        if pointer:
            raise ValueError('--pointer requires --slot')
        return {'context_mode': 'native-pointers', 'artifacts': [
            {'slot': key, 'uri': str(kernel.path(row['uri'])), 'sha256': row['sha256'],
             'valid': kernel.valid(key), 'stage': row['stage']}
            for key, row in kernel.state['artifacts'].items()],
            'instruction': 'Use context --slot SLOT --pointer /field for exact content. No context file is created.'}
    if not kernel.valid(slot):
        raise ValueError('Context artifact is missing, changed or stale: ' + slot)
    row = kernel.state['artifacts'][slot]
    return {'slot': slot, 'uri': str(kernel.path(row['uri'])), 'sha256': row['sha256'],
            'pointer': pointer, 'value': resolve(kernel.data(slot), pointer)}
