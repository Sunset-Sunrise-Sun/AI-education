# DEEPSEEK_CONTROLLER_REPORT — DeepSeek 转专业补修 Planning Controller

- **Agent**：Final Upgrade · Agent A（DeepSeek Planning Controller，无人值守）
- **分支**：`feature/deepseek-planning-controller`（起点 = `feature/final-upgrade-integration-qa`）
- **实现提交 SHA**：`293a78e563680fedd9257cbf58402920451775fa`
  （`feat(ai-planning): add DeepSeek intent controller with confirmation-gated solving`）
- **本报告提交 SHA**：见本文件所在提交（`docs(ai-planning): add controller report and API handoff`）
- **基线**：`37f62f2aaa5ab3d54ecabf9844c284b068369a29`
- **是否改动受保护分支**：**否**（未动 `main`、`feature/final-upgrade`、PR #62/#63/#64、B 的分支）
- **是否自动合并**：**否**（只允许创建 Draft PR；本报告不请求合并）
- **使用数据**：**Mock**（全部人工构造的合成教学班与补修任务）
- **真实 DeepSeek 在线调用**：**NOT VERIFIED**（运行环境未注入密钥）
- **公共契约是否变化**：**否**（`/schemas/`、`/docs/interfaces/`、四个冻结 Provider 签名一字未改）

---

## 1. 本次完成

### 核心（P0）

| # | 能力 | 实现位置 |
| --- | --- | --- |
| 1 | **意图解析**：自然语言 → 严格结构化意图草稿（范围 / 硬约束 / 软偏好 / 锁定课程 / 歧义） | `app/ai_planning/intent.py`、`minimize.py` |
| 2 | **真实 DeepSeek 接入**：OpenAI 兼容 `/chat/completions`、`response_format=json_object`、标准库实现（⛔ 无新依赖） | `app/ai_planning/deepseek_client.py` |
| 3 | **用户确认后的 Planner 调用**：只有确认且指纹匹配才求解；候选**只**由受控 Planner 产生 | `app/ai_planning/service.py` |
| 4 | **候选方案 + 确定性差异**：`diff` / `risks` 全部由后端计算，⛔ 不来自模型 | `service.py::compute_candidate_diff` |
| 5 | **二次确认采用/拒绝**：绑定方案指纹、TTL、重复采用 409 | `service.py::adopt` |
| 6 | **私有 API**：`status` / `interpret` / `solve` / `adopt` | `app/api/ai_planning.py` |
| 7 | **无密钥可跑的注入式假模型** | `app/ai_planning/fake_model.py` |

### 安全不变量（逐条落地，均有测试）

| 不变量 | 落地方式 |
| --- | --- |
| 模型输出**永远不能**直接成为 `PlanResult` | 候选唯一来源是注入的 `PlannerProvider.plan(...)` |
| 模型提到的课程 / 教学班必须在白名单内 | `intent.cross_check` 对**白名单外**标识直接拒绝整份草稿（不是静默丢弃） |
| "太累 / 少上一点"不得变成固定学分数 | `HardConstraint` 拒绝无数值的 `max_credit_limit`；且硬约束必须带 `evidence` |
| 未确认绝不求解 | `solve()` 第一步校验 `confirmed_intent` + 指纹 |
| 未二次确认绝不改方案 | 候选是新对象；只有 `adopt` 推进版本；拒绝/超时/出错都不变 |
| 指纹变化 ⇒ 旧意图 / 旧候选失效 | 每步与 `PlanningContext.digest` 比对（410） |
| 模型调用次数有上限 | `AiPlanningConfig.max_calls_per_request` + `ModelCallBudget` |
| 会话有界且不落盘 | `SessionStore`（进程内 LRU，重启失效并 fail closed） |
| ⛔ 不把 PII 发给模型 | `minimize.sanitize_user_message`：命中个人信息模式**直接 400**，一个字节都不外发 |
| ⛔ 密钥不进日志 / 响应 / 异常 | 只出现在请求头；错误只返回固定原因码 |
| 不返回"输入里根本没有的班次" | `_unavailable_selected_keys` → `blocked: candidate_references_unavailable_class` |

