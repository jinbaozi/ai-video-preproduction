"""Shared native obligation types and media consumption compatibility."""
OBLIGATION_TYPES = {'prompt':'prompt', 'parameter':'native_parameter',
                    'reference':'visual_reference', 'post':'post_production'}
CHANNEL_ROLES = {
    'keyframe_input': ('image', {'identity', 'appearance', 'style', 'scene', 'clean_keyframe'}),
    'first_frame': ('image', {'clean_keyframe'}),
    'last_frame': ('image', {'clean_keyframe'}),
    'image_reference': ('image', {'identity', 'appearance', 'style', 'scene', 'clean_keyframe', 'performance'}),
    'clay_video_reference': ('video', {'clay', 'performance'}),
    'audio_reference': ('audio', {'audio'}),
}


def compatible(asset, control):
    kind, roles = CHANNEL_ROLES.get(control['channel'], (None, set()))
    return asset['kind'] == kind and asset['role'] in roles


def reference_scope_matches(asset, control, use):
    point_reference = (control['channel'] == 'image_reference' and asset['role'] == 'clean_keyframe'
                       and use['start_ms'] == use['end_ms'])
    if not point_reference: return 'reference_scope' not in use
    scope = control.get('reference_scopes', {}).get(use['shot_id'])
    return bool(scope and use.get('reference_scope') == scope
                and scope['start_ms'] <= use['start_ms'] <= scope['end_ms'])
