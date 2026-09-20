"""Codex-only V4 kernel. Legacy executors are deliberately not imported."""
from copy import deepcopy
from pathlib import Path
from functools import wraps
import re
import unicodedata
from .storage import ProjectStore
from .transactions import before_write
from .utils import (PACKAGE_ROOT, canonical_json, sha256_bytes, sha256_file, stable_id,
                    read_json, markdown_view, deterministic_zip)
from .schema import validate, validate_artifact
from .ingest import extract_text, classify_source, IMAGE_EXTENSIONS
from .v4_contracts import PHASES, phase, output, model_policy, data_schema


def digest(value):
    return sha256_bytes(canonical_json(value).encode())


def approval_token(media):
    return digest({k: media[k] for k in ('key', 'input_hash', 'revision', 'sha256')})


def coverage_for(value, pointer=''):
    if isinstance(value, dict):
        return [row for key, item in value.items() for row in coverage_for(item, pointer + '/' + key)]
    if isinstance(value, list):
        return [row for index, item in enumerate(value) for row in coverage_for(item, pointer + '/' + str(index))]
    return [{'source_pointer': pointer, 'destination': 'execution_controls' + pointer, 'value_hash': digest(value)}]


def render_prompt(shot, refs, controls, start):
    header = f"镜头 {shot['shot_id']}｜{shot['duration_s']}秒｜分段 {shot['segment_id']} {start}—{start + shot['duration_s']}秒\n"
    attachments = '\n'.join(f"{r['alias']} = {r['filename']}；用途：{r['role']}；禁止继承：{'、'.join(r['forbidden_inheritance'])}" for r in refs)
    return header + attachments + '\n角色图约束身份，故事板图约束对应瞬间；动作、摄影与声音按以下秒级时序执行。\n' + canonical_json(controls)


def safe_name(name):
    name = unicodedata.normalize('NFC', name)
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name).strip(' .')[:100] or '未命名资产'


