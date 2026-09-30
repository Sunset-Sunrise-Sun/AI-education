# Mock 数据说明

> **本目录下的全部数据均为人工虚构的演示数据（Mock），不是任何学校的真实教务数据。**

## 为什么在这里

`/AGENTS.md` 第 6 节规定：允许使用 Mock 数据支持并行开发，统一放在 `/mock_data/`，
必须符合公共 Schema、明确标记为 Mock、不得冒充真实学校数据。

真实课程开设数据需要等用户完成教务页面技术侦察、并在本人正常登录且有权限的范围内获取后，
才由 Course Data 模块接入。本目录不参与真实数据流程。

## 文件清单

| 文件 | 对应公共 Schema | 消费方 |
|---|---|---|
| `makeup_tasks.json` | `schemas/makeup_task.schema.json` | Curriculum 模块输出 → Planner 输入 |
| `course_offerings.json` | `schemas/course_offering.schema.json` | Course Data 模块输出 → Planner 输入 |
| `preference.json` | `schemas/preference.schema.json` | Agent 解析用户偏好 → Planner 输入 |
| `plan_result.json` | `schemas/plan_result.schema.json` | Planner 输出 → Agent / Frontend 展示 |

## 校验方式

全部 Mock 数据同时通过两层校验，二者都有自动测试覆盖：

1. **公共 JSON Schema**（真源）——用 `jsonschema` 直接按 `/schemas/*.schema.json` 校验；
2. **后端 Pydantic 模型**——用 `backend/app/models/contracts.py` 校验。

```bash
cd backend
python -m pytest tests/test_mock_data_schema.py -v
```

## 课程代码与名称的约定

课程号、教学班号、教师姓名、课程名称**都是虚构的**，仅为让 Demo 可读。
为了让展示效果贴近真实形态，课程代码采用了与高校常见格式相似的写法（如 `62001001`），
**但这不代表任何真实课程**。请勿把这些代码与真实教务系统中的代码对应。

## 数据来源标记

`CourseOffering` 的 Schema 中定义了 `data_source` 字段，本目录全部教学班均为 `"mock"`。

其余三个对象（MakeupTask / Preference / PlanResult）的公共 Schema 中**没有** `data_source`
字段，且 schema 声明了 `additionalProperties: false`。因此本项目**不在这三个对象上私自增加
来源字段**（那会构成未获批准的公共接口变更），改为在 API 响应头 `X-Data-Source: mock`
和文档中明确标记。详见 `backend/README.md` 的「Mock / Real 边界」一节。

## 当前缺口（有意保留）

- 没有 `courses.json`。Phase 1 只要求 `CourseOffering`（教学班）级 Mock，
  `Course` 对象由 Curriculum 模块在真实培养方案接入后产出，本次不预造。
- `plan_result.json` 只描述「一门课的补修顺序」，不包含真实学分认定结论。
  所有涉及课程正式等价的部分都标记为 `manual_confirmation`，等待人工确认。
