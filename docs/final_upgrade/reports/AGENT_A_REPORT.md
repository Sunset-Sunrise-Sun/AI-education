# AGENT_A_REPORT — 个人规划输入闭环与确定性校验

- **Agent**：Final Upgrade · Agent A（Builder A，无人值守）
- **分支**：`feature/personal-planning-pipeline`（base = `feature/final-upgrade`）
- **实现提交 SHA**：
  - `1bcf152455db2652889b6225cd6dfd3e3a88c098` — `feat(personal): add verified curriculum catalog and personal planning pipeline`
  - 本报告提交 SHA：见本文件所在提交（`docs(final-upgrade): add AGENT_A_REPORT.md`）
- **基线**：`feature/final-upgrade` = `d387b9a990c6fbb7138212b5c6141616ad2dc2b3`
- **是否改动 `main` / `feature/final-upgrade`**：**否**（两者一字未动，也未推送）
- **是否创建 draft PR**：是（base = `feature/final-upgrade`），**未 merge**
- **使用数据**：**Mock**（全部人工构造）。**当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**

---

## 1. 本次完成

### 1.1 培养方案目录（P0）

`backend/app/curriculum/catalog.py`：只从**调用方显式给出**的本地 artifact 读取"可选版本"元信息
（年级 / 校区 / 方向 / 来源 / 核验依据 / 核验人 / 课程数 / 组数 / 总学分等），
并复用既有 `normalize_curriculum_version` 构造内部 `CurriculumVersion`。

| 情形 | 结果 |
| --- | --- |
| `verification.verified != true` 或核验依据为空 | `rejected[].code = not_verified`，**不可选** |
| `supported = false` | `unsupported_by_source`（附来源给出的 `unsupported_reason`），**不可选** |
| `supported = true` 同时又给了 `unsupported_reason` | `entry_invalid`（自相矛盾，fail closed） |
| 同一 `version_id` 出现多次 | `version_identity_conflict`，该 id **全部**不可选 |
| 记录 / 元信息形状非法 | `entry_invalid` |
| artifact 不存在 | **空目录**（不是异常）：明确回答"没有可选版本" |
| `catalog_version` 未知 | `artifact_format_unsupported`，⛔ **不做向前兼容解析** |

⛔ 不扫描文件系统找默认目录、⛔ 不联网、⛔ 不读数据库、⛔ 不读 `mock_data`、⛔ 不解析 docx。
真实培养方案 Word 的读取仍走既有 `app.curriculum` 入口 —— 本模块**不为个人入口另造一条解析路径**。
首期**未新增数据库**。

### 1.2 独立学生输入（P0）

`backend/app/personal/student_input.py`：

- `completed_source_id` **由调用方（API 层）给出**，⛔ 不取学生行里的来源字段；
  API 层用它从**请求体内容摘要**派生（`personal-upload://sha256:<digest>`）；
- 归一化层拒绝任何 `source_id` 与本学生来源不符的记录；
- `ConfirmedRecognition` / `ConfirmedMissingRequirement` 必须属于**本人** `completed_source_id`，
  否则整次请求被拒绝（⛔ 不能把别人的认定搬过来）；
- `rules.completed_source_id` 同样必须指向本人；
- 版本 id 若由调用方显式给出，必须等于本次选定版本，否则拒绝；
- 未知字段一律拒绝（⛔ 不猜测、⛔ 不静默丢弃）。

### 1.3 严格语义（P0）

`backend/app/personal/planning.py`：

- 每一位学生**独立组装**自己的 `CurriculumCase`，⛔ **不复用任何 case 文件**；
- 计算完全走既有 `CurriculumCase` / `build_curriculum_diff` /
  `CurriculumCaseProvider.get_makeup_tasks()`；⛔ 未重写匹配、组学分或 scope 规则；
- 保留既有 `required / possibly_equivalent / manual_confirmation / satisfied` 语义（一字未改）；
- **未找到记录不必然是确证缺口**：只有"目标方案与已修范围均确认完整 + 明确的缺课规则依据"
  才会得到 `required`；否则进 `manual_confirmation`（测试有专门断言）；
