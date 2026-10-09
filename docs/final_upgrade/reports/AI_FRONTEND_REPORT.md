# AI 前端开发报告（Final Upgrade · AI Planning Frontend）

- **Agent**：Builder B（AI 补修规划网页）
- **分支**：`feature/ai-planning-frontend`（起点 `feature/final-upgrade-integration-qa`）
- **日期**：2026-10-08
- **模式**：无人值守；已 push 自己的分支并创建 Draft PR，**未合并任何分支**
- **数据状态**：**Mock / 前端预览 fixture**。
  ⚠️ **当前功能仅使用 Mock 与前端预览数据验证，尚未完成真实数据与真实 AI 接口联调。**

---

## 1. 一句话结论

把单一长页面重组成**三个导航入口**（转专业分析 / 补修路径 / AI 调整），
并实现了围绕**当前选中补修方案**的 AI 对话式调整，严格走
**第一次确认（意图）→ 求解 → 候选对比 → 第二次确认（采用 / 保留）**；
后端 `/api/v1/ai-planning/*` 由 A 并行开发且**尚未存在**，因此前端用
**独立 typed adapter + 明确标注的前端预览 fixture** 完成可运行交互：
未配置时显示"尚未配置"、失败时如实报错，**不伪造后端规划成功**。
旧 Case A 的四区块与解释入口**原样保留**在「补修路径」视图。

---

## 2. 信息架构重组

| 入口 | 内容 | 数据来源 |
| --- | --- | --- |
| **转专业分析** | 版本选择（原 / 目标）、认定状态分布、培养要求缺口（逐条 `MakeupTask`）、数据来源标记 | `GET /api/v1/personal-planning/curriculum-versions`、`POST /api/v1/personal-planning/plan`（**已存在**，按真实 readiness） |
| **补修路径**（默认） | 当前学期精确课表、后续学期课程级条件路径、优先级线索 / 风险 / 人工确认；旧 0–5 区块（用户输入、MakeupTask、教学班、Preference、PlanResult、解释） | Mock Demo / Real Planning / 解释接口（**均已存在**） |
| **AI 调整** | 两次确认说明 + 打开 AI 抽屉的入口与当前调整对象 | AI adapter（**后端尚未实现**） |

实现方式：`App.vue` 变成薄外壳（导航 + 抽屉 + 状态），
旧内容整体迁入 `components/views/MakeupPathView.vue`，
**未改名任何既有 `data-testid`，未改公共契约**，旧 11 个测试文件 154 用例全部继续通过。

---

## 3. AI 交互实现点（P0）

### 3.1 第一次确认：待确认意图草稿

`components/ai/IntentConfirmPanel.vue` 展示并可编辑：

- **硬约束**（`hard_constraints[]`，含 `raw_text` / `evidence` / `confidence`）；
- **软偏好**（`soft_preferences[]`）；
- **学分上限**：后端给 `null` 时显示**"未指定"**并明确写出
  **"页面不会替你猜一个默认值"**，可留空或填数字；
- **锁定课程**：只能从**当前方案已有课程**（`MakeupTask` 上下文）勾选，⛔ 不凭空造课程；
- **范围**（学期 / horizon / 原话）与**未知项**（`unknowns[]`，标"需要你补充"）；
- **歧义**（`ambiguities[]`）在草稿中一并呈现（来自后端）。

⛔ **确认前不可进入有状态的 solve**：确认按钮由 `can_confirm` + 草稿存在共同控制；
`can_confirm = false` 时按钮禁用并显示"不足以求解"的原因。

### 3.2 求解：调用真正的规划工具 API（前端零计算）

- 只有通过第一次确认后才调用 `POST /api/v1/ai-planning/solve`；
- 前端**不做冲突检测、不选教学班、不排序、不填充假方案**；
- 状态被严格区分（⛔ 不都写成"没生成"）：

| `status` | 界面 |
| --- | --- |
| `candidate` | 展示候选与对比 |
| `infeasible` | "未生成候选：当前约束下无解" |
| `unavailable` | "未生成候选：缺少必要条件"（并列出后端说明） |
| `rejected` | "未生成候选：输入被拒绝" |

### 3.3 候选对比（`CandidateComparePanel.vue`）

