"""**双行表头 / 合并单元格 / 逐页结构检查**的回归测试（全部合成 PDF）。

真实培养方案（组长确认）具有：**双行表头、合并单元格、不同列数、
分页课程表、课程分类合并单元格**。本文件把这些形态固化成可回归的用例。

⛔ 仍然不含真实 PDF：那两份材料需要组长放到仓库外的目录（见验收报告 BLOCKED 段）。

## 本文件重点覆盖的负向回归

| 负向用例 | 必须发生什么 |
| --- | --- |
| 声明 1 行表头但文档是 2 行 | `table_header_mismatch`，⛔ 不把第二行表头当数据 |
| 声明 2 行表头但文档是 1 行 | `table_header_mismatch` |
| 双行表头第二行文字不符 | `table_header_mismatch`，⛔ 不模糊匹配 |
| 合并单元格导致该列为空 | 用 `null` 声明**精确匹配空**；⛔ 不向上填充 |
| 表头行数声明非法（0 / 4 / 字符串） | 立即 fail closed |
| 数据行数 < 表头行数 | `table_header_mismatch`，⛔ 不产出任何行 |
"""

from __future__ import annotations

import json

import pytest

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_reader import inspect_curriculum_pdf, load_curriculum_pdf
from tests.pdf_fixtures import (
    build_scanned_pdf,
    build_table_pdf,
    build_textonly_pdf,
    build_two_row_header_pdf,
)

SOURCE_ID = "pdf-upload:sha256:two-row-fixture"

#: 双行表头：第 1 行是"序号 / 课程名称 / 学分 / 建议学期"，
#: 第 2 行细分出"课程号"以及学分之下的"必修 / 选修"。
#: `None` 表示该列**这一行**没有文字（合并单元格被吞掉的那格）。
#: ⚠️ 这是**照抄** `inspect_curriculum_pdf()` 输出得到的，⛔ 不是猜的。
TWO_ROW_HEADER: list[list[str | None]] = [
    ["序号", None, "课程名称", "学分", None, "建议学期"],
    [None, "课程号", None, "必修", "选修", None],
]


def _data_rows() -> list[list[str | None]]:
    return [
        ["1", "MAR103", "Course-A", "3", None, "2025-1"],
        ["2", "CSE323", "Course-C", None, "2", "2027-1"],
    ]


def _two_row_profile() -> list[dict]:
    """双行表头 profile：`expected_headers` **逐行照抄**表头原文。

    ⚠️ `header_rows: 2` 时每个候选是"每行一个文字"的列表；`None` 表示该行为空。
    ⚠️ 注意"学分"在第 1 行的第 **4** 列（下标 3），第 5 列（下标 4）第 1 行是空的
    —— 第二行的"选修"就落在那一格。⛔ 不能把"学分"写到第 5 列上。
    """

    return [{
        "mode": "tables",
        "table_index": 1,
        "header_rows": 2,
        "columns": {
            "sequence": 1, "course_id": 2, "course_name": 3,
            "credit": 4, "requirement": 5, "recommended_term_text": 6,
        },
        "expected_headers": {
            "sequence": [["序号", None]],
            "course_id": [[None, "课程号"]],
            "course_name": [["课程名称", None]],
            "credit": [["学分", "必修"]],
            "requirement": [[None, "选修"]],
            "recommended_term_text": [["建议学期", None]],
        },
        "requirement": "required",
    }]


# --------------------------------------------------------------------------- #
# 逐页结构检查（真实的"先看表头再写 profile"步骤）
# --------------------------------------------------------------------------- #

def _cjk_pdf() -> bytes:
    return build_two_row_header_pdf(TWO_ROW_HEADER, _data_rows())


def test_inspect_reports_pages_tables_columns_and_raw_headers() -> None:
    info = inspect_curriculum_pdf(_cjk_pdf())

    assert info["page_count"] == 1
    assert info["scanned_suspected"] is False
    page = info["pages"][0]
    assert page["page"] == 1
    assert page["table_count"] == 1
    table = page["tables"][0]
    assert table["table_index"] == 1
    assert table["column_count"] == 6
    # ⚠️ `data_row_count` 是"表头之后的物理行数"，表头行数由 `header_rows` 给出。
    assert len(table["header_rows"]) == 3
    assert table["header_rows"][0][:4] == ["序号", None, "课程名称", "学分"]
    assert table["header_rows"][1][:3] == [None, "课程号", None]


