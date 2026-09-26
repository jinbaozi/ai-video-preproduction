import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from ai_comic_drama_workflow.v5_adapters import encoded, storyboard_to_avir

ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
TASK = 'TASK_f2d0f9805f575ed23ebfdb6d'
OUT = ROOT / 'runtime/v6/candidates' / TASK / '1'
EV = OUT / 'evidence'
MODULE = ROOT / 'runtime/modules/ff88d829cbbcb9c724b7afa3e1c85b0310deeb635284241230e3439fb6c41d4b/video-prompt-compiler'
ENV = json.loads((ROOT / 'runtime/v6/state.json').read_text())['tasks'][TASK]['envelope']
TASK5 = json.loads((ROOT / ENV['inputs'][1]['uri']).read_text())
PREFIX = f'runtime/v6/candidates/{TASK}/1/'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def run(*args):
    environment = os.environ.copy()
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = subprocess.run([sys.executable, *map(str, args)], text=True, capture_output=True, env=environment)
    return {'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr,
            'command': [str(x) for x in args]}


assert ENV['task_id'] == TASK and ENV['batch'] == 1 and ENV['role'] == 'control'
assert ENV['input_revision'] == 630
assert ENV['input_digest'] == '31b81c547956ff58bf81e2542c429da8b4542d07ac46af34587b3e34a6aeba7b'
source_rows = []
for item in ENV['inputs'] + ENV['resources']:
    path = ROOT / item['uri']
    actual = sha(path)
    assert actual == item['sha256'], (item['uri'], actual)
    source_rows.append({'uri': item['uri'], 'expected_sha256': item['sha256'],
                        'observed_sha256': actual, 'bytes': path.stat().st_size, 'status': 'MATCH'})
put(EV / 'source-integrity.json', {'schema': 'control-source-integrity/1.0',
                                  'task_id': TASK, 'input_revision': ENV['input_revision'],
                                  'input_digest': ENV['input_digest'],
                                  'frozen_inputs_and_resources': source_rows})
put(EV / 'module-receipt.json', {'module': ENV['module'], 'resource_hashes': source_rows[2:]})

source_path = ROOT / ENV['inputs'][0]['uri']
source = json.loads(source_path.read_text())
promoted_path = Path(TASK5['inputs'][0]['uri'])
assert sha(promoted_path) == TASK5['inputs'][0]['sha256']
promoted = json.loads(promoted_path.read_text())
assert source['schema_version'] == promoted['schema_version'] == 'storyboard-ir/1.2'

changes = []
def compare(a, b, pointer=''):
    if type(a) is not type(b):
        changes.append({'pointer': pointer, 'candidate': a, 'promoted': b})
    elif isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            path = pointer + '/' + key
            if key not in a or key not in b:
                changes.append({'pointer': path, 'candidate': a.get(key), 'promoted': b.get(key)})
            else:
                compare(a[key], b[key], path)
    elif isinstance(a, list):
        if len(a) != len(b):
            changes.append({'pointer': pointer + '/length', 'candidate': len(a), 'promoted': len(b)})
        for index, (left, right) in enumerate(zip(a, b)):
            compare(left, right, pointer + '/' + str(index))
    elif a != b:
        changes.append({'pointer': pointer, 'candidate': a, 'promoted': b})
compare(source, promoted)
allowed = {f'/sources/{index}/uri' for index in range(5)}
allowed |= {'/timeline/semantic_review/input_sha256'}
allowed |= {f'/upstreams/{index}/{key}' for index in range(len(source['upstreams']))
            for key in ('sha256', 'uri')}
assert {x['pointer'] for x in changes} == allowed, [x['pointer'] for x in changes]
put(EV / 'promotion-diff.json', {'schema': 'control-promotion-diff/1.0',
                                'candidate_storyboard_sha256': sha(source_path),
                                'promoted_storyboard_sha256': sha(promoted_path),
                                'diff_count': len(changes), 'core_semantics_unchanged': True,
                                'differences': changes})

avir, report = storyboard_to_avir(promoted, ROOT)
assert report['adapter'] == '1.2.0' and report['status'] == 'MAPPED'
assert report['semantic_review'] == 'INHERITED_DETERMINISTICALLY'
assert report['losses'] == []
assert len(report['derived_camera_tracks']) == 1
assert len([row for row in report['detail_coverage']
            if row['rule'] == 'STATE_SAMPLE.BOUNDARY_VISIBILITY.1.1']) == 10
