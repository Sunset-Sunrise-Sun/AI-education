"""与 `/schemas/*.schema.json` 一一对应的 Pydantic 模型（后端校验层）。

设计约束（来自 `/AGENTS.md` 第 4 节）：

- **公共真源是 `/schemas/*.schema.json`，不是本文件。**
  本文件只是给 FastAPI 用的等价映射，任何字段名、类型、枚举、限制都必须与 Schema 一致。
- 本文件**不得**为了让实现方便而新增字段。
  公共 Schema 中不存在的字段（例如 MakeupTask 的 `data_source`）在本文件中也不存在。
- 如果发现 Schema 不够用，先输出 `【接口变更请求】` 并等待人工确认，不得先改代码。

字段类型映射说明（Pydantic 与 JSON Schema 的固有差异，已在测试中单独覆盖）：

- `number` → `float`。Pydantic 的 `float` 接受整数（JSON 中 `3` 与 `3.0` 都是 `number`），语义一致。
- `["string", "null"]` → `str | None`。
- `"type": "array"` + `"default": []` → `list[...] = Field(default_factory=list)`，
  默认值不可用可变对象，否则所有实例会共享同一个列表。
- `"additionalProperties": false` → `model_config = ConfigDict(extra="forbid")`。

对齐关系由 `backend/tests/test_contracts.py`（关键字段 / 枚举 / 边界 / 非法输入）
与 `backend/tests/test_mock_data_schema.py`（按真实 Schema 校验 Mock 数据）共同保证。
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

__all__ = [
    "Change",
    "Course",
    "CourseIdList",
    "CourseOffering",
    "DataSource",
    "MakeupStatus",
    "MakeupTask",
    "Meeting",
    "PlanResult",
    "PlanStatus",
    "PositiveIntList",
    "Preference",
    "Risk",
    "RiskLevel",
    "SelectedClass",
    "TimeBlock",
    "UniqueStrList",
    "Unresolved",
]

# 与公共 Schema 中 `additionalProperties: false` 对应。
_FORBID_EXTRA = ConfigDict(extra="forbid")


def _reject_duplicates(values: object) -> object:
    """落实公共 Schema 的 `uniqueItems: true`。

    Pydantic 没有内置的「数组元素不重复」约束，必须自己校验，
    否则模型会比公共 Schema 宽松——那属于悄悄放宽公共契约。

    说明：Pydantic 不会把 `uniqueItems` 写进 `model_json_schema()`，
    所以本模型在这一点上比公共 Schema **更严格**（合法的数据仍然全部通过，
    只是额外拒绝重复项）。这是有意的收紧，方向安全，已在
    `tests/test_contracts.py::test_unique_items_fields_are_enforced_at_runtime`
    与 `test_duplicate_items_are_rejected` 中显式验证。
    """

    if not isinstance(values, list):
        return values

    seen: set[object] = set()
    duplicates: list[object] = []
    for value in values:
        if value in seen:
            duplicates.append(value)
        seen.add(value)

    if duplicates:
        raise ValueError(f"不允许重复项，出现重复：{sorted({str(d) for d in duplicates})}")

    return values


#: 元素不重复的字符串数组。公共 Schema 里所有 `uniqueItems: true` 的字符串数组都用它。
UniqueStrList = Annotated[list[str], BeforeValidator(_reject_duplicates)]

#: 课程号数组：元素非空且不重复。
#: 对应公共 Schema 中 `{"type": "array", "items": {"type": "string", "minLength": 1},
#: "uniqueItems": true}` —— 例如 Course.prerequisites 与 MakeupTask.prerequisites。
#: `minLength: 1` 必须加在**元素**上，而不是数组本身，否则会变成「数组至少 1 项」，
#: 与公共 Schema 的语义不同（公共 Schema 允许空数组）。
CourseIdList = Annotated[
    list[Annotated[str, Field(min_length=1)]],
    BeforeValidator(_reject_duplicates),
]

#: 正整数数组：元素 ≥1 且不重复。
#: 对应公共 Schema 中 `{"type": "array", "items": {"type": "integer", "minimum": 1},
#: "minItems": 1, "uniqueItems": true}` —— 即 `Meeting.weeks`。
#: `minimum: 1` 加在**元素**上（与 CourseIdList 同理）；
#: `uniqueItems` 同样由 `_reject_duplicates` 在运行时强制：
#: Pydantic 不会把 `uniqueItems` 生成为 Schema 关键字，不显式校验就会比公共契约更宽松。
PositiveIntList = Annotated[
    list[Annotated[int, Field(ge=1)]],
    BeforeValidator(_reject_duplicates),
]


class DataSource(str, Enum):
    """`course_offering.schema.json` 中 `data_source` 的取值。"""

    MOCK = "mock"
    REAL = "real"


class MakeupStatus(str, Enum):
    """`makeup_task.schema.json` 中 `status` 的取值。"""

    REQUIRED = "required"
    POSSIBLY_EQUIVALENT = "possibly_equivalent"
    MANUAL_CONFIRMATION = "manual_confirmation"
    SATISFIED = "satisfied"


class PlanStatus(str, Enum):
    """`plan_result.schema.json` 中 `status` 的取值。"""

    FEASIBLE = "feasible"
    PARTIALLY_FEASIBLE = "partially_feasible"
    INFEASIBLE = "infeasible"


class RiskLevel(str, Enum):
    """`plan_result.schema.json` 中 `risks[].level` 的取值。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Course(BaseModel):
    """对应 `schemas/course.schema.json`。

    必填：`course_id`、`course_name`、`credit`。
    """

    model_config = _FORBID_EXTRA

    course_id: str = Field(min_length=1, description="课程号，非空字符串")
    course_name: str = Field(min_length=1, description="课程名称，非空字符串")
    credit: float = Field(ge=0, description="学分，非负")
    course_type: str | None = None
    recommended_semester: int | None = Field(default=None, ge=1)
    prerequisites: CourseIdList = Field(
        default_factory=list, description="先修课程号，元素非空且不重复"
    )
    source: str | None = None


