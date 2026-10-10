"""DeepSeek 在线验收：**默认离线，绝不自动调用收费模型**。

```text
# 1) 默认（离线）：注入确定性假模型，覆盖全部失败路径。⛔ 不产生任何模型费用。
python -m tests.verify_deepseek_live

# 2) 检查环境是否具备在线验收条件（只读环境变量，⛔ 不打印密钥值）
python -m tests.verify_deepseek_live --check-env

# 3) 受控在线验收（**会产生真实费用**，需要显式二次确认）
python -m tests.verify_deepseek_live --live --i-understand-this-costs-money

# 4) 受控在线 + 额外查一次 /models（同样免费但需要鉴权，可确认账号实际可用模型名）
python -m tests.verify_deepseek_live --live --i-understand-this-costs-money --check-models
```

## 为什么要有这个脚本

`docs/final_upgrade/DEEPSEEK_LIVE_VERIFICATION.md` 里原来的 `/solve` 示例
与真实契约不一致（多了一个不存在的 `confirm` 字段，且缺 `plan_digest` /
`confirmed_intent`）。手写 curl 很容易在 Windows 上因为编码与引号失败，
也无法覆盖失败路径。所以把"在线验收"做成**一个可执行的、默认离线的检查器**：

- **离线模式**用 `app.dependency_overrides` 注入 `RuleFakeIntentModel` /
  `ScriptedIntentModel` / `UnavailableIntentModel`，驱动**真实 FastAPI 应用**，
  通过**真实 HTTP** 跑完整条链路，逐项断言"模型只能解析意图、不能绕过 Planner"；
- **在线模式**复用真实的 `AiPlanningService`（真密钥、真 DeepSeek），
  只做**最小成本**的调用序列。

## 硬边界（与本任务书逐条对应）

- ⛔ CI 永不触网：在线模式需要 `--live` **和** `--i-understand-this-costs-money`
  两个开关同时给出，缺一即拒绝；
- ⛔ 密钥**只**从后端进程环境 `DEEPSEEK_API_KEY` 读取；
  ⛔ 不打印、⛔ 不落盘、⛔ 不进前端、⛔ 不写进报告；
- ⛔ 不使用任何硬编码 / 历史密钥作为回退；
- ⛔ 没有新密钥时保留 **BLOCKED**，绝不伪造成功、绝不把测试替身说成真实调用；
- ✅ 报告里出现 `generator_kind` 时，`test_double` / `unavailable` / `deepseek_live`
  三者严格区分。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import uvicorn  # noqa: E402

from app.ai_planning import (  # noqa: E402
    AiPlanningConfig,
    AiPlanningService,
    RuleFakeIntentModel,
    ScriptedIntentModel,
    SessionStore,
    UnavailableIntentModel,
)
from app.main import app  # noqa: E402
from app.planner import RestrictedPlannerProvider  # noqa: E402
from app.services.ai_planning_runtime import get_ai_planning_service  # noqa: E402
from tests.ai_planning_fixtures import (  # noqa: E402
    ALGO_CLASS,
    ALGO_COURSE,
    DS_CLASS,
    DS_COURSE,
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

#: 本脚本**唯一**读取的密钥类环境变量；⛔ 从不读取、也从不需要其它密钥变量。
API_KEY_ENV = "DEEPSEEK_API_KEY"
_ENV_NAMES = (
    API_KEY_ENV,
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "AI_PLANNING_ENABLED",
    "AI_PLANNING_MAX_OUTPUT_TOKENS",
    "AI_PLANNING_REQUEST_TIMEOUT",
    "AI_PLANNING_MAX_CALLS_PER_REQUEST",
)


# --------------------------------------------------------------------------- #
# 结果收集
# --------------------------------------------------------------------------- #

@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""

    def render(self) -> str:
        return f"  {'[OK]  ' if self.ok else '[FAIL]'} {self.name}" + (
            f"  — {self.detail}" if self.detail else ""
        )


@dataclass
class Report:
    mode: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name=name, ok=ok, detail=detail))

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.checks) and bool(self.checks)

    def render(self) -> str:
        lines = [f"结果：{sum(1 for c in self.checks if c.ok)}/{len(self.checks)} 项通过"]
        lines.extend(item.render() for item in self.checks)
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 真实 HTTP 服务器（复用与 test_ai_planning_joint_e2e 相同的做法）
# --------------------------------------------------------------------------- #

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LiveServer:
    """真实监听端口的 uvicorn 服务器；服务通过依赖注入替换。"""

    def __init__(self, service: AiPlanningService) -> None:
        self._service = service
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def install_service(self, service: AiPlanningService) -> None:
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
        else:  # pragma: no cover
            raise RuntimeError("uvicorn 未能在 20 秒内启动")
        return self

    def __exit__(self, *args: object) -> None:
        app.dependency_overrides.pop(get_ai_planning_service, None)
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=20.0)


def http_json(
    base_url: str, method: str, path: str, body: dict | None = None
) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            return error.code, json.loads(raw)
        except json.JSONDecodeError:
            return error.code, {"raw": raw[:300]}


def error_code(payload: dict) -> str:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("error", ""))
    return ""


# --------------------------------------------------------------------------- #
# 模型与服务装配
# --------------------------------------------------------------------------- #

def _config(*, enabled: bool, ttl: int, api_key: str | None) -> AiPlanningConfig:
    return AiPlanningConfig(
        enabled=enabled,
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        max_output_tokens=1200,
        request_timeout=float(os.environ.get("AI_PLANNING_REQUEST_TIMEOUT", "20")),
        max_calls_per_request=3,
        max_sessions=50,
        adopt_ttl_seconds=ttl,
    )


def _service_for_offline(model: Any, *, enabled: bool = True, ttl: int = 900) -> AiPlanningService:
    return AiPlanningService(
        config=_config(enabled=enabled, ttl=ttl, api_key=None),
        intent_model=model,
        planner=RestrictedPlannerProvider(),
        sessions=SessionStore(max_sessions=50),
    )


def _rule_model() -> RuleFakeIntentModel:
    selected = {item.course_id: item.class_id for item in base_plan().selected_classes}
    return RuleFakeIntentModel(
        known_course_ids=(DS_COURSE, ALGO_COURSE, NET_COURSE),
        known_class_by_course={
            course_id: selected.get(course_id, f"{course_id.lower()}-01")
            for course_id in (DS_COURSE, ALGO_COURSE, NET_COURSE)
        },
        course_aliases={"数据结构": DS_COURSE, "算法": ALGO_COURSE, "网络": NET_COURSE},
    )


def _live_service(api_key: str, *, ttl: int = 900) -> AiPlanningService:
    """真实在线服务：真密钥 + 真 DeepSeek 客户端 + 真实冻结 Planner。"""

    from app.ai_planning import DeepSeekChatClient

    config = _config(enabled=True, ttl=ttl, api_key=api_key)
    return AiPlanningService(
        config=config,
        intent_model=DeepSeekChatClient(config),
        planner=RestrictedPlannerProvider(),
        sessions=SessionStore(max_sessions=50),
    )


# --------------------------------------------------------------------------- #
# 离线检查（默认路径）：覆盖失败路径 + "模型不得绕过 Planner" 的负向用例
# --------------------------------------------------------------------------- #

def run_offline(report: Report) -> None:
    context = context_payload()
    # ---- 1) 未启用：503，且不解析 ----
    with LiveServer(_service_for_offline(_rule_model(), enabled=False)) as server:
        code, body = http_json(server.base_url, "GET", STATUS_PATH)
        report.add(
            "未启用时 /status 如实报告 enabled=false",
            code == 200 and body.get("enabled") is False,
            f"HTTP {code} enabled={body.get('enabled')}",
        )
        code, body = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课"},
        )
        report.add(
            "未启用时 /interpret 返回 503 ai_planning_disabled（不 fallback）",
            code == 503 and error_code(body) == "ai_planning_disabled",
            f"HTTP {code} error={error_code(body)}",
        )

    # ---- 2) 无密钥 / 模型不可用：503 ----
    with LiveServer(_service_for_offline(UnavailableIntentModel(reason="missing_api_key"))) as server:
        code, body = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课"},
        )
        report.add(
            "无可用模型时 /interpret 返回 503 ai_planning_model_unavailable",
            code == 503 and error_code(body) == "ai_planning_model_unavailable",
            f"HTTP {code} error={error_code(body)}",
        )

    # ---- 3) 正常路径：一次完整闭环（离线假模型）----
    with LiveServer(_service_for_offline(_rule_model())) as server:
        code, status = http_json(server.base_url, "GET", STATUS_PATH)
        report.add(
            "离线 /status 不泄露密钥字段",
            code == 200 and status.get("api_key_configured") is False
            and "key" not in json.dumps(status).lower().replace("api_key_configured", "")
            and status.get("generator_kind_when_live") == "deepseek_live",
            f"HTTP {code} api_key_configured={status.get('api_key_configured')}",
        )

        code, draft = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课，最多 12 学分"},
        )
        report.add(
            "离线 /interpret 标注 test_double（⛔ 不说成 deepseek_live）",
            code == 200 and draft.get("generator_kind") == "test_double",
            f"HTTP {code} generator_kind={draft.get('generator_kind')}",
        )
        report.add(
            "离线 /interpret 返回 64 位方案指纹",
            len(str(draft.get("plan_digest", ""))) == 64,
            f"digest_len={len(str(draft.get('plan_digest', '')))}",
        )

        code, solved = http_json(
            server.base_url, "POST", SOLVE_PATH,
            {
                "intent_id": draft.get("intent_id"),
                "plan_digest": draft.get("plan_digest"),
                "confirmed_intent": confirm_payload(
                    plan_digest=draft.get("plan_digest", ""), weekday=5,
                ),
            },
        )
        report.add(
            "离线 /solve 返回 candidate_ready",
            code == 200 and solved.get("status") == "candidate_ready",
            f"HTTP {code} status={solved.get('status')}",
        )
        report.add(
            "候选里的教学班全部来自**请求给出的 offerings**（Planner 决定，不是模型编的）",
            _candidate_within_offerings(solved, context),
            _candidate_summary(solved),
        )

        code, adopted = http_json(
            server.base_url, "POST", ADOPT_PATH,
            {
                "candidate_id": solved.get("candidate_id"),
                "plan_digest": solved.get("plan_digest"),
                "accept": True,
            },
        )
        report.add(
            "二次确认采用后 scope=process_local_session 且版本推进到 1",
            code == 200 and adopted.get("accepted") is True
            and adopted.get("adopted_version") == 1
            and adopted.get("adopted_version_scope") == "process_local_session",
            f"HTTP {code} version={adopted.get('adopted_version')} scope={adopted.get('adopted_version_scope')}",
        )

        # 重复采用 ⇒ 409
        code, again = http_json(
            server.base_url, "POST", ADOPT_PATH,
            {
                "candidate_id": solved.get("candidate_id"),
                "plan_digest": solved.get("plan_digest"),
                "accept": True,
            },
        )
        report.add(
            "重复采用 ⇒ 409 ai_planning_adoption_conflict（原方案不变）",
            code == 409 and error_code(again) == "ai_planning_adoption_conflict",
            f"HTTP {code} error={error_code(again)}",
        )

    # ---- 4) 意图歧义：can_confirm=false，且确认前不能求解 ----
    with LiveServer(_service_for_offline(_rule_model())) as server:
        code, draft = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "这学期太累，少上一点课就行"},
        )
        report.add(
            "模糊意图（无学分数字）⇒ can_confirm=false 且给出歧义",
            code == 200 and draft.get("can_confirm") is False
            and len(draft.get("ambiguities") or []) > 0,
            f"HTTP {code} can_confirm={draft.get('can_confirm')} ambiguities={len(draft.get('ambiguities') or [])}",
        )
        # ⛔ 即使硬把 confirmed_intent 传进去，歧义意图也**不能**求解
        code, solved = http_json(
            server.base_url, "POST", SOLVE_PATH,
            {
                "intent_id": draft.get("intent_id"),
                "plan_digest": draft.get("plan_digest"),
                "confirmed_intent": confirm_payload(plan_digest=draft.get("plan_digest", "")),
            },
        )
        report.add(
            "歧义意图强行求解 ⇒ 409（⛔ 未确认不得求解）",
            code == 409,
            f"HTTP {code} error={error_code(solved)}",
        )

    # ---- 5) 指纹不符 ⇒ 410 ----
    with LiveServer(_service_for_offline(_rule_model())) as server:
        code, draft = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课，最多 12 学分"},
        )
        code, solved = http_json(
            server.base_url, "POST", SOLVE_PATH,
            {
                "intent_id": draft.get("intent_id"),
                "plan_digest": "f" * 64,
                "confirmed_intent": confirm_payload(plan_digest="f" * 64),
            },
        )
        report.add(
            "方案指纹不符 ⇒ 410 ai_planning_session_expired",
            code == 410 and error_code(solved) == "ai_planning_session_expired",
            f"HTTP {code} error={error_code(solved)}",
        )

    # ---- 6) 候选过期（TTL=1s）⇒ 410，且原方案不变 ----
    with LiveServer(_service_for_offline(_rule_model(), ttl=1)) as server:
        code, draft = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课，最多 12 学分"},
        )
        code, solved = http_json(
            server.base_url, "POST", SOLVE_PATH,
            {
                "intent_id": draft.get("intent_id"),
                "plan_digest": draft.get("plan_digest"),
                "confirmed_intent": confirm_payload(plan_digest=draft.get("plan_digest", "")),
            },
        )
        time.sleep(1.6)
        code, adopted = http_json(
            server.base_url, "POST", ADOPT_PATH,
            {
                "candidate_id": solved.get("candidate_id"),
                "plan_digest": solved.get("plan_digest"),
                "accept": True,
            },
        )
        report.add(
            "候选过期后采用 ⇒ 410 且原方案不变",
            code == 410 and error_code(adopted) == "ai_planning_session_expired",
            f"HTTP {code} error={error_code(adopted)}",
        )

    # ---- 7) 拒绝采用 ⇒ accepted=false、原方案不变 ----
    with LiveServer(_service_for_offline(_rule_model())) as server:
        code, draft = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课，最多 12 学分"},
        )
        code, solved = http_json(
            server.base_url, "POST", SOLVE_PATH,
            {
                "intent_id": draft.get("intent_id"),
                "plan_digest": draft.get("plan_digest"),
                "confirmed_intent": confirm_payload(plan_digest=draft.get("plan_digest", "")),
            },
        )
        code, rejected = http_json(
            server.base_url, "POST", ADOPT_PATH,
            {
                "candidate_id": solved.get("candidate_id"),
                "plan_digest": solved.get("plan_digest"),
                "accept": False,
            },
        )
        report.add(
            "拒绝采用 ⇒ accepted=false 且 original_plan_unchanged=true",
            code == 200 and rejected.get("accepted") is False
            and rejected.get("original_plan_unchanged") is True
            and rejected.get("adopted_version") == 0,
            f"HTTP {code} accepted={rejected.get('accepted')} version={rejected.get('adopted_version')}",
        )

    # ---- 8) 非法模型输出：白名单外课程号 ⇒ 422（⛔ 不猜测、不忽略）----
    hallucination = json.dumps(
        {
            "summary": "尽量别在周五上课",
            "scope": "current_semester",
            "target_semester": SEMESTER,
            "hard_constraints": [],
            "soft_preferences": [{"kind": "avoid_weekday", "value": 5, "note": "避开周五"}],
            "locked_courses": [
                {"course_id": "HALLUCINATED999", "class_id": "ghost-01", "reason": "模型编的"}
            ],
            "confidence": 0.9,
            "notes": [],
            "ambiguities": [],
        },
        ensure_ascii=False,
    )
    with LiveServer(_service_for_offline(ScriptedIntentModel(script=(hallucination,)))) as server:
        code, body = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "必须保留一门课"},
        )
        report.add(
            "模型输出幻觉课程号 ⇒ 422 ai_planning_model_output_invalid（白名单拦截）",
            code == 422 and error_code(body) == "ai_planning_model_output_invalid",
            f"HTTP {code} error={error_code(body)}",
        )

    # ---- 9) 非法模型输出：结构错（不是 JSON 对象）⇒ 503 unavailable ----
    with LiveServer(_service_for_offline(ScriptedIntentModel(script=("not json at all",)))) as server:
        code, body = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课"},
        )
        report.add(
            "模型返回非 JSON ⇒ 503（⛔ 不返回编造草稿）",
            code == 503 and error_code(body) == "ai_planning_model_unavailable",
            f"HTTP {code} error={error_code(body)}",
        )

    # ---- 10) 请求体多带字段 ⇒ 422（extra=forbid，防个人信息夹带）----
    with LiveServer(_service_for_offline(_rule_model())) as server:
        leaked = {"context": context, "user_message": "尽量别在周五上课", "student_name": "张三"}
        code, _ = http_json(server.base_url, "POST", INTERPRET_PATH, leaked)
        report.add(
            "请求体夹带额外字段（如姓名）⇒ 422（extra=forbid）",
            code == 422,
            f"HTTP {code}",
        )

    # ---- 11) 模型"想直接给方案"也必须被忽略：/interpret 的响应里没有方案体 ----
    solver_payload = json.dumps(
        {
            "summary": "直接给我排好的课",
            "scope": "current_semester",
            "target_semester": SEMESTER,
            "hard_constraints": [],
            "soft_preferences": [],
            "locked_courses": [],
            "confidence": 0.9,
            "notes": [],
            "ambiguities": [],
            "candidate_plan": {"selected_classes": [{"course_id": "GHOST", "class_id": "g-1"}]},
        },
        ensure_ascii=False,
    )
    with LiveServer(_service_for_offline(ScriptedIntentModel(script=(solver_payload,)))) as server:
        code, body = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "直接给我排好的课"},
        )
        # 模型多写了未声明字段 ⇒ 直接拒绝（比"忽略"更安全）
        report.add(
            "模型试图夹带 candidate_plan ⇒ 422（未声明字段直接拒绝，⛔ 不忽略）",
            code == 422 and error_code(body) == "ai_planning_model_output_invalid",
            f"HTTP {code} error={error_code(body)}",
        )


def _candidate_within_offerings(solved: dict, context: dict) -> bool:
    plan = solved.get("candidate_plan")
    if not isinstance(plan, dict):
        return False
    known = {
        (item.get("course_id"), item.get("class_id"))
        for item in (context.get("course_offerings") or [])
    }
    selected = plan.get("selected_classes") or []
    if not selected:
        return False
    return all((item.get("course_id"), item.get("class_id")) in known for item in selected)


def _candidate_summary(solved: dict) -> str:
    plan = solved.get("candidate_plan") or {}
    selected = plan.get("selected_classes") or []
    pairs = ", ".join(f"{i.get('course_id')}/{i.get('class_id')}" for i in selected)
    return f"status={solved.get('status')} selected=[{pairs}]"


# --------------------------------------------------------------------------- #
# 环境检查（只读环境变量，⛔ 不打印值）
# --------------------------------------------------------------------------- #

def run_check_env(report: Report) -> None:
    present = {name: bool(os.environ.get(name)) for name in _ENV_NAMES}
    report.add(
        "环境变量存在性（只报告有无，⛔ 不打印值）",
        True,
        ", ".join(f"{k}={'SET' if v else 'unset'}" for k, v in present.items()),
    )
    report.add(
        "存在新的 DEEPSEEK_API_KEY（未设置则本轮保持 BLOCKED）",
        present[API_KEY_ENV],
        "BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE" if not present[API_KEY_ENV] else "已设置",
    )
    enabled = (os.environ.get("AI_PLANNING_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"})
    report.add(
        "AI_PLANNING_ENABLED 已打开（在线验收前提）",
        enabled,
        f"AI_PLANNING_ENABLED={'true' if enabled else 'false/unset'}",
    )
    model = os.environ.get("DEEPSEEK_MODEL") or "(未设置，服务端默认将使用配置中的默认值)"
    report.add("模型名（⛔ 非密钥，可安全记录）", True, model)


# --------------------------------------------------------------------------- #
# 受控在线验收（会产生真实费用）
# --------------------------------------------------------------------------- #

def run_live(report: Report, api_key: str, *, check_models: bool) -> None:
    context = context_payload()
    with LiveServer(_live_service(api_key)) as server:
        code, status = http_json(server.base_url, "GET", STATUS_PATH)
        report.add(
            "/status 报告配置就绪（enabled + api_key_configured）",
            code == 200 and status.get("enabled") is True
            and status.get("api_key_configured") is True,
            f"HTTP {code} enabled={status.get('enabled')} "
            f"api_key_configured={status.get('api_key_configured')} "
            f"live_model_available={status.get('live_model_available')}",
        )
        report.add(
            "/status 不含密钥内容（只报告是否配置）",
            _no_secret_leak(json.dumps(status)),
            "响应体已检查，无嫌疑字符串",
        )

        if check_models:
            code, body = _list_models(api_key, status.get("base_url", ""))
            ids = [item.get("id") for item in (body.get("data") or [])] if isinstance(body, dict) else []
            report.add(
                "GET /models 列出账号实际可用模型（只读、不产生费用）",
                code == 200 and bool(ids),
                f"HTTP {code} ids={ids}",
            )
            report.add(
                "配置的模型名在账号可用列表内",
                status.get("model") in ids,
                f"configured={status.get('model')} available={ids}",
            )

        code, draft = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "尽量别在周五上课，最多 12 学分"},
        )
        live_ok = code == 200 and draft.get("generator_kind") == "deepseek_live"
        report.add(
            "真实 /interpret 返回 generator_kind=deepseek_live（这是在线路径可用的**唯一**证明）",
            live_ok,
            f"HTTP {code} generator_kind={draft.get('generator_kind')} model_id={draft.get('model_id')} "
            f"tokens={draft.get('token_usage_estimate', {}).get('total')}",
        )
        if not live_ok:
            report.add(
                "在线路径未通过 ⇒ 停止后续调用（⛔ 不把 test_double/unavailable 说成成功）",
                False,
                "已中止，避免无意义费用",
            )
            return

        report.add(
            "模型输出的课程号全部落在上下文白名单内",
            _draft_within_whitelist(draft, context),
            _draft_course_summary(draft),
        )

        code, ambiguous = http_json(
            server.base_url, "POST", INTERPRET_PATH,
            {"context": context, "user_message": "这学期太累，少上一点课就行"},
        )
        report.add(
            "模糊意图 ⇒ can_confirm=false（模型不得替用户默认学分上限）",
            code == 200 and ambiguous.get("can_confirm") is False,
            f"HTTP {code} can_confirm={ambiguous.get('can_confirm')} "
            f"ambiguities={len(ambiguous.get('ambiguities') or [])}",
        )

        code, solved = http_json(
            server.base_url, "POST", SOLVE_PATH,
            {
                "intent_id": draft.get("intent_id"),
                "plan_digest": draft.get("plan_digest"),
                "confirmed_intent": confirm_payload(
                    plan_digest=draft.get("plan_digest", ""), weekday=5,
                ),
            },
        )
        report.add(
            "/solve 由受控 Planner 产生候选（不产生模型调用）",
            code == 200 and solved.get("status") in {
                "candidate_ready", "no_feasible_candidate", "blocked"
            },
            f"HTTP {code} status={solved.get('status')} blocked_reason={solved.get('blocked_reason')}",
        )
        report.add(
            "候选（若有）中的教学班全部来自请求给出的 offerings ⇒ 方案不是模型编的",
            _candidate_within_offerings(solved, context) or solved.get("candidate_plan") is None,
            _candidate_summary(solved),
        )

        if solved.get("candidate_id"):
            code, rejected = http_json(
                server.base_url, "POST", ADOPT_PATH,
                {
                    "candidate_id": solved.get("candidate_id"),
                    "plan_digest": solved.get("plan_digest"),
                    "accept": False,
                },
            )
            report.add(
                "拒绝采用 ⇒ 原方案不变（在线会话同样如此）",
                code == 200 and rejected.get("accepted") is False
                and rejected.get("original_plan_unchanged") is True,
                f"HTTP {code} accepted={rejected.get('accepted')}",
            )


def _list_models(api_key: str, base_url: str) -> tuple[int, dict]:
    """只读地列出账号可用模型；⛔ 不打印密钥、⛔ 不写入任何文件。"""

    url = f"{(base_url or 'https://api.deepseek.com').rstrip('/')}/models"
    request = urllib.request.Request(
        url, method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, {}
    except OSError:
        return 0, {}


def _no_secret_leak(text: str) -> bool:
    lowered = text.lower()
    if "sk-" in lowered:
        return False
    # `api_key_configured` 是**布尔字段名**，允许出现；但不得出现 "api_key": "<值>"
    return '"api_key"' not in lowered


def _draft_within_whitelist(draft: dict, context: dict) -> bool:
    known_courses = {item.get("course_id") for item in (context.get("makeup_tasks") or [])}
    known_courses |= {item.get("course_id") for item in (context.get("course_offerings") or [])}
    known_courses |= {
        item.get("course_id") for item in (context.get("base_plan", {}).get("selected_classes") or [])
    }
    parsed = draft.get("parsed_intent") or {}
    for row in (parsed.get("locked_courses") or []):
        if row.get("course_id") not in known_courses:
            return False
    for row in (parsed.get("hard_constraints") or []):
        value = row.get("value")
        if isinstance(value, str) and value.startswith(("DS", "ALGO", "NET")) and value not in known_courses:
            return False
    return True


def _draft_course_summary(draft: dict) -> str:
    parsed = draft.get("parsed_intent") or {}
    locks = [row.get("course_id") for row in (parsed.get("locked_courses") or [])]
    hard = [row.get("kind") for row in (parsed.get("hard_constraints") or [])]
    soft = [row.get("kind") for row in (parsed.get("soft_preferences") or [])]
    return f"locked={locks} hard={hard} soft={soft}"


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DeepSeek 受控在线验收（默认离线；在线需双重显式确认）",
    )
    parser.add_argument("--check-env", action="store_true", help="只检查环境变量是否存在（⛔ 不打印值）")
    parser.add_argument("--live", action="store_true", help="启用真实在线调用（会产生费用）")
    parser.add_argument(
        "--i-understand-this-costs-money",
        dest="cost_ack",
        action="store_true",
        help="在线模式的第二重确认（缺此开关则拒绝运行）",
    )
    parser.add_argument("--check-models", action="store_true", help="在线时额外查询 /models（只读）")
    args = parser.parse_args(argv)

    report = Report(mode="offline")

    if args.check_env:
        report.mode = "check-env"
        run_check_env(report)
        print("=" * 72)
        print("DeepSeek 在线验收 —— 环境检查（CLI 侧进程环境）")
        print("=" * 72)
        print(report.render())
        print()
        print("说明：后端服务是**独立进程**。CLI 侧 unset 不代表后端侧也 unset；")
        print("      `--live` 模式在**本进程内**启动后端，因此这里的环境就是后端的环境。")
        return 0 if report.ok else 1

    if args.live:
        if not args.cost_ack:
            print("拒绝运行：--live 必须同时给出 --i-understand-this-costs-money。")
            print("（这是为了避免在无人值守 / CI 环境里意外产生真实模型费用。）")
            return 2
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            print("=" * 72)
            print("BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE")
            print("=" * 72)
            print("未检测到 DEEPSEEK_API_KEY：本轮**不进行**任何在线调用，")
            print("也⛔ 不使用历史密钥、⛔ 不伪造成功。")
            print("请按 docs/final_upgrade/DEEPSEEK_LIVE_VERIFICATION.md 注入新密钥后重试。")
            return 3
        report.mode = "live"
        print("=" * 72)
        print("DeepSeek 受控在线验收（会产生真实费用，调用次数最小化）")
        print("=" * 72)
        run_live(report, api_key, check_models=args.check_models)
    else:
        print("=" * 72)
        print("DeepSeek 验收 —— 离线模式（⛔ 不调用任何收费模型）")
        print("=" * 72)
        run_offline(report)

    print(report.render())
    print()
    if report.mode == "offline":
        print("说明：离线模式用注入的确定性假模型驱动**真实后端**，")
        print("      `generator_kind` 为 test_double / unavailable，⛔ 不代表真实 DeepSeek 可用。")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
