"""Portable CI regression: real skipped or xfail cases must fail status checks."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "assert_no_skips.py"
spec = importlib.util.spec_from_file_location("axiomize_zero_skips", SCRIPT)
assert spec and spec.loader
skip_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skip_gate)


def _verify(tmp_path: Path, content: str):
    path = tmp_path / "test-report.xml"
    path.write_text(content, encoding="utf-8")
    return skip_gate.verify_report(path)


def test_real_executed_cases_are_accepted(tmp_path):
    status, detail = _verify(tmp_path,
        "<testsuites><testsuite tests=\"2\"><testcase classname=\"a\" name=\"one\"/>"
        "<testcase classname=\"a\" name=\"two\"/></testsuite></testsuites>")
    assert status == 0
    assert "2 executed testcases" in detail
    assert "zero skipped" in detail


@pytest.mark.parametrize("marker", [
    "<skipped message=\"unavailable backend\"/>",
    "<skipped type=\"pytest.xfail\"/>",
])
def test_skip_and_xfail_are_fatal_on_the_actual_junit_structure(tmp_path, marker):
    status, detail = _verify(tmp_path,
        "<testsuite tests=\"1\"><testcase classname=\"science\" name=\"proof\">"
        + marker + "</testcase></testsuite>")
    assert status == 1
    assert "science::proof" in detail
    assert "1 testcases skipped/xfail" in detail


def test_empty_or_invalid_reports_are_never_treated_as_zero_skips(tmp_path):
    for content in ("", "<testsuite>", "<testsuite/>", "<unexpected/>"):
        status, _ = _verify(tmp_path, content)
        assert status == 1, content


def test_missing_report_cannot_count_as_a_green_gate(tmp_path):
    status, detail = skip_gate.verify_report(tmp_path / "absent.xml")
    assert status == 1
    assert "unreadable" in detail
