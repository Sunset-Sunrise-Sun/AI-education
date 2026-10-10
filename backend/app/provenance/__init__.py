"""来源可信性（provenance trust）：批准锚点与运行时门。

```text
原始文档 / 采集数据
      │
      ▼  （Parser / Importer / 生成工具）
   标准化数据（Case JSON / catalog.json / 全学期 manifest）
      │
      ▼  ← 人工或授权流程**在带外**写入批准记录（trust anchor）
   TrustAnchor（本模块读取；⛔ 生成工具不写）
      │
      ▼  运行时逐项校验：批准存在 + 摘要一致 + 身份一致 + 未过期 + 非自签
   Store / Provider / Planner / AI 上下文
      │
      ▼
   前端标识：未核验来源**永远**带风险提示
```

## 本模块解决什么、不解决什么

**解决**：让 `data_source=real` / `verification.verified=true` 这类**自述**
不再能单独生效。任何"已核验"声明都必须在运行时满足：

1. `APP_TRUST_ANCHOR_PATH` 指向的锚点文件**可读**且**格式合法**；
2. 该 artifact 有**对应的批准记录**（按 kind + 身份 + 摘要）；
3. **摘要一致**：批准记录里的 SHA-256 与从**当前磁盘内容**重算的摘要相同；
4. **身份一致**：版本号 / 学期 / manifest 摘要等身份字段完全相符；
5. **非自签**：`approver` 不能是生成该 artifact 的工具（见 `_SELF_ISSUING`）；
6. **未过期**（若声明了 `expires_at`）。

任一条不满足 ⇒ **fail closed**（拒绝进入生产链路），⛔ 不回退、⛔ 不降级放行。

**不解决（必须由人配置，本模块⛔ 不伪造）**：

- ⛔ **SHA-256 只证明"输入与摘要一致"，不证明来源真实。** 摘要由谁签发、
  依据什么授权，本模块**无法**验证；它只负责让"批准必须存在且与内容绑定"成为硬条件。
- ⛔ **本模块没有任何密码学签名**，因此**没有**防篡改能力：能写锚点文件的人就能批准。
  不要把它当成签名方案。真正的信任边界是**文件权限**与"锚点文件不在仓库内、
  且不在生成工具的写入范围内"。
- ⛔ 批准**不等于**课程等价、毕业要求或选课资格已获学校认定（见
  `docs/final_upgrade/TRUST_ANCHOR_DESIGN.md` §7）。

## 锚点文件格式（`trust_anchor_version: 1`）

```json
{
  "trust_anchor_version": 1,
  "approvals": [
    {
      "kind": "course_data_semester_manifest",
      "identity": { "semester": "2026-1", "acceptance_sha256": "<64 hex>" },
      "artifact_sha256": "<64 hex>",
      "approver": "教务数据负责人（姓名/工号）",
      "authorization": "邮件/会议纪要编号或签字文件标识",
      "approved_at": "2026-10-01T00:00:00Z",
      "expires_at": null,
      "note": null
    }
  ]
}
```

`kind` 目前支持：

| kind | 绑定的 artifact | 身份字段 |
| --- | --- | --- |
| `course_data_semester_manifest` | 全学期验收 manifest | `semester`、`acceptance_sha256` |
| `curriculum_case` | Case A case JSON | `target_version_id`、`as_of_term` |
| `curriculum_catalog` | `catalog.json` | `version_id` 列表（按版本逐条批准） |
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

__all__ = [
    "APPROVAL_KIND_COURSE_DATA_MANIFEST",
    "APPROVAL_KIND_CURRICULUM_CASE",
    "APPROVAL_KIND_CURRICULUM_CATALOG",
    "APPROVAL_KINDS",
    "TRUST_ANCHOR_ENV",
    "TRUST_ANCHOR_VERSION",
    "ApprovalRecord",
    "ProvenanceCheck",
    "ProvenanceDenied",
    "ProvenanceReason",
    "TrustAnchor",
    "TrustAnchorUnavailable",
    "load_trust_anchor",
    "sha256_bytes",
    "sha256_file",
    "verify_approval",
]

#: 锚点文件路径的环境变量名（与既有 `APP_*` 命名一致）。
TRUST_ANCHOR_ENV: Final[str] = "APP_TRUST_ANCHOR_PATH"

#: 锚点格式版本（⛔ 不向前兼容：版本不符即拒绝）。
TRUST_ANCHOR_VERSION: Final[int] = 1

APPROVAL_KIND_COURSE_DATA_MANIFEST: Final[str] = "course_data_semester_manifest"
APPROVAL_KIND_CURRICULUM_CASE: Final[str] = "curriculum_case"
APPROVAL_KIND_CURRICULUM_CATALOG: Final[str] = "curriculum_catalog"

APPROVAL_KINDS: Final[tuple[str, ...]] = (
    APPROVAL_KIND_COURSE_DATA_MANIFEST,
    APPROVAL_KIND_CURRICULUM_CASE,
    APPROVAL_KIND_CURRICULUM_CATALOG,
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

#: 允许的身份字段（⛔ 未声明字段直接拒绝，避免"多写一个字段就绕过"）。
_IDENTITY_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    APPROVAL_KIND_COURSE_DATA_MANIFEST: ("semester", "acceptance_sha256"),
    APPROVAL_KIND_CURRICULUM_CASE: ("target_version_id", "as_of_term"),
    APPROVAL_KIND_CURRICULUM_CATALOG: ("version_id",),
}

_RECORD_REQUIRED: Final[tuple[str, ...]] = (
    "kind", "identity", "artifact_sha256", "approver", "authorization", "approved_at",
)
_RECORD_ALLOWED: Final[frozenset[str]] = frozenset(_RECORD_REQUIRED) | {
    "expires_at", "note",
    # ⚠️ 本轮新增（角色分离与撤销）：全部为**可选元数据**，缺失即 null。
    # ⛔ 不破坏既有锚点：这些字段都不参与"是否放行"的判定（除 revoked 外）。
    "submitter", "generator", "review_evidence_sha256",
    "revoked", "revoked_at", "revoked_by", "revocation_reason",
}

#: 自签识别：artifact 生成工具**不得**成为自己的批准人。
#:
#: ⚠️ 这是**启发式**（小写子串匹配），不是安全边界：它只能挡住"工具名直接写进
#: `approver`"这种明显的自签。真正的边界是"锚点文件由人写、且生成工具没有写权限"。
#:
#: ⚠️ 它**只**作用于 `approver` 字段。`generator` 字段**允许**出现工具名——
#: 那是在**如实记录**artifact 由什么产出，不是在声称批准。
_SELF_ISSUING: Final[tuple[str, ...]] = (
    "generator", "importer", "parser", "loader", "builder", "collector",
    "mock", "fixture", "test", "tool", "prepare_real_case_a_runtime",
    "sysu_course_offering_collector", "catalog_draft",
)


#: 撤销时必须同时提供的三个字段（⛔ 不允许"撤了一半"的模糊记录）。
_REVOCATION_FIELDS: Final[tuple[str, ...]] = (
    "revoked_at", "revoked_by", "revocation_reason",
)


class ProvenanceReason:
    """拒绝原因（固定码；⛔ 不包含路径、文档内容或任何个人信息）。"""

    ANCHOR_NOT_CONFIGURED: Final[str] = "trust_anchor_not_configured"
    ANCHOR_UNREADABLE: Final[str] = "trust_anchor_unreadable"
    ANCHOR_FORMAT_UNSUPPORTED: Final[str] = "trust_anchor_format_unsupported"
    ANCHOR_INVALID: Final[str] = "trust_anchor_invalid"
    APPROVAL_MISSING: Final[str] = "approval_missing"
    APPROVAL_INVALID: Final[str] = "approval_invalid"
    DIGEST_MISMATCH: Final[str] = "approval_digest_mismatch"
    IDENTITY_MISMATCH: Final[str] = "approval_identity_mismatch"
    SELF_ISSUED: Final[str] = "approval_self_issued"
    APPROVAL_EXPIRED: Final[str] = "approval_expired"
    #: ⚠️ 本轮新增：**曾批准、现已撤销**。与 `APPROVAL_MISSING`（从未批准）区分，
    #: 因为两者的处置完全不同：前者要查撤销理由，后者要去补齐批准。
    APPROVAL_REVOKED: Final[str] = "approval_revoked"

    #: ⚠️ 本轮新增：**同一批准对象存在语义冲突或重复记录**。
    #: 例如"已撤销 + 有效"、"两条重复有效"、"已过期 + 有效"同时存在。
    #: ⛔ 一律拒绝该对象，⛔ 不挑一条有效的放行（防止用遗留记录绕过撤销）。
    APPROVAL_CONFLICT: Final[str] = "approval_conflict"

    ALL: Final[tuple[str, ...]] = (
        ANCHOR_NOT_CONFIGURED, ANCHOR_UNREADABLE, ANCHOR_FORMAT_UNSUPPORTED,
        ANCHOR_INVALID, APPROVAL_MISSING, APPROVAL_INVALID, DIGEST_MISMATCH,
        IDENTITY_MISMATCH, SELF_ISSUED, APPROVAL_EXPIRED, APPROVAL_REVOKED,
        APPROVAL_CONFLICT,
    )


class ProvenanceDenied(RuntimeError):
    """来源未被独立批准 / 与批准记录不符 ⇒ 拒绝进入生产链路。"""

    def __init__(self, reason: str, message: str) -> None:
        if reason not in ProvenanceReason.ALL:
            raise ValueError("provenance: unexpected reason code")
        super().__init__(message)
        self.reason = reason
        self.message = message


class TrustAnchorUnavailable(ProvenanceDenied):
    """锚点本身不可用（未配置 / 不可读 / 格式不符 / 结构非法）。"""


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """一条批准记录（**只能**由组长明确授权后的独立受控流程在带外写入）。

    角色分离（见 `docs/final_upgrade/APPROVAL_WORKFLOW_DESIGN.md` §1）：

    - `submitter`：数据提交者（材料从哪来）；
    - `generator`：产出该 artifact 的工具（⛔ 与 `approver` 不得相同）；
    - `approver`：**审核人**，本项目为组长本人（唯一有权批准的人）；
    - 保管者：在带外把记录写入锚点文件的人（⛔ 可能是组长本人）。
    """

    kind: str
    identity: tuple[tuple[str, str], ...]
    artifact_sha256: str
    approver: str
    authorization: str
    approved_at: str
    expires_at: str | None = None
    note: str | None = None
    # ---- 本轮新增（全部可选；⛔ 缺失即 None，⛔ 不猜测）------------------- #
    submitter: str | None = None
    generator: str | None = None
    #: 组长**实际审核过的那份待审核清单**的 SHA-256。
    #: ⚠️ 这是**审计字段**：它⛔ 不参与放行判定（见设计 §3.3）。
    review_evidence_sha256: str | None = None
    revoked: bool = False
    revoked_at: str | None = None
    revoked_by: str | None = None
    revocation_reason: str | None = None

    def __post_init__(self) -> None:
        """⛔ 规范化 `identity`，保证**手工构造**的记录与文件装载的记录形状一致。

        为什么需要：`verify_approval` 的重复检测依赖 `identity` 是**可哈希**的
        `tuple[tuple[str, str], ...]`。若允许它保持 `dict`，重复检测会直接抛
        `TypeError`（而不是给出明确错误码），且"同一对象"的判定会失真。
        这里把两种入口统一成同一种形状：dict 会被按该 `kind` 的字段顺序规范化。
        """

        raw = self.identity
        if isinstance(raw, Mapping):
            if self.kind not in APPROVAL_KINDS:
                raise ValueError("provenance: unexpected approval kind")
            missing = [name for name in _IDENTITY_FIELDS[self.kind] if name not in raw]
            if missing or set(raw) != set(_IDENTITY_FIELDS[self.kind]):
                raise ValueError("provenance: identity 字段与该 kind 不符")
            normalized = tuple(
                (name, str(raw[name]).strip()) for name in _IDENTITY_FIELDS[self.kind]
            )
        elif isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
            raise ValueError("provenance: identity 必须是映射或键值序列")
        else:
            normalized = tuple((str(name), str(value)) for name, value in raw)
        object.__setattr__(self, "identity", normalized)

    def identity_map(self) -> dict[str, str]:
        return dict(self.identity)

    def object_key(self) -> tuple[str, tuple[tuple[str, str], ...], str]:
        """**批准对象**：同一 `(kind, identity, artifact_sha256)` 只允许一条有效记录。

        ⚠️ 撤销记录与有效记录**共存**即视为冲突（见 `approval_conflict`），
        因为那正是"用遗留记录绕过撤销"的形状。
        """

        return (self.kind, self.identity, self.artifact_sha256)

    def is_self_issued(self) -> bool:
        lowered = self.approver.strip().lower()
        return any(marker in lowered for marker in _SELF_ISSUING)


@dataclass(frozen=True, slots=True)
class TrustAnchor:
    """已装载的批准锚点；⛔ 不含任何 artifact 内容。"""

    path: str = field(repr=False)
    approvals: tuple[ApprovalRecord, ...] = ()

    def matching(self, kind: str) -> tuple[ApprovalRecord, ...]:
        return tuple(item for item in self.approvals if item.kind == kind)


@dataclass(frozen=True, slots=True)
class ProvenanceCheck:
    """一次校验的结果。

    ⚠️ `verified=True` 只表示"批准存在且与当前内容一致"，
    ⛔ **不**表示来源真实、更⛔ 不代表学校已认定任何学业结论。
    """

    verified: bool
    reason: str
    message: str = ""

    def require(self) -> "ProvenanceCheck":
        """不通过就抛出（供运行时门使用）。"""

        if not self.verified:
            raise ProvenanceDenied(self.reason, self.message or self.reason)
        return self


# --------------------------------------------------------------------------- #
# 摘要
# --------------------------------------------------------------------------- #

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path, *, reason: str | None = None) -> str:
    """对文件**字节**求 SHA-256（含所有空白与编码差异，⛔ 不做规范化）。

    文件不可读时抛 `TrustAnchorUnavailable`（**显式领域异常**），
    这样调用方（runtime）⛔ 不需要、也⛔ 不应该去捕获 `OSError`。
    """

    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise TrustAnchorUnavailable(
            reason or ProvenanceReason.ANCHOR_UNREADABLE,
            "被批准的对象不可读。",
        ) from None
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# 装载
# --------------------------------------------------------------------------- #

def load_trust_anchor(environment: Mapping[str, str] | None = None) -> TrustAnchor:
    """从环境变量指向的文件装载批准锚点。

    ⛔ 未配置 / 不可读 / 版本不符 / 结构非法 ⇒ 抛 `TrustAnchorUnavailable`（fail closed）。
    ⛔ 返回的锚点不包含 artifact 内容，只包含批准元数据。
    """

    import os

    env = os.environ if environment is None else environment
    raw_path = (env.get(TRUST_ANCHOR_ENV) or "").strip()
    if not raw_path:
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_NOT_CONFIGURED,
            f"未配置 {TRUST_ANCHOR_ENV}：无法证明任何来源已被批准。",
        )
    path = Path(raw_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_UNREADABLE,
            "批准锚点文件不可读。",
        ) from None
    except (ValueError, UnicodeDecodeError):
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID,
            "批准锚点文件不是合法 JSON。",
        ) from None

    if not isinstance(payload, dict):
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID, "批准锚点顶层必须是对象。",
        )
    if set(payload) - {"trust_anchor_version", "approvals"}:
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID, "批准锚点包含未声明字段。",
        )
    version = payload.get("trust_anchor_version")
    if isinstance(version, bool) or version != TRUST_ANCHOR_VERSION:
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_FORMAT_UNSUPPORTED,
            "批准锚点版本不受支持（⛔ 不向前兼容）。",
        )
    raw_approvals = payload.get("approvals")
    if not isinstance(raw_approvals, list):
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID, "批准锚点的 approvals 必须是数组。",
        )
    records = tuple(_record(item) for item in raw_approvals)
    _require_unique_objects(records)
    return TrustAnchor(path=str(path), approvals=records)


#: 重复批准对象的**统一**说明与**统一**检查。
#:
#: ⚠️ 装载期（`_require_unique_objects`）与校验期（`verify_approval`）使用
#: **同一个**函数与**同一句话**，因此"任何重复记录 ⇒ `approval_conflict`"
#: 在两个入口上口径完全一致，⛔ 不依赖调用方走了哪条路径。
_APPROVAL_OBJECT_KEY = tuple[str, tuple[tuple[str, str], ...], str]

_DUPLICATE_OBJECT_MESSAGE: Final[str] = (
    "批准对象（kind + identity + artifact_sha256）出现多条记录；"
    "⛔ 语义不唯一，拒绝整个相关批准集合。请只保留**一条**记录："
    "撤销与重新审核都应改这**同一条**记录，⛔ 不要新增重复记录。"
)


def first_duplicate_object(
    records: Sequence[ApprovalRecord],
) -> _APPROVAL_OBJECT_KEY | None:
    """返回**第一个**重复出现的批准对象键；没有重复则返回 `None`。

    ⛔ 不检测"哪一条更可信"：只要同一对象出现两次，就说明**语义不唯一**，
    必须整体拒绝，而不是挑一条。
    """

    seen: set[_APPROVAL_OBJECT_KEY] = set()
    for record in records:
        key = record.object_key()
        if key in seen:
            return key
        seen.add(key)
    return None


def _require_unique_objects(records: tuple[ApprovalRecord, ...]) -> None:
    """⛔ **同一批准对象只允许一条记录**（`kind` + `identity` + `artifact_sha256`）。

    为什么必须在装载期就拒绝：两条记录同时描述同一个对象时，**哪一条算数是不确定的**。
    修复前的实现会挑出"未撤销"的那些，只要有一条有效就放行 —— 于是
    "已撤销 + 有效"共存时撤销被静默忽略，用一条遗留记录即可绕过撤销。

    这里直接要求**唯一**，而不是"未撤销的恰好一条"，理由有三：

    1. 不留任何"挑一条"的空间，语义没有歧义；
    2. 撤销记录是**同一条**记录的字段（不是新增记录），因此审计链完整保留；
    3. 重新审核改内容时对象本来就不同（摘要变了），不会误伤。

    ⛔ 不引入审批版本系统：只做"同一对象唯一记录"这一条最小规则。
    错误码用 `approval_conflict`（语义精确：这是**批准冲突**，不是格式错误）。
    """

    if first_duplicate_object(records) is not None:
        raise TrustAnchorUnavailable(
            ProvenanceReason.APPROVAL_CONFLICT, _DUPLICATE_OBJECT_MESSAGE,
        )


def _record(item: object) -> ApprovalRecord:
    if not isinstance(item, dict):
        raise TrustAnchorUnavailable(ProvenanceReason.ANCHOR_INVALID, "批准记录必须是对象。")
    if set(item) - _RECORD_ALLOWED:
        raise TrustAnchorUnavailable(ProvenanceReason.ANCHOR_INVALID, "批准记录包含未声明字段。")
    missing = [name for name in _RECORD_REQUIRED if name not in item]
    if missing:
        raise TrustAnchorUnavailable(ProvenanceReason.ANCHOR_INVALID, "批准记录缺少必需字段。")

    kind = item["kind"]
    if kind not in APPROVAL_KINDS:
        raise TrustAnchorUnavailable(ProvenanceReason.ANCHOR_INVALID, "批准记录的 kind 不受支持。")

    raw_identity = item["identity"]
    if not isinstance(raw_identity, dict):
        raise TrustAnchorUnavailable(ProvenanceReason.ANCHOR_INVALID, "identity 必须是对象。")
    allowed = set(_IDENTITY_FIELDS[kind])
    if set(raw_identity) != allowed:
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID, "identity 字段与该 kind 不符。",
        )
    identity: list[tuple[str, str]] = []
    for name in _IDENTITY_FIELDS[kind]:
        value = raw_identity[name]
        if not isinstance(value, str) or not value.strip():
            raise TrustAnchorUnavailable(
                ProvenanceReason.ANCHOR_INVALID, "identity 取值必须是非空字符串。",
            )
        if name.endswith("sha256") and not _SHA256_PATTERN.fullmatch(value.strip().lower()):
            raise TrustAnchorUnavailable(
                ProvenanceReason.ANCHOR_INVALID, "identity 里的摘要必须是 64 位小写十六进制。",
            )
        identity.append((name, value.strip()))

    digest = item["artifact_sha256"]
    if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest.strip().lower()):
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID, "artifact_sha256 必须是 64 位小写十六进制。",
        )

    def text(name: str) -> str:
        value = item[name]
        if not isinstance(value, str) or not value.strip():
            raise TrustAnchorUnavailable(
                ProvenanceReason.ANCHOR_INVALID, f"{name} 必须是非空字符串。",
            )
        return value.strip()

    # ---- 撤销字段：⛔ 不允许"撤了一半"的模糊记录 ------------------------- #
    raw_revoked = item.get("revoked", False)
    if type(raw_revoked) is not bool:
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID, "revoked 必须是真布尔。",
        )
    revocation = {name: _optional_text(item, name) for name in _REVOCATION_FIELDS}
    if raw_revoked:
        missing = [name for name, value in revocation.items() if value is None]
        if missing:
            raise TrustAnchorUnavailable(
                ProvenanceReason.ANCHOR_INVALID,
                "revoked=true 时必须同时给出 revoked_at / revoked_by / revocation_reason。",
            )
    elif any(value is not None for value in revocation.values()):
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID,
            "revoked=false 时不得填写撤销字段（⛔ 拒绝模糊记录）。",
        )

    evidence_digest = _optional_text(item, "review_evidence_sha256")
    if evidence_digest is not None and not _SHA256_PATTERN.fullmatch(evidence_digest.lower()):
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID,
            "review_evidence_sha256 必须是 64 位小写十六进制。",
        )

    approver = text("approver")
    generator = _optional_text(item, "generator")
    if generator is not None and generator.strip().lower() == approver.strip().lower():
        # ⛔ 角色分离：产出 artifact 的工具不得同时是审核人。
        # （`approver` 本身另受 `is_self_issued()` 的子串检测约束。）
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID,
            "approver 与 generator 不能是同一个人/工具（⛔ 违反角色分离）。",
        )

    record = ApprovalRecord(
        kind=kind,
        identity=tuple(identity),
        artifact_sha256=digest.strip().lower(),
        approver=approver,
        authorization=text("authorization"),
        approved_at=text("approved_at"),
        expires_at=_optional_text(item, "expires_at"),
        note=_optional_text(item, "note"),
        submitter=_optional_text(item, "submitter"),
        generator=generator,
        review_evidence_sha256=(
            evidence_digest.lower() if evidence_digest is not None else None
        ),
        revoked=raw_revoked,
        revoked_at=revocation["revoked_at"],
        revoked_by=revocation["revoked_by"],
        revocation_reason=revocation["revocation_reason"],
    )
    if record.is_self_issued():
        raise TrustAnchorUnavailable(
            ProvenanceReason.ANCHOR_INVALID,
            "批准记录的 approver 看起来是生成该 artifact 的工具（⛔ 不允许自签）。",
        )
    return record


def _optional_text(item: Mapping[str, Any], name: str) -> str | None:
    value = item.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TrustAnchorUnavailable(ProvenanceReason.ANCHOR_INVALID, f"{name} 必须是字符串或 null。")
    stripped = value.strip()
    return stripped or None


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #

def verify_approval(
    *,
    kind: str,
    identity: Mapping[str, str],
    artifact_sha256: str,
    anchor: TrustAnchor | None = None,
    environment: Mapping[str, str] | None = None,
    now: str | None = None,
) -> ProvenanceCheck:
    """按 kind + identity + 摘要校验是否已获独立批准。

    ⚠️ **统一检查重复批准对象**：本函数第一步就检查**整个** `anchor.approvals`
    里是否有重复的 `(kind, identity, artifact_sha256)`。只要发现重复，
    ⛔ 立即返回 `approval_conflict`，⛔ 不进入任何"按身份/摘要筛选"的逻辑。

    为什么必须在最前面：修复前本函数先筛出"未撤销"的记录再挑一条放行，
    因此"同一对象有两条记录"是**可以被绕过**的。现在重复检测与
    `load_trust_anchor()` 使用**同一个** `first_duplicate_object()`，
    所以无论调用方是把锚点从文件装载、还是**手工构造** `TrustAnchor` 传进来，
    任何重复记录都得到同一个错误码，⛔ 没有"走哪条路径就宽松一点"的余地。

    ⛔ 只返回结果、不抛异常（除锚点本身不可用）；调用方决定是 raise 还是记录。
    ⛔ `now` 仅用于测试注入（ISO-8601 字符串，字典序比较）。
    """

    import os

    try:
        loaded = anchor if anchor is not None else load_trust_anchor(environment)
    except TrustAnchorUnavailable as exc:
        return ProvenanceCheck(verified=False, reason=exc.reason, message=exc.message)

    # ---- 统一重复检查（必须先于任何筛选）------------------------------ #
    if first_duplicate_object(loaded.approvals) is not None:
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_CONFLICT,
            message=_DUPLICATE_OBJECT_MESSAGE,
        )

    if kind not in APPROVAL_KINDS:
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_INVALID,
            message="不支持的批准类型。",
        )

    digest = (artifact_sha256 or "").strip().lower()
    if not _SHA256_PATTERN.fullmatch(digest):
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_INVALID,
            message="待校验的摘要不是 64 位小写十六进制。",
        )

    wanted = {name: str(value).strip() for name, value in identity.items()}
    if set(wanted) != set(_IDENTITY_FIELDS[kind]) or any(not value for value in wanted.values()):
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.IDENTITY_MISMATCH,
            message="校验请求提供的身份字段不完整或与 kind 不符。",
        )

    # 先按身份筛（身份不符与"未批准"是**不同**的失败原因，便于运维定位）。
    same_identity = [
        item for item in loaded.matching(kind)
        if item.identity_map() == wanted
    ]
    if not same_identity:
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_MISSING,
            message="批准锚点里没有与该身份匹配的批准记录。",
        )

    matching_digest = [item for item in same_identity if item.artifact_sha256 == digest]
    if not matching_digest:
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.DIGEST_MISMATCH,
            message="批准记录存在，但其摘要与当前内容不符（内容可能已被修改）。",
        )

    # ------------------------------------------------------------------ #
    # ⚠️ **批准对象的唯一性（Architecture Review 修复）**
    #
    # 修复前：这里筛出所有**未撤销**记录，只要其中一条有效就放行。
    # 于是"已撤销 + 有效"共存时，撤销被**静默忽略** —— 用一条遗留记录
    # 就能绕过撤销。这正是复审指出的问题。
    #
    # 修复后（两层，都是 fail closed，⛔ 不引入审批版本系统）：
    #   ① 装载期 `_require_unique_objects`：同一对象出现多条记录 ⇒ 整个锚点拒绝
    #      （错误码 `approval_conflict`）——从根上消除"挑一条"的可能；
    #   ② 本函数：即使调用方**手工构造** `TrustAnchor` 绕过①，
    #      也绝不挑一条放行：任何"撤销 + 其它"或"多条有效"都返回 `approval_conflict`。
    # ------------------------------------------------------------------ #
    reference = now
    if reference is None:
        import datetime

        reference = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _expired(item: ApprovalRecord) -> bool:
        return item.expires_at is not None and item.expires_at < reference

    revoked = [item for item in matching_digest if item.revoked]
    live = [item for item in matching_digest if not item.revoked]
    usable = [item for item in live if not _expired(item)]

    # ① "已撤销 + 其它"共存：⛔ 不允许靠遗留记录自动恢复有效。
    if revoked and live:
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_CONFLICT,
            message=(
                "批准对象同时存在已撤销记录与其它记录；⛔ 不再采信任何一条。"
                "撤销后重新批准必须改**同一条**记录并留下明确的新审核决定。"
            ),
        )
    # ② 全部已撤销：保留"曾批准、现撤销"的准确语义。
    if revoked and not live:
        detail = revoked[0].revocation_reason or "未给出理由"
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_REVOKED,
            message=f"该批准已被撤销（{detail}）；⛔ 不再作为来源依据。",
        )
    # ③ 多条有效记录：语义不唯一 ⇒ 拒绝整个集合（⛔ 不挑一条）。
    if len(live) > 1:
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_CONFLICT,
            message="批准对象存在多条有效批准记录；⛔ 语义不唯一，拒绝整个相关批准集合。",
        )
    # ④ "已过期 + 有效"并存：⛔ 不允许挑未过期的那条放行。
    if usable and len(live) > len(usable):
        return ProvenanceCheck(
            verified=False, reason=ProvenanceReason.APPROVAL_CONFLICT,
            message="批准对象同时存在已过期记录与未过期记录；⛔ 语义冲突，拒绝整个相关批准集合。",
        )
    # ⑤ 唯一可信记录。
    if usable:
        return ProvenanceCheck(verified=True, reason="approved")
    # ⑥ 有效记录都已过期（不是冲突，而是需要续期）。
    return ProvenanceCheck(
        verified=False, reason=ProvenanceReason.APPROVAL_EXPIRED,
        message="批准记录已过期。",
    )


def digest_of_records(records: Iterable[Mapping[str, Any]]) -> str:
    """对**已标准化记录**求稳定摘要（兜底用；优先使用 artifact 文件字节摘要）。

    规范化规则：按键排序、紧凑分隔符、`ensure_ascii=False`，与既有
    `ai_planning.context._digest` 保持同一风格，避免同一份数据出现两个摘要。
    """

    canonical = json.dumps(
        [dict(item) for item in records], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    )
    return sha256_bytes(canonical.encode("utf-8"))


def identity_for(kind: str, **values: str) -> dict[str, str]:
    """构造并校验身份映射（⛔ 缺字段直接抛错，避免"漏传就跳过校验"）。"""

    if kind not in APPROVAL_KINDS:
        raise ValueError("provenance: unexpected approval kind")
    fields = _IDENTITY_FIELDS[kind]
    missing = [name for name in fields if not str(values.get(name, "")).strip()]
    if missing:
        raise ValueError("provenance: incomplete approval identity")
    return {name: str(values[name]).strip() for name in fields}


def describe_anchor(anchor: TrustAnchor) -> Sequence[str]:
    """给诊断用的**非敏感**摘要（⛔ 不含 artifact 内容、⛔ 不含路径）。"""

    return tuple(f"{item.kind}:{item.approver}" for item in anchor.approvals)
