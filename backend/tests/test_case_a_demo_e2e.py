"""Synthetic, zero-network proof of the distinct Case A closed loop."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.course_data import CaseAScopedCourseDataProvider, build_case_a_dataset, initialize_course_data_store
from app.curriculum.case import load_curriculum_case
from app.main import app
from app.models.contracts import CourseOffering, DataSource, Preference
from app.planner import RestrictedPlannerProvider
from app.services.case_a_demo import (
    CASE_A_DEMO_SCOPE_LABEL,
    MANUAL_SCHEDULE_SOURCE,
    CaseADemoInputError,
    CaseADemoRuntime,
    build_case_a_demo_runtime,
    get_case_a_demo_runtime,
)
from tests import pdf_fixtures
from tests.test_case_a_course_data_scope import SHENZHEN, SOUTH, _import_campus, _offering
from tests.test_curriculum_pdf_case_a_integration import _case_payload, _write_case

SEMESTER = "2026-1"


def test_demo_runtime_is_disabled_and_fail_closed_by_default() -> None:
    assert build_case_a_demo_runtime({}) is None
    assert build_case_a_demo_runtime({"APP_CASE_A_DEMO_ENABLED": "1"}) is None


def test_demo_api_is_503_without_explicit_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_CASE_A_DEMO_ENABLED", raising=False)
    response = TestClient(app).get(
        "/api/v1/case-a-demo/offerings", params={"semester": SEMESTER}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "case_a_demo_not_configured"


@pytest.fixture()
def runtime_and_pdf(tmp_path: Path) -> tuple[CaseADemoRuntime, bytes]:
    store = tmp_path / "case-a.sqlite3"
    initialize_course_data_store(store)
    unknown = _offering(
        "TGT-NET", "01", semester=SEMESTER, course_name="示例网络原理", meetings=[]
    )
    _import_campus(store, number=SOUTH, offerings=[unknown])
    _import_campus(
        store,
        number=SHENZHEN,
        offerings=[_offering("TGT-ALG", "01", semester=SEMESTER, course_name="示例线性代数")],
    )
    dataset = build_case_a_dataset(store, semester=SEMESTER)

    # Base case carries the approved target/scope decisions. Its completed input is replaced below.
    base_case = load_curriculum_case(_write_case(tmp_path, _case_payload(None), "base-case.json"))
    runtime = CaseADemoRuntime(
        base_case=base_case,
        course_data=CaseAScopedCourseDataProvider(dataset),
        planner=RestrictedPlannerProvider(),
    )
    pdf_path = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "transcript.pdf")
    return runtime, pdf_path.read_bytes()


def _manual() -> CourseOffering:
    return CourseOffering(
        course_id="MANUAL-1",
        course_name="本人课表课程",
        class_id="01",
        semester=SEMESTER,
        meetings=[],
        source=MANUAL_SCHEDULE_SOURCE,
        data_source=DataSource.REAL,
    )


def test_manual_schedule_requires_explicit_attestation(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    runtime, pdf = runtime_and_pdf
    with pytest.raises(CaseADemoInputError):
        runtime.run(
            pdf_bytes=pdf,
            semester=SEMESTER,
            current_schedule=[_manual()],
            preference=Preference(),
            manual_schedule_attested=False,
        )


def test_pdf_to_curriculum_case_scope_planner_and_api_closed_loop(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    runtime, pdf = runtime_and_pdf
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        response = TestClient(app).post(
            "/api/v1/case-a-demo/plan",
            json={
                "semester": SEMESTER,
                "transcript_pdf_base64": base64.b64encode(pdf).decode("ascii"),
                "current_schedule": [_manual().model_dump(mode="json")],
                "manual_schedule_attested": True,
                "preference": {
                    "max_credit": None,
                    "avoid_cross_campus": False,
                    "preferred_courses": [],
                    "avoid_times": [],
                    "notes": None,
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"]["record_count"] == 4
    assert body["transcript"]["pending_course_id_count"] == 4
    assert body["makeup_tasks"]
    assert body["course_offerings"]
    assert all(item["data_source"] == "real" for item in body["course_offerings"])
    assert body["provenance"]["course_data"] == CASE_A_DEMO_SCOPE_LABEL
    assert body["provenance"]["is_full_semester"] is False
    assert "mock" not in response.text.lower()
    # meetings=[] is UNKNOWN, not clear; the manual current class remains a recommendation.
    assert any(item["type"] == "schedule_unknown" for item in body["plan_result"]["unresolved"])
    assert {tuple(item.values()) for item in body["plan_result"]["selected_classes"]} >= {
        ("MANUAL-1", "01")
    }
    assert body["plan_result"]["risks"] == []


def test_case_scope_offerings_endpoint_uses_same_runtime(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    runtime, _pdf = runtime_and_pdf
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        response = TestClient(app).get(
            "/api/v1/case-a-demo/offerings", params={"semester": SEMESTER}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert len(response.json()) == 2
