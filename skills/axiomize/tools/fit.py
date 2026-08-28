"""Axiomize parameter calibration tool.

Fits model parameters to observed data (Phase 7 upgrade: real data instead of
placeholder values), reports confidence intervals and derived quantities.

Models:
    sir       fit beta, gamma from an infected-count time series
    logistic  fit r, K from a growth curve (adoption, population, sales)

Data format: CSV with a time column first and the observed quantity second
(header row required). Example:
    day,infected
    0,10
    5,340

Self-test (no data needed):
    python fit.py --model sir --selftest
    python fit.py --model logistic --selftest
"""

import argparse
import csv
import math
import sys

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import curve_fit


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 3:
        raise SystemExit(f"error: {path} needs a header plus at least 2 data rows")
    header, body = rows[0], [r for r in rows[1:] if len(r) >= 2]
    t = np.empty(len(body))
    y = np.empty(len(body))
    for i, r in enumerate(body):
        try:
            t[i] = float(r[0])
            y[i] = float(r[1])
        except ValueError:
            raise SystemExit(f"error: {path} row {i + 2}: cannot parse '{r[0]}', '{r[1]}' as numbers")
    return header[:2], t, y


def _sir_curve(t, beta, gamma, I0, N):
    def rhs(_, y):
        S, I, R = y
        return [-beta * S * I / N, beta * S * I / N - gamma * I, gamma * I]
    sol = solve_ivp(rhs, (t[0], t[-1]), [N - I0, float(I0), 0.0], t_eval=t,
                    rtol=1e-7, atol=1e-7)
    return sol.y[1]


def diagnostics(y, fitted, k):
    resid = y - fitted
    n = len(y)
    rss = float(np.sum(resid ** 2))
    aic = n * math.log(rss / n) + 2 * k
    bic = n * math.log(rss / n) + k * math.log(n)
    if n > 2 and np.std(resid) > 0:
        r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1])
    else:
        r1 = 0.0
    return {"rss": rss, "n": n, "k": k, "aic": aic, "bic": bic, "lag1_autocorr": r1}


def fit_sir(t, y, N=None):
    if N is None:
        raise SystemExit(
            "error: --N is required for SIR fit. Population size cannot be inferred from "
            "case counts alone — fabricating N as 50*max(y) silently returned R0=1.25 on "
            "synthetic N=100000, beta=0.35, gamma=0.12 data where truth is R0=2.92 (57% error). "
            "Pass --N <population> explicitly."
        )
    I0 = float(y[0])

    def model(tt, beta, gamma):
        return _sir_curve(tt, beta, gamma, I0, N)

    popt, pcov = curve_fit(model, t, y, p0=[0.4, 0.15],
                           bounds=([1e-4, 1e-4], [10.0, 10.0]), maxfev=20000)
    perr = np.sqrt(np.diag(pcov))
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
    if len(t) <= 2:
        raise SystemExit("error: logistic fit needs at least 3 data points (2 free parameters + residual df)")
    y0 = max(float(y[0]), 1e-9)
    K_guess = float(np.clip(y.max() * 1.2, y0 * 1.01, y0 * 1e6))

    def model(tt, r, K):
        return _logistic_curve(tt, r, K, y0)

    popt, pcov = curve_fit(model, t, y, p0=[0.3, K_guess],
                           bounds=([1e-4, y0], [10.0, y0 * 1e6]), maxfev=20000)
    perr = np.sqrt(np.diag(pcov))
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


def maybe_plot(args, t, y, result):
    if not args.plot:
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("plot skipped: matplotlib not installed")
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(t, y, s=18, label="observed", zorder=3)
    ax.plot(t, result["fitted"], lw=2, label="fitted model")
    ax.set_xlabel("time")
    ax.set_ylabel("count")
    ax.legend()
    fig.tight_layout()
    fig.savefig(args.plot, dpi=130)
    plt.close(fig)
    print(f"plot saved -> {args.plot}")


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
    print(f"=== fit selftest: sir ===")
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
    print(f"=== fit selftest: logistic ===")
    print(f"truth    : r={truth[0]}, K={truth[1]}")
    report("r fitted", r_hat, res['params']['r'][1])
    report("K fitted", k_hat, res['params']['K'][1])
    print(f"recovery within tolerance {'PASS' if ok_r and ok_k else 'FAIL'}")
    return 0 if (ok_r and ok_k) else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=["sir", "logistic"], default="sir")
    p.add_argument("--data", help="CSV file: time column then observed values")
    p.add_argument("--N", type=float, default=None, help="population size (sir) — required")
    p.add_argument("--selftest", action="store_true", help="fit synthetic data with known truth")
    p.add_argument("--compare", action="store_true", help="fit all models on the data, rank by AIC/BIC")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON result")
    p.add_argument("--plot", help="save fitted-curve plot to this PNG path", default=None)
    args = p.parse_args()

    if args.selftest:
        sys.exit(selftest_sir() if args.model == "sir" else selftest_logistic())

    if not args.data:
        p.error("--data is required unless --selftest")

    if args.model == "sir" and args.N is None and not args.compare:
        p.error("--N is required for SIR model (population size cannot be inferred from case counts)")

    header, t, y = load_csv(args.data)
    if args.compare:
        compare(t, y, args)
        return
    print(f"=== calibration: {args.model} on {args.data} ({header[0]}, {header[1]}) ===")
    result = fit_sir(t, y, args.N) if args.model == "sir" else fit_logistic(t, y)

    if args.json:
        import json
        payload = {
            "model": args.model,
            "data": args.data,
            "params": {k: {"value": v[0], "stderr": v[1]} for k, v in result["params"].items()},
            "derived": {k: v[0] for k, v in result["derived"].items()},
            "rmse": result["rmse"],
            "diagnostics": {k: v for k, v in result["diag"].items()},
        }
        print(json.dumps(payload, indent=2))
        maybe_plot(args, t, y, result)
        return

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


def compare(t, y, args):
    print("=== model comparison on same data (lower AIC/BIC better) ===")
    rows = []
    for name, fitter in [("logistic", lambda: fit_logistic(t, y)),
                         ("sir", lambda: fit_sir(t, y, args.N))]:
        try:
            res = fitter()
            d = res["diag"]
            rows.append((name, d["k"], d["aic"], d["bic"], d["lag1_autocorr"]))
        except Exception as e:
            rows.append((name, None, float("inf"), float("inf"), f"fit failed: {e}"))
    print(f"{'model':>10} {'k':>3} {'AIC':>12} {'BIC':>12} {'resid AC(1)':>12}")
    for name, k, aic, bic, ac in rows:
        ac_str = f"{ac:+.3f}" if isinstance(ac, float) else str(ac)[:12]
        print(f"{name:>10} {str(k):>3} {aic:12.2f} {bic:12.2f} {ac_str:>12}")
    best = min(rows, key=lambda r: r[3])
    print(f"\nBIC prefers: {best[0]}")


if __name__ == "__main__":
    main()
