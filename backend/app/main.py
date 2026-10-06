"""FastAPI 应用入口（组长模块后端集成底座）。

启动：

    cd backend
    python -m uvicorn app.main:app --reload

本文件只负责组装应用：路由、版本前缀、异常处理。
不包含任何业务算法。
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app import __version__
from app.api import completed_courses, completed_courses_pdf, health, mock, plan
from app.api.mock import MOCK_DATA_SOURCE_HEADER, MOCK_DATA_SOURCE_VALUE
from app.course_data import CourseDataAcceptanceError
from app.services.mock_service import MockDataError
from app.services.planning_runtime import PlanningRuntimeNotConfigured

#: 业务接口统一版本前缀。`/health` 作为探针接口不放在前缀下。
API_V1_PREFIX = "/api/v1"

app = FastAPI(
    title="学航·转衔 — 后端集成底座",
    version=__version__,
    description=(
        "组长模块 Phase 1：FastAPI 集成底座。\n\n"
        "提供永久 Mock 回放通道，以及真实规划链路的独立装配入口。\n\n"
        "**真实 Provider 尚未装配时，规划接口会明确返回 503，不会回退到 Mock。**"
    ),
)


@app.middleware("http")
async def mark_mock_data_source(request: Request, call_next):  # type: ignore[no-untyped-def]
    """只给永久 Mock 通道的响应打上数据来源标记。

    公共 Schema 中只有 CourseOffering 带 `data_source` 字段，其余对象不允许私自加字段
    （`additionalProperties: false`）。因此来源标记通过响应头暴露，确保调用方
    不可能把演示数据误认成真实教务数据。
    """

    response = await call_next(request)
    if request.url.path.startswith(f"{API_V1_PREFIX}/mock/"):
        response.headers[MOCK_DATA_SOURCE_HEADER] = MOCK_DATA_SOURCE_VALUE
    return response


@app.exception_handler(PlanningRuntimeNotConfigured)
async def planning_runtime_not_configured_handler(
    request: Request, exc: PlanningRuntimeNotConfigured
) -> JSONResponse:
    """把唯一的装配缺失状态翻译成可测试的 503；不捕获 Provider 业务异常。"""

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": {
                "error": "real_pipeline_not_configured",
                "message": str(exc),
            }
        },
    )


@app.exception_handler(CourseDataAcceptanceError)
async def course_data_acceptance_error_handler(
    request: Request, exc: CourseDataAcceptanceError
) -> JSONResponse:
    """把**请求期间**发现的 acceptance 失效映射成同一个 503 readiness 契约。

    语义：Course Data 的 full_semester acceptance 在请求过程中不再有效
    （被删除 / 被改写 / 内容被替换 / 行数不符）。这是**就绪性失败**，不是调用方错误，
    也⛔ 不是 Mock fallback 的理由 —— 因此与"未装配"共用 503 +
    `real_pipeline_not_configured`。

    ⛔ 其它未预期异常（例如 SQLite 损坏）**不在这里捕获**，仍然保持 500。
    """

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": {
                "error": "real_pipeline_not_configured",
                "message": (
                    "真实规划链路当前不可用：Course Data acceptance 已失效或不再匹配。"
                ),
            }
        },
    )


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
app.include_router(plan.router, prefix=API_V1_PREFIX)

# 通用已修课程 XLSX 摄取入口（Gate F）：
# ⛔ 不接入已冻结的 Case A fixed-case runtime，也⛔ 不改动 `/api/v1/plan` 的请求契约。
app.include_router(completed_courses.router, prefix=API_V1_PREFIX)

# 成绩单 PDF 摄取入口（Case A 主路径）：
# XLSX 入口保持不变、继续作为次要兼容路径；两个入口的错误码彼此独立。
app.include_router(completed_courses_pdf.router, prefix=API_V1_PREFIX)
