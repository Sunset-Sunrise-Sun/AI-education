# 培养方案 PDF 上传与解析：复用面报告与新增接口提案

> 分支：`feature/pdf-curriculum-import`（基线 `feature/final-upgrade` = `fbcc54d`）
> 本文件是**先交付的勘查结论**：哪些能直接复用、哪些必须新写、新增了哪些接口。
> ⚠️ 本轮的**架构负责人已批准**三项决定（见 §6）。

---

## 0. 一句话结论

> **DOCX 解析链的下游可以 100% 复用；需要新写的只有"PDF 字节 → 表格单元格"这一层，
> 外加一层传输/安全校验。** 硬约束（不得猜课程号、不得求和猜组学分、不得自动判定等价、
> 草稿默认未核验）**由既有代码自动满足**，不需要新增任何规则。

PDF 提取器只要产出既有数据类型 `DocxImportResult`（内含 `DocxCourseRow`），
后面整条链（草稿 → catalog.json → 审核 → provenance 门禁 → 个人规划）**零改动可用**。

---

## 1. 可直接复用（零修改）

### 1.1 数据形状：PDF 提取器的**输出契约**

`backend/app/curriculum/docx_reader.py`：

```python
@dataclass(frozen=True, slots=True)
class DocxImportIssue:      # code, table_index, row_index, field=None, column_index=None
@dataclass(frozen=True, slots=True)
class DocxCourseRow:        # table_index, row_index, course_id, course_name, credit,
                            # requirement, source_record, course_type=None, group_id=None,
                            # recommended_term_text=None, prerequisites=None,
                            # raw_values=(), issues=()
@dataclass(frozen=True, slots=True)
class DocxImportResult:     # source_id, rows, issues
```

**关键事实（已逐处核对）**：

- 该模块 **不 `import docx`**：它把 `.docx` 当 OOXML zip 包，用标准库 `zipfile` + `ElementTree` 读。
  → **"不依赖 python-docx" 但 "只认 OOXML 包结构"**，所以它**不能**吃 PDF。这一层必须新写。
- `DocxCourseRow` **没有 `__post_init__`** → 可从纯值裸构造。
- `DocxImportResult.__post_init__` 只校验 `source_id` 非空 + 元素类型；
  `to_version()` 的唯一 gate 是"**任何 issue 都不许有**"，之后由
  `normalize_curriculum_version` 做真正的强校验。
  → **PDF 层把未解析值填 `None` 是安全的**：`to_version()` 会 fail closed，
  不会静默产出半成品。

⚠️ 两个必须遵守的接缝：

| 接缝 | 要求 |
| --- | --- |
| `source_record` | 它是 `CurriculumVersion` 的**唯一性主键**。DOCX 用 `table:{t}!row:{r}`。**PDF 必须自己 mint 唯一值**，本方案用 `page:{n}!row:{i}` |
| `requirement` | 必须是 `RequirementKind` 枚举，⛔ 不能是 `str`（构造期不报错，会在 `to_version()` 才炸） |

### 1.2 草稿层：`backend/app/curriculum/catalog_draft.py`

| 符号 | 能否复用 |
| --- | --- |
| `CatalogDraftInput` / `to_payload()` | ✅ 完全复用（**无 `__post_init__`**，只消费 `DocxCourseRow` 属性） |
| `draft_to_catalog_payload()` | ✅ 完全复用（`verification.verified=False`、`complete=False` **硬编码**，签名里没有打开它们的开关） |
| `render_draft_report()` | ✅ 完全复用 |
| `_HUMAN_REQUIRED_FIELDS` | ✅ 完全复用：`recommended_semester` / `deadline_semester` / `prerequisites` 三项已写死为"解析器不推断" |
| `build_catalog_draft_input(docx_path, ...)` | ⚠️ **唯一耦合点**：它接 `docx_path` 并内部调 `load_curriculum_docx`；`source.kind` 与 `docx_name` 写死 DOCX |

