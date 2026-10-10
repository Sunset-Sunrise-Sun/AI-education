# 最终交付冲刺报告（`release/final-upgrade-demo-readiness`）

- **基线**：`origin/feature/final-upgrade` = **`85152e9`**（"Merge PR #70: UX polish and browser E2E QA"）
- **本分支**：`release/final-upgrade-demo-readiness`
- **执行环境**：Windows NT 10.0.26200；Python **3.14.7**（`PYTHONUTF8=1`）；Node **v24.19.0** / npm **11.17.0**；
  浏览器：**系统 Microsoft Edge**（`playwright-core` `channel=msedge`，⛔ 未下载浏览器二进制）
- **使用数据**：页面 **Mock**；AI 解析 **注入式测试替身模型**；Planner 为**真实冻结算法**
- **真实 DeepSeek 在线调用**：**BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE**（详见 §4）
- **真实教务数据**：**BLOCKED**（详见 §5）
- **公共 Schema / Planner 核心算法 / `main`**：**均未改动**
- **⛔ 未合并任何 PR、未自动合并**

---

## 0. 开工前必须读取的文档：实际存在情况

| 要求读取 | 状态 |
| --- | --- |
| `AGENTS.md` | ✅ 已读（343 行） |
| `PROJECT_CONTEXT.md` / `DEVELOPMENT_RULES.md` | ⚠️ **仓库中不存在** —— 已用 `docs/ARCHITECTURE.md` + `AGENTS.md` 代替 |
| `docs/ARCHITECTURE.md` | ✅ 已读 |
| `docs/final_upgrade/DEMO_ACCEPTANCE_RUNBOOK.md` | ✅ 已读 |
| `docs/final_upgrade/DEMO_SCRIPT.md` | ✅ 已读（并在 §7 追加彩排记录） |
| `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md` | ✅ 已读 |
| `docs/final_upgrade/reports/UX_BROWSER_E2E_FINAL_ACCEPTANCE.md` | ✅ 已读 |
| `docs/final_upgrade/reports/AI_PLANNING_JOINT_QA_REPORT.md` | ✅ 已读 |
| `docs/final_upgrade/reports/MERGE_GATE_FIX_REPORT.md` | ⚠️ **仓库中不存在**（其他同类报告存在，已读） |

**Git 核实**：`85152e9` 确实是 `feature/final-upgrade` 的 HEAD，且其父提交包含 PR #70 的
`ed82794`（联合验收复跑）与 `01fc7b5`（移动端关闭按钮修复）。

---

## 1. P0 —— 合并后完整冒烟与回归（**本轮实际执行**，全部为现场结果）

### 1.1 后端回归

```powershell
cd backend; $env:PYTHONUTF8='1'; python -m pytest -q
```

| 项 | 结果 |
| --- | --- |
| 通过 | **3188** |
| 失败 | **2** |
| 跳过 | **2** |
| 耗时 | 约 63 秒 |

失败项（与历史基线**完全一致**，属既有 Windows / Python 3.14 平台语义差异）：

```text
tests/test_curriculum_docx_reader.py::test_duplicate_or_unsafe_archive_members_are_rejected[word\\DEMO-PRIVATE-PART]
tests/test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]
```

- 前者：Windows ZIP 成员名里反斜杠的语义差异；
- 后者：Python 3.14 起 `Path("bad\x00path")` 不再抛错。
- ⛔ 未修改其实现或测试；**失败集合与基线一致，未出现新失败**。

### 1.2 前端回归

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 依赖安装 | `npm ci` | exit 0 |
| 单元测试 | `npx vitest run` | **313 passed / 0 failed**（20 文件） |
| 类型检查 | `npx vue-tsc --noEmit` | **exit 0** |
| 构建 | `npm run build` | **exit 0**（JS 249.57 kB / gzip 80.62 kB） |

> 合并前基线为 **303** 项；本轮新增 10 项（`tests/ai-drawer-capability.spec.ts`），
> 并更新 1 项旧断言（见 §3.4），因此为 **313**。

### 1.3 浏览器回归（真实 Edge）

| 运行 | 结果 |
| --- | --- |
| 全量（含本轮新增的演示彩排） | **24 passed / 0 failed / 0 skipped**（约 3 分 30 秒） |
| 严格开关 `QA_STRICT_HEADER_BUTTON=1 --filter=R-` | **3 passed / 0 failed**（375 / 768 / 1440） |

覆盖项（与任务书要求逐条对应）：