只展示**后端给出的差异**：新增 / 移除课程、教学班调整、学分变化、
**硬约束核对**（满足 / 未满足）、候选风险、未决事项；
原方案明细缺失时如实说明"当前上下文没有可对比的原方案明细"，⛔ 不用候选回填。

### 3.4 第二次确认：采用 / 保留

- `采用候选方案` → `POST /api/v1/ai-planning/adopt`（`accept: true`），
  **只有后端返回 `adopted` 才刷新当前方案**；
- `保留原方案` → 同样提交（`accept: false`），明确显示"已确认保留原方案"；
- `rejected` / `stale_candidate` / `unavailable` ⇒ **当前方案一个字都不改**，
  抽屉留在候选阶段并提示可"重新求解"；
- 方案指纹（`plan_digest`）在请求与响应间必须一致，不一致 ⇒ `stale_plan` 冲突。

### 3.5 抽屉形态与上下文

- 桌面：右侧抽屉（`width: min(520px, 96vw)`）+ 半透明遮罩；
- 移动端：全屏（`width: 100vw`，媒体查询 720px）；
- 聚焦课程：从教学班行「就这门课调整」进入时携带 `focus_course_id`，
  并明确写出"只作为解析上下文，⛔ 不会自动改这门课"；
- **复用已有解释入口**："查看依据"仍在补修路径第 5 区块，明确标注规则模板非 AI
  （未改动解释组件与后端解释服务）。

---

## 4. 哪些是真 API、哪些只是 Mock / 未接入（重要）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `GET /api/v1/mock/demo` | ✅ **已接入（Mock）** | 永久 Mock 通道，页面基础数据 |
| `POST /api/v1/plan` | ✅ **已接入（Real）** | 默认开关关闭；未装配 ⇒ 503 如实显示，⛔ 不 fallback |
| `POST /api/v1/explanation/plan` | ✅ **已接入（规则模板）** | 默认开关关闭；未配置模型 ⇒ 界面显示「规则模板（非 AI）」 |
| `GET /api/v1/personal-planning/curriculum-versions` | ✅ **已接入（真实 readiness）** | 目录未配置 ⇒ 503 ⇒ 显示"没有已核验版本目录"，⛔ 不退回 Case A |
| `POST /api/v1/personal-planning/plan` | ✅ **已接入（真实 readiness）** | `planning = null` ⇒ 显示跳过原因码，⛔ 不显示"已排好课" |
| `POST /api/v1/ai-planning/interpret` | ⛔ **后端未实现** | 前端 adapter 已就绪；默认关闭 ⇒ 显示"尚未配置" |
| `POST /api/v1/ai-planning/solve` | ⛔ **后端未实现** | 同上 |
| `POST /api/v1/ai-planning/adopt` | ⛔ **后端未实现** | 同上 |
| 前端预览 fixture | ⚠️ **仅前端预览** | 必须显示「仅前端预览 / 非真实模型 / 未调用 Planner」 |

**没有任何真实模型调用**：解析结果在预览中标注 `generator_kind = rule_based_template`，
界面显示「规则模板（非 AI）」；接入真实模型属受控事项，本轮⛔ 未引入任何密钥或服务。

---

## 5. 接口假设文档与可替换 adapter

- `docs/final_upgrade/FRONTEND_AI_API_EXPECTATIONS.md`：逐字段记录
  三个路径的请求 / 响应、状态语义、错误分类、`plan_digest` 一致性要求、
  预览 fixture 清单，以及与 A 的**集成差异核对表**；
- `src/api/aiPlanningTypes.ts`：契约类型唯一来源；
- `src/api/aiPlanning.ts`：**唯一**知道 `/api/v1/ai-planning/*` 的地方，含：
  - `interpretIntent` / `solvePlan` / `adoptCandidate`；
  - 错误分类 `disabled / not_configured(404,501) / input(422) / conflict(409) /
    unavailable(502,503,504) / server / network / unexpected`；
  - 结构校验：缺字段、`status` 与内容矛盾（如 `infeasible` 却带候选、
    `candidate` 却缺 `diff`、`adopted` 却无 `adopted_plan`）⇒ `unexpected`，
    ⛔ **不补默认值、不猜测**；
  - ⛔ 真实路径**没有**任何 fixture 回退分支。

---

## 6. 测试与验证（精确命令与结果）

