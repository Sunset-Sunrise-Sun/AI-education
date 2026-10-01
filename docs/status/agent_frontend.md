# Agent / Frontend 当前状态

> 最后更新：2026-09-30（**Data Gate-1：架构决策草案整理**完成，等待 Reviewer）
> 数据状态：**核心业务数据仍全部为 Mock**；已取得 Case A 两份 **2025 级真实培养方案**、
> **D4 已修课程脱敏样本** 与 **D5 教学班侦察样本**（均为认证来源），
> 但**原始材料、逐行记录与 Raw 响应均不进入 public Git**
> 契约状态：**`/schemas/` 与 `/docs/interfaces/` 本轮仍未修改**；
> `DATA_GATE_DECISIONS.md` 中的 **DG-01 – DG-06 全部是草案，尚未批准**

## 当前阶段

**Phase 2B-0：真实数据准备与数据源技术侦察**

```text
2B-0A ✅ 数据规划  →  2B-0B ✅ 公开政策 / 培养方案  →  2B-0B+ ✅ 认证来源培养方案
                   →  2B-0C ✅ 已修课程最小脱敏样本  →  2B-0D ✅ 教学班技术侦察
                   →  Data Gate-1 ← 本轮（架构决策草案：实体边界 + DG-01–DG-06）
                   →  负责人裁决  →  恢复 Phase 2B Integration / Orchestrator
```

- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待真实样本通过 **数据 Gate** 后恢复；
  Phase 1 与 Phase 2A 成果不受影响。

## 2B-0D 侦察结果（Case A：2025级 遥感科学与技术 → 网络空间安全）

| 目标 | 状态 | 说明 |
|---|---|---|
| **D1 政策** | **sufficient for current validation** | **3 项 Confirmed**；4 项 Partial；1 项 Historical；上级通知原文 **Not Found**。**版本链**：2024〔159号〕→2025〔1号〕有正文证据；**2025〔1号〕→2026〔62号〕待确认** |
| **D2 2025级 遥感科学与技术 正式培养方案** | ✅ **Confirmed** | `CURR-OLD-003`（Authenticated Official）：修业年限 **4 年**、毕业总学分 **147.0**、实践教学学分 **37.1** |
| **D3 2025级 网络空间安全 本科正式培养方案** | ✅ **Confirmed** | `CURR-NEW-004`（Authenticated Official）：修业年限 **4 年**、毕业总学分 **153.0**、实践教学学分 **38.5** |
| **D4 已完成课程记录** | ✅ **Confirmed via authenticated private sanitized sample** | `TRANSCRIPT-001`：**24 条**记录，8 个字段覆盖率均 **100%**；Raw 成绩单与逐行脱敏记录**均不在 public Git** |
| **D5 课程开设 / 教学班数据** | ✅ **Confirmed via authenticated private recon sample** | `OFFERING-001`：范围 **2026-1**，**小规模人工侦察**（`CSE202` 返回 **2 个真实教学班**）；**Raw 响应不入库** |

> ⚠️ **原始材料一律不进入 public Git**：培养方案 docx、Raw 成绩单、逐行脱敏课程记录、
> **D5 Raw response** 均不入库；仓库内只保存 `source_id`、来源性质、**汇总事实**与 Schema gap 结论。
> 这些来源均为 **Authenticated Official**，**外部访问者无法通过公开 URL 独立复核**。

**D5 本轮的两个重要发现**：

- **G9（结构缺口）**：**一个教学班可有多个独立的上课时间 / 地点 segment**，
  当前 `CourseOffering` 只能表达一组 `weekday` / `start_section` / `end_section` / `weeks[]` /
  `campus` / `classroom`，**无法在一个对象中无损表达**；最终表示方式**留给 Data Gate**；
- **G7 升级为已验证**：真实 D5 JSON 中确实出现 `openingUnitName` 与 `courseCategoryName`。

> ⚠️ **`remaining_capacity` 不是学校接口直接提供的**：它由 `limitNumber - selectedNumber` **派生**。
> ⚠️ `courseCategoryName`（样本为"专必"）**带培养方案上下文**，**不得**认定为课程全局固有属性。
> ⚠️ `teachProgressSubmitState` / `openClass` / `outlineTypeNum`：**字段存在，业务语义待确认**，**不解释 0/1**。

