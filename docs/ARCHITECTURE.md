# 系统架构

## 1. MVP 范围

“学航·转衔”当前只聚焦：

> 转专业学生从培养方案变化到可执行补修路径的完整衔接。

暂不把通用四年选课、延毕概率预测、自动提交选课等纳入 MVP。

## 2. 四个核心模块

### Curriculum
负责理解培养方案和已修课程，输出“缺什么”。

### Planner
负责依赖、优先级、冲突与 Path Repair，输出“怎么补”。

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
