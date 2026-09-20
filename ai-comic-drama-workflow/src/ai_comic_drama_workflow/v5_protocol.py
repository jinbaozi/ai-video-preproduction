"""V5 entry schemas are separate from every legacy and professional protocol."""
from jsonschema import Draft202012Validator
from .v5_modules import ROOT, read


def validate_protocol(name, value, root=ROOT):
    schema = read(root / 'schemas' / ('v5-' + name + '.schema.json'))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        error = errors[0]
        raise ValueError(name + ' ' + '/'.join(map(str, error.path)) + ': ' + error.message)
