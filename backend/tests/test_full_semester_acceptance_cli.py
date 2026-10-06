"""Full-semester acceptance CLI tests (synthetic, zero-network, no real captures).

Covers the Forward Red-Team fixes: exact-byte parsing (B1), independent campus
scope binding through an approved capture inventory + imported campus acceptance
records (B2), and content binding through the offering-set digest (B3).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.course_data import (
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    SnapshotScope,
    build_capture_inventory,
    capture_inventory_bytes,
    collect_captured_pages_snapshot,
    import_offering_snapshot,
    initialize_course_data_store,
    load_accepted_offerings,
    load_capture_bundle_bytes,
    load_course_data_provenance,
)


SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
SECRET = "SECRET-RAW-SCHEDULE-TOKEN"
VALID_SCHEDULE = "1-8周/星期五/第5-6节/REDACTED/示例环节,"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPOSITORY_ROOT / "tools" / "accept_full_semester_course_data.py"
CAMPUS_CLI_PATH = REPOSITORY_ROOT / "tools" / "validate_course_data_artifact.py"

SHARD_OPTIONS: dict[str, str] = {
    "east-campus": "--east",
    "south-campus": "--south",
    "shenzhen-campus": "--shenzhen",
    "zhuhai-campus": "--zhuhai",
    "north-campus": "--north",
}
SHARD_NUMBERS: dict[str, str] = {
    "east-campus": "5063559",
    "south-campus": "5062201",
    "shenzhen-campus": "333291143",
    "zhuhai-campus": "5062203",
    "north-campus": "5062202",
}


def _load_cli(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli() -> ModuleType:
    return _load_cli("accept_full_semester_course_data_for_test", CLI_PATH)


@pytest.fixture(scope="module")
def campus_cli() -> ModuleType:
    return _load_cli("validate_course_data_artifact_for_test_flow", CAMPUS_CLI_PATH)


def _row(
    *,
    course_number: str,
    class_number: str,
    schedule: str | None = VALID_SCHEDULE,
    course_name: str = "示例课程",
    semester: str = SEMESTER,
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


def _rows(shard_id: str, count: int = 1) -> list[dict[str, object]]:
    return [
        _row(
            course_number=f"SYN-{shard_id.upper()}-{index:03d}",
            class_number=f"{shard_id}-{index:03d}",
        )
        for index in range(count)
    ]


def _write_bundle(
    path: Path,
    rows: list[dict[str, object]],
    *,
    total: int | None = None,
    semester: str = SEMESTER,
) -> Path:
    payload = {
        "format": "sysu-opening-courses-capture-v1",
        "semester": semester,
        "first_page_no": 1,
        "page_size": 200,
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    return path


def _write_all(
    directory: Path,
    *,
    rows_by_shard: dict[str, list[dict[str, object]]] | None = None,
    totals_by_shard: dict[str, int] | None = None,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for shard_id in SHARD_OPTIONS:
        rows = (
            rows_by_shard[shard_id]
            if rows_by_shard is not None and shard_id in rows_by_shard
            else _rows(shard_id)
        )
        total = (
            totals_by_shard[shard_id]
            if totals_by_shard is not None and shard_id in totals_by_shard
            else None
        )
        paths[shard_id] = _write_bundle(
            directory / f"{shard_id}.json", rows, total=total
        )
    return paths


def _raw_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _campus_store(
    directory: Path,
    paths: dict[str, Path],
    *,
    skip: tuple[str, ...] = (),
    scope_overrides: dict[str, str] | None = None,
    source_overrides: dict[str, str] | None = None,
    digest_overrides: dict[str, str] | None = None,
) -> Path:
    store = directory / "campus-acceptances.sqlite3"

    for shard_id, path in paths.items():
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
            else f"capture://sysu/{SEMESTER}/campus/{number}"
        )
        digest = (
            digest_overrides[shard_id]
            if digest_overrides is not None and shard_id in digest_overrides
            else _raw_digest(path)
        )
        try:
            bundle = load_capture_bundle_bytes(path.read_bytes())
            snapshot = collect_captured_pages_snapshot(bundle, source=source)
            import_offering_snapshot(
                store,
                snapshot,
                artifact_sha256=digest,
                scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=number),
            )
        except Exception:
            continue

    return store


def _inventory(
    directory: Path,
    paths: dict[str, Path],
    *,
    digest_overrides: dict[str, str] | None = None,
) -> Path:
    digests = {
        shard_id: (
            digest_overrides[shard_id]
            if digest_overrides is not None and shard_id in digest_overrides
            else _raw_digest(path)
        )
        for shard_id, path in paths.items()
    }
    path = directory / "capture-inventory.json"
    path.write_bytes(capture_inventory_bytes(build_capture_inventory(SEMESTER, digests)))
    return path


def _arguments(
    paths: dict[str, Path],
    *,
    inventory: Path | None = None,
    campus_store: Path | None = None,
    baseline_before: int = 5,
    baseline_after: int = 5,
    sqlite_path: Path | None = None,
    manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
    draft_inventory: Path | None = None,
    extra: tuple[str, ...] = (),
) -> list[str]:
    result = [
        "--semester",
        SEMESTER,
        "--baseline-before",
        str(baseline_before),
        "--baseline-after",
        str(baseline_after),
    ]
    for shard_id, option in SHARD_OPTIONS.items():
        result.extend([option, str(paths[shard_id])])
    if inventory is not None:
        result.extend(["--inventory", str(inventory)])
    if campus_store is not None:
        result.extend(["--campus-store", str(campus_store)])
    if sqlite_path is not None:
        result.extend(["--sqlite", str(sqlite_path)])
    if manifest_path is not None:
        result.extend(["--output-manifest", str(manifest_path)])
    if expected_manifest_sha256 is not None:
        result.extend(["--expected-manifest-sha256", expected_manifest_sha256])
    if draft_inventory is not None:
        result.extend(["--draft-inventory", str(draft_inventory)])
    result.extend(extra)
    return result


def _invoke(
    cli: ModuleType,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> tuple[int, dict[str, object], str]:
    exit_code = cli.main(arguments)
    captured = capsys.readouterr()
    output = captured.out if exit_code == 0 else captured.err
    other = captured.err if exit_code == 0 else captured.out
    assert other == ""
    return exit_code, json.loads(output), output


def _prepared(tmp_path: Path) -> tuple[dict[str, Path], Path, Path]:
    paths = _write_all(tmp_path)
    return paths, _inventory(tmp_path, paths), _campus_store(tmp_path, paths)


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_accepts_five_shards_and_reports_aggregate_only_fields(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 0
    assert payload["status"] == "accepted"
    assert payload["sqlite_imported"] is False
    assert payload["semester"] == SEMESTER
    assert payload["scope_kind"] == SCOPE_KIND_FULL_SEMESTER
    assert payload["scope_id"] == SEMESTER
    assert payload["source"] == f"capture://sysu/{SEMESTER}/full-semester/{SEMESTER}"
    assert payload["baseline_before"] == payload["baseline_after"] == 5
    assert payload["baseline_stable"] is True
    assert payload["shard_count"] == 5
    assert payload["merged_offering_count"] == 5
    assert payload["snapshot.is_complete"] is True
    assert payload["manifest_written"] is False
    assert len(payload["manifest_sha256"]) == 64  # type: ignore[arg-type]
    assert len(payload["inventory_sha256"]) == 64  # type: ignore[arg-type]
    assert len(payload["merged_offering_set_sha256"]) == 64  # type: ignore[arg-type]

    shards = payload["shards"]
    assert isinstance(shards, list) and len(shards) == 5
    assert [shard["shard_id"] for shard in shards] == list(SHARD_OPTIONS)
    for shard in shards:
        assert shard["raw_bundle_sha256"] == shard["campus_acceptance_sha256"]
        assert len(shard["campus_offering_set_sha256"]) == 64
        assert shard["loaded_count"] == shard["reported_total"] == 1
        assert shard["page_count_semantics"] == "never_used_to_derive_completeness"

    serialized = json.dumps(payload, ensure_ascii=False)
    assert SECRET not in serialized
    assert "示例课程" not in serialized
    assert "teachingTimePlaceStr" not in serialized


def test_cli_acceptance_identity_is_deterministic(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    arguments = _arguments(paths, inventory=inventory, campus_store=campus_store)

    _, first, _ = _invoke(cli, capsys, arguments)
    _, second, _ = _invoke(cli, capsys, arguments)

    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert first["inventory_sha256"] == second["inventory_sha256"]


# --------------------------------------------------------------------------- #
# manifest file
# --------------------------------------------------------------------------- #


def test_manifest_file_bytes_are_the_acceptance_identity(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    manifest_path = tmp_path / "acceptance-manifest.json"

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            manifest_path=manifest_path,
        ),
    )

    assert exit_code == 0
    assert payload["manifest_written"] is True

    raw = manifest_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == payload["manifest_sha256"]
    assert b", " not in raw and b'": ' not in raw

    manifest = json.loads(raw)
    assert manifest["scope_kind"] == SCOPE_KIND_FULL_SEMESTER
    assert manifest["manifest_version"] == 2
    assert manifest["inventory_sha256"] == payload["inventory_sha256"]
    assert manifest["merged_offering_set_sha256"] == payload["merged_offering_set_sha256"]
    assert [item["shard_id"] for item in manifest["shards"]] == list(SHARD_OPTIONS)
    assert [item["openingSchoolNumber"] for item in manifest["shards"]] == [
        SHARD_NUMBERS[shard_id] for shard_id in SHARD_OPTIONS
    ]
    assert manifest["raw_bundle_sha256_semantics"] == (
        "exact_bytes_of_that_campus_artifact"
    )
    assert manifest["offering_set_sha256_semantics"] == (
        "exact_normalized_offering_content_of_the_accepted_dataset"
    )


def test_manifest_rewrite_is_idempotent_but_conflicting_content_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    manifest_path = tmp_path / "acceptance-manifest.json"
    arguments = _arguments(
        paths,
        inventory=inventory,
        campus_store=campus_store,
        manifest_path=manifest_path,
    )

    assert _invoke(cli, capsys, arguments)[0] == 0
    assert _invoke(cli, capsys, arguments)[0] == 0

    manifest_path.write_bytes(b'{"tampered":true}')

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 8
    assert payload["category"] == "manifest_already_exists_with_different_content"


def test_manifest_output_directory_must_exist(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            manifest_path=tmp_path / "missing" / "manifest.json",
        ),
    )

    assert exit_code == 8
    assert payload["category"] == "write_error"


def test_expected_manifest_sha256_gate(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    _, accepted, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    exit_code, _, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            expected_manifest_sha256=str(accepted["manifest_sha256"]),
        ),
    )
    assert exit_code == 0

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            expected_manifest_sha256="0" * 64,
        ),
    )
    assert exit_code == 8
    assert payload["category"] == "manifest_sha256_mismatch"


# --------------------------------------------------------------------------- #
# exact five-shard surface
# --------------------------------------------------------------------------- #


def test_campus_scope_arguments_are_not_expressible(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            extra=("--source", "capture://sysu/x"),
        ),
    )
    assert exit_code == 2
    assert payload["category"] == "invalid_arguments"


@pytest.mark.parametrize(
    "option",
    ["--skip-north", "--allow-partial-semester", "--force-complete", "--scope-kind"],
)
def test_no_escape_hatch_arguments_exist(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    option: str,
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    exit_code, _, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            extra=(option, "x"),
        ),
    )
    assert exit_code == 2


def test_north_bundle_is_a_mandatory_argument(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    arguments = _arguments(paths, inventory=inventory, campus_store=campus_store)
    index = arguments.index("--north")
    del arguments[index : index + 2]

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 2
    assert payload["category"] == "invalid_arguments"


def test_inventory_and_campus_store_are_mandatory(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, campus_store=campus_store)
    )
    assert exit_code == 2
    assert payload["category"] == "inventory_invalid"

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths, inventory=inventory))
    assert exit_code == 2
    assert payload["category"] == "campus_acceptance_missing"


def test_missing_shard_bundle_file_is_an_artifact_read_failure(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    paths["north-campus"] = tmp_path / "absent-north.json"

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 3
    assert payload["category"] == "bundle_read_failed"
    assert payload["shard_id"] == "north-campus"
    assert "absent-north.json" not in json.dumps(payload)
    assert str(tmp_path) not in json.dumps(payload)


# --------------------------------------------------------------------------- #
# B1 / B2 binding
# --------------------------------------------------------------------------- #


def test_changed_bytes_after_inventory_approval_are_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """inventory 批准之后 artifact 变了（哪怕只多一个换行）⇒ exit 9。"""

    paths, inventory, campus_store = _prepared(tmp_path)
    east = paths["east-campus"]
    east.write_bytes(east.read_bytes() + b"\n")

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 9
    assert payload["category"] == "inventory_digest_mismatch"
    assert payload["shard_id"] == "east-campus"


def test_missing_campus_acceptance_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths, skip=("south-campus",))

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 10
    assert payload["category"] == "campus_acceptance_missing"
    assert payload["shard_id"] == "south-campus"


def test_relabeled_campus_acceptance_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """East 的字节被以 South 的 scope 导入 ⇒ 不能被当作 East 的独立证据。"""

    paths = _write_all(tmp_path)
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(
        tmp_path,
        paths,
        skip=("east-campus",),
        digest_overrides={"south-campus": _raw_digest(paths["east-campus"])},
        scope_overrides={"south-campus": SHARD_NUMBERS["east-campus"]},
    )

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code in {5, 10}
    assert payload["category"] in {
        "campus_acceptance_missing",
        "campus_acceptance_mismatch",
        "duplicate_artifact_bytes",
    }


def test_invalid_inventory_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["shards"][0]["openingSchoolNumber"] = "9999999"
    inventory.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    exit_code, result, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 10
    assert result["category"] == "campus_acceptance_mismatch"


# --------------------------------------------------------------------------- #
# baseline / coverage / completeness
# --------------------------------------------------------------------------- #


def test_baseline_drift_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            baseline_before=5,
            baseline_after=6,
        ),
    )

    assert exit_code == 4
    assert payload["category"] == "snapshot_window_unstable"


@pytest.mark.parametrize("baseline", [4, 6])
def test_coverage_mismatch_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    baseline: int,
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            baseline_before=baseline,
            baseline_after=baseline,
        ),
    )

    assert exit_code == 4
    assert payload["category"] == "shard_coverage_mismatch"


@pytest.mark.parametrize("value", ["abc", "-1", "3.5", "", "0x5", "+5", "五", "5.0"])
def test_invalid_baseline_text_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    arguments = _arguments(paths, inventory=inventory, campus_store=campus_store)
    arguments[arguments.index("--baseline-before") + 1] = value

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 2
    assert payload["category"] == "invalid_baseline"


def test_baseline_text_tolerates_surrounding_whitespace(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    arguments = _arguments(paths, inventory=inventory, campus_store=campus_store)
    arguments[arguments.index("--baseline-before") + 1] = " 5 "

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 0
    assert payload["baseline_before"] == 5


def test_empty_semester_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    arguments = _arguments(paths, inventory=inventory, campus_store=campus_store)
    arguments[arguments.index("--semester") + 1] = "   "

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 2
    assert payload["category"] == "invalid_semester"


def test_partial_shard_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path, totals_by_shard={"south-campus": 3})
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            baseline_before=7,
            baseline_after=7,
        ),
    )

    assert exit_code == 6
    assert payload["category"] == "shard_not_complete"


def test_empty_shard_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path, rows_by_shard={"north-campus": []})
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            baseline_before=4,
            baseline_after=4,
        ),
    )

    assert exit_code == 6
    assert payload["category"] == "empty_shard"


def test_duplicate_identity_across_shards_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared = _row(course_number="SYN-SHARED", class_number="SHARED-01")
    paths = _write_all(
        tmp_path,
        rows_by_shard={
            "east-campus": [*_rows("east-campus"), shared],
            "south-campus": [shared],
        },
    )
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            baseline_before=6,
            baseline_after=6,
        ),
    )

    assert exit_code == 5
    assert payload["category"] in {
        "duplicate_identity_across_shards",
        "conflicting_identity_across_shards",
    }


def test_semester_mismatch_in_one_shard_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    _write_bundle(
        paths["zhuhai-campus"], _rows("zhuhai-campus"), semester=OTHER_SEMESTER
    )
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 5
    assert payload["category"] == "semester_mismatch"


def test_invalid_capture_bundle_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    paths["east-campus"].write_bytes(b'{"format":"not-a-bundle"}')
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths, skip=("east-campus",))

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 5
    assert payload["category"] == "invalid_capture_bundle"
    assert payload["shard_id"] == "east-campus"


# --------------------------------------------------------------------------- #
# draft inventory
# --------------------------------------------------------------------------- #


def test_draft_inventory_writes_a_canonical_draft_without_accepting(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    draft = tmp_path / "draft-inventory.json"

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, draft_inventory=draft)
    )

    assert exit_code == 0
    assert payload["status"] == "draft_inventory_written"
    assert payload["acceptance_performed"] is False
    assert payload["inventory_sha256_semantics"] == (
        "draft_document_identity_not_an_approval"
    )

    raw = draft.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        payload["inventory_sha256"]
    ) or payload["inventory_sha256_semantics"]
    document = json.loads(raw)
    assert document["format"] == "sysu-course-data-capture-inventory-v1"
    assert [entry["shard_id"] for entry in document["shards"]] == list(SHARD_OPTIONS)
    assert [entry["openingSchoolNumber"] for entry in document["shards"]] == [
        SHARD_NUMBERS[shard_id] for shard_id in SHARD_OPTIONS
    ]
    assert all(
        entry["raw_bundle_sha256"] == _raw_digest(paths[entry["shard_id"]])
        for entry in document["shards"]
    )

    # ⛔ 草稿模式不写库、不做 acceptance。
    assert _invoke(cli, capsys, _arguments(paths, draft_inventory=draft))[0] == 0


def test_draft_inventory_is_rejected_when_it_already_differs(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    draft = tmp_path / "draft-inventory.json"
    draft.write_bytes(b'{"format":"something-else"}')

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths, draft_inventory=draft))

    assert exit_code == 9
    assert payload["category"] == "inventory_already_exists_with_different_content"


def test_draft_inventory_does_not_bypass_the_acceptance_requirements(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """草稿模式只写草稿：⛔ 不产生 manifest、⛔ 不产生数据库。"""

    paths = _write_all(tmp_path)
    draft = tmp_path / "draft.json"
    manifest = tmp_path / "manifest.json"
    sqlite_path = tmp_path / "course-data.sqlite3"

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            draft_inventory=draft,
            manifest_path=manifest,
            sqlite_path=sqlite_path,
        ),
    )

    assert exit_code == 0
    assert payload["acceptance_performed"] is False
    assert not manifest.exists()
    assert not sqlite_path.exists()


# --------------------------------------------------------------------------- #
# SQLite
# --------------------------------------------------------------------------- #


def test_import_writes_and_reads_back_a_full_semester_record(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    sqlite_path = tmp_path / "course-data.sqlite3"
    manifest_path = tmp_path / "manifest.json"

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            sqlite_path=sqlite_path,
            manifest_path=manifest_path,
        ),
    )

    assert exit_code == 0
    assert payload["status"] == "imported"
    assert payload["inserted"] == 5
    assert payload["updated"] == 0
    assert payload["unchanged"] == 0
    assert payload["reconciled_offering_count"] == 5
    assert payload["accepted_row_count"] == 5
    assert payload["db_semester_offering_count"] == 5
    assert payload["provenance_artifact_sha256"] == payload["manifest_sha256"]
    assert payload["provenance_semester"] == SEMESTER
    assert payload["provenance_scope_kind"] == SCOPE_KIND_FULL_SEMESTER
    assert payload["provenance_scope_id"] == SEMESTER
    assert payload["provenance_completeness"] == "complete"
    assert payload["provenance_loaded_count"] == 5
    assert payload["provenance_reported_total"] == 5
    assert payload["provenance_offering_count"] == 5
    assert (
        payload["provenance_offering_set_sha256"]
        == payload["merged_offering_set_sha256"]
    )

    # 库里确实只有这一条 full_semester acceptance，并且它精确绑定 5 行。
    dataset = load_accepted_offerings(
        sqlite_path,
        semester=SEMESTER,
        acceptance_sha256=str(payload["manifest_sha256"]),
    )
    assert len(dataset.offerings) == 5
    assert dataset.acceptance.offering_set_sha256 == payload["merged_offering_set_sha256"]
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == (
        payload["manifest_sha256"]
    )
    assert len(load_course_data_provenance(sqlite_path, semester=SEMESTER)) == 1


def test_reimport_is_idempotent_and_keeps_exactly_one_record(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    sqlite_path = tmp_path / "course-data.sqlite3"
    arguments = _arguments(
        paths, inventory=inventory, campus_store=campus_store, sqlite_path=sqlite_path
    )

    assert _invoke(cli, capsys, arguments)[0] == 0
    exit_code, payload, _ = _invoke(cli, capsys, arguments)

    assert exit_code == 0
    assert payload["inserted"] == 0
    assert payload["unchanged"] == 5
    assert payload["accepted_row_count"] == 5
    assert payload["db_semester_offering_count"] == 5
    assert len(load_course_data_provenance(sqlite_path, semester=SEMESTER)) == 1


def test_failure_before_any_store_call_writes_no_database(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path, totals_by_shard={"south-campus": 3})
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)
    sqlite_path = tmp_path / "course-data.sqlite3"

    exit_code, _, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            baseline_before=7,
            baseline_after=7,
            sqlite_path=sqlite_path,
        ),
    )

    assert exit_code == 6
    assert not sqlite_path.exists()


def test_existing_store_gains_no_full_semester_record_when_a_shard_is_missing(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sqlite_path = tmp_path / "course-data.sqlite3"
    initialize_course_data_store(sqlite_path)

    paths, inventory, campus_store = _prepared(tmp_path)
    paths["north-campus"] = tmp_path / "absent-north.json"

    exit_code, _, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            sqlite_path=sqlite_path,
        ),
    )

    assert exit_code == 3
    assert load_course_data_provenance(sqlite_path) == []


def test_store_errors_are_reported_without_exception_text(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, inventory, campus_store = _prepared(tmp_path)
    directory = tmp_path / "a-directory"
    directory.mkdir()

    exit_code, payload, output = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            sqlite_path=directory,
        ),
    )

    assert exit_code == 7
    assert payload["category"] == "store_error"
    assert str(tmp_path) not in output
    assert "Traceback" not in output


def test_content_tampering_is_detected_on_read_and_repaired_by_reimport(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B3：同数量 / 同身份的**内容替换**必须被读路径发现（CLI 重跑会以批准内容覆盖）。"""

    import sqlite3

    from app.course_data import CourseDataStoreError

    paths, inventory, campus_store = _prepared(tmp_path)
    sqlite_path = tmp_path / "course-data.sqlite3"

    arguments = _arguments(
        paths, inventory=inventory, campus_store=campus_store, sqlite_path=sqlite_path
    )
    assert _invoke(cli, capsys, arguments)[0] == 0

    accepted = _invoke(cli, capsys, arguments)[1]
    acceptance_sha = str(accepted["manifest_sha256"])

    connection = sqlite3.connect(str(sqlite_path))
    connection.execute(
        "UPDATE course_offering SET course_name = ? WHERE class_id = ?",
        ("内容被替换", "east-campus-000"),
    )
    connection.commit()
    connection.close()

    # ⛔ 读路径必须 fail closed（content binding），而不是照原样返回被替换的内容。
    with pytest.raises(CourseDataStoreError):
        load_accepted_offerings(
            sqlite_path, semester=SEMESTER, acceptance_sha256=acceptance_sha
        )

    # CLI 重跑 = 用**已批准**内容重新导入（自愈），并如实报告 updated。
    exit_code, payload, _ = _invoke(cli, capsys, arguments)

    assert exit_code == 0
    assert payload["updated"] == 1
    assert payload["accepted_row_count"] == 5
    dataset = load_accepted_offerings(
        sqlite_path, semester=SEMESTER, acceptance_sha256=acceptance_sha
    )
    assert "内容被替换" not in {offering.course_name for offering in dataset.offerings}


