# 前端 AI 规划接口契约（**以后端实现为准**）

> 归属：**Frontend / Agent B（`feature/ai-planning-frontend`）**。
> 状态：**契约已对齐后端实现**（PR #65 Architecture Review 修复轮）。
>
> **单一契约来源**：后端分支 `feature/deepseek-planning-controller` 的
> `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`
> （与 `backend/app/api/ai_planning.py` 同一提交）。
>
> ⛔ 本文不是公共契约：`/schemas/` 与 `/docs/interfaces/` **未被修改**。
> 本文只记录**前端如何消费**该私有接口，以及前端侧的校验与降级规则。

## 0. Review 修复说明（本轮）

PR #65 Architecture Review 指出四处不一致，本轮全部按后端实现修正：

| # | 问题 | 修复 |
| --- | --- | --- |
| ① | 前端 `interpret` 校验/发送 `plan_digest` | 请求改为 `{context, user_message}`；`plan_digest` 由**后端**计算，前端只保存并原样回传 |
| ② | 前端只识别 `status='candidate'` | 改为 **`candidate_ready` / `no_feasible_candidate` / `blocked`** 三值 |
| ③ | 前端要求 `status/adopted_plan` | 改为 **`accepted / state / adopted_version / adopted_version_scope / original_plan_unchanged`**；**不伪造 `adopted_plan`** |
| ④ | 404/501 一律当成"接口未配置" | 改为按**后端固定错误码表**分类（404=会话不存在、410=过期、501=不支持、502=候选非法、429=额度…） |

同时新增：
- **两次确认**（执行前确认意图、采用前确认方案）保留并加强；
- "已采用"明确标注为**进程内会话状态**（`process_local_session`），不是持久保存、也不是教务选课成功；
- `GET /status` 作为可用性判据（`enabled` / `api_key_configured`）；
- 契约形状测试 `frontend/tests/ai-planning-contract.spec.ts`（真实后端 JSON 形状）。

## 1. 适配层位置与开关

| 项 | 值 |
| --- | --- |
| 契约类型与解析器 | `frontend/src/api/aiPlanningContract.ts` |
| typed adapter（唯一出口） | `frontend/src/api/aiPlanning.ts` |
| 预览 fixture | `frontend/src/api/aiPlanningFixtures.ts` |
| 旧路径兼容转发 | `frontend/src/api/aiPlanningTypes.ts`（只 re-export） |
| 开关 | `VITE_AI_PLANNING_API_ENABLED`（默认 **关闭**） |
| 预览开关 | `VITE_AI_PLANNING_PREVIEW`（默认 **关闭**） |

| 真实开关 | 预览开关 | 行为 |
| --- | --- | --- |
| `false` | `false` | 显示"AI 调整不可用"，**不发任何请求** |
| `true` | `false` | 调用真实接口；可用性以 `GET /status` 为准 |
| 任意 | `true` | 只读预览 fixture，并醒目标注「仅前端预览 / 非真实模型 / 未调用 Planner」 |

⛔ **真实失败不会回退到 fixture**；预览分支与真实分支互斥。
（测试里用 `setAiPlanningForceReal(true)` 强制走真实路径，生产代码不调用。）

## 2. `GET /api/v1/ai-planning/status`

页面初始化时调用，决定显示哪种未启用态。

```json
{"enabled": false, "live_model_available": false, "api_key_configured": false,
 "model": "deepseek-flash", "base_url": "https://api.deepseek.com",
 "max_calls_per_request": 3, "request_timeout_seconds": 20.0, "adopt_ttl_seconds": 900,
 "generator_kind_when_live": "deepseek_live", "data_source_note": "…"}
```

- 解析要求：字段齐全且类型正确，否则 `unexpected`（⛔ 不补默认值）；
- ⛔ 响应中永远没有密钥，只有布尔 `api_key_configured`；
- **该私有前缀尚未部署**（404/405 且无结构化错误码）⇒ 分类 `absent`，
  文案区分"未部署"；这与"已实现但未启用（503 `ai_planning_disabled`）"是两件事。

页面文案：

| 状态 | 文案 |
| --- | --- |
| `enabled=false` | AI 调整未启用（服务器未开启 `AI_PLANNING_ENABLED`） |
| `enabled=true, api_key_configured=false` | 已开启但未注入模型密钥，无法解析意图 |
| `/status` 404 | 该私有前缀尚未部署到当前后端 |
| 正常 | 显示输入框（`enabled / api_key_configured / live_model_available / model`） |