### 错误路径与成本（任务书 §7 逐项）

401 / 402 / 429 / 5xx / 超时 / 网络错误 / 超大响应 / 空 JSON / 幻觉课程号 /
重复确认 / 过期方案 / 无教学班 / 预算超限 —— 全部有**固定错误码 + 有边界 HTTP 状态**，
且**保留原方案**。⛔ 不重试、⛔ 不回退到 Mock、⛔ 不伪造成功。

---

## 2. 修改文件清单

**新增（生产代码）**

| 文件 | 行数级别 | 说明 |
| --- | --- | --- |
| `backend/app/ai_planning/__init__.py` | 小 | 包入口与显式导出 |
| `backend/app/ai_planning/config.py` | 中 | 环境配置（默认关闭、硬上界、`describe()` 不含密钥） |
| `backend/app/ai_planning/errors.py` | 小 | 13 个固定错误码 |
| `backend/app/ai_planning/context.py` | 中 | 方案上下文快照 + 指纹 + 白名单 + 最小化 payload |
| `backend/app/ai_planning/intent.py` | 大 | 严格意图模型 + 白名单核对 + 歧义 |
| `backend/app/ai_planning/minimize.py` | 中 | system prompt、PII 拒绝、不可信内容包裹 |
| `backend/app/ai_planning/deepseek_client.py` | 中 | OpenAI 兼容客户端（标准库）+ 固定失败原因 |
| `backend/app/ai_planning/fake_model.py` | 中 | 三类注入式假模型 |
| `backend/app/ai_planning/service.py` | 大 | 服务层：意图 → 求解 → 采用；会话存储；差异计算 |
| `backend/app/api/ai_planning.py` | 大 | 4 条私有路由 + 私有请求/响应包络 |
| `backend/app/services/ai_planning_runtime.py` | 小 | 进程内装配（无密钥不构造真实客户端） |
| `backend/.env.example` | 小 | DeepSeek 配置占位符（⛔ 无真实值） |

**修改（生产代码，最小）**

| 文件 | 改动 |
| --- | --- |
| `backend/app/main.py` | +1 import 组、+1 `include_router`（**仅此两处**） |

**新增（测试）**

| 文件 | 数量 |
| --- | --- |
| `backend/tests/ai_planning_fixtures.py` | Mock 夹具 |
| `backend/tests/test_ai_planning_service.py` | 47 项 |
| `backend/tests/test_ai_planning_api.py` | 22 项 |
| `backend/tests/test_ai_planning_client.py` | 27 项 |

**修改（测试）**

| 文件 | 改动 |
| --- | --- |
| `backend/tests/test_integration_orchestrator.py` | 在**显式路由白名单**中登记 4 条新私有路由 |

**文档**

`docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`（前后端契约）、
`docs/final_upgrade/reports/DEEPSEEK_CONTROLLER_REPORT.md`（本文件）、
`docs/status/ai_planning.md`（新增）、`docs/worklogs/ai_planning.md`（新增）。

**未修改**：`/schemas/**`、`/docs/interfaces/**`、`frontend/**`、
`app/planner/**`（⛔ 未改四参数签名与实现）、`app/curriculum/**`、
`app/personal/**`、`app/explanation/**`、`app/integration/**`、
`app/services/planning_runtime.py`、`mock_data/**`、`AGENTS.md`。

---

## 3. 接口契约是否变化

| 项 | 变化 |
| --- | --- |
| `/schemas/*.schema.json` | **否** |
| `/docs/interfaces/*.md` | **否** |
| `PlannerProvider.plan(*, makeup_tasks, offerings, current_schedule, preference)` | **否**（一字未改；控制器只是**调用方**） |
| `PlanningOrchestrator.build_plan(...)` | **否** |
| `POST /api/v1/plan`、`/api/v1/mock/*`、`/api/v1/personal-planning/*`、`/api/v1/explanation/*` | **否** |
| **新增** 4 条私有路由 `/api/v1/ai-planning/*` | **是**（已在路由白名单测试中登记；见 HANDOFF 文档） |
| **新增** 非公共请求/响应包络 | **是**（定义在 `app/api/ai_planning.py` 内，⛔ 不进 `/schemas/`） |

