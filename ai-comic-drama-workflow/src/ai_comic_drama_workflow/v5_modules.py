"""Locked, self-contained professional modules. No sibling-directory runtime imports."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

MODULES = ('screenplay-grammar', 'director-grammar', 'production-design-grammar', 'storyboard-grammar',
           'video-prompt-compiler', 'image-prompt-optimizer')
LEGACY_MODULES = tuple(name for name in MODULES if name != 'screenplay-grammar')
ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / 'SKILL.md').exists():
    ROOT = Path(sys.prefix) / 'share/ai-comic-drama-workflow'


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def verify_archive(archive, expected=None):
    archive = Path(archive)
    if expected and digest_file(archive) != expected:
        raise ValueError(f'Module archive hash differs: {archive.name}')
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if not names or len(names) != len(set(names)) or bundle.testzip():
            raise ValueError('Invalid or duplicate archive members')
        roots = set()
        for item in bundle.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename:
                raise ValueError('Unsafe module archive path')
            if (item.external_attr >> 16) & 0o170000 != 0o100000:
                raise ValueError('Module archive must contain regular files only')
            roots.add(path.parts[0])
        if len(roots) != 1 or next(iter(roots)) + '/SKILL.md' not in names:
            raise ValueError('Module must have one Skill root')
        return next(iter(roots)), {name: hashlib.sha256(bundle.read(name)).hexdigest() for name in names}


def default_lock(root=ROOT):
    lock = read(Path(root) / 'modules.lock.json')
    if set(lock['modules']) not in (set(MODULES), set(LEGACY_MODULES)):
        raise ValueError('Expected a six-module lock or a preserved legacy five-module lock')
    return lock


def verify_module(archive,name,item):
    actual,members=verify_archive(archive,item['sha256'])
    if actual!=name:raise ValueError('Locked module name differs from archive root')
    with zipfile.ZipFile(archive) as bundle:
        version=re.search(r'^  version:\s*[\"\']?([^\"\'\n]+)',bundle.read(name+'/SKILL.md').decode(),re.M)
    if not version or version.group(1).strip()!=item['version']:
        raise ValueError('Locked module version differs from Skill metadata')
    return members


def module_path(project, name, root=ROOT):
    if name not in MODULES:
        raise ValueError(f'Unknown professional module: {name}')
    project, root = Path(project).resolve(), Path(root).resolve()
    item = read(project / 'modules.lock.json')['modules'][name]
    # Projects retain their archive bytes, so a later Skill upgrade cannot change them.
    archive = project / 'runtime/module-archives' / (item['sha256'] + '.skill')
    if not archive.exists():
        bundled = root / 'assets/bundled-skills' / (name + '.skill')
        verify_archive(bundled, item['sha256'])
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundled, archive)
    members = verify_module(archive,name,item)
    cache = project / 'runtime/modules' / item['sha256']
    module = cache / name
    if not cache.resolve().is_relative_to(project) or module.is_symlink():
        raise ValueError('Module cache must stay inside the project')
    if module.exists():
        actual = {str(p.relative_to(cache)): digest_file(p) for p in module.rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
        if actual != members or any(p.is_symlink() for p in module.rglob('*')):
            raise ValueError(f'Cached module was modified: {name}')
    else:
        cache.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(cache)
    return module


def load_python(module, script):
    path = Path(module) / 'scripts' / script
    spec = importlib.util.spec_from_file_location('v5_module_' + digest_file(path), path)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


def native_validate(kind, path, modules):
    names = {'director': ('director-grammar', 'dg.py', 'validate'),
             'screenplay': ('screenplay-grammar', 'sg.py', 'validate'),
             'art': ('production-design-grammar', 'art_compile.py', 'validate'),
             'storyboard': ('storyboard-grammar', 'storyboard.py', 'inspect'),
             'avir': ('video-prompt-compiler', 'vpc.py', 'validate')}
    if kind not in names:
        return {'status': 'VALID'}
    name, script, command = names[kind]
    args = [sys.executable, str(modules(name) / 'scripts' / script), command, str(Path(path).resolve())]
    if kind == 'screenplay': args.append('--final')
    result = subprocess.run(args, capture_output=True, text=True)
    try:
        report = json.loads(result.stdout)
    except ValueError as error:
        raise ValueError(f'{kind} validator failed: {result.stderr or result.stdout}') from error
    if result.returncode:
        raise ValueError(f'{kind} native validation failed: {json.dumps(report, ensure_ascii=False)}')
    return report
