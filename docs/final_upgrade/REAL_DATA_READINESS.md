# 真实培养方案与教学班数据接入准备（验收与操作指南）

> 适用分支：`release/final-upgrade-demo-readiness`
> 依据：对 `backend/app/curriculum/**`、`backend/app/course_data/**`、
> `backend/app/services/**`、`backend/tests/**` 的**只读**代码勘查（含逐条文件与行号引用）。
>
> **一句话结论**：两个模块的代码**已完成且默认失败关闭**（fail-closed），
> 但仓库内**没有任何一份已核验的真实数据**；
> 个人规划链路已经通到 `MakeupTask` 与真实 Planner 的注入点，
> 缺的只有三件东西：**① 已核验的版本目录 artifact、② 真实已修记录进入请求、③ 教学班的全学期验收**。
>
> ⛔ 本文件不伪造学校正式培养方案，⛔ 不编造学生已修课程；
> 所有缺口都以"需要人工提供什么"的形式列出。

---

## 1. 数据缺口清单（人需要提供什么）

| # | 缺口 | 需要的产物 | 放置方式 | 现状 |
| --- | --- | --- | --- | --- |
| D1 | **已核验培养方案版本目录** | `catalog.json`（一份，含源专业 + 目标专业两个版本） | 任意本机目录，通过环境变量 `APP_PERSONAL_CATALOG_DIR` 指向 | **缺失**（仓库内 0 份；未配置时接口如实返回 503 `personal_catalog_not_configured`） |
| D2 | **学生已修记录（脱敏）** | ① 合规 XLSX，或 ② 直接构造 `student.completed.records[]` | XLSX 走 `POST /api/v1/completed-courses/import`；inline 走个人规划请求体 | **缺失**（前端目前硬编码 `records: []`，所以 UI 上恒为"全部缺修"） |
| D3 | **本学期教学班快照（真实）** | 五校区 Capture Bundle + 已批准的 inventory + 前后基线 | 通过两个 CLI 验收进 SQLite；再由 5 个环境变量接入 | **缺失**（仓库内 `"data_source": "real"` 的 JSON **0 条**） |
| D4 | **Case A 冻结案例文件** | case JSON（`data_source=real` 且与冻结决策一致） | `APP_CASE_A_CURRICULUM_CASE_PATH` | **缺失**（仅影响 `/api/v1/plan`，不影响个人规划） |
| D5 | **catalog artifact 的生产工具** | 把"real DOCX 培养方案 + 规则"转成 `catalog.json` 的导入器 | —— | ✅ **已交付**（`tools/build_catalog_draft.py`，产出 `verified=false` 的审核草稿；见 `DOCX_CATALOG_DRAFT.md`） |
| D6 | **批准锚点（组长签署）** | `trust-anchor.json`（含 kind / identity / artifact_sha256 / approver / authorization） | ⛔ **仓库外**受权限保护目录，由 `APP_TRUST_ANCHOR_PATH` 指向 | **缺失**（组长尚未签署任何记录；缺它 ⇒ `provenance_not_verified`（503），这是设计意图） |

> **D5 说明**：产出 D1 的导入器已交付，但它只产出 `verification.verified=false` 的**草稿**；
> 补齐为可用目录仍需人工确认字段（见 `DOCX_CATALOG_DRAFT.md` §4）。

> **D6 说明（本轮新增）**：即使 D1–D4 齐备，运行时仍会拒绝装配，直到组长签署 D6。
> 流程见 `APPROVAL_OPERATING_PROCEDURE.md`（组长逐条执行），
> 原理与角色分离见 `APPROVAL_WORKFLOW_DESIGN.md`。
> ⚠️ 组长签署仅代表**项目内部**确认来源可靠，
> ⛔ 不代表学校正式认证，也⛔ 不代表课程等价或学分认定。

---

## 2. 需要的确切字段

### 2.1 `catalog.json`（内部 artifact，⛔ **不是**公共 Schema）

顶层：`{"catalog_version": 1, "versions": [ ... ]}`
`catalog_version` 必须等于 `1`（`curriculum/catalog.py:94`）。

