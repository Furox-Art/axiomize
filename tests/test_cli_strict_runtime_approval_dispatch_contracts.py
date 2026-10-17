"""CLI roundtrips preserve consent, recorded data, and scientific failure status."""

from __future__ import annotations

import json

import pytest

from axiomize import cli


def file_json(tmp_path, payload):
    p = tmp_path / "input.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


@pytest.mark.parametrize(
    ("data", "pattern"),
    [
        ([], "must contain a JSON object"),
        (False, "must contain a JSON object"),
        ("nonobject", "must contain a JSON object"),
    ],
)
def test_cli_json_requires_an_actual_structured_object(tmp_path, data, pattern):
    with pytest.raises(ValueError, match=pattern):
        cli._load_object(file_json(tmp_path, data))


def test_cli_hard_file_size_budget_checks_before_loading_json(tmp_path):
    target = tmp_path / "oversize.json"
    with target.open("wb") as handle:
        handle.truncate(cli.MAX_RUN_JSON_BYTES + 1)
    with pytest.raises(ValueError, match="hard JSON input limit"):
        cli._load_object(str(target))


def test_cli_missing_json_input_explicitly_maps_to_empty_payload():
    assert cli._load_object(None) == {}


def test_cli_json_output_is_stable_and_never_writes_nan(tmp_path, capsys):
    filename = tmp_path / "out.json"
    assert cli._dump({"status": "UNVERIFIED", "count": 2}, str(filename)) == 0
    assert json.loads(filename.read_text()) == {"status": "UNVERIFIED", "count": 2}
    assert "wrote" in capsys.readouterr().out
    with pytest.raises(ValueError, match="Out of range float values"):
        cli._dump({"invalid": float("nan")}, None)


def test_cli_plan_preserves_need_model_ir_without_invented_dynamic_equations(tmp_path, capsys):
    rc = cli.main(["model", "--input-json", file_json(tmp_path, {"idea": "growth"}), "--action", "plan"])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "NEEDS_MODEL_IR"
    assert "model_ir" not in result


def test_cli_model_approval_flags_do_not_spontaneously_enable_expensive_computation(tmp_path, monkeypatch, capsys):
    from axiomize.application import general_services

    captured = []

    def stub(payload):
        captured.append(payload)
        return {"status": "APPROVAL_REQUIRED"}

    monkeypatch.setattr(general_services, "model_plan_service", stub)
    path = file_json(tmp_path, {"idea": "observe"})
    assert cli.main(["model", "--input-json", path, "--action", "plan"]) == 0
    assert captured[-1] == {"idea": "observe"}
    assert (
        cli.main(
            [
                "model",
                "--input-json",
                path,
                "--action",
                "plan",
                "--approve-heavy",
                "--approve-migration",
                "--approve-repair",
            ]
        )
        == 0
    )
    assert captured[-1]["approve_heavy"] is True
    assert captured[-1]["approve_migration"] is True
    assert captured[-1]["approve_repair"] is True


@pytest.mark.parametrize("bad_status", ["FAIL", "SURROGATE_REJECTED", "OUT_OF_DOMAIN"])
def test_cli_model_fails_closed_on_reported_scientific_rejection(tmp_path, monkeypatch, bad_status):
    from axiomize.application import general_services

    monkeypatch.setattr(general_services, "model_plan_service", lambda payload: {"status": bad_status})
    assert cli.main(["model", "--input-json", file_json(tmp_path, {"idea": "test"}), "--action", "plan"]) == 1


def test_cli_clean_data_keeps_auditable_nonfinite_exclusion(tmp_path, capsys):
    path = file_json(tmp_path, {"t": [0.0, 1.0, 2.0], "y": [1.0, None, 3.0]})
    # Invalid JSON null is a malformed numeric observation, not a missingness model.
    with pytest.raises(ValueError):
        cli.main(["clean-data", "--input-json", path])
    path = file_json(tmp_path, {"t": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]})
    assert cli.main(["clean-data", "--input-json", path]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cleaned_t"] == [0.0, 1.0, 2.0]
    assert result["cleaned_y"] == [1.0, 2.0, 3.0]
    assert result["audit"]


def test_cli_clean_data_explicit_option_preserves_order_when_chosen(tmp_path, capsys):
    path = file_json(tmp_path, {"t": [2.0, 1.0, 3.0], "y": [2.0, 1.0, 3.0]})
    assert cli.main(["clean-data", "--input-json", path, "--keep-order"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cleaned_t"] == [2.0, 1.0, 3.0]


@pytest.mark.parametrize(
    "content",
    [
        "t,y\n",
        "t,y\n1,2\n",
        "t,y\n1\n2,3\n",
    ],
)
def test_cli_fit_csv_refuses_missing_observations_or_columns(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(ValueError, match="at least two|needs at least two"):
        cli.main(["fit", "--data", str(path)])


def test_cli_fit_actual_logistic_csv_executes_native_scipy(tmp_path, capsys):
    import numpy as np

    tt = np.linspace(0, 7, 15)
    yy = 100 / (1 + 9 * np.exp(-0.5 * tt))
    path = tmp_path / "observations.csv"
    path.write_text("t,y\n" + "".join(f"{t},{y}\n" for t, y in zip(tt, yy, strict=True)))
    assert cli.main(["fit", "--data", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["success"] is True
    assert result["params"]["r"]["value"] == pytest.approx(0.5, abs=0.03)


def test_cli_serve_forwards_safely_confined_runtime_options_and_closes(monkeypatch, capsys):
    from axiomize.server import rest_server

    calls = []

    class FakeServer:
        server_address = ("127.0.0.1", 9000)

        def serve_forever(self):
            calls.append("serve")
            raise KeyboardInterrupt

        def server_close(self):
            calls.append("close")

    def fake_start(*args, **kw):
        calls.append((args, kw))
        return FakeServer()

    monkeypatch.setattr(rest_server, "start_server", fake_start)
    monkeypatch.setenv("AXIOMIZE_REST_TOKEN", "secret")
    assert cli.main(["serve", "--host", "127.0.0.1", "--port", "9000", "--max-concurrent-requests", "4"]) == 0
    args, kw = calls[0]
    assert kw["auth_token"] == "secret"
    assert kw["max_concurrent_requests"] == 4
    assert calls[-2:] == ["serve", "close"]
    assert "127.0.0.1:9000" in capsys.readouterr().out


def test_cli_mcp_does_not_implicitly_spawn_network_listener(monkeypatch):
    from axiomize.server import mcp_server

    seen = []
    monkeypatch.setattr(mcp_server, "serve_stdio", lambda *, run_root: seen.append(run_root))
    assert cli.main(["mcp", "--run-root", "/safe"]) == 0
    assert seen == ["/safe"]


def test_cli_argument_parser_requires_documented_subcommand():
    with pytest.raises(SystemExit) as err:
        cli.main([])
    assert err.value.code == 2
