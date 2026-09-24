"""Shared native obligation types and media consumption compatibility."""
OBLIGATION_TYPES = {'prompt':'prompt', 'parameter':'native_parameter',
                    'reference':'visual_reference', 'post':'post_production'}
CHANNEL_ROLES = {
    'first_frame': ('image', {'clean_keyframe'}),
    'last_frame': ('image', {'clean_keyframe'}),
    'image_reference': ('image', {'identity', 'appearance', 'style', 'scene', 'clean_keyframe', 'performance'}),
    'clay_video_reference': ('video', {'clay', 'performance'}),
    'audio_reference': ('audio', {'audio'}),
}


def compatible(asset, control):
    kind, roles = CHANNEL_ROLES.get(control['channel'], (None, set()))
    return asset['kind'] == kind and asset['role'] in roles
