"""健康检查接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    """/health 必须返回 200。"""

    response = client.get("/health")

    assert response.status_code == 200


def test_health_payload_status_is_ok(client: TestClient) -> None:
    """/health 的 status 字段必须是 "ok"。"""

    payload = client.get("/health").json()

    assert payload["status"] == "ok"


def test_health_declares_mock_data_source(client: TestClient) -> None:
    """健康检查要暴露当前数据来源，避免使用者误以为已经接入真实数据。"""

    payload = client.get("/health").json()

    assert payload["data_source"] == "mock"


def test_health_available_under_api_prefix(client: TestClient) -> None:
    """带版本前缀的 /api/v1/health 同样可用。"""

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_response_is_json(client: TestClient) -> None:
    """响应必须是 JSON，便于部署探针直接解析。"""

    response = client.get("/health")

    assert response.headers["content-type"].startswith("application/json")


def test_health_rejects_wrong_method(client: TestClient) -> None:
    """主要失败路径：用非 GET 方法访问 /health 不应被当作成功。"""

    response = client.post("/health")

    assert response.status_code == 405
