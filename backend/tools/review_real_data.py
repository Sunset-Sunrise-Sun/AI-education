"""产出**待组长审核清单**（证据）并做**只读**锚点自检。

```text
python tools/review_real_data.py evidence --artifact <file> --kind <kind> --source <来源> --out <清单.json>
python tools/review_real_data.py check-anchor --anchor <锚点.json>
```

## 这个工具**不做**什么（⛔ 硬边界）

- ⛔ **不批准**任何东西：它只计算摘要、原样转述解析异常与完整性字段、
  ⛔ 并把"审核结论"固定写成 `pending_group_lead_review`。
- ⛔ **不写锚点**：它没有"批准"子命令。若 `--out` 指向 `APP_TRUST_ANCHOR_PATH`
  或被要求写入锚点路径，工具会**拒绝执行**（退出码 3）。
- ⛔ **不改** artifact 的 `verification.verified` 或 `data_source`。
- ⛔ **不判断**来源是否真实：那是组长的职责（见清单里的 `reviewer_questions`）。

## 为什么不做"批准/撤销"子命令

因为"Agent 能不能自己批准"不应该取决于它**愿不愿意**，而应该取决于它
**有没有能力**。批准记录只能由组长明确授权后的独立受控流程写入锚点文件，
本工具在物理上没有那条路径（见 `docs/final_upgrade/APPROVAL_WORKFLOW_DESIGN.md` §4）。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.provenance import (  # noqa: E402
    APPROVAL_KINDS,
    TRUST_ANCHOR_ENV,
    TrustAnchorUnavailable,
    load_trust_anchor,
    sha256_file,
)

__all__ = ["main"]

#: 清单格式（⛔ 版本不符即拒绝读取）。
EVIDENCE_FORMAT = "real_data_review_evidence"
EVIDENCE_VERSION = 1

#: ⛔ 工具**只能**写这个结论；批准与否由组长填写。
PENDING_CONCLUSION = "pending_group_lead_review"

EXIT_OK = 0
EXIT_ARGUMENTS = 2
EXIT_REFUSED = 3
EXIT_INPUT = 4


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # 参数错误可能回显私有路径，统一改成通用提示。
        self.exit(EXIT_ARGUMENTS, "参数无效，请运行 --help 查看用法。\n")


def _refuse_if_anchor_path(target: Path, *, environment: dict[str, str]) -> None:
    """⛔ 工具**不得**写入批准锚点路径（防误操作的最后一道硬检查）。"""

    live = (environment.get(TRUST_ANCHOR_ENV) or "").strip()
    if not live:
        return
    try:
        same = target.resolve() == Path(live).resolve()
    except OSError:
        same = str(target) == live
    if same:
        print(json.dumps({
            "status": "refused",
            "reason": "refused_to_write_the_approval_anchor",
            "message": (
                f"⛔ 拒绝写入 {TRUST_ANCHOR_ENV} 指向的批准锚点路径。"
                "批准记录只能由组长明确授权后的独立受控流程写入，本工具没有这条路径。"
            ),
        }, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(EXIT_REFUSED)


# --------------------------------------------------------------------------- #
# artifact 适配：只**转述**已有字段，⛔ 不重新解释业务规则
# --------------------------------------------------------------------------- #

def _load_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise _InputError("artifact_unreadable")
    except (ValueError, UnicodeDecodeError):
        raise _InputError("artifact_not_json")
    if not isinstance(payload, dict):
        raise _InputError("artifact_not_object")
    return payload


class _InputError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _detect_kind(payload: dict) -> str | None:
    """按 artifact 的**结构标记**判定类别；⛔ 不猜、不确定就返回 None。"""

    if {"completed", "old", "new"} <= set(payload):
        return "curriculum_case"
    if "versions" in payload and "catalog_version" in payload:
        return "curriculum_catalog"
    if "shards" in payload and "semester" in payload:
        return "course_data_semester_manifest"
    return None


def _completeness(complete: object, evidence: object) -> dict:
    """转述完整性字段，并给出**唯一**一条工具能确定的自洽判定。

    ⚠️ 工具**只**检查一件事：`complete=true` 是否配了非空 `completeness_evidence`
    （这是 `catalog.py` / `requirements.py` 本来就强制的不变量）。
    ⛔ 工具**不**判断"这份数据真的完整吗"——那是组长的职责。
    """

    is_complete = complete is True
    has_evidence = isinstance(evidence, str) and bool(evidence.strip())
    return {
        "complete": complete if isinstance(complete, bool) else None,
        "completeness_evidence": evidence if isinstance(evidence, str) else None,
        # `complete=false` 且没有依据 = 自洽（如实声明不完整）；
        # `complete=true` 但没依据 = **不自洽**（缺少强制要求的完整性依据）。
        "self_consistent": (not is_complete) or has_evidence,
    }


def _curriculum_case_evidence(payload: dict) -> dict:
    target = payload.get("new") if isinstance(payload.get("new"), dict) else {}
    scope = payload.get("makeup_scope") if isinstance(payload.get("makeup_scope"), dict) else {}
    versions = {
        "target_version_id": target.get("version_id"),
        "old_version_id": (payload.get("old") or {}).get("version_id")
        if isinstance(payload.get("old"), dict) else None,
        "catalog_version": None,
    }
    issues: list[dict] = []
    for label in ("old", "new"):
        version = payload.get(label)
        if not isinstance(version, dict):
            continue
        for record in version.get("course_records") or []:
            if not isinstance(record, dict):
                continue
            for name in ("course_id", "course_name", "credit", "requirement", "source_record"):
                if record.get(name) is None:
                    issues.append({
                        "code": "missing_course_field", "version": label,
                        "field": name, "course_id": record.get("course_id"),
                    })
    for decision in payload.get("missing_requirements") or []:
        if isinstance(decision, dict):
            issues.append({"code": "missing_requirement_declared", "version": "case",
                           "field": "missing_requirements", "course_id": None})
    completeness = _completeness(target.get("complete"), target.get("completeness_evidence"))
    if not completeness["self_consistent"]:
        issues.append({"code": "complete_without_evidence", "version": "new",
                       "field": "completeness_evidence", "course_id": None})
    questions = [
        "这份 case 的两个版本是否都来自学校/学院正式培养方案？",
        "makeup_scope 的 as_of_term 是否与本次要做的学籍判断一致？",
        "missing_requirements 里的每一条，是学校规则本来如此，还是本项目推断？",
    ]
    return {
        "version": versions,
        "semester": {"semester": None, "as_of_term": scope.get("as_of_term")},
        "parse_issues": issues,
        "completeness": completeness,
        "reviewer_questions": questions,
    }


def _curriculum_catalog_evidence(payload: dict) -> dict:
    entries = [item for item in (payload.get("versions") or []) if isinstance(item, dict)]
    issues: list[dict] = []
    for index, entry in enumerate(entries, start=1):
        verification = entry.get("verification") if isinstance(entry.get("verification"), dict) else {}
        if verification.get("verified") is not True:
            issues.append({"code": "entry_not_marked_verified", "row": index,
                           "field": "verification.verified", "course_id": None})
        if not verification.get("evidence"):
            issues.append({"code": "entry_missing_evidence", "row": index,
                           "field": "verification.evidence", "course_id": None})
        if entry.get("complete") is not True:
            issues.append({"code": "entry_not_complete", "row": index,
                           "field": "complete", "course_id": None})
    version_ids = [entry.get("version_id") for entry in entries]
    all_complete = bool(entries) and all(entry.get("complete") is True for entry in entries)
    evidence_present = all(
        isinstance((entry.get("verification") or {}).get("evidence"), str)
        and ((entry.get("verification") or {}).get("evidence") or "").strip()
        for entry in entries
    )
    for index, entry in enumerate(entries, start=1):
        if entry.get("complete") is True and not (
            isinstance((entry.get("verification") or {}).get("evidence"), str)
            and ((entry.get("verification") or {}).get("evidence") or "").strip()
        ):
            issues.append({"code": "complete_without_evidence", "row": index,
                           "field": "verification.evidence", "course_id": None})
    completeness = {
        # ⚠️ "complete" 列 = artifact 自己声明的完整性；⛔ 不是工具的判断。
        "complete": all_complete,
        "completeness_evidence": "per-entry verification.evidence" if evidence_present else None,
        "self_consistent": evidence_present,
    }
    questions = [
        "每个 version_id 的培养方案是否都有学校/学院正式来源？",
        "标为 complete 的版本，其完整性依据是什么文件？",
        "是否存在应当排除（如荣誉课程、非本专业）的条目？",
    ]
    return {
        "version": {"catalog_version": payload.get("catalog_version"),
                    "version_ids": version_ids},
        "semester": {"semester": None, "as_of_term": None},
        "parse_issues": issues,
        "completeness": completeness,
        "reviewer_questions": questions,
    }


def _manifest_evidence(payload: dict) -> dict:
    shards = [item for item in (payload.get("shards") or []) if isinstance(item, dict)]
    issues: list[dict] = []
    counts = [item.get("loaded_count") for item in shards]
    for index, shard in enumerate(shards, start=1):
        if shard.get("loaded_count") != shard.get("reported_total"):
            issues.append({"code": "shard_count_mismatch", "row": index,
                           "field": "loaded_count", "course_id": None})
    total = sum(value for value in counts if isinstance(value, int))
    baseline_after = payload.get("baseline_after")
    consistent = isinstance(baseline_after, int) and baseline_after == total
    if not consistent:
        issues.append({"code": "baseline_does_not_match_shard_sum", "row": None,
                       "field": "baseline_after", "course_id": None})
    completeness = {
        # ⚠️ 这里的 `complete` 是"计数自洽"这一**可机械判定**的事实，
        #    ⛔ 不是"这份数据真的完整"的结论（后者由组长判断）。
        "complete": consistent,
        "completeness_evidence": payload.get("inventory_sha256"),
        "self_consistent": consistent,
    }
    questions = [
        "五个校区的开课数据是否都来自用户本人正常权限下可见的页面？",
        "采集时间窗口是否在允许的范围内？是否保存了用户授权依据？",
        "baseline_after 与各校区计数是否与采集当时的页面一致？",
    ]
    return {
        "version": {"target_version_id": None, "acceptance_sha256": payload.get("manifest_sha256")},
        "semester": {"semester": payload.get("semester"), "as_of_term": None},
        "parse_issues": issues,
        "completeness": completeness,
        "reviewer_questions": questions,
    }


_ADAPTERS = {
    "curriculum_case": _curriculum_case_evidence,
    "curriculum_catalog": _curriculum_catalog_evidence,
    "course_data_semester_manifest": _manifest_evidence,
}


def build_evidence_item(*, artifact: Path, kind: str, source: str) -> dict:
    """组装**一条**待审核项（⛔ 不写文件、⛔ 不下结论）。"""

    payload = _load_object(artifact)
    detected = _detect_kind(payload)
    if detected is not None and detected != kind:
        raise _InputError("kind_does_not_match_artifact_shape")
    item = _ADAPTERS[kind](payload)
    return {
        "kind": kind,
        # ⛔ 只写基名，避免泄漏私有目录结构。
        "file_name": artifact.name,
        "source": source,
        "version": item["version"],
        "semester": item["semester"],
        # 对被消费的那份字节计算，⛔ 不规范化、⛔ 不解析后重排。
        "artifact_sha256": sha256_file(artifact),
        "parse_issues": item["parse_issues"],
        "parse_issues_note": "本列**原样转述** artifact 自带字段，⛔ 工具不做解释或修补。",
        "completeness": item["completeness"],
        "review_conclusion": PENDING_CONCLUSION,
        "reviewer_questions": item["reviewer_questions"],
    }


def build_evidence_document(
    *, artifact: Path, kind: str, source: str, now: str,
) -> dict:
    return {
        "evidence_format": EVIDENCE_FORMAT,
        "evidence_version": EVIDENCE_VERSION,
        "generated_at": now,
        "artifact_generator": "tools/review_real_data.py",
        "review_conclusion": PENDING_CONCLUSION,
        "review_conclusion_note": (
            "⛔ 本字段由组长填写；工具**只会**写 "
            f"{PENDING_CONCLUSION}。批准与否不是工具的判断。"
        ),
        "scope_note": (
            "组长批准仅代表**项目内部**确认来源可靠，"
            "⛔ 不代表学校正式认证，也⛔ 不代表课程等价或学分认定。"
        ),
        "items": [build_evidence_item(artifact=artifact, kind=kind, source=source)],
    }


# --------------------------------------------------------------------------- #
# 子命令
# --------------------------------------------------------------------------- #

def _cmd_evidence(args: argparse.Namespace) -> int:
    artifact = Path(args.artifact)
    if not artifact.is_file():
        print(json.dumps({"status": "failed", "reason": "artifact_unreadable"},
                         ensure_ascii=False), file=sys.stderr)
        return EXIT_INPUT
    if args.out:
        _refuse_if_anchor_path(Path(args.out), environment=dict(os.environ))
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        document = build_evidence_document(
            artifact=artifact, kind=args.kind, source=args.source, now=now,
        )
    except _InputError as exc:
        print(json.dumps({"status": "failed", "reason": exc.code},
                         ensure_ascii=False), file=sys.stderr)
        return EXIT_INPUT

    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        item = document["items"][0]
        print(json.dumps({
            "status": "evidence_written",
            "out": Path(args.out).name,
            "artifact_sha256": item["artifact_sha256"],
            "review_conclusion": item["review_conclusion"],
            "note": "⛔ 这不是批准；请组长逐项核对 reviewer_questions 后再决定。",
        }, ensure_ascii=False, indent=2))
    else:
        print(text, end="")
    return EXIT_OK


def _cmd_check_anchor(args: argparse.Namespace) -> int:
    """**只读**自检：锚点能不能装载？每条记录处于什么状态？

    ⚠️ 本命令**只报告状态**，⛔ 既不能批准也不能撤销。它的用途是让组长在
    写入后确认"格式合法、没有被自签检测拦下"。
    """

    path = Path(args.anchor)
    try:
        anchor = load_trust_anchor({TRUST_ANCHOR_ENV: str(path)})
    except TrustAnchorUnavailable as exc:
        print(json.dumps({
            "status": "rejected", "reason": exc.reason, "message": exc.message,
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return EXIT_INPUT

    records = []
    for item in anchor.approvals:
        records.append({
            "kind": item.kind,
            "identity": item.identity_map(),
            "artifact_sha256": item.artifact_sha256,
            "approver": item.approver,
            "submitter": item.submitter,
            "generator": item.generator,
            "approved_at": item.approved_at,
            "expires_at": item.expires_at,
            "revoked": item.revoked,
            "revocation_reason": item.revocation_reason,
            "review_evidence_sha256": item.review_evidence_sha256,
        })
    print(json.dumps({
        "status": "loaded",
        "approval_count": len(records),
        "records": records,
        "note": (
            "⛔ 本输出只表示锚点**格式合法且未触发自签检测**；"
            "它⛔ 不代表来源真实，也⛔ 不代表任何课程认定。"
        ),
    }, ensure_ascii=False, indent=2))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(
        prog="python tools/review_real_data.py",
        description=(
            "产出待组长审核清单（证据）+ 只读锚点自检。"
            "⛔ 本工具不批准、不撤销、不写锚点。"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    evidence = sub.add_parser("evidence", help="产出待审核清单（⛔ 不下结论）")
    evidence.add_argument("--artifact", required=True, help="本地 artifact 路径（⛔ 不进 Git）")
    evidence.add_argument("--kind", required=True, choices=sorted(APPROVAL_KINDS))
    evidence.add_argument("--source", required=True, help="来源说明（由提交者提供，组长核对）")
    evidence.add_argument("--out", default=None, help="清单输出路径（⛔ 不得等于锚点路径）")
    evidence.set_defaults(handler=_cmd_evidence)

    check = sub.add_parser("check-anchor", help="只读自检锚点格式与记录状态")
    check.add_argument("--anchor", required=True, help="锚点文件路径")
    check.set_defaults(handler=_cmd_check_anchor)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
