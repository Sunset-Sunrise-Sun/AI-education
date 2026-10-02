"""Synthetic curriculum requirements only; no private documents or policies."""

from dataclasses import FrozenInstanceError, fields

import pytest

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import (
    CurriculumCourse,
    CurriculumGroup,
    CurriculumVersion,
    RequirementKind,
    normalize_curriculum_version,
)


def _course_record(**overrides: object) -> dict[str, object]:
    return {
        "course_id": "DEMO-COURSE-01",
        "course_name": "DEMO Course A",
        "credit": 3,
        "requirement": "required",
        "source_record": "DEMO-TABLE!row:1",
        **overrides,
    }


def _group_record(**overrides: object) -> dict[str, object]:
    return {
        "group_id": "DEMO-GROUP-01",
        "name": "DEMO Elective Group",
        "minimum_credit": 6,
        "source_record": "DEMO-GROUP-TABLE!row:1",
        **overrides,
    }


def _course(**overrides: object) -> CurriculumCourse:
    return CurriculumCourse(**_course_record(**overrides))


def _group(**overrides: object) -> CurriculumGroup:
    return CurriculumGroup(**_group_record(**overrides))


def _version(**overrides: object) -> CurriculumVersion:
    return CurriculumVersion(**{
        "version_id": "DEMO-VERSION-01",
        "major": "DEMO Major",
        "cohort": "DEMO Cohort",
        "source_id": "DEMO-SOURCE-01",
        "courses": (_course(),),
        **overrides,
    })


def _normalize(**overrides: object) -> CurriculumVersion:
    return normalize_curriculum_version(**{
        "version_id": "DEMO-VERSION-01",
        "major": "DEMO Major",
        "cohort": "DEMO Cohort",
        "source_id": "DEMO-SOURCE-01",
        "course_records": [_course_record()],
        **overrides,
    })


def test_structured_version_retains_source_and_requirement_context() -> None:
    version = _normalize(
        course_records=[_course_record(group_id="DEMO-GROUP-01", requirement="elective")],
        group_records=[_group_record()],
    )
    assert version.version_id == "DEMO-VERSION-01"
    assert version.major == "DEMO Major"
    assert version.cohort == "DEMO Cohort"
    assert version.source_id == "DEMO-SOURCE-01"
    assert version.complete is False and version.completeness_evidence is None
    assert version.courses[0].requirement is RequirementKind.ELECTIVE
    assert version.courses[0].group_id == version.groups[0].group_id
    assert version.courses[0].source_record == "DEMO-TABLE!row:1"
    assert version.groups[0].minimum_credit == 6.0
    assert isinstance(version.courses, tuple) and isinstance(version.groups, tuple)


@pytest.mark.parametrize("kind", list(RequirementKind))
def test_all_explicit_requirement_kinds_are_supported(kind: RequirementKind) -> None:
    assert _course(requirement=kind).requirement is kind
    assert _course(requirement=kind.value).requirement is kind


def test_course_type_does_not_determine_requirement() -> None:
    course = _course(requirement="unknown", course_type="DEMO Required-looking Text")
    assert course.requirement is RequirementKind.UNKNOWN


def test_unknown_and_explicitly_absent_prerequisites_remain_distinct() -> None:
    assert _course().prerequisites is None
    assert _course(prerequisites=None).prerequisites is None
    assert _course(prerequisites=()).prerequisites == ()
    assert _course(prerequisites=[]).prerequisites == ()


def test_prerequisite_order_is_retained_without_inference() -> None:
    assert _course(prerequisites=["DEMO-PREREQ-02", "DEMO-PREREQ-01"]).prerequisites == (
        "DEMO-PREREQ-02", "DEMO-PREREQ-01"
    )


def test_term_text_never_becomes_a_semester_index_or_deadline() -> None:
    course = _course(recommended_term_text="DEMO year 2 semester 1")
    assert course.recommended_term_text == "DEMO year 2 semester 1"
    assert course.recommended_semester is None
    assert course.deadline_semester is None


