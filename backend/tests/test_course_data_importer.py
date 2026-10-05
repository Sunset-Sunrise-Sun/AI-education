"""Raw-response import adapter 测试（Phase 2B-2B，纯本地、零网络）。

⚠️ **数据最小化**：本文件中的 Raw response **全部为人工虚构**的结构等价样本；
**不包含**私密脱敏样本原文、真实教师姓名、真实教室、`readObj`、内部长 ID **取值**、
Raw JSON、Cookie / Session / Token。

覆盖重点：response 形状校验、整体失败（不跳过坏 row）、顺序保留、
completeness **由调用方决定**（Adapter 不猜）、以及"不使用 `weekDay` / `openingSchoolName`"。
"""

from __future__ import annotations

import pytest

from app.course_data import (
    CourseDataNormalizationError,
    OfferingSnapshot,
    import_opening_courses_response,
)
from app.models.contracts import DataSource

SEMESTER = "2026-1"
SOURCE = "mock://course-data-importer-test"
TEACHER_A = "示例教师A"
ACTIVITY = "示例环节"

#: 5 字段（无地点）+ 末尾逗号。
SCHEDULE_NO_LOCATION = f"1-8周/星期五/第5-6节/{TEACHER_A}/{ACTIVITY},"
#: 6 字段（有地点）+ 末尾逗号。
SCHEDULE_WITH_LOCATION = (
    f"1-5周/星期五/第3-4节/示例校区-示例教学楼-2108/{TEACHER_A}/{ACTIVITY},"
)


def _row(**overrides: object) -> dict[str, object]:
    """一条**人工虚构**的 Raw row（键名对齐已确认字段）。"""

    row: dict[str, object] = {
        "courseNum": "62001001",
        "courseName": "离散数学",
        "classNumber": "6200100120260101",
        "yearTerm": SEMESTER,
        "score": "3",
        "teachingName": TEACHER_A,
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": SCHEDULE_NO_LOCATION,
        # 以下字段**必须被完全忽略**（内部 ID / 未确认映射 / 暂缓字段）：
        "courseId": "100000000000000001",
        "class_ID": "200000000000000002",
        "weekDay": "星期六",  # ⛔ 不得作为 Meeting.weekday 来源
        "openingSchoolName": "别的校区",  # ⛔ 不得作为 Meeting.campus 来源
        "courseCategoryName": "示例类别",
        "readObj": "示例修读对象",
    }
    row.update(overrides)
    return row


def _payload(rows: list[dict[str, object]], *, total: int | None = None, code: int = 200) -> dict:
    return {
        "code": code,
        "data": {
            "total": len(rows) if total is None else total,
            "rows": rows,
        },
    }


