# 浏览器 E2E 与系统验收报告（Final Upgrade · Agent A）

- **分支**：`test/final-upgrade-browser-e2e`（基于 `feature/final-upgrade` = `36ce35a`）
- **报告提交**：见本文件所在提交（`test(browser-e2e): add real-browser end-to-end suite and acceptance report`）
- **执行环境**
  - OS：Windows（PowerShell）；Python 3.14.7（`PYTHONUTF8=1`）
  - 浏览器：**Microsoft Edge**（系统已安装），由 `playwright-core` 以 `channel=msedge` 驱动 —— ⛔ 未下载 Playwright 自带浏览器
  - Node v24.19.0 / npm 11.17.0；前端 Vite 8.3.1（dev server）、Vue 3.5.43
  - 后端：**真实 FastAPI 应用**（`app.main.app`），由 uvicorn 真实监听随机端口
- **使用数据**：**Mock**（人工构造演示数据 + 注入式测试模型）
- **真实 DeepSeek**：**NOT VERIFIED**（无密钥，`live_model_available=false`）
- **公共契约 / Planner 核心**：**未修改**（`/schemas/**`、`/docs/interfaces/**`、`app/planner/**` 均未改动）
- **总结果**：**18 / 18 通过**（0 失败、0 跳过）

---

## 1. 一句话结论

在**真实浏览器**里跑通了三条主路径，并对每一步都断言了**浏览器实际发出的 HTTP 请求**：

```text
首页三入口 → 转专业分析（如实显示"没有已核验目录"）
          → 补修路径（四状态 / 教学班 / 风险 / 未决 / Mock 标识）
          → AI 调整（解析 → 第一次确认 → 求解 → 候选对比 → 第二次确认采用）
```

AI 调整全程使用**注入式测试模型**（`generator_kind=test_double`），
⛔ 报告不把它称为真实 DeepSeek 在线调用；真实在线仍为 **NOT VERIFIED**。

---

## 2. 怎么运行（可复现）

```powershell
# 1) 安装浏览器 E2E 套件自己的依赖（只 1 个包，且不下载浏览器）
cd tools/browser-e2e
npm install --no-audit --no-fund

# 2) 运行全部用例（会自动起真实后端 + 真实前端 + Edge）
node run_browser_e2e.mjs            # 或 npm run e2e
node run_browser_e2e.mjs --headed   # 想看窗口时
node run_browser_e2e.mjs --filter=L04   # 只跑匹配 id 的用例
```

运行器会自动：

1. 起 5 组服务（见 §3.2），全部使用**随机空闲端口**；
2. 用 `playwright-core` + `channel=msedge` 打开真实浏览器；
3. 逐个用例执行并截图；
4. 写出 `tools/browser-e2e/artifacts/browser-e2e-results.json`（含每例的请求清单与备注）。

**依赖与成本评估（任务书 P2 要求）**

| 方案 | 依赖 | 浏览器下载 | 结果 |
| --- | --- | --- | --- |
| **采用**：`playwright-core` + 系统 Edge | 1 个 devDependency（独立 `tools/browser-e2e/package.json`，⛔ 不改 `frontend/package.json`） | **0 MB**（复用系统 Edge 154） | `npm install` 2 秒；`npm audit` 报告 **0 漏洞** |
| 未采用：`@playwright/test` + `npx playwright install` | 2+ 个包 | 数百 MB | 安装成本与依赖面更大，且沙箱/网络风险更高 |

> 该依赖**只装在子目录**，`frontend/package.json` 与 `package-lock.json` 未被改动（已用哈希核对）。

---

## 3. 测试矩阵

### 3.1 用例矩阵（18 项，全部通过）

