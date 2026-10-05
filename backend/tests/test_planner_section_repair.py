"""单目标换班的正式测试；所有案例为人工合成 Mock，无真实教务材料。"""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models.contracts import Change, CourseOffering, Meeting
from app.planner import (
    ConflictState,
    RepairOutcome,
    SearchOutcome,
    find_alternative_sections,
    repair_target_section,
)


def _meeting(weekday: int = 1, start: int = 3, end: int = 4) -> Meeting:
    return Meeting(
        weekday=weekday, start_section=start, end_section=end, weeks=[1, 3, 5]
    )


def _offering(
    class_id: str,
    weekday: int = 1,
    *,
    course_id: str = "mock-target",
    semester: str = "2026-1",
    unknown: bool = False,
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=f"Mock 课程 {course_id}",
        class_id=class_id,
        semester=semester,
        meetings=[] if unknown else [_meeting(weekday)],
        data_source="mock",
    )


def _case() -> tuple[CourseOffering, list[CourseOffering]]:
    original = _offering("original")
    schedule = [
        _offering("before", 2, course_id="mock-before"),
        original,
        _offering("blocker", course_id="mock-blocker"),
        _offering("after", 4, course_id="mock-after"),
    ]
    return original, schedule


def _args(
    offerings: list[CourseOffering], schedule: list[CourseOffering]
) -> dict:
    return dict(
        course_id="mock-target",
        current_class_id="original",
        semester="2026-1",
        offerings=offerings,
        current_schedule=schedule,
    )


def _ids(offerings) -> list[str]:
    return [offering.class_id for offering in offerings]


def test_original_clear_does_not_replace_even_when_choice_provided() -> None:
    original = _offering("original", 3)
    schedule = [original, _offering("other", course_id="mock-other")]
    args = _args([_offering("alternative", 5)], schedule)
    result = repair_target_section(**args, replacement_class_id="alternative")
    assert result.search.original_state is ConflictState.CLEAR
    assert result.outcome is RepairOutcome.ORIGINAL_CLEAR
    assert list(result.new_schedule) == schedule
    assert result.changes == ()


def test_conflict_repair_keeps_other_classes_order_and_records_change() -> None:
    original, schedule = _case()
    alternative = _offering("alternative", 3)
    result = repair_target_section(
        **_args([original, alternative], schedule),
        replacement_class_id="alternative",
    )
    assert result.search.original_state is ConflictState.CONFLICT
    assert result.outcome is RepairOutcome.REPLACED
    assert _ids(result.new_schedule) == ["before", "alternative", "blocker", "after"]
    for index in (0, 2, 3):
        assert result.new_schedule[index] == schedule[index]
    assert result.changes == (
        Change(
            course_id="mock-target", from_class="original", to_class="alternative",
            reason=result.reason,
        ),
    )
    assert "已知时间冲突" in result.reason


def test_single_clear_candidate_does_not_get_automatically_selected() -> None:
    _, schedule = _case()
    result = repair_target_section(**_args([_offering("clear", 3)], schedule))
    assert result.outcome is RepairOutcome.SELECTION_REQUIRED
    assert _ids(result.search.clear_candidates) == ["clear"]
    assert list(result.new_schedule) == schedule
    assert result.changes == ()


@pytest.mark.parametrize("choice", [None, "z-clear", "a-clear"])
def test_multiple_clear_candidates_keep_source_order_and_explicit_choice(choice) -> None:
    _, schedule = _case()
    z = _offering("z-clear", 3)
    a = _offering("a-clear", 5)
    z.remaining_capacity, a.remaining_capacity = 0, 100
    z.teacher, a.teacher = "Mock 教师 Z", "Mock 教师 A"
    result = repair_target_section(
        **_args([z, a], schedule), replacement_class_id=choice
    )
    assert _ids(result.search.clear_candidates) == ["z-clear", "a-clear"]
    if choice is None:
        assert result.outcome is RepairOutcome.SELECTION_REQUIRED
        assert result.changes == ()
    else:
        assert result.outcome is RepairOutcome.REPLACED
        assert result.new_schedule[1].class_id == choice


