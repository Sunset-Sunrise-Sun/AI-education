# Curriculum

支持 D4 本地读取、结构化培养方案、课程匹配和结果适配。待确认课程号保留为空，重修记录逐条保留。

从 `backend/` 运行：

```bash
python -m app.curriculum /private/path/d4.xlsx --source-id SOURCE-ID
python -m pytest tests/test_curriculum_*.py
```

命令只显示数量，不导出逐行数据。输入文件放在仓库外。

内部入口：`normalize_curriculum_version`、`build_curriculum_diff`、`project_courses`、`CurriculumResultProvider`。

认定和缺课确认需要明确依据。修改结果后需重新计算；未解决的选修组要求或先修信息会阻止规划。

D2/D3 逐课程数据接入和真实匹配尚未验证。公共 Schema 和 API 未变。
