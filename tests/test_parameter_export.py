from __future__ import annotations

import json

import pytest

from axiomize.cli import main
from axiomize.parameters.export import export_parameter_table, parse_parameter_table


REPORT = """# Model

## Active Parameter Table

| Symbol | Name | Unit | Exo/Endo | Range (typical) | Source | Sensitivity | In model(s) |
|--------|------|------|----------|------------------|--------|-------------|-------------|
| β | transmission rate | 1/day | exo | 0.1-0.5 | lit. | high | det, stoch |
| γ | recovery rate | 1/day | exo | 0.05-0.2 | lit. | medium | det, stoch |
| I(t) | infected count | persons | endo | ≥ 0 | derived | low | det, stoch |

## Comparison
| Model | Score |
|-------|-------|
| SIR | 9 |
"""


def test_parse_parameter_table_schema_and_rows() -> None:
    out = parse_parameter_table(REPORT)
    assert out["schema"] == "axiomize.parameter-table.v1"
    assert out["count"] == 3
    assert out["parameters"][0] == {
        "symbol": "β",
        "name": "transmission rate",
        "unit": "1/day",
        "kind": "exo",
        "range": "0.1-0.5",
        "source": "lit.",
        "sensitivity": "high",
        "models": "det, stoch",
    }
    assert out["parameters"][2]["symbol"] == "I(t)"


def test_parse_parameter_table_does_not_match_other_tables() -> None:
    with pytest.raises(ValueError, match="active parameter table not found"):
        parse_parameter_table("| Model | Score |\n|---|---|\n| SIR | 9 |")


def test_parse_parameter_table_rejects_empty_table() -> None:
    text = """| Symbol | Name | Unit | Exo/Endo | Range | Source | Sensitivity | In model(s) |
|---|---|---|---|---|---|---|---|
"""
    with pytest.raises(ValueError, match="empty"):
        parse_parameter_table(text)


def test_export_parameter_table_writes_utf8_json(tmp_path) -> None:
    src = tmp_path / "report.md"
    dst = tmp_path / "params.json"
    src.write_text(REPORT, encoding="utf-8")

    payload = export_parameter_table(src, dst)
    loaded = json.loads(dst.read_text(encoding="utf-8"))

    assert loaded == payload
    assert loaded["parameters"][0]["symbol"] == "β"


def test_cli_export_parameters(tmp_path, capsys) -> None:
    src = tmp_path / "report.md"
    dst = tmp_path / "params.json"
    src.write_text(REPORT, encoding="utf-8")

    rc = main(["export-parameters", str(src), "--json", str(dst)])

    assert rc == 0
    assert json.loads(dst.read_text(encoding="utf-8"))["count"] == 3
    assert f"wrote {dst}" in capsys.readouterr().out
