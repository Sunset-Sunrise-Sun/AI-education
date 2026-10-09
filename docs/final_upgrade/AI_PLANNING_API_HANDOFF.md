# AI Planning API Handoff（前后端临时协作契约）

> 状态：**新内部路由，已实现，待 Reviewer / 负责人确认**
> 分支：`feature/deepseek-planning-controller`
> ⚠️ 本文件描述的接口是**私有前缀**下的新接口，
> **不是**预先授权修改 `/docs/interfaces/` 或 `/schemas/`。
> 前端（Agent B）**可以直接按本文件实现**；如后端实现与本文件有差异，
> 以本文件当前内容为准（本文件与代码在同一提交里）。

## 0. 一句话说明

```text
POST /interpret   自然语言 → 结构化意图草稿（只读，不求解、不改方案）
POST /solve       用户确认后的意图 → 受控 Planner 产生的候选方案 + 确定性差异
POST /adopt       用户二次确认 → 采用 / 拒绝候选（绑定方案指纹）
GET  /status      后端如实报告"真实 DeepSeek 是否可能可用"
```

前缀：`/api/v1/ai-planning`。默认**关闭**（`AI_PLANNING_ENABLED=false`）。

## 1. 全局约定

| 约定 | 说明 |
| --- | --- |
| 请求体 | `additionalProperties: false` —— 多余字段一律 **422**（含 `student_name` / `student_id` 等身份字段） |
| `plan_digest` | 64 位十六进制 SHA-256，由后端根据"学期 + 当前方案 + 补修任务 + 教学班 + 偏好"计算。**必须原样回传** |
| `intent_id` / `candidate_id` | 不透明字符串（内容派生哈希），前端**只回传、不解析** |
| 会话范围 | 进程内存储；**重启即失效** ⇒ 旧 id 返回 404/410，前端应提示"重新解析意图" |
| 幂等 | `interpret` 对同一内容幂等（同 id）；`adopt` **不幂等**（重复采用 → 409） |
| 时间 | 候选有 TTL（`AI_PLANNING_ADOPT_TTL_SECONDS`，默认 900s），过期 → 410 |
| 不变量 | **任何失败路径都不改变当前方案**；候选是独立对象，只有 `adopt(accept=true)` 才推进版本 |

### 1.1 `generator_kind`（如实标注，⛔ 只有三种）

```text
deepseek_live   真实 DeepSeek 在线调用成功（唯一可声称"已接入"的取值）
test_double     注入的测试替身模型（用于无密钥测试；⛔ 不是线上模型）
unavailable    任何未成功的情况
```

前端**必须**按取值显示不同文案，⛔ 不得把 `test_double` 显示成"AI 已接入"。

### 1.2 `data_source`

```text
real     上下文中所有教学班都是 real
mock     上下文中所有教学班都是 mock
mixed    real 与 mock 混合
unknown  本次没有任何教学班输入
```

由**教学班自身**的 `data_source` 判定，与页面处于哪个模式无关。⛔ `unknown` 不等于 `real`。

### 1.3 通用错误体

```json
{"detail": {"error": "<fixed_code>", "message": "<面向用户的安全说明>"}}
```

| HTTP | `error` | 含义 | 前端应做什么 |
| --- | --- | --- | --- |
| 503 | `ai_planning_disabled` | `AI_PLANNING_ENABLED` 未打开 | 显示"AI 调整未启用"，隐藏输入框 |
| 503 | `ai_planning_model_unavailable` | 无密钥 / 401 / 402 / 429 / 5xx / 超时 / 空输出 | 显示"模型暂不可用"，保留原方案 |
| 400 | `ai_planning_message_rejected` | 消息为空 / 超长 / **疑似个人信息** | 提示改写为只描述选课需求 |
| 422 | `ai_planning_model_output_invalid` | 模型输出结构非法 / 幻觉课程号 / 教学班号 | 提示"AI 未能理解，请换个说法" |
| 422 | `ai_planning_intent_invalid` | 确认意图形状或取值非法（含学分无依据） | 回到确认面板修正 |
| 422 | `ai_planning_plan_context_invalid` | 方案上下文自相矛盾（学期不一致 / 重复身份 / 缺字段） | 重新加载当前方案 |
| 409 | `ai_planning_intent_not_confirmable` | 意图仍有未消解歧义 | 渲染 `ambiguities[]` 让用户回答 |
| 409 | `ai_planning_adoption_conflict` | 重复采用 / 已拒绝候选 | 刷新候选状态 |
| 404 | `ai_planning_session_not_found` | id 不存在（进程重启 / 被淘汰） | 提示重新解析 |
| 410 | `ai_planning_session_expired` | 指纹不符 / 候选过期 | 提示重新解析或重新求解 |
| 501 | `ai_planning_solve_unsupported` | 冻结 Planner 无法表达该意图 | 说明当前只支持当前学期调整 |
| 502 | `ai_planning_candidate_invalid` | Planner 返回的对象不是合法 `PlanResult` | 报告内部错误，不要重试 |
| 429 | `ai_planning_budget_exceeded` | 本次请求的模型调用次数超限 | 稍后再试 |

