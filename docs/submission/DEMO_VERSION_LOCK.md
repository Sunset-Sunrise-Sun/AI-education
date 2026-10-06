# 比赛演示版本锁定（DEMO VERSION LOCK）

> 目的：让**录屏 / 截图 / 现场演示**对应的版本可复现。
> ⛔ 本文件不声称任何"真实学校 E2E"结论：正式 Real E2E 证据等级仍是 **LEVEL 0**。
> 录制与截图使用的是**模式 1（Mock 回放）**，它**不执行** Curriculum / Planner 业务计算。

---

## 1. 版本标识

| 项 | 值 |
|---|---|
| 仓库 | `Sunset-Sunrise-Sun/AI-education` |
| 演示版本分支 | `feature/competition-demo-closure`（PR #51） |
| **演示版本 commit（锁定）** | `51eaccb1f9b23f9226760eab323028ed85d01b0a` |
| 该 commit 的父提交 | `248f835e230e3a6654ba6a8f7be446896dfd5ec5`（文字/来源闭环：B1/B2/B3 与 AI/RAG/Planner/等级口径） |
| 该 commit 的标题 | `fix(demo): remove school-system acquisition claim from the CourseOffering section subtitle`（**单个用户可见字符串**：第 2 区副标题不再声称"从教务系统中抓取"） |
| 前序锁定值 | `248f835…`（截图 `01/04/05/06` 采集自该版本；两版之间只差上述一行文案，画面仅 02 / 03 受影响） |
| commit 时间 | 2026-10-07 01:15 +0800 |
| 本材料分支 | `docs/opc-final-submission-pack`：**基线即 `51eaccb…`**，相对演示分支的 diff **只包含 `docs/submission/**`**（⛔ 不含任何前端 / 后端改动，因为该文案修复已包含在演示分支自身） |
| 与 `origin/main` 的关系 | 3 ahead / 0 behind（⛔ 未合并） |

> ⚠️ 录制前后请用 `git rev-parse HEAD` 复核：演示分支 HEAD 应为 `51eaccb…`（或本材料分支在其之上只多 `docs/`），
> 否则截图/视频与本文档的记录不再对应，需要重新锁定。
>
> ✅ **评委向文案核对**：第 2 区副标题现为
> 「Course Data 模块负责教学班数据的标准化与结构化；当前比赛演示使用明确标识的 Synthetic 教学班快照（未连接任何实时教务系统）。支持多段排课及中性无排课数据状态（DG-01 / DG-07D）。」——
> 不再出现任何"从教务系统抓取 / 已对接 / 实时"的肯定式表述。

---

## 2. 运行环境（录制与截图实测）

| 组件 | 版本 |
|---|---|
| 操作系统 | Windows（本地 127.0.0.1 联调；⛔ 不访问校园网） |
| Python | 3.14.7 |
| FastAPI | 0.142.2 |
| Pydantic | 2.13.5 |
| Uvicorn | 0.54.0 |
| httpx | 0.28.1 |
| pytest | 9.1.1 |
| Node.js | v24.9.0 |
| npm | 11.17.0 |
| 前端框架 | Vue `^3.5.43`（`frontend/package.json` version `0.1.0`） |
| 构建工具 | Vite `^8.3.1` |
| 测试运行器 | Vitest `^3.2.7` |
| TypeScript | `^5.9.3` |
| 浏览器（截图） | Microsoft Edge（headless，`--headless=new`，`--force-device-scale-factor=1`） |

---

## 3. 数据与夹具（fixture）身份

### 3.1 模式 1 的 Mock 回放数据（提交在仓库内，录制时实际使用）

| 文件 | SHA-256（内容摘要） | 字节数 |
|---|---|---|
| `mock_data/makeup_tasks.json` | `803cae905eff5a4a217b15622769872e8c83dfb518173a23b6ff574cbdd23dc3` | 2131 |
| `mock_data/course_offerings.json` | `55ac59fb8f0ce01c931fe67b39929484fb634cdae687090e59cba03ceb67c11c` | 5269 |
| `mock_data/preference.json` | `be8b94199a4057f6818c803a4ce511c3fa1556d3872ac3ef24e7d9e2d6c3b4c2` | 331 |
| `mock_data/plan_result.json` | `b567ac766ed3e22880cccd93aa69cb011020a9cf0129f0c02915c9d7adf9bf69` | 2234 |

