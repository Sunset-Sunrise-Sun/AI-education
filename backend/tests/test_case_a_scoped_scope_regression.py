"""Case A scope regression: the approved scoped configuration, end to end.

This module exists because the previous demo E2E built its case with
``_case_payload(None)`` - i.e. **no** ``makeup_scope`` and **no** scope decisions -
so the whole scoped configuration was never exercised and the real 500
(``makeup scope: target entries have no confirmable arrangement term``) went
undetected.

The case here is synthetic (⛔ no private artifact), but it carries the **real
approved decision set** and a real ``makeup_scope`` cut-off, with ``range``
arrangement terms on the three historical entries, and completed records that look
exactly like an uploaded transcript: ``course_id=None`` / ``pending``.

What it proves:

- the scoped path does not depend on confirmed PDF course ids;
- it does not depend on a Mock curriculum, nor on a missing ``makeup_scope``;
- historical scope decisions discharge the range entries *for scope only* - the
  three courses stay ``manual_confirmation`` and are never silently SATISFIED.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.curriculum.case import load_curriculum_case
from app.curriculum.case_a_decisions import AS_OF_TERM, confirmed_scope_decisions
from app.course_data import CaseAScopedCourseDataProvider, build_case_a_dataset, initialize_course_data_store
from app.main import app
from app.models.contracts import CourseOffering, DataSource, Preference
from app.planner import RestrictedPlannerProvider
from app.services.case_a_demo import (
    CASE_A_DEMO_SCOPE_LABEL,
    CaseADemoRuntime,
    build_case_a_demo_runtime,
    get_case_a_demo_runtime,
)
from tests import pdf_fixtures
from tests.test_case_a_course_data_scope import SHENZHEN, SOUTH, _import_campus, _offering

SEMESTER = "2026-1"

#: The three entries whose arrangement range ends at the Case A cut-off.
HISTORICAL_IDS = ("MAR116", "PSY199", "PUB1991")
#: The four entries decided ``future`` (they must never project as current makeup).
FUTURE_IDS = ("MAR117", "MAR118", "MAR119", "PUB178")

#: The transcript-visible names of the three historical courses. A real transcript
#: carries these names but no course id.
HISTORICAL_NAMES = {
    "MAR116": "形势与政策（一·走在前列的广东实践）",
    "PSY199": "心理健康教育",
    "PUB1991": "国家安全教育",
}


def _course(
    course_id: str,
    name: str,
    credit: float,
    *,
    term: str | None,
    source_record: str,
    requirement: str = "required",
) -> dict:
    return {
        "course_id": course_id,
        "course_name": name,
        "credit": credit,
        "requirement": requirement,
        "source_record": source_record,
        "prerequisites": [],
        "deadline_semester": 5,
        "recommended_semester": 3,
        "recommended_term_text": term,
    }


def _target_courses() -> list[dict]:
    """The three historical range entries plus the four future range entries."""
    courses = [
        # `2025-1~2025-2` ends at the cut-off -> the range parser cannot interpret it.
        _course("MAR116", HISTORICAL_NAMES["MAR116"], 1.0,
                term="2025-1~2025-2", source_record="table:2!row:8"),
        _course("PSY199", HISTORICAL_NAMES["PSY199"], 2.0,
                term="2025-1~2025-2", source_record="table:2!row:9"),
        _course("PUB1991", HISTORICAL_NAMES["PUB1991"], 1.0,
                term="2025-1~2025-2", source_record="table:2!row:10"),
        # `2025-1~2028-2` crosses the cut-off; decided future by case-owner ruling.
        _course("PUB178", "劳动教育", 1.0,
                term="2025-1~2028-2", source_record="table:2!row:11"),
        _course("MAR117", "示例未来课一", 1.0,
                term="2026-1~2026-2", source_record="table:2!row:19"),
        _course("MAR118", "示例未来课二", 1.0,
                term="2027-1~2027-2", source_record="table:2!row:24"),
        _course("MAR119", "示例未来课三", 1.0,
                term="2028-1~2028-2", source_record="table:2!row:26"),
    ]
    return courses


def _scoped_case_payload() -> dict:
    """A real-marked case WITH makeup_scope and the real approved decision set."""
    return {
        "data_source": "real",
        "old": {
            "version_id": "case-a-old",
            "major": "示例原专业",
            "cohort": "2025",
            "source_id": "case-owner-confirmed://regression/old",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://regression/old/complete",
            "course_records": [
                _course("OLD1", "示例旧专业课", 3.0, term="2025-1",
                        source_record="row:OLD1"),
            ],
        },
        "new": {
            "version_id": "case-a-new",
            "major": "示例目标专业",
            "cohort": "2025",
            "source_id": "case-owner-confirmed://regression/new",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://regression/new/complete",
            "course_records": _target_courses(),
        },
        "completed": {
            "source_id": "case-owner-confirmed://regression/completed",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://regression/completed/complete",
            # Transcript-shaped: names present, NO course ids.
            "records": [
                {
                    "course_id": None,
                    "course_name": HISTORICAL_NAMES[course_id],
                    "credit": credit,
                    "semester": "2025-1",
                    "passed": True,
                    "course_type": "公必",
                    "course_id_status": "pending",
                    "id_match_source": None,
                    "source_record": f"pdf:{index}",
                }
                for index, (course_id, credit) in enumerate(
                    (("MAR116", 1.0), ("PSY199", 2.0), ("PUB1991", 1.0)), start=1
                )
            ],
        },
        "makeup_scope": {
            "target_version_id": "case-a-new",
            "as_of_term": AS_OF_TERM,
            "evidence": "case-owner-confirmed://regression/as-of-term",
        },
        "confirmed_scope_decisions": [
            {
                "target_version_id": decision.target_version_id,
                "target_source_record": decision.target_source_record,
                "target_course_id": decision.target_course_id,
                "decision": decision.decision,
                "evidence": decision.evidence,
            }
            for decision in confirmed_scope_decisions()
        ],
    }


def _write_case(tmp_path: Path) -> Path:
    import json

    path = tmp_path / "scoped-case.json"
    path.write_text(json.dumps(_scoped_case_payload(), ensure_ascii=False), encoding="utf-8")
    return path


def _manual() -> CourseOffering:
    return CourseOffering(
        course_id="MANUAL-1",
        course_name="本人课表课程",
        class_id="01",
        semester=SEMESTER,
        meetings=[],
        source="manual-entry://current-schedule",
        data_source=DataSource.REAL,
    )


def test_the_scoped_case_payload_actually_carries_a_scope_and_decisions(tmp_path: Path) -> None:
    """Guard the guard: this fixture must genuinely require the historical decisions.

    Without them the three range entries are ``unresolved`` and projection fails
    closed - which is exactly the failure this module regression-tests. With them the
    entries are ``historical``.
    """

    from dataclasses import replace

    from app.curriculum.case import CurriculumCaseProvider
    from app.curriculum.errors import CurriculumNormalizationError
    from app.curriculum.terms import SCOPE_HISTORICAL, SCOPE_UNRESOLVED

    historical_records = {"table:2!row:8", "table:2!row:9", "table:2!row:10"}
    case = load_curriculum_case(_write_case(tmp_path))

    assert case.makeup_scope is not None, "the fixture must carry a makeup_scope"
    assert case.makeup_scope.as_of_term == AS_OF_TERM
    assert len(case.confirmed_scope_decisions) == 7
    assert case.data_source.value == "real"

    def buckets_of(value):  # type: ignore[no-untyped-def]
        return value.build_diff().scope_buckets_by_entry()

    # WITH the approved (historical) decisions the three entries are historical.
    resolved = buckets_of(case)
    assert {record for record in historical_records if resolved.get(record) == SCOPE_HISTORICAL} == (
        historical_records
    )

    # WITHOUT them the very same entries are unresolved and projection fails closed,
    # so this fixture cannot silently degenerate into the old "no makeup_scope" blind spot.
    future_only = replace(
        case,
        confirmed_scope_decisions=tuple(
            decision for decision in case.confirmed_scope_decisions
            if decision.decision == "future"
        ),
    )
    unresolved = buckets_of(future_only)
    assert {record for record in historical_records if unresolved.get(record) == SCOPE_UNRESOLVED} == (
        historical_records
    )
    with pytest.raises(CurriculumNormalizationError):
        CurriculumCaseProvider(future_only).get_makeup_tasks()


@pytest.fixture()
def scoped_runtime(tmp_path: Path) -> tuple[CaseADemoRuntime, bytes]:
    store = tmp_path / "case-a.sqlite3"
    initialize_course_data_store(store)
    _import_campus(
        store,
        number=SOUTH,
        offerings=[_offering("TGT-NET", "01", semester=SEMESTER, course_name="示例网络原理", meetings=[])],
    )
    _import_campus(
        store,
        number=SHENZHEN,
        offerings=[_offering("TGT-ALG", "01", semester=SEMESTER, course_name="示例线性代数")],
    )
    dataset = build_case_a_dataset(store, semester=SEMESTER)
    base_case = load_curriculum_case(_write_case(tmp_path))
    runtime = CaseADemoRuntime(
        base_case=base_case,
        course_data=CaseAScopedCourseDataProvider(dataset),
        planner=RestrictedPlannerProvider(),
    )
    pdf = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "transcript.pdf")
    return runtime, pdf.read_bytes()


def test_scoped_run_does_not_raise_the_arrangement_term_error(
    scoped_runtime: tuple[CaseADemoRuntime, bytes],
) -> None:
    """Regression for the real 500: the scoped configuration must project."""

    runtime, pdf = scoped_runtime
    run = runtime.run(
        pdf_bytes=pdf,
        semester=SEMESTER,
        current_schedule=[],
        preference=Preference(),
        manual_schedule_attested=False,
    )
    assert run.makeup_tasks, "the scoped configuration must produce makeup tasks"
    assert not any(task.status.value == "satisfied" for task in run.makeup_tasks)


def test_api_closed_loop_with_scope_and_decisions(
    scoped_runtime: tuple[CaseADemoRuntime, bytes],
) -> None:
    import base64

    runtime, pdf = scoped_runtime
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        response = TestClient(app).post(
            "/api/v1/case-a-demo/plan",
            json={
                "semester": SEMESTER,
                "transcript_pdf_base64": base64.b64encode(pdf).decode("ascii"),
                "current_schedule": [],
                "manual_schedule_attested": False,
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
    assert body["makeup_tasks"]
    statuses = {task["course_id"]: task["status"] for task in body["makeup_tasks"]}

    # The three historical entries are in scope, but the transcript carries no
    # course id -> they remain manual confirmation and are never auto-satisfied.
    for course_id in HISTORICAL_IDS:
        assert statuses.get(course_id) != "satisfied", course_id
    # Scope alone must not create makeup for the future entries either.
    assert all(statuses.get(course_id) is None for course_id in FUTURE_IDS)

    assert body["provenance"]["course_data"] == CASE_A_DEMO_SCOPE_LABEL
    assert body["provenance"]["is_full_semester"] is False
    assert all(offering["data_source"] == "real" for offering in body["course_offerings"])
    assert "mock" not in response.text.lower()


def test_historical_decisions_discharge_scope_but_not_recognition(tmp_path: Path) -> None:
    """Scope and recognition stay separate: deciding the range changes no status.

    The same transcript-shaped completed records are projected twice - once with the
    three historical decisions, once without them - and the *recognition* outcome for
    the three courses must be identical. Only the scope blocking differs.
    """

    from dataclasses import replace

    from app.curriculum.case import CurriculumCaseProvider
    from app.curriculum.errors import CurriculumNormalizationError

    case = load_curriculum_case(_write_case(tmp_path))
    with_historical = case
    future_only = replace(
        case,
        confirmed_scope_decisions=tuple(
            decision for decision in case.confirmed_scope_decisions
            if decision.decision == "future"
        ),
    )

    with_tasks = CurriculumCaseProvider(with_historical).get_makeup_tasks()
    with_statuses = {task.course_id: task.status.value for task in with_tasks}
    for course_id in HISTORICAL_IDS:
        assert with_statuses.get(course_id) != "satisfied", course_id

    # Without the historical decisions the scope cannot be confirmed -> fail closed.
    with pytest.raises(CurriculumNormalizationError):
        CurriculumCaseProvider(future_only).get_makeup_tasks()


def test_demo_runtime_gate_rejects_an_unapproved_decision_set(tmp_path: Path) -> None:
    """⛔ The compatibility window must not accept invented decisions."""

    import json

    payload = _scoped_case_payload()
    payload["confirmed_scope_decisions"].append({
        "target_version_id": "case-a-new",
        "target_source_record": "table:2!row:999",
        "target_course_id": "DEMO-INVENTED",
        "decision": "historical",
        "evidence": "case-owner-confirmed://case-a/range-term-scope",
    })
    path = tmp_path / "invented.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    environment = {
        "APP_CASE_A_DEMO_ENABLED": "1",
        "APP_CASE_A_DEMO_CURRICULUM_CASE_PATH": str(path),
        "APP_CASE_A_DEMO_COURSE_DATA_SQLITE_PATH": str(tmp_path / "absent.sqlite3"),
        "APP_CASE_A_DEMO_SEMESTER": SEMESTER,
        "APP_CASE_A_DEMO_SOUTH_ACCEPTANCE_SHA256": "0" * 64,
        "APP_CASE_A_DEMO_SHENZHEN_ACCEPTANCE_SHA256": "1" * 64,
    }
    assert build_case_a_demo_runtime(environment) is None


def test_offerings_with_an_out_of_scope_semester_is_a_controlled_4xx(
    scoped_runtime: tuple[CaseADemoRuntime, bytes],
) -> None:
    """Regression: a semester the accepted scope does not cover must not 500."""

    runtime, _pdf = scoped_runtime
    app.dependency_overrides[get_case_a_demo_runtime] = lambda: runtime
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/case-a-demo/offerings", params={"semester": "1999-9"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "case_a_demo_semester_not_in_scope"
    assert detail["category"] == "semester_mismatch"
    # The provider's own validation is intact: it is the boundary that maps it.
    assert "Traceback" not in response.text