## 3. `POST /api/v1/ai-planning/interpret`

### 请求（⛔ **没有** `plan_digest`）

```jsonc
{
  "context": {
    "semester": "2026-1",
    "base_plan": { /* 公共 PlanResult */ },
    "makeup_tasks": [ /* 公共 MakeupTask[] */ ],
    "course_offerings": [ /* 公共 CourseOffering[] */ ],
    "preference": { /* 公共 Preference */ }
  },
  "user_message": "这学期太累，数据结构必须保留，尽量别在周五上课"
}
```

- 前端只发送**页面已有对象**；`context` 由 `useAiPlanning.buildPlanContext()` 组装；
- ⛔ 不发送姓名 / 学号 / 成绩单原文 / 凭据；
- 前端在发送前做与后端 `sanitize_user_message` **同构**的本地前置校验
  （空 / >1000 字 / 邮箱 / 手机号 / 身份证 / 学号样式 / 凭据样式 / `sk-` 密钥），
  ⛔ 但这**不是**唯一防线——服务器仍会校验并可能返回 400。

### 响应 200（要点）

```jsonc
{
  "intent_id": "intent_…",              // 不透明；前端只回传
  "plan_digest": "…64 位十六进制…",     // 后端计算；前端只保存、只回传
  "parsed_intent": {
    "summary": "…", "scope": "current_semester", "target_semester": "2026-1",
    "hard_constraints": [{"kind": "max_credit_limit", "value": 22, "evidence": "…"}],
    "soft_preferences": [{"kind": "avoid_weekday", "value": 5, "note": "…"}],
    "locked_courses": [{"course_id": "DS101", "class_id": "ds-01", "reason": "…"}],
    "confidence": 0.6, "notes": [],
    "ambiguities": [{"code": "…", "question": "…", "detail": null}]
  },
  "ambiguities": [ /* 同上，顶层也有一份 */ ],
  "data_source": "mock",                 // real | mock | mixed | unknown
  "generator_kind": "test_double",       // deepseek_live | test_double | unavailable
  "generator_note": "注入的测试替身模型（不是线上模型）",
  "model_id": "test-rule-fake",
  "can_confirm": true,
  "state": "intent_draft",
  "token_usage_estimate": {"prompt": 412, "completion": 96, "total": 508},
  "message": "已生成意图草稿，请确认后再求解。"
}
```

前端硬规则：

- `generator_kind` **只有三个取值**，未知取值 ⇒ `unexpected`（⛔ 不得把未知状态说成"AI 已接入"）；
- ⛔ **只有 `deepseek_live` 才显示"真实 DeepSeek 在线调用"**；
  `test_double` 显示「测试替身模型（不是线上模型）」；`unavailable` 显示不可用；
- `can_confirm=false` ⇒ 第一次确认按钮**禁用**，并渲染 `ambiguities[]` 的问题
  （固定歧义码白名单见 HANDOFF §3）；
- `token_usage_estimate` 只作展示（是估算，不是计费口径）。

### 第一次确认面板（保留）

可编辑项：**学分上限**（必须由用户给数字）、**避开星期**（软偏好）、**锁定课程**。
确认后才允许调用 `/solve`；⛔ 确认前不产生任何有状态求解。

## 4. `POST /api/v1/ai-planning/solve`

### 请求

```jsonc
{
  "intent_id": "intent_…",
  "plan_digest": "…",                    // 必须是 interpret 返回的同一个值（否则 410）
  "confirmed_intent": {
    "plan_digest": "…", "semester": "2026-1", "scope": "current_semester",
    "target_semester": "2026-1",
    "hard_constraints": [{"kind": "max_credit_limit", "value": 22, "evidence": "用户在确认面板填写"}],
    "soft_preferences": [{"kind": "avoid_weekday", "value": 5, "note": "…"}],
    "locked_courses": [{"course_id": "DS101", "class_id": "ds-01", "reason": "…"}],
    "user_note": null
  }
}
```

- `hard_constraints` 里 `max_credit_limit` **必须带 `evidence`**，否则后端 422；
  前端只在用户真的填了数字时才追加该项（`evidence` 固定为"用户在确认面板填写"）；
- `scope` 固定 `current_semester`（跨学期后端返回 `blocked` / 501）。

### 响应 200

