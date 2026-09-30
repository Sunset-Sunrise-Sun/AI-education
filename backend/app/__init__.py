"""组长模块（Agent / Integration）后端集成底座。

当前阶段只提供：
- 可启动的 FastAPI 服务；
- 与 `/schemas/` 公共契约一致的数据模型；
- 基于 Mock 数据的演示接口。

不包含任何上游业务算法（培养方案解析、等价判定、冲突求解、Path Repair）。
"""

__all__ = ["__version__"]

# 后端集成底座版本。与 /schemas/ 的契约版本无关，仅用于标识本次底座实现。
__version__ = "0.1.0"
