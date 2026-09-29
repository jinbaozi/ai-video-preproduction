"""Read-only RunningHub native-H3 graph inspection and compare-and-swap planning.

The API graph is DATA, never code. This module does not fetch URLs, install nodes,
submit tasks, or rewrite links. API/partner H3 wrappers need separate adapters.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
import math
import re
from typing import Any

from h3_runtime import check_prompt, fingerprint, frame_shape, require

NATIVE = {'MiniMaxH3ImageToVideo': 'fl2va', 'MiniMaxH3ReferenceToVideo': 'ref2va'}
SAMPLERS = {'KSampler', 'KSamplerAdvanced', 'SamplerCustom', 'SamplerCustomAdvanced'}
SECRET_KEYS = {'apikey', 'accesstoken', 'authorization', 'password', 'secret', 'clientsecret'}


def _secret_scan(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r'[^a-z0-9]', '', str(key).lower())
            require(normalized not in SECRET_KEYS or child in (None, ''),
                    'E_RH_SECRET', 'remove credentials from the workflow export before processing')
            _secret_scan(child)
    elif isinstance(value, list):
        for child in value:
            _secret_scan(child)


def graph_data(value: Any) -> dict[str, dict]:
    """Accept raw API JSON and Comfy's {prompt: API_JSON} envelope only."""
    _secret_scan(value)
    if isinstance(value, dict) and 'prompt' in value and not (isinstance(value['prompt'], dict) and 'class_type' in value['prompt']):
        # A node literally named "prompt" must not be mistaken for an envelope.
        value = value['prompt']
    require(isinstance(value, dict) and value and 'nodes' not in value,
            'E_RH_API_EXPORT', 'use Export Workflow API, not visual nodes/widgets_values JSON')
    require(len(value) <= 10000, 'E_RH_GRAPH_SIZE', 'workflow too large for this adapter')
    for node_id, node in value.items():
        require(isinstance(node_id, str) and bool(node_id) and isinstance(node, dict) and
                isinstance(node.get('class_type'), str) and bool(node['class_type']) and
                isinstance(node.get('inputs'), dict), 'E_RH_NODE', 'invalid API node: ' + str(node_id))
    edges = list(_edges(value))
    # Reject cycles without recursion (a deep but valid graph must not overflow Python).
    counts = {n: 0 for n in value}
    children = {n: [] for n in value}
    for source, target, _, _ in edges:
        counts[target] += 1
        children[source].append(target)
    queue = deque(n for n, count in counts.items() if count == 0)
    visited = 0
    while queue:
        node_id = queue.popleft()
        visited += 1
        for child in children[node_id]:
            counts[child] -= 1
            if counts[child] == 0:
                queue.append(child)
    require(visited == len(value), 'E_RH_CYCLE', 'API graph contains a dependency cycle')
    return value


def _edges(graph: dict):
    def walk(value, target, path):
        if isinstance(value, list):
            require(len(value) == 2 and isinstance(value[0], str) and value[0] in graph and
                    type(value[1]) is int and value[1] >= 0,
                    'E_RH_LINK', 'unsupported literal array or dangling connection: ' + target + '/' + '/'.join(path))
            yield value[0], target, tuple(path), value[1]
        elif isinstance(value, dict):
            for key, child in value.items():
                yield from walk(child, target, [*path, key])
    for node_id, node in graph.items():
        yield from walk(node['inputs'], node_id, [])


def _closure(graph: dict, roots: set[str], upstream=True) -> set[str]:
    seen = set(roots)
    edges = list(_edges(graph))
    queue = deque(roots)
    adjacency = {node_id: set() for node_id in graph}
    for source, target, _, _ in edges:
        adjacency[target if upstream else source].add(source if upstream else target)
    while queue:
        current = queue.popleft()
        for item in adjacency[current] - seen:
            seen.add(item)
            queue.append(item)
    return seen


