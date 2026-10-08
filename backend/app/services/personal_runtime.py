"""Personal Planning runtime 装配边界（**fail closed**，非公共契约）。

```text
APP_PERSONAL_CATALOG_DIR=<显式给出的本地已核验目录>
        ↓  load_personal_catalog(environment)
CurriculumCatalog（可选版本目录；目录缺失 = 没有可选版本，⛔ 不猜默认值）
```

## 为什么单独一个模块

与 `app/services/planning_runtime.py`（已冻结的 Case A runtime）**完全无关**：

- ⛔ **不读** Case A 的五个环境变量，也⛔ 不改动它们；
- ⛔ **不联网**、⛔ **不读 `mock_data`**、⛔ **不扫描文件系统猜输入**；
- ⛔ **没有 Mock fallback**：目录未配置就是"当前没有可选版本"，
  API 明确回答"无可用版本"，⛔ 不回退到 Case A 或任何演示方案。

## 诊断边界

诊断只包含**固定原因码**与**artifact 内的 version_id / 行号**，
⛔ **不含**目录路径、⛔ 不含任何学生数据、⛔ 不含配置取值。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from app.curriculum.catalog import CurriculumCatalog, load_curriculum_catalog
from app.curriculum.errors import CurriculumNormalizationError

__all__ = [
    "PERSONAL_CATALOG_DIR",
    "PersonalCatalogInspection",
    "inspect_personal_catalog",
    "load_personal_catalog",
]

#: 已核验培养方案目录的本地路径（**缺省即未配置**）。
PERSONAL_CATALOG_DIR = "APP_PERSONAL_CATALOG_DIR"


@dataclass(frozen=True, slots=True)
class PersonalCatalogInspection:
    """一次目录装配的结果：可用目录或固定原因码。"""

    catalog: CurriculumCatalog | None
    reason: str

    @property
    def ready(self) -> bool:
        return self.catalog is not None


def load_personal_catalog(environment: Mapping[str, str]) -> PersonalCatalogInspection:
    """按**显式**环境配置装载已核验目录；未配置 / 不可用即 fail closed。"""

    if not isinstance(environment, Mapping):
        raise CurriculumNormalizationError("runtime: expected an environment mapping")
    directory = environment.get(PERSONAL_CATALOG_DIR)
    if directory is None or not str(directory).strip():
        return PersonalCatalogInspection(None, "catalog_not_configured")
    try:
        catalog = load_curriculum_catalog(str(directory).strip())
    except CurriculumNormalizationError:
        return PersonalCatalogInspection(None, "catalog_not_ready")
    if not catalog.inspection.format_supported:
        return PersonalCatalogInspection(None, "catalog_format_unsupported")
    return PersonalCatalogInspection(catalog, "ready")


def inspect_personal_catalog() -> PersonalCatalogInspection:
    """检查**当前进程环境**中的目录（⛔ 不打印任何配置取值）。"""

    return load_personal_catalog(os.environ)
