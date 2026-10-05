"""Course Data 本地持久化层（SQLite）测试（**纯 synthetic、零网络、零真实数据**）。

覆盖 Architecture Review 要求的全部条目：

```text
complete snapshot import success
partial snapshot rejected
duplicate import idempotent
same course different class_id preserved
semester isolation
course_ids filter
meetings round-trip
provenance fields round-trip
malformed DB / path fail clearly
```

⚠️ 所有 course_id / 课程名 / 教学班号 / 教室均为**人工虚构**；
⛔ 不导入任何真实数据、⛔ 不读取任何 Capture Bundle。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.course_data import (
    CourseDataNormalizationError,
    CourseDataStoreError,
    OfferingSnapshot,
    compute_artifact_sha256,
    import_offering_snapshot,
    initialize_course_data_store,
    load_course_data_provenance,
    load_course_offerings,
)
from app.models.contracts import CourseOffering, DataSource, Meeting

SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
ARTIFACT = compute_artifact_sha256(b"synthetic-artifact-bytes")
OTHER_ARTIFACT = compute_artifact_sha256(b"another-synthetic-artifact")
SOURCE = "capture-set://synthetic/2026-1/shards"


# ---------------------------------------------------------------------------
# synthetic fixtures
# ---------------------------------------------------------------------------


def _meeting(
    weekday: int = 1,
    start_section: int = 1,
    end_section: int = 2,
    weeks: tuple[int, ...] = (1, 2, 3),
    *,
    campus: str | None = None,
    classroom: str | None = None,
) -> Meeting:
    return Meeting(
        weekday=weekday,
        start_section=start_section,
        end_section=end_section,
        weeks=list(weeks),
        campus=campus,
        classroom=classroom,
    )


def _offering(
    course_id: str = "SYN-0001",
    class_id: str = "01",
    *,
    semester: str = SEMESTER,
    course_name: str = "示例课程",
    teacher: str | None = None,
    credit: float | None = 3.0,
    meetings: list[Meeting] | None = None,
    capacity: int | None = 90,
    remaining_capacity: int | None = 12,
    source: str | None = SOURCE,
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=course_name,
        class_id=class_id,
        semester=semester,
        teacher=teacher,
        credit=credit,
        meetings=[_meeting()] if meetings is None else meetings,
        capacity=capacity,
        remaining_capacity=remaining_capacity,
        source=source,
        data_source=DataSource.REAL,
    )


def _snapshot(
    offerings: list[CourseOffering],
    *,
    semester: str = SEMESTER,
    completeness: str = "complete",
    reported_total: int | None = None,
) -> OfferingSnapshot:
    if reported_total is None:
        reported_total = len(offerings) if completeness == "complete" else None

    return OfferingSnapshot(
        semester=semester,
        offerings=tuple(offerings),
        completeness=completeness,  # type: ignore[arg-type]
        reported_total=reported_total,
    )


@pytest.fixture()
def store_path(tmp_path: Path) -> Path:
    path = tmp_path / "course_data.sqlite3"
    initialize_course_data_store(path)
    return path


def _raw_rows(path: Path) -> list[sqlite3.Row]:
    """直接读库（**测试专用**：验证 schema 级事实，不走公开 API）。"""

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute("SELECT * FROM course_offering").fetchall()
    finally:
        connection.close()


def _column_names(path: Path, table: str) -> list[str]:
    connection = sqlite3.connect(str(path))
    try:
        return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# 1. 建立 / 导入 complete 快照
# ---------------------------------------------------------------------------


def test_initialize_creates_store_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "course_data.sqlite3"

    resolved = initialize_course_data_store(path)

    assert resolved == path
    assert path.is_file()
    assert _column_names(path, "course_offering")
    assert _column_names(path, "course_data_import")

    # 再次初始化：不重建、不清空
    assert initialize_course_data_store(path) == path
    assert load_course_offerings(path, SEMESTER) == []


def test_import_complete_snapshot_round_trips_public_fields(store_path: Path) -> None:
    snapshot = _snapshot(
        [
            _offering(
                course_id="SYN-0001",
                class_id="01",
                course_name="示例课程甲",
                teacher="REDACTED",
                credit=2.5,
                capacity=80,
                remaining_capacity=7,
                meetings=[
                    _meeting(1, 1, 2, (1, 2, 3, 4), campus="示例校区", classroom="示例教学楼-210"),
                    _meeting(3, 5, 6, (2, 4, 6)),
                ],
            )
        ]
    )

    result = import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)

    assert (result.inserted, result.updated, result.unchanged) == (1, 0, 0)
    assert result.already_imported is False
    assert result.semester == SEMESTER
    assert result.artifact_sha256 == ARTIFACT

    loaded = load_course_offerings(store_path, SEMESTER)

    assert loaded == list(snapshot.offerings)


def test_import_records_artifact_provenance(store_path: Path) -> None:
    snapshot = _snapshot([_offering()])

    result = import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)
    records = load_course_data_provenance(store_path)

    assert len(records) == 1
    record = records[0]

    assert record.artifact_sha256 == ARTIFACT
    assert record.semester == SEMESTER
    assert record.source == SOURCE
    assert record.completeness == "complete"
    assert record.loaded_count == 1
    assert record.reported_total == 1
    assert record.offering_count == 1
    assert record.imported_at == result.imported_at

    parsed = datetime.fromisoformat(record.imported_at)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


def test_row_level_provenance_columns_are_written(store_path: Path) -> None:
    snapshot = _snapshot([_offering()])
    import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT.upper())

    rows = _raw_rows(store_path)

    assert len(rows) == 1
    assert rows[0]["artifact_sha256"] == ARTIFACT, "十六进制大小写应归一化"
    assert rows[0]["source"] == SOURCE
    assert rows[0]["data_source"] == "real"
    assert datetime.fromisoformat(rows[0]["imported_at"]).tzinfo is not None


def test_import_across_semesters_keeps_one_record_per_artifact(store_path: Path) -> None:
    import_offering_snapshot(
        store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT
    )
    import_offering_snapshot(
        store_path,
        _snapshot([_offering(semester=OTHER_SEMESTER)], semester=OTHER_SEMESTER),
        artifact_sha256=ARTIFACT,
    )

    assert len(load_course_data_provenance(store_path)) == 2
    assert len(load_course_data_provenance(store_path, semester=OTHER_SEMESTER)) == 1


# ---------------------------------------------------------------------------
# 2. completeness：partial 一律拒绝（本层不判断完整性）
# ---------------------------------------------------------------------------


def test_partial_snapshot_is_rejected(store_path: Path) -> None:
    partial = _snapshot([_offering()], completeness="partial")

    with pytest.raises(CourseDataStoreError) as excinfo:
        import_offering_snapshot(store_path, partial, artifact_sha256=ARTIFACT)

    assert "complete" in str(excinfo.value)
    assert "approved" in str(excinfo.value)


def test_rejected_partial_snapshot_writes_nothing(store_path: Path) -> None:
    partial = _snapshot([_offering()], completeness="partial")

    with pytest.raises(CourseDataStoreError):
        import_offering_snapshot(store_path, partial, artifact_sha256=ARTIFACT)

    assert _raw_rows(store_path) == []
    assert load_course_data_provenance(store_path) == []


def test_store_does_not_claim_completeness_by_itself(store_path: Path) -> None:
    """⛔ 库里不得出现任何"自封完整"的列 / 表。"""

    for table in ("course_offering", "course_data_import"):
        for column in _column_names(store_path, table):
            assert column not in ("complete", "is_complete", "claimed_complete")

    # 导入记录只**如实转述**上游的 completeness 值
    import_offering_snapshot(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)
    assert load_course_data_provenance(store_path)[0].completeness == "complete"


# ---------------------------------------------------------------------------
# 3. identity / upsert
# ---------------------------------------------------------------------------


def test_duplicate_import_of_same_artifact_is_idempotent(store_path: Path) -> None:
    snapshot = _snapshot([_offering(course_id="SYN-1"), _offering(course_id="SYN-2")])

    first = import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)
    before = load_course_offerings(store_path, SEMESTER)

    second = import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)
    after = load_course_offerings(store_path, SEMESTER)

    assert (first.inserted, first.already_imported) == (2, False)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 2)
    assert second.already_imported is True
    assert after == before
    assert len(_raw_rows(store_path)) == 2, "重复导入不得产生新行"
    assert len(load_course_data_provenance(store_path)) == 1


def test_reimport_with_changed_content_updates_in_place(store_path: Path) -> None:
    import_offering_snapshot(
        store_path, _snapshot([_offering(capacity=90)]), artifact_sha256=ARTIFACT
    )

    changed = _snapshot(
        [_offering(capacity=120, remaining_capacity=3, meetings=[_meeting(2, 3, 4)])]
    )
    result = import_offering_snapshot(store_path, changed, artifact_sha256=OTHER_ARTIFACT)

    assert (result.inserted, result.updated, result.unchanged) == (0, 1, 0)
    assert len(_raw_rows(store_path)) == 1, "identity 相同必须原地更新，不得新增行"

    reloaded = load_course_offerings(store_path, SEMESTER)[0]
    assert reloaded.capacity == 120
    assert reloaded.remaining_capacity == 3
    assert reloaded.meetings == [_meeting(2, 3, 4)]

    # provenance 跟随后一次写入
    assert _raw_rows(store_path)[0]["artifact_sha256"] == OTHER_ARTIFACT


def test_same_course_different_class_id_are_preserved(store_path: Path) -> None:
    snapshot = _snapshot(
        [
            _offering(course_id="SYN-SAME", class_id="01"),
            _offering(course_id="SYN-SAME", class_id="02"),
        ]
    )

    import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)

    loaded = load_course_offerings(store_path, SEMESTER, course_ids=["SYN-SAME"])

    assert [offering.class_id for offering in loaded] == ["01", "02"]
    assert len(_raw_rows(store_path)) == 2, "⛔ 不得按 course_id 单独覆盖不同教学班"


def test_same_identity_in_two_semesters_coexist(store_path: Path) -> None:
    import_offering_snapshot(
        store_path,
        _snapshot([_offering(course_name="甲学期课程")]),
        artifact_sha256=ARTIFACT,
    )
    import_offering_snapshot(
        store_path,
        _snapshot(
            [_offering(semester=OTHER_SEMESTER, course_name="乙学期课程")],
            semester=OTHER_SEMESTER,
        ),
        artifact_sha256=ARTIFACT,
    )

    assert [o.course_name for o in load_course_offerings(store_path, SEMESTER)] == ["甲学期课程"]
    assert [
        o.course_name for o in load_course_offerings(store_path, OTHER_SEMESTER)
    ] == ["乙学期课程"]
    assert len(_raw_rows(store_path)) == 2


# ---------------------------------------------------------------------------
# 4. 查询
# ---------------------------------------------------------------------------


def test_load_by_semester_returns_only_that_semester(store_path: Path) -> None:
    import_offering_snapshot(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)
    import_offering_snapshot(
        store_path,
        _snapshot([_offering(semester=OTHER_SEMESTER)], semester=OTHER_SEMESTER),
        artifact_sha256=ARTIFACT,
    )

    assert len(load_course_offerings(store_path, SEMESTER)) == 1
    assert load_course_offerings(store_path, "2099-9") == []


def test_load_with_course_ids_filter(store_path: Path) -> None:
    snapshot = _snapshot(
        [
            _offering(course_id="SYN-A", class_id="01"),
            _offering(course_id="SYN-A", class_id="02"),
            _offering(course_id="SYN-B", class_id="01"),
            _offering(course_id="SYN-C", class_id="01"),
        ]
    )
    import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)

    candidates = load_course_offerings(store_path, SEMESTER, course_ids=["SYN-A", "SYN-C"])

    assert [(o.course_id, o.class_id) for o in candidates] == [
        ("SYN-A", "01"),
        ("SYN-A", "02"),
        ("SYN-C", "01"),
    ]
    assert load_course_offerings(store_path, SEMESTER, course_ids=["SYN-Z"]) == []


def test_load_without_filter_returns_all_in_deterministic_order(store_path: Path) -> None:
    snapshot = _snapshot(
        [
            _offering(course_id="SYN-B", class_id="02"),
            _offering(course_id="SYN-A", class_id="02"),
            _offering(course_id="SYN-A", class_id="01"),
        ]
    )
    import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)

    loaded = load_course_offerings(store_path, SEMESTER)

    assert [(o.course_id, o.class_id) for o in loaded] == [
        ("SYN-A", "01"),
        ("SYN-A", "02"),
        ("SYN-B", "02"),
    ]


def test_load_with_empty_course_ids_returns_empty(store_path: Path) -> None:
    import_offering_snapshot(
        store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT
    )

    assert load_course_offerings(store_path, SEMESTER, course_ids=[]) == []


def test_load_order_is_guaranteed_by_sql_not_by_the_query_plan() -> None:
    """⛔ 读回顺序必须是 **SQL 显式保证**的，而不是"SQLite 恰好按索引顺序返回"。

    ⚠️ 这是**源码级**断言（与 `backend/tests/test_sysu_collector_guard.py` 同一做法）：
    因为 `WHERE semester = ?` 会命中主键索引，去掉 `ORDER BY` 后
    SQLite **当前**的查询计划仍会返回同样的顺序 ——
    纯行为用例无法区分"有保证"和"碰巧一致"，所以这里直接锁住 SQL 子句
    （断言带上 `{where}` 占位符，确保命中的是**查询语句**而不是文档里的说明文字）。
    """

    source = Path(__file__).resolve().parents[1] / "app" / "course_data" / "store.py"
    text = source.read_text(encoding="utf-8")

    assert "WHERE {where} ORDER BY course_id, class_id" in text


def test_load_on_unimported_store_returns_empty(store_path: Path) -> None:
    assert load_course_offerings(store_path, SEMESTER) == []
    assert load_course_data_provenance(store_path) == []


# ---------------------------------------------------------------------------
# 5. meetings round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "meetings",
    [
        [],
        [_meeting()],
        [_meeting(1, 1, 2, (1, 2, 3, 4, 5, 6, 7, 8), campus="示例校区", classroom="A-101")],
        [_meeting(7, 11, 13, (16, 15, 14))],
        [
            _meeting(2, 1, 2, (1, 3, 5)),
            _meeting(4, 3, 4, (2, 4, 6), campus=None, classroom=None),
            _meeting(6, 5, 6, (1,)),
        ],
    ],
)
def test_meetings_round_trip(store_path: Path, meetings: list[Meeting]) -> None:
    snapshot = _snapshot([_offering(meetings=meetings)])

    import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)
    loaded = load_course_offerings(store_path, SEMESTER)

    assert loaded[0].meetings == meetings


def test_meetings_json_is_canonical_and_stable(store_path: Path) -> None:
    meetings = [_meeting(3, 5, 6, (2, 4, 6), campus="示例校区", classroom="示例教学楼-210")]
    import_offering_snapshot(
        store_path, _snapshot([_offering(meetings=meetings)]), artifact_sha256=ARTIFACT
    )

    stored = _raw_rows(store_path)[0]["meetings_json"]

    assert stored == json.dumps(
        [meeting.model_dump() for meeting in meetings],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert json.loads(stored)[0]["weeks"] == [2, 4, 6], "weeks 顺序必须原样保留"


def test_nullable_public_fields_round_trip(store_path: Path) -> None:
    snapshot = _snapshot(
        [
            _offering(
                teacher=None,
                credit=None,
                capacity=None,
                remaining_capacity=None,
                source=None,
                meetings=[],
            )
        ]
    )

    import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)
    loaded = load_course_offerings(store_path, SEMESTER)[0]

    assert loaded.teacher is None
    assert loaded.credit is None
    assert loaded.capacity is None
    assert loaded.remaining_capacity is None
    assert loaded.source is None
    assert loaded.meetings == []
    assert loaded.data_source is DataSource.REAL


def test_import_record_keeps_the_first_import_of_an_artifact(store_path: Path) -> None:
    """同一 `(artifact_sha256, semester)` **只记首次导入**，后续导入不改写该记录。

    ⚠️ 这是"artifact 记录幂等"的语义锁：即使第二次导入带来了不同的 `source` /
    行数（正常情况不该发生：同一个 hash 就应代表同一份字节），
    审计记录也**不**被改写（⛔ 不覆盖原始导入事实）。
    """

    first = import_offering_snapshot(
        store_path,
        _snapshot([_offering(course_id="SYN-1", source="source-a")]),
        artifact_sha256=ARTIFACT,
    )
    first_record = load_course_data_provenance(store_path)[0]

    second = import_offering_snapshot(
        store_path,
        _snapshot(
            [
                _offering(course_id="SYN-1", source="source-b"),
                _offering(course_id="SYN-2", source="source-b"),
            ]
        ),
        artifact_sha256=ARTIFACT,
    )

    records = load_course_data_provenance(store_path)

    assert second.already_imported is True
    assert len(records) == 1, "同一 artifact + semester 只能有一条导入记录"
    assert records[0] == first_record
    assert records[0].source == "source-a"
    assert records[0].loaded_count == 1
    assert records[0].imported_at == first.imported_at

    # ⛔ 但教学班行按 identity 正常 upsert（记录不改写 ≠ 数据不更新）
    assert len(load_course_offerings(store_path, SEMESTER)) == 2


def test_mixed_source_snapshot_records_no_single_source(store_path: Path) -> None:
    snapshot = _snapshot(
        [_offering(course_id="SYN-1", source="source-a"), _offering(course_id="SYN-2", source="source-b")]
    )

    import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)

    # ⛔ 不猜：本批次 source 不唯一时，artifact 记录里如实留空
    assert load_course_data_provenance(store_path)[0].source is None
    loaded = load_course_offerings(store_path, SEMESTER)
    assert {offering.source for offering in loaded} == {"source-a", "source-b"}


# ---------------------------------------------------------------------------
# 6. 输入校验 / fail closed
# ---------------------------------------------------------------------------


def test_artifact_sha256_is_required_and_validated(store_path: Path) -> None:
    snapshot = _snapshot([_offering()])

    for bad in (
        None,
        "",
        "   ",
        "abc",
        "z" * 64,
        ARTIFACT[:63],
        ARTIFACT + "0",
        ARTIFACT.upper() + "!",  # 长度正确但含非法字符
        12345,
    ):
        with pytest.raises(CourseDataStoreError):
            import_offering_snapshot(store_path, snapshot, artifact_sha256=bad)  # type: ignore[arg-type]

    assert _raw_rows(store_path) == []


def test_import_rejects_non_snapshot_input(store_path: Path) -> None:
    with pytest.raises(CourseDataStoreError):
        import_offering_snapshot(store_path, "not-a-snapshot", artifact_sha256=ARTIFACT)  # type: ignore[arg-type]

    with pytest.raises(CourseDataStoreError):
        import_offering_snapshot(store_path, None, artifact_sha256=ARTIFACT)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_semester", ["", "   ", None, 2026])
def test_load_rejects_invalid_semester(store_path: Path, bad_semester: object) -> None:
    with pytest.raises(CourseDataStoreError):
        load_course_offerings(store_path, bad_semester)  # type: ignore[arg-type]


def test_load_rejects_invalid_course_ids(store_path: Path) -> None:
    for bad in ("SYN-1", b"SYN-1", [""], ["   "], [1], [None]):
        with pytest.raises(CourseDataStoreError):
            load_course_offerings(store_path, SEMESTER, course_ids=bad)  # type: ignore[arg-type]


def test_store_path_must_be_a_file_in_an_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(CourseDataStoreError) as missing_parent:
        initialize_course_data_store(tmp_path / "nope" / "course_data.sqlite3")
    assert "父目录" in str(missing_parent.value)

    directory = tmp_path / "as-directory"
    directory.mkdir()
    with pytest.raises(CourseDataStoreError):
        initialize_course_data_store(directory)

    with pytest.raises(CourseDataStoreError):
        load_course_offerings(tmp_path / "not-there.sqlite3", SEMESTER)


def test_non_sqlite_file_fails_clearly(tmp_path: Path) -> None:
    broken = tmp_path / "broken.sqlite3"
    broken.write_bytes(b"this is definitely not a sqlite database")

    with pytest.raises(CourseDataStoreError) as excinfo:
        load_course_offerings(broken, SEMESTER)

    assert "Course Data" in str(excinfo.value) or "SQLite" in str(excinfo.value)


def test_foreign_sqlite_file_fails_clearly(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(str(foreign))
    connection.execute("CREATE TABLE unrelated (x INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError) as excinfo:
        load_course_offerings(foreign, SEMESTER)

    assert "不是 Course Data 本地库" in str(excinfo.value)


def test_tampered_meetings_json_fails_clearly(store_path: Path) -> None:
    import_offering_snapshot(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

    connection = sqlite3.connect(str(store_path))
    connection.execute("UPDATE course_offering SET meetings_json = ?", ("{not json",))
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError) as excinfo:
        load_course_offerings(store_path, SEMESTER)

    assert "meetings" in str(excinfo.value)


def test_tampered_meetings_payload_fails_clearly(store_path: Path) -> None:
    import_offering_snapshot(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

    connection = sqlite3.connect(str(store_path))
    connection.execute(
        "UPDATE course_offering SET meetings_json = ?", (json.dumps([{"weekday": 99}]),)
    )
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError):
        load_course_offerings(store_path, SEMESTER)


def test_non_real_rows_are_rejected_on_load(store_path: Path) -> None:
    """⛔ 真实链路只应出现 real；库里混入 mock 时拒绝加载（例如指到了别的库）。"""

    import_offering_snapshot(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

    connection = sqlite3.connect(str(store_path))
    connection.execute("UPDATE course_offering SET data_source = 'mock'")
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError) as excinfo:
        load_course_offerings(store_path, SEMESTER)

    assert "real" in str(excinfo.value)


def test_store_error_is_a_course_data_normalization_error() -> None:
    """⛔ 不发明新的顶层错误类型：调用方按既有基类一处捕获即可。"""

    assert issubclass(CourseDataStoreError, CourseDataNormalizationError)


# ---------------------------------------------------------------------------
# 7. 数据边界 / artifact identity 口径
# ---------------------------------------------------------------------------


def test_schema_has_no_forbidden_columns_or_tables(store_path: Path) -> None:
    """⛔ 库里不得出现认证材料 / 原始 response / 教师隐私扩展字段 / 学生信息。"""

    forbidden = (
        "cookie",
        "token",
        "session",
        "authorization",
        "password",
        "raw",
        "response",
        "header",
        "student",
        "user",
        "id_card",
        "teaching_name",
        "read_obj",
    )

    for table in ("course_offering", "course_data_import"):
        for column in _column_names(store_path, table):
            lowered = column.lower()
            for token in forbidden:
                assert token not in lowered, f"{table}.{column} 命中禁止字段：{token}"


def test_stored_row_contains_no_unexpected_columns(store_path: Path) -> None:
    import_offering_snapshot(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

    assert _column_names(store_path, "course_offering") == [
        "semester",
        "course_id",
        "class_id",
        "course_name",
        "teacher",
        "credit",
        "capacity",
        "remaining_capacity",
        "source",
        "data_source",
        "meetings_json",
        "artifact_sha256",
        "imported_at",
    ]


def test_compute_artifact_sha256_matches_known_vector() -> None:
    assert compute_artifact_sha256(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert compute_artifact_sha256(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert compute_artifact_sha256(b"abc") == compute_artifact_sha256(b"abc")


@pytest.mark.parametrize("bad", ["abc", 123, None, ["abc"]])
def test_compute_artifact_sha256_rejects_non_bytes(bad: object) -> None:
    with pytest.raises(CourseDataStoreError):
        compute_artifact_sha256(bad)  # type: ignore[arg-type]


def test_artifact_hash_is_identity_not_acquisition_proof(store_path: Path) -> None:
    """口径测试：同一个 hash 可以被**不同时间**重复导入，且库不据此声称任何采集事实。"""

    snapshot = _snapshot([_offering()])

    first = import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)
    second = import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)

    assert first.artifact_sha256 == second.artifact_sha256 == ARTIFACT
    assert second.already_imported is True

    record = load_course_data_provenance(store_path)[0]
    # ⛔ 库里只有 artifact identity + 导入时间，没有任何"采集时间 / 采集者 / 授权"字段
    assert set(record.__dataclass_fields__) == {
        "artifact_sha256",
        "semester",
        "source",
        "imported_at",
        "completeness",
        "loaded_count",
        "reported_total",
        "offering_count",
    }
