# 学航·转衔

**面向高校转专业学生的 AI 学业路径重构 Agent 系统**（比赛演示参考场景：中山大学 Case A —— 2025 级 遥感科学与技术 → 网络空间安全）。

> 本项目是参赛交付版本。演示数据与真实受控输入严格分开，页面与文档都会明确标注数据来源；
> 系统**不代替学校完成选课或注册**，最终认定与执行始终由人工与学校正式渠道完成。

---

## 1. 项目简介

「学航·转衔」把学生转专业后面对的三件事连成一条可解释的链路：**缺什么（培养方案差异与补修判定）→ 现实里有什么（教学班供给）→ 怎么排进去（约束求解与 Path Repair）**，并把每一步的结论、风险与未决事项如实呈现给使用者。

面向对象：**高校转专业（转衔）学生**，以及为其提供学业指导的辅导员 / 教务人员 / 学院负责人。

核心原则（全项目通用）：

> AI 负责理解、解析、协调和解释；规则负责确定性判断；算法负责约束求解；人负责正式规则、权限边界和最终确认。

---

## 2. 问题与目标用户

### 痛点（不夸大）

- **培养方案差异难以自查**：转入新专业后，原专业已修课程与新专业培养要求的对应关系分散在文档与条款里，学生很难自己判断"哪几门已经满足、哪几门还需要补"。
- **补修判定涉及正式规则**：课程是否等价、能否替代，属于学校正式规则与审批范围，需要人工确认；学生自行推测容易出错。
- **供给与课表约束叠加**：即使确定了要补哪些课，还要面对一个学期内多门课的时间、节次、周次与校区约束，需要人工反复试排。
- **结论不易解释**：即使排出了一个方案，学生往往说不清"为什么这样排""哪里还有风险""哪些地方必须找老师确认"。

### 目标用户

| 角色 | 期望得到什么 |
|---|---|
| 转专业学生 | 一份看得懂、可对照检查、明确标注风险与待确认项的补修路径草案 |
| 辅导员 / 教务人员 | 一眼看清差异判定依据、风险点与需要人工介入的位置 |
| 学院负责人 / 评委 | 数据来源、判定责任主体与系统边界是否清晰、可复核 |

### 明确不做（本版本边界）

- 不代替学生执行选课 / 注册；
- 不代替学校做正式课程认定、学分认定与政策解释；
- 不做通用四年选课、延毕概率预测（MVP 之外）。

---

## 3. 核心能力

| 能力 | 说明 | 责任模块 |
|---|---|---|
| **培养方案解析与差异（Curriculum Diff）** | 解析原 / 新专业培养方案与已修课程记录，给出新旧方案差异与课程匹配建议 | Curriculum |
| **历史培养要求评估 / 补修判定** | 逐条评估目标培养方案要求，输出 `MakeupTask`（状态含 `required` / `possibly_equivalent` / `manual_confirmation` / `satisfied`）；先修关系由 `prerequisites[]` 承载 | Curriculum |
| **教学班供给** | 按学期提供结构化 `CourseOffering`（课程号、教学班号、教师、容量、多段排课 `meetings[]`） | Course Data |
| **偏好约束** | 把学生输入整理为 `Preference`：学分上限、避免跨校区、回避时段、意向课程 | Agent / Frontend |
| **冲突识别与 Path Repair** | 基于全部 `Meeting` 做时间 / 节次 / 周次冲突检测，搜索替代教学班并给出变更前后对照（`changes`） | Planner |
| **风险解释** | 输出 `risks[]`（`low` / `medium` / `high` + 原因），说明方案中哪些条件尚未完全认证 | Planner → Frontend |
| **人工确认模型** | 涉及课程等价、替代审批、学院特殊政策、培养方案歧义条款的结论一律标记为待人工确认（`unresolved[].type = manual_confirmation`），系统不自动下正式结论 | 全链路 |

三条贯穿设计的安全约束：

