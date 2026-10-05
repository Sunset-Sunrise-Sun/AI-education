"""Read explicitly mapped Word tables into private Curriculum import drafts.

This is a bounded OOXML reader, not an automatic school-policy interpreter.
Table and column meanings are supplied by the caller. Unknown identities,
ambiguous layouts and nonnumeric credits remain visible in an import draft;
they cannot enter a CurriculumVersion until the import is resolved.
"""

from __future__ import annotations

import math
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import CurriculumVersion, RequirementKind, normalize_curriculum_version

__all__ = ["DocxImportIssue", "DocxCourseRow", "DocxImportResult", "load_curriculum_docx"]

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_ALTERNATE_CONTENT = "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"
_MAX_FILE_BYTES = 32 * 1024 * 1024
_MAX_XML_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 2048
_MAX_COLUMNS = 512
_FIELDS = frozenset({"course_id", "course_name", "credit", "recommended_term_text", "requirement"})
_PROFILE_FIELDS = frozenset({
    "table_index", "header_row", "columns", "expected_headers", "first_data_row", "last_data_row",
    "requirement", "course_type", "group_id", "requirement_values",
})
_CREDIT = re.compile(r"\+?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)\Z")
_UNKNOWN_IDS = frozenset({"待确认", "未知", "未确认", "未提供", "pending", "unknown", "?"})
_REVISION_TAGS = frozenset({
    "ins", "del", "moveFrom", "moveTo", "trPrChange", "tcPrChange", "tblPrChange", "rPrChange", "pPrChange",
    "cellIns", "cellDel", "cellMerge", "tblGridChange",
})
_HIDDEN_TAGS = frozenset({"vanish", "webHidden"})
_VISIBLE_PROPERTY_VALUES = frozenset({"false", "off", "0"})
_UNSUPPORTED_TAGS = frozenset({
    "drawing", "pict", "object", "fldSimple", "fldChar", "instrText", "altChunk", "sdt", "customXml", "sym",
})


def _tag(name: str) -> str:
    return f"{{{_NS}}}{name}"


def _fail(message: str) -> None:
    raise CurriculumNormalizationError(message) from None


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label}: expected a nonempty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"{label}: expected a positive integer")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _requirement(value: object) -> RequirementKind:
    try:
        return RequirementKind(value)
    except (ValueError, TypeError):
        _fail("document profile: unsupported requirement")


@dataclass(frozen=True, slots=True)
class DocxImportIssue:
    """A numeric source position and fixed code, with no source text."""

    code: str
    table_index: int
    row_index: int
    field: str | None = None
    column_index: int | None = None


