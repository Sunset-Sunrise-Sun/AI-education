"""把一份**培养方案 PDF** 解析成「解析准确性报告 + 未识别课程清单」。

```powershell
cd backend
$env:PYTHONUTF8 = '1'

# 1) 先看用法
python tools/parse_curriculum_pdf.py --help

# 2) 解析一份 PDF（⛔ 不写目录、⛔ 不写批准锚点）
python tools/parse_curriculum_pdf.py `
    --pdf "<仓库外的 PDF 路径>" `
    --major "遥感科学与技术" --cohort 2025 --role origin `
    --source "教务系统保存网页重排生成的 PDF" `
    --out "<仓库外的输出目录>"
```

产出（全部在 `--out` 指定目录，⛔ 不写仓库）：

```text
<out>/<basename>.courses.json   解析出的课程行（含 page:N!row:M 定位）
<out>/<basename>.unresolved.json 未识别课程清单（行级问题）
<out>/<basename>.issues.json     文档级问题
<out>/<basename>.report.txt      人可读报告
```

## ⛔ 这个工具**不做**什么

- ⛔ 不批准、⛔ 不写批准锚点、⛔ 不写 `APP_PERSONAL_CATALOG_DIR`；
- ⛔ 不从课程名猜课程号、⛔ 不推导课程组学分要求、⛔ 不判定跨专业等价；
- ⛔ 不对扫描件做 OCR（明确报错并转人工）；
- ⛔ 不把结果标成已核验（`verification.verified=false` 是硬编码的）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.curriculum.errors import CurriculumNormalizationError  # noqa: E402
from app.curriculum.pdf_profiles import (  # noqa: E402
    DOCUMENT_TYPES,
    detect_document_type,
    list_document_types,
    load_curriculum_pdf_verified,
    profile_for,
)
from app.curriculum.pdf_reader import inspect_curriculum_pdf  # noqa: E402
from app.services.curriculum_pdf_ingest import (  # noqa: E402
    build_draft_from_result,
    describe_outcome,
)

__all__ = ["main"]

EXIT_OK = 0
EXIT_ARGUMENTS = 2
EXIT_INPUT = 4

class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(EXIT_ARGUMENTS, "参数无效，请运行 --help 查看用法。\n")


def _row_payload(row: object) -> dict:
    return {
        "course_id": row.course_id,  # type: ignore[attr-defined]
        "course_name": row.course_name,  # type: ignore[attr-defined]
        "credit": row.credit,  # type: ignore[attr-defined]
        "requirement": row.requirement.value,  # type: ignore[attr-defined]
        "source_record": row.source_record,  # type: ignore[attr-defined]
        "course_type": row.course_type,  # type: ignore[attr-defined]
        "group_id": row.group_id,  # type: ignore[attr-defined]
        "recommended_term_text": row.recommended_term_text,  # type: ignore[attr-defined]
        "issues": [
            {"code": issue.code, "field": issue.field, "row_index": issue.row_index}
            for issue in row.issues  # type: ignore[attr-defined]
        ],
    }


def _write(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )


def _readable_stem(pdf_path: Path) -> str:
    """把 percent-encoded 的下载文件名解成可读 stem；⛔ 解不出就用原样。"""

    stem = pdf_path.stem
    if "%" not in stem:
        return stem
    from urllib.parse import unquote

    decoded = unquote(stem)
    # ⛔ 只接受"解出来更可读"的情况；不引入路径分隔符或空串。
    if decoded and decoded != stem and not any(ch in decoded for ch in "/\\"):
        return decoded
    return stem


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(
        prog="python tools/parse_curriculum_pdf.py",
        description=(
            "解析一份培养方案 PDF，产出解析准确性报告与未识别课程清单。"
            "⛔ 不批准、⛔ 不写目录 / 锚点、⛔ 不 OCR。"
        ),
    )
    parser.add_argument("--pdf", default=None, help="仓库外的 PDF 路径（⛔ 不进 Git）")
    parser.add_argument("--major", default=None, help="专业名（由人给出，⛔ 不从 PDF 推断）")
    parser.add_argument("--cohort", default=None, help="年级（由人给出）")
    parser.add_argument("--role", default="origin", choices=("origin", "target"))
    parser.add_argument("--source", default="未提供来源说明", help="来源说明（提交者提供）")
    # ⚠️ `--out` 只在**解析**模式下必需；`--inspect` 是只读检查，不需要输出目录。
    #    这里不能用 `required=True`，否则 `--inspect` 单独跑会被参数校验挡下。
    parser.add_argument("--out", default=None, help="输出目录（仓库外；解析模式必需）")
    parser.add_argument(
        "--document-type", default=None,
        help=(
            "已验收文档类型的 key（例如 yuangan-2025 / netsec-2025）。"
            "⚠️ 它只是**断言**：会与按内容结构判定的结果核对，不一致即拒绝。"
            "省略时完全按内容结构自动判定。"
        ),
    )
    parser.add_argument(
        "--list-documents", action="store_true",
        help="列出**已验收**的培养方案文档类型后退出（⛔ 不解析、⛔ 不联网）",
    )
    parser.add_argument(
        "--show-tables", action="store_true",
        help="先打印每页识别到的表格数量与表头，便于人工确认声明是否匹配",
    )
    parser.add_argument(
        "--inspect", action="store_true",
        help=(
            "只做逐页结构检查（表格数量 / 列数 / 行数 / 逐行表头原文）并以 JSON 输出，"
            "⛔ 不解析课程、⛔ 不产出草稿。写 profile 前应先跑这个。"
        ),
    )
    parser.add_argument(
        "--inspect-out", default=None,
        help="可选：把 --inspect 的 JSON 写到该路径（便于归档为逐页解析检查记录）",
    )
    args = parser.parse_args(argv)

    if args.list_documents:
        # ⛔ 只读：列出已验收类型，不解析任何文件、不写任何文件。
        print(json.dumps(
            {"document_types": list(list_document_types())}, ensure_ascii=False, indent=2,
        ))
        return EXIT_OK

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        print(json.dumps({"status": "failed", "reason": "pdf_unreadable"},
                         ensure_ascii=False), file=sys.stderr)
        return EXIT_INPUT

    # ⚠️ 解析模式才需要 `--out`；`--inspect` 是纯只读检查。
    if not args.inspect and not args.out:
        parser.error("--out is required unless --inspect is used")

    if args.inspect:
        # ⛔ 只读检查：不解析课程、不产出草稿、不写目录。
        try:
            report = inspect_curriculum_pdf(pdf_path.read_bytes())
        except CurriculumNormalizationError as error:
            print(json.dumps({"status": "failed", "reason": str(error)},
                             ensure_ascii=False), file=sys.stderr)
            return EXIT_INPUT
        report["file_name"] = pdf_path.name
        report["note"] = (
            "⛔ 这不是解析结果。请照抄 header_rows 里的表头原文来写 expected_headers。"
        )
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.inspect_out:
            Path(args.inspect_out).write_text(text, encoding="utf-8")
        print(text)
        return EXIT_OK

    for label, value in (("--pdf", args.pdf), ("--major", args.major),
                         ("--cohort", args.cohort), ("--out", args.out)):
        if not value:
            parser.error(f"{label} is required unless --inspect/--list-documents is used")

    data = pdf_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    source_id = f"pdf-local:sha256:{digest[:16]}"

    if args.show_tables:
        try:
            import pymupdf

            document = pymupdf.open(stream=data, filetype="pdf")
            try:
                for index in range(document.page_count):
                    tables_on_page = list(
                        (document.load_page(index).find_tables().tables) or ()
                    )
                    print(f"page {index + 1}: {len(tables_on_page)} table(s)")
                    for order, table in enumerate(tables_on_page, start=1):
                        rows = table.extract()
                        header = rows[0] if rows else []
                        print(f"  table {order}: columns={len(header)} rows={len(rows)}")
                        print(f"    header={header}")
            finally:
                document.close()
        except CurriculumNormalizationError as error:
            print(json.dumps({"status": "failed", "reason": str(error)},
                             ensure_ascii=False), file=sys.stderr)
            return EXIT_INPUT

    try:
        # ⚠️ **CLI 与 HTTP 共用同一个注册表**（`app/curriculum/pdf_profiles.py`）：
        #    profile 不再来自 CLI 本地的默认声明，⛔ 也不会与 HTTP 各留一份而漂移。
        document, result = load_curriculum_pdf_verified(
            data, source_id=source_id, document_key=args.document_type,
        )
    except CurriculumNormalizationError as error:
        # ⛔ 固定前缀、⛔ 不回显路径；扫描件与损坏文件都在这里明确报告。
        print(json.dumps({
            "status": "failed", "reason": str(error),
            "note": "⛔ 未生成任何猜测结果；请人工处理该 PDF。",
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return EXIT_INPUT

    draft = build_draft_from_result(
        result, role=args.role, file_name=pdf_path.name, source_id=source_id,
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    # ⚠️ 下载来的文件名可能是 percent-encoded（`%E9%81%A5%E6%84%9F...`），
    #    直接拿来做文件名会生成一串看不懂的乱码。这里解回来；
    #    解不出来就退回原始 stem（⛔ 不猜文件名）。
    stem = _readable_stem(pdf_path)

    courses = [_row_payload(row) for row in result.rows]
    unresolved = [item for item in courses if item["issues"]]
    resolved = [item for item in courses if not item["issues"]]

    _write(out_dir / f"{stem}.courses.json", resolved)
    _write(out_dir / f"{stem}.unresolved.json", unresolved)
    _write(out_dir / f"{stem}.issues.json", [_ for _ in draft.document_issues])

    lines = [
        "=" * 72,
        "培养方案 PDF 解析准确性报告（待人工核对）",
        "=" * 72,
        f"文件            : {pdf_path.name}",
        f"SHA-256         : {digest}",
        f"专业 / 年级     : {args.major} / {args.cohort}",
        f"角色            : {args.role}",
        f"来源说明        : {args.source}",
        "",
        f"解析出的课程行  : {len(resolved)}",
        f"未识别的行      : {len(unresolved)}",
        f"文档级问题      : {len(draft.document_issues)}",
        "",
        "⚠️ 审核结论      : pending_group_lead_review（⛔ 工具不下结论）",
        "⚠️ 来源核验      : 未核验（⛔ 上传与解析都不构成来源核验）",
        "⚠️ 完整性        : complete=false（课程组学分要求必须人工填写）",
        "⚠️ 是否为学校正式签发 PDF : 否（本项目使用的 PDF 为教务网页重排生成的转换件）",
        "",
    ]
    if unresolved:
        lines.append("-" * 72)
        lines.append("未识别课程清单（必须人工判定后再决定是否采用）")
        for item in unresolved:
            codes = "、".join(issue["code"] for issue in item["issues"])
            lines.append(
                f"  {item['source_record']}  id={item['course_id']} "
                f"name={item['course_name']} credit={item['credit']} 问题={codes}"
            )
        lines.append("")
    if draft.document_issues:
        lines.append("-" * 72)
        lines.append("文档级问题（⛔ 必须处理后才可能进入正式目录）")
        for issue in draft.document_issues:
            lines.append(
                f"  [{issue['code']}] table={issue['table_index']} row={issue['row_index']}"
            )
        lines.append("")
    lines.append("-" * 72)
    lines.append("必须由人确认的字段")
    for item in draft.human_required:
        lines.append(f"  - {item['field']}（{item['applies_to']}）：{item['reason']}")
    lines.append("")
    lines.append("下一步：请把本报告与本目录下的清单交项目组长，依据**来源材料**逐项核对。")
    lines.append("⛔ 组长批准前，这些草稿不会被任何真实规划使用。")
    (out_dir / f"{stem}.report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = describe_outcome(
        type("_Outcome", (), {  # 轻量包装，只为复用 describe_outcome 的字段口径
            "source_id": source_id, "sha256": digest, "file_name": pdf_path.name,
            "role": args.role, "major": args.major, "cohort": args.cohort,
            "draft": draft, "result": result,
            "review_conclusion": "pending_group_lead_review",
            "row_count": len(draft.course_records),
            "unresolved_count": len(draft.unresolved_rows),
        })(),
        source=args.source,
    )
    print("\n".join(lines))
    print()
    print(json.dumps({
        "status": "parsed", "out_dir": str(out_dir), "summary": summary,
        "note": "⛔ 这不是批准；请组长依据来源材料审核。",
    }, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
