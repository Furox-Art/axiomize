"""Axiomize parallel execution engine.

Demonstrates and provides the same parallel-dispatch pattern the skill
prescribes for lens subagents, applied to parameter sweeps: each grid cell /
Monte Carlo chunk is an independent worker task with frozen inputs.

Usage:
    python parallel_sweep.py --job sweep    # beta x gamma grid of SIR final sizes
    python parallel_sweep.py --job mc       # parallel Gillespie fade-out estimate
"""

import argparse
import math
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.integrate import solve_ivp


def sir_final_size(params):
    beta, gamma, I0, N = params
    def rhs(t, y):
        S, I, R = y
        return [-beta * S * I / N, beta * S * I / N - gamma * I, gamma * I]
    sol = solve_ivp(rhs, (0, 365), [N - I0, float(I0), 0.0], rtol=1e-7, atol=1e-7)
    return (beta, gamma, sol.y[2][-1] / N)


def gillespie_chunk(args):
    beta, gamma, I0, N, runs, seed = args
    rng = np.random.default_rng(seed)
    extinct = 0
    for _ in range(runs):
        S, I, t = N - I0, I0, 0.0
        peak = I0
        while I > 0 and t < 365:
            r_inf = beta * S * I / N
            total = r_inf + gamma * I
            if total <= 0:
                break
            t += rng.exponential(1.0 / total)
            if rng.random() < r_inf / total:
                S -= 1
                I += 1
                peak = max(peak, I)
            else:
                I -= 1
        if peak <= I0:
            extinct += 1
    return extinct


def job_sweep(workers):
    betas = np.round(np.linspace(0.2, 0.5, 7), 3)
    gammas = np.round(np.linspace(0.05, 0.2, 4), 3)
    tasks = [(b, g, 10, 100_000) for g in gammas for b in betas]

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(sir_final_size, tasks))
    dt = time.perf_counter() - t0

    print("=== parallel sweep ===")
    print(f"{len(tasks)} independent ODE tasks on {workers} workers in {dt:.2f}s\n")
    header_label = "beta / gamma"
    print(f"{header_label:>11} " + " ".join(f"{g:>8.2f}" for g in gammas))
    table = {(round(b, 3), round(g, 3)): fs for b, g, fs in results}
    for b in betas:
        row = " ".join(f"{table[(round(b,3), round(g,3))]:8.3f}" for g in gammas)
        print(f"{b:10.2f} {row}")

    center = table[(0.35, 0.1)]
    from scipy.optimize import brentq
    r0 = 0.35 / 0.1
    theory = brentq(lambda z: z - (1 - math.exp(-r0 * z)), 1e-12, 1 - 1e-12)
    ok = abs(center - theory) < 2e-2
    print(f"\nsanity check: center cell ({center:.4f}) vs final-size theory ({theory:.4f}) -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def job_mc(workers, total_runs=400):
    beta, gamma, I0, N = 0.3, 0.1, 1, 5000
    chunk = total_runs // workers or 1
    seeds = [1000 + i for i in range(workers)]
    tasks = [(beta, gamma, I0, N, chunk, s) for s in seeds]

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        counts = list(ex.map(gillespie_chunk, tasks))
    dt = time.perf_counter() - t0

    done = sum(counts)
    runs = chunk * workers
    p_obs = done / runs
    p_theory = (1 / (1 + beta / gamma)) ** I0
    tol = max(0.04, 3 * math.sqrt(p_theory * (1 - p_theory) / runs))

    print(f"=== parallel Monte Carlo ===")
    print(f"{runs} CTMC runs split into {workers} frozen-brief chunks on {workers} workers in {dt:.2f}s")
    print(f"P(early fade-out) observed = {p_obs:.4f}")
    print(f"theory (1/(1+R0))^I0       = {p_theory:.4f}  (tolerance {tol:.4f})")
    ok = abs(p_obs - p_theory) < tol
    print(f"sanity check -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    import os

    default_workers = min(8, os.cpu_count() or 2)
    p.add_argument("--job", choices=["sweep", "mc"], default="sweep")
    p.add_argument("--workers", type=int, default=default_workers)
    args = p.parse_args()
    exit(job_sweep(args.workers) if args.job == "sweep" else job_mc(args.workers))


if __name__ == "__main__":
    main()
