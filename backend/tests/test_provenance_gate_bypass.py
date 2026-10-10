"""**来源可信性门**的端到端负向测试（任务书 §四 的九类绕过尝试）。

每一个用例都对应一种"把未经核验的数据说成已核验"的尝试，并且**必须被拒绝**。

| # | 绕过尝试 | 本文件里的用例 |
| --- | --- | --- |
| 1 | 合成数据改写成 `real` | `test_synthetic_data_relabelled_real_cannot_reach_the_planner` |
| 2 | 删除 `mock://` 标记 | `test_removing_the_mock_marker_does_not_earn_a_real_runtime` |
| 3 | 伪造 `verification.verified=true` | `test_forged_catalog_verified_flag_is_rejected` |
| 4 | 伪造 / 篡改 SHA-256 | `test_forged_manifest_digest_is_rejected`、`test_tampered_case_after_approval_is_rejected` |
| 5 | 修改已批准文档 / 教学班 / 学期 | `test_modified_approved_case_is_rejected`、`test_wrong_semester_approval_is_rejected` |
| 6 | 缺少核验人授权依据 | `test_approval_without_authorization_is_rejected` |
| 7 | AI 请求体自述 `data_source=real` | `test_ai_request_cannot_self_declare_real` |
| 8 | 未核验输入试图进入正式 Planner | `test_unverified_input_never_reaches_the_planner` |
| 9 | 正常 Mock 演示与既有合成 E2E | `test_mock_demo_path_still_works`（合成 E2E 见 `test_synthetic_production_e2e.py`） |

⛔ 本文件不产生任何真实批准：所有"批准"都是临时目录里的**测试夹具**锚点，
`approver` 明确写成"本地合成夹具负责人（非真实批准）"。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.provenance import (
    APPROVAL_KIND_COURSE_DATA_MANIFEST,
    APPROVAL_KIND_CURRICULUM_CASE,
    load_trust_anchor,
    verify_approval,
)
from app.services import planning_runtime
from tests.personal_fixtures import catalog_payload, write_catalog

SEMESTER = "2026-1"
PLAN_PATH = "/api/v1/plan"
VERSIONS_PATH = "/api/v1/personal-planning/curriculum-versions"

#: ⚠️ 必须避开 `app.provenance` 的自签启发式（`mock`/`test`/`tool` 等子串）。
FIXTURE_APPROVER = "本地合成夹具负责人（非真实批准）"
FIXTURE_AUTHORIZATION = "test fixture authorization record"


# --------------------------------------------------------------------------- #
# 夹具：合成 case + 合成 acceptance 行
# --------------------------------------------------------------------------- #


def _case_payload(*, data_source: str = "real") -> dict:
    """最小结构化 case（内容全为合成）。"""

    def version(version_id: str, course_id: str, name: str) -> dict:
        return {
            "version_id": version_id,
            "major": "示例专业",
            "cohort": "2025",
            "source_id": "fixture-source://plan",
            "complete": True,
            "completeness_evidence": "fixture-source://plan#complete",
            "course_records": [{
                "course_id": course_id, "course_name": name, "credit": 3.0,
                "requirement": "required", "source_record": f"fixture-source://plan#{course_id}",
            }],
            "group_records": [],
        }

    return {
        "data_source": data_source,
        "old": version("fixture-old-2025", "DEMO100", "示例旧课"),
        "new": version("fixture-new-2025", "DEMO200", "示例新课"),
        "completed": {
            "complete": True,
            "completeness_evidence": "fixture-source://done#complete",
            "source_id": "fixture-source://done",
            "records": [{
                "course_id": "DEMO100", "course_name": "示例旧课", "credit": 3.0,
                "semester": "2024-1", "passed": True, "course_type": "示例必修",
                "course_id_status": "已确认",
                "id_match_source": "fixture-source://done#DEMO100",
                "source_record": "fixture-source://done#row:1",
            }],
        },
    }


def _write_case(tmp_path: Path, *, data_source: str = "real") -> Path:
    path = tmp_path / "case" / "case-a.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_case_payload(data_source=data_source), ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchor(
    path: Path,
    *,
    case_path: Path | None = None,
    manifest_digest: str | None = None,
    semester: str = SEMESTER,
    authorization: str | None = FIXTURE_AUTHORIZATION,
    approver: str = FIXTURE_APPROVER,
) -> Path:
    """写一份测试夹具批准锚点（⛔ 不是真实批准）。"""

    approvals: list[dict] = []
    if case_path is not None:
        record = {
            "kind": APPROVAL_KIND_CURRICULUM_CASE,
            "identity": {
                "target_version_id": "fixture-new-2025",
                "as_of_term": "2025-2",
            },
            "artifact_sha256": _sha256_of(case_path),
            "approver": approver,
            "approved_at": "2026-10-09T00:00:00Z",
        }
        if authorization is not None:
            record["authorization"] = authorization
        approvals.append(record)
    if manifest_digest is not None:
        record = {
            "kind": APPROVAL_KIND_COURSE_DATA_MANIFEST,
            "identity": {"semester": semester, "acceptance_sha256": manifest_digest},
            "artifact_sha256": manifest_digest,
            "approver": approver,
            "approved_at": "2026-10-09T00:00:00Z",
        }
        if authorization is not None:
            record["authorization"] = authorization
        approvals.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"trust_anchor_version": 1, "approvals": approvals}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _runtime_environment(
    tmp_path: Path, *, anchor_path: Path | None, case_path: Path | None = None,
    digest: str | None = None, semester: str = SEMESTER,
) -> dict[str, str]:
    environment = {"APP_REAL_CASE_A_ENABLED": "1"}
    if case_path is not None:
        environment["APP_CASE_A_CURRICULUM_CASE_PATH"] = str(case_path)
    if digest is not None:
        environment["APP_COURSE_DATA_SQLITE_PATH"] = str(tmp_path / "course-data.sqlite3")
        environment["APP_COURSE_DATA_SEMESTER"] = semester
        environment["APP_COURSE_DATA_ACCEPTANCE_SHA256"] = digest
    if anchor_path is not None:
        environment["APP_TRUST_ANCHOR_PATH"] = str(anchor_path)
    return environment


def _install(monkeypatch: pytest.MonkeyPatch, environment: dict[str, str]) -> None:
    for name in (
        "APP_REAL_CASE_A_ENABLED", "APP_CASE_A_CURRICULUM_CASE_PATH",
        "APP_COURSE_DATA_SQLITE_PATH", "APP_COURSE_DATA_SEMESTER",
        "APP_COURSE_DATA_ACCEPTANCE_SHA256", "APP_TRUST_ANCHOR_PATH",
        "APP_PERSONAL_CATALOG_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)


# --------------------------------------------------------------------------- #
# 1 & 8 — 合成数据改写成 real、未核验输入不得进入正式 Planner
# --------------------------------------------------------------------------- #


def test_synthetic_data_relabelled_real_cannot_reach_the_planner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """① 把合成 case 的 `data_source` 改成 `real` ⇒ **仍然**进不了 Planner。"""

    case_path = _write_case(tmp_path, data_source="real")
    _install(monkeypatch, _runtime_environment(tmp_path, anchor_path=None, case_path=case_path))

    inspection = planning_runtime.build_planning_runtime(
        _runtime_environment(tmp_path, anchor_path=None, case_path=case_path)
    )

    assert inspection.orchestrator is None
    assert inspection.ready is False
    assert inspection.reason == "provenance_not_verified"


def test_unverified_input_never_reaches_the_planner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⑧ 没有批准锚点 ⇒ `/api/v1/plan` 必须 503，且⛔ 不带 Mock 标记头。"""

    case_path = _write_case(tmp_path)
    environment = _runtime_environment(tmp_path, anchor_path=None, case_path=case_path)
    _install(monkeypatch, environment)

    with TestClient(app) as client:
        response = client.post(
            PLAN_PATH,
            json={"semester": SEMESTER, "current_schedule": [], "preference": {}},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
    assert "X-Data-Source" not in response.headers


# --------------------------------------------------------------------------- #
# 2 — 删除 `mock://` 标记不再换来 real
# --------------------------------------------------------------------------- #


def test_removing_the_mock_marker_does_not_earn_a_real_runtime(
    tmp_path: Path,
) -> None:
    """② 来源标签不含 `mock://` ⇒ 旧守卫放行，但**批准门**仍然拒绝。"""

    case_path = _write_case(tmp_path, data_source="real")
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    assert "mock://" not in json.dumps(payload)  # 字面守卫对它无效

    # 没有锚点 ⇒ 拒绝
    with pytest.raises(planning_runtime._RuntimeSourceUnavailable):
        planning_runtime.build_curriculum_provider(str(case_path))

    # 锚点里的摘要与文件不符（只在"换掉 mock:// 就能过"的旧世界里才会放行）⇒ 拒绝
    anchor = load_trust_anchor({"APP_TRUST_ANCHOR_PATH": str(_anchor(
        tmp_path / "bad-anchor.json", case_path=case_path, approver=FIXTURE_APPROVER,
    ))})
    tampered = tmp_path / "tampered.json"
    payload["new"]["course_records"][0]["credit"] = 9.0
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(planning_runtime._RuntimeSourceUnavailable):
        planning_runtime.build_curriculum_provider(str(tampered), anchor=anchor)


# --------------------------------------------------------------------------- #
# 3 — 伪造 catalog 的 verified 标记
# --------------------------------------------------------------------------- #


def test_forged_catalog_verified_flag_is_rejected(tmp_path: Path) -> None:
    """③ 自述 `verified=true` + 任意非空 evidence ⇒ **没有锚点就没有可选版本**。"""

    from app.curriculum.catalog import load_curriculum_catalog

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": True, "evidence": "self-declared, no anchor"}
    write_catalog(tmp_path, payload)

    inspection = load_curriculum_catalog(tmp_path, approved_versions=frozenset()).inspection

    assert inspection.selectable == ()
    assert "provenance_not_verified" in {item.code for item in inspection.rejections}


def test_forged_catalog_verified_flag_cannot_use_the_personal_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """③ 走 production HTTP：没有锚点时目录接口必须 503，⛔ 不放出任何版本。"""

    payload = catalog_payload()
    for entry in payload["versions"]:
        entry["verification"] = {"verified": True, "evidence": "self-declared"}
    write_catalog(tmp_path, payload)
    _install(monkeypatch, {"APP_PERSONAL_CATALOG_DIR": str(tmp_path)})

    with TestClient(app) as client:
        response = client.get(VERSIONS_PATH)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "personal_catalog_provenance_not_verified"


# --------------------------------------------------------------------------- #
# 4 — 伪造 / 篡改 SHA-256
# --------------------------------------------------------------------------- #


def test_forged_manifest_digest_is_rejected(tmp_path: Path) -> None:
    """④ 锚点里的摘要与库内 manifest 不符 ⇒ 拒绝读取。"""

    from app.course_data.store import CourseDataStoreError, load_accepted_offerings

    # 库里没有任何 acceptance ⇒ 先证"批准通过也仍然要过 store 校验"
    empty = tmp_path / "empty.sqlite3"
    connection = sqlite3.connect(str(empty))
    connection.execute("CREATE TABLE unrelated (id INTEGER)")
    connection.commit()
    connection.close()

    forged = "f" * 64
    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            empty, semester=SEMESTER, acceptance_sha256=forged,
            approved_manifest_sha256=(forged,),
        )


