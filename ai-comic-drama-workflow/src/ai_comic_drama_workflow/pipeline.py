from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from html import escape
from pathlib import Path
from typing import Any, Mapping

from .capabilities import probe_capabilities
from .layout import (
    ADAPTED_PROMPT_PACKAGE,
    ASSET_REGISTRY,
    CANONICAL_PROMPT_PACKAGE,
    FINAL_DELIVERY_INDEX,
    GENERATION_SEGMENTS,
    MEDIA_EXECUTION_INDEX,
    P01,
    P02,
    P03,
    P04,
    P05,
    P06,
    P07,
    P08,
    P09,
    P10,
    P11,
    P12,
    P13,
    SCENE_SPACE_PLAN,
    SHOT_PLAN,
    SHOT_TIMELINE_INDEX,
    SOURCE_REGISTRY,
)
from .storage import ProjectStore
from .utils import PACKAGE_ROOT, canonical_json, sha256_bytes, sha256_file, stable_id
from .validation import validate_project


DECISION_DEFINITIONS: dict[str, dict[str, Any]] = {
    'spatial_execution_fallback': {
        'question': '本地三维执行不可用或未通过实际验证；不能以白模提示词冒充完成。请选择后续动作。',
        'options': [{'id': 'supply-capability', 'label': '补齐执行能力后恢复'},
                    {'id': 'draft-export', 'label': '仅导出当前草稿，原目标保持未完成'},
                    {'id': 'pause', 'label': '暂停'}], 'allow_custom': False,
    },
    'reference_overflow_action': {
        'question': '必需图片超过视频参考槽位，不能自动删图。请选择返修方向。',
        'options': [{'id': 'revise-shot', 'label': '返修镜头，保留剧情结果'},
                    {'id': 'revise-reference-plan', 'label': '调整参考方案并重新审核'},
                    {'id': 'change-platform', 'label': '更换平台并重新校验'},
                    {'id': 'pause', 'label': '暂停'}], 'allow_custom': False,
    },
    'image_job_budget': {
        'question': '请确认本项目累计可派发的原生图片任务上限（含重试）；费用以宿主实际提示为准，额外付费仍需确认。',
        'options': [{'id': 3, 'label': '累计最多3次'}, {'id': 10, 'label': '累计最多10次'},
                    {'id': 30, 'label': '累计最多30次'}, {'id': 60, 'label': '累计最多60次'},
                    {'id': 'pause', 'label': '暂停'}],
        'allow_custom': False,
    },
    'platform_reference_action': {
        'question': '此适配器未验证角色图与故事板共同输入；请选择交付边界。',
        'options': [{'id': 'manual-unverified', 'label': '保留双图人工执行包，明确未验证平台'},
                    {'id': 'pause', 'label': '暂停并更换平台或参考方案'}], 'allow_custom': False,
    },
    'delivery_target': {
        'question': '请选择本次交付范围；草稿不能满足双图与三维正式验收。',
        'options': [{'id': 'dual-reference-previs', 'label': '审核后的双图包与本地预演', 'recommended': True},
                    {'id': 'prompt-draft', 'label': '明确标识的提示词草稿'}],
        'allow_custom': False,
    },
    "migration_action": {
        "question": "检测到旧版项目，请选择打开方式（迁移目标 Schema 3.0）。",
        "options": [
            {"id": "non-destructive-migrate", "label": "非破坏迁移", "recommended": True},
            {"id": "read-only", "label": "只读打开"},
            {"id": "copy-new", "label": "复制为新项目"},
        ],
        "allow_custom": False,
    },
    "work_depth": {
        "question": "请确认本项目的工作深度。",
        "options": [
            {"id": "standard", "label": "标准", "recommended": True},
            {"id": "quick", "label": "快速"},
            {"id": "deep", "label": "深度"},
        ],
        "allow_custom": False,
    },
    "adaptation_policy": {
        "question": "请确认改编时允许的扩展边界。",
        "options": [
            {"id": "limited-expansion", "label": "有限扩展", "recommended": True},
            {"id": "source-strict", "label": "严格忠于原资料"},
            {"id": "creative-first", "label": "创作优先"},
        ],
        "allow_custom": False,
    },
    "rights_status": {
        "question": "这些输入资料用于当前项目的权利状态是什么？",
        "options": [
            {"id": "owned-or-authorized", "label": "自有或已获授权"},
            {"id": "licensed", "label": "已取得许可"},
            {"id": "public-domain", "label": "公版资料"},
            {"id": "unverified-prompt-only", "label": "尚未核实，仅制作提示词"},
        ],
        "allow_custom": False,
    },
    "segment_duration_s": {
        "question": "每个制片生成段采用多长时间？连续镜头仍会保持 1—12 秒。",
        "options": [
            {"id": 10, "label": "10 秒"},
            {"id": 15, "label": "15 秒"},
            {"id": 20, "label": "20 秒"},
        ],
        "allow_custom": True,
    },
    "chapter_batch_size": {
        "question": "小说按多少章一批处理？短篇建议 2—4 章，长篇建议 5—8 章；可覆盖。",
        "options": [
            {"id": 2, "label": "2 章/批"},
            {"id": 3, "label": "3 章/批"},
            {"id": 4, "label": "4 章/批"},
            {"id": 5, "label": "5 章/批"},
            {"id": 6, "label": "6 章/批"},
            {"id": 7, "label": "7 章/批"},
            {"id": 8, "label": "8 章/批"},
        ],
        "allow_custom": True,
    },
    "visual_style": {
        "question": "请选择确定的视觉风格。",
        "options": [
            {"id": "cinematic-live-action", "label": "电影级真人写实"},
            {"id": "chinese-3d-animation", "label": "国漫3D"},
            {"id": "aaa-game-cg", "label": "3A游戏CG"},
            {"id": "premium-2d-anime", "label": "高规格2D动漫"},
            {"id": "reference-driven", "label": "参考图驱动"},
        ],
        "allow_custom": True,
    },
    "aspect_ratio": {
        "question": "请选择成片画幅。",
        "options": [
            {"id": "9:16", "label": "9:16 竖屏"},
            {"id": "16:9", "label": "16:9 横屏"},
            {"id": "1:1", "label": "1:1 方形"},
        ],
        "allow_custom": True,
    },
    "asset_image_strategy": {
        "question": "美术参考图采用哪种执行方式？",
        "options": [
            {"id": "codex-native", "label": "Codex 原生生图或宿主导入", "recommended": True},
            {"id": "generate-if-available", "label": "已注册本地测试能力"},
            {"id": "prompt-only", "label": "仅输出资产提示词"},
            {"id": "use-provided-only", "label": "仅使用用户已提供参考图"},
        ],
        "allow_custom": False,
    },
    "asset_image_fallback": {
        "question": "当前无法生成美术参考图，请选择后续方式。",
        "options": [
            {"id": "prompt-only", "label": "确认降级为提示词", "recommended": True},
            {"id": "supply-capability", "label": "补充图片能力后重试"},
            {"id": "pause", "label": "暂停项目"},
        ],
        "allow_custom": False,
    },
    "asset_review_decision": {
        "question": "请审核风格、角色、场景和道具资产。",
        "options": [
            {"id": "approve", "label": "批准并锁定", "recommended": True},
            {"id": "revise", "label": "返修美术资产"},
        ],
        "allow_custom": False,
    },
    "spatial_representation": {
        "question": "站位与空间采用哪种表示？",
        "options": [
            {"id": "2.5d-structured-previsualization", "label": "2.5D 结构化预演", "recommended": True},
            {"id": "2d-blocking", "label": "2D 站位图"},
            {"id": "verified-3d", "label": "已验证真实 3D", "availability": "unavailable", "reason": "当前未注册真实3D生成与验收能力"},
        ],
        "allow_custom": False,
    },
    "spatial_review_decision": {
        "question": "请审核场景坐标、站位、阵营与移动路径。",
        "options": [
            {"id": "approve", "label": "批准并锁定", "recommended": True},
            {"id": "revise", "label": "返修站位与空间"},
        ],
        "allow_custom": False,
    },
    "storyboard_depth": {
        "question": "请选择故事板的表达深度。",
        "options": [
            {"id": "full-dimensional", "label": "全维度分镜", "recommended": True},
            {"id": "narrative", "label": "叙事分镜"},
            {"id": "blocking", "label": "调度分镜"},
            {"id": "action", "label": "动作分镜"},
        ],
        "allow_custom": False,
    },
    "storyboard_views": {
        "question": "请选择需要派生的故事板视图，可多选。",
        "selection_mode": "multi",
        "min_selections": 0,
        "max_selections": 5,
        "options": [
            {"id": "action-breakdown", "label": "动作拆解", "recommended": True},
            {"id": "director-track", "label": "导演轨道", "recommended": True},
            {"id": "scene-overview", "label": "场景概览"},
            {"id": "structured-whitebox", "label": "结构化白模"},
            {"id": "reference-images", "label": "分镜参考图", "recommended": True},
        ],
        "allow_custom": False,
    },
    "storyboard_image_fallback": {
        "question": "当前无法产出故事板参考图，请确认后续路径。",
        "options": [
            {"id": "prompt-only", "label": "降级为逐关键时点提示词", "recommended": True},
            {"id": "supply-capability", "label": "补充图片能力后重试"},
            {"id": "pause", "label": "暂停项目"},
        ],
        "allow_custom": False,
    },
    "storyboard_review_decision": {
        "question": "请审核镜头计划、时空轨道与故事板参考图。",
        "options": [
            {"id": "approve", "label": "批准并锁定", "recommended": True},
            {"id": "revise", "label": "返修故事板"},
        ],
        "allow_custom": False,
    },
    "target_platform": {
        "question": "请选择提示词目标平台。",
        "options": [
            {"id": "platform-neutral", "label": "平台中立"},
            {"id": "seedance-2.0-doubao", "label": "Seedance 2.0 / Doubao"},
        ],
        "allow_custom": False,
    },
    "media_execution_mode": {
        "question": "请选择本阶段的视频媒体执行方式。",
        "options": [
            {"id": "prompt-only", "label": "仅提示词与人工清单", "recommended": True},
            {"id": "execute-if-available", "label": "可用且已授权时执行"},
            {"id": "manual-external", "label": "仅登记外部人工执行"},
            {"id": "imported-local", "label": "使用已导入视频进行本地剪辑"},
        ],
        "allow_custom": False,
    },
    "voice_strategy": {
        "question": "请选择配音策略。",
        "options": [
            {"id": "original-audio", "label": "原声"},
            {"id": "tts", "label": "TTS"},
            {"id": "voice-script-only", "label": "仅配音脚本"},
            {"id": "no-dialogue", "label": "无对白"},
        ],
        "allow_custom": False,
    },
    "subtitle_language": {
        "question": "请选择字幕与发布语言。",
        "options": [
            {"id": "zh-CN", "label": "简体中文"},
            {"id": "zh-TW", "label": "繁体中文"},
            {"id": "en", "label": "英文"},
            {"id": "none", "label": "不使用字幕"},
        ],
        "allow_custom": True,
    },
    "conflict_policy": {
        "question": "多份叙事资料可能冲突，请选择合并规则；核心事实冲突仍需逐项确认。",
        "options": [
            {"id": "approved-downstream-priority", "label": "已批准下游职责优先"},
            {"id": "manual-per-conflict", "label": "逐项人工决定"},
            {"id": "source-priority", "label": "原始资料优先"},
        ],
        "allow_custom": False,
    },
    "core_conflict_resolution": {
        "question": "检测到结局、身份、关系、动机或世界规则等核心冲突，请提供解决方式。",
        "options": [
            {"id": "manual-resolution-attached", "label": "已附逐项解决方案"},
            {"id": "pause", "label": "暂不继续"},
        ],
        "allow_custom": True,
    },
    "likeness_authorization": {
        "question": "资料涉及真实人物肖像，请确认当前项目的使用边界。",
        "options": [
            {"id": "authorized", "label": "已获明确授权"},
            {"id": "prompt-only", "label": "仅制作提示词，不上传或生成"},
            {"id": "exclude-likeness", "label": "排除真实肖像"},
        ],
        "allow_custom": False,
    },
    "external_media_action": {
        "question": "当前媒体能力需要账号或可能产生费用，请选择本次执行边界。",
        "options": [
            {"id": "prompt-only", "label": "保持提示词交付"},
            {"id": "authorized-for-current-provider", "label": "仅授权当前已说明的提供方"},
        ],
        "allow_custom": False,
    },
    "visual_external_action": {
        "question": "美术参考图能力需要账号或可能产生费用，请确认本阶段执行边界。",
        "options": [
            {"id": "prompt-only", "label": "仅输出提示词", "recommended": True},
            {"id": "authorized-for-current-provider", "label": "授权当前提供方"},
        ],
        "allow_custom": False,
    },
    "video_external_action": {
        "question": "视频生成能力需要账号或可能产生费用，请确认本阶段执行边界。",
        "options": [
            {"id": "prompt-only", "label": "仅输出视频提示词", "recommended": True},
            {"id": "authorized-for-current-provider", "label": "授权当前提供方"},
        ],
        "allow_custom": False,
    },
    "audio_external_action": {
        "question": "外部配音或音频能力需要账号或可能产生费用，请确认本阶段执行边界。",
        "options": [
            {"id": "script-only", "label": "仅输出脚本与时间码", "recommended": True},
            {"id": "authorized-for-current-provider", "label": "授权当前提供方"},
        ],
        "allow_custom": False,
    },
    "unreadable_source_action": {
        "question": "存在无法可靠读取的叙事资料。请选择暂停补充文字，或明确排除这些资料。",
        "options": [
            {"id": "pause-and-supply-text", "label": "暂停并补充文字"},
            {"id": "exclude-unreadable", "label": "排除不可读资料"},
        ],
        "allow_custom": False,
    },
}


