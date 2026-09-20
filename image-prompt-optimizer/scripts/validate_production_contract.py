"""Validate the local production-contract schema and traceability (not image quality).

Python standard library only. This implements exactly the JSON Schema keywords used
by the bundled schema; it is not a general JSON Schema implementation.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas' / 'production-contract.schema.json'


def pointer(document, path):
    if path == '':
        return document
    if not path.startswith('/') or re.search(r'~(?![01])', path):
        raise ValueError('Invalid JSON Pointer')
    value = document
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise ValueError('Invalid array index')
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError('Pointer traverses scalar')
    return value


def same(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def schema_errors(value, schema, root, path='$'):
    if '$ref' in schema:
        return schema_errors(value, pointer(root, schema['$ref'][1:]), root, path)
    if 'anyOf' in schema:
        if any(not schema_errors(value, branch, root, path) for branch in schema['anyOf']):
            return []
        return [f'{path}: does not match any allowed shape']
    errors = []
    types = {'object': lambda x: isinstance(x, dict), 'array': lambda x: isinstance(x, list),
             'string': lambda x: isinstance(x, str), 'integer': lambda x: type(x) is int,
             'boolean': lambda x: type(x) is bool, 'null': lambda x: x is None}
    if 'type' in schema:
        allowed = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
        if not any(types[t](value) for t in allowed):
            return [f'{path}: expected {allowed}']
    if 'enum' in schema and not any(same(value, x) for x in schema['enum']):
        errors.append(f'{path}: value outside enum')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        for key in schema.get('required', []):
            if key not in value:
                errors.append(f'{path}/{key}: required')
        for key, item in value.items():
            if key in props:
                errors.extend(schema_errors(item, props[key], root, f'{path}/{key}'))
            elif schema.get('additionalProperties') is False:
                errors.append(f'{path}/{key}: unknown field')
            elif isinstance(schema.get('additionalProperties'), dict):
                errors.extend(schema_errors(item, schema['additionalProperties'], root, f'{path}/{key}'))
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            errors.append(f'{path}: too few items')
        for index, item in enumerate(value):
            errors.extend(schema_errors(item, schema.get('items', {}), root, f'{path}/{index}'))
    if isinstance(value, str):
        if len(value.strip()) < schema.get('minLength', 0):
            errors.append(f'{path}: empty string')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(f'{path}: invalid format')
    if type(value) is int and value < schema.get('minimum', value):
        errors.append(f'{path}: below minimum')
    return errors


def has_cycle(edges):
    graph = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    active, done = set(), set()

    def visit(node):
        if node in active:
            return True
        if node in done:
            return False
        active.add(node)
        if any(visit(n) for n in graph.get(node, ())):
            return True
        active.remove(node)
        done.add(node)
        return False

    return any(visit(node) for node in graph)


def validate(data, baseline=None):
    schema = json.loads(SCHEMA.read_text())
    errors = schema_errors(data, schema, schema)
    if errors:
        return errors

    def index(rows, label):
        found = {}
        for row in rows:
            if row['id'] in found:
                errors.append(f'{label}: duplicate id {row["id"]}')
            found[row['id']] = row
        return found

    def refs(values, known, label):
        for value in values:
            if value not in known:
                errors.append(f'{label}: unknown reference {value}')

    sources = index(data['sources'], 'sources')
    entities = index(data['icir']['entities'], 'entities')
    frames = index(data['icir']['frames'], 'frames')
    texts = index(data['icir']['texts'], 'texts')
    constraints = index(data['constraints'], 'constraints')
    index(data['compilations'], 'compilations')
    steps = index(data['execution'], 'execution')
    index(data['acceptance'], 'acceptance')
    index(data['unresolved'], 'unresolved')
    hard = {key: row for key, row in constraints.items() if row['level'] == 'hard'}
    if not hard:
        errors.append('constraints: at least one hard requirement is needed')
    for label, rows in [('entities', entities.values()), ('texts', texts.values()),
                        ('facts', data['facts']), ('constraints', constraints.values()),
                        ('unresolved', data['unresolved'])]:
        for row in rows:
            refs(row['source_ids'], sources, label)
    for row in data['facts'] + data['constraints']:
        try:
            if not row['path'].startswith('/icir/') or not same(pointer(data, row['path']), row['value']):
                errors.append(f'{row["path"]}: value does not match ICIR')
        except (KeyError, IndexError, ValueError):
            errors.append(f'{row["path"]}: unresolved ICIR pointer')
        if row.get('origin') == 'observed':
            if any(not sources[x]['reviewed'] for x in row['source_ids'] if x in sources):
                errors.append(f'{row["path"]}: observed fact uses unreviewed source')
    for row in data['icir']['references']:
        refs([row['source_id']], sources, 'reference asset')
        refs(row['entity_ids'], entities, 'reference binding')
    slots = [r['slot'] for r in data['icir']['references']]
    if len(slots) != len(set(slots)):
        errors.append('reference binding: duplicate attachment slot')
    for row in frames.values():
        refs(row['entity_ids'], entities, row['id'])
        if len(row['entity_ids']) != len(set(row['entity_ids'])):
            errors.append(f'{row["id"]}: duplicate entity')
        for state in row.get('performance', []):
            refs([state['entity_id']], row['entity_ids'], 'performance')
        prev = row.get('continuity', {}).get('previous_frame_id')
        if prev:
            refs([prev], frames, 'continuity')
    if has_cycle([(f['id'], f['continuity']['previous_frame_id']) for f in frames.values()
                  if f.get('continuity', {}).get('previous_frame_id')]):
        errors.append('continuity: cyclic frame order')
    graphs = {}
    inverse = {'right_of': 'left_of', 'behind': 'in_front_of', 'below': 'above'}
    for row in data['icir']['relations']:
        refs([row['frame_id']], frames, 'relation frame')
        refs([row['from'], row['to']], frames.get(row['frame_id'], {}).get('entity_ids', []), 'relation entity')
        relation, a, b = row['relation'], row['from'], row['to']
        owner = row.get('coordinate_owner')
        if row['coordinate_system'] == 'subject':
            if not owner:
                errors.append('spatial: subject coordinates require coordinate_owner')
            else:
                refs([owner], frames.get(row['frame_id'], {}).get('entity_ids', []), 'coordinate owner')
        if relation in inverse:
            relation, a, b = inverse[relation], b, a
        if relation in ('left_of', 'in_front_of', 'above', 'fully_occludes'):
            key = (row['frame_id'], row['coordinate_system'], owner, relation)
            graphs.setdefault(key, []).append((a, b))
    for key, edges in graphs.items():
        if has_cycle(edges):
            errors.append(f'spatial: cyclic {key}')
    for row in texts.values():
        refs([row['frame_id']], frames, 'text frame')
        if row['speaker_id'] is not None:
            refs([row['speaker_id']], frames.get(row['frame_id'], {}).get('entity_ids', []), 'text speaker')
        elif row['kind'] in ('dialogue', 'thought'):
            errors.append(f'{row["id"]}: dialogue/thought requires speaker')
        if row['channel'] == 'visible' and not row['placement']:
            errors.append(f'{row["id"]}: visible text requires placement')
        if row['channel'] == 'context_only' and row['placement'] is not None:
            errors.append(f'{row["id"]}: context text cannot have on-image placement')
    for out in data['compilations']:
        cap = out['capability']
        refs(cap['source_ids'], sources, 'capability')
        if cap['status'] == 'verified':
            if not cap['checked_at'] or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', cap['checked_at']) or not cap['source_ids']:
                errors.append('capability: verification needs date and sources')
            elif cap['checked_at']:
                try:
                    date.fromisoformat(cap['checked_at'])
                except ValueError:
                    errors.append('capability: invalid verification date')
            if any(sources[x]['kind'] != 'official' or not sources[x]['reviewed'] for x in cap['source_ids'] if x in sources):
                errors.append('capability: verification requires reviewed official evidence')
        elif cap['allowed_native_params']:
            errors.append('capability: unknown capabilities cannot declare supported parameters')
        if out['native_params'] and (cap['status'] != 'verified' or out['surface'] in ('generic', 'chat')):
            errors.append('capability: native params require verified executable surface')
        refs(out['native_params'], cap['allowed_native_params'], 'native parameter')
        if out['negative_prompt'] is not None and (cap['status'] != 'verified' or cap['negative_mode'] != 'separate'):
            errors.append('capability: independent negative prompt not supported by evidence')
        refs(out['constraint_clauses'], constraints, 'constraint clause')
        if out['status'] != 'BLOCKED':
            if not out['prompt'].strip():
                errors.append('compilation: ready output requires prompt')
            for key in hard:
                clause = out['constraint_clauses'].get(key)
                if not clause or clause not in out['prompt']:
                    errors.append(f'compilation {out["id"]}: hard clause missing from prompt: {key}')
            for row in texts.values():
                if row['channel'] == 'visible' and row['content'] not in out['prompt']:
                    errors.append(f'compilation: visible text missing: {row["id"]}')
        elif not data['unresolved']:
            errors.append('compilation: blocked output needs unresolved issue')
        if out['status'] == 'DEGRADED' and not out['warnings']:
            errors.append('compilation: degraded output needs explanation')
    for row in steps.values():
        refs(row['depends_on'], steps, 'execution dependency')
        if row['status'] == 'DONE' and any(steps[x]['status'] != 'DONE' for x in row['depends_on'] if x in steps):
            errors.append('execution: done step has unfinished dependency')
    if has_cycle([(r['id'], dep) for r in steps.values() for dep in r['depends_on']]):
        errors.append('execution: cyclic dependencies')
    covered = set()
    visual_evidence = False
    for row in data['acceptance']:
        refs(row['constraint_ids'], constraints, 'acceptance')
        covered.update(row['constraint_ids'])
        if row['status'] in ('PASS', 'FAIL') and not row['evidence']:
            errors.append('acceptance: concluded check requires evidence')
        if row['stage'] == 'visual' and row['status'] in ('PASS', 'FAIL') and row['evidence']:
            visual_evidence = True
    for key in hard.keys() - covered:
        errors.append(f'acceptance: missing hard requirement {key}')
    output = data['icir']['output']
    width, height = map(int, output['aspect_ratio'].split(':'))
    for field in ('requested_pixels', 'delivered_pixels'):
        px = output[field]
        if px and px['width'] * height != px['height'] * width:
            errors.append(f'{field}: aspect ratio mismatch')
    if (output['delivered_pixels'] or output['native_resolution'] != 'unknown') and not visual_evidence:
        errors.append('output: delivered/native claims require visual evidence')
    if baseline is not None:
        baseline_errors = validate(baseline)
        if baseline_errors:
            errors.append('baseline: invalid contract')
        else:
            if data['contract_id'] != baseline['contract_id']:
                errors.append('baseline: contract id changed; use new contract for authorized hard changes')
            for old in baseline['constraints']:
                if old['level'] == 'hard' and not same(constraints.get(old['id']), old):
                    errors.append(f'baseline: hard constraint changed or removed: {old["id"]}')
                if old['level'] == 'hard':
                    old_sources = {row['id']: row for row in baseline['sources']}
                    for source_id in old['source_ids']:
                        if not same(sources.get(source_id), old_sources[source_id]):
                            errors.append(f'baseline: hard source changed or removed: {source_id}')
    return errors


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f'Non-JSON number: {value}')

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid_constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract')
    parser.add_argument('--baseline')
    args = parser.parse_args()
    try:
        errors = validate(load(args.contract), load(args.baseline) if args.baseline else None)
    except (OSError, ValueError, RecursionError) as exc:
        errors = [str(exc)]
    print(json.dumps({'status': 'INVALID' if errors else 'STATIC_VALID', 'errors': errors,
                      'scope': 'schema, references, locks, coverage and state; not semantic or visual proof'},
                     ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
