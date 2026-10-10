# 真实文件验收（第 2 轮）— 状态与实测发现

> 分支：`feature/pdf-curriculum-import`（PR #75，Draft）
> 本轮针对架构审核 CHANGES REQUIRED 的十项要求逐条回应。

---

## 0. 【BLOCKED】两份真实 PDF 仍未到本机

```text
【BLOCKED — 真实材料验收（第 2 轮复核）】
阻塞原因：`C:\Users\28746\Desktop\AI+教育\real-curriculum-pdf\` **目录存在但为空**。
          按任务书给出的**精确文件名**在 C: 与 D: 全盘搜索：
            - 遥感科学与技术_2025级_培养方案.pdf  → 未找到
            - 网络空间安全_2025级_培养方案.pdf    → 未找到
          近 6 小时内 C:/D: 上没有任何与培养方案相关的 PDF 落盘。
已经确认：本轮把真实材料相关的**程序性障碍全部清除**：
          ① 逐页结构检查工具（表格数量/列数/行数/逐行表头原文）已实现并端到端验证；
          ② 双行表头 + 合并单元格 + 分页/不同列数的声明式 profile 已实现并通过负向回归；
          ③ **发现并修复了一个会直接毁掉可追溯性的真实缺陷**（见 §2）；
          ④ PyMuPDF 许可证兼容性评估已完成（见 PYMUPDF_LICENSE_ASSESSMENT.md）。
无法确认：① 两份 PDF 能否被正确读取；② 课程编码/名称/学分/必修选修/建议学期
          能否与源 PDF 逐项核对；③ 跨页课程表与课程分类合并单元格有无静默丢失；
          ④ 真实页数（8 / 9）与真实课程条目数；⑤ 真实表头文字与表格位置；
          ⑥ 如何区分课程明细 / 培养要求学分汇总 / 实践附表（避免重复导入）。
需要人工提供：把两份 PDF 放进上述目录（⛔ 不要提交进 Git）。
在确认前不会：把任何真实 PDF 提交进仓库；⛔ 不用合成数据冒充真实验收结论；
          ⛔ 不把"工具已就绪"写成"验收已通过"。
```

**材料到位后请直接执行**（两步，无需改代码）：

```powershell
cd backend
$env:PYTHONUTF8 = '1'

# 第 1 步：逐页结构检查（任务书要求 1）
python tools/parse_curriculum_pdf.py `
    --pdf "C:\Users\28746\Desktop\AI+教育\real-curriculum-pdf\遥感科学与技术_2025级_培养方案.pdf" `
    --major "遥感科学与技术" --cohort 2025 --role origin `
    --source "教务系统保存网页重排生成的 PDF" `
    --inspect --inspect-out "遥感_逐页解析检查.json"

# 第 2 步：按第 1 步输出的表头原文写 profile（--profile），再解析
python tools/parse_curriculum_pdf.py `
    --pdf "<同上>" --major "遥感科学与技术" --cohort 2025 --role origin `
    --source "<来源说明>" --profile "遥感_profile.json" --out "<仓库外目录>"
```

---

## 1. 逐页表格检查（要求 1）— 工具已实现

新增 `inspect_curriculum_pdf()` / CLI `--inspect`，**只读**输出：

```json
{
  "page_count": 8,
  "total_text_chars": 12345,
  "scanned_suspected": false,
  "pages": [
    { "page": 1, "text_chars": 1500, "table_count": 2, "tables": [
        { "table_index": 1, "column_count": 6, "data_row_count": 41,
          "header_rows": [ ["序号", null, "课程名称", "学分", null, "建议学期"],
                           [null, "课程号", null, "必修", "选修", null] ] } ] } ]
}
```

- `header_rows` 是**逐行表头原文**（最多前 3 行），`expected_headers` 直接照抄即可；
- `null` = 该格为空（合并单元格被吞掉的那一格）；
- ⛔ 不解析课程、⛔ 不猜列位、⛔ 不写目录。

用真实 PDF 的检查结果将原样写入本节（待材料到位）。

---

## 2. ⚠️ 本轮发现并修复的真实缺陷（会毁掉可追溯性）

### 2.1 缺陷：表格行序与页面阅读顺序**相反**

`page.find_tables()` 返回的 `table.extract()`，其**行序不是页面上从上到下的顺序**。
实测一份 4 行表格（表头 2 行 + 数据 2 行）：`extract()` 把**最后一行放在最前面**。

