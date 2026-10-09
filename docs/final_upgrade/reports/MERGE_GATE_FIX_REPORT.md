# 合并前收尾报告：PR #64 可合并性 + 前端依赖安全评估

- **日期**：2026-10-09
- **处理分支**：`fix/final-upgrade-integration-qa-mergeable`（从 PR #64 候选 `1c7d101` 派生）
- **合并提交**：`c774368e4943cc598174f85d17409ba4932ba252`
- **分支 head（含本报告）**：`f9d62b997a1820ffaae34134d466edca8611f219`
- **执行环境**：Windows + PowerShell；Python 3.14.7（`PYTHONUTF8=1`）；Node v24.19.0 / npm 11.17.0；Vitest 3.2.7 / vue-tsc 3.3.11 / Vite 8.3.1
- **公共契约**：**未修改** `/schemas/**` 与 `/docs/interfaces/**`
- **受保护分支**：`main`（`c75b6da`）与 `feature/final-upgrade-integration-qa`（`1c7d101`）**均未改动**，⛔ 未合并任何 PR
- **使用数据**：**Mock**；⛔ 未使用真实学生隐私数据

---

## 0. 本次读取到的 Review 意见

**PR #64（2026-10-09T02:04:56Z，head `1c7d101`）**

> Merge gate review: GitHub currently reports `mergeable=false` for PR #64
> (`feature/final-upgrade-integration-qa` → `feature/final-upgrade`).
> This is a blocker for safe integration. Do not force merge or modify main.
> Please refresh branch against current target and resolve any conflict in a
> separate fix/QA branch, then run combined regressions and get a new
> mergeable check. No approval/merge in this review.

**PR #67（两条，head `631443d` / `07564dc`）**

> Architecture Review — PASS WITH CONDITIONS (joint integration). …
> Caveats before final merge:
> (1) investigate/document npm ci 4 dependency advisories incl 2 critical;
>     establish whether exploitable in shipped bundle;
> (2) live DeepSeek NOT VERIFIED, real curriculum/offerings E2E NOT VERIFIED,
>     real browser E2E not run;
> (3) 2 backend failures need baseline classification recorded;
> (4) process-local adopt must not be called durable student save/official enrollment;
> (5) update API handoff to clarify nonempty replaced row from/to and
>     non-feasible candidate_id. No permission to merge main.

---

## 1. 任务一：PR #64 的 `mergeable=false` 根因与解决

### 1.1 根因（可复核）

| 项 | 事实 |
| --- | --- |
| 候选 head | `feature/final-upgrade-integration-qa` = `1c7d101` |
| 目标 head | `feature/final-upgrade` = `31c8473` |
| 共同祖先 | `d387b9a990c6fbb7138212b5c6141616ad2dc2b3` |
| 目标分支领先候选 | **2 个提交**：`d3ad53a`、`31c8473` |
| 这 2 个提交改了什么 | **只新增 2 个文件**：<br>`docs/final_upgrade/AI_PLANNING_NEXT_PHASE.md`<br>`docs/final_upgrade/DEEPSEEK_PLANNING_AGENT_V1.md` |
| 与候选变更集的关系 | 候选相对祖先改了 **49 个文件**；两个集合**交集为空** |
| 复现命令 | `git log --oneline 1c7d101..31c8473`、`git diff --name-status $(git merge-base 1c7d101 31c8473) 31c8473` |

**结论**：候选是在目标分支前进**之前**派生的，因此 GitHub 在当时的状态下无法给出干净的合并结果
（GitHub 的 `mergeable` 在首次查询时可能是 `null`/计算中或基于旧 snapshot，Reviewer 观测到的
`mergeable=false` 属该类过期状态）。**内容层面从来没有真正的冲突**：两边改的是互不相交的文件集合。

**现状复核（2026-10-09 本轮）**：直接查询 GitHub API，PR #64 现在返回
`"mergeable": true`、`"mergeable_state": "clean"`。

### 1.2 在独立分支上的解决过程（可复现）

```powershell
git worktree add <dir> feature/final-upgrade-integration-qa
cd <dir>
git log --oneline -1                       # 1c7d101
git merge --no-commit --no-ff origin/feature/final-upgrade
#   → Automatic merge went well; stopped before committing as requested   ← 0 冲突
git status --short
#   A  docs/final_upgrade/AI_PLANNING_NEXT_PHASE.md
#   A  docs/final_upgrade/DEEPSEEK_PLANNING_AGENT_V1.md
git commit -m "merge: refresh integration-qa candidate onto feature/final-upgrade (conflict-free)"
#   → c774368
git merge-base --is-ancestor origin/feature/final-upgrade HEAD   # → true
```