| # | 用例 id | 优先级 | 验证目标 | 结果 | 耗时 |
| --- | --- | --- | --- | --- | --- |
| 1 | `L01-home-three-entries` | P0 | 首页加载 + 三入口切换 + `/api/v1/mock/demo` 真实请求 | ✅ | 1.7s |
| 2 | `L02-transfer-analysis-readiness` | P0 | 无已核验目录时如实报错，⛔ 不伪造版本 | ✅ | 1.5s |
| 3 | `L03-makeup-path-structure` | P0 | 四状态 + 教学班 + 风险/未决 + Mock 标识 | ✅ | 1.3s |
| 4 | `L04-ai-full-two-confirmations` | P0 | **两次确认完整闭环**（含"未确认不得求解"） | ✅ | 2.0s |
| 5 | `L05-adopted-plan-refreshes-view` | P0 | 采用后用后端候选刷新展示方案（含导航切换） | ✅ | 2.0s |
| 6 | `L06-reject-keeps-original` | P0 | 拒绝候选 ⇒ 原方案不变、不推进版本 | ✅ | 1.9s |
| 7 | `L07-drawer-reopen-and-navigation` | P0 | 关闭/重开抽屉、切换导航不产生误导状态 | ✅ | 1.9s |
| 8 | `L08-ambiguity-blocks-solve` | P0 | "太累"不得换算成学分数字；歧义禁止求解 | ✅ | 1.6s |
| 9 | `L09-locked-course-explicit-lock` | P0 | 显式锁定课程后候选必须保留该班次 | ✅ | 1.5s |
| 10 | `L10-candidate-expiry-410` | P0 | 候选过期（TTL=2s）⇒ 410，原方案不变 | ✅ | 4.4s |
| 11 | `R-375-layout` | P1 | 375px：三入口无横向溢出、抽屉近似全屏、按钮可滚动到可点 | ✅ | 32.1s |
| 12 | `R-768-layout` | P1 | 768px：右侧 520px 面板落在视口内、按钮可操作 | ✅ | 32.1s |
| 13 | `R-1440-layout` | P1 | 1440px：同上（长文本、候选对比） | ✅ | 32.2s |
| 14 | `E01-double-click-confirm-single-solve` | P1 | 连点 3 次"确认" ⇒ 只 1 次 `/solve` | ✅ | 32.0s |
| 15 | `E02-double-click-adopt-single-request` | P1 | 连点"采用" ⇒ 只 1 次 `/adopt` | ✅ | 32.5s |
| 16 | `E03-backend-down-shows-error-not-fixture` | P1 | 后端不可用 ⇒ 明确错误，⛔ 不回退 fixture | ✅ | 3.9s |
| 17 | `D01-ai-disabled-state` | P0 | 后端未启用 ⇒ 如实提示，⛔ 0 次 AI 请求 | ✅ | 2.4s |
| 18 | `P01-preview-fully-labelled` | P0 | 预览档 ⇒ 三重标注，⛔ 0 次 `/ai-planning/*` | ✅ | 1.8s |

### 3.2 服务档位（每组都是真实后端 + 真实前端）

| 组 | 后端 | 前端环境变量 | 用途 |
| --- | --- | --- | --- |
| live | QA 注入式测试模型（enabled=true，无密钥） | `VITE_AI_PLANNING_API_ENABLED=true`、预览=false | P0 主流程 / 响应式 / 并发 |
| shortTtl | 同上 + `QA_ADOPT_TTL_SECONDS=2` | 同 live | 候选过期 410 |
| disabled | QA app + `QA_AI_PLANNING_ENABLED=0`（**不注入模型**） | 同 live | 未启用档 |
| preview | live 后端（只为 Demo 数据） | `VITE_AI_PLANNING_API_ENABLED=false`、预览=true | 纯前端预览标注 |
| deadBackend | 端口**不监听**（Vite 代理指向空端口） | 同 live | 后端不可用 |

### 3.3 关于"注入式测试模型"的边界（任务书要求）

- 注入方式与既有后端测试**完全一致**：`app.dependency_overrides[get_ai_planning_service]`；
- 入口是**测试目录内**的文件 `backend/tests/qa_browser_e2e/qa_app.py`，
  ⛔ **生产代码零改动**、⛔ **没有新增环境变量或公开假模型开关**；
- 被覆盖的只有永久 Mock 回放通道 `GET /api/v1/mock/demo`，
  且覆盖是**插到路由表最前面**（`include_router` 是追加，同路径后注册的路由永远不会被匹配 ——
  这是实现过程中真实踩到并修正的坑，见 §5）；
- 覆盖数据带 `X-QA-E2E-Seed: mock-qa-seed` 响应头与 `qa_e2e_seed` 字段；
- `/status` 如实返回 `live_model_available=false`、`api_key_configured=false`。

---

## 4. 浏览器实际发出的 HTTP 请求（不是模拟）

抽取每例的请求清单（去重），关键证据：

| 用例 | AI 规划相关请求 | 说明 |
| --- | --- | --- |
| L04（完整闭环） | `GET /status`、`POST /interpret`、`POST /solve`、`POST /adopt` | 四个接口**全部真实调用**，且顺序为解析 → 确认后求解 → 二次确认采用 |
| L05 / L06 / E02 | `POST /interpret` + `POST /solve` + `POST /adopt` | L06 的 `/adopt` 为 `accept=false`；E02 连点后仍只 1 次 |
| L07（重开抽屉） | `POST /interpret` + `POST /solve`（**无 adopt**） | 仅打开抽屉不产生 `/adopt`；切换导航不新增 `/solve` |
| L08（歧义） | 只有 `POST /interpret` | 存在歧义时**不调用** `/solve`（有断言） |
| L10（过期） | `POST /interpret` + `/solve` + `/adopt` | `/adopt` 返回过期语义，页面显示 `session_expired` |
| D01（未启用） | 只有 `GET /status` | `/interpret`、`/solve`、`/adopt` **调用次数为 0**（有断言） |
| P01（预览） | **无任何 `/ai-planning/*`** | 完全走前端 fixture（有断言） |
| E03（后端不可用） | 有请求但全部失败 | 页面显示错误，⛔ 未出现预览/替代数据 |

