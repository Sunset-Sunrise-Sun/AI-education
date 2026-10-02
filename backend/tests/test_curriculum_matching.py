"""Fictional cases that keep data matching separate from formal recognition."""

from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedElectiveSelection,
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CourseMatch,
    GroupGap,
    CurriculumResultProvider,
    build_curriculum_diff,
    project_courses,
    project_makeup_tasks,
)
from app.curriculum.requirements import (
    CurriculumCourse,
    CurriculumGroup,
    CurriculumVersion,
    RequirementKind,
)
from app.integration.ports import CurriculumProvider
from app.models.contracts import Course, MakeupStatus, MakeupTask


def _target(course_id: str = "DEMO-A", **overrides: object) -> CurriculumCourse:
    return CurriculumCourse(**{
        "course_id": course_id,
        "course_name": f"DEMO Course {course_id}",
        "credit": 3,
        "requirement": RequirementKind.REQUIRED,
        "source_record": f"DEMO-CATALOG#{course_id}",
        "prerequisites": (),
        **overrides,
    })


def _version(
    courses: tuple[CurriculumCourse, ...] = (), *, old: bool = False,
    complete: bool = True, groups: tuple[CurriculumGroup, ...] = (),
) -> CurriculumVersion:
    label = "OLD" if old else "NEW"
    return CurriculumVersion(
        version_id=f"DEMO-VERSION-{label}", major=f"DEMO Major {label}",
        cohort="DEMO Cohort", source_id=f"DEMO-SOURCE-{label}",
        courses=courses, groups=groups, complete=complete,
        completeness_evidence=f"DEMO-COMPLETE-{label}" if complete else None,
    )


def _attempt(
    course_id: str | None = "DEMO-A", *, row: int = 1, **overrides: object,
) -> CompletedCourse:
    return CompletedCourse(**{
        "course_id": course_id,
        "course_name": f"DEMO Course {course_id}",
        "credit": 3,
        "semester": "DEMO-ACTUAL-TERM",
        "passed": True,
        "course_type": "DEMO Context",
        "course_id_status": CourseIdStatus.PENDING if course_id is None else CourseIdStatus.CONFIRMED,
        "id_match_source": None if course_id is None else "DEMO-ID-EVIDENCE",
        "source_id": "DEMO-COMPLETED",
        "source_record": f"DEMO-SHEET!row:{row}",
        **overrides,
    })


def _recognition(
    target: CurriculumCourse, attempt: CompletedCourse, **overrides: object,
) -> ConfirmedRecognition:
    return ConfirmedRecognition(**{
        "target_version_id": "DEMO-VERSION-NEW",
        "target_course_id": target.course_id,
        "completed_source_id": attempt.source_id,
        "completed_source_record": attempt.source_record,
        "recognized_credit": target.credit,
        "evidence": "DEMO-EXPLICIT-RECOGNITION",
        **overrides,
    })


def _missing(target: CurriculumCourse, **overrides: object) -> ConfirmedMissingRequirement:
    return ConfirmedMissingRequirement(**{
        "target_version_id": "DEMO-VERSION-NEW", "target_course_id": target.course_id,
        "completed_source_id": "DEMO-COMPLETED",
        "evidence": "DEMO-EXPLICIT-MISSING-DECISION",
        **overrides,
    })


def _diff(
    targets: tuple[CurriculumCourse, ...], completed: tuple[CompletedCourse, ...] = (),
    **overrides: object,
):
    options = {
        "old": _version(old=True),
        "new": overrides["new"] if "new" in overrides else _version(targets),
        "completed": completed,
        "completed_source_id": "DEMO-COMPLETED",
        "completed_complete": True,
        "completed_completeness_evidence": "DEMO-COMPLETED-COMPLETE",
        **overrides,
    }
    return build_curriculum_diff(**options)


