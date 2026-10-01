# Agent / Frontend 当前状态

> 最后更新：2026-10-01（**DG-07A — Contract Migration 已实施、待 Reviewer**：
> `CourseOffering.meetings` 的 `minItems` 已由 **1 → 0**（`required` 不变），
> 前端类型**仅注释**同步、**未改类型形状 / 组件 / 文案**；
> ⛔ **DG-07 整体仍未完成**（DG-07B/C/D 未开始）；**Data Gate 仍保持 Reopened**）
> 数据状态：**核心业务数据仍全部为 Mock**；真实证据（D1–D5）只以**汇总事实**形式入仓，
> **原始材料、逐行记录、Raw 响应、私密脱敏样本、截图与真实 Capture Bundle 均不进入 public Git**
> 契约状态：**`CourseOffering.meetings` = `type: array`、`minItems: 0`**（DG-07A；
> 顶层 `required` 仍含 `meetings`，缺字段 / `null` 非法）；
> **DG-01 时的 `minItems: 1` 已是历史**；**Data Gate 通过条件 C1–C11 全部完成**
> ⚠️ **rollout gate**：`meetings = []` 契约合法，但在 **DG-07B / DG-07C / DG-07D 完成前**，
> 生产真实数据链路**不得**产生或接入 empty-meeting `CourseOffering`；
> `mock_data/` 保持全部非空；**前端尚未支持 empty-meeting 展示**（属 DG-07D）
>
> ⚠️ **准确表述（不得夸大）**：**Provider 边界与 Orchestrator skeleton 已完成**，
> Course Data 的**标准化内核、`teachingTimePlaceStr` parser、本地 import adapter、内部快照、
> 零网络分页采集核心、浏览器端授权采集器代码、Capture Bridge、结构诊断入口
> 与相关性诊断入口**均已完成，且**两个浏览器诊断均已在真实环境执行完成**；
> **已完成一次真实 smoke run + 一次真实结构诊断 + 一次真实相关性诊断 + 一次人工界面最小核验**
> （「全校开设课程」独立模块内 **same-origin 成功**，**认证不再是 blocker**）；
> 第 1 页 **200** 条真实 row 中 **39 条完全没有 `teachingTimePlaceStr`**、
> **161 条非空**，其余形态 0（⚠️ **39/200 只描述第 1 页样本，不得外推**），
> C1C 显示**结构差异集中在排课相关字段**（`limitNumber` / `selectedNumber` 完整存在），
> C1D（**n = 2**）显示两条典型候选在官方 UI 中**均为普通教学班行**、
> 时间 / 周次 / 地点**空白且无状态文字**，
> 当前 `collect()` **按设计 fail closed**，**尚未生成真实 Capture Bundle**、
> **尚未取得 complete semester snapshot**；**G11 仍未 resolved**
> （业务语义部分有界面证据，**契约缺口候选 DG-07 待架构裁决**）；
> **production Curriculum / Planner provider 仍未接入**，
> 因此**没有**任何一条真实数据链路端到端跑通，**也未新增任何 API**。
>
> ⚠️ **导航纠错**：「**选课**」与「**全校开设课程**」是**两个独立模块**。
>
> 详见 `docs/status/course_data.md`。

## 当前阶段

**DG-07A Contract Migration 已实施（待 Reviewer）
→ 下一步：等待 DG-07B / DG-07C / DG-07D 任务书（本模块不自行实施）**

```text
Phase 2B-0 ✅ 真实数据准备与数据源技术侦察（D1–D5）
                   →  Data Gate-1 ✅ 架构裁决
                   →  Data Gate-2 ✅ 契约实施（DG-01 meetings[] + DG-06 接口文档）
                   →  ✅ Data Gate PASSED / CLOSED
                   →  Phase 2B-1 ✅ Integration / Provider Skeleton（Provider 边界 + Orchestrator）
                   →  Phase 2B-2A ✅ Course Data Normalization Core（字段映射 + 快照 + Provider 落点）
                   →  Phase 2B-2B ✅ Schedule Parser + Local Import Adapter（纯本地、零网络）
                   →  Phase 2B-2C0 ✅ Pagination Core（零网络分页采集 + completeness 证据链）
                   →  ✅ SYSU 分页参数人工验证完成（first_page_no=1、单页上限 200、前两页 total=6892）
                   →  Phase 2B-2C1A ✅ 浏览器端授权采集器代码 + Capture Bridge
                   →  ✅ 真实 smoke run：same-origin 成功、认证不再是 blocker
                   →  Phase 2B-2C1B ✅ 结构诊断入口 + 负责人真实运行
                      第 1 页 200 条：39 missing / 161 非空 / 其余 0（仅第 1 页，不得外推）
                   →  Phase 2B-2C1C ✅ 相关性诊断入口 + Reviewer 批准并 merge
                      + 负责人真实运行 + 真实聚合结果已回填
                      （结构差异集中在排课相关字段）
                   →  Phase 2B-2C1D ✅ 人工界面最小核验（n = 2，负责人本人完成）
                      两条候选在官方 UI 中均为普通教学班行、时间区域空白、无状态文字
                   →  ⚠️  Data Gate Reopened narrowly for DG-07 only（仍保持 Reopened）
                   →  ✅  DG-07 APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING
                   →  ✅  DG-07A — Contract Migration 已实施（待 Reviewer）
                      meetings minItems 1 → 0（required 不变）；接口语义 + 契约级测试已同步；
                      前端仅注释同步
                   →  ⏳  待办：DG-07B（Course Data）/ DG-07C（Planner safety）/
                      DG-07D（Frontend 展示）—— **本轮不开始**
                   →  之后：真实 Capture 导入 UI → Phase 2B Integration 接真实 Provider
```

- **Phase 1 / Phase 2A 成果不受影响**；`/api/v1/mock/*` 仍是独立的**永久 Mock 通道**。

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

## Data Gate-1 结果（架构决策草案 + 架构裁决落档）

新增 `docs/data/DATA_GATE_DECISIONS.md`。**Architecture Lead 已完成 DG-01 – DG-06 裁决**；
**公共契约尚未实施** —— 本轮**不改代码、不改契约**。

**实体边界（7 个概念）**：

| 实体 | 表示 | 关键红线 | 裁决后落地形态 |
|---|---|---|---|
| `Course` | 课程基础身份 / 基础属性 | **不承担**学生修读结果，**不承担**培养方案上下文的"专必 / 专选" | 保持公共契约 |
| `CurriculumVersion` | 某专业 / 年级 / 版本的一份培养方案 | 方案级总量与适用年级无处承载（G1） | **Curriculum 内部**（DG-04） |
| `CurriculumCourse` | 某门 `Course` 在某方案中的**要求** | 承载 `course_type` / 推荐学期 / **课程分组** / 先修 | **Curriculum 内部**（DG-04） |
| `CompletedCourse` | 某学生**已经修过**某门课的事实 | **`semester` / `passed` 绝不能塞回 `Course`** | **Curriculum 内部规范化对象**（DG-02） |
| `CurrentEnrollment` | 学生**当前已选 / 在读**的教学班 | 必须与 `CompletedCourse` / `CourseOffering` / `Preference` 分开；Planner 冲突检测需要它 | **不新增 Schema**；`current_schedule` 复用 `CourseOffering[]`（DG-03） |
| `CourseOffering` | 某学期的一个教学班（**供给**） | 不等于"学生已选" | **改为承载 `meetings[]`**（DG-01） |
| `ScheduleSegment` / `Meeting` | 教学班内**一段**上课时间 / 地点 | `CourseOffering` 1 — N `Meeting` | **进入公共契约**（DG-01） |

**六项裁决（Architecture Lead，2026-09-30）**：

