"""Capture Bridge 测试（Phase 2B-2C1A，**零网络**）。

⚠️ **数据最小化**：所有 Capture Bundle 与 Raw row 均为**人工虚构**；
**不使用**真实 Capture Bundle、真实教师姓名、真实教室、内部 ID 取值、认证信息。

覆盖重点：bundle 结构与页码连续性校验、`CapturedPagesFetcher` 回放、
**复用** Pagination Core 判定 `partial` / `complete`、以及失败路径整体失败。
"""

from __future__ import annotations

import ast
import inspect
import json

import pytest

import app.course_data.captured_pages as captured_pages_module
from app.course_data import (
    CAPTURE_FORMAT,
    CapturedPagesFetcher,
    CourseDataNormalizationError,
    OpeningCoursesPageFetcher,
    collect_captured_pages_snapshot,
    load_capture_bundle,
    validate_capture_bundle,
)
from app.models.contracts import DataSource

SEMESTER = "2026-1"
SOURCE = "mock://capture-bridge-test"
TEACHER_PLACEHOLDER = "示例教师A"
ACTIVITY = "示例环节"
SCHEDULE = f"1-8周/星期五/第5-6节/{TEACHER_PLACEHOLDER}/{ACTIVITY},"


# ---------------------------------------------------------------------------
# 人工虚构的 Capture Bundle 构造器
# ---------------------------------------------------------------------------


def _row(class_number: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "courseNum": "62001001",
        "courseName": "离散数学",
        "classNumber": class_number,
        "yearTerm": SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": SCHEDULE,
    }
    row.update(overrides)
    return row


def _rows(prefix: str, count: int) -> list[dict[str, object]]:
    return [_row(f"620010012026{prefix}{index:02d}") for index in range(count)]


def _bundle(
    pages: list[tuple[int, dict[str, object]]],
    *,
    first_page_no: int = 1,
    page_size: int = 200,
    semester: str = SEMESTER,
    bundle_format: str = CAPTURE_FORMAT,
) -> dict[str, object]:
    return {
        "format": bundle_format,
        "semester": semester,
        "first_page_no": first_page_no,
        "page_size": page_size,
        "pages": [
            {"page_no": page_no, "response": response} for page_no, response in pages
        ],
    }


def _response(rows: list[dict[str, object]], *, total: int, code: int = 200) -> dict[str, object]:
    return {"code": code, "data": {"total": total, "rows": rows}}


def _two_page_bundle(*, total: int = 6) -> dict[str, object]:
    return _bundle(
        [
            (1, _response(_rows("01", 2), total=total)),
            (2, _response(_rows("02", 2), total=total)),
        ]
    )


# ---------------------------------------------------------------------------
# 结构 / 边界
# ---------------------------------------------------------------------------


def test_captured_fetcher_satisfies_frozen_page_fetcher_protocol() -> None:
    fetcher = CapturedPagesFetcher(_two_page_bundle())

    assert isinstance(fetcher, OpeningCoursesPageFetcher)


def test_bridge_module_has_no_network_and_no_integration_imports() -> None:
    """Capture Bridge 零网络，且**不 import Integration**。"""

    tree = ast.parse(inspect.getsource(captured_pages_module))

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")

    forbidden_roots = {
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "socket",
        "selenium",
        "playwright",
    }
    for module in imported_modules:
        root = module.split(".")[0]
        assert root not in forbidden_roots, f"Capture Bridge 出现网络依赖：{module}"
        assert not module.startswith("app.integration"), (
            f"Capture Bridge 不得依赖 Integration：{module}"
        )
        assert "mock_service" not in module, f"Capture Bridge 不得引用 Mock 回放：{module}"


def test_bridge_does_not_touch_provider() -> None:
    """⛔ Capture Bridge 不导入 / 不构造 Provider（partial 不得接产品链路）。"""

    tree = ast.parse(inspect.getsource(captured_pages_module))

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)

    assert "SnapshotCourseDataProvider" not in names
    assert "CourseDataProvider" not in names
    assert not hasattr(captured_pages_module, "SnapshotCourseDataProvider")


