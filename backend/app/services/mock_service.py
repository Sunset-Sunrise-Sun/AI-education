"""Mock 数据读取服务（**永久 Mock-only**）。

职责边界（严格遵守 `/AGENTS.md` 第 5 节）：

- 本服务**只读取 `mock_data/` 下已经存在的 JSON 文件**，并用公共契约校验；
- 本服务**不生成**、**不推导**、**不伪造**任何上游业务结果。
  换句话说：Curriculum 的补修判定、Planner 的求解结论都是别人写好的数据，
  这里只负责「把上游模块已经返回的结果读出来交给 API 层」；
- 本服务**永远只服务 Mock**。它不会在将来被"原地替换"成真实数据源，也不会读取真实教务数据。
  未来的真实接入将以**新增独立 adapter / provider** 的方式另开通道（详见 `backend/README.md` 第 9 节）。

校验顺序（两层，缺一不可）：

1. **先按 `/schemas/*.schema.json` 校验原始 JSON**——公共 JSON Schema 是唯一真源。
   这一步不能省：Pydantic 会做类型转换（`weekday: "1"` → `1`、`credit: true` → `1`），
   只做 `model_validate` 会放行"看起来能用、但违反公共 Schema"的数据，
   而启动自检的全部意义就是不让这种数据上线。
2. **再用 Pydantic 模型解析**，得到带类型、带枚举的后端对象。

真实数据接入必须等用户完成教务页面技术侦察并确认授权范围。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Final, TypeVar

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
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
    "MOCK_DATA_SCHEMAS",
    "SCHEMAS_DIR",
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

#: 公共 Schema 目录。**唯一真源**，本文件只读不写。
SCHEMAS_DIR: Final[Path] = _REPO_ROOT / "schemas"

#: 本次底座读取的 Mock 文件清单，供 README 与自检使用。
MOCK_DATA_FILES: Final[dict[str, str]] = {
    "makeup_tasks": "makeup_tasks.json",
    "course_offerings": "course_offerings.json",
    "preference": "preference.json",
    "plan_result": "plan_result.json",
}

#: Mock 文件键 -> 对应的公共 JSON Schema 文件。原始 JSON 必须先过这一关。
MOCK_DATA_SCHEMAS: Final[dict[str, str]] = {
    "makeup_tasks": "makeup_task.schema.json",
    "course_offerings": "course_offering.schema.json",
    "preference": "preference.schema.json",
    "plan_result": "plan_result.schema.json",
}

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class MockDataError(RuntimeError):
    """Mock 数据缺失、不是合法 JSON，或不符合公共契约。

    错误信息会写清楚「哪个文件、哪个字段」，方便非专业开发成员定位，
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


@lru_cache(maxsize=None)
def _load_public_schema(schema_name: str) -> dict:
    """读取并自检公共 JSON Schema。**只读**，绝不修改 `/schemas/`。

    结果做缓存：Schema 在一次运行期内不会变化，缓存可避免每次请求都读文件。
    """

    path = SCHEMAS_DIR / schema_name

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MockDataError(
            f"缺少公共 Schema 文件：{path}。公共契约是校验的唯一真源，缺失时无法保证数据合法。"
        ) from exc

    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MockDataError(
            f"公共 Schema 不是合法 JSON：{path}（第 {exc.lineno} 行第 {exc.colno} 列）。"
        ) from exc

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise MockDataError(f"公共 Schema 本身不合法：{path}。{exc.message}") from exc

    return schema


def _validate_against_public_schema(file_key: str, file_name: str, payload: object) -> None:
    """按公共 JSON Schema 校验**原始 JSON**（发生在 Pydantic 之前）。

    为什么必须单独做这一步：Pydantic 会做类型转换。
    例如 `weekday: "1"`（字符串）会被 Pydantic 转成 `1`，`credit: true` 会被转成 `1`；
    但公共 Schema 要求它们分别是 integer 与 number，这类数据**不符合公共契约**，
    必须在进入模型之前就被拒绝，而不是被"修正"成合法值。
    """

    schema = _load_public_schema(MOCK_DATA_SCHEMAS[file_key])
    validator = Draft202012Validator(schema)

    is_list = isinstance(payload, list)
    items = payload if is_list else [payload]

    problems: list[str] = []
    for index, item in enumerate(items):
        for error in validator.iter_errors(item):
            location = "/".join(str(part) for part in error.absolute_path) or "<根>"
            where = f"[{index}]{location}" if is_list else location
            problems.append(f"{where}：{error.message}")

    if problems:
        raise MockDataError(
            f"Mock 数据不符合公共 JSON Schema：{MOCK_DATA_DIR / file_name} -> "
            f"schemas/{MOCK_DATA_SCHEMAS[file_key]}。问题：{problems}"
        )


def _load_model(file_key: str, model: type[_ModelT]) -> _ModelT:
    """读取并校验单个对象型 Mock 数据（先公共 Schema，后 Pydantic）。"""

    file_name = MOCK_DATA_FILES[file_key]
    payload = _read_json(file_name)
    _validate_against_public_schema(file_key, file_name, payload)

    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise MockDataError(
            f"Mock 数据不符合公共契约：{MOCK_DATA_DIR / file_name} -> {model.__name__}。"
            f"校验错误：{exc.errors(include_url=False)}"
        ) from exc


def _load_list(file_key: str, model: type[_ModelT]) -> list[_ModelT]:
    """读取并校验数组型 Mock 数据（先公共 Schema，后 Pydantic）。

    空数组是合法的，但如果文件本身不是数组（例如误写成对象），会明确报错。
    """

    file_name = MOCK_DATA_FILES[file_key]
    payload = _read_json(file_name)

    if not isinstance(payload, list):
        raise MockDataError(
            f"Mock 数据文件应为 JSON 数组：{MOCK_DATA_DIR / file_name}，"
            f"实际是 {type(payload).__name__}。"
        )

    _validate_against_public_schema(file_key, file_name, payload)

    try:
        return [model.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise MockDataError(
            f"Mock 数据不符合公共契约：{MOCK_DATA_DIR / file_name} -> {model.__name__}[]。"
            f"校验错误：{exc.errors(include_url=False)}"
        ) from exc


def load_makeup_tasks() -> list[MakeupTask]:
    """补修任务列表（Curriculum 模块本应输出的结果，当前为 Mock）。"""

    return _load_list("makeup_tasks", MakeupTask)


def load_course_offerings() -> list[CourseOffering]:
    """教学班列表（Course Data 模块本应输出的结果，当前为 Mock）。"""

    return _load_list("course_offerings", CourseOffering)


def load_preference() -> Preference:
    """用户偏好（Agent 解析自然语言后本应产出的结果，当前为 Mock）。"""

    return _load_model("preference", Preference)


def load_plan_result() -> PlanResult:
    """排课结果（Planner 模块本应输出的结果，当前为 Mock）。"""

    return _load_model("plan_result", PlanResult)


def all_mock_data() -> dict[str, object]:
    """一次性读取全部 Mock 数据，供 `/demo` 聚合接口与启动自检使用。

    启动自检走的就是这条路径，因此"数据不合公共 Schema"会在启动阶段就暴露。
    返回的字典直接可被 JSON 序列化：调用方负责把结果交给 FastAPI。
    """

    return {
        "makeup_tasks": load_makeup_tasks(),
        "course_offerings": load_course_offerings(),
        "preference": load_preference(),
        "plan_result": load_plan_result(),
    }
