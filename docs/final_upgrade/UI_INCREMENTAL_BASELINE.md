# 旧版（main）与新版（feature/final-upgrade）前端对比

> 本文件是**第一阶段交付物**：只做对比与结论，⛔ 不改代码。
>
> - 旧版参考：`main` = `c75b6da`
> - 新版参考：`feature/final-upgrade` = `899d073`（HEAD，PR #76 合并提交）
> - 本轮分支：`feature/student-ui-incremental`（基于 `899d073`）
> - 对比方式：`git show` / `git rev-parse`（blob 哈希）/ `git diff`，并用真实浏览器截图对照
>   （旧版跑在 `:5174`，新版跑在 `:5173`，同一后端 `:8000`）

---

## 0. 最重要的结论（先说结果）

**旧版的视觉基础并没有被破坏，而且大部分就是这么留着的。**

| 结论 | 证据 |
| --- | --- |
| 旧版 CSS 的选择器**一个都没删** | `main` base.css 顶层选择器 274 个；新版 3388 行 / 465 个选择器；**main-only = 0**（274 个全部保留），新版只**新增** 191 个 |
| 旧版 `App.vue` 用到的每一个 class 都还在 | `page` / `page__main` / `page__footer` / `pipeline-guide` / `pipeline-step*` / `overview-bar` / `overview-metric*` / `loading-wrap` / `error-box` / `state*` / `spinner` / `uig-provenance*` / `footer-*` 全部 `present=True` |
| 12 个共用组件里 **10 个字节完全相同** | blob 哈希逐一比对：`CourseOfferingList`、`CurrentScheduleInput`、`E2EDebugPanel`、`PreferenceForm`、`PreferencePanel`、`SectionCard`、`StudentContextForm`、`SubmissionActions`、`TopStatusBar`、`UserInputPanel` = **IDENTICAL** |
| 三个视图组件**根本没有自己的样式** | `MakeupPathView.vue`（492 行）、`TransferAnalysisView.vue`（294 行）、`AiAdjustView.vue`（191 行）**均无 `<style>` 块** ⇒ 它们完全复用 `base.css` 的旧版视觉 |

所以"新版看起来不一样"**不是配色或样式被改掉了**，而是**页面结构**变了：

```text
旧版 main：单页长滚动
  TopStatusBar → pipeline-guide（4 步导航条）→ page__main（全部内容竖排）→ footer

新版 HEAD：四标签 + 抽屉
  TopStatusBar → app-nav（4 个标签）→ page__main（当前标签的**一个**视图）→ 遮罩 → AI 抽屉 → footer
```

**这正是组长想要的"简洁四导航"**，因此不需要回退结构；需要补的是旧版里**丢掉的东西**（见 §4）。

---

## 1. 导航与页面布局

| | 旧版 main | 新版 HEAD |
| --- | --- | --- |
| 导航 | **没有导航**（无 `ViewKey`，无 tab，单页滚动） | **4 个标签** + 1 个 AI 抽屉按钮（非标签） |
| 标签 | — | `转专业分析` → `补修路径` → `AI 调整` → `培养方案导入` |
| 默认视图 | — | `makeup-path` |
| 切换方式 | — | `activeView = view.key`（`v-if / v-else-if / v-else` 链） |
| 页面骨架 | `TopStatusBar` → `pipeline-guide` → `main` → `footer` | `TopStatusBar` → `app-nav` → `main`（单视图）→ 遮罩 → `AiAdjustDrawer` → `E2EDebugPanel` → `footer` |

⚠️ 旧版的"快速导航"是页内锚点（`0.用户输入 / 1.培养要求评估 / 2.开课教学班 / 3.用户偏好 / 4.重构方案与求解`），
新版的四标签是**视图级**导航，两者语义不同，⛔ 不能直接互相替换。

## 2. Vue 组件结构

**新版独有（必须保留，⛔ 不得为恢复旧样式而破坏）**

