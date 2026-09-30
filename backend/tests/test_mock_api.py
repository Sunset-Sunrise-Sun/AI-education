"""Mock API 接口测试。

覆盖任务第 10 节的要求：

- 所有 Mock API 返回 200；
- 返回数据可被对应模型校验；
- CourseOffering 明确为 mock；
- Mock 数据不包含敏感信息（在 `test_mock_data_schema.py` 中覆盖，这里再验一次响应体）。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.mock import MOCK_DATA_SOURCE_HEADER, MOCK_DATA_SOURCE_VALUE
from app.models.contracts import (
    CourseOffering,
    DataSource,
    MakeupTask,
    PlanResult,
    Preference,
)

API = "/api/v1/mock"

#: 接口 -> 期望得到 200 的路径
ENDPOINTS = [
    f"{API}/makeup-tasks",
    f"{API}/course-offerings",
    f"{API}/preference",
    f"{API}/plan-result",
    f"{API}/demo",
]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_mock_endpoint_returns_200(client: TestClient, path: str) -> None:
    """任务要求：所有 Mock API 都必须返回 200。"""

    response = client.get(path)

    assert response.status_code == 200, f"{path} 返回 {response.status_code}：{response.text[:400]}"


@pytest.mark.parametrize("path", ENDPOINTS)
def test_mock_endpoint_marks_data_source(client: TestClient, path: str) -> None:
    """每个 Mock 响应都要带来源标记，且值为 mock。"""

    response = client.get(path)

    assert response.headers.get(MOCK_DATA_SOURCE_HEADER) == MOCK_DATA_SOURCE_VALUE


def test_mock_endpoints_are_under_version_prefix(client: TestClient) -> None:
    """任务要求：业务接口统一在 /api/v1 下，不能把接口堆在根路径。"""

    # 不带前缀的同名业务接口不应存在
    assert client.get("/mock/makeup-tasks").status_code == 404

    # 根路径只保留探针用的 /health
    assert client.get("/health").status_code == 200
    assert client.get("/course-offerings").status_code == 404


def test_makeup_tasks_returns_validated_list(client: TestClient) -> None:
    """返回数据必须能被 MakeupTask 模型逐条校验。"""

    payload = client.get(f"{API}/makeup-tasks").json()

    assert isinstance(payload, list)
    assert payload, "Mock 补修任务列表不应为空"

    tasks = [MakeupTask.model_validate(item) for item in payload]
    statuses = {task.status.value for task in tasks}

    assert "required" in statuses
    assert statuses & {"manual_confirmation", "possibly_equivalent"}


def test_course_offerings_returns_validated_list(client: TestClient) -> None:
    """返回数据必须能被 CourseOffering 模型逐条校验。"""

    payload = client.get(f"{API}/course-offerings").json()

    assert isinstance(payload, list)
    assert payload

    offerings = [CourseOffering.model_validate(item) for item in payload]

    by_course: dict[str, int] = {}
    for offering in offerings:
        by_course[offering.course_id] = by_course.get(offering.course_id, 0) + 1

    assert any(count >= 2 for count in by_course.values()), "应存在同一课程的多个教学班"


def test_course_offerings_are_explicitly_mock(client: TestClient) -> None:
    """任务要求：CourseOffering 必须明确为 mock。"""

    payload = client.get(f"{API}/course-offerings").json()

    for item in payload:
        assert item["data_source"] == "mock", f"教学班 {item['class_id']} 来源不是 mock"

    assert all(
        CourseOffering.model_validate(item).data_source is DataSource.MOCK for item in payload
    )


def test_preference_returns_valid_single_object(client: TestClient) -> None:
    payload = client.get(f"{API}/preference").json()

    preference = Preference.model_validate(payload)

    assert preference.max_credit is not None
    assert preference.avoid_times or preference.avoid_cross_campus


def test_plan_result_returns_valid_single_object(client: TestClient) -> None:
    payload = client.get(f"{API}/plan-result").json()

    result = PlanResult.model_validate(payload)

    assert result.status.value in {"feasible", "partially_feasible", "infeasible"}
    assert result.selected_classes


def test_plan_result_exposes_unresolved_items(client: TestClient) -> None:
    """验收关注点：系统必须诚实暴露「待人工确认」的部分，不能假装全部已定。"""

    payload = client.get(f"{API}/plan-result").json()

    assert payload["unresolved"], "PlanResult 应包含 unresolved 项"
    assert any("manual_confirmation" == item["type"] for item in payload["unresolved"])


def test_demo_returns_all_four_objects(client: TestClient) -> None:
    """聚合接口要一次给全四个公共对象，便于前端原型只调一个接口。"""

    payload = client.get(f"{API}/demo").json()

    assert set(payload) == {"makeup_tasks", "course_offerings", "preference", "plan_result"}
    assert isinstance(payload["makeup_tasks"], list)
    assert isinstance(payload["course_offerings"], list)
    Preference.model_validate(payload["preference"])
    PlanResult.model_validate(payload["plan_result"])


def test_demo_matches_individual_endpoints(client: TestClient) -> None:
    """聚合接口与四个单一接口必须返回同一份数据，避免两处数据不一致。"""

    demo = client.get(f"{API}/demo").json()

    assert demo["makeup_tasks"] == client.get(f"{API}/makeup-tasks").json()
    assert demo["course_offerings"] == client.get(f"{API}/course-offerings").json()
    assert demo["preference"] == client.get(f"{API}/preference").json()
    assert demo["plan_result"] == client.get(f"{API}/plan-result").json()


@pytest.mark.parametrize("path", ENDPOINTS)
def test_mock_response_contains_no_credentials(client: TestClient, path: str) -> None:
    """响应体不得包含密码 / Cookie / Token / API Key 等凭据痕迹。"""

    body = json.dumps(client.get(path).json(), ensure_ascii=False).lower()

    for marker in ("password", "cookie", "jsessionid", "api_key", "apikey", "bearer "):
        assert marker not in body, f"{path} 响应体出现疑似凭据内容：{marker!r}"


def test_openapi_documents_all_mock_endpoints(client: TestClient) -> None:
    """OpenAPI 文档必须收录全部接口，方便前端直接对接。"""

    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    for path in ENDPOINTS:
        assert path in paths, f"OpenAPI 未收录 {path}"

    assert "/health" in paths
