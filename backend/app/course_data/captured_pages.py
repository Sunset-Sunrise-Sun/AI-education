"""Capture Bridge：把本地 Capture Bundle 回放给已有的分页核心（**零网络**）。

```text
已登录浏览器（用户显式触发）
        ↓  tools/sysu_course_offering_collector.js
本地 Capture Bundle（Real Sanitized Capture，**不入 Git**）
        ↓  CapturedPagesFetcher（只回放，不访问网络）
collect_opening_courses_snapshot()（已有的分页核心）
        ↓
OfferingSnapshot
```

## Capture Bundle 是 Course Data **内部**交换格式

- ⛔ **不是**公共 Schema：不进 `/schemas/`、不进 `/docs/interfaces/`；
- 结构（v1）：

```json
{
  "format": "sysu-opening-courses-capture-v1",
  "semester": "2026-1",
  "first_page_no": 1,
  "page_size": 200,
  "pages": [{"page_no": 1, "response": {"code": 200, "data": {"total": 0, "rows": []}}}]
}
```

- bundle **不含** `source`（由 Python 调用方显式给出）、
  **不含**认证信息 / 会话、**不含**用户标识、**不含**姓名学号、
  **不含**内部长 ID、**不含**教师姓名（采集器已在 segment 内脱敏为 `REDACTED`）。

## 本模块做什么

- 校验 bundle 的结构与分页连续性（**不排序修复**，有问题直接失败）；
- `CapturedPagesFetcher`：结构上满足 `OpeningCoursesPageFetcher`，**只回放已捕获的页**；
- `collect_captured_pages_snapshot()`：把 bundle 交给**已有的** `collect_opening_courses_snapshot()`。

## 本模块不做什么

- ⛔ **不访问网络**：没有 endpoint、没有认证处理、没有重试；
- ⛔ **不重新实现** completeness：`complete` / `partial` 一律由分页核心依据证据链判定；
- ⛔ **不 import Integration**（bundle 仍在 Course Data 内部）；
- ⛔ 不读取 / 不打印任何真实 Raw row。

## 隐私

错误信息只输出**结构性**信息（page_no、字段名、格式名），
**不输出** Raw row、`teachingTimePlaceStr` 原文、teacher 或任何认证信息。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.pagination import collect_opening_courses_snapshot
from app.course_data.snapshot import OfferingSnapshot

__all__ = [
    "CAPTURE_FORMAT",
    "CapturedPagesFetcher",
    "collect_captured_pages_snapshot",
    "load_capture_bundle",
    "validate_capture_bundle",
]

#: Capture Bundle 的格式标识（v1）。
CAPTURE_FORMAT = "sysu-opening-courses-capture-v1"

_REQUIRED_METADATA_KEYS = ("format", "semester", "first_page_no", "page_size", "pages")


@dataclass(frozen=True)
class _CapturedBundle:
    """校验通过的 bundle（内部结构）。"""

    semester: str
    first_page_no: int
    page_size: int
    pages: tuple[tuple[int, Mapping[str, object]], ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)


def _require_int(value: object, name: str, *, minimum: int) -> int:
    """整数校验（`bool` 不算整数）；非法即 fail closed。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise CourseDataNormalizationError(
            f"Capture Bundle 的 {name} 必须是整数，实际是 {type(value).__name__}：{value!r}"
        )
    if value < minimum:
        raise CourseDataNormalizationError(
            f"Capture Bundle 的 {name} 必须 >= {minimum}，实际是 {value}"
        )
    return value


def _parse_capture_bundle(bundle: object) -> _CapturedBundle:
    """校验 Capture Bundle（**不做任何排序修复**，不合法直接失败）。"""

    if not isinstance(bundle, Mapping):
        raise CourseDataNormalizationError(
            f"Capture Bundle 必须是对象，实际是 {type(bundle).__name__}"
        )

    missing = [key for key in _REQUIRED_METADATA_KEYS if key not in bundle]
    if missing:
        raise CourseDataNormalizationError(f"Capture Bundle 缺少字段：{missing}")

    bundle_format = bundle["format"]
    if bundle_format != CAPTURE_FORMAT:
        raise CourseDataNormalizationError(
            f"Capture Bundle 的 format 不是 {CAPTURE_FORMAT}（实际 {bundle_format!r}）"
        )

    semester = bundle["semester"]
    if not isinstance(semester, str) or not semester.strip():
        raise CourseDataNormalizationError(
            f"Capture Bundle 的 semester 必须是非空字符串，实际是 {type(semester).__name__}"
        )

    first_page_no = _require_int(bundle["first_page_no"], "first_page_no", minimum=0)
    page_size = _require_int(bundle["page_size"], "page_size", minimum=1)

    pages = bundle["pages"]
    if isinstance(pages, (str, bytes)) or not isinstance(pages, Sequence) or not pages:
        raise CourseDataNormalizationError(
            f"Capture Bundle 的 pages 必须是非空数组，实际是 {type(pages).__name__}"
        )

    parsed_pages: list[tuple[int, Mapping[str, object]]] = []
    seen_page_numbers: set[int] = set()

    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            raise CourseDataNormalizationError(
                f"Capture Bundle 的 pages[{index}] 必须是对象，实际是 {type(page).__name__}"
            )
        if "page_no" not in page or "response" not in page:
            raise CourseDataNormalizationError(
                f"Capture Bundle 的 pages[{index}] 必须同时包含 page_no 与 response"
            )

        page_no = _require_int(page["page_no"], f"pages[{index}].page_no", minimum=0)

        if page_no in seen_page_numbers:
            raise CourseDataNormalizationError(
                f"Capture Bundle 出现重复的 page_no：{page_no}"
            )
        seen_page_numbers.add(page_no)

        expected_page_no = first_page_no + index
        if page_no != expected_page_no:
            # ⛔ 不排序修复：页码必须从 first_page_no 开始连续。
            raise CourseDataNormalizationError(
                f"Capture Bundle 的页码不连续：第 {index} 项是 {page_no}，"
                f"按 first_page_no({first_page_no}) 应为 {expected_page_no}；本层不排序修复"
            )

        response = page["response"]
        if not isinstance(response, Mapping):
            raise CourseDataNormalizationError(
                f"Capture Bundle 的 pages[{index}].response 必须是对象，"
                f"实际是 {type(response).__name__}"
            )

        parsed_pages.append((page_no, response))

    return _CapturedBundle(
        semester=semester,
        first_page_no=first_page_no,
        page_size=page_size,
        pages=tuple(parsed_pages),
    )


