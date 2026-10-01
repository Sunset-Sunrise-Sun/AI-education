"""已确认 SYSU 字段 → `CourseOffering` 的**确定性**转换与校验。

本模块是 Course Data 的**内部实现**，不是跨模块公共 API。
公共边界只有一个：`CourseDataProvider.get_course_offerings(semester)`
（见 `docs/interfaces/integration.md`，已冻结）。

## 只实现"已经有真实证据"的字段映射

来源：`docs/data/SYSU_COURSE_OFFERING_RECON.md`（`OFFERING-001`，2026-1，`CSE202` → 2 个教学班）。

| Raw 字段（已确认存在） | → | 公共字段 | 说明 |
|---|---|---|---|
| `courseNum` | → | `course_id` | 公共标识**只**用它，不用后台 `courseId` |
| `courseName` | → | `course_name` | |
| `classNumber` | → | `class_id` | 公共标识**只**用它，不用后台 `class_ID` |
| `yearTerm` | → | `semester` | |
| `score` | → | `credit` | **字符串数字** → `number` |
| `teachingName` | → | `teacher` | 可选；教师姓名**不入库**（只在本函数内透传） |
| `limitNumber` | → | `capacity` | |
| `limitNumber - selectedNumber` | → | `remaining_capacity` | ⚠️ **派生值** |

⚠️ **`remaining_capacity` 是派生值**：学校接口**并未直接提供**剩余容量，
它由 `limitNumber - selectedNumber` 相减得到。**不得**把它描述成"接口直接给的字段"。

## 本轮明确**不映射**的字段

- **内部 ID / 计数**：`courseId`、`class_ID`、`sumClassesID`、`sumClassesNum`、
  `outLineId`、`timePlaceId` —— 它们**不等于**公共 `course_id` / `class_id`，
  本模块**只记录其存在**，**不读取、不映射、不落库**；
- **暂缓业务字段**：`courseCategoryName`、`openingUnitName`、`examMode`、`readObj`、
  `teachProgressSubmitState`、`openClass`、`outlineTypeNum` —— 按暂缓字段裁决**不进入公共契约**；
- ⛔ **`weekDay → Meeting.weekday` 与 `openingSchoolName → Meeting.campus` 一律不做**：
  这两个对应关系仍属 Data Gate **C11 的待确认项**，
  **代码里不得出现** `weekday = raw["weekDay"]` / `campus = raw["openingSchoolName"]` 这类 fallback；
- ⛔ **不解析 `teachingTimePlaceStr`**：当前 public Git 没有真实脱敏 Raw string，
  任何"猜分隔符 / 猜 segment 分隔 / 猜字段位置"都属臆测。
  这是**故意的阶段边界**，不是功能遗漏 —— `Meeting` 本轮只能由**已经解析好的明确数据**传入。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.course_data.errors import CourseDataNormalizationError
from app.models.contracts import CourseOffering, DataSource, Meeting

__all__ = ["build_course_offering", "expand_weeks"]


# ---------------------------------------------------------------------------
# 周次：Phase 2B-2A 只接受**已经观察到的两个具体取值**
# ---------------------------------------------------------------------------

#: 已观察到的周次文本 → `(起始周, 结束周, 是否只取单周)`。
#:
#: ⚠️ Phase 2B-2A **不做形状泛化**：不接受任意 `x-y周` / `x-y单周`。
#: 真实证据（`docs/data/SYSU_COURSE_OFFERING_RECON.md` §7）只记录了这**两个取值**：
#: `1-17周` 与 `1-17单周`。
#: 形状相似但**未被观察过**的区间（例如 `3-4周`、`3-15单周`、`3-3周`）
#: 一律拒绝 —— 它们属于"实现能力超过证据"。
#: 后续取得**脱敏真实样本**再据实扩（Phase 2B-2B）。
_OBSERVED_WEEK_TEXTS: dict[str, tuple[int, int, bool]] = {
    "1-17周": (1, 17, False),
    "1-17单周": (1, 17, True),
}

#: 已观察取值的说明，用于错误信息（便于人工对照）。
_SUPPORTED_WEEK_TEXTS = "、".join(f"`{text}`" for text in _OBSERVED_WEEK_TEXTS)


def expand_weeks(text: str) -> list[int]:
    """把**已经观察到的**周次文本展开成实际周次数组。

    Phase 2B-2A 只接受这两个**具体取值**（精确匹配，不做形状泛化）：

    ```text
    1-17周    → [1, 2, 3, …, 17]
    1-17单周  → [1, 3, 5, …, 17]
    ```

    ⛔ **其余一律拒绝** —— 既包括双周、逗号组合、多段组合、单个周次号、
    带"第"字前缀等**形状不同**的形式，也包括
    **形状相似但未被观察过**的区间（例如 `3-4周`、`3-15单周`、`3-3周`）。
    **绝不猜**：不接受任意 `x-y周` / `x-y单周` 的泛化。

    后续取得**脱敏后的真实样本**再据实扩 parser（Phase 2B-2B）。

    只做一处无害规整：去掉首尾空白（不改变格式语义）。
    """

    if not isinstance(text, str):
        raise CourseDataNormalizationError(
            f"周次必须是字符串，实际是 {type(text).__name__}：{text!r}"
        )

    candidate = text.strip()
    if not candidate:
        raise CourseDataNormalizationError("周次文本为空")

    observed = _OBSERVED_WEEK_TEXTS.get(candidate)
    if observed is None:
        raise CourseDataNormalizationError(
            f"暂不支持的周次格式：{text!r}。Phase 2B-2A 只接受已经观察到的两个取值："
            f"{_SUPPORTED_WEEK_TEXTS}；其它范围**即使形状相似也暂时拒绝**（不猜）。"
            f"后续取得脱敏真实样本再扩 parser。"
        )

    start, end, odd_only = observed
    weeks = list(range(start, end + 1))
    return [week for week in weeks if week % 2 == 1] if odd_only else weeks


# ---------------------------------------------------------------------------
# 字段级校验（类型不符合"已确认语义"时一律拒绝）
# ---------------------------------------------------------------------------


def _require(raw: Mapping[str, object], key: str) -> object:
    if key not in raw:
        raise CourseDataNormalizationError(f"缺少必要字段：{key}")
    return raw[key]


def _require_text(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CourseDataNormalizationError(
            f"{key} 必须是非空字符串，实际是 {type(value).__name__}：{value!r}"
        )
    return value


def _require_count(value: object, key: str) -> int:
    """容量 / 人数类字段：按已确认语义要求**整数**（`bool` 不算整数）。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise CourseDataNormalizationError(
            f"{key} 必须是整数，实际是 {type(value).__name__}：{value!r}"
        )
    if value < 0:
        raise CourseDataNormalizationError(f"{key} 不能为负：{value!r}")
    return value


