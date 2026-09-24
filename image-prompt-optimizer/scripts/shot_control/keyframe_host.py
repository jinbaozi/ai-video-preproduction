"""Freeze host inputs and receive local output; never execute or impersonate a host."""
from copy import deepcopy
from pathlib import Path
import os
import shutil
import tempfile

from .common import confined, digest, read, schema_check, sha, write
from .keyframes import check_request
from .media_probe import probe
from .package import recipe, verify_package, same_json_value
from .asset_usage import compatible


def _publish(out, writer):
    out = Path(out).resolve()
    if out.exists(): raise ValueError('Use a new output directory')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.keyframe-', dir=out.parent) as tmp:
        writer(Path(tmp))
        if out.exists(): raise ValueError('Output appeared during preparation')
        os.rename(tmp, out)


def _order(request):
    values = ([request['base_asset_id']] if request['generation_mode'] == 'edit' else []) + request['master_anchors']
    return list(dict.fromkeys(values))


def _uses(bundle, request, artifact_id):
    if artifact_id in request['master_anchors']: raise ValueError('Output cannot replace a master anchor')
    uses = []
    for control in bundle['config']['controls']:
        if artifact_id not in control['artifact_ids'] or request['shot_id'] not in control['shot_ids']: continue
        if not compatible({'kind':'image', 'role':'clean_keyframe'}, control):
            raise ValueError('Output artifact has an incompatible control channel')
        at = request['at_ms']
        use = {'control_id':control['id'], 'shot_id':request['shot_id'], 'start_ms':at, 'end_ms':at,
               'recipe_sha256':recipe(bundle['ir'], bundle['config'], control, request['shot_id'], 'clean_keyframe', at, at, frames=bundle['frames'])}
        if control['channel'] == 'image_reference':
            scope = control.get('reference_scopes', {}).get(request['shot_id'])
            if scope is None or not scope['start_ms'] <= at <= scope['end_ms']:
                raise ValueError('Event image_reference output requires an explicit frozen reference scope containing its event')
            use['reference_scope'] = deepcopy(scope)
        uses.append(use)
    if not uses: raise ValueError('Output artifact must be declared for this shot in the frozen controls')
    return uses


def _stage_data(root, artifact_id):
    bundle = verify_package(root/'control-package')
    request = read(root/'request.json')
    check = check_request(request, root/'control-package', root/'anchors.json')
    if check['status'] == 'BLOCKED': raise ValueError('Host input check blocked: '+str(check['reasons']))
    if not (root/'prompt.txt').read_text(encoding='utf-8').strip(): raise ValueError('Empty host prompt')
    anchors = read(root/'anchors.json')
    assets = {a['id']:a for a in anchors['artifacts']}
    order = _order(request)
    if set(assets) != set(order): raise ValueError('Unexpected or missing staged input')
    inputs = []
    for i, ident in enumerate(order):
        a = assets[ident]
        path = confined(root, a['path'])
        expected = f'inputs/{i:03d}/{path.name}'
        if a['path'] != expected: raise ValueError('Staged input order/path mismatch')
        inputs.append({'asset_id':ident, 'path':expected, 'sha256':sha(path),
                       'role':a['role'], 'edit_base':ident == request['base_asset_id']})
    return {'schema':'keyframe-host-stage/0.1', 'status':'HOST_INPUTS_FROZEN',
            'request_sha256':digest(request), 'prompt_sha256':sha(root/'prompt.txt'),
            'package_sha256':sha(root/'control-package/package-manifest.json'),
            'artifact_id':artifact_id, 'inputs':inputs, 'uses':_uses(bundle, request, artifact_id),
            'host_execution':'NOT_RUN', 'visual_review':'NOT_RUN', 'submitted':False}


def _seal(root, name):
    files = {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name != name}
    write(root/name, {'schema':'keyframe-files/0.1', 'files':files})


def _files(root, name, required):
    manifest = read(root/name)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} - {name}
    if set(manifest) != {'schema','files'} or manifest['schema'] != 'keyframe-files/0.1' or set(manifest['files']) != required or actual != required:
        raise ValueError('Incomplete or unexpected keyframe file set')
    for path, expected in manifest['files'].items():
        if sha(confined(root, path)) != expected: raise ValueError('Keyframe file changed: '+path)


