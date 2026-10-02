"""Synthetic evidence-scoped case rules, never real school policy."""

from dataclasses import FrozenInstanceError, replace

import pytest

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedElectiveSelection,
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumResultProvider,
    MatchingRules,
    build_curriculum_diff,
    elective_plan_covers_group,
    group_plan_covers_requirement,
    project_makeup_tasks,
    selected_elective_course_ids,
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


def _selection(*course_ids, **changes):
    return ConfirmedElectiveSelection(**{
        "target_version_id": "DEMO-NEW", "group_id": "DEMO-GROUP", "course_ids": course_ids,
        "evidence": "mock://DEMO-human-elective-choice", **changes,
    })


def _pool(minimum=6, **changes):
    targets = tuple(_target(f"DEMO-E{number}", requirement=RequirementKind.ELECTIVE,
                           group_id="DEMO-GROUP", **changes) for number in (1, 2, 3))
    group = CurriculumGroup("DEMO-GROUP", "DEMO Pool", minimum, "DEMO-GROUP-SOURCE")
    return targets, _version(targets, groups=(group,))


def test_rule_confirmed_absence_is_traceable_even_with_no_completed_candidates():
    diff = _diff((_target(),), (_attempt("DEMO-OTHER"),))
    task = project_makeup_tasks(diff)[0]
    assert task.status is MakeupStatus.REQUIRED
    assert task.source_evidence.endswith("已修记录完整性依据：DEMO-D4-CHECKLIST")
    assert "DEMO-CATALOG-CHECKLIST" in task.source_evidence and "DEMO-COMPLETED" in task.source_evidence
    assert "mock://DEMO-case-rules" in task.source_evidence


@pytest.mark.parametrize("changes", [
    {"evidence": None}, {"evidence": "  "}, {"group_id": ""}, {"target_version_id": None},
    {"course_ids": ()}, {"course_ids": "DEMO-E1"}, {"course_ids": ("DEMO-E1", "DEMO-E1")},
    {"course_ids": (1,)}, {"course_ids": (" ",)},
])
def test_elective_choice_requires_explicit_evidence_and_unique_real_course_references(changes):
    with pytest.raises(CurriculumNormalizationError):
        _selection("DEMO-E1", **changes)


def test_elective_selection_snapshots_source_lists_without_changing_group_facts():
    courses = ["DEMO-E1", "DEMO-E2"]
    selection = _selection(course_ids=courses)
    courses.clear()
    assert selection.course_ids == ("DEMO-E1", "DEMO-E2")
    with pytest.raises(FrozenInstanceError):
        selection.evidence = "DEMO-CHANGED"
    targets, version = _pool()
    selections = [selection]
    diff = _diff(targets, new=version, elective_selections=selections)
    selections.clear()
    assert diff.elective_selections == (selection,)
    assert diff.group_gaps[0].remaining_credit == 6
    assert all(match.status is not MakeupStatus.SATISFIED for match in diff.matches)


@pytest.mark.parametrize("selection", [
    _selection("DEMO-E1", target_version_id="DEMO-FOREIGN-VERSION"),
    _selection("DEMO-E1", group_id="DEMO-FOREIGN-GROUP"),
    _selection("DEMO-FOREIGN-ID"),
])
def test_elective_selection_cannot_escape_target_version_or_group(selection):
    targets, version = _pool()
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _diff(targets, new=version, elective_selections=(selection,))
    assert "DEMO-FOREIGN" not in str(excinfo.value)


def test_elective_selection_rejects_duplicate_decisions_cross_group_and_non_pool_targets():
    targets, version = _pool()
    selection = _selection("DEMO-E1")
    with pytest.raises(CurriculumNormalizationError, match="duplicate"):
        _diff(targets, new=version, elective_selections=(selection, selection))
    other = _target("DEMO-OTHER", requirement=RequirementKind.ELECTIVE, group_id="DEMO-OTHER-GROUP")
    required = _target("DEMO-REQUIRED", group_id="DEMO-GROUP")
    groups = version.groups + (CurriculumGroup("DEMO-OTHER-GROUP", "DEMO Other Pool", 0, "DEMO-OTHER-GROUP-SOURCE"),)
    expanded = _version(targets + (other, required), groups=groups)
    for course_id in (other.course_id, required.course_id):
        with pytest.raises(CurriculumNormalizationError, match="pool"):
            _diff(expanded.courses, new=expanded, elective_selections=(_selection(course_id),))