| 要求 | 覆盖用例 | 结果 |
| --- | --- | --- |
| 三入口正常 | `L01` | ✅ |
| AI 调整两次确认 | `L04`（含"第一次确认前 `/solve` 次数为 0"） | ✅ |
| Mock 与测试模型标注 | `L04`、`L03`、`P01` | ✅ |
| 采用后的当前方案刷新 | `L05` | ✅ |
| 拒绝 / 过期 / 无解 / 后端断开 | `L06`、`L10`、`E03`、`L08`（歧义禁止求解） | ✅ |
| 规则解释面板 | `X01`、`X02` | ✅ |
| 移动端按钮与滚动 | `R-375/768/1440`、`E01`、`E02` | ✅ |
| 无横向溢出 | 三个断点均断言 `scrollWidth - clientWidth <= 1` | ✅ |
| **无遗留进程** | 运行后 `node`/`python` 残留 **0**、headless Edge **0** | ✅ |

**"无遗留进程"是怎么保证的**：上一轮发现 Windows 下
`node(包装器) → cmd.exe → node(vite) / python(uvicorn)` 进程链只杀包装器会留下孤儿
（曾累积 317 node / 97 python）。现已改为：包装器把真实子进程 PID 写入日志，
清理时对它执行 `taskkill /PID <pid> /T /F`（整棵树），runner 结束显式 `process.exit`。
**本轮每次运行后都实测残留为 0**。

**未误杀他人进程**：清理按命令行精确匹配本工作树路径（`AI-education-release` / `qa_browser_e2e`）；
开发者自己的 20 个非 headless Edge 进程（DSH Web GUI 等）**全程未被触碰**。

---

## 2. P1 —— 移动端头部信息密度（观察项 O-1）：**已修复**

### 2.1 修复内容

| 位置 | 改动 |
| --- | --- |
| `frontend/src/components/ai/drawerCapability.ts` | **新增**：把"状态 → 人话摘要 + 技术详情"抽成纯函数，便于**穷举**测试 |
| `frontend/src/components/ai/AiAdjustDrawer.vue` | 头部改为"一句话能力状态" + 原生 `<details>` 折叠的"技术详情（配置与限额）"；新增 `ai-drawer-tech*` 测试标识，**保留**原有 `ai-drawer-status` / `ai-drawer-channel` |
| `frontend/src/styles/base.css` | 新增 `.ai-drawer__capability`、`.ai-drawer__tech*` 样式；`.ai-drawer__head-main` 允许收缩；手机宽度技术详情单列 |
| `frontend/tests/ai-drawer-capability.spec.ts` | **新增** 10 项：逐档区分 + 不夸大 + 不泄露 |
| `frontend/tests/ai-planning-drawer.spec.ts` | 更新 1 项旧断言（见 §3.4） |
| `tools/browser-e2e/cases.mjs` | 三档响应式新增：摘要不含原始字段、≤3 行、技术详情默认折叠、展开后字段齐全、无横向溢出、无密钥形态字符串 |

### 2.2 效果对比（真实浏览器实测）

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 375px 头部状态行 | `enabled=true · api_key_configured=false · live_model_available=false · model=…` 折 **2.8 行** / 54px | 人话摘要 **2 行** / 39px + 折叠的"技术详情"标题 1 行 |
| 768px | 1.8 行 / 35px | **1 行** / 20px |
| 1440px | 1.8 行 / 35px | **1 行** / 20px |
| 原始字段 | 一直铺在头部 | **完整保留**在可展开的技术详情里（⛔ 未删任何信息） |

375px 实际文案：**"已启用，但服务端没有配置模型密钥，本次不能解析需求"**
（这正是本档位的**如实**状态：控制器开了、注入的是测试替身、没有真实密钥。）

### 2.3 五档能力状态：逐档区分（有穷举测试锁定）

| 情形 | 摘要文案 |
| --- | --- |
| 通道完全不可用（无真实接口、无预览） | 未启用 AI 调整接口，也没有可用的演示数据；本次不能进行任何调整 |
| 尚未取得状态 | 尚未取得服务端状态 |
| 前端预览 | 当前为演示模式：状态与结果都是前端预览 fixture，未调用后端服务 |
| 服务端未启用 | 服务端未启用 AI 调整，本次不能生成候选 |
| 已启用、无密钥 | 已启用，但服务端没有配置模型密钥，本次不能解析需求 |
| 已启用、有密钥、无在线模型 | 已启用，但当前没有可用的在线模型，本次不能解析需求 |
| 配置就绪（`live_model_available=true`） | 服务端已启用且已注入模型密钥；**配置就绪不代表在线调用已经成功** |

**第 4 项要求（不得把 `live_model_available=true` 当成在线调用成功）**：
摘要与"技术详情"里都明写"仅表示开关与密钥就绪，**不代表已成功调用**"，
并有测试断言摘要**不得**包含 `调用成功` / `在线模型已接入` / `DeepSeek 已接入`。

