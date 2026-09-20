#!/usr/bin/env python3
"""Director Grammar 1.0: offline validation, routing, compilation and evidence gates."""
import argparse
import hashlib
import json
import re
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'^  version:\s*[\"\']?([^\"\'\n]+)', (ROOT/'SKILL.md').read_text(), re.M).group(1).strip()


def _detail_support(version=None):
    import importlib.util
    path = Path(__file__).with_name('v52_support.py' if version and version.endswith('1.2') else 'v51_support.py')
    spec = importlib.util.spec_from_file_location('v51_support_' + str(path), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    def invalid(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"Non-finite JSON number: {value}")
        return number
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid, parse_float=finite)


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def valid_reference_image(path):
    """Verify the adapter's narrow PNG/JPEG/WebP still-image input surface."""
    if Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        return False
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,nb_read_frames", "-of", "json", str(path)],
            capture_output=True,text=True,check=True)
        stream = json.loads(probe.stdout)["streams"][0]
        if stream["codec_name"] not in ("png", "mjpeg", "webp") or int(stream["nb_read_frames"]) != 1:
            return False
        decode = subprocess.run(["ffmpeg","-v","error","-i",str(path),"-frames:v","1","-f","null","-"],
            capture_output=True,text=True,check=True)
        return not decode.stderr.strip()
    except (OSError,subprocess.CalledProcessError,ValueError,KeyError,IndexError):
        return False


def save(path, value):
    Path(path).write_text(dump(value), encoding="utf-8")


def registry(name):
    return read(ROOT / "registries" / f"{name}.json")


