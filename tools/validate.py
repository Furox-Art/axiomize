"""Axiomize validation tool.

Runs the recommended model from a modeling session, checks internal
consistency, and sweeps the high-sensitivity parameters.

Usage:
    python validate.py --model sir --beta 0.3 --gamma 0.1 --I0 10 --N 1000000
"""

import argparse
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


def sanity_checks(sol, N, tol=1e-4):
    S, I, R = sol.y
    total_drift = np.max(np.abs(S + I + R - N))
    nonneg_ok = bool(np.all(S >= -tol) and np.all(I >= -tol) and np.all(R >= -tol))
    conserved = total_drift < 1e-3
    return {
        "conservation_of_population": bool(conserved),
        "max_population_drift": float(total_drift),
        "all_compartments_nonnegative": nonneg_ok,
        "monotonic_R_increase": bool(np.all(np.diff(R) >= -tol)),
    }


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
    match = abs(sim_final_size - theory_final_size) < 5e-2 or theory_final_size == 0
    print(f"Theory match           = {match}")

    checks = sanity_checks(sol, N)
    print("\n--- sanity checks ---")
    for k, v in checks.items():
        status = v if isinstance(v, float) else ("PASS" if v else "FAIL")
        print(f"{k:35s} {status}")
    ok = all(v for v in checks.values() if isinstance(v, bool)) and match

    if args.sweep:
        print("\n--- sensitivity sweep over beta ---")
        print(f"{'beta':>6} {'R0':>7} {'peak':>14} {'peak day':>9} {'final size':>11}")
        for b in np.linspace(0.2, 0.5, 7):
            s = run_sir(b, gamma, I0, N)
            i = s.y[1]
            pi = int(np.argmax(i))
            print(f"{b:6.3f} {b/gamma:7.2f} {i[pi]:14,.0f} {s.t[pi]:9.1f} {s.y[2][-1]/N:11.4f}")

    return 0 if ok else 1


MODELS = {"sir": report_sir}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=MODELS, default="sir")
    p.add_argument("--beta", type=float, default=0.3, help="transmission rate, 1/day")
    p.add_argument("--gamma", type=float, default=0.1, help="recovery rate, 1/day")
    p.add_argument("--I0", type=int, default=10, help="initial infected count")
    p.add_argument("--N", type=int, default=1_000_000, help="total population")
    p.add_argument("--days", type=int, default=180, help="simulation horizon")
    p.add_argument("--sweep", action="store_true", help="run sensitivity sweep over beta")
    args = p.parse_args()
    sys.exit(MODELS[args.model](args))


if __name__ == "__main__":
    main()
