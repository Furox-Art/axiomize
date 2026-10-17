"""Direct and dispatcher causal executors share the identical validated backend."""

from __future__ import annotations

import pytest

from axiomize import advanced_family_engine as advanced
from axiomize.causal_engine import estimate_causal_model
from axiomize.model_ir import ModelFamily, ModelIR


def _model(*, identified: bool):
    metadata = {
        "causal": {
            "treatment": "t",
            "outcome": "y",
            "data": {
                "t": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
                "y": [1.0, 3.0, 1.0, 3.0, 1.0, 3.0, 1.0, 3.0],
            },
            "identification": {"randomized": True} if identified else {},
        }
    }
    return ModelIR(
        name="identification",
        domain="epidemiology",
        family=ModelFamily.CAUSAL,
        variables=[],
        parameters=[],
        equations=[],
        metadata=metadata,
    )


def test_advanced_causal_alias_is_canonical_validated_backend():
    assert advanced._estimate_causal is estimate_causal_model


@pytest.mark.parametrize("identified", [True, False])
def test_native_dispatch_consistent_with_shared_causal_executor(identified):
    model = _model(identified=identified)
    direct = estimate_causal_model(model, t_span=(0.0, 1.0), points=10, parameter_overrides=None, seed=5)
    dispatched = advanced.simulate_advanced_family(
        model,
        t_span=(0.0, 1.0),
        points=10,
        parameter_overrides=None,
        seed=5,
        validate_fn=lambda _model, *, result: {"status": "PASS", "checks": []},
        simulate_fn=lambda *_args, **_kwargs: {},
    )
    if identified:
        assert direct["status"] == "PASS"
        assert direct["causal_effect"]["estimate"] == pytest.approx(2.0)
        assert dispatched["causal_effect"] == direct["causal_effect"]
    else:
        assert direct["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"
        assert dispatched["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"
        assert "causal_effect" not in dispatched