def test_metadata_round_trip() -> None:
    fetcher = CapturedPagesFetcher(_two_page_bundle())

    assert fetcher.semester == SEMESTER
    assert fetcher.first_page_no == 1
    assert fetcher.page_size == 200
    assert fetcher.page_count == 2


def test_validate_capture_bundle_accepts_valid_bundle() -> None:
    validate_capture_bundle(_two_page_bundle())


# ---------------------------------------------------------------------------
# partial / complete（由 Pagination Core 判定，Bridge 不重复实现）
# ---------------------------------------------------------------------------


def test_two_page_smoke_capture_is_partial_when_total_not_reached() -> None:
    """2 页 smoke capture + total 未被取满 → **partial**（Bridge 不自行声称 complete）。"""

    snapshot = collect_captured_pages_snapshot(_two_page_bundle(total=6892), source=SOURCE)

    assert snapshot.is_complete is False
    assert snapshot.completeness == "partial"
    assert snapshot.loaded_count == 4
    assert snapshot.reported_total == 6892


def test_full_bundle_is_complete() -> None:
    bundle = _bundle(
        [
            (1, _response(_rows("01", 2), total=4)),
            (2, _response(_rows("02", 2), total=4)),
        ]
    )

    snapshot = collect_captured_pages_snapshot(bundle, source=SOURCE)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 4
    assert snapshot.reported_total == 4


def test_single_page_complete_bundle() -> None:
    bundle = _bundle([(1, _response(_rows("01", 2), total=2))])

    snapshot = collect_captured_pages_snapshot(bundle, source=SOURCE)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 2


def test_zero_total_bundle_is_complete() -> None:
    bundle = _bundle([(1, _response([], total=0))])

    snapshot = collect_captured_pages_snapshot(bundle, source=SOURCE)

    assert snapshot.is_complete is True
    assert snapshot.loaded_count == 0


def test_first_page_no_zero_is_respected() -> None:
    bundle = _bundle(
        [
            (0, _response(_rows("01", 2), total=4)),
            (1, _response(_rows("02", 2), total=4)),
        ],
        first_page_no=0,
    )

    fetcher = CapturedPagesFetcher(bundle)
    snapshot = collect_captured_pages_snapshot(bundle, source=SOURCE)

    assert fetcher.first_page_no == 0
    assert snapshot.is_complete is True


def test_page_size_is_respected() -> None:
    bundle = _bundle([(1, _response(_rows("01", 1), total=1))], page_size=50)

    fetcher = CapturedPagesFetcher(bundle)

    assert fetcher.page_size == 50
    assert collect_captured_pages_snapshot(bundle, source=SOURCE).is_complete is True


def test_data_source_is_real_and_source_is_supplied_by_caller() -> None:
    snapshot = collect_captured_pages_snapshot(_two_page_bundle(), source=SOURCE)

    assert all(item.data_source is DataSource.REAL for item in snapshot.offerings)
    assert snapshot.offerings[0].source == SOURCE


# ---------------------------------------------------------------------------
# Bundle 校验失败
# ---------------------------------------------------------------------------


def test_missing_metadata_is_rejected() -> None:
    bundle = _two_page_bundle()
    del bundle["first_page_no"]

    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(bundle)


@pytest.mark.parametrize("bundle_format", ["", "v0", "sysu-opening-courses-capture-v2", None])
def test_wrong_format_is_rejected(bundle_format: object) -> None:
    with pytest.raises(CourseDataNormalizationError) as excinfo:
        CapturedPagesFetcher(_two_page_bundle() | {"format": bundle_format})

    assert "format" in str(excinfo.value)


