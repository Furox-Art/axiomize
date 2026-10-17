"""Population-conserving, work-bounded Gillespie SIR simulator.

This is the package-native stochastic executor; the benchmark must not
import a checkout-only research script that does not ship in the wheel.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

MAX_POPULATION = 1_000_000
MAX_RATE = 1_000_000.0
MAX_HORIZON = 1_000_000.0


def _real(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    if (positive and number <= 0) or (not positive and number < 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")
    return number


def _whole(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    value = int(value)
    if not minimum <= value <= MAX_POPULATION:
        raise ValueError(f"{name} must be in {minimum}..{MAX_POPULATION}")
    return value


def gillespie_sir_once(
    beta: float,
    gamma: float,
    I0: int,
    N: int,
    t_max: float = 180.0,
    rng: np.random.Generator | None = None,
) -> dict[str, int | float | bool]:
    """Direct SIR Markov process with no more than 2*N events.

    The separate observation-horizon totals are:
      final_R: recovered individuals (R), not including active infections;
      total_infected: cumulative ever infected (N - S = R + I), including I0.
    Before extinction these counts generally differ. All event times are <= t_max.
    """
    beta = _real(beta, "beta")
    gamma = _real(gamma, "gamma", positive=True)
    t_max = _real(t_max, "t_max", positive=True)
    if beta > MAX_RATE or gamma > MAX_RATE or t_max > MAX_HORIZON:
        raise ValueError("SIR parameters exceed hard numerical limits")
    N = _whole(N, "population N", minimum=1)
    I0 = _whole(I0, "I0", minimum=0)
    if I0 > N:
        raise ValueError("I0 must not exceed N")
    if rng is None:
        rng = np.random.default_rng()

    susceptible = N - I0
    infected = I0
    recovered = 0
    peak = I0
    time = 0.0
    events = 0
    event_limit = 2 * N

    while infected > 0 and time < t_max:
        if events >= event_limit:
            raise RuntimeError("Gillespie SIR exceeded at-most-2*N events")
        infected_rate = beta * susceptible * (infected / N)
        recovered_rate = gamma * infected
        total_rate = infected_rate + recovered_rate
        if not math.isfinite(total_rate):
            raise ValueError("non-finite Gillespie transition rate")
        if total_rate <= 0:
            break
        delay = float(rng.exponential(1.0 / total_rate))
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("invalid Gillespie waiting time")
        if time + delay > t_max:
            time = t_max
            break
        time += delay
        if rng.random() < infected_rate / total_rate:
            susceptible -= 1
            infected += 1
            peak = max(peak, infected)
        else:
            infected -= 1
            recovered += 1
        events += 1

    assert susceptible + infected + recovered == N
    return {
        "extinct_early": peak <= I0,
        "peak_I": peak,
        "final_R": recovered,
        "total_infected": N - susceptible,
        "t_end": time,
        "events": events,
    }
