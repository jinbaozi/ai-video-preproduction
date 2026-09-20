"""V4 contracts: no renderer, platform, or audio executor dependencies."""
from copy import deepcopy
from .schema import validate
from .utils import PACKAGE_ROOT, read_json

GRAPH = read_json(PACKAGE_ROOT / 'workflow-graph.json')
PHASES = GRAPH['phases']

def phase(number):
    return PHASES[number - 1]

def output(number):
    return phase(number)['folder'] + '/result.json'

def model_policy(number):
    return {key: phase(number)[key] for key in ('model', 'reasoning_effort')}

def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}

TEXT = {'type': 'string', 'minLength': 1}
STRINGS = {'type': 'array', 'items': TEXT}
NUMBER = {'type': 'number'}
VEC = {'type': 'array', 'items': NUMBER, 'minItems': 3, 'maxItems': 3}
INTERVAL = obj({'start_s': {'type': 'number', 'minimum': 0}, 'end_s': {'type': 'number', 'minimum': 0}, 'description': TEXT})
ACTION = obj({'start_s': NUMBER, 'end_s': NUMBER, 'phase': {'enum': ['prepare', 'start', 'develop', 'key', 'finish', 'recover', 'hold']}, 'description': TEXT, 'target_id': {'type': ['string', 'null']}, 'prop_state': TEXT})
CHARACTER = obj({'entity_id': TEXT, 'identity_asset_id': TEXT,
    'positions': {'type': 'array', 'minItems': 1, 'items': obj({'time_s': NUMBER, 'position': VEC, 'facing': TEXT, 'gaze': TEXT, 'pose': TEXT})},
    'actions': {'type': 'array', 'minItems': 1, 'items': ACTION},
    'emotions': {'type': 'array', 'minItems': 1, 'items': obj({'start_s': NUMBER, 'end_s': NUMBER, 'emotion': TEXT, 'intensity': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'expression': TEXT, 'trigger': TEXT})}})
SHOT = obj({'shot_id': TEXT, 'segment_id': TEXT, 'scene_id': TEXT, 'duration_s': {'type': 'number', 'minimum': 1, 'maximum': 12},
    'purpose': TEXT, 'initial_state': TEXT, 'end_state': TEXT, 'continuity': obj({'kind': {'enum': ['continuous', 'time_jump', 'scene_change']}, 'reason': TEXT}),
    'required_asset_ids': STRINGS, 'characters': {'type': 'array', 'items': CHARACTER},
    'camera': {'type': 'array', 'minItems': 1, 'items': obj({'start_s': NUMBER, 'end_s': NUMBER, 'framing': TEXT, 'position': VEC, 'movement': TEXT, 'focus': TEXT, 'axis': TEXT})},
    'sound': {'type': 'array', 'minItems': 1, 'items': obj({'start_s': NUMBER, 'end_s': NUMBER, 'speaker_id': {'type': ['string', 'null']}, 'dialogue': {'type': 'string'}, 'ambience': TEXT, 'sfx': TEXT, 'music_intent': TEXT})},
    'lighting': TEXT, 'environment': TEXT, 'negative_constraints': STRINGS,
    'key_moments': {'type': 'array', 'minItems': 1, 'maxItems': 3, 'items': obj({'time_s': NUMBER, 'name': TEXT, 'description': TEXT})}})
ASSET = obj({'asset_id': TEXT, 'name': TEXT, 'kind': {'enum': ['role', 'scene', 'prop', 'style']}, 'entity_ids': STRINGS,
    'version_label': TEXT, 'prompt': TEXT, 'continuity': STRINGS, 'forbidden_inheritance': STRINGS})
ASSET['properties']['reference_source_ids'] = STRINGS
SCENE = obj({'scene_id': TEXT, 'origin': TEXT, 'axes': TEXT, 'units': TEXT, 'bounds': obj({'min': VEC, 'max': VEC}),
    'fixed_elements': STRINGS, 'entrances': STRINGS, 'blocking': TEXT, 'axis_rules': TEXT})
BASE_DATA = {'content': TEXT, 'source_refs': STRINGS, 'inferences': STRINGS,
             'reuse': {'enum': ['created', 'reused', 'normalized']}}

