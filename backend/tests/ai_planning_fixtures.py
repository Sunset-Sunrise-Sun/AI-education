"""AI Planning Controller 测试夹具（**全部为人工构造的 Mock**）。

> ⚠️ 这里的教学班、补修任务与方案**全部是合成对象**，不是学校真实开课数据，
> 也不是任何真实学生的材料。`data_source="mock"` 一等一标注。

夹具刻意做成"一位学生 + 三门补修课 + 一个冲突/可行的班次集合"，
以便覆盖：正常意图→确认→求解、未确认不求解、锁定课程、
模糊学分、未知课程、快照过期、模型不可用、无教学班、结果无法满足。
"""

from __future__ import annotations

from app.models.contracts import (
    CourseOffering,
    DataSource,
    MakeupStatus,
    MakeupTask,
    Meeting,
    PlanResult,
    PlanStatus,
    Preference,
    SelectedClass,
)

SEMESTER = "2026-1"

#: 三门补修课：一门已选（数据结构），两门待补（算法、网络）。
DS_COURSE = "DS101"
ALGO_COURSE = "ALGO201"
NET_COURSE = "NET301"

#: 班级号（夹具内固定，便于断言）。
DS_CLASS = "ds-01"
DS_ALT_CLASS = "ds-02"
ALGO_CLASS = "algo-01"
ALGO_ALT_CLASS = "algo-02"
NET_CLASS = "net-01"


def meeting(weekday: int, start: int = 1, end: int = 2, weeks: list[int] | None = None) -> Meeting:
    return Meeting(weekday=weekday, start_section=start, end_section=end, weeks=weeks or [1, 3])


def offering(
    course_id: str,
    class_id: str,
    *,
    weekday: int,
    credit: float | None = 3.0,
    meetings: bool = True,
    data_source: DataSource = DataSource.MOCK,
    start: int = 1,
    end: int = 2,
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=f"Mock {course_id}",
        class_id=class_id,
        semester=SEMESTER,
        credit=credit,
        meetings=[meeting(weekday, start, end)] if meetings else [],
        data_source=data_source,
    )


def makeup_task(
    course_id: str,
    *,
    credit: float = 3.0,
    status: MakeupStatus = MakeupStatus.REQUIRED,
    prerequisites: list[str] | None = None,
    recommended_semester: int | None = None,
) -> MakeupTask:
    return MakeupTask(
        course_id=course_id,
        course_name=f"Mock {course_id}",
        credit=credit,
        status=status,
        prerequisites=prerequisites or [],
        recommended_semester=recommended_semester,
    )


def makeup_tasks() -> list[MakeupTask]:
    """三门补修任务：数据结构（必修）、算法（必修）、网络（待人工确认）。"""

    return [
        makeup_task(DS_COURSE, credit=3.0),
        makeup_task(ALGO_COURSE, credit=3.0),
        makeup_task(NET_COURSE, credit=2.0, status=MakeupStatus.MANUAL_CONFIRMATION),
    ]


def offerings() -> list[CourseOffering]:
    """可用教学班：数据结构两个班（周一 / 周三），算法两个班，网络一个班。

    刻意让 `ALGO_CLASS` 与当前已选的 `DS_CLASS` **同一时段**（周一 1-2 节），
    这样"唯一 CLEAR 新增"的判定是确定性的、可断言的。
    """

    return [
        offering(DS_COURSE, DS_CLASS, weekday=1),
        offering(DS_COURSE, DS_ALT_CLASS, weekday=3),
        offering(ALGO_COURSE, ALGO_CLASS, weekday=1),      # 与 DS_CLASS 冲突
        offering(ALGO_COURSE, ALGO_ALT_CLASS, weekday=2),  # 唯一 CLEAR
        offering(NET_COURSE, NET_CLASS, weekday=4, credit=2.0),
    ]


def base_plan() -> PlanResult:
    """当前方案：已选数据结构，补修任务尚未加入。"""

    return PlanResult(
        status=PlanStatus.PARTIALLY_FEASIBLE,
        selected_classes=[SelectedClass(course_id=DS_COURSE, class_id=DS_CLASS)],
        changes=[],
        risks=[],
        unresolved=[],
        objective_summary="Mock 基线方案：仅保留已选的数据结构班。",
    )


def preference(*, max_credit: float | None = None) -> Preference:
    return Preference(max_credit=max_credit)


def context_payload(*, include_offerings: bool = True, max_credit: float | None = None) -> dict:
    """`POST /interpret` 的 `context` 字段（JSON 形状）。"""

    return {
        "semester": SEMESTER,
        "base_plan": base_plan().model_dump(mode="json"),
        "makeup_tasks": [task.model_dump(mode="json") for task in makeup_tasks()],
        "course_offerings": (
            [item.model_dump(mode="json") for item in offerings()] if include_offerings else []
        ),
        "preference": preference(max_credit=max_credit).model_dump(mode="json"),
    }


def confirm_payload(
    *,
    plan_digest: str,
    max_credit: float | None = None,
    evidence: str | None = "学生明确说了 6 学分",
    locked: bool = False,
    weekday: int | None = None,
) -> dict:
    """`POST /solve` 的 `confirmed_intent` 字段（用户在确认面板回传的形状）。"""

    hard: list[dict] = []
    soft: list[dict] = []
    locks: list[dict] = []
    if max_credit is not None:
        hard.append({"kind": "max_credit_limit", "value": max_credit, "evidence": evidence})
    if weekday is not None:
        soft.append({"kind": "avoid_weekday", "value": weekday, "note": "尽量避开该天"})
    if locked:
        locks.append({
            "course_id": DS_COURSE, "class_id": DS_CLASS, "reason": "学生要求保留数据结构",
        })
    return {
        "plan_digest": plan_digest,
        "semester": SEMESTER,
        "scope": "current_semester",
        "target_semester": SEMESTER,
        "hard_constraints": hard,
        "soft_preferences": soft,
        "locked_courses": locks,
        "user_note": None,
    }
