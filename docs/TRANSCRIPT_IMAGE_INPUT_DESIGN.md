# 成绩单图片输入链（Phase 5）设计

> 状态：**已完成**（后端识别 + 前端确认页 + 提交接线 + E2E 测试）。
> ⛔ 未使用任何假识别数据：图片由**真实成绩单 PDF** 渲染，OCR 为本地真实推理。

## 1. 目标与硬约束

```text
成绩单图片 ─┐
            ├─→ CompletedCourse[] ─→ matching engine（⛔ 一行不改）
成绩单 PDF ─┘
```

| 约束 | 落实方式 |
|---|---|
| 图片/PDF 统一进 `CompletedCourse[]` | 两个适配器产出**同一形状**（第 3 节） |
| OCR 只负责识别，不负责认定 | 输出恒 `course_id=None` + `course_id_status="pending"` |
| ⛔ 不自动判断等价课程 | 识别层不产生任何等价关系 |
| ⛔ 不自动生成 satisfied | 识别层不产生任何 `MakeupStatus` |
| ⛔ 不接入假识别数据 | 失败即 fail closed，⛔ 无演示回退 |
| 必须经过确认页 | `GET` 只返回候选；提交走**已确认**记录 |

## 2. 架构设计

```text
┌──────────────────────── 前端 ────────────────────────┐
│ TranscriptImageImport.vue                            │
│   选择图片（本机预览，⛔ 不上传第三方）                │
│   → POST /api/v1/transcript-images/recognize         │
│   OCR 结果**确认页**                                  │
│     逐条：确认为成绩单课程 / 修改课程名 / 丢弃          │
│     ⛔ 未确认的条目不得进入匹配                        │
│   → POST /api/v1/case-a-demo/plan                    │
│        （completed_courses_records，见第 5 节）        │
└──────────────────────────────────────────────────────┘
┌──────────────────────── 后端 ────────────────────────┐
│ api/transcript_images.py        ← 新端点（仅识别）     │
│ services/transcript_ocr_ingest.py ← OCR + 脱敏 + 列网格│
│   ├─ 本地 OCR（RapidOCR / ONNX，⛔ 不联网）            │
│   ├─ ① 个人身份信息脱敏                                │
│   ├─ ② 列网格推断（由数据行几何推导）                   │
│   └─ ③ 行聚类 + 名称续行合并 → 候选                    │
│ services/case_a_demo.py   ← 接受已确认记录（⛔ 不改判定）│
│ curriculum/matching.py    ← ⛔ 一行不改                │
└──────────────────────────────────────────────────────┘
```

### 2.1 为什么 OCR 用 RapidOCR 而不是 PaddleOCR

任务要求"优先考虑本地 PaddleOCR"。实测结论：

```text
python 3.14.7  →  paddleocr : 无可用 wheel（PaddlePaddle 未支持 3.14）
                  rapidocr-onnxruntime : ✅ 已安装，可直接用
```

`RapidOCR` **就是 PaddleOCR 的 PP-OCR 模型**在 ONNX Runtime 上的本地推理实现：
模型同源、完全离线、⛔ 不联网。因此在本环境下它是 PaddleOCR 的等效替代。
若后续需要原生 PaddleOCR，只需替换 `_run_ocr()` 一个函数，其余逻辑不变。

### 2.2 为什么列归属不靠 x 容差

实测发现两个必须绕开的陷阱：

1. 卷面把「课程名称 / 学分 / 成绩 / 属性」横向重复若干遍（左上还多一个"序号"列），
   但**只有第一组填了课程行**；
2. OCR 会把表头**切碎并错位**（"课程名称"被拆成多块，`课程` 甚至落到属性列上），
   还会把课程名碎片误判成"学分"标题。

因此列归属改用**内容语义 + 固定列顺序**：

```text
课程名 → [学分] → 成绩 → 属性标记      （行内 x 递增）
```

以属性标记（公必/专必/…）为行锚点 —— 它是行内最右、最稳的信号；
其左侧**最近的数值块是成绩**、**再左侧的数值块是学分**、其余非数值块属于课程名。
⛔ 全程只判断"是不是数字"，⛔ 不读取课程名内容做任何判断。