**第 5 项要求（不泄露密钥）**：技术详情只列布尔事实与模型名，
测试断言其中**不得**出现 `sk-` 形态字符串、`DEEPSEEK_API_KEY=`、
或 `api_key: <8 位以上>` 形态。浏览器端也断言展开后无密钥形态字符串。

**第 6 项要求（保留测试定位标识，必要时更新旧断言）**：
`ai-drawer-status`、`ai-drawer-channel`、`ai-drawer-close` 等**全部保留**；
唯一更新的是一处**依赖旧文案**的断言（见 §3.4）。

**第 7 项要求（三档复测，标题与关闭按钮不再重叠）**：见下表。

| 视口 | 关闭按钮 | 标题/摘要 | 横向溢出 | 结论 |
| --- | --- | --- | --- | --- |
| 375px | 85×39px、**标签 1 行** | 标题 2 行 + 摘要 2 行，未与按钮重叠 | 0px | ✅ |
| 768px | 85×39px、1 行 | 摘要 1 行 | 0px | ✅ |
| 1440px | 85×39px、1 行 | 摘要 1 行 | 0px | ✅ |

> 已目视核对截图：`tools/browser-e2e/artifacts/responsive/R-{375,768,1440}-drawer.png`
> 与展开态 `R-{375,768,1440}-drawer-tech.png`。375px 下"✕ 关闭"单行位于右上，
> 标题与摘要换行在其左侧，**无重叠、无遮挡**。

---

## 3. P1 —— npm 依赖安全：**已清除全部已知漏洞**

### 3.1 本次实测审计（**不是引用旧报告**）

修复前 `npm audit --json`：

| 包 | 严重度 | 直接依赖 | 修复建议 |
| --- | --- | --- | --- |
| `tinypool@1.1.1` | **critical** ×2 | 否 | 需 `vitest@5.0.3`（semver major） |
| `vitest@3.2.7` | **critical**（聚合） | **是** | 同上 |
| `@vitest/mocker@3.2.7` | moderate | 否（vitest 内嵌） | 同上 |
| `source-map-js@1.2.1` | high | 否 | 有补丁版本 |

合计 **4 项**（2 critical / 1 high / 1 moderate）。

### 3.2 第一步：低风险补丁（`source-map-js`）

```powershell
npm audit fix            # ⛔ 未使用 --force
```

结果：`source-map-js@1.2.1 → 1.2.2`（仅 `package-lock.json` 变更，**3 行**）。
high 级漏洞清除，剩余 3 项（2 critical + 1 moderate）都需要升级 `vitest`。

### 3.3 第二步：`vitest` 安全升级（**有官方依据，不是猜测**）

查证两个 advisory 的官方修复版本：