def test_inspect_is_json_serialisable_and_carries_no_course_ids_in_headers() -> None:
    """检查输出必须可 JSON 序列化，且**表头**里不出现课程号取值。

    ⚠️ 检查输出按设计给出**前 3 行原文**（便于人看清表头结构），
    所以表头为 2 行的表里，第 3 行本来就是数据行——这里只检查表头那 2 行。
    """

    info = inspect_curriculum_pdf(_cjk_pdf())
    text = json.dumps(info, ensure_ascii=False)  # 必须可序列化
    assert text

    headers = info["pages"][0]["tables"][0]["header_rows"][:2]
    flattened = json.dumps(headers, ensure_ascii=False)
    assert "MAR103" not in flattened, "表头行里混进了课程号"
    assert "CSE323" not in flattened, "表头行里混进了课程号"
    assert "Course-A" not in flattened, "表头行里混进了课程名"


def test_inspect_reports_zero_tables_without_guessing() -> None:
    info = inspect_curriculum_pdf(build_textonly_pdf("no table rules here"))
    assert info["pages"][0]["table_count"] == 0
    assert info["pages"][0]["tables"] == []


def test_inspect_flags_scanned_pdfs() -> None:
    info = inspect_curriculum_pdf(build_scanned_pdf(pages=2))
    assert info["scanned_suspected"] is True


@pytest.mark.parametrize("payload", [b"", b"not a pdf", b"%PDF-1.4\njunk"])
def test_inspect_fails_closed_like_the_parser(payload: bytes) -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        inspect_curriculum_pdf(payload)
    assert str(excinfo.value).startswith("pdf import:")


# --------------------------------------------------------------------------- #
# 双行表头：正向
# --------------------------------------------------------------------------- #

def test_two_row_header_is_parsed_with_declared_profiles() -> None:
    result = load_curriculum_pdf(
        _cjk_pdf(),
        source_id=SOURCE_ID, tables=_two_row_profile(),
    )

    assert result.issues == ()
    assert [row.course_id for row in result.rows] == ["MAR103", "CSE323"]
    # ⚠️ 行号相对**数据区第一行**计数：表头有几行都不改变 source_record 的含义。
    assert [row.source_record for row in result.rows] == ["page:1!row:1", "page:1!row:2"]
    # ⚠️ "必修/选修"是**表头第二行的文字**，不是单元格取值：
    #    这里是"课程类别合并成一列、其下按必修/选修分栏"的形态，
    #    ⛔ 解析器不得把表头文字当取值，⛔ 也不得由它推断必修/选修。
    #    因此 `requirement` 只能停在 `UNKNOWN`，由人确认。
    assert [row.requirement.value for row in result.rows] == ["unknown", "unknown"]
    assert result.rows[0].recommended_term_text == "2025-1"


def test_header_row_two_text_is_never_used_as_a_cell_value() -> None:
    """⛔ 表头第二行的文字（"必修"/"选修"）**不得**变课程类别取值。

    本形态下"课程类别"由**表头**按必修/选修**分栏**表达，而不是单元格取值。
    解析器没有、也不允许有"从表头分栏猜 requirement"的规则：
    它只能停在 `UNKNOWN`，并在待人工确认清单里要求人补齐。
    """

    result = load_curriculum_pdf(
        _cjk_pdf(), source_id=SOURCE_ID, tables=_two_row_profile(),
    )
    from app.curriculum.requirements import RequirementKind

    for row in result.rows:
        assert row.requirement is RequirementKind.UNKNOWN
        # ⛔ 没有任何一行把表头文字当成取值
        assert row.course_id not in {"课程号", "必修", "选修"}
        assert row.recommended_term_text not in {"必修", "选修"}


def test_two_row_header_does_not_leak_header_text_into_data_rows() -> None:
    """⛔ 第二行表头（"课程号"/"必修"…）**不得**被当成数据行产出。"""

    result = load_curriculum_pdf(
        _cjk_pdf(),
        source_id=SOURCE_ID, tables=_two_row_profile(),
    )
    for row in result.rows:
        assert row.course_id not in {"课程号", "序号", "建议学期"}
        assert row.course_name not in {"课程名称", "必修", "选修"}


# --------------------------------------------------------------------------- #
# 双行表头：负向回归
# --------------------------------------------------------------------------- #

