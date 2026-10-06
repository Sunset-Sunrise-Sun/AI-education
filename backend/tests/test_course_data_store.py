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
    ALLOWED_SCOPE_KINDS,
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    CourseDataNormalizationError,
    CourseDataStoreError,
    OfferingSnapshot,
    SnapshotScope,
    compute_artifact_sha256,
    import_offering_snapshot,
    initialize_course_data_store,
    load_accepted_offerings,
    load_course_data_acceptances,
    load_course_data_provenance,
    load_course_offerings,
    load_course_offerings_for_acceptance,
    offering_set_sha256,
)
from app.models.contracts import CourseOffering, DataSource, Meeting

SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
ARTIFACT = compute_artifact_sha256(b"synthetic-artifact-bytes")
OTHER_ARTIFACT = compute_artifact_sha256(b"another-synthetic-artifact")
SOURCE = "capture-set://synthetic/2026-1/shards"

#: 测试用的**显式 scope**（真实链路同样必须由调用方显式声明，⛔ 不推断）。
CAMPUS_ID = "5062202"
OTHER_CAMPUS_ID = "5063559"
CAMPUS_SCOPE = SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=CAMPUS_ID)
OTHER_CAMPUS_SCOPE = SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=OTHER_CAMPUS_ID)
FULL_SCOPE = SnapshotScope(scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=SEMESTER)
OTHER_FULL_SCOPE = SnapshotScope(scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=OTHER_SEMESTER)


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


def _import(
    path: Path,
    snapshot: OfferingSnapshot,
    *,
    artifact_sha256: str,
    scope: SnapshotScope = CAMPUS_SCOPE,
):
    """便捷包装：本文件多数用例只关心 upsert / 查询，scope 固定为 campus。

    ⚠️ scope 自身的语义、拒绝路径与"不从 source / 文件名推断"由文件末尾的
    **专门用例**用真实 API（`import_offering_snapshot`）覆盖。
    """

    return import_offering_snapshot(
        path, snapshot, artifact_sha256=artifact_sha256, scope=scope
    )


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

    result = _import(store_path, snapshot, artifact_sha256=ARTIFACT)

    assert (result.inserted, result.updated, result.unchanged) == (1, 0, 0)
    assert result.already_imported is False
    assert result.semester == SEMESTER
    assert result.artifact_sha256 == ARTIFACT

    loaded = load_course_offerings(store_path, SEMESTER)

    assert loaded == list(snapshot.offerings)


def test_import_records_artifact_provenance(store_path: Path) -> None:
    snapshot = _snapshot([_offering()])

    result = _import(store_path, snapshot, artifact_sha256=ARTIFACT)
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
    _import(store_path, snapshot, artifact_sha256=ARTIFACT.upper())

    rows = _raw_rows(store_path)

    assert len(rows) == 1
    assert rows[0]["artifact_sha256"] == ARTIFACT, "十六进制大小写应归一化"
    assert rows[0]["source"] == SOURCE
    assert rows[0]["data_source"] == "real"
    assert datetime.fromisoformat(rows[0]["imported_at"]).tzinfo is not None


def test_import_across_semesters_keeps_one_record_per_artifact(store_path: Path) -> None:
    _import(
        store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT
    )
    _import(
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
        _import(store_path, partial, artifact_sha256=ARTIFACT)

    assert "complete" in str(excinfo.value)
    assert "approved" in str(excinfo.value)


def test_rejected_partial_snapshot_writes_nothing(store_path: Path) -> None:
    partial = _snapshot([_offering()], completeness="partial")

    with pytest.raises(CourseDataStoreError):
        _import(store_path, partial, artifact_sha256=ARTIFACT)

    assert _raw_rows(store_path) == []
    assert load_course_data_provenance(store_path) == []


def test_store_does_not_claim_completeness_by_itself(store_path: Path) -> None:
    """⛔ 库里不得出现任何"自封完整"的列 / 表。"""

    for table in ("course_offering", "course_data_import"):
        for column in _column_names(store_path, table):
            assert column not in ("complete", "is_complete", "claimed_complete")

    # 导入记录只**如实转述**上游的 completeness 值
    _import(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)
    assert load_course_data_provenance(store_path)[0].completeness == "complete"


# ---------------------------------------------------------------------------
# 3. identity / upsert
# ---------------------------------------------------------------------------


def test_duplicate_import_of_same_artifact_is_idempotent(store_path: Path) -> None:
    snapshot = _snapshot([_offering(course_id="SYN-1"), _offering(course_id="SYN-2")])

    first = _import(store_path, snapshot, artifact_sha256=ARTIFACT)
    before = load_course_offerings(store_path, SEMESTER)

    second = _import(store_path, snapshot, artifact_sha256=ARTIFACT)
    after = load_course_offerings(store_path, SEMESTER)

    assert (first.inserted, first.already_imported) == (2, False)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 2)
    assert second.already_imported is True
    assert after == before
    assert len(_raw_rows(store_path)) == 2, "重复导入不得产生新行"
    assert len(load_course_data_provenance(store_path)) == 1


