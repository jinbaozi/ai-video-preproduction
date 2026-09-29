"""Offline H3 prompt checks and explicit import of hosted Context-IR receipts.

This is NOT MiniMax's proprietary Context-IR implementation. No network calls,
credentials, generation submission, or semantic-success claims live here.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit

BASE_FIELDS = ('integrated_multimodal_description', 'overall_soundscape', 'non_diegetic_music')
REF_FIELDS = ('subject_definitions', 'summary', 'retention_analysis', 'detailed_description',
              'overall_soundscape', 'non_diegetic_music')
MODES = ('t2va', 'i2va', 'fl2va', 'l2va', 'ref2va')
CONTEXT_ENDPOINT = 'https://api.minimax.io/v2/h3_context_ir'
RATIOS = ('21:9', '16:9', '4:3', '1:1', '3:4', '9:16', 'adaptive')
LABEL_RE = re.compile(r'<(Picture|Video|Audio|Subject) ([1-9][0-9]*)>')


def fingerprint(value: Any) -> str:
    """Preserve insertion order: native autogrow reference order is semantic."""
    return sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')).hexdigest()


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ValueError(f'{code}: {message}')


def frame_shape(length: int) -> dict[str, Any]:
    """Pinned Comfy native algorithm: snap UP to 17k+5; never retime silently."""
    require(type(length) is int and 5 <= length <= 3600, 'E_H3_LENGTH', 'length must be an integer in 5..3600')
    frames = length + (5 - length) % 17
    return {'requested_frames': length, 'effective_frames': frames, 'fps': 24,
            'effective_seconds': frames / 24, 'last_frame_seconds': (frames - 1) / 24,
            'changed': frames != length,
            'source': 'Comfy-Org/ComfyUI@a7169322485d0049380fb207fa17e9fb3ec40486'}


def check_prompt(text: str, mode: str, duration: float,
                 reference_labels: list[str] | None = None) -> dict[str, Any]:
    """Syntactic checks only; original dialogue and visible text are never rewritten."""
    require(mode in MODES, 'E_H3_MODE', 'unknown input mode')
    require(isinstance(text, str) and text.strip(), 'E_H3_PROMPT', 'empty prompt')
    require(type(duration) in (int, float) and math.isfinite(duration) and duration > 0,
            'E_H3_DURATION', 'finite positive duration required')
    errors, warnings = [], []
    fields = REF_FIELDS if mode == 'ref2va' else BASE_FIELDS
    pattern = r'^(' + '|'.join(dict.fromkeys(BASE_FIELDS + REF_FIELDS)) + r')\s*:'
    headings = list(re.finditer(pattern, text, re.M))
    if tuple(m[1] for m in headings) != fields:
        errors.append('E_H3_SECTION_ORDER')
    for i, match in enumerate(headings):
        end = headings[i+1].start() if i+1 < len(headings) else len(text)
        if not text[match.end():end].strip():
            errors.append('E_H3_EMPTY_SECTION:' + match[1])
    # Restrict shot parsing to the main body: reference definitions also mention shots.
    main = 'detailed_description' if mode == 'ref2va' else 'integrated_multimodal_description'
    body = re.search(r'^' + main + r'\s*:(.*?)(?=^overall_soundscape\s*:|\Z)', text, re.M | re.S)
    if body:
        shots = list(re.finditer(r'\[Shot ([1-9][0-9]*)\]', body[1]))
        if not shots or [int(m[1]) for m in shots] != list(range(1, len(shots)+1)):
            errors.append('E_H3_SHOT_NUMBERING')
        previous = 0.0
        for i, shot in enumerate(shots):
            tail = body[1][shot.end():]
            if i == 0:
                if re.match(r'\s*At\s+\d', tail):
                    errors.append('E_H3_FIRST_SHOT_TIMESTAMP')
                continue
            stamp = re.match(r'\s*At (\d{2}):([0-5]\d)\.(\d{3})\b', tail)
            if not stamp:
                errors.append('E_H3_CUT_TIMESTAMP')
                continue
            at = int(stamp[1])*60 + int(stamp[2]) + int(stamp[3])/1000
            if not previous < at < duration:
                errors.append('E_H3_CUT_RANGE')
            previous = at
    else:
        errors.append('E_H3_MAIN_BODY')
    dialogue = re.findall(r'<d>(.*?)</d>', text, re.S)
    if len(dialogue) != text.count('<d>') or len(dialogue) != text.count('</d>'):
        errors.append('E_H3_DIALOGUE_TAGS')
    if any(not re.fullmatch(r'\[[^\]\n]+\] .+', line, re.S) or '<d>' in line for line in dialogue):
        errors.append('E_H3_DIALOGUE_LANGUAGE')
    if any(re.search(r'\[(?:UNRESOLVED|Unknown|Original language)\]', line, re.I) for line in dialogue):
        errors.append('E_H3_DIALOGUE_LANGUAGE')
    if mode in ('i2va', 'l2va', 'fl2va'):
        prefix = text[:headings[0].start()] if headings else ''
        # Guide prose is host-authored, not inferred from reference images by this checker.
        if not prefix.strip() or 'Picture 1' not in prefix:
            errors.append('E_H3_KEYFRAME_ALIGNMENT')
        if mode == 'fl2va' and 'Picture 2' not in prefix:
            errors.append('E_H3_KEYFRAME_ALIGNMENT')
    labels = list(dict.fromkeys(m[0] for m in LABEL_RE.finditer(text) if m[1] != 'Subject'))
    if mode in ('i2va', 'l2va', 'fl2va') and headings:
        prefix = text[:headings[0].start()]
        labels += ['<Picture ' + n + '>' for n in re.findall(r'(?<!<)\bPicture ([1-9][0-9]*)\b', prefix)]
    if reference_labels is not None:
        require(isinstance(reference_labels, list) and all(isinstance(x, str) for x in reference_labels),
                'E_H3_REFERENCE_LABELS', 'reference labels must be an array of strings')
        # Exact sets, not prefix/string containment: <Picture 10> is not <Picture 1>.
        if set(labels) != set(reference_labels):
            errors.append('E_H3_REFERENCE_LABELS')
    if mode == 'ref2va' and 'retention_analysis' in [m[1] for m in headings]:
        retention = re.search(r'^retention_analysis\s*:(.*?)(?=^detailed_description\s*:|\Z)', text, re.M | re.S)[1]
        for label in labels:
            if label.startswith('<Audio '):
                if not re.search(re.escape(label) + r'[^\n]*\b(fully_copy|partially_copy|reference|weak_reference)\b', retention):
                    errors.append('E_H3_AUDIO_RETENTION:' + label)
    if mode == 'ref2va':
        definitions = re.search(r'^subject_definitions\s*:(.*?)(?=^summary\s*:|\Z)', text, re.M | re.S)
        declared = set(re.findall(r'<Subject [1-9][0-9]*>', definitions[1])) if definitions else set()
        mentioned = set(re.findall(r'<Subject [1-9][0-9]*>', text))
        if not mentioned <= declared:
            errors.append('E_H3_UNDEFINED_SUBJECT')
    # Conservative warning, not an assertion that all non-ASCII text is Chinese.
    # Host translates prose BEFORE approval; this module never translates locked text.
    prose = re.sub(r'<d>.*?</d>|"[^"]*"|`[^`]*`', '', text, flags=re.S)
    if re.search(r'[\u3400-\u9fff]', prose):
        warnings.append('W_H3_ENGLISH_PROSE_REVIEW')
    return {'status': 'BLOCKED' if errors else 'STRUCTURE_CHECKED',
            'errors': sorted(set(errors)), 'warnings': warnings,
            'prompt_sha256': sha256(text.encode('utf-8')).hexdigest(),
            'semantic_review': 'NOT_RUN', 'media_qa': 'NOT_RUN', 'submitted': False}


def context_request(text: str, mode: str, duration: int, ratio: str,
                    media: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build an OFFLINE official API draft, deliberately narrower than the full API.

    URLs must be https; inline base64 and callbacks are intentionally unsupported.
    Unknown sizes/durations remain unverified, never counted as media acceptance.
    """
    require(isinstance(text, str) and bool(text.strip()), 'E_H3_PROMPT', 'text is required')
    require(mode in MODES, 'E_H3_MODE', 'unknown input mode')
    require(type(duration) is int and 4 <= duration <= 15, 'E_H3_DURATION', 'official API accepts integer 4..15 seconds')
    require(ratio in RATIOS, 'E_H3_RATIO', 'unsupported ratio')
    require((mode not in ('i2va', 'l2va', 'fl2va') or ratio == 'adaptive') and
            (mode != 't2va' or ratio != 'adaptive'), 'E_H3_RATIO_MODE',
            'keyframe API tasks require adaptive; text tasks require a concrete ratio')
    media = [] if media is None else media
    require(isinstance(media, list), 'E_H3_MEDIA', 'media must be an ordered array')
    roles = Counter()
    content = [{'type': 'text', 'text': text}]
    totals = Counter()
    for item in media:
        require(isinstance(item, dict) and set(item) <= {'kind', 'role', 'url', 'duration_seconds'},
                'E_H3_MEDIA_FIELDS', 'unknown media fields')
        kind, role, url = item.get('kind'), item.get('role'), item.get('url')
        require(kind in ('image', 'video', 'audio'), 'E_H3_MEDIA_KIND', 'image/video/audio only')
        allowed = {'first_frame', 'last_frame'} if mode in ('i2va', 'l2va', 'fl2va') else {'reference_' + str(kind)}
        require(role in allowed and (not role.endswith('_frame') or kind == 'image'),
                'E_H3_MEDIA_ROLE', 'keyframe and reference roles cannot be mixed')
        require(isinstance(url, str), 'E_H3_MEDIA_URL', 'https URL required')
        parsed = urlsplit(url)
        require(parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password,
                'E_H3_MEDIA_URL', 'https URL without embedded credentials required')
        if kind in ('video', 'audio') and 'duration_seconds' in item:
            length = item['duration_seconds']
            require(type(length) in (int, float) and math.isfinite(length) and 2 <= length <= 15,
                    'E_H3_MEDIA_DURATION', 'each reference clip must be 2..15 seconds')
            totals[kind] += length
        roles[role] += 1
        content.append({'type': kind + '_url', kind + '_url': {'url': url}, 'role': role})
    expected = {'t2va': {}, 'i2va': {'first_frame': 1}, 'l2va': {'last_frame': 1},
                'fl2va': {'first_frame': 1, 'last_frame': 1}}
    if mode != 'ref2va':
        require(dict(roles) == expected[mode], 'E_H3_MODE_MEDIA', 'mode and attached media disagree')
    else:
        require(bool(media), 'E_H3_MODE_MEDIA', 'reference mode needs media')
        require(roles['reference_image'] <= 9 and roles['reference_video'] <= 3 and
                roles['reference_audio'] <= 3 and len(media) <= 12,
                'E_H3_REF_LIMIT', 'model reference limits exceeded')
        require(all(n <= 15 for n in totals.values()), 'E_H3_MEDIA_TOTAL', 'reference video/audio totals must each be <=15 seconds')
    return {'model': 'MiniMax-H3', 'content': content, 'duration': duration, 'ratio': ratio}


