"""Exercise the private file-to-Provider route with artificial Office inputs."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from app.curriculum.case import (
    DEMO_CASE_PATH, CurriculumCaseProvider, load_curriculum_case, normalize_curriculum_case,
)
from app.curriculum.__main__ import main
from app.curriculum.errors import CurriculumNormalizationError
from test_curriculum_xlsx_reader import _facts, _sheet, _workbook

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_HEADERS = ["课程号", "课程名", "学分", "学期"]


def _docx(path: Path, rows):
    tag = lambda name: f"{{{_W}}}{name}"
    root = ET.Element(tag("document"))
    table = ET.SubElement(ET.SubElement(root, tag("body")), tag("tbl"))
    grid = ET.SubElement(table, tag("tblGrid"))
    for _ in _HEADERS:
        ET.SubElement(grid, tag("gridCol"), {tag("w"): "2000"})
    for values in [_HEADERS, *rows]:
        row = ET.SubElement(table, tag("tr"))
        for value in values:
            cell = ET.SubElement(row, tag("tc"))
            run = ET.SubElement(ET.SubElement(cell, tag("p")), tag("r"))
            ET.SubElement(run, tag("t")).text = value
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", ET.tostring(root, encoding="utf-8"))
    return path


def _mapping():
    return [{
        "table_index": 1, "header_row": 1,
        "columns": {"course_id": 1, "course_name": 2, "credit": 3, "recommended_term_text": 4},
        "expected_headers": dict(zip(
            ("course_id", "course_name", "credit", "recommended_term_text"), _HEADERS,
        )),
        "requirement": "required",
    }]


def _file_case(tmp_path):
    payload = json.loads(DEMO_CASE_PATH.read_text())
    _docx(tmp_path / "old.docx", [["DEMO101", "示例课程一", "3", "一至二"]])
    _docx(tmp_path / "new.docx", [
        ["DEMO101", "示例课程一", "3", "一至二"],
        ["DEMO202", "DEMO-PRIVATE-NAME", "4", "三至四"],
    ])
    for version, name in ((payload["old"], "old.docx"), (payload["new"], "new.docx")):
        version.pop("course_records")
        version["docx"] = {"path": name, "tables": _mapping()}
    workbook = _workbook(tmp_path, _sheet([(2, _facts(
        course_id="DEMO101", course_name="示例课程一", credit=3,
        id_match_source="mock://DEMO-ID-EVIDENCE",
    ))]))
    payload["completed"].pop("records")
    payload["completed"]["xlsx"] = {"path": workbook.name}
    path = tmp_path / "DEMO-PRIVATE-CASE.json"
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path, payload


def test_private_office_files_flow_through_computed_provider_with_original_locations(tmp_path):
    path, _ = _file_case(tmp_path)
    provider = CurriculumCaseProvider(load_curriculum_case(path))
    tasks = provider.get_makeup_tasks()
    assert len(tasks) == 2
    assert tasks[0].status.value == "satisfied"
    # Word has no confirmed prerequisite facts, even when a recommended term exists.
    assert tasks[1].status.value == "manual_confirmation" and tasks[1].prerequisites == []
    assert "table:1!row:3" in tasks[1].source_evidence
    assert tasks[1].recommended_semester is None
    assert len(provider.case.completed) == 1
    assert provider.case.completed[0].source_record == "已修课程_脱敏!row:2"


def test_case_cli_does_not_publish_private_word_rows_or_file_paths(tmp_path, capsys):
    path, _ = _file_case(tmp_path)
    assert main(["--case", str(path)]) == 0
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["makeup_task_count"] == 2
    assert summary["status_counts"] == {"satisfied": 1, "manual_confirmation": 1}
    assert "DEMO-PRIVATE" not in output.out + output.err
    assert "table:1" not in output.out and str(tmp_path) not in output.out


def test_missing_word_identity_is_preserved_in_draft_and_blocks_whole_case(tmp_path):
    path, _ = _file_case(tmp_path)
    _docx(tmp_path / "new.docx", [["", "DEMO-PRIVATE-COURSE", "4", "三至四"]])
    with pytest.raises(CurriculumNormalizationError) as error:
        load_curriculum_case(path)
    assert "DEMO-PRIVATE" not in str(error.value)


@pytest.mark.parametrize("side", ["old", "new", "completed"])
def test_in_memory_normalization_never_opens_file_references(tmp_path, monkeypatch, side):
    _, payload = _file_case(tmp_path)
    if side != "old":
        # Isolate the selected file reference from earlier curriculum references.
        demo = json.loads(DEMO_CASE_PATH.read_text())
        payload["old"] = demo["old"]
        if side == "completed":
            payload["new"] = demo["new"]
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("unexpected file access"))
    with pytest.raises(CurriculumNormalizationError, match="require load_curriculum_case"):
        normalize_curriculum_case(payload)


@pytest.mark.parametrize("side", ["old", "completed"])
def test_ambiguous_inline_and_file_inputs_are_rejected_without_fallback(tmp_path, side):
    path, payload = _file_case(tmp_path)
    payload[side]["course_records" if side == "old" else "records"] = []
    path.write_text(json.dumps(payload))
    with pytest.raises(CurriculumNormalizationError, match="exclusively"):
        load_curriculum_case(path)


def test_word_inspection_cli_retains_pending_rows_without_emitting_their_values(tmp_path, capsys):
    path = _docx(tmp_path / "DEMO-PRIVATE.docx", [["", "DEMO-PRIVATE-NAME", "2", "一"]])
    profile = tmp_path / "DEMO-PRIVATE-PROFILE.json"
    profile.write_text(json.dumps({"source_id": "mock://DEMO-PRIVATE-SOURCE", "tables": _mapping()}))
    assert main(["--docx", str(path), "--profile", str(profile)]) == 0
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["rows"] == 1 and summary["unresolved_rows"] == 1
    assert summary["conversion_ready"] is False
    assert summary["issue_counts"]
    assert "DEMO-PRIVATE" not in output.out + output.err


def test_blocked_group_case_remains_inspectable_without_projecting_partial_tasks(tmp_path, capsys):
    payload = json.loads(DEMO_CASE_PATH.read_text())
    payload["new"]["group_records"] = [{
        "group_id": "DEMO-G", "name": "DEMO-PRIVATE-GROUP", "minimum_credit": 2,
        "source_record": "mock://group-rule",
    }]
    payload["new"]["course_records"].append({
        "course_id": "DEMO-E", "course_name": "DEMO-PRIVATE-ELECTIVE", "credit": 2,
        "requirement": "elective", "group_id": "DEMO-G", "source_record": "mock://pool-row",
    })
    path = tmp_path / "DEMO-PRIVATE.json"
    path.write_text(json.dumps(payload))
    provider = CurriculumCaseProvider(load_curriculum_case(path))
    with pytest.raises(CurriculumNormalizationError, match="group"):
        provider.get_makeup_tasks()
    assert len(provider.get_curriculum_diff().group_gaps) == 1
    assert main(["--inspect-case", str(path)]) == 0
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["projection_ready"] is False and summary["makeup_task_count"] is None
    assert summary["group_gap_count"] == 1
    assert "DEMO-PRIVATE" not in output.out + output.err
