"""Synthetic evidence-scoped case rules, never real school policy."""

from dataclasses import FrozenInstanceError, replace

import pytest

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumResultProvider,
    MatchingRules,
    build_curriculum_diff,
    project_makeup_tasks,
)
from app.curriculum.requirements import CurriculumCourse, CurriculumGroup, CurriculumVersion, RequirementKind
from app.models.contracts import MakeupStatus


def _target(course_id="DEMO-A", **changes):
    return CurriculumCourse(**{
        "course_id": course_id, "course_name": f"DEMO Course {course_id}", "credit": 3,
        "requirement": RequirementKind.REQUIRED, "source_record": f"DEMO-CATALOG!{course_id}",
        "prerequisites": (), **changes,
    })


def _version(courses=(), **changes):
    return CurriculumVersion(**{
        "version_id": "DEMO-NEW", "major": "DEMO Major", "cohort": "DEMO Cohort",
        "source_id": "DEMO-CATALOG", "courses": courses, "complete": True,
        "completeness_evidence": "DEMO-CATALOG-CHECKLIST", **changes,
    })


def _attempt(course_id="DEMO-A", row=1, **changes):
    return CompletedCourse(**{
        "course_id": course_id, "course_name": f"DEMO Course {course_id}", "credit": 3,
        "semester": "DEMO-TERM", "passed": True, "course_type": None,
        "course_id_status": CourseIdStatus.CONFIRMED if course_id else CourseIdStatus.PENDING,
        "id_match_source": "DEMO-ID-SOURCE" if course_id else None,
        "source_id": "DEMO-COMPLETED", "source_record": f"DEMO-SHEET!row:{row}", **changes,
    })


def _rules(**changes):
    return MatchingRules(**{
        "target_version_id": "DEMO-NEW", "completed_source_id": "DEMO-COMPLETED",
        "evidence": "mock://DEMO-case-rules", "allow_exact_match": True,
        "allow_confirmed_absence": True, **changes,
    })


def _diff(targets, completed=(), **changes):
    return build_curriculum_diff(**{
        "old": _version(version_id="DEMO-OLD"),
        "new": changes["new"] if "new" in changes else _version(targets), "completed": completed,
        "completed_source_id": "DEMO-COMPLETED", "completed_complete": True,
        "completed_completeness_evidence": "DEMO-D4-CHECKLIST", "rules": _rules(), **changes,
    })


def _recognition(target, attempt):
    return ConfirmedRecognition(
        "DEMO-NEW", target.course_id, attempt.source_id, attempt.source_record,
        target.credit, "DEMO-EXPLICIT-OVERRIDE",
    )


def _missing(target, **changes):
    return ConfirmedMissingRequirement(**{
        "target_version_id": "DEMO-NEW", "target_course_id": target.course_id,
        "completed_source_id": "DEMO-COMPLETED", "evidence": "DEMO-EXPLICIT-ABSENCE", **changes,
    })


def test_rule_defaults_are_disabled_and_all_fields_are_immutable():
    rules = MatchingRules("DEMO-NEW", "DEMO-COMPLETED", "DEMO-EVIDENCE")
    assert rules.allow_exact_match is False and rules.allow_confirmed_absence is False
    with pytest.raises(FrozenInstanceError):
        rules.allow_exact_match = True


@pytest.mark.parametrize("field", ["target_version_id", "completed_source_id", "evidence"])
@pytest.mark.parametrize("value", [None, "", "  ", 1])
def test_rule_scope_and_evidence_require_nonempty_strings(field, value):
    with pytest.raises(CurriculumNormalizationError, match=field):
        _rules(**{field: value})


@pytest.mark.parametrize("field", ["allow_exact_match", "allow_confirmed_absence"])
@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_rule_flags_require_actual_booleans(field, value):
    with pytest.raises(CurriculumNormalizationError, match=field):
        _rules(**{field: value})


@pytest.mark.parametrize("rule_changes", [
    {"target_version_id": "DEMO-PRIVATE-FOREIGN-VERSION"},
    {"completed_source_id": "DEMO-PRIVATE-FOREIGN-D4"},
])
def test_rules_cannot_cross_case_scope_and_errors_do_not_echo_values(rule_changes):
    with pytest.raises(CurriculumNormalizationError) as error:
        _diff((_target(),), (_attempt(),), rules=_rules(**rule_changes))
    assert "DEMO-PRIVATE" not in str(error.value)


