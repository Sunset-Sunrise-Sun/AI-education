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
| `limitNumber` | → | `capacity` | 来源原始字段，⛔ 不改写 |
| `limitNumber` / `selectedNumber` | → | `remaining_capacity` | ⚠️ **派生值**，见下方三分支规则 |

⚠️ **`remaining_capacity` 是派生值**：学校接口**并未直接提供**剩余容量。
真实 2026-1 east artifact 已证明来源里确实存在 `selectedNumber > limitNumber`
（超员状态），因此**不得**再因为这一关系拒绝整条教学班；
但此时做减法也**无法**可靠产出符合公共契约的非负剩余容量。规则：

```text
selectedNumber <  limitNumber → remaining_capacity = limitNumber - selectedNumber
selectedNumber == limitNumber → remaining_capacity = 0
selectedNumber >  limitNumber → remaining_capacity = None（unknown）
```

- ⛔ **不 clamp 到 0**、⛔ **不修改 `capacity`**（它保持来源原值）、⛔ **不新增 `selected_count`**、
  ⛔ **不修改公共 Schema**、⛔ **不猜学校为何超额**；
- `None` 表示"**该派生值不可用**"，⛔ 不代表"已满"、⛔ 也不代表"无剩余"。

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
    "build_course_offering_from_non_concrete_schedule",
    "expand_weeks",
    "is_plain_week_range",
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

#: 单周语法形状 `N-M单周`（区间内取**奇数周**）。
#:
#: ⚠️ Architecture Review 裁定（2026-1 east artifact 已确认存在 `N-M单周` 13 处）
#: 起**泛化**为任意 `N-M单周`（此前只允许精确取值 `1-17单周`）。
_ODD_WEEK_RANGE = re.compile(r"^([0-9]+)-([0-9]+)单周$")

#: 双周语法形状 `N-M双周`（区间内取**偶数周**）。
_EVEN_WEEK_RANGE = re.compile(r"^([0-9]+)-([0-9]+)双周$")

#: **weeks 字段**已批准的 qualifier 白名单（Architecture Review 裁定）。
#:
#: ⛔ 这是**独立**于 `_KNOWN_SCHEDULE_QUALIFIERS`（parser 的 non-concrete 路径）
#: 与 sections suffix 白名单的**第三张**白名单：三处取值即使重合也**互不牵连**。
#: ⛔ **sections 的 `线上` 不适用于 weeks 字段**（`N-M周线上` 继续 fail closed）。
WEEK_QUALIFIER_OFF_CAMPUS = "校外"
WEEK_QUALIFIER_ON_CAMPUS_OUTDOOR = "校内(户外)"

_KNOWN_WEEK_QUALIFIERS = (
    WEEK_QUALIFIER_OFF_CAMPUS,
    WEEK_QUALIFIER_ON_CAMPUS_OUTDOOR,
)

#: 「连续 + 已批准 qualifier」：`N-M周` + 白名单字面量，**整段锚定**。
#:
#: ⛔ 不用 `.*`、⛔ 不用 `startswith`、⛔ 不把 qualifier 无条件 strip：
#: qualifier 的合法性由白名单字面量（逐个 `re.escape`）保证；
#: qualifier **只做校验**，不改变 weeks 的数学含义。
_QUALIFIED_CONTINUOUS_WEEK_RANGE = re.compile(
    r"^([0-9]+)-([0-9]+)周("
    + "|".join(re.escape(qualifier) for qualifier in _KNOWN_WEEK_QUALIFIERS)
    + r")$"
)

#: **仅用于错误分类**（⛔ 不用于接受）：是否形如 `N-M周` + 额外内容，
#: 用来把"qualifier 未获批准"与"形状本身不认识"分开，且⛔ 不回显任何 token 内容。
_WEEK_WITH_SUFFIX_PREFIX = re.compile(r"^[0-9]+-[0-9]+周")

#: weeks 错误的**安全稳定分类**（⛔ 不回显 raw weeks token）。
WEEK_ERROR_UNSUPPORTED_TYPE = "unsupported_week_type"
WEEK_ERROR_UNSUPPORTED_SHAPE = "unsupported_week_shape"
WEEK_ERROR_UNSUPPORTED_RANGE = "unsupported_week_range"
WEEK_ERROR_UNSUPPORTED_QUALIFIER = "unsupported_week_qualifier"
WEEK_ERROR_UNSUPPORTED_PARITY_RANGE = "unsupported_week_parity_range"

_SUPPORTED_WEEK_TEXTS = (
    "`N-M周`（连续）/ `N-M单周`（奇数周）/ `N-M双周`（偶数周）/ "
    "`N-M周` + 已批准 qualifier（校外、校内(户外)）；均要求 N ≥ 1 且 M ≥ N"
)


