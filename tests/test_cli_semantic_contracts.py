"""CLI routes are verified as thin adapters, with explicit consent and exit codes."""

from __future__ import annotations

import json

import pytest

from axiomize import cli


@pytest.mark.parametrize(
    ("content", "pattern"),
    [
        ("[]", "must contain a JSON object"),
        ('"text"', "must contain a JSON object"),
        ("null", "must contain a JSON object"),
    ],
)
def test_cli_json_file_must_hold_structured_scientific_request(tmp_path, content, pattern):
    source = tmp_path / "input.json"
    source.write_text(content)
    with pytest.raises(ValueError, match=pattern):
        cli._load_object(str(source))


def test_cli_json_input_empty_filename_means_no_implicit_model():
    assert cli._load_object(None) == {}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('{"idea":"oscillator"}', {"idea": "oscillator"}),
        ("{}", {}),
    ],
)
def test_cli_json_read_uses_declared_file(tmp_path, body, expected):
    file = tmp_path / "input.json"
    file.write_text(body)
    assert cli._load_object(str(file)) == expected


def test_cli_dump_never_serializes_nan_as_fake_json_success(tmp_path):
    with pytest.raises(ValueError, match="Out of range"):
        cli._dump({"value": float("nan")}, str(tmp_path / "report.json"))


def test_cli_dump_json_file_is_reusable_scientific_evidence(tmp_path, capsys):
    destination = tmp_path / "report.json"
    assert cli._dump({"value": 2.0, "tag": "precise"}, str(destination)) == 0
    assert json.loads(destination.read_text()) == {"value": 2.0, "tag": "precise"}
    assert "wrote" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("action", "module", "method"),
    [
        ("plan", "general_services", "model_plan_service"),
        ("validate", "general_services", "model_validate_service"),
        ("simulate", "general_services", "model_simulate_service"),
        ("fit", "general_services", "model_fit_service"),
        ("compare", "general_services", "model_compare_service"),
        ("repair", "general_services", "model_repair_service"),
        ("export", "general_services", "model_export_service"),
        ("stability", "general_services", "model_stability_service"),
        ("validity", "general_services", "model_validity_service"),
        ("discover", "general_services", "model_discovery_service"),
        ("experiment-design", "general_services", "experiment_design_service"),
        ("uncertainty", "advanced_services", "model_uncertainty_service"),
        ("bifurcation", "advanced_services", "model_bifurcation_service"),
        ("numerical-verify", "advanced_services", "model_numerical_verification_service"),
        ("stop-check", "advanced_services", "model_stopping_service"),
        ("surrogate", "surrogate_services", "model_surrogate_service"),
    ],
)
def test_cli_model_action_never_dispatches_to_other_scientific_tool(
    tmp_path, capsys, action, module, method, monkeypatch
):
    import importlib

    source = tmp_path / "request.json"
    source.write_text('{"model_ir":{"name":"exact"}}')
    backend = importlib.import_module("axiomize.application." + module)
    monkeypatch.setattr(backend, method, lambda payload: {"called": method, "payload": payload, "status": "PASS"})
    code = cli.main(
        [
            "model",
            "--input-json",
            str(source),
            "--action",
            action,
        ]
    )
    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["called"] == method
    assert output["payload"] == {"model_ir": {"name": "exact"}}


def test_cli_user_approval_flags_are_only_set_when_explicit(tmp_path, capsys, monkeypatch):
    from axiomize.application import general_services

    file = tmp_path / "input.json"
    file.write_text('{"approve_heavy":false,"approve_migration":false}')
    monkeypatch.setattr(general_services, "model_plan_service", lambda payload: payload)
    code = cli.main(
        [
            "model",
            "--input-json",
            str(file),
            "--approve-heavy",
            "--approve-migration",
            "--approve-repair",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["approve_heavy"] is True
    assert payload["approve_migration"] is True
    assert payload["approve_repair"] is True


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        ("PASS", 0),
        ("APPROVAL_REQUIRED", 0),
        ("UNVERIFIED", 0),
        ("FAIL", 1),
        ("SURROGATE_REJECTED", 1),
        ("OUT_OF_DOMAIN", 1),
    ],
)
def test_cli_scientific_failure_status_maps_to_nonzero_exit(tmp_path, capsys, monkeypatch, status, exit_code):
    from axiomize.application import general_services

    file = tmp_path / "input.json"
    file.write_text("{}")
    monkeypatch.setattr(general_services, "model_plan_service", lambda p: {"status": status})
    assert cli.main(["model", "--input-json", str(file)]) == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == status


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("time,value\n", "at least two data rows"),
        ("time,value\n0,1\n", "at least two data rows"),
        ("time,value\n0\n1,2\n", "needs at least two columns"),
    ],
)
def test_cli_csv_invalid_scientific_series_refused(tmp_path, contents, message):
    file = tmp_path / "observations.csv"
    file.write_text(contents)
    with pytest.raises(ValueError, match=message):
        cli.main(["fit", "--data", str(file)])


