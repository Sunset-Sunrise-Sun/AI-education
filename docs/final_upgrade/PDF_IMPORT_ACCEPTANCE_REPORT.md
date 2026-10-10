# 培养方案 PDF 导入验收报告

> 分支：`feature/pdf-curriculum-import`（基线 `feature/final-upgrade`）
> 复用面分析见 `PDF_IMPORT_REUSE_REPORT.md`（先交付的那一份）
> ⚠️ **两份真实 PDF 不在本机**，因此与真实材料相关的验收项**保持 BLOCKED**（见 §5）

---

## 1. 本轮交付了什么

| 层 | 交付物 | 说明 |
| --- | --- | --- |
| 解析 | `backend/app/curriculum/pdf_reader.py` | PDF 字节 → `DocxImportResult`（**复用既有输出契约**） |
| 传输与安全 | `backend/app/services/curriculum_pdf_ingest.py` | 媒体类型白名单、`Content-Length` 严格解析、流式限长、SHA-256 ⇒ `source_id` |
| HTTP | `backend/app/api/curriculum_import.py` | `POST /api/v1/curriculum-import/parse-pdf`（**模块内私有包络**） |
| 前端 | `frontend/src/components/CurriculumPdfImport.vue` + `frontend/src/api/curriculumImport.ts` | 两个独立 PDF 上传位、课程表、待确认清单、来源审核状态 |
| 依赖 | `backend/requirements.txt` 新增 `pymupdf>=1.24` | 已获架构负责人许可（AGPL/商业双许可） |
| 测试 | 后端 2 个新文件 + 前端 1 个新文件 + E2E 新用例 | 见 §4 |

**关键设计**：解析器产出的是既有类型 `DocxImportResult`，因此
`catalog_draft` → `catalog.json` → 审核工具 → provenance 门禁 → 个人规划
**整条下游零改动复用**，⛔ 没有复制任何业务规则。

---

## 2. 解析准确性（**合成 PDF**，可自动化验证的部分）

合成夹具覆盖真实形态的**结构**特征（`tests/pdf_fixtures.py` 自建最小 PDF 写入器，⛔ 未引入第二个库）。
表头与课程号用 ASCII（真实培养方案的课程号本来就是 `MAR103` / `CSE323` / `n08120200` 这类 ASCII）；
中文名称的解析依赖"文本层存在 + 表头精确匹配"这条同一路径。

| 检查 | 结果 |
| --- | --- |
| 能读出有边框表格 | ✅ 6 列 / N 行逐行读出 |
| **行数无静默丢失** | ✅ 参数化 1 / 2 / 3 / 5 / 8 行，读出行数**恒等于**画出行数 |
| 每行可追溯定位 | ✅ `source_record = page:{n}!row:{i}`，跨页各自带页码 |
| 学分解析（含单位） | ✅ `3` / `2.5` / `3 credits` / `3 学分` 均可取；`3-4`（区间）⇒ **留空 + `unresolved_credit`** |
| 要求类别映射 | ✅ `required` / `elective` / `必修` / `选修` 命中；未声明文字 ⇒ `UNKNOWN` + `unmapped_requirement` |
| 占位符课程号 | ✅ `待确认` / `unknown` ⇒ `course_id=None` + `unresolved_course_id`（⛔ **绝不**用课程名充当课程号） |
| 表头不匹配 | ✅ 整表拒绝（`table_header_mismatch`），⛔ 不按位置硬套 |
| 无表格线的 PDF | ✅ `table_not_found`（⛔ 不退回纯文本猜测） |
| 一个问题行仍然产出 | ✅ 3 行输入 ⇒ 3 行输出，坏行带 4 个 issue，⛔ 不丢弃 |
| 下游 fail closed | ✅ 任一行有 issue ⇒ `to_version()` 抛错 |

### 2.1 未识别课程清单（合成夹具）

合成夹具中"故意无法识别"的行**全部**被如实列入 `unresolved_rows`，无一条被静默丢弃：

