"""Internal Course Data artifact acceptance CLI tests (synthetic, zero-network)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.course_data import load_course_data_provenance, load_course_offerings


SEMESTER = "2026-1"
CAMPUS_ID = "5063559"
SOURCE = f"capture://sysu/{SEMESTER}/campus/{CAMPUS_ID}"
SECRET_TOKEN = "SECRET-RAW-SCHEDULE-TOKEN"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPOSITORY_ROOT / "tools" / "validate_course_data_artifact.py"


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_course_data_artifact_for_test", CLI_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli() -> ModuleType:
    return _load_cli()


def _row(class_number: str, *, schedule: str | None = None) -> dict[str, object]:
    return {
        "courseNum": "SYN-0001",
        "courseName": "示例课程",
        "classNumber": class_number,
        "yearTerm": SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": (
            schedule
            if schedule is not None
            else "1-8周/星期五/第5-6节/REDACTED/示例环节,"
        ),
    }


def _bundle(*, rows: list[dict[str, object]], total: int) -> dict[str, object]:
    return {
        "format": "sysu-opening-courses-capture-v1",
        "semester": SEMESTER,
        "first_page_no": 1,
        "page_size": 200,
        "pages": [
            {
                "page_no": 1,
                "response": {"code": 200, "data": {"total": total, "rows": rows}},
            }
        ],
    }


def _write_bundle(path: Path, payload: object) -> bytes:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _arguments(bundle_path: Path, *, sqlite_path: Path | None = None) -> list[str]:
    result = [
        "--bundle",
        str(bundle_path),
        "--expected-semester",
        SEMESTER,
        "--scope-id",
        CAMPUS_ID,
        "--source",
        SOURCE,
    ]
    if sqlite_path is not None:
        result.extend(["--sqlite", str(sqlite_path)])
    return result


def _invoke(
    cli: ModuleType,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> tuple[int, dict[str, object]]:
    exit_code = cli.main(arguments)
    captured = capsys.readouterr()
    output = captured.out if exit_code == 0 else captured.err
    other = captured.err if exit_code == 0 else captured.out
    assert other == ""
    return exit_code, json.loads(output)


def test_valid_complete_bundle_reports_aggregate_acceptance_fields(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path = tmp_path / "complete.json"
    raw = _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))

    exit_code, output = _invoke(cli, capsys, _arguments(bundle_path))

    assert exit_code == 0
    assert output == {
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact_sha256_semantics": "exact_byte_identity_and_integrity",
        "first_page_no": 1,
        "format": "sysu-opening-courses-capture-v1",
        "loaded_count": 1,
        "offering_count": 1,
        "page_count": 1,
        "page_size": 200,
        "reported_total": 1,
        "offering_count_semantics": "this_artifact_only",
        "scope_id": CAMPUS_ID,
        "scope_kind": "campus",
        "scope_kind_semantics": "campus_only_in_this_cli",
        "semester": SEMESTER,
        "snapshot.is_complete": True,
        "source": SOURCE,
        "source_semantics": "audit_label_only_not_provenance_proof",
        "sqlite_imported": False,
        "status": "validated",
    }


def test_sha256_is_deterministic_for_exact_raw_bytes(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path = tmp_path / "stable.json"
    raw = _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))

    first_code, first = _invoke(cli, capsys, _arguments(bundle_path))
    second_code, second = _invoke(cli, capsys, _arguments(bundle_path))

    assert first_code == second_code == 0
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["artifact_sha256"] == hashlib.sha256(raw).hexdigest()


def test_malformed_bundle_fails_closed(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path = tmp_path / "malformed.json"
    _write_bundle(bundle_path, {"format": "wrong"})

    exit_code, output = _invoke(cli, capsys, _arguments(bundle_path))

    assert exit_code != 0
    assert output["status"] == "normalization_failed"
    assert output["stage"] == "bundle_validation"
    assert output["category"] == "invalid_capture_bundle"


def test_normalization_failure_prints_no_raw_token_and_writes_no_database(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path = tmp_path / "bad-schedule.json"
    sqlite_path = tmp_path / "must-not-exist.sqlite3"
    _write_bundle(
        bundle_path,
        _bundle(rows=[_row("SYN-01", schedule=SECRET_TOKEN)], total=1),
    )

    exit_code, output = _invoke(
        cli, capsys, _arguments(bundle_path, sqlite_path=sqlite_path)
    )

    assert exit_code != 0
    assert output["status"] == "normalization_failed"
    assert output["stage"] == "snapshot_normalization"
    assert "exception_type" in output
    assert SECRET_TOKEN not in json.dumps(output, ensure_ascii=False)
    assert not sqlite_path.exists(), "normalization failure must happen before any DB write"


def test_incomplete_snapshot_writes_no_database(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path = tmp_path / "partial.json"
    sqlite_path = tmp_path / "must-not-exist.sqlite3"
    _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=2))

    exit_code, output = _invoke(
        cli, capsys, _arguments(bundle_path, sqlite_path=sqlite_path)
    )

    assert exit_code != 0
    assert output["status"] == "incomplete_snapshot"
    assert output["snapshot.is_complete"] is False
    assert output["loaded_count"] == 1
    assert output["reported_total"] == 2
    assert not sqlite_path.exists(), "partial snapshot must not create a SQLite file"


def test_explicit_scope_is_required_before_any_database_write(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path = tmp_path / "complete.json"
    sqlite_path = tmp_path / "must-not-exist.sqlite3"
    _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))
    arguments = [
        "--bundle",
        str(bundle_path),
        "--expected-semester",
        SEMESTER,
        "--source",
        SOURCE,
        "--sqlite",
        str(sqlite_path),
    ]

    exit_code, output = _invoke(cli, capsys, arguments)

    assert exit_code != 0
    assert output["status"] == "invalid_arguments"
    assert output["stage"] == "arguments"
    assert not sqlite_path.exists()


def test_blank_scope_id_writes_no_database(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ blank scope_id → scope 拒绝，且在任何 DB 写入之前。"""

    bundle_path = tmp_path / "complete.json"
    sqlite_path = tmp_path / "must-not-exist.sqlite3"
    _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))
    arguments = _arguments(bundle_path, sqlite_path=sqlite_path)
    arguments[arguments.index(CAMPUS_ID)] = "   "

    exit_code, output = _invoke(cli, capsys, arguments)

    assert exit_code != 0
    assert output["status"] in {"scope_invalid", "invalid_arguments"}
    assert not sqlite_path.exists()