@pytest.mark.parametrize("unknown_first", [True, False])
def test_unused_unknown_does_not_prevent_clear_repair(unknown_first: bool) -> None:
    _, schedule = _case()
    offerings = [_offering("unknown", unknown=True), _offering("clear", 3)]
    if not unknown_first:
        offerings.reverse()
    result = repair_target_section(
        **_args(offerings, schedule), replacement_class_id="clear"
    )
    assert result.outcome is RepairOutcome.REPLACED
    assert result.search.outcome is SearchOutcome.CLEAR_AVAILABLE
    assert _ids(result.search.clear_candidates) == ["clear"]
    assert result.search.unknown_candidates[0].offering.class_id == "unknown"
    assert "当前来源快照" in result.search.unknown_candidates[0].reason
    assert "人工核验" in result.search.unknown_candidates[0].reason


@pytest.mark.parametrize(
    "kind,search_outcome,repair_outcome",
    [
        ("unknown", SearchOutcome.SCHEDULE_UNKNOWN, RepairOutcome.SCHEDULE_UNKNOWN),
        ("conflict", SearchOutcome.ALL_CONFLICT, RepairOutcome.ALL_CONFLICT),
        ("none", SearchOutcome.NO_ALTERNATIVES, RepairOutcome.NO_ALTERNATIVES),
        ("mixed", SearchOutcome.SCHEDULE_UNKNOWN, RepairOutcome.SCHEDULE_UNKNOWN),
    ],
)
def test_no_confirmed_alternative_has_specific_internal_reason(
    kind: str, search_outcome: SearchOutcome, repair_outcome: RepairOutcome
) -> None:
    original, schedule = _case()
    candidates = {
        "unknown": [_offering("unknown", unknown=True)],
        "conflict": [_offering("conflicting")],
        "none": [original],
        "mixed": [_offering("conflicting"), _offering("unknown", unknown=True)],
    }[kind]
    result = repair_target_section(**_args(candidates, schedule))
    assert result.outcome is repair_outcome
    assert result.search.outcome is search_outcome
    assert result.search.clear_candidates == ()
    assert list(result.new_schedule) == schedule
    assert result.changes == ()
    assert result.reason
    assert "infeasible" not in result.reason
    assert not hasattr(result, "status")


@pytest.mark.parametrize("choice", ["unknown", "conflicting"])
def test_specifying_rejected_candidate_never_falls_back_to_clear(choice: str) -> None:
    _, schedule = _case()
    offerings = [
        _offering("clear", 3), _offering("unknown", unknown=True),
        _offering("conflicting"),
    ]
    result = repair_target_section(
        **_args(offerings, schedule), replacement_class_id=choice
    )
    assert result.outcome is RepairOutcome.REJECTED_SELECTION
    assert list(result.new_schedule) == schedule
    assert result.changes == ()
    expected_reason = "人工核验" if choice == "unknown" else "已知时间冲突"
    assert expected_reason in result.reason


def test_only_unknown_explicitly_selected_is_not_applied() -> None:
    _, schedule = _case()
    result = repair_target_section(
        **_args([_offering("unknown", unknown=True)], schedule),
        replacement_class_id="unknown",
    )
    assert result.outcome is RepairOutcome.REJECTED_SELECTION
    assert result.search.outcome is SearchOutcome.SCHEDULE_UNKNOWN
    assert result.changes == ()


@pytest.mark.parametrize("choice", ["not-found", "original", "wrong-course", "wrong-term"])
def test_choice_must_be_same_course_same_term_other_section(choice: str) -> None:
    original, schedule = _case()
    offerings = [
        original, _offering("clear", 3),
        _offering("wrong-course", 3, course_id="mock-other"),
        _offering("wrong-term", 3, semester="2026-2"),
    ]
    with pytest.raises(ValueError, match="指定班号"):
        repair_target_section(**_args(offerings, schedule), replacement_class_id=choice)


