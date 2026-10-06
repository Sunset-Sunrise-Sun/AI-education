# 已修课程 XLSX 导入（Gate F，通用摄取能力）

> 状态：**已实现（backend only，synthetic-only 验证）**。
> ⛔ 未修改 `/schemas/*.schema.json`、⛔ 未修改 frozen Provider contract、
> ⛔ 未接入已冻结的 Case A fixed-case runtime、⛔ 不含任何真实学生数据。

## 1. 两条**不同**的路径（⛔ 不要混淆）

```text
（A）Case A demo 固定 case 路径（已冻结）
     APP_CASE_A_CURRICULUM_CASE_PATH = <仓库外固定 case JSON>
       → CurriculumCaseProvider（固定 case，含已批准的 scope 决策）
       + StoreBackedCourseDataProvider（已验收 full_semester acceptance）
       + RestrictedPlannerProvider
       → POST /api/v1/plan
     ⚠️ 该 case 的 `completed` 段**固定**（本 Gate ⛔ 未动态化它）；
        未装配 ⇒ 503 real_pipeline_not_configured。

（B）通用已修课程 XLSX 摄取能力（本 Gate 新增）
     POST /api/v1/completed-courses/import  （原始 .xlsx 字节）
       → 已归一化的已修课程事实（Curriculum 既有内部输入）
       → 返回可直接回灌 curriculum case `completed` 的片段
     ⚠️ 这是**能力**，⛔ 不是"Case A 已经会读用户上传的成绩单"。
        要把上传结果接进规划，仍需由调用方/后续工作把该片段放进一个 case
        （届时属于 integration 变更，需另行裁定）。
```

⛔ **未做**：把上传结果动态注入已冻结的 Case A runtime。
`backend/app/services/planning_runtime.py` 仍然只装配固定 case（有回归测试锁定
"runtime 源码里不出现上传适配器"）。

## 2. 接口

```http
POST /api/v1/completed-courses/import
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
              （也接受 application/octet-stream）
Content-Length: <必填>
<原始 .xlsx 字节>
```

成功响应（200）：

```json
{
  "source_id": "upload:sha256:0123456789abcdef",
  "artifact_sha256": "<64 hex>",
  "worksheet": "已修课程_脱敏",
  "record_count": 3,
  "confirmed_course_id_count": 2,
  "pending_course_id_count": 1,
  "passed_count": 2,
  "distinct_course_count": 2,
  "notes_present_count": 2,
  "completed_input": {
    "source_id": "upload:sha256:0123456789abcdef",
    "records": [
      {
        "course_id": "DEMO-COURSE-01",
        "course_name": "示例课程一",
        "credit": 3.0,
        "semester": "2026-1",
        "passed": true,
        "course_type": "示例必修",
        "course_id_status": "confirmed",
        "id_match_source": "示例来源",
        "source_record": "已修课程_脱敏!row:2"
      }
    ]
  }
}
```

- `completed_input` **恰好**是 curriculum case `completed` 字段接受的 `records` 形状
  （已用 `normalize_completed_courses` 回灌验证）；
- `source_id` 由**内容摘要**派生（`upload:sha256:<16 hex>`），⛔ 不来自文件名 / 调用方输入；
- ⛔ **不回传 `备注` 自由文本**（唯一可能夹带个人信息的字段）：只回传
  `notes_present_count` 计数；其余字段与 Curriculum 输入契约一一对应。

## 3. 安全边界（F2）

| 项 | 做法 |
| --- | --- |
| 只允许明确支持的 XLSX | 媒体类型白名单（官方 XLSX MIME / `application/octet-stream`）+ **唯一**批准的 worksheet `已修课程_脱敏` + A:J 固定列头校验 |
| 文件大小限制 | `MAX_UPLOAD_BYTES = 8 MiB`（声明长度先拒、流式读取再拒，⛔ 不信任 `Content-Length`）；单部件 16 MiB / 解压总量 64 MiB 由既有 reader 把关 |
| 空文件拒绝 | `Content-Length: 0` ⇒ 400 `completed_courses_upload_empty`；只有表头没有数据行 ⇒ 400 `completed_courses_empty` |
| malformed ZIP/XLSX | fail closed ⇒ 400 `completed_courses_invalid`（⛔ 不静默跳过） |
| 禁止执行公式 | reader 遇到 `<f>` / 错误单元格**直接拒绝**（⛔ 无 openpyxl，⛔ 不评估公式） |
| 禁止宏执行 | 只解析 XML 部件；`xl/vbaProject.bin` 等宏部件被**忽略**，⛔ 永不加载 / 执行 |
| 不信任文件名 | 请求里根本没有"文件名"参与判定（⛔ 无 multipart、⛔ 无 `filename` 字段）；`source_id` 由内容摘要派生 |
| 不写到任意路径 | 只写进程自己的临时目录（`tempfile.mkstemp`，固定后缀）；⛔ 任何调用方字符串都不作为路径 |
| 临时文件生命周期 | `finally` 中无条件删除；成功与失败路径都有回归测试断言"不留残file" |
| 错误信息 | 只有通用文案 + 行列位置（数字）；⛔ 不含单元格取值 / 原始 XML / 本地路径 / stacktrace |
| 日志 | 本模块⛔ 不打印任何 worksheet / cell 内容（⛔ 不打整份成绩单/课程表） |
| 记录条数 | `MAX_COMPLETED_RECORDS = 2000`，超限 ⇒ 400 `completed_courses_too_many_records` |

错误码 ↔ 状态码：

```text
415 completed_courses_upload_unsupported_media_type
411 completed_courses_upload_length_required
400 completed_courses_upload_length_mismatch
413 completed_courses_upload_too_large
400 completed_courses_upload_empty
400 completed_courses_invalid
400 completed_courses_empty
400 completed_courses_too_many_records
```

## 4. 复用（⛔ 不重复实现 Curriculum 逻辑）

```text
worksheet/table extraction · 字段映射 · 结构校验  → app/curriculum/xlsx_reader.py（既有）
normalize into existing internal input            → app/curriculum/completed_courses.py（既有）
Curriculum Diff / equivalence / recognition /
makeup priority / prerequisite decision           → app/curriculum/matching.py（既有，本 Gate ⛔ 未改）
```

本次新增只有两处：`app/services/completed_courses_ingest.py`（字节 → 受控临时文件 → reader）
与 `app/api/completed_courses.py`（HTTP 边界与响应模型）。

## 5. 已实现的 F6 闭环（synthetic-only）

```text
synthetic XLSX 字节
  → POST /api/v1/completed-courses/import（真实 endpoint）
  → completed_input.records
  → normalize_completed_courses（Curriculum 既有归一化）
  → normalize_curriculum_case + CurriculumCaseProvider.get_makeup_tasks()
  → 与用原生 `records` 的同一 case 结果**完全一致**（回归测试逐条比对）
```

⚠️ 仍**未**做：前端接线（前端成绩文件仍只"选择"、不上传）、鉴权、
真实成绩单（⛔ 不接真实学生数据，North 仍 suspended）。

## 6. 未做 / 未声称

- ⛔ 未接真实成绩单 / 未真实登录 / 未联网；全部 fixture 为人工构造的 synthetic 工作簿；
- ⛔ 未声称"学校课程认定"：pending 身份、重复修读、等价性仍按既有规则处理，本 Gate 不新增任何认定；
- ⛔ 未做鉴权（与现有 `/api/v1/plan` 一致）；真实部署必须前置鉴权；
- ⛔ 未把上传结果动态注入 Case A runtime（见 §1）；
- ⛔ 未给前端新增上传交互。
