"""Case A roadmap wiring: turn **Curriculum facts** into a course-level roadmap.

```text
CurriculumCase（真实培养方案事实）
  + 本次导入的成绩单投影结果 MakeupTask[]
        ↓  build_case_a_roadmap()
AcademicRoadmap（app.path_planner，课程级；⛔ 不含任何教学班级字段）
```

## 为什么需要这一层

`app.path_planner.future_roadmap` 刻意保持"只吃已给出的培养方案事实"，
并要求调用方**显式**给出培养方案学期号映射与"已确认满足"事实。
本模块负责把 Case A 的**真实**事实翻译成那些输入，且：

- ⛔ 不做课程识别、不做等价判定、不按课程名匹配、不从成绩单推断；
- ⛔ 不访问 Course Data（未来学期不需要任何教学班数据）；
- ⛔ 不编造任何培养方案事实：只使用 `CurriculumCourse` 上已给出的取值；
- ⛔ 不把选修池整池当作必修。

## 学期号从哪来（⛔ 不得从 1 重新编号）

真实 Case A 培养方案**只有** `recommended_term_text`（如 `2027-1`），
**没有** `recommended_semester` / `deadline_semester` 整数字段。
因此本模块把"培养方案学期号"定义为**课程自身学期标签的稳定序号**：

```text
label  = "YYYY-H"（H ∈ {1,2}）
number = 以 current_semester 为 1 的连续序号（升序、连续、不跳号）
```

- 参照学期 = 当前学期（调用方显式给出，如 `2026-1`）；
- 学期集合 = 培养方案里**真实出现过**的学期标签 ∪ {参照学期}；
- ⛔ 绝不出现"未来学期从 1 重新编号"：未来学期一律用整条链上的学期号；
- 同一份培养方案 + 同一份输入 ⇒ 同一路线图（确定性）。

单学期标签（`2027-1`）直接映射为该学期；
区间标签（`2025-1~2025-2`、`2025-1~2028-2`）**不由本模块猜测方向**：
它们必须已由 Curriculum 的 scope decision 裁决（historical / future）。
本模块只对 `future` 的区间取**其自身写明的结束学期**；
historical（或未被裁决）的区间不参与未来规划，并如实记入 `unresolved`。
"""

from __future__ import annotations

from collections.abc import Sequence, Set as AbstractSet
from dataclasses import dataclass

from app.curriculum.case import CurriculumCase
from app.curriculum.requirements import CurriculumCourse, CurriculumGroup, RequirementKind
from app.curriculum.terms import (
    AcademicTerm,
    SCOPE_FUTURE,
    parse_academic_term,
)
from app.models.contracts import CourseOffering, MakeupStatus, MakeupTask
from app.path_planner import AcademicRoadmap, FutureSemester, build_academic_roadmap

__all__ = [
    "CaseARoadmapError",
    "CurriculumTermChain",
    "bind_current_semester_courses",
    "build_case_a_roadmap",
    "derive_term_chain",
    "future_semesters_after",
    "observed_term_facts",
    "requirement_kind_label",
    "resolve_course_target_terms",
]


class CaseARoadmapError(ValueError):
    """Case A 路线图输入不成立（fail closed，⛔ 不猜测）。"""


@dataclass(frozen=True, slots=True)
class CurriculumTermChain:
    """培养方案学期号链（由**真实学期标签**推导，⛔ 不从 1 任意开始）。"""

    reference_term: AcademicTerm
    term_index: dict[str, int]
    label_by_index: dict[int, str]

    def index_of(self, term: AcademicTerm) -> int | None:
        return self.term_index.get(str(term))

    def label_of(self, index: int) -> str | None:
        return self.label_by_index.get(index)


def derive_term_chain(
    terms: Sequence[AcademicTerm],
    *,
    reference_term: AcademicTerm,
) -> CurriculumTermChain:
    """把**真实出现过**的学期编号成连续的培养方案学期号链。

    ⛔ 只对真实存在的学期编号；没有学期事实的课程不会被编造学期。
    """

    if not isinstance(reference_term, AcademicTerm):
        raise CaseARoadmapError("reference_term 必须是 AcademicTerm。")
    values = sorted({(term.year, term.half) for term in terms} | {(reference_term.year, reference_term.half)})
    if not values:
        raise CaseARoadmapError("没有任何学期事实，无法建立学期号链。")

    term_index: dict[str, int] = {}
    label_by_index: dict[int, str] = {}
    for offset, (year, half) in enumerate(values):
        number = offset + 1
        label = f"{year}-{half}"
        term_index[label] = number
        label_by_index[number] = label
    return CurriculumTermChain(
        reference_term=reference_term,
        term_index=term_index,
        label_by_index=label_by_index,
    )