后果非常严重：`source_record = page:{n}!row:{i}` 会**指错行**，
人工拿着它去 PDF 里核对会对不上 —— 而这正是任务书要求的"原始页码/表格位置/行号可追溯"。

`strategy="lines"` / `"lines_strict"` / `"text"` 与 `extract(sort=True)` **都无法纠正**它。

### 2.2 修复：按库给出的行/列几何重建网格

✅ 实测 `table.rows[i].bbox` 的顺序**是**从上到下的（y0 递增）。
因此 `_geometry_grid()` 改为：

- 行 = `table.rows[i].bbox`（顺序可信）；
- 列 = `table.header.cells`（每列的 bbox）；
- 取值 = `page.get_text("text", clip=(列左, 行上, 列右, 行下))`。

横向用**整列**范围（列中点会把跨列文字切碎），纵向用**该行**上下界
（这样既不吃相邻列的边，也不吃表格上下的正文）。
几何不可用时返回 `None` → `table_extraction_unavailable`（**fail closed**，⛔ 不猜顺序）。

### 2.3 为什么这属于"必须修改通用解析器"

- ⛔ **无法只靠 profile 解决**：行序错误发生在 profile 被应用**之前**，
  是"表格 → 二维数组"这一步的缺陷，与列怎么映射无关；
- ⛔ **不改的后果**是产出**错误的可追溯定位**——比报错更糟（错误信息看起来是对的）；
- 修复是**纯几何排序**，没有引入任何取值推断。

### 2.4 负向回归

`tests/test_curriculum_pdf_two_row_header.py` 里新增/覆盖：

| 用例 | 断言 |
| --- | --- |
| 行序 | `source_record == ["page:1!row:1", "page:1!row:2"]`，且第 1 行 = 页面最上面那行数据 |
| 表头不泄漏 | ⛔ 表头文字（"课程号"/"必修"/"选修"）不得变成数据行取值 |
| 行数保持 | 参数化 1/2/3/5/8 行：读出多少行 **== **画出多少行 |
| 集合不可用 | 几何无法解释 ⇒ fail closed |

---

## 3. 双行表头 / 合并单元格 / 分页 / 不同列数（要求 4、5）

### 3.1 声明式扩展：`header_rows`

```json
{
  "mode": "tables", "table_index": 1, "header_rows": 2,
  "columns": { "sequence": 1, "course_id": 2, "course_name": 3,
               "credit": 4, "requirement": 5, "recommended_term_text": 6 },
  "expected_headers": {
    "sequence":     [["序号", null]],
    "course_id":    [[null, "课程号"]],
    "course_name":  [["课程名称", null]],
    "credit":       [["学分", "必修"]],
    "requirement":  [[null, "选修"]],
    "recommended_term_text": [["建议学期", null]]
  },
  "requirement": "required"
}
```

- `header_rows: 1..3`；每个候选是"**每行一个文字**"的列表，`null` = 该行为空；
- 匹配规则：**逐行精确相等**（唯一规范化是两侧 `strip()`，见 §3.3）；
- ⛔ 不做向上填充、⛔ 不做包含匹配、⛔ 不做大小写折叠。

### 3.2 分页 / 不同列数 ⇒ 已有机制足够，⛔ 无需新代码

`table_index` 的语义是"**该页第 N 张表**"，profile 是一个**列表**。
因此：

- 表格跨页 → 每页各声明一条 profile，`source_record` 自带页码；
- 不同页列数不同 → 每条 profile 独立声明自己的 `columns` / `expected_headers`；
- 实践建议（写入 CLI 帮助）：**表格结构相同的页声明一条并复用到每一页**，
  结构不同的页单独声明一条。

### 3.3 ⚠️ 一条必须说清的规范化

表头比较会**两侧 `strip()`**。原因：PDF 单元格常带尾随空格，
而首尾空白与语义无关。除此以外一律要求完全相等。
这一点有专门的测试：`test_header_whitespace_is_the_only_normalisation`
（`"  课程号  "` 命中；`"课程 号"` 拒绝）。

### 3.4 合并单元格的实测结论

**合并单元格不会产生 `""`**，而是 `null`（或横线渲染出的 `"-----"`）。
因此 profile 里 `""` **永远匹配不上** —— 这正是想要的：
⛔ 不允许"向上填充"式的宽松匹配。
（`test_merged_cell_columns_are_matched_by_explicit_nulls_not_by_filling`）

### 3.5 为什么夹具改用 PyMuPDF 嵌 CJK 字体

