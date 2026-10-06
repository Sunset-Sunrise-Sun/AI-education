#!/usr/bin/env python3
"""Accept a five-shard **full-semester** Course Data capture set (zero-network).

This is an internal acceptance tool.  It deliberately composes the existing
capture bridge, shard-merge primitives and SQLite store instead of implementing
another parser / bundle validator / completeness rule / persistence layer.

Scope contract (this tool is the ONLY full-semester entry point):

    scope_kind = full_semester        (fixed; not a CLI argument)
    scope_id   = <semester>           (must equal the snapshot semester)
    source     = capture://sysu/<semester>/full-semester/<semester>
                                      (derived, not caller-selectable)

The single-bundle campus CLI (``tools/validate_course_data_artifact.py``) can
only ever produce a ``campus`` acceptance; it is impossible to declare a bare
campus bundle as ``full_semester``.  This tool cannot produce a campus
acceptance either.  Neither tool subsumes the other.

Exact five-shard requirement (no escape hatches):

    east-campus / south-campus / shenzhen-campus / zhuhai-campus / north-campus

Missing, duplicate, unknown or aliased shard ids are rejected.  There is no
``--skip-north`` / ``--allow-partial-semester`` / ``--force-complete``.

North campus is currently allowlisted but operationally suspended, so no real
North artifact exists yet.  That is why no real full-semester acceptance can be
produced today; it is NOT a reason to add a bypass (the fifth input simply does
not exist, and full-semester acceptance stays fail closed until it does).

Baseline semantics:

    baseline_before / baseline_after are the collector's *reported totals* for
    the whole semester immediately before and after the capture window.  They
    are totals, NOT a baseline OfferingSnapshot.
    baseline_before != baseline_after         -> snapshot_window_unstable
    sum(shard reported_total) != baseline     -> shard_coverage_mismatch

    Completeness is never derived from captured page counts.

Identity / integrity semantics:

    raw bundle SHA-256   = exact bytes of that campus artifact
    manifest SHA-256     = acceptance record identity / integrity
                           != acquisition provenance proof
    source label         = audit label only, not provenance proof

Transaction caveat:

    the SQLite import commit and the provenance read-back are NOT one
    transaction, so a non-zero exit does not by itself prove the database is
    unchanged.  Failures before any store call only prove that this call did
    not happen.

Failure output is intentionally aggregate-only.  Exception messages are never
printed because normalization errors can originate from sensitive captured rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.course_data import (  # noqa: E402
    APPROVED_FULL_SEMESTER_SHARDS,
    CourseDataStoreError,
    FullSemesterAcceptance,
    FullSemesterAcceptanceError,
    ShardArtifact,
    accept_full_semester_capture_set,
    canonical_manifest_bytes,
    compute_artifact_sha256,
    import_offering_snapshot,
    load_course_data_provenance,
    load_course_offerings,
)


EXIT_ARGUMENTS = 2
EXIT_ARTIFACT_READ = 3
EXIT_BASELINE = 4
EXIT_SHARD_SET = 5
EXIT_COMPLETENESS = 6
EXIT_SQLITE = 7
EXIT_MANIFEST = 8

#: 失败类别 → 退出码（机器可读映射；⛔ 不解析错误文本）。
_CATEGORY_EXIT_CODES: dict[str, int] = {
    "invalid_semester": EXIT_ARGUMENTS,
    "invalid_baseline": EXIT_BASELINE,
    "duplicate_shard": EXIT_SHARD_SET,
    "unknown_shard": EXIT_SHARD_SET,
    "missing_shard": EXIT_SHARD_SET,
    "bundle_read_failed": EXIT_ARTIFACT_READ,
    "bundle_changed_during_acceptance": EXIT_ARTIFACT_READ,
    "bundle_digest_mismatch": EXIT_ARTIFACT_READ,
    "invalid_capture_bundle": EXIT_SHARD_SET,
    "semester_mismatch": EXIT_SHARD_SET,
    "shard_not_complete": EXIT_COMPLETENESS,
    "empty_shard": EXIT_COMPLETENESS,
    "snapshot_window_unstable": EXIT_BASELINE,
    "shard_coverage_mismatch": EXIT_BASELINE,
    "duplicate_identity_across_shards": EXIT_SHARD_SET,
    "conflicting_identity_across_shards": EXIT_SHARD_SET,
    "merge_failed": EXIT_SHARD_SET,
    "merged_count_mismatch": EXIT_SHARD_SET,
}

#: shard slug → CLI 参数名（⛔ 与已批准集合一一对应，不接受别名）。
_SHARD_OPTIONS: tuple[tuple[str, str], ...] = (
    ("east-campus", "--east"),
    ("south-campus", "--south"),
    ("shenzhen-campus", "--shenzhen"),
    ("zhuhai-campus", "--zhuhai"),
    ("north-campus", "--north"),
)


class CliArgumentError(ValueError):
    """The CLI shape is invalid; no user-supplied value is retained or printed."""


class ManifestWriteError(RuntimeError):
    """The canonical manifest could not be written (or already differs on disk)."""


class ManifestDigestMismatchError(RuntimeError):
    """The computed acceptance identity differs from the approved one."""


class ProvenanceReadBackError(RuntimeError):
    """The imported acceptance could not be read back as one exact provenance record."""


class SafeArgumentParser(argparse.ArgumentParser):
    """Convert argparse failures to structured, non-echoing CLI failures."""

    def error(self, message: str) -> NoReturn:  # noqa: ARG002 - intentionally suppressed
        raise CliArgumentError("invalid arguments")


@dataclass(frozen=True)
class AcceptanceFailure(Exception):
    exit_code: int
    payload: dict[str, object]


def _fail(
    *,
    exit_code: int,
    status: str,
    stage: str,
    category: str,
    exception: BaseException,
    extra: dict[str, object] | None = None,
) -> NoReturn:
    payload: dict[str, object] = {
        "status": status,
        "exception_type": type(exception).__name__,
        "stage": stage,
        "category": category,
    }
    if extra:
        payload.update(extra)
    raise AcceptanceFailure(exit_code=exit_code, payload=payload)


def _build_parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(
        description=(
            "Accept the five approved campus Capture Bundles as one full-semester "
            "Course Data acceptance and optionally import it into SQLite. "
            "The scope is fixed to full_semester/<semester>; the source label is "
            "derived and the manifest SHA-256 is the acceptance identity."
        )
    )
    parser.add_argument("--semester", required=True)
    parser.add_argument(
        "--baseline-before", required=True, help="collector reported total before the window"
    )
    parser.add_argument(
        "--baseline-after", required=True, help="collector reported total after the window"
    )
    for shard_id, option in _SHARD_OPTIONS:
        parser.add_argument(
            option,
            required=True,
            metavar="BUNDLE",
            help=f"local Capture Bundle JSON path for {shard_id}",
        )
    parser.add_argument(
        "--expected-manifest-sha256",
        help="optional approved manifest SHA-256; must match the computed identity",
    )
    parser.add_argument(
        "--output-manifest",
        help="optional path to write the canonical manifest; identical re-writes are idempotent",
    )
    parser.add_argument(
        "--sqlite",
        help="optional SQLite path; import occurs only after the acceptance succeeds",
    )
    return parser


def _parse_total(value: object, *, name: str) -> int:
    """把 CLI 上的总量证据解析成非负整数（`bool` 不算整数，⛔ 不接受空 / 小数）。"""

    if not isinstance(value, str) or not value.strip():
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="invalid_baseline",
            exception=CliArgumentError(f"invalid {name}"),
        )

    text = value.strip()
    if not text.isdigit():
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="invalid_baseline",
            exception=CliArgumentError(f"invalid {name}"),
        )

    return int(text)


def _validated_inputs(args: argparse.Namespace) -> tuple[str, int, int, list[ShardArtifact]]:
    semester = args.semester
    if not isinstance(semester, str) or not semester.strip():
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="invalid_semester",
            exception=CliArgumentError("invalid semester"),
        )

    baseline_before = _parse_total(args.baseline_before, name="baseline_before")
    baseline_after = _parse_total(args.baseline_after, name="baseline_after")

    artifacts = [
        ShardArtifact(shard_id=shard_id, bundle_path=getattr(args, option.lstrip("-").replace("-", "_")))
        for shard_id, option in _SHARD_OPTIONS
    ]

    return semester.strip(), baseline_before, baseline_after, artifacts


def _summary(
    *,
    acceptance: FullSemesterAcceptance,
    manifest_path: Path | None,
) -> dict[str, object]:
    return {
        "manifest_sha256": acceptance.manifest_sha256,
        "manifest_sha256_semantics": (
            "acceptance_record_identity_and_integrity_not_acquisition_provenance_proof"
        ),
        "manifest_format": acceptance.manifest["format"],
        "manifest_version": acceptance.manifest["manifest_version"],
        "semester": acceptance.semester,
        "scope_kind": acceptance.scope.scope_kind,
        "scope_id": acceptance.scope.scope_id,
        "scope_kind_semantics": "full_semester_acceptance_only",
        "source": acceptance.source,
        "source_semantics": "audit_label_only_not_provenance_proof",
        "baseline_before": acceptance.baseline_before,
        "baseline_after": acceptance.baseline_after,
        "baseline_semantics": "collector_reported_total_not_a_baseline_snapshot",
        "baseline_stable": acceptance.baseline_before == acceptance.baseline_after,
        "shard_count": len(acceptance.shards),
        "shards": [
            {
                "shard_id": record.shard_id,
                "scope_id": record.opening_school_number,
                "raw_bundle_sha256": record.raw_bundle_sha256,
                "page_count": record.page_count,
                "loaded_count": record.loaded_count,
                "reported_total": record.reported_total,
                "page_count_semantics": "never_used_to_derive_completeness",
            }
            for record in acceptance.shards
        ],
        "merged_offering_count": acceptance.merged_offering_count,
        "offering_count_semantics": "merged_full_semester_snapshot_only",
        "snapshot.is_complete": acceptance.merged.is_complete,
        "reported_total": acceptance.merged.reported_total,
        "manifest_written": manifest_path is not None,
    }


def _write_manifest(path: Path, acceptance: FullSemesterAcceptance) -> None:
    """写出 canonical manifest（⛔ 原子写入；已存在且内容不同则 fail closed）。"""

    payload = canonical_manifest_bytes(acceptance.manifest)

    if path.exists() and not path.is_file():
        _fail(
            exit_code=EXIT_MANIFEST,
            status="manifest_write_failed",
            stage="manifest_write",
            category="manifest_path_not_a_file",
            exception=ManifestWriteError("manifest path is not a file"),
        )

    if path.is_file():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            _fail(
                exit_code=EXIT_MANIFEST,
                status="manifest_write_failed",
                stage="manifest_write",
                category="manifest_read_error",
                exception=exc,
            )

        if existing != payload:
            _fail(
                exit_code=EXIT_MANIFEST,
                status="manifest_write_failed",
                stage="manifest_write",
                category="manifest_already_exists_with_different_content",
                exception=ManifestWriteError("manifest already exists"),
            )
    else:
        directory = path.parent
        try:
            if not directory.is_dir():
                raise ManifestWriteError("manifest parent directory does not exist")

            handle, temporary = tempfile.mkstemp(
                dir=str(directory), prefix=path.name, suffix=".tmp"
            )
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(payload)
                os.replace(temporary, path)
            except BaseException:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise
        except OSError as exc:
            _fail(
                exit_code=EXIT_MANIFEST,
                status="manifest_write_failed",
                stage="manifest_write",
                category="manifest_write_error",
                exception=exc,
            )
        except ManifestWriteError as exc:
            _fail(
                exit_code=EXIT_MANIFEST,
                status="manifest_write_failed",
                stage="manifest_write",
                category="manifest_write_error",
                exception=exc,
            )

    # ⛔ 落盘后复算：文件字节的 SHA-256 必须**就是** acceptance identity，
    #    否则"manifest SHA = acceptance identity"这句话不成立。
    try:
        digest = compute_artifact_sha256(path.read_bytes())
    except (OSError, CourseDataStoreError) as exc:
        _fail(
            exit_code=EXIT_MANIFEST,
            status="manifest_write_failed",
            stage="manifest_recheck",
            category="manifest_recheck_error",
            exception=exc,
        )

    if digest != acceptance.manifest_sha256:
        _fail(
            exit_code=EXIT_MANIFEST,
            status="manifest_write_failed",
            stage="manifest_recheck",
            category="manifest_digest_not_reproducible",
            exception=ManifestWriteError("manifest digest mismatch"),
        )


def accept_full_semester(args: argparse.Namespace) -> dict[str, object]:
    """Run the acceptance and return only aggregate, non-row output."""

    semester, baseline_before, baseline_after, artifacts = _validated_inputs(args)

    try:
        acceptance = accept_full_semester_capture_set(
            expected_semester=semester,
            baseline_before=baseline_before,
            baseline_after=baseline_after,
            shard_artifacts=artifacts,
        )
    except FullSemesterAcceptanceError as exc:
        exit_code = _CATEGORY_EXIT_CODES.get(exc.category, EXIT_SHARD_SET)
        extra = (
            {"shard_id": exc.shard_id} if getattr(exc, "shard_id", None) else None
        )
        _fail(
            exit_code=exit_code,
            status="acceptance_failed",
            stage=_stage_for_category(exc.category),
            category=exc.category,
            exception=exc,
            extra=extra,
        )

    expected_manifest_sha256 = getattr(args, "expected_manifest_sha256", None)
    if expected_manifest_sha256 is not None:
        if (
            not isinstance(expected_manifest_sha256, str)
            or expected_manifest_sha256.strip().lower() != acceptance.manifest_sha256
        ):
            _fail(
                exit_code=EXIT_MANIFEST,
                status="manifest_write_failed",
                stage="manifest_identity",
                category="manifest_sha256_mismatch",
                exception=ManifestDigestMismatchError("manifest digest mismatch"),
            )

    manifest_path = (
        Path(args.output_manifest) if args.output_manifest is not None else None
    )
    if manifest_path is not None:
        _write_manifest(manifest_path, acceptance)

    summary = _summary(acceptance=acceptance, manifest_path=manifest_path)

    sqlite_path = args.sqlite
    if sqlite_path is None:
        return {"status": "accepted", "sqlite_imported": False, **summary}

    try:
        import_result = import_offering_snapshot(
            sqlite_path,
            acceptance.merged,
            artifact_sha256=acceptance.manifest_sha256,
            scope=acceptance.scope,
        )
        provenance = [
            item
            for item in load_course_data_provenance(sqlite_path, semester=semester)
            if item.artifact_sha256 == acceptance.manifest_sha256
            and item.scope_kind == acceptance.scope.scope_kind
            and item.scope_id == acceptance.scope.scope_id
        ]
        if len(provenance) != 1:
            raise ProvenanceReadBackError("expected one provenance record")

        record = provenance[0]
        # ⛔ 逐项核对：acceptance identity / semester / full_semester scope /
        #    completeness / 三个计数。
        if (
            record.artifact_sha256 != acceptance.manifest_sha256
            or record.semester != semester
            or record.scope_kind != acceptance.scope.scope_kind
            or record.scope_id != semester
            or record.source != acceptance.source
            or record.completeness != "complete"
            or record.loaded_count != acceptance.merged.loaded_count
            or record.reported_total != acceptance.merged.reported_total
            or record.offering_count != acceptance.merged_offering_count
        ):
            _fail(
                exit_code=EXIT_SQLITE,
                status="sqlite_import_failed",
                stage="sqlite_readback_validation",
                category="provenance_readback_mismatch",
                exception=ProvenanceReadBackError("provenance mismatch"),
            )

        if (
            import_result.inserted
            + import_result.updated
            + import_result.unchanged
            != record.offering_count
        ):
            _fail(
                exit_code=EXIT_SQLITE,
                status="sqlite_import_failed",
                stage="sqlite_reconciliation",
                category="reconciliation_mismatch",
                exception=ProvenanceReadBackError("reconciliation mismatch"),
            )

        db_offerings = load_course_offerings(sqlite_path, semester)
    except Exception as exc:
        _fail(
            exit_code=EXIT_SQLITE,
            status="sqlite_import_failed",
            stage="sqlite_import_and_readback",
            category="store_error",
            exception=exc,
        )

    return {
        "status": "imported",
        "sqlite_imported": True,
        **summary,
        "inserted": import_result.inserted,
        "updated": import_result.updated,
        "unchanged": import_result.unchanged,
        "reconciled_offering_count": import_result.inserted
        + import_result.updated
        + import_result.unchanged,
        # ⚠️ 这是**整个学期**当前库里的 offering 数（可能包含其它 artifact / 旧的
        #    campus import），⛔ 不是本次 acceptance 的 offering 数。
        "db_semester_offering_count": len(db_offerings),
        "db_semester_offering_count_semantics": (
            "all_offerings_currently_stored_for_this_semester_not_this_acceptance"
        ),
        "provenance_artifact_sha256": provenance[0].artifact_sha256,
        "provenance_semester": provenance[0].semester,
        "provenance_scope_kind": provenance[0].scope_kind,
        "provenance_scope_id": provenance[0].scope_id,
        "provenance_completeness": provenance[0].completeness,
        "provenance_loaded_count": provenance[0].loaded_count,
        "provenance_reported_total": provenance[0].reported_total,
        "provenance_offering_count": provenance[0].offering_count,
    }


def _stage_for_category(category: str) -> str:
    """失败类别 → 阶段名（只用于输出，⛔ 不参与判定）。"""

    if category in {
        "invalid_semester",
        "invalid_baseline",
    }:
        return "arguments"
    if category in {
        "duplicate_shard",
        "unknown_shard",
        "missing_shard",
    }:
        return "shard_set_validation"
    if category in {
        "bundle_read_failed",
        "bundle_changed_during_acceptance",
        "bundle_digest_mismatch",
    }:
        return "artifact_read"
    if category in {
        "invalid_capture_bundle",
        "semester_mismatch",
    }:
        return "bundle_validation"
    if category in {
        "shard_not_complete",
        "empty_shard",
    }:
        return "completeness_validation"
    if category in {
        "snapshot_window_unstable",
        "shard_coverage_mismatch",
    }:
        return "baseline_validation"
    if category in {
        "duplicate_identity_across_shards",
        "conflicting_identity_across_shards",
        "merge_failed",
        "merged_count_mismatch",
    }:
        return "merge_validation"
    return "acceptance"


def _emit(payload: dict[str, object], *, stream: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stream)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        result = accept_full_semester(args)
    except AcceptanceFailure as failure:
        _emit(failure.payload, stream=sys.stderr)
        return failure.exit_code
    except CliArgumentError as exc:
        _emit(
            {
                "status": "invalid_arguments",
                "exception_type": type(exc).__name__,
                "stage": "arguments",
                "category": "invalid_arguments",
            },
            stream=sys.stderr,
        )
        return EXIT_ARGUMENTS
    except CourseDataStoreError as exc:  # pragma: no cover - defensive
        _emit(
            {
                "status": "sqlite_import_failed",
                "exception_type": type(exc).__name__,
                "stage": "sqlite_import_and_readback",
                "category": "store_error",
            },
            stream=sys.stderr,
        )
        return EXIT_SQLITE

    _emit(result, stream=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
