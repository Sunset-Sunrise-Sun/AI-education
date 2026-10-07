# Integration 当前状态

> 最后更新：2026-10-06
>
> ⚠️ **关于 `PROJECT_CONTEXT.md`**：外部 review 指令会要求先读 `/PROJECT_CONTEXT.md`，
> 但该文件**不在本仓库中**（`git ls-files` 无此文件，仓库内也没有任何文件引用它）。
> ⛔ 不要为了满足一份检查清单而**编造**一份项目背景文档；
> 本仓库的背景事实以 `/AGENTS.md`、`/docs/ARCHITECTURE.md`、
> `/docs/status/*.md` 与 `/docs/worklogs/*.md` 为准。
> 如果确实需要 `PROJECT_CONTEXT.md`，应由负责人提供其内容。

## 当前能力

- `PlanningOrchestrator` 继续只按 Curriculum → Course Data → Planner 顺序编排；
- 新增真实规划入口 `POST /api/v1/plan`，请求复用公共 `CourseOffering` 与 `Preference` 模型，成功响应为 `PlanResult`；
- production Provider 尚未在**当前部署**中装配（没有任何受控输入被提供），因此真实入口明确返回
  `503 real_pipeline_not_configured`；
- 真实入口不引用 `mock_service`，Provider 运行期异常不被吞掉，也不会回退到 Mock；
- 永久 Mock 通道仍为 `/api/v1/mock/*`，只有该路径携带 `X-Data-Source: mock`。

## 教师信息：TEACHER ENRICHMENT = BLOCKED_BY_MISSING_LOCAL_RAW_SOURCE

人工验收看到页面大量「任课教师：待核验」。**本机现有的原始 Course Data 里没有教师姓名**，
因此**不可能**在不抓新数据的前提下恢复教师。审计证据（`_caseA-validation/`，⛔ 不入库）：

```text
south-campus.json     2898 rows | row keys = classNumber, courseName, courseNum,
shenzhen-campus.json  1171 rows |            limitNumber, score, selectedNumber,
                                             teachingTimePlaceStr, yearTerm
两文件合计 4069 rows：携带 teachingName 字段的行 = 0；非空 teachingName = 0
teachingTimePlaceStr 解析出 12011 个 segment：教师段为 REDACTED 的 = 0
```

即：采集器的字段最小化白名单**根本不含 `teachingName`**，
而 `teachingTimePlaceStr` 里的教师段在**保存前**就已按设计剥离
（不是脱敏标记，是直接不存在）。
⚠️ 唯一可能拿到教师姓名的路径是**再次访问实时教务接口**，⛔ 本轮不做。

结论：教师展示本轮**不伪造、不推断**；页面改用中性文案「教师信息暂未同步」，
并把「待核验」留给真正影响决策的状态（例如排课信息缺失）。

## Case A production runtime wiring（Gate C，✅ 已实现）

- `backend/app/services/planning_runtime.py` 现在是**环境驱动、fail closed** 的装配边界：

  ```text
  APP_REAL_CASE_A_ENABLED=1
  APP_CASE_A_CURRICULUM_CASE_PATH=<real Case A case JSON>
  APP_COURSE_DATA_SQLITE_PATH=<local SQLite>
  APP_COURSE_DATA_SEMESTER=<acceptance 绑定的学期>
  APP_COURSE_DATA_ACCEPTANCE_SHA256=<full-semester manifest SHA-256>
        → CurriculumCaseProvider + StoreBackedCourseDataProvider + RestrictedPlannerProvider
        → PlanningOrchestrator；任一步不满足 ⇒ None ⇒ 503
  ```
- Course Data 侧从 PR #39 的**单 bundle + raw bytes digest + 内存快照**换成
  **SQLite + 显式 full_semester acceptance 绑定**（`campus complete != full semester complete`）；
  ⛔ **没有 campus fallback / Mock fallback / "有一些行就启动"**；
- ⛔ **PR #39 = FROZEN / DO NOT MERGE**（其装载模型已被取代，本 Gate 只在文档中标记 superseded）；
- 诊断码（`runtime_disabled` / `invalid_runtime_configuration` / `curriculum_not_ready` /
  `course_data_not_ready` / `ready`）**不含路径与配置取值**；
- 每次请求重新装配（不缓存 orchestrator）⇒ 启动之后的库改写会被发现并 fail closed；
- ⛔ 未改三个 frozen Provider Protocol、⛔ 未改 `PlanningOrchestrator`、⛔ 未改 public Schema；
- ⛔ 未给真实 API 增加 `X-Data-Source: real`（仍待裁定）；
- 使用说明：`docs/data/CASE_A_RUNTIME_WIRING.md`。