def validate_capture_bundle(bundle: object) -> None:
    """校验 Capture Bundle；不合法时抛 `CourseDataNormalizationError`。"""

    _parse_capture_bundle(bundle)


class CapturedPagesFetcher:
    """回放 Capture Bundle 中**已经捕获的**页（**零网络**）。

    - 结构上满足 Phase 2B-2C1A 之前的 `OpeningCoursesPageFetcher`，
      但**不继承、不修改**该 Protocol；
    - 只返回 bundle 中对应 `page_no` 的原始 response；
    - 请求的 `semester` / `page_size` / `page_no` 与 bundle 不一致时**直接失败**
      （避免把 A 学期 / 别的页大小的数据当成当前采集结果）。
    """

    def __init__(self, bundle: Mapping[str, object]) -> None:
        parsed = _parse_capture_bundle(bundle)
        self._semester = parsed.semester
        self._first_page_no = parsed.first_page_no
        self._page_size = parsed.page_size
        self._responses: dict[int, Mapping[str, object]] = {
            page_no: response for page_no, response in parsed.pages
        }

    @property
    def semester(self) -> str:
        return self._semester

    @property
    def first_page_no(self) -> int:
        return self._first_page_no

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def page_count(self) -> int:
        return len(self._responses)

    def fetch_page(
        self,
        *,
        semester: str,
        page_no: int,
        page_size: int,
    ) -> Mapping[str, object]:
        if semester != self._semester:
            raise CourseDataNormalizationError(
                f"Capture Bundle 只包含 {self._semester} 的数据，"
                f"无法回放 semester={semester!r}"
            )
        if page_size != self._page_size:
            raise CourseDataNormalizationError(
                f"Capture Bundle 的 page_size 是 {self._page_size}，无法按 {page_size} 回放"
            )
        if page_no not in self._responses:
            raise CourseDataNormalizationError(
                f"Capture Bundle 中没有 page_no={page_no}（已捕获 "
                f"{self._first_page_no}..{self._first_page_no + self.page_count - 1}）"
            )
        return self._responses[page_no]


def collect_captured_pages_snapshot(
    bundle: Mapping[str, object],
    *,
    source: str,
) -> OfferingSnapshot:
    """把 Capture Bundle 转成 `OfferingSnapshot`（**复用**分页核心，不重新实现完整性）。

    - `max_pages` 取 **bundle 中已捕获的页数**：因此 2 页 smoke capture
      在 `total` 未被取满时必然得到 `partial`；
    - `complete` / `partial` 由 `collect_opening_courses_snapshot()` 依据证据链判定；
    - `source` 由调用方显式给出（bundle 中**不含** source）。
    """

    fetcher = CapturedPagesFetcher(bundle)

    return collect_opening_courses_snapshot(
        fetcher,
        semester=fetcher.semester,
        source=source,
        page_size=fetcher.page_size,
        first_page_no=fetcher.first_page_no,
        max_pages=fetcher.page_count,
    )


def load_capture_bundle(path: str | Path) -> Mapping[str, object]:
    """从**本地** UTF-8 JSON 文件读取 Capture Bundle（stdlib `json`，无新依赖）。

    - 只读取调用方给出的**具体文件**：不提供默认路径、不扫描目录、不复制进仓库；
    - 读取后立即做与内存 bundle 相同的校验。
    """

    file_path = Path(path)

    try:
        raw = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CourseDataNormalizationError(f"Capture Bundle 文件不存在：{file_path}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CourseDataNormalizationError(
            f"Capture Bundle 不是合法 JSON：{file_path}（第 {exc.lineno} 行第 {exc.colno} 列）"
        ) from exc

    validate_capture_bundle(payload)

    if not isinstance(payload, Mapping):
        # 防御性：validate 已经拦下，这里只是让类型收敛。
        raise CourseDataNormalizationError("Capture Bundle 必须是对象")

    return payload
