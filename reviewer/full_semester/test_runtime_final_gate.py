"""Independent Runtime gate; execute only after the reviewed Provider gate passes."""
import copy
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.course_data import OfferingSnapshot, SnapshotScope, import_offering_snapshot
from app.course_data.store_provider import StoreBackedCourseDataProvider, CourseDataAcceptanceError
from app.planner import RestrictedPlannerProvider
from app.services import planning_runtime, mock_service

from test_closure_probes import inputs, SEMESTER
from test_focused_provider_gate import dataset


REQUEST = {"semester": SEMESTER, "current_schedule": [], "preference": {}}


@pytest.fixture
def runtime(dataset, tmp_path, monkeypatch):
    path, result, provider = dataset
    root = Path(planning_runtime.__file__).parents[2]
    spec = importlib.util.spec_from_file_location("runtime_curriculum_fixture",
                                               root / "tests/test_planning_runtime.py")
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    case = tmp_path / "synthetic-case.json"
    case.write_text(json.dumps(fixture_module._case_payload()), encoding="utf-8")
    for name, value in {
        "APP_REAL_CASE_A_ENABLED": "1", "APP_CASE_A_CURRICULUM_CASE_PATH": str(case),
        "APP_COURSE_DATA_SQLITE_PATH": str(path), "APP_COURSE_DATA_SEMESTER": SEMESTER,
        "APP_COURSE_DATA_ACCEPTANCE_SHA256": result.manifest_sha256,
    }.items():
        monkeypatch.setenv(name, value)
    assert app.dependency_overrides == {}
    return path, result, provider


def change(path, sql, params=()):
    with sqlite3.connect(path) as connection:
        connection.execute(sql, params)


