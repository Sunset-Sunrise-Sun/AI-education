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
    ImmutableAcceptanceConflictError,
    OfferingSnapshot,
    SnapshotScope,
    StoreBackedCourseDataProvider,
    canonical_manifest_bytes,
    compute_artifact_sha256,
    compute_manifest_sha256,
    import_offering_snapshot,
    initialize_course_data_store,
    load_accepted_offerings,
    load_course_data_acceptances,
    load_course_data_provenance,
    load_course_offerings,
    load_course_offerings_for_acceptance,
    offering_set_sha256,
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


def _manifest_for(
    offerings: list[CourseOffering],
    *,
    semester: str = SEMESTER,
    inventory_sha256: str | None = None,
) -> dict[str, object]:
    """为一份 full_semester 快照构造 canonical manifest（immutable identity）。"""

    total = len(offerings)

    return {
        "format": "sysu-course-data-full-semester-acceptance-v1",
        "manifest_version": 2,
        "tool": "tests/synthetic",
        "semester": semester,
        "scope_kind": SCOPE_KIND_FULL_SEMESTER,
        "scope_id": semester,
        "source": f"capture://sysu/{semester}/full-semester/{semester}",
        "inventory_sha256": inventory_sha256 or ("a" * 64),
        "baseline_before": total,
        "baseline_after": total,
        "merged_offering_count": total,
        "merged_offering_set_sha256": offering_set_sha256(offerings),
        "shards": [
            {
                "shard_id": "east-campus",
                "openingSchoolNumber": "5063559",
                "raw_bundle_sha256": "b" * 64,
                "campus_acceptance_sha256": "b" * 64,
                "campus_source": f"capture://sysu/{semester}/campus/5063559",
                "campus_offering_set_sha256": offering_set_sha256(offerings),
                "page_count": 1,
                "loaded_count": total,
                "reported_total": total,
            }
        ],
    }


def _accepted_store(
    tmp_path: Path,
    *,
    offerings: list[CourseOffering] | None = None,
    digest: str | None = None,
    scope: SnapshotScope = FULL_SCOPE,
    semester: str = SEMESTER,
) -> tuple[Path, str]:
    """导入一份 acceptance 并返回 `(store, acceptance_sha)`。

    ⚠️ `full_semester` 的 identity **必须**由 canonical manifest 重算出来
    （immutable acceptance identity），因此本 helper 会构造 manifest；
    `campus` scope 沿用调用方给出的 raw artifact digest（无 manifest）。
    """

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
    snapshot = _snapshot(resolved, semester=semester)

    if scope.scope_kind == SCOPE_KIND_FULL_SEMESTER:
        manifest = _manifest_for(resolved, semester=semester)
        resolved_digest = compute_manifest_sha256(manifest)
        import_offering_snapshot(
            store,
            snapshot,
            artifact_sha256=resolved_digest,
            scope=scope,
            canonical_manifest=manifest,
        )
        return store, resolved_digest

    resolved_digest = digest or CAMPUS_ACCEPTANCE
    import_offering_snapshot(
        store, snapshot, artifact_sha256=resolved_digest, scope=scope
    )
    return store, resolved_digest


