"""真实规划 API 的装配、隔离与失败语义测试。"""

from __future__ import annotations

import ast
import inspect
from contextlib import contextmanager
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import plan as plan_api
from app.api.mock import MOCK_DATA_SOURCE_HEADER, MOCK_DATA_SOURCE_VALUE
from app.integration import PlanningOrchestrator
from app.main import app
from app.models.contracts import CourseOffering, MakeupTask, PlanResult, Preference
from app.services import mock_service, planning_runtime
from app.services.planning_runtime import get_planning_orchestrator

PLAN_PATH = "/api/v1/plan"


def _offering(class_id: str, *, data_source: str = "real") -> CourseOffering:
    return CourseOffering(
        course_id="CSE101",
        course_name="程序设计",
        class_id=class_id,
        semester="2026-1",
        meetings=[
            {
                "weekday": 2,
                "start_section": 3,
                "end_section": 4,
                "weeks": [1, 2, 3],
                "campus": "东校区",
            }
        ],
        data_source=data_source,
    )


def _request_payload() -> dict[str, object]:
    return {
        "semester": "2026-1  ",
        "current_schedule": [
            _offering("CURRENT-01").model_dump(mode="json"),
        ],
        "preference": {
            "max_credit": 18,
            "avoid_cross_campus": True,
            "preferred_courses": ["CSE101"],
            "avoid_times": [
                {"weekday": 5, "start_section": 7, "end_section": 8},
            ],
            "notes": "保留原始偏好",
        },
    }


class RecordingCurriculumProvider:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.calls = 0
        self.tasks = [
            MakeupTask(
                course_id="CSE101",
                course_name="程序设计",
                credit=3,
                status="required",
            )
        ]

    def get_makeup_tasks(self) -> list[MakeupTask]:
        self.calls += 1
        self.log.append("curriculum")
        return self.tasks


class RecordingCourseDataProvider:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.semesters: list[str] = []
        self.offerings = [_offering("OFFERING-01")]

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        self.semesters.append(semester)
        self.log.append("course_data")
        return self.offerings