| 编号 | 主题 | 裁决 |
|---|---|---|
| **DG-01** | `CourseOffering` multi-segment（**G9，最重要**） | **APPROVED WITH MODIFICATION** —— 采用**嵌套 `meetings[]`（方案 A）**；`CourseOffering` 1 — N `Meeting`；每段 = `weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom`；`teacher` 暂留**教学班级**（汇总 / 展示）；**方案 B / C / D 转为"已评估但驳回"**；**Data Gate-2 正式改契约**；仍**明确禁止**"只保存第一段"与"拆成多个可独立选择的 `CourseOffering`" |
| **DG-02** | `CompletedCourse` | **DEFER PUBLIC CONTRACT** —— 概念成立，**MVP 不新增公共 Schema**，作为 **Curriculum 内部规范化对象**；D4 Sanitized Sample 由负责人经**非公开位置**交 Curriculum；对外**仍只输出 `MakeupTask[]`** |
| **DG-03** | `CurrentEnrollment` | **APPROVE CONCEPT, REUSE EXISTING CONTRACT** —— **不新增 Schema**；Planner 的 `current_schedule` **直接使用 `CourseOffering[]`**，语义 = 学生已选中的教学班子集；⛔ **不得用 `Preference.avoid_times[]` 冒充当前课表** |
| **DG-04** | `CurriculumVersion` / `CurriculumCourse` | **DEFER PUBLIC CONTRACT** —— **MVP 暂留 Curriculum 内部模型**，不新增两个公共 Schema；`Course.course_type` / `recommended_semester` 是**现有兼容字段**，**不得被解释为课程全局固有属性**；跨学期区间由 Curriculum 内部结构保留 |
| **DG-05** | dependency / priority | **NO NEW PUBLIC CONTRACT FOR MVP** —— 不新增 `DependencyGraph` / `priority` / `PriorityResult`；**Curriculum 认定并产出 dependency edges**，Planner 只能把已收到的 `prerequisites[]` 转成**本地** adjacency / topology，**不得新增 / 猜测 / 重写 edge**；**无正式 priority 时 Planner 不得自行生成优先级** |
| **DG-06** | `planner.md` 与 AGENTS 职责冲突 | **APPROVED** —— Data Gate-2 修正 `docs/interfaces/planner.md`，必要时同步 `curriculum.md`；本轮**仍不改 interfaces** |

> **进入 Data Gate-2 实施的契约变更只有 2 项**：**DG-01**（`course_offering.schema.json`，
> **有意的 breaking migration**）与 **DG-06**（接口文档修正）。
> **DG-02 / DG-03 / DG-04 / DG-05 本阶段均不产生公共契约变更。**

**其他产出**：实体所有者表；**Shared / Private / Derived** 分类（含"用户适用的 `CurriculumVersion` reference 属私有"）；
**暂缓字段分类**（A / B / C / D，见下）；**Course Data 获取边界**链路与红线；
**Data Gate 通过条件 11 条（C1–C11）**。

**暂不进入公共契约的字段**：

- **B（Course Data 内部即可）**：`selectedNumber`（`remaining_capacity` 用**派生值**即可）、`openingUnitName`、
  `teachingTimePlaceStr`（转换层）、D4 的 `offering_unit`
- **C（当前不进入系统）**：`examMode`（Planner MVP 非必需）、`readObj`（**未来可能影响可选资格，但当前规则不足**）、
  全部内部 ID / 计数（`class_ID` / `courseId` / `outLineId` / `timePlaceId` 等，**不记录取值**）
- **D（语义未知，继续待确认）**：`teachProgressSubmitState`、`openClass`、`outlineTypeNum`、
  `openingSchoolName` / `weekDay`（**与 `campus` / `weekday` 的转换关系待确认**）、D4 的 `cultivation_type`
- **归属转移**：`courseCategoryName`（样本"专必"）→ **培养方案上下文属性**，随 DG-04 暂留 **Curriculum 内部模型**，
  **不进入 `CourseOffering`**

> ⚠️ **本轮已落档裁决，但未实施任何一项**（契约实施在 **Data Gate-2**）；
> ⚠️ **未修改 `/schemas/`、`/docs/interfaces/`、`AGENTS.md`、`backend/`、`frontend/`、`mock_data/`**；
> ⚠️ **未写 parser / crawler / Adapter / CourseDataProvider / Integration**，**未建数据库**，**未调用 SYSU 接口**（本轮**零请求**）；
> ⚠️ **未自行进入 Data Gate-2**。

> **本轮 Reviewer 修复的 3 处**：① **教师证据修正** —— 删除"没有证据表明教师有 meeting-level 语义"，
> 改为"**meeting-level teacher association = 已知真实语义**，但 Planner MVP 不依赖它"，
> 登记为 **known deferred representation gap**；② **DG-05 权威边界表述改精确**（Curriculum 认定 / 产出 edges，
> Planner 只做本地转换，**不得新增 / 猜测 / 重写 edge**）；③ **通过条件计数由"12 条"更正为 11 条（C1–C11）**。

### Data Gate-1 最终同步（架构内容已通过 Reviewer）

**① §5.1 隐私措辞收紧（School-shared）**

- ❌ 删除过强表述"来源为学校侧，**不含个人身份信息**，原则上可跨成员共享"；
- ✅ 改为：**School-shared = "可在同一学校用户场景中复用的学校侧数据"**，
  **不代表天然不含人员信息，也不代表可以公开发布**；
- ✅ 明确 `CourseOffering` 等数据**可能包含教师等人员信息**；
  Real / Raw 仍须遵守**数据最小化、来源授权、非公开处理**；
  **"是否 School-shared" 与 "是否可以公开"是两个独立问题**；
- ⚠️ **不得把教师信息归为 Student-private**（教师信息属学校侧，但同样不得进 public 仓库）。

**② C9 裁决已写入 §11.3（目标与获取边界）**

- **目标**：**2026-1 semester offering snapshot**；
- **边界**：本人正常登录 / 已有权限 / **用户明确触发授权导入** /
  ⛔ 不保存密码·Cookie·Session·Token / ⛔ 不绕过认证·CAPTCHA / ⛔ 不越权 /
  ⛔ **未确认请求规模前不高频批量调用**；
- **分工**：Course Data = 获取·导入 → 解析 → 标准化 → 去重 → `source` / `data_source` → snapshot；
  Integration = **只经 `CourseDataProvider`**，不知道 SYSU endpoint / Cookie / pagination；
  Planner = **只消费标准化 `CourseOffering[]`**；
- ⚠️ 批量导入**必须先确认合理 `pageSize` / 请求规模**；
- ⚠️ **completeness 纪律**：「目标是一学期完整 Snapshot」**≠**「当前已取得完整数据」（当前只有 2 个教学班的侦察样本）；
  **若只能取得部分范围，必须显式记录 completeness，不得把 partial snapshot 宣称为 complete**。

**③ 通过条件 C1–C11 状态同步**

| 条件 | 状态 |
|---|---|
| C1 裁决完成 | ✅ 已确认 |
| **C2 实体边界与所有者** | ✅ **已确认** |
| **C3 Shared / Private / Derived 分类** | ✅ **已确认**（含 §5.1 措辞修正） |
| C4 多 segment 表示方式 | ✅ 已确定（`meetings[]`；Data Gate-2 实施） |
| **C5 契约变更流程** | ⏳ **唯一未完成项**（Data Gate-2 执行） |
| C6 暂缓字段清单 | ✅ 已确认 |
| C7 Curriculum → Planner 契约 | ✅ 已确定 |
| C8 接口文档债务修正决定 | ✅ 已批准（Data Gate-2 执行） |
| **C9 Course Data 获取边界与合规方向** | ✅ **已确认**（见 §11.3） |
| **C10 数据交接方式** | ✅ **已确认**；**真实逐行数据交接次数 = 0（不变）** |
| **C11 已知未覆盖字段风险** | ✅ **已确认**：`prerequisites[]` **暂无真实来源证据**、`weekDay` 对应关系**待确认**、`openingSchoolName → campus` **待确认**、**meeting-level teacher = known deferred representation gap**；⛔ **不允许实现层自行补齐** |

**④ `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` 状态同步（仅状态，不改历史分析）**

- §4.5 引用块与变更记录中的 `DATA_GATE_DECISIONS.md`（**草案，未经批准**）
  → 改为「**Data Gate-1 架构裁决已完成；公共契约尚未实施，实施进入 Data Gate-2**」；
- **G1–G10 的历史分析与 A/B/C 映射结论一字未改**。

## Data Gate-2 实施结果（契约已变更 → Data Gate CLOSED）

