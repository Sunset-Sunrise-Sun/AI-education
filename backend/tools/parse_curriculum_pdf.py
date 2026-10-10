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
from app.curriculum.pdf_reader import (  # noqa: E402
    inspect_curriculum_pdf,
    load_curriculum_pdf,
)
from app.services.curriculum_pdf_ingest import (  # noqa: E402
    build_draft_from_result,
    describe_outcome,
)

__all__ = ["main"]

EXIT_OK = 0
EXIT_ARGUMENTS = 2
EXIT_INPUT = 4

#: 默认表格声明。⚠️ 这是"从哪一列取值"的**声明**，⛔ 不是"猜哪一列是课程号"。
#: 每个候选都必须与表头单元格文字**完全相等**；全部不匹配 ⇒ 整表拒绝。
DEFAULT_TABLES: list[dict] = [{
    "mode": "tables",
    "table_index": 1,
    "columns": {
        "sequence": 1, "course_id": 2, "course_name": 3,
        "credit": 4, "requirement": 5, "recommended_term_text": 6,
    },
    "expected_headers": {
        "sequence": ["序号", "No.", "No", "Seq", "Sequence"],
        "course_id": ["课程号", "课程编号", "Course Code", "Course No.", "Code"],
        "course_name": ["课程名称", "课程名", "Course Name", "Course Title", "Title"],
        "credit": ["学分", "Credit", "Credits"],
        "requirement": ["课程类别", "课程性质", "必修/选修", "Category", "Type", "Kind"],
        "recommended_term_text": ["建议学期", "开课学期", "修读学期", "Term", "Semester", "When"],
    },
    "requirement_values": {
        "必修": "required", "选修": "elective",
        "required": "required", "elective": "elective",
    },
}]


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
    parser.add_argument("--pdf", required=True, help="仓库外的 PDF 路径（⛔ 不进 Git）")
    parser.add_argument("--major", required=True, help="专业名（由人给出，⛔ 不从 PDF 推断）")
    parser.add_argument("--cohort", required=True, help="年级（由人给出）")
    parser.add_argument("--role", default="origin", choices=("origin", "target"))
    parser.add_argument("--source", default="未提供来源说明", help="来源说明（提交者提供）")
    # ⚠️ `--out` 只在**解析**模式下必需；`--inspect` 是只读检查，不需要输出目录。
    #    这里不能用 `required=True`，否则 `--inspect` 单独跑会被参数校验挡下。
    parser.add_argument("--out", default=None, help="输出目录（仓库外；解析模式必需）")
    parser.add_argument(
        "--profile", default=None,
        help="可选：覆盖默认表格声明的 JSON 文件（当真实表头与默认不同时由人提供）",
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

    tables = DEFAULT_TABLES
    if args.profile:
        try:
            loaded = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(json.dumps({"status": "failed", "reason": "profile_unreadable"},
                             ensure_ascii=False), file=sys.stderr)
            return EXIT_INPUT
        # 允许两种形状：直接的 profile 列表，或带说明的包装对象（便于归档人读的注释）。
        # ⚠️ 只有 `tables` 会进解析器；⛔ 包装里的说明文字不参与任何判断。
        if isinstance(loaded, dict) and isinstance(loaded.get("tables"), list):
            tables = loaded["tables"]
        elif isinstance(loaded, list):
            tables = loaded
        else:
            print(json.dumps({"status": "failed", "reason": "profile_must_be_a_list"},
                             ensure_ascii=False), file=sys.stderr)
            return EXIT_INPUT
        # ⛔ 每个声明都必须是纯 profile：未知键会被 pdf_reader fail closed 拒绝。
        if any(not isinstance(spec, dict) for spec in tables):
            print(json.dumps({"status": "failed", "reason": "profile_entry_must_be_an_object"},
                             ensure_ascii=False), file=sys.stderr)
            return EXIT_INPUT

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
        result = load_curriculum_pdf(data, source_id=source_id, tables=tables)
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
