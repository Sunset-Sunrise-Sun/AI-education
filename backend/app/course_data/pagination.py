"""分页采集核心（Phase 2B-2C0，**零网络**）。

```text
fetch_page(第 1 页) → import_opening_courses_response(..., completeness="partial")
fetch_page(第 2 页) → import_opening_courses_response(..., completeness="partial")
...
        ↓  按原页序 + 原行序聚合
最终 OfferingSnapshot（complete 或 partial）
```

## 本模块做什么

- 定义 **Course Data 内部** `OpeningCoursesPageFetcher` Protocol（**不是** `/docs/interfaces` 公共接口，
  **不加入** Integration）；
- 串行取页、逐页复用**已审核通过的** importer（**不重写** Raw parser / normalizer）；
- 依据**证据链**判定最终 `completeness`，并在 `max_pages` 处安全截断为 `partial`。

## 本模块不做什么

- ⛔ **不实现真实 HTTP**：没有 endpoint、没有 Cookie / Session / Token、没有分页网络请求；
  `fetch_page` 本轮**只能由测试里的 Fake 提供**（真实 Transport 属于 **2B-2C1**）；
- ⛔ **不并发、不预取下一页**：严格串行；
- ⛔ **不重试、不 fallback、不跳页**：fetcher 抛异常或某页解析失败 → **原样向上失败**；
- ⛔ **不自行去重**：不 `set()`、不建 dict、不保留第一条 / 最后一条 ——
  重复判定交给 `OfferingSnapshot` 的 `(semester, course_id, class_id)` 规则；
- ⛔ **本核心不绑定任何具体分页参数**：**不写** `page_size` / `first_page_no` 默认值，
  **不假定** `page_no` 从 1 开始，全部由调用方显式给出。
  SYSU 专有的取值（起始页码、单页上限等）属于**后续 Transport** 的配置，
  **不得硬编码进 Pagination Core** —— 这样核心才能被 Fake 与真实 Transport 复用。

## complete 的证据链（缺一不可）

```text
所有页成功解析
+ 每页 reported_total 一致（与第一页相同，不允许采用最新 / 最大 / 最小值）
+ 累计 loaded_count == reported_total
+ 无重复教学班（由 OfferingSnapshot 判定）
+ 没有中途空页（在达到 total 之前出现空页 → 失败）
+ 没有请求错误（异常直接向上抛）
```

⛔ **不允许**因为"最后一页看起来少一点"或"服务器返回了 total"就直接宣称完整。

## `partial` 的边界

`max_pages` 只是**安全阀**，不是"完整页数"：达到上限仍未取满时，返回
`OfferingSnapshot(completeness="partial")`，如实记录 `reported_total`。

⛔ **本阶段禁止**把 `partial` snapshot 包成生产 `SnapshotCourseDataProvider` 接进 Integration。
`partial` 仅用于**获取规模验证 / 小范围验证 / parser 与 normalizer 验证**，
**不进入 Planner 产品链路**。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.importer import import_opening_courses_response
from app.course_data.snapshot import OfferingSnapshot
from app.models.contracts import CourseOffering

__all__ = [
    "OpeningCoursesPageFetcher",
    "collect_opening_courses_snapshot",
]


@runtime_checkable
class OpeningCoursesPageFetcher(Protocol):
    """取一页 Raw response 的**内部**插座（Course Data 内部接口）。

    ⚠️ 这不是 `/docs/interfaces` 的公共接口，也不加入 Integration。
    真实实现（网络 Transport）属于 **Phase 2B-2C1**；本轮只由测试 Fake 提供。
    """

    def fetch_page(
        self,
        *,
        semester: str,
        page_no: int,
        page_size: int,
    ) -> Mapping[str, object]:
        """返回**该页**的 Raw response（形状与单页导入时一致）。"""
        ...


def _require_non_empty_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CourseDataNormalizationError(
            f"{name} 必须是非空字符串，实际是 {type(value).__name__}：{value!r}"
        )
    return value


def _require_int(value: object, name: str, *, minimum: int) -> int:
    """整数参数校验（`bool` 不算整数）。非法即 fail closed。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise CourseDataNormalizationError(
            f"{name} 必须是整数，实际是 {type(value).__name__}：{value!r}"
        )
    if value < minimum:
        raise CourseDataNormalizationError(f"{name} 必须 >= {minimum}，实际是 {value}")
    return value


