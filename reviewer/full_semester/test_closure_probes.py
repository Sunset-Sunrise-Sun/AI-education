"""Independent closure probes for Builder d097f51 (not collected by backend defaults).

Run with the selected Builder archive/backend on PYTHONPATH. Synthetic input only.
Tests named diagnostic_* reproduce a remaining BLOCK; passing is not gate PASS.
"""
import copy
import hashlib
import importlib.util
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.course_data.full_semester_acceptance as acceptance_module
import app.course_data.store as store
from app.course_data import (
    ShardArtifact, SnapshotScope, OfferingSnapshot, accept_full_semester_capture_set,
    build_capture_inventory, campus_source_label, collect_captured_pages_snapshot,
    import_offering_snapshot, load_capture_bundle_bytes,
)
from app.course_data.offering_digest import offering_set_sha256
from app.course_data.store_provider import StoreBackedCourseDataProvider, CourseDataAcceptanceError
from app.models.contracts import CourseOffering

SEMESTER = "2026-1"
SHARDS = (
    ("east-campus", "5063559"), ("south-campus", "5062201"),
    ("shenzhen-campus", "333291143"), ("zhuhai-campus", "5062203"),
    ("north-campus", "5062202"),
)


def bundle(index):
    return {"format": "sysu-opening-courses-capture-v1", "semester": SEMESTER,
            "first_page_no": 1, "page_size": 200,
            "pages": [{"page_no": 1, "response": {"code": 200, "data": {
                "total": 1, "rows": [{"courseNum": f"REV-{index}", "courseName": "Synthetic A",
                                      "classNumber": "01", "yearTerm": SEMESTER,
                                      "score": "3", "limitNumber": 20, "selectedNumber": 5}]}}}]}


@pytest.fixture
def inputs(tmp_path):
    paths, digests = {}, {}
    campus = tmp_path / "campus.sqlite"
    for index, (shard, number) in enumerate(SHARDS):
        raw = json.dumps(bundle(index), sort_keys=True, separators=(",", ":")).encode()
        path = tmp_path / f"{shard}.json"
        path.write_bytes(raw)
        paths[shard] = path
        digests[shard] = hashlib.sha256(raw).hexdigest()
        snapshot = collect_captured_pages_snapshot(load_capture_bundle_bytes(raw),
                                                  source=campus_source_label(SEMESTER, number))
        import_offering_snapshot(campus, snapshot, artifact_sha256=digests[shard],
                                scope=SnapshotScope("campus", number))
    return {"paths": paths, "digests": digests, "campus": campus,
            "inventory": build_capture_inventory(SEMESTER, digests)}


def accept(inputs, **overrides):
    kwargs = dict(expected_semester=SEMESTER, baseline_before=5, baseline_after=5,
                  shard_artifacts=[ShardArtifact(shard, inputs["paths"][shard]) for shard, _ in SHARDS],
                  inventory=inputs["inventory"], campus_store_path=inputs["campus"])
    kwargs.update(overrides)
    return accept_full_semester_capture_set(**kwargs)


@pytest.fixture
def accepted(inputs, tmp_path):
    result = accept(inputs)
    path = tmp_path / "accepted.sqlite"
    import_offering_snapshot(path, result.merged, artifact_sha256=result.manifest_sha256,
                            scope=result.scope)
    provider = StoreBackedCourseDataProvider(sqlite_path=path, semester=SEMESTER,
                                            acceptance_sha256=result.manifest_sha256)
    return path, result, provider


def mutate(path, sql, parameters=()):
    with sqlite3.connect(path) as connection:
        connection.execute(sql, parameters)


