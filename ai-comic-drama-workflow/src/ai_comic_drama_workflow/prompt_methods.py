"""Use the locked compiler's method catalogue inside existing craft task receipts.

No new project state/files or user approval stage. Old module archives and tasks
without this optional feature retain their previous contract.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from .v5_modules import read
from .v5_adapters import digest


def _load(kernel):
    root = kernel.modules('video-prompt-compiler')
    path = root / 'scripts/prompt_techniques.py'
    if not path.is_file():
        return root, None  # Explicitly locked older module: do not silently migrate.
    spec = importlib.util.spec_from_file_location('locked_prompt_methods_' + digest(str(root))[:16], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return root, module


def _capability(root, kernel):
    target = kernel.project.get('target')
    if target is None:
        return None
    caps = read(root / 'registries/capabilities.json')['profiles']
    cap = next((row for row in caps if row['id'] == target), None)
    if cap is None:
        raise ValueError('Prompt method target is absent from locked capability registry')
    return cap


def attach(kernel, kind, craft, features=None):
    root, module = _load(kernel)
    if module is None:
        return
    selected = module.plan(_capability(root, kernel), kernel.project.get('mode', 'text'),
                           role=kind, tags=(features or {}).get('tags', []), root=root)
    craft['prompt_methods'] = selected
    # Consumer stages already review all inherited native evidence. Only creators
    # add new requirements, so rules do not multiply at every projection stage.
    if kind in ('screenplay', 'director', 'art', 'storyboard'):
        for row in selected['methods'] + selected['templates']:
            craft['rules'].append({'id': kind + ':prompt:' + row['id'],
                                   'instruction': row['instruction'], 'check': row['check'],
                                   'source': {'module': 'video-prompt-compiler',
                                              'path': 'registries/prompt-techniques.json',
                                              'catalog_sha256': selected['catalog_sha256'],
                                              'upstream': row['source']}})


    # Source notes are actually read by the locked runtime and embedded in the task.
    # Consumers owe scoped adoption/NA too; they cannot redesign locked upstream work.
    for row in selected.get('community', {}).get('cards', []):
        craft['rules'].append({'id': kind + ':community:' + row['id'],
            'instruction': row['instruction'], 'check': row['check'],
            'source': {'module': 'video-prompt-compiler',
                       'path': row['reading']['path'], 'section': row['reading']['section'],
                       'sha256': row['reading']['file_sha256'],
                       'section_sha256': row['reading']['section_sha256'],
                       'upstream': row['sources']}})


def check(kernel, craft):
    selected = craft.get('prompt_methods')
    if selected is None:
        return  # Legacy frozen task; no retrospective new requirement.
    root, module = _load(kernel)
    if module is None:
        raise ValueError('Locked prompt method runtime is missing')
    module.verify_plan(selected, _capability(root, kernel), root)
    if selected['role'] in ('screenplay', 'director', 'art', 'storyboard'):
        expected = {selected['role'] + ':prompt:' + r['id']: r
                    for r in selected['methods'] + selected['templates']}
        actual = {r['id']: r for r in craft.get('rules', []) if ':prompt:' in r['id']}
        if set(actual) != set(expected):
            raise ValueError('Selected prompt methods are absent from required craft evidence')
        for key, row in expected.items():
            if any(actual[key].get(field) != row[field] for field in ('instruction', 'check')):
                raise ValueError('Prompt method content changed since selection')


    expected_community = {selected['role'] + ':community:' + r['id']: r
                          for r in selected.get('community', {}).get('cards', [])}
    community_rows = [r for r in craft.get('rules', []) if ':community:' in r['id']]
    actual = {r['id']: r for r in community_rows}
    if len(actual) != len(community_rows) or set(actual) != set(expected_community):
        raise ValueError('Community rules missing or duplicated in required evidence')
    for key, row in expected_community.items():
        source = {'module': 'video-prompt-compiler', 'path': row['reading']['path'],
                  'section': row['reading']['section'], 'sha256': row['reading']['file_sha256'],
                  'section_sha256': row['reading']['section_sha256'], 'upstream': row['sources']}
        if any(actual[key].get(f) != row[f] for f in ('instruction', 'check')) or actual[key].get('source') != source:
            raise ValueError('Community instruction or read evidence changed')


def compiler_template_ids(kernel):
    """Only adopted templates from the accepted storyboard reach compilation.

    Reads existing RoleResult proof; no reselection from late-stage prose. The
    caller fingerprints this selection and compares it when importing packages.
    """
    from . import craft_runtime
    if not craft_runtime.enabled(kernel):
        return None
    record = kernel.state['artifacts'].get('storyboard')
    if not record or not record.get('craft_proof'):
        return None
    result = craft_runtime.proof_result(kernel, record)
    task = read(kernel.path('runtime/tasks/' + result['task_id'] + '.json'))
    craft = task.get('craft') or {}
    selected = craft.get('prompt_methods')
    if not selected:
        return None
    check(kernel, craft)
    applied = {r['id'] for r in result['craft_review']['applications'] if r['status'] == 'applied'}
    return sorted(r['id'] for r in selected['templates']
                  if 'storyboard:prompt:' + r['id'] in applied) or None


def compiler_args(kernel):
    return [part for template in compiler_template_ids(kernel) or [] for part in ('--template', template)]
