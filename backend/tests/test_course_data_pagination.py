"""分页采集核心测试（Phase 2B-2C0，**零网络**）。

⚠️ **数据最小化**：所有 Raw rows 均为**人工虚构**的结构等价样本；
**不使用**真实 D5 Raw、真实教师姓名、真实教室、内部 ID 取值、Cookie / Session / Token。

覆盖重点：串行页序、`first_page_no` 起点、`total` 一致性、空页提前停滞、
累计超限、`max_pages` 安全阀 → `partial`、跨页重复交给 `OfferingSnapshot`、
异常 / 解析失败原样向上失败、取满后不再请求下一页、顺序保持、参数校验。
"""

from __future__ import annotations

import ast
import inspect

import pytest

import app.course_data.pagination as pagination_module
from app.course_data import (
    CourseDataNormalizationError,
    OpeningCoursesPageFetcher,
    collect_opening_courses_snapshot,
)
from app.models.contracts import DataSource

SEMESTER = "2026-1"
SOURCE = "mock://course-data-pagination-test"
TEACHER_A = "示例教师A"
ACTIVITY = "示例环节"
SCHEDULE = f"1-8周/星期五/第5-6节/{TEACHER_A}/{ACTIVITY},"


# ---------------------------------------------------------------------------
# 人工虚构的 Raw page 构造器
# ---------------------------------------------------------------------------


def _row(class_number: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "courseNum": "62001001",
        "courseName": "离散数学",
        "classNumber": class_number,
        "yearTerm": SEMESTER,
        "score": "3",
        "teachingName": TEACHER_A,
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": SCHEDULE,
    }
    row.update(overrides)
    return row


def _page(rows: list[dict[str, object]], *, total: int, code: int = 200) -> dict[str, object]:
    return {"code": code, "data": {"total": total, "rows": rows}}


def _rows_for(prefix: str, count: int) -> list[dict[str, object]]:
    return [_row(f"620010012026{prefix}{index:02d}") for index in range(count)]


class FakePageFetcher:
    """测试用 Fake：按 `page_no` 返回预置页，并记录调用序列。

    ⛔ 不做网络、不做重试、不做 fallback —— 只回放给定的 Raw page。
    """

    def __init__(self, pages: dict[int, dict[str, object]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, object]] = []

    def fetch_page(
        self,
        *,
        semester: str,
        page_no: int,
        page_size: int,
    ) -> dict[str, object]:
        self.calls.append(
            {"semester": semester, "page_no": page_no, "page_size": page_size}
        )
        if page_no not in self._pages:
            raise AssertionError(f"Fake 未预置页码 {page_no}（调用越界即测试失败）")
        return self._pages[page_no]

    @property
    def page_numbers(self) -> list[int]:
        return [int(call["page_no"]) for call in self.calls]


class ExplodingPageFetcher:
    """第一次取页即抛异常：确认异常原样向上传递。"""

    class BoomError(RuntimeError):
        pass

    def __init__(self) -> None:
        self.calls = 0

    def fetch_page(self, *, semester: str, page_no: int, page_size: int) -> dict[str, object]:
        self.calls += 1
        raise ExplodingPageFetcher.BoomError("fetch failed")


def _collect(
    fetcher: object,
    *,
    first_page_no: int = 1,
    max_pages: int = 10,
    page_size: int = 2,
    semester: str = SEMESTER,
    source: str = SOURCE,
):
    return collect_opening_courses_snapshot(
        fetcher,  # type: ignore[arg-type]
        semester=semester,
        source=source,
        page_size=page_size,
        first_page_no=first_page_no,
        max_pages=max_pages,
    )


# ---------------------------------------------------------------------------
# Protocol / 结构
# ---------------------------------------------------------------------------


def test_fake_fetcher_satisfies_internal_protocol() -> None:
    assert isinstance(FakePageFetcher({}), OpeningCoursesPageFetcher)


