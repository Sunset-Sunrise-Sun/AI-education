"""培养方案 DOCX → 目录草稿工具的行为测试（全部使用**合成** DOCX）。

覆盖任务书对任务 B 的硬要求：

1. 复用既有解析器（⛔ 不重新实现 DOCX 解析）；
2. **⛔ 不猜测**：解析器不推断的字段（`recommended_semester` / `deadline_semester` /
   `prerequisites`）必须留在"待人工确认"清单里；
3. **⛔ 不自动核验**：草稿的 `verification.verified` 永远是 false、`complete` 永远是 false；
4. 草稿**放进运行时目录也不会半可用**：`catalog.py` 必须把它判为 `not_verified`；
5. 未确定的行**不会被静默丢弃**，而是进 `unresolved_rows` 并触发"待人工确认"。

真实培养方案文档**从不进入仓库**；这里的夹具都是合成的。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document

from app.curriculum.catalog import load_curriculum_catalog
from app.curriculum.catalog_draft import (
    DRAFT_STATUS_PENDING_REVIEW,
    build_catalog_draft_input,
    draft_to_catalog_payload,
    render_draft_report,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.plan_profiles import (
    TARGET_PLAN_PROFILE,
    plan_group_records,
)

# --------------------------------------------------------------------------- #
# 合成 DOCX 夹具（形状与 test_curriculum_elective_group.py 一致：两张空表占位后
# 让被选中的表落在物理索引 2 / 4 / 6）
# --------------------------------------------------------------------------- #


def _target_shaped_doc(path: Path, *, bad_credit: bool = False) -> Path:
    document = Document()

    def blank(rows: int = 1, cols: int = 1) -> None:
        table = document.add_table(rows=0, cols=cols)
        for _ in range(rows):
            table.add_row()

    blank()  # 物理表 1（不被选中）
    # 物理表 2：公必（9 列）
    t1 = document.add_table(rows=0, cols=9)
    t1.add_row(); t1.add_row()
    for index, (cid, credit) in enumerate([("MAR103", "3"), ("FL101", "2")], start=1):
        cells = t1.add_row().cells
        cells[2].text = str(index); cells[3].text = cid
        cells[4].text = f"课程{cid}"; cells[5].text = credit; cells[8].text = "2025-1"
    blank()  # 物理表 3
    # 物理表 4：专业课（10 列）
    t2 = document.add_table(rows=0, cols=10)
    t2.add_row(); t2.add_row()
    cells = t2.add_row().cells
    cells[2].text = "1"; cells[3].text = "CSE310"
    cells[4].text = "网络空间安全综合实践"; cells[5].text = "1"; cells[8].text = "2027-2"
    blank()  # 物理表 5
    # 物理表 6：专业选修课（id 在第 3 列、学分第 5 列、学期第 8 列）
    t3 = document.add_table(rows=0, cols=10)
    t3.add_row(); t3.add_row()
    banner = t3.add_row().cells
    for cell in banner:
        cell.text = "示例展示分区"
    for index, (cid, credit) in enumerate(
        [("CSE323", "3"), ("CS5701", "3"), ("CSE317", "3")], start=1
    ):
        row = t3.add_row().cells
        row[1].text = str(index); row[2].text = cid
        row[3].text = f"课程{cid}"; row[4].text = credit; row[7].text = "2027-1"
    if bad_credit:
        # 学分列写成非数字 ⇒ 解析器会产出 unresolved_credit，而不是瞎猜一个数。
        # ⚠️ 行必须**填满**声明的列数（否则解析器会以"行不完整"整体拒绝，
        #    那是结构问题而不是我们想验证的取值问题）。
        bad = t3.add_row().cells
        for column in range(10):
            bad[column].text = ""
        bad[1].text = "4"; bad[2].text = "CSE999"
        bad[3].text = "学分待定课程"; bad[4].text = "待定"; bad[7].text = "2027-1"
    document.save(str(path))
    return path


def _target_tables() -> list[dict]:
    """声明式列映射，但去掉锚点（合成长文档里没有真实锚点）。"""

    tables = []
    for spec in TARGET_PLAN_PROFILE:
        copy = dict(spec)
        copy.pop("identity", None)
        tables.append(copy)
    return tables


def _draft(tmp_path: Path, *, bad_credit: bool = False):
    docx = _target_shaped_doc(tmp_path / "plan.docx", bad_credit=bad_credit)
    return build_catalog_draft_input(
        str(docx),
        source_id="mock://draft/target",
        tables=_target_tables(),
        role="target",
        group_records=plan_group_records("target"),
    )


# --------------------------------------------------------------------------- #
# 1) 复用既有解析器：能从 DOCX 提出课程与课程组
# --------------------------------------------------------------------------- #

def test_draft_extracts_courses_and_groups_from_synthetic_docx(tmp_path: Path) -> None:
    draft = _draft(tmp_path)

    assert draft.status == DRAFT_STATUS_PENDING_REVIEW
    ids = {item["course_id"] for item in draft.course_records}
    assert {"MAR103", "FL101", "CSE310", "CSE323", "CS5701", "CSE317"} <= ids
    # 课程组来自显式声明（⛔ 不是从成员学分求和）
    assert draft.group_records
    assert draft.group_records[0]["group_id"] == "CSE-ELECTIVE-POOL"
    assert draft.group_records[0]["minimum_credit"] == 23
    # 每条课程记录都必须带来源定位，便于人工回溯
    assert all(item["source_record"].startswith("table:") for item in draft.course_records)


def test_elective_rows_carry_the_declared_group_id(tmp_path: Path) -> None:
    draft = _draft(tmp_path)
    electives = [item for item in draft.course_records if item["requirement"] == "elective"]
    assert electives
    assert {item["group_id"] for item in electives} == {"CSE-ELECTIVE-POOL"}
    # 必修行不加入选修池（键在缺失时不出现，所以用 .get）
    assert all(item.get("group_id") is None for item in draft.course_records
               if item["requirement"] == "required")


# --------------------------------------------------------------------------- #
# 2) ⛔ 不猜测：解析器不推断的字段必须进"待人工确认"清单
# --------------------------------------------------------------------------- #

def test_human_required_lists_every_uninferable_field(tmp_path: Path) -> None:
    draft = _draft(tmp_path)
    fields = {item["field"] for item in draft.human_required}

    assert "recommended_semester" in fields
    assert "deadline_semester" in fields
    assert "prerequisites" in fields
    assert "verification" in fields
    assert "version_identity" in fields

    # ⛔ 这些字段不能出现在自动提取出来的课程记录里（工具不许替人决定）
    for item in draft.course_records:
        assert "recommended_semester" not in item
        assert "deadline_semester" not in item
        assert "prerequisites" not in item
        # 学期只保留**原文**，⛔ 不转成序号
        assert item.get("recommended_term_text") in {"2025-1", "2027-1", "2027-2", None}


# --------------------------------------------------------------------------- #
# 3) ⛔ 不自动核验：草稿永远是"未核验 + 不完整"
# --------------------------------------------------------------------------- #

def test_draft_never_claims_verified_or_complete(tmp_path: Path) -> None:
    draft = _draft(tmp_path)
    payload = draft_to_catalog_payload(
        draft, version_id="draft-target-2025", major="网络空间安全", cohort="2025",
    )

    assert payload["catalog_version"] == 1
    (entry,) = payload["versions"]
    assert entry["verification"] == {"verified": False, "evidence": None}
    assert entry["complete"] is False
    assert "completeness_evidence" not in entry
    # 即使调用方想"顺手打开"也做不到：函数签名里根本没有这些开关
    assert entry["supported"] is True


# --------------------------------------------------------------------------- #
# 4) 草稿放进运行时目录也**不可选择**（fail closed，不是"半可用"）
# --------------------------------------------------------------------------- #

def test_draft_placed_in_catalog_dir_is_rejected_not_half_usable(tmp_path: Path) -> None:
    draft = _draft(tmp_path)
    payload = draft_to_catalog_payload(
        draft, version_id="draft-target-2025", major="网络空间安全", cohort="2025",
    )
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )

    inspection = load_curriculum_catalog(catalog_dir).inspection

    # 格式受支持（形状是对的），但**没有任何可选版本**
    assert inspection.format_supported is True
    assert inspection.entries == ()
    assert inspection.selectable == ()
    codes = {item.code for item in inspection.rejections}
    assert "not_verified" in codes
    # ⛔ 不允许出现"部分可用"：可选条目必须是 0
    assert len(inspection.selectable) == 0


# --------------------------------------------------------------------------- #
# 5) 未确定的行**不丢**：进 unresolved_rows 并触发人工确认
# --------------------------------------------------------------------------- #

def _ragged_doc(path: Path, rows: list[list[str]]) -> Path:
    """写一张"行宽不齐"的表（python-docx 会把行补齐，所以要主动删多余单元格）。"""

    document = Document()
    table = document.add_table(rows=0, cols=max(len(r) for r in rows))
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = value
        if len(row) < len(cells):
            for cell in cells[len(row):]:
                cell._element.getparent().remove(cell._element)
    document.save(str(path))
    return path


def _no_credit_filter_profile() -> list[dict]:
    """一个**不把学分纳入过滤**的位置式映射。

    为什么需要它：`plan_profiles` 的声明式映射把"学分必须是数字"写进了 `row_filter`，
    不满足的行会让**整份文档**失败关闭（结构不匹配），因此那种映射下
    永远不会出现"取不到值但被保留"的行。

    只有在**过滤条件不含学分**的映射下，解析器才会把"学分不是数字"
    表达成 `unresolved_credit` 的**行级问题**。本测试要验证的正是后者：
    工具必须把这种行**保留**下来交给人，⛔ 不能丢掉、也⛔ 不能猜一个学分。

    ⚠️ `row_kind` 的判别列必须同时出现在 `row_filter` 里（解析器的既有约束），
    所以这里保留序号列的 numeric 条件、去掉学分列的条件。
    """

    return [{
        "mode": "positional",
        "table_index": 1,
        "data_start_row": 3,
        "column_count": 5,
        "columns": {
            "sequence": 1, "course_id": 2, "course_name": 3, "credit": 4,
            "recommended_term_text": 5,
        },
        "row_kind": {"column": 1, "condition": "numeric"},
        "row_filter": [
            {"column": 1, "condition": "numeric"},
            {"column": 2, "condition": "nonempty"},
        ],
        "identity": {"column": 2, "values": ["DEMO101"]},
        "requirement": "required",
        "course_type": "示例分区",
    }]


def test_unresolved_rows_are_kept_for_review(tmp_path: Path) -> None:
    docx = _ragged_doc(tmp_path / "ragged.docx", [
        [""],
        [""],
        ["1", "DEMO101", "示例课程一", "3", "2025-1"],
        ["2", "DEMO102", "学分待定课程", "待定", "2026-1"],
    ])
    draft = build_catalog_draft_input(
        str(docx), source_id="mock://draft/ragged",
        tables=_no_credit_filter_profile(), role="custom",
    )

    assert draft.unresolved_rows, "学分非数字的行必须进 unresolved_rows，而不是被丢掉"
    unresolved = draft.unresolved_rows[0]
    codes = {item["code"] for item in unresolved["issues"]}
    assert "unresolved_credit" in codes
    assert unresolved["credit"] is None
    assert unresolved["course_id"] == "DEMO102"

    # 未确定的行不能混进可提取记录
    assert all(item["course_id"] != "DEMO102" for item in draft.course_records)
    # 并且必须明确要求人工处理
    assert any(item["field"] == "unresolved_rows" for item in draft.human_required)
    # 已确定的另一行仍然正常提取
    assert any(item["course_id"] == "DEMO101" for item in draft.course_records)


def test_declared_profile_rejects_bad_value_instead_of_guessing(tmp_path: Path) -> None:
    """声明式映射（带 row_filter）下，坏取值会让**整份文档**失败关闭。

    这是解析器既有的安全行为：⛔ 不跳过、⛔ 不猜值。
    本工具**不吞掉**这个错误，而是让调用方看到它。
    """

    docx = _target_shaped_doc(tmp_path / "bad.docx", bad_credit=True)
    with pytest.raises(CurriculumNormalizationError):
        build_catalog_draft_input(
            str(docx), source_id="mock://draft/bad",
            tables=_target_tables(), role="target",
            group_records=plan_group_records("target"),
        )


# --------------------------------------------------------------------------- #
# 6) 审核说明可读且不含文档内容回显
# --------------------------------------------------------------------------- #

def test_report_renders_and_hides_raw_cell_text(tmp_path: Path) -> None:
    draft = _draft(tmp_path)
    report = render_draft_report(draft)

    assert "待人工审核" in report
    assert "必须由人确认" in report
    assert "verification.verified=false" in report
    # 审核说明里不应出现原始表格的展示文案（只出现结构化字段）
    assert "示例展示分区" not in report


def test_audit_payload_round_trips_as_json(tmp_path: Path) -> None:
    draft = _draft(tmp_path)
    serialized = json.dumps(draft.to_payload(), ensure_ascii=False)
    restored = json.loads(serialized)

    assert restored["status"] == DRAFT_STATUS_PENDING_REVIEW
    assert restored["source"]["kind"] == "docx"
    assert restored["source"]["name"] == "plan.docx"
    assert len(restored["course_records"]) == len(draft.course_records)