def test_original_removed_before_comparing_candidate() -> None:
    original = _offering("original")
    # 候选和原班时间相同，但原班会被替换，不能让原班阻挡候选。
    candidate = _offering("clear")
    schedule = [original, _offering("other", 2, course_id="mock-other")]
    search = find_alternative_sections(**_args([original, candidate], schedule))
    assert _ids(search.clear_candidates) == ["clear"]
    assert search.original_state is ConflictState.CLEAR


def test_repair_can_use_candidate_overlapping_only_the_removed_original() -> None:
    original = _offering("original")
    blocker = _offering("blocker", course_id="mock-other")
    blocker.meetings = [_meeting(1, start=4, end=5)]
    candidate = _offering("clear")
    candidate.meetings = [_meeting(1, start=3, end=3)]
    # 原班 3-4 节与 blocker 4-5 节冲突；替代班仅 3 节，必须允许替换。
    result = repair_target_section(
        **_args([candidate], [original, blocker]), replacement_class_id="clear"
    )
    assert result.search.original_state is ConflictState.CONFLICT
    assert result.outcome is RepairOutcome.REPLACED
    assert _ids(result.new_schedule) == ["clear", "blocker"]


def test_removal_uses_full_identity_not_just_class_id() -> None:
    original = _offering("original")
    same_id_other_course = _offering("original", course_id="mock-other")
    schedule = [original, same_id_other_course]
    search = find_alternative_sections(**_args([_offering("alternative")], schedule))
    assert search.original_state is ConflictState.CONFLICT
    assert len(search.conflicting_candidates) == 1
    assert search.clear_candidates == ()


def test_original_need_not_be_in_offerings_and_schedule_is_authoritative() -> None:
    original, schedule = _case()
    contradictory_original = original.model_copy(deep=True)
    contradictory_original.meetings = [_meeting(7)]
    args = _args([contradictory_original, _offering("clear", 3)], schedule)
    assert find_alternative_sections(**args).original_state is ConflictState.CONFLICT
    args["offerings"] = [_offering("clear", 3)]
    assert find_alternative_sections(**args).original_state is ConflictState.CONFLICT


def test_filters_course_and_semester_without_reordering() -> None:
    original, schedule = _case()
    offerings = [
        _offering("irrelevant", 3, course_id="mock-other"),
        _offering("clear", 3, semester="2026-2"),
        _offering("z", 5), original, _offering("a", 3),
    ]
    search = find_alternative_sections(**_args(offerings, schedule))
    assert _ids(search.clear_candidates) == ["z", "a"]
    assert [item.offering.class_id for item in search.candidates] == ["z", "a"]


def test_unknown_original_can_be_replaced_by_explicit_clear_without_false_conflict_claim() -> None:
    original = _offering("original", unknown=True)
    schedule = [original, _offering("other", 1, course_id="mock-other")]
    result = repair_target_section(
        **_args([_offering("clear", 3)], schedule), replacement_class_id="clear"
    )
    assert result.search.original_state is ConflictState.UNKNOWN
    assert result.outcome is RepairOutcome.REPLACED
    assert "原班排课信息未知" in result.reason
    assert "存在已知时间冲突" not in result.reason
    assert result.changes[0].reason == result.reason


def test_unknown_original_is_not_automatically_replaced() -> None:
    schedule = [_offering("original", unknown=True)]
    result = repair_target_section(**_args([_offering("clear", 3)], schedule))
    assert result.outcome is RepairOutcome.SELECTION_REQUIRED
    assert list(result.new_schedule) == schedule


def test_remaining_unknown_prevents_known_candidate_from_being_certified() -> None:
    schedule = [_offering("original"), _offering("other", course_id="mock-other", unknown=True)]
    result = repair_target_section(
        **_args([_offering("known", 3)], schedule), replacement_class_id="known"
    )
    assert result.search.original_state is ConflictState.UNKNOWN
    assert result.search.unknown_candidates[0].state is ConflictState.UNKNOWN
    assert "剩余课表" in result.search.unknown_candidates[0].reason
    assert result.outcome is RepairOutcome.REJECTED_SELECTION


