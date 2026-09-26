"""Self-contained deterministic Skill packager, also used by suite builds."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import re
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = ROOT.name
ALLOWED = {'SKILL.md','README.md','requirements.txt','pyproject.toml','agents','scripts','src',
           'schemas','registries','styles','references','templates','presets','examples','tests',
           'assets','workflow-v5.json','workflow-v6.json','modules.lock.json','suite.json'}
EXCLUDED = {'.git','.venv','__pycache__','outputs','output','dist','dists','.local-tests','.DS_Store'}


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()


def files():
    result=[]
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if rel.parts[0] not in ALLOWED or set(rel.parts)&EXCLUDED or path.suffix in ('.pyc','.pyo'):
            continue
        if path.is_symlink():raise ValueError('Release source cannot contain symlinks')
        if path.is_file():result.append(path)
    return result


def verify(out):
    out=Path(out)
    archive=out if out.suffix=='.skill' else out/(NAME+'.skill')
    manifest=json.loads(archive.with_suffix('.skill-manifest.json').read_text())
    checksum=sha256(archive.read_bytes()).hexdigest()
    if manifest['archive_sha256']!=checksum or archive.with_suffix('.skill.sha256').read_text()!=f'{checksum}  {archive.name}\n':
        raise ValueError('Archive checksum differs')
    with zipfile.ZipFile(archive) as z:
        if manifest['name']!=NAME or manifest['archive']!=archive.name or manifest['file_count']!=len(z.namelist()) or z.testzip() or len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(manifest['files']):
            raise ValueError('Invalid archive member list or ZIP CRC')
        version=re.search(r'^  version:\s*[\"\']?([^\"\'\n]+)',z.read(NAME+'/SKILL.md').decode(),re.M)
        if not version or version.group(1).strip()!=manifest['version']:raise ValueError('Manifest version differs from Skill')
        for item in z.infolist():
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or path.parts[0]!=NAME:
                raise ValueError('Unsafe archive path')
            if (item.external_attr>>16)&0o170000!=0o100000:raise ValueError('Non-regular archive member')
            data=z.read(item.filename)
            if manifest['files'][item.filename]!={'sha256':sha256(data).hexdigest(),'bytes':len(data)}:
                raise ValueError('Archive member hash differs')
    return {'status':'VERIFIED','archive':str(archive.resolve()),'sha256':checksum,'files':manifest['file_count']}


def build(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    archive=out/(NAME+'.skill')
    match=re.search(r'^  version:\s*[\"\']?([^\"\'\n]+)',(ROOT/'SKILL.md').read_text(),re.M)
    if not match:raise ValueError('Skill metadata.version is required')
    version=match.group(1).strip()
    manifest={'name':NAME,'version':version,'archive':archive.name,'files':{}}
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in files():
            member=NAME+'/'+path.relative_to(ROOT).as_posix();data=path.read_bytes()
            info=zipfile.ZipInfo(member,(1980,1,1,0,0,0));info.create_system=3
            info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data,compresslevel=9)
            manifest['files'][member]={'sha256':sha256(data).hexdigest(),'bytes':len(data)}
    checksum=sha256(archive.read_bytes()).hexdigest()
    manifest.update(file_count=len(manifest['files']),archive_sha256=checksum)
    archive.with_suffix('.skill-manifest.json').write_bytes(encoded(manifest))
    archive.with_suffix('.skill.sha256').write_text(f'{checksum}  {archive.name}\n')
    return verify(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',nargs='?');parser.add_argument('--out');parser.add_argument('--output')
    parser.add_argument('--verify',nargs='?',const='')
    args=parser.parse_args()
    if args.verify is not None:
        result=verify(args.verify or args.out or args.directory or ROOT/'dist')
    else:
        out=Path(args.output).parent if args.output else args.out or args.directory or ROOT/'dist'
        result=build(out)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
