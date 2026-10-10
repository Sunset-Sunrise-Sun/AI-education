"""**多表同页 / 页限定 / 汇总表隔离**的负向回归。

背景：第 2 轮真实文件验收时，在 8 页的《遥感科学与技术 2025级 培养方案》上暴露了两个
**真实缺陷**，本文件把它们固化为回归用例：

| 缺陷 | 后果 | 修复 |
| --- | --- | --- |
| 一页多表时 `source_record` 只用 `page:{n}!row:{i}` | 不同表的第 1 行**撞成同一个定位**，而它是 `CurriculumVersion` 的**唯一性主键** | 改为 `page:{n}!table:{t}!row:{i}` |
| 页限定用 `continue` 放在 `find_tables()` **之前** | 未声明页上的表格**连问题都报不出来**（静默丢失） | `find_tables()` 每页只调一次，且不受页限定影响 |

⚠️ 这里用**单行表头**的确定性夹具（纯标准库写入器），因为本文件的重点是
"哪张表被处理、定位是否唯一"，而不是多行表头匹配
（后者由 `test_curriculum_pdf_two_row_header.py` 覆盖）。
⛔ 真实 PDF 不进仓库。
"""

from __future__ import annotations

import pytest

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_reader import load_curriculum_pdf
from tests.pdf_fixtures import build_table_pdf

SOURCE_ID = "pdf-upload:sha256:multi-table-fixture"

HEADER = ["No.", "Course Code", "Course Name", "Credit", "Category", "Term"]


def _rows(prefix: str, count: int) -> list[list[str]]:
    return [
        [str(i), f"{prefix}{i:03d}", f"Course-{prefix}-{i}", "3", "required", "2025-1"]
        for i in range(1, count + 1)
    ]


def _profile(table_index: int, *, pages: list[int] | None = None) -> dict:
    spec: dict = {
        "mode": "tables",
        "table_index": table_index,
        "columns": {
            "sequence": 1, "course_id": 2, "course_name": 3,
            "credit": 4, "requirement": 5, "recommended_term_text": 6,
        },
        "expected_headers": {
            "sequence": "No.",
            "course_id": "Course Code",
            "course_name": "Course Name",
            "credit": "Credit",
            "requirement": "Category",
            "recommended_term_text": "Term",
        },
        "requirement_values": {"required": "required", "elective": "elective"},
    }
    if pages is not None:
        spec["pages"] = pages
    return spec


def _pdf(count: int = 2, extra_pages: int = 0) -> bytes:
    return build_table_pdf([HEADER, *_rows("D", count)], extra_pages=extra_pages)


# --------------------------------------------------------------------------- #
# 缺陷 1：同一页多表时定位必须唯一
# --------------------------------------------------------------------------- #

def test_source_record_carries_the_table_number() -> None:
    """定位串必须带**表序号**：`page:{n}!table:{t}!row:{i}`。"""

    result = load_curriculum_pdf(_pdf(2), source_id=SOURCE_ID, tables=[_profile(1)])
    assert [row.source_record for row in result.rows] == [
        "page:1!table:1!row:1", "page:1!table:1!row:2",
    ]


def test_table_number_comes_from_the_declaration_not_a_constant() -> None:
    """表序号来自**声明**：同页声明 table_index=2 时报缺表（该页只有 1 张）。"""

    result = load_curriculum_pdf(_pdf(2), source_id=SOURCE_ID, tables=[_profile(2)])
    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_not_found"}


def test_all_source_records_are_unique_across_many_rows() -> None:
    """大表：所有 `source_record` 必须**两两不同**（唯一性主键）。"""

    result = load_curriculum_pdf(_pdf(30), source_id=SOURCE_ID, tables=[_profile(1)])
    records = [row.source_record for row in result.rows]
    assert len(records) == 30
    assert len(set(records)) == 30, "出现了重复的可追溯定位"


# --------------------------------------------------------------------------- #
# 缺陷 2：页限定不得静默丢失未声明页
# --------------------------------------------------------------------------- #

def test_pages_scope_limits_which_pages_are_parsed() -> None:
    profile = _profile(1, pages=[1])
    result = load_curriculum_pdf(_pdf(2, extra_pages=1), source_id=SOURCE_ID, tables=[profile])
    assert [row.source_record for row in result.rows] == [
        "page:1!table:1!row:1", "page:1!table:1!row:2",
    ]