def data_schema(number):
    properties = deepcopy(BASE_DATA)
    if number == 1:
        properties.update(entities={'type': 'array', 'items': obj({'entity_id': TEXT, 'name': TEXT})}, unresolved=STRINGS)
    if number == 6:
        properties['segments'] = {'type': 'array', 'minItems': 1, 'items': obj({'segment_id': TEXT, 'target_duration_s': {'type': 'number', 'exclusiveMinimum': 0}, 'source_text': TEXT})}
    if number == 7:
        properties['shots'] = {'type': 'array', 'minItems': 1, 'items': SHOT}
    if number == 8:
        properties['assets'] = {'type': 'array', 'minItems': 1, 'items': ASSET}
    if number == 9:
        properties.update(scenes={'type': 'array', 'minItems': 1, 'items': SCENE}, shots={'type': 'array', 'minItems': 1, 'items': SHOT})
    if number == 10:
        properties['review'] = obj({'passed': {'const': True}, 'checked_shot_ids': STRINGS, 'limitations': STRINGS})
    return obj(properties)

def validate_payload(value):
    required_by_kind = {
        'project': ['workflow_id', 'segment_target_s', 'adaptation_policy'],
        'workflow-state': ['status', 'phase_status', 'decisions', 'media', 'approvals', 'aliases'],
        'manifest': ['files'], 'source-registry': ['sources'], 'phase-index': ['phases'],
        'phase-result': ['phase', 'data', 'source_fingerprint', 'execution', 'qa', 'input_hashes'],
        'task-envelope': ['task_id', 'phase', 'task_kind', 'model_policy', 'context_fingerprint', 'loaded_resources', 'input_artifacts'],
        'image-record': ['key', 'role', 'path', 'filename', 'sha256', 'alias', 'input_hash', 'automatic_quality', 'human_approval', 'input_bindings'],
        'prompt-package': ['prompts', 'delivery_scope', 'platform_readiness', 'execution_status'],
        'decision-request': ['key', 'question', 'options', 'context_fingerprint', 'phase'],
    }
    validate(value, {'type': 'object', 'required': required_by_kind.get(value['artifact_type'], [])})
    if value['artifact_type'] == 'task-envelope':
        if value['model_policy'] != model_policy(value['phase']):
            raise ValueError('Task model does not match phase policy')
    if value['artifact_type'] == 'image-record':
        validate(value, {'properties': {'sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
                 'alias': {'type': 'string', 'pattern': '^@image_(role|scene|prop|style|board)_[1-9][0-9]*$'}}})
    if value['artifact_type'] == 'phase-result':
        number = value['phase']
        validate(value['data'], data_schema(number))
        if number in (7, 9):
            validate_shots(value['data']['shots'])
        if value['qa'].get('passed') is not True or value['qa'].get('actor') != 'automatic':
            raise ValueError('Stage needs explicit automatic QA, not invented human approval')

def validate_shots(shots):
    ids = [s['shot_id'] for s in shots]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate shot ID')
    for shot in shots:
        duration = shot['duration_s']
        for track in shot['characters']:
            times = [k['time_s'] for k in track['positions']]
            if times != sorted(set(times)) or times[0] != 0 or any(t < 0 or t > duration for t in times):
                raise ValueError('Position keyframes must be ordered, unique, start at zero and fit shot')
        groups = [shot['camera'], shot['sound']]
        groups += [t[k] for t in shot['characters'] for k in ('actions', 'emotions')]
        for group in groups:
            if [x['start_s'] for x in group] != sorted(x['start_s'] for x in group):
                raise ValueError('Track must be ordered')
            for item in group:
                if not 0 <= item['start_s'] < item['end_s'] <= duration:
                    raise ValueError('Track time outside shot duration')
        times = [k['time_s'] for k in shot['key_moments']]
        if times != sorted(set(times)) or any(t < 0 or t > duration for t in times):
            raise ValueError('Invalid storyboard moment')
    for previous, current in zip(shots, shots[1:]):
        if current['continuity']['kind'] == 'continuous':
            if previous['scene_id'] != current['scene_id'] or previous['end_state'] != current['initial_state']:
                raise ValueError('Continuous shot state handoff mismatch')
            prior = {t['entity_id']: t for t in previous['characters']}
            for track in current['characters']:
                if track['entity_id'] in prior and prior[track['entity_id']]['positions'][-1]['position'] != track['positions'][0]['position']:
                    raise ValueError('Unexplained character teleport')
