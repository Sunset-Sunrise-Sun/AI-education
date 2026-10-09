"""AI Planning Controller：DeepSeek 意图解析 + 受控 Planner 求解（**私有模块**）。

```text
用户自然语言
      ↓  interpret()   DeepSeek（OpenAI 兼容）只输出结构化**意图草稿**
用户确认意图
      ↓  solve()       后端把已确认意图翻成既有四参数 Planner 的输入，并复核候选
用户二次确认
      ↓  adopt()       绑定方案指纹的采用；过期 / 不符 ⇒ fail closed
```

## 边界（硬）

- ⛔ 不修改 `/schemas/`、`/docs/interfaces/`、`AGENTS.md` 与任何既有路由；
- ⛔ 不修改冻结的 `PlannerProvider.plan(makeup_tasks, offerings, current_schedule, preference)`；
- ⛔ 不新增第三方依赖 / Agent 框架；模型走标准库 `urllib` 调用 OpenAI 兼容接口；
- ⛔ 模型输出**永远**不能直接成为 `PlanResult`：候选只由受控 Planner 产生，
  且服务端会再做一次确定性复核（学分 / 时间 / 周次 / 锁定课程 / 数据来源）；
- ⛔ 没有密钥就不假装真实调用：`generator_kind` 只有
  `deepseek_live` / `test_double` / `unavailable` 三种取值；
- ⛔ 未确认意图不求解，未二次确认不采用，拒绝 / 超时 / 出错时原方案完全不变。

## 输入

只接受现有已验证对象：`MakeupTask` / `PlanResult` / `Preference` / `CourseOffering`
以及选中的方案上下文（学期）。⛔ 不接受成绩单 / 姓名 / 学号等个人信息字段。
"""

from __future__ import annotations

from app.ai_planning.config import AiPlanningConfig, load_config
from app.ai_planning.context import PlanningContext, build_context
from app.ai_planning.deepseek_client import (
    GENERATOR_DEEPSEEK_LIVE,
    GENERATOR_TEST_DOUBLE,
    GENERATOR_UNAVAILABLE,
    DeepSeekChatClient,
    IntentModel,
    ModelAnswer,
)
from app.ai_planning.errors import (
    ERROR_CODES,
    AdoptionConflictError,
    AiPlanningError,
    CandidateInvalidError,
    IntentNotConfirmableError,
    IntentValidationError,
    MessageRejectedError,
    ModelCallBudgetExceededError,
    ModelOutputInvalidError,
    ModelUnavailableError,
    PlanContextInvalidError,
    SessionExpiredError,
    SessionNotFoundError,
    SolveUnsupportedError,
)
from app.ai_planning.fake_model import (
    RuleFakeIntentModel,
    ScriptedIntentModel,
    UnavailableIntentModel,
)
from app.ai_planning.intent import (
    ADJUSTMENT_SCOPE_CURRENT_SEMESTER,
    ADJUSTMENT_SCOPE_UNSUPPORTED,
    AMBIGUITY_CODES,
    Ambiguity,
    ConfirmedIntent,
    HardConstraint,
    IntentDraft,
    LockedCourse,
    SoftPreference,
    parse_intent_draft,
    validate_confirmed_intent,
)
from app.ai_planning.service import (
    ADOPTED,
    BLOCKED,
    CANDIDATE_READY,
    INTENT_CONFIRMED,
    INTENT_DRAFT,
    NO_FEASIBLE_CANDIDATE,
    PLAN_KIND_NO_CANDIDATE,
    PLAN_KIND_PLAN_RESULT,
    REJECTED,
    AiPlanningService,
    CandidateDiff,
    CandidateRecord,
    IntentRecord,
    ModelCallBudget,
    SessionStore,
    SolveOutcome,
    compute_candidate_diff,
)

__all__ = [
    "ADJUSTMENT_SCOPE_CURRENT_SEMESTER",
    "ADJUSTMENT_SCOPE_UNSUPPORTED",
    "ADOPTED",
    "AMBIGUITY_CODES",
    "AiPlanningConfig",
    "AiPlanningError",
    "AiPlanningService",
    "Ambiguity",
    "BLOCKED",
    "CANDIDATE_READY",
    "CandidateDiff",
    "CandidateRecord",
    "ConfirmedIntent",
    "DeepSeekChatClient",
    "ERROR_CODES",
    "GENERATOR_DEEPSEEK_LIVE",
    "GENERATOR_TEST_DOUBLE",
    "GENERATOR_UNAVAILABLE",
    "HardConstraint",
    "INTENT_CONFIRMED",
    "INTENT_DRAFT",
    "IntentDraft",
    "IntentModel",
    "IntentRecord",
    "LockedCourse",
    "ModelAnswer",
    "ModelCallBudget",
    "NO_FEASIBLE_CANDIDATE",
    "PLAN_KIND_NO_CANDIDATE",
    "PLAN_KIND_PLAN_RESULT",
    "PlanningContext",
    "REJECTED",
    "RuleFakeIntentModel",
    "ScriptedIntentModel",
    "SessionStore",
    "SoftPreference",
    "SolveOutcome",
    "UnavailableIntentModel",
    "build_context",
    "compute_candidate_diff",
    "load_config",
    "parse_intent_draft",
    "validate_confirmed_intent",
]

# 显式重导出错误类型（`__all__` 之外的可用面刻意保持最小）。
_ERROR_TYPES = (
    AdoptionConflictError,
    CandidateInvalidError,
    IntentNotConfirmableError,
    IntentValidationError,
    MessageRejectedError,
    ModelCallBudgetExceededError,
    ModelOutputInvalidError,
    ModelUnavailableError,
    PlanContextInvalidError,
    SessionExpiredError,
    SessionNotFoundError,
    SolveUnsupportedError,
)