def test_cli_csv_fit_routes_numeric_arrays_without_changing_units(tmp_path, capsys, monkeypatch):
    from axiomize.application import services

    file = tmp_path / "observations.csv"
    file.write_text("time,value\n0,1\n1,2\n2,3\n")
    monkeypatch.setattr(services, "fit_logistic_service", lambda p: p)
    assert cli.main(["fit", "--data", str(file)]) == 0
    assert json.loads(capsys.readouterr().out) == {"t": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]}


def test_cli_clean_data_does_not_reinterpret_user_flags(tmp_path, capsys, monkeypatch):
    from axiomize.application import services

    file = tmp_path / "input.json"
    file.write_text('{"t":[0,1],"y":[1,2]}')
    monkeypatch.setattr(services, "clean_data_service", lambda p: p)
    assert (
        cli.main(
            [
                "clean-data",
                "--input-json",
                str(file),
                "--reject-nonfinite",
                "--keep-order",
                "--duplicate-policy",
                "first",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["drop_nonfinite"] is False
    assert result["sort_time"] is False
    assert result["duplicate_policy"] == "first"


@pytest.mark.parametrize(
    ("command", "method"),
    [
        ("solve", "solve_sir_service"),
        ("validate", "validate_sir_service"),
    ],
)
def test_legacy_sir_cli_preserves_explicit_population(tmp_path, capsys, monkeypatch, command, method):
    from axiomize.application import services

    monkeypatch.setattr(services, method, lambda p: {"status": "PASS", **p})
    assert cli.main([command, "--N", "2000", "--I0", "2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["N"] == 2000
    assert payload["I0"] == 2.0


def test_cli_validation_failure_is_process_failure(capsys, monkeypatch):
    from axiomize.application import services

    monkeypatch.setattr(services, "validate_sir_service", lambda p: {"status": "FAIL"})
    assert cli.main(["validate", "--N", "100"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"


def test_cli_benchmark_failure_cannot_be_reported_as_success(capsys, monkeypatch):
    from axiomize import benchmark_suite

    monkeypatch.setattr(benchmark_suite, "run_suite", lambda: {"status": "FAIL"})
    assert cli.main(["benchmark"]) == 1


def test_cli_mcp_uses_explicit_run_root(monkeypatch):
    from axiomize.server import mcp_server

    roots = []
    monkeypatch.setattr(mcp_server, "serve_stdio", lambda *, run_root: roots.append(run_root))
    assert cli.main(["mcp", "--run-root", "/tmp/recordings"]) == 0
    assert roots == ["/tmp/recordings"]


def test_cli_rest_serve_closes_server_after_interrupt(monkeypatch):
    from axiomize.server import rest_server

    calls = []

    class FakeServer:
        server_address = ("127.0.0.1", 5050)

        def serve_forever(self):
            calls.append("serve")
            raise KeyboardInterrupt

        def server_close(self):
            calls.append("close")

    monkeypatch.setattr(rest_server, "start_server", lambda *a, **kw: FakeServer())
    assert cli.main(["serve", "--port", "5050"]) == 0
    assert calls == ["serve", "close"]


def test_cli_policy_permissions_default_to_no_extra_paid_calls(capsys, monkeypatch):
    from axiomize.application import services

    monkeypatch.setattr(services, "workflow_policy_service", lambda p: p)
    assert cli.main(["policy"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["permissions"] == {
        "allow_spawn_subtasks": False,
        "allow_repeat_alternative_methods": False,
        "allow_extra_paid_model_calls": False,
    }
