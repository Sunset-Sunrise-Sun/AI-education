"""Synthetic production E2E: frontend request shape → API → factory → providers → PlanResult.

**Claim level: synthetic production wiring / LEVEL1 capability only.**

⛔ 本文件**不**声明 Real E2E（LEVEL2 / LEVEL3）：全部输入都是 synthetic、零网络，
⛔ 没有真实教务请求、⛔ 没有真实 artifact、⛔ 没有真实登录。

覆盖的是**已装配的真实代码路径**（同一套 factory / Provider / Orchestrator / API）：

```text
frontend RealPlanRequest（只有 semester / current_schedule / preference 三个键）
        ↓ POST /api/v1/plan（真实 dependency：get_planning_orchestrator）
build_planning_runtime(env)  →  CurriculumCaseProvider（真实 case 文件）
                             +  StoreBackedCourseDataProvider（已验收的 full_semester SQLite）
                             +  RestrictedPlannerProvider
        ↓ PlanningOrchestrator.build_plan(...)
PlanResult（公共 Schema 校验通过；前端按同一形状渲染）
```
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from app.api.mock import MOCK_DATA_SOURCE_HEADER, MOCK_DATA_SOURCE_VALUE
from app.course_data import (
    ShardArtifact,
    accept_full_semester_capture_set,
    import_offering_snapshot,
)
from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    CONFIRMED_SCOPE_DECISIONS,
)
from app.main import app
from app.services.planning_runtime import get_planning_orchestrator

SEMESTER = "2026-1"
PLAN_PATH = "/api/v1/plan"
MOCK_PATH = "/api/v1/mock/course-offerings"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

CONCRETE_SCHEDULE = "1-8周/星期五/第5-6节/REDACTED/示例环节,"
LATE_SCHEDULE = "1-8周/星期五/第7-8节/REDACTED/示例环节,"
SHARD_IDS = (
    "east-campus",
    "south-campus",
    "shenzhen-campus",
    "zhuhai-campus",
    "north-campus",
)

#: shard → 该 shard 携带的 (course_id, class_id, 排课串或 None)。
SHARD_ROWS: dict[str, tuple[str, str, str | None]] = {
    "east-campus": ("SYN-EAST-CAMPUS", "east-000", CONCRETE_SCHEDULE),
    "south-campus": ("SYN-UNKNOWN", "south-000", None),
    "shenzhen-campus": ("SYN-DUAL", "shenzhen-000", CONCRETE_SCHEDULE),
    "zhuhai-campus": ("SYN-DUAL", "zhuhai-000", LATE_SCHEDULE),
    "north-campus": ("SYN-NTH", "north-000", CONCRETE_SCHEDULE),
}

TARGET_COURSES: tuple[tuple[str, str], ...] = (
    ("SYN-EAST-CAMPUS", "示例可补修课"),
    ("SYN-UNKNOWN", "示例无排课信息课"),
    ("SYN-MISSING", "示例无候选课"),
    ("SYN-AMBIGUOUS", "示例歧义课"),
)

PREFERENCE_FIELDS = (
    "max_credit",
    "avoid_cross_campus",
    "preferred_courses",
    "avoid_times",
    "notes",
)


# --------------------------------------------------------------------------- #
# synthetic inputs
# --------------------------------------------------------------------------- #


def _row(course_number: str, class_number: str, *, schedule: str | None) -> dict[str, object]:
    row: dict[str, object] = {
        "courseNum": course_number,
        "courseName": f"示例课程 {course_number}",
        "classNumber": class_number,
        "yearTerm": SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
    }
    if schedule is not None:
        row["teachingTimePlaceStr"] = schedule
    # ⛔ 不带 `teachingTimePlaceStr` 键 ⇒ 该教学班 `meetings == []`（schedule UNKNOWN）。
    return row


def _write_bundle(directory: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for shard_id in SHARD_IDS:
        course_id, class_id, schedule = SHARD_ROWS[shard_id]
        path = directory / f"{shard_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            json.dumps(
                {
                    "format": "sysu-opening-courses-capture-v1",
                    "semester": SEMESTER,
                    "first_page_no": 1,
                    "page_size": 200,
                    "pages": [
                        {
                            "page_no": 1,
                            "response": {
                                "code": 200,
                                "data": {
                                    "total": 1,
                                    "rows": [_row(course_id, class_id, schedule=schedule)],
                                },
                            },
                        }
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        paths[shard_id] = path
    return paths


def _accepted_store(tmp_path: Path) -> tuple[Path, str]:
    """五 shard → 正式 full-semester acceptance → SQLite；返回 (路径, manifest SHA)。"""

    paths = _write_bundle(tmp_path / "captures")
    acceptance = accept_full_semester_capture_set(
        expected_semester=SEMESTER,
        baseline_before=len(SHARD_IDS),
        baseline_after=len(SHARD_IDS),
        shard_artifacts=[
            ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
            for shard_id in SHARD_IDS
        ],
    )

    sqlite_path = tmp_path / "course-data.sqlite3"
    import_offering_snapshot(
        sqlite_path,
        acceptance.merged,
        artifact_sha256=acceptance.manifest_sha256,
        scope=acceptance.scope,
    )
    return sqlite_path, acceptance.manifest_sha256


def _case_payload() -> dict[str, object]:
    """synthetic Case A case：4 个待办目标 + 已批准的 4 条范围决策。"""

    new_courses: list[dict[str, object]] = [
        {
            "course_id": course_id,
            "course_name": name,
            "credit": 3,
            "requirement": "required",
            "source_record": f"table:2!row:{index + 1}",
            "recommended_term_text": "2025-1",
            "prerequisites": [],
        }
        for index, (course_id, name) in enumerate(TARGET_COURSES)
    ]
    for record in CONFIRMED_SCOPE_DECISIONS:
        new_courses.append(
            {
                "course_id": record["target_course_id"],
                "course_name": f"示例课程{record['target_course_id']}",
                "credit": 3,
                "requirement": "required",
                "source_record": record["target_source_record"],
                "recommended_term_text": record["recommended_term_text"],
                "prerequisites": [],
            }
        )

    decisions = [
        {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "target_source_record": record["target_source_record"],
            "target_course_id": record["target_course_id"],
            "decision": record["decision"],
            "evidence": record["evidence"],
        }
        for record in CONFIRMED_SCOPE_DECISIONS
    ]

    return {
        "data_source": "real",
        "old": {
            "version_id": "case-a-synthetic-old",
            "major": "示例专业",
            "cohort": "示例年级",
            "source_id": "case-owner-confirmed://synthetic/old",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://synthetic/old/complete",
            "course_records": [],
        },
        "new": {
            "version_id": CASE_TARGET_VERSION_ID,
            "major": "示例专业",
            "cohort": "示例年级",
            "source_id": "case-owner-confirmed://synthetic/new",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://synthetic/new/complete",
            "course_records": new_courses,
            "group_records": [],
        },
        "completed": {
            "source_id": "case-owner-confirmed://synthetic/completed",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://synthetic/completed/complete",
            "records": [
                {
                    "course_id": "SYN-AMB-OLD",
                    "course_name": "示例歧义课",
                    "credit": 3,
                    "semester": "2025-1",
                    "passed": True,
                    "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "case-owner-confirmed://synthetic/id",
                    "source_record": "crow:1",
                }
            ],
        },
        "rules": {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "completed_source_id": "case-owner-confirmed://synthetic/completed",
            "evidence": "case-owner-confirmed://synthetic/rules",
            "allow_exact_match": True,
            "allow_confirmed_absence": True,
        },
        "makeup_scope": {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "as_of_term": AS_OF_TERM,
            "evidence": "case-owner-confirmed://synthetic/as-of",
        },
        "confirmed_scope_decisions": decisions,
    }


def _write_case(tmp_path: Path) -> Path:
    path = tmp_path / "case" / "case-a.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_case_payload(), ensure_ascii=False), encoding="utf-8")
    return path


ENVIRONMENT_NAMES = (
    "APP_REAL_CASE_A_ENABLED",
    "APP_CASE_A_CURRICULUM_CASE_PATH",
    "APP_COURSE_DATA_SQLITE_PATH",
    "APP_COURSE_DATA_SEMESTER",
    "APP_COURSE_DATA_ACCEPTANCE_SHA256",
)


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
) -> None:
    for name in ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)


def _configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, str]:
    sqlite_path, digest = _accepted_store(tmp_path)
    _configure(
        monkeypatch,
        {
            "APP_REAL_CASE_A_ENABLED": "1",
            "APP_CASE_A_CURRICULUM_CASE_PATH": str(_write_case(tmp_path)),
            "APP_COURSE_DATA_SQLITE_PATH": str(sqlite_path),
            "APP_COURSE_DATA_SEMESTER": SEMESTER,
            "APP_COURSE_DATA_ACCEPTANCE_SHA256": digest,
        },
    )
    return sqlite_path, digest


# --------------------------------------------------------------------------- #
# frontend request shape
# --------------------------------------------------------------------------- #


def _meeting() -> dict[str, object]:
    return {
        "weekday": 5,
        "start_section": 5,
        "end_section": 6,
        "weeks": [1, 2, 3, 4, 5, 6, 7, 8],
        "campus": "示例校区",
    }


def _current_offering(
    course_id: str,
    class_id: str,
    *,
    meetings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """前端 `current_schedule` 里的一项（与公共 `CourseOffering` 形状一致）。"""

    return {
        "course_id": course_id,
        "course_name": f"示例课程 {course_id}",
        "class_id": class_id,
        "semester": SEMESTER,
        "teacher": "REDACTED",
        "credit": 3.0,
        "meetings": [_meeting()] if meetings is None else meetings,
        "capacity": 90,
        "remaining_capacity": 75,
        "source": "capture://sysu/2026-1/full-semester/2026-1",
        "data_source": "real",
    }


def _preference() -> dict[str, object]:
    """前端 `Preference`（字段与公共 Schema 一一对应）。"""

    return {
        "max_credit": 18,
        "avoid_cross_campus": True,
        "preferred_courses": ["SYN-EAST-CAMPUS"],
        "avoid_times": [{"weekday": 5, "start_section": 7, "end_section": 8}],
        "notes": "保留原始偏好",
    }


def _frontend_request(
    *,
    current_schedule: list[dict[str, object]] | None = None,
    preference: dict[str, object] | None = None,
) -> dict[str, object]:
    """与 `frontend/src/api/plan.ts:RealPlanRequest` 完全一致的请求体（⛔ 无额外键）。"""

    return {
        "semester": SEMESTER,
        "current_schedule": list(current_schedule or []),
        "preference": _preference() if preference is None else preference,
    }


def _unresolved_types(payload: dict[str, object]) -> list[str]:
    return [item["type"] for item in payload["unresolved"]]  # type: ignore[index]


def _messages(payload: dict[str, object]) -> str:
    return json.dumps(payload["unresolved"], ensure_ascii=False)  # type: ignore[index]


def _selected(payload: dict[str, object]) -> set[tuple[str, str]]:
    return {
        (item["course_id"], item["class_id"])
        for item in payload["selected_classes"]  # type: ignore[index]
    }


def _changed_course_ids(payload: dict[str, object]) -> set[str]:
    return {item["course_id"] for item in payload["changes"]}  # type: ignore[index]


# --------------------------------------------------------------------------- #
# D1 — full path
# --------------------------------------------------------------------------- #


def test_frontend_request_shape_reaches_a_real_plan_result(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    load_schema,
) -> None:
    _configured(monkeypatch, tmp_path)

    response = client.post(PLAN_PATH, json=_frontend_request())

    assert response.status_code == 200
    payload = response.json()

    # 响应必须能过公共 Schema（前端按同一份契约渲染）。
    jsonschema.validate(payload, load_schema("plan_result.schema.json"))
    assert set(payload) <= {
        "status",
        "selected_classes",
        "changes",
        "risks",
        "unresolved",
        "objective_summary",
    }

    # 唯一的唯一 CLEAR 候选班来自 SQLite store ⇒ curriculum 与 course data 确实接上了。
    assert _changed_course_ids(payload) == {"SYN-EAST-CAMPUS"}
    assert ("SYN-EAST-CAMPUS", "east-000") in _selected(payload)

    # 无候选 ⇒ missing_data，⛔ 不推断学校未开课、⛔ 不加入建议课表。
    assert "missing_data" in _unresolved_types(payload)
    assert ("SYN-MISSING", "MISSING-000") not in _selected(payload)

    # 数据事实：每个 required 目标都来自 case，候选来自 store。
    assert "SYN-EAST-CAMPUS" in _messages(payload)
    assert payload["status"] in {"feasible", "partially_feasible", "infeasible"}
    assert payload["status"] == "partially_feasible"


def test_preference_fields_are_passed_through_and_reported(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, tmp_path)

    payload = client.post(PLAN_PATH, json=_frontend_request()).json()

    # 每个已启用的 preference 字段都必须出现在 Planner 的"待确认"说明里
    # （说明 Planner 收到的是调用方真实输入，而不是被悄悄丢弃 / 改写）。
    manual = [item for item in payload["unresolved"] if item["type"] == "manual_confirmation"]
    assert manual
    combined = json.dumps(manual, ensure_ascii=False)
    for field in PREFERENCE_FIELDS:
        assert field in combined


def test_current_schedule_is_preserved_and_never_silently_replaced(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, tmp_path)

    # 当前课表内已有一处已知时间冲突（两门当前班同一时段）；
    # store 里另有一个与剩余当前班不冲突的 SYN-DUAL 替代班 zhuhai-000。
    request = _frontend_request(
        current_schedule=[
            _current_offering("SYN-DUAL", "shenzhen-000"),
            _current_offering("SYN-NTH", "north-000"),
        ]
    )

    payload = client.post(PLAN_PATH, json=request).json()

    # 当前选择作为**事实**保留；替代班只被**报告**，⛔ 不执行替换。
    assert ("SYN-DUAL", "shenzhen-000") in _selected(payload)
    assert ("SYN-DUAL", "zhuhai-000") not in _selected(payload)
    assert "SYN-DUAL" not in _changed_course_ids(payload)
    assert "selection_required" in _unresolved_types(payload)
    assert "zhuhai-000" in _messages(payload)
    assert "不执行替换" in _messages(payload)
    # 当前课表被原样计入"保留"计数（Planner 的 objective_summary 由真实输入推导）。
    assert "保留 2 个当前班" in payload["objective_summary"]


# --------------------------------------------------------------------------- #
# D2 — UNKNOWN meetings are never treated as CLEAR
# --------------------------------------------------------------------------- #


def test_unknown_meetings_stay_unknown_end_to_end(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, tmp_path)

    request = _frontend_request(
        current_schedule=[_current_offering("SYN-UNKNOWN", "south-000", meetings=[])]
    )

    response = client.post(PLAN_PATH, json=request)
    payload = response.json()

    assert response.status_code == 200
    assert "schedule_unknown" in _unresolved_types(payload)
    assert "无法完成完整时间冲突确认" in _messages(payload)
    # 两条来源都必须被分别报告：①当前班本身无排课信息；②该 required 目标的候选
    # 在当前来源快照里无法完成确认。⛔ 不合并成一句、⛔ 不静默降级成 CONFLICT/CLEAR。
    assert "保留当前选择不代表 CLEAR" in _messages(payload)
    assert "的候选或当前课表在当前来源快照中没有可用排课信息" in _messages(payload)
    # ⛔ 绝不把"没有排课信息"说成"无冲突 / 可执行"。
    text = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("无冲突", "无需上课", "异步课程", "可直接执行"):
        assert forbidden not in text
    # 当前选择作为事实保留，但状态不能是 feasible。
    assert ("SYN-UNKNOWN", "south-000") in _selected(payload)
    assert payload["status"] == "partially_feasible"


# --------------------------------------------------------------------------- #
# D3 — manual confirmation is reported, never auto-resolved
# --------------------------------------------------------------------------- #


def test_manual_confirmation_tasks_are_reported_not_auto_added(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, tmp_path)

    payload = client.post(PLAN_PATH, json=_frontend_request()).json()

    assert "manual_confirmation" in _unresolved_types(payload)
    assert "仍需人工确认" in _messages(payload)
    # 歧义任务（possibly_equivalent：同名不同课程号）⛔ 不被自动加入建议课表。
    assert "SYN-AMBIGUOUS" not in _changed_course_ids(payload)
    assert all(
        course_id != "SYN-AMBIGUOUS"
        for course_id, _class_id in _selected(payload)
    )


# --------------------------------------------------------------------------- #
# D4 — 503 contract / no mock fallback / X-Data-Source audit
# --------------------------------------------------------------------------- #


def test_missing_acceptance_returns_the_frontend_503_contract(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 只有 case，没有任何 course data 受控输入 ⇒ acceptance 缺失。
    _configure(
        monkeypatch,
        {
            "APP_REAL_CASE_A_ENABLED": "1",
            "APP_CASE_A_CURRICULUM_CASE_PATH": str(_write_case(tmp_path)),
        },
    )

    response = client.post(PLAN_PATH, json=_frontend_request())

    assert response.status_code == 503
    body = response.json()
    # 与 `frontend/src/api/plan.ts::parsePlanErrorBody` 的已知形状一致。
    assert isinstance(body["detail"], dict)
    assert body["detail"]["error"] == "real_pipeline_not_configured"
    assert isinstance(body["detail"]["message"], str)
    assert MOCK_DATA_SOURCE_HEADER not in response.headers
    assert "selected_classes" not in response.text


def test_unconfigured_runtime_never_falls_back_to_mock(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, {})

    response = client.post(PLAN_PATH, json=_frontend_request())

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
    assert MOCK_DATA_SOURCE_VALUE not in response.text
    # Mock 通道**仍然**独立可用，并继续带来源标记（未被 Real 通道影响）。
    mock_response = client.get(MOCK_PATH)
    assert mock_response.status_code == 200
    assert mock_response.headers[MOCK_DATA_SOURCE_HEADER] == MOCK_DATA_SOURCE_VALUE


def test_x_data_source_audit_real_vs_mock(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """审计（⛔ 不改接口）：`X-Data-Source` 仍**只**由 Mock 通道设置。"""

    _configured(monkeypatch, tmp_path)

    real_response = client.post(PLAN_PATH, json=_frontend_request())
    assert real_response.status_code == 200
    assert MOCK_DATA_SOURCE_HEADER not in real_response.headers

    assert client.get(MOCK_PATH).headers[MOCK_DATA_SOURCE_HEADER] == "mock"
    assert MOCK_DATA_SOURCE_HEADER not in client.get("/health").headers


def test_tampered_store_is_not_served_and_does_not_fall_back(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_path, _digest = _configured(monkeypatch, tmp_path)

    # 启动后库被改写：下一次请求必须 fail closed。
    connection = sqlite3.connect(str(sqlite_path))
    connection.execute(
        "UPDATE course_offering SET artifact_sha256 = ? WHERE class_id = ?",
        ("f" * 64, "east-000"),
    )
    connection.commit()
    connection.close()

    response = client.post(PLAN_PATH, json=_frontend_request())

    # 装配在**请求时**重新做 ⇒ 绑定的行数不再自洽 ⇒ 明确的 503（⛔ 不回退到 Mock、
    # ⛔ 不返回"剩余 4 行"的部分数据）。
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
    assert "selected_classes" not in response.text
    assert MOCK_DATA_SOURCE_VALUE not in response.text

    # 直接读回时也会 fail closed（dependency 返回 None）。
    assert get_planning_orchestrator() is None


# --------------------------------------------------------------------------- #
# D5 — request-shape guards
# --------------------------------------------------------------------------- #


def test_extra_request_keys_are_rejected(client: TestClient) -> None:
    """前端请求体只有三个键；多传任何键都必须 422（⛔ 不被静默接受）。"""

    request = _frontend_request()
    request["student_id"] = "SHOULD-NOT-BE-ACCEPTED"

    response = client.post(PLAN_PATH, json=request)

    assert response.status_code == 422
    assert MOCK_DATA_SOURCE_HEADER not in response.headers


def test_current_schedule_must_be_marked_real(client: TestClient) -> None:
    offering = _current_offering("SYN-DUAL", "shenzhen-000")
    offering["data_source"] = "mock"

    response = client.post(
        PLAN_PATH, json=_frontend_request(current_schedule=[offering])
    )

    assert response.status_code == 422


def test_empty_preference_is_accepted(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """空 Preference `{}` 是合法输入（公共 Schema 允许），Pipeline 不补业务默认值。"""

    _configured(monkeypatch, tmp_path)

    response = client.post(PLAN_PATH, json=_frontend_request(preference={}))

    assert response.status_code == 200
    payload = response.json()
    # 没有 preference 字段被激活 ⇒ 不出现那条 preference 的 manual_confirmation，
    # 但其它待确认项（容量等）照旧如实报告。
    assert "Preference 字段" not in _messages(payload)


def test_runtime_assembly_is_shared_by_the_api_dependency(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API 使用的就是 factory 的产物（同一 dependency，⛔ 没有第二条装配路径）。"""

    sqlite_path, digest = _configured(monkeypatch, tmp_path)

    orchestrator = get_planning_orchestrator()
    assert orchestrator is not None
    assert orchestrator.course_data.semester == SEMESTER
    assert orchestrator.course_data.acceptance_sha256 == digest
    assert len(orchestrator.course_data.get_course_offerings(SEMESTER)) == 5
    assert app.dependency_overrides == {}