class Meeting(BaseModel):
    """`course_offering.schema.json` 中 `meetings[]` 的元素（一段上课时间 / 地点）。

    概念关系是 **`CourseOffering` 1 —— N `Meeting`**：
    一个教学班不等同一个时间段，可以有多个独立的排课段
    （例如"周一 3-4 节 1-16 周"与"周三 5-6 节 1-16 单周"）。

    必填：`weekday`、`start_section`、`end_section`、`weeks`。

    ⚠️ 本类**不含 `teacher`**。真实 D5 中 segment 与教师确实存在关联，
    但 Data Gate-1 的架构裁决把 meeting 级教师关联登记为
    **known deferred representation gap**：MVP 不依赖它，
    教师仍作为教学班汇总字段保留在 `CourseOffering.teacher`。
    """

    model_config = _FORBID_EXTRA

    weekday: int = Field(ge=1, le=7, description="1=周一 … 7=周日")
    start_section: int = Field(ge=1, description="起始节次")
    end_section: int = Field(ge=1, description="结束节次")
    weeks: PositiveIntList = Field(
        min_length=1, description="实际周次数组，至少 1 项且不重复"
    )
    campus: str | None = None
    classroom: str | None = None


class CourseOffering(BaseModel):
    """对应 `schemas/course_offering.schema.json`。

    必填：`course_id`、`course_name`、`class_id`、`semester`、`meetings`。

    **Data Gate-2（DG-01）后的结构**：排课信息不再位于顶层，
    而是收敛到 `meetings[]`（一个教学班可以有多个段）。旧的顶层
    `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom`
    已**彻底移除**，因为一个教学班可以有多个独立的时间 / 地点段，
    单组字段无法无损表达（G9）。

    ⚠️ 这是**有意的 breaking migration**：不保留兼容字段，旧结构一律被拒绝。
    消费方（Planner / 前端）必须遍历 `meetings[]`，不得只看第一段。

    **DG-07A（Contract Migration）起**：`meetings` 允许为空数组（`minItems: 0`），
    但 `meetings` 本身**仍是必填**（缺字段 / `null` 均非法）。

    - `meetings` 非空 → 来源提供了可用排课信息，必须保留全部可解析 segment；
    - `meetings == []` → **仅**表示"当前来源快照没有能够形成公共 `Meeting`
      的可用排课信息"；
      ⛔ **不表示**没有上课时间、异步教学、时间自由；
      ⛔ **更不表示没有时间冲突**（`meetings == []` ≠ conflict-free）。

    ⚠️ **rollout gate（DG-07B / DG-07C / DG-07D 完成前）**：
    契约层虽已允许 `meetings == []`，但**生产真实数据链路不得主动产生或接入**
    empty-meeting `CourseOffering`；Course Data 仍对"缺排课信息"fail closed。

    注意：这是公共 Schema 中**唯一**带 `data_source` 的对象。
    """

    model_config = _FORBID_EXTRA

    course_id: str = Field(min_length=1)
    course_name: str = Field(min_length=1)
    class_id: str = Field(min_length=1, description="教学班号")
    semester: str = Field(min_length=1, description="学期标识，例如 2026-1")
    teacher: str | None = Field(
        default=None, description="教学班汇总 / 展示用教师；meeting 级教师关联暂缓"
    )
    credit: float | None = Field(default=None, ge=0)
    meetings: list[Meeting] = Field(
        min_length=0,
        description=(
            "排课段，允许 0..N；空数组仅表示当前来源快照没有可用排课信息，"
            "不表示无课、异步、时间自由或无冲突"
        ),
    )
    capacity: int | None = Field(default=None, ge=0)
    remaining_capacity: int | None = Field(default=None, ge=0)
    source: str | None = None
    data_source: DataSource = DataSource.MOCK