def test_four_statuses_require_explicit_decisions_not_merely_complete_data() -> None:
    accepted = _target("DEMO-A")
    missing = _target("DEMO-B")
    candidate = _target("DEMO-C", course_name="DEMO Similar Name")
    same_id = _target("DEMO-D")
    first = _attempt("DEMO-A")
    named = _attempt("DEMO-OTHER", row=2, course_name="  demo SIMILAR name  ")
    unchanged = _attempt("DEMO-D", row=3)
    diff = _diff(
        (accepted, missing, candidate, same_id), (first, named, unchanged),
        recognitions=(_recognition(accepted, first),), missing_requirements=(_missing(missing),),
    )
    assert [match.status for match in diff.matches] == [
        MakeupStatus.SATISFIED, MakeupStatus.REQUIRED,
        MakeupStatus.POSSIBLY_EQUIVALENT, MakeupStatus.MANUAL_CONFIRMATION,
    ]
    assert diff.matches[2].candidates == (named,)
    assert all(match.reason and match.evidence for match in diff.matches)
    tasks = project_makeup_tasks(diff)
    assert [task.status for task in tasks] == [match.status for match in diff.matches]
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/makeup_task.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for task in tasks:
        validator.validate(task.model_dump(mode="json"))


def test_complete_data_does_not_mean_school_rules_are_confirmed() -> None:
    targets = (_target(), _target("DEMO-B"))
    diff = _diff(targets, (_attempt(),))
    assert all(match.status is MakeupStatus.MANUAL_CONFIRMATION for match in diff.matches)


@pytest.mark.parametrize("name", ["DEMO Candidate", "  demo\tCANDIDATE ", "ＤＥＭＯ Candidate"])
def test_normalized_name_is_only_a_candidate(name: str) -> None:
    target = _target(course_name="DEMO Candidate")
    attempt = _attempt("DEMO-OTHER", course_name=name)
    match = _diff((target,), (attempt,)).matches[0]
    assert match.status is MakeupStatus.POSSIBLY_EQUIVALENT
    assert match.candidates == (attempt,)


def test_pending_course_id_is_not_filled_in_by_candidate_matching() -> None:
    target = _target(course_name="DEMO Candidate")
    attempt = _attempt(None, course_name="DEMO Candidate")
    match = _diff((target,), (attempt,)).matches[0]
    assert match.status is MakeupStatus.POSSIBLY_EQUIVALENT
    assert match.candidates[0].course_id is None
    assert attempt.course_id_status is CourseIdStatus.PENDING


def test_explicit_recognition_can_refer_to_pending_identity_without_mutating_it() -> None:
    target = _target()
    attempt = _attempt(None, course_name="DEMO Different Original Name")
    match = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt),)).matches[0]
    assert match.status is MakeupStatus.SATISFIED
    assert attempt.course_id is None


@pytest.mark.parametrize("passed,credit", [(False, 3), (True, 2)])
def test_failed_or_credit_mismatched_same_id_is_not_automatically_satisfied(passed: bool, credit: int) -> None:
    match = _diff((_target(),), (_attempt(passed=passed, credit=credit),)).matches[0]
    assert match.status is MakeupStatus.MANUAL_CONFIRMATION


def test_failed_same_name_cannot_be_a_passing_equivalence_candidate() -> None:
    target = _target(course_name="DEMO Candidate")
    attempt = _attempt("DEMO-OTHER", course_name="DEMO Candidate", passed=False)
    match = _diff((target,), (attempt,)).matches[0]
    assert match.status is MakeupStatus.MANUAL_CONFIRMATION
    assert match.candidates == ()