**本轮是真正的契约实施轮**，不是文档轮。两项裁决均已落地。

### DG-01：`CourseOffering` → 1 — N `meetings[]`（breaking migration，已实施）

| 项 | 结果 |
|---|---|
| **契约真源** | `schemas/course_offering.schema.json` 已改写 |
| **顶层删除** | `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom`（**彻底移除**） |
| **顶层 `required`** | `course_id` / `course_name` / `class_id` / `semester` / **`meetings`** |
| **`meetings`** | `type: array`，`minItems: 1`（**DG-01 当时**；**DG-07A 起为 `minItems: 0`**） |
| **`Meeting` 必填** | `weekday`(1–7) / `start_section`(≥1) / `end_section`(≥1) / `weeks[]`(`minItems:1`, `uniqueItems`) |
| **`Meeting` 可选** | `campus` / `classroom` |
| **未新增** | `selectedNumber` / `openingUnitName` / `courseCategoryName` / `examMode` / `readObj` / `teachProgressSubmitState` / `openClass` / **`meeting.teacher`** |
| **表达损失** | **meeting 级教师关联仍为 known deferred representation gap**；`teacher` 留在教学班顶层 |

- **后端**：`backend/app/models/contracts.py` 新增 `Meeting`（`__all__` 同步）；
  `CourseOffering.meetings: list[Meeting]` **DG-01 当时为至少 1 项**（**DG-07A 起为 `min_length=0`**）；
  `weeks` 的 `uniqueItems` 仍由运行时真实拒绝重复项；
  预览旧结构被 Schema 与 Pydantic **双重拒绝**。
- **Mock**：`mock_data/course_offerings.json` **9 个教学班**全部迁移，
  其中 **1 个教学班含 2 段 meeting**（第二段为**人工构造的 Mock**，
  未复制真实 SYSU 响应或真实教师信息）。
- **测试**：`backend/tests/test_contracts.py`、`test_mock_data_schema.py` 已迁移并**加严** ——
  所有时间 / 地点 / 周次 / 节次检查改为**逐 meeting 遍历**（不再只看第一段），
  并新增：旧格式拒绝、`Meeting` 额外字段拒绝、
  `meetings[].weeks` 的 `uniqueItems` 单独锁定、Mock 至少 1 个多 meeting 教学班。
  （**当时**新增的"`meetings: []` 拒绝"用例已由 **DG-07A 翻转**为"必须通过"，见下。）
- **前端**：`types/contracts.ts` 新增 `Meeting`；`CourseOfferingList.vue` 把原来的
  上课时间 / 节次 / 周次 / 校区教室四列**收敛为"上课安排"一列并逐段展示**；
  `utils/labels.ts` 新增**纯展示**函数 `formatMeetingLine`（无任何业务判断）。

### DG-06：接口职责文档已修正（已实施）

- `docs/interfaces/planner.md`：Planner 职责改为冲突检测 / 当前课表冲突分析 / 替代教学班搜索 /
  硬软约束建模 / 确定性求解 / Path Repair / 无解处理 / `PlanResult`；
  **删除** `build_dependency_graph(courses)` 与 `calculate_priority(...)`；
  写明 `current_schedule: CourseOffering[]` 的语义、**"学校全部供给 ≠ 学生已选子集"**、
  依赖与优先级的权威边界、以及**冲突检测必须遍历全部 `meetings`**。
- `docs/interfaces/curriculum.md`：补上**课程依赖认定**、**补修风险 / 学业优先级的所有权**、
  **跨学期补修路径建议**；明确**优先级当前没有公共契约**，**不得假装可以跨模块传 priority**。

### 验证结果

```text
cd backend  && python -m pytest   →  133 passed / 2 skipped（全部通过）
cd frontend && npm run build      →  成功（含 vue-tsc --noEmit 类型检查）
```

两种原先的跳过仍然保留原语义，且**未通过删测试 / skip / 放宽校验来"让 CI 通过"**；
`meetings[].weeks` 的 `uniqueItems` 另有专项用例锁定（因为它嵌套在数组元素里，
顶层扫描会漏掉）。

### Data Gate 结论

```text
C1 ✅  C2 ✅  C3 ✅  C4 ✅  C5 ✅  C6 ✅
C7 ✅  C8 ✅  C9 ✅  C10 ✅  C11 ✅      →  Data Gate PASSED / CLOSED
```

- **G9 更新为「已通过 DG-01 / Data Gate-2 完成公共契约修复」**；
  `REAL_TO_SCHEMA_GAP_REPORT.md` 中**原缺口描述（一个教学班无法表达多 segment）原样保留**；
- **仅 DG-01 与 DG-06 产生契约变更**；DG-02 / DG-03 / DG-04 / DG-05 按裁决**不产生**契约变更。

## Phase 2B-1 结果（Integration / Provider Skeleton）

**只做"插座"，不接真实数据、不写业务算法、不新增用户可见功能。**

| 产出 | 内容 |
|---|---|
| `backend/app/integration/ports.py` | 三个 `typing.Protocol`：`CurriculumProvider.get_makeup_tasks()`、`CourseDataProvider.get_course_offerings(semester)`、`PlannerProvider.plan(*, makeup_tasks, offerings, current_schedule, preference)` |
| `backend/app/integration/orchestrator.py` | `@dataclass(frozen=True) PlanningOrchestrator`，只持有三个 Provider；`build_plan(*, semester, current_schedule, preference)` 按 **Curriculum → Course Data → Planner** 固定顺序调用并**原样**返回 `PlanResult` |
| `backend/tests/test_integration_orchestrator.py` | 14 个测试，全部使用 **test-only Fake / Spy Provider** |
| `docs/interfaces/integration.md` | 编排接口说明（职责 / 三个 Provider / 调用顺序 / `current_schedule` 语义 / dependency-priority 边界 / 错误处理 / 不 fallback / 尚无真实 API） |

**关键约束（已落地并有测试锁定）**：

- Orchestrator **不含任何业务判断**：不排序、不筛选、不补默认值、不改写 `PlanResult`；
  `makeup_tasks` / `offerings` / `current_schedule` / `preference` 按**对象身份**原样到达 Planner；
- `semester` **原样**传给 Course Data（不改写、不规整）；
- `current_schedule=[]` 合法，可继续下传，Integration 不自行报错；
- `offerings=[]` 原样交给 Planner，**是否 `infeasible` 由 Planner 决定**；
- Provider 异常**原样向上抛**：**不吞、不 fallback、不切 Mock**（AST 检查锁定 Integration 层不引用 `mock_service`）；
- **不新增 API**：路由集合与 Phase 1 完全一致（有测试断言 OpenAPI `paths` 未变化）；
- **不创建生产 Mock Provider**（`MockCurriculumProvider` / `MockCourseDataProvider` / `MockPlannerProvider` **均未创建**）；
- **未新增公共业务 Schema / 跨模块 DTO**：只使用 `MakeupTask[]` / `CourseOffering[]` / `Preference` / `PlanResult` / `semester: str`；
  但**新增了 Integration Provider 公共接口边界** —— `docs/interfaces/integration.md` 位于 `/docs/interfaces/`，
  与 `ports.py` / `orchestrator.py` 的四个调用签名**同属公共跨模块接口**，
  **后续模块不得自行修改方法名 / 参数语义 / 返回类型**（变更须走 `【接口变更请求】`）。

**DG-05 旧口径已修正**：`docs/ARCHITECTURE.md` 不再写"Planner 实际消费补修任务 + 课程依赖结果 + 已确认优先级"，
改为 **MVP 当前跨模块只传 `MakeupTask[]`**、prerequisite 由 `MakeupTask.prerequisites[]` 承载、
**`priority` 当前没有公共契约**。

## Phase 2B-2A 结果（Course Data Normalization Core）

**纯本地、零网络**：只实现"已确认字段 → `CourseOffering` → 带 completeness 的内部快照 → Provider 落点"。
**未抓数据、未猜未确认字段格式、未改公共契约。** 详见 `docs/status/course_data.md`。

