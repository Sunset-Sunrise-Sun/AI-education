"""QA-only ASGI app：真实 FastAPI + **注入式测试模型** + 受控演示数据。

```text
browser → Vite dev server (proxy /api → 本 app)
                 ↓
        app.main.app（**真实**路由：/api/v1/plan、personal-planning、
                       explanation、ai-planning/{status,interpret,solve,adopt}）
        + app.dependency_overrides[get_ai_planning_service]
              → AiPlanningService(intent_model=RuleFakeIntentModel(...),
                                  planner=RestrictedPlannerProvider())
        + 把 GET /api/v1/mock/demo **插到路由表最前面**，改为返回
          tests/qa_browser_e2e/qa_demo_data.json
```

## 为什么需要它（以及为什么它不是"生产假模型开关"）

任务书要求"对于需要真实后端测试替身的场景，应复用测试环境中的受控依赖注入，
不要在生产接口中新增公开的假模型开关"。因此：

- ⛔ **生产代码零改动**：本文件位于 `backend/tests/`，只在 QA 命令里被 uvicorn 加载；
- ⛔ **没有新增环境变量 / 没有公开开关**：注入方式与
  `tests/test_ai_planning_joint_e2e.py` 完全一致（`app.dependency_overrides`）；
- ✅ `/status` 会如实返回 `enabled=true`、`live_model_available=false`，
  `generator_kind` 只能是 `test_double`（⛔ 不是 `deepseek_live`）；
- ✅ 被覆盖的只有 **Mock 回放通道** `/api/v1/mock/demo`，
  它的数据本来就必须是演示数据；覆盖内容来自同目录的 JSON 夹具，
  在响应头与 JSON 内都带来源标记；
- ✅ 真实路由（Planner 求解、两次确认、adopt、503 readiness）全部是本 app 的真实实现。

⚠️ 覆盖必须**插到路由表最前面**：`app.include_router` 是追加，
后注册的同路径路由永远不会被匹配（否则会静默继续返回仓库自带的演示数据）。

启动方式见 `tools/browser-e2e/run_browser_e2e.mjs`。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.ai_planning import (
    AiPlanningConfig,
    AiPlanningService,
    RuleFakeIntentModel,
    SessionStore,
)
from app.main import app
from app.planner import RestrictedPlannerProvider
from app.services.ai_planning_runtime import get_ai_planning_service

__all__ = ["app", "QA_SEED_HEADER", "QA_SEED_VALUE", "build_qa_service", "install_overrides"]

#: 覆盖后的演示数据来源标记（响应头 + JSON 内都带，便于测试断言"MOCK 已标注"）。
QA_SEED_HEADER = "X-QA-E2E-Seed"
QA_SEED_VALUE = "mock-qa-seed"

DEMO_PATH = "/api/v1/mock/demo"
_SEED_FILE = Path(__file__).resolve().parent / "qa_demo_data.json"

#: 测试替身只认这些课程号，因此不会"发明"课程。
_KNOWN_COURSES = ("62001001", "62001002", "62002031", "62003007", "62004005", "62009001")
_CLASS_BY_COURSE = {
    "62001001": "6200100120260101",
    "62001002": "6200100220260101",
    "62002031": "6200203120260101",
    "62003007": "6200300720260101",
}


def _load_seed() -> dict:
    return json.loads(_SEED_FILE.read_text(encoding="utf-8"))


def _enabled() -> bool:
    """是否启用控制器；`QA_AI_PLANNING_ENABLED=0` 时用于验证"未启用"档位。"""

    return os.environ.get("QA_AI_PLANNING_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def build_qa_service() -> AiPlanningService:
    """构造注入式服务：**无密钥**、真实受限 Planner；默认启用，可按环境关闭。"""

    enabled = _enabled()
    config = AiPlanningConfig(
        enabled=enabled,
        api_key=None,                       # ⛔ 没有密钥：绝不会发真实 DeepSeek 请求
        base_url=os.environ.get("QA_DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model="qa-test-double",
        max_output_tokens=1200,
        request_timeout=5.0,
        max_calls_per_request=3,
        max_sessions=50,
        adopt_ttl_seconds=int(os.environ.get("QA_ADOPT_TTL_SECONDS", "900")),
    )
    model = RuleFakeIntentModel(
        model_id="qa-rule-fake",
        known_course_ids=_KNOWN_COURSES,
        known_class_by_course=dict(_CLASS_BY_COURSE),
        course_aliases={"数据结构": "62001002", "离散数学": "62001001"},
    )
    return AiPlanningService(
        config=config,
        # ⚠️ 关闭档位下**不注入任何模型**（与真实生产一致：没有密钥就没有模型），
        # 这样 /status 会返回 enabled=false，接口返回 503 ai_planning_disabled。
        intent_model=model if enabled else None,
        planner=RestrictedPlannerProvider(),
        sessions=SessionStore(max_sessions=50),
    )


def _qa_demo() -> Response:
    """覆盖永久 Mock 回放通道：返回 QA 夹具，并显式标注来源。"""

    payload = _load_seed()
    payload["qa_e2e_seed"] = QA_SEED_VALUE
    return JSONResponse(content=payload, headers={QA_SEED_HEADER: QA_SEED_VALUE})


def install_overrides() -> AiPlanningService:
    """装上依赖注入与演示数据覆盖（幂等，可重复调用）。"""

    service = build_qa_service()
    app.dependency_overrides[get_ai_planning_service] = lambda: service

    # ⚠️ 必须插到最前面：`include_router` 追加的同路径路由不会被匹配。
    app.router.routes = [
        route for route in app.router.routes
        if not (isinstance(route, APIRoute) and route.path == DEMO_PATH and "GET" in route.methods)
    ]
    app.router.routes.insert(
        0,
        APIRoute(
            DEMO_PATH,
            _qa_demo,
            methods=["GET"],
            include_in_schema=False,
            name="qa_mock_demo",
        ),
    )
    return service


QA_SERVICE = install_overrides()
