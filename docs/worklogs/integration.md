# Integration 工作日志

### 2026-10-05 - Real Integration API 骨架

- 从 `main@0eaa6c0b6348e43533255484b496a7bcbcd67d79` 创建 `feature/real-plan-api`；
- 新增 API 私有 `PlanRequest`：仅包含 `semester`、`current_schedule`、`preference`，其中后两者复用公共模型；
- 新增 `POST /api/v1/plan`，成功时直接返回 `PlanningOrchestrator.build_plan(...)`；
- 新增 `get_planning_orchestrator()` production wiring seam；当前未注册真实 Provider，API 返回明确的 503，错误码为 `real_pipeline_not_configured`；
- Provider 的其它异常继续上抛，不转成 200，不回放 Mock `PlanResult`；
- 修正全局 Mock header：只对 `/api/v1/mock/*` 添加 `X-Data-Source: mock`，真实入口和健康检查不再被错误标记；
- 新增真实 API 测试，覆盖路由存在、503、422、Mock/Real 隔离、Fake Provider 调用顺序与次数、参数透明传递、结果内容不改写、Provider 异常无 fallback；
- 保持 `/api/v1/mock/demo` 行为不变；
- 未修改 `backend/app/curriculum/**`、`backend/app/planner/**`、`backend/app/course_data/**`、`schemas/**`、公共契约模型或前端。

测试记录：

- 最终相关回归：50 passed；`python -m compileall -q app` 通过；
- 首次全量回归：2016 passed / 2 skipped / 15 failed；失败均位于 Curriculum 既有测试，原因是 Windows 默认 GBK、Windows ZIP 路径行为及当前仓库绝对路径包含 `-1`，与本轮修改无关；后续以 UTF-8 模式再次复核。
- UTF-8 全量复核：2030 passed / 2 skipped / 2 failed；剩余两项均为 Curriculum 既有 Windows 环境问题：ZIP 成员反斜杠安全断言未触发，以及仓库目录日期 `2026-10-05` 令“异常文本不得含 `-1`”断言误命中。按任务边界未修改 `backend/app/curriculum/**`。

### 2026-10-05 - Rebase 与 Mock 启动耦合修复

- 已 rebase 到 `main@1a740b2d960bb4bb78771d56aa1ec9f0424a12e1`；rebase 后首次全量回归为 **2043 passed / 2 skipped / 2 failed**；两项失败仍是既有 Curriculum Windows 环境问题。
- 去除 FastAPI 启动时读取全部 Mock 文件的全局耦合；Mock 数据损坏不再阻断 `/health` 或 `/api/v1/plan`。
- Mock endpoint 调用时仍按公共 Schema + Pydantic 严格校验；损坏时返回明确的 `500 mock_data_invalid`，不返回部分数据、不 fallback。
- 新增回归测试：注入损坏 Mock 后应用仍可启动、health 正常、已装配 Fake Real pipeline 正常返回原始 `PlanResult`、`/api/v1/mock/demo` 明确失败。
- 未修改 Curriculum / Planner / Course Data / Schema / Frontend。
- 修复后验证：targeted **51 passed**；全量 backend **2044 passed / 2 skipped / 2 failed**。两项失败与 rebase 后首次全量回归相同，均为既有 Curriculum Windows 环境问题，本轮未越界修改。

### 2026-10-05 - Real Plan current_schedule provenance Gate

- 在 API 私有 `PlanRequest` 增加来源校验：`current_schedule=[]` 合法；非空时每个 `CourseOffering.data_source` 必须明确为 `real`。
- 显式 `mock` 被拒绝；缺失 `data_source` 时公共模型会采用默认值 `mock`，随后同样由 Real API 边界返回 422。
- 校验只约束 Real HTTP 输入，不修改 Planner 算法、frozen Provider contract 或公共 Schema。
- 验证：targeted **55 passed**；全量 backend **2048 passed / 2 skipped / 2 failed**。两项失败仍为既有 Curriculum Windows 环境问题。

### 2026-10-05 - Case A production runtime wiring