def _channels(inputs: dict, group: str, prefix: str):
    """Recognize explicit native Autogrow keys; retain the export's actual order."""
    for key, value in inputs.items():
        if key == group:
            require(isinstance(value, dict), 'E_RH_AUTOGROW', 'unsupported autogrow container')
            for name, link in value.items():
                require(re.fullmatch(re.escape(prefix) + r'\d+', name) is not None,
                        'E_RH_AUTOGROW', 'unknown autogrow member: ' + name)
                if link is not None:
                    yield [key, name], name, link
        elif re.fullmatch(r'(?:' + re.escape(group) + r'\.)?' + re.escape(prefix) + r'\d+', key):
            if value is not None:
                yield [key], key.rsplit('.', 1)[-1], value


def references(graph: dict, node_id: str) -> tuple[str, list[dict]]:
    node = graph[node_id]
    inputs = node['inputs']
    require(isinstance(inputs.get('clip'), list), 'E_RH_CLIP', 'native H3 text encoder must be connected')
    if NATIVE[node['class_type']] == 'ref2va':
        require(not any(k in inputs for k in ('first_frame', 'last_frame')),
                'E_RH_MIXED_MODE', 'Ref2VA native node cannot receive first/last-frame ports')
    else:
        require(isinstance(inputs.get('vae'), list), 'E_RH_VIDEO_VAE', 'FL2VA native node requires video VAE')
        require(not any(k.startswith('ref_') for k in inputs), 'E_RH_MIXED_MODE', 'FL2VA node cannot receive reference ports')
    rows = []
    counts = Counter()
    def add(kind, field, link, role):
        require(isinstance(link, list) and len(link) == 2 and link[0] in graph,
                'E_RH_REFERENCE_LINK', 'native media must be connected, not a URL/filename literal')
        counts[kind] += 1
        label = '<' + {'image': 'Picture', 'video': 'Video', 'audio': 'Audio'}[kind] + f' {counts[kind]}>'
        rows.append({'label': label, 'kind': kind, 'role': role, 'input_path': field,
                     'source_node_id': link[0], 'source_output': link[1]})
    if NATIVE[node['class_type']] == 'fl2va':
        for key in ('first_frame', 'last_frame'):
            if inputs.get(key) is not None:
                add('image', [key], inputs[key], key)
        mode = {(False, False): 't2va', (True, False): 'i2va',
                (False, True): 'l2va', (True, True): 'fl2va'}[
                    (inputs.get('first_frame') is not None, inputs.get('last_frame') is not None)]
    else:
        mode = 'ref2va'
        images = list(_channels(inputs, 'ref_images', 'ref_image_'))
        videos = list(_channels(inputs, 'ref_videos', 'ref_video_'))
        paired = list(_channels(inputs, 'ref_video_audios', 'ref_video_audio_'))
        audios = list(_channels(inputs, 'ref_audios', 'ref_audio_'))
        require(len(images) <= 9 and len(videos) <= 3 and len(audios) <= 3 and
                len(images)+len(videos)+len(audios) <= 12, 'E_H3_REF_LIMIT', 'reference file limit exceeded')
        require(images or videos or audios, 'E_H3_MODE_MEDIA', 'Ref2VA has no attached reference')
        sounds = {name.rsplit('_', 1)[-1]: (field, link) for field, name, link in paired}
        require(len(sounds) == len(paired) and set(sounds) <= {name.rsplit('_', 1)[-1] for _, name, _ in videos},
                'E_RH_PAIRED_AUDIO', 'soundtrack has no matching video or duplicate suffix')
        for field, _, link in images:
            add('image', field, link, 'reference_image')
        for field, name, link in videos:
            sound = sounds.get(name.rsplit('_', 1)[-1])
            if sound:
                add('audio', sound[0], sound[1], 'video_soundtrack')
            add('video', field, link, 'reference_video')
        for field, _, link in audios:
            add('audio', field, link, 'reference_audio')
        if images or videos:
            require(isinstance(inputs.get('vae'), list), 'E_RH_VIDEO_VAE', 'visual references need the video VAE link')
        if paired or audios:
            require(isinstance(inputs.get('audio_vae'), list), 'E_RH_AUDIO_VAE', 'audio references need the audio VAE link')
    return mode, rows


