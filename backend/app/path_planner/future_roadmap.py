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
from app.models.contracts import MakeupStatus, MakeupTask

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
    curriculum_semester: int
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
    """调用方声明的**未来**学期，含显式的**培养方案学期号**。

    ⚠️ 关键语义（⛔ 不得回退）：`recommended_semester` / `deadline_semester` 是
    **培养方案相对学期号**（例如某专业第 3 学期 = `2026-1`），**不是**本次未来学期
    列表里的第几项。因此本模型同时携带：

    - `semester_label` —— 人类可读学期标签（如 `2026-2`）；
    - `curriculum_semester` —— 该标签对应的**培养方案学期号**（由调用方显式给出）。

    ⛔ 允许学期号不连续/不从 1 开始（例如只规划第 4、6 学期）；
    ⛔ 但**不允许**缺失或与标签不一致的映射。
    """

    semester_label: str
    curriculum_semester: int
    semester_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.semester_label, str) or not self.semester_label.strip():
            raise RoadmapInputError("semester_label 必须是非空字符串。")
        if (
            isinstance(self.curriculum_semester, bool)
            or not isinstance(self.curriculum_semester, int)
            or self.curriculum_semester < 1
        ):
            raise RoadmapInputError("curriculum_semester 必须是 ≥1 的整数。")
        if (
            isinstance(self.semester_index, bool)
            or not isinstance(self.semester_index, int)
            or self.semester_index < 1
        ):
            raise RoadmapInputError("semester_index 必须是 ≥1 的整数。")


@dataclass(frozen=True, slots=True)
class AcademicRoadmap:
    """完整路线图：当前学期摘要 + 未来学期课程级计划 + 选修学分账。"""

    current_semester: str | None
    current_semester_planned_course_ids: tuple[str, ...]
    future_semesters: tuple[SemesterPlan, ...]
    elective_requirement_credit: float | None
    elective_completed_credit: float | None
    elective_current_semester_credit: float
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

    @property
    def curriculum_semester_map(self) -> tuple[tuple[str, int], ...]:
        """`(semester_label, curriculum_semester)` 的显式映射（供审计 / 前端展示）。"""

        return tuple(
            (item.semester_label, item.curriculum_semester)
            for item in self.future_semesters
        )


@dataclass
class _Placement:
    course: CurriculumCourse
    semester_label: str
    reason: PlacementReason
    note: str = ""


def _round_credit(value: float) -> float:
    return round(float(value), 6)


