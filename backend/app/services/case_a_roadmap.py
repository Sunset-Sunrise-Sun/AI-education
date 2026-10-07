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

from collections.abc import Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass
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
    "CASE_A_CURRENT_HARD_MAX_CREDIT",
    "CASE_A_FUTURE_HARD_MAX_CREDIT",
    "CASE_A_FUTURE_SOFT_TARGET_CREDIT",
    "CaseARoadmapError",
    "CurrentElectiveRecommendation",
    "CurrentSemesterLoad",
    "CurriculumTermChain",
    "bind_current_semester_courses",
    "build_case_a_roadmap",
    "current_semester_load",
    "derive_term_chain",
    "future_semesters_after",
    "observed_term_facts",
    "recommend_current_electives",
    "requirement_kind_label",
    "resolve_course_target_terms",
]

#: 产品级学期学分政策（Case A 编排层，⛔ 不是学校政策声明）。
#:
#: - `FUTURE_HARD_MAX`（未来学期）：任何**未来**学期的建议学分不得超过它；超出的课程
#:   顺延到后续学期，而不是把一学期塞成 40/50 学分；实在排不下 ⇒ unresolved；
#: - `FUTURE_SOFT_TARGET`（未来学期）：常规目标区间上限。规划时先以它作为每学期预算，
#:   使分布贴近真实可执行负荷；只有"软目标排不下"的课才放宽到硬上限重试；
#: - `CURRENT_HARD_MAX`（**当前**学期）：section-level 的学分上限，
#:   与未来上限**不同**（当前 30 / 未来 35），⛔ 不要混用。
#:
#: ⚠️ 用户显式给出的 `Preference.max_credit` **优先**于这些默认值
#: （且用户值超过对应硬上限时按硬上限收口：⛔ 不因用户输入就产出不可执行的学期）。
#:
#: 负荷标签（前端展示，与上面同一口径）：
#:
#: ```text
#: <= 26      正常
#: 26 – 30    较满
#: 30 – 35    很满
#: > 35       ⛔ 禁止产生
#: ```
CASE_A_FUTURE_SOFT_TARGET_CREDIT = 26.0
CASE_A_FUTURE_HARD_MAX_CREDIT = 35.0
#: 当前学期（section-level）学分的硬上限；⛔ 与未来上限不是同一个值。
CASE_A_CURRENT_HARD_MAX_CREDIT = 30.0
#: 当前学期专业选修**展示上限**（⛔ 不是培养方案规则）。
#:
#: 只影响"列出几门候选"，⛔ 不影响选修学分要求、冲突判定或规划结果。
#: 取值需覆盖真实选修池规模，避免再次出现"排在第 4 位之后就被静默藏掉"。
CASE_A_ELECTIVE_DISPLAY_LIMIT = 50


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


@dataclass(frozen=True, slots=True)
class CurrentElectiveRecommendation:
    """当前学期**可考虑的专业选修**（只由 Curriculum × accepted offerings 推导）。

    ⛔ 不按课程名匹配、⛔ 不推断等价、⛔ 不猜测开课；只使用
    `CSE-ELECTIVE-POOL` 的**真实成员**与**已接受**教学班的精确 `course_id` 交集。
    """

    course_id: str
    course_name: str
    credit: float
    #: 本学期可用教学班数（已接受 offerings 中该课程的教学班个数）。
    available_class_count: int
    #: 与当前课表**已知**冲突的教学班数（UNKNOWN 不计入冲突）。
    conflicting_class_count: int
    #: 排课信息待核验（`meetings=[]` 或含空 meetings）的教学班数。
    unknown_schedule_class_count: int
    #: 已确认无冲突的教学班数。
    clear_class_count: int
    #: 唯一 CLEAR 教学班时直接给出其班号；否则为 None（需用户自己选）。
    unique_clear_class_id: str | None
    #: 面向用户的冲突状态说明（中文化，⛔ 不出现机器码）。
    conflict_label: str
    #: **精确的** CLEAR 教学班号集合（升序）。
    #:
    #: ⚠️ 前端必须只对**这些**教学班提供选择入口：⛔ 不允许用
    #:    "该课程有排课信息" 之类的近似条件自己推断哪些班可选，
    #:    否则会把 CONFLICT / UNKNOWN 的教学班也变成可点选项。
    clear_class_ids: tuple[str, ...] = ()


