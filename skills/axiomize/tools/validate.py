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


def sir_rhs(t, y, beta, gamma, N):
    S, I, R = y
    return [
        -beta * S * I / N,
        beta * S * I / N - gamma * I,
        gamma * I,
    ]


def final_size_theory(beta, gamma):
    r0 = beta / gamma
    if r0 <= 1:
        return 0.0
    from scipy.optimize import brentq

    f = lambda z: z - (1 - np.exp(-r0 * z))
    return brentq(f, 1e-12, 1 - 1e-12)


def run_sir(beta, gamma, I0, N, days=180):
    y0 = [N - I0, float(I0), 0.0]
    sol = solve_ivp(
        sir_rhs, (0, days), y0, args=(beta, gamma, N),
        dense_output=True, rtol=1e-8, atol=1e-8,
    )
    return sol


def report_sir(args):
    beta, gamma, I0, N = args.beta, args.gamma, args.I0, args.N
    r0 = beta / gamma
    sol = run_sir(beta, gamma, I0, N)
    t, S, I, R = sol.t, *sol.y

    peak_idx = int(np.argmax(I))
    sim_final_size = R[-1] / N
    theory_final_size = final_size_theory(beta, gamma)

    print(f"=== SIR validation ===")
    print(f"R0                     = {r0:.3f}  ({'outbreak' if r0 > 1 else 'dies out'})")
    print(f"Peak infected          = {I[peak_idx]:,.0f} at day {t[peak_idx]:.1f}")
    print(f"Final size (simulated) = {sim_final_size:.4f}")
    print(f"Final size (theory)    = {theory_final_size:.4f}")
    match = (sim_final_size < max(0.05, 3 * I0 / N)) if theory_final_size == 0 else abs(sim_final_size - theory_final_size) < 5e-2
    print(f"Theory match           = {match}")

    checks = {
        "population_conserved": bool(abs((S + I + R)[-1] - N) < 1e-3),
        "compartments_nonnegative": bool(np.all(I >= -1e-6) and np.all(S >= -1e-6)),
        "R_monotonic_increase": bool(np.all(np.diff(R) >= -1e-8)),
    }
    print("\n--- sanity checks ---")
    for k, v in checks.items():
        print(f"{k:35s} {'PASS' if v else 'FAIL'}")
    ok = all(checks.values()) and match

    if args.sweep:
        print("\n--- sensitivity sweep over beta ---")
        print(f"{'beta':>6} {'R0':>7} {'peak':>14} {'peak day':>9} {'final size':>11}")
        for b in np.linspace(0.2, 0.5, 7):
            s = run_sir(b, gamma, I0, N)
            i = s.y[1]
            pi = int(np.argmax(i))
            print(f"{b:6.3f} {b/gamma:7.2f} {i[pi]:14,.0f} {s.t[pi]:9.1f} {s.y[2][-1]/N:11.4f}")

    if args.plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("plot skipped: matplotlib not installed")
        else:
            fig, ax = plt.subplots(figsize=(7, 4))
            for series, label in [(S, "S"), (I, "I"), (R, "R")]:
                ax.plot(t, series, lw=2, label=label)
            ax.axvline(t[peak_idx], ls="--", c="gray", lw=1)
            ax.annotate(f"peak {I[peak_idx]:,.0f}\nday {t[peak_idx]:.0f}",
                        (t[peak_idx], I[peak_idx]), xytext=(8, -4),
                        textcoords="offset points", fontsize=9)
            ax.set_xlabel("days")
            ax.set_ylabel("individuals")
            ax.set_title(f"SIR: beta={beta}, gamma={gamma}, R0={r0:.2f}")
            ax.legend()
            fig.tight_layout()
            fig.savefig(args.plot, dpi=130)
            plt.close(fig)
            print(f"\nplot saved -> {args.plot}")

    return 0 if ok else 1


