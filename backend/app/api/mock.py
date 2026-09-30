"""Mock API：模拟「上游模块已经返回结果」。

重要边界（`/AGENTS.md` 第 5、19 节）：

本文件**不实现任何上游业务逻辑**。它只做三件事：
1. 从 `mock_data/` 读取上游本应产出的结果；
2. 用公共契约模型校验；
3. 按契约声明的形状返回。

所以这里没有、也不应该有：培养方案解析、课程等价判定、MakeupTask 生成、
冲突检测、补修优先级、OR-Tools 求解或 Path Repair。
那些属于 Curriculum / Course Data / Planner 模块。

每个响应都带 `X-Data-Source: mock` 响应头，确保调用方不可能把 Mock 误认成真实教务数据。

本文件是**永久 Mock 通道**：不会在将来被"原地替换"成真实数据源，也不会返回真实教务数据。
未来的真实接入将以**新增独立 adapter / provider** 的方式另开通道。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.contracts import CourseOffering, MakeupTask, PlanResult, Preference
from app.services.mock_service import (
    MockDataError,
    all_mock_data,
    load_course_offerings,
    load_makeup_tasks,
    load_plan_result,
    load_preference,
)

router = APIRouter(prefix="/mock", tags=["mock"])

#: 所有 Mock 响应统一携带的来源标记。
MOCK_DATA_SOURCE_HEADER = "X-Data-Source"
MOCK_DATA_SOURCE_VALUE = "mock"

_MOCK_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "description": "Mock 数据缺失或不符合公共契约（属于仓库数据问题，不是调用方错误）"
    }
}


def _mock_data_error(exc: MockDataError) -> HTTPException:
    """把数据层错误翻译成明确的 500 响应。

    Mock 数据损坏是**服务端仓库问题**，不是调用方传参错误，所以用 500 而不是 4xx；
    同时把具体文件和字段带出来，方便非专业开发成员直接定位。
    """

    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "mock_data_invalid", "message": str(exc)},
    )


def makeup_tasks() -> list[MakeupTask]:
    """依赖项：读取补修任务，供接口与自检复用。"""

    try:
        return load_makeup_tasks()
    except MockDataError as exc:
        raise _mock_data_error(exc) from exc


def course_offerings() -> list[CourseOffering]:
    """依赖项：读取教学班列表。"""

    try:
        return load_course_offerings()
    except MockDataError as exc:
        raise _mock_data_error(exc) from exc


def preference() -> Preference:
    """依赖项：读取用户偏好。"""

    try:
        return load_preference()
    except MockDataError as exc:
        raise _mock_data_error(exc) from exc


def plan_result() -> PlanResult:
    """依赖项：读取排课结果。"""

    try:
        return load_plan_result()
    except MockDataError as exc:
        raise _mock_data_error(exc) from exc


@router.get(
    "/makeup-tasks",
    response_model=list[MakeupTask],
    summary="[Mock] 补修任务列表",
    description=(
        "返回 Curriculum 模块**本应输出**的 MakeupTask 列表。当前为 mock_data/makeup_tasks.json 的演示数据，"
        "服务端不生成、不推导补修判定。"
    ),
    responses=_MOCK_RESPONSES,
)
def get_makeup_tasks(
    tasks: Annotated[list[MakeupTask], Depends(makeup_tasks)],
) -> list[MakeupTask]:
    return tasks


@router.get(
    "/course-offerings",
    response_model=list[CourseOffering],
    summary="[Mock] 教学班列表",
    description=(
        "返回 Course Data 模块**本应输出**的 CourseOffering 列表。当前为 mock_data/course_offerings.json 的演示数据，"
        "全部 data_source = \"mock\"，尚未接入真实教务数据。"
    ),
    responses=_MOCK_RESPONSES,
)
def get_course_offerings(
    offerings: Annotated[list[CourseOffering], Depends(course_offerings)],
) -> list[CourseOffering]:
    return offerings


@router.get(
    "/preference",
    response_model=Preference,
    summary="[Mock] 用户偏好",
    description=(
        "返回 Agent 模块解析自然语言后**本应产出**的 Preference。"
        "当前为 mock_data/preference.json 的人工演示数据，服务端不做自然语言解析。"
    ),
    responses=_MOCK_RESPONSES,
)
def get_preference(
    pref: Annotated[Preference, Depends(preference)],
) -> Preference:
    return pref


@router.get(
    "/plan-result",
    response_model=PlanResult,
    summary="[Mock] 排课结果",
    description=(
        "返回 Planner 模块**本应输出**的 PlanResult。"
        "当前为 mock_data/plan_result.json 的人工演示数据。"
        "**服务端不执行任何冲突检测或 Path Repair**，该结果不是求解器算出来的。"
    ),
    responses=_MOCK_RESPONSES,
)
def get_plan_result(
    result: Annotated[PlanResult, Depends(plan_result)],
) -> PlanResult:
    return result


@router.get(
    "/demo",
    summary="[Mock] 聚合演示数据",
    description=(
        "一次性返回四个公共对象，便于前端原型与联调时只调一个接口。"
        "这是**附加**能力，上面四个单一职责接口仍然保留。"
        "注意：名称里的 demo 指的是「演示数据」，不代表可运行的完整产品。"
    ),
    responses=_MOCK_RESPONSES,
)
def get_demo() -> dict[str, object]:
    try:
        return all_mock_data()
    except MockDataError as exc:
        raise _mock_data_error(exc) from exc
