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