真实表头是中文，需要**嵌入 CJK 字体 + Identity-H 编码**。
自建的最小写入器只处理 Latin-1 字面量；硬塞 UTF-16BE 十六进制串需要另写一套
字体嵌入器 —— 那已经不是"最小写入器"。
因此 `build_two_row_header_pdf` 用**项目已采用的** PyMuPDF 完成嵌字与排版
（⛔ 没有引入第二个库）；ASCII 用例仍走**纯标准库**写入器。

---

## 4. 课程分类合并单元格与"避免重复导入"（要求 5）

这条**需要真实材料才能判定**（见 §0）。已经就绪的机制：

| 需求 | 现成机制 |
| --- | --- |
| 区分课程明细 / 学分汇总 / 实践附表 | **每页每表一条 profile**：只声明课程明细表的 `table_index`，其余表⛔ 根本不会被声明 ⇒ 不会被导入 |
| 结构性防重复 | `source_record = page:{n}!row:{i}` 是 `CurriculumVersion` 的**唯一性主键**，同一定位不可能出现两条 |
| 汇总表若被误声明 | 表头不匹配 ⇒ `table_header_mismatch` 整表拒绝；或行级 `unresolved_course_id` 进待确认清单 |

⚠️ 唯一无法提前保证的是"真实汇总表的表头长什么样"。
因此**不许**用"名字里有'合计'就跳过"这类规则 —— 那属于猜测（⛔ AGENTS.md §7）。

---

## 5. 不从成员学分求和推断课程组要求（要求 7）

`pdf_reader` **完全不产出** `group_records`（代码里没有这个概念）。
`curriculum_pdf_ingest.build_draft_from_result()` 恒置 `group_records=()`，
并把 `group_records` 写入 `human_required`：

> PDF 解析⛔ 不推导课程组学分要求（文档明示数值须人工填写，⛔ 不得用成员学分求和代替）。

下游 `project_makeup_tasks` 在 `minimum_credit is None` 时 **raise** ⇒ 物理上不可能用求和冒充。

---

## 6. `verification.verified=false` / 不写锚点与目录（要求 8）

| 保证 | 位置 |
| --- | --- |
| `verification.verified=false`、`complete=false` | `draft_to_catalog_payload()` **硬编码** |
| `review_conclusion = pending_group_lead_review` | 常量，无开关 |
| `is_official_school_pdf = false` | 响应**硬编码** |
| ⛔ 不写 `APP_PERSONAL_CATALOG_DIR`、⛔ 不写批准锚点 | 端点只返回内存 payload；测试断言运行后目录为空、锚点不存在 |

---

## 7. 许可证（要求 9）

见 `PYMUPDF_LICENSE_ASSESSMENT.md`。要点：

- PyMuPDF = **AGPL-3.0 或 Artifex 商业许可**双许可；
- AGPL 的义务是"网络部署时向交互用户提供对应源码"；
- 本项目是**公开仓库 + 网络服务** ⇒ **现状下 AGPL 可满足**；
- ⚠️ 需负责人确认：**将来是否会闭源**；以及仓库目前**没有任何 LICENSE 文件**（建议补一份）；
- 替换点已收敛到 `pdf_reader.py` 两个函数（延迟导入），换库成本可控。

---

## 8. 本轮变更清单

| 文件 | 变更 |
| --- | --- |
| `backend/app/curriculum/pdf_reader.py` | 新增 `inspect_curriculum_pdf()`；新增 `header_rows` 多行表头；**修复行序缺陷**（`_geometry_grid` / `_table_rows`）；抽出 `_open_document()` 共用校验 |
| `backend/tools/parse_curriculum_pdf.py` | 新增 `--inspect` / `--inspect-out`；帮助里给出写 profile 的工作流 |
| `backend/tests/pdf_fixtures.py` | 新增 `build_two_row_header_pdf`（CJK 嵌字、双行表头、合并单元格）；修正 ASCII 夹具的行边界与标题间距（实测约束） |
| `backend/tests/test_curriculum_pdf_two_row_header.py` | 新增（25 用例）：逐页检查、双行表头正向、负向回归、空白规范化 |
| `backend/tests/test_curriculum_pdf_reader.py` | 去掉误入 BOM |
| `docs/final_upgrade/PYMUPDF_LICENSE_ASSESSMENT.md` | 新增（要求 9） |
| `docs/final_upgrade/PDF_IMPORT_REAL_ACCEPTANCE.md` | 本文件 |
