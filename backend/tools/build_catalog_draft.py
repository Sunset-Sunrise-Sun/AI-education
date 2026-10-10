"""把培养方案 DOCX 转成**待人工审核的目录草稿**（命令行入口）。

```text
# 用仓库里已经冻结的 Case A 档案（两个专业）生成一份草稿 + 审核说明
python tools/build_catalog_draft.py --docx <path.docx> --role target \
    --version-id net-2025 --major 网络空间安全 --cohort 2025 --out draft.json

# 用人工写的 profile（当文档不是 Case A 那两份时）
python tools/build_catalog_draft.py --docx <path.docx> --profile profile.json \
    --version-id x-2025 --major 某专业 --cohort 2025 --out draft.json
```

⛔ 本工具**只产出草稿**：`verification.verified=false`、`complete=false`，
放进 `APP_PERSONAL_CATALOG_DIR` 会被 `catalog.py` 判为 `not_verified` 而不可选择。
⛔ 不修改公共 Schema，⛔ 不猜测文档没写的信息，⛔ 不自动核验。

用法细节见 `python tools/build_catalog_draft.py --help`。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.curriculum import CurriculumNormalizationError  # noqa: E402
from app.curriculum.catalog_draft import (  # noqa: E402
    build_catalog_draft_input,
    draft_to_catalog_payload,
    render_draft_report,
)
from app.curriculum.json_reader import load_json_input  # noqa: E402
from app.curriculum.plan_profiles import (  # noqa: E402
    plan_group_records,
    plan_profiles,
)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # 参数错误可能回显私有文件路径，这里统一改成通用提示。
        self.exit(2, "参数无效，请运行 --help 查看用法。\n")


def _load_profile(args: argparse.Namespace) -> tuple[str, list[dict], list[dict]]:
    """返回 (source_id, tables, group_records)。

    ⛔ 表索引 / 列位 / 锚点**绝不猜测**：要么用仓库已冻结的 Case A 档案，
    要么由调用方提供 profile JSON（`{"source_id", "tables", "group_records"?}`）。
    """

    if args.profile:
        profile = load_json_input(args.profile, label="catalog draft profile")
        if not isinstance(profile, dict):
            raise CurriculumNormalizationError("catalog draft profile: expected an object")
        allowed = {"source_id", "tables", "group_records"}
        if set(profile) - allowed or "source_id" not in profile or "tables" not in profile:
            raise CurriculumNormalizationError(
                "catalog draft profile: expected source_id, tables[, group_records]"
            )
        return (
            str(profile["source_id"]),
            list(profile["tables"]),
            list(profile.get("group_records") or []),
        )

    role = args.role
    return (
        f"{args.draft_source_id or ('docx-' + role)}",
        list(plan_profiles(role)),
        list(plan_group_records(role)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(
        prog="python tools/build_catalog_draft.py",
        description="培养方案 DOCX → 待人工审核的目录草稿（⛔ 不自动核验）",
    )
    parser.add_argument("--docx", required=True, help="本地培养方案 .docx 路径（⛔ 不进 Git）")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--role", choices=("source", "target"),
        help="使用仓库已冻结的 Case A 档案（遥感科学与技术=source / 网络空间安全=target）",
    )
    source.add_argument("--profile", help="人工写的列映射 JSON：{source_id, tables[, group_records]}")
    parser.add_argument("--version-id", required=True, help="版本编号（重复会让该 id 整体不可选）")
    parser.add_argument("--major", required=True, help="专业名")
    parser.add_argument("--cohort", required=True, help="年级")
    parser.add_argument("--campus", default=None)
    parser.add_argument("--track", default=None)
    parser.add_argument("--total-credit", type=float, default=None)
    parser.add_argument("--practice-credit", type=float, default=None)
    parser.add_argument("--study-years", type=int, default=None)
    parser.add_argument(
        "--draft-source-id", default=None,
        help="覆盖 source_id（默认用角色名，如 docx-target）",
    )
    parser.add_argument("--out", default=None, help="把目录草稿 JSON 写到该路径（默认只打印审核说明）")
    parser.add_argument("--out-audit", default=None, help="把审核中间格式 JSON 写到该路径")
    args = parser.parse_args(argv)

    try:
        source_id, tables, groups = _load_profile(args)
        draft = build_catalog_draft_input(
            args.docx, source_id=source_id, tables=tables, role=args.role or "custom",
            group_records=groups,
        )
        payload = draft_to_catalog_payload(
            draft,
            version_id=args.version_id, major=args.major, cohort=args.cohort,
            campus=args.campus, track=args.track, total_credit=args.total_credit,
            practice_credit=args.practice_credit, study_years=args.study_years,
        )
    except CurriculumNormalizationError as exc:
        # ⛔ 错误信息只含字段名 / 行号 / 代码，不回显文档内容或私有路径。
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(render_draft_report(draft))

    if args.out:
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        print()
        print(f"目录草稿已写入：{args.out}")
    if args.out_audit:
        Path(args.out_audit).write_text(
            json.dumps(draft.to_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        print()
        print(f"审核中间格式已写入：{args.out_audit}")

    print()
    print("下一步：按上面『必须由人确认』清单补齐后再把 verification.verified 置为 true。")
    print("⛔ 本工具不会、也不允许自动完成这一步。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
