"""Mock 数据质量测试。

任务第 7、10 节要求：
- Mock 数据必须通过公共 Schema / 后端数据模型校验；
- CourseOffering 明确为 mock；
- Mock 数据不包含敏感信息。

本文件用**仓库里真实的** `/schemas/*.schema.json` 做校验（不是复制一份），
所以 Schema 一旦变化，Mock 数据是否合法会被立刻暴露。
"""

from __future__ import annotations

import json
import shutil

import pytest
from jsonschema import Draft202012Validator

from app.models.contracts import (
    CourseOffering,
    DataSource,
    MakeupStatus,
    MakeupTask,
    PlanResult,
    Preference,
)
from app.services import mock_service
from app.services.mock_service import MOCK_DATA_DIR, MockDataError

# Mock 文件 -> (公共 Schema 文件, Pydantic 模型, 是否数组)
MOCK_BINDINGS: dict[str, tuple[str, type, bool]] = {
    "makeup_tasks.json": ("makeup_task.schema.json", MakeupTask, True),
    "course_offerings.json": ("course_offering.schema.json", CourseOffering, True),
    "preference.json": ("preference.schema.json", Preference, False),
    "plan_result.json": ("plan_result.schema.json", PlanResult, False),
}

#: 个人身份信息字段名。
#: 注意：`teacher` 是公共 Schema 明确允许的课程元数据（教师姓名），
#: 不属于「学生个人隐私」，因此不在禁止之列。
_PERSONAL_FIELD_NAMES = {
    "student_id",
    "student_no",
    "student_name",
    "phone",
    "mobile",
    "email",
    "id_card",
    "id_number",
    "passport",
    "password",
    "token",
    "cookie",
    "session",
    "authorization",
}

#: 认证 / 凭据关键字。Mock 数据中不允许出现这些子串（小写比对）。
_CREDENTIAL_MARKERS = (
    "password",
    "passwd",
    "cookie",
    "jsessionid",
    "bearer ",
    "api_key",
    "apikey",
    "secret",
)


def _iter_strings(node):
    """递归产出 JSON 结构里的所有字符串键与值。"""

    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)
    elif isinstance(node, str):
        yield node


@pytest.fixture(scope="module")
def mock_files(load_mock_file) -> dict[str, object]:
    """一次性载入全部 Mock 文件。"""

    return {name: load_mock_file(name) for name in MOCK_BINDINGS}


@pytest.fixture(scope="module")
def course_offerings(load_mock_file) -> list[dict]:
    return load_mock_file("course_offerings.json")


@pytest.mark.parametrize("file_name", sorted(MOCK_BINDINGS))
def test_mock_file_passes_public_schema(file_name: str, load_schema, mock_files) -> None:
    """Mock 数据必须通过公共 JSON Schema（真源）校验。"""

    schema_name, _model, is_list = MOCK_BINDINGS[file_name]
    schema = load_schema(schema_name)
    payload = mock_files[file_name]

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    if is_list:
        assert isinstance(payload, list), f"{file_name} 应为数组"
        for index, item in enumerate(payload):
            errors = sorted(validator.iter_errors(item), key=lambda e: list(e.path))
            assert not errors, (
                f"{file_name}[{index}] 不符合 {schema_name}：{[e.message for e in errors]}"
            )
    else:
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        assert not errors, f"{file_name} 不符合 {schema_name}：{[e.message for e in errors]}"


@pytest.mark.parametrize("file_name", sorted(MOCK_BINDINGS))
def test_mock_file_passes_backend_model(file_name: str, mock_files) -> None:
    """Mock 数据必须能通过后端 Pydantic 模型校验。

    与上一条一起构成「Schema 与模型双通过」，任一侧漂移都会失败。
    """

    _schema_name, model, is_list = MOCK_BINDINGS[file_name]
    payload = mock_files[file_name]

    if is_list:
        parsed = [model.model_validate(item) for item in payload]
        assert len(parsed) == len(payload)
    else:
        model.model_validate(payload)


def test_course_offerings_are_all_marked_mock(course_offerings: list[dict]) -> None:
    """任务明确要求：CourseOffering 必须明确 data_source = mock。"""

    assert course_offerings, "course_offerings.json 不能为空"

    for offering in course_offerings:
        assert offering["data_source"] == "mock", (
            f"教学班 {offering['class_id']} 的 data_source 不是 mock，"
            f"可能是把真实数据伪装成了 Mock（或反之）"
        )


