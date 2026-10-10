"""组长批准流程的端到端测试（**全部使用合成数据**）。

覆盖任务书要求的五种流程：**批准 / 拒绝 / 篡改 / 过期 / 撤销**，
外加角色分离与"Agent 不能自行批准"的结构性断言。

⛔ 本文件不含任何真实材料、⛔ 不写任何真实锚点。
所有锚点都写在 `tmp_path` 里，`approver` 明确标注为"本地合成夹具组长（非真实批准）"。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.provenance import (
    APPROVAL_KIND_CURRICULUM_CASE,
    TRUST_ANCHOR_ENV,
    ProvenanceReason,
    TrustAnchorUnavailable,
    load_trust_anchor,
    sha256_file,
    verify_approval,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPOSITORY_ROOT / "backend" / "tools" / "review_real_data.py"

#: ⚠️ 合成夹具的"组长"标识（避开自签启发式；⛔ 不代表真实批准）。
FIXTURE_APPROVER = "本地合成夹具组长（非真实批准）"
FIXTURE_AUTHORIZATION = "synthetic fixture authorization"
IDENTITY = {"target_version_id": "fixture-new-2025", "as_of_term": "2025-2"}


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


def _case_payload(*, complete: bool = True) -> dict:
    """一份最小的合成 case（结构上像 Case A case JSON）。"""

    def version(version_id: str, course_id: str) -> dict:
        return {
            "version_id": version_id,
            "major": "示例专业",
            "cohort": "2025",
            "source_id": "fixture-source://plan",
            "complete": complete,
            "completeness_evidence": "fixture-source://plan#complete" if complete else None,
            "course_records": [{
                "course_id": course_id, "course_name": "示例课程", "credit": 3.0,
                "requirement": "required",
                "source_record": f"fixture-source://plan#{course_id}",
            }],
            "group_records": [],
        }

    return {
        "data_source": "real",
        "old": version("fixture-old-2025", "DEMO100"),
        "new": version("fixture-new-2025", "DEMO200"),
        "makeup_scope": {"as_of_term": "2025-2", "scope_kind": "current_semester",
                         "scope_id": "2025-2"},
        "missing_requirements": [],
        "completed": {
            "complete": True,
            "completeness_evidence": "fixture-source://done#complete",
            "source_id": "fixture-source://done",
            "records": [],
        },
    }


def _write_case(tmp_path: Path, *, name: str = "case-a.json", complete: bool = True) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(_case_payload(complete=complete), ensure_ascii=False), encoding="utf-8",
    )
    return path


def _write_anchor(tmp_path: Path, records: list[dict], *, name: str = "trust-anchor.json") -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps({"trust_anchor_version": 1, "approvals": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _record(digest: str, **overrides: object) -> dict:
    record: dict = {
        "kind": APPROVAL_KIND_CURRICULUM_CASE,
        "identity": dict(IDENTITY),
        "artifact_sha256": digest,
        "approver": FIXTURE_APPROVER,
        "authorization": FIXTURE_AUTHORIZATION,
        "approved_at": "2026-10-10T00:00:00Z",
    }
    record.update(overrides)
    return record


def _check(anchor: Path, digest: str):
    return verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity=dict(IDENTITY),
        artifact_sha256=digest,
        environment={TRUST_ANCHOR_ENV: str(anchor)},
    )


def _run_tool(*arguments: str, env_anchor: str | None = None) -> tuple[int, str, str]:
    import os

    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    if env_anchor is None:
        environment.pop(TRUST_ANCHOR_ENV, None)
    else:
        environment[TRUST_ANCHOR_ENV] = env_anchor
    completed = subprocess.run(
        [sys.executable, str(TOOL), *arguments],
        capture_output=True, text=True, encoding="utf-8", env=environment, cwd=str(TOOL.parents[1]),
    )
    return completed.returncode, completed.stdout, completed.stderr


# --------------------------------------------------------------------------- #
# ① 批准
# --------------------------------------------------------------------------- #


def test_flow_1_approved(tmp_path: Path) -> None:
    """批准：组长书面授权后，保管者写入一条记录 ⇒ 校验通过。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(sha256_file(artifact))])

    result = _check(anchor, sha256_file(artifact))
    assert result.verified is True
    assert result.reason == "approved"


