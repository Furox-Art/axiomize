"""Execute packaged benchmark grading and CSV preflight against real files.

No proxy grading or fabricated datasets are counted as science: every success
is derived from actual file contents and parser outcomes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

import benchmark_runner
import csv_check


def _cases_file(root: Path, records):
    target=root/"cases.json"
    target.write_text(json.dumps({"cases":records}),encoding="utf-8")
    return target


def _one_case():
    return {
        "id":"real-report", "prompt":"Inspect real evidence",
        "must_contain":["network"],"expected_archetype":"network",
        "min_lenses_built":1,
    }


def _report_content():
    return (
        "# Reproducibility report\n"
        "## 4. Perspective models\n"
        "### Lens A: network\n"
        "Measured a network.\n"
        "| Unit |\n"
        "| m | exo\n"
        "Violation consequence: invalid inference\n"
        "Falsifiability: independent measurements required\n"
    )


def test_packaged_benchmark_reads_and_indexes_actual_json(tmp_path):
    file=_cases_file(tmp_path,[_one_case()])
    result=benchmark_runner.load_cases(str(file))
    assert list(result)==["real-report"]
    assert result["real-report"]["min_lenses_built"]==1


def test_no_missing_dataset_is_implicitly_accepted(tmp_path):
    with pytest.raises(SystemExit,match="dataset not found"):
        benchmark_runner.load_cases("")
    with pytest.raises(SystemExit,match="not found"):
        benchmark_runner.load_cases(str(tmp_path/"missing.json"))


def test_malformed_json_does_not_create_fabricated_benchmark(tmp_path):
    file=tmp_path/"cases.json"
    file.write_text("{invalid:json",encoding="utf-8")
    with pytest.raises(SystemExit,match="invalid JSON"):
        benchmark_runner.load_cases(str(file))


@pytest.mark.parametrize("payload,expected_error",[
    ([], "cases array"),
    ({"cases":"invalid"}, "cases array"),
    ({"cases":[{"id":""}]}, "non-empty string id"),
    ({"cases":[{"id":"one","must_contain":"wrong"}]}, "invalid must_contain"),
    ({"cases":[{"id":"one","min_lenses_built":True}]}, "min_lenses_built"),
    ({"cases":[{"id":"one","min_lenses_built":-1}]}, "min_lenses_built"),
    ({"cases":[{"id":"one"},{"id":"one"}]}, "duplicate benchmark case id"),
])
def test_benchmark_registry_rejects_invalid_ground_truth(tmp_path,payload,expected_error):
    path=tmp_path/"dataset.json"
    path.write_text(json.dumps(payload),encoding="utf-8")
    with pytest.raises(SystemExit,match=expected_error):
        benchmark_runner.load_cases(str(path))


def test_benchmark_case_limit_is_checked_before_processing(tmp_path,monkeypatch):
    monkeypatch.setattr(benchmark_runner,"MAX_CASES",1)
    file=_cases_file(tmp_path,[{"id":"one"},{"id":"two"}])
    with pytest.raises(SystemExit,match="hard case limit"):
        benchmark_runner.load_cases(str(file))


def test_benchmark_byte_limit_rejects_oversized_dataset(tmp_path,monkeypatch):
    monkeypatch.setattr(benchmark_runner,"MAX_BENCHMARK_BYTES",8)
    path=_cases_file(tmp_path,[_one_case()])
    with pytest.raises(SystemExit,match="hard size limit"):
        benchmark_runner.load_cases(str(path))


def test_benchmark_literal_alternatives_cannot_execute_regex_metacharacters():
    assert benchmark_runner._literal_alt_present("network","network architecture")
    assert not benchmark_runner._literal_alt_present("(x+)+","xxx")
    assert benchmark_runner._literal_alt_present("","anything") is False


def test_grading_is_directly_grounded_in_report_content():
    checks,lenses=benchmark_runner.grade(_report_content(),_one_case())
    assert lenses==1
    assert checks
    assert all(checks.values())


def test_false_grading_cannot_claim_missing_falsifiability_or_units():
    checks,lenses=benchmark_runner.grade("network",_one_case())
    assert lenses==0
    assert any(value is False for value in checks.values())
    assert checks["falsifiability section"] is False


def test_grading_refuses_nontext_report():
    with pytest.raises(ValueError,match="report must be text"):
        benchmark_runner.grade(None,_one_case())


@pytest.mark.parametrize("oracle",[
    None,
    {"keyword":"R0"},
    {"keyword":"R0","expected":2,"tolerance":-1},
])
def test_numeric_oracle_must_be_explicit_validated_metadata(oracle):
    case={**_one_case(),"numeric_oracle":oracle}
    with pytest.raises((ValueError,TypeError),match="numeric_oracle|numeric oracle"):
        benchmark_runner.grade("network",case)


def test_numeric_oracle_measures_an_actual_reported_number():
    case={**_one_case(),"numeric_oracle":{
        "keyword":"R0","expected":2.25,"tolerance":0.001,
    }}
    checks,_=benchmark_runner.grade(_report_content()+"R0: 2.250\n",case)
    assert any("numeric oracle" in key and passed for key,passed in checks.items())


def test_packaged_grader_cli_reports_per_case_score_and_success(tmp_path,monkeypatch,capsys):
    casefile=_cases_file(tmp_path,[_one_case()])
    report=tmp_path/"report.md"
    report.write_text(_report_content(),encoding="utf-8")
    monkeypatch.setattr(sys,"argv",["axiomize-benchmark",
        "--benchmarks",str(casefile),"--case","real-report","--report",str(report)])
    assert benchmark_runner.main()==0
    assert "automated score:" in capsys.readouterr().out


def test_packaged_grader_cli_refuses_unknown_case(tmp_path,monkeypatch,capsys):
    casefile=_cases_file(tmp_path,[_one_case()])
    monkeypatch.setattr(sys,"argv",["axiomize-benchmark",
        "--benchmarks",str(casefile),"--case","absent"])
    assert benchmark_runner.main()==1
    assert "unknown case" in capsys.readouterr().out


def _csv(tmp_path,content):
    path=tmp_path/"observed.csv"
    path.write_text(content,encoding="utf-8")
    return path


def test_actual_csv_preflight_returns_unchanged_measurements(tmp_path):
    path=_csv(tmp_path,"time,value\n0,2\n1,3\n2,5\n")
    time_name,value_name,t,y=csv_check.load(str(path),"time","value")
    assert (time_name,value_name)==("time","value")
    np.testing.assert_allclose(t,[0,1,2])
    np.testing.assert_allclose(y,[2,3,5])


@pytest.mark.parametrize("content,field,pattern",[
    ("","time","is empty"),
    ("time,value\n0,1\n","missing","not found"),
    ("time,value\n0,1\n","time","--value-col is required"),
    ("time,value\n0,1\n","value","--time-col is required"),
    ("time,value\nno,2\n","time","cannot parse"),
    ("time,value\n0,nan\n","time","must be finite"),
    ("time,value\n0,1\n1\n","time",""),
])
def test_csv_preflight_rejects_corrupt_or_missing_data(tmp_path,content,field,pattern):
    path=_csv(tmp_path,content)
    if field=="missing":
        call=(str(path),"missing","value")
    elif field=="value":
        call=(str(path),None,"value")
    elif field=="time" and pattern.startswith("--value-col"):
        call=(str(path),"time",None)
    else:
        call=(str(path),"time","value")
    if pattern:
        with pytest.raises(SystemExit,match=pattern):
            csv_check.load(*call)
    else:
        result=csv_check.load(*call)
        assert len(result[2])==1


def test_csv_preflight_missing_file_is_not_treated_as_empty_dataset(tmp_path):
    with pytest.raises(SystemExit,match="cannot stat"):
        csv_check.load(str(tmp_path/"not-there.csv"),"time","value")


def test_csv_preflight_cli_accepts_real_monotone_positive_observations(tmp_path,monkeypatch,capsys):
    content="time,value\n"+"".join(f"{i},{i+1}\n" for i in range(10))
    path=_csv(tmp_path,content)
    monkeypatch.setattr(sys,"argv",["axiomize-csv-check","--data",str(path),
        "--time-col","time","--value-col","value"])
    assert csv_check.main()==0
    assert "PASS - safe to calibrate" in capsys.readouterr().out


def test_csv_preflight_cli_explicitly_fails_duplicate_or_short_series(tmp_path,monkeypatch,capsys):
    path=_csv(tmp_path,"time,value\n0,1\n0,1\n1,2\n")
    monkeypatch.setattr(sys,"argv",["axiomize-csv-check","--data",str(path),
        "--time-col","time","--value-col","value"])
    assert csv_check.main()==1
    assert "FAIL - clean data" in capsys.readouterr().out


def test_csv_preflight_cli_rejects_unphysical_outlier_threshold(tmp_path,monkeypatch):
    path=_csv(tmp_path,"time,value\n0,1\n1,2\n")
    monkeypatch.setattr(sys,"argv",["axiomize-csv-check","--data",str(path),
        "--time-col","time","--value-col","value","--z-outlier","0"])
    with pytest.raises(SystemExit):
        csv_check.main()