def test_same_course_has_multiple_offerings(course_offerings: list[dict]) -> None:
    """任务明确要求：至少包含同一课程的两个教学班。

    这是「当前教学班冲突时换同课其它教学班」能力的数据前提；
    如果每门课只有一个班，Path Repair 就无从演示。
    """

    by_course: dict[str, list[str]] = {}
    for offering in course_offerings:
        by_course.setdefault(offering["course_id"], []).append(offering["class_id"])

    multi = {course: classes for course, classes in by_course.items() if len(classes) >= 2}

    assert multi, f"没有任何课程拥有 ≥2 个教学班，无法演示备选教学班：{by_course}"


def test_offering_single_semester(course_offerings: list[dict]) -> None:
    """演示数据应集中在同一学期，否则选课方案会自相矛盾。"""

    semesters = {offering["semester"] for offering in course_offerings}

    assert len(semesters) == 1, f"Mock 教学班跨越多个学期：{sorted(semesters)}"


def test_course_offerings_have_time_and_location_details(course_offerings: list[dict]) -> None:
    """任务要求教学班包含教师、星期、节次、周次、校区信息。"""

    for offering in course_offerings:
        label = offering["class_id"]
        assert offering.get("teacher"), f"{label} 缺少教师"
        assert offering.get("weekday") is not None, f"{label} 缺少星期"
        assert offering.get("start_section") is not None, f"{label} 缺少起始节次"
        assert offering.get("end_section") is not None, f"{label} 缺少结束节次"
        assert offering.get("weeks"), f"{label} 缺少周次"
        assert offering.get("campus"), f"{label} 缺少校区"


def test_offering_end_section_not_before_start_section(course_offerings: list[dict]) -> None:
    """基本业务合理性：结束节次不能早于起始节次。

    注意：公共 Schema 并未强制这条（它只要求各自 ≥1），
    这是 Mock 数据自身的质量检查，不代表契约要求。
    """

    for offering in course_offerings:
        assert offering["end_section"] >= offering["start_section"], (
            f"{offering['class_id']}：end_section({offering['end_section']}) "
            f"< start_section({offering['start_section']})"
        )


def test_offering_data_source_enum_is_mock(course_offerings: list[dict]) -> None:
    """用模型再确认一次来源枚举，避免只靠字符串比较漏掉大小写等问题。"""

    for offering in course_offerings:
        assert CourseOffering.model_validate(offering).data_source is DataSource.MOCK


def test_offering_weeks_are_plausible_semester_weeks(course_offerings: list[dict]) -> None:
    """周次应落在 1~25 的合理学期范围内，且不重复。"""

    for offering in course_offerings:
        weeks = offering["weeks"]
        assert len(set(weeks)) == len(weeks), f"{offering['class_id']} 周次重复：{weeks}"
        assert all(1 <= week <= 25 for week in weeks), (
            f"{offering['class_id']} 周次超出合理学期范围：{weeks}"
        )


# ---------------------------------------------------------------------------
# 任务第 7 节对各对象的覆盖要求
# ---------------------------------------------------------------------------


def test_makeup_tasks_cover_required_and_uncertain_statuses(mock_files) -> None:
    """任务要求：至少一个 required，以及一个 manual_confirmation 或 possibly_equivalent。"""

    statuses = {task["status"] for task in mock_files["makeup_tasks.json"]}

    assert "required" in statuses, f"缺少 required 状态的补修任务：{sorted(statuses)}"
    assert statuses & {"manual_confirmation", "possibly_equivalent"}, (
        f"缺少需要人工确认或可能等价的补修任务：{sorted(statuses)}"
    )

    allowed = {member.value for member in MakeupStatus}
    assert statuses <= allowed, f"出现契约未定义的 status：{sorted(statuses - allowed)}"


def test_preference_has_credit_limit_and_avoidance_rule(mock_files) -> None:
    """任务要求：Preference 至少包含 max_credit，以及 avoid_times 或 avoid_cross_campus。"""

    preference = mock_files["preference.json"]

    assert preference.get("max_credit") is not None, "缺少 max_credit"
    assert preference.get("avoid_times") or preference.get("avoid_cross_campus"), (
        "缺少 avoid_times 且未开启 avoid_cross_campus"
    )


def test_plan_result_covers_all_five_sections(mock_files) -> None:
    """任务要求：PlanResult 至少包含 status/selected_classes/changes/risks/unresolved。"""

    plan_result = mock_files["plan_result.json"]

    for key in ("status", "selected_classes", "changes", "risks", "unresolved"):
        assert key in plan_result, f"PlanResult 缺少 {key}"

    assert plan_result["unresolved"], "演示数据应包含待人工确认项，否则无法展示系统的诚实边界"


