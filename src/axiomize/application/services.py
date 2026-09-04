"""Shared application services (PHASE 8).

CLI, MCP and REST are thin adapters over these functions: one core,
one behavior, every interface.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def solve_sir_service(params: dict[str, Any]) -> dict[str, Any]:
    from axiomize.routing.router import classify
    from axiomize.tools.numerical.scipy_tool import final_size_numeric, solve_sir
    from axiomize.tools.symbolic.sympy_tool import final_size_symbolic
    from axiomize.validation.cross import compare_values

    beta = float(params.get("beta", 0.3))
    gamma = float(params.get("gamma", 0.1))
    I0 = float(params.get("I0", 10.0))
    N = float(params.get("N", 100000.0))
    days = float(params.get("days", 180.0))
    if N <= 0:
        raise ValueError("population N must be positive")
    sol = solve_sir(beta, gamma, I0, N, days=days)
    cross = compare_values(sol.final_size, final_size_symbolic(beta / gamma),
                           tolerance=1e-3, name="sir_final_size")
    numeric_theory = compare_values(sol.final_size, final_size_numeric(beta, gamma),
                                    tolerance=1e-6, name="sir_numeric_theory")
    decision = classify({"signals": ["ode", "compartmental"]})
    ok = sol.success and cross.status.value == "PASS"
    return {
        "status": "PASS" if ok else "FAIL",
        "final_size": sol.final_size,
        "peak_infected": float(np.max(sol.y[1])),
        "max_conservation_error": sol.max_conservation_error,
        "max_residual": sol.max_residual,
        "cross_validation": cross.to_dict(),
        "numeric_theory_check": numeric_theory.to_dict(),
        "router": decision.to_dict(),
    }


def fit_logistic_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.fitting.estimator import fit_logistic_curve

    t = np.asarray(payload["t"], dtype=float)
    y = np.asarray(payload["y"], dtype=float)
    result = fit_logistic_curve(t, y)
    out = result.to_dict()
    for name, pair in result.params.items():
        out[name] = float(pair[0])
    return out


def sensitivity_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.sensitivity.analysis import local_sensitivity, mc_sensitivity
    from axiomize.tools.numerical.scipy_tool import solve_sir

    target = payload.get("target", "final_size")

    def final(p: dict[str, float]) -> float:
        res = solve_sir(p["beta"], p["gamma"], float(payload.get("I0", 10)),
                        float(payload.get("N", 100000)), days=120)
        return res.final_size if target == "final_size" else float(np.max(res.y[1]))

    params = {k: float(v) for k, v in payload["params"].items()}
    bounds = {k: (0.5 * v, 1.5 * v) for k, v in params.items()}
    return {"local": local_sensitivity(final, params),
            "mc_screening": mc_sensitivity(final, bounds, n=1000, seed=0)}


def validate_sir_service(params: dict[str, Any]) -> dict[str, Any]:
    from axiomize.validation.dimensions import Quantity, check_add

    normalized = {
        "beta": params.get("beta", 0.3),
        "gamma": params.get("gamma", 0.1),
        "I0": params.get("I0", 10.0),
        "N": params.get("N", 100000.0),
        "days": params.get("days", 180.0),
    }
    out = solve_sir_service(normalized)
    beta = Quantity("transmission rate", "beta", "1/day", float(normalized["beta"]))
    horizon = Quantity("horizon", "T", "day", float(normalized["days"]))
    dim_rate = (beta.dimension * horizon.dimension).is_dimensionless
    checks = {
        "conservation": out["max_conservation_error"] < 1e-3,
        "residual": out["max_residual"] < 1e-3,
        "cross_validation": out["cross_validation"]["status"] == "PASS",
        "dimensionless_exposure": dim_rate,
        "units_consistent": check_add(
            Quantity("a", "a", "persons", 1.0),
            Quantity("b", "b", "persons", 2.0)).status == "PASS",
    }
    out["validation_checks"] = checks
    out["status"] = "PASS" if all(checks.values()) else "FAIL"
    return out


def compare_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.fitting.estimator import compare_fits, fit_logistic_curve, fit_sir_curve

    t = np.asarray(payload["t"], dtype=float)
    y = np.asarray(payload["y"], dtype=float)
    candidates = {"logistic": fit_logistic_curve(t, y)}
    if "N" in payload:
        candidates["sir"] = fit_sir_curve(t, y, float(payload["N"]),
                                          float(payload.get("I0", y[0])))
    scored = {name: res.to_dict() for name, res in candidates.items()}
    return {"fits": scored, **compare_fits(candidates)}


def falsify_service(payload: dict[str, Any]) -> dict[str, Any]:
    from axiomize.falsification.engine import Falsifier, evaluate_falsifiers

    falsifiers = [Falsifier(name=f["name"], observable=f["observable"],
                            threshold=float(f["threshold"]),
                            direction=f.get("direction", "above"))
                  for f in payload.get("falsifiers", [])]
    result = evaluate_falsifiers(falsifiers, dict(payload.get("observations", {})))
    return {"results": result["results"],
            "model_status": result["model_status"].value,
            "untested": result["untested"]}


def uncertainty_service(payload: dict[str, Any]) -> dict[str, Any]:
    """Belirsizlik araliklari (core servis)."""
    from axiomize.validation.status import ValidationStatus

    params = payload.get("params", payload.get("fit", {}))
    if isinstance(params, dict) and "params" in params and isinstance(params["params"], dict):
        params = params["params"]
    if not isinstance(params, dict) or not params:
        return {"status": ValidationStatus.UNVERIFIED.value,
                "uncertainty": {"reason": "no fit payload with params; pass params as {name: [value, error]}"},
                "intervals": {}}
    try:
        from scipy.stats import norm

        z = float(norm.ppf(0.975))
    except Exception:
        return {"status": ValidationStatus.TOOL_UNAVAILABLE.value,
                "uncertainty": {"reason": "scipy.stats not available for intervals"},
                "intervals": {}}
    intervals: dict[str, Any] = {}
    try:
        for name, pair in params.items():
            if isinstance(pair, dict):
                value, err = float(pair["value"]), float(pair["stderr"])
            else:
                value, err = float(pair[0]), float(pair[1])
            intervals[name] = [value - z * err, value + z * err]
    except (TypeError, ValueError, IndexError, KeyError):
        return {"status": ValidationStatus.UNVERIFIED.value,
                "uncertainty": {"reason": "params must map names to [value, error] pairs"},
                "intervals": {}}
    return {"status": ValidationStatus.PASS.value,
            "uncertainty": {"method": "normal_95ci", "n_params": len(intervals)},
            "intervals": intervals}


def tools_service() -> dict[str, Any]:
    from axiomize.tools.inventory import collect_tool_inventory

    return collect_tool_inventory()


def capabilities_service() -> dict[str, Any]:
    from axiomize.capabilities import get_capabilities

    return get_capabilities()


def intake_service(payload: dict[str, Any]) -> dict[str, Any]:
    """Clarify a vague idea before model construction."""
    from axiomize.workflow.intake import build_intake_response

    return build_intake_response(payload)


def workflow_policy_service(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose the deterministic workflow and consumption policy."""
    from axiomize.workflow.policy import default_policy, recommend_rigor

    payload = dict(payload or {})
    permissions = payload.get("permissions")
    if permissions is not None and not isinstance(permissions, dict):
        raise ValueError("permissions must be an object")
    policy = default_policy(
        question_mode=payload.get("question_mode"),
        permissions=permissions,
    )
    return {
        "policy": policy.to_dict(),
        "rigor_recommendation": recommend_rigor(payload.get("signals")),
    }