每个 version 条目：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version_id` | ✅ | 唯一；两个版本不能同名（同名会被整体置为不可选，fail-closed） |
| `major` / `cohort` | ✅ | 专业名 / 年级 |
| `source_id` | ✅ | 来源标识 |
| `verification.verified` | ✅ | **布尔**，必须为 `true`（这是**自述标记**，不是证据；见 §5 风险） |
| `verification.evidence` | ✅ | 非空；建议写"学校/学院文件 + 日期 + 交付人" |
| `verification.verified_by` | 可选 | 核验人 |
| `supported` | ✅ | 是否受支持 |
| `unsupported_reason` | `supported=false` 时 | 不支持的原因 |
| `complete` | ✅ | 是否完整 |
| `completeness_evidence` | `complete=true` 时**必填** | 完整性证据（计数**不能**作为完整性证明） |
| `campus` / `track` / `total_credit` / `practice_credit` / `study_years` | 可选 | 校区 / 方向 / 学分 / 实践学分 / 学制 |
| `group_records[]` | ✅ | 见下 |
| `course_records[]` | ✅ | 见下 |

`course_records[]` 必填：`course_id`、`course_name`、`credit`、
`requirement` ∈ `required|elective|unknown`、`source_record`（**版本内唯一**）。
可选：`course_type`、`group_id`、`recommended_term_text`、`prerequisites[]`、
`recommended_semester`、`deadline_semester`。

`group_records[]` 必填：`group_id`、`name`、`minimum_credit`、`source_record`；
`group_id` 唯一，且**每个** `course.group_id` 必须能在某个 group 里找到。

### 2.2 已修记录（inline `student.completed.records[]`）

必填：`course_id`、`course_name`、`credit`、`semester`、`passed`、`course_type`、
`course_id_status`（`confirmed`/`已确认`/`pending`/`待确认`）、`id_match_source`。
可选：`source_record`（默认 `row:N`）、`notes`。

**语义约束（会被强制检查）**：

- `course_id_status = confirmed` ⇒ `course_id` **非空** 且 `id_match_source` **非空**；
- `course_id_status = pending` ⇒ `course_id` 必须是 `null`（⛔ 不允许猜一个课程号）。

`student.completed.complete = true` 时必须给 `completeness_evidence`。
⛔ 不建议由人来判"是否等价"——`recognitions[]`（课程认定）与
`missing_requirements[]` 都需要**人工证据**，没有证据就必须保持缺修/待确认。

### 2.3 XLSX 已修课程（推荐路径）

- 工作表名**必须**是 `已修课程_脱敏`；
- 第 1 行表头 A:J **必须**逐字为：
  `序号, course_id, course_name, credit, semester, passed, course_type, course_id_status, id_match_source, 备注`；
- `序号` 必须是唯一正整数；第 10 列之后除 L:M 的 `交接摘要`/`值` 外**不得**有内容；
- 限制：≤ 2000 条、≤ 8 MiB；公式**不会**被求值。

### 2.4 教学班快照（Course Data）

- Capture Bundle：`format=sysu-opening-courses-capture-v1`、`semester`、
  `first_page_no`、`page_size`、`pages[].page_no`、`pages[].response`
  （页码必须从 `first_page_no` 起**连续唯一**，不会被"修正"）；
- 原始行必填：`courseNum`、`courseName`、`classNumber`、`yearTerm`、
  `score`、`limitNumber`、`selectedNumber`；可选 `teachingTimePlaceStr`（课表串）、教师字段；
- 全学期验收需要：五个已批准校区 slug（`east-campus`/`south-campus`/`shenzhen-campus`/
  `zhuhai-campus`/`north-campus`）、已批准的 `CaptureInventory`、
  `baseline_before == baseline_after`、以及一个持有五个校区验收记录的校区库。

---

## 3. 数据校验流程（现有，可直接复用）

```text
① 目录层   load_curriculum_catalog
           - catalog_version 必须为 1；必填键缺失 ⇒ entry_invalid
           - verification.verified 必须为 true ⇒ 否则 not_verified
           - complete=true 必须有 completeness_evidence
           - version_id 重复 ⇒ 该 id 下所有条目**全部**不可选（fail-closed）

② 记录层   normalize_curriculum_version / normalize_completed_courses
           - 逐字段类型与枚举校验；source_record 版本内唯一
           - confirmed/pending 的语义约束（见 §2.2）

