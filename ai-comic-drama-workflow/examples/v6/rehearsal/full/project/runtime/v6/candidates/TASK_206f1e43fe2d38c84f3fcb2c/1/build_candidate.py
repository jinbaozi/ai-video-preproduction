import json
from pathlib import Path


ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_206f1e43fe2d38c84f3fcb2c/1/script-ir.json'
CANON = ROOT / 'artifacts/canon/f3c90f6c20dd218a854fa67548b296692d71fd08bc62e2ca5076a27667809b18/native/0cc4aebffda6a714_canon.json'
SOURCE = ROOT / 'sources/SRC_69a71adcfaca/source.txt'
REFS = ['SRC_69a71adcfaca', 'CANON_V12']


def check(check_id, method, predicate, assertions, evidence):
    return {
        'id': check_id,
        'method': method,
        'predicate': predicate,
        'assertions': assertions,
        'blocking': True,
        'evidence_required': evidence,
    }


def clause(clause_id, requirement, paths, check_ids):
    return {
        'id': clause_id,
        'requirement': requirement,
        'source_refs': REFS,
        'priority': 'hard',
        'owner': 'screenplay',
        'change_policy': 'preserve',
        'paths': paths,
        'realization': 'action',
        'steps': ['agent_write', 'static_validate', 'semantic_review', 'text_compile', 'director_realize'],
        'check_ids': check_ids,
    }


def event(event_id, description, block_id, causes, updates=None, preconditions=None):
    return {
        'id': event_id,
        'description': description,
        'scene_id': 'SCENE_HANDOFF',
        'block_ids': [block_id],
        'source_refs': REFS,
        'causes': causes,
        'preconditions': preconditions or [],
        'updates': updates or [],
    }


def block(block_id, text):
    return {
        'id': block_id,
        'kind': 'action',
        'speaker': None,
        'text': text,
        'source_refs': REFS,
    }


project = json.loads(OUT.read_text())
canon = json.loads(CANON.read_text())
source_text = SOURCE.read_text().strip()
assert canon['content'] == source_text
assert [x['id'] for x in canon['event_order']] == ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW']
assert [x['id'] for x in canon['source_requirements']] == ['REQ_RAIN_NIGHT', 'REQ_SAME_UNOPENED_LETTER', 'REQ_EVENT_ORDER']

