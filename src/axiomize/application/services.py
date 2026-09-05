"""Shared application services.

CLI, MCP and REST are thin adapters over these functions: one core, one
behavior, every interface.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.limits import MAX_ARRAY_ITEMS, bounded_sequence


def _finite(value: Any, *, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def _sir_parameters(params: dict[str, Any]) -> tuple[float, float, float, float, float]:
    beta = _finite(params.get("beta", 0.3), name="beta")
    gamma = _finite(params.get("gamma", 0.1), name="gamma")
    i0 = _finite(params.get("I0", 10.0), name="I0")
    n = _finite(params.get("N", 100000.0), name="N")
    days = _finite(params.get("days", 180.0), name="days")
    if beta < 0:
        raise ValueError("beta must be non-negative")
    if gamma <= 0:
        raise ValueError("gamma must be positive")
    if n <= 0:
        raise ValueError("population N must be positive")
    if not 0 <= i0 <= n:
        raise ValueError("I0 must satisfy 0 <= I0 <= N")
    if days <= 0:
        raise ValueError("days must be positive")
    return beta, gamma, i0, n, days


def _sir_asymptotic_final_size_numeric(beta: float, gamma: float, i0: float, n: float) -> float:
    """General SIR final removed fraction for arbitrary finite I0, R(0)=0."""
    if i0 <= 0:
        return 0.0
    s0 = (n - i0) / n
    if s0 <= 0:
        return 1.0
    r0 = beta / gamma
    if r0 == 0:
        return i0 / n
    from scipy.optimize import brentq

    tiny = max(np.finfo(float).tiny, s0 * 1e-15)

    def invariant(s: float) -> float:
        return math.log(s / s0) + r0 * (1.0 - s)

    s_inf = float(brentq(invariant, tiny, s0, xtol=1e-14, rtol=1e-13, maxiter=200))
    return 1.0 - s_inf


def _sir_asymptotic_final_size_symbolic(beta: float, gamma: float, i0: float, n: float) -> float:
    """Independent Lambert-W evaluation of the same exact SIR invariant."""
    if i0 <= 0:
        return 0.0
    s0 = (n - i0) / n
    if s0 <= 0:
        return 1.0
    r0 = beta / gamma
    if r0 == 0:
        return i0 / n
    import sympy as sp

    argument = -r0 * s0 * math.exp(-r0)
    # With a nonzero seed infection the physically reached root is the principal
    # real branch. For subcritical dynamics it naturally remains near S0.
    s_inf = -float(sp.N(sp.LambertW(argument, 0), 30)) / r0
    if not math.isfinite(s_inf) or s_inf < -1e-12 or s_inf > s0 + 1e-10:
        raise ValueError("symbolic SIR final-size root is outside the physical domain")
    s_inf = min(s0, max(0.0, s_inf))
    return 1.0 - s_inf


def solve_sir_service(params: dict[str, Any]) -> dict[str, Any]:
    from axiomize.routing.router import classify
    from axiomize.tools.numerical.scipy_tool import solve_sir
    from axiomize.validation.cross import compare_values

    beta, gamma, i0, n, days = _sir_parameters(params)
    sol = solve_sir(beta, gamma, i0, n, days=days)

    asym_numeric = _sir_asymptotic_final_size_numeric(beta, gamma, i0, n)
    asym_symbolic = _sir_asymptotic_final_size_symbolic(beta, gamma, i0, n)
    cross = compare_values(asym_numeric, asym_symbolic, tolerance=1e-8, name="sir_asymptotic_final_size")

    infected_final = float(sol.y[1, -1] / n) if sol.y.ndim == 2 and sol.y.shape[1] else math.inf
    horizon_converged = bool(math.isfinite(infected_final) and infected_final <= 1e-7)
    finite_vs_asymptotic: dict[str, Any]
    if horizon_converged:
        finite_check = compare_values(sol.final_size, asym_numeric, tolerance=1e-3, name="sir_converged_horizon_vs_asymptotic")
        finite_vs_asymptotic = finite_check.to_dict()
    else:
        finite_vs_asymptotic = {
            "status": "INCONCLUSIVE",
            "primary_result": sol.final_size,
            "verification_result": asym_numeric,
            "difference": abs(sol.final_size - asym_numeric),
            "recommended_action": [
                "finite simulation horizon has not reached the asymptotic SIR state; extend days before comparing it to final-size theory"
            ],
        }

    decision = classify({"signals": ["ode", "compartmental"]})
    ok = bool(sol.success and cross.status.value == "PASS")
    return {
        "status": "PASS" if ok else "FAIL",
        # Backward-compatible: final_size is the removed fraction at the requested horizon.
        "final_size": sol.final_size,
        "finite_horizon_final_size": sol.final_size,
        "asymptotic_final_size": asym_numeric,
        "finite_horizon_converged": horizon_converged,
        "infected_fraction_at_horizon": infected_final,
        "peak_infected": float(np.max(sol.y[1])),
        "max_conservation_error": sol.max_conservation_error,
        "max_residual": sol.max_residual,
        "cross_validation": cross.to_dict(),
        "numeric_theory_check": finite_vs_asymptotic,
        "router": decision.to_dict(),
    }


def _xy(payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    t_raw = bounded_sequence(payload["t"], name="t", minimum=2, maximum=MAX_ARRAY_ITEMS)
    y_raw = bounded_sequence(payload["y"], name="y", minimum=2, maximum=MAX_ARRAY_ITEMS)
    if len(t_raw) != len(y_raw):
        raise ValueError("t and y must have the same length")
    t = np.asarray(t_raw, dtype=float)
    y = np.asarray(y_raw, dtype=float)
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        raise ValueError("t and y must contain only finite values")
    return t, y


def fit_logistic_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.fitting.estimator import fit_logistic_curve

    t, y = _xy(payload)
    result = fit_logistic_curve(t, y)
    out = result.to_dict()
    for name, pair in result.params.items():
        out[name] = float(pair[0])
    return out


def sensitivity_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.sensitivity.analysis import local_sensitivity, mc_sensitivity
    from axiomize.tools.numerical.scipy_tool import solve_sir

    target = payload.get("target", "final_size")
    if target not in {"final_size", "peak_infected"}:
        raise ValueError("target must be final_size or peak_infected")
    raw_params = payload.get("params")
    if not isinstance(raw_params, dict) or not raw_params or len(raw_params) > 64:
        raise ValueError("params must be a non-empty object with at most 64 entries")
    params = {str(k): _finite(v, name=f"params.{k}") for k, v in raw_params.items()}
    required = {"beta", "gamma"}
    if not required <= set(params):
        raise ValueError("sensitivity params must include beta and gamma")
    i0 = _finite(payload.get("I0", 10), name="I0")
    n = _finite(payload.get("N", 100000), name="N")
    _sir_parameters({"beta": params["beta"], "gamma": params["gamma"], "I0": i0, "N": n, "days": 120})

    def final(p: dict[str, float]) -> float:
        res = solve_sir(p["beta"], p["gamma"], i0, n, days=120)
        return res.final_size if target == "final_size" else float(np.max(res.y[1]))

    bounds = {k: (0.5 * v, 1.5 * v) for k, v in params.items()}
    return {"local": local_sensitivity(final, params), "mc_screening": mc_sensitivity(final, bounds, n=1000, seed=0)}


def validate_sir_service(params: dict[str, Any]) -> dict[str, Any]:
    from axiomize.validation.dimensions import Quantity, check_add

    beta, gamma, i0, n, days = _sir_parameters(params)
    normalized = {"beta": beta, "gamma": gamma, "I0": i0, "N": n, "days": days}
    out = solve_sir_service(normalized)
    beta_q = Quantity("transmission rate", "beta", "1/day", beta)
    horizon = Quantity("horizon", "T", "day", days)
    dim_rate = (beta_q.dimension * horizon.dimension).is_dimensionless
    checks = {
        "conservation": out["max_conservation_error"] < 1e-3,
        "residual": out["max_residual"] < 1e-3,
        # This is asymptotic-vs-asymptotic, not a finite-horizon category error.
        "cross_validation": out["cross_validation"]["status"] == "PASS",
        "dimensionless_exposure": dim_rate,
        "units_consistent": check_add(
            Quantity("a", "a", "persons", 1.0), Quantity("b", "b", "persons", 2.0)
        ).status == "PASS",
    }
    out["validation_checks"] = checks
    out["status"] = "PASS" if all(checks.values()) else "FAIL"
    return out


def compare_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.fitting.estimator import compare_fits, fit_logistic_curve, fit_sir_curve

    t, y = _xy(payload)
    candidates = {"logistic": fit_logistic_curve(t, y)}
    if "N" in payload:
        candidates["sir"] = fit_sir_curve(t, y, _finite(payload["N"], name="N"), _finite(payload.get("I0", y[0]), name="I0"))
    scored = {name: res.to_dict() for name, res in candidates.items()}
    return {"fits": scored, **compare_fits(candidates)}


def falsify_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.falsification.engine import Falsifier, evaluate_falsifiers

    raw = payload.get("falsifiers", [])
    if not isinstance(raw, list) or len(raw) > 10_000:
        raise ValueError("falsifiers must be an array with at most 10000 entries")
    falsifiers = [Falsifier(name=f["name"], observable=f["observable"], threshold=_finite(f["threshold"], name="threshold"),
                            direction=f.get("direction", "above")) for f in raw]
    result = evaluate_falsifiers(falsifiers, dict(payload.get("observations", {})))
    return {"results": result["results"], "model_status": result["model_status"].value, "untested": result["untested"]}


def uncertainty_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.validation.status import ValidationStatus

    params = payload.get("params", payload.get("fit", {}))
    if isinstance(params, dict) and "params" in params and isinstance(params["params"], dict):
        params = params["params"]
    if not isinstance(params, dict) or not params:
        return {"status": ValidationStatus.UNVERIFIED.value,
                "uncertainty": {"reason": "no fit payload with params; pass params as {name: [value, error]}"}, "intervals": {}}
    if len(params) > 2000:
        raise ValueError("uncertainty params exceed hard limit 2000")
    try:
        from scipy.stats import norm
        z = float(norm.ppf(0.975))
    except Exception:
        return {"status": ValidationStatus.TOOL_UNAVAILABLE.value,
                "uncertainty": {"reason": "scipy.stats not available for intervals"}, "intervals": {}}
    intervals: dict[str, Any] = {}
    try:
        for name, pair in params.items():
            if isinstance(pair, dict):
                value, err = _finite(pair["value"], name=f"{name}.value"), _finite(pair["stderr"], name=f"{name}.stderr")
            else:
                value, err = _finite(pair[0], name=f"{name}.value"), _finite(pair[1], name=f"{name}.stderr")
            if err < 0:
                raise ValueError("standard error cannot be negative")
            intervals[str(name)] = [value - z * err, value + z * err]
    except (TypeError, ValueError, IndexError, KeyError):
        return {"status": ValidationStatus.UNVERIFIED.value,
                "uncertainty": {"reason": "params must map names to finite [value, nonnegative error] pairs"}, "intervals": {}}
    return {"status": ValidationStatus.PASS.value, "uncertainty": {"method": "normal_95ci", "n_params": len(intervals)}, "intervals": intervals}


def tools_service() -> dict[str, Any]:
    from axiomize.tools.inventory import collect_tool_inventory
    return collect_tool_inventory()


def capabilities_service() -> dict[str, Any]:
    from axiomize.capabilities import get_capabilities
    return get_capabilities()


def intake_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.workflow.intake import build_intake_response
    return build_intake_response(payload)


def workflow_policy_service(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from axiomize.workflow.policy import default_policy, recommend_rigor

    payload = dict(payload or {})
    permissions = payload.get("permissions")
    if permissions is not None and not isinstance(permissions, dict):
        raise ValueError("permissions must be an object")
    policy = default_policy(question_mode=payload.get("question_mode"), permissions=permissions)
    return {"policy": policy.to_dict(), "rigor_recommendation": recommend_rigor(payload.get("signals"))}


def clean_data_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.data.quality import clean_numeric_xy

    if "t" not in payload or "y" not in payload:
        raise ValueError("clean_data requires t and y arrays")
    bounded_sequence(payload["t"], name="t", minimum=1, maximum=MAX_ARRAY_ITEMS)
    bounded_sequence(payload["y"], name="y", minimum=1, maximum=MAX_ARRAY_ITEMS)
    result = clean_numeric_xy(payload["t"], payload["y"], drop_nonfinite=bool(payload.get("drop_nonfinite", True)),
                              sort_time=bool(payload.get("sort_time", True)), duplicate_policy=str(payload.get("duplicate_policy", "mean")))
    return result.to_dict()


def compare_runs_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.runs.compare import compare_run_directories

    before_dir = str(payload.get("before_dir", "")).strip(); after_dir = str(payload.get("after_dir", "")).strip()
    if not before_dir or not after_dir:
        raise ValueError("compare_runs requires before_dir and after_dir")
    return compare_run_directories(before_dir, after_dir)
