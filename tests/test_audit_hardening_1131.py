"""Regression coverage for the current repository-audit hardening pass.

Two defects are pinned here:

K-1  ``simulate_model`` ran a model that had not passed the unit and
     declared-vs-actual dimension checks the rest of the engine applies, so a
     dimensionally inconsistent Model IR simulated and produced numbers.
L-2  the deterministic domain/family hinting matched lexicon terms as raw
     substrings, so ``ecosystem`` counted as ``system``, ``enforced`` as
     ``force`` and ``graph theory`` as ``ph ``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axiomize.dimensional_engine import ModelDimensionMismatch
from axiomize.general_engine import (
    export_model,
    infer_domain,
    recommend_model_families,
    simulate_model,
)
from axiomize.general_engine_core import simulate_model as core_simulate_model
from axiomize.model_ir import ModelIR

ROOT = Path(__file__).resolve().parents[1]


def _model(*, k_unit: str = "1/day", variable_unit: str = "dimensionless",
           independent_unit: str = "day") -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0",
        "name": "decay",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": independent_unit,
        "variables": [{"name": "x", "unit": variable_unit, "initial": 1.0}],
        "parameters": [{"name": "k", "unit": k_unit, "value": 0.5}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


# ---------------------------------------------------------------------------
# K-1: simulation is a closed unit/dimensional gate
# ---------------------------------------------------------------------------


def test_dimension_mismatched_model_cannot_simulate() -> None:
    """dx/dt = -k*x with k dimensionless is dimensionally inconsistent."""
    model = _model(k_unit="dimensionless")
    with pytest.raises(ModelDimensionMismatch) as excinfo:
        simulate_model(model, t_span=(0.0, 1.0))
    failed = excinfo.value.failed_checks
    assert [check["name"] for check in failed] == ["equation_dimension:x"]
    assert "expected={'T': -1.0}; basis=d(x)/d(t)" in failed[0]["detail"]
    assert excinfo.value.validation["status"] == "FAIL"


def test_core_simulate_model_applies_the_same_gate() -> None:
    """The core executor (not just the facade) is fail-closed."""
    model = _model(k_unit="dimensionless")
    with pytest.raises(ModelDimensionMismatch):
        core_simulate_model(model, t_span=(0.0, 1.0))


def test_unknown_unit_blocks_simulation_as_a_typed_error() -> None:
    """An unparseable unit is a FAIL check, never an uncaught parser crash."""
    model = _model(variable_unit="lightyear")
    with pytest.raises(ModelDimensionMismatch) as excinfo:
        simulate_model(model, t_span=(0.0, 1.0))
    names = {check["name"] for check in excinfo.value.failed_checks}
    assert "variable_unit:x" in names
    assert "equation_dimension_engine" in names


def test_dimensionally_consistent_model_still_simulates() -> None:
    """The gate must not reject a model the engine is willing to validate."""
    result = simulate_model(_model(), t_span=(0.0, 1.0), points=20)
    assert result["status"] == "PASS"
    assert result["states"]["x"][-1] == pytest.approx(0.6065307, rel=1e-4)


def test_validation_payload_reaches_the_raised_error() -> None:
    """A caller can render the failing checks without re-running validation."""
    model = _model(k_unit="dimensionless")
    with pytest.raises(ModelDimensionMismatch) as excinfo:
        simulate_model(model, t_span=(0.0, 1.0))
    validation = excinfo.value.validation
    assert "equation_dimension_checks" in validation
    assert validation["equation_dimension_checks"][0]["status"] == "FAIL"


# ---------------------------------------------------------------------------
# L-2: term matching is token-anchored, not substring-anchored
# ---------------------------------------------------------------------------


def test_substring_terms_do_not_classify_as_their_container() -> None:
    """The audited case: a term that is a substring of another word."""
    # "system" is a substring of "ecosystem"; "force" of "enforced"/"reinforced".
    assert infer_domain("the ecosystem recovered after the fire")["domain"] == "ecology"
    assert "system" not in infer_domain("the ecosystem recovered after the fire")["matched_terms"]
    assert infer_domain("enforced contract terms")["domain"] == "general"
    assert infer_domain("reinforced concrete beam")["domain"] == "general"
    # "ph " used to be satisfied by the "ph " inside "graph theory".
    assert infer_domain("graph theory for the network")["domain"] == "general"
    # A prefix is not a word: "prior" must not be satisfied by "prioritize".
    assert "bayesian" not in [row["family"] for row in recommend_model_families(idea="we prioritize throughput")]
    # "gene" must not be satisfied by "generic".
    assert infer_domain("a generic transfer function")["domain"] == "general"


def test_word_boundary_matching_still_hits_inflected_and_stemmed_forms() -> None:
    """Plurals, verb forms and intentional stems must keep matching."""
    assert infer_domain("oscillation of a quantum field")["domain"] == "physics"
    assert infer_domain("epidemiology of an infectious disease")["domain"] == "epidemiology"
    assert infer_domain("a brisk market with high volatility")["domain"] == "finance"
    assert infer_domain("systems and control theory")["domain"] == "engineering"
    assert "control" in [row["family"] for row in recommend_model_families(idea="a control system for the reactor")]
    assert "agent_based" in [row["family"] for row in recommend_model_families(idea="agent-based crowd model")]


def test_multiphysics_phrase_is_not_promoted_by_a_substring() -> None:
    """A bare embedded 'multiphysics' substring must not force rank 1."""
    families = [row["family"] for row in recommend_model_families(idea="first-order decay of a tracer")]
    assert "multiphysics" not in families
    promoted = recommend_model_families(idea="coupled physics of a multiphysics reactor")
    assert promoted[0]["family"] == "multiphysics"
    assert promoted[0]["rank"] == 1