def test_undeclared_pages_are_skipped_without_producing_rows_or_noise() -> None:
    """⚠️ 页限定的语义：不在声明页上的表格**只被跳过该条声明**。

    ⚠️ 这条曾被我写错过一次：我为了"按页跳过"在 `find_tables()` **之前**加了 `continue`，
    结果是未声明页上的表格**连问题都报不出来**（静默丢失）。
    正确语义是：识别照常进行，只是**没有声明去消费它**，因此
    ⛔ 不产出课程行、⛔ 也不该产生噪声 issue（那一页本来就没打算解析）。

    真正的保护在另一边：**声明页上**的表头不匹配仍然必须报错
    （见 `test_pages_scoping_does_not_disable_header_checking_on_declared_pages`）。
    """

    profile = _profile(1, pages=[1])
    result = load_curriculum_pdf(_pdf(1, extra_pages=2), source_id=SOURCE_ID, tables=[profile])

    # 声明页正常解析
    assert [row.source_record for row in result.rows] == ["page:1!table:1!row:1"]
    # 未声明页不产出任何行，也不产生噪声
    assert all("page:2" not in row.source_record for row in result.rows)
    assert all("page:3" not in row.source_record for row in result.rows)


def test_pages_scoping_still_reports_a_missing_table_on_a_declared_page() -> None:
    """声明页上**没有**该表 ⇒ 必须如实报 `table_not_found`（⛔ 不能静默）。"""

    profile = _profile(2, pages=[1])  # 第 1 页只有 1 张表
    result = load_curriculum_pdf(_pdf(1), source_id=SOURCE_ID, tables=[profile])
    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_not_found"}


def test_pages_scoping_does_not_disable_header_checking_on_declared_pages() -> None:
    """声明页上的表头不匹配仍如实报错（页限定⛔ 不是"免检"）。"""

    profile = _profile(1, pages=[1])
    profile["expected_headers"]["credit"] = "Credits"
    result = load_curriculum_pdf(_pdf(1), source_id=SOURCE_ID, tables=[profile])
    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_header_mismatch"}


# --------------------------------------------------------------------------- #
# 汇总表隔离：⛔ 不声明就绝不导入
# --------------------------------------------------------------------------- #

SUMMARY_HEADER = ["Credit Required", "Course Count", "Total Credit", "Theory Hours", "Practice Hours"]


def test_summary_table_is_not_imported_when_not_declared() -> None:
    """学分汇总表（5 列）用课程表的表头去套 ⇒ 表头不匹配 ⇒ ⛔ 不产出课程行。"""

    pdf = build_table_pdf([SUMMARY_HEADER, ["39", "24", "39", "547", "247.0+2w"]])
    result = load_curriculum_pdf(pdf, source_id=SOURCE_ID, tables=[_profile(1)])
    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_header_mismatch"}
    assert result.issues


def test_summary_table_values_never_become_course_records() -> None:
    """即使汇总表的数字看起来像学分，也⛔ 不得变成课程记录。"""

    pdf = build_table_pdf([SUMMARY_HEADER, ["39", "24", "39", "547", "247.0+2w"]])
    result = load_curriculum_pdf(pdf, source_id=SOURCE_ID, tables=[_profile(1)])
    assert all(row.course_id is None for row in result.rows)
    assert all(row.credit is None for row in result.rows)


# --------------------------------------------------------------------------- #
# `pages` 声明的合法性
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", [
    1, "1", [0], [-1], [1, 1], ["1"], [1.5], [True],
])
def test_invalid_pages_declaration_is_rejected(bad: object) -> None:
    profile = _profile(1)
    profile["pages"] = bad
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(_pdf(1), source_id=SOURCE_ID, tables=[profile])


def test_empty_pages_or_missing_pages_means_all_pages() -> None:
    for pages in (None, []):
        profile = _profile(1, pages=pages)
        result = load_curriculum_pdf(_pdf(1), source_id=SOURCE_ID, tables=[profile])
        assert [row.course_id for row in result.rows] == ["D001"], pages


def test_same_table_index_on_disjoint_pages_is_allowed() -> None:
    """真实文件需要：同一 `table_index` 在不同页是**不同的表**。"""

    pdf = _pdf(1, extra_pages=1)
    result = load_curriculum_pdf(
        pdf, source_id=SOURCE_ID, tables=[_profile(1, pages=[1]), _profile(1, pages=[2])],
    )
    assert [row.course_id for row in result.rows] == ["D001"]


def test_same_table_index_on_overlapping_pages_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(
            _pdf(1), source_id=SOURCE_ID,
            tables=[_profile(1, pages=[1, 2]), _profile(1, pages=[2, 3])],
        )


def test_unscoped_and_scoped_declaration_of_the_same_table_index_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(
            _pdf(1), source_id=SOURCE_ID,
            tables=[_profile(1), _profile(1, pages=[1])],
        )