**关键证明**：合并后 `origin/feature/final-upgrade`（`31c8473`）**是** `HEAD` 的祖先。
即"候选已完整包含目标分支"，对目标分支**没有任何剩余差异**，
因此后续不会再有冲突；这正是 GitHub 报告 `mergeable=true` 的原因。

**合并只新增 2 个文档文件**（`git diff --cached --name-status` 输出即为这 2 条），
⛔ **未触碰候选的任何代码**：

| 检查 | 结果 |
| --- | --- |
| `backend/app/personal/**`、`app/explanation/**`、`app/api/personal_plan.py`、`app/api/explanation.py` | 全部保留 |
| `frontend/**`（含解释面板与三个入口） | 全部保留 |
| `backend/app/main.py`、`backend/tests/test_integration_orchestrator.py` | 未被本次合并改写 |

### 1.3 合并后联合回归（在合并树上真实执行）

```powershell
cd backend ; $env:PYTHONUTF8="1" ; python -m pytest -q
cd frontend; npm ci ; npx vitest run ; npx vue-tsc --noEmit ; npm run build
```

| 检查 | 结果 |
| --- | --- |
| 后端全量 pytest | **3078 passed / 2 failed / 2 skipped** |
| 前端 Vitest | **154 passed / 0 failed**（11 文件） |
| 前端 `vue-tsc --noEmit` | **exit 0** |
| 前端 `npm run build` | **exit 0**（`index.html` + CSS 27.99 kB + JS 144.11 kB / gzip 50.16 kB） |

→ **无新增回归**（详见 §4）。

### 1.4 交付物

- 分支：`fix/final-upgrade-integration-qa-mergeable`（已推送，head `c774368`）
- 合并内容：**仅** 2 个文档文件的冲突-free 刷新；候选全部代码原样保留
- ⛔ **未**强推、⛔ **未**改写候选分支历史、⛔ **未**修改 `main` / `feature/final-upgrade` / `feature/final-upgrade-integration-qa`

> **给负责人/Reviewer 的选择**：由于本次合并是"把目标分支的快照并入候选"，
> 候选分支若要走同一路径，只需把该合并提交（或等价的 `merge origin/feature/final-upgrade`）
> 放进候选分支即可。本轮**没有**权限改动候选分支，因此只提供独立 `fix/` 分支与可复现证据。

---

## 2. 任务二：`npm audit --json` 4 项漏洞分析

### 2.1 原始汇总

```powershell
cd frontend ; npm audit --json
#   auditReportVersion: 2
#   metadata.vulnerabilities: { info: 0, low: 0, moderate: 1, high: 1, critical: 2, total: 4 }
#   metadata.dependencies:    { prod: 25, dev: 216, optional: 79, peer: 0, peerOptional: 0, total: 240 }
#   受影响包: @vitest/mocker, source-map-js, tinypool, vitest
```

### 2.2 逐项分析

#### ① `tinypool` — **critical**（2 条公告）

| 项 | 内容 |
| --- | --- |
| 已安装版本 | `1.1.1` |
| 公告 | GHSA-5gmw-xhrv-c9v3（Prototype Pollution gadget in worker options → RCE，CWE-1321）<br>GHSA-85c8-ppgw-ccpr（Prototype Pollution Gadget to RCE in `run()` options，CWE-94 / CWE-1321） |
| 受影响区间 | `<=2.1.1`（含 1.x 全部版本） |
| 依赖路径 | `vitest@3.2.7` → `tinypool@1.1.1`（**仅测试依赖**；`package.json` 中 `vitest` 在 `devDependencies`） |
| 是否进入浏览器产物 | **否** — `dist/assets/*.js` 中检索 `tinypool` **0 命中** |
| 实际影响面 | 仅影响**在本机运行 Vitest** 的场景。触发需要攻击者能向 worker 池选项注入 `__proto__` 类键，而本项目的测试配置不接受外部输入；CI 若运行不可信 PR 的测试代码，风险等级才会上升 |
| 修复 | 需要 `tinypool >= 2.1.2`，而 `tinypool@1.x` **没有**修复版本；`vitest@3.2.7` 的依赖声明是 `tinypool: ^1.1.1`，无法在 1.x 内解决 |