def test_module_declares_no_network_imports() -> None:
    """分页核心自身必须是零网络实现（与包边界测试互相印证）。"""

    tree = ast.parse(inspect.getsource(pagination_module))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    for module in imported:
        root = module.split(".")[0]
        assert root not in {"requests", "httpx", "aiohttp", "urllib", "socket", "selenium", "playwright"}
        assert not module.startswith("app.integration"), f"分页核心不得依赖 Integration：{module}"


def test_partial_snapshot_is_not_wrapped_into_production_provider() -> None:
    """⛔ 本阶段禁止把 `partial` 包成生产 `SnapshotCourseDataProvider`。

    用 **AST** 检查真实的 import 与调用：文档里**声明**"禁止包装成 Provider"是允许的，
    被禁的是真的导入 / 构造它。
    """

    tree = ast.parse(inspect.getsource(pagination_module))

    imported_names: set[str] = set()
    imported_modules: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
            imported_names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            imported_names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)

    forbidden = {"SnapshotCourseDataProvider", "CourseDataProvider"}
    assert not (imported_names & forbidden), f"分页核心导入了 Provider：{imported_names & forbidden}"
    assert not (called_names & forbidden), f"分页核心构造了 Provider：{called_names & forbidden}"

    # provider 属于 Integration 边界，分页核心不得依赖它
    assert not any(module.startswith("app.integration") for module in imported_modules)

    # 运行时也不应把 Provider 暴露在本模块命名空间里
    assert not hasattr(pagination_module, "SnapshotCourseDataProvider")
    assert not hasattr(pagination_module, "CourseDataProvider")


# ---------------------------------------------------------------------------
# complete：单页 / 两页 / 三页
# ---------------------------------------------------------------------------


def test_single_page_complete() -> None:
    fetcher = FakePageFetcher({1: _page(_rows_for("01", 2), total=2)})

    snapshot = _collect(fetcher)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 2
    assert snapshot.reported_total == 2
    assert fetcher.page_numbers == [1]


def test_two_pages_complete() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 2), total=3),
            2: _page(_rows_for("02", 1), total=3),
        }
    )

    snapshot = _collect(fetcher)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 3
    assert fetcher.page_numbers == [1, 2]


def test_three_pages_complete() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 2), total=6),
            2: _page(_rows_for("02", 2), total=6),
            3: _page(_rows_for("03", 2), total=6),
        }
    )

    snapshot = _collect(fetcher)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 6
    assert fetcher.page_numbers == [1, 2, 3]


def test_default_like_call_requires_all_pagination_params() -> None:
    """分页参数**必须显式传入**：不提供 `page_size` / `first_page_no` / `max_pages` 会报错。"""

    fetcher = FakePageFetcher({1: _page(_rows_for("01", 1), total=1)})

    with pytest.raises(TypeError):
        collect_opening_courses_snapshot(  # type: ignore[call-arg]
            fetcher,
            semester=SEMESTER,
            source=SOURCE,
        )


# ---------------------------------------------------------------------------
# first_page_no 起点
# ---------------------------------------------------------------------------


def test_first_page_no_one_calls_one_two_three() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 1), total=3),
            2: _page(_rows_for("02", 1), total=3),
            3: _page(_rows_for("03", 1), total=3),
        }
    )

    snapshot = _collect(fetcher, first_page_no=1)

    assert snapshot.is_complete is True
    assert fetcher.page_numbers == [1, 2, 3]


def test_first_page_no_zero_calls_zero_one_two() -> None:
    """⛔ 不假定 `page_no` 从 1 开始：`first_page_no=0` 必须按 0,1,2 调用。"""

    fetcher = FakePageFetcher(
        {
            0: _page(_rows_for("01", 1), total=3),
            1: _page(_rows_for("02", 1), total=3),
            2: _page(_rows_for("03", 1), total=3),
        }
    )

    snapshot = _collect(fetcher, first_page_no=0)

    assert snapshot.is_complete is True
    assert fetcher.page_numbers == [0, 1, 2]


def test_semester_and_page_size_are_passed_through() -> None:
    fetcher = FakePageFetcher({1: _page(_rows_for("01", 1), total=1)})

    _collect(fetcher, page_size=7)

    assert fetcher.calls[0]["semester"] == SEMESTER
    assert fetcher.calls[0]["page_size"] == 7


