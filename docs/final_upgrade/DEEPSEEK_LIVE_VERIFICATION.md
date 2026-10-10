# 真实 DeepSeek 在线验证说明（推荐直接用脚本执行）

> **当前状态：`BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE`**
>
> 本轮（真实能力接入第一阶段，2026-10-09）在**本进程内**实测：
>
> | 环境变量 | 实测 |
> | --- | --- |
> | `DEEPSEEK_API_KEY` | **unset** |
> | `DEEPSEEK_BASE_URL` | unset |
> | `DEEPSEEK_MODEL` | unset |
> | `AI_PLANNING_ENABLED` | unset |
>
> ⛔ 本文件**不包含**、⛔ 也不要求任何历史对话中出现过的旧密钥；
> 旧 `sk-` 前缀密钥已作废，**禁止使用**。
> ⛔ 没有新密钥时**保留 BLOCKED**，绝不伪造成功、绝不把测试替身说成真实调用。
>
> 因此本轮：**真实在线路径 = NOT VERIFIED**。

---

## 0. 首选做法：用脚本，不要手写 curl

上一版本文档里的请求示例与真实契约**不一致**（尤其 `/solve`：写了一个不存在的
`confirm` 字段，又缺了必需的 `plan_digest` 与 `confirmed_intent`）。
手写 curl 传大段 JSON 在 Windows 上还容易因为编码 / 引号失败。

因此本轮新增了**一个默认离线、受控在线**的验收脚本：

```powershell
cd backend
$env:PYTHONUTF8 = '1'

# 1) 默认离线：注入确定性假模型驱动真实后端，覆盖全部失败路径。⛔ 不产生任何费用。
python -m tests.verify_deepseek_live

# 2) 只检查环境是否具备在线验收条件（只读环境变量，⛔ 不打印任何值）
python -m tests.verify_deepseek_live --check-env

# 3) 受控在线验收（**会产生真实费用**，必须显式二次确认）
python -m tests.verify_deepseek_live --live --i-understand-this-costs-money

# 4) 受控在线 + 额外查一次 /models（免费但需鉴权，用于确认账号实际可用模型名）
python -m tests.verify_deepseek_live --live --i-understand-this-costs-money --check-models
```

脚本的硬边界（与本任务书逐条对应）：

- ⛔ **CI 永不触网**：在线模式需要 `--live` **和** `--i-understand-this-costs-money`
  同时给出，缺一即拒绝（退出码 2）；
- ⛔ 密钥**只**从后端进程环境 `DEEPSEEK_API_KEY` 读取；
  ⛔ 不打印、⛔ 不落盘、⛔ 不进前端、⛔ 不写进报告；
- ⛔ 不使用任何硬编码 / 历史密钥作为回退；
- ✅ 没有密钥时返回**退出码 3** 并打印 `BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE`；
- ✅ 离线模式覆盖 19 项检查（见 §4），其中包含**"模型不得绕过 Planner"的负向用例**。

---

## 1. 默认模型名核验（已在线确认）

`backend/.env.example` 的默认值是 `DEEPSEEK_MODEL=deepseek-flash`。

**核验结论：与供应商当前文档一致（已在线确认）。**

- 依据：DeepSeek 官方 *Models & Pricing* 把当前模型列为
  **`deepseek-flash`** 与 **`deepseek-v4-pro`**，并明确说明
  "Use `deepseek-flash` as the model name"；旧名 `deepseek-v4-flash` /
  `deepseek-v4-flash-vision-exp` 仍被接受，但对应模型已下线。
  见 <https://api-docs.deepseek.com/quick_start/pricing>。
- 核验日期：2026-10-09。

⚠️ **边界（⛔ 不要把"名字对"当成"可用"）**：

- ⛔ 文档一致 ≠ 账号有权限、≠ 有余额、≠ 在线鉴权通过；
- ⛔ `GET /status` 的 `live_model_available=true` **只**表示"开关已开 + 密钥已配置"，
  **不是**在线调用成功证明；
- 只有一次受控 `POST /interpret` 真正返回 `generator_kind=deepseek_live`，才算在线路径可用。

---

## 2. 前置条件与安全要求

1. **新密钥**，由负责人通过安全渠道提供；⛔ 不使用历史旧密钥；
2. 密钥只注入**后端进程环境**（脚本会在本进程内起后端，所以 CLI 的环境就是后端的环境）；
   ⛔ 不写入 `.env` 提交、⛔ 不写入前端、⛔ 不写入日志、⛔ 不贴进聊天或 issue；
