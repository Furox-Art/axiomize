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
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.integrate import solve_ivp

# This file is both a direct source-checkout script and a wheel console module,
# so keep the hard process ceiling local rather than relying on package import
# layout. Approval is not a bypass for host process limits.
MAX_WORKERS = 32
MAX_MONTE_CARLO_RUNS = 100_000


def _default_workers() -> int:
    """Resolve the configured default worker count and validate it.

    The default is derived from the host CPU count, so it is still routed
    through the same bound check as an explicit ``--workers`` value. An
    unexplained host value (0, or a ceiling above the hard limit) must be a
    loud config-load failure rather than a dispatch that silently over- or
    under-subscribes the pool.
    """
    cpu_count = os.cpu_count()
    if not isinstance(cpu_count, int) or cpu_count < 1:
        return 1
    return _bounded_workers(min(8, cpu_count, MAX_WORKERS))


def _bounded_workers(workers):
    """Validate a requested worker count at config load.

    ``ProcessPoolExecutor`` raises an opaque ``ValueError`` for ``max_workers
    <= 0`` and spawns without complaint for an oversized pool, so the bound is
    enforced here where the reason is still the ``--workers`` flag. Booleans and
    non-integral floats are rejected explicitly: ``int(True)`` is 1 and
    ``int(2.5)`` is 2, both of which would silently reinterpret the request.
    """
    if isinstance(workers, bool) or workers is None:
        raise ValueError("workers must be an integer")
    if isinstance(workers, str):
        raise ValueError("workers must be an integer, not a string")
    if isinstance(workers, float) and not workers.is_integer():
        raise ValueError("workers must be an exact integer")
    try:
        value = int(workers)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("workers must be an integer") from exc
    if value < 1 or value > MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
    return value


def _dispatch_workers(requested: int, task_count: int) -> int:
    """Clamp a validated worker count to the batch size, never below 1.

    ``min(requested, task_count)`` alone passes 0 to the executor when the batch
    is empty, which surfaces as an opaque pool error instead of a bounded job.
    """
    return max(1, min(requested, max(1, int(task_count))))


def _bounded_runs(total_runs):
    if isinstance(total_runs, bool):
        raise ValueError("total_runs must be an integer")
    try:
        value = int(total_runs)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("total_runs must be an integer") from exc
    if isinstance(total_runs, float) and not total_runs.is_integer():
        raise ValueError("total_runs must be an exact integer")
    if value < 1 or value > MAX_MONTE_CARLO_RUNS:
        raise ValueError(f"total_runs must be between 1 and {MAX_MONTE_CARLO_RUNS}")
    return value


def sir_final_size(params):
    beta, gamma, I0, N = params

    def rhs(t, y):
        S, I, R = y
        return [-beta * S * I / N, beta * S * I / N - gamma * I, gamma * I]

    sol = solve_ivp(rhs, (0, 365), [N - I0, float(I0), 0.0], rtol=1e-7, atol=1e-7)
    return (beta, gamma, sol.y[2][-1] / N)


def gillespie_chunk(args):
    beta, gamma, I0, N, runs, seed = args
    runs = _bounded_runs(runs)
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
    workers = _bounded_workers(workers)
    betas = np.round(np.linspace(0.2, 0.5, 7), 3)
    gammas = np.round(np.linspace(0.05, 0.2, 4), 3)
    tasks = [(b, g, 10, 100_000) for g in gammas for b in betas]
    actual_workers = _dispatch_workers(workers, len(tasks))

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=actual_workers) as ex:
        results = list(ex.map(sir_final_size, tasks))
    dt = time.perf_counter() - t0

    print("=== parallel sweep ===")
    print(f"{len(tasks)} independent ODE tasks on {actual_workers} workers in {dt:.2f}s\n")
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
    workers = _bounded_workers(workers)
    total_runs = _bounded_runs(total_runs)
    actual_workers = _dispatch_workers(workers, total_runs)
    beta, gamma, I0, N = 0.3, 0.1, 1, 5000
    base, remainder = divmod(total_runs, actual_workers)
    seeds = [1000 + i for i in range(actual_workers)]
    tasks = [
        (beta, gamma, I0, N, base + (1 if i < remainder else 0), seeds[i])
        for i in range(actual_workers)
    ]

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=actual_workers) as ex:
        counts = list(ex.map(gillespie_chunk, tasks))
    dt = time.perf_counter() - t0

    done = sum(counts)
    runs = sum(task[4] for task in tasks)
    p_obs = done / runs
    p_theory = (1 / (1 + beta / gamma)) ** I0
    tol = max(0.04, 3 * math.sqrt(p_theory * (1 - p_theory) / runs))

    print("=== parallel Monte Carlo ===")
    print(f"{runs} CTMC runs split into {actual_workers} frozen-brief chunks on {actual_workers} workers in {dt:.2f}s")
    print(f"P(early fade-out) observed = {p_obs:.4f}")
    print(f"theory (1/(1+R0))^I0       = {p_theory:.4f}  (tolerance {tol:.4f})")
    ok = abs(p_obs - p_theory) < tol
    print(f"sanity check -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--job", choices=["sweep", "mc"], default="sweep")
    p.add_argument("--workers", type=int, default=None)
    args = p.parse_args()
    # Worker bounds are enforced once, at config load, before any job runs. The
    # resolved default is validated too, so the exit reason is the bound and not
    # a later pool failure.
    workers = 0
    try:
        workers = _bounded_workers(args.workers if args.workers is not None else _default_workers())
    except ValueError as exc:
        p.error(str(exc))
    raise SystemExit(job_sweep(workers) if args.job == "sweep" else job_mc(workers))


if __name__ == "__main__":
    main()