| 来源定位 | 课程号 | 课程名 | 学分 | 问题码 |
| --- | --- | --- | --- | --- |
| `page:1!row:2`（夹具） | `None` | `None` | `None` | `unresolved_course_id`、`missing_course_name`、`unresolved_credit`、`unmapped_requirement` |

⚠️ **真实材料的未识别清单尚不存在**——它需要两份真实 PDF 才可能产出（见 §5）。

---

## 3. 来源审核边界（本轮最重要的架构约束）

| 约束 | 如何被结构性保证 |
| --- | --- |
| 上传 / 解析 / 用户确认 ≠ 来源核验 | 响应 `verification_verified: false` **硬编码**；`review_conclusion` 恒为 `pending_group_lead_review` |
| ⛔ 不得误标为学校正式签发 PDF | 响应 `is_official_school_pdf: false` **硬编码**，并在来源说明里明写"由教务网页重排生成的转换件" |
| 草稿默认不可选 | `verification.verified=false` + `complete=false`（`draft_to_catalog_payload` 硬编码）⇒ `catalog.py` 判 `not_verified`/`provenance_not_verified` |
| 上传⛔ 不写 `APP_PERSONAL_CATALOG_DIR` | 端点只返回内存 payload；测试断言运行后目录**仍为空**、锚点**不存在** |
| 上传⛔ 不写批准锚点 | 只有组长授权的独立受控流程能写（`app/provenance`）；同上测试断言 |
| 前端⛔ 不能批准 | 组件没有批准按钮；文案把批准权归属组长；测试断言页面不出现"来源已核验" |
| 用户确认与组长批准分离 | 勾选框文案明写"只表示读对了，⛔ 不代表来源已被核验或批准" |

---

## 4. 安全测试结果（任务书 §七 第 7、8 项）

| 攻击 / 异常 | 结果 |
| --- | --- |
| 非 PDF 字节（`GIF89a…`） | ✅ 422 `pdf_import_unparsable` |
| `%PDF-` 头 + 垃圾（伪装） | ✅ 422（库解析失败 ⇒ 拒绝，⛔ 不返回空结果冒充成功） |
| 空文件 | ✅ 400 `pdf_upload_empty` |
| 超大文件（> 8 MiB） | ✅ 413；且**声明长度超长**（5000 位十进制）也判 413，⛔ 不走 `int()` 变成 500 |
| 缺 `Content-Length` | ✅ 411 `pdf_upload_length_required`（传输层实测） |
| 声明长度 ≠ 实读长度 | ✅ 400 `pdf_upload_declared_length_mismatch` |
| `multipart/form-data` / `text/plain` / `application/json` | ✅ 415 `pdf_upload_media_type_unsupported` |
| **扫描型 PDF（无文本层）** | ✅ 422，文案明确 "scanned PDF is not supported; manual handling required"（⛔ 不 OCR、⛔ 不猜测） |
| 加密 PDF | ✅ 拒绝（⛔ 不尝试破解、⛔ 不接受调用方传密码） |
| 页数超上限（> 200） | ✅ 拒绝 |
| 路径泄漏 | ✅ 响应只保留**基名**；实测 `C:\...\private\curriculum.pdf` ⇒ 只回 `curriculum.pdf`，响应全文不含 `C:\` / `Users` / `private` |
| 错误信息泄漏 | ✅ 所有失败都是固定文案（`pdf import:` 前缀），⛔ 不含路径 / 库版本 / 单元格原文 |
| issue 泄漏 | ✅ issue 只有固定码 + 行列号，⛔ 不携带原始文本 |
| 依赖 | ✅ `pymupdf` 只在解析层使用；⛔ 不改公共 Schema、⛔ 不触 Planner |

---

## 5. 【BLOCKED】两份真实 PDF 的人工验收

```text
【BLOCKED — 真实材料验收】
阻塞原因：两份培养方案 PDF（遥感科学与技术 2025级 8页、网络空间安全 2025级 9页）
          **在磁盘上不存在**。已整机搜索确认；仓库内也没有任何 .pdf。
已经确认：解析层、传输层、安全校验、前端入口与边界文案均已实现，
          并用**合成 PDF** 通过了全部可自动化验证的验收项（§2、§4）。