def test_approved_record_carries_submitter_and_generator(tmp_path: Path) -> None:
    """批准记录必须能说明：材料谁提交的、什么工具产出的、审核了哪份清单。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(
        sha256_file(artifact),
        submitter="教务数据交接人 李四",
        generator="tools/sysu_course_offering_collector.js",
        review_evidence_sha256="a" * 64,
    )])

    record = load_trust_anchor({TRUST_ANCHOR_ENV: str(anchor)}).approvals[0]
    assert record.submitter == "教务数据交接人 李四"
    # ⚠️ `generator` **允许**出现工具名：那是在如实记录 artifact 由什么产出。
    assert record.generator == "tools/sysu_course_offering_collector.js"
    assert record.review_evidence_sha256 == "a" * 64
    assert _check(anchor, sha256_file(artifact)).verified is True


# --------------------------------------------------------------------------- #
# ② 拒绝
# --------------------------------------------------------------------------- #


def test_flow_2_rejected_no_record(tmp_path: Path) -> None:
    """拒绝：组长不写记录 ⇒ 校验不通过（⛔ 不是"默认放行"）。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [])

    result = _check(anchor, sha256_file(artifact))
    assert result.verified is False
    assert result.reason == ProvenanceReason.APPROVAL_MISSING


def test_rejected_when_approver_is_the_generating_tool(tmp_path: Path) -> None:
    """⛔ 自签：把生成工具的名字写进 `approver` ⇒ 锚点整体非法。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(
        sha256_file(artifact), approver="catalog_draft tool",
    )])

    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(anchor)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_rejected_when_approver_equals_generator(tmp_path: Path) -> None:
    """⛔ 角色分离：`approver` 与 `generator` 不得是同一个人/工具。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(
        sha256_file(artifact), generator=FIXTURE_APPROVER,
    )])

    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(anchor)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_rejected_when_evidence_digest_is_not_a_digest(tmp_path: Path) -> None:
    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(
        sha256_file(artifact), review_evidence_sha256="not-a-digest",
    )])

    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(anchor)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


# --------------------------------------------------------------------------- #
# ③ 篡改
# --------------------------------------------------------------------------- #


def test_flow_3_tampered_artifact(tmp_path: Path) -> None:
    """篡改：批准之后改一个字节 ⇒ 摘要漂移 ⇒ 拒绝。"""

    artifact = _write_case(tmp_path)
    approved = sha256_file(artifact)
    anchor = _write_anchor(tmp_path, [_record(approved)])

    # 批准之后把学分从 3.0 改成 4.0
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["new"]["course_records"][0]["credit"] = 4.0
    artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _check(anchor, sha256_file(artifact))
    assert result.verified is False
    assert result.reason == ProvenanceReason.DIGEST_MISMATCH


def test_tampered_completeness_field_is_caught(tmp_path: Path) -> None:
    """把 `complete` 从 false 改成 true 也算篡改（摘要变了）。"""

    artifact = _write_case(tmp_path, complete=False)
    approved = sha256_file(artifact)
    anchor = _write_anchor(tmp_path, [_record(approved)])

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["new"]["complete"] = True
    payload["new"]["completeness_evidence"] = "伪造的依据"
    artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _check(anchor, sha256_file(artifact))
    assert result.verified is False
    assert result.reason == ProvenanceReason.DIGEST_MISMATCH


# --------------------------------------------------------------------------- #
# ④ 过期
# --------------------------------------------------------------------------- #


def test_flow_4_expired(tmp_path: Path) -> None:
    artifact = _write_case(tmp_path)
    digest = sha256_file(artifact)
    anchor = _write_anchor(tmp_path, [_record(digest, expires_at="2020-01-01T00:00:00Z")])

    result = _check(anchor, digest)
    assert result.verified is False
    assert result.reason == ProvenanceReason.APPROVAL_EXPIRED


def test_not_yet_expired_still_verifies(tmp_path: Path) -> None:
    artifact = _write_case(tmp_path)
    digest = sha256_file(artifact)
    anchor = _write_anchor(tmp_path, [_record(digest, expires_at="2099-01-01T00:00:00Z")])

    assert _check(anchor, digest).verified is True


# --------------------------------------------------------------------------- #
# ⑤ 撤销
# --------------------------------------------------------------------------- #


