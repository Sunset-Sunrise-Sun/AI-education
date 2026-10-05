"""真实规划 API：只负责请求校验、依赖注入与调用 Orchestrator。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.integration import PlanningOrchestrator
from app.models.contracts import CourseOffering, DataSource, PlanResult, Preference
from app.services.planning_runtime import (
    PlanningRuntimeNotConfigured,
    get_planning_orchestrator,
)

router = APIRouter(tags=["planning"])


class PlanRequest(BaseModel):
    """仅供 HTTP API 使用的请求包络；内部字段复用公共契约模型。"""

    model_config = ConfigDict(extra="forbid")

    semester: str = Field(min_length=1)
    current_schedule: list[CourseOffering]
    preference: Preference

    @field_validator("semester")
    @classmethod
    def semester_must_not_be_blank(cls, value: str) -> str:
        """拒绝纯空白学期，同时保留合法输入的原始文本。"""

        if not value.strip():
            raise ValueError("semester 必须是非空字符串")
        return value

    @field_validator("current_schedule")
    @classmethod
    def current_schedule_must_be_real(
        cls, value: list[CourseOffering]
    ) -> list[CourseOffering]:
        """Real API 只接受明确标记为 real 的当前课表；空课表合法。"""

        if any(item.data_source is not DataSource.REAL for item in value):
            raise ValueError("current_schedule 中所有教学班的 data_source 必须为 real")
        return value


@router.post(
    "/plan",
    response_model=PlanResult,
    summary="生成真实规划结果",
    description=(
        "调用已装配的真实 Curriculum、Course Data 与 Planner Provider。"
        "当前未装配时返回 503，绝不回退到 Mock 通道。"
    ),
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "真实规划链路尚未配置",
        }
    },
)
def create_plan(
    request: PlanRequest,
    orchestrator: Annotated[
        PlanningOrchestrator | None, Depends(get_planning_orchestrator)
    ],
) -> PlanResult:
    """把已校验输入原样交给 Orchestrator，并直接返回其结果。"""

    if orchestrator is None:
        raise PlanningRuntimeNotConfigured("真实规划链路尚未配置。")

    return orchestrator.build_plan(
        semester=request.semester,
        current_schedule=request.current_schedule,
        preference=request.preference,
    )
