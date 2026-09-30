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
    "PlanResult",
    "PlanStatus",
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


class CourseOffering(BaseModel):
    """对应 `schemas/course_offering.schema.json`。

    必填：`course_id`、`course_name`、`class_id`、`weekday`、
    `start_section`、`end_section`、`weeks`、`semester`。

    注意：这是公共 Schema 中**唯一**带 `data_source` 的对象。
    """

    model_config = _FORBID_EXTRA

    course_id: str = Field(min_length=1)
    course_name: str = Field(min_length=1)
    class_id: str = Field(min_length=1, description="教学班号")
    semester: str = Field(min_length=1, description="学期标识，例如 2026-1")
    teacher: str | None = None
    credit: float | None = Field(default=None, ge=0)
    weekday: int = Field(ge=1, le=7, description="1=周一 … 7=周日")
    start_section: int = Field(ge=1, description="起始节次")
    end_section: int = Field(ge=1, description="结束节次")
    weeks: list[Annotated[int, Field(ge=1)]] = Field(
        min_length=1, description="实际周次数组，至少 1 项且不重复"
    )
    campus: str | None = None
    classroom: str | None = None
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