| 组件 | 作用 |
| --- | --- |
| `views/TransferAnalysisView.vue` | 转专业分析（驱动 `usePersonalPlanning`） |
| `views/MakeupPathView.vue` | 补修路径（旧版单页内容的**新家**） |
| `views/AiAdjustView.vue` | AI 调整标签页 |
| `ai/AiAdjustDrawer.vue`、`ai/IntentConfirmPanel.vue`、`ai/CandidateComparePanel.vue`、`ai/drawerCapability.ts` | AI 抽屉与两次确认 |
| `CurriculumPdfImport.vue`、`CurriculumReviewPanel.vue` | PDF 导入 + 人工审核（PR #75/#76） |
| `ExplanationPanel.vue` | 方案解释 |
| `composables/usePersonalPlanning.ts`、`useAiPlanning.ts` | 个人规划 / AI 规划状态 |

**旧版独有 / 已迁移**

| 旧版内容 | 新版位置 |
| --- | --- |
| 加载中 / 错误 / 重试卡片（`main` L270-301） | 已迁到 `MakeupPathView.vue:185-212`（错误文案与 `🔄 重新尝试连接` **逐字保留**） |
| `overview-bar` 我的学业概览（`main` L306-330） | 已迁到 `MakeupPathView.vue:463+` |
| MakeupTask / CourseOffering / Preference / PlanResult 四个 SectionCard（`main` L333-407） | 已迁到 `MakeupPathView.vue:490-523`（同一批组件、同一 `data-testid="plan-provenance"`） |
| `UserInputPanel` 手动录入（`main` L244-267） | 已迁到 `MakeupPathView.vue:437-460` |
| **`pipeline-guide` 四步导航条（`main` L203-235）** | ⛔ **新版完全没有**（`git grep pipeline-guide HEAD` 只剩 CSS） |
| `DEMO_ENDPOINT` 显示在加载文案里（`main` L13/L278） | ⛔ 新版改成"正在向后端发送数据请求…"，端点字符串消失 |

## 2.5 ⚠️ 一处需要组长裁定的理解偏差：「简洁四导航」

任务书写"保留 main 旧版的**简洁四导航**"，但对比发现 **`main` 根本没有导航**：

| | 四标签导航（视图级） | `pipeline-guide`（流程级） |
| --- | --- | --- |
| 版本 | **仅新版有**（`ViewKey` + `nav.app-nav`） | **仅旧版有**（`main` L203-235） |
| 项数 | **4** 项 | **4** 步 |
| 内容 | `转专业分析` / `补修路径` / `AI 调整` / `培养方案导入` | `1 培养方案对比` ➔ `2 教学班供给获取` ➔ `3 偏好约束注入` ➔ `4 课表求解与调班` |
| 语义 | 切换**页面** | 说明**数据流水线**走到哪一步 |
| 新版状态 | ✅ 保留 | ⛔ **丢失**（只剩 CSS `base.css:301-366`） |

两者**都是 4 项**，因此"旧版四导航"可能指的是 `pipeline-guide`。
若如此，则本轮的"保留旧版四导航"= **把 `pipeline-guide` 搬回去**（见 §8 第 3 项），
而**不是**去改新版已有的四标签——后者恰好就是"简洁四导航"想要的效果。

⚠️ **这一条需要组长确认后我才动手**，因为两种理解会导向不同的实现。
在确认前我⛔ 不改导航结构。

## 3. CSS 与响应式设计

### 3.1 决定性事实：base.css = "旧版文件 + 末尾追加"，**零删除**

```text
head_base.css.splitlines()[:2006] == main_base.css.splitlines()     # 逐行相等
git diff --numstat main HEAD -- frontend/src/styles/base.css  →   1382   0
```

**第 1–2006 行与旧版逐字相同**，包括旧版的
`@media (max-width: 860px)`（L1925）与 `@media (max-width: 640px)`（L1970）。
新版只是在文件**末尾追加** 1382 行。

| 口径 | 旧版 main | 新版 HEAD |
| --- | --- | --- |
| 行数 | 2006 | 3388 |
| 顶层规则块 | 275 | 466（**+191**：191 普通规则 + 4 个 `@media`） |
| 扁平选择器（按逗号拆） | 274 | 479（**+205，删除 0**） |
| `@media` 断点 | 860、640 | 860、640、**1024、720** |

**⇒ 没有任何旧规则被覆盖或削弱；响应式是旧版的严格超集。**

### 3.2 新增 1382 行的归类