- 从 `main@d7e17eedcf8d25c20b8a31e01a2e3ec3711ec32f` 创建 `feature/case-a-runtime-wiring`。
- Provider 盘点：Curriculum 可直接使用 `CurriculumCaseProvider` + 仓库外显式 case manifest；Course Data 可直接使用 `SnapshotCourseDataProvider` + Capture Bridge；Planner 可直接使用 `RestrictedPlannerProvider`。实现均为 production-capable，但真实输入工件的 readiness 独立判定。
- 将 `planning_runtime.py` 扩展为默认关闭、显式配置、可诊断的 factory。配置项为 `APP_REAL_CASE_A_ENABLED`、`APP_CASE_A_CURRICULUM_CASE_PATH`、`APP_COURSE_SNAPSHOT_PATH`、`APP_COURSE_SNAPSHOT_SOURCE`；不提供默认路径，不扫描文件系统。
- Curriculum 只接受 `data_source=real`、Case A target version、`as_of_term=2025-2` 及仓库内已批准 scope decisions，并在装配时验证 `get_makeup_tasks()` 可投影；没有手写 23 条任务或状态统计。
- Course Data 复用 Capture Bridge 与分页 completeness 证据链；只有 `snapshot.is_complete` 才构造 Provider。partial、损坏、缺失或 Mock source 均返回内部 `course_data_not_ready`，不进入 Planner。
- Planner 直接实例化现有 deterministic `RestrictedPlannerProvider`；未新增算法、偏好执行语义或约束。
- API 外部契约不变：runtime unavailable 仍为 `503 real_pipeline_not_configured`；三类 Provider 均就绪时沿既有 `PlanningOrchestrator` 返回 `PlanResult`；无 Mock fallback。
- 新增测试使用人工 source-shaped 本地工件，覆盖默认关闭、缺失 Curriculum、缺失/partial Course Data、损坏输入、Mock 拒绝、非法 enable 配置、真实 Provider identity、production dependency 到 API 的 200 路径及 503 路径。测试工件不是 Real Case A 数据。
- 验证：targeted **358 passed**；`python -m compileall -q app` 通过；全量 backend **2059 passed / 2 skipped / 2 failed**。两项失败与基线相同，均为既有 Curriculum Windows 环境差异（ZIP 反斜杠成员、当前绝对路径日期含 `-1`），本轮未修改 Curriculum。
- Runtime wiring complete；仓库当前只有两页 partial 采集证据，没有 complete 2026-1 CourseOffering snapshot，因此 **完整 Real Case A E2E 仍被该 snapshot 阻塞，未宣称 REAL E2E PASSED**。

### 2026-10-05 - Approved exact-artifact SHA-256 gate

- 保留原始 wiring 的备份分支 `backup/case-a-runtime-wiring-3458d0a`，并将工作分支从原始 `3458d0a` 无冲突 rebase 到 `main@21f558f26b34602a97212d3be4055d28a62f0295`；Acceptance Pack 口径优先。
- 修复已确认的 provenance 缺陷：`APP_COURSE_SNAPSHOT_SOURCE` 不再被当作信任证明，只保留为审计标签与 `CourseOffering.source`；新增 `APP_COURSE_SNAPSHOT_SHA256` 作为人工批准的 exact-artifact digest。
- Runtime 对 `APP_COURSE_SNAPSHOT_PATH` 指向文件的**原始 bytes**计算 SHA-256，并用同一次读取的 bytes 解析 Capture Bundle；digest 缺失、文件不可读、digest mismatch、bundle 非法、学期非 2026-1、partial 或空 snapshot、source 标签非法，均 fail closed，不装配 Course Data Provider。
- SHA-256 只接受 64 位十六进制，比较前统一为小写（大小写输入均可）；格式非法归 `invalid_runtime_configuration`，工件不可用归 `course_data_not_ready`。外部 API 仍保持 `503 real_pipeline_not_configured`。
- Gate 防止未被批准的任意工件替换，但 **digest 本身不证明文件最初来自何种采集过程**；真实 complete snapshot 与正式 approved digest 尚未产生，未写入任何生产默认值。
- 使用动态生成的 synthetic fixture digest 只验证 LEVEL 1 wiring capability；正式项目状态仍为 **LEVEL 0 on main**，不声明 Real E2E passed。
- 验证：runtime/API/Integration targeted **53 passed**（其中 Real Plan API **16 passed**）；`python -m compileall -q app` 通过；全量 backend **2071 passed / 2 skipped / 2 failed**。两项失败均为既有 Windows Curriculum 基线差异（ZIP 反斜杠成员、当前绝对路径日期含 `-1`），本轮未修改 Curriculum。