def import_context(request: dict, created: dict, result: dict) -> dict[str, Any]:
    """Validate caller-supplied official creation/query receipts, not their authenticity.

    Import is a NEW candidate, never an in-place replacement of frozen AVIR.
    RunningHub's provider wrapper is intentionally NOT parsed as the MiniMax API.
    """
    require(isinstance(request, dict) and request.get('model') == 'MiniMax-H3',
            'E_CONTEXT_REQUEST', 'expected MiniMax-H3 request')
    require(type(request.get('duration')) is int and 4 <= request['duration'] <= 15 and
            request.get('ratio') in RATIOS and isinstance(request.get('content'), list) and
            any(isinstance(item, dict) and item.get('type') == 'text' and
                isinstance(item.get('text'), str) and item['text'].strip() for item in request['content']),
            'E_CONTEXT_REQUEST', 'original request must include valid duration, ratio and nonempty text content')
    require(isinstance(created, dict) and isinstance(created.get('task_id'), str) and created['task_id'],
            'E_CONTEXT_ACK', 'creation response task_id required')
    task = result.get('task') if isinstance(result, dict) else None
    require(isinstance(task, dict), 'E_CONTEXT_RESULT', 'official Query Task response required')
    require(task.get('id') == created['task_id'], 'E_CONTEXT_TASK_ID', 'creation/query task mismatch')
    require(task.get('model') == 'MiniMax-H3' and task.get('task_type') == 'h3_context_ir' and
            task.get('modality') == 'text', 'E_CONTEXT_TASK_TYPE', 'this is not an H3 Context-IR text task')
    require(task.get('status') == 'succeeded', 'E_CONTEXT_NOT_SUCCEEDED', 'queued/running/failed results are not prompts')
    require(task.get('duration') == request.get('duration') and task.get('ratio') == request.get('ratio'),
            'E_CONTEXT_REQUEST_DRIFT', 'duration or ratio differs from the submitted request')
    require(isinstance(task.get('content'), dict), 'E_CONTEXT_EMPTY', 'content must be an object')
    prompt = task['content'].get('prompt')
    require(isinstance(prompt, str) and bool(prompt.strip()), 'E_CONTEXT_EMPTY', 'completed task has no prompt')
    return {'schema': 'h3-context-candidate/1.0', 'status': 'IMPORTED_REQUIRES_SEMANTIC_REVIEW',
            'declared_provider': 'minimax-official-api', 'task_id': task['id'], 'prompt': prompt,
            'request_sha256': fingerprint(request), 'creation_sha256': fingerprint(created),
            'response_sha256': fingerprint(result), 'prompt_sha256': sha256(prompt.encode()).hexdigest(),
            'provenance': 'caller_supplied_receipts', 'transport_authentication': 'NOT_VERIFIED',
            'semantic_review': 'NOT_RUN', 'submitted': False, 'runnable': False, 'media_qa': 'NOT_RUN'}