```jsonc
{
  "candidate_id": "candidate_…",        // 仅 candidate_ready 时非 null
  "status": "candidate_ready",          // candidate_ready | no_feasible_candidate | blocked
  "plan_kind": "PlanResult",            // PlanResult | none
  "candidate_plan": { /* 公共 PlanResult */ },
  "diff": {
    "added": [{"course_id": "ALGO201", "class_id": "algo-02"}],
    "removed": [], "replaced": [],
    "kept": [{"course_id": "DS101", "class_id": "ds-01"}],
    "base_credit": 3.0, "candidate_credit": 6.0, "credit_delta": 3.0,
    "credit_unknown_course_ids": [], "empty": false
  },
  "risks": ["…"],                       // ⚠️ 字符串数组
  "unresolved": ["…"],
  "message": "…",
  "blocked_reason": null,               // 固定取值见 HANDOFF §4
  "data_source": "mock", "generator_kind": "test_double", "plan_digest": "…"
}
```

前端硬规则：

- **只有 `status = candidate_ready` 才是有效候选**；
  `no_feasible_candidate` / `blocked` ⇒ 显示"未生成候选"并**保持原方案不变**；
- 一致性校验：`candidate_ready` 必须带 `candidate_id` + `candidate_plan` + `diff`；
  非 `candidate_ready` 却带 `candidate_plan` ⇒ `unexpected`（⛔ 不接受自相矛盾的响应）；
- `credit_delta = null` 或 `credit_unknown_course_ids` 非空 ⇒ 显示"学分未知"；
- `blocked_reason` 原样展示并按已知取值给出说明（⛔ 不猜测未知原因）。

## 5. `POST /api/v1/ai-planning/adopt`

### 请求

```jsonc
{"candidate_id": "candidate_…", "plan_digest": "…", "accept": true}
```

### 响应 200（⚠️ **不返回方案体**）

```jsonc
{
  "candidate_id": "candidate_…",
  "accepted": true,
  "state": "adopted",                        // adopted | rejected
  "adopted_version": 1,                      // 进程内会话版本号（int）
  "adopted_version_scope": "process_local_session",
  "original_plan_unchanged": false,
  "plan_digest": "…",
  "message": "已采用候选方案（仅在本进程会话内有效，未持久化）。"
}
```

前端硬规则：

1. **⛔ 绝不伪造 `adopted_plan`**：采用成功时，刷新用的方案体只能是 `/solve`
   已经返回、**由后端 Planner 产生**的 `candidate_plan`（保存在内存里）；
2. **只有 `accepted === true && state === 'adopted'` 才刷新当前方案**；
   其它情况（拒绝 / 冲突 / 过期 / 不可用）⇒ **原方案一个字都不改**；
3. `adopted_version_scope` 只接受 `process_local_session`：
   界面必须写明**进程内会话状态、未持久化、服务重启即失效、不代表教务系统已完成选课**；
4. 采用成功后提供**撤销入口**：以原方案为 base 重新解析（⛔ 不修改后端状态）；
5. `accept=false`（保留原案）也必须经过后端确认，并显示 `original_plan_unchanged`。

### 第二次确认面板（保留）

展示：`diff.added / removed / replaced / kept`、学分变化、`risks[]`、`unresolved[]`、
`plan_kind`、`generator_kind`、`data_source`、`blocked_reason`（如有）。
两个按钮：**采用候选** / **保留原案**。

## 6. 错误码 → 前端分类（一一对应）

| HTTP | `error` | 前端 `kind` | 界面行为 |
| --- | --- | --- | --- |
| 503 | `ai_planning_disabled` | `disabled` | 显示"未启用"，隐藏输入 |
| 503 | `ai_planning_model_unavailable` | `model_unavailable` | 显示"模型暂不可用"，原方案不变 |
| 400 | `ai_planning_message_rejected` | `message_rejected` | 提示改写消息（去掉个人信息） |
| 422 | `ai_planning_model_output_invalid` | `model_output_invalid` | "AI 未能理解，请换个说法" |
| 422 | `ai_planning_intent_invalid` | `intent_invalid` | 回到确认面板修正 |
| 422 | `ai_planning_plan_context_invalid` | `plan_context_invalid` | 重新加载当前方案 |
| 409 | `ai_planning_intent_not_confirmable` | `intent_not_confirmable` | 渲染 `ambiguities[]` |
| 409 | `ai_planning_adoption_conflict` | `adoption_conflict` | 刷新候选状态 |
| 404 | `ai_planning_session_not_found` | `session_not_found` | 提示重新解析意图 |
| 410 | `ai_planning_session_expired` | `session_expired` | 提示重新解析 / 重新求解 |
| 501 | `ai_planning_solve_unsupported` | `solve_unsupported` | 说明只支持当前学期 |
| 502 | `ai_planning_candidate_invalid` | `candidate_invalid` | 报告服务端问题，⛔ 不重试 |
| 429 | `ai_planning_budget_exceeded` | `budget_exceeded` | 稍后再试 |
| 404/405（`/status`、无 code） | — | `absent` | **该私有前缀尚未部署** |
| 其它 5xx | — | `server` | 服务端错误，原方案不变 |
| 网络失败 | — | `network` | 无法连接 |
| 2xx 但形状不符 | — | `unexpected` | 停止渲染，⛔ 不补默认值 |

