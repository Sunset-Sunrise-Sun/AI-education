# 联合浏览器验收报告：PR #68（UX 优化）× PR #69（浏览器 E2E）

- **联合 QA 分支**：`qa/final-upgrade-ux-browser-e2e`
- **基线**：`feature/final-upgrade` = `36ce35a`
- **合并内容**（两个原始分支**均未修改**）
  - PR #68 `feature/final-upgrade-ux-polish` = `a38c9cd`（前端 UX + 测试 + 文档，11 文件）
  - PR #69 `test/final-upgrade-browser-e2e` = `d7e5f7e`（浏览器 E2E 基础设施，14 文件）
- **执行环境**：Windows；Python 3.14.7（`PYTHONUTF8=1`）；Node v24.19.0
  - 浏览器：**系统 Microsoft Edge**（`playwright-core` `channel=msedge`，⛔ 未下载浏览器二进制）
  - 后端：**真实 FastAPI**（`app.main.app`，uvicorn 真实监听随机端口）
  - 前端：**真实 Vite dev server**（`build.sourcemap: true`）
- **使用数据**：**Mock**（人工构造演示数据）+ **注入式测试模型**（`generator_kind=test_double`）
- **真实 DeepSeek**：**NOT VERIFIED**（无密钥，`live_model_available=false`）
- **公共 Schema / 接口 / Planner 算法**：**均未修改**
- **总结果**：**23 / 23 通过**；另做一次"只用 PR #69 原有 18 项"的对照复跑：**18 通过 / 5 跳过 / 0 失败**

---

## 1. 结论先行

| 问题 | 结论 |
| --- | --- |
| PR #68 的 UX 改动是否让 PR #69 的 18 项浏览器 E2E 失效？ | **没有**。18 项在合并后的树上**全部通过**（另有 5 项为本次新增） |
| PR #68 重排区块后，规则解释入口还能访问吗？ | **能**。入口仍在，点击后**真实调用** `POST /api/v1/explanation/plan`，面板标注"规则模板（非 AI）" |
| 三入口移动端布局与抽屉按钮可操作性如何？ | **通过**（375 / 768 / 1440），但发现 **1 个既有缺陷 K-1**（见 §5） |
| 抽屉头部原始配置字段是否过密？ | **375px 下确实过密**（状态行 2.8 行 / 占视口 14%）——已在报告中量化，**未自行改动**（见 §5） |
| 有无产品缺陷？ | **1 项既有缺陷 K-1（非 PR #68 引入）** + **1 项信息密度观察 O-1**；**未发现新的功能性缺陷** |
| 回归是否通过？ | 后端 **3188 / 2（既有平台差异）/ 2**；前端 **303 passed**；`vue-tsc` exit 0；`build` exit 0 —— **无新回归** |

---

## 2. 怎么复现

```powershell
# 0) 取联合 QA 分支
git fetch origin
git worktree add ..\AI-education-ux-e2e-qa qa/final-upgrade-ux-browser-e2e

# 1) 装依赖（两处；tools 那处是套件自己的，不动 frontend/package.json）
cd frontend      ; npm ci --no-audit --no-fund
cd ..\tools\browser-e2e ; npm install --no-audit --no-fund

# 2) 跑全部 23 项（自动起 5 组真实后端 + 真实前端 + Edge）
node tools/browser-e2e/run_browser_e2e.mjs

# 3) 对照：只跑 PR #69 原有的 18 项
python tools/browser-e2e/_make_baseline18.py
node tools/browser-e2e/run_browser_e2e.mjs --cases=_cases_baseline18.mjs

# 4) 把已知缺陷 K-1 从"观测"切回"判定失败"（用于复现/验收该缺陷）
$env:QA_STRICT_HEADER_BUTTON=1
node tools/browser-e2e/run_browser_e2e.mjs --filter=R-375
```

---

## 3. 测试矩阵与结果（23 项）

### 3.1 PR #69 原有 18 项（对照复跑）