| 类别 | 数量 | 说明 |
| --- | --- | --- |
| (a) AI 特性 `.ai-*` | 89 个规则块 / 79 个类 | `.ai-drawer__*`(28)、`.ai-view__*`(9)、`.ai-cta__*`(10)、`.ai-stage__*`(8) 等 |
| (b) PDF 导入 / 审核 | **0** | ⚠️ 这两个功能**完全**装在各自组件的 `<style scoped>` 内（`CurriculumPdfImport` 20 个 `.pdf-import__*`、`CurriculumReviewPanel` 14 个 `.review*`）⇒ 不可能污染其他页面 |
| (c) 视图布局 | 54 个规则块 | `.app-nav*`、`.view*`、`.path-*`、`.transfer-*`、`.gap-hero*`、`.change-hero*` |
| (d) 其他 | 48 个规则块 | `.explain-*`、`.evidence-*`、`.tag--ai-*`，以及 5 条为**被改过的两个旧组件**新增的按钮样式 |

**⚠️ (c)/(d) 会不会影响旧页面？—— CSS 层面证明不会：**

1. 新增规则的 **171/171 个根类全是新的**，旧版 base.css 里**一个都没有**。
2. 新增规则中**没有一条的最左复合选择器是裸元素**（不存在 `body` / `*` / `h2` / `table` 这类全局命中）。
3. 新增区域 **`!important` = 0**（旧版自身有 3 条）；无 `:root`、无自定义属性重定义、无 `@layer`、无新增 `@keyframes` / `@font-face`。
4. 唯一跨界的 `.ai-drawer__head .button`（L2594）被 `.ai-drawer__head` 限制，而旧版页面**没有**这个类。

**⇒ 旧样式"看起来变了"的机制不是样式覆盖，而是 §3.3 的重新挂载。**
⚠️ **因此⛔ 不要删除追加的 1382 行** —— 删了会打断 AI 抽屉、三个视图与审核面板。

### 3.3 真正的原因：**标记重新挂载 + 区块顺序改变**

三个视图组件**都没有** scoped 样式（`MakeupPathView` 527 行、`TransferAnalysisView` 324 行、
`AiAdjustView` 206 行，**`<style>` 块数 = 0**），而且它们在旧版**完全不存在**。
它们做的是把旧版区块**重新包一层**，并**改变顺序**：

```text
旧版：.page → .pipeline-guide → .page__main
        → [user-input, overview-bar, makeup, offerings, preference, plan]

新版：.page.page--ai-planning → .app-nav → .view.view--path
        → [current-semester, later-semesters, priority-risk, plan, explanation, path-support,
           user-input, overview-bar, makeup, offerings, preference]
```

| 区块 | 旧版位置 | 新版位置 |
| --- | --- | --- |
| user-input（手动录入） | 第 1 | 第 **7** |
| overview-bar（我的学业概览） | 第 2 | 第 **8** |
| makeup / offerings / preference | 第 3–5 | 第 **9–11** |
| 五个新增区块 | — | 第 1–6 |

新祖先（`.view`、`.path-*`、`.gap-hero`、`.app-nav` 等，几乎全是 grid/flex/宽度类）改变了被复用子元素的**盒子**，
加上区块顺序改变 ⇒ 观感与旧版不同。**这是唯一机制。**

实测佐证（同一后端、同一视口、同一次运行）：旧版整页高 **6635px**，新版 **8333px**（+25.6%）。

### 3.4 `MakeupTaskList` / `PlanResultPanel`——两版唯一不同的共用组件

`git diff --numstat`：`MakeupTaskList` **+21/−1**、`PlanResultPanel` **+46/−1**。
改动**全部为新增**，且都藏在一个新的可选布尔 prop（`evidenceEnabled?`，默认 `undefined` ⇒ 假）后面。

| 组件 | 改动 | 不传该 prop 时外观不变？ |
| --- | --- | --- |
| `MakeupTaskList` | 加一列「解释」`<th v-if="evidenceEnabled">` + 每行 `🔍 查看依据` 按钮；空态 `colspan` 改为 `evidenceEnabled ? 7 : 6` | ✅ 是 |
| `PlanResultPanel` | 3 处插入，均 `v-if="evidenceEnabled"` | ⚠️ **有 1 处例外** |

⚠️ **`PlanResultPanel` 中唯一"关掉也仍改变外观"的改动**（需要修复的旧版回归）：

