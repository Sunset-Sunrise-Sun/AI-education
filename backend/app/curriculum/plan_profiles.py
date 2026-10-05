"""Explicit positional table profiles for header-less Curriculum documents.

The two real Case A plan documents carry no column-label row at all: their
course tables are purely positional (row 1 and row 2 are blank, data starts at
row 3). The frozen header mode cannot read them, so this module declares an
explicit positional profile per course table.

Design rules honoured here:

- positions are declared, never inferred;
- only the *course* tables are selected (statistics / summary tables are left out);
- every guard is structural and deterministic (declared physical width, a
  course-id anchor from the first data row, and declared row-selection rules);
- no absolute local paths, names, student numbers, marks or GPAs appear here.

A school revision that changes the table width, shifts the columns, or removes
the anchor makes the import fail instead of silently mis-reading a column.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = [
    "ELECTIVE_POOL_GROUP_ID",
    "SOURCE_PLAN_PROFILE",
    "TARGET_PLAN_PROFILE",
    "plan_group_records",
    "plan_profiles",
]

# The target plan states exactly one professional-elective requirement:
# table 7 (the "（专业选修课）" summary row) gives 23 学分, and table 1 / table 10
# repeat the same figure independently. The six banner sections inside table 6
# are display partitions only - they carry no credit figure of their own - so the
# whole table is one pool and 23 is never split across them.
ELECTIVE_POOL_GROUP_ID = "CSE-ELECTIVE-POOL"
_ELECTIVE_POOL_MINIMUM_CREDIT = 23
_ELECTIVE_POOL_SOURCE_RECORD = "table:7!row:2"

_TARGET_GROUP_RECORDS: tuple[dict, ...] = ({
    "group_id": ELECTIVE_POOL_GROUP_ID,
    "name": "专业选修课",
    "minimum_credit": _ELECTIVE_POOL_MINIMUM_CREDIT,
    "source_record": _ELECTIVE_POOL_SOURCE_RECORD,
},)


def _course_table(
    table_index: int,
    *,
    columns: Mapping[str, int],
    column_count: int,
    anchors: tuple[str, ...],
    requirement: str,
    course_type: str,
    group_id: str | None = None,
) -> dict:
    """One declared positional course table with its structural guards."""
    profile = {
        "mode": "positional",
        "table_index": table_index,
        "data_start_row": 3,
        "column_count": column_count,
        "columns": dict(columns),
        # These plans print a bilingual course name inside one cell
        # ("中文\nEnglish"); only the leading Chinese name line is the identifier.
        "course_name_lines": 1,
        # The row-kind discriminator: a course row always has a numeric index in
        # the sequence column, while section / module labels do not. This is what
        # separates "definitely not a course row" from "looks like a course row
        # but is structurally broken".
        "row_kind": {"column": columns["sequence"], "condition": "numeric"},
        # Selectors that identify a course row, in this order:
        #   sequence numeric + course_id nonempty + credit numeric.
        # A row carrying the discriminator must satisfy all of them; a row with
        # the discriminator but a missing or failing selector fails closed.
        "row_filter": [
            {"column": columns["sequence"], "condition": "numeric"},
            {"column": columns["course_id"], "condition": "nonempty"},
            {"column": columns["credit"], "condition": "numeric"},
        ],
        "identity": {"column": columns["course_id"], "values": list(anchors)},
        "requirement": requirement,
        "course_type": course_type,
    }
    if group_id is not None:
        profile["group_id"] = group_id
    return profile


# 2025级 遥感科学与技术 (source plan). Course tables are 2, 4, 6 and 8.
SOURCE_PLAN_PROFILE: tuple[dict, ...] = (
    _course_table(
        2, columns={"sequence": 3, "course_id": 4, "course_name": 5, "credit": 6,
                    "recommended_term_text": 9},
        column_count=9, anchors=("FL101",), requirement="required", course_type="公必",
    ),
    _course_table(
        4, columns={"sequence": 3, "course_id": 4, "course_name": 5, "credit": 6,
                    "recommended_term_text": 9},
        column_count=10, anchors=("GST326",), requirement="required", course_type="专业课",
    ),
    _course_table(
        6, columns={"sequence": 2, "course_id": 3, "course_name": 4, "credit": 5,
                    "recommended_term_text": 8},
        column_count=10, anchors=("GST5210",), requirement="elective", course_type="专业选修课模块",
    ),
    _course_table(
        8, columns={"sequence": 2, "course_id": 3, "course_name": 4, "credit": 5,
                    "recommended_term_text": 8},
        column_count=8, anchors=("GST213",), requirement="required", course_type="专业基础与核心课",
    ),
)

# 网络空间安全 (target plan). Course tables 2, 4 and 6 are ordinary 主修 graduation
# requirements. Table 8 ("（荣誉课程）", 应修 0 学分, table 9 total) is NOT an ordinary
# requirement: it is deliberately left out of the target profile so honours courses
# never enter CurriculumVersion.courses. Its two shared codes (CS5701/CS5702) are
# therefore imported once, from the elective pool, not twice.
TARGET_PLAN_PROFILE: tuple[dict, ...] = (
    _course_table(
        2, columns={"sequence": 3, "course_id": 4, "course_name": 5, "credit": 6,
                    "recommended_term_text": 9},
        column_count=9, anchors=("MAR103",), requirement="required", course_type="公必",
    ),
    _course_table(
        4, columns={"sequence": 3, "course_id": 4, "course_name": 5, "credit": 6,
                    "recommended_term_text": 9},
        column_count=10, anchors=("CSE310",), requirement="required", course_type="专业课",
    ),
    _course_table(
        6, columns={"sequence": 2, "course_id": 3, "course_name": 4, "credit": 5,
                    "recommended_term_text": 8},
        column_count=10, anchors=("CSE323",), requirement="elective",
        course_type="专业选修课模块", group_id=ELECTIVE_POOL_GROUP_ID,
    ),
)


def plan_group_records(role: str) -> tuple[dict, ...]:
    """Declared course groups for one plan role ('source' or 'target').

    These are structural facts read off the plan documents, not school policy:
    the target plan states a single 23-credit professional-elective requirement,
    so it yields exactly one group. The source plan states none here.
    """
    if role == "source":
        return ()
    if role == "target":
        return _TARGET_GROUP_RECORDS
    raise ValueError("plan role must be 'source' or 'target'")


def plan_profiles(role: str) -> tuple[dict, ...]:
    """Return the declared profile for one plan role ('source' or 'target')."""
    if role == "source":
        return SOURCE_PLAN_PROFILE
    if role == "target":
        return TARGET_PLAN_PROFILE
    raise ValueError("plan role must be 'source' or 'target'")