def test_explicit_positive_semester_indices_are_retained() -> None:
    course = _course(recommended_semester=1, deadline_semester=5)
    assert course.recommended_semester == 1 and course.deadline_semester == 5


@pytest.mark.parametrize("field", ["course_type", "group_id", "recommended_term_text"])
def test_blank_optional_course_text_is_normalized_to_unknown(field: str) -> None:
    assert getattr(_course(**{field: " \t"}), field) is None


def test_unknown_group_minimum_is_not_zero() -> None:
    assert _group(minimum_credit=None).minimum_credit is None
    assert _group(minimum_credit=0).minimum_credit == 0.0


def test_same_course_id_in_multiple_source_entries_is_preserved() -> None:
    version = _normalize(course_records=[
        _course_record(source_record="DEMO-TABLE!row:1", requirement="required"),
        _course_record(source_record="DEMO-TABLE!row:2", requirement="elective"),
    ])
    assert len(version.courses) == 2
    assert version.courses[0].course_id == version.courses[1].course_id
    assert [entry.requirement for entry in version.courses] == [
        RequirementKind.REQUIRED, RequirementKind.ELECTIVE
    ]


def test_empty_courses_are_allowed_but_do_not_prove_completeness() -> None:
    version = _normalize(course_records=[])
    assert version.courses == ()
    assert version.complete is False


def test_complete_version_requires_explicit_evidence_not_counts() -> None:
    with pytest.raises(CurriculumNormalizationError, match="completeness_evidence"):
        _normalize(complete=True)
    version = _normalize(complete=True, completeness_evidence="DEMO Full-source checklist")
    assert version.complete is True
    assert version.completeness_evidence == "DEMO Full-source checklist"


def test_evidence_does_not_implicitly_change_completeness() -> None:
    version = _normalize(completeness_evidence="DEMO Partial-source note")
    assert version.complete is False


@pytest.mark.parametrize("number", [0, 0.0, 3.5])
def test_valid_numeric_credit_and_group_minimum(number: object) -> None:
    assert _course(credit=number).credit == float(number)
    assert _group(minimum_credit=number).minimum_credit == float(number)


@pytest.mark.parametrize("value", [True, False, -1, float("inf"), float("-inf"), float("nan"), "3", {}, [], 10**400])
def test_invalid_numeric_values_are_rejected_on_direct_construction(value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="credit"):
        _course(credit=value)
    with pytest.raises(CurriculumNormalizationError, match="minimum_credit"):
        _group(minimum_credit=value)


