"""Artificial OOXML tables only; no real curriculum documents are published."""

from __future__ import annotations

import traceback
import warnings
from pathlib import Path
from struct import unpack_from
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.curriculum.docx_reader import load_curriculum_docx
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import RequirementKind

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_HEADERS = ["课程号", "课程名称", "学分", "建议学期", "课程性质"]
_FIELDS = ["course_id", "course_name", "credit", "recommended_term_text", "requirement"]


def test_clearing_summary_issues_does_not_clear_unreviewed_row_facts(tmp_path):
    from dataclasses import replace

    table = _table()
    ET.SubElement(ET.SubElement(table[1][2], _q("tcPr")), _q("cellDel"))
    draft = _read(_docx(tmp_path, _document(table)))
    partial_copy = replace(draft, issues=())
    assert partial_copy.rows[0].issues
    with pytest.raises(CurriculumNormalizationError, match="unresolved rows"):
        partial_copy.to_version(version_id="DEMO-V1", major="DEMO", cohort="DEMO")


def _q(name: str) -> str:
    return f"{{{_NS}}}{name}"


def _cell(value: str | None) -> ET.Element:
    cell = ET.Element(_q("tc"))
    paragraph = ET.SubElement(cell, _q("p"))
    if value is not None:
        ET.SubElement(ET.SubElement(paragraph, _q("r")), _q("t")).text = value
    return cell


def _row(values: list[str | None]) -> ET.Element:
    row = ET.Element(_q("tr"))
    row.extend(_cell(value) for value in values)
    return row


def _facts(course_id="DEMO101", name="DEMO Course A", credit="2.5", term="2025-1~2025-2", requirement="必修"):
    return [course_id, name, credit, term, requirement]


def _table(values=None) -> ET.Element:
    table = ET.Element(_q("tbl"))
    table.append(_row(_HEADERS))
    for value in values if values is not None else [_facts()]:
        table.append(_row(value))
    return table


def _document(*tables) -> ET.Element:
    root = ET.Element(_q("document"))
    body = ET.SubElement(root, _q("body"))
    body.extend(tables or [_table()])
    return root


def _profile(**overrides):
    profile = {
        "table_index": 1, "header_row": 1,
        "columns": dict(zip(_FIELDS, range(1, 6))),
        "expected_headers": dict(zip(_FIELDS, _HEADERS)),
        "requirement_values": {"必修": "required", "选修": "elective"},
    }
    profile.update(overrides)
    return profile


def _docx(tmp_path: Path, root=None, *, raw=None, parts=None) -> Path:
    path = tmp_path / "DEMO-PRIVATE-DOCX.docx"
    material = {"word/document.xml": raw if raw is not None else ET.tostring(root if root is not None else _document())}
    material.update(parts or {})
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in material.items():
            archive.writestr(name, content)
    return path


def _read(path: Path, *profiles):
    return load_curriculum_docx(path, source_id="mock://docx-demo", tables=list(profiles or [_profile()]))


def _version(result, **metadata):
    return result.to_version(version_id="DEMO-V1", major="DEMO Major", cohort="DEMO Cohort", **metadata)


def _styles(*definitions) -> bytes:
    root = ET.Element(_q("styles"))
    for style_id, kind, parent, hidden in definitions:
        style = ET.SubElement(root, _q("style"), {_q("styleId"): style_id, _q("type"): kind})
        if parent is not None:
            ET.SubElement(style, _q("basedOn"), {_q("val"): parent})
        if hidden:
            ET.SubElement(ET.SubElement(style, _q("rPr")), _q("vanish"))
    return ET.tostring(root)


