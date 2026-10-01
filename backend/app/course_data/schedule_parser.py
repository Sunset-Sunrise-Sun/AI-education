"""`teachingTimePlaceStr` → `ParsedScheduleSegment[]`（Course Data 内部 parser）。

依据：负责人提供的**私密脱敏样本**（Sanitized Sample，**不入 Git**，
`source_id = OFFERING-001`，2026-1）。本模块只实现样本**已经证明**的结构。

## 已确认结构

```text
segment separator = ","
field separator   = "/"

无地点（5 字段）：weeks / weekday / sections / teacher / activity
有地点（6 字段）：weeks / weekday / sections / location / teacher / activity
```

- **末尾逗号**存在：`segment1,segment2,` → 末尾产生的空 segment **忽略**；
- **中间**空 segment **不得静默忽略**：`segment1,,segment2` → `CourseDataNormalizationError`；
- **字段数只接受 5 或 6**，其它一律 fail closed。

## 为什么需要内部 `ParsedScheduleSegment`

真实 segment **确实携带 teacher**，但**当前公共 `Meeting` 没有 `teacher`**
（Data Gate 已登记为 **known deferred representation gap**）。

因此 parser **在内部保留** teacher / activity 这两个真实语义，
再通过 `extract_meetings()` 只把 `Meeting[]` 交给公共契约 ——
⛔ **不为了 teacher 修改 `Meeting` Schema**。

## 本模块不做的事

- ⛔ **不读 Raw `weekDay`**：`weekday` 一律来自 segment 自身（`parse_weekday`）。
  样本已显示 Raw `weekDay` 的排列顺序**不能安全假设**与 segment 顺序一致，
  更不得与 segment 按位置 zip；
- ⛔ **不用 `openingSchoolName` 当 `campus`**：地点只来自 segment 中**实际存在的** location 字段；
- ⛔ 不排序、不去重、不丢弃任何一段：输出顺序 == Raw segment 顺序。

## 隐私

parser 的错误信息**不回显** location / teacher / activity 的取值
（只回显 weeks / weekday / sections 这类非个人数据的最小 token 与段序号），
避免真实地点、教师姓名顺带进入日志。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.normalization import expand_weeks
from app.models.contracts import Meeting

__all__ = [
    "ParsedScheduleSegment",
    "extract_meetings",
    "parse_sections",
    "parse_teaching_time_place",
    "parse_weekday",
]

#: 段分隔符（已确认）。
SEGMENT_SEPARATOR = ","

#: 字段分隔符（已确认）。
FIELD_SEPARATOR = "/"

#: 无地点 segment 的字段数（已确认）。
FIELDS_WITHOUT_LOCATION = 5

#: 有地点 segment 的字段数（已确认）。
FIELDS_WITH_LOCATION = 6

#: 星期 token → 公共 `weekday`（1=周一 … 7=周日）。
#: ⛔ 只接受这些标准 token；`星期天` / `周一` / `Monday` 等**未确认**写法一律拒绝。
_WEEKDAY_BY_TOKEN: dict[str, int] = {
    "星期一": 1,
    "星期二": 2,
    "星期三": 3,
    "星期四": 4,
    "星期五": 5,
    "星期六": 6,
    "星期日": 7,
}

#: 节次 `第N-M节`（`N >= 1`，`M >= N`；**允许 `M == N`**，样本中 `第4-4节` 真实存在）。
_SECTION_PATTERN = re.compile(r"^第([0-9]+)-([0-9]+)节$")


@dataclass(frozen=True)
class ParsedScheduleSegment:
    """一段已解析的上课安排（Course Data **内部对象**）。

    - `meeting` —— 可交给公共契约的部分；
    - `teacher` / `activity` —— 真实存在、但**当前公共契约不承载**的内部保真信息。

    ⚠️ 这不是 Schema、不是 DTO、不是 Integration 公共接口。
    """

    meeting: Meeting
    teacher: str
    activity: str


def parse_weekday(token: str) -> int:
    """把 segment 自带的星期 token 转成公共 `weekday`（1=周一 … 7=周日）。

    ⛔ 只接受 `星期一` … `星期日`；其它写法（`星期天` / `周一` / `Monday` / 空）一律拒绝。
    """

    if not isinstance(token, str):
        raise CourseDataNormalizationError(
            f"星期必须是字符串，实际是 {type(token).__name__}"
        )

    candidate = token.strip()
    weekday = _WEEKDAY_BY_TOKEN.get(candidate)
    if weekday is None:
        raise CourseDataNormalizationError(
            f"无法识别的星期 token：{token!r}；只接受 星期一 / 星期二 / … / 星期日"
        )

    return weekday


def parse_sections(token: str) -> tuple[int, int]:
    """解析 `第N-M节`，返回 `(start_section, end_section)`。

    要求 `N >= 1` 且 `M >= N` —— **允许 `M == N`**（样本中 `第4-4节` 真实存在）。
    ⛔ 不得写成 `end > start`。
    """

    if not isinstance(token, str):
        raise CourseDataNormalizationError(
            f"节次必须是字符串，实际是 {type(token).__name__}"
        )

    candidate = token.strip()
    match = _SECTION_PATTERN.match(candidate)
    if match is None:
        raise CourseDataNormalizationError(
            f"无法识别的节次格式：{token!r}；只接受 `第N-M节`（N ≥ 1、M ≥ N）"
        )

    start, end = (int(group) for group in match.groups())
    if start < 1:
        raise CourseDataNormalizationError(f"节次起点必须 ≥1：{token!r}（start={start}）")
    if end < start:
        raise CourseDataNormalizationError(
            f"节次区间非法（结束早于开始）：{token!r}（start={start}, end={end}）"
        )

    return start, end


def _parse_location(token: str, segment_index: int) -> tuple[str, str]:
    """解析 `校区-教学楼-教室`。

    只按**第一个 `-`** 切：

    ```text
    示例校区-示例教学楼-2108
      → campus    = "示例校区"
      → classroom = "示例教学楼-2108"
    ```

    ⛔ **不进一步猜** building / room —— 公共 Schema 目前没有这些字段。

    ⚠️ 错误信息**不回显** location 原文（可能含真实校区 / 教室信息）。
    """

    if not isinstance(token, str):
        raise CourseDataNormalizationError(
            f"第 {segment_index} 段的地点字段必须是字符串，实际是 {type(token).__name__}"
        )

    campus, separator, classroom = token.partition("-")
    if not separator:
        raise CourseDataNormalizationError(
            f"第 {segment_index} 段的地点字段不符合「校区-教学楼-教室」结构（缺少 '-'）"
        )

    campus = campus.strip()
    classroom = classroom.strip()

    if not campus:
        raise CourseDataNormalizationError(f"第 {segment_index} 段的地点字段「校区」部分为空")
    if not classroom:
        raise CourseDataNormalizationError(f"第 {segment_index} 段的地点字段「教室」部分为空")

    return campus, classroom


def _require_non_empty_token(value: object, *, field: str, segment_index: int) -> str:
    """teacher / activity 必须是非空字符串。

    ⚠️ 错误信息**不回显**取值。
    """

    if not isinstance(value, str):
        raise CourseDataNormalizationError(
            f"第 {segment_index} 段的 {field} 必须是字符串，实际是 {type(value).__name__}"
        )
    if not value.strip():
        raise CourseDataNormalizationError(f"第 {segment_index} 段的 {field} 不能为空")
    return value


def parse_teaching_time_place(text: str) -> list[ParsedScheduleSegment]:
    """解析整条 `teachingTimePlaceStr`，按 Raw 顺序返回**全部** segment。

    - 输出顺序 == Raw 顺序（**不排序**）；**不丢段**、**不合并**；
    - 末尾逗号产生的空 segment 忽略；中间空 segment 抛错；
    - 字段数只接受 5（无地点）或 6（有地点）。
    """

    if not isinstance(text, str):
        raise CourseDataNormalizationError(
            f"teachingTimePlaceStr 必须是字符串，实际是 {type(text).__name__}"
        )

    candidate = text.strip()
    if not candidate:
        raise CourseDataNormalizationError("teachingTimePlaceStr 为空字符串")

    raw_segments = candidate.split(SEGMENT_SEPARATOR)

    # 只忽略**末尾**的空 segment（真实存在末尾逗号）。
    while raw_segments and not raw_segments[-1].strip():
        raw_segments.pop()

    if not raw_segments:
        raise CourseDataNormalizationError(
            "teachingTimePlaceStr 不含任何有效 segment（只有分隔符或空白）"
        )

    parsed: list[ParsedScheduleSegment] = []

    for offset, raw_segment in enumerate(raw_segments, start=1):
        if not raw_segment.strip():
            raise CourseDataNormalizationError(
                f"teachingTimePlaceStr 的第 {offset} 段为空 segment；"
                f"只有**末尾**逗号产生的空段可以忽略，中间空段一律拒绝"
            )

        fields = raw_segment.split(FIELD_SEPARATOR)
        field_count = len(fields)

        if field_count not in (FIELDS_WITHOUT_LOCATION, FIELDS_WITH_LOCATION):
            raise CourseDataNormalizationError(
                f"teachingTimePlaceStr 的第 {offset} 段字段数为 {field_count}，"
                f"只接受 {FIELDS_WITHOUT_LOCATION}（无地点）或 "
                f"{FIELDS_WITH_LOCATION}（有地点）"
            )

        weeks = expand_weeks(fields[0])
        weekday = parse_weekday(fields[1])
        start_section, end_section = parse_sections(fields[2])

        if field_count == FIELDS_WITH_LOCATION:
            campus, classroom = _parse_location(fields[3], offset)
            teacher = _require_non_empty_token(
                fields[4], field="teacher", segment_index=offset
            )
            activity = _require_non_empty_token(
                fields[5], field="activity", segment_index=offset
            )
        else:
            campus, classroom = None, None
            teacher = _require_non_empty_token(
                fields[3], field="teacher", segment_index=offset
            )
            activity = _require_non_empty_token(
                fields[4], field="activity", segment_index=offset
            )

        parsed.append(
            ParsedScheduleSegment(
                meeting=Meeting(
                    weekday=weekday,
                    start_section=start_section,
                    end_section=end_section,
                    weeks=weeks,
                    campus=campus,
                    classroom=classroom,
                ),
                teacher=teacher,
                activity=activity,
            )
        )

    return parsed


def extract_meetings(segments: Sequence[ParsedScheduleSegment]) -> list[Meeting]:
    """把解析结果投影成公共 `Meeting[]`（原顺序、原段数）。

    ⚠️ 这里**只做投影**：丢弃当前公共契约不承载的 `teacher` / `activity`，
    不做任何筛选、合并、排序，也**不修改** `Meeting` Schema。
    """

    return [segment.meeting for segment in segments]