def test_unknown_reason_covers_candidate_and_remaining_schedule() -> None:
    schedule = [
        _offering("original"),
        _offering("other", course_id="mock-other", unknown=True),
    ]
    search = find_alternative_sections(
        **_args([_offering("unknown", unknown=True)], schedule)
    )
    reason = search.unknown_candidates[0].reason
    assert "该候选" in reason
    assert "剩余课表" in reason
    assert "没有可用排课信息" in reason
    assert "尚未排课" not in reason


def test_known_conflict_overrides_remaining_unknown() -> None:
    _, schedule = _case()
    schedule.insert(0, _offering("unknown-current", course_id="mock-unknown", unknown=True))
    search = find_alternative_sections(**_args([_offering("conflicting")], schedule))
    assert search.original_state is ConflictState.CONFLICT
    assert search.outcome is SearchOutcome.ALL_CONFLICT
    assert search.conflicting_candidates[0].state is ConflictState.CONFLICT


def test_candidate_second_meeting_conflict_is_not_missed() -> None:
    _, schedule = _case()
    candidate = _offering("candidate", 3)
    candidate.meetings.append(_meeting(1))
    search = find_alternative_sections(**_args([candidate], schedule))
    assert search.outcome is SearchOutcome.ALL_CONFLICT
    assert search.clear_candidates == ()


def test_remaining_course_second_meeting_conflict_is_not_missed() -> None:
    original = _offering("original")
    other = _offering("other", 2, course_id="mock-other")
    other.meetings.append(_meeting(3))
    search = find_alternative_sections(**_args([_offering("candidate", 3)], [original, other]))
    assert search.conflicting_candidates[0].state is ConflictState.CONFLICT


def test_repair_does_not_claim_other_courses_mutually_clear() -> None:
    _, schedule = _case()
    schedule.append(_offering("another-blocker", course_id="mock-another"))
    result = repair_target_section(
        **_args([_offering("clear", 3)], schedule), replacement_class_id="clear"
    )
    assert result.outcome is RepairOutcome.REPLACED
    assert _ids(result.new_schedule)[-1] == "another-blocker"
    assert "整体可行" not in result.reason
    assert not hasattr(result, "status")


@pytest.mark.parametrize("operation", [find_alternative_sections, repair_target_section])
def test_empty_offerings_are_allowed(operation) -> None:
    _, schedule = _case()
    result = operation(**_args([], schedule))
    assert result.outcome.value == "no_alternatives"


@pytest.mark.parametrize("operation", [find_alternative_sections, repair_target_section])
def test_empty_schedule_cannot_identify_a_target(operation) -> None:
    with pytest.raises(ValueError, match="恰好出现一次"):
        operation(**_args([_offering("clear", 3)], []))


@pytest.mark.parametrize("operation", [find_alternative_sections, repair_target_section])
@pytest.mark.parametrize("bad_schedule", ["missing", "other-semester", "duplicate"])
def test_invalid_target_or_schedule_reports_error(operation, bad_schedule: str) -> None:
    _, schedule = _case()
    if bad_schedule == "missing":
        schedule.pop(1)
    elif bad_schedule == "other-semester":
        schedule[0].semester = "2026-2"
    else:
        schedule.append(schedule[1].model_copy(deep=True))
    with pytest.raises(ValueError):
        operation(**_args([_offering("clear", 3)], schedule))


@pytest.mark.parametrize("operation", [find_alternative_sections, repair_target_section])
def test_duplicate_candidate_identity_is_not_silently_deduplicated(operation) -> None:
    _, schedule = _case()
    candidate = _offering("clear", 3)
    with pytest.raises(ValueError, match="重复"):
        operation(**_args([candidate, candidate.model_copy(deep=True)], schedule))


@pytest.mark.parametrize("operation", [find_alternative_sections, repair_target_section])
@pytest.mark.parametrize("field", ["course_id", "current_class_id", "semester"])
@pytest.mark.parametrize("bad", [None, "", 123])
def test_invalid_identifier(operation, field: str, bad: object) -> None:
    _, schedule = _case()
    args = _args([], schedule)
    args[field] = bad
    with pytest.raises((TypeError, ValueError), match=field):
        operation(**args)