@pytest.mark.parametrize("complete_target,complete_completed", [(False, True), (True, False), (False, False)])
def test_missing_decision_does_not_override_partial_input(complete_target: bool, complete_completed: bool) -> None:
    target = _target()
    diff = _diff(
        (target,), new=_version((target,), complete=complete_target),
        completed_complete=complete_completed,
        completed_completeness_evidence="DEMO-COMPLETED-COMPLETE" if complete_completed else None,
        missing_requirements=(_missing(target),),
    )
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_unrelated_pending_passed_identity_blocks_a_definitive_missing_claim() -> None:
    target = _target()
    attempt = _attempt(None, course_name="DEMO Unknown Identity")
    diff = _diff((target,), (attempt,), missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_failed_unrelated_pending_record_is_not_a_passing_obstruction() -> None:
    target = _target()
    attempt = _attempt(None, course_name="DEMO Unknown Failed Identity", passed=False)
    diff = _diff((target,), (attempt,), missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.REQUIRED


def test_passing_candidate_prevents_an_explicit_missing_claim() -> None:
    target = _target(course_name="DEMO Candidate")
    attempt = _attempt("DEMO-OTHER", course_name="DEMO Candidate")
    diff = _diff((target,), (attempt,), missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION
    assert "冲突" in diff.matches[0].reason


def test_missing_decision_from_another_completed_source_cannot_be_reused() -> None:
    target = _target()
    foreign = _missing(target, completed_source_id="DEMO-FOREIGN-COMPLETED")
    diff = _diff((target,), missing_requirements=(foreign,))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_explicit_completed_scope_rejects_a_record_from_another_source() -> None:
    target = _target()
    foreign = _attempt("DEMO-OTHER", source_id="DEMO-FOREIGN-COMPLETED")
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _diff((target,), (foreign,), missing_requirements=(_missing(target),))
    assert "DEMO-FOREIGN-COMPLETED" not in str(excinfo.value)


@pytest.mark.parametrize("scope", ["DEMO-COMPLETED", None])
def test_mixed_completed_sources_do_not_silently_bind_to_the_first_source(scope: str | None) -> None:
    first = _attempt()
    foreign = _attempt("DEMO-OTHER", row=2, source_id="DEMO-FOREIGN-COMPLETED")
    with pytest.raises(CurriculumNormalizationError):
        _diff((_target(),), (first, foreign), completed_source_id=scope)


def test_unique_record_source_can_supply_scope_without_explicit_argument() -> None:
    target = _target("DEMO-NEW-TARGET")
    failed = _attempt("DEMO-OTHER", passed=False)
    diff = _diff((target,), (failed,), completed_source_id=None, missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.REQUIRED


def test_empty_completed_records_need_explicit_scope_for_a_missing_decision() -> None:
    target = _target()
    diff = _diff((target,), completed_source_id=None, missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


@pytest.mark.parametrize("source_override", [
    {"completed_source_id": "DEMO-WRONG-SOURCE"},
    {"completed_source_record": "DEMO-SHEET!row:999"},
])
def test_recognition_must_locate_the_correct_source_attempt(source_override: dict[str, str]) -> None:
    target, attempt = _target(), _attempt()
    decision = _recognition(target, attempt, **source_override)
    assert _diff((target,), (attempt,), recognitions=(decision,)).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


@pytest.mark.parametrize("decision_override", [
    {"target_version_id": "DEMO-WRONG-VERSION"}, {"target_course_id": "DEMO-WRONG-TARGET"},
])
def test_out_of_scope_recognition_is_rejected(decision_override: dict[str, str]) -> None:
    target, attempt = _target(), _attempt()
    with pytest.raises(CurriculumNormalizationError):
        _diff((target,), (attempt,), recognitions=(_recognition(target, attempt, **decision_override),))


def test_recognition_of_failed_attempt_is_not_accepted() -> None:
    target, attempt = _target(), _attempt(passed=False)
    diff = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_recognized_credits_are_not_summed_across_attempts() -> None:
    target = _target(credit=3)
    attempts = (_attempt(credit=2), _attempt(row=2, credit=2))
    decisions = tuple(_recognition(target, attempt, recognized_credit=2) for attempt in attempts)
    diff = _diff((target,), attempts, recognitions=decisions)
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_insufficient_recognized_credit_remains_manual() -> None:
    target, attempt = _target(), _attempt()
    diff = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt, recognized_credit=2),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_explicitly_selected_passing_retake_keeps_both_attempts() -> None:
    target = _target()
    failed, passed = _attempt(passed=False), _attempt(row=2, semester="DEMO-RETAKE-TERM")
    diff = _diff((target,), (failed, passed), recognitions=(_recognition(target, passed),))
    assert diff.matches[0].status is MakeupStatus.SATISFIED
    assert diff.matches[0].candidates == (failed, passed)


def test_one_attempt_cannot_be_double_counted_for_multiple_targets() -> None:
    targets = (_target("DEMO-A"), _target("DEMO-B"))
    attempt = _attempt()
    decisions = tuple(_recognition(target, attempt) for target in targets)
    diff = _diff(targets, (attempt,), recognitions=decisions)
    assert all(match.status is MakeupStatus.MANUAL_CONFIRMATION for match in diff.matches)


def test_duplicate_recognition_is_manual_even_if_both_rows_are_identical() -> None:
    target, attempt = _target(), _attempt()
    decision = _recognition(target, attempt)
    diff = _diff((target,), (attempt,), recognitions=(decision, decision))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_duplicate_source_reference_is_not_a_unique_attempt() -> None:
    target, attempt = _target(), _attempt()
    another = replace(attempt, semester="DEMO-OTHER-TERM")
    diff = _diff((target,), (attempt, another), recognitions=(_recognition(target, attempt),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_conflicting_recognition_and_missing_decisions_remain_manual() -> None:
    target, attempt = _target(), _attempt()
    diff = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt),), missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_duplicate_target_id_keeps_both_entries_and_blocks_projection() -> None:
    targets = (_target(), _target(course_name="DEMO Different Context", source_record="DEMO-CATALOG#row:2"))
    attempt = _attempt()
    diff = _diff(targets, (attempt,), recognitions=(_recognition(targets[0], attempt),))
    assert len(diff.matches) == 2
    assert all(match.status is MakeupStatus.MANUAL_CONFIRMATION for match in diff.matches)
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)


def _elective_case(minimum_credit: float | None):
    targets = (
        _target("DEMO-E1", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP"),
        _target("DEMO-E2", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP"),
    )
    group = CurriculumGroup(group_id="DEMO-GROUP", name="DEMO Elective Pool", minimum_credit=minimum_credit, source_record="DEMO-GROUP-EVIDENCE")
    return targets, _version(targets, groups=(group,))


@pytest.mark.parametrize("minimum", [None, 6])
def test_unknown_or_unmet_group_quota_stays_internal_and_blocks_projection(minimum: float | None) -> None:
    targets, version = _elective_case(minimum)
    attempt = _attempt("DEMO-E1")
    diff = _diff(targets, (attempt,), new=version, recognitions=(_recognition(targets[0], attempt),))
    assert all(match.status is not MakeupStatus.REQUIRED for match in diff.matches)
    assert len(diff.group_gaps) == 1
    assert diff.group_gaps[0].group_id == "DEMO-GROUP"
    assert diff.group_gaps[0].remaining_credit == (None if minimum is None else 3)
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)


def test_only_confirmed_satisfaction_counts_toward_group_credit() -> None:
    targets, version = _elective_case(3)
    known = _attempt("DEMO-E1")
    pending = _attempt(None, row=2, course_name=targets[1].course_name)
    diff = _diff(targets, (known, pending), new=version)
    assert diff.group_gaps[0].remaining_credit == 3
    approved = _diff(targets, (known, pending), new=version, recognitions=(_recognition(targets[0], known),))
    assert approved.group_gaps == ()
    tasks = project_makeup_tasks(approved)
    assert all(task.status is not MakeupStatus.REQUIRED for task in tasks)
    assert [task.course_id for task in tasks] == ["DEMO-E1"]


def test_ungrouped_elective_cannot_be_projected_as_a_fake_required_course() -> None:
    target = _target(requirement=RequirementKind.ELECTIVE)
    diff = _diff((target,))
    assert diff.matches[0].status is not MakeupStatus.REQUIRED
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)


def test_missing_decision_for_elective_is_rejected() -> None:
    target = _target(requirement=RequirementKind.ELECTIVE)
    with pytest.raises(CurriculumNormalizationError):
        _diff((target,), missing_requirements=(_missing(target),))


@pytest.mark.parametrize("old_complete,new_complete", [(False, True), (True, False), (False, False)])
def test_partial_catalogs_do_not_claim_added_or_removed_courses(old_complete: bool, new_complete: bool) -> None:
    diff = _diff(
        (_target("DEMO-NEW"),), old=_version((_target("DEMO-OLD"),), old=True, complete=old_complete),
        new=_version((_target("DEMO-NEW"),), complete=new_complete),
    )
    assert diff.added_course_ids is None and diff.removed_course_ids is None


def test_complete_catalog_delta_does_not_itself_decide_makeup_status() -> None:
    shared, added, removed = _target("DEMO-SHARED"), _target("DEMO-ADDED"), _target("DEMO-REMOVED")
    diff = _diff((shared, added), old=_version((shared, removed), old=True))
    assert diff.added_course_ids == ("DEMO-ADDED",)
    assert diff.removed_course_ids == ("DEMO-REMOVED",)
    assert all(match.status is MakeupStatus.MANUAL_CONFIRMATION for match in diff.matches)


def test_partial_target_cannot_be_projected_even_with_an_explicit_recognition() -> None:
    target, attempt = _target(), _attempt()
    diff = _diff((target,), (attempt,), new=_version((target,), complete=False), recognitions=(_recognition(target, attempt),))
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)


def test_public_projection_preserves_schema_fields_and_marks_unknown_prerequisites() -> None:
    target = _target(prerequisites=None, recommended_term_text="DEMO academic-term range")
    diff = _diff((target,))
    task = project_makeup_tasks(diff)[0]
    assert task.status is MakeupStatus.MANUAL_CONFIRMATION
    assert task.prerequisites == []
    assert "先修" in task.reason and "未知" in task.reason
    assert "先修" in task.source_evidence and "确认" in task.source_evidence
    assert task.recommended_semester is None and task.deadline_semester is None
    payload = task.model_dump(mode="json")
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/makeup_task.schema.json").read_text())
    Draft202012Validator(schema).validate(payload)
    assert not {"priority", "group_id", "requirement", "recommended_term_text", "completed"} & set(payload)


def test_known_prerequisites_and_explicit_semesters_are_preserved() -> None:
    target = _target(prerequisites=("DEMO-PRE",), recommended_semester=3, deadline_semester=4)
    task = project_makeup_tasks(_diff((target,)))[0]
    assert task.prerequisites == ["DEMO-PRE"]
    assert task.recommended_semester == 3 and task.deadline_semester == 4


@pytest.mark.parametrize("status_case", ["manual", "candidate", "required"])
def test_provider_marks_unknown_prerequisites_manual_without_hiding_base_conclusion(status_case: str) -> None:
    target = _target(prerequisites=None, course_name="DEMO Candidate")
    completed = (_attempt("DEMO-OTHER", course_name="DEMO Candidate"),) if status_case == "candidate" else ()
    missing = (_missing(target),) if status_case == "required" else ()
    diff = _diff((target,), completed, missing_requirements=missing)
    task = CurriculumResultProvider(diff).get_makeup_tasks()[0]
    assert task.status is MakeupStatus.MANUAL_CONFIRMATION
    assert task.prerequisites == []
    assert diff.matches[0].reason in task.reason
    assert "先修关系未知" in task.reason
    assert "先修关系未确认" in task.source_evidence
    expected = {
        "manual": MakeupStatus.MANUAL_CONFIRMATION,
        "candidate": MakeupStatus.POSSIBLY_EQUIVALENT,
        "required": MakeupStatus.REQUIRED,
    }
    assert diff.matches[0].status is expected[status_case]


def test_provider_returns_fresh_public_objects_with_unchanged_signature() -> None:
    target = _target(prerequisites=("DEMO-PRE",))
    provider = CurriculumResultProvider(_diff((target,)))
    assert isinstance(provider, CurriculumProvider)
    assert len(inspect.signature(provider.get_makeup_tasks).parameters) == 0
    first, second = provider.get_makeup_tasks(), provider.get_makeup_tasks()
    assert isinstance(first, list) and isinstance(first[0], MakeupTask)
    assert first is not second and first[0] is not second[0]
    original_reason = second[0].reason
    first[0].reason = "DEMO caller mutation"
    first[0].prerequisites.append("DEMO-MUTATION")
    third = provider.get_makeup_tasks()
    assert second[0].reason == third[0].reason == original_reason
    assert second[0].prerequisites == third[0].prerequisites == ["DEMO-PRE"]
    assert target.prerequisites == ("DEMO-PRE",)


def test_satisfied_course_with_unknown_prerequisites_does_not_need_to_be_planned() -> None:
    target, attempt = _target(prerequisites=None), _attempt()
    diff = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt),))
    tasks = CurriculumResultProvider(diff).get_makeup_tasks()
    assert len(tasks) == 1 and tasks[0].status is MakeupStatus.SATISFIED


