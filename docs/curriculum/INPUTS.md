# Curriculum 输入

真实文件、映射配置和 case JSON 都放在仓库外。以下编号、路径和字段值仅用于说明。

## 结构化 case

`old`、`new` 使用内部 `CurriculumVersion` 字段，课程放在 `course_records`。`completed` 包含 `source_id` 和 `records`。完整示例见 `mock_data/curriculum_demo/case.json`。

`complete` 默认是 `false`。声明完整必须同时提供 `completeness_evidence`，不能由课程数量推出完整。`rules` 绑定目标版本及已修来源，规则依据不足时不要启用自动认定。`prerequisites: null` 表示未知，空数组表示已确认没有先修，二者不可混用。

只检查统计：

```bash
python -m app.curriculum --case /private/case.json
python -m app.curriculum --inspect-case /private/case.json
```

`--case` 要求整个任务结果可表达，遇未解决组要求会失败。`--inspect-case` 保留内部差异，输出问题数量及 `projection_ready`，不输出课程、成绩或来源文本。可输出公共任务不代表真实认定已经完成。

## Word 表格

Word 解析使用明确映射，不自动解释标题、分区、先修或学校政策。表、行、列编号从 1 开始。每个映射选定表头和数据范围，同一表的不同分区可以分别配置。

映射配置：

```json
{
  "source_id": "mock://example/curriculum",
  "tables": [{
    "table_index": 1,
    "header_row": 1,
    "first_data_row": 2,
    "last_data_row": 5,
    "columns": {"course_id": 1, "course_name": 2, "credit": 3, "recommended_term_text": 4},
    "expected_headers": {"course_id": "课程号", "course_name": "课程名", "credit": "学分", "recommended_term_text": "学期"},
    "requirement": "required",
    "course_type": "示例分区"
  }]
}
```

核心列 `course_id`、`course_name`、`credit` 必须明确映射，`expected_headers` 必须逐列匹配。`requirement` 可为 `required`、`elective`、`unknown`。分类来自已确认分区时用固定值；来自独立列时，在 `columns` 映射 `requirement` 并提供精确的 `requirement_values`。不要根据名称推断必修或选修。

### 两种显式模式：header 与 positional

真实培养方案有两种版式，分别对应两种**互不混用**的 profile 模式。`mode` 缺省为 `header`。

**`header` 模式**（原有行为，未放宽）：必须有 `header_row` 与 `expected_headers`，且 `expected_headers` 的键集合与 `columns` 完全一致；每个映射列的表头文字必须**逐字匹配**该行单元格，不匹配即失败。

**`positional` 模式**：用于**完全没有列标题行**的培养方案（如真实 Case A 的两份文档：第 1、2 行为空，数据自第 3 行起，列义纯位置式）。只接受下列字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `mode` | 是 | 固定 `"positional"` |
| `table_index` | 是 | 目标表序号（1 起） |
| `data_start_row` | 是 | 数据起始行（1 起）。**不会**自动寻找"第一条像课程的行" |
| `columns` | 是 | 逻辑字段 → 物理列号，**绝不推断** |
| `row_filter` | 否 | 数据行**必须全部满足**的声明式 selector（见下方判定顺序） |
| `row_kind` | 声明 `row_filter` 时必填 | **行身份判别器**：`{column, condition}`，且该列必须同时是 `row_filter` 中的 selector |
| `exclude` | 否 | 命中任一即丢弃该行的声明式条件（先于行身份判定） |
| `column_count` | 否 | 声明的表宽守卫（缺省取最大映射列号） |
| `identity` | 否 | 结构锚点：`{column, values}`，列必须已在 `columns` 中声明 |
| `course_name_lines` | 否 | 名称单元格为双语"中文\nEnglish"时，保留前 N 行（0=保留全部） |
| `last_data_row` / `requirement` / `course_type` / `group_id` / `requirement_values` | 否 | 与 header 模式同义 |

