# 跨材料对外主张一致性矩阵（FINAL CLAIM MATRIX）

> **审计对象**：仓库 `AI-education`（当前分支 `docs/opc-final-submission-pack`，演示锁定 commit **`51eaccb1f9b23f9226760eab323028ed85d01b0a`**；本材料分支基线即该 commit，diff 只含 `docs/submission/**`）的 9 份对外材料，外加 2 份只读参考件（`docs/submission/DEMO_VERSION_LOCK.md`、评审侧 `_reviewer/OPC_CROSS_PR_TRUTH_TABLE.md`）。
> **后续更新（2026-10-07 收尾）**：M1（页面文案越界）已按上述限制版本修复并重拍 02 / 03；本文件已同步标注 RESOLVED 与修复后核验结论。
> **审计方法**：逐份完整阅读并取行号；对可核实的事实另做仓库侧核对（`mock_data/*.json` 条目计数、`frontend/src/**` 实际文案、`docs/submission/assets/*.png` 抽验 5/6 张、`git status` 与 `git ls-files`）。
> **本轮未运行任何构建或测试**（按要求），也未修改除本文件以外的任何文件；未 commit、未 push。
> **行号口径**：行号来自本次实际读取；凡不确定处一律改写为小节名，不虚构行号。
> **术语基准**：真值表 §1 的五个来源等级（Actual / production implementation logic、Real school data、Synthetic、Mock / replay、Planned）与 §4 / §8 的 canonical 表述。

---

## 0. 列定义与取值口径

| 列 | 取值 | 口径 |
|---|---|---|
| `claim` | 文本 | 被审计的对外主张（族编号 F1–F18 标在单元格开头） |
| `where used` | `文件:行号` 或 小节名 | 该主张在各材料中的**实际措辞出处**（同一族拆多行以暴露措辞差异） |
| `implemented?` | YES / PARTIAL / NO / PLANNED | 指主张所描述的能力/状态在**当前代码与提交物**中是否成立：YES = 可核实成立；PARTIAL = 仅部分成立、或仅某一模式成立、或仅单点材料记录；NO = 不成立；PLANNED = 仅路线图方向 |
| `data provenance` | Mock / Synthetic / 外部本地输入 / 不适用 | 该主张所涉数据的来源类别；与"代码是否执行"是**两条独立轴**（真值表 §1） |
| `allowed?` | ALLOWED / ALLOWED-WITH-QUALIFIER / FORBIDDEN | 对照真值表与 `DEMO_VERSION_LOCK.md` §6 的允许/禁用口径判定 |
| `final wording` | 逐字文本 | 建议统一采用的标准表述（逐字给出，可直接复制） |

---

## 1. 材料存在性（逐份核对结果）

| 材料 | 状态 | 备注 |
|---|---|---|
| `README.md` | 存在（344 行） | — |
| `docs/architecture/COMPETITION_ARCHITECTURE.md` | 存在（256 行） | — |
| `docs/demo/COMPETITION_DEMO_SCRIPT.md` | 存在（227 行） | — |
| `docs/submission/OPC_FINAL_SLIDES_CONTENT.md` | 存在（274 行） | — |
| `docs/submission/OPC_FINAL_4MIN_DEMO.md` | 存在（397 行） | — |
| `docs/submission/OPC_PITCH_PACK.md` | 存在（158 行） | — |
| `docs/submission/OPC_JUDGE_QA_SHORT.md` | 存在（143 行） | — |
| `docs/submission/SCREENSHOT_INDEX.md` | 存在（81 行） | 6 张 `assets/*.png` 均已存在（115–192 KB）；本次抽验 5 张 |
| `docs/submission/DEMO_VERSION_LOCK.md`（只读参考） | 存在（152 行） | — |
| `_reviewer/OPC_CROSS_PR_TRUTH_TABLE.md`（只读参考） | 存在（158 行） | — |
| **附加材料（不在指定清单内，本次一并读取）** | 存在 | `OPC_PORTAL_INFO_TEMPLATE.md`、`OFFICIAL_RULE_CHECK.md`、`VIDEO_RECORDING_PLAN.md`、`REHEARSAL_LOG.md`、`tools/architecture_diagram.html`、`tools/shot-harness.html`、`学航转衔_OPC_答辩稿.pptx` |
| `docs/submission/FINAL_SUBMISSION_CHECKLIST.md` | **缺失（未生成）** | 被 `REHEARSAL_LOG.md:5` 引用，但仓库中不存在该文件 |

---

## 2. 主张矩阵

> 每族一张表，六列顺序与要求完全一致；同一族拆多行以显式暴露**各材料的实际措辞差异**。

### 族 F1 · AI / Agent 定位与「AI 负责理解 / 解析 / 解释」

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F1-a 定位标题：**学业路径重构原型（固定工具编排，AI 增强待接入）** | `README.md:3`「…原型（固定工具编排，AI 增强待接入）」；`COMPETITION_DEMO_SCRIPT.md:3` 同措辞；`OPC_FINAL_SLIDES_CONTENT.md:4`「逐字使用」；`OPC_FINAL_4MIN_DEMO.md:87` 品牌头；`OPC_PITCH_PACK.md:5`「唯一权威口径」；`OPC_JUDGE_QA_SHORT.md:3` 统一口径 | YES（原型与固定编排可核实） | 不适用 | ALLOWED | **学航·转衔：面向转专业学生的学业路径重构原型（固定工具编排，AI 增强待接入）。** |
| F1-b「AI 负责理解 / 解析 / 解释」——必须是**未来时态**，不得作为本次运行分工 | `README.md:21-23`「**未来**可由模型辅助理解输入…⛔ 不把"AI 负责理解 / 解析 / 解释"当作本版本已实现的功能分工」；`COMPETITION_ARCHITECTURE.md:175-176`「当前不存在生成式解释环节…（未来可由模型辅助理解输入、检索证据与生成解释）」；`COMPETITION_DEMO_SCRIPT.md:18`「**模型理解 / 检索 / 生成式解释为未来方向**…⛔ 不说"AI 正在理解 / 解析 / 解释本次演示"」；`OPC_FINAL_SLIDES_CONTENT.md:41`「本版本**没有接入大模型**，我们不会把"AI 在理解你"当作已实现的能力来讲」；`OPC_JUDGE_QA_SHORT.md:24`「产品方向上有 AI 的规划：未来由模型辅助理解输入、检索证据、生成解释」；`OPC_PITCH_PACK.md:22`「模型能力待接入」；`OPC_FINAL_4MIN_DEMO.md:281`「模型理解、检索与知识图谱是后续方向」 | NO（未实现，仅计划） | 不适用 | ALLOWED-WITH-QUALIFIER（必须保留"未来/尚未"限定） | **未来可由模型辅助理解输入、检索证据与生成解释；当前版本由结构化输入、规则和固定编排执行。** |
| F1-c 页面标题中的 "AI Agent" 只指产品方向与固定编排架构 | `README.md:9`；`OPC_JUDGE_QA_SHORT.md:24`（Q2）、`OPC_JUDGE_QA_SHORT.md:33`（Q3「严格讲，这是**固定工具编排**，不是自主决策 Agent，也不是多 Agent 协商」）；`OPC_PITCH_PACK.md:106`；`OPC_FINAL_SLIDES_CONTENT.md:242`（版式规范） | YES（页面标题与编排层均无模型调用；见 F2） | 不适用 | ALLOWED-WITH-QUALIFIER | **页面标题中的 "AI Agent" 指产品方向与固定工具编排架构，⛔ 不代表本版本已运行模型推理、检索或生成式解释。** |
| F1-d 历史措辞「AI 学业路径重构 Agent 系统」标题 | 本次 9 份材料中**未发现**；真值表 §7 曾将其列为需替换项，现行 `README.md:3` / `COMPETITION_DEMO_SCRIPT.md:3` 已是"原型（固定工具编排）" | YES（已改到位） | 不适用 | ALLOWED | 维持 F1-a 标题，不再出现"AI…Agent 系统"式标题。 |

### 族 F2 · LLM / RAG / GraphRAG 是否接入

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F2-a 未接入 / 未集成（三种措辞并存） | `README.md:8`「**LLM / RAG / GraphRAG 为后续增强方向，尚未接入**」、`README.md:293`「**未集成** LLM / RAG / GraphRAG：当前无模型调用、无检索管线」；`COMPETITION_ARCHITECTURE.md:39`「尚未接入 · 不在当前执行路径」、`COMPETITION_ARCHITECTURE.md:243`「⛔ 不声称 LLM / RAG / GraphRAG 已接入」；`COMPETITION_DEMO_SCRIPT.md:11`、`:207`「**当前未集成** LLM / RAG / GraphRAG，是固定工具编排原型」；`OPC_FINAL_SLIDES_CONTENT.md:7`、`:150`；`OPC_FINAL_4MIN_DEMO.md:15`、`:25`、`:281`；`OPC_PITCH_PACK.md:8`、`:106`、`:136`「LLM / RAG / GraphRAG 目前**不在执行路径上**」；`OPC_JUDGE_QA_SHORT.md:24`、`:42`（Q4）、`:114`（Q12）；`DEMO_VERSION_LOCK.md:139` | YES（仓库无模型调用、无检索管线，与真值表 §2 LLM/RAG/GraphRAG 行一致） | 不适用 | ALLOWED | **当前未集成 LLM、RAG 或 GraphRAG（无模型调用、无检索管线），不在当前执行路径上；模型能力为后续增强方向。** |
| F2-b 模型能力不得画进当前执行链路 | `COMPETITION_ARCHITECTURE.md:95`「点线边框 · 白色（`planned`）：当前**不在执行路径上**」；`OPC_FINAL_SLIDES_CONTENT.md:150`、`:158`「⛔ 不得把 LLM / RAG / GraphRAG 的连线接到 FastAPI、`PlanningOrchestrator`、任一 Provider 或 `PlanResult` 上」；`OPC_JUDGE_QA_SHORT.md:42` | YES（`PlanningOrchestrator` 不调用模型，`README.md:87`） | 不适用 | ALLOWED | **LLM / RAG / GraphRAG 只能放在 `AI ENHANCEMENT PLANNED` 灰框内，并标注「尚未接入 · 不在当前执行路径」。** |