@pytest.mark.parametrize("field", ["offerings", "current_schedule"])
@pytest.mark.parametrize("bad", [None, {}, "wrong", [{}]])
def test_invalid_sequences_or_items(field: str, bad: object) -> None:
    _, schedule = _case()
    args = _args([], schedule)
    args[field] = bad
    with pytest.raises(TypeError, match=field):
        find_alternative_sections(**args)


@pytest.mark.parametrize("bad", ["", 123])
def test_invalid_replacement_identifier(bad: object) -> None:
    _, schedule = _case()
    with pytest.raises((TypeError, ValueError), match="replacement_class_id"):
        repair_target_section(**_args([], schedule), replacement_class_id=bad)


@pytest.mark.parametrize("location", ["original", "current", "candidate"])
def test_reversed_sections_rejected_even_when_original_unknown(location: str) -> None:
    original, schedule = _case()
    candidate = _offering("clear", 3)
    original.meetings = []
    target = {"original": original, "current": schedule[0], "candidate": candidate}[location]
    target.meetings = [_meeting(3, start=5, end=3)]
    with pytest.raises(ValueError, match="end_section"):
        repair_target_section(**_args([candidate], schedule), replacement_class_id="clear")


def test_mutated_model_fields_are_revalidated() -> None:
    _, schedule = _case()
    candidate = _offering("clear", 3)
    candidate.meetings[0].weeks = []
    with pytest.raises(ValidationError):
        find_alternative_sections(**_args([candidate], schedule))


def test_inputs_and_returned_search_are_isolated() -> None:
    original, schedule = _case()
    offerings = [original, _offering("clear", 3), _offering("unknown", unknown=True)]
    before = deepcopy((offerings, schedule))
    result = find_alternative_sections(**_args(offerings, schedule))
    assert (offerings, schedule) == before
    result.clear_candidates[0].meetings[0].weeks.append(99)
    result.unknown_candidates[0].offering.meetings.append(_meeting(7))
    assert (offerings, schedule) == before


@pytest.mark.parametrize(
    "kind", ["replaced", "clear", "rejected", "no-choice", "no-alternative"]
)
def test_all_repair_paths_preserve_inputs_and_isolate_outputs(kind: str) -> None:
    original, schedule = _case()
    offerings = [original, _offering("clear", 3), _offering("unknown", unknown=True)]
    choice = "clear"
    if kind == "clear":
        original.meetings = [_meeting(7)]
    elif kind == "rejected":
        choice = "unknown"
    elif kind == "no-choice":
        choice = None
    elif kind == "no-alternative":
        choice = None
        offerings = [original]
    before = deepcopy((offerings, schedule))
    result = repair_target_section(**_args(offerings, schedule), replacement_class_id=choice)
    assert (offerings, schedule) == before
    result.new_schedule[0].meetings[0].weeks.append(99)
    if result.search.clear_candidates:
        result.search.clear_candidates[0].meetings[0].weeks.append(88)
    assert (offerings, schedule) == before
    if kind == "replaced":
        assert 88 not in result.new_schedule[1].meetings[0].weeks


def test_repair_reassesses_current_inputs_instead_of_trusting_old_search() -> None:
    _, schedule = _case()
    candidate = _offering("clear", 3)
    args = _args([candidate], schedule)
    assert find_alternative_sections(**args).clear_candidates
    candidate.meetings = [_meeting(1)]
    result = repair_target_section(**args, replacement_class_id="clear")
    assert result.outcome is RepairOutcome.REJECTED_SELECTION
    assert result.changes == ()


def test_search_accepts_tuple_inputs() -> None:
    _, schedule = _case()
    args = _args([], schedule)
    args["offerings"] = (_offering("clear", 3),)
    args["current_schedule"] = tuple(schedule)
    result = find_alternative_sections(**args)
    assert _ids(result.clear_candidates) == ["clear"]