def test_plan_result_references_real_mock_offerings(mock_files) -> None:
    """方案里选中的教学班必须真的存在于 Mock 教学班列表中。

    这是防「编造教学班数据」的一致性检查（职责边界要求 Agent 不得编造教学班）。
    """

    known_classes = {
        (offering["course_id"], offering["class_id"])
        for offering in mock_files["course_offerings.json"]
    }
    plan_result = mock_files["plan_result.json"]

    assert plan_result["selected_classes"], "演示方案应至少选中一个教学班"

    for selected in plan_result["selected_classes"]:
        key = (selected["course_id"], selected["class_id"])
        assert key in known_classes, f"PlanResult 选中了不存在的教学班：{key}"

    for change in plan_result["changes"]:
        for side in ("from_class", "to_class"):
            class_id = change.get(side)
            if class_id is None:
                continue
            key = (change["course_id"], class_id)
            assert key in known_classes, f"PlanResult changes 引用了不存在的教学班：{key}"


def test_plan_result_selected_credit_within_preference_limit(mock_files) -> None:
    """方案总学分不应超过偏好里的 max_credit。

    注意：这条是 Mock 数据自洽性检查，不是后端算法——
    真实的学分校验属于 Planner，本阶段后端不做任何求解。
    """

    credit_by_class = {
        (offering["course_id"], offering["class_id"]): offering["credit"]
        for offering in mock_files["course_offerings.json"]
    }
    plan_result = mock_files["plan_result.json"]
    max_credit = mock_files["preference.json"]["max_credit"]

    total = sum(
        credit_by_class[(selected["course_id"], selected["class_id"])]
        for selected in plan_result["selected_classes"]
    )

    assert total <= max_credit, f"方案总学分 {total} 超过偏好上限 {max_credit}"


def test_plan_result_avoids_preferred_avoid_times(mock_files) -> None:
    """演示方案应体现「避开用户不想要的时段」，否则看不出 Path Repair 的效果。"""

    avoid_blocks = mock_files["preference.json"]["avoid_times"]
    offerings = {
        (offering["course_id"], offering["class_id"]): offering
        for offering in mock_files["course_offerings.json"]
    }

    assert avoid_blocks, "演示偏好应至少包含一个 avoid_times"

    for selected in mock_files["plan_result.json"]["selected_classes"]:
        offering = offerings[(selected["course_id"], selected["class_id"])]
        for block in avoid_blocks:
            if offering["weekday"] != block["weekday"]:
                continue
            overlaps = (
                offering["start_section"] <= block["end_section"]
                and offering["end_section"] >= block["start_section"]
            )
            assert not overlaps, (
                f"选中教学班 {offering['class_id']} 落在用户避开的时段内：{block}"
            )


# ---------------------------------------------------------------------------
# 敏感信息
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("file_name", sorted(MOCK_BINDINGS))
def test_mock_data_contains_no_personal_identifiers(file_name: str, mock_files) -> None:
    """Mock 数据不得包含学生个人身份字段或邮箱。

    只禁止**学生隐私**类字段。课程元数据（如 `teacher` 教师姓名）是公共 Schema
    明确允许的内容，不算个人隐私，故不在检查范围内。
    """

    payload = mock_files[file_name]
    strings = list(_iter_strings(payload))

    for field_name in _PERSONAL_FIELD_NAMES:
        hits = [s for s in strings if s.strip().lower() == field_name]
        assert not hits, f"{file_name} 出现了疑似个人身份字段名：{field_name}"

    for value in strings:
        lowered = value.lower()
        assert "@" not in lowered or "mock://" in lowered, f"{file_name} 出现了疑似邮箱：{value}"


@pytest.mark.parametrize("file_name", sorted(MOCK_BINDINGS))
def test_mock_data_contains_no_credentials(file_name: str, mock_files) -> None:
    """Mock 数据不得包含密码 / Cookie / Token / API Key 等凭据痕迹。"""

    lowered = json.dumps(mock_files[file_name], ensure_ascii=False).lower()

    for marker in _CREDENTIAL_MARKERS:
        assert marker not in lowered, f"{file_name} 出现疑似凭据内容：{marker!r}"


