"""Scoped, evidence-labelled prompt methods. No model calls or frozen-IR rewrites.

The catalogue is data, not executable instructions. Templates supply authoring
patterns; the existing native renderer remains the sole prompt projection.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'prompt-techniques/1.0'
ROLES = ('screenplay', 'director', 'art', 'storyboard', 'image-prompt', 'avir', 'compile-review')
SELECTOR_KEYS = ('id', 'version', 'model', 'backend', 'template')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def catalog(root=ROOT):
    data = read(Path(root) / 'registries/prompt-techniques.json')
    if data.get('schema') != POLICY:
        raise ValueError('Unsupported prompt technique catalogue')
    for section in ('methods', 'templates', 'adapters'):
        rows = data.get(section)
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Invalid technique catalogue section: ' + section)
        ids = [r.get('id') for r in rows]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Duplicate or invalid technique identifier')
    return data


def _string_list(value, name):
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(name + ' must be a list of nonempty strings')
    if len(value) != len(set(value)):
        raise ValueError(name + ' must not contain duplicates')
    return list(value)


def select_templates(data, template_ids=None, tags=(), role='avir'):
    """Semantic tags come from existing source-bound host analysis, never raw prose.

    Ambiguous automatic style matches return candidates, not silently chosen looks.
    An explicit choice is validated and retained for replay; it is not an IR edit.
    """
    tags = _string_list(tags, 'tags')
    by_id = {row['id']: row for row in data['templates']}
    candidates = []
    if template_ids is not None:
        ids = _string_list(template_ids, 'template_ids')
        missing = set(ids) - set(by_id)
        if missing:
            raise ValueError('Unknown prompt template: ' + ', '.join(sorted(missing)))
        chosen = [by_id[i] for i in ids]
        basis = 'explicit_template_ids'
    else:
        folded = {t.casefold() for t in tags}
        chosen = [r for r in data['templates'] if role in r['roles'] and
                  (r['id'].casefold() in folded or folded & {t.casefold() for t in r['tags']})]
        basis = 'source_bound_host_tags' if tags else 'generic_methods_only'
    # Looks cannot be blended automatically. Camera/action/task patterns may coexist
    # (e.g. handheld food vlog); the host still owes native adoption/NA evidence.
    looks = [r for r in chosen if r['dimension'] == 'look']
    if len(looks) > 1:
        if template_ids is not None:
            raise ValueError('Conflicting look templates need a scoped upstream decision')
        candidates = [{'id': r['id'], 'reason': 'ambiguous_look_requires_host_decision'} for r in looks]
        chosen = [r for r in chosen if r['dimension'] != 'look']
    if template_ids is None:
        # Progressive disclosure: at most two task patterns in an ordinary task.
        if len(chosen) > 2:
            candidates += [{'id': r['id'], 'reason': 'multiple_patterns_require_scoped_host_selection'} for r in chosen]
            chosen = []
    return deepcopy(chosen), basis, candidates


def plan(cap=None, mode='text', *, role='avir', tags=(), template_ids=None, root=ROOT):
    if role not in ROLES:
        raise ValueError('Unknown prompt technique role: ' + str(role))
    if mode not in ('text', 'keyframe', 'reference', 'edit', 'extend'):
        raise ValueError('Unknown prompt technique mode: ' + str(mode))
    data = catalog(root)
    templates, basis, candidates = select_templates(data, template_ids, tags, role)
    exact = next((r for r in data['adapters'] if cap and all(
        cap.get(k) == r['selector'][k] for k in SELECTOR_KEYS) and mode in r['modes']), None)
    # Unknown/changed profiles retain neutral authoring methods, not a near-name adapter.
    adapter = deepcopy(exact)
    output = {'policy': POLICY, 'catalog_sha256': digest(data),
              'runtime_sha256': sha256((Path(root)/'scripts/prompt_techniques.py').read_bytes()).hexdigest(),
              'source': data['source'], 'role': role, 'mode': mode,
              'target': cap.get('id') if cap else None,
              'capability_sha256': digest(cap) if cap else None,
              'selection_basis': basis, 'tags': sorted(tags),
              'explicit_template_ids': list(template_ids) if template_ids is not None else None,
              'methods': [deepcopy(r) for r in data['methods'] if role in r['roles']],
              'templates': templates, 'candidates': candidates,
              'adapter': adapter,
              'adapter_status': 'SCOPED_PROMPT_POLICY' if adapter else 'UNRESOLVED_NO_MODEL_RULES',
              'execution': {'submitted': False, 'runnable': False, 'media_quality': 'NOT_RUN'},
              'instruction': '将方法写入当前原生字段并用现有 craft_review 说明采用或不适用；模板不能覆盖锁定项。'
                             '编译器只投影冻结字段；案例与静态检查不证明真实生成效果。'}
    output['plan_sha256'] = digest(output)
    return output


def verify_plan(value, cap=None, root=ROOT):
    """Recompute the complete selection, not just a self-reported digest."""
    if not isinstance(value, dict) or value.get('policy') != POLICY:
        raise ValueError('Missing prompt technique plan')
    expected = plan(cap, value.get('mode'), role=value.get('role'), tags=value.get('tags', ()),
                    template_ids=value.get('explicit_template_ids'), root=root)
    if value != expected:
        raise ValueError('Prompt technique plan or source/capability bytes changed')
    return True


def inspect_ir(ir):
    """Only objective supplementary checks; native validators own the full IR.

    No interpretation of dialogue, negative prose, exact camera numerics or image
    quality. One-main-action and realism remain source-bound host review criteria.
    """
    errors = []
    def fail(code, path, message):
        errors.append({'code': code, 'path': path, 'message': message, 'severity': 'error'})
    if not isinstance(ir, dict):
        fail('E_TECHNIQUE_INPUT', '/', 'Expected native AVIR object')
        return errors
    for i, binding in enumerate(ir.get('bindings') or []):
        if not isinstance(binding, dict):
            continue  # Native schema diagnoses it.
        inherit, exclude = binding.get('roles', []), binding.get('negative_roles', [])
        if isinstance(inherit, list) and isinstance(exclude, list):
            if set(x for x in inherit if isinstance(x, str)) & set(x for x in exclude if isinstance(x, str)):
                fail('E_TECHNIQUE_REFERENCE_ROLE_CONFLICT', f'/bindings/{i}',
                     '同一参考职责同时被要求继承与禁止继承；回到原责任节点澄清。')
    end = 0
    shots = ir.get('shots')
    duration = (ir.get('output') or {}).get('duration_ms')
    if isinstance(shots, list) and shots:
        for i, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            start, stop = shot.get('start_ms'), shot.get('end_ms')
            if type(start) is not int or type(stop) is not int or start != end or stop <= start:
                fail('E_TECHNIQUE_TIMELINE', f'/shots/{i}', '镜头必须从零起点连续覆盖时间轴，无空隙或重叠。')
            end = stop
        if type(duration) is int and end != duration:
            fail('E_TECHNIQUE_DURATION', '/output/duration_ms', '镜头结束时间与声明总时长不一致。')
    return errors


def enrich(artifact, ir, cap, mode, template_ids=None):
    """Add a compact, immutable-source plan; never insert prose into a locked prompt."""
    result = deepcopy(artifact)
    report = plan(cap, mode, template_ids=template_ids)
    report['input_sha256'] = digest(ir)
    report['inspection'] = inspect_ir(ir)
    # plan_sha256 covers selection only; the existing artifact+manifest hashes cover
    # the bound IR and inspection too. verify_compiled_report checks both explicitly.
    result['prompt_techniques'] = report
    result['diagnostics'].extend(report['inspection'])
    if report['inspection']:
        result['status'] = 'BLOCKED'
    return result


def verify_compiled_report(report, ir, cap, mode):
    expected = plan(cap, mode, template_ids=report.get('explicit_template_ids'))
    expected['input_sha256'] = digest(ir)
    expected['inspection'] = inspect_ir(ir)
    if report != expected:
        raise ValueError('E_TECHNIQUE_PLAN_CHANGED: compiled technique plan is stale or modified')
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('list', 'plan', 'check'))
    parser.add_argument('--target')
    parser.add_argument('--mode', default='text')
    parser.add_argument('--role', choices=ROLES, default='avir')
    parser.add_argument('--template', action='append', dest='template_ids')
    parser.add_argument('--tag', action='append', default=[], dest='tags')
    parser.add_argument('--input', type=Path, help='Native AVIR for objective checks; no rewriting')
    args = parser.parse_args(argv)
    try:
        from vpc_core import profile, validate
        if args.command == 'list':
            data = catalog()
            result = {'policy': POLICY, 'templates': [
                {k: r[k] for k in ('id', 'title', 'roles', 'tags')} for r in data['templates']],
                'model_profiles': [r['id'] for r in data['adapters']]}
            code = 0
        else:
            cap = profile(args.target) if args.target else None
            result = plan(cap, args.mode, role=args.role, tags=args.tags, template_ids=args.template_ids)
            code = 0
            if args.command == 'check':
                if not args.input:
                    raise ValueError('check requires --input native AVIR')
                ir = read(args.input)
                diagnostics = validate(ir, args.input.resolve().parent) + inspect_ir(ir)
                if cap:
                    from vpc_core import target_errors
                    diagnostics += target_errors(ir, cap, args.mode) if not any(
                        e['severity'] == 'error' for e in diagnostics) else []
                result = {'plan': result, 'diagnostics': diagnostics, 'media_quality': 'NOT_RUN'}
                code = 2 if any(e['severity'] in ('error', 'blocker') for e in diagnostics) else 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'BLOCKED', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