| # | 用例 | 结果 |
| --- | --- | --- |
| 1 | `L01-home-three-entries` | ✅ |
| 2 | `L02-transfer-analysis-readiness` | ✅ |
| 3 | `L03-makeup-path-structure` | ✅ |
| 4 | `L04-ai-full-two-confirmations` | ✅ |
| 5 | `L05-adopted-plan-refreshes-view` | ✅ |
| 6 | `L06-reject-keeps-original` | ✅ |
| 7 | `L07-drawer-reopen-and-navigation` | ✅ |
| 8 | `L08-ambiguity-blocks-solve` | ✅ |
| 9 | `L09-locked-course-explicit-lock` | ✅ |
| 10 | `L10-candidate-expiry-410` | ✅ |
| 11–13 | `R-375 / R-768 / R-1440-layout` | ✅ ✅ ✅ |
| 14 | `E01-double-click-confirm-single-solve` | ✅ |
| 15 | `E02-double-click-adopt-single-request` | ✅ |
| 16 | `E03-backend-down-shows-error-not-fixture` | ✅ |
| 17 | `D01-ai-disabled-state` | ✅ |
| 18 | `P01-preview-fully-labelled` | ✅ |

> 这 18 项**一个字都没改**，直接跑在"UX #68 + E2E #69"的合并树上。
> 结论：**UX 改动没有破坏任何原有用例的定位假设**。

### 3.2 本次新增 5 项（联合验收新增要求）

| # | 用例 | 验证目标 | 结果 | 关键证据 |
| --- | --- | --- | --- | --- |
| 19 | `X01-explanation-entry-and-panel` | 阅读顺序 5 步；解释入口可访问；面板渲染与标注 | ✅ | 真实 `POST /api/v1/explanation/plan` 1 次；生成方式`规则模板（非 AI）`；11 条解释条目；关闭后入口恢复 |
| 20 | `X02-explanation-single-course-focus` | 单条课程解释入口；解释只读 | ✅ | `plan-explain-overall` 可点并真实调用解释接口；解释前后方案指纹/来源一致；**0 次 `/solve`** |
| 21 | `U01-transfer-gap-summary` | 缺口摘要只读后端 `status_counts`，不重判、不凭空给数字 | ✅ | 无已核验目录时 `gap-summary` **不渲染**（断言 count=0） |
| 22 | `U02-ai-five-stages-and-partitions` | 五阶段指示、硬/软分区、变化摘要、临时采用提示 | ✅ | 阶段指示 4 段；入口示例 3 条；硬约束`不可协商`/软偏好`可协商`；变化摘要含 新增/移除/换班/保持/学分；采用提示含`未持久化` |
| 23 | `U03-supporting-data-section-is-secondary` | 支撑数据分区不产生新结论；旧输入 testid 未丢 | ✅ | `path-supporting-data` 含"不产生"；`origin-major-input`/`semester-input`/`target-major-input` 仍存在 |

### 3.3 增强后的响应式矩阵（375 / 768 / 1440）

在原 3 个断点用例里**追加**了 UX 结构断言（三档均通过）：

| 检查项 | 375px | 768px | 1440px |
| --- | --- | --- | --- |
| 三入口横向溢出 | 0px ✅ | 0px ✅ | 0px ✅ |
| 阅读顺序 5 步可读、宽度未超视口 | ✅ | ✅ | ✅ |
| 解释入口可滚动到视口内（宽 229px） | ✅ | ✅ | ✅ |
| 抽屉几何 | 近似全屏 ✅ | 右侧 520px 面板 ✅ | 右侧 520px 面板 ✅ |
| 抽屉头部：状态行行数 / 高度 | **2.8 行 / 54px** | 1.8 行 / 35px | 1.8 行 / 35px |
| 抽屉头部总高（占视口） | 117px（**14%**） | 98px（10%） | 98px（11%） |
| 关闭按钮尺寸 | **61×77px** | **71×58px** | **71×58px** |
| 关闭按钮落在视口内、≥24×24 | ✅ | ✅ | ✅ |
| 采用按钮可滚动到视口内并可点 | ✅ | ✅ | ✅ |
| 候选风险长文本已渲染 | ✅（55 字） | ✅ | ✅ |

---

## 4. 浏览器实际发出的请求（不是模拟）