- **课程身份确认 ≠ 学校转换审批**：`course_id_status = 待确认` 的通过记录
  仍得到 `manual_confirmation`（"匹配候选的课程号仍待确认，不能自动抵认"），**不降级为 required**；
- ⛔ 不从 Case A 继承 `satisfied` 状态或授信结论（两位学生交叉断言）。

### 1.4 规划假设与正式认定分离（P0/P1）

- `planning_assumptions[]` 带固定标签 `planning_assumption_not_a_recognition`；
- ⛔ 绝不改变任何 `MakeupTask.status`，只出现在 `notes` 里供人工区分；
- `ConfirmedRecognition` 走既有路径，必须带 `evidence` 且指向本人修读记录
  （认定学分不足 → 既有文案"已认定学分不足，补修方式待确认"）。

### 1.5 规划接入（P1）

- `MakeupTask[]` 来自**本学生** case；教学班供给只来自**已装配的** production Course Data；
- 显式使用**同一个已冻结的** `PlannerProvider.plan(makeup_tasks=, offerings=,
  current_schedule=, preference=)` 四参数签名：⛔ 未新增参数、⛔ 未改返回类型、⛔ 未复制 Planner 逻辑；
- 本学生 case 的 `MakeupTask[]` 是 Planner 的**唯一**任务输入；`PersonalPlanResult` 还会拒绝
  "Planner 返回本学生任务之外课程"的结果（有测试）；
- ⛔ 不改 `POST /api/v1/plan` 的请求 / 响应契约，⛔ 不读已冻结 Case A runtime 的任何配置。

### 1.6 API（P1，isolated）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/personal-planning/curriculum-versions` | 可选版本元信息 + 被拒条目（固定原因码） |
| `POST` | `/api/v1/personal-planning/plan` | 个人输入 → 本学生 `MakeupTask[]`（+ 可选 Planner） |

- 独立文件 `backend/app/api/personal_plan.py`；`backend/app/main.py` **只增加一行** `include_router`；
- 目录未配置 → **503** `personal_catalog_not_configured`（⛔ 不回退、⛔ 不猜默认版本）；
- 输入非法 → **422** `personal_plan_input_invalid`；既有规则判定不能投影 → **422** `personal_plan_not_projectable`；
- 供给 acceptance 失效 → **503** `personal_plan_course_data_unavailable`（⛔ 不返回 500、⛔ 不假装"供给为空"）；
- 未提供供给时 `planning = null` 且明确给出 `planning_skipped_code`（`no_course_data` / `no_semester`），
  ⛔ 不留空让人误解为"没有结果"。

### 1.7 确定性校验修复（P0，**行为变更**）

`backend/app/planner/credit_limit.py` + `RestrictedPlannerProvider._apply_credit_limit(...)`：

| 情况 | 新行为 |
| --- | --- |
| 两门新增彼此冲突（同天同节、周次相交） | 已有行为：都不自动加入（本轮补测试锁定，含顺序无关性） |
| 周次不重叠 | 已有行为：不构成冲突（本轮补测试锁定） |
| `原课表 + 累计新增` 已声明学分合计 **>** 学生声明上限 | **本次不加入任何新增**（⛔ 不排序、⛔ 不牺牲某一门） |
| 有课程没有学分声明 | `unverifiable` → 明确"无法证明"，⛔ **不当作已通过** |
| 原课表本身已超限 | 只提示，⛔ **不篡改学生已选事实**、⛔ 不影响无解证明 |
| 未声明上限 | 行为不变（⛔ 不发明上限） |

学分取值顺序（不猜）：`CourseOffering.credit` → 同课程 `MakeupTask.credit`；都没有 = **未知**。
⛔ 未改四参数签名、未改 `PlanResult` / `unresolved[].type` 取值、未改公共 Schema、
未定义优先级、未改学校规则或 Path Repair 目标。

---

## 2. 修改文件清单

**新增（生产代码）**

