"""`teachingTimePlaceStr` → `ParsedScheduleSegment[]`（Course Data 内部 parser）。

依据：负责人提供的**私密脱敏样本**（Sanitized Sample，**不入 Git**，
`source_id = OFFERING-001`，2026-1）与 **2026-1 全量采集首轮的真实报错证据**。
本模块只实现证据**已经证明**的结构。

## 已确认结构

```text
segment separator = ","
field separator   = "/"

4 字段（无地点、无教师）：weeks / weekday / sections / activity
5 字段 A（有地点、无教师）：weeks / weekday / sections / location / activity
5 字段 B（无地点、有教师）：weeks / weekday / sections / teacher / activity
6 字段（有地点、有教师）：weeks / weekday / sections / location / teacher / activity
```

⚠️ **teacher 并不总是在 segment 中出现**（2026-1 真实证据已确认）：
真实记录既可以没有 location，也可以没有 teacher。因此
⛔ **不得再把第 4 / 5 字段无条件当成 teacher** —— 那会把 location 静默错读成 teacher，
并导致 `Meeting.campus / classroom` 变成 `None`（**静默错误解释**）。

### 5 字段的判别规则（**严格三态**，唯一允许的判别方式）

只看 `fields[3]`：

```text
无 "-"                → teacher    → 5 字段 B（无地点、有教师）
>= 3 个非空 "-" 分段   → location   → 5 字段 A（有地点、无教师）
其余二义形态           → 一律 fail closed（⛔ 不猜）
```

⛔ 不根据 `courseName` / 学院 / `teachingName` 等字段猜；⛔ 不引入模糊匹配。

⚠️ **为什么不复用 `_is_location_token()`**：后者只要"非空园区 + `-` + 非空教室"成立，
会把 `A-B` 这种**只有两段**的 token 判成 location —— 而它同样可能是一个**含 `-` 的 teacher**。
5 字段本身二义，必须用更严格的门槛，否则会重现"teacher / location 互相静默错读"。

⚠️ **本轮未收紧 6 字段**：6 字段的语义**已由字段数确定**，因此仍用通用
`_parse_location()`；由此产生的 5 / 6 字段不对称性已记录为**已知风险**。

- **最多一个末尾逗号**：`seg,` → 忽略末尾空 segment；
  ⛔ `seg,,` / `seg,,,`（多个末尾逗号）**失败**；
- **中间**空 segment **不得静默忽略**：`segment1,,segment2` → `CourseDataNormalizationError`；
- **字段数只接受 4 / 5 / 6**，其它（3、7+）一律 fail closed。

## 为什么需要内部 `ParsedScheduleSegment`

真实 segment **可能携带 teacher**，但**当前公共 `Meeting` 没有 `teacher`**
（Data Gate 已登记为 **known deferred representation gap**）。

因此 parser **在内部保留** teacher / activity 这两个真实语义，
再通过 `extract_meetings()` 只把 `Meeting[]` 交给公共契约 ——
⛔ **不为了 teacher 修改 `Meeting` Schema**。

## 本模块不做的事

- ⛔ **不读 Raw `weekDay`**：`weekday` 一律来自 segment 自身（`parse_weekday`）。
  样本已显示 Raw `weekDay` 的排列顺序**不能安全假设**与 segment 顺序一致，
  更不得与 segment 按位置 zip；
- ⛔ **不用 `openingSchoolName` 当 `campus`**：地点只来自 segment 中**实际存在的** location 字段；
- ⛔ **不自动补 teacher / location**：缺失就是缺失，保持 `None`；
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

#: 无地点、**无教师** segment 的字段数（2026-1 真实证据确认）。
FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER = 4

#: 5 字段 segment 的字段数：**有地点无教师** 或 **无地点有教师**，需按 location grammar 判别。
FIELDS_FIVE = 5

#: 有地点、有教师 segment 的字段数（已确认）。
FIELDS_WITH_LOCATION_AND_TEACHER = 6

#: 允许的字段数集合（其它一律 fail closed）。
_ALLOWED_FIELD_COUNTS = (
    FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER,
    FIELDS_FIVE,
    FIELDS_WITH_LOCATION_AND_TEACHER,
)

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

    ⚠️ `teacher` 可以为 `None`：2026-1 真实证据已证明 **segment 中 teacher 可以不存在**。
    ⛔ 不得为了让类型好看而自动补一个占位 teacher。

    ⚠️ 这不是 Schema、不是 DTO、不是 Integration 公共接口。
    """

    meeting: Meeting
    teacher: str | None
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


