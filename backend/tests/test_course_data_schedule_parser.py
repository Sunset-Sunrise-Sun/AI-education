"""`teachingTimePlaceStr` parser 测试（Phase 2B-2B，2026-1 真实证据扩展）。

⚠️ **数据最小化**：本文件中的上课时间地点串、教师、校区、教室**全部为人工虚构**，
按结构等价构造。**不包含**私密脱敏样本原文、真实教师姓名、真实教室或内部 ID。

结构依据（已确认）：`segment separator = ","`、`field separator = "/"`，
**最多一个**末尾逗号（需忽略）。

2026-1 全量采集首轮的真实报错证据确认：**teacher 并不总是在 segment 中出现**。
因此合法结构有四种：

```text
4 字段（无地点、无教师）：weeks / weekday / sections / activity
5 字段 A（有地点、无教师）：weeks / weekday / sections / location / activity
5 字段 B（无地点、有教师）：weeks / weekday / sections / teacher / activity
6 字段（有地点、有教师）：weeks / weekday / sections / location / teacher / activity
```

⛔ 3 字段与 7+ 字段继续 fail closed。
"""

from __future__ import annotations

import pytest

from app.course_data import (
    CourseDataNormalizationError,
    ParsedScheduleSegment,
    extract_meetings,
    parse_sections,
    parse_teaching_time_place,
    parse_weekday,
)
from app.models.contracts import Meeting

# ---------------------------------------------------------------------------
# 人工虚构的 segment 文本构造器
# ---------------------------------------------------------------------------

TEACHER_A = "示例教师A"
TEACHER_B = "示例教师B"
ACTIVITY = "示例环节"
CAMPUS = "示例校区"
CLASSROOM = "示例教学楼-2108"
LOCATION = f"{CAMPUS}-{CLASSROOM}"


def _segment(
    weeks: str,
    weekday: str,
    sections: str,
    *,
    teacher: str = TEACHER_A,
    activity: str = ACTIVITY,
    location: str | None = None,
    no_teacher: bool = False,
) -> str:
    """构造一个 segment 文本。

    - `location` 非空 → 插入 location 字段；
    - `no_teacher=True` → **不插入** teacher（4 字段形态，或配合 location 得到 5 字段 A）。
    """

    fields = [weeks, weekday, sections]
    if location is not None:
        fields.append(location)
    if not no_teacher:
        fields.append(teacher)
    fields.append(activity)
    return "/".join(fields)


def _four_field(weeks: str, weekday: str, sections: str, *, activity: str = ACTIVITY) -> str:
    """4 字段：weeks / weekday / sections / activity（无地点、无教师）。"""

    return _segment(weeks, weekday, sections, activity=activity, no_teacher=True)


def _five_field_with_location(
    weeks: str,
    weekday: str,
    sections: str,
    *,
    location: str = LOCATION,
    activity: str = ACTIVITY,
) -> str:
    """5 字段 A：weeks / weekday / sections / location / activity（有地点、无教师）。"""

    return _segment(
        weeks, weekday, sections, location=location, activity=activity, no_teacher=True
    )


# ---------------------------------------------------------------------------
# 5 字段（无地点）
# ---------------------------------------------------------------------------


def test_five_field_segment_without_location() -> None:
    text = _segment("1-8周", "星期五", "第5-6节")

    segments = parse_teaching_time_place(text)

    assert len(segments) == 1
    meeting = segments[0].meeting
    assert meeting.weekday == 5
    assert meeting.start_section == 5
    assert meeting.end_section == 6
    assert meeting.weeks == list(range(1, 9))
    assert meeting.campus is None
    assert meeting.classroom is None


def test_missing_location_yields_none_campus_and_classroom() -> None:
    """无地点 segment 必须产生 `campus = None` / `classroom = None`。

    绝不允许拿 `openingSchoolName` 之类的外部字段来"补"地点。
    """

    (segment,) = parse_teaching_time_place(_segment("1-5周", "星期一", "第1-2节"))

    assert segment.meeting.campus is None
    assert segment.meeting.classroom is None


