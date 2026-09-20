"""Pure scene/time evaluation shared by previews, stills and media checks.

Coordinates are right-handed, Z-up. Renderers consume these evaluated values;
they do not invent independent positions or reinterpret narrative facts.
"""
from __future__ import annotations

import math
from copy import deepcopy
from fractions import Fraction
from typing import Any

from .utils import canonical_json, sha256_bytes

AXES = ("x", "y", "z")


def vector(value: dict) -> tuple[float, float, float]:
    result = tuple(float(value[key]) for key in AXES)
    if not all(math.isfinite(v) for v in result):
        raise ValueError("Coordinates must be finite")
    return result


def point(values) -> dict[str, float]:
    return dict(zip(AXES, values))


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def unit(value):
    length = math.sqrt(dot(value, value))
    if length < 1e-10:
        raise ValueError("Direction must be non-zero")
    return tuple(v / length for v in value)


def world_position(scene: dict, position: dict) -> dict[str, float]:
    values = vector(position)
    system = scene["coordinate_system"]
    if system["units"] == "meters":
        return point(values)
    if system["units"] != "normalized":
        raise ValueError("Qualitative coordinates cannot be evaluated as physical space")
    bounds = system.get("world_bounds")
    if not bounds:
        raise ValueError("Normalized space requires explicit meter-valued world_bounds")
    result = []
    for key, value in zip(AXES, values):
        low, high = map(float, system["bounds"][key])
        start, end = map(float, bounds[key])
        if high <= low or end <= start:
            raise ValueError("Coordinate bounds must have positive extent")
        result.append(start + (value - low) / (high - low) * (end - start))
    return point(result)


def interpolate_quaternion(a: list, b: list, ratio: float) -> list[float]:
    a, b = unit(tuple(a)), unit(tuple(b))
    cosine = dot(a, b)
    if cosine < 0:
        b, cosine = tuple(-v for v in b), -cosine
    if cosine > 0.9995:
        return list(unit(tuple(x + ratio*(y-x) for x, y in zip(a, b))))
    theta = math.acos(max(-1, min(1, cosine)))
    scale = math.sin(theta)
    return [(math.sin((1-ratio)*theta)*x + math.sin(ratio*theta)*y)/scale for x, y in zip(a, b)]


def sample_keyframes(keys: list[dict], time_s: float) -> dict:
    if not keys:
        raise ValueError("At least one keyframe is required")
    times = [float(k["time_s"]) for k in keys]
    if times != sorted(set(times)):
        raise ValueError("Keyframe times must be strictly increasing")
    left = keys[0]
    if time_s <= times[0]:
        return deepcopy(left)
    for right in keys[1:]:
        if time_s <= float(right["time_s"]):
            ratio = (time_s-float(left["time_s"]))/(float(right["time_s"])-float(left["time_s"]))
            if left.get("interpolation", "linear") == "hold":
                return deepcopy(right if ratio == 1 else left)
            if left.get("interpolation") == "smoothstep":
                ratio = ratio*ratio*(3-2*ratio)
            result = deepcopy(right if ratio == 1 else left)
            for field in ("position", "target", "head_target"):
                if field in left and field in right:
                    result[field] = point(x + ratio*(y-x) for x, y in zip(vector(left[field]), vector(right[field])))
            for field in ("focal_length_mm", "ortho_scale_m", "focus_distance_m"):
                if field in left and field in right:
                    result[field] = float(left[field]) + ratio*(float(right[field])-float(left[field]))
            if "rotation_quaternion" in left and "rotation_quaternion" in right:
                result["rotation_quaternion"] = interpolate_quaternion(left["rotation_quaternion"], right["rotation_quaternion"], ratio)
            result["joint_targets"] = {}
            for name in left.get("joint_targets", {}).keys() | right.get("joint_targets", {}).keys():
                a = left.get("joint_targets", {}).get(name) or right["joint_targets"][name]
                b = right.get("joint_targets", {}).get(name, a)
                result["joint_targets"][name] = point(x+ratio*(y-x) for x, y in zip(vector(a), vector(b)))
            return result
        left = right
    return deepcopy(left)


