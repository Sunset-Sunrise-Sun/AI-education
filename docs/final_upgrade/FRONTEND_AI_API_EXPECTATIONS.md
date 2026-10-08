# 前端 AI 规划接口预期（Field-Level Contract & Assumptions）

> 归属：**Frontend / Agent B（`feature/ai-planning-frontend`）**。
> 状态：**仅前端预期**。后端（Agent A）尚未实现 `POST /api/v1/ai-planning/*`，
> 本文记录前端 typed adapter 的所有**字段假设**、错误语义与 Mock fixtures。
>
> ⛔ 本文不是公共契约：`/schemas/` 与 `/docs/interfaces/` **未被修改**。
> 真实 A 接口若与本文不一致，前端**只报告差异**，⛔ 不在前端"自动适配"或编造字段。

## 0. 为什么需要这份文档

任务书要求前端使用**可替换的 typed adapter** 开发，且**不能假定 A 的接口已存在**。
因此前端把「AI 规划」当作一个**明确可能不可用**的能力：

- 真实接口未就绪 ⇒ 页面显示「AI 调整尚未配置」，**不伪造规划成功**；
- 离线演示 ⇒ 只能使用**醒目标注**的前端预览 fixture（`source = preview_fixture`），
  ⛔ 生产失败时**不 fallback** 到 fixture。

## 1. 适配层位置与开关

| 项 | 值 |
| --- | --- |
| 文件 | `frontend/src/api/aiPlanning.ts`（typed adapter，唯一出口） |
| 契约类型 | `frontend/src/api/aiPlanningTypes.ts` |
| 预览 fixture | `frontend/src/api/aiPlanningFixtures.ts` |
| 开关 | `VITE_AI_PLANNING_API_ENABLED`（默认 **关闭**） |
| 预览开关 | `VITE_AI_PLANNING_PREVIEW`（默认 **关闭**；打开后只用 fixture 渲染） |

开关语义（互斥且穷尽）：

| `VITE_AI_PLANNING_API_ENABLED` | `VITE_AI_PLANNING_PREVIEW` | 行为 |
| --- | --- | --- |
| `false` | `false` | 默认：面板显示「AI 调整尚未配置」，**不发任何请求** |
| `true` | `false` | 真实模式：请求 `/api/v1/ai-planning/*`；失败如实报错，⛔ 不 fallback |
| 任意 | `true` | 预览模式：只读 fixture，界面必须显示「前端预览 / 非真实模型 / 未调用 Planner」 |
| `true` | `true` | **预览优先**（便于离线演示），并显示预览标识 |

## 2. `POST /api/v1/ai-planning/interpret`

把学生自然语言解析成**待确认意图草稿**。⛔ 该步骤**不得**求解、不得给出候选方案。

### 请求

```jsonc
{
  "utterance": "尽量在大三前补完，这学期尽量轻松，但数据结构必须保留",   // 必填，非空
  "plan_digest": "sha256:…",        // 必填：当前被调整方案的指纹（防串案）
  "target_semester": "2026-1",      // 必填：本次要调整的学期
  "focus_course_id": "62001002",    // 可选：抽屉聚焦课程时的上下文
  "current_schedule_count": 3,      // 可选：仅计数，⛔ 不传课表明细
  "locale": "zh-CN"                 // 可选
}
```

⚠️ 请求体**不含**姓名 / 学号 / 成绩明细 / 头像 / 邮箱；前端适配层结构上无法加入这些字段。

### 响应

```jsonc
{
  "intent_id": "intent-…",              // 必填：后续 confirm / solve 的引用
  "plan_digest": "sha256:…",            // 必填：必须与请求中的 plan_digest 一致
  "data_source": "mock",                // 必填：mock | real
  "generator_kind": "rule_based_template", // 必填：model | rule_based_template | model_unavailable
  "can_confirm": true,                  // 必填：false 时前端禁止进入第一次确认后的求解
  "parsed_intent": {
    "hard_constraints": [               // 硬约束：不可协商；缺省 = 空数组（⛔ 不猜）
      { "code": "keep_course", "course_id": "62001002", "course_name": "数据结构与算法",
        "raw_text": "数据结构必须保留", "evidence": "utterance", "confidence": 0.9 }
    ],
    "soft_preferences": [               // 软偏好：可协商
      { "code": "lighter_semester", "raw_text": "这学期尽量轻松",
        "evidence": "utterance", "confidence": 0.8 }
    ],
    "credit_limit": null,               // number | null；⛔ 未提及必须为 null，前端不得猜默认值
    "locked_course_ids": ["62001002"],  // 必填：即使为空数组也必须给出
    "scope": {                          // 必填
      "semester": "2026-1",
      "horizon": "before_year_3",       // before_year_3 | within_semester | unknown
      "raw_text": "大三前补完"
    },
    "unknowns": [                       // 必填：解析不出来的部分必须显式列出
      { "topic": "毕业学期", "detail": "未说明计划毕业时间", "needs_user_input": true }
    ]
  },
  "ambiguities": [                      // 必填：可能与硬约束冲突 / 需要用户裁决
    { "code": "conflict_with_hard_constraint", "detail": "「尽量轻松」与「必须保留」可能冲突",
      "options": ["保留课程并接受更重的学期", "放弃该课程"] }
  ],
  "message": "已解析为待确认草稿"
}
```