```html
-  <span class="tag tag--selected">建议纳入</span>
+  <div class="selected-card__actions">
+    <span class="tag tag--selected">建议纳入</span>
+    <button v-if="evidenceEnabled" …>🔍 查看依据</button>
+  </div>
```

`.tag` 原本是行内，而 `.selected-card__actions`（base.css L2025）是**新的 flex 容器**
⇒ 即使不传 `evidenceEnabled`，"建议纳入"徽标的盒子与对齐也变了。
**若只回退一处，就回退这一处**（给 wrapper 也加 `v-if`，或恢复裸 `<span>`）。

两个组件的 diff 里**没有任何样式行**（只有 `<script>` / `<template>` hunk），与行数增量一致。


## 4. 数据状态管理

- 两版**都没有** Pinia/Vuex（`src/store`、`src/stores` 均为空）。
- 旧版只接 `useDemoData`；规划状态是 `App.vue` 里手写的 ref。
- 新版接 `useDemoData` + `usePersonalPlanning`；`useAiPlanning` 在**抽屉内部**实例化，不在 shell。
- 新版 `planResultMode` 是**三态** `'mock' | 'real' | 'ai_candidate'`（旧版两态）。
  ⚠️ 这是必须保留的改动：回退成两态会把 AI 采用的方案**误标成 Mock**，并把 Mock 课程名泄进真实结果。

## 5. API 调用

| | 旧版 | 新版 |
| --- | --- | --- |
| 挂载时 | `GET /api/v1/mock/demo` | `GET /api/v1/mock/demo` + `GET /api/v1/personal-planning/curriculum-versions` |
| 用户动作 | `POST /api/v1/plan` | `POST /api/v1/plan` + `POST /api/v1/personal-planning/*` |
| AI | 无 | `/api/v1/ai-planning/status|interpret|solve|adopt`（在抽屉内调用） |
| PDF | 无 | `/api/v1/curriculum-import/*` + `/api/v1/curriculum-review/*` |

## 6. 用户输入 / 课程选择与教学班 / 规划结果 / AI 调整

| 能力 | 旧版 | 新版 | 结论 |
| --- | --- | --- | --- |
| 用户信息 + 原/目标专业选择 | `StudentContextForm` | 同一组件（**IDENTICAL**）在 `MakeupPathView` | ✅ 直接复用 |
| 手动录入已修/当前课表 | `UserInputPanel` / `CurrentScheduleInput`（IDENTICAL） | 同一批组件 | ✅ 直接复用 |
| 手动设置偏好 | `PreferenceForm` / `PreferencePanel`（IDENTICAL） | 同一批组件 | ✅ 直接复用 |
| 课程 / 教学班选择 | `CourseOfferingList`（IDENTICAL） | 同一组件 | ✅ 直接复用 |
| 补修任务展示 | `MakeupTaskList` | `MakeupTaskList`（**有改动**） | ⚠️ 需逐行确认 |
| 规划结果与风险说明 | `PlanResultPanel` + provenance | `PlanResultPanel`（**有改动**）+ 三态 provenance | ⚠️ 需逐行确认 |
| AI 调整 | 无 | 标签页 + 抽屉 + 两次确认 | ✅ 新版独有，保留 |
| 我的学业概览 | `overview-bar` | 已迁入 `MakeupPathView` | ✅ 已有，⛔ 不要重复加 |

## 7. 测试文件

| | 旧版 | 新版 |
| --- | --- | --- |
| 测试文件 | 8 个 | 23 个 |
| 沿用 | `app-provenance-guard`、`form-validation-gate`、`plan-api`、`plan-result-provenance`、`real-e2e-prep`、`real-path-readiness`、`schedule-provenance-gate`、`user-input-panel`、`user-input` | ✅ 全部沿用 |
| 新增 | — | `ai-*`（5）、`personal-planning-contract`、`curriculum-pdf-import`、`curriculum-review`、`explanation-*`（2）、`provenance-source-labels`、`transfer-analysis-view`、`ux-polish` |

## 8. 可以直接复用的旧版代码