def _import(
    rows: list[dict[str, object]],
    *,
    total: int | None = None,
    completeness: str = "partial",
    payload: dict | None = None,
) -> OfferingSnapshot:
    """按需构造 Raw response 并调用 adapter。

    `payload` 显式给出时优先使用它（用于构造畸形响应）；否则由 `rows` / `total` 组装。
    """

    return import_opening_courses_response(
        payload if payload is not None else _payload(rows, total=total),
        semester=SEMESTER,
        source=SOURCE,
        completeness=completeness,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 正常流程
# ---------------------------------------------------------------------------


def test_valid_partial_response() -> None:
    snapshot = _import([_row(), _row(classNumber="6200100120260102")], total=40)

    assert isinstance(snapshot, OfferingSnapshot)
    assert snapshot.semester == SEMESTER
    assert snapshot.completeness == "partial"
    assert snapshot.reported_total == 40
    assert snapshot.loaded_count == 2


def test_valid_complete_response() -> None:
    snapshot = _import([_row()], completeness="complete")

    assert snapshot.is_complete is True
    assert snapshot.reported_total == 1


def test_rows_preserve_original_order() -> None:
    rows = [
        _row(classNumber="6200100120260103"),
        _row(classNumber="6200100120260101"),
        _row(classNumber="6200100120260102"),
    ]

    snapshot = _import(rows)

    assert [item.class_id for item in snapshot.offerings] == [
        "6200100120260103",
        "6200100120260101",
        "6200100120260102",
    ]


def test_same_course_with_different_class_ids_is_preserved() -> None:
    snapshot = _import(
        [
            _row(classNumber="6200100120260101"),
            _row(classNumber="6200100120260102"),
        ]
    )

    assert {item.class_id for item in snapshot.offerings} == {
        "6200100120260101",
        "6200100120260102",
    }


def test_data_source_is_real_and_source_is_preserved() -> None:
    snapshot = _import([_row()])

    offering = snapshot.offerings[0]
    assert offering.data_source is DataSource.REAL
    assert offering.source == SOURCE


# ---------------------------------------------------------------------------
# non-concrete schedule（2026-1 真实证据新增）
# ---------------------------------------------------------------------------


def test_non_concrete_only_schedule_produces_empty_meetings() -> None:
    """`12-19周校外/实验实践环节`（见习类课程）→ `meetings == []`，row 不被跳过。

    ⚠️ 语义：**有课程安排信息，但不足以确定时间冲突**（没有 weekday / sections /
    具体地点），由现有 **DG-07** 承接为 **schedule UNKNOWN**。
    ⛔ 这与"字段不存在"是**两条不同路径**，但都产出 `meetings == []`。
    """

    snapshot = _import([_row(teachingTimePlaceStr="12-19周校外/实验实践环节")], total=1)

    assert snapshot.loaded_count == 1
    assert snapshot.offerings[0].meetings == []
    assert snapshot.offerings[0].data_source is DataSource.REAL


def test_non_concrete_with_concrete_in_same_snapshot_keeps_both_rows() -> None:
    """混合：concrete row + non-concrete row → 两条都保留（⛔ 不丢 row）。"""

    snapshot = _import(
        [
            _row(classNumber="6200100120260101"),
            _row(
                classNumber="6200100120260102",
                teachingTimePlaceStr="12-19周校外/实验实践环节",
            ),
        ],
        total=2,
    )

    assert snapshot.loaded_count == 2
    assert len(snapshot.offerings[0].meetings) >= 1
    assert snapshot.offerings[1].meetings == []


def test_malformed_schedule_still_fails_whole_import() -> None:
    """⛔ non-concrete 支持**不得**放宽"解析失败"：未知 2 字段仍整体失败。"""

    with pytest.raises(CourseDataNormalizationError):
        _import([_row(teachingTimePlaceStr="12-19周未知词/实验实践环节")], total=1)


def test_multiple_segments_are_all_kept() -> None:
    multi = (
        f"1-5周/星期五/第3-4节/示例校区-示例教学楼-2108/{TEACHER_A}/{ACTIVITY},"
        f"10-17周/星期一/第1-2节/示例校区-示例教学楼-2109/{TEACHER_A}/{ACTIVITY},"
    )

    snapshot = _import([_row(teachingTimePlaceStr=multi)])

    meetings = snapshot.offerings[0].meetings
    assert len(meetings) == 2
    assert [item.weekday for item in meetings] == [5, 1]


def test_week_day_field_is_never_used_for_weekday() -> None:
    """⛔ Raw `weekDay` 完全不参与 `Meeting.weekday`。

    row 里 `weekDay` 故意写成"星期六"，而 segment 自带"星期五"；
    结果必须是 **5**（来自 segment），不是 6。
    """

    snapshot = _import([_row(weekDay="星期六")])

    assert snapshot.offerings[0].meetings[0].weekday == 5


def test_opening_school_name_is_never_used_for_campus() -> None:
    """⛔ `openingSchoolName` 仍然**不是** `campus` 的 fallback。"""

    without_location = _import([_row(openingSchoolName="别的校区")])
    assert without_location.offerings[0].meetings[0].campus is None

    with_location = _import(
        [_row(teachingTimePlaceStr=SCHEDULE_WITH_LOCATION, openingSchoolName="别的校区")]
    )
    assert with_location.offerings[0].meetings[0].campus == "示例校区"


def test_internal_ids_and_deferred_fields_do_not_leak_into_offering() -> None:
    snapshot = _import([_row()])

    dumped = snapshot.offerings[0].model_dump()

    for forbidden in (
        "courseId",
        "class_ID",
        "weekDay",
        "openingSchoolName",
        "courseCategoryName",
        "readObj",
    ):
        assert forbidden not in dumped

    assert dumped["course_id"] == "62001001"
    assert dumped["class_id"] == "6200100120260101"


# ---------------------------------------------------------------------------
# Response 形状校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [0, 500, 404, 201])
def test_non_success_code_is_rejected(code: int) -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload=_payload([_row()], code=code))


def test_missing_code_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"data": {"total": 1, "rows": [_row()]}})


def test_non_integer_code_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": "200", "data": {"total": 1, "rows": [_row()]}})


