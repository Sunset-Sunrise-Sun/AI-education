"""真实 HTTP E2E：启动 FastAPI（uvicorn）并用**真实 HTTP 请求**跑通 AI 规划闭环。

## 这个文件与既有 API 测试的区别

`tests/test_ai_planning_api.py` 用 `TestClient`（进程内 ASGI 直调）。
本文件**真的监听一个端口**，用 `httpx` 发真实 HTTP 请求，验证：

```text
GET  /api/v1/ai-planning/status      → 可用状态（⛔ 不含密钥）
POST /api/v1/ai-planning/interpret   → 意图草稿（只读）
POST /api/v1/ai-planning/solve       → 确认后的候选 + 确定性差异
POST /api/v1/ai-planning/adopt       → 二次确认采用 / 拒绝
```

## 模型来源（如实标注）

本环境**没有** `DEEPSEEK_API_KEY`，因此通过 `app.dependency_overrides` 注入
**测试替身模型**（`RuleFakeIntentModel`）。响应里的 `generator_kind` 因此是
`test_double` —— ⛔ 本文件**不**证明真实 DeepSeek 在线调用，
真实在线验证仍是 **NOT VERIFIED**（需运行方注入新密钥）。

## 数据来源（如实标注）

上下文中的教学班全部是人工构造的合成对象（`data_source="mock"`），
⛔ 不包含任何真实学生隐私数据，也⛔ 不代表真实教务开课。
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Iterator

import pytest
import uvicorn

from app.ai_planning import (
    AiPlanningConfig,
    AiPlanningService,
    RuleFakeIntentModel,
    ScriptedIntentModel,
    SessionStore,
    UnavailableIntentModel,
)
from app.main import app
from app.planner import RestrictedPlannerProvider
from app.services.ai_planning_runtime import get_ai_planning_service
from tests.ai_planning_fixtures import (
    ALGO_ALT_CLASS,
    ALGO_CLASS,
    ALGO_COURSE,
    DS_ALT_CLASS,
    DS_CLASS,
    DS_COURSE,
    NET_CLASS,
    NET_COURSE,
    SEMESTER,
    base_plan,
    confirm_payload,
    context_payload,
    offerings,
)

STATUS_PATH = "/api/v1/ai-planning/status"
INTERPRET_PATH = "/api/v1/ai-planning/interpret"
SOLVE_PATH = "/api/v1/ai-planning/solve"
ADOPT_PATH = "/api/v1/ai-planning/adopt"


# --------------------------------------------------------------------------- #
# 服务装配与真实 HTTP 服务器
# --------------------------------------------------------------------------- #

def make_config(*, enabled: bool = True, ttl: int = 900) -> AiPlanningConfig:
    return AiPlanningConfig(
        enabled=enabled, api_key=None, base_url="https://api.deepseek.com",
        model="deepseek-flash", max_output_tokens=1200, request_timeout=5.0,
        max_calls_per_request=3, max_sessions=50, adopt_ttl_seconds=ttl,
    )


def rule_model() -> RuleFakeIntentModel:
    selected = {item.course_id: item.class_id for item in base_plan().selected_classes}
    return RuleFakeIntentModel(
        known_course_ids=(DS_COURSE, ALGO_COURSE, NET_COURSE),
        known_class_by_course={
            course_id: selected.get(course_id, f"{course_id.lower()}-01")
            for course_id in (DS_COURSE, ALGO_COURSE, NET_COURSE)
        },
        course_aliases={"数据结构": DS_COURSE, "算法": ALGO_COURSE, "网络": NET_COURSE},
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LiveServer:
    """真实监听端口的 uvicorn 服务器（用于真实 HTTP 请求）。"""

    def __init__(self, service: AiPlanningService) -> None:
        self._service = service
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def install_service(self, service: AiPlanningService) -> None:
        """替换依赖（服务器已启动时同样生效，因为 override 是查表）。"""

        self._service = service
        app.dependency_overrides[get_ai_planning_service] = lambda: self._service

    def __enter__(self) -> "LiveServer":
        app.dependency_overrides[get_ai_planning_service] = lambda: self._service
        port = _free_port()
        self.base_url = f"http://127.0.0.1:{port}"
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if self._server.started:
                break
            time.sleep(0.05)
        else:  # pragma: no cover - 启动失败属于环境问题
            raise RuntimeError("uvicorn 未能在 20 秒内启动")
        return self

    def __exit__(self, *args) -> None:
        app.dependency_overrides.pop(get_ai_planning_service, None)
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=20.0)


def http_json(
    base_url: str, method: str, path: str, body: dict | None = None
) -> tuple[int, dict]:
    """发一次真实 HTTP 请求，返回 (状态码, 解析后的 JSON)。"""

    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url=f"{base_url}{path}", data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except ValueError:  # pragma: no cover - 非 JSON 错误体
            payload = {"raw": raw}
        return exc.code, payload


@contextlib.contextmanager
def live_server(service: AiPlanningService) -> Iterator[LiveServer]:
    with LiveServer(service) as server:
        yield server


def service_with(model=None, *, cfg: AiPlanningConfig | None = None) -> AiPlanningService:
    return AiPlanningService(
        config=cfg or make_config(),
        intent_model=model if model is not None else rule_model(),
        planner=RestrictedPlannerProvider(),
        sessions=SessionStore(max_sessions=50),
    )


# --------------------------------------------------------------------------- #
# 1. status
# --------------------------------------------------------------------------- #

def test_status_over_real_http_reports_test_double_without_exposing_a_key():
    with live_server(service_with()) as server:
        status, payload = http_json(server.base_url, "GET", STATUS_PATH)

    assert status == 200
    assert payload["enabled"] is True
    assert payload["live_model_available"] is False      # 本环境没有密钥
    assert payload["api_key_configured"] is False
    assert payload["generator_kind_when_live"] == "deepseek_live"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "sk-" not in serialized
    assert "api_key" not in payload


def test_status_reports_disabled_when_switch_is_off():
    with live_server(service_with(cfg=make_config(enabled=False))) as server:
        status, payload = http_json(server.base_url, "GET", STATUS_PATH)
        disabled_status, disabled_body = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context_payload(max_credit=24.0), "user_message": "少上点课"},
        )

    assert status == 200 and payload["enabled"] is False
    assert disabled_status == 503
    assert disabled_body["detail"]["error"] == "ai_planning_disabled"


# --------------------------------------------------------------------------- #
# 2. 两次确认的完整闭环（真实 HTTP）
# --------------------------------------------------------------------------- #

def _interpret(server: LiveServer, message: str, *, max_credit: float | None = 24.0) -> dict:
    status, payload = http_json(server.base_url, "POST", INTERPRET_PATH, {
        "context": context_payload(max_credit=max_credit),
        "user_message": message,
    })
    assert status == 200, payload
    return payload


def test_full_two_confirmation_flow_over_real_http():
    with live_server(service_with()) as server:
        # ---- 第一次确认之前：只解析，不求解 ----
        draft = _interpret(server, "这学期太累，数据结构必须保留，尽量别在周五上课")
        assert draft["generator_kind"] == "test_double"
        assert draft["data_source"] == "mock"
        assert draft["can_confirm"] is True
        assert draft["state"] == "intent_draft"
        assert len(draft["plan_digest"]) == 64
        assert "candidate_plan" not in draft
        assert draft["parsed_intent"]["locked_courses"][0]["course_id"] == DS_COURSE
        assert draft["parsed_intent"]["locked_courses"][0]["reason"]

        # ---- 未确认直接求解 → 必须被拒绝，且不改方案 ----
        unconfirmed_status, unconfirmed = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"],
            "plan_digest": draft["plan_digest"],
            "confirmed_intent": {"plan_digest": draft["plan_digest"]},
        })
        assert unconfirmed_status == 422
        assert unconfirmed["detail"]["error"] == "ai_planning_intent_invalid"

        # ---- 第一次确认：求解 ----
        solve_status, solved = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"],
            "plan_digest": draft["plan_digest"],
            "confirmed_intent": confirm_payload(
                plan_digest=draft["plan_digest"], locked=True, weekday=5
            ),
        })
        assert solve_status == 200, solved
        assert solved["status"] == "candidate_ready"
        assert solved["plan_kind"] == "PlanResult"
        assert solved["candidate_id"]
        assert solved["blocked_reason"] is None
        assert solved["generator_kind"] == "test_double"
        assert solved["data_source"] == "mock"

        added = {(row["course_id"], row["class_id"]) for row in solved["diff"]["added"]}
        kept = {(row["course_id"], row["class_id"]) for row in solved["diff"]["kept"]}
        assert (ALGO_COURSE, ALGO_ALT_CLASS) in added      # 唯一 CLEAR 新增
        assert (ALGO_COURSE, ALGO_CLASS) not in added      # 与已选班冲突，未被自动加入
        assert (DS_COURSE, DS_CLASS) in kept               # 锁定课程被保留
        assert solved["diff"]["empty"] is False
        assert isinstance(solved["diff"]["credit_delta"], (int, float))
        # 候选方案来自 Planner，且锁定课程仍在其中
        selected = {
            (row["course_id"], row["class_id"])
            for row in solved["candidate_plan"]["selected_classes"]
        }
        assert (DS_COURSE, DS_CLASS) in selected

        # ---- 第二次确认：采用 ----
        adopt_status, adopted = http_json(server.base_url, "POST", ADOPT_PATH, {
            "candidate_id": solved["candidate_id"],
            "plan_digest": solved["plan_digest"],
            "accept": True,
        })
        assert adopt_status == 200, adopted
        assert adopted["accepted"] is True
        assert adopted["state"] == "adopted"
        assert adopted["adopted_version"] == 1
        assert adopted["adopted_version_scope"] == "process_local_session"
        assert adopted["original_plan_unchanged"] is False
        # ⛔ adopt 不返回方案体：方案体只能来自 /solve 的候选
        assert "adopted_plan" not in adopted
        assert "candidate_plan" not in adopted

        # ---- 重复采用 → 冲突 ----
        repeat_status, repeat = http_json(server.base_url, "POST", ADOPT_PATH, {
            "candidate_id": solved["candidate_id"],
            "plan_digest": solved["plan_digest"],
            "accept": True,
        })
        assert repeat_status == 409
        assert repeat["detail"]["error"] == "ai_planning_adoption_conflict"


def test_rejecting_a_candidate_over_real_http_keeps_the_original_plan():
    with live_server(service_with()) as server:
        draft = _interpret(server, "尽量别在周五上课")
        _, solved = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"], "plan_digest": draft["plan_digest"],
            "confirmed_intent": confirm_payload(
                plan_digest=draft["plan_digest"], weekday=5
            ),
        })
        assert solved["status"] == "candidate_ready"

        adopt_status, adopted = http_json(server.base_url, "POST", ADOPT_PATH, {
            "candidate_id": solved["candidate_id"],
            "plan_digest": solved["plan_digest"],
            "accept": False,
        })
        assert adopt_status == 200
        assert adopted["accepted"] is False
        assert adopted["state"] == "rejected"
        assert adopted["adopted_version"] == 0
        assert adopted["original_plan_unchanged"] is True

        # 拒绝后再次采用必须被拒（状态冲突），原方案不变
        again_status, again = http_json(server.base_url, "POST", ADOPT_PATH, {
            "candidate_id": solved["candidate_id"],
            "plan_digest": solved["plan_digest"],
            "accept": True,
        })
        assert again_status == 409
        assert again["detail"]["error"] == "ai_planning_adoption_conflict"


# --------------------------------------------------------------------------- #
# 3. 歧义 / 过期 / 模型不可用 / 无供给
# --------------------------------------------------------------------------- #

def test_ambiguous_intent_cannot_be_solved_over_real_http():
    with live_server(service_with()) as server:
        # 上下文**没有**声明学分上限，消息也没有给出数字 ⇒ 必须留待用户填写
        draft = _interpret(server, "这学期太累，少上一点课就行", max_credit=None)
        assert draft["can_confirm"] is False
        codes = {item["code"] for item in draft["ambiguities"]}
        assert "credit_limit_missing_evidence" in codes

        solve_status, solved = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"], "plan_digest": draft["plan_digest"],
            "confirmed_intent": confirm_payload(plan_digest=draft["plan_digest"]),
        })
        assert solve_status == 409
        assert solved["detail"]["error"] == "ai_planning_intent_not_confirmable"


def test_stale_plan_digest_is_rejected_over_real_http():
    with live_server(service_with()) as server:
        draft = _interpret(server, "尽量别在周五上课")
        status, payload = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"], "plan_digest": "f" * 64,
            "confirmed_intent": confirm_payload(plan_digest="f" * 64, weekday=5),
        })
        assert status == 410
        assert payload["detail"]["error"] == "ai_planning_session_expired"


def test_candidate_expiry_is_rejected_over_real_http():
    """TTL 到期后采用必须失败，且原方案不变。"""

    with live_server(service_with(cfg=make_config(ttl=1))) as server:
        draft = _interpret(server, "尽量别在周五上课")
        _, solved = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"], "plan_digest": draft["plan_digest"],
            "confirmed_intent": confirm_payload(
                plan_digest=draft["plan_digest"], weekday=5
            ),
        })
        assert solved["status"] == "candidate_ready"
        time.sleep(1.6)          # 超过 1 秒 TTL
        status, payload = http_json(server.base_url, "POST", ADOPT_PATH, {
            "candidate_id": solved["candidate_id"],
            "plan_digest": solved["plan_digest"], "accept": True,
        })
        assert status == 410
        assert payload["detail"]["error"] == "ai_planning_session_expired"
        assert "有效期" in payload["detail"]["message"]


def test_unavailable_model_is_reported_over_real_http():
    with live_server(service_with(UnavailableIntentModel(reason="missing_api_key"))) as server:
        status, payload = http_json(server.base_url, "POST", INTERPRET_PATH, {
            "context": context_payload(max_credit=24.0), "user_message": "尽量别在周五上课",
        })
        assert status == 503
        assert payload["detail"]["error"] == "ai_planning_model_unavailable"
        assert "missing_api_key" in payload["detail"]["message"]


def test_no_selected_classes_still_reports_no_feasible_candidate():
    """没有教学班供给时：⛔ 不凭空补班次，缺口如实暴露。"""

    with live_server(service_with()) as server:
        status, payload = http_json(server.base_url, "POST", INTERPRET_PATH, {
            "context": context_payload(include_offerings=False, max_credit=24.0),
            "user_message": "尽量别在周五上课",
        })
        assert status == 200
        assert payload["data_source"] == "unknown"     # ⛔ 不默认成 real
        draft = payload
        _, solved = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"], "plan_digest": draft["plan_digest"],
            "confirmed_intent": confirm_payload(
                plan_digest=draft["plan_digest"], weekday=5
            ),
        })
        assert solved["status"] in {"candidate_ready", "no_feasible_candidate"}
        if solved["status"] == "candidate_ready":
            # 只有在候选引用了本次输入里真实的班次时才算合法候选
            assert solved["candidate_plan"] is not None
        assert any("没有候选教学班" in message for message in solved["unresolved"])


# --------------------------------------------------------------------------- #
# 4. 前端契约一致性（真实后端响应必须能被前端解析器接受）
# --------------------------------------------------------------------------- #

def test_backend_response_shapes_match_the_frontend_contract_over_real_http():
    """把后端真实响应的**形状**与前端解析器要求逐字段对齐。

    这里刻意检查两个真实存在过的形状陷阱：

    1. `diff.replaced[]` 的键是 `from_class` / `to_class`（换班），
       ⛔ 不是 `class_id`；
    2. `parsed_intent.locked_courses[].reason` 在后端是**可空**的。
    """

    with live_server(service_with()) as server:
        draft = _interpret(server, "尽量别在周五上课")
        assert set(draft) >= {
            "intent_id", "plan_digest", "parsed_intent", "ambiguities", "data_source",
            "generator_kind", "generator_note", "model_id", "can_confirm", "state",
            "token_usage_estimate", "message",
        }
        for row in draft["parsed_intent"]["locked_courses"]:
            assert "course_id" in row and "class_id" in row
            assert row.get("reason") is None or isinstance(row["reason"], str)

        _, solved = http_json(server.base_url, "POST", SOLVE_PATH, {
            "intent_id": draft["intent_id"], "plan_digest": draft["plan_digest"],
            "confirmed_intent": confirm_payload(
                plan_digest=draft["plan_digest"], weekday=5
            ),
        })
        for bucket in ("added", "removed", "kept"):
            for row in solved["diff"][bucket]:
                assert set(row) == {"course_id", "class_id"}
        for row in solved["diff"]["replaced"]:
            assert set(row) == {"course_id", "from_class", "to_class"}
        assert all(isinstance(item, str) for item in solved["risks"])
        assert all(isinstance(item, str) for item in solved["unresolved"])


def test_swap_diff_rows_use_from_class_and_to_class_keys():
    """直接构造一次**换班**，确认 `replaced` 行的键形状。

    这是前端 `parsePlanDiff` 最容易搞错的形状，因此单独锁定，
    防止以后有人把它改成 `class_id` 或在前端按 `class_id` 解析。
    """

    from app.ai_planning import compute_candidate_diff
    from app.models.contracts import PlanResult, PlanStatus, SelectedClass

    base = PlanResult(
        status=PlanStatus.PARTIALLY_FEASIBLE,
        selected_classes=[SelectedClass(course_id=DS_COURSE, class_id=DS_CLASS)],
        changes=[], risks=[], unresolved=[],
    )
    candidate = PlanResult(
        status=PlanStatus.PARTIALLY_FEASIBLE,
        selected_classes=[SelectedClass(course_id=DS_COURSE, class_id=DS_ALT_CLASS)],
        changes=[], risks=[], unresolved=[],
    )
    diff = compute_candidate_diff(base=base, candidate=candidate, offerings=tuple(offerings()))
    payload = diff.to_payload()
    assert payload["replaced"] == [{
        "course_id": DS_COURSE, "from_class": DS_CLASS, "to_class": DS_ALT_CLASS,
    }]
    assert set(payload["replaced"][0]) == {"course_id", "from_class", "to_class"}
    # ⚠️ 后端既有语义：`added` / `removed` 是**教学班键**的集合差，
    #    因此一次换班同时出现在 replaced（按课程看）与 added/removed（按班次看）。
    #    前端展示"换班"时必须优先看 `replaced`，否则会把同一门课显示成
    #    "移除 + 新增"两条。这里把该语义锁定下来，防止被静默改变。
    assert payload["added"] == [{"course_id": DS_COURSE, "class_id": DS_ALT_CLASS}]
    assert payload["removed"] == [{"course_id": DS_COURSE, "class_id": DS_CLASS}]
    assert payload["kept"] == []


# --------------------------------------------------------------------------- #
# 5. 既有路由不受影响
# --------------------------------------------------------------------------- #

def test_existing_routes_still_answer_over_real_http():
    with live_server(service_with()) as server:
        status, openapi = http_json(server.base_url, "GET", "/openapi.json")
        assert status == 200
        paths = set(openapi["paths"])
        for expected in (
            "/api/v1/plan",
            "/api/v1/mock/demo",
            "/api/v1/personal-planning/plan",
            "/api/v1/personal-planning/curriculum-versions",
            "/api/v1/explanation/plan",
            "/api/v1/completed-courses/import",
            STATUS_PATH, INTERPRET_PATH, SOLVE_PATH, ADOPT_PATH,
        ):
            assert expected in paths

        mock_status, mock = http_json(server.base_url, "GET", "/api/v1/mock/preference")
        assert mock_status == 200
        assert isinstance(mock, dict)


def test_scripted_model_with_hallucinated_course_is_rejected_over_real_http():
    """幻觉课程号必须 fail closed（422），不能变成候选。"""

    scripted = ScriptedIntentModel(script=(json.dumps({
        "summary": "锁定幻觉课程", "scope": "current_semester",
        "locked_courses": [{"course_id": "HALLUCINATED1", "class_id": "h-01"}],
    }),))
    with live_server(service_with(scripted)) as server:
        status, payload = http_json(server.base_url, "POST", INTERPRET_PATH, {
            "context": context_payload(max_credit=24.0), "user_message": "帮我锁定这门课",
        })
    assert status == 422
    assert payload["detail"]["error"] == "ai_planning_model_output_invalid"
    assert "HALLUCINATED1" not in json.dumps(payload, ensure_ascii=False)


def test_personal_information_in_message_is_refused_before_any_model_call():
    with live_server(service_with()) as server:
        status, payload = http_json(server.base_url, "POST", INTERPRET_PATH, {
            "context": context_payload(max_credit=24.0),
            "user_message": "我的学号是 2025123456，帮我少上点课",
        })
    assert status == 400
    assert payload["detail"]["error"] == "ai_planning_message_rejected"


# 让静态检查明确知道这些名字被引用（避免误删导入）。
_ = SEMESTER, NET_CLASS, NET_COURSE
