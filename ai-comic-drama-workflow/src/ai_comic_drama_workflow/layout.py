from __future__ import annotations

from typing import Final


PHASES: Final[tuple[dict[str, object], ...]] = (
    {"id": "phase-01", "index": 1, "name": "项目设置与资料摄取", "folder": "stages/01-项目设置与资料摄取"},
    {"id": "phase-02", "index": 2, "name": "输入标准化与缺口处理", "folder": "stages/02-输入标准化与缺口处理"},
    {"id": "phase-03", "index": 3, "name": "叙事提取与动态记忆", "folder": "stages/03-叙事提取与动态记忆"},
    {"id": "phase-04", "index": 4, "name": "改编方案", "folder": "stages/04-改编方案"},
    {"id": "phase-05", "index": 5, "name": "剧本创作与增强", "folder": "stages/05-剧本创作与增强"},
    {"id": "phase-06", "index": 6, "name": "故事审核与生成分段", "folder": "stages/06-故事审核与生成分段"},
    {"id": "phase-07", "index": 7, "name": "美术资产", "folder": "stages/07-美术资产"},
    {"id": "phase-08", "index": 8, "name": "站位与空间", "folder": "stages/08-站位与空间"},
    {"id": "phase-09", "index": 9, "name": "故事板", "folder": "stages/09-故事板"},
    {"id": "phase-10", "index": 10, "name": "分镜级视频提示词", "folder": "stages/10-分镜级视频提示词"},
    {"id": "phase-11", "index": 11, "name": "平台适配与媒体执行", "folder": "stages/11-平台适配与媒体执行"},
    {"id": "phase-12", "index": 12, "name": "配音字幕与剪辑", "folder": "stages/12-配音字幕与剪辑"},
    {"id": "phase-13", "index": 13, "name": "最终质检与交付", "folder": "stages/13-最终质检与交付"},
)

PHASE_BY_ID: Final[dict[str, dict[str, object]]] = {str(item["id"]): item for item in PHASES}


def phase_folder(phase_id: str) -> str:
    return str(PHASE_BY_ID[phase_id]["folder"])


def phase_path(phase_id: str, relative: str) -> str:
    return f"{phase_folder(phase_id)}/{relative}"


P01 = phase_folder("phase-01")
P02 = phase_folder("phase-02")
P03 = phase_folder("phase-03")
P04 = phase_folder("phase-04")
P05 = phase_folder("phase-05")
P06 = phase_folder("phase-06")
P07 = phase_folder("phase-07")
P08 = phase_folder("phase-08")
P09 = phase_folder("phase-09")
P10 = phase_folder("phase-10")
P11 = phase_folder("phase-11")
P12 = phase_folder("phase-12")
P13 = phase_folder("phase-13")

SOURCE_REGISTRY = f"{P01}/source-registry.json"
NARRATIVE_BUNDLE = f"{P03}/narrative-bundle.json"
DYNAMIC_MEMORY = f"{P03}/dynamic-memory.json"
GENERATION_SEGMENTS = f"{P06}/generation-segments.json"
ASSET_REGISTRY = f"{P07}/asset-registry.json"
SCENE_SPACE_PLAN = f"{P08}/scene-space-plan.json"
SHOT_PLAN = f"{P09}/shot-plan.json"
SHOT_TIMELINE_INDEX = f"{P09}/shot-timeline-index.json"
CANONICAL_PROMPT_PACKAGE = f"{P10}/prompt-package.json"
ADAPTED_PROMPT_PACKAGE = f"{P11}/adapted-prompt-package.json"
MEDIA_EXECUTION_INDEX = f"{P11}/execution-index.json"
FINAL_DELIVERY_INDEX = f"{P13}/final-delivery-index.json"


LEGACY_PATH_MAP: Final[dict[str, str]] = {
    "sources/source-registry.json": SOURCE_REGISTRY,
    "intake/brief.json": f"{P02}/intake-brief.json",
    "intake/gap-resolution.json": f"{P02}/gap-resolution.json",
    "story/narrative-bundle.json": NARRATIVE_BUNDLE,
    "planning/source-batches.json": f"{P03}/source-batches.json",
    "story/memory/dynamic-memory.json": DYNAMIC_MEMORY,
    "story/adaptation-plan.json": f"{P04}/adaptation-plan.json",
    "story/screenplay.json": f"{P05}/screenplay.json",
    "story/screenplay-enhanced.json": f"{P05}/screenplay-enhanced.json",
    "reviews/story-review.json": f"{P06}/story-review.json",
    "planning/generation-segments.json": GENERATION_SEGMENTS,
}