def test_missing_data_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": 200})


def test_non_mapping_data_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": 200, "data": [_row()]})


@pytest.mark.parametrize("total", ["3", 3.0, True, None, -1])
def test_invalid_total_is_rejected(total: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": 200, "data": {"total": total, "rows": [_row()]}})


def test_missing_total_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": 200, "data": {"rows": [_row()]}})


@pytest.mark.parametrize("rows", ["not-a-list", 5, {"0": _row()}, None])
def test_rows_not_a_sequence_is_rejected(rows: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": 200, "data": {"total": 1, "rows": rows}})


def test_missing_rows_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": 200, "data": {"total": 1}})


def test_non_mapping_row_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], payload={"code": 200, "data": {"total": 1, "rows": ["row"]}})


def test_non_mapping_payload_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        import_opening_courses_response(
            ["not", "a", "mapping"],  # type: ignore[arg-type]
            semester=SEMESTER,
            source=SOURCE,
            completeness="partial",
        )


# ---------------------------------------------------------------------------
# 坏 row：整体失败，不静默跳过
# ---------------------------------------------------------------------------


def test_missing_schedule_field_produces_empty_meetings() -> None:
    """DG-07B：单 row **真的没有** `teachingTimePlaceStr` → import 成功且 `meetings == []`。

    ⚠️ 这是"来源快照没有可用排课信息"，**不是**学校业务状态；row **不被跳过**。
    """

    row = _row()
    del row["teachingTimePlaceStr"]
    assert "teachingTimePlaceStr" not in row

    snapshot = _import([row], total=1)

    assert snapshot.loaded_count == 1
    assert len(snapshot.offerings) == 1
    assert snapshot.offerings[0].meetings == []
    assert snapshot.offerings[0].data_source is DataSource.REAL


def test_missing_schedule_row_is_kept_in_order_and_counted() -> None:
    """normal / missing / normal：**三条全部保留**、**顺序不变**、`loaded_count == 3`。

    ⛔ 缺排课信息的 row **不得被跳过**：否则 completeness 会被破坏。
    """

    missing = _row(classNumber="6200100120260102")
    del missing["teachingTimePlaceStr"]

    snapshot = _import(
        [
            _row(classNumber="6200100120260101"),
            missing,
            _row(classNumber="6200100120260103"),
        ],
        total=3,
        completeness="complete",
    )

    assert snapshot.loaded_count == 3
    assert [item.class_id for item in snapshot.offerings] == [
        "6200100120260101",
        "6200100120260102",
        "6200100120260103",
    ]
    assert snapshot.offerings[0].meetings != []
    assert snapshot.offerings[1].meetings == []
    assert snapshot.offerings[2].meetings != []
    assert snapshot.completeness == "complete"


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", 42, 3.5, True, {"a": 1}, ["x"]],
    ids=["null", "empty-string", "blank-string", "number", "float", "boolean", "object", "list"],
)
def test_present_schedule_field_with_unusable_value_is_rejected(value: object) -> None:
    """⛔ 字段**存在**但取值不可用（含 `null` / 空串 / 其它类型）→ **整体失败**。

    这些属于"字段存在但无可用排课信息（或类型不对）"，**不**等于"属性不存在"，
    因此**一律不得**转成 `meetings = []`。
    """

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _import([_row(teachingTimePlaceStr=value)])

    assert "teachingTimePlaceStr" in str(excinfo.value)


def test_present_schedule_field_with_malformed_text_is_rejected() -> None:
    """⛔ 非空但 malformed → **整体失败**（parser 原样抛错）。"""

    with pytest.raises(CourseDataNormalizationError):
        _import([_row(teachingTimePlaceStr="只有一段没有分隔符的文本")])

    with pytest.raises(CourseDataNormalizationError):
        _import([_row(teachingTimePlaceStr="1-8周/星期五/第5-6节,")])  # 字段数不足


def test_parser_exception_is_never_converted_into_empty_meetings() -> None:
    """⛔ importer **没有** `except -> meetings=[]`：解析失败必须整体失败。

    反向证明：同一批数据里混入一条 malformed row 时，**整批**失败，
    不会产出"部分成功 + 空 meetings"的结果。
    """

    good = _row(classNumber="6200100120260101")
    bad = _row(classNumber="6200100120260102", teachingTimePlaceStr="坏格式")

    with pytest.raises(CourseDataNormalizationError):
        _import([good, bad], total=2)


