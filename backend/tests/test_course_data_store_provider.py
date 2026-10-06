"""Store-backed CourseDataProvider tests (synthetic SQLite, zero-network)."""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from app.course_data import (
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    CourseDataAcceptanceError,
    CourseDataStoreError,
    ShardArtifact,
    SnapshotScope,
    StoreBackedCourseDataProvider,
    accept_full_semester_capture_set,
    import_offering_snapshot,
    initialize_course_data_store,
    load_course_data_provenance,
    load_course_offerings,
    load_course_offerings_for_acceptance,
)
from app.integration import PlanningOrchestrator
from app.integration.ports import CourseDataProvider
from app.models.contracts import PlanResult, Preference

SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
VALID_SCHEDULE = "1-8周/星期五/第5-6节/REDACTED/示例环节,"

SHARD_IDS = (
    "east-campus",
    "south-campus",
    "shenzhen-campus",
    "zhuhai-campus",
    "north-campus",
)
SHARD_NUMBERS = {
    "east-campus": "5063559",
    "south-campus": "5062201",
    "shenzhen-campus": "333291143",
    "zhuhai-campus": "5062203",
    "north-campus": "5062202",
}


def _row(
    *,
    course_number: str,
    class_number: str,
    semester: str = SEMESTER,
    course_name: str = "示例课程",
    schedule: str = VALID_SCHEDULE,
) -> dict[str, object]:
    return {
        "courseNum": course_number,
        "courseName": course_name,
        "classNumber": class_number,
        "yearTerm": semester,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": schedule,
    }


def _bundle(rows: list[dict[str, object]], *, semester: str = SEMESTER) -> dict[str, object]:
    return {
        "format": "sysu-opening-courses-capture-v1",
        "semester": semester,
        "first_page_no": 1,
        "page_size": 200,
        "pages": [
            {
                "page_no": 1,
                "response": {
                    "code": 200,
                    "data": {"total": len(rows), "rows": rows},
                },
            }
        ],
    }


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    return path


def _shard_rows(shard_id: str, count: int = 1) -> list[dict[str, object]]:
    return [
        _row(
            course_number=f"SYN-{shard_id.upper()}-{index:03d}",
            class_number=f"{shard_id}-{index:03d}",
        )
        for index in range(count)
    ]


def _accept_full_semester(
    directory: Path,
    *,
    rows_by_shard: dict[str, list[dict[str, object]]] | None = None,
    sqlite_path: Path | None = None,
):
    """写出五个 shard、跑正式 acceptance，并（可选）导入 SQLite。"""

    paths: dict[str, Path] = {}
    total = 0
    for shard_id in SHARD_IDS:
        rows = (
            rows_by_shard[shard_id]
            if rows_by_shard is not None and shard_id in rows_by_shard
            else _shard_rows(shard_id)
        )
        total += len(rows)
        paths[shard_id] = _write(directory / f"{shard_id}.json", _bundle(rows))

    acceptance = accept_full_semester_capture_set(
        expected_semester=SEMESTER,
        baseline_before=total,
        baseline_after=total,
        shard_artifacts=[
            ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
            for shard_id in SHARD_IDS
        ],
    )

    if sqlite_path is not None:
        import_offering_snapshot(
            sqlite_path,
            acceptance.merged,
            artifact_sha256=acceptance.manifest_sha256,
            scope=acceptance.scope,
        )

    return acceptance


def _accepted_store(tmp_path: Path, **kwargs: object) -> tuple[Path, object]:
    sqlite_path = tmp_path / "course-data.sqlite3"
    acceptance = _accept_full_semester(tmp_path / "captures", sqlite_path=sqlite_path, **kwargs)  # type: ignore[arg-type]
    return sqlite_path, acceptance


