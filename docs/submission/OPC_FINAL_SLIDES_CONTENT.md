# 学航·转衔 · 决赛幻灯片内容（5 张主幻灯片）

> **项目定位（全片统一口径，逐字使用）**：
> **学航·转衔：面向转专业学生的学业路径重构原型（固定工具编排，AI 增强待接入）**
>
> **本片三条红线（每页都适用）**：
> ① **LLM / RAG / GraphRAG 尚未接入**——本版本无模型推理、无检索管线、无自然语言偏好解析；`Preference` 来自**结构化表单**；已实现的是**固定工具编排**。
> ② **实际代码执行 ≠ 输入数据已获得真实学校来源认证**：默认「模式 1」`GET /api/v1/mock/demo` 为**回放**预置对象，**不运行** Curriculum / Planner；「模式 2」`POST /api/v1/plan` 才**执行实际 Provider / RestrictedPlanner 代码**，且页面**基础展示区仍为 Mock 演示数据**，只有**规划结果区**来自实际计算；教学班 `CourseOffering` 输入是**明确标注的 Synthetic 演示快照**。
> ③ 正式 **Real E2E = LEVEL 0**（另具备 **LEVEL 1（synthetic）** wiring capability）；⛔ 未完成 Real LEVEL 2 / LEVEL 3，**`ready` ≠ LEVEL2**；北校园开课查询为**外部系统阻塞**（稳定深分页异常）已挂起。
>
> **Planner 权威表述（逐字使用，⛔ 不改写）**：
> 「已实现确定性时间检查、受限组合可行性检查及替代教学班候选评估。当前 Planner 保留已有班，仅在受限条件下提出新增/候选建议，并把无法确定的事项保留到 `unresolved` / 人工确认。」
>
> ⛔ 全片**不得出现**：准确率 / 用户数 / 部署情况 / 节省时间 / 学校背书 / 商业验证 / 真实风险打分等任何未经验证的数字或背书。

---

## Slide 1 · 问题 + 目标用户

### 1.1 slide title

**转专业之后：从零重建一条能毕业的学业路径**

### 1.2 bullets（4 条，可直接上版）

- 转专业学生最难的**不是补几门课**，而是把原专业的已修课程与**新专业的培养要求**重新对齐。
- 「缺什么 → 现实里开什么班 → 怎么排得进去 → 哪些必须由人拍板」，目前**全靠学生人工拼**。
- 目标用户：**转专业（转衔）学生**；以及**辅导员 / 教务人员**；以及关注边界与可复核性的**学院负责人 / 评委**。
- 本项目做的是**路径草案与风险清单**：⛔ 不代替学校做课程认定，⛔ 不代替学生选课 / 注册。

### 1.3 visual suggestion

- 主图：使用 `01_background.png`（用户输入区 / 转专业背景与目标学期上下文）。
- 建议版式：左侧「三类目标用户」三行卡片（学生 / 辅导员·教务 / 学院负责人·评委），右侧放截图，底部压一行定位语：
  **「面向转专业学生的学业路径重构原型（固定工具编排，AI 增强待接入）」**。

### 1.4 presenter notes

- 开场一句话：「转专业以后，问题不是重新选几门课，而是需要重新构建一条能毕业、能执行、风险透明的学业路径。」
- 我们服务的是三类人：学生要一份**看得懂、能对照检查**的补修路径草案；老师要一眼看清**风险点与需要人工介入的位置**；评委要能复核**数据来源与系统边界**。
- 请评委先记住一件事：这是一个**固定工具编排原型**，本版本**没有接入大模型**，我们不会把"AI 在理解你"当作已实现的能力来讲。

### 1.5 evidence source

- `README.md` §2「问题与目标用户」（痛点四条、目标用户三行表、「明确不做」边界）。
- `docs/demo/COMPETITION_DEMO_SCRIPT.md` §1「推荐开场白」、§0「事实基线」第 11 行（实现边界：固定工具编排原型；LLM / RAG / GraphRAG 尚未接入）。
- `docs/demo/COMPETITION_STARTUP.md` 开篇「实现边界（开场必须说清）」。

### 1.6 forbidden overclaim