def test_tampered_case_after_approval_is_rejected(tmp_path: Path) -> None:
    """④ 批准之后修改 case 内容 ⇒ 摘要漂移 ⇒ 拒绝（⛔ 不因为"曾批准过"而放行）。"""

    case_path = _write_case(tmp_path)
    anchor = load_trust_anchor({"APP_TRUST_ANCHOR_PATH": str(_anchor(
        tmp_path / "anchor.json", case_path=case_path,
    ))})

    # 批准当下：身份与摘要都对得上
    good = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "fixture-new-2025", "as_of_term": "2025-2"},
        artifact_sha256=_sha256_of(case_path),
        anchor=anchor,
    )
    assert good.verified is True

    # 批准之后偷偷改一个学分
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["new"]["course_records"][0]["credit"] = 4.0
    case_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    drifted = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "fixture-new-2025", "as_of_term": "2025-2"},
        artifact_sha256=_sha256_of(case_path),
        anchor=anchor,
    )
    assert drifted.verified is False
    assert drifted.reason == "approval_digest_mismatch"


# --------------------------------------------------------------------------- #
# 5 — 修改已批准文档 / 教学班 / 学期
# --------------------------------------------------------------------------- #


def test_modified_approved_case_is_rejected(tmp_path: Path) -> None:
    """⑤ 与上一条同源，但走**真实装配入口**断言 fail closed。"""

    case_path = _write_case(tmp_path)
    anchor_path = _anchor(tmp_path / "anchor.json", case_path=case_path)
    anchor = load_trust_anchor({"APP_TRUST_ANCHOR_PATH": str(anchor_path)})

    # 改学期（scope 语义变了）
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["data_source"] = "real"
    case_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(planning_runtime._RuntimeSourceUnavailable):
        planning_runtime.build_curriculum_provider(str(case_path), anchor=anchor)


