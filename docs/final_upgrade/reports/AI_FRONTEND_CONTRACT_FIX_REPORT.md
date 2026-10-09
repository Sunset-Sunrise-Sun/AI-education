# AI Frontend 契约修复报告（PR #65 Architecture Review）

- **分支**：`feature/ai-planning-frontend`（原分支修复，未新建分支）
- **触发**：PR #65 Architecture Review —— **BLOCKER：前后端协议不一致，暂缓合并**
- **本轮范围**：**只修复前后端接口契约不一致**。
  ⛔ 未重构页面结构；⛔ 未修改后端；⛔ 未改公共 Schema / `/docs/interfaces/`；
  ⛔ 未改 `main` 或任何正式集成分支；**未合并任何 PR**。
- **契约单一来源**：后端分支 `feature/deepseek-planning-controller` 的
  `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`
  （与 `backend/app/api/ai_planning.py` 同一提交；本轮逐字段核对了该 py 文件）。

---

## 1. Review 四点的修复（逐条）

| # | Review 指出 | 修复后行为 | 证据 |
| --- | --- | --- | --- |
| ① | 前端 `interpret` 校验 `request.plan_digest`，后端**没有**该字段 | 请求体改为 `{context, user_message}`；`context = {semester, base_plan, makeup_tasks, course_offerings, preference}`。`plan_digest` 由**后端**计算并返回，前端**只保存、只回传**（⛔ 前端不再计算摘要） | `aiPlanningContract.ts` 的 `AiInterpretRequest`；契约测试断言请求键集合恰为 `['context','user_message']` |
| ② | 前端只识别 `solve.status='candidate'` | 改为 **`candidate_ready` / `no_feasible_candidate` / `blocked`**；只有 `candidate_ready` 才渲染候选，其余显示"未生成候选"且原方案不变 | `SOLVE_STATUSES`；契约测试含"旧值 `candidate` 必须被拒"用例 |
| ③ | 前端要求 `status/adopted_plan`，后端返回 `state/accepted/...` 且**不含方案体** | 改为 `accepted / state / adopted_version / adopted_version_scope / original_plan_unchanged / plan_digest / message`；采用成功时刷新用的方案体**只能**来自 `/solve` 已返回的 `candidate_plan`（保存在内存） | `AiAdoptResponse`（类型里**没有** `adopted_plan`）；契约测试断言 `Object.keys(data)` 不含 `adopted_plan` |
| ④ | 404/501 的含义不只是"接口未配置" | 改为按**后端固定错误码表**逐项分类：404→`session_not_found`、410→`session_expired`、501→`solve_unsupported`、502→`candidate_invalid`、429→`budget_exceeded`、400→`message_rejected`、409→`intent_not_confirmable`/`adoption_conflict`、503→`disabled`/`model_unavailable`；**"该私有前缀尚未部署"**单列为 `absent`（只在 `GET /status` 返回 404/405 且无结构化错误码时） | `ERROR_CODE_TO_KIND` + `STATUS_FALLBACK`；契约测试 `it.each` 覆盖 13 个错误码 |

另外按 Review 要求补充的三条：

1. **`candidate_ready` 才是有效候选** ⇒ 解析器做状态-内容一致性校验：
   `candidate_ready` 缺 `candidate_id`/`candidate_plan`/`diff` ⇒ `unexpected`；
   非 `candidate_ready` 却带 `candidate_plan` ⇒ `unexpected`。
2. **`adopt` 不返回方案体** ⇒ 前端**没有**任何"拼一份 adopted_plan"的代码路径；
   采用事件携带的是 `/solve` 的候选对象（测试断言其 `objective_summary` 来自候选）。
3. **"已采用"只是进程内会话状态** ⇒ `adopted_version_scope` 只接受
   `process_local_session`（其它取值 ⇒ `unexpected`）；界面固定显示
   "进程内会话状态 / 未持久化 / 服务重启即失效 / **不代表**教务系统已完成选课"，
   并提供"以原方案为基准重新调整"的撤销入口。

### 1.1 两次确认**保留并加强**

| 确认 | 位置 | 门禁 |
| --- | --- | --- |
| **执行前确认意图** | `IntentConfirmPanel.vue` | `can_confirm=false` ⇒ 按钮 disabled 且**不发** `/solve`；可编辑学分上限（必须用户给数字，回传带 `evidence`）/ 避开星期 / 锁定课程 |
| **采用前确认方案** | `CandidateComparePanel.vue` | 展示 added/removed/replaced/kept + 学分 + 风险 + 未决；两个按钮：`采用候选方案` / `保留原方案`（后者同样经后端确认） |

### 1.2 新增 `GET /status` 接入

