#!/usr/bin/env python3
"""Update probe_passed or quality_validated only from a frozen experiment result."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply(protocol_path, registry_path):
    protocol = json.loads(Path(protocol_path).read_text())
    if protocol.get('results') != 'PASS':
        raise SystemExit('Refusing to update capabilities: experiment results are ' + protocol.get('results', 'MISSING'))
    if protocol.get('status') != 'COMPLETE':
        raise SystemExit('Refusing to update capabilities before the protocol is COMPLETE')
    registry = json.loads(Path(registry_path).read_text())
    for route in registry['routes']:
        if route['model'] == protocol['entry'] and route['surface'] == protocol['surface']:
            route['probe_passed'] = True
            if protocol.get('quality_gate_met') is True:
                route['quality_validated'] = True
    Path(registry_path).write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return registry


if __name__ == '__main__':
    apply(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ROOT/'registries/control-capabilities.json')