| # | 可复用项 | 方式 | 理由 |
| --- | --- | --- | --- |
| 1 | 10 个字节相同的组件 | **已经就是同一份**，无需动作 | blob 哈希 IDENTICAL |
| 2 | `base.css` 的 274 个旧选择器 | **已经全在**，无需动作 | main-only = 0 |
| 3 | `pipeline-guide` 四步导航条（`main` L203-235） | **原样搬运，但换位置** ⇒ 放进 `MakeupPathView.vue` 头部之后 | 纯静态、无绑定；⛔ 不能放 shell（会在 4 个标签上都出现）；CSS 已在 base.css:301-366，**零样式工作量** |
| 4 | 单页长滚动的阅读顺序（用户输入 → 概览 → 补修 → 教学班 → 偏好 → 结果） | 已由 `MakeupPathView` 保有 | 见 §2 迁移表 |

## 9. 必须保留的新版代码（⛔ 不得为恢复旧样式而破坏）

1. `type ViewKey` + `VIEWS` + `activeView` + `nav.app-nav`（四导航）与 AI 抽屉按钮。
2. `usePersonalPlanning` + `TransferAnalysisView` + `onPersonalSubmit` / `onPersonalUseResults`。
3. `AiAdjustView` + `AiAdjustDrawer` + 遮罩 + `openAiDrawer` / `closeAiDrawer` / `onAiAdopted`。
4. **三态 provenance**：`planResultMode`（mock/real/ai_candidate）、`planResultLabel`、
   `planResultProvenanceNote`、`displayedPlanResult` 优先级
   （`aiAdoptedPlan ?? realPlanResult ?? data.plan_result`）、反转的课程名映射
   （`planResultMode === 'mock' ? courseNameById : {}`）、footer 的 `ai_candidate` 分支。
5. `CurriculumPdfImport` + `CurriculumReviewPanel`（PR #75/#76）。
6. `ExplanationPanel` 接线与 `EXPLANATION_API_ENABLED`。
7. `usesVerifiedSource`（**硬编码 `false`**）—— 这是"来源未核验"的诚实声明，⛔ 不得改成 `true`。
8. `submitRealPlan` 成功后的 `aiAdoptedPlan = null` / `aiAdoptedVersion = null`
   （否则 `displayedPlanResult` 会继续优先显示**过期的 AI 方案**）。

## 10. 发现的问题（只报告，本轮未修）

| # | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| 1 | **`E2EDebugPanel` 在开发环境渲染两次** | 新版 shell L510 渲染一次，同时仍把 `:debug-info` 经 `MakeupPathView.vue:454` 传给 `UserInputPanel.vue:230` 再渲染一次 | 补修路径标签下出现两个 `data-testid="e2e-debug"` |
| 2 | `pipeline-guide` 四步导航条丢失 | §2 | 少了旧版的流程引导 |
| 3 | `DEMO_ENDPOINT` 不再显示 | §2 | 旧版会在加载卡片里显示请求端点（也可能是**有意收敛**，因为它把内部端点暴露给演示界面 ⇒ 需组长定夺） |
| 4 | `App.vue` 导入了 `watch` 但从未使用 | 新版 L2 | 死代码 |
| 5 | `planScheduleBlocked` 两版都声明但从未使用 | 旧版 L69 / 新版 L87 | 死代码（⛔ 不要"恢复"它） |
| 6 | `PlanResultPanel` 的 `selected-card__actions` 包装**关掉功能也改变外观** | §3.4 | "建议纳入"徽标盒子/对齐改变 ⇒ **旧版视觉回归** |
| 7 | `view--path` / `view--transfer` / `view--ai` 是**没有任何规则**的惰性类 | §3.2 | 仅标记用途，无影响（但说明有未清理的痕迹） |

## 11. 下一步（⚠️ 待组长确认后才动代码）

### 11.1 ⛔ 第一优先：需要组长裁定的一件事

**"简洁四导航"到底指什么？**（§2.5）

- **理解 A**：指新版已有的**四标签导航**（转专业分析 / 补修路径 / AI 调整 / 培养方案导入）
  ⇒ 那么"保留"已经满足，本轮**不动导航**，只做 §三 的小范围新增。
- **理解 B**：指旧版的 **`pipeline-guide` 四步流程条**（已丢失）
  ⇒ 那么需要把它**搬回 `MakeupPathView`**（零样式工作量）。

⚠️ 在确认前我⛔ **不改导航结构**。

