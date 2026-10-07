# 系统架构

## 1. MVP 范围

“学航·转衔”当前只聚焦：

> 转专业学生从培养方案变化到可执行补修路径的完整衔接。

暂不把通用四年选课、延毕概率预测、自动提交选课等纳入 MVP。

## 2. 四个核心模块

> 模块边界以 `/AGENTS.md` 第 5 节为准；本节只是简化说明，不得据此扩大任何模块的职责。

### Curriculum / 学业路径
负责培养方案解析、已修课程结构化、新旧培养方案差异分析、课程匹配与 MakeupTask 生成，
以及课程依赖图、补修风险与优先级、跨学期补修路径建议。输出“缺什么、先补什么”。

不负责：真实教学班抓取、课表约束求解、Path Repair。

### Planner / Path Repair
负责时间 / 节次 / 周次冲突检测、当前课表冲突分析、替代教学班搜索、硬约束 / 软约束建模、
确定性约束求解、Path Repair、无解 / 部分可行处理与 PlanResult 生成。
输出“在现实约束下怎么排进去”。

> ⚠️ **当前实际实现（不得夸大）**：Planner 是**受限确定性规划** ——
> 先修拓扑序 + 截止学期硬约束 + 建议学期偏好 + 每学期学分预算的**启发式**。
> ⛔ **不是** OR-Tools CP-SAT / ILP 全局最优求解，⛔ 没有评分权重，⛔ 不自动换班，
> ⛔ 不在生成建议时自动应用（换班必须由用户**显式确认**后才生效）。

Planner 消费 Curriculum 提供的补修任务，**不得为求解方便自行重写课程认定或学业优先级规则**。

> ⚠️ **按 Data Gate DG-05 修正**（2026-09-30）：
> **MVP 当前跨模块只传 `MakeupTask[]`**，prerequisite 信息由
> **`MakeupTask.prerequisites[]`** 承载（Planner 可把它转换成本地 adjacency / topology
> 供确定性求解使用，但**不得新增 / 猜测 / 重写**先修边）。
> **`priority` 当前没有公共契约** —— 在正式接口变更之前，
> **不得声称 Integration / Planner 已经消费跨模块 priority**。

### Course Data
负责真实开课数据的获取和标准化，输出“现实里有什么课”。

### Agent / Frontend
负责用户交互、工具调用和解释展示。

## 3. 核心数据流

```text
原专业培养方案 ─┐
新专业培养方案 ─┼─> Curriculum ──> MakeupTask[] ──┐
已修课程       ─┘                                │
                                                  v
真实教务课程 ─────> Course Data ─> CourseOffering[] ─> Planner ─> PlanResult
                                                               │
用户偏好 ─────────────> Preference ─────────────────────────────┘
                                                               │
                                                               v
                                                       Agent / Frontend
```

> 图中 Curriculum 的输出简写为 `MakeupTask[]`。按 **Data Gate DG-05**，
> **MVP 当前跨模块只传 `MakeupTask[]`**：prerequisite 信息由 `MakeupTask.prerequisites[]` 承载，
> **`priority` 当前没有公共契约**。
> 因此上图就是当前**真实**的跨模块数据流，不再另加"依赖结果 / 优先级"对象。
>
> 模块之间的调用顺序与 Provider 边界见 `docs/interfaces/integration.md`
> （Integration 只做编排，不做业务算法）。

## 4. 公共契约

跨模块只通过 `schemas/` 和 `docs/interfaces/` 中的定义交互。

模块不得依赖其他模块内部实现。

## 5. 当前建议技术

> ⚠️ **本节是"建议 / 候选"清单，不是"已上线"清单。**
> 某一项出现在这里**不表示**它已经在代码里使用；
> 判断实际实现状态请看 `docs/status/<module>.md`。

- Python / FastAPI / Pydantic（**已使用**）
- JavaScript/TypeScript（**已使用**）
- Vue 3 + TypeScript + Vite（**已使用**；前端技术栈已由负责人确认）
- NetworkX（**候选；当前未使用**）
- Google OR-Tools CP-SAT（**候选；当前未使用** ——
  当前 Planner 是**确定性启发式**：先修拓扑序 + 截止学期硬约束 + 建议学期偏好 + 每学期学分预算，
  ⛔ 不是 CP-SAT / ILP 全局最优求解）
- PostgreSQL（**候选；当前未使用** —— 本地 Course Data 使用 SQLite）
- Chrome Extension Manifest V3（**候选；当前未使用** ——
  当前采集是**浏览器内显式授权调用**，不是扩展）
- LLM Structured Output / Tool Calling（**候选；当前未接入** ——
  Case A 的编排是**固定工具编排**，AI 增强待接入）

任何核心技术替换需人工确认并记录。
