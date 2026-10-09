"""AI Planning 私有路由测试（**全部 Mock**，⛔ 不调用真实 DeepSeek）。

覆盖任务书要求的接口行为：

- `GET /status` 如实报告"是否真的可能在线调用"；
- 默认关闭时 `interpret` 明确 503，⛔ 不回退到任何演示模型；
- 正常意图 → 确认 → 求解 → 二次确认采用，全程走 HTTP；
- 未确认不求解、指纹过期 410、重复采用 409、未知 id 404；
- 请求体不接受身份字段（`extra="forbid"`）；
- 会话隔离：不同 process-local store 之间不串。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.ai_planning import (
    AiPlanningConfig,
    AiPlanningService,
    RuleFakeIntentModel,
    SessionStore,
    UnavailableIntentModel,
)
from app.main import app
from app.planner import RestrictedPlannerProvider
from app.services.ai_planning_runtime import get_ai_planning_service
from tests.ai_planning_fixtures import (
    ALGO_COURSE,
    DS_CLASS,
    DS_COURSE,
    NET_COURSE,
    base_plan,
    confirm_payload,
    context_payload,
)

STATUS_PATH = "/api/v1/ai-planning/status"
INTERPRET_PATH = "/api/v1/ai-planning/interpret"
SOLVE_PATH = "/api/v1/ai-planning/solve"
ADOPT_PATH = "/api/v1/ai-planning/adopt"


def config(*, enabled: bool = True, api_key: str | None = None) -> AiPlanningConfig:
    return AiPlanningConfig(
        enabled=enabled, api_key=api_key, base_url="https://api.deepseek.com",
        model="deepseek-flash", max_output_tokens=1200, request_timeout=5.0,
        max_calls_per_request=3, max_sessions=10, adopt_ttl_seconds=300,
    )


def rule_model() -> RuleFakeIntentModel:
    selected = {item.course_id: item.class_id for item in base_plan().selected_classes}
    return RuleFakeIntentModel(
        known_course_ids=(DS_COURSE, ALGO_COURSE, NET_COURSE),
        known_class_by_course={
            course_id: selected.get(course_id, f"{course_id.lower()}-01")
            for course_id in (DS_COURSE, ALGO_COURSE, NET_COURSE)
        },
        # 模拟"真实模型能认出课程中文名"；⛔ 与业务认定无关，只属于测试替身。
        course_aliases={"数据结构": DS_COURSE, "算法": ALGO_COURSE, "网络": NET_COURSE},
    )


def install_service(*, model=None, cfg: AiPlanningConfig | None = None) -> AiPlanningService:
    service = AiPlanningService(
        config=cfg or config(),
        intent_model=model if model is not None else rule_model(),
        planner=RestrictedPlannerProvider(),
        sessions=SessionStore(max_sessions=10),
    )
    app.dependency_overrides[get_ai_planning_service] = lambda: service
    return service


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_ai_planning_service, None)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #

def test_status_reports_disabled_by_default(client: TestClient):
    install_service(cfg=config(enabled=False))
    body = client.get(STATUS_PATH).json()
    assert body["enabled"] is False
    assert body["live_model_available"] is False
    assert body["api_key_configured"] is False
    assert body["generator_kind_when_live"] == "deepseek_live"
    # ⛔ 响应里不含任何密钥字段
    assert "api_key" not in body


def test_status_reports_key_presence_without_exposing_the_key(client: TestClient):
    install_service(cfg=config(api_key="placeholder-not-a-real-key"))
    body = client.get(STATUS_PATH).json()
    assert body["api_key_configured"] is True
    assert body["live_model_available"] is True
    import json as _json

    assert "placeholder-not-a-real-key" not in _json.dumps(body, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# 默认关闭
# --------------------------------------------------------------------------- #

def test_interpret_is_503_when_disabled(client: TestClient):
    install_service(cfg=config(enabled=False))
    response = client.post(
        INTERPRET_PATH,
        json={"context": context_payload(max_credit=24.0), "user_message": "少上点课"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "ai_planning_disabled"


def test_solve_and_adopt_are_503_when_disabled(client: TestClient):
    install_service(cfg=config(enabled=False))
    solve = client.post(SOLVE_PATH, json={
        "intent_id": "intent_abcdefgh", "plan_digest": "0" * 64, "confirmed_intent": {},
    })
    adopt = client.post(ADOPT_PATH, json={
        "candidate_id": "candidate_abcdefgh", "plan_digest": "0" * 64, "accept": True,
    })
    assert solve.status_code == 503 and adopt.status_code == 503


# --------------------------------------------------------------------------- #
# 正常链路
# --------------------------------------------------------------------------- #

def test_interpret_returns_a_draft_and_never_solves(client: TestClient):
    install_service()
    response = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0),
        "user_message": "这学期太累，数据结构必须保留，尽量别在周五上课",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generator_kind"] == "test_double"        # ⛔ 绝不是 deepseek_live
    assert "测试替身" in body["generator_note"]
    assert body["can_confirm"] is True
    assert body["state"] == "intent_draft"
    assert body["data_source"] == "mock"
    assert body["parsed_intent"]["scope"] == "current_semester"
    assert body["ambiguities"] == []
    # 只读：响应里没有任何候选方案字段
    assert "candidate_plan" not in body
    assert body["parsed_intent"]["locked_courses"][0]["course_id"] == DS_COURSE


def test_full_flow_through_http_requires_two_confirmations(client: TestClient):
    install_service()
    interpret = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0),
        "user_message": "尽量别在周五上课",
    }).json()

    solve_response = client.post(SOLVE_PATH, json={
        "intent_id": interpret["intent_id"],
        "plan_digest": interpret["plan_digest"],
        "confirmed_intent": confirm_payload(
            plan_digest=interpret["plan_digest"], weekday=5
        ),
    })
    assert solve_response.status_code == 200, solve_response.text
    solved = solve_response.json()
    assert solved["status"] == "candidate_ready"
    assert solved["plan_kind"] == "PlanResult"
    assert solved["candidate_plan"]["status"] in {"feasible", "partially_feasible"}
    assert solved["diff"]["added"]
    assert solved["blocked_reason"] is None

    adopt_response = client.post(ADOPT_PATH, json={
        "candidate_id": solved["candidate_id"],
        "plan_digest": solved["plan_digest"],
        "accept": True,
    })
    assert adopt_response.status_code == 200, adopt_response.text
    adopted = adopt_response.json()
    assert adopted["accepted"] is True
    assert adopted["state"] == "adopted"
    assert adopted["adopted_version"] == 1
    assert adopted["adopted_version_scope"] == "process_local_session"
    assert adopted["original_plan_unchanged"] is False


def test_rejecting_keeps_the_original_plan(client: TestClient):
    install_service()
    interpret = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0),
        "user_message": "尽量别在周五上课",
    }).json()
    solved = client.post(SOLVE_PATH, json={
        "intent_id": interpret["intent_id"],
        "plan_digest": interpret["plan_digest"],
        "confirmed_intent": confirm_payload(
            plan_digest=interpret["plan_digest"], weekday=5
        ),
    }).json()
    body = client.post(ADOPT_PATH, json={
        "candidate_id": solved["candidate_id"],
        "plan_digest": solved["plan_digest"],
        "accept": False,
    }).json()
    assert body["accepted"] is False
    assert body["state"] == "rejected"
    assert body["adopted_version"] == 0
    assert body["original_plan_unchanged"] is True


# --------------------------------------------------------------------------- #
# 错误路径
# --------------------------------------------------------------------------- #

def test_unconfirmed_intent_is_rejected_with_422(client: TestClient):
    install_service()
    interpret = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0),
        "user_message": "尽量别在周五上课",
    }).json()
    response = client.post(SOLVE_PATH, json={
        "intent_id": interpret["intent_id"],
        "plan_digest": interpret["plan_digest"],
        "confirmed_intent": {"plan_digest": interpret["plan_digest"]},
    })
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "ai_planning_intent_invalid"


def test_ambiguous_intent_returns_409(client: TestClient):
    """上下文没有声明学分上限、意图也没有给出数字 ⇒ 必须留待用户填写。"""

    install_service()
    interpret = client.post(INTERPRET_PATH, json={
        "context": context_payload(),          # 刻意不声明学分上限
        "user_message": "这学期太累，少上一点课就行",
    }).json()
    assert interpret["can_confirm"] is False
    codes = {item["code"] for item in interpret["ambiguities"]}
    assert "credit_limit_missing_evidence" in codes

    response = client.post(SOLVE_PATH, json={
        "intent_id": interpret["intent_id"],
        "plan_digest": interpret["plan_digest"],
        "confirmed_intent": confirm_payload(plan_digest=interpret["plan_digest"]),
    })
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "ai_planning_intent_not_confirmable"


def test_stale_plan_digest_returns_410(client: TestClient):
    install_service()
    interpret = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0),
        "user_message": "尽量别在周五上课",
    }).json()
    response = client.post(SOLVE_PATH, json={
        "intent_id": interpret["intent_id"],
        "plan_digest": "f" * 64,
        "confirmed_intent": confirm_payload(plan_digest="f" * 64, weekday=5),
    })
    assert response.status_code == 410
    assert response.json()["detail"]["error"] == "ai_planning_session_expired"


def test_unknown_intent_id_returns_404(client: TestClient):
    install_service()
    response = client.post(SOLVE_PATH, json={
        "intent_id": "intent_deadbeefdeadbeef",
        "plan_digest": "a" * 64,
        "confirmed_intent": confirm_payload(plan_digest="a" * 64),
    })
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ai_planning_session_not_found"


def test_duplicate_adoption_returns_409(client: TestClient):
    install_service()
    interpret = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0),
        "user_message": "尽量别在周五上课",
    }).json()
    solved = client.post(SOLVE_PATH, json={
        "intent_id": interpret["intent_id"],
        "plan_digest": interpret["plan_digest"],
        "confirmed_intent": confirm_payload(
            plan_digest=interpret["plan_digest"], weekday=5
        ),
    }).json()
    first = client.post(ADOPT_PATH, json={
        "candidate_id": solved["candidate_id"],
        "plan_digest": solved["plan_digest"], "accept": True,
    })
    assert first.status_code == 200
    second = client.post(ADOPT_PATH, json={
        "candidate_id": solved["candidate_id"],
        "plan_digest": solved["plan_digest"], "accept": True,
    })
    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "ai_planning_adoption_conflict"


def test_unknown_candidate_returns_404(client: TestClient):
    install_service()
    response = client.post(ADOPT_PATH, json={
        "candidate_id": "candidate_deadbeefdeadbeef",
        "plan_digest": "a" * 64, "accept": True,
    })
    assert response.status_code == 404


def test_model_unavailable_returns_503(client: TestClient):
    install_service(model=UnavailableIntentModel(reason="missing_api_key"))
    response = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0), "user_message": "尽量别在周五上课",
    })
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "ai_planning_model_unavailable"
    assert "missing_api_key" in response.json()["detail"]["message"]


def test_personal_information_in_message_returns_400(client: TestClient):
    install_service()
    response = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0),
        "user_message": "我的学号是 2025123456，帮我少上点课",
    })
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "ai_planning_message_rejected"


def test_inconsistent_semester_in_offerings_returns_422(client: TestClient):
    install_service()
    payload = context_payload(max_credit=24.0)
    payload["course_offerings"][0]["semester"] = "2026-2"
    response = client.post(INTERPRET_PATH, json={
        "context": payload, "user_message": "尽量别在周五上课",
    })
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "ai_planning_plan_context_invalid"


# --------------------------------------------------------------------------- #
# 请求边界
# --------------------------------------------------------------------------- #

def test_identity_fields_are_rejected_by_the_contract(client: TestClient):
    install_service()
    payload = {"context": context_payload(max_credit=24.0), "user_message": "少上点课"}
    payload["student_name"] = "示例姓名"
    assert client.post(INTERPRET_PATH, json=payload).status_code == 422
    context_with_identity = context_payload(max_credit=24.0)
    context_with_identity["student_id"] = "2025123456"
    assert client.post(INTERPRET_PATH, json={
        "context": context_with_identity, "user_message": "少上点课",
    }).status_code == 422


def test_empty_message_is_rejected(client: TestClient):
    install_service()
    response = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0), "user_message": "",
    })
    assert response.status_code == 422      # pydantic min_length


def test_oversized_message_is_rejected_at_the_service_boundary(client: TestClient):
    install_service()
    response = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0), "user_message": "课" * 2000,
    })
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "ai_planning_message_rejected"


def test_bad_plan_digest_length_is_a_contract_error(client: TestClient):
    install_service()
    response = client.post(SOLVE_PATH, json={
        "intent_id": "intent_abcdefgh", "plan_digest": "short", "confirmed_intent": {},
    })
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# 路由与隔离
# --------------------------------------------------------------------------- #

def test_existing_routes_are_untouched(client: TestClient):
    paths = set(client.get("/openapi.json").json()["paths"])
    # 旧路由一个都不能消失
    for existing in (
        "/api/v1/plan",
        "/api/v1/mock/demo",
        "/api/v1/personal-planning/plan",
        "/api/v1/personal-planning/curriculum-versions",
        "/api/v1/explanation/plan",
        "/api/v1/completed-courses/import",
    ):
        assert existing in paths
    # 新路由都在私有前缀下
    for new in (STATUS_PATH, INTERPRET_PATH, SOLVE_PATH, ADOPT_PATH):
        assert new in paths


def test_sessions_are_isolated_between_service_instances(client: TestClient):
    install_service()
    interpret = client.post(INTERPRET_PATH, json={
        "context": context_payload(max_credit=24.0), "user_message": "尽量别在周五上课",
    }).json()
    # 换一个全新会话存储（模拟进程内另一个实例 / 重新装配）
    install_service()
    response = client.post(SOLVE_PATH, json={
        "intent_id": interpret["intent_id"],
        "plan_digest": interpret["plan_digest"],
        "confirmed_intent": confirm_payload(
            plan_digest=interpret["plan_digest"], weekday=5
        ),
    })
    assert response.status_code == 404
