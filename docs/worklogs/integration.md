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

### 2026-10-06 - Gate C：Case A runtime wiring（PR #39 successor）

- **分支**：基于 Gate B tip 新建 `feature/case-a-runtime-wiring-store`（stacked；
  ⛔ 未 merge main、⛔ 未 merge PR #39 —— 旧分支只 fetch 作参考）；
- **取代 PR #39 的装载模型**：single Capture Bundle + raw bytes digest + 内存快照
  → SQLite + **显式 full_semester acceptance 绑定**
  （`campus complete != full semester complete`，单 bundle 会静默不完整）；
  ⛔ PR #39 = FROZEN / DO NOT MERGE，只在文档中标记 **superseded**；
- **环境契约（五个变量）**：`APP_REAL_CASE_A_ENABLED` /
  `APP_CASE_A_CURRICULUM_CASE_PATH` / `APP_COURSE_DATA_SQLITE_PATH` /
  `APP_COURSE_DATA_SEMESTER` / `APP_COURSE_DATA_ACCEPTANCE_SHA256`；
  ⛔ 不存在单 bundle 的旧变量名，⛔ 无 campus / Mock / "有行就启动" 退化路径；
- **装配**：`build_planning_runtime(environment)` 返回
  `PlanningRuntimeInspection(orchestrator, reason)`；reason ∈
  `runtime_disabled` / `invalid_runtime_configuration` / `curriculum_not_ready` /
  `course_data_not_ready` / `ready`（⛔ 不含路径与配置取值）；
  Curriculum 侧沿用同一套受控校验（real / case-a-new / as_of_term=2025-2 /
  已批准决策集合 / 构造期 projection 成功）；
  Course Data 侧全部交由 `StoreBackedCourseDataProvider` 构造期 fail closed；
- **每请求重新装配**（不缓存 orchestrator）⇒ 启动之后被改写的库会被发现并 fail closed；
- **API 行为不变**：未装配 ⇒ `503 real_pipeline_not_configured` 且不带 `X-Data-Source`；
  已装配 ⇒ 200 + `PlanResult`（公共 Schema 通过）；上抛异常仍不被吞；
  ⛔ 未给真实 API 增加 `X-Data-Source: real`（接口面变更仍需裁定）；
- **测试**：`test_planning_runtime.py` **47 passed**（synthetic / zero-network，含
  开关值矩阵、缺配置、非法 digest、大写 digest、case 四类受控校验的**逐个隔离**用例、
  库缺失 / 非 Course Data 库 / campus-only 库 / 错 digest / 错 semester、
  ready 装配、planner 收到恰好绑定行、启动后库被改写 ⇒ fail closed、
  真实 endpoint 503 与 200、mock 通道仍标记、源码级无 Mock / 无快照 Provider / 无网络 import）；
  相关回归（real plan api + mock api + orchestrator + planner provider + runtime）**307 passed**；
- **mutation sweep**（workspace-only `mutate_planning_runtime.py`，17 处唯一锚点、
  按字节还原核对）：**16 killed / 1 可证等价 / 0 survived**；
  等价项 = "版本必须等于 Case A 目标版本"，冗余性由测试证明
  （已批准决策绑定在 `case-a-new`，换版本后 Curriculum 层自身拒绝）；
- **边界**：⛔ 未改 frozen Provider Protocol / public Schema / `PlanningOrchestrator`、
  ⛔ 未 merge main 或 PR #39、⛔ 未真实登录、⛔ 未发真实教务请求、⛔ 未处理真实 artifact；
  formal Real E2E 继续 **LEVEL0**。

### 2026-10-06 - Runtime BLOCK：异常边界收窄（只有显式领域失败才是 503）

- **BLOCK（Codex 独立 probe）**：构造期无关 `ValueError` 被
  `build_planning_runtime()` 的 `except (CourseDataStoreError, OSError, ValueError)` /
  `except (CurriculumNormalizationError, OSError, ValueError, _RuntimeSourceUnavailable)`
  吞掉 ⇒ 变成 `503 real_pipeline_not_configured`（程序缺陷伪装成"未配置"）；
- **修复**：Curriculum 侧只捕 `(CurriculumNormalizationError, _RuntimeSourceUnavailable)`，
  Course Data 侧只捕 `CourseDataStoreError`（含 `CourseDataAcceptanceError` /
  `ImmutableAcceptanceConflictError`）；理由：case loader / store 各自**已经**在自己
  的边界内把 `OSError` / `ValueError` / `RuntimeError` 规范化成领域异常，
  这里再捕泛型只会吞掉缺陷；⛔ 不捕 `Exception` / `RuntimeError` / 裸 `except:`；
  ⛔ 未改 public Schema / frozen Provider contract / `PlanningOrchestrator`；
- **11 个 probe（真实 dependency + 真实 endpoint + 真实 HTTP 状态码）**：
  ①缺库 ②缺 acceptance ③错 SHA ④campus-only ⑤显式 `CourseDataAcceptanceError`
  ⇒ **503**；⑥Provider 构造器无关 `ValueError` ⑦无关 `RuntimeError`
  ⑧构造链程序缺陷（planner factory / orchestrator / curriculum factory）
  ⇒ **500**；⑨正常链路 ⇒ **200**；⑩构造成功后 acceptance 被删 ⇒ 请求期 **503**；
  ⑪请求期无关内部异常（provider / planner）⇒ **500**；
- **精确分类证明**：`ValueError` / `RuntimeError` / `KeyError` / `AttributeError` /
  `TypeError` / `OSError` / `ZeroDivisionError` 在两个构造边界上**逐类型**
  `pytest.raises` 冒泡；`CourseDataStoreError` / `CourseDataAcceptanceError` /
  `ImmutableAcceptanceConflictError` ⇒ `course_data_not_ready`；
  `CurriculumNormalizationError` ⇒ `curriculum_not_ready`；
  结构层 AST 断言模块内每个 `except` 目标 ∈ 显式白名单（4 个名字）；
- **修复前复现**（`eb135a8`）：`test_probe_06…` ⇒ 实际响应
  `503 {"detail":{"error":"real_pipeline_not_configured"}}`，
  `6 failed / 76 passed`；修复后同文件 **82 passed**；
- **边界**：⛔ 未 merge main、⛔ 未改 Provider store 语义（PROVIDER GATE: PASS）、
  ⛔ 未处理真实 artifact；Gate E / F / G 继续 parked。

### 2026-10-07 - Case A nightly scoped closed-loop integration

- 从 `main@c75b6da` 集成已 Review 的 PDF transcript 与 Case A 南+深圳 scoped provider，
  新增与 production `/api/v1/plan` 完全分离的 `/api/v1/case-a-demo/*`；
- combined plan 请求携带 PDF bytes（Base64）、current_schedule、manual attestation 与
  Preference；服务端重新验证 accepted offering 或明确 student-attested manual source；
- PDF 内容摘要成为新的 completed source；旧 XLSX source-bound rules / recognition /
  missing decisions 全部清空，不发明 `pdf:N` 映射；scope/elective/priority case facts保留；
- Course Data 必须由显式 SQLite、semester、South/SZ exact acceptance SHA 配置构造；
  缺任一项即 503，不 fallback Mock/Synthetic；公开 provenance 为
  `case-scoped:south+shenzhen` 且 `is_full_semester=false`；
- synthetic E2E 覆盖完整编排、pending course IDs、manual attestation、DG-07 UNKNOWN、
  selected_classes recommendation 与无 Mock fallback；前端独立页面只渲染同一次运行上下文。