def _parse_credit(value: object) -> float:
    """`score` 是**字符串数字**（已确认真实格式），转换成 `number`。

    ✅ 只接受**已经确认**的形态：字符串数字，例如 `"3"` / `"3.0"` / `" 3 "`
    （去掉首尾空白后仍是数字）。

    ⛔ **数值型 `score`（`3` / `3.0`）目前没有真实来源证据**，因此**当前拒绝**。
    `docs/data/SYSU_COURSE_OFFERING_RECON.md` 只确认了"`score` 是字符串数字"；
    如果后续**脱敏真实样本**显示 `score` 也可能是 JSON number，再据实放宽。

    继续拒绝：布尔、负数、空字符串、非数字文本（例如 `"3学分"`）。
    """

    if not isinstance(value, str):
        raise CourseDataNormalizationError(
            f"score 必须是**字符串**形式的数字（已确认真实格式），"
            f"实际是 {type(value).__name__}：{value!r}；"
            f"数值型 score 尚无真实来源证据，本轮拒绝"
        )

    candidate = value.strip()
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", candidate):
        raise CourseDataNormalizationError(
            f"score 不是合法的字符串数字：{value!r}（已确认真实格式为字符串数字）"
        )

    # 正则已排除符号位，因此结果必然 ≥0。
    return float(candidate)


def _optional_teacher(raw: Mapping[str, object]) -> str | None:
    """`teachingName` → `teacher`（可选）。

    ⚠️ 教师姓名**不入库**：这里只做契约允许的透传，Course Data 不额外存储教师信息。
    """

    if "teachingName" not in raw:
        return None

    value = raw["teachingName"]
    if value is None:
        return None
    if not isinstance(value, str):
        raise CourseDataNormalizationError(
            f"teachingName 类型不符合已确认语义：{type(value).__name__}（{value!r}）"
        )
    return value