def test_selection_cannot_choose_a_course_with_multiple_target_contexts():
    targets, version = _pool()
    duplicate = replace(targets[0], source_record="DEMO-SECOND-CONTEXT")
    version = _version(targets + (duplicate,), groups=version.groups)
    with pytest.raises(CurriculumNormalizationError, match="uniquely"):
        _diff(version.courses, new=version, elective_selections=(_selection(targets[0].course_id),))


def test_confirmed_choice_produces_future_tasks_and_preserves_actual_unearned_group_gap():
    targets, version = _pool()
    passed = _attempt("DEMO-E1")
    diff = _diff(targets, (passed,), new=version, elective_selections=(_selection("DEMO-E2"),))
    assert diff.group_gaps[0].remaining_credit == 3
    assert selected_elective_course_ids(diff) == ("DEMO-E2",)
    assert elective_plan_covers_group(diff, "DEMO-GROUP")
    tasks = project_makeup_tasks(diff)
    assert [(task.course_id, task.status) for task in tasks] == [
        ("DEMO-E1", MakeupStatus.SATISFIED), ("DEMO-E2", MakeupStatus.REQUIRED),
    ]
    assert "mock://DEMO-human-elective-choice" in tasks[1].source_evidence
    assert "DEMO-GROUP-SOURCE" in tasks[1].source_evidence and "DEMO-D4-CHECKLIST" in tasks[1].source_evidence
    assert "未来计划" in tasks[1].reason
    tasks[1].course_name = "DEMO-MUTATED"
    assert project_makeup_tasks(diff)[1].course_name == targets[1].course_name
    assert diff.group_gaps[0].remaining_credit == 3


@pytest.mark.parametrize("mode", ["no_rules", "candidate", "unknown_prerequisite", "unknown_passing_identity"])
def test_confirmed_choice_does_not_confirm_matching_or_unknown_prerequisites(mode):
    targets, version = _pool(3, prerequisites=None if mode == "unknown_prerequisite" else ())
    completed = ()
    rules = None if mode in {"no_rules", "candidate"} else _rules()
    if mode == "candidate":
        completed = (_attempt("DEMO-OTHER", course_name=targets[0].course_name),)
    elif mode == "unknown_passing_identity":
        completed = (_attempt(None, course_name="DEMO Unresolved Other Course"),)
    diff = _diff(targets, completed, new=version, rules=rules, elective_selections=(_selection("DEMO-E1"),))
    task = project_makeup_tasks(diff)[0]
    assert task.status is (MakeupStatus.POSSIBLY_EQUIVALENT if mode == "candidate" else MakeupStatus.MANUAL_CONFIRMATION)
    assert task.course_id == "DEMO-E1" and "mock://DEMO-human-elective-choice" in task.source_evidence
    assert diff.group_gaps[0].remaining_credit == 3
    if mode == "unknown_prerequisite":
        assert task.prerequisites == [] and "先修关系未知" in task.reason
        assert diff.matches[0].status is MakeupStatus.REQUIRED


@pytest.mark.parametrize("minimum,chosen,passed", [
    (None, ("DEMO-E1", "DEMO-E2"), False),
    (6, ("DEMO-E1",), False),
    (6, ("DEMO-E1",), True),
    (6, (), False),
])
def test_unknown_or_uncovered_quota_never_counts_a_future_choice_as_earned_credit(minimum, chosen, passed):
    targets, version = _pool(minimum)
    completed = (_attempt("DEMO-E1"),) if passed else ()
    selections = (_selection(*chosen),) if chosen else ()
    diff = _diff(targets, completed, new=version, elective_selections=selections)
    assert diff.group_gaps[0].remaining_credit == (None if minimum is None else minimum - (3 if passed else 0))
    assert not elective_plan_covers_group(diff, "DEMO-GROUP")
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)