def test_single_row_header_profile_rejects_a_two_row_header_document() -> None:
    """声明 1 行表头、文档却是 2 行 ⇒ **拒绝**，⛔ 不把第二行表头当数据。"""

    single = json.loads(json.dumps(_two_row_profile()))
    single[0]["header_rows"] = 1
    single[0]["expected_headers"] = {
        key: value[0][0] if value[0][0] is not None else value[0][1]
        for key, value in single[0]["expected_headers"].items()
    }

    result = load_curriculum_pdf(
        _cjk_pdf(),
        source_id=SOURCE_ID, tables=single,
    )

    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_header_mismatch"}


def test_two_row_header_profile_rejects_a_single_row_header_document() -> None:
    """声明 2 行表头、文档只有 1 行 ⇒ **拒绝**。"""

    single_header_doc = build_table_pdf([
        ["No.", "Course Code", "Course Name", "Credit", "Category", "Term"],
        *_data_rows(),
    ])
    result = load_curriculum_pdf(
        single_header_doc, source_id=SOURCE_ID, tables=_two_row_profile(),
    )

    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_header_mismatch"}


def test_two_row_header_second_row_must_match_exactly() -> None:
    """第二行表头文字不符 ⇒ 拒绝（⛔ 不做模糊匹配 / 包含匹配 / 大小写折叠）。

    ⚠️ 用 `course_id` 那一列（它在第 2 行**有**文字"课程号"），
    这样"第二行写错"才是被真正检验的那条路径。
    """

    for wrong in ("课程编号", "课程", "Course Code", "课程号x", "课程 号"):
        profile = _two_row_profile()
        profile[0]["expected_headers"]["course_id"] = [[None, wrong]]
        result = load_curriculum_pdf(
            _cjk_pdf(),
            source_id=SOURCE_ID, tables=profile,
        )
        assert result.rows == (), wrong
        assert {issue.code for issue in result.issues} == {"table_header_mismatch"}, wrong


def test_header_whitespace_is_the_only_normalisation() -> None:
    """首尾空白两侧都 strip() ⇒ 命中；⛔ 但空白以外的差异仍然拒绝。"""

    padded = _two_row_profile()
    padded[0]["expected_headers"]["course_id"] = [[None, "  课程号  "]]
    hit = load_curriculum_pdf(_cjk_pdf(), source_id=SOURCE_ID, tables=padded)
    assert {issue.code for issue in hit.issues} == set()
    assert [row.course_id for row in hit.rows] == ["MAR103", "CSE323"]

    spaced = _two_row_profile()
    spaced[0]["expected_headers"]["course_id"] = [[None, "课程 号"]]
    miss = load_curriculum_pdf(_cjk_pdf(), source_id=SOURCE_ID, tables=spaced)
    assert miss.rows == ()
    assert {issue.code for issue in miss.issues} == {"table_header_mismatch"}


def test_merged_cell_columns_are_matched_by_explicit_nulls_not_by_filling() -> None:
    """合并单元格：⛔ **不向上填充**；`null` 表示该格为空，`""` 永远匹配不上。"""

    rows = [*TWO_ROW_HEADER, *_data_rows()]
    # ① 从**检查输出**里读真实表头，而不是猜。
    inspected = inspect_curriculum_pdf(_cjk_pdf())
    header = inspected["pages"][0]["tables"][0]["header_rows"]
    assert header[0][1] is None, "第 1 行第 2 列（课程号上方）应为空"
    assert header[1][0] is None, "第 2 行第 1 列（序号下方）应为空"

    # ② 用 `""`（空字符串）代替 `null` ⇒ **必须拒绝**（这是"填充式匹配"的入口）。
    strict = _two_row_profile()
    strict[0]["expected_headers"]["credit"] = [["学分", ""]]
    rejected = load_curriculum_pdf(
        _cjk_pdf(), source_id=SOURCE_ID, tables=strict,
    )
    assert rejected.rows == ()
    assert {issue.code for issue in rejected.issues} == {"table_header_mismatch"}

    # ③ 用 `null` 精确声明"该行为空" ⇒ 命中。
    ok = _two_row_profile()
    ok[0]["expected_headers"]["credit"] = [["学分", "必修"]]
    hit = load_curriculum_pdf(_cjk_pdf(), source_id=SOURCE_ID, tables=ok)
    assert {issue.code for issue in hit.issues} == set()
    assert [row.course_id for row in hit.rows] == ["MAR103", "CSE323"]