def recommend_current_electives(
    case: CurriculumCase,
    current_schedule: Sequence[CourseOffering],
    offerings: Sequence[CourseOffering],
    *,
    elective_group_id: str,
    already_taken_course_ids: AbstractSet[str] | None = None,
    remaining_elective_credit: float | None = None,
    #: 产品展示上限：⛔ 不再只用 3 门。
    #:
    #: 早期默认 3 门会让排在第 4 位之后的选修（真实数据里正是
    #: CSE335 数据库系统原理 / CSE337 数据库系统实验）**静默消失**，
    #: 用户既看不到、也无法加入。产品要求是"要么可见，要么可达"，
    #: 因此这里放宽到能覆盖当前真实选修池的规模（前端仍会做渐进披露）。
    max_courses: int = CASE_A_ELECTIVE_DISPLAY_LIMIT,
    only_class_ids: Mapping[str, AbstractSet[str]] | None = None,
) -> tuple[CurrentElectiveRecommendation, ...]:
    """给出本学期**可考虑的专业选修**建议（最多 `max_courses` 门）。

    用途：当"选修还缺学分"时，本学期方案里**不应该一门选修都没有**，
    但⛔ 也不能把整个选修池塞进方案。因此这里只**列出候选**供用户自己选择，
    ⛔ 不自动加入、⛔ 不自动选教学班。

    排序（确定性，⛔ 无评分）：
    CLEAR 数多者优先 → 未知排课少者优先 → 学分大者优先 → `course_id` 升序。

    `only_class_ids`：可选。`course_id -> {class_id, ...}`，只对**这些教学班**
    判定 CLEAR/UNKNOWN/CONFLICT。用于"用户明确选择了某个教学班"时的**服务端复核**，
    使"可选择的"与"被推荐的"永远共用同一套冲突判定（⛔ 不复制判定逻辑）。
    """

    if not isinstance(case, CurriculumCase):
        raise CaseARoadmapError("case 必须是 CurriculumCase。")
    if remaining_elective_credit is not None and remaining_elective_credit <= 0:
        return ()
    group = _elective_group(case, elective_group_id)
    taken = set(already_taken_course_ids or ())
    restrict = dict(only_class_ids or {})

    # 精确身份：选修组成员 ∩ 本学期已接受教学班
    members = {
        course.course_id: course
        for course in case.new.courses
        if course.group_id == group.group_id
    }
    sections_by_course: dict[str, list[CourseOffering]] = {}
    for item in offerings:
        if item.course_id in members:
            sections_by_course.setdefault(item.course_id, []).append(item)

    # 当前课表的**已知**时间占用（UNKNOWN 教学班不参与冲突判定，⛔ 不假装无冲突）
    busy: set[tuple[int, int]] = set()
    for item in current_schedule:
        for meeting in item.meetings:
            if meeting.weekday is None or meeting.start_section is None:
                continue
            end = meeting.end_section if meeting.end_section is not None else meeting.start_section
            for section in range(meeting.start_section, end + 1):
                busy.add((meeting.weekday, section))

    def sections_busy(sections: list[CourseOffering]) -> bool:
        for item in sections:
            for meeting in item.meetings:
                if meeting.weekday is None or meeting.start_section is None:
                    continue
                end = (
                    meeting.end_section
                    if meeting.end_section is not None
                    else meeting.start_section
                )
                for section in range(meeting.start_section, end + 1):
                    if (meeting.weekday, section) in busy:
                        return True
        return False

    recommendations: list[CurrentElectiveRecommendation] = []
    for course_id, sections in sections_by_course.items():
        if course_id in taken:
            continue
        # ⚠️ 服务端复核：用户明确选择了某个教学班时，只对该教学班判定状态，
        #    这样"能否加入方案"与"推荐里的 CLEAR 数"用的是**同一套**判定。
        allowed_classes = restrict.get(course_id)
        if allowed_classes is not None:
            sections = [item for item in sections if item.class_id in allowed_classes]
            if not sections:
                continue
        course = members[course_id]
        clear: list[str] = []
        unknown = 0
        conflict = 0
        for item in sections:
            if not item.meetings:
                unknown += 1
                continue
            if sections_busy([item]):
                conflict += 1
            else:
                clear.append(item.class_id)

        if clear:
            label = "已找到与当前课表不冲突的教学班"
        elif conflict and not unknown:
            label = "当前候选教学班均与你的课表冲突"
        elif unknown and not conflict:
            label = "排课信息尚未同步，需要你确认后再判断冲突"
        else:
            label = "部分候选与课表冲突，另有候选排课信息尚未同步"
        recommendations.append(
            CurrentElectiveRecommendation(
                course_id=course_id,
                course_name=course.course_name,
                credit=float(course.credit),
                available_class_count=len(sections),
                conflicting_class_count=conflict,
                unknown_schedule_class_count=unknown,
                clear_class_count=len(clear),
                unique_clear_class_id=clear[0] if len(clear) == 1 else None,
                clear_class_ids=tuple(sorted(clear)),
                conflict_label=label,
            )
        )

    recommendations.sort(
        key=lambda item: (
            -item.clear_class_count,
            item.unknown_schedule_class_count,
            -item.credit,
            item.course_id,
        )
    )
    return tuple(recommendations[:max_courses])


