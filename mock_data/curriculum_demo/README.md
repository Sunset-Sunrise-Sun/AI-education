# Curriculum 人工案例

`case.json` 是结构化输入，`makeup_tasks.json` 是运行结果。

`elective_case.json` 演示已确认的选修计划，`elective_makeup_tasks.json` 是对应任务。已满足 2 学分、还需 2 学分时，只列出明确选中的剩余课程，实际缺口仍保留。

所有课程、专业、规则和记录均为人工构造，不是学校政策或真实学生材料。

从 `backend/` 运行 `python -m app.curriculum --demo` 可重新计算。修改输入后，结果会重新生成。

运行 `python -m app.curriculum --inspect-case ../mock_data/curriculum_demo/elective_case.json` 可检查选修案例统计。程序调用用 `CurriculumCaseProvider(load_curriculum_case(path))`。