def inspect(value: dict) -> dict:
    graph = graph_data(value)
    candidates = []
    for node_id, node in graph.items():
        if node['class_type'] not in NATIVE:
            continue
        try:
            mode, refs = references(graph, node_id)
            diagnostics = []
        except ValueError as error:
            mode, refs, diagnostics = None, [], [str(error)]
        candidates.append({'node_id': node_id, 'class_type': node['class_type'], 'mode': mode,
                           'references': refs, 'diagnostics': diagnostics,
                           'scalar_fields': {k: v for k, v in node['inputs'].items()
                                             if type(v) in (str, bool, int, float)}})
    return {'schema': 'runninghub-h3-inspection/1.0', 'workflow_sha256': fingerprint(graph),
            'native_h3_nodes': candidates,
            'selection': 'UNAMBIGUOUS' if len(candidates) == 1 else 'EXPLICIT_SELECTION_REQUIRED',
            'source': 'supplied_API_export', 'live_runninghub_verified': False, 'submitted': False}


def _positive_path(graph: dict, source: str, sampler: str) -> bool:
    """Never mistake an unused/negative-only H3 prompt for the positive branch."""
    stack = [sampler]
    visited = set()
    while stack:
        node_id = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        fields = {'positive', 'conditioning', 'guider', 'conditioning_1', 'conditioning_2'}
        for field, link in graph[node_id]['inputs'].items():
            if field not in fields or not isinstance(link, list):
                continue
            if link == [source, 0]:
                return True
            stack.append(link[0])
    return False


def _typed(value, expected):
    if type(expected) in (float, int) and type(value) in (float, int):
        return math.isfinite(value) and (type(expected) is float or type(value) is int)
    return type(value) is type(expected) and type(value) in (str, bool)


def _set(graph, edit):
    required = {'nodeId', 'classType', 'fieldName', 'expectedValue', 'fieldValue'}
    require(isinstance(edit, dict) and set(edit) == required, 'E_RH_EDIT', 'edits need exact CAS fields')
    node_id, field = edit['nodeId'], edit['fieldName']
    require(isinstance(node_id, str) and node_id in graph, 'E_RH_NODE_ID', 'unknown node')
    node = graph[node_id]
    require(node['class_type'] == edit['classType'], 'E_RH_CLASS_DRIFT', 'node class changed')
    require(isinstance(field, str) and field in node['inputs'] and field != 'control_after_generate',
            'E_RH_FIELD', 'field is absent, nested, or frontend-only')
    old = node['inputs'][field]
    require(type(old) in (str, bool, int, float), 'E_RH_PROTECTED_LINK', 'cannot replace connections or structured inputs')
    require(type(old) is type(edit['expectedValue']) and old == edit['expectedValue'],
            'E_RH_VALUE_DRIFT', 'old value differs from the inspected snapshot')
    new = edit['fieldValue']
    require(_typed(new, old), 'E_RH_VALUE_TYPE', 'new value has an incompatible scalar type')
    if field in ('seed', 'noise_seed'):
        require(type(new) is int and 0 <= new < 2**64, 'E_RH_SEED', 'explicit uint64 seed required')
    if field in ('steps', 'turbo_steps'):
        require(type(new) is int and 1 <= new <= 1000, 'E_RH_STEPS', 'steps must be a positive integer')
    if field in ('cfg', 'guidance'):
        require(type(new) in (int, float) and 0 <= new <= 100, 'E_RH_CFG', 'invalid guidance value')
    if node['class_type'] == 'LoadImage' and field == 'image':
        require(isinstance(new, str) and not url_like(new) and '..' not in new.replace('\\', '/').split('/') and
                not new.startswith(('/', '\\')) and not re.match(r'^[A-Za-z]:', new),
                'E_RH_UPLOAD_NAME', 'LoadImage requires a RunningHub upload fileName, not a URL/local absolute path')
    node['inputs'][field] = new


