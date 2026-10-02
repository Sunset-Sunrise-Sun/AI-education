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

## 人工选修确认

仅支持现有平面课程组及最低学分。组成员、最低学分和所选课程均须来自明确输入，不支持跨组抵扣、门数、互斥或复杂组合规则。

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

选择绑定目标版本和已存在的同组课程。只有已满足学分加明确所选课程能覆盖组要求时，才允许用真实课程任务表达剩余计划。选择不会增加已取得学分，也不会确认课程等价。所选课程的身份、认定或先修未知时仍输出待确认。组已满足时不再把未修选修逐门列为必补。

内部 `get_curriculum_diff()` 保留实际组缺口，`get_academic_analysis()` 保留有来源的风险及依赖。内部顺序不进入公共任务，也不能证明跨学期排课可行。