def active_events(events: list[dict], time_s: float, duration: float) -> list[dict]:
    def active(event):
        if event.get("time_mode") == "full_shot" or event.get('full_shot') is True:
            return True
        if "time_s" in event:
            return abs(float(event["time_s"])-time_s) < 1e-8
        start, end = float(event["start_s"]), float(event["end_s"])
        return start <= time_s < end or time_s == duration == end
    return [deepcopy(event) for event in events if active(event)]


def camera_at(shot: dict, time_s: float) -> dict:
    keys = []
    for event in shot["camera_track"]:
        value = deepcopy(event)
        value["time_s"] = float(value.get("time_s", value.get("start_s", 0)))
        keys.append(value)
    camera = sample_keyframes(keys, time_s)
    for field in ("position", "target"):
        vector(camera[field])
    unit(subtract(vector(camera["target"]), vector(camera["position"])))
    if camera.get("projection") not in {"perspective", "orthographic"}:
        raise ValueError("Camera requires an explicit projection")
    for field in ("sensor_width_mm", "focal_length_mm"):
        if float(camera.get(field, 0)) <= 0:
            raise ValueError(f"Camera requires positive {field}")
    if camera["projection"] == "orthographic" and float(camera.get("ortho_scale_m", 0)) <= 0:
        raise ValueError("Orthographic camera requires ortho_scale_m")
    return camera


def project_point(camera: dict, position: dict, aspect: float) -> dict:
    origin, target, subject = vector(camera["position"]), vector(camera["target"]), vector(position)
    forward = unit(subtract(target, origin))
    right = unit(cross(forward, vector(camera.get("up", {"x": 0, "y": 0, "z": 1}))))
    up = cross(right, forward)
    relative = subtract(subject, origin)
    depth = dot(relative, forward)
    if camera["projection"] == "orthographic":
        width = float(camera["ortho_scale_m"])
    else:
        width = depth * float(camera["sensor_width_mm"])/float(camera["focal_length_mm"])
    if abs(width) < 1e-10:
        return {"x": None, "y": None, "depth_m": depth, "in_frame": False}
    x, y = 0.5+dot(relative, right)/width, 0.5+dot(relative, up)/(width/aspect)
    return {"x": x, "y": y, "depth_m": depth, "in_frame": depth > 0 and 0 <= x <= 1 and 0 <= y <= 1}


def evaluate_state(scene: dict, shot: dict, time_s: float, *, aspect: float = 16/9, fps: int = 24, _timing_checked=False) -> dict:
    if shot.get('timing'):
        if not _timing_checked:
            from .timing import validate_timing
            shot = validate_timing(shot)
        fps = shot['timing']['fps']
    duration = float(shot["duration_s"])
    if not 0 <= time_s <= duration or fps <= 0:
        raise ValueError("Evaluation time must fall inside the shot")
    camera = camera_at(shot, time_s)
    characters = []
    for track in shot["character_tracks"]:
        state = sample_keyframes(track["trajectory"], time_s)
        state["position"] = world_position(scene, state["position"])
        for name, target in state.get("joint_targets", {}).items():
            state["joint_targets"][name] = world_position(scene, target)
        visible = track["visible_interval"]
        state.update(character_id=track["character_id"],
                     visible=float(visible['start_s']) < float(visible['end_s']) and float(visible["start_s"]) <= time_s <= float(visible["end_s"]),
                     actions=active_events(track.get("action_events", []), time_s, duration),
                     emotions=active_events(track.get("emotion_events", []), time_s, duration))
        state["screen_position"] = project_point(camera, state["position"], aspect)
        characters.append(state)
    frame = Fraction(str(time_s))*fps
    props = []
    prop_tracks = {p['asset_id']: p for p in shot.get('prop_tracks', [])}
    for prop in scene.get('prop_placements', []):
        state = deepcopy(prop)
        if prop['asset_id'] in prop_tracks:
            state.update(sample_keyframes(prop_tracks[prop['asset_id']]['trajectory'], time_s))
        state['position'] = world_position(scene, state['position'])
        props.append(state)
    facts = {"scene_id": scene["scene_id"], "shot_id": shot["shot_id"], "time_s": time_s,
             "frame_time": {"numerator": frame.numerator, "denominator": frame.denominator, "fps": fps},
             "camera": camera, "characters": characters,
             "props": props,
             "audio": active_events(shot.get("audio_track", []), time_s, duration),
             "director": active_events(shot.get("director_track", []), time_s, duration)}
    facts["source_hash"] = sha256_bytes(canonical_json({"scene": scene, "shot": shot}).encode())
    return facts


