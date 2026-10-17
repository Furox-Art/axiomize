"""Exact population accounting for both package and reference SIR outputs."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize.tools.numerical.gillespie import gillespie_sir_once as native_sir


def _reference():
    source = Path(__file__).resolve().parents[1] / "skills/axiomize/tools/validate.py"
    spec = importlib.util.spec_from_file_location("axiomize_dual_sir_reference", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ControlledRng:
    """Force infection, recovery, and a horizon-crossing waiting time."""

    def __init__(self, waits: list[float], choices: list[float]) -> None:
        self.waits = iter(waits)
        self.choices = iter(choices)

    def exponential(self, _scale: float) -> float:
        return next(self.waits)

    def random(self) -> float:
        return next(self.choices)


@pytest.mark.parametrize("implementation", ["package", "reference"])
def test_recovered_and_cumulative_infected_are_distinct_at_finite_horizon(
    implementation: str,
) -> None:
    fn = native_sir if implementation == "package" else _reference().gillespie_sir_once
    outcome = fn(
        beta=2.0,
        gamma=1.0,
        I0=1,
        N=10,
        t_max=0.5,
        rng=ControlledRng([0.1, 0.1, 1.0], [0.0, 0.99]),
    )
    assert outcome["total_infected"] == 2  # I0 + one new infection
    assert outcome["final_R"] == 1  # one recovery; one still infected
    assert outcome["total_infected"] - outcome["final_R"] == 1
    assert outcome["peak_I"] == 2
    assert outcome["events"] == 2
    assert outcome["t_end"] == pytest.approx(0.5)


@pytest.mark.parametrize("implementation", ["package", "reference"])
def test_no_event_before_horizon_counts_initial_infected_but_no_recoveries(
    implementation: str,
) -> None:
    fn = native_sir if implementation == "package" else _reference().gillespie_sir_once
    outcome = fn(
        0.3,
        0.1,
        1,
        10,
        t_max=0.25,
        rng=ControlledRng([1.0], []),
    )
    assert outcome["final_R"] == 0
    assert outcome["total_infected"] == 1
    assert outcome["events"] == 0
    assert outcome["t_end"] == pytest.approx(0.25)


@pytest.mark.parametrize("implementation", ["package", "reference"])
def test_fully_recovered_or_zero_initial_cases_are_consistent(
    implementation: str,
) -> None:
    fn = native_sir if implementation == "package" else _reference().gillespie_sir_once
    recovered = fn(0.0, 1.0, 1, 10, rng=ControlledRng([0.1], [0.5]))
    assert recovered["final_R"] == 1
    assert recovered["total_infected"] == 1
    assert recovered["events"] == 1
    zero = fn(0.3, 0.1, 0, 10, rng=ControlledRng([], []))
    assert zero["final_R"] == 0
    assert zero["total_infected"] == 0
    assert zero["events"] == 0


@pytest.mark.parametrize("seed", [0, 17, 2026])
def test_reference_and_package_simulate_identical_populations(seed: int) -> None:
    native = native_sir(0.3, 0.1, 2, 80, t_max=3.0, rng=np.random.default_rng(seed))
    reference = _reference().gillespie_sir_once(0.3, 0.1, 2, 80, t_max=3.0, rng=np.random.default_rng(seed))
    assert native == reference
    assert 0 <= native["final_R"] <= native["total_infected"] <= 80
    assert native["total_infected"] >= 2
    assert native["t_end"] <= 3.0


def test_validation_report_prints_recovered_and_cumulative_separately(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _reference()
    monkeypatch.setattr(
        module,
        "gillespie_sir_once",
        lambda *_args, **_kwargs: {
            "extinct_early": True,
            "peak_I": 1,
            "final_R": 0,
            "total_infected": 1,
            "events": 0,
            "t_end": 0.5,
        },
    )
    args = SimpleNamespace(
        beta=0.0,
        gamma=1.0,
        I0=1,
        N=10,
        days=0.5,
        runs=2,
        seed=42,
        sweep=False,
    )
    assert module.report_gillespie(args) == 0
    printed = capsys.readouterr().out
    assert "mean total infected (N-S)   = 1.00  (0.1000 of N" in printed
    assert "mean recovered (R)          = 0.00  (0.0000 of N" in printed
    assert "recovered_within_total_infected" in printed


def test_development_branch_runs_full_quality_ci() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text()
    assert "branches: [main, dev/strict-json-wire-20261017]" in workflow
    assert "\n  workflow_dispatch:\n" in workflow
    assert "python -m pytest tests/ -q --cov=axiomize" in workflow
    assert "python .github/scripts/quality_ratchet.py" in workflow
