"""解释接口（**新增的私有接口**，不修改任何既有路径或公共 Schema）。

```text
POST /api/v1/explanation/plan
  body: { plan_result, makeup_tasks?, course_offerings? }
        ↓
  只读解释服务（默认确定性规则模板；可选注入模型适配层）
        ↓
  { contract_version, plan_result_digest, context_digest, generation, source_summary,
    warnings, items[] }
```

## 边界（硬）

- ⛔ 不修改 `PlanResult`：`plan_result_digest` 就是被解释方案的指纹，调用方可据此核对；
- ⛔ 不调用 Planner / Curriculum / Course Data / Mock 通道，不读写数据库，不联网；
- ⛔ 未配置模型时**绝不**声称是 AI 生成：响应里 `generation.generator_kind`
  明确是 `rule_based_template`，并给出面向用户的 disclaimer；
- ⛔ 失败时**不回退**到任何演示数据，也不返回一份"看起来像成功"的解释；
  请求体不合法 ⇒ 422；上下文过大 ⇒ 422；内部只读保证被破坏 ⇒ 500（不吞异常）；
- ⛔ 本接口只接受公共契约对象，**不接受**成绩单 / 姓名 / 学号等个人信息字段
  （`extra="forbid"` 会让额外字段直接 422）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.explanation.models import ExplanationRequest, ExplanationResponse
from app.explanation.service import (
    MAX_CONTEXT_ITEMS,
    ExplanationContextTooLarge,
    ExplanationService,
)
from app.models.contracts import CourseOffering, MakeupTask, PlanResult

router = APIRouter(prefix="/explanation", tags=["explanation"])


class ExplanationRequestBody(BaseModel):
    """HTTP 请求包络：字段与内部模型一一对应，不允许额外键。"""

    model_config = ConfigDict(extra="forbid")

    plan_result: PlanResult
    makeup_tasks: list[MakeupTask] = Field(
        default_factory=list,
        description="可选：Curriculum 已输出的补修任务上下文",
    )
    course_offerings: list[CourseOffering] = Field(
        default_factory=list,
        description="可选：Course Data 已输出的教学班上下文",
    )


@router.post(
    "/plan",
    response_model=ExplanationResponse,
    summary="为已有规划结果生成有依据的解释（只读，默认规则模板）",
    description=(
        "解释服务只读消费调用方**已经拿到**的 PlanResult（可选附带 MakeupTask / CourseOffering 上下文），"
        "逐条给出「为什么这样判定 / 这样安排」，并列出信息来源字段、证据强度与待人工确认事项。\n\n"
        "**它不计算、不改写、不修改规划结果**：响应中的 `plan_result_digest` 是输入方案的指纹。\n\n"
        "**生成方式如实标注**：未配置模型时为 `rule_based_template`（明确不是 AI 生成）；"
        "即使配置了模型，输出也必须通过事实绑定校验，否则降级为模板并记录原因。"
    ),
    responses={
        # 422：不同 Starlette 版本的常量名不同（`HTTP_422_UNPROCESSABLE_ENTITY`
        # 已在 1.x 标记为弃用），这里直接用标准码，避免把接口行为绑在依赖版本上。
        422: {
            "description": "请求体不符合公共契约，或解释上下文条目过多（fail closed，不回退）",
        }
    },
)
def explain_plan(request: ExplanationRequestBody) -> ExplanationResponse:
    """把已校验输入原样交给解释服务，并直接返回其结果。"""

    try:
        return ExplanationService().explain(
            ExplanationRequest(
                plan_result=request.plan_result,
                makeup_tasks=list(request.makeup_tasks),
                course_offerings=list(request.course_offerings),
            )
        )
    except ExplanationContextTooLarge as exc:
        # 上下文规模越界属于调用方输入问题：明确 422，⛔ 不吞成 500、⛔ 不静默截断。
        raise HTTPException(
            status_code=422,
            detail={"error": "explanation_context_too_large", "message": str(exc)},
        ) from exc
