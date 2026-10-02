"""Synthetic source facts for internal academic analysis, with no private IO."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.curriculum.academic import (
    AcademicAnalysis,
    AcademicIssue,
    PriorityPolicy,
    analyze_academic_path,
)
from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumResultProvider,
    build_curriculum_diff,
)
from app.curriculum.requirements import CurriculumCourse, CurriculumGroup, CurriculumVersion, RequirementKind
from app.models.contracts import MakeupStatus


def _target(course_id: str = "DEMO-A", **overrides: object) -> CurriculumCourse:
    return CurriculumCourse(**{
        "course_id": course_id, "course_name": f"DEMO Course {course_id}", "credit": 3,
        "requirement": RequirementKind.REQUIRED, "source_record": f"DEMO-CATALOG#{course_id}",
        "prerequisites": (), "deadline_semester": 3, **overrides,
    })


def _version(courses: tuple[CurriculumCourse, ...], **overrides: object) -> CurriculumVersion:
    return CurriculumVersion(**{
        "version_id": "DEMO-NEW", "major": "DEMO Major", "cohort": "DEMO Cohort",
        "source_id": "DEMO-CURRICULUM-SOURCE", "courses": courses,
        "complete": True, "completeness_evidence": "DEMO-COMPLETE-CHECK", **overrides,
    })


def _attempt(course_id: str, **overrides: object) -> CompletedCourse:
    return CompletedCourse(**{
        "course_id": course_id, "course_name": f"DEMO Course {course_id}", "credit": 3,
        "semester": "DEMO-TERM", "passed": True, "course_type": "DEMO Context",
        "course_id_status": CourseIdStatus.CONFIRMED, "id_match_source": "DEMO-ID-FACT",
        "source_id": "DEMO-COMPLETED-SOURCE", "source_record": f"DEMO-SHEET#{course_id}",
        **overrides,
    })


def _diff(
    courses: tuple[CurriculumCourse, ...], *, satisfied: tuple[str, ...] = (),
    missing_ids: tuple[str, ...] | None = None, **overrides: object,
):
    completed = tuple(_attempt(course_id) for course_id in satisfied)
    granted = tuple(ConfirmedRecognition(
        "DEMO-NEW", course_id, attempt.source_id, attempt.source_record, 3, "DEMO-RECOGNITION",
    ) for course_id, attempt in zip(satisfied, completed))
    if missing_ids is None:
        missing_ids = tuple(course.course_id for course in courses
                            if course.course_id not in satisfied and course.requirement is RequirementKind.REQUIRED)
    missing = tuple(ConfirmedMissingRequirement(
        "DEMO-NEW", course_id, "DEMO-COMPLETED-SOURCE", "DEMO-MISSING-DECISION",
    ) for course_id in missing_ids)
    return build_curriculum_diff(**{
        "old": _version(()),
        "new": overrides["new"] if "new" in overrides else _version(courses),
        "completed": completed,
        "recognitions": granted, "missing_requirements": missing,
        "completed_complete": True, "completed_completeness_evidence": "DEMO-COMPLETED-COMPLETE",
        "completed_source_id": "DEMO-COMPLETED-SOURCE", **overrides,
    })


def _policy(**overrides: object) -> PriorityPolicy:
    return PriorityPolicy(**{
        "target_version_id": "DEMO-NEW", "evidence": "DEMO-CONFIRMED-PRIORITY-POLICY", **overrides,
    })


def _codes(result: AcademicAnalysis) -> set[str]:
    return {issue.code for issue in result.issues}


def test_default_policy_does_not_invent_a_final_priority_order() -> None:
    result = analyze_academic_path(_diff((_target("DEMO-B", prerequisites=("DEMO-A",)), _target())))
    assert result.dependency_order == ("DEMO-A", "DEMO-B")
    assert result.priority_order is None
    assert "priority_unconfirmed" in _codes(result)


def test_explicit_deadline_policy_orders_available_nodes_without_violating_edges() -> None:
    courses = (
        _target("DEMO-D", prerequisites=("DEMO-B", "DEMO-C"), deadline_semester=1),
        _target("DEMO-C", prerequisites=("DEMO-A",), deadline_semester=7),
        _target("DEMO-B", prerequisites=("DEMO-A",), deadline_semester=3),
        _target("DEMO-A", deadline_semester=9),
        _target("DEMO-E", deadline_semester=2),
    )
    result = analyze_academic_path(_diff(courses), priority_policy=_policy())
    assert result.priority_order == ("DEMO-E", "DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D")
    positions = {course_id: index for index, course_id in enumerate(result.dependency_order)}
    assert positions["DEMO-A"] < positions["DEMO-B"] < positions["DEMO-D"]
    assert positions["DEMO-A"] < positions["DEMO-C"] < positions["DEMO-D"]


def test_satisfied_predecessor_is_not_scheduled_as_an_additional_task() -> None:
    courses = (_target("DEMO-B", prerequisites=("DEMO-A",)), _target("DEMO-A", deadline_semester=None))
    diff = _diff(courses, satisfied=("DEMO-A",))
    assert diff.matches[1].status is MakeupStatus.SATISFIED
    result = analyze_academic_path(diff, priority_policy=_policy())
    assert result.dependency_order == ("DEMO-A", "DEMO-B")
    assert result.priority_order == ("DEMO-B",)
    assert "deadline_unknown" not in _codes(result)


def test_unknown_prerequisites_are_not_equivalent_to_an_empty_set() -> None:
    target = _target(prerequisites=None)
    result = analyze_academic_path(_diff((target,)), priority_policy=_policy())
    assert result.dependency_order is None and result.priority_order is None
    assert "prerequisites_unknown" in _codes(result)
    assert target.prerequisites is None
    known = analyze_academic_path(_diff((_target(prerequisites=()),)), priority_policy=_policy())
    assert known.dependency_order == known.priority_order == ("DEMO-A",)


def test_missing_deadline_is_not_inferred_from_recommended_term_or_semester() -> None:
    target = _target(deadline_semester=None, recommended_semester=2, recommended_term_text="DEMO-TERM-1~DEMO-TERM-2")
    result = analyze_academic_path(_diff((target,)), priority_policy=_policy())
    assert result.dependency_order == ("DEMO-A",) and result.priority_order is None
    issue = next(issue for issue in result.issues if issue.code == "deadline_unknown")
    assert issue.evidence and issue.course_id == "DEMO-A"
    assert target.deadline_semester is None and target.recommended_term_text == "DEMO-TERM-1~DEMO-TERM-2"


def test_cycle_cannot_be_fixed_by_deleting_or_guessing_prerequisite_edges() -> None:
    courses = (_target("DEMO-A", prerequisites=("DEMO-B",)), _target("DEMO-B", prerequisites=("DEMO-A",)))
    result = analyze_academic_path(_diff(courses), priority_policy=_policy())
    assert result.dependency_order is None and result.priority_order is None
    assert "dependency_cycle" in _codes(result)
    assert courses[0].prerequisites == ("DEMO-B",) and courses[1].prerequisites == ("DEMO-A",)


def test_external_prerequisite_remains_unknown_despite_a_passed_candidate() -> None:
    target = _target(prerequisites=("DEMO-EXTERNAL",))
    external = _attempt("DEMO-EXTERNAL", course_name=target.course_name)
    granted = ConfirmedRecognition("DEMO-NEW", target.course_id, external.source_id, external.source_record, 3, "DEMO-RECOGNITION")
    diff = _diff((target,), completed=(external,), recognitions=(granted,), missing_requirements=())
    assert diff.matches[0].status is MakeupStatus.SATISFIED
    result = analyze_academic_path(diff, priority_policy=_policy())
    assert "external_prerequisite_unresolved" in _codes(result)
    assert result.dependency_order is None and result.priority_order is None


def test_unconfirmed_internal_predecessor_does_not_get_a_final_priority() -> None:
    courses = (_target("DEMO-B", prerequisites=("DEMO-A",)), _target("DEMO-A"))
    result = analyze_academic_path(_diff(courses, missing_ids=("DEMO-B",)), priority_policy=_policy())
    assert result.dependency_order == ("DEMO-A", "DEMO-B")
    assert result.priority_order is None
    assert {"matching_unconfirmed", "prerequisite_match_unconfirmed"} <= _codes(result)


def test_possibly_equivalent_match_is_reported_with_evidence_not_scored() -> None:
    target = _target()
    named = _attempt("DEMO-OTHER", course_name=target.course_name)
    diff = _diff((target,), completed=(named,), missing_requirements=())
    assert diff.matches[0].status is MakeupStatus.POSSIBLY_EQUIVALENT
    result = analyze_academic_path(diff, priority_policy=_policy())
    issue = next(issue for issue in result.issues if issue.code == "matching_unconfirmed")
    assert issue.evidence == diff.matches[0].evidence
    assert result.priority_order is None


@pytest.mark.parametrize("minimum", [None, 6])
def test_group_quota_gap_prevents_final_priority_without_creating_fake_course(minimum: float | None) -> None:
    course = _target("DEMO-ELECTIVE", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP")
    group = CurriculumGroup("DEMO-GROUP", "DEMO Elective Pool", minimum, "DEMO-GROUP-SOURCE")
    version = _version((course,), groups=(group,))
    diff = _diff((course,), new=version)
    result = analyze_academic_path(diff, priority_policy=_policy())
    assert "group_requirement_unresolved" in _codes(result)
    assert result.priority_order is None
    assert result.dependency_order == ("DEMO-ELECTIVE",)
    assert all(issue.course_id != "DEMO-GROUP" for issue in result.issues)


def test_duplicate_course_contexts_do_not_get_a_dependency_order() -> None:
    courses = (_target(), _target(source_record="DEMO-CATALOG#other-context"))
    result = analyze_academic_path(_diff(courses), priority_policy=_policy())
    assert result.dependency_order is None and result.priority_order is None
    assert "duplicate_course_id" in _codes(result)


def test_partial_curriculum_does_not_get_a_final_academic_path() -> None:
    course = _target()
    diff = _diff((course,), new=_version((course,), complete=False, completeness_evidence=None))
    result = analyze_academic_path(diff, priority_policy=_policy())
    assert result.dependency_order is None and result.priority_order is None
    assert "curriculum_incomplete" in _codes(result)


def test_policy_is_scoped_to_a_target_version() -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        analyze_academic_path(_diff((_target(),)), priority_policy=_policy(target_version_id="DEMO-PRIVATE-OTHER"))
    assert "DEMO-PRIVATE-OTHER" not in str(excinfo.value)


def test_explicit_policy_can_keep_source_order_without_implicit_weights() -> None:
    courses = (_target("DEMO-A", deadline_semester=7), _target("DEMO-B", deadline_semester=1))
    result = analyze_academic_path(_diff(courses), priority_policy=_policy(deadline_first=False))
    assert result.priority_order == ("DEMO-A", "DEMO-B")


def test_academic_analysis_never_reorders_or_modifies_public_provider_tasks() -> None:
    courses = (_target("DEMO-A", deadline_semester=7), _target("DEMO-B", deadline_semester=1))
    diff = _diff(courses)
    provider = CurriculumResultProvider(diff)
    before = [task.model_dump(mode="json") for task in provider.get_makeup_tasks()]
    result = analyze_academic_path(diff, priority_policy=_policy())
    after = [task.model_dump(mode="json") for task in provider.get_makeup_tasks()]
    assert before == after and [task["course_id"] for task in after] == ["DEMO-A", "DEMO-B"]
    assert result.priority_order == ("DEMO-B", "DEMO-A")
    assert all("priority" not in task for task in after)


def test_verified_empty_curriculum_produces_only_explicit_empty_order() -> None:
    result = analyze_academic_path(_diff(()), priority_policy=_policy())
    assert result.dependency_order == result.priority_order == ()


def test_issue_and_analysis_snapshot_mutable_sequences_and_are_frozen() -> None:
    evidence = ["DEMO-SOURCE"]
    issue = AcademicIssue("DEMO-CODE", None, "DEMO message", evidence)
    items, dependency, priority = [issue], ["DEMO-A"], ["DEMO-A"]
    result = AcademicAnalysis(items, dependency, priority)
    evidence.clear()
    items.clear()
    dependency.clear()
    priority.clear()
    assert result.issues == (issue,) and issue.evidence == ("DEMO-SOURCE",)
    assert result.dependency_order == result.priority_order == ("DEMO-A",)
    with pytest.raises(FrozenInstanceError):
        result.priority_order = ()
    with pytest.raises(FrozenInstanceError):
        issue.message = "DEMO mutation"


def test_invalid_policy_cannot_coerce_confirmation_flags_or_empty_evidence() -> None:
    for kwargs in ({"evidence": ""}, {"deadline_first": 1}):
        with pytest.raises(CurriculumNormalizationError):
            _policy(**kwargs)