3. 验证场景必须是**合成数据**（脚本内置的 `tests/ai_planning_fixtures.py` 就是合成夹具）；
   ⛔ 不使用任何真实学生成绩、姓名、学号；
4. 明确本次预算与超时（服务端会夹到硬上界内）。

```text
AI_PLANNING_ENABLED=true
DEEPSEEK_API_KEY=<由安全渠道注入，不写入任何文件>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash

AI_PLANNING_MAX_OUTPUT_TOKENS=1200
AI_PLANNING_REQUEST_TIMEOUT=20
AI_PLANNING_MAX_CALLS_PER_REQUEST=3
AI_PLANNING_MAX_SESSIONS=200
AI_PLANNING_ADOPT_TTL_SECONDS=900
```

**成本控制**：`AI_PLANNING_MAX_CALLS_PER_REQUEST=3` 表示"一次 `/interpret` 最多 3 次模型调用"。
本脚本的在线流程最多产生 **2–3 次模型调用**（两次 `/interpret`；`/solve` 与 `/adopt` 不调用模型）。

> ⛔ 密钥注入示例见 §6，且⛔ 不要写进任何文件。

---

## 3. 真实接口契约（从代码提取，⛔ 不是文档转抄）

下面的形状直接来自 `backend/app/api/ai_planning.py` 的 pydantic 模型
（全部 `extra="forbid"` ⇒ 多一个字段就 422）。

### 3.1 `GET /api/v1/ai-planning/status`

```text
enabled, live_model_available, api_key_configured, model, base_url,
max_calls_per_request, request_timeout_seconds, adopt_ttl_seconds,
generator_kind_when_live, data_source_note
```

⛔ 响应里没有任何密钥字段。

### 3.2 `POST /api/v1/ai-planning/interpret`

```json
{
  "context": {
    "semester": "2026-1",
    "base_plan": { "...PlanResult..." },
    "makeup_tasks": [ "...MakeupTask..." ],
    "course_offerings": [ "...CourseOffering..." ],
    "preference": { "...Preference..." }
  },
  "user_message": "尽量别在周五上课，最多 12 学分"
}
```

响应关键字段：

```text
intent_id, plan_digest(64 hex), parsed_intent{...}, ambiguities[], data_source,
generator_kind, generator_note, model_id, can_confirm, state,
token_usage_estimate{prompt,completion,total}, message
```

### 3.3 `POST /api/v1/ai-planning/solve`

```json
{
  "intent_id": "<来自 /interpret>",
  "plan_digest": "<64 hex，与 /interpret 一致>",
  "confirmed_intent": {
    "plan_digest": "<同上，必须一致，否则 410>",
    "semester": "2026-1",
    "scope": "current_semester",
    "target_semester": "2026-1",
    "hard_constraints": [{"kind": "max_credit_limit", "value": 12, "evidence": "学生说了 12 学分"}],
    "soft_preferences": [{"kind": "avoid_weekday", "value": 5, "note": "尽量避开周五"}],
    "locked_courses": [{"course_id": "DS101", "class_id": "ds-01", "reason": "必须保留"}],
    "user_note": null
  }
}
```

⚠️ **上一版文档的错误就在这里**：
⛔ 没有 `confirm` 字段；⛔ `plan_digest` 与 `confirmed_intent` 都是**必需**的；
`confirmed_intent` **只允许上面这 8 个键**（多一个即 422）；
`scope` **只能**是 `current_semester`。

响应关键字段：`candidate_id, status(candidate_ready|no_feasible_candidate|blocked),
plan_kind, candidate_plan, diff, risks[], unresolved[], message, blocked_reason,
data_source, generator_kind, plan_digest`。

### 3.4 `POST /api/v1/ai-planning/adopt`

```json
{ "candidate_id": "<来自 /solve>", "plan_digest": "<来自 /solve>", "accept": true }
```

响应：`accepted, state, adopted_version, adopted_version_scope("process_local_session"),
original_plan_unchanged, plan_digest, message`。

### 3.5 错误码 → HTTP（⛔ 无 500 兜底）

