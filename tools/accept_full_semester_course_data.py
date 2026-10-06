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

Independence contract (Forward Red-Team BLOCK B2):

    A caller saying "this file is the East campus bundle" is NOT evidence.
    A formal acceptance therefore consumes, per shard:

        1. an approved capture inventory
           (semester, shard_id, openingSchoolNumber, raw_bundle_sha256)
        2. the already-imported campus acceptance record for those exact bytes
           (scope_kind=campus, scope_id=approved number, canonical campus source,
            same counts, same normalized content digest)

    One artifact may not be declared as two campuses; the five raw digests must
    be pairwise distinct; filenames never decide scope and rows never imply it.

Exact-byte contract (BLOCK B1):

    the exact bytes hashed == the exact bytes parsed
    (one read; digest and JSON parsing consume the same bytes)

Content-binding contract (BLOCK B3):

    merged_offering_set_sha256 = SHA256 of the canonical normalized offering
    content of the accepted dataset, so a same-count / same-identity payload
    substitution cannot pass.

Exact five-shard requirement (no escape hatches):

    east-campus / south-campus / shenzhen-campus / zhuhai-campus / north-campus

Missing, duplicate, unknown or aliased shard ids are rejected.  There is no
``--skip-north`` / ``--allow-partial-semester`` / ``--force-complete``.

Baseline semantics:

    baseline_before / baseline_after are the collector's *reported totals* for
    the whole semester immediately before and after the capture window.  They
    are totals, NOT a baseline OfferingSnapshot.
    baseline_before != baseline_after         -> snapshot_window_unstable
    sum(shard reported_total) != baseline     -> shard_coverage_mismatch

    Completeness is never derived from captured page counts.

Transaction caveat:

    the SQLite import commit and the provenance read-back are NOT one
    transaction, so a non-zero exit does not by itself prove the database is
    unchanged.  Failures before any store call only prove that this call did
    not happen.

Draft inventory mode:

    ``--draft-inventory <path>`` only writes a canonical inventory *draft* from
    the five local files and exits WITHOUT accepting anything.  The draft is not
    an approval: a human/review step is what makes an inventory approved, and
    this tool cannot prove that any given inventory went through it.