def _require_semesters(
    semesters: Sequence[str] | Sequence[FutureSemester] | Mapping[str, int],
) -> tuple[FutureSemester, ...]:
    """把调用方声明的未来学期规范化成显式 `(label, curriculum_semester)` 映射。

    接受三种显式声明形式（⛔ 都必须**显式**给出培养方案学期号）：

    ```text
    1) Mapping[str, int]              {"2026-2": 4, "2027-1": 5, "2027-2": 6}
    2) Sequence[FutureSemester]       [FutureSemester(...), ...]
    3) Sequence[str] + 显式编号参数    → 由 build_academic_roadmap 的
                                       from_curriculum_semester= 补全
    ```

    ⛔ 绝不把"未来学期列表的第 N 项"当成培养方案第 N 学期：
    调用方不给出映射（既不是 Mapping，也没有 `from_curriculum_semester`）⇒ fail closed。
    """

    if isinstance(semesters, Mapping):
        if not semesters:
            raise RoadmapInputError("semesters 映射不能为空。")
        entries: list[tuple[str, int]] = []
        for label, number in semesters.items():
            if not isinstance(label, str) or not label.strip():
                raise RoadmapInputError("学期标签必须是非空字符串。")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise RoadmapInputError(
                    "培养方案学期号必须是 ≥1 的整数（⛔ 不接受省略或推断）。"
                )
            entries.append((label.strip(), number))
        labels = [item[0] for item in entries]
        if len(set(labels)) != len(labels):
            raise RoadmapInputError("semesters 存在重复学期标签。")
        if len({item[1] for item in entries}) != len(entries):
            raise RoadmapInputError("semesters 存在重复的培养方案学期号。")
        return tuple(
            FutureSemester(semester_label=label, curriculum_semester=number, semester_index=index)
            for index, (label, number) in enumerate(entries, start=1)
        )

    if isinstance(semesters, (str, bytes)) or not isinstance(semesters, Sequence):
        raise RoadmapInputError(
            "semesters 必须是 学期标签 -> 培养方案学期号 的映射，"
            "或 FutureSemester 序列，或学期标签序列 + from_curriculum_semester。"
        )
    material = tuple(semesters)
    if not material:
        raise RoadmapInputError("semesters 不能为空：未来学期顺序必须由调用方显式声明。")

    if all(isinstance(item, FutureSemester) for item in material):
        labels = [item.semester_label for item in material]
        if len(set(labels)) != len(labels):
            raise RoadmapInputError("semesters 存在重复学期标签。")
        numbers = [item.curriculum_semester for item in material]
        if len(set(numbers)) != len(numbers):
            raise RoadmapInputError("semesters 存在重复的培养方案学期号。")
        return tuple(
            FutureSemester(
                semester_label=item.semester_label,
                curriculum_semester=item.curriculum_semester,
                semester_index=index,
            )
            for index, item in enumerate(material, start=1)
        )

    for item in material:
        if not isinstance(item, str) or not item.strip():
            raise RoadmapInputError(
                "semesters 必须是纯学期标签序列（培养方案学期号须由调用方显式提供）。"
            )
    if len(set(material)) != len(material):
        raise RoadmapInputError("semesters 存在重复学期标签。")
    # ⛔ 纯标签序列在这里**不能**自行编号：必须由调用方给出显式映射。
    raise RoadmapInputError(
        "仅给出学期标签不足以确定培养方案学期号（⛔ 不会默认从 1 开始编号）："
        "请传入 学期标签 -> 培养方案学期号 的映射、FutureSemester 序列，"
        "或额外显式提供 from_curriculum_semester。"
    )


