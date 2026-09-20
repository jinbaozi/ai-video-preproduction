#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_gpt_image_2_size.py"
SPEC = importlib.util.spec_from_file_location("gpt_image_2_size_validator", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SizeValidationTests(unittest.TestCase):
    def test_standard_sizes(self) -> None:
        for value in ("1024x1024", "1536x1024", "1024x1536", "2560x1440", "640x1024"):
            with self.subTest(value=value):
                result = MODULE.validate_size(value)
                self.assertTrue(result["valid"])
                self.assertEqual(result["tier"], "standard")

    def test_experimental_boundary_sizes(self) -> None:
        for value in ("3840x2160", "2160x3840", "2880x2880", "2048x2048"):
            with self.subTest(value=value):
                result = MODULE.validate_size(value)
                self.assertTrue(result["valid"])
                self.assertEqual(result["tier"], "experimental")

    def test_invalid_sizes(self) -> None:
        for value in ("1080x1920", "4096x2160", "3840x3840", "3840x1248", "3840x2176", "640x1008"):
            with self.subTest(value=value):
                result = MODULE.validate_size(value)
                self.assertFalse(result["valid"])
                self.assertTrue(result["issues"])

    def test_auto(self) -> None:
        result = MODULE.validate_size("auto")
        self.assertTrue(result["valid"])
        self.assertEqual(result["tier"], "auto")

    def test_four_k_flag(self) -> None:
        self.assertTrue(MODULE.validate_size("3840x2160")["is_4k_uhd"])
        self.assertFalse(MODULE.validate_size("2880x2880")["is_4k_uhd"])

    def test_common_separators(self) -> None:
        for value in ("3840X2160", "3840×2160"):
            with self.subTest(value=value):
                result = MODULE.validate_size(value)
                self.assertTrue(result["valid"])
                self.assertEqual(result["normalized"], "3840x2160")


if __name__ == "__main__":
    unittest.main()