→ **新增**：一个接受"`DocxImportResult` + 来源标注"的组装入口（见 §3.1），
把 `source.kind` 参数化。⛔ 不复制 `catalog_draft.py` 的任何逻辑。

### 1.3 目录层与门禁

| 复用项 | 位置 | 效果 |
| --- | --- | --- |
| `load_curriculum_catalog(..., approved_versions=...)` | `curriculum/catalog.py` | 草稿一律 `not_verified`（缺证据）或 `provenance_not_verified`（缺锚点），**不可选** |
| `CATALOG_REJECTED_CODES` | 同上 | 固定原因码，⛔ 不回显私有文本 |
| `load_personal_catalog` | `services/personal_runtime.py` | env `APP_PERSONAL_CATALOG_DIR` + `APP_TRUST_ANCHOR_PATH`；缺锚点 ⇒ `provenance_not_verified` |
| 组长审批 | `tools/review_real_data.py` + `app/provenance/` | `--kind curriculum_catalog` **已支持**该 artifact 形状 |

**结论：草稿在物理上无法进入可选列表**——`catalog.py` 先过 provenance 门再过 `not_verified`。
本轮的 PDF 路径**不需要、也不允许**绕过它。

### 1.4 计算层（Phase C）

`curriculum/matching.py`：`build_curriculum_diff(...)`、`project_makeup_tasks(diff)`。
个人路径：`personal/planning.py` 的 `personal_curriculum_case` / `build_personal_plan`。

**"不得声称算出个人缺修课程"的护栏已存在且充足**（⛔ 本轮不新增规则）：

1. 默认状态是 `MANUAL_CONFIRMATION`，理由是"未发现匹配，但缺课认定尚未确认"；
2. `not new.complete or not completed_complete` ⇒ "输入范围未确认完整，不能确定缺课"；
3. `project_makeup_tasks` 硬要求 `diff.new.complete`，否则 raise；
4. `group.minimum_credit is None` ⇒ raise（**不可能用成员学分求和冒充组要求**）。

由于草稿的 `complete` 恒为 `False`，**PDF 导入的版本在人工补齐前物理上无法产出 `MakeupTask`**。

### 1.5 传输层与安全范式（照抄，不重造）

`api/completed_courses.py` + `services/completed_courses_ingest.py` 提供可直接照抄的先例：

| 检查 | 复用点 |
| --- | --- |
| **刻意不用 multipart** | 全仓库 `UploadFile` 出现 **0** 次；`python-multipart` **不是依赖** |
| 媒体类型白名单 + 归一化 | `normalize_media_type()` |
| `Content-Length` 严格解析（先查位数再 `int()`） | 防超长十进制变 500；缺失/非法 ⇒ 411 |
| 声明长度 == 实读长度 | 不一致 ⇒ 400 |
| 空文件拒绝 | ⇒ 400 |
| **流式限长读取（不信声明值）** | `_read_limited_body()` |
| 受控临时文件 + 无条件删除 | `tempfile.mkstemp` + `finally: unlink` |
| **source_id 由内容摘要派生** | `f"upload:sha256:{digest[:16]}"`，⛔ 不信任文件名 |
| 错误码 → HTTP 映射表 | `_STATUS_BY_CODE`（413 用字面量，避免绑 Starlette 版本） |

⚠️ **仓库内不存在任何 magic-byte 检查**（XLSX 靠 zipfile 结构校验代替）⇒ **`%PDF-` 校验必须新写**。

### 1.6 前端与 E2E

