# Curriculum

支持结构化培养方案、D4 读取、课程匹配和可调用 Provider。待确认课程号保留为空，重修记录逐条保留。

从 `backend/` 运行：

```bash
python -m app.curriculum --demo
python -m app.curriculum --case /private/path/case.json
python -m app.curriculum /private/path/d4.xlsx --source-id SOURCE-ID
python -m pytest tests/test_curriculum_*.py
```

`--demo` 计算人工样例并输出任务；私有输入模式只显示统计。真实输入放在仓库外。

程序入口：`CurriculumCaseProvider(load_curriculum_case(path)).get_makeup_tasks()`。输入结构见 `mock_data/curriculum_demo/case.json`。

匹配规则按 case 绑定来源。明确匹配可自动判断，模糊等价和学分差异保留待确认；未知先修输出待确认任务。无法表达的选修组缺口仍明确报错。

学业问题和显式策略下的顺序只留在模块内部，不改公共任务排序。真实 D2/D3 和学校规则尚未验收，公共契约未变。
