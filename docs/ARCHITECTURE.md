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
OR-Tools CP-SAT 等确定性约束求解、Path Repair、无解 / 部分可行处理与 PlanResult 生成。
输出“在现实约束下怎么排进去”。

Planner 消费 Curriculum 提供的补修任务、课程依赖结果与已确认优先级，
**不得为求解方便自行重写课程认定或学业优先级规则**。

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

> 图中 Curriculum 的输出简写为 `MakeupTask[]`。按 `/AGENTS.md` 第 5 节，
> Planner 实际消费的是补修任务**加上** Curriculum 给出的课程依赖结果与已确认优先级，
> 而不是只有补修任务清单。

## 4. 公共契约

跨模块只通过 `schemas/` 和 `docs/interfaces/` 中的定义交互。

模块不得依赖其他模块内部实现。

## 5. 当前建议技术

- Python / FastAPI / Pydantic
- NetworkX
- Google OR-Tools CP-SAT
- PostgreSQL
- JavaScript/TypeScript
- Chrome Extension Manifest V3
- Vue 3 + TypeScript + Vite（前端技术栈已由负责人确认）
- LLM Structured Output / Tool Calling

任何核心技术替换需人工确认并记录。
