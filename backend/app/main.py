"""FastAPI 应用入口（组长模块后端集成底座）。

启动：

    cd backend
    python -m uvicorn app.main:app --reload

本文件只负责组装应用：路由、版本前缀、启动自检。
不包含任何业务算法。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api import health, mock
from app.api.mock import MOCK_DATA_SOURCE_HEADER, MOCK_DATA_SOURCE_VALUE
from app.services.mock_service import MockDataError, all_mock_data

#: 业务接口统一版本前缀。`/health` 作为探针接口不放在前缀下。
API_V1_PREFIX = "/api/v1"

#: 启动自检失败时的报错文案前缀，便于人工在日志里快速定位。
_STARTUP_CHECK_FAILED = "启动自检失败：Mock 数据不符合公共契约。"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动自检。

    启动时立刻读一遍全部 Mock 数据，让「数据坏了」在启动阶段就暴露，
    而不是等前端调到某个接口才发现。数据损坏时进程直接启动失败，
    避免带着错误数据对外提供服务。
    """

    try:
        all_mock_data()
    except MockDataError as exc:
        raise RuntimeError(f"{_STARTUP_CHECK_FAILED}{exc}") from exc

    yield


app = FastAPI(
    title="学航·转衔 — 后端集成底座",
    version=__version__,
    description=(
        "组长模块 Phase 1：FastAPI 集成底座。\n\n"
        "当前只提供健康检查与 Mock 接口，用于在 Curriculum / Course Data / Planner "
        "尚未完成时模拟完整数据链路。\n\n"
        "**当前所有数据均为 Mock，尚未接入真实教务数据。**"
    ),
    lifespan=lifespan,
)


@app.middleware("http")
async def mark_mock_data_source(request: Request, call_next):  # type: ignore[no-untyped-def]
    """给所有响应打上数据来源标记。

    公共 Schema 中只有 CourseOffering 带 `data_source` 字段，其余对象不允许私自加字段
    （`additionalProperties: false`）。因此来源标记通过响应头暴露，确保调用方
    不可能把演示数据误认成真实教务数据。
    """

    response = await call_next(request)
    response.headers[MOCK_DATA_SOURCE_HEADER] = MOCK_DATA_SOURCE_VALUE
    return response


@app.exception_handler(MockDataError)
async def mock_data_error_handler(request: Request, exc: MockDataError) -> JSONResponse:
    """兜底处理数据层异常，保证不把内部堆栈直接抛给前端。"""

    return JSONResponse(
        status_code=500,
        content={"detail": {"error": "mock_data_invalid", "message": str(exc)}},
    )


# `/health` 挂在根路径，作为部署探针。
app.include_router(health.router)

# 业务接口统一在 /api/v1 下；同一份 health 路由再挂一次，便于带前缀的调用方使用。
app.include_router(health.router, prefix=API_V1_PREFIX)
app.include_router(mock.router, prefix=API_V1_PREFIX)