| 文件 | 说明 |
| --- | --- |
| `backend/app/curriculum/catalog.py` | 已核验版本目录读取器（fail closed） |
| `backend/app/personal/__init__.py` | 个人规划包入口 |
| `backend/app/personal/student_input.py` | 本学生输入模型与归一化 |
| `backend/app/personal/planning.py` | 本学生 case 组装 + 结果对象 |
| `backend/app/api/personal_plan.py` | 两条 API + 请求/响应包络 |
| `backend/app/services/personal_runtime.py` | 目录的显式装配边界 |
| `backend/app/planner/credit_limit.py` | 学分上限的确定性接纳校验（纯函数） |

**修改（生产代码）**

| 文件 | 改动 |
| --- | --- |
| `backend/app/main.py` | +1 import、+1 `include_router`（**仅此两处**） |
| `backend/app/planner/provider.py` | 新增 `_apply_credit_limit`；`_pending_non_time` 不再重复报告 `max_credit` |

**新增（测试与工具）**

| 文件 | 说明 |
| --- | --- |
| `backend/tests/personal_fixtures.py` | 全部显式 Mock 的培养方案 / 学生夹具 |
| `backend/tests/test_personal_planning.py` | 27 项：个人规划闭环验收用例 |
| `backend/tests/test_personal_planning_api.py` | 14 项：API + Planner 接入 |
| `backend/tests/test_planner_credit_limit.py` | 21 项：新增/选修接纳边界 |
| `backend/tools/repro_personal_planning.py` | 可复现的两位学生演示脚本 |

**修改（测试）**

| 文件 | 改动与理由 |
| --- | --- |
| `backend/tests/test_planner_provider.py` | 按新口径改写 `max_credit` 参数化用例（⛔ **不是**为了让测试变绿而放宽：原 `max_credit=0` 用例断言的是"超限新增仍被接纳"这一**旧行为**）；新增 3 项上限用例 |
| `backend/tests/test_synthetic_production_e2e.py` | `max_credit` 断言改为断言"学分上限"语义（Planner 仍**逐字回报**调用方真实取值） |
| `backend/tests/test_integration_orchestrator.py` | 显式开放路由白名单登记 2 条新路径 |

**文档**

| 文件 | 说明 |
| --- | --- |
| `docs/final_upgrade/PERSONAL_PLANNING_DESIGN.md` | 设计与边界说明、运行 / 测试 / 排查 |
| `docs/final_upgrade/reports/AGENT_A_REPORT.md` | 本报告 |
| `docs/status/curriculum.md` | 目录读取器 + 个人入口状态；Mock 声明 |
| `docs/status/planner.md` | 学分上限接纳校验（行为变更，待 Reviewer 确认） |
| `docs/worklogs/curriculum.md` | 本轮记录（追加） |
| `docs/worklogs/planner.md` | 本轮记录（追加） |

**未修改（重要）**：`/schemas/**`、`/docs/interfaces/**`、`frontend/**`、
已冻结的 Case A runtime（`app/services/planning_runtime.py`）、
`POST /api/v1/plan`、`app/integration/**` 四个调用签名、`mock_data/**`。

---

## 3. 接口契约是否变化

| 项 | 是否变化 |
| --- | --- |
| `/schemas/*.schema.json` | **否** |
| `/docs/interfaces/*.md` | **否** |
| `CurriculumProvider.get_makeup_tasks()` | **否** |
| `CourseDataProvider.get_course_offerings(semester)` | **否** |
| `PlannerProvider.plan(*, makeup_tasks, offerings, current_schedule, preference)` | **否**（参数集合恰为四个） |
| `PlanningOrchestrator.build_plan(*, semester, current_schedule, preference)` | **否** |
| `POST /api/v1/plan` 请求 / 响应 | **否**（有回归测试锁定：多给一个字段仍 422） |
| `GET /api/v1/mock/*` | **否** |
| **新增** API 路径 | **是**（2 条，见 §1.6；已在路由白名单测试中显式登记） |
| **新增** 本地 artifact 格式（`catalog_version` / `versions[]` / `verification`） | **是**（模块内部格式，⛔ 不是公共 Schema） |
| Planner 在声明了 `max_credit` 时的**输出行为** | **是**（行为变更，见 §1.7；⛔ 未改任何契约形状） |