@pytest.mark.parametrize("inherited", [False, True])
@pytest.mark.parametrize("kind", ["character", "paragraph"])
def test_used_hidden_styles_and_inheritance_cannot_silently_change_source_credit(tmp_path, inherited, kind):
    table = _table([_facts(credit="2")])
    paragraph = table[1][2][0]
    run = ET.SubElement(paragraph, _q("r"))
    ET.SubElement(run, _q("t")).text = "3"
    style_key = "DEMO-CHILD" if inherited else "DEMO-HIDDEN"
    properties = ET.SubElement(run if kind == "character" else paragraph, _q("rPr" if kind == "character" else "pPr"))
    ET.SubElement(properties, _q("rStyle" if kind == "character" else "pStyle"), {_q("val"): style_key})
    styles = _styles(("DEMO-HIDDEN", kind, None, True), ("DEMO-CHILD", kind, "DEMO-HIDDEN", False))
    result = _read(_docx(tmp_path, _document(table), parts={"word/styles.xml": styles}))
    assert len(result.rows) == 1 and any(issue.code == "hidden_style_content" for issue in result.rows[0].issues)
    assert dict(result.rows[0].raw_values)["credit"] == "23"
    with pytest.raises(CurriculumNormalizationError, match="unresolved rows"):
        _version(result)


def test_unused_hidden_styles_do_not_block_selected_visible_rows(tmp_path):
    styles = _styles(("DEMO-UNUSED-HIDDEN", "character", None, True))
    result = _read(_docx(tmp_path, parts={"word/styles.xml": styles}))
    assert not result.issues and _version(result).courses[0].credit == 2.5


@pytest.mark.parametrize("visible_value", ["false", "off", "0"])
def test_direct_visibility_override_clears_hidden_style_for_that_run(tmp_path, visible_value):
    table = _table([_facts(credit="2")])
    run = ET.SubElement(table[1][2][0], _q("r"))
    properties = ET.SubElement(run, _q("rPr"))
    ET.SubElement(properties, _q("rStyle"), {_q("val"): "DEMO-HIDDEN"})
    ET.SubElement(properties, _q("vanish"), {_q("val"): visible_value})
    ET.SubElement(run, _q("t")).text = "3"
    styles = _styles(("DEMO-HIDDEN", "character", None, True))
    result = _read(_docx(tmp_path, _document(table), parts={"word/styles.xml": styles}))
    assert not result.issues and _version(result).courses[0].credit == 23


def test_style_hidden_header_blocks_exact_header_check(tmp_path):
    table = _table()
    properties = ET.SubElement(table[0][0][0][0], _q("rPr"))
    ET.SubElement(properties, _q("rStyle"), {_q("val"): "DEMO-HIDDEN"})
    styles = _styles(("DEMO-HIDDEN", "character", None, True))
    with pytest.raises(CurriculumNormalizationError, match="header layout"):
        _read(_docx(tmp_path, _document(table), parts={"word/styles.xml": styles}))


def test_default_hidden_styles_and_document_defaults_block_unverified_visibility(tmp_path):
    style_root = ET.Element(_q("styles"))
    defaults = ET.SubElement(ET.SubElement(style_root, _q("docDefaults")), _q("rPrDefault"))
    ET.SubElement(ET.SubElement(defaults, _q("rPr")), _q("vanish"))
    with pytest.raises(CurriculumNormalizationError, match="header layout"):
        _read(_docx(tmp_path, parts={"word/styles.xml": ET.tostring(style_root)}))
    style_root = ET.fromstring(_styles(("DEMO-HIDDEN-DEFAULT", "paragraph", None, True)))
    style_root[0].set(_q("default"), "1")
    with pytest.raises(CurriculumNormalizationError, match="header layout"):
        _read(_docx(tmp_path, parts={"word/styles.xml": ET.tostring(style_root)}))


def test_table_hidden_style_is_conservatively_rejected_without_simulating_conditions(tmp_path):
    table = _table()
    ET.SubElement(ET.SubElement(table, _q("tblPr")), _q("tblStyle"), {_q("val"): "DEMO-HIDDEN-TABLE"})
    styles = _styles(("DEMO-HIDDEN-TABLE", "table", None, True))
    with pytest.raises(CurriculumNormalizationError, match="header layout"):
        _read(_docx(tmp_path, _document(table), parts={"word/styles.xml": styles}))


