"""Multi-start calibration and profile-likelihood identifiability.

``fit_curve`` used a single curve_fit start (local-minimum risk) and reported
no identifiability. It now accepts deterministic multi-start seeds (best RSS
wins) and an opt-in profile-likelihood flag that marks parameters whose profile
is flat (the data cannot pin them down). Defaults preserve prior behaviour.
"""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.fitting import estimator as est


def _linear_data():
    t = np.linspace(0.0, 5.0, 25)
    return t, 3.0 * t


def test_default_single_start_is_backward_compatible() -> None:
    t, y = _linear_data()
    res = est.fit_curve(lambda tt, a: a * tt, t, y, [1.0], ["a"], bounds=([0.0], [10.0]))
    assert res.success
    assert res.n_starts == 1
    assert res.identifiability == {}
    assert res.params["a"][0] == pytest.approx(3.0, abs=1e-6)


def test_multistart_fits_at_least_as_well_as_single_start() -> None:
    t = np.linspace(0.0, 4.0, 30)
    y = 2.5 * np.exp(-0.7 * t)

    def model(tt, a, b):
        return a * np.exp(-b * tt)

    single = est.fit_curve(model, t, y, [5.0, 3.0], ["a", "b"], bounds=([0.01, 0.01], [20.0, 20.0]))
    multi = est.fit_curve(model, t, y, [5.0, 3.0], ["a", "b"], bounds=([0.01, 0.01], [20.0, 20.0]), n_starts=6)
    assert multi.success
    assert multi.n_starts == 6
    assert multi.rmse <= single.rmse + 1e-9


@pytest.mark.parametrize("n_starts", [0, -1, 17])
def test_n_starts_is_bounded(n_starts) -> None:
    t, y = _linear_data()
    with pytest.raises(ValueError, match="fit starts"):
        est.fit_curve(lambda tt, a: a * tt, t, y, [1.0], ["a"], n_starts=n_starts)


def test_generate_starts_spans_finite_and_infinite_bounds() -> None:
    starts = est._generate_starts([1.0, 2.0], [0.0, -np.inf], [10.0, np.inf], 3)
    assert len(starts) == 3
    np.testing.assert_allclose(starts[0], [1.0, 2.0])
    assert 0.0 < starts[1][0] < 10.0
    assert starts[1][1] > 2.0


def test_multistart_all_starts_fail_falls_back(monkeypatch) -> None:
    t, y = _linear_data()
    monkeypatch.setattr(est, "_fit_once", lambda *a, **k: (np.array([1.0]), np.array([np.inf]), False))
    popt, perr, success = est._multistart_fit(lambda tt, a: a * tt, t, y, [1.0], [0.0], [10.0], 4)
    assert success is False


def test_multistart_skips_raising_model(monkeypatch) -> None:
    t, y = _linear_data()
    monkeypatch.setattr(est, "_fit_once", lambda *a, **k: (np.array([float("nan")]), np.array([np.inf]), True))

    def raising(tt, a):
        raise ValueError("boom")

    popt, perr, success = est._multistart_fit(raising, t, y, [1.0], [0.0], [10.0], 3)
    # every candidate's model raised -> skipped; fallback returns the stub result
    assert np.isnan(popt[0])


def test_multistart_skips_nonfinite_fitted(monkeypatch) -> None:
    t, y = _linear_data()
    monkeypatch.setattr(est, "_fit_once", lambda *a, **k: (np.array([1.0]), np.array([0.1]), True))
    popt, perr, success = est._multistart_fit(lambda tt, a: np.full_like(tt, np.nan), t, y, [1.0], [0.0], [10.0], 3)
    assert popt[0] == 1.0


def test_profile_single_param_is_identifiable() -> None:
    t, y = _linear_data()
    res = est.fit_curve(lambda tt, a: a * tt, t, y, [1.0], ["a"], bounds=([0.0], [10.0]), profile=True)
    assert res.identifiability["a"]["identifiable"] is True
    assert res.identifiability["identifiable"] is True
    assert res.identifiability["a"]["profile_rss_increase"] > 0.0


def test_profile_degenerate_product_is_not_identifiable() -> None:
    t = np.linspace(0.1, 5.0, 25)
    y = 2.0 * t
    res = est.fit_curve(lambda tt, a, b: (a * b) * tt, t, y, [1.0, 1.0], ["a", "b"],
                        bounds=([0.01, 0.01], [100.0, 100.0]), profile=True)
    assert res.success
    assert res.identifiability["identifiable"] is False


def test_profile_at_bound_skips_probe() -> None:
    t = np.linspace(0.0, 5.0, 25)
    y = 1.0 * t
    res = est.fit_curve(lambda tt, a: a * tt, t, y, [0.5], ["a"], bounds=([0.0], [1.0]), profile=True)
    assert res.identifiability["a"]["identifiable"] is False


def test_profile_rss_k1_handles_raise_and_nonfinite() -> None:
    t = np.linspace(0.0, 5.0, 10)
    y = 3.0 * t

    def raising(tt, a):
        raise ValueError("boom")

    assert est._profile_rss(raising, t, y, np.array([3.0]), [0.0], [10.0], 0, 3.5, 0.0) == 0.0
    assert est._profile_rss(lambda tt, a: np.full_like(tt, np.nan), t, y,
                            np.array([3.0]), [0.0], [10.0], 0, 3.5, 0.0) == 0.0
    assert est._profile_rss(lambda tt, a: a * tt, t, y, np.array([3.0]), [0.0], [10.0], 0, 3.5, 0.0) > 0.0


def test_profile_rss_k2_handles_raise_and_nonfinite(monkeypatch) -> None:
    t = np.linspace(0.1, 5.0, 10)
    y = 2.0 * t
    popt = np.array([1.0, 2.0])

    def raising(tt, a, b):
        return (a * b) * tt

    import scipy.optimize as so
    monkeypatch.setattr(so, "curve_fit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no fit")))
    assert est._profile_rss(raising, t, y, popt, [0.01, 0.01], [100.0, 100.0], 0, 1.5, 0.0) == 0.0

    monkeypatch.setattr(so, "curve_fit", lambda *a, **k: (np.array([2.0]), np.eye(1)))
    assert est._profile_rss(lambda tt, a, b: np.full_like(tt, np.nan), t, y,
                            popt, [0.01, 0.01], [100.0, 100.0], 0, 1.5, 0.0) == 0.0


def test_profile_rss_k2_normal_increase() -> None:
    t = np.linspace(0.1, 5.0, 20)
    y = 3.0 * np.exp(-0.5 * t)
    popt = np.array([3.0, 0.5])
    increase = est._profile_rss(lambda tt, a, b: a * np.exp(-b * tt), t, y,
                                popt, [0.01, 0.01], [20.0, 20.0], 0, 4.0, 0.0)
    assert increase > 0.0


def test_fit_result_to_dict_includes_new_fields() -> None:
    t, y = _linear_data()
    res = est.fit_curve(lambda tt, a: a * tt, t, y, [1.0], ["a"], bounds=([0.0], [10.0]),
                        n_starts=2, profile=True)
    payload = res.to_dict()
    assert payload["n_starts"] == 2
    assert "identifiability" in payload