def _sequential_semesters(
    labels: Sequence[str], *, from_curriculum_semester: int
) -> tuple[FutureSemester, ...]:
    """由调用方显式给出的**起始培养方案学期号**顺序编号（4,5,6,...）。"""

    if (
        isinstance(from_curriculum_semester, bool)
        or not isinstance(from_curriculum_semester, int)
        or from_curriculum_semester < 1
    ):
        raise RoadmapInputError("from_curriculum_semester 必须是 ≥1 的整数。")
    material = tuple(labels)
    if not material:
        raise RoadmapInputError("semesters 不能为空。")
    for item in material:
        if not isinstance(item, str) or not item.strip():
            raise RoadmapInputError("semesters 中的学期标签必须是非空字符串。")
    if len(set(material)) != len(material):
        raise RoadmapInputError("semesters 存在重复学期标签。")
    return tuple(
        FutureSemester(
            semester_label=item.strip(),
            curriculum_semester=from_curriculum_semester + offset,
            semester_index=offset + 1,
        )
        for offset, item in enumerate(material)
    )


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
    semesters: Sequence[str] | Sequence[FutureSemester] | Mapping[str, int],
    from_curriculum_semester: int | None = None,
    confirmed_satisfied_course_ids: Sequence[str] = (),
    makeup_tasks: Sequence[MakeupTask] = (),
    current_semester: str | None = None,
    current_semester_courses: Sequence[CurriculumCourse] = (),
    elective_group_id: str | None = None,
    elective_completed_course_ids: Sequence[str] | None = None,
    elective_current_semester_course_ids: Sequence[str] | None = None,
    per_semester_credit_budget: Mapping[str, float] | None = None,
) -> AcademicRoadmap:
    """生成**课程级**未来学期路线图（只依赖培养方案事实）。

    参数：

    - `version` —— 目标培养方案（`CurriculumCourse` / `CurriculumGroup` 事实）；
    - `semesters` —— **未来**学期声明，**必须显式给出培养方案学期号**，三种形式：
      `{标签: 培养方案学期号}` 映射 / `FutureSemester` 序列 /
      纯标签序列 **+** `from_curriculum_semester`。
      ⛔ 绝不把"列表第 N 项"当成培养方案第 N 学期；
    - `from_curriculum_semester` —— 第一项未来的培养方案学期号（如 4 ⇒ 4,5,6...）；
      仅在 `semesters` 为纯标签序列时使用，用来**显式**顺序编号；
    - `confirmed_satisfied_course_ids` —— **Curriculum 层已确认满足**的目标课程号
      （例如 `MakeupTask.status == satisfied`）。⛔ 本模块不做任何识别：
      不按课程名匹配、不从成绩单推断、不做等价判定；
    - `makeup_tasks` —— 可选的 Curriculum 事实；本模块**只**采纳
      `status == satisfied` 的条目，⛔ `manual_confirmation` /
      `possibly_equivalent` **绝不**被提升为"已满足"；
    - `completed` —— 原始已修事实。⚠️ 其 `course_id` **不是**唯一机制：
      真实成绩单 PDF 不提供官方课程号，因此已满足事实要主要由
      `confirmed_satisfied_course_ids` / `makeup_tasks` 提供；
    - `current_semester` / `current_semester_courses` —— 当前学期**摘要**：
      ⛔ 本模块**不**重新生成当前学期教学班选择，只把它当作"不要再排一遍"的输入；
    - `elective_group_id` —— 需要满足最低学分的选修组；
    - `elective_completed_course_ids` —— **调用方确认**已归属该选修组的**已修**课程号；
      ⛔ `None`（缺省）表示**证据不足**：此时不猜，`elective_completed_credit`
      与 `elective_remaining_credit` 报 `None`，并写入 `unresolved`；
    - `elective_current_semester_course_ids` —— **调用方确认**本学期已选、且归属该
      选修组的课程号；这些学分**计入**选修组最低学分（见 `elective_current_semester_credit`）；
    - `per_semester_credit_budget` —— 每学期学分上限（可选）；缺省表示不设上限，
      并在 `warnings` 中如实说明。
    """

    if not isinstance(version, CurriculumVersion):
        raise RoadmapInputError("version 必须是 CurriculumVersion。")

    # ---- 未来学期：显式 (标签, 培养方案学期号) 映射（⛔ 不从 1 隐式编号） ----------
    if isinstance(semesters, Mapping):
        declared = _require_semesters(semesters)
        if from_curriculum_semester is not None:
            raise RoadmapInputError(
                "semesters 已自带培养方案学期号；⛔ 不得同时再传 from_curriculum_semester"
                "（两套编号来源会互相矛盾）。"
            )
    elif isinstance(semesters, Sequence) and not isinstance(semesters, (str, bytes)) and all(
        isinstance(item, FutureSemester) for item in semesters
    ):
        declared = _require_semesters(semesters)
        if from_curriculum_semester is not None:
            raise RoadmapInputError(
                "semesters 已自带培养方案学期号；⛔ 不得同时再传 from_curriculum_semester"
                "（两套编号来源会互相矛盾）。"
            )
    else:
        if from_curriculum_semester is None:
            # ⛔ 纯标签序列无法确定培养方案学期号 ⇒ fail closed（不默认从 1 开始）。
            raise RoadmapInputError(
                "仅给出学期标签不足以确定培养方案学期号（⛔ 不会默认从 1 开始编号）："
                "请传入 学期标签 -> 培养方案学期号 的映射、FutureSemester 序列，"
                "或额外显式提供 from_curriculum_semester。"
            )
        declared = _sequential_semesters(
            semesters, from_curriculum_semester=from_curriculum_semester
        )

    labels = tuple(item.semester_label for item in declared)
    #: 未来学期在列表中的位置（1..N，仅用于**时间先后**与排序）
    position_of: dict[str, int] = {
        item.semester_label: item.semester_index for item in declared
    }
    #: 显式的 培养方案学期号 → 列表位置 映射（⛔ 唯一允许的学期号解释方式）
    position_by_curriculum_semester: dict[int, int] = {
        item.curriculum_semester: item.semester_index for item in declared
    }
    curriculum_semester_of: dict[str, int] = {
        item.semester_label: item.curriculum_semester for item in declared
    }
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

    # ---- 已满足事实（Curriculum 层确认，⛔ 本模块不做任何识别） ------------------
    satisfied_ids: set[str] = set()
    if isinstance(confirmed_satisfied_course_ids, (str, bytes)) or not isinstance(
        confirmed_satisfied_course_ids, Sequence
    ):
        raise RoadmapInputError("confirmed_satisfied_course_ids 必须是课程号序列。")
    for item in confirmed_satisfied_course_ids:
        if not isinstance(item, str) or not item.strip():
            raise RoadmapInputError(
                "confirmed_satisfied_course_ids 中的课程号必须是非空字符串。"
            )
        satisfied_ids.add(item.strip())

    # ⛔ 只有 satisfied 被采纳；manual_confirmation / possibly_equivalent 一律不提升。
    for task in makeup_tasks:
        if not isinstance(task, MakeupTask):
            raise RoadmapInputError("makeup_tasks 中混入了非 MakeupTask 对象。")
        if task.status is MakeupStatus.SATISFIED:
            satisfied_ids.add(task.course_id)
        elif task.status in (MakeupStatus.MANUAL_CONFIRMATION, MakeupStatus.POSSIBLY_EQUIVALENT):
            warnings.append(
                f"课程 {task.course_id} 的补修状态为 {task.status.value}："
                f"⛔ 该状态**不是**已满足，仍需人工认定，本次按「未满足」处理。"
            )

    # ---- 已修 / 当前学期事实 ----------------------------------------------------
    # ⚠️ 原始 CompletedCourse.course_id 只是**次要**来源：真实成绩单 PDF 不提供官方
    #    课程号，因此已满足事实主要由 confirmed_satisfied_course_ids / makeup_tasks 提供。
    completed_ids: set[str] = set()
    for item in completed:
        if not isinstance(item, CompletedCourse):
            raise RoadmapInputError("completed 中混入了非 CompletedCourse 对象。")
        # ⛔ 只有"已通过 + 身份已确认（course_id 非空）"才计入；
        #    pending（course_id=None）绝不被当成已满足。
        if item.course_id is not None and item.passed:
            completed_ids.add(item.course_id)

    satisfied_all = completed_ids | satisfied_ids

    current_course_ids: set[str] = set()
    for item in current_semester_courses:
        if not isinstance(item, CurriculumCourse):
            raise RoadmapInputError(
                "current_semester_courses 中混入了非 CurriculumCourse 对象。"
            )
        current_course_ids.add(item.course_id)

    # 已满足 / 本学期已覆盖的课不再排入未来学期（⛔ 不重复安排同一门课）。
    planned_pool = [
        course
        for course in version.courses
        if course.course_id not in satisfied_all
        and course.course_id not in current_course_ids
    ]

    # ---- 选修学分账 -------------------------------------------------------------
    elective_requirement = group.minimum_credit if group is not None else None
    elective_completed: float | None = None
    elective_current: float = 0.0
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
        # ⛔ 已计入"已完成选修学分"的课**不得**再被规划一次：把它们从课程池移除，
        #    否则同一门课既被算作已修学分、又被排进未来学期。
        #    （`planned_pool` 已由 satisfied_all 过滤，但调用方通过
        #      `elective_completed_course_ids` 声明的课程不一定出现在 satisfied_all 中。）
        credited_ids = {item for item in confirmed if item in credit_by_id}
        if credited_ids:
            planned_pool = [
                course
                for course in planned_pool
                if course.course_id not in credited_ids
            ]

        # 本学期已选选修学分**计入**选修组最低学分（否则会把已在读的选修重复规划）。
        if elective_current_semester_course_ids is None:
            unresolved.append(
                f"选修组 {group.group_id} 的**本学期选修学分证据不足**"
                f"（调用方未确认本学期已选课程是否归属该组）；⛔ 不计入，"
                f"因此本次选修缺口可能被高估，留待人工确认。"
            )
        else:
            if isinstance(elective_current_semester_course_ids, (str, bytes)) or not isinstance(
                elective_current_semester_course_ids, Sequence
            ):
                raise RoadmapInputError(
                    "elective_current_semester_course_ids 必须是课程号序列。"
                )
            current_group_ids = {
                course.course_id for course in current_semester_courses if _is_member(course, group)
            }
            declared_current = {
                str(item).strip()
                for item in elective_current_semester_course_ids
                if isinstance(item, str) and item.strip()
            }
            unknown_current = sorted(declared_current - current_group_ids)
            if unknown_current:
                unresolved.append(
                    f"调用方声明的本学期选修课程中有 {len(unknown_current)} 门"
                    f"**不是**选修组 {group.group_id} 的培养方案成员（或不是本学期确认课程）；"
                    f"⛔ 不计入选修学分，需人工确认。"
                )
            elective_current = _round_credit(
                sum(
                    float(course.credit)
                    for course in current_semester_courses
                    if _is_member(course, group) and course.course_id in declared_current
                )
            )

        elective_remaining = _round_credit(
            max(elective_requirement - elective_completed - elective_current, 0.0)
        )

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
    #: 已放置课程 → 其**培养方案学期号**（先修先后与截止比较都用它，⛔ 不用列表位置）
    placed_curriculum_semester: dict[str, int] = {}
    used_credit: dict[str, float] = {label: 0.0 for label in labels}

    # ---- 1) 必修课：先修顺序 → 截止学期（硬）→ 建议学期（偏好）→ 学分预算 --------
    for course in required_queue:
        placement = _place_required(
            course,
            curriculum_semesters=tuple(
                item.curriculum_semester for item in declared
            ),
            position_by_curriculum_semester=position_by_curriculum_semester,
            curriculum_semester_of=curriculum_semester_of,
            budget=budget,
            used_credit=used_credit,
            prerequisite_edges=prerequisite_edges,
            placed_curriculum_semester=placed_curriculum_semester,
            unresolved=unresolved,
        )
        if placement is None:
            continue
        placements.append(placement)
        placed_curriculum_semester[course.course_id] = curriculum_semester_of[
            placement.semester_label
        ]
        used_credit[placement.semester_label] += float(course.credit)

    # ---- 2) 选修：只选**足够满足 group 最低学分**的学分 --------------------------
    if group is not None and elective_requirement is not None and elective_remaining is not None:
        #: 规划前仍缺的学分（缺口）。
        gap = elective_remaining
        remaining = gap
        for course in elective_pool:
            if remaining <= 0:
                break
            if float(course.credit) > remaining:
                # ⛔ 不超额规划：只选"装得进缺口"的课程，避免为凑学分多修整门课。
                #    （缺口可能因此无法被精确填满，届时如实报 unresolved。）
                continue
            placement = _place_elective(
                course,
                curriculum_semesters=tuple(item.curriculum_semester for item in declared),
                position_by_curriculum_semester=position_by_curriculum_semester,
                curriculum_semester_of=curriculum_semester_of,
                budget=budget,
                used_credit=used_credit,
                prerequisite_edges=prerequisite_edges,
                placed_curriculum_semester=placed_curriculum_semester,
                unresolved=unresolved,
            )
            if placement is None:
                continue
            placements.append(placement)
            placed_curriculum_semester[course.course_id] = curriculum_semester_of[
                placement.semester_label
            ]
            used_credit[placement.semester_label] += float(course.credit)
            remaining = _round_credit(remaining - float(course.credit))
        elective_planned = _round_credit(gap - max(remaining, 0.0))
        # `elective_remaining_credit` 语义 = **规划之后**仍缺的学分。
        elective_remaining = _round_credit(max(remaining, 0.0))
        if remaining > 0:
            unresolved.append(
                f"选修组 {group.group_id} 仍缺 {remaining} 学分：当前培养方案成员不足以满足"
                f"最低学分，或受先修 / 学分预算限制；⛔ 不编造课程来补齐。"
            )

    # ---- 组装学期计划 -----------------------------------------------------------
    by_semester: dict[int, list[_Placement]] = {
        item.semester_index: [] for item in declared
    }
    for placement in placements:
        by_semester[position_of[placement.semester_label]].append(placement)

    future: list[SemesterPlan] = []
    for item in declared:
        label = item.semester_label
        index = item.semester_index
        items = sorted(by_semester[index], key=lambda entry: entry.course.course_id)
        semester_warnings: list[str] = []
        cap = budget.get(label)
        total = _round_credit(sum(float(entry.course.credit) for entry in items))
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
                curriculum_semester=item.curriculum_semester,
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
        elective_current_semester_credit=elective_current,
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
    placed_curriculum_semester: Mapping[str, int],
    curriculum_semesters: Sequence[int],
) -> int | None:
    """先修约束下的最早**培养方案学期号**（floor）。

    ⚠️ 先修先后使用的是**培养方案学期号**（同一个学期轴），
    ⛔ 不是未来学期在列表中的位置；因此列表顺序变化不影响先修判断。

    调用方保证课程按先修拓扑序处理，因此每个先修**必然**已处理：
    要么已落位（取其学期号 + 1），要么不可落位（返回 `None` ⇒ 本课也不可落位）。
    """

    if not curriculum_semesters:
        return None
    floor = min(curriculum_semesters)
    for prereq in edges.get(course.course_id, ()):
        placed = placed_curriculum_semester.get(prereq)
        if placed is None:
            return None
        floor = max(floor, placed + 1)
    return floor


