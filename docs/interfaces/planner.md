# Planner 模块接口

## 职责

回答：**哪些课先补，以及怎么在现实约束下排进去？**

本模块负责：
- 课程依赖图；
- 补修优先级与风险；
- 时间/周次冲突；
- 教学班替换；
- Path Repair；
- 跨学期补修路径的 MVP 规划。

## 对外输入

来自 Curriculum：
- `MakeupTask[]`

来自 Course Data：
- `CourseOffering[]`

来自用户：
- 当前课表；
- `Preference`

## 对外输出

必须符合：
- `schemas/plan_result.schema.json`

建议接口：

```text
build_dependency_graph(courses)
calculate_priority(makeup_tasks, context)
check_conflict(offering_a, offering_b)
find_alternative_sections(course_id, offerings, current_schedule)
optimize_path(makeup_tasks, offerings, current_schedule, preferences) -> PlanResult
```

## 实现约束

- 时间冲突、学分计算、先修关系等确定性逻辑不得交给 LLM 判断；
- 优化器第一版建议使用 Google OR-Tools CP-SAT；
- 图关系第一版建议使用 NetworkX；
- 无解时必须返回明确的 `infeasible` 或 `partially_feasible`，不得伪造可行方案。

## 人工确认边界

以下内容需人工确认后才能作为规则写死：
- 补修优先级权重；
- 跨校区最小通勤时间；
- 硬约束/软约束定义；
- 特殊培养政策。