1. **冲突状态三态**：`CONFLICT > UNKNOWN > CLEAR`。排课信息未知时，结论只能表述为"与当前课表中已知时间段未发现冲突"，整体状态仍是未知，**不会**被写成无冲突。
2. **UNKNOWN ≠ INFEASIBLE**：数据不足只表示"当前证据不足以证明无解"，不构成无解证明。
3. **诚实失败**：任一前置条件不满足时系统明确拒绝（fail closed），**不会**用演示数据顶替真实结果。

---

## 4. 系统架构

四层结构，自上而下：

```text
前端 Vue 3 + Vite 单页应用（输入区 + 展示区块）
        ↓  HTTP
后端 FastAPI（POST /api/v1/plan；GET /api/v1/mock/demo；GET /health）
        ↓
Agent / Orchestration：PlanningOrchestrator（只编排，不做业务算法）
        ├── CurriculumProvider    培养方案解析 / 差异 / 补修判定 → MakeupTask[]
        ├── CourseDataProvider    整学期教学班供给 → CourseOffering[]
        └── PlannerProvider       受限确定性求解 + Path Repair → PlanResult
        ↓
PlanResult（status / selected_classes / changes / risks / unresolved / objective_summary）
        ↓
前端展示（培养要求评估 / 教学班 / 偏好 / 规划结果 / 来源声明）→ 人工确认回路
```

- **Orchestrator 只做三件事**：取 `MakeupTask[]`、取该学期 `CourseOffering[]`、把两者连同 `current_schedule` 与 `Preference` 交给 Planner 并**原样**返回 `PlanResult`；它不判断缺什么课、不检测冲突、不选班、不改写结果。
- **公共契约**只来自 `schemas/*.schema.json` 与 `docs/interfaces/*.md`，模块之间不依赖彼此内部实现。

完整分层图（含真实执行链路 / 演示快照 / Mock 回放通道的视觉区分、Provider 输入输出契约要点、fail-closed 语义、模式 1 与模式 2 对照表）见：

> **[`docs/architecture/COMPETITION_ARCHITECTURE.md`](docs/architecture/COMPETITION_ARCHITECTURE.md)**

---

## 5. 数据来源与真实性声明

### 5.1 三段数据事实（必须分开表述）

| 数据面 | 本版本的准确表述 |
|---|---|
| **培养方案（Case A）与业务语义** | Curriculum Diff、MakeupTask、补修判定、Planner 受限确定性求解、Path Repair、风险解释与人工确认模型，**按正式架构执行**；在模式 2 下走真实链路 |
| **教学班 `CourseOffering`** | 比赛演示中使用**明确标识的 Synthetic 演示快照** |
| **`mock_data/*.json` 演化数据** | 以文件形式提交，**仅用于演示回放**，且已通过 `schemas/*.schema.json` 校验 |

⛔ 本版本**没有**连接任何实时教务系统，**不存在**"全部数据均为真实"的说法；Mock 与 Synthetic 一律按要求标注，不会被表述为真实数据。

### 5.2 关于教学班数据的既定措辞

> **教学班数据：演示快照（Synthetic）**
>
> 由于学校教务系统北校园开课查询存在稳定的深分页异常，当前比赛版本的教学班演示使用经过明确标识的 Synthetic 快照。系统的培养方案解析、补修判定、约束规划、Path Repair、风险解释与前后端运行链路仍按正式架构执行。

该措辞同样适用于相关文档与演示话术；模式 2 下前端的「教学班数据：演示快照（Synthetic）」标签是本项目在教学班来源上的**唯一披露面**，不得在其上叠加"真实教学班"的表述。

### 5.3 两种运行模式与数据来源

| | 模式 1「演示快照回放」（默认） | 模式 2「真实规划链路」 |
|---|---|---|
| 触发条件 | 不设置任何真实链路环境变量 | 5 个运行时环境变量齐全且相互一致 |
| 基础数据 | `GET /api/v1/mock/demo` | 受控 Case A manifest + 已验收整学期 Course Data SQLite |
| 规划结果 | 同样来自 Mock 聚合接口 | `POST /api/v1/plan` 走真实链路 |
| 标注 | 全部标注为演示数据 / Mock | 规划结果为 Real；教学班输入仍是 Synthetic 演示快照 |