def test_empty_completed_facts_require_an_explicit_scope_for_rules():
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        _diff((_target(),), completed_source_id=None)
    assert _diff((_target(),)).matches[0].status is MakeupStatus.REQUIRED


def test_nonempty_unique_completed_source_can_bind_the_rules():
    diff = _diff((_target(),), (_attempt(),), completed_source_id=None)
    assert diff.matches[0].status is MakeupStatus.SATISFIED


def test_invalid_rules_type_is_rejected():
    with pytest.raises(CurriculumNormalizationError, match="rules"):
        _diff((_target(),), rules={"allow_exact_match": True})


def test_no_rules_and_disabled_rules_keep_the_original_conservative_behavior():
    for rules in (None, _rules(allow_exact_match=False, allow_confirmed_absence=False)):
        diff = _diff((_target(), _target("DEMO-B")), (_attempt(),), rules=rules)
        assert all(match.status is MakeupStatus.MANUAL_CONFIRMATION for match in diff.matches)


def test_exact_passing_match_is_satisfied_without_per_course_decisions():
    target = _target(course_name="DEMO Course Ａ")
    attempt = _attempt(course_name=" demo   course a ")
    diff = _diff((target,), (attempt,))
    assert diff.matches[0].status is MakeupStatus.SATISFIED
    assert diff.matches[0].candidates == (attempt,)
    task = CurriculumResultProvider(diff).get_makeup_tasks()[0]
    assert task.status is MakeupStatus.SATISFIED
    assert "mock://DEMO-case-rules" in task.source_evidence
    assert "case" in task.reason and "学校批准" not in task.reason


@pytest.mark.parametrize("attempt_changes", [
    {"credit": 2}, {"credit": 4}, {"credit": 3.0000000000000004},
    {"course_name": "DEMO Conflicting Name"},
])
def test_credit_or_name_difference_does_not_auto_recognize(attempt_changes):
    assert _diff((_target(),), (_attempt(**attempt_changes),)).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_name_only_with_a_different_confirmed_id_stays_a_candidate():
    attempt = _attempt("DEMO-OTHER", course_name=_target().course_name)
    assert _diff((_target(),), (attempt,)).matches[0].status is MakeupStatus.POSSIBLY_EQUIVALENT


def test_pending_identity_candidate_requires_manual_confirmation():
    attempt = _attempt(None, course_name=_target().course_name)
    assert _diff((_target(),), (attempt,)).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_a_failed_attempt_with_a_separate_exact_pass_is_satisfied_without_credit_merging():
    failed = _attempt(passed=False, credit=2)
    passing = _attempt(row=2)
    diff = _diff((_target(),), (failed, passing))
    assert diff.matches[0].status is MakeupStatus.SATISFIED
    assert diff.matches[0].candidates == (failed, passing)
    assert project_makeup_tasks(diff)[0].credit == 3


def test_multiple_consistent_passes_do_not_add_credits():
    attempts = (_attempt(), _attempt(row=2))
    diff = _diff((_target(),), attempts)
    assert diff.matches[0].status is MakeupStatus.SATISFIED
    assert project_makeup_tasks(diff)[0].credit == 3


@pytest.mark.parametrize("changes", [{"credit": 4}, {"course_name": "DEMO Different Passing Name"}])
def test_conflicting_passing_records_remain_manual_even_with_one_exact_pass(changes):
    attempts = (_attempt(), _attempt(row=2, **changes))
    assert _diff((_target(),), attempts).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_duplicate_source_reference_is_manual_even_with_a_passing_record():
    failed = _attempt(passed=False)
    passing = _attempt()
    assert _diff((_target(),), (failed, passing)).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_complete_case_absence_rule_generates_required_without_rowwise_decisions():
    target = _target()
    diff = _diff((target,), (_attempt(passed=False),))
    assert diff.matches[0].status is MakeupStatus.REQUIRED
    assert "mock://DEMO-case-rules" in project_makeup_tasks(diff)[0].source_evidence


def test_absence_permission_does_not_enable_exact_recognition():
    diff = _diff((_target(),), (_attempt(),), rules=_rules(allow_exact_match=False))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_absence_only_rules_do_not_ignore_duplicate_source_references():
    attempt = _attempt(passed=False)
    diff = _diff((_target(),), (attempt, attempt), rules=_rules(allow_exact_match=False))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_an_ambiguous_source_reference_cannot_prove_absence_of_another_course():
    attempt = _attempt("DEMO-OTHER", passed=False)
    diff = _diff((_target(),), (attempt, attempt))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