无法确认：① 能否正确读取这两份 PDF；
          ② 课程信息能否与源 PDF 逐项核对；
          ③ 跨页表格与选修组有无静默丢失；
          ④ 两份 PDF 的真实页数（8 / 9）与真实课程条目数；
          ⑤ 真实表头文字与表格位置（默认 profile 是否需要调整）。
需要人工提供：把两份 PDF 放到
          C:\Users\28746\Desktop\AI+教育\real-curriculum-pdf\
          然后执行：
            cd backend
            $env:PYTHONUTF8='1'
            python tools/parse_curriculum_pdf.py --help
          按提示对每份 PDF 产出「解析准确性报告」与「未识别课程清单」。
在确认前不会：把任何真实 PDF 提交进仓库；⛔ 不会用合成数据冒充真实验收结果；
          ⛔ 不会为了让链路跑通而放宽任何 fail-closed 检查。
```

### 5.1 材料到位后的执行步骤（已备好）

1. 把两份 PDF 放入上述目录（⛔ 不要提交进 Git）；
2. 跑 `python tools/parse_curriculum_pdf.py`（见该工具的 `--help`），得到：
   - 解析出的课程表（含 `page:N!row:M` 定位）；
   - 未识别课程清单；
   - 文档级 issue 清单；
3. 逐项与源 PDF 人工核对（任务书 §七 第 2 项），把差异记入本节；
4. 若真实表头与默认 profile 不同，**由人**在工具参数里调整声明（⛔ 不让 Agent 猜列位）。

---

## 6. 保留不变的部分

| 项 | 状态 |
| --- | --- |
| Mock 演示通道 | ✅ 未改动；`GET /api/v1/mock/demo` 仍返回 200 + `X-Data-Source: mock`（测试断言） |
| 既有 DOCX 工具与解析器 | ✅ 未改动；`docx_reader.__all__` 与入口签名原样（测试断言） |
| 公共 Schema | ✅ `/schemas/*.schema.json` 文件名与内容均未改（测试断言无 `pdf`/`catalog`/`verification` 字样） |
| `/docs/interfaces/**` | ✅ 未改动 |
| Planner 算法 | ✅ 未改动；PDF 模块不 import `app.planner` / `app.integration`（测试断言） |
| 既有路由 | ✅ 未覆盖；新路由逐条登记进白名单测试 |

---

## 7. 已知限制（如实列出）

| # | 限制 | 影响 | 缓解 |
| --- | --- | --- | --- |
| 1 | 只支持**有表格线**的 PDF | 无边框（纯文本对齐）表格识别不出来 | 如实报 `table_not_found`，⛔ 不猜；后续可评估按显式列位解析 |
| 2 | `table_index` 语义是"**该页**第 N 张表" | 表格跨页时需按页声明 | 已在 docstring 与实际行为中说明；真实材料到位后按需调整声明 |
| 3 | 不支持扫描件 | 图片型 PDF 无法解析 | 明确报告 + 转人工；⛔ 不自动 OCR（任务书要求） |
| 4 | 中文表头未在合成夹具中覆盖 | 默认 profile 已列中文表头，但自动化测试用 ASCII 表头 | 真实 PDF 到位后由人工核对表头命中情况 |
| 5 | 默认 profile 是**声明**而非推断 | 真实表头不同则整表拒绝 | ⛔ 不猜列位；由人调整声明 |

---

## 8. 建议下一步

1. **组长把两份 PDF 放入指定目录** ⇒ 我立即补跑 §5 的验收并回填本报告；
2. 若表头与默认声明不同，由人给出真实表头 ⇒ 我调整 profile **参数**（⛔ 不改解析逻辑）；
3. Phase B/C（审核集成与补修联调）在真实材料验收后推进：
   - Phase B 依赖组长批准锚点（⛔ 我无法签发）；
   - Phase C 在没有真实学生已修记录前**无法**声称算出了个人缺修课程——
     这由既有护栏保证（`not diff.new.complete → raise`）。
