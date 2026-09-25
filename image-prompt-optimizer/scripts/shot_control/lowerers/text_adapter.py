"""Control package without an execution payload."""
from .agnes_api import require_agnes


def text_adapter_package(bundle, target, mode, capability, scope):
    try:
        require_agnes(capability)
    except ValueError:
        pass
    else:
        raise ValueError('Agnes targets use the API adapter')
    ir = bundle['ir']
    request = {
        'id': 'REQUEST_001', 'scope': scope, 'parameters': {'model': capability.get('model'), 'mode': mode},
        'prompt': None, 'status': 'TEXT_ADAPTER_ONLY', 'reasons': ['TEXT_ADAPTER_ONLY'],
        'payload_draft': None, 'execution_payload': None, 'submitted': False, 'runnable': False,
        'media_acceptance': 'NOT_RUN',
        'primary_obligations': [{'requirement_id': c['id'], 'channel': c['channel'], 'acceptance': c.get('acceptance')}
                                for c in ir['contract']],
    }
    return {
        'schema': 'joint-control-compile/0.1', 'target': target, 'mode': mode,
        'capability_snapshot': capability, 'scope': scope, 'status': 'TEXT_ADAPTER_ONLY',
        'reasons': ['TEXT_ADAPTER_ONLY'], 'requests': [request], 'execution_payload': None,
        'submitted': False, 'runnable': False, 'media_acceptance': 'NOT_RUN',
    }
