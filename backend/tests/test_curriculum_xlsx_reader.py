"""Exercise the real XLSX reader using generated, entirely fictional XML files."""

from __future__ import annotations

import warnings
import traceback
from struct import unpack_from
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile
from zlib import error as ZlibError

import pytest

from app.curriculum.completed_courses import CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.xlsx_reader import load_completed_courses_xlsx

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_SHEET = "已修课程_脱敏"
_HEADERS = (
    "序号", "course_id", "course_name", "credit", "semester", "passed",
    "course_type", "course_id_status", "id_match_source", "备注",
)


def _q(name: str) -> str:
    return f"{{{_NS}}}{name}"


def _cell(reference: str, value: object, *, kind: str | None = None) -> ET.Element:
    cell = ET.Element(_q("c"), r=reference)
    if value is None:
        return cell
    kind = kind or ("b" if isinstance(value, bool) else "n" if isinstance(value, (int, float)) else "inlineStr")
    cell.set("t", kind)
    if kind == "inlineStr":
        inline = ET.SubElement(cell, _q("is"))
        ET.SubElement(inline, _q("t")).text = str(value)
    else:
        ET.SubElement(cell, _q("v")).text = "1" if value is True else "0" if value is False else str(value)
    return cell


def _facts(sequence: int = 1, *, pending: bool = False, **overrides: object) -> list[object]:
    record = {
        "sequence": sequence,
        "course_id": None if pending else "DEMO-COURSE-01",
        "course_name": "DEMO Course A",
        "credit": 2.5,
        "semester": "DEMO-TERM-1",
        "passed": True,
        "course_type": "DEMO Required",
        "course_id_status": "待确认" if pending else "已确认",
        "id_match_source": None if pending else "DEMO-CATALOG-01",
        "notes": "DEMO review note",
        **overrides,
    }
    return list(record.values())


def _sheet(rows: list[tuple[int, list[object]]] | None = None, *, summary: bool = False) -> ET.Element:
    root = ET.Element(_q("worksheet"))
    data = ET.SubElement(root, _q("sheetData"))
    header = ET.SubElement(data, _q("row"), r="1")
    for column, value in enumerate(_HEADERS):
        header.append(_cell(f"{chr(65 + column)}1", value))
    if summary:
        header.append(_cell("K1", None))
        header.append(_cell("L1", "交接摘要"))
        header.append(_cell("M1", "值"))
    for row_index, values in rows or []:
        row = ET.SubElement(data, _q("row"), r=str(row_index))
        for column, value in enumerate(values):
            row.append(_cell(f"{chr(65 + column)}{row_index}", value))
    return root


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _workbook(
    tmp_path: Path, sheet: ET.Element, *, target: str = "worksheets/sheet2.xml",
    mode: str = "Internal", selected_name: str = _SHEET,
    shared: bool = False, parts_override: dict[str, bytes] | None = None,
) -> Path:
    workbook = ET.Element(_q("workbook"))
    sheets = ET.SubElement(workbook, _q("sheets"))
    ET.SubElement(sheets, _q("sheet"), name="DEMO Other Sheet", sheetId="1", **{f"{{{_DOC_RELS}}}id": "rId1"})
    ET.SubElement(sheets, _q("sheet"), name=selected_name, sheetId="2", **{f"{{{_DOC_RELS}}}id": "rId2"})
    relationships = ET.Element(f"{{{_RELS}}}Relationships")
    ET.SubElement(relationships, f"{{{_RELS}}}Relationship", Id="rId1", Type=f"{_DOC_RELS}/worksheet", Target="worksheets/sheet1.xml")
    ET.SubElement(relationships, f"{{{_RELS}}}Relationship", Id="rId2", Type=f"{_DOC_RELS}/worksheet", Target=target, TargetMode=mode)
    strings: list[str] = []
    if shared:
        for cell in sheet.iter(_q("c")):
            if cell.get("t") == "inlineStr":
                reference = cell.get("r")
                value = "".join(node.text or "" for node in cell.iter(_q("t")))
                cell.clear()
                cell.set("r", reference)
                strings.append(value)
                cell.set("t", "s")
                ET.SubElement(cell, _q("v")).text = str(len(strings) - 1)
    parts = {
        "xl/workbook.xml": _xml(workbook),
        "xl/_rels/workbook.xml.rels": _xml(relationships),
        "xl/worksheets/sheet1.xml": _xml(_sheet()),
        "xl/worksheets/sheet2.xml": _xml(sheet),
    }
    if shared:
        sst = ET.Element(_q("sst"))
        for value in strings:
            ET.SubElement(ET.SubElement(sst, _q("si")), _q("t")).text = value
        parts["xl/sharedStrings.xml"] = _xml(sst)
    parts.update(parts_override or {})
    path = tmp_path / "DEMO-handoff.xlsx"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return path


