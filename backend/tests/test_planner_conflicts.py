"""Planner 三态冲突检测；案例均为人工合成 Mock，不包含真实教务数据。"""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models.contracts import CourseOffering, Meeting
from app.planner import ConflictState, check_conflict, check_schedule_conflict


def _meeting(
    weekday: int = 1,
    start: int = 3,
    end: int = 4,
    weeks: tuple[int, ...] = (1, 2, 3),
) -> Meeting:
    return Meeting(
        weekday=weekday, start_section=start, end_section=end, weeks=list(weeks)
    )


def _offering(*meetings: Meeting) -> CourseOffering:
    return CourseOffering(
        course_id="mock-course",
        course_name="Mock 测试课程",
        class_id="mock-class",
        semester="2026-1",
        meetings=list(meetings),
        data_source="mock",
    )


@pytest.mark.parametrize(
    ("right", "expected"),
    [
        (_meeting(start=4, end=5), ConflictState.CONFLICT),
        (_meeting(weekday=2), ConflictState.CLEAR),
        (_meeting(weeks=(4, 5)), ConflictState.CLEAR),
        (_meeting(start=5, end=6), ConflictState.CLEAR),
        (_meeting(start=1, end=2), ConflictState.CLEAR),
        (_meeting(start=1, end=3), ConflictState.CONFLICT),
        (_meeting(start=4, end=4), ConflictState.CONFLICT),
        (_meeting(start=3, end=3), ConflictState.CONFLICT),
        (_meeting(start=1, end=8), ConflictState.CONFLICT),
        (_meeting(weeks=(3, 8)), ConflictState.CONFLICT),
        (_meeting(weeks=(3, 1)), ConflictState.CONFLICT),
        (_meeting(weeks=(4, 6, 8)), ConflictState.CLEAR),
    ],
)
def test_known_pairs(right: Meeting, expected: ConflictState) -> None:
    left_offering, right_offering = _offering(_meeting()), _offering(right)
    assert check_conflict(left_offering, right_offering) is expected
    assert check_conflict(right_offering, left_offering) is expected


@pytest.mark.parametrize(
    "left_known,right_known", [(True, False), (False, True), (False, False)]
)
def test_empty_meetings_are_unknown(left_known: bool, right_known: bool) -> None:
    left = _offering(_meeting()) if left_known else _offering()
    right = _offering(_meeting()) if right_known else _offering()
    assert check_conflict(left, right) is ConflictState.UNKNOWN


def test_conflict_only_between_second_meetings() -> None:
    left = _offering(_meeting(weekday=1), _meeting(weekday=3, weeks=(5, 7)))
    right = _offering(_meeting(weekday=2), _meeting(weekday=3, weeks=(7, 9)))
    assert check_conflict(left, right) is ConflictState.CONFLICT
    assert check_conflict(right, left) is ConflictState.CONFLICT


def test_all_known_meeting_pairs_clear() -> None:
    left = _offering(_meeting(weekday=1), _meeting(weekday=3, weeks=(1, 3, 5)))
    right = _offering(_meeting(weekday=2), _meeting(weekday=3, weeks=(2, 4, 6)))
    assert check_conflict(left, right) is ConflictState.CLEAR


@pytest.mark.parametrize("unknown_first", [True, False])
def test_unknown_and_known_clear_schedule(unknown_first: bool) -> None:
    schedule = [_offering(), _offering(_meeting(weekday=2))]
    if not unknown_first:
        schedule.reverse()
    assert (
        check_schedule_conflict(_offering(_meeting()), schedule)
        is ConflictState.UNKNOWN
    )


@pytest.mark.parametrize("unknown_first", [True, False])
def test_conflict_overrides_unknown_schedule(unknown_first: bool) -> None:
    schedule = [_offering(), _offering(_meeting())]
    if not unknown_first:
        schedule.reverse()
    assert (
        check_schedule_conflict(_offering(_meeting()), schedule)
        is ConflictState.CONFLICT
    )


def test_schedule_checks_later_meetings() -> None:
    schedule = [_offering(), _offering(_meeting(weekday=2), _meeting())]
    assert (
        check_schedule_conflict(_offering(_meeting()), schedule)
        is ConflictState.CONFLICT
    )