def test_flow_5_revoked(tmp_path: Path) -> None:
    """撤销：记录保留但标记 revoked ⇒ 明确报 `approval_revoked`（⛔ 不是"从未批准"）。"""

    artifact = _write_case(tmp_path)
    digest = sha256_file(artifact)
    anchor = _write_anchor(tmp_path, [_record(digest, **{
        "revoked": True,
        "revoked_at": "2026-10-11T00:00:00Z",
        "revoked_by": FIXTURE_APPROVER,
        "revocation_reason": "材料被替换",
    })])

    result = _check(anchor, digest)
    assert result.verified is False
    assert result.reason == ProvenanceReason.APPROVAL_REVOKED
    assert "材料被替换" in result.message


def test_revocation_does_not_delete_the_audit_trail(tmp_path: Path) -> None:
    """撤销**不删除**记录：审计链必须还能回答"何时、被谁、因为什么"。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(sha256_file(artifact), **{
        "revoked": True,
        "revoked_at": "2026-10-11T00:00:00Z",
        "revoked_by": FIXTURE_APPROVER,
        "revocation_reason": "来源存疑",
    })])

    record = load_trust_anchor({TRUST_ANCHOR_ENV: str(anchor)}).approvals[0]
    assert record.revoked is True
    assert record.revoked_at == "2026-10-11T00:00:00Z"
    assert record.revoked_by == FIXTURE_APPROVER
    assert record.revocation_reason == "来源存疑"
    # 原件摘要仍然留在记录里，便于追溯"曾经批准过哪一份"
    assert record.artifact_sha256 == sha256_file(artifact)


@pytest.mark.parametrize("missing", ["revoked_at", "revoked_by", "revocation_reason"])
def test_half_filled_revocation_is_rejected(tmp_path: Path, missing: str) -> None:
    """⛔ 不允许"撤了一半"：revoked=true 时三个撤销字段都必须有值。"""

    artifact = _write_case(tmp_path)
    record = _record(sha256_file(artifact), **{
        "revoked": True,
        "revoked_at": "2026-10-11T00:00:00Z",
        "revoked_by": FIXTURE_APPROVER,
        "revocation_reason": "来源存疑",
    })
    record.pop(missing)
    anchor = _write_anchor(tmp_path, [record])

    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(anchor)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_revocation_fields_without_the_flag_are_rejected(tmp_path: Path) -> None:
    """`revoked` 缺省为 false ⇒ 不得同时填撤销字段（⛔ 拒绝模糊记录）。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(
        sha256_file(artifact), revoked_at="2026-10-11T00:00:00Z",
    )])

    with pytest.raises(TrustAnchorUnavailable) as excinfo:
        load_trust_anchor({TRUST_ANCHOR_ENV: str(anchor)})
    assert excinfo.value.reason == ProvenanceReason.ANCHOR_INVALID


def test_revocation_takes_priority_over_expiry(tmp_path: Path) -> None:
    """同时撤销且过期 ⇒ 报**撤销**（主动决定比被动过期更需要人看到理由）。"""

    artifact = _write_case(tmp_path)
    digest = sha256_file(artifact)
    anchor = _write_anchor(tmp_path, [_record(digest, **{
        "expires_at": "2020-01-01T00:00:00Z",
        "revoked": True,
        "revoked_at": "2026-10-11T00:00:00Z",
        "revoked_by": FIXTURE_APPROVER,
        "revocation_reason": "来源存疑",
    })])

    assert _check(anchor, digest).reason == ProvenanceReason.APPROVAL_REVOKED


def test_re_review_adds_a_new_record_for_new_content(tmp_path: Path) -> None:
    """重新审核：内容变了 ⇒ **新增**一条记录，旧记录保持 revoked。"""

    artifact = _write_case(tmp_path)
    old_digest = sha256_file(artifact)

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["new"]["course_records"][0]["credit"] = 4.0
    artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    new_digest = sha256_file(artifact)

    anchor = _write_anchor(tmp_path, [
        _record(old_digest, **{
            "revoked": True,
            "revoked_at": "2026-10-11T00:00:00Z",
            "revoked_by": FIXTURE_APPROVER,
            "revocation_reason": "材料被替换",
        }),
        _record(new_digest, approved_at="2026-10-12T00:00:00Z",
                authorization="重新审核纪要 2026-10-12"),
    ])

    # 新内容通过
    assert _check(anchor, new_digest).verified is True
    # 旧内容仍然被撤销（⛔ 不会因为"新记录存在"而复活）
    assert _check(anchor, old_digest).reason == ProvenanceReason.APPROVAL_REVOKED