def collect_opening_courses_snapshot(
    fetcher: OpeningCoursesPageFetcher,
    *,
    semester: str,
    source: str,
    page_size: int,
    first_page_no: int,
    max_pages: int,
) -> OfferingSnapshot:
    """串行取页并聚合为一个 `OfferingSnapshot`。

    所有分页参数都必须**显式传入**（没有默认值）：

    - `page_size` —— 每页条数；
    - `first_page_no` —— 起始页码（**本核心不假定从 1 开始**，可为 0；
      SYSU 的实际起点由后续 Transport 配置）；
    - `max_pages` —— **安全阀**：最多取多少页；未取满时返回 `partial`。

    返回：

    - 累计数量恰好等于 `reported_total` → `completeness="complete"`；
    - 达到 `max_pages` 仍未取满 → `completeness="partial"`（`reported_total` 如实记录）。

    失败条件（一律 `CourseDataNormalizationError`，**不重试 / 不跳页 / 不 fallback**）：

    - 参数非法；
    - 某页 fetcher 抛异常（原样向上抛）；
    - 某页 Raw 解析失败（由 importer 抛出）；
    - 某页 `reported_total` 与第一页不一致；
    - 在达到 `reported_total` 之前出现**空页**；
    - 累计数量**超过** `reported_total`；
    - 跨页出现**重复教学班**（由 `OfferingSnapshot` 判定）。
    """

    resolved_semester = _require_non_empty_text(semester, "semester")
    resolved_source = _require_non_empty_text(source, "source")
    resolved_page_size = _require_int(page_size, "page_size", minimum=1)
    resolved_first_page_no = _require_int(first_page_no, "first_page_no", minimum=0)
    resolved_max_pages = _require_int(max_pages, "max_pages", minimum=1)

    collected: list[CourseOffering] = []
    accumulated_count = 0
    expected_total: int | None = None

    for page_offset in range(resolved_max_pages):
        page_no = resolved_first_page_no + page_offset

        payload = fetcher.fetch_page(
            semester=resolved_semester,
            page_no=page_no,
            page_size=resolved_page_size,
        )

        # 复用已审核通过的 importer：不重写 Raw parser / normalizer。
        page_snapshot = import_opening_courses_response(
            payload,
            semester=resolved_semester,
            source=resolved_source,
            completeness="partial",
        )

        page_total = page_snapshot.reported_total
        if page_total is None:
            # importer 总会带上 data.total；这里只是防御性检查。
            raise CourseDataNormalizationError(
                f"第 {page_no} 页缺少 reported_total，无法判断分页是否取满"
            )

        if expected_total is None:
            expected_total = page_total
        elif page_total != expected_total:
            # ⛔ 不采用最新值 / 最大值 / 最小值：任意变化都视为数据集合不稳定。
            raise CourseDataNormalizationError(
                f"第 {page_no} 页的 reported_total({page_total}) 与第一页"
                f"({expected_total}) 不一致；分页期间数据集合发生变化，拒绝聚合"
            )

        page_loaded = page_snapshot.loaded_count

        if page_loaded == 0 and accumulated_count < expected_total:
            raise CourseDataNormalizationError(
                f"第 {page_no} 页为空，但累计数量({accumulated_count})仍未达到 "
                f"reported_total({expected_total})；分页在取满之前提前停滞"
            )

        accumulated_count += page_loaded

        if accumulated_count > expected_total:
            raise CourseDataNormalizationError(
                f"累计数量({accumulated_count})超过了 reported_total({expected_total})"
            )

        # 按**原页序 + 原行序**累积，不做任何去重 / 重排。
        collected.extend(page_snapshot.offerings)

        if accumulated_count == expected_total:
            # 已取满：**不再**请求下一页。
            break

    if expected_total is None:
        # max_pages >= 1 保证至少取过一页，因此理论上不可达。
        raise CourseDataNormalizationError("未取得任何页面，无法判定 completeness")

    completeness = "complete" if accumulated_count == expected_total else "partial"

    return OfferingSnapshot(
        semester=resolved_semester,
        offerings=tuple(collected),
        completeness=completeness,
        reported_total=expected_total,
    )