**语义硬要求**

- `plan_digest` 必须回显请求值：不一致 ⇒ 适配层抛 `stale_plan`（前端提示"原方案已变化，请重新解析"）；
- `can_confirm = false` ⇒ 前端**禁止**进入求解，并展示原因；
- `credit_limit = null` ⇒ 前端显示"未指定"并**要求用户确认或填写**，⛔ 不代填。

## 3. `POST /api/v1/ai-planning/solve`

在**已确认**意图上求解候选方案。⛔ 前端不做冲突检测、不填假方案。

### 请求

```jsonc
{
  "intent_id": "intent-…",
  "plan_digest": "sha256:…",           // 必须与 interpret 时一致
  "confirmed_intent": {                // 用户**第一次确认**后的意图（编辑后的最终值）
    "hard_constraints": [ … ],
    "soft_preferences": [ … ],
    "credit_limit": 18,
    "locked_course_ids": ["…"],
    "scope": { … }
  },
  "semester": "2026-1"
}
```

### 响应

```jsonc
{
  "candidate_id": "cand-…",            // status = candidate 时必填
  "status": "candidate",               // candidate | infeasible | unavailable | rejected
  "candidate_plan": { /* 公共 PlanResult 形状 */ },  // status=candidate 时必填，否则必须为 null
  "plan_digest": "sha256:…",           // 候选所基于的原方案指纹
  "candidate_digest": "sha256:…",      // 候选自身指纹，adopt 时回传
  "diff": {                            // status=candidate 时必填
    "added":   [ { "course_id": "…", "course_name": "…", "class_id": "…", "credit": 3 } ],
    "removed": [ { "course_id": "…", "course_name": "…", "class_id": "…", "credit": 3 } ],
    "moved":   [ { "course_id": "…", "from_class": "…", "to_class": "…", "reason": "…" } ],
    "credit_delta": 3,
    "hard_constraint_checks": [
      { "code": "keep_course", "course_id": "62001002", "satisfied": true, "detail": "已保留" }
    ]
  },
  "risks": [ { "course_id": "…", "level": "medium", "reason": "…" } ],
  "unresolved": [ { "type": "schedule_unknown", "message": "…" } ],
  "message": "已生成 1 个候选方案",
  "expires_at": null                   // ISO8601 | null；非空时过期后 adopt 会返回 stale_candidate
}
```

**状态语义**（前端必须分别显示，⛔ 不得都写成"没生成"）：

| `status` | 含义 | 前端行为 |
| --- | --- | --- |
| `candidate` | 成功 | 展示候选 + 对比 + 第二次确认 |
| `infeasible` | 当前约束下无解 | 显示"未生成候选（当前约束下无解）"，原案不变 |
| `unavailable` | 缺少课表 / Planner 未装配 / 模型不可用 | 显示"未生成候选（缺少必要条件）"，列出原因 |
| `rejected` | 输入被拒绝（意图过期 / 违反硬约束） | 显示拒绝原因；可重新解析 |

## 4. `POST /api/v1/ai-planning/adopt`

**第二次确认**。⛔ 只有后端确认成功才能刷新当前方案。

### 请求

```jsonc
{
  "candidate_id": "cand-…",
  "plan_digest": "sha256:…",        // 当前页面上的原方案指纹
  "candidate_digest": "sha256:…",   // 候选指纹，防"换了候选再采用"
  "accept": true                    // true = 采用候选；false = 明确保留原方案
}
```

### 响应

```jsonc
{
  "status": "adopted",              // adopted | rejected | stale_candidate | unavailable
  "adopted_plan": { /* PlanResult */ },  // status=adopted 时必填
  "adopted_digest": "sha256:…",
  "result_version": "v2",           // 结果版本，用于展示"已刷新到第 N 版"
  "message": "已采用候选方案"
}
```

**失败语义**