def is_plain_week_range(text: object) -> bool:
    """`text` 是否是**普通连续周次** token（`N-M周`，`N >= 1`、`M >= N`）。

    只用于**结构判别**（例如 non-concrete segment 的 `<weeks token>` 是否为该形态），
    ⛔ 不扩大 `expand_weeks()` 本身接受的语法集合：
    `1-17单周` 这类**白名单单周**不在此函数返回 `True`，
    调用方仍应把真正的取值校验交给 `expand_weeks()`。
    """

    if not isinstance(text, str):
        return False

    match = _PLAIN_WEEK_RANGE.match(text.strip())
    if match is None:
        return False

    start, end = int(match.group(1)), int(match.group(2))
    return start >= 1 and end >= start


def expand_weeks(text: str) -> list[int]:
    """把**已确认语法**的周次文本展开成实际周次数组。

    已批准语法（Architecture Review 裁定；2026-1 east artifact 聚合证据：
    `N-M周校外` 54、`N-M双周` 15、`N-M单周` 13、`N-M周校内(户外)` 11）：

    ```text
    N-M周              → 连续全部周次          例如 1-5周   → [1,2,3,4,5]
    N-M单周            → 区间内**奇数周**      例如 1-17单周 → [1,3,…,17]
    N-M双周            → 区间内**偶数周**      例如 1-4双周  → [2,4]
    N-M周校外          → 与 `N-M周` **完全相同**（suffix 只做白名单校验）
    N-M周校内(户外)    → 与 `N-M周` **完全相同**（suffix 只做白名单校验）
    ```

    规则：

    - 一律要求 `N >= 1` 且 `M >= N`（**允许 `M == N`**）；
    - 单/双周在区间内按奇偶过滤；**过滤后为空 → fail closed**（⛔ 不生成空 weeks，
      例如 `3-3双周`）；
    - qualifier **不改变 weeks 的数学含义**，也⛔ **不写入公共 `Meeting`**
      （公共 Schema 没有 week qualifier 字段）；
    - **weeks qualifier 白名单本轮只有 `校外` / `校内(户外)`**：
      ⛔ `N-M周线上` 继续 fail closed（sections 的 `线上` ⛔ 不迁移到 weeks）；
    - ⛔ 其余一律拒绝：任意其它 suffix、`N-M周单周`、`N-M单双周`、`N,M周`、
      `第N-M周`、`N~M周`、全角数字、多段组合（`1-17周,3-4单周`）；
    - ⛔ **不用 `.*` / `startswith` / 无条件 strip qualifier**：qualifier 由
      白名单字面量整段锚定校验。

    错误只给**安全稳定分类**（`unsupported_week_type` / `unsupported_week_shape` /
    `unsupported_week_range` / `unsupported_week_qualifier` /
    `unsupported_week_parity_range`），⛔ **不回显 raw weeks token**。

    这是 Course Data **内部函数**，不是跨模块公共 API。
    """

    if not isinstance(text, str):
        raise CourseDataNormalizationError(
            f"周次必须是字符串（{WEEK_ERROR_UNSUPPORTED_TYPE}），"
            f"实际类型是 {type(text).__name__}（⛔ 不回显 raw weeks token）"
        )

    candidate = text.strip()
    if not candidate:
        raise CourseDataNormalizationError(
            f"周次文本为空（{WEEK_ERROR_UNSUPPORTED_SHAPE}）；"
            f"只接受 {_SUPPORTED_WEEK_TEXTS}（⛔ 不回显 raw weeks token）"
        )

    def _checked_range(match: re.Match[str]) -> tuple[int, int]:
        start, end = int(match.group(1)), int(match.group(2))
        if start < 1 or end < start:
            raise CourseDataNormalizationError(
                f"周次区间非法（{WEEK_ERROR_UNSUPPORTED_RANGE}）："
                f"要求 N ≥ 1 且 M ≥ N（⛔ 不回显 raw weeks token）"
            )
        return start, end

    # 1) 连续：N-M周
    plain_match = _PLAIN_WEEK_RANGE.match(candidate)
    if plain_match:
        start, end = _checked_range(plain_match)
        return list(range(start, end + 1))

    # 2) 连续 + 已批准 qualifier（qualifier 只做白名单校验，不改变含义）
    qualified_match = _QUALIFIED_CONTINUOUS_WEEK_RANGE.match(candidate)
    if qualified_match:
        start, end = _checked_range(qualified_match)
        return list(range(start, end + 1))

    # 3) 单周 / 双周（parity）
    for pattern, parity in ((_ODD_WEEK_RANGE, 1), (_EVEN_WEEK_RANGE, 0)):
        parity_match = pattern.match(candidate)
        if parity_match:
            start, end = _checked_range(parity_match)
            weeks = [week for week in range(start, end + 1) if week % 2 == parity]
            if not weeks:
                raise CourseDataNormalizationError(
                    f"单/双周过滤后为空（{WEEK_ERROR_UNSUPPORTED_PARITY_RANGE}）："
                    f"该区间内没有符合条件的周次，⛔ 不生成空 weeks"
                    f"（⛔ 不回显 raw weeks token）"
                )
            return weeks

    # 4) 未通过：只做**分类**，不回显 token / qualifier / 任何取值
    #    多段组合（含逗号）是**形状**问题，不是 qualifier 问题。
    if "," in candidate:
        raise CourseDataNormalizationError(
            f"周次形状未确认（{WEEK_ERROR_UNSUPPORTED_SHAPE}）：一个 weeks 字段只承载"
            f"**一段**周次，逗号组合（多段）未获批准（⛔ 不回显 raw weeks token）"
        )

    if _WEEK_WITH_SUFFIX_PREFIX.match(candidate) is not None:
        raise CourseDataNormalizationError(
            f"周次 qualifier 未获批准（{WEEK_ERROR_UNSUPPORTED_QUALIFIER}）："
            f"weeks 字段只接受 {'、'.join(_KNOWN_WEEK_QUALIFIERS)}；"
            f"⛔ sections 的 `线上` 不适用于 weeks（⛔ 不回显 raw weeks token）"
        )

    raise CourseDataNormalizationError(
        f"周次形状未确认（{WEEK_ERROR_UNSUPPORTED_SHAPE}）："
        f"只接受 {_SUPPORTED_WEEK_TEXTS}（⛔ 不回显 raw weeks token）"
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
            f"{key} 必须是非空字符串，实际类型是 {type(value).__name__}"
            f"（⛔ 不回显 raw 取值）"
        )
    return value


