"""**注入式假模型**：无密钥也能端到端测试控制器。

这些实现只用于测试与本地联调。它们的关键作用是让"意图解析 → 用户确认 →
受控求解 → 二次确认采用"整条链路在没有真实密钥时也能被完整验证，同时
**诚实标注**：它们返回 `generator_kind = test_double`，
⛔ **绝不**是 `deepseek_live`，因此不能被说成"已接入 DeepSeek"。

包含三类假模型：

- `RuleFakeIntentModel`：按关键词做**确定性**解析，覆盖常见意图；
- `ScriptedIntentModel`：按脚本依次返回原始 JSON（可注入非法 / 空 / 幻觉课程号输出）；
- `UnavailableIntentModel`：永远返回固定失败原因，用于验证模型不可用路径。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Final, Sequence

from app.ai_planning.deepseek_client import (
    GENERATOR_TEST_DOUBLE,
    GENERATOR_UNAVAILABLE,
    ModelAnswer,
    estimate_tokens,
)

__all__ = [
    "RuleFakeIntentModel",
    "ScriptedIntentModel",
    "UnavailableIntentModel",
]

_COURSE_CODE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z]{2,}[A-Za-z0-9_-]*\d")
_EXPLICIT_CREDIT: Final[re.Pattern[str]] = re.compile(r"(\d{1,2}(?:\.\d)?)\s*学分")
_WEEKDAY_CN: Final[dict[str, int]] = {
    "周一": 1, "周二": 2, "周三": 3, "周四": 4, "周五": 5, "周六": 6, "周日": 7,
}
_WEEKDAY_EN: Final[dict[str, int]] = {
    "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5,
    "saturday": 6, "sunday": 7,
}
_FUTURE_MARKERS: Final[tuple[str, ...]] = (
    "下学期", "下个学期", "未来学期", "大三", "大四", "明年",
)
_KEEP_MARKERS: Final[tuple[str, ...]] = (
    "必须保留", "一定要保留", "不能动", "不许动", "保留", "锁",
)
_TIRED_MARKERS: Final[tuple[str, ...]] = (
    "太累", "轻松", "少上", "减少", "降低", "压力",
)


def _extract_credit(text: str) -> float | None:
    match = _EXPLICIT_CREDIT.search(text)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_weekday(text: str) -> int | None:
    for token, value in _WEEKDAY_CN.items():
        if token in text:
            return value
    lowered = text.lower()
    for token, value in _WEEKDAY_EN.items():
        if token in lowered:
            return value
    return None


def _extract_mentioned_courses(
    text: str, known: Sequence[str], aliases: dict[str, str] | None = None
) -> list[str]:
    """只保留**上下文里真实存在**的课程号（⛔ 不发明课程）。

    - 课程号字面出现（`DS101`）→ 直接命中；
    - 课程别名（例如中文名）出现 → 通过测试替身自己的映射命中。
    """

    mentioned: list[str] = []
    for token in _COURSE_CODE.findall(text):
        for known_id in known:
            if token.upper() == known_id.upper() and known_id not in mentioned:
                mentioned.append(known_id)
    for known_id in known:
        if known_id in text and known_id not in mentioned:
            mentioned.append(known_id)
    for alias, course_id in (aliases or {}).items():
        if alias and alias in text and course_id in known and course_id not in mentioned:
            mentioned.append(course_id)
    return mentioned


@dataclass
class RuleFakeIntentModel:
    """确定性的关键词解析假模型（测试与本地联调用）。

    `course_aliases` 用来模拟"真实模型能认出课程中文名"这件事：
    它是**测试替身自己的**映射，⛔ 与业务认定无关，也⛔ 不会被写进任何响应。
    """

    model_id: str = "test-rule-fake"
    known_course_ids: tuple[str, ...] = ()
    known_class_by_course: dict[str, str] = field(default_factory=dict)
    course_aliases: dict[str, str] = field(default_factory=dict)
    fail_reason: str | None = None

    def complete(self, messages: tuple[dict[str, str], ...]) -> ModelAnswer:
        prompt = " ".join(item.get("content", "") for item in messages)
        prompt_tokens = estimate_tokens(prompt)
        if self.fail_reason is not None:
            return ModelAnswer(
                generator_kind=GENERATOR_UNAVAILABLE, model_id=self.model_id,
                reason=self.fail_reason, prompt_tokens_estimate=prompt_tokens,
            )
        payload = self.parse(prompt)
        content = json.dumps(payload, ensure_ascii=False)
        return ModelAnswer(
            generator_kind=GENERATOR_TEST_DOUBLE,
            model_id=self.model_id,
            payload=payload,
            prompt_tokens_estimate=prompt_tokens,
            completion_tokens_estimate=estimate_tokens(content),
        )

    def parse(self, prompt: str) -> dict:
        """纯函数式解析：便于测试直接断言"意图长什么样"。"""

        student_text = _student_message(prompt)
        context = _context_payload(prompt)
        hard: list[dict] = []
        soft: list[dict] = []
        locked: list[dict] = []

        credit = _extract_credit(student_text)
        if credit is not None:
            hard.append({
                "kind": "max_credit_limit", "value": credit,
                "evidence": "学生在消息中明确给出了学分数字",
            })
        elif any(marker in student_text for marker in _TIRED_MARKERS):
            # ⚠️ 刻意**不**把"太累 / 少上一点"换算成数字：由本地校验标成歧义。
            soft.append({
                "kind": "prefer_fewer_credits", "value": None,
                "note": "学生表达了降低负荷的意愿，但未给出学分数字",
            })

        weekday = _extract_weekday(student_text)
        if weekday is not None:
            soft.append({
                "kind": "avoid_weekday", "value": weekday, "note": f"尽量避开周{weekday}",
            })

        if any(marker in student_text for marker in _KEEP_MARKERS):
            mentioned = _extract_mentioned_courses(
                student_text, self.known_course_ids, self.course_aliases
            )
            if mentioned:
                soft.append({
                    "kind": "prefer_keep_prerequisites", "value": None,
                    "note": "学生要求保留指定课程",
                })
            for course_id in mentioned:
                class_id = self.known_class_by_course.get(course_id)
                if class_id is not None:
                    locked.append({
                        "course_id": course_id, "class_id": class_id,
                        "reason": "学生明确要求保留该课程",
                    })

        scope = (
            "future_semesters"
            if any(marker in student_text for marker in _FUTURE_MARKERS)
            else "current_semester"
        )
        return {
            "summary": student_text.strip()[:60] or "学生未提供明确内容",
            "scope": scope,
            "target_semester": context.get("semester"),
            "hard_constraints": hard,
            "soft_preferences": soft,
            "locked_courses": locked,
            "confidence": 0.6,
            "notes": [],
        }


@dataclass
class ScriptedIntentModel:
    """按脚本依次返回**原始 JSON 文本**的假模型。

    `script` 的每一项是模型"返回的 JSON 文本"；
    非法 JSON、空对象、幻觉课程号都可以直接写进脚本，
    用来验证服务层的 fail-closed 行为。
    """

    script: tuple[str, ...]
    model_id: str = "test-scripted-fake"
    repeat_last: bool = True
    _index: int = 0

    def complete(self, messages: tuple[dict[str, str], ...]) -> ModelAnswer:
        prompt = " ".join(item.get("content", "") for item in messages)
        prompt_tokens = estimate_tokens(prompt)
        if not self.script:
            return ModelAnswer(
                generator_kind=GENERATOR_UNAVAILABLE, model_id=self.model_id,
                reason="script_exhausted", prompt_tokens_estimate=prompt_tokens,
            )
        if self._index >= len(self.script):
            if not self.repeat_last:
                return ModelAnswer(
                    generator_kind=GENERATOR_UNAVAILABLE, model_id=self.model_id,
                    reason="script_exhausted", prompt_tokens_estimate=prompt_tokens,
                )
            raw = self.script[-1]
        else:
            raw = self.script[self._index]
            self._index += 1

        parsed: dict | None
        try:
            candidate = json.loads(raw)
        except ValueError:
            candidate = None
        parsed = candidate if isinstance(candidate, dict) else None
        if parsed is None:
            # 非法 / 非对象输出：以"不可用 + 固定原因"表达，由服务层转成明确错误。
            return ModelAnswer(
                generator_kind=GENERATOR_UNAVAILABLE, model_id=self.model_id,
                reason="invalid_json", prompt_tokens_estimate=prompt_tokens,
            )
        return ModelAnswer(
            generator_kind=GENERATOR_TEST_DOUBLE,
            model_id=self.model_id,
            payload=parsed,
            prompt_tokens_estimate=prompt_tokens,
            completion_tokens_estimate=estimate_tokens(raw),
        )


@dataclass
class UnavailableIntentModel:
    """永远失败的假模型（验证无密钥 / 401 / 超时 / 空输出等不可用路径）。"""

    reason: str = "missing_api_key"
    model_id: str = "test-unavailable-fake"

    def complete(self, messages: tuple[dict[str, str], ...]) -> ModelAnswer:
        prompt = " ".join(item.get("content", "") for item in messages)
        return ModelAnswer(
            generator_kind=GENERATOR_UNAVAILABLE, model_id=self.model_id,
            reason=self.reason, prompt_tokens_estimate=estimate_tokens(prompt),
        )


def _student_message(prompt: str) -> str:
    match = re.search(r"<student_message>\s*(.*?)\s*</student_message>", prompt, re.S)
    return match.group(1) if match else prompt


def _context_payload(prompt: str) -> dict:
    match = re.search(r"<context>\s*(.*?)\s*</context>", prompt, re.S)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1))
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