def test_style_inheritance_cycle_is_bounded_and_does_not_erase_hidden_ancestor(tmp_path):
    table = _table()
    properties = ET.SubElement(table[1][2][0][0], _q("rPr"))
    ET.SubElement(properties, _q("rStyle"), {_q("val"): "DEMO-CYCLE-1"})
    styles = _styles(("DEMO-CYCLE-1", "character", "DEMO-CYCLE-2", False),
                     ("DEMO-CYCLE-2", "character", "DEMO-CYCLE-1", True))
    result = _read(_docx(tmp_path, _document(table), parts={"word/styles.xml": styles}))
    assert any(issue.code == "hidden_style_content" for issue in result.issues)


@pytest.mark.parametrize("condition", ["missing_definition", "missing_parent", "cycle"])
def test_unknown_or_cyclic_used_style_references_remain_unresolved(tmp_path, condition):
    table = _table()
    properties = ET.SubElement(table[1][2][0][0], _q("rPr"))
    ET.SubElement(properties, _q("rStyle"), {_q("val"): "DEMO-STYLE"})
    definitions = []
    if condition == "missing_parent":
        definitions = [("DEMO-STYLE", "character", "DEMO-MISSING", False)]
    elif condition == "cycle":
        definitions = [("DEMO-STYLE", "character", "DEMO-STYLE", False)]
    result = _read(_docx(tmp_path, _document(table), parts={"word/styles.xml": _styles(*definitions)}))
    assert any(issue.code == "unresolved_style_reference" for issue in result.issues)
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


def test_style_definition_count_is_bounded(tmp_path):
    definitions = [(f"DEMO-STYLE-{index}", "character", None, False) for index in range(4097)]
    with pytest.raises(CurriculumNormalizationError, match="style count limit"):
        _read(_docx(tmp_path, parts={"word/styles.xml": _styles(*definitions)}))


@pytest.mark.parametrize("header", [False, True])
def test_alternate_content_never_combines_choice_and_fallback_into_confirmed_credit(tmp_path, header):
    table = _table([_facts(credit="")])
    cell = table[0 if header else 1][2]
    cell.clear()
    alternate = ET.SubElement(cell, "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent")
    for branch, value in [("Choice", "2"), ("Fallback", "3")]:
        container = ET.SubElement(alternate, f"{{http://schemas.openxmlformats.org/markup-compatibility/2006}}{branch}")
        run = ET.SubElement(ET.SubElement(container, _q("p")), _q("r"))
        ET.SubElement(run, _q("t")).text = value
    path = _docx(tmp_path, _document(table))
    if header:
        with pytest.raises(CurriculumNormalizationError, match="header layout"):
            _read(path)
    else:
        result = _read(path)
        assert len(result.rows) == 1 and any(issue.code == "unsupported_content" for issue in result.issues)
        with pytest.raises(CurriculumNormalizationError):
            _version(result)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_styles_xml_has_same_dtd_and_entity_boundary(tmp_path, encoding):
    styles = f'<?xml version="1.0" encoding="{encoding}"?><!DOCTYPE styles [<!ENTITY demo "DEMO-PRIVATE">]><styles xmlns="{_NS}"/>'
    with pytest.raises(CurriculumNormalizationError, match="unsupported XML declaration"):
        _read(_docx(tmp_path, parts={"word/styles.xml": styles.encode(encoding)}))


def test_styles_xml_has_same_actual_xml_size_limit(tmp_path, monkeypatch):
    path = _docx(tmp_path, parts={"word/styles.xml": b"x" * 20000})
    monkeypatch.setattr("app.curriculum.docx_reader._MAX_XML_BYTES", 10000)
    with pytest.raises(CurriculumNormalizationError, match="XML size"):
        _read(path)


@pytest.mark.parametrize("styles", [b"DEMO-PRIVATE-MALFORMED", b"<styles/>",
    _styles(("DEMO-PRIVATE-DUPLICATE", "character", None, False), ("DEMO-PRIVATE-DUPLICATE", "character", None, True)),
])
def test_invalid_styles_do_not_echo_source_or_ids(tmp_path, styles):
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_docx(tmp_path, parts={"word/styles.xml": styles}))
    assert "DEMO-PRIVATE" not in "".join(traceback.format_exception(excinfo.value))


