"""GAP-2 Lean/formal adapter iskelet testleri.

Adapter Lean kurulu olmadigi icin her zaman TOOL_UNAVAILABLE donmeli
ve asla sahte PASS / uydurma ispat uretmemelidir.
"""

import pytest

from axiomize.formal.lean_adapter import LeanAdapter
from axiomize.tools.base import ScientificTool
from axiomize.validation.status import ValidationStatus


def test_implements_scientific_tool_interface():
    assert issubclass(LeanAdapter, ScientificTool)
    adapter = LeanAdapter()
    assert callable(adapter.validate_input)
    assert callable(adapter.execute)


def test_availability_always_false():
    meta = LeanAdapter.availability()
    assert meta.available is False


def test_execute_returns_tool_unavailable():
    adapter = LeanAdapter()
    result = adapter.execute({"theorem": "forall n : Nat, n + 0 = n"})
    assert result["status"] == ValidationStatus.TOOL_UNAVAILABLE.value
    assert result["status"] == "TOOL_UNAVAILABLE"


def test_no_fake_pass_or_proof():
    adapter = LeanAdapter()
    result = adapter.execute({"theorem": "forall n : Nat, n + 0 = n"})
    assert result["status"] != ValidationStatus.PASS.value
    assert result.get("proved") is False
    assert result.get("proof") is None


def test_validate_input_rejects_bad_payload():
    adapter = LeanAdapter()
    with pytest.raises(ValueError):
        adapter.execute({})
    with pytest.raises(ValueError):
        adapter.execute({"theorem": "   "})