`header` 模式的 profile **不允许**出现 `data_start_row` / `row_filter` / `exclude` / `column_count` / `identity` / `course_name_lines`；`positional` 模式**不允许**出现 `header_row` / `expected_headers`。因此 `expected_headers: ""` 之类的写法不能被当作 positional 的旁路。

**结构性守卫（drift 防护）**：

- **行宽**：数据行的物理列必须覆盖全部映射列，否则失败（绝不静默返回空）。
- **表宽**：数据行的物理列不得超过 `column_count`，否则失败——学校改版把整块列右移时必须报错而不是错列读取。
- **身份锚点**：`identity` 声明某一（已映射）列必须出现指定值之一（取自首个数据行）。列被整体移动后锚点失配，导入失败。
- **横向合并**：若某数据行存在 `gridSpan > 1` 的合并单元格且覆盖任一映射列，该行位置语义不唯一，导入失败。（纵向合并只是把分区标签下延，不影响位置，允许。）
- **行选择（fail closed，不得成为绕过结构校验的旁路）**：先由 `row_kind` 判别器决定"这一行是不是课程行"，再判结构：

  ```text
  判别器命中，且全部 selector 命中                    → 课程行 → 进入完整 structural guard
  判别器命中，但任一 selector 无值或 selector 不命中   → 疑似课程行但结构损坏 → fail closed
  判别器不命中，但其余 identifying selectors 全部命中  → 判别器本身损坏（course_id 有值且
                                                       credit 为数字）→ fail closed
  判别器不命中，其余 selectors 未全部命中              → 真实分区/模块/小计行 → skip
  ```

  即：只要 `course_id` 有值且 `credit` 为数字，这一行就按课程行处理；判别器读不到值（单元格缺失**或**为空）只说明判别器损坏，必须阻断而不能 skip。单元格"存在但为空"与"物理缺失"在 positional 模式下语义相同。真实 section 行形如 `判别器 False / course_id True / credit False`，仍然安全跳过。

  `row_kind` 只支持 `numeric` 判别（真实课程行必有数字序号，分区标签行没有）。selector 只能读取**标识性列**（`course_id` / `credit` / `recommended_term_text` / `sequence`）；若某个 selector 映射到 `requirement` 这类可选列，会因为可能整表无行命中而被直接拒绝。真实 Case A 的 selector 为 **`sequence` numeric + `course_id` nonempty + `credit` numeric**。

- **行选择**：`row_filter` / `exclude` 只使用声明式条件（`nonempty` / `numeric` / `equals` + 显式取值），没有任何内容猜测。分区标题、模块行、小计行由这些规则显式排除。

没有任何自动回退：未知 `.docx`、无 profile、或 header 模式读无表头文档，一律 reject；不存在 `try header except positional`。

```json
{
  "mode": "positional",
  "table_index": 2,
  "data_start_row": 3,
  "column_count": 9,
  "columns": {"sequence": 3, "course_id": 4, "course_name": 5, "credit": 6, "recommended_term_text": 9},
  "course_name_lines": 1,
  "row_kind": {"column": 3, "condition": "numeric"},
  "row_filter": [{"column": 3, "condition": "numeric"}, {"column": 4, "condition": "nonempty"}, {"column": 6, "condition": "numeric"}],
  "exclude": [{"column": 5, "condition": "equals", "values": ["小计", "合计"]}],
  "identity": {"column": 4, "values": ["FL101"]},
  "requirement": "required",
  "course_type": "公必"
}
```

真实 Case A 两份方案的声明式 profile 见 `backend/app/curriculum/plan_profiles.py`（只含表序号、列位置、锚点课程号与结构守卫，**不含**任何真实文件、路径、姓名、学号或成绩）。真实 `.docx` 本身仍留在受控本地目录，不入库。

```bash
python -m app.curriculum --docx /private/plan.docx --profile /private/profile.json
```

命令只显示行数及问题数量。程序入口：

```python
draft = load_curriculum_docx(path, source_id=source_id, tables=tables)
version = draft.to_version(version_id=version_id, major=major, cohort=cohort)
```