### 5.4 fail-closed：明确拒绝，不回退

- 真实链路任一前置条件未就绪 ⇒ `POST /api/v1/plan` 返回 **`503 real_pipeline_not_configured`**；
- **不回退**到 Mock，也不用演示数据顶替真实结果；
- `X-Data-Source: mock` 响应头**只**由永久 Mock 通道（`/api/v1/mock/*`）设置；真实链路响应上不出现该头，反之真实链路也不会借用 Mock 数据。

### 5.5 Real E2E 证据等级

- 本版本的正式 Real E2E 证据等级仍是 **LEVEL 0**：**没有**真实教务登录、**没有**真实 artifact 被处理；
- 已具备的是 **LEVEL 1（synthetic）** 的 wiring capability（合成产物跑通装配），⛔ 不得据此声称 LEVEL 2 / LEVEL 3 已达成；
- 等级定义与晋升规则见 [`docs/e2e/REAL_CASE_A_ACCEPTANCE.md`](docs/e2e/REAL_CASE_A_ACCEPTANCE.md)，LEVEL 2 / LEVEL 3 的证据清单见 [`docs/e2e/REAL_E2E_EVIDENCE_PROTOCOL.md`](docs/e2e/REAL_E2E_EVIDENCE_PROTOCOL.md)。

---

## 6. 快速开始

### 模式 1：演示快照回放（默认，干净检出即可运行）

前置条件：本机已安装 Python 与 Node.js。**不需要**任何凭据、任何真实材料、任何环境变量。

```powershell
# 终端 1：后端（工作目录 backend/）
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 终端 2：前端（工作目录 frontend/）
cd frontend
npm install          # 首次
npm run dev          # Vite 默认 http://127.0.0.1:5173
```

自检三步（前端必须通过 Vite 的 dev 地址打开，⛔ 不要直接双击 `dist/index.html`）：

```powershell
curl -s http://127.0.0.1:8000/health
curl -i -s http://127.0.0.1:8000/api/v1/mock/demo   # 期望 200，且响应头含 X-Data-Source: mock
# 浏览器打开 http://127.0.0.1:5173
```

前端 Real 提交按钮默认 **disabled**（`VITE_PLAN_API_ENABLED` 未设置）。这是刻意的默认值：演示不依赖后端已装配的真实输入。前端代理目标默认 `http://127.0.0.1:8000`，可用 `VITE_PROXY_TARGET` 覆盖。

### 模式 2：真实规划链路（可选，需要操作者本机已批准的真实输入）

前置条件（全部由操作者在本机准备，**都不在 Git 中**）：

1. 一份**已批准的真实 Case A manifest**（受控真实输入，按数据边界私下交接）；
2. 一份**已验收的整学期 Course Data SQLite**（含 `full_semester` acceptance 记录）。

需要的运行时环境变量**恰好 5 个**：

| 变量 | 语义 |
|---|---|
| `APP_REAL_CASE_A_ENABLED` | `1` = 启用；未设置或 `0` = 关闭；其它取值 ⇒ `invalid_runtime_configuration` |
| `APP_CASE_A_CURRICULUM_CASE_PATH` | 真实 Case A manifest 的本地路径 |
| `APP_COURSE_DATA_SQLITE_PATH` | 本地 Course Data SQLite 库路径 |
| `APP_COURSE_DATA_SEMESTER` | 该 acceptance 绑定的学期 |
| `APP_COURSE_DATA_ACCEPTANCE_SHA256` | 整学期 acceptance 的 manifest SHA-256（64 位 hex） |

前端另需：`VITE_PLAN_API_ENABLED=true`（写入 `frontend/.env.local`），可选 `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:8000`）。

