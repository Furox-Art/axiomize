"""Dispatch all scientific CLI model actions and preserve explicit consent flags.

These are interface-routing tests with isolated service spies. Actual scientific
numerics are independently exercised by native model and benchmark suites.
"""
from __future__ import annotations

import argparse
import json

import pytest

from axiomize import cli
from axiomize.application import advanced_services, general_services, surrogate_services

_CLI_MODEL_ACTIONS = [
    ("plan", general_services, "model_plan_service"),
    ("validate", general_services, "model_validate_service"),
    ("simulate", general_services, "model_simulate_service"),
    ("fit", general_services, "model_fit_service"),
    ("compare", general_services, "model_compare_service"),
    ("repair", general_services, "model_repair_service"),
    ("export", general_services, "model_export_service"),
    ("stability", general_services, "model_stability_service"),
    ("validity", general_services, "model_validity_service"),
    ("discover", general_services, "model_discovery_service"),
    ("experiment-design", general_services, "experiment_design_service"),
    ("uncertainty", advanced_services, "model_uncertainty_service"),
    ("bifurcation", advanced_services, "model_bifurcation_service"),
    ("numerical-verify", advanced_services, "model_numerical_verification_service"),
    ("stop-check", advanced_services, "model_stopping_service"),
    ("surrogate", surrogate_services, "model_surrogate_service"),
]


def _args(file, action, *, heavy=False, repair=False, migration=False, output=None):
    return argparse.Namespace(
        input_json=str(file), action=action, approve_heavy=heavy,
        approve_repair=repair, approve_migration=migration, json=output,
    )


@pytest.mark.parametrize("action,module,service", _CLI_MODEL_ACTIONS)
def test_every_model_cli_action_reaches_named_backend(
    monkeypatch, tmp_path, capsys, action, module, service,
):
    payload = {"domain": "physics", "metadata": {"id": 12}}
    file = tmp_path / "request.json"
    file.write_text(json.dumps(payload))
    received = []
    monkeypatch.setattr(module, service, lambda request: (
        received.append(dict(request)) or {"status": "PASS", "route": action}
    ))
    assert cli.cmd_model(_args(file, action)) == 0
    assert received == [payload]
    out = json.loads(capsys.readouterr().out)
    assert out == {"status": "PASS", "route": action}


@pytest.mark.parametrize("flag,attribute", [
    ("approve_heavy", "approve_heavy"),
    ("approve_repair", "approve_repair"),
    ("approve_migration", "approve_migration"),
])
def test_model_cli_accepts_only_explicit_consent_not_guesswork(
    tmp_path, monkeypatch, capsys, flag, attribute,
):
    file = tmp_path / "request.json"
    file.write_text('{"domain":"general"}')
    calls = []
    monkeypatch.setattr(general_services, "model_plan_service", lambda request: (
        calls.append(dict(request)) or {"status": "PASS"}
    ))
    kwargs = {attribute: True}
    args = _args(file, "plan", heavy=kwargs.get("approve_heavy", False),
                 repair=kwargs.get("approve_repair", False),
                 migration=kwargs.get("approve_migration", False))
    assert cli.cmd_model(args) == 0
    assert calls[0][flag] is True
    assert not any(key in calls[0] for key in {
        "approve_heavy", "approve_repair", "approve_migration",
    } - {flag})
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"


@pytest.mark.parametrize("decision", ["FAIL", "SURROGATE_REJECTED", "OUT_OF_DOMAIN"])
def test_model_cli_preserves_rejected_evidence_as_nonzero_exit(
    tmp_path, monkeypatch, capsys, decision,
):
    file = tmp_path / "request.json"
    file.write_text('{"domain":"general"}')
    monkeypatch.setattr(general_services, "model_plan_service", lambda _: {
        "status": decision, "reason": "unverified model",
    })
    assert cli.cmd_model(_args(file, "plan")) == 1
    assert json.loads(capsys.readouterr().out)["status"] == decision


def test_model_cli_writes_exact_json_report_to_user_chosen_path(
    tmp_path, monkeypatch, capsys,
):
    file = tmp_path / "request.json"
    file.write_text("{}")
    output = tmp_path / "report.json"
    monkeypatch.setattr(general_services, "model_validate_service", lambda _: {
        "status": "UNVERIFIED", "scientific_claim": None,
    })
    assert cli.cmd_model(_args(file, "validate", output=str(output))) == 0
    assert json.loads(output.read_text()) == {
        "status": "UNVERIFIED", "scientific_claim": None,
    }
    assert str(output) in capsys.readouterr().out


def test_model_cli_missing_input_refuses_implicit_model(tmp_path):
    args = _args(tmp_path / "missing.json", "plan")
    with pytest.raises(FileNotFoundError):
        cli.cmd_model(args)