def _require_meetings(meetings: Sequence[Meeting]) -> list[Meeting]:
    """本轮 `meetings` **只能由已经解析好的明确数据传入**。

    因此这里拒绝"原始 dict / 未解析结构" —— 那意味着调用方在标准化层之前
    就开始猜 `teachingTimePlaceStr`，而这一层**故意不做解析**。
    """

    if isinstance(meetings, (str, bytes)) or not isinstance(meetings, Sequence):
        raise CourseDataNormalizationError(
            f"meetings 必须是 Meeting 序列，实际是 {type(meetings).__name__}"
        )

    materials = list(meetings)
    if not materials:
        raise CourseDataNormalizationError(
            "meetings 至少需要 1 段：一个教学班不表示一个时间段，但也不能没有时间段"
        )

    for index, item in enumerate(materials):
        if not isinstance(item, Meeting):
            raise CourseDataNormalizationError(
                f"meetings[{index}] 必须是已解析的 Meeting，实际是 {type(item).__name__}；"
                f"本轮不解析 teachingTimePlaceStr，也不接受原始 dict"
            )

    return materials


def _require_source(source: str) -> str:
    """`source` 必须由调用方**显式提供**，绝不从未知 Raw 字段里猜。"""

    if not isinstance(source, str) or not source.strip():
        raise CourseDataNormalizationError(
            f"source 必须由调用方显式提供为非空字符串，实际是 {type(source).__name__}：{source!r}"
        )
    return source


#: 本模块**只会**读取这些 Raw 字段。其余字段一律忽略（不是"遗漏"，是明确边界）。
#:
#: ⚠️ **`selectedNumber` 的处理口径**：当前 2B-2A 的 **narrow normalizer**
#: **基于已观察到的 D5 字段**把它作为必要字段（缺失即失败），因为
#: `remaining_capacity = limitNumber - selectedNumber` 需要它。
#:
#: 这**不等于**"SYSU 所有记录必然都有 `selectedNumber`" ——
#: 该字段是否**总是**存在，目前**没有**证据。
#: **若后续真实脱敏样本出现缺失，再据实调整本内部实现**（不预先放宽，也不对外宣称必然存在）。
_REQUIRED_RAW_FIELDS = (
    "courseNum",
    "courseName",
    "classNumber",
    "yearTerm",
    "score",
    "limitNumber",
    "selectedNumber",
)


def build_course_offering(
    raw: Mapping[str, object],
    *,
    meetings: Sequence[Meeting],
    source: str,
) -> CourseOffering:
    """把**已确认字段**的 Raw 映射成一个合法的公共 `CourseOffering`。

    - `meetings` 由调用方传入**已经解析好的** `Meeting` 序列（至少 1 项）；
    - `source` 由调用方**显式提供**；
    - 输出 `data_source` **强制为 `real`**；
    - 返回对象会再由 `CourseOffering`（Pydantic）校验一次。

    ⚠️ 这是 Course Data **内部函数**，不是跨模块公共 API。
    """

    if not isinstance(raw, Mapping):
        raise CourseDataNormalizationError(
            f"raw 必须是字段映射，实际是 {type(raw).__name__}"
        )

    resolved_source = _require_source(source)
    resolved_meetings = _require_meetings(meetings)

    course_id = _require_text(_require(raw, "courseNum"), "courseNum")
    course_name = _require_text(_require(raw, "courseName"), "courseName")
    class_id = _require_text(_require(raw, "classNumber"), "classNumber")
    semester = _require_text(_require(raw, "yearTerm"), "yearTerm")

    credit = _parse_credit(_require(raw, "score"))
    capacity = _require_count(_require(raw, "limitNumber"), "limitNumber")
    selected = _require_count(_require(raw, "selectedNumber"), "selectedNumber")

    if selected > capacity:
        raise CourseDataNormalizationError(
            f"selectedNumber({selected}) 不能大于 limitNumber({capacity})："
            f"{class_id}"
        )

    # ⚠️ 派生值：学校接口没有直接提供剩余容量，它是相减得到的。
    remaining_capacity = capacity - selected

    return CourseOffering(
        course_id=course_id,
        course_name=course_name,
        class_id=class_id,
        semester=semester,
        teacher=_optional_teacher(raw),
        credit=credit,
        meetings=resolved_meetings,
        capacity=capacity,
        remaining_capacity=remaining_capacity,
        source=resolved_source,
        data_source=DataSource.REAL,
    )
