"""未来学期：**课程级**（course-level）多学期补修路线图。

```text
CurriculumVersion（目标方案事实）
  + CompletedCourse[]（已修事实）
  + 确认的当前学期课程摘要（来自 RestrictedPlanner / 真实教学班规划）
        ↓  build_academic_roadmap()
AcademicRoadmap（current_semester 摘要 + future_semesters[] + 选修学分账）
```

## 硬架构规则（⛔ 不得越界）

```text
当前学期 = 教学班级（section-level）规划，由 RestrictedPlanner + 真实 CourseOffering 负责
未来学期 = 课程级（course-level）规划，只吃培养方案事实
```

因此本模块：

- ⛔ **不要求、不预测、不生成**任何未来 `CourseOffering`；
- ⛔ 未来学期输出**没有** `class_id` / `teacher` / `weekday` / `start_section` /
  `end_section` / `campus` / `classroom` / `capacity`（由 `SemesterCoursePlan`
  的字段集在结构上保证，不是"约定"）；
- ⛔ **不**用本学期真实开课情况去断言未来教学班是否存在；
- ⛔ **不**访问 Course Data（本模块不 import 任何 `app.course_data`）；
- ⛔ **不**编造先修关系 / 学分 / 学期事实：只使用 `CurriculumCourse` 上已给出的取值；
- ⛔ **不**把选修池里的每门课都当成必修：只为**满足 group 最低学分**选足够学分。

## 学分与学期口径

- `minimum_credit` 一律从 `CurriculumGroup.minimum_credit` **读取**，
  ⛔ 算法里**不存在**任何硬编码学分常数；
- `semester_index` 由调用方给出的 `semesters` 顺序映射得到（1..N），
  `recommended_semester` / `deadline_semester` 按**同一映射**解释；
- `recommended_semester` 只作**排课偏好**（可被先修/预算推迟）；
  `deadline_semester` 是**硬约束**（⛔ 宁可留 unresolved 也不违反）。

## 确定性

课程放置顺序 = 先修拓扑序（同层按 `deadline → recommended → course_id`），
因此同一输入恒得同一路线图（⛔ 无随机、⛔ 无评分权重、⛔ 不是全局最优求解）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from app.curriculum.completed_courses import CompletedCourse
from app.curriculum.requirements import (
    CurriculumCourse,
    CurriculumGroup,
    CurriculumVersion,
    RequirementKind,
)

__all__ = [
    "AcademicRoadmap",
    "FutureSemester",
    "PlacementReason",
    "RoadmapInputError",
    "SemesterCoursePlan",
    "SemesterPlan",
    "build_academic_roadmap",
]


class RoadmapInputError(ValueError):
    """路线图输入不合法（fail closed，⛔ 不猜测）。"""


class PlacementReason(str, Enum):
    """一门课被放进某个学期的**原因分类**（机器可读，⛔ 不是学校政策解释）。"""

    REQUIRED_BY_RECOMMENDED_TERM = "required_by_recommended_term"
    REQUIRED_BEFORE_DEADLINE = "required_before_deadline"
    PREREQUISITE_ORDER = "prerequisite_order"
    ELECTIVE_TO_MEET_GROUP_MINIMUM = "elective_to_meet_group_minimum"
    DEFERRED_FOR_CREDIT_BUDGET = "deferred_for_credit_budget"


@dataclass(frozen=True, slots=True)
class SemesterCoursePlan:
    """一门课在某个学期的**课程级**安排。

    ⛔ 该字段集**故意**不含 `class_id` / `teacher` / `weekday` / `start_section` /
    `end_section` / `campus` / `classroom` / `capacity`：未来学期不允许输出教学班级
    信息，这是结构上的保证。
    """

    course_id: str
    course_name: str
    credit: float
    requirement_kind: RequirementKind
    reason: str
    placement: PlacementReason

    def __post_init__(self) -> None:
        for name in ("course_id", "course_name", "reason"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise RoadmapInputError(f"{name} 必须是非空字符串。")
        if isinstance(self.credit, bool) or not isinstance(self.credit, (int, float)):
            raise RoadmapInputError("credit 必须是数字。")
        if self.credit < 0:
            raise RoadmapInputError("credit 不能为负。")
        if not isinstance(self.requirement_kind, RequirementKind):
            raise RoadmapInputError("requirement_kind 必须是 RequirementKind。")
        if not isinstance(self.placement, PlacementReason):
            raise RoadmapInputError("placement 必须是 PlacementReason。")


@dataclass(frozen=True, slots=True)
class SemesterPlan:
    """一个**未来**学期的课程级计划。"""

    semester_index: int
    semester_label: str
    courses: tuple[SemesterCoursePlan, ...]
    warnings: tuple[str, ...] = ()

    @property
    def required_credit(self) -> float:
        return _round_credit(
            sum(
                item.credit
                for item in self.courses
                if item.requirement_kind is RequirementKind.REQUIRED
            )
        )

    @property
    def elective_credit(self) -> float:
        return _round_credit(
            sum(
                item.credit
                for item in self.courses
                if item.requirement_kind is RequirementKind.ELECTIVE
            )
        )

    @property
    def total_credit(self) -> float:
        return _round_credit(sum(item.credit for item in self.courses))

    @property
    def course_ids(self) -> tuple[str, ...]:
        return tuple(item.course_id for item in self.courses)


@dataclass(frozen=True, slots=True)
class FutureSemester:
    """调用方声明的学期（标签 + 位置）；`semester_index` 从 1 开始。"""

    semester_label: str
    semester_index: int


@dataclass(frozen=True, slots=True)
class AcademicRoadmap:
    """完整路线图：当前学期摘要 + 未来学期课程级计划 + 选修学分账。"""

    current_semester: str | None
    current_semester_planned_course_ids: tuple[str, ...]
    future_semesters: tuple[SemesterPlan, ...]
    elective_requirement_credit: float | None
    elective_completed_credit: float | None
    elective_planned_credit: float
    elective_remaining_credit: float | None
    unresolved: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def future_course_ids(self) -> tuple[str, ...]:
        return tuple(
            course_id
            for semester in self.future_semesters
            for course_id in semester.course_ids
        )

    @property
    def total_future_credit(self) -> float:
        return _round_credit(sum(item.total_credit for item in self.future_semesters))


@dataclass
class _Placement:
    course: CurriculumCourse
    semester_index: int
    reason: PlacementReason
    note: str = ""


def _round_credit(value: float) -> float:
    return round(float(value), 6)


def _require_semesters(semesters: Sequence[str]) -> tuple[str, ...]:
    if isinstance(semesters, (str, bytes)) or not isinstance(semesters, Sequence):
        raise RoadmapInputError("semesters 必须是非空的学期标签序列。")
    material = tuple(semesters)
    if not material:
        raise RoadmapInputError("semesters 不能为空：未来学期顺序必须由调用方显式声明。")
    for item in material:
        if not isinstance(item, str) or not item.strip():
            raise RoadmapInputError("semesters 中的学期标签必须是非空字符串。")
    if len(set(material)) != len(material):
        raise RoadmapInputError("semesters 存在重复学期标签。")
    return tuple(item.strip() for item in material)


def _require_credits(
    per_semester_credit_budget: Mapping[str, float] | None,
) -> dict[str, float]:
    if per_semester_credit_budget is None:
        return {}
    if not isinstance(per_semester_credit_budget, Mapping):
        raise RoadmapInputError("per_semester_credit_budget 必须是 学期标签 -> 学分 的映射。")
    budget: dict[str, float] = {}
    for label, value in per_semester_credit_budget.items():
        if not isinstance(label, str) or not label.strip():
            raise RoadmapInputError("学分预算的键必须是非空学期标签。")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise RoadmapInputError("学分预算必须是非负数字。")
        budget[label.strip()] = float(value)
    return budget


def _is_member(course: CurriculumCourse, group: CurriculumGroup) -> bool:
    return course.group_id is not None and course.group_id == group.group_id


def build_academic_roadmap(
    *,
    version: CurriculumVersion,
    completed: Sequence[CompletedCourse] = (),
    semesters: Sequence[str],
    current_semester: str | None = None,
    current_semester_courses: Sequence[CurriculumCourse] = (),
    elective_group_id: str | None = None,
    elective_completed_course_ids: Sequence[str] | None = None,
    per_semester_credit_budget: Mapping[str, float] | None = None,
) -> AcademicRoadmap:
    """生成**课程级**未来学期路线图（只依赖培养方案事实）。

    参数：

    - `version` —— 目标培养方案（`CurriculumCourse` / `CurriculumGroup` 事实）；
    - `completed` —— 已修课程事实（用于识别"已修过 / 已通过的 target 课程"）；
    - `semesters` —— **未来**学期顺序（调用方显式声明；`semester_index` = 1..N）；
    - `current_semester` / `current_semester_courses` —— 当前学期**摘要**：
      ⛔ 本模块**不**重新生成当前学期教学班选择，只把它当作"不要再排一遍"的输入；
    - `elective_group_id` —— 需要满足最低学分的选修组；
    - `elective_completed_course_ids` —— **调用方确认**已归属该选修组的课程号；
      ⛔ `None`（缺省）表示**证据不足**：此时不猜，`elective_completed_credit`
      与 `elective_remaining_credit` 报 `None`，并写入 `unresolved`；
    - `per_semester_credit_budget` —— 每学期学分上限（可选）；缺省表示不设上限，
      并在 `warnings` 中如实说明。
    """

    if not isinstance(version, CurriculumVersion):
        raise RoadmapInputError("version 必须是 CurriculumVersion。")
    labels = _require_semesters(semesters)
    budget = _require_credits(per_semester_credit_budget)

    if current_semester is not None:
        if not isinstance(current_semester, str) or not current_semester.strip():
            raise RoadmapInputError("current_semester 必须是非空字符串或 None。")
        current_semester = current_semester.strip()
        if current_semester in labels:
            raise RoadmapInputError(
                "current_semester 不得同时出现在未来学期序列中；"
                "当前学期由 RestrictedPlanner / 真实教学班规划负责。"
            )

    unresolved: list[str] = []
    warnings: list[str] = []

    # ---- 选修组：一律从 CurriculumGroup.minimum_credit 读取（⛔ 无硬编码） --------
    group: CurriculumGroup | None = None
    if elective_group_id is not None:
        if not isinstance(elective_group_id, str) or not elective_group_id.strip():
            raise RoadmapInputError("elective_group_id 必须是非空字符串或 None。")
        matches = [item for item in version.groups if item.group_id == elective_group_id]
        if not matches:
            raise RoadmapInputError(
                f"培养方案中不存在选修组 {elective_group_id}；⛔ 不猜测其最低学分。"
            )
        group = matches[0]

    # ---- 已修 / 当前学期事实 ----------------------------------------------------
    completed_ids: set[str] = set()
    for item in completed:
        if not isinstance(item, CompletedCourse):
            raise RoadmapInputError("completed 中混入了非 CompletedCourse 对象。")
        if item.course_id is not None and item.passed:
            completed_ids.add(item.course_id)

    current_course_ids: set[str] = set()
    for item in current_semester_courses:
        if not isinstance(item, CurriculumCourse):
            raise RoadmapInputError(
                "current_semester_courses 中混入了非 CurriculumCourse 对象。"
            )
        current_course_ids.add(item.course_id)

    # 已修 / 本学期已覆盖的课不再排入未来学期（⛔ 不重复安排同一门课）。
    planned_pool = [
        course
        for course in version.courses
        if course.course_id not in completed_ids
        and course.course_id not in current_course_ids
    ]

    # ---- 选修学分账 -------------------------------------------------------------
    elective_requirement = group.minimum_credit if group is not None else None
    elective_completed: float | None = None
    elective_remaining: float | None = None
    elective_planned = 0.0

    if group is None:
        unresolved.append(
            "未指定需要满足最低学分的选修组；本次不规划选修学分，也不推断任何选修要求。"
        )
    elif elective_requirement is None:
        unresolved.append(
            f"选修组 {group.group_id} 的 minimum_credit 在培养方案中未知；"
            f"⛔ 不猜测最低学分，选修规划留待人工确认。"
        )
    elif elective_completed_course_ids is None:
        unresolved.append(
            f"选修组 {group.group_id} 的**已完成选修学分证据不足**"
            f"（调用方未确认哪些已修课程归属该组）；⛔ 不猜测已完成学分，"
            f"因此本次不规划选修学分。"
        )
    else:
        if isinstance(elective_completed_course_ids, (str, bytes)) or not isinstance(
            elective_completed_course_ids, Sequence
        ):
            raise RoadmapInputError("elective_completed_course_ids 必须是课程号序列。")
        confirmed = {
            str(item).strip()
            for item in elective_completed_course_ids
            if isinstance(item, str) and item.strip()
        }
        credit_by_id = {
            course.course_id: float(course.credit)
            for course in version.courses
            if _is_member(course, group)
        }
        unknown = sorted(confirmed - set(credit_by_id))
        if unknown:
            unresolved.append(
                f"调用方声明的已完成选修课程中有 {len(unknown)} 门不在选修组 "
                f"{group.group_id} 的培养方案成员里；⛔ 不计入学分，需人工确认。"
            )
        elective_completed = _round_credit(
            sum(credit_by_id[item] for item in confirmed if item in credit_by_id)
        )
        elective_remaining = _round_credit(max(elective_requirement - elective_completed, 0.0))

    # ---- 先修关系（只使用已给出的先修事实） --------------------------------------
    pool_by_id: dict[str, CurriculumCourse] = {}
    for course in planned_pool:
        # 同一 course_id 可能有多条来源记录；取第一条并在下方如实报告重复。
        pool_by_id.setdefault(course.course_id, course)
    duplicates = sorted(
        {
            course.course_id
            for course in planned_pool
            if sum(1 for other in planned_pool if other.course_id == course.course_id) > 1
        }
    )
    if duplicates:
        warnings.append(
            f"培养方案中有 {len(duplicates)} 门课存在多条来源记录；本次规划按课程号合并，"
            f"⛔ 不改变任何来源事实。"
        )

    prerequisite_edges: dict[str, tuple[str, ...]] = {}
    for course_id, course in pool_by_id.items():
        edges: list[str] = []
        for reference in course.prerequisites or ():
            if reference in completed_ids or reference in current_course_ids:
                continue  # 已修 / 本学期在读 ⇒ 不再约束未来学期先后
            if reference not in pool_by_id:
                unresolved.append(
                    f"课程 {course_id} 的先修 {reference} 不在本次培养方案事实中；"
                    f"⛔ 不编造先修，该校验留待人工确认（不阻断其余课程的规划）。"
                )
                continue
            edges.append(reference)
        prerequisite_edges[course_id] = tuple(sorted(set(edges)))

    order, cyclic = _prerequisite_order(
        pool_by_id,
        prerequisite_edges,
        key=lambda item: (
            item.deadline_semester if item.deadline_semester is not None else 10**6,
            item.recommended_semester if item.recommended_semester is not None else 10**6,
            item.course_id,
        ),
    )
    for course_id in sorted(cyclic):
        unresolved.append(
            f"课程 {course_id} 落在先修环中，无法确定先后顺序；⛔ 不猜测，未排入路线图。"
        )

    required_queue = [
        pool_by_id[course_id]
        for course_id in order
        if pool_by_id[course_id].requirement is RequirementKind.REQUIRED
        and not (group is not None and _is_member(pool_by_id[course_id], group))
    ]
    elective_pool = [
        pool_by_id[course_id]
        for course_id in order
        if group is not None and _is_member(pool_by_id[course_id], group)
    ]

    placements: list[_Placement] = []
    placed_index: dict[str, int] = {}
    used_credit: dict[str, float] = {label: 0.0 for label in labels}

    # ---- 1) 必修课：先修顺序 → 截止学期（硬）→ 建议学期（偏好）→ 学分预算 --------
    for course in required_queue:
        placement = _place_required(
            course,
            labels=labels,
            budget=budget,
            used_credit=used_credit,
            prerequisite_edges=prerequisite_edges,
            placed_index=placed_index,
            unresolved=unresolved,
        )
        if placement is None:
            continue
        placements.append(placement)
        placed_index[course.course_id] = placement.semester_index
        used_credit[labels[placement.semester_index - 1]] += float(course.credit)

    # ---- 2) 选修：只选**足够满足 group 最低学分**的学分 --------------------------
    if group is not None and elective_requirement is not None and elective_remaining is not None:
        remaining = elective_remaining
        for course in elective_pool:
            if remaining <= 0:
                break
            placement = _place_elective(
                course,
                labels=labels,
                budget=budget,
                used_credit=used_credit,
                prerequisite_edges=prerequisite_edges,
                placed_index=placed_index,
                unresolved=unresolved,
            )
            if placement is None:
                continue
            placements.append(placement)
            placed_index[course.course_id] = placement.semester_index
            used_credit[labels[placement.semester_index - 1]] += float(course.credit)
            remaining = _round_credit(remaining - float(course.credit))
        elective_planned = _round_credit(elective_remaining - max(remaining, 0.0))
        if remaining > 0:
            unresolved.append(
                f"选修组 {group.group_id} 仍缺 {remaining} 学分：当前培养方案成员不足以满足"
                f"最低学分，或受先修 / 学分预算限制；⛔ 不编造课程来补齐。"
            )

    # ---- 组装学期计划 -----------------------------------------------------------
    by_semester: dict[int, list[_Placement]] = {index: [] for index in range(1, len(labels) + 1)}
    for placement in placements:
        by_semester[placement.semester_index].append(placement)

    future: list[SemesterPlan] = []
    for index, label in enumerate(labels, start=1):
        items = sorted(by_semester[index], key=lambda item: item.course.course_id)
        semester_warnings: list[str] = []
        cap = budget.get(label)
        total = _round_credit(sum(float(item.course.credit) for item in items))
        if cap is not None and total > cap:
            # 结构上不可达（放置时已检查预算）；保留为纵深防御。
            semester_warnings.append(
                f"该学期已规划 {total} 学分，超过预算 {cap} 学分。"
            )
        if not items:
            semester_warnings.append("该学期按当前培养方案事实没有需要安排的课程。")
        future.append(
            SemesterPlan(
                semester_index=index,
                semester_label=label,
                courses=tuple(
                    SemesterCoursePlan(
                        course_id=item.course.course_id,
                        course_name=item.course.course_name,
                        credit=float(item.course.credit),
                        requirement_kind=item.course.requirement,
                        reason=item.note,
                        placement=item.reason,
                    )
                    for item in items
                ),
                warnings=tuple(semester_warnings),
            )
        )

    if not budget:
        warnings.append(
            "未提供每学期学分预算：本次不设学期学分上限，"
            "⛔ 这不代表真实学期负荷可接受。"
        )

    return AcademicRoadmap(
        current_semester=current_semester,
        current_semester_planned_course_ids=tuple(sorted(current_course_ids)),
        future_semesters=tuple(future),
        elective_requirement_credit=elective_requirement,
        elective_completed_credit=elective_completed,
        elective_planned_credit=elective_planned,
        elective_remaining_credit=elective_remaining,
        unresolved=tuple(unresolved),
        warnings=tuple(warnings),
    )


def _prerequisite_order(
    pool_by_id: Mapping[str, CurriculumCourse],
    edges: Mapping[str, tuple[str, ...]],
    *,
    key,
) -> tuple[list[str], set[str]]:
    """先修拓扑序（确定性）。返回 `(顺序, 落在环里的课程号)`。"""

    pending: dict[str, set[str]] = {
        course_id: set(edges.get(course_id, ())) for course_id in pool_by_id
    }
    ordered: list[str] = []
    settled: set[str] = set()

    while True:
        ready = [
            course_id
            for course_id, prereqs in pending.items()
            if course_id not in settled and not (prereqs - settled)
        ]
        if not ready:
            break
        # 同层按调用方给定的确定性 key（deadline → recommended → course_id）。
        ready.sort(key=lambda course_id: key(pool_by_id[course_id]))
        for course_id in ready:
            ordered.append(course_id)
            settled.add(course_id)

    cyclic = {course_id for course_id in pool_by_id if course_id not in settled}
    return ordered, cyclic


def _prerequisite_floor(
    course: CurriculumCourse,
    *,
    edges: Mapping[str, tuple[str, ...]],
    placed_index: Mapping[str, int],
) -> int:
    """先修约束下的最早 semester_index（floor）。

    调用方保证课程按先修拓扑序处理，因此此处每个先修**必然**已处理：
    要么已落位（取其下标 + 1），要么已被报告为不可安排（此时本课也不可安排，
    由调用方在 `placed_index` 缺失时拒绝）。
    """

    floor = 1
    for prereq in edges.get(course.course_id, ()):
        placed = placed_index.get(prereq)
        if placed is None:
            # 先修未能落位 ⇒ 本课同样不可落位（由调用方检查）。
            return 0
        floor = max(floor, placed + 1)
    return floor


def _candidate_positions(
    course: CurriculumCourse,
    *,
    labels: Sequence[str],
    floor: int,
    deadline: int | None,
) -> list[int]:
    """候选学期顺序：建议学期优先，其次是 floor..limit 的升序。"""

    limit = deadline if deadline is not None else len(labels)
    preference = course.recommended_semester
    order: list[int] = []
    if preference is not None and 1 <= preference <= len(labels):
        order.append(preference)
    order.extend(position for position in range(floor, limit + 1) if position not in order)
    return [position for position in order if floor <= position <= limit]


def _fits_budget(
    credit: float,
    label: str,
    *,
    budget: Mapping[str, float],
    used_credit: Mapping[str, float],
) -> bool:
    cap = budget.get(label)
    if cap is None:
        return True
    return used_credit[label] + credit <= cap


def _place_required(
    course: CurriculumCourse,
    *,
    labels: Sequence[str],
    budget: Mapping[str, float],
    used_credit: dict[str, float],
    prerequisite_edges: Mapping[str, tuple[str, ...]],
    placed_index: Mapping[str, int],
    unresolved: list[str],
) -> _Placement | None:
    """必修课落位：截止学期是**硬约束**，建议学期是**偏好**。"""

    deadline = course.deadline_semester
    if deadline is not None and not (1 <= deadline <= len(labels)):
        unresolved.append(
            f"课程 {course.course_id} 的 deadline_semester={deadline} 落在本次提供的学期范围"
            f"（1..{len(labels)}）之外；⛔ 不猜测该学期，未排入路线图。"
        )
        return None

    floor = _prerequisite_floor(
        course, edges=prerequisite_edges, placed_index=placed_index
    )
    if floor == 0:
        unresolved.append(
            f"课程 {course.course_id} 的先修课程未能排入本次学期范围；"
            f"⛔ 不压缩先修顺序，未排入路线图。"
        )
        return None
    if floor > len(labels):
        unresolved.append(
            f"课程 {course.course_id} 的先修顺序要求最早已是第 {floor} 个学期，"
            f"而本次只提供 {len(labels)} 个学期；⛔ 不压缩先修顺序，未排入路线图。"
        )
        return None

    recommended = course.recommended_semester
    if recommended is not None and not (1 <= recommended <= len(labels)):
        unresolved.append(
            f"课程 {course.course_id} 的 recommended_semester={recommended} 落在本次提供的"
            f"学期范围（1..{len(labels)}）之外；仅按截止学期与先修顺序安排。"
        )

    for position in _candidate_positions(
        course, labels=labels, floor=floor, deadline=deadline
    ):
        label = labels[position - 1]
        if not _fits_budget(
            float(course.credit), label, budget=budget, used_credit=used_credit
        ):
            continue
        return _Placement(
            course,
            position,
            *_required_reason(
                course,
                position,
                floor=floor,
                deadline=deadline,
            ),
        )

    if deadline is not None:
        unresolved.append(
            f"课程 {course.course_id} 无法在不晚于第 {deadline} 个学期、且满足先修与学分预算的"
            f"前提下安排；⛔ 不违反截止学期，未排入路线图。"
        )
    else:
        unresolved.append(
            f"课程 {course.course_id} 在本次学期范围的学分预算内无法安排；"
            f"⛔ 不超出预算，未排入路线图。"
        )
    return None


def _required_reason(
    course: CurriculumCourse,
    position: int,
    *,
    floor: int,
    deadline: int | None,
) -> tuple[PlacementReason, str]:
    """返回 `(placement, reason)`（原因分类 + 人类可读说明）。"""

    if floor > 1 and position == floor:
        return (
            PlacementReason.PREREQUISITE_ORDER,
            f"课程 {course.course_id}（{course.course_name}）的先修课程须先完成，"
            f"因此排在第 {position} 个学期。",
        )
    if course.recommended_semester == position:
        return (
            PlacementReason.REQUIRED_BY_RECOMMENDED_TERM,
            f"课程 {course.course_id}（{course.course_name}）为培养方案要求课程，"
            f"按其建议学期排在第 {position} 个学期。",
        )
    if deadline is not None and position < deadline:
        return (
            PlacementReason.REQUIRED_BEFORE_DEADLINE,
            f"课程 {course.course_id}（{course.course_name}）须在第 {deadline} 个学期前完成，"
            f"排在第 {position} 个学期。",
        )
    if deadline is not None:
        return (
            PlacementReason.DEFERRED_FOR_CREDIT_BUDGET,
            f"课程 {course.course_id}（{course.course_name}）受先修或学分预算影响，"
            f"排在第 {position} 个学期（仍不晚于截止学期 {deadline}）。",
        )
    return (
        PlacementReason.DEFERRED_FOR_CREDIT_BUDGET,
        f"课程 {course.course_id}（{course.course_name}）受先修或学分预算影响，"
        f"排在第 {position} 个学期。",
    )


def _place_elective(
    course: CurriculumCourse,
    *,
    labels: Sequence[str],
    budget: Mapping[str, float],
    used_credit: dict[str, float],
    prerequisite_edges: Mapping[str, tuple[str, ...]],
    placed_index: Mapping[str, int],
    unresolved: list[str],
) -> _Placement | None:
    """选修课落位：只为满足 group 最低学分而选，受先修与预算约束。"""

    deadline = course.deadline_semester
    if deadline is not None and not (1 <= deadline <= len(labels)):
        unresolved.append(
            f"选修课程 {course.course_id} 的 deadline_semester={deadline} 落在本次提供的学期"
            f"范围之外；⛔ 不猜测该学期，未排入路线图。"
        )
        return None

    floor = _prerequisite_floor(
        course, edges=prerequisite_edges, placed_index=placed_index
    )
    if floor == 0:
        unresolved.append(
            f"选修课程 {course.course_id} 的先修课程未能排入本次学期范围；"
            f"⛔ 不压缩先修顺序，未排入路线图。"
        )
        return None
    if floor > len(labels):
        unresolved.append(
            f"选修课程 {course.course_id} 的先修顺序要求最早已是第 {floor} 个学期，"
            f"而本次只提供 {len(labels)} 个学期；未排入路线图。"
        )
        return None
    if deadline is not None and deadline < floor:
        unresolved.append(
            f"选修课程 {course.course_id} 的截止学期早于其先修顺序；"
            f"⛔ 不违反先修，未排入路线图。"
        )
        return None

    for position in _candidate_positions(
        course, labels=labels, floor=floor, deadline=deadline
    ):
        label = labels[position - 1]
        if not _fits_budget(
            float(course.credit), label, budget=budget, used_credit=used_credit
        ):
            continue
        return _Placement(
            course,
            position,
            PlacementReason.ELECTIVE_TO_MEET_GROUP_MINIMUM,
            f"选修课程 {course.course_id}（{course.course_name}）用于满足专业选修组最低学分，"
            f"排在第 {position} 个学期；⛔ 选修组内并非每门课都必须修读。",
        )
    unresolved.append(
        f"选修课程 {course.course_id} 在本次学期范围的先修与学分预算内无法安排；"
        f"⛔ 不超出预算。"
    )
    return None