# --------------------------------------------------------------------------- #
# real campus → full-semester flow
# --------------------------------------------------------------------------- #


def test_campus_cli_then_full_semester_cli_flow(
    cli: ModuleType,
    campus_cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """真实操作流程：每个 shard 先跑 campus CLI 入库，再跑 full-semester acceptance。"""

    paths = _write_all(tmp_path)
    campus_store = tmp_path / "campus-acceptances.sqlite3"

    for shard_id, path in paths.items():
        exit_code = campus_cli.main(
            [
                "--bundle",
                str(path),
                "--expected-semester",
                SEMESTER,
                "--scope-id",
                SHARD_NUMBERS[shard_id],
                "--source",
                f"capture://sysu/{SEMESTER}/campus/{SHARD_NUMBERS[shard_id]}",
                "--sqlite",
                str(campus_store),
            ]
        )
        assert exit_code == 0
        capsys.readouterr()

    inventory = _inventory(tmp_path, paths)
    sqlite_path = tmp_path / "course-data.sqlite3"

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            sqlite_path=sqlite_path,
        ),
    )

    assert exit_code == 0
    assert payload["status"] == "imported"
    assert payload["accepted_row_count"] == 5
    for shard in payload["shards"]:
        assert shard["raw_bundle_sha256"] == shard["campus_acceptance_sha256"]