演示所用的**教学班输入**由 `tools/generate_competition_demo_snapshot.py` 确定性合成（五个 campus bundle + 披露文件，逐行带 `DEMO-` 标记），再经**既有**两步验收链路
（`tools/prepare_real_case_a_runtime.py`：草稿 inventory → 正式 acceptance）写成上面的 SQLite；
⛔ 该工具不写库、不产生 acceptance、不声称 ready，且课程号来自已批准 Case A manifest 的补修判定投影。
逐步命令见 [`docs/demo/COMPETITION_STARTUP.md`](docs/demo/COMPETITION_STARTUP.md) §2.1.1。

任一项未就绪 ⇒ `POST /api/v1/plan` 返回 `503 real_pipeline_not_configured`，**不回退** Mock。运行时装配是**逐请求重新校验**的：启动之后被改写 / 被覆盖的库不会被继续使用。

> **详细的逐步启动、检查点与故障处理**见 [`docs/demo/COMPETITION_STARTUP.md`](docs/demo/COMPETITION_STARTUP.md)。

---

## 7. 演示路径（8 个场景）

一段式概览（按演示顺序；详细话术与逐场景检查点见 [`docs/demo/COMPETITION_DEMO_SCRIPT.md`](docs/demo/COMPETITION_DEMO_SCRIPT.md)）：

1. **场景 1 · 转专业背景**：从第 0 区「用户输入」讲清输入从哪里来（目标学期 `2026-1`、原专业遥感科学与技术、目标专业网络空间安全、转入学期），并说明该区块只组织输入，不做冲突检测、不生成补修任务。
2. **场景 2 · 学业差异**：用顶部概览计数与第 1 区副标题说明"差异"如何被组织 —— 由 Curriculum 依据目标培养方案要求与已修记录逐条产出，前端只展示、不重算；具体数字以页面实际显示为准。
3. **场景 3 · 历史培养要求评估（MakeupTask）**：逐条念判定列，说明四种状态（`satisfied` / `possibly_equivalent` / `manual_confirmation` / `required`）互不等同，凡涉及课程等价与学分差额一律留待人工确认。
4. **场景 4 · 教学班供给 + 学生偏好**：在第 2 区展示按课程分组的 `CourseOffering`（多段 `meetings`、容量、`data_source`），对没有可用排课信息的教学班使用中性文案「当前数据中无排课信息」；在第 3 区展示 `Preference`。**此处一次性披露教学班数据性质**，逐字念出：「教学班数据：演示快照（Synthetic）。」以及 §5.2 的既定说明，随后不再重复致歉或追加解释。
5. **场景 5 · 冲突与风险**：展示第 4 区的 `risks[]`（等级 + 原因），说明风险由后端给出、前端不重算；排课信息缺失时坚持中性表述，不据此下可行性结论。
6. **场景 6 · Path Repair**：展示 `PlanResult.changes` 的"原教学班 → 调整为 + 调整原因"，说明替代教学班搜索来自受约束的确定性求解，不由语言模型决定，也不涉及任何选课 / 退课操作。
7. **场景 7 · 方案与建议课表**：展示 `selected_classes` 与方案状态（`可行` / `部分可确认` / `当前范围内不可行`）及求解目标说明，明确这只是**建议方案**，不代表学校已完成选课或注册。
8. **场景 8 · 人工确认模型**：收尾在第 4 区的 `unresolved[]`，逐条展示原始 `type`（`manual_confirmation` / `missing_data` / `schedule_unknown` / `selection_required`），说明这些是**边界声明**而非缺陷列表 —— 系统把最终认定交回给人。

---

## 8. 测试与质量门禁

命令均与仓库实际脚本 / 配置一致。

### 后端

```powershell
cd backend
python -m pytest
```

- 覆盖公共契约、Mock 通道、Course Data 摄取与验收、Curriculum 解析与判定、Planner 冲突与 Path Repair、Integration 编排、runtime 装配与 `POST /api/v1/plan` 契约等；
- **已知项（非本次改动引入）**：在 Windows 上有 **2 个预先存在的平台相关失败用例**，属已知项，与比赛功能无关：
  - `test_curriculum_docx_reader.py` 中关于 **ZIP 成员名里字面反斜杠**的安全断言在 Windows 路径语义下不触发；
  - 同一组用例中，**本机仓库绝对路径包含形如日期 `-1` 的片段**时，"异常文本不得包含 `-1`"类断言会被误命中。
  - 这两项在改动前的基线上同样失败，**未修、未 skip、未删除断言**；宿主为 Windows + GBK（`cp936`）时，可先以 UTF-8 模式运行以排除解码类噪声。

