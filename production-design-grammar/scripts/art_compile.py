#!/usr/bin/env python3
"""Validate ArtIR and compile deterministic, offline production-design handoffs."""
import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'^  version:\s*[\"\']?([^\"\'\n]+)', (ROOT/'SKILL.md').read_text(), re.M).group(1).strip()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def object_hash(value):
    return digest(dumps(value).encode())


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def schema_errors(value, name):
    schema = read(ROOT / "schemas" / (name + ".schema.json"))
    return ["/" + "/".join(map(str, e.absolute_path)) + ": " + e.message
            for e in Draft202012Validator(schema).iter_errors(value)]


def pointer(value, path):
    if not re.fullmatch(r"/(?:[^~]|~[01])*", path):
        raise ValueError("Invalid JSON Pointer: " + path)
    for part in path[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", key):
                raise ValueError("Invalid array index: " + path)
            value = value[int(key)]
        else:
            value = value[key]
    return value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def indexed(items, label):
    out = {x["id"]: x for x in items}
    require(len(out) == len(items), "Duplicate ID in " + label)
    return out


def resolve(base, filename):
    path = Path(filename).expanduser()
    return path if path.is_absolute() else Path(base) / path


def inspect_media(path, kind):
    require(shutil.which("ffprobe") and shutil.which("ffmpeg"), "Media inspection requires ffprobe and ffmpeg")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                           capture_output=True, text=True, timeout=30)
    require(probe.returncode == 0, "Media cannot be probed: " + str(path))
    streams = json.loads(probe.stdout).get("streams", [])
    visual = [x for x in streams if x.get("codec_type") == "video" and x.get("width", 0) > 0]
    require(visual, "No visual stream: " + str(path))
    if kind == "image":
        require(path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"},
                "Reference must be a still image: " + str(path))
        require(visual[0].get("codec_name") in {"png", "mjpeg", "webp", "bmp", "tiff"}, "Not a supported still-image codec")
    else:
        require(float(visual[0].get("duration", 0)) > 0, "Video has no measurable duration")
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-frames:v", "1", "-f", "null", "-"],
                             capture_output=True, timeout=30)
    require(decoded.returncode == 0, "Media first frame cannot be decoded: " + str(path))
    return {"width": visual[0]["width"], "height": visual[0]["height"], "codec": visual[0]["codec_name"]}


def route(art):
    brief = art["brief"]
    cards = read(ROOT / "registries" / "styles.json")["styles"]
    eligible, rejected = [], []
    for card in cards:
        reason = []
        if brief["world_mode"] not in card["world_modes"]:
            reason.append("world_mode")
        if brief["medium"] not in card["media"]:
            reason.append("medium")
        if card["id"] in brief["forbidden_styles"]:
            reason.append("forbidden")
        if reason:
            rejected.append({"id": card["id"], "reasons": reason})
            continue
        matches = sorted(set(brief["tags"]) & set(card["tags"]))
        eligible.append({"id": card["id"], "matches": matches, "score": 3 * len(matches) - card["risk_prior"]})
    ranked = sorted(eligible, key=lambda x: (-x["score"], x["id"]))
    locked = brief["locked_style"]
    if locked:
        require(any(x["id"] == locked for x in eligible), "Locked style conflicts with hard filters: " + locked)
        selected = locked
    else:
        matched = [x for x in ranked if x["matches"]]
        require(matched, "No semantic style match; add meaningful tags or an explicit compatible locked_style")
        selected = matched[0]["id"]
    secondary = brief["secondary"]
    if secondary:
        require(secondary["style_id"] != selected, "Secondary style duplicates primary")
        require(any(x["id"] == secondary["style_id"] for x in eligible), "Secondary style conflicts with hard filters")
    return dict(selected=selected, secondary=secondary, ranked=ranked, rejected=rejected,
                rule="hard filters then 3*tag_matches-risk_prior; heuristic, not an aesthetic score")


