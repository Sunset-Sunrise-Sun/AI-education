# 评委向截图索引（SCREENSHOT INDEX）

> 全部截图在**模式 1（Mock 回放）**下现场采集，采集所用版本为 **`51eaccb1f9b23f9226760eab323028ed85d01b0a`**
> （PR #51 完成文案修复后的 HEAD；02 / 03 已按该 HEAD 重新采集，其余四张采集自前序锁定值 `248f835…`，
> 两版之间**只差第 2 区副标题这一行文案**，画面上仅 02 / 03 受影响）：
> 后端 `127.0.0.1:8000` + 前端**生产构建预览** `127.0.0.1:4173`（`npm run build` → `npm run preview`）。
> 采集环境与复现步骤见 `docs/submission/DEMO_VERSION_LOCK.md`。
> 截图内**没有**浏览器地址栏、**没有** DevTools、**没有**任何凭据 / 学号 / 成绩单 / 私人内容；页面为脱敏演示数据。
>
> ⚠️ 采集方式说明（诚实披露）：为获得统一取景，截图通过一个**同源本地包装页**按区块 id 精确滚动后截屏
> （包装页只做滚动，不修改应用、不注入业务逻辑；取景工具见 `docs/submission/tools/shot-harness.html`）。
> 现场演示时由主讲人手动滚动，画面内容一致。

---

## 01_background.png

| 项 | 内容 |
|---|---|
| 取景 | 页面顶部：应用标题区 + Mock 演示横幅 + **8 场景演示路线** + 第 0 区「用户输入」上半部 |
| 评委看到 | 产品定位（学业路径重构**原型**，固定工具编排，AI 增强待接入）、后端数据源标头 `mock`、脱敏验证环境标记、8 场景路线、目标学期 `2026-1` 与转专业上下文输入 |
| 它证明了什么 | ① 页面真实渲染且数据来自 `GET /api/v1/mock/demo`（模式 1）；② 演示路线与 8 场景结构存在；③ **来源披露在首屏可见**（Mock 横幅 + 数据源标头） |
| 确切来源 | `GET /api/v1/mock/demo`（读取 `mock_data/makeup_tasks.json` / `course_offerings.json` / `preference.json` / `plan_result.json`） |
| ⛔ 它不能证明 | 不证明输入数据来自学校；不证明 Curriculum / Planner 在本次会话中被执行；不证明任何认定或选课结论 |

## 02_requirement_assessment.png

| 项 | 内容 |
|---|---|
| 取景 | 第 1 区「历史培养要求评估（MakeupTask）」整表 + 第 2 区顶部（含 Synthetic 披露条） |
| 评委看到 | 逐条判定状态：`需要补修` / `可能等价（待人工确认）` / `待人工确认` / `已满足`；每行「认定说明与证据」带 `mock://curriculum/diff/...` 来源前缀；区块带 `Mock` 标记 |
| 它证明了什么 | ① 四种状态**互不等同**且原样展示；② 证据来源字段可追溯到 Mock 通道；③ **「待人工确认」没有被写成「需要补修」** |
| 确切来源 | `mock_data/makeup_tasks.json`（5 条，经 `/schemas/makeup_task.schema.json` 校验） |
| ⛔ 它不能证明 | 不证明这些补修结论对任何真实学生成立；不证明课程等价关系已被学校认定；不证明先修关系来自真实培养方案 |

## 03_offerings_preferences.png

| 项 | 内容 |
|---|---|
| 取景 | 第 2 区「开课教学班供给（CourseOffering）」**整块**（含顶部 Synthetic 披露条与全部教学班表）+ 第 3 区「学生个性化偏好（Preference）」 |
| 评委看到 | 教学班按课程分组（班号 / 教师 / 多段排课 / 容量「剩余 / 总数」/ 数据源 `mock`）；**「教学班数据：演示快照（Synthetic）」披露条** + 「当前为演示数据；Mock模式回放预置结果，计算模式执行实际代码，输入来源需逐项核验。」+ 折叠说明（北校园深分页异常长句）；第 3 区的偏好字段 |
| 它证明了什么 | ① Synthetic 披露**在界面上逐字可见**；② 多段 `meetings` 与容量原样展示、无前端推断；③ 偏好为**结构化字段**（⛔ 无自然语言解析） |
| 确切来源 | `mock_data/course_offerings.json`（9 个教学班）、`mock_data/preference.json` |
| ⛔ 它不能证明 | 不证明这是真实学校开课供给（**是 Synthetic 演示快照**）；不证明偏好被全部执行；不证明排课信息完整 |

## 04_plan_result.png