#### ② `@vitest/mocker` — **moderate**（1 条公告）

| 项 | 内容 |
| --- | --- |
| 已安装版本 | `3.2.7`（位于 `vitest/node_modules/@vitest/mocker`） |
| 公告 | GHSA-82fw-gwwq-j7x9（Path Traversal / Arbitrary File Read via Redirect Mock，CWE-22，CVSS 5.9） |
| 受影响区间 | `>=2.1.0 <4.1.11` |
| 依赖路径 | `vitest@3.2.7` → `@vitest/mocker@3.2.7`（**仅测试依赖**） |
| 是否进入浏览器产物 | **否**（`dist/assets/*.js` 检索 `vitest` / `mocker` 0 命中） |
| 实际影响面 | 仅在运行 **`vi.mock` 的 redirect 模式** 且 mock 目标路径可控时可读取任意文件。本项目测试只 mock 自己的模块（`@/api/aiPlanning` 等），不接受外部路径 |
| 修复 | `@vitest/mocker >= 4.1.11`，即 **vitest 需升到 4.x/5.x** |

#### ③ `vitest` — **critical**（聚合条目）

| 项 | 内容 |
| --- | --- |
| 已安装版本 | `3.2.7`（**直接 devDependency**） |
| 受影响区间 | `0.0.95 - 4.1.10` |
| `via` | 传递自 ① `tinypool`（critical）与 ② `@vitest/mocker`（moderate） |
| 是否进入浏览器产物 | **否** |
| 实际影响面 | 同上：**纯开发/测试链路** |
| 修复 | `fixAvailable: { name: "vitest", version: "5.0.3", isSemVerMajor: true }` |

#### ④ `source-map-js` — **high**（唯一被 npm 判定为 **非 dev** 的包）

| 项 | 内容 |
| --- | --- |
| 已安装版本 | `1.2.1` |
| 公告 | GHSA-68fv-2mgg-jv7q（event-loop DoS through indexed source-map section offsets，CWE-1284，CVSS 7.5） |
| 受影响区间 | `>=1.0.0 <1.2.2` |
| 依赖路径（`npm ls source-map-js` 实测） | `vite@8.3.1 → postcss@8.5.28 → source-map-js@1.2.1`<br>`vue@3.5.43 → @vue/compiler-sfc@3.5.43 → source-map-js@1.2.1`（deduped）<br>`@vue/test-utils@2.5.1 → @vue/compiler-dom@3.5.43 → @vue/compiler-core@3.5.43 → source-map-js@1.2.1`（deduped） |
| 为什么被算作 prod | 在 lockfile 里它不是 `dev: true`（`vue` 与 `postcss` 是生产域依赖），因此 `npm audit` 把它归入生产统计——这不等于"它被打包进浏览器产物" |
| 是否进入浏览器产物 | **否** — `frontend/dist/assets/index-*.js` 是**单文件**（144.11 kB），检索 `postcss` / `source-map-js` / `SourceMapConsumer` **0 命中**；产物只有 `index.html` / `index-*.js` / `index-*.js.map` / `index-*.css` |
| 实际影响面 | 该库只在**构建期**解析 source map（Vue SFC 编译、PostCSS 处理）。`vite.config.ts` 里 `build.sourcemap: true` 只影响**我们自己源码**生成的 `.map`，浏览器只在打开 devtools 时才拉取，且不会把外部来源的 source map 喂给 `source-map-js`。因此**当前不存在可利用的运行时路径** |
| 修复 | `source-map-js@1.2.2`（registry `latest`），属**补丁级**升级，`npm audit fix`（⛔ 非 `--force`）即可完成；`postcss` / `@vue/*` 的依赖区间（`^1.0.2`）都接受 1.2.2 |

### 2.3 影响范围汇总

| 包 | 严重度 | 域 | 进入浏览器产物 | 可被外部输入触发 | 是否 production 风险 |
| --- | --- | --- | --- | --- | --- |
| `tinypool` | critical | dev/test | 否 | 否 | **否** |
| `@vitest/mocker` | moderate | dev/test | 否 | 否 | **否** |
| `vitest` | critical | dev/test | 否 | 否 | **否** |
| `source-map-js` | high | 构建期（非 dev 标记） | 否 | 否 | **否**（无可利用路径） |

