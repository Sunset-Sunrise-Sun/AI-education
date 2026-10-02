# Curriculum

支持结构化培养方案、Word 表格、D4 读取和可调用 Provider。待确认课程号保留为空，重修记录逐条保留。

从 `backend/` 运行：

```bash
python -m app.curriculum --demo
python -m app.curriculum --case /private/path/case.json
python -m app.curriculum --inspect-case /private/path/case.json
python -m app.curriculum --docx /private/path/plan.docx --profile /private/path/profile.json
python -m app.curriculum /private/path/d4.xlsx --source-id SOURCE-ID
python -m pytest tests/test_curriculum_*.py
```

`--demo` 计算人工样例并输出任务；私有输入模式只显示统计。真实输入放在仓库外。`--inspect-case` 可检查尚不能输出任务的 case。

程序入口：`CurriculumCaseProvider(load_curriculum_case(path)).get_makeup_tasks()`。输入结构见 `mock_data/curriculum_demo/case.json`。

匹配规则按 case 绑定来源。模糊等价、学分差异和未知先修保留待确认。平面组可由已有必修任务和有依据的选修选择表达，实际学分缺口仍保留。剩余选修没有选择或额度不足时明确报错。

Word 按明确的表格和列映射读取，问题行保留在内部草稿。输入格式和组合文件用法见 [INPUTS.md](INPUTS.md)。学业分析只留在模块内部，不改公共任务排序。真实 D2/D3 和学校规则尚未验收，公共契约未变。

技术审查和联调范围见 [REVIEW.md](REVIEW.md)。
