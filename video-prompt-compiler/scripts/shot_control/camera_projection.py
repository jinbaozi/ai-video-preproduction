"""Pinhole projection: world right/up/depth, screen right/down. No occlusion claim."""
import math


def vector(value):
    if not isinstance(value, list) or len(value) != 3 or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ValueError('Expected a finite three-vector')
    return value


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def unit(v):
    length = math.sqrt(dot(v, v))
    if length < 1e-10:
        raise ValueError('Degenerate camera basis')
    return [x/length for x in v]


def project(point, position, forward, vertical_fov_deg, aspect, roll_deg=0, crop=None):
    vector(point); vector(position); vector(forward)
    if not all(math.isfinite(x) for x in (vertical_fov_deg, aspect, roll_deg)) or not 0 < vertical_fov_deg < 180 or aspect <= 0:
        raise ValueError('Invalid camera intrinsics')
    f = unit(forward)
    right = unit(cross([0, 1, 0], f))
    up = cross(f, right)
    angle = math.radians(roll_deg)
    r = [a*math.cos(angle)+b*math.sin(angle) for a, b in zip(right, up)]
    u = [-a*math.sin(angle)+b*math.cos(angle) for a, b in zip(right, up)]
    delta = sub(point, position); depth = dot(delta, f)
    if depth <= 1e-8:
        return {'status': 'BEHIND_CAMERA', 'xy': None, 'depth': depth}
    scale = math.tan(math.radians(vertical_fov_deg)/2)*depth
    x, y = .5 + dot(delta, r)/(2*scale*aspect), .5 - dot(delta, u)/(2*scale)
    if crop is not None:
        if len(crop) != 4 or not all(math.isfinite(v) for v in crop) or min(crop[:2]) < 0 or min(crop[2:]) <= 0 or crop[0]+crop[2] > 1 or crop[1]+crop[3] > 1:
            raise ValueError('Invalid normalized crop')
        x, y = (x-crop[0])/crop[2], (y-crop[1])/crop[3]
    return {'status': 'IN_FRAME' if 0 <= x <= 1 and 0 <= y <= 1 else 'OUTSIDE_FRAME',
            'xy': [x, y], 'depth': depth, 'occlusion': 'NOT_EVALUATED'}