### 族 F3 · 自然语言偏好解析

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F3-a 本版本**没有**自然语言偏好解析；`Preference` 来自结构化表单 | `README.md:59`「⛔ 本版本没有自然语言解析」、`README.md:234`、`README.md:293`；`COMPETITION_DEMO_SCRIPT.md:42`、`:55`、`:118`「偏好是**结构化输入**的约束条件，不是结论（本版本没有自然语言解析）」；`OPC_FINAL_SLIDES_CONTENT.md:7`、`:51`、`:105`、`:177`；`OPC_FINAL_4MIN_DEMO.md:15`、`:155`、`:190`（压缩稿亦保留）、`:281`；`OPC_PITCH_PACK.md:38`、`:107`；`OPC_JUDGE_QA_SHORT.md:114`（Q12）、`:123`（Q13） | NO（未实现） | 不适用 | ALLOWED（否定式，且是必须说出的边界） | **`Preference` 来自结构化表单（学分上限、避免跨校区、回避时段、意向课程）；本版本没有自然语言偏好解析。** |
| F3-b 措辞差异 | 9 份材料一律为否定式，用词在「没有自然语言解析」（README / 4MIN）/「无自然语言偏好解析」（SLIDES）/「没有自然语言理解」（PITCH）之间摆动 | — | — | ALLOWED | 统一为 F3-a 逐字句。 |

