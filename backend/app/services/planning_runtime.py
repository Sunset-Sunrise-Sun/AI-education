"""真实规划链路的最小装配边界。

这里不提供 Mock fallback，也不猜测尚未就绪的 production Provider。
后续真实 Provider 可用时，只需在本模块中构造并返回 ``PlanningOrchestrator``。
"""

from __future__ import annotations

from app.integration import PlanningOrchestrator

__all__ = ["PlanningRuntimeNotConfigured", "get_planning_orchestrator"]


class PlanningRuntimeNotConfigured(RuntimeError):
    """真实 Curriculum / Course Data / Planner 尚未完成装配。"""


def get_planning_orchestrator() -> PlanningOrchestrator | None:
    """返回 production 规划编排器；当前尚未配置，因此返回 ``None``。

    该依赖是唯一的 production wiring seam。测试可通过 FastAPI dependency override
    注入由 Fake Provider 构造的编排器，但生产代码绝不回退到 Mock 数据。
    """

    return None
