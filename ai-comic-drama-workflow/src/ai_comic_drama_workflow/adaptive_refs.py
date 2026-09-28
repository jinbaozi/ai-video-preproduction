"""Use accepted local geometry as image-host inputs, never video/identity assets."""
from pathlib import Path
from .v5_modules import digest_file
from .v5_adapters import digest


def index(root, control):
    root = Path(root).resolve()
    if control.get('status') != 'READY':
        raise ValueError('Current adaptive controls are not ready')
    def contained(value):
        path = (root/value).resolve()
        if not path.is_relative_to(root): raise ValueError('Control reference escapes project')
        return path
    package = contained(control['uri'])
    if digest_file(package/'package-manifest.json') != control['package_manifest_sha256']:
        raise ValueError('Accepted control package changed')
    materials = control['materials']
    if (materials.get('status') != 'CONTROL_MATERIALS_VERIFIED'
            or digest(materials) != control['materials_sha256']):
        raise ValueError('Accepted control materials changed')
    result = {}
    for sid, renders in materials['renders'].items():
        for render in renders:
            for frame in render['frames']:
                path = contained(frame['path'])
                if digest_file(path) != frame['sha256']:
                    raise ValueError('Control reference bytes changed')
                key = 'CONTROL_'+digest([sid,frame['at_ms'],frame['sha256']])[:24]
                result[key] = {'key':key, 'uri':path.relative_to(root).as_posix(),
                    'sha256':frame['sha256'], 'shot_id':sid, 'at_ms':frame['at_ms'], 'entity_id':None,
                    'purpose':'geometry and camera layout only; neutral proxy is not identity, clothing, lighting or final appearance'}
    return result


def for_panel(root, control, brief, references=None):
    row = next((r for r in control.get('adaptive',{}).get('shots',[]) if r['shot_id']==brief['shot_id']),None)
    if row is None: raise ValueError('Missing shot-scoped adaptive plan')
    if not {'proxy_keyframes','clay_previs'}.intersection(row['required_assets']): return []
    at = brief['spatial_dependency']['at_ms']
    matches = [r for r in (references if references is not None else index(root,control)).values()
               if r['shot_id']==brief['shot_id'] and r['at_ms']==at]
    if not matches: raise ValueError(f"Missing exact geometry frame for {brief['shot_id']} at {at} ms; no nearest-frame substitution")
    if len({r['sha256'] for r in matches})!=1: raise ValueError('Conflicting geometry frames for one panel')
    return matches[:1]


def binding_valid(root, control, binding):
    try:
        ref = index(root,control).get(binding['key'])
        return bool(ref and ref['sha256']==binding['sha256'])
    except (KeyError,ValueError,OSError,TypeError):
        return False
