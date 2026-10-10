# PyMuPDF 许可证兼容性评估（任务书第 9 项）

> 结论先行：**在本项目的实际发布方式下，AGPL-3.0 是可以满足的**；
> 但**是否构成"竞赛/交付材料"层面的风险，必须由负责人确认一次**——
> 因为本仓库**没有任何 LICENSE 文件**，发布方式本身尚未被明确声明。
>
> 评估依据：<https://pymupdf.io/licensing>（2026-10-10 抓取）、PyPI `pymupdf` 元数据。

---

## 1. PyMuPDF 的许可模式

| 路径 | 条款 |
| --- | --- |
| **AGPL-3.0**（默认） | 免费使用与再分发；**网络部署**时必须向交互用户提供**对应源代码**；修改过的开源部分须继续以 AGPL 分发；保留生产者声明 |
| **商业许可**（Artifex） | 可闭源；无 AGPL 源码披露义务；含技术支持 |

官方明示的两条 AGPL 义务（原文要点）：

1. **Source Code Disclosure** — "If you deploy the AGPL version in a networked product,
   users interacting with it must receive the corresponding source code under the AGPL."
2. **Code Changes Must Remain Open** — "Any modified version of the open-source code
   must also be distributed under AGPL terms."

⛔ 本项目**没有修改 PyMuPDF**（只调用 `page.find_tables()` / `page.get_text()`），
因此第 2 条不产生额外义务。

---

## 2. 本项目的实际发布方式（事实，非推测）

| 事实 | 核对方式 |
| --- | --- |
| 仓库**公开**托管在 GitHub（`Sunset-Sunrise-Sun/AI-education`） | 远端地址 |
| 后端是**网络服务**（FastAPI，浏览器通过 HTTP 交互） | `backend/app/main.py` |
| 仓库根目录**没有** `LICENSE` / `COPYING` 文件 | `Get-ChildItem -Filter LICENSE*` ⇒ 空 |
| README 与文档里**没有**任何许可声明 | `Select-String -Pattern "许可\|License\|AGPL\|MIT\|Apache"` ⇒ 空 |
| PyMuPDF 只被 `app/curriculum/pdf_reader.py` 使用 | `grep -rn pymupdf backend/app` |

### 2.1 关键判断

AGPL-3.0 的义务是"**向交互用户提供对应源代码**"。
本项目已满足该义务的实质条件：

- 后端源码已在**公开仓库**；
- 服务通过浏览器交互，用户就是仓库的可见对象。

⇒ **在本项目当前的发布方式下，AGPL-3.0 不构成阻塞。**

### 2.2 但有两处必须由人确认

| # | 需要确认的问题 | 为什么 Agent 不能自行决定 |
| --- | --- | --- |
| 1 | 本仓库是否**将来**要改为闭源 / 私有？ | 一旦闭源，AGPL 就要求披露源码，或必须购买 Artifex 商业许可（**涉及费用，属 AGENTS.md §7 必须人工确认**） |
| 2 | 比赛/交付材料里是否要求"可闭源分发"？ | 这是**产品与合规决策**，不是技术选择 |

⚠️ 另外提醒：仓库目前**没有任何许可证声明**。
一个公开仓库没有 LICENSE，会让"用户已获得源码"这一条变得含糊
（默认版权保留，他人无权使用）。**建议负责人明确给出 LICENSE**，
这既解决上述问题，也顺带让 AGPL 合规路径无歧义。

---

## 3. 许可证风险的技术缓解（已完成）

即使将来必须换库，**替换点已被收敛到一处**：

```text
app/curriculum/pdf_reader.py
    load_curriculum_pdf(data, *, source_id, tables) -> DocxImportResult
    inspect_curriculum_pdf(data) -> dict
```

- 上层（`catalog_draft` / `catalog` / 审核 / provenance / Planner）**完全不知道 PDF 库的存在**；
- 依赖只出现在 `pdf_reader.py` 的**两个函数体内部**（延迟导入，便于替换与在无 PDF 支持环境下启动）；
- 测试夹具 `tests/pdf_fixtures.py` 里只有 `build_two_row_header_pdf` 需要用 PyMuPDF 嵌 CJK 字体
  （其余合成 PDF 由**纯标准库**写入器生成），因此换库时测试主体的改动也有限。

### 3.1 若必须改为宽松许可的替代方案

| 方案 | 取舍 |
| --- | --- |
| `pypdf`（BSD） | 无许可风险；但**没有表格识别**，只能抽取文本 ⇒ 需要改成"显式声明列位 + 文本坐标聚类"，识别率与稳健性都会下降 |
| `pdfplumber`（MIT） | 有表格识别（基于线/矩形），许可宽松；换库成本集中在 `pdf_reader.py` 一处 |
| Artifex 商业许可 | 保留现实现；需要采购 |

⛔ 本轮**不**做更换：负责人已明确接受 AGPL（见 PR #75 的开工前确认记录）。

---

## 4. 给负责人的一句话

> PyMuPDF 的 AGPL 与本项目"公开仓库 + 网络服务"的现状是兼容的；
> 需要你确认的是**将来是否会闭源**，以及是否要为仓库补一份 LICENSE。
> 如果两者都保持现状，无需任何改动。
