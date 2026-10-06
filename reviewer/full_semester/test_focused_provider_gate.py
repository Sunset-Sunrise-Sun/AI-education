"""Focused provider gate for ef910e3 or newer. No Runtime/E2E execution here.

Uses our independently generated five-shard inputs from the prior reviewer helper.
Every acceptance import now supplies the real generated canonical manifest.
"""
import copy
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager

import pytest

import app.course_data.store as store
from app.course_data import import_offering_snapshot, OfferingSnapshot
from app.course_data.store_provider import StoreBackedCourseDataProvider, CourseDataAcceptanceError
from test_closure_probes import inputs, accept, SEMESTER


@pytest.fixture
def dataset(inputs, tmp_path):
    result = accept(inputs)
    path = tmp_path / "focused-accepted.sqlite"
    import_offering_snapshot(path, result.merged, artifact_sha256=result.manifest_sha256,
                            scope=result.scope, canonical_manifest=result.manifest)
    provider = StoreBackedCourseDataProvider(sqlite_path=path, semester=SEMESTER,
                                            acceptance_sha256=result.manifest_sha256)
    return path, result, provider


def db_state(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.execute(f"SELECT * FROM {table} ORDER BY 1,2,3,4").fetchall()
                     for table in ("course_data_acceptance", "course_data_acceptance_member",
                                   "course_offering", "course_data_import"))


