"""API-level proof of the **positive** Case A roadmap path.

`test_case_a_demo_e2e.py` uses a synthetic curriculum that has **no term facts**, so it
correctly proves the fail-closed branch (`roadmap == null` + note). This module proves the
other branch: when the curriculum does carry term facts, the endpoint must return a
course-level roadmap that satisfies every boundary the review cares about.

Zero network: synthetic transcript + synthetic curriculum + a temp SQLite store.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.course_data import (
    CaseAScopedCourseDataProvider,
    build_case_a_dataset,
    initialize_course_data_store,
)
from app.curriculum.case import load_curriculum_case
from app.main import app
from app.models.contracts import DataSource, Preference
from app.planner import RestrictedPlannerProvider
from app.services.case_a_demo import (
    CASE_A_ELECTIVE_GROUP_ID,
    CaseADemoRuntime,
    get_case_a_demo_runtime,
)
from tests import pdf_fixtures
from tests.test_case_a_course_data_scope import SHENZHEN, SOUTH, _import_campus, _offering

SEMESTER = "2026-1"
GROUP = CASE_A_ELECTIVE_GROUP_ID

#: 培养方案真实存在的学期跨度：当前 2026-1 = 第 3 学期。
TERM_SPAN = ("2025-1", "2025-2", "2026-1", "2026-2", "2027-1")


def _course(
    course_id: str,
    name: str,
    credit: float,
    *,
    term: str,
    requirement: str = "required",
    group_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "course_id": course_id,
        "course_name": name,
        "credit": credit,
        "requirement": requirement,
        "source_record": f"row:{course_id}",
        "prerequisites": None,
        "recommended_term_text": term,
    }
    if group_id is not None:
        payload["group_id"] = group_id
    return payload


def _case_payload() -> dict[str, object]:
    return {
        "data_source": "mock",
        "old": {
            "version_id": "synthetic-old",
            "major": "示例源专业",
            "cohort": "2025",
            "source_id": "synthetic://old",
            "complete": True,
            "completeness_evidence": "synthetic://old/scope",
            "course_records": [_course("OLD-1", "示例旧专业课", 3.0, term="2025-1")],
        },
        "new": {
            "version_id": "synthetic-new",
            "major": "示例目标专业",
            "cohort": "2025",
            "source_id": "synthetic://new",
            "complete": True,
            "completeness_evidence": "synthetic://new/scope",
            "course_records": [
                # 转专业前的历史学期：让学期号链覆盖完整跨度
                _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
                _course("PAST-2", "示例已过必修 2", 2.0, term="2025-2"),
                # 未来学期必修
                _course("REQ-A", "示例必修 A", 3.0, term="2026-2"),
                _course("REQ-B", "示例必修 B", 3.0, term="2027-1"),
                # 未来学期选修池：整组都落在 future 窗口，因此无需历史份额拆分
                # （⛔ 这不是绕过校验，而是让本用例只考察"池 ≠ 全必修"这一件事）。
                _course("EL-1", "示例选修 1", 3.0, term="2026-2",
                        requirement="elective", group_id=GROUP),
                _course("EL-2", "示例选修 2", 3.0, term="2026-2",
                        requirement="elective", group_id=GROUP),
                _course("EL-3", "示例选修 3", 3.0, term="2026-2",
                        requirement="elective", group_id=GROUP),
            ],
            "group_records": [
                {
                    "group_id": GROUP,
                    "name": "示例专业选修池",
                    "minimum_credit": 6.0,
                    "source_record": "row:group",
                }
            ],
        },
        "completed": {
            "source_id": "synthetic://completed",
            "complete": True,
            "completeness_evidence": "synthetic://completed/scope",
            "records": [],
        },
        # 显式 makeup scope：转专业的历史窗口截止到 2025-2，因此 2026-2 起的选修池
        # 整组落在 future 窗口（该组不声明任何历史份额，⛔ 不需要拆分）。
        "makeup_scope": {
            "target_version_id": "synthetic-new",
            "as_of_term": "2025-2",
            "evidence": "synthetic://makeup-scope",
        },
    }


@pytest.fixture()
def term_bearing_runtime(tmp_path: Path) -> tuple[CaseADemoRuntime, bytes]:
    store = tmp_path / "case-a.sqlite3"
    initialize_course_data_store(store)
    _import_campus(
        store,
        number=SOUTH,
        offerings=[_offering("REQ-A", "01", semester=SEMESTER, course_name="示例必修 A")],
    )
    _import_campus(
        store,
        number=SHENZHEN,
        offerings=[_offering("REQ-B", "01", semester=SEMESTER, course_name="示例必修 B")],
    )
    dataset = build_case_a_dataset(store, semester=SEMESTER)

    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(_case_payload(), ensure_ascii=False), encoding="utf-8")
    runtime = CaseADemoRuntime(
        base_case=load_curriculum_case(case_path),
        course_data=CaseAScopedCourseDataProvider(dataset),
        planner=RestrictedPlannerProvider(),
    )
    pdf_path = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "transcript.pdf")
    return runtime, pdf_path.read_bytes()


def _plan(runtime: CaseADemoRuntime, pdf: bytes) -> dict:
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        response = TestClient(app).post(
            "/api/v1/case-a-demo/plan",
            json={
                "semester": SEMESTER,
                "transcript_pdf_base64": base64.b64encode(pdf).decode("ascii"),
                "current_schedule": [],
                "manual_schedule_attested": False,
                "preference": Preference().model_dump(mode="json"),
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json()


def test_roadmap_is_returned_with_explicit_curriculum_semesters(
    term_bearing_runtime: tuple[CaseADemoRuntime, bytes],
) -> None:
    runtime, pdf = term_bearing_runtime
    body = _plan(runtime, pdf)

    roadmap = body["roadmap"]
    assert roadmap is not None, body["roadmap_note"]

    semesters = roadmap["future_semesters"]
    # 当前 2026-1 = 培养方案第 3 学期 ⇒ 未来是第 4、5 学期（⛔ 不是从 1 重新编号）
    assert [(item["semester_label"], item["curriculum_semester"]) for item in semesters] == [
        ("2026-2", 4),
        ("2027-1", 5),
    ]
    assert [item["semester_index"] for item in semesters] == [1, 2]

    by_id = {
        course["course_id"]: semester["curriculum_semester"]
        for semester in semesters
        for course in semester["courses"]
    }
    # 课程自身的学期事实决定落位
    assert by_id["REQ-A"] == 4
    assert by_id["REQ-B"] == 5


def test_roadmap_future_courses_carry_no_section_level_field(
    term_bearing_runtime: tuple[CaseADemoRuntime, bytes],
) -> None:
    runtime, pdf = term_bearing_runtime
    roadmap = _plan(runtime, pdf)["roadmap"]
    assert roadmap is not None

    forbidden = {
        "class_id",
        "teacher",
        "weekday",
        "start_section",
        "end_section",
        "weeks",
        "campus",
        "classroom",
        "capacity",
        "remaining_capacity",
        "meetings",
    }
    allowed = {
        "course_id",
        "course_name",
        "credit",
        "requirement_kind",
        "requirement_label",
        "placement",
        "reason",
    }
    for semester in roadmap["future_semesters"]:
        assert not (set(semester) & forbidden)
        for course in semester["courses"]:
            assert not (set(course) & forbidden), set(course) & forbidden
            # 多余的字段同样不允许：字段集是**锁定**的
            assert set(course) == allowed, set(course) ^ allowed


def test_elective_pool_is_not_treated_as_all_required_and_gap_is_exact(
    term_bearing_runtime: tuple[CaseADemoRuntime, bytes],
) -> None:
    runtime, pdf = term_bearing_runtime
    roadmap = _plan(runtime, pdf)["roadmap"]
    assert roadmap is not None

    elective = roadmap["elective"]
    assert elective["requirement_credit"] == 6.0
    assert elective["completed_credit"] == 0.0
    assert elective["current_semester_credit"] == 0.0
    assert elective["gap_credit"] == 6.0
    # 只补足 6 学分缺口（池里共 12 学分）⇒ ⛔ 不得把整个池当成必修
    assert elective["planned_credit"] == 6.0
    assert elective["remaining_credit"] == 0.0

    planned_courses = [
        course["course_id"]
        for semester in roadmap["future_semesters"]
        for course in semester["courses"]
    ]
    elective_planned = [item for item in planned_courses if item.startswith("EL-")]
    assert len(elective_planned) == 2  # 2 × 3 学分 = 6
    assert planned_courses.count("REQ-A") == 1
    assert planned_courses.count("REQ-B") == 1
    # 未满足的**已过**学期课程仍要补修（⛔ 不被静默丢弃）
    assert "PAST-1" in planned_courses
    assert "PAST-2" in planned_courses


def test_repair_apply_is_never_called_by_planning(
    term_bearing_runtime: tuple[CaseADemoRuntime, bytes],
) -> None:
    """生成方案**绝不**改动课表：`plan_result.changes` 为空且课表原样。"""

    runtime, pdf = term_bearing_runtime
    body = _plan(runtime, pdf)
    assert body["plan_result"]["changes"] == []
    assert body["repair_proposals"]["semester"] == SEMESTER
