# 成绩单图片识别（OCR）接入设计

> 状态：**设计已提交，等待确认后实现**。
> 本阶段⛔ 未实现 OCR、⛔ 未接任何假 OCR、⛔ 未用演示数据代替识别结果。

## 1. 目标：图片与 PDF **统一输出** `TranscriptCourse[]`

Phase 4 的硬要求是"图片/PDF 统一输出 `TranscriptCourse[]`"，且**不改动既有 matching engine**。

### 1.1 统一口径：`CompletedCourse`（既有内部输入）

仓库**已经有**这条统一缝，本轮勘察确认（`backend/app/api/completed_courses.py`）：

```text
POST /api/v1/completed-courses/import            （既有 XLSX 入口，Gate F）
  → CompletedCoursesImportResponse.completed_input.records
     = 可直接放进 curriculum case `completed.records` 的片段
     = app/curriculum/completed_courses.py 的 CompletedCourse 输入形状
         course_id / course_name / credit / semester / passed
         course_type / course_id_status / id_match_source / source_record
```

**这就是 `TranscriptCourse` 的既有形状。** 因此"统一输出"不需要新契约：

```text
成绩单 PDF ──┐
             ├─→ CompletedCourse[] ─→ matching engine（⛔ 一行不改）
成绩单图片 ──┘
```

### 1.2 两个入口的对称性

| 入口 | 摄取适配器 | `source_id` 前缀 | `source_record` | `course_id_status` |
|---|---|---|---|---|
| PDF（现有） | `services/completed_courses_pdf_ingest.py` | `upload:pdf:sha256:` | `pdf:<n>` | 恒 `pending` |
| XLSX（现有） | `services/completed_courses_ingest.py` | `upload:sha256:` | `row:<n>` | 可为 `confirmed` |
| **图片（本次设计）** | `services/transcript_ocr_ingest.py` | `upload:image:sha256:` | `img:<n>` | 恒 `pending` |

三条路径**产出同一个 `CompletedCourse` 元组**，然后走同一个 matching engine。

## 2. 输入

| 项 | 要求 |
|---|---|
| 格式 | PNG / JPEG / WebP（与既有课表截图导入一致） |
| 大小 | ≤ 8 MiB（与 `MAX_UPLOAD_BYTES` 同口径） |
| 分辨率 | 长边 ≥ 1600 px；低于此值**提示可能影响识别**，⛔ 不静默降级 |
| 页数 | 单张。多页需逐页上传、逐页确认 |
| 敏感字段 | 姓名 / 学号 / 身份证 / 照片**必须**在返回前剔除 |

## 3. 输出：`TranscriptCourse` 结构

### 3.1 识别层（OCR 组件的产出，未归一化）

```jsonc
{
  "source_id": "upload:image:sha256:1f3c…",   // 由内容摘要派生，⛔ 不来自文件名
  "artifact_sha256": "1f3c…",
  "image": { "width": 2480, "height": 3508 },
  "records": [
    {
      "row_id": "img:3",                       // 稳定标识，供用户确认引用
      "course_name": "程序设计",                 // 识别出的课程名
      "credit": 2.0,                           // 可空
      "score": 88.0,                           // 可空
      "semester_text": "2025-2026学年第一学期",  // 可空
      "passed": true,
      "confidence": 0.93,                      // ⛔ 仅用于交互，不参与判定
      "unconfirmed": ["图片未包含官方课程号，需人工确认课程身份。"]
    }
  ],
  "unrecognized_rows": [
    { "row_id": "img:7", "reason": "表格线遮挡，课程名不完整" }
  ]
}
```

### 3.2 归一化层（喂给 matching engine，**统一输出**）

`transcript_ocr_ingest.py` 把它映射成既有 `CompletedCourse`：

| CompletedCourse 字段 | 取值 | 说明 |
|---|---|---|
| `course_id` | **恒 `null`** | ⛔ OCR 不得推断课程号 |
| `course_name` | 用户确认后的最终值 | 未经确认的不进入本层 |
| `credit` | 识别值；空则 `0.0` 并在 `notes` 标注待确认 | |
| `semester` | `semester_text`；空则 `"unknown"` | ⛔ 不猜学期 |
| `passed` | 识别值 | |
| `course_type` | `null` | 图片无此信息 |
| `course_id_status` | **恒 `"pending"`** | 与 PDF 入口一致 |
| `id_match_source` | `null` | 未做任何身份匹配 |
| `source_id` | `upload:image:sha256:<digest[:16]>` | 与 PDF 入口格式对称 |
| `source_record` | `img:<row>` | 可审计到图片行号 |
| `notes` | 识别警告文本 | ⛔ 不参与判定 |

**硬约束**：`course_id` 恒 `null` + `course_id_status` 恒 `pending`
⇒ 匹配引擎必然给出 `manual_confirmation`/`possibly_equivalent`，
**⛔ 不会伪造任何自动认定**。

