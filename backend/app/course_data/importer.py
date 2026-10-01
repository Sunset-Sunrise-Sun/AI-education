"""纯本地 Raw-response import adapter（Course Data 内部实现，**零网络**）。

```text
已 decode 的 Raw response（dict）
        ↓  结构校验
        ↓  data.total → reported_total
        ↓  逐行 teachingTimePlaceStr → ParsedScheduleSegment[] → Meeting[]
        ↓  build_course_offering()
        ↓
OfferingSnapshot
```

## 本轮边界

- ✅ 只消费**已经 decode 成 Python object** 的 Raw response；
- ✅ 校验 response 形状、逐行标准化、产出带 completeness 的内部快照；
- ⛔ **不访问网络**：没有 endpoint、没有 Cookie / Session / Token、没有分页请求；
- ⛔ **不做** fallback、重试、"尽力解析"、忽略坏 row；
- ⛔ **不猜 completeness**：必须由调用方明确给出。

真实受控获取（登录、分页、请求规模确认）属于 **Phase 2B-2C**。

## 错误原则：整体失败，不静默跳过

**任意一行失败 → 本次 import 整体失败**（异常直接向上抛）。
不存在"跳过坏 row 继续"的路径 —— 那会让不完整的数据被当成完整快照。

## completeness 由调用方决定

Adapter **不会**因为 `len(rows) == data.total` 就自己宣布 `complete`：
`reported_total` 会原样传给 `OfferingSnapshot`，
最终由 `OfferingSnapshot` 的规则判定（`complete` 必须 `reported_total == loaded_count`）。
Adapter **不重复实现** semester 一致性 / real-only / duplicate key / completeness 这些规则。

## 隐私

错误信息**不回显** teachingTimePlaceStr 原文或其中任何字段取值。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.normalization import build_course_offering
from app.course_data.schedule_parser import extract_meetings, parse_teaching_time_place
from app.course_data.snapshot import OfferingSnapshot
from app.models.contracts import CourseOffering

__all__ = ["import_opening_courses_response"]

#: 已观察到的成功响应码。
_SUCCESS_CODE = 200

#: Raw row 中承载上课时间地点的字段名（已确认存在）。
_SCHEDULE_FIELD = "teachingTimePlaceStr"


def _require_success_code(payload: Mapping[str, object]) -> None:
    if "code" not in payload:
        raise CourseDataNormalizationError("Raw response 缺少 `code` 字段")

    code = payload["code"]
    if isinstance(code, bool) or not isinstance(code, int):
        raise CourseDataNormalizationError(
            f"Raw response 的 `code` 必须是整数，实际是 {type(code).__name__}"
        )
    if code != _SUCCESS_CODE:
        raise CourseDataNormalizationError(
            f"Raw response 的 `code` 不是 {_SUCCESS_CODE}（实际 {code}）；"
            f"本轮只支持已观察到的成功响应"
        )


def _require_data(payload: Mapping[str, object]) -> Mapping[str, object]:
    if "data" not in payload:
        raise CourseDataNormalizationError("Raw response 缺少 `data` 字段")

    data = payload["data"]
    if not isinstance(data, Mapping):
        raise CourseDataNormalizationError(
            f"Raw response 的 `data` 必须是对象，实际是 {type(data).__name__}"
        )
    return data


def _require_total(data: Mapping[str, object]) -> int:
    if "total" not in data:
        raise CourseDataNormalizationError("Raw response 缺少 `data.total`")

    total = data["total"]
    if isinstance(total, bool) or not isinstance(total, int):
        raise CourseDataNormalizationError(
            f"`data.total` 必须是非负整数，实际是 {type(total).__name__}"
        )
    if total < 0:
        raise CourseDataNormalizationError(f"`data.total` 不能为负：{total}")
    return total


def _require_rows(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    if "rows" not in data:
        raise CourseDataNormalizationError("Raw response 缺少 `data.rows`")

    rows = data["rows"]
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise CourseDataNormalizationError(
            f"`data.rows` 必须是数组，实际是 {type(rows).__name__}"
        )

    materials: list[Mapping[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            # ⚠️ 不回显 row 内容（可能含真实数据）。
            raise CourseDataNormalizationError(
                f"`data.rows[{index}]` 必须是对象，实际是 {type(row).__name__}"
            )
        materials.append(row)

    return materials


def _build_offering_from_row(row: Mapping[str, object], *, source: str) -> CourseOffering:
    if _SCHEDULE_FIELD not in row:
        raise CourseDataNormalizationError(f"Raw row 缺少 `{_SCHEDULE_FIELD}` 字段")

    segments = parse_teaching_time_place(row[_SCHEDULE_FIELD])  # type: ignore[arg-type]
    meetings = extract_meetings(segments)

    return build_course_offering(row, meetings=meetings, source=source)


def import_opening_courses_response(
    payload: Mapping[str, object],
    *,
    semester: str,
    source: str,
    completeness: Literal["partial", "complete"],
) -> OfferingSnapshot:
    """把一个已 decode 的成功 Raw response 转成内部 `OfferingSnapshot`。

    参数：

    - `payload` —— 完整 Raw response（`{"code": 200, "data": {"total": ..., "rows": [...]}}`）；
    - `semester` —— 本批数据所属学期（**不校验** row 里的 `yearTerm` 是否相同，
      该一致性由 `OfferingSnapshot` 判定）；
    - `source` —— **由调用方显式提供**的来源标注；
    - `completeness` —— **由调用方明确给出**，Adapter 不猜。

    返回：`OfferingSnapshot`（其本身的规则负责 semester 一致性、real-only、
    duplicate key 与 partial / complete 纪律）。

    任意一行失败 → 整体失败，**不静默跳过**。
    """

    if not isinstance(payload, Mapping):
        raise CourseDataNormalizationError(
            f"Raw response 必须是对象，实际是 {type(payload).__name__}"
        )

    _require_success_code(payload)
    data = _require_data(payload)
    total = _require_total(data)
    rows = _require_rows(data)

    # 按 Raw 顺序逐行处理；不排序、不筛选、不跳过。
    offerings = tuple(_build_offering_from_row(row, source=source) for row in rows)

    return OfferingSnapshot(
        semester=semester,
        offerings=offerings,
        completeness=completeness,
        reported_total=total,
    )
