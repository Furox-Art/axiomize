"""Axiomize parameter calibration tool.

Fits model parameters to observed data, reports confidence intervals and derived
quantities. Input is bounded and validated before numerical fitting; malformed or
non-finite data never reaches SciPy.
"""

import argparse
import csv
import math
import os
import sys

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import curve_fit

MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_DATA_ROWS = 200_000
MAX_FIT_EVALUATIONS = 20_000


def _finite_float(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _validate_xy(t, y, *, minimum=2):
    t_arr = np.asarray(t, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    if t_arr.ndim != 1 or y_arr.ndim != 1:
        raise ValueError("time and observed values must be one-dimensional")
    if len(t_arr) != len(y_arr):
        raise ValueError("time and observed arrays must have the same length")
    if len(t_arr) < minimum:
        raise ValueError(f"at least {minimum} observations are required")
    if len(t_arr) > MAX_DATA_ROWS:
        raise ValueError(f"dataset exceeds hard row limit {MAX_DATA_ROWS}")
    if not np.all(np.isfinite(t_arr)) or not np.all(np.isfinite(y_arr)):
        raise ValueError("time and observed values must be finite")
    if np.any(np.diff(t_arr) <= 0):
        raise ValueError("time values must be strictly increasing with no duplicates")
    return t_arr, y_arr


def load_csv(path):
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise SystemExit(f"error: cannot stat {path}: {exc}") from exc
    if size > MAX_CSV_BYTES:
        raise SystemExit(f"error: {path} exceeds hard CSV size limit {MAX_CSV_BYTES} bytes")

    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise SystemExit(f"error: cannot open {path}: {exc}") from exc
    with fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise SystemExit(f"error: {path} is empty") from exc
        if len(header) < 2:
            raise SystemExit(f"error: {path} needs at least two columns")
        t_values = []
        y_values = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) < 2:
                continue
            if len(t_values) >= MAX_DATA_ROWS:
                raise SystemExit(f"error: {path} exceeds hard row limit {MAX_DATA_ROWS}")
            try:
                t_value = float(row[0])
                y_value = float(row[1])
            except ValueError as exc:
                raise SystemExit(
                    f"error: {path} row {row_number}: cannot parse '{row[0]}', '{row[1]}' as numbers"
                ) from exc
            if not math.isfinite(t_value) or not math.isfinite(y_value):
                raise SystemExit(f"error: {path} row {row_number}: values must be finite")
            t_values.append(t_value)
            y_values.append(y_value)

    if len(t_values) < 2:
        raise SystemExit(f"error: {path} needs a header plus at least 2 parseable data rows")
    try:
        t, y = _validate_xy(t_values, y_values, minimum=2)
    except ValueError as exc:
        raise SystemExit(f"error: {path}: {exc}") from exc
    return header[:2], t, y


def _sir_curve(t, beta, gamma, I0, N):
    t, _dummy = _validate_xy(t, np.zeros(len(t)), minimum=2)
    beta = _finite_float(beta, "beta")
    gamma = _finite_float(gamma, "gamma")
    I0 = _finite_float(I0, "I0")
    N = _finite_float(N, "N")
    if beta < 0 or gamma <= 0:
        raise ValueError("SIR beta must be non-negative and gamma must be positive")
    if N <= 0 or not 0 <= I0 <= N:
        raise ValueError("SIR requires N > 0 and 0 <= I0 <= N")

    def rhs(_, state):
        S, I, R = state
        return [-beta * S * I / N, beta * S * I / N - gamma * I, gamma * I]

    sol = solve_ivp(
        rhs,
        (float(t[0]), float(t[-1])),
        [N - I0, float(I0), 0.0],
        t_eval=t,
        rtol=1e-7,
        atol=1e-7,
    )
    if not sol.success or sol.y.shape != (3, len(t)) or not np.all(np.isfinite(sol.y)):
        raise RuntimeError(f"SIR integration failed: {sol.message}")
    return sol.y[1]


def _lag1(resid):
    resid = np.asarray(resid, dtype=float)
    if len(resid) <= 2:
        return 0.0
    left, right = resid[:-1], resid[1:]
    if np.std(left) == 0.0 or np.std(right) == 0.0:
        return 0.0
    value = float(np.corrcoef(left, right)[0, 1])
    return value if math.isfinite(value) else 0.0


def diagnostics(y, fitted, k):
    y = np.asarray(y, dtype=float)
    fitted = np.asarray(fitted, dtype=float)
    if y.shape != fitted.shape or y.ndim != 1 or not np.all(np.isfinite(y)) or not np.all(np.isfinite(fitted)):
        raise ValueError("diagnostics require matching finite 1D observed/fitted arrays")
    n = len(y)
    if n < 1 or k < 0:
        raise ValueError("diagnostics require observations and a non-negative parameter count")
    resid = y - fitted
    raw_rss = float(np.sum(resid ** 2))
    # Perfect fits have log-likelihood limit -> +infinity and information
    # criteria -> -infinity. Use a tiny positive numerical floor so CLI/JSON
    # remain finite and sortable while recording the raw RSS separately.
    rss_for_ic = max(raw_rss, np.finfo(float).tiny * max(1, n))
    aic = n * math.log(rss_for_ic / n) + 2 * k
    bic = n * math.log(rss_for_ic / n) + k * math.log(n)
    return {
        "rss": raw_rss,
        "n": n,
        "k": k,
        "aic": aic,
        "bic": bic,
        "lag1_autocorr": _lag1(resid),
        "perfect_fit_floor_applied": raw_rss == 0.0,
    }


def fit_sir(t, y, N=None):
    t, y = _validate_xy(t, y, minimum=3)
    if N is None:
        raise ValueError("N is required for SIR fit; population size cannot be inferred from case counts")
    N = _finite_float(N, "N")
    if N <= 0:
        raise ValueError("N must be positive")
    I0 = float(y[0])
    if I0 < 0 or I0 > N:
        raise ValueError("first observed infected count must satisfy 0 <= I0 <= N")
    if np.any(y < 0) or np.any(y > N):
        raise ValueError("SIR observations must lie in [0, N]")

    def model(tt, beta, gamma):
        return _sir_curve(tt, beta, gamma, I0, N)

    popt, pcov = curve_fit(
        model,
        t,
        y,
        p0=[0.4, 0.15],
        bounds=([1e-4, 1e-4], [10.0, 10.0]),
        maxfev=MAX_FIT_EVALUATIONS,
    )
    perr = np.sqrt(np.maximum(np.diag(pcov), 0.0))
    fitted = model(t, *popt)
    rmse = float(np.sqrt(np.mean((fitted - y) ** 2)))
    return {
        "params": {"beta": (popt[0], perr[0]), "gamma": (popt[1], perr[1])},
        "derived": {"R0": (popt[0] / popt[1], None)},
        "rmse": rmse,
        "fitted": fitted,
        "N": N,
        "diag": diagnostics(y, fitted, k=2),
    }


def _logistic_curve(t, r, K, y0):
    return K / (1 + (K / y0 - 1) * np.exp(-r * (t - t[0])))


def fit_logistic(t, y):
    t, y = _validate_xy(t, y, minimum=3)
    if np.any(y < 0):
        raise ValueError("logistic observations must be non-negative")
    y0 = max(float(y[0]), 1e-9)
    K_guess = float(np.clip(y.max() * 1.2, y0 * 1.01, y0 * 1e6))

    def model(tt, r, K):
        return _logistic_curve(tt, r, K, y0)

    popt, pcov = curve_fit(
        model,
        t,
        y,
        p0=[0.3, K_guess],
        bounds=([1e-4, y0], [10.0, y0 * 1e6]),
        maxfev=MAX_FIT_EVALUATIONS,
    )
    perr = np.sqrt(np.maximum(np.diag(pcov), 0.0))
    fitted = model(t, *popt)
    rmse = float(np.sqrt(np.mean((fitted - y) ** 2)))
    return {
        "params": {"r": (popt[0], perr[0]), "K": (popt[1], perr[1])},
        "derived": {"doubling_time_ln2/r_at_start": (math.log(2) / popt[0] if popt[0] > 0 else float("inf"), None)},
        "rmse": rmse,
        "fitted": fitted,
        "diag": diagnostics(y, fitted, k=2),
    }


def report(name, value, err=None, unit=""):
    e = f" +/- {err:.4g}" if err else ""
    print(f"  {name:28s} = {value:.4g}{e} {unit}".rstrip())


def maybe_plot(args, t, y, result, *, announce=True):
    if not args.plot:
        return None
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        if announce:
            print("plot skipped: matplotlib not installed")
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(t, y, s=18, label="observed", zorder=3)
    ax.plot(t, result["fitted"], lw=2, label="fitted model")
    ax.set_xlabel("time")
    ax.set_ylabel("count")
    ax.legend()
    fig.tight_layout()
    fig.savefig(args.plot, dpi=130)
    plt.close(fig)
    if announce:
        print(f"plot saved -> {args.plot}")
    return str(args.plot)


def selftest_sir():
    rng = np.random.default_rng(7)
    t = np.linspace(0, 60, 25)
    truth = (0.35, 0.12)
    N, I0 = 10000, 20

    def rhs(_, y):
        S, I, R = y
        return [-truth[0] * S * I / N, truth[0] * S * I / N - truth[1] * I, truth[1] * I]

    clean = solve_ivp(rhs, (0, 60), [N - I0, float(I0), 0.0], t_eval=t).y[1]
    noisy = clean * (1 + rng.normal(0, 0.03, size=len(t)))
    res = fit_sir(t, noisy, N=N)
    b_hat, g_hat = res["params"]["beta"][0], res["params"]["gamma"][0]
    ok_b = abs(b_hat - truth[0]) / truth[0] < 0.15
    ok_g = abs(g_hat - truth[1]) / truth[1] < 0.15
    print("=== fit selftest: sir ===")
    print(f"truth    : beta={truth[0]}, gamma={truth[1]}")
    report("beta fitted", b_hat, res['params']['beta'][1])
    report("gamma fitted", g_hat, res['params']['gamma'][1])
    report("R0 recovered", b_hat / g_hat)
    print(f"recovery within 15%      {'PASS' if ok_b and ok_g else 'FAIL'}")
    return 0 if (ok_b and ok_g) else 1


def selftest_logistic():
    rng = np.random.default_rng(11)
    t = np.linspace(0, 30, 22)
    truth = (0.4, 5000.0)
    clean = _logistic_curve(t, *truth, 40.0)
    noisy = clean * (1 + rng.normal(0, 0.02, size=len(t)))
    res = fit_logistic(t, noisy)
    r_hat, k_hat = res["params"]["r"][0], res["params"]["K"][0]
    ok_r = abs(r_hat - truth[0]) / truth[0] < 0.15
    ok_k = abs(k_hat - truth[1]) / truth[1] < 0.05
    print("=== fit selftest: logistic ===")
    print(f"truth    : r={truth[0]}, K={truth[1]}")
    report("r fitted", r_hat, res['params']['r'][1])
    report("K fitted", k_hat, res['params']['K'][1])
    print(f"recovery within tolerance {'PASS' if ok_r and ok_k else 'FAIL'}")
    return 0 if (ok_r and ok_k) else 1


def compare(t, y, args):
    print("=== model comparison on same data (lower AIC/BIC better) ===")
    rows = []
    candidates = [("logistic", lambda: fit_logistic(t, y))]
    if args.N is not None:
        candidates.append(("sir", lambda: fit_sir(t, y, args.N)))
    else:
        rows.append(("sir", None, float("inf"), float("inf"), "requires --N"))
    for name, fitter in candidates:
        try:
            res = fitter()
            d = res["diag"]
            rows.append((name, d["k"], d["aic"], d["bic"], d["lag1_autocorr"]))
        except (ValueError, RuntimeError, TypeError, FloatingPointError, OverflowError) as exc:
            rows.append((name, None, float("inf"), float("inf"), f"fit failed: {exc}"))
    print(f"{'model':>10} {'k':>3} {'AIC':>12} {'BIC':>12} {'resid AC(1)':>12}")
    for name, k, aic, bic, ac in rows:
        ac_str = f"{ac:+.3f}" if isinstance(ac, float) and math.isfinite(ac) else str(ac)[:12]
        print(f"{name:>10} {str(k):>3} {aic:12.2f} {bic:12.2f} {ac_str:>12}")
    viable = [row for row in rows if math.isfinite(row[3])]
    if not viable:
        print("\nNo model produced a valid fit.")
        return 1
    best = min(viable, key=lambda r: r[3])
    print(f"\nBIC prefers: {best[0]}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=["sir", "logistic"], default="sir")
    p.add_argument("--data", help="CSV file: time column then observed values")
    p.add_argument("--N", type=float, default=None, help="population size (sir), required")
    p.add_argument("--selftest", action="store_true", help="fit synthetic data with known truth")
    p.add_argument("--compare", action="store_true", help="fit all feasible models on the data, rank by AIC/BIC")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON result")
    p.add_argument("--plot", help="save fitted-curve plot to this PNG path", default=None)
    args = p.parse_args()

    if args.selftest:
        raise SystemExit(selftest_sir() if args.model == "sir" else selftest_logistic())
    if not args.data:
        p.error("--data is required unless --selftest")
    if args.model == "sir" and args.N is None and not args.compare:
        p.error("--N is required for SIR model (population size cannot be inferred from case counts)")

    header, t, y = load_csv(args.data)
    if args.compare:
        raise SystemExit(compare(t, y, args))
    try:
        result = fit_sir(t, y, args.N) if args.model == "sir" else fit_logistic(t, y)
    except (ValueError, RuntimeError, TypeError, FloatingPointError, OverflowError) as exc:
        p.error(str(exc))

    if args.json:
        import json
        plot_path = maybe_plot(args, t, y, result, announce=False)
        payload = {
            "model": args.model,
            "data": args.data,
            "params": {k: {"value": float(v[0]), "stderr": float(v[1])} for k, v in result["params"].items()},
            "derived": {k: float(v[0]) for k, v in result["derived"].items()},
            "rmse": float(result["rmse"]),
            "diagnostics": {k: v for k, v in result["diag"].items()},
        }
        if plot_path is not None:
            payload["plot"] = plot_path
        print(json.dumps(payload, indent=2, allow_nan=False))
        return

    print(f"=== calibration: {args.model} on {args.data} ({header[0]}, {header[1]}) ===")
    for pname, (val, err) in result["params"].items():
        report(pname, val, err)
    for dname, (val, _) in result["derived"].items():
        report(dname, val)
    print(f"  {'RMSE':28s} = {result['rmse']:.4g}")
    diag = result["diag"]
    print("  --- diagnostics ---")
    print(f"  {'AIC':28s} = {diag['aic']:.2f}")
    print(f"  {'BIC':28s} = {diag['bic']:.2f}")
    ac = diag["lag1_autocorr"]
    flag = "OK" if abs(ac) < 0.4 else "HIGH - model structure may be wrong"
    print(f"  {'residual lag-1 autocorrelation':28s} = {ac:+.3f} ({flag})")
    maybe_plot(args, t, y, result)


if __name__ == "__main__":
    main()