> 校验命令（PowerShell）：
> `Get-ChildItem mock_data -File -Filter *.json | ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name }`

### 3.2 教学班演示快照（Synthetic，模式 2 才需要；本轮录制**未使用**）

- 生成器：`tools/generate_competition_demo_snapshot.py`（确定性；同一输入 ⇒ 逐字节相同的五个 campus bundle）；
- 生成后每个 bundle 的 SHA-256 与行数会写进 `DEMO_SNAPSHOT_DISCLOSURE.json`（`synthetic: true`，含逐字标签
  「教学班数据：演示快照（Synthetic）」），并经**既有**两步验收链路写入本地 SQLite；
- ⛔ 该快照**不是**真实学校供给；通过验收只证明完整性与一致性；
- ⛔ 本轮录屏/截图使用模式 1，**没有**生成、也没有使用该快照，因此其摘要不在此固定（避免把本地产物当成版本内容）。

### 3.3 Case A 真实输入

- ⛔ 不在 Git 中（操作者受控本地输入）；**本轮录制未使用**；
- 其真实学校来源须由绑定 artifact 字节的批准 provenance 证明（⛔ `data_source=real` 字段本身不是证明）。

---

## 4. 精确启动命令（录制/截图实测路径）

### 4.1 模式 1（默认；截图与录屏使用）

```powershell
# 终端 A：后端（工作目录 backend/）
cd backend
python -m pip install -r requirements.txt          # 首次
$env:PYTHONUTF8="1"
python -m uvicorn app.main:app --port 8000
```

```powershell
# 终端 B：前端 —— 为得到**无开发调试面板**的干净画面，使用生产构建 + 预览服务器
cd frontend
npm install                                          # 首次
npm run build                                        # 产出 dist/
npm run preview -- --port 4173                       # Vite preview，已配置 /api 代理到 8000
```

- 录屏/截图地址：**`http://127.0.0.1:4173/`**
- （开发联调地址 `http://127.0.0.1:5173/` 会渲染开发专用调试面板，⛔ 不用于录制。）
- 浏览器缩放 **100%**，窗口 **1920×1080**（>视口高度时页面正常滚动）。

### 4.2 启动成功判据

```powershell
curl.exe -s http://127.0.0.1:8000/health
# 期望：{"status":"ok","service":"integration-backend","version":"0.1.0","data_source":"mock"}

curl.exe -i -s http://127.0.0.1:4173/api/v1/mock/demo | Select-String "HTTP/|X-Data-Source"
# 期望：HTTP/1.1 200 且包含 X-Data-Source: mock（证明前端 → 预览代理 → 后端 链路通）

curl.exe -i -s -X POST http://127.0.0.1:8000/api/v1/plan -H "Content-Type: application/json" -d "{\"semester\":\"2026-1\",\"current_schedule\":[],\"preference\":{}}"
# 期望：503 real_pipeline_not_configured（模式 1 的**预期** fail-closed，且**不**回退到 Mock）
```

---

## 5. 演示模式（录制采用）

| 项 | 值 |
|---|---|
| 模式 | **模式 1（演示回放 / Mock replay）** |
| 数据通道 | `GET /api/v1/mock/demo`（读取 §3.1 四个已提交 JSON，经 `/schemas/*.schema.json` 校验） |
| 是否执行 Curriculum / Planner | ⛔ **不执行**（不调用 `CurriculumCaseProvider` / `RestrictedPlannerProvider`） |
| `changes` / `risks` 的性质 | **人工构造的演示样例**（预置在 `mock_data/plan_result.json` 中），⛔ 不是本次现场求解结果 |
| 前端开关 | `VITE_PLAN_API_ENABLED` 未设置 ⇒ Real 提交按钮**不可用**（预期默认） |
| 环境变量 | 不需要任何 `APP_*` 变量 |