| 复用项 | 说明 |
| --- | --- |
| `frontend/src/config.ts` | 端点 + `VITE_*` 开关范式（`PERSONAL_PLANNING_ENDPOINTS` 可照抄） |
| `api/personalPlanning.ts` | 版本清单客户端范式（错误类型 / 原因码分离） |
| `UserInputPanel.vue` | **唯一**文件输入范式：⛔ 它刻意"只选文件、不上传"，可作为对立面参考 |
| `components/views/MakeupPathView.vue`、`components/ai/IntentConfirmPanel.vue` | "待人工确认"交互范式 |
| `tools/browser-e2e/cases.mjs` | 用例声明形状；核心断言是**浏览器实际发出的 HTTP 请求** |

---

## 2. 必须新写（清单）

| # | 新增 | 为什么不能复用 |
| --- | --- | --- |
| 1 | **PDF → 单元格提取层** `app/curriculum/pdf_reader.py` | `docx_reader` 只认 OOXML zip；OOXML 的 revision/hidden/merge 语义在 PDF 里**没有对应物**，必须按 PDF 实际情况重新定义 |
| 2 | **`%PDF-` magic 校验** | 全仓库无任何 magic-byte 检查 |
| 3 | **PDF 媒体类型白名单** | 既有 `ALLOWED_MEDIA_TYPES` 是 XLSX 专用 |
| 4 | **PDF 上传路由 + 请求/响应模型** | 见 §3.2（负责人已批准） |
| 5 | **PDF 依赖声明** | 见 §3.3（负责人已批准 PyMuPDF） |
| 6 | **草稿组装入口**（接 `DocxImportResult`） | `build_catalog_draft_input` 直接接路径且写死 `kind="docx"` |
| 7 | **前端 PDF 导入 UI + 上传客户端** | 现无任何上传 API 客户端 |
| 8 | **合成 PDF 测试夹具** | 仓库内 **0 个 `.pdf`**；需自建最小 PDF 生成器（不引入第二个库） |

---

## 3. 本轮新增的接口

### 3.1 `app/curriculum/pdf_reader.py`（新模块）

```python
def load_curriculum_pdf(
    data: bytes, *, source_id: str, tables: Sequence[Mapping[str, object]],
) -> DocxImportResult: ...
```

- **输入 `bytes` 而非路径**：上传路径直接给内存字节；⛔ 不接受调用方字符串作为路径。
- **输出就是 `DocxImportResult`**：下游（草稿 → catalog → 审核 → 门禁）零改动。
- `tables` profile 沿用既有形状，新增 `mode="tables"`（库表格识别 + **表头精确匹配**）。
- `source_record = f"page:{n}!row:{i}"`（与 DOCX 的 `table:T!row:R` 同构）。
- ⛔ **严格模式**：表头不匹配、行宽不符、学分不可解析、行数超限 ⇒ 产出行级 issue 或整体失败，
  **绝不猜值、绝不静默丢行**。

### 3.2 `app/api/curriculum_import.py`（新私有端点，负责人已批准）

沿用 `personal_plan.py` 先例：**请求/响应模型是本模块私有包络**，
⛔ **不动 `/schemas/**`**、⛔ **不动 `/docs/interfaces/**`**；`main.py` 只加一行 `include_router`。

```text
POST /api/v1/curriculum-import/parse
  headers: Content-Type: application/pdf, Content-Length: <n>
  body:    原始 PDF 字节（⛔ 不用 multipart）
  query:   role=origin|target, source=<提交者给出的来源说明>
  → 200: { draft: CatalogDraftInput.to_payload(), source: {kind, name, sha256},
           review_conclusion: "pending_group_lead_review", notes: [...] }
  → 400/411/413/415: 固定错误码
```

⚠️ **如实声明**：这是一条**新增的公共 HTTP 表面**（即使不改 Schema）。
负责人已批准；PR 里会明确写出。

### 3.3 依赖

`backend/requirements.txt` 新增 **PyMuPDF**（负责人已接受其 AGPL/商业双许可）。

- ⛔ 不用 PyMuPDF 的 `page.get_text()` 拼表格，只用 `page.find_tables()` 的**结构**；
  ⛔ 不做正则"从行文本里抠课程号"。