### 11.2 安全增量路径（⛔ 不得整体覆盖 `frontend` 目录）

**硬约束：整体覆盖会删掉约 14.9k 行**（`git diff --stat main HEAD -- frontend` = 46 文件，+14924/−2195），
包括 PDF 导入审核、AI 规划、解释、个人规划全部栈，以及 20 个 spec 文件；
且新版 spec 会挂载并断言新版 `App.vue`（`ai-planning-app-shell.spec.ts`、`ux-polish.spec.ts` 等）⇒ 测试必红。

**必须保留（⛔ 回退即破坏）**：
`config.ts`、`api/aiPlanning*.ts`、`api/curriculumImport.ts`、`api/curriculumReview.ts`、
`api/explanation.ts`、`api/personalPlanning*.ts`、`composables/useAiPlanning.ts`、
`composables/usePersonalPlanning.ts`、`utils/explanationLabels.ts`、`components/ai/*`、
`CurriculumPdfImport.vue`、`CurriculumReviewPanel.vue`、全部 spec、`vitest.config.ts`、
`package.json`（vitest 3→4，需与 lockfile 同步）、以及 **`base.css` 整份文件**。

**可直接复用（已逐字相同，取用等于不改动）**：
`SectionCard`、`TopStatusBar`、`UserInputPanel`、`CourseOfferingList`、`PreferencePanel`、
`CurrentScheduleInput`、`StudentContextForm`、`SubmissionActions`、`PreferenceForm`、
`E2EDebugPanel`、`state/userInput.ts`、`api/plan.ts`、`utils/labels.ts`、`types/contracts.ts`、
`composables/useDemoData.ts`（blob 哈希逐一相同）。
`MakeupTaskList` / `PlanResultPanel` 是**唯二**有差异的共用组件，且均为纯新增。

**`App.vue` 是真正的杠杆，但⛔ 不是逐字替换**（新版 545 行 vs 旧版 432 行，churn 977 行）。
建议顺序：

1. **修 `PlanResultPanel` 的旧版回归**（§3.4）—— 优先级最高，因为它影响**每次**渲染。
2. **搬回 `pipeline-guide`**（若组长确认为理解 B）—— 纯标记迁移，CSS 已在 base.css:301-366。
3. **修 `E2EDebugPanel` 重复渲染**（问题 #1）—— 保留一个。
4. **在 `MakeupPathView` 内恢复旧版区块顺序**（若组长要单页阅读顺序）：
   user-input → overview-bar → makeup → offerings → preference → plan。
   `SectionCard` 与旧版逐字相同 ⇒ **纯重排即可复现旧版这五张卡的观感**。
5. **完成 §三 的小范围新增**：更清晰的专业选择交互、
   **成绩截图样本导入入口（⚠️ 样本尚未提供 ⇒ 只做入口与手动录入保留，⛔ 不假装已实现识别）**、
   当前/未来学期并排、调整前后课表对比、必要的响应式。
6. **逐项跑测试**：`npx vitest run`（23 文件 / 371 用例）+ `vue-tsc --noEmit` + `npm run build`，再跑浏览器 E2E。
7. **验证 §四 的 7 条验收**并出截图，然后开 Draft PR（目标 `feature/final-upgrade`，⛔ 不自动合并）。

⚠️ 任何一步都⛔ 不得改 `/schemas/**`、`/docs/interfaces/**`、`main`、Planner 或正式批准锚点。

---

## ⚠️ 诚实声明

- 本文件是**静态对比 + 浏览器截图对照**，⛔ 尚未做任何代码改动。
- §三 的"成绩截图样本导入"：**样本尚未提供**，因此该功能⛔ 未实现，也⛔ 不会假装已实现识别能力。
- 本对比的布局结论来自 CSS 规则与模板结构 + 整页高度实测（旧 6635px / 新 8333px），
  ⛔ **未做像素级回归**；`.selected-card__actions` 徽标位移是**结构性断言**（`span` → 新 flex `div`），未量测。
- 本次⛔ 未跑 `vitest`（对比阶段只读；且 `package.json` 把 vitest 3 升到 4，需先安装才能跑）。
- 截图基线存放在 `_ux-baseline/`（⚠️ 仅供本地比对，**不提交**）。
