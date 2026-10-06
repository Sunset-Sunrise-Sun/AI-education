"""Five-shard full-semester Course Data acceptance tests (synthetic, zero-network).

Covers the Forward Red-Team fixes:

```text
B1  the exact bytes hashed == the exact bytes parsed
B2  the artifact is independently bound to a campus scope
    (approved capture inventory + imported campus acceptance record)
B3  the accepted dataset is content-bound (offering-set digest)
```
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from app.course_data import (
    APPROVED_FULL_SEMESTER_SHARDS,
    CAPTURE_INVENTORY_FORMAT,
    FullSemesterAcceptanceError,
    OfferingSnapshot,
    SCOPE_KIND_FULL_SEMESTER,
    ShardArtifact,
    SnapshotScope,
    accept_full_semester_capture_set,
    build_capture_inventory,
    campus_source_label,
    canonical_manifest_bytes,
    capture_inventory_bytes,
    collect_captured_pages_snapshot,
    compute_manifest_sha256,
    full_semester_scope,
    full_semester_source,
    import_offering_snapshot,
    load_capture_bundle_bytes,
    load_capture_inventory,
    offering_set_sha256,
    validate_full_semester_manifest_bytes,
)
from app.course_data.errors import CourseDataNormalizationError


SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
SECRET_SCHEDULE = "1-8周/星期五/第5-6节/REDACTED/SECRET-RAW-SCHEDULE-TOKEN,"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PATH = REPOSITORY_ROOT / "tools" / "sysu_course_offering_collector.js"

SHARD_IDS = tuple(shard.shard_id for shard in APPROVED_FULL_SEMESTER_SHARDS)
SHARD_NUMBERS = {
    shard.shard_id: shard.opening_school_number
    for shard in APPROVED_FULL_SEMESTER_SHARDS
}
PLACEHOLDER_DIGEST = "0" * 64


def _row(
    *,
    course_number: str,
    class_number: str,
    course_name: str = "示例课程",
    semester: str = SEMESTER,
    schedule: str | None = SECRET_SCHEDULE,
) -> dict[str, object]:
    row: dict[str, object] = {
        "courseNum": course_number,
        "courseName": course_name,
        "classNumber": class_number,
        "yearTerm": semester,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
    }
    if schedule is not None:
        row["teachingTimePlaceStr"] = schedule
    return row


def _rows(shard_id: str, count: int) -> list[dict[str, object]]:
    """一个 shard 的 `count` 条**互不重复**的 synthetic 教学班。"""

    return [
        _row(
            course_number=f"SYN-{shard_id.upper()}-{index:03d}",
            class_number=f"{shard_id}-{index:03d}",
        )
        for index in range(count)
    ]


def _bundle(
    rows: list[dict[str, object]],
    *,
    total: int | None = None,
    semester: str = SEMESTER,
    page_size: int = 200,
) -> dict[str, object]:
    return {
        "format": "sysu-opening-courses-capture-v1",
        "semester": semester,
        "first_page_no": 1,
        "page_size": page_size,
        "pages": [
            {
                "page_no": 1,
                "response": {
                    "code": 200,
                    "data": {
                        "total": len(rows) if total is None else total,
                        "rows": rows,
                    },
                },
            }
        ],
    }


def _write(path: Path, payload: object) -> bytes:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _counts(**overrides: int) -> dict[str, int]:
    counts = {shard_id: 1 for shard_id in SHARD_IDS}
    counts.update(overrides)
    return counts


def _write_shards(
    directory: Path,
    *,
    counts: dict[str, int] | None = None,
    rows_by_shard: dict[str, list[dict[str, object]]] | None = None,
    totals_by_shard: dict[str, int] | None = None,
    semesters_by_shard: dict[str, str] | None = None,
) -> dict[str, Path]:
    """写出五个 shard 的 bundle 文件，返回 shard_id → 路径。"""

    resolved_counts = counts if counts is not None else _counts()
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for shard_id in SHARD_IDS:
        rows = (
            rows_by_shard[shard_id]
            if rows_by_shard is not None and shard_id in rows_by_shard
            else _rows(shard_id, resolved_counts.get(shard_id, 0))
        )
        total = (
            totals_by_shard[shard_id]
            if totals_by_shard is not None and shard_id in totals_by_shard
            else None
        )
        semester = (
            semesters_by_shard[shard_id]
            if semesters_by_shard is not None and shard_id in semesters_by_shard
            else SEMESTER
        )
        path = directory / f"{shard_id}.json"
        _write(path, _bundle(rows, total=total, semester=semester))
        paths[shard_id] = path

    return paths


def _raw_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _campus_store(
    tmp_path: Path,
    paths: dict[str, Path],
    *,
    semester: str = SEMESTER,
    scope_overrides: dict[str, str] | None = None,
    source_overrides: dict[str, str] | None = None,
    skip: tuple[str, ...] = (),
    digest_overrides: dict[str, str] | None = None,
) -> Path:
    """把每个 shard 以 **campus scope** 正式导入一个独立 SQLite 库（B2 的信任来源）。"""

    store = tmp_path / "campus-acceptances.sqlite3"

    for shard_id in SHARD_IDS:
        if shard_id in skip:
            continue

        number = (
            scope_overrides[shard_id]
            if scope_overrides is not None and shard_id in scope_overrides
            else SHARD_NUMBERS[shard_id]
        )
        source = (
            source_overrides[shard_id]
            if source_overrides is not None and shard_id in source_overrides
            else campus_source_label(semester, number)
        )
        digest = (
            digest_overrides[shard_id]
            if digest_overrides is not None and shard_id in digest_overrides
            else _raw_digest(paths[shard_id])
        )

        try:
            bundle = load_capture_bundle_bytes(paths[shard_id].read_bytes())
            snapshot = collect_captured_pages_snapshot(bundle, source=source)
            import_offering_snapshot(
                store,
                snapshot,
                artifact_sha256=digest,
                scope=SnapshotScope(scope_kind="campus", scope_id=number),
            )
        except (CourseDataNormalizationError, ValueError):
            # 该 shard 本身无法形成 complete 快照（用于 partial / empty / 学期错配用例）。
            continue

    return store


def _inventory_path(
    tmp_path: Path,
    paths: dict[str, Path],
    *,
    semester: str = SEMESTER,
    digest_overrides: dict[str, str] | None = None,
    missing: tuple[str, ...] = (),
) -> Path:
    digests: dict[str, str] = {}
    for shard_id in SHARD_IDS:
        if shard_id in missing:
            digests[shard_id] = PLACEHOLDER_DIGEST
            continue
        digests[shard_id] = (
            digest_overrides[shard_id]
            if digest_overrides is not None and shard_id in digest_overrides
            else _raw_digest(paths[shard_id])
        )

    inventory = build_capture_inventory(semester, digests)
    path = tmp_path / "capture-inventory.json"
    path.write_bytes(capture_inventory_bytes(inventory))
    return path


def _artifacts(
    paths: dict[str, Path], *, order: tuple[str, ...] = SHARD_IDS
) -> list[ShardArtifact]:
    return [
        ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
        for shard_id in order
    ]


def _accept(
    directory: Path,
    *,
    counts: dict[str, int] | None = None,
    rows_by_shard: dict[str, list[dict[str, object]]] | None = None,
    totals_by_shard: dict[str, int] | None = None,
    semesters_by_shard: dict[str, str] | None = None,
    baseline_before: int | None = None,
    baseline_after: int | None = None,
    order: tuple[str, ...] = SHARD_IDS,
    semester: str = SEMESTER,
    missing_files: tuple[str, ...] = (),
    inventory_digest_overrides: dict[str, str] | None = None,
    campus_skip: tuple[str, ...] = (),
    campus_scope_overrides: dict[str, str] | None = None,
    campus_source_overrides: dict[str, str] | None = None,
    campus_digest_overrides: dict[str, str] | None = None,
    campus_store: Path | None = None,
    inventory_path: Path | None = None,
    artifacts: list[ShardArtifact] | None = None,
):
    resolved_counts = counts if counts is not None else _counts()
    paths = _write_shards(
        directory,
        counts=resolved_counts,
        rows_by_shard=rows_by_shard,
        totals_by_shard=totals_by_shard,
        semesters_by_shard=semesters_by_shard,
    )
    for shard_id in missing_files:
        paths[shard_id] = directory / f"{shard_id}-absent.json"

    if rows_by_shard is None:
        total = sum(resolved_counts.get(shard_id, 0) for shard_id in SHARD_IDS)
    else:
        total = sum(
            len(rows_by_shard[shard_id])
            if shard_id in rows_by_shard
            else resolved_counts.get(shard_id, 0)
            for shard_id in SHARD_IDS
        )
    if totals_by_shard is not None:
        total = sum(
            totals_by_shard.get(shard_id, resolved_counts.get(shard_id, 0))
            for shard_id in SHARD_IDS
        )

    if inventory_path is None:
        inventory_path = _inventory_path(
            directory,
            paths,
            semester=semester,
            digest_overrides=inventory_digest_overrides,
            missing=missing_files,
        )

    if campus_store is None:
        campus_store = _campus_store(
            directory,
            paths,
            semester=semester,
            scope_overrides=campus_scope_overrides,
            source_overrides=campus_source_overrides,
            skip=(*campus_skip, *missing_files),
            digest_overrides=campus_digest_overrides,
        )

    return accept_full_semester_capture_set(
        expected_semester=semester,
        baseline_before=total if baseline_before is None else baseline_before,
        baseline_after=total if baseline_after is None else baseline_after,
        shard_artifacts=artifacts if artifacts is not None else _artifacts(paths, order=order),
        inventory=load_capture_inventory(inventory_path),
        campus_store_path=campus_store,
    )


# --------------------------------------------------------------------------- #
# shard identity table
# --------------------------------------------------------------------------- #


def test_approved_full_semester_shards_match_the_collector_table() -> None:
    """⛔ 两侧各写一份 `openingSchoolNumber`，必须逐项一致（不允许悄悄漂移）。"""

    source = COLLECTOR_PATH.read_text(encoding="utf-8")
    block = re.search(r"var APPROVED_SHARDS = \[(.*?)\];", source, re.DOTALL)
    assert block is not None, "collector APPROVED_SHARDS table not found"

    pairs = re.findall(
        r'shard_id:\s*"([^"]+)",\s*openingSchoolNumber:\s*"([^"]+)"', block.group(1)
    )
    assert pairs, "collector APPROVED_SHARDS entries not parsed"

    collector_numbers = {name: number for name, number in pairs}

    assert len(pairs) == 5
    assert collector_numbers["东校园"] == SHARD_NUMBERS["east-campus"]
    assert collector_numbers["北校园"] == SHARD_NUMBERS["north-campus"]
    assert collector_numbers["南校园"] == SHARD_NUMBERS["south-campus"]
    assert collector_numbers["深圳校区"] == SHARD_NUMBERS["shenzhen-campus"]
    assert collector_numbers["珠海校区"] == SHARD_NUMBERS["zhuhai-campus"]


def test_scope_and_source_are_derived_from_the_semester_only() -> None:
    scope = full_semester_scope(SEMESTER)
    assert scope.scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert scope.scope_id == SEMESTER
    assert full_semester_source(SEMESTER) == f"capture://sysu/{SEMESTER}/full-semester/{SEMESTER}"
    assert (
        campus_source_label(SEMESTER, "5063559")
        == f"capture://sysu/{SEMESTER}/campus/5063559"
    )

    with pytest.raises(FullSemesterAcceptanceError) as blank_scope:
        full_semester_scope("   ")
    assert blank_scope.value.category == "invalid_semester"

    with pytest.raises(FullSemesterAcceptanceError) as blank_source:
        full_semester_source("")
    assert blank_source.value.category == "invalid_semester"

    with pytest.raises(FullSemesterAcceptanceError) as blank_semester:
        accept_full_semester_capture_set(
            expected_semester=" ",
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=[],
            inventory=None,  # type: ignore[arg-type]
            campus_store_path="unused.sqlite",
        )
    assert blank_semester.value.category == "invalid_semester"


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_happy_path_accepts_exact_five_shards(tmp_path: Path) -> None:
    acceptance = _accept(tmp_path)

    assert acceptance.semester == SEMESTER
    assert acceptance.merged.is_complete
    assert acceptance.merged.loaded_count == 5
    assert acceptance.merged.reported_total == 5
    assert acceptance.merged_offering_count == 5
    assert acceptance.baseline_before == acceptance.baseline_after == 5
    assert acceptance.scope.scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert acceptance.scope.scope_id == SEMESTER
    assert acceptance.source == full_semester_source(SEMESTER)
    assert acceptance.merged_offering_set_sha256 == offering_set_sha256(
        acceptance.merged.offerings
    )

    assert [record.shard_id for record in acceptance.shards] == list(SHARD_IDS)
    assert [record.loaded_count for record in acceptance.shards] == [1, 1, 1, 1, 1]
    assert [record.opening_school_number for record in acceptance.shards] == [
        SHARD_NUMBERS[shard_id] for shard_id in SHARD_IDS
    ]

    for record in acceptance.shards:
        assert record.campus_acceptance_sha256 == record.raw_bundle_sha256
        assert record.campus_source == campus_source_label(
            SEMESTER, record.opening_school_number
        )
        assert re.fullmatch(r"[0-9a-f]{64}", record.campus_offering_set_sha256)

    manifest = acceptance.manifest
    assert manifest["scope_kind"] == SCOPE_KIND_FULL_SEMESTER
    assert manifest["scope_id"] == SEMESTER
    assert manifest["manifest_version"] == 2
    assert manifest["merged_offering_count"] == 5
    assert manifest["merged_offering_set_sha256"] == acceptance.merged_offering_set_sha256
    assert manifest["inventory_sha256"] == acceptance.inventory_sha256
    assert manifest["baseline_before"] == manifest["baseline_after"] == 5
    assert len(manifest["shards"]) == 5  # type: ignore[arg-type]
    assert acceptance.manifest_sha256 == compute_manifest_sha256(manifest)


def test_manifest_passes_its_own_strict_validator(tmp_path: Path) -> None:
    acceptance = _accept(tmp_path)
    raw = canonical_manifest_bytes(acceptance.manifest)

    validated = validate_full_semester_manifest_bytes(raw)

    assert canonical_manifest_bytes(validated) == raw
    assert compute_manifest_sha256(validated) == acceptance.manifest_sha256


def test_accepted_offerings_are_real_and_share_the_full_semester_source(
    tmp_path: Path,
) -> None:
    acceptance = _accept(tmp_path)

    sources = {offering.source for offering in acceptance.merged.offerings}
    assert sources == {full_semester_source(SEMESTER)}

    from app.models.contracts import DataSource

    assert {offering.data_source for offering in acceptance.merged.offerings} == {
        DataSource.REAL
    }


def test_artifact_order_does_not_change_the_manifest(tmp_path: Path) -> None:
    first = _accept(tmp_path / "a", order=SHARD_IDS)
    second = _accept(tmp_path / "b", order=tuple(reversed(SHARD_IDS)))

    assert canonical_manifest_bytes(first.manifest) == canonical_manifest_bytes(
        second.manifest
    )
    assert first.manifest_sha256 == second.manifest_sha256


def test_shard_page_count_is_recorded_but_never_used_for_completeness(
    tmp_path: Path,
) -> None:
    acceptance = _accept(tmp_path)
    assert {record.page_count for record in acceptance.shards} == {1}
    assert acceptance.manifest["page_count_semantics"] == (
        "captured_pages_only_never_used_to_derive_completeness"
    )


# --------------------------------------------------------------------------- #
# B2: independent campus scope binding
# --------------------------------------------------------------------------- #


def test_relabeled_artifact_is_rejected_by_the_inventory_digest(tmp_path: Path) -> None:
    """East / South 文件互换（字节不变）⇒ 与已批准 inventory 不符。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    east, south = "east-campus", "south-campus"
    paths[east], paths[south] = paths[south], paths[east]

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "inventory_digest_mismatch"


