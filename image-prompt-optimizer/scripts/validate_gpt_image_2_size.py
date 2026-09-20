#!/usr/bin/env python3
"""Validate GPT-Image-2 custom output sizes against current documented limits."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any


MIN_PIXELS = 655_360
EXPERIMENTAL_ABOVE_PIXELS = 3_686_400
MAX_PIXELS = 8_294_400
MAX_EDGE = 3_840
MAX_RATIO = 3.0
SIZE_PATTERN = re.compile(r"^(\d+)[xX×](\d+)$")


def validate_size(value: str) -> dict[str, Any]:
    normalized = value.strip()
    if normalized.lower() == "auto":
        return {
            "input": value,
            "normalized": "auto",
            "valid": True,
            "tier": "auto",
            "issues": [],
        }

    match = SIZE_PATTERN.fullmatch(normalized)
    if not match:
        return {
            "input": value,
            "normalized": normalized,
            "valid": False,
            "tier": "invalid",
            "issues": ["Use WIDTHxHEIGHT with positive integer dimensions."],
        }

    width, height = (int(part) for part in match.groups())
    pixels = width * height
    short_edge = min(width, height)
    long_edge = max(width, height)
    ratio = float("inf") if short_edge == 0 else long_edge / short_edge
    issues: list[str] = []

    if width <= 0 or height <= 0:
        issues.append("Width and height must be positive integers.")
    if width % 16 or height % 16:
        issues.append("Width and height must both be divisible by 16.")
    if long_edge > MAX_EDGE:
        issues.append(f"Maximum edge must be <= {MAX_EDGE}px.")
    if short_edge > 0 and ratio > MAX_RATIO:
        issues.append(f"Long-edge to short-edge ratio must be <= {MAX_RATIO}:1.")
    if pixels < MIN_PIXELS:
        issues.append(f"Total pixels must be >= {MIN_PIXELS:,}.")
    if pixels > MAX_PIXELS:
        issues.append(f"Total pixels must be <= {MAX_PIXELS:,}.")

    valid = not issues
    experimental = valid and pixels > EXPERIMENTAL_ABOVE_PIXELS
    result: dict[str, Any] = {
        "input": value,
        "normalized": f"{width}x{height}",
        "width": width,
        "height": height,
        "pixels": pixels,
        "aspect_ratio": round(ratio, 6) if ratio != float("inf") else None,
        "valid": valid,
        "tier": "experimental" if experimental else "standard" if valid else "invalid",
        "issues": issues,
    }
    if valid:
        result["is_4k_uhd"] = (width, height) in {(3840, 2160), (2160, 3840)}
        result["is_max_square"] = (width, height) == (2880, 2880)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate one or more GPT-Image-2 sizes such as 3840x2160."
    )
    parser.add_argument("sizes", nargs="+", help="WIDTHxHEIGHT or auto")
    args = parser.parse_args(argv)
    results = [validate_size(value) for value in args.sizes]
    payload: dict[str, Any] | list[dict[str, Any]] = results[0] if len(results) == 1 else results
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(result["valid"] for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