def test_explicit_mapping_preserves_source_context_without_inferring_school_rules(tmp_path):
    profile = _profile(course_type="DEMO module", group_id="DEMO group")
    result = _read(_docx(tmp_path), profile)
    assert len(result.rows) == 1 and result.issues == ()
    row = result.rows[0]
    assert row.course_id == "DEMO101" and row.course_name == "DEMO Course A"
    assert row.credit == 2.5 and row.requirement is RequirementKind.REQUIRED
    assert row.course_type == "DEMO module" and row.group_id == "DEMO group"
    assert row.source_record == "table:1!row:2" and row.prerequisites is None
    assert dict(row.raw_values)["credit"] == "2.5"
    group = {"group_id": "DEMO group", "name": "DEMO group", "minimum_credit": None, "source_record": "DEMO group evidence"}
    version = _version(result, group_records=[group], total_credit=9, practice_credit=2, study_years=4)
    assert version.source_id == "mock://docx-demo" and version.complete is False
    assert version.courses[0].recommended_term_text == "2025-1~2025-2"
    assert version.courses[0].recommended_semester is None and version.courses[0].deadline_semester is None
    assert version.courses[0].prerequisites is None and version.total_credit == 9


def test_conversion_requires_explicit_completeness_evidence(tmp_path):
    result = _read(_docx(tmp_path))
    with pytest.raises(CurriculumNormalizationError, match="completeness_evidence"):
        _version(result, complete=True)
    assert _version(result, complete=True, completeness_evidence="mock://approved-completeness").complete is True


def test_header_only_table_is_empty_and_never_inferred_complete(tmp_path):
    result = _read(_docx(tmp_path, _document(_table([]))))
    assert result.rows == () and result.issues == () and not _version(result).complete


def test_split_runs_and_bilingual_paragraphs_preserve_source_name(tmp_path):
    table = _table()
    cell = table[1][1]
    cell.clear()
    paragraph = ET.SubElement(cell, _q("p"))
    for text in ["DEMO ", "中文课程"]:
        ET.SubElement(ET.SubElement(paragraph, _q("r")), _q("t")).text = text
    second = ET.SubElement(cell, _q("p"))
    ET.SubElement(ET.SubElement(second, _q("r")), _q("t")).text = "DEMO English Name"
    result = _read(_docx(tmp_path, _document(table)))
    assert result.rows[0].course_name == "DEMO 中文课程\nDEMO English Name" and not result.issues


@pytest.mark.parametrize("kind", ["vanish", "webHidden"])
@pytest.mark.parametrize("value", [None, "true", "on", "1", "DEMO-UNKNOWN"])
def test_active_hidden_runs_preserve_draft_but_cannot_change_visible_credit(tmp_path, kind, value):
    table = _table([_facts(credit="2")])
    run = ET.SubElement(table[1][2][0], _q("r"))
    properties = ET.SubElement(run, _q("rPr"))
    ET.SubElement(properties, _q(kind), {} if value is None else {_q("val"): value})
    ET.SubElement(run, _q("t")).text = "3"
    result = _read(_docx(tmp_path, _document(table)))
    assert len(result.rows) == 1 and any(issue.code == "hidden_content" for issue in result.rows[0].issues)
    assert dict(result.rows[0].raw_values)["credit"] == "23"
    with pytest.raises(CurriculumNormalizationError, match="unresolved rows"):
        _version(result, complete=True, completeness_evidence="mock://complete")


@pytest.mark.parametrize("kind", ["vanish", "webHidden"])
@pytest.mark.parametrize("value", ["false", "off", "0"])
def test_explicitly_disabled_hidden_properties_remain_visible(tmp_path, kind, value):
    table = _table([_facts(credit="2")])
    run = ET.SubElement(table[1][2][0], _q("r"))
    properties = ET.SubElement(run, _q("rPr"))
    ET.SubElement(properties, _q(kind), {_q("val"): value})
    ET.SubElement(run, _q("t")).text = "3"
    result = _read(_docx(tmp_path, _document(table)))
    assert not result.issues and _version(result).courses[0].credit == 23