def test_exact_byte_single_source_aba_is_closed(inputs, monkeypatch):
    east = inputs["paths"][SHARDS[0][0]]
    raw_a = east.read_bytes()
    altered = json.loads(raw_a)
    altered["pages"][0]["response"]["data"]["rows"][0]["courseName"] = "Synthetic B"
    raw_b = json.dumps(altered).encode()
    original = acceptance_module.load_capture_bundle_bytes
    parsed = []

    def path_changes_while_parser_runs(raw):
        if raw != raw_a:
            return original(raw)
        east.write_bytes(raw_b)
        try:
            parsed.append(raw)
            return original(raw)
        finally:
            east.write_bytes(raw_a)

    monkeypatch.setattr(acceptance_module, "load_capture_bundle_bytes", path_changes_while_parser_runs)
    result = accept(inputs)
    assert parsed == [raw_a]
    assert result.merged.offerings[0].course_name == "Synthetic A"
    assert result.shards[0].raw_bundle_sha256 == hashlib.sha256(parsed[0]).hexdigest()


@pytest.mark.parametrize("case", ["swap", "reuse", "wrong-scope", "wrong-digest", "missing-record"])
def test_independent_campus_binding_closed(inputs, case):
    east, south = SHARDS[0][0], SHARDS[1][0]
    if case == "swap":
        inputs["paths"][east], inputs["paths"][south] = inputs["paths"][south], inputs["paths"][east]
    elif case == "reuse":
        inputs["paths"][south] = inputs["paths"][east]
    elif case == "wrong-scope":
        mutate(inputs["campus"], "UPDATE course_data_acceptance SET scope_id='wrong' WHERE artifact_sha256=?",
               (inputs["digests"][east],))
    elif case == "wrong-digest":
        mutate(inputs["campus"], "UPDATE course_data_acceptance SET artifact_sha256=? WHERE artifact_sha256=?",
               ("0" * 64, inputs["digests"][east]))
    else:
        mutate(inputs["campus"], "DELETE FROM course_data_acceptance WHERE artifact_sha256=?",
               (inputs["digests"][east],))
    with pytest.raises(acceptance_module.FullSemesterAcceptanceError):
        accept(inputs)


PAYLOAD_CHANGES = [
    ("course_name", "Synthetic changed"), ("teacher", "Synthetic teacher"),
    ("credit", 4.0), ("capacity", 21), ("remaining_capacity", 3),
    ("meetings_json", '[{"weekday":1,"start_section":1,"end_section":2,"weeks":[1]}]'),
    ("source", "synthetic://changed"), ("course_id", "REV-SUBSTITUTED"),
]


@pytest.mark.parametrize("column,value", PAYLOAD_CHANGES)
def test_direct_payload_substitution_closed(accepted, column, value):
    path, result, provider = accepted
    first = provider.get_course_offerings(SEMESTER)
    mutated = first[0].model_copy(update={"course_name": "changed"})
    assert offering_set_sha256(first) != offering_set_sha256([mutated, *first[1:]])
    mutate(path, f"UPDATE course_offering SET {column}=? WHERE course_id='REV-0'", (value,))
    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


CONTINUOUS_MUTATIONS = [
    "DELETE FROM course_data_acceptance",
    "DELETE FROM course_data_import",
    "UPDATE course_data_acceptance SET artifact_sha256='" + "0" * 64 + "'",
    "UPDATE course_data_acceptance SET scope_kind='campus'",
    "UPDATE course_data_acceptance SET offering_set_sha256='" + "0" * 64 + "'",
    "DELETE FROM course_data_acceptance_member WHERE course_id='REV-0'",
    "UPDATE course_data_acceptance_member SET offering_payload_sha256='" + "0" * 64 + "'",
    "INSERT INTO course_data_acceptance_member SELECT artifact_sha256, semester, 'FAKE', class_id, "
    "offering_payload_sha256 FROM course_data_acceptance_member LIMIT 1",
    "DELETE FROM course_offering WHERE course_id='REV-0'",
]


@pytest.mark.parametrize("sql", CONTINUOUS_MUTATIONS)
def test_continuous_mutation_next_read_closed(accepted, sql):
    path, _, provider = accepted
    assert len(provider.get_course_offerings(SEMESTER)) == 5
    mutate(path, sql)
    with pytest.raises(CourseDataAcceptanceError):
        provider.get_course_offerings(SEMESTER)