### 前端

```powershell
cd frontend
npm run test        # vitest run —— 单元 / 组件 / provenance 门禁测试
npm run typecheck   # vue-tsc --noEmit
npm run build       # vue-tsc --noEmit && vite build
```

前端测试重点锁定：来源标注（Mock / Real 不得混用）、Real 提交的 provenance 门禁（含 Mock 项一律阻止）、503 之后**只请求一次**且**不回退** Mock、以及 `meetings` 为空时的中性文案。

> 本 README 只记录命令与已知项；质量门禁的执行与结果判定由专门的质量门禁流程负责。

---

## 9. 安全与隐私

- **凭据不入库**：不保存教务密码，不提交 Cookie / Session / Token / API Key；`.env` 不入 Git，允许提交的 `.env.example` 不含真实值。
- **真实学生数据不入 Git**：真实培养方案、成绩单 / 已修记录、当前课表、采集产物与其摘要均按受控材料处理，**不进入 public Git**；`evidence/` 不入 Git。
- **零网络默认**：后端与工具链默认不发起任何外部网络请求；本轮不探测、不访问外部教务系统。
- **访问边界**：只处理用户正常登录后本人已有权限查看的数据；禁止绕过登录、破解验证码、越权访问、枚举未授权数据、对学校系统做大量自动请求。
- **错误信息不泄漏**：诊断码与错误响应不包含本地绝对路径、配置取值或输入内容；工具链的错误类别是机器可读字段，**不解析错误文本、不外泄原始行**。
- **演示数据已脱敏 / 已虚构**：`mock_data/` 下全部内容为人工构造，课程号、教学班号、教师、课程名均为虚构，仅用于演示可读性。
- **前端不越界**：前端只做发请求、按后端枚举展示、对失败诚实报错；不在本地编造替代数据，也不重算 `PlanResult`。

---

## 10. 已知限制与未决事项

1. **教学班数据是 Synthetic 演示快照**：比赛版本的教学班输入为明确标识的演示快照，不是实时教务数据（原因见 §5.2）。
2. **OPEN ITEM：`data_source` 标记**：Course Data 代码会把已验收 Course Data 行的 `data_source` 置为 `real`；该标记表达的是"真实来源等级"，**不是**"这份数据已被证明来自受信采集"。因此模式 2 下前端显示的「教学班数据：演示快照（Synthetic）」标签是**唯一披露面**，此问题仍有待架构裁决。
3. **北校园开课查询采集为外部系统阻塞，已挂起**：整学期 acceptance 要求五个校区齐备，因此在该外部问题解决前，**真实整学期 acceptance 尚不可产出**；当前版本不探测、不绕过该阻塞。
4. **Real E2E 证据等级 = LEVEL 0**：本轮没有真实教务登录、没有真实 artifact；已具备的是 synthetic 级 wiring capability（LEVEL 1）。
5. **未做选课 / 注册执行**：系统输出的是规划结果与解释，**不代替学生完成选课或注册**，也不代表学校已完成任何审批。
6. **先修关系的真实来源尚无证据**：现有真实培养方案样本中未发现明确的先修 / 前置课程字段，`prerequisites[]` 能否被真实数据填充目前无法确认（这不构成"学校没有先修制度"的结论）。
7. **meeting 级教师关联为已知表达缺口**：真实数据中排课段与教师存在关联，但当前公共 `Meeting` 不表达它，`teacher` 仍是教学班顶层的汇总字段。
8. **拓扑不承诺**：不保证任意输入都能得到可行方案；数据不足时系统输出部分可行或未知，而非编造结论。

---

## 11. 比赛提交物清单