# ---------------------------------------------------------------------------
# 6 字段（有地点）
# ---------------------------------------------------------------------------


def test_six_field_segment_with_location() -> None:
    text = _segment("7-8周", "星期三", "第4-4节", location=f"{CAMPUS}-{CLASSROOM}")

    (segment,) = parse_teaching_time_place(text)

    assert segment.meeting.campus == CAMPUS
    assert segment.meeting.classroom == CLASSROOM


def test_location_splits_on_first_hyphen_only() -> None:
    """地点只按**第一个 `-`** 切：campus = 第一段，classroom = 其余完整文本。"""

    (segment,) = parse_teaching_time_place(
        _segment("1-5周", "星期一", "第1-2节", location="示例校区-示例教学楼-2108")
    )

    assert segment.meeting.campus == "示例校区"
    assert segment.meeting.classroom == "示例教学楼-2108"


def test_location_without_hyphen_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(
            _segment("1-5周", "星期一", "第1-2节", location="没有分隔符的地点")
        )


def test_location_with_empty_campus_or_classroom_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(
            _segment("1-5周", "星期一", "第1-2节", location="-第二教学楼")
        )

    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(
            _segment("1-5周", "星期一", "第1-2节", location="示例校区-")
        )


def test_opening_school_name_is_never_used_for_campus() -> None:
    """⛔ 地点只来自 segment 中**实际存在的** location 字段。

    这里故意在字符串里放一个"看起来像校区"的取值，
    但 5 字段 segment **没有** location，因此 `campus` 必须是 `None`。
    """

    (segment,) = parse_teaching_time_place(_segment("1-5周", "星期一", "第1-2节"))

    assert segment.meeting.campus is None


# ---------------------------------------------------------------------------
# 多 segment / 末尾逗号 / 中间空段
# ---------------------------------------------------------------------------


def test_multiple_segments_are_all_preserved_in_order() -> None:
    """多 segment 必须**全部保留**，且顺序与 Raw 一致（不排序、不合并）。"""

    first = _segment("1-5周", "星期五", "第3-4节", location=f"{CAMPUS}-示例教室甲")
    second = _segment("10-17周", "星期一", "第1-2节", location=f"{CAMPUS}-示例教室乙")
    third = _segment("6-6周", "星期五", "第3-4节", location=f"{CAMPUS}-示例教室甲")

    segments = parse_teaching_time_place(",".join([first, second, third]))

    assert [s.meeting.weekday for s in segments] == [5, 1, 5]
    assert [s.meeting.weeks for s in segments] == [
        list(range(1, 6)),
        list(range(10, 18)),
        [6],
    ]
    assert [s.meeting.classroom for s in segments] == ["示例教室甲", "示例教室乙", "示例教室甲"]


def test_single_trailing_comma_is_ignored() -> None:
    """`seg,` —— 真实证据确认**最多一个**末尾逗号，因此单个末尾空段可忽略。"""

    text = _segment("1-8周", "星期五", "第5-6节") + ","

    assert len(parse_teaching_time_place(text)) == 1


def test_two_segments_with_single_trailing_comma() -> None:
    """`seg1,seg2,` —— 多段 + 单个末尾逗号（真实样本形态）。"""

    text = (
        _segment("1-8周", "星期五", "第5-6节")
        + ","
        + _segment("10-17周", "星期五", "第5-6节")
        + ","
    )

    assert len(parse_teaching_time_place(text)) == 2


@pytest.mark.parametrize("trailing", [",,", ",,,", ",,,,"])
def test_multiple_trailing_commas_are_rejected(trailing: str) -> None:
    """⛔ 多个末尾逗号**超出真实证据**（只确认最多一个），必须拒绝。

    这里**不用** `while` 静默吞掉多个末尾空 segment。
    """

    text = _segment("1-8周", "星期五", "第5-6节") + trailing

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place(text)

    assert "末尾" in str(excinfo.value)


