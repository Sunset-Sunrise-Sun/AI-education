# DOCX → 目录草稿工具（任务 B）：设计、可行性判定与人工确认清单

> 分支：`feature/real-capability-readiness`（基线 `f537bee`）
> 代码：`backend/app/curriculum/catalog_draft.py`、`backend/tools/build_catalog_draft.py`
> 测试：`backend/tests/test_catalog_draft.py`（8 项，全部使用**合成** DOCX）

---

## 1. 可行性判定：**可以做，而且能大量复用既有模块**

| 结论 | 说明 |
| --- | --- |
| 解析 DOCX | ✅ **完全复用** `app.curriculum.docx_reader.load_curriculum_docx`（⛔ 未重写任何解析逻辑） |
| 需要新写的只有 | ① **序列化器**（把解析结果落成 JSON——仓库里原本没有任何 catalog 写入代码）；② 一层薄 CLI |
| 是否需要改公共 Schema | ⛔ **不需要**：输出形状就是 `catalog.py` 已接受的内部 artifact 形状 |
| 是否需要 `python-docx` | ⛔ **不需要**（`docx_reader.py` 只用标准库 `zipfile` + `ElementTree`；`python-docx` 只在测试里用来**构造**夹具） |

既有可复用链路（全部已存在）：

```python
from app.curriculum.docx_reader import load_curriculum_docx
from app.curriculum.plan_profiles import plan_profiles, plan_group_records

draft = load_curriculum_docx(docx_path, source_id=..., tables=plan_profiles(role))
version = draft.to_version(version_id=..., major=..., cohort=...,
                           group_records=plan_group_records(role), complete=False)
```

---

## 2. 转换流程（实际实现）

```text
① 选择列映射
   ├─ --role source|target  → 复用仓库已冻结的 Case A 档案（plan_profiles.py）
   └─ --profile profile.json → 人工声明 {source_id, tables[, group_records]}
   ⛔ 表索引 / 列位 / 锚点**绝不猜测**：没有声明就报错退出，不会"试着读读看"。

② 解析（复用 docx_reader）
   └─ 行级取值 + 行级问题（unresolved_course_id / unresolved_credit / unmapped_requirement …）

③ 分流
   ├─ 已确定的行 → course_records[]
   └─ 未确定的行 → unresolved_rows[]（⛔ 不丢弃、⛔ 不猜值）

④ 产出两个文件
   ├─ 审核中间格式（--out-audit）：来源文件 / 原始条目 / 证据 / 待确认清单 / 问题
   └─ 目录草稿（--out）：verification.verified = false、complete = false
```

### 命令示例

```powershell
cd backend
$env:PYTHONUTF8 = '1'

python tools/build_catalog_draft.py --docx <path.docx> --role target `
    --version-id net-2025 --major 网络空间安全 --cohort 2025 `
    --out draft.json --out-audit draft-audit.json
```

---

## 3. 哪些字段能**机械提取**，哪些**必须人工确认**

| ✅ 可从文档 + 声明映射机械提取 | ⛔ 必须人工确认（工具**不猜**） |
| --- | --- |
| `course_id`（占位符会被拒，产出 `unresolved_course_id`） | `recommended_semester` / `deadline_semester`（解析器**不**把学期文字转成序号） |
| `course_name`（按 `course_name_lines` 取前 N 行） | `prerequisites`（解析器把先修关系**硬编码为 None**） |
| `credit`（非数字 ⇒ `unresolved_credit`，⛔ 不猜） | `group_records[].minimum_credit`（**必须**是文档明示数值，⛔ 不是成员学分之和） |
| `requirement`（按表声明或 `requirement_values` 映射） | `group_records[].name` / `source_record`（"哪一行写了这个数字"） |
| `course_type` / `group_id`（按**表**声明） | `verification.verified` / `evidence` / `verified_by` |
| `recommended_term_text`（**原文**，⛔ 不转换） | `complete` + `completeness_evidence`（计数**不能**当完整性证据） |
| `source_record` = `table:T!row:R`（版本内唯一） | `version_id` / `major` / `cohort` / `campus` / `track` / `total_credit` … |
| 整个 `versions[]` 的形状与校验 | `supported` / `unsupported_reason`；任何超出映射的 `requirement` 文本 |
| 哪张表 / 哪些列 / 哪个锚点（Case A 两份已冻结） | 混合课程组的历史学分拆分（需 `ConfirmedGroupScopeDecision` + 证据） |