---

## 4. 运行方法

```powershell
# 1) 指向一个**已核验**目录（本轮用测试目录；真实目录由负责人提供）
$env:APP_PERSONAL_CATALOG_DIR = "<local verified catalog dir>"
$env:PYTHONUTF8 = "1"          # Windows 上必须，否则既有用例会因 GBK 解码失败

# 2) 启动后端（在 backend/ 下）
python -m uvicorn app.main:app --reload

# 3) 列可选版本
curl http://127.0.0.1:8000/api/v1/personal-planning/curriculum-versions

# 4) 个人规划（请求体示例见 docs/final_upgrade/PERSONAL_PLANNING_DESIGN.md）
curl -X POST http://127.0.0.1:8000/api/v1/personal-planning/plan `
     -H "Content-Type: application/json" -d @request.json
```

未设置 `APP_PERSONAL_CATALOG_DIR` 时，两条接口都明确返回
**503 `personal_catalog_not_configured`** —— 这是**当前正确状态**，
⛔ 不代表功能故障，也⛔ 不会回退到固定 Case A。

---

## 5. 输入来源（可追溯性）

| 输入 | 来源 | 状态 |
| --- | --- | --- |
| 培养方案（源 / 目标） | `backend/tests/personal_fixtures.py` | **人工构造 Mock**，`source_id` / `evidence` 全为 `mock://` |
| 两位学生的已修记录 | 同上 | **人工构造 Mock** |
| 选修计划 / 匹配规则 | 同上 | **人工构造 Mock**，显式标注"人工确认，Mock" |
| 真实已核验目录 | 未交接 | **BLOCKED**（见 §8） |
| 第二位学生的真实脱敏成绩 | 未交接 | **BLOCKED**（见 §8） |

`CurriculumCase.__post_init__` 的"Mock 来源不得标为 real"守卫会在误用时立刻失败，
因此夹具不可能被当成真实数据。

---

## 6. 覆盖范围与可复现测试

### 6.1 两位学生可复现演示（命令 + 实际输出）

```powershell
cd backend
$env:PYTHONUTF8 = "1"
python tools/repro_personal_planning.py
```

实际输出（节选）：

```text
selectable versions: ('mock-old-2025', 'mock-target-2025')

--- student-one ---
completed_source_id : mock://repro/student-one
completed records   : 2
  TGT100  satisfied            依据本 case 匹配规则，课程号、规范化名称、学分及通过事实完全匹配。
  TGT101  satisfied            依据本 case 匹配规则，课程号、规范化名称、学分及通过事实完全匹配。
  TGT201  required             依据本 case 缺课规则，完整目标要求与已修记录中未发现通过匹配或身份未知的通过记录。人工已确认选修计划范围，所列学分是未来计划，不表示课程已修或选修组已满足。
planning skipped    : no_course_data: …

--- student-two ---
completed_source_id : mock://repro/student-two
completed records   : 2
  TGT100  satisfied            依据本 case 匹配规则，课程号、规范化名称、学分及通过事实完全匹配。
  TGT101  required             依据本 case 缺课规则，完整目标要求与已修记录中未发现通过匹配或身份未知的通过记录。
  TGT201  required             依据本 case 缺课规则，…
planning skipped    : no_course_data: …
```

**差异原因（具体，不是"结果不相等"）**：学生一有 TGT101 的本人已通过记录 →
既有规则判定"课程号、规范化名称、学分及通过事实完全匹配"→ `satisfied`；
学生二没有该记录（只有一次未通过）→ 既有规则判定"完整目标要求与已修记录中未发现通过匹配"
→ `required`。两位学生的 `completed_source_id` 亦不同。

### 6.2 测试命令与结果

```powershell
cd backend
$env:PYTHONUTF8 = "1"
python -m pytest -q
```

