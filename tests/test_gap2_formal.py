"""GAP-2 Lean/formal adapter gercek entegrasyon testleri.

Adapter sabitlenmis gercek Lean toolchain'i kullanir: dogru teorem
PASS, yanlis teorem FAIL, zincir yoksa TOOL_UNAVAILABLE. Hicbir dalda
sahte ispat uretilemez. Yavas testler degil: her `lean` cagrisi
saniyeler surer (core Lean, mathlib yok).
"""

import pytest

from axiomize.formal.lean_adapter import LeanAdapter
from axiomize.tools.base import ScientificTool
from axiomize.validation.status import ValidationStatus

TRUE_THEOREM = "theorem t_true : 2 + 2 = 4 := rfl"
FALSE_THEOREM = "theorem t_false : 2 + 2 = 5 := rfl"


def test_implements_scientific_tool_interface():
    assert issubclass(LeanAdapter, ScientificTool)
    adapter = LeanAdapter()
    assert callable(adapter.validate_input)
    assert callable(adapter.execute)


def test_availability_matches_reality():
    import shutil
    import subprocess

    meta = LeanAdapter.availability()
    if shutil.which("elan") is None:
        assert meta.available is False
        return
    probe = subprocess.run(
        ["elan", "run", LeanAdapter.TOOLCHAIN, "lean", "--version"],
        capture_output=True, text=True, timeout=60, shell=False)
    assert meta.available is (probe.returncode == 0)
    if meta.available:
        assert "4.30.0" in meta.version


def test_true_theorem_proved_by_real_lean():
    adapter = LeanAdapter()
    if not LeanAdapter.availability().available:
        pytest.skip("lean toolchain yok; TOOL_UNAVAILABLE yolu gecerli")
    result = adapter.execute({"theorem": TRUE_THEOREM})
    assert result["status"] == ValidationStatus.PASS.value
    assert result["proved"] is True


def test_false_theorem_rejected_by_real_lean():
    adapter = LeanAdapter()
    if not LeanAdapter.availability().available:
        pytest.skip("lean toolchain yok; TOOL_UNAVAILABLE yolu gecerli")
    result = adapter.execute({"theorem": FALSE_THEOREM})
    assert result["status"] == ValidationStatus.FAIL.value
    assert result["proved"] is False
    assert result.get("lean_output")


def test_missing_toolchain_reports_unavailable_honestly(monkeypatch):
    adapter = LeanAdapter()
    monkeypatch.setattr(
        LeanAdapter, "TOOLCHAIN", "leanprover/lean4:v0.0.0-yok")
    meta = LeanAdapter.availability()
    assert meta.available is False
    result = adapter.execute({"theorem": TRUE_THEOREM})
    assert result["status"] == ValidationStatus.TOOL_UNAVAILABLE.value
    assert result["proved"] is False
    assert result["proof"] is None


def test_no_fake_pass_or_proof():
    adapter = LeanAdapter()
    result = adapter.execute({"theorem": FALSE_THEOREM})
    assert result["status"] != ValidationStatus.PASS.value
    assert not (result["status"] == ValidationStatus.PASS.value
                and result.get("proved") is not True)


def test_validate_input_rejects_bad_payload():
    adapter = LeanAdapter()
    with pytest.raises(ValueError):
        adapter.execute({})
    with pytest.raises(ValueError):
        adapter.execute({"theorem": "   "})