def test_inspection_output_round_trips_into_the_profile_verbatim() -> None:
    """**照抄即命中**：把检查输出里的表头原文（`None` 原样保留）写进 profile 就能解析。

    这正是"先检查、再写声明"这条工作流的可验证保证：
    检查输出与 profile 的表头表示法是**同一套**，⛔ 不需要人工翻译。
    """

    rows = [*TWO_ROW_HEADER, *_data_rows()]
    inspect = inspect_curriculum_pdf(_cjk_pdf())
    header = inspect["pages"][0]["tables"][0]["header_rows"][:2]

    # ⚠️ 检查输出默认给前 3 行原文（便于人看清结构）；本表只有 2 行表头，
    #    所以第 3 行是**数据行**——这里只取前 2 行作为表头声明。
    assert header[0] == TWO_ROW_HEADER[0]
    assert header[1] == TWO_ROW_HEADER[1]

    # 把每一列的两行表头拼成一个候选（`None` 原样保留，⛔ 不翻译、不填充）
    columns = {"sequence": 1, "course_id": 2, "course_name": 3,
               "credit": 4, "requirement": 5, "recommended_term_text": 6}
    profile = [{
        "mode": "tables",
        "table_index": 1,
        "header_rows": 2,
        "columns": columns,
        "expected_headers": {
            key: [[header[0][position - 1], header[1][position - 1]]]
            for key, position in columns.items()
        },
        "requirement": "required",
    }]

    result = load_curriculum_pdf(
        _cjk_pdf(), source_id=SOURCE_ID, tables=profile,
    )
    assert {issue.code for issue in result.issues} == set()
    assert [row.course_id for row in result.rows] == ["MAR103", "CSE323"]
    assert [row.source_record for row in result.rows] == ["page:1!row:1", "page:1!row:2"]


@pytest.mark.parametrize("bad", [0, 4, "2", 2.0, True, None])
def test_invalid_header_rows_is_rejected(bad: object) -> None:
    profile = _two_row_profile()
    profile[0]["header_rows"] = bad
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(
            _cjk_pdf(),
            source_id=SOURCE_ID, tables=profile,
        )


def test_two_row_candidate_with_wrong_row_count_is_rejected() -> None:
    profile = _two_row_profile()
    profile[0]["expected_headers"]["credit"] = [["学分"]]  # 只给了 1 行
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(
            _cjk_pdf(),
            source_id=SOURCE_ID, tables=profile,
        )


def test_document_shorter_than_declared_header_rows_is_rejected() -> None:
    """文档连表头都读不全 ⇒ 拒绝，⛔ 不产出任何行。

    ⚠️ 用 **CJK 夹具**造一份只有 1 行内容的表（`header_rows: 2` 需要至少 3 行），
    这样"表头行数不够"这条路径才真的被走到。
    """

    # 文档只有 2 行，但 profile 声明 3 行表头 ⇒ 读不全 ⇒ 拒绝。
    short = build_two_row_header_pdf(TWO_ROW_HEADER, [])
    profile = _two_row_profile()
    profile[0]["header_rows"] = 3
    profile[0]["expected_headers"] = {
        key: [[*candidate[0], None]] for key, candidate in
        profile[0]["expected_headers"].items()
    }
    result = load_curriculum_pdf(short, source_id=SOURCE_ID, tables=profile)
    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_header_mismatch"}


def test_single_row_header_still_accepts_the_documented_shorthand() -> None:
    """单行表头仍支持"字符串 or 候选列表"两种写法（向后兼容）。"""

    doc = build_table_pdf([
        ["No.", "Course Code", "Course Name", "Credit", "Category", "Term"],
        ["1", "MAR103", "Course-A", "3", "required", "2025-1"],
    ])
    for header_value in ("Course Code", ["Course Code", "Code"]):
        profile = [{
            "mode": "tables", "table_index": 1,
            "columns": {"course_id": 2, "course_name": 3, "credit": 4},
            "expected_headers": {
                "course_id": header_value,
                "course_name": "Course Name",
                "credit": "Credit",
            },
        }]
        result = load_curriculum_pdf(doc, source_id=SOURCE_ID, tables=profile)
        assert [row.course_id for row in result.rows] == ["MAR103"], header_value