**Confirmed（7）**：
- `POLICY-001` 中山大学本科生学籍管理规定（中大教务〔2026〕62号），教务部现行收录，2026-08-16
- `POLICY-003` 网络空间安全学院 2026 年本科生转院系专业考核通知，2026-04-20
- `POLICY-008` 中山大学本科生学籍管理规定（中大教务〔2025〕1号），官方站点发布**全文**，2025-04-05
  （**其第三十一条直接规定转专业后的学分认定与成绩转换**）
- **`CURR-OLD-003`** 25级 遥感科学与技术 本科培养方案 —— **Authenticated Official**（中大本科教务系统）
- **`CURR-NEW-004`** 25级 网络空间安全 本科培养方案 —— **Authenticated Official**（中大本科教务系统）
- **`TRANSCRIPT-001`** 已完成课程记录（D4）—— **Authenticated Official**（中大本科教务系统，
  负责人私密侧合并与脱敏；**24 条**记录、8 字段 100% 覆盖）
- **`OFFERING-001`** 课程开设 / 教学班真实样本（D5）—— **Authenticated Official**（中大本科教务系统，
  **小规模人工侦察**；范围 **2026-1**，`CSE202` 返回 **2 个真实教学班**；**Raw 响应不入库**）

**Partial（7）**：`POLICY-002`（转专业实施办法，现行性未确认）、`POLICY-004`、`POLICY-005`、
`POLICY-006`（学分成绩转换操作指南，学院站点发布）、`CURR-OLD-001`（2019 级培养方案）、
`CURR-OLD-002`（专业白皮书，非培养方案）、`CURR-NEW-003`（本科生课程表，非培养方案）

**Not Found（1）**：`CURR-NEW-001`（2025 级网络空间安全本科培养方案）—— **公开搜索**未找到；
**保留为公开搜索历史记录，不删除、不改造成新来源**；认证来源缺口已由 `CURR-NEW-004` 补齐

**Historical（1）**：`POLICY-007`（学籍管理规定〔2022〕52号）—— **较早历史版本**；
其后至少还存在 2024〔159号〕/ 2025〔1号〕/ 2026〔62号〕，
**逐版废止关系尚未全部取得官方正文证据**，**不得**描述为"被〔2026〕62号直接取代"

**不适用（1）**：`CURR-NEW-002`（网络空间安全 0839 **硕士**培养方案，与本科 Case A 无关）

> ⚠️ **总体证据缺口已由认证来源补齐，但公开官网仍然没有。**
> D2 / D3 的 2025 级正式培养方案在**公开搜索**中**仍未找到**
> （`CURR-NEW-001` 的 **Public Not Found 历史继续保留**），
> 现由**认证来源** `CURR-OLD-003` / `CURR-NEW-004` 补齐**总体证据**；
> 本轮**没有**用旧版本、白皮书或研究生方案顶替。

## Data Gate-1 本轮结果（架构决策草案）

新增 `docs/data/DATA_GATE_DECISIONS.md`（**草案，未经批准**）。本轮**不改代码、不改契约**。

**实体边界（7 个概念）**：

| 实体 | 表示 | 关键红线 |
|---|---|---|
| `Course` | 课程基础身份 / 基础属性 | **不承担**学生修读结果，**不承担**培养方案上下文的"专必 / 专选" |
| `CurriculumVersion` | 某专业 / 年级 / 版本的一份培养方案 | 方案级总量与适用年级无处承载（G1） |
| `CurriculumCourse` | 某门 `Course` 在某方案中的**要求** | 承载 `course_type` / 推荐学期 / **课程分组** / 先修 |
| `CompletedCourse` | 某学生**已经修过**某门课的事实 | **`semester` / `passed` 绝不能塞回 `Course`** |
| `CurrentEnrollment` | 学生**当前已选 / 在读**的教学班 | 必须与 `CompletedCourse` / `CourseOffering` / `Preference` 分开；Planner 冲突检测需要它 |
| `CourseOffering` | 某学期的一个教学班（**供给**） | 不等于"学生已选" |
| `ScheduleSegment` / `Meeting` | 教学班内**一段**上课时间 / 地点 | `CourseOffering` 1 — N `ScheduleSegment` |

**核心裁决草案（DG-01 – DG-06，全部待负责人裁决）**：