def _is_location_token(token: object) -> bool:
    """`token` 是否满足 **location grammar**。

    与 `_parse_location()` **完全同一套规则**（非空园区 + 至少一个 `-` + 非空教室），
    只是以**布尔**形式表达。

    ⚠️ 这是**通用**判定，用于 6 字段等**已经由字段数确定语义**的位置。
    ⛔ 5 字段的**二义判别**不使用本函数 —— 它用更严格的 `_classify_five_field_token()`
    （要求 `>= 3` 个非空 `-` 分段），以免把 `A-B` 形态的 teacher 误判成 location。

    ⛔ 纯结构判别：不比对课程名 / 学院 / 教师名，不做模糊匹配。

    ⚠️ 本函数**不抛异常** —— 判别失败是正常分支，不是错误。
    """

    if not isinstance(token, str):
        return False

    campus, separator, classroom = token.partition("-")
    if not separator:
        return False

    return bool(campus.strip()) and bool(classroom.strip())


#: 5 字段 `fields[3]` 的三种判别结果。
#: - `teacher` —— 明确是 teacher（无 `-`）
#: - `location` —— 明确是 location（`>= 3` 个非空 `-` 分段）
#: - `ambiguous` —— **二义形态**，一律 fail closed
_FIVE_FIELD_TEACHER = "teacher"
_FIVE_FIELD_LOCATION = "location"
_FIVE_FIELD_AMBIGUOUS = "ambiguous"

#: 明确判定为 location 所需的**最少非空 `-` 分段数**。
_MIN_LOCATION_SEGMENTS = 3


def _count_non_empty_dash_segments(token: str) -> int:
    """统计按 `-` 切分后**非空**（去空白后）的分段数量。"""

    return sum(1 for part in token.split("-") if part.strip() != "")