def gillespie_sir_once(beta, gamma, I0, N, t_max=180.0, rng=None):
    rng = rng or np.random.default_rng()
    S, I = N - I0, I0
    t = 0.0
    peak_I = I0
    while I > 0 and t < t_max:
        rate_infection = beta * S * I / N
        rate_recovery = gamma * I
        total = rate_infection + rate_recovery
        if total <= 0:
            break
        t += rng.exponential(1.0 / total)
        if rng.random() < rate_infection / total:
            S -= 1
            I += 1
            peak_I = max(peak_I, I)
        else:
            I -= 1
    recovered = N - S
    return {"extinct_early": peak_I <= I0, "peak_I": peak_I, "final_R": recovered, "t_end": t}


def report_gillespie(args):
    beta, gamma, I0, N = args.beta, args.gamma, args.I0, args.N
    runs = args.runs
    rng = np.random.default_rng(args.seed)

    results = [gillespie_sir_once(beta, gamma, I0, N, rng=rng) for _ in range(runs)]
    early_extinct = sum(r["extinct_early"] for r in results)
    finals = np.array([r["final_R"] for r in results]) / N
    peaks = np.array([r["peak_I"] for r in results])

    r0 = beta / gamma
    det_final = final_size_theory(beta, gamma)
    if r0 <= 1:
        p_fadeout_theory = 1.0
    else:
        q = 1 / r0
        p_fadeout_theory = q**I0 * (1 - q) / (1 - q ** (I0 + 1))

    results_print = early_extinct / runs
    print("=== Gillespie stochastic SIR ===")
    print(f"(exact CTMC simulation; N kept small for tractability)")
    print(f"fade-out := chain dies before ever exceeding its initial size")
    print(f"R0                          = {r0:.3f}")
    print(f"runs                        = {runs}, seed = {args.seed}")
    print(f"P(early fade-out)           = {results_print:.4f}")
    print(f"theory fade-out prob        = {p_fadeout_theory:.4f}   [jump-chain, r=1/R0]")
    print(f"mean final size             = {finals.mean():.4f}  (deterministic theory: {det_final:.4f})")
    print(f"final size 5-95% interval   = [{np.percentile(finals, 5):.4f}, {np.percentile(finals, 95):.4f}]")
    major_mask = ~np.array([r["extinct_early"] for r in results])
    major = finals[major_mask]
    if len(major) > 0:
        big = np.sum(major > 0.1)
        print(f"non-fade-out runs           = {len(major)}, of which true outbreaks (>10% infected): {big}")
        print(f"true-outbreak final size    = {major[major > 0.1].mean() if big else float('nan'):.4f} (deterministic: {det_final:.4f})")

    tol = max(0.04, 3 * math.sqrt(max(p_fadeout_theory * (1 - p_fadeout_theory), 1e-6) / runs))
    checks = {
        "fade_out_prob_consistent": bool(abs(results_print - p_fadeout_theory) < tol),
        "finals_within_bounds": bool(np.all((finals >= 0) & (finals <= 1))),
        "peaks_at_least_initial": bool(np.all(peaks >= I0)),
    }
    print("\n--- sanity checks ---")
    for k, v in checks.items():
        print(f"{k:35s} {'PASS' if v else 'FAIL'}")

    if args.sweep:
        print("\n--- sensitivity sweep over I0 (fade-out risk vs initial cases) ---")
        print(f"{'I0':>5} {'P(fade-out)':>12}")
        for i0 in [1, 5, 10, 25, 50]:
            rs = [gillespie_sir_once(beta, gamma, i0, N, rng=rng) for _ in range(200)]
            p = sum(r["extinct_early"] for r in rs) / len(rs)
            print(f"{i0:5d} {p:12.4f}")

    return 0 if all(checks.values()) else 1


def erlang_c(lam, mu, c):
    a = lam / mu
    rho = a / c
    if rho >= 1:
        return 1.0, float("inf")
    log_terms = [k * math.log(a) - math.lgamma(k + 1) for k in range(c)]
    m = max(log_terms)
    sum_term = sum(math.exp(x - m) for x in log_terms)
    top = math.exp(c * math.log(a) - math.lgamma(c + 1) - math.log1p(-rho) - m)
    p_wait = top / (sum_term + top)
    w_q_hours = p_wait / (c * mu - lam)
    return p_wait, w_q_hours