def _read(path: Path, **kwargs: object):
    return load_completed_courses_xlsx(path, source_id="DEMO-TRANSCRIPT-01", **kwargs)


@pytest.mark.parametrize("target", ["worksheets/sheet2.xml", "/xl/worksheets/sheet2.xml"])
@pytest.mark.parametrize("shared", [False, True])
def test_requested_sheet_and_supported_strings_are_read(tmp_path: Path, target: str, shared: bool) -> None:
    result = _read(_workbook(tmp_path, _sheet([(2, _facts())]), target=target, shared=shared))
    assert isinstance(result, tuple) and len(result) == 1
    course = result[0]
    assert course.course_id == "DEMO-COURSE-01"
    assert course.course_name == "DEMO Course A"
    assert course.credit == 2.5
    assert course.semester == "DEMO-TERM-1"
    assert course.passed is True
    assert course.course_id_status is CourseIdStatus.CONFIRMED
    assert course.id_match_source == "DEMO-CATALOG-01"
    assert course.notes == "DEMO review note"
    assert course.source_id == "DEMO-TRANSCRIPT-01"
    assert course.source_record == f"{_SHEET}!row:2"


def test_all_rows_and_retakes_keep_order_and_actual_row_references(tmp_path: Path) -> None:
    sheet = _sheet([(2, [None] * 10), (3, _facts(passed=False)), (7, _facts(2, semester="DEMO-TERM-2")), (9, _facts(3, pending=True))])
    result = _read(_workbook(tmp_path, sheet))
    assert len(result) == 3
    assert [item.passed for item in result] == [False, True, True]
    assert [item.source_record for item in result] == [f"{_SHEET}!row:{index}" for index in [3, 7, 9]]
    assert result[2].course_id is None and result[2].course_id_status is CourseIdStatus.PENDING
    assert result[2].id_match_source is None


def test_every_fictional_row_is_read_without_sampling(tmp_path: Path) -> None:
    sheet = _sheet([(index + 1, _facts(index)) for index in range(1, 38)])
    assert len(_read(_workbook(tmp_path, sheet))) == 37


def _direct_strings(sheet: ET.Element) -> ET.Element:
    for cell in sheet.iter(_q("c")):
        if cell.get("t") == "inlineStr":
            inline = cell.find(_q("is"))
            value = "".join(node.text or "" for node in inline.iter(_q("t")))
            cell.remove(inline)
            cell.set("t", "str")
            ET.SubElement(cell, _q("v")).text = value
    return sheet


def test_direct_string_headers_and_fields_keep_numeric_and_boolean_types(tmp_path: Path) -> None:
    sheet = _direct_strings(_sheet([
        (2, _facts(passed=False)),
        (3, _facts(2, pending=True)),
        (4, _facts(3, semester="DEMO-TERM-2")),
    ]))
    rows = sheet.find(_q("sheetData"))
    assert all(cell.get("t") == "str" for cell in rows[0])
    assert rows[1][0].get("t") == "n" and rows[1][3].get("t") == "n"
    assert rows[1][5].get("t") == "b"
    # An explicitly empty string remains an unresolved ID rather than a guess.
    rows[2][1].set("t", "str")
    ET.SubElement(rows[2][1], _q("v"))
    result = _read(_workbook(tmp_path, sheet))
    assert len(result) == 3
    assert result[0].course_name == "DEMO Course A" and result[0].passed is False
    assert result[0].credit == 2.5
    assert result[1].course_id is None
    assert result[1].course_id_status is CourseIdStatus.PENDING
    assert result[2].semester == "DEMO-TERM-2"
    assert [item.source_record for item in result] == [f"{_SHEET}!row:{index}" for index in (2, 3, 4)]


