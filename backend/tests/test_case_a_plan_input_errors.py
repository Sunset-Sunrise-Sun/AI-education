"""Case A `/plan` input-shape errors must be 422/409, never an unhandled 500.

Regression cover for the two shapes the Planner rejects internally:

* the same teaching-class identity submitted twice;
* two different classes of the same course in one current schedule.

Both are things the *caller* can fix, so the API must report them as request errors
with a message a user can act on, while every existing fail-closed, provenance and
manual-confirmation check stays exactly where it was.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.contracts import CourseOffering, DataSource
from app.services.case_a_demo import CaseADemoRuntime, get_case_a_demo_runtime
from tests.test_case_a_demo_e2e import (  # noqa: F401  (fixture re-export)
    SEMESTER,
    _manual,
    runtime_and_pdf,
)

PREFERENCE = {
    "max_credit": None,
    "avoid_cross_campus": False,
    "preferred_courses": [],
    "avoid_times": [],
    "notes": None,
}


def _post(runtime: CaseADemoRuntime, pdf: bytes, schedule: list[dict]) -> object:
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        return TestClient(app).post(
            "/api/v1/case-a-demo/plan",
            json={
                "semester": SEMESTER,
                "transcript_pdf_base64": base64.b64encode(pdf).decode("ascii"),
                "current_schedule": schedule,
                "manual_schedule_attested": True,
                "preference": PREFERENCE,
            },
        )
    finally:
        app.dependency_overrides.clear()


def _real_class(course_id: str, class_id: str) -> dict:
    """A caller-supplied real teaching class (non-manual), i.e. an accepted offering."""
    return CourseOffering(
        course_id=course_id,
        course_name="示例课程",
        class_id=class_id,
        semester=SEMESTER,
        meetings=[],
        source="capture://synthetic/case-a",
        data_source=DataSource.REAL,
    ).model_dump(mode="json")


def test_duplicate_teaching_class_identity_is_422_not_500(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """The same (semester, course_id, class_id) twice is a request error."""
    runtime, pdf = runtime_and_pdf
    item = _manual().model_dump(mode="json")

    response = _post(runtime, pdf, [item, dict(item)])

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "case_a_demo_duplicate_offering"
    assert "重复教学班身份" in detail["message"]
    # The message must tell the caller how to fix it.
    assert "只能提交一次" in detail["message"]


def test_two_classes_of_one_course_is_422_not_500(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """Two different class ids for one course must not reach the Planner as a 500."""
    runtime, pdf = runtime_and_pdf

    response = _post(runtime, pdf, [_real_class("TGT-ALG", "01"), _real_class("TGT-ALG", "02")])

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "case_a_demo_multiple_classes_for_course"
    assert "多个已选班" in detail["message"]
    assert "明确" in detail["message"]


def test_duplicate_check_runs_before_the_planner(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """The duplicate shape is rejected at the API boundary, so the Planner never runs."""
    runtime, pdf = runtime_and_pdf
    item = _manual().model_dump(mode="json")

    calls: list[str] = []
    original = runtime.planner.plan

    def spy(**kwargs: object):  # type: ignore[no-untyped-def]
        calls.append("plan")
        return original(**kwargs)  # type: ignore[arg-type]

    object.__setattr__(runtime.planner, "plan", spy)
    try:
        response = _post(runtime, pdf, [item, dict(item)])
    finally:
        object.__setattr__(runtime.planner, "plan", original)

    assert response.status_code == 422
    assert calls == [], "the Planner must not be invoked for a rejected input shape"


def test_valid_single_class_input_still_succeeds(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """The fix must not reject legitimate input."""
    runtime, pdf = runtime_and_pdf

    response = _post(runtime, pdf, [_manual().model_dump(mode="json")])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_result"]["selected_classes"]
    assert "mock" not in response.text.lower()


def test_empty_schedule_is_still_accepted(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """An empty current schedule is legal and must not trip the new checks."""
    runtime, pdf = runtime_and_pdf

    response = _post(runtime, pdf, [])

    assert response.status_code == 200, response.text
    assert response.json()["plan_result"]["selected_classes"] == []


def test_unexpected_planner_failure_is_not_rewritten_as_a_user_input_error(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """An unknown Planner failure must never be re-labelled as a fixable request error.

    The API boundary only translates the two shapes it explicitly validates; anything
    else propagates untouched, so it surfaces as a server fault and its internal message
    is **not** handed to the caller as something they could act on.
    """
    runtime, pdf = runtime_and_pdf
    sentinel = "unexpected-planner-invariant-xyz"
    original = runtime.planner.plan

    def boom(**kwargs: object):  # type: ignore[no-untyped-def]
        raise ValueError(sentinel)

    object.__setattr__(runtime.planner, "plan", boom)
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        # raise_server_exceptions=False: observe the real HTTP response instead of
        # letting TestClient re-raise the unhandled exception in-process.
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/case-a-demo/plan",
            json={
                "semester": SEMESTER,
                "transcript_pdf_base64": base64.b64encode(pdf).decode("ascii"),
                "current_schedule": [_manual().model_dump(mode="json")],
                "manual_schedule_attested": True,
                "preference": PREFERENCE,
            },
        )
    finally:
        object.__setattr__(runtime.planner, "plan", original)
        app.dependency_overrides.clear()

    # Not a "your input is wrong" answer: neither of the corrective statuses.
    assert response.status_code not in (409, 422), response.text
    assert response.status_code == 500, response.text

    body = response.text
    # The internal message must not be used as a caller-facing correction hint.
    assert sentinel not in body
    for hint in ("重复教学班身份", "多个已选班", "case_a_demo_duplicate_offering",
                 "case_a_demo_multiple_classes_for_course", "case_a_demo_planner_input_rejected"):
        assert hint not in body


def test_only_the_two_validated_shapes_are_translated(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """Guard the boundary: exactly the two validated shapes get a corrective 422.

    A shape that the API does *not* pre-validate (here: an inverted avoid_times range,
    which the Planner rejects on its own) must not be silently relabelled either.
    """
    runtime, pdf = runtime_and_pdf
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/case-a-demo/plan",
            json={
                "semester": SEMESTER,
                "transcript_pdf_base64": base64.b64encode(pdf).decode("ascii"),
                "current_schedule": [_manual().model_dump(mode="json")],
                "manual_schedule_attested": True,
                "preference": {
                    **PREFERENCE,
                    "avoid_times": [{"weekday": 1, "start_section": 5, "end_section": 3}],
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code not in (409,), response.text
    assert "case_a_demo_planner_input_rejected" not in response.text


def test_runtime_missing_is_still_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fail-closed behaviour is untouched: no runtime still means 503."""
    monkeypatch.delenv("APP_CASE_A_DEMO_ENABLED", raising=False)
    response = TestClient(app).post(
        "/api/v1/case-a-demo/plan",
        json={
            "semester": SEMESTER,
            "transcript_pdf_base64": "eA==",
            "current_schedule": [],
            "manual_schedule_attested": False,
            "preference": PREFERENCE,
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "case_a_demo_not_configured"


def test_attestation_boundary_is_untouched(
    runtime_and_pdf: tuple[CaseADemoRuntime, bytes],
) -> None:
    """A manual entry without attestation is still rejected by the service (422)."""
    runtime, pdf = runtime_and_pdf
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        response = TestClient(app).post(
            "/api/v1/case-a-demo/plan",
            json={
                "semester": SEMESTER,
                "transcript_pdf_base64": base64.b64encode(pdf).decode("ascii"),
                "current_schedule": [_manual().model_dump(mode="json")],
                "manual_schedule_attested": False,
                "preference": PREFERENCE,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422, response.text
    assert "attest" in response.text.lower() or "确认" in response.text