| 错误码 | HTTP |
| --- | --- |
| `ai_planning_disabled` | 503 |
| `ai_planning_model_unavailable` | 503 |
| `ai_planning_message_rejected` | 400 |
| `ai_planning_model_output_invalid` | 422 |
| `ai_planning_intent_invalid` | 422 |
| `ai_planning_intent_not_confirmable` | 409 |
| `ai_planning_session_not_found` | 404 |
| `ai_planning_session_expired` | 410 |
| `ai_planning_plan_context_invalid` | 422 |
| `ai_planning_solve_unsupported` | 501 |
| `ai_planning_candidate_invalid` | 502 |
| `ai_planning_budget_exceeded` | 429 |
| `ai_planning_adoption_conflict` | 409 |

---

## 4. 验收标准（逐条可判定）

| # | 检查项 | 通过判据 | 失败判据 |
| --- | --- | --- | --- |
| 1 | 配置状态 | `/status` → `enabled=true`、`api_key_configured=true` | 任一 false ⇒ 配置问题，**不是**在线验证 |
| 2 | 模型名有效 | `GET /models` 的 `id` 列表包含 `DEEPSEEK_MODEL` 的值 | 不含 ⇒ 模型名/权限问题，换名重试**一次** |
| 3 | 真实在线路径 | `POST /interpret` → HTTP 200 且 **`generator_kind="deepseek_live"`** | 返回 `test_double` / `unavailable` ⇒ **不算通过** |
| 4 | 结构校验 | 响应通过契约解析；`parsed_intent` 里的课程号全部落在**请求给出的上下文白名单**内 | 出现白名单外课程号 ⇒ 校验失效，**必须报告** |
| 5 | 模糊意图机制 | 不含学分数字的消息 ⇒ `can_confirm=false` 且有 `ambiguities` | `can_confirm=true` ⇒ 模型越权替用户决定，**必须报告** |
| 6 | **方案由 Planner 决定** | `/solve` 候选里的每个 `(course_id, class_id)` 都能在**请求给出的 offerings** 里找到 | 候选含模型自创课程/班次 ⇒ **严重问题**，停止演示 |
| 7 | 失败不虚构 | 无密钥 / 模型不可用 / 非法输出 / 指纹不符 / 过期 / 拒绝 ⇒ 明确错误码 + 原方案不变 | 返回了编造结果或推进了版本 ⇒ **严重问题** |
| 8 | 不泄露 | 任何响应、日志、截图都不含密钥值（`sk-` 或 `"api_key": "…"`） | 出现 ⇒ 立即停止并按安全事件处理 |

> 第 4–7 项**已经全部被离线模式自动断言**（见 §5），
> 在线模式只需再确认第 3 项（真实 `generator_kind`）与第 2 项（模型清单）。

---

## 5. 离线模式覆盖的 19 项检查（⛔ 不产生费用）

`python -m tests.verify_deepseek_live` 实测全部通过：

| 组 | 检查 |
| --- | --- |
| 未启用 | `/status` 如实 `enabled=false`；`/interpret` ⇒ 503 `ai_planning_disabled`（不 fallback） |
| 无模型 | `/interpret` ⇒ 503 `ai_planning_model_unavailable` |
| 正常闭环 | `/status` 不泄露密钥；`/interpret` 标 `test_double`（⛔ 不说成 `deepseek_live`）；指纹 64 位；`/solve` ⇒ `candidate_ready`；**候选教学班全部来自请求给出的 offerings**；采用后 `scope=process_local_session`、版本 1；重复采用 ⇒ 409 |
| 意图歧义 | 模糊消息 ⇒ `can_confirm=false` 且有歧义；**歧义意图强行求解 ⇒ 409** |
| 会话/过期 | 指纹不符 ⇒ 410；候选过期后采用 ⇒ 410 且原方案不变 |
| 拒绝 | `accepted=false`、`original_plan_unchanged=true`、版本仍为 0 |
| **模型越权（负向）** | 幻觉课程号 ⇒ 422 白名单拦截；非 JSON 输出 ⇒ 503；请求体夹带姓名 ⇒ 422；**模型试图夹带 `candidate_plan` ⇒ 422（未声明字段直接拒绝，⛔ 不忽略）** |

---

## 6. 在线模式的执行步骤（最少调用）

```powershell
# 0) 只在本终端会话内注入密钥（⛔ 不要 Echo、不要重定向、不要放进 .env）
cd backend
$env:PYTHONUTF8 = '1'
$env:AI_PLANNING_ENABLED = 'true'
$env:DEEPSEEK_MODEL = 'deepseek-flash'
$env:DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
$env:DEEPSEEK_API_KEY = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText

# 1) 先看环境是否齐备（免费）
python -m tests.verify_deepseek_live --check-env

# 2) 受控在线（第 1 次调用 = /interpret；随后模糊意图 = 第 2 次调用）
python -m tests.verify_deepseek_live --live --i-understand-this-costs-money

# 3) 可选：额外确认账号可用模型名（免费，需鉴权）
python -m tests.verify_deepseek_live --live --i-understand-this-costs-money --check-models
```

