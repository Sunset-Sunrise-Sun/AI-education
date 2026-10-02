"""Read the specific sanitized completed-course handoff layout, locally only.

This is intentionally not a general Excel reader. It reads A:J of the selected
worksheet, ignores only the explicitly labeled L:M summary, and never evaluates
formulas. The caller is responsible for sanitizing free text before import.
Errors contain generic messages or numeric positions, never input values.
"""

from __future__ import annotations

import math
import posixpath
import re
from pathlib import Path
from typing import NoReturn
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from app.curriculum.completed_courses import CompletedCourse, normalize_completed_courses
from app.curriculum.errors import CurriculumNormalizationError

__all__ = ["load_completed_courses_xlsx"]

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_HEADERS = (
    "序号", "course_id", "course_name", "credit", "semester", "passed",
    "course_type", "course_id_status", "id_match_source", "备注",
)
_CELL_REFERENCE = re.compile(r"([A-Z]+)([1-9][0-9]*)\Z")
_POSITIVE_INDEX = re.compile(r"[1-9][0-9]*\Z")
_MAX_XML_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_BYTES = 64 * 1024 * 1024


def _tag(name: str) -> str:
    return f"{{{_MAIN_NS}}}{name}"


def _fail(message: str) -> NoReturn:
    raise CurriculumNormalizationError(message) from None


def _read_xml(archive: ZipFile, member: str) -> ET.Element:
    info = archive.getinfo(member)
    if info.file_size > _MAX_XML_BYTES:
        _fail("workbook: XML size limit exceeded")
    data = archive.read(info)
    declaration_bytes = data.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in declaration_bytes or b"<!ENTITY" in declaration_bytes:
        _fail("workbook: unsupported XML declaration")
    return ET.fromstring(data)


def _sheet_member(archive: ZipFile, sheet_name: str) -> str:
    workbook = _read_xml(archive, "xl/workbook.xml")
    if workbook.tag != _tag("workbook"):
        _fail("workbook: invalid workbook XML")
    matches = [
        sheet for sheet in workbook.findall(f"{_tag('sheets')}/{_tag('sheet')}")
        if sheet.get("name") == sheet_name
    ]
    if len(matches) != 1:
        _fail("workbook: selected worksheet is missing or ambiguous")
    relation_id = matches[0].get(f"{{{_DOCUMENT_REL_NS}}}id")
    if not relation_id:
        _fail("workbook: worksheet relationship is missing")

    relationships = _read_xml(archive, "xl/_rels/workbook.xml.rels")
    if relationships.tag != f"{{{_REL_NS}}}Relationships":
        _fail("workbook: invalid relationships XML")
    by_id: dict[str, ET.Element] = {}
    for relation in relationships.findall(f"{{{_REL_NS}}}Relationship"):
        key = relation.get("Id")
        if not key or key in by_id:
            _fail("workbook: invalid or duplicate relationship")
        by_id[key] = relation
    relation = by_id.get(relation_id)
    if relation is None:
        _fail("workbook: worksheet relationship is missing")
    if (
        relation.get("TargetMode", "Internal") != "Internal"
        or relation.get("Type") != f"{_DOCUMENT_REL_NS}/worksheet"
    ):
        _fail("workbook: unsupported worksheet relationship")
    target = relation.get("Target", "")
    if not target or any(character in target for character in ("\\", ":", "?", "#", "\x00")):
        _fail("workbook: invalid worksheet target")
    member = posixpath.normpath(
        target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
    )
    if not member.startswith("xl/") or member == "xl/":
        _fail("workbook: invalid worksheet target")
    return member


def _text_runs(node: ET.Element) -> str:
    parts: list[str] = []
    for child in node:
        if child.tag == _tag("t"):
            parts.append(child.text or "")
        elif child.tag == _tag("r"):
            parts.extend(text.text or "" for text in child.findall(_tag("t")))
    return "".join(parts)


def _shared_strings(archive: ZipFile) -> tuple[str, ...]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return ()
    root = _read_xml(archive, "xl/sharedStrings.xml")
    if root.tag != _tag("sst"):
        _fail("workbook: invalid shared strings XML")
    return tuple(_text_runs(item) for item in root.findall(_tag("si")))


def _has_content(cell: ET.Element) -> bool:
    return (
        cell.find(_tag("f")) is not None
        or cell.get("t") == "e"
        or any(node.text and node.text.strip() for node in cell.iter() if node.tag in {_tag("v"), _tag("t")})
    )


def _cell_value(cell: ET.Element, strings: tuple[str, ...], position: str) -> object:
    if cell.find(_tag("f")) is not None or cell.get("t") == "e":
        _fail(f"{position}: formula or error cell is not allowed")
    kind = cell.get("t", "n")
    values = cell.findall(_tag("v"))
    if len(values) > 1:
        _fail(f"{position}: duplicate cell value")
    value = values[0].text if values else None
    if kind == "inlineStr":
        inline = cell.findall(_tag("is"))
        if len(inline) != 1:
            _fail(f"{position}: invalid inline string")
        return _text_runs(inline[0])
    if kind == "s":
        if value is None or not re.fullmatch(r"[0-9]+", value):
            _fail(f"{position}: invalid shared string index")
        index = int(value)
        if index >= len(strings):
            _fail(f"{position}: invalid shared string index")
        return strings[index]
    if kind == "b":
        if value not in {"0", "1"}:
            _fail(f"{position}: invalid boolean cell")
        return value == "1"
    if kind == "str":
        return value or ""
    if kind != "n":
        _fail(f"{position}: unsupported cell type")
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        _fail(f"{position}: invalid numeric cell")
    if not math.isfinite(number):
        _fail(f"{position}: invalid numeric cell")
    return number