## Runtime 异常边界收窄（Codex BLOCK，✅ 已修）

- **BLOCK**：构造期一个**无关的 `ValueError`**（例如 Provider 构造器内部程序缺陷）
  被 `build_planning_runtime()` 的 `except (CourseDataStoreError, OSError, ValueError)`
  吞掉 ⇒ 伪装成"未装配" ⇒ `503 real_pipeline_not_configured`。程序缺陷必须 **500**；
- **修复**：只捕获**显式领域异常**（⛔ 不捕 `ValueError` / `RuntimeError` / `OSError` /
  `Exception` / 裸 `except:`）：

  ```text
  503 real_pipeline_not_configured
      _RuntimeSourceUnavailable · _RuntimeConfigurationInvalid
      CurriculumNormalizationError            （loader 已把 OSError/ValueError/RuntimeError 规范化）
      CourseDataStoreError
        ├── CourseDataAcceptanceError
        └── ImmutableAcceptanceConflictError
  500（原样冒出，FastAPI 默认处理）
      ValueError · RuntimeError（非上述类型）· KeyError · AttributeError · TypeError · OSError …
  ```
- **11 个 probe 全部走真实 dependency + 真实 `POST /api/v1/plan` 并断言真实 HTTP 状态码**
  （缺库 / 缺 acceptance / 错 SHA / campus-only / 显式领域异常 ⇒ 503；
  无关 `ValueError` / `RuntimeError` / 构造期程序缺陷 ⇒ 500；正常链路 ⇒ 200；
  请求期 acceptance 失效 ⇒ 503；请求期无关内部异常 ⇒ 500）；
  另有**精确分类**证明：非领域异常在两个构造边界上**逐个类型**冒泡，
  领域异常（含 `ImmutableAcceptanceConflictError`）被分类成 `course_data_not_ready`；
  结构层用 AST 断言模块内**每一个** `except` 目标都在显式白名单内；
- `eb135a8`（修复前）上同一 probe 复现：`ValueError` ⇒ **503**（Codex 报告的 BLOCK）；
  修复后 ⇒ **500**；⛔ 未改 public Schema / frozen Provider contract / `PlanningOrchestrator`。

## Real E2E acceptance criteria prepared

- 已新增验收文档包 `docs/e2e/`：`REAL_CASE_A_ACCEPTANCE.md`（正式定义 + 等级）、
  `COURSE_DATA_SNAPSHOT_CHECKLIST.md`（快照清单 + provenance OPEN ITEM）、
  `REAL_E2E_TEST_MATRIX.md`（验收矩阵）、`DEMO_RUNBOOK.md`（演示手册）；
- 定义了「Real Case A E2E PASSED」必须**同时**满足的 10 条条件，
  以及四档验收等级（LEVEL 0–3）；
- **当前状态：`LEVEL 0`** —— 真实链路尚未用真实 artifact 跑通（North suspended + 需真实登录），
  因此真实入口在没有受控输入时仍返回 503 `real_pipeline_not_configured`。

## Case A 学业路径规划集成（✅ 已实现，待 Architecture Review）

**把 A（前端 Case A 规划 UX）与 B（Path Planner Core）真正接起来**，
形成一个**完整的课程级 + 教学班级闭环**。⛔ 未改任何 frozen 公共契约。

### 新增能力

| 能力 | 落点 |
|---|---|
| 未来学期**课程级**路线图 | `backend/app/services/case_a_roadmap.py`（接线层）+ `app/path_planner/future_roadmap.py` |
| 结构化**换班建议**（只生成） | `app/path_planner/repair_proposals.py`，由 `case_a_demo` 编排进响应 |
| **显式**换班确认接口 | `POST /api/v1/case-a-demo/repair/apply` |
| 加法式响应（⛔ 不动 `PlanResult`） | `app/api/case_a_demo.py` 新增 `repair_proposals` / `roadmap` / `roadmap_note` |
| 前端接线 | `PendingAdjustments.vue`（真实候选 + 采用/暂不调整）、`FutureRoadmapView.vue`（真实路线图 + 选修进度） |

### 关键设计（可与真实 artifact 对照）

- **培养方案学期号来源**：真实 Case A 培养方案**只有** `recommended_term_text`
  （如 `2027-1`），**没有** `recommended_semester` / `deadline_semester` 整数字段。
  因此学期号链由**培养方案自身出现过的学期标签**推导，
  以**当前学期**为参照（Case A：`2026-1` = 第 3 学期 ⇒ 未来 `2026-2`=4 … `2028-2`=8）。
  ⛔ **不存在"未来学期从 1 重新编号"**；纯标签序列**不给映射**时 fail closed。