| advisory | 影响范围 | **首个已修复版本** |
| --- | --- | --- |
| [GHSA-5gmw-xhrv-c9v3](https://github.com/advisories/GHSA-5gmw-xhrv-c9v3)（tinypool 原型链污染 → RCE，CVSS v4 **9.5**） | `tinypool <= 2.1.0` | `tinypool 2.1.1` |
| [GHSA-85c8-ppgw-ccpr](https://github.com/advisories/GHSA-85c8-ppgw-ccpr)（tinypool `run()` 原型链 gadget → RCE，CVSS v4 9.5） | `tinypool < 2.1.2` | `tinypool 2.1.2` |
| [GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9)（`@vitest/mocker` 路径穿越/任意文件读取） | `@vitest/mocker >= 2.1.0, < 4.1.11`；`vitest >= 2.1.0, < 4.1.11` | **`vitest 4.1.11`**（明确写：3.x 不再维护、不会修） |

**决策过程（为什么必须升 major）**：

- advisory 明确说 "Older majors (2.1.x, 3.x) are not maintained and are not planned to receive the fix"，
  所以**不存在**"留在 3.2.7 只升 tinypool"的官方修复路径；
- `vitest@3.2.7` 依赖 `tinypool@^1.1.1`，`@vitest/mocker` 是它自己的依赖（无法用 overrides 安全替换）；
- 因此选择 **`vitest@^4.1.11`**（不是 5.x：4.1.11 已是首个含全部修复的版本，且升级幅度最小）。

**升级前的前置条件核验**：

| 前提 | 本项目 | 是否满足 |
| --- | --- | --- |
| Vite ≥ 6.0.0 | `vite@8.3.1` | ✅ |
| Node ≥ 20.0.0 | `node v24.19.0` | ✅ |

**升级风险的代码级排查**（v3→v4 的破坏性变更里唯一可能影响本项目的是 mock 行为）：

- v4 改变了 `vi.spyOn` / `restoreAllMocks` / automock 的语义；
- 本项目测试里 **`vi.spyOn` 使用次数 = 0**，只用 `vi.fn()` 与 `vi.stubGlobal('fetch', …)`；
- 其余变更（coverage 重构、`workspace`→`projects`、browser provider、pool 重构）
  本项目**均未使用**（单项目配置、无 coverage、无 browser mode）。

**升级结果**：

| 项 | 结果 |
| --- | --- |
| `vitest` | `3.2.7 → 4.1.11`（`frontend/package.json` 1 行 + lockfile） |
| `@vitest/mocker` | `4.1.11`（vitest 内嵌，随主包升级） |
| `tinypool` | **不再出现在依赖树里**（v4 已改用 Vite Module Runner / Vite 内建 worker 池） |
| `source-map-js` | `1.2.2` |
| **`npm audit`** | **`{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0}`** |
| `npx vitest run` | **313 passed / 0 failed**（且时长由 ~6.3s 降到 ~4.1s） |
| `npx vue-tsc --noEmit` | exit 0 |
| `npm run build` | exit 0（产物大小与升级前一致：JS 249.57 kB） |
| 浏览器 E2E | **24 passed / 0 failed** |

> ✅ 因此**保留了**这次升级，未回滚，也**没有**出现"需要大规模改写测试体系"的情况。

### 3.4 唯一被更新的旧断言（说明为什么必须改）

`frontend/tests/ai-planning-drawer.spec.ts` 原来断言：

```ts
expect(wrapper.find('[data-testid="ai-drawer-status"]').text()).toContain('enabled=true')
```

这是**依赖旧文案**的定位假设：`enabled=true` 现在被移进了折叠的技术详情。
新断言改为同时锁定**两件事**：

1. 头部摘要说的是人话（含"演示模式"，且**不含** `api_key_configured`）；
2. **原始字段一个都没丢**：技术详情默认折叠，展开后 `enabled=true`、
   `live_model_available=false`、`api_key_configured=` 都必须在。

⇒ 这不是"为了测试通过而放松断言"，而是把断言从"文案长什么样"改成"信息有没有丢"。

### 3.5 CI 安全

**现状**：仓库**此前没有任何 CI**（`.github/` 不存在）。

本轮新增（**可审查的最小方案**）：

- `.github/workflows/ci.yml`：三个 Job（后端 pytest / 前端测试+类型+构建 / 依赖审计）；
- `docs/final_upgrade/CI_PLAN.md`：设计说明与运行记录。

安全边界（逐条对应任务书要求）：

| 要求 | 落实 |
| --- | --- |
| 不在不可信 PR 环境执行写权限任务 | 顶层 `permissions: contents: read` |
| 不向 Fork PR 暴露密钥 | 工作流里**零** `secrets.*` 引用；`AI_PLANNING_ENABLED=false` |
| 不允许扫描器自动改依赖 | 只跑 `npm audit --audit-level=high`；⛔ 工作流里**没有** `audit fix` |
| 不未经审批启用高权限自动合并 | ⛔ 无 auto-merge、无 `gh pr merge`、无部署步骤 |

#### 3.5.1 第 1 次真实运行：后端 Job 失败（已修复）

| 项 | 值 |
| --- | --- |
| Run | [#37948975531](https://github.com/Sunset-Sunrise-Sun/AI-education/actions/runs/37948975531)（提交 `af6a5cb`） |
| Frontend tests / typecheck / build | ✅ SUCCESS |
| Dependency audit（只报告） | ✅ SUCCESS |
| Backend pytest | ❌ FAILURE |

失败原因（Job 日志逐行确认）是**依赖声明缺失**，不是测试问题：

```text
ERROR collecting tests/test_curriculum_elective_group.py
    from docx import Document
E   ModuleNotFoundError: No module named 'docx'
ERROR collecting tests/test_curriculum_positional_docx.py
E   ModuleNotFoundError: No module named 'docx'
!!! Interrupted: 2 errors during collection !!!
```

`python-docx` 只存在于我的开发机上、**从未写进 `requirements.txt`**，
所以 Windows 本地一直绿、干净的 Linux Runner 一装就缺。

**判定为测试依赖**（逐处核对后的依据）：

- `app/curriculum/docx_reader.py` **不 import `docx`**：它把 .docx 当 OOXML 包，
  用标准库 `zipfile` + `xml.etree.ElementTree` 直接读 `word/document.xml`
  （这也是它能实现"有界读取 / 拒绝重复成员 / 拒绝路径穿越"的原因）；
  生产代码里其余 `docx` 出现都只是**字段名/变量名**（如 `record["docx"]`）。
- 只有 2 个测试文件 `from docx import Document`，用途是**构造**测试用 .docx：
  `tests/test_curriculum_elective_group.py`、`tests/test_curriculum_positional_docx.py`。

**修复方式**：把 `python-docx>=1.1` 加进 `backend/requirements.txt` 的**测试依赖段**
（并写明上述判定理由），**而不是**新建 `requirements-dev.txt` ——
因为 README / RUNBOOK / CI 三处既有安装命令都是
`python -m pip install -r requirements.txt`，拆文件会让这三处约定同时失效。
⛔ 未跳过这两个测试文件，⛔ 未加 `continue-on-error`，⛔ 未加 `xfail`。

**修复前先在本地自证**：新建**空白虚拟环境**，只装 `requirements.txt`，再跑全量 pytest：

```text
pip install -r requirements.txt → exit 0；python-docx 1.2.0 已随之上装
pytest totals: 3188 passed / 2 failed / 2 skipped  ← 与开发机基线完全一致
```

⇒ 说明"只装 `requirements.txt`"已足够收集并运行**全部**测试。

#### 3.5.2 第 2 次运行（修复后）：三个 Job 全部通过

| 项 | 值 |
| --- | --- |
| Run | [#38006322656](https://github.com/Sunset-Sunrise-Sun/AI-education/actions/runs/38006322656) |
| 提交 | **`decc84b`** |
| Backend pytest | ✅ success（Job `114075845916`） |
| Frontend tests / typecheck / build | ✅ success（Job `114075845865`） |
| Dependency audit（只报告） | ✅ success（Job `114075845748`） |

后端 Job 日志确认 `Collecting python-docx>=1.1 (from -r requirements.txt (line 37))`
与 `Successfully installed … python-docx-1.2.0`，pytest 跑到 100%，
日志中**没有** `ModuleNotFoundError`、**没有** `FAILED` / `short test summary` 段，
也**没有** `SKIPPED` / `xfail` / `continue-on-error`。

**如实说明**：该 Job 日志在本地读取时被**尾部截断**，我**没有取到 Linux 上的准确测试计数**
（`===== N passed =====` 不在可见片段内）；可确证的是收集成功、跑到 100%、无失败、Job 通过。
Windows + Python 3.14 上同一条命令实测 **3188 / 2 / 2**。

#### 3.5.3 仍未验证（如实声明）

| 项 | 状态 |
| --- | --- |
| Linux 上的准确测试计数 | **未取到**（日志被截断） |
| 两个 Job 的 Node 20 弃用告警 | 存在但**不影响结论**（Actions 已落到 Node 24；Job success） |

---

## 4. P1 —— 真实 DeepSeek 在线验证：**BLOCKED**

### 4.1 环境实测（只检查"是否存在"，⛔ 未打印任何值）

| 变量 | 进程 | 用户级 | 机器级 |
| --- | --- | --- | --- |
| `AI_PLANNING_ENABLED` | unset | unset | unset |
| `DEEPSEEK_API_KEY` | **unset** | **unset** | **unset** |
| `DEEPSEEK_BASE_URL` | unset | unset | unset |
| `DEEPSEEK_MODEL` | unset | unset | unset |

```text
BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE
```

⛔ 未使用任何历史对话中的旧密钥；⛔ 未在仓库中加入假密钥；
⛔ 未用注入式测试替身冒充真实 DeepSeek 调用。

### 4.2 默认模型名核验（这项**已在线确认**）

`backend/.env.example` 的默认值 `DEEPSEEK_MODEL=deepseek-flash` **与供应商当前文档一致**：

- 官方 *Models & Pricing* 现在把当前模型列为 **`deepseek-flash`** 与 **`deepseek-v4-pro`**，
  并写明 "Use `deepseek-flash` as the model name"；旧名 `deepseek-v4-flash` 等仍被接受但模型已下线。
  来源：<https://api-docs.deepseek.com/quick_start/pricing>（核验日期 2026-10-09）。
- 同时明确**边界**：文档一致 ≠ 账号有权限/有余额 ≠ 在线鉴权通过。
  `GET /status` 的 `live_model_available=true` **只**表示"开关已开 + 密钥已配置"。

### 4.3 交付：可直接执行的在线验证说明

见 **`docs/final_upgrade/DEEPSEEK_LIVE_VERIFICATION.md`**，包含：

- 环境变量与**安全注入示例**（只进进程环境，不进文件/不进聊天）；
- **8 条验收标准**（含"`generator_kind` 必须是 `deepseek_live`"、
  "白名单外课程号不得出现"、"模糊意图必须 `can_confirm=false`"、
  "`/solve` 候选必须能由本地冻结 Planner 复算一致"、"失败不得虚构结果"、"任何地方不得出现密钥"）；
- **8 步最小成本流程**（最多 3–4 次模型调用，含两次失败注入）；
- **失败处理表**（401/403/429/超时/模型越权/密钥泄露 各自的处置，含"立即停止"与"按安全事件处理"）；
- 与演示口径的关系（未通过前必须保留 Mock / 测试替身标注）。

---

## 5. P1 —— 真实培养方案与教学班数据接入准备：**已完成准备，数据仍缺失**

完整指南见 **`docs/final_upgrade/REAL_DATA_READINESS.md`**。要点：

### 5.1 现状（只读代码勘查结论）

- 两个模块**代码完成且默认失败关闭**；
- 个人规划链路已通到 `MakeupTask`，Planner 注入点也已存在；
- **仓库内没有任何已核验真实数据**（全仓库 `"data_source": "real"` 的 JSON **0 条**）；
- 缺的三件东西：**① 已核验版本目录 artifact、② 真实已修记录进入请求、③ 教学班全学期验收**；
- **最大缺口**：**没有**把"真实 DOCX 培养方案 + 规则"转成 `catalog.json` 的**生产工具**
  （`plan_profiles.py` 只被测试使用）——这属**新增开发**，需人工批准。

### 5.2 交付物

| 交付 | 说明 |
| --- | --- |
| 数据缺口清单 | `REAL_DATA_READINESS.md` §1（D1–D5，逐项说明"谁提供什么"） |
| 所需字段说明 | §2：`catalog.json` 逐字段、已修记录逐字段、XLSX 逐列、Capture Bundle 逐字段 |
| 数据校验流程 | §3：目录层 → 记录层 → 快照层 → 验收层 → 读取层，逐条写清判据 |
| 接入操作指南 | §4：合成自检 → 换已核验目录 → 接入教学班 → 复跑（可直接照做） |
| 纯合成独立夹具 | §5：5 类夹具，全部带 `mock://` 标记，可被真实校验器接受又能一眼识别 |
| **到位即可执行的端到端测试** | **`backend/tests/verify_real_data_e2e.py`**（新增，已实测） |
| 已知风险 | §6：`data_source` 自述、运行时无合成/真实闸门、`plan_profiles` 硬编码、XLSX→个人规划的 `source_id` 不匹配 |

### 5.3 新增脚本已实测（合成模式）

```powershell
$env:APP_PERSONAL_CATALOG_DIR = "$env:TEMP\verify_catalog"
python -m uvicorn app.main:app --port 8000        # 另开终端
python -m tests.verify_real_data_e2e --mode synthetic --catalog-dir "$env:TEMP\verify_catalog"
```

实测输出（节选）：

```text
CLAIM LEVEL: SYNTHETIC —— 以下全部为人工构造数据，⛔ 不代表真实教务数据
⚠️  本目录的 source_id / evidence 含 mock:// 标记：人工构造数据…不得作为真实教务数据…
[1/3] ✅ 可选版本 2 个：['mock-old-2025', 'mock-target-2025']
[2/3] ✅ student-one：3 个补修任务（TGT100, TGT101, TGT201），status_counts={'satisfied': 2, 'required': 1}
      ✅ student-two：3 个补修任务（TGT100, TGT101, TGT201），status_counts={'satisfied': 1, 'required': 2}
[3/3] ⚠️  两位学生：补修任务正常，但没有规划结果（planning_skipped_code=no_course_data）
      这属于**如实失败**：教学班数据尚未接入…
```

**这正好证明了两件事**：① 目录 → 已修记录 → `MakeupTask` 这条链**真的通**；
② 教学班缺失时**如实失败**，⛔ 不会回退成固定 Case A 或伪造"已排好课"。

⚠️ 开发过程中踩到并已修正的一点：合成模式必须把目录写到**后端正在用的那个目录**
（`--catalog-dir`），否则第 1 步会因"目录里没有 `catalog.json`"而空跑。

---

## 6. P2 —— 最终演示剧本与产品验收：**已彩排，11 步全部可达**

### 6.1 彩排方式（已自动化）

新增浏览器用例 **`DMO01-demo-script-rehearsal`**，按 `DEMO_SCRIPT.md` §2 的 11 步实际走一遍，
并断言每一步"该看到的东西真的在"。它已纳入 24 项回归：

```powershell
node tools/browser-e2e/run_browser_e2e.mjs --filter=DMO01
```

### 6.2 逐步结果（真实 Edge 实测）

| 步骤 | 环节 | 实测 |
| --- | --- | --- |
| 1 | 进入项目 | ✅ 三入口全部可见可切 |
| 2 | 转专业背景 | ✅ 如实显示"没有已核验版本目录"，**缺口摘要不渲染**（⛔ 不伪造数字） |
| 3 | 补修缺口 | ✅ 任务/状态/来源标记（`规划结果来源：Mock`）齐全 |
| 4 | 当前与后续学期规划 | ✅ 阅读顺序 5 步 + 当前学期课表 |
| 5 | 课程依据与风险 | ✅ 解释面板打开，标注 **规则模板（非 AI）**，11 条条目 |
| 6 | 自然语言提出调整 | ✅ 入口 + **3 条示例** + 常驻"当前调整对象" |
| 7 | 确认硬约束 / 软偏好 | ✅ "不可协商" / "可协商" 分区正确；学分上限未被系统替用户默认 |
| 8 | 受控 Planner 求解 | ✅ 确认前 `/solve`=**0**，确认后**恰好 1 次**，`candidate_ready` |
| 9 | 对比变化与边界 | ✅ 五格齐全；候选态风险 55 字、未决事项 **317 字** |
| 10 | 二次确认采用 | ✅ 真实调用 1 次 `/adopt`，`adopted_version=1` |
| 11 | 临时范围 | ✅ 明写 `process_local_session`、**未持久化**、重启失效、不代表教务选课成功 |

### 6.3 文案与实现一致性核查

- `DEMO_SCRIPT.md` 里点名的 testid 与按键（`查看依据 / 为什么这样安排`、
  `采用候选方案（临时）`、`技术详情`）均已与代码核对一致；
- 剧本 §2 第 3 步说"在历史培养要求评估或规划结果区点查看依据"——
  实际上解释入口在**第 5 区块"解释与依据"**（阅读顺序第 ⑤ 步，风险之后），
  已在 `DEMO_SCRIPT.md` §7.4 的自检清单里补上更明确的位置提示；
- 剧本 §5「演示禁忌」与真实实现一致（⛔ 无 `exclude_course`、⛔ 无跨学期自动重排）。

### 6.4 演示时"哪一步是什么数据"（已在剧本 §7 固定）

| 屏幕上看到 | 真实来源 | 必须说的声明 |
| --- | --- | --- |
| 缺口数量/逐条判定 | 前端预览 fixture（档位 A）或后端目录（档位 B） | "仅前端预览" 或 "已核验目录" |
| 当前学期课表/教学班/偏好/规划结果 | 后端 `GET /api/v1/mock/demo` | **Mock 演示数据** |
| 解释面板 | 后端 `POST /api/v1/explanation/plan` | **规则模板（非 AI）** |
| AI 意图解析 | 后端（本次：**注入式测试替身模型**） | "测试替身模型（不是线上模型）" |
| AI 候选方案 | 后端**真实冻结 Planner** | "由确定性算法算出" |
| 采用 | 后端 `adopted_version`（进程内） | "临时、未持久化、不代表教务选课成功" |
| 真实 DeepSeek / 真实教务数据 | **尚未接入** | "NOT VERIFIED，本轮不演示" |

---

## 7. 修改文件清单

**生产代码（前端展示层，未触碰业务规则）**

| 文件 | 改动 |
| --- | --- |
| `frontend/src/components/ai/AiAdjustDrawer.vue` | 头部改为"人话摘要 + 可展开技术详情" |
| `frontend/src/components/ai/drawerCapability.ts` | **新增**纯函数（状态 → 摘要 + 技术事实） |
| `frontend/src/styles/base.css` | 新增头部/技术详情样式与手机单列规则 |
| `frontend/package.json` / `frontend/package-lock.json` | `vitest ^3.2.7 → ^4.1.11`；`source-map-js 1.2.2` |

**测试**

| 文件 | 改动 |
| --- | --- |
| `frontend/tests/ai-drawer-capability.spec.ts` | **新增** 10 项穷举测试 |
| `frontend/tests/ai-planning-drawer.spec.ts` | 更新 1 项依赖旧文案的断言 |
| `tools/browser-e2e/cases.mjs` | 新增演示彩排用例；三档响应式新增头部信息密度/技术详情断言 |
| `tools/browser-e2e/run_browser_e2e.mjs` | 接入演示彩排用例组 |
| `backend/tests/verify_real_data_e2e.py` | **新增**真实数据接入端到端验收脚本 |

**CI 与文档**

| 文件 | 改动 |
| --- | --- |
| `.github/workflows/ci.yml` | **新增**（只读权限、无 secret、审计只报告） |
| `docs/final_upgrade/CI_PLAN.md` | **新增** |
| `docs/final_upgrade/DEEPSEEK_LIVE_VERIFICATION.md` | **新增** |
| `docs/final_upgrade/REAL_DATA_READINESS.md` | **新增** |
| `docs/final_upgrade/DEMO_SCRIPT.md` | 追加 §7 彩排记录与"哪一步是什么数据" |
| `docs/final_upgrade/reports/FINAL_DELIVERY_READINESS_REPORT.md` | **新增**（本文件） |
| `docs/status/agent_frontend.md`、`docs/worklogs/agent_frontend.md` | 追加本轮记录 |

**⛔ 未改动**：`main`、`schemas/**`、`docs/interfaces/**`、`backend/app/planner/**`、
`backend/app/curriculum/**`（只读勘查）、`backend/app/course_data/**`（只读勘查）。

---

## 8. 尚未完成 / 未验证 / 需要人工确认

### 8.1 BLOCKED（缺外部输入，非技术阻塞）

| 项 | 阻塞原因 | 已提供的解锁物 |
| --- | --- | --- |
| 真实 DeepSeek 在线验证 | `BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE` | `DEEPSEEK_LIVE_VERIFICATION.md`（可直接执行） |
| 真实培养方案目录 / 已修记录 / 教学班数据 E2E | 数据未提供 | `REAL_DATA_READINESS.md` + `verify_real_data_e2e.py` |

### 8.2 NOT VERIFIED（已实现但未获外部确认）

- **CI 第 1 次运行**：前端 Job 与依赖审计 Job **已成功**；后端 Job **失败**并已修复
  （缺测试依赖 `python-docx`，见 §3.5.1）；修复提交后的新一轮结论以实际 Run 为准；
- 两项 Windows 平台差异失败在 Linux 上是否消失（预期消失；以实际 Run 为准）；
- 五个已批准校区 `openingSchoolNumber` 是否与学校当前系统一致（仅测试锁定其不被改动）；
- `planning_skipped_code="semester_not_bound"` 是否真的可达（前端有文案，未找到后端产出路径）。

### 8.3 需要人工确认

| # | 事项 | 建议 |
| --- | --- | --- |
| 1 | 是否把 `catalog.json` 生产工具（DOCX → artifact）列入开发计划 | 这是真实数据接入的**最大缺口**，属新增开发 |
| 2 | 是否把"合成数据不得进生产库"从工具层下沉为运行时不变式 | 影响 `backend/app/course_data/**`，需人工批准 |
| 3 | `verification.verified` 目前只是文件里的布尔自述 | 建议真实目录交付走人工签字并保留 `verification.evidence` |
| 4 | CI 是否作为合并门槛 | 建议先以观测模式跑一次 |
| 5 | 后端 2 项 Windows 平台差异失败 | 建议单独立 issue；⛔ 我不改其实现或测试 |

### 8.4 已知问题（非本轮引入）

- 375px 抽屉头部总高由 137px 变为 **164px**（占视口 20%）：摘要多一行 +
  新增一行"技术详情"折叠标题；仍远低于 50% 阈值，且**信息可读性显著改善**。
  若需进一步压缩，可把折叠标题并入摘要行（属 UX 微调，需人工确认）。
- 依赖漏洞虽已清零，但 `npm audit` 只是"当前时间点"的快照；
  建议把 `npm audit --audit-level=high` 留在 CI 里持续观测。

---

## 9. 结论

| 任务书要求 | 状态 |
| --- | --- |
| P0 合并后完整冒烟与回归（后端 / 前端 / 浏览器 / 无遗留进程） | ✅ **完成**（3188+2+2；313；24/24；残留 0） |
| P1 修复移动端头部信息密度 | ✅ **完成**（五档区分 + 可展开技术详情 + 穷举测试 + 三档复测） |
| P1 处理 npm 依赖安全问题 | ✅ **完成**（audit 归零；vitest 3.2.7 → 4.1.11，有官方依据与全量回归） |
| P1 CI 安全 | ✅ **已在 GitHub Actions 真实运行且三个 Job 全部通过**（Run #38006322656，提交 `decc84b`）；第 1 次后端因缺测试依赖失败已修复（见 §3.5） |
| P1 真实 DeepSeek 在线验证 | 🔴 **BLOCKED**（无新密钥）——已交付可直接执行的验证说明 + 默认模型名已在线核验 |
| P1 真实培养方案与教学班数据接入准备 | ✅ **完成准备**（缺口/字段/校验/指南/合成夹具/一键验收脚本，脚本已实测） |
| P2 最终演示剧本与产品验收 | ✅ **完成彩排**（11 步全通，已自动化回归） |

**⛔ 未自动合并；Draft PR 目标为 `feature/final-upgrade`。**