def test_empty_verified_target_has_no_invented_makeup_tasks() -> None:
    diff = _diff(())
    assert diff.matches == () and diff.group_gaps == ()
    assert CurriculumResultProvider(diff).get_makeup_tasks() == []


def test_direct_construction_snapshots_mutable_candidate_evidence_and_diff_lists() -> None:
    target, attempt = _target(), _attempt()
    candidates = [attempt]
    evidence = ["DEMO-MANUAL-SOURCE"]
    match = CourseMatch(target, MakeupStatus.MANUAL_CONFIRMATION, candidates, "DEMO review required", evidence)
    candidates.clear()
    evidence.clear()
    assert match.candidates == (attempt,) and match.evidence == ("DEMO-MANUAL-SOURCE",)

    matches, gaps, added, requirements = [match], [], [target.course_id], []
    diff = replace(
        _diff((target,)), matches=matches, group_gaps=gaps,
        added_course_ids=added, unrepresented_requirements=requirements,
    )
    matches.clear()
    gaps.append(GroupGap("DEMO-UNRELATED", 1, "DEMO later mutation"))
    added.clear()
    requirements.append("DEMO later mutation")
    assert diff.matches == (match,) and diff.group_gaps == ()
    assert diff.added_course_ids == (target.course_id,) and diff.unrepresented_requirements == ()
    for instance, field in [(match, "reason"), (diff, "matches"), (GroupGap("DEMO-GROUP", 1, "DEMO reason"), "remaining_credit")]:
        with pytest.raises(FrozenInstanceError):
            setattr(instance, field, None)