---

## 6. 溯源声明（逐字，随录屏/截图材料一并使用）

> 由于学校教务系统北校园开课查询存在稳定的深分页异常，当前比赛版本的教学班演示使用经过明确标识的 Synthetic 快照。系统的培养方案解析、补修判定、约束规划、Path Repair、风险解释与前后端运行链路仍按正式架构执行。

界面上的三处披露（截图中可见）：

1. 页面顶部横幅：**当前展示的是 Mock 演示通道数据（人工虚构），不是真实教务在线数据。**
2. 教学班区块：**教学班数据：演示快照（Synthetic）** + 「当前为演示数据；Mock模式回放预置结果，计算模式执行实际代码，输入来源需逐项核验。」
3. 规划结果区块：`基础演示数据：Mock · 规划结果：Mock`，并注明「属回放预置结果（未执行本次 Planner 求解）」；页脚给出实现边界（固定工具编排原型；未接入 LLM / RAG / GraphRAG）。

⛔ 录制材料不得出现：真实学校数据认证、已连接教务系统、全局最优、自动选课/换班、偏好全部生效、已接入大模型、Real E2E 完成、LEVEL2/LEVEL3 达成。

**等级表述统一口径（避免各材料互相矛盾）**：

- 正式 Real E2E 证据等级 = **LEVEL 0**；
- 仅可表述为「**具备 LEVEL 1（synthetic）wiring capability**」（合成产物可跑通装配），
  ⛔ **不得**表述为「已达成 LEVEL 1 / LEVEL 2 / LEVEL 3」。

**术语统一口径（教学班供给）**：

- 模式 1 中第 2 区展示的对象来自 `mock_data/course_offerings.json`（**Mock 回放通道**）；
- 同时界面按既定口径标注「**教学班数据：演示快照（Synthetic）**」；
- 两者指同一份**人工构造的演示供给**，均**不是**真实学校开课数据 —— ⛔ 不得把二者对立成"一个是 Mock、一个是真实"。

⚠️ **官方规则尚未核实项（影响本材料资格判断）**：`docs/submission/OFFICIAL_RULE_CHECK.md` 已核实通用材料与视频要求，
但**本赛道细则 / 是否要求 AI 模型真实运行 / 是否必须现场演示**仍未从权威来源确认；
本材料据实声明「未接入 LLM / RAG / GraphRAG」，⛔ 不得为迎合可能的规则而把未接入的能力写成已接入。

---

## 7. 复现步骤（第三方按此可得到同样的画面）

1. `git fetch origin` → `git switch --detach 51eaccb1f9b23f9226760eab323028ed85d01b0a`（或本材料分支，其相对演示分支只多 `docs/`）；
2. 按 §4.1 启动后端与前端预览；
3. 按 §4.2 三条命令确认成功判据；
4. 打开 `http://127.0.0.1:4173/`，页面应显示：Mock 横幅、8 场景演示路线、五个区块均非空、教学班区块带 Synthetic 披露；
5. 截图取景与说明见 `docs/submission/SCREENSHOT_INDEX.md`；截图文件本身见 `docs/submission/assets/`。

⚠️ 若第 4 步缺少 Synthetic 披露或出现「后端接口连接异常」，按 `docs/demo/DEMO_RECOVERY.md` 处理，
⛔ 不得用 Mock 画面冒充"现场计算"，也不得口头更正为"真实数据"。

---

## 8. 本轮实测证据（记录时间、命令与结果）

> 下表是**实测**，用于避免"证据数字只出现在幻灯片里"。执行时间：2026-10-07（Asia/Shanghai，本地一次性收尾）。

