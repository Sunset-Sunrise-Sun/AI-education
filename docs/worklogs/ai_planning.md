# AI Planning（DeepSeek Controller）工作日志

> 仅追加历史记录。新的 Agent 优先阅读 docs/status/ai_planning.md。

## 模板
### YYYY-MM-DD - 功能
- 本次目标：
- 已完成：
- 修改文件：
- 测试：
- 使用数据：Mock / Real
- 已知问题：
- 需要人工确认：
- 对其他模块影响：
- 下一步：

### 2026-10-08 - 新建 DeepSeek AI Planning Controller（分支 `feature/deepseek-planning-controller`）
- 本次目标：实现真实的 DeepSeek 意图解析 + 用户确认后的 Planner 调用 + 候选与二次确认采用；
  无密钥时用注入式假模型完成端到端测试，但**不得声称完成真实在线调用**。
- 已完成：
  - 新增隔离模块 `backend/app/ai_planning/`（config / errors / context / intent / minimize /
    deepseek_client / fake_model / service）与 4 条私有路由
    `backend/app/api/ai_planning.py`（status / interpret / solve / adopt）。
  - 新增 `backend/app/services/ai_planning_runtime.py`：进程内装配；
    **无密钥不构造真实客户端**，⛔ 也不内置假模型作为回退。
  - `backend/app/main.py` 只加 **2 行**（import 组 + `include_router`）。
  - DeepSeek 走 OpenAI 兼容 `/chat/completions`，`response_format=json_object`，
    仅用标准库 `urllib`（⛔ 未引入第三方依赖 / Agent 框架 / 数据库）。
  - 安全不变量：白名单外课程 / 教学班 ⇒ 拒绝整份草稿；"太累"不换算成学分数；
    硬约束必须带依据；未确认不求解；未二次确认不改方案；指纹变化即失效；
    模型调用次数有上限；会话进程内有界；命中 PII 直接 400 且不外发。
  - 候选只由冻结的四参数 `PlannerProvider.plan(...)` 产生，服务端再做确定性复核；
    差异与风险完全由后端计算。
- 修改文件：见 `docs/final_upgrade/reports/DEEPSEEK_CONTROLLER_REPORT.md` §2。
- 测试：新增 96 项（`test_ai_planning_service.py` 47 / `test_ai_planning_api.py` 22 /
  `test_ai_planning_client.py` 27）；后端全量 **3174 passed / 2 failed / 2 skipped**，
  2 项失败为既有 Windows 路径语义差异（基线同命令 3078 / 2 / 2）。
- 使用数据：**Mock**（合成教学班与补修任务）。
- 已知问题：真实在线调用 **NOT VERIFIED**（环境无密钥）；
  会话仅进程内；`exclude_course` 与跨学期调整明确 `blocked`；
  没有教学班输入时候选可能为空课表（已在 `diff.removed` / `risks` 中如实暴露）。
- 需要人工确认：是否引入会话持久化（属数据库结构变化）；
  是否扩展 Planner 以支持 exclude / 跨学期；是否接受新私有路由路径。
- 对其他模块影响：`main.py` 2 行（与 B 分支的共享冲突面）；
  `test_integration_orchestrator.py` 路由白名单新增 4 条。
  ⛔ 未改 `/schemas`、`/docs/interfaces`、`app/planner/**`、`app/curriculum/**`、
  `app/personal/**`、`app/explanation/**`、`app/integration/**`。
- 下一步：Reviewer 评审；运行方用新密钥做在线验证；B 按
  `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md` 实现前端三块 UI。

### 2026-10-09 - 前后端联合验收（分支 `feature/ai-planning-joint-e2e`，PR #67）
- 本次目标：在可执行环境里运行完整 backend pytest / frontend Vitest / TypeCheck / Build，
  用**真实 HTTP** 验证 AI 规划四接口闭环，修复集成引入的兼容性问题并补测试。