页面初始化调用 `GET /api/v1/ai-planning/status`，区分三种未启用态：
`未部署（404）` / `未启用（enabled=false）` / `已启用但未注入密钥（api_key_configured=false）`，
并把 `enabled / api_key_configured / live_model_available / model` 如实显示。
⛔ 响应里不含密钥（契约测试断言解析结果序列化后不含 `sk-`）。

### 1.3 顺带修正的两处契约细节

- `solve` 的 `risks` / `unresolved` 是**字符串数组**（旧前端按对象数组渲染）；
- `diff` 是 `added / removed / replaced / kept` + `base_credit / candidate_credit /
  credit_delta / credit_unknown_course_ids / empty`；`credit_delta=null` 或
  `credit_unknown_course_ids` 非空时显示"学分未知"（⛔ 不猜学分）。

---

## 2. 修改范围

**新增**

```text
frontend/src/api/aiPlanningContract.ts          # 后端真实契约类型 + 严格解析器
frontend/tests/ai-planning-contract.spec.ts     # 联调契约测试（真实后端形状）
frontend/tests/personal-planning-contract.spec.ts # 个人规划接口契约测试
```

**修改**

```text
frontend/src/api/aiPlanning.ts           # 4 个端点 + 错误码表 + 强制真实路径开关（测试用）
frontend/src/api/aiPlanningFixtures.ts   # fixture 全部改为后端真实形状
frontend/src/api/aiPlanningTypes.ts      # 改为兼容转发（只 re-export 契约文件）
frontend/src/api/personalPlanning.ts     # 503 细分（目录未配置 vs 服务端未就绪）+ 形状校验
frontend/src/composables/useAiPlanning.ts# 状态机按 candidate_ready / accepted / 进程内会话重写
frontend/src/components/ai/AiAdjustDrawer.vue        # status 门禁 + 四阶段渲染
frontend/src/components/ai/IntentConfirmPanel.vue    # 新草稿形状（歧义 / 学分 / 锁定 / 软偏好）
frontend/src/components/ai/CandidateComparePanel.vue # 新 diff 形状 + 阻塞原因
frontend/src/components/views/AiAdjustView.vue       # 指纹改为"后端计算"，新增会话版本提示
frontend/src/App.vue                     # 去掉前端摘要计算；采用回调带会话版本
frontend/src/config.ts                   # endpoints 增加 status
frontend/tests/ai-planning-adapter.spec.ts / -drawer.spec.ts / -app-shell.spec.ts  # 按新契约重写
frontend/.env.example / frontend/README.md
docs/final_upgrade/FRONTEND_AI_API_EXPECTATIONS.md   # 改为"以后端实现为准"的契约说明
```

**删除**：`frontend/src/utils/planDigest.ts`（前端摘要计算 —— 正是 Review ① 的问题根源）。

**⛔ 未改**：`backend/**`（`git diff --stat -- backend/` 为空）、`schemas/**`、
`docs/interfaces/**`、`main`、`feature/final-upgrade`、`feature/final-upgrade-integration-qa`。

---

## 3. 测试与验证（精确命令与结果）

```text
cd frontend && npx vitest run         → 17 文件 / 268 passed（本轮新增/重写后总数）
cd frontend && npx vue-tsc --noEmit   → exit 0
cd frontend && npm run build          → 成功（JS 235.17 kB / CSS 35.59 kB）
cd backend  && $env:PYTHONUTF8=1; python -m pytest -q → 3074 passed / 2 failed / 2 skipped（**后端未改动**）
```

后端 2 个失败为**既有环境差异**（Python 3.14 下 NUL 路径用例 `DID NOT RAISE`），
与开工前基线一致；本轮未修改、未跳过任何后端用例。

### 3.1 新增「真实后端契约形状」测试（Review 明确要求）

`frontend/tests/ai-planning-contract.spec.ts`（39 用例）用**逐字段抄自 HANDOFF** 的 JSON
直接喂给适配层（mocked fetch + `setAiPlanningForceReal(true)` 强制真实路径）：

- `interpret`：请求体恰为 `context` + `user_message`（**断言没有 `plan_digest`**）；
  `context` 键集合；`generator_kind`/`data_source` 未知取值必须被拒；
  `can_confirm=false` + `ambiguities` 是**合法响应**；
- `solve`：`candidate_ready` 正常解析；`blocked` 带 `blocked_reason`；
  `no_feasible_candidate`；`credit_delta=null` 如实保留；
  **状态与内容矛盾必须被拒**（缺候选 / 非 candidate_ready 却带候选）；
  **旧值 `status='candidate'` 必须被拒**；