| 交付物 | 路径 |
|---|---|
| 项目总览（本文件） | `README.md` |
| 架构图与 Provider 契约说明 | `docs/architecture/COMPETITION_ARCHITECTURE.md` |
| 演示脚本（8 个场景话术与检查点） | `docs/demo/COMPETITION_DEMO_SCRIPT.md` |
| 启动指南（模式 1 / 模式 2 逐步操作） | `docs/demo/COMPETITION_STARTUP.md` |
| 演示运行手册（启动顺序、检查点、应急切换） | `docs/e2e/DEMO_RUNBOOK.md` |
| Real E2E 验收定义与等级 | `docs/e2e/REAL_CASE_A_ACCEPTANCE.md` |
| Real E2E 证据协议（LEVEL 2 / LEVEL 3） | `docs/e2e/REAL_E2E_EVIDENCE_PROTOCOL.md` |
| 真实执行链与采集操作包 | `docs/e2e/REAL_DATA_EXECUTION_MAP.md` |
| 数据来源登记 / 数据闸门裁决 | `docs/data/DATA_SOURCE_REGISTRY.md`、`docs/data/DATA_GATE_DECISIONS.md` |
| 演示数据（Mock 回放） | `mock_data/makeup_tasks.json`、`mock_data/course_offerings.json`、`mock_data/preference.json`、`mock_data/plan_result.json`、`mock_data/curriculum_demo/` |
| 公共契约（唯一真源） | `schemas/course.schema.json`、`schemas/course_offering.schema.json`、`schemas/makeup_task.schema.json`、`schemas/preference.schema.json`、`schemas/plan_result.schema.json` |
| 数据工具与采集器 | `tools/generate_competition_demo_snapshot.py`（Synthetic 教学班演示快照生成）、`tools/accept_full_semester_course_data.py`、`tools/validate_course_data_artifact.py`、`tools/prepare_real_case_a_runtime.py`、`tools/sysu_course_offering_collector.js` |
| 项目协作规则与模块边界 | `AGENTS.md`、`docs/ARCHITECTURE.md`、`docs/interfaces/` |

> 恢复 / 故障处理步骤并入启动指南；`evidence/` 目录（若现场产生）**不入 Git**。

---

## 12. 目录结构

| 路径 | 说明 |
|---|---|
| `backend/` | FastAPI 后端：`/api/v1/plan` 规划编排入口、永久 Mock 通道、Course Data / Curriculum / Planner 各 Provider 与 runtime 装配 |
| `frontend/` | Vue 3 + TypeScript + Vite 单页应用：用户输入区与展示区块，只消费后端响应，不实现业务规则 |
| `schemas/` | 公共 JSON Schema，是跨模块契约的唯一真源（Course / CourseOffering / MakeupTask / Preference / PlanResult） |
| `mock_data/` | 人工构造的演示数据（Mock），仅服务永久 Mock 回放通道，已通过 `schemas/*.schema.json` 校验 |
| `tools/` | 数据工具链：整学期 acceptance、单校区校验、真实 runtime 编排、教务开课采集器（采集器当前不对外使用） |
| `docs/` | 项目文档：架构、模块接口、数据闸门与来源登记、E2E 验收、演示材料、各模块 status / worklog |

---

## 相关文档索引

- 项目协作规则与模块边界：[`AGENTS.md`](AGENTS.md)
- 系统架构（模块视角）：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 参赛架构图：[`docs/architecture/COMPETITION_ARCHITECTURE.md`](docs/architecture/COMPETITION_ARCHITECTURE.md)
- 模块接口：`docs/interfaces/curriculum.md`、`course_data.md`、`planner.md`、`integration.md`、`agent_frontend.md`
- 演示运行手册：[`docs/e2e/DEMO_RUNBOOK.md`](docs/e2e/DEMO_RUNBOOK.md)
- 后端运行说明：[`backend/README.md`](backend/README.md)
- 前端运行说明：[`frontend/README.md`](frontend/README.md)
- 演示数据说明：[`mock_data/README.md`](mock_data/README.md)