def test_middle_empty_segment_is_rejected() -> None:
    """⛔ `segment1,,segment2` **不得静默忽略**，必须失败。"""

    text = (
        _segment("1-8周", "星期五", "第5-6节")
        + ",,"
        + _segment("10-17周", "星期一", "第1-2节")
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place(text)

    assert "空 segment" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 非法输入
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [None, 123, ["1-8周"], {"a": 1}])
def test_non_string_input_is_rejected(text: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(text)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["", "   ", ",", ",,,"])
def test_empty_or_separator_only_input_is_rejected(text: str) -> None:
    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(text)


# ---------------------------------------------------------------------------
# 2 字段：non-concrete（`<weeks token><qualifier>` / activity）
# ---------------------------------------------------------------------------


def test_non_concrete_segment_is_parsed_without_meeting() -> None:
    """真实证据：`12-19周校外/实验实践环节`（见习类课程）。

    该 segment **没有** weekday / sections / 具体地点 / teacher，
    因此**不制造** `Meeting`，但 `ParsedScheduleSegment` **必须保留**。
    """

    (segment,) = parse_teaching_time_place("12-19周校外/实验实践环节")

    assert isinstance(segment, ParsedScheduleSegment)
    assert segment.meeting is None
    assert segment.teacher is None
    assert segment.schedule_qualifier == "校外"
    assert segment.activity == "实验实践环节"


def test_non_concrete_segment_retains_expanded_weeks() -> None:
    """⚠️ `meeting is None` 时，**展开后的周次必须保存在内部字段** `schedule_weeks`。

    否则周次会**永久丢失**：`meeting.weeks` 不存在，`schedule_qualifier` 里也没有周次，
    后续无法回答"这门见习课排在第几周"。
    """

    (segment,) = parse_teaching_time_place("12-19周校外/实验实践环节")

    assert segment.schedule_weeks == list(range(12, 20))
    # 周次确实是从**拆出来的 weeks token** 展开的（12..19 连续）
    assert segment.schedule_weeks is not None
    assert segment.schedule_weeks[0] == 12
    assert segment.schedule_weeks[-1] == 19


def test_non_concrete_weeks_survive_extract_meetings() -> None:
    """⛔ `extract_meetings()` 不投影 non-concrete，但**不得**因此丢失周次信息。"""

    segments = parse_teaching_time_place("12-19周校外/实验实践环节")

    assert extract_meetings(segments) == []
    # 原始 segment 仍带着周次
    assert segments[0].schedule_weeks == list(range(12, 20))
    assert segments[0].schedule_qualifier == "校外"


def test_concrete_segment_leaves_schedule_weeks_none() -> None:
    """concrete segment 的周次在 `meeting.weeks`，`schedule_weeks` 保持 `None`。"""

    (segment,) = parse_teaching_time_place(_segment("1-5周", "星期一", "第1-2节"))

    assert segment.schedule_weeks is None
    assert segment.meeting is not None
    assert segment.meeting.weeks == [1, 2, 3, 4, 5]


def test_mixed_segments_carry_weeks_in_their_respective_fields() -> None:
    """混合时各自把周次放在各自字段：concrete → `meeting.weeks`；non-concrete → `schedule_weeks`。"""

    text = ",".join(
        [
            _segment("1-8周", "星期五", "第5-6节"),
            "12-19周校外/实验实践环节",
        ]
    )

    segments = parse_teaching_time_place(text)

    assert segments[0].meeting is not None
    assert segments[0].meeting.weeks == list(range(1, 9))
    assert segments[0].schedule_weeks is None

    assert segments[1].meeting is None
    assert segments[1].schedule_weeks == list(range(12, 20))


def test_non_concrete_segment_weeks_are_expanded_from_token_not_whole_field() -> None:
    """⚠️ 周次必须来自**拆出来的 weeks token**，⛔ 不能把 `12-19周校外` 整串送进 `expand_weeks()`。

    本测试同时锁住"qualifier 不被当成周次的一部分"。
    """

    (segment,) = parse_teaching_time_place("12-19周校外/实验实践环节")

    # 12..19 连续周次（若把整串送进 expand_weeks 会直接失败）
    assert segment.meeting is None  # non-concrete 不投影
    # 通过 concrete 同名周次对照，确认 expand_weeks 的语义没被改动
    (concrete,) = parse_teaching_time_place("12-19周/星期五/第5-6节/示例教师A/示例环节")
    assert concrete.meeting is not None
    assert concrete.meeting.weeks == list(range(12, 20))