`draft.rows` 保存原始字段及 `table:1!row:2` 定位。缺课程号、非数值学分、合并单元格、嵌套表、未处理修订、隐藏内容和兼容分支等问题会阻止转换，问题行不会静默丢弃。隐藏样式采用保守检查，不实现完整 Word 渲染。推荐学期保留原文，不转成整数。读取文件不代表培养方案范围、课程号或学校认定规则已获核验。

## Word 与 D4 组合

通过 `load_curriculum_case(path)` 组合本地文件。文件引用的相对路径以 case 所在目录为准，不从网络下载。

`old` 或 `new` 用 `docx` 替代 `course_records`，其余版本元信息仍显式提供：

```json
{
  "version_id": "mock-new",
  "major": "示例专业",
  "cohort": "示例年级",
  "source_id": "mock://example/new",
  "docx": {"path": "new.docx", "tables": []}
}
```

`tables` 应填写上节映射。已修部分用 `xlsx` 替代 `records`：

```json
{
  "source_id": "mock://example/completed",
  "xlsx": {"path": "d4.xlsx", "sheet_name": "已修课程_脱敏"},
  "complete": false
}
```

内存函数 `normalize_curriculum_case` 不读取文件。任何文件导入失败都会停止整个 case，不回退到 Demo，也不输出部分任务。

### 真实培养方案的课程组声明（`plan_group_records`）

无标签培养方案的 profile 除了选表与列位置，还可以声明**结构性的课程组事实**。真实 Case A 目标方案（网络空间安全）已确认：

- table 6 `（专业选修课）` 共 37 门 / 课程学分合计 86，方案给出的**主修应修专选 = 23**（table 7 合计行，并被 table 1、table 10 独立重复）。
- 因此建模为**一个统一池**：`group_id = CSE-ELECTIVE-POOL`、`minimum_credit = 23`；table 6 的 37 门课全部 `requirement = elective` 且带该 `group_id`。
- table 6 内部六个 banner 分区（人工智能与内容安全 / 本研贯通课 / 网络与通信安全 / 软硬件系统及安全 / 安全基础模块 / 密码与攻防对抗）是**展示分区**，**不**各自生成 `CurriculumGroup`，23 **不**按模块拆分。
- table 8 `（荣誉课程）`（table 9 合计应修 **0** 学分）**不属于普通主修毕业要求**，因此**不进入**目标方案的普通 requirement 导入；也**不**为它创建 `minimum_credit = 0` 的假组。荣誉课程暂留在当前模型之外。

声明式表达见 `backend/app/curriculum/plan_profiles.py` 的 `plan_group_records(role)`；调用方把结果传给 `DocxImportResult.to_version(group_records=...)` 即可构造 `CurriculumGroup`。`source_record` 指向可追溯来源（如 `table:7!row:2`）。

> ⚠️ 课程组的数量与额度**只能来自原文事实**：`course_type`（展示分区名）**不等于** `group_id`，课程学分合计**不等于** `minimum_credit`。
## 课程组与人工选修确认

仅支持现有平面课程组及最低学分。组成员、最低学分和所选课程均须来自明确输入，不支持跨组抵扣、门数、互斥或复杂组合规则。已有必修任务可表达组内未来要求，无需为了必修课程额外提供选修选择。

case 可增加：

```json
{
  "elective_selections": [{
    "target_version_id": "mock-new",
    "group_id": "DEMO-GROUP",
    "course_ids": ["DEMO-E1", "DEMO-E2"],
    "evidence": "mock://example/confirmed-choice"
  }]
}
```

选择绑定目标版本和已存在的同组课程。已满足学分、已有必修任务及明确所选选修课程能覆盖组要求时，允许用实际课程任务表达剩余计划。计划容量不会增加已取得学分，也不会确认课程等价。身份、认定或先修未知时仍输出待确认。若必修任务不足以覆盖剩余额度，必须明确选择剩余选修课程。组已满足时不再把未修选修逐门列为必补。

内部 `get_curriculum_diff()` 保留实际组缺口，`get_academic_analysis()` 保留有来源的风险及依赖。内部顺序不进入公共任务，也不能证明跨学期排课可行。