# ---------------------------------------------------------------------------
# total == 0
# ---------------------------------------------------------------------------


def test_zero_total_completes_immediately() -> None:
    fetcher = FakePageFetcher({1: _page([], total=0)})

    snapshot = _collect(fetcher)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 0
    assert snapshot.reported_total == 0
    # 不应继续请求下一页
    assert fetcher.page_numbers == [1]


def test_zero_total_with_first_page_no_zero() -> None:
    fetcher = FakePageFetcher({0: _page([], total=0)})

    snapshot = _collect(fetcher, first_page_no=0)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 0
    assert fetcher.page_numbers == [0]


# ---------------------------------------------------------------------------
# max_pages 安全阀 → partial
# ---------------------------------------------------------------------------


def test_max_pages_truncation_returns_partial() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 2), total=6),
            2: _page(_rows_for("02", 2), total=6),
        }
    )

    snapshot = _collect(fetcher, max_pages=2)

    assert snapshot.is_complete is False
    assert snapshot.completeness == "partial"
    assert snapshot.loaded_count == 4
    assert snapshot.reported_total == 6
    assert fetcher.page_numbers == [1, 2]


def test_max_pages_one_returns_partial_when_not_full() -> None:
    fetcher = FakePageFetcher({1: _page(_rows_for("01", 1), total=5)})

    snapshot = _collect(fetcher, max_pages=1)

    assert snapshot.is_complete is False
    assert snapshot.reported_total == 5
    assert snapshot.loaded_count == 1


def test_max_pages_is_a_safety_valve_not_a_page_count() -> None:
    """取满时**提前停止**，不会为了凑满 `max_pages` 多取页。"""

    fetcher = FakePageFetcher({1: _page(_rows_for("01", 2), total=2)})

    snapshot = _collect(fetcher, max_pages=50)

    assert snapshot.is_complete is True
    assert fetcher.page_numbers == [1]


# ---------------------------------------------------------------------------
# total 一致性
# ---------------------------------------------------------------------------


def test_total_change_on_second_page_fails() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 2), total=6),
            2: _page(_rows_for("02", 2), total=5),
        }
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _collect(fetcher)

    assert "reported_total" in str(excinfo.value)


def test_total_increase_on_second_page_fails() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 2), total=4),
            2: _page(_rows_for("02", 2), total=5),
        }
    )

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher)


# ---------------------------------------------------------------------------
# 空页 / 超限
# ---------------------------------------------------------------------------


def test_empty_page_before_total_fails() -> None:
    """达到 `total` 之前出现空页 → 分页提前停滞，必须失败。"""

    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 2), total=6),
            2: _page([], total=6),
        }
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _collect(fetcher)

    assert "空" in str(excinfo.value)


def test_accumulated_greater_than_total_fails() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 2), total=3),
            2: _page(_rows_for("02", 2), total=3),
        }
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _collect(fetcher)

    assert "超过" in str(excinfo.value)


def test_page_with_more_rows_than_total_fails() -> None:
    """单页行数就超过 `total`：由每页 `OfferingSnapshot` 直接拦下。"""

    fetcher = FakePageFetcher({1: _page(_rows_for("01", 3), total=2)})

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher)


# ---------------------------------------------------------------------------
# 跨页重复
# ---------------------------------------------------------------------------


def test_duplicate_class_across_pages_fails() -> None:
    """分页器**不自行去重**：跨页重复交给 `OfferingSnapshot` 判定并失败。"""

    duplicated = _row("6200100120260101")
    fetcher = FakePageFetcher(
        {
            1: _page([duplicated], total=2),
            2: _page([dict(duplicated)], total=2),
        }
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        _collect(fetcher)

    assert "重复" in str(excinfo.value)


def test_same_course_different_classes_across_pages_are_kept() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page([_row("6200100120260101")], total=2),
            2: _page([_row("6200100120260102")], total=2),
        }
    )

    snapshot = _collect(fetcher)

    assert snapshot.loaded_count == 2
    assert [item.class_id for item in snapshot.offerings] == [
        "6200100120260101",
        "6200100120260102",
    ]