每个用例还记录了**响应体片段**（含错误体），用于确认"浏览器实际收到什么"。

---

## 5. 发现的问题与修复情况

四类问题，**全部是测试基础设施/测试用例本身的问题，未发现产品缺陷**。
⛔ 未修改任何生产代码；⛔ 未修改任何业务规则、方案状态、数据来源或公共契约。

| # | 现象 | 根因 | 处理 |
| --- | --- | --- | --- |
| 1 | QA 应用的 `/api/v1/mock/demo` 覆盖**不生效**（页面拿到仓库自带演示数据） | `app.include_router` 是**追加**路由；同路径后注册的路由永远不会被匹配 | 在 `qa_app.py` 里把覆盖路由**插到 `app.router.routes` 最前面**（并先移除同路径旧路由），再断言响应头与字段 |
| 2 | 子进程日志重定向导致 `spawn ENOENT` / `stdio` 非法 | DSH 沙箱下 `spawn` 的 `stdio` 只能用 `pipe`/`inherit`/`ignore`；传 Stream 对象非法，传 fd 触发 ENOENT | 新增 `dispatchers/stdio_inherit.mjs`：runner 以 `stdio:['ignore',fd,fd]` 拉起它，它再用 `inherit` 拉起真实服务；日志仍落盘到 `artifacts/logs/` |
| 3 | 截图写到了错误目录（`tools/browser-e2e/lib/artifacts`） | `harness.mjs` 的 `ARTIFACT_DIR` 基准目录少算一层 | 修正为 `tools/browser-e2e/artifacts`；并把截图改为**只截视口**（抽屉是 fixed 面板，`fullPage` 会把它压扁） |
| 4 | 若干用例初次失败（超时/断言） | 测试自身的假设不对：① 把 `ai-generator-kind` 的**用户标签**当成后端原始枚举；② 消息里的学分上限高于上下文已声明上限 → 后端**正确地**禁止确认；③ 在 `v-if` 子元素尚未挂载时就读文本；④ 误以为 768px 下抽屉应全屏（CSS 是 `min(520px, 96vw)` 的右侧面板）；⑤ 采用按钮在抽屉滚动区内，需 `scrollIntoView` 后才可点 | 逐条改正**测试**：等面板子元素就绪、使用可确认的学分上限、按 CSS 事实断言布局、滚动后再点击、断言"界面如实标注 + 不出现 deepseek_live" |

**真实产品行为验证结论（未发现缺陷）**

- 两次确认门有效：未确认时 `/solve` 调用次数为 **0**；
- 后端在学分上限高于已声明上限时**正确地**拒绝确认（`credit_limit_conflicts_with_declared_max`），
  前端禁用确认按钮 —— 这是设计意图，不是缺陷；
- "太累"没有被换算成任何学分数；
- 采用只是 `process_local_session`，页面明确标注"未持久化保存"；
- Mock / 测试替身 / 预览三者的标注都正确且互不混淆。

---

## 6. 截图存放位置

`tools/browser-e2e/artifacts/`（26 张，按档位分目录）：

| 目录 | 文件 |
| --- | --- |
| `live/` | `L01-home-ai-adjust`、`L02-transfer-analysis`、`L03-makeup-path`、`L04-a-intent-draft`、`L04-b-candidate-compare`、`L04-c-adopted`、`L05-a-ai-view-after-adopt`、`L05-b-makeup-path-after-adopt`、`L06-rejected`、`L07-reopened-drawer`、`L07-after-nav`、`L08-ambiguity`、`L09-a-locked-before-solve`、`L09-b-candidate-keeps-lock`、`L10-expired-candidate` |
| `responsive/` | `R-375-drawer`、`R-375-candidate`、`R-768-drawer`、`R-768-candidate`、`R-1440-drawer`、`R-1440-candidate` |
| `resilience/` | `E01-double-click`、`E02-double-adopt`、`E03-backend-down` |
| `disabled/` | `D01-ai-disabled` |
| `preview/` | `P01-preview-notice` |

另外：`artifacts/browser-e2e-results.json`（每例状态、耗时、备注、请求清单）、
`artifacts/logs/*.log`（五组服务的启动日志）。

**人工核对过的关键截图**

- `live/L04-b-candidate-compare.png`：候选对比面板显示
  **新增 62004005（班号 6200400520260101）/ 移除：无 / 替换：无 / 保持 4 项**、
  **学分变化 原方案 12 · 候选 15 · 总学分 +3**、候选风险与未决事项 ——
  与"真实 Planner 产生候选"一致；页面顶部同时显示 Mock 演示通道警示。
