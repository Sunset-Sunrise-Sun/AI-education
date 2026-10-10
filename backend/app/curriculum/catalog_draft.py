"""把培养方案 DOCX 转成**待人工审核的目录草稿**（⛔ 不生成可直接使用的正式目录）。

```text
DOCX ──load_curriculum_docx──> DocxImportResult（行 + 问题）
                                      │
                                      ├── build_catalog_draft_input(...)  ──> 审核中间格式
                                      │        （来源文件 / 原始条目 / 证据 / 待确认清单）
                                      │
                                      └── draft_to_catalog_payload(...)  ──> 目录草稿 JSON
                                               （verification.verified = false）
```

## 为什么要有这个模块

真实能力接入的**最大缺口**是"没有已核验的培养方案版本目录"，
而仓库里**没有任何把 DOCX 转成 `catalog.json` 的工具**
（`plan_profiles.py` 只被测试使用，`python -m app.curriculum --docx` 只打印计数）。

本模块**只补最小的一环**：把既有解析器的输出**序列化**成
① 供人审核的中间格式，② 一个 `verification.verified=false` 的目录草稿。

## 硬边界（⛔ 不允许突破）

1. **⛔ 不重新实现 DOCX 解析**：一切解析都复用
   `app.curriculum.docx_reader.load_curriculum_docx`；
2. **⛔ 不猜测**：`recommended_semester` / `deadline_semester` / `prerequisites`
   这些解析器明确不推断的字段**一律留在"待人工确认"清单里**，⛔ 不填默认值；
3. **⛔ 不自动把草稿标成已核验**：输出的 `verification` 永远是
   `{"verified": false, "evidence": null}`；`complete` 也永远是 `false`；
4. **⛔ 不修改公共 Schema**：输出形状就是 `catalog.py` 已接受的内部 artifact 形状；
5. **⛔ 不写进运行时目录**：本模块只**返回** payload / 写**指定路径**，
   不会去动 `APP_PERSONAL_CATALOG_DIR`；草稿即使被误放进目录，
   也会因为 `verified=false` 被 `catalog.py` 判为 `not_verified` 而**不可选择**（fail closed）。

## 与 `verification.verified=true` 的距离

草稿到"可用目录"必须由人补齐（见 `docs/final_upgrade/DOCX_CATALOG_DRAFT.md` §4）：

- `verification.verified=true` + 非空 `verification.evidence`（可加 `verified_by`）；
- `complete`（建议 true）+ 非空 `completeness_evidence`；
- 每个 `group_records[].minimum_credit` 的**文档明示数值**（⛔ 不是成员学分之和）；
- `version_id` / `major` / `cohort` / `source_id` 等身份信息；
- 逐条处理"待确认清单"里的行级问题。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.curriculum.docx_reader import (
    DocxCourseRow,
    DocxImportResult,
    load_curriculum_docx,
)
from app.curriculum.requirements import RequirementKind

__all__ = [
    "DRAFT_STATUS_PENDING_REVIEW",
    "CatalogDraftInput",
    "build_catalog_draft_input",
    "draft_to_catalog_payload",
    "render_draft_report",
]

#: 草稿状态：**只能**是"待人工审核"。⛔ 不存在"已核验草稿"这种状态。
DRAFT_STATUS_PENDING_REVIEW = "pending_human_review"

#: 解析器明确**不推断**、因此必须由人确认的字段。
_HUMAN_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("recommended_semester", "解析器不把学期文字转成学期序号；需要人工按培养方案确认。"),
    ("deadline_semester", "解析器不推断修读截止学期；需要人工确认（缺失时应保持未知）。"),
    ("prerequisites", "解析器把先修关系硬编码为 None；需要人工依据培养方案补全或明确留空。"),
)


@dataclass(frozen=True, slots=True)
class CatalogDraftInput:
    """DOCX → 目录草稿的**审核中间格式**。

    ⛔ 保留来源文件、原始条目与证据，便于人工逐条核对；
    ⛔ 不含任何学生个人信息（输入只有培养方案文档）。
    """

    source_id: str
    docx_name: str
    role: str
    course_records: tuple[dict[str, Any], ...]
    group_records: tuple[dict[str, Any], ...]
    unresolved_rows: tuple[dict[str, Any], ...]
    document_issues: tuple[dict[str, Any], ...]
    human_required: tuple[dict[str, str], ...] = field(default=())
    status: str = DRAFT_STATUS_PENDING_REVIEW

    def to_payload(self) -> dict[str, Any]:
        """序列化成 JSON 友好的审核中间格式。"""

        return {
            "status": self.status,
            "source": {"kind": "docx", "name": self.docx_name, "role": self.role},
            "source_id": self.source_id,
            "course_records": [dict(item) for item in self.course_records],
            "group_records": [dict(item) for item in self.group_records],
            "unresolved_rows": [dict(item) for item in self.unresolved_rows],
            "document_issues": [dict(item) for item in self.document_issues],
            "human_required": [dict(item) for item in self.human_required],
        }


def build_catalog_draft_input(
    docx_path: str,
    *,
    source_id: str,
    tables: Sequence[Mapping[str, object]],
    role: str,
    group_records: Sequence[Mapping[str, object]] = (),
) -> CatalogDraftInput:
    """解析 DOCX 并组装**审核中间格式**（⛔ 不写文件、⛔ 不判定核验）。

    `tables` / `group_records` 由调用方**显式声明**（来自 `plan_profiles.py` 或人工写的 profile）：
    ⛔ 本函数不会去猜表索引、列位或锚点。
    """

    result = load_curriculum_docx(docx_path, source_id=source_id, tables=tables)
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for row in result.rows:
        payload = _row_payload(row)
        if _row_is_resolved(row):
            resolved.append(payload)
        else:
            unresolved.append(payload)

    human_required = [
        {
            "field": name,
            "reason": reason,
            "applies_to": "each course_record",
        }
        for name, reason in _HUMAN_REQUIRED_FIELDS
    ]
    if unresolved:
        human_required.append({
            "field": "unresolved_rows",
            "reason": "文档里有未能确定取值的行：必须人工判定后再决定是否进入正式目录。",
            "applies_to": f"{len(unresolved)} row(s)",
        })
    if not group_records:
        human_required.append({
            "field": "group_records",
            "reason": "课程组（选修池等）的学分要求必须来自文档明示数值，⛔ 不能由成员学分求和推出。",
            "applies_to": "missing",
        })
    human_required.append({
        "field": "verification",
        "reason": "⛔ 工具不会自动核验：必须由人给出 verified=true 与非空 evidence 才能进入可选列表。",
        "applies_to": "version entry",
    })
    human_required.append({
        "field": "version_identity",
        "reason": "version_id / major / cohort 必须由人确认（version_id 重复会让该 id 整体不可选）。",
        "applies_to": "version entry",
    })

    return CatalogDraftInput(
        source_id=source_id,
        docx_name=_basename(docx_path),
        role=role,
        course_records=tuple(resolved),
        group_records=tuple(dict(item) for item in group_records),
        unresolved_rows=tuple(unresolved),
        document_issues=tuple(_issue_payload(issue) for issue in result.issues),
        human_required=tuple(human_required),
    )


def draft_to_catalog_payload(
    draft: CatalogDraftInput,
    *,
    version_id: str,
    major: str,
    cohort: str,
    campus: str | None = None,
    track: str | None = None,
    total_credit: float | None = None,
    practice_credit: float | None = None,
    study_years: int | None = None,
) -> dict[str, Any]:
    """把草稿包成**目录草稿**（`verification.verified=false`，⛔ 不可选择）。

    ⚠️ 只输出 `catalog.py` 已接受的键；`verification.verified` 与 `complete`
    被**硬编码为 false**，⛔ 调用方无法通过参数把它们打开。
    """

    entry: dict[str, Any] = {
        "version_id": version_id,
        "major": major,
        "cohort": cohort,
        "source_id": draft.source_id,
        # ⛔ 硬编码：草稿永远不是"已核验"，也永远不是"完整"。
        "verification": {"verified": False, "evidence": None},
        "supported": True,
        "complete": False,
        "course_records": [dict(item) for item in draft.course_records],
        "group_records": [dict(item) for item in draft.group_records],
    }
    for key, value in (
        ("campus", campus), ("track", track), ("total_credit", total_credit),
        ("practice_credit", practice_credit), ("study_years", study_years),
    ):
        if value is not None:
            entry[key] = value
    return {"catalog_version": 1, "versions": [entry]}


def render_draft_report(draft: CatalogDraftInput) -> str:
    """给人看的一页审核说明（⛔ 不含个人信息）。"""

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("培养方案 DOCX → 目录草稿（待人工审核）")
    lines.append("=" * 72)
    lines.append(f"状态            : {draft.status}")
    lines.append(f"来源文件        : {draft.docx_name}")
    lines.append(f"角色            : {draft.role}")
    lines.append(f"source_id       : {draft.source_id}")
    lines.append(f"可提取课程条数  : {len(draft.course_records)}")
    lines.append(f"未确定课程条数  : {len(draft.unresolved_rows)}")
    lines.append(f"课程组条数      : {len(draft.group_records)}")
    lines.append(f"文档级问题      : {len(draft.document_issues)}")

    if draft.document_issues:
        lines.append("")
        lines.append("-" * 72)
        lines.append("文档级问题（⛔ 必须处理后才可能进入正式目录）")
        for issue in draft.document_issues:
            lines.append(
                f"  [{issue.get('code')}] table={issue.get('table_index')} "
                f"row={issue.get('row_index')} field={issue.get('field')}"
            )

    if draft.unresolved_rows:
        lines.append("")
        lines.append("-" * 72)
        lines.append("未能确定取值的行（⛔ 工具不猜测）")
        for row in draft.unresolved_rows:
            codes = ",".join(item.get("code", "") for item in (row.get("issues") or []))
            lines.append(
                f"  {row.get('source_record')} id={row.get('course_id')} "
                f"credit={row.get('credit')} requirement={row.get('requirement')} issues={codes}"
            )

    lines.append("")
    lines.append("-" * 72)
    lines.append("必须由人确认后才能标为已核验的字段")
    for item in draft.human_required:
        lines.append(f"  - {item['field']}（{item['applies_to']}）：{item['reason']}")

    lines.append("")
    lines.append("-" * 72)
    lines.append("提醒：本草稿的 verification.verified=false，")
    lines.append("      放进 APP_PERSONAL_CATALOG_DIR 会被 catalog.py 判为 not_verified，")
    lines.append("      ⛔ 因此不会半可用，也⛔ 不会被当成已核验方案。")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 内部辅助
# --------------------------------------------------------------------------- #

def _row_is_resolved(row: DocxCourseRow) -> bool:
    return (
        not row.issues
        and row.course_id is not None
        and row.course_name is not None
        and row.credit is not None
        and row.requirement != RequirementKind.UNKNOWN
    )


def _row_payload(row: DocxCourseRow) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "course_id": row.course_id,
        "course_name": row.course_name,
        "credit": row.credit,
        "requirement": row.requirement.value,
        "source_record": row.source_record,
    }
    for key, value in (
        ("course_type", row.course_type),
        ("group_id", row.group_id),
        ("recommended_term_text", row.recommended_term_text),
    ):
        if value is not None:
            payload[key] = value
    payload["issues"] = [_issue_payload(issue) for issue in row.issues]
    return payload


def _issue_payload(issue: Any) -> dict[str, Any]:
    return {
        "code": issue.code,
        "table_index": issue.table_index,
        "row_index": issue.row_index,
        "field": issue.field,
        "column_index": issue.column_index,
    }


def _basename(path: str) -> str:
    cleaned = str(path).replace("\\", "/")
    return cleaned.rsplit("/", 1)[-1]
