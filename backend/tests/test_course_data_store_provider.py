"""Store-backed CourseDataProvider tests (synthetic SQLite, zero-network).

Covers the Forward Red-Team BLOCK B3/B4 fixes: the accepted dataset is read
through the content-bound plane and **every** call re-verifies the acceptance
record, both planes, the membership and the per-row content digests.
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from app.course_data import (
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    AcceptedDataset,
    CourseDataAcceptanceError,
    CourseDataStoreError,
    OfferingSnapshot,
    SnapshotScope,
    StoreBackedCourseDataProvider,
    compute_artifact_sha256,
    import_offering_snapshot,
    initialize_course_data_store,
    load_accepted_offerings,
    load_course_data_acceptances,
    load_course_data_provenance,
    load_course_offerings,
    load_course_offerings_for_acceptance,
)
from app.integration import PlanningOrchestrator
from app.integration.ports import CourseDataProvider
from app.models.contracts import CourseOffering, DataSource, PlanResult, Preference

SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
ACCEPTANCE = compute_artifact_sha256(b"synthetic-full-semester-acceptance")
OTHER_ACCEPTANCE = compute_artifact_sha256(b"synthetic-other-acceptance")
CAMPUS_ACCEPTANCE = compute_artifact_sha256(b"synthetic-campus-acceptance")

FULL_SCOPE = SnapshotScope(scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=SEMESTER)
CAMPUS_SCOPE = SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id="5063559")


def _meeting() -> dict[str, object]:
    return {
        "weekday": 5,
        "start_section": 5,
        "end_section": 6,
        "weeks": [1, 2, 3],
        "campus": "示例校区",
    }


def _offering(
    course_id: str,
    class_id: str,
    *,
    course_name: str = "示例课程",
    semester: str = SEMESTER,
    meetings: list[dict[str, object]] | None = None,
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=course_name,
        class_id=class_id,
        semester=semester,
        teacher="REDACTED",
        credit=3.0,
        meetings=[_meeting()] if meetings is None else meetings,
        capacity=90,
        remaining_capacity=75,
        source=f"capture://sysu/{semester}/full-semester/{semester}",
        data_source=DataSource.REAL,
    )


def _snapshot(
    offerings: list[CourseOffering], *, semester: str = SEMESTER
) -> OfferingSnapshot:
    return OfferingSnapshot(
        semester=semester,
        offerings=tuple(offerings),
        completeness="complete",
        reported_total=len(offerings),
    )


def _accepted_store(
    tmp_path: Path,
    *,
    offerings: list[CourseOffering] | None = None,
    digest: str = ACCEPTANCE,
    scope: SnapshotScope = FULL_SCOPE,
) -> tuple[Path, str]:
    store = tmp_path / "course-data.sqlite3"
    resolved = (
        offerings
        if offerings is not None
        else [
            _offering("SYN-A", "A-01"),
            _offering("SYN-B", "B-01"),
            _offering("SYN-C", "C-01"),
        ]
    )
    import_offering_snapshot(
        store, _snapshot(resolved), artifact_sha256=digest, scope=scope
    )
    return store, digest


def _provider(path: Path, digest: str = ACCEPTANCE) -> StoreBackedCourseDataProvider:
    return StoreBackedCourseDataProvider(
        sqlite_path=path, semester=SEMESTER, acceptance_sha256=digest
    )


def _tamper(path: Path, statement: str, parameters: tuple[object, ...]) -> None:
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(statement, parameters)
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_valid_full_semester_store_returns_the_bound_rows(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store)

    assert provider.semester == SEMESTER
    assert provider.acceptance_sha256 == digest
    assert provider.expected_offering_count == 3
    assert provider.provenance.scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert provider.provenance.scope_id == SEMESTER

    offerings = provider.get_course_offerings(SEMESTER)
    assert [offering.class_id for offering in offerings] == ["A-01", "B-01", "C-01"]
    assert {offering.data_source for offering in offerings} == {DataSource.REAL}


def test_provider_structurally_satisfies_the_frozen_protocol(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    assert isinstance(provider, CourseDataProvider)
    assert list(
        inspect.signature(CourseDataProvider.get_course_offerings).parameters
    ) == ["self", "semester"]
    assert list(inspect.signature(provider.get_course_offerings).parameters) == [
        "semester"
    ]


def test_provider_ordering_is_deterministic(tmp_path: Path) -> None:
    store, _digest = _accepted_store(
        tmp_path,
        offerings=[
            _offering("SYN-Z", "Z-01"),
            _offering("SYN-A", "A-01"),
            _offering("SYN-M", "M-01"),
        ],
    )
    provider = _provider(store)

    keys = [
        (offering.course_id, offering.class_id)
        for offering in provider.get_course_offerings(SEMESTER)
    ]
    assert keys == sorted(keys)


def test_provider_is_read_only_for_the_store(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    before = load_course_data_provenance(store, semester=SEMESTER)
    provider.get_course_offerings(SEMESTER)
    provider.get_course_offerings(SEMESTER)
    after = load_course_data_provenance(store, semester=SEMESTER)

    assert before == after
    assert len(load_course_offerings(store, SEMESTER)) == 3


def test_orchestrator_receives_the_bound_offerings(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    seen: dict[str, object] = {}

    class _Curriculum:
        def get_makeup_tasks(self) -> list[object]:
            return []

    class _Planner:
        def plan(self, *, makeup_tasks, offerings, current_schedule, preference) -> PlanResult:
            seen["offerings"] = list(offerings)
            seen["preference"] = preference
            return PlanResult(
                status="feasible",
                selected_classes=[],
                changes=[],
                risks=[],
                unresolved=[],
            )

    orchestrator = PlanningOrchestrator(
        curriculum=_Curriculum(), course_data=provider, planner=_Planner()
    )
    result = orchestrator.build_plan(
        semester=SEMESTER, current_schedule=[], preference=Preference()
    )

    assert result.status == "feasible"
    assert len(seen["offerings"]) == 3  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# construction fail-closed matrix
# --------------------------------------------------------------------------- #


def test_store_acceptance_missing_is_not_ready(tmp_path: Path) -> None:
    store = tmp_path / "empty.sqlite3"
    initialize_course_data_store(store)

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_campus_only_store_is_rejected(tmp_path: Path) -> None:
    store, _digest = _accepted_store(
        tmp_path,
        offerings=[_offering("SYN-CAMPUS", "C-01")],
        digest=CAMPUS_ACCEPTANCE,
        scope=CAMPUS_SCOPE,
    )

    with pytest.raises(CourseDataAcceptanceError):
        StoreBackedCourseDataProvider(
            sqlite_path=store, semester=SEMESTER, acceptance_sha256=CAMPUS_ACCEPTANCE
        )


def test_wrong_acceptance_sha256_is_rejected(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, OTHER_ACCEPTANCE)


def test_wrong_scope_kind_is_rejected(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(
        store, "UPDATE course_data_acceptance SET scope_kind = ?", (SCOPE_KIND_CAMPUS,)
    )
    _tamper(store, "UPDATE course_data_import SET scope_kind = ?", (SCOPE_KIND_CAMPUS,))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_wrong_scope_id_is_rejected(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(store, "UPDATE course_data_acceptance SET scope_id = ?", (OTHER_SEMESTER,))
    _tamper(store, "UPDATE course_data_import SET scope_id = ?", (OTHER_SEMESTER,))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_incomplete_provenance_is_rejected(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(store, "UPDATE course_data_acceptance SET completeness = ?", ("partial",))
    _tamper(store, "UPDATE course_data_import SET completeness = ?", ("partial",))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("loaded_count", 2),
        ("reported_total", 2),
        ("offering_count", 2),
        ("offering_count", 0),
        ("reported_total", None),
    ],
)
def test_store_with_inconsistent_counts_is_not_ready(
    tmp_path: Path, column: str, value: object
) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(store, f"UPDATE course_data_acceptance SET {column} = ?", (value,))
    _tamper(store, f"UPDATE course_data_import SET {column} = ?", (value,))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_store_with_zero_rows_is_not_ready(tmp_path: Path) -> None:
    store = tmp_path / "course-data.sqlite3"
    import_offering_snapshot(
        store,
        _snapshot([]),
        artifact_sha256=ACCEPTANCE,
        scope=FULL_SCOPE,
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_two_planes_must_agree(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(store, "DELETE FROM course_data_import", ())

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("course_name", "被替换"),
        ("course_id", "SYN-SUBSTITUTED"),
        ("class_id", "SUB-01"),
        ("source", "capture://sysu/tampered"),
        ("meetings_json", "[]"),
        ("credit", 9.0),
    ],
)
def test_store_with_tampered_content_is_not_ready(
    tmp_path: Path, column: str, value: object
) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(
        store,
        f"UPDATE course_offering SET {column} = ? WHERE class_id = ?",
        (value, "B-01"),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_store_with_tampered_membership_is_not_ready(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(
        store,
        "DELETE FROM course_data_acceptance_member WHERE class_id = ?",
        ("C-01",),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_deleted_row_is_rejected(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    _tamper(store, "DELETE FROM course_offering WHERE class_id = ?", ("A-01",))
    _tamper(
        store,
        "DELETE FROM course_data_acceptance_member WHERE class_id = ?",
        ("A-01",),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store)


def test_foreign_sqlite_file_is_rejected(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(str(foreign))
    connection.execute("CREATE TABLE unrelated (id INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError):
        _provider(foreign)


def test_missing_sqlite_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CourseDataStoreError):
        _provider(tmp_path / "absent.sqlite3")


@pytest.mark.parametrize("semester", ["", "   ", None, 5])
def test_invalid_semester_is_rejected(tmp_path: Path, semester: object) -> None:
    store, _digest = _accepted_store(tmp_path)

    with pytest.raises(CourseDataStoreError):
        StoreBackedCourseDataProvider(
            sqlite_path=store,
            semester=semester,  # type: ignore[arg-type]
            acceptance_sha256=ACCEPTANCE,
        )


@pytest.mark.parametrize("digest", ["", "not-a-digest", "a" * 63, "z" * 64, None])
def test_invalid_acceptance_digest_is_rejected(tmp_path: Path, digest: object) -> None:
    store, _digest = _accepted_store(tmp_path)

    with pytest.raises(CourseDataStoreError):
        StoreBackedCourseDataProvider(
            sqlite_path=store,
            semester=SEMESTER,
            acceptance_sha256=digest,  # type: ignore[arg-type]
        )


def test_non_path_sqlite_argument_is_rejected() -> None:
    with pytest.raises(CourseDataAcceptanceError):
        StoreBackedCourseDataProvider(
            sqlite_path=123,  # type: ignore[arg-type]
            semester=SEMESTER,
            acceptance_sha256=ACCEPTANCE,
        )


# --------------------------------------------------------------------------- #
# isolation
# --------------------------------------------------------------------------- #


def test_stale_campus_rows_are_not_served(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    # 塞一条只有 campus provenance 的陈旧行（不属于本 acceptance）。
    import_offering_snapshot(
        store,
        _snapshot([_offering("SYN-STALE", "STALE-01")]),
        artifact_sha256=CAMPUS_ACCEPTANCE,
        scope=CAMPUS_SCOPE,
    )

    provider = _provider(store)
    offerings = provider.get_course_offerings(SEMESTER)

    assert len(offerings) == 3
    assert "SYN-STALE" not in {offering.course_id for offering in offerings}
    # 整学期查询仍然能看到陈旧行 ⇒ 两者语义确实不同。
    assert len(load_course_offerings(store, SEMESTER)) == 4


def test_other_semester_rows_are_not_served(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    import_offering_snapshot(
        store,
        _snapshot(
            [_offering("SYN-OTHER", "O-01", semester=OTHER_SEMESTER)],
            semester=OTHER_SEMESTER,
        ),
        artifact_sha256=OTHER_ACCEPTANCE,
        scope=SnapshotScope(
            scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=OTHER_SEMESTER
        ),
    )

    provider = _provider(store)
    offerings = provider.get_course_offerings(SEMESTER)

    assert {offering.semester for offering in offerings} == {SEMESTER}


def test_requesting_another_semester_fails_closed(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(OTHER_SEMESTER)

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings("")

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# BLOCK B4: continuous verification
# --------------------------------------------------------------------------- #


def test_acceptance_record_removed_after_construction_fails_closed(
    tmp_path: Path,
) -> None:
    """Reviewer probe：构造成功 → 删除 acceptance → **下一次读取必须失败**。"""

    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)
    assert len(provider.get_course_offerings(SEMESTER)) == 3

    _tamper(store, "DELETE FROM course_data_acceptance", ())

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_import_record_removed_after_construction_fails_closed(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    _tamper(store, "DELETE FROM course_data_import", ())

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_content_change_after_construction_fails_closed(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    _tamper(
        store,
        "UPDATE course_offering SET course_name = ? WHERE class_id = ?",
        ("构造之后被替换", "C-01"),
    )

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_membership_change_after_construction_fails_closed(tmp_path: Path) -> None:
    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    _tamper(
        store,
        "UPDATE course_data_acceptance_member SET offering_payload_sha256 = ? "
        "WHERE class_id = ?",
        ("f" * 64, "A-01"),
    )

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_new_stale_row_after_construction_does_not_leak(tmp_path: Path) -> None:
    """构造之后塞入陈旧 campus 行 ⇒ 读取仍然只返回被接受的那批行。"""

    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    import_offering_snapshot(
        store,
        _snapshot([_offering("SYN-LATE", "LATE-01")]),
        artifact_sha256=CAMPUS_ACCEPTANCE,
        scope=CAMPUS_SCOPE,
    )

    offerings = provider.get_course_offerings(SEMESTER)
    assert len(offerings) == 3
    assert "SYN-LATE" not in {offering.course_id for offering in offerings}


def test_provider_re_reads_instead_of_caching_rows(tmp_path: Path) -> None:
    """⛔ 不缓存 rows：每次调用都从库里重新物化。"""

    store, _digest = _accepted_store(tmp_path)
    provider = _provider(store)

    first = provider.get_course_offerings(SEMESTER)
    second = provider.get_course_offerings(SEMESTER)

    assert first == second
    assert first is not second


# --------------------------------------------------------------------------- #
# lower-level helpers kept for diagnostics
# --------------------------------------------------------------------------- #


def test_declaration_plane_query_is_not_authoritative(tmp_path: Path) -> None:
    """行级 provenance 查询**不核对内容** ⇒ ⛔ 不能当作权威读取路径。"""

    store, digest = _accepted_store(tmp_path)
    _tamper(
        store,
        "UPDATE course_offering SET course_name = ? WHERE class_id = ?",
        ("被替换", "A-01"),
    )

    rows = load_course_offerings_for_acceptance(
        store, semester=SEMESTER, acceptance_sha256=digest
    )
    assert len(rows) == 3  # ⚠️ 内容已变，它仍然返回

    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(store, semester=SEMESTER, acceptance_sha256=digest)


def test_acceptance_metadata_is_exposed(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)

    records = load_course_data_acceptances(store, semester=SEMESTER)
    assert len(records) == 1
    assert records[0].artifact_sha256 == digest
    assert len(records[0].offering_set_sha256) == 64


def test_accepted_dataset_shape(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)

    dataset = load_accepted_offerings(
        store, semester=SEMESTER, acceptance_sha256=digest
    )

    assert isinstance(dataset, AcceptedDataset)
    assert dataset.member_count == 3
    assert len(dataset.offerings) == 3
    assert len(dataset.acceptance.offering_set_sha256) == 64


def test_provider_module_has_no_network_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "course_data" / "store_provider.py"
    )
    source = module_path.read_text(encoding="utf-8")

    for forbidden in ("requests", "httpx", "urllib", "socket", "aiohttp", "http.client"):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source