- **已满足事实**：只采纳 `MakeupTask.status == satisfied`；
  `manual_confirmation` / `possibly_equivalent` **绝不提升**（并写入 `warnings`）；
  真实成绩单 PDF **没有官方课程号**，因此已满足事实**不依赖** `CompletedCourse.course_id`。
- **选修学分账**：最低学分读自 `CurriculumGroup.minimum_credit`（⛔ 无硬编码）；
  缺口 = `requirement − completed(已确认) − current(已确认)`；
  组外 satisfied 课程**不算**选修学分；已记账课程**不会**被再规划一次；
  ⛔ **不超额规划**。
- **换班**：`apply_repair_proposal()` 要求完整身份（semester / course_id / from / to），
  校验同一课程 + 同一学期 + `from` 在课表内 + `to` 在已接受教学班内 + 候选**重新**确认 CLEAR，
  应用后**重校验整份课表**；⛔ 生成建议时**绝不**自动应用，⛔ 不自动挑候选。

### 边界（⛔ 未越过）

- 未来学期**结构上不可能**出现 `class_id` / `teacher` / 时间 / 校区 / 教室 / 容量 / `meetings`
  （字段集由 `SemesterCoursePlan` 锁定 + API 层逐条断言 + 前端测试断言）；
- `app.path_planner` **不 import** `app.course_data`（AST 检查锁定）；
- ⛔ 未修改 `/schemas/`、`/docs/interfaces/`、frozen Provider Protocol、
  `RestrictedPlanner` 语义、`PlanningOrchestrator`；
- 路由白名单测试**逐条登记**了新增的 `repair/apply`（⛔ 不是"顺手多挂"）。

### 验证

```text
backend 定向回归：639 passed / 2 skipped
  （path planner / case-a roadmap / case-a demo e2e / case-a scoped scope /
    planner conflicts·provider·section_repair / planning runtime /
    integration orchestrator / contracts / real plan API）
backend 全量：与基线相同的 15 项 Windows 历史失败，无新增失败
frontend：233 passed / typecheck exit 0 / vite build 成功
真实 artifact smoke（私有、不入库）：4069 条真实教学班、23 条补修任务、
  选修账 23/0/0 ⇒ 缺口 23；未来学期 #4..#8；未来字段泄漏 = NONE
真实换班 smoke：跨课程替换被拒且课表不变；合法替换 applied=True 且 remaining_conflicts=[]
```

新增文档：`docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md`、
`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md`。

## 当前边界

### Case A scoped closed-loop demo（独立于 production runtime）

- 新增私有演示入口：`GET /api/v1/case-a-demo/offerings` 与
  `POST /api/v1/case-a-demo/plan`；后者把用户上传 PDF、当前课表与 Preference
  绑定在同一个无状态请求中，不保存学生身份信息；
- 装配为 PDF `CompletedCourse[]` → 动态 `CurriculumCaseProvider` →
  `CaseAScopedCourseDataProvider`（南+深圳 campus acceptance）→
  `RestrictedPlannerProvider`；旧 XLSX source-bound rules / recognitions / missing decisions
  不会自动重映射到 `pdf:N`；
- 来源明确标记 `case-scoped:south+shenzhen`，`is_full_semester=false`；
  ⛔ 不修改 production `build_course_data_provider()`，⛔ 不升级 formal Real E2E LEVEL0；
- 前端只有显式 `VITE_CASE_A_DEMO_ENABLED=true` 才进入独立页面；同一响应同时渲染
  MakeupTask、CourseOffering、Preference 与 PlanResult，不与 Mock 上半页混用。

- 未修改 `/schemas/`、frozen Provider contract 或 `PlanningOrchestrator`；
- 未实现 Curriculum、Course Data 或 Planner 业务算法；
- 未接入真实教务网络、XLSX 上传或学生身份信息；
- runtime wiring 只**消费**已经通过各自 Data Gate 的本地输入（真实 Case A case + 已验收的
  full_semester SQLite 记录）；⛔ 它自己不产生、不猜测、不下载任何数据。

## 下一步

- 由 Architecture Reviewer 审查本 Gate 分支（PR #39 按 superseded 处理，⛔ 不 merge）；
- 拿到真实五校区 artifact → 正式 full-semester acceptance → 配置五个环境变量 → 跑真实 Case A E2E
  （当前被 North suspended 阻塞）。
