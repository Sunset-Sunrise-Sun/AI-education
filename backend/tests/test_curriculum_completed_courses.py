"""Synthetic completed-course facts only; no private files or school policy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

from app.curriculum import (
    CompletedCourse,
    CourseIdStatus,
    CurriculumNormalizationError,
    normalize_completed_courses,
)


def _record(**overrides: object) -> dict[str, object]:
    return {
        "course_id": "DEMO-COURSE-01",
        "course_name": "DEMO Course A",
        "credit": 3,
        "semester": "DEMO-TERM-1",
        "passed": True,
        "course_type": "DEMO Required",
        "course_id_status": "已确认",
        "id_match_source": "DEMO-CATALOG-01",
        **overrides,
    }


def _course(**overrides: object) -> CompletedCourse:
    return CompletedCourse(
        **{
            **_record(),
            "source_id": "DEMO-TRANSCRIPT-01",
            "source_record": "row:1",
            **overrides,
        }
    )


def test_confirmed_facts_are_retained_without_public_course_conversion() -> None:
    result = normalize_completed_courses([_record()], source_id="DEMO-TRANSCRIPT-01")
    assert isinstance(result, tuple)
    assert len(result) == 1
    course = result[0]
    assert course.course_id == "DEMO-COURSE-01"
    assert course.course_name == "DEMO Course A"
    assert course.credit == 3.0 and isinstance(course.credit, float)
    assert course.semester == "DEMO-TERM-1"
    assert course.passed is True
    assert course.course_type == "DEMO Required"
    assert course.course_id_status is CourseIdStatus.CONFIRMED
    assert course.id_match_source == "DEMO-CATALOG-01"
    assert course.source_id == "DEMO-TRANSCRIPT-01"
    assert course.source_record == "row:1"
    assert course.notes is None
    assert "recommended_semester" not in asdict(course)
    assert "status" not in asdict(course)


@pytest.mark.parametrize("status", ["confirmed", "已确认", CourseIdStatus.CONFIRMED])
def test_confirmed_status_forms_are_supported(status: object) -> None:
    assert _course(course_id_status=status).course_id_status is CourseIdStatus.CONFIRMED


@pytest.mark.parametrize("status", ["pending", "待确认", CourseIdStatus.PENDING])
@pytest.mark.parametrize("course_id", [None, "", " \t "])
def test_pending_identity_is_explicit_and_never_guessed(status: object, course_id: object) -> None:
    result = normalize_completed_courses(
        [_record(course_id=course_id, course_id_status=status, id_match_source=None)],
        source_id="DEMO-TRANSCRIPT-01",
    )
    assert result[0].course_id is None
    assert result[0].course_id_status is CourseIdStatus.PENDING
    assert result[0].id_match_source is None


def test_pending_identity_can_retain_a_match_note_source() -> None:
    course = _course(course_id=None, course_id_status="pending", id_match_source="DEMO-REVIEW-01")
    assert course.id_match_source == "DEMO-REVIEW-01"


def test_repeated_attempts_and_records_keep_their_order() -> None:
    first = _record(passed=False, semester="DEMO-TERM-1")
    retake = _record(passed=True, semester="DEMO-TERM-2")
    result = normalize_completed_courses([first, retake, retake], source_id="DEMO-TRANSCRIPT-01")
    assert [(course.semester, course.passed) for course in result] == [
        ("DEMO-TERM-1", False), ("DEMO-TERM-2", True), ("DEMO-TERM-2", True)
    ]
    assert [course.source_record for course in result] == ["row:1", "row:2", "row:3"]


def test_explicit_source_record_and_notes_are_preserved() -> None:
    course = normalize_completed_courses(
        [_record(source_record="DEMO-SHEET!row:7", notes="DEMO manual review note")],
        source_id="DEMO-TRANSCRIPT-01",
    )[0]
    assert course.source_record == "DEMO-SHEET!row:7"
    assert course.notes == "DEMO manual review note"


def test_semester_is_not_parsed_or_rewritten_as_a_recommended_semester() -> None:
    semester = "  DEMO academic semester text  "
    assert _course(semester=semester).semester == semester


@pytest.mark.parametrize("records", [[], ()])
def test_empty_input_is_valid_with_an_explicit_source(records: object) -> None:
    assert normalize_completed_courses(records, source_id="DEMO-TRANSCRIPT-01") == ()


@pytest.mark.parametrize("credit", [0, 0.0, 2.5])
def test_finite_nonnegative_credits_are_valid(credit: object) -> None:
    assert _course(credit=credit).credit == float(credit)


@pytest.mark.parametrize("source_id", [None, "", " \t", 1, True])
def test_source_is_validated_even_for_empty_records(source_id: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="source_id"):
        normalize_completed_courses([], source_id=source_id)


@pytest.mark.parametrize("records", [None, {}, "DEMO", b"DEMO", iter([]), 1])
def test_invalid_record_container_is_rejected(records: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="records"):
        normalize_completed_courses(records, source_id="DEMO-TRANSCRIPT-01")


def test_invalid_row_fails_the_entire_operation_without_values_in_error() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        normalize_completed_courses([_record(), "DEMO-PRIVATE-ROW"], source_id="DEMO-TRANSCRIPT-01")
    assert "row 2" in str(excinfo.value)
    assert "DEMO-PRIVATE-ROW" not in str(excinfo.value)


@pytest.mark.parametrize("field", list(_record()))
def test_each_minimum_input_field_is_required(field: str) -> None:
    record = _record()
    del record[field]
    with pytest.raises(CurriculumNormalizationError, match=f"row 1: missing field {field}"):
        normalize_completed_courses([record], source_id="DEMO-TRANSCRIPT-01")


@pytest.mark.parametrize("key", ["student_id", "student_name", "cookie", "source_id", "DEMO-PRIVATE-KEY"])
def test_unknown_or_personal_fields_are_rejected_without_echoing_them(key: str) -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        normalize_completed_courses(
            [_record(**{key: "DEMO-PRIVATE-VALUE"})], source_id="DEMO-TRANSCRIPT-01"
        )
    assert str(excinfo.value) == "row 1: unexpected record field"
    assert key not in str(excinfo.value)
    assert "DEMO-PRIVATE-VALUE" not in str(excinfo.value)


@pytest.mark.parametrize("field", ["course_name", "semester", "source_record"])
@pytest.mark.parametrize("value", [None, "", " \t", 1, [], {}])
def test_required_text_fields_reject_missing_or_wrong_types(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _course(**{field: value})


@pytest.mark.parametrize("field", ["course_id", "course_type", "id_match_source", "notes"])
@pytest.mark.parametrize("value", [1, True, [], {}])
def test_text_fields_cannot_hide_mutable_or_coerced_values(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _course(**{field: value})


@pytest.mark.parametrize("passed", [1, 0, "true", "是", None])
def test_passed_requires_an_actual_boolean(passed: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="passed"):
        _course(passed=passed)


@pytest.mark.parametrize("credit", [True, False, -1, float("inf"), float("-inf"), float("nan"), "3", "DEMO-PRIVATE-CREDIT", None, [], {}, 10**400])
def test_invalid_credit_is_rejected_without_coercion_or_nonfinite_values(credit: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="credit") as excinfo:
        _course(credit=credit)
    assert "DEMO-PRIVATE-CREDIT" not in str(excinfo.value)


@pytest.mark.parametrize("field", ["course_id", "id_match_source"])
@pytest.mark.parametrize("value", [None, "", " \t"])
def test_confirmed_identity_requires_both_id_and_source(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _course(**{field: value})


def test_pending_nonempty_id_is_rejected_instead_of_dropped() -> None:
    with pytest.raises(CurriculumNormalizationError, match="course_id") as excinfo:
        _course(course_id="DEMO-UNCONFIRMED-ID", course_id_status="待确认")
    assert "DEMO-UNCONFIRMED-ID" not in str(excinfo.value)


@pytest.mark.parametrize("status", ["satisfied", "possibly_equivalent", "DEMO-PRIVATE-STATUS", None, 1, {}])
def test_unknown_identity_status_is_not_treated_as_recognition(status: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="course_id_status") as excinfo:
        _course(course_id_status=status)
    assert "DEMO-PRIVATE-STATUS" not in str(excinfo.value)


def test_each_course_field_is_immutable() -> None:
    course = _course()
    for field in fields(CompletedCourse):
        with pytest.raises(FrozenInstanceError):
            setattr(course, field.name, None)


def test_input_changes_do_not_change_normalized_facts() -> None:
    record = _record()
    records = [record]
    result = normalize_completed_courses(records, source_id="DEMO-TRANSCRIPT-01")
    record["course_name"] = "DEMO Changed"
    record["passed"] = False
    records.clear()
    assert len(result) == 1
    assert result[0].course_name == "DEMO Course A"
    assert result[0].passed is True


def test_normalizer_reports_the_invalid_row_without_any_raw_values() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        normalize_completed_courses(
            [_record(), _record(semester="", notes="DEMO-PRIVATE-NOTE", course_name="DEMO-PRIVATE-NAME")],
            source_id="DEMO-PRIVATE-SOURCE",
        )
    assert str(excinfo.value) == "row 2: semester: expected a nonempty string"
    assert "DEMO-PRIVATE" not in str(excinfo.value)