## 补修判定时点（makeup scope）

目标培养方案会包含转专业之后各学年的正常课程。若不给出判定时点，这些未来课程在“尚未修读”时会与真正的历史缺口混在一起。因此 case 可以显式给出判定时点：

```json
{
  "makeup_scope": {
    "target_version_id": "mock-scope-new",
    "as_of_term": "2025-2",
    "evidence": "mock://example/as-of-basis"
  }
}
```

- `as_of_term` 只回答一个问题：**历史补修缺口判定到哪个学期为止**。它必须由输入显式给出并附 `evidence`，**不依据系统当前日期**，也不从 `deadline_semester`、先修或其他字段推断。`evidence` 会写入相关任务的 `source_evidence`，保持可追溯。
- 判定规则：课程的建议安排学期**早于或等于** `as_of_term`（含当期）→ 属历史范围，继续按原有匹配逻辑判为 `satisfied` / `required` / `possibly_equivalent` / `manual_confirmation`；**晚于** `as_of_term` → 属未来正常培养计划，**不进入当前 `MakeupTask[]`**（必修与选修同样处理）。
- 学期比较只接受已确认的 `YYYY-1` / `YYYY-2` 形式（严格匹配，不裁剪空白）。其余一律**不猜**：
  - 区间（如 `2025-1~2025-2`、`2025-1~2028-2`）、`未知`、`空`、空白、异常格式 → 该课程标为 **unresolved**；
  - 只要存在 unresolved 条目，**整个投影被阻断**，需要人工给出明确的学期范围决定，而不是猜成历史或未来；
  - `as_of_term` 本身不可解释时同样阻断。
- **未提供 `makeup_scope` 时保持原有 generic curriculum-diff 行为**（不启用时点过滤，也不读取系统日期）；此时 `recommended_term_text` 仍然只是展示用的建议学期。
- `recommended_term_text` 的语义**未被扩展**：它不是先修关系、不是 deadline、不是学校认定规则，也不是转专业补修政策。本机制只把它用于与显式 `as_of_term` 比较。
- 若没有正式学校依据确认 Case A 的执行时点，只能使用人工 Mock 依据或负责人明确确认的 evidence，并在其中写明这不是学校官方政策。
- `MakeupScope` 是 Curriculum 内部对象：它不进入公共 Schema、`MakeupTask`、Provider 签名、Integration 或 Planner。示例见 `mock_data/curriculum_demo/scoped_case.json`。

### 逐条人工范围确认（`confirmed_scope_decisions`）

真实培养方案里会有解析器无法安全解释的学期写法（`2025-1~2025-2`、`2025-1~2028-2`、`未知`、`空`、缺失、异常格式）。这类条目标为 unresolved 并阻断投影是正确行为，但真实 case 必须有一条合法出口。因此 case 可以提供逐条人工确认：

```json
{
  "confirmed_scope_decisions": [
    {
      "target_version_id": "mock-scope-new",
      "target_source_record": "row:DEMO-410",
      "target_course_id": "DEMO410",
      "decision": "historical",
      "evidence": "mock://example/human-range-confirmation"
    }
  ]
}
```

- **主键是 `target_source_record`**（目标培养方案中的**具体 requirement entry**），不是 `course_id` —— 同一课程号可能在不同分组 / 荣誉课 / 重复条目中出现，范围决策必须针对具体条目。`target_course_id` 仅用于核对与诊断。
- **scope 查询按条目进行**：内部的 bucket / evidence 查询都以 requirement entry 的 `source_record` 为键（`scope_bucket_for_entry` / `scope_evidence_for_entry`），**不提供按 `course_id` 的查询入口**。同一 course_id 的两条 entry 可以分别是 historical 与 future，互不串线；针对一条 entry 的人工确认**不会**一并解除同一 course_id 的另一条 entry。
- `decision` 只允许 `historical` 或 `future`。`evidence` 必须非空，并会写入相关任务的 `source_evidence`（只放可追溯的 source reference，不含本地真实文件路径、姓名、学号、成绩或 GPA）。
- **只能解除 parser 无法确认的 unresolved**：若某条目本来就有明确单学期（如 `2026-1`）并已由 `as_of_term` 自动得到 historical / future，那么针对它的 decision 属于与来源事实冲突，**直接报错，不静默覆盖**。
- 校验：版本必须匹配；`source_record` 必须真实存在且与 `target_course_id` 一致；**重复 decision 拒绝**；额外字段拒绝；Real case 不得使用 `mock://` evidence（Mock case 允许）。
- 未提供 `makeup_scope` 时，不允许出现 `confirmed_scope_decisions`。

