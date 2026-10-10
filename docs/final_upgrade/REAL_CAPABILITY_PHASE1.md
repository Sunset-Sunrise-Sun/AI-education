# 学航·转衔｜真实能力接入第一阶段（`feature/real-capability-readiness`）

> 本文件是本轮任务的**设计文档**（设计先行，便于人工审核），
> 也是三个子任务的"边界声明"。代码与测试见同目录其它文件。

基准分支：`feature/final-upgrade` = **`f537bee`**（"Merge PR #71: final demo readiness and CI fixes"）
本分支：`feature/real-capability-readiness`（独立 worktree，⛔ 未改 `main`，⛔ 未自动合并）

---

## 0. 开工前核查结果（如实记录）

| 要求读取 | 状态 |
| --- | --- |
| `AGENTS.md` | ✅ 已读（本分支 worktree 内的版本） |
| 架构文档 `docs/ARCHITECTURE.md` | ✅ 已读 |
| 当前后端接口实现 `backend/app/api/ai_planning.py` 等 | ✅ **逐行读过**（本轮所有请求/响应结构都从源码提取） |
| 前次验收报告 | ✅ 已读 `docs/final_upgrade/reports/FINAL_DELIVERY_READINESS_REPORT.md`、`UX_BROWSER_E2E_FINAL_ACCEPTANCE.md`、`AI_PLANNING_JOINT_QA_REPORT.md`、`CI_PLAN.md` |
| `PROJECT_CONTEXT.md` / `DEVELOPMENT_RULES.md` | ⚠️ 仓库中**不存在**（与前轮结论一致） |
| `docs/status/<module>.md` | ✅ 已读 `ai_planning.md` / `curriculum.md` / `course_data.md` |

**重要发现（基线与前次不同）**：PR #71 **已被合并**，`feature/final-upgrade` 从
`85152e9` 前进到 **`f537bee`**。因此本轮分支基于 `f537bee`，
已自带我刚提交的 CI 工作流与 `python-docx` 依赖声明。

---

## 1. 任务 A：从源码提取的真实接口契约

下面每一条都来自代码，不是文档转抄。

### 1.1 `GET /api/v1/ai-planning/status`

`backend/app/api/ai_planning.py:174-186` 定义 `StatusResponse`（`extra="forbid"`）：

```text
enabled: bool
live_model_available: bool
api_key_configured: bool
model: str
base_url: str
max_calls_per_request: int
request_timeout_seconds: float
adopt_ttl_seconds: int
generator_kind_when_live: str   # 常量 "deepseek_live"
data_source_note: str
```

⛔ **不含任何密钥**。`live_model_available` 只表示"开关开 + 密钥已配置"
（`config.live_model_available`），**不是**在线鉴权或调用成功。

### 1.2 `POST /api/v1/ai-planning/interpret`

请求（`InterpretRequestBody`，`extra="forbid"`）：

```json
{
  "context": {
    "semester": "2026-1",
    "base_plan": { ...PlanResult... },
    "makeup_tasks": [ ...MakeupTask... ],
    "course_offerings": [ ...CourseOffering... ],
    "preference": { ...Preference... }
  },
  "user_message": "尽量别在周五上课，最多 12 学分"
}
```

- `base_plan` / `makeup_tasks` / `course_offerings` / `preference` 都是**公共对象**；
- `extra="forbid"` ⇒ 多传成绩单 / 姓名 / 学号等字段直接 **422**。

响应（`InterpretResponse`）：

```text
intent_id: str
plan_digest: str            # 64 位十六进制（服务端算的方案指纹）
parsed_intent: { summary, scope, target_semester,
                 hard_constraints[{kind,value,evidence}],
                 soft_preferences[{kind,value,note}],
                 locked_courses[{course_id,class_id,reason}],
                 confidence, notes[], ambiguities[{code,question,detail}] }
ambiguities: [{code, question, detail}]
data_source: str            # mock / real / mixed / unknown（由教学班自身 data_source 判定）
generator_kind: str         # deepseek_live / test_double / unavailable
generator_note: str
model_id: str
can_confirm: bool           # = (ambiguities 为空)
state: str
token_usage_estimate: {prompt, completion, total}
message: str
```

