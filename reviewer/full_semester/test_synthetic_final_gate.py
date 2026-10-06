"""Independent HTTP assertions on synthetic production wiring, no dependency overrides."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import planning_runtime, mock_service
from app.planner import RestrictedPlannerProvider
from app.models.contracts import CourseOffering, Preference


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    root = Path(planning_runtime.__file__).parents[2]
    spec = importlib.util.spec_from_file_location('builder_synthetic_inputs', root / 'tests/test_synthetic_production_e2e.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path, digest = module._configured(monkeypatch, tmp_path)
    assert not app.dependency_overrides
    return module, path, digest


def mock_guard(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Mock planning fallback invoked')
    for name in ('load_makeup_tasks', 'load_course_offerings', 'load_preference', 'load_plan_result'):
        monkeypatch.setattr(mock_service, name, forbidden)


def test_exact_inputs_unknown_and_manual_confirmation(synthetic, monkeypatch):
    module, path, digest = synthetic
    request = module._frontend_request(current_schedule=[module._current_offering('SYN-UNKNOWN', 'south-000', meetings=[])])
    seen = []
    original = RestrictedPlannerProvider.plan
    def observe(self, **kwargs):
        seen.append(kwargs)
        return original(self, **kwargs)
    monkeypatch.setattr(RestrictedPlannerProvider, 'plan', observe)
    with TestClient(app) as client:
        mock_guard(monkeypatch)
        response = client.post('/api/v1/plan', json=request)
    assert response.status_code == 200
    assert len(seen) == 1
    assert seen[0]['current_schedule'] == [CourseOffering.model_validate(row) for row in request['current_schedule']]
    assert seen[0]['preference'] == Preference.model_validate(request['preference'])
    unknown = [row for row in seen[0]['offerings'] if row.course_id == 'SYN-UNKNOWN']
    assert unknown and all(row.meetings == [] for row in unknown)
    payload = response.json()
    kinds = {row['type'] for row in payload['unresolved']}
    assert {'schedule_unknown', 'manual_confirmation'} <= kinds
    assert payload['status'] == 'partially_feasible'
    assert all(row['course_id'] != 'SYN-AMBIGUOUS' for row in payload['selected_classes'])
    assert any(row['course_id'] == 'SYN-UNKNOWN' for row in payload['selected_classes'])


@pytest.mark.parametrize('mutation', ['missing', 'wrong-sha', 'campus', 'manifest', 'row', 'member', 'revoke-after-construction'])
def test_independent_synthetic_http_refusals(synthetic, tmp_path, monkeypatch, mutation):
    module, path, digest = synthetic
    with TestClient(app) as client:
        mock_guard(monkeypatch)
        assert client.post('/api/v1/plan', json=module._frontend_request()).status_code == 200
        if mutation == 'wrong-sha':
            monkeypatch.setenv('APP_COURSE_DATA_ACCEPTANCE_SHA256', 'f' * 64)
        elif mutation == 'campus':
            monkeypatch.setenv('APP_COURSE_DATA_SQLITE_PATH', str(module._campus_only_store(tmp_path)))
        elif mutation == 'revoke-after-construction':
            original = planning_runtime.build_planning_runtime
            def revoke(environment):
                inspection = original(environment)
                assert inspection.orchestrator is not None
                with sqlite3.connect(path) as db:
                    db.execute('DELETE FROM course_data_acceptance')
                return inspection
            monkeypatch.setattr(planning_runtime, 'build_planning_runtime', revoke)
        else:
            with sqlite3.connect(path) as db:
                if mutation == 'missing':
                    db.execute('DELETE FROM course_data_acceptance')
                elif mutation == 'row':
                    db.execute("UPDATE course_offering SET course_name='Independent payload tamper'")
                elif mutation == 'member':
                    db.execute('DELETE FROM course_data_acceptance_member')
                else:
                    manifest = json.loads(db.execute('SELECT canonical_manifest_json FROM course_data_acceptance').fetchone()[0])
                    manifest['inventory_sha256'] = 'e' * 64
                    db.execute('UPDATE course_data_acceptance SET canonical_manifest_json=?', (json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')),))
        response = client.post('/api/v1/plan', json=module._frontend_request())
        assert response.status_code == 503
        assert response.json()['detail']['error'] == 'real_pipeline_not_configured'


def test_stale_row_never_reaches_planner(synthetic, monkeypatch):
    module, path, digest = synthetic
    with sqlite3.connect(path) as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info(course_offering)')]
        values = list(db.execute('SELECT * FROM course_offering LIMIT 1').fetchone())
        values[columns.index('course_id')] = 'INDEPENDENT-STALE'
        values[columns.index('artifact_sha256')] = 'a' * 64
        values[columns.index('scope_kind')] = 'campus'
        values[columns.index('scope_id')] = '5063559'
        db.execute('INSERT INTO course_offering VALUES (' + ','.join('?' for _ in values) + ')', values)
    captured = []
    original = RestrictedPlannerProvider.plan
    def observe(self, **kwargs):
        captured.extend(kwargs['offerings'])
        return original(self, **kwargs)
    monkeypatch.setattr(RestrictedPlannerProvider, 'plan', observe)
    with TestClient(app) as client:
        mock_guard(monkeypatch)
        response = client.post('/api/v1/plan', json=module._frontend_request())
    assert response.status_code == 200
    assert len(captured) == 5
    assert all(row.course_id != 'INDEPENDENT-STALE' for row in captured)


def test_same_sha_changed_dataset_refused_and_original_http_rows_preserved(synthetic, monkeypatch):
    from app.course_data import OfferingSnapshot, SnapshotScope, import_offering_snapshot
    from app.course_data.store import CourseDataStoreError
    module, path, digest = synthetic
    orchestrator = planning_runtime.get_planning_orchestrator()
    original_rows = orchestrator.course_data.get_course_offerings(module.SEMESTER)
    with sqlite3.connect(path) as db:
        manifest = json.loads(db.execute('SELECT canonical_manifest_json FROM course_data_acceptance').fetchone()[0])
    changed = original_rows[0].model_copy(update={'course_name': 'Independent same-SHA Dataset B'})
    rows_b = [changed, *original_rows[1:]]
    assert len(rows_b) == len(original_rows)
    assert [(r.course_id, r.class_id) for r in rows_b] == [(r.course_id, r.class_id) for r in original_rows]
    with pytest.raises(CourseDataStoreError):
        import_offering_snapshot(path, OfferingSnapshot(module.SEMESTER, tuple(rows_b), 'complete', len(rows_b)),
                                artifact_sha256=digest, scope=SnapshotScope('full_semester', module.SEMESTER),
                                canonical_manifest=manifest)
    observed = []
    original = RestrictedPlannerProvider.plan
    def observe(self, **kwargs):
        observed.append(kwargs['offerings'])
        return original(self, **kwargs)
    monkeypatch.setattr(RestrictedPlannerProvider, 'plan', observe)
    with TestClient(app) as client:
        mock_guard(monkeypatch)
        response = client.post('/api/v1/plan', json=module._frontend_request())
    assert response.status_code == 200  # B rejected; intact A remains available.
    assert observed == [original_rows]