@pytest.mark.parametrize("evidence", [(), ("  ",)])
def test_direct_match_requires_nonempty_source_evidence(evidence: tuple[str, ...]) -> None:
    with pytest.raises(CurriculumNormalizationError):
        CourseMatch(_target(), MakeupStatus.MANUAL_CONFIRMATION, (), "DEMO reason", evidence)


@pytest.mark.parametrize("failure", ["omit", "reverse"])
def test_direct_diff_cannot_drop_or_reorder_target_entries(failure: str) -> None:
    diff = _diff((_target("DEMO-A"), _target("DEMO-B")))
    matches = diff.matches[:-1] if failure == "omit" else tuple(reversed(diff.matches))
    with pytest.raises(CurriculumNormalizationError):
        replace(diff, matches=matches)


def test_direct_group_gap_cannot_contain_nonfinite_credit() -> None:
    with pytest.raises(CurriculumNormalizationError):
        GroupGap("DEMO-GROUP", float("nan"), "DEMO pending quota")


def test_course_projection_matches_schema_without_converting_term_text() -> None:
    target = _target(course_type="DEMO Context", recommended_term_text="DEMO-TERM-A~DEMO-TERM-B")
    explicit = _target("DEMO-B", recommended_semester=3)
    courses = project_courses(_version((target, explicit)))
    assert isinstance(courses, list) and all(isinstance(course, Course) for course in courses)
    assert courses[0].course_id == target.course_id and courses[0].course_name == target.course_name
    assert courses[0].credit == target.credit and courses[0].course_type == "DEMO Context"
    assert courses[0].recommended_semester is None
    assert courses[1].recommended_semester == 3
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/course.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for course in courses:
        payload = course.model_dump(mode="json")
        validator.validate(payload)
        assert "recommended_term_text" not in payload and "group_id" not in payload


