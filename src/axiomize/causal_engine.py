"""Causal Engine 2.0 for explicit Model IR causal studies.

The engine never promotes association to causation. It requires supplied
identification evidence, validates DAG structure when present, supports explicit
backdoor adjustment, and uses doubly-robust AIPW for binary treatments when
covariates are available. Diagnostics surface positivity, effective sample size,
and covariate balance rather than hiding weak identification.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.model_ir import ModelIR

_EPS = 1e-8


def _parameter_values(model: ModelIR, overrides: dict[str, float] | None) -> dict[str, float]:
    overrides = dict(overrides or {})
    known = {p.name for p in model.parameters}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise ValueError(f"unknown parameter overrides: {unknown}")
    out: dict[str, float] = {}
    for p in model.parameters:
        raw = overrides[p.name] if p.name in overrides else p.value
        if raw is None:
            raise ValueError(f"parameter {p.name!r} has no value")
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"parameter {p.name!r} must be finite")
        out[p.name] = value
    return out


def _finite_vector(data: dict[str, Any], name: str, *, n: int | None = None) -> np.ndarray:
    if name not in data:
        raise ValueError(f"causal variable {name!r} missing from data")
    arr = np.asarray(data[name], dtype=float)
    if arr.ndim != 1 or arr.size < 3:
        raise ValueError(f"causal variable {name!r} must be a 1D array with at least 3 rows")
    if n is not None and arr.size != n:
        raise ValueError(f"causal variable {name!r} length mismatch")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"causal variable {name!r} must be finite")
    return arr


def _dag(edges: Any) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    parents: dict[str, set[str]] = {}
    children: dict[str, set[str]] = {}
    if edges in (None, []):
        return parents, children
    if not isinstance(edges, list) or len(edges) > 10_000:
        raise ValueError("causal DAG edges must be an array with at most 10000 entries")
    for raw in edges:
        if isinstance(raw, dict):
            source, target = raw.get("source"), raw.get("target")
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            source, target = raw
        else:
            raise ValueError("each causal DAG edge must contain source and target")
        a, b = str(source), str(target)
        if not a or not b or a == b:
            raise ValueError("causal DAG edges require distinct non-empty node names")
        children.setdefault(a, set()).add(b)
        parents.setdefault(b, set()).add(a)
        parents.setdefault(a, set())
        children.setdefault(b, set())
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("causal DAG contains a directed cycle")
        if node in visited:
            return
        visiting.add(node)
        for child in children.get(node, ()):
            visit(child)
        visiting.remove(node); visited.add(node)
    for node in set(parents) | set(children):
        visit(node)
    return parents, children


def _ancestors(node: str, parents: dict[str, set[str]]) -> set[str]:
    out: set[str] = set(); stack = list(parents.get(node, ()))
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current); stack.extend(parents.get(current, ()))
    return out


def _descendants(node: str, children: dict[str, set[str]]) -> set[str]:
    out: set[str] = set(); stack = list(children.get(node, ()))
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current); stack.extend(children.get(current, ()))
    return out


def _derive_adjustment(treatment: str, outcome: str, parents: dict[str, set[str]], children: dict[str, set[str]], observed: set[str]) -> list[str]:
    if not parents and not children:
        return []
    ancestors_y = _ancestors(outcome, parents) | {outcome}
    descendants_t = _descendants(treatment, children)
    candidates = parents.get(treatment, set()) & ancestors_y
    return sorted((candidates - descendants_t - {treatment, outcome}) & observed)


def _ols(X: np.ndarray, y: np.ndarray, *, weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if weights is None:
        Xw, yw = X, y
    else:
        sw = np.sqrt(np.asarray(weights, dtype=float))
        Xw, yw = X * sw[:, None], y * sw
    beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
    residual = y - X @ beta
    # HC1 sandwich; more defensible than homoskedastic-only SE for observational data.
    bread = np.linalg.pinv(X.T @ X if weights is None else X.T @ (weights[:, None] * X))
    score = X * residual[:, None] if weights is None else X * (weights * residual)[:, None]
    meat = score.T @ score
    n, p = X.shape
    hc1 = n / max(1, n - p)
    cov = bread @ meat @ bread * hc1
    return beta, cov, residual


def _logistic_irls(X: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta = np.zeros(X.shape[1], dtype=float)
    for _ in range(100):
        eta = np.clip(X @ beta, -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.maximum(p * (1.0 - p), 1e-6)
        z = eta + (t - p) / w
        new, *_ = np.linalg.lstsq(X * np.sqrt(w)[:, None], z * np.sqrt(w), rcond=None)
        if np.max(np.abs(new - beta)) < 1e-9:
            beta = new; break
        beta = new
    propensity = np.clip(1.0 / (1.0 + np.exp(-np.clip(X @ beta, -30.0, 30.0))), 1e-4, 1 - 1e-4)
    return beta, propensity


def _smd(x: np.ndarray, t: np.ndarray, weights: np.ndarray | None = None) -> float:
    mask1, mask0 = t == 1, t == 0
    if not np.any(mask1) or not np.any(mask0):
        return math.inf
    if weights is None:
        m1, m0 = float(np.mean(x[mask1])), float(np.mean(x[mask0]))
        v1, v0 = float(np.var(x[mask1], ddof=1)), float(np.var(x[mask0], ddof=1))
    else:
        def moments(mask: np.ndarray) -> tuple[float, float]:
            w = weights[mask]; values = x[mask]; s = float(np.sum(w))
            mean = float(np.sum(w * values) / max(s, _EPS))
            var = float(np.sum(w * (values - mean) ** 2) / max(s, _EPS))
            return mean, var
        m1, v1 = moments(mask1); m0, v0 = moments(mask0)
    scale = math.sqrt(max((v1 + v0) / 2.0, _EPS))
    return abs(m1 - m0) / scale


def _binary_effect(y: np.ndarray, t: np.ndarray, Z: np.ndarray, labels: list[str]) -> dict[str, Any]:
    n = y.size
    propX = np.column_stack([np.ones(n), Z]) if Z.size else np.ones((n, 1))
    _, propensity = _logistic_irls(propX, t)
    overlap = {
        "min_propensity": float(np.min(propensity)),
        "max_propensity": float(np.max(propensity)),
        "fraction_outside_0.05_0.95": float(np.mean((propensity < 0.05) | (propensity > 0.95))),
    }
    ipw = t / propensity + (1.0 - t) / (1.0 - propensity)
    ess = float(np.sum(ipw) ** 2 / max(np.sum(ipw ** 2), _EPS))

    Xout = np.column_stack([np.ones(n), t, Z]) if Z.size else np.column_stack([np.ones(n), t])
    beta, cov, residual = _ols(Xout, y)
    reg_effect = float(beta[1]); reg_se = math.sqrt(max(0.0, float(cov[1, 1])))

    # Separate outcome models m1(z), m0(z).
    base = np.column_stack([np.ones(n), Z]) if Z.size else np.ones((n, 1))
    b1, *_ = np.linalg.lstsq(base[t == 1], y[t == 1], rcond=None)
    b0, *_ = np.linalg.lstsq(base[t == 0], y[t == 0], rcond=None)
    m1 = base @ b1; m0 = base @ b0
    psi = m1 - m0 + t * (y - m1) / propensity - (1.0 - t) * (y - m0) / (1.0 - propensity)
    aipw = float(np.mean(psi)); aipw_se = float(np.std(psi, ddof=1) / math.sqrt(n))
    ipw_effect = float(np.mean(t * y / propensity - (1.0 - t) * y / (1.0 - propensity)))

    before: dict[str, float] = {}; after: dict[str, float] = {}
    for i, label in enumerate(labels):
        before[label] = _smd(Z[:, i], t)
        after[label] = _smd(Z[:, i], t, ipw)
    return {
        "estimate": aipw,
        "std_error": aipw_se,
        "ci95": [aipw - 1.96 * aipw_se, aipw + 1.96 * aipw_se],
        "method": "aipw_doubly_robust" if Z.size else "aipw_unadjusted_randomized",
        "estimators": {
            "aipw": {"estimate": aipw, "std_error": aipw_se},
            "ipw": {"estimate": ipw_effect},
            "outcome_regression": {"estimate": reg_effect, "std_error": reg_se},
        },
        "positivity": overlap,
        "effective_sample_size_ipw": ess,
        "balance": {"standardized_mean_difference_before": before, "after_ipw": after},
        "residual_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def _continuous_effect(y: np.ndarray, t: np.ndarray, Z: np.ndarray) -> dict[str, Any]:
    X = np.column_stack([np.ones(y.size), t, Z]) if Z.size else np.column_stack([np.ones(y.size), t])
    beta, cov, residual = _ols(X, y)
    effect = float(beta[1]); se = math.sqrt(max(0.0, float(cov[1, 1])))
    return {
        "estimate": effect, "std_error": se,
        "ci95": [effect - 1.96 * se, effect + 1.96 * se],
        "method": "robust_linear_backdoor_adjustment",
        "residual_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def estimate_causal_model(model: ModelIR, *, t_span: tuple[float, float], points: int,
                          parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del t_span, points, seed
    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("causal", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.causal must be an object")
    data = cfg.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("causal.data must be an object")
    treatment = str(cfg.get("treatment", "")); outcome = str(cfg.get("outcome", ""))
    if not treatment or not outcome:
        raise ValueError("causal model requires treatment and outcome names")
    y = _finite_vector(data, outcome); t = _finite_vector(data, treatment, n=y.size)

    identification = cfg.get("identification", model.metadata.get("causal_identification", {}))
    if not isinstance(identification, dict):
        identification = {}
    edges = identification.get("dag_edges", cfg.get("dag_edges", cfg.get("dag", [])))
    parents, children = _dag(edges)
    explicit = identification.get("adjustment_set", cfg.get("adjustment_set", cfg.get("covariates")))
    if explicit is not None and not isinstance(explicit, list):
        raise ValueError("causal adjustment_set must be an array")
    if explicit is None:
        adjustment = _derive_adjustment(treatment, outcome, parents, children, set(data))
    else:
        adjustment = [str(v) for v in explicit]
    if treatment in adjustment or outcome in adjustment:
        raise ValueError("adjustment set cannot include treatment or outcome")
    descendants = _descendants(treatment, children)
    post_treatment = sorted(set(adjustment) & descendants)
    if post_treatment:
        raise ValueError(f"adjustment set contains descendants of treatment: {post_treatment}")

    randomized = bool(identification.get("randomized") or identification.get("intervention"))
    dag_identified = bool(identification.get("identified_dag") or (parents and outcome in (set(parents) | set(children))))
    assumptions = identification.get("assumptions", [])
    if not randomized and not dag_identified and not (adjustment and assumptions):
        return {
            "status": "INSUFFICIENT_CAUSAL_EVIDENCE",
            "family": model.family.value,
            "detail": "causal conclusion unavailable: provide randomization/intervention evidence or a DAG/backdoor set with explicit assumptions",
            "required_next_evidence": ["randomization/intervention", "acyclic DAG plus measured adjustment variables", "explicit exchangeability/positivity assumptions"],
        }

    covariates = [_finite_vector(data, name, n=y.size) for name in adjustment]
    Z = np.column_stack(covariates) if covariates else np.empty((y.size, 0))
    unique_t = np.unique(t)
    is_binary = unique_t.size == 2 and set(np.round(unique_t, 12).tolist()) <= {0.0, 1.0}
    if is_binary:
        effect = _binary_effect(y, t.astype(int), Z, adjustment)
    else:
        effect = _continuous_effect(y, t, Z)

    # Intervention predictions use the robust regression estimand, conditional on
    # mean adjustment values; they are explicitly scoped to the identification assumptions.
    X = np.column_stack([np.ones(y.size), t, Z]) if Z.size else np.column_stack([np.ones(y.size), t])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    means = [float(np.mean(Z[:, i])) for i in range(Z.shape[1])]
    counterfactuals: list[dict[str, Any]] = []
    values = cfg.get("intervention_values", [])
    if isinstance(values, list):
        for raw in values[:1000]:
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError("intervention values must be finite")
            row = np.asarray([1.0, value, *means])
            counterfactuals.append({"do": {treatment: value}, "predicted_outcome_mean": float(row @ beta)})

    warning: list[str] = []
    if is_binary:
        positivity = effect.get("positivity", {})
        if float(positivity.get("fraction_outside_0.05_0.95", 0.0)) > 0.1:
            warning.append("limited propensity overlap; causal estimate may be extrapolation-sensitive")
        after = effect.get("balance", {}).get("after_ipw", {})
        if any(float(v) > 0.1 for v in after.values()):
            warning.append("residual covariate imbalance after weighting exceeds SMD 0.1")
    return {
        "status": "PASS",
        "family": model.family.value,
        "states": {},
        "parameters": parameters,
        "causal_effect": {"treatment": treatment, "outcome": outcome, **effect},
        "counterfactuals": counterfactuals,
        "identification": {
            **identification,
            "dag_validated_acyclic": bool(parents or children),
            "adjustment_set_used": adjustment,
            "randomized_or_interventional": randomized,
        },
        "solver": {"backend": "numpy", "method": effect["method"]},
        "diagnostics": {"n": int(y.size), "binary_treatment": is_binary, "warnings": warning},
        "causal_scope": "causal interpretation is valid only conditional on the supplied identification assumptions, measured adjustment set, consistency, positivity, and no unmeasured confounding where required",
    }
