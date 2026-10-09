"""生成"只跑 PR #69 原有 18 项"的临时验证变体（不入库）。

用途：对照验证"合并 PR #68 之前就存在的 18 项用例，在合并后的树上是否仍然通过"。

用法（仓库根目录）：
    python tools/browser-e2e/_make_baseline18.py
    node tools/browser-e2e/run_browser_e2e.mjs --cases=_cases_baseline18.mjs

⛔ 生成物 `_cases_baseline18.mjs` 是临时对照文件，验证完即删除，不提交。
"""

from __future__ import annotations

import io
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "cases.mjs"
DST = HERE / "_cases_baseline18.mjs"

#: 联合验收新增的 5 项（PR #69 原始 18 项里没有）
NEW_IDS = [
    "X01-explanation-entry-and-panel",
    "X02-explanation-single-course-focus",
    "U01-transfer-gap-summary",
    "U02-ai-five-stages-and-partitions",
    "U03-supporting-data-section-is-secondary",
]

text = io.open(SRC, encoding="utf-8").read()

for case_id in NEW_IDS:
    needle = "id: '%s'," % case_id
    if needle not in text:
        raise SystemExit("未找到用例 id：" + case_id)
    text = text.replace(needle, "id: '%s', skip: true," % case_id)

io.open(DST, "w", encoding="utf-8", newline="\n").write(text)
print("已生成", DST.name)
