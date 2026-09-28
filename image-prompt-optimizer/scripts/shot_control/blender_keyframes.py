"""Set declared samples to constant keys across legacy and layered Blender actions."""


def constant_keys(action):
    """Never leave Blender's default Bezier interpolation on a baked control plan.

    Capability detection is intentional: legacy actions expose fcurves while
    layered actions store them in strip channelbags. Unknown layouts fail closed.
    This helper has no bpy dependency so both layouts receive unit regression.
    """
    layers = getattr(action, 'layers', None)
    if layers:
        curves = [curve for layer in layers for strip in layer.strips
                  for bag in strip.channelbags for curve in bag.fcurves]
    else:
        curves = list(getattr(action, 'fcurves', ()))
    if not curves:
        raise ValueError('Unsupported or empty Blender action; cannot freeze interpolation')
    for curve in curves:
        for point in curve.keyframe_points:
            point.interpolation = 'CONSTANT'