- ⛔ 不得说「AI 已能理解 / 解析自然语言偏好」——本版本 `Preference` 来自**结构化表单**，**没有自然语言偏好解析**。
- ⛔ 不得说「已帮助 N 名学生 / 已在某高校部署 / 节省 X% 时间 / 学校已背书」——本版本**没有任何真实用户数、部署或背书数据**。
- ⛔ 不得说「系统可以替学生选课 / 注册 / 完成认定」——输出始终只是**建议方案**与**未决事项清单**。

---

## Slide 2 · 转专业规划为什么难

### 2.1 slide title

**五重不确定性叠加：差异、规则、供给、课表、认定**

### 2.2 bullets（5 条，可直接上版）

- **旧培养方案（原专业）**：已修课程与新专业要求的**对应关系分散在条款与文档里**，学生难以自查。
- **新培养方案（目标专业）**：要求逐条存在，但「已满足 / 可能等价 / 待人工确认 / 需要补修」**四种状态互不等同**。
- **已修课程记录**：只能推出「可能等价」，课程是否等价、学分差额如何认定属于**学校正式规则与审批范围**。
- **课表约束**：即使知道要补什么，还要在一个学期内同时满足**时间、节次、周次、校区**约束。
- **认定不确定性**：涉及等价、替代、学院特殊政策、培养方案歧义条款的结论**一律留给人工确认**，系统不下正式结论。

### 2.3 visual suggestion

- 主图：使用 `03_offerings_preferences.png`（教学班供给 + 结构化偏好），配合一张自绘「五重不确定性」五边形 / 五列卡片示意（纯几何图形，⛔ 不用任何机器人或大模型图形）。
- 建议版式：五列卡片等宽排列，每列一个来源（旧方案 / 新方案 / 已修 / 课表 / 认定），每列下一行中性短句；卡片底部统一踩一行：
  **「教学班数据：演示快照（Synthetic）」**。

### 2.4 presenter notes

- 这页想让评委看到：难点不是一个维度，而是五个维度**同时**叠加，所以单靠"让学生自己排"几乎不可能。
- 特别提醒一句判定状态：页面上会出现「待人工确认」和「可能等价（待人工确认）」——**它们都不等于"需要补修"**，一个是证据不足要请人认定，一个是已确认需要补修。
- 课表这一层，如果某个教学班当前数据里没有排课信息，我们的说法是中性的「当前数据中无排课信息」，**不会**说成"没有冲突"或"时间上可行"。

### 2.5 evidence source

- `README.md` §2「痛点（不夸大）」四条；§3「核心能力」表中 MakeupTask 状态说明与 `manual_confirmation` / `possibly_equivalent` 的边界说明；§10「已知限制与未决事项」第 7 条（先修关系真实来源尚无证据）。
- `docs/architecture/COMPETITION_ARCHITECTURE.md` §3.4（`meetings = []` 的中性语义、四种 `MakeupTask` 状态）、§3.5（三态冲突判定 `CONFLICT > UNKNOWN > CLEAR`、UNKNOWN ≠ INFEASIBLE）。
- `docs/demo/COMPETITION_DEMO_SCRIPT.md` 场景 3、场景 4 的口径与兜底话术。

### 2.6 forbidden overclaim

- ⛔ 不得把 `manual_confirmation` / `possibly_equivalent` 说成「已经确认需要补修」——两者与 `required` **互不等同**。
- ⛔ 不得说「系统已完成课程认定 / 学分认定 / 替代审批」——这些属于学校正式规则与审批范围，系统只**如实呈现**并交回人工。
- ⛔ 不得把本页的困难描述包装成「用 AI 就能自动解决」——本版本**没有模型参与**差异判定、等价判定与先修推断。

---

## Slide 3 · 产品流程

### 3.1 slide title

**一条可复核的链路：输入 → 评估 → 受限规划 → 候选调整 → 风险与未决 → 人工确认**

### 3.2 bullets（5 条，可直接上版）

- **输入**：目标学期、转专业上下文、当前课表、结构化偏好（`Preference` 来自表单，⛔ 无自然语言解析）。
- **培养要求评估**：Curriculum 逐条产出 `MakeupTask`，状态为 `satisfied` / `possibly_equivalent` / `manual_confirmation` / `required`。
- **受限规划**：已实现**确定性时间检查**、**受限组合可行性检查**、**替代教学班候选评估**；保留已有班，**仅在受限条件下**提出新增 / 候选建议。
- **Path Repair / 候选调整**：`changes[]` 记录「原教学班 → 调整为 + 原因」；⛔ **不自动换班、不自动选课、不是全局优化器**。
- **风险与未决 → 人工确认**：`risks[]` / `unresolved[]` 如实列出，涉及等价、替代审批、学院政策、歧义条款的结论留待人工确认。

