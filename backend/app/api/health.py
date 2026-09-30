"""健康检查接口。

按任务要求，`/health` 挂在根路径（不在 `/api/v1` 下），
便于部署探针、反向代理和人工快速确认服务是否活着。
"""

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["health"])

#: 数据来源标记。本阶段全部数据均为 Mock，接口层显式暴露，避免被误当成真实数据。
DATA_SOURCE = "mock"


@router.get(
    "/health",
    summary="健康检查",
    description="返回服务存活状态。不检查数据库或上游模块，本阶段尚未接入。",
)
def health() -> dict[str, str]:
    """返回 `{"status": "ok"}` 以及当前数据来源标记。"""

    return {
        "status": "ok",
        "service": "integration-backend",
        "version": __version__,
        "data_source": DATA_SOURCE,
    }