@pytest.mark.parametrize("field", ["recommended_semester", "deadline_semester"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1", "DEMO-TERM", {}, []])
def test_semester_indices_reject_conversion_and_invalid_types(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _course(**{field: value})


@pytest.mark.parametrize("field", ["course_id", "course_name", "source_record"])
@pytest.mark.parametrize("value", [None, "", " \t", 1, {}, []])
def test_course_required_strings_are_validated(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _course(**{field: value})


@pytest.mark.parametrize("field", ["group_id", "name", "source_record"])
@pytest.mark.parametrize("value", [None, "", " \t", 1])
def test_group_required_strings_are_validated(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _group(**{field: value})


@pytest.mark.parametrize("field", ["version_id", "major", "cohort", "source_id"])
@pytest.mark.parametrize("value", [None, "", " \t", 1])
def test_version_metadata_is_validated_before_records(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _normalize(**{field: value, "course_records": ["DEMO-PRIVATE-ROW"]})


@pytest.mark.parametrize("field", ["course_type", "group_id", "recommended_term_text"])
@pytest.mark.parametrize("value", [1, True, {}, []])
def test_optional_text_fields_cannot_hold_mutable_values(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _course(**{field: value})


@pytest.mark.parametrize("kind", [None, "DEMO-PRIVATE-KIND", "必修", {}, True])
def test_unknown_requirement_labels_are_not_guessed(kind: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="requirement") as excinfo:
        _course(requirement=kind)
    assert "DEMO-PRIVATE-KIND" not in str(excinfo.value)


@pytest.mark.parametrize("prerequisites", ["DEMO-PREREQ", {}, iter([]), [None], [""], [" \t"], [1], [{}], ["DEMO-01", "DEMO-01"]])
def test_invalid_prerequisites_are_rejected_without_inference(prerequisites: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="prerequisites"):
        _course(prerequisites=prerequisites)


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_completeness_requires_an_actual_boolean(value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="complete"):
        _version(complete=value)


@pytest.mark.parametrize("value", [None, "", " \t"])
def test_complete_version_rejects_missing_evidence(value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="completeness_evidence"):
        _version(complete=True, completeness_evidence=value)


@pytest.mark.parametrize("value", [1, [], {}])
def test_evidence_must_be_optional_text(value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="completeness_evidence"):
        _version(completeness_evidence=value)


def test_duplicate_course_source_record_is_rejected_without_echoing_it() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _normalize(course_records=[
            _course_record(source_record="DEMO-PRIVATE-REFERENCE"),
            _course_record(course_id="DEMO-COURSE-02", source_record="DEMO-PRIVATE-REFERENCE"),
        ])
    assert str(excinfo.value) == "courses row 2: source_record: duplicate reference"
    assert "DEMO-PRIVATE-REFERENCE" not in str(excinfo.value)


def test_duplicate_group_id_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError, match="groups row 2: group_id"):
        _normalize(group_records=[_group_record(), _group_record(source_record="DEMO-GROUP!row:2")])


def test_unknown_group_reference_is_rejected_without_dropping_the_course() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _normalize(course_records=[_course_record(group_id="DEMO-PRIVATE-GROUP")])
    assert str(excinfo.value) == "courses row 1: group_id: unknown reference"
    assert "DEMO-PRIVATE-GROUP" not in str(excinfo.value)


@pytest.mark.parametrize("field", list(_course_record()))
def test_minimum_course_record_fields_are_required(field: str) -> None:
    record = _course_record()
    del record[field]
    with pytest.raises(CurriculumNormalizationError, match=f"courses row 1: missing field {field}"):
        _normalize(course_records=[record])


@pytest.mark.parametrize("field", list(_group_record()))
def test_all_group_record_fields_are_required_even_nullable_minimum(field: str) -> None:
    record = _group_record()
    del record[field]
    with pytest.raises(CurriculumNormalizationError, match=f"groups row 1: missing field {field}"):
        _normalize(group_records=[record])


@pytest.mark.parametrize("key", ["student_id", "cookie", "DEMO-PRIVATE-KEY"])
@pytest.mark.parametrize("field", ["course_records", "group_records"])
def test_extra_record_fields_are_rejected_without_echoing_key_or_value(key: str, field: str) -> None:
    record = _course_record() if field == "course_records" else _group_record()
    record[key] = "DEMO-PRIVATE-VALUE"
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _normalize(**{field: [record]})
    assert str(excinfo.value).endswith("row 1: unexpected record field")
    assert key not in str(excinfo.value) and "DEMO-PRIVATE-VALUE" not in str(excinfo.value)


@pytest.mark.parametrize("field", ["course_records", "group_records"])
@pytest.mark.parametrize("value", [None, {}, "DEMO-PRIVATE-TEXT", b"DEMO", iter([])])
def test_invalid_record_sequences_are_rejected(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError):
        _normalize(**{field: value})


@pytest.mark.parametrize("field", ["course_records", "group_records"])
def test_invalid_record_row_reports_only_its_position(field: str) -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _normalize(**{field: ["DEMO-PRIVATE-ROW"]})
    assert str(excinfo.value).endswith("row 1: expected a mapping")
    assert "DEMO-PRIVATE-ROW" not in str(excinfo.value)


@pytest.mark.parametrize("field", ["courses", "groups"])
@pytest.mark.parametrize("value", [None, {}, "DEMO-PRIVATE-TEXT", [object()]])
def test_direct_version_construction_cannot_bypass_child_type_validation(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError):
        _version(**{field: value})


def test_all_model_fields_are_immutable() -> None:
    for model in (_course(), _group(), _version()):
        for field in fields(model):
            with pytest.raises(FrozenInstanceError):
                setattr(model, field.name, None)


def test_direct_construction_freezes_nested_input_containers() -> None:
    prereqs = ["DEMO-PREREQ-01"]
    course = _course(prerequisites=prereqs, group_id="DEMO-GROUP-01")
    courses, groups = [course], [_group()]
    version = _version(courses=courses, groups=groups)
    prereqs.append("DEMO-PREREQ-02")
    courses.clear()
    groups.clear()
    assert version.courses == (course,)
    assert len(version.groups) == 1
    assert version.courses[0].prerequisites == ("DEMO-PREREQ-01",)


def test_normalized_version_is_isolated_from_input_mapping_changes() -> None:
    record, group = _course_record(group_id="DEMO-GROUP-01"), _group_record()
    version = _normalize(course_records=[record], group_records=[group])
    record["course_name"] = "DEMO Changed"
    group["minimum_credit"] = 99
    assert version.courses[0].course_name == "DEMO Course A"
    assert version.groups[0].minimum_credit == 6.0


def test_invalid_later_record_fails_the_whole_import_with_private_values_hidden() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _normalize(course_records=[
            _course_record(),
            _course_record(course_id="DEMO-PRIVATE-ID", source_record="DEMO-PRIVATE-ROW", credit="DEMO-PRIVATE-CREDIT"),
        ])
    assert str(excinfo.value) == "courses row 2: credit: expected a finite nonnegative number"
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_explicit_summary_metadata_is_preserved_by_constructor_and_normalizer() -> None:
    for version in (
        _version(total_credit=100, practice_credit=12.5, study_years=3),
        _normalize(total_credit=100, practice_credit=12.5, study_years=3),
    ):
        assert version.total_credit == 100.0
        assert version.practice_credit == 12.5
        assert version.study_years == 3


def test_summary_metadata_can_remain_unknown_and_does_not_imply_full_courses() -> None:
    unknown = _normalize(course_records=[])
    assert unknown.total_credit is None
    assert unknown.practice_credit is None
    assert unknown.study_years is None
    known = _normalize(course_records=[], total_credit=100, practice_credit=12.5, study_years=3)
    assert known.courses == () and known.complete is False


@pytest.mark.parametrize("field", ["total_credit", "practice_credit"])
@pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan"), "100"])
def test_summary_credits_reject_nonfinite_or_coerced_values(field: str, value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match=field):
        _version(**{field: value})
    with pytest.raises(CurriculumNormalizationError, match=field):
        _normalize(**{field: value})


@pytest.mark.parametrize("value", [True, 0, -1, 3.0, "3"])
def test_study_years_requires_an_explicit_positive_integer(value: object) -> None:
    with pytest.raises(CurriculumNormalizationError, match="study_years"):
        _version(study_years=value)
    with pytest.raises(CurriculumNormalizationError, match="study_years"):
        _normalize(study_years=value)


def test_study_years_never_sets_course_deadlines_or_replaces_supplied_summary() -> None:
    version = _normalize(
        study_years=3, total_credit=100,
        course_records=[_course_record(group_id="DEMO-GROUP-01", requirement="elective")],
        group_records=[_group_record(minimum_credit=6)],
    )
    assert version.courses[0].deadline_semester is None
    assert version.courses[0].recommended_semester is None
    assert version.total_credit == 100.0