# ---------------------------------------------------------------------------
# 顺序
# ---------------------------------------------------------------------------


def test_page_and_row_order_are_preserved() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(
                [_row("6200100120260103"), _row("6200100120260101")], total=4
            ),
            2: _page(
                [_row("6200100120260102"), _row("6200100120260104")], total=4
            ),
        }
    )

    snapshot = _collect(fetcher)

    assert [item.class_id for item in snapshot.offerings] == [
        "6200100120260103",
        "6200100120260101",
        "6200100120260102",
        "6200100120260104",
    ]


# ---------------------------------------------------------------------------
# 失败传播
# ---------------------------------------------------------------------------


def test_fetcher_exception_propagates() -> None:
    fetcher = ExplodingPageFetcher()

    with pytest.raises(ExplodingPageFetcher.BoomError):
        _collect(fetcher)

    assert fetcher.calls == 1


def test_second_page_fetch_exception_propagates() -> None:
    class SecondPageBoom(FakePageFetcher):
        def fetch_page(self, *, semester: str, page_no: int, page_size: int):
            if page_no == 2:
                raise RuntimeError("second page failed")
            return super().fetch_page(
                semester=semester, page_no=page_no, page_size=page_size
            )

    fetcher = SecondPageBoom({1: _page(_rows_for("01", 1), total=3)})

    with pytest.raises(RuntimeError):
        _collect(fetcher)


def test_parser_failure_on_any_page_fails_whole_collection() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 1), total=2),
            2: _page([_row("6200100120260102", teachingTimePlaceStr="不是合法格式")], total=2),
        }
    )

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher)


def test_malformed_response_on_second_page_fails_whole_collection() -> None:
    fetcher = FakePageFetcher(
        {
            1: _page(_rows_for("01", 1), total=2),
            2: {"code": 500, "data": {"total": 2, "rows": []}},
        }
    )

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher)


def test_semester_mismatch_in_row_fails() -> None:
    fetcher = FakePageFetcher(
        {1: _page([_row("6200100120260101", yearTerm="2026-2")], total=1)}
    )

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher)


def test_data_source_is_real_for_collected_offerings() -> None:
    fetcher = FakePageFetcher({1: _page(_rows_for("01", 1), total=1)})

    snapshot = _collect(fetcher)

    assert all(item.data_source is DataSource.REAL for item in snapshot.offerings)
    assert snapshot.offerings[0].source == SOURCE


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page_size", [0, -1, "2", 2.0, True, None])
def test_invalid_page_size_is_rejected(page_size: object) -> None:
    fetcher = FakePageFetcher({1: _page([], total=0)})

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher, page_size=page_size)  # type: ignore[arg-type]

    assert fetcher.calls == []


@pytest.mark.parametrize("first_page_no", [-1, "0", 0.0, True, None])
def test_invalid_first_page_no_is_rejected(first_page_no: object) -> None:
    fetcher = FakePageFetcher({0: _page([], total=0)})

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher, first_page_no=first_page_no)  # type: ignore[arg-type]

    assert fetcher.calls == []


@pytest.mark.parametrize("max_pages", [0, -1, "1", 1.0, True, None])
def test_invalid_max_pages_is_rejected(max_pages: object) -> None:
    fetcher = FakePageFetcher({1: _page([], total=0)})

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher, max_pages=max_pages)  # type: ignore[arg-type]

    assert fetcher.calls == []


@pytest.mark.parametrize("semester", ["", "   ", None, 123])
def test_invalid_semester_is_rejected(semester: object) -> None:
    fetcher = FakePageFetcher({1: _page([], total=0)})

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher, semester=semester)  # type: ignore[arg-type]

    assert fetcher.calls == []


@pytest.mark.parametrize("source", ["", "   ", None, 123])
def test_invalid_source_is_rejected(source: object) -> None:
    fetcher = FakePageFetcher({1: _page([], total=0)})

    with pytest.raises(CourseDataNormalizationError):
        _collect(fetcher, source=source)  # type: ignore[arg-type]

    assert fetcher.calls == []