---

## 4. 运行方法

```powershell
# 1) 复制占位配置（⛔ 不要把真实密钥写进仓库）
Copy-Item backend\.env.example backend\.env      # 按需修改，.env 已在 .gitignore

# 2) 打开开关并注入密钥（仅服务器环境）
$env:AI_PLANNING_ENABLED = "1"
$env:DEEPSEEK_API_KEY    = "<server-injected>"
$env:DEEPSEEK_BASE_URL   = "https://api.deepseek.com"
$env:DEEPSEEK_MODEL      = "deepseek-flash"
$env:PYTHONUTF8          = "1"

# 3) 启动
cd backend && python -m uvicorn app.main:app --reload

# 4) 查看状态（不会暴露密钥）
curl http://127.0.0.1:8000/api/v1/ai-planning/status
```

未设置 `AI_PLANNING_ENABLED` 时，`interpret` / `solve` / `adopt` 一律返回
**503 `ai_planning_disabled`** —— 这是**默认正确状态**，⛔ 不是故障。

---

## 5. 测试命令与结果

```powershell
cd backend
$env:PYTHONUTF8 = "1"
python -m pytest -q
```

| 范围 | 结果 |
| --- | --- |
| **后端全量（本轮）** | **3174 passed / 2 failed / 2 skipped** |
| 后端全量（基线 `37f62f2`，同命令同环境） | 3078 passed / 2 failed / 2 skipped |
| 新增测试 | 47 + 22 + 27 = **96 passed / 0 failed** |
| 受影响的既有测试 | `test_integration_orchestrator.py`（白名单登记，已更新并通过） |

**遗留基线失败（与本轮改动无关，开工前已用同命令复现）**

1. `test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]`
   —— Python 3.14 起 `Path("bad\x00path")` 不再抛 `ValueError`（Windows 路径语义差异）；
2. `test_curriculum_docx_reader.py::test_duplicate_or_unsafe_archive_members_are_rejected[word\\DEMO-PRIVATE-PART]`
   —— Windows 上 ZIP 成员名中字面反斜杠的语义差异。

⛔ 本轮**未**修改这两处实现或测试，也⛔ 未为了让它们变绿而放宽任何断言。

**前端测试**：worktree 内无 `frontend/node_modules`（未安装依赖），且本轮**未改任何前端文件**，
因此未运行 Vitest；这不是回归风险，但也没有本轮前端证据。

---

## 6. 验收用例覆盖对照（任务书「边界与验收」）

