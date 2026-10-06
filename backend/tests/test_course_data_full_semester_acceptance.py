"""Five-shard full-semester Course Data acceptance tests (synthetic, zero-network)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from app.course_data import (
    APPROVED_FULL_SEMESTER_SHARDS,
    SCOPE_KIND_FULL_SEMESTER,
    FullSemesterAcceptanceError,
    OfferingSnapshot,
    ShardArtifact,
    accept_full_semester_capture_set,
    canonical_manifest_bytes,
    compute_manifest_sha256,
    full_semester_scope,
    full_semester_source,
)
from app.course_data.errors import CourseDataNormalizationError


SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
SECRET_SCHEDULE = "1-8周/星期五/第5-6节/REDACTED/SECRET-RAW-SCHEDULE-TOKEN,"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PATH = REPOSITORY_ROOT / "tools" / "sysu_course_offering_collector.js"

SHARD_IDS = tuple(shard.shard_id for shard in APPROVED_FULL_SEMESTER_SHARDS)


def _row(
    *,
    course_number: str,
    class_number: str,
    course_name: str = "示例课程",
    semester: str = SEMESTER,
    schedule: str = SECRET_SCHEDULE,
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


def _artifacts(paths: dict[str, Path], *, order: tuple[str, ...] = SHARD_IDS) -> list[ShardArtifact]:
    return [ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id]) for shard_id in order]


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
):
    resolved_counts = counts if counts is not None else _counts()
    paths = _write_shards(
        directory,
        counts=resolved_counts,
        rows_by_shard=rows_by_shard,
        totals_by_shard=totals_by_shard,
        semesters_by_shard=semesters_by_shard,
    )

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

    return accept_full_semester_capture_set(
        expected_semester=semester,
        baseline_before=total if baseline_before is None else baseline_before,
        baseline_after=total if baseline_after is None else baseline_after,
        shard_artifacts=_artifacts(paths, order=order),
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
    expected = {
        shard.shard_id: shard.opening_school_number
        for shard in APPROVED_FULL_SEMESTER_SHARDS
    }

    assert len(pairs) == 5
    # 中文 shard 名 → slug 的对应关系由采集侧文档固定：东/北/南/深圳/珠海。
    assert collector_numbers["东校园"] == expected["east-campus"]
    assert collector_numbers["北校园"] == expected["north-campus"]
    assert collector_numbers["南校园"] == expected["south-campus"]
    assert collector_numbers["深圳校区"] == expected["shenzhen-campus"]
    assert collector_numbers["珠海校区"] == expected["zhuhai-campus"]


def test_scope_and_source_are_derived_from_the_semester_only() -> None:
    scope = full_semester_scope(SEMESTER)
    assert scope.scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert scope.scope_id == SEMESTER
    assert full_semester_source(SEMESTER) == f"capture://sysu/{SEMESTER}/full-semester/{SEMESTER}"

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

    assert [record.shard_id for record in acceptance.shards] == list(SHARD_IDS)
    assert [record.loaded_count for record in acceptance.shards] == [1, 1, 1, 1, 1]
    assert [record.opening_school_number for record in acceptance.shards] == [
        "5063559",
        "5062201",
        "333291143",
        "5062203",
        "5062202",
    ]

    manifest = acceptance.manifest
    assert manifest["scope_kind"] == SCOPE_KIND_FULL_SEMESTER
    assert manifest["scope_id"] == SEMESTER
    assert manifest["merged_offering_count"] == 5
    assert manifest["baseline_before"] == manifest["baseline_after"] == 5
    assert len(manifest["shards"]) == 5  # type: ignore[arg-type]
    assert acceptance.manifest_sha256 == compute_manifest_sha256(manifest)


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
    """合并顺序固定为已批准顺序 ⇒ 传入顺序不影响 acceptance identity。"""

    first = _accept(tmp_path / "a", order=SHARD_IDS)
    second = _accept(
        tmp_path / "b",
        order=tuple(reversed(SHARD_IDS)),
    )

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
# exact five-shard set
# --------------------------------------------------------------------------- #


def test_missing_north_shard_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    artifacts = [
        ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
        for shard_id in SHARD_IDS
        if shard_id != "north-campus"
    ]

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
        )

    assert error.value.category == "missing_shard"
    assert "north-campus" in str(error.value)


@pytest.mark.parametrize("missing", ["east-campus", "south-campus", "shenzhen-campus", "zhuhai-campus"])
def test_missing_any_single_shard_is_rejected(tmp_path: Path, missing: str) -> None:
    paths = _write_shards(tmp_path)
    artifacts = [
        ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
        for shard_id in SHARD_IDS
        if shard_id != missing
    ]

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
        )

    assert error.value.category == "missing_shard"


def test_missing_two_shards_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    artifacts = [
        ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
        for shard_id in SHARD_IDS
        if shard_id not in {"north-campus", "south-campus"}
    ]

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
        )

    assert error.value.category == "missing_shard"


def test_duplicate_shard_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
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
        )

    assert error.value.category == "duplicate_shard"


@pytest.mark.parametrize(
    "unknown",
    ["north", "north-campus2", "北校园", "east_campus", "EAST-CAMPUS", "", "south-campus "],
)
def test_unknown_or_aliased_shard_is_rejected(tmp_path: Path, unknown: str) -> None:
    paths = _write_shards(tmp_path)
    artifacts = _artifacts(paths)
    artifacts[4] = ShardArtifact(shard_id=unknown, bundle_path=paths["north-campus"])

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
        )

    assert error.value.category == "unknown_shard"


def test_six_shards_are_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    artifacts = _artifacts(paths)
    artifacts.append(
        ShardArtifact(shard_id="east-campus", bundle_path=paths["east-campus"])
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
        )

    assert error.value.category == "duplicate_shard"


def test_non_shard_artifact_inputs_are_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)

    with pytest.raises(FullSemesterAcceptanceError) as wrong_sequence:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts="not-a-sequence",  # type: ignore[arg-type]
        )
    assert wrong_sequence.value.category == "unknown_shard"

    artifacts = _artifacts(paths)
    artifacts[0] = (paths["east-campus"])  # type: ignore[assignment]
    with pytest.raises(FullSemesterAcceptanceError) as wrong_element:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,  # type: ignore[arg-type]
        )
    assert wrong_element.value.category == "unknown_shard"


# --------------------------------------------------------------------------- #
# baseline semantics
# --------------------------------------------------------------------------- #


def test_baseline_drift_is_rejected_before_reading_any_artifact(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    artifacts = _artifacts(paths)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=6,
            shard_artifacts=artifacts,
        )

    assert error.value.category == "snapshot_window_unstable"


def test_sum_below_baseline_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, baseline_before=6, baseline_after=6)

    assert error.value.category == "shard_coverage_mismatch"


def test_sum_above_baseline_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path, baseline_before=4, baseline_after=4)

    assert error.value.category == "shard_coverage_mismatch"


@pytest.mark.parametrize("value", [-1, True, "5", 1.5, None])
def test_non_integer_baseline_is_rejected(tmp_path: Path, value: object) -> None:
    paths = _write_shards(tmp_path)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=value,  # type: ignore[arg-type]
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
        )

    assert error.value.category == "invalid_baseline"


def test_zero_baseline_with_empty_shards_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(
            tmp_path,
            counts={shard_id: 0 for shard_id in SHARD_IDS},
        )

    assert error.value.category == "empty_shard"


# --------------------------------------------------------------------------- #
# per-shard artifact validation
# --------------------------------------------------------------------------- #


def test_missing_bundle_file_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    artifacts = _artifacts(paths)
    artifacts[0] = ShardArtifact(
        shard_id="east-campus", bundle_path=tmp_path / "does-not-exist.json"
    )

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
        )

    assert error.value.category == "bundle_read_failed"


def test_expected_shard_digest_gate(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    digests = {
        shard_id: hashlib.sha256(path.read_bytes()).hexdigest()
        for shard_id, path in paths.items()
    }

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
        )
    assert wrong_digest.value.category == "bundle_digest_mismatch"

    artifacts[2] = ShardArtifact(
        shard_id="shenzhen-campus",
        bundle_path=paths["shenzhen-campus"],
        expected_sha256=123,  # type: ignore[arg-type]
    )
    with pytest.raises(FullSemesterAcceptanceError) as non_string:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=artifacts,
        )
    assert non_string.value.category == "bundle_digest_mismatch"


def test_bundle_digest_is_recorded_for_every_shard(tmp_path: Path) -> None:
    acceptance = _accept(tmp_path)

    for record in acceptance.shards:
        raw = (tmp_path / f"{record.shard_id}.json").read_bytes()
        assert record.raw_bundle_sha256 == hashlib.sha256(raw).hexdigest()
        assert re.fullmatch(r"[0-9a-f]{64}", record.raw_bundle_sha256)


def test_invalid_capture_bundle_is_rejected(tmp_path: Path) -> None:
    paths = _write_shards(tmp_path)
    _write(paths["east-campus"], {"format": "not-a-bundle"})

    with pytest.raises(FullSemesterAcceptanceError) as error:
        accept_full_semester_capture_set(
            expected_semester=SEMESTER,
            baseline_before=5,
            baseline_after=5,
            shard_artifacts=_artifacts(paths),
        )

    assert error.value.category == "invalid_capture_bundle"


def test_semester_mismatch_in_one_shard_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(
            tmp_path,
            semesters_by_shard={"zhuhai-campus": OTHER_SEMESTER},
        )

    assert error.value.category == "semester_mismatch"


def test_partial_shard_is_rejected_even_when_the_totals_still_add_up(
    tmp_path: Path,
) -> None:
    """南校园只取到 total 的一部分：⛔ 不允许用"总数等式"掩盖不完整 shard。"""

    # south: 1 条已加载 / reported_total=3（partial）；其余各 1 条。
    # baseline 取 7 == Σ reported_total ⇒ 总和等式**成立**，
    # 但 partial shard 本身必须先被拒绝。
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
    rows = _rows("north-campus", 1)
    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(
            tmp_path,
            rows_by_shard={"north-campus": []},
        )

    assert error.value.category == "empty_shard"
    assert rows  # 其它 shard 仍有数据，空 shard 是唯一原因


# --------------------------------------------------------------------------- #
# identity merge invariants
# --------------------------------------------------------------------------- #


def test_duplicate_identity_across_shards_is_rejected(tmp_path: Path) -> None:
    duplicated = _row(course_number="SYN-SHARED", class_number="SHARED-01")

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
    east = _row(
        course_number="SYN-SHARED", class_number="SHARED-01", course_name="课程甲"
    )
    south = _row(
        course_number="SYN-SHARED", class_number="SHARED-01", course_name="课程乙"
    )

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


def test_bundle_changed_during_acceptance_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.course_data.full_semester_acceptance as module

    real_loader = module.load_capture_bundle
    state = {"touched": False}

    def _loader(path: object) -> object:
        bundle = real_loader(path)  # type: ignore[arg-type]
        if not state["touched"]:
            state["touched"] = True
            _write(Path(path), _bundle(_rows("north-campus", 2)))
        return bundle

    monkeypatch.setattr(module, "load_capture_bundle", _loader)

    with pytest.raises(FullSemesterAcceptanceError) as error:
        _accept(tmp_path)

    assert error.value.category == "bundle_changed_during_acceptance"


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


def test_manifest_digest_changes_when_a_raw_bundle_changes(tmp_path: Path) -> None:
    baseline_run = _accept(tmp_path / "one")

    # 同样的规模（总和不变），但东校园的内容不同 ⇒ 只有 raw bundle 摘要会变。
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

    duplicated = _row(course_number="SYN-SHARED", class_number="SHARED-01")
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
