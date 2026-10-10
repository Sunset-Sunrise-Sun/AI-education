"""AI Planning 私有路由：`/api/v1/ai-planning/*`（**新增**，⛔ 不覆盖任何旧路由）。

```text
GET  /api/v1/ai-planning/status
POST /api/v1/ai-planning/interpret   → 结构化意图草稿（**不求解、不改方案**）
POST /api/v1/ai-planning/solve       → 仅对已确认意图生成候选（受控 Planner）
POST /api/v1/ai-planning/adopt       → 二次确认的采用 / 拒绝（绑定方案指纹）
```

## 边界（硬）

- ⛔ 不修改 `/api/v1/plan`、`/api/v1/mock/*`、`/api/v1/personal-planning/*`、
  `/api/v1/explanation/*` 的任何行为或契约；
- ⛔ 不新增 / 不修改 `/schemas/*.schema.json` 与 `/docs/interfaces/`：
  本文件里的请求 / 响应模型都是**这个模块自己的私有包络**；
- ⛔ 请求体只接受公共对象（`MakeupTask` / `PlanResult` / `Preference` / `CourseOffering`）
  与最小方案上下文；`extra="forbid"` 让成绩单 / 姓名 / 学号等额外字段直接 422；
- ⛔ 原方案在任何失败路径上都不变：候选是**新对象**，只有 `adopt` 才推进版本；
- ✅ `data_source` / `generator_kind` / `adopted_version_scope` 如实标注，
  ⛔ 不把测试替身说成真实 DeepSeek，也⛔ 不把 Mock 教学班说成真实教务数据。
"""

from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.ai_planning import (
    ADJUSTMENT_SCOPE_CURRENT_SEMESTER,
    AiPlanningError,
    AiPlanningService,
    PlanningContext,
    build_context,
)
from app.ai_planning.errors import PlanContextInvalidError
from app.models.contracts import CourseOffering, MakeupTask, PlanResult, Preference
from app.services.ai_planning_runtime import get_ai_planning_service

router = APIRouter(prefix="/ai-planning", tags=["ai-planning"])

#: `generator_kind` 的固定取值（⛔ 只有这三种）。
_GENERATOR_KINDS = ("deepseek_live", "test_double", "unavailable")

#: 错误码 → HTTP 状态码（⛔ 全部有边界，⛔ 不出现 500 兜底）。
_STATUS_BY_ERROR: dict[str, int] = {
    "ai_planning_disabled": status.HTTP_503_SERVICE_UNAVAILABLE,
    "ai_planning_model_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "ai_planning_message_rejected": status.HTTP_400_BAD_REQUEST,
    "ai_planning_model_output_invalid": 422,
    "ai_planning_intent_invalid": 422,
    "ai_planning_intent_not_confirmable": 409,
    "ai_planning_session_not_found": status.HTTP_404_NOT_FOUND,
    "ai_planning_session_expired": status.HTTP_410_GONE,
    "ai_planning_plan_context_invalid": 422,
    "ai_planning_solve_unsupported": 501,
    "ai_planning_candidate_invalid": 502,
    "ai_planning_budget_exceeded": 429,
    "ai_planning_adoption_conflict": status.HTTP_409_CONFLICT,
}


def _reject(code: str, message: str) -> None:
    raise HTTPException(
        status_code=_STATUS_BY_ERROR.get(code, 400),
        detail={"error": code, "message": message},
    )


def _require_enabled(service: AiPlanningService) -> None:
    if not service.config.enabled:
        _reject(
            "ai_planning_disabled",
            "AI 规划控制器未启用（AI_PLANNING_ENABLED 未打开）；"
            "本次不解析意图，也不会回退到任何演示模型。",
        )


def _translate(exc: AiPlanningError) -> NoReturn:
    """把领域错误翻译成有边界的 HTTP 错误（⛔ 不吞、⛔ 不兜底成 500）。"""

    code = exc.code if exc.code in _STATUS_BY_ERROR else "ai_planning_intent_invalid"
    _reject(code, exc.message)
    raise AssertionError("unreachable")  # pragma: no cover - _reject 一定抛出


# --------------------------------------------------------------------------- #
# 请求 / 响应包络（本模块私有）
# --------------------------------------------------------------------------- #

class PlanContextBody(BaseModel):
    """最小方案上下文：只允许公共对象与学期。"""

    model_config = ConfigDict(extra="forbid")

    semester: str = Field(min_length=1)
    base_plan: PlanResult
    makeup_tasks: list[MakeupTask] = Field(default_factory=list)
    course_offerings: list[CourseOffering] = Field(default_factory=list)
    preference: Preference = Field(default_factory=Preference)


class InterpretRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: PlanContextBody
    user_message: str = Field(min_length=1)


class InterpretResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    plan_digest: str
    parsed_intent: dict[str, Any]
    ambiguities: list[dict[str, Any]]
    data_source: str
    #: ⚠️ **新增**：服务端是否有**独立批准依据**证明上下文教学班确已核验。
    #:
    #: AI 接口的教学班来自请求体，因此这里**永远是 `False`**：
    #: 请求方自述 `data_source=real` ⛔ 不能换来"已核验"的说法。
    #: 前端凭此区分"HTTP 请求成功"与"使用了已核验真实教务数据"。
    context_source_verified: bool
    generator_kind: str
    generator_note: str
    model_id: str
    can_confirm: bool
    state: str
    token_usage_estimate: dict[str, int]
    message: str


class SolveRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(min_length=8)
    plan_digest: str = Field(min_length=64, max_length=64)
    confirmed_intent: dict[str, Any]


class SolveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None
    status: str
    plan_kind: str
    candidate_plan: dict[str, Any] | None
    diff: dict[str, Any] | None
    risks: list[str]
    unresolved: list[str]
    message: str
    blocked_reason: str | None
    data_source: str
    generator_kind: str
    plan_digest: str


class AdoptRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=8)
    plan_digest: str = Field(min_length=64, max_length=64)
    accept: bool


class AdoptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    accepted: bool
    state: str
    adopted_version: int
    adopted_version_scope: str
    original_plan_unchanged: bool
    plan_digest: str
    message: str


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    live_model_available: bool
    api_key_configured: bool
    model: str
    base_url: str
    max_calls_per_request: int
    request_timeout_seconds: float
    adopt_ttl_seconds: int
    generator_kind_when_live: str
    data_source_note: str


# --------------------------------------------------------------------------- #
# 依赖
# --------------------------------------------------------------------------- #

ServiceDep = Annotated[AiPlanningService, Depends(get_ai_planning_service)]


def _context_of(body: PlanContextBody) -> PlanningContext:
    try:
        return build_context(
            semester=body.semester,
            base_plan=body.base_plan,
            makeup_tasks=body.makeup_tasks,
            offerings=body.course_offerings,
            preference=body.preference,
            # ⚠️ **硬编码 False**：AI 接口的教学班**全部来自请求体**，
            # 服务端没有任何独立批准依据，因此这里永远不能声称"来源已核验"。
            # ⛔ 请求方无法通过任何字段把这一档打开（`source_verified` 不在请求模型里，
            # 且请求模型是 `extra="forbid"`）。
            source_verified=False,
        )
    except PlanContextInvalidError as exc:
        _translate(exc)


def _intent_payload(draft, ambiguities) -> dict[str, Any]:
    return {
        "summary": draft.summary,
        "scope": draft.scope,
        "target_semester": draft.target_semester,
        "hard_constraints": [
            {"kind": item.kind, "value": item.value, "evidence": item.evidence}
            for item in draft.hard_constraints
        ],
        "soft_preferences": [
            {"kind": item.kind, "value": item.value, "note": item.note}
            for item in draft.soft_preferences
        ],
        "locked_courses": [
            {"course_id": item.course_id, "class_id": item.class_id, "reason": item.reason}
            for item in draft.locked_courses
        ],
        "confidence": draft.confidence,
        "notes": list(draft.notes),
        "ambiguities": [
            {"code": item.code, "question": item.question, "detail": item.detail}
            for item in ambiguities
        ],
    }


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #

@router.get(
    "/status",
    response_model=StatusResponse,
    summary="AI 规划控制器的可用状态（⛔ 不暴露密钥）",
)
def read_status(service: ServiceDep) -> StatusResponse:
    """如实报告"真实在线模型是否可能可用"，供前端展示未启用态。"""

    config = service.config
    return StatusResponse(
        enabled=config.enabled,
        live_model_available=config.live_model_available,
        api_key_configured=config.has_api_key,
        model=config.model,
        base_url=config.base_url,
        max_calls_per_request=config.max_calls_per_request,
        request_timeout_seconds=config.request_timeout,
        adopt_ttl_seconds=config.adopt_ttl_seconds,
        generator_kind_when_live="deepseek_live",
        data_source_note=(
            "上下文 data_source 由教学班自身的 data_source 判定（mock / real / mixed / unknown）；"
            "没有教学班输入时为 unknown，⛔ 不默认成 real。"
        ),
    )


