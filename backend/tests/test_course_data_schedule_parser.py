"""`teachingTimePlaceStr` parser 测试（Phase 2B-2B）。

⚠️ **数据最小化**：本文件中的上课时间地点串、教师、校区、教室**全部为人工虚构**，
按结构等价构造。**不包含**私密脱敏样本原文、真实教师姓名、真实教室或内部 ID。

结构依据（已确认）：`segment separator = ","`、`field separator = "/"`，
无地点 5 字段 / 有地点 6 字段，**最多一个**末尾逗号（需忽略）。
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


def _segment(
    weeks: str,
    weekday: str,
    sections: str,
    *,
    teacher: str = TEACHER_A,
    activity: str = ACTIVITY,
    location: str | None = None,
) -> str:
    fields = [weeks, weekday, sections]
    if location is not None:
        fields.append(location)
    fields.extend([teacher, activity])
    return "/".join(fields)


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


@pytest.mark.parametrize(
    "text",
    [
        "1-8周/星期五/第5-6节",  # 3 字段
        "1-8周/星期五/第5-6节/示例教师A",  # 4 字段
        "1-8周/星期五/第5-6节/示例教师A/示例环节/多出来的/再多一个",  # 7 字段
    ],
)
def test_unexpected_field_count_is_rejected(text: str) -> None:
    """字段数只接受 5 或 6，其它 fail closed。"""

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        parse_teaching_time_place(text)

    assert "字段数" in str(excinfo.value)


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