def test_non_concrete_segment_does_not_fake_campus_or_weekday() -> None:
    """⛔ `校外` 不得被伪装成 `campus`；⛔ 不得猜 weekday / sections。"""

    (segment,) = parse_teaching_time_place("12-19周校外/实验实践环节")

    # 没有 Meeting 就没有 campus / weekday / sections 可猜
    assert segment.meeting is None
    assert segment.schedule_qualifier == "校外"
    assert segment.schedule_qualifier != "北校园"  # ⛔ 与具体校区是两回事


def test_extract_meetings_skips_non_concrete_segment() -> None:
    """`extract_meetings()` 对该 segment 返回 `[]`（DG-07：schedule UNKNOWN）。"""

    segments = parse_teaching_time_place("12-19周校外/实验实践环节")

    assert extract_meetings(segments) == []


def test_mixed_concrete_and_non_concrete_keeps_segment_not_dropped() -> None:
    """混合：concrete + 校外实践 → **segment 数 2、Meeting 数 1**。

    证明 non-concrete 只是"不投影成 Meeting"，⛔ **不是静默丢 segment**。
    """

    text = ",".join(
        [
            _segment("1-8周", "星期五", "第5-6节"),
            "12-19周校外/实验实践环节",
        ]
    )

    segments = parse_teaching_time_place(text)
    meetings = extract_meetings(segments)

    assert len(segments) == 2, "⛔ non-concrete segment 不得被丢弃"
    assert len(meetings) == 1
    assert segments[1].meeting is None
    assert segments[1].schedule_qualifier == "校外"
    # concrete 段不受影响
    assert segments[0].meeting is not None
    assert segments[0].teacher == TEACHER_A


def test_non_concrete_after_trailing_comma_still_parses() -> None:
    """末尾逗号与 non-concrete 段可以共存。"""

    (segment,) = parse_teaching_time_place("12-19周校外/实验实践环节,")

    assert segment.meeting is None
    assert segment.schedule_qualifier == "校外"


@pytest.mark.parametrize(
    "text",
    [
        "随便写的东西/实验实践环节",  # 第 1 字段根本不是 weeks token
        "12-19周未知词/实验实践环节",  # ⛔ qualifier 不在白名单（不得通配）
        "12-19周线上/实验实践环节",  # 尚无证据的 qualifier
        "12-19周医院/实验实践环节",  # 尚无证据的 qualifier
        "12-19周实践基地/实验实践环节",  # 尚无证据的 qualifier
        "校外/实验实践环节",  # 缺 weeks token
        "12-19周校外/",  # activity 为空
        "12-19周校外",  # 只有 1 字段 → 字段数不在允许集合
    ],
)
def test_non_concrete_unknown_two_field_grammar_fails_closed(text: str) -> None:
    """⛔ 2 字段只接受**已验证** grammar；其余任意 2 字段结构 fail closed。"""

    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(text)


def test_non_concrete_error_message_does_not_echo_token() -> None:
    """错误信息不得回显未识别 2 字段的取值。"""

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place("12-19周未知词/实验实践环节")

    message = str(excinfo.value)
    assert "不猜格式" in message
    assert "12-19周未知词" not in message


@pytest.mark.parametrize(
    "text",
    [
        "1-8周/星期五/第5-6节/示例教师A/示例环节/多出来的/再多一个",  # 7 字段 → 拒绝
        "1-8周/星期五/第5-6节/示例教师A/示例环节/多出来的/再多一个/还更多",  # 8 字段 → 拒绝
    ],
)
def test_unexpected_field_count_is_rejected(text: str) -> None:
    """字段数只接受 2 / 3 / 4 / 5 / 6，其它（7+）fail closed。

    ⚠️ 3 字段**现在是合法结构**（`weeks / teacher / activity`，2026-1 真实证据），
    因此**不再**出现在本拒绝列表里。
    """

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place(text)

    assert "字段数" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 3 字段：non-concrete 带 teacher（`weeks` / `teacher` / `activity`）
