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


def test_self_declared_verified_catalog_is_rejected_without_anchor(tmp_path: Path) -> None:
    """**F-03 修复后的回归**：自述 `verified=true` ≠ 已核验。

    修复前：任意非空 `evidence` 文本就能让版本进入可选列表。
    修复后：**没有带外批准锚点**时，条目一律以 `provenance_not_verified` 拒绝。

    ⛔ 本测试**必须**断言"拒绝"——它曾经是 `test_KNOWN_GAP_...` 式的
    "断言不安全行为是正确的"，本轮已按要求改写为**必须拒绝绕过**的回归测试。
    """

    from app.curriculum.catalog import load_curriculum_catalog

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": True, "evidence": "任意非空文本即可"}
    write_catalog(tmp_path, payload, name="catalog.json")

    inspection = load_curriculum_catalog(tmp_path, approved_versions=frozenset()).inspection

    assert inspection.selectable == (), "⛔ 没有独立批准依据的版本不得进入可选列表"
    assert inspection.entries == ()
    assert "provenance_not_verified" in {item.code for item in inspection.rejections}


def test_declared_verified_catalog_is_rejected_when_anchor_lacks_the_version(
    tmp_path: Path,
) -> None:
    """锚点里批准的是**另一个** version_id ⇒ 本版本仍不可选（身份绑定）。"""

    from app.curriculum.catalog import load_curriculum_catalog

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": True, "evidence": "自述依据"}
    write_catalog(tmp_path, payload, name="catalog.json")

    inspection = load_curriculum_catalog(
        tmp_path, approved_versions=frozenset({"some-other-version"}),
    ).inspection

    assert inspection.selectable == ()
    assert "provenance_not_verified" in {item.code for item in inspection.rejections}


def test_anchor_approved_version_becomes_selectable(tmp_path: Path) -> None:
    """锚点批准了该 version_id ⇒ 才可能可选（证明这道门不是"一律拒绝"）。"""

    from app.curriculum.catalog import load_curriculum_catalog

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": True, "evidence": "自述依据"}
    write_catalog(tmp_path, payload, name="catalog.json")

    ids = {entry["version_id"] for entry in payload["versions"]}
    inspection = load_curriculum_catalog(tmp_path, approved_versions=ids).inspection

    assert len(inspection.selectable) == len(ids)
    assert inspection.rejections == ()


def test_personal_catalog_runtime_requires_an_anchor(tmp_path: Path) -> None:
    """production 目录装载路径（F-03）没有锚点 ⇒ fail closed。"""

    from app.services.personal_runtime import load_personal_catalog

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": True, "evidence": "自述依据"}
    write_catalog(tmp_path, payload, name="catalog.json")

    # 有目录、没有锚点 ⇒ 不放出任何版本
    without_anchor = load_personal_catalog({"APP_PERSONAL_CATALOG_DIR": str(tmp_path)})
    assert without_anchor.catalog is None
    assert without_anchor.reason == "provenance_not_verified"

    # 有锚点但没有 curriculum_catalog 批准记录 ⇒ 同样拒绝
    anchor_path = _write_anchor(tmp_path / "anchor.json", approvals=[])
    still_none = load_personal_catalog({
        "APP_PERSONAL_CATALOG_DIR": str(tmp_path),
        "APP_TRUST_ANCHOR_PATH": str(anchor_path),
    })
    assert still_none.catalog is None
    assert still_none.reason == "catalog_provenance_empty"


# --------------------------------------------------------------------------- #
# 已确认的绕过路径：**修复后必须被拒绝**（不再是"断言缺口存在"）
# --------------------------------------------------------------------------- #


def test_synthetic_case_cannot_be_labelled_real_by_avoiding_mock_marker(
    tmp_path: Path,
) -> None:
    """**F-02 修复后的回归**：只避开字面量 `mock://` 不再够用。

    ⚠️ 说明本测试覆盖的范围：`load_curriculum_case` **本身**仍然只做
    `mock://` 子串扫描（那是 loader 的声明侧守卫，⛔ 本轮未改它的契约）。
    **真正的拒绝发生在运行时装配门**：`build_curriculum_provider` 现在要求
    case 文件的 SHA-256 出现在带外批准锚点里。因此这里断言的是
    **装配门必须拒绝**——那才是数据进入生产链路的入口。
    """

    from app.services import planning_runtime

    case = _minimal_case(
        sources=("verified-source://example/old", "verified-source://example/new",
                 "verified-source://example/done"),
        real=True,
    )
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    # ① 没有锚点 ⇒ 拒绝装配（⛔ 不再"因为没写 mock:// 就放行"）
    with pytest.raises(planning_runtime._RuntimeSourceUnavailable):
        planning_runtime.build_curriculum_provider(str(path))

    # ② 有锚点但摘要不符（内容被改过）⇒ 仍然拒绝。
    #    ⚠️ 锚点身份必须与该 case 自身声明一致（否则会先在 "not Case A" 处失败，
    #    那样就**没有**覆盖到摘要门）。
    from app.provenance import load_trust_anchor

    anchor_path = _write_anchor(tmp_path / "anchor", approvals=[{
        "kind": "curriculum_case",
        "identity": {"target_version_id": "demo-new-2025", "as_of_term": "2025-2"},
        "artifact_sha256": "f" * 64,  # 与真实文件摘要不符
        "approver": "教务数据负责人 张三",
        "authorization": "教务数据交接会议纪要 2026-10-01",
        "approved_at": "2026-10-01T00:00:00Z",
    }])
    anchor = load_trust_anchor({"APP_TRUST_ANCHOR_PATH": str(anchor_path)})
    # 该 case 不是 Case A ⇒ 会在版本号检查处被拒（同样是 fail closed）。
    with pytest.raises(planning_runtime._RuntimeSourceUnavailable):
        planning_runtime.build_curriculum_provider(str(path), anchor=anchor)


def test_caller_declared_real_ai_context_is_downgraded_not_trusted() -> None:
    """**F-05 修复后的回归**：请求体自述 real 被降级为 `real_unverified`。

    ⛔ 本测试**必须**断言降级——它曾经断言"声明即结果"。
    """

    from app.ai_planning.context import (
        CONTEXT_SOURCE_REAL_UNVERIFIED,
        build_context,
    )
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

    # 声明为 real 的教学班 ⇒ **降级**为 real_unverified（F-05 已修）
    declared_real = build_context(
        semester="2026-1", base_plan=plan, makeup_tasks=[],
        offerings=[offering(DataSource.REAL)], preference=Preference(),
    )
    assert declared_real.data_source == CONTEXT_SOURCE_REAL_UNVERIFIED
    assert declared_real.source_verified is False


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


def _write_anchor(path: Path, *, approvals: list[dict]) -> Path:
    """写一份**测试专用**批准锚点（⛔ 不代表任何真实批准）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"trust_anchor_version": 1, "approvals": approvals}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


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
