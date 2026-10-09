"""学分上限的确定性接纳校验（Planner 内部，**不改变优化目标**）。

```text
current_schedule（原课表，学生已选事实）  +  proposed（本次建议新增的班）
        ↓  credit_ledger(...)
已声明学分合计 / 是否有课程没有声明学分
        ↓  cap_violation(...)
within_limit | over_limit | unverifiable | not_declared
```

## 为什么需要它

`RestrictedPlannerProvider` 会把"唯一 CLEAR 新增"加进建议课表。
新增本身没有时间冲突 ≠ 这次建议**仍然符合学生自己声明的学分上限**：
两门各 3 学分的课可以完全不冲突，却让"上限 4 学分"的学生超限。

本模块只做**一件事**：把"已声明的学分上限"变成对**候选集合**的确定性判断，
供 Provider 决定是否真的把新增放进建议课表。它：

- ⛔ 不做时间冲突判断（那是 `conflicts.py`）；
- ⛔ 不排序、不评分、不挑选新增（不定义优先级）；
- ⛔ 不给课程编造学分；
- ⛔ 不修改学校规则、不修改公共 Schema。

## 学分从哪里来（不猜）

按固定的、可复核的顺序取值，取不到就是**没有声明**：

1. 该 `CourseOffering.credit`（教学班自己的学分声明）；
2. 否则该课程在本次 `MakeupTask[]` 中的 `credit`（Curriculum 给出的学分）。

两者都没有 → 这门课的学分**未知**（`None`），绝不按 0 计、也绝不按别的课推测。

## 为什么"有未知学分"时不放行

`Preference.max_credit` 是学生**本人**声明的上限。当建议课表里有课程学分未知时，
"合计 ≤ 上限"**无法证明**：既不能证明超限，也不能证明不超限。
这种情况返回 `unverifiable`，由调用方显式报告待确认，
⛔ 不得把它当成"已通过校验"。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.models.contracts import CourseOffering, MakeupTask, Preference

__all__ = [
    "CREDIT_STATE_NOT_DECLARED",
    "CREDIT_STATE_OVER_LIMIT",
    "CREDIT_STATE_UNVERIFIABLE",
    "CREDIT_STATE_WITHIN_LIMIT",
    "CreditLedger",
    "credit_ledger",
    "credit_state",
    "task_credit_map",
]

#: 学生没有声明学分上限 → 本模块不判断（⛔ 也不擅自发明一个上限）。
CREDIT_STATE_NOT_DECLARED = "not_declared"

#: 已声明的学分合计可以证明**不超过**上限。
CREDIT_STATE_WITHIN_LIMIT = "within_limit"

#: 已声明的学分合计可以证明**超过**上限。
CREDIT_STATE_OVER_LIMIT = "over_limit"

#: 存在没有声明学分的课程 → 上限是否满足**无法证明**（⛔ 不等于通过）。
CREDIT_STATE_UNVERIFIABLE = "unverifiable"

#: 原课表本身已经超限（只提示，⛔ 不篡改学生的已选事实）。
CREDIT_STATE_ORIGINAL_OVER_LIMIT = "original_over_limit"


def _credit_of(offering: CourseOffering) -> float | None:
    value = getattr(offering, "credit", None)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


@dataclass(frozen=True, slots=True)
class CreditLedger:
    """一组教学班的学分合计 + 哪些课没有声明学分。"""

    declared_total: float
    unknown_course_ids: tuple[str, ...]
    course_count: int

    def __post_init__(self) -> None:
        value = self.declared_total
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("declared_total 必须是数值。")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError("declared_total 必须是非负有限数值。")
        object.__setattr__(self, "declared_total", number)
        object.__setattr__(self, "unknown_course_ids", tuple(self.unknown_course_ids))
        if isinstance(self.course_count, bool) or not isinstance(self.course_count, int):
            raise TypeError("course_count 必须是整数。")

    @property
    def complete(self) -> bool:
        """每一门课的学分都已声明。"""

        return not self.unknown_course_ids


def credit_ledger(
    offerings: Sequence[CourseOffering],
    *,
    task_credits: Mapping[str, float] | None = None,
) -> CreditLedger:
    """按``CourseOffering.credit`` → ``MakeupTask.credit`` 的顺序统计学分。

    - ⛔ 不把缺失学分当成 0；
    - ⛔ 不按同类课程推测学分；
    - 同一 `course_id` 出现多次时**逐次计入**（不同教学班不合并）。
    """

    if isinstance(offerings, (str, bytes)) or not isinstance(offerings, Sequence):
        raise TypeError("offerings 必须是 CourseOffering 序列。")
    fallback: Mapping[str, float] = task_credits or {}
    total = 0.0
    unknown: list[str] = []
    for index, offering in enumerate(offerings):
        if not isinstance(offering, CourseOffering):
            raise TypeError("offerings 中每项必须是 CourseOffering。")
        credit = _credit_of(offering)
        if credit is None:
            candidate = fallback.get(offering.course_id)
            credit = _credit_of_candidate(candidate)
        if credit is None:
            if offering.course_id not in unknown:
                unknown.append(offering.course_id)
            continue
        total += credit
    return CreditLedger(total, tuple(unknown), len(offerings))


def _credit_of_candidate(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


def credit_state(preference: Preference, ledger: CreditLedger) -> str:
    """把一次学分统计翻译成固定状态。

    ⛔ 不返回布尔值：`unverifiable` 与 `over_limit` 是两种不同的结论，
    调用方必须分开处理（前者是"待确认"，后者是"已确认越界"）。
    """

    if not isinstance(preference, Preference):
        raise TypeError("preference 必须是 Preference。")
    if not isinstance(ledger, CreditLedger):
        raise TypeError("ledger 必须是 CreditLedger。")
    limit = preference.max_credit
    if limit is None:
        return CREDIT_STATE_NOT_DECLARED
    if not ledger.complete:
        return CREDIT_STATE_UNVERIFIABLE
    return CREDIT_STATE_OVER_LIMIT if ledger.declared_total > limit else CREDIT_STATE_WITHIN_LIMIT


def task_credit_map(tasks: Sequence[MakeupTask]) -> dict[str, float]:
    """`course_id -> credit` 的只读映射，供 ``credit_ledger`` 作为兜底取值。

    同一课程出现多条任务时保留**第一条**（`MakeupTask[]` 本身不允许重复
    `course_id`，这里的保序行为只是不让重复输入静默改写取值）。
    """

    if isinstance(tasks, (str, bytes)) or not isinstance(tasks, Sequence):
        raise TypeError("tasks 必须是 MakeupTask 序列。")
    result: dict[str, float] = {}
    for task in tasks:
        if not isinstance(task, MakeupTask):
            raise TypeError("tasks 中每项必须是 MakeupTask。")
        result.setdefault(task.course_id, task.credit)
    return result
