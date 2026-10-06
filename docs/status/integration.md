# Integration 当前状态

> 最后更新：2026-10-06

## 当前能力

- `PlanningOrchestrator` 继续只按 Curriculum → Course Data → Planner 顺序编排；
- 新增真实规划入口 `POST /api/v1/plan`，请求复用公共 `CourseOffering` 与 `Preference` 模型，成功响应为 `PlanResult`；
- production Provider 尚未在**当前部署**中装配（没有任何受控输入被提供），因此真实入口明确返回
  `503 real_pipeline_not_configured`；
- 真实入口不引用 `mock_service`，Provider 运行期异常不被吞掉，也不会回退到 Mock；
- 永久 Mock 通道仍为 `/api/v1/mock/*`，只有该路径携带 `X-Data-Source: mock`。

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