⛔ 这些路径**全部有边界**，不存在"500 兜底 + 悄悄回退到 Mock/演示数据"。

---

## 2. `GET /api/v1/ai-planning/status`

**用途**：页面初始化时决定是否显示"AI 调整"输入框，以及显示哪种未启用态。

```json
{
  "enabled": false,
  "live_model_available": false,
  "api_key_configured": false,
  "model": "deepseek-flash",
  "base_url": "https://api.deepseek.com",
  "max_calls_per_request": 3,
  "request_timeout_seconds": 20.0,
  "adopt_ttl_seconds": 900,
  "generator_kind_when_live": "deepseek_live",
  "data_source_note": "上下文 data_source 由教学班自身的 data_source 判定（mock / real / mixed / unknown）；没有教学班输入时为 unknown，⛔ 不默认成 real。"
}
```

⛔ 响应中**永远不包含密钥**，只有布尔 `api_key_configured`。

页面建议文案：

- `enabled=false` → "AI 调整未启用（服务器未开启 AI_PLANNING_ENABLED）"
- `enabled=true, api_key_configured=false` → "AI 调整已开启但未注入模型密钥，无法解析意图"
- `enabled=true, api_key_configured=true` → 正常输入框

---

## 3. `POST /api/v1/ai-planning/interpret`

**只读**：不生成方案、不改任何状态。

### 请求

```json
{
  "context": {
    "semester": "2026-1",
    "base_plan": {
      "status": "partially_feasible",
      "selected_classes": [{"course_id": "DS101", "class_id": "ds-01"}],
      "changes": [],
      "risks": [],
      "unresolved": [],
      "objective_summary": "…"
    },
    "makeup_tasks": [
      {"course_id": "DS101", "course_name": "数据结构", "credit": 3,
       "status": "required", "prerequisites": []}
    ],
    "course_offerings": [
      {"course_id": "DS101", "course_name": "数据结构", "class_id": "ds-01",
       "semester": "2026-1", "credit": 3.0, "data_source": "mock",
       "meetings": [{"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1, 3]}]}
    ],
    "preference": {"max_credit": 22, "avoid_cross_campus": false,
                   "preferred_courses": [], "avoid_times": [], "notes": null}
  },
  "user_message": "这学期太累，数据结构必须保留，尽量别在周五上课"
}
```

> `base_plan` / `makeup_tasks` / `course_offerings` / `preference` 都是**现有公共对象**，
> 前端复用已有类型即可；`context` 只是把它们打包在一起。

### 响应 200

```json
{
  "intent_id": "intent_b0c38498f4423f57c…",
  "plan_digest": "e4df931cec5e9c89…",
  "parsed_intent": {
    "summary": "学生想降低负荷并保留数据结构",
    "scope": "current_semester",
    "target_semester": "2026-1",
    "hard_constraints": [],
    "soft_preferences": [
      {"kind": "prefer_fewer_credits", "value": null,
       "note": "学生表达了降低负荷的意愿，但未给出学分数字"},
      {"kind": "avoid_weekday", "value": 5, "note": "尽量避开周五"}
    ],
    "locked_courses": [
      {"course_id": "DS101", "class_id": "ds-01", "reason": "学生明确要求保留该课程"}
    ],
    "confidence": 0.6,
    "notes": [],
    "ambiguities": []
  },
  "ambiguities": [],
  "data_source": "mock",
  "generator_kind": "test_double",
  "generator_note": "注入的测试替身模型（不是线上模型）",
  "model_id": "test-rule-fake",
  "can_confirm": true,
  "state": "intent_draft",
  "token_usage_estimate": {"prompt": 412, "completion": 96, "total": 508},
  "message": "已生成意图草稿，请确认后再求解。"
}
```

### 第一确认面板需要做三件事

