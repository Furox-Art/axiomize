"""Exact bounded Metropolis-Hastings and conjugate normal input contracts."""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.bayesian import mh
from axiomize.limits import MAX_MODEL_PARAMETERS


def posterior(x):
    return -0.5 * float(np.sum(np.square(x)))


@pytest.mark.parametrize("bad", [None, "not numeric", object()])
def test_proposal_width_refuses_non_numeric_evidence(bad):
    with pytest.raises(ValueError, match="proposal_std must be numeric"):
        mh.metropolis_hastings(posterior, np.array([0.0]), n_samples=8,
                              burn=2, proposal_std=bad)


@pytest.mark.parametrize("bad", [np.array([]), np.ones((2, 2)), 0.0])
def test_initial_chain_must_be_nonempty_vector(bad):
    with pytest.raises(ValueError, match="non-empty 1D numeric array"):
        mh.metropolis_hastings(posterior, bad, n_samples=8, burn=2)


def test_bayesian_chain_rejects_overdimensioned_parameters():
    with pytest.raises(ValueError, match="x0 dimension exceeds"):
        mh.metropolis_hastings(
            posterior, np.zeros(MAX_MODEL_PARAMETERS + 1), n_samples=8, burn=2,
        )


@pytest.mark.parametrize("bad", [[float("nan")], [float("inf")]])
def test_nonfinite_chain_start_never_enters_inference(bad):
    with pytest.raises(ValueError, match="only finite values"):
        mh.metropolis_hastings(posterior, np.asarray(bad), n_samples=8, burn=2)


@pytest.mark.parametrize("bad", [[], [[0, 1], [2, 3]], 3.0])
def test_mean_posterior_refuses_invalid_observation_shape(bad):
    with pytest.raises(ValueError, match="non-empty 1D array"):
        mh.normal_mean_posterior(bad, sigma=1.0, n_samples=8, burn=2)


@pytest.mark.parametrize("bad", [[0.0, float("nan")], [float("inf"), 2.0]])
def test_mean_posterior_refuses_nonfinite_measurements(bad):
    with pytest.raises(ValueError, match="only finite values"):
        mh.normal_mean_posterior(bad, sigma=1.0, n_samples=8, burn=2)


@pytest.mark.parametrize("bad", [None, object(), "not a prior mean"])
def test_prior_mean_must_be_real_numeric(bad):
    with pytest.raises(ValueError, match="prior_mean must be numeric"):
        mh.normal_mean_posterior([1.0, 2.0], sigma=1.0, prior_mean=bad,
                                 n_samples=8, burn=2)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_prior_mean_must_be_finite(bad):
    with pytest.raises(ValueError, match="prior_mean must be finite"):
        mh.normal_mean_posterior([1.0, 2.0], sigma=1.0, prior_mean=bad,
                                 n_samples=8, burn=2)


def test_seeded_chain_is_reproducible_with_actual_log_posterior():
    one = mh.metropolis_hastings(posterior, np.array([0.0]), n_samples=50,
                                 burn=10, seed=19)
    two = mh.metropolis_hastings(posterior, np.array([0.0]), n_samples=50,
                                 burn=10, seed=19)
    np.testing.assert_array_equal(one["samples"], two["samples"])
    assert 0 <= one["acceptance_rate"] <= 1
    assert all(math.isfinite(float(v)) for v in one["mean"])


def test_nonfinite_proposal_density_does_not_corrupt_chain():
    def disallow_all_proposals(x):
        if x[0] != 0:
            return float("nan")
        return 0.0

    outcome = mh.metropolis_hastings(
        disallow_all_proposals, np.asarray([0.0]), n_samples=20, burn=5, seed=3,
    )
    assert outcome["acceptance_rate"] == 0.0
    np.testing.assert_array_equal(outcome["samples"], np.zeros((15, 1)))


def test_actual_normal_mean_posterior_draws_are_reproducible_and_finite():
    values = [1.8, 2.0, 2.2, 2.4]
    args = dict(sigma=0.5, prior_mean=0.0, prior_std=3.0, n_samples=300, burn=60, seed=11)
    left = mh.normal_mean_posterior(values, **args)
    right = mh.normal_mean_posterior(values, **args)
    assert left == right
    assert left["mean"] == pytest.approx(2.1, abs=0.4)
    assert 0 <= left["acceptance_rate"] <= 1
    assert left["ci95"][0] < left["ci95"][1]
    assert math.isfinite(left["std"])
