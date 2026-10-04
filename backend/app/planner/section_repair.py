"""Planner 内部的替代班搜索与单目标换班。

只确认目标班与剩余课表的时间关系，不代表整张课表或学业方案可行。
输入不被修改，返回的 CourseOffering 为深拷贝；无网络、Provider 或选班评分。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.models.contracts import Change, CourseOffering
from app.planner.conflicts import ConflictState, check_schedule_conflict


class SearchOutcome(str, Enum):
    """仅描述当前输入中的候选搜索，不是 PlanResult.status。"""

    CLEAR_AVAILABLE = "clear_available"
    NO_ALTERNATIVES = "no_alternatives"
    SCHEDULE_UNKNOWN = "schedule_unknown"
    ALL_CONFLICT = "all_conflict"


class RepairOutcome(str, Enum):
    """单目标换班内部结果，不表达完整规划可行性。"""

    ORIGINAL_CLEAR = "original_clear"
    SELECTION_REQUIRED = "selection_required"
    REPLACED = "replaced"
    NO_ALTERNATIVES = "no_alternatives"
    SCHEDULE_UNKNOWN = "schedule_unknown"
    ALL_CONFLICT = "all_conflict"
    REJECTED_SELECTION = "rejected_selection"


@dataclass(frozen=True)
class CandidateAssessment:
    offering: CourseOffering
    state: ConflictState
    reason: str


@dataclass(frozen=True)
class AlternativeSearchResult:
    """候选保持来源顺序；UNKNOWN / CONFLICT 同样保留供解释与核验。"""

    original_state: ConflictState
    candidates: tuple[CandidateAssessment, ...]
    outcome: SearchOutcome
    reason: str

    @property
    def clear_candidates(self) -> tuple[CourseOffering, ...]:
        return tuple(
            candidate.offering
            for candidate in self.candidates
            if candidate.state is ConflictState.CLEAR
        )

    @property
    def unknown_candidates(self) -> tuple[CandidateAssessment, ...]:
        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.state is ConflictState.UNKNOWN
        )

    @property
    def conflicting_candidates(self) -> tuple[CandidateAssessment, ...]:
        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.state is ConflictState.CONFLICT
        )


@dataclass(frozen=True)
class SectionRepairResult:
    new_schedule: tuple[CourseOffering, ...]
    changes: tuple[Change, ...]
    search: AlternativeSearchResult
    outcome: RepairOutcome
    reason: str


def _validate_identifier(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} 必须是非空字符串。")
    if not value:
        raise ValueError(f"{name} 必须是非空字符串。")


def _identity(offering: CourseOffering) -> tuple[str, str, str]:
    return offering.semester, offering.course_id, offering.class_id


def _copy_offerings(
    values: Sequence[CourseOffering], name: str
) -> tuple[CourseOffering, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise TypeError(f"{name} 必须是 CourseOffering 教学班对象序列。")
    copied: list[CourseOffering] = []
    seen: set[tuple[str, str, str]] = set()
    for value in values:
        if not isinstance(value, CourseOffering):
            raise TypeError(f"{name} 中每项必须是 CourseOffering 教学班对象。")
        # 重新通过现有模型校验，同时深拷贝，包括可能被调用方修改的嵌套列表。
        offering = CourseOffering.model_validate(value.model_dump())
        # 复用第一阶段校验，包括公共模型尚未检查的倒置节次。
        check_schedule_conflict(offering, ())
        key = _identity(offering)
        if key in seen:
            raise ValueError(f"{name} 中存在重复的 (semester, course_id, class_id)。")
        seen.add(key)
        copied.append(offering)
    return tuple(copied)


def _prepare_inputs(
    course_id: str,
    current_class_id: str,
    semester: str,
    offerings: Sequence[CourseOffering],
    current_schedule: Sequence[CourseOffering],
) -> tuple[tuple[CourseOffering, ...], tuple[CourseOffering, ...], int]:
    for name, value in (
        ("course_id", course_id), ("current_class_id", current_class_id),
        ("semester", semester),
    ):
        _validate_identifier(value, name)
    available = _copy_offerings(offerings, "offerings")
    schedule = _copy_offerings(current_schedule, "current_schedule")
    if any(offering.semester != semester for offering in schedule):
        raise ValueError("current_schedule 中混入了其他学期的教学班。")
    target_key = (semester, course_id, current_class_id)
    indices = [
        i for i, offering in enumerate(schedule)
        if _identity(offering) == target_key
    ]
    if len(indices) != 1:
        raise ValueError("目标原 Section 必须在 current_schedule 中恰好出现一次。")
    return available, schedule, indices[0]


def _search(
    original: CourseOffering,
    offerings: tuple[CourseOffering, ...],
    remaining_schedule: tuple[CourseOffering, ...],
) -> AlternativeSearchResult:
    original_state = check_schedule_conflict(original, remaining_schedule)
    assessments: list[CandidateAssessment] = []
    for offering in offerings:
        if (
            offering.course_id != original.course_id
            or offering.semester != original.semester
            or offering.class_id == original.class_id
        ):
            continue
        state = check_schedule_conflict(offering, remaining_schedule)
        if state is ConflictState.CLEAR:
            reason = "该候选与移除原班后的剩余课表已确认无时间冲突。"
        elif state is ConflictState.CONFLICT:
            reason = "该候选与剩余课表存在已知时间冲突，不能用于本次换班。"
        else:
            missing: list[str] = []
            if not offering.meetings:
                missing.append("该候选在当前来源快照中没有可用排课信息")
            if any(not current.meetings for current in remaining_schedule):
                missing.append("剩余课表中有教学班没有可用排课信息")
            reason = "；".join(missing) + "，无法完成完整时间冲突确认，需要人工核验。"
        assessments.append(CandidateAssessment(offering, state, reason))

    if any(item.state is ConflictState.CLEAR for item in assessments):
        outcome = SearchOutcome.CLEAR_AVAILABLE
        reason = "存在已确认无时间冲突的替代班，需由调用方指定，不自动选择。"
    elif not assessments:
        outcome = SearchOutcome.NO_ALTERNATIVES
        reason = "当前输入中没有同课程、同学期的其他 Section。"
    elif any(item.state is ConflictState.UNKNOWN for item in assessments):
        outcome = SearchOutcome.SCHEDULE_UNKNOWN
        reason = "没有已确认无时间冲突的替代班，存在排课信息未知的候选，需要人工核验。"
    else:
        outcome = SearchOutcome.ALL_CONFLICT
        reason = "当前输入中的所有替代班均与剩余课表存在已知时间冲突。"
    return AlternativeSearchResult(original_state, tuple(assessments), outcome, reason)


def find_alternative_sections(
    *,
    course_id: str,
    current_class_id: str,
    semester: str,
    offerings: Sequence[CourseOffering],
    current_schedule: Sequence[CourseOffering],
) -> AlternativeSearchResult:
    """搜索同课程、同学期的其他教学班，不自动选择，也不改变课表。

    原班排课信息以 current_schedule 为准，原班可不在 offerings 中。
    身份重复、目标缺失或非法输入明确报错；不静默修正或去重。
    """
    available, schedule, index = _prepare_inputs(
        course_id, current_class_id, semester, offerings, current_schedule
    )
    remaining = schedule[:index] + schedule[index + 1:]
    return _search(schedule[index], available, remaining)


def repair_target_section(
    *,
    course_id: str,
    current_class_id: str,
    semester: str,
    offerings: Sequence[CourseOffering],
    current_schedule: Sequence[CourseOffering],
    replacement_class_id: str | None = None,
) -> SectionRepairResult:
    """由调用方指定 CLEAR 候选后，仅替换目标位置，保留其他教学班。

    每次基于当前输入重新评估，不能拿过期搜索结果直接换班。
    原班 CLEAR 时不替换（不使用 replacement_class_id）。原班 UNKNOWN 时允许
    明确指定 CLEAR，但原因不得称为已确认冲突。所有返回数据与输入隔离。
    """
    if replacement_class_id is not None:
        _validate_identifier(replacement_class_id, "replacement_class_id")
    available, schedule, index = _prepare_inputs(
        course_id, current_class_id, semester, offerings, current_schedule
    )
    original = schedule[index]
    remaining = schedule[:index] + schedule[index + 1:]
    search = _search(original, available, remaining)
    if search.original_state is ConflictState.CLEAR:
        return SectionRepairResult(
            schedule, (), search, RepairOutcome.ORIGINAL_CLEAR,
            "原班与剩余课表已确认无时间冲突，本次不进行替换。",
        )
    if replacement_class_id is None:
        outcome = {
            SearchOutcome.CLEAR_AVAILABLE: RepairOutcome.SELECTION_REQUIRED,
            SearchOutcome.NO_ALTERNATIVES: RepairOutcome.NO_ALTERNATIVES,
            SearchOutcome.SCHEDULE_UNKNOWN: RepairOutcome.SCHEDULE_UNKNOWN,
            SearchOutcome.ALL_CONFLICT: RepairOutcome.ALL_CONFLICT,
        }[search.outcome]
        return SectionRepairResult(schedule, (), search, outcome, search.reason)

    selected = next(
        (item for item in search.candidates
         if item.offering.class_id == replacement_class_id),
        None,
    )
    if selected is None:
        raise ValueError("指定班号不属于当前输入中的同课程、同学期替代 Section。")
    if selected.state is not ConflictState.CLEAR:
        return SectionRepairResult(
            schedule, (), search, RepairOutcome.REJECTED_SELECTION, selected.reason
        )

    if search.original_state is ConflictState.CONFLICT:
        reason = "原班与剩余课表存在已知时间冲突，按调用方指定换为已确认无时间冲突的同课程教学班。"
    else:
        reason = "原班排课信息未知，按调用方明确指定换为与剩余课表已确认无时间冲突的同课程教学班。"
    # 与 search 中的可修改模型也保持隔离，避免修改候选报告影响新课表。
    replacement = selected.offering.model_copy(deep=True)
    new_schedule = schedule[:index] + (replacement,) + schedule[index + 1:]
    change = Change(
        course_id=original.course_id,
        from_class=original.class_id,
        to_class=replacement.class_id,
        reason=reason,
    )
    return SectionRepairResult(
        new_schedule, (change,), search, RepairOutcome.REPLACED, reason
    )
