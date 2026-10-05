#!/usr/bin/env python3
"""Validate and optionally import one local Course Data Capture Bundle.

This is an internal, zero-network acceptance tool.  It deliberately composes the
existing Capture Bridge and SQLite store instead of implementing another parser,
bundle validator, completeness check, or persistence layer.

Security / provenance boundary:

    source label = audit label only
    artifact SHA-256 = exact-byte identity / integrity
    source label != acquisition provenance proof

Failure output is intentionally aggregate-only.  Exception messages are never
printed because normalization errors can originate from sensitive captured rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.course_data import (  # noqa: E402
    SCOPE_KIND_CAMPUS,
    CourseDataStoreError,
    SnapshotScope,
    collect_captured_pages_snapshot,
    compute_artifact_sha256,
    import_offering_snapshot,
    load_capture_bundle,
    load_course_data_provenance,
    load_course_offerings,
)


EXIT_ARGUMENTS = 2
EXIT_ARTIFACT_READ = 3
EXIT_SCOPE = 4
EXIT_NORMALIZATION = 5
EXIT_INCOMPLETE = 6
EXIT_SQLITE = 7


class CliArgumentError(ValueError):
    """The CLI shape is invalid; no user-supplied value is retained or printed."""


class SourceLabelError(ValueError):
    """The explicit audit label does not match the declared campus scope."""


class SemesterMismatchError(ValueError):
    """The validated bundle semester differs from the explicit expected semester."""


class ArtifactChangedError(RuntimeError):
    """The file changed between exact-byte hashing and existing-validator loading."""


class IncompleteSnapshotError(RuntimeError):
    """The existing pagination core classified the snapshot as incomplete."""


class ProvenanceReadBackError(RuntimeError):
    """The imported artifact could not be read back as one exact provenance record."""


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
            "Validate one local SYSU Course Data Capture Bundle and optionally import "
            "a complete snapshot into SQLite. The source is an audit label, not "
            "provenance proof; SHA-256 identifies the exact artifact bytes."
        )
    )
    parser.add_argument("--bundle", required=True, help="local Capture Bundle JSON path")
    parser.add_argument("--expected-semester", required=True)
    parser.add_argument("--scope-kind", required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--source", required=True, help="explicit audit label")
    parser.add_argument(
        "--sqlite",
        help="optional SQLite path; import occurs only after complete validation",
    )
    return parser


def _validated_arguments(args: argparse.Namespace) -> tuple[str, str, SnapshotScope]:
    semester = args.expected_semester
    source = args.source

    if not isinstance(semester, str) or not semester.strip():
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="invalid_expected_semester",
            exception=CliArgumentError("invalid expected semester"),
        )
    if not isinstance(source, str) or not source.strip():
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="invalid_source_label",
            exception=CliArgumentError("invalid source label"),
        )

    semester = semester.strip()
    source = source.strip()

    try:
        scope = SnapshotScope(scope_kind=args.scope_kind, scope_id=args.scope_id)
    except CourseDataStoreError as exc:
        _fail(
            exit_code=EXIT_SCOPE,
            status="scope_invalid",
            stage="scope_validation",
            category="invalid_scope",
            exception=exc,
        )

    if scope.scope_kind == SCOPE_KIND_CAMPUS:
        expected_source = f"capture://sysu/{semester}/campus/{scope.scope_id}"
        if source != expected_source:
            _fail(
                exit_code=EXIT_SCOPE,
                status="scope_invalid",
                stage="source_validation",
                category="invalid_campus_source_label",
                exception=SourceLabelError("invalid campus source label"),
            )

    return semester, source, scope


def _read_and_validate_bundle(path: Path) -> tuple[bytes, str, dict[str, Any]]:
    try:
        artifact_bytes = path.read_bytes()
    except OSError as exc:
        _fail(
            exit_code=EXIT_ARTIFACT_READ,
            status="artifact_read_failed",
            stage="artifact_read",
            category="read_error",
            exception=exc,
        )

    try:
        artifact_sha256 = compute_artifact_sha256(artifact_bytes)
    except CourseDataStoreError as exc:
        _fail(
            exit_code=EXIT_ARTIFACT_READ,
            status="artifact_read_failed",
            stage="artifact_hash",
            category="sha256_error",
            exception=exc,
        )

    try:
        bundle = load_capture_bundle(path)
    except Exception as exc:
        _fail(
            exit_code=EXIT_NORMALIZATION,
            status="normalization_failed",
            stage="bundle_validation",
            category="invalid_capture_bundle",
            exception=exc,
        )

    # `load_capture_bundle()` intentionally owns validation and reads the given file.
    # Re-read afterwards so the digest cannot silently describe different bytes if
    # another process changes the artifact during acceptance.
    try:
        bytes_after_validation = path.read_bytes()
    except OSError as exc:
        _fail(
            exit_code=EXIT_ARTIFACT_READ,
            status="artifact_read_failed",
            stage="artifact_recheck",
            category="read_error",
            exception=exc,
        )
    if bytes_after_validation != artifact_bytes:
        _fail(
            exit_code=EXIT_ARTIFACT_READ,
            status="artifact_read_failed",
            stage="artifact_recheck",
            category="artifact_changed_during_validation",
            exception=ArtifactChangedError("artifact changed"),
        )

    return artifact_bytes, artifact_sha256, dict(bundle)


def _summary(
    *,
    artifact_sha256: str,
    bundle: dict[str, Any],
    snapshot: Any,
    scope: SnapshotScope,
    source: str,
) -> dict[str, object]:
    return {
        "artifact_sha256": artifact_sha256,
        "artifact_sha256_semantics": "exact_byte_identity_and_integrity",
        "format": bundle["format"],
        "semester": bundle["semester"],
        "first_page_no": bundle["first_page_no"],
        "page_size": bundle["page_size"],
        "page_count": len(bundle["pages"]),
        "loaded_count": snapshot.loaded_count,
        "reported_total": snapshot.reported_total,
        "offering_count": len(snapshot.offerings),
        "snapshot.is_complete": snapshot.is_complete,
        "scope_kind": scope.scope_kind,
        "scope_id": scope.scope_id,
        "source": source,
        "source_semantics": "audit_label_only_not_provenance_proof",
    }


def accept_artifact(args: argparse.Namespace) -> dict[str, object]:
    """Run acceptance and return only aggregate, non-row output."""

    expected_semester, source, scope = _validated_arguments(args)
    _, artifact_sha256, bundle = _read_and_validate_bundle(Path(args.bundle))

    if bundle["semester"] != expected_semester:
        _fail(
            exit_code=EXIT_NORMALIZATION,
            status="normalization_failed",
            stage="semester_validation",
            category="semester_mismatch",
            exception=SemesterMismatchError("semester mismatch"),
        )

    try:
        snapshot = collect_captured_pages_snapshot(bundle, source=source)
    except Exception as exc:
        _fail(
            exit_code=EXIT_NORMALIZATION,
            status="normalization_failed",
            stage="snapshot_normalization",
            category="normalization_error",
            exception=exc,
        )

    summary = _summary(
        artifact_sha256=artifact_sha256,
        bundle=bundle,
        snapshot=snapshot,
        scope=scope,
        source=source,
    )

    if not snapshot.is_complete:
        _fail(
            exit_code=EXIT_INCOMPLETE,
            status="incomplete_snapshot",
            stage="completeness_validation",
            category="snapshot_not_complete",
            exception=IncompleteSnapshotError("incomplete snapshot"),
            extra=summary,
        )

    sqlite_path = args.sqlite
    if sqlite_path is None:
        return {"status": "validated", "sqlite_imported": False, **summary}

    try:
        import_result = import_offering_snapshot(
            sqlite_path,
            snapshot,
            artifact_sha256=artifact_sha256,
            scope=scope,
        )
        provenance = [
            item
            for item in load_course_data_provenance(sqlite_path, semester=expected_semester)
            if item.artifact_sha256 == artifact_sha256
            and item.scope_kind == scope.scope_kind
            and item.scope_id == scope.scope_id
        ]
        if len(provenance) != 1:
            raise ProvenanceReadBackError("expected one provenance record")

        db_offerings = load_course_offerings(sqlite_path, expected_semester)
    except Exception as exc:
        _fail(
            exit_code=EXIT_SQLITE,
            status="sqlite_import_failed",
            stage="sqlite_import_and_readback",
            category="store_error",
            exception=exc,
        )

    provenance_record = provenance[0]
    return {
        "status": "imported",
        "sqlite_imported": True,
        **summary,
        "inserted": import_result.inserted,
        "updated": import_result.updated,
        "unchanged": import_result.unchanged,
        "db_offering_count": len(db_offerings),
        "provenance_artifact_sha256": provenance_record.artifact_sha256,
        "provenance_scope_kind": provenance_record.scope_kind,
        "provenance_scope_id": provenance_record.scope_id,
    }


def _emit(payload: dict[str, object], *, stream: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stream)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        result = accept_artifact(args)
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

    _emit(result, stream=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
