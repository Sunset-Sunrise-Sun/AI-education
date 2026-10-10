"""批准锚点（trust anchor）自身的回归测试。

覆盖任务书要求的负向场景中"锚点层"的部分：

- 未配置 / 不可读 / 版本不符 / 结构非法 ⇒ fail closed；
- 缺少批准记录 ⇒ `approval_missing`；
- **篡改摘要** ⇒ `approval_digest_mismatch`；
- **身份不符**（版本 / 学期被改） ⇒ `approval_missing` 或 `identity_mismatch`；
- **自签**（生成工具把自己的名字写进 `approver`） ⇒ 锚点整体拒绝；
- 过期 ⇒ `approval_expired`；
- 字段多余 ⇒ 拒绝（⛔ 不允许"加字段绕过"）。

⛔ 这些测试**不产生任何真实批准**：全部使用临时目录里的合成 artifact 与夹具锚点。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.provenance import (
    APPROVAL_KIND_COURSE_DATA_MANIFEST,
    APPROVAL_KIND_CURRICULUM_CASE,
    APPROVAL_KIND_CURRICULUM_CATALOG,
    TRUST_ANCHOR_ENV,
    ProvenanceDenied,
    ProvenanceReason,
    TrustAnchor,
    TrustAnchorUnavailable,
    identity_for,
    load_trust_anchor,
    sha256_bytes,
    sha256_file,
    verify_approval,
)

_APPROVER = "教务数据负责人 张三（工号 0001）"
_AUTHORIZATION = "教务数据交接会议纪要 2026-10-01"


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _artifact(tmp_path: Path, name: str = "artifact.json") -> Path:
    return _write(tmp_path / name, {"kind": "synthetic", "value": 1})


def _anchor(tmp_path: Path, approvals: list[dict]) -> Path:
    return _write(tmp_path / "anchor.json", {
        "trust_anchor_version": 1, "approvals": approvals,
    })


def _case_approval(digest: str, **overrides: object) -> dict:
    record = {
        "kind": APPROVAL_KIND_CURRICULUM_CASE,
        "identity": {"target_version_id": "net-2025", "as_of_term": "2025-2"},
        "artifact_sha256": digest,
        "approver": _APPROVER,
        "authorization": _AUTHORIZATION,
        "approved_at": "2026-10-01T00:00:00Z",
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------- #
# 装载层：fail closed
# --------------------------------------------------------------------------- #

def test_missing_env_var_is_not_configured(tmp_path: Path) -> None:
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_NOT_CONFIGURED


def test_unreadable_anchor_is_rejected() -> None:
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: "Z:/definitely/not/here.json"})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_UNREADABLE


def test_unsupported_version_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path / "anchor.json", {"trust_anchor_version": 2, "approvals": []})
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_FORMAT_UNSUPPORTED


def test_boolean_version_is_not_accepted_as_one(tmp_path: Path) -> None:
    """`True == 1`，所以必须显式排除布尔（防类型混淆）。"""

    path = _write(tmp_path / "anchor.json", {"trust_anchor_version": True, "approvals": []})
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_FORMAT_UNSUPPORTED


def test_extra_top_level_field_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path / "anchor.json", {
        "trust_anchor_version": 1, "approvals": [], "synthetic": False,
    })
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_not_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "anchor.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


# --------------------------------------------------------------------------- #
# 记录层：校验
# --------------------------------------------------------------------------- #

def test_approved_artifact_verifies(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(sha256_file(artifact)),
    ]))})

    result = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "net-2025", "as_of_term": "2025-2"},
        artifact_sha256=sha256_file(artifact),
        anchor=anchor,
    )
    assert result.verified is True


def test_approval_missing_when_identity_not_approved(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(sha256_file(artifact)),
    ]))})

    result = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "other-2025", "as_of_term": "2025-2"},
        artifact_sha256=sha256_file(artifact),
        anchor=anchor,
    )
    assert result.verified is False
    assert result.reason == ProvenanceReason.APPROVAL_MISSING


def test_tampered_content_fails_digest_check(tmp_path: Path) -> None:
    """**改一个字符**就要被摘要抓住。"""

    artifact = _artifact(tmp_path)
    approved_digest = sha256_file(artifact)
    _write(artifact, {"kind": "synthetic", "value": 2})  # 内容被改
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(approved_digest),
    ]))})

    result = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "net-2025", "as_of_term": "2025-2"},
        artifact_sha256=sha256_file(artifact),
        anchor=anchor,
    )
    assert result.verified is False
    assert result.reason == ProvenanceReason.DIGEST_MISMATCH


def test_forged_digest_string_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(sha256_file(artifact)),
    ]))})

    result = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "net-2025", "as_of_term": "2025-2"},
        artifact_sha256="z" * 64,  # 不是合法十六进制
        anchor=anchor,
    )
    assert result.verified is False
    assert result.reason == ProvenanceReason.APPROVAL_INVALID


def test_incomplete_identity_request_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(sha256_file(artifact)),
    ]))})

    result = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "net-2025"},  # 缺 as_of_term
        artifact_sha256=sha256_file(artifact),
        anchor=anchor,
    )
    assert result.verified is False
    assert result.reason == ProvenanceReason.IDENTITY_MISMATCH


def test_expired_approval_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(sha256_file(artifact), expires_at="2020-01-01T00:00:00Z"),
    ]))})

    result = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "net-2025", "as_of_term": "2025-2"},
        artifact_sha256=sha256_file(artifact),
        anchor=anchor,
    )
    assert result.verified is False
    assert result.reason == ProvenanceReason.APPROVAL_EXPIRED


def test_not_yet_expired_approval_verifies(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(sha256_file(artifact), expires_at="2099-01-01T00:00:00Z"),
    ]))})

    result = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={"target_version_id": "net-2025", "as_of_term": "2025-2"},
        artifact_sha256=sha256_file(artifact),
        anchor=anchor,
        now="2030-06-01T00:00:00Z",
    )
    assert result.verified is True


# --------------------------------------------------------------------------- #
# 自签与结构：⛔ 生成工具不得签发
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("approver", [
    "catalog_draft tool",
    "docx_importer",
    "mock fixture loader",
    "test-suite",
    "sysu_course_offering_collector",
    "prepare_real_case_a_runtime",
])
def test_self_issued_approval_is_rejected(tmp_path: Path, approver: str) -> None:
    """生成 artifact 的工具**不得**成为自己的批准人。"""

    artifact = _artifact(tmp_path)
    path = _anchor(tmp_path, [_case_approval(sha256_file(artifact), approver=approver)])
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_extra_identity_field_is_rejected(tmp_path: Path) -> None:
    """identity 字段集合必须与 kind **完全相等**（⛔ 加字段不能绕过）。"""

    artifact = _artifact(tmp_path)
    record = _case_approval(sha256_file(artifact))
    record["identity"]["synthetic"] = "false"
    path = _anchor(tmp_path, [record])
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_extra_record_field_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    path = _anchor(tmp_path, [_case_approval(sha256_file(artifact), verified=True)])
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_unsupported_kind_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    path = _anchor(tmp_path, [_case_approval(sha256_file(artifact), kind="whatever")])
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_empty_approver_or_authorization_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    for field in ("approver", "authorization"):
        path = _anchor(tmp_path, [_case_approval(sha256_file(artifact), **{field: "   "})])
        with pytest.raises(TrustAnchorUnavailable) as excinfo:
            load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
        assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_missing_approver_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    record = _case_approval(sha256_file(artifact))
    record.pop("approver")
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [record]))})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_missing_authorization_is_rejected(tmp_path: Path) -> None:
    """⛔ 缺"授权依据"不得被视为已批准。"""

    artifact = _artifact(tmp_path)
    record = _case_approval(sha256_file(artifact))
    record.pop("authorization")
    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [record]))})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


# --------------------------------------------------------------------------- #
# 其余 kind 与工具
# --------------------------------------------------------------------------- #

def test_catalog_kind_binds_one_version(tmp_path: Path) -> None:
    catalog = _artifact(tmp_path, "catalog.json")
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [{
        "kind": APPROVAL_KIND_CURRICULUM_CATALOG,
        "identity": {"version_id": "net-2025"},
        "artifact_sha256": sha256_file(catalog),
        "approver": _APPROVER,
        "authorization": _AUTHORIZATION,
        "approved_at": "2026-10-01T00:00:00Z",
    }]))})

    ok = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CATALOG, identity={"version_id": "net-2025"},
        artifact_sha256=sha256_file(catalog), anchor=anchor,
    )
    other = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CATALOG, identity={"version_id": "other-2025"},
        artifact_sha256=sha256_file(catalog), anchor=anchor,
    )
    assert ok.verified is True
    assert other.reason == ProvenanceReason.APPROVAL_MISSING


def test_manifest_kind_requires_semester_and_acceptance_digest(tmp_path: Path) -> None:
    manifest = _artifact(tmp_path, "manifest.json")
    digest = sha256_file(manifest)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [{
        "kind": APPROVAL_KIND_COURSE_DATA_MANIFEST,
        "identity": {"semester": "2026-1", "acceptance_sha256": digest},
        "artifact_sha256": digest,
        "approver": _APPROVER,
        "authorization": _AUTHORIZATION,
        "approved_at": "2026-10-01T00:00:00Z",
    }]))})

    ok = verify_approval(
        kind=APPROVAL_KIND_COURSE_DATA_MANIFEST,
        identity={"semester": "2026-1", "acceptance_sha256": digest},
        artifact_sha256=digest, anchor=anchor,
    )
    wrong_semester = verify_approval(
        kind=APPROVAL_KIND_COURSE_DATA_MANIFEST,
        identity={"semester": "2026-2", "acceptance_sha256": digest},
        artifact_sha256=digest, anchor=anchor,
    )
    assert ok.verified is True
    assert wrong_semester.reason == ProvenanceReason.APPROVAL_MISSING


def test_identity_for_rejects_incomplete_input() -> None:
    with pytest.raises(ValueError):
        identity_for(APPROVAL_KIND_CURRICULUM_CASE, target_version_id="net-2025")
    assert identity_for(
        APPROVAL_KIND_CURRICULUM_CASE, target_version_id="net-2025", as_of_term="2025-2",
    ) == {"target_version_id": "net-2025", "as_of_term": "2025-2"}


def test_require_raises_for_callers_that_must_fail_closed() -> None:
    from app.provenance import ProvenanceCheck

    with pytest.raises(ProvenanceDenied):
        ProvenanceCheck(verified=False, reason=ProvenanceReason.APPROVAL_MISSING).require()


def test_anchor_exposes_no_artifact_content(tmp_path: Path) -> None:
    """锚点只装元数据；⛔ 不把 artifact 内容读进内存。"""

    artifact = _artifact(tmp_path)
    anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(_anchor(tmp_path, [
        _case_approval(sha256_file(artifact)),
    ]))})

    assert isinstance(anchor, TrustAnchor)
    rendered = repr(anchor)
    assert "synthetic" not in rendered
    assert '"value"' not in rendered


def test_sha256_bytes_matches_hashlib() -> None:
    import hashlib

    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()
