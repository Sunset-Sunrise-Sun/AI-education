"""The target plan's professional-elective requirement is one explicit group.

Architecture-confirmed modelling of the real 网络空间安全 plan:

- table 6 ("（专业选修课）") holds 37 courses / 86 course credits, and the plan
  states a single 23-credit requirement (table 7 summary, repeated by table 1 and
  table 10). It is ONE pool: ``group_id = CSE-ELECTIVE-POOL``,
  ``minimum_credit = 23``.
- the six banner sections inside table 6 are display partitions only; they must
  never become six ``CurriculumGroup`` rows, and 23 is never split across them.
- table 8 ("（荣誉课程）", 应修 0 学分) is deliberately **not** part of the ordinary
  target requirement import. No zero-credit "fake" group is created for it either.

The fixtures here are synthetic; the real plan documents are never committed.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document

from app.curriculum.docx_reader import load_curriculum_docx
from app.curriculum.plan_profiles import (
    ELECTIVE_POOL_GROUP_ID,
    SOURCE_PLAN_PROFILE,
    TARGET_PLAN_PROFILE,
    plan_group_records,
    plan_profiles,
)


def _target_shaped_doc(path: Path) -> Path:
    """A document shaped like the target plan's declared profile.

    The declared profile selects tables 2, 4 and 6, so the document carries a
    filler table plus gap tables to place them at those physical indices - the
    same layout the real plan has.
    """
    document = Document()

    def blank(rows: int = 1, cols: int = 1) -> None:
        table = document.add_table(rows=0, cols=cols)
        for _ in range(rows):
            table.add_row()

    blank()  # physical table 1 (unselected)
    # physical table 2: 公必 (9 columns, data from row 3)
    t1 = document.add_table(rows=0, cols=9)
    t1.add_row(); t1.add_row()
    for index, (cid, credit) in enumerate([("MAR103", "3"), ("FL101", "2")], start=1):
        cells = t1.add_row().cells
        cells[2].text = str(index); cells[3].text = cid
        cells[4].text = f"课程{cid}"; cells[5].text = credit; cells[8].text = "2025-1"
    blank()  # physical table 3 (unselected)
    # physical table 4: 专业课 (10 columns)
    t2 = document.add_table(rows=0, cols=10)
    t2.add_row(); t2.add_row()
    cells = t2.add_row().cells
    cells[2].text = "1"; cells[3].text = "CSE310"
    cells[4].text = "网络空间安全综合实践"; cells[5].text = "1"; cells[8].text = "2027-2"
    blank()  # physical table 5 (unselected)
    # physical table 6: 专业选修课 (id at 3, credit at 5, term at 8)
    t3 = document.add_table(rows=0, cols=10)
    t3.add_row(); t3.add_row()
    banner = t3.add_row().cells
    for cell in banner:
        cell.text = "示例展示分区"
    for index, (cid, credit) in enumerate(
        [("CSE323", "3"), ("CS5701", "3"), ("CSE317", "3")], start=1
    ):
        cells = t3.add_row().cells
        cells[1].text = str(index); cells[2].text = cid
        cells[3].text = f"课程{cid}"; cells[4].text = credit; cells[7].text = "2027-1"
    document.save(str(path))
    return path


def _target_tables():
    """The declared target tables, with anchors dropped for the synthetic fixture."""
    tables = []
    for spec in TARGET_PLAN_PROFILE:
        copy = dict(spec)
        copy.pop("identity", None)
        tables.append(copy)
    return tables


# --------------------------------------------------------------------------
# End-to-end behaviour of the declared target profile
# --------------------------------------------------------------------------

def test_every_elective_shares_one_group_id(tmp_path: Path) -> None:
    draft = load_curriculum_docx(_target_shaped_doc(tmp_path / "t.docx"),
                                 source_id="mock://target", tables=_target_tables())
    electives = [row for row in draft.rows if row.requirement.value == "elective"]
    assert electives, "the fixture must contain elective rows"
    assert {row.group_id for row in electives} == {ELECTIVE_POOL_GROUP_ID}
    # Required rows never join the pool.
    assert all(row.group_id is None for row in draft.rows if row.requirement.value == "required")


def test_display_banners_do_not_create_extra_groups(tmp_path: Path) -> None:
    """A banner row is skipped, so it cannot become a group of its own."""
    draft = load_curriculum_docx(_target_shaped_doc(tmp_path / "t.docx"),
                                 source_id="mock://target", tables=_target_tables())
    assert not any("示例展示分区" in (row.course_name or "") for row in draft.rows)
    version = draft.to_version(
        version_id="mock-target", major="演示专业", cohort="2025级",
        group_records=plan_group_records("target"), complete=False,
    )
    assert len(version.groups) == 1


def test_group_minimum_credit_is_23(tmp_path: Path) -> None:
    draft = load_curriculum_docx(_target_shaped_doc(tmp_path / "t.docx"),
                                 source_id="mock://target", tables=_target_tables())
    version = draft.to_version(
        version_id="mock-target", major="演示专业", cohort="2025级",
        group_records=plan_group_records("target"), complete=False,
    )
    (group,) = version.groups
    assert group.group_id == ELECTIVE_POOL_GROUP_ID
    assert group.minimum_credit == 23
    assert group.source_record == "table:7!row:2"


def test_pool_membership_is_not_the_sum_of_course_credits(tmp_path: Path) -> None:
    """The requirement is the stated figure, never the pool's course-credit total."""
    draft = load_curriculum_docx(_target_shaped_doc(tmp_path / "t.docx"),
                                 source_id="mock://target", tables=_target_tables())
    version = draft.to_version(
        version_id="mock-target", major="演示专业", cohort="2025级",
        group_records=plan_group_records("target"), complete=False,
    )
    pool_total = sum(c.credit for c in version.courses if c.group_id == ELECTIVE_POOL_GROUP_ID)
    assert pool_total != 23
    assert version.groups[0].minimum_credit == 23