③ 快照层   OfferingSnapshot
           - completeness ∈ {partial, complete}
           - complete 要求 reported_total == loaded_count（计数必须自洽）
           - 所有 offering 必须同 semester 且 data_source=real
           - 重复 (semester, course_id, class_id) ⇒ 失败
           - ⛔ partial **不能**进入生产：import_offering_snapshot 直接拒绝

④ 验收层   accept_full_semester_capture_set
           - 五校区 + inventory 绑定 + bundle 摘要两两不同 + 基线稳定
           - 产生不可变验收（manifest SHA-256 作为身份）；同语义重复导入会冲突

⑤ 读取层   StoreBackedCourseDataProvider
           - **每次读**都重算：验收记录、双平面、completeness、
             loaded_count == reported_total == offering_count > 0、
             成员身份集合、逐行 offering_payload_sha256、offering_set_sha256、逐行 provenance
           - 任何漂移 ⇒ CourseDataAcceptanceError ⇒ HTTP 503 real_pipeline_not_configured
```

**公共 Schema 只在 Mock 通道被真正强制**（`services/mock_service.py`：
先 `jsonschema` 对 `schemas/*.schema.json` 校验，再进 Pydantic）。
其它路径用 Pydantic + 手写校验；测试里另有若干处显式 `jsonschema.validate`。

---

## 4. 已核验数据的接入操作指南（可直接照做）

### 步骤 0：准备目录

```text
<DATA_DIR>/
  catalog.json          # 已核验版本目录（源专业 + 目标专业，共 2 个版本）
  student.json          # 可选：已脱敏已修记录（inline 形式）
  bundles/              # 仅当教学班数据也到位时：五校区 Capture Bundle
```

### 步骤 1：先用**合成**数据确认链路本身是通的（不碰真实数据）

```powershell
cd backend
$env:PYTHONUTF8 = '1'
$env:APP_PERSONAL_CATALOG_DIR = "$env:TEMP\verify_catalog"   # 任意空目录即可
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另一个终端：

```powershell
cd backend
$env:PYTHONUTF8 = '1'
python -m tests.verify_real_data_e2e --mode synthetic `
  --catalog-dir "$env:TEMP\verify_catalog" --base-url http://127.0.0.1:8000
```

**期望**：`✅ 可选版本 2 个`；两位合成学生各自产出 3 个补修任务；
第三步如实报告 `planning_skipped_code = no_course_data`（教学班还没接入）。

> **本轮已实测**：合成模式通过，输出见
> `docs/final_upgrade/reports/FINAL_DELIVERY_READINESS_REPORT.md` §5。

### 步骤 2：换成已核验目录，再跑一次

```powershell
$env:APP_PERSONAL_CATALOG_DIR = "<DATA_DIR>"
# 重启后端后：
python -m tests.verify_real_data_e2e --mode verified `
  --catalog-dir "<DATA_DIR>" --student "<DATA_DIR>\student.json" --semester 2026-1
```

脚本会**先拒绝** `verification.verified != true` 的版本（⛔ 未核验目录不得进入验收）。

### 步骤 3：接入真实教学班（如已采集）

```powershell
# 五校区逐一做校区验收
python tools/validate_course_data_artifact.py --help
# 再做全学期验收
python tools/accept_full_semester_course_data.py --help
# 或者用统一的编排工具（含 LEVEL2 资格判定与 env 文件草稿）
python tools/prepare_real_case_a_runtime.py --help
```

然后设置（**五个都要**）：

```text
APP_REAL_CASE_A_ENABLED=1
APP_CASE_A_CURRICULUM_CASE_PATH=<DATA_DIR>\case.json
APP_COURSE_DATA_SQLITE_PATH=<DATA_DIR>\course_data.sqlite
APP_COURSE_DATA_SEMESTER=2026-1
APP_COURSE_DATA_ACCEPTANCE_SHA256=<64 位十六进制>
```

### 步骤 4：再次运行验收脚本

```powershell
python -m tests.verify_real_data_e2e --mode verified `
  --catalog-dir "<DATA_DIR>" --student "<DATA_DIR>\student.json" --semester 2026-1
```

**期望**：第三步从 `no_course_data` 变为
`✅ 已产出规划结果（教学班数据已接入）`。

---

## 5. 现有合成夹具（本轮可直接用；⛔ 都明确标注为合成）

| 夹具 | 内容 | 何时用 |
| --- | --- | --- |
| `backend/tests/personal_fixtures.py` | 完整目录 artifact（`mock-old-2025` / `mock-target-2025`）+ 两位独立合成学生 | `verify_real_data_e2e --mode synthetic` |
| `backend/tests/test_synthetic_production_e2e.py` | **整条生产链路**的进程内合成验证：合成原始行 → Capture Bundle → 校区验收 → 全学期验收 → SQLite → `build_planning_runtime` → `/api/v1/plan` → `PlanResult` 过 jsonschema | 教学班数据到位前验证"接线是否正确" |
| `mock_data/*.json` + `mock_data/curriculum_demo/*` | 演示数据；运行时先过 `/schemas/*.schema.json` 再进 Pydantic | 页面演示（有 `X-Data-Source: mock` 头） |
| `backend/tests/qa_browser_e2e/qa_demo_data.json` | 浏览器 E2E 的受控演示数据（带 `_qa_note`） | 浏览器 E2E |
| `backend/tests/xlsx_fixtures.py` | 合成 XLSX 字节 | XLSX 读取器测试 |

**所有合成夹具的共同点**：`source_id` / `evidence` 一律以 `mock://` 开头，
所以既能被真实校验器接受，又能被一眼识别为合成数据。

---

## 6. 已知风险（供负责人决策，⛔ 本 Agent 不擅自修改）

1. **`data_source` 是自述字段。** 个人规划请求里的 `data_source` 由调用方声明；
   唯一的守卫是"real + evidence 含字面量 `mock://` ⇒ 拒绝"（`curriculum/case.py:147`）。
   一份本地 `catalog.json` 只要不写 `mock://`，其内容就会被报成 `real`，
   而 `verification.verified` 本身只是文件里的一个布尔。
   ⇒ **建议**：真实目录的交付要走人工签字 + 记录 `verification.evidence`，
   并在验收报告里写明"verified 是人工声明，不是技术证明"。

2. **真实运行时没有"合成 vs 真实"闸门。** `build_planning_runtime`
   只检查开关、案例文件与验收 SHA-256；合成 Capture Bundle 经由两个 CLI
   也能产出 `data_source=real` 的教学班。
   `handoff.synthetic == false` 这类闸门只存在于 `tools/prepare_real_case_a_runtime.py`（工具层）。
   ⇒ **建议**：把"合成不得进生产库"的判定下沉为运行时不变式（**属新增开发，需人工批准**）。

3. **`plan_profiles.py` 硬编码文档假设**（表索引、列位、锚点 `FL101`/`GST326`/…、
   选修池 `CSE-ELECTIVE-POOL` / 23 学分）。换专业对或学校改版都会失败关闭。
   ⇒ 真实 DOCX 到位后需先确认这些假设，或改写 profile（**属新增开发**）。

4. **XLSX 导入结果不能直接喂给个人规划**：导入返回的 `source_id` 是
   `upload:sha256:<16 hex>`，而个人规划要求
   `personal-upload://sha256:<64 hex>`，直接透传会 **422**。
   正确做法：**只复制 `records`**（去掉 `source_id`），
   由个人规划侧自行派生 `completed_source_id`。
   本轮的验收脚本已按这个方式构造请求。

5. **AI 调整上下文由调用方提供**（`makeup_tasks` + `course_offerings` 来自请求体），
   ⛔ 后端没有"从 Curriculum/Course Data 拉上下文"的链路。
   ⇒ 任何声称"Curriculum → Course Data → Planner → AI 上下文"是单条后端链路的说法都是**不准确**的。

---

## 7. 未验证事项

| 项 | 状态 |
| --- | --- |
| 真实已核验 `catalog.json` 是否存在（由负责人在仓库外产出） | **UNVERIFIED**（仓库内无任何指示） |
| 五个已批准 `openingSchoolNumber` 是否与学校当前系统一致 | **UNVERIFIED**（有测试锁定它不被改动，但未对真实系统核验） |
| `planning_skipped_code = "semester_not_bound"` 是否真的可达 | **UNVERIFIED**（前端有文案，未找到产出该前缀的后端路径） |
| 真实学生成绩单、真实教学班数据的端到端 | **BLOCKED**（数据未提供） |
