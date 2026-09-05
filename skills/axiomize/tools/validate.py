"""Axiomize validation tool.

Runs reference implementations from modeling sessions, checks internal
consistency, and sweeps high-sensitivity parameters.

Models:
    sir        deterministic SIR ODE + final-size theory check
    gillespie  stochastic SIR (continuous-time Markov chain) -> extinction risk
    queue      M/M/c Erlang-C staffing cliff -> minimal staff for a wait target
"""

import argparse
import math
import sys

import numpy as np
from scipy.integrate import solve_ivp

MAX_RUNS = 100_000
MAX_GILLESPIE_WORK = 50_000_000
MAX_GILLESPIE_POPULATION = 1_000_000
MAX_DAYS = 1_000_000
MAX_RATE = 1_000_000.0
MAX_QUEUE_STAFF = 100_000


def _finite(value, name):
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def _validate_sir(beta, gamma, I0, N, days, *, stochastic=False):
    beta = _finite(beta, "beta"); gamma = _finite(gamma, "gamma")
    days = _finite(days, "days")
    if beta < 0 or beta > MAX_RATE:
        raise ValueError(f"beta must be in [0, {MAX_RATE:g}]")
    if gamma <= 0 or gamma > MAX_RATE:
        raise ValueError(f"gamma must be in (0, {MAX_RATE:g}]")
    if isinstance(I0, bool) or isinstance(N, bool):
        raise ValueError("I0 and N must be integers")
    I0 = int(I0); N = int(N)
    if N <= 0:
        raise ValueError("N must be positive")
    if stochastic and N > MAX_GILLESPIE_POPULATION:
        raise ValueError(f"Gillespie N exceeds hard limit {MAX_GILLESPIE_POPULATION}")
    if I0 < 0 or I0 > N:
        raise ValueError("I0 must satisfy 0 <= I0 <= N")
    if days <= 0 or days > MAX_DAYS:
        raise ValueError(f"days must be in (0, {MAX_DAYS}]")
    return beta, gamma, I0, N, days


def sir_rhs(t, y, beta, gamma, N):
    S, I, _R = y
    infection = beta * S * (I / N)
    return [-infection, infection - gamma * I, gamma * I]


def final_size_theory(beta, gamma):
    beta = _finite(beta, "beta"); gamma = _finite(gamma, "gamma")
    if beta < 0 or gamma <= 0:
        raise ValueError("final-size theory requires beta >= 0 and gamma > 0")
    r0 = beta / gamma
    if r0 <= 1:
        return 0.0
    from scipy.optimize import brentq
    return float(brentq(lambda z: z - (1 - np.exp(-r0 * z)), 1e-12, 1 - 1e-12))


def run_sir(beta, gamma, I0, N, days=180):
    beta, gamma, I0, N, days = _validate_sir(beta, gamma, I0, N, days)
    y0 = [N - I0, float(I0), 0.0]
    sol = solve_ivp(sir_rhs, (0, days), y0, args=(beta, gamma, N), dense_output=True, rtol=1e-8, atol=1e-8)
    if not sol.success or sol.y.shape[0] != 3 or not np.all(np.isfinite(sol.y)):
        raise RuntimeError(f"SIR solve failed: {sol.message}")
    return sol