def test_unaccepted_stale_row_excluded(accepted):
    path, result, provider = accepted
    stale = result.merged.offerings[0].model_copy(update={"course_id": "STALE"})
    import_offering_snapshot(path, OfferingSnapshot(SEMESTER, (stale,), "complete", 1),
                            artifact_sha256="a" * 64, scope=SnapshotScope("campus", SHARDS[0][1]))
    rows = provider.get_course_offerings(SEMESTER)
    assert [o.course_id for o in rows] == [f"REV-{i}" for i in range(5)]


def test_manifest_canonicalization_and_content_binding(inputs):
    result = accept(inputs)
    document = copy.deepcopy(dict(result.manifest))
    reordered = dict(reversed(list(document.items())))
    pretty = json.dumps(reordered, indent=4).encode()
    normalized = acceptance_module.validate_full_semester_manifest_bytes(pretty)
    assert acceptance_module.compute_manifest_sha256(normalized) == result.manifest_sha256
    document["merged_offering_set_sha256"] = "f" * 64
    assert acceptance_module.compute_manifest_sha256(document) != result.manifest_sha256


def changed_snapshot(result):
    original = list(result.merged.offerings)
    original[0] = original[0].model_copy(update={"course_name": "Synthetic replacement"})
    return OfferingSnapshot(SEMESTER, tuple(original), "complete", len(original))


def test_diagnostic_same_count_reimport_still_rebinds_approved_sha(accepted):
    path, result, provider = accepted
    changed = changed_snapshot(result)
    assert offering_set_sha256(changed.offerings) != result.manifest["merged_offering_set_sha256"]
    import_offering_snapshot(path, changed, artifact_sha256=result.manifest_sha256, scope=result.scope)
    # Remaining BLOCK: even the old constructed Provider accepts changed content under the old SHA.
    rows = provider.get_course_offerings(SEMESTER)
    assert rows[0].course_name == "Synthetic replacement"
    assert provider.acceptance_sha256 == result.manifest_sha256


def test_diagnostic_selects_have_no_snapshot_transaction(accepted, monkeypatch):
    path, result, _ = accepted
    original_open = store._open_store
    transaction_states = []
    deleted = []

    @contextmanager
    def traced_open(*args, **kwargs):
        with original_open(*args, **kwargs) as connection:
            def trace(sql):
                if "FROM course_data_import WHERE" in sql:
                    transaction_states.append(connection.in_transaction)
                    # First metadata SELECT already ended. A different connection can commit now.
                    mutate(path, "DELETE FROM course_data_acceptance")
                    deleted.append(True)
            connection.set_trace_callback(trace)
            yield connection

    monkeypatch.setattr(store, "_open_store", traced_open)
    rows = store.load_accepted_offerings(path, semester=SEMESTER,
                                        acceptance_sha256=result.manifest_sha256)
    assert transaction_states == [False] and deleted == [True]
    assert len(rows.offerings) == 5
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM course_data_acceptance").fetchone()[0] == 0