def test_plan_credit_from_one_group_cannot_cover_a_second_group():
    targets, version = _pool(3)
    other = _target("DEMO-OTHER", requirement=RequirementKind.ELECTIVE, group_id="DEMO-OTHER-GROUP")
    group = CurriculumGroup("DEMO-OTHER-GROUP", "DEMO Other Pool", 3, "DEMO-OTHER-GROUP-SOURCE")
    version = _version(targets + (other,), groups=version.groups + (group,))
    diff = _diff(version.courses, new=version, elective_selections=(_selection("DEMO-E1", "DEMO-E2"),))
    assert elective_plan_covers_group(diff, "DEMO-GROUP")
    assert not elective_plan_covers_group(diff, group.group_id)
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)


def test_satisfied_group_does_not_require_unearned_chosen_pool_courses():
    targets, version = _pool(3)
    diff = _diff(targets, (_attempt("DEMO-E1"),), new=version,
                 elective_selections=(_selection("DEMO-E2"),))
    assert diff.group_gaps == () and selected_elective_course_ids(diff) == ()
    assert diff.matches[1].status is not MakeupStatus.REQUIRED
    assert [task.course_id for task in project_makeup_tasks(diff)] == ["DEMO-E1"]


def test_clearing_choices_from_a_modified_diff_does_not_bypass_builder_guard():
    targets, version = _pool(3)
    valid = _diff(targets, new=version, elective_selections=(_selection("DEMO-E1"),))
    assert project_makeup_tasks(valid)[0].status is MakeupStatus.REQUIRED
    with pytest.raises(CurriculumNormalizationError, match="rebuild"):
        project_makeup_tasks(replace(valid, elective_selections=()))


def test_selected_credit_cannot_complete_a_partial_target_catalog():
    targets, version = _pool(3)
    version = replace(version, complete=False, completeness_evidence=None)
    diff = _diff(targets, new=version, elective_selections=(_selection("DEMO-E1"),))
    assert not elective_plan_covers_group(diff, "DEMO-GROUP")
    assert diff.matches[0].status is MakeupStatus.MANUAL_CONFIRMATION
    with pytest.raises(CurriculumNormalizationError, match="incomplete"):
        project_makeup_tasks(diff)


def test_known_mandatory_group_projects_without_an_elective_choice():
    targets = tuple(_target(course_id, group_id="DEMO-GROUP") for course_id in ("DEMO-R1", "DEMO-R2"))
    group = CurriculumGroup("DEMO-GROUP", "DEMO Mandatory Group", 6, "DEMO-GROUP-SOURCE")
    diff = _diff(targets, new=_version(targets, groups=(group,)))
    assert not diff.elective_selections and diff.group_gaps[0].remaining_credit == 6
    assert group_plan_covers_requirement(diff, "DEMO-GROUP")
    assert elective_plan_covers_group(diff, "DEMO-GROUP")
    tasks = project_makeup_tasks(diff)
    assert [(task.course_id, task.status) for task in tasks] == [
        ("DEMO-R1", MakeupStatus.REQUIRED), ("DEMO-R2", MakeupStatus.REQUIRED),
    ]
    assert diff.group_gaps[0].remaining_credit == 6