def _require_count(value: object, key: str) -> int:
    """容量 / 人数类字段：按已确认语义要求**整数**（`bool` 不算整数）。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise CourseDataNormalizationError(
            f"{key} 必须是整数，实际类型是 {type(value).__name__}（⛔ 不回显 raw 取值）"
        )
    if value < 0:
        raise CourseDataNormalizationError(f"{key} 不能为负（⛔ 不回显 raw 取值）")
    return value


def _parse_credit(value: object) -> float:
    r"""`score` 是**字符串数字**（已确认真实格式），转换成 `number`。

    ✅ 只接受**已经确认**的形状（Architecture Review 裁定；2026-1 east artifact
    已确认存在 98 个 `.N` 形式的 `score`）：

    ```text
    [0-9]+            例如 "3"   → 3.0
    [0-9]+\.[0-9]+    例如 "3.0" → 3.0 / "0.5" → 0.5
    \.[0-9]+          例如 ".5"  → 0.5 / ".0"  → 0.0
    ```

    ⛔ **不用宽松的 `float()` 替代语法校验**：`float()` 还会接受符号位、指数写法、
    `nan` / `inf` 等未确认形态，且规则不在本文件里显式可见。
    ⛔ 继续拒绝：符号位（`-.5` / `+.5`）、`3.`、`.`、`..5`、`1.2.3`、全角数字、
    带单位文本（`"3学分"`）、布尔 / 数值型 / 其它类型。
    ⛔ **数值型 `score`（`3` / `3.0`）仍无真实来源证据，继续拒绝**；
    若后续脱敏真实样本显示它也可能是 JSON number，再据实放宽。

    抛错时只给**安全稳定分类**（`unsupported_credit_type` / `unsupported_credit_format`），
    ⛔ **不回显 raw score**。
    """

    if not isinstance(value, str):
        raise CourseDataNormalizationError(
            f"score 必须是**字符串**形式的数字（{CREDIT_ERROR_UNSUPPORTED_TYPE}），"
            f"实际类型是 {type(value).__name__}（⛔ 不回显 raw score）；"
            f"数值型 score 尚无真实来源证据，本轮仍拒绝"
        )

    candidate = value.strip()
    if _CREDIT_PATTERN.match(candidate) is None:
        raise CourseDataNormalizationError(
            f"score 形状未确认（{CREDIT_ERROR_UNSUPPORTED_FORMAT}）：只接受 "
            f"`[0-9]+` / `[0-9]+.[0-9]+` / `.[0-9]+`（⛔ 不回显 raw score；"
            f"已确认真实格式为字符串数字）"
        )

    # 正则已排除符号位 / 全角 / 单位文本，因此这里可以安全地转成 float：
    # 结果必然 ≥ 0，且不会出现 `nan` / `inf`。
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
            f"teachingName 类型不符合已确认语义：{type(value).__name__}"
            f"（⛔ 不回显 raw 取值；教师姓名不入库）"
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
#: `remaining_capacity` 需要它（三分支规则见模块 docstring：
#: `<` 相减、`==` 取 0、`>` 取 `None`）。
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

#: 已确认的 `score` 形状（**语法校验**；Architecture Review 裁定，
#: 2026-1 east artifact 已确认存在 98 个 `.N` 形式）：
#:
#: ```text
#: [0-9]+            例如 "3"   → 3.0
#: [0-9]+\.[0-9]+    例如 "3.0" → 3.0 / "0.5" → 0.5
#: \.[0-9]+          例如 ".5"  → 0.5 / ".0"  → 0.0
#: ```
#:
#: ⛔ **不用宽松的 `float()` 代替语法校验**（会额外接受符号位 / 指数 / `nan` / `inf`）；
#: ⛔ 继续拒绝符号位、`3.`、`.`、`..5`、`1.2.3`、全角数字、带单位文本、数值型 / 布尔。
_CREDIT_PATTERN = re.compile(r"^(?:[0-9]+|[0-9]+\.[0-9]+|\.[0-9]+)$")

#: credit 错误的**安全稳定分类**（⛔ 不回显 raw score）。
CREDIT_ERROR_UNSUPPORTED_TYPE = "unsupported_credit_type"
CREDIT_ERROR_UNSUPPORTED_FORMAT = "unsupported_credit_format"


def _build_common_offering_fields(raw: Mapping[str, object], *, source: str) -> dict[str, object]:
    """**共用**的公共字段构造（不含 `meetings`）。

    ⛔ 这里**只有一份**字段映射：正常 Meeting 路径与 missing-schedule 路径**共用它**，
    避免两处复制 `courseNum` / `courseName` / `classNumber` / `yearTerm` / `score` /
    `limitNumber` / `selectedNumber` 的转换逻辑。

    `remaining_capacity` 是**派生值**，按三分支规则（Architecture Review 裁定，
    真实 2026-1 east artifact 已证明来源里存在 `selectedNumber > limitNumber`）：

    ```text
    selected <  capacity → capacity - selected（正常差值）
    selected == capacity → 0
    selected >  capacity → None（unknown）
    ```

    - ⛔ **不 clamp 到 0**、⛔ **不改写 `capacity`**（保持来源 `limitNumber` 原值）、
      ⛔ **不新增 `selected_count`**、⛔ **不修改公共 Schema**、⛔ **不猜学校为何超额**；
    - `None` = "该派生值不可用"，⛔ 不表示"已满"，⛔ 也不表示"无剩余"；
    - ⛔ `selected > capacity` **不再**拒绝整条教学班（此前会 fail closed）。

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

    # ⚠️ 派生值：学校接口没有直接提供剩余容量。
    remaining_capacity: int | None

    if selected < capacity:
        remaining_capacity = capacity - selected
    elif selected == capacity:
        remaining_capacity = 0
    else:
        # selected > capacity：减法无法可靠生成**非负**的剩余容量，
        # 因此降级为 unknown（None），⛔ 不 clamp 到 0、⛔ 不拒绝整条教学班。
        remaining_capacity = None

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


