"""DeepSeek（OpenAI 兼容）模型客户端 + 注入点协议。

```text
AiPlanningConfig + 最小化 messages
        ↓  DeepSeekChatClient（标准库 urllib，POST {base_url}/chat/completions）
        ↓  response_format={"type":"json_object"}
ModelAnswer（成功带 payload；失败带固定原因码）
```

## 边界（硬）

- ⛔ **不新增第三方依赖 / Agent 框架**：只用标准库 `urllib.request`；
- ⛔ **没有密钥就不发请求**：`DeepSeekChatClient` 在无密钥时直接返回
  `missing_api_key`，⛔ 绝不伪造一次"成功调用"；
- ⛔ **密钥不进日志 / 异常 / 响应**：错误信息只包含**固定原因码**；
- ⛔ **不重试**：超时 / 429 / 5xx 一律作为一次有界失败返回，
  由上层转成明确错误并保留原方案（避免放大成本与放大故障）；
- ✅ 响应体大小、输出 token 数、请求次数都由上层与配置共同设上限。

## 生成方式的三种取值（⛔ 只有这三种）

```text
deepseek_live   真实在线调用成功（唯一可以声称"已接入 DeepSeek"的取值）
test_double     注入的**测试替身**（假模型）；⛔ 绝不等于线上模型
unavailable     任何未成功的情况（未启用 / 无密钥 / 网络 / 协议 / 空输出）
```

## 错误原因码（固定，⛔ 不含任何取值）

```text
model_disabled        开关为关闭
missing_api_key       没有注入密钥
http_401 / 402 / 429  鉴权 / 余额 / 限流
http_5xx              服务端错误
http_other            其它非 2xx
timeout               请求超时
network_error         连接失败 / DNS / TLS
request_build_error   请求构造失败
response_too_large    响应体超过上限
invalid_json          响应不是 JSON，或 choices 结构不符
empty_content         模型返回空内容
```
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from app.ai_planning.config import AiPlanningConfig

__all__ = [
    "CLIENT_FAILURE_REASONS",
    "GENERATOR_DEEPSEEK_LIVE",
    "GENERATOR_TEST_DOUBLE",
    "GENERATOR_UNAVAILABLE",
    "GENERATOR_KINDS",
    "MAX_RESPONSE_BYTES",
    "DeepSeekChatClient",
    "IntentModel",
    "ModelAnswer",
    "estimate_tokens",
]

GENERATOR_DEEPSEEK_LIVE: Final[str] = "deepseek_live"
GENERATOR_TEST_DOUBLE: Final[str] = "test_double"
GENERATOR_UNAVAILABLE: Final[str] = "unavailable"

GENERATOR_KINDS: Final[tuple[str, ...]] = (
    GENERATOR_DEEPSEEK_LIVE, GENERATOR_TEST_DOUBLE, GENERATOR_UNAVAILABLE,
)

#: 客户端可能返回的失败原因码（仅 `DeepSeekChatClient` 使用）。
CLIENT_FAILURE_REASONS: Final[tuple[str, ...]] = (
    "model_disabled", "missing_api_key", "http_401", "http_402", "http_429",
    "http_5xx", "http_other", "timeout", "network_error", "request_build_error",
    "response_too_large", "invalid_json", "empty_content",
)

#: 单次模型响应体的字节上限（防止异常超大响应）。
MAX_RESPONSE_BYTES: Final[int] = 256 * 1024


def estimate_tokens(text: str) -> int:
    """**粗略** token 估算（用于预算与成本提示，⛔ 不是计费口径）。

    中英混排按"每 3 个字符约 1 token"的上界估算；
    响应里必须写明这是**估算**，不得当成账单数字。
    """

    if not isinstance(text, str):
        return 0
    return (len(text) + 2) // 3


@dataclass(frozen=True, slots=True)
class ModelAnswer:
    """一次模型调用的**有界**结果。"""

    generator_kind: str
    model_id: str
    payload: dict | None = None
    reason: str | None = None
    prompt_tokens_estimate: int = 0
    completion_tokens_estimate: int = 0

    def __post_init__(self) -> None:
        if self.generator_kind not in GENERATOR_KINDS:
            raise ValueError("generator_kind 取值非法。")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id 必须是非空字符串。")
        if self.generator_kind == GENERATOR_UNAVAILABLE:
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise ValueError("不可用结果必须带固定原因码。")
            if self.payload is not None:
                raise ValueError("不可用结果不得带 payload。")
        else:
            if not isinstance(self.payload, dict):
                raise ValueError("成功结果必须带 JSON 对象。")
            if self.reason is not None:
                raise ValueError("成功结果不得带失败原因。")
        for name in ("prompt_tokens_estimate", "completion_tokens_estimate"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} 必须是非负整数。")

    @property
    def ok(self) -> bool:
        return self.generator_kind in (GENERATOR_DEEPSEEK_LIVE, GENERATOR_TEST_DOUBLE)

    @property
    def is_live(self) -> bool:
        """是否**真实**在线调用成功（唯一可用于对外声称已接入的判据）。"""

        return self.generator_kind == GENERATOR_DEEPSEEK_LIVE

    @property
    def total_tokens_estimate(self) -> int:
        return self.prompt_tokens_estimate + self.completion_tokens_estimate


@runtime_checkable
class IntentModel(Protocol):
    """意图解析模型的**注入点**。

    实现方（真实客户端 / 测试假模型）必须：

    - ⛔ 不接收、不打印、不落盘任何学生个人信息（调用方已做最小化）；
    - 只返回 `ModelAnswer`，⛔ 不自行决定业务状态或方案；
    - ⛔ 不把 `api_key` 写进返回对象。
    """

    model_id: str

    def complete(self, messages: tuple[dict[str, str], ...]) -> ModelAnswer: ...


class DeepSeekChatClient:
    """标准库实现的 OpenAI 兼容 Chat Completions 客户端（**无可选依赖**）。

    ⛔ 无密钥 / 开关关闭 ⇒ 立即返回 `missing_api_key` / `model_disabled`，
    **不发任何网络请求**。
    """

    def __init__(self, config: AiPlanningConfig, *, opener=None) -> None:
        self._config = config
        self._opener = opener if opener is not None else urllib.request.urlopen

    @property
    def model_id(self) -> str:
        return self._config.model

    @property
    def config(self) -> AiPlanningConfig:
        return self._config

    def build_request(self, messages: tuple[dict[str, str], ...]) -> urllib.request.Request:
        """构造请求对象（可被测试单独校验；⛔ 不把密钥写进任何返回文本）。"""

        body = json.dumps(
            {
                "model": self._config.model,
                "messages": list(messages),
                "response_format": {"type": "json_object"},
                "max_tokens": self._config.max_output_tokens,
                "stream": False,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        return urllib.request.Request(
            url=f"{self._config.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                # ⚠️ 密钥只在这里出现；⛔ 不写日志、⛔ 不回显、⛔ 不进异常文本。
                "Authorization": f"Bearer {self._config.api_key or ''}",
                "Accept": "application/json",
            },
        )

    def complete(self, messages: tuple[dict[str, str], ...]) -> ModelAnswer:
        """执行一次有界调用；任何失败都返回固定原因码，⛔ 不抛出、⛔ 不重试。"""

        prompt_estimate = sum(estimate_tokens(item.get("content", "")) for item in messages)
        if not self._config.enabled:
            return self._fail("model_disabled", prompt_estimate)
        if not self._config.has_api_key:
            return self._fail("missing_api_key", prompt_estimate)

        try:
            request = self.build_request(messages)
        except (TypeError, ValueError, OSError):
            return self._fail("request_build_error", prompt_estimate)

        try:
            with self._opener(request, timeout=self._config.request_timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            code = getattr(exc, "code", None)
            try:
                exc.close()
            except Exception:  # noqa: BLE001 - 关闭失败不影响错误映射
                pass
            if code in (401, 403):
                return self._fail("http_401", prompt_estimate)
            if code == 402:
                return self._fail("http_402", prompt_estimate)
            if code == 429:
                return self._fail("http_429", prompt_estimate)
            if isinstance(code, int) and 500 <= code < 600:
                return self._fail("http_5xx", prompt_estimate)
            return self._fail("http_other", prompt_estimate)
        except (TimeoutError, socket.timeout):
            return self._fail("timeout", prompt_estimate)
        except urllib.error.URLError:
            return self._fail("network_error", prompt_estimate)
        except (OSError, ValueError):
            return self._fail("network_error", prompt_estimate)

        if len(raw) > MAX_RESPONSE_BYTES:
            return self._fail("response_too_large", prompt_estimate)

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._fail("invalid_json", prompt_estimate)

        content = self._extract_content(parsed)
        if content is None:
            return self._fail("invalid_json", prompt_estimate)
        if not content.strip():
            return self._fail("empty_content", prompt_estimate)

        try:
            payload = json.loads(content)
        except ValueError:
            return self._fail("invalid_json", prompt_estimate)
        if not isinstance(payload, dict):
            return self._fail("invalid_json", prompt_estimate)

        return ModelAnswer(
            generator_kind=GENERATOR_DEEPSEEK_LIVE,
            model_id=self._config.model,
            payload=payload,
            prompt_tokens_estimate=prompt_estimate,
            completion_tokens_estimate=estimate_tokens(content),
        )

    @staticmethod
    def _extract_content(parsed: object) -> str | None:
        """从 OpenAI 兼容响应里取出第一条 `choices[0].message.content`。"""

        if not isinstance(parsed, dict):
            return None
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        message = first.get("message")
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        return content if isinstance(content, str) else None

    def _fail(self, reason: str, prompt_estimate: int) -> ModelAnswer:
        return ModelAnswer(
            generator_kind=GENERATOR_UNAVAILABLE,
            model_id=self._config.model,
            reason=reason,
            prompt_tokens_estimate=prompt_estimate,
        )