- `adopt`：请求键集合；成功 → `accepted/state/adopted_version/process_local_session`；
  拒绝 → `accepted=false` + `original_plan_unchanged=true`；
  **断言解析结果不含 `adopted_plan`**；`adopted_version_scope` 只接受 `process_local_session`；
- `status`：正常解析、无密钥；前缀未部署（404 无 code）⇒ `absent`；
  已实现未启用（503 `ai_planning_disabled`）⇒ `disabled`；
- 错误码表逐项 `it.each`（13 项）+ 无 code 时按状态码兜底 + 未知码不被误判成"未配置"。

`frontend/tests/personal-planning-contract.spec.ts`（10 用例）：
503 `personal_catalog_not_configured` ⇒ `not_configured`（**不退回固定 Case A**）；
`planning=null` ⇒ `shouldApplyPersonalPlan` 为 false（⛔ 不显示"已排好课"）；
请求体不含身份字段；`personal_plan_not_projectable` / `..._course_data_unavailable` 分类正确。

### 3.2 界面状态流测试（重写，29 用例）

`ai-planning-drawer.spec.ts` 覆盖：不可用三态、预览标注、
`test_double` 不得说成"DeepSeek 已接入"、第一次确认（学分不猜 / 锁定 / 软偏好 / 歧义禁求解）、
`candidate_ready` 才渲染候选、diff 四类集合、`no_feasible_candidate`、`blocked`、
第二次确认（采用 → 发出 `applied` 且方案体来自候选 + 显示进程内会话 / 保留 / 冲突重试 / 撤销）、
无原方案时**拒绝解析**（不造假上下文）、消息前置校验（个人信息 / 超长）、
预览全程**零真实请求**。

`ai-planning-app-shell.spec.ts`（12 用例）覆盖页面级接线：
采用后当前方案刷新为非 Mock 内容、保留原方案时方案不变、采用被拒时保留候选、
预览全程不发 `/api/v1/ai-planning/*` 请求。

---

## 4. 仍然是 Mock / 未验证的部分（不得声称已完成）

| 项 | 状态 |
| --- | --- |
| 真实 DeepSeek 在线调用（`generator_kind=deepseek_live`） | **未验证**（运行环境未注入密钥） |
| 前端 ↔ 真实后端**端到端**联调 | **未执行**：本轮是"按真实形状写契约测试"，真实 HTTP 联调需要部署含该私有前缀的后端 |
| 已核验培养方案目录 / 真实教学班快照 | **BLOCKED**（未装配） |
| 跨学期自动重排 | **不支持**（后端返回 `blocked` / 501） |
| 会话持久化 | **不支持**（进程内；重启失效） |
| 课表图片 OCR / 通用聊天 | 任务书延后项，本轮未做 |

---

## 5. 关于 404 / 501 的精确说明（Review ④ 的落地）

- **`/status` 返回 404/405 且无结构化错误码** ⇒ 前端 `absent`：
  文案"该私有前缀尚未部署到当前后端"（这是**唯一的**"接口不存在"信号）；
- **任何带结构化 `detail.error` 的 404** ⇒ `ai_planning_session_not_found`
  ⇒ 文案"本次意图 / 候选已不存在（服务可能已重启），请重新解析"；
- **501** ⇒ `ai_planning_solve_unsupported` ⇒ "当前冻结的 Planner 无法表达该意图"；
- **410** ⇒ `session_expired`（指纹变化 / 候选过期）；
- **502** ⇒ `candidate_invalid`（服务端内部问题，界面明确**不建议重试**）。

⛔ 以上任何一条都**不会**触发 Mock / fixture 回退。

---

## 6. 需要人工确认

1. 后端 `feature/deepseek-planning-controller` 的三个新接口路径与字段是否最终定稿
   （本轮严格按 HANDOFF 实现，若定稿有变需要再同步一轮）；
2. 真实联调环境（含该私有前缀的后端 + 模型密钥）何时可用；
3. `adopted_version_scope` 未来若引入持久化取值，前端文案需要同步更新
   （当前解析器会**拒绝**非 `process_local_session` 的取值，这是有意的收紧）。

## 7. 给非专业读者的三句话

1. 这次只改"前后端对不上"的地方：以前前端会自己算一个方案编号、会等后端返回"新方案内容"，
   但后端其实不这么给——现在完全按后端实际返回的字段来做。
2. 现在的规则是：后端说 `candidate_ready` 才算真的算出了候选；点"采用"之后，
   页面用的是**后端算出来的那份候选**，而不是自己拼一份；并且会明确写着
   "这只是本次运行期间临时生效，没有保存，也不等于学校选课成功"。
3. 如果后端还没部署这套 AI 接口，页面会说"尚未部署"，不会假装成功。