def guard_mock(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("production runtime called a Mock planning loader")
    for name in ("load_makeup_tasks", "load_course_offerings", "load_preference", "load_plan_result"):
        monkeypatch.setattr(mock_service, name, forbidden)


@pytest.mark.parametrize("case", [
    "missing-acceptance", "wrong-sha", "campus-only", "deleted-acceptance", "tampered-manifest",
    "tampered-membership", "tampered-row",
])
def test_actual_runtime_readiness_refusal(runtime, tmp_path, monkeypatch, case):
    path, result, _ = runtime
    with TestClient(app) as client:
        guard_mock(monkeypatch)
        assert client.post("/api/v1/plan", json=REQUEST).status_code == 200
        if case in ("missing-acceptance", "deleted-acceptance"):
            change(path, "DELETE FROM course_data_acceptance")
        elif case == "wrong-sha":
            monkeypatch.setenv("APP_COURSE_DATA_ACCEPTANCE_SHA256", "0" * 64)
        elif case == "campus-only":
            campus_path = tmp_path / "campus-only.sqlite"
            import_offering_snapshot(campus_path, result.merged, artifact_sha256="a" * 64,
                                    scope=SnapshotScope("campus", "5063559"))
            monkeypatch.setenv("APP_COURSE_DATA_SQLITE_PATH", str(campus_path))
            monkeypatch.setenv("APP_COURSE_DATA_ACCEPTANCE_SHA256", "a" * 64)
        elif case == "tampered-manifest":
            document = copy.deepcopy(dict(result.manifest))
            document["baseline_after"] = 6
            change(path, "UPDATE course_data_acceptance SET canonical_manifest_json=?",
                   (json.dumps(document, sort_keys=True, separators=(",", ":")),))
        elif case == "tampered-membership":
            change(path, "DELETE FROM course_data_acceptance_member WHERE course_id='REV-0'")
        else:
            change(path, "UPDATE course_offering SET course_name='Synthetic tampered' WHERE course_id='REV-0'")
        response = client.post("/api/v1/plan", json=REQUEST)
        assert response.status_code == 503
        assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
        assert "x-data-source" not in response.headers


def test_stale_nonmember_never_reaches_real_planner(runtime, monkeypatch):
    path, result, _ = runtime
    stale = result.merged.offerings[0].model_copy(update={"course_id": "STALE-NONMEMBER"})
    import_offering_snapshot(path, OfferingSnapshot(SEMESTER, (stale,), "complete", 1),
                            artifact_sha256="a" * 64, scope=SnapshotScope("campus", "5063559"))
    recorded = []
    original = RestrictedPlannerProvider.plan
    def spy(self, **kwargs):
        recorded.append(kwargs["offerings"])
        return original(self, **kwargs)
    monkeypatch.setattr(RestrictedPlannerProvider, "plan", spy)
    with TestClient(app) as client:
        guard_mock(monkeypatch)
        assert client.post("/api/v1/plan", json=REQUEST).status_code == 200
    assert recorded == [list(result.merged.offerings)]


def test_request_time_acceptance_error_maps_to_503(runtime, monkeypatch):
    def fail_on_request(self, semester):
        raise CourseDataAcceptanceError("synthetic request-time revocation")
    monkeypatch.setattr(StoreBackedCourseDataProvider, "get_course_offerings", fail_on_request)
    with TestClient(app) as client:
        response = client.post("/api/v1/plan", json=REQUEST)
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"


@pytest.mark.parametrize("error_type", [RuntimeError, TypeError, ValueError, KeyError, AttributeError, OSError])
@pytest.mark.parametrize("stage", ["construction", "curriculum-construction", "planner-construction", "request", "planner-request", "orchestrator-request"])
def test_unrelated_internal_error_is_not_swallowed_as_readiness(runtime, monkeypatch, error_type, stage):
    def internal_bug(*args, **kwargs):
        raise error_type("synthetic unrelated programming defect")
    if stage == "construction":
        monkeypatch.setattr(planning_runtime, "build_course_data_provider", internal_bug)
    elif stage == "curriculum-construction":
        monkeypatch.setattr(planning_runtime, "build_curriculum_provider", internal_bug)
    elif stage == "planner-construction":
        monkeypatch.setattr(planning_runtime, "build_planner_provider", internal_bug)
    elif stage == "orchestrator-request":
        monkeypatch.setattr(planning_runtime.PlanningOrchestrator, "build_plan", internal_bug)
    elif stage == "planner-request":
        monkeypatch.setattr(RestrictedPlannerProvider, "plan", internal_bug)
    else:
        monkeypatch.setattr(StoreBackedCourseDataProvider, "get_course_offerings", internal_bug)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/plan", json=REQUEST)
    assert response.status_code == 500, (
        f"{stage} {error_type.__name__} incorrectly classified as {response.status_code}: {response.text}")


@pytest.mark.parametrize("case", ["missing-db", "invalid-sha", "disabled", "missing-config", "construction-acceptance"])
def test_explicit_domain_and_config_readiness(runtime, tmp_path, monkeypatch, case):
    if case == "missing-db":
        monkeypatch.setenv("APP_COURSE_DATA_SQLITE_PATH", str(tmp_path / "absent.sqlite"))
    elif case == "invalid-sha":
        monkeypatch.setenv("APP_COURSE_DATA_ACCEPTANCE_SHA256", "invalid")
    elif case == "disabled":
        monkeypatch.setenv("APP_REAL_CASE_A_ENABLED", "0")
    elif case == "missing-config":
        monkeypatch.delenv("APP_COURSE_DATA_SEMESTER")
    else:
        def domain_failure(*args, **kwargs):
            raise CourseDataAcceptanceError("explicit construction acceptance refusal")
        monkeypatch.setattr(planning_runtime, "build_course_data_provider", domain_failure)
    with TestClient(app) as client:
        guard_mock(monkeypatch)
        response = client.post("/api/v1/plan", json=REQUEST)
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"


def test_constructed_orchestrator_request_time_revocation(runtime, monkeypatch):
    path, _, _ = runtime
    original = planning_runtime.build_planning_runtime
    def construct_then_revoke(environment):
        inspection = original(environment)
        assert inspection.orchestrator is not None
        change(path, "DELETE FROM course_data_acceptance")
        return inspection
    monkeypatch.setattr(planning_runtime, "build_planning_runtime", construct_then_revoke)
    with TestClient(app) as client:
        guard_mock(monkeypatch)
        response = client.post("/api/v1/plan", json=REQUEST)
    assert response.status_code == 503