| 用例 | AI / 解释相关请求 | 说明 |
| --- | --- | --- |
| `X01` | `POST /api/v1/explanation/plan` ×1 | 规则解释是**真实后端调用**，不是前端编造 |
| `X02` | `POST /api/v1/explanation/plan` ≥1；**`/solve` = 0** | 解释只读，不触碰规划 |
| `L04` | `GET /status` + `POST /interpret` + `POST /solve` + `POST /adopt` | 两次确认闭环四接口齐全 |
| `L06` / `L07` / `E02` | `interpret` + `solve`（+ `adopt` 按用例） | 拒绝不推进版本；重开抽屉不重放 `/solve`；连点只 1 次 `/adopt` |
| `L08` | 只有 `interpret` | 歧义时**不调用** `/solve` |
| `L10` | `interpret` + `solve` + `adopt` | 过期 ⇒ 后端拒绝，原方案不变 |
| `D01` | 只有 `GET /status` | `/interpret` `/solve` `/adopt` 均为 **0** |
| `P01` | **无任何 `/ai-planning/*`** | 预览档完全走 fixture |

---

## 5. 发现的问题与本轮处理

### 5.1 已知缺陷 K-1：抽屉头部关闭按钮被挤成竖长条（**既有，非 PR #68 引入**）

**复现步骤**

1. 打开 `http://127.0.0.1:<port>/`，切到"补修路径"，点"打开 AI 调整"；
2. 把视口设为 375px（或 768 / 1440），量 `[data-testid="ai-drawer-close"]`。

**实测**（本轮真实浏览器测量）

| 视口 | 按钮外框 | 按钮内**文本盒** | `white-space` |
| --- | --- | --- | --- |
| 375px | **61 × 77 px** | 14 × 54 px | `normal` |
| 768px | **71 × 58 px** | 28 × 35 px | `normal` |
| 1440px | **71 × 58 px** | 28 × 35 px | `normal` |

**判断：产品缺陷（样式缺陷），不是测试假设问题。**
文本盒只有 14px 宽说明"✕ 关闭"被折成了多行；按钮没有 `flex-shrink: 0`，
在 flex 头部的挤压下"变窄→变高"，最终变成一个竖长条。
用户仍能点到它（≥24×24、落在视口内），所以**不阻塞**，但明显不好看、也不好看懂。

**是否为 PR #68 引入：不是。**
在 PR #69 分支（即 UX 改动**之前**）上测到的是完全相同的 61×77 / 71×58 —— 属于既有基线问题。

**建议修复（一行 CSS，属 frontend/UX 负责人组件）**

```css
.ai-drawer__head .button {
  flex-shrink: 0;
  white-space: nowrap;
}
```

**本轮处理**：⛔ **未自行修改** `frontend/src/styles/base.css` 与 PR #68 的组件
（遵守"QA 不擅自重写他人已评审模块"的边界）。
而是在 E2E 里把它做成**可复现的观测项**，并提供严格开关：

```powershell
$env:QA_STRICT_HEADER_BUTTON=1
node tools/browser-e2e/run_browser_e2e.mjs --filter=R-375
# ⇒ AssertionFailure: 关闭按钮过高（61×77px；文本盒仅 14×54px）
```

> 因此该缺陷是**可一键证伪**的，不会因为"测试通过"而被埋掉。
> **需要人工确认**：是否授权我直接加这 2 行 CSS（会让 `base.css` 变更，需要同步 PR #68）。

### 5.2 观察 O-1：抽屉头部把原始配置字段直接铺开（375px 下过密）

Architecture Review 明确要求检查这一点，本轮量化如下：

```text
状态行文本：enabled=true · api_key_configured=false · live_model_available=false · model=qa-test-double
375px：状态行 2.8 行 / 高 54px；整个头部 117px（占视口 14%）
768px：状态行 1.8 行 / 高 35px；整个头部 98px（占视口 10%）
1440px：同 768px
```

**判断：这是**面向开发者的能力事实披露**，是有意设计，不是安全或正确性问题。**
证据：`frontend/tests/ai-planning-drawer.spec.ts` 明确断言
`ai-drawer-status` 必须包含 `enabled=true` 与 `live_model_available=false` ——
即有测试在**锁定**这段文案，说明它是被团队接受的设计。