def validate_spatial_timeline(scene: dict, shot: dict) -> list[dict]:
    issues = []
    system = scene["coordinate_system"]
    for axis in AXES:
        bounds = system["bounds"][axis]
        if len(bounds) != 2 or not all(math.isfinite(float(v)) for v in bounds) or bounds[1] <= bounds[0]:
            raise ValueError("Invalid scene coordinate bounds")
    duration = float(shot["duration_s"])
    camera_at(shot, 0)
    characters = {track["character_id"] for track in shot["character_tracks"]}
    targets = characters | {str(item.get("element_id")) for item in scene.get("fixed_elements", [])} | {str(item.get("asset_id")) for item in scene.get("prop_placements", [])}
    props = {p['asset_id'] for p in scene.get('prop_placements', [])}
    for track in shot.get('prop_tracks', []):
        if track['asset_id'] not in props:
            issues.append({'code': 'unknown-prop-track', 'asset_id': track['asset_id']})
        times = [float(k['time_s']) for k in track['trajectory']]
        if times != sorted(set(times)) or any(t < 0 or t > duration for t in times):
            raise ValueError('Prop trajectory must be ordered and inside the shot')
        if any(k.get('holder_id') and k['holder_id'] not in characters for k in track['trajectory']):
            issues.append({'code': 'unknown-prop-holder', 'asset_id': track['asset_id']})
    for track in shot["character_tracks"]:
        times = [float(k["time_s"]) for k in track["trajectory"]]
        if times != sorted(set(times)) or any(t < 0 or t > duration for t in times):
            raise ValueError("World trajectory must be ordered and inside the shot, independently of visibility")
        for key in track["trajectory"]:
            rotation = key.get('rotation_quaternion', [])
            if len(rotation) != 4 or not all(math.isfinite(float(v)) for v in rotation) or abs(sum(float(v)**2 for v in rotation)-1) > .001:
                issues.append({'code': 'invalid-rotation-quaternion', 'character_id': track['character_id'], 'time_s': key['time_s']})
            for axis, value in zip(AXES, vector(key["position"])):
                low, high = system["bounds"][axis]
                if not low <= value <= high:
                    issues.append({"code": "character-out-of-bounds", "character_id": track["character_id"], "time_s": key["time_s"]})
            if key.get("gaze_target_id") and key["gaze_target_id"] not in targets:
                issues.append({"code": "unknown-gaze-target", "target": key["gaze_target_id"]})
        for action in track.get("action_events", []):
            if action.get("interaction_target") and action["interaction_target"] not in targets:
                issues.append({"code": "unknown-interaction-target", "target": action["interaction_target"]})
    return issues


def snapshot_prompt(snapshot: dict, *, style: dict, reference_bindings: list[dict]) -> str:
    return "\n".join([
        f"故事板成图：镜头 {snapshot['shot_id']} 的 {snapshot['time_s']} 秒瞬间。只绘制这一瞬间，不绘制整段动作或拼接多格。",
        f"视觉风格：{canonical_json(style).strip()}",
        f"输入图片角色及职责：{canonical_json([{k: v for k, v in b.items() if k != 'approval_ref'} for b in reference_bindings]).strip()}",
        "角色图只继承身份和批准服装，不继承背景、原构图及无关姿势。空间图只继承机位、构图、遮挡及站位，不继承白模外观。",
        "只绘制 visible=true 的人物；画外人物状态仅用于连续性记录，不得因其出现在数据里而加入画面。",
        f"此刻求值状态：{canonical_json(snapshot).strip()}",
        "保留角色身份与当前动作、视线、情绪、道具。禁止新增人物、改变关键行动结果、重排空间或绘制文字标签。",
    ])
