"""Regression tests for standalone validation-tool hard limits."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _validate_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "skills" / "axiomize" / "tools" / "validate.py"
    spec = importlib.util.spec_from_file_location("axiomize_validate_hardening", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_direct_sir_rejects_fractional_population_and_initial_count() -> None:
    module = _validate_module()
    with pytest.raises(ValueError, match="exact finite integer"):
        module.run_sir(0.3, 0.1, 1, 100.5, days=30)
    with pytest.raises(ValueError, match="exact finite integer"):
        module.run_sir(0.3, 0.1, 1.5, 100, days=30)


def test_erlang_c_rejects_fractional_staff() -> None:
    module = _validate_module()
    with pytest.raises(ValueError, match="exact finite integer"):
        module.erlang_c(10.0, 5.0, 2.5)


def test_fadeout_probability_is_stable_for_extreme_ratios() -> None:
    module = _validate_module()
    assert 0.0 <= module._fadeout_probability(1e-300, 1.0, 1000) <= 1.0
    assert 0.0 <= module._fadeout_probability(1.0, 1e-300, 1000) <= 1.0


def test_gillespie_sweep_work_is_included_in_preflight() -> None:
    module = _validate_module()
    args = SimpleNamespace(
        beta=0.3,
        gamma=0.1,
        I0=1,
        N=100_000,
        days=30,
        runs=1,
        seed=1,
        sweep=True,
    )
    with pytest.raises(ValueError, match="all requested Gillespie"):
        module.report_gillespie(args)
