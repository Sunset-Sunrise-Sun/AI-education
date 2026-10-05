"""Course Data 标准化内核测试（Phase 2B-2A）。

覆盖"**已确认 SYSU 字段 → `CourseOffering`**"的确定性映射与校验，
以及**故意不做**的那些映射（`weekDay` / `openingSchoolName` / 内部 ID / 原始时间串）。

⚠️ 数据最小化：本文件只使用**人工虚构**的 source-shaped dict。
**不包含**真实教师姓名、内部长 ID 取值、`readObj`、Raw JSON、Cookie / Session / Token。
测试中的教师统一写作 `"示例教师A"`（或 `None`）。

⚠️ 本文件**不测任何网络行为** —— 本轮实现是零网络的。
"""

from __future__ import annotations

import pytest

from app.course_data import (
    CourseDataNormalizationError,
    build_course_offering,
    expand_weeks,
)
from app.course_data.normalization import build_course_offering_from_missing_schedule_field
from app.models.contracts import CourseOffering, DataSource, Meeting

# ---------------------------------------------------------------------------
# 人工虚构的 source-shaped 输入
# ---------------------------------------------------------------------------


def _raw(**overrides: object) -> dict[str, object]:
    """构造一条**人工虚构**的 Raw 记录（键名对齐已确认的 SYSU 字段）。"""

    raw: dict[str, object] = {
        "courseNum": "62001001",
        "courseName": "离散数学",
        "classNumber": "6200100120260101",
        "yearTerm": "2026-1",
        "score": "3",
        "teachingName": "示例教师A",
        "limitNumber": 90,
        "selectedNumber": 75,
    }
    raw.update(overrides)
    return raw


def _meeting(**overrides: object) -> Meeting:
    payload: dict[str, object] = {
        "weekday": 1,
        "start_section": 1,
        "end_section": 2,
        "weeks": [1, 2, 3, 4],
        "campus": "东校园",
        "classroom": "东A201",
    }
    payload.update(overrides)
    return Meeting(**payload)


def _build(raw: dict[str, object] | None = None, meetings: list[Meeting] | None = None):
    return build_course_offering(
        raw if raw is not None else _raw(),
        meetings=meetings if meetings is not None else [_meeting()],
        source="mock://course-data-normalization-test",
    )


#: 内部长 ID / 计数：**只记录存在**，绝不映射。
_INTERNAL_ID_FIELDS = (
    "courseId",
    "class_ID",
    "sumClassesID",
    "sumClassesNum",
    "outLineId",
    "timePlaceId",
)

#: 暂缓业务字段（D5 其余字段）：一律不进入公共契约。
_BUSINESS_DEFERRED_FIELDS = (
    "courseCategoryName",
    "openingUnitName",
    "examMode",
    "readObj",
    "teachProgressSubmitState",
    "openClass",
    "outlineTypeNum",
)


# ---------------------------------------------------------------------------
# 已确认字段映射
# ---------------------------------------------------------------------------


def test_confirmed_fields_are_mapped() -> None:
    offering = _build()

    assert offering.course_id == "62001001"
    assert offering.course_name == "离散数学"
    assert offering.class_id == "6200100120260101"
    assert offering.semester == "2026-1"
    assert offering.teacher == "示例教师A"


def test_score_string_number_becomes_credit() -> None:
    """`score` 是**字符串数字**，必须转换成 `number`。"""

    offering = _build(_raw(score="3.5"))

    assert offering.credit == 3.5
    assert isinstance(offering.credit, float)


def test_score_accepts_surrounding_whitespace() -> None:
    assert _build(_raw(score=" 3 ")).credit == 3.0


def test_limit_number_becomes_capacity() -> None:
    assert _build(_raw(limitNumber=120)).capacity == 120


def test_remaining_capacity_is_derived_from_limit_and_selected() -> None:
    """⚠️ `remaining_capacity` 是**派生值**：`limitNumber - selectedNumber`。

    学校接口**没有**直接提供剩余容量。这条用例同时锁住：
    ① 结果等于两者相减；② 输入里**根本不存在** `remaining_capacity` 这个 Raw 字段。
    """

    raw = _raw(limitNumber=120, selectedNumber=112)

    assert "remaining_capacity" not in raw

    offering = _build(raw)

    assert offering.capacity == 120
    assert offering.remaining_capacity == 8