- 依赖边界写在 §5（`REQUIRED` / `OPTIONAL`），便于日后换库或去掉依赖时**一处修改**。

---

## 4. 硬约束如何被"结构性地"满足

| 约束 | 由什么保证 |
| --- | --- |
| 不得从课程名猜课程号 | 提取器只读声明列位/表头里的**课程号单元格**；缺失即 `unresolved_course_id`，⛔ 无任何名称→编号映射 |
| 不得用成员学分求和猜组最低要求 | `group_records` **不由 PDF 推导**；缺失自动进 `human_required`，且 `minimum_credit=None` ⇒ `project_makeup_tasks` raise |
| 不得自动判定跨专业等价 | 等价关系只来自 `ConfirmedRecognition` / `MatchingRules`；默认 `allow_*` 全 False |
| 默认 `verified=false` / `complete=false` / `approval=pending` | `draft_to_catalog_payload()` **硬编码**，无参数可打开 |
| 上传不得直接写 catalog 目录 / 批准锚点 | 上传路径只返回 payload；写盘由**人**执行；`review_real_data.py` 另有 `_refuse_if_anchor_path` |
| 扫描型 PDF 不自动 OCR | 可提取字符数低于阈值 ⇒ `scanned_pdf_text_layer_missing` 整体 fail closed，⛔ 不产出猜测结果 |
| 不得误标为学校正式签发 PDF | 来源标注**参数化**为 `pdf-upload` / 材料说明原文；`verification.evidence` 保持 `None`，⛔ 不写"学校正式"字样 |

---

## 5. 未验证项（UNVERIFIED，如实列出）

| # | 未验证 | 原因 |
| --- | --- | --- |
| 1 | 两份真实 PDF 的表格能否被 `find_tables()` 稳定识别 | **两份 PDF 在本机不存在**（已整机搜索确认）；仓库内也无任何 `.pdf` |
| 2 | 跨页表格合并的实际表现 | 同上 |
| 3 | 真实 PDF 的页数是否为 8 / 9 | 同上 |
| 4 | 真实课程条目数与源 PDF 能否逐项核对 | 同上 |

→ 与之相关的 6 项人工验收（任务书 §七 的 1–4 项等）在真实材料到位前**保持 BLOCKED**。
本轮的自动化验收全部基于**自建合成 PDF**（自建最小 PDF 生成器，不引入第二个库）。

---

## 6. 本轮已获批准的三项决定

| 决定 | 内容 |
| --- | --- |
| **PDF 样本** | 负责人会把两份 PDF 放到 `C:\Users\28746\Desktop\AI+教育\real-curriculum-pdf\`；在此之前真实样本验收保持 BLOCKED，⛔ 不虚构 |
| **PDF 依赖** | 采用 **PyMuPDF**（表格识别最强）；负责人已知悉其 AGPL-3.0 / 商业双许可 |
| **HTTP 表面** | 批准新增模块内私有端点，⛔ 不动 `/schemas/**` 与 `/docs/interfaces/**` |

---

## 7. 顺带发现（供负责人判断，⛔ 本轮不据此扩大范围）

桌面上有一份 **`mk.html`（312 KB，2026-10-10 16:24）**，是**已保存的教务网页**
（`jwxt.sysu.edu.cn` 全校培养方案查看）。内容统计：

| 关键词 | 出现次数 |
| --- | --- |
| 遥感科学与技术 | **14** |
| 网络空间安全 | **0** |
| 培养方案 | 5 |
| 学分 | 44 |
| 必修 / 选修 | 5 / 8 |
| 课程号 | **0** |

→ 它可能是"两份 PDF 由教务 HTML 重排而来"中的**原始 HTML 素材之一**（仅含遥感专业）。
⛔ 本轮**不**把它纳入解析范围（任务书只要求 PDF）；如需要，请另行指示——
它涉及"从 HTML 提取"这一条**新的**来源类型，应与 PDF 路径分开评估。