def test_reimport_with_changed_content_updates_in_place(store_path: Path) -> None:
    _import(
        store_path, _snapshot([_offering(capacity=90)]), artifact_sha256=ARTIFACT
    )

    changed = _snapshot(
        [_offering(capacity=120, remaining_capacity=3, meetings=[_meeting(2, 3, 4)])]
    )
    result = _import(store_path, changed, artifact_sha256=OTHER_ARTIFACT)

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

    _import(store_path, snapshot, artifact_sha256=ARTIFACT)

    loaded = load_course_offerings(store_path, SEMESTER, course_ids=["SYN-SAME"])

    assert [offering.class_id for offering in loaded] == ["01", "02"]
    assert len(_raw_rows(store_path)) == 2, "⛔ 不得按 course_id 单独覆盖不同教学班"


def test_same_identity_in_two_semesters_coexist(store_path: Path) -> None:
    _import(
        store_path,
        _snapshot([_offering(course_name="甲学期课程")]),
        artifact_sha256=ARTIFACT,
    )
    _import(
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
    _import(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)
    _import(
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
    _import(store_path, snapshot, artifact_sha256=ARTIFACT)

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
    _import(store_path, snapshot, artifact_sha256=ARTIFACT)

    loaded = load_course_offerings(store_path, SEMESTER)

    assert [(o.course_id, o.class_id) for o in loaded] == [
        ("SYN-A", "01"),
        ("SYN-A", "02"),
        ("SYN-B", "02"),
    ]


def test_load_with_empty_course_ids_returns_empty(store_path: Path) -> None:
    _import(
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

    _import(store_path, snapshot, artifact_sha256=ARTIFACT)
    loaded = load_course_offerings(store_path, SEMESTER)

    assert loaded[0].meetings == meetings


def test_meetings_json_is_canonical_and_stable(store_path: Path) -> None:
    meetings = [_meeting(3, 5, 6, (2, 4, 6), campus="示例校区", classroom="示例教学楼-210")]
    _import(
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

    _import(store_path, snapshot, artifact_sha256=ARTIFACT)
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

    first = _import(
        store_path,
        _snapshot([_offering(course_id="SYN-1", source="source-a")]),
        artifact_sha256=ARTIFACT,
    )
    first_record = load_course_data_provenance(store_path)[0]

    second = _import(
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

    _import(store_path, snapshot, artifact_sha256=ARTIFACT)

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
            _import(store_path, snapshot, artifact_sha256=bad)  # type: ignore[arg-type]

    assert _raw_rows(store_path) == []


def test_import_rejects_non_snapshot_input(store_path: Path) -> None:
    with pytest.raises(CourseDataStoreError):
        _import(store_path, "not-a-snapshot", artifact_sha256=ARTIFACT)  # type: ignore[arg-type]

    with pytest.raises(CourseDataStoreError):
        _import(store_path, None, artifact_sha256=ARTIFACT)  # type: ignore[arg-type]


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
    _import(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

    connection = sqlite3.connect(str(store_path))
    connection.execute("UPDATE course_offering SET meetings_json = ?", ("{not json",))
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError) as excinfo:
        load_course_offerings(store_path, SEMESTER)

    assert "meetings" in str(excinfo.value)


def test_tampered_meetings_payload_fails_clearly(store_path: Path) -> None:
    _import(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

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

    _import(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

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
    _import(store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT)

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
        "scope_kind",
        "scope_id",
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

    first = _import(store_path, snapshot, artifact_sha256=ARTIFACT)
    second = _import(store_path, snapshot, artifact_sha256=ARTIFACT)

    assert first.artifact_sha256 == second.artifact_sha256 == ARTIFACT
    assert second.already_imported is True

    record = load_course_data_provenance(store_path)[0]
    # ⛔ 库里只有 artifact identity + 导入时间 + 声明 scope，
    #    没有任何"采集时间 / 采集者 / 授权"字段
    assert set(record.__dataclass_fields__) == {
        "artifact_sha256",
        "semester",
        "scope_kind",
        "scope_id",
        "source",
        "imported_at",
        "completeness",
        "loaded_count",
        "reported_total",
        "offering_count",
    }


# ---------------------------------------------------------------------------
# 8. scope：`complete` **只在声明的 scope 内**成立（Review Blocker 修正）
# ---------------------------------------------------------------------------


def test_campus_scoped_complete_snapshot_can_be_imported(store_path: Path) -> None:
    """campus scope 的 complete 快照可以导入（scope 由调用方显式声明）。"""

    snapshot = _snapshot([_offering(course_id="SYN-C1")])

    result = import_offering_snapshot(
        store_path, snapshot, artifact_sha256=ARTIFACT, scope=CAMPUS_SCOPE
    )

    assert (result.inserted, result.already_imported) == (1, False)
    assert result.scope_kind == SCOPE_KIND_CAMPUS
    assert result.scope_id == CAMPUS_ID
    assert len(load_course_offerings(store_path, SEMESTER)) == 1


def test_campus_scope_round_trips(store_path: Path) -> None:
    import_offering_snapshot(
        store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT, scope=CAMPUS_SCOPE
    )

    record = load_course_data_provenance(store_path)[0]

    assert record.scope_kind == SCOPE_KIND_CAMPUS
    assert record.scope_id == CAMPUS_ID
    assert record.completeness == "complete"
    # ⛔ 记录里没有任何"全学期完整"的字段
    assert "global" not in " ".join(record.__dataclass_fields__)
    assert "semester_complete" not in record.__dataclass_fields__


def test_full_semester_scope_round_trips(store_path: Path) -> None:
    import_offering_snapshot(
        store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT, scope=FULL_SCOPE
    )

    record = load_course_data_provenance(store_path)[0]

    assert record.scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert record.scope_id == SEMESTER


def test_scope_is_required(store_path: Path) -> None:
    """⛔ scope 必须显式传入：省略 → TypeError；显式 None / 字符串 → 明确拒绝。"""

    snapshot = _snapshot([_offering()])

    with pytest.raises(TypeError):
        import_offering_snapshot(store_path, snapshot, artifact_sha256=ARTIFACT)  # type: ignore[call-arg]

    for bad in (None, "campus/5062202", ("campus", CAMPUS_ID), {"scope_kind": "campus"}):
        with pytest.raises(CourseDataStoreError):
            import_offering_snapshot(
                store_path, snapshot, artifact_sha256=ARTIFACT, scope=bad  # type: ignore[arg-type]
            )

    assert _raw_rows(store_path) == []
    assert load_course_data_provenance(store_path) == []


def test_invalid_scope_kinds_and_ids_are_rejected(store_path: Path) -> None:
    for bad_kind in ("case_a", "shard", "campus_shard", "CAMPUS", "full-semester", "", None, 1):
        with pytest.raises(CourseDataStoreError):
            SnapshotScope(scope_kind=bad_kind, scope_id="2026-1")  # type: ignore[arg-type]

    for bad_id in ("", "   ", None, 123):
        with pytest.raises(CourseDataStoreError):
            SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=bad_id)  # type: ignore[arg-type]

    # ⚠️ Case-A-scoped 的 id 语义尚未确证 ⇒ 明确**不在**白名单内（当前一律拒绝）
    assert "case_a" not in ALLOWED_SCOPE_KINDS


def test_full_semester_scope_id_must_match_the_snapshot_semester(store_path: Path) -> None:
    snapshot = _snapshot([_offering()])

    with pytest.raises(CourseDataStoreError) as excinfo:
        import_offering_snapshot(
            store_path, snapshot, artifact_sha256=ARTIFACT, scope=OTHER_FULL_SCOPE
        )

    assert "scope_id" in str(excinfo.value)
    assert _raw_rows(store_path) == []


def test_scope_is_never_inferred_from_source_or_filename(store_path: Path) -> None:
    """⛔ scope 只认**调用方声明**：`source` 里写什么都不得改变它。"""

    campus_looking_source = _snapshot([_offering(source="campus/5062202/shard-bundle.json")])
    import_offering_snapshot(
        store_path, campus_looking_source, artifact_sha256=ARTIFACT, scope=FULL_SCOPE
    )

    record = load_course_data_provenance(store_path)[0]
    assert (record.scope_kind, record.scope_id) == (SCOPE_KIND_FULL_SEMESTER, SEMESTER)
    # source 原样保留（它只是来源标注，⛔ 不参与 scope）
    assert record.source == "campus/5062202/shard-bundle.json"

    full_looking_source = _snapshot(
        [_offering(course_id="SYN-2", source="capture-set://full/2026-1/semester.sqlite3")]
    )
    import_offering_snapshot(
        store_path, full_looking_source, artifact_sha256=OTHER_ARTIFACT, scope=CAMPUS_SCOPE
    )

    records = {item.artifact_sha256: item for item in load_course_data_provenance(store_path)}
    assert (records[OTHER_ARTIFACT].scope_kind, records[OTHER_ARTIFACT].scope_id) == (
        SCOPE_KIND_CAMPUS,
        CAMPUS_ID,
    )


def test_same_semester_different_campus_artifacts_are_audited_separately(
    store_path: Path,
) -> None:
    """同 semester 的不同校区 artifact：两条审计记录并存，两批教学班并存。"""

    import_offering_snapshot(
        store_path,
        _snapshot([_offering(course_id="SYN-A", class_id="01")]),
        artifact_sha256=ARTIFACT,
        scope=CAMPUS_SCOPE,
    )
    import_offering_snapshot(
        store_path,
        _snapshot([_offering(course_id="SYN-B", class_id="01")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=OTHER_CAMPUS_SCOPE,
    )

    records = load_course_data_provenance(store_path, semester=SEMESTER)

    assert len(records) == 2
    assert {(item.scope_kind, item.scope_id) for item in records} == {
        (SCOPE_KIND_CAMPUS, CAMPUS_ID),
        (SCOPE_KIND_CAMPUS, OTHER_CAMPUS_ID),
    }
    assert len(load_course_offerings(store_path, SEMESTER)) == 2


def test_same_artifact_under_two_scopes_keeps_two_audit_records(store_path: Path) -> None:
    """同一份 artifact 以不同 scope 声明时：⛔ 不静默合并成一条含糊记录。"""

    snapshot = _snapshot([_offering()])

    first = import_offering_snapshot(
        store_path, snapshot, artifact_sha256=ARTIFACT, scope=CAMPUS_SCOPE
    )
    second = import_offering_snapshot(
        store_path, snapshot, artifact_sha256=ARTIFACT, scope=FULL_SCOPE
    )

    assert first.already_imported is False
    assert second.already_imported is False, "不同 scope 不算已导入"

    records = load_course_data_provenance(store_path)
    assert len(records) == 2
    assert {(item.scope_kind, item.scope_id) for item in records} == {
        (SCOPE_KIND_CAMPUS, CAMPUS_ID),
        (SCOPE_KIND_FULL_SEMESTER, SEMESTER),
    }

    # 同一 (artifact, semester, scope) 再导一次才幂等
    third = import_offering_snapshot(
        store_path, snapshot, artifact_sha256=ARTIFACT, scope=CAMPUS_SCOPE
    )
    assert third.already_imported is True
    assert len(load_course_data_provenance(store_path)) == 2
    assert len(_raw_rows(store_path)) == 1, "identity 与 scope 无关：仍然只有一行"


def test_row_level_scope_provenance_follows_the_latest_import(store_path: Path) -> None:
    import_offering_snapshot(
        store_path, _snapshot([_offering()]), artifact_sha256=ARTIFACT, scope=CAMPUS_SCOPE
    )
    row = _raw_rows(store_path)[0]
    assert (row["scope_kind"], row["scope_id"]) == (SCOPE_KIND_CAMPUS, CAMPUS_ID)

    # 同一 identity 后来被 full_semester 的 artifact 再次覆盖
    import_offering_snapshot(
        store_path, _snapshot([_offering()]), artifact_sha256=OTHER_ARTIFACT, scope=FULL_SCOPE
    )

    row = _raw_rows(store_path)[0]
    assert (row["scope_kind"], row["scope_id"]) == (SCOPE_KIND_FULL_SEMESTER, SEMESTER)
    assert row["artifact_sha256"] == OTHER_ARTIFACT
    # 两条审计记录都还在（⛔ 不丢历史）
    assert len(load_course_data_provenance(store_path)) == 2


def test_legacy_store_without_scope_columns_fails_clearly(tmp_path: Path) -> None:
    """⛔ 更早 schema 的本地库（没有 scope 列）→ 明确提示重建，⛔ 不静默降级读写。"""

    legacy = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(str(legacy))
    connection.executescript(
        """
        CREATE TABLE course_offering (
            semester TEXT NOT NULL, course_id TEXT NOT NULL, class_id TEXT NOT NULL,
            course_name TEXT NOT NULL, teacher TEXT, credit REAL, capacity INTEGER,
            remaining_capacity INTEGER, source TEXT, data_source TEXT NOT NULL,
            meetings_json TEXT NOT NULL, artifact_sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            PRIMARY KEY (semester, course_id, class_id)
        );
        CREATE TABLE course_data_import (
            artifact_sha256 TEXT NOT NULL, semester TEXT NOT NULL, source TEXT,
            imported_at TEXT NOT NULL, completeness TEXT NOT NULL,
            loaded_count INTEGER NOT NULL, reported_total INTEGER,
            offering_count INTEGER NOT NULL,
            PRIMARY KEY (artifact_sha256, semester)
        );
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError) as read_error:
        load_course_offerings(legacy, SEMESTER)
    assert "scope" in str(read_error.value)

    with pytest.raises(CourseDataStoreError) as write_error:
        import_offering_snapshot(
            legacy, _snapshot([_offering()]), artifact_sha256=ARTIFACT, scope=CAMPUS_SCOPE
        )
    assert "scope" in str(write_error.value)


def test_schema_holds_no_global_completeness_column(store_path: Path) -> None:
    """⛔ 库里不得出现任何"全学期 / 全局完整"的列（scope 只如实记录声明值）。"""

    for table in ("course_offering", "course_data_import"):
        for column in _column_names(store_path, table):
            lowered = column.lower()
            for token in ("global", "semester_complete", "full_complete", "is_full"):
                assert token not in lowered, f"{table}.{column} 命中禁止字段：{token}"


# ---------------------------------------------------------------------------
# 10. content-bound acceptance 平面（BLOCK B3 / B4）
# ---------------------------------------------------------------------------


def _full_snapshot(offerings: list[CourseOffering]) -> OfferingSnapshot:
    return _snapshot(offerings)


def test_import_writes_the_content_bound_acceptance_plane(store_path: Path) -> None:
    offerings = [
        _offering(course_id="SYN-A", class_id="A-01"),
        _offering(course_id="SYN-B", class_id="B-01"),
    ]
    snapshot = _full_snapshot(offerings)

    _import(store_path, snapshot, artifact_sha256=OTHER_ARTIFACT, scope=FULL_SCOPE)

    records = load_course_data_acceptances(store_path, semester=SEMESTER)
    assert len(records) == 1
    assert records[0].artifact_sha256 == OTHER_ARTIFACT
    assert records[0].scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert records[0].scope_id == SEMESTER
    assert records[0].offering_count == 2
    assert records[0].offering_set_sha256 == offering_set_sha256(snapshot.offerings)

    dataset = load_accepted_offerings(
        store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
    )
    assert dataset.member_count == 2
    assert [offering.course_id for offering in dataset.offerings] == ["SYN-A", "SYN-B"]
    assert dataset.acceptance.offering_set_sha256 == records[0].offering_set_sha256


def test_accepted_read_requires_both_planes(store_path: Path) -> None:
    _import(
        store_path,
        _full_snapshot([_offering(course_id="SYN-A", class_id="A-01")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    connection = sqlite3.connect(str(store_path))
    connection.execute("DELETE FROM course_data_import WHERE artifact_sha256 = ?", (OTHER_ARTIFACT,))
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError) as missing_provenance:
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
        )
    assert "两个平面" in str(missing_provenance.value) or "导入记录" in str(
        missing_provenance.value
    )


def test_accepted_read_requires_the_acceptance_record(store_path: Path) -> None:
    """B4：acceptance 记录被删除 ⇒ 下一次读取必须 fail closed（⛔ 不靠缓存）。"""

    _import(
        store_path,
        _full_snapshot([_offering(course_id="SYN-A", class_id="A-01")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    connection = sqlite3.connect(str(store_path))
    connection.execute(
        "DELETE FROM course_data_acceptance WHERE artifact_sha256 = ?", (OTHER_ARTIFACT,)
    )
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("course_name", "被替换的课程名"),
        ("course_id", "SYN-SUBSTITUTED"),
        ("class_id", "SUBSTITUTED-01"),
        ("source", "capture://tampered"),
        ("meetings_json", "[]"),
        ("credit", 9.0),
    ],
)
def test_same_count_content_substitution_is_detected(
    store_path: Path, column: str, value: object
) -> None:
    """B3：同数量 / 同身份下的**内容替换**必须被读路径发现。"""

    _import(
        store_path,
        _full_snapshot([_offering(course_id="SYN-A", class_id="A-01")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    connection = sqlite3.connect(str(store_path))
    connection.execute(f"UPDATE course_offering SET {column} = ?", (value,))
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
        )


def test_deleted_or_extra_member_is_detected(store_path: Path) -> None:
    offerings = [
        _offering(course_id="SYN-A", class_id="A-01"),
        _offering(course_id="SYN-B", class_id="B-01"),
    ]
    _import(
        store_path,
        _full_snapshot(offerings),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    connection = sqlite3.connect(str(store_path))
    connection.execute("DELETE FROM course_offering WHERE class_id = ?", ("B-01",))
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
        )


def test_stale_rows_and_other_semesters_are_never_returned(store_path: Path) -> None:
    _import(
        store_path,
        _full_snapshot([_offering(course_id="SYN-STALE", class_id="STALE-01")]),
        artifact_sha256=ARTIFACT,
        scope=CAMPUS_SCOPE,
    )
    _import(
        store_path,
        _snapshot(
            [_offering(semester=OTHER_SEMESTER, class_id="OTHER-01")],
            semester=OTHER_SEMESTER,
        ),
        artifact_sha256=OTHER_ARTIFACT,
        scope=OTHER_FULL_SCOPE,
    )
    _import(
        store_path,
        _full_snapshot([_offering(course_id="SYN-A", class_id="A-01")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    dataset = load_accepted_offerings(
        store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
    )
    assert [offering.course_id for offering in dataset.offerings] == ["SYN-A"]
    # 整学期查询仍然能看到陈旧行 ⇒ 两者语义确实不同。
    assert len(load_course_offerings(store_path, SEMESTER)) == 2


def test_later_campus_overwrite_invalidates_the_full_acceptance(store_path: Path) -> None:
    _import(
        store_path,
        _full_snapshot([_offering(course_id="SYN-A", class_id="A-01")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )
    # 后来的 campus import 覆盖同一行的 provenance（内容相同也不行）。
    _import(
        store_path,
        _snapshot([_offering(course_id="SYN-A", class_id="A-01")]),
        artifact_sha256=ARTIFACT,
        scope=CAMPUS_SCOPE,
    )

    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
        )


def test_accepted_read_is_scope_parameterized(store_path: Path) -> None:
    _import(
        store_path,
        _snapshot([_offering(course_id="SYN-C", class_id="C-01")]),
        artifact_sha256=ARTIFACT,
        scope=CAMPUS_SCOPE,
    )

    campus_dataset = load_accepted_offerings(
        store_path,
        semester=SEMESTER,
        acceptance_sha256=ARTIFACT,
        scope=CAMPUS_SCOPE,
    )
    assert [offering.course_id for offering in campus_dataset.offerings] == ["SYN-C"]

    # ⛔ 同一批字节不能以 full_semester 语义读回。
    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=ARTIFACT
        )


def test_reimport_with_different_content_under_one_identity_fails_closed(
    store_path: Path,
) -> None:
    """同一 acceptance identity 被以**不同内容**重复导入 ⇒ 两个平面不一致 ⇒ 拒绝。"""

    _import(
        store_path,
        _full_snapshot([_offering(course_id="SYN-A", class_id="A-01")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )
    first = load_accepted_offerings(
        store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
    )
    assert first.member_count == 1

    _import(
        store_path,
        _full_snapshot(
            [
                _offering(course_id="SYN-A", class_id="A-01"),
                _offering(course_id="SYN-B", class_id="B-01"),
            ]
        ),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    # 历史审计记录保留**首次**导入的计数（声明平面），content-bound 平面记录最新内容
    # ⇒ 两者不一致 ⇒ fail closed（⛔ 不会悄悄采用其中一边）。
    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
        )


def test_identical_reimport_keeps_the_acceptance_readable(store_path: Path) -> None:
    offerings = [
        _offering(course_id="SYN-A", class_id="A-01"),
        _offering(course_id="SYN-B", class_id="B-01"),
    ]
    for _ in range(2):
        _import(
            store_path,
            _full_snapshot(offerings),
            artifact_sha256=OTHER_ARTIFACT,
            scope=FULL_SCOPE,
        )

    dataset = load_accepted_offerings(
        store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
    )
    assert dataset.member_count == 2
    assert len(load_course_data_provenance(store_path, semester=SEMESTER)) == 1


def test_accepted_read_rejects_unreadable_store(store_path: Path) -> None:
    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256="not-a-digest"
        )

    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester="   ", acceptance_sha256=OTHER_ARTIFACT
        )


def test_empty_acceptance_is_rejected_by_the_read_path(store_path: Path) -> None:
    """零行 acceptance 不得被装配（⛔ 不做"有一些行就启动"）。"""

    _import(
        store_path,
        _full_snapshot([]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
        )


# ---------------------------------------------------------------------------
# 9. acceptance-bound read-back（Gate B：`load_course_offerings_for_acceptance`）
# ---------------------------------------------------------------------------


def test_acceptance_bound_query_returns_only_that_acceptance(store_path: Path) -> None:
    """`load_course_offerings(semester)` 与按 acceptance 读回**语义不同**。"""

    _import(
        store_path,
        _snapshot([_offering(course_id="SYN-CAMPUS", class_id="campus-000")]),
        artifact_sha256=ARTIFACT,
        scope=CAMPUS_SCOPE,
    )
    _import(
        store_path,
        _snapshot([_offering(course_id="SYN-FULL", class_id="full-000")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )

    assert len(load_course_offerings(store_path, SEMESTER)) == 2

    bound = load_course_offerings_for_acceptance(
        store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
    )
    assert [offering.course_id for offering in bound] == ["SYN-FULL"]
    assert [offering.data_source for offering in bound] == [DataSource.REAL]


def test_acceptance_bound_query_requires_the_full_semester_scope(store_path: Path) -> None:
    """同一份 artifact 若以 **campus** scope 声明，则不属于任何 full_semester acceptance。"""

    _import(
        store_path,
        _snapshot([_offering()]),
        artifact_sha256=ARTIFACT,
        scope=CAMPUS_SCOPE,
    )

    assert (
        load_course_offerings_for_acceptance(
            store_path, semester=SEMESTER, acceptance_sha256=ARTIFACT
        )
        == []
    )


def test_acceptance_bound_query_is_semester_isolated(store_path: Path) -> None:
    _import(
        store_path,
        _snapshot([_offering(class_id="full-000")]),
        artifact_sha256=OTHER_ARTIFACT,
        scope=FULL_SCOPE,
    )
    _import(
        store_path,
        _snapshot(
            [_offering(semester=OTHER_SEMESTER, class_id="other-000")],
            semester=OTHER_SEMESTER,
        ),
        artifact_sha256=OTHER_ARTIFACT,
        scope=OTHER_FULL_SCOPE,
    )

    bound = load_course_offerings_for_acceptance(
        store_path, semester=SEMESTER, acceptance_sha256=OTHER_ARTIFACT
    )
    assert [offering.semester for offering in bound] == [SEMESTER]


def test_acceptance_bound_query_rejects_invalid_arguments(store_path: Path) -> None:
    with pytest.raises(CourseDataStoreError):
        load_course_offerings_for_acceptance(
            store_path, semester=SEMESTER, acceptance_sha256="not-a-digest"
        )
    with pytest.raises(CourseDataStoreError):
        load_course_offerings_for_acceptance(
            store_path, semester="   ", acceptance_sha256=OTHER_ARTIFACT
        )


def test_acceptance_bound_query_orders_by_sql() -> None:
    """⛔ 顺序必须是 SQL 显式保证的（源码级断言，同 `load_order_is_guaranteed`）。"""

    source = Path(__file__).resolve().parents[1] / "app" / "course_data" / "store.py"
    text = source.read_text(encoding="utf-8")

    assert (
        "AND artifact_sha256 = ? ORDER BY course_id, class_id" in text
    )
    assert "WHERE semester = ? AND scope_kind = ? AND scope_id = ? " in text
