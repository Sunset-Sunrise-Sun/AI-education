"""Full-semester acceptance CLI tests (synthetic, zero-network, no real captures)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.course_data import (
    SCOPE_KIND_FULL_SEMESTER,
    initialize_course_data_store,
    load_course_data_provenance,
)


SEMESTER = "2026-1"
SECRET = "SECRET-RAW-SCHEDULE-TOKEN"
VALID_SCHEDULE = "1-8周/星期五/第5-6节/REDACTED/示例环节,"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPOSITORY_ROOT / "tools" / "accept_full_semester_course_data.py"

SHARD_OPTIONS: dict[str, str] = {
    "east-campus": "--east",
    "south-campus": "--south",
    "shenzhen-campus": "--shenzhen",
    "zhuhai-campus": "--zhuhai",
    "north-campus": "--north",
}


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "accept_full_semester_course_data_for_test", CLI_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli() -> ModuleType:
    return _load_cli()


def _row(
    *,
    course_number: str,
    class_number: str,
    schedule: str = VALID_SCHEDULE,
    course_name: str = "示例课程",
) -> dict[str, object]:
    return {
        "courseNum": course_number,
        "courseName": course_name,
        "classNumber": class_number,
        "yearTerm": SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": schedule,
    }


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


def _arguments(
    paths: dict[str, Path],
    *,
    baseline_before: int = 5,
    baseline_after: int = 5,
    sqlite_path: Path | None = None,
    manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
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
    if sqlite_path is not None:
        result.extend(["--sqlite", str(sqlite_path)])
    if manifest_path is not None:
        result.extend(["--output-manifest", str(manifest_path)])
    if expected_manifest_sha256 is not None:
        result.extend(["--expected-manifest-sha256", expected_manifest_sha256])
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


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_accepts_five_shards_and_reports_aggregate_only_fields(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths))

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
    assert isinstance(payload["manifest_sha256"], str)
    assert len(payload["manifest_sha256"]) == 64  # type: ignore[arg-type]

    shards = payload["shards"]
    assert isinstance(shards, list) and len(shards) == 5
    assert [shard["shard_id"] for shard in shards] == list(SHARD_OPTIONS)
    for shard in shards:
        assert len(shard["raw_bundle_sha256"]) == 64
        assert shard["loaded_count"] == shard["reported_total"] == 1
        assert shard["page_count_semantics"] == (
            "never_used_to_derive_completeness"
        )

    # ⛔ 聚合输出里不得出现任何取值 / 原始排课串。
    serialized = json.dumps(payload, ensure_ascii=False)
    assert SECRET not in serialized
    assert "示例课程" not in serialized
    assert "teachingTimePlaceStr" not in serialized


def test_cli_acceptance_identity_is_deterministic(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path / "run")

    _, first, _ = _invoke(cli, capsys, _arguments(paths))
    _, second, _ = _invoke(cli, capsys, _arguments(paths))

    assert first["manifest_sha256"] == second["manifest_sha256"]


# --------------------------------------------------------------------------- #
# manifest file
# --------------------------------------------------------------------------- #


def test_manifest_file_bytes_are_the_acceptance_identity(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    manifest_path = tmp_path / "acceptance-manifest.json"

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, manifest_path=manifest_path)
    )

    assert exit_code == 0
    assert payload["manifest_written"] is True

    raw = manifest_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == payload["manifest_sha256"]
    assert b", " not in raw and b'": ' not in raw

    manifest = json.loads(raw)
    assert manifest["scope_kind"] == SCOPE_KIND_FULL_SEMESTER
    assert manifest["scope_id"] == SEMESTER
    assert manifest["baseline_before"] == manifest["baseline_after"] == 5
    assert [item["shard_id"] for item in manifest["shards"]] == list(SHARD_OPTIONS)
    assert manifest["raw_bundle_sha256_semantics"] == (
        "exact_bytes_of_that_campus_artifact"
    )


def test_manifest_rewrite_is_idempotent_but_conflicting_content_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    manifest_path = tmp_path / "acceptance-manifest.json"
    arguments = _arguments(paths, manifest_path=manifest_path)

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
    paths = _write_all(tmp_path)

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(paths, manifest_path=tmp_path / "missing" / "manifest.json"),
    )

    assert exit_code == 8
    assert payload["category"] == "manifest_write_error"


def test_expected_manifest_sha256_gate(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)

    _, accepted, _ = _invoke(cli, capsys, _arguments(paths))

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(paths, expected_manifest_sha256=str(accepted["manifest_sha256"])),
    )
    assert exit_code == 0

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, expected_manifest_sha256="0" * 64)
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
    paths = _write_all(tmp_path)

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, extra=("--source", "capture://sysu/x"))
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
    paths = _write_all(tmp_path)

    exit_code, _, _ = _invoke(cli, capsys, _arguments(paths, extra=(option, "x")))
    assert exit_code == 2


def test_north_bundle_is_a_mandatory_argument(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    arguments = _arguments(paths)
    index = arguments.index("--north")
    del arguments[index : index + 2]

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 2
    assert payload["category"] == "invalid_arguments"


def test_missing_shard_bundle_file_is_an_artifact_read_failure(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    paths["north-campus"] = tmp_path / "absent-north.json"

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths))

    assert exit_code == 3
    assert payload["category"] == "bundle_read_failed"
    # 只暴露**结构性**定位信息：shard slug，⛔ 不含文件名 / 完整路径。
    assert payload["shard_id"] == "north-campus"
    assert "absent-north.json" not in json.dumps(payload)
    assert str(tmp_path) not in json.dumps(payload)


# --------------------------------------------------------------------------- #
# baseline / coverage / completeness
# --------------------------------------------------------------------------- #


def test_baseline_drift_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, baseline_before=5, baseline_after=6)
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
    paths = _write_all(tmp_path)

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, baseline_before=baseline, baseline_after=baseline)
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
    paths = _write_all(tmp_path)
    arguments = _arguments(paths)
    arguments[arguments.index("--baseline-before") + 1] = value

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 2
    assert payload["category"] == "invalid_baseline"


def test_baseline_text_tolerates_surrounding_whitespace(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    arguments = _arguments(paths)
    arguments[arguments.index("--baseline-before") + 1] = " 5 "

    exit_code, payload, _ = _invoke(cli, capsys, arguments)
    assert exit_code == 0
    assert payload["baseline_before"] == 5


def test_empty_semester_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    arguments = _arguments(paths)
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

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths, baseline_before=7, baseline_after=7))

    assert exit_code == 6
    assert payload["category"] == "shard_not_complete"


def test_empty_shard_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path, rows_by_shard={"north-campus": []})

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths, baseline_before=4, baseline_after=4))

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

    exit_code, payload, _ = _invoke(
        cli, capsys, _arguments(paths, baseline_before=6, baseline_after=6)
    )

    assert exit_code == 5
    assert payload["category"] == "duplicate_identity_across_shards"


def test_semester_mismatch_in_one_shard_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    _write_bundle(paths["zhuhai-campus"], _rows("zhuhai-campus"), semester="2026-2")

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths))

    assert exit_code == 5
    assert payload["category"] == "semester_mismatch"


def test_invalid_capture_bundle_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    paths["east-campus"].write_bytes(b'{"format":"not-a-bundle"}')

    exit_code, payload, _ = _invoke(cli, capsys, _arguments(paths))

    assert exit_code == 5
    assert payload["category"] == "invalid_capture_bundle"


# --------------------------------------------------------------------------- #
# SQLite
# --------------------------------------------------------------------------- #


def test_import_writes_and_reads_back_a_full_semester_record(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    sqlite_path = tmp_path / "course-data.sqlite3"
    manifest_path = tmp_path / "manifest.json"

    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(paths, sqlite_path=sqlite_path, manifest_path=manifest_path),
    )

    assert exit_code == 0
    assert payload["status"] == "imported"
    assert payload["sqlite_imported"] is True
    assert payload["inserted"] == 5
    assert payload["updated"] == 0
    assert payload["unchanged"] == 0
    assert payload["reconciled_offering_count"] == 5
    assert payload["db_semester_offering_count"] == 5
    assert payload["provenance_artifact_sha256"] == payload["manifest_sha256"]
    assert payload["provenance_semester"] == SEMESTER
    assert payload["provenance_scope_kind"] == SCOPE_KIND_FULL_SEMESTER
    assert payload["provenance_scope_id"] == SEMESTER
    assert payload["provenance_completeness"] == "complete"
    assert payload["provenance_loaded_count"] == 5
    assert payload["provenance_reported_total"] == 5
    assert payload["provenance_offering_count"] == 5

    records = load_course_data_provenance(sqlite_path, semester=SEMESTER)
    assert len(records) == 1
    assert records[0].scope_kind == SCOPE_KIND_FULL_SEMESTER
    assert records[0].scope_id == SEMESTER
    assert records[0].artifact_sha256 == payload["manifest_sha256"]
    assert records[0].source == payload["source"]
    # manifest 文件字节的摘要 = 库里记录的 acceptance identity
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == records[0].artifact_sha256


def test_reimport_is_idempotent_and_keeps_exactly_one_record(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    sqlite_path = tmp_path / "course-data.sqlite3"
    arguments = _arguments(paths, sqlite_path=sqlite_path)

    assert _invoke(cli, capsys, arguments)[0] == 0
    exit_code, payload, _ = _invoke(cli, capsys, arguments)

    assert exit_code == 0
    assert payload["inserted"] == 0
    assert payload["unchanged"] == 5
    assert payload["db_semester_offering_count"] == 5
    assert len(load_course_data_provenance(sqlite_path, semester=SEMESTER)) == 1


def test_failure_before_any_store_call_writes_no_database(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path, totals_by_shard={"south-campus": 3})
    sqlite_path = tmp_path / "course-data.sqlite3"

    exit_code, _, _ = _invoke(
        cli,
        capsys,
        _arguments(
            paths, baseline_before=7, baseline_after=7, sqlite_path=sqlite_path
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

    paths = _write_all(tmp_path)
    paths["north-campus"] = tmp_path / "absent-north.json"

    exit_code, _, _ = _invoke(
        cli, capsys, _arguments(paths, sqlite_path=sqlite_path)
    )

    assert exit_code == 3
    assert load_course_data_provenance(sqlite_path) == []


def test_store_errors_are_reported_without_exception_text(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_all(tmp_path)
    directory = tmp_path / "a-directory"
    directory.mkdir()

    exit_code, payload, output = _invoke(
        cli, capsys, _arguments(paths, sqlite_path=directory)
    )

    assert exit_code == 7
    assert payload["category"] == "store_error"
    assert str(tmp_path) not in output
    assert "Traceback" not in output


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

    exit_code, payload, output = _invoke(cli, capsys, _arguments(paths))

    assert exit_code == 5
    assert payload["category"] == "invalid_capture_bundle"
    assert payload["shard_id"] == "east-campus"
    assert SECRET not in output
    assert "teachingTimePlaceStr" not in output
    # ⛔ 失败输出只有聚合字段 + 结构性 shard 定位，⛔ 永不回显异常文本。
    assert set(payload) == {"status", "exception_type", "stage", "category", "shard_id"}


def test_failure_stage_and_exit_code_follow_the_category(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """每个失败类别 ⇄ 退出码 ⇄ 阶段名必须一一对应（⛔ 不解析错误文本）。"""

    paths = _write_all(tmp_path, totals_by_shard={"south-campus": 3})
    arguments = _arguments(paths, baseline_before=7, baseline_after=7)

    exit_code, payload, _ = _invoke(cli, capsys, arguments)

    assert exit_code == 6
    assert payload["category"] == "shard_not_complete"
    assert payload["stage"] == "completeness_validation"
    assert payload["shard_id"] == "south-campus"

    drifting = _write_all(tmp_path / "drift")
    exit_code, payload, _ = _invoke(
        cli,
        capsys,
        _arguments(drifting, baseline_before=4, baseline_after=6),
    )
    assert exit_code == 4
    assert payload["category"] == "snapshot_window_unstable"
    assert payload["stage"] == "baseline_validation"

    unknown = _write_all(tmp_path / "unknown")
    unknown["north-campus"] = tmp_path / "unknown" / "absent.json"
    exit_code, payload, _ = _invoke(cli, capsys, _arguments(unknown))
    assert exit_code == 3
    assert payload["category"] == "bundle_read_failed"
    assert payload["stage"] == "artifact_read"
    assert payload["shard_id"] == "north-campus"


def test_module_documents_the_transaction_caveat_and_boundaries() -> None:
    source = CLI_PATH.read_text(encoding="utf-8")

    assert "NOT one" in source and "transaction" in source
    assert "capture://sysu/<semester>/full-semester/<semester>" in source
    assert "--skip-north" in source  # 文档明确写出"没有这类参数"
    assert "scope_kind = full_semester" in source