def verify_stage(root):
    root = Path(root).resolve()
    recorded = read(root/'stage.json')
    if not isinstance(recorded.get('artifact_id'), str) or not recorded['artifact_id'].strip():
        raise ValueError('Output artifact ID required')
    expected = _stage_data(root, recorded['artifact_id'])
    if not same_json_value(expected, recorded): raise ValueError('Frozen host stage differs from source inputs')
    files = {'stage.json', 'request.json', 'prompt.txt', 'anchors.json', 'control-package/package-manifest.json'}
    files.update('control-package/'+p for p in read(root/'control-package/package-manifest.json')['files'])
    files.update(i['path'] for i in expected['inputs'])
    _files(root, 'stage-manifest.json', files)
    return expected


def stage(package, request_path, artifacts, prompt, artifact_id, out):
    bundle = verify_package(package)
    request = read(request_path)
    check = check_request(request, package, artifacts)
    if check['status'] == 'BLOCKED': raise ValueError('Host input check blocked: '+str(check['reasons']))
    _uses(bundle, request, artifact_id)
    source = Path(artifacts).resolve()
    assets = {a['id']:a for a in read(source)['artifacts']}

    def create(root):
        package_root = Path(package).resolve()
        for name in ['package-manifest.json', *read(package_root/'package-manifest.json')['files']]:
            dest = confined(root/'control-package', name); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(confined(package_root, name), dest)
        write(root/'request.json', request)
        shutil.copyfile(prompt, root/'prompt.txt')
        selected = []
        for index, ident in enumerate(_order(request)):
            a = deepcopy(assets[ident]); original = confined(source.parent, a['path'])
            dest = root/'inputs'/f'{index:03d}'/original.name
            dest.parent.mkdir(parents=True); shutil.copyfile(original, dest)
            a['path'] = dest.relative_to(root).as_posix(); selected.append(a)
        # Preserve invalidations: copying an anchor must not revive an invalidated use.
        manifest = read(source)
        write(root/'anchors.json', {**manifest, 'artifacts':selected})
        write(root/'stage.json', _stage_data(root, artifact_id))
        _seal(root, 'stage-manifest.json')
        verify_stage(root)
    _publish(out, create)
    return {'status':'HOST_INPUTS_FROZEN', 'out':str(Path(out).resolve()), 'host_execution':'NOT_RUN', 'submitted':False}