### 课程组的范围切分（`confirmed_group_scope_decisions`）

课程组的最低学分是**组级总量**，来源通常不会说明“截至转专业时点应完成组内多少学分”。因此：

- 组内成员**全部**安排在历史范围之后 → 该组不构成历史要求，**不阻断**当前 historical projection。
- 组内成员**全部**在历史范围内 → 仍按原有严格组规则处理（额度未知、缺口未满足、计划不足等继续阻断）。
- 组内**同时**有历史与未来成员（mixed）→ 这是一个**不能被推导**的切分：
  - ⛔ 不按课程数量比例拆；
  - ⛔ 不按推荐学期比例拆；
  - ⛔ 不按已得学分自动推导；
  - ⛔ 不假设最低学分全部属于历史或全部属于未来。
  - 默认 `historical_minimum_credit` 未知 → **阻断投影**，需要人工明确切分。

若来源确实给出了历史切分，可显式提供：

```json
{
  "confirmed_group_scope_decisions": [
    {
      "target_version_id": "mock-scope-new",
      "group_id": "SCOPE-GROUP",
      "historical_minimum_credit": 6,
      "evidence": "mock://example/group-historical-share"
    }
  ]
}
```

`historical_minimum_credit` 只表示**历史部分**的额度，不是学校政策。它必须：不超过组最低学分、能被组内历史成员的实际学分总量满足、且只用于 mixed 组（对纯历史组或纯未来组会被拒绝）。未来选修选择不会被计入历史组额度。

**历史额度只由历史事实覆盖**：mixed 组的历史额度**只能**由 bucket 为 `historical` 的组成员覆盖。**future 成员一律不参与历史覆盖**，无论它处于 satisfied、required、selected、manual_confirmation 还是 possibly_equivalent —— 计划安排在该时点之后的课程，无论状态如何，都不构成"历史额度已满足"的证据。

**组决策 evidence 的传播范围**：`confirmed_group_scope_decisions[].evidence` 只会附加到**该组内、且本身属于历史范围的已输出任务**上（按 `target.group_id` + entry bucket 双重匹配）。它不会进入同一组的 future 任务、其他组、其他课程，或没有 `group_id` 的课程。

**组缺口的 reason 区分两种情形**：
- mixed 组**没有** split decision（`historical_minimum_credit` 未知）→ 表示"历史学分要求无法从来源分割，需人工确认"；
- mixed 组**已有** split decision 但历史学分仍有缺口 → 表示"历史额度已经确认，但仍存在未满足学分"（不再声称无法分割）。

### 语义边界（不得混用）

```text
MakeupScope
  ≠ 学校转专业政策
  = case 显式给出的历史缺口判定时点（含其 evidence）

recommended_term_text
  ≠ deadline
  ≠ prerequisite
  ≠ official makeup rule
  = 培养方案的建议安排学期，仅用于与 as_of_term 比较

ConfirmedScopeDecision
  = 对无法安全解析的目标 requirement entry 的显式人工范围确认
  ≠ 可覆盖明确单学期事实的开关
```

> ⚠️ **明确单学期事实原则上不能被人工 scope decision 静默覆盖。**
> 若条目本身有可自动解析的单学期，以其与 `as_of_term` 的比较结果为准；针对它的 decision 会被判为冲突并报错，而不是默默改写来源事实。



