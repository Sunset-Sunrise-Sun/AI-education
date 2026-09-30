# Agent / Frontend 模块接口

## 职责

回答：**如何让用户完成任务并理解结果？**

本模块负责：
- 用户输入和文件上传；
- 用户自然语言需求解析；
- 调用 Curriculum / Course Data / Planner；
- 展示培养方案 Diff；
- 展示补修清单和依赖图；
- 展示冲突和 Path Repair 前后变化；
- 解释 PlanResult；
- 输出最终学业衔接方案。

## Agent 工具边界

Agent 只负责：
- 理解用户意图；
- 把自然语言偏好转换为 `Preference`；
- 调用后端工具；
- 将确定性结果解释成人话。

Agent 不得自行：
- 计算学分；
- 判定时间冲突；
- 决定课程正式等价；
- 修改 Planner 的求解结果；
- 编造真实开课信息。

## 主要依赖

读取：
- `MakeupTask[]`
- `CourseOffering[]`
- `PlanResult`

## 失败处理

任一工具失败时必须明确告诉用户当前失败模块，不得用 LLM 自行补出“看起来合理”的结果。