# --------------------------------------------------------------------------- #
# 工具：待审核清单 + ⛔ 不能写锚点
# --------------------------------------------------------------------------- #


def test_evidence_tool_emits_the_review_checklist(tmp_path: Path) -> None:
    """清单必须含任务书要求的全部列，且结论固定为"待组长审核"。"""

    artifact = _write_case(tmp_path)
    out = tmp_path / "review.json"
    code, stdout, stderr = _run_tool(
        "evidence", "--artifact", str(artifact), "--kind", "curriculum_case",
        "--source", "学校培养方案交接批次 2026-10", "--out", str(out),
    )

    assert code == 0, stderr
    document = json.loads(out.read_text(encoding="utf-8"))
    item = document["items"][0]

    assert document["evidence_format"] == "real_data_review_evidence"
    assert item["kind"] == "curriculum_case"
    assert item["file_name"] == "case-a.json"
    assert item["source"] == "学校培养方案交接批次 2026-10"
    assert item["version"]["target_version_id"] == "fixture-new-2025"
    assert item["semester"]["as_of_term"] == "2025-2"
    assert item["artifact_sha256"] == sha256_file(artifact)
    assert isinstance(item["parse_issues"], list)
    assert item["completeness"]["complete"] is True
    # ⛔ 工具**永远**只写这个结论
    assert item["review_conclusion"] == "pending_group_lead_review"
    assert item["reviewer_questions"], "必须给出组长需要回答的问题"
    # ⛔ 清单里不得出现绝对路径
    assert str(tmp_path) not in out.read_text(encoding="utf-8")


def test_evidence_tool_reports_parse_issues_without_fixing_them(tmp_path: Path) -> None:
    """解析异常只**转述**，⛔ 工具不修补、⛔ 不改 artifact。"""

    artifact = _write_case(tmp_path, complete=False)
    before = artifact.read_bytes()
    code, _stdout, stderr = _run_tool(
        "evidence", "--artifact", str(artifact), "--kind", "curriculum_case",
        "--source", "synthetic fixture",
    )

    assert code == 0, stderr
    document = json.loads(_stdout)
    item = document["items"][0]
    # 如实转述：这份 case 声明自己**不完整**
    assert item["completeness"]["complete"] is False
    # `complete=false` 且没有依据 = **自洽**（如实声明不完整）；
    # 不自洽的是"声明完整却没有依据"那一种。工具只判定这一条机械事实。
    assert item["completeness"]["self_consistent"] is True
    # 解析异常列存在（即使为空也必须是数组，便于组长逐条核对）
    assert isinstance(item["parse_issues"], list)
    # artifact 未被修改
    assert artifact.read_bytes() == before


def test_evidence_tool_flags_complete_without_evidence(tmp_path: Path) -> None:
    """`complete=true` 却没有 `completeness_evidence` ⇒ 工具必须标为不自洽。

    ⚠️ 这是工具**唯一**能确定的自洽判定（`catalog.py` / `requirements.py`
    本来就强制这条不变量）。⛔ 工具不判断"数据真的完整吗"。
    """

    artifact = tmp_path / "case-bad.json"
    payload = _case_payload(complete=True)
    payload["new"]["completeness_evidence"] = None
    artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    code, stdout, stderr = _run_tool(
        "evidence", "--artifact", str(artifact), "--kind", "curriculum_case",
        "--source", "synthetic fixture",
    )

    assert code == 0, stderr
    item = json.loads(stdout)["items"][0]
    assert item["completeness"]["self_consistent"] is False
    codes = {issue["code"] for issue in item["parse_issues"]}
    assert "complete_without_evidence" in codes


def test_evidence_tool_refuses_to_write_the_live_anchor_path(tmp_path: Path) -> None:
    """⛔ 硬检查：`--out` 指向 `APP_TRUST_ANCHOR_PATH` ⇒ 拒绝写入（退出码 3）。"""

    artifact = _write_case(tmp_path)
    live = tmp_path / "trust-anchor.json"
    code, _stdout, stderr = _run_tool(
        "evidence", "--artifact", str(artifact), "--kind", "curriculum_case",
        "--source", "synthetic fixture", "--out", str(live),
        env_anchor=str(live),
    )

    assert code == 3, (code, stderr)
    assert "refused_to_write_the_approval_anchor" in stderr
    assert not live.exists(), "⛔ 工具不得创建锚点文件"


