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
# 周次：只支持"已经记录过"的两种原子格式
# ---------------------------------------------------------------------------

#: `1-17周` —— 连续周次。
#: 用 `[0-9]` 而不是 `\d`：Python 的 `\d` 会匹配全角等 Unicode 数字，
#: 那属于"未确认的格式"，一律拒绝而不是宽容接受。
_PLAIN_WEEK_RANGE = re.compile(r"^([0-9]+)-([0-9]+)周$")

#: `1-17单周` —— 奇数周次。
_ODD_WEEK_RANGE = re.compile(r"^([0-9]+)-([0-9]+)单周$")

#: 已知可支持的周次格式说明，用于错误信息（便于人工对照）。
_SUPPORTED_WEEK_FORMATS = "`1-17周`（连续）与 `1-17单周`（单周）"


def _week_range_bounds(start: int, end: int, raw_text: str) -> None:
    if start < 1:
        raise CourseDataNormalizationError(
            f"周次起点必须 ≥1：{raw_text!r}（解析出 start={start}）"
        )
    if end < start:
        raise CourseDataNormalizationError(
            f"周次区间非法（结束早于开始）：{raw_text!r}（start={start}, end={end}）"
        )


def expand_weeks(text: str) -> list[int]:
    """把**已确认格式**的周次文本展开成实际周次数组。

    当前只支持 `docs/data/SYSU_COURSE_OFFERING_RECON.md` §7 记录过的两种：

    ```text
    1-17周    → [1, 2, 3, …, 17]
    1-17单周  → [1, 3, 5, …, 17]
    ```

    ⛔ **其余格式一律拒绝**（双周、逗号组合、多段组合、单个周次号、
    带"第"字前缀、其它未知语法），**绝不猜**。
    后续取得**脱敏后的真实样本**再扩 parser。

    只做一处无害规整：去掉首尾空白（不改变格式语义）。
    """

    if not isinstance(text, str):
        raise CourseDataNormalizationError(
            f"周次必须是字符串，实际是 {type(text).__name__}：{text!r}"
        )

    candidate = text.strip()
    if not candidate:
        raise CourseDataNormalizationError("周次文本为空")

    odd_match = _ODD_WEEK_RANGE.match(candidate)
    if odd_match:
        start, end = (int(group) for group in odd_match.groups())
        _week_range_bounds(start, end, candidate)
        return [week for week in range(start, end + 1) if week % 2 == 1]

    plain_match = _PLAIN_WEEK_RANGE.match(candidate)
    if plain_match:
        start, end = (int(group) for group in plain_match.groups())
        _week_range_bounds(start, end, candidate)
        return list(range(start, end + 1))

    raise CourseDataNormalizationError(
        f"暂不支持的周次格式：{text!r}。当前仅支持 {_SUPPORTED_WEEK_FORMATS}；"
        f"其余格式需取得脱敏真实样本后再实现，本轮不猜。"
    )


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

    接受：`"3"`、`"3.0"`、`" 3 "` 这类字符串数字，以及等价的 `int` / `float`。
    拒绝：布尔、负数、空串、非数字文本（例如 `"3学分"`）。
    """

    if isinstance(value, bool):
        raise CourseDataNormalizationError(f"score 不能是布尔值：{value!r}")

    if isinstance(value, (int, float)):
        credit = float(value)
    elif isinstance(value, str):
        candidate = value.strip()
        if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", candidate):
            raise CourseDataNormalizationError(
                f"score 不是合法的字符串数字：{value!r}（已确认真实格式为字符串数字）"
            )
        credit = float(candidate)
    else:
        raise CourseDataNormalizationError(
            f"score 类型不符合已确认语义：{type(value).__name__}（{value!r}）"
        )

    if credit < 0:
        raise CourseDataNormalizationError(f"score 不能为负：{value!r}")

    return credit


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