| 门禁 | 精确命令 | 实测结果 | 备注 |
|---|---|---|---|
| 后端全量 | `cd backend && python -m pytest -o addopts="" -q` | **2987 passed / 2 failed / 2 skipped**（约 52 s） | 2 个失败为**既有 Windows 平台项**：`test_curriculum_docx_reader.py::...[word\DEMO-PRIVATE-PART]`、`test_curriculum_json_reader.py::...[bad\x00path]`；⛔ 未修、⛔ 未 skip、与本次改动无关。（`docs/data/SECOND_PASS_INTEGRATION_AUDIT.md` 中的 2853 是更早快照，不是本版本数字。） |
| 前端单测 | `cd frontend && npm run test` | **142 passed / 10 files**（约 4 s） | 含披露测试 `tests/demo-snapshot-disclosure.spec.ts`（8 条） |
| 前端类型 | `npm run typecheck` | exit 0 | `vue-tsc --noEmit` |
| 前端构建 | `npm run build` | exit 0（46 modules） | 产出 `frontend/dist/`（不入库） |
| 启动冒烟（模式 1） | `GET /health`、`GET /api/v1/mock/demo`、`GET /`、`POST /api/v1/plan` | 200 / 200（`X-Data-Source: mock`）/ 200 / **503 `real_pipeline_not_configured`** | 503 是模式 1 的**预期** fail-closed；⛔ 无 Mock 回退 |
| 路线彩排 | `rehearse_opc_route.py`（本地驱动） | **四次**彩排：文案修复前 7 554 ms / 7 297 ms；修复后（`51eaccb…`）**7 993 ms / 7 386 ms**，两次均 6/6 段非空、8/8 锚点可解析、`POST /api/v1/plan` = 503 | 详见 `docs/submission/REHEARSAL_LOG.md`；⛔ 无真人出声 |
| 截图采集 | Edge headless（`--headless=new`，`--force-device-scale-factor=1`） | 6 张 PNG：`01` 1600×1150、`02` 1600×1200（**已按新 HEAD 重拍**）、`03` 1600×2000（**已按新 HEAD 重拍**）、`04` 1600×1400、`05` 1600×1250、`06` 1600×900 | **截图取景窗口宽 1600**（按区块自适应高度）；**录屏**建议窗口 1920×1080（见 §4.1）——两者用途不同，不是同一参数 |
| 隐私/密钥扫描 | 只读扫描 `docs/submission/**` 文本 + PNG 元数据 | 无凭据 / 无本地路径 / 无用户名；PNG 元数据为空 | 文本中"学号 / 身份证"仅出现在 ⛔ 禁止性说明里 |
| 文案红线审计 | `audit_demo_copy.py`（本地） | 用户可见面 **0 命中**；文档面命中全部处于 ⛔ 反面语境；越界说法 48 处命中、**非反面语境 0** | 修复后复跑，结果 PASS |

---

## 9. 文案阻塞状态（修复后）

1. **[已修复]** 第 2 区副标题的肯定式表述（原「Course Data 模块**从教务系统中抓取**并标准化的目标学期开课清单…」）：
   已在 `feature/competition-demo-closure` HEAD `51eaccb1f9b23f9226760eab323028ed85d01b0a` 替换为
   「Course Data 模块负责教学班数据的标准化与结构化；当前比赛演示使用明确标识的 Synthetic 教学班快照（未连接任何实时教务系统）。支持多段排课及中性无排课数据状态（DG-01 / DG-07D）。」，
   `02` / `03` 已按新 HEAD 重拍；`frontend/src/**` 中已无「抓取 / 已连接教务 / 实时教务」表述。
2. **[P1，未改]** `docs/demo/COMPETITION_DEMO_SCRIPT.md` 的页面导航名与实际界面不一致（真实为
   「0. 用户输入 / 1. 培养要求评估 / 2. 开课教学班 / 3. 用户偏好 / 4. 重构方案与求解」），
   且该文件中有肯定式"调班修复"字样残留，建议一并按 README 权威口径统一。
3. **[P1] 官方规则未核实项**：是否要求 AI 模型真实运行 / 是否必须现场演示 / 本赛道细则——
   见 `docs/submission/OFFICIAL_RULE_CHECK.md` 的"未核实项"。

⛔ 以上均为**文字/展示**问题：不需要改动 Planner、Provider、runtime、Course Data 或任何 Schema。