## 4. 接口设计

### 4.1 识别（新增）

```http
POST /api/v1/transcript-images/recognize
Content-Type: application/json

{ "image_base64": "…", "media_type": "image/png" }
```

响应：第 3.1 节的识别层结构。

**为什么单独一个端点**：识别是"图片 → 课程记录"的**无状态转换**，
不属于任何 case，也⛔ 不触发匹配。与 `/plan` 分离，保证"识别"与"判定"
在接口层就分开（符合 `AGENTS.md`「OCR 层只负责 图片 → 课程记录」）。

| 状态码 | `detail.error` | 含义 |
|---|---|---|
| 400 | `transcript_image_unsupported_media_type` | 非 PNG/JPEG/WebP |
| 413 | `transcript_image_too_large` | 超 8 MiB |
| 422 | `transcript_image_invalid` | 无法解码 / 版面不符 |
| 422 | `transcript_image_no_records` | 未识别出任何课程行 |
| 503 | `transcript_ocr_not_configured` | OCR 运行时未配置 |
| 500 | `transcript_ocr_failed` | OCR 引擎内部失败 |

⛔ 任何失败都**不回退到演示数据**。

### 4.2 提交（**⛔ 不需要新契约**）

```http
POST /api/v1/case-a-demo/plan
{ "semester": …, "completed_courses_records": [ …已完成确认的 CompletedCourse… ], … }
```

⚠️ **这是本设计中唯一需要你批准的一处接口扩展**，但它是**最小**的：

```text
当前设计：PlanRequest 只接受 transcript_pdf_base64（必填）。
建议修改：新增可选字段 completed_courses_records，
         与 transcript_pdf_base64 **恰好提供一个**（互斥校验）。
原因：     图片识别的产物是"已确认的课程记录"；
         把它重新编码成 PDF 属于伪造原始材料，⛔ 不可接受。
影响模块： backend/app/api/case_a_demo.py（请求体 + 一条互斥校验）
         app/services/case_a_demo.py（run() 入口分支：record 分支跳过 PDF 解析）
是否破坏性：否（新增可选字段，PDF 行为完全不变）
替代方案：  ⛔ 无（另建 /plan-with-records 会造成两套匹配入口，更差）
```

**不需要改的**（明确列出，便于 review）：
- ⛔ `app/curriculum/matching.py`（匹配引擎）—— 一行不改
- ⛔ `/schemas/*.schema.json`、`app/models/contracts.py` —— 一行不改
- ⛔ `/api/v1/plan` 生产契约 —— 一行不改

### 4.3 前端流程

```text
选择成绩单图片（本机预览，⛔ 不上传第三方）
  ↓ POST /transcript-images/recognize
识别结果列表（课程名 / 学分 / 学期 / 置信度 / 为什么需确认）
  ↓ 用户逐条 确认 / 修改 / 丢弃（⛔ 未确认的不进入匹配）
经确认的 TranscriptCourse[]
  ↓ POST /case-a-demo/plan（completed_courses_records）
补修缺口分析（satisfied / need_confirmation / missing）
```

## 5. 安全边界

| 项 | 约束 |
|---|---|
| 联网 | ⛔ 默认本地/自建 OCR；使用第三方云必须先获明确授权 |
| 图片留存 | ⛔ 不留存原图；识别后立即释放，服务端只保留 SHA-256 |
| 日志 | ⛔ 不打印图片内容、姓名、学号；错误码为固定枚举 |
| 脱敏 | 姓名 / 学号 / 身份证 / 照片**不进入**响应体 |
| 上传目标 | 前端图片只发**本项目后端**，⛔ 不发第三方 |
| 权限 | 只处理用户本人成绩单（与 PDF 入口同口径） |

## 6. 待你确认的两点

1. **提交契约扩展**（第 4.2 节）：是否批准 `completed_courses_records` 可选字段？
2. **OCR 引擎选型**：本地 Tesseract / PaddleOCR / 学校或云服务？
   以及**是否允许**把学生成绩单图片发往该服务？
   在确认前不会实现 —— 因为⛔ 不允许"先用假数据顶上"。

## 7. 验收标准（实现后必须满足）

1. 上传图片后 `records.length > 0`，且全部 `course_id_status == "pending"`、`course_id is None`。
2. 未经用户确认的记录**不进入**匹配（断言"确认前不产生任何匹配结果"）。
3. 确认识别结果后三状态随之变化，且 `source_evidence` 出现 `img:<n>` 依据。
4. OCR 失败时页面如实报错，⛔ 不出现演示数据。
5. ⛔ 全程不向第三方上传图片（用请求拦截断言）。
6. **图片与 PDF 走同一个 matching engine**：断言两条路径产出的
   `CompletedCourse` 形状完全一致（同字段、同 `pending` 语义）。