**结论**：4 项漏洞**全部不进入交付的浏览器产物**，当前**没有可利用的生产运行时路径**。
其中 2 项 critical 位于本机测试运行器（Vitest）链路，属**开发环境风险**，
不是线上服务风险；`source-map-js` 属构建期风险。

### 2.4 安全修复建议（按风险/成本排序，⛔ 本轮均未执行）

| 优先级 | 动作 | 命令 | 风险 | 说明 |
| --- | --- | --- | --- | --- |
| **P1（建议尽快、低风险）** | 仅升级 `source-map-js` 到 `1.2.2` | `npm audit fix`（**⛔ 不是 `--force`**） | 低：补丁级、`^1.0.2` 区间内 | `npm audit fix --dry-run` 已实测：它会**只**修 `source-map-js`，并明确提示剩余 2 项需要 `--force` |
| **P2（需单独评审）** | 升级测试运行器以消除 `tinypool` / `@vitest/mocker` | `npm i -D vitest@^4.1.11`（或 `@^5.0.3`）+ 全套 `npx vitest run` / `vue-tsc` / `build` 回归 | **中**：`isSemVerMajor: true`，属跨主版本升级，可能改测试配置/API | `vitest@4.1.11` 与 `5.0.3` 都为 registry 上的正式版本；⛔ 未经独立评审不要合并 |
| **P3（可选缓解）** | 若短期不能升级 vitest，则收紧运行边界 | 在 CI 中对不可信来源的 PR **不自动运行** `npm test`；测试只在受控 runner 上跑 | 低 | 该漏洞的触发前提是"运行不可信代码/参数"；对本仓库自有用例无实际暴露面 |
| **P4（不建议）** | `npm audit fix --force` 或"升级全部依赖" | — | 高 | ⛔ 任务明确禁止；会连带跨主版本变更，超出本次收尾范围 |
| **P5（长期）** | 把 `npm audit` 纳入 CI 门禁并设定阈值 | — | 低 | 建议只对 **critical + 可进入产物** 的漏洞硬失败；dev-only 允许带期限豁免 |

**为什么不建议现在直接升 vitest**：
① 属跨主版本（3 → 4/5），需要单独回归与评审；
② 两项 critical 的实际暴露面是"本机/CI 运行测试"，不进入用户浏览器；
③ 本轮任务是"合并前收尾"，改动测试栈会扩大风险面。

---

## 3. 任务三：修复后重新回归（是否产生新回归）

### 3.1 PR #64 候选（合并树上，本轮真实执行）

| 检查 | 合并前（`1c7d101` 基线） | 合并后（`c774368`） | 是否回归 |
| --- | --- | --- | --- |
| 后端 pytest | 3078 passed / 2 failed / 2 skipped | **3078 passed / 2 failed / 2 skipped** | **否**（集合相同） |
| 前端 Vitest | —— | **154 passed / 0 failed** | 否 |
| 前端 typecheck | —— | **exit 0** | 否 |
| 前端 build | —— | **exit 0** | 否 |

### 3.2 PR #67 分支（上一轮结果，作为对照）

| 检查 | 结果 |
| --- | --- |
| 后端 pytest | 3188 passed / 2 failed / 2 skipped |
| 前端 Vitest | 274 passed / 0 failed（18 文件） |
| 前端 typecheck / build | exit 0 / exit 0 |

> ⚠️ **两组计数不可直接比较**：PR #64 候选**不含** PR #66（DeepSeek Controller，96 项测试）
> 与 PR #65（AI Planning Frontend）的代码，因此 3078 vs 3188、154 vs 274 的差异是**范围差异**，
> 不是回归。

### 3.3 结论

**未产生任何新的回归。** 合并只新增 2 个文档文件，未触碰任何代码，因此两侧测试集合
与合并前逐项一致。

### 3.4 遗留失败基线分类（Review 条件 3）

两项后端失败在**本轮任何改动之前**、在多个分支上以同一命令、同一环境稳定复现，
且都与 PR #64/#67 的改动文件无关：

| # | 用例 | 分类 | 依据 |
| --- | --- | --- | --- |
| 1 | `tests/test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]` | **既有 · Python 版本语义差异** | Python 3.14 起 `Path("bad\x00path")` 不再抛 `ValueError`；在 `d387b9a`（PR #64 祖先）、`37f62f2`、`c60bf20`、`1c7d101`、`c774368` 上均同样失败 |
| 2 | `tests/test_curriculum_docx_reader.py::test_duplicate_or_unsafe_archive_members_are_rejected[word\\DEMO-PRIVATE-PART]` | **既有 · Windows 平台语义差异** | Windows 上 ZIP 成员名中字面反斜杠的处理与 POSIX 不同；同样在全部上述分支上复现 |

