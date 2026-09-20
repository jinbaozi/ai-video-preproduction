from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Iterable

from .layout import P01
from .storage import ProjectStore
from .utils import sha256_bytes, stable_id


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "-", value).strip("-.")
    return normalized[:100] or "input"


def _read_docx(path: Path) -> tuple[str | None, str]:
    try:
        from docx import Document  # type: ignore[import-not-found]
    except ImportError:
        return None, "requires-python-docx"
    try:
        document = Document(path)
    except Exception as error:
        return None, f"docx-parse-error:{type(error).__name__}"
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    blocks = []
    for index, element in enumerate(document.element.body, start=1):
        if element.tag.endswith("}p"):
            value = Paragraph(element, document).text
            if value.strip():
                blocks.append(f"[paragraph:{index}] {value}")
        elif element.tag.endswith("}tbl"):
            table = Table(element, document)
            for row_index, row in enumerate(table.rows, start=1):
                blocks.append(f"[table:{index}/row:{row_index}] " + " | ".join(cell.text for cell in row.cells))
    text = "\n".join(blocks)
    return (text, "extracted") if text.strip() else (None, "empty-or-scanned")


def _read_pdf(path: Path) -> tuple[str | None, str]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return None, "requires-pypdf-or-ocr"
    try:
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        if any(not page.strip() for page in pages):
            return None, "requires-ocr-or-complete-text"
        text = "\n".join(f"[page:{index}]\n{page}" for index, page in enumerate(pages, start=1))
    except Exception as error:
        return None, f"pdf-parse-error:{type(error).__name__}"
    return (text, "extracted") if text.strip() else (None, "requires-ocr")


def extract_text(path: Path) -> tuple[str | None, str]:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        try:
            return path.read_text(encoding="utf-8"), "extracted"
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="replace"), "extracted-with-replacement"
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "invalid-json"
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), "extracted"
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    return None, "not-textual"


def classify_source(path: Path, text: str | None, hint: str | None = None) -> str:
    if hint:
        return hint
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "reference-image"
    if suffix in VIDEO_EXTENSIONS:
        return "reference-video"
    if suffix == ".json" and text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        artifact_type = str(payload.get("artifact_type", "")) if isinstance(payload, dict) else ""
        if artifact_type in {"storyboard", "shot-spec", "shot-spec-index", "shot-timeline-spec", "shot-timeline-index", "storyboard-package", "shot-plan"}:
            return "storyboard"
        if artifact_type in {"screenplay", "screenplay-enhanced", "edit-plan"}:
            return "screenplay"
        if artifact_type in {"project", "workflow-state", "manifest"} or (
            isinstance(payload, dict) and "schema_version" in payload and "project_id" in payload
            and payload.get('artifact_type') in {None, 'project'}
        ):
            return "legacy-project"
        if isinstance(payload, dict) and payload.get('artifact_type'):
            return 'other'
    if any(token in name for token in ("storyboard", "shot-list", "shot_spec", "\u5206\u955c", "\u955c\u5934")):
        return "storyboard"
    if any(token in name for token in ("screenplay", "script", "\u5267\u672c", "\u53f0\u8bcd")):
        return "screenplay"
    sample = (text or "")[:12000]
    storyboard_markers = len(re.findall(r"(?:\u955c\u5934|\u5206\u955c|SHOT)\s*[#\d]", sample, flags=re.I))
    screenplay_markers = len(re.findall(r"(?:INT\.|EXT\.|\u5185\s+\u65e5|\u5916\s+\u591c|\u573a\s*\d+|\u4eba\u7269\s*[:\uff1a])", sample, flags=re.I))
    if storyboard_markers >= 2:
        return "storyboard"
    if screenplay_markers >= 2:
        return "screenplay"
    return "novel" if text else "other"


def determine_entry_mode(kinds: Iterable[str]) -> str:
    values = list(kinds)
    narrative = {kind for kind in values if kind in {"novel", "screenplay", "storyboard"}}
    if "legacy-project" in values and not narrative:
        return "legacy-project"
    if len(narrative) > 1:
        return "mixed"
    if narrative:
        return next(iter(narrative))
    if values and all(kind.startswith("reference-") or kind == "other" for kind in values):
        return "reference-only"
    return "novel"


def ingest_inputs(
    store: ProjectStore,
    inputs: list[str],
    *,
    input_type: str | None = None,
    start_index: int = 1,
) -> tuple[list[dict[str, Any]], str]:
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(inputs, start=start_index):
        candidate = Path(raw).expanduser()
        if candidate.exists() and candidate.is_file():
            name = _safe_name(candidate.name)
            relative = f"{P01}/sources/original/{index:03d}-{name}"
            digest = store.copy_source(candidate.resolve(), relative)
            stored = store.path(relative)
            original_path = str(candidate.resolve())
        else:
            supported_suffixes = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | {".json", ".docx", ".pdf"}
            if candidate.suffix.lower() in supported_suffixes and ("/" in raw or "\\" in raw):
                raise FileNotFoundError(f"Input file does not exist: {candidate}")
            name = f"inline-{index:03d}.txt"
            relative = f"{P01}/sources/original/{name}"
            digest = store.write_text(relative, raw)
            stored = store.path(relative)
            original_path = "inline-text"
        text, extraction_status = extract_text(stored)
        kind = classify_source(stored, text, input_type)
        source_id = stable_id("src", digest, kind)
        record: dict[str, Any] = {
            "source_id": source_id,
            "kind": kind,
            "stored_path": relative,
            "sha256": digest,
            "rights_status": "unknown",
            "authority": "reference" if kind.startswith("reference-") else "source",
            "original_path": original_path,
            "mime_type": mimetypes.guess_type(stored.name)[0] or "application/octet-stream",
            "extraction_status": extraction_status,
        }
        if text is not None:
            text_relative = f"{P01}/sources/text/{source_id}.txt"
            store.write_text(text_relative, text)
            record["text_path"] = text_relative
            record["text_sha256"] = sha256_bytes(text.encode("utf-8"))
        records.append(record)
    return records, determine_entry_mode(record["kind"] for record in records)
