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

import importlib.util
import json
import re
import xml.etree.ElementTree as ET
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


# ---------------------------------------------------------------------------
# M-4: an auth failure and a missing record are different failures
# ---------------------------------------------------------------------------


def _rest_server(tmp_path: Path, *, auth_token: str | None = None):
    import threading

    from axiomize.server.rest_server import start_server

    server = start_server("127.0.0.1", 0, run_root=tmp_path, auth_token=auth_token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _get(server, path: str, *, token: str | None = None):
    import urllib.error
    import urllib.request

    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_missing_run_is_404_not_an_auth_error(tmp_path: Path) -> None:
    """A token-authenticated caller asking for an absent run gets a 404."""
    server = _rest_server(tmp_path, auth_token="a-very-long-research-token")
    try:
        status, body = _get(server, "/runs/does-not-exist", token="a-very-long-research-token")
        assert status == 404
        assert body == {"error": "run not found or failed integrity checks"}
    finally:
        server.shutdown()
        server.server_close()


def test_failed_auth_is_401_even_for_a_missing_run(tmp_path: Path) -> None:
    """A missing record must not mask an auth failure, in either direction."""
    server = _rest_server(tmp_path, auth_token="a-very-long-research-token")
    try:
        status, body = _get(server, "/runs/does-not-exist", token="wrong-token-entirely")
        assert status == 401
        assert body == {"error": "unauthorized"}
        # ... and the same missing record is still a 404 for the right caller.
        assert _get(server, "/runs/does-not-exist", token="a-very-long-research-token")[0] == 404
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# M-5: parallel batch worker bounds are enforced at config load
# ---------------------------------------------------------------------------


def _sweep_module():
    path = ROOT / "skills" / "axiomize" / "tools" / "parallel_sweep.py"
    spec = importlib.util.spec_from_file_location("axiomize_parallel_sweep_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("workers", [0, -1, -32, 33, 64, 1000, 10 ** 9])
def test_absurd_worker_counts_are_rejected_at_config_load(workers: int) -> None:
    module = _sweep_module()
    with pytest.raises(ValueError, match="workers must be between 1 and"):
        module._bounded_workers(workers)


@pytest.mark.parametrize("workers", [True, False, None, "4", "many", 2.5, 0.5])
def test_non_integer_worker_requests_are_rejected(workers) -> None:
    module = _sweep_module()
    with pytest.raises(ValueError, match="workers must be"):
        module._bounded_workers(workers)


def test_worker_bounds_accept_the_declared_range() -> None:
    module = _sweep_module()
    assert module._bounded_workers(1) == 1
    assert module._bounded_workers(module.MAX_WORKERS) == module.MAX_WORKERS
    assert module._bounded_workers(4.0) == 4


def test_resolved_default_worker_count_is_also_bounded() -> None:
    module = _sweep_module()
    assert 1 <= module._default_workers() <= module.MAX_WORKERS


def test_dispatch_worker_count_is_never_zero() -> None:
    module = _sweep_module()
    assert module._dispatch_workers(8, 28) == 8
    assert module._dispatch_workers(8, 4) == 4
    # An empty batch must not hand 0 to ProcessPoolExecutor.
    assert module._dispatch_workers(8, 0) == 1
    assert module._dispatch_workers(8, -3) == 1


# ---------------------------------------------------------------------------
# M-7 / M-10: the release workflow must not carry a silent packaging gap, and
# the provenance guard must stay wired in beside the other version guards
# ---------------------------------------------------------------------------


def test_windows_runner_produces_a_preserved_packaging_artifact() -> None:
    """Windows must not be a build-and-discard-only platform in the release path.

    The workflow YAML is checked as text, not with PyYAML: the CI environment
    intentionally does not install it, and a packaging-gap guard that cannot run
    is the very class of silent gap this test exists to catch.
    """
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    # The matrix of platform jobs must cover Windows explicitly.
    assert re.search(r"^\s*os:\s*\[.*windows-latest", release, re.MULTILINE), (
        "no release-path job runs on Windows"
    )
    assert "macos-latest" in release and "ubuntu-latest" in release
    # And the platform job must keep the wheel it built instead of discarding it.
    lines = release.splitlines()
    platforms = [
        index for index, line in enumerate(lines)
        if "Preserve the platform packaging artifact" in line
    ]
    assert platforms, "no release-path job preserves the wheels it builds"
    for index in platforms:
        window = "\n".join(lines[index:index + 16])
        assert "actions/upload-artifact" in window, "the preservation step does not upload"
        assert re.search(r"^\s*path:\s*dist/\*\.whl\b", window, re.MULTILINE), (
            "the upload does not preserve the built wheel"
        )
        assert "if-no-files-found: error" in window, "an upload would silently drop artifacts"
        assert re.search(r"^\s*name:\s*platform-wheel-", window, re.MULTILINE), (
            "the preserved artifact is not named per platform"
        )


@pytest.mark.parametrize("workflow", ["ci.yml", "release.yml"])
def test_provenance_claim_guard_is_registered_beside_the_version_guards(workflow: str) -> None:
    """An unregistered guard cannot fail on drift, so registration is asserted."""
    document = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    assert "check_provenance_claims.py" in document
    assert ".github/scripts/check_release_contract.py" in document


# ---------------------------------------------------------------------------
# K-2: exported numbers come back bit-exact, with their units
# ---------------------------------------------------------------------------


def _precision_model() -> ModelIR:
    """A model whose values are not representable in short decimal form."""
    return ModelIR.from_dict({
        "schema_version": "1.0",
        "name": "precision",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": "day",
        "variables": [
            {"name": "x", "unit": "dimensionless", "initial": 0.1234567890123456789},
            {"name": "tiny", "unit": "1/day", "initial": 5e-324},
        ],
        "parameters": [
            {"name": "k", "unit": "1/day", "value": 3.141592653589793238462643383279},
            {"name": "floor", "unit": "1/day", "value": 1e-300},
        ],
        "equations": [
            {"target": "x", "expression": "-k*x", "kind": "derivative"},
            {"target": "tiny", "expression": "-floor*tiny", "kind": "derivative"},
        ],
    })


def test_sbml_export_round_trips_values_and_units_losslessly() -> None:
    """Every exported number must parse back to the identical float.

    ``repr`` of a Python float is the shortest round-tripping decimal, so the
    SBML ``initialConcentration``/``value`` attributes and the units carried in
    the axiomize annotation are read back and compared bit-exactly. A
    re-serialization that formats to fewer digits would break here.
    """
    model = _precision_model()
    out = export_model(model, format="sbml-l3v2")
    # This fixture includes the smallest positive IEEE-754 subnormal.  The
    # libSBML numeric lexer can reject its initialConcentration as outside the
    # normal double range.  Keep the exact literal and never call an invalid
    # native export PASS; an unvalidated XML-only export is NOT_RUN instead.
    try:
        import libsbml
    except ImportError:
        assert out["status"] == "PASS"
        assert out["validation"]["schema_validation"] == "NOT_RUN"
    else:
        parsed = libsbml.readSBMLFromString(out["content"])
        native_errors = int(parsed.getNumErrors())
        assert out["validation"]["libsbml_errors"] == native_errors
        assert out["status"] == ("FAIL" if native_errors else "PASS")
        assert out["validation"]["schema_validation"] == out["status"]
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    sbml_ns = "{http://www.sbml.org/sbml/level3/version2/core}"
    axiomize_ns = "{https://github.com/Furox-Art/axiomize/model-ir}"

    by_id = {
        element.get("id"): element.get("initialConcentration")
        for element in root.iter(f"{sbml_ns}species")
    }
    for variable in model.variables:
        assert float(by_id[variable.name]) == float(variable.initial)

    by_param_id = {
        element.get("id"): element.get("value")
        for element in root.iter(f"{sbml_ns}parameter")
    }
    for parameter in model.parameters:
        assert float(by_param_id[parameter.name]) == float(parameter.value)

    annotation = json.loads(root.find(f".//{axiomize_ns}modelIR").text)
    assert annotation["independent_unit"] == model.independent_unit
    assert annotation["variable_units"] == {v.name: v.unit for v in model.variables}
    assert annotation["parameter_units"] == {p.name: p.unit for p in model.parameters}


def test_normal_range_sbml_numbers_validate_natively_without_loss() -> None:
    # A boundary value inside IEEE normal range must be accepted by the native
    # SBML parser and preserve its exact binary64 value in an XML attribute.
    payload = _precision_model().to_dict()
    smallest_normal = float.fromhex("0x1.0p-1022")
    for variable in payload["variables"]:
        if variable["name"] == "tiny":
            variable["initial"] = smallest_normal
    model = ModelIR.from_dict(payload)
    out = export_model(model, format="sbml-l3v2")
    assert out["status"] == "PASS", out["validation"]
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    species_ns = "{http://www.sbml.org/sbml/level3/version2/core}species"
    values = {item.get("id"): item.get("initialConcentration") for item in root.iter(species_ns)}
    assert float(values["tiny"]) == smallest_normal
    if out["validation"]["schema_validation"] != "NOT_RUN":
        assert out["validation"]["schema_validation"] == "PASS"
        assert out["validation"]["libsbml_errors"] == 0


def test_cellml_and_modelica_export_round_trip_values_losslessly() -> None:
    model = _precision_model()
    for fmt in ("cellml-2.0", "modelica-3.6"):
        out = export_model(model, format=fmt)
        assert out["status"] == "PASS", (fmt, out)
        content = out["content"]
        for parameter in model.parameters:
            assert repr(float(parameter.value)) in content, (fmt, parameter.name)
        for variable in model.variables:
            assert repr(float(variable.initial)) in content, (fmt, variable.name)


def test_json_export_round_trip_is_bit_exact() -> None:
    model = _precision_model()
    content = export_model(model, format="json")["content"]
    restored = ModelIR.from_dict(json.loads(content))
    assert [v.initial for v in restored.variables] == [v.initial for v in model.variables]
    assert [p.value for p in restored.parameters] == [p.value for p in model.parameters]


def test_notebook_export_round_trips_the_model_it_claims_to() -> None:
    """The rerunnable notebook must reconstruct the exact same Model IR."""
    import ast

    model = _precision_model()
    out = export_model(model, format="notebook")
    notebook = out["notebook"]
    # ``content`` is the published artifact; it must describe the same notebook
    # object the caller was handed, including the compat alias.
    assert out["content"] == json.dumps(notebook, indent=2)

    source = "".join(notebook["cells"][1]["source"])

    def _is_json_loads(call: ast.Call) -> bool:
        func = call.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "loads"
            and isinstance(func.value, ast.Name)
            and func.value.id == "json"
        )

    literals = [
        ast.literal_eval(node.args[0])
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and _is_json_loads(node)
    ]
    assert literals, "notebook does not embed a literal Model IR payload"
    restored = ModelIR.from_dict(json.loads(literals[0]))
    assert [v.initial for v in restored.variables] == [v.initial for v in model.variables]
    assert [p.value for p in restored.parameters] == [p.value for p in model.parameters]
    assert restored.to_dict() == model.to_dict()