# --------------------------------------------------------------------------
# Declared profile / group-record integrity
# --------------------------------------------------------------------------

def test_table_8_honours_is_absent_from_the_target_profile() -> None:
    """Honours courses must not be imported as ordinary requirements."""
    assert {spec["table_index"] for spec in TARGET_PLAN_PROFILE} == {2, 4, 6}
    assert all(spec["table_index"] != 8 for spec in TARGET_PLAN_PROFILE)
    assert all(spec["course_type"] != "专业选修课模块二" for spec in TARGET_PLAN_PROFILE)


def test_target_profile_declares_the_elective_pool() -> None:
    electives = [s for s in TARGET_PLAN_PROFILE if s["requirement"] == "elective"]
    assert len(electives) == 1
    assert electives[0]["table_index"] == 6
    assert electives[0]["group_id"] == ELECTIVE_POOL_GROUP_ID


def test_exactly_one_target_group_with_the_declared_minimum() -> None:
    records = plan_group_records("target")
    assert len(records) == 1
    assert records[0]["group_id"] == ELECTIVE_POOL_GROUP_ID
    assert records[0]["minimum_credit"] == 23
    assert records[0]["source_record"] == "table:7!row:2"


def test_no_zero_credit_or_per_module_groups_are_declared() -> None:
    """No fake zero-credit group, and no split of 23 across the six banners."""
    records = plan_group_records("target")
    assert all(record["minimum_credit"] != 0 for record in records)
    assert sum(record["minimum_credit"] for record in records) == 23


def test_source_plan_declares_no_group_records() -> None:
    assert plan_group_records("source") == ()


def test_plan_role_is_validated() -> None:
    import pytest

    from app.curriculum.errors import CurriculumNormalizationError

    with pytest.raises(ValueError):
        plan_profiles("both")
    with pytest.raises(ValueError):
        plan_group_records("both")
    # The declared records survive the internal group model unchanged.
    from app.curriculum.requirements import normalize_curriculum_version

    version = normalize_curriculum_version(
        version_id="mock", major="m", cohort="c", source_id="mock://s",
        course_records=[{"course_id": "CSE323", "course_name": "n", "credit": 3,
                         "requirement": "elective", "source_record": "row:1",
                         "group_id": ELECTIVE_POOL_GROUP_ID}],
        group_records=plan_group_records("target"), complete=False,
    )
    assert version.groups[0].minimum_credit == 23
    assert version.courses[0].group_id == ELECTIVE_POOL_GROUP_ID


def test_source_plan_elective_table_is_unchanged() -> None:
    """The source plan's own elective table keeps its previous shape."""
    assert plan_profiles("source") is SOURCE_PLAN_PROFILE
    source_electives = [s for s in SOURCE_PLAN_PROFILE if s["requirement"] == "elective"]
    assert len(source_electives) == 1
    # Only the target plan's confirmed pool carries a group.
    assert all("group_id" not in spec for spec in SOURCE_PLAN_PROFILE)
