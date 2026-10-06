"""Run with the 13c5556 Builder archive on PYTHONPATH. Diagnostic, not gate approval."""
import sqlite3

import pytest

from app.course_data.store_provider import StoreBackedCourseDataProvider, CourseDataAcceptanceError
from test_store_probes import SEMESTER, put


def provider(path, digest):
    return StoreBackedCourseDataProvider(sqlite_path=path, semester=SEMESTER,
                                        acceptance_sha256=digest)


def test_stale_campus_rows_excluded_and_later_overwrite_rejected(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    put(path, "campus", ["stale"])
    digest = put(path, "D", ["accepted"], "full_semester", SEMESTER)
    bound = provider(path, digest)
    assert [r.course_id for r in bound.get_course_offerings(SEMESTER)] == ["accepted"]
    put(path, "later-campus", ["accepted"])
    with pytest.raises(CourseDataAcceptanceError):
        bound.get_course_offerings(SEMESTER)


def test_same_count_identity_substitution_is_accepted(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    digest = put(path, "D", ["accepted"], "full_semester", SEMESTER)
    bound = provider(path, digest)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE course_offering SET course_id='substituted'")
    assert [r.course_id for r in bound.get_course_offerings(SEMESTER)] == ["substituted"]
    assert provider(path, digest).get_course_offerings(SEMESTER)[0].course_id == "substituted"


def test_valid_payload_mutation_preserving_provenance_is_accepted(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    digest = put(path, "D", ["accepted"], "full_semester", SEMESTER)
    bound = provider(path, digest)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE course_offering SET course_name='synthetic changed'")
    assert bound.get_course_offerings(SEMESTER)[0].course_name == "synthetic changed"


def test_declared_full_campus_snapshot_passes_provider(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    digest = put(path, "campus-only", ["campus-only"], "full_semester", SEMESTER)
    assert provider(path, digest).get_course_offerings(SEMESTER)[0].course_id == "campus-only"


def test_deleted_acceptance_record_is_not_rechecked_on_request(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    digest = put(path, "D", ["accepted"], "full_semester", SEMESTER)
    bound = provider(path, digest)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM course_data_import")
    assert bound.get_course_offerings(SEMESTER)[0].course_id == "accepted"
    with pytest.raises(CourseDataAcceptanceError):
        provider(path, digest)
