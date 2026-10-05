"""Positional DOCX profiles: explicit positions, structural guards, fail closed.

The real Case A plan documents carry no column-label row, so header mode cannot
read them. These tests lock the two-mode contract:

- header mode is unchanged and still requires exact literal headers;
- positional mode reads declared positions only, and refuses to guess: a missing
  guard, a narrower row, a wrong table width, a shifted anchor, a horizontal
  merge over a mapped column, or a mode field mix all fail closed.

Every fixture here is synthetic. No real school document is committed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from app.curriculum.docx_reader import load_curriculum_docx
from app.curriculum.errors import CurriculumNormalizationError

# --------------------------------------------------------------------------
# synthetic document builders
# --------------------------------------------------------------------------


def _write(path: Path, rows: list[list[str]]) -> Path:
    """Write a table, keeping rows ragged so a short row stays short."""
    document = Document()
    table = document.add_table(rows=0, cols=max(len(r) for r in rows))
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = value
        # Drop the cells this row does not declare, so the physical row is truly
        # narrower than the table (python-docx pads rows to the full grid).
        if len(row) < len(cells):
            for cell in cells[len(row):]:
                cell._element.getparent().remove(cell._element)
    document.save(str(path))
    return path


def _positional_doc(path: Path) -> Path:
    """Two blank rows, then data: the real header-less shape."""
    return _write(path, [
        [""],
        [""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["2", "DEMO102", "示例课程二", "2.5", "2026-1"],
    ])


def _header_doc(path: Path) -> Path:
    return _write(path, [
        ["课程号", "课程名", "学分", "学期"],
        ["DEMO101", "示例课程一", "3", "2025-1"],
    ])


def _positional_profile(**overrides) -> dict:
    profile = {
        "mode": "positional",
        "table_index": 1,
        "data_start_row": 3,
        "column_count": 5,
        "columns": {"sequence": 1, "course_id": 2, "course_name": 3, "credit": 4,
                    "recommended_term_text": 5},
        # The course-row discriminator: a real row always has a numeric index in
        # the sequence column; a section label does not.
        "row_kind": {"column": 1, "condition": "numeric"},
        "row_filter": [
            {"column": 1, "condition": "numeric"},
            {"column": 2, "condition": "nonempty"},
            {"column": 4, "condition": "numeric"},
        ],
        "identity": {"column": 2, "values": ["DEMO101"]},
        "requirement": "required",
        "course_type": "示例分区",
    }
    profile.update(overrides)
    return profile


def _header_profile(**overrides) -> dict:
    profile = {
        "table_index": 1,
        "header_row": 1,
        "columns": {"course_id": 1, "course_name": 2, "credit": 3, "recommended_term_text": 4},
        "expected_headers": {"course_id": "课程号", "course_name": "课程名",
                             "credit": "学分", "recommended_term_text": "学期"},
        "requirement": "required",
    }
    profile.update(overrides)
    return profile


# ==========================================================================
# Header regression: the old contract must not loosen
# ==========================================================================

def test_header_mode_still_reads_selectively(tmp_path: Path) -> None:
    draft = load_curriculum_docx(_header_doc(tmp_path / "h.docx"), source_id="mock://h",
                                 tables=[_header_profile()])
    assert [row.course_id for row in draft.rows] == ["DEMO101"]
    assert draft.rows[0].credit == 3.0
    assert draft.rows[0].recommended_term_text == "2025-1"
    assert draft.issues == ()


def test_header_mode_still_requires_expected_headers(tmp_path: Path) -> None:
    profile = _header_profile()
    del profile["expected_headers"]
    with pytest.raises(CurriculumNormalizationError, match="missing required field"):
        load_curriculum_docx(_header_doc(tmp_path / "h.docx"), source_id="mock://h", tables=[profile])


def test_header_mode_still_rejects_a_header_mismatch(tmp_path: Path) -> None:
    profile = _header_profile(expected_headers={
        "course_id": "课程号", "course_name": "课程名", "credit": "学分",
        "recommended_term_text": "建议学期",
    })
    with pytest.raises(CurriculumNormalizationError, match="header mismatch"):
        load_curriculum_docx(_header_doc(tmp_path / "h.docx"), source_id="mock://h", tables=[profile])


def test_header_mode_missing_table_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="selected table is missing"):
        load_curriculum_docx(_header_doc(tmp_path / "h.docx"), source_id="mock://h",
                             tables=[_header_profile(table_index=4)])


# ==========================================================================
# Positional happy path
# ==========================================================================

def test_positional_profile_reads_a_header_less_table(tmp_path: Path) -> None:
    draft = load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                                 tables=[_positional_profile()])
    assert draft.issues == ()
    assert [(r.course_id, r.course_name, r.credit, r.recommended_term_text) for r in draft.rows] == [
        ("DEMO101", "示例课程一", 3.0, "2025-1"),
        ("DEMO102", "示例课程二", 2.5, "2026-1"),
    ]
    assert draft.rows[0].requirement.value == "required"
    assert draft.rows[0].source_record == "table:1!row:3"


def test_positional_profile_converts_to_a_version(tmp_path: Path) -> None:
    draft = load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                                 tables=[_positional_profile()])
    version = draft.to_version(version_id="demo", major="示例专业", cohort="2025级", complete=False)
    assert [course.course_id for course in version.courses] == ["DEMO101", "DEMO102"]


def test_positional_row_filter_drops_declared_non_data_rows(tmp_path: Path) -> None:
    """Module headers and a declared summary label are dropped by the rules."""
    path = _write(tmp_path / "mixed.docx", [
        [""],
        [""],
        ["", "本研贯通课", "", "", ""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["2", "小计", "", "3", ""],
    ])
    profile = _positional_profile(data_start_row=2)
    # A declared exclusion label; no semantic guessing is involved.
    profile["exclude"] = [{"column": 2, "condition": "equals", "values": ["小计", "合计"]}]
    draft = load_curriculum_docx(path, source_id="mock://mix", tables=[profile])
    assert [row.course_id for row in draft.rows] == ["DEMO101"]
    assert draft.issues == ()


def test_positional_row_filter_without_labels_still_drops_blank_rows(tmp_path: Path) -> None:
    path = _write(tmp_path / "blankish.docx", [
        [""],
        [""],
        ["", "本研贯通课", "", "", ""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["", "", "", "", ""],
    ])
    draft = load_curriculum_docx(path, source_id="mock://blankish",
                                 tables=[_positional_profile(data_start_row=2)])
    assert [row.course_id for row in draft.rows] == ["DEMO101"]


def test_positional_profile_can_target_a_later_data_row(tmp_path: Path) -> None:
    path = _write(tmp_path / "later.docx", [
        [""],
        [""],
        ["", "本研贯通课", "", "", ""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
    ])
    draft = load_curriculum_docx(path, source_id="mock://later",
                                 tables=[_positional_profile(data_start_row=2)])
    assert [row.course_id for row in draft.rows] == ["DEMO101"]


# ==========================================================================
# Positional fail-closed
# ==========================================================================

def test_no_profile_rejects_a_header_less_document(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="expected table mappings"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p", tables=[])


def test_header_mode_profile_cannot_read_a_header_less_document(tmp_path: Path) -> None:
    """There is no automatic fallback from header mode into positional mode."""
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_header_profile()])


def test_positional_profile_requires_data_start_row(tmp_path: Path) -> None:
    profile = _positional_profile()
    del profile["data_start_row"]
    with pytest.raises(CurriculumNormalizationError, match="missing required field"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[profile])


def test_positional_profile_requires_core_columns(tmp_path: Path) -> None:
    profile = _positional_profile()
    del profile["columns"]["credit"]
    with pytest.raises(CurriculumNormalizationError, match="core course columns"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[profile])


def test_positional_profile_rejects_an_unknown_missing_table(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="selected table is missing"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(table_index=7)])


@pytest.mark.parametrize("start,label", [(9, "selected data row range"), (0, "expected a positive integer")])
def test_positional_profile_rejects_a_bad_data_start_row(tmp_path: Path, start: int, label: str) -> None:
    with pytest.raises(CurriculumNormalizationError, match=label):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(data_start_row=start)])


def test_positional_profile_rejects_a_narrower_physical_row(tmp_path: Path) -> None:
    path = _write(tmp_path / "narrow.docx", [
        [""],
        [""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["2", "DEMO102", "示例课程二", "2.5"],
    ])
    with pytest.raises(CurriculumNormalizationError, match="narrower than the mapped columns"):
        load_curriculum_docx(path, source_id="mock://narrow", tables=[_positional_profile()])


def test_positional_profile_rejects_a_wider_than_declared_table(tmp_path: Path) -> None:
    path = _write(tmp_path / "wide.docx", [
        [""],
        [""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1", "extra", "extra"],
    ])
    with pytest.raises(CurriculumNormalizationError, match="does not match the profile"):
        load_curriculum_docx(path, source_id="mock://wide",
                             tables=[_positional_profile(column_count=5)])


def test_positional_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="does not match the profile"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(identity={"column": 2, "values": ["OTHER999"]})])


def test_positional_identity_must_map_a_declared_column(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="identity: column is not declared"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(identity={"column": 9, "values": ["DEMO101"]})])


def test_positional_identity_on_another_declared_column_still_guards(tmp_path: Path) -> None:
    """The anchor may use any declared column; a wrong value still fails closed."""
    with pytest.raises(CurriculumNormalizationError, match="does not match the profile"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(
                                 identity={"column": 3, "values": ["不存在的课程名"]})])


def test_positional_row_filter_must_map_a_declared_column(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="row_filter: column is not declared"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(row_filter=[{"column": 9, "condition": "nonempty"}])])


@pytest.mark.parametrize("bad", ["guess", "", None, 3])
def test_positional_row_filter_rejects_unsupported_conditions(tmp_path: Path, bad) -> None:
    with pytest.raises(CurriculumNormalizationError, match="row_filter: unsupported condition"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(row_filter=[{"column": 2, "condition": bad}])])


def test_positional_row_filter_equals_requires_declared_values(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="equals requires declared values"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(row_filter=[{"column": 2, "condition": "equals"}])])


def test_positional_column_count_must_cover_the_mapped_columns(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="column_count is narrower"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(column_count=3)])


# ==========================================================================
# Mode separation: the two modes never mix fields
# ==========================================================================

@pytest.mark.parametrize("field,value", [
    ("header_row", 1),
    ("expected_headers", {"course_id": "课程号", "course_name": "课程名", "credit": "学分"}),
])
def test_positional_mode_rejects_header_only_fields(tmp_path: Path, field: str, value) -> None:
    with pytest.raises(CurriculumNormalizationError, match="invalid fields"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(**{field: value})])


@pytest.mark.parametrize("field,value", [
    ("data_start_row", 3),
    ("identity", {"column": 1, "values": ["DEMO101"]}),
    ("row_filter", [{"column": 1, "condition": "nonempty"}]),
    ("column_count", 4),
])
def test_header_mode_rejects_positional_only_fields(tmp_path: Path, field: str, value) -> None:
    with pytest.raises(CurriculumNormalizationError, match="invalid fields"):
        load_curriculum_docx(_header_doc(tmp_path / "h.docx"), source_id="mock://h",
                             tables=[_header_profile(**{field: value})])


def test_positional_mode_cannot_smuggle_an_empty_expected_headers(tmp_path: Path) -> None:
    """An empty expected_headers is not a positional back door."""
    with pytest.raises(CurriculumNormalizationError, match="invalid fields"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(expected_headers={})])


def test_header_mode_cannot_be_selected_without_its_fields(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="missing required field"):
        load_curriculum_docx(_header_doc(tmp_path / "h.docx"), source_id="mock://h",
                             tables=[{"mode": "header", "table_index": 1, "columns": {"course_id": 1,
                                      "course_name": 2, "credit": 3}}])


def test_unknown_mode_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="unsupported mode"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(mode="auto")])


def test_positional_mode_rejects_extra_fields(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="invalid fields"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(DEMO_PRIVATE_FIELD="DEMO-PRIVATE-VALUE")])


# ==========================================================================
# Structural drift
# ==========================================================================

def test_shifted_columns_are_rejected_instead_of_misread(tmp_path: Path) -> None:
    """The whole course_id/course_name block moved one column right.

    Positions now point at the wrong cells (course_id reads the sequence number),
    so the declared anchor no longer matches and the import must fail rather
    than silently classify the wrong text.
    """
    path = _write(tmp_path / "shifted.docx", [
        [""],
        [""],
        ["", "1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["", "2", "DEMO102", "示例课程二", "2.5", "2026-1"],
    ])
    with pytest.raises(CurriculumNormalizationError, match="does not match the profile"):
        load_curriculum_docx(path, source_id="mock://shifted", tables=[_positional_profile()])


def test_shifted_columns_without_anchor_still_fail_on_width(tmp_path: Path) -> None:
    """Even with no anchor guard, a width change must not be read silently."""
    path = _write(tmp_path / "shifted2.docx", [
        [""],
        [""],
        ["", "1", "DEMO101", "示例课程一", "3", "2025-1"],
    ])
    profile = _positional_profile(column_count=5)
    del profile["identity"]
    with pytest.raises(CurriculumNormalizationError, match="does not match the profile"):
        load_curriculum_docx(path, source_id="mock://shifted2", tables=[profile])


def test_horizontal_merge_over_a_mapped_column_is_rejected(tmp_path: Path) -> None:
    """A merged cell would make a declared position ambiguous, so it fails."""
    document = Document()
    table = document.add_table(rows=0, cols=5)
    table.add_row()
    table.add_row()
    row = table.add_row()
    row.cells[0].text = "1"                             # the row-kind discriminator
    merged = row.cells[1].merge(row.cells[2])          # covers columns 2-3
    merged.text = "DEMO101"
    row.cells[3].text = "3"
    row.cells[4].text = "2025-1"
    document.save(str(tmp_path / "merged.docx"))
    with pytest.raises(CurriculumNormalizationError, match="merged cells overlap mapped columns"):
        load_curriculum_docx(tmp_path / "merged.docx", source_id="mock://merged",
                             tables=[_positional_profile()])


def test_foreign_section_merge_outside_mapped_columns_is_tolerated(tmp_path: Path) -> None:
    """A vertical section label spanning unmapped columns does not block a row."""
    document = Document()
    table = document.add_table(rows=0, cols=5)
    table.add_row()
    table.add_row()
    header = table.add_row()
    header.cells[0].text = "示例模块"
    data = table.add_row()
    for index, value in enumerate(["1", "DEMO101", "示例课程一", "3", "2025-1"]):
        data.cells[index].text = value
    document.save(str(tmp_path / "section.docx"))
    draft = load_curriculum_docx(tmp_path / "section.docx", source_id="mock://section",
                                 tables=[_positional_profile()])
    assert [row.course_id for row in draft.rows] == ["DEMO101"]


# ==========================================================================
# Row selection must not be a way to bypass the structural guards
# ==========================================================================

def _kind_row(sequence: str, course_id: str, name: str, credit: str, term: str = "2025-1") -> list[str]:
    return [sequence, course_id, name, credit, term]


def test_row_kind_absent_means_a_section_row_is_skipped(tmp_path: Path) -> None:
    """Test 3: no discriminator -> definitely not a course row -> skip."""
    path = _write(tmp_path / "section_rows.docx", [
        [""], [""],
        ["", "本研贯通课", "本研贯通课", "本研贯通课", "本研贯通课"],
        _kind_row("1", "DEMO101", "示例课程一", "3"),
        ["", "专业提升课", "专业提升课", "专业提升课", "专业提升课"],
        _kind_row("2", "DEMO102", "示例课程二", "2"),
    ])
    draft = load_curriculum_docx(path, source_id="mock://sections", tables=[_positional_profile()])
    assert [row.course_id for row in draft.rows] == ["DEMO101", "DEMO102"]
    assert draft.issues == ()


def test_row_kind_present_but_course_id_cell_missing_is_rejected(tmp_path: Path) -> None:
    """Test 1: it claims to be a course row, but the course_id cell is absent."""
    path = _write(tmp_path / "missing_id.docx", [
        [""], [""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["2"],
    ])
    with pytest.raises(CurriculumNormalizationError, match="narrower than the mapped columns"):
        load_curriculum_docx(path, source_id="mock://missingid", tables=[_positional_profile()])


def test_row_kind_present_but_credit_cell_missing_is_rejected(tmp_path: Path) -> None:
    """Test 2: discriminator and course_id exist, the credit cell is absent."""
    path = _write(tmp_path / "missing_credit.docx", [
        [""], [""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["2", "DEMO102", "示例课程二"],
    ])
    with pytest.raises(CurriculumNormalizationError, match="narrower than the mapped columns"):
        load_curriculum_docx(path, source_id="mock://missingcredit", tables=[_positional_profile()])


def test_row_kind_present_but_a_selector_fails_is_rejected(tmp_path: Path) -> None:
    """A row that claims to be a course row but has a bad selector fails closed."""
    path = _write(tmp_path / "bad_selector.docx", [
        [""], [""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["2", "DEMO102", "示例课程二", "not-a-credit", "2026-1"],
    ])
    with pytest.raises(CurriculumNormalizationError, match="incomplete for the declared selectors"):
        load_curriculum_docx(path, source_id="mock://badselector", tables=[_positional_profile()])


def test_complete_course_rows_are_read_normally(tmp_path: Path) -> None:
    """Test 4: every selector holds on a full row -> normal read."""
    path = _write(tmp_path / "complete.docx", [
        [""], [""],
        _kind_row("1", "DEMO101", "示例课程一", "3", "2025-1"),
        _kind_row("2", "DEMO102", "示例课程二", "2.5", "2026-1"),
    ])
    draft = load_curriculum_docx(path, source_id="mock://complete", tables=[_positional_profile()])
    assert [(r.course_id, r.credit, r.recommended_term_text) for r in draft.rows] == [
        ("DEMO101", 3.0, "2025-1"), ("DEMO102", 2.5, "2026-1"),
    ]
    assert draft.issues == ()


def test_row_filter_requires_an_explicit_row_kind(tmp_path: Path) -> None:
    profile = _positional_profile()
    del profile["row_kind"]
    with pytest.raises(CurriculumNormalizationError, match="row_filter requires an explicit row_kind"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[profile])


def test_row_kind_must_use_a_numeric_discriminator(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="only a numeric discriminator"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(row_kind={"column": 1, "condition": "nonempty"})])


def test_row_kind_must_map_a_declared_column(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError, match="row_kind: column is not declared"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[_positional_profile(row_kind={"column": 9, "condition": "numeric"})])


def test_row_kind_must_also_be_a_selector(tmp_path: Path) -> None:
    profile = _positional_profile(row_filter=[{"column": 2, "condition": "nonempty"},
                                              {"column": 4, "condition": "numeric"}])
    with pytest.raises(CurriculumNormalizationError, match="must also be a declared selector"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[profile])


def test_selector_must_read_an_identifying_column(tmp_path: Path) -> None:
    """A selector over a non-identifying column could skip every row: rejected."""
    profile = _positional_profile(**{
        # "requirement" is a legal mapped field but not an identifying column,
        # so it can never serve as a course-row selector.
        "columns": {"sequence": 1, "course_id": 2, "course_name": 3, "credit": 4,
                    "requirement": 5},
        "row_filter": [{"column": 5, "condition": "nonempty"}],
        "row_kind": {"column": 5, "condition": "numeric"},
        "identity": {"column": 2, "values": ["DEMO101"]},
    })
    with pytest.raises(CurriculumNormalizationError, match="selector must read an identifying"):
        load_curriculum_docx(_positional_doc(tmp_path / "p.docx"), source_id="mock://p",
                             tables=[profile])