Failure output is intentionally aggregate-only.  Exception messages are never
printed because normalization errors can originate from sensitive captured rows.
"""

from __future__ import annotations

import argparse
import hashlib
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
    CourseDataStoreError,
    FullSemesterAcceptance,
    FullSemesterAcceptanceError,
    ShardArtifact,
    accept_full_semester_capture_set,
    build_capture_inventory,
    canonical_manifest_bytes,
    capture_inventory_bytes,
    compute_artifact_sha256,
    import_offering_snapshot,
    load_accepted_offerings,
    load_capture_inventory,
    load_course_offerings,
    validate_full_semester_manifest_bytes,
)


EXIT_ARGUMENTS = 2
EXIT_ARTIFACT_READ = 3
EXIT_BASELINE = 4
EXIT_SHARD_SET = 5
EXIT_COMPLETENESS = 6
EXIT_SQLITE = 7
EXIT_MANIFEST = 8
EXIT_INVENTORY = 9
EXIT_CAMPUS_BINDING = 10

#: 失败类别 → 退出码（机器可读映射；⛔ 不解析错误文本）。
_CATEGORY_EXIT_CODES: dict[str, int] = {
    "invalid_semester": EXIT_ARGUMENTS,
    "invalid_baseline": EXIT_BASELINE,
    "inventory_invalid": EXIT_INVENTORY,
    "inventory_digest_mismatch": EXIT_INVENTORY,
    "duplicate_shard": EXIT_SHARD_SET,
    "unknown_shard": EXIT_SHARD_SET,
    "missing_shard": EXIT_SHARD_SET,
    "duplicate_artifact_bytes": EXIT_SHARD_SET,
    "bundle_read_failed": EXIT_ARTIFACT_READ,
    "bundle_changed_during_acceptance": EXIT_ARTIFACT_READ,
    "bundle_digest_mismatch": EXIT_ARTIFACT_READ,
    "invalid_capture_bundle": EXIT_SHARD_SET,
    "semester_mismatch": EXIT_SHARD_SET,
    "shard_not_complete": EXIT_COMPLETENESS,
    "empty_shard": EXIT_COMPLETENESS,
    "campus_acceptance_missing": EXIT_CAMPUS_BINDING,
    "campus_acceptance_mismatch": EXIT_CAMPUS_BINDING,
    "snapshot_window_unstable": EXIT_BASELINE,
    "shard_coverage_mismatch": EXIT_BASELINE,
    "duplicate_identity_across_shards": EXIT_SHARD_SET,
    "conflicting_identity_across_shards": EXIT_SHARD_SET,
    "merge_failed": EXIT_SHARD_SET,
    "merged_count_mismatch": EXIT_SHARD_SET,
    "manifest_invalid": EXIT_MANIFEST,
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
    """The imported acceptance could not be read back as one exact acceptance."""


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
            "A formal acceptance requires an approved capture inventory and the "
            "matching campus acceptance records; the manifest SHA-256 is the "
            "acceptance identity."
        )
    )
    parser.add_argument("--semester", required=True)
    parser.add_argument(
        "--baseline-before", help="collector reported total before the window"
    )
    parser.add_argument(
        "--baseline-after", help="collector reported total after the window"
    )
    for shard_id, option in _SHARD_OPTIONS:
        parser.add_argument(
            option,
            required=True,
            metavar="BUNDLE",
            help=f"local Capture Bundle JSON path for {shard_id}",
        )
    parser.add_argument(
        "--inventory",
        help="approved capture inventory (required for a formal acceptance)",
    )
    parser.add_argument(
        "--campus-store",
        help="SQLite store holding the five imported campus acceptances (required)",
    )
    parser.add_argument(
        "--draft-inventory",
        help=(
            "write a canonical inventory DRAFT from the five files and exit "
            "without accepting anything"
        ),
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
    """把 CLI 上的总量证据解析成非负整数（⛔ 不接受空 / 小数 / 负数）。"""

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


def _validated_inputs(args: argparse.Namespace) -> tuple[str, list[ShardArtifact]]:
    semester = args.semester
    if not isinstance(semester, str) or not semester.strip():
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="invalid_semester",
            exception=CliArgumentError("invalid semester"),
        )

    artifacts = [
        ShardArtifact(
            shard_id=shard_id,
            bundle_path=getattr(args, option.lstrip("-").replace("-", "_")),
        )
        for shard_id, option in _SHARD_OPTIONS
    ]

    return semester.strip(), artifacts


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
        "inventory_sha256": acceptance.inventory_sha256,
        "inventory_sha256_semantics": "approved_capture_inventory_document_identity",
        "baseline_before": acceptance.baseline_before,
        "baseline_after": acceptance.baseline_after,
        "baseline_semantics": "collector_reported_total_not_a_baseline_snapshot",
        "baseline_stable": acceptance.baseline_before == acceptance.baseline_after,
        "shard_count": len(acceptance.shards),
        "shards": [
            {
                "shard_id": record.shard_id,
                "openingSchoolNumber": record.opening_school_number,
                "raw_bundle_sha256": record.raw_bundle_sha256,
                "campus_acceptance_sha256": record.campus_acceptance_sha256,
                "campus_offering_set_sha256": record.campus_offering_set_sha256,
                "page_count": record.page_count,
                "loaded_count": record.loaded_count,
                "reported_total": record.reported_total,
                "page_count_semantics": "never_used_to_derive_completeness",
            }
            for record in acceptance.shards
        ],
        "merged_offering_count": acceptance.merged_offering_count,
        "merged_offering_set_sha256": acceptance.merged_offering_set_sha256,
        "offering_set_sha256_semantics": (
            "exact_normalized_offering_content_of_the_accepted_dataset"
        ),
        "snapshot.is_complete": acceptance.merged.is_complete,
        "reported_total": acceptance.merged.reported_total,
        "manifest_written": manifest_path is not None,
    }


def _write_bytes(path: Path, payload: bytes, *, category: str, exit_code: int) -> None:
    """原子写入；已存在且内容不同 ⇒ fail closed（⛔ 不覆盖已批准的产物）。"""

    if path.exists() and not path.is_file():
        _fail(
            exit_code=exit_code,
            status="write_failed",
            stage="write",
            category="path_is_not_a_file",
            exception=ManifestWriteError("path is not a file"),
        )

    if path.is_file():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            _fail(
                exit_code=exit_code,
                status="write_failed",
                stage="write",
                category="read_error",
                exception=exc,
            )
        if existing != payload:
            _fail(
                exit_code=exit_code,
                status="write_failed",
                stage="write",
                category=category,
                exception=ManifestWriteError("existing file differs"),
            )
        return

    directory = path.parent
    try:
        if not directory.is_dir():
            raise ManifestWriteError("parent directory does not exist")

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
            exit_code=exit_code,
            status="write_failed",
            stage="write",
            category="write_error",
            exception=exc,
        )
    except ManifestWriteError as exc:
        _fail(
            exit_code=exit_code,
            status="write_failed",
            stage="write",
            category="write_error",
            exception=exc,
        )


def _write_manifest(path: Path, acceptance: FullSemesterAcceptance) -> None:
    """写出 canonical manifest，并用**严格校验器**回读确认 identity。"""

    payload = canonical_manifest_bytes(acceptance.manifest)
    _write_bytes(
        path,
        payload,
        category="manifest_already_exists_with_different_content",
        exit_code=EXIT_MANIFEST,
    )

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

    # ⛔ 落盘后按**严格校验器**再读一次：拒绝未知字段 / 重复键 / 非法计数。
    try:
        validated = validate_full_semester_manifest_bytes(path.read_bytes())
    except FullSemesterAcceptanceError as exc:
        _fail(
            exit_code=EXIT_MANIFEST,
            status="manifest_write_failed",
            stage="manifest_validation",
            category="manifest_invalid",
            exception=exc,
        )

    if canonical_manifest_bytes(validated) != payload:
        _fail(
            exit_code=EXIT_MANIFEST,
            status="manifest_write_failed",
            stage="manifest_validation",
            category="manifest_invalid",
            exception=ManifestWriteError("manifest is not canonical"),
        )


def _draft_inventory(args: argparse.Namespace) -> dict[str, object]:
    """只写 inventory 草稿，⛔ 不做任何 acceptance、⛔ 不写库。"""

    semester, artifacts = _validated_inputs(args)
    path = Path(args.draft_inventory)

    digests: dict[str, str] = {}
    for artifact in artifacts:
        file_path = Path(artifact.bundle_path)
        try:
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except OSError as exc:
            _fail(
                exit_code=EXIT_ARTIFACT_READ,
                status="artifact_read_failed",
                stage="artifact_read",
                category="bundle_read_failed",
                exception=exc,
                extra={"shard_id": artifact.shard_id},
            )
        digests[artifact.shard_id] = digest

    try:
        inventory = build_capture_inventory(semester, digests)
    except FullSemesterAcceptanceError as exc:
        _fail(
            exit_code=EXIT_INVENTORY,
            status="inventory_draft_failed",
            stage="inventory_draft",
            category=exc.category,
            exception=exc,
        )

    document_bytes = capture_inventory_bytes(inventory)

    _write_bytes(
        path,
        document_bytes,
        category="inventory_already_exists_with_different_content",
        exit_code=EXIT_INVENTORY,
    )

    return {
        "status": "draft_inventory_written",
        "acceptance_performed": False,
        "inventory_sha256": inventory.canonical_sha256,
        "inventory_sha256_semantics": "draft_document_identity_not_an_approval",
        "semester": inventory.semester,
        "shards": [
            {
                "shard_id": shard.shard_id,
                "openingSchoolNumber": shard.opening_school_number,
                "raw_bundle_sha256": shard.raw_bundle_sha256,
            }
            for shard in inventory.shards
        ],
        "note": (
            "draft only: an approved inventory must be reviewed out of band; "
            "this tool cannot prove that any inventory was approved"
        ),
    }


def accept_full_semester(args: argparse.Namespace) -> dict[str, object]:
    """Run the acceptance and return only aggregate, non-row output."""

    if args.draft_inventory:
        return _draft_inventory(args)

    semester, artifacts = _validated_inputs(args)

    if not args.inventory:
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="inventory_invalid",
            exception=CliArgumentError("approved inventory is required"),
        )
    if not args.campus_store:
        _fail(
            exit_code=EXIT_ARGUMENTS,
            status="invalid_arguments",
            stage="arguments",
            category="campus_acceptance_missing",
            exception=CliArgumentError("campus store is required"),
        )

    baseline_before = _parse_total(args.baseline_before, name="baseline_before")
    baseline_after = _parse_total(args.baseline_after, name="baseline_after")

    try:
        inventory = load_capture_inventory(args.inventory)
    except FullSemesterAcceptanceError as exc:
        _fail(
            exit_code=_CATEGORY_EXIT_CODES.get(exc.category, EXIT_INVENTORY),
            status="inventory_invalid",
            stage="inventory_validation",
            category=exc.category,
            exception=exc,
        )

    try:
        acceptance = accept_full_semester_capture_set(
            expected_semester=semester,
            baseline_before=baseline_before,
            baseline_after=baseline_after,
            shard_artifacts=artifacts,
            inventory=inventory,
            campus_store_path=args.campus_store,
        )
    except FullSemesterAcceptanceError as exc:
        exit_code = _CATEGORY_EXIT_CODES.get(exc.category, EXIT_SHARD_SET)
        extra = {"shard_id": exc.shard_id} if getattr(exc, "shard_id", None) else None
        _fail(
            exit_code=exit_code,
            status="acceptance_failed",
            stage=stage_for_category(exc.category),
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
            # ⛔ acceptance identity 是**不可变**的：canonical manifest 与 rows 同事务落库，
            #    使 Provider 每次读取都能重算 SHA256(canonical stored manifest) 并与
            #    configured SHA 比对（Forward Red-Team：immutable acceptance identity）。
            canonical_manifest=acceptance.manifest,
        )

        # ⛔ content-bound 回读（B3）：acceptance 平面必须与本次 acceptance 的
        #    scope / 计数 / 整批内容 digest 完全一致。
        dataset = load_accepted_offerings(
            sqlite_path,
            semester=semester,
            acceptance_sha256=acceptance.manifest_sha256,
        )
        record = dataset.acceptance

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
            # ⚠️ store 的 load_accepted_offerings 已经核对过整批 digest；
            #    这里再比一次是纵深防御（对账 CLI 看到的 manifest 与库）。
            or record.offering_set_sha256 != acceptance.merged_offering_set_sha256
            # ⛔ immutable acceptance identity：持久化的 canonical manifest 必须能重算出
            #    同一个 acceptance SHA（由 store 的 trust chain 给出）。
            or record.canonical_manifest_sha256 != acceptance.manifest_sha256
            or len(dataset.offerings) != acceptance.merged_offering_count
        ):
            _fail(
                exit_code=EXIT_SQLITE,
                status="sqlite_import_failed",
                stage="sqlite_readback_validation",
                category="provenance_readback_mismatch",
                exception=ProvenanceReadBackError("acceptance mismatch"),
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

        semester_row_count = len(load_course_offerings(sqlite_path, semester))
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
        # ⚠️ 该学期当前库里的**全部**行（可能含陈旧 campus 行 / 其它 artifact），
        #    ⛔ 不是本次 acceptance 的 offering 数（后者见 `merged_offering_count`）。
        "db_semester_offering_count": semester_row_count,
        "db_semester_offering_count_semantics": (
            "all_rows_currently_stored_for_this_semester_not_this_acceptance"
        ),
        "accepted_row_count": len(dataset.offerings),
        "accepted_row_count_semantics": "exact_rows_bound_to_this_acceptance",
        "provenance_artifact_sha256": record.artifact_sha256,
        "provenance_semester": record.semester,
        "provenance_scope_kind": record.scope_kind,
        "provenance_scope_id": record.scope_id,
        "provenance_completeness": record.completeness,
        "provenance_loaded_count": record.loaded_count,
        "provenance_reported_total": record.reported_total,
        "provenance_offering_count": record.offering_count,
        "provenance_offering_set_sha256": record.offering_set_sha256,
        "provenance_canonical_manifest_sha256": record.canonical_manifest_sha256,
    }


def stage_for_category(category: str) -> str:
    """失败类别 → 阶段名（只用于输出，⛔ 不参与判定）。"""

    if category in {"invalid_semester", "invalid_baseline"}:
        return "arguments"
    if category in {"inventory_invalid", "duplicate_artifact_bytes"}:
        return "inventory_validation"
    if category == "inventory_digest_mismatch":
        return "inventory_binding"
    if category in {"duplicate_shard", "unknown_shard", "missing_shard"}:
        return "shard_set_validation"
    if category in {
        "bundle_read_failed",
        "bundle_changed_during_acceptance",
        "bundle_digest_mismatch",
    }:
        return "artifact_read"
    if category in {"invalid_capture_bundle", "semester_mismatch"}:
        return "bundle_validation"
    if category in {"shard_not_complete", "empty_shard"}:
        return "completeness_validation"
    if category in {"campus_acceptance_missing", "campus_acceptance_mismatch"}:
        return "campus_binding"
    if category in {"snapshot_window_unstable", "shard_coverage_mismatch"}:
        return "baseline_validation"
    if category in {
        "duplicate_identity_across_shards",
        "conflicting_identity_across_shards",
        "merge_failed",
        "merged_count_mismatch",
    }:
        return "merge_validation"
    if category == "manifest_invalid":
        return "manifest_validation"
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