def _result(root):
    stage_root = root/'stage'; frozen = verify_stage(stage_root)
    host = read(root/'host-result.json'); schema_check(host, 'keyframe-host-result')
    if host['stage_sha256'] != sha(stage_root/'stage-manifest.json') or host['prompt_sha256'] != frozen['prompt_sha256'] or host['input_sha256'] != [i['sha256'] for i in frozen['inputs']]:
        raise ValueError('Host assertion differs from frozen stage, prompt or ordered inputs')
    media = root/'output'/host['output_filename']
    if Path(host['output_filename']).name != host['output_filename'] or host['output_filename'] in ('.','..'):
        raise ValueError('Host output filename must be a basename')
    info = probe(media)
    if info['detected_kind'] != 'image' or info['sha256'] != host['output_sha256']:
        raise ValueError('Returned output must be the hash-bound still image')
    info['path'] = media.relative_to(root).as_posix()
    request = read(stage_root/'request.json')
    technical_issues = []
    aspect = request['camera_state']['output_aspect']
    if abs(info['display_width']-aspect*info['display_height']) > max(1, aspect):
        technical_issues.append('OUTPUT_ASPECT_MISMATCH')
    if info['sample_aspect_ratio'] not in (None, 'N/A', '1:1'):
        technical_issues.append('NON_SQUARE_PIXELS')
    asset = {'id':frozen['artifact_id'], 'path':info['path'], 'sha256':info['sha256'],
             'source_sha256':request['source']['sha256'], 'kind':'image', 'role':'clean_keyframe',
             'uses':frozen['uses'], 'review':None, 'binding':None}
    review_status = 'NOT_RUN'
    if (root/'visual-review.json').exists():
        review = read(root/'visual-review.json'); schema_check(review, 'keyframe-image-review')
        if review['sha256'] != info['sha256'] or review['stage_sha256'] != host['stage_sha256']:
            raise ValueError('Visual review is for a different output or request')
        criteria = list(dict.fromkeys(request['acceptance'] + (request.get('edit_delta') or {}).get('acceptance', [])))
        if [c['criterion'] for c in review['checks']] != criteria:
            raise ValueError('Visual review must cover every frozen acceptance criterion in order')
        results = {c['result'] for c in review['checks']}
        review_status = 'FAIL' if 'FAIL' in results else 'UNDETERMINED' if 'UNDETERMINED' in results else 'PASS'
        if technical_issues: review_status = 'FAIL'
        if review_status != 'UNDETERMINED':
            asset['review'] = {'sha256':info['sha256'], 'uses_sha256':digest(asset['uses']),
                               'reviewer':review['reviewer'], 'result':review_status,
                               'checks':[c['criterion']+' — '+c['result']+': '+c['evidence'] for c in review['checks']] + technical_issues}
    anchors = read(stage_root/'anchors.json')
    artifacts = []
    for a in anchors['artifacts']:
        if a['id'] == asset['id']: continue  # The old edit base stays immutable inside stage/.
        artifacts.append({**a, 'path':'stage/'+a['path']})
    manifest = {**anchors, 'artifacts':artifacts+[asset]}
    schema_check(manifest, 'control-artifacts')
    receipt = {'schema':'keyframe-received/0.1', 'status':'MEDIA_RECEIVED', 'stage_sha256':host['stage_sha256'],
               'host_assertion_sha256':sha(root/'host-result.json'), 'media':info, 'visual_review':review_status,
               'technical_issues':technical_issues,
               'provenance':'HOST_ASSERTION_NOT_INDEPENDENT_EXECUTION_PROOF', 'submitted':False,
               'video_execution':'NOT_RUN'}
    return receipt, manifest


def verify_received(root):
    root = Path(root).resolve()
    receipt, artifacts = _result(root)
    if not same_json_value(read(root/'receipt.json'), receipt) or not same_json_value(read(root/'artifact-manifest.json'), artifacts):
        raise ValueError('Received keyframe derivation differs from frozen inputs or review')
    required = {'host-result.json', 'receipt.json', 'artifact-manifest.json', receipt['media']['path'], 'stage/stage-manifest.json'}
    required.update('stage/'+p for p in read(root/'stage/stage-manifest.json')['files'])
    if (root/'visual-review.json').exists(): required.add('visual-review.json')
    _files(root, 'received-manifest.json', required)
    return {'status':'VERIFIED_RECEIVED_KEYFRAME', 'visual_review':receipt['visual_review'],
            'provenance':receipt['provenance'], 'submitted':False}


def receive(stage_path, media, host_result, out, review=None):
    stage_path = Path(stage_path).resolve()
    if Path(out).resolve().is_relative_to(stage_path): raise ValueError('Output cannot be inside its frozen stage')
    verify_stage(stage_path)
    host = read(host_result); schema_check(host, 'keyframe-host-result')
    if host['output_filename'] != Path(media).name: raise ValueError('Host output filename mismatch')
    def create(root):
        shutil.copytree(stage_path, root/'stage')
        (root/'output').mkdir(); shutil.copyfile(media, root/'output'/Path(media).name)
        shutil.copyfile(host_result, root/'host-result.json')
        if review is not None: shutil.copyfile(review, root/'visual-review.json')
        receipt, artifacts = _result(root)
        write(root/'receipt.json', receipt); write(root/'artifact-manifest.json', artifacts)
        _seal(root, 'received-manifest.json')
        verify_received(root)
    _publish(out, create)
    return {**verify_received(out), 'status':'MEDIA_RECEIVED', 'out':str(Path(out).resolve())}