def _provider(path: Path, digest: str = ACCEPTANCE) -> StoreBackedCourseDataProvider:
    """构造 provider，并给出**测试专用**批准摘要。

    ⚠️ 本轮（F-01/F-03）起 provider 要求"带外批准锚点里记录的 manifest 摘要"。
    这些用例验证的是**批准门之后**的 content-bound 校验（计数 / membership /
    逐行指纹 / 整批 digest / 读取不缓存），因此这里提供 `digest` 作为批准值——
    它恰好就是这些合成夹具自己的 manifest 摘要。
    ⛔ 这不代表任何真实批准：没有锚点文件、也没有人。
    """

    return StoreBackedCourseDataProvider(
        sqlite_path=path, semester=SEMESTER, acceptance_sha256=digest,
        approved_manifest_sha256=(digest,) if _is_sha256(digest) else (),
        require_approval=_is_sha256(digest),
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


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
    provider = _provider(store, digest)

    assert provider.semester == SEMESTER
    assert provider.acceptance_sha256 == digest
    assert provider.expected_offering_count == 3
    assert provider.provenance.scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert provider.provenance.scope_id == SEMESTER

    offerings = provider.get_course_offerings(SEMESTER)
    assert [offering.class_id for offering in offerings] == ["A-01", "B-01", "C-01"]
    assert {offering.data_source for offering in offerings} == {DataSource.REAL}


def test_provider_structurally_satisfies_the_frozen_protocol(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

    assert isinstance(provider, CourseDataProvider)
    assert list(
        inspect.signature(CourseDataProvider.get_course_offerings).parameters
    ) == ["self", "semester"]
    assert list(inspect.signature(provider.get_course_offerings).parameters) == [
        "semester"
    ]


def test_provider_ordering_is_deterministic(tmp_path: Path) -> None:
    store, digest = _accepted_store(
        tmp_path,
        offerings=[
            _offering("SYN-Z", "Z-01"),
            _offering("SYN-A", "A-01"),
            _offering("SYN-M", "M-01"),
        ],
    )
    provider = _provider(store, digest)

    keys = [
        (offering.course_id, offering.class_id)
        for offering in provider.get_course_offerings(SEMESTER)
    ]
    assert keys == sorted(keys)


def test_provider_is_read_only_for_the_store(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

    before = load_course_data_provenance(store, semester=SEMESTER)
    provider.get_course_offerings(SEMESTER)
    provider.get_course_offerings(SEMESTER)
    after = load_course_data_provenance(store, semester=SEMESTER)

    assert before == after
    assert len(load_course_offerings(store, SEMESTER)) == 3


def test_orchestrator_receives_the_bound_offerings(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

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
        _provider(store, ACCEPTANCE)


def test_campus_only_store_is_rejected(tmp_path: Path) -> None:
    store, digest = _accepted_store(
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
    store, digest = _accepted_store(tmp_path)

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, OTHER_ACCEPTANCE)


def test_wrong_scope_kind_is_rejected(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    _tamper(
        store, "UPDATE course_data_acceptance SET scope_kind = ?", (SCOPE_KIND_CAMPUS,)
    )
    _tamper(store, "UPDATE course_data_import SET scope_kind = ?", (SCOPE_KIND_CAMPUS,))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


def test_wrong_scope_id_is_rejected(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    _tamper(store, "UPDATE course_data_acceptance SET scope_id = ?", (OTHER_SEMESTER,))
    _tamper(store, "UPDATE course_data_import SET scope_id = ?", (OTHER_SEMESTER,))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


def test_incomplete_provenance_is_rejected(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    _tamper(store, "UPDATE course_data_acceptance SET completeness = ?", ("partial",))
    _tamper(store, "UPDATE course_data_import SET completeness = ?", ("partial",))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


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
    store, digest = _accepted_store(tmp_path)
    _tamper(store, f"UPDATE course_data_acceptance SET {column} = ?", (value,))
    _tamper(store, f"UPDATE course_data_import SET {column} = ?", (value,))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


def test_store_with_zero_rows_is_not_ready(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path, offerings=[])

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


def test_two_planes_must_agree(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    _tamper(store, "DELETE FROM course_data_import", ())

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


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
    store, digest = _accepted_store(tmp_path)
    _tamper(
        store,
        f"UPDATE course_offering SET {column} = ? WHERE class_id = ?",
        (value, "B-01"),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


def test_store_with_tampered_membership_is_not_ready(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    _tamper(
        store,
        "DELETE FROM course_data_acceptance_member WHERE class_id = ?",
        ("C-01",),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


def test_deleted_row_is_rejected(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    _tamper(store, "DELETE FROM course_offering WHERE class_id = ?", ("A-01",))
    _tamper(
        store,
        "DELETE FROM course_data_acceptance_member WHERE class_id = ?",
        ("A-01",),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, digest)


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
    store, digest = _accepted_store(tmp_path)

    with pytest.raises(CourseDataStoreError):
        StoreBackedCourseDataProvider(
            sqlite_path=store,
            semester=semester,  # type: ignore[arg-type]
            acceptance_sha256=ACCEPTANCE,
        )


@pytest.mark.parametrize("digest", ["", "not-a-digest", "a" * 63, "z" * 64, None])
def test_invalid_acceptance_digest_is_rejected(tmp_path: Path, digest: object) -> None:
    store, _acceptance = _accepted_store(tmp_path)

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
    store, digest = _accepted_store(tmp_path)
    # 塞一条只有 campus provenance 的陈旧行（不属于本 acceptance）。
    import_offering_snapshot(
        store,
        _snapshot([_offering("SYN-STALE", "STALE-01")]),
        artifact_sha256=CAMPUS_ACCEPTANCE,
        scope=CAMPUS_SCOPE,
    )

    provider = _provider(store, digest)
    offerings = provider.get_course_offerings(SEMESTER)

    assert len(offerings) == 3
    assert "SYN-STALE" not in {offering.course_id for offering in offerings}
    # 整学期查询仍然能看到陈旧行 ⇒ 两者语义确实不同。
    assert len(load_course_offerings(store, SEMESTER)) == 4


def test_other_semester_rows_are_not_served(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
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

    provider = _provider(store, digest)
    offerings = provider.get_course_offerings(SEMESTER)

    assert {offering.semester for offering in offerings} == {SEMESTER}


def test_requesting_another_semester_fails_closed(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

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

    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)
    assert len(provider.get_course_offerings(SEMESTER)) == 3

    _tamper(store, "DELETE FROM course_data_acceptance", ())

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_import_record_removed_after_construction_fails_closed(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

    _tamper(store, "DELETE FROM course_data_import", ())

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_content_change_after_construction_fails_closed(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

    _tamper(
        store,
        "UPDATE course_offering SET course_name = ? WHERE class_id = ?",
        ("构造之后被替换", "C-01"),
    )

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_membership_change_after_construction_fails_closed(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

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

    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

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

    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

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
        store, semester=SEMESTER, acceptance_sha256=digest,
        approved_manifest_sha256=(digest,),
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


# --------------------------------------------------------------------------- #
# BLOCK: immutable acceptance identity（Codex 复现的攻击 → 回归）
# --------------------------------------------------------------------------- #


def test_same_sha_reimport_with_dataset_b_cannot_replace_dataset_a(tmp_path: Path) -> None:
    """Codex 攻击的回归：同一个 acceptance SHA 不得被第二次导入改写为 Dataset B。

    攻击（旧 `cb585c1`）：A 落库 → Provider 构造 → 用**同一个 SHA** 导入同数量 /
    同身份但 payload 不同的 B → store 刷新 acceptance / membership digest
    → **旧 Provider 返回 B**。

    修复后：
    ```text
    B + A 的 manifest（内容不符）      ⇒ reject
    B + B 的 manifest 但声称 SHA = X  ⇒ reject（manifest SHA ≠ identity）
    旧 Provider 下一次读取            ⇒ 仍然只能返回 A（或 fail closed）
    ```
    """

    snapshot_a = _snapshot([_offering("SYN-A", "A-01", course_name="DATASET_A")])
    manifest_a = _manifest_for(list(snapshot_a.offerings))
    digest_a = compute_manifest_sha256(manifest_a)

    store = tmp_path / "course-data.sqlite3"
    import_offering_snapshot(
        store,
        snapshot_a,
        artifact_sha256=digest_a,
        scope=FULL_SCOPE,
        canonical_manifest=manifest_a,
    )

    provider = _provider(store, digest_a)
    assert [offering.course_name for offering in provider.get_course_offerings(SEMESTER)] == [
        "DATASET_A"
    ]

    # Dataset B：同数量 / 同 identity，仅 payload 不同。
    snapshot_b = _snapshot(
        [_offering("SYN-A", "A-01", course_name="DATASET_B_TAMPERED")]
    )
    manifest_b = _manifest_for(list(snapshot_b.offerings))

    # (a) 同一个 SHA + A 的 manifest ⇒ reject
    with pytest.raises(CourseDataStoreError):
        import_offering_snapshot(
            store,
            snapshot_b,
            artifact_sha256=digest_a,
            scope=FULL_SCOPE,
            canonical_manifest=manifest_a,
        )

    # (b) 同一个 SHA + B 自己的 manifest ⇒ reject（manifest SHA 是另一个 identity）
    assert compute_manifest_sha256(manifest_b) != digest_a
    with pytest.raises(CourseDataStoreError):
        import_offering_snapshot(
            store,
            snapshot_b,
            artifact_sha256=digest_a,
            scope=FULL_SCOPE,
            canonical_manifest=manifest_b,
        )

    # 旧 Provider 仍然只能返回 A。
    assert [offering.course_name for offering in provider.get_course_offerings(SEMESTER)] == [
        "DATASET_A"
    ]
    assert "DATASET_B_TAMPERED" not in {
        offering.course_name for offering in provider.get_course_offerings(SEMESTER)
    }

    # 新构造的 Provider 同样如此。
    fresh = _provider(store, digest_a)
    assert [offering.course_name for offering in fresh.get_course_offerings(SEMESTER)] == [
        "DATASET_A"
    ]


def test_campus_scope_same_sha_reimport_is_rejected(tmp_path: Path) -> None:
    """没有 manifest 的 campus acceptance 由 immutability 兜底（同 SHA 不同内容 ⇒ reject）。"""

    store, digest = _accepted_store(
        tmp_path,
        offerings=[_offering("SYN-CAMPUS", "C-01", course_name="DATASET_A")],
        digest=CAMPUS_ACCEPTANCE,
        scope=CAMPUS_SCOPE,
    )

    with pytest.raises(ImmutableAcceptanceConflictError):
        import_offering_snapshot(
            store,
            _snapshot([_offering("SYN-CAMPUS", "C-01", course_name="DATASET_B")]),
            artifact_sha256=digest,
            scope=CAMPUS_SCOPE,
        )

    dataset = load_accepted_offerings(
        store, semester=SEMESTER, acceptance_sha256=digest, scope=CAMPUS_SCOPE,
        require_approval=False,
    )
    assert [offering.course_name for offering in dataset.offerings] == ["DATASET_A"]


def test_stored_manifest_rewrite_after_construction_fails_closed(tmp_path: Path) -> None:
    """DB 里把 canonical manifest 与 digest 一起 rewrite ⇒ 重算对不上 ⇒ 读取失败。"""

    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)
    assert len(provider.get_course_offerings(SEMESTER)) == 3

    manifest = _manifest_for(
        [_offering("SYN-A", "A-01"), _offering("SYN-B", "B-01"), _offering("SYN-C", "C-01")]
    )
    rewritten = dict(manifest)
    rewritten["inventory_sha256"] = "c" * 64
    rewritten_json = canonical_manifest_bytes(rewritten).decode("utf-8")

    connection = sqlite3.connect(str(store))
    connection.execute(
        "UPDATE course_data_acceptance SET canonical_manifest_json = ? "
        "WHERE artifact_sha256 = ?",
        (rewritten_json, digest),
    )
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_full_semester_acceptance_without_manifest_is_not_servable(tmp_path: Path) -> None:
    """⛔ 没有 canonical manifest 的 full_semester acceptance 不得装配 Provider。"""

    store = tmp_path / "course-data.sqlite3"
    import_offering_snapshot(
        store,
        _snapshot([_offering("SYN-A", "A-01")]),
        artifact_sha256=ACCEPTANCE,
        scope=FULL_SCOPE,
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(store, ACCEPTANCE)


def test_accepted_read_exposes_the_manifest_identity(tmp_path: Path) -> None:
    store, digest = _accepted_store(tmp_path)

    dataset = load_accepted_offerings(
        store, semester=SEMESTER, acceptance_sha256=digest,
        approved_manifest_sha256=(digest,),
    )

    assert dataset.acceptance.canonical_manifest_sha256 == digest


def test_acceptance_metadata_mutation_after_construction_fails_closed(tmp_path: Path) -> None:
    """列式 metadata 被改写（manifest 未动）⇒ 语义交叉核对失败。"""

    store, digest = _accepted_store(tmp_path)
    provider = _provider(store, digest)

    connection = sqlite3.connect(str(store))
    connection.execute(
        "UPDATE course_data_acceptance SET offering_count = 2 WHERE artifact_sha256 = ?",
        (digest,),
    )
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)