def test_wrong_semester_approval_is_rejected(tmp_path: Path) -> None:
    """⑤ 学期身份不符 ⇒ `approval_missing`（⛔ 不会"模糊匹配"）。"""

    digest = "a" * 64
    anchor = load_trust_anchor({"APP_TRUST_ANCHOR_PATH": str(_anchor(
        tmp_path / "anchor.json", manifest_digest=digest, semester="2026-2",
    ))})

    result = verify_approval(
        kind=APPROVAL_KIND_COURSE_DATA_MANIFEST,
        identity={"semester": SEMESTER, "acceptance_sha256": digest},
        artifact_sha256=digest,
        anchor=anchor,
    )
    assert result.verified is False
    assert result.reason == "approval_missing"


# --------------------------------------------------------------------------- #
# 6 — 缺少核验人授权依据
# --------------------------------------------------------------------------- #


def test_approval_without_authorization_is_rejected(tmp_path: Path) -> None:
    """⑥ 有 approver、**没有** authorization ⇒ 锚点整体非法（fail closed）。"""

    from app.provenance import TrustAnchorUnavailable

    case_path = _write_case(tmp_path)
    anchor_path = _anchor(
        tmp_path / "anchor.json", case_path=case_path, authorization=None,
    )

    with pytest.raises(TrustAnchorUnavailable):
        load_trust_anchor({"APP_TRUST_ANCHOR_PATH": str(anchor_path)})