| 编号 | 主题 | 要点 |
|---|---|---|
| **DG-01** | `CourseOffering` multi-segment（**G9，本轮最重要**） | 给出概念关系、6 项 segment 量、`teacher` 层级结论与 **4 个候选方案**；**明确禁止**"只保存第一段"与"拆成多个可独立选择的 `CourseOffering`" |
| **DG-02** | `CompletedCourse` | 建议正式化"学生修读事实"公共对象；**同时列出"作为 Curriculum 模块内部输入、不进公共契约"这一可行替代方案** |
| **DG-03** | `CurrentEnrollment` | 建议独立对象；**替代方案** = 用现有 `Preference.avoid_times[]` 降级近似（语义不足，需裁决） |
| **DG-04** | `CurriculumVersion` / `CurriculumCourse` | 建议引入；**兼容 / 迁移策略与 `Course.course_type` / `recommended_semester` 的处置待裁决** |
| **DG-05** | Curriculum → Planner 依赖 / 优先级 | **倾向不新增 `DependencyGraph`**（`MakeupTask.prerequisites[]` 可能已足够）；`priority` 只提方向，**字段名 / 类型 / 取值域 / 枚举一律待裁决** |
| **DG-06** | `planner.md` 与 AGENTS 职责冲突 | `docs/interfaces/planner.md` 把"课程依赖图 / 补修优先级与风险"写成 Planner 职责，**与 `/AGENTS.md` 第 5 节冲突** → 登记为**接口文档债务**，本轮**不修改该文件** |

**其他产出**：实体所有者表；**Shared / Private / Derived** 分类（含"用户适用的 `CurriculumVersion` reference 属私有"）；
**暂缓字段分类**（A / B / C / D，见下）；**Course Data 获取边界**链路与红线；
**Data Gate 通过条件 C1–C11**。

**暂不进入公共契约的字段**：

- **B（Course Data 内部即可）**：`selectedNumber`（`remaining_capacity` 用**派生值**即可）、`openingUnitName`、
  `teachingTimePlaceStr`（转换层）、D4 的 `offering_unit`
- **C（当前不进入系统）**：`examMode`（Planner MVP 非必需）、`readObj`（**未来可能影响可选资格，但当前规则不足**）、
  全部内部 ID / 计数（`class_ID` / `courseId` / `outLineId` / `timePlaceId` 等，**不记录取值**）
- **D（语义未知，继续待确认）**：`teachProgressSubmitState`、`openClass`、`outlineTypeNum`、
  `openingSchoolName` / `weekDay`（**与 `campus` / `weekday` 的转换关系待确认**）、D4 的 `cultivation_type`
- **归属转移**：`courseCategoryName`（样本"专必"）→ **培养方案上下文属性**，归 **DG-04**，**不进入 `CourseOffering`**

> ⚠️ **本轮未裁决任何一项**；⚠️ **未修改 `/schemas/`、`/docs/interfaces/`、`AGENTS.md`、`backend/`、`frontend/`、`mock_data/`**；
> ⚠️ **未写 parser / crawler / Adapter / CourseDataProvider / Integration**，**未建数据库**，**未调用 SYSU 接口**（本轮**零请求**）；
> ⚠️ **未自行进入 Data Gate-2**。

## 已完成
- 模块边界和依赖接口已定义
- **前端技术栈已由负责人确认：Vue 3 + TypeScript + Vite**（`/docs/ARCHITECTURE.md` 已同步）
- 后端集成底座可启动：`backend/app/main.py`
- 与 `/schemas/` 一致的 Pydantic 校验层：`backend/app/models/contracts.py`（含 `uniqueItems` 的运行时强制）
- Mock 回放接口：`GET /api/v1/mock/{makeup-tasks, course-offerings, preference, plan-result, demo}`
- 健康检查：`GET /health`（另挂 `/api/v1/health`）
- 启动数据自检：**先按公共 JSON Schema 校验原始 JSON**（不依赖 Pydantic 的类型转换），不合契约时进程直接启动失败
- 后端自动测试：125 passed / 1 skipped（`cd backend && python -m pytest`）
- **前端最小 Demo 壳层已建立**：`frontend/`（Vue 3 + TypeScript + Vite，单页面，原生 CSS）
  - 唯一数据来源：`GET /api/v1/mock/demo`；同源请求，由 Vite 开发/预览服务器代理转发到后端
  - 顶部醒目 Mock 标识，四个区块各有 `Mock` 标记，并显示后端 `X-Data-Source` 实际取值
  - 四个展示区块：补修任务 / 教学班（按课程分组）/ 用户偏好 / 最终方案
  - loading / success / error 三态；请求失败时只报错，**绝不生成替代数据**