| 范围 | 结果 |
| --- | --- |
| **后端全量（本轮）** | **3045 passed / 2 failed / 2 skipped** |
| 后端全量（基线 `d387b9a`，同命令同环境） | 2981 passed / 2 failed / 2 skipped |
| 新增测试 | 27 + 14 + 21 = **62 passed / 0 failed** |
| Planner 相关（含改写后的 Provider 用例） | 212 passed / 0 failed |

**那 2 项失败是基线既有、与本轮改动无关**（已在本轮开工前用同一条命令复现）：

1. `test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]`
   —— Python 3.14 起 `Path("bad\x00path")` 不再抛 `ValueError`（Windows 路径语义差异）；
2. `test_curriculum_docx_reader.py::test_duplicate_or_unsafe_archive_members_are_rejected[word\\DEMO-PRIVATE-PART]`
   —— Windows 上 ZIP 成员名中的字面反斜杠语义差异。

两者都不涉本轮改动文件，本轮也**未**修改这两处实现或测试。

### 6.3 本轮新增覆盖的验收用例

| 验收要求 | 对应测试 |
| --- | --- |
| 同一目标方案 + 两份独立输入 → 基于真实输入差异的不同状态（断言具体原因） | `test_personal_planning.py::test_two_independent_students_get_different_states_with_specific_reasons`、`test_personal_planning_api.py::test_two_students_get_different_results_through_the_api` |
| 切换版本 / 成绩后旧结果、他人确认不可错用 | `test_result_never_inherits_another_students_satisfied_state`、`test_recognition_requires_this_students_own_evidence`、`test_rules_cannot_belong_to_another_completed_source`、`test_declared_source_mismatch_is_rejected`、`test_each_student_sees_only_their_own_records` |
| 不支持版本 / 未核验规则 明确拒绝 | `test_unknown_version_is_rejected_without_falling_back_to_case_a`、`test_unverified_version_is_not_selectable`、`test_version_the_source_declares_unsupported_is_not_selectable`、`test_same_version_id_declared_twice_is_not_selectable`、`test_unsupported_artifact_format_is_not_parsed`、`test_missing_catalog_is_empty_not_an_error` |
| 空 / 错误输入 明确拒绝 | `test_empty_student_input_is_not_silently_treated_as_complete`、`test_unknown_input_fields_are_rejected`、`test_source_and_target_must_be_two_different_versions`、`test_incomplete_target_curriculum_is_rejected_at_projection`、`test_planning_skipped_reason_is_explicit_without_course_data`、`test_planner_and_offerings_must_be_given_together` |
| 模糊成绩 / 未知等价 留待核验 | `test_recognition_with_insufficient_credit_stays_pending`、`test_ambiguous_identity_stays_pending_not_required`、`test_failed_attempt_only_is_not_satisfied` |
| 两门新增彼此冲突 | `test_planner_credit_limit.py::test_two_mutually_conflicting_additions_are_not_accepted`、`test_conflicting_addition_order_does_not_change_the_result` |
| 周次不重叠 | `test_disjoint_weeks_are_not_a_conflict`、`test_overlapping_weeks_are_a_conflict` |
| 超学分上限 | `test_total_credit_over_the_declared_limit_is_not_accepted`、`test_cumulative_additions_respect_the_limit_together`、`test_total_credit_at_the_declared_limit_is_accepted`、`test_missing_credit_declaration_makes_the_limit_unverifiable` |
| 原课表已超限 | `test_already_over_limit_current_schedule_is_reported_not_rewritten`、`test_over_limit_current_schedule_does_not_block_an_independent_proof` |
| 重复添加 | `test_duplicate_task_is_rejected`、`test_duplicate_offering_identity_is_rejected`、`test_already_selected_course_is_never_added_twice`、`test_duplicate_planning_assumptions_are_rejected` |
| 完整集合校验（不只与当前课表比） | `test_joint_selection_is_always_conflict_free` |
| 规划假设不改变状态 | `test_planning_assumption_never_changes_a_status`、`test_planning_assumption_on_unrelated_course_is_reported` |
| 旧 Case A 不回归 | 全量后端回归（3045 passed，除上述 2 项既有环境失败）+ `test_real_plan_api.py` / `test_planning_runtime.py` / `test_synthetic_production_e2e.py` 全绿 |
| `/api/v1/plan` 契约未变 | `test_personal_planning_api.py::test_plan_endpoint_does_not_touch_the_frozen_plan_contract`、`test_integration_orchestrator.py` 全绿 |

