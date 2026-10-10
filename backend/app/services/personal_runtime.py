"""Personal Planning runtime 装配边界（**fail closed**，非公共契约）。

```text
APP_PERSONAL_CATALOG_DIR=<显式给出的本地已核验目录>
APP_TRUST_ANCHOR_PATH=<带外批准锚点：哪些 version_id 真的被人工批准>
        ↓  load_personal_catalog(environment)
CurriculumCatalog（可选版本目录；目录缺失 = 没有可选版本，⛔ 不猜默认值）
```

## 为什么单独一个模块

与 `app/services/planning_runtime.py`（已冻结的 Case A runtime）**完全无关**：

- ⛔ **不读** Case A 的五个环境变量，也⛔ 不改动它们；
- ⛔ **不联网**、⛔ **不读 `mock_data`**、⛔ **不扫描文件系统猜输入**；
- ⛔ **没有 Mock fallback**：目录未配置就是"当前没有可选版本"，
  API 明确回答"无可用版本"，⛔ 不回退到 Case A 或任何演示方案。

## 来源可信性（本轮新增）

`catalog.json` 的 `verification.verified=true` 是**自述布尔**，
因此本模块额外要求 `APP_TRUST_ANCHOR_PATH` 指向的**带外批准锚点**里
存在对应的 `curriculum_catalog` 批准记录。⛔ 缺锚点 ⇒ 不放出任何版本。

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
from app.provenance import (
    APPROVAL_KIND_CURRICULUM_CATALOG,
    TrustAnchorUnavailable,
    load_trust_anchor,
)

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
    """按**显式**环境配置装载已核验目录；未配置 / 不可用即 fail closed。

    ⚠️ **本轮修复（F-03）**：`catalog.json` 里的 `verification.verified=true`
    只是自述布尔。因此这里额外要求**带外批准锚点**
    （`APP_TRUST_ANCHOR_PATH`，见 `app.provenance`）里存在对应的
    `curriculum_catalog` 批准记录：

    - 锚点缺失 / 不可读 / 非法 ⇒ `provenance_not_verified`（⛔ 不退回只按自述）；
    - 锚点里没有已批准的 `version_id` ⇒ 该目录装载结果**没有可选版本**
      （`catalog_provenance_empty`），⛔ 不放出任何自述版本。
    """

    if not isinstance(environment, Mapping):
        raise CurriculumNormalizationError("runtime: expected an environment mapping")
    directory = environment.get(PERSONAL_CATALOG_DIR)
    if directory is None or not str(directory).strip():
        return PersonalCatalogInspection(None, "catalog_not_configured")

    # ---- 独立批准锚点（F-03）--------------------------------------------
    try:
        anchor = load_trust_anchor(environment)
    except TrustAnchorUnavailable:
        return PersonalCatalogInspection(None, "provenance_not_verified")
    approved = frozenset(
        record.identity_map()["version_id"]
        for record in anchor.matching(APPROVAL_KIND_CURRICULUM_CATALOG)
    )
    if not approved:
        return PersonalCatalogInspection(None, "catalog_provenance_empty")

    try:
        catalog = load_curriculum_catalog(
            str(directory).strip(), approved_versions=approved,
        )
    except CurriculumNormalizationError:
        return PersonalCatalogInspection(None, "catalog_not_ready")
    if not catalog.inspection.format_supported:
        return PersonalCatalogInspection(None, "catalog_format_unsupported")
    return PersonalCatalogInspection(catalog, "ready")


def inspect_personal_catalog() -> PersonalCatalogInspection:
    """检查**当前进程环境**中的目录（⛔ 不打印任何配置取值）。"""

    return load_personal_catalog(os.environ)