**本接口不生成任何方案**：`can_confirm=false` 表示仍有歧义必须用户回答。

### 1.3 `POST /api/v1/ai-planning/solve`

请求（`SolveRequestBody`）：

```json
{
  "intent_id": "<来自 /interpret，长度 ≥ 8>",
  "plan_digest": "<64 位十六进制，与 /interpret 返回一致>",
  "confirmed_intent": {
    "plan_digest": "<同上，必须一致>",
    "semester": "2026-1",
    "scope": "current_semester",
    "target_semester": "2026-1",
    "hard_constraints": [{"kind":"max_credit_limit","value":12,"evidence":"…"}],
    "soft_preferences": [{"kind":"avoid_weekday","value":5,"note":"…"}],
    "locked_courses": [{"course_id":"DS101","class_id":"ds-01","reason":"…"}],
    "user_note": null
  }
}
```

⚠️ **`confirmed_intent` 只允许这 8 个键**（`service.py:664-669`），多一个键即 422。
其它硬性约束（`service.py:672-683`）：

- `confirmed_intent.plan_digest` 必须与 `context.digest` **完全一致**，否则 **410**（SessionExpired）；
- `semester` 必须等于 `context.semester`；
- `scope` **只能**是 `current_semester`。

响应（`SolveResponse`）：

```text
candidate_id: str | null
status: str                 # candidate_ready / no_feasible_candidate / blocked
plan_kind: str              # "PlanResult" 或 "none"
candidate_plan: {...} | null
diff: {...} | null          # 含 added / removed / replaced[{course_id,from_class,to_class}] / kept / credit_delta
risks: [str]
unresolved: [str]
message: str
blocked_reason: str | null
data_source: str
generator_kind: str
plan_digest: str
```

### 1.4 `POST /api/v1/ai-planning/adopt`

请求（`AdoptRequestBody`）：`{candidate_id, plan_digest, accept: bool}`。
响应（`AdoptResponse`）：`{candidate_id, accepted, state, adopted_version,
adopted_version_scope:"process_local_session", original_plan_unchanged, plan_digest, message}`。

### 1.5 错误码 → HTTP（`ai_planning.py:47-61`，⛔ 无 500 兜底）

| 错误码 | HTTP | 含义 |
| --- | --- | --- |
| `ai_planning_disabled` | 503 | `AI_PLANNING_ENABLED` 未打开 |
| `ai_planning_model_unavailable` | 503 | 模型不可用（无密钥 / 上游不可达） |
| `ai_planning_message_rejected` | 400 | 消息不合规（空 / 超长 / 疑似个人信息） |
| `ai_planning_model_output_invalid` | 422 | 模型输出未通过结构或白名单校验 |
| `ai_planning_intent_invalid` | 422 | 确认意图形状/取值非法 |
| `ai_planning_intent_not_confirmable` | 409 | 意图仍有歧义 |
| `ai_planning_session_not_found` | 404 | 会话/候选不存在 |
| `ai_planning_session_expired` | 410 | 指纹不符或候选过期 |
| `ai_planning_plan_context_invalid` | 422 | 上下文非法 |
| `ai_planning_solve_unsupported` | 501 | 冻结 Planner 无法表达该意图 |
| `ai_planning_candidate_invalid` | 502 | 候选未通过确定性复核 |
| `ai_planning_budget_exceeded` | 429 | 超出调用预算 |
| `ai_planning_adoption_conflict` | 409 | 重复采用 / 状态冲突 |

### 1.6 `DEEPSEEK_LIVE_VERIFICATION.md` 中与实现不一致之处（本轮修复清单）

