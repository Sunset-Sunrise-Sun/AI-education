"""AI Planning Controller 的服务器端配置（**默认关闭**，绝不内置任何密钥）。

```text
DEEPSEEK_API_KEY           仅由服务器运行环境注入；⛔ 不提交、⛔ 不回传前端、⛔ 不写日志
DEEPSEEK_BASE_URL          默认 https://api.deepseek.com（OpenAI 兼容）
DEEPSEEK_MODEL             默认 deepseek-flash
AI_PLANNING_ENABLED        默认 false ⇒ 控制器整体不可用（fail closed）
AI_PLANNING_MAX_OUTPUT_TOKENS   单次模型输出上限（有界）
AI_PLANNING_REQUEST_TIMEOUT     单次模型请求超时秒数（有界）
AI_PLANNING_MAX_CALLS_PER_REQUEST   单次 HTTP 请求允许的模型调用次数上限
AI_PLANNING_MAX_SESSIONS        进程内会话上限（超出即淘汰最旧，不落盘）
AI_PLANNING_ADOPT_TTL_SECONDS   候选的有效期；过期即 fail closed
```

## 硬边界

- ⛔ **没有密钥时绝不假装调用成功**：`enabled` 为假，
  `generator_kind` 只能是 `unavailable`，接口明确返回"未启用"而不是伪造意图；
- ⛔ 不引入新的第三方依赖或 Agent 框架：走标准库 `urllib.request`
  直接调用 OpenAI 兼容的 `/chat/completions`；
- ⛔ 不把配置取值（尤其是密钥）写进响应、日志或异常文本；
- ⚠️ 历史对话中出现过的 `sk-` 前缀旧密钥**已作废**，本模块⛔ 不使用、⛔ 不引用、
  ⛔ 不做任何形式的硬编码回退。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

__all__ = [
    "AI_PLANNING_ENABLED",
    "AI_PLANNING_MAX_CALLS_PER_REQUEST",
    "AI_PLANNING_MAX_OUTPUT_TOKENS",
    "AI_PLANNING_MAX_SESSIONS",
    "AI_PLANNING_ADOPT_TTL_SECONDS",
    "AI_PLANNING_REQUEST_TIMEOUT",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_CALLS_PER_REQUEST",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_SESSIONS",
    "DEFAULT_ADOPT_TTL_SECONDS",
    "DEFAULT_MODEL",
    "DEFAULT_REQUEST_TIMEOUT",
    "MAX_ALLOWED_CALLS_PER_REQUEST",
    "MAX_ALLOWED_OUTPUT_TOKENS",
    "MAX_ALLOWED_REQUEST_TIMEOUT",
    "MAX_ALLOWED_SESSIONS",
    "MIN_ALLOWED_REQUEST_TIMEOUT",
    "AiPlanningConfig",
    "load_config",
]

DEEPSEEK_API_KEY: Final[str] = "DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL: Final[str] = "DEEPSEEK_BASE_URL"
DEEPSEEK_MODEL: Final[str] = "DEEPSEEK_MODEL"
AI_PLANNING_ENABLED: Final[str] = "AI_PLANNING_ENABLED"
AI_PLANNING_MAX_OUTPUT_TOKENS: Final[str] = "AI_PLANNING_MAX_OUTPUT_TOKENS"
AI_PLANNING_REQUEST_TIMEOUT: Final[str] = "AI_PLANNING_REQUEST_TIMEOUT"
AI_PLANNING_MAX_CALLS_PER_REQUEST: Final[str] = "AI_PLANNING_MAX_CALLS_PER_REQUEST"
AI_PLANNING_MAX_SESSIONS: Final[str] = "AI_PLANNING_MAX_SESSIONS"
AI_PLANNING_ADOPT_TTL_SECONDS: Final[str] = "AI_PLANNING_ADOPT_TTL_SECONDS"

DEFAULT_BASE_URL: Final[str] = "https://api.deepseek.com"
DEFAULT_MODEL: Final[str] = "deepseek-flash"
DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 1200
DEFAULT_REQUEST_TIMEOUT: Final[float] = 20.0
DEFAULT_MAX_CALLS_PER_REQUEST: Final[int] = 3
DEFAULT_MAX_SESSIONS: Final[int] = 200
DEFAULT_ADOPT_TTL_SECONDS: Final[int] = 900

#: 硬上界：即使环境变量被写成很大的数，也不会让成本 / 延迟失控。
MAX_ALLOWED_OUTPUT_TOKENS: Final[int] = 8000
MIN_ALLOWED_REQUEST_TIMEOUT: Final[float] = 1.0
MAX_ALLOWED_REQUEST_TIMEOUT: Final[float] = 120.0
MAX_ALLOWED_CALLS_PER_REQUEST: Final[int] = 8
MAX_ALLOWED_SESSIONS: Final[int] = 5000
MAX_ALLOWED_ADOPT_TTL: Final[int] = 86400

_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES: Final[frozenset[str]] = frozenset({"0", "false", "no", "off", ""})


def _flag(environment: Mapping[str, str], name: str, *, default: bool) -> bool:
    raw = environment.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    # ⛔ 非法开关值一律 fail closed（当作关闭），不猜用户意图。
    return False


def _bounded_int(
    environment: Mapping[str, str], name: str, *, default: int, minimum: int, maximum: int
) -> int:
    raw = environment.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip(), 10)
    except (TypeError, ValueError):
        return default
    if value < minimum:
        return minimum
    return min(value, maximum)


def _bounded_float(
    environment: Mapping[str, str], name: str, *, default: float, minimum: float, maximum: float
) -> float:
    raw = environment.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return default
    if value != value or value <= 0:  # NaN / 非正数
        return default
    if value < minimum:
        return minimum
    return min(value, maximum)


@dataclass(frozen=True, slots=True)
class AiPlanningConfig:
    """一次装配得到的**只读**配置快照。

    ⛔ `api_key` 永远不出现在 `describe()` 里，也⛔ 不被任何响应 / 日志引用。
    """

    enabled: bool
    api_key: str | None
    base_url: str
    model: str
    max_output_tokens: int
    request_timeout: float
    max_calls_per_request: int
    max_sessions: int
    adopt_ttl_seconds: int

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled 必须是布尔值。")
        if self.api_key is not None and not isinstance(self.api_key, str):
            raise TypeError("api_key 必须是字符串或 None。")
        for name in ("base_url", "model"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串。")

    @property
    def has_api_key(self) -> bool:
        """是否注入了非空密钥（⛔ 不暴露密钥本身）。"""

        return bool(self.api_key and self.api_key.strip())

    @property
    def live_model_available(self) -> bool:
        """真实在线模型是否**可能**被调用（开关打开 + 有密钥）。"""

        return self.enabled and self.has_api_key

    def describe(self) -> dict:
        """可安全暴露给响应 / 日志的配置摘要（⛔ 绝不含密钥取值）。"""

        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_configured": self.has_api_key,
            "max_output_tokens": self.max_output_tokens,
            "request_timeout_seconds": self.request_timeout,
            "max_calls_per_request": self.max_calls_per_request,
            "adopt_ttl_seconds": self.adopt_ttl_seconds,
        }


def load_config(environment: Mapping[str, str] | None = None) -> AiPlanningConfig:
    """从环境读取配置；缺省即**关闭**。"""

    env: Mapping[str, str] = os.environ if environment is None else environment
    raw_key = env.get(DEEPSEEK_API_KEY)
    api_key = raw_key.strip() if isinstance(raw_key, str) and raw_key.strip() else None
    base_url = env.get(DEEPSEEK_BASE_URL)
    model = env.get(DEEPSEEK_MODEL)
    return AiPlanningConfig(
        enabled=_flag(env, AI_PLANNING_ENABLED, default=False),
        api_key=api_key,
        base_url=(base_url or DEFAULT_BASE_URL).strip().rstrip("/"),
        model=(model or DEFAULT_MODEL).strip(),
        max_output_tokens=_bounded_int(
            env, AI_PLANNING_MAX_OUTPUT_TOKENS, default=DEFAULT_MAX_OUTPUT_TOKENS,
            minimum=1, maximum=MAX_ALLOWED_OUTPUT_TOKENS,
        ),
        request_timeout=_bounded_float(
            env, AI_PLANNING_REQUEST_TIMEOUT, default=DEFAULT_REQUEST_TIMEOUT,
            minimum=MIN_ALLOWED_REQUEST_TIMEOUT, maximum=MAX_ALLOWED_REQUEST_TIMEOUT,
        ),
        max_calls_per_request=_bounded_int(
            env, AI_PLANNING_MAX_CALLS_PER_REQUEST, default=DEFAULT_MAX_CALLS_PER_REQUEST,
            minimum=1, maximum=MAX_ALLOWED_CALLS_PER_REQUEST,
        ),
        max_sessions=_bounded_int(
            env, AI_PLANNING_MAX_SESSIONS, default=DEFAULT_MAX_SESSIONS,
            minimum=1, maximum=MAX_ALLOWED_SESSIONS,
        ),
        adopt_ttl_seconds=_bounded_int(
            env, AI_PLANNING_ADOPT_TTL_SECONDS, default=DEFAULT_ADOPT_TTL_SECONDS,
            minimum=1, maximum=MAX_ALLOWED_ADOPT_TTL,
        ),
    )