### 3.3 visual suggestion

- 主图：使用 `02_requirement_assessment.png` + `04_plan_result.png` + `05_risks_confirmation.png`（三张横向串联成一条流程带入 → 出）。
- 建议版式：顶部一条六段式横向流程图（输入 / 评估 / 受限规划 / 候选调整 / 风险与未决 / 人工确认），每段下方挂一张对应截图；**人工确认**段用绿色收束块标注「人负责正式规则、权限边界与最终确认」。
- ⛔ 流程图中不得出现任何模型 / 检索 / 智能体图标。

### 3.4 presenter notes

- 这条链路的顺序是**严格固定**的：编排层只负责按固定顺序调用，不判断缺什么课、不检测冲突、不选班，把 Planner 的结果**原样**返回。
- 讲 Planner 时请逐字用这句权威口径：「已实现确定性时间检查、受限组合可行性检查及替代教学班候选评估。当前 Planner 保留已有班，仅在受限条件下提出新增/候选建议，并把无法确定的事项保留到 `unresolved` / 人工确认。」
- 最后一段是这套系统最核心的设计：我们**不替人下结论**。课程等价、学分差额、信息不足时的判断，系统全部原样留给人。

### 3.5 evidence source

- `README.md` §1 定位、§3「核心能力」表（含 Planner 权威表述与禁用说法）、三条安全约束（三态冲突 / UNKNOWN ≠ INFEASIBLE / 诚实失败）、§7「演示路径（8 个场景）」。
- `docs/architecture/COMPETITION_ARCHITECTURE.md` §3.3（编排内部顺序严格固定）、§3.5（解释 / 风险 / 人工确认回路）。
- `schemas/plan_result.schema.json`（`status` / `selected_classes` / `changes` / `risks` / `unresolved` 字段与枚举）。
- `backend/app/integration/orchestrator.py`（`PlanningOrchestrator`）、`backend/app/planner/provider.py`（`RestrictedPlannerProvider`）——仅用于确认类/文件名存在。

### 3.6 forbidden overclaim

- ⛔ 不得说「全局最优 / 全局优化 / CP-SAT 已求解 / ILP 已求解 / 自动换班 / 自动选课 / 所有偏好已执行」。
- ⛔ 不得说「系统实时算出风险等级」——模式 1 的 `risks` / `changes` 是**人工构造的演示样例**；计算模式以实际 Planner 输出为准，当前 Provider 主要输出 `unresolved`，**`risks` 可能为空**。
- ⛔ 不得把「风险与未决」讲成缺陷列表或已解决的问题清单——它们是**边界声明**，不是已经消化掉的问题。

---

## Slide 4 · 技术架构（只画实际已实现路径）

### 4.1 slide title

**IMPLEMENTED NOW 与 AI ENHANCEMENT PLANNED：两条互不混淆的边界**

### 4.2 bullets（5 条，可直接上版）

- **IMPLEMENTED NOW（执行路径）**：前端 Vue → FastAPI → `PlanningOrchestrator` → `CurriculumProvider` / `StoreBackedCourseDataProvider` / `RestrictedPlannerProvider` → `PlanResult`。
- 编排层**固定顺序**且只做三件事：取 `MakeupTask[]` → 取该学期 `CourseOffering[]` → 一并交给 Planner 并**原样**返回 `PlanResult`（⛔ 不做业务算法、⛔ 不调用模型）。
- **两条模式必须分开标注**：模式 1 `GET /api/v1/mock/demo` **回放**预置对象（不运行 Curriculum / Planner）；模式 2 `POST /api/v1/plan` **执行实际代码**，但**页面基础展示区仍为 Mock 演示数据**。
- 输入侧披露：教学班 `CourseOffering` 是**明确标注的 Synthetic 演示快照**；真实链路任一前置条件未就绪 ⇒ `503 real_pipeline_not_configured`，**不回退 Mock**（fail closed）。
- **AI ENHANCEMENT PLANNED（虚线、不在执行路径上）**：LLM / RAG / GraphRAG、自然语言偏好解析——**尚未接入**；⛔ 本次不画入任何执行链路，也不承载任何结论。

