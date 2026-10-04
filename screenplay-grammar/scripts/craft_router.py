#!/usr/bin/env python3
"""Source-backed craft selection, not a semantic model or a film-quality predictor.

The host supplies semantic features with source evidence. Lexical bootstrapping is
explicitly labelled. This file is synchronized into independently installable Skills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

POLICY = 'craft-routing/1.0'
ROLES = {'screenplay': 'screenplay-grammar', 'director': 'director-grammar',
         'art': 'production-design-grammar', 'storyboard': 'storyboard-grammar'}
DEFAULTS = {'screenplay': 'character_causal', 'director': 'observational',
            'art': 'contemporary_observation', 'storyboard': 'transparent'}
# Retrieval vocabulary, not claims about an artist. Semantic interpretation belongs to the host.
CONCEPTS = {
    '悬疑': ('mystery', 'suspense', 'thriller', '密室', '线索', '隐瞒', '失踪', '真相'),
    '调查': ('investigation', '侦查', '取证', '搜证'),
    '群像': ('ensemble', '多人关系', '各自的秘密', '五名陌生人'),
    '关系': ('relationship', 'family', '亲情', '父女', '母子', '重逢'),
    '克制': ('restrained', 'quiet', '沉默', '不说话', '安静'),
    '记忆': ('memory', 'flashback', '回忆', '往事'),
    '动作': ('action', 'chase', 'fight', '追逐', '打斗'),
    '教学': ('tutorial', 'instruction', 'teaching', '演示步骤', '步法', '滑步'),
    '产品': ('product', '商品', '产品演示'),
    '观察': ('documentary', 'observation', '纪录', '日常'),
    '喜剧': ('comedy', 'comic', '笑点', '反讽'),
    '科幻': ('sci-fi', 'science fiction', 'spaceship', '宇宙飞船', '太空站'),
    '仙侠': ('xianxia', '仙宫', '云顶', '神话'),
    '古风': ('historical', 'period drama', '古代', '武侠'),
    '色彩': ('color', 'colour', '冷暖', '冷转暖', '色温', '配色'),
    '转焦': ('rack focus', 'focus shift', '焦点转移', '焦点从', '虚实'),
    '转场': ('transition', 'match cut', '声桥', '剪辑', '切镜'),
    '仪式': ('ritual', '礼制', '祭祀'),
    '动画': ('animation', 'animated', '卡通'),
    '服装': ('costume', 'wardrobe', '衣装', '服化道'),
}
NEGATION = re.compile(r'(?:不要|不得|禁止|避免|不采用|不使用|without\b|not\b|no\b)', re.I)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def read(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('Duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def pointer(value, path):
    if not isinstance(path, str) or not path.startswith('/') or path == '/':
        raise ValueError('Evidence needs a non-root JSON pointer')
    for part in path.split('/')[1:]:
        if re.search(r'~(?![01])', part):
            raise ValueError('Invalid JSON pointer escape')
        key = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', key):
                raise ValueError('Invalid array pointer')
            value = value[int(key)]
        else:
            value = value[key]
    return value


def source(root, relative, locator=''):
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Craft source escapes the selected Skill')
    raw = path.read_bytes()
    return {'path': relative, 'locator': locator, 'sha256': hashlib.sha256(raw).hexdigest()}


def _strings(value, label):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(label + ' must be a list of nonempty strings')
    return value


def features(value):
    if not isinstance(value, dict):
        raise ValueError('Craft analysis must be an object')
    allowed = {'tags', 'goal', 'requested', 'forbidden_profiles', 'forbidden_techniques',
               'task', 'world_mode', 'medium'}
    if set(value) - allowed:
        raise ValueError('Unknown craft feature: ' + sorted(set(value) - allowed)[0])
    for key in ('tags', 'forbidden_profiles', 'forbidden_techniques'):
        _strings(value.get(key, []), key)
    for key in allowed - {'tags', 'forbidden_profiles', 'forbidden_techniques'}:
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError('Invalid craft feature: ' + key)
    enums = {'task': ('narrative', 'observation', 'demonstration', 'performance', 'product'),
             'world_mode': ('historical', 'fantasy', 'contemporary', 'future', 'product'),
             'medium': ('live_action', '3d', '2d', 'mixed')}
    for key, choices in enums.items():
        if key in value and value[key] not in choices:
            raise ValueError('Unknown craft ' + key)
    return value


def lexical(query):
    positive, negative = [], []
    for clause in re.split(r'[，。；;,.!！?？\n]|\bbut\b|但是|但要', query.casefold()):
        found = NEGATION.search(clause)
        if found:
            positive.append(clause[:found.start()])
            negative.append(clause[found.end():])
        else:
            positive.append(clause)
    pos, neg = ' '.join(positive), ' '.join(negative)
    tags = {tag for tag, terms in CONCEPTS.items() if any(term in pos for term in (tag, *terms))}
    if '动作' in tags and not re.search(r'追逐|打斗|追车|武打|动作片|动作戏|action scene|chase|fight', pos):
        tags.discard('动作')  # a small gesture is not an action-film genre
    denied = {tag for tag, terms in CONCEPTS.items() if any(term in neg for term in (tag, *terms))}
    return pos, neg, tags - denied, denied


def catalog(root, role):
    """Read locally in Python; return only selected records to the model context."""
    root = Path(root)
    if role not in ROLES:
        raise ValueError('Unknown professional role: ' + role)
    result = []
    if role in ('director', 'screenplay'):
        styles = read(root / 'registries/styles.json')['styles']
        people_file = 'registries/directors.json' if role == 'director' else 'registries/writers.json'
        people_key = 'directors' if role == 'director' else 'writers'
        people = read(root / people_file)[people_key]
        techniques = {t['id']: t for t in read(root / 'registries/techniques.json')['techniques']}
        for i, style in enumerate(styles):
            rules = []
            for tid in style['techniques']:
                technique = techniques[tid]
                if role == 'director':
                    instruction = technique['parameters'] + '；' + technique['invariants']
                    check = technique['acceptance']
                    src = source(root, 'registries/techniques.json', '/techniques/' + str(list(techniques).index(tid)))
                else:
                    source(root, technique['path'])  # validate containment before opening a referenced card
                    text = (root / technique['path']).read_text(encoding='utf-8')
                    def line(prefix):
                        return next(s.split('：', 1)[1] for s in text.splitlines() if s.startswith(prefix + '：'))
                    instruction, check = line('操作'), line('验收')
                    src = source(root, technique['path'])
                rules.append({'id': tid, 'instruction': instruction, 'check': check, 'source': src})
            practitioners = []
            for n, person in enumerate(people):
                if person.get('style_id', person.get('profile')) != style['id']:
                    continue
                practitioners.append({'name': person['name'],
                    'alias': person.get('alias', person.get('english_name', '')),
                    'method': person.get('method', person.get('method_analysis', '')),
                    'source': source(root, people_file, '/' + people_key + '/' + str(n)),
                    'attribution': 'project_interpretation_not_independently_verified'})
            result.append({**style, 'rules': rules, 'practitioners': practitioners,
                           'source': source(root, 'registries/styles.json', '/styles/' + str(i))})
    elif role == 'art':
        people = read(root / 'registries/research-index.json')['entries']
        for i, style in enumerate(read(root / 'registries/styles.json')['styles']):
            src = source(root, 'registries/styles.json', '/styles/' + str(i))
            rules = [{'id': 'art_' + str(n), 'instruction': instruction,
                      'check': '；'.join(style['acceptance']), 'source': src}
                     for n, instruction in enumerate(style['rules'])]
            practitioners = [{'name': person['name'], 'alias': '', 'method': person['study_question'],
                              'source': source(root, 'registries/research-index.json', '/entries/' + str(n)),
                              'attribution': 'project_interpretation_not_independently_verified'}
                             for n, person in enumerate(people) if person['grammar_lookup'] == style['id']]
            result.append({**style, 'rules': rules, 'practitioners': practitioners, 'source': src})
    else:
        for i, style in enumerate(read(root / 'registries/style-index.json')['styles']):
            src = source(root, style['file'])
            card = read(root / style['file'])
            rules = [{'id': 'board_' + str(n), 'instruction': instruction,
                      'check': '；'.join(card['acceptance']), 'source': src}
                     for n, instruction in enumerate(card['rules'])]
            # The existing research table is a case-study index, not an artist API.
            result.append({**style, 'rules': rules, 'practitioners': [], 'source': src})
    return result


def route(root, role, query, analysis=None, *, scope=None, inherited=None):
    if not isinstance(query, str) or not query.strip():
        raise ValueError('Craft routing requires source content')
    analysis = features(analysis or {})
    cards = catalog(root, role)
    pos, neg, lexical_tags, denied = lexical(query)
    # Host semantic tags supersede lexical bootstrapping, except local camera overlays.
    tags = set(analysis['tags']) | (lexical_tags & {'转焦', '色彩', '转场'}) if analysis.get('tags') else lexical_tags
    if not analysis.get('tags'):
        tags -= denied
    request = analysis.get('requested')
    unknown = set(analysis.get('forbidden_profiles', [])) - {c['id'] for c in cards}
    techniques = {r['id'] for c in cards for r in c['rules']}
    unknown |= set(analysis.get('forbidden_techniques', [])) - techniques
    if unknown:
        raise ValueError('Unknown forbidden craft reference: ' + sorted(unknown)[0])
    named = []
    for card in cards:
        for person in card['practitioners']:
            aliases = [s.casefold() for s in (person['name'], person['alias']) if s]
            if any(a in neg for a in aliases):
                continue
            if request and request.casefold() in aliases:
                named.append((card['id'], person))
            elif not request and not analysis and any(re.search(r'(?:参考|借鉴|采用|风格|inspired by)\s*' + re.escape(a), pos) or pos.strip() == a for a in aliases):
                named.append((card['id'], person))
    if len({c for c, _ in named}) > 1:
        raise ValueError('Conflicting named craft references require a dimension-specific decision')
    if named:
        request = named[0][0]
    if request and request not in {c['id'] for c in cards}:
        raise ValueError('Unknown requested craft profile or practitioner: ' + request)
    task = analysis.get('task') or ('demonstration' if '教学' in tags else 'product' if '产品' in tags else None)
    ranked, rejected = [], []
    for card in cards:
        reasons = []
        if card['id'] in analysis.get('forbidden_profiles', []):
            reasons.append('forbidden profile')
        if not analysis.get('tags') and (card['id'].casefold() in neg or any(t.casefold() in neg for t in card.get('tags', []))):
            reasons.append('negative preference')
        if set(analysis.get('forbidden_techniques', [])) & {r['id'] for r in card['rules']}:
            reasons.append('forbidden technique')
        if role == 'director' and task and task not in card['tasks']:
            reasons.append('task mismatch')
        if role == 'screenplay' and task in ('demonstration', 'product', 'observation') and card['id'] != 'non_dramatic':
            reasons.append('non-dramatic task')
        if role == 'art':
            if analysis.get('world_mode') and analysis['world_mode'] not in card['world_modes']:
                reasons.append('world mismatch')
            if analysis.get('medium') and analysis['medium'] not in card['media']:
                reasons.append('medium mismatch')
        if reasons:
            rejected.append({'id': card['id'], 'reasons': reasons})
            continue
        matches = sorted(t for t in card.get('tags', []) if t in tags or (not analysis and t not in CONCEPTS and t.casefold() in pos))
        # Narrative objectives outrank cosmetic vocabulary; this is retrieval, not taste scoring.
        weights = {'悬疑': 9, '调查': 8, '教学': 12, '产品': 12, '动作': 8,
                   '关系': 7, '喜剧': 8, '群像': 7, '仙侠': 7, '古风': 6, '仪式': 6,
                   '记忆': 3, '色彩': 1}
        score = sum(weights.get(t, 3) for t in matches)
        if role == 'director' and (task, card['id']) in (('product','product_evidence'), ('demonstration','movement_clarity'), ('observation','observational')):
            score += 20
        ranked.append((score, card['id'] != DEFAULTS[role], card['id'], matches, card))
    if request:
        ranked = [row for row in ranked if row[2] == request]
    if not ranked:
        raise ValueError('No compatible craft profile; do not silently downgrade')
    ranked.sort(key=lambda row: (-row[0], row[1], row[2]))
    score, _, _, matches, card = ranked[0]
    people = [p for p in card['practitioners'] if not any(s.casefold() in neg for s in (p['name'], p['alias']) if s)]
    def method_match(person):
        method = person['method'].casefold()
        bigrams = {method[i:i+2] for i in range(len(method)-1) if all('\u4e00' <= c <= '\u9fff' for c in method[i:i+2])}
        return sum(t in method for t in tags) * 3 + sum(b in pos for b in bigrams)
    people.sort(key=lambda p: (-method_match(p), p['name']))
    person = next((p for cid, p in named if cid == card['id']), people[0] if people else None)
    rules = list(card['rules'][:3])
    if person:
        rules.append({'id': 'practitioner_method',
                      'instruction': '将项目归纳的“' + person['method'] + '”落实为当前范围的可见行为、信息或设计，不以姓名代替内容。',
                      'check': '指出本场/本镜的具体实现和观众可感知的结果；不得只复述人名或方法标题。',
                      'source': person['source']})
    # Local craft overlays change a dimension, not the project's primary style.
    if role == 'director':
        extra = [('转焦', 'rack_focus'), ('色彩', 'color_structure'), ('转场', 'sound_bridge')]
        all_rules = {r['id']: r for c in cards for r in c['rules']}
        for tag, rid in extra:
            if tag in tags and rid in all_rules and rid not in analysis.get('forbidden_techniques', []) and rid not in {r['id'] for r in rules}:
                rules.append(all_rules[rid])
            if len(rules) >= 6:
                break
    if role == 'art':
        rules.extend([
            {'id': 'costume_makeup', 'instruction': '服装、发妆服务角色身份、动作和表情可读性；跨镜保留衣着、发型与磨损锚点。',
             'check': '逐镜核对身份、衣装覆盖、面部可读性；无人场景说明不适用。',
             'source': source(root, 'references/world-and-assets.md')},
            {'id': 'prop_continuity', 'instruction': '道具用途、尺寸、持握归属和状态改变有事件来源，不因换镜头重置。',
             'check': '核对道具初态、事件、末态和下一镜入口；无道具时说明不适用。',
             'source': source(root, 'references/world-and-assets.md')}])
    for rule in rules:
        rule['id'] = role + ':' + rule['id']
    sources = [card['source'], *[r['source'] for r in rules]]
    if person:
        sources.append(person['source'])
    plan = {'policy': POLICY, 'role': role, 'scope': scope or {}, 'primary': card['id'],
            'practitioner': person, 'rules': rules, 'sources': sources,
            'goal': analysis.get('goal', '宿主须依据原文解释本次方法如何服务观众体验。'),
            'selection_basis': 'host_semantic_features+deterministic_retrieval' if analysis else 'lexical_bootstrap_requires_host_review',
            'matched_tags': matches, 'fallback': not bool(score or request), 'explicit': bool(request),
            'alternatives': [{'id': row[2], 'matched_tags': row[3]} for row in ranked[1:3]],
            'rejected': rejected, 'input_sha256': digest({'query': query, 'analysis': analysis}),
            'inherited': inherited or [], 'status': 'SELECTED_NOT_APPLIED', 'media_quality': 'NOT_RUN'}
    plan['plan_sha256'] = digest(plan)
    return plan


def expand_applications(review):
    """Expand explicitly enumerated equal evidence, without guessing applicability."""
    if not isinstance(review, dict):
        raise ValueError('Craft review must be an object')
    if 'groups' not in review:
        return review.get('applications')
    if 'applications' in review or not isinstance(review['groups'], list):
        raise ValueError('Use applications or groups, not both')
    rows = []
    for group in review['groups']:
        if not isinstance(group, dict):
            raise ValueError('Craft evidence group must be an object')
        ids = group.get('rule_ids')
        if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i or '*' in i for i in ids)
                or len(ids) != len(set(ids)) or 'id' in group):
            raise ValueError('Group needs explicit unique rule_ids, never a wildcard')
        rows.extend({**{k: v for k, v in group.items() if k != 'rule_ids'}, 'id': identifier} for identifier in ids)
    return rows


def bind_review(plan, review, artifact):
    """Compute bindings of submitted content, not proof the host saw or understood it.

    Authors provide every quote/finding/status. Existing supplied hashes must match;
    no replacement of stale hashes and no inference of artistic or visual quality.
    """
    from copy import deepcopy
    result = deepcopy(review)
    if not isinstance(result, dict):
        raise ValueError('Craft review must be an object')
    if result.get('plan_sha256', plan['plan_sha256']) != plan['plan_sha256']:
        raise ValueError('Stale craft plan binding')
    result['plan_sha256'] = plan['plan_sha256']
    rules={r['id']:r for r in plan.get('rules',[])+plan.get('inherited',[])}
    if isinstance(result.get('groups'),list):
        for group in result['groups']:
            if not isinstance(group,dict) or not isinstance(group.get('rule_ids'),list):
                raise ValueError('Craft group must enumerate rule_ids')
            identifiers=group['rule_ids']
            if any(not isinstance(i,str) for i in identifiers):
                raise ValueError('Craft rule_ids must be strings')
            scopes={digest(rules[i].get('scope',plan.get('scope',{}))) for i in identifiers if i in rules}
            if len(scopes)>1:
                raise ValueError('Different rule scopes require separate evidence groups')
    rows = expand_applications(result)
    if not isinstance(rows, list):
        raise ValueError('Craft applications or groups are required')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Craft application must be an object')
        if row.get('status') == 'applied':
            try:
                actual = pointer(artifact, row.get('pointer'))
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise ValueError('Craft evidence pointer does not resolve') from error
            expected = digest(actual)
            if row.get('value_sha256', expected) != expected:
                raise ValueError('Craft evidence content hash changed')
            row['value_sha256'] = expected
    result.pop('groups', None)
    result['applications'] = rows
    validate_review(plan, result, artifact)
    return result


def validate_review(plan, review, artifact):
    """Verify evidence bindings, never label semantic/visual quality as proven."""
    if not isinstance(review, dict) or review.get('plan_sha256') != plan['plan_sha256']:
        raise ValueError('Missing or stale craft_review')
    if not isinstance(review.get('rationale'), str) or len(review['rationale'].strip()) < 12:
        raise ValueError('Craft review needs a content-specific rationale')
    if digest({k:v for k,v in plan.items() if k != 'plan_sha256'}) != plan['plan_sha256']:
        raise ValueError('Craft plan integrity changed')
    if review.get('semantic_review') is not True:
        raise ValueError('Host semantic craft review is required')
    rows = expand_applications(review)
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Craft applications must be objects')
    required = {r['id'] for r in plan.get('rules', [])}
    required.update(r['id'] for r in plan.get('inherited', []))
    ids = [r.get('id') for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != required:
        raise ValueError('Craft applications must cover every selected and inherited rule exactly once')
    for row in rows:
        if row.get('status') not in ('applied', 'not_applicable'):
            raise ValueError('Unresolved craft rule cannot be accepted')
        if not isinstance(row.get('reason'), str) or len(row['reason'].strip()) < 8:
            raise ValueError('Craft application needs a concrete explanation')
        if not isinstance(row.get('check'), str) or len(row['check'].strip()) < 8:
            raise ValueError('Craft application needs an observable check')
        if row['status'] == 'not_applicable':
            if not isinstance(row.get('condition'), str) or len(row['condition'].strip()) < 8:
                raise ValueError('Not-applicable craft needs an explicit scope condition')
            continue
        try:
            actual = pointer(artifact, row.get('pointer'))
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError('Craft evidence pointer does not resolve') from error
        if not isinstance(actual, str) or not actual.strip():
            raise ValueError('Craft evidence must point to an actual content string, not a container')
        if row.get('value_sha256') != digest(actual):
            raise ValueError('Craft evidence content hash changed')
        if not isinstance(row.get('quote'), str) or len(row['quote'].strip()) < 4 or row['quote'] not in actual:
            raise ValueError('Craft evidence quote is absent from output')
        person = (plan.get('practitioner') or {}).get('name', '')
        if person and row['quote'].strip() in (person, '参考' + person, person + '风格'):
            raise ValueError('A practitioner name is not implementation evidence')
        if re.search(r'/(?:sources|review|checks|craft_review|style|tags|rationale|style_request|style_id|locked_style|primary|profile)(?:/|$)', row['pointer']):
            raise ValueError('Craft evidence must reference implementation, not labels or review metadata')
    own_ids = {r['id'] for r in plan.get('rules', []) if not r.get('scope')}
    if own_ids and not any(r['id'] in own_ids and r['status'] == 'applied' for r in rows):
        raise ValueError('All craft primary rules are inapplicable; return to routing')
    if required and all(r['status'] == 'not_applicable' for r in rows):
        raise ValueError('All craft rules are inapplicable; return to routing instead of ceremonial adoption')
    return {'status': 'EVIDENCE_BOUND', 'semantic_assessment': 'HOST_DECLARED', 'media_quality': 'NOT_RUN'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', nargs='?', default='')
    parser.add_argument('--role', choices=ROLES)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--analysis', type=Path, help='Host-authored semantic features; never user-required JSON')
    parser.add_argument('--plan', type=Path, help='Frozen standalone route plan for evidence binding')
    parser.add_argument('--review', type=Path, help='Host-authored applications or explicit evidence groups')
    parser.add_argument('--artifact', type=Path, help='Native content reviewed by the host')
    args = parser.parse_args(argv)
    role = args.role or next((role for role, name in ROLES.items() if args.root.name == name), None)
    try:
        if args.review or args.artifact or args.plan:
            if not (args.review and args.artifact and args.plan):
                raise ValueError('Evidence binding requires --plan, --review and --artifact')
            plan = read(args.plan)
            if not isinstance(plan,dict):
                raise ValueError('Standalone plan must be an object')
            # Check immutable plan and current source bytes before binding.
            for source in plan.get('sources', []):
                if not isinstance(source,dict):
                    raise ValueError('Standalone source must be an object')
                relative = source.get('path')
                path = (args.root / relative).resolve() if isinstance(relative,str) else None
                if path is None or not path.is_relative_to(args.root.resolve()) or not path.is_file():
                    raise ValueError('Standalone craft source path is missing or escapes the skill')
                if source.get('sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
                    raise ValueError('Standalone craft source changed')
            result = bind_review(plan, read(args.review), read(args.artifact))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if role is None:
            raise ValueError('Use the responsible native Skill root and role; consumers inherit upstream decisions')
        plan = route(args.root, role, args.query, read(args.analysis) if args.analysis else None)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'BLOCKED', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
