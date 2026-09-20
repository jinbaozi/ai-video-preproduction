from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Callable, Mapping


def _command_status(command: str, which: Callable[[str], str | None]) -> dict[str, object]:
    resolved = which(command)
    return {
        "status": "available" if resolved else "unavailable",
        "evidence": resolved or f"{command} was not found on PATH",
        "executable": bool(resolved),
    }


def _provider_status(
    capability: str,
    environment: Mapping[str, str],
) -> dict[str, object]:
    key = f"AI_COMIC_DRAMA_{capability.upper()}_STATUS"
    requested = environment.get(key, "unavailable")
    allowed = {"available", "unavailable", "requires_account", "requires_payment", "unknown"}
    status = requested if requested in allowed else "unknown"
    provider = environment.get(f"AI_COMIC_DRAMA_{capability.upper()}_PROVIDER")
    if status == "available":
        status = "unknown"
    evidence = (
        f"Explicit provider declaration: {provider}"
        if provider
        else f"No executable {capability.replace('_', ' ')} provider is registered"
    )
    return {"status": status, "evidence": evidence, "provider": provider, "executable": False}


def probe_capabilities(
    *,
    environment: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, dict[str, object]]:
    env = environment if environment is not None else os.environ
    docx_available = importlib.util.find_spec("docx") is not None
    pdf_available = importlib.util.find_spec("pypdf") is not None
    pillow_available = importlib.util.find_spec("PIL") is not None
    ffmpeg = _command_status("ffmpeg", which)
    ffprobe = _command_status("ffprobe", which)
    tesseract = _command_status("tesseract", which)
    svg_converter_path = which("rsvg-convert") or which("magick")
    tts = _provider_status("tts", env)
    if tts["status"] == "unavailable" and which("say"):
        tts = {"status": "available", "evidence": which("say"), "provider": "macos-say", "executable": True}
    fixture_dir = env.get("AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR")
    image_generation = _provider_status("image_generation", env)
    video_generation = _provider_status("video_generation", env)
    if fixture_dir and Path(fixture_dir).is_dir():
        fixture_evidence = f"Explicit local fixture provider: {Path(fixture_dir).resolve()}"
        fixture_path = Path(fixture_dir)
        if any(path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} for path in fixture_path.iterdir() if path.is_file()):
            image_generation = {
                "status": "available",
                "evidence": fixture_evidence,
                "provider": "local-fixture",
                "executable": True,
            }
        if any(path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"} for path in fixture_path.iterdir() if path.is_file()):
            video_generation = {
                "status": "available",
                "evidence": fixture_evidence,
                "provider": "local-fixture",
                "executable": True,
            }
    true_3d = _provider_status("true_3d", env)
    true_3d["executable"] = False
    from .blender_adapter import find_blender
    blender = find_blender()
    if blender and not env.get('AI_COMIC_DRAMA_TRUE_3D_PROVIDER'):
        true_3d.update(status='unknown', provider='blender-local', evidence=blender,
                       boundary='Installed executable only; project build/render/read-back required')
    if true_3d["status"] == "available" and not true_3d["executable"]:
        true_3d["status"] = "unknown"
        true_3d["evidence"] = f"{true_3d['evidence']}; no executable integration was declared"
    return {
        "text_documents": {"status": "available", "evidence": "UTF-8 text/Markdown/JSON parser", "executable": True},
        "docx": {
            "status": "available" if docx_available else "unavailable",
            "evidence": "python-docx import" if docx_available else "python-docx is not installed",
            "executable": docx_available,
        },
        "pdf_text": {
            "status": "available" if pdf_available else "unavailable",
            "evidence": "pypdf import" if pdf_available else "pypdf is not installed",
            "executable": pdf_available,
        },
        "ocr": tesseract,
        "image_inspection": {
            "status": "available" if pillow_available else "unavailable",
            "evidence": "Pillow import" if pillow_available else "Pillow is not installed",
            "executable": pillow_available,
        },
        "image_generation": image_generation,
        "video_generation": video_generation,
        "svg_to_png": {
            "status": "available" if svg_converter_path else "unavailable",
            "evidence": svg_converter_path or "Neither rsvg-convert nor ImageMagick was found on PATH",
            "executable": bool(svg_converter_path),
        },
        "true_3d": true_3d,
        "tts": tts,
        "music_sfx": _provider_status("music_sfx", env),
        "media_inspection": ffprobe,
        "final_render": ffmpeg,
        "seedance_2_doubao": {
            "status": "unknown",
            "evidence": "Provisional prompt adapter only; live account, limits, cost, and generation are not verified",
            "executable": False,
        },
    }


def doctor_report() -> dict[str, object]:
    capabilities = probe_capabilities()
    return {
        "schema_version": "3.0",
        "runtime": "python-local",
        "capabilities": capabilities,
        "ready_for_prompt_only": True,
        "media_execution_available": any(
            capabilities[name]["status"] == "available" and capabilities[name].get("executable")
            for name in ("image_generation", "video_generation")
        ),
    }