def test_successful_sqlite_import_and_provenance_round_trip(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path = tmp_path / "complete.json"
    sqlite_path = tmp_path / "course-data.sqlite3"
    raw = _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))
    expected_digest = hashlib.sha256(raw).hexdigest()

    exit_code, output = _invoke(
        cli, capsys, _arguments(bundle_path, sqlite_path=sqlite_path)
    )

    assert exit_code == 0
    assert output["status"] == "imported"
    assert output["sqlite_imported"] is True
    assert output["inserted"] == 1
    assert output["updated"] == 0
    assert output["unchanged"] == 0
    assert output["reconciled_offering_count"] == output["offering_count"] == 1
    assert output["db_semester_offering_count"] == 1
    assert (
        output["db_semester_offering_count_semantics"]
        == "all_offerings_currently_stored_for_this_semester_not_this_artifact"
    )
    assert output["provenance_artifact_sha256"] == expected_digest
    assert output["provenance_semester"] == SEMESTER
    assert output["provenance_scope_kind"] == "campus"
    assert output["provenance_scope_id"] == CAMPUS_ID
    assert output["provenance_completeness"] == "complete"
    assert output["provenance_loaded_count"] == 1
    assert output["provenance_reported_total"] == 1
    assert output["provenance_offering_count"] == 1

    offerings = load_course_offerings(sqlite_path, SEMESTER)
    provenance = load_course_data_provenance(sqlite_path, semester=SEMESTER)
    assert len(offerings) == 1
    assert len(provenance) == 1
    assert provenance[0].artifact_sha256 == expected_digest
    assert provenance[0].scope_kind == "campus"
    assert provenance[0].scope_id == CAMPUS_ID
    assert provenance[0].source == SOURCE


