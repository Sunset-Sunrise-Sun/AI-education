"""服务层：数据来源与业务编排。

当前只有一个 Mock 数据读取服务。未来真实模块接入时，替换的是这一层，
而不是 API 层或契约模型层。
"""

from app.services.mock_service import (
    MOCK_DATA_DIR,
    MOCK_DATA_FILES,
    MockDataError,
    all_mock_data,
    load_course_offerings,
    load_makeup_tasks,
    load_plan_result,
    load_preference,
)

__all__ = [
    "MOCK_DATA_DIR",
    "MOCK_DATA_FILES",
    "MockDataError",
    "all_mock_data",
    "load_course_offerings",
    "load_makeup_tasks",
    "load_plan_result",
    "load_preference",
]