```text
cd frontend && npx vitest run          → 15 文件 / 223 passed（本轮新增 69 用例）
cd frontend && npx vue-tsc --noEmit    → exit 0
cd frontend && npm run build           → 成功（dist JS 209.62 kB / CSS 35.59 kB）
cd backend  && $env:PYTHONUTF8=1; python -m pytest -q  → 3074 passed / 2 failed / 2 skipped（未改动后端）
```

后端 2 个失败**非本轮引入**：`test_curriculum_docx_reader` 与 `test_curriculum_json_reader`
的 `DID NOT RAISE CurriculumNormalizationError` 用例（本机 Python 3.14 对含 NUL 字节的路径
不再抛 `OSError`），**开工前基线即为 2 failed / 3074 passed**，本轮**未修改后端任何文件**
（`git diff --stat -- backend/` 为空），也未修改 / 跳过这些用例。

### 6.1 新增测试（69 用例）

| 文件 | 用例 | 覆盖 |
| --- | --- | --- |
| `tests/ai-planning-adapter.spec.ts` | 22 | 开关与能力状态、错误体解析、**预览标注**、404/503/network/缺字段/digest 不一致/状态矛盾、**不 fallback**、backend 来源包裹 |
| `tests/ai-planning-drawer.spec.ts` | 24 | 未配置态、预览标注、草稿内容、学分"不猜"、锁定/解锁、`can_confirm=false` 禁求解、候选对比、无解/缺条件、采用/过期/拒绝/保留/重新求解、聚焦上下文、全屏类名、长文本、预览零请求 |
| `tests/ai-planning-app-shell.spec.ts` | 12 | 三入口导航与默认视图、旧区块保留、个人分析视图切换、当前学期课表、风险/人工确认、聚焦课程开抽屉、两次确认端到端（预览）、**采用后方案刷新**、保留 / 过期时方案不变、预览不发真实请求 |
| `tests/transfer-analysis-view.spec.ts` | 11 | 目录未配置（503）不提供版本、空目录列原因码、通道未启用、读取失败、版本选择约束、只发两个版本 id、`planning = null` 不显示"已排好课"、状态分布、缺口来源字段、仅在 `planning != null` 时提供"用作当前方案" |

### 6.2 手工检查（窄屏 / 长文本 / loading / 错误）

- 窄屏：`.ai-drawer--fullscreen` 在 ≤720px 全屏；导航入口改为整行；
- 长文本：抽屉与解释面板均不截断、不重写（测试断言原样渲染）；
- loading：解释 / 个人规划 / 求解各有独立的进行中文案，按钮禁用；
- 错误：每个通道失败都显示"失败类型 + 不会伪造"的说明，且**当前方案不变**。

### 6.3 未做真实浏览器 E2E（如实记录）

本机环境未启动浏览器自动化工具，因此**没有**执行真实浏览器端到端；
所有结论来自组件 / 适配器层测试 + `vue-tsc` + 生产构建。
真实联调需要：A 的 `/api/v1/ai-planning/*` 实现 + 已核验目录 + 真实教学班供给。

---

## 7. 文件列表

**新增**

```text
docs/final_upgrade/FRONTEND_AI_API_EXPECTATIONS.md
docs/final_upgrade/reports/AI_FRONTEND_REPORT.md
frontend/src/api/aiPlanningTypes.ts
frontend/src/api/aiPlanning.ts
frontend/src/api/aiPlanningFixtures.ts
frontend/src/api/personalPlanning.ts
frontend/src/api/personalPlanningFixtures.ts
frontend/src/composables/useAiPlanning.ts
frontend/src/composables/usePersonalPlanning.ts
frontend/src/utils/planDigest.ts
frontend/src/components/ai/AiAdjustDrawer.vue
frontend/src/components/ai/IntentConfirmPanel.vue
frontend/src/components/ai/CandidateComparePanel.vue
frontend/src/components/views/MakeupPathView.vue
frontend/src/components/views/TransferAnalysisView.vue
frontend/src/components/views/AiAdjustView.vue
frontend/tests/ai-planning-adapter.spec.ts
frontend/tests/ai-planning-drawer.spec.ts
frontend/tests/ai-planning-app-shell.spec.ts
frontend/tests/transfer-analysis-view.spec.ts
```

**修改**