def test_bad_row_fails_the_entire_import() -> None:
    """⛔ 任意一行失败 → 本次 import 整体失败（**不跳过坏 row、不返回部分结果**）。"""

    good = _row(classNumber="6200100120260101")
    bad = _row(classNumber="6200100120260102", teachingTimePlaceStr="不是合法格式")

    with pytest.raises(CourseDataNormalizationError):
        _import([good, bad, _row(classNumber="6200100120260103")])


def test_bad_row_after_good_rows_still_fails() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row(), _row(classNumber="6200100120260102", limitNumber=-1)])


def test_unparsable_schedule_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row(teachingTimePlaceStr="只有一段没有分隔符的文本")])


def test_missing_required_raw_field_is_rejected() -> None:
    row = _row()
    del row["courseNum"]

    with pytest.raises(CourseDataNormalizationError):
        _import([row])


# ---------------------------------------------------------------------------
# completeness / 一致性：交由 OfferingSnapshot 判定，Adapter 不猜
# ---------------------------------------------------------------------------


def test_snapshot_rules_are_delegated_not_reimplemented() -> None:
    """Adapter **不**因为 `len(rows) == total` 就自己宣布 complete。

    这里 `len(rows) == total == 2`，但调用方给的是 `partial` → 结果必须是 `partial`。
    """

    snapshot = _import(
        [_row(), _row(classNumber="6200100120260102")],
        completeness="partial",
    )

    assert snapshot.reported_total == 2
    assert snapshot.loaded_count == 2
    assert snapshot.is_complete is False


def test_complete_with_rows_not_equal_to_total_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import(
            [_row(), _row(classNumber="6200100120260102")],
            total=5,
            completeness="complete",
        )


def test_partial_with_total_not_smaller_than_loaded_passes() -> None:
    snapshot = _import([_row()], total=10, completeness="partial")

    assert snapshot.is_complete is False
    assert snapshot.reported_total == 10


def test_partial_with_total_smaller_than_loaded_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import(
            [_row(), _row(classNumber="6200100120260102")],
            total=1,
            completeness="partial",
        )


def test_semester_mismatch_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row(yearTerm="2026-2")])


def test_duplicate_class_key_is_rejected() -> None:
    """判重规则由 `OfferingSnapshot` 负责；Adapter 不重复实现，但必须让它生效。"""

    duplicate = _row()

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _import([duplicate, dict(duplicate)])

    assert "重复" in str(excinfo.value)


def test_invalid_completeness_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([_row()], completeness="mostly")


def test_empty_rows_with_partial_is_allowed() -> None:
    snapshot = _import([], total=0, completeness="partial")

    assert snapshot.loaded_count == 0
    assert snapshot.is_complete is False


@pytest.mark.parametrize("source", ["", "   ", None, 123])
def test_invalid_source_is_rejected_even_with_empty_rows(source: object) -> None:
    """⛔ **空 rows 也必须校验 source**。

    否则 `rows == []` 时不会调用 `build_course_offering()`，
    非法 source 会被静默放过（"空数据 + 非法来源"不应算成功）。
    """

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        import_opening_courses_response(
            _payload([]),
            semester=SEMESTER,
            source=source,  # type: ignore[arg-type]
            completeness="partial",
        )

    assert "source" in str(excinfo.value)


@pytest.mark.parametrize("source", ["", "   ", None, 123])
def test_invalid_source_is_rejected_with_non_empty_rows(source: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        import_opening_courses_response(
            _payload([_row()]),
            semester=SEMESTER,
            source=source,  # type: ignore[arg-type]
            completeness="partial",
        )


def test_empty_rows_with_complete_is_allowed_when_total_is_zero() -> None:
    snapshot = _import([], total=0, completeness="complete")

    assert snapshot.is_complete is True


def test_empty_rows_with_complete_and_nonzero_total_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        _import([], total=3, completeness="complete")


# ---------------------------------------------------------------------------
# 无 Mock fallback
# ---------------------------------------------------------------------------


def test_importer_has_no_mock_fallback() -> None:
    """Adapter 不引用任何 Mock 通道，也不会在解析失败时回退。"""

    import app.course_data.importer as importer_module

    offenders = [name for name in vars(importer_module) if "mock" in name.lower()]
    assert not offenders, f"importer 模块出现 Mock 相关名字：{offenders}"

    snapshot = _import([_row()])
    assert all(item.data_source is DataSource.REAL for item in snapshot.offerings)