### 族 F4 · Planner 能力（确定性时间检查 / 受限组合可行性 / 替代候选评估）

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F4-a canonical「Planner 权威表述」 | `README.md:64-66`；`OPC_FINAL_SLIDES_CONTENT.md:11-12`（标注"逐字使用，⛔ 不改写"）、`:120`；`OPC_PITCH_PACK.md:88-90`（标注"逐字权威口径"）；`OPC_FINAL_4MIN_DEMO.md:202`（照读台词）；`OPC_JUDGE_QA_SHORT.md:51`（Q5）；附加：`OPC_PORTAL_INFO_TEMPLATE.md:228` | YES（受限确定性检查与候选评估已实现；真值表 §4 证据：`provider.py:97-104`、`185-193`） | Mock（模式 1 回放）/ 实际代码计算（模式 2） | ALLOWED | **已实现确定性时间检查、受限组合可行性检查及替代教学班候选评估。当前 Planner 保留已有班，仅在受限条件下提出新增/候选建议，并把无法确定的事项保留到 `unresolved` / 人工确认。** |
| F4-b 上句的**逐字偏差**（实际存在 2 处） | ① `OPC_JUDGE_QA_SHORT.md:51` 写作「新增**或**候选建议」（canonical 为「新增**/**候选建议」）；② `OPC_FINAL_4MIN_DEMO.md:202` 把「保留到 `unresolved` / 人工确认」改写为「保留到**未决事项（unresolved）与**人工确认」 | 语义等同，但**不是逐字** | — | ALLOWED-WITH-QUALIFIER（既称"逐字使用"就应逐字） | 统一为 F4-a 的逐字句（含 `unresolved` / 人工确认 的斜杠写法）。 |
| F4-c 更具体的限定：仅对 `required` 任务的**唯一 CLEAR 候选**提出新增建议 | `README.md:60`「仅对 `required` 任务的唯一 CLEAR 候选提出新增建议」、`README.md:236`；`COMPETITION_DEMO_SCRIPT.md:142`；`OPC_FINAL_4MIN_DEMO.md:202`；`OPC_JUDGE_QA_SHORT.md:51`「`changes` 可能只是某个 `required` 任务唯一 CLEAR 候选的新增记录」；真值表 §4 | YES | Mock / 实际代码计算 | ALLOWED | **Planner 保留已有班（返回 `selection_required`），仅对 `required` 任务的唯一 CLEAR 候选提出新增建议。** |
| F4-d 边界：不是全局优化器、不自动换班 | `README.md:60`、`:68`、`:296`；`OPC_FINAL_SLIDES_CONTENT.md:108`、`:132`；`COMPETITION_DEMO_SCRIPT.md:142`、`:146`；`OPC_FINAL_4MIN_DEMO.md:203` | YES（否定式，与代码一致） | 不适用 | ALLOWED | **它不是自动调班，也不是全局最优。** |

### 族 F5 · 全局最优 / 优化求解（CP-SAT / ILP）

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F5-a 禁用「全局最优 / 全局优化 / CP-SAT 已求解 / ILP 已求解」 | `README.md:68`；`OPC_FINAL_SLIDES_CONTENT.md:132`、`:205`（禁止表述条）；`OPC_PITCH_PACK.md:93`、`:146`（红线表）；`OPC_JUDGE_QA_SHORT.md:60`（Q6「我们没有把这个问题建模成全局优化问题，也没有用 CP-SAT 或 ILP 求解」）、`:140`；`COMPETITION_DEMO_SCRIPT.md:142`；`OPC_FINAL_4MIN_DEMO.md:21`、`:203`、`:221`；附加：`OPC_PORTAL_INFO_TEMPLATE.md:229`、`tools/architecture_diagram.html:113` | NO（未实现，且不打算如此表述） | 不适用 | ALLOWED（全部为否定式或禁用清单） | **本项目不做全局优化，不使用 CP-SAT / ILP 求解；输出的是受限候选与未决事项，不是最优解。** |
| F5-b 目标摘要里的"求解目标与策略说明"字样 | 页面实际文案（模式 1 回放）：`mock_data/plan_result.json:54`「演示用方案：…**具体演示数据，非真实求解结果**」；`OPC_FINAL_4MIN_DEMO.md:216`「方案状态徽标（如「部分可确认」）与「求解目标与策略说明」」 | PARTIAL（文案存在，语义已由 Mode 1 披露兜住） | Mock | ALLOWED-WITH-QUALIFIER | **「求解目标与策略说明」在模式 1 中属于预置样例文本，不代表本次求解；模式 2 以实际 Planner 输出为准。** |

### 族 F6 · 自动调班 / 自动换班 / 自动选课

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F6-a 禁用「自动调班 / 自动换班 / 自动选课 / 自动注册」 | `README.md:68`；`OPC_FINAL_SLIDES_CONTENT.md:108`、`:132`、`:148`、`:205`；`OPC_PITCH_PACK.md:147`、`:148`；`OPC_JUDGE_QA_SHORT.md:53`、`:140`；`COMPETITION_DEMO_SCRIPT.md:141`、`:142`、`:145`；`OPC_FINAL_4MIN_DEMO.md:21`、`:28`「**否定式**表述…是允许的，而且必须说」、`:203`、`:221`；附加：`VIDEO_RECORDING_PLAN.md:151`、`tools/architecture_diagram.html:113` | NO（未实现自动替换；`provider.py:97-104` 对已有班返回 `selection_required`） | 不适用 | ALLOWED（全部为否定式） | **保留已有班并要求人做选择；`changes` 是候选 / 新增记录，不是自动调班，也不涉及任何选课 / 退课操作。** |
| F6-b **残留肯定式术语「调班」** | `COMPETITION_DEMO_SCRIPT.md:31`「把…偏好约束、**调班修复**和风险解释串成一条链」（开场白，无"受限/候选"限定）；`COMPETITION_DEMO_SCRIPT.md:87`「四步流程引导条（… → **课表求解与调班 Path Repair**）」；页面 CSS 注释 `base.css:1341`「调班 changes 卡片」（注释，不入镜） | PARTIAL（术语残留，非能力断言） | Mock | ALLOWED-WITH-QUALIFIER | 统一为「**受限修复候选（Path Repair）**」；引用页面导航时逐字用实际文案「1. 培养要求评估 / 2. 开课教学班 / 3. 用户偏好 / 4. 重构方案与求解」。 |

### 族 F7 · 偏好是否全部执行

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F7-a 不保证全部偏好被执行（三种措辞） | `README.md:59`「⛔ 不保证全部偏好都被执行」、`README.md:296`；`COMPETITION_DEMO_SCRIPT.md:121`「⛔ 不保证全部偏好都被执行——须结合 `unresolved` 与人工确认」、`:146`；`OPC_FINAL_4MIN_DEMO.md:226`；`OPC_PITCH_PACK.md:149`「**执行口径受限**，须结合 `unresolved` 与人工确认」；`OPC_JUDGE_QA_SHORT.md:123`（Q13「**不保证**…当前并不保证全部被**满足**」） | PARTIAL（偏好原样传入 Planner，执行口径受限；真值表 §2 `Preference` 行） | Mock（模式 1）/ 外部本地输入（模式 2 表单输入） | ALLOWED（否定式 / 限定式） | **`Preference` 以结构化输入原样传入 Planner，但当前不保证全部偏好被执行（更不保证被满足）；须结合 `unresolved` 与人工确认。** |
| F7-b 措辞差异：**执行 vs 满足** | README / SLIDES / 4MIN 用"被执行"；QA Q13 用"被满足"；PITCH 用"执行口径受限" | — | — | ALLOWED | 统一为 F7-a 逐字句。 |
| F7-c 「空 `changes` 只表示没有变更记录」 | `COMPETITION_DEMO_SCRIPT.md:146`；`OPC_FINAL_4MIN_DEMO.md:226`；`OPC_JUDGE_QA_SHORT.md:123`；`README.md:61`（Mode 1 为人工样例） | YES | Mock | ALLOWED | **空 `changes` 只表示没有变更记录；不代表偏好被忽略，也不代表方案已经最优。** |

### 族 F8 · Real 数据 / 真实学校数据 / `data_source=real`

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F8-a 两轴独立：实际执行代码 ≠ 经证明的输入来源 | `README.md:114-119`（两轴表）、`:108-112`；`COMPETITION_ARCHITECTURE.md:87-103`（两条独立轴图例）；`COMPETITION_DEMO_SCRIPT.md:15`；`OPC_FINAL_SLIDES_CONTENT.md:8`、`:53-54`（创新点 2）；`OPC_JUDGE_QA_SHORT.md:69`（Q7）；`OPC_PITCH_PACK.md:52-54` | YES（机制与标注已实现） | 不适用 | ALLOWED | **「实际执行的代码」与「经证明的输入来源」是两条相互独立的轴；⛔ 不允许一个 "Real" 字样同时充当两者。** |
| F8-b `data_source=real` 只是契约 / 来源声明，不是来源证明 | `README.md:119`、`README.md:289`（OPEN ITEM「形状正确的 Synthetic 输入经 adapter 之后同样可能带上 `real` 枚举值」）；`COMPETITION_ARCHITECTURE.md:92`；`OPC_PITCH_PACK.md:98`、`:110`；`OPC_JUDGE_QA_SHORT.md:69`；`COMPETITION_DEMO_SCRIPT.md:45`；`DEMO_VERSION_LOCK.md:73` | YES（代码行为与文档一致；裁决仍开放） | Synthetic（可经形状正确的 adapter 取得 `real` 标签） | ALLOWED-WITH-QUALIFIER | **`data_source` 是契约 / 来源声明标记，不是 provenance 证明；只有绑定具体 artifact 的批准 provenance 才能支撑「真实学校输入」的表述。** |
| F8-c 是否存在肯定式「真实学校数据」断言 | 9 份材料中**未发现**；均为条件式，如 `README.md:125`「Curriculum 是否属于**真实学校输入**，须由该次 artifact 的批准 provenance 逐项证明」、`COMPETITION_DEMO_SCRIPT.md:195` | — | — | ALLOWED | **真实 Curriculum 只在具体 artifact 来源批准且与消费字节一致时声明；可复现 Synthetic E2E 的 Curriculum 也是合成输入。** |

### 族 F9 · Synthetic 教学班快照

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F9-a 教学班的既定披露口径 | `README.md:58`、`:133-139`（§5.2 逐字）、`:288`；`COMPETITION_ARCHITECTURE.md:93`、`:220`、`:225-227`、`:240`；`COMPETITION_DEMO_SCRIPT.md:42`、`:54`、`:118`（逐字）、`:195`；`OPC_FINAL_SLIDES_CONTENT.md:8`、`:75`、`:149`、`:192`、`:244`；`OPC_FINAL_4MIN_DEMO.md:13`、`:151-153`（逐字，永不可压缩）；`OPC_PITCH_PACK.md:105`；`OPC_JUDGE_QA_SHORT.md:78`（Q8 逐字）；`SCREENSHOT_INDEX.md:39`、`:42`；`DEMO_VERSION_LOCK.md:62-68`、`:131`、`:136` | YES（生成器 `tools/generate_competition_demo_snapshot.py` + 披露文件；UI 标签见 `utils/labels.ts:168`） | Synthetic | ALLOWED | **教学班数据：演示快照（Synthetic）。由于学校教务系统北校园开课查询存在稳定的深分页异常，当前比赛版本的教学班演示使用经过明确标识的 Synthetic 快照。** |
| F9-b **术语混用**：模式 1 的教学班对象实际来自 Mock 通道，却统一披露为 "Synthetic" | 口径侧：`README.md:133-139`、`COMPETITION_ARCHITECTURE.md:225-227`（"两种模式都必须保留教学班来源披露"）；事实侧：`DEMO_VERSION_LOCK.md:50-57`（§3.1 模式 1 用 `mock_data/course_offerings.json`，含 SHA-256）、`DEMO_VERSION_LOCK.md:62-68`（§3.2 Synthetic 快照**模式 2 才需要，本轮录制未使用**）、`SCREENSHOT_INDEX.md:41`（「确切来源：`mock_data/course_offerings.json`（9 个教学班）」而 caption 写 Synthetic） | PARTIAL（两条通道都非真实，但来源类别被合并表述） | Mock（模式 1）/ Synthetic（模式 2） | ALLOWED-WITH-QUALIFIER | **模式 1 的教学班对象经 Mock 回放通道提供，模式 2 为 Synthetic 生成器快照；两者皆为人工 / 程序生成，均不是真实学校供给。** |
| F9-c 「只有教学班是 Synthetic、其余全部真实」属禁用结论 | `README.md:137`、`:288`；`COMPETITION_ARCHITECTURE.md:227`、`:237`；`COMPETITION_DEMO_SCRIPT.md:118`；`OPC_PITCH_PACK.md:153`；`OPC_JUDGE_QA_SHORT.md:71`；附加：`VIDEO_RECORDING_PLAN.md:120` | YES（否定式，与真值表 §1/§5 一致） | 不适用 | ALLOWED | **⛔ 不存在"只有教学班是 Synthetic、其余全部真实"的默认结论；教学班与 Curriculum 来源须分别披露与核验。** |

### 族 F10 · Mock 回放（模式 1）与「是否现场求解」

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F10-a 模式 1 为回放，不执行上游业务计算 | `README.md:61`、`:146-147`、`:235-236`；`COMPETITION_ARCHITECTURE.md:47`、`:94`、`:215-217`；`COMPETITION_DEMO_SCRIPT.md:21`、`:41`；`OPC_FINAL_SLIDES_CONTENT.md:8`、`:133`、`:148`；`OPC_FINAL_4MIN_DEMO.md:11`、`:199`、`:215`、`:242`；`DEMO_VERSION_LOCK.md:120-123`；`SCREENSHOT_INDEX.md:22`、`:52`、`:62` | YES（`GET /api/v1/mock/demo` 返回提交的 JSON；`X-Data-Source: mock`） | Mock | ALLOWED | **模式 1 为演示回放：页面回放预置的 Mock 样例，不执行 Curriculum / Planner；`changes` / `risks` 是人工构造的演示样例，不是本次现场求解结果。** |
| F10-b 措辞差异（同向） | "回放预置结果"（README:147、SLIDES:148、4MIN:215）/「Mock 聚合接口」（README:147）/「读取仓库内已提交…`mock_data/*.json`」（DEMO_SCRIPT:41）/「不执行上游业务计算」（ARCHITECTURE:217） | — | Mock | ALLOWED | 统一采用 F10-a 逐字句。 |

### 族 F11 · 模式 2 页面来源分层（基础区 Mock vs 结果区实际代码计算）

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F11-a 只有规划结果区来自 `POST /api/v1/plan` 实际计算，页面基础区仍为 Mock | `README.md:146-149`；`COMPETITION_ARCHITECTURE.md:215-221`、`:102-103`；`OPC_FINAL_SLIDES_CONTENT.md:8`、`:148`；`OPC_FINAL_4MIN_DEMO.md:14`、`:167`、`:294`；`COMPETITION_DEMO_SCRIPT.md:52-58`；`OPC_JUDGE_QA_SHORT.md:69` | YES（后端 Provider / Planner 确实执行；UI 基础区仍走 Mock） | Mock（基础区）/ 外部本地输入 + Synthetic（模式 2 输入） | ALLOWED | **规划结果区来自 `POST /api/v1/plan` 的实际代码计算（Actual API computation）；页面基础展示区仍为 Mock 演示数据，⛔ 不得整页称为「真实」。** |
| F11-b **标注口径不精确**：「全部标注为演示数据 / Mock」与同文件要求保留 Synthetic 标签并存 | `README.md:149`「标注口径 / 全部标注为演示数据 / Mock」；`COMPETITION_ARCHITECTURE.md:221` 同句；对照 `COMPETITION_ARCHITECTURE.md:225-227`「两种模式**都必须**保留教学班来源披露…『教学班数据：演示快照（Synthetic）』」、`OPC_FINAL_4MIN_DEMO.md:12`「本模式下**第 1–4 区全部标注为 Mock 演示数据**」与 `:13`「第 2 区顶部**固定可见**：『教学班数据：演示快照（Synthetic）』」；截图事实：`SCREENSHOT_INDEX.md:59`（05 页脚）与 `02_requirement_assessment.png` 均含 Synthetic 披露条 | PARTIAL（Synthetic 属"演示数据"，但标签不只是 Mock） | Mock + Synthetic | ALLOWED-WITH-QUALIFIER | **模式 1 基础区标注为 Mock 演示数据；其中教学班区块另标「教学班数据：演示快照（Synthetic）」，两者同时保留。** |
| F11-c 模式 2 不含真实学校数据认证 | `README.md:149`、`:221`；`COMPETITION_ARCHITECTURE.md:221`；`OPC_FINAL_4MIN_DEMO.md:14`、`:231`；`OPC_FINAL_SLIDES_CONTENT.md:8` | YES | 外部本地输入（Case A manifest，来源须另证） | ALLOWED-WITH-QUALIFIER | **✅ 实际代码执行 ⛔ 不等于输入数据已获得真实学校来源认证。** |

### 族 F12 · LEVEL1 / LEVEL2 / LEVEL3 与 `ready`

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F12-a 正式 Real E2E 证据等级 = LEVEL 0 | `README.md:163`、`:291`；`COMPETITION_ARCHITECTURE.md:223`；`COMPETITION_DEMO_SCRIPT.md:16`、`:207`；`OPC_FINAL_SLIDES_CONTENT.md:9`、`:194`、`:228`；`OPC_FINAL_4MIN_DEMO.md:15`、`:282`；`OPC_PITCH_PACK.md:99`、`:109`；`OPC_JUDGE_QA_SHORT.md:114`；`SCREENSHOT_INDEX.md:69`；`DEMO_VERSION_LOCK.md:4` | YES（无真实教务登录、无真实全量 artifact） | 不适用 | ALLOWED | **本版本的正式 Real E2E 证据等级是 LEVEL 0（无真实教务登录、无真实全量 artifact）。** |
| F12-b `ready` ⛔ ≠ LEVEL2 | `README.md:157-160`、`:291`；`COMPETITION_ARCHITECTURE.md:223`；`OPC_FINAL_SLIDES_CONTENT.md:9`、`:178`、`:228`；`OPC_FINAL_4MIN_DEMO.md:24`；`OPC_PITCH_PACK.md:99`、`:112`、`:152`；`OPC_JUDGE_QA_SHORT.md:114`；`SCREENSHOT_INDEX.md:69`；`COMPETITION_DEMO_SCRIPT.md:16` | YES（readiness 工具只做 Store + Curriculum 复验） | 不适用 | ALLOWED | **`ready` 只表示运行时输入通过了 Store + Curriculum 的最终复验，⛔ 不证明真实学校来源、⛔ 不等于 LEVEL 2 / LEVEL 3。** |
| F12-c **限定语冲突**：「已具备 LEVEL 1（synthetic）wiring capability」 vs 「⛔ 不得声称已达成 LEVEL1」 | 肯定侧：`README.md:163`「已具备的是 **LEVEL 1（synthetic）** 的 wiring capability」、`OPC_FINAL_SLIDES_CONTENT.md:9`「另具备 **LEVEL 1（synthetic）** wiring capability」、`:228`、`OPC_PITCH_PACK.md:99`；否定侧：同文件 `OPC_FINAL_SLIDES_CONTENT.md:228`「⛔ 不得声称已达成 **LEVEL 1** / LEVEL 2 / LEVEL 3」、`COMPETITION_DEMO_SCRIPT.md:16`「⛔ 脚本中不得声称已达成 LEVEL1 / LEVEL2 / LEVEL3」、`OPC_FINAL_4MIN_DEMO.md:24`「⛔ …已达到 LEVEL1 / LEVEL2 / LEVEL3」 | PARTIAL（能力存在，等级未"达成"） | 不适用 | ALLOWED-WITH-QUALIFIER | **正式证据等级为 LEVEL 0；仅具备 LEVEL 1（synthetic）的 wiring capability，⛔ 不得表述为「已达成 LEVEL 1 / LEVEL 2 / LEVEL 3」。** |
| F12-d LEVEL 2 的额外要求与 `level2_eligible=false` | `README.md:162`；`OPC_PITCH_PACK.md:99`；`COMPETITION_DEMO_SCRIPT.md:207`「当前教学班供给是 Synthetic，所以 `level2_eligible` 如实为 false」；真值表 §5 | YES（与 readiness CLI 证据一致） | Synthetic | ALLOWED | **LEVEL 2 还须已批准的真实 Course Data provenance / handoff、与之精确对应的已验收整学期证据、已批准的真实 Curriculum provenance，且不得有 Synthetic 替代；教学班为 Synthetic 时 `level2_eligible` 为 false。** |

### 族 F13 · 是否连接学校教务系统 / 北校园

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F13-a 未连接任何实时教务系统、无真实教务登录 | `README.md:129`「⛔ 本版本**没有**连接任何实时教务系统」、`:278`；`COMPETITION_ARCHITECTURE.md:243`；`COMPETITION_DEMO_SCRIPT.md:195`、`:207`；`OPC_FINAL_4MIN_DEMO.md:22`、`:282`；`OPC_PITCH_PACK.md:151`；`OPC_JUDGE_QA_SHORT.md:87`（Q9「没有。当前版本没有连接任何实时教务系统，也没有真实教务登录」）；`DEMO_VERSION_LOCK.md:31` | NO（未连接） | 不适用 | ALLOWED（否定式） | **本版本没有连接任何实时教务系统，也没有真实教务登录；教学班为 Synthetic 演示快照。** |
| F13-b 北校园开课查询为外部系统阻塞、已挂起 | `README.md:290`「北校园开课查询采集为外部系统阻塞，已挂起」；`COMPETITION_ARCHITECTURE.md:233`；`COMPETITION_DEMO_SCRIPT.md:17`、`:195`；`OPC_FINAL_SLIDES_CONTENT.md:9`、`:194`、`:229`；`OPC_FINAL_4MIN_DEMO.md:15`、`:185`；`OPC_PITCH_PACK.md:108`；`OPC_JUDGE_QA_SHORT.md:87` | YES（阻塞状态如实记录；不探测、不绕过） | 不适用 | ALLOWED-WITH-QUALIFIER | **历史记录显示北校园开课查询存在稳定的深分页异常，完整真实供给仍未完成；⛔ 不探测、不绕过、不声称该部分可用。** |
| F13-c **（原越界项，已修复 ✅）** 肯定式「从教务系统中抓取」 | 修复前：页面第 2 区副标题 `frontend/src/App.vue:323`；**修复后**：`frontend/src/App.vue` 同位置改为「…负责教学班数据的标准化与结构化；当前比赛演示使用明确标识的 Synthetic 教学班快照（未连接任何实时教务系统）…」（PR #51 HEAD `51eaccb…`），02 / 03 截图已重拍 | 修复后为 **YES（口径正确）**：仅声明模块职责 + Synthetic 快照 + 未连接教务 | Mock / Synthetic | **ALLOWED** | 「未连接任何实时教务系统；教学班为 Synthetic 演示快照」（已落地） |

### 族 F14 · Path Repair 语义（候选 / 新增记录 / 人审选择）

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F14-a 保留已有班、候选择一、`changes` 可为新增 | `README.md:60`、`:236`；`COMPETITION_ARCHITECTURE.md:142`（编排层 ⛔ 不执行 Path Repair，由 Planner 承担）、`:159`（`changes[]` 字段语义）、`:169`（`selection_required`）；`OPC_FINAL_SLIDES_CONTENT.md:108`；`OPC_FINAL_4MIN_DEMO.md:202`、`:221`；`OPC_PITCH_PACK.md:147`；`OPC_JUDGE_QA_SHORT.md:51`、`:53`；`COMPETITION_DEMO_SCRIPT.md:142`、`:145`；`SCREENSHOT_INDEX.md:52` | PARTIAL（替代候选检查已实现；**不自动替换已有班**） | Mock（模式 1 样例）/ 实际代码计算（模式 2） | ALLOWED-WITH-QUALIFIER | **已实现替代教学班候选评估；保留已有班并要求人做选择，`changes` 可能只是唯一 CLEAR `required` 候选的新增记录。** |
| F14-b **样例与口径的张力**：Mode 1 提交样例的两条 `changes` 均为**替换型**，原因正是"命中回避时段 / 连堂过密" | 样例事实：`mock_data/plan_result.json:11-21`（两条均为 `from_class` → `to_class`，原因分别为"命中用户避开的时段""与当前课表中已记录的时间段连堂过密"）；口径侧：`README.md:61`「Mode 1 的 `risks` / `changes` 是**人工构造的演示样例**」、`COMPETITION_DEMO_SCRIPT.md:142`、`OPC_FINAL_4MIN_DEMO.md:199`、`DEMO_VERSION_LOCK.md:123`、`SCREENSHOT_INDEX.md:52`（已披露为人工样例） | PARTIAL（已逐处披露，但样例形态与"不自动调班"口径反向） | Mock | ALLOWED-WITH-QUALIFIER | **Mode 1 的 `changes` 为人工构造的预置演示样例（可含替换型示例），不代表系统具备按偏好 / 连堂密度自动调班的能力。** |

### 族 F15 · Preference 语义（结构化输入、未保证全部执行）

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F15-a `Preference` 由结构化表单收集并原样传给 Planner | `README.md:59`、`:234`；`COMPETITION_ARCHITECTURE.md:151`（`plan(*, makeup_tasks, offerings, current_schedule, preference)` 四参数）；`OPC_PITCH_PACK.md:149`；`OPC_JUDGE_QA_SHORT.md:123`；`OPC_FINAL_4MIN_DEMO.md:155`；页面事实：`PreferenceForm.vue:154`「仅记录偏好；是否作为正式求解约束执行，以 PlanResult 输出为准。」 | YES（收集与传递已实现） | 外部本地输入（用户表单）/ Mock（模式 1 默认值） | ALLOWED-WITH-QUALIFIER | **`Preference` 来自结构化表单，由编排原样传入 Planner；是否作为正式求解约束执行，以 `PlanResult` 输出为准。** |
| F15-b 硬软分类与执行口径未冻结 | `OPC_JUDGE_QA_SHORT.md:123`「偏好的硬软分类与执行口径仍需要人工确认」；真值表 §4「`_pending_non_time` 将激活 Preference、容量、跨校区及先修口径留作 `manual_confirmation`」 | PARTIAL | 不适用 | ALLOWED-WITH-QUALIFIER | **偏好、容量、跨校区、通勤与先修口径保留人工确认，未声称全约束已执行。** |

### 族 F16 · 选课 / 注册是否执行

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F16-a 不执行选课 / 注册，输出只是建议方案 | `README.md:6`、`:46`、`:292`；`COMPETITION_ARCHITECTURE.md:180`；`COMPETITION_DEMO_SCRIPT.md:20`、`:199`（Q3）；`OPC_FINAL_SLIDES_CONTENT.md:29`、`:53`、`:193`；`OPC_FINAL_4MIN_DEMO.md:20`、`:200`；`OPC_PITCH_PACK.md:111`；`OPC_JUDGE_QA_SHORT.md:114`（Q12） | NO（未实现，且为明确边界） | 不适用 | ALLOWED | **系统不代替学生完成选课或注册，不执行任何教务操作；输出的是建议方案与未决事项清单。** |
| F16-b 「已选课 / 已注册 / 可直接执行 / 无冲突」属禁用表述 | `OPC_FINAL_SLIDES_CONTENT.md:204-205`（禁止表述条）、`:245`（术语规范）；`OPC_FINAL_4MIN_DEMO.md:22-23`；`OPC_PITCH_PACK.md:148` | — | 不适用 | ALLOWED（禁用清单） | **术语统一使用「建议方案」「建议纳入」「当前数据中无排课信息」「待人工确认」；⛔ 不用「已选课 / 已注册 / 无冲突 / 可直接执行」。** |

### 族 F17 · 风险 `risks[]` 与未决 `unresolved[]` 的来源

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F17-a 页面展示 `risks[]` / `unresolved[]`；Mode 1 为人工样例，计算模式以实际输出为准 | `README.md:61`、`:235`；`COMPETITION_ARCHITECTURE.md:160-171`；`COMPETITION_DEMO_SCRIPT.md:131`、`:135`；`OPC_FINAL_SLIDES_CONTENT.md:109`、`:133`；`OPC_FINAL_4MIN_DEMO.md:242`、`:266`；`OPC_PITCH_PACK.md:113`；`OPC_JUDGE_QA_SHORT.md:143`；`SCREENSHOT_INDEX.md:61-62`；`DEMO_VERSION_LOCK.md:123` | PARTIAL（`unresolved` 为实际输出；当前 Provider `risks=[]`） | Mock（模式 1 样例）/ 实际代码计算（模式 2） | ALLOWED-WITH-QUALIFIER | **页面显示 `risks` / `unresolved`；当前 Provider 主要输出 `unresolved`，`risks` 可为空；Mode 1 的风险等级是人工示例，⛔ 不称"实时算出风险等级"。** |
| F17-b `unresolved[].type` 四类语义（含"不得写成学校尚未排课 / 无课 / 无冲突"） | `COMPETITION_ARCHITECTURE.md:164-171`；`README.md:238`；`COMPETITION_DEMO_SCRIPT.md:167`；`OPC_FINAL_SLIDES_CONTENT.md:109`；`OPC_PITCH_PACK.md:59` | YES（页面按原始 `type` 展示，不归一） | Mock / 实际代码计算 | ALLOWED | **`schedule_unknown` / `selection_required` / `missing_data` / `manual_confirmation` 按原始类型展示；⛔ 不写成"学校尚未排课 / 无课 / 无冲突"。** |
| F17-c 样例核对 | `mock_data/plan_result.json:23-53`：`risks` 3 条（high / medium / low）、`unresolved` 3 条（`manual_confirmation` ×2 + `missing_data` ×1）；`SCREENSHOT_INDEX.md:59` 的 caption 与之逐项一致（本次另在 `05_risks_confirmation.png` 底部实图确认 `缺少数据 type: missing_data` 条目与页脚声明） | YES（caption 与样例一致） | Mock | ALLOWED | 维持现有 caption 与披露口径。 |

### 族 F18 · 测试与构建证据数字

| claim | where used | implemented? | data provenance | allowed? | final wording |
|---|---|---|---|---|---|
| F18-a 后端 `python -m pytest -o addopts="" -q` = 2987 passed / 2 既有 Windows 平台失败 / 2 skipped | `OPC_FINAL_SLIDES_CONTENT.md:190`、`:218`（**仅此一处**；9 份材料其余各处均无测试数字） | PARTIAL（单点记录，本轮按要求**未复跑**；`docs/data/SECOND_PASS_INTEGRATION_AUDIT.md:203` 另记早期快照 2853 passed / 2 failed / 2 skipped，同类形态一致但非同一数字） | 不适用 | ALLOWED-WITH-QUALIFIER | **后端 `python -m pytest -o addopts="" -q`：2987 passed / 2 既有 Windows 平台失败（非本次引入、未修未 skip）/ 2 skipped（<记录日期、宿主与 Python 版本待 owner 补全>）。** |
| F18-b 前端 `npm run test` = 142 passed / 10 files；`npm run typecheck` 与 `npm run build` 均 exit 0 | `OPC_FINAL_SLIDES_CONTENT.md:191`、`:218`、`:220`（列出 10 个测试文件名） | PARTIAL（10 个测试文件**已核实存在**：`frontend/tests/` 下恰为 10 个 `*.spec.ts`，与 `:220` 清单逐一对应；142 passed 与 exit 0 本轮未复跑） | 不适用 | ALLOWED-WITH-QUALIFIER | **前端 `npm run test`：142 passed / 10 files；`npm run typecheck`、`npm run build` 均 exit 0（同一记录环境）。** |
| F18-c 命令口径与 README 不一致 | `README.md:250` 记载的命令是 `python -m pytest`（无 `-o addopts="" -q`）；`:263-266` 记载前端三命令；证据数字出现在 `OPC_FINAL_SLIDES_CONTENT.md:190-191` 且未附日期 / 宿主 / 版本 | PARTIAL | 不适用 | ALLOWED-WITH-QUALIFIER | **README §8 应同时给出证据命令 `python -m pytest -o addopts="" -q`，并把 2987 / 142 / exit 0 与日期、宿主、Python 与 Node 版本绑定记录。** |

---

## 3. 矛盾清单

> 共 **15 条**（其中 **M1 已于 2026-10-07 修复**，见 §3.1；修复后**未发现新的越界项**，剩余 14 条均为【可核对不一致】或【限定语/术语】）。判定分三档：**【越界】**= 可能被读成"已实现真实能力/已连接真实来源"；**【可核对不一致】**= 评委按材料即可当场核对出不符；**【限定语/术语】**= 同向但强度或用语不齐，会导致讲法漂移。

### 3.1 【越界】1 条（**已修复 ✅**）

**M1.（原）页面第 2 区副标题出现肯定式「从教务系统中抓取」，与全部材料的「未连接任何实时教务系统」直接冲突**
- 涉及文件（修复前）：产品文案 `frontend/src/App.vue:323`（该句已入镜 `docs/submission/assets/02_requirement_assessment.png`）↔ `README.md:129`、`COMPETITION_ARCHITECTURE.md:243`、`OPC_PITCH_PACK.md:151`、`OPC_JUDGE_QA_SHORT.md:87`、`OPC_FINAL_SLIDES_CONTENT.md:178`
- 具体差异（修复前）：材料侧一律为"没有连接任何实时教务系统"；页面侧为"Course Data 模块**从教务系统中抓取**并标准化"。同屏正下方就是「教学班数据：演示快照（Synthetic）」，形成自相矛盾的同屏观感。
- 判定（修复前）：**是**（"从教务系统中抓取"等价于"已对接学校系统"，正是 `OPC_PITCH_PACK.md:151` 红线禁止的说法）。
- **修复记录**：已在 PR #51 HEAD `51eaccb1f9b23f9226760eab323028ed85d01b0a` 替换为
  「Course Data 模块负责教学班数据的标准化与结构化；当前比赛演示使用明确标识的 Synthetic 教学班快照（未连接任何实时教务系统）。支持多段排课及中性无排课数据状态（DG-01 / DG-07D）。」
  —— diff 为**单个用户可见字符串**（⛔ 未改业务逻辑 / API / Planner / Provider / Schema / 后端 / mock 数据 / runtime）。
- **修复后复核**：`frontend/src/**` 全文检索「抓取 / 已连接教务 / 实时教务」= **0 命中**；文案红线审计 PASS（用户可见面 0 命中）；
  `02_requirement_assessment.png` 与 `03_offerings_preferences.png` 已按新 HEAD **重新采集**，同屏同时给出「Synthetic 教学班快照」与「未连接任何实时教务系统」。
- 当前状态：**RESOLVED**（不再构成对外越界项）。

### 3.2 【可核对不一致】4 条

**M2. `DEMO_VERSION_LOCK.md:135` 的"逐字"页面横幅引用与实际 UI 不符**
- 涉及文件：`docs/submission/DEMO_VERSION_LOCK.md:135`（写作「当前展示的是 Mock 演示通道数据（**人工智能**），不是真实教务在线数据。」）↔ 实际 UI `frontend/src/components/TopStatusBar.vue:75`（「当前展示的是 Mock 演示通道数据（**人工虚构**），不是真实教务在线数据。」）
- 具体差异：「人工智能」 vs 「人工虚构」。该句被该文件定位为"界面上的三处披露（截图中可见）"之一，属逐字引用。
- 是否构成越界：否（两者都不声称真实数据），但**逐字引用失准**，且"人工智能"字样反而会被读成"已接入 AI"。
- 建议统一为：**「当前展示的是 Mock 演示通道数据（人工虚构），不是真实教务在线数据。」**

**M3. `SCREENSHOT_INDEX.md` 的 `01_background.png` caption 超出实际画面**
- 涉及文件：`SCREENSHOT_INDEX.md:18-22`（claim 取景含"应用标题区 + Mock 演示横幅 + 8 场景演示路线"，评委看到含"后端数据源标头 `mock`"，并据此写"来源披露在首屏可见（Mock 横幅 + 数据源标头）"）↔ 实际 `docs/submission/assets/01_background.png`（1600×1100，本次实图：顶部自"演示路线（8 场景）"标题起，**不含**品牌头、Mock 横幅与数据源标头）
- 具体差异：画面内确有第 0 区的 `Mock 数据` 角标可支撑"来源披露可见"，但 caption 点名的三个元素均不在画面中。
- 是否构成越界：否（页面本身确有这些披露），但属**可当场核对出的 caption 夸大**。
- 建议统一为：**取景：8 场景演示路线 + 第 0 区「用户输入」上半部（含区块 `Mock 数据` 角标）。** 或按 caption 重拍含 Mock 横幅与数据源标头的取景。

**M4. `SCREENSHOT_INDEX.md` 的 `03_offerings_preferences.png` caption 声称 Synthetic 披露条在画面内，实际不在；且与 SLIDES 的强制规范冲突**
- 涉及文件：`SCREENSHOT_INDEX.md:38-42`（取景写"第 2 区…下半部 + 第 3 区"，评委看到却写"**「教学班数据：演示快照（Synthetic）」披露条** + 「当前为演示数据…」+ 折叠说明（北校园深分页异常长句）"，并据此断言"① Synthetic 披露**在界面上逐字可见**"）↔ 实际 `docs/submission/assets/03_offerings_preferences.png`（1600×1250，本次实图：顶部即第 2 区教学班表格中部，**无**披露条与长句）；同图对照 `02_requirement_assessment.png` **含**披露条
- 具体差异：披露方向相反——02 有、03 无；而 `OPC_FINAL_SLIDES_CONTENT.md:244` 明文要求"每张涉及数据的截图区**必须保留**…「教学班数据：演示快照（Synthetic）」；⛔ 不得裁掉、覆盖或折叠"，且 `:73` 指定 03 作为 Slide 2 主图。
- 是否构成越界：否（同屏其他截图已有披露），但属**自家版式规范未满足 + caption 与素材不符**。
- 建议统一为：**03 的 caption 改为"第 2 区教学班表格下半部 + 第 3 区结构化偏好（本帧不含披露条，披露见 02）"**；或重拍 03 使披露条入镜（推荐，符合 SLIDES §版式规范）。

**M5. 「截图 / 成品尚未生成」的声明已过期**
- 涉及文件：`OPC_FINAL_SLIDES_CONTENT.md:252`（"以下 6 张截图**由另一位同事生成**，本文件只引用文件名；⛔ 本文件未创建、也未声称这些文件已生成"）↔ `docs/submission/assets/` 下 6 个 PNG 均已存在（126 KB / 191 KB / 142 KB / 177 KB / 153 KB / 115 KB，本次抽验 5 张为真实页面截图）且 `SCREENSHOT_INDEX.md` 逐张描述、`DEMO_VERSION_LOCK.md:149` 亦引用；附加：`OFFICIAL_RULE_CHECK.md:32`「尚无可提交的成品 PPT/PDF」与 `OPC_PORTAL_INFO_TEMPLATE.md:327`「成品文件（PPT/PDF）…不在仓库中」 ↔ 工作区已存在 `docs/submission/学航转衔_OPC_答辩稿.pptx`（765 KB）
- 具体差异：文字声明落后于工作区现状。需注意 `git status` 显示 `docs/submission/` **整个目录未被 Git 跟踪**（`git ls-files docs/submission` 为空），故"不在仓库中"在"未被版本控制"的意义上仍成立。
- 是否构成越界：否。
- 建议统一为：**「6 张截图与答辩稿 PPT 已在本分支工作区生成（尚未提交 / 尚未上传，故暂无 URL）；其来源与口径以 `SCREENSHOT_INDEX.md` 与 `DEMO_VERSION_LOCK.md` 为准。」**

### 3.3 【限定语 / 术语】10 条

**M6. LEVEL 1 的"禁称"与"已具备"两种口径并存**
- 涉及文件：`COMPETITION_DEMO_SCRIPT.md:16`、`OPC_FINAL_4MIN_DEMO.md:24`（⛔ 不得声称已达成 LEVEL1）↔ `README.md:163`、`OPC_FINAL_SLIDES_CONTENT.md:9`、`:228`、`OPC_PITCH_PACK.md:99`（已具备 LEVEL 1（synthetic）wiring capability）；同一文件 `OPC_FINAL_SLIDES_CONTENT.md` 的 §0 红线 ③ 与 §5.6 即同时出现两种口径。
- 具体差异：**限定语有无**。真值表 §5 允许"已具备 LEVEL 1（synthetic）wiring capability"，但禁止无限定地"已达到 LEVEL 1"。
- 是否构成越界：否（限定语在肯定侧出现）；但主讲人可能因禁语而不敢说，或因摘引而说过头。
- 建议统一为：**「正式证据等级为 LEVEL 0；仅具备 LEVEL 1（synthetic）的 wiring capability，⛔ 不得表述为『已达成 LEVEL 1 / LEVEL 2 / LEVEL 3』。」**

**M7. 教学班来源术语混用：模式 1 实为 Mock 通道对象，却被统一称作 "Synthetic 演示快照"**
- 涉及文件：`README.md:133-139`、`COMPETITION_ARCHITECTURE.md:225-227`、`OPC_FINAL_4MIN_DEMO.md:13`、`SCREENSHOT_INDEX.md:39`（caption 写 Synthetic）↔ `DEMO_VERSION_LOCK.md:50-57`（§3.1 模式 1 使用 `mock_data/course_offerings.json` 并给出 SHA-256）、`DEMO_VERSION_LOCK.md:62-68`（§3.2 Synthetic 快照"模式 2 才需要；本轮录制**未使用**"）、`SCREENSHOT_INDEX.md:41`（"确切来源：`mock_data/course_offerings.json`（9 个教学班）"）
- 具体差异：同一份材料内，caption 说 Synthetic、确切来源说 Mock JSON。
- 是否构成越界：否（两者均为人工 / 程序生成，皆非真实供给）；但会把审批口径（真值表 §2 的 Mode1 source = `mock_data/course_offerings.json`）讲糊。
- 建议统一为：**「模式 1 的教学班对象经 Mock 回放通道提供；模式 2 为 Synthetic 生成器快照。两者皆为人工 / 程序生成，均不是真实学校供给。」**

**M8. 「全部标注为 Mock」与「必须保留 Synthetic 标签」并存**
- 涉及文件：`README.md:149`、`COMPETITION_ARCHITECTURE.md:221`、`OPC_FINAL_4MIN_DEMO.md:12` ↔ `COMPETITION_ARCHITECTURE.md:225-227`、`OPC_FINAL_4MIN_DEMO.md:13`、`SCREENSHOT_INDEX.md:39`、截图事实（`02_requirement_assessment.png` 同屏同时含 `Mock 数据` 角标与 Synthetic 披露条）
- 具体差异：粒度不齐——Synthetic 属"演示数据"，但标签并不只是 Mock。
- 是否构成越界：否。
- 建议统一为：**「模式 1 基础区标注为 Mock 演示数据；其中教学班区块另标『教学班数据：演示快照（Synthetic）』，两者同时保留。」**

**M9. 测试证据数字单点且与 README 命令口径不一致**
- 涉及文件：`OPC_FINAL_SLIDES_CONTENT.md:190-191`、`:218` ↔ `README.md:250`（`python -m pytest`）、`:263-266`；另 `OPC_FINAL_SLIDES_CONTENT.md:14` 自身禁止"任何未经验证的数字"
- 具体差异：① 数字（2987 / 142 / exit 0）**仅出现在 SLIDES**，9 份材料其余各处无复述，也无日期 / 宿主 / 版本；② 证据命令带 `-o addopts="" -q`，README 记载的命令不带；③ 前端"10 files"已核实（`frontend/tests/` 恰 10 个 `*.spec.ts`），但 142 passed 与 exit 0 本轮未复跑。
- 是否构成越界：否（测试计数不是效果指标）；但不符合 SLIDES 自己的数字可验证要求。
- 建议统一为：**「后端 `python -m pytest -o addopts="" -q`：2987 passed / 2 既有 Windows 平台失败（非本次引入、未修未 skip）/ 2 skipped；前端 `npm run test`：142 passed / 10 files；`npm run typecheck`、`npm run build` 均 exit 0（<记录日期 / 宿主 / Python 与 Node 版本>）。」** 并同步进 `README.md` §8。

**M10. 「`changes` 可能只是新增记录」与 Mode 1 样例的"替换型"变更反向**
- 涉及文件：口径侧 `README.md:236`、`OPC_JUDGE_QA_SHORT.md:51`、`OPC_FINAL_4MIN_DEMO.md:202` ↔ 样例侧 `mock_data/plan_result.json:11-21`（两条 `changes` 均为 `from_class` → `to_class`，原因分别是"命中用户避开的时段""连堂过密"）
- 具体差异：材料说"可能只是新增"，而提交的演示样例恰恰演示了"按偏好 / 连堂密度换班"——正是真值表 B1 认定为误导的叙事形态。所幸 `README.md:61`、`COMPETITION_DEMO_SCRIPT.md:142`、`DEMO_VERSION_LOCK.md:123`、`SCREENSHOT_INDEX.md:52` 均已逐处披露 Mode 1 为人工样例。
- 是否构成越界：否（已披露），但属**样例与口径反向**的高风险组合。
- 建议统一为：**「Mode 1 的 `changes` 为人工构造的预置演示样例（可含替换型示例），不代表系统具备按偏好 / 连堂密度自动调班的能力。」**

**M11. `COMPETITION_DEMO_SCRIPT.md` 残留肯定式「调班」并误引页面导航文案**
- 涉及文件：`COMPETITION_DEMO_SCRIPT.md:31`（"偏好约束、**调班修复**和风险解释串成一条链"）、`:87`（"四步流程引导条（… → **课表求解与调班 Path Repair**）"）↔ 实际页面导航 `frontend/src/components/TopStatusBar.vue:53-67`（「0. 用户输入 / 1. 培养要求评估 / 2. 开课教学班 / 3. 用户偏好 / 4. 重构方案与求解」）；同族禁用清单见 `OPC_FINAL_4MIN_DEMO.md:21`
- 具体差异：材料引用的 UI 文案不存在；"调班"字样在两处肯定式出现（虽未写"自动"）。
- 是否构成越界：否。
- 建议统一为：**「…偏好约束、受限修复候选（Path Repair）和风险解释串成一条链」**；引用导航时逐字使用实际文案「1. 培养要求评估 / 2. 开课教学班 / 3. 用户偏好 / 4. 重构方案与求解」。

**M12. `OPC_FINAL_SLIDES_CONTENT.md` 的"6 张截图引用清单"与其"版式规范"对同一素材的要求不齐**
- 涉及文件：`OPC_FINAL_SLIDES_CONTENT.md:252-261`（只引用文件名）↔ `:244`（每张涉及数据的截图区**必须保留** Synthetic 披露）与 M4 的事实（03 未保留）
- 具体差异：规范层要求保留披露，素材层未满足。
- 是否构成越界：否。
- 建议统一为：**保持 `:244` 的规范；对不含披露的素材补拍或在 caption 中显式标注"本帧不含披露，披露见 XX"。**

**M13. 「200–300 字简介」存在两个不同版本与两个不同字数**
- 涉及文件：`OPC_PITCH_PACK.md:38`（297 字版本，内容含"输出建议方案、变更记录与未决事项"）↔ 附加材料 `OPC_PORTAL_INFO_TEMPLATE.md:53`（290 字版本，内容含"输出建议课表、变更、风险与未决事项"），后者 `:56` 称"与 `OPC_PITCH_PACK.md` §4 同一口径"
- 具体差异：正文不同、字数不同（297 / 290），且都标 `已确定（仓库可核实）`。
- 是否构成越界：否。
- 建议统一为：**两者只保留一份正文，另一处改为逐字引用（同一文本、同一字数）。**

**M14. `REHEARSAL_LOG.md` 引用了不存在的文件**
- 涉及文件：`REHEARSAL_LOG.md:5`（"真人出声计时彩排仍是提交前的 P0 待办（见 `docs/submission/FINAL_SUBMISSION_CHECKLIST.md`）"）↔ 仓库中**缺失（未生成）** `docs/submission/FINAL_SUBMISSION_CHECKLIST.md`
- 是否构成越界：否。
- 建议统一为：**把引用改为现有的清单载体（如 `REHEARSAL_LOG.md` §4 遗留清单或 `DEMO_VERSION_LOCK.md` §7），或补齐该文件。**

**M15. 外部规则未决风险（是否要求 AI 真实运行）在对外材料中覆盖不齐**
- 涉及文件：附加材料 `OFFICIAL_RULE_CHECK.md:35`（"🔴 **高风险不匹配**：本项目为固定工具编排原型，未集成 LLM / RAG / GraphRAG…①**必须**在本赛道细则中确认是否有'作品须真实运行 AI 模型 / 智能体'的硬性要求"）、`:54`（未核实项）↔ `OPC_FINAL_SLIDES_CONTENT.md` / `OPC_FINAL_4MIN_DEMO.md` / `OPC_JUDGE_QA_SHORT.md` / `OPC_PITCH_PACK.md` 四份对外材料**均未提示该未决资格风险**（仅 `OPC_PORTAL_INFO_TEMPLATE.md:370` 提到"以 `OFFICIAL_RULE_CHECK.md` 核查结果为准"）
- 具体差异：内部风险已识别，对外材料未同步其"未决"属性；四份材料一律把"未接入 LLM"表述为**纯边界**，读起来没有任何资格风险。
- 是否构成越界：否（并未把未实现说成已实现）；但**披露覆盖不一致**，一旦赛道细则要求 AI 真实运行，评委会认为材料未披露已知风险。
- 建议统一为：**「⛔ 未接入 LLM / RAG / GraphRAG；本赛道细则是否要求作品真实运行 AI 模型，**尚未核实**，已列入提交前 owner 核对项（见 `OFFICIAL_RULE_CHECK.md`）。」**

### 3.4 结论性说明

- 未发现"把未实现说成已实现"的**材料层**断言：9 份材料中"全局最优 / 自动调班 / 自动选课 / 偏好全部生效 / 已接入大模型 / Real E2E 完成 / 其余全部真实 / `ready` 即 LEVEL2"一律出现在 ⛔ 禁用清单或否定句中。
- **唯一的实质越界来自产品文案而非文档**（M1），且已经进入提交截图 02。
- 最接近"疑似矛盾但其实一致"的一组：`README.md:236`「`changes` 可能只是唯一 CLEAR `required` 候选的新增记录」与 Mode 1 样例的两条替换型 `changes`（M10）——**方向相反但已被逐处披露为人工样例**，故不计入越界，只列为需限定语的组合风险。

---

## 4. 禁止说法对照表

> 「材料中是否出现」指该说法（或其字面）是否出现在 9 份审计材料中；「语境」判定其是 ⛔/不/非 的否定式，还是肯定式。

| 禁用说法 | 材料中是否出现 | 出现位置 | 语境是否定式（⛔ / 不 / 非） | 判定 |
|---|---|---|---|---|
| 全局最优 / 全局优化 | 出现 | `README.md:68`；`OPC_FINAL_SLIDES_CONTENT.md:132`、`:205`；`OPC_PITCH_PACK.md:93`、`:146`；`OPC_JUDGE_QA_SHORT.md:60`、`:140`；`COMPETITION_DEMO_SCRIPT.md:142`；`OPC_FINAL_4MIN_DEMO.md:21`、`:203`、`:221`；`OPC_PORTAL_INFO_TEMPLATE.md:229`、`tools/architecture_diagram.html:113` | ✅ 全部为否定式或禁用清单（如"不是全局优化器""不得说"） | **合规** |
| CP-SAT / ILP 已求解 | 出现 | `README.md:68`；`OPC_FINAL_SLIDES_CONTENT.md:132`；`OPC_PITCH_PACK.md:93`、`:146`；`OPC_JUDGE_QA_SHORT.md:60`；`OPC_PORTAL_INFO_TEMPLATE.md:229` | ✅ 否定式（"没有用 CP-SAT 或 ILP 求解"） | **合规** |
| 自动调班 / 自动换班 | 出现 | `README.md:68`；`OPC_FINAL_SLIDES_CONTENT.md:108`、`:132`、`:205`；`OPC_PITCH_PACK.md:147`；`OPC_JUDGE_QA_SHORT.md:53`、`:140`；`COMPETITION_DEMO_SCRIPT.md:141`、`:142`、`:145`；`OPC_FINAL_4MIN_DEMO.md:21`、`:203`、`:221`；`VIDEO_RECORDING_PLAN.md:151` | ✅ 否定式（`OPC_FINAL_4MIN_DEMO.md:28` 明文"否定式表述允许且必须说"） | **合规**（术语残留另见 M11：`COMPETITION_DEMO_SCRIPT.md:31`、`:87` 的"调班"为肯定式词组，但未与"自动"连用） |
| 自动选课 / 自动注册 | 出现 | `README.md:68`；`OPC_FINAL_SLIDES_CONTENT.md:205`；`OPC_PITCH_PACK.md:148`；`OPC_JUDGE_QA_SHORT.md:140`；`OPC_FINAL_4MIN_DEMO.md:22`；`tools/architecture_diagram.html:113` | ✅ 否定式 | **合规** |
| 偏好全部生效 / 所有偏好已执行 | 出现 | `README.md:68`、`:296`；`OPC_PITCH_PACK.md:149`；`OPC_FINAL_SLIDES_CONTENT.md:205`；`OPC_FINAL_4MIN_DEMO.md:21`；`OPC_JUDGE_QA_SHORT.md:123`、`:125`；`COMPETITION_DEMO_SCRIPT.md:121`、`:146` | ✅ 否定式（"不保证全部偏好被执行"） | **合规**（措辞"执行 / 满足"不齐，见 F7-b） |
| 已接入大模型 / LLM 自动分析本 case / 已 RAG 增强 / GraphRAG 推理 | 出现 | `OPC_PITCH_PACK.md:150`；`OPC_FINAL_SLIDES_CONTENT.md:206`；`OPC_JUDGE_QA_SHORT.md:26`、`:44`；`DEMO_VERSION_LOCK.md:139`；`OPC_PORTAL_INFO_TEMPLATE.md:311` | ✅ 否定式 | **合规** |
| 已连接教务 / 已对接学校系统 / 实时教务数据 | 出现（文档侧均为否定式） | `OPC_PITCH_PACK.md:151`；`OPC_JUDGE_QA_SHORT.md:89`；`OPC_FINAL_4MIN_DEMO.md:22`；`OPC_FINAL_SLIDES_CONTENT.md:178`、`:203`；`README.md:129`；`COMPETITION_ARCHITECTURE.md:243`；`DEMO_VERSION_LOCK.md:139` | ✅ 文档侧否定式；**⛔ 但产品文案 `frontend/src/App.vue:323`「从教务系统中抓取」为肯定式，并已进入 `assets/02_requirement_assessment.png`** | **文档合规 / 产品+截图不合规（M1，唯一实质越界）** |
| Real E2E 完成 / completed | 出现 | `OPC_PITCH_PACK.md:152`；`OPC_FINAL_SLIDES_CONTENT.md:204`、`:228`；`OPC_JUDGE_QA_SHORT.md:140`；`OPC_FINAL_4MIN_DEMO.md:24`；`DEMO_VERSION_LOCK.md:139` | ✅ 否定式（"未完成""不得声称"） | **合规** |
| 真实数据 / 全部数据均为真实 | 出现 | `README.md:129`（"不存在'全部数据均为真实'的说法"）；`OPC_PITCH_PACK.md:153`；`OPC_JUDGE_QA_SHORT.md:71`、`:140`；`OPC_FINAL_4MIN_DEMO.md:22`；`OPC_FINAL_SLIDES_CONTENT.md:203` | ✅ 否定式 | **合规** |
| 只有教学班是合成的 / 其余全部真实 | 出现 | `COMPETITION_ARCHITECTURE.md:227`、`:237`；`README.md:137`；`COMPETITION_DEMO_SCRIPT.md:118`；`OPC_PITCH_PACK.md:153`；`OPC_JUDGE_QA_SHORT.md:71`；`VIDEO_RECORDING_PLAN.md:120` | ✅ 否定式 | **合规** |
| `ready` 即 LEVEL2 / `ready` 不等于 LEVEL2 | 出现 | `README.md:157`、`:160`、`:291`；`COMPETITION_ARCHITECTURE.md:223`；`OPC_FINAL_SLIDES_CONTENT.md:9`、`:178`、`:228`；`OPC_PITCH_PACK.md:112`、`:152`；`OPC_JUDGE_QA_SHORT.md:114`；`OPC_FINAL_4MIN_DEMO.md:24`；`COMPETITION_DEMO_SCRIPT.md:16`；`SCREENSHOT_INDEX.md:69`；`REHEARSAL_LOG.md:93` | ✅ 否定式（"ready ≠ LEVEL2"） | **合规** |
| 已达成 LEVEL1 / LEVEL2 / LEVEL3 | 出现 | `OPC_FINAL_4MIN_DEMO.md:24`；`COMPETITION_DEMO_SCRIPT.md:16`；`OPC_FINAL_SLIDES_CONTENT.md:228`；`OPC_PITCH_PACK.md:109`；`OPC_JUDGE_QA_SHORT.md:140` | ✅ 禁称清单；肯定侧的"已具备 LEVEL 1（synthetic）wiring capability"带限定语（见 M6） | **合规（限定语需统一）** |
| 已选课 / 已注册 / 无冲突 / 可直接执行 | 出现 | `OPC_FINAL_SLIDES_CONTENT.md:204`、`:205`、`:245`；`OPC_FINAL_4MIN_DEMO.md:20`、`:22`、`:23`；`README.md:6`、`:46` | ✅ 否定式/术语禁令 | **合规** |
| 系统实时算出风险等级 / AI 正在解释本次结果 | 出现 | `README.md:61`；`OPC_FINAL_SLIDES_CONTENT.md:133`；`OPC_PITCH_PACK.md:154`；`OPC_JUDGE_QA_SHORT.md:26`；`COMPETITION_DEMO_SCRIPT.md:134` | ✅ 否定式 | **合规** |
| 准确率 / 用户数 / 部署量 / 节省时间 / 学校背书 / 商业验证 | 出现 | `OPC_FINAL_SLIDES_CONTENT.md:14`、`:52`、`:227`；`OPC_PITCH_PACK.md:8`、`:67`、`:71`、`:75`、`:155`；`OPC_JUDGE_QA_SHORT.md:17`、`:98`、`:107`；`OPC_PORTAL_INFO_TEMPLATE.md:13`、`:62`、`:423` | ✅ 全部为禁用清单（唯一数字类证据是测试计数与字数，见 M9） | **合规** |

---

## 5. 审计结论

**一句话结论**：9 份对外材料在"AI 定位 / LLM 未接入 / Planner 受限 / Synthetic 与 Mock 分层 / LEVEL 0 与 `ready` ≠ LEVEL2 / 不选课不注册"六条主口径上高度收敛，未发现"把未实现说成已实现"的材料层断言；审计共记录 **15 条不一致**——其中 **1 条实质越界已修复**（页面文案"从教务系统中抓取"，已改并重拍截图 02 / 03）、**4 条可当场核对出的 caption / 逐字引用 / 成品状态不符**（其中 M2 / M3 / M4 已在本轮修正：横幅逐字引用、01 与 03 取景与 caption 一致）、**10 条限定语与术语不齐**（未改，属讲法与精度层面）。
**修复后对外越界项计数 = 0**（`frontend/src/**` 中「抓取 / 已连接教务 / 实时教务」0 命中；文案红线审计 PASS）。

**是否建议在提交前修改表述**：**建议继续整理剩余表述（仅限表述层，⛔ 不建议改任何代码）。** 按优先级：

1. **[已完成 ✅]** M1：页面文案已替换为「…负责教学班数据的标准化与结构化；当前比赛演示使用明确标识的 Synthetic 教学班快照（未连接任何实时教务系统）…」，02 / 03 已按新 HEAD 重拍。
2. **[已完成 ✅]** M2：`DEMO_VERSION_LOCK.md` 的横幅逐字引用已修正为"人工虚构"；M3 / M4 的 01、03 取景与 caption 已对齐（01 含品牌头与 Mock 横幅、03 含 Synthetic 披露条）。
3. **必须（owner）**：官方规则四项未核实（截止时间 / PPT 格式 / 是否必须现场演示 / 是否要求 AI 模型真实运行）——
   见 `docs/submission/OFFICIAL_RULE_CHECK.md`，该结论影响资格判断，⛔ 不得据猜测推进。
4. **强烈建议**：按 M6 / M9 / M10 / M11 统一四句 canonical 文本（LEVEL 1 限定语、测试证据命令与三要素、
   Mode 1 `changes` 样例说明、Path Repair / 导航文案），并把 `python -m pytest -o addopts="" -q` 与 2987 / 142 / exit 0
   一并写进 `README.md` §8（现已在 `DEMO_VERSION_LOCK.md` §8 记录实测证据）。
5. **建议**：修正 M13 / M15 的双版本简介与外部规则风险披露；M14 的悬空引用已因清单文件生成而消除。
6. **不改**：M7 / M8 / M12 属表述精度问题，可在下一轮随口径统一一并处理，不阻塞提交。

---

> **本文件性质**：审计记录，不构成对任何规则符合性、参赛资格或获奖的主张。所有行号来自本次实际读取。
> **截图核验范围（精确）**：`06_architecture.png`（整图）、`03_offerings_preferences.png`（整图 + 顶部裁切复核）、`01_background.png`（顶部裁切，含 y=0 起 340px）、`02_requirement_assessment.png`（底部裁切 420px）、`04_plan_result.png`（顶部裁切 420px）、`05_risks_confirmation.png`（底部裁切 360px）。即 6 张全部抽验，其中 01 / 02 / 04 / 05 为**局部裁切**核验，未整图逐行核对。
> 本轮未运行构建与测试，故 F18 的 2987 / 142 / exit 0 **未被本轮复现**。
