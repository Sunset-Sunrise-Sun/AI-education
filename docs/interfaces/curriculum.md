# Curriculum 模块接口

## 职责

回答：**学生转专业后缺什么？**

本模块负责：
- 解析原专业培养方案；
- 解析新专业培养方案；
- 解析已修课程/成绩记录；
- 做 Curriculum Diff；
- 给出课程匹配建议；
- 生成补修任务。

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

## 人工确认边界

以下结果不得自动作为正式结论：
- 模糊课程等价关系；
- 课程替代审批；
- 学院特殊政策；
- 培养方案歧义条款。

这类结果必须标记 `manual_confirmation` 或 `possibly_equivalent`。

## 给 Planner 的交付

Planner 只依赖结构化的 `MakeupTask[]` 和课程依赖信息，不依赖本模块内部解析方式。