- 运行与验收说明：`backend/README.md`、`frontend/README.md`
- **2B-0A 数据获取规划**：`docs/data/` 四份规划文档（已 merge 进 `main`）
- **2B-0B 公开官方材料获取**：新增 `docs/data/SYSU_CASE_A_PUBLIC_EVIDENCE.md`；
  `docs/data/DATA_SOURCE_REGISTRY.md` 登记公开官方来源并新增「证据等级」字段
- **2B-0B+ 认证来源培养方案**：新增 `docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`；
  登记 **`CURR-OLD-003`**（25级 遥感）与 **`CURR-NEW-004`**（25级 网安）两个
  **Authenticated Official** 来源，并新增「访问类型」字段（区分 Public / Authenticated）；
  `REAL_TO_SCHEMA_GAP_REPORT.md` 中 **G1 升级为「已由 Case A 两份 2025 级真实培养方案确认存在」**，
  且 `Course` 字段映射已按真实样本逐项判定 A/B/C
- **2B-0C 已修课程真实样本验证（D4）**：新增 `docs/data/SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md`；
  登记 **`TRANSCRIPT-001`**（**Authenticated Official**，**未创建新的 D4 `source_id`**）；
  `REAL_TO_SCHEMA_GAP_REPORT.md` 新增 **§3.6**（D4 八个字段逐项判定 A/B/C）与 **§4.4**，
  **G2 更新为「已由 Case A 真实 D4 样本验证」**；
  并明确 `semester` **不得**映射到 `recommended_semester`、`passed` **不得**塞入 `Course`、
  `cultivation_type` **不得**当成 `course_type`
- **2B-0D 教学班技术侦察（D5）**：新增 `docs/data/SYSU_COURSE_OFFERING_RECON.md`；
  登记 **`OFFERING-001`**（**Authenticated Official**，**小规模人工侦察**，范围 2026-1）；
  `REAL_TO_SCHEMA_GAP_REPORT.md` 新增 **§3.2**（`CourseOffering` 字段逐项 A/B/C）与 **§4.5**，
  **G7 升级为「已由真实 D5 样本验证」**，并**新增 G9 / G10**；
  明确 **`remaining_capacity` 是派生值**、**`courseCategoryName` 带培养方案上下文**、
  **`teachProgressSubmitState` / `openClass` 语义待确认**；
  **未写 parser、未建库、未写 Adapter、未进入 Integration**
- **Data Gate-1 架构决策草案（本轮）**：新增 `docs/data/DATA_GATE_DECISIONS.md`；
  整理 **7 个核心实体边界**（`Course` / `CurriculumVersion` / `CurriculumCourse` /
  `CompletedCourse` / `CurrentEnrollment` / `CourseOffering` / `ScheduleSegment`）、
  **实体所有者**、**Shared / Private / Derived** 分类、**Course Data 获取边界**与
  **12 条 Data Gate 通过条件**；对 **G9 多 segment** 给出概念关系与 4 个候选方案（含 2 个**被禁止**方案）；
  分析 **Curriculum → Planner 契约**（`prerequisites[]` 是否足够、优先级是否进契约）；
  提交 **DG-01 – DG-06** 六项 `【接口变更请求】`**草案**；
  更新 `docs/data/MEMBER_DATA_HANDOFF.md`（新增"可直接共享 / 按需交接 / 禁止交接"三层清单，
  澄清"已有真实证据 ≠ 已交付逐行数据"，**真实逐行数据交接次数仍为 0**）；
  `REAL_TO_SCHEMA_GAP_REPORT.md` 仅小幅补 **Data Gate 引用**（缺口状态不变）。
  **未修改 Schema / Interface / 代码，未调用 SYSU 接口（本轮零请求），未做任何裁决**

## 当前接口
- 读取：`MakeupTask[]`、`CourseOffering[]`、`Preference`、`PlanResult`（当前来自 Mock）
- 前端唯一数据来源：`GET /api/v1/mock/demo`
- 业务接口统一前缀 `/api/v1`；全部响应带 `X-Data-Source: mock`
- 公共契约真源仍是 `/schemas/*.schema.json`，本轮**未修改**