def report_sir(args):
    beta, gamma, I0, N, days = _validate_sir(args.beta, args.gamma, args.I0, args.N, args.days)
    r0 = beta / gamma
    sol = run_sir(beta, gamma, I0, N, days)
    t, S, I, R = sol.t, *sol.y
    peak_idx = int(np.argmax(I))
    sim_final_size = R[-1] / N
    theory_final_size = final_size_theory(beta, gamma)

    print("=== SIR validation ===")
    print(f"horizon                = {days:g} days  (final-size theory is the t->infinity limit)")
    print(f"R0                     = {r0:.3f}  ({'outbreak' if r0 > 1 else 'dies out'})")
    print(f"Peak infected          = {I[peak_idx]:,.0f} at day {t[peak_idx]:.1f}")
    print(f"Final size (simulated) = {sim_final_size:.4f}")
    print(f"Final size (theory)    = {theory_final_size:.4f}")
    match = (sim_final_size < max(0.05, 3 * I0 / N)) if theory_final_size == 0 else abs(sim_final_size - theory_final_size) < 5e-2
    print(f"Theory match           = {match}")
    checks = {
        "population_conserved": bool(np.max(np.abs(S + I + R - N)) < max(1e-3, 1e-9 * N)),
        "compartments_nonnegative": bool(np.all(I >= -1e-6) and np.all(S >= -1e-6) and np.all(R >= -1e-6)),
        "R_monotonic_increase": bool(np.all(np.diff(R) >= -1e-8)),
    }
    print("\n--- sanity checks ---")
    for key, value in checks.items(): print(f"{key:35s} {'PASS' if value else 'FAIL'}")
    ok = all(checks.values()) and match

    if args.sweep:
        print("\n--- sensitivity sweep over beta ---")
        print(f"{'beta':>6} {'R0':>7} {'peak':>14} {'peak day':>9} {'final size':>11}")
        for b in np.linspace(0.2, 0.5, 7):
            s = run_sir(b, gamma, I0, N, days); i = s.y[1]; pi = int(np.argmax(i))
            print(f"{b:6.3f} {b/gamma:7.2f} {i[pi]:14,.0f} {s.t[pi]:9.1f} {s.y[2][-1]/N:11.4f}")

    if args.plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("plot skipped: matplotlib not installed")
        else:
            fig, ax = plt.subplots(figsize=(7, 4))
            for series, label in [(S, "S"), (I, "I"), (R, "R")]: ax.plot(t, series, lw=2, label=label)
            ax.axvline(t[peak_idx], ls="--", c="gray", lw=1)
            ax.annotate(f"peak {I[peak_idx]:,.0f}\nday {t[peak_idx]:.0f}", (t[peak_idx], I[peak_idx]), xytext=(8, -4), textcoords="offset points", fontsize=9)
            ax.set_xlabel("days"); ax.set_ylabel("individuals"); ax.set_title(f"SIR: beta={beta}, gamma={gamma}, R0={r0:.2f}"); ax.legend(); fig.tight_layout()
            fig.savefig(args.plot, dpi=130); plt.close(fig); print(f"\nplot saved -> {args.plot}")
    return 0 if ok else 1


def gillespie_sir_once(beta, gamma, I0, N, t_max=180.0, rng=None):
    beta, gamma, I0, N, t_max = _validate_sir(beta, gamma, I0, N, t_max, stochastic=True)
    rng = rng or np.random.default_rng()
    S, I = N - I0, I0; t = 0.0; peak_I = I0
    while I > 0 and t < t_max:
        rate_infection = beta * S * (I / N); rate_recovery = gamma * I; total = rate_infection + rate_recovery
        if total <= 0: break
        t += rng.exponential(1.0 / total)
        if rng.random() < rate_infection / total:
            S -= 1; I += 1; peak_I = max(peak_I, I)
        else: I -= 1
    return {"extinct_early": peak_I <= I0, "peak_I": peak_I, "final_R": N - S, "t_end": t}


