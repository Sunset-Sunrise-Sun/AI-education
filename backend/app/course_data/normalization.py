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
- ✅ **`teachingTimePlaceStr` 的解析在 `app/course_data/schedule_parser.py`**（Phase 2B-2B）：
  本模块仍然**不解析**原始串，只接收**已经解析好的** `Meeting`。
  `weekday` 一律来自 segment 自身（`parse_weekday`），**不来自 Raw `weekDay`**。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.course_data.errors import CourseDataNormalizationError
from app.models.contracts import CourseOffering, DataSource, Meeting

__all__ = [
    "build_course_offering",
    "build_course_offering_from_missing_schedule_field",
    "expand_weeks",
]


# ---------------------------------------------------------------------------
# 周次：Phase 2B-2B 依据**脱敏真实样本**重新界定
# ---------------------------------------------------------------------------

#: 普通连续周次 `N-M周`（`N >= 1`，`M >= N`）。
#:
#: 真实脱敏样本已确认存在多种范围与**退化区间**：
#: `1-5周`、`1-6周`、`1-8周`、**`6-6周`**、`7-8周`、`10-17周`。
#: 因此普通周次允许任意 `N-M周`（`M >= N`，含 `M == N`）。
#:
#: 用 `[0-9]` 而不是 `\d`：Python 的 `\d` 会匹配全角等 Unicode 数字，
#: 那属于"未确认的格式"，一律拒绝而不是宽容接受。
_PLAIN_WEEK_RANGE = re.compile(r"^([0-9]+)-([0-9]+)周$")

#: 单周语法形状 `N-M单周`。
#: 只用于**识别**"这看起来像单周"，实际取值仍必须命中 `_ODD_WEEK_TEXTS` 白名单。
_ODD_WEEK_RANGE = re.compile(r"^([0-9]+)-([0-9]+)单周$")

#: 单周：**仍然只允许已观察到的精确取值**。
#:
#: ⛔ Phase 2B-2B **不把单周泛化成任意 `N-M单周`** ——
#: 真实样本只确认了 `1-17单周` 这一个取值。
_ODD_WEEK_TEXTS: dict[str, tuple[int, int]] = {
    "1-17单周": (1, 17),
}

_SUPPORTED_WEEK_TEXTS = (
    "普通连续周次 `N-M周`（`N >= 1`、`M >= N`）与单周 `1-17单周`"
)