def _normalize_floor(
    floor: int | None, curriculum_semesters: Sequence[int]
) -> int | None:
    """把先修 floor **对齐到实际提供的学期号**上。

    先修 floor 可能落在一个**没有未来学期**的学期号上（例如先修排在培养方案第 4 学期，
    于是 floor=5，但本次只规划第 4、5 学期 —— 5 是存在的；若只规划第 4 学期，floor=5
    就落空了）。此时把它抬升到**最小的 ≥ floor 的已提供学期号**，
    仍然严格满足"晚于先修"；若不存在这样的学期 ⇒ `None`（fail closed，⛔ 不压缩先修）。
    """

    if floor is None:
        return None
    reachable = sorted(item for item in curriculum_semesters if item >= floor)
    return reachable[0] if reachable else None


def _candidate_labels(
    course: CurriculumCourse,
    *,
    declared: Sequence[FutureSemester],
    floor: int | None,
    deadline: int | None,
    prefer_latest: bool,
) -> list[str]:
    """候选学期标签顺序（⛔ 全部按**培养方案学期号**判断，与列表位置无关）。

    - `prefer_latest=True`（必修课）：优先**建议学期**；没有可行的建议学期时退到
      **截止学期**（在截止前完成即可，不提前占用学期）；都没有才用最早可行学期。
    - `prefer_latest=False`（选修填充）：优先**建议学期**，否则用最早可行学期
      （尽早补足选修缺口）。

    候选一律被裁剪到 `[floor, deadline]` 之内：
    先修先后（floor）与截止学期（deadline）都是**硬约束**。
    """

    floor_value = floor if floor is not None else -1
    limit = deadline if deadline is not None else 10**6
    eligible = sorted(
        (
            item
            for item in declared
            if floor_value <= item.curriculum_semester <= limit
        ),
        key=lambda item: item.curriculum_semester,
    )
    if not eligible:
        return []

    preference = course.recommended_semester
    preferred = [
        item
        for item in eligible
        if preference is not None and item.curriculum_semester == preference
    ]

    if prefer_latest:
        tail = [eligible[-1]] if deadline is not None else []
    else:
        tail = []

    ordered: list[FutureSemester] = []
    for group in (preferred, tail, eligible):
        for item in group:
            if item not in ordered:
                ordered.append(item)
    return [item.semester_label for item in ordered]


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
    curriculum_semesters: Sequence[int],
    position_by_curriculum_semester: Mapping[int, int],
    curriculum_semester_of: Mapping[str, int],
    budget: Mapping[str, float],
    used_credit: dict[str, float],
    prerequisite_edges: Mapping[str, tuple[str, ...]],
    placed_curriculum_semester: Mapping[str, int],
    unresolved: list[str],
) -> _Placement | None:
    """必修课落位：截止学期是**硬约束**，建议学期是**偏好**。

    ⚠️ `recommended_semester` / `deadline_semester` 是**培养方案学期号**，
    与 `future_semesters[].curriculum_semester` 直接比较；⛔ 不与列表位置比较。
    """

    declared = _declared_from_maps(
        position_by_curriculum_semester, curriculum_semester_of
    )
    deadline = course.deadline_semester
    if deadline is not None and deadline not in position_by_curriculum_semester:
        unresolved.append(
            f"课程 {course.course_id} 的 deadline_semester={deadline}（培养方案学期号）"
            f"不在本次提供的学期映射 {list(curriculum_semesters)} 中；"
            f"⛔ 不猜测该学期，未排入路线图。"
        )
        return None

    floor = _prerequisite_floor(
        course,
        edges=prerequisite_edges,
        placed_curriculum_semester=placed_curriculum_semester,
        curriculum_semesters=curriculum_semesters,
    )
    floor = _normalize_floor(floor, curriculum_semesters)
    if floor is None:
        unresolved.append(
            f"课程 {course.course_id} 的先修课程未能排入本次学期范围；"
            f"⛔ 不压缩先修顺序，未排入路线图。"
        )
        return None

    recommended = course.recommended_semester
    if recommended is not None and recommended not in position_by_curriculum_semester:
        unresolved.append(
            f"课程 {course.course_id} 的 recommended_semester={recommended}（培养方案学期号）"
            f"不在本次提供的学期映射中；仅按截止学期与先修顺序安排。"
        )

    for label in _candidate_labels(
        course, declared=declared, floor=floor, deadline=deadline, prefer_latest=True
    ):
        if not _fits_budget(
            float(course.credit), label, budget=budget, used_credit=used_credit
        ):
            continue
        return _Placement(
            course,
            label,
            *_required_reason(
                course,
                curriculum_semester_of[label],
                floor=floor,
                deadline=deadline,
            ),
        )

    if deadline is not None:
        unresolved.append(
            f"课程 {course.course_id} 无法在不晚于培养方案第 {deadline} 学期、"
            f"且满足先修与学分预算的前提下安排；⛔ 不违反截止学期，未排入路线图。"
        )
    else:
        unresolved.append(
            f"课程 {course.course_id} 在本次学期范围的学分预算内无法安排；"
            f"⛔ 不超出预算，未排入路线图。"
        )
    return None