def report_gillespie(args):
    beta, gamma, I0, N, days = _validate_sir(args.beta, args.gamma, args.I0, args.N, args.days, stochastic=True)
    runs = int(args.runs)
    if runs < 1 or runs > MAX_RUNS: raise ValueError(f"runs must be in 1..{MAX_RUNS}")
    if runs * N > MAX_GILLESPIE_WORK: raise ValueError(f"runs*N exceeds hard stochastic work limit {MAX_GILLESPIE_WORK}")
    rng = np.random.default_rng(args.seed)
    results = [gillespie_sir_once(beta, gamma, I0, N, t_max=days, rng=rng) for _ in range(runs)]
    early_extinct = sum(r["extinct_early"] for r in results)
    finals = np.array([r["final_R"] for r in results], dtype=float) / N
    peaks = np.array([r["peak_I"] for r in results])
    r0 = beta / gamma; det_final = final_size_theory(beta, gamma)
    if beta == 0:
        p_fadeout_theory = 1.0
    else:
        r = gamma / beta
        p_fadeout_theory = 1.0 / (I0 + 1.0) if abs(r - 1.0) < 1e-9 else (r - 1.0) / (r - r ** (-I0))
    results_print = early_extinct / runs
    print("=== Gillespie stochastic SIR ===")
    print("fade-out := chain dies before ever exceeding its initial size")
    print(f"R0                          = {r0:.3f}")
    print(f"runs                        = {runs}, seed = {args.seed}")
    print(f"P(early fade-out)           = {results_print:.4f}")
    print(f"theory fade-out prob        = {p_fadeout_theory:.4f}   [jump-chain]")
    print(f"mean final size             = {finals.mean():.4f}  (deterministic theory: {det_final:.4f})")
    print(f"final size 5-95% interval   = [{np.percentile(finals, 5):.4f}, {np.percentile(finals, 95):.4f}]")
    major_mask = ~np.array([r["extinct_early"] for r in results]); major = finals[major_mask]
    if len(major) > 0:
        big = int(np.sum(major > 0.1)); print(f"non-fade-out runs           = {len(major)}, of which true outbreaks (>10% infected): {big}")
        if big: print(f"true-outbreak final size    = {major[major > 0.1].mean():.4f} (deterministic: {det_final:.4f})")
    tol = max(0.04, 3 * math.sqrt(max(p_fadeout_theory * (1 - p_fadeout_theory), 1e-6) / runs))
    checks = {"fade_out_prob_consistent": bool(abs(results_print - p_fadeout_theory) < tol), "finals_within_bounds": bool(np.all((finals >= 0) & (finals <= 1))), "peaks_at_least_initial": bool(np.all(peaks >= I0))}
    print("\n--- sanity checks ---")
    for key, value in checks.items(): print(f"{key:35s} {'PASS' if value else 'FAIL'}")
    if args.sweep:
        print("\n--- sensitivity sweep over I0 (fade-out risk vs initial cases) ---"); print(f"{'I0':>5} {'P(fade-out)':>12}")
        for i0 in [v for v in [1, 5, 10, 25, 50] if v <= N]:
            rs = [gillespie_sir_once(beta, gamma, i0, N, t_max=days, rng=rng) for _ in range(200)]
            print(f"{i0:5d} {sum(r['extinct_early'] for r in rs)/len(rs):12.4f}")
    return 0 if all(checks.values()) else 1


def erlang_c(lam, mu, c):
    lam = _finite(lam, "lambda"); mu = _finite(mu, "mu")
    c = int(c)
    if lam < 0 or mu <= 0 or c < 1 or c > MAX_QUEUE_STAFF: raise ValueError("queue requires lambda >= 0, mu > 0 and bounded positive staff")
    if lam == 0: return 0.0, 0.0
    a = lam / mu; rho = a / c
    if rho >= 1: return 1.0, float("inf")
    log_terms = [k * math.log(a) - math.lgamma(k + 1) for k in range(c)]
    m = max(log_terms); sum_term = sum(math.exp(x - m) for x in log_terms)
    top = math.exp(c * math.log(a) - math.lgamma(c + 1) - math.log1p(-rho) - m)
    p_wait = top / (sum_term + top); return p_wait, p_wait / (c * mu - lam)