def url_like(value: str) -> bool:
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', value))


def _value_string(value):
    if type(value) is bool:
        return 'true' if value else 'false'
    return str(value)


def plan(value: dict, prompt: str, node_id: str, expected_sha256: str,
         edits: list[dict] | None = None, prompt_binding: dict | None = None,
         upload_receipts: dict[str, dict] | None = None) -> tuple[dict, dict]:
    """Return an auditable nodeInfoList and an offline patched COPY of the graph.

    Every explicit edit is CAS-checked. All reachable seed fields are pinned.
    A successful return means static planning, not a runnable/paid task.
    """
    original = graph_data(value)
    require(fingerprint(original) == expected_sha256, 'E_RH_WORKFLOW_DRIFT', 're-inspect the current API export')
    require(node_id in original and original[node_id]['class_type'] in NATIVE,
            'E_RH_H3_NODE', 'select one inspected native H3 node, not an API wrapper')
    graph = deepcopy(original)
    edits = deepcopy(edits) if edits is not None else []
    require(isinstance(edits, list), 'E_RH_EDIT', 'edits must be an array')
    direct = graph[node_id]['inputs'].get('prompt')
    if isinstance(direct, str):
        require(prompt_binding is None, 'E_RH_PROMPT_BINDING', 'direct prompt requires no alternate binding')
        prompt_edit = {'nodeId': node_id, 'classType': graph[node_id]['class_type'], 'fieldName': 'prompt',
                       'expectedValue': direct, 'fieldValue': prompt}
    else:
        require(isinstance(direct, list) and isinstance(prompt_binding, dict) and
                set(prompt_binding) == {'nodeId', 'classType', 'fieldName'},
                'E_RH_PROMPT_BINDING', 'linked prompt requires an explicit inspected scalar producer')
        source = prompt_binding['nodeId']
        require(source in _closure(graph, {direct[0]}), 'E_RH_PROMPT_PATH', 'binding does not feed this H3 prompt port')
        old = graph[source]['inputs'].get(prompt_binding['fieldName'])
        require(isinstance(old, str), 'E_RH_PROMPT_BINDING', 'prompt producer must be a string field')
        prompt_edit = dict(prompt_binding, expectedValue=old, fieldValue=prompt)
    edits.insert(0, prompt_edit)
    seen = set()
    for edit in edits:
        require(isinstance(edit, dict), 'E_RH_EDIT', 'edit must be an object')
        key = (edit.get('nodeId'), edit.get('fieldName'))
        require(key not in seen, 'E_RH_DUPLICATE_EDIT', 'two writes target the same field')
        seen.add(key)
        _set(graph, edit)
        if edit['classType'] == 'LoadImage' and edit['fieldName'] == 'image':
            receipt = (upload_receipts or {}).get(edit['nodeId'], {})
            require(isinstance(receipt, dict) and type(receipt.get('code')) is int and receipt['code'] == 0 and
                    isinstance(receipt.get('data'), dict) and receipt['data'].get('fileName') == edit['fieldValue'],
                    'E_RH_UPLOAD_RECEIPT', 'changed LoadImage needs its actual matching upload response')
    descendants = _closure(graph, {node_id}, upstream=False)
    samplers = {n for n in descendants if graph[n]['class_type'] in SAMPLERS}
    require(bool(samplers) and all(_positive_path(graph, node_id, n) for n in samplers),
            'E_RH_UNUSED_H3', 'selected H3 must feed the POSITIVE conditioning path of every affected sampler')
    relevant = _closure(graph, samplers)
    checkpoints = [n['inputs'].get('unet_name', n['inputs'].get('ckpt_name', ''))
                   for key, n in graph.items() if key in relevant and
                   n['class_type'] in ('UNETLoader', 'CheckpointLoaderSimple')]
    family = NATIVE[graph[node_id]['class_type']]
    require(bool(checkpoints) and any(isinstance(name, str) and 'minimax' in name.lower() and
            'h3' in name.lower() and family in name.lower() for name in checkpoints),
            'E_RH_CHECKPOINT_FAMILY', 'no matching H3 diffusion checkpoint name on the sampling path')
    other = 'ref2va' if family == 'fl2va' else 'fl2va'
    require(not any(isinstance(name, str) and 'h3' in name.lower() and other in name.lower() for name in checkpoints),
            'E_RH_CHECKPOINT_FAMILY', 'opposite H3 checkpoint family is also on this sampling path')
    seeds = 0
    for key, node in graph.items():
        if key not in relevant:
            continue
        for field, current in node['inputs'].items():
            if field not in ('seed', 'noise_seed'):
                continue
            require(type(current) is int and 0 <= current < 2**64,
                    'E_RH_SEED', 'linked/random/invalid seed cannot be pinned without rewriting links')
            seeds += 1
            if (key, field) not in seen:
                edits.append({'nodeId': key, 'classType': node['class_type'], 'fieldName': field,
                              'expectedValue': current, 'fieldValue': current})
                seen.add((key, field))
    require(seeds > 0, 'E_RH_SEED', 'no explicit seed on the supported sampling path')
    inputs = graph[node_id]['inputs']
    width, height, length = (inputs.get(k) for k in ('width', 'height', 'length'))
    require(all(type(v) is int and v >= 32 and v % 32 == 0 for v in (width, height)),
            'E_RH_CANVAS', 'native canvas dimensions must be integer multiples of 32')
    require(width*height <= 768*1344, 'E_RH_CANVAS_AREA', 'base canvas exceeds the verified area profile; use a separate regenerate/upscale workflow')
    shape = frame_shape(length)
    require(96 <= length <= 362, 'E_RH_LENGTH_PROFILE', 'outside the scoped 4..15s native base profile')
    require(inputs.get('ref_image_size', 'match') in ('match', 'max'), 'E_RH_REF_SIZE', 'unknown reference resize mode')
    mode, refs = references(graph, node_id)
    checks = check_prompt(prompt, mode, shape['effective_seconds'], [r['label'] for r in refs])
    require(not checks['errors'], 'E_RH_PROMPT_CHECK', ', '.join(checks['errors']))
    require(list(_edges(original)) == list(_edges(graph)), 'E_RH_LINK_CHANGED', 'planning must preserve all connections')
    warnings = list(checks['warnings'])
    if prompt_binding is not None:
        warnings.append('W_PROMPT_PRODUCER_SEMANTICS: verify the explicitly bound custom string producer output')
    if shape['changed']:
        warnings.append('W_H3_FRAME_GRID_REVIEW: native frame count snaps up; review action and last-frame timing')
    if length < 124:
        warnings.append('W_H3_SHORT_NATIVE_CLIP: below the native source tooltip training range; verify quality')
    warnings.append('W_RUNTIME_UNVERIFIED: node installation, actual weights, media bytes and RunningHub account are not checked')
    # Deliberately do not auto-enable turbo, precision patches, masks or control nodes.
    result = {'schema': 'runninghub-h3-plan/1.0', 'status': 'PLANNED_REQUIRES_RUNTIME_CHECK',
              'workflow_sha256': expected_sha256, 'patched_workflow_sha256': fingerprint(graph),
              'h3_node_id': node_id, 'mode': mode, 'checkpoint_names': checkpoints,
              'checkpoint_verification': 'filename_only', 'frame_shape': shape,
              'canvas': {'width': width, 'height': height}, 'references': refs,
              'edits': edits, 'nodeInfoList': [{'nodeId': e['nodeId'], 'fieldName': e['fieldName'],
                                             'fieldValue': _value_string(e['fieldValue'])} for e in edits],
              'prompt_check': checks, 'warnings': warnings, 'link_changes': 0,
              'prompt_origin': 'caller_supplied_candidate', 'official_context_ir_executed': False,
              'submitted': False, 'runnable': False, 'media_qa': 'NOT_RUN'}
    return result, graph