def decision_fields(field_ids: list[str]) -> list[dict[str, Any]]:
    fields = []
    for field_id in field_ids:
        definition = DECISION_DEFINITIONS[field_id]
        field = {"id": field_id, **definition}
        field.setdefault("selection_mode", "single")
        field.setdefault("min_selections", 1)
        if field["selection_mode"] == "multi":
            field.setdefault("max_selections", len(field["options"]))
        options = []
        for index, source in enumerate(field["options"]):
            option = dict(source)
            option.setdefault("availability", "available")
            option.setdefault("recommended", index == 0)
            option.setdefault("consequence", "该选择只对当前阶段及依赖下游生效。")
            options.append(option)
        field["options"] = options
        fields.append(field)
    return fields


def validate_decision(field: dict[str, Any], selection: Any) -> None:
    available_options = [
        option for option in field["options"] if option.get("availability", "available") == "available"
    ]
    option_ids = [option["id"] for option in available_options]
    if field.get("selection_mode", "single") == "multi":
        if not isinstance(selection, list):
            raise ValueError(f"{field['id']} must be a list")
        if len(selection) != len({repr(item) for item in selection}):
            raise ValueError(f"{field['id']} must not contain duplicate selections")
        minimum = int(field.get("min_selections", 0))
        maximum = int(field.get("max_selections", len(option_ids)))
        if not minimum <= len(selection) <= maximum:
            raise ValueError(f"{field['id']} must contain {minimum}-{maximum} selections")
        unknown = [item for item in selection if item not in option_ids]
        if unknown:
            raise ValueError(f"{field['id']} contains unavailable or unknown selections: {unknown!r}")
        return
    if selection in option_ids:
        return
    if not field.get("allow_custom"):
        raise ValueError(f"{field['id']} must be one of {option_ids!r}")
    if field["id"] == "segment_duration_s":
        if not isinstance(selection, (int, float)) or isinstance(selection, bool) or not 1 <= selection <= 120:
            raise ValueError("Custom segment_duration_s must be a number from 1 to 120")
    elif field["id"] == "chapter_batch_size":
        if not isinstance(selection, int) or isinstance(selection, bool) or not 1 <= selection <= 50:
            raise ValueError("Custom chapter_batch_size must be an integer from 1 to 50")
    elif not isinstance(selection, str) or not selection.strip():
        raise ValueError(f"Custom {field['id']} must be a non-empty string")


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_prompt_for_shot(shot: dict[str, Any]) -> tuple[str, str]:
    fact_keys = [
        "shot_id",
        "index",
        "segment_id",
        "scene_id",
        "duration_s",
        "narrative_purpose",
        "character_tracks",
        "camera_track",
        "audio_track",
        "director_track",
        "spatial_track",
        "scene_fixed_track",
        "environment",
        "lighting",
        "continuity",
        "required_asset_ids",
        "selected_reference_ids",
        "negative_constraints",
        "timing",
        "prop_tracks",
    ]
    facts = {key: shot.get(key) for key in fact_keys}
    fact_hash = sha256_bytes(canonical_json(facts).encode("utf-8"))
    character_lines = []
    for track in facts["character_tracks"] or []:
        trajectory = ", ".join(
            f"{point.get('time_s')}s@{_compact(point.get('position'))} {point.get('pose', '')} "
            f"朝向:{point.get('facing')} 视线:{point.get('gaze')}"
            for point in track.get("trajectory", [])
        )
        actions = ", ".join(
            f"{item.get('start_s')}-{item.get('end_s')}s {item.get('phase')}:{item.get('description')} "
            f"互动:{item.get('interaction_target')} 道具:{_compact(item.get('prop_ids', []))}"
            for item in track.get("action_events", [])
        )
        emotions = ", ".join(
            f"{item.get('start_s')}-{item.get('end_s')}s {item.get('emotion')}({item.get('intensity')}) "
            f"表演:{_compact(item.get('visible_cues', []))} 触发:{item.get('trigger')}"
            for item in track.get("emotion_events", [])
        )
        character_lines.append(
            f"{track.get('character_id')}：轨迹[{trajectory}]；动作[{actions}]；情绪[{emotions}]"
        )
    prompt = "\n".join(
        [
            f"镜头 {facts['shot_id']}，时长 {facts['duration_s']} 秒。",
            f"叙事目的：{facts['narrative_purpose']}",
            *character_lines,
            f"环境：{_compact(facts['environment'])}",
            f"摄影机轨道：{_compact(facts['camera_track'])}",
            f"导演轨道：{_compact(facts['director_track'])}",
            f"空间轨道：{_compact(facts['spatial_track'])}",
            f"场景固定轨道：{_compact(facts['scene_fixed_track'])}",
            f"灯光：{_compact(facts['lighting'])}",
            f"声音轨道：{_compact(facts['audio_track'])}",
            f"连续性：{_compact(facts['continuity'])}",
            f"必需资产：{_compact(facts['required_asset_ids'])}",
            f"上传参考槽位：{_compact(facts['selected_reference_ids'])}",
            f"禁止项：{_compact(facts['negative_constraints'])}",
        ]
    )
    return prompt, fact_hash


