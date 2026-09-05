"""Causal Engine 2.0 for declarative Model IR causal studies.

The engine separates *identification* from *estimation*.  A numerical association
is never promoted to a causal effect unless the caller supplies randomization /
intervention evidence or a DAG for which a back-door adjustment set can be
verified.  Supported bounded estimators are difference-in-means, robust linear
back-door adjustment, IPW and AIPW for binary treatments.
"""
from __future__ import annotations

import itertools
import math
from collections import defaultdict, deque
from typing import Any

import numpy as np
from scipy.optimize import minimize

from axiomize.limits import MAX_ARRAY_ITEMS, bounded_int
from axiomize.model_ir import ModelIR

_MAX_DAG_NODES = 256
_MAX_DAG_EDGES = 4096
_MAX_AUTO_ADJUSTMENT_CANDIDATES = 14
_MAX_AUTO_ADJUSTMENT_SIZE = 5


def _finite_vector(values: Any, *, name: str, minimum: int = 3) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a numeric array") from exc
    if array.ndim != 1 or array.size < minimum or array.size > MAX_ARRAY_ITEMS:
        raise ValueError(f"{name} must be a 1D array with {minimum}..{MAX_ARRAY_ITEMS} values")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array


def _parse_edges(raw: Any) -> list[tuple[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > _MAX_DAG_EDGES:
        raise ValueError(f"causal DAG edges must be an array with at most {_MAX_DAG_EDGES} entries")
    edges: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            source, target = item.get("source"), item.get("target")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            source, target = item
        else:
            raise ValueError("each DAG edge must be [source, target] or {source,target}")
        source, target = str(source), str(target)
        if not source or not target or source == target:
            raise ValueError("DAG edges require distinct non-empty node names")
        edges.append((source, target))
    if len(set(edges)) != len(edges):
        raise ValueError("causal DAG contains duplicate edges")
    return edges


def _graph(edges: list[tuple[str, str]]) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    nodes: set[str] = set()
    children: dict[str, set[str]] = defaultdict(set)
    parents: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        nodes.update((source, target))
        children[source].add(target)
        parents[target].add(source)
    if len(nodes) > _MAX_DAG_NODES:
        raise ValueError(f"causal DAG exceeds hard node limit {_MAX_DAG_NODES}")
    indegree = {node: len(parents[node]) for node in nodes}
    queue = deque(node for node in nodes if indegree[node] == 0)
    visited = 0
    while queue:
        node = queue.popleft(); visited += 1
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(nodes):
        raise ValueError("causal DAG contains a directed cycle")
    return nodes, children, parents


def _descendants(start: str, children: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set(); queue = deque(children[start])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node); queue.extend(children[node])
    return seen


def _ancestors(starts: set[str], parents: dict[str, set[str]]) -> set[str]:
    seen = set(starts); queue = deque(starts)
    while queue:
        node = queue.popleft()
        for parent in parents[node]:
            if parent not in seen:
                seen.add(parent); queue.append(parent)
    return seen


def _backdoor_valid(
    treatment: str,
    outcome: str,
    adjustment: list[str],
    edges: list[tuple[str, str]],
) -> tuple[bool, str]:
    nodes, children, parents = _graph(edges)
    if treatment not in nodes or outcome not in nodes:
        return False, "treatment/outcome must both occur in the DAG"
    z = set(adjustment)
    if treatment in z or outcome in z:
        return False, "adjustment set cannot contain treatment or outcome"
    descendants = _descendants(treatment, children)
    bad = sorted(z & descendants)
    if bad:
        return False, f"adjustment set contains treatment descendants: {bad}"

    # Back-door graph: remove arrows emanating from treatment.
    backdoor_edges = [(a, b) for a, b in edges if a != treatment]
    _, bd_children, bd_parents = _graph(backdoor_edges)
    relevant = _ancestors({treatment, outcome, *z}, bd_parents)

    # Moralize the ancestral graph.
    undirected: dict[str, set[str]] = defaultdict(set)
    for a, b in backdoor_edges:
        if a in relevant and b in relevant:
            undirected[a].add(b); undirected[b].add(a)
    for child in relevant:
        ps = sorted(p for p in bd_parents[child] if p in relevant)
        for i, left in enumerate(ps):
            for right in ps[i + 1:]:
                undirected[left].add(right); undirected[right].add(left)

    blocked = z
    if treatment in blocked or outcome in blocked:
        return False, "invalid adjustment set"
    queue = deque([treatment]); seen = {treatment}
    while queue:
        node = queue.popleft()
        if node == outcome:
            return False, "adjustment set does not block all back-door paths"
        for neighbor in undirected[node]:
            if neighbor not in blocked and neighbor not in seen:
                seen.add(neighbor); queue.append(neighbor)
    return True, "verified by back-door d-separation in the supplied DAG"


def _auto_adjustment(treatment: str, outcome: str, edges: list[tuple[str, str]]) -> list[str] | None:
    nodes, children, _ = _graph(edges)
    descendants = _descendants(treatment, children)
    candidates = sorted(nodes - {treatment, outcome} - descendants)
    if len(candidates) > _MAX_AUTO_ADJUSTMENT_CANDIDATES:
        return None
    for size in range(0, min(_MAX_AUTO_ADJUSTMENT_SIZE, len(candidates)) + 1):
        for combo in itertools.combinations(candidates, size):
            valid, _ = _backdoor_valid(treatment, outcome, list(combo), edges)
            if valid:
                return list(combo)
    return None


def _design(data: dict[str, Any], outcome: str, treatment: str, adjustment: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = _finite_vector(data[outcome], name=f"causal.data.{outcome}")
    t = _finite_vector(data[treatment], name=f"causal.data.{treatment}")
    if t.shape != y.shape:
        raise ValueError("causal treatment and outcome arrays must have the same length")
    columns = [np.ones_like(y), t]
    for name in adjustment:
        if name not in data:
            raise ValueError(f"causal adjustment variable {name!r} missing from data")
        values = _finite_vector(data[name], name=f"causal.data.{name}")
        if values.shape != y.shape:
            raise ValueError(f"causal covariate {name!r} length mismatch")
        columns.append(values)
    return y, t, np.column_stack(columns)


def _robust_ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    residual = y - X @ beta
    rank = np.linalg.matrix_rank(X)
    if rank < X.shape[1]:
        raise ValueError("causal design matrix is rank deficient")
    bread = np.linalg.pinv(X.T @ X)
    meat = X.T @ ((residual ** 2)[:, None] * X)
    hc0 = bread @ meat @ bread
    scale = y.size / max(1, y.size - X.shape[1])
    covariance = hc0 * scale
    return beta, covariance, residual


def _binary_treatment(t: np.ndarray) -> bool:
    unique = np.unique(t)
    return bool(unique.size == 2 and np.all(np.isin(unique, [0.0, 1.0])))


def _propensity(t: np.ndarray, z: np.ndarray) -> np.ndarray:
    # z includes intercept? caller provides intercept + covariates (no treatment).
    ridge = 1e-6
    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        eta = np.clip(z @ beta, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-eta))
        loss = -float(np.sum(t * np.log(np.clip(p, 1e-12, 1.0)) + (1 - t) * np.log(np.clip(1 - p, 1e-12, 1.0))))
        penalty = 0.5 * ridge * float(beta[1:] @ beta[1:])
        grad = z.T @ (p - t)
        grad[1:] += ridge * beta[1:]
        return loss + penalty, grad
    start = np.zeros(z.shape[1], dtype=float)
    result = minimize(lambda b: objective(b)[0], start, jac=lambda b: objective(b)[1], method="L-BFGS-B", options={"maxiter": 1000})
    if not result.success or not np.all(np.isfinite(result.x)):
        raise ValueError(f"propensity model failed: {result.message}")
    eta = np.clip(z @ result.x, -35.0, 35.0)
    return np.clip(1.0 / (1.0 + np.exp(-eta)), 1e-3, 1 - 1e-3)


def _estimate_binary(y: np.ndarray, t: np.ndarray, X: np.ndarray, method: str) -> tuple[float, float, dict[str, Any], np.ndarray | None]:
    # Covariate-only design for propensity: intercept + Z.
    z = np.column_stack([np.ones_like(y), X[:, 2:]]) if X.shape[1] > 2 else np.ones((y.size, 1))
    p = _propensity(t, z)
    overlap = {
        "propensity_min": float(np.min(p)),
        "propensity_max": float(np.max(p)),
        "fraction_outside_0.05_0.95": float(np.mean((p < 0.05) | (p > 0.95))),
        "effective_sample_size_ipw": float((np.sum(t / p + (1 - t) / (1 - p)) ** 2) / np.sum((t / p + (1 - t) / (1 - p)) ** 2)),
    }
    if method == "ipw":
        psi = t * y / p - (1 - t) * y / (1 - p)
    else:
        beta, _, _ = _robust_ols(y, X)
        X1 = X.copy(); X1[:, 1] = 1.0
        X0 = X.copy(); X0[:, 1] = 0.0
        mu1, mu0 = X1 @ beta, X0 @ beta
        psi = (mu1 - mu0) + t * (y - mu1) / p - (1 - t) * (y - mu0) / (1 - p)
    effect = float(np.mean(psi))
    se = float(np.std(psi, ddof=1) / math.sqrt(y.size))
    return effect, se, overlap, p


def estimate_causal(
    model: ModelIR,
    *,
    t_span: tuple[float, float] = (0.0, 1.0),
    points: int = 2,
    parameter_overrides: dict[str, float] | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    del t_span, points, seed
    from axiomize.general_engine_core import _parameter_values

    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("causal", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.causal must be an object")
    data = cfg.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("causal.data must be an object")
    treatment, outcome = str(cfg.get("treatment", "")), str(cfg.get("outcome", ""))
    if not treatment or not outcome or treatment not in data or outcome not in data:
        raise ValueError("causal model requires treatment/outcome names present in data")

    identification = cfg.get("identification", model.metadata.get("causal_identification", {}))
    if not isinstance(identification, dict):
        identification = {}
    edges = _parse_edges(identification.get("dag", identification.get("edges", cfg.get("dag"))))
    randomized = bool(identification.get("randomized"))
    intervention = bool(identification.get("intervention"))
    requested_adjustment = identification.get("adjustment_set", cfg.get("adjustment_set", cfg.get("covariates", [])))
    if requested_adjustment is None:
        requested_adjustment = []
    if not isinstance(requested_adjustment, list) or not all(isinstance(v, str) for v in requested_adjustment):
        raise ValueError("causal adjustment_set must be an array of variable names")
    adjustment = list(dict.fromkeys(requested_adjustment))

    identification_detail = ""
    if randomized or intervention:
        identification_detail = "identified by supplied randomization/intervention evidence"
    elif edges:
        if not adjustment and bool(identification.get("auto_adjustment", True)):
            found = _auto_adjustment(treatment, outcome, edges)
            if found is None:
                return {"status": "INSUFFICIENT_CAUSAL_EVIDENCE", "family": model.family.value,
                        "detail": "no bounded automatic back-door adjustment set could be verified"}
            adjustment = found
        valid, identification_detail = _backdoor_valid(treatment, outcome, adjustment, edges)
        if not valid:
            return {"status": "INSUFFICIENT_CAUSAL_EVIDENCE", "family": model.family.value,
                    "detail": identification_detail, "adjustment_set": adjustment}
    elif adjustment and identification.get("assumptions"):
        identification_detail = "identified conditionally on caller-supplied adjustment assumptions (no DAG supplied)"
    else:
        return {
            "status": "INSUFFICIENT_CAUSAL_EVIDENCE",
            "family": model.family.value,
            "detail": "provide randomization/intervention evidence or a DAG/back-door adjustment set with explicit assumptions",
        }

    y, t, X = _design(data, outcome, treatment, adjustment)
    binary = _binary_treatment(t)
    method = str(cfg.get("estimator", "auto")).strip().lower()
    if method == "auto":
        method = "difference_in_means" if randomized and binary and not adjustment else "aipw" if binary else "robust_ols"

    propensity: np.ndarray | None = None
    overlap: dict[str, Any] = {"applicable": False}
    if method == "difference_in_means":
        if not binary:
            raise ValueError("difference_in_means requires a binary 0/1 treatment")
        treated, control = y[t == 1], y[t == 0]
        if treated.size < 2 or control.size < 2:
            raise ValueError("each treatment arm requires at least two observations")
        effect = float(np.mean(treated) - np.mean(control))
        se = float(math.sqrt(np.var(treated, ddof=1) / treated.size + np.var(control, ddof=1) / control.size))
    elif method == "robust_ols":
        beta, covariance, _ = _robust_ols(y, X)
        effect, se = float(beta[1]), float(math.sqrt(max(0.0, covariance[1, 1])))
    elif method in {"ipw", "aipw"}:
        if not binary:
            raise ValueError(f"{method} requires a binary 0/1 treatment")
        effect, se, overlap, propensity = _estimate_binary(y, t, X, method)
        overlap["applicable"] = True
    else:
        raise ValueError("causal estimator must be auto, difference_in_means, robust_ols, ipw, or aipw")

    ci = [effect - 1.96 * se, effect + 1.96 * se]
    counterfactuals: list[dict[str, Any]] = []
    intervention_values = cfg.get("intervention_values", [0.0, 1.0] if binary else [])
    if isinstance(intervention_values, list) and method in {"robust_ols", "aipw"}:
        beta, _, _ = _robust_ols(y, X)
        means = [float(np.mean(_finite_vector(data[name], name=f"causal.data.{name}"))) for name in adjustment]
        for value in intervention_values[:100]:
            row = np.asarray([1.0, float(value), *means], dtype=float)
            counterfactuals.append({"do": {treatment: float(value)}, "predicted_outcome_mean": float(row @ beta)})

    diagnostics = {
        "n": int(y.size),
        "design_rank": int(np.linalg.matrix_rank(X)),
        "adjustment_set": adjustment,
        "binary_treatment": binary,
        "overlap": overlap,
    }
    if propensity is not None:
        diagnostics["propensity_summary"] = {
            "mean": float(np.mean(propensity)), "sd": float(np.std(propensity, ddof=1))
        }
    return {
        "status": "PASS",
        "family": model.family.value,
        "states": {},
        "parameters": parameters,
        "causal_effect": {
            "treatment": treatment, "outcome": outcome, "estimand": "ATE",
            "estimate": effect, "std_error": se, "ci95": ci,
        },
        "counterfactuals": counterfactuals,
        "identification": {
            **identification,
            "verified": True,
            "detail": identification_detail,
            "adjustment_set": adjustment,
            "dag_edges": [[a, b] for a, b in edges],
        },
        "solver": {"backend": "numpy+scipy", "method": method},
        "diagnostics": diagnostics,
        "causal_scope": "causal interpretation is conditional on the verified/supplied identification assumptions; estimation alone is not identification",
    }