@pytest.mark.parametrize(
    ("limit_number", "selected_number", "expected"),
    [
        (90, 75, 15),  # selected <  limit → 正常差值
        (60, 60, 0),  # selected == limit → 0
        (150, 40, 110),
        (10, 11, None),  # selected >  limit → unknown（真实来源存在该状态）
        (10, 49, None),
    ],
)
def test_remaining_capacity_follows_inputs(
    limit_number: int, selected_number: int, expected: int | None
) -> None:
    """`remaining_capacity` 三分支规则（Architecture Review 裁定）。"""

    offering = _build(_raw(limitNumber=limit_number, selectedNumber=selected_number))

    assert offering.remaining_capacity == expected


def test_selected_greater_than_limit_is_not_rejected() -> None:
    """⛔ `selectedNumber > limitNumber` **不再**拒绝整条教学班。

    真实 2026-1 east artifact 已证明来源里确实存在该状态；
    `capacity` 保持来源原值，`remaining_capacity` 降级为 `None`。
    """

    offering = _build(_raw(limitNumber=10, selectedNumber=49))

    assert offering.capacity == 10
    assert offering.remaining_capacity is None


def test_selected_greater_than_limit_does_not_clamp_or_rewrite_capacity() -> None:
    """⛔ 不 clamp 到 0、⛔ 不改写 `capacity`（保持来源 `limitNumber`）。"""

    for limit_number, selected_number in ((0, 1), (10, 11), (45, 49), (1, 999)):
        offering = _build(
            _raw(limitNumber=limit_number, selectedNumber=selected_number)
        )

        assert offering.capacity == limit_number, "capacity 必须是来源原值"
        assert offering.remaining_capacity is None, "⛔ 不得 clamp 到 0"
        assert not hasattr(offering, "selected_count"), "⛔ 不得新增 selected_count"


def test_normalization_errors_do_not_echo_raw_row_values() -> None:
    """⛔ production 错误不得回显 raw row 取值（含 `classNumber` / 教师姓名）。"""

    secret_class_id = "机密教学班号-0001"
    secret_course_name = "机密课程名"

    cases = [
        _raw(classNumber=""),  # classNumber 空
        _raw(classNumber=12345),  # 类型不符（会带出 raw 取值）
        _raw(courseName=secret_course_name, classNumber=[]),
        _raw(score="3学分"),  # 非法字符串数字（会带出 raw 取值）
        _raw(score=3),
        _raw(limitNumber="90"),  # 类型不符
        _raw(limitNumber=-1),
        _raw(selectedNumber=-5),
        _raw(teachingName=12345),
    ]

    for raw in cases:
        with pytest.raises(CourseDataNormalizationError) as excinfo:
            _build(raw)

        message = str(excinfo.value)

        for leaked in (secret_class_id, secret_course_name, "机密", "3学分", "12345", "-1", "-5"):
            assert leaked not in message, f"错误信息回显了 raw 取值：{leaked!r}"


def test_data_source_is_forced_to_real() -> None:
    assert _build().data_source is DataSource.REAL


def test_source_is_supplied_by_caller() -> None:
    offering = build_course_offering(
        _raw(),
        meetings=[_meeting()],
        source="mock://caller-supplied-source",
    )

    assert offering.source == "mock://caller-supplied-source"


def test_missing_teaching_name_yields_none() -> None:
    raw = _raw()
    del raw["teachingName"]

    assert _build(raw).teacher is None


def test_explicit_null_teaching_name_yields_none() -> None:
    assert _build(_raw(teachingName=None)).teacher is None


def test_multiple_meetings_are_preserved() -> None:
    """多段 meeting 不得丢失（G9 的核心）。"""

    meetings = [
        _meeting(weekday=3, start_section=3, end_section=4, weeks=[1, 2, 3]),
        _meeting(
            weekday=1,
            start_section=5,
            end_section=6,
            weeks=[1, 3, 5],
            campus="东校园",
            classroom="东B307",
        ),
    ]

    offering = _build(meetings=meetings)

    assert [item.weekday for item in offering.meetings] == [3, 1]
    assert offering.meetings[1].weeks == [1, 3, 5]
    assert offering.meetings[1].classroom == "东B307"


def test_output_passes_course_offering_model_validation() -> None:
    """输出必须能再次通过公共 Pydantic 模型校验。"""

    offering = _build()

    assert isinstance(offering, CourseOffering)
    CourseOffering.model_validate(offering.model_dump())


