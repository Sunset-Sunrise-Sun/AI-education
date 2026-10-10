"""真实数据隔离边界的**可执行**测试（含已确认的绕过路径）。

本文件把一次只读安全审计的结论**变成可执行的断言**，目的有两个：

1. **锁定已经正确的 fail-closed 行为**（防止以后被无意改坏）；
2. **把已确认的绕过路径写成显式断言**（`test_KNOWN_GAP_*`），
   让"合成数据能自称 real"这件事**不能被悄悄忽略**，也**不能冒充成已修复**。

⚠️ 本文件**不改任何生产行为**：断言全部针对现状。
真正修掉那些缺口需要改运行时不变式与 provenance 模型，属**需人工批准的架构改动**
（理由与最小方案见 `docs/final_upgrade/REAL_DATA_ISOLATION_AUDIT.md`）。

术语：
- **合成数据**：人工构造、非学校正式数据（本仓库的 fixtures 全是这一类）；
- **`data_source=real`**：公共契约上的来源标记，**不是**技术证明；
- **fail closed**：信息不足时拒绝服务，而不是回退到演示数据。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.curriculum.case import load_curriculum_case
from app.curriculum.errors import CurriculumNormalizationError
from app.models.contracts import DataSource
from tests.personal_fixtures import catalog_payload, write_catalog

# --------------------------------------------------------------------------- #
# 已经正确的行为：必须继续 fail closed（回归护栏）
# --------------------------------------------------------------------------- #


def test_contract_default_is_mock_not_real(tmp_path: Path) -> None:
    """缺字段永远变不成 real（契约默认值是 mock）。"""

    from app.models.contracts import CourseOffering

    offering = CourseOffering.model_validate({
        "course_id": "DS101", "course_name": "示例课程", "class_id": "ds-01",
        "semester": "2026-1", "meetings": [
            {"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1]},
        ],
    })
    assert offering.data_source is DataSource.MOCK


def test_case_rejects_real_label_on_mock_sources(tmp_path: Path) -> None:
    """显式 `mock://` 来源**不允许**被标成 real（`case.py` 的既有守卫）。"""

    case = _minimal_case(sources=("mock://plan/old", "mock://plan/new", "mock://done/row"), real=True)
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_case(path)
    assert "mock" in str(excinfo.value).lower()


def test_catalog_without_verification_evidence_is_rejected(tmp_path: Path) -> None:
    """catalog 的 `verified=false`（或空 evidence）⇒ 不可选（不是"半可用"）。"""

    from app.curriculum.catalog import load_curriculum_catalog

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": False, "evidence": None}
    write_catalog(tmp_path, payload, name="catalog.json")

    inspection = load_curriculum_catalog(tmp_path).inspection
    assert inspection.format_supported is True
    assert inspection.selectable == ()
    assert "not_verified" in {item.code for item in inspection.rejections}


def test_catalog_verification_is_a_self_declared_boolean(tmp_path: Path) -> None:
    """**已确认**：`verification.verified` 只做类型检查，不由证据推导。

    ⛔ 这不是本测试要修的东西，而是要把"它是自述布尔"写成可执行事实：
    任意非空文本都能通过，因此**不能**把 `verified=true` 当作技术证明。
    """

    from app.curriculum.catalog import load_curriculum_catalog

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": True, "evidence": " " * 0 or "任意非空文本即可"}
    write_catalog(tmp_path, payload, name="catalog.json")

    inspection = load_curriculum_catalog(tmp_path).inspection
    assert len(inspection.selectable) == 2, (
        "现状：任意非空 evidence 即可让版本进入可选列表 —— "
        "这正是已知缺口 F-03，修复需要带摘要的核验记录模型（需人工批准）"
    )


# --------------------------------------------------------------------------- #
# 已确认的绕过路径：显式写成断言，⛔ 不掩盖
# --------------------------------------------------------------------------- #


def test_KNOWN_GAP_real_label_survives_without_mock_marker(tmp_path: Path) -> None:
    """**已知缺口 F-02**：只避开字面量 `mock://`，合成数据就能被标成 real。

    守卫只做子串扫描；文档使用的来源标签（如 `verified-source://…`）
    不含 `mock://`，因此整份**合成** case 会被接受为 `data_source=real`。
    ⛔ 本测试断言**当前行为**，用于证明缺口真实存在，**不代表它是可接受的**。
    """

    case = _minimal_case(
        sources=("verified-source://example/old", "verified-source://example/new",
                 "verified-source://example/done"),
        real=True,
    )
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    loaded = load_curriculum_case(path)

    assert loaded.data_source is DataSource.REAL, (
        "现状：不含 `mock://` 的合成来源被接受为 real（缺口 F-02）。"
        "修复方向：用「来源等价性 / 摘要绑定」替代子串启发式（需人工批准）。"
    )
    # ⛔ 但它仍然是**合成**数据：内容里没有任何学校核验痕迹
    assert "verified-source://" in loaded.new.source_id


def test_KNOWN_GAP_ai_context_source_is_caller_declared() -> None:
    """**已知缺口 F-05**：AI 上下文的 `data_source` 由请求体推导并回显。

    `unknown`（无教学班）是正确行为；但客户端只要在请求里放教学班，
    上下文就会按教学班自身的 `data_source` 报 real/ mock —— 这是**声明**而不是证明。
    """

    from app.ai_planning.context import build_context
    from app.models.contracts import CourseOffering, PlanResult, Preference

    def offering(source: DataSource) -> CourseOffering:
        return CourseOffering.model_validate({
            "course_id": "DS101", "course_name": "示例课程", "class_id": "ds-01",
            "semester": "2026-1",
            "meetings": [{"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1]}],
            "data_source": source.value,
        })

    plan = PlanResult.model_validate({
        "status": "partially_feasible", "selected_classes": [
            {"course_id": "DS101", "class_id": "ds-01"},
        ],
        "changes": [], "risks": [], "unresolved": [],
    })

    # 无教学班 ⇒ unknown（正确，⛔ 不默认成 real）
    empty = build_context(
        semester="2026-1", base_plan=plan, makeup_tasks=[], offerings=[],
        preference=Preference(),
    )
    assert empty.data_source == "unknown"

    # 只有 mock 教学班 ⇒ mock
    mock_only = build_context(
        semester="2026-1", base_plan=plan, makeup_tasks=[],
        offerings=[offering(DataSource.MOCK)], preference=Preference(),
    )
    assert mock_only.data_source == "mock"

    # 声明为 real 的教学班 ⇒ 上下文报 real（**声明即结果**，这就是缺口 F-05）
    declared_real = build_context(
        semester="2026-1", base_plan=plan, makeup_tasks=[],
        offerings=[offering(DataSource.REAL)], preference=Preference(),
    )
    assert declared_real.data_source == "real"


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


def _minimal_case(*, sources: tuple[str, str, str], real: bool) -> dict:
    """一份最小的结构化 case（内容为合成，两个版本 + 一条已修记录）。"""

    def version(version_id: str, source_id: str, course_id: str, name: str) -> dict:
        return {
            "version_id": version_id,
            "major": "示例专业",
            "cohort": "2025",
            "source_id": source_id,
            "complete": True,
            "completeness_evidence": f"{source_id}#complete",
            "course_records": [{
                "course_id": course_id, "course_name": name, "credit": 3.0,
                "requirement": "required", "source_record": f"{source_id}#{course_id}",
            }],
            "group_records": [],
        }

    old_source, new_source, done_source = sources
    return {
        "data_source": "real" if real else "mock",
        "old": version("demo-old-2025", old_source, "DEMO100", "示例旧课"),
        "new": version("demo-new-2025", new_source, "DEMO200", "示例新课"),
        "completed": {
            "complete": True,
            "completeness_evidence": f"{done_source}#complete",
            "source_id": done_source,
            "records": [{
                "course_id": "DEMO100", "course_name": "示例旧课", "credit": 3.0,
                "semester": "2024-1", "passed": True, "course_type": "示例必修",
                "course_id_status": "已确认",
                "id_match_source": f"{done_source}#DEMO100",
                "source_record": f"{done_source}#row:1",
            }],
        },
    }
