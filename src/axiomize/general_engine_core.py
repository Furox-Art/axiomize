"""General scientific model planning, execution, validation and diagnostics.

A language model may propose a :class:`~axiomize.model_ir.ModelIR`, but
numerical execution and scientific checks happen here using explicit equations,
constraints and user-consent flags. Unsupported model families are reported as
such instead of being silently replaced by a reference SIR/logistic model.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
import platform
from typing import Any, Callable

import numpy as np

from axiomize.model_ir import (
    CURRENT_SCHEMA_VERSION,
    ConstraintSpec,
    ModelFamily,
    ModelIR,
    ProvenanceEvent,
)

_ALLOWED_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "Abs", "Min", "Max", "Piecewise", "Heaviside",
}


class UnsupportedModelExecution(NotImplementedError):
    """Raised only when a valid IR has no native generic executor yet."""


class ScientificConstraintFailure(ValueError):
    """Raised when caller explicitly requests fail-fast scientific validation."""


def _module_present(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def infer_domain(text: str) -> dict[str, Any]:
    """Conservative deterministic domain hinting for provider-independent use."""
    lower = str(text).lower()
    lexicon = {
        "physics": ("force", "energy", "momentum", "oscillat", "quantum", "field", "fluid", "heat"),
        "chemistry": ("reaction", "concentration", "molecule", "catal", "ph ", "molar", "kinetic"),
        "biology": ("cell", "gene", "protein", "population", "organism", "enzyme", "growth"),
        "epidemiology": ("epidem", "infect", "suscept", "disease", "transmission", "incidence"),
        "engineering": ("controller", "control", "sensor", "actuator", "circuit", "mechanical", "system"),
        "ecology": ("ecosystem", "species", "predator", "prey", "habitat", "ecolog"),
        "economics": ("market", "demand", "price", "utility", "econom", "competition"),
        "finance": ("portfolio", "return", "volatility", "option", "risk", "asset"),
    }
    scored: list[tuple[int, str, list[str]]] = []
    for domain, words in lexicon.items():
        hits = [w for w in words if w in lower]
        if hits:
            scored.append((len(hits), domain, hits))
    if not scored:
        return {"domain": "general", "confidence": "low", "matched_terms": []}
    scored.sort(reverse=True)
    score, domain, hits = scored[0]
    return {
        "domain": domain,
        "confidence": "medium" if score == 1 else "strong",
        "matched_terms": hits,
    }


def recommend_model_families(*, domain: str = "general", signals: list[str] | None = None,
                             idea: str = "") -> list[dict[str, Any]]:
    """Rank 2-3 candidate model families without inventing equations."""
    signals_l = {str(v).strip().lower().replace("-", "_") for v in (signals or [])}
    text = idea.lower()
    ranked: list[tuple[int, ModelFamily, str]] = []

    def add(score: int, family: ModelFamily, reason: str) -> None:
        ranked.append((score, family, reason))

    if {"spatial", "diffusion", "field"} & signals_l or any(w in text for w in ("spatial", "diffusion", "field")):
        add(100, ModelFamily.PDE, "spatial/field dynamics signal")
    if {"stochastic", "noise", "random"} & signals_l or any(w in text for w in ("noise", "random", "stochastic")):
        add(95, ModelFamily.STOCHASTIC, "stochastic/noise signal")
    if {"optimization", "optimal", "decision"} & signals_l or any(w in text for w in ("optimiz", "optimal", "minimize", "maximize")):
        add(95, ModelFamily.OPTIMIZATION, "optimization objective signal")
    if {"network", "graph"} & signals_l or any(w in text for w in ("network", "graph", "contact")):
        add(90, ModelFamily.NETWORK, "network/graph structure signal")
    if {"causal", "intervention", "counterfactual"} & signals_l or any(w in text for w in ("causal", "intervention", "counterfactual")):
        add(90, ModelFamily.CAUSAL, "causal/intervention question")
    if {"control", "controller"} & signals_l or any(w in text for w in ("controller", "control system", "feedback")):
        add(90, ModelFamily.CONTROL, "feedback/control signal")
    if {"agent", "individual_based"} & signals_l or "agent-based" in text:
        add(90, ModelFamily.AGENT_BASED, "individual/agent behavior signal")
    if {"event", "queue"} & signals_l or any(w in text for w in ("queue", "event-driven", "arrival")):
        add(85, ModelFamily.DISCRETE_EVENT, "event/queue signal")
    if {"bayesian", "posterior"} & signals_l or any(w in text for w in ("bayesian", "posterior", "prior")):
        add(85, ModelFamily.BAYESIAN, "Bayesian inference signal")
    if {"algebraic", "equilibrium", "steady_state"} & signals_l or "equilibrium" in text:
        add(75, ModelFamily.ALGEBRAIC, "equilibrium/algebraic relation signal")

    domain_defaults = {
        "physics": [(ModelFamily.ODE, "continuous-time dynamics"), (ModelFamily.PDE, "spatial continuum alternative")],
        "chemistry": [(ModelFamily.ODE, "reaction kinetics"), (ModelFamily.STOCHASTIC, "molecular-count alternative")],
        "biology": [(ModelFamily.ODE, "population/state dynamics"), (ModelFamily.AGENT_BASED, "individual heterogeneity alternative")],
        "epidemiology": [(ModelFamily.ODE, "compartment dynamics"), (ModelFamily.NETWORK, "contact-structure alternative")],
        "engineering": [(ModelFamily.CONTROL, "feedback dynamics"), (ModelFamily.ODE, "plant dynamics")],
        "ecology": [(ModelFamily.ODE, "population interactions"), (ModelFamily.STOCHASTIC, "environmental variability")],
        "economics": [(ModelFamily.OPTIMIZATION, "decision/equilibrium model"), (ModelFamily.CAUSAL, "policy/intervention alternative")],
        "finance": [(ModelFamily.STOCHASTIC, "stochastic price/risk dynamics"), (ModelFamily.OPTIMIZATION, "portfolio/decision alternative")],
        "general": [(ModelFamily.ODE, "generic dynamic-system candidate"), (ModelFamily.ALGEBRAIC, "static/equilibrium candidate")],
    }
    for index, (family, reason) in enumerate(domain_defaults.get(domain, domain_defaults["general"])):
        add(60 - index, family, reason)

    best: dict[ModelFamily, tuple[int, str]] = {}
    for score, family, reason in ranked:
        if family not in best or score > best[family][0]:
            best[family] = (score, reason)
    ordered = sorted(best.items(), key=lambda item: item[1][0], reverse=True)[:3]
    return [
        {"rank": i + 1, "family": family.value, "reason": reason, "score": score}
        for i, (family, (score, reason)) in enumerate(ordered)
    ]


def select_solver(model: ModelIR) -> dict[str, Any]:
    """Select a backend/method and explicit fallbacks from model structure."""
    if model.solver.backend != "auto" or model.solver.method != "auto":
        return {
            "backend": model.solver.backend,
            "method": model.solver.method,
            "fallbacks": list(model.solver.fallbacks),
            "reason": "explicit solver configuration",
        }

    stiff = bool(model.metadata.get("stiff", False))
    convex = bool(model.metadata.get("convex", False))
    mapping: dict[ModelFamily, tuple[str, str, list[str], str]] = {
        ModelFamily.ODE: ("scipy", "Radau" if stiff else "DOP853",
                          ["BDF", "RK45"] if stiff else ["RK45", "Radau", "BDF"],
                          "stiff ODE signal" if stiff else "high-accuracy non-stiff ODE default"),
        ModelFamily.STOCHASTIC: ("builtin", "euler_maruyama", ["scipy"], "generic SDE integration"),
        ModelFamily.ALGEBRAIC: ("sympy", "nsolve", ["scipy.root"], "symbolic algebraic system"),
        ModelFamily.OPTIMIZATION: (
            "cvxpy" if convex and _module_present("cvxpy") else "scipy",
            "CLARABEL" if convex and _module_present("cvxpy") else "SLSQP",
            ["casadi-ipopt", "scipy-trust-constr"],
            "convex optimization" if convex else "generic constrained nonlinear optimization",
        ),
        ModelFamily.PDE: ("fenics" if _module_present("fenics") else "scipy",
                          "finite_element" if _module_present("fenics") else "method_of_lines",
                          ["finite_difference"], "PDE backend availability"),
        ModelFamily.DAE: ("casadi", "idas", ["ipopt"], "differential-algebraic system"),
        ModelFamily.CONTROL: ("control", "state_space", ["scipy"], "control-system backend"),
        ModelFamily.NETWORK: ("networkx", "graph_dynamics", ["scipy"], "network-structured model"),
        ModelFamily.BAYESIAN: (
            "pymc" if _module_present("pymc") else "builtin",
            "nuts" if _module_present("pymc") else "mh",
            ["builtin-mh"], "posterior inference backend availability"),
        ModelFamily.AGENT_BASED: ("builtin", "agent_loop", [], "agent update rules"),
        ModelFamily.DISCRETE_EVENT: ("builtin", "event_queue", [], "event-scheduled dynamics"),
        ModelFamily.HYBRID: ("builtin", "hybrid_event_ode", ["scipy"], "continuous dynamics plus events"),
        ModelFamily.CAUSAL: ("statsmodels", "causal_guard", [], "causal estimation requires explicit identification assumptions"),
    }
    backend, method, fallbacks, reason = mapping[model.family]
    return {"backend": backend, "method": method, "fallbacks": fallbacks, "reason": reason}


def estimate_compute(model: ModelIR, *, action: str = "simulate", points: int = 1000,
                     samples: int = 1) -> dict[str, Any]:
    """Return a coarse, auditable compute estimate before expensive work."""
    family_factor = {
        ModelFamily.ALGEBRAIC: 1, ModelFamily.ODE: 2, ModelFamily.STOCHASTIC: 5,
        ModelFamily.OPTIMIZATION: 5, ModelFamily.CONTROL: 2, ModelFamily.NETWORK: 5,
        ModelFamily.PDE: 30, ModelFamily.DAE: 15, ModelFamily.BAYESIAN: 50,
        ModelFamily.AGENT_BASED: 20, ModelFamily.DISCRETE_EVENT: 10,
        ModelFamily.HYBRID: 25, ModelFamily.CAUSAL: 5,
    }[model.family]
    action_factor = {
        "solve": 1, "simulate": 1, "validate": 2, "fit": 12,
        "uncertainty": 20, "parameter_scan": 25, "discovery": 30,
        "experiment_design": 15,
    }.get(action, 5)
    evals = max(1, int(points)) * max(1, int(samples)) * family_factor * action_factor
    level = "low" if evals < 50_000 else "medium" if evals < 2_000_000 else "high"
    estimated_memory_mb = max(1.0, len(model.variables) * max(1, points) * 8 / 1_000_000 * max(2, samples))
    guarded = action in {"uncertainty", "parameter_scan", "discovery", "experiment_design"}
    return {
        "action": action,
        "level": level,
        "estimated_model_evaluations": int(evals),
        "estimated_memory_mb": round(float(estimated_memory_mb), 2),
        "requires_user_approval": level == "high" or guarded,
        "reason": "high-cost or multiplicative scientific work requires explicit consent"
        if level == "high" or guarded else "bounded local deterministic work",
    }


def build_execution_plan(model: ModelIR, *, action: str = "simulate", points: int = 1000,
                         samples: int = 1) -> dict[str, Any]:
    solver = select_solver(model)
    cost = estimate_compute(model, action=action, points=points, samples=samples)
    stages = [
        "schema_and_structure_validation", "unit_and_dimension_declaration_check",
        "scientific_constraint_check", "solver_selection", action,
        "numerical_diagnostics", "residual_or_invariant_checks", "provenance_record",
    ]
    if action == "fit":
        stages.extend(["identifiability_check", "residual_diagnostics", "model_selection_scores"])
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "model": model.name,
        "family": model.family.value,
        "solver": solver,
        "cost": cost,
        "stages": stages,
        "approval_required": cost["requires_user_approval"],
    }


def _validate_expression_syntax(expression: str, allowed_names: set[str]) -> None:
    tree = ast.parse(expression, mode="eval")
    allowed_nodes = (
        ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd,
        ast.Call,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"unsupported expression syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in allowed_names and node.id not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"unknown symbol in expression: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
                raise ValueError("only approved mathematical functions may be called")


def _sympy_expression(expression: str, symbols: dict[str, Any]) -> Any:
    import sympy as sp

    _validate_expression_syntax(expression, set(symbols))
    local_dict = dict(symbols)
    for name in _ALLOWED_FUNCTIONS:
        if hasattr(sp, name):
            local_dict[name] = getattr(sp, name)
    return sp.sympify(expression, locals=local_dict)


def _parameter_values(model: ModelIR, overrides: dict[str, float] | None = None) -> dict[str, float]:
    values: dict[str, float] = {}
    overrides = dict(overrides or {})
    for p in model.parameters:
        if p.name in overrides:
            value = float(overrides[p.name])
        elif p.value is not None:
            value = float(p.value)
        else:
            raise ValueError(f"parameter {p.name!r} has no value")
        if p.bounds is not None:
            low, high = p.bounds
            if low is not None and value < low:
                raise ValueError(f"parameter {p.name}={value} below lower bound {low}")
            if high is not None and value > high:
                raise ValueError(f"parameter {p.name}={value} above upper bound {high}")
        values[p.name] = value
    unknown = sorted(set(overrides) - {p.name for p in model.parameters})
    if unknown:
        raise ValueError(f"unknown parameter overrides: {unknown}")
    return values


def _compile_ode(model: ModelIR, parameter_values: dict[str, float]) -> tuple[list[str], Callable[..., Any]]:
    import sympy as sp

    state_vars = [v for v in model.variables if v.role == "state"]
    names = [v.name for v in state_vars]
    pnames = [p.name for p in model.parameters]
    symbols = {name: sp.Symbol(name, real=True) for name in names + pnames + [model.independent_variable]}
    by_target = {eq.target: eq for eq in model.equations if eq.kind == "derivative"}
    expressions = [_sympy_expression(by_target[name].expression, symbols) for name in names]
    args = [symbols[model.independent_variable], *[symbols[n] for n in names], *[symbols[p] for p in pnames]]
    compiled = sp.lambdify(args, expressions, modules=["numpy", "math"])
    pvals = [float(parameter_values[p]) for p in pnames]

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        out = compiled(float(t), *[float(v) for v in y], *pvals)
        return np.asarray(out, dtype=float).reshape(len(names))

    return names, rhs


def simulate_model(model: ModelIR, *, t_span: tuple[float, float] = (0.0, 1.0),
                   points: int = 200, parameter_overrides: dict[str, float] | None = None,
                   seed: int = 0, approve_heavy: bool = False) -> dict[str, Any]:
    """Execute a generic IR for natively supported families."""
    structure = model.validate_structure()
    if any(c["status"] == "FAIL" for c in structure):
        return {"status": "FAIL", "stage": "structure", "checks": structure}
    cost = estimate_compute(model, action="simulate", points=points)
    if cost["requires_user_approval"] and not approve_heavy:
        return {
            "status": "APPROVAL_REQUIRED", "cost": cost,
            "plan": build_execution_plan(model, action="simulate", points=points),
        }
    if model.family == ModelFamily.ODE:
        return _simulate_ode(model, t_span=t_span, points=points,
                             parameter_overrides=parameter_overrides)
    if model.family == ModelFamily.STOCHASTIC:
        return _simulate_sde(model, t_span=t_span, points=points,
                             parameter_overrides=parameter_overrides, seed=seed)
    if model.family == ModelFamily.ALGEBRAIC:
        return _solve_algebraic(model, parameter_overrides=parameter_overrides)
    return {
        "status": "TOOL_ROUTE_REQUIRED",
        "family": model.family.value,
        "solver": select_solver(model),
        "detail": "IR is valid and routed, but this family requires its specialized adapter rather than a silent fallback model",
    }


def _simulate_ode(model: ModelIR, *, t_span: tuple[float, float], points: int,
                  parameter_overrides: dict[str, float] | None) -> dict[str, Any]:
    from scipy.integrate import solve_ivp

    pvals = _parameter_values(model, parameter_overrides)
    names, rhs = _compile_ode(model, pvals)
    by_name = {v.name: v for v in model.variables}
    y0 = []
    for name in names:
        initial = by_name[name].initial
        if initial is None:
            raise ValueError(f"state {name!r} needs an initial value")
        y0.append(float(initial))
    t0, t1 = map(float, t_span)
    if not math.isfinite(t0) or not math.isfinite(t1) or t1 <= t0:
        raise ValueError("t_span must be finite and increasing")
    t_eval = np.linspace(t0, t1, max(2, int(points)))
    selected = select_solver(model)
    methods = [selected["method"], *selected.get("fallbacks", [])]
    scipy_methods = [m for m in methods if m in {"RK23", "RK45", "DOP853", "Radau", "BDF", "LSODA"}]
    attempts: list[dict[str, Any]] = []
    solution = None
    for method in scipy_methods or ["DOP853"]:
        try:
            sol = solve_ivp(rhs, (t0, t1), np.asarray(y0, dtype=float), t_eval=t_eval,
                            method=method, rtol=model.solver.rtol, atol=model.solver.atol)
            attempts.append({"method": method, "success": bool(sol.success), "message": str(sol.message)})
            if sol.success and np.all(np.isfinite(sol.y)):
                solution = sol
                break
        except Exception as exc:
            attempts.append({"method": method, "success": False, "message": f"{type(exc).__name__}: {exc}"})
    if solution is None:
        return {"status": "FAIL", "stage": "solve", "solver_attempts": attempts}

    states = {name: solution.y[i].tolist() for i, name in enumerate(names)}
    result = {
        "status": "PASS",
        "family": model.family.value,
        "time": solution.t.tolist(),
        "states": states,
        "parameters": pvals,
        "solver": {"backend": "scipy", "method": attempts[-1]["method"], "attempts": attempts},
        "diagnostics": {
            "nfev": int(solution.nfev),
            "njev": None if solution.njev is None else int(solution.njev),
            "finite": bool(np.all(np.isfinite(solution.y))),
        },
    }
    result["validation"] = validate_model(model, result=result)
    result["status"] = "PASS" if result["validation"]["status"] != "FAIL" else "FAIL"
    return result


def _simulate_sde(model: ModelIR, *, t_span: tuple[float, float], points: int,
                  parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    pvals = _parameter_values(model, parameter_overrides)
    names, drift = _compile_ode(model, pvals)
    by_name = {v.name: v for v in model.variables}
    y = np.zeros((len(names), max(2, int(points))), dtype=float)
    y[:, 0] = [float(by_name[n].initial) if by_name[n].initial is not None else np.nan for n in names]
    if not np.all(np.isfinite(y[:, 0])):
        raise ValueError("all stochastic state variables need finite initial values")
    t = np.linspace(float(t_span[0]), float(t_span[1]), y.shape[1])
    if t[-1] <= t[0]:
        raise ValueError("t_span must be increasing")
    dt = np.diff(t)
    diffusion = model.metadata.get("diffusion", {})
    if not isinstance(diffusion, dict):
        raise ValueError("stochastic metadata.diffusion must be an object mapping state -> sigma")
    sigma = np.asarray([float(diffusion.get(name, 0.0)) for name in names], dtype=float)
    rng = np.random.default_rng(seed)
    for i, step in enumerate(dt, start=1):
        dW = rng.normal(size=len(names)) * math.sqrt(step)
        y[:, i] = y[:, i - 1] + drift(t[i - 1], y[:, i - 1]) * step + sigma * dW
    result = {
        "status": "PASS", "family": model.family.value, "time": t.tolist(),
        "states": {name: y[j].tolist() for j, name in enumerate(names)},
        "parameters": pvals,
        "solver": {"backend": "builtin", "method": "euler_maruyama", "seed": int(seed)},
        "diagnostics": {"finite": bool(np.all(np.isfinite(y)))},
    }
    result["validation"] = validate_model(model, result=result)
    result["status"] = "PASS" if result["validation"]["status"] != "FAIL" else "FAIL"
    return result


def _solve_algebraic(model: ModelIR, *, parameter_overrides: dict[str, float] | None) -> dict[str, Any]:
    import sympy as sp

    pvals = _parameter_values(model, parameter_overrides)
    unknowns = [v for v in model.variables if v.role in {"state", "latent", "output"}]
    symbols = {name: sp.Symbol(name, real=True) for name in [v.name for v in unknowns] + [p.name for p in model.parameters]}
    equations = []
    for eq in model.equations:
        expr = _sympy_expression(eq.expression, symbols)
        if eq.kind == "residual" or not eq.target:
            equations.append(expr)
        else:
            equations.append(symbols[eq.target] - expr)
    equations = [e.subs({symbols[k]: v for k, v in pvals.items()}) for e in equations]
    guesses = [float(v.initial if v.initial is not None else 1.0) for v in unknowns]
    roots = sp.nsolve(equations, [symbols[v.name] for v in unknowns], guesses)
    values = np.asarray(roots, dtype=float).reshape(-1)
    state = {v.name: float(values[i]) for i, v in enumerate(unknowns)}
    result = {
        "status": "PASS", "family": model.family.value, "states": state,
        "parameters": pvals, "solver": {"backend": "sympy", "method": "nsolve"},
    }
    result["validation"] = validate_model(model, result=result)
    result["status"] = "PASS" if result["validation"]["status"] != "FAIL" else "FAIL"
    return result


def _constraint_context(model: ModelIR, result: dict[str, Any] | None) -> list[dict[str, float]]:
    result_params = result.get("parameters") if isinstance(result, dict) else None
    pvals = _parameter_values(model, result_params if isinstance(result_params, dict) else None)
    contexts: list[dict[str, float]] = []
    if result and isinstance(result.get("time"), list) and isinstance(result.get("states"), dict):
        times = result["time"]
        states = result["states"]
        for i, t in enumerate(times):
            row = {model.independent_variable: float(t), **pvals}
            for name, values in states.items():
                row[name] = float(values[i])
            contexts.append(row)
        return contexts
    if result and isinstance(result.get("states"), dict):
        contexts.append({**pvals, **{k: float(v) for k, v in result["states"].items()}})
        return contexts
    row = {**pvals}
    for variable in model.variables:
        if variable.initial is not None:
            row[variable.name] = float(variable.initial)
    contexts.append(row)
    return contexts


def _evaluate_constraint(constraint: ConstraintSpec, contexts: list[dict[str, float]]) -> dict[str, Any]:
    import sympy as sp

    names = sorted({name for row in contexts for name in row})
    symbols = {name: sp.Symbol(name, real=True) for name in names}
    expr = _sympy_expression(constraint.expression, symbols)
    func = sp.lambdify([symbols[n] for n in names], expr, modules=["numpy", "math"])
    values = np.asarray([float(func(*[row.get(n, np.nan) for n in names])) for row in contexts], dtype=float)
    if not np.all(np.isfinite(values)):
        ok = False
        detail = "constraint produced non-finite values"
    elif constraint.relation == "ge":
        margin = values - constraint.threshold
        ok = bool(np.min(margin) >= -constraint.tolerance)
        detail = f"min_margin={float(np.min(margin)):.6g}"
    elif constraint.relation == "le":
        margin = constraint.threshold - values
        ok = bool(np.min(margin) >= -constraint.tolerance)
        detail = f"min_margin={float(np.min(margin)):.6g}"
    elif constraint.relation == "eq":
        error = np.abs(values - constraint.threshold)
        ok = bool(np.max(error) <= constraint.tolerance)
        detail = f"max_abs_error={float(np.max(error)):.6g}"
    elif constraint.relation == "between":
        if constraint.upper is None:
            raise ValueError(f"constraint {constraint.name!r} relation='between' requires upper")
        low_margin = values - constraint.threshold
        high_margin = constraint.upper - values
        ok = bool(min(float(np.min(low_margin)), float(np.min(high_margin))) >= -constraint.tolerance)
        detail = f"range=[{float(np.min(values)):.6g}, {float(np.max(values)):.6g}]"
    else:
        raise ValueError(f"unsupported constraint relation: {constraint.relation}")
    return {
        "name": constraint.name, "status": "PASS" if ok else "FAIL",
        "relation": constraint.relation, "threshold": constraint.threshold,
        "upper": constraint.upper, "tolerance": constraint.tolerance,
        "severity": constraint.severity, "scientific_basis": constraint.scientific_basis,
        "detail": detail,
    }


def validate_model(model: ModelIR, *, result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run visible structural, unit, scientific and causal checks."""
    checks = list(model.validate_structure())
    try:
        from axiomize.validation.dimensions import dimension_of

        unit_specs = [(f"variable_unit:{v.name}", v.unit) for v in model.variables]
        unit_specs += [(f"parameter_unit:{p.name}", p.unit) for p in model.parameters]
        unit_specs.append(("independent_unit", model.independent_unit))
        for name, unit in unit_specs:
            try:
                dimension_of(unit)
                checks.append({"name": name, "status": "PASS", "detail": unit})
            except Exception as exc:
                checks.append({"name": name, "status": "FAIL", "detail": str(exc)})
    except Exception as exc:
        checks.append({"name": "unit_engine", "status": "UNVERIFIED", "detail": str(exc)})

    scientific_checks: list[dict[str, Any]] = []
    if model.constraints:
        contexts = _constraint_context(model, result)
        for constraint in model.constraints:
            try:
                scientific_checks.append(_evaluate_constraint(constraint, contexts))
            except Exception as exc:
                scientific_checks.append({
                    "name": constraint.name, "status": "FAIL",
                    "severity": constraint.severity,
                    "scientific_basis": constraint.scientific_basis,
                    "detail": f"{type(exc).__name__}: {exc}",
                })

    causal = _causal_guard(model)
    if causal is not None:
        checks.append(causal)
    hard_fail = any(c["status"] == "FAIL" for c in checks)
    hard_fail = hard_fail or any(
        c["status"] == "FAIL" and c.get("severity", "error") == "error"
        for c in scientific_checks
    )
    failed_science = [c for c in scientific_checks if c["status"] == "FAIL"]
    return {
        "status": "FAIL" if hard_fail else "PASS",
        "checks": checks,
        "scientific_constraints": scientific_checks,
        "repair_requires_approval": bool(failed_science),
        "repair_proposal": _repair_proposal(model, failed_science) if failed_science else None,
    }


