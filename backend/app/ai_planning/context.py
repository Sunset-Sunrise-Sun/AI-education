"""方案上下文快照与指纹（**控制器内部对象，不是公共 Schema**）。

```text
调用方已拿到的 PlanResult + MakeupTask[] + CourseOffering[] + Preference + 学期
        ↓  build_context(...)
PlanningContext（只读快照 + 内容指纹 + 课程 / 教学班白名单 + Mock/Real 标记）
        ↓  context.digest
意图草稿与候选都绑定这个指纹；指纹变化 ⇒ 旧意图 / 旧候选立即失效（fail closed）
```

## 为什么需要指纹

"AI 调整"必须建立在**用户当时看到的那个方案**之上。如果期间的培养方案认定、
已修记录或教学班快照发生变化，任何基于旧快照的意图或候选都**不可再用** ——
否则用户会采用一份依据已经过期的方案。指纹把这件事变成可复核的确定性判断。

## 白名单从哪来（⛔ 不猜）

- **课程号**：只来自 `MakeupTask[].course_id` 与 `CourseOffering[].course_id`
  （以及当前方案 `PlanResult.selected_classes[].course_id` / `changes[].course_id`）；
- **教学班号**：只来自 `CourseOffering[]` 的 `(course_id, class_id)` 对
  以及 `PlanResult.selected_classes[]`。

模型给出的任何白名单外课程 / 教学班一律被拒绝，⛔ 不会因为"看起来合理"而放行。

## 数据来源标记

`data_source` 只取 `mock` / `real` / `mixed`，由**教学班自身**的
`data_source` 字段判定（与页面处于哪个模式无关）：
- 全部 `real` → `real`；全部 `mock` → `mock`；两者都有 → `mixed`；
- 没有任何教学班输入 → `unknown`（⛔ 不默认成 real，也不默认成 mock）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from app.ai_planning.errors import PlanContextInvalidError
from app.models.contracts import (
    CourseOffering,
    DataSource,
    MakeupTask,
    PlanResult,
    Preference,
)

__all__ = [
    "CONTEXT_SOURCE_MIXED",
    "CONTEXT_SOURCE_REAL",
    "CONTEXT_SOURCE_UNKNOWN",
    "MAX_CONTEXT_OFFERINGS",
    "MAX_CONTEXT_TASKS",
    "PlanningContext",
    "build_context",
]

CONTEXT_SOURCE_REAL: Final[str] = "real"
CONTEXT_SOURCE_MIXED: Final[str] = "mixed"
CONTEXT_SOURCE_UNKNOWN: Final[str] = "unknown"

#: 上下文规模硬上限：避免把巨量输入喂给模型或让内存无界增长。
MAX_CONTEXT_TASKS: Final[int] = 300
MAX_CONTEXT_OFFERINGS: Final[int] = 2000

#: 参与模型输入的最小上下文里，单个字段的最大字符数（防注入 / 防超长）。
_MAX_TEXT: Final[int] = 200


def _text(value: object, *, limit: int = _MAX_TEXT) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _canonical(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _source_of(offerings: tuple[CourseOffering, ...]) -> str:
    if not offerings:
        return CONTEXT_SOURCE_UNKNOWN
    values = {item.data_source for item in offerings}
    if values == {DataSource.REAL}:
        return CONTEXT_SOURCE_REAL
    if values == {DataSource.MOCK}:
        return "mock"
    return CONTEXT_SOURCE_MIXED


@dataclass(frozen=True, slots=True)
class PlanningContext:
    """一次"AI 调整"所依据的**只读**快照。"""

    semester: str
    base_plan: PlanResult
    makeup_tasks: tuple[MakeupTask, ...]
    offerings: tuple[CourseOffering, ...]
    preference: Preference
    data_source: str
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.semester, str) or not self.semester.strip():
            raise PlanContextInvalidError("semester 必须是非空字符串。")
        if not isinstance(self.base_plan, PlanResult):
            raise PlanContextInvalidError("base_plan 必须是 PlanResult。")
        if not isinstance(self.preference, Preference):
            raise PlanContextInvalidError("preference 必须是 Preference。")
        object.__setattr__(self, "makeup_tasks", tuple(self.makeup_tasks))
        object.__setattr__(self, "offerings", tuple(self.offerings))
        if any(not isinstance(item, MakeupTask) for item in self.makeup_tasks):
            raise PlanContextInvalidError("makeup_tasks 中每项必须是 MakeupTask。")
        if any(not isinstance(item, CourseOffering) for item in self.offerings):
            raise PlanContextInvalidError("offerings 中每项必须是 CourseOffering。")
        if not isinstance(self.digest, str) or len(self.digest) != 64:
            raise PlanContextInvalidError("digest 必须是 64 位十六进制指纹。")

    # ------------------------------------------------------------------ #
    # 白名单
    # ------------------------------------------------------------------ #

    @property
    def course_ids(self) -> frozenset[str]:
        """模型**允许**提到的课程号（全部来自调用方输入）。"""

        ids: set[str] = set()
        ids.update(task.course_id for task in self.makeup_tasks)
        ids.update(item.course_id for item in self.offerings)
        ids.update(item.course_id for item in self.base_plan.selected_classes)
        ids.update(
            item.course_id for item in self.base_plan.changes if item.course_id
        )
        return frozenset(ids)

    @property
    def class_keys(self) -> frozenset[tuple[str, str]]:
        """模型**允许**提到的 `(course_id, class_id)` 对。"""

        keys: set[tuple[str, str]] = set()
        keys.update((item.course_id, item.class_id) for item in self.offerings)
        keys.update(
            (item.course_id, item.class_id) for item in self.base_plan.selected_classes
        )
        return frozenset(keys)

    @property
    def selected_by_course(self) -> dict[str, CourseOffering]:
        """当前方案里每个课程号对应的教学班（学生**已经选择**的事实）。"""

        index: dict[str, CourseOffering] = {}
        for selected in self.base_plan.selected_classes:
            for offering in self.offerings:
                if (
                    offering.course_id == selected.course_id
                    and offering.class_id == selected.class_id
                ):
                    index.setdefault(selected.course_id, offering)
        return index

    @property
    def required_course_ids(self) -> frozenset[str]:
        return frozenset(
            task.course_id for task in self.makeup_tasks if task.status.value == "required"
        )

    # ------------------------------------------------------------------ #
    # 供模型使用的最小化上下文（⛔ 不含姓名 / 学号 / 成绩 / Cookie）
    # ------------------------------------------------------------------ #

    def model_payload(self) -> dict:
        """**发送给模型**的最小上下文：只有课程标识、学分、学期与已确认约束。"""

        return {
            "semester": self.semester,
            "data_source": self.data_source,
            "selected_classes": [
                {"course_id": _text(item.course_id, limit=40),
                 "class_id": _text(item.class_id, limit=40)}
                for item in self.base_plan.selected_classes
            ],
            "makeup_tasks": [
                {
                    "course_id": _text(task.course_id, limit=40),
                    "credit": task.credit,
                    "status": task.status.value,
                    "has_prerequisites": bool(task.prerequisites),
                }
                for task in self.makeup_tasks
            ],
            "available_sections": [
                {
                    "course_id": _text(item.course_id, limit=40),
                    "class_id": _text(item.class_id, limit=40),
                    "meetings_known": bool(item.meetings),
                }
                for item in self.offerings
            ],
            "declared_max_credit": self.preference.max_credit,
            "plan_status": self.base_plan.status.value,
        }

    def selected_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            (item.course_id, item.class_id) for item in self.base_plan.selected_classes
        )


def build_context(
    *,
    semester: str,
    base_plan: PlanResult,
    makeup_tasks: list[MakeupTask] | tuple[MakeupTask, ...] = (),
    offerings: list[CourseOffering] | tuple[CourseOffering, ...] = (),
    preference: Preference | None = None,
) -> PlanningContext:
    """校验并冻结一次方案上下文；失败即 `PlanContextInvalidError`（fail closed）。"""

    if not isinstance(semester, str) or not semester.strip():
        raise PlanContextInvalidError("semester 必须是非空字符串。")
    if not isinstance(base_plan, PlanResult):
        raise PlanContextInvalidError("base_plan 必须是 PlanResult。")
    tasks = tuple(makeup_tasks)
    sections = tuple(offerings)
    pref = preference if preference is not None else Preference()
    if len(tasks) > MAX_CONTEXT_TASKS:
        raise PlanContextInvalidError("makeup_tasks 条目过多。")
    if len(sections) > MAX_CONTEXT_OFFERINGS:
        raise PlanContextInvalidError("course_offerings 条目过多。")
    if any(not isinstance(item, MakeupTask) for item in tasks):
        raise PlanContextInvalidError("makeup_tasks 中每项必须是 MakeupTask。")
    if any(not isinstance(item, CourseOffering) for item in sections):
        raise PlanContextInvalidError("course_offerings 中每项必须是 CourseOffering。")
    if not isinstance(pref, Preference):
        raise PlanContextInvalidError("preference 必须是 Preference。")

    semesters = {item.semester for item in sections}
    if semesters and semesters != {semester}:
        # ⛔ 不猜、不裁剪：单学期控制器只接受同一学期的教学班。
        raise PlanContextInvalidError("course_offerings 的学期与本次 semester 不一致。")
    if len({item.course_id for item in tasks}) != len(tasks):
        raise PlanContextInvalidError("makeup_tasks 存在重复 course_id。")
    if len({(item.course_id, item.class_id) for item in sections}) != len(sections):
        raise PlanContextInvalidError("course_offerings 存在重复教学班身份。")

    fingerprint = _digest({
        "semester": semester,
        "plan": base_plan.model_dump(mode="json"),
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "offerings": [item.model_dump(mode="json") for item in sections],
        "preference": pref.model_dump(mode="json"),
    })
    return PlanningContext(
        semester=semester,
        base_plan=base_plan,
        makeup_tasks=tasks,
        offerings=sections,
        preference=pref,
        data_source=_source_of(sections),
        digest=fingerprint,
    )
