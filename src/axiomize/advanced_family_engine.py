"""Native executors for advanced Model IR families.

The adapters in this module are deterministic, provider-independent and consume
only explicit Model IR + metadata contracts. They never invent a hidden
reference model. Expensive families are still gated by ``general_engine`` before
entry.
"""

from __future__ import annotations

import ast
import math
from typing import Any, Callable

import numpy as np

from axiomize.model_ir import ModelFamily, ModelIR

_ALLOWED_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "Abs", "Min", "Max", "Heaviside",
}


def _validate_expression(expression: str, allowed_names: set[str]) -> None:
    tree = ast.parse(str(expression), mode="eval")
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


def _compile_expression(expression: str, arg_names: list[str]) -> Callable[..., Any]:
    import sympy as sp

    symbols = {name: sp.Symbol(name, real=True) for name in arg_names}
    _validate_expression(expression, set(symbols))
    local_dict: dict[str, Any] = dict(symbols)
    for name in _ALLOWED_FUNCTIONS:
        if hasattr(sp, name):
            local_dict[name] = getattr(sp, name)
    expr = sp.sympify(expression, locals=local_dict)
    return sp.lambdify([symbols[name] for name in arg_names], expr, modules=["numpy", "math"])


def _parameter_values(model: ModelIR, overrides: dict[str, float] | None = None) -> dict[str, float]:
    overrides = dict(overrides or {})
    names = {p.name for p in model.parameters}
    unknown = sorted(set(overrides) - names)
    if unknown:
        raise ValueError(f"unknown parameter overrides: {unknown}")
    out: dict[str, float] = {}
    for parameter in model.parameters:
        if parameter.name in overrides:
            value = float(overrides[parameter.name])
        elif parameter.value is not None:
            value = float(parameter.value)
        else:
            raise ValueError(f"parameter {parameter.name!r} has no value")
        if parameter.bounds is not None:
            low, high = parameter.bounds
            if low is not None and value < float(low):
                raise ValueError(f"parameter {parameter.name}={value} below lower bound {low}")
            if high is not None and value > float(high):
                raise ValueError(f"parameter {parameter.name}={value} above upper bound {high}")
        out[parameter.name] = value
    return out


def _resolve_scalar(value: Any, parameters: dict[str, float], *, name: str) -> float:
    if isinstance(value, str):
        if value not in parameters:
            raise ValueError(f"{name} references unknown parameter {value!r}")
        return float(parameters[value])
    return float(value)


def _flatten_validation_proxy(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten entity/spatial axes so existing constraint checks remain pointwise."""
    states = result.get("states")
    times = result.get("time")
    if not isinstance(states, dict) or not isinstance(times, list) or not states:
        return result
    arrays: dict[str, np.ndarray] = {}
    width: int | None = None
    for name, values in states.items():
        arr = np.asarray(values, dtype=float)
        if arr.ndim == 1:
            arrays[name] = arr.reshape(-1, 1)
        elif arr.ndim == 2:
            arrays[name] = arr
        else:
            return result
        if arrays[name].shape[0] != len(times):
            return result
        if width is None:
            width = arrays[name].shape[1]
        elif arrays[name].shape[1] != width:
            return result
    if width is None or width == 1:
        return result
    proxy = dict(result)
    proxy["time"] = np.repeat(np.asarray(times, dtype=float), width).tolist()
    proxy["states"] = {name: arr.reshape(-1).tolist() for name, arr in arrays.items()}
    return proxy


def _finalize(model: ModelIR, result: dict[str, Any], validate_fn: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    if result.get("status") not in {"PASS", "FAIL"}:
        return result
    try:
        validation = validate_fn(model, result=_flatten_validation_proxy(result))
    except Exception as exc:
        result["status"] = "FAIL"
        result["validation"] = {
            "status": "FAIL",
            "checks": [{
                "name": "advanced_result_validation",
                "status": "FAIL",
                "detail": f"{type(exc).__name__}: {exc}",
            }],
            "scientific_constraints": [],
            "repair_requires_approval": False,
            "repair_proposal": None,
        }
        return result
    result["validation"] = validation
    if validation.get("status") == "FAIL":
        result["status"] = "FAIL"
    return result


def simulate_advanced_family(
    model: ModelIR,
    *,
    t_span: tuple[float, float],
    points: int,
    parameter_overrides: dict[str, float] | None,
    seed: int,
    validate_fn: Callable[..., dict[str, Any]],
    simulate_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Dispatch every advanced family to a real native executor."""
    dispatch = {
        ModelFamily.PDE: _simulate_pde,
        ModelFamily.DAE: _simulate_dae,
        ModelFamily.OPTIMIZATION: _solve_optimization,
        ModelFamily.CONTROL: _simulate_control,
        ModelFamily.NETWORK: _simulate_network,
        ModelFamily.BAYESIAN: _infer_bayesian,
        ModelFamily.AGENT_BASED: _simulate_agent_based,
        ModelFamily.DISCRETE_EVENT: _simulate_discrete_event,
        ModelFamily.HYBRID: _simulate_hybrid,
        ModelFamily.CAUSAL: _estimate_causal,
    }
    if model.family == ModelFamily.MULTIPHYSICS:
        result = _simulate_multiphysics(
            model,
            t_span=t_span,
            points=points,
            parameter_overrides=parameter_overrides,
            seed=seed,
            simulate_fn=simulate_fn,
        )
        return _finalize(model, result, validate_fn)
    executor = dispatch.get(model.family)
    if executor is None:
        return {
            "status": "TOOL_ROUTE_REQUIRED",
            "family": model.family.value,
            "detail": "no advanced native executor registered for this family",
        }
    result = executor(
        model,
        t_span=t_span,
        points=points,
        parameter_overrides=parameter_overrides,
        seed=seed,
    )
    return _finalize(model, result, validate_fn)


def _compile_local_vector_field(model: ModelIR, parameters: dict[str, float]) -> tuple[list[str], Callable[[float, np.ndarray], np.ndarray]]:
    states = [v for v in model.variables if v.role == "state"]
    names = [v.name for v in states]
    by_target = {e.target: e for e in model.equations if e.kind == "derivative"}
    missing = sorted(set(names) - set(by_target))
    if missing:
        raise ValueError(f"missing derivative equations for states: {missing}")
    pnames = [p.name for p in model.parameters]
    args = [model.independent_variable, *names, *pnames]
    functions = [_compile_expression(by_target[name].expression, args) for name in names]
    pvals = [parameters[name] for name in pnames]

    def rhs(t: float, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=float)
        out: list[np.ndarray] = []
        for function in functions:
            evaluated = np.asarray(function(float(t), *[values[j] for j in range(len(names))], *pvals), dtype=float)
            if evaluated.ndim == 0:
                evaluated = np.full(values.shape[1] if values.ndim == 2 else 1, float(evaluated))
            out.append(evaluated)
        return np.asarray(out, dtype=float)

    return names, rhs


def _boundary_spec(model: ModelIR, cfg: dict[str, Any], state: str) -> dict[str, Any]:
    raw = cfg.get("boundary_conditions", model.boundary_conditions)
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get(state), dict):
        return dict(raw[state])
    if "left" in raw or "right" in raw or "type" in raw:
        return dict(raw)
    return {}