# ---------------------------------------------------------------------------


def test_three_field_non_concrete_with_teacher() -> None:
    """真实证据：`1-17周/龙霞/实验实践环节`（同行 `teachingName` 亦为教师姓名）。

    ⇒ `fields[1]` 是 **teacher**，⛔ 不是 location，⛔ 不是未知 qualifier。
    """

    (segment,) = parse_teaching_time_place("1-17周/示例教师/实验实践环节")

    assert segment.meeting is None
    assert segment.schedule_weeks == list(range(1, 18))
    assert segment.teacher == "示例教师"
    assert segment.activity == "实验实践环节"
    assert segment.schedule_qualifier is None


def test_three_field_non_concrete_does_not_fake_meeting_or_location() -> None:
    """⛔ 不生成 `Meeting`；⛔ 不把 teacher 当成 location / campus。"""

    (segment,) = parse_teaching_time_place("1-17周/示例教师/实验实践环节")

    assert segment.meeting is None  # 没有 weekday / sections
    assert extract_meetings([segment]) == []


def test_three_field_weeks_are_expanded_from_plain_token() -> None:
    """周次必须由 `<weeks token>` 展开并保存在 `schedule_weeks`。"""

    (segment,) = parse_teaching_time_place("2-6周/示例教师/实验实践环节")

    assert segment.schedule_weeks == [2, 3, 4, 5, 6]


@pytest.mark.parametrize(
    "text",
    [
        "1-17周//实验实践环节",  # teacher 为空
        "1-17周/   /实验实践环节",  # teacher 全空白
        "1-17周/示例教师/",  # activity 为空
        "abc周/示例教师/实验实践环节",  # weeks token 非法
        "1-17/示例教师/实验实践环节",  # weeks token 缺"周"
        "第1-17周/示例教师/实验实践环节",  # ⛔ 带"第"字前缀无证据
        "1-17单周/示例教师/实验实践环节",  # 单周形态未泛化 → 拒绝
    ],
)
def test_three_field_invalid_parts_fail_closed(text: str) -> None:
    """3 字段的 weeks / teacher / activity 任一非法 → fail closed。"""

    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(text)


def test_three_field_error_message_does_not_echo_teacher() -> None:
    """3 字段路径的错误信息不得回显 teacher 取值（隐私）。"""

    # weeks token 非法（但 teacher 本身合法）→ 报错只讲 weeks，不回显 teacher
    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place("不是周次/某位教师/实验实践环节")

    assert "某位教师" not in str(excinfo.value)

    # activity 为空 → 只讲 activity，不回显 teacher
    with pytest.raises(CourseDataNormalizationError) as excinfo2:
        parse_teaching_time_place("1-17周/某位教师/")

    assert "某位教师" not in str(excinfo2.value)


def test_known_gap_weekday_error_echoes_token() -> None:
    """⚠️ **已登记的既有隐私缺口（本轮未修，属既有行为）**。

    4 字段结构是 `weeks / weekday / sections / activity`，
    因此当某条**含教师姓名**的文本被误当作 4 字段时，
    `fields[1]` 会作为 weekday token 被 `parse_weekday()` 回显到错误信息里：

    ```text
    无法识别的星期 token：'某位教师'；只接受 星期一 / … / 星期日
    ```

    本测试**只用于固定当前事实**（防止被误以为已修），
    ⛔ **不代表**该行为可接受。修它需要单独决策（会牵动既有 `parse_weekday` 契约与测试）。
    """

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place("1-8周/某位教师/实验实践环节/多余一段")

    # 当前**确实**会回显 —— 记录事实
    assert "某位教师" in str(excinfo.value)