def _split_range(text: str) -> tuple[str, str] | None:
    if "~" not in text:
        return None
    left, _, right = text.partition("~")
    return left.strip(), right.strip()


def resolve_course_target_terms(
    case: CurriculumCase,
) -> tuple[dict[str, AcademicTerm], tuple[str, ...]]:
    """把每门课的 `recommended_term_text` 解析成**目标学期事实**。

    返回 `(course_id -> 目标学期, unresolved 说明)`。规则：

    ```text
    单学期标签                → 该学期
    range 且 scope = future   → 区间**写明的结束学期**（课程自身事实）
    range 且 scope != future  → 不解析（historical 区间不是"待修学期"）
    range 且无 scope decision → 不解析，记 unresolved（⛔ 不猜方向）
    无法解析的文本            → 不解析，记 unresolved
    ```
    """

    decisions = {
        decision.target_source_record: decision.decision
        for decision in case.confirmed_scope_decisions
    }
    resolved: dict[str, AcademicTerm] = {}
    unresolved: list[str] = []

    for course in case.new.courses:
        text = (course.recommended_term_text or "").strip()
        if not text:
            unresolved.append(
                f"课程 {course.course_id} 在培养方案中没有学期事实；"
                f"⛔ 不猜测其开课学期，未排入路线图。"
            )
            continue

        single = parse_academic_term(text)
        if single is not None:
            resolved[course.course_id] = single
            continue

        bounds = _split_range(text)
        if bounds is None:
            unresolved.append(
                f"课程 {course.course_id} 的学期文本无法安全解析；⛔ 不猜测，未排入路线图。"
            )
            continue

        start_text, end_text = bounds
        if parse_academic_term(start_text) is None or parse_academic_term(end_text) is None:
            unresolved.append(
                f"课程 {course.course_id} 的学期区间端点无法解析；⛔ 不猜测，未排入路线图。"
            )
            continue

        decision = decisions.get(course.source_record)
        if decision == SCOPE_FUTURE:
            end = parse_academic_term(end_text)
            assert end is not None  # 已在上方校验
            resolved[course.course_id] = end
        elif decision is None:
            unresolved.append(
                f"课程 {course.course_id} 的学期是区间且没有已确认的 scope 裁决；"
                f"⛔ 不猜测方向，未排入路线图。"
            )
        # decision == historical：该区间是转专业前的历史窗口，不是未来待修学期，
        # 因此**不**放入未来路线图，也**不**报 unresolved（这是已裁决的事实）。

    return resolved, tuple(unresolved)


def future_semesters_after(
    chain: CurriculumTermChain,
    *,
    current_semester_label: str,
    last_curriculum_semester: str | None = None,
) -> tuple[FutureSemester, ...]:
    """当前学期之后的**显式**未来学期序列（标签 + 培养方案学期号）。

    - 起点 = 当前学期在链中的学期号 + 1；
    - 终点 = `last_curriculum_semester`（可选）在链中的学期号，缺省取链尾；
    - ⛔ 序号来自链，**不从 1 重新编号**；⛔ 未来学期不得早于当前学期。
    """

    reference = parse_academic_term(current_semester_label)
    if reference is None:
        raise CaseARoadmapError("当前学期标签无法解析为 YYYY-H（⛔ 不猜测）。")
    current_index = chain.index_of(reference)
    if current_index is None:
        raise CaseARoadmapError("当前学期不在学期号链中。")

    last_index = max(chain.label_by_index)
    if last_curriculum_semester is not None:
        last_term = parse_academic_term(last_curriculum_semester)
        if last_term is None:
            raise CaseARoadmapError("未来学期上界无法解析为 YYYY-H（⛔ 不猜测）。")
        resolved = chain.index_of(last_term)
        if resolved is None:
            raise CaseARoadmapError(
                "未来学期上界不在本次培养方案的学期集合中；⛔ 不猜测其学期号。"
            )
        last_index = resolved
    if last_index <= current_index:
        raise CaseARoadmapError("未来学期上界不晚于当前学期，无法生成未来路线图。")

    # ⚠️ 顺序不变量（结构上成立，无需运行时校验）：
    #    未来学期由 `range(current_index + 1, last_index + 1)` 生成，
    #   因此 `curriculum_semester` 与 `semester_index` **必然**严格递增且不重复。
    #   ⛔ 本函数不会重排调用方给出的顺序，也不会猜测顺序 —— 顺序完全由学期号链决定。
    return tuple(
        FutureSemester(
            semester_label=chain.label_by_index[index],
            curriculum_semester=index,
            semester_index=index - current_index,
        )
        for index in range(current_index + 1, last_index + 1)
    )