def _causal_guard(model: ModelIR) -> dict[str, Any] | None:
    wants_causal = model.family == ModelFamily.CAUSAL or bool(model.metadata.get("causal_claim"))
    if not wants_causal:
        return None
    evidence = model.metadata.get("causal_identification", {})
    if not isinstance(evidence, dict):
        evidence = {}
    supported = bool(evidence.get("intervention") or evidence.get("randomized") or evidence.get("identified_dag"))
    return {
        "name": "causal_identification",
        "status": "PASS" if supported else "UNVERIFIED",
        "detail": "causal identification evidence supplied" if supported else
        "causal conclusion is not identified from fit/correlation alone; provide an intervention, randomized design, or an identified DAG/assumption set",
    }


def _repair_proposal(model: ModelIR, failures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "action": "rebuild_or_refit_with_constraints",
        "requires_user_approval": True,
        "failed_constraints": [f["name"] for f in failures],
        "preserve_failed_model": True,
        "detail": "No repair has been applied. Approve explicitly before constraining/refitting the model.",
    }


def repair_model(model: ModelIR, *, approve: bool = False,
                 validation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepare a constrained-model revision without silently changing science."""
    validation = dict(validation) if isinstance(validation, dict) else validate_model(model)
    proposal = validation.get("repair_proposal")
    if not proposal:
        return {"status": "NO_REPAIR_NEEDED", "model": model.to_dict()}
    if not approve:
        return {"status": "APPROVAL_REQUIRED", "proposal": proposal, "model": model.to_dict()}
    revised = ModelIR.from_dict(model.to_dict())
    revised.metadata["constraint_rebuild_approved"] = True
    revised.provenance.append(ProvenanceEvent(
        action="constraint_rebuild_approved",
        detail={"failed_constraints": proposal["failed_constraints"]},
    ))
    return {
        "status": "REBUILD_REQUIRED", "model": revised.to_dict(),
        "preserved_original": model.to_dict(),
        "detail": "approval recorded; mechanism-specific rebuild/refit must honor the listed constraints",
    }


def residual_diagnostics(observed: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    residual = np.asarray(observed, dtype=float) - np.asarray(predicted, dtype=float)
    if residual.shape != np.asarray(observed).shape:
        raise ValueError("observed/predicted shape mismatch")
    if residual.size == 0:
        raise ValueError("residual diagnostics require observations")
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    mean = float(np.mean(residual))
    std = float(np.std(residual, ddof=1)) if residual.size > 1 else 0.0
    lag1 = 0.0
    if residual.size > 2 and std > 0:
        lag1 = float(np.corrcoef(residual[:-1], residual[1:])[0, 1])
        if not math.isfinite(lag1):
            lag1 = 0.0
    return {
        "rmse": rmse, "bias": mean, "std": std,
        "max_abs": float(np.max(np.abs(residual))),
        "lag1_autocorrelation": lag1,
        "systematic_error_warning": bool(abs(mean) > 0.25 * max(std, 1e-12) or abs(lag1) > 0.5),
    }


def fit_ode_model(model: ModelIR, *, time: list[float], observations: dict[str, list[float]],
                  approve_heavy: bool = False) -> dict[str, Any]:
    """Fit IR parameters marked ``fit=true`` using nonlinear least squares."""
    from scipy.optimize import least_squares

    if model.family != ModelFamily.ODE:
        return {
            "status": "TOOL_ROUTE_REQUIRED",
            "detail": "generic native fitting currently targets ODE IRs",
            "solver": select_solver(model),
        }
    fit_params = [p for p in model.parameters if p.fit]
    cost = estimate_compute(model, action="fit", points=len(time), samples=max(1, len(fit_params)))
    if cost["requires_user_approval"] and not approve_heavy:
        return {"status": "APPROVAL_REQUIRED", "cost": cost}
    t = np.asarray(time, dtype=float)
    if t.ndim != 1 or t.size < 3 or not np.all(np.diff(t) > 0):
        raise ValueError("time must be a strictly increasing 1D array with at least 3 points")
    if not fit_params:
        raise ValueError("mark at least one parameter with fit=true")
    observed = {k: np.asarray(v, dtype=float) for k, v in observations.items()}
    for name, values in observed.items():
        if values.shape != t.shape:
            raise ValueError(f"observations[{name}] length must match time")
    state_names = {v.name for v in model.variables if v.role == "state"}
    unknown_states = sorted(set(observed) - state_names)
    if unknown_states:
        raise ValueError(f"observations reference unknown states: {unknown_states}")

    x0, lower, upper = [], [], []
    for p in fit_params:
        if p.value is None:
            raise ValueError(f"fit parameter {p.name} needs an initial value")
        x0.append(float(p.value))
        lo, hi = p.bounds if p.bounds is not None else (None, None)
        lower.append(-np.inf if lo is None else float(lo))
        upper.append(np.inf if hi is None else float(hi))

    def predict(x: np.ndarray) -> dict[str, np.ndarray]:
        overrides = {p.name: float(x[i]) for i, p in enumerate(fit_params)}
        sim = _simulate_ode(model, t_span=(float(t[0]), float(t[-1])), points=len(t),
                            parameter_overrides=overrides)
        if sim["status"] not in {"PASS", "FAIL"} or "states" not in sim:
            raise RuntimeError("ODE simulation failed during fitting")
        sim_t = np.asarray(sim["time"], dtype=float)
        return {
            name: np.interp(t, sim_t, np.asarray(sim["states"][name], dtype=float))
            for name in observed
        }

    def residual_vector(x: np.ndarray) -> np.ndarray:
        pred = predict(x)
        return np.concatenate([observed[name] - pred[name] for name in sorted(observed)])

    result = least_squares(residual_vector, np.asarray(x0),
                           bounds=(np.asarray(lower), np.asarray(upper)))
    resid = residual_vector(result.x)
    n = int(resid.size)
    k = int(len(result.x))
    sse = float(np.sum(resid ** 2))
    sigma2 = sse / max(1, n - k)
    rank = int(np.linalg.matrix_rank(result.jac))
    identifiable = rank == k
    covariance = None
    stderr: dict[str, float | None] = {p.name: None for p in fit_params}
    if identifiable and n > k:
        try:
            cov = np.linalg.inv(result.jac.T @ result.jac) * sigma2
            covariance = cov.tolist()
            for i, p in enumerate(fit_params):
                stderr[p.name] = float(math.sqrt(max(0.0, cov[i, i])))
        except np.linalg.LinAlgError:
            identifiable = False
    fitted = {p.name: float(result.x[i]) for i, p in enumerate(fit_params)}
    pred = predict(result.x)
    per_state = {name: residual_diagnostics(observed[name], pred[name]) for name in sorted(observed)}
    aic = float(n * math.log(max(sse / max(n, 1), 1e-300)) + 2 * k)
    bic = float(n * math.log(max(sse / max(n, 1), 1e-300)) + k * math.log(max(n, 1)))
    return {
        "status": "PASS" if result.success else "FAIL",
        "success": bool(result.success), "message": str(result.message),
        "parameters": fitted, "stderr": stderr, "covariance": covariance,
        "identifiability": {"jacobian_rank": rank, "n_parameters": k, "identifiable": identifiable},
        "residual_diagnostics": per_state,
        "selection_scores": {"sse": sse, "aic": aic, "bic": bic, "n": n, "k": k},
        "cost": cost,
    }


def rank_model_fits(fits: dict[str, dict[str, Any]], *, criterion: str = "bic") -> dict[str, Any]:
    if criterion not in {"aic", "bic", "sse"}:
        raise ValueError("criterion must be aic, bic, or sse")
    rows = []
    for name, payload in fits.items():
        scores = payload.get("selection_scores", payload)
        if criterion in scores:
            rows.append((float(scores[criterion]), name, scores))
    rows.sort(key=lambda row: row[0])
    ranked = [
        {"rank": i + 1, "model": name, criterion: score, "scores": scores}
        for i, (score, name, scores) in enumerate(rows[:3])
    ]
    return {
        "criterion": criterion, "ranked": ranked,
        "winner": ranked[0]["model"] if ranked else None,
        "principle": "prefer the simplest model that retains predictive adequacy; information criteria penalize unnecessary complexity",
    }


def local_stability(model: ModelIR, *, state: dict[str, float],
                    parameter_overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Linearize an ODE around a supplied state and report eigenvalue stability."""
    import sympy as sp

    if model.family != ModelFamily.ODE:
        raise ValueError("local stability currently requires an ODE model")
    pvals = _parameter_values(model, parameter_overrides)
    names = [v.name for v in model.variables if v.role == "state"]
    pnames = [p.name for p in model.parameters]
    symbols = {name: sp.Symbol(name, real=True) for name in names + pnames + [model.independent_variable]}
    by_target = {e.target: e for e in model.equations if e.kind == "derivative"}
    vector = sp.Matrix([_sympy_expression(by_target[name].expression, symbols) for name in names])
    jac = vector.jacobian([symbols[name] for name in names])
    subs = {symbols[k]: float(v) for k, v in {**pvals, **state}.items() if k in symbols}
    matrix = np.asarray(jac.subs(subs), dtype=float)
    eig = np.linalg.eigvals(matrix)
    max_real = float(np.max(np.real(eig)))
    return {
        "jacobian": matrix.tolist(),
        "eigenvalues": [[float(np.real(v)), float(np.imag(v))] for v in eig],
        "max_real_part": max_real,
        "classification": "stable" if max_real < 0 else "unstable" if max_real > 0 else "marginal",
    }


def validity_scan(model: ModelIR, *, parameter: str, values: list[float],
                  t_span: tuple[float, float], points: int = 200,
                  approve_heavy: bool = False) -> dict[str, Any]:
    cost = estimate_compute(model, action="parameter_scan", points=points, samples=len(values))
    if cost["requires_user_approval"] and not approve_heavy:
        return {"status": "APPROVAL_REQUIRED", "cost": cost}
    rows = []
    for value in values:
        out = simulate_model(model, t_span=t_span, points=points,
                             parameter_overrides={parameter: float(value)}, approve_heavy=True)
        validation = out.get("validation", {})
        rows.append({
            "value": float(value), "status": out.get("status"),
            "validation": validation.get("status"),
        })
    valid = [r["value"] for r in rows if r["status"] == "PASS" and r["validation"] == "PASS"]
    return {
        "status": "PASS", "parameter": parameter, "evaluations": rows,
        "valid_interval_observed": [min(valid), max(valid)] if valid else None,
        "cost": cost,
    }


def nondimensionalization_plan(model: ModelIR) -> dict[str, Any]:
    """Propose visible scale transformations; never applies them silently."""
    scales: dict[str, float] = {}
    for variable in model.variables:
        candidates = []
        if variable.initial is not None:
            candidates.append(abs(float(variable.initial)))
        if variable.bounds is not None:
            candidates.extend(
                abs(float(v)) for v in variable.bounds
                if v is not None and math.isfinite(float(v))
            )
        scales[variable.name] = max([v for v in candidates if v > 0] or [1.0])
    pscales = {
        p.name: abs(float(p.value)) if p.value not in (None, 0) else 1.0
        for p in model.parameters
    }
    ratio_values = list(scales.values()) + list(pscales.values())
    dynamic_range = max(ratio_values) / max(min(ratio_values), 1e-300) if ratio_values else 1.0
    return {
        "recommended": bool(dynamic_range > 1e6),
        "dynamic_range": float(dynamic_range),
        "variable_scales": scales, "parameter_scales": pscales,
        "transformation": {name: f"{name}_hat = {name} / {scale:g}" for name, scale in scales.items()},
        "applied": False,
        "detail": "scaling is a proposal; execution must display and record any applied transformation",
    }


def split_uncertainty(*, residual_std: float | None = None,
                      parameter_covariance: list[list[float]] | None = None) -> dict[str, Any]:
    epistemic = None
    if parameter_covariance is not None:
        cov = np.asarray(parameter_covariance, dtype=float)
        epistemic = float(math.sqrt(max(0.0, float(np.trace(cov)))))
    return {
        "aleatoric": {
            "estimate": None if residual_std is None else float(residual_std),
            "source": "measurement/process residual variability",
        },
        "epistemic": {
            "estimate": epistemic,
            "source": "parameter/model uncertainty proxy",
        },
        "note": "these components are reported separately; neither is collapsed into a single confidence number",
    }


def discover_sparse_dynamics(*, time: list[float], state: list[float],
                             degree: int = 2, threshold: float = 1e-4,
                             approve_heavy: bool = False) -> dict[str, Any]:
    """Small native SINDy-style candidate-equation discovery for one state."""
    t = np.asarray(time, dtype=float)
    x = np.asarray(state, dtype=float)
    if t.shape != x.shape or t.ndim != 1 or t.size < 5 or not np.all(np.diff(t) > 0):
        raise ValueError("time/state must be same-length increasing 1D arrays with at least 5 points")
    if degree < 1 or degree > 5:
        raise ValueError("degree must be between 1 and 5")
    mock = ModelIR(name="discovery", domain="general", family=ModelFamily.ODE,
                   variables=[], parameters=[], equations=[])
    cost = estimate_compute(mock, action="discovery", points=len(t), samples=degree)
    if cost["requires_user_approval"] and not approve_heavy:
        return {"status": "APPROVAL_REQUIRED", "cost": cost}
    dx = np.gradient(x, t)
    columns = [np.ones_like(x)] + [x ** power for power in range(1, degree + 1)]
    names = ["1"] + ["x" if p == 1 else f"x**{p}" for p in range(1, degree + 1)]
    theta = np.column_stack(columns)
    coef, *_ = np.linalg.lstsq(theta, dx, rcond=None)
    for _ in range(8):
        small = np.abs(coef) < threshold
        coef[small] = 0.0
        active = ~small
        if not np.any(active):
            break
        refit, *_ = np.linalg.lstsq(theta[:, active], dx, rcond=None)
        coef[active] = refit
    prediction = theta @ coef
    terms = [
        {"term": names[i], "coefficient": float(c)}
        for i, c in enumerate(coef) if abs(c) >= threshold
    ]
    return {
        "status": "PASS", "method": "sequential_thresholded_least_squares",
        "candidate_terms": terms,
        "rmse_derivative": float(np.sqrt(np.mean((dx - prediction) ** 2))),
        "scientific_status": "UNVERIFIED",
        "required_next_checks": [
            "dimensional_consistency", "domain_law_consistency",
            "out_of_sample_validation", "falsification",
        ],
        "cost": cost,
    }


def rank_experiment_times(model: ModelIR, *, parameter: str, candidate_times: list[float],
                          horizon: float, delta_fraction: float = 0.01,
                          approve_heavy: bool = False) -> dict[str, Any]:
    """Rank observation times by a finite-difference information proxy."""
    cost = estimate_compute(model, action="experiment_design", points=400,
                            samples=len(candidate_times) * 2)
    if cost["requires_user_approval"] and not approve_heavy:
        return {"status": "APPROVAL_REQUIRED", "cost": cost}
    p = next((p for p in model.parameters if p.name == parameter), None)
    if p is None or p.value is None:
        raise ValueError(f"parameter {parameter!r} needs a baseline value")
    delta = max(abs(float(p.value)) * delta_fraction, 1e-8)
    plus = simulate_model(model, t_span=(0.0, float(horizon)), points=400,
                          parameter_overrides={parameter: float(p.value) + delta}, approve_heavy=True)
    minus = simulate_model(model, t_span=(0.0, float(horizon)), points=400,
                           parameter_overrides={parameter: float(p.value) - delta}, approve_heavy=True)
    if "states" not in plus or "states" not in minus:
        return {"status": "FAIL", "detail": "simulation failed during experiment design"}
    t = np.asarray(plus["time"], dtype=float)
    rows = []
    for target_time in candidate_times:
        score = 0.0
        for state_name in plus["states"]:
            yp = float(np.interp(target_time, t, np.asarray(plus["states"][state_name])))
            ym = float(np.interp(target_time, t, np.asarray(minus["states"][state_name])))
            sensitivity = (yp - ym) / (2 * delta)
            score += sensitivity ** 2
        rows.append({"time": float(target_time), "information_proxy": float(score)})
    rows.sort(key=lambda row: row["information_proxy"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return {
        "status": "PASS", "parameter": parameter, "ranked_tests": rows,
        "metric": "sum_squared_local_sensitivity (Fisher-information proxy)",
        "cost": cost,
    }


def provenance_snapshot(model: ModelIR, *, seed: int | None = None,
                        data_hash: str | None = None) -> dict[str, Any]:
    import scipy
    import sympy

    versions = {
        "python": platform.python_version(), "numpy": np.__version__,
        "scipy": scipy.__version__, "sympy": sympy.__version__,
    }
    for module in ("z3", "cvxpy", "casadi", "statsmodels"):
        if _module_present(module):
            try:
                imported = __import__(module)
                versions[module] = str(getattr(imported, "__version__", "available"))
            except Exception:
                versions[module] = "available"
    return {
        "schema_version": model.schema_version, "model_name": model.name,
        "model_family": model.family.value, "solver": select_solver(model),
        "tool_versions": versions, "seed": seed, "data_hash": data_hash,
        "assumptions": list(model.assumptions),
    }


def export_model(model: ModelIR, *, format: str = "json") -> dict[str, Any]:
    """Export a portable model representation without filesystem side effects."""
    fmt = format.lower()
    payload = model.to_dict()
    if fmt == "json":
        return {"format": "json", "content": json.dumps(payload, indent=2, sort_keys=True)}
    if fmt == "python":
        content = (
            "# Generated by Axiomize from a versioned Model IR.\n"
            "import json\n"
            "from axiomize.model_ir import ModelIR\n"
            "from axiomize.general_engine import simulate_model\n\n"
            f"MODEL = json.loads({json.dumps(json.dumps(payload, sort_keys=True))})\n"
            "model = ModelIR.from_dict(MODEL)\n"
            "print(simulate_model(model))\n"
        )
        return {"format": "python", "content": content}
    if fmt in {"yaml", "yml"}:
        if not _module_present("yaml"):
            return {
                "status": "TOOL_UNAVAILABLE", "format": fmt,
                "detail": "PyYAML is not installed; JSON export remains fully portable",
            }
        import yaml
        return {"format": "yaml", "content": yaml.safe_dump(payload, sort_keys=False)}
    if fmt in {"sbml", "cellml"}:
        return {
            "status": "ADAPTER_REQUIRED", "format": fmt,
            "detail": "standards-compliant SBML/CellML export requires a dedicated schema adapter; Axiomize will not emit misleading pseudo-standard XML",
            "portable_ir": payload,
        }
    raise ValueError("format must be json, python, yaml, sbml, or cellml")