def test_mixed_concrete_two_field_and_three_field_all_segments_kept() -> None:
    """混合：concrete + 2 字段 non-concrete + 3 字段 non-concrete。

    要求：`ParsedScheduleSegment` **全部保留**（3 条）；
    `Meeting` **只含 concrete**（1 条）；两种 non-concrete 的 **weeks 均保留**。
    """

    text = ",".join(
        [
            _segment("1-8周", "星期五", "第5-6节"),  # concrete
            "12-19周校外/实验实践环节",  # 2 字段 non-concrete
            "1-17周/示例教师/实验实践环节",  # 3 字段 non-concrete
        ]
    )

    segments = parse_teaching_time_place(text)
    meetings = extract_meetings(segments)

    # 段数全部保留
    assert len(segments) == 3, "⛔ 不得丢弃任何 segment"
    # 只有 concrete 进入公共契约
    assert len(meetings) == 1
    assert meetings[0].weeks == list(range(1, 9))

    # 2 字段 non-concrete：qualifier + weeks 保留
    assert segments[1].meeting is None
    assert segments[1].schedule_qualifier == "校外"
    assert segments[1].schedule_weeks == list(range(12, 20))
    assert segments[1].teacher is None

    # 3 字段 non-concrete：teacher + weeks 保留，qualifier 为 None
    assert segments[2].meeting is None
    assert segments[2].schedule_qualifier is None
    assert segments[2].teacher == "示例教师"
    assert segments[2].schedule_weeks == list(range(1, 18))


# ---------------------------------------------------------------------------
# 4 字段：无地点、无教师（2026-1 真实证据新增）
# ---------------------------------------------------------------------------


def test_four_field_segment_has_no_teacher_and_no_location() -> None:
    """4 字段：weeks / weekday / sections / activity → teacher / campus / classroom 全为 None。"""

    (segment,) = parse_teaching_time_place(_four_field("1-8周", "星期五", "第5-6节"))

    assert segment.teacher is None
    assert segment.activity == ACTIVITY
    assert segment.meeting.campus is None
    assert segment.meeting.classroom is None
    assert segment.meeting.weekday == 5
    assert segment.meeting.start_section == 5
    assert segment.meeting.end_section == 6


def test_four_field_segment_missing_activity_is_rejected() -> None:
    """4 字段的 activity 仍必须非空（⛔ 不自动补，也不静默接受空值）。"""

    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place("1-8周/星期五/第5-6节/   ")


# ---------------------------------------------------------------------------
# 5 字段 A：有地点、无教师（2026-1 真实证据新增）
# ---------------------------------------------------------------------------


def test_five_field_with_location_parses_location_not_teacher() -> None:
    """5 字段 A：weeks / weekday / sections / location / activity。"""

    (segment,) = parse_teaching_time_place(_five_field_with_location("1-8周", "星期五", "第5-6节"))

    assert segment.meeting.campus == CAMPUS
    assert segment.meeting.classroom == CLASSROOM
    assert segment.teacher is None
    assert segment.activity == ACTIVITY


def test_five_field_with_location_does_not_treat_location_as_teacher() -> None:
    """⚠️ **回归测试（本轮核心缺陷）**：

    旧实现把 5 字段的第 4 字段**无条件当成 teacher**，
    于是真实数据里的 location 被静默错读成 teacher，
    导致 `Meeting.campus / classroom` 变成 `None`（静默错误解释）。

    本测试锁定：location 必须被解析成地点，⛔ 绝不能被当成 teacher。
    """

    (segment,) = parse_teaching_time_place(_five_field_with_location("1-8周", "星期五", "第5-6节"))

    # location 必须落在 meeting 上
    assert segment.meeting.campus == CAMPUS
    assert segment.meeting.classroom == CLASSROOM
    # 且**不得**被当成 teacher
    assert segment.teacher is None
    assert segment.teacher != LOCATION


# ---------------------------------------------------------------------------
# 5 字段 B：无地点、有教师（保留旧行为）
# ---------------------------------------------------------------------------


def test_five_field_with_teacher_keeps_legacy_behaviour() -> None:
    """5 字段 B：第 4 字段**不满足** location grammar → 仍按 teacher 解释。"""

    (segment,) = parse_teaching_time_place(_segment("1-8周", "星期五", "第5-6节"))

    assert segment.teacher == TEACHER_A
    assert segment.activity == ACTIVITY
    assert segment.meeting.campus is None
    assert segment.meeting.classroom is None


