# Curriculum

当前支持 D4 脱敏已修课程表的本地读取和规范化。待确认课程号保留为空，重修记录逐条保留。

从 `backend/` 运行：

```bash
python -m app.curriculum /private/path/d4.xlsx --source-id SOURCE-ID
python -m pytest tests/test_curriculum_completed_courses.py tests/test_curriculum_xlsx_reader.py tests/test_curriculum_cli.py
```

命令只显示数量，不导出逐行数据。输入文件放在仓库外。

培养方案解析、课程匹配和补修任务生成尚未实现。公共 Schema 和 API 未变。
