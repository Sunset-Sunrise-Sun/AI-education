# Integration 当前状态

> 最后更新：2026-10-05

## 当前能力

- `PlanningOrchestrator` 继续只按 Curriculum → Course Data → Planner 顺序编排；
- 新增真实规划入口 `POST /api/v1/plan`，请求复用公共 `CourseOffering` 与 `Preference` 模型，成功响应为 `PlanResult`；
- production runtime factory 已完成：显式装配已有的 `CurriculumCaseProvider`、`SnapshotCourseDataProvider` 与 `RestrictedPlannerProvider`；
- runtime 默认关闭，只有 `APP_REAL_CASE_A_ENABLED=1` 且显式提供 Case A manifest、完整 CourseOffering Capture Bundle 与真实 source 标识时才启用；缺任一输入或输入不合法均 fail closed；
- Curriculum runtime 会核验 Real 标记、Case A target version、`as_of_term=2025-2` 与已批准的 scope decisions；Course Data runtime 只接受已有证据链判为 `complete` 的 snapshot；
- 仓库当前没有完整 2026-1 CourseOffering snapshot，因此默认真实入口仍明确返回 `503 real_pipeline_not_configured`；内部诊断为 `course_data_not_ready`（显式启用且 Curriculum 已就绪时）；
- 真实入口不引用 `mock_service`，Provider 运行期异常不被吞掉，也不会回退到 Mock；
- 永久 Mock 通道仍为 `/api/v1/mock/*`，只有该路径携带 `X-Data-Source: mock`。

## Real E2E acceptance criteria prepared

- 已新增验收文档包 `docs/e2e/`：`REAL_CASE_A_ACCEPTANCE.md`（正式定义 + 等级）、
  `COURSE_DATA_SNAPSHOT_CHECKLIST.md`（快照清单 + provenance OPEN ITEM）、
  `REAL_E2E_TEST_MATRIX.md`（验收矩阵）、`DEMO_RUNBOOK.md`（演示手册）；
- 定义了「Real Case A E2E PASSED」必须**同时**满足的 10 条条件，
  以及四档验收等级（LEVEL 0–3）；
- **当前状态：`LEVEL 0 on main`** —— 真实入口仍返回 503 `real_pipeline_not_configured`。

## 当前边界

- 未修改 `/schemas/`、frozen Provider contract 或 `PlanningOrchestrator`；
- 未实现 Curriculum、Course Data 或 Planner 业务算法；
- 未接入真实教务网络、XLSX 上传或学生身份信息；
- runtime 不扫描目录、不猜本地路径、不打印输入内容，不接受 partial snapshot，也不使用 Mock fallback；
- Runtime wiring 已完成；完整 Real Case A E2E 仍被 complete 2026-1 CourseOffering snapshot 阻塞。

## 下一步

- 由 Architecture Reviewer 审查 runtime 配置边界；
- 取得并审核完整 2026-1 Capture Bundle 后，以仓库外显式路径进行真实 Case A E2E 验收。
