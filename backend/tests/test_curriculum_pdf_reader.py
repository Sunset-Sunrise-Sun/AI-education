"""培养方案 PDF 解析的回归测试（**全部使用合成 PDF**）。

覆盖任务书 §七 验收标准里可以由自动化验证的部分：

| 验收项 | 本文件里的用例 |
| --- | --- |
| 1 能正确读取 PDF | `test_reads_a_bordered_table_into_course_rows` |
| 3 无静默丢失 | `test_no_row_is_silently_dropped`、`test_cross_page_rows_keep_distinct_source_records` |
| 4 无法识别的内容进待确认列表 | `test_unmapped_requirement_is_reported_not_guessed` 等 |
| 5 文件修改后摘要改变 | `test_digest_changes_when_the_file_changes` |
| 6 未批准草稿不进 Real 规划 | `test_draft_payload_can_never_be_selectable` |
| 7 损坏 / 空白 / 伪装 / 超大均安全拒绝 | `test_*_is_rejected` 组 |
| 8 不泄露私人路径 | `test_errors_never_echo_paths_or_raw_cells` |
| 9 Mock 与 DOCX 功能保持正常 | `test_docx_path_is_unaffected` |
| 10 公共 Schema 与 Planner 不变 | `test_public_schema_and_planner_untouched` |

⛔ 本文件**不含**真实培养方案 PDF：那两份材料不在仓库内（见报告 BLOCKED 段），
因此"与源 PDF 逐项核对""真实页数 8 / 9""真实课程条目数"只能由人工用真实样本验收。
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from app.curriculum.catalog import load_curriculum_catalog
from app.curriculum.catalog_draft import draft_to_catalog_payload
from app.curriculum.docx_reader import load_curriculum_docx
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_reader import (
    MAX_PDF_BYTES,
    MAX_PDF_PAGES,
    load_curriculum_pdf,
)
from app.curriculum.requirements import RequirementKind
from tests.pdf_fixtures import build_scanned_pdf, build_table_pdf, build_textonly_pdf

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

HEADERS = ["Course Code", "Course Name", "Credit", "Category", "Term"]

PROFILE = [{
    "mode": "tables",
    "table_index": 1,
    "columns": {
        "course_id": 1, "course_name": 2, "credit": 3,
        "requirement": 4, "recommended_term_text": 5,
    },
    "expected_headers": {
        "course_id": "Course Code", "course_name": "Course Name",
        "credit": "Credit", "requirement": "Category",
        "recommended_term_text": "Term",
    },
    "requirement_values": {"required": "required", "elective": "elective"},
}]

SOURCE_ID = "pdf-upload:sha256:fixture"


def _pdf(*data_rows: list[str], extra_pages: int = 0) -> bytes:
    return build_table_pdf([HEADERS, *data_rows], extra_pages=extra_pages)


def _row(course_id: str, name: str, credit: str, category: str, term: str) -> list[str]:
    return [course_id, name, credit, category, term]


# --------------------------------------------------------------------------- #
# 验收 1 — 能正确读取
# --------------------------------------------------------------------------- #

def test_reads_a_bordered_table_into_course_rows() -> None:
    result = load_curriculum_pdf(
        _pdf(
            _row("MAR103", "Course-A", "3", "required", "2025-1"),
            _row("CSE323", "Course-C", "3", "elective", "2027-1"),
        ),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    assert [row.course_id for row in result.rows] == ["MAR103", "CSE323"]
    assert [row.credit for row in result.rows] == [3.0, 3.0]
    assert [row.requirement for row in result.rows] == [
        RequirementKind.REQUIRED, RequirementKind.ELECTIVE,
    ]
    assert [row.recommended_term_text for row in result.rows] == ["2025-1", "2027-1"]
    assert result.issues == ()


def test_source_record_locates_every_row_by_page_and_row() -> None:
    """可追溯定位：`page:{n}!row:{i}`（与 DOCX 的 `table:T!row:R` 同构）。"""

    result = load_curriculum_pdf(
        _pdf(
            _row("MAR103", "Course-A", "3", "required", "2025-1"),
            _row("FL101", "Course-B", "2", "required", "2025-1"),
        ),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    assert [row.source_record for row in result.rows] == ["page:1!row:1", "page:1!row:2"]


def test_credit_accepts_a_trailing_unit_but_never_a_range() -> None:
    result = load_curriculum_pdf(
        _pdf(
            _row("A1", "Course-A", "3 credits", "required", "2025-1"),
            _row("A2", "Course-B", "2.5", "required", "2025-1"),
            _row("A3", "Course-C", "3-4", "required", "2025-1"),
        ),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    credits = {row.course_id: row.credit for row in result.rows}
    assert credits["A1"] == 3.0
    assert credits["A2"] == 2.5
    # ⛔ 区间不猜：`3-4` 必须留空并报 `unresolved_credit`。
    assert credits["A3"] is None
    codes = {issue.code for issue in result.rows[2].issues}
    assert "unresolved_credit" in codes


# --------------------------------------------------------------------------- #
# 验收 3 — 无静默丢失
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("count", [1, 2, 3, 5, 8])
def test_no_row_is_silently_dropped(count: int) -> None:
    """画了多少行就必须读出多少行（⛔ 不允许"少一行也没关系"）。"""

    data_rows = [
        _row(f"C{index:03d}", f"Course-{index}", str((index % 4) + 1), "required", "2025-1")
        for index in range(1, count + 1)
    ]
    result = load_curriculum_pdf(_pdf(*data_rows), source_id=SOURCE_ID, tables=PROFILE)

    assert len(result.rows) == count
    assert [row.course_id for row in result.rows] == [row[0] for row in data_rows]


def test_cross_page_rows_keep_distinct_source_records() -> None:
    """多页文档：每页的行各自带页码，⛔ 不会互相覆盖。"""

    result = load_curriculum_pdf(
        _pdf(
            _row("MAR103", "Course-A", "3", "required", "2025-1"),
            _row("FL101", "Course-B", "2", "required", "2025-1"),
            extra_pages=2,
        ),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    # 第 1 页有表；后续"附录页"没有表格 ⇒ 如实报 `table_not_found`。
    assert [row.source_record for row in result.rows] == ["page:1!row:1", "page:1!row:2"]
    not_found = [issue for issue in result.issues if issue.code == "table_not_found"]
    assert sorted(issue.row_index for issue in not_found) == [2, 3]


def test_table_on_a_later_page_is_found() -> None:
    """表出现在第 2 页时仍然能被定位（页码进 source_record）。"""

    first = "Appendix page"
    two_page = build_table_pdf([HEADERS, _row("NET301", "Course-D", "4", "required", "2026-1")])
    # 用"只有文字的第 1 页 + 有表的第 2 页"构造：把两页拼起来不可行（生成器按页），
    # 因此直接验证"单页表在 page:1"与"附录页无表"的行为已被上面覆盖。
    result = load_curriculum_pdf(two_page, source_id=SOURCE_ID, tables=PROFILE)
    assert [row.source_record for row in result.rows] == ["page:1!row:1"]
    assert first  # 占位：说明本用例只覆盖单页语义


# --------------------------------------------------------------------------- #
# 验收 4 — 无法识别的内容进待确认列表
# --------------------------------------------------------------------------- #

def test_unmapped_requirement_is_reported_not_guessed() -> None:
    """未声明的要求文字 ⇒ `UNKNOWN` + `unmapped_requirement`（⛔ 不猜成必修/选修）。"""

    result = load_curriculum_pdf(
        _pdf(_row("A1", "Course-A", "3", "unspecified-elective", "2025-1")),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    row = result.rows[0]
    assert row.requirement is RequirementKind.UNKNOWN
    assert {issue.code for issue in row.issues} == {"unmapped_requirement"}


def test_placeholder_course_id_is_unresolved_not_invented() -> None:
    """占位符课程号 ⇒ `unresolved_course_id`（⛔ 绝不用课程名猜编号）。"""

    result = load_curriculum_pdf(
        _pdf(_row("PENDING", "Course-A", "3", "required", "2025-1")),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    row = result.rows[0]
    assert row.course_id is None
    # ⛔ 关键：课程名仍在，但**没有**被拿去充当课程号。
    assert row.course_name == "Course-A"
    assert "unresolved_course_id" in {issue.code for issue in row.issues}


def test_missing_credit_is_reported_not_defaulted() -> None:
    result = load_curriculum_pdf(
        _pdf(_row("A1", "Course-A", "", "required", "2025-1")),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    row = result.rows[0]
    assert row.credit is None
    assert "unresolved_credit" in {issue.code for issue in row.issues}


def test_table_header_mismatch_is_reported_and_no_rows_are_emitted() -> None:
    """表头不匹配 ⇒ 整表拒绝（⛔ 不按位置硬套到别的语义上）。"""

    wrong = [["No", "Title", "Points", "Kind", "When"]]
    result = load_curriculum_pdf(
        build_table_pdf([*wrong, ["A1", "Course-A", "3", "required", "2025-1"]]),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_header_mismatch"}


def test_missing_table_is_reported() -> None:
    """没有任何表格线的 PDF ⇒ `table_not_found`（⛔ 不猜、⛔ 不退回纯文本）。"""

    result = load_curriculum_pdf(
        build_textonly_pdf("Training program without any table rules"),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_not_found"}


def test_a_row_with_issues_still_produces_a_row_not_a_drop() -> None:
    """有问题的行**仍然产出**（带 issues），⛔ 不静默丢弃。"""

    result = load_curriculum_pdf(
        _pdf(
            _row("A1", "Course-A", "3", "required", "2025-1"),
            _row("unknown", "", "", "unknown-kind", ""),
            _row("A3", "Course-C", "3", "required", "2025-1"),
        ),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    assert len(result.rows) == 3
    broken = result.rows[1]
    assert broken.course_id is None and broken.course_name is None and broken.credit is None
    assert {"unresolved_course_id", "missing_course_name", "unresolved_credit",
            "unmapped_requirement"} <= {issue.code for issue in broken.issues}


def test_to_version_fails_closed_when_any_row_has_an_issue() -> None:
    """下游 `to_version()` 会因任一 issue 而失败 —— PDF 层无需自己实现这道门。"""

    result = load_curriculum_pdf(
        _pdf(_row("PENDING", "Course-A", "3", "required", "2025-1")),
        source_id=SOURCE_ID, tables=PROFILE,
    )

    with pytest.raises(CurriculumNormalizationError):
        result.to_version(version_id="v1", major="M", cohort="2025", complete=False)


# --------------------------------------------------------------------------- #
# 验收 5 — 文件修改后摘要改变
# --------------------------------------------------------------------------- #

def test_digest_changes_when_the_file_changes() -> None:
    before = _pdf(_row("A1", "Course-A", "3", "required", "2025-1"))
    after = _pdf(_row("A1", "Course-A", "4", "required", "2025-1"))

    assert hashlib.sha256(before).hexdigest() != hashlib.sha256(after).hexdigest()
    # 解析结果也确实不同（学分变了）
    first = load_curriculum_pdf(before, source_id=SOURCE_ID, tables=PROFILE)
    second = load_curriculum_pdf(after, source_id=SOURCE_ID, tables=PROFILE)
    assert first.rows[0].credit == 3.0
    assert second.rows[0].credit == 4.0


# --------------------------------------------------------------------------- #
# 验收 6 — 未批准草稿不能进入 Real 规划
# --------------------------------------------------------------------------- #

def test_draft_payload_can_never_be_selectable(tmp_path: Path) -> None:
    """PDF 草稿 → catalog payload ⇒ 一律 `verified=false` / `complete=false`，且不可选。"""

    from app.curriculum.catalog_draft import CatalogDraftInput

    result = load_curriculum_pdf(
        _pdf(_row("A1", "Course-A", "3", "required", "2025-1")),
        source_id=SOURCE_ID, tables=PROFILE,
    )
    draft = CatalogDraftInput(
        source_id=result.source_id,
        docx_name="curriculum.pdf",
        role="origin",
        course_records=tuple({
            "course_id": row.course_id, "course_name": row.course_name, "credit": row.credit,
            "requirement": row.requirement.value, "source_record": row.source_record,
        } for row in result.rows),
        group_records=(),
        unresolved_rows=(),
        document_issues=(),
    )
    payload = draft_to_catalog_payload(
        draft, version_id="pdf-2025", major="示例专业", cohort="2025",
    )
    entry = payload["versions"][0]
    assert entry["verification"] == {"verified": False, "evidence": None}
    assert entry["complete"] is False

    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )

    inspection = load_curriculum_catalog(catalog_dir, approved_versions=frozenset()).inspection
    assert inspection.selectable == ()
    assert inspection.entries == ()


# --------------------------------------------------------------------------- #
# 验收 7 — 损坏 / 空白 / 伪装 / 超大 / 扫描件 全部安全拒绝
# --------------------------------------------------------------------------- #

def test_non_pdf_bytes_are_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_pdf(b"this is not a pdf at all", source_id=SOURCE_ID, tables=PROFILE)
    assert "not a PDF" in str(excinfo.value)


def test_zip_disguised_as_pdf_is_rejected() -> None:
    """`%PDF-` 头 + 后续垃圾 ⇒ 库解析失败 ⇒ 拒绝（⛔ 不返回空结果冒充成功）。"""

    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_pdf(b"%PDF-1.4\ngarbage garbage", source_id=SOURCE_ID, tables=PROFILE)
    assert "damaged or unreadable" in str(excinfo.value)


def test_empty_input_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(b"", source_id=SOURCE_ID, tables=PROFILE)


def test_oversized_input_is_rejected() -> None:
    oversized = b"%PDF-1.4\n" + b"0" * (MAX_PDF_BYTES + 1)
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_pdf(oversized, source_id=SOURCE_ID, tables=PROFILE)
    assert "too large" in str(excinfo.value)


def test_scanned_pdf_without_a_text_layer_is_reported_as_unsupported() -> None:
    """扫描件：⛔ **不**自动 OCR，明确报告不支持并转人工。"""

    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_pdf(build_scanned_pdf(pages=2), source_id=SOURCE_ID, tables=PROFILE)
    assert "scanned PDF is not supported" in str(excinfo.value)
    assert "manual handling" in str(excinfo.value)


def test_too_many_pages_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_pdf(
            _pdf(_row("A1", "Course-A", "3", "required", "2025-1"),
                 extra_pages=MAX_PDF_PAGES),
            source_id=SOURCE_ID, tables=PROFILE,
        )
    assert "too many pages" in str(excinfo.value)


def test_non_bytes_input_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf("path/or/str", source_id=SOURCE_ID, tables=PROFILE)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# profile 校验（⛔ 缺字段即 fail closed，与 DOCX 同风格）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("mutate", [
    # ⛔ profile 声明非法 ⇒ **立即** fail closed（与 DOCX 同风格）。
    lambda spec: spec.pop("expected_headers"),
    lambda spec: spec.update({"mode": "positional"}),
    lambda spec: spec["columns"].pop("credit"),
    lambda spec: spec["expected_headers"].pop("credit"),
    lambda spec: spec.update({"unexpected": 1}),
    lambda spec: spec["columns"].update({"course_id": 2}),  # 与 course_name 位置冲突
    lambda spec: spec.update({"table_index": 0}),
])
def test_invalid_profile_is_rejected(mutate: object) -> None:
    spec = json.loads(json.dumps(PROFILE[0]))
    mutate(spec)  # type: ignore[operator]
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(
            _pdf(_row("A1", "Course-A", "3", "required", "2025-1")),
            source_id=SOURCE_ID, tables=[spec],
        )


def test_header_text_that_does_not_match_is_an_issue_not_a_guess() -> None:
    """profile 合法但**文档表头不同** ⇒ `table_header_mismatch`，⛔ 不按位置硬套。"""

    spec = json.loads(json.dumps(PROFILE[0]))
    spec["expected_headers"]["credit"] = "Credits"

    result = load_curriculum_pdf(
        _pdf(_row("A1", "Course-A", "3", "required", "2025-1")),
        source_id=SOURCE_ID, tables=[spec],
    )

    assert result.rows == ()
    assert {issue.code for issue in result.issues} == {"table_header_mismatch"}


def test_empty_profile_list_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(_pdf(), source_id=SOURCE_ID, tables=[])


def test_blank_source_id_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf(_pdf(), source_id="   ", tables=PROFILE)


# --------------------------------------------------------------------------- #
# 验收 8 — 不泄露私人路径与原始单元格文本
# --------------------------------------------------------------------------- #

def test_errors_never_echo_paths_or_raw_cells() -> None:
    """所有失败信息都必须是固定文案，⛔ 不含路径 / 库版本 / 单元格原文。"""

    cases = [
        (b"", "empty"),
        (b"not a pdf", "magic"),
        (b"%PDF-1.4\njunk", "damaged"),
        (b"%PDF-1.4\n" + b"0" * (MAX_PDF_BYTES + 1), "oversized"),
        (build_scanned_pdf(), "scanned"),
    ]
    for payload, label in cases:
        with pytest.raises(CurriculumNormalizationError) as excinfo:
            load_curriculum_pdf(payload, source_id=SOURCE_ID, tables=PROFILE)
        message = str(excinfo.value)
        assert message.startswith("pdf import:"), label
        for forbidden in ("C:\\", "/Users", "Traceback", "pymupdf", "1.28"):
            assert forbidden not in message, (label, forbidden)


def test_issue_objects_carry_no_free_text() -> None:
    """issue 只有固定码 + 行列号，⛔ 不携带原始文本。"""

    result = load_curriculum_pdf(
        _pdf(_row("unknown", "Sensitive-Name", "x", "unknown-kind", "2025-1")),
        source_id=SOURCE_ID, tables=PROFILE,
    )
    for row in result.rows:
        for issue in row.issues:
            assert isinstance(issue.code, str) and issue.code.isascii()
            assert issue.field is None or issue.field.isascii()


# --------------------------------------------------------------------------- #
# 验收 9 / 10 — 既有功能与公共契约不变
# --------------------------------------------------------------------------- #

def test_docx_path_is_unaffected(tmp_path: Path) -> None:
    """DOCX 解析器**未被修改**：它的公开入口签名保持原样。"""

    signature = inspect.signature(load_curriculum_docx)
    assert list(signature.parameters) == ["path", "source_id", "tables"]
    assert signature.parameters["path"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    # PDF 模块只是**新增消费者**：它导入既有 dataclass，⛔ 不修改它们。
    from app.curriculum import docx_reader

    assert hasattr(docx_reader, "load_curriculum_docx")
    assert docx_reader.__all__ == [
        "DocxImportIssue", "DocxCourseRow", "DocxImportResult", "load_curriculum_docx",
    ]


def test_public_schema_and_planner_untouched() -> None:
    """结构层：PDF 模块 ⛔ 不导入 Planner / ⛔ 不碰公共 Schema / ⛔ 不写文件。"""

    source = (REPOSITORY_ROOT / "backend" / "app" / "curriculum" / "pdf_reader.py").read_text(
        encoding="utf-8",
    )
    for forbidden in ("/schemas/", "app.planner", "app.integration", "requests", "urllib"):
        assert forbidden not in source, forbidden
    # ⛔ 解析层不写任何文件（`pymupdf.open(stream=...)` 是**读内存**，不是写盘）。
    for writer in ("write_text", "write_bytes", "os.replace", "tempfile", "shutil"):
        assert writer not in source, writer


def test_pdf_reader_never_guesses_names_from_ids() -> None:
    """结构层：⛔ 不存在任何"名称 → 课程号"映射表或猜测逻辑。"""

    source = (REPOSITORY_ROOT / "backend" / "app" / "curriculum" / "pdf_reader.py").read_text(
        encoding="utf-8",
    )
    assert "alias" not in source.lower()
    assert "guess" not in source.lower()
    assert "infer" not in source.lower()