| 项 | 内容 |
|---|---|
| 取景 | 第 4 区「规划结果与建议课表（PlanResult）」：来源标注行 + 方案状态徽标 + KPI + 建议课表教学班 + 教学班调整对比与成因 + 风险提示开头 |
| 评委看到 | `基础演示数据：Mock · 规划结果：Mock`，并注明「属**回放预置结果**（未执行本次 Planner 求解）」；状态「部分可确认」；建议课表 4 个教学班（标签「建议纳入」）；2 条变更记录（原教学班 → 调整为 + 原因） |
| 它证明了什么 | ① 结果区来源被**局部、精确**标注（不冒充整页真实）；② `selected_classes` 的语义是**建议方案**（⛔ 不是已选课 / 已注册）；③ `changes[]` 前后对照与原因字段完整呈现 |
| 确切来源 | `mock_data/plan_result.json`（`partially_feasible`，预置演示样例） |
| ⛔ 它不能证明 | **不证明**这些变更由本次 Planner 求解得出（Mode 1 为人工构造样例）；不证明方案可执行；不证明偏好已进入求解 |

## 05_risks_confirmation.png

| 项 | 内容 |
|---|---|
| 取景 | 第 4 区：「教学班调整对比与成因」+「方案风险提示（risks）」+「待解决与待确认事项（unresolved）」+ 页脚数据声明 |
| 评委看到 | 3 条风险（高 / 中 / 低 + 原因）、3 条未决事项（`待人工确认` ×2 + `缺少数据` ×1，并保留原始 `type` 字段）；页脚写明实现边界（固定工具编排原型；未接入 LLM / RAG / GraphRAG）、数据声明（基础区 Mock；规划结果为回放预置结果）与教学班 Synthetic 披露 |
| 它证明了什么 | ① 风险与未决事项**如实暴露**，类型不被归一；② 人机边界：认定类结论一律待人工确认；③ 页脚给出与文档一致的 provenance 与实现边界 |
| 确切来源 | `mock_data/plan_result.json` 的 `risks[]` / `unresolved[]`（预置演示样例） |
| ⛔ 它不能证明 | 不证明风险等级由本次实际 Planner 计算（当前 Provider 主要输出 `unresolved`，`risks` 可能为空）；不证明方案无风险或可执行 |

## 06_architecture.png

| 项 | 内容 |
|---|---|
| 取景 | 架构图：**两条独立轴**——`IMPLEMENTED NOW · 实际执行的代码`（前端 → FastAPI → `PlanningOrchestrator` → 三个 Provider → `PlanResult`）与 `输入来源 · DISCLOSED`（外部本地 Case A manifest〔来源须证明〕/ Synthetic 教学班快照 / Mock 回放通道），外加 `AI ENHANCEMENT PLANNED`（LLM / RAG / GraphRAG，**尚未接入、不在执行路径上**） |
| 评委看到 | 图例区分「实际执行代码 / 外部本地输入 / Synthetic 演示快照 / Mock 回放通道 / 规划中能力」；页脚写明 LEVEL 0 与 `ready ≠ LEVEL2`，以及 ⛔ 不声称已接入大模型、不声称全局最优或自动选课 |
| 它证明了什么 | ① 架构语义与 `docs/architecture/COMPETITION_ARCHITECTURE.md` 一致（两轴、不含未实现能力）；② 明确区分「代码执行」与「输入来源」；③ 未把 LLM / RAG / GraphRAG 画进当前执行链路 |
| 确切来源 | 由 `docs/architecture/COMPETITION_ARCHITECTURE.md` 的语义以静态 HTML/CSS 渲染后截屏（与文档同源，不含新增主张） |
| ⛔ 它不能证明 | 不证明真实学校数据接入；不证明 LEVEL2 / LEVEL3；不证明任何模型能力已上线 |

---

## 截图与材料的一致性

- 六张截图与 `docs/submission/OPC_FINAL_SLIDES_CONTENT.md` 的 `visual suggestion` 一一对应（文件名相同）；
- 截图中的披露文案逐字来自 `frontend/src/utils/labels.ts`：
  「教学班数据：演示快照（Synthetic）」与「当前为演示数据；Mock模式回放预置结果，计算模式执行实际代码，输入来源需逐项核验。」；
- 截图中不出现任何真实学校数据、学生个人数据或凭据；所有条目来自提交在仓库内的 Mock 演示数据。

---

## ⚠️ 已修复的文案缺陷（记录，不再构成阻塞）

**02 / 03 截图内曾出现的第 2 区副标题旧句**：`Course Data 模块从教务系统中抓取并标准化的目标学期开课清单…`
（`frontend/src/App.vue` 第 2 区 `SectionCard` 的 `subtitle`）。

- 问题：肯定式"已对接学校系统"表述，与「⛔ 未连接任何实时教务系统」口径冲突；
- **处置：已修复**（PR #51 HEAD `51eaccb…`），现文案为：

  > Course Data 模块负责教学班数据的标准化与结构化；当前比赛演示使用明确标识的 Synthetic 教学班快照（未连接任何实时教务系统）。支持多段排课及中性无排课数据状态（DG-01 / DG-07D）。

- **02 与 03 已按修复后的 HEAD 重新采集**，新图中该行同时给出「Synthetic 教学班快照」与「未连接任何实时教务系统」；
- 修复方式为**单个用户可见字符串**替换（⛔ 未改任何业务逻辑 / API / Planner / Provider / Schema / 后端 / mock 数据 / runtime）。