def test_course_projection_marks_unknown_prerequisites_in_source() -> None:
    course = project_courses(_version((_target(prerequisites=None),)))[0]
    assert course.prerequisites == []
    assert "先修" in course.source
    assert "未知" in course.source or "未确认" in course.source


def test_course_projection_rejects_partial_or_duplicate_target_catalogs() -> None:
    target = _target()
    partial = _version((target,), complete=False)
    duplicate = _version((target, _target(course_name="DEMO Other Context", source_record="DEMO-CATALOG#row:2")))
    for version in (partial, duplicate):
        with pytest.raises(CurriculumNormalizationError):
            project_courses(version)


def test_course_projection_returns_independent_objects_and_lists() -> None:
    target = _target(prerequisites=("DEMO-PRE",))
    version = _version((target,))
    first, second = project_courses(version), project_courses(version)
    assert first is not second and first[0] is not second[0]
    first[0].course_name = "DEMO caller mutation"
    first[0].prerequisites.append("DEMO-MUTATED-PRE")
    third = project_courses(version)
    assert second[0].course_name == third[0].course_name == target.course_name
    assert second[0].prerequisites == third[0].prerequisites == ["DEMO-PRE"]
    assert target.prerequisites == ("DEMO-PRE",)


def _assert_modified_diff_is_not_exportable(diff) -> None:
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)
    with pytest.raises(CurriculumNormalizationError):
        CurriculumResultProvider(diff).get_makeup_tasks()


