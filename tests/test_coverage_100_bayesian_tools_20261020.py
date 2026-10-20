"""Coverage-completing tests for the optional PyMC adapter and MH prior laws."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from axiomize.bayesian import engine_v2
from axiomize.bayesian.pymc_tool import PyMCTool, _finite


def _fake_pymc(draws_value: float = 1.0, sample_size=None):
    module = types.ModuleType("pymc")
    module.__version__ = "0.0-fake"

    class _Model:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Posterior:
        def __init__(self, array):
            self.array = array

        def __getitem__(self, key):
            return self

        def to_numpy(self):
            return self.array

    class _Trace:
        def __init__(self, array):
            self.posterior = {"mu": _Posterior(array)}

    module.Model = lambda: _Model()
    module.Normal = lambda name, **kwargs: object()

    def sample(**kwargs):
        size = sample_size if sample_size is not None else 2 * kwargs["draws"]
        return _Trace(np.full(size, draws_value, dtype=float))

    module.sample = sample
    return module


def _fake_arviz(r_hat: float, ess: float):
    module = types.ModuleType("arviz")
    module.rhat = lambda posterior: types.SimpleNamespace(to_numpy=lambda: np.array([r_hat]))
    module.ess = lambda posterior: types.SimpleNamespace(to_numpy=lambda: np.array([ess]))
    return module


def test_finite_helper_rejects_non_numeric_and_non_finite() -> None:
    with pytest.raises(ValueError, match="must be numeric"):
        _finite("abc", name="sigma")
    with pytest.raises(ValueError, match="sigma must be finite$"):
        _finite(float("inf"), name="sigma")
    with pytest.raises(ValueError, match="must be finite and positive"):
        _finite(0.0, name="sigma", positive=True)
    assert _finite(2.5, name="sigma", positive=True) == 2.5


def test_probe_version_reports_module_version(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc())
    assert PyMCTool._probe_version() == "0.0-fake"
    assert PyMCTool.availability().available is True


def test_input_validation_and_unavailable_backend(monkeypatch) -> None:
    tool = PyMCTool()
    with pytest.raises(ValueError, match="payload needs a 'model'"):
        tool.validate_input([])
    with pytest.raises(ValueError, match="payload needs a 'model'"):
        tool.validate_input({})
    with pytest.raises(ValueError, match="needs observed data under 'y'"):
        tool.validate_input({"model": "normal-mean"})
    monkeypatch.setitem(sys.modules, "pymc", None)
    with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
        tool.execute({"model": "normal-mean", "y": [1.0, 2.0]})


def test_execute_rejects_unimplemented_model(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc())
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        PyMCTool().execute({"model": "hierarchical"})


def test_normal_mean_observation_validation(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc())
    with pytest.raises(ValueError, match="numeric 1D observation array"):
        PyMCTool._run_normal_mean({"y": ["bad"]})
    with pytest.raises(ValueError, match="one-dimensional"):
        PyMCTool._run_normal_mean({"y": [[1.0], [2.0]]})
    with pytest.raises(ValueError, match="1..200000 observations"):
        PyMCTool._run_normal_mean({"y": []})
    with pytest.raises(ValueError, match="only finite values"):
        PyMCTool._run_normal_mean({"y": [1.0, float("inf")]})
    with pytest.raises(ValueError, match="sigma must be finite and positive"):
        PyMCTool._run_normal_mean({"y": [1.0, 2.0], "sigma": 0.0})
    with pytest.raises(ValueError, match="pymc.draws must be"):
        PyMCTool._run_normal_mean({"y": [1.0, 2.0], "draws": 0})
    with pytest.raises(ValueError, match="likelihood work limit"):
        PyMCTool._run_normal_mean({
            "y": [1.0] * 600, "draws": 100_000, "tune": 100_000,
        })
    with pytest.raises(ValueError, match="pymc.seed must be"):
        PyMCTool._run_normal_mean({"y": [1.0, 2.0], "seed": -1})


def test_normal_mean_happy_path_without_diagnostics(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(1.5))
    monkeypatch.setitem(sys.modules, "arviz", None)
    out = PyMCTool().execute({"model": "normal-mean", "y": [1.0, 2.0, 3.0], "draws": 5, "tune": 5})
    assert out["status"] == "PASS"
    assert out["backend"] == "pymc-0.0-fake"
    assert out["n_obs"] == 3
    assert out["posterior_mean"] == 1.5
    assert out["r_hat"] == ""
    assert out["diagnostics_note"].startswith("diagnostics unavailable")
    assert out["ci95"] == [1.5, 1.5]


def test_normal_mean_diagnostics_and_warning_status(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(1.0))
    monkeypatch.setitem(sys.modules, "arviz", _fake_arviz(1.02, 123.0))
    healthy = PyMCTool().execute({"model": "normal-mean", "y": [1.0, 2.0], "draws": 4, "tune": 2})
    assert healthy["status"] == "PASS"
    assert healthy["r_hat"] == pytest.approx(1.02)
    assert healthy["ess_bulk"] == pytest.approx(123.0)

    monkeypatch.setitem(sys.modules, "arviz", _fake_arviz(1.2, 50.0))
    warning = PyMCTool().execute({"model": "normal-mean", "y": [1.0, 2.0], "draws": 4, "tune": 2})
    assert warning["status"] == "WARNING"


def test_normal_mean_rejects_malformed_trace(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(1.0, sample_size=3))
    monkeypatch.setitem(sys.modules, "arviz", None)
    with pytest.raises(RuntimeError, match="malformed/non-finite posterior samples"):
        PyMCTool._run_normal_mean({"y": [1.0, 2.0], "draws": 5, "tune": 1})


def test_mh_prior_laws() -> None:
    assert engine_v2._log_prior(1.0, {"dist": "halfnormal", "sigma": 2.0}, None, 1.0) == pytest.approx(
        -0.5 * (0.5) ** 2 - np.log(2.0)
    )
    assert engine_v2._log_prior(-1.0, {"dist": "halfnormal", "sigma": 2.0}, None, 1.0) == -np.inf
    with pytest.raises(ValueError, match="halfnormal prior sigma"):
        engine_v2._log_prior(1.0, {"dist": "halfnormal", "sigma": 0.0}, None, 1.0)

    assert engine_v2._log_prior(0.5, {"dist": "uniform", "low": 0.0, "high": 1.0}, None, 0.0) == 0.0
    assert engine_v2._log_prior(2.0, {"dist": "uniform", "low": 0.0, "high": 1.0}, None, 0.0) == -np.inf
    with pytest.raises(ValueError, match="uniform prior lower"):
        engine_v2._log_prior(0.5, {"dist": "uniform", "low": 1.0, "high": 1.0}, None, 0.0)

    expected = -0.5 * (np.log(2.0) / 0.5) ** 2 - np.log(2.0 * 0.5)
    assert engine_v2._log_prior(2.0, {"dist": "lognormal", "mu": 0.0, "sigma": 0.5}, None, 1.0) == pytest.approx(expected)
    assert engine_v2._log_prior(0.0, {"dist": "lognormal"}, None, 1.0) == -np.inf
    with pytest.raises(ValueError, match="lognormal prior sigma"):
        engine_v2._log_prior(1.0, {"dist": "lognormal", "sigma": -1.0}, None, 1.0)

    with pytest.raises(ValueError, match="unsupported builtin prior distribution"):
        engine_v2._log_prior(1.0, {"dist": "cauchy"}, None, 1.0)