def test_hidden_header_text_blocks_mapping_validation(tmp_path):
    table = _table()
    run = table[0][0][0][0]
    ET.SubElement(ET.SubElement(run, _q("rPr")), _q("vanish"))
    with pytest.raises(CurriculumNormalizationError, match="header layout"):
        _read(_docx(tmp_path, _document(table)))


@pytest.mark.parametrize("course_id", [None, "", "  ", "待确认", "unknown", "PENDING"])
def test_pending_ids_remain_rows_and_cannot_be_projected(tmp_path, course_id):
    result = _read(_docx(tmp_path, _document(_table([_facts(course_id=course_id), _facts(course_id="DEMO102")]))))
    assert len(result.rows) == 2 and result.rows[0].course_id is None
    assert result.rows[0].issues[0].code == "unresolved_course_id"
    assert dict(result.rows[0].raw_values)["course_id"] in {course_id, ""}
    with pytest.raises(CurriculumNormalizationError, match="unresolved rows"):
        _version(result)


@pytest.mark.parametrize("credit", [None, "", "待确认", "2 学分", "-1", "NaN", "Infinity", "2,5", "1e2", "9" * 500])
def test_credit_ambiguity_is_retained_and_never_coerced_or_dropped(tmp_path, credit):
    result = _read(_docx(tmp_path, _document(_table([_facts(credit=credit)]))))
    assert len(result.rows) == 1 and result.rows[0].credit is None
    assert [issue.code for issue in result.issues] == ["unresolved_credit"]
    assert dict(result.rows[0].raw_values)["credit"] in {credit, ""}
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


@pytest.mark.parametrize("credit,expected", [("0", 0), (" +2.50 ", 2.5), (".5", .5)])
def test_plain_decimal_credits_are_read_from_explicit_credit_columns(tmp_path, credit, expected):
    result = _read(_docx(tmp_path, _document(_table([_facts(credit=credit)]))))
    assert result.rows[0].credit == expected and not result.issues


def test_fixed_section_classification_is_explicit_and_not_inferred_from_name(tmp_path):
    profile = _profile(requirement="elective", course_type="DEMO 专必 text")
    del profile["columns"]["requirement"]
    del profile["expected_headers"]["requirement"]
    del profile["requirement_values"]
    result = _read(_docx(tmp_path), profile)
    assert result.rows[0].requirement is RequirementKind.ELECTIVE and not result.issues
    del profile["requirement"]
    assert _read(_docx(tmp_path), profile).rows[0].requirement is RequirementKind.UNKNOWN


@pytest.mark.parametrize("value", ["  必修", "DEMO-PRIVATE-UNCONFIRMED", ""])
def test_requirement_mapping_is_exact_and_unknown_values_require_review(tmp_path, value):
    result = _read(_docx(tmp_path, _document(_table([_facts(requirement=value)]))))
    assert result.rows[0].requirement is RequirementKind.UNKNOWN
    assert any(issue.code == "unmapped_requirement" for issue in result.issues)
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


def test_fixed_and_row_classification_conflict_blocks_conversion(tmp_path):
    result = _read(_docx(tmp_path), _profile(requirement="elective"))
    assert any(issue.code == "conflicting_requirement" for issue in result.issues)
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


def test_blank_rows_skip_but_summary_rows_and_missing_names_are_preserved(tmp_path):
    result = _read(_docx(tmp_path, _document(_table([
        [None] * 5, _facts(name=""), ["DEMO total", None, "9", None, None], _facts(course_id="DEMO102"),
    ]))))
    assert [row.row_index for row in result.rows] == [3, 4, 5]
    assert result.rows[0].course_name is None and result.rows[1].course_id == "DEMO total"
    assert any(issue.code == "missing_course_name" for issue in result.rows[0].issues)
    assert result.rows[2].issues == ()
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