| 要求 | 对应测试 |
| --- | --- |
| 正常意图 → 确认 → 求解 | `test_full_flow_confirmed_intent_produces_a_planner_candidate`、`test_full_flow_through_http_requires_two_confirmations` |
| **未确认不求解** | `test_unconfirmed_intent_never_reaches_the_planner`（含"Planner 从未被调用"断言）、`test_unconfirmed_intent_is_rejected_with_422` |
| 锁定课程 | `test_locked_course_is_preserved_in_the_candidate`、`test_candidate_breaking_a_locked_course_is_rejected`、`test_locking_a_course_outside_the_current_plan_is_an_ambiguity`、`test_locking_a_class_that_cannot_exist_is_rejected_by_whitelist` |
| 模糊学分 | `test_vague_tiredness_is_not_converted_into_a_credit_number`、`test_credit_limit_without_evidence_is_not_accepted`、`test_credit_limit_above_the_declared_max_is_rejected`、`test_ambiguous_intent_returns_409` |
| 未知课程（幻觉） | `test_hallucinated_course_or_class_in_locked_list_is_rejected_by_whitelist`、`test_invalid_model_output_fails_closed`（5 类非法输出）、`test_invalid_model_output_fails_closed` 中的非法 `kind` / `scope` / 未知字段 |
| 数据快照过期 | `test_changed_context_invalidates_the_previous_intent`、`test_stale_plan_digest_returns_410`、`test_expired_candidate_cannot_be_adopted` |
| LLM 不可用 | `test_unavailable_model_never_produces_an_intent`（10 种原因码）、`test_disabled_controller_refuses_to_interpret`、`test_no_intent_model_injected_is_explicit_unavailable`、`test_interpret_is_503_when_disabled` |
| 无教学班 | `test_missing_offerings_never_invents_a_class_and_reports_missing_data` |
| 结果无法满足 / 未采用 | `test_planner_rejecting_input_returns_blocked_not_a_fabricated_candidate`、`test_rejecting_a_candidate_keeps_the_original_plan`、`test_rejecting_keeps_the_original_plan`、`test_adopting_twice_is_a_conflict_and_does_not_advance_the_version` |
| 意图数据隔离 | `test_two_intents_have_isolated_ids_and_payloads`、`test_message_with_personal_information_is_never_sent_to_the_model`、`test_context_minimization_excludes_private_fields`、`test_context_payload_has_no_student_identity_fields_at_all`、`test_sessions_are_isolated_between_service_instances` |
| 请求体不接受身份字段 | `test_identity_fields_are_rejected_by_the_contract` |
| 旧路由与 Case A 不回归 | `test_existing_routes_are_untouched`、全量回归 3174 passed、`test_real_plan_api.py` / `test_planning_runtime.py` / `test_synthetic_production_e2e.py` / `test_personal_planning*.py` / `explanation` 全绿 |
| 模型客户端行为（不发真实请求） | `test_ai_planning_client.py`（27 项，覆盖请求形状 / 失败映射 / 成功标记 / 不重试 / 密钥不外泄） |

---

## 7. 真实 DeepSeek 在线调用状态

> **NOT VERIFIED。**

- 运行环境**未注入** `DEEPSEEK_API_KEY`，因此本轮**没有**发起任何真实 DeepSeek 请求；
- `GET /api/v1/ai-planning/status` 在本环境返回 `live_model_available=false`；
- 所有 `generator_kind` 断言都明确是 `test_double` 或 `unavailable`，
  ⛔ **没有任何测试或文档声称已完成真实在线调用**；
- 代码路径已就绪：`DeepSeekChatClient` 只依赖 `urllib`，
  开关 + 密钥齐备时会**真实** POST `{base_url}/chat/completions`；
- **在线验证方式（由运行方执行，⛔ 不需要把密钥发回给我）**：
  1. 在服务器上设置 `AI_PLANNING_ENABLED=1` 与新的安全 `DEEPSEEK_API_KEY`（历史 `sk-` 旧密钥已作废，禁止复用）；
  2. `GET /api/v1/ai-planning/status` 应返回 `live_model_available=true`；
  3. `POST /interpret` 的 `generator_kind` 应为 `deepseek_live`，
     `model_id` 应等于 `DEEPSEEK_MODEL`；
  4. 若返回 `http_401` / `http_402`，说明密钥或余额问题 —— 错误体只含固定原因码。

---

## 8. 【BLOCKED】

### BLOCKED 1 — 真实 DeepSeek 密钥 / 在线验证

```text
阻塞原因：运行环境未注入 DEEPSEEK_API_KEY，无法发起真实在线调用。
已经确认：客户端实现、请求形状、错误映射与成功标记都有测试锁定（注入式传输层）。
无法确认：真实 DeepSeek 服务的实际响应形状与额度状态。
需要人工提供：由运行方在服务器上注入**新的安全密钥**并执行 §7 的 4 步在线验证。
在确认前不会修改：⛔ 不使用任何历史 sk- 旧密钥、⛔ 不在仓库写入任何真实密钥、
                ⛔ 不把 test_double 说成线上模型。
```

### BLOCKED 2 — 真实已核验培养方案目录与真实教学班快照

```text
阻塞原因：沿用上一轮结论，APP_PERSONAL_CATALOG_DIR 与真实 full-semester acceptance 未装配。
已经确认：控制器只消费调用方传入的已验证对象；data_source 会如实标注 mock/real/mixed/unknown。
无法确认：真实供给下 Planner 会给出什么候选。
需要人工提供：已核验目录 artifact + 已验收的 current-semester 教学班快照。
在确认前不会修改：⛔ 不伪造教学班、⛔ 不把 Mock 数据标成 real。
```