def load_builder_e2e_fixture_module():
    root = Path(acceptance_module.__file__).parents[2]
    spec = importlib.util.spec_from_file_location("closure_curriculum_fixture",
                                               root / "tests/test_synthetic_production_e2e.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_api(monkeypatch, tmp_path, accepted):
    from app.main import app
    path, result, _ = accepted
    # Reuse ONLY the synthetic Curriculum document payload, not Builder gate/test assertions.
    case = tmp_path / "synthetic-case.json"
    case.write_text(json.dumps(load_builder_e2e_fixture_module()._case_payload()))
    for key, value in {
        "APP_REAL_CASE_A_ENABLED": "1", "APP_CASE_A_CURRICULUM_CASE_PATH": str(case),
        "APP_COURSE_DATA_SQLITE_PATH": str(path), "APP_COURSE_DATA_SEMESTER": SEMESTER,
        "APP_COURSE_DATA_ACCEPTANCE_SHA256": result.manifest_sha256,
    }.items():
        monkeypatch.setenv(key, value)
    assert app.dependency_overrides == {}
    return app


REQUEST = {"semester": SEMESTER, "current_schedule": [], "preference": {}}


@pytest.mark.parametrize("sql", CONTINUOUS_MUTATIONS)
def test_real_api_mutation_readiness_503(accepted, monkeypatch, tmp_path, sql):
    app = configure_api(monkeypatch, tmp_path, accepted)
    with TestClient(app) as client:
        assert client.post("/api/v1/plan", json=REQUEST).status_code == 200
        mutate(accepted[0], sql)
        response = client.post("/api/v1/plan", json=REQUEST)
        assert response.status_code == 503
        assert response.json()["detail"]["error"] == "real_pipeline_not_configured"


def test_diagnostic_real_api_serves_reimported_content_under_old_sha(accepted, monkeypatch, tmp_path):
    app = configure_api(monkeypatch, tmp_path, accepted)
    path, result, _ = accepted
    with TestClient(app) as client:
        assert client.post("/api/v1/plan", json=REQUEST).status_code == 200
        import_offering_snapshot(path, changed_snapshot(result),
                                artifact_sha256=result.manifest_sha256, scope=result.scope)
        # Remaining runtime/E2E BLOCK: approved manifest has not changed but payload did.
        assert client.post("/api/v1/plan", json=REQUEST).status_code == 200


@pytest.mark.parametrize("case", ["missing-db", "wrong-sha", "wrong-config-semester", "wrong-request-semester"])
def test_independent_runtime_config_failures_503(accepted, monkeypatch, tmp_path, case):
    app = configure_api(monkeypatch, tmp_path, accepted)
    request = copy.deepcopy(REQUEST)
    if case == "missing-db":
        monkeypatch.setenv("APP_COURSE_DATA_SQLITE_PATH", str(tmp_path / "not-created.sqlite"))
    elif case == "wrong-sha":
        monkeypatch.setenv("APP_COURSE_DATA_ACCEPTANCE_SHA256", "0" * 64)
    elif case == "wrong-config-semester":
        monkeypatch.setenv("APP_COURSE_DATA_SEMESTER", "2026-2")
    else:
        request["semester"] = "2026-2"
    with TestClient(app) as client:
        response = client.post("/api/v1/plan", json=request)
        assert response.status_code == 503
        assert response.json()["detail"]["error"] == "real_pipeline_not_configured"


def test_exact_payload_and_request_passthrough_with_real_planner(accepted, monkeypatch, tmp_path):
    from app.planner import RestrictedPlannerProvider
    from app.services import mock_service
    app = configure_api(monkeypatch, tmp_path, accepted)
    expected = list(accepted[1].merged.offerings)
    original_plan = RestrictedPlannerProvider.plan
    calls = []

    def recording_plan(self, **kwargs):
        calls.append(kwargs)
        return original_plan(self, **kwargs)

    def forbidden_mock(*args, **kwargs):
        pytest.fail("production planning called the Mock offering loader")

    monkeypatch.setattr(RestrictedPlannerProvider, "plan", recording_plan)
    request = copy.deepcopy(REQUEST)
    current = CourseOffering(course_id="CURRENT", course_name="Synthetic current", class_id="01",
                             semester=SEMESTER, meetings=[], data_source="real",
                             source="synthetic://current")
    request["current_schedule"] = [current.model_dump(mode="json")]
    request["preference"] = {"max_credit": 12, "avoid_cross_campus": True,
                             "preferred_courses": ["REV-0"], "notes": "Synthetic preference",
                             "avoid_times": [{"weekday": 1, "start_section": 3, "end_section": 4}]}
    with TestClient(app) as client:
        # Startup documented Mock schema self-check is permitted. The planning call is not.
        for name in ("get_course_offerings", "load_course_offerings"):
            if hasattr(mock_service, name):
                monkeypatch.setattr(mock_service, name, forbidden_mock)
        response = client.post("/api/v1/plan", json=request)
    assert response.status_code == 200 and len(calls) == 1
    assert calls[0]["offerings"] == expected
    assert calls[0]["current_schedule"][0].model_dump(mode="json") == request["current_schedule"][0]
    assert calls[0]["preference"].model_dump(mode="json") == request["preference"]
    assert calls[0]["current_schedule"][0].meetings == []
    assert response.json()["status"] == "partially_feasible"
    assert any(item["type"] == "manual_confirmation" for item in response.json()["unresolved"])