def test_known_schedule_clear() -> None:
    schedule = (
        _offering(_meeting(weekday=2)), _offering(_meeting(start=7, end=8))
    )
    assert check_schedule_conflict(_offering(_meeting()), schedule) is ConflictState.CLEAR


def test_unknown_candidate_against_known_schedule() -> None:
    assert (
        check_schedule_conflict(_offering(), [_offering(_meeting())])
        is ConflictState.UNKNOWN
    )


@pytest.mark.parametrize(
    "known,expected", [(True, ConflictState.CLEAR), (False, ConflictState.UNKNOWN)]
)
def test_empty_current_schedule(known: bool, expected: ConflictState) -> None:
    candidate = _offering(_meeting()) if known else _offering()
    assert check_schedule_conflict(candidate, []) is expected


def test_schema_boundaries_sunday_single_section_and_week() -> None:
    # Schema 没有节次/周次上限，不擅自加入“最多 12 节/16 周”的限制。
    left = _offering(_meeting(weekday=7, start=20, end=20, weeks=(30,)))
    right = _offering(_meeting(weekday=7, start=20, end=21, weeks=(30, 31)))
    assert check_conflict(left, right) is ConflictState.CONFLICT


def test_location_not_part_of_time_conflict() -> None:
    left, right = _offering(_meeting()), _offering(_meeting())
    left.meetings[0].campus = "Mock 校区 A"
    right.meetings[0].campus = "Mock 校区 B"
    assert check_conflict(left, right) is ConflictState.CONFLICT


def test_inputs_are_not_modified() -> None:
    candidate = _offering(_meeting(weeks=(3, 1, 2)))
    schedule = [_offering(), _offering(_meeting(weekday=2))]
    before = deepcopy((candidate, schedule))
    check_conflict(candidate, schedule[1])
    check_schedule_conflict(candidate, schedule)
    assert (candidate, schedule) == before


@pytest.mark.parametrize(
    "fields",
    [
        {"weekday": 0}, {"weekday": 8}, {"start_section": 0},
        {"end_section": 0}, {"weeks": []}, {"weeks": [0]},
        {"weeks": [1, 1]}, {"weeks": None},
    ],
)
def test_invalid_meeting_rejected_by_existing_model(fields: dict) -> None:
    payload = _meeting().model_dump()
    payload.update(fields)
    with pytest.raises(ValidationError):
        Meeting.model_validate(payload)


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_null_meetings_not_treated_as_unknown(missing: bool) -> None:
    payload = _offering().model_dump()
    if missing:
        del payload["meetings"]
    else:
        payload["meetings"] = None
    with pytest.raises(ValidationError):
        CourseOffering.model_validate(payload)


@pytest.mark.parametrize("bad", [None, {}, []])
def test_wrong_pair_input_type(bad: object) -> None:
    with pytest.raises(TypeError, match="CourseOffering"):
        check_conflict(bad, _offering(_meeting()))
    with pytest.raises(TypeError, match="CourseOffering"):
        check_conflict(_offering(_meeting()), bad)


@pytest.mark.parametrize("bad_schedule", [None, {}, "invalid", [None]])
def test_wrong_schedule_input_type(bad_schedule: object) -> None:
    with pytest.raises(TypeError, match="CourseOffering"):
        check_schedule_conflict(_offering(_meeting()), bad_schedule)


def test_reversed_section_range_rejected_even_with_unknown() -> None:
    invalid = _offering(_meeting(start=5, end=3))
    with pytest.raises(ValueError, match="end_section"):
        check_conflict(_offering(), invalid)
    with pytest.raises(ValueError, match="end_section"):
        check_conflict(invalid, _offering())
    with pytest.raises(ValueError, match="end_section"):
        check_schedule_conflict(_offering(), [invalid])


def test_invalid_schedule_member_not_hidden_by_early_conflict() -> None:
    candidate = _offering(_meeting())
    invalid = _offering(_meeting(start=5, end=3))
    with pytest.raises(ValueError, match="end_section"):
        check_schedule_conflict(candidate, [_offering(_meeting()), invalid])