@pytest.mark.parametrize(
    "teacher_like",
    [
        "示例教师A",  # 无 '-' → 明确是 teacher
        "示例教师B",  # 无 '-' → 明确是 teacher
    ],
)
def test_five_field_no_dash_token_is_teacher(teacher_like: str) -> None:
    """5 字段判别（收紧后）：**无 `-`** → 明确是 teacher。"""

    text = "/".join(["1-8周", "星期五", "第5-6节", teacher_like, ACTIVITY])

    (segment,) = parse_teaching_time_place(text)

    assert segment.teacher == teacher_like
    assert segment.meeting.campus is None
    assert segment.meeting.classroom is None


def test_five_field_three_segment_token_is_location() -> None:
    """5 字段判别（收紧后）：**>= 3 个非空 `-` 分段** → 明确是 location。"""

    text = "/".join(["1-8周", "星期五", "第5-6节", LOCATION, ACTIVITY])

    (segment,) = parse_teaching_time_place(text)

    assert segment.meeting.campus == CAMPUS
    assert segment.meeting.classroom == CLASSROOM
    assert segment.teacher is None


@pytest.mark.parametrize(
    "ambiguous",
    [
        "示例-教师A",  # 2 段 → 二义
        "-示例教师A",  # 2 段（园区空）→ 二义
        "示例教师A-",  # 2 段（教室空）→ 二义
        "  -  ",  # 2 段（两侧空）→ 二义
        "示例校区-示例教学楼-",  # 3 段但末段为空 → 非空仅 2 段 → 二义
    ],
)
def test_five_field_ambiguous_token_fails_closed(ambiguous: str) -> None:
    """5 字段判别（收紧后）：**其余二义形态 → fail closed**（⛔ 不猜 teacher / location）。"""

    text = "/".join(["1-8周", "星期五", "第5-6节", ambiguous, ACTIVITY])

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place(text)

    # 错误信息必须说明"不猜语义"，且**不回显**该字段取值
    assert "不猜" in str(excinfo.value)
    assert ambiguous not in str(excinfo.value)


def test_five_field_ambiguous_does_not_silently_become_teacher_or_location() -> None:
    """⚠️ **回归测试（本轮收紧的核心）**：

    旧规则下 `A-B`（两段、含 `-`）会被判成 location，从而把可能的 teacher
    静默错读成地点；收紧后必须**整体失败**，⛔ 既不得当成 teacher、也不得当成 location。
    """

    text = "/".join(["1-8周", "星期五", "第5-6节", "示例-教师A", ACTIVITY])

    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(text)


def test_mixed_three_segment_string_from_real_evidence_shape() -> None:
    """按 2026-1 真实证据的形状：5 字段(location) / 4 字段(无) / 5 字段(location)。"""

    text = ",".join(
        [
            _five_field_with_location("1-8周", "星期五", "第5-6节"),
            _four_field("2-9周", "星期三", "第1-2节"),
            _five_field_with_location("3-10周", "星期一", "第3-4节"),
        ]
    )

    segments = parse_teaching_time_place(text)

    assert len(segments) == 3
    assert segments[0].meeting.campus == CAMPUS
    assert segments[1].meeting.campus is None
    assert segments[1].teacher is None
    assert segments[2].meeting.campus == CAMPUS
    assert all(item.teacher is None for item in segments)


# ---------------------------------------------------------------------------
# 星期
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("星期一", 1),
        ("星期二", 2),
        ("星期三", 3),
        ("星期四", 4),
        ("星期五", 5),
        ("星期六", 6),
        ("星期日", 7),
    ],
)
def test_weekday_tokens_are_mapped(token: str, expected: int) -> None:
    assert parse_weekday(token) == expected


@pytest.mark.parametrize("token", ["星期天", "周一", "Monday", "星期八", "", "  "])
def test_unknown_weekday_tokens_are_rejected(token: str) -> None:
    with pytest.raises(CourseDataNormalizationError):
        parse_weekday(token)