def test_policy_cli_preserves_explicit_permissions_and_signals(tmp_path, monkeypatch, capsys):
    from axiomize.application import services

    source = tmp_path / "signals.json"
    source.write_text('{"uncertain":true}')
    received = []
    monkeypatch.setattr(services, "workflow_policy_service", lambda request: (
        received.append(request) or {"status": "UNVERIFIED"}
    ))
    args = argparse.Namespace(
        signals_json=str(source), question_mode="adaptive",
        allow_subtasks=True, allow_repeat=False, allow_extra_paid_calls=False,
        json=None,
    )
    assert cli.cmd_policy(args) == 0
    assert received[0]["permissions"] == {
        "allow_spawn_subtasks": True,
        "allow_repeat_alternative_methods": False,
        "allow_extra_paid_model_calls": False,
    }
    assert received[0]["signals"] == {"uncertain": True}
    assert json.loads(capsys.readouterr().out)["status"] == "UNVERIFIED"


def test_intake_cli_does_not_invent_authorization(tmp_path, monkeypatch, capsys):
    from axiomize.application import services

    calls = []
    monkeypatch.setattr(services, "intake_service", lambda request: (
        calls.append(request) or {"status": "QUESTION_REQUIRED"}
    ))
    args = argparse.Namespace(
        idea="test explicit physical law", context_json=None, signals_json=None,
        question_mode="one_by_one", preferred_question_mode="one_by_one",
        rigor="research", allow_subtasks=False, allow_repeat=False,
        allow_extra_paid_calls=False, json=None,
    )
    assert cli.cmd_intake(args) == 0
    assert calls[0]["idea"] == "test explicit physical law"
    assert calls[0]["permissions"] == {
        "allow_spawn_subtasks": False,
        "allow_repeat_alternative_methods": False,
        "allow_extra_paid_model_calls": False,
    }
    assert json.loads(capsys.readouterr().out)["status"] == "QUESTION_REQUIRED"


@pytest.mark.parametrize("status,exit_code", [("PASS", 0), ("FAIL", 1)])
def test_validate_sir_cli_refuses_to_report_failed_science_as_success(
    monkeypatch, capsys, status, exit_code,
):
    from axiomize.application import services

    monkeypatch.setattr(services, "validate_sir_service", lambda _: {
        "status": status,
    })
    args = argparse.Namespace(
        beta=0.3, gamma=0.1, I0=10, N=1000, days=3, json=None,
    )
    assert cli.cmd_validate(args) == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_sir_cli_forwards_complete_numeric_input(monkeypatch, capsys):
    from axiomize.application import services

    received = []
    monkeypatch.setattr(services, "solve_sir_service", lambda request: (
        received.append(request) or {"status": "PASS"}
    ))
    args = argparse.Namespace(
        beta=0.4, gamma=0.2, I0=5.0, N=400, days=8.0, json=None,
    )
    assert cli.cmd_solve(args) == 0
    assert received == [{"beta": 0.4, "gamma": 0.2, "I0": 5, "N": 400, "days": 8.0}]
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"


def test_run_comparison_cli_passes_both_explicit_paths(monkeypatch, capsys):
    from axiomize.application import services

    received = []
    monkeypatch.setattr(services, "compare_runs_service", lambda request: (
        received.append(request) or {"differences": {"model": "changed"}}
    ))
    args = argparse.Namespace(before_dir="/tmp/run-A", after_dir="/tmp/run-B", json=None)
    assert cli.cmd_compare_runs(args) == 0
    assert received == [{"before_dir": "/tmp/run-A", "after_dir": "/tmp/run-B"}]
    assert json.loads(capsys.readouterr().out)["differences"]["model"] == "changed"


@pytest.mark.parametrize("status,exit_code", [("PASS", 0), ("FAIL", 1)])
def test_cli_benchmark_exit_reflects_actual_registered_result(
    monkeypatch, capsys, status, exit_code,
):
    from axiomize import benchmark_suite

    monkeypatch.setattr(benchmark_suite, "run_suite", lambda: {
        "status": status, "passed": 11 if status == "FAIL" else 12,
        "total": 12,
    })
    assert cli.cmd_benchmark(None) == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_cli_tools_marks_unavailable_backend_explicitly(monkeypatch, capsys):
    from axiomize.application import services

    monkeypatch.setattr(services, "tools_service", lambda: {
        "tools": {"lean": {"available": False, "version": "none", "reason": "not installed"},
                  "sympy": {"available": True, "version": "1.14", "reason": ""}},
    })
    assert cli.cmd_tools(None) == 0
    output = capsys.readouterr().out
    assert "UNAVAILABLE (not installed)" in output
    assert "sympy" in output and "available" in output


def test_cli_capabilities_are_machine_readable_and_provenance_preserving(
    monkeypatch, capsys,
):
    from axiomize.application import services

    monkeypatch.setattr(services, "capabilities_service", lambda: {
        "runtime": {"lean": "TOOL_UNAVAILABLE"},
    })
    assert cli.cmd_capabilities(None) == 0
    assert json.loads(capsys.readouterr().out)["runtime"]["lean"] == "TOOL_UNAVAILABLE"


def test_cli_reproduce_reports_stored_results_and_input_hash(tmp_path, capsys):
    from axiomize.runs.state import RunState

    root = tmp_path / "run"
    state = RunState(parameters={"k": 0.4}, results={"observed": [1, 2]})
    state.save(root)
    assert cli.cmd_reproduce(argparse.Namespace(run_id=str(root))) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["results"] == {"observed": [1, 2]}
    assert output["input_hash"] == state.input_hash()