def canonical_record_for_shot(shot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: shot.get(key)
        for key in (
            "shot_id",
            "index",
            "segment_id",
            "scene_id",
            "duration_s",
            "narrative_purpose",
            "character_tracks",
            "camera_track",
            "audio_track",
            "director_track",
            "spatial_track",
            "scene_fixed_track",
            "environment",
            "lighting",
            "continuity",
            "required_asset_ids",
            "selected_reference_ids",
            "negative_constraints",
            "timing",
            "prop_tracks",
        )
    }


def _normalized_position(value: object) -> tuple[float, float, float]:
    if not isinstance(value, dict):
        return 0.5, 0.5, 0.0
    coordinates = []
    for key, default in (("x", 0.5), ("y", 0.5), ("z", 0.0)):
        raw = value.get(key, default)
        number = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else default
        coordinates.append(min(1.0, max(0.0, number)))
    return coordinates[0], coordinates[1], coordinates[2]


def _scene_svg(scene: dict[str, Any]) -> str:
    width, height = 960, 540
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#111827"/>',
        '<rect x="60" y="60" width="840" height="420" fill="#1f2937" stroke="#94a3b8" stroke-width="2"/>',
        f'<text x="60" y="36" fill="#f8fafc" font-size="22">SceneSpace {escape(str(scene.get("scene_id", "unknown")))}</text>',
    ]
    for zone in scene.get("zones", []):
        if not isinstance(zone, dict):
            continue
        x, y, _ = _normalized_position(zone.get("position", zone))
        label = escape(str(zone.get("zone_id") or zone.get("name") or "zone"))
        elements.append(
            f'<rect x="{70 + x * 760:.1f}" y="{70 + y * 340:.1f}" width="120" height="60" fill="#334155" stroke="#64748b"/>'
        )
        elements.append(f'<text x="{78 + x * 760:.1f}" y="{104 + y * 340:.1f}" fill="#e2e8f0" font-size="14">{label}</text>')
    for index, placement in enumerate(scene.get("character_placements", []), start=1):
        if not isinstance(placement, dict):
            continue
        x, y, _ = _normalized_position(placement.get("position"))
        px, py = 90 + x * 780, 90 + y * 360
        label = escape(str(placement.get("character_id") or f"CHAR-{index:03d}"))
        elements.extend(
            [
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="18" fill="#38bdf8" stroke="#e0f2fe"/>',
                f'<text x="{px + 24:.1f}" y="{py + 5:.1f}" fill="#f8fafc" font-size="14">{label}</text>',
            ]
        )
    elements.append('<text x="60" y="515" fill="#94a3b8" font-size="13">structured_previsualization; not a verified 3D model</text>')
    elements.append("</svg>\n")
    return "\n".join(elements)


def _key_moments(shot: dict[str, Any]) -> list[dict[str, Any]]:
    duration = float(shot["duration_s"])
    if "storyboard_key_time_s" in shot:
        selected = shot["storyboard_key_time_s"]
        if isinstance(selected, bool) or not isinstance(selected, (int, float)) or not 0 <= selected <= duration:
            raise ValueError("Selected storyboard key time must be inside the shot")
        return [{"moment_id": "key", "time_s": float(selected), "purpose": "selected-representative-frame"}]
    candidates: list[tuple[int, float, str, str]] = []
    for track in shot.get("character_tracks", []):
        character_id = str(track.get("character_id", "unknown"))
        for action in track.get("action_events", []):
            phase_priority = {"key": 100, "development": 70, "start": 50, "end": 40}.get(str(action.get("phase")), 20)
            time_s = (float(action.get("start_s", 0)) + float(action.get("end_s", 0))) / 2
            candidates.append((phase_priority, time_s, str(action.get("description", "action")), character_id))
        for emotion in track.get("emotion_events", []):
            priority = int(float(emotion.get("intensity", 0)) * 90)
            time_s = (float(emotion.get("start_s", 0)) + float(emotion.get("end_s", 0))) / 2
            candidates.append((priority, time_s, str(emotion.get("emotion", "emotion")), character_id))
    moments = [{"moment_id": "start", "time_s": 0.0, "purpose": "initial-state"}]
    if candidates:
        _, time_s, purpose, character_id = max(candidates, key=lambda item: (item[0], -item[1], item[2]))
        clamped = round(min(duration, max(0.0, time_s)), 3)
        if 0 < clamped < duration:
            moments.append(
                {
                    "moment_id": "key",
                    "time_s": clamped,
                    "purpose": purpose,
                    "character_id": character_id,
                }
            )
    if shot.get("continuity", {}).get("start_state") != shot.get("continuity", {}).get("end_state"):
        moments.append({"moment_id": "end", "time_s": duration, "purpose": "end-state"})
    return moments[:3]


def _shot_previsualization_svg(shot: dict[str, Any], moments: list[dict[str, Any]]) -> str:
    width = 420 * len(moments)
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="300" viewBox="0 0 {width} 300">',
        '<rect width="100%" height="100%" fill="#0f172a"/>',
    ]
    for panel, moment in enumerate(moments):
        x0 = panel * 420
        time_s = float(moment["time_s"])
        elements.append(f'<rect x="{x0 + 12}" y="38" width="396" height="220" fill="#1e293b" stroke="#64748b"/>')
        elements.append(f'<text x="{x0 + 20}" y="26" fill="#f8fafc" font-size="16">{escape(str(shot["shot_id"]))} @ {time_s:g}s</text>')
        for track_index, track in enumerate(shot.get("character_tracks", []), start=1):
            trajectory = sorted(track.get("trajectory", []), key=lambda item: float(item.get("time_s", 0)))
            point = min(trajectory, key=lambda item: abs(float(item.get("time_s", 0)) - time_s)) if trajectory else {}
            x, y, _ = _normalized_position(point.get("position"))
            px, py = x0 + 40 + x * 330, 62 + y * 160
            label = escape(str(track.get("character_id") or f"CHAR-{track_index:03d}"))
            elements.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="14" fill="#f59e0b"/>')
            elements.append(f'<text x="{px + 18:.1f}" y="{py + 5:.1f}" fill="#f8fafc" font-size="12">{label}</text>')
        elements.append(f'<text x="{x0 + 20}" y="282" fill="#94a3b8" font-size="12">{escape(str(moment.get("purpose", "")))}</text>')
    elements.append('<text x="12" y="296" fill="#64748b" font-size="10">structured_previsualization; not a verified 3D model</text>')
    elements.append("</svg>\n")
    return "\n".join(elements)


def _optional_svg_png(store: ProjectStore, svg_relative: str) -> dict[str, Any] | None:
    converter = shutil.which("rsvg-convert") or shutil.which("magick")
    if not converter:
        return None
    png_relative = str(Path(svg_relative).with_suffix(".png"))
    source = store.path(svg_relative)
    with tempfile.TemporaryDirectory(prefix='ai-comic-svg-') as temporary:
        target = Path(temporary) / 'preview.png'
        command = ([converter, '-o', str(target), str(source)] if Path(converter).name == 'rsvg-convert'
                   else [converter, str(source), str(target)])
        process = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        if process.returncode != 0 or not target.exists() or not inspect_image(target)['verified']:
            return None
        store.copy_source(target, png_relative)
    return {
        "path": png_relative,
        "converter": converter,
        "status": "structured_previsualization",
        "verified_3d": False,
        **inspect_image(store.path(png_relative)),
    }


def inspect_video(path: Path, *, require_audio: bool = False) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"verified": False, "reason": "ffprobe unavailable", "sha256": sha256_file(path)}
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if process.returncode != 0:
        return {
            "verified": False,
            "reason": process.stderr.strip() or "ffprobe failed",
            "sha256": sha256_file(path),
        }
    payload = json.loads(process.stdout)
    duration = float(payload.get("format", {}).get("duration", 0) or 0)
    streams = payload.get("streams", [])
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    ffmpeg = shutil.which("ffmpeg")
    decode_check: dict[str, Any] = {"status": "unavailable", "evidence": "ffmpeg unavailable"}
    black_check: dict[str, Any] = {"status": "unavailable", "evidence": "ffmpeg unavailable"}
    freeze_check: dict[str, Any] = {"status": "unavailable", "evidence": "ffmpeg unavailable"}
    if ffmpeg:
        decode = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        decode_check = {
            "status": "passed" if decode.returncode == 0 else "failed",
            "evidence": decode.stderr.strip(),
        }
        black = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                str(path),
                "-vf",
                "blackdetect=d=0.1:pix_th=0.10:pic_th=0.98",
                "-an",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        black_durations = [
            float(value)
            for value in re.findall(r"black_duration:([0-9.]+)", black.stderr)
        ]
        black_total = sum(black_durations)
        black_check = {
            "status": "passed" if duration <= 0 or black_total < duration * 0.98 else "failed",
            "black_duration_s": round(black_total, 3),
            "threshold": "fails when at least 98% of the file is detected as black",
        }
        freeze = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                str(path),
                "-vf",
                "freezedetect=n=-60dB:d=0.5",
                "-an",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        freeze_durations = [
            float(value)
            for value in re.findall(r"freeze_duration: ([0-9.]+)", freeze.stderr)
        ]
        freeze_starts = [float(value) for value in re.findall(r'freeze_start: ([0-9.]+)', freeze.stderr)]
        freeze_ends = [float(value) for value in re.findall(r'freeze_end: ([0-9.]+)', freeze.stderr)]
        if len(freeze_starts) > len(freeze_ends):
            freeze_durations.append(max(0, duration-freeze_starts[-1]))
        freeze_check = {
            "status": "review" if freeze_durations else "passed",
            "freeze_durations_s": freeze_durations,
            "note": "Freeze findings are advisory because a static dramatic hold may be intentional.",
        }
    verified = (
        duration > 0
        and bool(video_streams)
        and decode_check["status"] == "passed"
        and black_check["status"] != "failed"
        and (not require_audio or bool(audio_streams))
    )
    return {
        "verified": verified,
        "sha256": sha256_file(path),
        "duration_s": duration,
        "streams": streams,
        "video_track_present": bool(video_streams),
        "audio_track_present": bool(audio_streams),
        "full_decode": decode_check,
        "black_frame_scan": black_check,
        "freeze_frame_scan": freeze_check,
        "checks": [
            "container-readable",
            "positive-duration",
            "codec-and-stream-metadata",
            "full-decode",
            "black-frame-scan",
            "freeze-frame-scan",
            "audio-track-present" if require_audio else "audio-track-recorded",
        ],
    }