assert avir['timeline']['semantic_review']['status'] == 'PASS'
put(OUT / 'native-av-ir.json', avir)
put(EV / 'adapter-report.json', report)
assert sha(OUT / 'native-av-ir.json') == report['target_hash']

sample_rows = []
for at, boundary in ((0, 'start_state'), (12000, 'end_state')):
    sample = next(row for row in promoted['timeline']['state_samples']
                  if row['shot_id'] == 'S1' and row['at_ms'] == at)
    states = {row['entity_id']: row for row in avir['shots'][0][boundary]}
    for entity_id, timeline_state in sample['entities'].items():
        avir_value = states[entity_id]['visible_parts']
        assert avir_value == timeline_state['visible_parts'], (entity_id, at)
        sample_rows.append({'at_ms': at, 'entity_id': entity_id,
                            'timeline_visible_parts': timeline_state['visible_parts'],
                            'avir_visible_parts': avir_value, 'status': 'MATCH'})
assert next(row for row in promoted['timeline']['state_samples']
            if row['at_ms'] == 10500)['entities']['PROP_LETTER']['visible_parts'] == []
assert next(row for row in avir['shots'][0]['end_state']
            if row['entity_id'] == 'PROP_LETTER')['visible_parts'] == []
old_avir = ROOT / 'runtime/v6/candidates/TASK_ddd2a77146e2ddd7866420cb/1/native-av-ir.json'
old_conflict = next(row for row in json.loads(old_avir.read_text())['shots'][0]['end_state']
                    if row['entity_id'] == 'PROP_LETTER')['visible_parts']
assert old_conflict == ['body', 'prop']
put(EV / 'boundary-visibility.json', {'schema': 'control-boundary-visibility/1.0',
                                     'storyboard_sha256': sha(promoted_path),
                                     'avir_sha256': sha(OUT / 'native-av-ir.json'),
                                     'mapping_rule': 'STATE_SAMPLE.BOUNDARY_VISIBILITY.1.1',
                                     'rows': sample_rows,
                                     'letter_10500ms_visible_parts': [],
                                     'letter_12000ms_visible_parts': [],
                                     'prior_accepted_control_avir_sha256': sha(old_avir),
                                     'prior_wrong_end_value': old_conflict,
                                     'corrected_end_pointer': '/shots/0/end_state/4/visible_parts',
                                     'corrected_end_value': [],
                                     'media_review': 'NOT_RUN'})

shot = promoted['shots'][0]
assert shot['camera']['start_m'] == shot['camera']['end_m'] == [0, 1.2, -2.8]
assert '[0,1.2,-2.8]' in promoted['timeline']['camera_operations'][0]['start_position']
assert '[0,1.2,-2.8]' in promoted['timeline']['camera_operations'][0]['end_position']
config = {'schema': 'shot-control-config/0.2', 'controls': [],
          'lenses': {'S1': {'aspect': 1280/720, 'basis': 'authored_proxy',
                            'vertical_fov_deg': 50,
                            'evidence': 'Accepted StoryboardIR S1 fixes start_m=end_m=[0,1.2,-2.8] in timeline x-right/y-up/z-depth coordinates, look_at_m=[0,1.0,0], locked operation CAM_LOCKED, and 1280x720 output. Director scene X-right/Y-depth/Z-up point [0,-2.8,1.2] maps to the same physical camera point. 50-degree vertical FOV is an authored review proxy, not a calibrated focal length or model trajectory control.'}}}
put(OUT / 'control-config.json', config)

native = run(MODULE / 'scripts/vpc.py', 'validate', OUT / 'native-av-ir.json')
put(EV / 'native-av-validation-command.json', native)
assert native['returncode'] == 0, native['stderr'] or native['stdout']
valid = json.loads(native['stdout'])
put(EV / 'native-av-validation.json', {'command': 'locked scripts/vpc.py validate',
                                      'status': valid['status'],
                                      'diagnostics': valid['diagnostics'],
                                      'avir_sha256': sha(OUT / 'native-av-ir.json'),
                                      'adapter_status': report['status'],
                                      'losses': len(report['losses'])})
print(json.dumps({'status': valid['status'], 'avir_sha256': sha(OUT / 'native-av-ir.json'),
                  'boundary_rows': len(sample_rows), 'promotion_diff_count': len(changes)},
                 ensure_ascii=False))