### 6.4 未运行的测试（如实记录）

- **前端 Vitest / build 未运行**：worktree 内没有 `frontend/node_modules`（未安装依赖），
  本轮也**未修改任何前端文件**。因此前端无回归风险，但也没有本轮前端验证证据。
- 真实数据链路测试：**BLOCKED**（见 §8）。

---

## 7. 未完成 / 阻塞

### 【BLOCKED 1】真实已核验培养方案目录

```text
阻塞原因：APP_PERSONAL_CATALOG_DIR 指向的真实已核验目录不存在于仓库，也未交接。
已经确认：目录 artifact 格式与 fail-closed 规则已实现并有测试锁定（内部声明，非公共 Schema）。
无法确认：哪些真实版本算"已核验"、由谁核验、核验依据的具体形式；
          版本元信息里的 campus / track 对真实方案应如何取值。
需要人工提供：由负责人产出的已核验目录 artifact（含逐条 verification.evidence），
              或批准一个产出该 artifact 的工具流程。
在确认前不会修改：不自行批准任何版本、不把未核验方案设为可选、不用 mock_data 冒充真实目录。
```

### 【BLOCKED 2】第二位学生的真实脱敏成绩记录

```text
阻塞原因：第二位学生的经授权脱敏成绩记录未交接。
已经确认：个人入口已能对任意一份本人输入独立计算，且有两位 Mock 学生的差异断言。
无法确认：真实成绩单的字段取值与身份确认依据。
需要人工提供：第二份经授权脱敏成绩记录（或明确说明本轮不做真实第二人验证）。
在确认前不会修改：不编造第二位学生数据、不用第一位学生的结论填充第二人。
```

### 【BLOCKED 3】`max_credit` 语义与 Planner 接纳口径

```text
阻塞原因：把 Preference.max_credit 变成"对 原课表 + 累计新增 的确定性接纳判断"
          属于行为变更；信用额度模型（哪些课计入本学期、是否含重修学分）无正式来源。
已经确认：任务书明确要求"防止…总学分上限越界被错误接纳"；
          实现只消费**学生本人显式声明**的公共 Preference 字段，
          ⛔ 未新增 Schema 字段、⛔ 未修改学校规则或优化目标。
无法确认：该校"本学期学分上限"的正式计算口径。
需要人工提供：负责人对该口径的裁决（若口径不同，只需替换 credit_limit 的统计输入）。
在确认前不会修改：⛔ 不发明上限、⛔ 不在无声明时启用该判断、
                  ⛔ 不据此改变学业优先级或必修要求。
```

### 【BLOCKED 4】新 API 路径的正式批准

```text
阻塞原因：/api/v1/personal-planning/* 是新公开路径，属"公共输入输出"范畴。
已经确认：实现是独立文件 + main.py 一行注册；有路由白名单测试显式登记；
          ⛔ 未改动任何现有路由。
无法确认：负责人是否接受该路径命名与暴露方式。
需要人工提供：路径命名 / 是否改为内部调用（不入 OpenAPI）的裁决。
在确认前不会修改：不扩张到更多路径，也不改动 /api/v1/plan。
```

### 未做（有意延后，非阻塞）

| 项 | 原因 |
| --- | --- |
| **前端最小接入** | 共享入口 `frontend/src/App.vue`（432 行）与 Agent B 的解释 UI 冲突风险高；本轮只做后端 + 联调说明（见设计文档 §5）。⛔ 未添加任何假动态效果。 |
| **课表图片 OCR** | 任务书列为 **P2 延后**；本轮不抢占 P0/P1，也⛔ 不以假 OCR 冒充 AI。 |
| 数据库 | 任务书要求首期不新增数据库；目录是本地只读 artifact。 |