脚本会依次断言：`/status` 配置就绪 → （可选）`/models` → 真实 `/interpret`
`generator_kind=deepseek_live` → 白名单 → 模糊意图 `can_confirm=false` →
`/solve`（不调模型）→ 拒绝采用（不调模型）。
若第 3 项不通过，脚本**立即停止**后续调用，避免无意义费用。

### 记录模板（⛔ 不含密钥与个人信息）

```text
日期：
分支 / commit：
模型名（当次 /models 返回值）：
/status：enabled=… api_key_configured=… live_model_available=…
/interpret：HTTP 状态 / generator_kind / model_id / can_confirm / 歧义数 / token 估计
模糊意图：can_confirm / 歧义类型
/solve：status / 候选是否全部落在 offerings 内 / blocked_reason
/adopt(拒绝)：accepted / original_plan_unchanged
结论：PASS / FAIL（逐条对应 §4）
```

---

## 7. 失败处理

| 现象 | 分类 | 处置 |
| --- | --- | --- |
| `/status` 的 `enabled=false` | 配置 | 检查 `AI_PLANNING_ENABLED` 是否注入到**后端进程** |
| `api_key_configured=false` | 配置 | 密钥没进到后端进程；⛔ 不要为了"跑通"把密钥写进仓库文件 |
| `/models` 不含目标模型 | 权限/名字 | 换用当次返回的 id，重试**一次**；仍失败则记录并停止 |
| `/interpret` 返回 `test_double` | 严重 | 说明注入的仍是测试替身；**本次不算在线验证**，如实标注 |
| `/interpret` 返回 `unavailable` | 上游 | 记录 HTTP 状态与错误类型；检查余额/限流/网络出口 |
| 401/403 | 鉴权 | 密钥无效或无权限；**停止**，向负责人索取新密钥，⛔ 不要重试刷次数 |
| 429 | 限流 | 降低调用频率；本轮直接停止，不重试 |
| 超时 | 网络/上游 | 记录耗时；确认后端返回的是超时错误而**不是**编造结果 |
| 模型输出含白名单外课程号 | **严重** | 立即停止演示；按"校验失效"上报（安全/正确性问题，不是体验问题） |
| 候选含请求 offerings 之外的班次 | **严重** | 说明模型绕过了 Planner；停止演示并上报 |
| 响应/日志/截图里出现密钥 | **安全事件** | 立即停止、撤销该密钥、按安全流程处理；⛔ 不要把密钥内容贴进任何记录 |

---

## 8. 与演示口径的关系

在真实在线验证**通过之前**，所有演示必须使用以下口径（与 `DEMO_SCRIPT.md` 一致）：

- 页面顶部 Mock 提示、`仅前端预览` 提示、`规则模板（非 AI）` 标签必须原样展示；
- AI 调整若走测试替身，必须显示"测试替身模型（不是线上模型）"；
- 抽屉"技术详情"里的 `live_model_available` 必须与
  "配置就绪 ≠ 在线调用成功"的说明**同时**出现
  （已实现，见 `frontend/src/components/ai/drawerCapability.ts`）；
- ⛔ 不得用测试替身结果冒充真实 DeepSeek 在线调用。

---

## 9. 本次改动说明（相对上一版）

| # | 上一版问题 | 本版处置 |
| --- | --- | --- |
| 1 | `/solve` 示例写了不存在的 `confirm` 字段，且缺 `plan_digest` / `confirmed_intent` | §3.3 **按代码重写**，并显式标出"这是上一版的错误" |
| 2 | 未说明 `plan_digest` 必须与 `/interpret` 一致（否则 410） | §3.3 明确写出 |
| 3 | 未说明 `confirmed_intent` 只允许 8 个键、`scope` 只能是 `current_semester` | §3.3 明确写出 |
| 4 | `/adopt` 只写"确认采用" | §3.4 给出完整请求体 |
| 5 | 只给手写 curl，容易在 Windows 上失败且无法覆盖失败路径 | §0 改为**脚本优先**；curl 仅作契约参考 |
| 6 | 验收标准缺少"模型不得绕过 Planner"的可判定项 | §4 第 4/6 项 + §5 负向用例 |