@pytest.mark.parametrize("field,value", [
    ("course_name", "Synthetic B"), ("teacher", "Synthetic teacher"),
    ("credit", 4.0), ("capacity", 21), ("remaining_capacity", 3),
    ("meetings", [{"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1]}]),
])
@pytest.mark.parametrize("manifest_strategy", ["original", "changed", "omitted"])
def test_same_sha_dataset_b_rejected_atomically(dataset, field, value, manifest_strategy):
    path, result, provider = dataset
    before = db_state(path)
    original_rows = provider.get_course_offerings(SEMESTER)
    payload = result.merged.offerings[0].model_dump(mode="json")
    payload[field] = value
    changed_row = type(result.merged.offerings[0]).model_validate(payload)
    rows_b = (changed_row, *result.merged.offerings[1:])
    dataset_b = OfferingSnapshot(SEMESTER, rows_b, "complete", len(rows_b))
    manifest = copy.deepcopy(dict(result.manifest))
    from app.course_data.offering_digest import offering_set_sha256
    if manifest_strategy == "changed":
        manifest["merged_offering_set_sha256"] = offering_set_sha256(rows_b)
    kwargs = {} if manifest_strategy == "omitted" else {"canonical_manifest": manifest}
    with pytest.raises(store.CourseDataStoreError):
        import_offering_snapshot(path, dataset_b, artifact_sha256=result.manifest_sha256,
                                scope=result.scope, **kwargs)
    assert db_state(path) == before  # Includes rows, records, timestamps: failure is atomic.
    assert provider.get_course_offerings(SEMESTER) == original_rows
    reconstructed = StoreBackedCourseDataProvider(sqlite_path=path, semester=SEMESTER,
                                                  acceptance_sha256=result.manifest_sha256)
    assert reconstructed.get_course_offerings(SEMESTER) == original_rows


def test_stored_manifest_canonical_sha_and_idempotency_no_semantic_updates(dataset):
    path, result, provider = dataset
    with sqlite3.connect(path) as connection:
        raw = connection.execute("SELECT canonical_manifest_json FROM course_data_acceptance").fetchone()[0]
        canonical = json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False).encode()
        assert raw.encode() == canonical
        assert hashlib.sha256(canonical).hexdigest() == provider.acceptance_sha256
        connection.executescript("""
          CREATE TRIGGER reviewer_no_semantic_update BEFORE UPDATE ON course_data_acceptance
          BEGIN SELECT RAISE(ABORT,'semantic acceptance UPDATE'); END;
          CREATE TRIGGER reviewer_no_member_update BEFORE UPDATE ON course_data_acceptance_member
          BEGIN SELECT RAISE(ABORT,'member UPDATE'); END;
          CREATE TRIGGER reviewer_no_member_delete BEFORE DELETE ON course_data_acceptance_member
          BEGIN SELECT RAISE(ABORT,'member DELETE/reinsert'); END;
        """)
    before = db_state(path)
    import_offering_snapshot(path, result.merged, artifact_sha256=result.manifest_sha256,
                            scope=result.scope, canonical_manifest=result.manifest)
    after = db_state(path)
    assert after[:2] == before[:2]  # Semantic planes, including original accepted timestamp, unchanged.
    assert provider.get_course_offerings(SEMESTER) == list(result.merged.offerings)


@pytest.mark.parametrize("mutation", ["semantic", "whitespace", "duplicate-key", "unknown-field", "non-json"])
def test_stored_manifest_tamper_rejected(dataset, mutation):
    path, result, provider = dataset
    document = copy.deepcopy(dict(result.manifest))
    if mutation == "semantic":
        document["merged_offering_set_sha256"] = "f" * 64
    elif mutation == "unknown-field":
        document["unexpected"] = True
    raw = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if mutation == "whitespace":
        raw = json.dumps(document, indent=2)
    elif mutation == "duplicate-key":
        raw = '{"semester":"2026-1",' + raw[1:]
    elif mutation == "non-json":
        raw = "invalid"
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE course_data_acceptance SET canonical_manifest_json=?", (raw,))
    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


@pytest.mark.parametrize("mutation", ["delete-acceptance", "replace-row", "mutate-membership"])
def test_explicit_read_transaction_and_concurrent_epoch(dataset, monkeypatch, mutation):
    path, result, provider = dataset
    original = provider.get_course_offerings(SEMESTER)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    reader_paused = threading.Event()
    writer_done = threading.Event()
    read_finished = threading.Event()
    states, reader_results, reader_errors, writer_errors = [], [], [], []
    real_open = store._open_store
    real_manifest_validation = store._require_manifest_trust_chain

    @contextmanager
    def instrumented_open(*args, **kwargs):
        with real_open(*args, **kwargs) as connection:
            def trace(sql):
                if "FROM course_data_acceptance " in sql and sql.lstrip().startswith("SELECT"):
                    states.append(connection.in_transaction)
            connection.set_trace_callback(trace)
            yield connection

    def pause_after_acceptance_read(*args, **kwargs):
        reader_paused.set()
        assert writer_done.wait(5), "writer did not commit/finish"
        return real_manifest_validation(*args, **kwargs)

    monkeypatch.setattr(store, "_open_store", instrumented_open)
    monkeypatch.setattr(store, "_require_manifest_trust_chain", pause_after_acceptance_read)

    def reader():
        try:
            reader_results.append(provider.get_course_offerings(SEMESTER))
        except BaseException as exc:
            reader_errors.append(exc)
        finally:
            read_finished.set()

    def writer():
        try:
            assert reader_paused.wait(5), "reader did not reach acceptance boundary"
            with sqlite3.connect(path, timeout=2) as connection:
                if mutation == "delete-acceptance":
                    connection.execute("DELETE FROM course_data_acceptance")
                elif mutation == "replace-row":
                    connection.execute("UPDATE course_offering SET course_name='Synthetic epoch B' WHERE course_id='REV-0'")
                else:
                    connection.execute("DELETE FROM course_data_acceptance_member WHERE course_id='REV-0'")
        except BaseException as exc:
            writer_errors.append(exc)
        finally:
            writer_done.set()

    threads = [threading.Thread(target=reader, daemon=True), threading.Thread(target=writer, daemon=True)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(8)
    assert read_finished.is_set() and all(not thread.is_alive() for thread in threads)
    assert not writer_errors, repr(writer_errors)
    # Outcome must be full epoch A or typed fail-closed. No substituted/mixed row is allowed.
    if reader_results:
        assert reader_results == [original]
    else:
        assert len(reader_errors) == 1 and isinstance(reader_errors[0], CourseDataAcceptanceError)
    assert states and all(states), (
        f"authoritative SELECT did not start in explicit transaction: states={states}; "
        f"outcome={'epoch A' if reader_results else 'fail closed'}; writer committed {mutation}")