def build_course_offering_from_non_concrete_schedule(
    raw: Mapping[str, object],
    *,
    source: str,
) -> CourseOffering:
    """**窄语义**路径：当 `teachingTimePlaceStr` **存在且已被解析**，
    但其中**没有任何 concrete segment**（即全部是 non-concrete）时，
    构造 `meetings = []` 的 `CourseOffering`。

    语义（与 DG-07B 一致，且**不混用**）：

    - `meetings = []` 表示「**有课程安排信息，但不足以确定时间冲突**」——
      由现有 **DG-07** 语义承接为 **schedule UNKNOWN**；
    - ⛔ 本函数**不解析**任何文本、**不吞**任何异常；调用方必须已经成功
      `parse_teaching_time_place()` 并确认 `extract_meetings()` 为空；
    - ⛔ 与 `build_course_offering_from_missing_schedule_field()` **不是同一条路径**：
      后者要求 `teachingTimePlaceStr` **属性不存在**，本函数要求"属性存在且已解析"。
      两者都不接受"字段存在但解析失败"。

    ⚠️ 这是 Course Data **内部函数**：不进 `docs/interfaces/`、不进 Provider / API、
    不是新的公共 Schema。
    """

    if not isinstance(raw, Mapping):
        raise CourseDataNormalizationError(
            f"raw 必须是字段映射，实际是 {type(raw).__name__}"
        )

    return CourseOffering(
        **_build_common_offering_fields(raw, source=source),  # type: ignore[arg-type]
        meetings=[],
    )
