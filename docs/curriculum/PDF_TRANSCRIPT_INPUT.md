# 成绩单 PDF 输入（Case A 主路径）

> 状态：**已实现并通过测试**（后端 + 窄接口）。⛔ 未改公共 Schema、⛔ 未改 Provider 签名、
> ⛔ 未改既有匹配规则。

## 一句话

**支持当前已验证的中山大学本科成绩单 PDF 版面**，把它变成 Curriculum 既有的已修课程输入，
再由既有匹配 / 投影逻辑产出 `MakeupTask[]`。

⚠️ ⛔ **不要**把这句话读成"支持所有大学成绩单"或"支持中大成绩单所有版本"。
本模块只覆盖**已核验的那一种版面**，版面不符即 fail closed。

## 数据流

```text
成绩单 PDF
  ↓ backend/app/curriculum/pdf_reader.py      版面校验 + 字段抽取
term / course_name / credits / grade / course_attribute
  ↓ normalize_completed_courses()             既有内部模型，⛔ 不新增对象
CompletedCourse[]（course_id = None + pending）
  ↓ backend/app/curriculum/case.py            `completed.pdf` 键（与 records / xlsx 三选一）
build_curriculum_diff() → project_makeup_tasks()   ← 既有逻辑，⛔ 没有第二套匹配
MakeupTask[]
```

## 支持的版面（已核验）

| 维度 | 已支持 |
| --- | --- |
| 标题 | `中山大学本科生成绩单` |
| 学生信息区块 | 姓名 / 学号 / 学院 / 专业 / 年级 / 入校时间 / 学制 —— **解析时整体丢弃** |
| 表头 | 四列一组：`课程名称` / `学分` / `成绩` / `课程属性`（`课程` 与 `属性` 分两行打印） |
| 列组数量 | 横向重复平铺（已核验样本为 4 组） |
| 学期行 | `2025-2026学年 第一学期`（`学年` + `第X学期`） |
| 成绩 | 0–100 数字、`P`、`NP` |
| 学分 | 整数或一位小数（如 `1.5`） |
| 课程名 | 含换行课程名（`……探索与` / 数据行 / `发现`） |
| 多学期 | 支持；学期随每条记录一起保留 |
| 多页 | 支持（每页都要求出现同样的表头） |

### 明确不支持的

- ⛔ 扫描件 / 图片型 PDF（**没有 OCR**）；
- ⛔ 其它学校、其它语言、其它版式；
- ⛔ 中山大学成绩单的**其它版本**（只有当前核验过的这一种）；
- ⛔ **需要修复的 PDF**（截断 / 损坏）：页面解析库会**成功修复**这类文件并返回
  （可能不完整的）内容而不报错。实测把真实成绩单截断到 97% 会让第二个学期整段消失。
  因此打开文档后立即检查 `is_repaired`，为真即按 "malformed PDF" **fail closed**：
  ⛔ 绝不把修复过的文件当作权威成绩单输入。
- ⛔ 从版面里"猜"课程号（成绩单本来就没有官方课程号）。

## 必须被拒绝的行（⛔ 绝不当作课程）

- 学期汇总行：`学分 20.5(必修)1(专选)`、`绩点(必、专选)3.6`；
- 页脚统计：`毕业应得学分：…`、`实得学分：…`、
  `主修全部课程平均绩点：…`、`评分体系：…`、`P/NP 通过/不通过，不计绩点`；
- `毕业论文题目：`、`审核人: … 印制`、`国家学生体质健康标准：…`；
- 任何"没有成对的学分 + 成绩单元格"的文本行。

判定方式是**结构化**的：只有学分列与成绩列同时出现合法取值，才认为是一张课程数据行；
再与该行（或上一行）的名称格配对。⛔ 不靠"像不像课程名"来判定。

## 为什么导入结果全是 `pending`

真实成绩单**不提供**官方课程号。⛔ 本模块**不构造、不推断、不借用**任何课程号，
因此每条记录都是：

```json
{
  "course_id": null,
  "course_id_status": "pending",
  "id_match_source": null,
  "course_name": "…",
  "credit": 3.0,
  "semester": "2025-2026学年第一学期",
  "passed": true,
  "course_type": "专必",
  "source_record": "pdf:1"
}
```

既有 `matching.py` 对这种"身份未确认"的记录是**保守**的：

