"""公共契约模型测试。

本文件同时承担两件事：

1. **行为测试**：合法数据通过、非法数据失败（任务第 10 节明确要求的用例）；
2. **防漂移测试**：机械比对 Pydantic 模型与 `/schemas/*.schema.json`，
   一旦有人改了 Schema 却没同步模型（或反过来），测试立刻失败。

任务第 6 节要求「必须有测试保证关键字段、枚举和限制与 Schema 不冲突」，
第 2 项就是这条要求的自动化落实方式。

比对逻辑说明（`_compare_shape`）：把模型生成的 Schema 与公共 Schema 当作两棵
「形状树」递归比对，逐个字段检查类型、枚举、约束键和约束取值是否完全一致。
模型侧多出任何公共 Schema 没有的约束都会失败，因此「偷偷加字段或加限制」无法通过。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.contracts import (
    Course,
    CourseOffering,
    DataSource,
    MakeupStatus,
    MakeupTask,
    PlanResult,
    PlanStatus,
    Preference,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# 合法基准数据（模块级共享，避免每个用例重复抄写）
# ---------------------------------------------------------------------------

VALID_COURSE: dict = {
    "course_id": "62001001",
    "course_name": "离散数学",
    "credit": 3,
}

VALID_OFFERING: dict = {
    "course_id": "62001001",
    "course_name": "离散数学",
    "class_id": "6200100120260101",
    "semester": "2026-1",
    "weekday": 1,
    "start_section": 1,
    "end_section": 2,
    "weeks": [1, 2, 3, 4],
}

VALID_MAKEUP_TASK: dict = {
    "course_id": "62001001",
    "course_name": "离散数学",
    "credit": 3,
    "status": "required",
}

VALID_PLAN_RESULT: dict = {
    "status": "feasible",
    "selected_classes": [{"course_id": "62001001", "class_id": "6200100120260101"}],
    "changes": [],
    "risks": [],
    "unresolved": [],
}

# 模型 <-> 公共 Schema 文件的对应关系。防漂移测试按这张表逐项比对。
SCHEMA_BINDINGS: dict[str, tuple[type, str]] = {
    "Course": (Course, "course.schema.json"),
    "CourseOffering": (CourseOffering, "course_offering.schema.json"),
    "MakeupTask": (MakeupTask, "makeup_task.schema.json"),
    "Preference": (Preference, "preference.schema.json"),
    "PlanResult": (PlanResult, "plan_result.schema.json"),
}

#: Pydantic 自动生成的、纯注解性质的键，不属于契约语义，比对时忽略。
_ANNOTATION_KEYS = frozenset({"title", "description"})

#: 形状树里逐项比对的标量约束键。
_SCALAR_CONSTRAINT_KEYS = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "pattern",
    "format",
)


def _resolve(schema: dict, defs: dict) -> dict:
    """解析 `$ref`，并丢弃注解键，得到可直接比对的节点。"""

    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        assert ref_name in defs, f"模型生成 Schema 里存在无法解析的引用：{schema['$ref']}"
        schema = defs[ref_name]

    return {
        k: v
        for k, v in schema.items()
        if k not in _ANNOTATION_KEYS and k not in {"$defs", "$ref"}
    }


def _nullable(schema: dict) -> bool:
    """判断节点是否允许 null。

    公共 Schema 用 `type: ["x", "null"]`；Pydantic 用 `anyOf: [{type: x}, {type: null}]`。
    """

    if isinstance(schema.get("type"), list) and "null" in schema["type"]:
        return True
    return any(
        branch.get("type") == "null"
        or (isinstance(branch.get("type"), list) and "null" in branch["type"])
        for branch in schema.get("anyOf", [])
    )


def _concrete_type(schema: dict) -> str | None:
    """取出节点的具体（非 null）类型。"""

    if isinstance(schema.get("type"), str):
        return schema["type"]
    if isinstance(schema.get("type"), list):
        non_null = [t for t in schema["type"] if t != "null"]
        return non_null[0] if len(non_null) == 1 else None
    for branch in schema.get("anyOf", []):
        branch_type = branch.get("type")
        if isinstance(branch_type, str) and branch_type != "null":
            return branch_type
        # Pydantic 对内联对象可能生成 {"type": "object", ...} 之外的形式
        if isinstance(branch_type, list):
            non_null = [t for t in branch_type if t != "null"]
            if len(non_null) == 1:
                return non_null[0]
    return None


def _variant(schema: dict) -> dict:
    """把一个可空节点压平成具体类型那一支，便于继续比对它的约束。"""

    if isinstance(schema.get("type"), str):
        return schema
    for branch in schema.get("anyOf", []):
        if _concrete_type(branch) is not None:
            merged = {
                k: v
                for k, v in branch.items()
                if k not in _ANNOTATION_KEYS and k not in {"$defs", "$ref"}
            }
            merged.setdefault("type", _concrete_type(branch))
            return merged
    return schema


def _compare_shape(path: str, model_node: dict, json_node: dict, model_defs: dict) -> None:
    """递归比对模型 Schema 与公共 Schema 的一个节点。"""

    # 先解析 $ref，再做任何比较；否则模型侧的 {"$ref": ...} 取不到 type。
    model_node = _resolve(model_node, model_defs)
    json_node = _resolve(json_node, {})

    assert _nullable(model_node) == _nullable(json_node), (
        f"{path}：可空性不一致。模型 {_nullable(model_node)} vs Schema {_nullable(json_node)}"
    )

    model_type = _concrete_type(model_node)
    json_type = _concrete_type(json_node)
    assert model_type == json_type, f"{path}：类型不一致。模型 {model_type!r} vs Schema {json_type!r}"

    model_variant = _variant(model_node)
    json_variant = _variant(json_node)

    # --- 枚举 -------------------------------------------------------------
    if "enum" in json_variant:
        assert "enum" in model_variant, f"{path}：公共 Schema 限定取值，但模型没有 enum"
        assert set(model_variant["enum"]) == set(json_variant["enum"]), (
            f"{path}：enum 不一致。"
            f"模型 {sorted(model_variant['enum'])} vs Schema {sorted(json_variant['enum'])}"
        )

    # --- 标量约束 ---------------------------------------------------------
    # 注意 `uniqueItems`：Pydantic 不生成这个关键字，但本项目的模型通过
    # `UniqueStrList` 在运行时强制它（比公共 Schema 更严格，方向安全）。
    # 该差异由 `test_unique_items_fields_are_enforced_at_runtime` 与
    # `test_duplicate_items_are_rejected` 专门验证，因此这里跳过不比对。
    for key in _SCALAR_CONSTRAINT_KEYS:
        if key == "uniqueItems":
            continue
        json_has, model_has = key in json_variant, key in model_variant
        assert json_has == model_has, (
            f"{path}：约束 {key} 只在一侧出现（模型 {model_has} / Schema {json_has}）"
        )
        if json_has:
            assert model_variant[key] == json_variant[key], (
                f"{path}.{key}：取值不一致。"
                f"模型 {model_variant[key]!r} vs Schema {json_variant[key]!r}"
            )

    # --- 对象：字段集合、必填、是否禁止额外字段 ----------------------------
    if json_type == "object":
        json_props = json_variant.get("properties", {})
        model_props = model_variant.get("properties", {})

        assert set(model_props) == set(json_props), (
            f"{path}：字段集合不一致。"
            f"模型多出 {sorted(set(model_props) - set(json_props))}，"
            f"缺少 {sorted(set(json_props) - set(model_props))}"
        )

        assert set(model_variant.get("required", [])) == set(json_variant.get("required", [])), (
            f"{path}：必填字段不一致。"
            f"模型 {sorted(model_variant.get('required', []))} vs "
            f"Schema {sorted(json_variant.get('required', []))}"
        )

        if json_variant.get("additionalProperties") is False:
            assert model_variant.get("additionalProperties") is False, (
                f"{path}：公共 Schema 声明 additionalProperties: false，"
                f"但模型未设置 extra='forbid'"
            )

        for prop_name, json_prop in json_props.items():
            _compare_shape(
                f"{path}.{prop_name}", model_props[prop_name], json_prop, model_defs
            )

    # --- 数组：元素形状 ---------------------------------------------------
    if json_type == "array":
        assert "items" in json_variant, f"{path}：Schema 声明为数组但没有 items"
        assert "items" in model_variant, f"{path}：模型缺少数组元素定义"
        _compare_shape(f"{path}[]", model_variant["items"], json_variant["items"], model_defs)


# ---------------------------------------------------------------------------
# 防漂移：模型 vs 公共 Schema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_name", sorted(SCHEMA_BINDINGS))
def test_model_matches_public_schema(model_name: str, load_schema) -> None:
    """模型必须与公共 Schema 同构：字段、类型、枚举、约束、必填、禁止额外字段。

    这条用例是「不许私自改契约」的自动化护栏：
    只改 JSON Schema 而不改模型（或反之）都会在这里失败。

    唯一的例外见 `test_unique_list_fields_are_enforced`：
    公共 Schema 的 `uniqueItems` 由模型在运行时强制，不体现在生成的 Schema 里。
    """

    model, schema_file = SCHEMA_BINDINGS[model_name]
    json_schema = load_schema(schema_file)
    model_schema = model.model_json_schema()
    model_defs = model_schema.get("$defs", {})

    top_level_extra = set(model_schema) - set(json_schema) - _ANNOTATION_KEYS - {"$defs"}
    assert not top_level_extra, (
        f"{model_name}：模型顶层 Schema 出现公共 Schema 未声明的关键字 {sorted(top_level_extra)}"
    )

    _compare_shape(model_name, model_schema, json_schema, model_defs)


#: 每个模型的最小合法数据，用于「只替换某一个字段」构造非法输入。
_VALID_BASE: dict[str, dict] = {
    "Course": VALID_COURSE,
    "CourseOffering": VALID_OFFERING,
    "MakeupTask": VALID_MAKEUP_TASK,
    "Preference": {},
    "PlanResult": VALID_PLAN_RESULT,
}

#: 按公共 Schema 的 items 类型生成「重复元素」。
#: 如果将来公共 Schema 给新的元素类型加了 uniqueItems，这里会因为找不到对应类型而失败，
#: 从而强制补测试，而不是静默跳过验证。
_DUPLICATE_ITEM_BY_TYPE: dict[str, object] = {
    "string": "DUP",
    "integer": 1,
}


@pytest.mark.parametrize("model_name", sorted(SCHEMA_BINDINGS))
def test_unique_items_fields_are_enforced_at_runtime(model_name: str, load_schema) -> None:
    """公共 Schema 声明 `uniqueItems: true` 的数组，模型必须真的拒绝重复项。

    Pydantic 不会把 `uniqueItems` 生成为 Schema 关键字，因此这条必须单独验证。

    注意：本用例是**构造重复数据并断言被拒绝**，不是「确认字段存在」。
    只确认字段存在无法证明模型真的会拒绝重复项——那正是第一轮 Review 指出的问题。
    """

    model, schema_file = SCHEMA_BINDINGS[model_name]
    json_schema = load_schema(schema_file)

    unique_fields = [
        name
        for name, prop in json_schema["properties"].items()
        if prop.get("type") == "array" and prop.get("uniqueItems") is True
    ]

    if not unique_fields:
        pytest.skip(f"{model_name} 的公共 Schema 没有 uniqueItems 字段，无需运行")

    for name in unique_fields:
        assert name in model.model_fields, f"{model_name} 缺少带有 uniqueItems 的字段 {name}"

        item_type = json_schema["properties"][name]["items"]["type"]
        assert item_type in _DUPLICATE_ITEM_BY_TYPE, (
            f"{model_name}.{name} 的元素类型 {item_type!r} 尚未在测试中支持，"
            f"请扩展 _DUPLICATE_ITEM_BY_TYPE，不要跳过这条验证"
        )

        duplicate = _DUPLICATE_ITEM_BY_TYPE[item_type]
        payload = {**_VALID_BASE[model_name], name: [duplicate, duplicate]}

        with pytest.raises(ValidationError):
            model.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "payload", "field"),
    [
        (Course, {**VALID_COURSE, "prerequisites": ["A", "A"]}, "prerequisites"),
        (CourseOffering, {**VALID_OFFERING, "weeks": [1, 1]}, "weeks"),
        (MakeupTask, {**VALID_MAKEUP_TASK, "prerequisites": ["A", "B", "A"]}, "prerequisites"),
        (Preference, {"preferred_courses": ["62001001", "62001001"]}, "preferred_courses"),
    ],
    ids=[
        "course-prerequisites",
        "course-offering-weeks",
        "makeup-task-prerequisites",
        "preference-preferred-courses",
    ],
)
def test_duplicate_items_are_rejected(model: type, payload: dict, field: str) -> None:
    """`uniqueItems: true` 的实际行为：重复元素必须被拒绝。

    显式写出模型而不是靠 payload 猜，避免「加了字段但映射写错」导致验证落空。
    """

    assert field in model.model_fields

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_duplicate_weeks_are_rejected() -> None:
    """第一轮 Review 明确要求：`weeks=[1, 1]` 必须 ValidationError。"""

    with pytest.raises(ValidationError):
        CourseOffering.model_validate({**VALID_OFFERING, "weeks": [1, 1]})


def test_distinct_weeks_are_accepted() -> None:
    """反向确认：不重复的 weeks 必须正常通过，避免把合法数据也挡掉。"""

    offering = CourseOffering.model_validate({**VALID_OFFERING, "weeks": [1, 2]})

    assert offering.weeks == [1, 2]


def test_duplicate_items_allow_distinct_values() -> None:
    """反向确认：不重复的数组必须正常通过，避免把合法数据也挡掉。"""

    course = Course.model_validate({**VALID_COURSE, "prerequisites": ["62001001", "62001002"]})

    assert course.prerequisites == ["62001001", "62001002"]


@pytest.mark.parametrize(
    ("enum_cls", "expected"),
    [
        (DataSource, {"mock", "real"}),
        (MakeupStatus, {"required", "possibly_equivalent", "manual_confirmation", "satisfied"}),
        (PlanStatus, {"feasible", "partially_feasible", "infeasible"}),
        (RiskLevel, {"low", "medium", "high"}),
    ],
)
def test_enum_members_match_schema_values(enum_cls, expected: set[str]) -> None:
    """枚举类成员必须与公共 Schema 中写死的取值完全一致。"""

    assert {member.value for member in enum_cls} == expected


# ---------------------------------------------------------------------------
# 行为测试：合法输入通过
# ---------------------------------------------------------------------------


def test_valid_course_passes() -> None:
    assert Course.model_validate(VALID_COURSE).credit == 3


def test_valid_course_offering_passes() -> None:
    offering = CourseOffering.model_validate(VALID_OFFERING)

    assert offering.weekday == 1
    assert offering.weeks == [1, 2, 3, 4]


def test_valid_makeup_task_passes() -> None:
    assert MakeupTask.model_validate(VALID_MAKEUP_TASK).status is MakeupStatus.REQUIRED


def test_valid_plan_result_passes() -> None:
    assert PlanResult.model_validate(VALID_PLAN_RESULT).status is PlanStatus.FEASIBLE


def test_preference_requires_no_field() -> None:
    """Preference 所有字段都可选，空对象也必须合法（否则上游无法输出「暂无偏好」）。"""

    preference = Preference.model_validate({})

    assert preference.max_credit is None
    assert preference.avoid_cross_campus is False
    assert preference.avoid_times == []
    assert preference.preferred_courses == []


def test_optional_fields_accept_null() -> None:
    """可空字段必须接受显式 null。"""

    offering = CourseOffering.model_validate({**VALID_OFFERING, "teacher": None, "campus": None})
    task = MakeupTask.model_validate({**VALID_MAKEUP_TASK, "deadline_semester": None})

    assert offering.teacher is None
    assert task.deadline_semester is None


def test_plan_result_accepts_empty_optional_sections() -> None:
    """changes / risks / unresolved 允许为空数组（但不可缺省）。"""

    result = PlanResult.model_validate(VALID_PLAN_RESULT)

    assert result.changes == []
    assert result.risks == []
    assert result.unresolved == []


# ---------------------------------------------------------------------------
# 边界：weekday 1 和 7 是合法的
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("weekday", [1, 7])
def test_weekday_boundaries_are_valid(weekday: int) -> None:
    assert CourseOffering.model_validate({**VALID_OFFERING, "weekday": weekday}).weekday == weekday


def test_single_week_is_valid() -> None:
    """weeks 只有 1 项是合法的边界情况。"""

    assert CourseOffering.model_validate({**VALID_OFFERING, "weeks": [3]}).weeks == [3]


def test_zero_credit_is_valid() -> None:
    """minimum: 0 表示 0 学分合法（例如某些不计学分的必修环节）。"""

    assert Course.model_validate({**VALID_COURSE, "credit": 0}).credit == 0


def test_plan_result_with_empty_selected_classes_is_valid() -> None:
    """selected_classes 允许为空：无解方案也应该能被表达出来。"""

    result = PlanResult.model_validate(
        {**VALID_PLAN_RESULT, "status": "infeasible", "selected_classes": []}
    )

    assert result.selected_classes == []


# ---------------------------------------------------------------------------
# 行为测试：非法输入必须失败
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("weekday", [0, 8, -1, 9])
def test_invalid_weekday_is_rejected(weekday: int) -> None:
    """任务明确要求：weekday 超范围必须失败。"""

    with pytest.raises(ValidationError):
        CourseOffering.model_validate({**VALID_OFFERING, "weekday": weekday})


@pytest.mark.parametrize("weeks", [[], None, "1-16"])
def test_empty_weeks_is_rejected(weeks) -> None:
    """任务明确要求：weeks 为空必须失败。"""

    with pytest.raises(ValidationError):
        CourseOffering.model_validate({**VALID_OFFERING, "weeks": weeks})


def test_non_positive_section_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CourseOffering.model_validate({**VALID_OFFERING, "start_section": 0})


def test_negative_credit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Course.model_validate({**VALID_COURSE, "credit": -1})


def test_empty_course_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Course.model_validate({**VALID_COURSE, "course_id": ""})


def test_missing_required_field_is_rejected() -> None:
    payload = dict(VALID_OFFERING)
    del payload["class_id"]

    with pytest.raises(ValidationError):
        CourseOffering.model_validate(payload)


def test_extra_field_is_rejected() -> None:
    """additionalProperties: false —— 不允许夹带公共契约以外的字段。"""

    with pytest.raises(ValidationError):
        CourseOffering.model_validate({**VALID_OFFERING, "not_in_schema": "x"})


def test_invalid_data_source_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CourseOffering.model_validate({**VALID_OFFERING, "data_source": "pretend_real"})


def test_data_source_defaults_to_mock() -> None:
    """默认值必须是 mock，绝不能让缺失来源的数据被当成真实数据。"""

    assert CourseOffering.model_validate(VALID_OFFERING).data_source is DataSource.MOCK


def test_invalid_makeup_task_status_is_rejected() -> None:
    """任务明确要求：非法 MakeupTask status 必须失败。"""

    with pytest.raises(ValidationError):
        MakeupTask.model_validate({**VALID_MAKEUP_TASK, "status": "pending"})


def test_makeup_task_has_no_data_source_field() -> None:
    """公共 Schema 没有 data_source，因此不允许在 MakeupTask 上私加来源字段。"""

    assert "data_source" not in MakeupTask.model_fields

    with pytest.raises(ValidationError):
        MakeupTask.model_validate({**VALID_MAKEUP_TASK, "data_source": "mock"})


def test_invalid_plan_result_status_is_rejected() -> None:
    """任务明确要求：非法 PlanResult status 必须失败。"""

    with pytest.raises(ValidationError):
        PlanResult.model_validate({**VALID_PLAN_RESULT, "status": "ok"})


@pytest.mark.parametrize("field", ["status", "selected_classes", "changes", "risks", "unresolved"])
def test_plan_result_missing_required_section_is_rejected(field: str) -> None:
    """PlanResult 的五个部分都是必填，缺一个都不行。"""

    payload = dict(VALID_PLAN_RESULT)
    del payload[field]

    with pytest.raises(ValidationError):
        PlanResult.model_validate(payload)


def test_change_requires_reason() -> None:
    with pytest.raises(ValidationError):
        PlanResult.model_validate(
            {**VALID_PLAN_RESULT, "changes": [{"course_id": "62001002", "to_class": "x"}]}
        )


def test_risk_requires_valid_level() -> None:
    with pytest.raises(ValidationError):
        PlanResult.model_validate(
            {**VALID_PLAN_RESULT, "risks": [{"level": "critical", "reason": "x"}]}
        )


def test_risk_allows_missing_course_id() -> None:
    """risks[].course_id 可为 null 或省略：有些风险是整体性的，不针对某一门课。"""

    result = PlanResult.model_validate(
        {**VALID_PLAN_RESULT, "risks": [{"level": "low", "reason": "总学分偏低"}]}
    )

    assert result.risks[0].course_id is None


def test_preference_rejects_invalid_avoid_time_weekday() -> None:
    with pytest.raises(ValidationError):
        Preference.model_validate(
            {"avoid_times": [{"weekday": 8, "start_section": 1, "end_section": 2}]}
        )


def test_preference_rejects_negative_max_credit() -> None:
    with pytest.raises(ValidationError):
        Preference.model_validate({"max_credit": -1})


def test_plan_result_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        PlanResult.model_validate({**VALID_PLAN_RESULT, "solver_log": "..."})