def test_multi_table_source_order_and_explicit_section_ranges(tmp_path):
    first = _table([_facts(course_id="DEMO101"), _facts(course_id="DEMO102")])
    second = _table([_facts(course_id="DEMO201")])
    result = _read(_docx(tmp_path, _document(first, second)),
                   _profile(table_index=2), _profile(first_data_row=3), _profile(last_data_row=2))
    assert [row.course_id for row in result.rows] == ["DEMO101", "DEMO102", "DEMO201"]
    assert [row.source_record for row in result.rows] == ["table:1!row:2", "table:1!row:3", "table:2!row:2"]


def test_overlapping_profiles_do_not_count_source_rows_twice(tmp_path):
    with pytest.raises(CurriculumNormalizationError, match="overlapping"):
        _read(_docx(tmp_path), _profile(), _profile())


@pytest.mark.parametrize("kind", ["gridSpan", "vMerge", "hMerge"])
def test_merged_data_rows_are_retained_and_require_review(tmp_path, kind):
    table = _table()
    properties = ET.SubElement(table[1][1], _q("tcPr"))
    ET.SubElement(properties, _q(kind), {_q("val"): "2" if kind == "gridSpan" else "restart"})
    result = _read(_docx(tmp_path, _document(table)))
    assert len(result.rows) == 1 and any(issue.code == "merged_cells" for issue in result.issues)
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


def test_nested_table_rows_are_not_silently_flattened_into_extra_courses(tmp_path):
    table = _table()
    table[1][1].append(_table([_facts(course_id="DEMO-NESTED")]))
    result = _read(_docx(tmp_path, _document(table)))
    assert len(result.rows) == 1 and any(issue.code == "nested_table" for issue in result.issues)
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


@pytest.mark.parametrize("wrapper", ["sdt", "DEMO-unknown-wrapper"])
def test_wrapped_cells_with_nonempty_source_text_are_never_skipped(tmp_path, wrapper):
    table = _table()
    row = table[1]
    cells = list(row)
    for cell in cells:
        row.remove(cell)
        ET.SubElement(row, _q(wrapper)).append(cell)
    result = _read(_docx(tmp_path, _document(table)))
    assert len(result.rows) == 1 and result.rows[0].issues
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


@pytest.mark.parametrize("kind", ["ins", "del", "moveFrom", "moveTo"])
def test_revision_wrapped_rows_remain_in_draft(tmp_path, kind):
    table = _table()
    row = table[1]
    table.remove(row)
    ET.SubElement(table, _q(kind)).append(row)
    result = _read(_docx(tmp_path, _document(table)))
    assert len(result.rows) == 1 and result.rows[0].course_id == "DEMO101"
    assert any(issue.code == "unreviewed_revision" for issue in result.rows[0].issues)


@pytest.mark.parametrize("kind", ["cellIns", "cellDel", "cellMerge"])
@pytest.mark.parametrize("row_index", [0, 1])
def test_cell_revisions_block_header_or_preserve_unreviewed_data_row(tmp_path, kind, row_index):
    table = _table()
    ET.SubElement(ET.SubElement(table[row_index][2], _q("tcPr")), _q(kind))
    path = _docx(tmp_path, _document(table))
    if row_index == 0:
        with pytest.raises(CurriculumNormalizationError, match="header layout"):
            _read(path)
    else:
        result = _read(path)
        assert len(result.rows) == 1 and any(issue.code == "unreviewed_revision" for issue in result.rows[0].issues)
        with pytest.raises(CurriculumNormalizationError):
            _version(result)


def test_table_grid_revision_blocks_entire_mapping(tmp_path):
    table = _table()
    ET.SubElement(ET.SubElement(table, _q("tblGrid")), _q("tblGridChange"))
    with pytest.raises(CurriculumNormalizationError, match="header layout"):
        _read(_docx(tmp_path, _document(table)))