def _declared_from_maps(
    position_by_curriculum_semester: Mapping[int, int],
    curriculum_semester_of: Mapping[str, int],
) -> list[FutureSemester]:
    """由既有映射重建 `FutureSemester` 列表（仅供候选顺序计算，⛔ 不引入新事实）。"""

    rebuilt = [
        FutureSemester(
            semester_label=label,
            curriculum_semester=number,
            semester_index=position_by_curriculum_semester[number],
        )
        for label, number in curriculum_semester_of.items()
    ]
    return sorted(rebuilt, key=lambda item: item.semester_index)


def _required_reason(
    course: CurriculumCourse,
    curriculum_semester: int,
    *,
    floor: int | None,
    deadline: int | None,
) -> tuple[PlacementReason, str]:
    """返回 `(placement, reason)`（原因分类 + 人类可读说明）。

    ⚠️ 文案里的"第 N 学期"指**培养方案学期号**，与 `recommended_semester` /
    `deadline_semester` 同一口径（⛔ 不是未来学期列表位置）。
    """

    if course.recommended_semester == curriculum_semester:
        return (
            PlacementReason.REQUIRED_BY_RECOMMENDED_TERM,
            f"课程 {course.course_id}（{course.course_name}）为培养方案要求课程，"
            f"按其建议学期（培养方案第 {curriculum_semester} 学期）安排。",
        )
    if floor is not None and curriculum_semester == floor:
        return (
            PlacementReason.PREREQUISITE_ORDER,
            f"课程 {course.course_id}（{course.course_name}）的先修课程须先完成，"
            f"因此排在培养方案第 {curriculum_semester} 学期。",
        )
    if deadline is not None and curriculum_semester < deadline:
        return (
            PlacementReason.REQUIRED_BEFORE_DEADLINE,
            f"课程 {course.course_id}（{course.course_name}）须在培养方案第 {deadline} 学期前完成，"
            f"排在第 {curriculum_semester} 学期。",
        )
    if deadline is not None:
        return (
            PlacementReason.DEFERRED_FOR_CREDIT_BUDGET,
            f"课程 {course.course_id}（{course.course_name}）受先修或学分预算影响，"
            f"排在培养方案第 {curriculum_semester} 学期（仍不晚于截止学期 {deadline}）。",
        )
    return (
        PlacementReason.DEFERRED_FOR_CREDIT_BUDGET,
        f"课程 {course.course_id}（{course.course_name}）受先修或学分预算影响，"
        f"排在培养方案第 {curriculum_semester} 学期。",
    )


