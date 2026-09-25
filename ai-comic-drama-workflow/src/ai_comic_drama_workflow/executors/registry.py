"""New entries stay unavailable until they pass their own probe and quality check."""

IMPLEMENTED = {'agnes_api_draft': 'agnes_api'}


def require_execution(profile):
    backend = profile.get('backend')
    if backend not in IMPLEMENTED:
        raise ValueError('TEXT_ADAPTER_ONLY: execution is not integrated for ' + str(backend))
    if not profile.get('probe_passed') or not profile.get('quality_validated'):
        raise ValueError('Entry requires an independent execution probe and quality validation')
    return IMPLEMENTED[backend]