@pytest.mark.parametrize("kind", ["ins", "del"])
def test_revision_wrapped_tables_cannot_shift_selected_table_identity(tmp_path, kind):
    root = _document()
    body = root.find(_q("body"))
    table = body[0]
    body.remove(table)
    ET.SubElement(body, _q(kind)).append(table)
    body.append(_table([_facts(course_id="DEMO201")]))
    path = _docx(tmp_path, root)
    with pytest.raises(CurriculumNormalizationError, match="header layout"):
        _read(path)
    assert _read(path, _profile(table_index=2)).rows[0].course_id == "DEMO201"


@pytest.mark.parametrize("kind", ["drawing", "object", "fldSimple"])
def test_images_objects_and_cached_fields_are_not_treated_as_verified_text(tmp_path, kind):
    table = _table()
    ET.SubElement(table[1][1], _q(kind))
    result = _read(_docx(tmp_path, _document(table)))
    assert any(issue.code == "unsupported_content" for issue in result.issues)
    with pytest.raises(CurriculumNormalizationError):
        _version(result)


def test_external_relationships_are_not_followed(tmp_path):
    relation = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="DEMO" TargetMode="External" Target="file:///DEMO-PRIVATE-PATH"/></Relationships>'
    result = _read(_docx(tmp_path, parts={"word/_rels/document.xml.rels": relation}))
    assert not result.issues and result.rows[0].course_id == "DEMO101"


@pytest.mark.parametrize("overrides", [
    {"table_index": 0}, {"table_index": True}, {"header_row": -1}, {"first_data_row": 1},
    {"last_data_row": 1}, {"course_type": ""}, {"group_id": 3}, {"requirement": "DEMO-PRIVATE-POLICY"},
    {"columns": {"course_id": 1, "course_name": 1, "credit": 3}},
    {"columns": {"course_id": 1, "course_name": 2, "credit": 999}},
    {"columns": {"course_id": 1, "course_name": 2}},
    {"columns": {"course_id": 1, "course_name": 2, "credit": 3, "DEMO-PRIVATE-FIELD": 4}},
    {"expected_headers": {"course_id": "DEMO-PRIVATE-HEADER"}},
    {"requirement_values": {"DEMO-PRIVATE-POLICY": "DEMO-UNKNOWN"}},
    {"DEMO-PRIVATE-FIELD": "DEMO-PRIVATE-VALUE"},
])
def test_invalid_profiles_fail_before_reading_and_do_not_echo_inputs(tmp_path, overrides):
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(tmp_path / "DEMO-PRIVATE-MISSING.docx", _profile(**overrides))
    assert "DEMO-PRIVATE" not in str(excinfo.value) and "unreadable DOCX" not in str(excinfo.value)


@pytest.mark.parametrize("tables", [None, [], "DEMO-PRIVATE-TABLE", [None]])
def test_profiles_require_an_explicit_nonempty_sequence(tmp_path, tables):
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_docx(tmp_path / "DEMO-PRIVATE-MISSING.docx", source_id="mock://docx-demo", tables=tables)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("overrides", [{"table_index": 2}, {"header_row": 9}, {"last_data_row": 9}, {"first_data_row": 9}])
def test_missing_selections_never_fall_back_to_another_table_or_row(tmp_path, overrides):
    with pytest.raises(CurriculumNormalizationError):
        _read(_docx(tmp_path), _profile(**overrides))


def test_exact_header_validation_detects_wrong_column_mapping(tmp_path):
    profile = _profile()
    profile["expected_headers"]["credit"] = "DEMO-PRIVATE-HEADER"
    with pytest.raises(CurriculumNormalizationError, match="table 1 row 1: header mismatch") as excinfo:
        _read(_docx(tmp_path), profile)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("grid", ["-1", "0", "999", "9" * 5000, "DEMO-PRIVATE-GRID"])
def test_invalid_grid_spans_are_draft_issues_without_integer_conversion_failures(tmp_path, grid):
    table = _table()
    ET.SubElement(ET.SubElement(table[1][0], _q("tcPr")), _q("gridSpan"), {_q("val"): grid})
    result = _read(_docx(tmp_path, _document(table)))
    assert len(result.rows) == 1 and any(issue.code == "invalid_layout" for issue in result.issues)
    assert "DEMO-PRIVATE" not in repr(result)


