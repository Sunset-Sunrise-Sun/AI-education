"""DeepSeek 客户端测试：**不发真实网络请求**（用注入的 opener 模拟传输层）。

覆盖：

- 无密钥 / 开关关闭时**不发请求**；
- OpenAI 兼容请求体的形状（model / messages / json_object / max_tokens）；
- 401 / 402 / 429 / 5xx / 超时 / 网络错误 / 超大响应 / 非法 JSON / 空内容
  全部映射成**固定原因码**，⛔ 不抛出、⛔ 不重试、⛔ 不泄漏密钥；
- 成功时 `generator_kind = deepseek_live`（这是唯一允许声称"已接入"的取值）。

⚠️ 这些测试**不能**证明真实 DeepSeek 在线可用：它们只证明客户端在有界输入下的行为。
真实在线调用状态在本轮报告中记为 **NOT VERIFIED**（没有密钥）。
"""

from __future__ import annotations

import io
import json
import socket
import urllib.error

import pytest

from app.ai_planning.config import AiPlanningConfig, load_config
from app.ai_planning.deepseek_client import (
    CLIENT_FAILURE_REASONS,
    GENERATOR_DEEPSEEK_LIVE,
    GENERATOR_UNAVAILABLE,
    MAX_RESPONSE_BYTES,
    DeepSeekChatClient,
    estimate_tokens,
)


def make_config(
    *,
    enabled: bool = True,
    api_key: str | None = "test-placeholder-key",
    model: str = "deepseek-flash",
    base_url: str = "https://api.deepseek.com",
) -> AiPlanningConfig:
    return AiPlanningConfig(
        enabled=enabled, api_key=api_key, base_url=base_url, model=model,
        max_output_tokens=1200, request_timeout=5.0, max_calls_per_request=3,
        max_sessions=10, adopt_ttl_seconds=60,
    )


class FakeResponse(io.BytesIO):
    def __enter__(self):  # pragma: no cover - 与 urlopen 的上下文协议一致
        return self

    def __exit__(self, *args) -> None:
        self.close()


class RecordingOpener:
    """记录调用并返回预置响应 / 抛出预置异常。"""

    def __init__(self, *, payload: bytes = b"", error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[tuple[object, float]] = []

    def __call__(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return FakeResponse(self.payload)


def ok_body(content: str) -> bytes:
    return json.dumps({
        "id": "chatcmpl-mock",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }).encode("utf-8")


Messages = ({"role": "system", "content": "sys"}, {"role": "user", "content": "hello"})


# --------------------------------------------------------------------------- #
# 不调用
# --------------------------------------------------------------------------- #

def test_disabled_config_never_sends_a_request():
    opener = RecordingOpener(payload=ok_body("{}"))
    client = DeepSeekChatClient(make_config(enabled=False), opener=opener)
    result = client.complete(Messages)
    assert result.generator_kind == GENERATOR_UNAVAILABLE
    assert result.reason == "model_disabled"
    assert opener.calls == []


def test_missing_api_key_never_sends_a_request():
    opener = RecordingOpener(payload=ok_body("{}"))
    client = DeepSeekChatClient(make_config(api_key=None), opener=opener)
    result = client.complete(Messages)
    assert result.reason == "missing_api_key"
    assert opener.calls == []


def test_blank_api_key_is_treated_as_missing():
    opener = RecordingOpener(payload=ok_body("{}"))
    client = DeepSeekChatClient(make_config(api_key="   "), opener=opener)
    assert client.complete(Messages).reason == "missing_api_key"
    assert opener.calls == []


# --------------------------------------------------------------------------- #
# 请求形状
# --------------------------------------------------------------------------- #

def test_request_shape_is_openai_compatible_and_json_mode():
    client = DeepSeekChatClient(make_config())
    request = client.build_request(Messages)
    assert request.method == "POST"
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    body = json.loads(request.data.decode("utf-8"))
    assert body["model"] == "deepseek-flash"
    assert body["messages"] == list(Messages)
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 1200
    assert body["stream"] is False


def test_base_url_trailing_slash_is_normalized():
    config = load_config({"DEEPSEEK_BASE_URL": "https://api.deepseek.com/"})
    assert config.base_url == "https://api.deepseek.com"


def test_config_describe_never_contains_the_key():
    config = make_config(api_key="super-secret-value")
    described = json.dumps(config.describe(), ensure_ascii=False)
    assert "super-secret-value" not in described
    assert config.describe()["api_key_configured"] is True


def test_client_passes_timeout_and_does_not_retry():
    opener = RecordingOpener(error=urllib.error.URLError("boom"))
    client = DeepSeekChatClient(make_config(), opener=opener)
    result = client.complete(Messages)
    assert result.reason == "network_error"
    assert len(opener.calls) == 1          # ⛔ 不重试
    assert opener.calls[0][1] == 5.0       # 超时来自配置


# --------------------------------------------------------------------------- #
# 失败映射（固定原因码）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code,expected", [
    (401, "http_401"), (403, "http_401"), (402, "http_402"),
    (429, "http_429"), (500, "http_5xx"), (503, "http_5xx"), (400, "http_other"),
])
def test_http_errors_map_to_fixed_reasons(code, expected):
    error = urllib.error.HTTPError(
        url="https://api.deepseek.com/chat/completions", code=code,
        msg="err", hdrs=None, fp=io.BytesIO(b""),
    )
    opener = RecordingOpener(error=error)
    client = DeepSeekChatClient(make_config(), opener=opener)
    result = client.complete(Messages)
    assert result.reason == expected
    assert result.generator_kind == GENERATOR_UNAVAILABLE