@dataclass(frozen=True, slots=True)
class DocxCourseRow:
    """One original selected row, including unresolved source facts."""

    table_index: int
    row_index: int
    course_id: str | None = field(repr=False)
    course_name: str | None = field(repr=False)
    credit: float | None
    requirement: RequirementKind
    source_record: str
    course_type: str | None = field(default=None, repr=False)
    group_id: str | None = field(default=None, repr=False)
    recommended_term_text: str | None = field(default=None, repr=False)
    prerequisites: None = None
    raw_values: tuple[tuple[str, str | None], ...] = field(default=(), repr=False)
    issues: tuple[DocxImportIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class DocxImportResult:
    """An internal draft. Conversion never drops an unresolved source row."""

    source_id: str = field(repr=False)
    rows: tuple[DocxCourseRow, ...] = field(repr=False)
    issues: tuple[DocxImportIssue, ...]

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id")
        for label, model in (("rows", DocxCourseRow), ("issues", DocxImportIssue)):
            value = getattr(self, label)
            if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
                _fail(f"document import: invalid {label}")
            value = tuple(value)
            if any(not isinstance(entry, model) for entry in value):
                _fail(f"document import: invalid {label}")
            object.__setattr__(self, label, value)

    def to_version(
        self, *, version_id: str, major: str, cohort: str,
        group_records: Sequence[Mapping[str, object]] = (),
        complete: bool = False, completeness_evidence: str | None = None,
        total_credit: float | None = None, practice_credit: float | None = None,
        study_years: int | None = None,
    ) -> CurriculumVersion:
        """Convert only a resolved draft, using explicit version metadata."""
        if self.issues or any(row.issues for row in self.rows):
            _fail("document import: unresolved rows require review")
        return normalize_curriculum_version(
            version_id=version_id, major=major, cohort=cohort, source_id=self.source_id,
            course_records=[{
                "course_id": row.course_id, "course_name": row.course_name, "credit": row.credit,
                "requirement": row.requirement, "source_record": row.source_record,
                "course_type": row.course_type, "group_id": row.group_id,
                "recommended_term_text": row.recommended_term_text, "prerequisites": None,
            } for row in self.rows],
            group_records=group_records, complete=complete,
            completeness_evidence=completeness_evidence,
            total_credit=total_credit, practice_credit=practice_credit, study_years=study_years,
        )


@dataclass(frozen=True, slots=True)
class _TableProfile:
    table_index: int
    header_row: int
    columns: tuple[tuple[str, int], ...]
    expected_headers: tuple[tuple[str, str], ...]
    first_data_row: int
    last_data_row: int | None
    requirement: RequirementKind
    fixed_requirement: bool
    course_type: str | None
    group_id: str | None
    requirement_values: tuple[tuple[str, RequirementKind], ...]


def _profiles(tables: object) -> tuple[_TableProfile, ...]:
    if isinstance(tables, (str, bytes, bytearray)) or not isinstance(tables, Sequence) or not tables:
        _fail("document profile: expected table mappings")
    if len(tables) > 128:
        _fail("document profile: table mapping limit exceeded")
    result = []
    for spec in tables:
        if not isinstance(spec, Mapping) or set(spec) - _PROFILE_FIELDS:
            _fail("document profile: invalid fields")
        if {"table_index", "header_row", "columns", "expected_headers"} - set(spec):
            _fail("document profile: missing required field")
        table_index = _integer(spec["table_index"], "table_index")
        header = _integer(spec["header_row"], "header_row")
        columns = spec["columns"]
        expected = spec["expected_headers"]
        if not isinstance(columns, Mapping) or not {"course_id", "course_name", "credit"} <= set(columns):
            _fail("document profile: core course columns are required")
        if set(columns) - _FIELDS:
            _fail("document profile: unsupported column field")
        if not isinstance(expected, Mapping) or set(expected) != set(columns):
            _fail("document profile: headers must cover exactly the mapped fields")
        positions = tuple(_integer(value, "column_index") for value in columns.values())
        if len(set(positions)) != len(positions) or max(positions) > _MAX_COLUMNS:
            _fail("document profile: invalid or duplicate column index")
        for value in expected.values():
            _text(value, "expected_headers")
        first = _integer(spec.get("first_data_row", header + 1), "first_data_row")
        last = spec.get("last_data_row")
        if last is not None:
            last = _integer(last, "last_data_row")
        if first <= header or (last is not None and last < first):
            _fail("document profile: invalid data row range")
        mapping = spec.get("requirement_values", {})
        if not isinstance(mapping, Mapping) or (mapping and "requirement" not in columns):
            _fail("document profile: invalid requirement mapping")
        values = tuple((_text(key, "requirement_values"), _requirement(value)) for key, value in mapping.items())
        result.append(_TableProfile(
            table_index, header, tuple(columns.items()), tuple(expected.items()), first, last,
            _requirement(spec.get("requirement", RequirementKind.UNKNOWN)), "requirement" in spec,
            _optional_text(spec.get("course_type"), "course_type"),
            _optional_text(spec.get("group_id"), "group_id"), values,
        ))
    return tuple(result)


def _read_xml(archive: ZipFile, member: str) -> ET.Element:
    info = archive.getinfo(member)
    if info.file_size > _MAX_XML_BYTES:
        _fail("document: XML size limit exceeded")
    with archive.open(info) as source:
        raw = source.read(_MAX_XML_BYTES + 1)
    if len(raw) > _MAX_XML_BYTES:
        _fail("document: XML size limit exceeded")
    declarations = raw.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
        _fail("document: unsupported XML declaration")
    return ET.fromstring(raw)


def _read_document(path: str | Path) -> tuple[ET.Element, ET.Element | None]:
    if not isinstance(path, (str, Path)):
        _fail("document: invalid input path")
    try:
        with Path(path).open("rb") as source:
            data = source.read(_MAX_FILE_BYTES + 1)
        if len(data) > _MAX_FILE_BYTES:
            _fail("document: file size limit exceeded")
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_ARCHIVE_MEMBERS:
                _fail("document: archive member limit exceeded")
            if len({info.filename for info in infos}) != len(infos):
                _fail("document: duplicate archive member")
            if sum(info.file_size for info in infos) > _MAX_TOTAL_BYTES:
                _fail("document: archive size limit exceeded")
            for info in infos:
                name = info.filename
                if (name.startswith("/") or "\\" in name or "\x00" in name
                    or any(part in {".", ".."} for part in name.split("/"))
                    or stat.S_ISLNK(info.external_attr >> 16)):
                    _fail("document: invalid archive member")
            root = _read_xml(archive, "word/document.xml")
            styles = _read_xml(archive, "word/styles.xml") if "word/styles.xml" in archive.namelist() else None
        if root.tag != _tag("document") or len(root.findall(_tag("body"))) != 1:
            _fail("document: invalid document XML")
        if styles is not None and styles.tag != _tag("styles"):
            _fail("document: invalid styles XML")
        return root, styles
    except CurriculumNormalizationError:
        raise
    except (OSError, ValueError, LookupError, BadZipFile, ET.ParseError, RuntimeError, NotImplementedError, ZlibError):
        raise CurriculumNormalizationError("document: invalid or unreadable DOCX") from None


def _cell_text(cell: ET.Element) -> str:
    paragraphs = []
    for paragraph in cell.iter(_tag("p")):
        parts = []
        for node in paragraph.iter():
            if node.tag in {_tag("t"), _tag("delText")}:
                parts.append(node.text or "")
            elif node.tag in {_tag("br"), _tag("cr")}:
                parts.append("\n")
            elif node.tag == _tag("tab"):
                parts.append("\t")
            elif node.tag == _tag("noBreakHyphen"):
                parts.append("\u2011")
            elif node.tag == _tag("softHyphen"):
                parts.append("\u00ad")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _active_hidden_properties(node: ET.Element) -> frozenset[str]:
    return frozenset(name for name in _HIDDEN_TAGS for entry in node.iter(_tag(name))
                     if entry.get(_tag("val")) not in _VISIBLE_PROPERTY_VALUES)


@dataclass(frozen=True, slots=True)
class _StyleVisibility:
    hidden: Mapping[str, frozenset[str]]
    defaults: Mapping[str, frozenset[str]]
    document_defaults: frozenset[str]
    unresolved: frozenset[str] = frozenset()
    unresolved_defaults: frozenset[str] = frozenset()

    def referenced(self, parent: ET.Element, tag: str, kind: str) -> frozenset[str]:
        entry = parent.find(tag)
        return self.hidden.get(entry.get(_tag("val")), frozenset()) if entry is not None else self.defaults.get(kind, frozenset())

    def uncertain(self, parent: ET.Element, tag: str, kind: str) -> bool:
        entry = parent.find(tag)
        if entry is None:
            return kind in self.unresolved_defaults
        key = entry.get(_tag("val"))
        return key not in self.hidden or key in self.unresolved


def _style_visibility(root: ET.Element | None) -> _StyleVisibility:
    if root is None:
        return _StyleVisibility({}, {}, frozenset())
    styles = root.findall(_tag("style"))
    if len(styles) > 4096:
        _fail("document: style count limit exceeded")
    definitions = {}
    parents = {}
    direct = {}
    for style in styles:
        key = style.get(_tag("styleId"))
        if not key or key in definitions:
            _fail("document: invalid or duplicate style definition")
        definitions[key] = style
        parent = style.find(_tag("basedOn"))
        parents[key] = parent.get(_tag("val")) if parent is not None else None
        direct[key] = _active_hidden_properties(style)
    hidden = {}
    unresolved = set()
    for key in definitions:
        chain = []
        indices = {}
        current = key
        while current in definitions and current not in hidden and current not in indices:
            indices[current] = len(chain)
            chain.append(current)
            current = parents[current]
        flags = hidden.get(current, frozenset())
        uncertain = current in indices or current in unresolved or (current is not None and current not in definitions)
        if current in indices:
            for member in chain[indices[current]:]:
                flags |= direct[member]
        for member in reversed(chain):
            flags |= direct[member]
            hidden[member] = flags
            if uncertain:
                unresolved.add(member)
    defaults = {}
    unresolved_defaults = set()
    for key, style in definitions.items():
        if style.get(_tag("default")) in {"true", "on", "1"}:
            kind = style.get(_tag("type"))
            defaults[kind] = defaults.get(kind, frozenset()) | hidden[key]
            if key in unresolved:
                unresolved_defaults.add(kind)
    default_properties = root.find(_tag("docDefaults"))
    document_defaults = _active_hidden_properties(default_properties) if default_properties is not None else frozenset()
    return _StyleVisibility(hidden, defaults, document_defaults, frozenset(unresolved), frozenset(unresolved_defaults))


def _style_codes(row: ET.Element, visibility: _StyleVisibility, table_properties: frozenset[str],
                 table_uncertain: bool = False) -> tuple[str, ...]:
    """Detect potentially hidden used styles without simulating Word rendering."""
    codes = {"unresolved_style_reference"} if table_uncertain else set()
    for paragraph in row.iter(_tag("p")):
        paragraph_hidden = visibility.referenced(paragraph, f"{_tag('pPr')}/{_tag('pStyle')}", "paragraph")
        if visibility.uncertain(paragraph, f"{_tag('pPr')}/{_tag('pStyle')}", "paragraph"):
            codes.add("unresolved_style_reference")
        for run in paragraph.iter(_tag("r")):
            if visibility.uncertain(run, f"{_tag('rPr')}/{_tag('rStyle')}", "character"):
                codes.add("unresolved_style_reference")
            flags = set(visibility.document_defaults | table_properties | paragraph_hidden
                        | visibility.referenced(run, f"{_tag('rPr')}/{_tag('rStyle')}", "character"))
            for name in _HIDDEN_TAGS:
                direct = run.find(f"{_tag('rPr')}/{_tag(name)}")
                if direct is not None and direct.get(_tag("val")) in _VISIBLE_PROPERTY_VALUES:
                    flags.discard(name)
            if flags:
                codes.add("hidden_style_content")
    return tuple(sorted(codes))


def _layout(row: ET.Element) -> tuple[dict[int, ET.Element], tuple[str, ...]]:
    """Retain physical grid positions and report unsupported row layouts."""
    cells = {}
    codes = set()
    before = row.find(f"{_tag('trPr')}/{_tag('gridBefore')}")
    start = 1
    if before is not None:
        value = before.get(_tag("val"), "")
        if len(value) > 3 or not value.isascii() or not value.isdigit() or int(value) > _MAX_COLUMNS:
            return {}, ("invalid_layout",)
        start += int(value)
    for cell in row.findall(_tag("tc")):
        spans = cell.findall(f"{_tag('tcPr')}/{_tag('gridSpan')}")
        span = 1
        if spans:
            value = spans[0].get(_tag("val"), "")
            if (len(spans) != 1 or len(value) > 3 or not value.isascii()
                or not value.isdigit() or not 1 <= int(value) <= _MAX_COLUMNS):
                return {}, ("invalid_layout",)
            span = int(value)
        if (span > 1 or cell.find(f"{_tag('tcPr')}/{_tag('vMerge')}") is not None
            or cell.find(f"{_tag('tcPr')}/{_tag('hMerge')}") is not None):
            codes.add("merged_cells")
        if start + span - 1 > _MAX_COLUMNS:
            return {}, ("invalid_layout",)
        for position in range(start, start + span):
            cells[position] = cell
        start += span
    for node in row.iter():
        if node.tag == _tag("tbl"):
            codes.add("nested_table")
        if node.tag in {_tag(name) for name in _REVISION_TAGS}:
            codes.add("unreviewed_revision")
        if node.tag in {_tag(name) for name in _UNSUPPORTED_TAGS}:
            codes.add("unsupported_content")
        if node.tag == _ALTERNATE_CONTENT:
            codes.add("unsupported_content")
        if (node.tag in {_tag(name) for name in _HIDDEN_TAGS}
            and node.get(_tag("val")) not in _VISIBLE_PROPERTY_VALUES):
            codes.add("hidden_content")
    return cells, tuple(sorted(codes))


def _descendant_items(node: ET.Element, kind: str, inherited: tuple[str, ...] = ()) -> list[tuple[ET.Element, tuple[str, ...]]]:
    """Include revision-wrapped tables or rows without counting nested tables."""
    result = []
    pending = [(child, inherited) for child in reversed(node)]
    while pending:
        child, parent_codes = pending.pop()
        codes = set(parent_codes)
        if child.tag in {_tag(name) for name in _REVISION_TAGS}:
            codes.add("unreviewed_revision")
        if child.tag in {_tag(name) for name in _UNSUPPORTED_TAGS}:
            codes.add("unsupported_content")
        if child.tag == _ALTERNATE_CONTENT:
            codes.add("unsupported_content")
        if child.tag == _tag(kind):
            result.append((child, tuple(sorted(codes))))
        elif child.tag != _tag("tbl"):
            pending.extend((descendant, tuple(sorted(codes))) for descendant in reversed(child))
    return result


def _import(root: ET.Element, profiles: tuple[_TableProfile, ...], source_id: str,
            visibility: _StyleVisibility) -> DocxImportResult:
    tables = _descendant_items(root.find(_tag("body")), "tbl")
    result = []
    issues = []
    selected = set()
    for profile in profiles:
        if profile.table_index > len(tables):
            _fail("document: selected table is missing")
        source_table, table_codes = tables[profile.table_index - 1]
        table_style_hidden = visibility.referenced(source_table, f"{_tag('tblPr')}/{_tag('tblStyle')}", "table")
        table_style_uncertain = visibility.uncertain(source_table, f"{_tag('tblPr')}/{_tag('tblStyle')}", "table")
        properties = source_table.findall(_tag("tblPr")) + source_table.findall(_tag("tblGrid"))
        if any(node.tag in {_tag(name) for name in _REVISION_TAGS} for property_node in properties for node in property_node.iter()):
            table_codes = tuple(sorted(set(table_codes) | {"unreviewed_revision"}))
        rows = _descendant_items(source_table, "tr", table_codes)
        if profile.header_row > len(rows):
            _fail("document: selected header row is missing")
        header_row, inherited_header_codes = rows[profile.header_row - 1]
        header, header_issues = _layout(header_row)
        if header_issues or inherited_header_codes or _style_codes(header_row, visibility, table_style_hidden, table_style_uncertain):
            _fail("document: selected header layout requires review")
        columns = dict(profile.columns)
        for key, expected in profile.expected_headers:
            if columns[key] not in header or _cell_text(header[columns[key]]) != expected:
                _fail(f"table {profile.table_index} row {profile.header_row}: header mismatch")
        last = profile.last_data_row if profile.last_data_row is not None else len(rows)
        if profile.first_data_row > len(rows) + 1 or last > len(rows):
            _fail("document: selected data row range is outside the table")
        for index in range(profile.first_data_row, last + 1):
            source_position = (profile.table_index, index)
            if source_position in selected:
                _fail("document profile: overlapping source rows")
            selected.add(source_position)
            source_row, inherited_codes = rows[index - 1]
            cells, codes = _layout(source_row)
            codes = tuple(sorted(set(codes) | set(inherited_codes) | set(_style_codes(source_row, visibility, table_style_hidden, table_style_uncertain))))
            values = {key: _cell_text(cells[column]) if column in cells else None for key, column in profile.columns}
            visible_text = any(
                (node.text or "").strip() for node in source_row.iter()
                if node.tag in {_tag("t"), _tag("delText")}
            )
            if not codes and not visible_text:
                continue
            issue_start = len(issues)
            for code in codes:
                issues.append(DocxImportIssue(code, profile.table_index, index))

            def issue(code: str, key: str) -> None:
                issues.append(DocxImportIssue(code, profile.table_index, index, key, columns.get(key)))

            course_id = values["course_id"]
            if course_id is None or not course_id.strip() or course_id.strip().lower() in _UNKNOWN_IDS:
                course_id = None
                issue("unresolved_course_id", "course_id")
            course_name = values["course_name"]
            if course_name is None or not course_name.strip():
                course_name = None
                issue("missing_course_name", "course_name")
            raw_credit = values["credit"]
            credit = None
            if raw_credit is not None and _CREDIT.fullmatch(raw_credit.strip()):
                candidate = float(raw_credit.strip())
                if math.isfinite(candidate):
                    credit = candidate
            if credit is None:
                issue("unresolved_credit", "credit")
            requirement = profile.requirement
            if "requirement" in columns:
                raw_requirement = values["requirement"]
                mapping = dict(profile.requirement_values)
                if raw_requirement in mapping:
                    requirement = mapping[raw_requirement]
                elif raw_requirement in {kind.value for kind in RequirementKind}:
                    requirement = RequirementKind(raw_requirement)
                else:
                    requirement = RequirementKind.UNKNOWN
                    issue("unmapped_requirement", "requirement")
                if profile.fixed_requirement and requirement != profile.requirement:
                    issue("conflicting_requirement", "requirement")
            term = values.get("recommended_term_text")
            if term is not None and not term.strip():
                term = None
            result.append(DocxCourseRow(
                profile.table_index, index, course_id, course_name, credit, requirement,
                f"table:{profile.table_index}!row:{index}", profile.course_type, profile.group_id,
                term, raw_values=tuple(values.items()), issues=tuple(issues[issue_start:]),
            ))
    result.sort(key=lambda row: (row.table_index, row.row_index))
    issues.sort(key=lambda issue: (issue.table_index, issue.row_index, issue.code, issue.field or ""))
    return DocxImportResult(source_id, tuple(result), tuple(issues))


def load_curriculum_docx(path: str | Path, *, source_id: str, tables: Sequence[Mapping[str, object]]) -> DocxImportResult:
    """Read selected top-level tables using explicit one-based mappings.

Every mapped field requires its exact expected header. Each mapping needs
course_id, course_name and credit columns. Explicit row ranges may describe
different source sections. Overlaps are rejected. Blank rows may be skipped;
all other selected rows remain in the draft, including summaries and ambiguities.
No XML relationship, macro, image, field or embedded object is executed.
"""
    _text(source_id, "source_id")
    profiles = _profiles(tables)
    root, styles = _read_document(path)
    return _import(root, profiles, source_id, _style_visibility(styles))