# ---------------------------------------------------------------------------
# 缺字段 / 非法值一律失败
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        "courseNum",
        "courseName",
        "classNumber",
        "yearTerm",
        "score",
        "limitNumber",
        "selectedNumber",
    ],
)
def test_missing_required_raw_field_is_rejected(missing: str) -> None:
    raw = _raw()
    del raw[missing]

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _build(raw)

    assert missing in str(excinfo.value)


@pytest.mark.parametrize("score", ["abc", "", "   ", "-1", "3.5.1", "3学分", True, None, [3], 3, 3.0])
def test_invalid_score_is_rejected(score: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        _build(_raw(score=score))


@pytest.mark.parametrize("score", [3, 3.0])
def test_numeric_score_is_rejected_without_evidence(score: object) -> None:
    """⛔ **数值型 `score` 尚无真实来源证据，因此当前拒绝**。

    `docs/data/SYSU_COURSE_OFFERING_RECON.md` 只确认了"`score` 是**字符串数字**"。
    接受 `3` / `3.0` 会让实现能力超过真实证据，所以本轮一律拒绝；
    若后续脱敏真实样本显示 `score` 也可能是 JSON number，再据实放宽。
    """

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _build(_raw(score=score))

    assert "字符串" in str(excinfo.value)


@pytest.mark.parametrize("value", [-1, "90", 90.0, True, None])
def test_invalid_limit_number_is_rejected(value: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        _build(_raw(limitNumber=value))


def test_empty_meetings_is_rejected() -> None:
    """⛔ **普通路径**（DG-07B 后仍然）拒绝任意空 `meetings`。

    空数组只有一条窄路径可以产生：`build_course_offering_from_missing_schedule_field()`，
    且要求 Raw row **真的没有** `teachingTimePlaceStr` 这个 key。
    """

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _build(meetings=[])

    assert "meetings" in str(excinfo.value)


# ---------------------------------------------------------------------------
# DG-07B：窄语义 missing-schedule 路径（只有 key 真不存在才放行）
# ---------------------------------------------------------------------------


def _build_missing_schedule(raw: dict[str, object] | None = None):
    return build_course_offering_from_missing_schedule_field(
        raw if raw is not None else _raw(),
        source="mock://course-data-normalization-test",
    )


def test_missing_schedule_field_produces_empty_meetings() -> None:
    """A. raw **不含** `teachingTimePlaceStr` → 窄路径成功，`meetings == []`。"""

    raw = _raw()  # `_raw()` 本身就不含 teachingTimePlaceStr
    assert "teachingTimePlaceStr" not in raw

    offering = _build_missing_schedule(raw)

    assert offering.meetings == []
    assert offering.data_source is DataSource.REAL
    assert offering.source == "mock://course-data-normalization-test"


def test_missing_schedule_path_keeps_other_field_mapping_identical() -> None:
    """窄路径与普通路径的**其它字段映射完全一致**（共用同一份字段构造）。"""

    raw = _raw()
    empty_path = _build_missing_schedule(raw)
    normal_path = _build(raw, meetings=[_meeting()])

    for field in (
        "course_id",
        "course_name",
        "class_id",
        "semester",
        "teacher",
        "credit",
        "capacity",
        "remaining_capacity",
        "source",
        "data_source",
    ):
        assert getattr(empty_path, field) == getattr(normal_path, field), field


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", 42, 3.5, True, {}, [], {"segment": "x"}],
    ids=["null", "empty-string", "blank-string", "number", "float", "boolean", "object", "list", "dict"],
)
def test_missing_schedule_path_rejects_present_field_whatever_the_value(value: object) -> None:
    """B–E. **字段存在**（无论取值是什么）→ 窄路径必须拒绝。

    `None` / `""` / `"   "` / 数字 / 对象 / 列表 **一律**不走 empty path；
    它们属于"字段存在但（可能）无法解析"，必须回普通 parser 路径并整体失败。
    """

    raw = _raw(teachingTimePlaceStr=value)

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _build_missing_schedule(raw)

    message = str(excinfo.value)
    assert "teachingTimePlaceStr" in message
    # ⛔ 错误信息不回显取值（可能含真实教师 / 教室文本）。
    if isinstance(value, str) and value.strip():
        assert value not in message


def test_missing_schedule_path_rejects_present_valid_text() -> None:
    """F. 字段存在且是**合法** schedule 文本 → 也**不得**走 empty path。"""

    raw = _raw(teachingTimePlaceStr="1-8周/星期五/第5-6节/示例教师A/示例环节,")

    with pytest.raises(CourseDataNormalizationError):
        _build_missing_schedule(raw)


@pytest.mark.parametrize("source", ["", "   ", None, 123])
def test_missing_schedule_path_still_validates_source(source: object) -> None:
    """窄路径同样要求调用方**显式提供**合法 `source`。"""

    with pytest.raises(CourseDataNormalizationError):
        build_course_offering_from_missing_schedule_field(_raw(), source=source)


@pytest.mark.parametrize("missing", ["courseNum", "courseName", "classNumber", "yearTerm", "score"])
def test_missing_schedule_path_still_requires_base_fields(missing: str) -> None:
    """窄路径**不放松**基础字段要求：缺基础字段仍失败。"""

    raw = _raw()
    del raw[missing]

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _build_missing_schedule(raw)

    assert missing in str(excinfo.value)


def test_missing_schedule_path_rejects_non_mapping_raw() -> None:
    with pytest.raises(CourseDataNormalizationError):
        build_course_offering_from_missing_schedule_field(  # type: ignore[arg-type]
            "not-a-mapping", source="mock://course-data-normalization-test"
        )


def test_unparsed_meeting_dict_is_rejected() -> None:
    """本轮 `meetings` 只能由**已经解析好的** `Meeting` 传入。

    传原始 dict 意味着调用方已经开始猜 `teachingTimePlaceStr`，
    而标准化层**故意不做解析**。
    """

    with pytest.raises(CourseDataNormalizationError):
        build_course_offering(
            _raw(),
            meetings=[{"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1]}],
            source="mock://course-data-normalization-test",
        )


@pytest.mark.parametrize("source", ["", "   ", None, 123])
def test_invalid_source_is_rejected(source: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        build_course_offering(_raw(), meetings=[_meeting()], source=source)


# ---------------------------------------------------------------------------
# 周次：Phase 2B-2B 依据**脱敏真实样本**重新界定
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1-5周", [1, 2, 3, 4, 5]),
        ("1-6周", [1, 2, 3, 4, 5, 6]),
        ("1-8周", [1, 2, 3, 4, 5, 6, 7, 8]),
        ("7-8周", [7, 8]),
        ("10-17周", list(range(10, 18))),
        ("1-17周", list(range(1, 18))),
    ],
)
def test_observed_plain_week_ranges_are_expanded(text: str, expected: list[int]) -> None:
    """✅ 普通连续周次 `N-M周`（脱敏样本中已观察到多种范围）。"""

    assert expand_weeks(text) == expected


def test_observed_degenerate_week_range_is_expanded() -> None:
    """✅ **`6-6周` 真实存在**，必须合法并展开为 `[6]`（`M == N`）。"""

    assert expand_weeks("6-6周") == [6]


def test_observed_odd_week_text_is_expanded() -> None:
    """✅ `1-17单周` —— 单周只允许这一个已观察取值。"""

    assert expand_weeks("1-17单周") == [1, 3, 5, 7, 9, 11, 13, 15, 17]


@pytest.mark.parametrize("text", ["3-15单周", "1-5单周", "10-17单周"])
def test_unobserved_odd_week_ranges_are_rejected(text: str) -> None:
    """⛔ 单周**不泛化**为任意 `N-M单周`：只接受已观察到的 `1-17单周`。"""

    with pytest.raises(CourseDataNormalizationError):
        expand_weeks(text)


@pytest.mark.parametrize("text", ["17-1周", "0-17周", "5-3周"])
def test_invalid_plain_week_range_is_rejected(text: str) -> None:
    """⛔ `N < 1` 或 `M < N` 的区间非法。"""

    with pytest.raises(CourseDataNormalizationError):
        expand_weeks(text)


@pytest.mark.parametrize(
    "text",
    [
        "1-17双周",  # 双周：未确认
        "1,3,5周",  # 逗号组合：未确认
        "1-17周,3-4单周",  # 多段组合：未确认
        "5周",  # 单个周次号：未确认
        "1-17",  # 缺"周"字
        "第1-17周",  # 带前缀
        "1~17周",  # 波浪号
        "１-１７周",  # 全角数字：未确认
        "",  # 空
        "   ",  # 全空白
    ],
)
def test_unconfirmed_week_formats_are_rejected(text: str) -> None:
    """未确认格式一律拒绝 —— **绝不猜**。"""

    with pytest.raises(CourseDataNormalizationError):
        expand_weeks(text)


@pytest.mark.parametrize("value", [None, 17, ["1-17周"], {"weeks": "1-17周"}])
def test_non_string_weeks_input_is_rejected(value: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        expand_weeks(value)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 本轮**明确不做**的映射
# ---------------------------------------------------------------------------


def test_internal_ids_never_enter_course_offering() -> None:
    """内部长 ID **只记录存在**，不得进入 `CourseOffering`。"""

    raw = _raw(
        courseId="999999999999999999",
        class_ID="888888888888888888",
        sumClassesID="777",
        sumClassesNum=3,
        outLineId="666",
        timePlaceId="555",
        # 公共标识必须仍然取自 courseNum / classNumber
    )

    offering = _build(raw)
    dumped = offering.model_dump()

    assert offering.course_id == "62001001"
    assert offering.class_id == "6200100120260101"
    assert offering.course_id != raw["courseId"]
    assert offering.class_id != raw["class_ID"]

    assert set(dumped) == set(CourseOffering.model_fields)
    for forbidden in _INTERNAL_ID_FIELDS:
        assert forbidden not in dumped


def test_deferred_business_fields_never_enter_course_offering() -> None:
    """暂缓字段不进入公共契约（D5 其余字段一律不映射）。"""

    raw = _raw(
        courseCategoryName="专必",
        openingUnitName="示例开课单位",
        examMode="闭卷",
        readObj="示例修读对象",
        teachProgressSubmitState="9",
        openClass="9",
        outlineTypeNum=1,
    )

    dumped = _build(raw).model_dump()

    for forbidden in _BUSINESS_DEFERRED_FIELDS:
        assert forbidden not in dumped


def test_week_day_is_not_auto_mapped_to_meeting_weekday() -> None:
    """⛔ `weekDay → Meeting.weekday` 属 C11 待确认项，本轮**绝不做**。

    这里故意把 `weekDay` 设成一个**非法值 9**：
    如果实现里偷偷读了它，要么结果变成 9（被断言抓到），要么直接报错。
    """

    raw = _raw(weekDay=9)
    meetings = [_meeting(weekday=3)]

    offering = _build(raw, meetings=meetings)

    assert offering.meetings[0].weekday == 3


def test_opening_school_name_is_not_auto_mapped_to_campus() -> None:
    """⛔ `openingSchoolName → Meeting.campus` 属 C11 待确认项，本轮**绝不做**。"""

    raw = _raw(openingSchoolName="南校园")
    meetings = [_meeting(campus="东校园")]

    offering = _build(raw, meetings=meetings)

    assert offering.meetings[0].campus == "东校园"


#: 占位值：**不携带任何格式假设**（不假装知道真实 SYSU 的上课时间地点串长什么样）。
#: 真实格式需取得脱敏样本后另行确认。
UNPARSED_SCHEDULE_TEXT = "UNPARSED_SCHEDULE_TEXT"


def test_raw_schedule_string_is_not_parsed() -> None:
    """⛔ `teachingTimePlaceStr` 本轮**不解析**（无真实脱敏 Raw string，不猜分隔符）。

    这里刻意使用**不含任何格式假设**的占位值：
    传了它也不会产生任何 `Meeting` —— meeting 只能由调用方显式传入。
    """

    raw = _raw(teachingTimePlaceStr=UNPARSED_SCHEDULE_TEXT)
    meetings = [_meeting(weekday=1)]

    offering = _build(raw, meetings=meetings)

    assert len(offering.meetings) == 1
    assert offering.meetings[0].weekday == 1


def test_forbidden_fields_alone_cannot_construct_an_offering() -> None:
    """只给内部 ID / 暂缓字段、不给已确认字段时，必须失败而不是"尽力而为"。"""

    with pytest.raises(CourseDataNormalizationError):
        build_course_offering(
            {"courseId": "999", "class_ID": "888", "courseCategoryName": "专必"},
            meetings=[_meeting()],
            source="mock://course-data-normalization-test",
        )