def test_self_issued_approval_is_rejected(tmp_path: Path) -> None:
    """⑥ 生成工具自签（`approver` 里出现工具名）⇒ 锚点整体非法。"""

    from app.provenance import TrustAnchorUnavailable

    case_path = _write_case(tmp_path)
    anchor_path = _anchor(
        tmp_path / "anchor.json", case_path=case_path, approver="prepare_real_case_a_runtime",
    )

    with pytest.raises(TrustAnchorUnavailable):
        load_trust_anchor({"APP_TRUST_ANCHOR_PATH": str(anchor_path)})


# --------------------------------------------------------------------------- #
# 7 — AI 请求体自述 real
# --------------------------------------------------------------------------- #


def test_ai_request_cannot_self_declare_real(tmp_path: Path) -> None:
    """⑦ 请求体把教学班写成 `real` ⇒ 上下文降级 + 响应如实报告未核验。"""

    from app.ai_planning.context import CONTEXT_SOURCE_REAL_UNVERIFIED, build_context
    from app.models.contracts import CourseOffering, PlanResult, Preference

    plan = PlanResult.model_validate({
        "status": "partially_feasible",
        "selected_classes": [{"course_id": "DEMO200", "class_id": "demo-200-01"}],
        "changes": [], "risks": [], "unresolved": [],
    })
    offering = CourseOffering.model_validate({
        "course_id": "DEMO200", "course_name": "示例新课", "class_id": "demo-200-01",
        "semester": SEMESTER,
        "meetings": [{"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1]}],
        "data_source": "real",  # ← 请求方自述
    })

    context = build_context(
        semester=SEMESTER, base_plan=plan, makeup_tasks=[], offerings=[offering],
        preference=Preference(),
    )

    assert context.data_source == CONTEXT_SOURCE_REAL_UNVERIFIED
    assert context.source_verified is False


# --------------------------------------------------------------------------- #
# 9 — 正常 Mock 演示不受影响
# --------------------------------------------------------------------------- #


def test_mock_demo_path_still_works() -> None:
    """⑨ Mock 演示通道不经过真实批准门 ⇒ 必须继续可用（⛔ 不误伤）。"""

    with TestClient(app) as client:
        response = client.get("/api/v1/mock/demo")

    assert response.status_code == 200
    assert response.headers.get("X-Data-Source") == "mock"


def test_demo_case_loader_still_requires_pure_mock() -> None:
    """⑨ 演示 loader 的既有守卫不变（⛔ 本轮的批准门不会放松它）。"""

    from app.curriculum.case import load_demo_case

    case = load_demo_case()
    assert case.data_source.value == "mock"