### BLOCKED 3 — 会话持久化 / 多实例

```text
阻塞原因：本实现刻意只用**进程内**会话存储（任务书允许并要求在此情况下 fail closed）。
已经确认：重启/淘汰后旧 intent_id / candidate_id 返回 404；TTL 过期返回 410；
         响应里 adopted_version_scope=process_local_session 如实标注。
无法确认：是否需要数据库、跨实例共享、跨设备同步（属"数据库结构变化"，须人工确认）。
需要人工提供：是否引入持久化的决定。
在确认前不会修改：⛔ 不新增数据库、⛔ 不把进程内版本说成账户级版本。
```

### BLOCKED 4 — `exclude_course` / 跨学期自动重排

```text
阻塞原因：冻结的四参数 Planner 不接收"排除某门课"或"跨学期重排"参数。
已经确认：控制器**不硬造**候选，而是明确返回 blocked + 固定原因
         （exclude_course_hard_constraint_not_supported_by_frozen_planner /
          cross_semester_adjustment_not_supported）。
无法确认：是否要为这两种意图扩展 Planner 能力（属接口/算法变更，须人工确认）。
需要人工提供：是否排期扩展的裁决。
在确认前不会修改：⛔ 不新增 Planner 参数、⛔ 不在控制器里重写求解逻辑。
```

---

## 9. 已知问题（非阻塞）

1. **`data_source` 只有 `unknown` 时** Planner 无法确认无冲突；控制器如实报告
   `schedule_unknown` / `missing_data`，⛔ 不推断学校未开课。
2. **没有教学班输入时**，冻结 Planner 连"当前已选班"的完整对象也取不到，
   因此候选可能变成空课表。控制器**不隐藏**这一点：`diff.removed` 列出被移除课程、
   `risks` 明确指出移除。这是当前契约下的诚实降级，不是本控制器的 bug。
3. **`token_usage_estimate` 是估算**，⛔ 不是计费口径；成本上限只做了"每请求调用次数"这一层。
4. **候选只做"确认后一次求解"**：不搜索"可行子集"、不排序多个候选
   （`INTEGRATION_QA_STATUS.md` 已记录"保守拒绝 ≠ 最优补修路径"，属下一轮工作）。
5. **前端未实现**（属 Agent B）；本报告只交付后端与契约文档。

---

## 10. 其他成员需要注意

- **共享文件冲突面**：本轮只改 `backend/app/main.py` 的 **2 行**
  （1 行 import 组 + 1 行 `include_router`），是全部改动里最可能冲突的位置；
  如与 B 的分支冲突，请**各自保留自己的 `include_router` 行**，⛔ 不要删除任何一条。
- **`test_integration_orchestrator.py` 的路由白名单**已增加 4 条；
  任何后续新增路由都必须继续在该测试中逐条登记。
- **⛔ 未改 `PlannerProvider`**：控制器只作为调用方；如果需要 exclude/跨学期能力，
  必须走接口变更提案，⛔ 不要在控制器里复制求解逻辑。
- **前端（B）请以 `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md` 为准**，
  ⛔ 不要猜字段；`generator_kind` 与 `data_source` 必须如实展示。
- **密钥**：历史对话里出现过的 `sk-` 旧密钥**已作废**，⛔ 不得使用或引用。

---

## 11. 建议下一步

1. Reviewer 评审本分支（重点：§3 契约表、§6 覆盖对照、§8 BLOCKED 1/4）。
2. 运行方按 §7 的 4 步做**真实在线验证**（新密钥，⛔ 不需要发回给我）。
3. B 按 HANDOFF 文档实现三块 UI（意图确认面板 / 候选对比 / 采用与撤销）。
4. 若负责人决定扩展 Planner（exclude / 跨学期 / 可行子集搜索），
   应先走 `【接口变更请求】`，再在本模块接入。