def inspect_image(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        return {"verified": False, "reason": "Pillow unavailable", "sha256": sha256_file(path)}
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            mode = image.mode
            image_format = image.format
    except Exception as error:
        return {
            "verified": False,
            "reason": f"image inspection failed: {type(error).__name__}: {error}",
            "sha256": sha256_file(path),
        }
    return {
        "verified": width > 0 and height > 0,
        "sha256": sha256_file(path),
        "width": width,
        "height": height,
        "mode": mode,
        "format": image_format,
        "checks": ["decode", "positive-canvas", "format-and-mode-recorded"],
    }


def inspect_audio(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"verified": False, "reason": "ffprobe unavailable", "sha256": sha256_file(path)}
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if process.returncode != 0:
        return {"verified": False, "reason": process.stderr.strip() or "ffprobe failed", "sha256": sha256_file(path)}
    payload = json.loads(process.stdout)
    duration = float(payload.get("format", {}).get("duration", 0) or 0)
    streams = payload.get("streams", [])
    return {
        "verified": duration > 0 and any(item.get("codec_type") == "audio" for item in streams),
        "sha256": sha256_file(path),
        "duration_s": duration,
        "streams": streams,
        "checks": ["container-readable", "positive-duration", "audio-track-present"],
    }


class DeterministicPipeline:
    def __init__(self, store: ProjectStore, *, environment: Mapping[str, str] | None = None):
        self.store = store
        self.environment = environment if environment is not None else os.environ

    def execute(self, stage_id: str, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"stage_{stage_id}", None)
        if handler is None:
            raise ValueError(f"No deterministic handler for stage {stage_id}")
        return handler(project, state)

    def stage_project_configuration(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return {
            "work_depth": state["decisions"]["work_depth"],
            "adaptation_policy": state["decisions"]["adaptation_policy"],
            "decision_refs": {
                key: state.get("decision_approvals", {}).get(key)
                for key in ("work_depth", "adaptation_policy")
            },
        }

    def stage_gap_resolution(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        registry = self.store.read(SOURCE_REGISTRY)
        brief = self.store.read(f"{P02}/intake-brief.json")
        unresolved = [
            {
                "source_id": source["source_id"],
                "issue": source.get("extraction_status"),
                "impact": "Text must be supplied before semantic use",
            }
            for source in registry["sources"]
            if source.get("extraction_status") in {"requires-pypdf-or-ocr", "requires-ocr", "not-textual"}
            and not str(source.get("kind", "")).startswith("reference-")
            and not source.get("excluded")
        ]
        return {
            "entry_mode": registry["entry_mode"],
            "rights_status": state["decisions"]["rights_status"],
            "external_generation_blocked": project.get("external_generation_blocked", True),
            "unresolved_inputs": unresolved,
            "conflicts": brief.get("conflicts", []),
            "conflict_policy": state["decisions"].get("conflict_policy"),
            "auto_expansion_boundary": [
                "transitions",
                "actions",
                "expressions",
                "environment reactions",
                "shot links",
                "non-plot sound effects",
            ],
            "unknowns": brief.get("unknowns", []),
        }

    def stage_style_choice(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return {
            "visual_style": state["decisions"]["visual_style"],
            "aspect_ratio": state["decisions"]["aspect_ratio"],
            "asset_image_strategy": state["decisions"]["asset_image_strategy"],
            "decision_refs": state.get("decision_approvals", {}),
        }

    def stage_visual_capability_probe(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return {
            "scope": "visual-assets-and-storyboard-references",
            "capabilities": probe_capabilities(environment=self.environment),
        }

    def stage_asset_generation_or_prompt(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        plan = self.store.read(f"{P07}/asset-plan.json")
        style = self.store.read(f"{P07}/style-choice.json")
        capabilities = self.store.read(f"{P07}/capability-snapshot.json")["capabilities"]
        registry = self.store.read(SOURCE_REGISTRY)
        strategy = state["decisions"]["asset_image_strategy"]
        allowed = (
            not project.get("external_generation_blocked", True)
            and state["decisions"].get("visual_external_action") != "prompt-only"
        )
        fixture = self.environment.get("AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR")
        can_fixture = bool(
            allowed
            and strategy == "generate-if-available"
            and fixture
            and capabilities["image_generation"]["status"] == "available"
            and capabilities["image_generation"].get("provider") == "local-fixture"
        )
        provided = {
            str(item["source_id"]): item
            for item in registry.get("sources", [])
            if item.get("kind") == "reference-image"
        }
        assets = []
        previous_assets = {a['asset_id']: a for a in self.store.read(ASSET_REGISTRY)['assets']} if self.store.exists(ASSET_REGISTRY) else {}
        degradations: list[dict[str, Any]] = []
        allowed_types = {
            "style-reference",
            "character-reference",
            "scene-reference",
            "prop-reference",
            "other",
        }
        planned_types = {str(item.get("asset_type")) for item in plan.get("assets", []) if isinstance(item, dict)}
        required_categories = {'style-reference', 'scene-reference'}
        if self.store.read(f'{P07}/visual-bible.json').get('characters'):
            required_categories.add('character-reference')
        missing_categories = required_categories - planned_types
        if missing_categories:
            raise ValueError(
                f"Asset plan must cover style, character, and scene references; missing {sorted(missing_categories)}"
            )
        seen_asset_ids: set[str] = set()
        for index, asset in enumerate(plan.get("assets", []), start=1):
            asset_id = str(asset.get("asset_id") or stable_id("asset", project["project_id"], index, _compact(asset)))
            if asset_id in seen_asset_ids:
                raise ValueError(f"Asset IDs must be unique: {asset_id}")
            seen_asset_ids.add(asset_id)
            asset_type = str(asset.get("asset_type", "other"))
            if asset_type not in allowed_types:
                asset_type = "other"
            source_refs = list(asset.get("source_refs", asset.get("reference_ids", [])))
            item: dict[str, Any] = {
                "asset_id": asset_id,
                "entity_ids": list(asset.get('entity_ids', [])),
                "asset_type": asset_type,
                "version": int(asset.get("version", 1)),
                "description": str(asset.get("description") or f"{asset_type} {asset_id}"),
                "source_refs": source_refs,
                "continuity_constraints": list(asset.get("continuity_constraints", [])),
                "forbidden_inheritance": list(asset.get("forbidden_inheritance", [])),
                "prompt": (
                    f"视觉风格：{style['visual_style']}；画幅：{style['aspect_ratio']}；"
                    f"资产规格：{_compact(asset)}"
                ),
                "execution_status": "prompt_ready",
            }
            provided_source = next((provided[ref] for ref in source_refs if ref in provided), None)
            if strategy == 'codex-native' or (strategy == 'use-provided-only' and not provided_source):
                if strategy == 'codex-native' and not allowed:
                    raise ValueError('Native generation needs confirmed source rights and external-use authorization')
                from .media_bridge import acquire_candidate
                receipt = acquire_candidate(self.store, stage_id='asset_generation_or_prompt', key=asset_id,
                    prompt=item['prompt'], bindings=asset.get('reference_bindings', []), folder=f'{P07}/assets/generated', output_kind='asset',
                    revision_token=state.get('creative_revision_tokens', {}).get('asset:' + asset_id),
                    allowed_providers=('provided',) if strategy == 'use-provided-only' else ('codex-imagegen', 'provided'))
                item.update(media_path=receipt['media_path'], sha256=receipt['sha256'],
                            execution_status='provided' if receipt['provider'] == 'provided' else 'generated_verified', provider=receipt['provider'],
                            file_validation=receipt['file_validation'], creative_review='pending')
            elif strategy == "use-provided-only" and provided_source:
                item.update(
                    {
                        "execution_status": "provided",
                        "media_path": provided_source["stored_path"],
                        "sha256": provided_source["sha256"],
                    }
                )
            elif can_fixture:
                candidates = [
                    path
                    for suffix in (".png", ".jpg", ".jpeg", ".webp")
                    if (path := Path(str(fixture)) / f"{asset_id}{suffix}").is_file()
                ]
                if candidates:
                    source = candidates[0]
                    relative = f"{P07}/assets/generated/{asset_id}{source.suffix.lower()}"
                    self.store.copy_source(source, relative)
                    inspection = inspect_image(self.store.path(relative))
                    item.update(
                        {
                            "execution_status": "generated_verified" if inspection["verified"] else "generated_unverified",
                            "media_path": relative,
                            **inspection,
                        }
                    )
            if item["execution_status"] == "prompt_ready" and strategy == "generate-if-available":
                degradations.append(
                    {
                        "code": "asset-image-prompt-fallback",
                        "asset_id": asset_id,
                        "reason": state["decisions"].get("asset_image_fallback", "provider-unavailable"),
                    }
                )
            previous = previous_assets.get(asset_id)
            if previous:
                changed = previous.get('prompt') != item['prompt'] or previous.get('sha256') != item.get('sha256')
                item['version'] = max(item['version'], previous['version'] + 1) if changed else previous['version']
            assets.append(item)
        verified = len([item for item in assets if item["execution_status"] in {"generated_verified", "provided"}])
        return {
            "assets": assets,
            "execution_status": (
                "media_verified" if assets and verified == len(assets) else "media_partial" if verified else "prompt_ready"
            ),
            "degradations": degradations,
            "boundary": "Prompt-ready entries are not generated reference images.",
        }

    def stage_asset_quality_gate(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        registry = self.store.read(ASSET_REGISTRY)
        return {
            "review_status": "approved",
            "user_decision": state["decisions"]["asset_review_decision"],
            "checked_asset_ids": [item["asset_id"] for item in registry.get("assets", [])],
            "prompt_only_assets": [
                item["asset_id"] for item in registry.get("assets", []) if item["execution_status"] == "prompt_ready"
            ],
        }

    def stage_spatial_preview(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        plan = self.store.read(SCENE_SPACE_PLAN)
        previews = []
        for index, scene in enumerate(plan.get("scenes", []), start=1):
            scene_id = str(scene.get("scene_id") or f"SCENE-{index:03d}")
            safe = re.sub(r"[^0-9A-Za-z._-]+", "-", scene_id).strip("-.") or f"scene-{index:03d}"
            relative = f"{P08}/previews/{safe}.svg"
            digest = self.store.write_text(relative, _scene_svg(scene))
            previews.append(
                {
                    "scene_id": scene_id,
                    "path": relative,
                    "sha256": digest,
                    "media_type": "image/svg+xml",
                    "status": "structured_previsualization",
                    "verified_3d": False,
                    "png": _optional_svg_png(self.store, relative),
                }
            )
            if state['decisions'].get('delivery_target') == 'dual-reference-previs':
                from .blender_adapter import render_shot, overview_shot
                previews[-1]['blender'] = render_shot(self.store, scene, overview_shot(scene),
                    folder=f'{P08}/blender/{safe}', size=(640, 640), key_times=[0])
        return {
            "representation": plan["representation"],
            "previews": previews,
            "boundary": "SVG previews are deterministic spatial diagrams, not verified 3D models.",
        }

    def stage_spatial_lock_gate(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        plan = self.store.read(SCENE_SPACE_PLAN)
        return {
            "review_status": "approved",
            "user_decision": state["decisions"]["spatial_review_decision"],
            "locked_scene_ids": [item["scene_id"] for item in plan.get("scenes", [])],
            "representation": plan["representation"],
        }

    def stage_storyboard_choice(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return {
            "depth": state["decisions"]["storyboard_depth"],
            "views": state["decisions"]["storyboard_views"],
            "decision_refs": {
                key: state.get("decision_approvals", {}).get(key)
                for key in ("storyboard_depth", "storyboard_views")
            },
        }

    def stage_storyboard_package(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        index = self.store.read(SHOT_TIMELINE_INDEX)
        choice = self.store.read(f"{P09}/storyboard-choice.json")
        views = list(choice.get("views", []))
        shots = []
        previous_shot = None
        previous_scene = None
        for entry in sorted(index.get("shots", []), key=lambda item: item["index"]):
            shot = self.store.read(entry["path"])
            moments = _key_moments(shot)
            derived_views: dict[str, Any] = {}
            if "action-breakdown" in views:
                derived_views["action-breakdown"] = [
                    {
                        "character_id": track["character_id"],
                        "action_events": track.get("action_events", []),
                    }
                    for track in shot.get("character_tracks", [])
                ]
            if "director-track" in views:
                derived_views["director-track"] = shot.get("director_track", [])
            if "scene-overview" in views:
                derived_views["scene-overview"] = {
                    "scene_id": shot["scene_id"],
                    "scene_space_path": SCENE_SPACE_PLAN,
                    "spatial_track": shot.get("spatial_track", []),
                    "scene_fixed_track": shot.get("scene_fixed_track", []),
                }
            if "reference-images" in views:
                derived_views["reference-images"] = {
                    "status": "planned_by_key_moments",
                    "moment_ids": [item["moment_id"] for item in moments],
                }
            record: dict[str, Any] = {
                "shot_id": shot["shot_id"],
                "timeline_path": entry["path"],
                "timeline_sha256": sha256_file(self.store.path(entry["path"])),
                "key_moments": moments,
                "derived_views": derived_views,
            }
            from .spatial import evaluate_state
            scene = next(s for s in self.store.read(SCENE_SPACE_PLAN)['scenes'] if s['scene_id'] == shot['scene_id'])
            record['evaluated_frames'] = [evaluate_state(scene, shot, m['time_s']) for m in moments]
            from .spatial_qa import audit_shot, audit_handoff
            record['spatial_diagnostics'] = audit_shot(scene, shot)
            if previous_shot is not None:
                record['spatial_diagnostics']['handoff_issues'] = audit_handoff(previous_scene, previous_shot, scene, shot)
                transition = shot.get('continuity', {}).get('transition', {})
                if transition.get('type') in {'time_jump', 'scene_change'}:
                    from .references import current_approval
                    try:
                        current_approval(self.store, transition.get('approval_ref'))
                    except ValueError as error:
                        record['spatial_diagnostics']['handoff_issues'].append(str(error))
            if state['decisions'].get('delivery_target') == 'dual-reference-previs':
                if not record['spatial_diagnostics']['passed'] or record['spatial_diagnostics'].get('handoff_issues'):
                    raise ValueError('Spatial quality gate requires revision: ' + _compact(record['spatial_diagnostics']))
                from .blender_adapter import render_shot
                ratio = str(state['decisions']['aspect_ratio']).split(':')
                width, height = map(float, ratio)
                size = (640, max(2, round(640 * height / width / 2) * 2))
                record['blender_stills'] = render_shot(self.store, scene, shot,
                    folder=f'{P09}/blender/{shot["shot_id"]}/stills', size=size,
                    key_times=[m['time_s'] for m in moments])
                record['blender_motion'] = render_shot(self.store, scene, shot,
                    folder=f'{P09}/blender/{shot["shot_id"]}/motion', size=size, animate=True)
            previous_shot, previous_scene = shot, scene
            if "structured-whitebox" in views:
                relative = f"{P09}/previsualization/{shot['shot_id']}.svg"
                digest = self.store.write_text(relative, _shot_previsualization_svg(shot, moments))
                record["previsualization"] = {
                    "path": relative,
                    "sha256": digest,
                    "status": "structured_previsualization",
                    "verified_3d": False,
                    "png": _optional_svg_png(self.store, relative),
                }
                derived_views["structured-whitebox"] = record["previsualization"]
            shots.append(record)
        return {
            "depth": choice["depth"],
            "views": views,
            "shots": shots,
            "previsualization_status": (
                "structured_previsualization" if "structured-whitebox" in views else "not_selected"
            ),
            "director_track": "derived-from-shot-timelines" if "director-track" in views else None,
            "action_breakdown": "derived-from-shot-timelines" if "action-breakdown" in views else None,
            "scene_overview": "derived-from-scene-space" if "scene-overview" in views else None,
        }

    def stage_storyboard_reference_generation_or_prompt(
        self, project: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        package = self.store.read(f"{P09}/storyboard-package.json")
        capabilities = self.store.read(f"{P07}/capability-snapshot.json")["capabilities"]
        views = set(package.get("views", []))
        if "reference-images" not in views:
            return {
                "status": "not_selected",
                "references": [],
                "boundary": "Storyboard reference images were not selected.",
            }
        fixture = self.environment.get("AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR")
        allowed = (
            not project.get("external_generation_blocked", True)
            and state["decisions"].get("visual_external_action") != "prompt-only"
        )
        can_fixture = bool(
            allowed
            and fixture
            and capabilities["image_generation"]["status"] == "available"
            and capabilities["image_generation"].get("provider") == "local-fixture"
        )
        references = []
        previous_refs = {r['reference_id']: r for r in self.store.read(f'{P09}/reference-image-index.json')['references']} if self.store.exists(f'{P09}/reference-image-index.json') else {}
        for shot_record in package["shots"]:
            timeline = self.store.read(shot_record["timeline_path"])
            for moment_index, moment in enumerate(shot_record["key_moments"]):
                moment_id = str(moment["moment_id"])
                reference_id = f"{timeline['shot_id']}-{moment_id}"
                from .spatial import snapshot_prompt
                snapshot = shot_record['evaluated_frames'][moment_index]
                bindings = []
                if state['decisions'].get('asset_image_strategy') in {'codex-native', 'use-provided-only'}:
                    from .references import character_bindings
                    bindings = character_bindings(self.store, timeline, state)
                    stills = shot_record.get('blender_stills', {}).get('files', [])
                    layout = next((f for f in stills if f['path'].endswith(f'/{moment_index:04d}.png')), None)
                    if not layout:
                        raise ValueError('Native storyboard needs an actual space keyframe; enable and approve Blender previs')
                    bindings.append({'reference_id': reference_id + '-layout', 'role': 'layout', 'entity_ids': [],
                        'revision': timeline['revision'], 'path': layout['path'], 'sha256': layout['sha256'],
                        'approval_ref': state.get('decision_approvals', {}).get('spatial_review_decision'),
                        'allowed_inheritance': ['camera', 'blocking', 'composition'],
                        'forbidden_inheritance': ['proxy appearance', 'labels']})
                prompt = snapshot_prompt(snapshot, style=self.store.read(f'{P07}/style-choice.json'), reference_bindings=bindings)
                record: dict[str, Any] = {
                    "reference_id": reference_id,
                    "shot_id": timeline["shot_id"],
                    "moment_id": moment_id,
                    "time_s": moment["time_s"],
                    "prompt": prompt,
                    "execution_status": "prompt_ready",
                    "evaluated_source_hash": snapshot['source_hash'],
                }
                if state['decisions'].get('asset_image_strategy') in {'codex-native', 'use-provided-only'}:
                    if state['decisions']['asset_image_strategy'] == 'codex-native' and not allowed:
                        raise ValueError('Storyboard upload/generation needs explicit authorization')
                    from .media_bridge import acquire_candidate
                    receipt = acquire_candidate(self.store, stage_id='storyboard_reference_generation_or_prompt',
                        key=reference_id, prompt=prompt, bindings=bindings,
                        folder=f'{P09}/reference-images', output_kind='storyboard',
                        revision_token=state.get('creative_revision_tokens', {}).get('storyboard:' + timeline['shot_id']),
                        allowed_providers=('provided',) if state['decisions']['asset_image_strategy'] == 'use-provided-only' else ('codex-imagegen', 'provided'))
                    record.update(path=receipt['media_path'], sha256=receipt['sha256'],
                        execution_status='provided' if receipt['provider'] == 'provided' else 'generated_verified', image_role='finished_storyboard',
                        provider=receipt['provider'],
                        reference_binding_evidence='user-import-attestation' if receipt['provider'] == 'provided' else 'host-call-receipt',
                        generation_reference_bindings=receipt['reference_bindings'],
                        file_validation=receipt['file_validation'], creative_review='pending')
                elif can_fixture:
                    candidates = [
                        path
                        for suffix in (".png", ".jpg", ".jpeg", ".webp")
                        if (path := Path(str(fixture)) / f"{reference_id}{suffix}").is_file()
                    ]
                    if candidates:
                        source = candidates[0]
                        relative = f"{P09}/reference-images/{reference_id}{source.suffix.lower()}"
                        self.store.copy_source(source, relative)
                        inspection = inspect_image(self.store.path(relative))
                        record.update(
                            {
                                "path": relative,
                                "execution_status": (
                                    "generated_verified" if inspection["verified"] else "generated_unverified"
                                ),
                                **inspection,
                            }
                        )
                previous = previous_refs.get(reference_id)
                changed = previous and (previous.get('sha256') != record.get('sha256') or previous.get('prompt') != record['prompt'])
                record['version'] = previous.get('version', 1) + 1 if changed else previous.get('version', 1) if previous else 1
                references.append(record)
        verified = len([item for item in references if item["execution_status"] in {"generated_verified", "provided"}])
        return {
            "status": (
                "media_verified"
                if references and verified == len(references)
                else "media_partial"
                if verified
                else "prompt_ready"
            ),
            "references": references,
            "fallback_decision": state["decisions"].get("storyboard_image_fallback"),
            "boundary": "Prompt-ready storyboard entries are not generated images.",
        }

    def stage_storyboard_quality_gate(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        package = self.store.read(f"{P09}/storyboard-package.json")
        references = self.store.read(f"{P09}/reference-image-index.json")
        return {
            "review_status": "approved",
            "user_decision": state["decisions"]["storyboard_review_decision"],
            "checked_shot_ids": [item["shot_id"] for item in package.get("shots", [])],
            "reference_status": references["status"],
        }

    def stage_canonical_prompt_compile(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        index = self.store.read(SHOT_TIMELINE_INDEX)
        source_candidates = [
            f"{P05}/screenplay-enhanced.json",
            SOURCE_REGISTRY,
            f"{P07}/style-choice.json",
            ASSET_REGISTRY,
            SCENE_SPACE_PLAN,
            f"{P09}/storyboard-package.json",
            f"{P09}/storyboard-review.json",
            f"{P09}/reference-image-index.json",
            f"{P07}/asset-review.json",
            f"{P04}/director-treatment.json",
        ]
        shared_sources = [path for path in source_candidates if self.store.exists(path)]
        prompts = []
        shot_ids = []
        for entry in sorted(index.get("shots", []), key=lambda item: item["index"]):
            shot = self.store.read(entry["path"])
            prompt, fact_hash = canonical_prompt_for_shot(shot)
            asset_description = [{key: asset.get(key) for key in ('asset_id', 'entity_ids', 'version', 'description', 'continuity_constraints', 'forbidden_inheritance')}
                                 for asset in self.store.read(ASSET_REGISTRY)['assets'] if asset['asset_id'] in shot['required_asset_ids']]
            prompt += '\n已确认风格和画幅：' + _compact(self.store.read(f'{P07}/style-choice.json'))
            prompt += '\n资产职责与连续性：' + _compact(asset_description)
            canonical_record = canonical_record_for_shot(shot)
            from .references import dual_bindings, prompt_controls
            controls, coverage = prompt_controls(self.store, shot)
            dual_error = None
            try:
                bindings = dual_bindings(self.store, shot, state)
            except ValueError as error:
                bindings, dual_error = [], str(error)
                if state['decisions'].get('delivery_target') == 'dual-reference-previs':
                    raise
            prompt += '\n附件对应表：' + _compact(bindings)
            prompt += '\n完整时序控制（持续整镜使用full_shot）：' + _compact(controls)
            source_paths = [*shared_sources, entry["path"]]
            source_trace = [
                {"path": path, "sha256": sha256_file(self.store.path(path))}
                for path in source_paths
            ]
            shot_ids.append(shot["shot_id"])
            prompts.append(
                {
                    "shot_id": shot["shot_id"],
                    "duration_s": shot["duration_s"],
                    "timeline_path": entry["path"],
                    "timeline_sha256": sha256_file(self.store.path(entry["path"])),
                    "execution_prompt": prompt,
                    "asset_descriptions": asset_description,
                    "reference_bindings": bindings,
                    "execution_controls": controls,
                    "field_coverage": coverage,
                    "dual_reference_status": 'ready' if not dual_error else 'missing',
                    "unresolved_limits": [dual_error] if dual_error else [],
                    "canonical_record": canonical_record,
                    "canonical_fact_hash": fact_hash,
                    "source_trace": source_trace,
                    "source_trace_hash": sha256_bytes(canonical_json(source_trace).encode("utf-8")),
                    "required_asset_ids": shot["required_asset_ids"],
                    "selected_reference_ids": shot["selected_reference_ids"],
                    "negative_constraints": shot["negative_constraints"],
                }
            )
        return {
            "package_id": stable_id("prompt-package", project["project_id"], "canonical"),
            "adapter_id": "generic-video-v1",
            "shot_ids": shot_ids,
            "prompts": prompts,
            "warnings": [],
            "degradations": [],
            "canonical_only": True,
            "delivery_scope": state['decisions'].get('delivery_target', 'prompt-draft'),
            "dual_reference_status": 'ready' if all(p['dual_reference_status'] == 'ready' for p in prompts) else 'missing',
            "platform_readiness": 'unverified',
            "execution_status": 'not_submitted',
            "record_boundary": "Full structured facts remain in each referenced ShotTimelineSpec.",
        }

    def stage_platform_choice(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        platform = state["decisions"]["target_platform"]
        adapter = "generic-video-v1" if platform == "platform-neutral" else "seedance-2.0-doubao"
        return {"target_platform": platform, "adapter_id": adapter}

    def stage_platform_adaptation(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        canonical = self.store.read(CANONICAL_PROMPT_PACKAGE)
        choice = self.store.read(f"{P11}/platform-choice.json")
        adapter_id = choice["adapter_id"]
        adapter = json.loads((PACKAGE_ROOT / "adapters" / f"{adapter_id}.json").read_text(encoding="utf-8"))
        prompts = []
        for item in canonical["prompts"]:
            limit = adapter.get('max_references')
            if isinstance(limit, int) and len(item.get('reference_bindings', [])) > min(5, limit):
                from .references import ReferenceCapacityError
                raise ReferenceCapacityError('Required joint image references exceed the selected platform slots; no reference was dropped')
            if adapter_id == "generic-video-v1":
                adapted_prompt = item["execution_prompt"]
            else:
                adapted_prompt = (
                    f"【时长】{item['duration_s']}秒\n"
                    f"【画面与动作】\n{item['execution_prompt']}\n"
                    f"【参考素材槽位】{_compact(item['selected_reference_ids'])}\n"
                    f"【禁止项】{_compact(item['negative_constraints'])}"
                )
            prompts.append(
                {
                    "shot_id": item["shot_id"],
                    "adapted_prompt": adapted_prompt,
                    "reference_bindings": item.get('reference_bindings', []),
                    "execution_controls": item.get('execution_controls', {}),
                    "field_coverage": item.get('field_coverage', []),
                    "request_mapping": [{'slot': b['slot'], 'path': b['path'], 'sha256': b['sha256'], 'role': b['role']}
                                        for b in item.get('reference_bindings', [])],
                    "canonical_fact_hash": item["canonical_fact_hash"],
                    "selected_reference_ids": item["selected_reference_ids"],
                    "required_asset_ids": item["required_asset_ids"],
                }
            )
        warnings = []
        degradations = []
        if adapter["status"] != "verified-local-contract":
            warnings.append(
                {
                    "code": "adapter-provisional",
                    "message": adapter["capability_evidence"],
                    "requires_human_review": True,
                }
            )
        aspect_ratio = project.get("selected_config", {}).get("aspect_ratio")
        verified_aspects = adapter.get("aspect_ratios", [])
        if verified_aspects and aspect_ratio not in verified_aspects:
            degradations.append(
                {
                    "code": "aspect-requires-target-validation",
                    "message": f"{aspect_ratio} is not in the adapter's verified aspect list {verified_aspects}",
                }
            )
        if not verified_aspects:
            warnings.append(
                {
                    "code": "aspect-limit-unknown",
                    "message": "The selected aspect ratio must be reverified on the live target surface.",
                }
            )
        if adapter.get("single_operation_duration_s", {}).get("maximum") is None:
            warnings.append(
                {
                    "code": "duration-limit-unknown",
                    "message": "Live single-operation duration remains unknown; Canonical shots stay at 1-12 seconds.",
                }
            )
        return {
            "package_id": stable_id("prompt-package", project["project_id"], adapter_id),
            "adapter_id": adapter_id,
            "shot_ids": list(canonical["shot_ids"]),
            "prompts": prompts,
            "warnings": warnings,
            "degradations": degradations,
            "canonical_source": CANONICAL_PROMPT_PACKAGE,
            "platform_readiness": 'unverified',
            "execution_status": 'not_submitted',
            "dual_reference_status": canonical.get('dual_reference_status', 'missing'),
            "delivery_scope": canonical.get('delivery_scope', 'prompt-draft'),
        }

    def stage_media_capability_probe(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return {"capabilities": probe_capabilities(environment=self.environment)}

    def stage_media_execution_or_fallback(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        capabilities = self.store.read(f"{P11}/capability-snapshot.json")["capabilities"]
        prompts = self.store.read(ADAPTED_PROMPT_PACKAGE)
        assets = self.store.read(ASSET_REGISTRY)
        fixture = self.environment.get("AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR")
        outputs: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []
        allowed = (
            not project.get("external_generation_blocked", True)
            and state["decisions"].get("video_external_action") != "prompt-only"
            and state["decisions"].get("media_execution_mode") == "execute-if-available"
        )
        can_video_fixture = bool(
            allowed
            and fixture
            and capabilities["video_generation"]["status"] == "available"
            and capabilities["video_generation"].get("provider") == "local-fixture"
        )
        for prompt in prompts["prompts"]:
            shot_id = prompt["shot_id"]
            source = Path(fixture) / f"{shot_id}.mp4" if fixture else Path()
            imported_path = f'runtime/imported-videos/{shot_id}.json'
            if state['decisions'].get('media_execution_mode') == 'imported-local' and self.store.exists(imported_path):
                item = self.store.read(imported_path)
                if project.get('external_generation_blocked'):
                    raise ValueError('Confirm source rights before including imported video in delivery')
                if sha256_file(self.store.path(item['path'])) != item['sha256']:
                    raise ValueError('Imported video changed; reimport and review')
                outputs.append(item)
            elif can_video_fixture and source.is_file():
                relative = f"{P11}/media/generated/video/{shot_id}.mp4"
                self.store.copy_source(source, relative)
                inspection = inspect_video(self.store.path(relative))
                outputs.append(
                    {
                        "shot_id": shot_id,
                        "kind": "video",
                        "path": relative,
                        **inspection,
                        "provider": "local-fixture",
                        "simulated": True,
                    }
                )
            else:
                operations.append(
                    {
                        "shot_id": shot_id,
                        "kind": "video",
                        "prompt": prompt["adapted_prompt"],
                        "selected_reference_ids": prompt["selected_reference_ids"],
                        "status": "manual_required",
                        "reason": (
                            "rights-or-authorization-boundary"
                            if not allowed
                            else "no-executable-video-provider"
                        ),
                    }
                )
        generated_videos = len([item for item in outputs if item["kind"] == "video"])
        expected_videos = len(prompts["prompts"])
        expected_images = 0
        all_expected = expected_videos
        all_generated = generated_videos
        return {
            "status": (
                "media_complete"
                if all_expected and all_generated == all_expected
                else "media_partial"
                if all_generated
                else "prompt_ready"
            ),
            "outputs": outputs,
            "manual_operations": operations,
            "expected_video_count": expected_videos,
            "generated_video_count": len([item for item in outputs if item.get('provider') != 'provided-local']),
            "imported_video_count": len([item for item in outputs if item.get('provider') == 'provided-local']),
            "expected_image_count": expected_images,
            "generated_image_count": 0,
            "approved_asset_ids": [item["asset_id"] for item in assets.get("assets", [])],
            "external_generation_blocked": not allowed,
            "boundary": "Prompt validation is not media generation. Fixture outputs are explicitly simulated.",
        }

    def stage_media_quality_gate(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        execution = self.store.read(MEDIA_EXECUTION_INDEX)
        outputs = execution.get("outputs", [])
        verified = [item for item in outputs if item.get("verified")]
        expected = execution.get("expected_video_count", 0) + execution.get("expected_image_count", 0)
        if not outputs:
            review_status = "approved-prompt-only"
        elif len(verified) == expected:
            review_status = "approved-media"
        else:
            review_status = "media-partial"
        return {
            "review_status": review_status,
            "checks": {
                "registered_outputs": len(outputs),
                "file_verified_outputs": len(verified),
                "expected_outputs": expected,
                "verified_images": len([item for item in verified if item.get("kind") == "image"]),
                "verified_videos": len([item for item in verified if item.get("kind") == "video"]),
            },
            "limitations": [
                "Black-frame, freeze-frame, lip-sync, safe-area, and story-continuity checks require actual review evidence."
            ],
        }

    def stage_final_render_or_edit_package(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        edit_plan = self.store.read(f"{P12}/edit-plan.json")
        execution = self.store.read(MEDIA_EXECUTION_INDEX)
        capabilities = self.store.read(f"{P11}/capability-snapshot.json")["capabilities"]
        voice_strategy = state["decisions"]["voice_strategy"]
        dialogue = edit_plan.get("dialogue_table", [])
        audio_assets: list[dict[str, Any]] = []
        audio_fallback: list[dict[str, Any]] = []
        if (
            voice_strategy == "tts"
            and dialogue
            and state["decisions"].get("audio_external_action") != "script-only"
        ):
            tts = capabilities["tts"]
            if tts.get("status") == "available" and tts.get("provider") == "macos-say" and tts.get("executable"):
                say = str(tts["evidence"])
                for index, line in enumerate(dialogue, start=1):
                    line_id = str(line.get("line_id") or f"LINE-{index:03d}")
                    text = str(line.get("text", "")).strip()
                    if not text:
                        audio_fallback.append({"line_id": line_id, "reason": "missing dialogue text", "timecode": line.get("start_s")})
                        continue
                    cast = next((c for c in edit_plan['voice_cast'] if c.get('speaker_id', c.get('character_id')) == line['speaker_id']), {})
                    voice = cast.get('local_voice')
                    voice_hash = sha256_bytes(canonical_json({'line': line, 'voice': voice, 'provider': say}).encode())
                    relative = f"{P12}/media/generated/audio/{voice_hash[:20]}.aiff"
                    failure = None
                    if not self.store.exists(relative):
                        with tempfile.TemporaryDirectory(prefix='ai-comic-voice-') as temporary:
                            target = Path(temporary) / 'voice.aiff'
                            argv = [say, '-o', str(target)] + (['-v', voice] if voice else []) + [text]
                            process = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)
                            self.store.write_text(f'runtime/voice-logs/{voice_hash}.json', canonical_json({
                                'provider': 'macos-say', 'line_id': line_id, 'speaker_id': line['speaker_id'],
                                'voice': voice or 'system-default', 'returncode': process.returncode,
                                'stdout': process.stdout, 'stderr': process.stderr}))
                            if process.returncode == 0 and target.exists():
                                self.store.copy_source(target, relative)
                            else:
                                failure = process.stderr.strip() or 'TTS failed'
                    if self.store.exists(relative):
                        inspection = inspect_audio(self.store.path(relative))
                        allocated = line.get("duration_s")
                        if isinstance(allocated, (int, float)) and not isinstance(allocated, bool):
                            inspection["allocated_duration_s"] = allocated
                            inspection["duration_fit"] = inspection.get("duration_s", 0) <= float(allocated) + 0.25
                        audio_assets.append({"line_id": line_id, "speaker_id": line['speaker_id'], "path": relative,
                                             'provider': 'macos-say', 'voice': voice or 'system-default', **inspection})
                    else:
                        audio_fallback.append(
                            {
                                "line_id": line_id,
                                "reason": failure,
                                "text": text,
                                "timecode": line.get("start_s"),
                            }
                        )
            else:
                audio_fallback = [
                    {
                        "line_id": line.get("line_id", f"LINE-{index:03d}"),
                        "text": line.get("text"),
                        "timecode": line.get("start_s"),
                        "reason": "no executable TTS provider",
                    }
                    for index, line in enumerate(dialogue, start=1)
                ]
        elif voice_strategy == "voice-script-only" or (
            voice_strategy == "tts" and state["decisions"].get("audio_external_action") == "script-only"
        ):
            audio_fallback = [
                {
                    "line_id": line.get("line_id", f"LINE-{index:03d}"),
                    "text": line.get("text"),
                    "timecode": line.get("start_s"),
                    "reason": "voice script delivery selected",
                }
                for index, line in enumerate(dialogue, start=1)
            ]
        outputs = [item for item in execution.get('outputs', []) if item.get('kind') == 'video']
        if not outputs and state['decisions'].get('delivery_target') == 'dual-reference-previs':
            storyboards = self.store.read(f'{P09}/storyboard-package.json')
            outputs = [{'shot_id': shot['shot_id'], **shot['blender_motion']['video']}
                       for shot in storyboards['shots'] if shot.get('blender_motion', {}).get('video')]
        final_video: dict[str, Any] | None = None
        ffmpeg = shutil.which("ffmpeg")
        if outputs and all(item.get("verified") for item in outputs) and ffmpeg:
            from .editing import execute_edit_plan
            final_video = execute_edit_plan(self.store, edit_plan, outputs, audio_assets=audio_assets,
                aspect=state['decisions']['aspect_ratio'], voice_strategy=voice_strategy)
        if final_video and final_video.get("streams"):
            expected_duration = final_video.get('expected_duration_s', sum(float(item.get("duration_s", 0)) for item in edit_plan.get("timeline", [])))
            actual_duration = float(final_video.get("duration_s", 0))
            duration_tolerance = max(0.5, expected_duration * 0.05)
            duration_match = abs(actual_duration - expected_duration) <= duration_tolerance
            video_stream = next(
                (item for item in final_video["streams"] if item.get("codec_type") == "video"),
                {},
            )
            width = int(video_stream.get("width", 0) or 0)
            height = int(video_stream.get("height", 0) or 0)
            selected_ratio = str(project.get("selected_config", {}).get("aspect_ratio", ""))
            try:
                ratio_left, ratio_right = (float(value) for value in selected_ratio.split(":", 1))
                expected_ratio = ratio_left / ratio_right
                aspect_match = bool(height) and abs(width / height - expected_ratio) <= 0.02
            except (ValueError, ZeroDivisionError):
                expected_ratio = None
                aspect_match = False
            final_video["contract_checks"] = {
                "expected_duration_s": expected_duration,
                "actual_duration_s": actual_duration,
                "duration_tolerance_s": duration_tolerance,
                "duration_match": duration_match,
                "expected_aspect_ratio": selected_ratio,
                "actual_canvas": f"{width}x{height}" if width and height else None,
                "aspect_match": aspect_match,
                "frame_rate": video_stream.get("r_frame_rate"),
                "video_codec": video_stream.get("codec_name"),
                "audio_track_present": final_video.get("audio_track_present", False),
                "dialogue_sync": "requires_human_review",
                "subtitle_safe_area": "requires_human_review",
                "story_continuity": "requires_human_review",
            }
            final_video["verified"] = bool(final_video["verified"] and duration_match and aspect_match)
        mixed = bool(dialogue) and set((final_video or {}).get('mixed_line_ids', [])) == {line['line_id'] for line in dialogue}
        unresolved_voice = bool(dialogue) and voice_strategy == 'tts' and (
            bool(audio_fallback) or not mixed or not all(item.get('verified') for item in audio_assets))
        if final_video:
            final_video['voice_integration'] = 'mixed' if mixed else 'script_only' if voice_strategy == 'voice-script-only' else 'source_audio_or_not_requested'
        if final_video and unresolved_voice:
            final_video["technical_verified"] = final_video.get("verified", False)
            final_video["verified"] = False
            final_video["voice_integration"] = "pending_timeline_mix"
        music_sfx = capabilities["music_sfx"]
        return {
            "render_status": "media_verified" if final_video and final_video.get("verified") else "edit_package_ready",
            "final_video": final_video,
            "edit_plan_path": f"{P12}/edit-plan.json",
            "material_index": [item.get("path") for item in outputs],
            "manual_edit_required": not bool(final_video and final_video.get("verified")),
            "timeline_summary": edit_plan.get("timeline", []),
            "voice_strategy": voice_strategy,
            "voice_delivery_status": (
                "mixed"
                if dialogue and set((final_video or {}).get('mixed_line_ids', [])) == {line['line_id'] for line in dialogue}
                else
                "complete"
                if not dialogue or voice_strategy in {"original-audio", "no-dialogue"}
                else "assets_generated_pending_mix"
                if audio_assets and not audio_fallback
                else "script_or_manual_required"
            ),
            "audio_assets": audio_assets,
            "audio_fallback": audio_fallback,
            "music_sfx": {
                "status": music_sfx["status"],
                "plan": {"sfx": edit_plan.get("sfx", []), "music": edit_plan.get("music", [])},
                "execution": "not_attempted" if music_sfx["status"] != "available" else "provider-specific execution not registered",
            },
        }

    def stage_final_validation(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        report = validate_project(self.store.root, verify_manifest=False)
        if not report["valid"]:
            raise ValueError(f"Final validation failed: {_compact(report['errors'])}")
        report["acceptance_scope"] = {
            "structure": "checked",
            "semantic_continuity": "requires approved quality artifacts",
            "media": f"checked only for files registered in {MEDIA_EXECUTION_INDEX}",
            "publication": "not performed",
        }
        return report

    def stage_export(self, project: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        report = validate_project(self.store.root, verify_manifest=False)
        if not report["valid"]:
            raise ValueError(f"Export validation failed: {_compact(report['errors'])}")
        manifest = self.store.read("manifest.json") if self.store.exists("manifest.json") else {"files": []}
        render = self.store.read(f"{P12}/render-package.json")
        execution = self.store.read(MEDIA_EXECUTION_INDEX)
        style = self.store.read(f"{P07}/style-choice.json")
        canonical = self.store.read(CANONICAL_PROMPT_PACKAGE)
        intake = self.store.read(f"{P02}/intake-brief.json")
        if (render.get("final_video") or {}).get("verified"):
            status = "media_verified"
        elif execution.get("outputs"):
            status = "media_partial"
        else:
            status = "prompt_ready"
        return {
            "delivery_id": stable_id("delivery", project["project_id"]),
            "status": status,
            "package_status": "export_ready",
            "delivery_scope": canonical.get('delivery_scope', 'prompt-draft'),
            "dual_reference_status": canonical.get('dual_reference_status', 'missing'),
            "platform_readiness": canonical.get('platform_readiness', 'unverified'),
            "execution_status": 'not_submitted',
            "artifacts": [
                {**item, "delivery_status": "included"}
                for item in manifest.get("files", [])
                if item.get("path") not in {"state.json", "state.md"}
                and not str(item.get("path", "")).startswith("runtime/")
            ],
            "boundaries": [
                "No external platform publication was performed.",
                "Seedance/Doubao live capabilities were not inferred from prompt adaptation.",
                "Prompt-only outputs are not described as generated media.",
            ],
            "archive": f"{P13}/delivery/{project['project_id']}.zip",
            "_extra_artifacts": [
                {
                    "path": f"{P13}/cover-package.json",
                    "artifact_type": "cover-package",
                    "body": {
                        "title": project["title"],
                        "visual_style": style["visual_style"],
                        "aspect_ratio": style["aspect_ratio"],
                        "prompt": (
                            f"AI漫剧封面，标题《{project['title']}》，风格 {style['visual_style']}，"
                            f"画幅 {style['aspect_ratio']}。主视觉依据首镜："
                            f"{canonical['prompts'][0]['execution_prompt']}"
                        ),
                        "execution_status": "prompt_ready",
                        "boundary": "No cover image is claimed unless a verified file is separately registered.",
                    },
                },
                {
                    "path": f"{P13}/publication-copy.json",
                    "artifact_type": "publication-copy",
                    "body": {
                        "title": project["title"],
                        "synopsis": intake.get("summary") or "简介待依据已批准剧情人工定稿。",
                        "language": state["decisions"].get("subtitle_language"),
                        "platform_specific_copy": None,
                        "status": "draft-for-human-review",
                    },
                },
                {
                    "path": f"{P13}/publication-checklist.json",
                    "artifact_type": "publication-checklist",
                    "body": {
                        "items": [
                            {"id": "rights", "status": state["decisions"].get("rights_status")},
                            {"id": "media", "status": status},
                            {"id": "subtitle_language", "status": state["decisions"].get("subtitle_language")},
                            {"id": "aspect_ratio", "status": state["decisions"].get("aspect_ratio")},
                            {"id": "target_platform", "status": state["decisions"].get("target_platform")},
                            {"id": "platform_limits_reverified", "status": "required-before-publication"},
                            {"id": "human_story_and_safety_review", "status": "required-before-publication"},
                        ],
                        "publication_performed": False,
                    },
                },
            ],
        }