def _place_elective(
    course: CurriculumCourse,
    *,
    curriculum_semesters: Sequence[int],
    position_by_curriculum_semester: Mapping[int, int],
    curriculum_semester_of: Mapping[str, int],
    budget: Mapping[str, float],
    used_credit: dict[str, float],
    prerequisite_edges: Mapping[str, tuple[str, ...]],
    placed_curriculum_semester: Mapping[str, int],
    unresolved: list[str],
) -> _Placement | None:
    """选修课落位：只为满足 group 最低学分而选，受先修与预算约束。"""

    declared = _declared_from_maps(
        position_by_curriculum_semester, curriculum_semester_of
    )
    deadline = course.deadline_semester
    if deadline is not None and deadline not in position_by_curriculum_semester:
        unresolved.append(
            f"选修课程 {course.course_id} 的 deadline_semester={deadline}（培养方案学期号）"
            f"不在本次提供的学期映射中；⛔ 不猜测该学期，未排入路线图。"
        )
        return None

    floor = _prerequisite_floor(
        course,
        edges=prerequisite_edges,
        placed_curriculum_semester=placed_curriculum_semester,
        curriculum_semesters=curriculum_semesters,
    )
    floor = _normalize_floor(floor, curriculum_semesters)
    if floor is None:
        unresolved.append(
            f"选修课程 {course.course_id} 的先修课程未能排入本次学期范围；"
            f"⛔ 不压缩先修顺序，未排入路线图。"
        )
        return None
    if deadline is not None and deadline < floor:
        unresolved.append(
            f"选修课程 {course.course_id} 的截止学期早于其先修顺序；"
            f"⛔ 不违反先修，未排入路线图。"
        )
        return None

    for label in _candidate_labels(
        course, declared=declared, floor=floor, deadline=deadline, prefer_latest=False
    ):
        if not _fits_budget(
            float(course.credit), label, budget=budget, used_credit=used_credit
        ):
            continue
        return _Placement(
            course,
            label,
            PlacementReason.ELECTIVE_TO_MEET_GROUP_MINIMUM,
            f"选修课程 {course.course_id}（{course.course_name}）用于满足专业选修组最低学分，"
            f"排在培养方案第 {curriculum_semester_of[label]} 学期；"
            f"⛔ 选修组内并非每门课都必须修读。",
        )
    unresolved.append(
        f"选修课程 {course.course_id} 在本次学期范围的先修与学分预算内无法安排；"
        f"⛔ 不超出预算。"
    )
    return None
