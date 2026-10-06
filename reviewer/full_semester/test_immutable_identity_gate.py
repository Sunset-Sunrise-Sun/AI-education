"""STRICT reviewer gate, expected-to-fail until immutable acceptance identity is fixed.

Not in backend default testpaths. No xfail markers: failures are real gate failures.
Run against a selected Builder archive with its backend on PYTHONPATH.
"""
import hashlib
import json
import sqlite3

import pytest

from app.course_data import import_offering_snapshot
from app.course_data.store import CourseDataStoreError
from app.course_data.full_semester_acceptance import canonical_manifest_bytes

from test_closure_probes import accepted, inputs, changed_snapshot, SEMESTER


def semantic_rows(path):
    with sqlite3.connect(path) as connection:
        acceptance_rows = connection.execute(
            "SELECT artifact_sha256,semester,scope_kind,scope_id,source,completeness,"
            "loaded_count,reported_total,offering_count,offering_set_sha256 "
            "FROM course_data_acceptance ORDER BY artifact_sha256,semester,scope_kind,scope_id").fetchall()
        members = connection.execute(
            "SELECT * FROM course_data_acceptance_member ORDER BY artifact_sha256,semester,course_id,class_id"
        ).fetchall()
    return acceptance_rows, members


def test_same_sha_same_identity_same_count_changed_payload_import_must_reject(accepted):
    path, result, provider = accepted
    original = provider.get_course_offerings(SEMESTER)
    expected_semantics = semantic_rows(path)
    dataset_b = changed_snapshot(result)
    assert len(dataset_b.offerings) == len(original)
    assert [(o.semester, o.course_id, o.class_id) for o in dataset_b.offerings] == [
        (o.semester, o.course_id, o.class_id) for o in original]
    assert dataset_b.offerings[0].course_name != original[0].course_name
    with pytest.raises(CourseDataStoreError):
        import_offering_snapshot(path, dataset_b,
                                artifact_sha256=result.manifest_sha256, scope=result.scope)
    assert semantic_rows(path) == expected_semantics
    assert provider.get_course_offerings(SEMESTER) == original


def test_existing_semantic_acceptance_and_members_are_not_updated(accepted):
    path, result, provider = accepted
    before = semantic_rows(path)
    # Instrument test database only; no production implementation or migration is modified.
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TRIGGER reviewer_no_acceptance_semantic_update
            BEFORE UPDATE OF artifact_sha256,semester,scope_kind,scope_id,source,completeness,
                             loaded_count,reported_total,offering_count,offering_set_sha256
            ON course_data_acceptance BEGIN
              SELECT RAISE(ABORT,'reviewer detected semantic acceptance UPDATE');
            END;
            CREATE TRIGGER reviewer_no_member_update
            BEFORE UPDATE ON course_data_acceptance_member BEGIN
              SELECT RAISE(ABORT,'reviewer detected member UPDATE');
            END;
            CREATE TRIGGER reviewer_no_member_delete
            BEFORE DELETE ON course_data_acceptance_member BEGIN
              SELECT RAISE(ABORT,'reviewer detected member DELETE/rebuild');
            END;
        """)
    # Exact content reimport may refresh audit timestamps/repair rows, but not semantic identity.
    import_offering_snapshot(path, result.merged,
                            artifact_sha256=result.manifest_sha256, scope=result.scope)
    assert semantic_rows(path) == before
    assert provider.get_course_offerings(SEMESTER) == list(result.merged.offerings)


def test_stored_canonical_manifest_recomputes_to_pinned_sha(accepted):
    path, result, _ = accepted
    with sqlite3.connect(path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(course_data_acceptance)")]
        document_columns = [name for name in columns if "manifest" in name and "sha256" not in name]
        assert document_columns, "acceptance stores no canonical manifest document to recompute against configured SHA"
        # A future separate manifest table needs an explicit binding read in this gate after inspection.
        record = connection.execute(
            'SELECT "' + document_columns[0] + '" FROM course_data_acceptance '
            "WHERE artifact_sha256=? AND scope_kind='full_semester'",
            (result.manifest_sha256,),
        ).fetchone()
    assert record is not None and record[0] is not None
    raw = record[0].encode("utf-8") if isinstance(record[0], str) else bytes(record[0])
    document = json.loads(raw)
    assert canonical_manifest_bytes(document) == raw
    assert hashlib.sha256(raw).hexdigest() == result.manifest_sha256