1. 允许用户**编辑**：学分上限数值、锁定课程、软偏好、调整范围；
2. 逐条渲染 `ambiguities[]`：
   ```json
   {"code": "credit_limit_missing_evidence",
    "question": "你说的“少上一点 / 太累”没有给出明确学分上限。请填写本学期的学分上限（例如 22），系统不会替你猜。",
    "detail": "模型未给出可验证的学分上限依据"}
   ```
   **固定歧义码**：
   `credit_limit_missing_evidence` / `credit_limit_conflicts_with_declared_max` /
   `locked_course_unknown` / `target_course_unknown` / `target_class_unknown` /
   `adjustment_scope_ambiguous` / `adjustment_scope_unsupported` /
   `constraint_kind_unknown` / `soft_preference_not_executable` / `no_adjustable_target`
3. `can_confirm=false` 时**禁用**确认按钮。

⚠️ `token_usage_estimate` 是**估算**（不是计费口径），只用于展示成本量级。

### 约束 `kind` 白名单

| `kind` | 语义 | 是否可作硬约束 |
| --- | --- | --- |
| `max_credit_limit` | 本学期学分上限（**必须由用户给出数字**） | ✅ |
| `lock_course` | 保留某门课（配合 `locked_courses[]`） | ✅ |
| `exclude_course` | 排除某门课 | ⚠️ 当前求解**不支持** → `blocked` / `ai_planning_solve_unsupported` |
| `avoid_weekday` | 尽量避开某天 | 软 |
| `prefer_fewer_credits` | 尽量降低学分 | 软 |
| `prefer_keep_prerequisites` | 尽量保留先修链 | 软 |

---

## 4. `POST /api/v1/ai-planning/solve`

**只有用户确认后才调用。** 服务器会校验
`confirmed_intent.plan_digest === 当前上下文指纹`，否则 410。

### 请求

```json
{
  "intent_id": "intent_b0c38498f4423f57c…",
  "plan_digest": "e4df931cec5e9c89…",
  "confirmed_intent": {
    "plan_digest": "e4df931cec5e9c89…",
    "semester": "2026-1",
    "scope": "current_semester",
    "target_semester": "2026-1",
    "hard_constraints": [
      {"kind": "max_credit_limit", "value": 22, "evidence": "用户在确认面板填写"}
    ],
    "soft_preferences": [
      {"kind": "avoid_weekday", "value": 5, "note": "尽量避开周五"}
    ],
    "locked_courses": [
      {"course_id": "DS101", "class_id": "ds-01", "reason": "用户要求保留"}
    ],
    "user_note": null
  }
}
```

⚠️ **硬约束必须带 `evidence`**：缺少依据的 `max_credit_limit` 一律 422
（`ai_planning_intent_invalid`）。这是"AI 不得把'少上点课'换算成固定学分数"的落地方式。

### 响应 200（有候选）

```json
{
  "candidate_id": "candidate_1b69e89768ff7e4e…",
  "status": "candidate_ready",
  "plan_kind": "PlanResult",
  "candidate_plan": {
    "status": "partially_feasible",
    "selected_classes": [
      {"course_id": "DS101", "class_id": "ds-01"},
      {"course_id": "ALGO201", "class_id": "algo-02"}
    ],
    "changes": [{"course_id": "ALGO201", "from_class": null, "to_class": "algo-02",
                 "reason": "新增 required 任务仅有一个…CLEAR 教学班…"}],
    "risks": [],
    "unresolved": [{"type": "manual_confirmation", "message": "…"}],
    "objective_summary": "受限 Planner 本学期建议课表：…"
  },
  "diff": {
    "added":    [{"course_id": "ALGO201", "class_id": "algo-02"}],
    "removed":  [],
    "replaced": [],
    "kept":     [{"course_id": "DS101", "class_id": "ds-01"}],
    "base_credit": 3.0,
    "candidate_credit": 6.0,
    "credit_delta": 3.0,
    "credit_unknown_course_ids": [],
    "empty": false
  },
  "risks": ["本次上下文的教学班数据来源为 mock，不代表真实教务开课。"],
  "unresolved": ["课程 NET301 的补修认定仍需人工确认，不自动新增。"],
  "message": "已按确认意图调用受控 Planner 生成候选；请对照差异后决定是否采用。",
  "blocked_reason": null,
  "data_source": "mock",
  "generator_kind": "test_double",
  "plan_digest": "e4df931cec5e9c89…"
}
```

### 响应 200（无变化 / 阻塞）

```json
{
  "candidate_id": null,
  "status": "blocked",
  "plan_kind": "none",
  "candidate_plan": null,
  "diff": null,
  "risks": [],
  "unresolved": ["锁定的课程 DS101（班次 ds-01）在候选里发生了变化。"],
  "message": "候选破坏了用户锁定的课程，已拒绝该候选并保留原方案。",
  "blocked_reason": "locked_course_would_change",
  "data_source": "mock",
  "generator_kind": "test_double",
  "plan_digest": "e4df931cec5e9c89…"
}
```