def test_direct_string_formula_is_rejected_before_cached_text(tmp_path: Path) -> None:
    sheet = _direct_strings(_sheet([(2, _facts())]))
    cell = sheet.find(_q("sheetData"))[1][2]
    ET.SubElement(cell, _q("f")).text = '"DEMO-PRIVATE-CACHED-NAME"'
    with pytest.raises(CurriculumNormalizationError, match="formula or error") as excinfo:
        _read(_workbook(tmp_path, sheet))
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("with_value", [False, True])
def test_empty_direct_string_course_name_is_not_silently_skipped(tmp_path: Path, with_value: bool) -> None:
    sheet = _direct_strings(_sheet([(2, _facts())]))
    cell = sheet.find(_q("sheetData"))[1][2]
    cell.remove(cell.find(_q("v")))
    if with_value:
        ET.SubElement(cell, _q("v"))
    with pytest.raises(CurriculumNormalizationError, match="invalid completed-course record"):
        _read(_workbook(tmp_path, sheet))


def test_explicit_summary_is_ignored_even_on_other_rows(tmp_path: Path) -> None:
    sheet = _sheet([(2, _facts()), (4, [None] * 10)], summary=True)
    row = sheet.find(_q("sheetData"))[-1]
    row.append(_cell("L4", "DEMO summary count"))
    summary_cell = _cell("M4", 1)
    ET.SubElement(summary_cell, _q("f")).text = "COUNTA(A2:A3)"
    row.append(summary_cell)
    assert len(_read(_workbook(tmp_path, sheet))) == 1


@pytest.mark.parametrize("summary", [False, True])
def test_empty_valid_course_area_returns_empty_tuple(tmp_path: Path, summary: bool) -> None:
    assert _read(_workbook(tmp_path, _sheet(summary=summary))) == ()


def test_inline_rich_text_is_concatenated_without_phonetic_annotation(tmp_path: Path) -> None:
    sheet = _sheet([(2, _facts())])
    cell = sheet.find(_q("sheetData"))[1][2]
    inline = cell.find(_q("is"))
    inline.clear()
    ET.SubElement(ET.SubElement(inline, _q("r")), _q("t")).text = "DEMO "
    ET.SubElement(ET.SubElement(inline, _q("r")), _q("t")).text = "Course A"
    ET.SubElement(ET.SubElement(inline, _q("rPh")), _q("t")).text = "DEMO phonetic annotation"
    assert _read(_workbook(tmp_path, sheet))[0].course_name == "DEMO Course A"


@pytest.mark.parametrize("column", range(10))
def test_each_header_is_required(tmp_path: Path, column: int) -> None:
    sheet = _sheet([(2, _facts())])
    header = sheet.find(_q("sheetData"))[0]
    header.remove(header[column])
    with pytest.raises(CurriculumNormalizationError, match="header"):
        _read(_workbook(tmp_path, sheet))


@pytest.mark.parametrize("reference,value", [("K1", "姓名"), ("L1", "GPA"), ("M1", "成绩"), ("N1", "DEMO-PRIVATE-HEADER")])
def test_extra_data_header_is_rejected_without_disclosure(tmp_path: Path, reference: str, value: str) -> None:
    sheet = _sheet([(2, _facts())])
    sheet.find(_q("sheetData"))[0].append(_cell(reference, value))
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_workbook(tmp_path, sheet))
    assert value not in str(excinfo.value)


@pytest.mark.parametrize("summary,reference", [(False, "K2"), (False, "L2"), (True, "K2"), (True, "N2")])
def test_nonempty_unapproved_extra_columns_fail_without_silent_drop(tmp_path: Path, summary: bool, reference: str) -> None:
    sheet = _sheet([(2, _facts())], summary=summary)
    sheet.find(_q("sheetData"))[1].append(_cell(reference, "DEMO-PRIVATE-VALUE"))
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_workbook(tmp_path, sheet))
    assert "DEMO-PRIVATE-VALUE" not in str(excinfo.value)


@pytest.mark.parametrize("sequence", [None, "1", True, 0, -1, 1.25])
def test_missing_or_invalid_sequence_fails(tmp_path: Path, sequence: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="sequence"):
        _read(_workbook(tmp_path, _sheet([(2, _facts(sequence=sequence))])))


