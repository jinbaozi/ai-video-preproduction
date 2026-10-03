"""Offline source-grounded retrieval, with exact scope and immutable local reads.

External sources are citations/data, never imports, commands or authorizations.
A successful read/route audit makes no claim about host comprehension or live video.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'community-knowledge/1.0'
ROLES = ('screenplay', 'director', 'art', 'storyboard', 'image-prompt', 'avir', 'compile-review')
MODES = ('text', 'keyframe', 'reference', 'edit', 'extend')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


def strings(value, name, *, allow_empty=True):
    if not isinstance(value, (list, tuple)) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(name + ': expected strings')
    if len(set(value)) != len(value) or (not allow_empty and not value):
        raise ValueError(name + ': empty or duplicate entries')
    return list(value)


def local_path(root, relative):
    """No absolute paths, traversal, backslashes, URL, encoded path or symlink escape."""
    if not isinstance(relative, str) or not relative or re.search(r'[\\\x00-\x20%:#?]', relative):
        raise ValueError('Unsafe knowledge path')
    path = PurePosixPath(relative)
    if path.is_absolute() or any(p in ('.', '..') for p in relative.split('/')):
        raise ValueError('Unsafe knowledge path')
    root = Path(root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('Knowledge file missing or outside locked module: ' + relative)
    return resolved


def read_section(root, descriptor):
    if not isinstance(descriptor, dict):
        raise ValueError('Knowledge reading must be an object')
    path = local_path(root, descriptor.get('path'))
    data = path.read_bytes()
    if sha256(data).hexdigest() != descriptor.get('file_sha256'):
        raise ValueError('Knowledge source note bytes changed: ' + descriptor['path'])
    section = descriptor.get('section')
    if not isinstance(section, str) or not re.fullmatch(r'[a-z0-9-]+', section):
        raise ValueError('Invalid knowledge section')
    text = data.decode('utf-8')
    headings = list(re.finditer(r'^## ([^\n]+)\n', text, re.M))
    selected = [(i, m) for i, m in enumerate(headings) if m.group(1) == section]
    if len(selected) != 1:
        raise ValueError('Knowledge section missing or ambiguous: ' + section)
    i, match = selected[0]
    stop = headings[i+1].start() if i+1 < len(headings) else len(text)
    body = text[match.end():stop].strip()
    if not body:
        raise ValueError('Empty knowledge section')
    return {**descriptor, 'text': body, 'section_sha256': sha256(body.encode()).hexdigest(),
            'read_status': 'READ_LOCAL_NOTE', 'external_response_hash': None}


def catalog(root=ROOT):
    root = Path(root)
    data = json.loads(local_path(root, 'registries/community-knowledge.json').read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') != POLICY:
        raise ValueError('Unsupported community catalogue')
    for key in ('sources', 'cards'):
        if not isinstance(data.get(key), list) or any(not isinstance(r, dict) for r in data[key]):
            raise ValueError('Invalid knowledge section: ' + key)
        strings([r.get('id') for r in data[key]], key, allow_empty=False)
    sources = {r['id']: r for r in data['sources']}
    caps = json.loads((root/'registries/capabilities.json').read_text(encoding='utf-8'))['profiles']
    capabilities = {r['id']: digest(r) for r in caps}
    for source in sources.values():
        url = urlparse(source.get('url', ''))
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Invalid source URL')
        if source.get('read_status') not in ('READ', 'UNAVAILABLE') or source.get('kind') not in (
                'official_docs', 'author_documentation', 'community_index', 'discovery'):
            raise ValueError('Invalid source classification')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', source.get('checked_at', '')):
            raise ValueError('Source lacks dated observation')
    for row in data['cards']:
        allowed = {'id','title','roles','modes','tags','always','sources','profiles','instruction','check','native_fields','scope','status','reading'}
        if set(row) != allowed:
            raise ValueError('Unknown or missing community card fields; no executable extensions')
        if row.get('status') != 'ADMITTED' or row.get('scope') not in ('portable_method', 'exact_profile'):
            raise ValueError('Invalid admitted card')
        for field, allowed in (('roles', ROLES), ('modes', MODES)):
            if not set(strings(row.get(field), field, allow_empty=False)) <= set(allowed):
                raise ValueError('Unknown card scope: ' + field)
        strings(row.get('tags'), 'tags')
        if type(row.get('always')) is not bool or not (row['always'] or row['tags']):
            raise ValueError('Unreachable card: no trigger')
        for field in ('title', 'instruction', 'check'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError('Empty method ' + field)
        strings(row.get('native_fields'), 'native_fields', allow_empty=False)
        for identifier in strings(row.get('sources'), 'sources', allow_empty=False):
            if identifier not in sources or sources[identifier]['read_status'] != 'READ' or sources[identifier]['kind'] == 'discovery':
                raise ValueError('Unread/discovery source cannot support an admitted rule')
        profiles = row.get('profiles')
        if not isinstance(profiles, dict) or bool(profiles) != (row['scope'] == 'exact_profile'):
            raise ValueError('Invalid exact profile selectors')
        for identifier, fingerprint in profiles.items():
            if capabilities.get(identifier) != fingerprint:
                raise ValueError('Stale or unknown profile selector: ' + identifier)
        # The entire catalogue remains source-closed, not only today's selected card.
        read_section(root, row.get('reading'))
    return data


def plan(cap=None, mode='text', *, role='avir', tags=(), root=ROOT):
    if cap is not None and not isinstance(cap, dict):
        raise ValueError('Capability must be an object or None')
    if role not in ROLES or mode not in MODES:
        raise ValueError('Unknown knowledge role or mode')
    tags = strings(tags, 'tags')
    data = catalog(root)
    folded = {tag.casefold() for tag in tags}
    cards = []
    for row in data['cards']:
        if role not in row['roles'] or mode not in row['modes']:
            continue
        if row['profiles'] and (not cap or row['profiles'].get(cap.get('id')) != digest(cap)):
            continue
        if not row['always'] and not (folded & {t.casefold() for t in row['tags']}):
            continue
        card = {k: deepcopy(row[k]) for k in ('id', 'title', 'instruction', 'check', 'native_fields', 'sources', 'scope')}
        card['reading'] = read_section(root, row['reading'])
        cards.append(card)
    source_ids = {s for card in cards for s in card['sources']}
    result = {'policy': POLICY, 'catalog_sha256': digest(data),
              'runtime_sha256': sha256(local_path(root, 'scripts/community_knowledge.py').read_bytes()).hexdigest(),
              'role': role, 'mode': mode, 'tags': sorted(tags), 'target': cap.get('id') if cap else None,
              'capability_sha256': digest(cap) if cap else None, 'cards': cards,
              'sources': [deepcopy(s) for s in data['sources'] if s['id'] in source_ids],
              'evidence_boundary': 'Local note bytes read; external URLs are provenance, not executed code. Host adoption needs craft_review; live quality NOT_RUN.',
              'execution': {'submitted': False, 'runnable': False, 'media_quality': 'NOT_RUN'}}
    result['plan_sha256'] = digest(result)
    return result


def verify(value, cap=None, root=ROOT):
    if not isinstance(value, dict) or value != plan(cap, value.get('mode'), role=value.get('role'), tags=value.get('tags', ()), root=root):
        raise ValueError('Community selection, scope or source bytes changed')
    return True


def audit(root=ROOT):
    """Exercise a witness for EVERY admitted card, not only count nonempty paths."""
    data = catalog(root)
    caps = json.loads((Path(root)/'registries/capabilities.json').read_text())['profiles']
    by_id = {c['id']: c for c in caps}
    witnesses = []
    for row in data['cards']:
        targets = [by_id[t] for t in row['profiles']] or [None]
        for role in row['roles']:
            for mode in row['modes']:
                for cap in targets:
                    selected = plan(cap, mode, role=role, tags=row['tags'][:1], root=root)
                    actual = next((c for c in selected['cards'] if c['id'] == row['id']), None)
                    if actual is None or not actual['reading']['text']:
                        raise ValueError('Unreachable community card: ' + row['id'])
                    witnesses.append({'card': row['id'], 'role': role, 'mode': mode,
                                      'target': cap.get('id') if cap else None,
                                      'read_sha256': actual['reading']['section_sha256']})
    return {'status': 'PASS', 'cards': len(data['cards']), 'sources': len(data['sources']),
            'deferred_sources': [s['id'] for s in data['sources'] if s['read_status'] != 'READ'],
            'route_witnesses': witnesses, 'boundary': 'Selection and local reading only; no external model execution.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'plan', 'audit'])
    parser.add_argument('--target'); parser.add_argument('--role', default='avir', choices=ROLES)
    parser.add_argument('--mode', default='text', choices=MODES)
    parser.add_argument('--tag', action='append', default=[], dest='tags')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            data = catalog()
            result = {'policy': POLICY, 'cards': [{k: r[k] for k in ('id', 'title', 'roles', 'modes', 'tags', 'scope')} for r in data['cards']],
                      'deferred_sources': [s for s in data['sources'] if s['read_status'] != 'READ']}
        elif args.command == 'audit': result = audit()
        else:
            from vpc_core import profile
            result = plan(profile(args.target) if args.target else None, args.mode, role=args.role, tags=args.tags)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as error:
        print(json.dumps({'status': 'BLOCKED', 'error': str(error)}, ensure_ascii=False), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