| `status` | 含义 | 前端行为 |
| --- | --- | --- |
| `adopted` | 成功 | 才允许刷新当前方案；显示新结果版本 |
| `rejected` | 后端拒绝采用 | **原案保持**，显示拒绝原因 |
| `stale_candidate` | 候选或原案已过期 | **原案保持**，提示"可重新求解" |
| `unavailable` | 后端不可用 | **原案保持**，显示不可用原因 |

⛔ 除 `adopted` 之外的任何情况，前端**不得**改变当前方案、也不得显示"已调整成功"。

## 5. 错误与 HTTP 语义（适配层统一分类）

```ts
type AiPlanningErrorKind =
  | 'disabled'        // 开关关闭：一个请求都不发
  | 'not_configured'  // 404 / 501：后端尚未实现该能力
  | 'input'           // 422：请求体被拒绝
  | 'conflict'        // 409：意图或候选过期
  | 'unavailable'     // 503：缺少课表 / 运行时未装配
  | 'server'          // 其它 5xx
  | 'network'         // 请求根本没完成
  | 'unexpected'      // 2xx 但响应形状不符合契约
```

已知错误体形状（尽力解析，⛔ 不假设一定存在）：

```jsonc
{ "detail": { "error": "ai_planning_not_configured", "message": "…" } }
```

- 任何非 2xx ⇒ 适配层抛 `AiPlanningApiError`，**绝不返回兜底数据**；
- 2xx 但结构不符合本文契约 ⇒ `unexpected`，并停止渲染（防止把半截数据当成功）。

## 6. 与 A 的集成差异记录（待 A 实现后核对）

| 待核对项 | 前端假设 | 若不一致 |
| --- | --- | --- |
| 三个路径名 | `/api/v1/ai-planning/{interpret,solve,adopt}` | 只报告差异，不在前端做路径猜测 |
| `plan_digest` 算法 | 服务端定义；前端只做**透传与一致性比较** | 前端不自行计算摘要 |
| `candidate_plan` 形状 | 公共 `PlanResult` | 若为私有形状，需要新增映射并更新本文 |
| 错误体形状 | `{detail:{error,message}}` | 适配层按状态码分类，不依赖 code 文案 |
| 开关与 readiness | 后端未实现 ⇒ 404/501 | 前端显示「尚未配置」 |

## 7. 明确不在本轮范围

- 真实课表图片 OCR（P2 延后，⛔ 不做假 OCR）；
- 通用聊天机器人（AI 面板必须绑定**当前选中补修方案**）；
- 多学期未验证的自动重排；
- 用文本直接覆盖当前课表（⛔ 只能通过 `adopt` 且后端确认成功）。

## 8. 预览 fixture 清单

| fixture | 覆盖场景 | 标识 |
| --- | --- | --- |
| `PREVIEW_INTERPRET_OK` | 正常解析（硬约束 + 软偏好 + 锁定课程 + 未知项） | `source: preview_fixture` |
| `PREVIEW_INTERPRET_LOW_CONFIDENCE` | `can_confirm=false`（解析不足，禁止求解） | 同上 |
| `PREVIEW_SOLVE_CANDIDATE` | 成功候选（含新增 / 移班 / 学分变化 / 风险） | 同上 |
| `PREVIEW_SOLVE_INFEASIBLE` | 无解 | 同上 |
| `PREVIEW_SOLVE_UNAVAILABLE` | 缺少课表 / Planner 未装配 | 同上 |
| `PREVIEW_ADOPT_ADOPTED` | 采用成功 | 同上 |
| `PREVIEW_ADOPT_STALE` | 候选过期 | 同上 |
| `PREVIEW_ADOPT_REJECTED` | 后端拒绝采用 | 同上 |
| `PREVIEW_ERROR_NOT_CONFIGURED` | 后端尚未实现 | 同上 |

每个 fixture 都带 `preview: true` 与固定文案：
**「仅前端预览 / 非真实模型 / 未调用 Planner」**。

## 9. 个人规划接口（已存在，接口面事实）

`POST /api/v1/personal-planning/plan` 已由 Agent A 实现，前端按**真实 readiness** 接入：

- 目录未配置 ⇒ `503 personal_catalog_not_configured` ⇒ 页面显示"没有已核验版本目录"，
  ⛔ **不退回固定 Case A 冒充个人结果**；
- `planning = null` ⇒ 显示 `planning_skipped_code` / `planning_skipped_reason`
  （`no_course_data` / `no_semester` / `semester_not_bound`），
  ⛔ 不显示"已排好课"；
- 前端请求体只发送：`old_version_id` / `target_version_id` / `semester` /
  `student`（`completed.records[]` 的**脱敏**字段）/ `preference` / `current_schedule`；
  ⛔ 不发送姓名、学号、成绩单原文、真实 Key。
