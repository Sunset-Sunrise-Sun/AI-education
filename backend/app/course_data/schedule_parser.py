"""`teachingTimePlaceStr` → `ParsedScheduleSegment[]`（Course Data 内部 parser）。

依据：负责人提供的**私密脱敏样本**（Sanitized Sample，**不入 Git**，
`source_id = OFFERING-001`，2026-1）与 **2026-1 全量采集首轮的真实报错证据**。
本模块只实现证据**已经证明**的结构。

## 已确认结构

```text
segment separator = ","
field separator   = "/"

2 字段（non-concrete：无 weekday / sections / 具体地点 / teacher）：
        <weeks token> / activity                        例如 1-17周 / 实验实践环节
        <weeks token><qualifier> / activity             例如 12-19周校外 / 实验实践环节
3 字段（non-concrete：无 weekday / sections / 具体地点）：
        <weeks token> / teacher / activity              例如 1-17周 / 龙霞 / 实验实践环节
        <weeks token><qualifier> / teacher / activity   例如 16-16周校内(户外) / 龙霞 / 实验实践环节
4 字段（无地点、无教师）：weeks / weekday / sections / activity
5 字段 A（有地点、无教师）：weeks / weekday / sections / location / activity
5 字段 B（无地点、有教师）：weeks / weekday / sections / teacher / activity
6 字段（有地点、有教师）：weeks / weekday / sections / location / teacher / activity
```

### non-concrete segment（2026-1 真实证据确认）

真实见习类课程的 `teachingTimePlaceStr` 形如 `12-19周校外/实验实践环节`：
**没有** weekday / sections / 具体地点 / teacher，因此：

- ⛔ **不制造** `Meeting`（`meeting = None`）——
  ⛔ 不得把 `weekday=None` / `sections=None` 塞进公共 `Meeting`；⛔ 不猜星期 / 节次；
- ⛔ **不把 qualifier 伪装成 `campus`**：`"校外"` 不是具体校区
  （与 `openingSchoolName → campus` 是两回事），因此单独存入
  `ParsedScheduleSegment.schedule_qualifier`；
- ⚠️ **不能整串**把 `12-19周校外` 交给 `expand_weeks()` —— 它只认识 `<weeks token>`。
  必须先拆成 `weeks_token = "12-19周"`（→ `expand_weeks`）与 `qualifier = "校外"`；
- ⛔ qualifier 是**白名单**（目前只有 `校外`）：`12-19周XXX` 一律拒绝；
  后续按新真实证据逐个加入，⛔ 不预先泛化；
- `extract_meetings()` **不投影**它，但 `ParsedScheduleSegment` **仍保留**
  （⛔ 不是静默丢弃）。若某 `CourseOffering` 因此 `meetings == []`，
  按现有 **DG-07** 即为 **schedule UNKNOWN**。

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
- **字段数只接受 2 / 3 / 4 / 5 / 6**，其它（7+）一律 fail closed。

### 2 字段 non-concrete（**无 teacher**，2026-1 真实证据）

两种已确认形态，**都没有** teacher 字段：

```text
plain     ：<weeks token> / activity              例如 1-17周 / 实验实践环节
qualified ：<weeks token><已确认 qualifier> / activity  例如 12-19周校外 / 实验实践环节
```

⛔ **不得把 row 级 `teachingName` 注入 `segment.teacher`**：
`teachingName` 是 **row 级**信息，与"该 segment 内是否有 teacher"没有对应关系；
注入等于凭空造事实。因此这两种形态的 `teacher` **一律为 `None`**。

- `meeting = None`；`schedule_weeks` 保存展开后的周次；
  plain 的 `schedule_qualifier = None`，qualified 的为对应白名单取值；
- ⛔ 2 字段只接受上面两种形态；其它 suffix（`1-17周未知词`）→ fail closed。

### 3 字段 non-concrete（带 teacher，2026-1 真实证据）

真实证据：`1-17周/龙霞/实验实践环节` 与 **`16-16周校内(户外)/龙霞/实验实践环节`**，
同行 `row.teachingName` 均为同一教师姓名。
⇒ 该 3 字段是 **`weeks[qualifier] / teacher / activity`**：
⛔ **不是** location，⛔ **不是**未知 qualifier。

- **两种已确认形态**：plain（`1-17周`，`schedule_qualifier = None`）与
  qualified（`16-16周校内(户外)`，`schedule_qualifier = "校内(户外)"`）；
- ⚠️ **必须先拆开**：`16-16周校内(户外)` → `weeks_token = "16-16周"` +
  `qualifier = "校内(户外)"`，⛔ **只把 `weeks_token` 交给 `expand_weeks()`**；
- `meeting = None`（没有 weekday / sections）；⛔ 不生成 `Meeting`；
- `teacher` 保留在内部字段（脱敏由 collector 负责）；
- `schedule_weeks` 保存展开后的周次；
- ⛔ `weeks` 必须是合法 `N-M周`；⛔ teacher / activity 必须非空；
- ⛔ **qualifier 是白名单**（当前：`校外`、`校内(户外)`）：
  `16-16周未知文本` / `16-16周线上` / `16-16周医院` 一律拒绝；
- ⛔ **不放开为"任意 3 字段 / 任意 suffix"**。


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
from app.course_data.normalization import expand_weeks, is_plain_week_range
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

#: **无地点、无教师** segment 的字段数（2026-1 真实证据确认）。
FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER = 4

#: 5 字段 segment 的字段数：**有地点无教师** 或 **无地点有教师**，需按 location grammar 判别。
FIELDS_FIVE = 5

#: 有地点、有教师 segment 的字段数（已确认）。
FIELDS_WITH_LOCATION_AND_TEACHER = 6

#: **non-concrete** segment 的字段数（2026-1 真实证据确认）：
#: `<weeks token> + <qualifier>` / `<activity>`，**没有** weekday / sections / 具体地点 / teacher。
FIELDS_NON_CONCRETE = 2

#: **non-concrete、带 teacher** segment 的字段数（2026-1 真实证据确认）：
#: `<weeks token>` / `<teacher>` / `<activity>`，**没有** weekday / sections / 具体地点。
#:
#: 真实证据：`1-17周/龙霞/实验实践环节`，同行 `row.teachingName` 亦为同一教师姓名。
#: ⇒ 该 3 字段是 **teacher**，⛔ **不是** location，⛔ 也不是未知 qualifier。
FIELDS_NON_CONCRETE_WITH_TEACHER = 3

#: 允许的字段数集合（其它一律 fail closed）。
_ALLOWED_FIELD_COUNTS = (
    FIELDS_NON_CONCRETE,
    FIELDS_NON_CONCRETE_WITH_TEACHER,
    FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER,
    FIELDS_FIVE,
    FIELDS_WITH_LOCATION_AND_TEACHER,
)

#: 目前**唯一**经真实证据确认的 schedule qualifier（校外见习类）。
#:
#: ⛔ **白名单而非通配**：`12-19周XXX` 一律拒绝。
#: 后续若真实数据再出现（例如 `12-19周线上` / `12-19周医院` / `12-19周实践基地`），
#: **按新证据**逐个加入，⛔ 不预先泛化。
SCHEDULE_QUALIFIER_OFF_CAMPUS = "校外"

#: 真实证据（2026-1）：`16-16周校内(户外)/<教师>/实验实践环节`。
#: ⛔ 这是**另一个已确认 qualifier**，且**不是**具体校区 → 同样不得当作 `campus`。
SCHEDULE_QUALIFIER_ON_CAMPUS_OUTDOOR = "校内(户外)"

#: 已确认的 schedule qualifier 集合（**白名单**）。
_KNOWN_SCHEDULE_QUALIFIERS = (
    SCHEDULE_QUALIFIER_OFF_CAMPUS,
    SCHEDULE_QUALIFIER_ON_CAMPUS_OUTDOOR,
)

# ---------------------------------------------------------------------------
# sections 字段的 suffix 白名单（Architecture Review 裁定，2026-1 真实 east artifact）
# ---------------------------------------------------------------------------
#
# 真实证据：east campus artifact 的 sections 位置上出现 `第N-M节<suffix>`，
# 其中 suffix 的聚合计数为 `校内(户外)` × 173、`线上` × 11、`校外` × 1。
#
# ⚠️ 这是**独立于** `_KNOWN_SCHEDULE_QUALIFIERS` 的**第二张**白名单：
#    weeks 字段的限定词白名单当前仍只有 `校外` / `校内(户外)`，
#    ⛔ **不因本裁定而被放宽**（`线上` 只被批准出现在 **sections** 字段上）。
SCHEDULE_SECTIONS_SUFFIX_ON_CAMPUS_OUTDOOR = "校内(户外)"
SCHEDULE_SECTIONS_SUFFIX_OFF_CAMPUS = "校外"
SCHEDULE_SECTIONS_SUFFIX_ONLINE = "线上"

#: sections suffix 白名单（**已批准**的完整取值，⛔ 不含任何前缀/通配）。
_KNOWN_SECTIONS_SUFFIXES = (
    SCHEDULE_SECTIONS_SUFFIX_ON_CAMPUS_OUTDOOR,
    SCHEDULE_SECTIONS_SUFFIX_OFF_CAMPUS,
    SCHEDULE_SECTIONS_SUFFIX_ONLINE,
)

#: production 错误的**安全分类**：⛔ 不回显原始 token，只给出类别。
SECTIONS_ERROR_UNSUPPORTED_SUFFIX = "unsupported_sections_suffix"
SECTIONS_ERROR_UNSUPPORTED_SHAPE = "unsupported_sections_shape"
SECTIONS_ERROR_UNSUPPORTED_RANGE = "unsupported_sections_range"

#: 普通周次 token：`N-M周`（`N >= 1`、`M >= N`）。
_PLAIN_WEEKS_GRAMMAR = r"[0-9]+-[0-9]+周"

#: schedule qualifier 的形状：**非空任意文本**（具体取值由白名单把关）。
#:
#: ⚠️ 这里刻意**不把 qualifier 枚举进正则**：regex 只负责"拆出 weeks 与 qualifier"，
#: "这个 qualifier 是否已被真实证据确认"由白名单判断。
#: 这样新增一个已确认 qualifier 只需改常量，不必改文法。
_QUALIFIER_GRAMMAR = r".+"

#: 带 qualifier 的周次字段形状（qualifier 可省略，但若存在则不能为空）。
_WEEKS_WITH_OPTIONAL_QUALIFIER = re.compile(
    r"^(" + _PLAIN_WEEKS_GRAMMAR + r")(" + _QUALIFIER_GRAMMAR + r")?$"
)

#: 已确认 qualifier 的**整段**匹配（用于 2 字段场景）。
_QUALIFIED_WEEKS_ONLY = re.compile(
    r"^(" + _PLAIN_WEEKS_GRAMMAR + r")("
    + "|".join(re.escape(q) for q in _KNOWN_SCHEDULE_QUALIFIERS)
    + r")$"
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

#: 节次：`第N-M节` + **精确命中白名单**的可选 suffix
#: （`N >= 1`、`M >= N`；**允许 `M == N`**，样本中 `第4-4节` 真实存在）。
#:
#: ⛔ 实现约束（Architecture Review 裁定）：
#: - ⛔ **不用 `startswith`**；
#: - ⛔ **不用 `.*`**（也不抓取 suffix 再做字符串比较）；
#: - ⛔ **不把 `节` 之后的字符无条件 strip**；
#: - suffix 的合法性由**白名单字面量**（逐个 `re.escape`）+ **整段锚定** `^...$` 保证，
#:   因此 `第5-6节校内(户外)X` / `第5-6节校` / `第5-6节线上教学` 一律不接受。
_SECTION_PATTERN = re.compile(
    r"^第([0-9]+)-([0-9]+)节("
    + "|".join(re.escape(suffix) for suffix in _KNOWN_SECTIONS_SUFFIXES)
    + r")?$"
)

#: **仅用于错误分类**（⛔ 不用于接受）：`第N-M节` 前缀是否成立，
#: 用来把"未知 suffix"与"形状本身不认识"分开，同时⛔ 不回显任何 token 内容。
_SECTION_PREFIX_PATTERN = re.compile(r"^第[0-9]+-[0-9]+节")


@dataclass(frozen=True)
class ParsedScheduleSegment:
    """一段已解析的上课安排（Course Data **内部对象**）。

    - `meeting` —— 可交给公共契约的部分；**可为 `None`**（non-concrete segment，
      见下）；
    - `teacher` / `activity` —— 真实存在、但**当前公共契约不承载**的内部保真信息；
    - `schedule_qualifier` —— **non-concrete** segment 携带的限定词
      （目前唯一已确认取值：`"校外"`）；
    - `schedule_weeks` —— **non-concrete** segment 已展开的周次
      （例如 `12-19周校外` → `[12, …, 19]`）。

    ⚠️ `meeting is None` 表示该 segment **有课程安排信息，但不足以确定时间冲突**
    （没有 weekday / sections / 具体地点）。此时：

    - `schedule_weeks` **必须**保存已解析的周次 ——
      ⛔ 否则周次信息在 `meeting is None` 时就**永久丢失**（`meeting.weeks` 不存在，
      而 qualifier 里也没有周次），后续无法回答"这门见习课到底排在第几周"；
    - ⛔ **不得**把 `weekday=None` / `sections=None` 塞进公共 `Meeting`；
    - ⛔ **不得**把 qualifier 伪装成 `Meeting.campus`（`"校外"` 不是具体校区，
      与 `openingSchoolName → campus` 是两回事）；
    - ⛔ **不猜**星期 / 节次。

    因此该 segment 由 `extract_meetings()` **不投影**为 `Meeting`，
    但 **`ParsedScheduleSegment` 本身仍保留**（⛔ 不是静默丢弃）。

    ⚠️ `schedule_weeks` 只用于 non-concrete segment；
    concrete segment 的周次仍在 `meeting.weeks`（此处为 `None`）。

    ⚠️ 这不是 Schema、不是 DTO、不是 Integration 公共接口。
    """

    meeting: Meeting | None
    teacher: str | None
    activity: str
    schedule_qualifier: str | None = None
    schedule_weeks: list[int] | None = None


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
    """解析 sections 字段，返回 `(start_section, end_section)`。

    已批准形态（**白名单**，Architecture Review 裁定）：

    ```text
    第N-M节
    第N-M节校内(户外)
    第N-M节校外
    第N-M节线上
    ```

    要求 `N >= 1` 且 `M >= N` —— **允许 `M == N`**（样本中 `第4-4节` 真实存在）；
    ⛔ 不得写成 `end > start`。

    ⚠️ suffix **只用于白名单校验**：公共 `Meeting` 没有 qualifier 字段，
    因此⛔ **不新增公共字段**、⛔ 也不把它存进任何公共对象（校验后即丢弃）。

    ⛔ 未批准的 suffix / 不认识的形状 / 非法区间一律 fail closed，
    且异常信息**只给安全分类**（`unsupported_sections_suffix` /
    `unsupported_sections_shape` / `unsupported_sections_range`），
    ⛔ **不回显原始 token**。
    """

    if not isinstance(token, str):
        raise CourseDataNormalizationError(
            f"节次必须是字符串，实际是 {type(token).__name__}"
        )

    candidate = token.strip()
    match = _SECTION_PATTERN.match(candidate)
    if match is None:
        # ⛔ 只做分类，不回显 token / suffix / 任何 token 内容
        reason = (
            SECTIONS_ERROR_UNSUPPORTED_SUFFIX
            if _SECTION_PREFIX_PATTERN.match(candidate) is not None
            else SECTIONS_ERROR_UNSUPPORTED_SHAPE
        )
        raise CourseDataNormalizationError(
            f"节次形态未确认（{reason}）：只接受 `第N-M节` 或 `第N-M节` + 已批准 suffix "
            f"（{'、'.join(_KNOWN_SECTIONS_SUFFIXES)}）；N ≥ 1 且 M ≥ N。"
            f"⛔ 本错误不回显原始 token"
        )

    # ⚠️ 第 3 个捕获组是**已批准 suffix**（可能为 `None`）：
    # 它只用于白名单校验，⛔ 不进入任何公共对象。
    start, end = int(match.group(1)), int(match.group(2))
    if start < 1 or end < start:
        raise CourseDataNormalizationError(
            f"节次区间非法（{SECTIONS_ERROR_UNSUPPORTED_RANGE}）：要求 N ≥ 1 且 M ≥ N。"
            f"⛔ 本错误不回显原始 token"
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


def _try_parse_non_concrete_fields(
    fields: Sequence[str], segment_index: int
) -> ParsedScheduleSegment | None:
    """尝试把 **2 字段** 解析为 **non-concrete** segment。

    支持**两种已确认**形态：

    ```text
    plain     ：<weeks token> / <non-empty activity>
                例如 1-17周 / 实验实践环节
    qualified ：<weeks token><已确认 qualifier> / <non-empty activity>
                例如 12-19周校外 / 实验实践环节
    ```

    ✅ 两种都**没有** teacher 字段：
    ⛔ **不得把 row 级 `teachingName` 注入 segment.teacher**
    （row 级教师与该 segment 无对应关系，注入等于凭空造事实）。

    成功返回 `ParsedScheduleSegment(meeting=None, teacher=None, ...)`；
    ⛔ 不符合 grammar 时返回 `None`，由调用方**整体失败**。

    ⚠️ 关键点：`12-19周校外` **不能整串**送进 `expand_weeks()` ——
    它只认识 `<weeks token>`。因此这里先**分别**取得：

    - `weeks_token` = `12-19周` → 交给 `expand_weeks()`
    - `qualifier`    = `校外`    → 单独存入 `schedule_qualifier`（⛔ 不伪装成 campus）

    展开后的周次存入 **`schedule_weeks`**：因为 `meeting is None`，
    `meeting.weeks` 不存在，若不在此保存，周次信息会**永久丢失**。

    ⛔ qualifier 是**白名单**：`12-19周XXX` 一律不匹配 → 整体失败。
    """

    first_field = fields[0].strip()
    weeks_token: str
    qualifier: str | None

    if is_plain_week_range(first_field):
        # plain：`1-17周 / activity` —— 没有 qualifier。
        weeks_token, qualifier = first_field, None
    else:
        match = _QUALIFIED_WEEKS_ONLY.match(first_field)
        if match is None:
            return None
        # qualified：`12-19周校外 / activity` —— qualifier 已在白名单内。
        weeks_token, qualifier = match.group(1), match.group(2)

    # 只展开**周次 token 自身**，绝不把 qualifier 一起送进去。
    weeks = expand_weeks(weeks_token)

    activity = _require_non_empty_token(
        fields[1], field="activity", segment_index=segment_index
    )

    # non-concrete：没有 weekday / sections / 具体地点 / teacher。
    # ⚠️ 周次**必须**随 segment 保留（meeting 为 None，别处无处存放）。
    return ParsedScheduleSegment(
        meeting=None,
        teacher=None,
        activity=activity,
        schedule_qualifier=qualifier,
        schedule_weeks=weeks,
    )


def _try_parse_non_concrete_with_teacher_fields(
    fields: Sequence[str], segment_index: int
) -> ParsedScheduleSegment:
    """把 **3 字段** 解析为 **non-concrete、带 teacher** 的 segment。

    支持**两种已确认**的第 1 字段形态：

    ```text
    plain     ：<weeks token> / <non-empty teacher> / <non-empty activity>
                例如 1-17周 / 龙霞 / 实验实践环节
    qualified ：<weeks token><已确认 qualifier> / <non-empty teacher> / <non-empty activity>
                例如 16-16周校内(户外) / 龙霞 / 实验实践环节
    ```

    ⚠️ **真实证据（2026-1）**：两种形态的 `fields[1]` 均经同行 `row.teachingName`
    交叉确认是 **teacher** ⇒
    ⛔ **不是** location（没有 weekday / sections / 具体地点）；
    ⛔ 也**不是**未知 qualifier。

    ⚠️ **必须先把 weeks 与 qualifier 拆开**：
    `16-16周校内(户外)` → `weeks_token = "16-16周"`、`qualifier = "校内(户外)"`；
    ⛔ **只把 `weeks_token` 交给 `expand_weeks()`**（整串会直接失败）。

    ⛔ **不生成 `Meeting`**；⛔ **不把 teacher 塞进 `Meeting`**；
    ✅ 周次保留在 `schedule_weeks`；✅ qualifier 保留在 `schedule_qualifier`
    （⛔ **不当作 `campus`**）；✅ teacher 保留在内部 `teacher` 字段。
    """

    first_field = fields[0].strip()

    match = _WEEKS_WITH_OPTIONAL_QUALIFIER.match(first_field)
    if match is None:
        # 连"weeks + 可选 qualifier"的基本形状都不是（例如 `abc周/...`、
        # `1-17/...`、`第1-17周/...`）。
        if not is_plain_week_range(first_field):
            raise CourseDataNormalizationError(
                f"teachingTimePlaceStr 的第 {segment_index} 段是 3 字段"
                f"（weeks / teacher / activity），但其第 1 个字段不是合法的"
                f"`N-M周` 周次 token（也不符合已确认的 qualifier 形态）。"
                f"本 parser 不猜格式，已整体停止（不回显该字段取值）"
            )
        weeks_token, qualifier = first_field, None
    else:
        weeks_token = match.group(1)
        qualifier = match.group(2)

    if qualifier is not None and qualifier not in _KNOWN_SCHEDULE_QUALIFIERS:
        # ⛔ 白名单而非通配：`16-16周未知文本` 一律拒绝（不回显取值）。
        raise CourseDataNormalizationError(
            f"teachingTimePlaceStr 的第 {segment_index} 段的 qualifier 尚未被真实证据确认"
            f"（已确认：{'、'.join(_KNOWN_SCHEDULE_QUALIFIERS)}）。"
            f"本 parser 不猜格式，已整体停止（不回显该字段取值）"
        )

    # 只展开**周次 token 自身**，绝不把 qualifier 一起送进去。
    weeks = expand_weeks(weeks_token)

    teacher = _require_non_empty_token(
        fields[1], field="teacher", segment_index=segment_index
    )
    activity = _require_non_empty_token(
        fields[2], field="activity", segment_index=segment_index
    )

    # non-concrete：没有 weekday / sections / 具体地点；⛔ 不生成 Meeting。
    return ParsedScheduleSegment(
        meeting=None,
        teacher=teacher,
        activity=activity,
        schedule_qualifier=qualifier,
        schedule_weeks=weeks,
    )


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
                f"{FIELDS_NON_CONCRETE}（non-concrete："
                f"`<weeks token><已确认 qualifier>` / activity）/ "
                f"{FIELDS_NON_CONCRETE_WITH_TEACHER}（non-concrete："
                f"`<weeks token>` / teacher / activity）/ "
                f"{FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER}（无地点无教师）/ "
                f"{FIELDS_FIVE}（有地点无教师 或 无地点有教师）/ "
                f"{FIELDS_WITH_LOCATION_AND_TEACHER}（有地点有教师）"
            )

        # 2 字段：**只有**已确认的 non-concrete grammar 才接受；
        # ⛔ 其余任意 2 字段结构一律 fail closed。
        if field_count == FIELDS_NON_CONCRETE:
            non_concrete = _try_parse_non_concrete_fields(fields, offset)
            if non_concrete is None:
                raise CourseDataNormalizationError(
                    f"teachingTimePlaceStr 的第 {offset} 段是 2 字段，"
                    f"但既不是已确认的 plain 形态（`<weeks token>` / activity），"
                    f"也不是已确认的 qualified 形态"
                    f"（`<weeks token>` + 已确认 qualifier "
                    f"{'/'.join(_KNOWN_SCHEDULE_QUALIFIERS)} / activity）。"
                    f"本 parser 不猜格式，已整体停止（不回显该字段取值）"
                )
            parsed.append(non_concrete)
            continue

        # 3 字段：**只有**已确认的 `weeks / teacher / activity` 结构才接受
        # （2026-1 真实证据；⛔ 不是 location，⛔ 不生成 Meeting）。
        if field_count == FIELDS_NON_CONCRETE_WITH_TEACHER:
            parsed.append(
                _try_parse_non_concrete_with_teacher_fields(fields, offset)
            )
            continue

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
    """把解析结果投影成公共 `Meeting[]`。

    - 只投影 `meeting is not None` 的 segment（**non-concrete** segment
      没有 weekday / sections，不足以构成公共 `Meeting`）；
    - ⛔ **不是静默丢弃**：`ParsedScheduleSegment` 本身仍完整保留在解析结果里，
      只是不进入公共契约；
    - 其余情况仍**只做投影**：丢弃当前公共契约不承载的 `teacher` / `activity` /
      `schedule_qualifier`，不筛选、不合并、不排序，也**不修改** `Meeting` Schema。

    ⚠️ 若某 `CourseOffering` 最终 `meetings == []`（例如只有 non-concrete segment），
    按现有 **DG-07** 语义即为 **schedule UNKNOWN** ——
    「有课程安排信息，但不足以判断时间冲突」。⛔ 本轮**未修改** Planner。
    """

    return [segment.meeting for segment in segments if segment.meeting is not None]