## 当前使用数据
- **业务数据仍全部为 Mock**：仓库根目录 `/mock_data/`（人工虚构的演示数据）
- 已取得的真实材料包括**公开官方政策 URL / 事实**、**Case A 两份 2025 级真实培养方案的结构化事实**、
  **D4 已修课程脱敏样本的汇总事实（24 条、8 字段 100% 覆盖）**，
  以及 **D5 教学班侦察的字段结构与汇总事实（2026-1，`CSE202` 返回 2 个教学班）**
- **原始培养方案 docx、Raw 成绩单、逐行脱敏课程记录、D5 Raw response 均不进入 public Git**；
  仓库内**不含完整课程表**，也**不含任何具体成绩 / GPA**，**不含教师姓名 / 内部长 ID / 完整逐行记录**
- 这些来源为 **Authenticated Official**：**外部访问者无法通过公开 URL 独立复核**
- 真实数据链路**已取得 D1–D5 全部五类样本**，但**尚未进入产品链路**
- 「当前功能仅使用 Mock 数据验证，尚未完成真实数据验证」

## 当前阻塞
- **D2 / D3 的总体证据缺口已由认证来源补齐**（`CURR-OLD-003` / `CURR-NEW-004`）；
  **公开官网仍未找到对应的 2025 级正式培养方案，Public Not Found 历史继续保留**（`CURR-NEW-001`）。
  剩余限制：**原始材料不入库**，外部访问者无法通过公开 URL 独立复核
- **学籍管理规定版本链待人工确认**：已确认存在 2022〔52号〕/ 2024〔159号〕/ 2025〔1号〕/ 2026〔62号〕；
  其中**仅 2024〔159号〕→2025〔1号〕有正文直接证据**，
  **2025〔1号〕→2026〔62号〕的正式替代关系尚未确认**（本轮未能读到 2026〔62号〕正文）；
  Case A 转专业时点适用哪一版需人工判定。另：转专业实施办法（`POLICY-002`）现行性未确认
- **G9 结构缺口已进入 Data Gate-1，但尚未裁决**：一个教学班可有**多个上课时间 / 地点 segment**，
  当前 `CourseOffering` **无法无损表达**；`DATA_GATE_DECISIONS.md` 已给出概念关系与 4 个候选方案，
  **最终表示方式仍待负责人裁决**（DG-01）
- **DG-01 – DG-06 全部待负责人裁决**：本轮只提交**草案**，**未批准任何一项**，**未修改任何契约**
- **上游 Curriculum / Course Data / Planner 均未产出真实结果**，前端只能展示 Mock
- **集成骨架尚未建立**：上游模块暂时没有正式的接入点
- **五类真实样本已齐备，但尚未通过 Data Gate**：Phase 2B Integration 仍暂停编码
- **接口文档债务**：`docs/interfaces/planner.md` 的职责描述与 `/AGENTS.md` 第 5 节冲突（DG-06），
  本轮**未修改**该文件
- **`prerequisites[]` 尚无真实证据**：真实培养方案样本中**未发现明确的先修字段**，
  该字段"可被真实数据填充"目前**无证据**（不构成"学校无先修制度"的结论）

## 下一步
- **Data Gate-1 完成，等待 Reviewer 验收**
- **Reviewer / 负责人需逐项裁决 DG-01 – DG-06**，并按 `DATA_GATE_DECISIONS.md` 第 12 节
  的 **C1 – C11** 判定是否通过 Data Gate
- 裁决顺序建议（仅供 Reviewer 参考，**不构成本轮结论**）：
  **DG-01（多 segment，P0）→ DG-03（`CurrentEnrollment`，P0）→ DG-02 / DG-04 / DG-05（P1）→ DG-06（P2 文档）**
- ⚠️ **在负责人裁决前不得开始实施**：不得改 `/schemas/` 或 `/docs/interfaces/`、
  不得写 Course Data Adapter / `CourseDataProvider`、不得进入 Integration。
  **不得自行进入 Data Gate-2**，必须等新一轮任务书
- 2B-0 全程遵守 `docs/data/DATA_ACQUISITION_PLAN.md` 的三层数据模型与红线：
  **Raw 不进 Git；D4 的 Raw 与逐行脱敏样本均不得进入 public 仓库；`/mock_data/` 保持人工虚构**
- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待**Data Gate 通过**后恢复
- 比赛 Demo 故事线**不属于当前开发主线**，推迟到后续产品展示阶段再评估
- 在真实 Curriculum / Planner / Course Data 稳定之前，不接 Agent / LLM