class MakeupTask(BaseModel):
    """对应 `schemas/makeup_task.schema.json`。

    必填：`course_id`、`course_name`、`credit`、`status`。

    注意：公共 Schema 中**没有** `data_source` 字段，因此本模型也不提供。
    """

    model_config = _FORBID_EXTRA

    course_id: str = Field(min_length=1)
    course_name: str = Field(min_length=1)
    credit: float = Field(ge=0)
    status: MakeupStatus
    deadline_semester: int | None = Field(default=None, ge=1)
    recommended_semester: int | None = Field(default=None, ge=1)
    prerequisites: CourseIdList = Field(default_factory=list)
    reason: str | None = None
    source_evidence: str | None = Field(
        default=None,
        description="该判定所依据的材料来源，便于人工复核；Mock 数据必须写明是演示数据",
    )


class TimeBlock(BaseModel):
    """`preference.schema.json` 中 `avoid_times[]` 的元素。"""

    model_config = _FORBID_EXTRA

    weekday: int = Field(ge=1, le=7)
    start_section: int = Field(ge=1)
    end_section: int = Field(ge=1)


class Preference(BaseModel):
    """对应 `schemas/preference.schema.json`。

    所有字段均为可选，因此一个空的 `{}` 也是合法的 Preference。
    """

    model_config = _FORBID_EXTRA

    max_credit: float | None = Field(default=None, ge=0)
    avoid_cross_campus: bool = False
    preferred_courses: UniqueStrList = Field(default_factory=list)
    avoid_times: list[TimeBlock] = Field(default_factory=list)
    notes: str | None = None


class SelectedClass(BaseModel):
    """`plan_result.schema.json` 中 `selected_classes[]` 的元素。"""

    model_config = _FORBID_EXTRA

    course_id: str
    class_id: str


class Change(BaseModel):
    """`plan_result.schema.json` 中 `changes[]` 的元素。"""

    model_config = _FORBID_EXTRA

    course_id: str
    from_class: str | None = None
    to_class: str | None = None
    reason: str


class Risk(BaseModel):
    """`plan_result.schema.json` 中 `risks[]` 的元素。"""

    model_config = _FORBID_EXTRA

    course_id: str | None = None
    level: RiskLevel
    reason: str


class Unresolved(BaseModel):
    """`plan_result.schema.json` 中 `unresolved[]` 的元素。

    类型不加枚举：公共 Schema 对 `unresolved[].type` 只要求字符串，
    后端不应擅自收紧上游可以输出的类别。
    """

    model_config = _FORBID_EXTRA

    type: str
    message: str


class PlanResult(BaseModel):
    """对应 `schemas/plan_result.schema.json`。

    必填：`status`、`selected_classes`、`changes`、`risks`、`unresolved`。
    `changes` / `risks` / `unresolved` 允许为空数组，但不可缺省。
    """

    model_config = _FORBID_EXTRA

    status: PlanStatus
    selected_classes: list[SelectedClass]
    changes: list[Change]
    risks: list[Risk]
    unresolved: list[Unresolved]
    objective_summary: str | None = None
