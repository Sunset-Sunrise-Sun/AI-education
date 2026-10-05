"""Case A production runtime wiring tests; all local artifacts are synthetic."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.course_data import SnapshotCourseDataProvider
from app.curriculum import CurriculumCaseProvider
from app.curriculum.case import DEMO_CASE_PATH
from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    CONFIRMED_SCOPE_DECISIONS,
)
from app.integration import PlanningOrchestrator
from app.main import app
from app.planner import RestrictedPlannerProvider
from app.services.planning_runtime import build_planning_runtime

PLAN_PATH = "/api/v1/plan"
_ENV_NAMES = (
    "APP_REAL_CASE_A_ENABLED",
    "APP_CASE_A_CURRICULUM_CASE_PATH",
    "APP_COURSE_SNAPSHOT_PATH",
    "APP_COURSE_SNAPSHOT_SOURCE",
    "APP_COURSE_SNAPSHOT_SHA256",
)


def _replace_mock_sources(value: object) -> object:
    if isinstance(value, str):
        return value.replace("mock://", "case-owner-confirmed://")
    if isinstance(value, list):
        return [_replace_mock_sources(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_mock_sources(item) for key, item in value.items()}
    return value


def _write_curriculum_case(tmp_path: Path, *, data_source: str = "real") -> Path:
    payload = _replace_mock_sources(
        json.loads(DEMO_CASE_PATH.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict)
    payload["data_source"] = data_source
    payload["old"]["version_id"] = "case-a-old"
    payload["new"]["version_id"] = CASE_TARGET_VERSION_ID
    payload["rules"]["target_version_id"] = CASE_TARGET_VERSION_ID
    for record in payload["new"]["course_records"]:
        record["recommended_term_text"] = "2025-1"
    payload["makeup_scope"] = {
        "target_version_id": CASE_TARGET_VERSION_ID,
        "as_of_term": AS_OF_TERM,
        "evidence": "case-owner-confirmed://runtime-test/scope",
    }
    payload["confirmed_scope_decisions"] = [
        {
            "target_version_id": row["target_version_id"],
            "target_source_record": row["target_source_record"],
            "target_course_id": row["target_course_id"],
            "decision": row["decision"],
            "evidence": row["evidence"],
        }
        for row in CONFIRMED_SCOPE_DECISIONS
    ]
    payload["new"]["course_records"].extend(
        {
            "course_id": row["target_course_id"],
            "course_name": f"Synthetic {row['target_course_id']}",
            "credit": 1,
            "requirement": "required",
            "source_record": row["target_source_record"],
            "prerequisites": [],
            "recommended_term_text": row["recommended_term_text"],
        }
        for row in CONFIRMED_SCOPE_DECISIONS
    )
    path = tmp_path / "case-a.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _row(
    class_id: str = "SYNTHETIC-CLASS-01",
    *,
    semester: str = "2026-1",
) -> dict[str, object]:
    return {
        "courseNum": "DEMO202",
        "courseName": "Synthetic Course",
        "classNumber": class_id,
        "yearTerm": semester,
        "score": "4",
        "limitNumber": 90,
        "selectedNumber": 20,
        "teachingTimePlaceStr": "1-8周/星期五/第5-6节/REDACTED/示例环节,",
    }


def _write_snapshot(
    tmp_path: Path,
    *,
    total: int = 1,
    rows: list[dict[str, object]] | None = None,
    semester: str = "2026-1",
) -> Path:
    payload = {
        "format": "sysu-opening-courses-capture-v1",
        "semester": semester,
        "first_page_no": 1,
        "page_size": 200,
        "pages": [
            {
                "page_no": 1,
                "response": {
                    "code": 200,
                    "data": {
                        "total": total,
                        "rows": (
                            rows if rows is not None else [_row(semester=semester)]
                        ),
                    },
                },
            }
        ],
    }
    path = tmp_path / "complete-capture.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _environment(
    case_path: Path,
    snapshot_path: Path,
    *,
    source: str = "case-owner-confirmed://runtime-test/course-data",
    include_digest: bool = True,
) -> dict[str, str]:
    environment = {
        "APP_REAL_CASE_A_ENABLED": "1",
        "APP_CASE_A_CURRICULUM_CASE_PATH": str(case_path),
        "APP_COURSE_SNAPSHOT_PATH": str(snapshot_path),
        "APP_COURSE_SNAPSHOT_SOURCE": source,
    }
    if include_digest:
        environment["APP_COURSE_SNAPSHOT_SHA256"] = hashlib.sha256(
            snapshot_path.read_bytes()
        ).hexdigest()
    return environment


def _configure_process_environment(monkeypatch, values: Mapping[str, str]) -> None:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_default_environment_has_no_real_runtime() -> None:
    result = build_planning_runtime({})

    assert result.orchestrator is None
    assert result.reason == "runtime_disabled"


def test_missing_curriculum_source_fails_closed_without_mock_fallback() -> None:
    result = build_planning_runtime({"APP_REAL_CASE_A_ENABLED": "1"})

    assert result.orchestrator is None
    assert result.reason == "curriculum_not_ready"


def test_missing_course_data_source_fails_closed(tmp_path: Path) -> None:
    result = build_planning_runtime(
        {
            "APP_REAL_CASE_A_ENABLED": "1",
            "APP_CASE_A_CURRICULUM_CASE_PATH": str(_write_curriculum_case(tmp_path)),
        }
    )

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_incomplete_course_data_cannot_enter_runtime(tmp_path: Path) -> None:
    case_path = _write_curriculum_case(tmp_path)
    snapshot_path = _write_snapshot(tmp_path, total=6892)

    result = build_planning_runtime(_environment(case_path, snapshot_path))

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_complete_snapshot_without_approved_digest_is_not_ready(tmp_path: Path) -> None:
    result = build_planning_runtime(
        _environment(
            _write_curriculum_case(tmp_path),
            _write_snapshot(tmp_path),
            source="real://looks-trusted-but-is-only-a-label",
            include_digest=False,
        )
    )

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_approved_digest_mismatch_is_not_ready(tmp_path: Path) -> None:
    environment = _environment(
        _write_curriculum_case(tmp_path),
        _write_snapshot(tmp_path),
    )
    environment["APP_COURSE_SNAPSHOT_SHA256"] = "0" * 64

    result = build_planning_runtime(environment)

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_missing_snapshot_artifact_is_not_ready(tmp_path: Path) -> None:
    snapshot_path = _write_snapshot(tmp_path)
    environment = _environment(_write_curriculum_case(tmp_path), snapshot_path)
    environment["APP_COURSE_SNAPSHOT_PATH"] = str(tmp_path / "does-not-exist.json")

    result = build_planning_runtime(environment)

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_mock_source_label_is_not_ready_even_with_exact_digest(tmp_path: Path) -> None:
    result = build_planning_runtime(
        _environment(
            _write_curriculum_case(tmp_path),
            _write_snapshot(tmp_path),
            source="mock://not-a-real-source-label",
        )
    )

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_synthetic_bundle_and_real_looking_source_need_exact_approval(
    tmp_path: Path,
) -> None:
    result = build_planning_runtime(
        _environment(
            _write_curriculum_case(tmp_path),
            _write_snapshot(tmp_path),
            source="real://synthetic-does-not-prove-provenance",
            include_digest=False,
        )
    )

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_malformed_runtime_input_fails_closed(tmp_path: Path) -> None:
    malformed = tmp_path / "case-a.json"
    malformed.write_text("{not-json", encoding="utf-8")

    result = build_planning_runtime(
        _environment(malformed, _write_snapshot(tmp_path))
    )

    assert result.orchestrator is None
    assert result.reason == "curriculum_not_ready"


def test_complete_snapshot_for_another_semester_fails_closed(tmp_path: Path) -> None:
    result = build_planning_runtime(
        _environment(
            _write_curriculum_case(tmp_path),
            _write_snapshot(tmp_path, semester="2026-2"),
        )
    )

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_empty_complete_snapshot_is_not_ready(tmp_path: Path) -> None:
    result = build_planning_runtime(
        _environment(
            _write_curriculum_case(tmp_path),
            _write_snapshot(tmp_path, total=0, rows=[]),
        )
    )

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_mock_labeled_curriculum_cannot_enter_runtime(tmp_path: Path) -> None:
    result = build_planning_runtime(
        _environment(
            _write_curriculum_case(tmp_path, data_source="mock"),
            _write_snapshot(tmp_path),
        )
    )

    assert result.orchestrator is None
    assert result.reason == "curriculum_not_ready"


def test_invalid_enable_flag_fails_closed() -> None:
    result = build_planning_runtime({"APP_REAL_CASE_A_ENABLED": "true"})

    assert result.orchestrator is None
    assert result.reason == "invalid_runtime_configuration"


@pytest.mark.parametrize("approved_digest", ["abc", "g" * 64, "0" * 63, "0" * 65])
def test_invalid_approved_digest_is_invalid_configuration(
    tmp_path: Path,
    approved_digest: str,
) -> None:
    environment = _environment(
        _write_curriculum_case(tmp_path),
        _write_snapshot(tmp_path),
    )
    environment["APP_COURSE_SNAPSHOT_SHA256"] = approved_digest

    result = build_planning_runtime(environment)

    assert result.orchestrator is None
    assert result.reason == "invalid_runtime_configuration"


def test_uppercase_exact_digest_is_accepted(tmp_path: Path) -> None:
    environment = _environment(
        _write_curriculum_case(tmp_path),
        _write_snapshot(tmp_path),
    )
    environment["APP_COURSE_SNAPSHOT_SHA256"] = environment[
        "APP_COURSE_SNAPSHOT_SHA256"
    ].upper()

    result = build_planning_runtime(environment)

    assert result.ready is True


def test_artifact_change_after_approval_is_not_ready(tmp_path: Path) -> None:
    snapshot_path = _write_snapshot(tmp_path)
    environment = _environment(_write_curriculum_case(tmp_path), snapshot_path)
    snapshot_path.write_bytes(snapshot_path.read_bytes() + b" ")

    result = build_planning_runtime(environment)

    assert result.orchestrator is None
    assert result.reason == "course_data_not_ready"


def test_all_valid_sources_build_only_real_provider_implementations(
    tmp_path: Path,
) -> None:
    result = build_planning_runtime(
        _environment(_write_curriculum_case(tmp_path), _write_snapshot(tmp_path))
    )

    assert result.ready is True
    assert result.reason == "ready"
    assert isinstance(result.orchestrator, PlanningOrchestrator)
    assert isinstance(result.orchestrator.curriculum, CurriculumCaseProvider)
    assert isinstance(result.orchestrator.course_data, SnapshotCourseDataProvider)
    assert result.orchestrator.course_data.snapshot.is_complete is True
    assert isinstance(result.orchestrator.planner, RestrictedPlannerProvider)
    for provider in (
        result.orchestrator.curriculum,
        result.orchestrator.course_data,
        result.orchestrator.planner,
    ):
        assert not any(
            token in type(provider).__name__.lower()
            for token in ("fake", "stub", "mock")
        )


def test_api_uses_production_factory_and_returns_real_plan_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    values = _environment(_write_curriculum_case(tmp_path), _write_snapshot(tmp_path))
    _configure_process_environment(monkeypatch, values)

    with TestClient(app) as client:
        response = client.post(
            PLAN_PATH,
            json={
                "semester": "2026-1",
                "current_schedule": [],
                "preference": {
                    "max_credit": None,
                    "avoid_cross_campus": False,
                    "preferred_courses": [],
                    "avoid_times": [],
                    "notes": None,
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] in {
        "feasible",
        "partially_feasible",
        "infeasible",
    }
    assert "X-Data-Source" not in response.headers


def test_api_stays_503_when_runtime_is_disabled(monkeypatch) -> None:
    _configure_process_environment(monkeypatch, {})

    with TestClient(app) as client:
        response = client.post(
            PLAN_PATH,
            json={
                "semester": "2026-1",
                "current_schedule": [],
                "preference": {
                    "max_credit": None,
                    "avoid_cross_campus": False,
                    "preferred_courses": [],
                    "avoid_times": [],
                    "notes": None,
                },
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