- 目标方案里**同名**的课 ⇒ `possibly_equivalent`（"发现名称候选，等价关系待人工确认"）；
- 目标方案里**没有候选**的课 ⇒ `manual_confirmation`（"仍有课程号待确认的已修记录，
  不能确定缺课"）；
- ⛔ **不会**因为课程名相似就变成 `satisfied`。

也就是说：**PDF 输入可以驱动分析，但"认定"仍然要人来做**。
要把 `pending` 升级为已确认身份，必须在官方来源侧（例如"成绩转换"页面的实修课程成绩）
拿到课程号，并留下 `id_match_source` 依据。

## 内部接入点

`case.py` 的 `completed` 字段现在支持三种**互斥**输入：

```json
{ "source_id": "…", "pdf":   { "path": "相对本文件的路径" } }
{ "source_id": "…", "xlsx":  { "path": "…", "sheet_name": "已修课程_脱敏" } }
{ "source_id": "…", "records": [ … ] }
```

三者必须**恰好提供一个**；给两个会直接报错（⛔ 不"悄悄挑一个"）。
XLSX 入口与 `records` 形式**行为完全未变**，仍是兼容路径。

## 窄接口

```text
POST /api/v1/completed-courses/import-pdf
  Content-Type: application/pdf
  Content-Length: <必填>
  body: 原始 PDF 字节（⛔ 不用 multipart，⛔ 不读文件名）
```

返回归一化统计 + 可直接回灌 `completed` 的 `completed_input` 片段。

| 状态码 | `detail.error` | 含义 |
| --- | --- | --- |
| 415 | `completed_courses_pdf_upload_unsupported_media_type` | 不是受支持的 PDF 媒体类型 |
| 411 | `completed_courses_pdf_upload_length_required` | 缺少 / 非法 `Content-Length` |
| 413 | `completed_courses_pdf_upload_too_large` | 声明或实际字节数超限 |
| 400 | `completed_courses_pdf_upload_length_mismatch` | 字节数与声明长度不一致 |
| 400 | `completed_courses_pdf_upload_empty` | 空文件 |
| 400 | `completed_courses_pdf_invalid` | 不是合格成绩单 / 版面不符 / 损坏 / **需要修复** |
| 400 | `completed_courses_pdf_empty` | 版面正确但没有任何课程行 |
| 400 | `completed_courses_pdf_too_many_records` | 课程条数超过上限 |

⚠️ `source_id` 由**内容摘要**派生（`upload:pdf:sha256:<16 hex>`），⛔ 与文件名无关。
⚠️ 本接口是**摄取能力**，⛔ 不接入已冻结的 Case A fixed-case runtime；
Case A 固定 case 仍由 `app/services/planning_runtime.py` 装配。

## 隐私边界

| 项 | 处理 |
| --- | --- |
| 姓名 / 学号 / 学院 / 专业 | ⛔ 不读取、不返回：表头以上的区块整体丢弃 |
| 绩点 / 排名 / 平均绩点 | ⛔ 不返回（页脚统计行被拒） |
| 具体成绩 | 仅在内部 `TranscriptRecord.grade` 与本机审计中存在，⛔ 不进入 API 响应 |
| 错误信息 | 只含固定通用文案；⛔ 不含课程名、成绩、学号、姓名、路径、堆栈 |
| 落盘 | ⛔ 不写临时文件；PDF 只在内存中解析 |
| 网络 | ⛔ 不联网；不执行 PDF 内嵌脚本 / 动作 |

## 运行依赖

```text
pymupdf>=1.24
```

已核验版面的四个单元格共享**同一基线**；字符级回调会按字体给出不同基线偏移
（同一行错位约 8 个用户单位），无法可靠按行归并。因此解析层使用 PyMuPDF 的
**词级坐标**。环境缺少该库时 PDF 入口 fail closed 并返回明确错误，⛔ 不静默降级。

## 已知限制

1. 只支持已核验版面；其它版本的成绩单会 **fail closed**（报"版面不符"），
   不会给出错误的课程表。
2. 成绩单没有课程号 ⇒ 同名课程停在 `possibly_equivalent`，需要人工认定。
3. 换行课程名的续行判定依赖"紧跟在一个无名称数据行之后且间距不超过一个行高"，
   已核验样本满足；⛔ 若未来出现别的换行方式，会表现为**少合并**（课程名偏短）
   而不是**错合并**（两门课粘一起）。
4. 成绩单里的课程属性只保留原始文本（`公必` / `专必` / `专选` / `公选` 等），
   **不**据此推断课程归属或认定规则。
