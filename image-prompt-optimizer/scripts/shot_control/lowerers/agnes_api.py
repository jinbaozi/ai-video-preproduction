"""Agnes API draft payloads. Other backends must not enter this adapter."""


def require_agnes(capability):
    if capability['backend'] != 'agnes_api_draft':
        raise ValueError('Joint API lowering is not integrated for this exact target')
    return capability