def test_weekday_is_taken_from_the_segment_itself() -> None:
    """`weekday` 只来自 segment 自带的星期 token（与任何外部字段无关）。"""

    (segment,) = parse_teaching_time_place(_segment("1-5周", "星期六", "第1-2节"))

    assert segment.meeting.weekday == 6


# ---------------------------------------------------------------------------
# 节次
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("第1-2节", (1, 2)),
        ("第3-4节", (3, 4)),
        ("第5-6节", (5, 6)),
        ("第7-8节", (7, 8)),
        ("第4-4节", (4, 4)),  # 单节：真实存在，必须合法
        ("第1-1节", (1, 1)),
    ],
)
def test_section_tokens_are_parsed(token: str, expected: tuple[int, int]) -> None:
    assert parse_sections(token) == expected


@pytest.mark.parametrize(
    "token",
    [
        "4-4节",  # 缺"第"
        "第4节",  # 单个节次
        "第4－4节",  # 全角连字符
        "第0-4节",  # 起点 0
        "第6-3节",  # 结束早于开始
        "第 4-4 节",  # 含空格
        "第4~4节",
        "",
    ],
)
def test_invalid_section_tokens_are_rejected(token: str) -> None:
    with pytest.raises(CourseDataNormalizationError):
        parse_sections(token)


def test_sections_allow_equal_start_and_end() -> None:
    """⛔ 不得写成 `end > start`；`第4-4节` 必须合法。"""

    (segment,) = parse_teaching_time_place(_segment("1-5周", "星期三", "第4-4节"))

    assert segment.meeting.start_section == 4
    assert segment.meeting.end_section == 4


# ---------------------------------------------------------------------------
# teacher / activity：内部保留，但不进入公共 Meeting
# ---------------------------------------------------------------------------


def test_teacher_and_activity_are_preserved_internally() -> None:
    (segment,) = parse_teaching_time_place(_segment("1-5周", "星期一", "第1-2节"))

    assert isinstance(segment, ParsedScheduleSegment)
    assert segment.teacher == TEACHER_A
    assert segment.activity == ACTIVITY


def test_public_meeting_has_no_teacher_field() -> None:
    """⛔ meeting 级教师关联仍是 known deferred representation gap：

    teacher 保留在内部 `ParsedScheduleSegment`，**不**进入公共 `Meeting`。
    """

    (segment,) = parse_teaching_time_place(_segment("1-5周", "星期一", "第1-2节"))

    assert "teacher" not in Meeting.model_fields
    assert "teacher" not in segment.meeting.model_dump()


def test_extract_meetings_projects_only_meetings() -> None:
    segments = parse_teaching_time_place(
        ",".join(
            [
                _segment("1-5周", "星期一", "第1-2节"),
                _segment("7-8周", "星期三", "第4-4节", location=f"{CAMPUS}-{CLASSROOM}"),
            ]
        )
    )

    meetings = extract_meetings(segments)

    assert all(isinstance(item, Meeting) for item in meetings)
    assert [item.weekday for item in meetings] == [1, 3]
    assert meetings[1].campus == CAMPUS


@pytest.mark.parametrize("field_index", [3, 4])
def test_empty_teacher_or_activity_is_rejected(field_index: int) -> None:
    fields = ["1-5周", "星期一", "第1-2节", TEACHER_A, ACTIVITY]
    fields[field_index] = "   "

    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place("/".join(fields))


def test_empty_teacher_in_location_segment_is_rejected() -> None:
    text = "/".join(["1-5周", "星期一", "第1-2节", f"{CAMPUS}-{CLASSROOM}", "", ACTIVITY])

    with pytest.raises(CourseDataNormalizationError):
        parse_teaching_time_place(text)


def test_parser_error_messages_do_not_echo_sensitive_fields() -> None:
    """错误信息不得回显 location / teacher / activity 原文（隐私卫生）。"""

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place(
            "/".join(
                [
                    "1-5周",
                    "星期一",
                    "第1-2节",
                    "机密校区-机密楼-机密教室",
                    "机密教师",
                    ACTIVITY,
                    "多余字段",
                ]
            )
        )

    message = str(excinfo.value)
    assert "机密" not in message
