"""Documented interface counts must match the code that serves them.

The README states the CLI subcommand count, the ``model --action`` count and the
MCP tool count in prose. Those numbers drifted from the installed handlers once
already (#105), so they are pinned here against the real parser and the real
tool registry instead of being trusted as text.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from axiomize import cli
from axiomize.server import mcp_server

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _section(text: str, heading_fragment: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("### ") and heading_fragment in line:
            start = index + 1
            break
    if start is None:
        raise AssertionError(f"section {heading_fragment!r} not found")
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("### "):
            end = index
            break
    return "\n".join(lines[start:end])


def _backticked(text: str) -> set[str]:
    return set(re.findall(r"`([a-z][a-z0-9_-]*)`", text))


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise AssertionError("parser has no subcommands")


def _model_actions() -> set[str]:
    parser = cli.build_parser()
    model_parser = _subparsers_action(parser).choices["model"]
    for action in model_parser._actions:
        if action.dest == "action":
            return set(action.choices or ())
    raise AssertionError("model subcommand has no --action choices")


def _model_tool_suffixes(tools: set[str]) -> set[str]:
    return {name.split(".", 1)[1] for name in tools if ".model_" in name}


def test_documented_subcommands_match_the_parser() -> None:
    readme = _read("README.md")
    documented = _backticked(_section(readme, "subcommands ("))
    choices = set(_subparsers_action(cli.build_parser()).choices)
    assert documented == choices, (
        f"README subcommands {sorted(documented)} != parser {sorted(choices)}"
    )
    assert len(choices) == 14
    assert "14 subcommands" in readme
    assert "14 subcommands" in _read("docs/integrations.md")


def test_documented_model_actions_match_the_parser() -> None:
    readme = _read("README.md")
    documented = _backticked(_section(readme, "model --action"))
    actions = _model_actions()
    assert documented == actions, (
        f"README model actions {sorted(documented)} != parser {sorted(actions)}"
    )
    assert len(actions) == 16


def test_documented_mcp_tool_counts_match_the_registry() -> None:
    readme = _read("README.md")
    integrations = _read("docs/integrations.md")
    tools = set(mcp_server._TOOL_SCHEMAS)
    model_tools = {name for name in tools if ".model_" in name}

    assert len(tools) == 35, f"registry has {len(tools)} tools, README says 35"
    assert len(model_tools) == 16, f"registry has {len(model_tools)} model_* tools, README says 16"
    assert "**35 tools**" in readme
    assert re.search(r"^35 tools,", integrations, re.MULTILINE)
    assert "Sixteen are `axiomize.model_*`" in readme
    assert "other nineteen names" in readme

    other_nineteen = {
        "intake", "solve", "simulate", "fit_model", "validate", "cross_validate",
        "sensitivity_analysis", "uncertainty_analysis", "falsify", "compare_models",
        "experiment_design", "clean_data", "compare_runs", "inspect_run",
        "reproduce", "get_capabilities", "list_tools", "select_tools", "workflow_policy",
    }
    suffixes = {name.split(".", 1)[1] for name in tools}
    assert suffixes - _model_tool_suffixes(tools) == other_nineteen


def test_documented_console_script_count_matches_pyproject() -> None:
    readme = _read("README.md")
    pyproject = _read("pyproject.toml")
    scripts_block = pyproject.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    scripts = re.findall(r"^([a-z0-9-]+) = ", scripts_block, re.MULTILINE)
    assert len(scripts) == 8, scripts
    assert "Console scripts (8)" in readme