def _classify_five_field_token(token: object) -> str:
    """判别 5 字段 `fields[3]` 的语义（**严格三态**）。

    判定规则（本轮收紧后）：

    ```text
    无 "-"                 → teacher    （明确是 teacher）
    >= 3 个非空 "-" 分段    → location   （明确是 location）
    其余二义形态            → ambiguous  → 调用方 fail closed
    ```

    ⚠️ **为什么不复用 `_is_location_token()`**：
    后者只要"非空园区 + `-` + 非空教室"就成立，会把 `A-B` 这种
    **只有两段**的 token 判成 location —— 而那同样可能是一个**含 `-` 的 teacher**。
    对 5 字段这种**本身二义**的位置，必须用更严格的门槛，
    否则会重现"把 teacher 当成 location（或反之）"的静默错读。

    ⛔ 无法明确归入上面两类时**不猜**：返回 `ambiguous`，由调用方整体失败。
    """

    if not isinstance(token, str):
        return _FIVE_FIELD_AMBIGUOUS

    if "-" not in token:
        return _FIVE_FIELD_TEACHER

    if _count_non_empty_dash_segments(token) >= _MIN_LOCATION_SEGMENTS:
        return _FIVE_FIELD_LOCATION

    return _FIVE_FIELD_AMBIGUOUS


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
    - **最多一个**末尾逗号：`seg,` 可以，`seg,,` / `seg,,,` 抛错；
    - 中间 / 开头的空 segment 抛错；
    - 字段数只接受 4（无地点无教师）/ 5（按 location grammar 判别）/
      6（有地点有教师）。
    """

    if not isinstance(text, str):
        raise CourseDataNormalizationError(
            f"teachingTimePlaceStr 必须是字符串，实际是 {type(text).__name__}"
        )

    candidate = text.strip()
    if not candidate:
        raise CourseDataNormalizationError("teachingTimePlaceStr 为空字符串")

    raw_segments = candidate.split(SEGMENT_SEPARATOR)

    # 真实证据只确认**最多一个**末尾逗号：因此只允许**恰好一个**末尾空 segment。
    # ⛔ 不能用 while 静默吞掉多个末尾空 segment（那会超出证据）。
    trailing_empty_count = 0
    for item in reversed(raw_segments):
        if item.strip():
            break
        trailing_empty_count += 1

    if trailing_empty_count > 1:
        raise CourseDataNormalizationError(
            f"teachingTimePlaceStr 出现了 {trailing_empty_count} 个连续的末尾分隔符；"
            f"真实证据只确认**最多一个**末尾逗号，因此只允许恰好一个末尾空 segment"
        )

    if trailing_empty_count == 1:
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
                f"只有**单个**末尾逗号产生的末尾空段可以忽略，"
                f"中间 / 开头空段与多个末尾逗号一律拒绝"
            )

        fields = raw_segment.split(FIELD_SEPARATOR)
        field_count = len(fields)

        if field_count not in _ALLOWED_FIELD_COUNTS:
            raise CourseDataNormalizationError(
                f"teachingTimePlaceStr 的第 {offset} 段字段数为 {field_count}，只接受 "
                f"{FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER}（无地点无教师）/ "
                f"{FIELDS_FIVE}（有地点无教师 或 无地点有教师）/ "
                f"{FIELDS_WITH_LOCATION_AND_TEACHER}（有地点有教师）"
            )

        weeks = expand_weeks(fields[0])
        weekday = parse_weekday(fields[1])
        start_section, end_section = parse_sections(fields[2])

        campus: str | None
        classroom: str | None
        teacher: str | None

        if field_count == FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER:
            # 4 字段：weeks / weekday / sections / activity
            campus, classroom, teacher = None, None, None
            activity = _require_non_empty_token(
                fields[3], field="activity", segment_index=offset
            )
        elif field_count == FIELDS_FIVE:
            # 5 字段**二义**：必须严格判别，⛔ 不得默认按 teacher 也不得默认按 location。
            classification = _classify_five_field_token(fields[3])

            if classification == _FIVE_FIELD_AMBIGUOUS:
                raise CourseDataNormalizationError(
                    f"teachingTimePlaceStr 的第 {offset} 段是 5 字段，"
                    f"但其第 4 个字段既不能明确判定为 location"
                    f"（需 >= {_MIN_LOCATION_SEGMENTS} 个非空 '-' 分段），"
                    f"也不能明确判定为 teacher（需完全不含 '-'）。"
                    f"本 parser 不猜语义，已整体停止（不回显该字段取值）"
                )

            if classification == _FIVE_FIELD_LOCATION:
                # 5 字段 A：weeks / weekday / sections / location / activity
                campus, classroom = _parse_location(fields[3], offset)
                teacher = None
            else:
                # 5 字段 B：weeks / weekday / sections / teacher / activity
                campus, classroom = None, None
                teacher = _require_non_empty_token(
                    fields[3], field="teacher", segment_index=offset
                )

            activity = _require_non_empty_token(
                fields[4], field="activity", segment_index=offset
            )
        else:
            # 6 字段：weeks / weekday / sections / location / teacher / activity
            # ⚠️ 6 字段的语义**已由字段数确定**，因此仍用通用 location grammar
            # （本轮**未**收紧 6 字段；该不对称性已记录为已知风险）。
            campus, classroom = _parse_location(fields[3], offset)
            teacher = _require_non_empty_token(
                fields[4], field="teacher", segment_index=offset
            )
            activity = _require_non_empty_token(
                fields[5], field="activity", segment_index=offset
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