- `responsive/R-375-drawer.png`：手机上抽屉近似全屏，头部显示
  `真实接口 · enabled=true · api_key_configured=false · live_model_available=false · model=qa-test-double`。

---

## 7. 未验证事项（如实记录）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| **真实 DeepSeek 在线调用** | **NOT VERIFIED** | 环境无密钥；本报告全部 AI 结果来自注入式测试模型（`test_double`） |
| 真实已核验培养方案目录 | **BLOCKED** | 转专业分析如实显示"没有已核验版本目录"；个人规划端到端未在浏览器里跑通成功路径 |
| 真实教学班快照 / 真实成绩数据 | **BLOCKED** | 全部使用人工构造演示数据（`data_source=mock`） |
| 真实浏览器端到端的"真实数据"闭环 | **未执行** | 需要上游已核验数据才能执行 |
| 解释面板（规则模板）的浏览器交互 | **未覆盖** | 本轮聚焦三入口与 AI 调整闭环；解释仅作为既有页面对照出现 |
| 持久方案版本 / 跨进程会话 | **不存在** | `adopted_version_scope=process_local_session` |
| 依赖漏洞修复（`tinypool` / `@vitest/mocker` / `source-map-js`） | **未修复** | 已在上一轮报告中给出分级建议；本轮未改依赖清单 |

---

## 8. 本轮改动的文件

**新增（全部为测试基础设施，⛔ 无生产代码改动）**

| 文件 | 作用 |
| --- | --- |
| `backend/tests/qa_browser_e2e/qa_app.py` | QA 专用 ASGI 入口：注入测试模型 + 覆盖 Mock 回放通道（插到路由表最前） |
| `backend/tests/qa_browser_e2e/qa_demo_data.json` | 人工构造演示数据（含一门**尚未选班**的必修课，使真实 Planner 能产生候选） |
| `backend/tests/qa_browser_e2e/verify_seed.py` | 夹具自检：确认"夹具 + 真实 Planner = 一个真实候选" |
| `tools/browser-e2e/package.json` | 套件自身依赖（仅 `playwright-core`） |
| `tools/browser-e2e/lib/harness.mjs` | 断言、截图、请求/响应采集、极简 runner |
| `tools/browser-e2e/lib/servers.mjs` | 服务编排（随机端口、健康等待、日志、优雅停止） |
| `tools/browser-e2e/dispatchers/stdio_inherit.mjs` | 沙箱兼容的子进程启动包装器 |
| `tools/browser-e2e/cases.mjs` | 18 个浏览器用例 |
| `tools/browser-e2e/run_browser_e2e.mjs` | 运行器（5 组服务 + 结果 JSON） |
| `tools/browser-e2e/.gitignore` | 忽略 `node_modules/`、`artifacts/` |
| `docs/final_upgrade/reports/BROWSER_E2E_REPORT.md` | 本报告 |

**未改动**：`/schemas/**`、`/docs/interfaces/**`、`frontend/src/**`、`frontend/package.json`、
`backend/app/**`（生产代码零改动）。

---

## 9. 回归结果（本轮同分支复跑）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 浏览器 E2E | `node tools/browser-e2e/run_browser_e2e.mjs` | **18 passed / 0 failed** |
| 后端 pytest | `python -m pytest -q`（`backend/`，`PYTHONUTF8=1`） | **3188 passed / 2 failed / 2 skipped**（与基线一致） |
| 前端 Vitest | `npx vitest run` | **274 passed / 0 failed**（18 文件） |
| 前端类型检查 | `npx vue-tsc --noEmit` | **exit 0** |
| 前端构建 | `npm run build` | **exit 0**（JS 236.02 kB / gzip 76.11 kB） |

**2 项后端失败**为既有平台差异（Python 3.14 `Path("bad\x00path")`、Windows ZIP 成员名反斜杠），
在本分支与历史基线上一律同样失败，与本轮改动无关；⛔ 未修改其实现或测试。

**未产生任何新回归。**

---

## 10. 建议下一步

1. 上游提供**已核验培养方案目录**后，在浏览器里补跑"转专业分析 → 个人规划成功路径"，
   并把结果接到 AI 调整的上下文（当前该路径如实显示"没有已核验版本目录"）；
2. 用**新密钥**在受控环境做一次真实 DeepSeek 在线验证（`generator_kind=deepseek_live`）；
3. 按上一轮报告的分级建议处理依赖漏洞（P1：非 force 的 `npm audit fix`；P2：单独评审 vitest 升级）；
4. 把 `tools/browser-e2e` 纳入 CI（先在受控 runner 上跑，避免对不可信 PR 执行测试）。