def test_duplicate_sequence_fails_but_repeated_courses_are_valid(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="sequence"):
        _read(_workbook(tmp_path, _sheet([(2, _facts()), (3, _facts())])))


@pytest.mark.parametrize("column", range(10))
@pytest.mark.parametrize("kind", ["formula", "error"])
def test_formulas_and_error_cells_in_every_data_column_reject_cache(tmp_path: Path, column: int, kind: str) -> None:
    sheet = _sheet([(2, _facts())])
    cell = sheet.find(_q("sheetData"))[1][column]
    if kind == "formula":
        ET.SubElement(cell, _q("f")).text = '"DEMO-PRIVATE-FORMULA"'
    else:
        cell.set("t", "e")
    with pytest.raises(CurriculumNormalizationError, match="formula or error") as excinfo:
        _read(_workbook(tmp_path, sheet))
    assert "DEMO-PRIVATE-FORMULA" not in str(excinfo.value)


@pytest.mark.parametrize("overrides", [
    {"credit": "3"}, {"credit": True}, {"credit": -1}, {"credit": float("nan")},
    {"credit": float("inf")}, {"passed": "true"}, {"passed": 1}, {"semester": 46100},
    {"course_name": None}, {"course_id": 17}, {"course_id_status": "DEMO unknown"},
    {"id_match_source": None}, {"notes": 2},
])
def test_wrong_fact_types_fail_without_coercion(tmp_path: Path, overrides: dict[str, object]) -> None:
    with pytest.raises(CurriculumNormalizationError):
        _read(_workbook(tmp_path, _sheet([(2, _facts(**overrides))])))


@pytest.mark.parametrize("reference", ["B3", "B0", "B", "b2", "", "A2"])
def test_inconsistent_or_duplicate_cell_references_fail(tmp_path: Path, reference: str) -> None:
    sheet = _sheet([(2, _facts())])
    sheet.find(_q("sheetData"))[1][1].set("r", reference)
    with pytest.raises(CurriculumNormalizationError, match="cell reference"):
        _read(_workbook(tmp_path, sheet))


@pytest.mark.parametrize("row_reference", ["1", "", "0", "2.0", "DEMO-PRIVATE-INDEX"])
def test_invalid_or_duplicate_row_indices_fail(tmp_path: Path, row_reference: str) -> None:
    sheet = _sheet([(2, _facts())])
    sheet.find(_q("sheetData"))[1].set("r", row_reference)
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_workbook(tmp_path, sheet))
    assert "DEMO-PRIVATE-INDEX" not in str(excinfo.value)


def test_bad_second_record_fails_whole_import_and_reports_actual_row(tmp_path: Path) -> None:
    sheet = _sheet([(2, _facts()), (8, _facts(2, semester="", notes="DEMO-PRIVATE-NOTE"))])
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_workbook(tmp_path, sheet))
    assert str(excinfo.value) == "row 8: invalid completed-course record"
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("target,mode", [
    ("https://example.invalid/DEMO-PRIVATE-TARGET", "External"),
    ("../DEMO-PRIVATE-TARGET", "Internal"),
    ("file:///DEMO-PRIVATE-TARGET", "Internal"),
    ("worksheets\\DEMO-PRIVATE-TARGET", "Internal"),
])
def test_external_or_unsafe_relationships_are_never_followed(tmp_path: Path, target: str, mode: str) -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_workbook(tmp_path, _sheet([(2, _facts())]), target=target, mode=mode))
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_missing_requested_sheet_does_not_fall_back(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="selected worksheet") as excinfo:
        _read(_workbook(tmp_path, _sheet([(2, _facts())])), sheet_name="DEMO-PRIVATE-SHEET")
    assert "DEMO-PRIVATE-SHEET" not in str(excinfo.value)