### 4.3 visual suggestion

- 主图：使用 `06_architecture.png`（分层架构图）。
- 建议版式：**同页左右两块、中间用一条醒目分隔线**——
  - 左块标题 **`IMPLEMENTED NOW`**：实线方框串起 Vue → FastAPI → `PlanningOrchestrator` → 三个 Provider → `PlanResult`；Mock 回放通道与 Synthetic 快照用**虚线**旁挂，并标注「输入来源，非代码」。
  - 右块标题 **`AI ENHANCEMENT PLANNED`**：浅灰点线框，仅列 LLM / RAG / GraphRAG 与自然语言偏好解析，明确写「尚未接入 · 不在当前执行路径」。
- ⛔ 不得把 LLM / RAG / GraphRAG 的连线接到 FastAPI、`PlanningOrchestrator`、任一 Provider 或 `PlanResult` 上。

### 4.4 presenter notes

- 这页请评委只看左半边：**蓝色实线**只说明"这段代码确实执行"，它**不说明输入来自学校**——这是两件独立的事。
- 右半边的灰框是方向，不是现状：本版本**没有模型调用、没有检索管线、没有自然语言偏好解析**，偏好是从结构化表单来的。
- 关于数据：默认模式是演示回放，页面回放预置对象、不运行上游计算；即使切到计算模式，页面**基础展示区仍是演示数据**，只有规划结果区来自实际计算。教学班的准确表述始终是「教学班数据：演示快照（Synthetic）」。

### 4.5 evidence source

- `docs/architecture/COMPETITION_ARCHITECTURE.md` §1 分层架构图（含 `AI["模型增强（LLM / RAG / GraphRAG）尚未接入 · 不在当前执行路径"]` 节点）、§2 图例（两条独立轴）、§3.3、§3.4、§4 fail-closed、§5 模式 1 / 模式 2 差异对照表。
- `README.md` §4 系统架构四层结构、§5.1 三段数据事实、§5.3 两种运行模式表、§5.4 fail-closed、§10 第 6 条（未集成 LLM / RAG / GraphRAG）。
- `docs/demo/COMPETITION_STARTUP.md` §2.3「模式 2 下必须如实说明的三件事」、§7 数据来源标注口径表。
- 类/文件存在性核对：`backend/app/integration/orchestrator.py`（`PlanningOrchestrator`）、`backend/app/curriculum/case.py`（`CurriculumCaseProvider`）、`backend/app/course_data/store_provider.py`（`StoreBackedCourseDataProvider`）、`backend/app/planner/provider.py`（`RestrictedPlannerProvider`）。
- 契约真源：`schemas/plan_result.schema.json`。

### 4.6 forbidden overclaim

- ⛔ 不得把 LLM / RAG / GraphRAG 画进当前执行链路，也不得把它们表述为「已接入 / 已在用 / 正在理解本次演示」。
- ⛔ 不得声称存在自然语言偏好解析——`Preference` 来自**结构化表单**。
- ⛔ 不得说「已连接实时教务系统 / 全部数据均为真实 / 可由此推出 LEVEL 2」——`data_source` 字段、HTTP 200、端点名、已验收 Store、`full_semester` 枚举、Case A 名称**都不是**真实来源证明；`ready` ⛔ ≠ LEVEL2。

---

## Slide 5 · 验证 + 限制 + 下一步

### 5.1 slide title

**完整的运行链路与诚实的 provenance：证据、限制、下一步**

### 5.2 bullets（5 条，可直接上版）