def test_missing_bundle_is_a_safe_nonzero_read_failure(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "private-name-must-not-be-printed.json"

    exit_code, output = _invoke(cli, capsys, _arguments(missing))

    assert exit_code != 0
    assert output["status"] == "artifact_read_failed"
    assert output["stage"] == "artifact_read"
    assert missing.name not in json.dumps(output)


def test_cli_has_no_network_or_parser_implementation() -> None:
    source = CLI_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "socket",
        "schedule_parser",
        "parse_teaching_time_place",
        "continue  # skip",
    ):
        assert forbidden not in source

    for required in (
        "load_capture_bundle",
        "collect_captured_pages_snapshot",
        "SnapshotScope",
        "import_offering_snapshot",
        "load_course_data_provenance",
        "load_course_offerings",
    ):
        assert required in source


# ---------------------------------------------------------------------------
# Acceptance CLI Gate：campus-only scope / source 绑定 / digest / read-back
# ---------------------------------------------------------------------------


def test_full_semester_scope_is_not_expressible(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ 单 artifact CLI **没有** full_semester 路径（该选项已不存在）。"""

    bundle_path = tmp_path / "complete.json"
    _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))

    for arguments in (
        _arguments(bundle_path) + ["--scope-kind", "full_semester"],
        [
            "--bundle",
            str(bundle_path),
            "--expected-semester",
            SEMESTER,
            "--scope-kind",
            "full_semester",
            "--scope-id",
            SEMESTER,
            "--source",
            f"capture://sysu/{SEMESTER}/full_semester/{SEMESTER}",
        ],
    ):
        exit_code, output = _invoke(cli, capsys, arguments)
        assert exit_code != 0
        assert output["status"] == "invalid_arguments"
        assert output["stage"] == "arguments"

    # ⛔ 源码里不得存在 full_semester 路径（docstring 里会**说明**它被延后）。
    source = CLI_PATH.read_text(encoding="utf-8")
    assert "--scope-kind" not in source
    assert "args.scope_kind" not in source
    assert "scope_kind=SCOPE_KIND_CAMPUS" in source


def test_arbitrary_source_label_is_rejected(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ source 必须精确等于 campus 模板。"""

    bundle_path = tmp_path / "complete.json"
    sqlite_path = tmp_path / "must-not-exist.sqlite3"
    _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))

    for bad_source in (
        "east-campus",
        f"capture://sysu/{SEMESTER}/campus/",
        f"capture://sysu/{SEMESTER}/{CAMPUS_ID}",
        f"https://example.com/{CAMPUS_ID}",
    ):
        arguments = _arguments(bundle_path, sqlite_path=sqlite_path)
        arguments[arguments.index(SOURCE)] = bad_source

        exit_code, output = _invoke(cli, capsys, arguments)

        assert exit_code != 0, bad_source
        assert output["status"] == "scope_invalid"
        assert output["category"] == "invalid_campus_source_label"
        assert not sqlite_path.exists()


def test_source_semester_and_campus_must_match_exactly(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ source 中的 semester / campus id 必须与参数一致。"""

    bundle_path = tmp_path / "complete.json"
    _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))

    wrong_semester = _arguments(bundle_path)
    wrong_semester[wrong_semester.index(SOURCE)] = (
        f"capture://sysu/2027-1/campus/{CAMPUS_ID}"
    )
    exit_code, output = _invoke(cli, capsys, wrong_semester)
    assert exit_code != 0
    assert output["category"] == "invalid_campus_source_label"

    wrong_campus = _arguments(bundle_path)
    wrong_campus[wrong_campus.index(SOURCE)] = f"capture://sysu/{SEMESTER}/campus/9999999"
    exit_code, output = _invoke(cli, capsys, wrong_campus)
    assert exit_code != 0
    assert output["category"] == "invalid_campus_source_label"


def test_expected_sha256_gate_rejects_a_wrong_digest(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ 显式 expected digest 与 raw bytes 不符 ⇒ fail closed（无 DB 调用）。"""

    bundle_path = tmp_path / "complete.json"
    sqlite_path = tmp_path / "must-not-exist.sqlite3"
    raw = _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))

    good = _arguments(bundle_path, sqlite_path=sqlite_path) + [
        "--expected-sha256",
        hashlib.sha256(raw).hexdigest(),
    ]
    exit_code, output = _invoke(cli, capsys, good)
    assert exit_code == 0
    assert output["status"] == "imported"

    bad = _arguments(bundle_path, sqlite_path=sqlite_path) + [
        "--expected-sha256",
        "0" * 64,
    ]
    exit_code, output = _invoke(cli, capsys, bad)
    assert exit_code != 0
    assert output["category"] == "sha256_mismatch"
    assert output["stage"] == "artifact_hash"