## 3. 数据流

```text
图片字节
  ↓ 媒体类型 / 声明长度 / 实际大小 / 空文件 校验（与既有 PDF / XLSX 入口同口径）
本地 OCR → 文本块 + 置信度 + 包围盒
  ↓ ① 个人身份信息脱敏（姓名 / 学号 / 学院 / 专业 …）
  ↓ ② 列网格推断（由数据行几何推导）
  ↓ ③ 行聚类（属性标记锚定）+ 名称续行合并（前缀 / 后缀两种方向）
课程候选（course_id=None、course_id_status=pending）
  ↓ 用户在确认页逐条确认 / 修改 / 丢弃
CompletedCourse 元组
  ↓
matching engine（⛔ 一行不改）→ makeup_tasks / elective_progress
```

### 3.1 与 PDF 入口的形状一致性

| 字段 | PDF 入口 | **图片入口（本阶段）** |
|---|---|---|
| `course_id` | `None` | `None` |
| `course_name` | PDF 抽取 | OCR + 用户确认 |
| `credit` | PDF 抽取 | OCR 抽取；缺失则 `0.0` + `notes` 标注 |
| `semester` | PDF 学期行 | OCR 学期行；缺失则 `unknown` |
| `passed` | 成绩判定 | `score_text` 判定；缺失按未通过处理并标注 |
| `course_type` | `null` | `null` |
| `course_id_status` | `pending` | `pending` |
| `id_match_source` | `null` | `null` |
| `source_id` | `upload:pdf:sha256:<16>` | `upload:image:sha256:<16>` |
| `source_record` | `pdf:<n>` | `img:<n>` |

## 4. 隐私边界

| 项 | 约束 | 实现 |
|---|---|---|
| 联网 | ⛔ 图片不发往任何第三方 | 本地 ONNX 推理 |
| 落盘 | ⛔ 不写临时文件、⛔ 不留存原图 | 全内存处理 |
| 脱敏 | 姓名 / 学号 / 学院 / 专业 / 年级 / 时间 等**在进入聚类之前丢弃** | `_is_pii()`，实测丢弃 9 块 |
| 回传 | ⛔ 不回传被丢弃块的内容，只回传**数量** | `redacted_block_count` |
| 日志 | ⛔ 不打印识别内容；错误码为固定枚举 | 错误信息只含通用文案 |
| 失败 | ⛔ 不回退演示数据 | fail closed |

实测（真实成绩单）：识别 128 块，**丢弃 9 块个人身份信息**，
候选中**不含**姓名、学号、"姓名"、"学号"字样。

## 5. 接口设计

### 5.1 识别（新增，独立于 case-a-demo）

```http
POST /api/v1/transcript-images/recognize
Content-Type: application/json

{ "image_base64": "…", "media_type": "image/png" }
```

响应：

```jsonc
{
  "source_id": "upload:image:sha256:28296d35be34e8c6",
  "artifact_sha256": "…",
  "media_type": "image/png",
  "width": 2198, "height": 1489,
  "block_count": 128,
  "redacted_block_count": 9,          // ⛔ 不回传被丢弃的内容
  "column_groups": 1,
  "candidates": [
    {
      "row_id": "img:3",
      "course_name": "三维遥感技术导论",
      "credit": 1.5,
      "score_text": "87",
      "semester_text": "2025-2026学年第一学期",
      "course_attribute": "专必",
      "confidence": 0.663,
      "unconfirmed": ["图片未包含官方课程号，需人工确认课程身份。"]
    }
  ],
  "unrecognized": ["…"]
}
```

⛔ 响应**不含** `course_id`、⛔ 不含任何 `MakeupStatus`、⛔ 不含等价关系。

错误契约：