- **后端**：`python -m pytest -o addopts="" -q` = **2987 passed / 2 既有 Windows 平台失败（非本次引入、未修未 skip）/ 2 skipped**。
- **前端**：`npm run test` = **142 passed / 10 files**；`npm run typecheck` 与 `npm run build` 均 **exit 0**。
- **数据披露**：页面基础展示区为 **Mock 演示数据**；教学班 `CourseOffering` 是**明确标注的 Synthetic 演示快照**（每个区块分别标注）。
- **human-in-the-loop**：课程等价、学分差额、替代审批、学院政策与歧义条款一律标记待人工确认；系统⛔ 不执行选课 / 注册。
- **仍待完成**：正式 **Real E2E = LEVEL 0**（具备 LEVEL 1 synthetic wiring capability），⛔ **Real LEVEL 2 / LEVEL 3 未完成**；北校园开课查询为**外部系统阻塞**已挂起（⛔ 不声称可用、⛔ 不建议现场探测）；LLM / RAG / GraphRAG **尚未接入**。

### 5.3 visual suggestion

- 主图：使用 `05_risks_confirmation.png`（风险与未决事项 / 人工确认区）。
- 建议版式：左侧三格「验证证据」卡片（后端测试 / 前端测试与构建 / 页面 provenance 标注），右侧一格「限制与下一步」清单；
- 底部固定一条禁止表述条（可直接印上幻灯片）：

```text
⛔ 禁止出现的说法：已连接实时教务系统 · 实时教务数据 · 全部数据均为真实 ·
⛔ 禁止出现的说法：Real E2E completed · 可直接执行 · 已选课 · 已注册 · 无冲突 ·
⛔ 禁止出现的说法：官方已批准 · 完全无风险 · 全局最优 · 自动调班 · 自动选课 · 偏好全部生效 ·
⛔ 禁止出现的说法：LLM / RAG / GraphRAG 已接入 · 达成 LEVEL2 / LEVEL3
```

### 5.4 presenter notes

- 我们的验证重点不在"排得漂不漂亮"，而在**诚实**：Mock 与计算模式严格分离、未装配时明确拒绝、风险与人工确认事项如实暴露。
- 后端测试里那 2 个失败是**改动前基线上就存在的 Windows 平台相关用例**，属于已知项，我们**没有修、没有 skip、没有删断言**；前端 10 个测试文件覆盖来源标注、provenance 门禁、503 之后只请求一次且不回退 Mock 等门禁。
- 数据上请注意分层：页面基础区是演示数据，教学班是 Synthetic 快照；**实际代码执行不等于输入数据已获得真实学校来源认证**。
- 下一步清单很清楚：把真实 Real E2E 证据补齐推等级（当前 LEVEL 0）、解决北校园外部阻塞、再评估模型增强能力的接入——**接入之前，绝不把它写进当前执行路径**。

### 5.5 evidence source

- 测试与构建结果：后端 `python -m pytest -o addopts="" -q` = 2987 passed / 2 既有 Windows 平台失败 / 2 skipped；前端 `npm run test` = 142 passed / 10 files；`npm run typecheck`、`npm run build` exit 0。
- 测试已知项说明：`README.md` §8「测试与质量门禁」（2 个预先存在的平台相关失败用例：DOCX ZIP 成员名反斜杠断言在 Windows 语义下不触发；仓库绝对路径含形如日期 `-1` 片段导致断言误命中）。
- 前端测试文件（共 10 个，位于 `frontend/tests/`）：`app-provenance-guard.spec.ts`、`demo-snapshot-disclosure.spec.ts`、`form-validation-gate.spec.ts`、`plan-api.spec.ts`、`plan-result-provenance.spec.ts`、`real-e2e-prep.spec.ts`、`real-path-readiness.spec.ts`、`schedule-provenance-gate.spec.ts`、`user-input-panel.spec.ts`、`user-input.spec.ts`。
- Synthetic / Mock 披露口径：`README.md` §5.1 / §5.2；`docs/architecture/COMPETITION_ARCHITECTURE.md` §6；`docs/demo/COMPETITION_STARTUP.md` §7。
- 限制与等级：`README.md` §10「已知限制与未决事项」第 1–9 条、§5.5（`ready` ⛔ ≠ LEVEL2）；`docs/demo/COMPETITION_STARTUP.md` §2.1.1 第 2 点与「北校园外部阻塞」说明。
- 人工确认模型：`README.md` §3「人工确认模型」；`docs/architecture/COMPETITION_ARCHITECTURE.md` §3.5；`schemas/plan_result.schema.json` 的 `unresolved[]`（`type` 为开放字符串）。

### 5.6 forbidden overclaim

