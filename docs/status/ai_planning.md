# AI Planning（DeepSeek Controller）当前状态

更新日期：2026-10-09（联合验收轮）。分支：`feature/ai-planning-joint-e2e`（= 后端 PR #66 的
`feature/deepseek-planning-controller` + 前端 PR #65 的 `feature/ai-planning-frontend`）。
状态：**前后端联合验收已执行（真实 HTTP 闭环通过）**；真实在线调用 **仍为 NOT VERIFIED**。

## 联合验收结果（2026-10-09）

| 项 | 结果 |
| --- | --- |
| 后端完整 pytest | **3188 passed / 2 failed / 2 skipped**（2 项为既有 Windows 路径语义差异） |
| 前端 Vitest | **274 passed / 0 failed**（18 文件） |
| 前端 `vue-tsc --noEmit` | **exit 0** |
| 前端 `npm run build` | **exit 0** |
| 真实 HTTP 闭环（uvicorn + 真实请求） | `status` / `interpret` / `solve` / `adopt` **全部通过** |
| 两次确认 / 候选 / 拒绝 / 过期 / 模型不可用 / 原方案不变 | **全部通过** |
| 集成兼容性修复 | **2 处**（`diff.replaced` 键形状、`locked_courses[].reason` 可空）+ 20 项回归测试 |

- 新增 `backend/tests/test_ai_planning_joint_e2e.py`（14 项，**真实监听端口 + 真实 HTTP**）；
- 新增 `frontend/tests/ai-planning-joint-contract-fix.spec.ts`（6 项，先验证后修复）；
- 完整逐项报告见 `docs/final_upgrade/reports/AI_PLANNING_JOINT_QA_REPORT.md`；
- ⛔ 未改 `/schemas/**` 与 `/docs/interfaces/**`；⛔ 未改后端生产代码；
- ⛔ 本轮仍**没有**密钥 ⇒ 真实 DeepSeek 在线调用 **NOT VERIFIED**，
  全部用例的 `generator_kind` 是 `test_double` 或 `unavailable`。

## 是什么

转专业学生的"AI 调整补修方案"后端控制器：

```text
自然语言 → 结构化意图草稿（只读，不求解）
        → 用户确认 → 受控 Planner 生成候选 + 确定性差异
        → 用户二次确认 → 采用 / 拒绝（绑定方案指纹）
```

私有前缀 `/api/v1/ai-planning`：`GET /status`、`POST /interpret`、`POST /solve`、`POST /adopt`。
契约（含 JSON 示例与全部错误码）见 `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`。

## 已实现

- **DeepSeek 接入**：OpenAI 兼容 `/chat/completions`、`response_format={"type":"json_object"}`；
  仅用标准库 `urllib`（⛔ 未引入第三方依赖或 Agent 框架）。
  配置全部走环境变量：`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` /
  `AI_PLANNING_ENABLED`（**默认 false**）/ `AI_PLANNING_MAX_OUTPUT_TOKENS` /
  `AI_PLANNING_REQUEST_TIMEOUT` / `AI_PLANNING_MAX_CALLS_PER_REQUEST` /
  `AI_PLANNING_MAX_SESSIONS` / `AI_PLANNING_ADOPT_TTL_SECONDS`。
  占位样例见 `backend/.env.example`（⛔ 无真实值）。取值都有**硬上界**。
- **严格意图解析**：枚举白名单 + 课程 / 教学班白名单 + 学分依据校验；
  **白名单外标识 ⇒ 拒绝整份草稿**（不是静默丢弃）；
  "太累 / 少上一点"⛔ 不会被换算成任何固定学分数；
  硬约束 `max_credit_limit` 必须带 `evidence`。
- **确认门**：`solve()` 只有在用户确认且 `plan_digest` 与当前上下文一致时才执行；
  `intent_id` / `candidate_id` 由内容派生（⛔ 不含个人信息）。
- **候选只由受控 Planner 产生**：调用冻结的
  `PlannerProvider.plan(makeup_tasks, offerings, current_schedule, preference)` 四参数签名；
  ⛔ 未改签名、⛔ 未复制求解逻辑、⛔ 不接受模型输出的 `PlanResult`。
  服务端再做确定性复核：锁定课程 / 未知班次 / 学分与数据来源。
- **确定性差异**：`diff`（added / removed / replaced / kept / 学分增减）与 `risks`
  全部由后端计算，⛔ 不来自模型输出。
- **二次确认采用**：`adopt(accept=true/false)`；重复采用 409、指纹不符或过期 410、
  未知 id 404；拒绝 / 超时 / 出错都**不改变原方案**。
- **有界错误与成本**：401/402/429/5xx、超时、网络、超大响应、空 JSON、
  幻觉课程号、预算超限 —— 全部有固定错误码与有边界 HTTP 状态；⛔ 不重试、⛔ 不回退到 Mock。
- **PII 边界**：消息命中个人信息 / 凭据模式 ⇒ **400 且一个字节都不外发**；
  发给模型的上下文只含课程号、学分、状态、学期、已声明约束；
  ⛔ 不含姓名 / 学号 / 成绩 / GPA / Cookie / Token。
- **无密钥可测**：`RuleFakeIntentModel` / `ScriptedIntentModel` / `UnavailableIntentModel`
  通过依赖注入使用；它们返回 `generator_kind = test_double`，⛔ **绝不**是 `deepseek_live`。

## 生成方式标记（前端必须如实展示）