@router.post(
    "/interpret",
    response_model=InterpretResponse,
    summary="把自然语言解析成结构化意图草稿（只读，不求解）",
    description=(
        "DeepSeek（或注入的测试替身）只输出严格 JSON 意图草稿，"
        "服务端做枚举 / 白名单 / 学分依据校验后返回。\n\n"
        "**本接口不生成任何方案**：`can_confirm=false` 时表示仍有歧义必须由用户回答。"
    ),
    responses={
        503: {"description": "AI 规划未启用或模型不可用（fail closed，不回退）"},
        400: {"description": "用户消息不合规（空 / 超长 / 疑似个人信息）"},
        422: {"description": "模型输出未通过结构或白名单校验"},
    },
)
def interpret(body: InterpretRequestBody, service: ServiceDep) -> InterpretResponse:
    _require_enabled(service)
    context = _context_of(body.context)
    try:
        record, answer = service.interpret(message=body.user_message, context=context)
    except AiPlanningError as exc:
        _translate(exc)
        raise AssertionError("unreachable")  # pragma: no cover

    return InterpretResponse(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        parsed_intent=_intent_payload(record.draft, record.ambiguities),
        ambiguities=[
            {"code": item.code, "question": item.question, "detail": item.detail}
            for item in record.ambiguities
        ],
        data_source=record.context.data_source,
        # ⚠️ 如实报告：AI 接口的来源**从未**经过服务端独立核验。
        context_source_verified=record.context.source_verified,
        generator_kind=record.generator_kind,
        generator_note=record.generator_note,
        model_id=answer.model_id,
        can_confirm=not record.ambiguities,
        state=record.state,
        token_usage_estimate={
            "prompt": answer.prompt_tokens_estimate,
            "completion": answer.completion_tokens_estimate,
            "total": answer.total_tokens_estimate,
        },
        message=(
            "已生成意图草稿，请确认后再求解。"
            if not record.ambiguities
            else "意图草稿中仍有必须由你回答的歧义，请先补充信息。"
        ),
    )


@router.post(
    "/solve",
    response_model=SolveResponse,
    summary="对**已确认**意图调用受控 Planner 生成候选",
    description=(
        "只有用户确认过的意图（并与服务器当前方案指纹一致）才会进入求解。\n\n"
        "候选**只**由受控 Planner 产生，随后由服务端再做确定性复核"
        "（锁定课程 / 学分 / 时间 / 数据来源）。无法表达或无法求解时返回"
        "`status=blocked` 与 `blocked_reason`，⛔ 绝不硬造候选。"
    ),
    responses={
        409: {"description": "意图仍有歧义或状态冲突"},
        410: {"description": "方案指纹已过期"},
        422: {"description": "确认意图形状或取值非法"},
        501: {"description": "冻结 Planner 无法表达该意图"},
    },
)
def solve(body: SolveRequestBody, service: ServiceDep) -> SolveResponse:
    _require_enabled(service)
    try:
        outcome = service.solve(
            intent_id=body.intent_id,
            plan_digest=body.plan_digest,
            confirmed_intent=body.confirmed_intent,
        )
    except AiPlanningError as exc:
        _translate(exc)
        raise AssertionError("unreachable")  # pragma: no cover

    return SolveResponse(
        candidate_id=outcome.candidate_id,
        status=outcome.status,
        plan_kind=(
            "PlanResult" if outcome.candidate_plan is not None else "none"
        ),
        candidate_plan=(
            None if outcome.candidate_plan is None
            else outcome.candidate_plan.model_dump(mode="json")
        ),
        diff=None if outcome.diff is None else outcome.diff.to_payload(),
        risks=list(outcome.risks),
        unresolved=list(outcome.unresolved),
        message=outcome.message,
        blocked_reason=outcome.blocked_reason,
        data_source=outcome.data_source,
        generator_kind=outcome.generator_kind,
        plan_digest=outcome.plan_digest,
    )


@router.post(
    "/adopt",
    response_model=AdoptResponse,
    summary="二次确认：采用 / 拒绝某个候选（绑定方案指纹）",
    description=(
        "只有绑定了**同一方案指纹**且未过期的候选才能被采用；"
        "重复采用、跨指纹采用、已拒绝候选一律 409/410，原方案保持不变。\n\n"
        "⚠️ 会话状态在**进程内**：没有可靠持久化机制，进程重启即失效并 fail closed。"
    ),
    responses={
        409: {"description": "重复采用 / 状态冲突"},
        410: {"description": "候选已过期或指纹不符"},
        404: {"description": "候选不存在"},
    },
)
def adopt(body: AdoptRequestBody, service: ServiceDep) -> AdoptResponse:
    _require_enabled(service)
    try:
        record, version = service.adopt(
            candidate_id=body.candidate_id,
            plan_digest=body.plan_digest,
            accept=body.accept,
        )
    except AiPlanningError as exc:
        _translate(exc)
        raise AssertionError("unreachable")  # pragma: no cover

    return AdoptResponse(
        candidate_id=record.candidate_id,
        accepted=record.state == "adopted",
        state=record.state,
        adopted_version=version,
        adopted_version_scope="process_local_session",
        original_plan_unchanged=record.state != "adopted",
        plan_digest=record.plan_digest,
        message=(
            "已采用候选方案（仅在本进程会话内有效，未持久化）。"
            if record.state == "adopted"
            else "已拒绝候选方案；原方案完全不变。"
        ),
    )


# 让静态检查明确知道这些名字被使用（避免误删导出）。
_ = (ADJUSTMENT_SCOPE_CURRENT_SEMESTER, _GENERATOR_KINDS)