def test_mixed_group_combines_earned_elective_and_remaining_mandatory_requirement():
    targets = (
        _target("DEMO-R1", group_id="DEMO-GROUP"),
        _target("DEMO-E1", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP"),
        _target("DEMO-E2", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP"),
    )
    group = CurriculumGroup("DEMO-GROUP", "DEMO Mixed Group", 6, "DEMO-GROUP-SOURCE")
    diff = _diff(targets, (_attempt("DEMO-E1"),), new=_version(targets, groups=(group,)))
    assert diff.group_gaps[0].remaining_credit == 3 and not diff.elective_selections
    assert [(task.course_id, task.status) for task in project_makeup_tasks(diff)] == [
        ("DEMO-R1", MakeupStatus.REQUIRED), ("DEMO-E1", MakeupStatus.SATISFIED),
    ]
    assert diff.group_gaps[0].remaining_credit == 3


def test_insufficient_mandatory_credits_still_require_an_explicit_elective_choice():
    targets = (
        _target("DEMO-R1", group_id="DEMO-GROUP"),
        _target("DEMO-E1", requirement=RequirementKind.ELECTIVE, group_id="DEMO-GROUP"),
    )
    group = CurriculumGroup("DEMO-GROUP", "DEMO Mixed Group", 6, "DEMO-GROUP-SOURCE")
    version = _version(targets, groups=(group,))
    uncovered = _diff(targets, new=version)
    assert not group_plan_covers_requirement(uncovered, "DEMO-GROUP")
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(uncovered)
    selected = _diff(targets, new=version, elective_selections=(_selection("DEMO-E1"),))
    assert group_plan_covers_requirement(selected, "DEMO-GROUP")
    assert [task.status for task in project_makeup_tasks(selected)] == [MakeupStatus.REQUIRED] * 2
    assert selected.group_gaps[0].remaining_credit == 6


def test_unknown_requirement_classification_does_not_cover_a_group_credit_gap():
    targets = (
        _target("DEMO-R1", group_id="DEMO-GROUP"),
        _target("DEMO-U1", requirement=RequirementKind.UNKNOWN, group_id="DEMO-GROUP"),
    )
    group = CurriculumGroup("DEMO-GROUP", "DEMO Mixed Group", 6, "DEMO-GROUP-SOURCE")
    diff = _diff(targets, new=_version(targets, groups=(group,)))
    assert diff.matches[1].status is MakeupStatus.MANUAL_CONFIRMATION
    assert not group_plan_covers_requirement(diff, "DEMO-GROUP")
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)
    assert diff.group_gaps[0].remaining_credit == 6


@pytest.mark.parametrize("mode", ["no_rules", "candidate", "unknown_prerequisite", "unknown_passing_identity"])
def test_mandatory_plan_capacity_preserves_unconfirmed_matching_and_prerequisites(mode):
    target = _target("DEMO-R1", group_id="DEMO-GROUP",
                     prerequisites=None if mode == "unknown_prerequisite" else ())
    group = CurriculumGroup("DEMO-GROUP", "DEMO Mandatory Group", 3, "DEMO-GROUP-SOURCE")
    completed = ()
    rules = None if mode in {"no_rules", "candidate"} else _rules()
    if mode == "candidate":
        completed = (_attempt("DEMO-OTHER", course_name=target.course_name),)
    elif mode == "unknown_passing_identity":
        completed = (_attempt(None, course_name="DEMO Unresolved Other Course"),)
    diff = _diff((target,), completed, new=_version((target,), groups=(group,)), rules=rules)
    assert group_plan_covers_requirement(diff, "DEMO-GROUP")
    task = project_makeup_tasks(diff)[0]
    assert task.status is (MakeupStatus.POSSIBLY_EQUIVALENT if mode == "candidate" else MakeupStatus.MANUAL_CONFIRMATION)
    assert diff.group_gaps[0].remaining_credit == 3
    if mode == "unknown_prerequisite":
        assert diff.matches[0].status is MakeupStatus.REQUIRED
        assert task.prerequisites == [] and "先修关系未知" in task.reason


@pytest.mark.parametrize("mode", ["unknown_minimum", "incomplete", "duplicate_target"])
def test_mandatory_capacity_does_not_bypass_incomplete_or_ambiguous_group_inputs(mode):
    target = _target("DEMO-R1", group_id="DEMO-GROUP")
    targets = (target, replace(target, source_record="DEMO-SECOND-CONTEXT")) if mode == "duplicate_target" else (target,)
    group = CurriculumGroup("DEMO-GROUP", "DEMO Mandatory Group", None if mode == "unknown_minimum" else 3,
                            "DEMO-GROUP-SOURCE")
    version = _version(targets, groups=(group,), complete=mode != "incomplete",
                       completeness_evidence=None if mode == "incomplete" else "DEMO-CATALOG-CHECKLIST")
    diff = _diff(targets, new=version)
    assert not group_plan_covers_requirement(diff, "DEMO-GROUP")
    with pytest.raises(CurriculumNormalizationError):
        project_makeup_tasks(diff)
