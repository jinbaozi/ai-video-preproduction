"""Explicit final editing dispatch; a handoff is never an executed edit."""
from pathlib import Path

from .assembly import assemble_ffmpeg
from .v5_modules import digest_file, read


def execute_edit(kernel, edl, output, spec, *, core_root=None, backend='portable-ffmpeg',
                 authorization=None, usage='personal-noncommercial'):
    required = kernel.project.get('editing_backend', 'ffmpeg')
    if required == 'jianying-headless':
        from .jianying import assemble_jianying
        return assemble_jianying(edl, output, spec, core_root=core_root, backend=backend,
                                 authorization=authorization, usage=usage)
    if core_root or authorization:
        raise ValueError('Jianying arguments cannot silently change the frozen editing backend')
    return assemble_ffmpeg(edl, output, spec)


def verify_editing_record(kernel, record):
    """Re-read editable project and plan evidence, rather than accepting a tool label."""
    editing = record.get('editing')
    if kernel.project.get('editing_backend') != 'jianying-headless' and editing is None:
        return
    if record.get('tool') != 'jianying' or not isinstance(editing, dict):
        raise ValueError('Required Jianying final editing has not run')
    from .jianying import PINNED_COMMIT
    if editing.get('core_commit') != PINNED_COMMIT:
        raise ValueError('Editing core is not the reviewed pinned commit')
    if editing.get('backend') not in ('portable-ffmpeg', 'native'):
        raise ValueError('Editing backend is unknown')
    if editing.get('native_editable') is not (editing['backend'] == 'native'):
        raise ValueError('Portable project cannot claim a native Jianying draft')
    files = editing.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('Editable timeline evidence is missing')
    by_role = {}
    verified_files = {}
    for item in files:
        path = Path(item['path'])
        if not path.is_absolute():
            path = kernel.path(item['path'])
        path=path.resolve()
        if not path.is_file() or digest_file(path) != item.get('sha256'):
            raise ValueError('Editing evidence is missing or changed: ' + str(path))
        role=item.get('role')
        if role in ('project','plan','receipt','adapter-manifest') and role in by_role:
            raise ValueError('Editing evidence duplicates a required role')
        by_role[role]=path
        if path in verified_files:raise ValueError('Editing evidence contains duplicate paths')
        verified_files[path]=item['sha256']
    if not {'project', 'plan', 'receipt', 'adapter-manifest'} <= set(by_role):
        raise ValueError('Editing project, plan, execution receipt and adapter manifest are all required')
    from .jianying import canonical_json_sha256, build_headless_plan
    manifest=read(by_role['adapter-manifest'])
    if (manifest.get('schema')!='jianying-adapter-manifest/1.0' or
            manifest.get('executor')!='jianying-headless' or manifest.get('core_commit')!=PINNED_COMMIT or
            manifest.get('backend')!=editing['backend']):
        raise ValueError('Editing adapter manifest identity differs')
    if manifest.get('edl')!=record.get('edl') or manifest.get('edl_sha256')!=canonical_json_sha256(record.get('edl')):
        raise ValueError('Editing manifest EDL differs from the current assembly')
    frozen=kernel.path('runtime/production/delivery-manifest.json')
    if not frozen.is_file():raise ValueError('Editing requires the frozen output specification')
    spec=read(frozen)['output_spec']
    if manifest.get('spec')!=spec or manifest.get('spec_sha256')!=canonical_json_sha256(spec):
        raise ValueError('Editing manifest spec differs from frozen delivery')
    if not record.get('output_sha256') or manifest.get('output_sha256')!=record['output_sha256']:
        raise ValueError('Editing manifest output differs from current MP4')
    for key,role in (('plan_sha256','plan'),('project_sha256','project'),('receipt_sha256','receipt')):
        if manifest.get(key)!=digest_file(by_role[role]):raise ValueError('Editing manifest differs from '+role)
    for key in ('source_sha256','edl_sha256','spec_sha256','plan_sha256','project_sha256','receipt_sha256','output_sha256'):
        if editing.get(key)!=manifest.get(key):raise ValueError('Editing metadata differs from manifest: '+key)
    sources=[Path(row['source']).resolve() for row in record['edl']]
    sources.extend(Path(row['source']).resolve() for row in spec.get('post_audio',[]))
    if manifest.get('source_sha256')!={str(path):digest_file(path) for path in sources}:
        raise ValueError('Editing manifest source bytes differ from selected media')
    project=read(by_role['project']);receipt=read(by_role['receipt']);plan=read(by_role['plan'])
    native=editing['backend']=='native'
    if project.get('schema')!=('jy14-headless-build/v1' if native else 'jy14-windows-render-build/v1'):
        raise ValueError('Editing project has the wrong build schema')
    if (receipt.get('schema')!=('jy14-native-export/v1' if native else 'jy14-ffmpeg-export/v2') or
            receipt.get('status')!='encoded-and-decoded' or receipt.get('full_decode_passed') is not True or
            receipt.get('source_build_unchanged') is not True or receipt.get('output_sha256')!=record['output_sha256']):
        raise ValueError('Editing export receipt does not bind the current checked output')
    if not native and (receipt.get('backend')!='windows-ffmpeg' or receipt.get('native_editable_draft') is not False):
        raise ValueError('Portable editing receipt claims a different backend')
    expected=build_headless_plan(record['edl'],spec,name=plan.get('name'))
    if plan!=expected:raise ValueError('Executed editing plan differs from frozen trims/audio/spec')
    package=by_role['adapter-manifest'].parent
    expected_files=manifest.get('project_files')
    if not isinstance(expected_files,dict) or not expected_files:
        raise ValueError('Editing project file manifest is empty')
    for relative,sha in expected_files.items():
        component=Path(relative)
        if component.is_absolute() or '..' in component.parts:
            raise ValueError('Editing project file escapes package')
        path=(package/component).resolve()
        if not path.is_relative_to(package.resolve()) or verified_files.get(path)!=sha:
            raise ValueError('Editing project inventory differs from manifest')


def snapshot_editing_record(kernel, assembly_id, editing):
    """Retain one project-owned editable package with its relative layout intact."""
    import copy
    import os
    result=copy.deepcopy(editing)
    sources=[Path(item['path']).resolve() for item in editing['files']]
    common=Path(os.path.commonpath([str(path.parent) for path in sources]))
    for source,item in zip(sources,result['files']):
        if digest_file(source)!=item['sha256']:raise ValueError('Editing artifact changed before snapshot')
        uri='runtime/production/editing/'+assembly_id+'/'+source.relative_to(common).as_posix()
        kernel.write(uri,source.read_bytes())
        item['path']=kernel.path(uri).relative_to(kernel.root).as_posix()
    return result
