"""Course Data 内部快照 + Provider 落点测试（Phase 2B-2A）。

覆盖 Data Gate **C9** 的 completeness 纪律：

  "目标是一学期完整 snapshot" **≠** "当前已经拥有完整 snapshot"

以及 `SnapshotCourseDataProvider` 与 Phase 2B-1 冻结的 `CourseDataProvider` 的**结构一致性**。

⚠️ 数据最小化：只使用**人工虚构**的 source-shaped 输入与占位教师名 `"示例教师A"`；
**不包含**真实教师姓名、内部长 ID 取值、`readObj`、Raw JSON、Cookie / Session / Token。

⚠️ 零网络：本文件不发起任何请求；另有一条**代码边界检查**锁定
`backend/app/course_data/` 不导入任何网络 / 抓取 / Mock 回放依赖。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.course_data import (
    CourseDataNormalizationError,
    OfferingSnapshot,
    SnapshotCourseDataProvider,
    build_course_offering,
)
from app.integration import CourseDataProvider
from app.models.contracts import CourseOffering, DataSource, Meeting

SEMESTER = "2026-1"

# backend/tests/test_course_data_snapshot.py -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_COURSE_DATA_PACKAGE = _BACKEND_ROOT / "app" / "course_data"

#: Course Data 内部包**不得**导入的依赖（网络 / 抓取 / Mock 回放）。
_FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "httpx",
    "aiohttp",
    "selenium",
    "playwright",
    "urllib",
    "http",
    "socket",
}


def _meeting(**overrides: object) -> Meeting:
    payload: dict[str, object] = {
        "weekday": 1,
        "start_section": 1,
        "end_section": 2,
        "weeks": [1, 2, 3],
        "campus": "东校园",
        "classroom": "东A201",
    }
    payload.update(overrides)
    return Meeting(**payload)


def _real_offering(
    *,
    course_id: str = "62001001",
    class_id: str = "6200100120260101",
    semester: str = SEMESTER,
) -> CourseOffering:
    return build_course_offering(
        {
            "courseNum": course_id,
            "courseName": "离散数学",
            "classNumber": class_id,
            "yearTerm": semester,
            "score": "3",
            "teachingName": "示例教师A",
            "limitNumber": 90,
            "selectedNumber": 75,
        },
        meetings=[_meeting()],
        source="mock://course-data-snapshot-test",
    )


def _mock_offering() -> CourseOffering:
    """一条 `data_source = mock` 的教学班（用于验证"Mock 不得混入 real snapshot"）。"""

    return CourseOffering(
        course_id="62001001",
        course_name="离散数学",
        class_id="6200100120260101",
        semester=SEMESTER,
        meetings=[_meeting()],
        data_source=DataSource.MOCK,
    )


# ---------------------------------------------------------------------------
# completeness：partial
# ---------------------------------------------------------------------------


def test_partial_snapshot_without_reported_total_is_valid() -> None:
    snapshot = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_real_offering(),),
        completeness="partial",
    )

    assert snapshot.loaded_count == 1
    assert snapshot.reported_total is None
    assert snapshot.is_complete is False


def test_partial_snapshot_with_reported_total_not_smaller_than_loaded_is_valid() -> None:
    snapshot = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_real_offering(),),
        completeness="partial",
        reported_total=40,
    )

    assert snapshot.reported_total == 40
    assert snapshot.is_complete is False


def test_partial_snapshot_with_reported_total_smaller_than_loaded_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError) as excinfo:
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_real_offering(),),
            completeness="partial",
            reported_total=0,
        )

    assert "reported_total" in str(excinfo.value)


def test_empty_partial_snapshot_is_valid() -> None:
    """"什么都还没导入"是合法的 partial 状态，但**不能**被说成 complete。"""

    snapshot = OfferingSnapshot(semester=SEMESTER, offerings=(), completeness="partial")

    assert snapshot.loaded_count == 0
    assert snapshot.is_complete is False


# ---------------------------------------------------------------------------
# completeness：complete
# ---------------------------------------------------------------------------


def test_complete_snapshot_requires_reported_total() -> None:
    with pytest.raises(CourseDataNormalizationError) as excinfo:
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_real_offering(),),
            completeness="complete",
        )

    assert "reported_total" in str(excinfo.value)


def test_complete_snapshot_with_matching_counts_is_valid() -> None:
    snapshot = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(
            _real_offering(class_id="6200100120260101"),
            _real_offering(class_id="6200100120260102"),
        ),
        completeness="complete",
        reported_total=2,
    )

    assert snapshot.loaded_count == 2
    assert snapshot.is_complete is True


def test_complete_snapshot_with_mismatched_counts_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_real_offering(),),
            completeness="complete",
            reported_total=99,
        )


def test_two_sample_offerings_cannot_claim_complete_semester_snapshot() -> None:
    """核心纪律用例：**2 条侦察样本不得声称 complete**。

    D5 侦察只取得 2 个真实教学班；如果整学期实际有更多教学班，
    把 completeness 写成 "complete" 且 reported_total 写 2 就必须能通过，
    但只要上游报告的真实总数不是 2，这里就必须失败。
    """

    two_samples = (
        _real_offering(class_id="6200100120260101"),
        _real_offering(class_id="6200100120260102"),
    )

    # 上游报告整学期共 6892 条 → 绝不允许把 2 条样本说成 complete
    with pytest.raises(CourseDataNormalizationError):
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=two_samples,
            completeness="complete",
            reported_total=6892,
        )

    # 退一步：即使谎报总数，2 条样本也只能是 partial
    partial = OfferingSnapshot(
        semester=SEMESTER, offerings=two_samples, completeness="partial"
    )
    assert partial.is_complete is False


# ---------------------------------------------------------------------------
# 其它一致性校验
# ---------------------------------------------------------------------------


def test_invalid_completeness_value_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_real_offering(),),
            completeness="mostly",  # type: ignore[arg-type]
        )


def test_negative_reported_total_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_real_offering(),),
            completeness="partial",
            reported_total=-1,
        )


def test_empty_semester_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        OfferingSnapshot(semester="", offerings=(), completeness="partial")


def test_offering_from_another_semester_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError) as excinfo:
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_real_offering(semester="2026-2"),),
            completeness="partial",
        )

    assert "2026-2" in str(excinfo.value)


def test_mock_offering_in_real_snapshot_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError) as excinfo:
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_mock_offering(),),
            completeness="partial",
        )

    assert "mock" in str(excinfo.value)


def test_duplicate_class_key_is_rejected() -> None:
    """同一教学班重复 → 失败（**不静默保留第一条**）。

    判重键是 `(semester, course_id, class_id)`；
    ⛔ **不能**按 `course_id` 去重 —— 一门课本来就可以有多个教学班。
    """

    duplicate = _real_offering(class_id="6200100120260101")

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(duplicate, duplicate),
            completeness="partial",
        )

    assert "重复" in str(excinfo.value)


def test_same_course_with_different_class_ids_is_allowed() -> None:
    """同一门课的多个教学班必须都保留（这正是 Path Repair 的数据前提）。"""

    snapshot = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(
            _real_offering(class_id="6200100120260101"),
            _real_offering(class_id="6200100120260102"),
        ),
        completeness="complete",
        reported_total=2,
    )

    assert {offering.class_id for offering in snapshot.offerings} == {
        "6200100120260101",
        "6200100120260102",
    }


def test_snapshot_freezes_offerings_into_a_tuple() -> None:
    """传入 list 也会被固化成 tuple，避免外部继续改动让快照悄悄变样。"""

    container = [_real_offering()]
    snapshot = OfferingSnapshot(
        semester=SEMESTER, offerings=container, completeness="partial"
    )

    assert isinstance(snapshot.offerings, tuple)

    container.append(_real_offering(class_id="6200100120260102"))

    assert snapshot.loaded_count == 1


# ---------------------------------------------------------------------------
# SnapshotCourseDataProvider
# ---------------------------------------------------------------------------


def _provider() -> SnapshotCourseDataProvider:
    snapshot = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(
            _real_offering(class_id="6200100120260101"),
            _real_offering(class_id="6200100120260102"),
        ),
        completeness="complete",
        reported_total=2,
    )
    return SnapshotCourseDataProvider(snapshot)


def test_provider_structurally_satisfies_frozen_course_data_provider() -> None:
    """结构上满足 Phase 2B-1 冻结的 `CourseDataProvider`（不继承、不修改 Protocol）。"""

    assert isinstance(_provider(), CourseDataProvider)


def test_provider_returns_offerings_for_matching_semester() -> None:
    offerings = _provider().get_course_offerings(SEMESTER)

    assert [offering.class_id for offering in offerings] == [
        "6200100120260101",
        "6200100120260102",
    ]
    assert all(offering.data_source is DataSource.REAL for offering in offerings)


def test_provider_returns_empty_list_for_other_semester() -> None:
    """"查不到"就如实返回空列表 —— **不报错、不 fallback 到 Mock**。"""

    provider = _provider()

    assert provider.get_course_offerings("2027-1") == []
    assert provider.get_course_offerings("") == []


def test_provider_returns_a_fresh_list_each_call() -> None:
    provider = _provider()

    first = provider.get_course_offerings(SEMESTER)
    first.clear()

    assert provider.get_course_offerings(SEMESTER) != []


def test_provider_exposes_its_snapshot_read_only() -> None:
    provider = _provider()

    assert provider.snapshot.semester == SEMESTER
    assert provider.snapshot.is_complete is True


def test_provider_rejects_non_snapshot_input() -> None:
    with pytest.raises(CourseDataNormalizationError):
        SnapshotCourseDataProvider(object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 代码边界：Course Data 内部包必须是零网络实现
# ---------------------------------------------------------------------------


def test_course_data_package_imports_no_network_or_mock_dependencies() -> None:
    """`backend/app/course_data/` 不得导入网络 / 抓取 / Mock 回放依赖。

    用 AST 检查**真实的 import 语句**（文档里出现这些名字是允许的，
    被禁的是真的导入它们）。这也是"本轮为零网络实现"的机器可验证证据。
    """

    sources = sorted(_COURSE_DATA_PACKAGE.glob("*.py"))
    assert sources, f"未找到 Course Data 包源文件：{_COURSE_DATA_PACKAGE}"

    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))

        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")

        for module in imported_modules:
            root = module.split(".")[0]
            assert root not in _FORBIDDEN_IMPORT_ROOTS, (
                f"{path.name} 导入了网络 / 抓取依赖：{module}"
            )
            assert not module.startswith("app.services"), (
                f"{path.name} 导入了 Mock 回放通道：{module}"
            )
            assert "mock_service" not in module, (
                f"{path.name} 导入了 mock_service：{module}"
            )


def _non_docstring_string_literals(path: Path) -> list[str]:
    """收集源码里**非 docstring** 的字符串字面量。

    为什么排除 docstring：本包的文档**正是在声明**"我们不碰 Cookie / 不写 endpoint"，
    这类说明性文字是允许的；被禁止的是**代码里真的出现**这些字面量。
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))

    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_nodes.add(id(body[0].value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    ]


def test_course_data_package_has_no_endpoint_or_credential_literals() -> None:
    """代码中不得出现 endpoint / 凭据类字面量（防止把抓取逻辑偷偷塞进来）。

    只检查**非 docstring** 的字符串字面量：文档里说明"不碰 Cookie / 不写 endpoint"
    是允许的，代码里真的写出来才是问题。
    """

    forbidden_literals = (
        "jwxt.sysu.edu.cn",
        "querySchoolOpeningCourses",
        "Cookie",
        "jsessionid",
        "JSESSIONID",
        "Authorization",
        "pageNo",
        "pageSize",
        "NetID",
        "captcha",
    )

    for path in sorted(_COURSE_DATA_PACKAGE.glob("*.py")):
        for literal in _non_docstring_string_literals(path):
            for forbidden in forbidden_literals:
                assert forbidden not in literal, (
                    f"{path.name} 的代码字面量里出现 endpoint / 凭据痕迹：{literal!r}"
                )