def report_queue(args):
    lam, mu, target_min = args.lam, args.mu, args.target_wait
    target_h = target_min / 60.0

    c_min = max(1, math.ceil(lam / mu))
    print("=== M/M/c queue staffing (Erlang-C) ===")
    print(f"lambda = {lam}/h, mu = {mu}/h, promised avg wait <= {target_min} min\n")
    print(f"{'staff':>5} {'util':>6} {'P(wait)':>9} {'E[W] min':>10} {'meets':>6}")

    feasible = None
    rows = []
    c = c_min
    while feasible is None and c <= c_min + 100:
        p_wait, w_h = erlang_c(lam, mu, c)
        w_min = w_h * 60 if math.isfinite(w_h) else float("inf")
        meets = w_min <= target_min
        rows.append((c, lam / (c * mu), p_wait, w_min, meets))
        if meets:
            feasible = c
        c += 1

    first_feasible_idx = next((i for i, r in enumerate(rows) if r[4]), len(rows) - 1)
    show_until = min(len(rows), first_feasible_idx + 2)
    for row in rows[:show_until]:
        c_, rho, pw, wm, mt = row
        w_str = f"{wm:10.2f}" if math.isfinite(wm) else f"{'inf':>10}"
        print(f"{c_:5d} {rho:6.2f} {pw:9.4f} {w_str} {'YES' if mt else 'no':>6}")

    if feasible is None:
        print("\nNo staffing level meets the target within search bound.")
        return 1

    prev_w = rows[first_feasible_idx - 1][3] if first_feasible_idx > 0 else float("nan")
    print(f"\nminimal staffing c* = {feasible}  (fluid lower bound was {c_min})")
    print(f"at c*-1 the average wait was {prev_w:.2f} min vs {rows[first_feasible_idx][3]:.2f} min -- the staffing cliff")

    checks = {
        "c*_above_fluid_bound": bool(feasible >= c_min),
        "wait_decreases_with_staff": all(
            rows[i][3] >= rows[i + 1][3] for i in range(len(rows) - 1)
        ),
        "target_met_at_c*": bool(erlang_c(lam, mu, feasible)[1] * 60 <= target_min + 1e-9),
    }
    print("\n--- sanity checks ---")
    for k, v in checks.items():
        print(f"{k:35s} {'PASS' if v else 'FAIL'}")

    if args.sweep:
        print("\n--- sensitivity sweep over mu ---")
        print(f"{'mu':>5} {'c*':>4}")
        for m in range(max(5, int(mu) - 5), int(mu) + 6, 2):
            cc = c_min
            while True:
                _, wh = erlang_c(lam, m, cc)
                if wh * 60 <= target_min or cc > c_min + 100:
                    break
                cc += 1
            print(f"{m:5d} {cc:4d}")

    return 0 if all(checks.values()) else 1


MODELS = {
    "sir": report_sir,
    "gillespie": report_gillespie,
    "queue": report_queue,
}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=MODELS, default="sir")
    p.add_argument("--beta", type=float, default=0.3, help="SIR transmission rate, 1/day")
    p.add_argument("--gamma", type=float, default=0.1, help="SIR recovery rate, 1/day")
    p.add_argument("--I0", type=int, default=10, help="initial infected count")
    p.add_argument("--N", type=int, default=1_000_000, help="total population")
    p.add_argument("--runs", type=int, default=300, help="Gillespie Monte Carlo runs")
    p.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    p.add_argument("--lam", type=float, default=60, help="queue arrival rate per hour")
    p.add_argument("--mu", type=float, default=20, help="queue service rate per server per hour")
    p.add_argument("--target-wait", type=float, default=3, help="promised max average wait, minutes")
    p.add_argument("--days", type=int, default=180, help="SIR simulation horizon")
    p.add_argument("--sweep", action="store_true", help="run sensitivity sweep over beta")
    p.add_argument("--plot", metavar="PNG", default=None, help="save SIR curves plot (needs matplotlib)")
    args = p.parse_args()
    sys.exit(MODELS[args.model](args))


if __name__ == "__main__":
    main()