def test_source_evidence_points_to_mock(mock_files) -> None:
    """Mock 数据的来源标注必须自证是演示数据，不能看起来像真实出处。"""

    for task in mock_files["makeup_tasks.json"]:
        evidence = task.get("source_evidence") or ""
        assert evidence.startswith("mock://"), (
            f"{task['course_id']} 的 source_evidence 未标明是演示数据：{evidence!r}"
        )
        assert "演示数据" in evidence or "非真实" in evidence, (
            f"{task['course_id']} 的 source_evidence 未说明非真实：{evidence!r}"
        )


# ---------------------------------------------------------------------------
# 运行期必须按公共 JSON Schema 校验（不能依赖 Pydantic 的类型转换）
# ---------------------------------------------------------------------------


def _poisoned_copy(tmp_path, file_name: str) -> dict:
    """把真实 Mock 文件复制到临时目录并返回可修改的原始 JSON，供破坏性用例使用。

    直接改仓库里的 `mock_data/` 会污染其他测试与工作区，所以一律在 tmp_path 上做。
    """

    shutil.copy(MOCK_DATA_DIR / file_name, tmp_path / file_name)
    return json.loads((tmp_path / file_name).read_text(encoding="utf-8"))


def test_json_schema_rejects_string_weekday_before_pydantic(tmp_path, monkeypatch) -> None:
    """回归测试：JSON 里 `weekday` 写成字符串 `"1"` 必须被拒绝。

    背景（第一轮 Review blocker 2）：`mock_service` 早期只做 `model_validate`，
    而 Pydantic 默认会把 `"1"` 转成 `1`，于是「违反公共 JSON Schema（要求 integer）
    的数据」会被静默接受。公共 Schema 是唯一真源，必须先按 Schema 校验原始 JSON。

    本用例先断言 Pydantic 单独校验**确实会接受**这条数据，以证明回归测试不是空跑，
    然后再断言数据层会拒绝它。
    """

    raw = _poisoned_copy(tmp_path, "course_offerings.json")
    raw[0]["weekday"] = "1"

    assert CourseOffering.model_validate(raw[0]).weekday == 1, (
        "Pydantic 不再转换该数据，本回归测试的前提已变化，需要改用别的类型错误样例"
    )

    (tmp_path / "course_offerings.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(mock_service, "MOCK_DATA_DIR", tmp_path)

    with pytest.raises(MockDataError) as excinfo:
        mock_service.load_course_offerings()

    message = str(excinfo.value)
    assert "weekday" in message, f"报错未指出问题字段：{message}"
    assert "course_offering.schema.json" in message, f"报错未指出依据的公共 Schema：{message}"


def test_json_schema_rejects_boolean_credit_before_pydantic(tmp_path, monkeypatch) -> None:
    """第二个回归样例：`credit` 写成布尔值也必须被拒绝。

    公共 Schema 要求 `credit` 是 number，而 `true` 不是 number。
    Pydantic 默认会把 `True` 当成 `1`，所以只有先按 Schema 校验才能拦住。
    """

    raw = _poisoned_copy(tmp_path, "course_offerings.json")
    raw[0]["credit"] = True

    assert CourseOffering.model_validate(raw[0]).credit == 1

    (tmp_path / "course_offerings.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(mock_service, "MOCK_DATA_DIR", tmp_path)

    with pytest.raises(MockDataError):
        mock_service.load_course_offerings()


def test_json_schema_rejects_duplicate_weeks(tmp_path, monkeypatch) -> None:
    """`weeks` 重复元素不仅要被模型拒绝，也必须被公共 Schema 在数据层拦下。"""

    raw = _poisoned_copy(tmp_path, "course_offerings.json")
    raw[0]["weeks"] = [1, 1]

    (tmp_path / "course_offerings.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(mock_service, "MOCK_DATA_DIR", tmp_path)

    with pytest.raises(MockDataError) as excinfo:
        mock_service.load_course_offerings()

    assert "weeks" in str(excinfo.value)


def test_startup_self_check_uses_public_schema(tmp_path, monkeypatch) -> None:
    """启动自检走的 `all_mock_data()` 也必须按公共 JSON Schema 校验，而不是只靠 Pydantic。"""

    for file_name in MOCK_BINDINGS:
        shutil.copy(MOCK_DATA_DIR / file_name, tmp_path / file_name)

    raw = json.loads((tmp_path / "preference.json").read_text(encoding="utf-8"))
    raw["max_credit"] = "15"

    assert Preference.model_validate(raw).max_credit == 15

    (tmp_path / "preference.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(mock_service, "MOCK_DATA_DIR", tmp_path)

    with pytest.raises(MockDataError):
        mock_service.all_mock_data()
