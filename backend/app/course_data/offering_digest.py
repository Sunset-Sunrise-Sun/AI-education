"""Canonical offering-level digests（Course Data **内部**，**零网络**）。

## 为什么需要它

`artifact_sha256` / `manifest_sha256` 只绑定**字节**或**acceptance 记录**，
它们都**不绑定规范化后的教学班内容**。只比较

```text
offering_count          ← 数量
identity set            ← 身份集合
```

无法发现"**同数量、同身份、内容被替换**"的篡改，也无法发现"同一 acceptance
下一次 import 覆盖了某行的公共字段"。因此本模块给出确定性的**内容指纹**。

## 口径（⛔ 不得改动）

```text
offering_payload_sha256 = SHA256(canonical offering payload)     —— 单条教学班内容
offering_set_sha256     = SHA256(canonical accepted dataset)     —— 整批已验收内容
```

canonical offering payload：

```text
json.dumps(offering.model_dump(mode="json"),
           sort_keys=True, ensure_ascii=False,
           separators=(",", ":"), allow_nan=False).encode("utf-8")
```

- ⛔ **只用公共模型当前已有的字段**（`CourseOffering` 的全部字段，含 `data_source`
  与 `meetings[]`）；⛔ **不新增任何公共 Schema 字段**；
- `model_dump(mode="json")` 之后再做键排序 ⇒ 与字典构造顺序无关；
- `allow_nan=False` ⇒ ⛔ 不接受 NaN / Infinity（它们没有确定性 JSON 表示）。

canonical accepted dataset：

```text
rows = sorted(offerings, key=(semester, course_id, class_id))
canonical bytes = b"\n".join(offering_payload_sha256(o).encode("ascii") for o in rows)
offering_set_sha256 = SHA256(canonical bytes)
```

- ⛔ 与"调用方传入顺序"无关（先按 identity 稳定排序）；
- ⛔ 重复 identity 一律拒绝（分片应互斥，⛔ 不静默去重）；
- 空集合也有确定 digest（`SHA256(b"")`），⛔ 不会被当成"未提供"。

⚠️ 这是 Course Data **内部**工具：⛔ 不进 `schemas/`、⛔ 不进 `docs/interfaces/`、
⛔ 不是新的公共 Schema。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from app.course_data.errors import CourseDataNormalizationError
from app.models.contracts import CourseOffering

__all__ = [
    "canonical_offering_payload",
    "offering_identity",
    "offering_payload_sha256",
    "offering_set_sha256",
]

#: identity 口径（与 `OfferingSnapshot` / Planner 一致）：⛔ 不是"仅 course_id"。
OfferingIdentity = tuple[str, str, str]


def offering_identity(offering: CourseOffering) -> OfferingIdentity:
    """一条教学班的 identity：`(semester, course_id, class_id)`。"""

    if not isinstance(offering, CourseOffering):
        raise CourseDataNormalizationError(
            f"只能对 CourseOffering 计算 identity，实际是 {type(offering).__name__}"
        )

    return (offering.semester, offering.course_id, offering.class_id)


def canonical_offering_payload(offering: CourseOffering) -> bytes:
    """一条教学班的 canonical JSON 字节（⛔ 只含公共模型当前字段）。"""

    if not isinstance(offering, CourseOffering):
        raise CourseDataNormalizationError(
            f"只能对 CourseOffering 计算 canonical payload，实际是 "
            f"{type(offering).__name__}"
        )

    try:
        return json.dumps(
            offering.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:  # pragma: no cover - 防御性
        raise CourseDataNormalizationError(
            "教学班内容无法序列化成确定性 JSON（可能存在 NaN / Infinity 或非 JSON 值）"
        ) from exc


def offering_payload_sha256(offering: CourseOffering) -> str:
    """单条教学班内容的 SHA-256（十六进制小写）。"""

    return hashlib.sha256(canonical_offering_payload(offering)).hexdigest()


def offering_set_sha256(offerings: Sequence[CourseOffering]) -> str:
    """**整批**教学班内容的确定性 SHA-256（⛔ 与传入顺序无关）。

    任一行的 identity 或公共字段变化 ⇒ digest 变化；
    同数量 / 同身份的"内容替换"必然被发现。
    """

    if isinstance(offerings, (str, bytes)) or not isinstance(offerings, Sequence):
        raise CourseDataNormalizationError(
            f"offerings 必须是 CourseOffering 序列，实际是 {type(offerings).__name__}"
        )

    digests: list[tuple[OfferingIdentity, str]] = []
    seen: set[OfferingIdentity] = set()

    for offering in offerings:
        identity = offering_identity(offering)
        if identity in seen:
            # ⛔ 不静默去重：重复 identity 说明调用方把两批数据混在了一起。
            raise CourseDataNormalizationError(
                f"计算 offering set digest 时出现重复教学班 identity："
                f"semester={identity[0]} course_id={identity[1]} class_id={identity[2]}"
            )
        seen.add(identity)
        digests.append((identity, offering_payload_sha256(offering)))

    digests.sort(key=lambda item: item[0])

    canonical = b"\n".join(digest.encode("ascii") for _identity, digest in digests)

    return hashlib.sha256(canonical).hexdigest()