- 已完成：
  - 后端 `python -m pytest -q` → **3188 passed / 2 failed / 2 skipped**
    （基线同命令同环境 3174 / 2 / 2；2 项失败为既有 Windows 路径语义差异）。
  - 前端 `npm ci` → `npx vitest run` **274 passed / 0 failed**（18 文件）；
    `npx vue-tsc --noEmit` → exit 0；`npm run build` → exit 0。
  - 新增 `backend/tests/test_ai_planning_joint_e2e.py`（14 项）：
    用 **uvicorn 真实监听端口** + `urllib` 发真实 HTTP 请求，覆盖
    status / interpret / solve / adopt、两次确认、未确认不求解、拒绝候选、
    指纹过期、候选 TTL 过期、重复采用 409、模型不可用 503、
    无教学班（data_source=unknown）、PII 400、幻觉课程号 422、既有路由不受影响。
  - 新增 `frontend/tests/ai-planning-joint-contract-fix.spec.ts`（6 项）并修复两处真实形状错配：
    ① `diff.replaced[]` 的键是 `from_class` / `to_class`（⛔ 不是 `class_id`）——
       前端解析器与对比面板按 `class_id` 解析会在换班时抛 `ContractViolation` / 显示 undefined；
    ② `parsed_intent.locked_courses[].reason` 后端**可空** —— 前端原来会拒绝整份合法草稿。
    两者都先在未修复代码上验证失败（6 项里 4 项失败），再修复使 6 项全绿；⛔ 未放宽契约
    （非法形状仍然抛错，有测试锁定）。
  - 新增逐项报告 `docs/final_upgrade/reports/AI_PLANNING_JOINT_QA_REPORT.md`。
- 修改文件：`frontend/src/api/aiPlanningContract.ts`、
  `frontend/src/components/ai/CandidateComparePanel.vue`、
  新增 `backend/tests/test_ai_planning_joint_e2e.py`、
  新增 `frontend/tests/ai-planning-joint-contract-fix.spec.ts`、
  新增报告 + 更新本 STATUS/WORKLOG。⛔ 未改后端生产代码、⛔ 未改 `/schemas` 与 `/docs/interfaces`。
- 测试：见上；命令与原始计数见报告 §2 与 §3。
- 使用数据：**Mock**（合成教学班与补修任务）；⛔ 未使用真实学生隐私数据。
- 已知问题：真实 DeepSeek 在线调用 **NOT VERIFIED**（环境无密钥）；
  未做真实浏览器端到端；会话仅进程内；`no_feasible_candidate` 仍返回非空 `candidate_id`
  （前端不用它，建议后端后续在 HANDOFF 里写明语义）。
- 需要人工确认：是否引入会话持久化；是否扩展 Planner（exclude / 跨学期 / 可行子集搜索）；
  是否接受本分支以 Draft PR 呈现后再合并。
- 对其他模块影响：仅前端 AI 规划契约层与对比面板；后端、Schema、接口、其他模块均未改。
- 下一步：项目 Reviewer 验收；运行方在受控环境用**新密钥**做真实在线验证。

### 2026-10-09 - 真实能力接入第一阶段：DeepSeek 在线验收工具（分支 `feature/real-capability-readiness`）
- 本次目标：修复在线验收工具与文档、评估 DOCX→catalog 工具、加强真实数据隔离、跑可重复验收。
- 已完成（AI 规划部分）：
  - 从 `backend/app/api/ai_planning.py` 逐个 pydantic 模型提取真实契约（⛔ 不再照抄文档）。
  - 新增 `backend/tests/verify_deepseek_live.py`：默认离线 19 项检查全绿；在线模式双重开关；
    密钥只读进程环境且不落盘；无密钥时退出码 3 + BLOCKED。
  - 修正 `DEEPSEEK_LIVE_VERIFICATION.md` 中与实现不一致的 `/solve` / `/adopt` 示例与验收标准。
- 修改文件：见 `docs/final_upgrade/REAL_CAPABILITY_PHASE1.md`。
- 测试：浏览器 24/24；后端 3203 passed / 2 failed（既有 Windows 平台差异）/ 2 skipped；
  前端 313 passed；`vue-tsc` exit 0；`npm run build` exit 0。
- 使用数据：Mock + 注入式测试替身（离线）；真实在线 **BLOCKED**（无密钥）。
- 需要人工确认：是否按 `REAL_DATA_ISOLATION_AUDIT.md` §4 落地运行时真实性不变式。