def schema_errors(value, name):
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError as exc:
        raise ValueError("缺少 jsonschema；在虚拟环境执行 pip install -r requirements.txt") from exc
    resources = [("https://director-grammar.local/" + p.name,
                  Resource.from_contents(read(p))) for p in (ROOT / "schemas").glob("*.json")]
    schema = read(ROOT / "schemas" / f"{name}.schema.json")
    validator = Draft202012Validator(schema, registry=Registry().with_resources(resources))
    return [f"/{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in sorted(validator.iter_errors(value), key=lambda e: str(e.absolute_path))]


def pointer(data, path):
    for key in path.split("/")[1:]:
        key = key.replace("~1", "/").replace("~0", "~")
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def route(intent):
    styles = registry("styles")["styles"]
    aliases = registry("directors")["directors"]
    requested = intent["style_request"]
    for alias in aliases:
        if requested and requested.casefold() in (alias["name"].casefold(), alias["alias"].casefold()):
            requested = alias["style_id"]
    if requested and requested not in {s["id"] for s in styles}:
        raise ValueError(f"未知风格/导演 {requested}；需建立有来源的临时风格，不能静默替换")
    accepted, rejected = [], []
    for style in styles:
        reason = []
        if intent["task"] not in style["tasks"]:
            reason.append("任务类型不匹配")
        conflict = set(style["techniques"]) & set(intent["forbidden_techniques"])
        if conflict:
            reason.append("违反禁用技法：" + ",".join(sorted(conflict)))
        if reason:
            rejected.append({"style_id": style["id"], "reason": reason})
        else:
            hits = sorted(set(intent["tags"]) & set(style["tags"]))
            accepted.append({"style_id": style["id"], "score": len(hits), "matched_tags": hits,
                             "direction": style["direction"], "fallback": style["fallback"]})
    if requested:
        accepted = [s for s in accepted if s["style_id"] == requested]
    if not accepted:
        raise ValueError("没有满足硬约束的风格；修改合同或补充专用风格，禁止静默降级")
    accepted.sort(key=lambda s: (-s["score"], s["style_id"]))
    # No tag evidence: choose a low-complexity method suitable for the task.
    default = {"narrative": "observational", "observation": "observational",
               "demonstration": "movement_clarity", "performance": "movement_clarity",
               "product": "product_evidence"}[intent["task"]]
    if not requested and accepted[0]["score"] == 0:
        accepted.sort(key=lambda s: (s["style_id"] != default, s["style_id"]))
    return {"selected": accepted[0], "alternatives": accepted[1:], "rejected": rejected,
            "basis": "可解释标签启发式；硬约束先过滤；不是实测质量排名"}


def validate(ir):
    if ir.get('schema_version') in ('1.1','1.2'):
        return [e['path'] + ': ' + e['message'] for e in _detail_support(ir.get('schema_version')).validate_native(ir, ROOT, 'director-ir') if e['severity'] in ('error', 'blocker')]
    errors = schema_errors(ir, "director-ir")
    if errors:
        return errors
    def err(path, message):
        errors.append(f"{path}: {message}")
    def unique(items, path):
        keys = [x["id"] for x in items]
        if len(keys) != len(set(keys)):
            err(path, "重复 ID")
        return {x["id"]: x for x in items}
    sources = unique(ir["sources"], "/sources")
    entities = unique(ir["entities"], "/entities")
    assets = unique(ir["assets"], "/assets")
    scenes = unique(ir["scenes"], "/scenes")
    beats = unique(ir["beats"], "/beats")
    shots = unique(ir["shots"], "/shots")
    checks = unique(ir["contract"]["checks"], "/contract/checks")
    unique(ir["contract"]["clauses"], "/contract/clauses")
    styles = {x["id"]: x for x in registry("styles")["styles"]}
    techniques = {x["id"] for x in registry("techniques")["techniques"]}
    try:
        routed = route(ir["intent"])
    except ValueError as e:
        err("/intent", str(e))
        routed = None
    for collection in (ir["entities"], ir["assets"], ir["beats"], ir["shots"], ir["contract"]["clauses"]):
        for item in collection:
            for ref in item["source_refs"]:
                if ref not in sources:
                    err(item["id"], f"未知来源 {ref}")
    for clause in ir["contract"]["clauses"]:
        for path in clause["paths"]:
            try:
                pointer(ir, path)
            except (KeyError, IndexError, ValueError, TypeError):
                err(clause["id"], f"无效来源字段路径 {path}")
        for check in clause["check_ids"]:
            if check not in checks:
                err(clause["id"], f"未知验收项 {check}")
            elif clause["priority"] == "hard" and not checks[check]["blocking"]:
                err(clause["id"], "硬要求必须连接 blocking 验收项")
    hard_checks = {c for clause in ir["contract"]["clauses"] if clause["priority"] == "hard"
                   for c in clause["check_ids"]}
    for waiver in ir["contract"]["acceptance"]["waivers"]:
        if waiver["check_id"] not in checks or waiver["check_id"] in hard_checks:
            err("/contract/acceptance/waivers", "未知或硬要求不能以豁免代替合同修订")
    execution = ir["contract"]["execution"]
    if execution["mode"] == "authorized_execution" and not execution["authorization_ref"]:
        err("/contract/execution", "执行授权需要可追溯记录；不能由编译器自行授予")
    if sum(x["frames"] for x in ir["shots"]) != ir["format"]["total_frames"]:
        err("/format/total_frames", "镜头帧数总和不等于成片合同")
    for scene in ir["scenes"]:
        if scene["location_id"] not in entities or entities[scene["location_id"]]["kind"] != "location":
            err(scene["id"], "未知场景实体")
        a, b = scene["axis_start_m"], scene["axis_end_m"]
        if a[:2] == b[:2]:
            err(scene["id"], "动作轴在地平面上的两点不能重合")
        style = styles.get(scene["style_id"])
        if not style:
            err(scene["id"], "未知风格")
        elif ir["intent"]["task"] not in style["tasks"] or set(style["techniques"]) & set(ir["intent"]["forbidden_techniques"]):
            err(scene["id"], "风格与任务/禁用技法冲突")
        if ir["intent"]["style_request"] and routed and scene["style_id"] != routed["selected"]["style_id"]:
            err(scene["id"], "未落实用户指定风格")
    for beat in ir["beats"]:
        if beat["scene_id"] not in scenes:
            err(beat["id"], "未知场景引用")
    visited = set()
    knowledge = {}
    for index, shot in enumerate(ir["shots"]):
        p = f"/shots/{index}"
        scene = scenes.get(shot["scene_id"])
        if not scene or shot["beat_id"] not in beats:
            err(p, "未知场景/节拍")
            continue
        if beats[shot["beat_id"]]["scene_id"] != shot["scene_id"]:
            err(p, "节拍归属场景不匹配")
        for technique in shot["technique_ids"]:
            if technique not in techniques or technique in ir["intent"]["forbidden_techniques"]:
                err(p, f"未知或被禁止技法 {technique}")
        states = []
        for label in ("start_state", "end_state"):
            items = shot[label]
            values = {x["entity_id"]: x for x in items}
            if len(items) != len(values):
                err(p + "/" + label, "重复实体状态")
            for v in items:
                if v["entity_id"] not in entities or (v["gaze_target"] and v["gaze_target"] not in entities):
                    err(p + "/" + label, "未知实体或视线目标")
            states.append(values)
        if set(states[0]) != set(states[1]):
            err(p, "起止实体集合不一致；离画实体仍应保留世界状态")
        cursor = 0
        for phase in shot["phases"]:
            if phase["start_frame"] != cursor or phase["end_frame"] <= phase["start_frame"]:
                err(p + "/phases", "阶段必须连续覆盖且时长为正")
            cursor = phase["end_frame"]
        if cursor != shot["frames"]:
            err(p + "/phases", "动作阶段未覆盖整个镜头")
        comp = shot["composition"]
        visible = {x["entity_id"]: x for x in comp["subjects"]}
        if len(visible) != len(comp["subjects"]):
            err(p + "/composition", "重复构图主体")
        for subject in comp["subjects"]:
            x, y, w, h = subject["box"]
            if w <= 0 or h <= 0 or x + w > 1.000001 or y + h > 1.000001:
                err(p + "/composition", "box 必须为画幅内的 [x,y,width,height]")
            if subject["entity_id"] not in states[0]:
                err(p + "/composition", "画内主体缺少世界状态")
        x,y,w,h = comp["safe_area"]
        if w <= 0 or h <= 0 or x+w > 1 or y+h > 1:
            err(p + "/composition/safe_area", "无效安全区")
        if any(x not in visible for x in comp["attention_order"]):
            err(p + "/composition", "注意力对象不在画内")
        for must in shot["must_show"]:
            if must["entity_id"] not in visible or must["part"] not in visible[must["entity_id"]]["visible_parts"]:
                err(p + "/must_show", "必要证据与声明的可见区域矛盾")
        for actor in shot["performance"]:
            if actor["entity_id"] not in entities or entities[actor["entity_id"]]["kind"] != "character":
                err(p + "/performance", "表演主体不是已登记角色")
            parts = visible.get(actor["entity_id"], {}).get("visible_parts", [])
            if (actor["face"] or actor["eyes"]) and (actor["visibility"] != "visible" or "face" not in parts):
                err(p + "/performance", "不可见面部不能要求可读微表情")
            if actor["eyes"] and "eyes" not in parts:
                err(p + "/performance", "眼神要求缺少眼睛可见条件")
            if actor["hands"] and "hands" not in parts:
                err(p + "/performance", "手部表演要求缺少可见条件")
        for line in shot["dialogue"]:
            if line["speaker_id"] not in entities or entities[line["speaker_id"]]["kind"] != "character":
                err(p + "/dialogue", "未知说话人；画外音也需要登记角色")
            if not 0 <= line["start_frame"] < line["end_frame"] <= shot["frames"]:
                err(p + "/dialogue", "对白时间超出镜头")
        camera = shot["camera"]
        a, b = scene["axis_start_m"], scene["axis_end_m"]
        def side(c):
            v = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            return "on_axis" if abs(v) < 1e-6 else "positive" if v > 0 else "negative"
        if side(camera["start_m"]) != camera["axis_side"]:
            err(p + "/camera/axis_side", "声明的轴线侧与世界坐标矛盾")
        if side(camera["start_m"]) != side(camera["end_m"]) and not camera["axis_transition"]:
            err(p + "/camera", "机位跨轴但缺少可见过渡方案")
        if camera["movement"] == "locked" and camera["start_m"] != camera["end_m"]:
            err(p + "/camera", "固定机位不能同时声明位移")
        forward = [camera["look_at_m"][i]-camera["start_m"][i] for i in range(3)]
        if sum(x*x for x in forward) < 1e-8:
            err(p + "/camera", "观察点不能与摄影机重合")
        # Basic horizontal order check for an unrolled, non-vertical camera; not a 3D renderer.
        if abs(camera["roll_deg"]) < 1e-6 and math.hypot(*forward[:2]) > 1e-6:
            right = [forward[1], -forward[0], 0]
            projected = []
            for subject in comp["subjects"]:
                st = states[0].get(subject["entity_id"])
                if not st:
                    continue
                delta = [st["position_m"][i]-camera["start_m"][i] for i in range(3)]
                depth = sum(x*y for x,y in zip(delta, forward))
                if depth <= 0:
                    err(p + "/composition", "声明可见主体位于摄影机后方")
                else:
                    projected.append((sum(x*y for x,y in zip(delta,right))/depth,
                                      subject["box"][0]+subject["box"][2]/2))
            for u,v in zip(sorted(projected), sorted(projected)[1:]):
                if v[0]-u[0] > 0.01 and u[1] > v[1]+0.05:
                    err(p + "/composition", "画面左右顺序与机位/世界坐标矛盾")
        ownership, frame_roles = set(), set()
        for ref in shot["references"]:
            if ref["asset_id"] not in assets or ref["entity_id"] not in entities:
                err(p + "/references", "未知素材或实体")
            key = (ref["entity_id"], ref["dimension"])
            if key in ownership:
                err(p + "/references", "同一实体同一参考维度存在多个权威")
            ownership.add(key)
            if ref["role"] != "reference":
                # One asset may own several dimensions of the same frame.
                pair = (ref["role"], ref["asset_id"])
                if any(role == pair[0] and asset != pair[1] for role, asset in frame_roles):
                    err(p + "/references", "多个不同首/尾帧")
                frame_roles.add(pair)
        cont = shot["continuity"]
        previous = cont["from_shot"]
        if previous:
            if previous not in visited:
                err(p + "/continuity", "连续性前驱必须是更早的展示镜头")
            else:
                prior = shots[previous]
                old = {x["entity_id"]: x for x in prior["end_state"]}
                for entity in cont["match_entities"]:
                    if old.get(entity) != states[0].get(entity) or entity not in old:
                        err(p + "/continuity", f"{entity} 前驱终态与当前初态不一致")
                if prior["scene_id"] == shot["scene_id"] and prior["camera"]["axis_side"] != camera["axis_side"] and not camera["axis_transition"]:
                    err(p + "/continuity", "相邻引用镜头换轴侧，缺少轴线过渡说明")
        elif cont["match_entities"]:
            err(p + "/continuity", "无前驱不能声明匹配实体")
        for check in shot["acceptance_ids"]:
            if check not in checks or checks[check]["scope"] not in (shot["id"], "project"):
                err(p + "/acceptance_ids", "未知或范围错误的验收项")
        if not any(checks.get(c, {}).get("gate") == "G3" for c in shot["acceptance_ids"]):
            err(p + "/acceptance_ids", "每个镜头需要实际素材验收项 G3")
        known = knowledge.setdefault(shot["scene_id"], set())
        if not set(shot["narrative"]["audience_before"]) <= known:
            err(p + "/narrative", "观众初始知识没有前序镜头来源；背景信息应在首镜叙事中建立")
        known.update(shot["narrative"]["audience_after"])
        visited.add(shot["id"])
    return errors


CAMERA_WORDS = {"locked":"固定机位", "dolly_in":"摄影机向主体推进", "dolly_out":"摄影机远离主体拉出",
    "truck_left":"摄影机向左平移", "truck_right":"摄影机向右平移", "pan_left":"机位不动向左摇摄",
    "pan_right":"机位不动向右摇摄", "tilt_up":"向上摇摄", "tilt_down":"向下摇摄",
    "pedestal_up":"机位升高", "pedestal_down":"机位降低", "orbit":"摄影机沿弧线环绕",
    "tracking":"摄影机跟随主体", "handheld":"有控制的手持摄影", "zoom_in":"机位不动变焦拉近", "zoom_out":"机位不动变焦拉远"}
LEXICAL = dict(zip(["locked","dolly_in","dolly_out","truck_left","truck_right","pan_left","pan_right",
    "tilt_up","tilt_down","pedestal_up","pedestal_down","tracking","handheld","zoom_in","zoom_out"],
    ["Static shot","Push in","Pull out","Truck left","Truck right","Pan left","Pan right","Tilt up",
     "Tilt down","Pedestal up","Pedestal down","Tracking shot","Shake","Zoom in","Zoom out"]))


def prompt_parts(ir, shot, profile):
    if ir.get('schema_version') in ('1.1','1.2'):
        support = _detail_support(ir.get('schema_version'))
        start, end = support.detail.bounds(ir)[shot['id']]
        blocks, coverage = support.detail.render(ir, start, end)
        parts = [('timeline', b['text']) for b in blocks if b['channel'] == 'prompt']
        scene=next(s for s in ir['scenes'] if s['id']==shot['scene_id'])
        parts += [('static','场景：'+scene['space'])]
        ids={eid for sample in ir['timeline']['state_samples'] if sample['shot_id']==shot['id'] for eid in sample['entities']}
        parts += [('static',e['name']+'：'+e['description']) for e in ir['entities'] if e['id'] in ids]
        if ir['schema_version']=='1.1':parts += [('static', '构图：' + support.detail.readable(shot['composition']))]
        parts += [('static', '灯光：' + support.detail.readable(shot['lighting']))]
        return parts
    names = {e["id"]:e["name"] for e in ir["entities"]}
    scene = next(s for s in ir["scenes"] if s["id"] == shot["scene_id"])
    style = next(s for s in registry("styles")["styles"] if s["id"] == scene["style_id"])
    fps = ir["format"]["fps"]
    parts = []
    def add(path, text):
        if text:
            parts.append((path, text))
    if profile["mode"] != "i2v":
        add("scene", scene["space"])
        add("entities", "；".join(e["name"]+"："+e["description"] for e in ir["entities"]
                                  if e["id"] in {s["entity_id"] for s in shot["start_state"]}))
        add("start_state", "初始："+"；".join(f"{names[s['entity_id']]} {s['pose']}；支撑{s['support']}；接触{s['contact']}" for s in shot["start_state"]))
        add("lighting", "光线："+"；".join(shot["lighting"].values()))
    add("style", style["direction"])
    add("narrative", "本镜信息："+"；".join(shot["narrative"]["audience_after"])+
        "。人物当前所知："+"；".join(shot["narrative"]["character_knows"]))
    add("phases", " ".join(f"{p['start_frame']/fps:g}–{p['end_frame']/fps:g}秒：{p['action']}；{p['reaction']}；结束时{p['end_state']}。" for p in shot["phases"]))
    for i, actor in enumerate(shot["performance"]):
        add(f"performance/{i}", names[actor["entity_id"]]+"表演："+"；".join(str(actor[k]) for k in ("trigger","eyes","face","hands","body","voice") if actor[k]))
    cam = shot["camera"]
    move = CAMERA_WORDS[cam["movement"]]
    if profile["camera_channel"] == "lexical" and cam["movement"] in LEXICAL:
        move = "["+LEXICAL[cam["movement"]]+"] " + move
    add("camera", f"{move}；{cam['framing_start']}至{cam['framing_end']}；{cam['path']}；{cam['speed']}；焦点{cam['focus']}。")
    if profile["mode"] != "i2v":
        add("camera_intent", f"拍摄设计意图：等效{cam['focal_mm']:g}mm，机位高度{cam['start_m'][2]:g}至{cam['end_m'][2]:g}米，画面roll {cam['roll_deg']:g}度；{cam['motivation']}。")
    comp = shot["composition"]
    add("composition", f"构图：{comp['rule']}；{comp['negative_space']}；{comp['depth_layers']}；关注顺序"+"→".join(names[x] for x in comp["attention_order"]))
    add("must_show", "清楚保留："+"；".join(names[m["entity_id"]]+"的"+m["part"]+"（"+m["reason"]+"）" for m in shot["must_show"]))
    add("end_state", "终态："+"；".join(names[s["entity_id"]]+" "+s["pose"]+"；"+s["contact"] for s in shot["end_state"]))
    add("continuity", "保持："+"；".join(shot["continuity"]["invariants"]))
    shot_index = ir["shots"].index(shot)
    scene_index = ir["scenes"].index(scene)
    relevant = []
    for clause in ir["contract"]["clauses"]:
        if clause["priority"] != "hard":
            continue
        audio_only = all("/dialogue" in p or "/sound" in p for p in clause["paths"])
        if audio_only and not profile["native_audio"]:
            continue
        prefixes = (f"/shots/{shot_index}", f"/scenes/{scene_index}", "/intent")
        shot_scopes = {p.split("/")[2] for p in clause["paths"] if p.startswith("/shots/")}
        if len(shot_scopes) > 1:
            # Cross-shot requirements stay in the assembly contract; future reveals must not
            # be injected into an earlier single-shot generation prompt.
            continue
        if any(p == prefix or p.startswith(prefix+"/") for p in clause["paths"] for prefix in prefixes):
            relevant.append(clause["requirement"])
    add("contract", "本镜头制作约束："+"；".join(relevant) if relevant else "")
    if profile["native_audio"]:
        add("dialogue", " ".join(f"{names[d['speaker_id']]}：“{d['text']}”（{d['delivery']}，{d['start_frame']/fps:g}–{d['end_frame']/fps:g}秒）" for d in shot["dialogue"]))
        add("sound", "声音："+"；".join(str(shot["sound"][k]) for k in ("ambience","cue","sync")))
    return parts


def compile_ir(ir, target, asset_root, resolution=None):
    errors = validate(ir)
    if ir.get('schema_version') in ('1.1','1.2') and not _detail_support(ir.get('schema_version')).detail.semantic_status(ir):
        errors.append('时间轨缺少绑定当前内容的语义审查')
    if errors:
        raise ValueError("\n".join(errors))
    if ir.get('schema_version') in ('1.1','1.2'):
        from fractions import Fraction
        ir = json.loads(dump(ir))
        ir['format']['fps'] = float(Fraction(str(ir['format']['fps'])))
    profiles = {p["id"]:p for p in registry("capabilities")["profiles"]}
    if target not in profiles:
        raise ValueError(f"未知目标 {target}；先登记精确入口及证据")
    cap = profiles[target]
    assets = {a["id"]:a for a in ir["assets"]}
    losses, jobs, segments, mapping = [], [], [], []
    def loss(path, feature, channel, severity, reason, remedy, checks):
        losses.append(dict(id=f"LOSS{len(losses)+1:03}", path=path, feature=feature, channel=channel,
                           severity=severity, reason=reason, remedy=remedy, check_ids=checks))
    groups = [ir["shots"]] if cap["mode"] in ("multishot","agent") else [[s] for s in ir["shots"]]
    timeline = 0
    all_checks = [c["id"] for c in ir["contract"]["checks"]]
    for group in groups:
        jid = f"JOB{len(jobs)+1:03}"
        reasons, bindings, texts = [], [], []
        seconds = sum(s["frames"] for s in group) / ir["format"]["fps"]
        durations = cap["durations"]
        if cap["backend"] == "api":
            resolution = resolution or cap["default_resolution"]
            if resolution not in cap["resolution_durations"]:
                raise ValueError(f"未核验分辨率 {resolution}")
            durations = cap["resolution_durations"][resolution]
        duration = next((v for v in durations if v >= seconds), None) if durations else seconds
        if duration is None:
            duration = seconds
            reasons.append("时长超出目标入口；需按动作终态重分镜，不能自动切断接触或对白")
        for shot in group:
            index = ir["shots"].index(shot)
            path = f"/shots/{index}"
            checks = shot["acceptance_ids"]
            parts = prompt_parts(ir, shot, cap)
            text = "\n".join(t for _,t in parts)
            if len(group)>1:
                text = f"{shot['id']}（{shot['frames']/ir['format']['fps']:g}秒）\n" + text
            texts.append(text)
            for field, phrase in parts:
                source_path = path+"/"+field
                if field == "scene":
                    source_path = f"/scenes/{next(i for i,s in enumerate(ir['scenes']) if s['id']==shot['scene_id'])}/space"
                elif field == "style":
                    source_path = f"/scenes/{next(i for i,s in enumerate(ir['scenes']) if s['id']==shot['scene_id'])}/style_id"
                elif field == "entities":
                    source_path = "/entities"
                elif field == "contract":
                    source_path = "/contract/clauses"
                elif field == "camera_intent":
                    source_path = path+"/camera"
                mapping.append(dict(path=source_path,destination=f"{jid}.prompt:{shot['id']}:{field}",channel="prompt",check_ids=checks))
            camera_channel = cap["camera_channel"]
            if camera_channel == "lexical" and shot["camera"]["movement"] not in LEXICAL:
                camera_channel = "natural_language"
            loss(path+"/camera", "机位、焦距与轨迹精度",camera_channel,
                 "blocker" if shot["camera"]["precision"]=="metric" else "warning",
                 "镜头参数是拍摄意图；此后端不能保证米级路径或光学数值", "度量要求用3D预演/实拍验证；定性意图审查实际素材", checks)
            if shot["camera"]["precision"] == "metric":
                reasons.append("当前后端无法兑现 metric 摄影机精度")
            loss(path+"/composition", "构图与空间投影", "natural_language", "warning",
                 "bbox与坐标保存在合同中，文本后端不能逐像素执行", "先审关键帧，再检查真实视频起中末帧和遮挡", checks)
            if cap["mode"] == "i2v":
                loss(path+"/start_state", "I2V静态视觉由首帧承担", "natural_language", "warning",
                     "初态、服装和光线不在动作提示词中重复重绘", "逐项核对首帧与原合同", checks)
            if not cap["native_audio"]:
                loss(path+"/sound", "声音与对白", "post", "warning",
                     "目标未提供本适配器可核验的原生音频路径；声音合同保留于导演原件", "按原对白/声源/时间锚点后期制作并检查口型", checks)
                mapping.append(dict(path=path+"/dialogue",destination="director_contract.json"+path+"/dialogue",channel="post",check_ids=checks))
            unique_assets = {}
            asset_roles = {}
            first = set()
            for ref in shot["references"]:
                asset = assets[ref["asset_id"]]
                unique_assets.setdefault(asset["id"], []).append(ref["dimension"])
                asset_roles.setdefault(asset["id"], set()).add(ref["role"])
                if ref["role"] in ("first_frame", "last_frame") and ref["role"] not in cap["reference_roles"]:
                    reasons.append(f"目标没有已核验的 {ref['role']} 角色；不能合并到其他槽位")
                if ref["role"] == "first_frame":
                    first.add(asset["id"])
                file = Path(asset_root)/asset["path"] if asset["path"] else None
                if asset["status"] != "approved" or not file or not file.is_file():
                    reasons.append(f"素材 {asset['id']} 未批准或文件不存在")
                elif file.name != asset["filename"] or not asset["sha256"] or file_digest(file) != asset["sha256"]:
                    reasons.append(f"素材 {asset['id']} 文件名或哈希不匹配")
                elif cap["mode"]=="i2v" and not valid_reference_image(file):
                    reasons.append(f"素材 {asset['id']} 无法解码为支持的PNG/JPEG/WebP单帧图像，或缺少ffprobe/ffmpeg")
            if cap["mode"] == "i2v" and len(first) != 1:
                reasons.append("I2V 需要恰好一张已批准首帧")
            if len(unique_assets) > cap["max_references"]:
                reasons.append("此适配器的已核验附件路径无法容纳全部参考；不得静默丢弃维度权威")
            for aid,dims in unique_assets.items():
                a = assets[aid]
                bindings.append(dict(asset_id=aid,filename=a["filename"],path=a["path"],sha256=a["sha256"],
                                     slot="first_frame" if aid in first and cap["mode"]=="i2v" else "UNRESOLVED",
                                     dimensions=sorted(set(dims)), roles=sorted(asset_roles[aid])))
            segments.append(dict(id=f"EDIT{len(segments)+1:03}",shot_id=shot["id"],job_id=jid,
                                 timeline_start_frame=timeline,frames=shot["frames"],source_in_frame=0,
                                 take_id=None))
            timeline += shot["frames"]
        text = "\n\n".join(texts)
        if cap["max_chars"] and len(text)>cap["max_chars"]:
            reasons.append(f"提示词 {len(text)} 字符超出 {cap['max_chars']}，不允许自动截断")
        if cap["backend"] == "blocked":
            reasons.append("产品入口、模型或参数契约未核验")
        request, kind = None, "none"
        if cap["backend"] == "api":
            request = dict(model=cap["model_id"],prompt=text,duration=duration,resolution=resolution,prompt_optimizer=False)
            kind = "api_body"
        elif cap["backend"] == "ui":
            request = {"instruction":"UI填写表，非API请求", "model_label":cap["model_id"], "duration_seconds":duration}
            if cap["mode"] == "multishot":
                request.update(multi_shot=True,custom_multi_shot=[dict(shot_id=s["id"],seconds=s["frames"]/ir["format"]["fps"],text=t) for s,t in zip(group,texts)])
            kind = "ui_fields"
        elif cap["backend"] == "agent":
            text = f"制作目标：{ir['intent']['goal']}\n交付："+"；".join(ir["contract"]["deliverables"])+"\n"+text+"\n不可改变："+"；".join(c["requirement"] for c in ir["contract"]["clauses"] if c["priority"]=="hard")+"\n验收："+"；".join(c["predicate"] for c in ir["contract"]["checks"])
            request, kind = {"message":text}, "agent_task"
            loss("/contract", "平台Agent重新规划", "natural_language", "warning", "任务消息无法强制平台内部执行策略", "提交前核对平台返回计划，提交后逐项验收", all_checks)
        jobs.append(dict(id=jid,shot_ids=[s["id"] for s in group],mode=cap["mode"],duration_seconds=duration,
                         edit_frames=sum(s["frames"] for s in group),prompt=text,bindings=bindings,
                         request=request,request_kind=kind,status="BLOCKED" if reasons else "PLANNED",reason=sorted(set(reasons))))
        if len(group)>1:
            # Candidate subshot boundaries are only nominal until the generated take is inspected.
            offset = 0
            for seg in [s for s in segments if s["job_id"]==jid]:
                seg["source_in_frame"] = offset
                offset += seg["frames"]
            loss("/shots", "多镜头边界", "post", "warning", "同一次生成中的切点只是计划值", "根据实片重新定源入点并裁切，禁止把计划帧位当实测切点", all_checks)
    for clause in ir["contract"]["clauses"]:
        for path in clause["paths"]:
            mapping.append(dict(path=path,destination="director_contract.json"+path,channel="contract_review",check_ids=clause["check_ids"]))
            if "/dialogue" in path or "/sound" in path:
                channel = "native" if cap["native_audio"] else "post"
            elif "/camera" in path:
                channel = cap["camera_channel"]
                if path.startswith("/shots/") and channel == "lexical":
                    shot = ir["shots"][int(path.split("/")[2])]
                    if shot["camera"]["movement"] not in LEXICAL:
                        channel = "natural_language"
            elif path.startswith("/assets") or "/references" in path:
                channel = "reference" if cap["max_references"] else "unsupported"
            elif path.startswith("/format"):
                channel = "post"
            elif path.startswith("/shots") or path.startswith("/scenes") or path.startswith("/intent"):
                channel = "natural_language"
            else:
                channel = "review"
            if clause["priority"]=="hard" and channel not in clause["allowed_channels"]:
                reason=f"合同 {clause['id']} 不允许 {channel} 实现 {path}"
                loss(path,clause["requirement"],channel if channel!="review" else "unknown","blocker",reason,
                     "选择满足原实现渠道的入口，或经明确决定修订合同",clause["check_ids"])
                for job in jobs:
                    job["status"]="BLOCKED"
                    job["reason"].append(reason)
    loss("/format", "最终画幅、帧率与帧数", "post", "warning", "生成规格与最终交付规格不同", "实际probe后按合同剪辑/适配；裁切不可损失必要证据", all_checks)
    blocked = any(j["status"]=="BLOCKED" for j in jobs)
    result = dict(schema_version="1.0",compiler_version=VERSION,ir_sha256=digest(ir),capability_sha256=digest(cap),
                  registries_sha256=digest({k:registry(k) for k in ("styles","techniques","directors","evidence")}),
                  contract_id=ir["contract"]["id"],target=target,status="BLOCKED" if blocked else "PLANNED",
                  submitted=False,jobs=jobs,edit_segments=segments,losses=losses,semantic_map=mapping,
                  qa={"G0":"BLOCKED" if blocked else "STATIC_PASS","G1":"STATIC_PASS","G2":"BLOCKED" if blocked else "STATIC_PASS","G3":"NOT_RUN","G4":"NOT_RUN"})
    errors = schema_errors(result,"execution-ir")
    if errors:
        raise ValueError("Compiler output invalid: " + "\n".join(errors))
    return result


def qa_gate(ir, execution, report, evidence_root):
    errors = validate(ir) + schema_errors(execution,"execution-ir") + schema_errors(report,"qa-report")
    if errors:
        return {"status":"BLOCKED","errors":errors}
    if execution["ir_sha256"] != digest(ir) or report["ir_sha256"] != digest(ir) or report["execution_sha256"] != digest(execution):
        errors.append("上游内容已变化，验收记录 STALE")
    if execution["status"]=="BLOCKED":
        errors.append("执行计划仍然 BLOCKED")
    records = {r["check_id"]:r for r in report["records"]}
    known = {c["id"] for c in ir["contract"]["checks"]}
    if len(records)!=len(report["records"]) or not set(records)<=known:
        errors.append("验收记录重复或引用未知check_id")
    waived = {w["check_id"] for w in ir["contract"]["acceptance"]["waivers"]}
    for check in ir["contract"]["checks"]:
        if not check["blocking"] or check["id"] in waived:
            continue
        record = records.get(check["id"])
        if not record or record["status"]!="PASS":
            errors.append(check["id"]+": 尚未通过")
            continue
        if not record["reviewer"]:
            errors.append(check["id"]+": 缺少检查执行者")
        if record["observation"].strip() in ("尚未执行", "NOT_RUN", "未执行"):
            errors.append(check["id"]+": PASS仍保留未执行观察")
        fields = [("evidence_path","evidence_sha256")]
        if check["gate"] in ("G3","G4"):
            fields.append(("media_path","media_sha256"))
        for path_key, hash_key in fields:
            path = Path(evidence_root)/record[path_key] if record[path_key] else None
            if not path or not path.is_file() or file_digest(path)!=record[hash_key]:
                errors.append(check["id"]+": 缺少真实文件或哈希不符 "+path_key)
        if check["gate"] in ("G3", "G4") and record["media_path"]:
            try:
                probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                    "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames", "-of", "json",
                    str(Path(evidence_root)/record["media_path"])],capture_output=True,text=True,check=True)
                stream = json.loads(probe.stdout)["streams"][0]
                frames = int(stream["nb_read_frames"])
                if frames < 2:
                    raise ValueError("media is not a multi-frame video")
                if check["gate"] == "G4":
                    fmt = ir["format"]
                    if frames != fmt["total_frames"] or Fraction(stream["avg_frame_rate"]) != fmt["fps"] or (stream["width"],stream["height"]) != (fmt["width"],fmt["height"]):
                        errors.append(check["id"]+": 最终视频帧数、帧率或尺寸不符合合同")
            except (OSError,subprocess.CalledProcessError,ValueError,KeyError,IndexError,ZeroDivisionError):
                errors.append(check["id"]+": 缺少ffprobe或媒体不能解码为视频")
    return {"status":"BLOCKED" if errors else "ACCEPTED_RECORDED", "errors":errors,
            "meaning":"核对证据记录完整性与新鲜度；视觉判断由记录中的审片者承担，脚本不识别画面内容"}