def states(art):
    current = {a["id"]: copy.deepcopy(a["initial_state"]) for a in art["assets"]}
    rules = {a["id"]: {r["field"]: r["allowed_values"] for r in a["state_rules"]} for a in art["assets"]}
    result = {}
    for shot in art["shots"]:
        before = copy.deepcopy(current)
        events = sorted([e for e in art["events"] if e["shot_id"] == shot["id"]], key=lambda e: e["order"])
        require(len({e["order"] for e in events}) == len(events), "Duplicate event order in " + shot["id"])
        for event in events:
            aid, field = event["asset_id"], event["field"]
            require(field in rules[aid], "State mutation not allowed: " + event["id"])
            require(event["before"] != event["after"], "Event must change state: " + event["id"])
            require(current[aid].get(field) == event["before"], "State chain mismatch: " + event["id"])
            require(event["after"] in rules[aid][field], "State value outside contract: " + event["id"])
            current[aid][field] = event["after"]
        result[shot["id"]] = {"before": before, "after": copy.deepcopy(current), "events": events}
    return result


def validate(art, base):
    errors = schema_errors(art, "art-ir")
    require(not errors, "Schema: " + "; ".join(errors))
    sources = indexed(art["sources"], "sources")
    assets = indexed(art["assets"], "assets")
    shots = indexed(art["shots"], "shots")
    refs = indexed(art["references"], "references")
    indexed(art["events"], "events")
    materials = indexed(art["world"]["materials"], "materials")
    palette = indexed(art["world"]["palette"], "palette")
    def source_links(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "source_refs":
                    require(set(child) <= sources.keys(), "Unknown source reference: " + str(child))
                source_links(child)
        elif isinstance(value, list):
            for child in value:
                source_links(child)
    source_links(art)
    for a in assets.values():
        require(set(a["material_ids"]) <= materials.keys(), "Unknown material: " + a["id"])
        if a["origin"] == "existing":
            require(a["entity_id"], "Existing asset needs host entity_id")
        fields = [r["field"] for r in a["state_rules"]]
        require(len(fields) == len(set(fields)), "Duplicate state rule")
        for rule in a["state_rules"]:
            require(a["initial_state"].get(rule["field"]) in rule["allowed_values"], "Invalid initial state: " + a["id"])
    for color in art["world"]["color_script"]:
        require(set(color["shot_ids"]) <= shots.keys() and set(color["palette_ids"]) <= palette.keys(), "Unknown color-script reference")
    require(set().union(*(set(c["shot_ids"]) for c in art["world"]["color_script"])) == shots.keys(), "Color script must cover every shot")
    scene = art["set"]
    indexed(scene["layout"], "layout")
    indexed(scene["functional_zones"], "zones")
    indexed(scene["practical_lights"], "practical_lights")
    low, high = scene["bounds"]["min_m"], scene["bounds"]["max_m"]
    require(all(l < h for l, h in zip(low, high)), "Invalid set bounds")
    for item in scene["layout"]:
        require(item["asset_id"] in assets, "Unknown layout asset")
        require(all(l <= p <= h for l, p, h in zip(low, item["position_m"], high)), "Layout anchor outside bounds: " + item["id"])
    counts = scene["counts"]
    require(len({c["asset_id"] for c in counts}) == len(counts), "Duplicate count assertion")
    for count in counts:
        require(count["asset_id"] in assets, "Unknown count asset")
        require(sum(i["asset_id"] == count["asset_id"] for i in scene["layout"]) == count["count"], "Layout count mismatch: " + count["asset_id"])
    for zone in scene["functional_zones"]:
        require(all(l <= a < b <= h for l, a, b, h in zip(low, zone["min_m"], zone["max_m"], high)), "Invalid functional zone: " + zone["id"])
    for light in scene["practical_lights"]:
        require(all(l <= p <= h for l, p, h in zip(low, light["position_m"], high)), "Light outside bounds")
    for r in refs.values():
        require(r["asset_id"] in assets, "Unknown reference asset")
        if r["status"] == "ready":
            require(r["file"] and r["sha256"], "Ready reference requires file and hash")
            path = resolve(base, r["file"])
            require(path.is_file(), "Missing ready reference: " + r["id"])
            require(digest(path.read_bytes()) == r["sha256"], "Stale reference hash: " + r["id"])
            inspect_media(path, "image")
        else:
            require(r["file"] is None and r["sha256"] is None, "Planned reference cannot claim existing bytes")
    director = None
    if art["director"]:
        binding = art["director"]
        path = resolve(base, binding["uri"])
        require(path.is_file(), "Missing DirectorIR")
        require(digest(path.read_bytes()) == binding["sha256"], "Stale DirectorIR hash")
        director = read(path)
        require(director.get("schema_version") in ("1.0", "1.1", "1.2"), "Unsupported DirectorIR schema; migrate explicitly")
        require(director["project_id"] == binding["project_id"] == art["project_id"], "Director project mismatch")
        require(director["revision"] == binding["revision"], "Director revision mismatch")
        require(director["canon_ref"] == art["canon"]["uri"], "Canon reference mismatch")
        entities = indexed(director["entities"], "director entities")
        require(all(a["entity_id"] is None or a["entity_id"] in entities for a in assets.values()), "Unknown host entity")
        require(scene["location_entity_id"] in entities, "Unknown director location")
        require(any(s["id"] == scene["scene_id"] and s["location_id"] == scene["location_entity_id"]
                    and s["coordinate_system"] == scene["coordinate_system"] for s in director["scenes"]), "Director scene mismatch")
    previous_index = -1
    for s in shots.values():
        require(set(s["visible_assets"]) <= assets.keys(), "Unknown visible asset")
        require(s["composition_support"]["focal_asset"] in s["visible_assets"], "Focal asset not visible")
        require(set(s["required_references"]) <= refs.keys(), "Unknown shot reference")
        winners = set()
        for rid in s["required_references"]:
            r = refs[rid]
            require(r["asset_id"] in s["visible_assets"], "Reference asset not in shot")
            key = (r["asset_id"], r["role"])
            require(key not in winners, "Conflicting reference authority for " + str(key))
            winners.add(key)
        for rel in s["relative_relations"]:
            require(rel["subject_asset"] in assets and rel["object_asset"] in assets, "Unknown relative-position asset")
        for support in s["performance_support"]:
            require(any(a["entity_id"] == support["entity_id"] and a["id"] in s["visible_assets"] for a in assets.values()), "Performance support must target visible host entity")
        if director:
            require(s["director_pointer"] and re.fullmatch(r"/shots/[0-9]+", s["director_pointer"]), "Need a DirectorIR shot pointer")
            index = int(s["director_pointer"].split("/")[-1])
            require(index > previous_index, "Art shots must follow DirectorIR order")
            previous_index = index
            ds = pointer(director, s["director_pointer"])
            require(ds["id"] == s["id"] and ds["scene_id"] == scene["scene_id"], "Director shot identity mismatch")
            visible = {x["entity_id"]: set(x["visible_parts"]) for x in ds["composition"]["subjects"]}
            for support in s["performance_support"]:
                require(set(support["required_parts"]) <= visible.get(support["entity_id"], set()), "Expression/body evidence is not visible in DirectorIR: " + s["id"])
        else:
            require(s["director_pointer"] is None, "Director pointer without binding")
    for event in art["events"]:
        require(event["shot_id"] in shots and event["asset_id"] in assets, "Unknown event target")
        if director:
            path = event["director_pointer"]
            if director["schema_version"] == "1.0":
                prefix = shots[event["shot_id"]]["director_pointer"] + "/phases/"
                require(path and re.fullmatch(re.escape(prefix) + r"(?:0|[1-9][0-9]*)", path),
                        "Event must cite its director phase")
                pointer(director, path)
            else:
                require(path and re.fullmatch(r"/timeline/actions/(?:0|[1-9][0-9]*)", path),
                        "Event must cite a Director timeline action")
                action = pointer(director, path)
                require(event["shot_id"] in action["shot_ids"], "Event action is outside its shot")
                entity_id = assets[event["asset_id"]]["entity_id"]
                require(entity_id and any(change["entity_id"] == entity_id
                    and change["field"] == event["field"]
                    and change["before"] == event["before"]
                    and change["after"] == event["after"] for change in action["changes"]),
                    "Event must match a Director action state change")
        else:
            require(event["director_pointer"] is None, "Event pointer without director")
    contract = art["contract"]
    clauses = indexed(contract["clauses"], "clauses")
    checks = indexed(contract["checks"], "checks")
    for check in checks.values():
        require(check["scope"] == "project" or check["scope"] in shots, "Unknown check scope")
        require((check["gate"] in {"G0", "G1", "G2"}) == (check["method"] == "static"), "Gate/method mismatch")
    for c in clauses.values():
        require(set(c["check_ids"]) <= checks.keys() and set(c["shot_ids"]) <= shots.keys(), "Unknown clause check/shot")
        require(set(c["execution"]["reference_ids"]) <= refs.keys(), "Unknown execution reference")
        if c["execution"]["channel"] == "reference":
            require(c["execution"]["reference_ids"], "Reference channel requires references")
        if c["priority"] == "hard":
            require(all(sources[r]["verification"] != "unverified" for r in c["source_refs"]), "Hard clause has unverified source")
            require(any(checks[q]["blocking"] and checks[q]["gate"] in {"G3", "G4"} for q in c["check_ids"]), "Hard clause requires blocking media acceptance")
            media_scopes = {checks[q]["scope"] for q in c["check_ids"]
                            if checks[q]["blocking"] and checks[q]["gate"] in {"G3", "G4"}}
            require("project" in media_scopes or set(c["shot_ids"] or shots) <= media_scopes,
                    "Hard clause acceptance does not cover its shot scope")
        for path in c["paths"]:
            require(path.split("/")[1] in {"brief", "world", "assets", "set", "events", "shots", "references", "canon", "director"}, "Clause points outside design contract")
            pointer(art, path)
            if path == "/events" or path.startswith("/events/"):
                require(c["shot_ids"], "Event clause must have explicit shot scope")
                affected = art["events"] if path == "/events" else [art["events"][int(path.split("/")[2])]]
                require({e["shot_id"] for e in affected} <= set(c["shot_ids"]), "Event clause scope omits affected shot")
    for i, shot in enumerate(art["shots"]):
        applicable = [c for c in clauses.values() if not c["shot_ids"] or shot["id"] in c["shot_ids"]]
        paths = [p for c in applicable for p in c["paths"]]
        needed = [f"/shots/{i}"] + [f"/assets/{j}" for j, a in enumerate(art["assets"]) if a["id"] in shot["visible_assets"]]
        for needed_path in needed:
            require(any(needed_path == p or needed_path.startswith(p + "/") for p in paths),
                    "Contract does not bind visible shot/asset: " + shot["id"] + " " + needed_path)
    require(set().union(*(set(c["check_ids"]) for c in clauses.values())) == checks.keys(), "Orphan acceptance check")
    if contract["execution"]["mode"] == "authorized_execution":
        require(contract["execution"]["authorization_ref"] in sources, "Execution authorization requires a source record")
        authorization = sources[contract["execution"]["authorization_ref"]]
        require(authorization["kind"] in {"user", "canon"} and authorization["verification"] in {"provided", "read"},
                "Execution authorization cannot be a design inference")
    states(art)
    decision = route(art)
    return {"status": "STATIC_VALID", "director": director, "route": decision}


def compile_art(art, base, target_id, out):
    validated = validate(art, base)
    targets = indexed(read(ROOT / "registries" / "targets.json")["targets"], "targets")
    require(target_id in targets, "Unknown target: " + target_id)
    target = targets[target_id]
    out = Path(out)
    require(not out.exists() or (out.is_dir() and not any(out.iterdir())), "Output directory must be empty")
    assets = indexed(art["assets"], "assets")
    refs = indexed(art["references"], "references")
    state_map = states(art)
    blockers = []
    if target["needs_entry_resolution"]:
        blockers.append("ENTRY_UNRESOLVED: provider/product/model/mode/docs/region/permissions require host resolution")
    if target["needs_director"] and art["director"] is None:
        blockers.append("DIRECTOR_UNRESOLVED: video handoff needs a versioned DirectorIR")
    handoff_shots, texts = [], {}
    style = next(x for x in read(ROOT / "registries" / "styles.json")["styles"] if x["id"] == validated["route"]["selected"])
    for s in art["shots"]:
        sid = s["id"]
        shot_refs = [refs[r] for r in s["required_references"]]
        if target["needs_first_frame"] and not any(r["role"] == "first_frame" for r in shot_refs):
            blockers.append(sid + ": FIRST_FRAME_MISSING")
        for r in shot_refs:
            if r["status"] != "ready":
                blockers.append(sid + ": REFERENCE_NOT_READY " + r["id"])
        ds = pointer(validated["director"], s["director_pointer"]) if validated["director"] else None
        before = {a: state_map[sid]["before"][a] for a in s["visible_assets"]}
        after = {a: state_map[sid]["after"][a] for a in s["visible_assets"]}
        bindings = [{**r, "platform_object_id": None, "slot": "UNRESOLVED"} for r in shot_refs]
        handoff_shots.append(dict(id=sid, director_context=ds, art_support=s, state_before=before,
                                  state_after=after, events=state_map[sid]["events"], reference_bindings=bindings))
        lines = [sid + " 美术交接（离线）", "美术命题：" + art["world"]["thesis"],
                 "世界：" + art["world"]["era"] + "；" + art["world"]["region"] + "；" + art["world"]["social_logic"],
                 "形态：" + art["world"]["shape_language"], "主语法：" + style["name"],
                 "语法目的：" + style["purpose"] + "。具体色材与形制以下列项目设计为准，不从语法卡新增人物、器物或情节。",
                 "场景坐标：" + art["set"]["coordinate_system"] + "；原点：" + art["set"]["origin"],
                 "空间数据是设计意图；保持世界布局，但局部镜头只呈现导演视点内的部分。",
                 "本镜可见资产：" + "、".join(s["visible_assets"])]
        for item in art["set"]["layout"]:
            if item["asset_id"] in s["visible_assets"]:
                lines.append(f"布局 {item['id']} / {assets[item['asset_id']]['name']}：底面中心{item['position_m']}米，尺寸{item['size_m']}米，yaw={item['yaw_deg']}度；{item['role']}")
        for count in art["set"]["counts"]:
            lines.append(f"世界总数：{assets[count['asset_id']]['name']} {count['count']}，不等于本镜可见数。")
        for light in art["set"]["practical_lights"]:
            lines.append(f"世界光源：{light['source']}在{light['position_m']}米；{light['color']}；{light['art_purpose']}")
        lines.append("气氛：" + art["set"]["atmosphere"])
        if art["brief"]["secondary"]:
            sec = art["brief"]["secondary"]
            card = next(x for x in read(ROOT / "registries" / "styles.json")["styles"] if x["id"] == sec["style_id"])
            lines.append("辅助维度（仅此维度）：" + sec["dimension"] + "；" + card["dimensions"][sec["dimension"]] + "；理由：" + sec["reason"])
        color = [c for c in art["world"]["color_script"] if sid in c["shot_ids"]]
        color_ids = set().union(*(set(c["palette_ids"]) for c in color))
        lines += ["本镜色彩：" + "；".join(p["color"] + "用于" + p["role"] for p in art["world"]["palette"] if p["id"] in color_ids),
                  "色彩依据：" + "；".join(c["change_reason"] for c in color)]
        for aid in s["visible_assets"]:
            a = assets[aid]
            lines += [f"资产 {aid}（{a['name']}）：{a['design']}", "不可改：" + "；".join(a["identity_locks"])]
            for material in art["world"]["materials"]:
                if material["id"] in a["material_ids"]:
                    lines.append("材料：" + " → ".join(material[k] for k in ("base", "craft", "finish", "wear")))
            if a["graphic_text"]:
                lines.append("画内准确文字交给可编辑图形/合成任务：" + a["graphic_text"])
        lines += ["当前初态：" + dumps(before).strip(), "构图美术支持：" + "；".join(s["composition_support"][k] for k in ("background", "separation", "negative_space", "occlusion"))]
        for support in s["performance_support"]:
            lines.append(f"可读性 {support['entity_id']} / {','.join(support['required_parts'])}：{support['wardrobe_makeup']}；{support['background']}")
        for relation in s["relative_relations"]:
            lines.append(f"相对关系 {relation['subject_asset']} {relation['relation']} {relation['object_asset']}：{relation['criterion']}")
        if target["kind"] == "keyframe":
            lines.append("仅表现当前初态；这是一张关键帧，不叠加动作过程与末态。导演机位/构图需宿主合并。")
        else:
            lines += ["本镜允许状态变化：" + dumps(state_map[sid]["events"]).strip(), "末态：" + dumps(after).strip(),
                      "导演镜头/表演/时序：以 handoff.json 的 director_context 原文为准，美术不得改写。"]
        for r in shot_refs:
            lines.append(f"参考 {r['id']}：{r['file'] or '待制作'}；仅继承：{'；'.join(r['inherit'])}；不继承：{'；'.join(r['exclude'])}")
        for c in art["contract"]["clauses"]:
            if not c["shot_ids"] or sid in c["shot_ids"]:
                if target["kind"] == "keyframe" and any(p == "/events" or p.startswith("/events/") for p in c["paths"]):
                    lines.append("状态过程合同 " + c["id"] + " 交视频阶段执行；本张图仅使用上述当前初态。")
                    continue
                lines.append(f"合同 {c['id']} [{c['priority']}/{c['execution']['channel']}]：{c['requirement']}")
        texts[sid] = "\n".join(lines) + "\n"
    tasks, coverage = [], []
    for c in art["contract"]["clauses"]:
        task = dict(id="TASK_" + c["id"], clause_id=c["id"], **c["execution"], check_ids=c["check_ids"])
        tasks.append(task)
        for rid in task["reference_ids"]:
            if refs[rid]["status"] != "ready":
                blockers.append(task["id"] + ": REFERENCE_NOT_READY " + rid)
        coverage.append(dict(clause_id=c["id"], source_refs=c["source_refs"], values={p: pointer(art, p) for p in c["paths"]},
                             task_id=task["id"], channel=task["channel"], check_ids=c["check_ids"], status="EXPLICIT_MAPPING_NOT_VISUAL_PASS"))
    blockers = sorted(set(blockers))
    status = "BLOCKED" if blockers else "PLANNED"
    handoff = dict(schema_version="1.0", kind="OFFLINE_HANDOFF_NOT_API_REQUEST", art_sha256=object_hash(art),
                   target=target_id, status=status, execution_implemented=False, runnable=False,
                   api_submission_allowed=False, submitted=False, blockers=blockers, shots=handoff_shots, tasks=tasks)
    require(not schema_errors(handoff, "handoff"), "Internal handoff schema error")
    dependency = dict(art_sha256=object_hash(art), director=art["director"],
                      shots={s["id"]: {"asset_ids": s["visible_assets"], "reference_ids": s["required_references"],
                                         "director_pointer": s["director_pointer"]} for s in art["shots"]},
                      acceptance_invalidation="Any ArtIR/compiler/registry/director/reference byte change requires recompilation and new QA; local reuse needs host review")
    files = {"art-ir.json": dumps(art), "handoff.json": dumps(handoff), "constraint-coverage.json": dumps(coverage),
             "route-report.json": dumps(validated["route"]), "asset-plan.json": dumps({"assets": art["assets"], "references": art["references"]}),
             "dependency-index.json": dumps(dependency), "target-snapshot.json": dumps(target),
             "visual-bible.md": "# Visual Bible\n\n" + art["world"]["thesis"] + "\n\n```json\n" + dumps({"world": art["world"], "set": art["set"]}) + "```\n",
             "production-contract.md": render_contract(art, coverage)}
    files.update({"prompts/" + sid + ".txt": value for sid, value in texts.items()})
    receipt = dict(version=VERSION, art_sha256=object_hash(art), status=status, target=target_id, submitted=False,
                   validation="STATIC_VALID", coverage="EXPLICIT_MAPPING_NOT_VISUAL_PASS", media_acceptance="NOT_RUN",
                   toolchain_sha256=object_hash({str(p.relative_to(ROOT)): digest(p.read_bytes()) for name in ("scripts", "schemas", "registries")
                                                for p in sorted((ROOT / name).glob("*")) if p.is_file()}),
                   files={name: digest(value.encode()) for name, value in sorted(files.items())}, blockers=blockers)
    qa = dict(schema_version="1.0", art_sha256=object_hash(art), receipt_sha256=object_hash(receipt), status="NOT_RUN",
              records=[dict(check_id=c["id"], result="NOT_RUN", reviewer=None, observation=None, evidence=[]) for c in art["contract"]["checks"]])
    files.update({"receipt.json": dumps(receipt), "qa-report.json": dumps(qa)})
    out.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    return receipt


def render_contract(art, coverage):
    contract = art["contract"]
    lines = ["# 美术制作合同", "", f"{contract['id']} / revision {contract['version']} / ArtIR {art['revision']}", "",
             contract["scope"], "", "创作与执行协作协议；导演/摄影/表演决策通过只读引用交接。", ""]
    for c, mapping in zip(contract["clauses"], coverage):
        lines += [f"## {c['id']} · {c['priority']}", "", c["requirement"],
                  "", "来源：" + ", ".join(c["source_refs"]), "字段：" + ", ".join(c["paths"]),
                  "执行：" + mapping["task_id"] + " / " + c["execution"]["channel"] + " / " + c["execution"]["instruction"],
                  "验收：" + ", ".join(c["check_ids"]), "变更：新 revision，重编译；不能静默弱化硬要求。", ""]
    lines += ["## 来源、验收与执行边界", "", "```json", dumps({"sources": art["sources"], "checks": contract["checks"], "execution": contract["execution"]}).strip(), "```", ""]
    return "\n".join(lines)


def verify_qa(bundle, qa_path):
    bundle, qa_path = Path(bundle), Path(qa_path)
    receipt, art, qa = read(bundle / "receipt.json"), read(bundle / "art-ir.json"), read(qa_path)
    errors = schema_errors(qa, "qa-report")
    require(not errors, "QA schema: " + "; ".join(errors))
    require(receipt["status"] == "PLANNED", "Blocked bundle cannot be accepted")
    require(qa["art_sha256"] == receipt["art_sha256"] == object_hash(art), "QA ArtIR hash mismatch")
    require(qa["receipt_sha256"] == object_hash(receipt), "Stale QA receipt")
    for name, expected in receipt["files"].items():
        p = Path(name)
        require(not p.is_absolute() and ".." not in p.parts, "Unsafe receipt path")
        require(digest((bundle / p).read_bytes()) == expected, "Compiled artifact changed: " + name)
    checks = indexed(art["contract"]["checks"], "checks")
    records = {r["check_id"]: r for r in qa["records"]}
    require(len(records) == len(qa["records"]) and records.keys() == checks.keys(), "QA check set mismatch")
    accepted = True
    for cid, check in checks.items():
        record = records[cid]
        if record["result"] != "NOT_RUN":
            require(record["reviewer"] and record["observation"] and record["evidence"], "Review needs reviewer, observation and evidence")
            if check["gate"] in {"G3", "G4"}:
                require(any(e["kind"] in {"image", "video"} for e in record["evidence"]), "Media gate needs media evidence")
            if check["method"] == "playback":
                require(any(e["kind"] == "video" for e in record["evidence"]), "Playback needs video evidence")
            for evidence in record["evidence"]:
                path = resolve(qa_path.parent, evidence["file"])
                require(path.is_file() and digest(path.read_bytes()) == evidence["sha256"], "QA evidence missing or stale")
                if evidence["kind"] != "report":
                    inspect_media(path, evidence["kind"])
        if check["blocking"] and record["result"] != "PASS":
            accepted = False
    derived = "ACCEPTED_RECORDED" if accepted else "NOT_ACCEPTED"
    require(qa["status"] != "ACCEPTED_RECORDED" or accepted, "Declared acceptance contradicts records")
    return dict(status=derived, semantic_review="recorded by named reviewer, not inferred by this script")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "route", "compile"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        if name == "compile":
            command.add_argument("--target", default="generic-keyframe")
            command.add_argument("--out", type=Path, required=True)
    command = commands.add_parser("verify-qa")
    command.add_argument("bundle", type=Path)
    command.add_argument("qa", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "verify-qa":
            result = verify_qa(args.bundle, args.qa)
        else:
            art = read(args.input)
            if args.command == "compile":
                result = compile_art(art, args.input.parent, args.target, args.out)
            else:
                checked = validate(art, args.input.parent)
                result = checked["route"] if args.command == "route" else dict(status=checked["status"], art_sha256=object_hash(art))
        print(dumps(result), end="")
        return 2 if result.get("status") in {"BLOCKED", "NOT_ACCEPTED"} else 0
    except (ValueError, OSError, KeyError, IndexError, TypeError, subprocess.TimeoutExpired) as error:
        print(dumps(dict(status="INVALID", error=str(error))), file=sys.stderr, end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())