@pytest.mark.parametrize("part", ["xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/worksheets/sheet2.xml", "xl/sharedStrings.xml"])
def test_malformed_xml_fails_without_source_text(tmp_path: Path, part: str) -> None:
    path = _workbook(tmp_path, _sheet([(2, _facts())]), shared=True, parts_override={part: b"<DEMO-PRIVATE-BROKEN"})
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_shared_string_out_of_range_fails(tmp_path: Path) -> None:
    sheet = _sheet([(2, _facts())])
    cell = sheet.find(_q("sheetData"))[1][2]
    cell.clear()
    cell.set("r", "C2")
    cell.set("t", "s")
    ET.SubElement(cell, _q("v")).text = "900"
    with pytest.raises(CurriculumNormalizationError, match="shared string index"):
        _read(_workbook(tmp_path, sheet))


@pytest.mark.parametrize("kind,value", [("b", "true"), ("n", "DEMO-PRIVATE-NUMBER"), ("d", "2040-01-01"), ("s", "-1")])
def test_bad_encoded_types_fail_without_date_inference(tmp_path: Path, kind: str, value: str) -> None:
    sheet = _sheet([(2, _facts())])
    row = sheet.find(_q("sheetData"))[1]
    row.remove(row[3])
    row.append(_cell("D2", value, kind=kind))
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_workbook(tmp_path, sheet))
    assert "DEMO-PRIVATE" not in str(excinfo.value)
    # Underlying float()/ZIP/XML errors must not disclose values via chaining.
    formatted = "".join(traceback.format_exception(excinfo.value))
    assert value not in formatted


@pytest.mark.parametrize("content", [b"DEMO not a zip", b"PK\x03\x04DEMO truncated"])
def test_bad_zip_never_echoes_path(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "DEMO-PRIVATE-FILENAME.xlsx"
    path.write_bytes(content)
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert "DEMO-PRIVATE" not in str(excinfo.value)
    assert str(tmp_path) not in str(excinfo.value)


def test_missing_file_is_sanitized(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(tmp_path / "DEMO-PRIVATE-MISSING.xlsx")
    assert str(excinfo.value) == "workbook: invalid or unreadable XLSX"


def test_corrupt_deflate_stream_is_sanitized(tmp_path: Path) -> None:
    path = _workbook(tmp_path, _sheet([(2, _facts())]))
    with ZipFile(path) as archive:
        header_offset = archive.getinfo("xl/workbook.xml").header_offset
    data = bytearray(path.read_bytes())
    filename_length, extra_length = unpack_from("<HH", data, header_offset + 26)
    body_offset = header_offset + 30 + filename_length + extra_length
    data[body_offset] = 0xFF  # Reserved DEFLATE block type, not a mock exception.
    path.write_bytes(data)
    with ZipFile(path) as archive, pytest.raises(ZlibError):
        archive.read("xl/workbook.xml")
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert str(excinfo.value) == "workbook: invalid or unreadable XLSX"


@pytest.mark.parametrize("member", ["xl/workbook.xml", "../DEMO-PRIVATE-MEMBER"])
def test_duplicate_or_unsafe_zip_members_fail(tmp_path: Path, member: str) -> None:
    path = _workbook(tmp_path, _sheet([(2, _facts())]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(path, "a") as archive:
            archive.writestr(member, "DEMO")
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_xml_entities_are_not_expanded(tmp_path: Path, encoding: str) -> None:
    xml = f'<?xml version="1.0" encoding="{encoding}"?><!DOCTYPE workbook [<!ENTITY demo "DEMO-PRIVATE">]><workbook xmlns="{_NS}"/>'
    path = _workbook(tmp_path, _sheet(), parts_override={"xl/workbook.xml": xml.encode(encoding)})
    with pytest.raises(CurriculumNormalizationError, match="unsupported XML declaration"):
        _read(path)


def test_unknown_xml_encoding_is_sanitized(tmp_path: Path) -> None:
    xml = f'<?xml version="1.0" encoding="DEMO-PRIVATE-ENCODING"?><workbook xmlns="{_NS}"/>'
    path = _workbook(tmp_path, _sheet(), parts_override={"xl/workbook.xml": xml.encode("utf-8")})
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert str(excinfo.value) == "workbook: invalid or unreadable XLSX"
    assert "DEMO-PRIVATE-ENCODING" not in str(excinfo.value)


def test_empty_source_id_is_invalid_even_for_empty_sheet(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="source_id"):
        load_completed_courses_xlsx(_workbook(tmp_path, _sheet()), source_id="")