- ⛔ 不得把测试通过数 / 构建成功包装成「准确率 X%」「效果提升 X%」或任何未经验证的质量指标。
- ⛔ 不得声称已达成 **LEVEL 1 / LEVEL 2 / LEVEL 3** 或「Real E2E completed」——正式证据等级是 **LEVEL 0**，具备的是 LEVEL 1（synthetic）wiring capability。
- ⛔ 不得声称北校园已可用 / 已修复，也不得**建议现场探测**外部教务系统（零网络默认，该阻塞已挂起）。
- ⛔ 不得把「2 个既有失败」隐去或说成"全部通过"——它们是改动前基线上同样失败的已知项。

---

## 版式与视觉规范

| 项 | 规范 |
|---|---|
| 画幅 | **16:9**（1920×1080 或 1280×720），全片统一模板 |
| 字号 | 正文与条目**不低于 24pt**，标题 ≥ 36pt；投影后 3 米内可读 |
| 条目数 | **每页 ≤ 5 条**，每条 ≤ 2 行；短句，可直接上版 |
| 配色 | **克制**：以白底 + 深色正文为主，最多 2 个强调色（建议深蓝 = 实际执行代码 / 米黄或灰 = 输入来源标注）；⛔ 不用高饱和渐变大色块 |
| 图形标识 | ⛔ **不使用暗示"已接入大模型"的图形 / 机器人图标 / 神经网络图标 / 对话气泡"AI 助手"意象**；PPT 标题中的 "AI Agent" 只指产品方向与固定编排架构 |
| LLM / RAG / GraphRAG | 如需出现，只能放在 **`AI ENHANCEMENT PLANNED`** 灰框内，并标注「尚未接入 · 不在当前执行路径」 |
| 数据来源标注 | 每张涉及数据的截图区**必须保留**：区块 `Mock` 标记与「**教学班数据：演示快照（Synthetic）**」；⛔ 不得裁掉、覆盖或折叠 |
| 术语 | 统一使用「建议方案」「建议纳入」「当前数据中无排课信息」「待人工确认」；⛔ 不用「已选课 / 已注册 / 无冲突 / 可直接执行」 |
| 每页必备 | 页脚统一一行：**「固定工具编排原型 · LLM / RAG / GraphRAG 尚未接入 · Real E2E 等级 LEVEL 0」** |

---

## 截图引用清单

> ⚠️ 以下 6 张截图**由另一位同事生成**，本文件**只引用文件名**；⛔ 本文件未创建、也未声称这些文件已生成。

| 文件名 | 用于 | 内容要点 |
|---|---|---|
| `docs/submission/assets/01_background.png` | **Slide 1** | 用户输入区：目标学期 `2026-1`、原专业 → 目标专业、转入学期（转专业背景） |
| `docs/submission/assets/02_requirement_assessment.png` | **Slide 3** | 第 1 区「历史培养要求评估（MakeupTask）」：逐条判定与四种状态 |
| `docs/submission/assets/03_offerings_preferences.png` | **Slide 2** | 第 2 区教学班供给（含「教学班数据：演示快照（Synthetic）」）+ 第 3 区结构化 `Preference` |
| `docs/submission/assets/04_plan_result.png` | **Slide 3** | 第 4 区「建议课表教学班（`selected_classes`）」与方案状态、求解目标说明 |
| `docs/submission/assets/05_risks_confirmation.png` | **Slide 5** | 第 4 区「方案风险提示（`risks`）」与「待解决与待确认事项（`unresolved`）」 |
| `docs/submission/assets/06_architecture.png` | **Slide 4** | 分层架构图：`IMPLEMENTED NOW` 与 `AI ENHANCEMENT PLANNED` 两块清晰分开 |

---

## 附录 · 本文件引用的事实来源（仓库文件）

- `README.md`
- `docs/architecture/COMPETITION_ARCHITECTURE.md`
- `docs/demo/COMPETITION_DEMO_SCRIPT.md`
- `docs/demo/COMPETITION_STARTUP.md`
- `AGENTS.md`
- `schemas/plan_result.schema.json`
- 类/文件存在性核对：`backend/app/integration/orchestrator.py`、`backend/app/curriculum/case.py`、`backend/app/course_data/store_provider.py`、`backend/app/planner/provider.py`
- 前端测试文件名清单：`frontend/tests/*.spec.ts`（共 10 个）
