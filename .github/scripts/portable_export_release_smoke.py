#!/usr/bin/env python3
"""Installed-wheel smoke test for versioned portable scientific exports."""

from __future__ import annotations

import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


MODEL = {
    "schema_version": "1.0",
    "name": "release-decay",
    "domain": "physics",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "day",
    "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
    "parameters": [{"name": "k", "unit": "1/day", "value": 0.5}],
    "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    "assumptions": ["release smoke"],
}


def run_export(fmt: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        request = Path(td) / "request.json"
        request.write_text(json.dumps({"model_ir": MODEL, "format": fmt}), encoding="utf-8")
        proc = subprocess.run(
            ["axiomize", "model", "--action", "export", "--input-json", str(request)],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{fmt} export failed rc={proc.returncode}: {proc.stderr}\n{proc.stdout}")
        return json.loads(proc.stdout)


def main() -> int:
    sbml = run_export("sbml-l3v2")
    assert sbml["status"] == "PASS"
    assert sbml["standard"] == "SBML Level 3 Version 2 Core"
    root = ET.fromstring(sbml["content"].split("\n", 1)[1])
    assert root.tag.endswith("}sbml") and root.attrib == {"level": "3", "version": "2"}

    cellml = run_export("cellml-2.0")
    assert cellml["status"] == "PASS"
    assert cellml["standard"] == "CellML 2.0"
    root = ET.fromstring(cellml["content"].split("\n", 1)[1])
    assert root.tag.endswith("}model")

    notebook = run_export("ipynb")
    assert notebook["status"] == "PASS"
    decoded = json.loads(notebook["content"])
    assert decoded["nbformat"] == 4
    assert decoded["metadata"]["axiomize"]["schema_version"] == "1.0"

    print("RESULT: PASS - installed versioned portable export contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