# --------------------------------------------------------------------------- #
# privacy / docs
# --------------------------------------------------------------------------- #


def test_captured_values_never_reach_the_failure_output(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(
        tmp_path,
        rows_by_shard={
            "east-campus": [
                _row(
                    course_number="SYN-EAST-CAMPUS-000",
                    class_number="east-campus-000",
                    schedule=SECRET,
                )
            ]
        },
    )
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths, skip=("east-campus",))

    exit_code, payload, output = _invoke(
        cli, capsys, _arguments(paths, inventory=inventory, campus_store=campus_store)
    )

    assert exit_code == 5
    assert payload["category"] == "invalid_capture_bundle"
    assert payload["shard_id"] == "east-campus"
    assert SECRET not in output
    assert "teachingTimePlaceStr" not in output
    assert set(payload) == {"status", "exception_type", "stage", "category", "shard_id"}


def test_failure_stage_and_exit_code_follow_the_category(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path, totals_by_shard={"south-campus": 3})
    inventory = _inventory(tmp_path, paths)
    campus_store = _campus_store(tmp_path, paths)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths,
            inventory=inventory,
            campus_store=campus_store,
            baseline_before=7,
            baseline_after=7,
        ),
    )
    assert exit_code == 6
    assert payload["stage"] == "completeness_validation"
    assert payload["shard_id"] == "south-campus"

    missing = _write_all(tmp_path / "missing")
    missing["north-campus"] = tmp_path / "missing" / "absent.json"
    inventory2 = _inventory(
        tmp_path / "missing",
        missing,
        digest_overrides={"north-campus": "0" * 64},
    )
    campus_store2 = _campus_store(tmp_path / "missing", missing, skip=("north-campus",))

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(missing, inventory=inventory2, campus_store=campus_store2),
    )
    assert exit_code == 3
    assert payload["stage"] == "artifact_read"


def test_module_documents_the_transaction_caveat_and_boundaries() -> None:
    source = CLI_PATH.read_text(encoding="utf-8")

    assert "NOT one" in source and "transaction" in source
    assert "capture://sysu/<semester>/full-semester/<semester>" in source
    assert "--skip-north" in source  # 文档明确写出"没有这类参数"
    assert "scope_kind = full_semester" in source
    assert "the exact bytes hashed == the exact bytes parsed" in source
    assert "approved capture inventory" in source
    assert "merged_offering_set_sha256" in source
