"""Path Planner Core 第一阶段测试（**纯 synthetic、零网络、零真实资产**）。

覆盖两个方向：

```text
A. 当前学期 repair_proposals
   1 conflict + 1 CLEAR alt → 有建议        2 conflict + 多个 CLEAR → 多条建议
   3 生成建议不修改课表                      4 非法显式选择 fail closed
   5 只有显式选择后才应用                    6 换课程被拒绝
   7 跨学期被拒绝                            8 应用后重新校验

B. 未来学期 future_roadmap
   9 必修课落位                             10 先修顺序
   11 截止学期被尊重                         12 建议学期作为偏好
   13 选修组最低学分被满足                   14 选修池并非全部必修
   15 选修证据不足 → unresolved              16 学期学分上限被尊重
   17 未来输出没有 class_id                  18 没有 teacher
   19 没有上课时间/校区字段                  20 未来规划不需要 Course Data

⚠️ 所有课程号 / 课程名 / 教学班号均为**人工虚构**；⛔ 不含任何真实培养方案事实
（包括不硬编码任何具体学分要求）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.requirements import (
    CurriculumCourse,
    CurriculumGroup,
    CurriculumVersion,
    RequirementKind,
)
from app.models.contracts import (
    CourseOffering,
    DataSource,
    MakeupStatus,
    MakeupTask,
    Meeting,
)
from app.path_planner import (
    FutureSemester,
    RepairApplicationStatus,
    RoadmapInputError,
    SemesterCoursePlan,
    apply_repair_proposal,
    build_academic_roadmap,
    generate_repair_proposals,
)

SEMESTER = "2026-1"

#: 未来学期标签序列（调用方显式声明；培养方案学期号由 below 的映射显式给出）。
FUTURE = ("2026-2", "2027-1", "2027-2", "2028-1")

#: 当前真实学期 `2026-1` = 培养方案第 3 学期（Case A 口径）。
#: 因此未来学期显式映射为 4/5/6/7 —— ⛔ 绝不等于"列表第 1..4 项"。
CURRENT_CURRICULUM_SEMESTER = 3
FUTURE_MAP: dict[str, int] = {
    FUTURE[0]: CURRENT_CURRICULUM_SEMESTER + 1,  # 2026-2 -> 4
    FUTURE[1]: CURRENT_CURRICULUM_SEMESTER + 2,  # 2027-1 -> 5
    FUTURE[2]: CURRENT_CURRICULUM_SEMESTER + 3,  # 2027-2 -> 6
    FUTURE[3]: CURRENT_CURRICULUM_SEMESTER + 4,  # 2028-1 -> 7
}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def meeting(
    weekday: int,
    start: int,
    end: int,
    *,
    weeks: tuple[int, ...] = (1, 2, 3),
) -> Meeting:
    return Meeting(
        weekday=weekday,
        start_section=start,
        end_section=end,
        weeks=list(weeks),
        campus="示例校区",
        classroom="示例楼101",
    )


def offering(
    course_id: str,
    class_id: str,
    *,
    semester: str = SEMESTER,
    meetings: list[Meeting] | None = None,
    course_name: str = "示例课程",
    teacher: str | None = None,
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=course_name,
        class_id=class_id,
        semester=semester,
        teacher=teacher,
        credit=3.0,
        meetings=meetings if meetings is not None else [meeting(1, 1, 2)],
        source="capture://synthetic/case-a",
        data_source=DataSource.REAL,
    )


def course(
    course_id: str,
    *,
    credit: float = 3.0,
    requirement: RequirementKind = RequirementKind.REQUIRED,
    recommended: int | None = None,
    deadline: int | None = None,
    prerequisites: tuple[str, ...] | None = None,
    group_id: str | None = None,
    name: str | None = None,
) -> CurriculumCourse:
    return CurriculumCourse(
        course_id=course_id,
        course_name=name or f"示例课程 {course_id}",
        credit=credit,
        requirement=requirement,
        source_record=f"table:2!row:{course_id}",
        group_id=group_id,
        prerequisites=prerequisites,
        recommended_semester=recommended,
        deadline_semester=deadline,
    )


def version(
    courses: list[CurriculumCourse],
    *,
    groups: tuple[CurriculumGroup, ...] = (),
    version_id: str = "synthetic-new",
) -> CurriculumVersion:
    return CurriculumVersion(
        version_id=version_id,
        major="示例目标专业",
        cohort="2025",
        source_id="case-owner-confirmed://synthetic/target-plan",
        courses=tuple(courses),
        groups=groups,
        complete=True,
        completeness_evidence="case-owner-confirmed://synthetic/target-plan/complete",
    )


def completed(course_id: str, *, credit: float = 3.0, passed: bool = True) -> CompletedCourse:
    return CompletedCourse(
        course_id=course_id,
        course_name=f"示例已修 {course_id}",
        credit=credit,
        semester="2025-1",
        passed=passed,
        course_type="公必",
        course_id_status=CourseIdStatus.CONFIRMED,
        id_match_source="case-owner-confirmed://synthetic/completed",
        source_id="case-owner-confirmed://synthetic/completed",
        source_record=f"row:{course_id}",
    )


# ===========================================================================
# A. 当前学期：repair proposals
# ===========================================================================


def current_schedule_fixture() -> tuple[list[CourseOffering], list[CourseOffering]]:
    """课表：[A(冲突), C(无冲突)]；offerings 另含 A 的两个 CLEAR 候选。

    - `A-01` 与 `C-01` 在周三 3-4 节冲突；
    - `A-02`（周三 5-6 节）与 `A-03`（周五 1-2 节）都不与剩余课表冲突 ⇒ CLEAR 候选；
    - `A-99`（周三 3-4 节）与 C 冲突 ⇒ 不可选。
    """

    schedule = [
        offering("AAA101", "A-01", meetings=[meeting(3, 3, 4)]),
        offering("CCC101", "C-01", meetings=[meeting(3, 3, 4)]),
    ]
    available = [
        offering("AAA101", "A-01", meetings=[meeting(3, 3, 4)]),
        offering("AAA101", "A-02", meetings=[meeting(3, 5, 6)]),
        offering("AAA101", "A-03", meetings=[meeting(5, 1, 2)]),
        offering("AAA101", "A-99", meetings=[meeting(3, 3, 4)]),
        offering("CCC101", "C-01", meetings=[meeting(3, 3, 4)]),
    ]
    return schedule, available


def test_conflict_with_one_clear_alternative_produces_a_proposal() -> None:
    schedule, available = current_schedule_fixture()
    proposals = generate_repair_proposals(
        semester=SEMESTER, current_schedule=schedule, offerings=available
    )

    assert proposals.semester == SEMESTER
    assert proposals.proposal_count >= 1
    assert "AAA101" in {item.target_course_id for item in proposals.proposals}


def test_conflict_with_multiple_clear_alternatives_produces_multiple_proposals() -> None:
    schedule, available = current_schedule_fixture()
    proposals = generate_repair_proposals(
        semester=SEMESTER, current_schedule=schedule, offerings=available
    )

    candidates = {
        item.candidate_class_id for item in proposals.for_course("AAA101")
    }
    assert {"A-02", "A-03"} <= candidates
    # 与剩余课表冲突的 A-99 ⛔ 不得成为建议。
    assert "A-99" not in candidates


def test_proposal_generation_does_not_mutate_the_schedule() -> None:
    schedule, available = current_schedule_fixture()
    before = [item.model_dump(mode="json") for item in schedule]
    available_before = [item.model_dump(mode="json") for item in available]

    generate_repair_proposals(
        semester=SEMESTER, current_schedule=schedule, offerings=available
    )

    assert [item.model_dump(mode="json") for item in schedule] == before
    assert [item.model_dump(mode="json") for item in available] == available_before


def test_clear_original_produces_no_proposal() -> None:
    schedule = [offering("AAA101", "A-01", meetings=[meeting(1, 1, 2)])]
    available = [
        offering("AAA101", "A-01", meetings=[meeting(1, 1, 2)]),
        offering("AAA101", "A-02", meetings=[meeting(2, 1, 2)]),
    ]
    proposals = generate_repair_proposals(
        semester=SEMESTER, current_schedule=schedule, offerings=available
    )
    # 原班已确认无冲突 ⇒ ⛔ 不制造无谓换班建议。
    assert proposals.proposal_count == 0


def test_unknown_schedule_is_reported_not_treated_as_conflict_free() -> None:
    """`meetings = []` = schedule UNKNOWN；⛔ 不得被说成"无冲突"。"""

    schedule = [offering("AAA101", "A-01", meetings=[])]
    available = [
        offering("AAA101", "A-01", meetings=[]),
        offering("AAA101", "A-02", meetings=[meeting(2, 1, 2)]),
    ]
    proposals = generate_repair_proposals(
        semester=SEMESTER, current_schedule=schedule, offerings=available
    )
    if proposals.proposal_count:
        for item in proposals.proposals:
            assert item.original_state.value == "UNKNOWN"
            assert "无冲突" not in item.reason or "已确认无时间冲突" in item.reason


def test_invalid_explicit_selection_fails_closed() -> None:
    schedule, available = current_schedule_fixture()

    # from 班不存在
    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="NOT-IN-SCHEDULE",
        to_class_id="A-02",
        current_schedule=schedule,
        offerings=available,
    )
    assert result.status is RepairApplicationStatus.REJECTED
    assert result.schedule == tuple(schedule)

    # to 班不在已接受 offerings 中
    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="A-01",
        to_class_id="NOT-IN-OFFERINGS",
        current_schedule=schedule,
        offerings=available,
    )
    assert result.status is RepairApplicationStatus.REJECTED

    # 候选仍与课表冲突 ⇒ 拒绝
    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="A-01",
        to_class_id="A-99",
        current_schedule=schedule,
        offerings=available,
    )
    assert result.status is RepairApplicationStatus.REJECTED


def test_repair_applies_only_after_explicit_selection() -> None:
    schedule, available = current_schedule_fixture()

    proposals = generate_repair_proposals(
        semester=SEMESTER, current_schedule=schedule, offerings=available
    )
    assert proposals.proposal_count > 0

    # ⛔ 生成建议后课表**没有**变化（仍未应用）。
    assert [item.class_id for item in schedule] == ["A-01", "C-01"]

    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="A-01",
        to_class_id="A-02",
        current_schedule=schedule,
        offerings=available,
    )

    assert result.status is RepairApplicationStatus.APPLIED
    assert [item.class_id for item in result.schedule] == ["A-02", "C-01"]
    assert len(result.changes) == 1
    change = result.changes[0]
    assert (change.course_id, change.from_class, change.to_class) == ("AAA101", "A-01", "A-02")


def test_different_course_substitution_is_rejected() -> None:
    schedule, available = current_schedule_fixture()

    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="A-01",
        to_class_id="C-01",  # 属于另一门课
        current_schedule=schedule,
        offerings=available,
    )
    # 候选属于另一门课（CCC101）⇒ ⛔ 不得被接受为 AAA101 的替代班。
    assert result.status is RepairApplicationStatus.REJECTED
    assert result.changes == ()
    assert [item.class_id for item in result.schedule] == ["A-01", "C-01"]
    # 课表身份必须原样保留：既没有新增 CCC101 的班，也没有改动 A-01。
    assert {(item.course_id, item.class_id) for item in result.schedule} == {
        ("AAA101", "A-01"),
        ("CCC101", "C-01"),
    }


def test_different_semester_substitution_is_rejected() -> None:
    schedule, available = current_schedule_fixture()
    other_semester = [
        offering("AAA101", "A-07", semester="2026-2", meetings=[meeting(3, 5, 6)])
    ]

    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="A-01",
        to_class_id="A-07",
        current_schedule=schedule,
        offerings=[*available, *other_semester],
    )
    # ⛔ 不得接受"存在于另一学期"的班号来替换本学期教学班。
    assert result.status is RepairApplicationStatus.REJECTED
    assert result.changes == ()
    assert [item.class_id for item in result.schedule] == ["A-01", "C-01"]
    assert "A-07" not in {item.class_id for item in result.schedule}


def test_repair_revalidates_the_new_schedule() -> None:
    schedule, available = current_schedule_fixture()

    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="A-01",
        to_class_id="A-02",
        current_schedule=schedule,
        offerings=available,
    )
    assert result.status is RepairApplicationStatus.APPLIED
    assert result.revalidated is True
    assert result.remaining_conflicts == ()


def test_same_class_selection_is_a_no_op() -> None:
    schedule, available = current_schedule_fixture()
    result = apply_repair_proposal(
        semester=SEMESTER,
        course_id="AAA101",
        from_class_id="A-01",
        to_class_id="A-01",
        current_schedule=schedule,
        offerings=available,
    )
    assert result.status is RepairApplicationStatus.UNCHANGED
    assert result.changes == ()


def test_duplicate_identity_in_input_is_rejected() -> None:
    duplicate = offering("AAA101", "A-01")
    with pytest.raises(ValueError):
        generate_repair_proposals(
            semester=SEMESTER,
            current_schedule=[duplicate, duplicate.model_copy(deep=True)],
            offerings=[duplicate],
        )


# ===========================================================================
# B. 未来学期：future roadmap
# ===========================================================================


def test_required_course_is_placed_in_its_recommended_semester() -> None:
    """`recommended_semester` 是**培养方案学期号**：4 ⇒ 第一个未来学期（2026-2）。"""

    roadmap = build_academic_roadmap(
        version=version([course("REQ101", recommended=4)]),
        semesters=FUTURE_MAP,
    )
    placed = {
        item.course_id: semester.semester_label
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert placed == {"REQ101": FUTURE[0]}


def test_prerequisite_ordering_is_respected() -> None:
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("BASE101", recommended=4),
                course("ADV101", recommended=4, prerequisites=("BASE101",)),
            ]
        ),
        semesters=FUTURE_MAP,
    )
    index = {
        item.course_id: semester.semester_index
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert index["BASE101"] < index["ADV101"]


def test_deadline_semester_is_honoured() -> None:
    """`deadline_semester` 是**培养方案学期号**：5 ⇒ 不晚于 2027-1。"""

    roadmap = build_academic_roadmap(
        version=version([course("DEAD101", recommended=6, deadline=5)]),
        semesters=FUTURE_MAP,
    )
    index = {
        item.course_id: semester.curriculum_semester
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert index["DEAD101"] <= 5


def test_recommended_semester_is_a_preference_not_absolute() -> None:
    """建议学期是偏好：受学分预算挤压时可推迟，但仍不晚于截止学期（培养方案学期号）。"""

    roadmap = build_academic_roadmap(
        version=version([course("PREF101", credit=4.0, recommended=4, deadline=5)]),
        semesters=FUTURE_MAP,
        per_semester_credit_budget={FUTURE[0]: 2.0, FUTURE[1]: 10.0},
    )
    index = {
        item.course_id: semester.curriculum_semester
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert index["PREF101"] == 5  # 培养方案第 4 学期装不下 ⇒ 推迟到第 5 学期（仍在截止前）


def test_semester_credit_budget_is_respected() -> None:
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("B1", credit=3.0, recommended=1),
                course("B2", credit=3.0, recommended=1),
                course("B3", credit=3.0, recommended=1),
            ]
        ),
        semesters=FUTURE_MAP,
        per_semester_credit_budget={FUTURE[0]: 6.0},
    )
    first = roadmap.future_semesters[0]
    assert first.total_credit <= 6.0


def test_hard_coded_credit_is_not_used_group_minimum_is_read_from_curriculum() -> None:
    group = CurriculumGroup(
        group_id="SYN-ELECTIVE-POOL",
        name="示例专业选修课",
        minimum_credit=5.0,
        source_record="table:4!row:1",
    )
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("E1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
                course("E2", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
                course("E3", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
            ],
            groups=(group,),
        ),
        semesters=FUTURE_MAP,
        elective_group_id="SYN-ELECTIVE-POOL",
        elective_completed_course_ids=[],
    )
    assert roadmap.elective_requirement_credit == 5.0  # ⛔ 不是任何硬编码常数
    # 3 学分粒度无法精确填满 5 学分 ⇒ ⛔ 不超额规划（只排 1 门 = 3 学分）。
    assert roadmap.elective_planned_credit == 3.0
    assert roadmap.elective_remaining_credit == 2.0
    # 选修池 3 门共 9 学分，只需 5 学分 ⇒ ⛔ 不得把 3 门全排进去。
    assert len(roadmap.future_course_ids) == 1


def test_elective_pool_courses_are_not_all_treated_as_required() -> None:
    group = CurriculumGroup(
        group_id="SYN-ELECTIVE-POOL",
        name="示例专业选修课",
        minimum_credit=3.0,
        source_record="table:4!row:1",
    )
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("E1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
                course("E2", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
            ],
            groups=(group,),
        ),
        semesters=FUTURE_MAP,
        elective_group_id="SYN-ELECTIVE-POOL",
        elective_completed_course_ids=[],
    )
    assert roadmap.elective_planned_credit == 3.0
    assert len(roadmap.future_course_ids) == 1


def test_insufficient_elective_evidence_stays_unresolved() -> None:
    group = CurriculumGroup(
        group_id="SYN-ELECTIVE-POOL",
        name="示例专业选修课",
        minimum_credit=6.0,
        source_record="table:4!row:1",
    )
    roadmap = build_academic_roadmap(
        version=version(
            [course("E1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL")],
            groups=(group,),
        ),
        semesters=FUTURE_MAP,
        elective_group_id="SYN-ELECTIVE-POOL",
        elective_completed_course_ids=None,  # 证据不足
    )
    assert roadmap.elective_completed_credit is None
    assert roadmap.elective_remaining_credit is None
    assert roadmap.elective_planned_credit == 0.0
    assert any("证据不足" in item for item in roadmap.unresolved)
    # ⛔ 证据不足时不得凭空规划选修学分。
    assert "E1" not in roadmap.future_course_ids


def test_unknown_group_minimum_is_reported_not_guessed() -> None:
    group = CurriculumGroup(
        group_id="SYN-UNKNOWN-MIN",
        name="示例学分未知选修组",
        minimum_credit=None,
        source_record="table:4!row:2",
    )
    roadmap = build_academic_roadmap(
        version=version([], groups=(group,)),
        semesters=FUTURE_MAP,
        elective_group_id="SYN-UNKNOWN-MIN",
        elective_completed_course_ids=[],
    )
    assert roadmap.elective_requirement_credit is None
    assert any("minimum_credit" in item for item in roadmap.unresolved)


def test_unknown_elective_group_fails_closed() -> None:
    with pytest.raises(RoadmapInputError):
        build_academic_roadmap(
            version=version([]),
            semesters=FUTURE_MAP,
            elective_group_id="NOT-IN-CURRICULUM",
        )


def test_future_output_has_no_section_teacher_or_meeting_fields() -> None:
    """⛔ 未来学期输出不得含 class_id / teacher / 时间地点 / 容量等字段。"""

    roadmap = build_academic_roadmap(
        version=version([course("REQ101", recommended=1)]),
        semesters=FUTURE_MAP,
    )
    plan = roadmap.future_semesters[0].courses[0]

    forbidden = {
        "class_id",
        "teacher",
        "weekday",
        "start_section",
        "end_section",
        "weeks",
        "campus",
        "classroom",
        "capacity",
        "remaining_capacity",
        "meetings",
    }
    field_names = set(SemesterCoursePlan.__dataclass_fields__)
    assert not (field_names & forbidden)
    assert not (set(type(plan).__dataclass_fields__) & forbidden)

    # 序列化后的实际键集也必须干净。
    serialized = {
        "course_id": plan.course_id,
        "course_name": plan.course_name,
        "credit": plan.credit,
        "requirement_kind": plan.requirement_kind.value,
        "reason": plan.reason,
        "placement": plan.placement.value,
    }
    assert not (set(serialized) & forbidden)


def test_future_planning_does_not_import_course_data() -> None:
    """⛔ 未来规划不依赖 Course Data：AST 层面不得有任何该模块 import。

    （docstring 里可以**声明**这条边界，但真实 import 必须为 0。）
    """

    package = Path(__file__).resolve().parents[1] / "app" / "path_planner"
    for name in ("future_roadmap.py", "__init__.py", "repair_proposals.py"):
        tree = ast.parse((package / name).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        offenders = [item for item in imported if "course_data" in item]
        assert offenders == [], f"{name} 不得 import Course Data：{offenders}"


def test_current_semester_is_summary_only_and_not_replanned() -> None:
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("NOW101", recommended=1),
                course("LATER101", recommended=2),
            ]
        ),
        semesters=FUTURE_MAP,
        current_semester=SEMESTER,
        current_semester_courses=[course("NOW101", recommended=1)],
    )
    # 当前学期由 RestrictedPlanner 负责 ⇒ ⛔ 未来路线图不得再排它一次。
    assert "NOW101" not in roadmap.future_course_ids
    assert roadmap.current_semester == SEMESTER
    assert roadmap.current_semester_planned_course_ids == ("NOW101",)
    assert "LATER101" in roadmap.future_course_ids


def test_current_semester_must_not_appear_in_future_labels() -> None:
    with pytest.raises(RoadmapInputError):
        build_academic_roadmap(
            version=version([]),
            semesters=FUTURE_MAP,
            current_semester=FUTURE[0],
        )


def test_deadline_outside_semester_range_is_unresolved_not_guessed() -> None:
    roadmap = build_academic_roadmap(
        version=version([course("OUT101", deadline=99)]),
        semesters=FUTURE_MAP,
    )
    assert "OUT101" not in roadmap.future_course_ids
    assert any("deadline_semester" in item for item in roadmap.unresolved)


def test_prerequisite_cycle_is_reported_not_guessed() -> None:
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("CYC1", prerequisites=("CYC2",)),
                course("CYC2", prerequisites=("CYC1",)),
            ]
        ),
        semesters=FUTURE_MAP,
    )
    assert roadmap.future_course_ids == ()
    assert any("先修环" in item for item in roadmap.unresolved)


def test_missing_prerequisite_is_reported_and_does_not_invent_edges() -> None:
    roadmap = build_academic_roadmap(
        version=version([course("SOLO101", recommended=1, prerequisites=("GHOST101",))]),
        semesters=FUTURE_MAP,
    )
    assert any("先修 GHOST101" in item or "GHOST101" in item for item in roadmap.unresolved)
    # ⛔ 不编造先修 ⇒ 该课仍按其自身事实落位。
    assert "SOLO101" in roadmap.future_course_ids


def test_completed_course_is_not_replanned() -> None:
    roadmap = build_academic_roadmap(
        version=version([course("DONE101", recommended=1)]),
        completed=[completed("DONE101")],
        semesters=FUTURE_MAP,
    )
    assert "DONE101" not in roadmap.future_course_ids


def test_semester_without_budget_warns_that_no_cap_applied() -> None:
    roadmap = build_academic_roadmap(
        version=version([course("REQ101", recommended=1)]),
        semesters=FUTURE_MAP,
    )
    assert any("学分预算" in item for item in roadmap.warnings)


def test_empty_semesters_sequence_is_rejected() -> None:
    with pytest.raises(RoadmapInputError):
        build_academic_roadmap(version=version([]), semesters=())


def test_deterministic_output_for_same_input() -> None:
    courses = [
        course("D1", recommended=5),
        course("D2", recommended=4),
        course("D3", recommended=4, prerequisites=("D2",)),
    ]
    first = build_academic_roadmap(version=version(list(courses)), semesters=FUTURE_MAP)
    second = build_academic_roadmap(version=version(list(courses)), semesters=FUTURE_MAP)
    assert first.future_course_ids == second.future_course_ids
    assert [item.semester_index for item in first.future_semesters] == [
        item.semester_index for item in second.future_semesters
    ]


# ===========================================================================
# ARCHITECTURE REVIEW FIX 1 — 培养方案学期号映射
# ===========================================================================


def test_A_curriculum_semester_map_is_explicit_and_not_list_position() -> None:
    """当前=培养方案第 3 学期；未来 4,5,6；`recommended=4` ⇒ 第一个未来学期。"""

    mapping = {"2026-2": 4, "2027-1": 5, "2027-2": 6}
    roadmap = build_academic_roadmap(
        version=version([course("REC4", recommended=4)]),
        semesters=mapping,
    )
    assert roadmap.curriculum_semester_map == (("2026-2", 4), ("2027-1", 5), ("2027-2", 6))
    placed = {
        item.course_id: semester.semester_label
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    # ⛔ 关键：不是"列表第 4 项"（列表只有 3 项），而是培养方案第 4 学期 = 2026-2。
    assert placed == {"REC4": "2026-2"}


def test_A_recommended_semester_6_maps_to_third_future_label() -> None:
    mapping = {"2026-2": 4, "2027-1": 5, "2027-2": 6}
    roadmap = build_academic_roadmap(
        version=version([course("REC6", recommended=6)]),
        semesters=mapping,
    )
    placed = {
        item.course_id: semester.semester_label
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert placed == {"REC6": "2027-2"}


def test_B_deadline_compares_curriculum_semester_not_position() -> None:
    """`deadline=5` ⇒ 不晚于**培养方案第 5 学期**（= 2027-1），⛔ 不是列表第 5 项。"""

    mapping = {"2026-2": 4, "2027-1": 5, "2027-2": 6}
    roadmap = build_academic_roadmap(
        version=version([course("DL5", recommended=6, deadline=5)]),
        semesters=mapping,
    )
    by_id = {
        item.course_id: semester.curriculum_semester
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert by_id["DL5"] <= 5
    assert by_id["DL5"] == 5  # 建议学期 6 被截止学期 5 拉回

    # 不可满足的截止（培养方案第 3 学期，早于所有未来学期）⇒ 不猜、不违反。
    blocked = build_academic_roadmap(
        version=version([course("DL3", deadline=3)]),
        semesters=mapping,
    )
    assert "DL3" not in blocked.future_course_ids
    assert any("deadline_semester=3" in item for item in blocked.unresolved)


def test_C_plain_label_sequence_without_mapping_is_rejected() -> None:
    """⛔ 只给学期标签不足以确定培养方案学期号：必须 fail closed。"""

    with pytest.raises(RoadmapInputError):
        build_academic_roadmap(
            version=version([course("X", recommended=4)]),
            semesters=("2026-2", "2027-1"),
        )


def test_C_conflicting_semester_sources_are_rejected() -> None:
    with pytest.raises(RoadmapInputError):
        build_academic_roadmap(
            version=version([]),
            semesters={"2026-2": 4},
            from_curriculum_semester=4,
        )
    with pytest.raises(RoadmapInputError):
        build_academic_roadmap(
            version=version([]),
            semesters=[FutureSemester("2026-2", 4, 1)],
            from_curriculum_semester=4,
        )


def test_C_duplicate_curriculum_semesters_are_rejected() -> None:
    with pytest.raises(RoadmapInputError):
        build_academic_roadmap(
            version=version([]),
            semesters={"2026-2": 4, "2027-1": 4},
        )


def test_from_curriculum_semester_explicit_sequencing_works() -> None:
    """显式给出起始培养方案学期号时，可按顺序编号。"""

    roadmap = build_academic_roadmap(
        version=version([course("SEQ", recommended=5)]),
        semesters=("2026-2", "2027-1", "2027-2"),
        from_curriculum_semester=4,
    )
    assert roadmap.curriculum_semester_map == (
        ("2026-2", 4),
        ("2027-1", 5),
        ("2027-2", 6),
    )
    placed = {
        item.course_id: semester.semester_label
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert placed == {"SEQ": "2027-1"}


def test_prerequisite_order_uses_chronology_not_list_position() -> None:
    """先修先后按**培养方案学期号**（时间轴），列表顺序不影响结论。"""

    mapping = {"2027-1": 5, "2026-2": 4}  # ⚠️ 故意乱序列出
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("EARLY", recommended=4),
                course("LATE", recommended=5, prerequisites=("EARLY",)),
            ]
        ),
        semesters=mapping,
    )
    by_id = {
        item.course_id: semester.curriculum_semester
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert by_id["EARLY"] == 4
    assert by_id["LATE"] == 5
    assert by_id["EARLY"] < by_id["LATE"]


# ===========================================================================
# ARCHITECTURE REVIEW FIX 2 — 使用 Curriculum 已确认的满足事实
# ===========================================================================


def test_A_pending_completed_course_with_confirmed_satisfaction_is_not_replanned() -> None:
    """`CompletedCourse.course_id=None`（成绩单无官方课程号）+ 目标课已确认满足。"""

    pending = CompletedCourse(
        course_id=None,  # ⛔ 真实成绩单 PDF 不提供官方课程号
        course_name="示例已修课程名",
        credit=3.0,
        semester="2025-1",
        passed=True,
        course_type="公必",
        course_id_status=CourseIdStatus.PENDING,
        id_match_source=None,
        source_id="case-owner-confirmed://synthetic/completed",
        source_record="pdf:1",
    )
    roadmap = build_academic_roadmap(
        version=version([course("SAT101", recommended=4)]),
        completed=[pending],
        confirmed_satisfied_course_ids=["SAT101"],
        semesters=FUTURE_MAP,
    )
    # ⛔ 已确认满足 ⇒ 绝不重新规划。
    assert "SAT101" not in roadmap.future_course_ids


def test_A_satisfied_makeup_task_is_accepted_as_satisfaction_fact() -> None:
    roadmap = build_academic_roadmap(
        version=version([course("SAT202", recommended=4)]),
        makeup_tasks=[
            MakeupTask(
                course_id="SAT202",
                course_name="示例课程 SAT202",
                credit=3.0,
                status=MakeupStatus.SATISFIED,
            )
        ],
        semesters=FUTURE_MAP,
    )
    assert "SAT202" not in roadmap.future_course_ids


@pytest.mark.parametrize(
    "status",
    [MakeupStatus.MANUAL_CONFIRMATION, MakeupStatus.POSSIBLY_EQUIVALENT],
)
def test_B_manual_confirmation_is_never_promoted_to_satisfied(status: MakeupStatus) -> None:
    """`manual_confirmation` / `possibly_equivalent` ⛔ **不得**被当成已满足。"""

    roadmap = build_academic_roadmap(
        version=version([course("AMB101", recommended=4)]),
        makeup_tasks=[
            MakeupTask(
                course_id="AMB101",
                course_name="示例课程 AMB101",
                credit=3.0,
                status=status,
            )
        ],
        semesters=FUTURE_MAP,
    )
    # 仍需规划（未视为已满足）。
    assert "AMB101" in roadmap.future_course_ids
    # 并且必须如实说明它未满足、仍需人工认定。
    assert any(status.value in item for item in roadmap.warnings)


def test_C_satisfied_course_never_appears_in_future_course_ids() -> None:
    roadmap = build_academic_roadmap(
        version=version(
            [
                course("SAT303", recommended=4),
                course("TODO404", recommended=4),
            ]
        ),
        confirmed_satisfied_course_ids=["SAT303"],
        semesters=FUTURE_MAP,
    )
    assert "SAT303" not in roadmap.future_course_ids
    assert "TODO404" in roadmap.future_course_ids


def test_raw_completed_id_alone_is_secondary_not_the_only_mechanism() -> None:
    """原始 `CompletedCourse.course_id` 不是唯一机制：两者都能阻止重复规划。"""

    by_confirmed = build_academic_roadmap(
        version=version([course("M1", recommended=4)]),
        confirmed_satisfied_course_ids=["M1"],
        semesters=FUTURE_MAP,
    )
    by_completed = build_academic_roadmap(
        version=version([course("M1", recommended=4)]),
        completed=[completed("M1")],
        semesters=FUTURE_MAP,
    )
    assert "M1" not in by_confirmed.future_course_ids
    assert "M1" not in by_completed.future_course_ids


# ===========================================================================
# ARCHITECTURE REVIEW FIX 3 — 本学期选修学分计入
# ===========================================================================


def elective_group(minimum: float) -> CurriculumGroup:
    return CurriculumGroup(
        group_id="SYN-ELECTIVE-POOL",
        name="示例专业选修课",
        minimum_credit=minimum,
        source_record="table:4!row:1",
    )


def test_current_semester_elective_credit_enters_the_gap() -> None:
    """minimum=23 / completed=8 / current=6 ⇒ 未来缺口 9（⛔ 不得再规划 15）。"""

    pool = [
        course("E1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
        course("E2", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
        course("E3", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
        course("E4", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
        course("E5", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
    ]
    completed_electives = [
        course("D1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
        course("D2", credit=5.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
    ]
    current_electives = [
        course("C1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
        course("C2", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
    ]

    roadmap = build_academic_roadmap(
        version=version(
            [*pool, *completed_electives, *current_electives],
            groups=(elective_group(23.0),),
        ),
        semesters=FUTURE_MAP,
        current_semester=SEMESTER,
        current_semester_courses=list(current_electives),
        elective_group_id="SYN-ELECTIVE-POOL",
        elective_completed_course_ids=["D1", "D2"],
        elective_current_semester_course_ids=["C1", "C2"],
    )

    assert roadmap.elective_requirement_credit == 23.0
    assert roadmap.elective_completed_credit == 8.0
    assert roadmap.elective_current_semester_credit == 6.0
    # 规划前缺口 = 23 - 8 - 6 = 9；3 学分粒度精确填满 ⇒ 规划 9、剩余 0。
    assert roadmap.elective_planned_credit == 9.0
    assert roadmap.elective_remaining_credit == 0.0
    # ⛔ 不得把缺口当成 15 去规划 15 学分。
    assert roadmap.elective_planned_credit != 15.0


def test_current_semester_elective_credit_requires_confirmation() -> None:
    """未确认本学期选修归属 ⇒ ⛔ 不计入，并如实报 unresolved。"""

    current_electives = [
        course("C1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL"),
    ]
    roadmap = build_academic_roadmap(
        version=version(
            [*current_electives, course("E1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL")],
            groups=(elective_group(9.0),),
        ),
        semesters=FUTURE_MAP,
        current_semester=SEMESTER,
        current_semester_courses=list(current_electives),
        elective_group_id="SYN-ELECTIVE-POOL",
        elective_completed_course_ids=[],
        elective_current_semester_course_ids=None,  # 证据不足
    )
    assert roadmap.elective_current_semester_credit == 0.0
    assert any("本学期选修学分证据不足" in item for item in roadmap.unresolved)


def test_current_semester_course_outside_group_is_not_counted() -> None:
    other = course("OUT1", credit=3.0, requirement=RequirementKind.REQUIRED)
    roadmap = build_academic_roadmap(
        version=version(
            [other, course("E1", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL")],
            groups=(elective_group(9.0),),
        ),
        semesters=FUTURE_MAP,
        current_semester=SEMESTER,
        current_semester_courses=[other],
        elective_group_id="SYN-ELECTIVE-POOL",
        elective_completed_course_ids=[],
        elective_current_semester_course_ids=["OUT1"],  # ⛔ 不属于该选修组
    )
    assert roadmap.elective_current_semester_credit == 0.0
    assert any("不计入选修学分" in item for item in roadmap.unresolved)


def test_elective_gap_never_exceeds_requirement_minus_completed_minus_current() -> None:
    """选修账恒等式：`requirement − completed − current == planned + remaining`。

    ⚠️ `remaining` 是**规划之后**仍缺的学分；`planned` 是本次实际排入的学分。
    """

    pool = [
        course(f"P{i}", credit=3.0, requirement=RequirementKind.ELECTIVE, group_id="SYN-ELECTIVE-POOL")
        for i in range(4)
    ]
    roadmap = build_academic_roadmap(
        version=version(pool, groups=(elective_group(10.0),)),
        semesters=FUTURE_MAP,
        elective_group_id="SYN-ELECTIVE-POOL",
        elective_completed_course_ids=[],
        elective_current_semester_course_ids=[],
    )
    assert roadmap.elective_requirement_credit == 10.0
    assert roadmap.elective_completed_credit == 0.0
    assert roadmap.elective_current_semester_credit == 0.0
    assert (
        roadmap.elective_requirement_credit
        - roadmap.elective_completed_credit
        - roadmap.elective_current_semester_credit
        == roadmap.elective_planned_credit + roadmap.elective_remaining_credit
    )
    # ⛔ 不得为凑学分超额规划（10 学分缺口不应排入 4×3=12 学分）。
    assert roadmap.elective_planned_credit <= 10.0
    # 3 学分粒度无法精确填满 10 ⇒ 只排 3 门（9 学分），如实报告仍缺 1 学分。
    assert roadmap.elective_remaining_credit == 1.0
    assert roadmap.elective_planned_credit == 9.0
    assert any("仍缺 1.0 学分" in item for item in roadmap.unresolved)
    # 账目恒等式（`remaining` = 规划**之后**仍缺的学分）：
    assert (
        roadmap.elective_requirement_credit
        - roadmap.elective_completed_credit
        - roadmap.elective_current_semester_credit
        == roadmap.elective_planned_credit + roadmap.elective_remaining_credit
    )