@dataclass(frozen=True, slots=True)
class CurrentSemesterLoad:
    """当前学期**学分负荷**摘要（产品层；⛔ 不改变 Planner 结果）。

    用于让用户第一眼看到"这学期会不会超载"，而不是自己去加总。
    """

    #: 当前课表里已确认的学分（按精确课程身份、去重）。
    selected_credit: float
    #: Planner 建议新增的补修学分（不在当前课表内的建议课程）。
    suggested_makeup_credit: float
    #: 建议的专业选修学分（当前学期可考虑的选修，最多 3 门）。
    suggested_elective_credit: float
    #: 预计合计 = selected + suggested_makeup + suggested_elective。
    projected_total_credit: float
    #: 生效的学分上限（用户 `Preference.max_credit` 优先，否则产品默认 30）。
    max_credit: float
    #: `projected_total > max_credit`。⛔ 产品层不产出超限建议；该标记用于如实提示。
    exceeds_max: bool


def current_semester_load(
    *,
    current_schedule: Sequence[CourseOffering],
    planned_course_ids: Sequence[str],
    credit_by_course_id: Mapping[str, float],
    recommendations: Sequence[CurrentElectiveRecommendation] = (),
    user_max_credit: float | None = None,
) -> CurrentSemesterLoad:
    """计算当前学期学分负荷（确定性；⛔ 不含任何推断）。

    - 已选学分只统计**当前课表**中能按精确 `course_id` 对上培养方案课程的课；
    - 建议补修学分统计 Planner 建议里**当前课表没有**的课；
    - 建议选修学分统计本轮的选修候选；
    - 上限 = 用户设置优先，否则 `CASE_A_CURRENT_HARD_MAX_CREDIT`。
    """

    have = {item.course_id for item in current_schedule}
    selected = sum(
        credit_by_course_id.get(course_id, 0.0)
        for course_id in sorted({item.course_id for item in current_schedule})
    )
    makeup = sum(
        credit_by_course_id.get(course_id, 0.0)
        for course_id in sorted(set(planned_course_ids) - have)
    )
    elective = sum(item.credit for item in recommendations)
    limit = CASE_A_CURRENT_HARD_MAX_CREDIT
    if user_max_credit is not None and float(user_max_credit) > 0:
        limit = min(float(user_max_credit), CASE_A_CURRENT_HARD_MAX_CREDIT)
    total = round(selected + makeup + elective, 3)
    return CurrentSemesterLoad(
        selected_credit=round(selected, 3),
        suggested_makeup_credit=round(makeup, 3),
        suggested_elective_credit=round(elective, 3),
        projected_total_credit=total,
        max_credit=limit,
        exceeds_max=total > limit,
    )


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
    user_max_credit: float | None = None,
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

    # ---- 学期学分预算：产品级默认 + 用户上限优先 --------------------------------
    #
    # ⛔ 旧行为是 `per_semester_credit_budget=None`（不设上限），真实数据下曾产出
    #    **53.5 学分**的学期 —— 对学生没有可执行意义。现在：
    #    - 硬上限 = 用户 `Preference.max_credit`（若给出且更严）否则 HARD_MAX(30)；
    #    - 软目标 = min(用户上限, SOFT_TARGET(26))；
    #    - ⛔ 任何学期都不得 > 硬上限；排不下的课顺延，实在排不下 ⇒ unresolved。
    effective_hard = CASE_A_FUTURE_HARD_MAX_CREDIT
    if user_max_credit is not None:
        if isinstance(user_max_credit, bool) or not isinstance(user_max_credit, (int, float)):
            raise CaseARoadmapError("user_max_credit 必须是数字或 None。")
        if float(user_max_credit) <= 0:
            raise CaseARoadmapError("user_max_credit 必须为正数或 None。")
        # 用户更严的上限优先；更宽松的上限**不能**突破产品硬上限。
        effective_hard = min(float(user_max_credit), CASE_A_FUTURE_HARD_MAX_CREDIT)
    effective_soft = min(CASE_A_FUTURE_SOFT_TARGET_CREDIT, effective_hard)
    hard_budget = {label: effective_hard for label in semester_map}
    soft_budget = {label: effective_soft for label in semester_map}

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
        # 产品级学分政策：软目标 + 硬上限（⛔ 不再是 None ⇒ 不再产出 53.5 学分学期）。
        per_semester_credit_budget=hard_budget,
        per_semester_soft_budget=soft_budget,
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