def test_empty_snapshot_is_rejected_before_any_database_write(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ zero/empty snapshot ⇒ fail closed，且不创建 DB 文件。"""

    bundle_path = tmp_path / "empty.json"
    sqlite_path = tmp_path / "must-not-exist.sqlite3"
    _write_bundle(bundle_path, _bundle(rows=[], total=0))

    exit_code, output = _invoke(
        cli, capsys, _arguments(bundle_path, sqlite_path=sqlite_path)
    )

    assert exit_code != 0
    assert output["status"] == "empty_snapshot"
    assert output["category"] == "snapshot_has_zero_offerings"
    assert output["loaded_count"] == 0
    assert not sqlite_path.exists()


def test_reimport_is_reconciled_and_db_count_is_semester_wide(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """✅ 幂等重入对账；⚠️ `db_semester_offering_count` 与 artifact 计数区分。"""

    bundle_path = tmp_path / "complete.json"
    other_bundle_path = tmp_path / "other-campus.json"
    sqlite_path = tmp_path / "course-data.sqlite3"
    _write_bundle(bundle_path, _bundle(rows=[_row("SYN-01")], total=1))
    other = _bundle(rows=[_row("SYN-02")], total=1)
    other["pages"][0]["response"]["data"]["rows"][0]["courseNum"] = "SYN-0002"
    _write_bundle(other_bundle_path, other)

    exit_code, first = _invoke(
        cli, capsys, _arguments(bundle_path, sqlite_path=sqlite_path)
    )
    assert exit_code == 0
    assert first["inserted"] + first["updated"] + first["unchanged"] == 1
    assert first["db_semester_offering_count"] == 1

    # 幂等重入：计数必须仍然对账（inserted/updated/unchanged 之和 == 1）
    exit_code, second = _invoke(
        cli, capsys, _arguments(bundle_path, sqlite_path=sqlite_path)
    )
    assert exit_code == 0
    assert second["inserted"] + second["updated"] + second["unchanged"] == 1
    assert second["offering_count"] == 1

    # 另一个 artifact（同 semester，不同 campus）→ 学期级计数变大，但 artifact 计数不变
    other_arguments = [
        "--bundle",
        str(other_bundle_path),
        "--expected-semester",
        SEMESTER,
        "--scope-id",
        "5062201",
        "--source",
        f"capture://sysu/{SEMESTER}/campus/5062201",
        "--sqlite",
        str(sqlite_path),
    ]
    exit_code, third = _invoke(cli, capsys, other_arguments)
    assert exit_code == 0
    assert third["offering_count"] == 1
    assert third["db_semester_offering_count"] == 2
    assert third["reconciled_offering_count"] == third["offering_count"]


def test_exception_text_is_never_printed(
    cli: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ 失败输出只含 stage/category/类型名，不含异常文本或原始 token。"""

    bundle_path = tmp_path / "bad.json"
    _write_bundle(bundle_path, {"format": "wrong", "leak": SECRET_TOKEN})

    exit_code, output = _invoke(cli, capsys, _arguments(bundle_path))

    assert exit_code != 0
    serialized = json.dumps(output, ensure_ascii=False)
    assert SECRET_TOKEN not in serialized
    assert "message" not in output
    assert "Traceback" not in serialized
    assert set(output) <= {
        "status",
        "exception_type",
        "stage",
        "category",
        "artifact_sha256",
        "artifact_sha256_semantics",
        "format",
        "semester",
        "first_page_no",
        "page_size",
        "page_count",
        "loaded_count",
        "reported_total",
        "offering_count",
        "offering_count_semantics",
        "snapshot.is_complete",
        "scope_kind",
        "scope_kind_semantics",
        "scope_id",
        "source",
        "source_semantics",
    }