| 产出 | 内容 |
|---|---|
| `backend/app/course_data/errors.py` | `CourseDataNormalizationError(ValueError)`（单一异常） |
| `backend/app/course_data/normalization.py` | `build_course_offering(raw, *, meetings, source)`、`expand_weeks(text)` |
| `backend/app/course_data/snapshot.py` | `OfferingSnapshot`（`partial` / `complete`）、`SnapshotCourseDataProvider` |
| `backend/tests/test_course_data_{normalization,snapshot}.py` | 99 个测试 |

**关键约束**：

- 只映射已确认真实存在的字段（`courseNum` / `courseName` / `classNumber` / `yearTerm` /
  `score` / `teachingName` / `limitNumber` / `selectedNumber`）；
  **`remaining_capacity` 是 `limitNumber - selectedNumber` 的派生值**，不是接口直接给的；
- **证据边界（实现能力不得超过真实证据）**：`score` **只接受字符串数字**
  （⛔ 数值型 `3` / `3.0` 尚无真实来源证据，当前拒绝）；
  **周次当前仅接受已经观察到的两个具体取值：`1-17周` / `1-17单周`**；
  **其它范围即使形状相似、即使满足 `start < end`，也暂时拒绝**
  （`3-4周`、`3-15单周`、`3-3周`、`2-18周` 等均拒绝；双周 / 组合 / 单个周次号同样拒绝）；
  `selectedNumber` 是 **narrow normalizer 基于已观察 D5 字段**要求的必要字段，
  **不代表"SYSU 所有记录必然都有它"** —— 若后续真实脱敏样本出现缺失，再据实调整内部实现；
- ⛔ **不映射**内部 ID（`courseId` ≠ `course_id`、`class_ID` ≠ `class_id`）与全部暂缓字段；
- ⛔ **不做** `weekDay → weekday`、`openingSchoolName → campus`（C11 待确认）；
- ⛔ **不解析 `teachingTimePlaceStr`**（缺真实脱敏 Raw string，不猜分隔符）；`meetings` 只能由已解析的 `Meeting` 传入；
- completeness 落代码：`complete` 必须 `reported_total == loaded_count`，
  否则不能声称完整快照（C9）；重复 `(semester, course_id, class_id)` 即失败；
- `SnapshotCourseDataProvider` **结构上满足**已冻结的 `CourseDataProvider`（不继承、不修改），
  **零网络、无 Mock fallback**；另有代码边界检查锁定该包不导入网络 / 抓取 / Mock 回放依赖；
- **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/ports.py`、`orchestrator.py` 均未修改；
  后端 **246 passed / 2 skipped**。

## Phase 2B-2B 结果（Schedule Parser + Local Import Adapter）

**纯本地、零网络**：依据负责人单独提供的**私密脱敏样本**（Sanitized Sample，**未进入 Git**）
实现 `teachingTimePlaceStr` parser 与 Raw-response import adapter。详见 `docs/status/course_data.md`。

| 产出 | 内容 |
|---|---|
| `backend/app/course_data/schedule_parser.py` | `parse_teaching_time_place()`、`ParsedScheduleSegment`、`extract_meetings()`、`parse_weekday()`、`parse_sections()` |
| `backend/app/course_data/importer.py` | `import_opening_courses_response(payload, *, semester, source, completeness)` |
| `backend/app/course_data/normalization.py` | `expand_weeks()` 依据新证据扩到 `N-M周`（`N ≥ 1`、`M ≥ N`，含 `M == N`） |
| `backend/tests/test_course_data_{schedule_parser,importer}.py` | 新增测试 |

**关键边界**：

- segment 分隔符 `,`、字段分隔符 `/`；无地点 **5 字段** / 有地点 **6 字段**；
  **最多一个**末尾逗号（单个忽略、多个失败）、**中间空段失败**；
- ⛔ **`weekday` 只来自 segment 自身**（`星期一`…`星期日`）；Raw `weekDay` **完全不使用**（样本显示其顺序不可安全假设）；
- 节次 `第N-M节`，**允许 `M == N`**（`第4-4节`）；
- 地点只按**第一个 `-`** 切；⛔ **`openingSchoolName` 不是 `campus` 的 fallback**；
- **teacher / activity 内部保留**（`ParsedScheduleSegment`），⛔ **未修改任何 Schema**（仍是 deferred gap）；
- importer **任意一行失败即整体失败**（不 fallback / 不重试 / 不跳过坏 row）；
  **completeness 由调用方给出**，adapter 不因 `len(rows) == total` 自称 complete；
  semester 一致性 / real-only / duplicate key / completeness **全部交由 `OfferingSnapshot`**；
- 错误信息**不回显** Raw 串或其中任何字段取值；**包内仍零网络**（边界测试自动覆盖新增文件）；
- **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/`、`main.py`、`api/` 均未修改；
  后端 **366 passed / 2 skipped**。

## Phase 2B-2C0 结果（Course Data Pagination Core）

**零网络**分页采集核心：把多页 Raw 逐页交给**已审核通过的** importer 标准化，
再按**证据链**判定最终 `completeness`。详见 `docs/status/course_data.md`。

| 产出 | 内容 |
|---|---|
| `backend/app/course_data/pagination.py` | `OpeningCoursesPageFetcher`（**内部** Protocol）+ `collect_opening_courses_snapshot()` |
| `backend/tests/test_course_data_pagination.py` | 54 个测试（全部使用测试内 Fake Fetcher） |

**关键边界**：

- `fetch_page` **由调用方提供**，本轮**只由测试 Fake 提供**；⛔ **不实现真实 HTTP**，⛔ 不并发、⛔ 不预取下一页；
- 逐页**复用** `import_opening_courses_response(..., completeness="partial")`，**不重写** parser / normalizer；
- `expected_total` 取第一页的 `reported_total`；后续每页**必须完全相等**（⛔ 不采用最新 / 最大 / 最小值）；
- **complete 证据链**：所有页成功解析 + 每页 total 一致 + 累计 `== total` + 无重复教学班 + 无中途空页 + 无请求错误；
- **partial**：达到 `max_pages`（**安全阀**）仍未取满 → `partial`，并如实记录 `reported_total`；
- 提前空页 / 累计超限 / 跨页重复 → **FAIL**；fetcher 异常与解析失败**原样向上抛**（⛔ 不 retry / fallback / 跳页）；
- 分页器**不自行去重**，重复判定交给 `OfferingSnapshot`；按**原页序 + 原行序**累积；
- 分页参数**无默认值**（核心与具体学校无关），且**不假定 `page_no` 从 1 开始**（`first_page_no=0` 按 0,1,2 调用）；
  SYSU 的实际取值属**后续 Transport 配置**，**不硬编码进核心**；
- ⛔ **`partial` 不得接入 Integration / Planner**（有测试锁定分页核心不导入 / 不构造 Provider）；
- **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/`、`main.py`、`api/` 均未修改；
  后端 **420 passed / 2 skipped**。

### SYSU 分页参数人工验证（已完成）

| 项 | 已验证结果 |
|---|---|
| `pageNo=1` | 请求成功（`code=200`，`total=6892`） |
| `pageNo=2` | 请求成功（`code=200`，`total=6892`） |
| `pageSize=200` | 请求成功；负责人确认 **SYSU 单页最大支持 200** |
| `total` 稳定性 | **已验证前两页** `total` 均为 **6892** |

> ⚠️ **仅覆盖已验证的前两页**，不代表整学期分页已跑完；
> ⚠️ 本次**未单独记录** `rows.length`，因此**不声称**已确认每页满 200 行；
> ⚠️ `max_pages` 是**内部安全阀**，**不是**学校侧参数，无需人工验证。

## Phase 2B-2C1B 结果（Schedule Presence Diagnostic）

**只取证、不裁决**：在**现有**采集器内新增显式触发的结构诊断入口。详见 `docs/status/course_data.md`。

| 产出 | 内容 |
|---|---|
| `tools/sysu_course_offering_collector.js` | 新增 `diagnoseSchedulePresence({ semester })` 与纯函数 `summarizeSchedulePresence(rows)` |
| `backend/tests/test_sysu_collector_guard.py` | 新增诊断相关静态守卫 |

**关键边界**：

- ⛔ **加载脚本仍不自动请求**；诊断必须由用户显式调用；
- **固定只取第 1 页一次**：`pageNo = 1`、`pageSize = 200`、`total = true`；⛔ 无 `maxPages` /
  `firstPageNo` / 循环 / 重试 / 并发；**复用**既有 hostname guard 与取页函数（不复制认证逻辑）；
- **只返回聚合统计**：`semester` / `page_no` / `page_size` / `reported_total` /
  `total_rows`（= `data.rows.length`）/ `teachingTimePlaceStr{missing, null, empty_string,
  non_empty_string, other_type}`；五类之和 == `total_rows`；
- ⛔ **不含** Raw row、row 下标、课程号 / 课程名 / 教学班号 / 教师 / 教室 / 原文 / 内部 ID；
- ⛔ **不生成 Capture Bundle**、不做字段最小化、不做教师脱敏、不调用 `toJson`；
- ⛔ **不改** `collect()` 的 fail-closed 行为（缺字段仍整体失败，不跳过 / 不补空 / 不造占位 `Meeting`）；
- ⛔ **本轮不改契约**：`CourseOffering.meetings` `minItems = 1` 保持不变；**G11 只登记、不裁决**；
- **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/`、`main.py`、`api/`、`frontend/` 均未修改；
  后端 **524 passed / 2 skipped**。

