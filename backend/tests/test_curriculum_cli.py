"""CLI output must not contain completed-course details or input paths."""

from __future__ import annotations

import json

import pytest

from app.curriculum import CurriculumNormalizationError, normalize_completed_courses
from app.curriculum.__main__ import main


def test_cli_prints_counts_without_private_values(monkeypatch, capsys) -> None:
    records = [{
        "course_id": "DEMO-PRIVATE-ID",
        "course_name": "DEMO-PRIVATE-NAME",
        "credit": 2,
        "semester": "DEMO-PRIVATE-SEMESTER",
        "passed": True,
        "course_type": None,
        "course_id_status": "已确认",
        "id_match_source": "DEMO-PRIVATE-CATALOG",
    }, {
        "course_id": None,
        "course_name": "DEMO-PRIVATE-OTHER-NAME",
        "credit": 1,
        "semester": "DEMO-PRIVATE-SEMESTER",
        "passed": False,
        "course_type": None,
        "course_id_status": "待确认",
        "id_match_source": None,
    }]
    courses = normalize_completed_courses(records, source_id="DEMO-PRIVATE-SOURCE")
    monkeypatch.setattr("app.curriculum.__main__.load_completed_courses_xlsx", lambda *a, **kw: courses)

    assert main(["/DEMO-PRIVATE-PATH/input.xlsx", "--source-id", "DEMO-PRIVATE-SOURCE"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "records": 2, "confirmed_course_ids": 1, "pending_course_ids": 1,
    }
    assert captured.err == ""
    assert "DEMO-PRIVATE" not in captured.out


def test_cli_reports_validation_failure_without_partial_counts(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise CurriculumNormalizationError("row 2: credit: invalid number")

    monkeypatch.setattr("app.curriculum.__main__.load_completed_courses_xlsx", fail)
    assert main(["/DEMO-PRIVATE-PATH/input.xlsx", "--source-id", "DEMO-SOURCE"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"error": "row 2: credit: invalid number"}
    assert "DEMO-PRIVATE-PATH" not in captured.err


def test_cli_handles_empty_valid_course_data(monkeypatch, capsys) -> None:
    monkeypatch.setattr("app.curriculum.__main__.load_completed_courses_xlsx", lambda *a, **kw: ())
    assert main(["/DEMO-PATH/input.xlsx", "--source-id", "DEMO-SOURCE"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "records": 0, "confirmed_course_ids": 0, "pending_course_ids": 0,
    }


@pytest.mark.parametrize("argv", [
    ["/DEMO-PRIVATE-PATH/input.xlsx", "--source-id", "DEMO-SOURCE", "/DEMO-PRIVATE-PATH/extra.xlsx"],
    ["/DEMO-PRIVATE-PATH/input.xlsx", "--source-id", "DEMO-SOURCE", "--DEMO-PRIVATE-OPTION"],
    ["/DEMO-PRIVATE-PATH/input.xlsx"],
    [],
])
def test_argument_errors_do_not_echo_private_arguments(argv, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "参数无效，请运行 --help 查看用法。\n"
    assert "DEMO-PRIVATE" not in captured.err


def test_demo_cli_computes_tasks_with_explicit_mock_marker(capsys) -> None:
    assert main(["--demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["data_source"] == "mock"
    assert {task["status"] for task in result["makeup_tasks"]} == {
        "satisfied", "required", "possibly_equivalent", "manual_confirmation",
    }


def test_case_cli_only_prints_statistics_for_private_input(tmp_path, capsys) -> None:
    from app.curriculum.case import DEMO_CASE_PATH

    payload = json.loads(DEMO_CASE_PATH.read_text())
    payload["data_source"] = "real"
    payload["old"]["major"] = "DEMO-PRIVATE-MAJOR"
    payload["old"]["source_id"] = "DEMO-PRIVATE-OLD-SOURCE"
    payload["new"]["source_id"] = "DEMO-PRIVATE-NEW-SOURCE"
    payload["completed"]["source_id"] = "DEMO-PRIVATE-COMPLETED-SOURCE"
    payload["rules"]["completed_source_id"] = "DEMO-PRIVATE-COMPLETED-SOURCE"
    payload["rules"]["evidence"] = "DEMO-PRIVATE-RULE-EVIDENCE"
    payload["old"]["completeness_evidence"] = "DEMO-PRIVATE-OLD-COMPLETENESS"
    payload["new"]["completeness_evidence"] = "DEMO-PRIVATE-NEW-COMPLETENESS"
    payload["completed"]["completeness_evidence"] = "DEMO-PRIVATE-COMPLETED-COMPLETENESS"
    for row in payload["completed"]["records"]:
        row["id_match_source"] = "DEMO-PRIVATE-ID-EVIDENCE"
    path = tmp_path / "DEMO-PRIVATE-CASE.json"
    path.write_text(json.dumps(payload))
    assert main(["--case", str(path)]) == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["data_source"] == "real" and output["makeup_task_count"] == 5
    assert "makeup_tasks" not in output and "DEMO-PRIVATE" not in captured.out
    assert "示例课程" not in captured.out


@pytest.mark.parametrize("argv", [
    ["--demo", "--case", "/DEMO-PRIVATE-PATH/input.json"],
    ["--demo", "/DEMO-PRIVATE-PATH/input.xlsx"],
    ["--case", "/DEMO-PRIVATE-PATH/input.json", "--source-id", "DEMO-SOURCE"],
])
def test_input_modes_cannot_mix_private_input_with_public_demo(argv, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "DEMO-PRIVATE" not in captured.err
