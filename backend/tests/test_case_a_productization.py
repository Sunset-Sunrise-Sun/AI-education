"""人工验收产品化修整 —— 后端必测项（学分上限 + 本学期选修建议 + 负荷）。

对应任务书第 7 / 8 / 9 / 15 节中属于**后端**的部分：

- 未来学期**任何**学期都不得超过硬上限（真实数据曾出现 53.5 / 103 学分）；
- 用户 `Preference.max_credit` 优先，但⛔ 不得突破产品硬上限；
- 排不下时顺延；实在排不下 ⇒ unresolved，⛔ 不产出超限学期；
- 本学期选修建议只来自"选修组成员 ∩ 已接受教学班"的**精确 course_id**；
- 非成员 ⛔ 不得出现；排课信息未知必须如实标为不确定，⛔ 不得说成 CLEAR。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.curriculum.case import load_curriculum_case
from app.models.contracts import CourseOffering, DataSource, Meeting
from app.services.case_a_roadmap import (
    CASE_A_CURRENT_HARD_MAX_CREDIT,
    CASE_A_ELECTIVE_DISPLAY_LIMIT,
    CASE_A_FUTURE_HARD_MAX_CREDIT,
    CASE_A_FUTURE_SOFT_TARGET_CREDIT,
    recommend_current_electives,
)
from app.services.case_a_roadmap import build_case_a_roadmap

from tests.test_case_a_roadmap import GROUP, _course, _payload, SEMESTER, _write


def _case(tmp_path: Path, *, courses: list[dict[str, object]]):
    return load_curriculum_case(_write(tmp_path, _payload(courses=courses)))


def _offering(
    course_id: str,
    class_id: str,
    *,
    meetings: tuple[Meeting, ...] = (),
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=f"示例 {course_id}",
        class_id=class_id,
        semester=SEMESTER,
        credit=3.0,
        meetings=list(meetings),
        data_source=DataSource.REAL,
    )


# ---------------------------------------------------------------------------
# 学分上限
# ---------------------------------------------------------------------------


def test_no_future_semester_exceeds_the_hard_max(tmp_path: Path) -> None:
    """把一门超大课程塞进一个学期 ⇒ 也不得超过硬上限（而是顺延 / unresolved）。"""

    # 3 门 × 20 学分 = 60 学分，理论上想挤进同一学期
    courses = [
        _course("BIG1", "示例大课 1", 20.0, term="2026-2"),
        _course("BIG2", "示例大课 2", 20.0, term="2026-2"),
        _course("BIG3", "示例大课 3", 20.0, term="2026-2"),
        _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
    ]
    case = _case(tmp_path, courses=courses)
    roadmap = build_case_a_roadmap(
        case, makeup_tasks=[], current_semester_label=SEMESTER, elective_group_id=None
    )
    for semester in roadmap.future_semesters:
        assert semester.total_credit <= CASE_A_FUTURE_HARD_MAX_CREDIT, (
            f"{semester.semester_label} 学分 {semester.total_credit} 超过硬上限"
        )


def test_user_max_credit_takes_priority_but_cannot_exceed_hard_max(tmp_path: Path) -> None:
    courses = [
        _course("A1", "示例课 1", 10.0, term="2026-2"),
        _course("A2", "示例课 2", 10.0, term="2026-2"),
        _course("A3", "示例课 3", 10.0, term="2026-2"),
        _course("A4", "示例课 4", 10.0, term="2027-1"),
        _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
    ]
    case = _case(tmp_path, courses=courses)

    strict = build_case_a_roadmap(
        case,
        makeup_tasks=[],
        current_semester_label=SEMESTER,
        elective_group_id=None,
        user_max_credit=10.0,
    )
    for semester in strict.future_semesters:
        assert semester.total_credit <= 10.0

    # 用户给了一个**更宽松**的上限 ⇒ 仍然被产品硬上限收口
    loose = build_case_a_roadmap(
        case,
        makeup_tasks=[],
        current_semester_label=SEMESTER,
        elective_group_id=None,
        user_max_credit=200.0,
    )
    for semester in loose.future_semesters:
        assert semester.total_credit <= CASE_A_FUTURE_HARD_MAX_CREDIT


def test_default_policy_constants(tmp_path: Path) -> None:
    """产品级默认：未来软目标 26 / 未来硬上限 35；当前学期上限 30（⛔ 两者不同）。"""

    assert CASE_A_FUTURE_SOFT_TARGET_CREDIT == 26.0
    assert CASE_A_FUTURE_HARD_MAX_CREDIT == 35.0
    # ⛔ 当前学期与未来学期的上限**不同**，不得混用
    assert CASE_A_CURRENT_HARD_MAX_CREDIT == 30.0
    assert CASE_A_CURRENT_HARD_MAX_CREDIT != CASE_A_FUTURE_HARD_MAX_CREDIT


def test_impossible_load_is_reported_instead_of_overfilling(tmp_path: Path) -> None:
    """4 门 × 20 学分 = 80 学分但只有 2 个可行学期（每个上限 30）⇒ 必须 unresolved。"""

    courses = [
        _course("H1", "示例超载 1", 20.0, term="2026-2"),
        _course("H2", "示例超载 2", 20.0, term="2026-2"),
        _course("H3", "示例超载 3", 20.0, term="2026-2"),
        _course("H4", "示例超载 4", 20.0, term="2026-2"),
        _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
    ]
    case = _case(tmp_path, courses=courses)
    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=[],
        current_semester_label=SEMESTER,
        elective_group_id=None,
        last_curriculum_semester="2026-2",  # 只给一个未来学期
    )
    for semester in roadmap.future_semesters:
        assert semester.total_credit <= CASE_A_FUTURE_HARD_MAX_CREDIT
    # 排不下的课必须如实出现在 unresolved，而不是被塞进学期
    assert roadmap.unresolved, "over-capacity courses must be reported, not crammed in"
    placed = set(roadmap.future_course_ids)
    assert placed != {"H1", "H2", "H3", "H4"}


def test_deferral_is_used_when_the_credit_budget_is_exceeded(tmp_path: Path) -> None:
    """单学期装不下时，课程应被**顺延**到后续学期，⛔ 不是丢进 unresolved。

    学分链覆盖 2025-1 / 2026-2 / 2027-1：
    两门 12 学分 = 24 ≤ 预算，可同放；再加一门 12 学分 ⇒ 单学期 36 > 硬上限 30，
    因此第三门必须顺延到 2027-1（⛔ 不能塞成 36，也不能丢课）。
    """

    courses = [
        _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
        # 该项让学期号链延伸到 2027-1，从而"顺延"有地方可去
        _course("FAR-1", "示例远期课", 1.0, term="2027-1"),
        _course("S1", "示例课 1", 12.0, term="2026-2"),
        _course("S2", "示例课 2", 12.0, term="2026-2"),
        _course("S3", "示例课 3", 12.0, term="2026-2"),
    ]
    case = _case(tmp_path, courses=courses)
    roadmap = build_case_a_roadmap(
        case, makeup_tasks=[], current_semester_label=SEMESTER, elective_group_id=None
    )
    # 全部课程都被安排（顺延），⛔ 没有因为学分负荷而丢课
    assert {"S1", "S2", "S3"}.issubset(set(roadmap.future_course_ids))
    # 至少用到两个学期：12×3 = 36 > 单学期硬上限 30
    used = [s.semester_label for s in roadmap.future_semesters if s.courses]
    assert len(used) >= 2
    for semester in roadmap.future_semesters:
        assert semester.total_credit <= CASE_A_FUTURE_HARD_MAX_CREDIT
    # 被顺延的课必须带"因学分负荷顺延"的既有语义（DEFERRED_FOR_CREDIT_BUDGET）
    deferred = [
        course
        for semester in roadmap.future_semesters
        for course in semester.courses
        if course.placement.value == "deferred_for_credit_budget"
    ]
    assert deferred, "a deferred course must carry the credit-budget placement reason"


# ---------------------------------------------------------------------------
# 本学期专业选修建议
# ---------------------------------------------------------------------------


def _elective_courses() -> list[dict[str, object]]:
    return [
        _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
        _course("EL-1", "示例选修 1", 3.0, term="2026-2",
                requirement="elective", group_id=GROUP),
        _course("EL-2", "示例选修 2", 3.0, term="2026-2",
                requirement="elective", group_id=GROUP),
        _course("REQ-1", "示例必修", 3.0, term="2026-2"),
    ]


def _group_records() -> list[dict[str, object]]:
    return [
        {
            "group_id": GROUP,
            "name": "示例专业选修池",
            "minimum_credit": 6.0,
            "source_record": "row:group",
        }
    ]


def test_elective_member_with_an_accepted_offering_is_recommended(tmp_path: Path) -> None:
    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    offerings = [_offering("EL-1", "01"), _offering("REQ-1", "01")]
    recs = recommend_current_electives(
        case, [], offerings, elective_group_id=GROUP, remaining_elective_credit=6.0
    )
    assert [item.course_id for item in recs] == ["EL-1"]
    # ⛔ 必修课不得出现在选修建议里
    assert "REQ-1" not in {item.course_id for item in recs}


def test_nonmember_course_is_never_recommended(tmp_path: Path) -> None:
    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    offerings = [_offering("NOT-A-MEMBER", "01"), _offering("REQ-1", "01")]
    recs = recommend_current_electives(
        case, [], offerings, elective_group_id=GROUP, remaining_elective_credit=6.0
    )
    assert recs == ()


def test_course_name_similarity_never_binds(tmp_path: Path) -> None:
    """⛔ 同名但课程号不同的课不得被当成选修成员（不按名字匹配）。"""

    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    imposter = CourseOffering(
        course_id="EL-1X",
        course_name="示例选修 1",  # 与培养方案成员完全同名
        class_id="01",
        semester=SEMESTER,
        credit=3.0,
        meetings=[],
        data_source=DataSource.REAL,
    )
    recs = recommend_current_electives(
        case, [], [imposter], elective_group_id=GROUP, remaining_elective_credit=6.0
    )
    assert recs == ()


def test_unknown_schedule_is_reported_as_uncertain_not_clear(tmp_path: Path) -> None:
    """`meetings=[]` ⇒ 排课信息待核验，⛔ 不得算作"已确认无冲突"。"""

    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    recs = recommend_current_electives(
        case,
        [],
        [_offering("EL-1", "01", meetings=())],  # meetings = []
        elective_group_id=GROUP,
        remaining_elective_credit=6.0,
    )
    assert len(recs) == 1
    item = recs[0]
    assert item.unknown_schedule_class_count == 1
    assert item.clear_class_count == 0
    assert item.unique_clear_class_id is None
    # 中文说明必须表达"不确定"，⛔ 不能说成不冲突
    assert '核验' in item.conflict_label or '未同步' in item.conflict_label
    assert '不冲突' not in item.conflict_label


def test_a_single_clear_class_is_offered_directly(tmp_path: Path) -> None:
    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    meeting = Meeting(
        weekday=1, start_section=1, end_section=2, weeks=[1, 2, 3], campus="南校园", classroom="A101"
    )
    recs = recommend_current_electives(
        case,
        [],
        [_offering("EL-1", "01", meetings=(meeting,))],
        elective_group_id=GROUP,
        remaining_elective_credit=6.0,
    )
    assert recs[0].unique_clear_class_id == "01"
    assert recs[0].clear_class_count == 1


def test_multiple_clear_classes_require_the_user_to_choose(tmp_path: Path) -> None:
    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    meeting = Meeting(
        weekday=1, start_section=1, end_section=2, weeks=[1], campus="南校园", classroom="A101"
    )
    recs = recommend_current_electives(
        case,
        [],
        [
            _offering("EL-1", "01", meetings=(meeting,)),
            _offering("EL-1", "02", meetings=(meeting,)),
        ],
        elective_group_id=GROUP,
        remaining_elective_credit=6.0,
    )
    # ⛔ 多个候选时不得替用户自动选一个
    assert recs[0].unique_clear_class_id is None
    assert recs[0].clear_class_count == 2


def test_all_elective_members_are_surfaced_not_silently_capped(tmp_path: Path) -> None:
    """⛔ 选修候选不得因为一个隐藏的显示上限而消失。

    ⚠️ 回归背景：默认上限曾经是 **3**，于是排在第 4 位之后的选修在真实 Case A 数据里
    **静默消失**（正是 CSE335 数据库系统原理 / CSE337 数据库系统实验）。
    产品要求是"要么可见、要么可达"，因此默认上限必须覆盖真实选修池规模，
    前端只做**可见的**渐进披露（查看更多 / 筛选）。
    """

    courses = [_course("PAST-1", "示例已过必修", 2.0, term="2025-1")]
    courses += [
        _course(f"EL-{i}", f"示例选修 {i}", 3.0, term="2026-2",
                requirement="elective", group_id=GROUP)
        for i in range(1, 6)
    ]
    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=courses, groups=_group_records()))
    )
    offerings = [_offering(f"EL-{i}", "01") for i in range(1, 6)]
    recs = recommend_current_electives(
        case, [], offerings, elective_group_id=GROUP, remaining_elective_credit=15.0
    )
    # 5 门成员全部返回（⛔ 不是被截断到 3）
    assert len(recs) == 5
    assert {r.course_id for r in recs} == {f"EL-{i}" for i in range(1, 6)}
    # 默认上限足够大，不会重演"第 4 位之后被藏掉"
    assert CASE_A_ELECTIVE_DISPLAY_LIMIT >= 5


def test_explicit_max_courses_still_bounds_the_list(tmp_path: Path) -> None:
    """显式传入的 `max_courses` 仍然生效（上限本身没有被移除）。"""

    courses = [_course("PAST-1", "示例已过必修", 2.0, term="2025-1")]
    courses += [
        _course(f"EL-{i}", f"示例选修 {i}", 3.0, term="2026-2",
                requirement="elective", group_id=GROUP)
        for i in range(1, 6)
    ]
    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=courses, groups=_group_records()))
    )
    offerings = [_offering(f"EL-{i}", "01") for i in range(1, 6)]
    recs = recommend_current_electives(
        case, [], offerings, elective_group_id=GROUP, remaining_elective_credit=15.0,
        max_courses=2,
    )
    assert len(recs) == 2


def test_no_recommendation_when_nothing_is_outstanding(tmp_path: Path) -> None:
    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    offerings = [_offering("EL-1", "01")]
    assert (
        recommend_current_electives(
            case, [], offerings, elective_group_id=GROUP, remaining_elective_credit=0.0
        )
        == ()
    )


def test_future_plan_absorption_does_not_hide_the_current_recommendation(tmp_path: Path) -> None:
    """⛔ 关键回归：未来学期把选修缺口排满时，本学期**仍然**要给出可选选修。

    人工验收正是看到这个：`roadmap.elective_remaining_credit == 0`（因为路线图把
    23 学分选修全排进未来学期），于是本学期选修面板静默显示 0。
    门控必须用**真实未覆盖需求**（`requirement − completed − current`），
    而不是"排完之后还剩多少"。
    """

    case = load_curriculum_case(
        _write(tmp_path, _payload(courses=_elective_courses(), groups=_group_records()))
    )
    from app.services.case_a_roadmap import build_case_a_roadmap

    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=[],
        current_semester_label=SEMESTER,
        elective_group_id=GROUP,
    )
    # 路线图确实把缺口吸收掉了……
    assert roadmap.elective_remaining_credit == 0.0
    assert roadmap.elective_planned_credit > 0.0

    # ……但真实未覆盖需求仍为正，因此本学期建议**必须**存在
    uncovered = (
        roadmap.elective_requirement_credit
        - roadmap.elective_completed_credit
        - roadmap.elective_current_semester_credit
    )
    assert uncovered > 0, "fixture must still owe elective credit"
    recs = recommend_current_electives(
        case,
        [],
        [_offering("EL-1", "01")],
        elective_group_id=GROUP,
        remaining_elective_credit=uncovered,
    )
    assert [item.course_id for item in recs] == ["EL-1"], (
        "absorbing the gap into future semesters must not hide the current-semester "
        "elective recommendation"
    )


def test_current_semester_load_uses_the_30_cap_not_the_future_35() -> None:
    """⛔ 当前学期上限 30 与未来硬上限 35 是**两个**阈值，不得混用。"""

    from app.services.case_a_roadmap import current_semester_load

    load = current_semester_load(
        current_schedule=[],
        planned_course_ids=[],
        credit_by_course_id={},
        recommendations=(),
        user_max_credit=None,
    )
    assert load.max_credit == CASE_A_CURRENT_HARD_MAX_CREDIT == 30.0

    # 用户更低的上限优先
    strict = current_semester_load(
        current_schedule=[],
        planned_course_ids=[],
        credit_by_course_id={},
        recommendations=(),
        user_max_credit=18.0,
    )
    assert strict.max_credit == 18.0

    # 用户给更高值 ⇒ 仍被当前学期上限收口（⛔ 不得借用未来的 35）
    loose = current_semester_load(
        current_schedule=[],
        planned_course_ids=[],
        credit_by_course_id={},
        recommendations=(),
        user_max_credit=40.0,
    )
    assert loose.max_credit == 30.0
