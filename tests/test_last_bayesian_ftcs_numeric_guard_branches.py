"""Synthetic fault injection checks guarded branches that normal runs rarely reach."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.bayesian import diagnostics, mh
from axiomize.pde import diffusion
from axiomize.uncertainty import quantify


def test_mh_dimension_ceiling_is_checked_before_allocating_markov_chain(monkeypatch):
    monkeypatch.setattr(mh, "MAX_MODEL_PARAMETERS", 1)
    with pytest.raises(ValueError, match="dimension exceeds hard limit"):
        mh.metropolis_hastings(lambda x: -float(np.sum(x * x)), np.array([0.0, 0.0]), n_samples=10, burn=0, seed=0)


def test_heat_step_rounding_cannot_cross_hard_limit_after_first_preflight(monkeypatch):
    monkeypatch.setattr(diffusion, "MAX_FTCS_STEPS", 1)
    with pytest.raises(ValueError, match="step count must be in"):
        diffusion.heat_ftcs(alpha=0.0, length=1.0, nx=3, dt=2.0, t_end=3.0)


def test_heat_error_metric_is_checked_for_nonfinite_numeric_backend_output(monkeypatch):
    monkeypatch.setattr(diffusion.np, "sqrt", lambda *_a, **_kw: float("nan"))
    with pytest.raises(RuntimeError, match="non-finite error metric"):
        diffusion.heat_ftcs(alpha=0.1, length=1.0, nx=5, dt=0.001, t_end=0.01)


def test_confidence_intervals_refuse_oversized_fitted_parameter_map(monkeypatch):
    monkeypatch.setattr(quantify, "MAX_MODEL_PARAMETERS", 1)
    from types import SimpleNamespace

    with pytest.raises(ValueError, match="parameter count exceeds hard limit"):
        quantify.confidence_intervals(SimpleNamespace(params={"a": (1.0, 0.1), "b": (2.0, 0.2)}))


def test_ess_positive_pair_sequence_exhaustion_uses_all_available_lags(monkeypatch):
    monkeypatch.setattr(
        diagnostics,
        "_autocorrelation",
        lambda _x, max_lag: np.asarray([1.0] + [0.4] * max_lag),
    )
    result = diagnostics.effective_sample_size(np.ones((2, 6)))
    assert math.isfinite(result)
    assert 1.0 <= result <= 12
    assert result < 12