**Reviewer 修复（2026-10-01，本阶段 6 项）**：

- 真实结构 smoke **登记为 `OFFERING-002`**（`DATA_SOURCE_REGISTRY.md`；只登记汇总事实、无 Raw row）；
- 删除**不成立的精确条数**表述（原写作"第 1 页第 N 条"，来自 JS 0-based 下标）→ 统一为"**第 1 页至少 1 条** row 缺少
  `teachingTimePlaceStr`"（**只登记"至少 1 条"**）；**G11** 补 **样本出处 `OFFERING-002`**；
  缺口报告表头补 `Phase 2B-2C1B 真实 smoke 结构证据`；
- **错误信息行号口径 = 1-based**：`collect()` 调用点 `minimizeRow(row, currentPageNo, rowIndex + 1)`
  （`map` 的 0-based 下标 + 1），`minimizeRow` / `redactTeachingTimePlace` / `redactSegmentTeacher`
  第三参数统一为 `humanRowNo` 并写入 JSDoc（**只用于错误信息**）；
  ⛔ **未改** fail-closed、字段检查、数据行为、诊断统计；⛔ 未改任何契约 / 前端产品 UI；
- 新增守卫：`test_collector_reports_one_based_human_row_numbers`、
  `test_collector_row_number_is_only_for_messages`；回归 **524 passed / 2 skipped**、
  `node --check` exit 0；**实际 SYSU 请求数：0**。

## Phase 2B-2C1C 结果（Missing Schedule Correlation Diagnostic）

**只取证、不裁决**：在**现有**采集器内新增显式触发的**相关性诊断**入口。
详见 `docs/status/course_data.md`。

| 产出 | 内容 |
|---|---|
| `tools/sysu_course_offering_collector.js` | 新增 `diagnoseMissingScheduleCorrelation({ semester })`；字段级 summarizer `classifySchedulePresence` / `summarizeFieldShape` / `summarizeCategoricalValues` 为**内部实现，不暴露** |
| `backend/tests/test_sysu_collector_guard.py` | 新增 C1C 静态守卫（15 条） |
| `docs/data/DATA_SOURCE_REGISTRY.md` | `OFFERING-002` 补录第 1 页真实聚合证据（`missing 39` / `non_empty_string 161`，其余 0；**仅第 1 页**）与 **C1C 相关性聚合结果** |
| `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` | G11 / §4.7 补录聚合证据 + 未确认清单；**§4.7.1** 记录 C1C 真实相关性诊断结果 |

**唯一目标**：在第 1 页同一份样本内，对 `missing` 组与 `non_empty_string` 组做
**已有真实字段**的**聚合结构对照**，判断"缺字段的 row 是否表现出一致的结构特征"。
⛔ **不判断业务含义**；⛔ **不是 workaround**。

**关键边界**：

- ⛔ **加载脚本仍不自动请求**；诊断必须由用户显式调用；
- **固定只取第 1 页一次**（`pageNo = 1` / `pageSize = 200`）；⛔ 无分页循环 / 重试 / 并发 /
  第二次请求 / 不复制 `fetch()`；**复用**既有 hostname guard 与 `requestPage()`；
- **参数为严格白名单**：`Object.keys(opts)` 中**只允许** `semester`；任何其它 own key
  （`pageSize` / `pageNo` / `firstPageNo` / `maxPages` / `delayMs` / `retry`，以及任意未知字段）
  都在**发请求之前** fail closed（⛔ 不是"已知参数黑名单"；⛔ 不回显调用方键名）；
- **暴露面收口**：C1C 只暴露 `diagnoseMissingScheduleCorrelation`；
  `summarizeCategoricalValues` 这类**任意字段**的 generic summarizer
  **不得**出现在 `window.XuehangSysuCollector`（否则可绕过字段 allowlist）；
- **分组**：`schedule_presence` 保留**五桶**；只比较 `missing` 与 `non_empty_string`；
  `ungrouped_rows`（`null` + `empty_string` + `other_type`）**保留但不并入任何一组**；
- **A 类字段（Structural-only）只做存在性 / 类型统计**
  （`timePlaceId` / `limitNumber` / `selectedNumber`）：⛔ **不返回具体值**、无 value 列表；
- **B 类字段（Categorical）做有限分类值计数**（`weekDay` / `openClass` /
  `teachProgressSubmitState` / `courseCategoryName` / `examMode` / `openingUnitName`）：
  值**序列化为字符串 + 保留原始类型**（`{ type, value, count }`），
  `missing` / `null` / `empty_string` / `other_type` 单独归类；
- **返回内容口径（⚠️ 不是"只有计数"）**：⛔ **不返回** Raw row / 逐行数据 /
  课程与教学班标识 / 教师 / 教室 / `teachingTimePlaceStr` 原文；
  **Structural-only 字段不返回具体值**；
  **Categorical 字段 `distinct <= 20` 时会返回聚合后的原始标量分类值 + `count`**；
  **`distinct > 20` 时 `values` 全部 suppression**；
- **高基数安全阀** `MAX_DISTINCT_VALUES = 20`：⛔ 不返回前 N / 随机 N / 最常见 N 个；
- **计数不变量在代码中显式校验**（五桶之和、两组之和、`compared_rows + ungrouped_rows`、
  每字段加总）：⛔ **任一不成立即整体失败，不静默丢 row**；