def expand_weeks(text: str) -> list[int]:
    """把**已确认语法**的周次文本展开成实际周次数组。

    当前支持（依据 Phase 2B-2B 的脱敏真实样本）：

    ```text
    1-5周 / 1-6周 / 1-8周 / 7-8周 / 10-17周   → 连续周次
    6-6周                                     → [6]（退化区间**合法**）
    1-17单周                                  → [1, 3, 5, …, 17]
    ```

    规则：

    - 普通周次 `N-M周`：要求 `N >= 1` 且 `M >= N`（**允许 `M == N`**）；
    - 单周：**只**接受已观察到的精确取值 `1-17单周`，
      **不泛化成任意 `N-M单周`**（那一形态尚无证据）；
    - ⛔ 其余一律拒绝：双周、逗号组合（`1,3,5周`）、带"第"字前缀（`第1-17周`）、
      波浪号（`1~17周`）、全角数字、其它组合格式。

    后续如真实样本出现新的周次语法，**按证据**再加；不凭经验扩展。

    这是 Course Data **内部函数**，不是跨模块公共 API。
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
        observed = _ODD_WEEK_TEXTS.get(candidate)
        if observed is None:
            raise CourseDataNormalizationError(
                f"暂不支持的单周格式：{text!r}。当前只接受已观察到的精确取值 "
                f"`1-17单周`；单周暂不泛化为任意 `N-M单周`（尚无证据）。"
            )
        start, end = observed
        return [week for week in range(start, end + 1) if week % 2 == 1]

    plain_match = _PLAIN_WEEK_RANGE.match(candidate)
    if plain_match:
        start, end = (int(group) for group in plain_match.groups())
        if start < 1:
            raise CourseDataNormalizationError(
                f"周次起点必须 ≥1：{text!r}（解析出 start={start}）"
            )
        if end < start:
            raise CourseDataNormalizationError(
                f"周次区间非法（结束早于开始）：{text!r}（start={start}, end={end}）"
            )
        return list(range(start, end + 1))

    raise CourseDataNormalizationError(
        f"暂不支持的周次格式：{text!r}。当前支持 {_SUPPORTED_WEEK_TEXTS}；"
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
    """普通路径的 `meetings` **只能由已经解析好的明确数据传入**，且**必须非空**。

    因此这里拒绝"原始 dict / 未解析结构" —— 那意味着调用方在标准化层之前
    就开始猜 `teachingTimePlaceStr`，而这一层**故意不做解析**。

    ⚠️ **DG-07B 后本条仍然有效**：空 `meetings` **不**能从这里进入。
    只有 `build_course_offering_from_missing_schedule_field()` 这一条**窄路径**
    （要求 Raw row **真的没有** `teachingTimePlaceStr` 这个 key）才允许 `meetings = []`。
    """

    if isinstance(meetings, (str, bytes)) or not isinstance(meetings, Sequence):
        raise CourseDataNormalizationError(
            f"meetings 必须是 Meeting 序列，实际是 {type(meetings).__name__}"
        )

    materials = list(meetings)
    if not materials:
        raise CourseDataNormalizationError(
            "meetings 至少需要 1 段：普通路径不接受空数组；"
            "来源快照没有可用排课信息时，必须走 "
            "build_course_offering_from_missing_schedule_field()（要求该字段 key 真的不存在）"
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


#: 排课字段名（Raw 侧）。**只有**它"属性不存在"时才允许走 empty path（DG-07B）。
_SCHEDULE_RAW_FIELD = "teachingTimePlaceStr"


def _build_common_offering_fields(raw: Mapping[str, object], *, source: str) -> dict[str, object]:
    """**共用**的公共字段构造（不含 `meetings`）。

    ⛔ 这里**只有一份**字段映射：正常 Meeting 路径与 missing-schedule 路径**共用它**，
    避免两处复制 `courseNum` / `courseName` / `classNumber` / `yearTerm` / `score` /
    `limitNumber` / `selectedNumber` 的转换逻辑。

    这是 Course Data **内部** private helper：不进 `docs/interfaces/`、不进 Provider / API、
    不是新的公共 Schema。
    """

    if not isinstance(raw, Mapping):
        raise CourseDataNormalizationError(
            f"raw 必须是字段映射，实际是 {type(raw).__name__}"
        )

    resolved_source = _require_source(source)

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

    return {
        "course_id": course_id,
        "course_name": course_name,
        "class_id": class_id,
        "semester": semester,
        "teacher": _optional_teacher(raw),
        "credit": credit,
        "capacity": capacity,
        "remaining_capacity": remaining_capacity,
        "source": resolved_source,
        "data_source": DataSource.REAL,
    }


def build_course_offering(
    raw: Mapping[str, object],
    *,
    meetings: Sequence[Meeting],
    source: str,
) -> CourseOffering:
    """把**已确认字段**的 Raw 映射成一个合法的公共 `CourseOffering`（**普通路径**）。

    - `meetings` 由调用方传入**已经解析好的** `Meeting` 序列（**至少 1 项**）；
    - `source` 由调用方**显式提供**；
    - 输出 `data_source` **强制为 `real`**；
    - 返回对象会再由 `CourseOffering`（Pydantic）校验一次。

    ⚠️ **DG-07B**：本函数**仍然拒绝空 `meetings`**。
    "来源快照没有可用排课信息"必须走
    `build_course_offering_from_missing_schedule_field()`，不得从此处放行。

    ⚠️ 这是 Course Data **内部函数**，不是跨模块公共 API。
    """

    resolved_meetings = _require_meetings(meetings)

    return CourseOffering(
        **_build_common_offering_fields(raw, source=source),  # type: ignore[arg-type]
        meetings=resolved_meetings,
    )


def build_course_offering_from_missing_schedule_field(
    raw: Mapping[str, object],
    *,
    source: str,
) -> CourseOffering:
    """**窄语义**路径：仅当 Raw row **真的没有** `teachingTimePlaceStr` 这个 key 时，
    构造 `meetings = []` 的 `CourseOffering`（DG-07B）。

    ⛔ 语义边界（必须逐条成立）：

    - **key 不存在** → 允许（来源快照没有提供可形成公共 `Meeting` 的排课信息）；
    - key 存在但 `null` / `""` / `"   "` / 数字 / 对象 / 列表 / 合法文本
      → **一律拒绝**，必须回普通 parser 路径 —— 那属于
      "字段存在但解析失败"，与"字段不存在"是**两类不同状态**，DG-07 的核心目的
      就是保证它们**永远不会被混淆**；
    - 本函数**不解析**任何排课文本，**不**吞任何 parser / normalization 异常
      （它根本不调用 parser）。

    字段映射与普通路径**共用** `_build_common_offering_fields()`，
    因此 `data_source` / `source` / 其它字段语义完全一致。

    ⚠️ 这是 Course Data **内部函数**：不进 `docs/interfaces/`、不进 Provider / API、
    不是新的公共 Schema。
    """

    if not isinstance(raw, Mapping):
        raise CourseDataNormalizationError(
            f"raw 必须是字段映射，实际是 {type(raw).__name__}"
        )

    # ⛔ 唯一的准入条件：key **真的不存在**。
    if _SCHEDULE_RAW_FIELD in raw:
        # 不回显取值（可能含真实教师 / 教室文本），只说明"该走普通路径"。
        raise CourseDataNormalizationError(
            f"Raw row 存在 `{_SCHEDULE_RAW_FIELD}` 字段，不得走 missing-schedule 路径："
            f"字段存在时必须由 parser 解析，解析失败应整体失败（不回显取值）"
        )

    return CourseOffering(
        **_build_common_offering_fields(raw, source=source),  # type: ignore[arg-type]
        meetings=[],
    )