```text
frontend/src/App.vue            # 薄外壳：三入口导航 + AI 抽屉 + 状态；旧区块迁入 MakeupPathView
frontend/src/config.ts          # 新增 AI / 个人规划 endpoint 与 4 个默认关闭的开关
frontend/src/styles/base.css    # 导航 / 视图 / 抽屉 / 候选对比样式（追加，不改旧规则）
frontend/vitest.config.ts       # 测试环境打开"预览"（不是真实接口）
frontend/.env.example           # 文档化 4 个新开关及其边界
frontend/README.md              # 新增第 9.6 节：三入口、AI 调整用法、三种数据模式、验收步骤
```

**明确未改**：`backend/**`（`git diff --stat -- backend/` 为空）、
`schemas/**`、`docs/interfaces/**`、`main` / `feature/final-upgrade` / 集成候选分支、
旧 PR #62/#63/#64、Agent A 分支与文件。

---

## 8. 与 A 的并行接口差异（待 A 实现后核对）

| 项 | 前端假设 | 若不一致 |
| --- | --- | --- |
| 路径 | `/api/v1/ai-planning/{interpret,solve,adopt}` | 只报告差异，**不在前端猜路径** |
| `plan_digest` | 服务端定义；前端只做透传与一致性比较 | 若算法不同，前端仍只比较回显 |
| `candidate_plan` | 公共 `PlanResult` 形状 | 若为私有形状，需要新增映射并更新预期文档 |
| `generator_kind` | 沿用 `explanation-v1` 三值（`model` / `rule_based_template` / `model_unavailable_fell_back_to_template`） | 若命名不同，适配层新增枚举并显示 |
| 错误体 | `{detail:{error,message}}`（尽力解析） | 按状态码分类，不依赖 code 文案 |
| 开关语义 | 关闭 ⇒ 不发请求 | 若后端要求"始终可调用"，需要新的 readiness 约定 |

**共享文件冲突风险**：`frontend/src/App.vue` 与 `frontend/src/config.ts` 是两边都可能改的入口。
本轮的改动是**结构性重组 + 追加**（旧区块整体迁入新视图组件，未改旧 `data-testid`）；
若与 A 的分支冲突，**只报告、不跨分支解决**。

---

## 9. 已知局限

1. `/api/v1/ai-planning/*` **后端尚未实现**：真实模式打开后会得到 404，页面显示"尚未配置"；
2. 预览 fixture 是**人工构造**的演示数据，不是模型输出，也不是 Planner 结果；
3. 个人规划目录与真实教学班供给尚未配置，因此真实个人规划与真实候选仍不可用（BLOCKED）；
4. 未引入 vue-router：三入口用内部状态切换（避免为演示新增依赖）；
5. 未做课表图片 OCR、通用聊天、多学期自动重排（任务书明确的延后项），
   ⛔ 也没有用假 OCR / 假模型调用充数；
6. 未执行真实浏览器 E2E（见 §6.3）。

---

## 10. 给非专业读者的六句话

1. **现在能做什么**：网页分成三块——先看"转专业后缺什么课"，再看"这学期怎么排、以后几学期怎么补"，
   最后可以对着当前方案用一句自然语言说"我想怎么调"。
2. **用户会看到什么**：说一句需求后，系统先把"我理解的意思"摆出来让你确认（第一次确认），
   确认后才去算候选方案；候选会和原方案并排对比，你再决定"采用"还是"保留原方案"（第二次确认）。
3. **主要代码在哪**：页面外壳 `frontend/src/App.vue`；三个视图在
   `frontend/src/components/views/`；AI 抽屉在 `frontend/src/components/ai/`；
   与后端对接的适配层在 `frontend/src/api/aiPlanning.ts`。
4. **怎么运行**：`cd backend && python -m uvicorn app.main:app --reload`，然后
   `cd frontend && npm run dev`；想离线看 AI 交互效果，在 `frontend/.env.local` 写
   `VITE_AI_PLANNING_PREVIEW=true` 后重启。
5. **怎么测试**：`cd frontend && npx vitest run`（223 个用例）、`npx vue-tsc --noEmit`、
   `npm run build`。
6. **出问题先检查什么**：先看 AI 面板顶部显示的"通道"是**尚未配置**还是**前端预览**；
   再确认 `.env.local` 里对应的开关是否打开；若打开了真实接口却报"尚未配置"，
   说明后端 `/api/v1/ai-planning/*` 还没实现（这是当前正确状态，不是页面故障）。