| 状态码 | `detail.error` | 含义 |
|---|---|---|
| 400 | `transcript_image_unsupported_media_type` | 非 PNG/JPEG/WebP |
| 411 | `transcript_image_length_required` | 缺少 `Content-Length` |
| 413 | `transcript_image_too_large` | 超 8 MiB 或像素总量超限 |
| 400 | `transcript_image_empty` | 空文件 |
| 400 | `transcript_image_invalid` | 无法解码 |
| 422 | `transcript_image_no_records` | 版面不可解析 / 无课程行 |
| 503 | `transcript_ocr_not_configured` | 本地 OCR 不可用 |

### 5.2 提交（**最小接口扩展**）

```http
POST /api/v1/case-a-demo/plan
{
  "semester": "2026-1",
  "completed_courses_records": [ …用户已确认的 CompletedCourse… ],
  "current_schedule": [],
  "manual_schedule_attested": false,
  "preference": {}
}
```

```text
当前设计：PlanRequest 只接受 transcript_pdf_base64（必填）。
建议修改：新增可选字段 completed_courses_records，
         与 transcript_pdf_base64 **恰好提供一个**（互斥校验）。
原因：     图片识别的产物是"已确认的课程记录"；
         重新编码成 PDF 属于伪造原始材料，⛔ 不可接受。
破坏性：   否（新增可选字段，PDF 行为完全不变）
⛔ 不需要改：matching engine / schemas / contracts.py / /api/v1/plan
```

## 6. 实测识别质量（真实成绩单）

```text
真实课程行（PDF 解析路径，作为对照）: 24 门
OCR 候选                            : 23 条
课程名正确                          : 22/24（约 92%）
个人身份信息泄漏                    : 0
```

已确认的已知限制（**必须在 UI 上如实告知，并由用户修正**）：

| 限制 | 表现 | 处理方式 |
|---|---|---|
| 学分列常读不出 | 23 条中仅 2 条给出 credit | 确认页可手工补填；缺失时 `notes` 标注 |
| 长课程名偶发残留 | 如 `对地观测一一探索与发现`（多一个"一"） | 确认页可编辑修正 |
| 少数行被并入相邻行 | 如"思想道德与法治"被吃进上一行 | 确认页可拆分/丢弃 |
| 成绩偶有误读 | 如 `08`（实为 86） | 确认页可修正 |

> ⚠️ 这些限制**不构成伪造**：所有候选都标注 `unconfirmed`，
> 且**必须经用户确认**才会进入匹配。OCR 是"候选生成器"，不是权威数据源。

## 7. 实现清单（全部已完成）

```text
后端：✅ services/transcript_ocr_ingest.py（OCR + 脱敏 + 列网格 + 行聚类）
      ✅ api/transcript_images.py（POST /transcript-images/recognize）
      ✅ services/case_a_demo.py（confirmed_records 分支，与 PDF 共用同一 matching）
      ✅ api/case_a_demo.py（confirmed_completed_courses，与 PDF 二选一）
      ✅ tests/test_transcript_ocr_ingest.py（41 条）

前端：✅ api/transcriptImages.ts（识别调用 + 确认记录转换）
      ✅ components/TranscriptImageImport.vue
           - 本机预览、识别中、候选列表
           - 逐条：确认为成绩单课程 / 修改课程名 / 补填学分 / 设置是否通过 / 丢弃
           - 未识别内容如实列出（⛔ 不猜测）
           - ⛔ 未确认条目不进入提交内容
      ✅ components/CaseADemoView.vue（图片确认结果 → plan 请求；PDF 路径不变）
      ✅ tests/transcript-image-input.spec.ts（15 条 E2E）
```

## 8. 验收标准

1. 上传图片后 `candidates.length > 0`，且全部无 `course_id`、无 `MakeupStatus`。
2. 未经用户确认的条目**不进入**匹配（断言"确认前不产生任何匹配结果"）。
3. 确认后三状态随之变化，且 `source_evidence` 出现 `img:<n>`。
4. OCR 失败时页面如实报错，⛔ 不出现演示数据。
5. ⛔ 全程不向第三方上传图片（请求拦截断言）。
6. 图片与 PDF 走**同一个** matching engine（形状一致性断言）。
7. 个人身份信息不出现在响应任何字段。