**没有**"500 兜底 + 悄悄回退到 Mock"这条路径。

## 7. 前端必须避免的写法

| ⛔ 不要做 | 原因 |
| --- | --- |
| 把 `test_double` 显示成"DeepSeek 已接入" | 虚构能力 |
| 在 `can_confirm=false` 时仍调 `/solve` | 必然 409；且绕过歧义确认 |
| 自己算 / 改写 `plan_digest` | 后端按上下文计算；不一致必然 410 |
| 在 `/interpret` 响应里找候选方案 | 该接口**只**给草稿 |
| `/adopt` 之后凭空造一份 `adopted_plan` | 后端不返回方案体；伪造等于假成功 |
| 把"已采用"说成"已保存 / 已选课成功" | 只是**进程内会话状态** |
| 失败时用 Mock / fixture 填充候选面板 | 违反 fail-closed 与 provenance |
| 把 `data_source=unknown/mock` 渲染成"真实开课" | Mock/Real 混淆 |
| 在前端保存任何 DeepSeek 密钥 | 密钥只存在于服务器环境 |

## 8. 预览 fixture 清单

| fixture | 覆盖场景 |
| --- | --- |
| `PREVIEW_INTERPRET_OK` | 正常解析（软偏好 + 锁定课程；`can_confirm=true`） |
| `PREVIEW_INTERPRET_WITH_AMBIGUITIES` | `can_confirm=false` + `credit_limit_missing_evidence` |
| `PREVIEW_SOLVE_CANDIDATE` | `candidate_ready`（含 added/removed/kept、学分 +2、风险、未决） |
| `PREVIEW_SOLVE_NO_FEASIBLE` | `no_feasible_candidate`（无候选） |
| `PREVIEW_SOLVE_BLOCKED` | `blocked` + `locked_course_would_change` |
| `PREVIEW_ADOPT_ACCEPTED` | `accepted=true` / `adopted` / `adopted_version=1` |
| `PREVIEW_ADOPT_KEPT` | `accept=false` 保留原案 |
| `PREVIEW_ADOPT_REJECTED` | 冲突（已被处理） |
| `PREVIEW_STATUS_TEST_DOUBLE` / `_LIVE` / `_DISABLED` | 三种可用状态 |

全部带 `（前端预览）` 文案，并在界面显示 `AI_PREVIEW_NOTICE`：
**「仅前端预览 / 非真实模型 / 未调用 Planner」**。

## 9. 个人规划接口（已实现，接口面事实）

`GET /api/v1/personal-planning/curriculum-versions` 与
`POST /api/v1/personal-planning/plan` 由 Agent A 实现，前端按**真实 readiness** 接入：

- 目录未配置 ⇒ 503 `personal_catalog_not_configured` ⇒ 显示"没有已核验的培养方案版本目录"，
  ⛔ **不退回固定 Case A**；
- `planning = null` ⇒ 显示 `planning_skipped_code` / `planning_skipped_reason`
  （`no_course_data` / `no_semester` / `semester_not_bound`），⛔ 不显示"已排好课"；
- 请求体只发送版本 id、`semester`、脱敏已修记录、`preference`、`current_schedule`；
  ⛔ 不发送姓名、学号、成绩单原文或任何凭据。

## 10. 仍然没有验证的部分（不得声称已完成）

| 项 | 状态 |
| --- | --- |
| 真实 DeepSeek 在线调用（`generator_kind=deepseek_live`） | **未验证**（运行环境未注入密钥） |
| 前端 ↔ 真实后端端到端联调 | **未执行**（本轮为契约对齐 + mocked fetch 契约测试） |
| 已核验培养方案目录 / 真实教学班快照 | **BLOCKED**（未装配） |
| 跨学期自动重排 | **不支持**（后端 501 / `blocked`） |
| 会话持久化 / 多实例共享 | **不支持**（进程内） |
