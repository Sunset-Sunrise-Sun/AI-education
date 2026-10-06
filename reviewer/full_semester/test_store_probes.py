"""Synthetic diagnostic probes: passing means the documented hazard is reproduced."""
import hashlib
import sqlite3

from app.course_data.snapshot import OfferingSnapshot
from app.course_data.store import (
    SnapshotScope, import_offering_snapshot, load_course_offerings,
    load_course_data_provenance,
)
from app.models.contracts import CourseOffering

SEMESTER = "2026-1"


def offering(identity):
    return CourseOffering(course_id=identity, course_name="synthetic",
                          class_id="01", semester=SEMESTER, meetings=[],
                          source="synthetic://review-only", data_source="real")


def put(path, artifact, identities, kind="campus", scope="5063559"):
    rows = tuple(offering(identity) for identity in identities)
    digest = hashlib.sha256(artifact.encode()).hexdigest()
    import_offering_snapshot(path, OfferingSnapshot(SEMESTER, rows, "complete", len(rows)),
                            artifact_sha256=digest,
                            scope=SnapshotScope(kind, scope))
    return digest


def test_full_import_leaves_old_campus_rows(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    put(path, "A", ["east-current", "east-obsolete"])
    put(path, "B", ["south-current"], scope="5062201")
    put(path, "C", ["east-old-extra"])
    digest = put(path, "D", ["east-current", "south-current", "accepted-new"],
                 "full_semester", SEMESTER)
    assert {row.course_id for row in load_course_offerings(path, SEMESTER)} == {
        "east-current", "south-current", "accepted-new", "east-obsolete", "east-old-extra"}
    with sqlite3.connect(path) as connection:
        accepted = connection.execute(
            "SELECT course_id FROM course_offering WHERE artifact_sha256=? "
            "AND scope_kind='full_semester' AND scope_id=?", (digest, SEMESTER)).fetchall()
    assert {row[0] for row in accepted} == {"east-current", "south-current", "accepted-new"}


def test_later_campus_import_removes_accepted_membership_but_not_record(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    digest = put(path, "D", ["accepted-a", "accepted-b"], "full_semester", SEMESTER)
    put(path, "E", ["accepted-a"])
    records = [r for r in load_course_data_provenance(path) if r.artifact_sha256 == digest]
    assert len(records) == 1 and records[0].offering_count == 2
    with sqlite3.connect(path) as connection:
        count = connection.execute("SELECT count(*) FROM course_offering WHERE artifact_sha256=?",
                                   (digest,)).fetchone()[0]
    assert count == 1


def test_scope_declaration_alone_can_relabel_a_campus_snapshot(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    digest = put(path, "campus-only", ["campus-row"], "full_semester", SEMESTER)
    record = load_course_data_provenance(path)[0]
    assert record.artifact_sha256 == digest and record.scope_kind == "full_semester"
    # Store is a declaration sink, not the acceptance trust boundary.