固定 `blocked_reason`：
`planner_not_configured` / `planner_rejected_input: <ExcType>` /
`locked_course_would_change` / `candidate_references_unavailable_class` /
`exclude_course_hard_constraint_not_supported_by_frozen_planner` /
`cross_semester_adjustment_not_supported`

`status` 取值：`candidate_ready` / `no_feasible_candidate` / `blocked`。

> `candidate_plan` 是 Planner **实际产生**的 `PlanResult`；
> `diff` / `risks` 完全由后端**确定性**计算，⛔ 不来自模型输出。
> 前端渲染时请同时显示 `plan_kind` 与 `blocked_reason`，⛔ 不要伪造"已排好课"。

### 第二确认面板

展示：`diff.added / removed / replaced / kept`、`diff.credit_delta`
（为 `null` 时说明"学分未知"）、`risks[]`、`unresolved[]`。
两个按钮：**采用候选** / **保留原案**（后者可直接调 `/adopt` `accept=false`）。

---

### 联合验收后澄清（非公共契约变更）

- `diff.replaced[]` 非空行采用 `{course_id, from_class, to_class}`；`added[]`、`removed[]`、`kept[]` 则采用 `{course_id, class_id}`。同一次换班可能同时在教学班键集合差异中出现新增与移除，界面不应重复理解为多门课程。
- `status=no_feasible_candidate` 时 `candidate_id` 可能非空，但仅是记录标识，不能据此提供采用功能；只有 `candidate_ready` 且候选及差异有效时才能采用。
- `locked_courses[].reason` 可缺省或为 null，不得虚构说明。

## 5. `POST /api/v1/ai-planning/adopt`

### 请求

```json
{
  "candidate_id": "candidate_1b69e89768ff7e4e…",
  "plan_digest": "e4df931cec5e9c89…",
  "accept": true
}
```

### 响应 200

```json
{
  "candidate_id": "candidate_1b69e89768ff7e4e…",
  "accepted": true,
  "state": "adopted",
  "adopted_version": 1,
  "adopted_version_scope": "process_local_session",
  "original_plan_unchanged": false,
  "plan_digest": "e4df931cec5e9c89…",
  "message": "已采用候选方案（仅在本进程会话内有效，未持久化）。"
}
```

⚠️ **必须如实展示**：`adopted_version_scope = process_local_session`
表示"进程内会话版本"，**不是**持久账户版本，也没有跨设备同步。
前端应在采用成功后显示该提示，并在提示里给出"撤销"入口（再次以旧方案为 base 重新 interpret）。

拒绝时：`accept=false` → `accepted=false`、`state="rejected"`、
`original_plan_unchanged=true`、`adopted_version` 不变。

---

## 6. 前端必须避免的写法

| ⛔ 不要做 | 原因 |
| --- | --- |
| 把 `test_double` 显示成"DeepSeek 已接入" | 虚构能力 |
| 在 `can_confirm=false` 时仍然调 `/solve` | 必然 409；且绕过歧义确认 |
| 自己拼 `confirmed_intent` 而不回传后端给的 `plan_digest` | 必然 410 |
| 在 `/interpret` 响应里找候选方案 | 该接口**只**给草稿 |
| 失败时自动改用 Mock 结果填充候选面板 | 违反 fail-closed 与 provenance |
| 把 `data_source=unknown/mock` 渲染成"真实开课" | Mock/Real 混淆 |
| 在前端保存任何 DeepSeek 密钥 | 密钥只存在于服务器环境 |

## 7. 本轮实际实现与本文档的差异

**无差异**。本文档与同一提交里的 `backend/app/api/ai_planning.py` 一一对应；
所有字段名、状态码、错误码都来自实际代码与测试。

## 8. ⚠️ 本轮尚未验证的部分（不得声称已完成）

| 项 | 状态 |
| --- | --- |
| 真实 DeepSeek 在线调用 | **NOT VERIFIED** — 运行环境未注入密钥 |
| 真实已核验培养方案目录 / 真实教学班快照 | **BLOCKED** — 未装配（沿用上一轮结论） |
| 跨学期自动重排 | **不支持** — 明确 501 / `blocked` |
| 会话持久化 / 多实例共享 | **不支持** — 进程内存储，重启失效 |
| 前端页面 | 未实现（属 Agent B） |
