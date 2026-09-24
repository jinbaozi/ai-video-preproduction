import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sha(path):
    with Path(path).open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
        return digest.hexdigest()


def pointer(value, path):
    if path == '':
        return value
    if not path.startswith('/'):
        raise ValueError('Expected JSON pointer')
    for key in path[1:].split('/'):
        key = key.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def schema_check(value, name):
    from jsonschema import Draft202012Validator
    schema = read(Path(__file__).resolve().parents[2]/'schemas'/f'{name}.schema.json')
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        raise ValueError('; '.join(f'{list(e.path)}: {e.message}' for e in errors))


def confined(base, name):
    base = Path(base).resolve(); path = (base/name).resolve()
    if not path.is_relative_to(base):
        raise ValueError('Artifact path escapes package')
    return path
