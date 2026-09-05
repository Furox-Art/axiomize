"""Regression for custom benchmark integer parsing."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _runner():
    root = Path(__file__).resolve().parents[1]
    path = root / "skills" / "axiomize" / "tools" / "benchmark_runner.py"
    spec = importlib.util.spec_from_file_location("axiomize_benchmark_input_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grade_rejects_fractional_minimum_lenses() -> None:
    runner = _runner()
    case = {
        "must_contain": [],
        "expected_archetype": "",
        "min_lenses_built": 1.9,
        "must_reject_at_least_one": False,
    }
    with pytest.raises(ValueError, match="integer"):
        runner.grade("", case)