project['canon'] = {
    'facts': [],
    'proposals': [],
    'ref': {
        'uri': str(CANON),
        'sha256': 'ec1a717dc3c8059122916da8f3207437393d9a0cbc4a00cb342dd1b46a94a7a5',
    },
}
project['sources'] = [
    {
        'id': 'SRC_69a71adcfaca',
        'kind': 'user',
        'uri': str(SOURCE),
        'sha256': '69a71adcfaca63b093b3e799edb74b3be60505c26e02b32b1603f5de06bb1054',
        'excerpt': source_text,
        'locator': '原文全文',
        'verification': 'read',
    },
    {
        'id': 'CANON_V12',
        'kind': 'canon',
        'uri': str(CANON),
        'sha256': 'ec1a717dc3c8059122916da8f3207437393d9a0cbc4a00cb342dd1b46a94a7a5',
        'excerpt': canon['content'],
        'locator': 'content、source_requirements、event_order、entities',
        'verification': 'read',
    },
]
project['source_refs'] = REFS
project['characters'] = [
    {'id': 'CHAR_JIA', 'name': '甲', 'goal': '把未拆的信交给乙', 'voice': '本场没有对白，语气未指定', 'source_refs': REFS},
    {'id': 'CHAR_YI', 'name': '乙', 'goal': '接信并确认封口完整，然后将同一封信收进背包', 'voice': '本场没有对白，语气未指定', 'source_refs': REFS},
]
project['propositions'] = [
    {'id': 'SEAL_INTACT', 'statement': '这封信的封口完整', 'truth': 'true', 'source_refs': REFS},
]
know_seal = {'actor': 'CHAR_YI', 'proposition': 'SEAL_INTACT', 'state': 'knows', 'source_refs': REFS}
project['narrative'] = {
    'premise': '雨夜，甲交给乙一封未拆的信；乙确认封口完整后收进背包。',
    'events': [
        event('EVT_HANDOFF', '甲把一封未拆的信交给乙。', 'B_HANDOFF', []),
        event('EVT_SEAL_CHECK', '乙检查同一封信，确认封口完整。', 'B_SEAL_CHECK', ['EVT_HANDOFF'], updates=[know_seal]),
        event('EVT_STOW', '确认后，乙把同一封信收进背包。', 'B_STOW', ['EVT_SEAL_CHECK'], preconditions=[know_seal]),
    ],
    'initial_knowledge': [],
    'promises': [],
    'reveal_order': ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW'],
    'ending': '乙将那封封口完整、仍未拆开的信收进背包。',
}
project['scenes'] = [
    {
        'id': 'SCENE_HANDOFF',
        'heading': '地点未指定·雨夜',
        'purpose': '按已知顺序呈现交信、验封与收存',
        'source_refs': REFS,
        'blocks': [
            block('B_HANDOFF', '雨夜。甲把一封未拆的信交给乙。'),
            block('B_SEAL_CHECK', '乙接过这封信，查看封口，确认封口完整；信仍未拆开。'),
            block('B_STOW', '确认后，乙将同一封信收进背包。'),
        ],
    },
]
project['contract'] = {
    'deliverables': ['screenplay'],
    'scope': '依据来源和当前 Canon 整理单场短剧本，只呈现已给定的事件及顺序。',
    'checks': [
        check('RAIN_STATIC', 'static', '场景与动作都明确为雨夜。', [
            {'op': 'contains', 'path': '/scenes/0/heading', 'value': '雨夜'},
            {'op': 'contains', 'path': '/scenes/0/blocks/0/text', 'value': '雨夜'},
        ], 'ScriptIR JSON Pointer 断言'),
        check('RAIN_SEMANTIC', 'semantic', '是否保留雨夜，且未擅定地点及室内外？', [], '当前执行者对 Canon 与全文的语义核对'),
        check('LETTER_STATIC', 'static', '三段动作都指向同一封未拆的信。', [
            {'op': 'contains', 'path': '/scenes/0/blocks/0/text', 'value': '一封未拆的信'},
            {'op': 'contains', 'path': '/scenes/0/blocks/1/text', 'value': '这封信'},
            {'op': 'contains', 'path': '/scenes/0/blocks/1/text', 'value': '信仍未拆开'},
            {'op': 'contains', 'path': '/scenes/0/blocks/2/text', 'value': '同一封信'},
        ], 'ScriptIR JSON Pointer 断言'),
        check('LETTER_SEMANTIC', 'semantic', '交接、验封和收存是否同一封信，过程中是否保持未拆？', [], '当前执行者对 Canon 与全文的语义核对'),
        check('ORDER_STATIC', 'static', '事件与场景动作顺序一致。', [
            {'op': 'equals', 'path': '/narrative/reveal_order', 'value': ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW']},
            {'op': 'equals', 'path': '/scenes/0/blocks/0/id', 'value': 'B_HANDOFF'},
            {'op': 'equals', 'path': '/scenes/0/blocks/1/id', 'value': 'B_SEAL_CHECK'},
            {'op': 'equals', 'path': '/scenes/0/blocks/2/id', 'value': 'B_STOW'},
        ], 'ScriptIR JSON Pointer 断言'),
        check('ORDER_SEMANTIC', 'semantic', '是否先交信、再确认封口，最后才收进背包？', [], '当前执行者对 Canon 与全文的语义核对'),
    ],
    'clauses': [
        clause('REQ_RAIN_NIGHT', '保留雨夜。', ['/scenes/0/heading', '/scenes/0/blocks/0/text'], ['RAIN_STATIC', 'RAIN_SEMANTIC']),
        clause('REQ_SAME_UNOPENED_LETTER', '交接、检查和收存的是同一封未拆的信。', ['/scenes/0/blocks/0/text', '/scenes/0/blocks/1/text', '/scenes/0/blocks/2/text'], ['LETTER_STATIC', 'LETTER_SEMANTIC']),
        clause('REQ_EVENT_ORDER', '甲交给乙，乙确认封口完整，之后乙将信收进背包。', ['/narrative/reveal_order', '/scenes/0/blocks'], ['ORDER_STATIC', 'ORDER_SEMANTIC']),
    ],
}
project['rewrite_scope'] = {
    'allow_new_events': False,
    'allowed_paths': ['/scenes', '/narrative', '/characters', '/propositions'],
    'level': 'structure',
    'preserve_paths': [],
}
project['task']['operation'] = 'adapt'
project['status'] = 'READY'
project['open_issues'] = []
project['review'] = {'status': 'NOT_RUN', 'reviewer': None, 'findings': [], 'content_sha256': None}
OUT.write_text(json.dumps(project, ensure_ascii=False, indent=2) + '\n')