> 上表的"机械"一侧已在 `tests/test_catalog_draft.py` 里逐项断言；
> "人工"一侧被写成 `human_required` 清单（`test_human_required_lists_every_uninferable_field`）。

---

## 4. 草稿 → 可用目录，人必须补什么

1. `verification.verified = true`（**真布尔**）+ 非空 `verification.evidence`（可加 `verified_by`）；
2. 建议 `complete = true` + 非空 `completeness_evidence`
   （因为 `matching.py` 的组覆盖判定要求 `diff.new.complete`，否则选修池永远算不清）；
3. 每个 `group_records[].minimum_credit` 的**文档明示数值**；
4. `version_id`（全局唯一——**重复会让该 id 下所有条目都不可选**）、`major`、`cohort`、`source_id`；
5. `unsupported_reason` 保持 null（或把 `supported` 设为 false）；
6. 逐条处理 `unresolved_rows` 与 `document_issues`。

⛔ **工具不会、也不允许自动完成这一步**：`draft_to_catalog_payload()` 把
`verified` 与 `complete` **硬编码为 false**，函数签名里根本没有把它们打开的开关。

---

## 5. 为什么草稿"放进运行时目录也不会半可用"

`catalog.py:367-369`：`verified=false` 或 `evidence is None` ⇒ 该条目以
`not_verified` 被**拒绝**，`format_supported=True` 但 `entries` 为空。

因此把草稿命名为 `catalog.json` 放进 `APP_PERSONAL_CATALOG_DIR` 的结果是
**"没有可选版本"**（fail closed），而不是"看起来能用一点"。

这一条已写成可执行断言：
`test_draft_placed_in_catalog_dir_is_rejected_not_half_usable`
（断言 `entries == ()`、`selectable == ()`、`rejections` 含 `not_verified`）。

---

## 6. 已实现文件的边界声明

| 文件 | 改了什么 | 边界 |
| --- | --- | --- |
| `backend/app/curriculum/catalog_draft.py`（新增） | 纯序列化 + 分流；⛔ 不解析 DOCX、⛔ 不判定核验 | 只消费 `docx_reader` 的输出 |
| `backend/tools/build_catalog_draft.py`（新增） | 薄 CLI；⛔ 不改既有 `python -m app.curriculum` 的参数面 | 独立工具 |
| `backend/tests/test_catalog_draft.py`（新增） | 8 项合成 DOCX 回归 | 全合成夹具，⛔ 无真实培养方案进仓库 |

⛔ **未修改**：`docx_reader.py`、`plan_profiles.py`、`catalog.py`、`requirements.py`、
`case.py`、`matching.py`、`__main__.py`；⛔ **未修改**任何公共 Schema。

---

## 7. 仍未完成 / 需要人工确认

| # | 事项 | 性质 |
| --- | --- | --- |
| 1 | `plan_profiles.py` 仍**没有生产调用方**（只被测试使用）；本工具是第一个可用的调用入口，但它是**人工步骤**，不是自动流水线 | 需确认是否要接进运行时 |
| 2 | 非 Case A 的文档需要**人工写 profile**（表索引 / 列位 / 锚点 / `column_count`） | 属人工声明，工具⛔ 不会推断 |
| 3 | `to_version()` 在**任何**行级问题存在时整体失败；本工具因此走 `draft.rows` 直接序列化，**不做** `to_version` | 设计选择，已写进 docstring |
| 4 | 结构化不匹配（行宽、锚点、横向合并压到映射列）会让**整份文档**失败关闭，无法产出"部分草稿" | 解析器既有安全行为，本轮不放松 |
| 5 | 真实培养方案 DOCX 仍**不在仓库内**（`docs/curriculum/INPUTS.md`），因此本工具**从未**在真实文档上运行过 | **NOT VERIFIED** |
