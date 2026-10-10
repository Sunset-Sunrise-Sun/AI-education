"""Personal Planning API 与 Planner 接入测试（**全部使用显式 Mock 输入**）。

> ⚠️ 培养方案、课程与学生记录均为人工构造的 Mock，不是学校正式条款，
> 也不是任何真实学生的材料。真实数据验证尚未完成。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.models.contracts import CourseOffering, Meeting, Preference
from app.personal import build_personal_plan
from app.planner import RestrictedPlannerProvider
from tests.personal_fixtures import (
    OLD_VERSION_ID,
    TARGET_VERSION_ID,
    load_catalog,
    student_one_input,
    student_two_input,
    write_catalog,
)

VERSIONS_PATH = "/api/v1/personal-planning/curriculum-versions"
PLAN_PATH = "/api/v1/personal-planning/plan"


def _write_approval_anchor(tmp_path, *, version_ids, name: str = "trust-anchor.json"):
    """写一份**测试专用**批准锚点（⛔ 不是任何真实人工批准）。

    ⚠️ 本轮（F-03）起 `verification.verified=true` 只是自述，
    production 目录装载还会要求 `APP_TRUST_ANCHOR_PATH` 里有对应的
    `curriculum_catalog` 批准记录。这里为合成夹具补上那一步，
    以便继续验证"批准之后"的目录 / 规划行为。
    """

    import json as _json
    from pathlib import Path

    path = Path(tmp_path) / name
    path.write_text(
        _json.dumps({
            "trust_anchor_version": 1,
            "approvals": [
                {
                    "kind": "curriculum_catalog",
                    "identity": {"version_id": version_id},
                    "artifact_sha256": "a" * 64,
                    "approver": "本地合成夹具负责人（非真实批准）",
                    "authorization": "test fixture",
                    "approved_at": "2026-10-09T00:00:00Z",
                }
                for version_id in version_ids
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def catalog_dir(tmp_path, monkeypatch):
    """把已核验目录配置为测试目录（⛔ 不读任何默认目录）。"""

    write_catalog(tmp_path)
    monkeypatch.setenv("APP_PERSONAL_CATALOG_DIR", str(tmp_path))
    monkeypatch.setenv(
        "APP_TRUST_ANCHOR_PATH",
        str(_write_approval_anchor(tmp_path, version_ids=(OLD_VERSION_ID, TARGET_VERSION_ID))),
    )
    return tmp_path


def _body(**overrides) -> dict:
    body = {
        "old_version_id": OLD_VERSION_ID,
        "target_version_id": TARGET_VERSION_ID,
        "student": student_two_input(),
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# 目录接口
# --------------------------------------------------------------------------- #

def test_versions_endpoint_lists_only_selectable_versions(client: TestClient, catalog_dir):
    response = client.get(VERSIONS_PATH)
    assert response.status_code == 200
    payload = response.json()
    assert payload["catalog_ready"] is True
    assert payload["selectable_count"] == 2
    ids = {item["version_id"] for item in payload["versions"]}
    assert ids == {OLD_VERSION_ID, TARGET_VERSION_ID}
    for item in payload["versions"]:
        assert item["verification_evidence"].startswith("mock://")
        assert item["source_id"].startswith("mock://")


def test_versions_endpoint_reports_rejected_entries(client: TestClient, tmp_path, monkeypatch):
    from tests.personal_fixtures import catalog_payload

    payload = catalog_payload()
    payload["versions"][0]["verification"]["verified"] = False
    write_catalog(tmp_path, payload)
    monkeypatch.setenv("APP_PERSONAL_CATALOG_DIR", str(tmp_path))
    # ⚠️ 锚点**同时**批准两个版本：这样被拒的那一个才是因为 `verified=false`
    #    （`not_verified`），而不是因为缺少批准（`provenance_not_verified`）。
    monkeypatch.setenv(
        "APP_TRUST_ANCHOR_PATH",
        str(_write_approval_anchor(tmp_path, version_ids=(OLD_VERSION_ID, TARGET_VERSION_ID))),
    )

    response = client.get(VERSIONS_PATH)
    assert response.status_code == 200
    body = response.json()
    ids = {item["version_id"] for item in body["versions"]}
    assert OLD_VERSION_ID not in ids
    rejected = {item["version_id"]: item["code"] for item in body["rejected"]}
    assert rejected[OLD_VERSION_ID] == "not_verified"


def test_versions_endpoint_is_503_without_a_configured_catalog(
    client: TestClient, monkeypatch
):
    monkeypatch.delenv("APP_PERSONAL_CATALOG_DIR", raising=False)
    response = client.get(VERSIONS_PATH)
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "personal_catalog_not_configured"


# --------------------------------------------------------------------------- #
# 个人规划接口
# --------------------------------------------------------------------------- #

def test_plan_endpoint_computes_this_students_own_tasks(client: TestClient, catalog_dir):
    response = client.post(PLAN_PATH, json=_body())
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["target_version"]["version_id"] == TARGET_VERSION_ID
    assert payload["data_source"] == "mock"
    assert payload["completed_source_id"].startswith("personal-upload://sha256:")
    statuses = {task["course_id"]: task["status"] for task in payload["makeup_tasks"]}
    assert statuses["TGT100"] == "satisfied"
    assert statuses["TGT101"] == "required"
    # 已明确选中的选修课 TGT201 在组缺口尚未满足时也是补修任务；
    # 未被选中的 TGT202 按既有规则保留在课程池，不进入补修任务列表。
    assert statuses["TGT201"] == "required"
    assert "TGT202" not in statuses
    assert payload["status_counts"] == {"satisfied": 1, "required": 2}
    # 没有教学班供给 → 明确说明为什么没有规划结果，而不是留空。
    assert payload["planning"] is None
    assert payload["planning_skipped_code"] == "no_course_data"
    assert "no_course_data" in payload["planning_skipped_reason"]


def test_two_students_get_different_results_through_the_api(client: TestClient, catalog_dir):
    first = client.post(PLAN_PATH, json=_body(student=student_one_input()))
    second = client.post(PLAN_PATH, json=_body(student=student_two_input()))
    assert first.status_code == 200 and second.status_code == 200

    one = {task["course_id"]: task["status"] for task in first.json()["makeup_tasks"]}
    two = {task["course_id"]: task["status"] for task in second.json()["makeup_tasks"]}
    assert one["TGT101"] == "satisfied"
    assert two["TGT101"] == "required"
    # 内容绑定的来源 id 不同 → 两人的材料不会被当成同一份。
    assert first.json()["completed_source_id"] != second.json()["completed_source_id"]


def test_plan_endpoint_rejects_an_unselectable_version(client: TestClient, catalog_dir):
    response = client.post(PLAN_PATH, json=_body(target_version_id="not-in-the-catalog"))
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "personal_plan_input_invalid"


def test_plan_endpoint_rejects_unknown_request_fields(client: TestClient, catalog_dir):
    body = _body()
    body["student_name"] = "示例姓名"
    response = client.post(PLAN_PATH, json=body)
    assert response.status_code == 422  # pydantic extra=forbid


def test_plan_endpoint_rejects_duplicate_preference_locations(client: TestClient, catalog_dir):
    student = student_two_input()
    student["preference"] = {"max_credit": 10}
    response = client.post(PLAN_PATH, json=_body(student=student, preference={"max_credit": 10}))
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "personal_plan_input_conflict"


def test_plan_endpoint_is_503_without_a_configured_catalog(client: TestClient, monkeypatch):
    monkeypatch.delenv("APP_PERSONAL_CATALOG_DIR", raising=False)
    response = client.post(PLAN_PATH, json=_body())
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "personal_catalog_not_configured"


def test_plan_endpoint_does_not_touch_the_frozen_plan_contract(client: TestClient, catalog_dir):
    """个人入口不得改变 `/api/v1/plan` 的请求契约（多给字段仍然被拒）。"""

    response = client.post(
        "/api/v1/plan",
        json={
            "semester": "2026-1",
            "current_schedule": [],
            "preference": {},
            "old_version_id": OLD_VERSION_ID,
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Planner 接入（用进程内 Mock 教学班，不经 production runtime）
# --------------------------------------------------------------------------- #

def section(cid: str, class_id: str, day: int, credit: float | None = 3.0) -> CourseOffering:
    return CourseOffering(
        course_id=cid, course_name=f"Mock {cid}", class_id=class_id, semester="2026-1",
        credit=credit,
        meetings=[Meeting(weekday=day, start_section=1, end_section=2, weeks=[1, 3])],
        data_source="mock",
    )


def test_planner_runs_on_this_students_tasks_only(tmp_path):
    catalog = load_catalog(tmp_path)
    from app.personal import normalize_personal_plan_request
    from app.models.contracts import DataSource

    request = normalize_personal_plan_request(
        {
            "old_version_id": OLD_VERSION_ID,
            "target_version_id": TARGET_VERSION_ID,
            "semester": "2026-1",
            "student": student_two_input(),
        },
        catalog=catalog,
        data_source=DataSource.MOCK,
        completed_source_id="mock://personal/planner-test",
    )
    result = build_personal_plan(
        catalog, request,
        planner=RestrictedPlannerProvider(),
        offerings=[section("TGT101", "t101-a", 1)],
    )
    assert result.planning is not None
    assert result.planning_skipped_reason is None
    selected = {(item.course_id, item.class_id) for item in result.planning.selected_classes}
    assert ("TGT101", "t101-a") in selected
    # Planner 只看到本学生的补修任务：没有出现学生一/其他人的课程。
    assert {change.course_id for change in result.planning.changes} <= {"TGT101"}


def test_planner_rejects_a_result_outside_this_students_tasks(tmp_path):
    """Planner 若返回本学生任务之外的课程，必须报错而不是被当成有效方案。"""

    from app.models.contracts import DataSource, PlanResult, SelectedClass
    from app.personal import (
        PersonalPlanResult,
        normalize_personal_plan_request,
    )

    catalog = load_catalog(tmp_path)
    request = normalize_personal_plan_request(
        {
            "old_version_id": OLD_VERSION_ID,
            "target_version_id": TARGET_VERSION_ID,
            "student": student_two_input(),
        },
        catalog=catalog,
        data_source=DataSource.MOCK,
        completed_source_id="mock://personal/planner-test",
    )
    result = build_personal_plan(catalog, request)
    alien = PlanResult(
        status="feasible",
        selected_classes=[SelectedClass(course_id="SOMEONE-ELSE-COURSE", class_id="x")],
        changes=[], risks=[], unresolved=[],
    )
    with pytest.raises(Exception, match="outside this student's makeup tasks"):
        PersonalPlanResult(
            old_version=result.old_version, target_version=result.target_version,
            data_source=result.data_source,
            completed_source_id=result.completed_source_id,
            completed_record_count=result.completed_record_count,
            makeup_tasks=result.makeup_tasks, planning=alien,
            planning_skipped_reason=None,
        )


def test_credit_limit_is_honoured_for_personal_planning_additions(tmp_path):
    """学生自己声明的学分上限必须影响新增接纳（新增无冲突 ≠ 不超限）。"""

    catalog = load_catalog(tmp_path)
    from app.models.contracts import DataSource
    from app.personal import normalize_personal_plan_request

    student = student_two_input()
    del student["elective_selections"]
    student["elective_selections"] = [{
        "group_id": "MOCK-TGT-ELECTIVE", "course_ids": ["TGT201"],
        "evidence": "mock://personal/planner-test/选修计划",
    }]
    student["preference"] = {"max_credit": 0}
    request = normalize_personal_plan_request(
        {
            "old_version_id": OLD_VERSION_ID,
            "target_version_id": TARGET_VERSION_ID,
            "semester": "2026-1",
            "student": student,
        },
        catalog=catalog,
        data_source=DataSource.MOCK,
        completed_source_id="mock://personal/planner-test",
    )
    result = build_personal_plan(
        catalog, request,
        planner=RestrictedPlannerProvider(),
        offerings=[section("TGT101", "t101-a", 1, credit=4.0)],
    )
    assert result.planning is not None
    messages = " ".join(item.message for item in result.planning.unresolved)
    assert "学分上限" in messages
    assert ("TGT101", "t101-a") not in {
        (item.course_id, item.class_id) for item in result.planning.selected_classes
    }


def test_preference_object_is_passed_through_unchanged(tmp_path):
    catalog = load_catalog(tmp_path)
    from app.models.contracts import DataSource
    from app.personal import normalize_personal_plan_request

    student = student_two_input()
    student["preference"] = {"max_credit": 30, "notes": "示例备注"}
    request = normalize_personal_plan_request(
        {
            "old_version_id": OLD_VERSION_ID,
            "target_version_id": TARGET_VERSION_ID,
            "semester": "2026-1",
            "student": student,
        },
        catalog=catalog,
        data_source=DataSource.MOCK,
        completed_source_id="mock://personal/planner-test",
    )
    assert request.student.preference == Preference(max_credit=30, notes="示例备注")
    assert json.loads(json.dumps(request.student.preference.model_dump()))["max_credit"] == 30