def test_clearing_unmet_quota_does_not_make_modified_diff_exportable() -> None:
    targets, version = _elective_case(6)
    original = _diff(targets, new=version)
    assert original.group_gaps
    modified = replace(original, group_gaps=())
    assert modified.group_gaps == ()  # Still usable as an internal view.
    _assert_modified_diff_is_not_exportable(modified)


def test_clearing_unassigned_elective_does_not_authorize_public_output() -> None:
    original = _diff((_target(requirement=RequirementKind.ELECTIVE),))
    assert original.unrepresented_requirements
    modified = replace(original, unrepresented_requirements=())
    _assert_modified_diff_is_not_exportable(modified)


def test_forged_satisfaction_of_failed_attempt_cannot_enter_provider() -> None:
    target, failed = _target(), _attempt(passed=False)
    original = _diff((target,), (failed,))
    assert original.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION
    forged_match = CourseMatch(
        target, MakeupStatus.SATISFIED, (failed,), "DEMO forged recognition",
        ("DEMO arbitrary evidence",),
    )
    _assert_modified_diff_is_not_exportable(replace(original, matches=(forged_match,)))


def test_unmodified_builder_output_remains_exportable() -> None:
    target, attempt = _target(), _attempt()
    original = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt),))
    assert project_makeup_tasks(original)[0].status is MakeupStatus.SATISFIED
    assert CurriculumResultProvider(original).get_makeup_tasks()[0].status is MakeupStatus.SATISFIED


def test_explicit_missing_output_retains_both_complete_input_sources() -> None:
    target = _target()
    diff = _diff((target,), missing_requirements=(_missing(target),))
    task = project_makeup_tasks(diff)[0]
    assert task.status is MakeupStatus.REQUIRED
    assert "DEMO-EXPLICIT-MISSING-DECISION" in task.source_evidence
    assert diff.new.completeness_evidence in task.source_evidence
    assert "DEMO-COMPLETED-COMPLETE" in task.source_evidence
    assert "DEMO-COMPLETED" in task.source_evidence


