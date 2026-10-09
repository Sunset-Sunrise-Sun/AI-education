"""AI Planning Controller 的领域错误与固定错误码。

设计原则（与既有模块一致）：

- ⛔ **不吞异常**：本模块只在自己**显式知道**的失败上抛这些类型，
  其它未预期异常（`ValueError` / `KeyError` / `TypeError` / `OSError` …）原样往上冒；
- ⛔ **错误文本不含密钥、Prompt 正文、学生原始对话或个人信息**；
- 每个错误都带一个**固定错误码**，供 API 层映射成有边界的 HTTP 状态码。
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ERROR_CODES",
    "AiPlanningError",
    "IntentNotConfirmableError",
    "IntentValidationError",
    "MessageRejectedError",
    "ModelCallBudgetExceededError",
    "ModelOutputInvalidError",
    "ModelUnavailableError",
    "PlanContextInvalidError",
    "SessionExpiredError",
    "SessionNotFoundError",
    "SolveUnsupportedError",
    "CandidateInvalidError",
    "AdoptionConflictError",
]

#: 全部对外错误码（`detail.error` 只会取这些值之一）。
ERROR_CODES: Final[tuple[str, ...]] = (
    "ai_planning_disabled",
    "ai_planning_model_unavailable",
    "ai_planning_message_rejected",
    "ai_planning_model_output_invalid",
    "ai_planning_intent_invalid",
    "ai_planning_intent_not_confirmable",
    "ai_planning_session_not_found",
    "ai_planning_session_expired",
    "ai_planning_plan_context_invalid",
    "ai_planning_solve_unsupported",
    "ai_planning_candidate_invalid",
    "ai_planning_budget_exceeded",
    "ai_planning_adoption_conflict",
)


class AiPlanningError(RuntimeError):
    """本模块**显式领域失败**的基类；带固定错误码与安全消息。"""

    code: str = "ai_planning_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ModelUnavailableError(AiPlanningError):
    """模型未启用 / 无密钥 / 网络或协议失败 ⇒ 明确不可用，⛔ 不伪造结果。"""

    code = "ai_planning_model_unavailable"


class MessageRejectedError(AiPlanningError):
    """用户消息本身不合规（空 / 超长 / 疑似包含个人信息）。"""

    code = "ai_planning_message_rejected"


class ModelOutputInvalidError(AiPlanningError):
    """模型输出不是合法 JSON、字段非法、含白名单外的课程 / 教学班。"""

    code = "ai_planning_model_output_invalid"


class IntentValidationError(AiPlanningError):
    """确认意图未通过本地校验（改写了事实、范围越界、学分无依据）。"""

    code = "ai_planning_intent_invalid"


class IntentNotConfirmableError(AiPlanningError):
    """意图仍有必须由用户消解的歧义 ⇒ 不允许进入求解。"""

    code = "ai_planning_intent_not_confirmable"


class SessionNotFoundError(AiPlanningError):
    """意图 / 候选不存在，或不属于本会话。"""

    code = "ai_planning_session_not_found"


class SessionExpiredError(AiPlanningError):
    """上下文指纹或候选有效性已过期 ⇒ fail closed。"""

    code = "ai_planning_session_expired"


class PlanContextInvalidError(AiPlanningError):
    """请求携带的方案上下文自相矛盾或不符合公共契约。"""

    code = "ai_planning_plan_context_invalid"


class SolveUnsupportedError(AiPlanningError):
    """当前冻结 Planner 无法表达该意图 ⇒ 明确 unsupported，⛔ 不硬造候选。"""

    code = "ai_planning_solve_unsupported"


class CandidateInvalidError(AiPlanningError):
    """候选未通过控制器的确定性校验（锁定课程被破坏 / 越界 / 白名单外）。"""

    code = "ai_planning_candidate_invalid"


class ModelCallBudgetExceededError(AiPlanningError):
    """单次请求或会话的模型调用 / 输出预算超限。"""

    code = "ai_planning_budget_exceeded"


class AdoptionConflictError(AiPlanningError):
    """采用请求与原方案不一致（重复采用 / 并发采用 / 指纹不符）。"""

    code = "ai_planning_adoption_conflict"