```text
deepseek_live   真实在线调用成功（唯一可声称"已接入"的取值）
test_double     注入的测试替身（无密钥测试用）
unavailable     未启用 / 无密钥 / 网络 / 协议 / 空输出
```

## 当前未完成 / BLOCKED

- **真实在线调用：NOT VERIFIED** —— 运行环境未注入密钥；
  ⛔ 报告与响应都未声称已完成真实调用。
- **真实已核验培养方案目录与真实教学班快照未装配**（沿用上一轮结论）；
  控制器只消费调用方传入的已验证对象，并如实标注 `data_source`（mock/real/mixed/unknown）。
- **会话仅进程内**：`adopted_version_scope = process_local_session`；
  重启 / 淘汰即失效并返回 404，⛔ 不宣称持久账户或跨设备同步。
- **不支持**：`exclude_course` 硬约束、跨学期自动重排 —— 明确返回 `blocked` + 固定原因，
  ⛔ 不硬造候选（需负责人裁决是否扩展 Planner）。
- **前端未实现**（属 Agent B）。
- 未做"可行子集搜索 / 多候选排序"：当前超限时按保守拒绝处理，
  这不等于最优补修路径（`INTEGRATION_QA_STATUS.md` 已记录）。

## 边界（硬）

- ⛔ 未改 `/schemas/`、`/docs/interfaces/`、`AGENTS.md`；
- ⛔ 未改 `PlannerProvider` 四参数签名或 `app/planner/**` 实现；
- ⛔ 未改 `/api/v1/plan`、`/api/v1/mock/*`、`/api/v1/personal-planning/*`、`/api/v1/explanation/*`；
- ⛔ 未改 `app/curriculum/**`、`app/personal/**`、`app/explanation/**`、`app/integration/**`；
- ⛔ 未引入数据库、未落盘会话、未联网（联网只发生在真实客户端被调用时）。

## 测试

```powershell
cd backend && $env:PYTHONUTF8="1"; python -m pytest -q
```

后端全量 **3174 passed / 2 failed / 2 skipped**（基线同命令 3078 / 2 / 2）。
新增 96 项（service 47 / api 22 / client 27）。
2 项失败为既有 Windows 路径语义差异，与本轮无关，详见
`docs/final_upgrade/reports/DEEPSEEK_CONTROLLER_REPORT.md` §5。

## 下一步

1. Reviewer 评审；2. 运行方用**新密钥**做在线验证；3. B 按 HANDOFF 实现前端；
4. 是否扩展 Planner（exclude / 跨学期 / 可行子集）需先走接口变更提案。

## 真实能力接入第一阶段（2026-10-09，`feature/real-capability-readiness`）

- **离线验收工具**：新增 `backend/tests/verify_deepseek_live.py`（默认离线，⛔ 不调用收费模型）。
  离线模式用注入的确定性假模型驱动**真实 FastAPI**，**19 项检查全部通过**，覆盖：
  未启用 / 无模型 / 正常闭环 / 意图歧义 / 指纹不符 / 候选过期 / 拒绝采用 /
  **模型幻觉课程号被白名单拦截** / 非 JSON 输出 / 请求体夹带姓名 / **模型试图夹带 candidate_plan 被拒**。
  在线模式需 `--live` **和** `--i-understand-this-costs-money` 双重开关，密钥只从
  `DEEPSEEK_API_KEY` 读取（⛔ 不打印、不落盘、不进前端）。
- **契约修正**：`docs/final_upgrade/DEEPSEEK_LIVE_VERIFICATION.md` 从代码重新提取
  `/status`、`/interpret`、`/solve`、`/adopt` 的请求/响应结构；修正了 `/solve` 示例里
  **不存在的 `confirm` 字段**与缺失的 `plan_digest` / `confirmed_intent`，并补充
  `confirmed_intent` 只允许 8 个键、`scope` 只能是 `current_semester`、指纹不符 ⇒ 410。
- **真实在线状态：BLOCKED**（`DEEPSEEK_API_KEY` 实测 unset）。`--check-env` 只报告有无；
  `--live`（无密钥）返回退出码 3 并打印 `BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE`。
  ⛔ 未使用历史旧密钥、⛔ 未伪造成功、⛔ 未用测试替身冒充在线调用。
- 详见 `docs/final_upgrade/REAL_CAPABILITY_PHASE1.md`。

## 来源可信性门：AI 上下文来源不再由请求体决定（2026-10-10）

- 新取值 **`real_unverified`**：教学班自称 `real` 但**服务端没有独立批准依据**。
  `PlanningContext.__post_init__` 里的不变量保证：`real` + `source_verified=False`
  ⇒ 一律降级为 `real_unverified`（⛔ 任何构造路径都绕不过）。
- `api/ai_planning.py` 的 `_context_of()` **硬编码** `source_verified=False`：
  AI 接口的教学班全部来自请求体，服务端⛔ 永远不能声称"来源已核验"；
  请求模型是 `extra="forbid"`，⛔ 无法通过请求体打开这一档。
- 响应新增 **`context_source_verified`**（恒 `false`），供前端区分
  "HTTP 请求成功"与"使用了已核验真实教务数据"。
- 风险提示判据从 `data_source != "real"` 改为 **`not context.source_verified`**：
  ⛔ 自述 real 再也不能抑制"不代表真实教务开课"的提示。
- 前端同步：`DATA_SOURCES` 增加 `real_unverified`；`dataSourceLabel()` 明确写出
  "未经服务端独立核验"，⛔ 不显示成"已核验"。
- ⛔ 未改 `PlanResult` 等公共 Schema；`context_source_verified` 属本模块私有包络字段。