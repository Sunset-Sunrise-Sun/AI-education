"""AI Planning Controller 的进程内装配（**显式、fail closed**，非公共契约）。

```text
环境变量
    ↓  build_ai_planning_service(environment)
AiPlanningService（含进程内会话存储 + 可选的真实 DeepSeek 客户端）
```

## 硬边界

- ⛔ **没有密钥就不构造真实客户端**：`intent_model` 为 `None` ⇒ 解析接口明确不可用；
- ⛔ **不内置任何假模型作为回退**：测试必须**显式注入**
  （`app.dependency_overrides` 或直接构造服务），因此"线上看起来能用"
  永远不可能是测试替身造成的；
- ⛔ 不落盘、不建库、不联网（联网只发生在真实客户端被调用时）；
- ⛔ 不打印任何配置取值（尤其是密钥）。
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from app.ai_planning.config import AiPlanningConfig, load_config
from app.ai_planning.deepseek_client import DeepSeekChatClient, IntentModel
from app.ai_planning.service import AiPlanningService, SessionStore
from app.planner import RestrictedPlannerProvider

__all__ = [
    "build_ai_planning_service",
    "get_ai_planning_service",
    "reset_ai_planning_service",
]

_SERVICE: AiPlanningService | None = None


def _optional_planner() -> object | None:
    """受控 Planner 是**确定性**组件，可直接装配（⛔ 它不是模型）。"""

    return RestrictedPlannerProvider()


def build_ai_planning_service(
    environment: Mapping[str, str] | None = None,
    *,
    intent_model: IntentModel | None = None,
    planner: object | None = None,
    sessions: SessionStore | None = None,
) -> AiPlanningService:
    """按环境配置装配服务；真实模型只在**开关打开且注入密钥**时构造。"""

    config: AiPlanningConfig = load_config(environment)
    model = intent_model
    if model is None and config.live_model_available:
        model = DeepSeekChatClient(config)
    return AiPlanningService(
        config=config,
        intent_model=model,
        planner=_optional_planner() if planner is None else planner,
        sessions=sessions if sessions is not None else SessionStore(
            max_sessions=config.max_sessions
        ),
    )


def get_ai_planning_service() -> AiPlanningService:
    """FastAPI dependency：进程内**单例**（会话状态在进程内，重启即失效）。"""

    global _SERVICE
    if _SERVICE is None:
        _SERVICE = build_ai_planning_service(os.environ)
    return _SERVICE


def reset_ai_planning_service() -> None:
    """测试用：丢弃当前单例（⛔ 生产路径不调用）。"""

    global _SERVICE
    _SERVICE = None