@pytest.mark.parametrize("semester", ["", "   ", None, 123])
def test_wrong_semester_is_rejected(semester: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(_two_page_bundle() | {"semester": semester})


@pytest.mark.parametrize("first_page_no", [-1, "1", 1.0, True, None])
def test_invalid_first_page_no_is_rejected(first_page_no: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(_two_page_bundle() | {"first_page_no": first_page_no})


@pytest.mark.parametrize("page_size", [0, -1, "200", 200.0, True, None])
def test_invalid_page_size_is_rejected(page_size: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(_two_page_bundle() | {"page_size": page_size})


@pytest.mark.parametrize("pages", [[], "pages", {"1": {}}, None])
def test_invalid_pages_container_is_rejected(pages: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(_two_page_bundle() | {"pages": pages})


def test_page_entry_missing_keys_is_rejected() -> None:
    bundle = _two_page_bundle()
    bundle["pages"] = [{"page_no": 1}]

    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(bundle)


def test_non_mapping_response_is_rejected() -> None:
    bundle = _bundle([(1, ["not", "a", "mapping"])])  # type: ignore[list-item]

    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(bundle)


def test_non_mapping_bundle_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(["not", "a", "bundle"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 页码连续性
# ---------------------------------------------------------------------------


def test_duplicate_page_no_is_rejected() -> None:
    bundle = _bundle(
        [
            (1, _response(_rows("01", 1), total=2)),
            (1, _response(_rows("02", 1), total=2)),
        ]
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        CapturedPagesFetcher(bundle)

    assert "重复" in str(excinfo.value)


def test_missing_page_is_rejected_without_sorting() -> None:
    """`1,3`（缺 2）**不得**被排序修复，直接失败。"""

    bundle = _bundle(
        [
            (1, _response(_rows("01", 1), total=3)),
            (3, _response(_rows("03", 1), total=3)),
        ]
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        CapturedPagesFetcher(bundle)

    assert "连续" in str(excinfo.value)


def test_pages_starting_after_first_page_no_is_rejected() -> None:
    """bundle 元数据写 `first_page_no=1`，但实际页从 2 开始 → 失败（不自动纠正）。"""

    bundle = _bundle(
        [
            (2, _response(_rows("02", 1), total=2)),
            (3, _response(_rows("03", 1), total=2)),
        ]
    )

    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(bundle)


def test_out_of_order_pages_are_rejected() -> None:
    bundle = _bundle(
        [
            (2, _response(_rows("02", 1), total=2)),
            (1, _response(_rows("01", 1), total=2)),
        ]
    )

    with pytest.raises(CourseDataNormalizationError):
        CapturedPagesFetcher(bundle)


# ---------------------------------------------------------------------------
# 回放器自身
# ---------------------------------------------------------------------------


def test_fetcher_returns_captured_response_for_known_page() -> None:
    bundle = _two_page_bundle()
    fetcher = CapturedPagesFetcher(bundle)

    response = fetcher.fetch_page(semester=SEMESTER, page_no=2, page_size=200)

    assert response is bundle["pages"][1]["response"]


def test_fetcher_rejects_unknown_page() -> None:
    fetcher = CapturedPagesFetcher(_two_page_bundle())

    with pytest.raises(CourseDataNormalizationError):
        fetcher.fetch_page(semester=SEMESTER, page_no=9, page_size=200)


def test_fetcher_rejects_semester_mismatch() -> None:
    fetcher = CapturedPagesFetcher(_two_page_bundle())

    with pytest.raises(CourseDataNormalizationError):
        fetcher.fetch_page(semester="2026-2", page_no=1, page_size=200)


def test_fetcher_rejects_page_size_mismatch() -> None:
    fetcher = CapturedPagesFetcher(_two_page_bundle())

    with pytest.raises(CourseDataNormalizationError):
        fetcher.fetch_page(semester=SEMESTER, page_no=1, page_size=100)


# ---------------------------------------------------------------------------
# 由 Pagination Core 判定的失败路径
# ---------------------------------------------------------------------------


def test_total_change_between_pages_fails() -> None:
    bundle = _bundle(
        [
            (1, _response(_rows("01", 2), total=6)),
            (2, _response(_rows("02", 2), total=5)),
        ]
    )

    with pytest.raises(CourseDataNormalizationError):
        collect_captured_pages_snapshot(bundle, source=SOURCE)


def test_malformed_response_on_second_page_fails() -> None:
    bundle = _bundle(
        [
            (1, _response(_rows("01", 1), total=2)),
            (2, {"code": 500, "data": {"total": 2, "rows": []}}),
        ]
    )

    with pytest.raises(CourseDataNormalizationError):
        collect_captured_pages_snapshot(bundle, source=SOURCE)


def test_parser_failure_fails_whole_bundle() -> None:
    bundle = _bundle(
        [
            (1, _response(_rows("01", 1), total=2)),
            (
                2,
                _response(
                    [_row("6200100120260102", teachingTimePlaceStr="不是合法格式")], total=2
                ),
            ),
        ]
    )

    with pytest.raises(CourseDataNormalizationError):
        collect_captured_pages_snapshot(bundle, source=SOURCE)


def test_duplicate_class_across_pages_fails() -> None:
    bundle = _bundle(
        [
            (1, _response([_row("6200100120260101")], total=2)),
            (2, _response([_row("6200100120260101")], total=2)),
        ]
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        collect_captured_pages_snapshot(bundle, source=SOURCE)

    assert "重复" in str(excinfo.value)


def test_empty_page_before_total_fails() -> None:
    bundle = _bundle(
        [
            (1, _response(_rows("01", 2), total=6)),
            (2, _response([], total=6)),
        ]
    )

    with pytest.raises(CourseDataNormalizationError):
        collect_captured_pages_snapshot(bundle, source=SOURCE)


@pytest.mark.parametrize("source", ["", "   ", None, 123])
def test_invalid_source_is_rejected(source: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        collect_captured_pages_snapshot(_two_page_bundle(), source=source)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 本地文件读取（仅 tmp_path + 人工虚构 JSON）
# ---------------------------------------------------------------------------


def test_load_capture_bundle_reads_valid_file(tmp_path) -> None:
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(_two_page_bundle()), encoding="utf-8")

    bundle = load_capture_bundle(path)

    assert bundle["format"] == CAPTURE_FORMAT
    assert collect_captured_pages_snapshot(bundle, source=SOURCE).completeness == "partial"


def test_load_capture_bundle_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(CourseDataNormalizationError) as excinfo:
        load_capture_bundle(tmp_path / "not-there.json")

    assert "不存在" in str(excinfo.value)


def test_load_capture_bundle_rejects_invalid_json(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        load_capture_bundle(path)

    assert "JSON" in str(excinfo.value)


def test_load_capture_bundle_rejects_invalid_bundle(tmp_path) -> None:
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"format": "nope"}), encoding="utf-8")

    with pytest.raises(CourseDataNormalizationError):
        load_capture_bundle(path)


def test_load_capture_bundle_requires_explicit_path() -> None:
    """⛔ 不提供默认路径（调用方必须显式给出文件）。"""

    with pytest.raises(TypeError):
        load_capture_bundle()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 错误信息隐私
# ---------------------------------------------------------------------------


def test_error_messages_do_not_echo_raw_rows() -> None:
    """错误信息不得回显 Raw row 内容或 teachingTimePlaceStr 原文。"""

    secret_marker = "机密教师"
    bundle = _bundle(
        [
            (
                1,
                _response(
                    [_row("6200100120260101", teachingTimePlaceStr=f"1-8周/星期五/第5-6节/{secret_marker}/示例环节,")],
                    total=1,
                ),
            )
        ]
    )
    bundle["page_size"] = 0

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        CapturedPagesFetcher(bundle)

    assert secret_marker not in str(excinfo.value)