def _rows(sheet: ET.Element) -> list[tuple[int, dict[int, ET.Element]]]:
    if sheet.tag != _tag("worksheet"):
        _fail("workbook: invalid worksheet XML")
    data = sheet.findall(_tag("sheetData"))
    if len(data) != 1:
        _fail("workbook: worksheet data is missing or ambiguous")
    rows: list[tuple[int, dict[int, ET.Element]]] = []
    previous = 0
    for row in data[0].findall(_tag("row")):
        index_text = row.get("r", "")
        if not _POSITIVE_INDEX.fullmatch(index_text):
            _fail("workbook: invalid row index")
        index = int(index_text)
        if index <= previous:
            _fail("workbook: duplicate or unordered row index")
        previous = index
        cells: dict[int, ET.Element] = {}
        for cell in row.findall(_tag("c")):
            reference = _CELL_REFERENCE.fullmatch(cell.get("r", ""))
            if reference is None or int(reference[2]) != index:
                _fail(f"row {index}: invalid cell reference")
            column = 0
            for character in reference[1]:
                column = column * 26 + ord(character) - ord("A") + 1
            if column in cells:
                _fail(f"row {index}: duplicate cell reference")
            cells[column] = cell
        rows.append((index, cells))
    return rows


def _load(archive: ZipFile, *, source_id: str, sheet_name: str) -> tuple[CompletedCourse, ...]:
    infos = archive.infolist()
    if len({info.filename for info in infos}) != len(infos):
        _fail("workbook: duplicate archive member")
    if sum(info.file_size for info in infos) > _MAX_TOTAL_BYTES:
        _fail("workbook: archive size limit exceeded")
    for info in infos:
        if info.filename.startswith("/") or "\\" in info.filename or ".." in info.filename.split("/"):
            _fail("workbook: invalid archive member")

    member = _sheet_member(archive, sheet_name)
    strings = _shared_strings(archive)
    rows = _rows(_read_xml(archive, member))
    if not rows or rows[0][0] != 1:
        _fail("workbook: header row is missing")
    headers = rows[0][1]
    for column, expected in enumerate(_HEADERS, start=1):
        if column not in headers or _cell_value(headers[column], strings, f"row 1 column {column}") != expected:
            _fail(f"row 1 column {column}: invalid or missing header")
    summary = (
        12 in headers and 13 in headers
        and _cell_value(headers[12], strings, "row 1 column 12") == "交接摘要"
        and _cell_value(headers[13], strings, "row 1 column 13") == "值"
    )
    for column, cell in headers.items():
        if column > 10 and _has_content(cell) and not (summary and column in {12, 13}):
            _fail(f"row 1 column {column}: unexpected data column")

    result: list[CompletedCourse] = []
    sequences: set[int] = set()
    for row_index, cells in rows[1:]:
        for column, cell in cells.items():
            if column > 10 and _has_content(cell) and not (summary and column in {12, 13}):
                _fail(f"row {row_index} column {column}: unexpected data column")
        values = {
            column: _cell_value(cell, strings, f"row {row_index} column {column}")
            for column, cell in cells.items() if column <= 10
        }
        if not any(
            value is not None and (not isinstance(value, str) or value.strip())
            for value in values.values()
        ):
            continue
        sequence = values.get(1)
        if (
            isinstance(sequence, bool) or not isinstance(sequence, (int, float))
            or not float(sequence).is_integer() or sequence < 1 or sequence in sequences
        ):
            _fail(f"row {row_index}: invalid or duplicate sequence number")
        sequences.add(int(sequence))
        record = {
            field: values.get(column)
            for column, field in enumerate(_HEADERS[1:9], start=2)
        }
        record["notes"] = values.get(10)
        record["source_record"] = f"{sheet_name}!row:{row_index}"
        try:
            result.extend(normalize_completed_courses([record], source_id=source_id))
        except CurriculumNormalizationError:
            _fail(f"row {row_index}: invalid completed-course record")
    return tuple(result)


def load_completed_courses_xlsx(
    path: Path | str, *, source_id: str, sheet_name: str = "已修课程_脱敏"
) -> tuple[CompletedCourse, ...]:
    """Read every valid A:J course row of exactly the requested worksheet.

    Blank course IDs remain unresolved. Repeated course attempts are retained;
    the sequence number is checked for integrity and never used as a course ID.
    The workbook is read only. No cells or private records are exported.
    """
    normalize_completed_courses([], source_id=source_id)
    if not isinstance(sheet_name, str) or not sheet_name.strip():
        _fail("workbook: invalid worksheet selection")
    if not isinstance(path, (str, Path)):
        _fail("workbook: invalid input path")
    try:
        with ZipFile(path) as archive:
            return _load(archive, source_id=source_id, sheet_name=sheet_name)
    except CurriculumNormalizationError:
        raise
    except (OSError, ValueError, LookupError, BadZipFile, ET.ParseError, RuntimeError, NotImplementedError, ZlibError):
        raise CurriculumNormalizationError("workbook: invalid or unreadable XLSX") from None