@pytest.mark.parametrize("satisfied_dependent", [False, True])
def test_unsatisfied_pool_prerequisites_remain_visible_without_making_the_pool_required(satisfied_dependent) -> None:
    dependent = _target("DEMO-B", prerequisites=("DEMO-E2",))
    earned = _target("DEMO-E1", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP")
    predecessor = _target("DEMO-E2", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP",
                          prerequisites=("DEMO-E3",))
    earlier = _target("DEMO-E3", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP")
    unrelated = _target("DEMO-E4", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP")
    targets = (dependent, earned, predecessor, earlier, unrelated)
    group = CurriculumGroup("DEMO-GROUP", "DEMO Pool", 3, "DEMO-GROUP-SOURCE")
    attempt = _attempt("DEMO-E1")
    completed = (attempt,)
    recognitions = (_recognition(earned, attempt),)
    missing = (_missing(dependent),)
    if satisfied_dependent:
        passed_dependent = _attempt("DEMO-B", row=2)
        completed += (passed_dependent,)
        recognitions += (_recognition(dependent, passed_dependent),)
        missing = ()
    diff = _diff(targets, completed, new=_version(targets, groups=(group,)),
                 recognitions=recognitions, missing_requirements=missing)
    assert diff.group_gaps == ()
    tasks = CurriculumResultProvider(diff).get_makeup_tasks()
    if satisfied_dependent:
        assert [task.course_id for task in tasks] == ["DEMO-B", "DEMO-E1"]
    else:
        assert [task.course_id for task in tasks] == ["DEMO-B", "DEMO-E1", "DEMO-E2", "DEMO-E3"]
        assert tasks[0].prerequisites == ["DEMO-E2"]
        assert tasks[2].prerequisites == ["DEMO-E3"]
        assert all(task.status is MakeupStatus.MANUAL_CONFIRMATION for task in tasks[2:])
        assert all("DEMO-GROUP-SOURCE" in task.source_evidence and "选修池" in task.reason for task in tasks[2:])
        tasks[2].prerequisites.clear()
        assert CurriculumResultProvider(diff).get_makeup_tasks()[2].prerequisites == ["DEMO-E3"]


def test_cyclic_pool_prerequisite_references_are_retained_and_projection_terminates() -> None:
    dependent = _target("DEMO-B", prerequisites=("DEMO-E1",))
    first = _target("DEMO-E1", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP",
                    prerequisites=("DEMO-E2",))
    second = _target("DEMO-E2", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP",
                     prerequisites=("DEMO-E1",))
    group = CurriculumGroup("DEMO-GROUP", "DEMO Pool", 0, "DEMO-GROUP-SOURCE")
    targets = (dependent, first, second)
    diff = _diff(targets, new=_version(targets, groups=(group,)), missing_requirements=(_missing(dependent),))
    tasks = project_makeup_tasks(diff)
    assert [task.prerequisites for task in tasks] == [["DEMO-E1"], ["DEMO-E2"], ["DEMO-E1"]]
    assert [task.status for task in tasks[1:]] == [MakeupStatus.MANUAL_CONFIRMATION] * 2


def test_adding_selection_to_a_modified_diff_cannot_authorize_unmet_group_projection() -> None:
    targets, version = _elective_case(6)
    original = _diff(targets, new=version)
    selection = ConfirmedElectiveSelection(version.version_id, "DEMO-GROUP",
                                          tuple(target.course_id for target in targets), "DEMO-CHOICE")
    modified = replace(original, elective_selections=(selection,))
    _assert_modified_diff_is_not_exportable(modified)


def test_explicitly_selected_elective_can_use_a_scoped_missing_decision() -> None:
    targets, version = _elective_case(3)
    selected = targets[0]
    selection = ConfirmedElectiveSelection(version.version_id, "DEMO-GROUP", (selected.course_id,), "DEMO-CHOICE")
    diff = _diff(targets, new=version, elective_selections=(selection,), missing_requirements=(_missing(selected),))
    tasks = project_makeup_tasks(diff)
    assert [task.course_id for task in tasks] == [selected.course_id]
    assert tasks[0].status is MakeupStatus.REQUIRED
    assert "DEMO-CHOICE" in tasks[0].source_evidence
    assert diff.group_gaps[0].remaining_credit == 3
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/makeup_task.schema.json").read_text())
    payload = tasks[0].model_dump(mode="json")
    Draft202012Validator(schema).validate(payload)
    assert not {"group_id", "elective_selections", "priority"} & set(payload)