def requirement_kind_label(kind: RequirementKind) -> str:
    """`RequirementKind` → 面向用户的中文分类（⛔ 不做业务推断）。"""

    return {
        RequirementKind.REQUIRED: "必修",
        RequirementKind.ELECTIVE: "选修",
        RequirementKind.UNKNOWN: "未分类",
    }[kind]


def observed_term_facts(case: CurriculumCase) -> tuple[AcademicTerm, ...]:
    """课程文本里**真实出现过的**单学期标签（含区间端点）。

    ⚠️ 用途仅限建立学期号链（"培养方案总共有哪些学期"），
    ⛔ **不**用来决定某门课排在哪：区间方向仍由 Kurriculum 的 scope decision 裁决。
    把区间端点也算进学期集合，是为了让学期号链覆盖培养方案的完整时间跨度，
    从而 ⛔ 不会因为"课程全是未来学期"而把未来学期误编号成 1、2。
    """

    found: set[tuple[int, int]] = set()
    for course in case.new.courses:
        text = (course.recommended_term_text or "").strip()
        if not text:
            continue
        single = parse_academic_term(text)
        if single is not None:
            found.add((single.year, single.half))
            continue
        bounds = _split_range(text)
        if bounds is None:
            continue
        for candidate in bounds:
            parsed = parse_academic_term(candidate)
            if parsed is not None:
                found.add((parsed.year, parsed.half))
    return tuple(AcademicTerm(year=year, half=half) for year, half in sorted(found))


def bind_current_semester_courses(
    case: CurriculumCase,
    current_schedule: Sequence[CourseOffering],
    *,
    elective_group_id: str | None = None,
    completed_course_ids: AbstractSet[str] | None = None,
) -> tuple[tuple[CurriculumCourse, ...], tuple[str, ...], tuple[str, ...]]:
    """把**本学期真实教学班**按**精确课程身份**绑定到培养方案课程。

    ⛔ 只按 `course_id` 精确匹配：⛔ 不按课程名匹配、⛔ 不模糊匹配、⛔ 不推断等价。
    绑定结果返回 `(已绑定的培养方案课程, 归属选修组的课程号, 未解析说明)`。

    - 一门课在本学期选了**多个教学班**时只算**一次**（按培养方案课程身份去重）；
    - 教学班课程号不在培养方案里 ⇒ 记入 unresolved 且**不**计入任何学分；
    - `completed_course_ids` 中的课程（已确认满足 / 已计入已完成学分）
      ⇒ **不**计入本学期学分，并记入 unresolved。
      原因：同一 curriculum course identity ⛔ **绝不**同时在
      `elective_completed_credit` 与 `elective_current_semester_credit` 里各算一次；
      一门课不可能既"已确认修完"又"本学期在修"，这是**矛盾状态**，必须如实报告。
    - `elective_group_id=None` ⇒ 不做选修组判定，第二个返回值是空元组。
    """

    if not isinstance(case, CurriculumCase):
        raise CaseARoadmapError("case 必须是 CurriculumCase。")
    already_completed = set(completed_course_ids or ())
    by_id: dict[str, CurriculumCourse] = {}
    for course in case.new.courses:
        by_id.setdefault(course.course_id, course)

    group: CurriculumGroup | None = None
    if elective_group_id is not None:
        # ⚠️ 组不存在时**不在这里**抛错：组校验是 `build_case_a_roadmap` 的职责
        #    （它会对未知组 fail closed）。本函数只做精确身份绑定，
        #    没有该组时自然没有成员可计入 ⇒ 返回空元组。
        group = next(
            (item for item in case.new.groups if item.group_id == elective_group_id), None
        )

    bound: dict[str, CurriculumCourse] = {}
    unresolved: list[str] = []
    for item in current_schedule:
        course = by_id.get(item.course_id)
        if course is None:
            unresolved.append(
                f"本学期课程 {item.course_id}（教学班 {item.class_id}）不在培养方案课程中；"
                f"⛔ 无法按精确课程身份绑定，未计入学分，需人工确认。"
            )
            continue
        if course.course_id in already_completed:
            # ⛔ 双计分防线：已完成身份不得再作为"本学期在修"计一次。
            unresolved.append(
                f"本学期课程 {course.course_id} 已被记为**已确认完成**，"
                f"不能同时计为本学期在修学分；⛔ 本次只算一次（计入已完成），"
                f"需人工确认这条本学期记录是否应保留。"
            )
            continue
        # 同一门课的多个教学班只算一次（按培养方案课程身份去重）。
        bound.setdefault(course.course_id, course)

    elective_ids = tuple(
        sorted(
            course_id
            for course_id, course in bound.items()
            if group is not None and _is_member(course, group)
        )
    )
    return tuple(bound[course_id] for course_id in sorted(bound)), elective_ids, tuple(unresolved)