def write_bundle(out, ir, execution):
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("输出目录非空；使用新的版本目录，避免覆盖旧回执")
    save(out/"director_contract.json",ir)
    save(out/"execution.json",execution)
    save(out/"capability-snapshot.json",next(c for c in registry("capabilities")["profiles"] if c["id"]==execution["target"]))
    save(out/"style-decision.json",route(ir["intent"]))
    techniques={t["id"]:t for t in registry("techniques")["techniques"]}
    save(out/"technique-plan.json",dict(status="REQUIRES_DIRECTOR_REVIEW",shots=[dict(shot_id=s["id"],
        techniques=[techniques[t] for t in s["technique_ids"]]) for s in ir["shots"]]))
    save(out/"post-production.json",dict(ir_sha256=digest(ir),execution_sha256=digest(execution),status="NOT_RUN",
        edit_segments=execution["edit_segments"],sound_and_dialogue=[dict(shot_id=s["id"],sound=s["sound"],
        dialogue=s["dialogue"],acceptance_ids=s["acceptance_ids"]) for s in ir["shots"]],
        instructions="按真实Take边界选择源入点；无原生音频时按此声源与台词制作声轨，实测同步。"))
    save(out/"qa-report.json",dict(schema_version="1.0",ir_sha256=digest(ir),execution_sha256=digest(execution),
         records=[dict(check_id=c["id"],status="NOT_RUN",evidence_path=None,evidence_sha256=None,
                       media_path=None,media_sha256=None,reviewer=None,observation="尚未执行") for c in ir["contract"]["checks"]]))
    if ir.get('schema_version') in ('1.1','1.2'):
        blocks, coverage = _detail_support(ir.get('schema_version')).detail.render(ir)
        save(out/'detail-coverage.json', coverage)
        save(out/'temporal-post-production.json', [b for b in blocks if b['channel'] != 'prompt'])
    prompts = []
    for job in execution["jobs"]:
        prompts.append(f"## {job['id']} / {job['status']}\n\n{job['prompt']}\n\n附件：\n"+
                       ("\n".join(f"- {b['asset_id']} | {b['filename']} | {b['slot']} | {','.join(b['dimensions'])}" for b in job["bindings"]) or "- 无")+
                       "\n\n"+"\n".join(job["reason"]))
    (out/"prompts.md").write_text("# 可复制提示词与附件表\n\n"+"\n\n".join(prompts)+"\n",encoding="utf-8")
    rows = ["# 制作合同\n",f"合同：{ir['contract']['id']} v{ir['contract']['version']}；编译：{execution['status']}；未提交生成。\n",
            "|要求|来源|等级|验收|","|---|---|---|---|"]
    rows += [f"|{c['requirement']}|{','.join(c['source_refs'])}|{c['priority']}|{','.join(c['check_ids'])}|" for c in ir["contract"]["clauses"]]
    rows += ["\n## 执行与损失\n"] + [f"- {x['path']}：{x['reason']}；{x['remedy']}。" for x in execution["losses"]]
    (out/"production-contract.md").write_text("\n".join(rows)+"\n",encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    for name in ("validate","route"):
        p = sub.add_parser(name); p.add_argument("input")
        if name=="validate":
            p.add_argument("--screenplay-handoff"); p.add_argument("--screenplay-map")
    p = sub.add_parser("compile"); p.add_argument("input"); p.add_argument("--target",required=True)
    p.add_argument("--asset-root"); p.add_argument("--resolution"); p.add_argument("--out",required=True)
    p.add_argument("--screenplay-handoff"); p.add_argument("--screenplay-map")
    p = sub.add_parser("import-screenplay"); p.add_argument("input"); p.add_argument("--out",required=True)
    p = sub.add_parser("qa"); p.add_argument("input"); p.add_argument("execution"); p.add_argument("report")
    p.add_argument("--evidence-root",required=True)
    args = parser.parse_args()
    try:
        if args.command=="import-screenplay":
            from screenplay_protocol import load_handoff
            handoff,project=load_handoff(args.input)
            brief={"schema":"screenplay-director-brief/1.0","screenplay_handoff":str(Path(args.input).resolve()),
                   "project_id":project["project_id"],"content_sha256":handoff["content_sha256"],
                   "characters":project["characters"],"narrative":project["narrative"],"scenes":project["scenes"],
                   "requirements":handoff["requirements"],"director_freedom":handoff["director_freedom"],
                   "notice":"Read-only screenplay briefing, not a fabricated DirectorIR or user approval."}
            with Path(args.out).open("x",encoding="utf-8") as f:f.write(dump(brief))
            print(dump({"status":"IMPORTED","out":args.out}));return 0
        ir = read(args.input)
        handoff=getattr(args,"screenplay_handoff",None); mapping=getattr(args,"screenplay_map",None)
        if bool(handoff)!=bool(mapping):raise ValueError("Both --screenplay-handoff and --screenplay-map are required")
        binding={"status":"NOT_CHECKED"}
        if handoff:
            from screenplay_protocol import check_handoff, content_hash
            errors=check_handoff(ir,handoff,mapping)
            if errors:
                print(dump({"status":"BLOCKED","errors":errors,"owner":"screenplay/director"}));return 2
            binding={"status":"REVIEW_ATTESTED","handoff_sha256":file_digest(handoff),
                     "mapping_sha256":file_digest(mapping),"director_content_sha256":content_hash(ir)}
        if args.command=="validate":
            errors=validate(ir); result={"status":"INVALID" if errors else "STATIC_VALID","errors":errors,"screenplay_binding":binding}
        elif args.command=="route":
            result=route(ir["intent"])
        elif args.command=="compile":
            result=compile_ir(ir,args.target,args.asset_root or Path(args.input).resolve().parent,args.resolution)
            write_bundle(args.out,ir,result)
            save(Path(args.out)/"screenplay-binding.json",binding)
        else:
            result=qa_gate(ir,read(args.execution),read(args.report),args.evidence_root)
        print(dump(result))
        return 2 if result.get("status") in ("INVALID","BLOCKED") else 0
    except (ValueError, OSError, KeyError) as e:
        print(dump({"status":"ERROR","error":str(e)}),file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
