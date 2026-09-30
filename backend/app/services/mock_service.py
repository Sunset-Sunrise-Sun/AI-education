"""Mock 数据读取服务。

职责边界（严格遵守 `/AGENTS.md` 第 5 节）：

- 本服务**只读取 `mock_data/` 下已经存在的 JSON 文件**，并用公共契约模型校验；
- 本服务**不生成**、**不推导**、**不伪造**任何上游业务结果。
  换句话说：Curriculum 的补修判定、Planner 的求解结论都是别人写好的数据，
  这里只负责「把上游模块已经返回的结果读出来交给 API 层」。
- 因此未来把 Mock 换成真实模块时，**只需要替换这一层的数据来源**
  （例如改成调用 Curriculum / Planner 的函数），API 层与模型层都不用动。

所有返回数据都是 Mock。真实数据接入必须等用户完成教务页面技术侦察并确认授权范围。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, TypeVar

from pydantic import BaseModel, ValidationError

from app.models.contracts import (
    CourseOffering,
    MakeupTask,
    PlanResult,
    Preference,
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

# backend/app/services/mock_service.py -> 上溯 3 层到仓库根目录
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

#: Mock 数据目录。与 `/AGENTS.md` 第 6 节规定的 `/mock_data/` 一致。
MOCK_DATA_DIR: Final[Path] = _REPO_ROOT / "mock_data"

#: 本次底座读取的 Mock 文件清单，供 README 与自检使用。
MOCK_DATA_FILES: Final[dict[str, str]] = {
    "makeup_tasks": "makeup_tasks.json",
    "course_offerings": "course_offerings.json",
    "preference": "preference.json",
    "plan_result": "plan_result.json",
}

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class MockDataError(RuntimeError):
    """Mock 数据缺失、不是合法 JSON，或不符合公共契约。

    错误信息会写清楚「哪个文件、哪一行、哪个字段」，方便非专业开发成员定位，
    不使用难懂的裸异常（见 `docs/DEVELOPMENT_RULES.md` 第 6 节）。
    """


def _read_json(file_name: str) -> object:
    """读取 `mock_data/` 下的 JSON 文件。

    故意不做缓存：Mock 数据体量很小，每次读文件可以保证改完数据立即生效，
    避免开发阶段出现「改了 JSON 但接口还是旧数据」的困惑。
    """

    path = MOCK_DATA_DIR / file_name

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MockDataError(f"缺少 Mock 数据文件：{path}。请确认 mock_data/ 目录存在且完整。") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MockDataError(
            f"Mock 数据文件不是合法 JSON：{path}（第 {exc.lineno} 行第 {exc.colno} 列）。"
            f"原始错误：{exc.msg}"
        ) from exc


def _load_model(file_name: str, model: type[_ModelT]) -> _ModelT:
    """读取并校验单个对象型 Mock 数据。"""

    payload = _read_json(file_name)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise MockDataError(
            f"Mock 数据不符合公共契约：{MOCK_DATA_DIR / file_name} -> {model.__name__}。"
            f"校验错误：{exc.errors(include_url=False)}"
        ) from exc


def _load_list(file_name: str, model: type[_ModelT]) -> list[_ModelT]:
    """读取并校验数组型 Mock 数据。

    空数组是合法的，但如果文件本身不是数组（例如误写成对象），会明确报错。
    """

    payload = _read_json(file_name)
    if not isinstance(payload, list):
        raise MockDataError(
            f"Mock 数据文件应为 JSON 数组：{MOCK_DATA_DIR / file_name}，"
            f"实际是 {type(payload).__name__}。"
        )

    try:
        return [model.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise MockDataError(
            f"Mock 数据不符合公共契约：{MOCK_DATA_DIR / file_name} -> {model.__name__}[]。"
            f"校验错误：{exc.errors(include_url=False)}"
        ) from exc


def load_makeup_tasks() -> list[MakeupTask]:
    """补修任务列表（Curriculum 模块本应输出的结果，当前为 Mock）。"""

    return _load_list(MOCK_DATA_FILES["makeup_tasks"], MakeupTask)


def load_course_offerings() -> list[CourseOffering]:
    """教学班列表（Course Data 模块本应输出的结果，当前为 Mock）。"""

    return _load_list(MOCK_DATA_FILES["course_offerings"], CourseOffering)


def load_preference() -> Preference:
    """用户偏好（Agent 解析自然语言后本应产出的结果，当前为 Mock）。"""

    return _load_model(MOCK_DATA_FILES["preference"], Preference)


def load_plan_result() -> PlanResult:
    """排课结果（Planner 模块本应输出的结果，当前为 Mock）。"""

    return _load_model(MOCK_DATA_FILES["plan_result"], PlanResult)


def all_mock_data() -> dict[str, object]:
    """一次性读取全部 Mock 数据，供 `/demo` 聚合接口与启动自检使用。

    返回的字典直接可被 JSON 序列化：调用方负责把结果交给 FastAPI。
    """

    return {
        "makeup_tasks": load_makeup_tasks(),
        "course_offerings": load_course_offerings(),
        "preference": load_preference(),
        "plan_result": load_plan_result(),
    }