def test_evidence_tool_exposes_no_approve_or_revoke_command() -> None:
    """⛔ 工具**不提供**任何批准 / 撤销子命令（接口设计层面的保证）。"""

    code, stdout, stderr = _run_tool("--help")
    assert code == 0, stderr
    for forbidden in ("approve", "approval", "revoke", "sign", "grant"):
        assert forbidden not in stdout.lower().split("options:")[0], (
            f"⛔ 工具不得暴露 {forbidden!r} 子命令"
        )


def test_evidence_tool_cannot_be_pointed_at_a_real_approval(tmp_path: Path) -> None:
    """⛔ 工具产出的清单**不是**批准记录：它没有 approver / authorization 字段。"""

    artifact = _write_case(tmp_path)
    code, stdout, _stderr = _run_tool(
        "evidence", "--artifact", str(artifact), "--kind", "curriculum_case",
        "--source", "synthetic fixture",
    )
    assert code == 0
    document = json.loads(stdout)
    text = json.dumps(document, ensure_ascii=False)
    assert "approver" not in text
    assert "authorization" not in text


def test_check_anchor_reports_status_without_deciding(tmp_path: Path) -> None:
    """`check-anchor` 只报告状态；⛔ 它不能批准、也不能撤销。"""

    artifact = _write_case(tmp_path)
    digest = sha256_file(artifact)
    anchor = _write_anchor(tmp_path, [
        _record(digest),
        _record("b" * 64, **{
            "revoked": True,
            "revoked_at": "2026-10-11T00:00:00Z",
            "revoked_by": FIXTURE_APPROVER,
            "revocation_reason": "来源存疑",
        }),
    ])

    code, stdout, stderr = _run_tool("check-anchor", "--anchor", str(anchor))
    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["status"] == "loaded"
    assert payload["approval_count"] == 2
    states = {record["artifact_sha256"]: record["revoked"] for record in payload["records"]}
    assert states[digest] is False
    assert states["b" * 64] is True


def test_check_anchor_rejects_a_self_issued_anchor(tmp_path: Path) -> None:
    """自签锚点 ⇒ `check-anchor` 明确报 rejected（⛔ 不静默通过）。"""

    artifact = _write_case(tmp_path)
    anchor = _write_anchor(tmp_path, [_record(
        sha256_file(artifact), approver="prepare_real_case_a_runtime",
    )])

    code, _stdout, stderr = _run_tool("check-anchor", "--anchor", str(anchor))
    assert code == 4
    assert "trust_anchor_invalid" in stderr


# --------------------------------------------------------------------------- #
# 结构性：Agent 无法自行批准
# --------------------------------------------------------------------------- #


def test_tool_source_has_no_write_to_the_live_anchor_path() -> None:
    """结构层：源码里**没有**任何"写锚点"的代码路径。

    ⛔ 唯一的写入目标是**清单**（`--out`），而且写之前会拒绝锚点路径。
    """

    source = TOOL.read_text(encoding="utf-8")
    # 工具里不得出现 subcommands 形式的批准/撤销
    for forbidden in ('add_parser("approve"', "add_parser('approve'",
                      'add_parser("revoke"', "add_parser('revoke'"):
        assert forbidden not in source, f"⛔ 工具不得有 {forbidden}"
    # 唯一的 write_text 必须只服务于清单输出
    assert source.count("write_text") == 1, "⛔ 工具只应有一处写文件的代码"
    assert "_refuse_if_anchor_path" in source


def test_runtime_reads_the_anchor_and_never_writes_it() -> None:
    """结构层：provenance 模块只有读路径（`read_text`），没有写锚点的代码。"""

    module = REPOSITORY_ROOT / "backend" / "app" / "provenance" / "__init__.py"
    source = module.read_text(encoding="utf-8")
    assert "read_text" in source
    for writer in ("write_text", "json.dump(", "open(", "os.replace", "shutil"):
        if writer == "open(":
            # `sha256_file` 用 `open(path, "rb")` 只读——必须不是写模式
            assert '"rb"' in source
            continue
        assert writer not in source, f"⛔ provenance 模块不得出现 {writer}"