def project_transaction(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if self.legacy:
            if method.__name__ == 'run':
                return self.status()
            raise ValueError('Legacy project is read-only; explicitly copy it before modifying')
        with self.store.transaction():
            return method(self, *args, **kwargs)
    return wrapped


class V4Kernel:
    def __init__(self, project):
        self.store = ProjectStore(project)
        if not self.store.exists('project.json'):
            raise ValueError('Project not found')
        # Legacy opening must be read-only, including transaction recovery.
        self.legacy = self.store.read('project.json').get('schema_version') != '4.0'
        if not self.legacy:
            with self.store.transaction():
                pass

    @property
    def state(self):
        return self.store.read('state.json')

    def base(self, path, kind, number=1):
        project_id = self.store.read('project.json')['project_id']
        return dict(schema_version='4.0', artifact_type=kind, artifact_id=stable_id('artifact', project_id, path),
                    project_id=project_id, revision=self.store.revision_for(path),
                    stage_id=phase(number)['id'], role_provenance='kernel')

    def commit(self, path, kind, payload, number=1):
        value = {**self.base(path, kind, number), **payload}
        if self.store.exists(path):
            old = self.store.read(path)
            if {k: v for k, v in old.items() if k != 'revision'} == {k: v for k, v in value.items() if k != 'revision'}:
                return old
        self.store.commit(path, value)
        return value

    def save_state(self, state):
        payload = {k: v for k, v in state.items() if k not in self.base('state.json', 'workflow-state')}
        self.commit('state.json', 'workflow-state', payload)

    def manifest(self):
        files = []
        for path in sorted(self.store.root.rglob('*')):
            relative = path.relative_to(self.store.root).as_posix()
            if not path.is_file() or relative.startswith(('runtime/', '.history/')) or '/delivery/' in relative or relative in ('manifest.json', 'manifest.md'):
                continue
            files.append({'path': relative, 'sha256': sha256_file(path)})
        return self.commit('manifest.json', 'manifest', {'files': files})

    @classmethod
    def initialize(cls, project, inputs, *, title=None, input_type=None, style=None, canvas=None,
                   rights=None, image_budget=None, segment_seconds=15):
        store = ProjectStore(project)
        if store.root.exists() and any(store.root.iterdir()):
            raise ValueError('Initialize into an empty project; existing projects are never overwritten')
        if not inputs:
            raise ValueError('At least one input is required')
        if not isinstance(segment_seconds, (int, float)) or isinstance(segment_seconds, bool) or not 0 < segment_seconds <= 120:
            raise ValueError('Segment target must be a positive duration up to 120s; shots remain 1–12s')
        if rights not in (None, 'authorized', 'draft-only'):
            raise ValueError('Unknown rights selection')
        if image_budget is not None and (not isinstance(image_budget, int) or isinstance(image_budget, bool) or image_budget <= 0):
            raise ValueError('Image budget must be a positive integer')
        choices = {k: v for k, v in {'style': style, 'canvas': canvas, 'rights': rights, 'image_budget': image_budget}.items() if v is not None}
        if rights == 'draft-only':
            choices['delivery'] = 'draft-only'
        store.root.mkdir(parents=True, exist_ok=True)
        project_id = stable_id('project', title or store.root.name, digest(inputs))
        base = dict(schema_version='4.0', artifact_type='project', artifact_id=stable_id('project-artifact', project_id),
                    project_id=project_id, revision=1, stage_id='phase-01', role_provenance='kernel')
        with store.transaction():
            store.commit('project.json', {**base, 'title': title or store.root.name, 'workflow_id': 'ai-comic-drama-v4',
                                         'adaptation_policy': 'limited-expansion', 'segment_target_s': segment_seconds})
            kernel = cls(store.root)
            for item in PHASES:
                store.path(item['folder']).mkdir(parents=True, exist_ok=True)
            kernel.commit('phase-index.json', 'phase-index', {'phases': PHASES})
            kernel.commit('state.json', 'workflow-state', {'status': 'running', 'phase_status': {str(i): 'pending' for i in range(1, 11)},
                'decisions': choices, 'active_task': None, 'active_decision': None, 'model_capabilities': [],
                'image_capability': 'unknown', 'aliases': {}, 'media': {}, 'approvals': {},
                'image_dispatches': 0, 'failures': {}, 'creative_retries': {}, 'generation_tokens': {}, 'batches': {}})
            kernel._ingest(inputs, input_type)
            if choices:
                kernel.commit(phase(1)['folder'] + '/initial-choices.json', 'approval-record', {'actor': 'user', 'selections': choices, 'source': 'explicit initialize arguments'})
            kernel.manifest()
        return kernel

    def _ingest(self, inputs, hint=None):
        path = phase(1)['folder'] + '/sources.json'
        records = self.store.read(path)['sources'] if self.store.exists(path) else []
        for raw in inputs:
            try:
                candidate = Path(raw).expanduser()
                is_file = candidate.is_file()
            except OSError:
                is_file = False
            index = len(records) + 1
            if is_file:
                if candidate.suffix.lower() not in IMAGE_EXTENSIONS | {'.txt', '.md', '.json', '.pdf', '.docx'}:
                    raise ValueError('V4 accepts text/document/image references, not video or 3D inputs')
                relative = f"{phase(1)['folder']}/sources/{index:03d}_{safe_name(candidate.name)}"
                self.store.copy_source(candidate, relative)
                text, extraction = extract_text(candidate)
                kind = classify_source(candidate, text, hint)
                if kind == 'legacy-project':
                    raise ValueError('Open old project read-only or use copy-project; do not ingest controls as story')
            else:
                if '\n' not in raw and len(raw) < 250 and (raw.startswith(('/', './', '../', '~'))):
                    raise FileNotFoundError(raw)
                relative = f"{phase(1)['folder']}/sources/{index:03d}_文字资料.txt"
                self.store.write_text(relative, raw)
                text, extraction, kind = raw, 'extracted', hint or 'text'
            record = {'source_id': stable_id('source', relative, sha256_file(self.store.path(relative))),
                      'path': relative, 'sha256': sha256_file(self.store.path(relative)), 'kind': kind,
                      'extraction_status': extraction, 'rights': 'unknown'}
            if text is not None:
                record['text_path'] = f"{phase(1)['folder']}/sources/{index:03d}_提取文本.txt"
                self.store.write_text(record['text_path'], text)
            records.append(record)
        self.commit(path, 'source-registry', {'sources': records})

    def fingerprint(self, number):
        entries = {'project.json': sha256_file(self.store.path('project.json'))}
        dependencies = phase(number)['dependencies']
        for i in dependencies:
            if self.store.exists(output(i)):
                entries[output(i)] = sha256_file(self.store.path(output(i)))
        sources = phase(1)['folder'] + '/sources.json'
        entries[sources] = sha256_file(self.store.path(sources))
        for record in self.store.read(sources)['sources']:
            for key in ('path', 'text_path'):
                if key in record:
                    entries[record[key]] = sha256_file(self.store.path(record[key]))
        state = self.state
        # All source/rule bytes are hashed, but only relevant resources enter model context.
        rules = {p.relative_to(PACKAGE_ROOT).as_posix(): sha256_file(p) for pattern in ('src/ai_comic_drama_workflow/v4*.py', 'references/v4/*.md', 'schemas/v4*.json') for p in PACKAGE_ROOT.glob(pattern)}
        rules['workflow-graph.json'] = sha256_file(PACKAGE_ROOT / 'workflow-graph.json')
        decisions = {k: v for k, v in state['decisions'].items() if k in ('style', 'canvas', 'rights')}
        media = {k: {'input_hash': v['input_hash'], 'actual_sha256': sha256_file(self.store.path(v['path'])) if self.store.exists(v['path']) else 'missing'}
                 for k, v in state['media'].items() if number >= 9 and v['phase'] < number}
        return digest({'inputs': entries, 'rules': rules, 'decisions': decisions if number >= 8 else {},
                       'media': media, 'model': model_policy(number), 'capabilities': state['model_capabilities'],
                       'image_capability': state['image_capability'] if number >= 8 else None})

    def status(self):
        if self.legacy:
            return {'status': 'awaiting_choice', 'legacy_read_only': True, 'options': ['read-only', 'copy-project'],
                    'message': 'Old project unchanged. Use copy-project with a new destination to adapt to V4.'}
        state = self.state
        result = {'status': state['status'], 'phase_status': state['phase_status'], 'project': str(self.store.root)}
        for key in ('active_task', 'active_decision'):
            if state[key]:
                result['task' if key == 'active_task' else 'decision'] = self.store.read(state[key])
        return result

    def choice(self, key, question, options, number, scope=None):
        state = self.state
        request = self.commit('runtime/decision.json', 'decision-request', {'key': key, 'question': question,
            'options': options, 'scope': scope, 'context_fingerprint': self.fingerprint(number), 'phase': number}, number)
        request_id = stable_id('decision', digest(request))
        request = self.commit('runtime/decision.json', 'decision-request', {**{k: v for k, v in request.items() if k not in self.base('runtime/decision.json', 'decision-request')}, 'request_id': request_id}, number)
        state.update(status='awaiting_choice', active_decision='runtime/decision.json', active_task=None)
        self.save_state(state)
        self.manifest()
        return self.status()

    @project_transaction
    def configure_host(self, models, image_capability, evidence):
        if self.legacy:
            raise ValueError('Legacy is read-only')
        if not evidence or image_capability not in ('available', 'unavailable', 'unknown'):
            raise ValueError('Host inventory evidence and an honest image capability are required')
        for item in models:
            if set(item) != {'model', 'reasoning_effort'}:
                raise ValueError('Models must record model and reasoning_effort')
        state = self.state
        state.update(model_capabilities=models, image_capability=image_capability,
                     capability_evidence=evidence, active_task=None, active_decision=None, status='running')
        self.save_state(state)
        self.manifest()
        return self.run()

    def dispatch(self, number, kind='creative', job=None):
        state = self.state
        resources = ['references/v4/phase-%02d.md' % number, 'references/v4/' + ('director.md' if number >= 9 else 'writer.md'), 'references/v4/quality.md']
        if kind == 'image':
            resources.append('references/v4/imagegen.md')
        batch_path = state.get('batches', {}).get(str(number))
        batch = self.store.read(batch_path)['data'] if batch_path else {}
        expected_ids = None
        completed_ids = batch.get('review', {}).get('checked_shot_ids', [s['shot_id'] for s in batch.get('shots', [])])
        reference_images = job['bindings'] if job else []
        if number in (9, 10) and kind == 'creative':
            upstream_shots = self.store.read(output(7 if number == 9 else 9))['data']['shots']
            all_ids = [s['shot_id'] for s in upstream_shots]
            expected_ids = all_ids[len(completed_ids):][:5]
            required_assets = {a for s in upstream_shots if s['shot_id'] in expected_ids for a in s['required_asset_ids']}
            reference_images = [m for m in state['media'].values() if m['key'] in required_assets or m.get('shot_id') in expected_ids]
        task = {'phase': number, 'task_kind': kind, 'model_policy': model_policy(number),
                'input_artifacts': [output(i) for i in phase(number)['dependencies']] + [phase(1)['folder'] + '/sources.json'],
                'loaded_resources': resources, 'context_fingerprint': self.fingerprint(number),
                'output_schema': data_schema(number) if kind == 'creative' else None,
                'constraints': {'max_shots_per_batch': 5, 'human_approval_is_not_automatic_qa': True}, 'job': job,
                'revision_scope': state.get('revision_scope', {}), 'project_config': self.store.read('project.json'),
                'reference_images': reference_images,
                'identity_approvals': state['approvals'] if number >= 9 else {},
                'batch': {'completed_shot_ids': completed_ids, 'expected_shot_ids': expected_ids,
                          'previous_end_state': batch.get('shots', [{}])[-1].get('end_state') if batch.get('shots') else None},
                'attempt': state['failures'].get(job['key'] if job else str(number), 0) + state['creative_retries'].get(job['key'] if job else str(number), 0)}
        task['task_id'] = stable_id('task', digest(task))
        self.commit('runtime/task.json', 'task-envelope', task, number)
        state.update(status='awaiting_agent_result', active_task='runtime/task.json', active_decision=None)
        self.save_state(state)
        self.manifest()
        return self.status()

    @project_transaction
    def run(self):
        if self.legacy:
            return self.status()
        self.refresh_invalidations()
        state = self.state
        if state['status'] in ('awaiting_choice', 'awaiting_agent_result', 'paused'):
            return self.status()
        for number in range(1, 11):
            state = self.state
            if state['phase_status'][str(number)] == 'complete':
                continue
            if model_policy(number) not in state['model_capabilities']:
                return self.choice('model_unavailable', '宿主未证明所需模型组合可用；请补充能力或暂停。', ['supply-capability', 'pause'], number)
            if number == 1:
                unreadable = [r for r in self.store.read(phase(1)['folder'] + '/sources.json')['sources'] if r['kind'] != 'reference-image' and r['extraction_status'] != 'extracted']
                if unreadable:
                    return self.choice('unreadable', '资料未可靠读取，请补充可读文字；不会猜测缺失内容。', ['supply-text', 'pause'], number)
            if number == 8:
                choices = state['decisions']
                for key, question, options in (
                    ('style', '请选择视觉风格。', ['电影级真人写实', '国漫3D', '3A游戏CG', '高规格2D动漫', '参考图驱动', 'custom']),
                    ('canvas', '请选择画幅。', ['9:16', '16:9', '1:1', 'custom']),
                    ('rights', '请确认资料允许用于本项目原生生图，包括所涉肖像与外发范围。', ['authorized', 'draft-only', 'pause'])):
                    if key not in choices:
                        return self.choice(key, question, options, number)
            if not self.store.exists(output(number)) or state['phase_status'][str(number)] == 'invalidated':
                return self.dispatch(number)
            if number in (8, 9):
                pending = self.advance_images(number)
                if pending:
                    return pending
                if number == 8:
                    state = self.state
                    for item in self.store.read(output(8))['data']['assets']:
                        if item['kind'] != 'role':
                            continue
                        media = state['media'].get(item['asset_id'])
                        if media and state['approvals'].get(item['asset_id']) != approval_token(media):
                            return self.choice('identity_approval', f"请确认角色图：{item['name']}（{media['path']}）", ['approve', 'revise', 'pause'], 8, item['asset_id'])
            if number == 10:
                shots = self.store.read(output(9))['data']['shots']
                if any(len(set(c['identity_asset_id'] for c in s['characters'])) + len(s['key_moments']) > 5 for s in shots) and state['decisions'].get('delivery') != 'draft-only':
                    return self.choice('reference_capacity', '必需参考超过5张，不能静默丢图。请修订镜头或选择草稿。', ['revise', 'draft-only', 'pause'], number)
                self.compile_prompts()
            state = self.state
            state['phase_status'][str(number)] = 'complete'
            self.save_state(state)
        self.manifest()
        report = self.validate(final=True)
        state = self.state
        state['status'] = 'complete' if report['valid'] else ('draft_ready' if state['decisions'].get('delivery') == 'draft-only' else 'blocked')
        state['delivery_status'] = 'dual_reference_prompt_ready' if report['valid'] else 'draft'
        self.save_state(state)
        self.manifest()
        return self.status()

    def refresh_invalidations(self):
        state = self.state
        changed = set()
        media_phases = set()
        for key, record in list(state['media'].items()):
            if not self.store.exists(record['path']) or sha256_file(self.store.path(record['path'])) != record['sha256']:
                media_phases.add(record['phase'])
                state['media'].pop(key)
                state['approvals'].pop(key, None)
        for number in range(1, 11):
            if state['phase_status'][str(number)] != 'complete':
                continue
            if not self.store.exists(output(number)) or self.store.read(output(number))['source_fingerprint'] != self.fingerprint(number):
                changed.add(number)
        roots = changed | media_phases
        if not roots:
            return
        affected = set(roots)
        for number in range(1, 11):
            if affected.intersection(phase(number)['dependencies']):
                affected.add(number)
        for number in affected:
            state['phase_status'][str(number)] = 'running' if number in media_phases and number not in changed else 'invalidated'
            state.get('batches', {}).pop(str(number), None)
        state.update(status='running', active_task=None, active_decision=None)
        self.save_state(state)
        self.manifest()

    @project_transaction
    def resume(self, decision):
        if isinstance(decision, (str, Path)):
            decision = read_json(Path(decision))
        state = self.state
        if not state['active_decision']:
            raise ValueError('No active decision')
        request = self.store.read(state['active_decision'])
        if decision.get('request_id') != request['request_id'] or request['context_fingerprint'] != self.fingerprint(request['phase']):
            raise ValueError('Stale decision')
        value = decision.get('value')
        if value not in request['options']:
            raise ValueError('Choice is not an available option')
        key = request['key']
        if value == 'custom':
            value = decision.get('custom_value')
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Custom choice requires text')
        if key == 'identity_approval' and value == 'approve':
            state['approvals'][request['scope']] = approval_token(state['media'][request['scope']])
        elif key == 'identity_approval' and value == 'revise':
            asset_id = request['scope']
            state['generation_tokens'][asset_id] = state['generation_tokens'].get(asset_id, 0) + 1
            state['media'].pop(asset_id, None)
        elif key == 'image_budget' and value != 'pause':
            state['decisions'][key] = int(value)
        else:
            state['decisions'][key] = value
        self.commit(f"{phase(request['phase'])['folder']}/decisions/{request['request_id']}.json", 'approval-record',
                    {'request': request, 'selection': value, 'actor': 'user'}, request['phase'])
        if value == 'draft-only':
            state['decisions']['delivery'] = 'draft-only'
        state.update(active_decision=None, status='paused' if value in ('pause', 'supply-text', 'supply-capability', 'revise') and key != 'identity_approval' else 'running')
        self.save_state(state)
        return self.run()

    def check_execution(self, result, task):
        execution = result.get('execution', {})
        if {k: execution.get(k) for k in ('model', 'reasoning_effort')} != task['model_policy']:
            raise ValueError('Wrong model or reasoning effort; never silently substitute')
        if not execution.get('agent_id') or not execution.get('dispatch_evidence'):
            raise ValueError('Host dispatch evidence is required; result self-label is insufficient')

    @project_transaction
    def submit(self, result):
        if isinstance(result, (str, Path)):
            result = read_json(Path(result))
        state = self.state
        if not state['active_task']:
            raise ValueError('No active task')
        task = self.store.read(state['active_task'])
        number = task['phase']
        if result.get('task_id') != task['task_id'] or result.get('context_fingerprint') != task['context_fingerprint'] or task['context_fingerprint'] != self.fingerprint(number):
            raise ValueError('Stale task or changed inputs')
        self.check_execution(result, task)
        if result.get('status') in ('failed', 'uncertain') or result.get('qa', {}).get('passed') is False:
            evidence = result.get('failure_evidence') or result.get('qa')
            if not evidence:
                raise ValueError('Failure requires evidence')
            self.commit(f"runtime/failures/{task['task_id']}.json", 'failure-evidence', {'task': task, 'evidence': evidence}, number)
            if result.get('status') == 'uncertain':
                return self.choice('uncertain_result', '调用结果不确定，请核对实际返回；不得自动重复生图。', ['supply-capability', 'pause'], number)
            counter = 'creative_retries' if result.get('qa', {}).get('passed') is False else 'failures'
            maximum = 2 if counter == 'creative_retries' else 3
            failure_key = task['job']['key'] if task.get('job') else str(number)
            state[counter][failure_key] = state[counter].get(failure_key, 0) + 1
            state.update(active_task=None, status='running')
            self.save_state(state)
            if state[counter][failure_key] > maximum:
                return self.choice('retry_exhausted', '自动返修或重试次数耗尽，请修订输入或暂停。', ['revise', 'pause'], number)
            return self.run()
        findings = result.get('findings', [])
        if any(f.get('severity') in ('critical', 'blocking') for f in findings):
            self.commit('runtime/failure.json', 'failure-evidence', {'findings': findings, 'task': task}, number)
            return self.choice('core_conflict', '存在关键剧情或质量问题，请提供修订指令后重试。', ['revise', 'pause'], number)
        self.commit('runtime/results/' + task['task_id'] + '.json', 'agent-result', {'result': result}, number)
        if task['task_kind'] == 'image':
            self.import_image(task, result)
        else:
            data = result['data']
            validate(data, data_schema(number))
            if result.get('qa', {}).get('passed') is not True:
                raise ValueError('Automatic quality review is required, not implicit approval')
            if number == 10:
                reviewed = data['review']['checked_shot_ids']
                if reviewed != task['batch']['expected_shot_ids']:
                    raise ValueError('Review exactly the requested shot batch')
                completed = task['batch']['completed_shot_ids'] + reviewed
                data = {**data, 'review': {**data['review'], 'checked_shot_ids': completed}}
                if len(completed) < len(self.store.read(output(9))['data']['shots']):
                    batch_path = 'runtime/batches/phase-10.json'
                    self.commit(batch_path, 'batch-draft', {'data': data}, number)
                    state.setdefault('batches', {})['10'] = batch_path
                    state.update(active_task=None, status='running')
                    self.save_state(state)
                    return self.dispatch(number)
                state.setdefault('batches', {}).pop('10', None)
                self.save_state(state)
            if number in (7, 9):
                if len(data['shots']) > 5:
                    raise ValueError('At most five shots per AgentResult')
                batch_path = state.get('batches', {}).get(str(number))
                prior_batch = self.store.read(batch_path)['data'] if batch_path else {}
                expected = task['batch']['expected_shot_ids']
                if expected is not None and [s['shot_id'] for s in data['shots']] != expected:
                    raise ValueError('Batch must contain exactly the requested ordered shots')
                merged = {**data, 'shots': prior_batch.get('shots', []) + data['shots']}
                for field in ('source_refs', 'inferences'):
                    merged[field] = list(dict.fromkeys(prior_batch.get(field, []) + data[field]))
                if prior_batch:
                    merged['content'] = prior_batch['content'] + '\n' + data['content']
                if number == 9:
                    scenes = {s['scene_id']: s for s in prior_batch.get('scenes', [])}
                    for scene in data['scenes']:
                        if scene['scene_id'] in scenes and scenes[scene['scene_id']] != scene:
                            raise ValueError('Scene definition changed between shot batches')
                        scenes[scene['scene_id']] = scene
                    merged['scenes'] = list(scenes.values())
                from .v4_contracts import validate_shots
                validate_shots(merged['shots'])
                finished = len(merged['shots']) == len(self.store.read(output(7))['data']['shots']) if number == 9 else result.get('batch_complete', True)
                if not finished:
                    batch_path = f'runtime/batches/phase-{number:02d}.json'
                    self.commit(batch_path, 'batch-draft', {'data': merged, 'context_fingerprint': task['context_fingerprint']}, number)
                    state.setdefault('batches', {})[str(number)] = batch_path
                    state.update(active_task=None, status='running')
                    self.save_state(state)
                    return self.dispatch(number)
                data = merged
                state.setdefault('batches', {}).pop(str(number), None)
                self.save_state(state)
            self.check_links(number, data)
            self.check_revision_scope(number, data, state.get('revision_scope', {}))
            if result.get('qa', {}).get('passed') is not True:
                raise ValueError('Automatic quality review is required, not implicit approval')
            self.commit(output(number), 'phase-result', {'phase': number, 'data': data,
                'source_fingerprint': self.fingerprint(number), 'execution': result['execution'],
                'qa': {**result['qa'], 'actor': 'automatic'}, 'input_hashes': {p: sha256_file(self.store.path(p)) for p in task['input_artifacts'] if self.store.exists(p)}}, number)
        self.commit('runtime/results/' + task['task_id'] + '.json', 'agent-result', {'result': result}, number)
        state = self.state
        state.update(active_task=None, status='running')
        success_key = task['job']['key'] if task.get('job') else str(number)
        state['failures'].pop(success_key, None)
        state['creative_retries'].pop(success_key, None)
        if task['task_kind'] == 'creative':
            state['phase_status'][str(number)] = 'running'
        self.save_state(state)
        return self.run()

    def check_links(self, number, data):
        allowed = {r['source_id'] for r in self.store.read(phase(1)['folder'] + '/sources.json')['sources']}
        allowed.update(output(i) for i in phase(number)['dependencies'])
        if not data['source_refs'] or not set(data['source_refs']) <= allowed:
            raise ValueError('Untraceable source refs')
        if number == 1 and data['unresolved']:
            raise ValueError('Unresolved core gaps must be submitted as blocking findings')
        if number == 7:
            segments = {s['segment_id'] for s in self.store.read(output(6))['data']['segments']}
            if any(s['segment_id'] not in segments for s in data['shots']):
                raise ValueError('Unknown segment reference')
            if {s['segment_id'] for s in data['shots']} != segments:
                raise ValueError('Every script segment must be covered by a shot')
        if number == 8:
            ids = [a['asset_id'] for a in data['assets']]
            if len(ids) != len(set(ids)):
                raise ValueError('Duplicate asset ID')
            if not {'style', 'scene'} <= {a['kind'] for a in data['assets']}:
                raise ValueError('Asset plan requires explicit style and scene references')
            needed = {a for s in self.store.read(output(7))['data']['shots'] for a in s['required_asset_ids']}
            if not needed <= set(ids):
                raise ValueError('Missing planned logical assets')
            sources = {r['source_id']: r for r in self.store.read(phase(1)['folder'] + '/sources.json')['sources']}
            for asset in data['assets']:
                for source_id in asset.get('reference_source_ids', []):
                    if source_id not in sources or sources[source_id]['kind'] != 'reference-image':
                        raise ValueError('Unknown reference image source')
        if number == 9:
            before = self.store.read(output(7))['data']['shots']
            if [s['shot_id'] for s in before] != [s['shot_id'] for s in data['shots']]:
                raise ValueError('Shot order must be preserved')
            scenes = {s['scene_id']: s for s in data['scenes']}
            assets = {a['asset_id']: a for a in self.store.read(output(8))['data']['assets']}
            for prior, shot in zip(before, data['shots']):
                for key in ('segment_id', 'duration_s', 'purpose', 'sound', 'initial_state', 'end_state'):
                    if prior[key] != shot[key]:
                        raise ValueError('Spatial refinement cannot silently change narrative, duration or dialogue')
                if [c['entity_id'] for c in prior['characters']] != [c['entity_id'] for c in shot['characters']]:
                    raise ValueError('Spatial refinement cannot add or remove characters')
                if shot['scene_id'] not in scenes or not set(shot['required_asset_ids']) <= assets.keys():
                    raise ValueError('Unknown scene or logical asset')
                for track in shot['characters']:
                    if track['identity_asset_id'] not in shot['required_asset_ids']:
                        raise ValueError('Identity reference must remain a logical asset dependency')
                    asset = assets.get(track['identity_asset_id'], {})
                    if asset.get('kind') != 'role' or track['entity_id'] not in asset.get('entity_ids', []):
                        raise ValueError('Character identity reference mismatch')
                    for k in track['positions']:
                        bounds = scenes[shot['scene_id']]['bounds']
                        if any(not lo <= p <= hi for p, lo, hi in zip(k['position'], bounds['min'], bounds['max'])):
                            raise ValueError('Position outside declared scene bounds')
        if number == 10:
            expected = [s['shot_id'] for s in self.store.read(output(9))['data']['shots']]
            if data['review']['checked_shot_ids'] != expected:
                raise ValueError('Director review must cover every shot in order')

    def image_jobs(self, number):
        state = self.state
        jobs = []
        if number == 8:
            sources = {r['source_id']: r for r in self.store.read(phase(1)['folder'] + '/sources.json')['sources']}
            for asset in self.store.read(output(8))['data']['assets']:
                bindings = [{'key': key, 'path': sources[key]['path'], 'sha256': sources[key]['sha256'], 'role': 'source_reference'} for key in asset.get('reference_source_ids', [])]
                for binding in bindings:
                    self.check_image(binding)
                jobs.append({'key': asset['asset_id'], 'name': asset['name'] + '_' + asset['version_label'],
                    'role': asset['kind'], 'entity_ids': asset['entity_ids'], 'prompt': asset['prompt'], 'bindings': bindings,
                    'forbidden_inheritance': asset['forbidden_inheritance'], 'phase': 8})
        else:
            data = self.store.read(output(9))['data']
            for shot in data['shots']:
                bindings = []
                for character in shot['characters']:
                    asset_id = character['identity_asset_id']
                    media = state['media'].get(asset_id)
                    if not media or state['approvals'].get(asset_id) != approval_token(media):
                        if state['decisions'].get('delivery') == 'draft-only':
                            continue
                        raise ValueError('Storyboard generation requires approved real character images')
                    self.check_image(media)
                    if media not in bindings:
                        bindings.append(media)
                scene = next(s for s in data['scenes'] if s['scene_id'] == shot['scene_id'])
                for index, moment in enumerate(shot['key_moments'], 1):
                    # Only the state at this instant is described, not the entire movement sequence.
                    entities = []
                    time = moment['time_s']
                    for track in shot['characters']:
                        frames = track['positions']
                        left = max((f for f in frames if f['time_s'] <= time), key=lambda f: f['time_s'])
                        right = next((f for f in frames if f['time_s'] > time), left)
                        weight = (time - left['time_s']) / (right['time_s'] - left['time_s']) if right != left else 0
                        position = [a + (b-a)*weight for a, b in zip(left['position'], right['position'])]
                        entities.append({'entity_id': track['entity_id'], **left, 'position': position, 'time_s': time,
                            'actions': [a for a in track['actions'] if a['start_s'] <= time < a['end_s'] or time == shot['duration_s'] == a['end_s']],
                            'emotions': [a for a in track['emotions'] if a['start_s'] <= time < a['end_s'] or time == shot['duration_s'] == a['end_s']]})
                    snapshot = {'shot_id': shot['shot_id'], 'moment': moment, 'scene': scene, 'characters': entities,
                                'camera': [c for c in shot['camera'] if c['start_s'] <= time < c['end_s'] or time == shot['duration_s'] == c['end_s']],
                                'lighting': shot['lighting'], 'environment': shot['environment']}
                    jobs.append({'key': f"{shot['shot_id']}:moment:{index}", 'name': f"{shot['shot_id']}_{moment['name']}",
                        'role': 'board', 'entity_ids': [c['entity_id'] for c in shot['characters']], 'shot_id': shot['shot_id'],
                        'time_s': time, 'phase': 9, 'bindings': bindings, 'forbidden_inheritance': [],
                        'prompt': '生成单张正式故事板成图。参考角色图只继承身份和服装，不继承背景、构图或无关姿势。只呈现以下瞬间：\n' + canonical_json(snapshot),
                        'snapshot_hash': digest(snapshot)})
        for job in jobs:
            job['style'] = state['decisions'].get('style')
            job['canvas'] = state['decisions'].get('canvas')
            job['generation_token'] = state['generation_tokens'].get(job['key'], 0)
            job['input_hash'] = digest(job)
        return jobs

    def advance_images(self, number):
        state = self.state
        if state['decisions'].get('delivery') == 'draft-only':
            return None
        provided_only = state['decisions'].get('image_unavailable') == 'import-images'
        if state['image_capability'] != 'available' and not provided_only:
            return self.choice('image_unavailable', '原生生图能力不可用。补充能力、导入图片或选择草稿。', ['supply-capability', 'import-images', 'draft-only', 'pause'], number)
        jobs = self.image_jobs(number)
        pending = [j for j in jobs if state['media'].get(j['key'], {}).get('input_hash') != j['input_hash']]
        if not pending:
            return None
        if provided_only:
            return self.dispatch(number, 'image', {**pending[0], 'provided_only': True})
        if state['image_dispatches'] >= state['decisions'].get('image_budget', 0):
            # Account for assets and expected board moments even before phase 9 refinement.
            estimate = len(self.store.read(output(8))['data']['assets']) + sum(len(s['key_moments']) for s in self.store.read(output(7))['data']['shots'])
            total = max(estimate, state['image_dispatches'] + len(pending))
            return self.choice('image_budget', f'当前计划约{estimate}项图片；请选择累计任务上限（包括重试）。', [total, total + 3, total + 10, 'pause'], number)
        job = pending[0]
        state['image_dispatches'] += 1
        self.save_state(state)
        return self.dispatch(number, 'image', job)

    def import_image(self, task, result):
        job = task['job']
        media = result.get('media', {})
        if media.get('input_hash') != job['input_hash'] or media.get('bindings') != job['bindings']:
            raise ValueError('Actual image input bindings must exactly match dispatched images')
        if media.get('provider') not in ('codex-imagegen', 'provided') or not media.get('call_evidence'):
            raise ValueError('Actual native call or explicit user-import evidence is required')
        if job.get('provided_only') and media['provider'] != 'provided':
            raise ValueError('Import-only task does not authorize native generation')
        for binding in job['bindings']:
            self.check_image(binding)
        source = Path(media['output_path']).resolve(strict=True)
        if source.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp') or sha256_file(source) != media['sha256']:
            raise ValueError('Real raster image and matching SHA required; no whitebox substitution')
        from PIL import Image
        with Image.open(source) as im:
            im.verify()
        with Image.open(source) as im:
            dimensions = list(im.size)
        if result.get('qa', {}).get('passed') is not True or not result['qa'].get('visual_findings'):
            raise ValueError('Image must be visually inspected, not just opened by a decoder')
        state = self.state
        aliases = state['aliases']
        key = job['key']
        if key not in aliases:
            prefix = '@image_' + job['role'] + '_'
            count = max([int(v.rsplit('_', 1)[1]) for v in aliases.values() if v.startswith(prefix)] or [0]) + 1
            aliases[key] = prefix + str(count)
        name = safe_name(job['name'])
        others = [m for k, m in state['media'].items() if k != key and safe_name(m['name']) == name]
        if others:
            name += '_' + digest(key)[:8]
        folder = phase(job['phase'])['folder'] + '/images/'
        version = 1
        while self.store.exists(folder + f'{name}_v{version:03d}' + source.suffix.lower()):
            version += 1
        relative = folder + f'{name}_v{version:03d}' + source.suffix.lower()
        self.store.copy_source(source, relative)
        record = {k: deepcopy(v) for k, v in job.items() if k not in ('bindings', 'prompt')}
        record.update(path=relative, filename=Path(relative).name, sha256=media['sha256'], alias=aliases[key], revision=version,
                      input_bindings=job['bindings'], dimensions=dimensions, provider=media['provider'],
                      call_evidence=media['call_evidence'], technical_status='readable', automatic_quality=result['qa'],
                      human_approval='pending' if job['role'] == 'role' else 'not_required')
        state['media'][key] = record
        state['aliases'] = aliases
        self.save_state(state)
        self.commit(f"{phase(job['phase'])['folder']}/image-records/{stable_id('image', key)}.json", 'image-record', record, job['phase'])

    def check_image(self, record):
        path = self.store.path(record['path'])
        if not path.is_file() or sha256_file(path) != record['sha256']:
            raise ValueError('Missing or changed reference image: ' + record['path'])
        from PIL import Image
        with Image.open(path) as image:
            image.verify()

    def compile_prompts(self):
        state = self.state
        shots = self.store.read(output(9))['data']['shots']
        prompts = []
        segment_offsets = {}
        for shot in shots:
            refs = []
            keys = list(dict.fromkeys(c['identity_asset_id'] for c in shot['characters']))
            keys += [f"{shot['shot_id']}:moment:{i}" for i in range(1, len(shot['key_moments']) + 1)]
            for key in keys:
                if key in state['media']:
                    record = state['media'][key]
                    self.check_image(record)
                    refs.append({**record, 'attachment_order': len(refs) + 1,
                                 'human_approval': 'approved' if state['approvals'].get(key) == approval_token(record) else record['human_approval']})
            if len(refs) > 5 and state['decisions'].get('delivery') != 'draft-only':
                raise ValueError('Reference capacity exceeded; revise shot/reference plan or explicitly select draft')
            start = segment_offsets.get(shot['segment_id'], 0)
            segment_offsets[shot['segment_id']] = start + shot['duration_s']
            controls = self.prompt_controls(shot)
            text = render_prompt(shot, refs, controls, start)
            sources = {output(i): sha256_file(self.store.path(output(i))) for i in (5, 6, 7, 8, 9)}
            coverage = coverage_for(controls)
            path = phase(10)['folder'] + '/prompts/' + safe_name(shot['shot_id']) + '.txt'
            self.store.write_text(path, text)
            prompts.append({'shot_id': shot['shot_id'], 'prompt_path': path, 'prompt_sha256': sha256_file(self.store.path(path)),
                            'execution_controls': controls, 'coverage': coverage, 'references': refs, 'source_hashes': sources,
                            'segment_start_s': start, 'segment_end_s': start + shot['duration_s']})
        self.commit(phase(10)['folder'] + '/prompt-package.json', 'prompt-package', {'prompts': prompts,
            'delivery_scope': 'dual-reference-video-prompts', 'platform_readiness': 'not_verified', 'execution_status': 'video_not_generated'}, 10)

    def prompt_controls(self, shot):
        state = self.state
        return {'shot': shot, 'style': state['decisions']['style'], 'canvas': state['decisions']['canvas'],
                'scene': next(s for s in self.store.read(output(9))['data']['scenes'] if s['scene_id'] == shot['scene_id']),
                'assets': [a for a in self.store.read(output(8))['data']['assets'] if a['asset_id'] in shot['required_asset_ids']]}

    def validate(self, final=False):
        if self.legacy:
            return {'valid': False, 'errors': ['Legacy project is read-only; copy before V4 validation']}
        errors = []
        state = self.state
        try:
            for number in range(1, 11):
                if not self.store.exists(output(number)):
                    if final:
                        errors.append(f'Missing phase {number}')
                    continue
                artifact = self.store.read(output(number))
                validate_artifact(artifact)
                if artifact['source_fingerprint'] != self.fingerprint(number):
                    errors.append('Stale context: phase ' + str(number))
                self.check_links(number, artifact['data'])
                for path, expected in artifact['input_hashes'].items():
                    if sha256_file(self.store.path(path)) != expected:
                        errors.append('Stale dependency: ' + path)
                if final and state['phase_status'][str(number)] != 'complete':
                    errors.append('Phase not complete: ' + str(number))
            if self.store.exists('manifest.json'):
                for item in self.store.read('manifest.json')['files']:
                    if not self.store.exists(item['path']) or sha256_file(self.store.path(item['path'])) != item['sha256']:
                        errors.append('Manifest hash mismatch: ' + item['path'])
                    if item['path'].endswith('.json') and '/sources/' not in item['path'] and self.store.exists(item['path']):
                        value = self.store.read(item['path'])
                        if value.get('schema_version') == '4.0':
                            validate_artifact(value)
                            md = str(Path(item['path']).with_suffix('.md'))
                            if not self.store.exists(md) or self.store.path(md).read_text() != markdown_view(item['path'], sha256_file(self.store.path(item['path'])), value):
                                errors.append('Markdown derivation mismatch: ' + md)
            if final:
                if state['decisions'].get('delivery') == 'draft-only':
                    errors.append('User selected draft-only; formal dual-reference goal not fulfilled')
                for number in (8, 9):
                    for job in self.image_jobs(number):
                        media = state['media'].get(job['key'])
                        if not media or media['input_hash'] != job['input_hash']:
                            errors.append('Missing or stale image: ' + job['key'])
                            continue
                        self.check_image(media)
                        if job['role'] == 'role' and state['approvals'].get(job['key']) != approval_token(media):
                            errors.append('Identity not approved: ' + job['key'])
                package = self.store.read(phase(10)['folder'] + '/prompt-package.json')
                shots = self.store.read(output(9))['data']['shots']
                if [p['shot_id'] for p in package['prompts']] != [s['shot_id'] for s in shots]:
                    errors.append('Prompt order or shot coverage mismatch')
                offsets = {}
                for prompt in package['prompts']:
                    if sha256_file(self.store.path(prompt['prompt_path'])) != prompt['prompt_sha256']:
                        errors.append('Changed prompt text')
                    shot = next(s for s in self.store.read(output(9))['data']['shots'] if s['shot_id'] == prompt['shot_id'])
                    controls = self.prompt_controls(shot)
                    start = offsets.get(shot['segment_id'], 0)
                    offsets[shot['segment_id']] = start + shot['duration_s']
                    if prompt['execution_controls'] != controls or prompt['coverage'] != coverage_for(controls):
                        errors.append('Prompt facts differ from current shot')
                    if prompt['segment_start_s'] != start or prompt['segment_end_s'] != start + shot['duration_s']:
                        errors.append('Segment timecode mismatch')
                    if self.store.path(prompt['prompt_path']).read_text() != render_prompt(shot, prompt['references'], controls, start):
                        errors.append('Execution text does not cover all current canonical facts')
                    if prompt['source_hashes'] != {output(i): sha256_file(self.store.path(output(i))) for i in (5, 6, 7, 8, 9)}:
                        errors.append('Prompt source trace is stale')
                    expected_keys = set(c['identity_asset_id'] for c in shot['characters']) | {f"{shot['shot_id']}:moment:{i}" for i in range(1, len(shot['key_moments']) + 1)}
                    if {r['key'] for r in prompt['references']} != expected_keys or len(prompt['references']) > 5:
                        errors.append('Required images absent from actual attachment binding')
                    for ref in prompt['references']:
                        self.check_image(ref)
                        if ref['sha256'] != state['media'][ref['key']]['sha256']:
                            errors.append('Stale attachment version')
                        if ref['alias'] != state['aliases'][ref['key']] or ref['filename'] != state['media'][ref['key']]['filename']:
                            errors.append('Attachment alias or filename mismatch')
        except (ValueError, KeyError, OSError, TypeError, StopIteration) as error:
            errors.append(str(error))
        return {'valid': not errors, 'errors': errors, 'delivery_scope': 'dual-reference-video-prompts',
                'video_generated': False, 'human_director_review': 'not_claimed'}

    @project_transaction
    def export(self, draft=False):
        report = self.validate(final=True)
        if not draft and not report['valid']:
            raise ValueError('Formal export blocked: ' + '; '.join(report['errors']))
        folder = phase(10)['folder'] + '/delivery'
        # Review files are archive members; no self-referencing archive hashes.
        self.commit(phase(10)['folder'] + '/validation.json', 'final-validation', {**report, 'draft': draft}, 10)
        self.manifest()
        files = [self.store.path(item['path']) for item in self.store.read('manifest.json')['files']]
        files += [self.store.path('manifest.json'), self.store.path('manifest.md')]
        target = self.store.path(folder + ('/DRAFT.zip' if draft else '/双图视频提示词包.zip'))
        before_write(self.store.root, target)
        deterministic_zip(target, self.store.root, files)
        self.store.write_text(target.relative_to(self.store.root).as_posix() + '.sha256', sha256_file(target) + '\n')
        return {'path': str(target), 'sha256': sha256_file(target), 'draft': draft, 'validation': report}

    @project_transaction
    def revise(self, number, *, shot_id=None, asset_id=None, scene_id=None):
        if self.legacy:
            raise ValueError('Legacy project is read-only')
        number = int(str(number).replace('phase-', ''))
        if number not in range(1, 11):
            raise ValueError('Phase must be 1–10')
        if sum(v is not None for v in (shot_id, asset_id, scene_id)) > 1:
            raise ValueError('Use exactly one revision scope')
        if asset_id and (number != 8 or asset_id not in {a['asset_id'] for a in self.store.read(output(8))['data']['assets']}):
            raise ValueError('Unknown asset or wrong revision phase')
        if shot_id and (number not in (7, 9) or shot_id not in {s['shot_id'] for s in self.store.read(output(number))['data']['shots']}):
            raise ValueError('Unknown shot or wrong revision phase')
        if scene_id and (number != 9 or scene_id not in {s['scene_id'] for s in self.store.read(output(9))['data']['scenes']}):
            raise ValueError('Unknown scene or wrong revision phase')
        state = self.state
        affected = {number}
        for i in range(number + 1, 11):
            if affected.intersection(phase(i)['dependencies']):
                affected.add(i)
        for i in affected:
            state['phase_status'][str(i)] = 'invalidated'
            state.get('batches', {}).pop(str(i), None)
        state.update(status='running', active_task=None, active_decision=None)
        scope = {'shot_id': shot_id, 'asset_id': asset_id, 'scene_id': scene_id}
        state['revision_scope'] = {k: v for k, v in scope.items() if v}
        state['revision_scope']['phase'] = number
        # Image reuse is keyed to its own canonical inputs; unrelated image bytes remain valid.
        if asset_id:
            state['generation_tokens'][asset_id] = state['generation_tokens'].get(asset_id, 0) + 1
            state['approvals'].pop(asset_id, None)
        self.save_state(state)
        self.manifest()
        return self.run()

    def check_revision_scope(self, number, data, scope):
        if scope.get('phase') != number or not self.store.exists(output(number)):
            return
        old = self.store.read(output(number))['data']
        if scope.get('asset_id'):
            old_items = {a['asset_id']: a for a in old['assets'] if a['asset_id'] != scope['asset_id']}
            new_items = {a['asset_id']: a for a in data['assets'] if a['asset_id'] != scope['asset_id']}
            if old_items != new_items:
                raise ValueError('Scoped asset revision changed unrelated assets')
        if scope.get('shot_id'):
            if [s['shot_id'] for s in old['shots']] != [s['shot_id'] for s in data['shots']]:
                raise ValueError('Scoped revision changed shot order')
            if [s for s in old['shots'] if s['shot_id'] != scope['shot_id']] != [s for s in data['shots'] if s['shot_id'] != scope['shot_id']]:
                raise ValueError('Scoped revision changed unrelated shots')
            if number == 9 and old['scenes'] != data['scenes']:
                raise ValueError('Shot revision cannot change unrelated scene geometry')
        if scope.get('scene_id'):
            for key in ('scenes', 'shots'):
                if [s for s in old[key] if s['scene_id'] != scope['scene_id']] != [s for s in data[key] if s['scene_id'] != scope['scene_id']]:
                    raise ValueError('Scene revision changed unrelated scenes or shots')

    @project_transaction
    def add(self, inputs, input_type=None):
        self._ingest(inputs, input_type)
        return self.revise(1)

    @classmethod
    def copy_project(cls, old, destination):
        old = ProjectStore(old)
        target = Path(destination).expanduser().resolve()
        if target.is_relative_to(old.root) or old.root.is_relative_to(target):
            raise ValueError('Migration destination must be separate from the original project tree')
        project = old.read('project.json')
        if project.get('schema_version') not in ('1.0', '2.0', '3.0', '4.0'):
            raise ValueError('Unsupported project version')
        records = old.read('manifest.json').get('files', [])
        verified = []
        source_inputs = []
        for item in records:
            path = old.path(item['path'])
            if not path.is_file() or sha256_file(path) != item['sha256']:
                raise ValueError('Old project manifest failed; preserve source and resolve mismatch first')
            if path.suffix == '.json' and '/sources/' not in item['path']:
                value = read_json(path)
                if value.get('artifact_type') == 'source-registry':
                    for source in value.get('sources', []):
                        relative = source.get('stored_path', source.get('path'))
                        if relative:
                            original = old.path(relative)
                            if not original.is_file() or sha256_file(original) != source.get('sha256'):
                                raise ValueError('Old source failed hash validation')
                            source_inputs.append(str(original))
                if value.get('artifact_type') == 'phase-result' and value.get('phase', 99) > 7:
                    continue
                if value.get('schema_version') == '4.0':
                    validate_artifact(value)
                if value.get('artifact_type') in ('screenplay', 'screenplay-enhanced', 'shot-plan', 'phase-result'):
                    verified.append(str(path))
        if not verified:
            verified = list(dict.fromkeys(source_inputs))
        if not verified:
            raise ValueError('No validated reusable narrative artifacts; provide original story inputs')
        new = cls.initialize(destination, verified, title=project.get('title'))
        with new.store.transaction():
            for path in sorted(old.root.rglob('*')):
                if path.is_file() and not path.relative_to(old.root).parts[0] == 'runtime':
                    new.store.copy_source(path, '.history/migrations/' + path.relative_to(old.root).as_posix())
            new.commit(phase(1)['folder'] + '/migration.json', 'migration-record', {'source_version': project['schema_version'],
                'old_project_id': project['project_id'], 'reused_inputs': verified, 'approvals_reused': False,
                'images': 'Retained in migration history; import explicitly after V4 validation.'})
            new.manifest()
        return new