- ⛔ **不生成 Capture Bundle**、不落盘、不写浏览器存储、不调用 `toJson`；
- ⛔ **不改** `collect()` 的 fail-closed 行为；⛔ **不改** 2B-2C1B 的 `diagnoseSchedulePresence()`；
- ⛔ **本轮不改契约**：`CourseOffering.meetings` `minItems = 1` 保持不变；**G11 只登记、不裁决**；
- **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/`、`main.py`、`api/`、
  `frontend/`、`backend/app/course_data/*.py` 均未修改；后端 **539 passed / 2 skipped**；
- ✅ **已在真实环境执行完成**（**负责人手动执行**，Builder 未发起任何请求）：
  - `total_rows = 200`、`compared_rows = 200`、`ungrouped_rows = 0`；
  - **结构差异集中在排课相关字段**：`timePlaceId` 在 `missing` 组 38/39 缺失、
    在 `non_empty_string` 组 161/161 存在；`weekDay` 38/39 缺失 vs 12/161 缺失；
  - `limitNumber` / `selectedNumber` 在 39 条中**完整存在**；
  - `openClass` 两组**实际取值完全一致**（不能区分两组）；
  - `teachProgressSubmitState` / `examMode` 两组**共享同一分类集合**（仅分布不同）；
    `courseCategoryName` 的 3 个分类**全部出现在** present 组；
  - ⚠️ **只有边际计数、无逐 row 交叉证据** → ⛔ **不得**写成
    "38 条**同时**缺 `weekDay` 和 `timePlaceId`"；
  - ⛔ **不登记任何真实 categorical 取值 / 分类名 / 单位名**；⛔ **不推断业务语义**；
  - **G11**：**business semantics partially evidenced; contract gap candidate identified;
    architecture decision pending** —— ⛔ **不声称 G11 resolved**；
- **Builder 实际 SYSU 请求数：0**（本轮为**文档证据同步**）。

## Phase 2B-2C1D 结果（G11 人工界面最小核验 + DG-07 草案）

**由 Architecture Lead 指导定位候选，由负责人本人在官方 UI 人工检查（n = 2）**；
本阶段产出**契约缺口**并已获裁决，**不是实施**。详见 `docs/status/course_data.md`。

| 产出 | 内容 |
|---|---|
| `docs/data/DATA_GATE_DECISIONS.md` | **新增 §17 `DG-07`**（`CourseOffering` 空 `meetings` / 未知排课信息）：完整 `【接口变更请求】` + 4 个替代方案比较 + 安全不变量 + **§17.5.1 裁决**；**状态 `APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**（**2026-10-01 批准，尚未实施**） |
| `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` | **新增 §4.7.2**（C1D 人工核验）+ G11 状态更新（**contract decision approved; implementation pending; school-side business cause still unknown**） |
| `docs/data/DATA_SOURCE_REGISTRY.md` | `OFFERING-002` 补 **C1D 汇总事实（n = 2）** |

**核验结果（两条候选一致）**：UI 中可正常找到 ｜ 时间 / 周次 / 地点**完全空白** ｜
**无状态文字** ｜ 容量 / 已选人数**正常显示** ｜ **与普通教学班同一种表格行** ｜
**无解释空白原因的详情 / tooltip**。

**关键边界（不得越过）**：

- ⚠️ **n = 2**，⛔ **不得**写成"39 条全部如此"；⛔ 不得外推 39/200 到 6892；
- ⛔ **不登记**候选的课程名 / 课程号 / 教学班号，也不登记截图；
- ⛔ **不得**使用"未排课课程 / 未排课教学班 / 时间待定课程 / 异步课程 / 无需排课课程 /
  停开课程 / 无效教学班 / 自由时间教学班"等**学校未提供**的业务标签；
- ⛔ **不推断学校业务状态**、⛔ **不声称 G11 resolved**（**学校侧业务原因仍未查明**）；
- **DG-07 已批准（`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`）**，
  含两条**必须同时成立**的组成部分：① **fail-closed 不变量** ——
  `meetings = []` 只能来自**来源层确实没有提供**排课信息（初始边界：**仅
  `teachingTimePlaceStr` 属性不存在**），⛔ **不得**当作 parser / importer / normalizer
  解析失败的 fallback；② **Planner 安全规则同时覆盖 `offerings` 与 `current_schedule`**
  （同为 `CourseOffering[]`）：任何 `meetings = []` 的 schedule 均为 unknown，
  ⛔ 且 `current_schedule` 含空 meetings 时**不得**声明"已验证与当前课表无时间冲突"；
- ⛔ **`schedule_status` / `schedule_known` / `schedule_state` 本轮未获批准**（不新增）；
  `PlanResult.status` 取值与 `unresolved[].type` 最终命名**仍 deferred 到
  Planner Implementation Review**（`missing_schedule` = **candidate convention only**）；
- ⛔ **本轮未修改** `schemas/` / `docs/interfaces/` / 任何代码 / 任何测试 /
  `mock_data/`；DG-07 **未实施**；
- **Browser 侧**：⛔ **没有新增任何诊断入口**，⛔ **不再需要重复运行** C1B / C1C；
  **Builder 实际 SYSU 请求数：0**（UI 核验由负责人本人完成）。

## DG-07A 结果（Contract Migration，待 Reviewer）

**只做契约迁移**：公共契约放宽 + 契约直接镜像 + 公共接口语义 + 契约级测试。
⛔ **不实施** Course Data 归一化（DG-07B）、Planner safety（DG-07C）、前端展示（DG-07D）。

| 产出 | 内容 |
|---|---|
| `schemas/course_offering.schema.json` | `meetings` 的 **`minItems: 1 → 0`**；`required` **不变**；新增非校验性 `description`（空数组语义）；**未新增 / 未删除字段**、**`Meeting` 未变** |
| `backend/app/models/contracts.py` | `CourseOffering.meetings` → **`min_length=0`**（Pydantic 生成 **`minItems: 0`**，与公共 Schema 精确对齐）；注释同步 |
| `docs/interfaces/course_data.md` | 两种合法状态 + 已批准的 fail-closed 边界（DG-07B 唯一允许来源形态 = `teachingTimePlaceStr` 属性不存在） |
| `docs/interfaces/planner.md` | `meetings` 非空 → 遍历全部 `Meeting`；`meetings = []` → **schedule unknown，绝不 conflict-free**；**同一规则覆盖 `offerings` 与 `current_schedule`** |
| `docs/interfaces/integration.md` | **Provider 签名一字不改**；`meetings = []` **原样透明传递**（不过滤 / 不补 / 不转换 / 不推断） |
| `frontend/src/types/contracts.ts` | **仅注释**同步（`meetings: Meeting[]` 类型形状**未变**） |
| `backend/tests/test_contracts.py`、`test_mock_data_schema.py` | "`meetings: []` 必须失败" **翻转为"必须通过"**；新增 `null` / 非法元素 / 额外字段拒绝、Schema 层 `minItems == 0` 锁定、rollout-gate 用例；**未删除既有严格性用例、未新增 skip** |

**⚠️ rollout gate（本阶段最重要的一条）**：

> `meetings = []` **已成为契约合法状态**，但在 **DG-07B / DG-07C / DG-07D 完成前**，
> **生产真实数据链路不得主动产生或接入 empty-meeting `CourseOffering`**。
> `mock_data/` **保持全部教学班 ≥1 段**；Course Data 仍对"缺排课信息"fail closed；
> **前端尚未实现 empty-meeting 的明确展示**（属 DG-07D）。
> 这是**阶段性 rollout gate**，不是新的 Schema 字段。

**⛔ 前端未改**：任何 Vue 组件 / CSS / 展示文案 / 业务行为**均未修改**；
`CourseOfferingList.vue` 仍按"至少有一段"的现状渲染（因此**不应**收到空数组数据）。

**Builder 实际 SYSU 请求数：0**；**未 merge**。

## Phase 2B-2C1A 结果（SYSU Authorized Browser Transport + Capture Bridge）

**浏览器端显式触发的授权采集 + Python 本地回放桥**；不接 Integration / Planner / API / 前端产品 UI。
详见 `docs/status/course_data.md`。

| 产出 | 内容 |
|---|---|
| `tools/sysu_course_offering_collector.js` | 浏览器端采集器（`window.XuehangSysuCollector.collect({...})`，**必须用户显式调用**） |
| `backend/app/course_data/captured_pages.py` | `CapturedPagesFetcher` + `collect_captured_pages_snapshot()` + `load_capture_bundle()` |
| `backend/tests/test_course_data_captured_pages.py`、`test_sysu_collector_guard.py` | Bridge 测试 + 采集器**静态安全守卫** |

**关键边界**：

- ⛔ **加载脚本不自动请求**：无顶层调用、无定时轮询、无并发；唯一入口是显式 `collect()`；
- ✅ **hostname guard**（必须是 `jwxt.sysu.edu.cn`）+ `pageSize ≤ 200` 校验 + 最小延迟 1000ms；
  默认 2 页、绝对上限 50 页；超过 2 页必须 `confirm()`，取消则 **0 个请求**；**严格串行**；
- ✅ **`firstPageNo` 锁定为 `1`**（SYSU 唯一已验证值）：传入其它起始页**在发请求之前**失败；
- ✅ **认证边界**：`credentials: "same-origin"`，认证完全交给浏览器；
  ⛔ 不读取 / 不保存 / 不打印 / 不导出任何认证状态；401 / 403 / 非 JSON → 立即停止；
- ✅ **数据最小化**：每条 row 只保留 8 个字段，⛔ 丢弃内部 ID 与暂缓字段；
- ✅ **教师脱敏**：`teachingTimePlaceStr` 内 segment 的 teacher → `REDACTED`，其余结构原样保留；
  ⛔ **空 / 非字符串 teacher 不得被 `REDACTED` 静默修复** → 整体失败（错误信息不回显 teacher 取值）；
- ✅ **结果导出**：`toJson(result)` 输出**裸 Capture Bundle**（顶层即 `format` / `semester` /
  `first_page_no` / `page_size` / `pages`），可直接交给 `load_capture_bundle(...)`；
  ⛔ 取消（`cancelled=true`）或无 bundle 时 `toJson()` **失败，不生成伪 bundle**；
- ⛔ 采集器**不判断** completeness（`claimedComplete: false`），交给 Python 分页核心；
- **Capture Bridge 零网络**：只回放本地 Capture Bundle，**不 import Integration**、**不修改 Provider**，
  并**复用** `collect_opening_courses_snapshot()` 判定 `partial` / `complete`（bundle 页码必须连续，不排序修复）；
- ⚠️ **Capture Bundle 是 Real Sanitized Capture**：**不进 Git** / 不进 `mock_data/` / 不做测试 fixture；
- **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/`、`main.py`、`api/`、`frontend/` 均未修改；
  后端 **515 passed / 2 skipped**。

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
  **11 条 Data Gate 通过条件（C1–C11）**；对 **G9 多 segment** 给出概念关系与 4 个候选方案（含 2 个**被禁止**方案）；
  分析 **Curriculum → Planner 契约**（`prerequisites[]` 是否足够、优先级是否进契约）；
  提交 **DG-01 – DG-06** 六项 `【接口变更请求】`**草案**；
  更新 `docs/data/MEMBER_DATA_HANDOFF.md`（新增"可直接共享 / 按需交接 / 禁止交接"三层清单，
  澄清"已有真实证据 ≠ 已交付逐行数据"，**真实逐行数据交接次数仍为 0**）；
  `REAL_TO_SCHEMA_GAP_REPORT.md` 仅小幅补 **Data Gate 引用**（缺口状态不变）。
  **未修改 Schema / Interface / 代码，未调用 SYSU 接口（零请求）**
- **Data Gate-1 架构裁决落档（Architecture Lead）**：DG-01 – DG-06 **全部裁决完毕并写入
  `docs/data/DATA_GATE_DECISIONS.md`** —— **DG-01 APPROVED WITH MODIFICATION**、
  **DG-02 / DG-04 DEFER PUBLIC CONTRACT**、**DG-03 REUSE EXISTING CONTRACT**、
  **DG-05 NO NEW PUBLIC CONTRACT**、**DG-06 APPROVED**；
  同步**修正教师证据**（meeting 级教师关联 = **已知真实语义**，登记为 **known deferred representation gap**）、
  **精确化 DG-05 权威边界**（Planner 只能做本地 adjacency / topology 转换）、
  **更正通过条件计数为 11 条**。
  **仍未修改 Schema / Interface / 代码；契约实施统一在 Data Gate-2**
- **Data Gate-1 最终同步修复**：**§5.1 School-shared 隐私措辞收紧**（不再声称"不含个人身份信息"，
  明确 School-shared ≠ 可公开、`CourseOffering` 可能含教师等人员信息、
  **不得把教师信息归为 Student-private**）；**新增 §11.3 C9 裁决**（目标 2026-1 snapshot、
  7 条获取边界、三方分工、`pageSize` / 请求规模须先确认、**partial snapshot 必须显式记录 completeness**）；
  **§12 同步 C2 / C3 / C9 / C10 / C11 为 ✅ 已确认**（进度＝**仅 C5 待 Data Gate-2**，
  C10 保留**交接次数 = 0**，C11 明确四项风险且**不允许实现层自行补齐**）；
  `REAL_TO_SCHEMA_GAP_REPORT.md` **仅同步 Data Gate 状态**（**G1–G10 历史分析一字未改**）。
  **未修改 Schema / Interface / 代码，未调用 SYSU 接口（零请求），未进入 Data Gate-2**
- **Data Gate-2 公共契约实施（契约已变更）**：
  ① **DG-01 已实施** —— `schemas/course_offering.schema.json` 改为
  **`CourseOffering` 1 — N `meetings[]`**（顶层删除六个排课字段，`required` 含 `meetings`；
  `Meeting` = `weekday` / `start_section` / `end_section` / `weeks[]` / `campus?` / `classroom?`）；
  ② **后端同步** —— `backend/app/models/contracts.py` 新增 `Meeting`，
  `CourseOffering.meetings` 至少 1 项，删除顶层六字段，`__all__` 更新；
  ③ **Mock 迁移** —— `mock_data/course_offerings.json` **9 个教学班**全部迁移，
  **1 个教学班含 2 段 meeting**（第二段人工构造）；
  ④ **测试迁移并加严** —— 所有时间 / 地点 / 周次检查改为**逐 meeting**，
  新增旧格式拒绝 / `meetings: []` 拒绝 / `Meeting` 额外字段拒绝 /
  `meetings[].weeks` 的 `uniqueItems` 专项锁定 / 多 meeting 存在性检查；
  **后端 133 passed / 2 skipped**；
  ⑤ **前端同步** —— `types/contracts.ts` 新增 `Meeting`，
  `CourseOfferingList.vue` 把时间 / 节次 / 周次 / 校区教室**收敛为"上课安排"并逐段展示**，
  `utils/labels.ts` 新增**纯展示**函数 `formatMeetingLine`（无业务判断）；
  **`npm run build` 成功**；
  ⑥ **DG-06 已实施** —— `docs/interfaces/planner.md` 与 `curriculum.md` 按 `/AGENTS.md` 第 5 节修正
  （删除 `build_dependency_graph` / `calculate_priority`；写明 `current_schedule` 语义与
  "全部供给 ≠ 已选子集"；写明优先级**当前无**公共契约）；
  并同步 `docs/interfaces/course_data.md`（DG-01 的 breaking migration：
  一个 `CourseOffering` = 一个教学班，`meetings[]` = 全部上课段；`normalize_offering` 必须聚合全部 meeting，
  不得只解析第一段；登记 meeting 级教师关联为 deferred gap）；
  ⑦ **Data Gate 收口** —— **C5 完成，C1–C11 全部完成 → Data Gate PASSED / CLOSED**；
  **G9 更新为「已通过 DG-01 / Data Gate-2 完成公共契约修复」**（原缺口描述保留）。
  ⚠️ **全程零 SYSU 请求；未写 crawler / Adapter / Provider / Integration；未建数据库；未进入 Course Data MVP**
- **Phase 2B-1 Integration / Provider Skeleton**：新增 `backend/app/integration/`
  （`ports.py` 三个 `typing.Protocol` + `orchestrator.py` 的 `PlanningOrchestrator`）、
  `backend/tests/test_integration_orchestrator.py`（14 个测试，全部用 test-only Fake / Spy Provider）、
  `docs/interfaces/integration.md`；**最小修正 `docs/ARCHITECTURE.md` 的 DG-05 旧口径**。
  Orchestrator **不含业务判断**（不排序 / 不筛选 / 不改写 `PlanResult`），参数按**对象身份**透明传递，
  `semester` 原样下传，`current_schedule=[]` 与 `offerings=[]` 均合法下传，
  Provider 异常**不吞 / 不 fallback / 不切 Mock**。
  **未新增 API**（`main.py` 未修改，OpenAPI `paths` 有测试锁定）；
  **未创建生产 Mock Provider**；**未新增公共业务 Schema / 跨模块 DTO**，
  但**新增了 Integration Provider 公共接口边界**（`docs/interfaces/integration.md` + 三个 Protocol +
  `PlanningOrchestrator` 的四个调用签名；同属 `/docs/interfaces/` 公共契约，
  变更须走 `【接口变更请求】`）；
  **`mock_service.py` 与 `/api/v1/mock/*` 未修改**。
  后端 **147 passed / 2 skipped**。

## 当前接口
- 读取：`MakeupTask[]`、`CourseOffering[]`（**含 `meetings[]`**）、`Preference`、`PlanResult`（当前来自 Mock）
- 前端唯一数据来源：`GET /api/v1/mock/demo`
- 业务接口统一前缀 `/api/v1`；全部响应带 `X-Data-Source: mock`
- **Integration 层（Phase 2B-1）**：`backend/app/integration/` 定义了
  `CurriculumProvider` / `CourseDataProvider` / `PlannerProvider` 三个 Protocol
  与 `PlanningOrchestrator`；**尚未暴露任何 API**，`main.py` 未修改。
  ⚠️ 这四个调用签名是**已确认的 Integration 公共接口边界**
  （`docs/interfaces/integration.md`，属 `/docs/interfaces/` 公共契约）——
  **不得由实现模块私自修改**，变更须走 `【接口变更请求】`
- 公共契约真源仍是 `/schemas/*.schema.json`；
  **`course_offering.schema.json` 已由 Data Gate-2 变更**（`meetings[]`），
  其余四个 Schema **未变**

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
- ~~**G9 结构缺口**~~ ✅ **已修复**：**DG-01 已实施** —— `CourseOffering` 现为
  **1 — N `meetings[]`**（`course_offering.schema.json` 已改，breaking migration 已完成）；
  原缺口（一个教学班无法表达多个时间段）**已消除**，历史记录保留在缺口报告 §4.5 / §4.6
- ~~**DG-01 – DG-06 尚未实施**~~ ✅ **DG-01 与 DG-06 均已实施**；其余四项按裁决不产生契约变更
- ~~**上游 Curriculum / Course Data / Planner 均未产出真实结果**~~ →
  **Course Data 已完成本地标准化内核、`teachingTimePlaceStr` parser、本地 import adapter、快照落点
  与零网络分页采集核心**（Phase 2B-2A / 2B-2B / 2B-2C0，**零网络**），
  但**完整真实 semester snapshot 尚未取得，真实数据尚未进入产品链路**；
  Curriculum / Planner 仍未产出真实结果，前端只能展示 Mock
- ~~集成骨架尚未建立~~ ✅ **Provider 边界与 Orchestrator skeleton 已完成**（Phase 2B-1）；
  ⚠️ 但 **production Curriculum / Planner provider 尚未接入**；
  Course Data 侧只有 `SnapshotCourseDataProvider`（**需要外部先喂入真实快照**），
  因此**没有**任何真实数据链路可以端到端跑通
- ~~五类真实样本尚未通过 Data Gate~~ ✅ **Data Gate PASSED / CLOSED**
- ~~接口文档债务~~ ✅ **DG-06 已实施**：`planner.md` 与 `curriculum.md` 已与 `/AGENTS.md` 第 5 节一致；
  ~~`course_data.md` 未同步 `meetings[]`~~ ✅ **已同步**（DG-01 breaking migration 已写入该文件）
- **`prerequisites[]` 尚无真实证据**：真实培养方案样本中**未发现明确的先修字段**，
  该字段"可被真实数据填充"目前**无证据**（不构成"学校无先修制度"的结论）；
  裁决要求：来源无法提供时**标记未知 / 待人工确认，不得自动补齐**
- **meeting 级教师关联为已知的表达损失**：`teachingTimePlaceStr` 的 segment **本身包含教师项**，
  但 **`meetings[]` 不承载教师**；`teacher` 暂留教学班级作为汇总 / 展示字段，
  登记为 **known deferred representation gap**（**不是"无证据"**）

## 下一步
- **浏览器侧诊断已全部真实执行完成**（2B-2C1B 结构诊断 + 2B-2C1C 相关性诊断，
  均由**负责人手动执行**）：⛔ **不再需要重复运行任何一个诊断**；
  两者的真实聚合结果均已登记（见 `docs/status/course_data.md` 与
  `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` §4.7 / §4.7.1）；
- **当前人工下一步：等待 DG-07B / DG-07C / DG-07D 的任务书**
  （`docs/data/DATA_GATE_DECISIONS.md` §17；**DG-07A 契约迁移已实施 / 待 Reviewer**）；
  ⛔ **DG-07 整体仍为 `IMPLEMENTATION PENDING`**：
  Course Data 归一化（DG-07B）、Planner safety（DG-07C）、
  前端 empty-meeting 展示（DG-07D）**均未开始**；
  Data Gate **仍保持 Reopened**（⛔ 未 CLOSED；⛔ DG-01 – DG-06 不重新打开）；
  ⛔ **本模块不自行实施**，也**不自行命名 / 拆分实施阶段**；
  ⛔ **不再要求重复** C1B / C1C 诊断或 C1D 人工核验；
  ⚠️ **rollout gate**：`meetings = []` 契约合法，但在 DG-07B/C/D 完成前，
  产品链路（含前端展示）**不得**接入 empty-meeting `CourseOffering`；
- **真实 Capture Bundle 的导入 UI**（前端产品链路）属**后续步骤**，本轮不做；
- **分页参数人工验证已完成**（`first_page_no=1`、单页上限 200、前两页 `total=6892`）；
  `max_pages` 是**内部安全阀**，不是学校侧参数；
  **partial snapshot 必须显式记录 completeness，不得宣称 complete**（C9）
- **仍不允许实现层自行补齐**：`prerequisites[]` / `weekDay` / `openingSchoolName → campus` /
  meeting-level teacher 四项保持"待确认"或"已知暂缓"（C11）；
  **G11（部分 row 缺 `teachingTimePlaceStr`）**同样**只登记、不推测业务含义**，
  且 **DG-07B/C/D 实施前，⛔ 不得**在 Course Data / Planner / Frontend 里
  以任何 workaround 方式表达"排课信息不可用"（不得伪造 `Meeting`、不得过滤、不得猜时间、
  不得把 `meetings = []` 提前接入产品链路）
- ⚠️ **公共契约不得再自行修改**：任何后续变更仍须走 `【接口变更请求】` → 人工确认
- ⛔ **`partial` snapshot 不得接入 Integration / Planner 产品链路**（仅用于规模 / 小范围 / parser 验证）
- **真实 Capture Bundle 属 Real Sanitized Capture**：**不得进入 Git**（含 `mock_data/` 与测试 fixture）
- 真实 Curriculum / Planner provider 的接入顺序与形式**待负责人安排**
  （Phase 2B-1 只定义了插座，未决定实现方式）
- 2B-0 全程遵守 `docs/data/DATA_ACQUISITION_PLAN.md` 的三层数据模型与红线：
  **Raw 不进 Git；D4 的 Raw 与逐行脱敏样本均不得进入 public 仓库；`/mock_data/` 保持人工虚构**
- 比赛 Demo 故事线**不属于当前开发主线**，推迟到后续产品展示阶段再评估
- 在真实 Curriculum / Planner / Course Data 稳定之前，不接 Agent / LLM
- **分页参数人工验证已完成**（`first_page_no=1`、单页上限 200、前两页 `total=6892`）；
  `max_pages` 是**内部安全阀**，不是学校侧参数；
  **partial snapshot 必须显式记录 completeness，不得宣称 complete**（C9）
- **仍不允许实现层自行补齐**：`prerequisites[]` / `weekDay` / `openingSchoolName → campus` /
  meeting-level teacher 四项保持"待确认"或"已知暂缓"（C11）
- ⚠️ **公共契约不得再自行修改**：任何后续变更仍须走 `【接口变更请求】` → 人工确认
- ⛔ **`partial` snapshot 不得接入 Integration / Planner 产品链路**（仅用于规模 / 小范围 / parser 验证）
- **真实 Capture Bundle 属 Real Sanitized Capture**：**不得进入 Git**（含 `mock_data/` 与测试 fixture）
- 真实 Curriculum / Planner provider 的接入顺序与形式**待负责人安排**
  （Phase 2B-1 只定义了插座，未决定实现方式）
- 2B-0 全程遵守 `docs/data/DATA_ACQUISITION_PLAN.md` 的三层数据模型与红线：
  **Raw 不进 Git；D4 的 Raw 与逐行脱敏样本均不得进入 public 仓库；`/mock_data/` 保持人工虚构**
- 比赛 Demo 故事线**不属于当前开发主线**，推迟到后续产品展示阶段再评估
- 在真实 Curriculum / Planner / Course Data 稳定之前，不接 Agent / LLM