def _is_member(course: CurriculumCourse, group: CurriculumGroup) -> bool:
    """是否属于该培养方案分组（**精确** `group_id` 相等，⛔ 不推断、不模糊匹配）。"""

    return course.group_id is not None and course.group_id == group.group_id


def _elective_group(case: CurriculumCase, group_id: str) -> CurriculumGroup:
    matches = [item for item in case.new.groups if item.group_id == group_id]
    if not matches:
        raise CaseARoadmapError(
            f"培养方案中不存在选修组 {group_id}；⛔ 不猜测其最低学分。"
        )
    return matches[0]


def build_case_a_roadmap(
    case: CurriculumCase,
    *,
    makeup_tasks: Sequence[MakeupTask],
    current_semester_label: str,
    last_curriculum_semester: str | None = None,
    elective_group_id: str | None = None,
    current_semester_courses: Sequence = (),
    elective_current_semester_course_ids: Sequence[str] | None = None,
) -> AcademicRoadmap:
    """由 Curriculum 事实构建**课程级**未来路线图（⛔ 不触碰任何 CourseOffering）。

    参数：

    - `makeup_tasks` —— Curriculum 的投影结果。**只**采纳
      `status == satisfied` 作为"已确认满足"事实；⛔ `manual_confirmation` /
      `possibly_equivalent` 绝不提升（由 `future_roadmap` 内部保证）；
    - `current_semester_label` —— 当前学期（如 `2026-1`），同时是学期号链的参照学期；
    - `last_curriculum_semester` —— 未来学期上界（可选）；缺省取培养方案链尾；
    - `elective_group_id` —— 需要满足最低学分的选修组；
    - `current_semester_courses` —— 本学期已确认的培养方案课程（避免重复规划）；
    - `elective_current_semester_course_ids` —— 其中**已确认归属该选修组**的课程号；
      ⛔ `None` 表示证据不足（计入 0 并报 unresolved）。
    """

    if not isinstance(case, CurriculumCase):
        raise CaseARoadmapError("case 必须是 CurriculumCase。")
    if not isinstance(current_semester_label, str) or not current_semester_label.strip():
        raise CaseARoadmapError("current_semester_label 必须是非空字符串。")

    target_terms, term_unresolved = resolve_course_target_terms(case)
    reference = parse_academic_term(current_semester_label.strip())
    if reference is None:
        raise CaseARoadmapError("当前学期标签无法解析为 YYYY-H（⛔ 不猜测）。")

    chain = derive_term_chain(observed_term_facts(case), reference_term=reference)
    declared = future_semesters_after(
        chain,
        current_semester_label=current_semester_label.strip(),
        last_curriculum_semester=last_curriculum_semester,
    )
    semester_map = {item.semester_label: item.curriculum_semester for item in declared}

    # 课程级建议学期：直接把课程自己的学期事实折算成学期号（⛔ 不改课程、不改公共契约）。
    # ⚠️ 只登记**未来**学期（> 当前学期）的建议学期：
    #    培养方案里早于当前学期的安排（转专业前的历史窗口）**不是**"未来建议学期"，
    #    把它们当成建议学期会产生"建议学期不在本次映射中"的噪声 unresolved。
    #    ⛔ 这里既没有猜测、也没有改写课程事实，只是不把一个**已过**的学期当作未来偏好。
    current_index_for_preference = chain.index_of(reference)
    recommended_index: dict[str, int] = {}
    for course_id, term in target_terms.items():
        number = chain.index_of(term)
        if number is None:
            continue
        if current_index_for_preference is not None and number <= current_index_for_preference:
            continue
        recommended_index[course_id] = number

    satisfied_course_ids = tuple(
        sorted(
            {
                task.course_id
                for task in makeup_tasks
                if task.status is MakeupStatus.SATISFIED
            }
        )
    )

    # ---- 选修组：最低学分读自 CurriculumGroup；已完成选修学分只用**已确认满足**事实 ----
    elective_completed_course_ids: Sequence[str] | None = None
    if elective_group_id is not None:
        group = _elective_group(case, elective_group_id)
        member_ids = {
            course.course_id
            for course in case.new.courses
            if course.group_id == group.group_id
        }
        # ⛔ 只把"已确认满足 **且** 确实属于该选修组"的课程计入已完成选修学分。
        #    不属于该组的已满足课程**不**计入（⛔ 不猜测组归属）。
        elective_completed_course_ids = tuple(
            sorted(course_id for course_id in satisfied_course_ids if course_id in member_ids)
        )

    # ---- 已完成 / 本学期 选修身份必须**互斥**（⛔ 同一课程身份不得双计分） -------------
    # 第二道防线：即使调用方传入了重叠集合，账目也必须只算一次，并如实报告矛盾。
    overlap_unresolved: list[str] = []
    if elective_current_semester_course_ids is not None:
        completed_set = set(elective_completed_course_ids or ())
        kept: list[str] = []
        for course_id in elective_current_semester_course_ids:
            if course_id in completed_set:
                overlap_unresolved.append(
                    f"选修课程 {course_id} 同时出现在**已确认完成**与**本学期在修**中；"
                    f"⛔ 同一课程身份只计一次（计入已完成），本次不计入本学期学分，"
                    f"需人工确认这条本学期记录是否应保留。"
                )
                continue
            kept.append(course_id)
        elective_current_semester_course_ids = tuple(
            sorted(dict.fromkeys(kept))
        )

    roadmap = build_academic_roadmap(
        version=case.new,
        semesters=semester_map,
        confirmed_satisfied_course_ids=satisfied_course_ids,
        makeup_tasks=tuple(makeup_tasks),
        current_semester=current_semester_label.strip(),
        current_semester_courses=tuple(current_semester_courses),
        elective_group_id=elective_group_id,
        elective_completed_course_ids=elective_completed_course_ids,
        elective_current_semester_course_ids=elective_current_semester_course_ids,
        per_semester_credit_budget=None,
        recommended_semester_by_course=recommended_index,
    )
    extra = (*term_unresolved, *overlap_unresolved)
    if extra:
        roadmap = _with_extra_unresolved(roadmap, extra)
    return roadmap


def _with_extra_unresolved(
    roadmap: AcademicRoadmap, extra: Sequence[str]
) -> AcademicRoadmap:
    """把学期解析阶段的 unresolved 如实并入路线图（⛔ 不吞掉、不改其它字段）。"""

    return AcademicRoadmap(
        current_semester=roadmap.current_semester,
        current_semester_planned_course_ids=roadmap.current_semester_planned_course_ids,
        future_semesters=roadmap.future_semesters,
        elective_requirement_credit=roadmap.elective_requirement_credit,
        elective_completed_credit=roadmap.elective_completed_credit,
        elective_current_semester_credit=roadmap.elective_current_semester_credit,
        elective_planned_credit=roadmap.elective_planned_credit,
        elective_remaining_credit=roadmap.elective_remaining_credit,
        unresolved=(*roadmap.unresolved, *extra),
        warnings=roadmap.warnings,
    )