def test_timeout_maps_to_timeout():
    opener = RecordingOpener(error=socket.timeout("slow"))
    client = DeepSeekChatClient(make_config(), opener=opener)
    assert client.complete(Messages).reason == "timeout"


@pytest.mark.parametrize("payload,expected", [
    (b"", "invalid_json"),
    (b"not json at all", "invalid_json"),
    (b"{}", "invalid_json"),
    (b'{"choices": []}', "invalid_json"),
    (b'{"choices": [{"message": {"content": "   "}}]}', "empty_content"),
    (b'{"choices": [{"message": {"content": "not-json"}}]}', "invalid_json"),
    (b'{"choices": [{"message": {"content": "[1,2,3]"}}]}', "invalid_json"),
])
def test_malformed_responses_map_to_fixed_reasons(payload, expected):
    opener = RecordingOpener(payload=payload)
    client = DeepSeekChatClient(make_config(), opener=opener)
    result = client.complete(Messages)
    assert result.reason == expected


def test_oversized_response_is_rejected_before_parsing():
    opener = RecordingOpener(payload=b"x" * (MAX_RESPONSE_BYTES + 10))
    client = DeepSeekChatClient(make_config(), opener=opener)
    assert client.complete(Messages).reason == "response_too_large"


def test_all_failure_reasons_are_in_the_declared_set():
    empty = lambda: RecordingOpener(payload=b"")  # noqa: E731 - 测试本地简写
    reasons = {
        DeepSeekChatClient(make_config(enabled=False), opener=empty()).complete(
            Messages
        ).reason,
        DeepSeekChatClient(make_config(api_key=None), opener=empty()).complete(
            Messages
        ).reason,
        DeepSeekChatClient(
            make_config(), opener=RecordingOpener(error=socket.timeout())
        ).complete(Messages).reason,
        DeepSeekChatClient(
            make_config(), opener=RecordingOpener(error=urllib.error.URLError("x"))
        ).complete(Messages).reason,
        DeepSeekChatClient(
            make_config(), opener=RecordingOpener(payload=b"bad")
        ).complete(Messages).reason,
        DeepSeekChatClient(
            make_config(),
            opener=RecordingOpener(payload=b'{"choices":[{"message":{"content":""}}]}'),
        ).complete(Messages).reason,
        DeepSeekChatClient(
            make_config(), opener=RecordingOpener(payload=b"x" * (MAX_RESPONSE_BYTES + 1))
        ).complete(Messages).reason,
    }
    assert reasons <= set(CLIENT_FAILURE_REASONS)


# --------------------------------------------------------------------------- #
# 成功
# --------------------------------------------------------------------------- #

def test_successful_call_is_marked_as_live_with_estimates():
    content = json.dumps({"summary": "学生想降低负荷", "scope": "current_semester"})
    opener = RecordingOpener(payload=ok_body(content))
    client = DeepSeekChatClient(make_config(), opener=opener)
    result = client.complete(Messages)
    assert result.generator_kind == GENERATOR_DEEPSEEK_LIVE
    assert result.is_live is True
    assert result.payload == {"summary": "学生想降低负荷", "scope": "current_semester"}
    assert result.reason is None
    assert result.prompt_tokens_estimate > 0
    assert result.completion_tokens_estimate == estimate_tokens(content)


def test_error_text_never_contains_the_api_key():
    error = urllib.error.HTTPError(
        url="https://api.deepseek.com/chat/completions", code=401,
        msg="unauthorized", hdrs=None, fp=io.BytesIO(b""),
    )
    client = DeepSeekChatClient(make_config(api_key="super-secret-value"), opener=RecordingOpener(error=error))
    result = client.complete(Messages)
    assert "super-secret-value" not in json.dumps(result.reason or "")


def test_estimate_tokens_is_bounded_and_monotonic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") >= 1
    assert estimate_tokens("a" * 300) > estimate_tokens("a" * 30)