def report_queue(args):
    lam = _finite(args.lam, "lambda"); mu = _finite(args.mu, "mu"); target_min = _finite(args.target_wait, "target_wait")
    if lam < 0 or mu <= 0 or target_min < 0: raise ValueError("queue requires lambda >= 0, mu > 0, target_wait >= 0")
    c_min = max(1, math.ceil(lam / mu))
    if c_min > MAX_QUEUE_STAFF: raise ValueError(f"required baseline staff exceeds hard limit {MAX_QUEUE_STAFF}")
    print("=== M/M/c queue staffing (Erlang-C) ==="); print(f"lambda = {lam}/h, mu = {mu}/h, promised avg wait <= {target_min} min\n"); print(f"{'staff':>5} {'util':>6} {'P(wait)':>9} {'E[W] min':>10} {'meets':>6}")
    feasible = None; rows = []; c = c_min
    while feasible is None and c <= min(c_min + 100, MAX_QUEUE_STAFF):
        p_wait, w_h = erlang_c(lam, mu, c); w_min = w_h * 60 if math.isfinite(w_h) else float("inf"); meets = w_min <= target_min
        rows.append((c, lam / (c * mu), p_wait, w_min, meets)); feasible = c if meets else feasible; c += 1
    if not rows: return 1
    first_feasible_idx = next((i for i, row in enumerate(rows) if row[4]), len(rows) - 1)
    for c_, rho, pw, wm, mt in rows[:min(len(rows), first_feasible_idx + 2)]:
        w_str = f"{wm:10.2f}" if math.isfinite(wm) else f"{'inf':>10}"; print(f"{c_:5d} {rho:6.2f} {pw:9.4f} {w_str} {'YES' if mt else 'no':>6}")
    if feasible is None: print("\nNo staffing level meets the target within search bound."); return 1
    prev_w = rows[first_feasible_idx - 1][3] if first_feasible_idx > 0 else float("nan")
    print(f"\nminimal staffing c* = {feasible}  (fluid lower bound was {c_min})"); print(f"at c*-1 the average wait was {prev_w:.2f} min vs {rows[first_feasible_idx][3]:.2f} min -- the staffing cliff")
    checks = {"c*_above_fluid_bound": feasible >= c_min, "wait_decreases_with_staff": all(rows[i][3] >= rows[i+1][3] for i in range(len(rows)-1)), "target_met_at_c*": erlang_c(lam, mu, feasible)[1] * 60 <= target_min + 1e-9}
    print("\n--- sanity checks ---"); [print(f"{k:35s} {'PASS' if v else 'FAIL'}") for k, v in checks.items()]
    if args.sweep:
        print("\n--- sensitivity sweep over mu ---"); print(f"{'mu':>5} {'c*':>4}")
        for m in range(max(5, int(mu)-5), int(mu)+6, 2):
            cc=max(1, math.ceil(lam/m));
            while cc <= MAX_QUEUE_STAFF:
                _, wh=erlang_c(lam,m,cc)
                if wh*60 <= target_min or cc > max(1, math.ceil(lam/m))+100: break
                cc += 1
            print(f"{m:5d} {cc:4d}")
    return 0 if all(checks.values()) else 1


MODELS = {"sir": report_sir, "gillespie": report_gillespie, "queue": report_queue}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=MODELS, default="sir"); p.add_argument("--beta", type=float, default=0.3); p.add_argument("--gamma", type=float, default=0.1)
    p.add_argument("--I0", type=int, default=10); p.add_argument("--N", type=int, default=1_000_000); p.add_argument("--runs", type=int, default=300); p.add_argument("--seed", type=int, default=42)
    p.add_argument("--lam", type=float, default=60); p.add_argument("--mu", type=float, default=20); p.add_argument("--target-wait", type=float, default=3); p.add_argument("--days", type=int, default=180)
    p.add_argument("--sweep", action="store_true"); p.add_argument("--plot", metavar="PNG", default=None)
    args = p.parse_args()
    try: code = MODELS[args.model](args)
    except (ValueError, RuntimeError, OverflowError) as exc: p.error(str(exc))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