def _simulate_pde(model: ModelIR, *, t_span: tuple[float, float], points: int,
                  parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del seed
    from scipy.integrate import solve_ivp

    cfg = model.metadata.get("pde", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.pde must be an object")
    parameters = _parameter_values(model, parameter_overrides)
    state_names, reaction = _compile_local_vector_field(model, parameters)
    nx = int(cfg.get("grid_points", 32))
    if nx < 5 or nx > 4096:
        raise ValueError("pde.grid_points must be between 5 and 4096")
    space_span = cfg.get("space_span", cfg.get("x_span", [0.0, 1.0]))
    if not isinstance(space_span, (list, tuple)) or len(space_span) != 2:
        raise ValueError("pde.space_span must be [start, stop]")
    x0, x1 = float(space_span[0]), float(space_span[1])
    if not math.isfinite(x0) or not math.isfinite(x1) or x1 <= x0:
        raise ValueError("pde.space_span must be finite and increasing")
    x = np.linspace(x0, x1, nx)
    dx = float(x[1] - x[0])
    t0, t1 = map(float, t_span)
    if t1 <= t0:
        raise ValueError("t_span must be increasing")
    t_eval = np.linspace(t0, t1, max(2, int(points)))
    by_name = {v.name: v for v in model.variables}
    profiles = cfg.get("initial_profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError("pde.initial_profiles must be an object")
    initial = np.zeros((len(state_names), nx), dtype=float)
    profile_args = [str(cfg.get("space_variable", "x")), *[p.name for p in model.parameters]]
    for index, name in enumerate(state_names):
        spec = profiles.get(name)
        if isinstance(spec, str):
            fn = _compile_expression(spec, profile_args)
            values = np.asarray(fn(x, *[parameters[p.name] for p in model.parameters]), dtype=float)
            if values.ndim == 0:
                values = np.full(nx, float(values))
            if values.shape != (nx,):
                raise ValueError(f"initial profile for {name!r} must evaluate to grid length {nx}")
            initial[index] = values
        elif isinstance(spec, list):
            values = np.asarray(spec, dtype=float)
            if values.shape != (nx,):
                raise ValueError(f"initial profile for {name!r} must have grid length {nx}")
            initial[index] = values
        else:
            value = by_name[name].initial
            if value is None:
                raise ValueError(f"PDE state {name!r} needs initial or metadata.pde.initial_profiles")
            initial[index] = float(value)

    diffusion_cfg = cfg.get("diffusion", {})
    advection_cfg = cfg.get("advection", {})
    if not isinstance(diffusion_cfg, (dict, int, float, str)):
        raise ValueError("pde.diffusion must be scalar, parameter name, or state mapping")
    if not isinstance(advection_cfg, (dict, int, float, str)):
        raise ValueError("pde.advection must be scalar, parameter name, or state mapping")

    boundary: dict[str, dict[str, Any]] = {}
    for index, name in enumerate(state_names):
        bc = _boundary_spec(model, cfg, name)
        boundary[name] = bc
        left = bc.get("left", {}) if isinstance(bc.get("left", {}), dict) else {}
        right = bc.get("right", {}) if isinstance(bc.get("right", {}), dict) else {}
        if str(left.get("type", "")).lower() == "dirichlet":
            initial[index, 0] = float(left.get("value", initial[index, 0]))
        if str(right.get("type", "")).lower() == "dirichlet":
            initial[index, -1] = float(right.get("value", initial[index, -1]))

    def coeff(config: Any, name: str, label: str) -> float:
        raw = config.get(name, 0.0) if isinstance(config, dict) else config
        return _resolve_scalar(raw, parameters, name=f"pde.{label}.{name}")

    def spatial_rhs(t: float, flat: np.ndarray) -> np.ndarray:
        values = np.asarray(flat, dtype=float).reshape(len(state_names), nx)
        deriv = reaction(t, values)
        for index, name in enumerate(state_names):
            u = values[index]
            bc = boundary[name]
            left = bc.get("left", {}) if isinstance(bc.get("left", {}), dict) else {}
            right = bc.get("right", {}) if isinstance(bc.get("right", {}), dict) else {}
            periodic = str(left.get("type", "")).lower() == "periodic" or str(right.get("type", "")).lower() == "periodic"
            diff = coeff(diffusion_cfg, name, "diffusion")
            adv = coeff(advection_cfg, name, "advection")
            if diff != 0.0:
                if periodic:
                    lap = (np.roll(u, -1) - 2.0 * u + np.roll(u, 1)) / (dx * dx)
                else:
                    lap = np.empty_like(u)
                    lap[1:-1] = (u[2:] - 2.0 * u[1:-1] + u[:-2]) / (dx * dx)
                    left_type = str(left.get("type", "neumann")).lower()
                    right_type = str(right.get("type", "neumann")).lower()
                    left_grad = float(left.get("value", 0.0))
                    right_grad = float(right.get("value", 0.0))
                    left_ghost = u[1] - 2.0 * dx * left_grad
                    right_ghost = u[-2] + 2.0 * dx * right_grad
                    lap[0] = (u[1] - 2.0 * u[0] + left_ghost) / (dx * dx)
                    lap[-1] = (right_ghost - 2.0 * u[-1] + u[-2]) / (dx * dx)
                    if left_type == "dirichlet":
                        lap[0] = 0.0
                    if right_type == "dirichlet":
                        lap[-1] = 0.0
                deriv[index] = deriv[index] + diff * lap
            if adv != 0.0:
                if periodic:
                    grad = (np.roll(u, -1) - np.roll(u, 1)) / (2.0 * dx)
                else:
                    grad = np.empty_like(u)
                    grad[1:-1] = (u[2:] - u[:-2]) / (2.0 * dx)
                    grad[0] = (u[1] - u[0]) / dx
                    grad[-1] = (u[-1] - u[-2]) / dx
                deriv[index] = deriv[index] - adv * grad
            if str(left.get("type", "")).lower() == "dirichlet":
                deriv[index, 0] = 0.0
            if str(right.get("type", "")).lower() == "dirichlet":
                deriv[index, -1] = 0.0
        return deriv.reshape(-1)

    attempts: list[dict[str, Any]] = []
    solution = None
    for method in ("BDF", "Radau", "RK45"):
        try:
            candidate = solve_ivp(
                spatial_rhs,
                (t0, t1),
                initial.reshape(-1),
                t_eval=t_eval,
                method=method,
                rtol=model.solver.rtol,
                atol=model.solver.atol,
            )
            attempts.append({"method": method, "success": bool(candidate.success), "message": str(candidate.message)})
            if candidate.success and np.all(np.isfinite(candidate.y)):
                solution = candidate
                break
        except Exception as exc:
            attempts.append({"method": method, "success": False, "message": f"{type(exc).__name__}: {exc}"})
    if solution is None:
        return {"status": "FAIL", "family": model.family.value, "stage": "pde_solve", "solver_attempts": attempts}
    states: dict[str, Any] = {}
    for index, name in enumerate(state_names):
        states[name] = solution.y[index * nx:(index + 1) * nx, :].T.tolist()
    return {
        "status": "PASS",
        "family": model.family.value,
        "time": solution.t.tolist(),
        "coordinates": {str(cfg.get("space_variable", "x")): x.tolist()},
        "states": states,
        "parameters": parameters,
        "solver": {"backend": "scipy", "method": attempts[-1]["method"], "spatial_method": "method_of_lines", "attempts": attempts},
        "diagnostics": {
            "grid_points": nx,
            "dx": dx,
            "nfev": int(solution.nfev),
            "finite": bool(np.all(np.isfinite(solution.y))),
            "discretization_error": "not estimated; request an approved mesh-refinement study for a numerical error bound",
        },
    }


def _simulate_dae(model: ModelIR, *, t_span: tuple[float, float], points: int,
                  parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del seed
    from scipy.integrate import solve_ivp
    from scipy.optimize import root

    parameters = _parameter_values(model, parameter_overrides)
    derivative_equations = {e.target: e for e in model.equations if e.kind == "derivative"}
    differential = [v for v in model.variables if v.name in derivative_equations]
    algebraic = [v for v in model.variables if v.name not in derivative_equations]
    if not differential or not algebraic:
        raise ValueError("DAE requires both differential and algebraic variables")
    diff_names = [v.name for v in differential]
    alg_names = [v.name for v in algebraic]
    pnames = [p.name for p in model.parameters]
    args = [model.independent_variable, *diff_names, *alg_names, *pnames]
    derivative_fns = [_compile_expression(derivative_equations[name].expression, args) for name in diff_names]
    residual_equations = []
    for equation in model.equations:
        if equation.kind == "residual":
            residual_equations.append(equation.expression)
        elif equation.target in alg_names and equation.kind in {"algebraic", "constraint"}:
            residual_equations.append(f"({equation.target})-({equation.expression})")
    if len(residual_equations) != len(alg_names):
        raise ValueError(
            f"index-1 DAE needs one residual per algebraic variable; got {len(residual_equations)} residuals for {len(alg_names)} variables"
        )
    residual_fns = [_compile_expression(expression, args) for expression in residual_equations]
    pvals = [parameters[name] for name in pnames]
    y0 = np.asarray([float(v.initial) if v.initial is not None else np.nan for v in differential], dtype=float)
    z_guess = np.asarray([float(v.initial) if v.initial is not None else 0.0 for v in algebraic], dtype=float)
    if not np.all(np.isfinite(y0)):
        raise ValueError("all differential DAE variables need finite initial values")

    def solve_algebraic(t: float, y: np.ndarray, guess: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
        def residual(z: np.ndarray) -> np.ndarray:
            values = [float(t), *[float(v) for v in y], *[float(v) for v in z], *pvals]
            return np.asarray([float(fn(*values)) for fn in residual_fns], dtype=float)

        solved = root(residual, guess, method="hybr")
        if not solved.success or not np.all(np.isfinite(solved.x)):
            fallback = root(residual, guess, method="lm")
            solved = fallback if fallback.success and np.all(np.isfinite(fallback.x)) else solved
        if not solved.success or not np.all(np.isfinite(solved.x)):
            raise RuntimeError(f"algebraic solve failed at t={t:g}: {solved.message}")
        return np.asarray(solved.x, dtype=float), {"success": True, "message": str(solved.message)}

    z0, _ = solve_algebraic(float(t_span[0]), y0, z_guess)
    last_z = z0.copy()

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        nonlocal last_z
        last_z, _ = solve_algebraic(float(t), np.asarray(y, dtype=float), last_z)
        values = [float(t), *[float(v) for v in y], *[float(v) for v in last_z], *pvals]
        return np.asarray([float(fn(*values)) for fn in derivative_fns], dtype=float)

    t0, t1 = map(float, t_span)
    t_eval = np.linspace(t0, t1, max(2, int(points)))
    attempts: list[dict[str, Any]] = []
    solution = None
    for method in ("BDF", "Radau", "DOP853"):
        try:
            candidate = solve_ivp(rhs, (t0, t1), y0, t_eval=t_eval, method=method,
                                  rtol=model.solver.rtol, atol=model.solver.atol)
            attempts.append({"method": method, "success": bool(candidate.success), "message": str(candidate.message)})
            if candidate.success and np.all(np.isfinite(candidate.y)):
                solution = candidate
                break
        except Exception as exc:
            attempts.append({"method": method, "success": False, "message": f"{type(exc).__name__}: {exc}"})
    if solution is None:
        return {"status": "FAIL", "family": model.family.value, "stage": "dae_solve", "solver_attempts": attempts}

    algebraic_values = np.zeros((len(alg_names), len(solution.t)), dtype=float)
    guess = z0.copy()
    max_residual = 0.0
    for index, (time_value, y_value) in enumerate(zip(solution.t, solution.y.T)):
        guess, _ = solve_algebraic(float(time_value), y_value, guess)
        algebraic_values[:, index] = guess
        values = [float(time_value), *[float(v) for v in y_value], *[float(v) for v in guess], *pvals]
        residual_now = np.asarray([float(fn(*values)) for fn in residual_fns], dtype=float)
        max_residual = max(max_residual, float(np.max(np.abs(residual_now))))
    states = {name: solution.y[i].tolist() for i, name in enumerate(diff_names)}
    states.update({name: algebraic_values[i].tolist() for i, name in enumerate(alg_names)})
    return {
        "status": "PASS",
        "family": model.family.value,
        "time": solution.t.tolist(),
        "states": states,
        "parameters": parameters,
        "solver": {"backend": "scipy", "method": attempts[-1]["method"], "dae_form": "semi_explicit_index_1", "attempts": attempts},
        "diagnostics": {"max_algebraic_residual": max_residual, "finite": bool(np.all(np.isfinite(solution.y)))},
    }


def _solve_optimization(model: ModelIR, *, t_span: tuple[float, float], points: int,
                        parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del t_span, points, seed
    from scipy.optimize import minimize

    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("optimization", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.optimization must be an object")
    decisions = [v for v in model.variables if v.role == "decision"]
    if not decisions:
        decisions = [v for v in model.variables if v.role in {"state", "latent"}]
    if not decisions:
        raise ValueError("optimization requires decision variables")
    names = [v.name for v in decisions]
    pnames = [p.name for p in model.parameters]
    args = [*names, *pnames]
    objective_expression = cfg.get("objective")
    if objective_expression is None:
        objective_equation = next((e for e in model.equations if e.kind == "objective"), None)
        if objective_equation is None:
            raise ValueError("optimization requires metadata.optimization.objective or an equation with kind='objective'")
        objective_expression = objective_equation.expression
    objective_fn = _compile_expression(str(objective_expression), args)
    sense = str(cfg.get("sense", cfg.get("objective_sense", "minimize"))).lower()
    sign = -1.0 if sense in {"maximize", "max"} else 1.0
    pvals = [parameters[name] for name in pnames]

    def objective(x: np.ndarray) -> float:
        return sign * float(objective_fn(*[float(v) for v in x], *pvals))

    scipy_constraints = []
    raw_constraints = cfg.get("constraints", [])
    if not isinstance(raw_constraints, list):
        raise ValueError("optimization.constraints must be an array")
    for item in raw_constraints:
        if not isinstance(item, dict) or "expression" not in item:
            raise ValueError("each optimization constraint must be an object with expression")
        fn = _compile_expression(str(item["expression"]), args)
        relation = str(item.get("relation", "ge")).lower()
        threshold = float(item.get("threshold", 0.0))
        upper = item.get("upper")

        def value(x: np.ndarray, fn: Callable[..., Any] = fn) -> float:
            return float(fn(*[float(v) for v in x], *pvals))

        if relation == "ge":
            scipy_constraints.append({"type": "ineq", "fun": lambda x, f=value, t=threshold: f(x) - t})
        elif relation == "le":
            scipy_constraints.append({"type": "ineq", "fun": lambda x, f=value, t=threshold: t - f(x)})
        elif relation == "eq":
            scipy_constraints.append({"type": "eq", "fun": lambda x, f=value, t=threshold: f(x) - t})
        elif relation == "between":
            if upper is None:
                raise ValueError("optimization relation='between' requires upper")
            high = float(upper)
            scipy_constraints.append({"type": "ineq", "fun": lambda x, f=value, t=threshold: f(x) - t})
            scipy_constraints.append({"type": "ineq", "fun": lambda x, f=value, h=high: h - f(x)})
        else:
            raise ValueError(f"unsupported optimization constraint relation: {relation}")

    x0 = np.asarray([float(v.initial) if v.initial is not None else 0.0 for v in decisions], dtype=float)
    bounds = []
    for variable in decisions:
        low, high = variable.bounds if variable.bounds is not None else (None, None)
        bounds.append((None if low is None else float(low), None if high is None else float(high)))
    attempts: list[dict[str, Any]] = []
    solved = None
    methods = [str(model.solver.method)] if model.solver.method not in {"", "auto"} else []
    methods += ["SLSQP", "trust-constr"]
    seen: set[str] = set()
    for method in methods:
        if method in seen or method not in {"SLSQP", "trust-constr"}:
            continue
        seen.add(method)
        try:
            candidate = minimize(
                objective,
                x0,
                method=method,
                bounds=bounds,
                constraints=scipy_constraints,
                options={"maxiter": int(cfg.get("maxiter", 1000))},
            )
            attempts.append({"method": method, "success": bool(candidate.success), "message": str(candidate.message)})
            if candidate.success and np.all(np.isfinite(candidate.x)):
                solved = candidate
                break
            if np.all(np.isfinite(candidate.x)):
                x0 = np.asarray(candidate.x, dtype=float)
        except Exception as exc:
            attempts.append({"method": method, "success": False, "message": f"{type(exc).__name__}: {exc}"})
    if solved is None:
        return {"status": "FAIL", "family": model.family.value, "stage": "optimization", "solver_attempts": attempts}
    decision_values = {name: float(solved.x[index]) for index, name in enumerate(names)}
    raw_objective = float(objective_fn(*[decision_values[name] for name in names], *pvals))
    return {
        "status": "PASS",
        "family": model.family.value,
        "states": decision_values,
        "parameters": parameters,
        "objective": {"sense": "maximize" if sign < 0 else "minimize", "value": raw_objective},
        "solver": {"backend": "scipy", "method": attempts[-1]["method"], "attempts": attempts},
        "diagnostics": {"iterations": int(getattr(solved, "nit", 0)), "optimality_success": bool(solved.success)},
    }


def _simulate_control(model: ModelIR, *, t_span: tuple[float, float], points: int,
                      parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del seed
    from scipy.signal import lsim

    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("control", model.metadata.get("state_space", {}))
    if not isinstance(cfg, dict):
        raise ValueError("metadata.control must be an object")
    matrix_source = cfg.get("state_space", cfg)
    if not isinstance(matrix_source, dict):
        raise ValueError("control.state_space must be an object")
    try:
        A = np.asarray(matrix_source["A"], dtype=float)
        B = np.asarray(matrix_source["B"], dtype=float)
        C = np.asarray(matrix_source["C"], dtype=float)
        D = np.asarray(matrix_source["D"], dtype=float)
    except KeyError as exc:
        raise ValueError(f"control state-space matrix missing: {exc.args[0]}") from exc
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError("control A must be square")
    n = A.shape[0]
    if B.ndim == 1:
        B = B.reshape(n, 1)
    if C.ndim == 1:
        C = C.reshape(1, n)
    if D.ndim == 0:
        D = D.reshape(1, 1)
    elif D.ndim == 1:
        D = D.reshape(C.shape[0], -1)
    if B.shape[0] != n or C.shape[1] != n or D.shape != (C.shape[0], B.shape[1]):
        raise ValueError("control state-space matrix dimensions are inconsistent")
    feedback = cfg.get("feedback_gain")
    if feedback is not None:
        K = np.asarray(feedback, dtype=float)
        if K.ndim == 1:
            K = K.reshape(1, -1)
        if K.shape[1] != n or K.shape[0] != B.shape[1]:
            raise ValueError("feedback_gain shape must be (n_inputs, n_states)")
        A = A - B @ K
    t = np.linspace(float(t_span[0]), float(t_span[1]), max(2, int(points)))
    if t[-1] <= t[0]:
        raise ValueError("t_span must be increasing")
    state_vars = [v for v in model.variables if v.role == "state"]
    if len(state_vars) != n:
        raise ValueError(f"control model needs {n} state variables to match A")
    x0 = np.asarray([float(v.initial) if v.initial is not None else 0.0 for v in state_vars], dtype=float)
    m = B.shape[1]
    input_spec = cfg.get("input", 0.0)
    if isinstance(input_spec, dict):
        values = input_spec.get("values", 0.0)
        input_time = input_spec.get("time")
        array = np.asarray(values, dtype=float)
        if input_time is not None:
            ti = np.asarray(input_time, dtype=float)
            if array.ndim == 1:
                array = array.reshape(-1, 1)
            if array.shape[0] != ti.size:
                raise ValueError("control input values/time length mismatch")
            U = np.column_stack([np.interp(t, ti, array[:, j]) for j in range(array.shape[1])])
        else:
            U = array
    else:
        U = np.asarray(input_spec, dtype=float)
    if U.ndim == 0:
        U = np.full((len(t), m), float(U))
    elif U.ndim == 1:
        if m == 1 and U.size == len(t):
            U = U.reshape(-1, 1)
        elif U.size == m:
            U = np.tile(U.reshape(1, -1), (len(t), 1))
        else:
            raise ValueError("control input vector shape is ambiguous")
    if U.shape != (len(t), m):
        raise ValueError(f"control input must have shape ({len(t)}, {m})")
    tout, yout, xout = lsim((A, B, C, D), U=U, T=t, X0=x0)
    xout = np.asarray(xout, dtype=float)
    if xout.ndim == 1:
        xout = xout.reshape(-1, 1)
    yout = np.asarray(yout, dtype=float)
    if yout.ndim == 1:
        yout = yout.reshape(-1, 1)
    output_vars = [v for v in model.variables if v.role == "output"]
    output_names = [v.name for v in output_vars]
    if len(output_names) != C.shape[0]:
        output_names = [f"y{index}" for index in range(C.shape[0])]
    eig = np.linalg.eigvals(A)
    return {
        "status": "PASS",
        "family": model.family.value,
        "time": np.asarray(tout, dtype=float).tolist(),
        "states": {v.name: xout[:, index].tolist() for index, v in enumerate(state_vars)},
        "outputs": {name: yout[:, index].tolist() for index, name in enumerate(output_names)},
        "parameters": parameters,
        "solver": {"backend": "scipy.signal", "method": "state_space_lsim", "closed_loop": feedback is not None},
        "diagnostics": {
            "eigenvalues": [[float(np.real(value)), float(np.imag(value))] for value in eig],
            "stability": "stable" if np.max(np.real(eig)) < 0 else "unstable" if np.max(np.real(eig)) > 0 else "marginal",
        },
    }


def _simulate_network(model: ModelIR, *, t_span: tuple[float, float], points: int,
                      parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del seed
    from scipy.integrate import solve_ivp

    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("network", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.network must be an object")
    raw_nodes = cfg.get("nodes")
    raw_edges = cfg.get("edges", [])
    if raw_nodes is None:
        discovered: list[Any] = []
        for edge in raw_edges:
            if isinstance(edge, dict):
                pair = [edge.get("source"), edge.get("target")]
            else:
                pair = list(edge[:2])
            for node in pair:
                if node not in discovered:
                    discovered.append(node)
        if not discovered:
            discovered = list(range(int(cfg.get("n_nodes", 1))))
        raw_nodes = discovered
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("network.nodes must be a non-empty array")
    nodes = list(raw_nodes)
    node_index = {str(node): index for index, node in enumerate(nodes)}
    n = len(nodes)
    adjacency = np.zeros((n, n), dtype=float)
    directed = bool(cfg.get("directed", False))
    for edge in raw_edges:
        if isinstance(edge, dict):
            source, target = edge.get("source"), edge.get("target")
            weight = float(edge.get("weight", 1.0))
        else:
            values = list(edge)
            if len(values) < 2:
                raise ValueError("network edge must have source and target")
            source, target = values[0], values[1]
            weight = float(values[2]) if len(values) > 2 else 1.0
        if str(source) not in node_index or str(target) not in node_index:
            raise ValueError("network edge references unknown node")
        i, j = node_index[str(source)], node_index[str(target)]
        adjacency[i, j] += weight
        if not directed:
            adjacency[j, i] += weight
    state_vars = [v for v in model.variables if v.role == "state"]
    names = [v.name for v in state_vars]
    if not names:
        raise ValueError("network model requires state variables")
    pnames = [p.name for p in model.parameters]
    metric_names: list[str] = ["degree"]
    for name in names:
        metric_names.extend([f"mean_{name}", f"neighbor_{name}_sum", f"neighbor_{name}_mean", f"laplacian_{name}"])
    args = [model.independent_variable, *names, *metric_names, *pnames]
    by_target = {e.target: e for e in model.equations if e.kind == "derivative"}
    missing = sorted(set(names) - set(by_target))
    if missing:
        raise ValueError(f"network model missing derivative equations: {missing}")
    functions = {name: _compile_expression(by_target[name].expression, args) for name in names}
    pvals = [parameters[name] for name in pnames]
    initial_cfg = cfg.get("initial", {})
    if not isinstance(initial_cfg, dict):
        raise ValueError("network.initial must be an object")
    initial = np.zeros((len(names), n), dtype=float)
    for sindex, variable in enumerate(state_vars):
        raw = initial_cfg.get(variable.name, variable.initial)
        if isinstance(raw, dict):
            initial[sindex] = [float(raw.get(str(node), raw.get(node, variable.initial if variable.initial is not None else 0.0))) for node in nodes]
        elif isinstance(raw, list):
            values = np.asarray(raw, dtype=float)
            if values.shape != (n,):
                raise ValueError(f"network.initial.{variable.name} must have length {n}")
            initial[sindex] = values
        elif raw is not None:
            initial[sindex] = float(raw)
        else:
            raise ValueError(f"network state {variable.name!r} needs an initial value")
    degree = np.sum(adjacency, axis=1)

    def rhs(t: float, flat: np.ndarray) -> np.ndarray:
        values = np.asarray(flat, dtype=float).reshape(len(names), n)
        global_means = {name: float(np.mean(values[index])) for index, name in enumerate(names)}
        out = np.zeros_like(values)
        for node_i in range(n):
            local = [float(values[index, node_i]) for index in range(len(names))]
            metrics: list[float] = [float(degree[node_i])]
            for state_i, name in enumerate(names):
                neighbor_sum = float(adjacency[node_i] @ values[state_i])
                neighbor_mean = neighbor_sum / degree[node_i] if degree[node_i] > 0 else float(values[state_i, node_i])
                laplacian = neighbor_sum - float(degree[node_i]) * float(values[state_i, node_i])
                metrics.extend([global_means[name], neighbor_sum, neighbor_mean, laplacian])
            call_args = [float(t), *local, *metrics, *pvals]
            for state_i, name in enumerate(names):
                out[state_i, node_i] = float(functions[name](*call_args))
        return out.reshape(-1)

    t0, t1 = map(float, t_span)
    t_eval = np.linspace(t0, t1, max(2, int(points)))
    attempts: list[dict[str, Any]] = []
    solution = None
    for method in ("DOP853", "RK45", "Radau"):
        try:
            candidate = solve_ivp(rhs, (t0, t1), initial.reshape(-1), t_eval=t_eval, method=method,
                                  rtol=model.solver.rtol, atol=model.solver.atol)
            attempts.append({"method": method, "success": bool(candidate.success), "message": str(candidate.message)})
            if candidate.success and np.all(np.isfinite(candidate.y)):
                solution = candidate
                break
        except Exception as exc:
            attempts.append({"method": method, "success": False, "message": f"{type(exc).__name__}: {exc}"})
    if solution is None:
        return {"status": "FAIL", "family": model.family.value, "stage": "network_solve", "solver_attempts": attempts}
    states = {
        name: solution.y[index * n:(index + 1) * n, :].T.tolist()
        for index, name in enumerate(names)
    }
    return {
        "status": "PASS",
        "family": model.family.value,
        "time": solution.t.tolist(),
        "coordinates": {"node": [str(node) for node in nodes]},
        "states": states,
        "parameters": parameters,
        "solver": {"backend": "scipy+networkx-compatible", "method": attempts[-1]["method"], "attempts": attempts},
        "diagnostics": {"nodes": n, "edges": int(np.count_nonzero(adjacency) if directed else np.count_nonzero(adjacency) // 2), "directed": directed},
    }


def _log_prior(value: float, prior: dict[str, Any] | None, bounds: tuple[float | None, float | None] | None,
               center: float) -> float:
    if bounds is not None:
        low, high = bounds
        if low is not None and value < float(low):
            return -math.inf
        if high is not None and value > float(high):
            return -math.inf
    if not prior:
        scale = max(abs(center), 1.0) * 10.0
        return -0.5 * ((value - center) / scale) ** 2 - math.log(scale)
    dist = str(prior.get("dist", prior.get("distribution", "normal"))).lower()
    if dist == "normal":
        mu = float(prior.get("mu", prior.get("mean", center)))
        sigma = float(prior.get("sigma", prior.get("sd", 1.0)))
        if sigma <= 0:
            raise ValueError("normal prior sigma must be positive")
        return -0.5 * ((value - mu) / sigma) ** 2 - math.log(sigma)
    if dist == "halfnormal":
        sigma = float(prior.get("sigma", prior.get("sd", 1.0)))
        if value < 0 or sigma <= 0:
            return -math.inf
        return -0.5 * (value / sigma) ** 2 - math.log(sigma)
    if dist == "uniform":
        low = float(prior.get("low", prior.get("lower", -math.inf)))
        high = float(prior.get("high", prior.get("upper", math.inf)))
        return 0.0 if low <= value <= high else -math.inf
    if dist == "lognormal":
        if value <= 0:
            return -math.inf
        mu = float(prior.get("mu", 0.0))
        sigma = float(prior.get("sigma", 1.0))
        if sigma <= 0:
            raise ValueError("lognormal prior sigma must be positive")
        logv = math.log(value)
        return -0.5 * ((logv - mu) / sigma) ** 2 - math.log(value * sigma)
    raise ValueError(f"unsupported builtin prior distribution: {dist}")


def _infer_bayesian(model: ModelIR, *, t_span: tuple[float, float], points: int,
                    parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del t_span
    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("bayesian", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.bayesian must be an object")
    data = cfg.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("bayesian.data must be an object")
    observed_raw = cfg.get("observations", cfg.get("observed"))
    if observed_raw is None and isinstance(cfg.get("outcome"), str):
        observed_raw = data.get(str(cfg["outcome"]))
    if observed_raw is None:
        raise ValueError("bayesian inference requires observations")
    observed = np.asarray(observed_raw, dtype=float)
    if observed.ndim != 1 or observed.size < 2:
        raise ValueError("bayesian observations must be a 1D array with at least 2 values")
    mean_expression = cfg.get("mean_expression")
    if mean_expression is None:
        equation = next((e for e in model.equations if e.kind in {"likelihood", "observation", "mean"}), None)
        if equation is None:
            raise ValueError("bayesian inference requires mean_expression or likelihood/observation equation")
        mean_expression = equation.expression
    sampled_parameters = [p for p in model.parameters if p.fit or p.prior is not None]
    if not sampled_parameters:
        sampled_parameters = list(model.parameters)
    if not sampled_parameters:
        raise ValueError("bayesian inference requires at least one parameter")
    predictor_names = sorted(k for k in data if k != cfg.get("outcome"))
    pnames = [p.name for p in model.parameters]
    args = [*predictor_names, *pnames]
    mean_fn = _compile_expression(str(mean_expression), args)
    predictor_values: list[Any] = []
    for name in predictor_names:
        array = np.asarray(data[name], dtype=float)
        if array.ndim == 0:
            predictor_values.append(float(array))
        elif array.shape == observed.shape:
            predictor_values.append(array)
        else:
            raise ValueError(f"bayesian.data.{name} must be scalar or match observations")
    sigma_spec = cfg.get("sigma", 1.0)
    if isinstance(sigma_spec, str) and sigma_spec not in pnames:
        raise ValueError("bayesian sigma parameter name is unknown")
    draws = int(cfg.get("draws", max(200, int(points))))
    burn = int(cfg.get("burn", max(50, draws // 4)))
    if draws < 50 or burn < 0 or draws > 200000:
        raise ValueError("bayesian draws must be in [50, 200000] and burn nonnegative")
    total = draws + burn
    current = np.asarray([parameters[p.name] for p in sampled_parameters], dtype=float)
    proposal_cfg = cfg.get("proposal_scale", {})
    proposal_scale = np.zeros(len(sampled_parameters), dtype=float)
    for index, parameter in enumerate(sampled_parameters):
        if isinstance(proposal_cfg, dict) and parameter.name in proposal_cfg:
            proposal_scale[index] = float(proposal_cfg[parameter.name])
        elif isinstance(proposal_cfg, (int, float)):
            proposal_scale[index] = float(proposal_cfg)
        elif parameter.prior and str(parameter.prior.get("dist", "normal")).lower() in {"normal", "halfnormal", "lognormal"}:
            proposal_scale[index] = 0.15 * float(parameter.prior.get("sigma", parameter.prior.get("sd", 1.0)))
        elif parameter.bounds is not None and parameter.bounds[0] is not None and parameter.bounds[1] is not None:
            proposal_scale[index] = 0.05 * (float(parameter.bounds[1]) - float(parameter.bounds[0]))
        else:
            proposal_scale[index] = 0.1 * max(abs(parameters[parameter.name]), 1.0)
        proposal_scale[index] = max(proposal_scale[index], 1e-8)

    sampled_index = {parameter.name: index for index, parameter in enumerate(sampled_parameters)}

    def log_posterior(values: np.ndarray) -> float:
        env = dict(parameters)
        for parameter in sampled_parameters:
            env[parameter.name] = float(values[sampled_index[parameter.name]])
        prior_total = 0.0
        for parameter in sampled_parameters:
            lp = _log_prior(
                env[parameter.name], parameter.prior, parameter.bounds,
                parameters[parameter.name],
            )
            if not math.isfinite(lp):
                return -math.inf
            prior_total += lp
        mean = np.asarray(mean_fn(*predictor_values, *[env[name] for name in pnames]), dtype=float)
        if mean.ndim == 0:
            mean = np.full(observed.shape, float(mean))
        if mean.shape != observed.shape or not np.all(np.isfinite(mean)):
            return -math.inf
        sigma = env[sigma_spec] if isinstance(sigma_spec, str) else float(sigma_spec)
        if sigma <= 0 or not math.isfinite(float(sigma)):
            return -math.inf
        residual = observed - mean
        likelihood = -0.5 * float(np.sum((residual / sigma) ** 2)) - observed.size * math.log(float(sigma))
        return prior_total + likelihood

    rng = np.random.default_rng(seed)
    current_lp = log_posterior(current)
    if not math.isfinite(current_lp):
        raise ValueError("initial Bayesian parameter values have zero/invalid posterior density")
    chain = np.zeros((draws, len(sampled_parameters)), dtype=float)
    accepted = 0
    kept = 0
    for iteration in range(total):
        proposal = current + rng.normal(scale=proposal_scale, size=current.shape)
        proposed_lp = log_posterior(proposal)
        if math.isfinite(proposed_lp) and math.log(max(rng.random(), 1e-300)) < proposed_lp - current_lp:
            current = proposal
            current_lp = proposed_lp
            accepted += 1
        if iteration >= burn:
            chain[kept] = current
            kept += 1
    summaries: dict[str, Any] = {}
    posterior_parameters = dict(parameters)
    for index, parameter in enumerate(sampled_parameters):
        column = chain[:, index]
        mean = float(np.mean(column))
        posterior_parameters[parameter.name] = mean
        summaries[parameter.name] = {
            "mean": mean,
            "sd": float(np.std(column, ddof=1)),
            "q025": float(np.quantile(column, 0.025)),
            "median": float(np.quantile(column, 0.5)),
            "q975": float(np.quantile(column, 0.975)),
        }
    states = {v.name: float(v.initial) for v in model.variables if v.initial is not None}
    result: dict[str, Any] = {
        "status": "PASS",
        "family": model.family.value,
        "states": states,
        "parameters": posterior_parameters,
        "posterior": summaries,
        "solver": {"backend": "builtin", "method": "random_walk_metropolis", "seed": int(seed)},
        "diagnostics": {
            "draws": draws,
            "burn": burn,
            "acceptance_rate": float(accepted / total),
            "finite": bool(np.all(np.isfinite(chain))),
        },
    }
    if bool(cfg.get("return_samples", False)):
        result["samples"] = {parameter.name: chain[:, index].tolist() for index, parameter in enumerate(sampled_parameters)}
    return result


def _simulate_agent_based(model: ModelIR, *, t_span: tuple[float, float], points: int,
                          parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("agents", model.metadata.get("agent_based", {}))
    if not isinstance(cfg, dict):
        raise ValueError("metadata.agents must be an object")
    n_agents = int(cfg.get("count", cfg.get("n_agents", 100)))
    if n_agents < 1 or n_agents > 1_000_000:
        raise ValueError("agent count must be between 1 and 1000000")
    state_vars = [v for v in model.variables if v.role == "state"]
    names = [v.name for v in state_vars]
    if not names:
        raise ValueError("agent-based model requires state variables")
    pnames = [p.name for p in model.parameters]
    metric_names = [f"mean_{name}" for name in names]
    args = [model.independent_variable, *names, *metric_names, *pnames]
    by_target = {e.target: e for e in model.equations if e.kind in {"update", "difference", "derivative"}}
    missing = sorted(set(names) - set(by_target))
    if missing:
        raise ValueError(f"agent model missing update/derivative equations: {missing}")
    functions = {name: _compile_expression(by_target[name].expression, args) for name in names}
    initial_cfg = cfg.get("initial", {})
    if not isinstance(initial_cfg, dict):
        raise ValueError("agents.initial must be an object")
    values = np.zeros((len(names), n_agents), dtype=float)
    for index, variable in enumerate(state_vars):
        raw = initial_cfg.get(variable.name, variable.initial)
        if isinstance(raw, list):
            array = np.asarray(raw, dtype=float)
            if array.shape != (n_agents,):
                raise ValueError(f"agents.initial.{variable.name} must have length {n_agents}")
            values[index] = array
        elif raw is not None:
            values[index] = float(raw)
        else:
            raise ValueError(f"agent state {variable.name!r} needs an initial value")
    time = np.linspace(float(t_span[0]), float(t_span[1]), max(2, int(points)))
    if time[-1] <= time[0]:
        raise ValueError("t_span must be increasing")
    history = {name: np.zeros((len(time), n_agents), dtype=float) for name in names}
    for index, name in enumerate(names):
        history[name][0] = values[index]
    noise_cfg = cfg.get("noise_std", {})
    if not isinstance(noise_cfg, (dict, int, float)):
        raise ValueError("agents.noise_std must be scalar or state mapping")
    rng = np.random.default_rng(seed)
    pvals = [parameters[name] for name in pnames]
    for step in range(1, len(time)):
        dt = float(time[step] - time[step - 1])
        means = [float(np.mean(values[index])) for index in range(len(names))]
        old = values.copy()
        for index, name in enumerate(names):
            evaluated = np.asarray(functions[name](float(time[step - 1]), *[old[j] for j in range(len(names))], *means, *pvals), dtype=float)
            if evaluated.ndim == 0:
                evaluated = np.full(n_agents, float(evaluated))
            if evaluated.shape != (n_agents,):
                raise ValueError(f"agent update for {name!r} must evaluate to scalar or one value per agent")
            if by_target[name].kind == "derivative":
                values[index] = old[index] + dt * evaluated
            else:
                values[index] = evaluated
            raw_noise = noise_cfg.get(name, 0.0) if isinstance(noise_cfg, dict) else noise_cfg
            noise = float(raw_noise)
            if noise != 0.0:
                values[index] += rng.normal(scale=noise * math.sqrt(dt), size=n_agents)
            if state_vars[index].bounds is not None:
                low, high = state_vars[index].bounds
                if low is not None:
                    values[index] = np.maximum(values[index], float(low))
                if high is not None:
                    values[index] = np.minimum(values[index], float(high))
            history[name][step] = values[index]
    return {
        "status": "PASS",
        "family": model.family.value,
        "time": time.tolist(),
        "coordinates": {"agent": list(range(n_agents))},
        "states": {name: history[name].tolist() for name in names},
        "parameters": parameters,
        "solver": {"backend": "builtin", "method": "synchronous_agent_loop", "seed": int(seed)},
        "diagnostics": {"agents": n_agents, "steps": len(time) - 1, "finite": bool(all(np.all(np.isfinite(history[name])) for name in names))},
    }


def _simulate_discrete_event(model: ModelIR, *, t_span: tuple[float, float], points: int,
                             parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("discrete_event", model.metadata.get("events", {}))
    if isinstance(cfg, list):
        cfg = {"events": cfg}
    if not isinstance(cfg, dict):
        raise ValueError("metadata.discrete_event must be an object")
    events = cfg.get("events", [])
    if not isinstance(events, list) or not events:
        raise ValueError("discrete-event model requires metadata.discrete_event.events")
    state_vars = [v for v in model.variables if v.role == "state"]
    names = [v.name for v in state_vars]
    pnames = [p.name for p in model.parameters]
    args = [model.independent_variable, *names, *pnames]
    compiled_events = []
    for event in events:
        if not isinstance(event, dict) or "rate" not in event or not isinstance(event.get("delta"), dict):
            raise ValueError("each discrete event needs rate and delta mapping")
        rate_fn = _compile_expression(str(event["rate"]), args)
        delta_fns: dict[str, Any] = {}
        for name, delta in event["delta"].items():
            if name not in names:
                raise ValueError(f"event delta references unknown state {name!r}")
            delta_fns[name] = _compile_expression(str(delta), args) if isinstance(delta, str) else float(delta)
        compiled_events.append((str(event.get("name", f"event_{len(compiled_events)}")), rate_fn, delta_fns))
    state = np.asarray([float(v.initial) if v.initial is not None else np.nan for v in state_vars], dtype=float)
    if not np.all(np.isfinite(state)):
        raise ValueError("all discrete-event states need finite initial values")
    t0, t1 = map(float, t_span)
    sample_times = np.linspace(t0, t1, max(2, int(points)))
    history = np.zeros((len(sample_times), len(names)), dtype=float)
    history[0] = state
    sample_index = 1
    current_time = t0
    event_counts = {name: 0 for name, _, _ in compiled_events}
    max_events = int(cfg.get("max_events", 1_000_000))
    rng = np.random.default_rng(seed)
    total_events = 0
    pvals = [parameters[name] for name in pnames]
    while current_time < t1 and total_events < max_events:
        call_args = [float(current_time), *[float(v) for v in state], *pvals]
        rates = np.asarray([float(rate_fn(*call_args)) for _, rate_fn, _ in compiled_events], dtype=float)
        if np.any(~np.isfinite(rates)) or np.any(rates < 0):
            raise ValueError("event rates must be finite and nonnegative")
        total_rate = float(np.sum(rates))
        if total_rate <= 0:
            break
        next_time = current_time + float(rng.exponential(1.0 / total_rate))
        while sample_index < len(sample_times) and sample_times[sample_index] <= min(next_time, t1):
            history[sample_index] = state
            sample_index += 1
        if next_time > t1:
            current_time = t1
            break
        choice = int(rng.choice(len(compiled_events), p=rates / total_rate))
        event_name, _, delta_fns = compiled_events[choice]
        call_args = [float(next_time), *[float(v) for v in state], *pvals]
        for state_name, delta in delta_fns.items():
            index = names.index(state_name)
            amount = float(delta(*call_args)) if callable(delta) else float(delta)
            state[index] += amount
        current_time = next_time
        event_counts[event_name] += 1
        total_events += 1
    while sample_index < len(sample_times):
        history[sample_index] = state
        sample_index += 1
    status = "PASS" if total_events < max_events else "FAIL"
    return {
        "status": status,
        "family": model.family.value,
        "time": sample_times.tolist(),
        "states": {name: history[:, index].tolist() for index, name in enumerate(names)},
        "parameters": parameters,
        "solver": {"backend": "builtin", "method": "gillespie_event_queue", "seed": int(seed)},
        "diagnostics": {"total_events": total_events, "event_counts": event_counts, "max_events_reached": total_events >= max_events},
    }


def _simulate_hybrid(model: ModelIR, *, t_span: tuple[float, float], points: int,
                     parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del seed
    from scipy.integrate import solve_ivp

    parameters = _parameter_values(model, parameter_overrides)
    state_vars = [v for v in model.variables if v.role == "state"]
    names = [v.name for v in state_vars]
    by_target = {e.target: e for e in model.equations if e.kind == "derivative"}
    missing = sorted(set(names) - set(by_target))
    if missing:
        raise ValueError(f"hybrid model missing derivative equations: {missing}")
    pnames = [p.name for p in model.parameters]
    args = [model.independent_variable, *names, *pnames]
    derivative_fns = [_compile_expression(by_target[name].expression, args) for name in names]
    pvals = [parameters[name] for name in pnames]

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        call_args = [float(t), *[float(v) for v in y], *pvals]
        return np.asarray([float(fn(*call_args)) for fn in derivative_fns], dtype=float)

    cfg = model.metadata.get("hybrid", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.hybrid must be an object")
    raw_events = cfg.get("events", [])
    if not isinstance(raw_events, list):
        raise ValueError("hybrid.events must be an array")
    compiled = []
    for event in raw_events:
        if not isinstance(event, dict) or "expression" not in event:
            raise ValueError("each hybrid event requires expression")
        event_fn = _compile_expression(str(event["expression"]), args)
        reset_raw = event.get("reset", {})
        if not isinstance(reset_raw, dict):
            raise ValueError("hybrid event reset must be an object")
        reset = {
            name: _compile_expression(str(expression), args)
            for name, expression in reset_raw.items()
        }
        unknown = sorted(set(reset) - set(names))
        if unknown:
            raise ValueError(f"hybrid reset references unknown states: {unknown}")
        compiled.append({
            "name": str(event.get("name", f"event_{len(compiled)}")),
            "function": event_fn,
            "reset": reset,
            "direction": float(event.get("direction", 0.0)),
        })
    y = np.asarray([float(v.initial) if v.initial is not None else np.nan for v in state_vars], dtype=float)
    if not np.all(np.isfinite(y)):
        raise ValueError("all hybrid states need finite initial values")
    time = np.linspace(float(t_span[0]), float(t_span[1]), max(2, int(points)))
    history = np.zeros((len(time), len(names)), dtype=float)
    history[0] = y
    event_log: list[dict[str, Any]] = []
    max_events_per_interval = int(cfg.get("max_events_per_interval", 100))

    def event_wrapper(item: dict[str, Any]) -> Callable[[float, np.ndarray], float]:
        def fn(t: float, state: np.ndarray) -> float:
            return float(item["function"](float(t), *[float(v) for v in state], *pvals))
        fn.terminal = True  # type: ignore[attr-defined]
        fn.direction = item["direction"]  # type: ignore[attr-defined]
        return fn

    wrappers = [event_wrapper(item) for item in compiled]
    for index in range(1, len(time)):
        current = float(time[index - 1])
        target = float(time[index])
        events_this_interval = 0
        while current < target - 1e-14:
            solution = solve_ivp(
                rhs,
                (current, target),
                y,
                method="DOP853",
                rtol=model.solver.rtol,
                atol=model.solver.atol,
                events=wrappers if wrappers else None,
            )
            if not solution.success or not np.all(np.isfinite(solution.y)):
                return {"status": "FAIL", "family": model.family.value, "stage": "hybrid_continuous_solve", "message": str(solution.message)}
            y = np.asarray(solution.y[:, -1], dtype=float)
            hit_index = None
            hit_time = None
            if wrappers:
                for event_i, event_times in enumerate(solution.t_events):
                    if len(event_times):
                        candidate_time = float(event_times[0])
                        if hit_time is None or candidate_time < hit_time:
                            hit_time = candidate_time
                            hit_index = event_i
            if hit_index is None or hit_time is None:
                current = target
                break
            item = compiled[hit_index]
            event_state = np.asarray(solution.y_events[hit_index][0], dtype=float)
            call_args = [hit_time, *[float(v) for v in event_state], *pvals]
            reset_state = event_state.copy()
            for state_name, reset_fn in item["reset"].items():
                reset_state[names.index(state_name)] = float(reset_fn(*call_args))
            y = reset_state
            event_log.append({"name": item["name"], "time": hit_time, "state_after": {name: float(y[j]) for j, name in enumerate(names)}})
            events_this_interval += 1
            if events_this_interval >= max_events_per_interval:
                return {"status": "FAIL", "family": model.family.value, "stage": "hybrid_event_chatter", "detail": "max_events_per_interval reached"}
            epsilon = max(1e-12, (target - float(time[index - 1])) * 1e-10)
            current = min(target, hit_time + epsilon)
        history[index] = y
    return {
        "status": "PASS",
        "family": model.family.value,
        "time": time.tolist(),
        "states": {name: history[:, index].tolist() for index, name in enumerate(names)},
        "parameters": parameters,
        "events": event_log,
        "solver": {"backend": "scipy+builtin", "method": "event_driven_piecewise_ode"},
        "diagnostics": {"event_count": len(event_log), "finite": bool(np.all(np.isfinite(history)))},
    }


def _estimate_causal(model: ModelIR, *, t_span: tuple[float, float], points: int,
                     parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del t_span, points, seed
    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("causal", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.causal must be an object")
    identification = cfg.get("identification", model.metadata.get("causal_identification", {}))
    if not isinstance(identification, dict):
        identification = {}
    adjustment = identification.get("adjustment_set", cfg.get("covariates", []))
    if not isinstance(adjustment, list):
        raise ValueError("causal adjustment_set/covariates must be an array")
    identified = bool(
        identification.get("randomized")
        or identification.get("intervention")
        or identification.get("identified_dag")
        or (adjustment and identification.get("assumptions"))
    )
    if not identified:
        return {
            "status": "INSUFFICIENT_CAUSAL_EVIDENCE",
            "family": model.family.value,
            "detail": "causal conclusion cannot be drawn: provide randomization/intervention evidence or an identified DAG/adjustment set with assumptions",
        }
    data = cfg.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("causal.data must be an object")
    treatment = str(cfg.get("treatment", ""))
    outcome = str(cfg.get("outcome", ""))
    if not treatment or not outcome or treatment not in data or outcome not in data:
        raise ValueError("causal model requires treatment/outcome names present in data")
    y = np.asarray(data[outcome], dtype=float)
    treatment_values = np.asarray(data[treatment], dtype=float)
    if y.ndim != 1 or treatment_values.shape != y.shape or y.size < 3:
        raise ValueError("causal treatment/outcome arrays must be same-length 1D arrays with at least 3 rows")
    columns = [np.ones_like(y), treatment_values]
    labels = ["intercept", treatment]
    for name in adjustment:
        if name not in data:
            raise ValueError(f"causal adjustment variable {name!r} missing from data")
        values = np.asarray(data[name], dtype=float)
        if values.shape != y.shape:
            raise ValueError(f"causal covariate {name!r} length mismatch")
        columns.append(values)
        labels.append(str(name))
    X = np.column_stack(columns)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    residual = y - X @ beta
    dof = max(1, y.size - X.shape[1])
    sigma2 = float(np.sum(residual ** 2) / dof)
    covariance = np.linalg.pinv(X.T @ X) * sigma2
    effect = float(beta[1])
    se = float(math.sqrt(max(0.0, covariance[1, 1])))
    counterfactuals = []
    intervention_values = cfg.get("intervention_values", [])
    if isinstance(intervention_values, list):
        means = [float(np.mean(np.asarray(data[name], dtype=float))) for name in adjustment]
        for value in intervention_values:
            row = np.asarray([1.0, float(value), *means], dtype=float)
            counterfactuals.append({"do": {treatment: float(value)}, "predicted_outcome_mean": float(row @ beta)})
    return {
        "status": "PASS",
        "family": model.family.value,
        "states": {},
        "parameters": parameters,
        "causal_effect": {"treatment": treatment, "outcome": outcome, "estimate": effect, "std_error": se},
        "counterfactuals": counterfactuals,
        "identification": identification,
        "solver": {"backend": "numpy", "method": "linear_backdoor_adjustment"},
        "diagnostics": {"n": int(y.size), "design_rank": int(np.linalg.matrix_rank(X)), "columns": labels},
        "causal_scope": "estimate is causal only conditional on the supplied identification assumptions",
    }


def _reduction(value: Any, mode: str) -> float:
    array = np.asarray(value, dtype=float)
    if array.size == 0:
        raise ValueError("cannot reduce empty coupled state")
    if mode == "mean":
        return float(np.mean(array))
    if mode == "max":
        return float(np.max(array))
    if mode == "min":
        return float(np.min(array))
    if mode == "final_mean":
        return float(np.mean(array[-1])) if array.ndim >= 2 else float(array[-1])
    return float(np.asarray(array[-1]).mean()) if array.ndim >= 2 else float(array[-1])


def _simulate_multiphysics(model: ModelIR, *, t_span: tuple[float, float], points: int,
                           parameter_overrides: dict[str, float] | None, seed: int,
                           simulate_fn: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    del parameter_overrides
    cfg = model.metadata.get("multiphysics", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.multiphysics must be an object")
    raw_components = cfg.get("components")
    if isinstance(raw_components, dict):
        component_payloads = {str(name): payload for name, payload in raw_components.items()}
    elif isinstance(raw_components, list):
        component_payloads = {}
        for item in raw_components:
            if not isinstance(item, dict) or "name" not in item:
                raise ValueError("multiphysics component list items need name")
            component_payloads[str(item["name"])] = item.get("model_ir", item.get("model"))
    else:
        raise ValueError("multiphysics.components must be an object or array")
    if len(component_payloads) < 2:
        raise ValueError("multiphysics requires at least two component models")
    components: dict[str, ModelIR] = {}
    for name, payload in component_payloads.items():
        if not isinstance(payload, dict):
            raise ValueError(f"multiphysics component {name!r} must contain Model IR")
        components[name] = ModelIR.from_dict(payload, allow_migration=False)
        if components[name].family == ModelFamily.MULTIPHYSICS:
            raise ValueError("nested multiphysics components are not supported")
    couplings = cfg.get("couplings", [])
    if not isinstance(couplings, list):
        raise ValueError("multiphysics.couplings must be an array")
    overrides: dict[str, dict[str, float]] = {name: {} for name in components}
    previous: dict[tuple[str, str], float] = {}
    tolerance = float(cfg.get("tolerance", 1e-6))
    max_iterations = int(cfg.get("max_iterations", 8))
    if max_iterations < 1 or max_iterations > 100:
        raise ValueError("multiphysics.max_iterations must be between 1 and 100")
    last_results: dict[str, dict[str, Any]] = {}
    convergence: list[dict[str, Any]] = []
    converged = not couplings
    for iteration in range(max_iterations):
        last_results = {}
        for index, (name, component) in enumerate(components.items()):
            out = simulate_fn(
                component,
                t_span=t_span,
                points=points,
                parameter_overrides=overrides[name],
                seed=seed + index,
                approve_heavy=True,
            )
            last_results[name] = out
            if out.get("status") != "PASS":
                return {
                    "status": "FAIL",
                    "family": model.family.value,
                    "stage": "component_execution",
                    "component": name,
                    "component_result": out,
                }
        max_change = 0.0
        updates: list[dict[str, Any]] = []
        new_values: dict[tuple[str, str], float] = {}
        for coupling in couplings:
            if not isinstance(coupling, dict):
                raise ValueError("each multiphysics coupling must be an object")
            source_component = str(coupling.get("from_component", ""))
            source_state = str(coupling.get("from_state", ""))
            target_component = str(coupling.get("to_component", ""))
            target_parameter = str(coupling.get("to_parameter", ""))
            if source_component not in last_results or target_component not in components:
                raise ValueError("multiphysics coupling references unknown component")
            source_states = last_results[source_component].get("states", {})
            if not isinstance(source_states, dict) or source_state not in source_states:
                raise ValueError(f"multiphysics coupling source state {source_component}.{source_state} missing")
            raw_value = _reduction(source_states[source_state], str(coupling.get("reduction", "final")))
            value = raw_value * float(coupling.get("scale", 1.0)) + float(coupling.get("offset", 0.0))
            parameter_names = {p.name for p in components[target_component].parameters}
            if target_parameter not in parameter_names:
                raise ValueError(f"multiphysics target parameter {target_component}.{target_parameter} missing")
            key = (target_component, target_parameter)
            new_values[key] = value
            old = previous.get(key, overrides[target_component].get(target_parameter, value))
            max_change = max(max_change, abs(value - old))
            updates.append({
                "from": f"{source_component}.{source_state}",
                "to": f"{target_component}.{target_parameter}",
                "value": value,
            })
        for (target_component, target_parameter), value in new_values.items():
            overrides[target_component][target_parameter] = value
        previous = new_values
        convergence.append({"iteration": iteration + 1, "max_coupling_change": max_change, "updates": updates})
        if iteration > 0 and max_change <= tolerance:
            converged = True
            break
    if couplings and not converged:
        return {
            "status": "FAIL",
            "family": model.family.value,
            "stage": "coupling_convergence",
            "components": last_results,
            "convergence": convergence,
            "detail": "multiphysics fixed-point coupling did not converge within max_iterations",
        }
    top_states = {v.name: float(v.initial) for v in model.variables if v.initial is not None}
    return {
        "status": "PASS",
        "family": model.family.value,
        "states": top_states,
        "components": last_results,
        "coupling_overrides": overrides,
        "solver": {"backend": "axiomize", "method": "partitioned_fixed_point_cosimulation"},
        "diagnostics": {"iterations": len(convergence), "converged": converged, "tolerance": tolerance},
        "convergence": convergence,
    }