class RecordingPlannerProvider:
    def __init__(self, log: list[str], result: PlanResult) -> None:
        self.log = log
        self.result = result
        self.received: list[dict[str, object]] = []

    def plan(
        self,
        *,
        makeup_tasks: list[MakeupTask],
        offerings: list[CourseOffering],
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult:
        self.log.append("planner")
        self.received.append(
            {
                "makeup_tasks": makeup_tasks,
                "offerings": offerings,
                "current_schedule": current_schedule,
                "preference": preference,
            }
        )
        return self.result


class ProviderBoom(RuntimeError):
    pass


class ExplodingPlannerProvider:
    def plan(
        self,
        *,
        makeup_tasks: list[MakeupTask],
        offerings: list[CourseOffering],
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult:
        raise ProviderBoom("real planner failed")


@contextmanager
def _configured_client(orchestrator: PlanningOrchestrator) -> Iterator[TestClient]:
    app.dependency_overrides[get_planning_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_planning_orchestrator, None)


def _recording_orchestrator() -> tuple[
    PlanningOrchestrator,
    list[str],
    RecordingCurriculumProvider,
    RecordingCourseDataProvider,
    RecordingPlannerProvider,
    PlanResult,
]:
    log: list[str] = []
    result = PlanResult(
        status="partially_feasible",
        selected_classes=[{"course_id": "CSE101", "class_id": "OFFERING-01"}],
        changes=[],
        risks=[{"course_id": "CSE101", "level": "medium", "reason": "原样风险"}],
        unresolved=[{"type": "selection_required", "message": "原样待处理项"}],
        objective_summary="Planner 原始摘要",
    )
    curriculum = RecordingCurriculumProvider(log)
    course_data = RecordingCourseDataProvider(log)
    planner = RecordingPlannerProvider(log, result)
    orchestrator = PlanningOrchestrator(
        curriculum=curriculum,
        course_data=course_data,
        planner=planner,
    )
    return orchestrator, log, curriculum, course_data, planner, result


def test_plan_endpoint_exists(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"][PLAN_PATH]

    assert "post" in operation
    assert operation["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/PlanResult")


def test_unconfigured_runtime_returns_503_without_mock_plan(client: TestClient) -> None:
    response = client.post(PLAN_PATH, json=_request_payload())

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
    assert "selected_classes" not in response.json()
    assert "plan_result" not in response.json()
    assert MOCK_DATA_SOURCE_HEADER not in response.headers


def test_mock_demo_remains_separate_and_marked(client: TestClient) -> None:
    response = client.get("/api/v1/mock/demo")

    assert response.status_code == 200
    assert response.headers[MOCK_DATA_SOURCE_HEADER] == MOCK_DATA_SOURCE_VALUE
    assert "plan_result" in response.json()


def test_broken_mock_data_does_not_block_health_or_real_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock 损坏只影响 Mock endpoint，不得阻断应用启动或真实规划链路。"""

    def broken_makeup_tasks() -> list[MakeupTask]:
        raise mock_service.MockDataError("测试注入：Mock 数据损坏")

    monkeypatch.setattr(mock_service, "load_makeup_tasks", broken_makeup_tasks)
    orchestrator, log, _curriculum, _course_data, _planner, result = (
        _recording_orchestrator()
    )

    with _configured_client(orchestrator) as client:
        health_response = client.get("/health")
        plan_response = client.post(PLAN_PATH, json=_request_payload())
        mock_response = client.get("/api/v1/mock/demo")

    assert health_response.status_code == 200
    assert plan_response.status_code == 200
    assert plan_response.json() == result.model_dump(mode="json")
    assert log == ["curriculum", "course_data", "planner"]
    assert MOCK_DATA_SOURCE_HEADER not in plan_response.headers

    assert mock_response.status_code == 500
    assert mock_response.json()["detail"]["error"] == "mock_data_invalid"
    assert "Mock 数据损坏" in mock_response.json()["detail"]["message"]
    assert mock_response.headers[MOCK_DATA_SOURCE_HEADER] == MOCK_DATA_SOURCE_VALUE


def test_configured_pipeline_calls_each_provider_once_and_preserves_data() -> None:
    orchestrator, log, curriculum, course_data, planner, result = _recording_orchestrator()
    payload = _request_payload()

    with _configured_client(orchestrator) as client:
        response = client.post(PLAN_PATH, json=payload)

    assert response.status_code == 200
    assert MOCK_DATA_SOURCE_HEADER not in response.headers
    assert log == ["curriculum", "course_data", "planner"]
    assert curriculum.calls == 1
    assert course_data.semesters == [payload["semester"]]
    assert len(planner.received) == 1

    received = planner.received[0]
    assert received["makeup_tasks"] is curriculum.tasks
    assert received["offerings"] is course_data.offerings
    assert [item.model_dump(mode="json") for item in received["current_schedule"]] == payload[
        "current_schedule"
    ]
    assert received["preference"].model_dump(mode="json") == payload["preference"]
    assert response.json() == result.model_dump(mode="json")


@pytest.mark.parametrize(
    "current_schedule",
    [
        pytest.param([], id="empty"),
        pytest.param(
            [
                _offering("REAL-01").model_dump(mode="json"),
                _offering("REAL-02").model_dump(mode="json"),
            ],
            id="all-real",
        ),
    ],
)
def test_real_plan_accepts_empty_or_all_real_current_schedule(
    current_schedule: list[dict[str, object]],
) -> None:
    orchestrator, log, _curriculum, _course_data, planner, _result = (
        _recording_orchestrator()
    )
    payload = _request_payload()
    payload["current_schedule"] = current_schedule

    with _configured_client(orchestrator) as client:
        response = client.post(PLAN_PATH, json=payload)

    assert response.status_code == 200
    assert log == ["curriculum", "course_data", "planner"]
    assert [
        item.model_dump(mode="json") for item in planner.received[0]["current_schedule"]
    ] == current_schedule


@pytest.mark.parametrize(
    "current_schedule",
    [
        pytest.param(
            [
                _offering("REAL-ALONGSIDE-MOCK").model_dump(mode="json"),
                _offering("MOCK-01", data_source="mock").model_dump(mode="json"),
            ],
            id="any-explicit-mock",
        ),
        pytest.param(
            [
                _offering("DEFAULTS-TO-MOCK")
                .model_dump(mode="json", exclude={"data_source"})
            ],
            id="missing-data-source",
        ),
    ],
)
def test_real_plan_rejects_mock_or_missing_current_schedule_source(
    current_schedule: list[dict[str, object]],
) -> None:
    orchestrator, log, _curriculum, _course_data, _planner, _result = (
        _recording_orchestrator()
    )
    payload = _request_payload()
    payload["current_schedule"] = current_schedule

    with _configured_client(orchestrator) as client:
        response = client.post(PLAN_PATH, json=payload)

    assert response.status_code == 422
    assert log == []
    assert "data_source 必须为 real" in response.text


def test_provider_error_propagates_without_mock_fallback() -> None:
    log: list[str] = []
    curriculum = RecordingCurriculumProvider(log)
    course_data = RecordingCourseDataProvider(log)
    orchestrator = PlanningOrchestrator(
        curriculum=curriculum,
        course_data=course_data,
        planner=ExplodingPlannerProvider(),
    )

    with _configured_client(orchestrator) as client:
        with pytest.raises(ProviderBoom, match="real planner failed"):
            client.post(PLAN_PATH, json=_request_payload())

    assert log == ["curriculum", "course_data"]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("semester", ""),
        ("semester", "   "),
        ("student_id", "SHOULD-NOT-BE-ACCEPTED"),
        ("preference", {"max_credit": -1}),
        (
            "current_schedule",
            [
                {
                    "course_id": "CSE101",
                    "course_name": "程序设计",
                    "class_id": "BROKEN-01",
                    "semester": "2026-1",
                    "meetings": [
                        {
                            "weekday": 9,
                            "start_section": 1,
                            "end_section": 2,
                            "weeks": [1],
                        }
                    ],
                    "data_source": "real",
                }
            ],
        ),
    ],
)
def test_malformed_request_returns_422(
    client: TestClient, field: str, bad_value: object
) -> None:
    payload = _request_payload()
    payload[field] = bad_value

    response = client.post(PLAN_PATH, json=payload)

    assert response.status_code == 422
    assert MOCK_DATA_SOURCE_HEADER not in response.headers


def test_real_api_and_runtime_do_not_import_mock_replay() -> None:
    for module in (plan_api, planning_runtime):
        tree = ast.parse(inspect.getsource(module))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }

        assert "app.services.mock_service" not in imports
        assert "app.api.mock" not in imports