**⛔ 因此本轮不改文案、不改测试**（改它需要同步修改 frontend 作者已评审的 Vitest 断言）。
**建议**（供人工确认，不属于本次验收阻塞项）：

- 375px 下把状态行折叠为一行摘要（如 `测试替身 · 未配置密钥`）+ 可展开的"技术细节"；
- 或把 `enabled / api_key_configured / live_model_available / model` 改成键值网格（两列），减少折行。

### 5.3 本轮修复的问题（都是**测试基础设施**自身）

| # | 现象 | 根因 | 处理 |
| --- | --- | --- | --- |
| 1 | 新增对照跑法需要"只跑某个 PR 的用例集" | 运行器把用例文件写死 | 新增 `--cases=<文件>` 与 `skip: true` 支持；补 `_make_baseline18.py` 生成对照变体 |
| 2 | 第一版"文字折行"检测把 3 个断点全判失败（假阳性） | 直接用 `按钮高度 / line-height`，但 `.button` 是 `inline-flex + align-items: center`，除出来的根本不是行数 | 改成"把文本克隆到同字体同宽度的隐藏测量盒里量行数"，得到真实行数（1 行） |
| 3 | `skipped` 被算进 `failed` | 汇总只分了 passed / 非 passed | 汇总拆成 passed / failed / skipped，并让退出码只看 failed |

⛔ 未修改任何生产代码、公共 Schema、接口或 Planner 算法。
⛔ 未修改 PR #68 与 PR #69 的原始分支。

---

## 6. 截图存放位置

`tools/browser-e2e/artifacts/`（34 张，按档位分目录）：

| 目录 | 数量 | 内容 |
| --- | --- | --- |
| `live/` | 15 | L01–L10 主流程（含候选对比、采用、拒绝、过期） |
| `explanation/` | 3 | **X01 解释入口 / 解释面板 / X02 聚焦解释** |
| `ux/` | 5 | **U01 缺口摘要（不伪造）/ U02 入口·分区·变化摘要 / U03 支撑数据** |
| `responsive/` | 6 | 375 / 768 / 1440 的抽屉与候选对比 |
| `resilience/` | 3 | 连点确认、连点采用、后端不可用 |
| `disabled/` | 1 | AI 未启用 |
| `preview/` | 1 | 前端预览标注 |

另有 `artifacts/browser-e2e-results.json`（全部 23 项）、
`artifacts/browser-e2e-results-_cases_baseline18.json`（对照 18 项）、
`artifacts/logs/*.log`（各组服务启动日志）。

**人工核对过的关键截图**

- `explanation/X01-b-explanation-panel.png`：第 5 区块"解释与依据"渲染完整 ——
  右上角 `Mock 数据`、`解释对象：Mock 演示结果`、`生成方式：规则模板（非 AI）`、
  指纹 `ea20087c39de…`、`解释条目：11`，并明确写出"本解释由确定性规则模板生成，
  **没有调用任何 AI 模型**（未配置模型服务）"，以及"补修任务 6 条 / 教学班 9 个 / 含 Mock 标记：是 / 含 Real 教学班：否"。
- `responsive/R-375-drawer.png`：手机宽度下抽屉近似全屏，四阶段指示与示例按钮可见；
  头部状态行折行、关闭按钮呈竖长条（即缺陷 K-1 的现场）。

---

## 7. 回归结果

在合并后的树上（commit `a38c9cd` + `d7e5f7e` 的合并提交）实测：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 浏览器 E2E（23 项，UX+E2E 合并树） | `node tools/browser-e2e/run_browser_e2e.mjs` | **23 passed / 0 failed / 0 skipped** |
| 浏览器 E2E（PR #69 原有 18 项对照） | `--cases=_cases_baseline18.mjs` | **18 passed / 0 failed / 5 skipped** |
| 后端 pytest | `python -m pytest -q`（`backend/`，`PYTHONUTF8=1`） | **3188 passed / 2 failed / 2 skipped** |
| 前端 Vitest | `npx vitest run` | **303 passed / 0 failed**（19 文件，含 PR #68 新增的 `ux-polish.spec.ts`） |
| 前端类型检查 | `npx vue-tsc --noEmit` | **exit 0** |
| 前端构建 | `npm run build` | **exit 0**（JS 247.21 kB / gzip 79.82 kB） |