---

## 8. 已知问题

1. **真实数据验证未完成** —— 全部结论仅来自人工构造 Mock。
2. **Planner 学分上限是行为变更** —— 已同步 `docs/status/planner.md` 并标注"待 Reviewer 确认"；
   影响 2 处既有测试的断言口径（已在 §6.2 与文件清单中逐条说明，⛔ 没有为了让测试变绿而放宽断言）。
3. **目录 artifact 格式是内部声明** —— `catalog_version` / `verification` 等字段
   尚未进入 `/schemas/` / `/docs/interfaces/`；是否作为长期内部格式保留需 Reviewer 决定。
4. **`unverifiable` 不是"通过"** —— 有课程没有学分声明时，Planner 仍会列出唯一 CLEAR 新增，
   但会明确说明"未认证其学分合规性"，且 `unresolved` 里有 `manual_confirmation`。
   这是**有意的保守**，不是遗漏。
5. **前端未验证**（无 `node_modules`，且本轮未改前端）。
6. **2 项基线既有失败** 仍在（见 §6.2），⛔ 本轮未修（它们不在本任务范围内，
   且修 Windows 路径/ZIP 语义属于其他模块的既有实现口径）。

---

## 9. 需要人工确认

1. `APP_PERSONAL_CATALOG_DIR` 的真实目录内容与产出来源（**BLOCKED 1**）。
2. 第二位学生的真实脱敏成绩记录（**BLOCKED 2**）。
3. `Preference.max_credit` 的正式计算口径与是否应影响 Planner 接纳（**BLOCKED 3**）。
4. `/api/v1/personal-planning/*` 路径命名与暴露方式（**BLOCKED 4**）。
5. 目录 artifact 字段是否作为长期内部格式保留。
6. 是否批准把"个人规划入口"接入前端（需与 Agent B 协调共享入口改动）。

---

## 10. 其他成员需要注意

- **Agent B（解释服务）**：本轮**未**编辑 `frontend/**`、
  **未**新建任何解释服务或解释 UI 文件，也**未**修改任何解释相关入口。
  个人规划结果为解释服务预留了稳定载体：`version` 元信息（含来源与核验依据）、
  `MakeupTask[].reason` / `source_evidence`、`planning_skipped_code` 与 `notes`。
- **共享文件冲突面**：本轮只改了 `backend/app/main.py` 的 **2 行**
  （1 行 import + 1 行 `include_router`），是两份分支上最可能冲突的位置；
  如与 B 的分支冲突，请按"各自保留自己的 `include_router` 行"合并，⛔ 不要删除任何一条。
- **Planner 口径**：`max_credit` 现在会影响新增接纳（**行为变更**）。
  任何依赖"声明了上限也照样新增"的既有假设都需要更新。
- **Curriculum**：`app/curriculum/catalog.py` 是**新增只读**模块，
  ⛔ 未修改 `requirements.py` / `matching.py` / `case.py` / `terms.py` 的任何行为。
- **Case A**：完全未触碰。旧 Case A 的 case 文件、decisions、runtime、API 一字未改。

---

## 11. 建议下一步

1. 项目 Reviewer 审核本分支（重点：§1.7 的行为变更、§3 的契约表、§8 的已知问题）。
2. 负责人裁决 **BLOCKED 1 / 3 / 4**；其中 3 会直接改变 Planner 输出，建议优先。
3. 若裁决通过：提供已核验目录 artifact → 用真实方案替换 Mock 目录跑一次
   `GET curriculum-versions`；再接入前端（与 B 协调共享入口）。
4. 提供第二位学生脱敏成绩后，把 §6.1 的演示脚本换成真实输入再跑一次，
   并在 `docs/e2e/` 记录证据（遵守 `REAL_E2E_EVIDENCE_PROTOCOL.md`）。
5. 前端最小接入建议按**独立组件 + 独立路由/面板**方式做，
   避免修改 `App.vue` 的共享结构；本轮未做，也未留下半成品。