@pytest.mark.parametrize("raw", [b"DEMO-PRIVATE-BROKEN", b"<DEMO-PRIVATE-BROKEN", b"<document/>"])
def test_bad_xml_or_wrong_root_never_echoes_source_or_filename(tmp_path, raw):
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_docx(tmp_path, raw=raw))
    formatted = "".join(traceback.format_exception(excinfo.value))
    assert "DEMO-PRIVATE" not in formatted and str(tmp_path) not in str(excinfo.value)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_dtd_and_entities_are_rejected_before_xml_expansion(tmp_path, encoding):
    raw = f'<?xml version="1.0" encoding="{encoding}"?><!DOCTYPE document [<!ENTITY demo "DEMO-PRIVATE">]><document xmlns="{_NS}"/>'
    with pytest.raises(CurriculumNormalizationError, match="unsupported XML declaration"):
        _read(_docx(tmp_path, raw=raw.encode(encoding)))


def test_unknown_xml_encoding_does_not_escape_as_lookup_error(tmp_path):
    raw = f'<?xml version="1.0" encoding="DEMO-PRIVATE-ENCODING"?><document xmlns="{_NS}"/>'
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(_docx(tmp_path, raw=raw.encode()))
    assert str(excinfo.value) == "document: invalid or unreadable DOCX"


@pytest.mark.parametrize("member", ["word/document.xml", "../DEMO-PRIVATE-PART", "/DEMO-PRIVATE-PART", "word\\DEMO-PRIVATE-PART"])
def test_duplicate_or_unsafe_archive_members_are_rejected(tmp_path, member):
    path = _docx(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(path, "a") as archive:
            archive.writestr(member, b"DEMO")
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_symlink_members_are_not_interpreted(tmp_path):
    path = _docx(tmp_path)
    info = ZipInfo("word/DEMO-PRIVATE-LINK")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with ZipFile(path, "a") as archive:
        archive.writestr(info, b"/DEMO-PRIVATE-TARGET")
    with pytest.raises(CurriculumNormalizationError, match="invalid archive member"):
        _read(path)


@pytest.mark.parametrize("limit,expected", [
    ("_MAX_FILE_BYTES", "file size"), ("_MAX_XML_BYTES", "XML size"),
    ("_MAX_TOTAL_BYTES", "archive size"), ("_MAX_ARCHIVE_MEMBERS", "archive member"),
])
def test_real_size_limits_are_enforced_before_parsing(tmp_path, monkeypatch, limit, expected):
    path = _docx(tmp_path, parts={"word/extra.xml": b"x" * 10000})
    monkeypatch.setattr(f"app.curriculum.docx_reader.{limit}", 1)
    with pytest.raises(CurriculumNormalizationError, match=expected):
        _read(path)


def test_corrupt_compressed_stream_is_sanitized(tmp_path):
    path = _docx(tmp_path)
    with ZipFile(path) as archive:
        offset = archive.getinfo("word/document.xml").header_offset
    data = bytearray(path.read_bytes())
    filename, extra = unpack_from("<HH", data, offset + 26)
    data[offset + 30 + filename + extra] = 0xFF
    path.write_bytes(data)
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert str(excinfo.value) == "document: invalid or unreadable DOCX"


@pytest.mark.parametrize("mode", ["missing", "not_zip", "missing_xml"])
def test_unreadable_input_has_no_path_or_fallback_data(tmp_path, mode):
    path = tmp_path / "DEMO-PRIVATE-FILE.docx"
    if mode == "not_zip":
        path.write_bytes(b"DEMO-PRIVATE-CONTENT")
    elif mode == "missing_xml":
        with ZipFile(path, "w") as archive:
            archive.writestr("DEMO-PRIVATE-OTHER.xml", b"DEMO")
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _read(path)
    assert str(excinfo.value) == "document: invalid or unreadable DOCX"


def test_source_id_is_validated_even_for_empty_document(tmp_path):
    with pytest.raises(CurriculumNormalizationError, match="source_id"):
        load_curriculum_docx(_docx(tmp_path), source_id="", tables=[_profile()])