**2 项后端失败**为既有平台差异（Python 3.14 `Path("bad\x00path")` 不再抛错；
Windows ZIP 成员名反斜杠语义），在历史各分支上同样失败，与本轮改动无关；⛔ 未修改其实现或测试。

**未产生任何新回归。**

---

## 8. 未验证事项（如实记录）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| **真实 DeepSeek 在线调用** | **NOT VERIFIED** | 无密钥；全部 AI 结果来自注入式测试模型（`test_double`），⛔ 不冒充在线模型 |
| 真实已核验培养方案目录 | **BLOCKED** | 转专业分析如实显示"没有已核验版本目录"；个人规划成功路径未在浏览器跑通 |
| 真实教学班 / 成绩数据 | **BLOCKED** | 全部使用人工构造演示数据（`data_source=mock`） |
| 持久化方案版本 / 跨进程会话 | **不存在** | `adopted_version_scope=process_local_session` |
| 真机（iOS/Android）浏览器与触屏手势 | **未执行** | 本轮只做视口尺寸模拟（375/768/1440），非真机 |
| 无障碍专项（屏幕阅读器、键盘 Tab 序） | **未执行** | 仅验证了对比度无关的尺寸/可点性 |
| 依赖漏洞修复（tinypool / @vitest/mocker / source-map-js） | **未修复** | 与前一轮报告一致，未改依赖清单 |

---

## 9. 本轮改动文件

**仅测试基础设施**（⛔ 无生产代码改动、⛔ 未改两个原始分支）：

| 文件 | 变更 |
| --- | --- |
| `tools/browser-e2e/cases.mjs` | 新增 `explanationCases()`（X01/X02）、`uxStructureCases()`（U01–U03）；响应式用例追加 UX 结构与头部信息密度断言；新增 `textLineCount()` / `measureDrawerHeader()` |
| `tools/browser-e2e/lib/harness.mjs` | `runCases()` 支持 `skip: true`（记录为 skipped） |
| `tools/browser-e2e/run_browser_e2e.mjs` | 新增 `--cases=<文件>`；结果汇总拆分 passed/failed/skipped；新增两个用例组 |
| `tools/browser-e2e/_make_baseline18.py` | 新增：生成"只跑 PR #69 原有 18 项"的临时对照变体 |
| `docs/final_upgrade/reports/UX_BROWSER_E2E_JOINT_REPORT.md` | 本报告 |

**未改动**：`main`、`feature/final-upgrade`、`feature/final-upgrade-ux-polish`、
`test/final-upgrade-browser-e2e`、`/schemas/**`、`/docs/interfaces/**`、
`frontend/src/**`、`frontend/tests/**`、`backend/app/**`、Planner 算法。

---

## 10. 建议下一步

1. **人工确认缺陷 K-1**：是否授权在 `frontend/src/styles/base.css` 加
   `.ai-drawer__head .button { flex-shrink: 0; white-space: nowrap; }`（约 2 行），
   改完把 `QA_STRICT_HEADER_BUTTON=1` 打开复跑 `R-*` 应转绿；
2. **人工确认观察 O-1**：是否把抽屉头部状态行改为"一行摘要 + 可展开技术细节"
   （需同步修改 `frontend/tests/ai-planning-drawer.spec.ts` 的字符串断言）；
3. 两个 PR 合并顺序建议：先合 PR #69（测试基础设施，无生产影响）再合 PR #68，
   合并后立刻在 `feature/final-upgrade` 上复跑本套件（23 项）；
4. 上游提供真实培养方案 / 教学班数据后，补跑"转专业分析 → 个人规划成功路径"，
   并把结果接到 AI 调整上下文；
5. 用新密钥做一次真实 DeepSeek 在线验证（预期 `generator_kind=deepseek_live`）。
