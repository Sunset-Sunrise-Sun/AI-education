"""Course Data 内部异常。

**不建立复杂异常层级**：Course Data 只需要一个明确的"标准化 / 校验失败"信号，
让调用方知道"这条数据不能变成合法的 `CourseOffering`"，而不是自己去猜一个值。
"""

from __future__ import annotations

__all__ = ["CourseDataNormalizationError"]


class CourseDataNormalizationError(ValueError):
    """已确认字段的标准化 / 校验失败（Course Data 内部）。

    触发场景（**只在这几种情况下抛出，且一律"拒绝"而不是"猜一个值"**）：

    - 缺少必要字段；
    - 字段类型不符合**已确认语义**（例如 `score` 不是字符串数字、`limitNumber` 不是整数）；
    - **不支持的周次格式**（当前只支持 `1-17周` 与 `1-17单周`）；
    - 负容量、或 `selectedNumber > limitNumber`；
    - `meetings` 为空；
    - snapshot 自相矛盾（`semester` 混入、Mock 混入、同一教学班重复、completeness 不成立）。

    继承 `ValueError`：这是"数据不合法"，不是运行环境故障。
    """
