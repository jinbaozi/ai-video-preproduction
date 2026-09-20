"""One-time, deterministic v2 -> v3 repository contract upgrade.

This is repository maintenance, NOT permission to migrate user projects.
"""
from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'schemas'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required)}


def array(items, **kw):
    return {'type': 'array', 'items': items, **kw}


TEXT = {'type': 'string', 'minLength': 1}
NUMBER = {'type': 'number'}
VECTOR = obj({a: NUMBER for a in 'xyz'}, 'xyz')
STRINGS = array(TEXT)
archive = SCHEMAS / 'legacy-v2-schemas.json'
if not archive.exists():
    write(archive, {p.name: read(p) for p in sorted(SCHEMAS.glob('*.schema.json'))})
for path in SCHEMAS.glob('*.schema.json'):
    value = read(path)
    value = json.loads(json.dumps(value).replace('ai-comic-drama-main-v2', 'ai-comic-drama-main-v3'))
    value['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    value['$id'] = 'urn:ai-comic-drama:3.0:' + path.name
    if 'schema_version' in value.get('properties', {}):
        value['properties']['schema_version'] = {'const': '3.0'}
    write(path, value)


def formal(kind, properties, required):
    value = deepcopy(read(SCHEMAS / 'artifact.schema.json'))
    value['$id'] = 'urn:ai-comic-drama:3.0:' + kind + '.schema.json'
    value['properties']['artifact_type'] = {'const': kind}
    value['properties'].update(properties)
    value['required'] = list(dict.fromkeys(value['required'] + list(required)))
    write(SCHEMAS / (kind + '.schema.json'), value)


scene_fields = ('scene_id', 'purpose', 'pov', 'audience_information', 'emotional_start',
                'emotional_end', 'camera_rationale', 'edit_rationale')
beat_fields = ('beat_id', 'character_id', 'goal', 'obstacle', 'tactic', 'action', 'reaction', 'trigger')
formal('director-treatment', {'scenes': array(obj({
    **{key: TEXT for key in scene_fields},
    'source_refs': array(TEXT, minItems=1),
    'beats': array(obj({key: TEXT for key in beat_fields}, beat_fields), minItems=1),
}, (*scene_fields, 'source_refs', 'beats')), minItems=1)}, ['scenes'])

path = SCHEMAS / 'shot-timeline-spec.schema.json'
shot = read(path)
shot['properties']['timing'] = obj({'fps': {'type': 'integer', 'minimum': 1, 'maximum': 120},
                                   'frame_count': {'type': 'integer', 'minimum': 1},
                                   'authority': {'const': 'frames'}}, ['fps', 'frame_count', 'authority'])
shot['required'] = list(dict.fromkeys(shot['required'] + ['timing']))
trajectory = shot['properties']['character_tracks']['items']['properties']['trajectory']['items']
trajectory['properties'].update({
    'rotation_quaternion': array(NUMBER, minItems=4, maxItems=4),
    'interpolation': {'enum': ['linear', 'hold', 'smoothstep']},
    'joint_targets': {'type': 'object', 'additionalProperties': VECTOR},
    'gaze_target_id': {'type': ['string', 'null']},
})
trajectory['required'] = list(dict.fromkeys(trajectory['required'] + ['rotation_quaternion', 'interpolation']))
camera = obj({
    'position': VECTOR, 'target': VECTOR, 'projection': {'enum': ['perspective', 'orthographic']},
    'focal_length_mm': {'type': 'number', 'exclusiveMinimum': 0},
    'sensor_width_mm': {'type': 'number', 'exclusiveMinimum': 0},
    'ortho_scale_m': {'type': 'number', 'exclusiveMinimum': 0},
    'focus_distance_m': {'type': 'number', 'exclusiveMinimum': 0},
    'interpolation': {'enum': ['linear', 'hold', 'smoothstep']},
    'time_s': {'type': 'number', 'minimum': 0},
    'start_s': {'type': 'number', 'minimum': 0}, 'end_s': {'type': 'number', 'minimum': 0},
    'full_shot': {'const': True},
    'time_mode': {'const': 'full_shot'},
}, ['position', 'target', 'projection', 'focal_length_mm', 'sensor_width_mm', 'interpolation'])
camera['anyOf'] = [{'required': ['time_s']}, {'required': ['start_s', 'end_s']}, {'required': ['full_shot']}, {'required': ['time_mode']}]
camera['allOf'] = [{'if': {'properties': {'projection': {'const': 'orthographic'}}}, 'then': {'required': ['ortho_scale_m']}}]
shot['properties']['camera_track'] = array(camera, minItems=1)
prop_key = obj({'time_s': {'type': 'number', 'minimum': 0}, 'position': VECTOR,
                'holder_id': {'type': ['string', 'null']}, 'holder_joint': TEXT,
                'handoff_from': {'type': ['string', 'null']}, 'state': TEXT,
                'interpolation': {'enum': ['linear', 'hold', 'smoothstep']}},
               ['time_s', 'position', 'holder_id', 'interpolation'])
shot['properties']['prop_tracks'] = array(obj({'asset_id': TEXT, 'trajectory': array(prop_key, minItems=1)}, ['asset_id', 'trajectory']))
write(path, shot)
path = SCHEMAS / 'scene-space-plan.schema.json'
scene = read(path)
system = scene['properties']['scenes']['items']['properties']['coordinate_system']
bounds = obj({a: array(NUMBER, minItems=2, maxItems=2) for a in 'xyz'}, 'xyz')
system['properties'].update({'bounds': bounds, 'world_bounds': bounds})
system['allOf'] = [{'if': {'properties': {'units': {'const': 'normalized'}}}, 'then': {'required': ['world_bounds']}}]
scene['properties']['scenes']['items']['properties']['character_placements']['items']['properties']['position'] = VECTOR
write(path, scene)

binding = obj({
    'reference_id': TEXT, 'role': {'enum': ['character_identity', 'storyboard_frame', 'layout', 'style', 'scene', 'prop']},
    'entity_ids': STRINGS, 'revision': {'type': 'integer', 'minimum': 1},
    'path': TEXT, 'sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
    'allowed_inheritance': STRINGS, 'forbidden_inheritance': STRINGS,
    'approval_ref': {'type': ['string', 'null']}, 'shot_id': TEXT,
    'time_s': {'type': 'number', 'minimum': 0}, 'slot': {'type': 'integer', 'minimum': 1},
}, ['reference_id', 'role', 'entity_ids', 'revision', 'path', 'sha256', 'allowed_inheritance', 'forbidden_inheritance', 'approval_ref'])
binding['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
binding['$id'] = 'urn:ai-comic-drama:3.0:reference-binding.schema.json'
binding['allOf'] = [{'if': {'properties': {'role': {'const': 'storyboard_frame'}}}, 'then': {'required': ['shot_id', 'time_s']}}]
write(SCHEMAS / 'reference-binding.schema.json', binding)
refs = array({'$ref': binding['$id']})
formal('evaluated-frame-state', {
    'scene_id': TEXT, 'shot_id': TEXT, 'time_s': NUMBER, 'source_hash': TEXT,
    'camera': {'type': 'object'}, 'characters': array({'type': 'object'}), 'frame_time': {'type': 'object'},
}, ['scene_id', 'shot_id', 'time_s', 'source_hash', 'camera', 'characters', 'frame_time'])
formal('media-job', {
    'job_id': TEXT, 'execution_context': {'enum': ['codex-host', 'local-blender', 'provided']},
    'prompt': TEXT, 'prompt_sha256': TEXT, 'input_hash': TEXT, 'reference_bindings': refs,
    'status': {'enum': ['pending', 'returned', 'failed', 'uncertain']},
    'output_kind': {'enum': ['asset', 'storyboard', 'previsualization']},
}, ['job_id', 'execution_context', 'prompt', 'prompt_sha256', 'input_hash', 'reference_bindings', 'status', 'output_kind'])
formal('media-result', {
    'job_id': TEXT, 'input_hash': TEXT, 'output_path': TEXT, 'sha256': TEXT,
    'provider': {'enum': ['codex-imagegen', 'provided', 'local-blender', 'local-fixture']},
    'call_evidence': {'type': 'object'}, 'reference_bindings': refs,
}, ['job_id', 'input_hash', 'output_path', 'sha256', 'provider', 'call_evidence', 'reference_bindings'])

formal('asset-plan', {'assets': array(obj({
    'asset_id': TEXT, 'asset_type': {'enum': ['style-reference', 'character-reference', 'scene-reference', 'prop-reference', 'other']},
    'description': TEXT, 'entity_ids': STRINGS, 'reference_ids': STRINGS,
    'continuity_constraints': STRINGS, 'forbidden_inheritance': STRINGS,
}, ['asset_id', 'asset_type', 'description', 'continuity_constraints', 'forbidden_inheritance']), minItems=1)}, ['assets'])
formal('edit-plan', {
    'timeline': array(obj({'shot_id': TEXT, 'duration_s': {'type': 'number', 'exclusiveMinimum': 0},
                         'in_s': {'type': 'number', 'minimum': 0}}, ['shot_id', 'duration_s']), minItems=1),
    'dialogue_table': array({**obj({'line_id': TEXT, 'speaker_id': TEXT, 'text': TEXT,
                                'start_s': {'type': 'number', 'minimum': 0},
                                'end_s': {'type': 'number', 'exclusiveMinimum': 0},
                                'duration_s': {'type': 'number', 'exclusiveMinimum': 0}}, ['line_id', 'speaker_id', 'text', 'start_s']),
                            'anyOf': [{'required': ['end_s']}, {'required': ['duration_s']}]}),
    'voice_cast': array({'type': 'object'}), 'sfx': array({'type': 'object'}),
    'music': array({'type': 'object'}), 'subtitle_language': TEXT,
}, ['timeline', 'dialogue_table', 'voice_cast', 'sfx', 'music', 'subtitle_language'])

path = SCHEMAS / 'final-delivery-index.schema.json'
value = read(path)
value['properties']['status']['enum'] = list(dict.fromkeys(value['properties']['status']['enum'] + ['draft']))
write(path, value)

path = SCHEMAS / 'prompt-package.schema.json'
value = read(path)
fields = {'delivery_scope': {'enum': ['prompt-draft', 'dual-reference-previs']},
          'dual_reference_status': {'enum': ['missing', 'ready']},
          'platform_readiness': {'enum': ['unverified', 'supported', 'incompatible']},
          'execution_status': {'enum': ['not_submitted', 'submitted', 'returned', 'verified']}}
value['properties'].update(fields)
value['required'] = list(dict.fromkeys(value['required'] + list(fields)))
prompt = value['properties']['prompts']['items']
prompt['properties'].update({'reference_bindings': {**refs, 'maxItems': 5},
                             'execution_controls': {'type': 'object'},
                             'field_coverage': array(obj({'source_pointer': TEXT, 'destination_pointer': TEXT,
                                                          'sha256': TEXT, 'status': {'const': 'transferred'}},
                                                         ['source_pointer', 'destination_pointer', 'sha256', 'status']), minItems=1)})
prompt['required'] = list(dict.fromkeys(prompt['required'] + ['reference_bindings', 'execution_controls', 'field_coverage']))
write(path, value)

graph = read(ROOT / 'workflow-graph.json')
graph['schema_version'], graph['workflow_id'] = '3.0', 'ai-comic-drama-main-v3'
director_path = 'stages/04-改编方案/director-treatment.json'
if not any(s['id'] == 'director_treatment' for s in graph['stages']):
    index = next(i for i, s in enumerate(graph['stages']) if s['id'] == 'adaptation_plan') + 1
    graph['stages'].insert(index, {
        'id': 'director_treatment', 'phase_id': 'phase-04', 'kind': 'semantic', 'role': 'director',
        'resources': ['references/role-director.md'],
        'inputs': ['stages/03-叙事提取与动态记忆/narrative-bundle.json', 'stages/02-输入标准化与缺口处理/intake-brief.json'],
        'output': director_path, 'artifact_type': 'director-treatment',
    })
for stage in graph['stages']:
    if stage['id'] in ('screenplay', 'story_quality_gate', 'storyboard_plan', 'shot_timeline_specs', 'canonical_prompt_compile'):
        stage['inputs'] = list(dict.fromkeys(stage['inputs'] + [director_path]))
write(ROOT / 'workflow-graph.json', graph)
catalog = read(ROOT / 'resource-catalog.json')
catalog['schema_version'] = '3.0'
catalog['resources'] = list(dict.fromkeys(catalog['resources'] + ['references/role-director.md', 'references/codex-imagegen.md', 'references/blender-execution.md']))
write(ROOT / 'resource-catalog.json', catalog)

# Only runtime/fixture version literals; preserve platform names and v2 input tests.
for relative in ['src/ai_comic_drama_workflow/__init__.py', 'src/ai_comic_drama_workflow/validation.py',
                 'tests/helpers.py', 'tests/test_v2_workflow.py', 'tests/test_schema_and_choices.py',
                 'tests/test_routing_and_disclosure.py', 'tests/test_recovery_and_media.py']:
    path = ROOT / relative
    path.write_text(path.read_text().replace('"0.2.0"', '"0.3.0"').replace('"2.0"', '"3.0"'))
for relative in ['tests/test_schema_and_choices.py', 'tests/test_routing_and_disclosure.py', 'tests/test_recovery_and_media.py']:
    path = ROOT / relative
    path.write_text(path.read_text().replace('"selections": {"work_depth":', '"selections": {"delivery_target": "prompt-draft", "work_depth":'))
