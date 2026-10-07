"""Case A demo **planning override** 层（run-local；⛔ 不改任何冻结契约）。

产品背景
--------

基础 Case A 评估是**来源可核验**的事实：

```text
12 satisfied + 11 manual_confirmation      （由培养方案 + 已确认 D4 事实推出）
```

用户可以对其中**部分** `manual_confirmation` 事项表达意图：

```text
"本次规划按已满足处理"
```

这**不是**学校官方认定，⛔ 也**不能**回头改写基础评估。因此本模块提供一层
**run-local 的规划覆盖（planning override）**：

```text
基础 case（不可变）
   + user_confirmed_manual_task_keys（用户本次规划确认的课程号）
   + selected_elective_sections（用户明确选择的选修教学班）
        ↓  一次确定性 recompute
   有效补救任务（effective makeup tasks）+ 有效方案/路线图/负荷
```

设计红线（与独立 Review 结论一致）
----------------------------------

- ⛔ **不改** `MakeupTask.status`、培养方案 JSON、成绩单 binding、provenance 或 SQLite；
- ⛔ 覆盖只影响**本次规划**，移除 key 后必须**确定性地**回到原方案（可撤销）；
- ⛔ 身份只能用**精确 `course_id`**：`MakeupTask` 没有独立 id，它是培养方案课程的投影。
  拒绝未知 / 重复 / 已满足 / 必修 / `possibly_equivalent` 的 key（fail closed）；
- ⛔ 不用 `course_name`、`reason`、渲染文本、数组下标等自由文本当身份；
- ⛔ 选修只接受**精确 `course_id` + `class_id`**，且服务端复核该教学班状态为 `CLEAR`；
  多个 CLEAR 时必须显式指定教学班，⛔ 不隐式取第一个。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from app.curriculum.case import CurriculumCase
from app.integration.ports import CurriculumProvider
from app.models.contracts import CourseOffering, MakeupStatus, MakeupTask
from app.services.case_a_roadmap import recommend_current_electives

__all__ = [
    "ElectiveSelection",
    "PLANNING_ONLY_DISCLOSURE",
    "PlanningOverrideError",
    "PlanningOverrideOutcome",
    "PlanningViewCurriculumProvider",
    "apply_planning_overrides",
    "build_outcome",
    "merge_elective_sources",
    "resolve_elective_selections",
    "validate_override_course_ids",
]

#: 三项披露文案必须**同时**出现（独立 Review 明确要求）。
PLANNING_ONLY_DISCLOSURE: dict[str, str] = {
    "basis": "基于你的确认",
    "scope": "仅用于本次规划",
    "authority": "不是学校官方认定结果",
}


class PlanningOverrideError(ValueError):
    """覆盖输入不成立（fail closed，⛔ 不猜测）。"""


@dataclass(frozen=True)
class ElectiveSelection:
    """用户明确选择的选修教学班（精确身份：`semester + course_id + class_id`）。"""

    semester: str
    course_id: str
    class_id: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.semester, self.course_id, self.class_id)


@dataclass(frozen=True)
class PlanningOverrideOutcome:
    """一次 recompute 的覆盖结果（全部为**规划层**事实，⛔ 不改基础评估）。"""

    #: 有效（effective）补救任务：被确认的 `manual_confirmation` 在本轮视为已满足。
    effective_tasks: tuple[MakeupTask, ...]
    #: 本轮实际生效的覆盖课程号（已通过校验、排序稳定）。
    applied_course_ids: tuple[str, ...]
    #: 被拒绝的输入（结构化、面向用户的中文原因；⛔ 不静默丢弃）。
    rejected_course_ids: tuple[tuple[str, str], ...]
    #: 被拒绝的选修选择（`(课程号, 原因)`）。
    rejected_elective_course_ids: tuple[tuple[str, str], ...]
    #: 有效补救任务里被视为已满足的课程号（用于学分/路线图口径）。
    effective_satisfied_course_ids: frozenset[str]
    #: 用户确认的选修教学班（已通过校验）。
    accepted_elective_sections: tuple[CourseOffering, ...]
    #: 用户选择但服务端判定**不是 CLEAR** 的选修（⛔ 不得进入方案）。
    rejected_elective_sections: tuple[tuple[str, str], ...]


def _manual_confirmation_by_course_id(
    tasks: Sequence[MakeupTask],
) -> dict[str, MakeupTask]:
    """只收集 `manual_confirmation` 的补救任务（唯一允许被覆盖的状态）。"""

    return {
        task.course_id: task
        for task in tasks
        if task.status is MakeupStatus.MANUAL_CONFIRMATION
    }


def validate_override_course_ids(
    tasks: Sequence[MakeupTask],
    keys: Iterable[str],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """校验用户确认 key（精确 `course_id`），返回 `(通过, 被拒绝)`。

    规则（fail closed）：
    - 空 key / 非字符串 ⇒ 拒绝；
    - 重复出现 ⇒ 拒绝该 key（⛔ 不猜"以哪一次为准"）；
    - 不在本次响应里 ⇒ 拒绝（"未知"）；
    - 状态不是 `manual_confirmation` ⇒ 拒绝（已满足 / 必修 / 可能等同）；
    - ⛔ 不做名称匹配、不做前缀匹配、不接受数组下标。
    """

    allowed = {
        task.course_id: task.status
        for task in tasks
    }
    manual = _manual_confirmation_by_course_id(tasks)

    # ⚠️ 先统计出现次数：重复 key 一律**整条拒绝**（fail closed），
    #    ⛔ 不"取第一次" —— 静默挑选哪一次为准会让结果不确定、也不可复核。
    raw_values = [raw.strip() if isinstance(raw, str) else str(raw) for raw in keys]
    occurrences: dict[str, int] = {}
    for value in raw_values:
        occurrences[value] = occurrences.get(value, 0) + 1

    accepted: list[str] = []
    rejected: list[tuple[str, str]] = []
    for key in raw_values:
        if not key:
            rejected.append(("", "确认项为空，无法识别课程"))
            continue
        if occurrences[key] > 1:
            rejected.append((key, "同一门课被重复确认，未采纳（重复输入一律拒绝）"))
            continue
        if key not in allowed:
            rejected.append((key, "该课程不在本次评估结果中，无法确认"))
            continue
        if key not in manual:
            status = allowed[key]
            label = {
                MakeupStatus.SATISFIED: "该课程在评估中已是「已满足」，无需确认",
                MakeupStatus.REQUIRED: "该课程是必修要求，不能按已满足处理",
                MakeupStatus.POSSIBLY_EQUIVALENT: "该课程是否等同尚未确认，需先人工认定",
            }.get(status, "该课程的评估状态不允许按已满足处理")
            rejected.append((key, label))
            continue
        accepted.append(key)

    return tuple(sorted(accepted)), tuple(rejected)


def apply_planning_overrides(
    tasks: Sequence[MakeupTask],
    *,
    confirmed_course_ids: Iterable[str] = (),
) -> tuple[tuple[MakeupTask, ...], tuple[str, ...], tuple[tuple[str, str], ...]]:
    """构造**有效**补救任务：被确认的 `manual_confirmation` 本轮按已满足处理。

    ⛔ 只在本函数返回的副本上生效：输入 `tasks` 不被修改，
       基础评估（来源可核验的 12 satisfied / 11 manual_confirmation）保持不变。

    `reason` 会带上"基于你的确认 / 仅用于本次规划"，使下游展示天然可追溯。
    """

    accepted, rejected = validate_override_course_ids(tasks, confirmed_course_ids)
    accepted_set = set(accepted)

    effective: list[MakeupTask] = []
    for task in tasks:
        if task.course_id in accepted_set and task.status is MakeupStatus.MANUAL_CONFIRMATION:
            existing = task.reason or ""
            note = (
                f"{existing}｜{PLANNING_ONLY_DISCLOSURE['basis']}，"
                f"{PLANNING_ONLY_DISCLOSURE['scope']}；"
                f"{PLANNING_ONLY_DISCLOSURE['authority']}"
            ).strip("｜")
            effective.append(
                # ⚠️ `MakeupTask` 是 Pydantic 模型（不是 dataclass），因此用 model_copy。
                task.model_copy(
                    update={
                        "status": MakeupStatus.SATISFIED,
                        "reason": note,
                    }
                )
            )
        else:
            effective.append(task)
    return tuple(effective), accepted, rejected


def resolve_elective_selections(
    case: CurriculumCase,
    selections: Sequence[ElectiveSelection],
    offerings: Sequence[CourseOffering],
    *,
    elective_group_id: str,
    current_schedule: Sequence[CourseOffering] = (),
) -> tuple[tuple[CourseOffering, ...], tuple[tuple[str, str], ...]]:
    """校验用户明确选择的选修教学班，返回 `(通过的教学班, 拒绝原因)`。

    规则（精确身份 + 服务端复核，⛔ 不隐式选择教学班）：

    1. `course_id` 必须是选修组**成员**（精确匹配，⛔ 不做名称/模糊/等同推断）；
    2. `semester` + `class_id` 必须精确命中一个**已接受**教学班；
    3. 该教学班的状态必须由服务端判定为 **CLEAR**
       —— `UNKNOWN` / `CONFLICT` 一律不接受（⛔ 不能选一个不可执行的教学班）；
    4. 判定复用 `recommend_current_electives(..., only_class_ids=...)`：
       ⛔ 不复制冲突判定逻辑，"可选择的"与"被推荐的"共用同一套语义。

    ⚠️ 多个 CLEAR 候选取哪一个由**用户**决定：本函数只复核用户给出的那一个，
       ⛔ 绝不回退到其它教学班（若用户给的不是 CLEAR，就明确拒绝）。
    """

    group_members = {
        course.course_id: course
        for course in case.new.courses
        if course.group_id == elective_group_id
    }
    accepted_offerings = {
        (item.semester, item.course_id, item.class_id): item for item in offerings
    }

    accepted: list[CourseOffering] = []
    rejected: list[tuple[str, str]] = []
    # ⚠️ 同一门选修被提交多次 ⇒ **整门拒绝**（与 manual_confirmation 的去重口径一致）：
    #    ⛔ 不"取第一次"，避免静默挑选哪一次为准。
    occurrences: dict[str, int] = {}
    for selection in selections:
        cid = (selection.course_id or "").strip()
        occurrences[cid] = occurrences.get(cid, 0) + 1
    seen_courses: set[str] = set()

    for selection in selections:
        course_id = (selection.course_id or "").strip()
        class_id = (selection.class_id or "").strip()
        if not course_id:
            rejected.append(("", "选修选择缺少课程号，无法识别课程"))
            continue
        if course_id not in group_members:
            rejected.append((course_id, "该课程不在本专业选修组中，不能加入本学期方案"))
            continue
        if occurrences[course_id] > 1:
            rejected.append((course_id, "同一门选修被重复选择，未采纳（重复输入一律拒绝）"))
            continue
        if course_id in seen_courses:
            continue
        item = accepted_offerings.get((selection.semester, course_id, class_id))
        if item is None or not class_id:
            rejected.append((course_id, "所选教学班不在已接受的教学班数据中，需重新选择"))
            continue

        # ⚠️ 服务端复核：只对这个教学班判定状态（共用推荐用的同一套冲突语义）。
        checked = recommend_current_electives(
            case,
            current_schedule,
            offerings,
            elective_group_id=elective_group_id,
            max_courses=10_000,
            only_class_ids={course_id: {class_id}},
        )
        status = next((r for r in checked if r.course_id == course_id), None)
        if status is None:
            rejected.append((course_id, "本学期没有该课程可用的教学班，无法加入"))
            continue
        if status.clear_class_count == 0:
            if status.unknown_schedule_class_count > 0:
                rejected.append(
                    (course_id, "所选教学班排课信息待核验，暂时无法确认是否冲突，不能加入")
                )
            else:
                rejected.append(
                    (course_id, "所选教学班与你的当前课表冲突，不能加入")
                )
            continue

        seen_courses.add(course_id)
        accepted.append(item)

    return tuple(accepted), tuple(rejected)


def build_outcome(
    tasks: Sequence[MakeupTask],
    *,
    confirmed_course_ids: Iterable[str] = (),
    accepted_electives: Sequence[CourseOffering] = (),
    rejected_electives: Sequence[tuple[str, str]] = (),
    rejected_elective_sections: Sequence[tuple[str, str]] = (),
) -> PlanningOverrideOutcome:
    """把校验结果打包成一次 recompute 的覆盖结果。"""

    effective, accepted, rejected = apply_planning_overrides(
        tasks, confirmed_course_ids=confirmed_course_ids
    )
    satisfied = frozenset(
        task.course_id for task in effective if task.status is MakeupStatus.SATISFIED
    )
    return PlanningOverrideOutcome(
        effective_tasks=effective,
        applied_course_ids=accepted,
        rejected_course_ids=rejected,
        rejected_elective_course_ids=tuple(rejected_electives),
        effective_satisfied_course_ids=satisfied,
        accepted_elective_sections=tuple(accepted_electives),
        rejected_elective_sections=tuple(rejected_elective_sections),
    )


@dataclass(frozen=True)
class PlanningViewCurriculumProvider:
    """**只用于本次规划**的 CurriculumProvider 视图。

    背景：`CurriculumCaseProvider.get_makeup_tasks()` 从不可变的培养方案 case 派生任务，
    没有"注入任务"的接口。而用户确认必须是 run-local 的规划覆盖，⛔ **不能**
    通过添加 `recognitions` 等"已修认定"来实现 —— 那等于伪造来源事实
    （`ConfirmedRecognition` 要求 `completed_source_record` + `evidence`，
    用户勾选**没有**这样的依据）。

    因此这里包一层视图：

    - 从被包装的 provider 取**来源可核验**的任务；
    - 把用户本次规划确认过的 `manual_confirmation` 呈现为 `satisfied`
      （并带上"基于你的确认 / 仅用于本次规划 / 不是学校官方认定结果"的 reason）；
    - 其余任务原样透传。

    ⛔ 基础 case、培养方案 JSON、成绩单 binding、provenance、SQLite 都不被修改：
       被改写的只是**本次规划**看到的那一份任务副本。
    """

    inner: CurriculumProvider
    #: 用户本次规划确认的课程号（**已通过校验**）。
    confirmed_course_ids: tuple[str, ...] = ()

    def _effective_tasks(self) -> list[MakeupTask]:
        base = list(self.inner.get_makeup_tasks())
        effective, _, _ = apply_planning_overrides(
            base, confirmed_course_ids=self.confirmed_course_ids
        )
        return list(effective)

    def get_makeup_tasks(self) -> list[MakeupTask]:
        return self._effective_tasks()

    def get_academic_analysis(self) -> object:
        return self.inner.get_academic_analysis()

    def get_curriculum_diff(self) -> object:
        return self.inner.get_curriculum_diff()

    def __getattr__(self, name: str) -> object:
        # 未显式覆盖的能力（例如 validation summary）继续委托给真实 provider。
        return getattr(self.inner, name)


def merge_elective_sources(
    selections: Sequence[ElectiveSelection],
    *,
    default_semester: str,
) -> tuple[ElectiveSelection, ...]:
    """把缺省学期的选择补齐为完整 `semester + course_id + class_id` 身份。"""

    merged: list[ElectiveSelection] = []
    for selection in selections:
        merged.append(
            ElectiveSelection(
                semester=(selection.semester or default_semester).strip() or default_semester,
                course_id=(selection.course_id or "").strip(),
                class_id=(selection.class_id or "").strip(),
            )
        )
    return tuple(merged)


def elective_membership(
    case: CurriculumCase,
    *,
    elective_group_id: str,
) -> Mapping[str, str]:
    """`course_id -> course_name`：选修组成员（精确匹配，供审计与测试复用）。"""

    return {
        course.course_id: course.course_name
        for course in case.new.courses
        if course.group_id == elective_group_id
    }
