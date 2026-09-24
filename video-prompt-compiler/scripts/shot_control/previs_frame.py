"""Render one frozen event as neutral geometry, without inventing intervening motion."""
from pathlib import Path
import shutil
from .common import read, write, sha, digest, schema_check, confined
from .package import verify_package
from .previs import derive, _render_plan, validate_readback
from .media_probe import probe
from .keyframe_host import _uses


def _inputs(package, keyframe_id, artifact_id):
    bundle = verify_package(package)
    request = next((r for r in bundle['requests'] if r['id']==keyframe_id), None)
    if request is None: raise ValueError('Unknown frozen keyframe')
    if artifact_id in {a['id'] for a in bundle['ir']['assets']}:
        raise ValueError('Proxy cannot replace a native reference asset')
    uses = _uses(bundle, request, artifact_id)
    return derive(bundle, request['shot_id'], keyframe_id), uses


def _artifacts(plan, uses, artifact_id, out):
    return {'schema':'control-artifacts/0.2', 'submitted':False, 'artifacts':[{
        'id':artifact_id, 'path':'keyframe.png', 'sha256':sha(out/'keyframe.png'),
        'source_sha256':plan['source_sha256'], 'kind':'image', 'role':'clean_keyframe',
        'uses':uses, 'review':None, 'binding':None}]}


def render(package, keyframe_id, artifact_id, out, blender):
    plan, uses = _inputs(package, keyframe_id, artifact_id)
    out = Path(out).resolve()
    checks, readback, script = _render_plan(plan, out, blender)
    shutil.copyfile(out/'frames/000000.png', out/'keyframe.png')
    info = probe(out/'keyframe.png')
    if info['detected_kind'] != 'image' or [info['width'],info['height']] != plan['geometry']['resolution']:
        raise ValueError('Rendered keyframe dimensions or kind mismatch')
    write(out/'artifact-manifest.json', _artifacts(plan, uses, artifact_id, out))
    receipt = {'schema':'previs-keyframe-receipt/0.1', 'status':'RENDERED_LOCAL_KEYFRAME',
        'keyframe_id':keyframe_id, 'artifact_id':artifact_id, 'source_package':str(Path(package).resolve()),
        'source_package_sha256':sha(Path(package)/'package-manifest.json'), 'plan_sha256':digest(plan),
        'renderer_script_sha256':sha(script), 'renderer':readback['renderer'], 'projection_check':checks,
        'media':{**info,'path':'keyframe.png'}, 'visual_review':'NOT_RUN', 'model_execution':'NOT_RUN', 'submitted':False}
    write(out/'render-receipt.json',receipt)
    write(out/'render-manifest.json', {'schema':'previs-keyframe-manifest/0.1', 'files':{
        p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
    verify(out)
    return {'status':'RENDERED_LOCAL_KEYFRAME', 'out':str(out), 'projection_check':checks,
            'appearance':'NEUTRAL_CLAY', 'visual_review':'NOT_RUN', 'model_execution':'NOT_RUN'}


def verify(out):
    out = Path(out).resolve(); manifest = read(out/'render-manifest.json')
    required = {'render-plan.json','render-receipt.json','blender-readback.json','scene.blend','blender.log',
                'frames/000000.png','keyframe.png','artifact-manifest.json'}
    if manifest.get('schema') != 'previs-keyframe-manifest/0.1' or set(manifest['files']) != required:
        raise ValueError('Incomplete keyframe render file set')
    for name, expected in manifest['files'].items():
        if sha(confined(out,name)) != expected: raise ValueError('Rendered keyframe changed: '+name)
    receipt = read(out/'render-receipt.json')
    package = Path(receipt['source_package'])
    plan, uses = _inputs(package, receipt['keyframe_id'], receipt['artifact_id'])
    if sha(package/'package-manifest.json') != receipt['source_package_sha256'] or read(out/'render-plan.json') != plan:
        raise ValueError('Stale keyframe render source or plan')
    readback = read(out/'blender-readback.json'); checks = validate_readback(plan,readback)
    info = probe(out/'keyframe.png')
    if info['detected_kind'] != 'image' or [info['width'],info['height']] != plan['geometry']['resolution'] or sha(out/'frames/000000.png') != info['sha256']:
        raise ValueError('Keyframe frame or dimensions mismatch')
    expected = {'schema':'previs-keyframe-receipt/0.1','status':'RENDERED_LOCAL_KEYFRAME',
        'keyframe_id':plan['keyframe_id'],'artifact_id':receipt['artifact_id'],'source_package':str(package.resolve()),
        'source_package_sha256':sha(package/'package-manifest.json'),'plan_sha256':digest(plan),
        'renderer_script_sha256':sha(Path(__file__).with_name('blender_previs.py')),'renderer':readback['renderer'],
        'projection_check':checks,'media':{**info,'path':'keyframe.png'},'visual_review':'NOT_RUN','model_execution':'NOT_RUN','submitted':False}
    if receipt != expected: raise ValueError('Keyframe render receipt mismatch')
    artifacts = read(out/'artifact-manifest.json'); schema_check(artifacts,'control-artifacts')
    if artifacts != _artifacts(plan,uses,receipt['artifact_id'],out): raise ValueError('Keyframe render artifact mapping mismatch')
    return {'status':'VERIFIED_LOCAL_KEYFRAME','projection_check':checks,'visual_review':'NOT_RUN','model_execution':'NOT_RUN'}
