"""当前学期：**结构化换班建议**（section-level），生成与应严格分离。

```text
current_schedule + offerings
        ↓  generate_repair_proposals()          ← 只读，⛔ 不动课表
RepairProposalSet（每个冲突课程可有多条候选）
        ↓  调用方 / 用户**显式选择**一条         ← ⛔ 不存在"自动接受"
apply_repair_proposal()                          ← 校验 + 重新评估 + 应用
        ↓
RepairApplicationResult（新 schedule + changes + 重校验结果）
```

## 硬边界

- ⛔ **不自动换班**：本模块永远不替调用方挑候选；`generate_*` 只产出建议；
- ⛔ 不重复实现冲突判定：一律**复用** `planner.section_repair` 的原语
  （`find_alternative_sections()` / `repair_target_section()`）与
  `planner.conflicts` 的稳定枚举；
- ⛔ 建议里**不复制** `CourseOffering` 取值（只给 identity + 状态 + 原因），
  前端自行与 `CourseOffering[]` join；
- ⛔ 不新增公共 Schema、⛔ 不改 `PlannerProvider` 契约、⛔ 不写库。

## 与 DG-07（`meetings = []`）的关系

`meetings = []` 表示**当前来源快照没有可用排课信息**（schedule UNKNOWN），
⛔ 不表示无冲突。因此：

- 原班/候选为 UNKNOWN 时，其 `conflict_state` 一律是 `UNKNOWN`，
  本模块**不**把它说成"无冲突"，也⛔ 不因此自动换班；
- UNKNOWN 与"已确认冲突"**不合并**：建议里会如实带上 `original_state`。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.models.contracts import Change, CourseOffering
from app.planner.conflicts import ConflictState, check_schedule_conflict
from app.planner.section_repair import (
    RepairOutcome,
    find_alternative_sections,
    repair_target_section,
)

__all__ = [
    "RepairApplicationResult",
    "RepairApplicationStatus",
    "RepairProposalSet",
    "SectionRepairProposal",
    "apply_repair_proposal",
    "generate_repair_proposals",
]


class RepairApplicationStatus(str, Enum):
    """一次**显式选择**的应用结果（⛔ 不表达整学期可行性）。"""

    APPLIED = "applied"
    ORIGINAL_CLEAR = "original_clear"
    REJECTED = "rejected"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class SectionRepairProposal:
    """一条**待用户确认**的同课程换班建议（⛔ 尚未生效）。

    只携带 identity 与判定结果；⛔ 不含课程名 / 教师 / 时间地点等 `CourseOffering`
    取值 —— 调用方用 `(semester, target_course_id, candidate_class_id)`
    自行与 `CourseOffering[]` join。
    """

    semester: str
    target_course_id: str
    current_class_id: str
    candidate_class_id: str
    original_state: ConflictState
    candidate_state: ConflictState
    reason: str

    @property
    def proposal_id(self) -> str:
        """稳定标识（同一 identity 的建议恒为同一取值），供前端选择时回传。"""

        return (
            f"{self.semester}::{self.target_course_id}"
            f"::{self.current_class_id}->{self.candidate_class_id}"
        )


@dataclass(frozen=True, slots=True)
class RepairProposalSet:
    """一批建议 + 未能给出建议的原因（⛔ 只读快照，不含 course 取值）。"""

    semester: str
    proposals: tuple[SectionRepairProposal, ...]
    unresolved: tuple[str, ...]

    @property
    def proposal_count(self) -> int:
        return len(self.proposals)

    def for_course(self, course_id: str) -> tuple[SectionRepairProposal, ...]:
        """某门课程的全部候选（⛔ 顺序即建议顺序，不代表优劣排名）。"""

        return tuple(item for item in self.proposals if item.target_course_id == course_id)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串。")
    return value


def _copy_schedule(values: Sequence[CourseOffering], name: str) -> tuple[CourseOffering, ...]:
    """隔离输入：返回深拷贝，且要求 identity 唯一（⛔ 不静默去重）。"""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} 必须是 CourseOffering 序列。")
    copied: list[CourseOffering] = []
    seen: set[tuple[str, str, str]] = set()
    for item in values:
        if not isinstance(item, CourseOffering):
            raise ValueError(f"{name} 中混入了非 CourseOffering 对象。")
        key = (item.semester, item.course_id, item.class_id)
        if key in seen:
            raise ValueError(f"{name} 存在重复教学班身份：{key}")
        seen.add(key)
        copied.append(item.model_copy(deep=True))
    return tuple(copied)


def generate_repair_proposals(
    *,
    semester: str,
    current_schedule: Sequence[CourseOffering],
    offerings: Sequence[CourseOffering],
) -> RepairProposalSet:
    """为 `current_schedule` 生成换班建议（**只读**：⛔ 绝不修改任何输入）。

    对课表中**每一个**教学班：

    - 与课表其余部分已确认无冲突（`CLEAR`）⇒ 不产生建议；
    - 存在已知冲突 / 排课信息未知（`CONFLICT` / `UNKNOWN`）⇒ 为每一个
      `CLEAR` 的同课程同学期候选产生一条建议；
    - 没有 CLEAR 候选 ⇒ 如实记入 `unresolved`（⛔ 不编造候选）。

    ⛔ 本函数**不排序优劣**、**不自动选择**、**不应用**任何替换。
    """

    semester = _require_text(semester, "semester")
    schedule = _copy_schedule(current_schedule, "current_schedule")
    available = _copy_schedule(offerings, "offerings")

    proposals: list[SectionRepairProposal] = []
    unresolved: list[str] = []

    for item in schedule:
        if item.semester != semester:
            unresolved.append(
                f"课程 {item.course_id} 的教学班学期 {item.semester} 与本次规划学期 "
                f"{semester} 不一致；不生成建议。"
            )
            continue

        search = find_alternative_sections(
            course_id=item.course_id,
            current_class_id=item.class_id,
            semester=semester,
            offerings=available,
            current_schedule=schedule,
        )
        if search.original_state is ConflictState.CLEAR:
            # 原班已确认无冲突 ⇒ 不需要换班建议（⛔ 不制造无谓变更）。
            continue

        clear_candidates = [
            candidate
            for candidate in search.candidates
            if candidate.state is ConflictState.CLEAR
        ]
        if not clear_candidates:
            unresolved.append(
                f"课程 {item.course_id} 的当前教学班 {item.class_id} 状态为 "
                f"{search.original_state.value}，但本次输入中没有可确认无冲突的同课程候选"
                f"（{search.outcome.value}）；需要人工核验，不生成建议。"
            )
            continue

        for candidate in clear_candidates:
            proposals.append(
                SectionRepairProposal(
                    semester=semester,
                    target_course_id=item.course_id,
                    current_class_id=item.class_id,
                    candidate_class_id=candidate.offering.class_id,
                    original_state=search.original_state,
                    candidate_state=candidate.state,
                    reason=(
                        f"课程 {item.course_id} 的当前教学班 {item.class_id} 状态为 "
                        f"{search.original_state.value}；候选 {candidate.offering.class_id} "
                        f"与其余课表已确认无时间冲突，需调用方明确选择后才替换。"
                    ),
                )
            )

    proposals.sort(key=lambda item: (item.target_course_id, item.candidate_class_id))
    return RepairProposalSet(
        semester=semester,
        proposals=tuple(proposals),
        unresolved=tuple(unresolved),
    )


@dataclass(frozen=True, slots=True)
class RepairApplicationResult:
    """一次显式选择的应用结果（⛔ 新 schedule 已与输入隔离）。"""

    status: RepairApplicationStatus
    schedule: tuple[CourseOffering, ...]
    changes: tuple[Change, ...]
    reason: str
    revalidated: bool
    remaining_conflicts: tuple[str, ...]


def apply_repair_proposal(
    *,
    semester: str,
    course_id: str,
    from_class_id: str,
    to_class_id: str,
    current_schedule: Sequence[CourseOffering],
    offerings: Sequence[CourseOffering],
) -> RepairApplicationResult:
    """把调用方**显式选择**的一条建议应用到课表（fail closed）。

    选择必须完整标识 `(semester, course_id, from_class_id, to_class_id)`。
    校验（任一不成立 ⇒ 拒绝，⛔ 不静默修正）：

    - `from_class_id` 必须**确实存在**于 `current_schedule`；
    - `to_class_id` 必须在该 semester 的**已接受 offerings** 中；
    - 两者必须是**同一门课**（⛔ 不允许换课）；
    - 学期必须一致（⛔ 不允许跨学期替换）；
    - 候选必须**重新评估**为 `CLEAR`（⛔ 不接受过期搜索结果）。

    应用后按**新课表**重新做一次内部冲突复核：残留冲突会被如实列出
    （`revalidated = False`），⛔ 不伪装成"已验证无冲突"。
    """

    semester = _require_text(semester, "semester")
    course_id = _require_text(course_id, "course_id")
    from_class_id = _require_text(from_class_id, "from_class_id")
    to_class_id = _require_text(to_class_id, "to_class_id")
    schedule = _copy_schedule(current_schedule, "current_schedule")
    available = _copy_schedule(offerings, "offerings")

    if from_class_id == to_class_id:
        return RepairApplicationResult(
            RepairApplicationStatus.UNCHANGED,
            schedule,
            (),
            "所选教学班与原教学班相同，课表未发生变化。",
            revalidated=True,
            remaining_conflicts=(),
        )

    target = next(
        (
            item
            for item in schedule
            if item.course_id == course_id and item.class_id == from_class_id
        ),
        None,
    )
    if target is None:
        return RepairApplicationResult(
            RepairApplicationStatus.REJECTED,
            schedule,
            (),
            f"当前课表中不存在课程 {course_id} 的教学班 {from_class_id}；拒绝应用。",
            revalidated=False,
            remaining_conflicts=(),
        )
    if target.semester != semester:
        return RepairApplicationResult(
            RepairApplicationStatus.REJECTED,
            schedule,
            (),
            f"教学班 {from_class_id} 的学期 {target.semester} 与请求学期 {semester} "
            f"不一致；⛔ 不允许跨学期替换。",
            revalidated=False,
            remaining_conflicts=(),
        )

    candidate = next(
        (
            item
            for item in available
            if item.course_id == course_id
            and item.class_id == to_class_id
            and item.semester == semester
        ),
        None,
    )
    if candidate is None:
        return RepairApplicationResult(
            RepairApplicationStatus.REJECTED,
            schedule,
            (),
            f"学期 {semester} 的已接受教学班中没有课程 {course_id} 的教学班 "
            f"{to_class_id}；拒绝应用（⛔ 不接受输入之外的班号）。",
            revalidated=False,
            remaining_conflicts=(),
        )
    if candidate.course_id != target.course_id:
        # 结构上不可达（两者都按 course_id 过滤），保留为纵深防御。
        return RepairApplicationResult(
            RepairApplicationStatus.REJECTED,
            schedule,
            (),
            "候选教学班与原教学班不属于同一门课程；⛔ 拒绝换课。",
            revalidated=False,
            remaining_conflicts=(),
        )

    try:
        repair = repair_target_section(
            course_id=course_id,
            current_class_id=from_class_id,
            semester=semester,
            offerings=available,
            current_schedule=schedule,
            replacement_class_id=to_class_id,
        )
    except ValueError as exc:
        return RepairApplicationResult(
            RepairApplicationStatus.REJECTED,
            schedule,
            (),
            f"换班未通过既有换班原语的校验：{exc}",
            revalidated=False,
            remaining_conflicts=(),
        )

    if repair.outcome is RepairOutcome.REPLACED:
        remaining = _internal_conflict_identities(repair.new_schedule)
        return RepairApplicationResult(
            RepairApplicationStatus.APPLIED,
            repair.new_schedule,
            repair.changes,
            repair.reason,
            revalidated=not remaining,
            remaining_conflicts=remaining,
        )
    if repair.outcome is RepairOutcome.ORIGINAL_CLEAR:
        return RepairApplicationResult(
            RepairApplicationStatus.ORIGINAL_CLEAR,
            repair.new_schedule,
            (),
            repair.reason,
            revalidated=True,
            remaining_conflicts=(),
        )
    return RepairApplicationResult(
        RepairApplicationStatus.REJECTED,
        repair.new_schedule,
        (),
        repair.reason,
        revalidated=False,
        remaining_conflicts=(),
    )


def _internal_conflict_identities(
    schedule: Sequence[CourseOffering],
) -> tuple[str, ...]:
    """新课表内部复核：列出仍然存在**已确认**冲突的教学班 identity。

    ⚠️ 只报告 `CONFLICT`；`UNKNOWN`（`meetings = []` 等排课信息未知）
    ⛔ 不算作已确认冲突，也不被吞掉 —— 调用方可用
    `generate_repair_proposals()` 看到它们。
    """

    conflicts: list[str] = []
    for item in schedule:
        others = [other for other in schedule if other is not item]
        if check_schedule_conflict(item, others) is ConflictState.CONFLICT:
            conflicts.append(f"{item.semester}::{item.course_id}::{item.class_id}")
    return tuple(sorted(conflicts))
