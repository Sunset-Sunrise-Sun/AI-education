"""纯时间冲突检测：CONFLICT > UNKNOWN > CLEAR。

输入为已经通过公共模型校验的 CourseOffering；调用方提供同学期数据。
只比较周内时间，不计算通勤、学分、偏好或选班，也不生成 PlanResult。
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from app.models.contracts import CourseOffering, Meeting


class ConflictState(str, Enum):
    """Planner 内部状态；调用方应显式比较枚举，不能当作布尔值使用。"""

    CONFLICT = "CONFLICT"
    CLEAR = "CLEAR"
    UNKNOWN = "UNKNOWN"


def _validate_offering(offering: CourseOffering) -> None:
    if not isinstance(offering, CourseOffering):
        raise TypeError("冲突检测输入必须是已校验的 CourseOffering 教学班对象。")
    # 公共模型未比较两个字段的大小；沿用 Course Data 对倒置节次的拒绝规则。
    for meeting in offering.meetings:
        if meeting.end_section < meeting.start_section:
            raise ValueError(
                "节次区间非法：end_section 不能小于 start_section。"
            )


def _meetings_conflict(left: Meeting, right: Meeting) -> bool:
    return (
        left.weekday == right.weekday
        and not set(left.weeks).isdisjoint(right.weeks)
        and left.start_section <= right.end_section
        and right.start_section <= left.end_section
    )


def _compare_offerings(
    left: CourseOffering, right: CourseOffering
) -> ConflictState:
    for left_meeting in left.meetings:
        for right_meeting in right.meetings:
            if _meetings_conflict(left_meeting, right_meeting):
                return ConflictState.CONFLICT
    if not left.meetings or not right.meetings:
        return ConflictState.UNKNOWN
    return ConflictState.CLEAR


def check_conflict(
    offering_a: CourseOffering, offering_b: CourseOffering
) -> ConflictState:
    """比较两个教学班的全部 Meeting；节次为包含首尾的整数区间。

    meetings=[] 仅表示时间未知。非法对象或倒置节次明确报错，不转为三态。
    本函数不按课程号/教学班号跳过任何输入，也不修改输入。
    """
    _validate_offering(offering_a)
    _validate_offering(offering_b)
    return _compare_offerings(offering_a, offering_b)


def check_schedule_conflict(
    offering: CourseOffering, current_schedule: Sequence[CourseOffering]
) -> ConflictState:
    """比较一个教学班与当前课表；不检查课表成员之间的相互冲突。

    已知冲突优先于未知；unknown 不能导致提前跳过后续已知冲突。
    空课表时，已知教学班返回 CLEAR；未知教学班仍返回 UNKNOWN。
    调用方提供实际需要比较的课表，不在这里按 ID 排除或筛选教学班。
    """
    _validate_offering(offering)
    if not isinstance(current_schedule, Sequence) or isinstance(
        current_schedule, (str, bytes)
    ):
        raise TypeError("current_schedule 必须是 CourseOffering 教学班对象序列。")
    for current in current_schedule:
        _validate_offering(current)

    result = ConflictState.CLEAR if offering.meetings else ConflictState.UNKNOWN
    for current in current_schedule:
        state = _compare_offerings(offering, current)
        if state is ConflictState.CONFLICT:
            return state
        if state is ConflictState.UNKNOWN:
            result = state
    return result