def _provider(sqlite_path: Path, acceptance: object) -> StoreBackedCourseDataProvider:
    return StoreBackedCourseDataProvider(
        sqlite_path=sqlite_path,
        semester=SEMESTER,
        acceptance_sha256=acceptance.manifest_sha256,  # type: ignore[attr-defined]
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
    sqlite_path, acceptance = _accepted_store(tmp_path)
    provider = _provider(sqlite_path, acceptance)

    assert provider.semester == SEMESTER
    assert provider.acceptance_sha256 == acceptance.manifest_sha256  # type: ignore[attr-defined]
    assert provider.expected_offering_count == 5
    assert provider.provenance.scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert provider.provenance.scope_id == SEMESTER

    offerings = provider.get_course_offerings(SEMESTER)
    assert len(offerings) == 5
    assert all(offering.semester == SEMESTER for offering in offerings)
    assert {offering.source for offering in offerings} == {
        acceptance.source  # type: ignore[attr-defined]
    }


def test_provider_structurally_satisfies_the_frozen_protocol(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    provider = _provider(sqlite_path, acceptance)

    # ⛔ Protocol 未被修改：签名仍是 `get_course_offerings(self, semester)`。
    assert isinstance(provider, CourseDataProvider)
    assert list(
        inspect.signature(CourseDataProvider.get_course_offerings).parameters
    ) == ["self", "semester"]
    assert list(inspect.signature(provider.get_course_offerings).parameters) == [
        "semester"
    ]


def test_provider_ordering_is_deterministic(tmp_path: Path) -> None:
    # 让 bundle 内行序与 (course_id, class_id) 排序不同。
    rows_by_shard = {
        shard_id: _shard_rows(shard_id) for shard_id in SHARD_IDS
    }
    rows_by_shard["east-campus"] = [
        _row(course_number="SYN-ZZZ", class_number="east-campus-zzz"),
        _row(course_number="SYN-AAA", class_number="east-campus-aaa"),
    ]

    sqlite_path, acceptance = _accepted_store(tmp_path, rows_by_shard=rows_by_shard)
    provider = _provider(sqlite_path, acceptance)

    keys = [
        (offering.course_id, offering.class_id)
        for offering in provider.get_course_offerings(SEMESTER)
    ]
    assert keys == sorted(keys)
    assert keys[0][0] == "SYN-AAA"


def test_provider_is_read_only_for_the_store(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    provider = _provider(sqlite_path, acceptance)

    before = load_course_data_provenance(sqlite_path, semester=SEMESTER)
    provider.get_course_offerings(SEMESTER)
    provider.get_course_offerings(SEMESTER)
    after = load_course_data_provenance(sqlite_path, semester=SEMESTER)

    assert before == after
    assert len(load_course_offerings(sqlite_path, SEMESTER)) == 5


def test_orchestrator_receives_the_bound_offerings(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    provider = _provider(sqlite_path, acceptance)

    seen: dict[str, object] = {}

    class _Curriculum:
        def get_makeup_tasks(self) -> list[object]:
            return []

    class _Planner:
        def plan(self, *, makeup_tasks, offerings, current_schedule, preference) -> PlanResult:
            seen["offerings"] = offerings
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
    assert len(seen["offerings"]) == 5  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# construction fail-closed matrix
# --------------------------------------------------------------------------- #


def test_missing_provenance_is_rejected(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "empty.sqlite3"
    initialize_course_data_store(sqlite_path)

    with pytest.raises(CourseDataAcceptanceError):
        StoreBackedCourseDataProvider(
            sqlite_path=sqlite_path, semester=SEMESTER, acceptance_sha256="a" * 64
        )


def test_campus_only_store_is_rejected(tmp_path: Path) -> None:
    from app.course_data import load_capture_bundle, collect_captured_pages_snapshot

    sqlite_path = tmp_path / "course-data.sqlite3"
    bundle_path = _write(
        tmp_path / "east.json", _bundle(_shard_rows("east-campus", 1))
    )
    snapshot = collect_captured_pages_snapshot(
        load_capture_bundle(bundle_path), source="capture://sysu/2026-1/campus/5063559"
    )
    import_offering_snapshot(
        sqlite_path,
        snapshot,
        artifact_sha256="c" * 64,
        scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id="5063559"),
    )

    # campus 记录存在，但**不是** full_semester acceptance。
    with pytest.raises(CourseDataAcceptanceError):
        StoreBackedCourseDataProvider(
            sqlite_path=sqlite_path, semester=SEMESTER, acceptance_sha256="c" * 64
        )


def test_wrong_acceptance_sha256_is_rejected(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)

    with pytest.raises(CourseDataAcceptanceError):
        StoreBackedCourseDataProvider(
            sqlite_path=sqlite_path, semester=SEMESTER, acceptance_sha256="b" * 64
        )


def test_wrong_scope_kind_is_rejected(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    _tamper(
        sqlite_path,
        "UPDATE course_data_import SET scope_kind = ?",
        (SCOPE_KIND_CAMPUS,),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(sqlite_path, acceptance)


def test_wrong_scope_id_is_rejected(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    _tamper(
        sqlite_path,
        "UPDATE course_data_import SET scope_id = ?",
        (OTHER_SEMESTER,),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(sqlite_path, acceptance)


def test_incomplete_provenance_is_rejected(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    _tamper(
        sqlite_path,
        "UPDATE course_data_import SET completeness = ?",
        ("partial",),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(sqlite_path, acceptance)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("loaded_count", 4),
        ("reported_total", 4),
        ("offering_count", 4),
        ("offering_count", 0),
        ("reported_total", None),
    ],
)
def test_inconsistent_counts_are_rejected(
    tmp_path: Path, column: str, value: object
) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    _tamper(
        sqlite_path,
        f"UPDATE course_data_import SET {column} = ?",
        (value,),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(sqlite_path, acceptance)


def test_row_count_mismatch_is_rejected(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    # 只把一行的 provenance 改掉：绑定的行少了一行，但 provenance 仍说 5。
    _tamper(
        sqlite_path,
        "UPDATE course_offering SET artifact_sha256 = ? WHERE class_id = ?",
        ("d" * 64, "east-campus-000"),
    )

    with pytest.raises(CourseDataAcceptanceError):
        _provider(sqlite_path, acceptance)


def test_deleted_row_is_rejected(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    _tamper(sqlite_path, "DELETE FROM course_offering WHERE class_id = ?", ("south-campus-000",))

    with pytest.raises(CourseDataAcceptanceError):
        _provider(sqlite_path, acceptance)


def test_tampered_meetings_are_rejected(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    _tamper(
        sqlite_path,
        "UPDATE course_offering SET meetings_json = ? WHERE class_id = ?",
        ("not-json", "east-campus-000"),
    )

    with pytest.raises(CourseDataStoreError):
        _provider(sqlite_path, acceptance)


def test_foreign_sqlite_file_is_rejected(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(str(foreign))
    connection.execute("CREATE TABLE unrelated (id INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataStoreError):
        StoreBackedCourseDataProvider(
            sqlite_path=foreign, semester=SEMESTER, acceptance_sha256="a" * 64
        )


def test_missing_sqlite_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CourseDataStoreError):
        StoreBackedCourseDataProvider(
            sqlite_path=tmp_path / "absent.sqlite3",
            semester=SEMESTER,
            acceptance_sha256="a" * 64,
        )


@pytest.mark.parametrize("semester", ["", "   ", None, 5])
def test_invalid_semester_is_rejected(tmp_path: Path, semester: object) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)

    with pytest.raises(CourseDataStoreError):
        StoreBackedCourseDataProvider(
            sqlite_path=sqlite_path,
            semester=semester,  # type: ignore[arg-type]
            acceptance_sha256=acceptance.manifest_sha256,  # type: ignore[attr-defined]
        )


@pytest.mark.parametrize("digest", ["", "not-a-digest", "a" * 63, "z" * 64, None])
def test_invalid_acceptance_digest_is_rejected(tmp_path: Path, digest: object) -> None:
    sqlite_path, _ = _accepted_store(tmp_path)

    with pytest.raises(CourseDataStoreError):
        StoreBackedCourseDataProvider(
            sqlite_path=sqlite_path,
            semester=SEMESTER,
            acceptance_sha256=digest,  # type: ignore[arg-type]
        )


def test_non_path_sqlite_argument_is_rejected() -> None:
    with pytest.raises(CourseDataAcceptanceError):
        StoreBackedCourseDataProvider(
            sqlite_path=123,  # type: ignore[arg-type]
            semester=SEMESTER,
            acceptance_sha256="a" * 64,
        )


# --------------------------------------------------------------------------- #
# isolation
# --------------------------------------------------------------------------- #


def test_stale_campus_rows_are_not_returned(tmp_path: Path) -> None:
    """旧的 campus import 行（不在 acceptance 里）必须被排除。"""

    from app.course_data import collect_captured_pages_snapshot, load_capture_bundle

    sqlite_path = tmp_path / "course-data.sqlite3"

    # 1) 先导入一个**只有旧行**的 campus artifact。
    stale_row = _row(course_number="SYN-STALE", class_number="stale-000")
    stale_bundle = _write(tmp_path / "stale.json", _bundle([stale_row]))
    stale_snapshot = collect_captured_pages_snapshot(
        load_capture_bundle(stale_bundle), source="capture://sysu/2026-1/campus/5063559"
    )
    import_offering_snapshot(
        sqlite_path,
        stale_snapshot,
        artifact_sha256="e" * 64,
        scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id="5063559"),
    )

    # 2) 再导入正式 full-semester acceptance（不含 stale 行）。
    acceptance = _accept_full_semester(tmp_path / "captures", sqlite_path=sqlite_path)

    provider = _provider(sqlite_path, acceptance)
    offerings = provider.get_course_offerings(SEMESTER)

    assert len(offerings) == 5
    assert "SYN-STALE" not in {offering.course_id for offering in offerings}
    # 整学期查询仍能看到陈旧行 ⇒ 证明两者语义确实不同。
    assert len(load_course_offerings(sqlite_path, SEMESTER)) == 6
    # 直接按 acceptance 读回也只给绑定的 5 行。
    assert (
        len(
            load_course_offerings_for_acceptance(
                sqlite_path,
                semester=SEMESTER,
                acceptance_sha256=acceptance.manifest_sha256,
            )
        )
        == 5
    )


def test_other_semester_rows_are_not_returned(tmp_path: Path) -> None:
    from app.course_data import collect_captured_pages_snapshot, load_capture_bundle

    sqlite_path = tmp_path / "course-data.sqlite3"

    other_bundle = _write(
        tmp_path / "other.json",
        _bundle(
            [_row(course_number="SYN-OTHER", class_number="other-000", semester=OTHER_SEMESTER)],
            semester=OTHER_SEMESTER,
        ),
    )
    other_snapshot = collect_captured_pages_snapshot(
        load_capture_bundle(other_bundle),
        source=f"capture://sysu/{OTHER_SEMESTER}/campus/5063559",
    )
    import_offering_snapshot(
        sqlite_path,
        other_snapshot,
        artifact_sha256="f" * 64,
        scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id="5063559"),
    )

    acceptance = _accept_full_semester(tmp_path / "captures", sqlite_path=sqlite_path)
    provider = _provider(sqlite_path, acceptance)

    offerings = provider.get_course_offerings(SEMESTER)
    assert len(offerings) == 5
    assert {offering.semester for offering in offerings} == {SEMESTER}


def test_requesting_another_semester_fails_closed(tmp_path: Path) -> None:
    sqlite_path, acceptance = _accepted_store(tmp_path)
    provider = _provider(sqlite_path, acceptance)

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(OTHER_SEMESTER)

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings("")

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(None)  # type: ignore[arg-type]


def test_rows_overwritten_after_construction_are_detected(tmp_path: Path) -> None:
    """构造之后有别的 import 覆盖了绑定行的 provenance ⇒ 读取时必须 fail closed。"""

    sqlite_path, acceptance = _accepted_store(tmp_path)
    provider = _provider(sqlite_path, acceptance)

    _tamper(
        sqlite_path,
        "UPDATE course_offering SET scope_kind = ?, artifact_sha256 = ? WHERE class_id = ?",
        (SCOPE_KIND_CAMPUS, "9" * 64, "zhuhai-campus-000"),
    )

    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_provider_module_has_no_network_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "course_data" / "store_provider.py"
    )
    source = module_path.read_text(encoding="utf-8")

    for forbidden in ("requests", "httpx", "urllib", "socket", "aiohttp", "http.client"):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source