| # | 文档原写法 | 实际契约 | 处置 |
| --- | --- | --- | --- |
| 1 | `curl … -d $body` 用 PowerShell `ConvertTo-Json` 直接传 | 可运行但**极易**在 Windows 上因编码/引号失败；且没有说明 `extra="forbid"` | 改为"用脚本调用"，不再手写 curl 大 JSON |
| 2 | `/solve` 示例体 `{"intent_id":…,"confirm":true,"semester":…}` | ⛔ **错误**：没有 `confirm` 字段；必须传 `plan_digest` + `confirmed_intent`（8 键） | **修正为真实形状**（见 §1.3） |
| 3 | `/solve` 未说明 `plan_digest` 必须与 `/interpret` 一致 | 不一致 ⇒ **410** | 补充说明与验收判据 |
| 4 | 未说明 `confirmed_intent.scope` 只能是 `current_semester` | 其它值 ⇒ 422 | 补充 |
| 5 | `/adopt` 只写"确认采用" | 必须同时传 `candidate_id` + `plan_digest` + `accept` | 补充完整请求体 |
| 6 | 验收标准里没有"模型不得绕过 Planner"的可判定项 | `status=candidate_ready` 时候选的每个 `(course_id,class_id)` 必须能在**请求给出的 offerings** 里找到，且与本地冻结 Planner 同输入结果一致 | 补进验收标准 |

---

## 2. 任务 A 的交付物设计

### 2.1 新增受控在线验收脚本

`backend/tests/verify_deepseek_live.py`（**默认离线**）：

| 模式 | 命令 | 是否调用收费模型 |
| --- | --- | --- |
| 默认（离线自检） | `python -m tests.verify_deepseek_live` | ⛔ **否**：注入确定性假模型，覆盖全部失败路径 |
| 受控在线（仅在确认有新密钥时） | `python -m tests.verify_deepseek_live --live --i-understand-this-costs-money` | ✅ 是，且**必须显式二次确认** |

设计要点：

1. **默认离线**：CI 永不触网；在线模式需要显式双重开关，缺一即拒绝运行；
2. **密钥只从后端进程环境读取**（`DEEPSEEK_API_KEY`），
   ⛔ 不打印、⛔ 不落盘、⛔ 不进前端、⛔ 不写进任何报告；
3. **离线模式覆盖这些路径**（用注入的假模型驱动真实 FastAPI 应用）：
   - 无密钥 / 未启用 ⇒ 503 `ai_planning_disabled` / `ai_planning_model_unavailable`；
   - 模型输出非法（白名单外课程号 / 结构错）⇒ 422 `ai_planning_model_output_invalid`；
   - 意图歧义（"太累"没给学分数字）⇒ `can_confirm=false`，且**确认后仍不能求解**（409）；
   - 指纹不符 ⇒ 410；
   - 候选过期（TTL 极小）⇒ 410；
   - 拒绝采用 ⇒ `accepted=false`、`original_plan_unchanged=true`、版本不变；
   - 重复采用 ⇒ 409；
   - **模型绕过 Planner 的负向用例**：注入一个"返回 offerings 里不存在的课程号"的模型，
     断言 `/solve` 不会把该课程号放进候选（这是本任务书点名的验收重点）。
4. **在线模式**只做最小成本调用：`/status` → `/models` → 一次 `/interpret` → 一次模糊意图 `/interpret`
   → `/solve` + `/adopt`（不产生模型调用）→ 返回结论；
   ⛔ 不在在线模式里跑破坏性用例（那些留给离线模式）。

### 2.2 复用的既有夹具

优先复用 `backend/tests/ai_planning_fixtures.py`
（`context_payload()` / `confirm_payload()` / `makeup_tasks()` / `offerings()` / `base_plan()`）
与 `backend/tests/test_ai_planning_joint_e2e.py` 的"真实 HTTP + uvicorn"模式，⛔ 不重写一套。

---

## 3. 任务 B / C / D

见本目录另外两份文档：

- `REAL_DATA_ISOLATION_AUDIT.md`（任务 C 的审计结论与最小修复）
- 任务 B 的可行性判定与（如可行）`catalog_draft` 工具说明 —— 见
  `DOCX_CATALOG_DRAFT.md`

任务 D 的可重复验收结果见本轮任务的完成报告。
