"""Direct Markov SIR accounting and explicit numerical fail-closed branches."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.tools.numerical import gillespie as sir


class FixedWait:
    def __init__(self, delay):
        self.delay = delay

    def exponential(self, _scale):
        return self.delay

    def random(self):
        return 0.5


@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        (True, "finite number"),
        ("invalid", "finite number"),
        (None, "finite number"),
        (float("nan"), "finite number"),
        (float("inf"), "finite number"),
        (-0.5, "non-negative"),
    ],
)
def test_infection_transition_rate_requires_finite_nonnegative_scalar(value, pattern):
    with pytest.raises(ValueError, match=pattern):
        sir.gillespie_sir_once(value, 1.0, 1, 10)


@pytest.mark.parametrize(
    ("gamma", "pattern"),
    [
        (False, "finite number"),
        (0.0, "positive"),
        (-1.0, "positive"),
    ],
)
def test_recovery_rate_must_be_strictly_positive(gamma, pattern):
    with pytest.raises(ValueError, match=pattern):
        sir.gillespie_sir_once(0.5, gamma, 1, 10)


@pytest.mark.parametrize(
    ("population", "pattern"),
    [
        (0, "in 1.."),
        (-1, "in 1.."),
        (True, "must be an integer"),
        (1.5, "must be an integer"),
        (2_000_000, "in 1.."),
    ],
)
def test_population_requires_finite_integer_within_explicit_hard_limit(population, pattern):
    with pytest.raises(ValueError, match=pattern):
        sir.gillespie_sir_once(0.1, 0.2, 1, population)


@pytest.mark.parametrize(
    ("seed_cases", "pattern"),
    [
        (True, "must be an integer"),
        (-1, "in 0.."),
        (2.5, "must be an integer"),
    ],
)
def test_initial_cases_cannot_be_fabricated_or_negative(seed_cases, pattern):
    with pytest.raises(ValueError, match=pattern):
        sir.gillespie_sir_once(0.1, 0.2, seed_cases, 10)


def test_initial_infectious_cases_cannot_exceed_declared_population():
    with pytest.raises(ValueError, match="I0 must not exceed N"):
        sir.gillespie_sir_once(0.1, 0.2, 11, 10)


@pytest.mark.parametrize(
    ("altered", "pattern"),
    [
        ({"beta": sir.MAX_RATE + 1.0}, "hard numerical limits"),
        ({"gamma": sir.MAX_RATE + 1.0}, "hard numerical limits"),
        ({"t_max": sir.MAX_HORIZON + 1.0}, "hard numerical limits"),
        ({"t_max": 0.0}, "positive"),
    ],
)
def test_transition_rate_and_observation_horizon_have_separate_hard_ceiling(altered, pattern):
    data = dict(beta=0.2, gamma=0.1, I0=1, N=10, t_max=2.0)
    data.update(altered)
    with pytest.raises(ValueError, match=pattern):
        sir.gillespie_sir_once(**data)


@pytest.mark.parametrize("delay", [float("nan"), float("inf"), -1.0])
def test_unphysical_rng_wait_does_not_produce_reported_epidemic_event(delay):
    with pytest.raises(ValueError, match="invalid Gillespie waiting time"):
        sir.gillespie_sir_once(0.2, 0.1, 1, 10, t_max=1.0, rng=FixedWait(delay))


def test_builtin_rng_path_respects_zero_initial_cases_with_no_events():
    out = sir.gillespie_sir_once(0.2, 0.1, 0, 100, t_max=1.0, rng=None)
    assert out["final_R"] == 0
    assert out["total_infected"] == 0
    assert out["events"] == 0


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 99, 2026])
def test_seeded_real_gillespie_path_conserves_populations_at_finite_horizon(seed):
    out = sir.gillespie_sir_once(0.6, 0.15, 3, 100, t_max=2.0, rng=np.random.default_rng(seed))
    recovered = out["final_R"]
    total = out["total_infected"]
    infected_now = total - recovered
    susceptible = 100 - total
    assert recovered >= 0
    assert infected_now >= 0
    assert susceptible >= 0
    assert recovered + infected_now + susceptible == 100
    assert 3 <= total <= 100
    assert out["peak_I"] >= 3
    assert 0 <= out["t_end"] <= 2.0
    assert out["events"] <= 200


def test_nonfinite_transition_rate_is_fail_closed_under_backend_fault_injection(monkeypatch):
    true_finite = math.isfinite
    counter = {"n": 0}

    def fault_at_transition(value):
        counter["n"] += 1
        if counter["n"] == 4:
            return False
        return true_finite(value)

    monkeypatch.setattr(sir.math, "isfinite", fault_at_transition)
    with pytest.raises(ValueError, match="non-finite Gillespie transition rate"):
        sir.gillespie_sir_once(0.2, 0.1, 1, 10, t_max=1.0, rng=FixedWait(0.1))


def test_zero_total_transition_rate_exits_without_creating_an_event(monkeypatch):
    original = sir._real

    def failed_backend(value, name, *, positive=False):
        if name == "gamma":
            return 0.0
        return original(value, name, positive=positive)

    # Defensive fault injection: normal validation prohibits gamma = 0.
    monkeypatch.setattr(sir, "_real", failed_backend)
    out = sir.gillespie_sir_once(0.0, 1.0, 1, 10, t_max=1.0, rng=FixedWait(0.1))
    assert out["events"] == 0
    assert out["final_R"] == 0
    assert out["total_infected"] == 1