两者涉及模块为 `app/curriculum/json_reader.py` 与 `app/curriculum/docx_reader.py`，
**不在**本候选或本轮的改动文件内；⛔ 本轮未修改其实现或测试，⛔ 未放宽任何断言。

---

## 4. PR #67 Review 的 5 项合并门槛条件处理

| # | 条件 | 本轮处理 | 状态 |
| --- | --- | --- | --- |
| 1 | 调查/记录 npm ci 的 4 项漏洞并判断产物是否可利用 | 见 §2：逐包给出公告、CVSS、依赖路径、产物检索结果 | ✅ **已完成**（结论：全部不进入浏览器产物，无可利用生产路径） |
| 2 | live DeepSeek / 真实培养方案与教学班 E2E / 真实浏览器 E2E 未验证 | 如实保持未验证；`/status` 在本环境返回 `live_model_available=false` | ✅ **如实记录，仍为 NOT VERIFIED** |
| 3 | 2 项后端失败需要基线分类记录 | 见 §3.4：逐项分类为 Python / Windows 平台差异，并列出复现分支 | ✅ **已完成** |
| 4 | `process_local_session` 的采用不得被称作持久保存或教务选课 | 后端响应字段为 `adopted_version_scope=process_local_session`、`original_plan_unchanged`；前端文案为"仅在本进程会话内有效，未持久化"；本轮再次确认无"已持久化/已选课"表述 | ✅ **已确认** |
| 5 | 更新 API handoff，说明非空 `replaced` 行与 `no_feasible_candidate` 的 `candidate_id` | 已由 `07564dc`（PR #67 head）完成：新增"联合验收后澄清"三条（`replaced` 用 `from_class`/`to_class`、`no_feasible_candidate` 的 `candidate_id` 只是记录标识、`locked_courses[].reason` 可空） | ✅ **已满足**（本轮复核确认，无需再改） |

---

## 5. 交付物与分支策略

| 交付物 | 位置 |
| --- | --- |
| 合并刷新分支 | `fix/final-upgrade-integration-qa-mergeable`（head `c774368`），已推送 |
| 本报告 | `docs/final_upgrade/reports/MERGE_GATE_FIX_REPORT.md` |
| 候选状态更新 | `docs/final_upgrade/INTEGRATION_QA_STATUS.md`（新增"Review 反馈处理"一节） |

**⛔ 未做**（超出授权或依赖人工裁决）：
- 未强推、未改写 `feature/final-upgrade-integration-qa` 或 `feature/ai-planning-joint-e2e` 的历史；
- 未合并任何 PR；未修改 `main`、`feature/final-upgrade`、`feature/final-upgrade-integration-qa`；
- 未执行 `npm audit fix --force`、未升级 `vitest`、未改动 `package.json` / `package-lock.json`；
- 未修改 `/schemas/**` 与 `/docs/interfaces/**`。

**Draft PR 建议**：
- 对 PR #64 的可合并性修复：`fix/final-upgrade-integration-qa-mergeable` → `feature/final-upgrade-integration-qa`
- ⛔ 两者都保持 Draft，等待负责人与 Reviewer 决定是否把该合并提交引入候选分支。

---

## 6. 结论

```text
TASK 1  PR #64 mergeable=false：根因已定位（候选派生后目标分支前进 2 个纯文档提交，零文件重叠）；
        已在独立 fix/ 分支完成 conflict-free 刷新（合并提交 c774368），
        且可证明对目标分支无剩余差异；合并后联合回归无新增回归。
TASK 2  npm audit 4 项漏洞已逐项分析：1 moderate + 1 high + 2 critical，
        全部位于开发/测试或构建期链路，⛔ 均不进入交付的浏览器产物；
        给出 P1–P5 分级修复建议（P1 可用非 force 的 npm audit fix 解决 high 项）。
TASK 3  合并后回归：后端 3078/2/2、前端 154 passed、typecheck exit 0、build exit 0 →
        无新增回归（2 项失败为既有平台差异，已分类记录）。
TASK 4  报告已提交到独立分支，保持 Draft，未合并、未改 main。
```
