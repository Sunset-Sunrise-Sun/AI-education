# Curriculum 模块接口

> Data Gate-2（**DG-06**）同步修正本文件，使其与 `/AGENTS.md` 第 5 节的模块边界一致：
> **课程依赖认定、补修风险与学业优先级的所有权在本模块**，Planner 只是消费方。

## 职责

回答：**学生转专业后缺什么、先补什么、大概怎么排？**

本模块负责：

- 解析原专业培养方案；
- 解析新专业培养方案；
- 解析已修课程 / 成绩记录；
- 做 Curriculum Diff（新旧培养方案差异分析）；
- 给出课程匹配建议；
- 生成补修任务（`MakeupTask[]`）；
- **课程依赖认定**（先修 / 前置关系的**权威来源**）—— 产出 `MakeupTask.prerequisites[]`；
- **补修风险与学业优先级**（**所有权在本模块**）；
- **跨学期补修路径建议**。

本模块**不负责**：

- 真实教学班抓取（属 Course Data）；
- 课表约束求解与 Path Repair（属 Planner）。

## 对外输入

- 原专业培养方案文件或结构化数据；
- 新专业培养方案文件或结构化数据；
- 已修课程记录。

## 对外输出

核心输出必须符合：

- `schemas/course.schema.json`
- `schemas/makeup_task.schema.json`

建议接口：

```text
parse_curriculum(input) -> Course[]
compare_curriculum(old, new, completed) -> MakeupTask[]
match_courses(completed, target_courses) -> MatchResult[]
```

### ⚠️ 关于优先级：当前**没有**公共契约

- `/schemas/` 下**没有** `priority` 字段，也**没有** `PriorityResult` 或任何等效对象
  （Data Gate-1 / **DG-05** 裁决：MVP 不新增）；
- 因此**不得假装当前已经可以跨模块传 priority** ——
  在出现正式公共契约之前，优先级**只存在于本模块内部**；
- `Course.course_type` / `Course.recommended_semester` 是**现有兼容字段**，
  **不得**被解释为课程的全局固有属性（培养方案内部的上下文由本模块自行承载，
  见 Data Gate-1 / DG-04）。

## 人工确认边界

以下结果不得自动作为正式结论：

- 模糊课程等价关系；
- 课程替代审批；
- 学院特殊政策；
- 培养方案歧义条款。

这类结果必须标记 `manual_confirmation` 或 `possibly_equivalent`。

## 给 Planner 的交付

- Planner 依赖结构化的 `MakeupTask[]`（含 `prerequisites[]`），
  不依赖本模块内部的解析方式与内部结构；
- **先修边的权威来源是本模块**：`MakeupTask.prerequisites[]` 中给出的边由 Curriculum 认定；
  Planner 只能把**已经收到的**边转换成本地 adjacency / topology 供确定性求解使用，
  ⛔ **不得新增、猜测、重写任何 prerequisite edge**（`/AGENTS.md` 第 5 节、Data Gate-1 / DG-05）；
- 真实来源**无法提供** prerequisite 时，标记 **未知 / 待人工确认**，**不得自动补齐**；
- 学业优先级同样由本模块负责，但**当前没有公共字段承载**（MVP 不新增 `priority`），
  **Planner 不得自行生成优先级**；
- ⚠️ **先修关系的真实来源目前尚无证据**：两份真实培养方案样本中
  **未发现明确的先修 / 前置课程字段或条款**，
  因此 `prerequisites[]` **能否被真实数据填充目前无法确认**
  （这**不构成**"学校没有先修制度"的结论，只说明本样本未覆盖）。