def test_relabeled_campus_acceptance_is_rejected(tmp_path: Path) -> None:
    """把 East 的字节以 **South 的 campus scope** 导入，仍必须被拒绝。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)

    east_digest = _raw_digest(paths["east-campus"])
    # 恶意 / 误操作：East 的字节被声明成 south-campus（号码 5062201）。
    campus_store = _campus_store(
        tmp_path,
        paths,
        digest_overrides={"south-campus": east_digest},
        scope_overrides={"south-campus": SHARD_NUMBERS["east-campus"]},
        skip=("east-campus",),
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category in {
        "campus_acceptance_missing",
        "campus_acceptance_mismatch",
        "duplicate_artifact_bytes",
    }


def test_missing_campus_acceptance_record_is_rejected(tmp_path: Path) -> None:
    """artifact 与 inventory 都对，但没有对应的 campus acceptance ⇒ fail closed。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths, skip=("shenzhen-campus",))

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "campus_acceptance_missing"
    assert error.value.shard_id == "shenzhen-campus"


def test_campus_acceptance_with_arbitrary_source_label_is_rejected(
    tmp_path: Path,
) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(
        tmp_path,
        paths,
        source_overrides={"zhuhai-campus": "capture://sysu/2026-1/campus/whatever"},
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "campus_acceptance_mismatch"


def test_campus_acceptance_with_wrong_row_count_is_rejected(tmp_path: Path) -> None:
    """"行数碰巧相等 / 不相等"的替代 campus acceptance 都必须被拒绝。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    # 篡改 campus acceptance 的计数（保持 digest / scope 不变）。
    connection = sqlite3.connect(str(campus_store))
    connection.execute(
        "UPDATE course_data_acceptance SET offering_count = 99 "
        "WHERE scope_id = ? AND scope_kind = 'campus'",
        (SHARD_NUMBERS["north-campus"],),
    )
    connection.commit()
    connection.close()

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category in {
        "campus_acceptance_mismatch",
        "campus_acceptance_missing",
    }


def test_campus_acceptance_with_changed_content_digest_is_rejected(
    tmp_path: Path,
) -> None:
    """campus acceptance 的**内容** digest 与该 artifact 解析结果不符 ⇒ 拒绝（B3）。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    connection = sqlite3.connect(str(campus_store))
    connection.execute(
        "UPDATE course_data_acceptance SET offering_set_sha256 = ? WHERE scope_id = ?",
        ("f" * 64, SHARD_NUMBERS["east-campus"]),
    )
    connection.commit()
    connection.close()

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "campus_acceptance_mismatch"


def test_campus_acceptance_with_wrong_scope_id_is_rejected(tmp_path: Path) -> None:
    """只把 acceptance 记录的 scope_id 改成别的校区（digest / source / 内容不变）⇒ 拒绝（B2）。

    这正是"artifact 与 campus scope 必须独立绑定"的核心：⛔ 只靠调用方自称的
    label 或只靠 source 文本都不够。
    """

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    connection = sqlite3.connect(str(campus_store))
    connection.execute(
        "UPDATE course_data_acceptance SET scope_id = ? WHERE scope_id = ?",
        (SHARD_NUMBERS["south-campus"], SHARD_NUMBERS["east-campus"]),
    )
    connection.commit()
    connection.close()

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "campus_acceptance_mismatch"
    assert error.value.shard_id == "east-campus"


def test_one_digest_with_two_campus_records_is_rejected(tmp_path: Path) -> None:
    """同一批字节在同一学期留下**两条** campus acceptance ⇒ 拒绝（一份 artifact 一个 scope）。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)

    # 两次导入同一批字节：一次作为 East（正确号码），一次作为 South 的号码。
    campus_store = _campus_store(tmp_path, paths, skip=("south-campus",))
    east_digest = _raw_digest(paths["east-campus"])
    import_offering_snapshot(
        campus_store,
        collect_captured_pages_snapshot(
            load_capture_bundle_bytes(paths["east-campus"].read_bytes()),
            source=campus_source_label(SEMESTER, SHARD_NUMBERS["south-campus"]),
        ),
        artifact_sha256=east_digest,
        scope=SnapshotScope(
            scope_kind="campus", scope_id=SHARD_NUMBERS["south-campus"]
        ),
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "campus_acceptance_mismatch"


def test_campus_acceptance_record_with_tampered_source_is_rejected(
    tmp_path: Path,
) -> None:
    """只篡改 acceptance 记录的 source（内容不变）⇒ 仍必须被拒绝（B2 + 矩阵 17）。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    connection = sqlite3.connect(str(campus_store))
    connection.execute(
        "UPDATE course_data_acceptance SET source = ? WHERE scope_id = ?",
        ("capture://sysu/2026-1/campus/tampered", SHARD_NUMBERS["zhuhai-campus"]),
    )
    connection.commit()
    connection.close()

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "campus_acceptance_mismatch"
    assert error.value.shard_id == "zhuhai-campus"


def test_same_artifact_bytes_cannot_be_declared_as_two_campuses(tmp_path: Path) -> None:
    """同一批字节被声明成两个校区 ⇒ inventory 阶段就 fail closed。"""

    paths = _write_shards(tmp_path)
    east_digest = _raw_digest(paths["east-campus"])

    digests = {shard_id: _raw_digest(paths[shard_id]) for shard_id in SHARD_IDS}
    digests["south-campus"] = east_digest

    with pytest.raises(FullSemesterAcceptanceError) as error:
        build_capture_inventory(SEMESTER, digests)

    assert error.value.category == "duplicate_artifact_bytes"


def test_inventory_requires_the_approved_numbers(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)

    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["shards"][0]["openingSchoolNumber"] = "9999999"
    inventory.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        load_capture_inventory(inventory)

    assert error.value.category == "campus_acceptance_mismatch"


def test_inventory_rejects_unknown_fields_and_duplicate_keys(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    canonical = inventory.read_text(encoding="utf-8")

    payload = json.loads(canonical)
    payload["extra"] = "nope"
    inventory.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(FullSemesterAcceptanceError) as unknown_field:
        load_capture_inventory(inventory)
    assert unknown_field.value.category == "inventory_invalid"

    inventory.write_text(
        canonical.replace('"semester":"2026-1"', '"semester":"2026-1","semester":"2026-1"'),
        encoding="utf-8",
    )
    with pytest.raises(FullSemesterAcceptanceError) as duplicate_key:
        load_capture_inventory(inventory)
    assert duplicate_key.value.category in {"inventory_invalid", "manifest_invalid"}


def test_inventory_requires_exact_five_shards(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)

    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["shards"] = [entry for entry in payload["shards"] if entry["shard_id"] != "north-campus"]
    inventory.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        load_capture_inventory(inventory)

    assert error.value.category == "missing_shard"


def test_inventory_format_is_locked(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)

    payload = json.loads(inventory.read_text(encoding="utf-8"))
    assert payload["format"] == CAPTURE_INVENTORY_FORMAT

    payload["format"] = "some-other-format"
    inventory.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        load_capture_inventory(inventory)

    assert error.value.category == "inventory_invalid"


def test_inventory_must_be_canonical(tmp_path: Path) -> None:
    """inventory 是审核产物：非 canonical 形式（空白 / 顺序不同）必须被拒绝。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    canonical = inventory.read_text(encoding="utf-8")

    inventory.write_text(json.dumps(json.loads(canonical), indent=2), encoding="utf-8")

    with pytest.raises(FullSemesterAcceptanceError) as error:
        load_capture_inventory(inventory)

    assert error.value.category == "inventory_invalid"


def test_build_capture_inventory_requires_all_five_shards() -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        build_capture_inventory(SEMESTER, {"east-campus": "a" * 64})

    assert error.value.category == "inventory_invalid"

    with pytest.raises(FullSemesterAcceptanceError) as bad_digest:
        build_capture_inventory(
            SEMESTER,
            {shard_id: ("a" * 64 if shard_id != "north-campus" else "short") for shard_id in SHARD_IDS},
        )

    assert bad_digest.value.category == "inventory_invalid"


# --------------------------------------------------------------------------- #
# B1: hashed bytes == parsed bytes
# --------------------------------------------------------------------------- #


def test_hashed_bytes_and_parsed_bytes_are_the_same_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A/B/A 交错：解析必须使用**被 hash 的那批**字节（B1）。"""

    import app.course_data.full_semester_acceptance as module

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    east_path = paths["east-campus"]
    original_bytes = east_path.read_bytes()
    original_loader = module.load_capture_bundle_bytes

    state = {"swapped": False}

    def _swap_while_parsing(raw: bytes) -> object:
        if not state["swapped"]:
            state["swapped"] = True
            altered = json.loads(original_bytes.decode("utf-8"))
            altered["pages"][0]["response"]["data"]["rows"][0]["courseName"] = (
                "synthetic altered content"
            )
            # 文件在解析期间被换成 B，随后（finally）恢复 A。
            try:
                east_path.write_text(json.dumps(altered), encoding="utf-8")
                return original_loader(raw)
            finally:
                east_path.write_bytes(original_bytes)
        return original_loader(raw)

    monkeypatch.setattr(module, "load_capture_bundle_bytes", _swap_while_parsing)

    acceptance = accept_full_semester_capture_set(
        expected_semester=SEMESTER,
        baseline_before=5,
        baseline_after=5,
        shard_artifacts=_artifacts(paths),
        inventory=load_capture_inventory(inventory),
        campus_store_path=campus_store,
    )

    # ⛔ 解析结果必须来自被 hash 的 A 字节，而不是中途出现的 B。
    course_names = {offering.course_name for offering in acceptance.merged.offerings}
    assert "synthetic altered content" not in course_names
    assert acceptance.shards[0].raw_bundle_sha256 == hashlib.sha256(
        original_bytes
    ).hexdigest()
    # 复读探测：文件被改过 ⇒ 该次 acceptance 必须整体失败（而不是接受 B 的行）。
    # （本用例中 A 已恢复，所以这里走的是"解析到 A"的分支；见下一个用例。）


def test_bundle_changed_during_acceptance_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.course_data.full_semester_acceptance as module

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    east_path = paths["east-campus"]
    original_loader = module.load_capture_bundle_bytes
    state = {"swapped": False}

    def _loader(raw: bytes) -> object:
        bundle = original_loader(raw)
        if not state["swapped"]:
            state["swapped"] = True
            _write(east_path, _bundle(_rows("east-campus", 2)))
        return bundle

    monkeypatch.setattr(module, "load_capture_bundle_bytes", _loader)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "bundle_changed_during_acceptance"


def test_raw_bytes_change_does_not_change_the_identity(tmp_path: Path) -> None:
    """whitespace-only 变化会改变 raw digest ⇒ 与已批准 inventory 不符 ⇒ 拒绝（矩阵 15）。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    east_path = paths["east-campus"]
    east_path.write_bytes(east_path.read_bytes() + b"\n")

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "inventory_digest_mismatch"


def test_load_capture_bundle_bytes_rejects_bad_input() -> None:
    with pytest.raises(CourseDataNormalizationError):
        load_capture_bundle_bytes(b"\xff\xfe\x00")  # 非法 UTF-8

    with pytest.raises(CourseDataNormalizationError):
        load_capture_bundle_bytes(b"{ not json")

    with pytest.raises(CourseDataNormalizationError):
        load_capture_bundle_bytes(json.dumps({"format": "nope"}).encode("utf-8"))

    with pytest.raises(CourseDataNormalizationError):
        load_capture_bundle_bytes("not-bytes")  # type: ignore[arg-type]

    # 同一批字节 → 同一解析结果（确定性）。
    raw = json.dumps(_bundle(_rows("east-campus", 1))).encode("utf-8")
    assert load_capture_bundle_bytes(raw) == load_capture_bundle_bytes(raw)


# --------------------------------------------------------------------------- #
# exact five-shard set
# --------------------------------------------------------------------------- #


def test_missing_north_shard_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=[
                ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
                for shard_id in SHARD_IDS
                if shard_id != "north-campus"
            ],
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "missing_shard"
    assert "north-campus" in str(error.value)


@pytest.mark.parametrize(
    "missing", ["east-campus", "south-campus", "shenzhen-campus", "zhuhai-campus"]
)
def test_missing_any_single_shard_is_rejected(tmp_path: Path, missing: str) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=[
                ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
                for shard_id in SHARD_IDS
                if shard_id != missing
            ],
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "missing_shard"


def test_duplicate_shard_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    artifacts = _artifacts(paths)
    artifacts[1] = ShardArtifact(
        shard_id="east-campus", bundle_path=paths["east-campus"]
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "duplicate_shard"


@pytest.mark.parametrize(
    "unknown",
    ["north", "north-campus2", "北校园", "east_campus", "EAST-CAMPUS", "", "south-campus "],
)
def test_unknown_or_aliased_shard_is_rejected(tmp_path: Path, unknown: str) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    artifacts = _artifacts(paths)
    artifacts[4] = ShardArtifact(shard_id=unknown, bundle_path=paths["north-campus"])

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "unknown_shard"


def test_non_shard_artifact_inputs_are_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    with pytest.raises(FullSemesterAcceptanceError) as wrong_sequence:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts="not-a-sequence",  # type: ignore[arg-type]
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )
    assert wrong_sequence.value.category == "unknown_shard"

    artifacts = _artifacts(paths)
    artifacts[0] = paths["east-campus"]  # type: ignore[assignment]
    with pytest.raises(FullSemesterAcceptanceError) as wrong_element:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,  # type: ignore[arg-type]
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )
    assert wrong_element.value.category == "unknown_shard"


def test_missing_inventory_object_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    campus_store = _campus_store(tmp_path, paths)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory={"semester": SEMESTER},  # type: ignore[arg-type]
            campus_store_path=campus_store,
        )

    assert error.value.category == "inventory_invalid"


def test_inventory_for_another_semester_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths, semester=OTHER_SEMESTER)
    campus_store = _campus_store(tmp_path, paths)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "semester_mismatch"


# --------------------------------------------------------------------------- #
# baseline semantics
# --------------------------------------------------------------------------- #


def test_baseline_drift_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, baseline_before=5, baseline_after=6)

    assert error.value.category == "snapshot_window_unstable"


def test_sum_below_baseline_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, baseline_before=6, baseline_after=6)

    assert error.value.category == "shard_coverage_mismatch"


def test_sum_above_baseline_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, baseline_before=4, baseline_after=4)

    assert error.value.category == "shard_coverage_mismatch"


@pytest.mark.parametrize("value", [-1, True, "5", 1.5])
def test_non_integer_baseline_is_rejected(tmp_path: Path, value: object) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, baseline_before=value, baseline_after=5)

    assert error.value.category == "invalid_baseline"


def test_missing_baseline_is_rejected(tmp_path: Path) -> None:
    """`None`（缺失的 baseline）也必须 fail closed，⛔ 不被当成默认值。"""

    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=None,  # type: ignore[arg-type]
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "invalid_baseline"


def test_five_identical_empty_artifacts_are_rejected(tmp_path: Path) -> None:
    """五个**完全相同**的空 artifact ⇒ inventory 阶段就拒绝（字节不得声明成两个校区）。"""

    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, counts={shard_id: 0 for shard_id in SHARD_IDS})

    assert error.value.category == "duplicate_artifact_bytes"


# --------------------------------------------------------------------------- #
# per-shard artifact validation
# --------------------------------------------------------------------------- #


def test_missing_bundle_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, missing_files=("east-campus",))

    assert error.value.category == "bundle_read_failed"
    assert error.value.shard_id == "east-campus"


def test_expected_shard_digest_gate(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)
    digests = {shard_id: _raw_digest(path) for shard_id, path in paths.items()}

    artifacts = [
        ShardArtifact(
            shard_id=shard_id,
            bundle_path=paths[shard_id],
            expected_sha256=digests[shard_id].upper(),
        )
        for shard_id in SHARD_IDS
    ]
    acceptance = accept_full_semester_capture_set(
        expected_semester=SEMESTER,
        baseline_before=5,
        baseline_after=5,
        shard_artifacts=artifacts,
        inventory=load_capture_inventory(inventory),
        campus_store_path=campus_store,
    )
    assert acceptance.merged_offering_count == 5

    artifacts[2] = ShardArtifact(
        shard_id="shenzhen-campus",
        bundle_path=paths["shenzhen-campus"],
        expected_sha256="0" * 64,
    )
    with pytest.raises(FullSemesterAcceptanceError) as wrong_digest:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )
    assert wrong_digest.value.category == "bundle_digest_mismatch"


def test_bundle_digest_is_recorded_for_every_shard(tmp_path: Path) -> None:
    acceptance = _accept(tmp_path)

    for record in acceptance.shards:
        raw = (tmp_path / f"{record.shard_id}.json").read_bytes()
        assert record.raw_bundle_sha256 == hashlib.sha256(raw).hexdigest()
        assert re.fullmatch(r"[0-9a-f]{64}", record.raw_bundle_sha256)


def test_invalid_capture_bundle_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    _write(paths["east-campus"], {"format": "not-a-bundle"})
    # ⚠️ inventory 与 campus store 都按**当前**字节生成（"审核过这批字节"），
    #    因此失败必须来自 bundle 校验本身。
    inventory = _inventory_path(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths, skip=("east-campus",))

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
            inventory=load_capture_inventory(inventory),
            campus_store_path=campus_store,
        )

    assert error.value.category == "invalid_capture_bundle"


def test_semester_mismatch_in_one_shard_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, semesters_by_shard={"zhuhai-campus": OTHER_SEMESTER})

    assert error.value.category == "semester_mismatch"


def test_partial_shard_is_rejected_even_when_the_totals_still_add_up(
    tmp_path: Path,
) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(
            tmp_path,
            totals_by_shard={"south-campus": 3},
            baseline_before=7,
            baseline_after=7,
        )

    assert error.value.category == "shard_not_complete"


def test_partial_shard_with_mismatched_sum_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, totals_by_shard={"south-campus": 3})

    assert error.value.category == "shard_not_complete"


def test_empty_shard_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, rows_by_shard={"north-campus": []})

    assert error.value.category == "empty_shard"


# --------------------------------------------------------------------------- #
# identity merge invariants
# --------------------------------------------------------------------------- #


def _shared_row(*, course_name: str = "示例课程") -> dict[str, object]:
    return _row(
        course_number="SYN-SHARED",
        class_number="SHARED-01",
        course_name=course_name,
    )


def test_duplicate_identity_across_shards_is_rejected(tmp_path: Path) -> None:
    duplicated = _shared_row()

    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(
            tmp_path,
            rows_by_shard={
                "east-campus": [*_rows("east-campus", 1), duplicated],
                "south-campus": [duplicated],
            },
        )

    assert error.value.category == "duplicate_identity_across_shards"
    assert "SYN-SHARED" in str(error.value)
    assert "east-campus" in str(error.value)


def test_conflicting_identity_across_shards_is_rejected(tmp_path: Path) -> None:
    east = _shared_row(course_name="课程甲")
    south = _shared_row(course_name="课程乙")

    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(
            tmp_path,
            rows_by_shard={
                "east-campus": [*_rows("east-campus", 1), east],
                "south-campus": [south],
            },
        )

    assert error.value.category == "conflicting_identity_across_shards"
    assert "课程甲" not in str(error.value)
    assert "课程乙" not in str(error.value)


def test_merge_failure_from_the_low_level_function_is_reported_as_merge_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.course_data.full_semester_acceptance as module

    def _raise(*args: object, **kwargs: object) -> None:
        raise CourseDataNormalizationError("synthetic merge failure")

    monkeypatch.setattr(module, "merge_offering_snapshots", _raise)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path)

    assert error.value.category == "merge_failed"


def test_materialized_row_count_is_recounted_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ 不采信下层自报数字：物化后重新计数，行数不符即失败。"""

    import app.course_data.full_semester_acceptance as module

    def _shrink(snapshots: object, *, baseline_total: int) -> OfferingSnapshot:
        return OfferingSnapshot(
            semester=SEMESTER,
            offerings=(),
            completeness="complete",
            reported_total=0,
        )

    monkeypatch.setattr(module, "merge_offering_snapshots", _shrink)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path)

    assert error.value.category == "merged_count_mismatch"


# --------------------------------------------------------------------------- #
# manifest determinism / canonical form
# --------------------------------------------------------------------------- #


def test_manifest_is_deterministic_across_runs(tmp_path: Path) -> None:
    first = _accept(tmp_path / "one")
    second = _accept(tmp_path / "two")

    assert canonical_manifest_bytes(first.manifest) == canonical_manifest_bytes(
        second.manifest
    )
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.inventory_sha256 == second.inventory_sha256


def test_manifest_digest_changes_when_a_raw_bundle_changes(tmp_path: Path) -> None:
    baseline_run = _accept(tmp_path / "one")

    changed_rows = [
        _row(course_number="SYN-EAST-CAMPUS-999", class_number="east-campus-999")
    ]
    changed = _accept(tmp_path / "two", rows_by_shard={"east-campus": changed_rows})

    assert changed.merged_offering_count == baseline_run.merged_offering_count
    assert changed.manifest_sha256 != baseline_run.manifest_sha256

    recorded = {
        shard["shard_id"]: shard["raw_bundle_sha256"]
        for shard in baseline_run.manifest["shards"]  # type: ignore[union-attr]
    }
    re_recorded = {
        shard["shard_id"]: shard["raw_bundle_sha256"]
        for shard in changed.manifest["shards"]  # type: ignore[union-attr]
    }
    assert recorded["east-campus"] != re_recorded["east-campus"]
    assert recorded["south-campus"] == re_recorded["south-campus"]


def test_manifest_digest_changes_when_only_the_content_changes(tmp_path: Path) -> None:
    """B3：**同数量 / 同身份**的内容替换必须改变整批内容 digest。"""

    first = _accept(tmp_path / "one")
    # 保持五个 shard 的行数不变，只改 east 里那条的课程名。
    changed_east = [
        _row(
            course_number="SYN-EAST-CAMPUS-000",
            class_number="east-campus-000",
            course_name="内容被替换的示例课程",
        )
    ]
    second = _accept(tmp_path / "two", rows_by_shard={"east-campus": changed_east})

    assert first.merged_offering_count == second.merged_offering_count == 5
    assert {
        (offering.course_id, offering.class_id) for offering in first.merged.offerings
    } == {
        (offering.course_id, offering.class_id) for offering in second.merged.offerings
    }
    assert first.merged_offering_set_sha256 != second.merged_offering_set_sha256
    assert first.manifest_sha256 != second.manifest_sha256


def test_offering_set_digest_is_order_independent_and_content_bound() -> None:
    first = _row(course_number="SYN-A", class_number="A-01")
    second = _row(course_number="SYN-B", class_number="B-01")

    from app.course_data import import_opening_courses_response

    snapshot_a = import_opening_courses_response(
        {"code": 200, "data": {"total": 2, "rows": [first, second]}},
        semester=SEMESTER,
        source="capture://sysu/2026-1/full-semester/2026-1",
        completeness="complete",
    )
    snapshot_b = import_opening_courses_response(
        {"code": 200, "data": {"total": 2, "rows": [second, first]}},
        semester=SEMESTER,
        source="capture://sysu/2026-1/full-semester/2026-1",
        completeness="complete",
    )
    assert offering_set_sha256(snapshot_a.offerings) == offering_set_sha256(
        snapshot_b.offerings
    )

    mutated = import_opening_courses_response(
        {
            "code": 200,
            "data": {
                "total": 2,
                "rows": [first, {**second, "courseName": "被替换"}],
            },
        },
        semester=SEMESTER,
        source="capture://sysu/2026-1/full-semester/2026-1",
        completeness="complete",
    )
    assert offering_set_sha256(mutated.offerings) != offering_set_sha256(
        snapshot_a.offerings
    )
    # 空集合也有确定 digest（⛔ 不会被当成"未提供"），且任何一行都会改变它。
    assert offering_set_sha256(()) == hashlib.sha256(b"").hexdigest()
    assert offering_set_sha256(()) != offering_set_sha256(snapshot_a.offerings[:1])


def test_canonical_manifest_bytes_are_sorted_and_compact(tmp_path: Path) -> None:
    acceptance = _accept(tmp_path)
    payload = canonical_manifest_bytes(acceptance.manifest)

    assert payload == json.dumps(
        dict(acceptance.manifest),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert b", " not in payload
    assert b'": ' not in payload
    assert hashlib.sha256(payload).hexdigest() == acceptance.manifest_sha256


def test_canonical_manifest_bytes_rejects_non_mapping() -> None:
    with pytest.raises(FullSemesterAcceptanceError):
        canonical_manifest_bytes(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_manifest_validator_rejects_unknown_fields_and_bad_counts(
    tmp_path: Path,
) -> None:
    acceptance = _accept(tmp_path)
    manifest = dict(acceptance.manifest)

    with_extra = dict(manifest)
    with_extra["student_name"] = "should-not-be-here"
    with pytest.raises(FullSemesterAcceptanceError) as unknown:
        validate_full_semester_manifest_bytes(canonical_manifest_bytes(with_extra))
    assert unknown.value.category == "manifest_invalid"

    with_bool = dict(manifest)
    with_bool["merged_offering_count"] = True
    with pytest.raises(FullSemesterAcceptanceError) as bad_count:
        validate_full_semester_manifest_bytes(canonical_manifest_bytes(with_bool))
    assert bad_count.value.category == "manifest_invalid"

    wrong_version = dict(manifest)
    wrong_version["manifest_version"] = 1
    with pytest.raises(FullSemesterAcceptanceError) as bad_version:
        validate_full_semester_manifest_bytes(canonical_manifest_bytes(wrong_version))
    assert bad_version.value.category == "manifest_invalid"

    reordered = dict(manifest)
    reordered["shards"] = list(reversed(manifest["shards"]))  # type: ignore[arg-type]
    validated = validate_full_semester_manifest_bytes(canonical_manifest_bytes(reordered))
    assert canonical_manifest_bytes(validated) == canonical_manifest_bytes(manifest)


def test_manifest_validator_rejects_duplicate_keys_and_nan(tmp_path: Path) -> None:
    acceptance = _accept(tmp_path)
    payload = canonical_manifest_bytes(acceptance.manifest).decode("utf-8")

    duplicated = payload.replace('"semester":"2026-1"', '"semester":"2026-1","semester":"2026-1"')
    with pytest.raises(FullSemesterAcceptanceError):
        validate_full_semester_manifest_bytes(duplicated.encode("utf-8"))

    with pytest.raises(FullSemesterAcceptanceError):
        validate_full_semester_manifest_bytes(
            payload.replace('"baseline_before":5', '"baseline_before":NaN').encode("utf-8")
        )

    with pytest.raises(FullSemesterAcceptanceError):
        validate_full_semester_manifest_bytes(b"\xef\xbb\xbf" + payload.encode("utf-8"))


# --------------------------------------------------------------------------- #
# privacy
# --------------------------------------------------------------------------- #


def test_manifest_and_errors_never_leak_captured_values(tmp_path: Path) -> None:
    acceptance = _accept(tmp_path)
    payload = canonical_manifest_bytes(acceptance.manifest)

    assert b"SECRET-RAW-SCHEDULE-TOKEN" not in payload
    assert "示例课程".encode("utf-8") not in payload
    assert b"REDACTED" not in payload
    assert b"2026" in payload  # semester 本身是结构性信息

    duplicated = _shared_row()
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(
            tmp_path / "dup",
            rows_by_shard={
                "east-campus": [*_rows("east-campus", 1), duplicated],
                "south-campus": [duplicated],
            },
        )

    message = str(error.value)
    assert "SECRET-RAW-SCHEDULE-TOKEN" not in message
    assert "示例课程" not in message
    assert str(tmp_path) not in message