@pytest.mark.parametrize("changes", [
    {"completed_complete": False, "completed_completeness_evidence": None},
    {"new": _version((_target(),), complete=False, completeness_evidence=None)},
    {"rules": _rules(allow_confirmed_absence=False)},
])
def test_absence_requires_both_completeness_and_rule_permission(changes):
    assert _diff((_target(),), **changes).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_an_unrelated_unknown_passing_id_prevents_confirmed_absence():
    pending = _attempt(None, course_name="DEMO Unresolved Course")
    assert _diff((_target(),), (pending,)).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_unknown_requirement_kind_is_not_made_required_by_rules():
    target = _target(requirement=RequirementKind.UNKNOWN)
    assert _diff((target,)).matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_explicit_recognition_can_override_a_credit_difference_with_evidence():
    target, attempt = _target(), _attempt(credit=2)
    diff = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt),))
    assert diff.matches[0].status is MakeupStatus.SATISFIED
    assert "DEMO-EXPLICIT-OVERRIDE" in project_makeup_tasks(diff)[0].source_evidence


def test_explicit_absence_works_even_when_case_absence_rule_is_disabled():
    target = _target()
    diff = _diff((target,), rules=_rules(allow_confirmed_absence=False), missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.REQUIRED


def test_explicit_missing_and_recognition_conflict_is_not_erased_by_rules():
    target, attempt = _target(), _attempt()
    diff = _diff((target,), (attempt,), recognitions=(_recognition(target, attempt),), missing_requirements=(_missing(target),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_invalid_explicit_missing_source_is_not_overridden_by_case_absence():
    target = _target()
    diff = _diff((target,), missing_requirements=(_missing(target, completed_source_id="DEMO-OTHER"),))
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION


def test_automatic_identity_and_explicit_recognition_cannot_reuse_one_attempt_across_targets():
    a, b, attempt = _target(), _target("DEMO-B"), _attempt()
    diff = _diff((a, b), (attempt,), recognitions=(_recognition(b, attempt),))
    assert all(match.status is MakeupStatus.MANUAL_CONFIRMATION for match in diff.matches)
    assert all("多门" in match.reason for match in diff.matches)


def test_duplicate_target_guard_and_builder_token_remain_active():
    a = _target()
    another = _target(source_record="DEMO-CATALOG!other-context")
    diff = _diff((a, another), (_attempt(),))
    assert all(match.status is MakeupStatus.MANUAL_CONFIRMATION for match in diff.matches)
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)
    valid = _diff((a,), (_attempt(),))
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(replace(valid, matches=valid.matches))


def test_elective_group_gaps_are_not_hidden_or_transformed_into_required_tasks():
    target = _target(requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP")
    group = CurriculumGroup("DEMO-GROUP", "DEMO Elective Group", 6, "DEMO-GROUP-SOURCE")
    version = _version((target,), groups=(group,))
    diff = _diff((target,), (_attempt(),), new=version)
    assert diff.matches[0].status is MakeupStatus.SATISFIED
    assert diff.group_gaps[0].remaining_credit == 3
    with pytest.raises(CurriculumNormalizationError):
        CurriculumResultProvider(diff).get_makeup_tasks()


def test_unknown_prerequisites_project_manual_while_internal_required_is_retained():
    target = _target(prerequisites=None)
    diff = _diff((target,))
    assert diff.matches[0].status is MakeupStatus.REQUIRED
    provider = CurriculumResultProvider(diff)
    first, second = provider.get_makeup_tasks(), provider.get_makeup_tasks()
    assert first[0].status is MakeupStatus.MANUAL_CONFIRMATION
    assert diff.matches[0].reason in first[0].reason and "先修关系未知" in first[0].reason
    assert "先修关系未确认" in first[0].source_evidence
    assert first[0].prerequisites == []
    first[0].prerequisites.append("DEMO-MUTATION")
    assert second[0].prerequisites == provider.get_makeup_tasks()[0].prerequisites == []


def test_satisfied_unknown_prerequisites_are_not_downgraded_to_makeup():
    target = _target(prerequisites=None)
    diff = _diff((target,), (_attempt(),))
    assert CurriculumResultProvider(diff).get_makeup_tasks()[0].status is MakeupStatus.SATISFIED
