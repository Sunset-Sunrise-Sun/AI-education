# Data Gate-1 架构决策与裁决记录

> **状态：Data Gate-1 架构裁决已完成；DG-01 与 DG-06 已于 Data Gate-2 实施。**
> **Data Gate 已 PASSED / CLOSED —— 通过条件 C1–C11 全部完成。**
>
> ⚠️ **Data Gate Reopen（2026-10-01，narrow）：**
> 因 **G11** 的新真实证据（见 §17 与 `REAL_TO_SCHEMA_GAP_REPORT.md` §4.7 / §4.7.1 / §4.7.2），
> Data Gate 已**仅在 DG-07 范围内临时 Reopen** —— **Reopened narrowly for DG-07 only**。
> **DG-01 – DG-06 不重新打开**，其它已裁决完成的问题**不重新讨论**。
> ⚠️ **Data Gate 仍保持 Reopened**：**尚未**回到 CLOSED
> （DG-07 已批准，但**尚未实施、尚未完成回归、尚未经 Reviewer 验收**）。
>
> **DG-07 状态：`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**
> （**2026-10-01 由项目负责人批准**；⛔ **本轮未实施**：
> `schemas/` 与 `docs/interfaces/` **未被修改**）。
> ⚠️ **"WITH MODIFICATION" 的准确含义**：**不是**只批准把 `meetings` 的
> `minItems: 1 → 0`，而是 **Schema 放宽** 与
> **Course Data fail-closed 不变量（§17.12.1）**、
> **Planner 安全不变量（§17.9，含 `current_schedule`）** **必须同时成立**。
>
> 本文件因此是**决策与裁决的归档记录**，不是契约本身：
> 契约真源仍是 `/schemas/*.schema.json` 与 `/docs/interfaces/`。
> 实施记录见 **§16 Data Gate 关闭记录**；DG-07 草案见 **§17**。
>
> ## 本文件的三条红线（对未经授权的新变更仍然适用）
>
> 1. **不得绕过流程改 `/schemas/`、`/docs/interfaces/`。** 后续任何契约变更仍须走
>    `/AGENTS.md` 第 4 节的 `【接口变更请求】` → 人工确认。
> 2. **不得自行增删字段、不得改变字段含义。**
> 3. **未获授权不得提前实施。**
>
> 配套文档：
> `DATA_SOURCE_REGISTRY.md`（来源登记）、`REAL_TO_SCHEMA_GAP_REPORT.md`（缺口登记）、
> `SYSU_CASE_A_PUBLIC_EVIDENCE.md` / `SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md` /
> `SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md` / `SYSU_COURSE_OFFERING_RECON.md`（D1–D5 证据）。

---

## 架构裁决总表（Architecture Lead，2026-09-30）

> 本节是六项 `【接口变更请求】` 草案的**裁决结果**。
> **状态更新（Data Gate-2）：DG-01 与 DG-06 已实施；其余四项按裁决"不产生公共契约变更"。**
> 裁决目标：**只修改当时确实阻塞真实 Course Data / Planner 联调的契约**，
> **不趁 Data Gate 把整个项目重构成一套大型领域模型**。

| DG | 主题 | 裁决 | MVP 处置 | 是否变更公共契约 | 实施状态 |
|---|---|---|---|---|---|
| **DG-01** | `CourseOffering` 多 segment | **APPROVED WITH MODIFICATION** | 采用"**一个 `CourseOffering` 内含多个 meeting / segment**"的方案 | **是**（`course_offering.schema.json`；**有意的 breaking migration**） | ✅ **已在 Data Gate-2 实施**（见 §16） |
| **DG-02** | `CompletedCourse` | **DEFER PUBLIC CONTRACT** | 概念成立；**MVP 不新增** `completed_course.schema.json`，先作为 **Curriculum 内部规范化对象**；真实 D4 由负责人经**非公开位置**交 Curriculum；Curriculum 对外**仍只输出 `MakeupTask[]`** | **否** | ✅ 按裁决执行（无契约变更） |
| **DG-03** | `CurrentEnrollment` | **APPROVE CONCEPT, REUSE EXISTING CONTRACT** | 概念保留；**不新增** `CurrentEnrollment` Schema；Planner 的 `current_schedule` **直接使用现有公共类型 `CourseOffering[]`**，语义为"**学生已选中的教学班子集**" | **否** | ✅ 按裁决执行（无契约变更） |
| **DG-04** | `CurriculumVersion` / `CurriculumCourse` | **DEFER PUBLIC CONTRACT** | 概念边界成立；**MVP 暂作为 Curriculum 内部模型**，**不新增两个公共 Schema**；同时明确 `Course.course_type` / `Course.recommended_semester` **不得被解释为课程全局固有属性** | **否** | ✅ 按裁决执行（无契约变更） |
| **DG-05** | dependency / priority | **NO NEW PUBLIC CONTRACT FOR MVP** | **不新增** `DependencyGraph`、**不新增** `priority` 字段、**不新增** `PriorityResult`；Curriculum 认定并产出 dependency edges；Planner 只消费 `MakeupTask.prerequisites[]` | **否** | ✅ 按裁决执行（无契约变更） |
| **DG-06** | `planner.md` 职责冲突 | **APPROVED** | 修正 `docs/interfaces/planner.md`，并同步 `docs/interfaces/curriculum.md`，使其与 `/AGENTS.md` 第 5 节一致 | **是**（**文档修正**，非字段变更） | ✅ **已在 Data Gate-2 实施**（见 §16） |

**进入 Data Gate-2 实施的契约变更只有两项** ——
**DG-01（`course_offering.schema.json`）** 与 **DG-06（`planner.md` / `curriculum.md` 文档修正）**，
**两项均已完成**。
**DG-02 / DG-03 / DG-04 / DG-05 不产生公共契约变更。**

> ⚠️ **Data Gate-1 的"最小接口变更集合"因此比原草案更小**（见 §9）：
> 真实联调真正被阻塞的只有 **多 segment 建模** 与 **接口文档职责冲突** 两项。
>
> ⚠️ **DG-07（2026-10-01，独立于上表）**：`CourseOffering` 空 `meetings` / 未知排课信息，
> 状态 **`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**
> （**尚未实施**）—— 见 **§17.5.1 裁决** 与 **§12.3**。
> ⛔ 上表 DG-01 – DG-06 的裁决与实施状态**不受影响、不重新打开**。

---

## 1. Data Gate 目的

### 1.1 为什么需要 Data Gate

Phase 1 的 5 个公共 Schema 是在**没有真实数据**的情况下设计的。
Phase 2B-0B / 2B-0B+ / 2B-0C / 2B-0D 依次取得了 D2 / D3 / D4 / D5 的真实样本，
`REAL_TO_SCHEMA_GAP_REPORT.md` 已经把"承载不了的地方"逐条登记为 G1–G10。

现在真实数据已经**足够暴露出结构性问题**，继续扩大数据集不会再增加新的判断，
所以**暂停继续采集，先做一次架构裁决**：

> 在投入真实 Curriculum / Course Data / Planner 开发之前，
> 必须先把**实体边界**、**数据所有权**和**契约缺口**定下来；
> 否则三个模块会各自"按自己理解"造结构，最后在集成时才发现对不上。

### 1.2 Data Gate-1 做什么、不做什么

| | 内容 |
|---|---|
| **做** | 把已确认的真实事实整理为**实体边界**；区分 Shared / Private / Derived；对多 segment、Curriculum → Planner 契约等关键问题给出**候选方案与权衡**；提交 **DG-01 – DG-06 接口变更请求草案**；明确 Course Data 获取边界；给出 **Data Gate 通过条件** |
| **不做** | 不改 Schema、不改接口文档、不写代码、不写 parser / crawler / Adapter / CourseDataProvider / Integration、不建数据库、不调 SYSU 接口、**不实施裁决**（实施在 Data Gate-2） |

### 1.3 本轮性质

```text
D1–D5 真实证据  →  缺口登记（REAL_TO_SCHEMA_GAP_REPORT）
                →  Data Gate-1：决策草案 + 接口变更请求草案（已完成）
                →  架构裁决：DG-01 – DG-06 全部裁决完毕（Architecture Lead）
                →  Data Gate-2：实施 DG-01 契约变更 + DG-06 文档修正（已完成）
                →  ✅ Data Gate PASSED / CLOSED
                →  下一步：Course Data MVP（真实 2026-1 semester offering snapshot）
```

**裁决与实施均已完成；Data Gate 已关闭。本文档作为归档记录保留。**

---

## 2. D1–D5 已确认事实

> 只列**已经取得真实证据**的事实。证据等级与访问类型见 `DATA_SOURCE_REGISTRY.md`。
> **原始材料、逐行记录、Raw 响应一律不在仓库内。**

| 数据 | source_id | 访问类型 | 已确认到什么程度 |
|---|---|---|---|
| **D1 政策** | `POLICY-001` / `POLICY-003` / `POLICY-008`（Confirmed）等 | Public Official | 3 项 Confirmed；4 项 Partial；1 项 Historical；上级通知原文与"独立校级课程认定专门文件"**Not Found**。**版本链**：2024〔159号〕→2025〔1号〕有正文直接证据；**2025〔1号〕→2026〔62号〕待确认**。`POLICY-008` 第三十一条直接规定转专业后的**学分认定与成绩转换**（"适用异动后年级专业的培养方案"、"在学籍异动后一学期内完成、以一次为限"） |
| **D2 原专业培养方案** | `CURR-OLD-003`（25级 遥感科学与技术） | **Authenticated Official**（中大本科教务系统） | 修业年限 4 年；毕业总学分 **147.0**；实践教学学分要求 **37.1**；培养类别 公必 39 / 专必 78 / 专选 22 / 公选 8；附表一 **128** 个课程号单元格 |
| **D3 新专业培养方案** | `CURR-NEW-004`（25级 网络空间安全） | **Authenticated Official** | 修业年限 4 年；毕业总学分 **153.0**；实践教学学分 **38.5**；公必 39 / 专必 83 / 专选 23 / 公选 8；附表一 **138** 个课程号单元格 |
| **D4 已完成课程** | `TRANSCRIPT-001` | **Authenticated Official**（负责人私密侧合并 + 脱敏） | **24 条**记录；8 个字段覆盖率**均为 100%**；字段 = `course_id` / `course_name` / `credit` / `course_type` / `semester` / `passed` / `offering_unit` / `cultivation_type` |
| **D5 课程开设 / 教学班** | `OFFERING-001` | **Authenticated Official**（小规模人工侦察） | 范围 **2026-1**；`CSE202` 返回 **2 个真实教学班**；**每个教学班都有多个上课时间 / 地点 segment** |

### 2.1 本轮必须继承的既有限制（不得被本文档推翻）

1. **`remaining_capacity` 不是学校接口直接提供的** —— 它是 `limitNumber - selectedNumber` 的**派生值**，
   **不得**声称接口直接提供剩余容量。
2. **`courseCategoryName`（样本为"专必"）带培养方案 / 上下文语义** —— **不得**认定为课程的全局固有属性。
3. **`teachProgressSubmitState` / `openClass` / `outlineTypeNum`：字段存在，业务语义待确认** —— **不得**根据 0/1 值自行解释。
4. **`courseId` / `class_ID` 等后台长 ID ≠ 公共 `course_id` / `class_id`** —— 只记录其存在，不记录取值。
5. **D2 / D3 的公开搜索仍然 Not Found** —— 总体证据由**认证来源**补齐，`CURR-NEW-001` 的 Public Not Found
   历史**继续保留**；外部访问者无法通过公开 URL 独立复核。
6. **本轮不做任何课程等价判断**，**不做课程差分**，**不生成 MakeupTask**。

### 2.2 真实数据尚未覆盖的部分（重要）

- **真实培养方案样本中未发现明确的先修 / 前置课程字段或条款**（见 `REAL_TO_SCHEMA_GAP_REPORT.md` §3.1）。
  ⚠️ 这**只是对本次两份材料的观察**，**不构成**"学校制度中没有先修要求"的结论；
  但它意味着 **`prerequisites[]` 的"可被真实数据填充"目前尚无证据**（直接影响 DG-05 的分析，见 §7.3）。
- G3（学分差额）、G5（`PlanResult` 无冲突对象）、G8（`Preference` 无法表达"已经有什么"）**仍未验证**，
  本轮**不处理**，继续留在缺口报告中。

---

## 3. 核心实体边界

> 本节只定义**概念边界**（"这个实体表示什么、不表示什么"）。
> **不定义字段清单** —— 字段级设计以**架构裁决给出的目标结构**与 Data Gate-2 契约文本为准。
>
> 核心原则（已由负责人确定，本轮继承）：
>
> ```text
> Course          ≠  CurriculumCourse  ≠  CompletedCourse
> ```
>
> 三者分别回答："**世界上有哪些课**" / "**某份培养方案要求什么**" / "**某学生修过什么**"。

### 3.1 `Course` —— 课程基础身份 / 基础属性

| 项 | 内容 |
|---|---|
| **表示** | 一门课的**基础身份与基础属性**：课程号、课程名、学分 |
| **不表示** | ① 学生的修读结果（`semester` / `passed`）；② 培养方案上下文中的"专必 / 专选"等身份；③ 某学期是否开课、由谁开、什么时间上 |
| **当前承载** | `schemas/course.schema.json`（必填 `course_id` / `course_name` / `credit`） |
| **边界问题** | 现有 `Course` 上还挂着 **`course_type`** 与 **`recommended_semester`** —— 这两个字段都带**培养方案 / 上下文语义**（`course_type` 已在 2B-0C Review 中改判为上下文属性）。它们**当前不应视为课程固有属性**，但**本轮不动 Schema**，兼容 / 迁移策略见 **DG-04**。 |
| **真实证据** | `course_id` / `course_name` / `credit` 在 D2 / D3 / D4 / D5 中均为 **A 直接映射** |

### 3.2 `CurriculumVersion` —— 一份培养方案

| 项 | 内容 |
|---|---|
| **表示** | **某专业、某年级、某个版本**的一份培养方案（一个版本化的整体） |
| **不表示** | 单门课的基础属性；学生的修读结果；某学期的实际开课情况 |
| **为什么需要** | D2 / D3 两份文档的**标题本身**就写明"25级 遥感科学与技术"、"25级 网络空间安全"，且各自带有**培养方案级**的总学分（147.0 / 153.0）、实践教学学分（37.1 / 38.5）、培养类别学分口径与适用年级 —— 这些**都是"方案级"的量**，不是单门课的属性 |
| **当前承载** | **无**（`/schemas/` 下没有任何文件）→ **G1**，已由两份 2025 级真实培养方案确认存在 |
| **边界要点** | `CurriculumVersion` 是**共享数据**（学校侧产物），但**"某学生适用哪一版"是用户私有信息**（见 §5） |
| **裁决** | **DG-04：MVP 暂留 Curriculum 内部模型**，不新增公共 Schema；培养方案级总量、课程分组等由 Curriculum 内部结构承载 |

### 3.3 `CurriculumCourse` —— 某门课在某份培养方案中的要求

| 项 | 内容 |
|---|---|
| **表示** | **某门 `Course` 在某个 `CurriculumVersion` 中的要求** —— 即"这份方案对这门课提出了什么" |
| **承载的上下文** | `course_type`（公必 / 专必 / 专选 / 公选 等）、推荐修读学期、**课程分组 / 模块归属**、先修要求 |
| **不表示** | 课程本身的基础身份（那是 `Course`）；学生是否修过、是否通过（那是 `CompletedCourse`） |
| **为什么必须与 `Course` 分开** | 同一门课**在不同专业 / 不同培养方案下可能被归入不同类别**（在专业 A 属专必、在专业 B 属专选、在某方案属公选）。把 `course_type` 当课程全局属性，会在跨专业转衔场景中**直接产生错误结论** —— 而本项目处理的正是转专业场景 |
| **当前承载** | **无**（`course_type` / `recommended_semester` 目前挂在 `Course` 上，属**位置不当**）→ 见 **DG-04** |
| **已知的表达限制** | 培养方案里的推荐学期存在**跨学期区间**形态（如 `2025-1~2025-2`、`2025-1~2028-2`），而现有 `recommended_semester` 只能存**单个整数** → **无法无损表示**（§3.1 记为 C） |

### 3.4 `CompletedCourse` —— 某学生已经修过某门课的事实

| 项 | 内容 |
|---|---|
| **表示** | **某个学生**在**某个学期**修了**某门课**、**结果如何** |
| **至少需要承载（真实 D4 已确认）** | `course_id`、`course_name`、`credit`、`semester`（实际修读学期）、`passed`（该次修读是否通过） |
| **不表示** | 课程基础属性（那是 `Course`）；学校开设了什么（那是 `CourseOffering`）；学生**当前**在读什么（那是 `CurrentEnrollment`） |
| **最关键的红线** | **`semester` / `passed` 绝对不能塞回 `Course`。**<br>`semester` 是**学生实际修读学期**，与 `Course.recommended_semester`（**培养方案建议学期**）**语义完全不同**，**不可互相替代**；<br>`passed` 是**学生的一次修读事实**，**不是课程固有属性** —— 同一门课由不同学生、在不同学期修读，结果可能不同 |
| **当前承载** | **无** → **G2**，已由 `TRANSCRIPT-001` 验证 |
| **数据所有权** | **用户私有数据**（见 §5） |
| **裁决** | **DG-02：DEFER PUBLIC CONTRACT** —— **MVP 不新增公共 Schema**，先作为 **Curriculum 内部规范化对象**；D4 Sanitized Sample 由负责人经**非公开位置**交 Curriculum；Curriculum 对外**仍只输出 `MakeupTask[]`** |

### 3.5 `CurrentEnrollment` —— 学生当前已选 / 正在修读的教学班

| 项 | 内容 |
|---|---|
| **表示** | 学生**当前**已经选择 / 正在修读的**教学班**（"我的课表里现在有什么"） |
| **必须与之分开** | `CompletedCourse`（那是**已经修完**的）／`CourseOffering`（那是**学校开设的供给**）／`Preference`（那是**想要什么**） |
| **为什么必须要这个概念** | Planner 的**当前课表冲突检测**需要的正是"学生现在已占用哪些时间段"。若用 `CourseOffering` 代替，就等于把"学校开设的全部教学班"当成"我的课表"，冲突检测会**完全失真** |
| **当前承载** | **无** → **G4**（`docs/interfaces/planner.md` 把"当前课表"列为 Planner 输入，但 `/schemas/` 下没有对应文件）。⚠️ G4 **尚未用真实样本验证**，目前是"接口文档与 Schema 不一致"这一**文档级事实** |
| **数据所有权** | **用户私有数据**（见 §5） |
| **裁决** | **DG-03：APPROVE CONCEPT, REUSE EXISTING CONTRACT** —— **不新增 Schema**；Planner 的 `current_schedule` **直接使用 `CourseOffering[]`**，语义 = **学生已选中的教学班子集**。⚠️ 必须在接口文档中与"学校全部供给"区分；⛔ **不得用 `Preference.avoid_times[]` 冒充当前课表** |

### 3.6 `CourseOffering` —— 某学期的一个教学班（供给）

| 项 | 内容 |
|---|---|
| **表示** | **学校在某学期开设的一个教学班**："现实中当前学期有哪些可用教学班" |
| **不表示** | 学生是否选了它；学生是否修过它；课程在培养方案中的身份（`courseCategoryName` 带方案上下文，**不得**当成课程全局属性） |
| **当前承载** | `schemas/course_offering.schema.json` |
| **真实证据** | `courseNum → course_id`、`courseName → course_name`、`classNumber → class_id`、`yearTerm → semester`、`limitNumber → capacity` 为 **A**；`score → credit` 为 **B**（字符串数字）；`remaining_capacity` 为 **B 派生值** |
| **已知结构缺口** | **G9：一个教学班可有多个上课时间 / 地点 segment，当前一个 `CourseOffering` 只能表达一组 → 无法无损表达**（见 §6 / DG-01）。**已裁决（DG-01 APPROVED WITH MODIFICATION）：改为 `CourseOffering 1 — N Meeting`，Data Gate-2 实施** |

### 3.7 `ScheduleSegment` / `Meeting` —— 教学班下的一段上课时间 / 地点

| 项 | 内容 |
|---|---|
| **表示** | 一个教学班**内部**的一段独立排课："第几周（哪些周）、星期几、第几节到第几节、在哪个校区 / 教室" |
| **概念关系** | `CourseOffering` **1 —— N** `ScheduleSegment` |
| **至少需要表达（真实 D5 已存在的量）** | `weekday`、`start_section`、`end_section`、`weeks[]`、`campus`、`classroom` |
| **当前承载** | **无独立对象** —— 这 6 项目前是 `CourseOffering` 的**直接字段**，一个对象只能装一组 |
| **裁决** | **已裁决（DG-01 APPROVED WITH MODIFICATION）：本概念成为公共契约的目标结构**，形态为 `CourseOffering.meetings[]`（嵌套 segment 数组），**Data Gate-2 实施**。见 §6.8 目标结构 |
| **注意** | 本文档**只记录裁决与目标结构**，**不在本轮修改任何 Schema**。⚠️ **不得把本节理解为"契约已经改好"。** |

### 3.8 边界一句话总结

```text
Course            —— 世界上有哪些课（基础身份，与谁修、哪份方案无关）
CurriculumVersion —— 某专业 / 年级 / 版本的一份培养方案
CurriculumCourse  —— 某门课在这份方案里的要求（专必 / 专选 / 推荐学期 / 分组 / 先修）
CompletedCourse   —— 某学生已经修过某门课的事实（含实际修读学期、是否通过）
CurrentEnrollment —— 某学生当前已选 / 在读的教学班
CourseOffering    —— 学校某学期开设的一个教学班（供给）
ScheduleSegment   —— 一个教学班内的一段上课时间 / 地点
```

**四类信息互不替代**：课程身份 / 方案要求 / 修读事实 / 当前占用。

> **裁决后的落地形态（一句话版）**：
> `Course` 保持公共契约；`CurriculumVersion` / `CurriculumCourse` **留 Curriculum 内部**（DG-04）；
> `CompletedCourse` **留 Curriculum 内部规范化对象**（DG-02）；
> `CurrentEnrollment` **不新增 Schema，复用 `CourseOffering[]` 作为 `current_schedule`**（DG-03）；
> `CourseOffering` **改为承载 `meetings[]`**（DG-01，Data Gate-2 实施）。

---

## 4. 实体所有者

> "所有者"= **负责定义并生产该数据**的模块。所有者为 Curriculum / Course Data 的实体，
> 其他模块**只消费**，不得自行重写（`/AGENTS.md` 第 5 节）。

| 实体 | 所有者模块 | 消费方 | 当前是否公共契约 | 裁决结论（2026-09-30） |
|---|---|---|---|---|
| `Course` | **Curriculum**（课程基础身份可视为共享基础） | Course Data、Planner、Agent / Frontend | **是**（`course.schema.json`） | 保留为公共契约；`course_type` / `recommended_semester` 是**现有兼容字段**，**不得被解释为课程全局固有属性**（DG-04） |
| `CurriculumVersion` | **Curriculum** | Planner（间接）、Agent / Frontend | **否**（G1） | **MVP 暂留 Curriculum 内部模型**，不新增公共 Schema（DG-04） |
| `CurriculumCourse` | **Curriculum** | Planner（间接）、Course Data（`courseCategoryName` 对齐）、Agent / Frontend | **否**（G1） | **MVP 暂留 Curriculum 内部模型**，不新增公共 Schema（DG-04） |
| `CompletedCourse` | **Curriculum**（由负责人私密侧产出的脱敏样本派生） | **MVP 阶段仅 Curriculum 内部** | **否**（G2） | **MVP 不新增公共 Schema**，作为 **Curriculum 内部规范化对象**；D4 Sanitized Sample 由负责人经**非公开位置**交给 Curriculum（DG-02） |
| `CurrentEnrollment` | **Integration / Agent**（用户侧课表）× **Planner**（消费） | Planner | **否**（G4） | **不新增 Schema**；Planner 的 `current_schedule` **复用现有公共类型 `CourseOffering[]`**，语义 = 学生已选中的教学班子集（DG-03） |
| `CourseOffering` | **Course Data** | Planner、Agent / Frontend | **是**（`course_offering.schema.json`） | **批准修改**：改为承载 `meetings[]`（多 segment）；Data Gate-2 正式改契约（DG-01） |
| `ScheduleSegment` / `Meeting` | **Course Data** | Planner | **否** → **是（Data Gate-2 起）** | **已裁决进入公共契约**，形态为 `CourseOffering.meetings[]`（DG-01） |
| `Preference` | **Agent / Integration**（由用户真实需求转换） | Planner | **是**（`preference.schema.json`） | 本轮不变；⚠️ **不得用 `avoid_times[]` 冒充"当前课表"**（DG-03） |
| `MakeupTask` | **Curriculum** | Planner、Agent / Frontend | **是**（`makeup_task.schema.json`） | 依赖 / 优先级**均不新增字段**；Planner 只消费已有 `prerequisites[]`（DG-05） |
| `PlanResult` | **Planner** | Agent / Frontend | **是**（`plan_result.schema.json`） | 本轮不变（G5 未验证，暂不处理） |
| 学业优先级 / 风险 | **Curriculum** | Planner（消费，不得自行重算） | **否** | **暂不新增 `priority` 字段**；无正式 priority 时 **Planner 不得自行生成优先级**（DG-05） |
| 课程依赖结果 | **Curriculum** | Planner | **否**（但 `MakeupTask.prerequisites[]` 已存在） | **不新增 `DependencyGraph`**；Curriculum 认定并产出 dependency edges，Planner 只做本地 adjacency / topology 转换（DG-05） |

### 4.1 边界红线（沿用 `/AGENTS.md` 第 5 节）

- **Planner** 不得为求解方便自行重写课程认定或学业优先级规则；
- **Course Data** 不得判断"学生是否需要补修某门课"，不得决定补修优先级；
- **Curriculum** 不负责真实教学班抓取、课表约束求解与 Path Repair；
- **Agent / Integration** 不得用 LLM 重新计算 Planner 结果，不得自动确认课程等价关系。

---

## 5. Shared / Private / Derived 分类

> 这是 Data Gate 的**核心产出之一**：先确定"谁的数据、能不能出仓库"，
> 再谈接口形状。**本轮不设计 PostgreSQL 表、不设计 ORM / migration。**

### 5.1 学校共享数据（School-shared）

**School-shared 的含义**：表示"**可在同一学校用户场景中复用的学校侧数据**"。

> ⚠️ **它不代表天然不含人员信息，也不代表可以公开发布。**

- `CourseOffering` 等数据**可能包含教师等人员信息**（真实 D5 中 `teachingName` 即为一例）；
- **Real / Raw 数据仍须遵守数据最小化、来源授权和非公开处理规则**；
- **"是否 School-shared" 与 "是否可以公开" 是两个独立问题** ——
  前者描述**数据归属与复用范围**，后者描述**披露与发布边界**；
- ⚠️ **不得把教师信息归为 Student-private**：教师信息属**学校侧**数据，
  但**同样不得进入 public 仓库**，其处理口径由数据最小化与来源授权规则决定。

| 数据 | 说明 |
|---|---|
| `Course` | 课程基础身份与基础属性 |
| `CurriculumVersion` | 培养方案（专业 / 年级 / 版本） |
| `CurriculumCourse` | 课程在该方案中的要求（类别 / 推荐学期 / 分组 / 先修） |
| `CourseOffering` | 某学期教学班（供给）。⚠️ **可含教师等人员信息** |
| **semester offering snapshot** | 某学期的**开课快照**（"这一学期学校开了什么"的时点切片） |

⚠️ 即使属共享数据，**认证来源的原始材料（docx、Raw JSON）仍不进入 public Git**，
仓库内只保留 `source_id`、来源性质、**汇总事实**与缺口结论。

### 5.2 用户私有数据（User-private）

**归属具体学生**，只能在授权范围内使用，**不得进入 public 仓库**（含脱敏逐行样本）。

| 数据 | 说明 | 裁决后的公共表达 |
|---|---|---|
| `CompletedCourse` | 已修课程事实（含实际修读学期、是否通过） | **MVP 不进公共契约**；作为 **Curriculum 内部规范化对象**（DG-02） |
| `CurrentEnrollment` | 当前已选 / 在读教学班 | **MVP 不新增 Schema**；Planner 的 `current_schedule` **复用 `CourseOffering[]`**，语义 = 学生已选中的子集（DG-03） |
| `Preference` | 用户偏好与约束意愿 | 公共契约；⚠️ **不得用 `avoid_times[]` 冒充当前课表** |
| **用户适用的 `CurriculumVersion` reference** | "**这个学生**适用哪一版培养方案"是一个**指向共享数据的私有引用**：培养方案本身是共享的，**但"该生适用哪一版"是私有信息**（由学籍异动时点、年级、专业决定，见 D1 政策） | 私有引用；培养方案本体**MVP 不进公共契约**（DG-04） |

> ⚠️ **用户私有 ≠ 可以脱敏后进 public 仓库**：逐行样本（含 D4）一律**不得进入 public Git**，
> 只能通过**负责人控制的非公开位置**按需交接（见 `MEMBER_DATA_HANDOFF.md`）。

### 5.3 派生结果（Derived）

由系统依据共享数据 + 私有数据**计算得出**，不是学校提供的原始事实。

| 数据 | 说明 |
|---|---|
| `MakeupTask` | 补修需求（由 Curriculum Diff 派生） |
| risk / priority | 补修风险与学业优先级（**Curriculum 生产，Planner 消费**） |
| `PlanResult` | 补修方案（Planner 约束求解派生） |

⚠️ **派生结果的权威性低于学校正式规则。** 任何涉及学分认定、课程等价、期限与先修的确定性判断，
都必须回到 D1 正式政策 + 人工确认（`/AGENTS.md` 第 7 节）。

---

## 6. `CourseOffering` multi-segment 裁决（G9）

### 6.1 已确认的真实事实

`SYSU_COURSE_OFFERING_RECON.md` §6（`OFFERING-001`）：

- **`CSE202` 的每个教学班都存在多个 schedule segment**（真实结构形如：
  "1-17周 星期一 第 3-4 节 某教室" ＋ "1-17单周 星期三 第 5-6 节 某教室"）；
- 当前 `CourseOffering` **只能表达一组** `weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom`。

**结论：一个教学班可以拥有多个独立的上课时间 / 地点 segment，当前 `CourseOffering` 无法在一个对象中无损表达（G9 成立）。**

### 6.2 正确的概念关系

```text
CourseOffering（一个教学班）
  ├─ ScheduleSegment / Meeting   （第 1 段：周次 / 星期 / 节次 / 校区 / 教室）
  ├─ ScheduleSegment / Meeting   （第 2 段：…）
  └─ …
```

而**不是**：

```text
CourseOffering = 一个时间段        ❌（当前 Schema 的形态，无法容纳多段）
```

### 6.3 每个 segment 至少需要表达的量

| 量 | 依据 |
|---|---|
| `weekday` | 已在公共 Schema 中（`CourseOffering.weekday`） |
| `start_section` | 已在公共 Schema 中 |
| `end_section` | 已在公共 Schema 中 |
| `weeks[]` | 已在公共 Schema 中（`uniqueItems`，运行时强制） |
| `campus` | 已在公共 Schema 中 |
| `classroom` | 已在公共 Schema 中 |

> ⚠️ **MVP 最小设计原则**：不要因为真实 JSON 里有字段就全部加入公共 Schema。
> 上表 6 项之所以入选，是因为它们**已经有对应的公共语义**，只是"位置"从教学班级降到了 segment 级。

### 6.4 `teacher` 与 meeting 的关系 —— 事实与裁决

> ⚠️ **本节曾出现一处不准确的表述，已在 Reviewer 修复中更正**：
> 原文写"未观察到 segment 级教师字段，因此没有证据表明教师有 meeting-level 语义" ——
> **该说法不成立，已删除。**

| 检查项 | 真实事实 |
|---|---|
| 真实 D5 的 `teachingTimePlaceStr` | 该**原始串本身就是按 segment 组织的，且 segment 项中包含教师信息** —— 即 **segment 与教师是有关联的** |
| 一个教学班内多个 segment 与教师的关联 | **已有样本表明 segment 与教师存在关联**（不同 segment 可对应教师信息） |
| 因此能否说"没有证据" | **不能。** 准确表述是：**meeting-level 教师关联 = 已知的真实语义** |

**架构裁决（DG-01）**：

- ✅ **meeting-level teacher association = 已知真实语义**，**不是"无证据"**；
- ⛔ **但 Planner MVP 不依赖它** —— 因此 **meeting 的最小公共字段不包含教师**；
- ✅ 现有**教学班级 `teacher` 暂作为"教学班汇总 / 展示"字段保留**（顶层，不下放到 meeting）；
- ✅ 该表达限制明确登记为 **known deferred representation gap（已知但暂缓的表达损失）**：
  MVP 的 `meetings[]` **无法表达"某一段具体由哪位教师授课"** ——
  这是**已知的表达损失**，**不是"该语义不存在"**。
- 后续若 Planner 或前端确实需要 meeting 级教师关联，再按 `/AGENTS.md` 第 4 节走
  `【接口变更请求】`。

### 6.5 候选方案与权衡（**已裁决：采纳方案 A**）

> **裁决结果：采用方案 A**（在教学班内引入嵌套 segment 数组，即 `meetings[]`）。
> **Data Gate-2 不再讨论方案 B / C / D** —— 下表保留为**已评估但驳回的方案**记录，
> 以便后来者理解为何不采用。

| 方案 | 形态 | 优点 | 代价 / 风险 | 裁决 |
|---|---|---|---|---|
| **A. 在教学班内引入 segment 数组** | `CourseOffering` 增加 `meetings[]`；原 6 个单值字段不再作为排课真相 | 概念最清晰，与 6.2 的关系一致；Planner 可精确比较两个教学班的**全部**时间占用 | **破坏性**：现有 `course_offering.schema.json` 的 `weekday` / `start_section` / `end_section` / `weeks` 是**必填**；`mock_data/course_offerings.json`、`backend/app/models/contracts.py`、`frontend` 类型与展示、启动自检都会受影响 | ✅ **采纳** |
| **B. 保留单段字段，另加可选的段数组** | 原字段保留（作为"第一段"或"合并视图"），新增可选 segment 数组 | 对旧数据向后兼容（旧数据仍合法） | **双份表示**：同一信息两处存放，容易出现"字段与数组不一致"；Planner 必须同时读两处，语义不清晰 | ❌ **驳回**（不为一个错误的数据模型保留兼容层） |
| **C. 同一 `class_id` 多行（扁平化）** | 一个 segment 一行，多行共享同一 `class_id` | **完全不改 Schema** | ① 与"`class_id` 标识一个教学班"的现有隐含假设冲突；② `PlanResult.selected_classes[]` 只引用 `course_id` + `class_id`，**无法区分同一教学班的哪一段**；③ 消费方必须自行聚合，等于把契约问题推给每个下游 | ❌ **驳回** |
| **D. Course Data 内部保留完整 segment，对外只暴露合并后的时间占用** | 公共契约不变 | 完全不改 Schema | **丢失 segment 身份**：Planner 做"教学班替换"时无法精确比较"换掉这一段是否解决冲突"，Path Repair 质量下降 | ❌ **驳回** |

**为什么在这里接受破坏性变更**：

> 这是一次**有意的 breaking contract migration**。
> **现在还没有真实联调，正是该修的时候。**
> **不能为了旧 Mock 保留一个错误的数据模型。**

⚠️ 破坏性变更的**实施与回归范围**（`mock_data/`、`backend` 启动自检、`frontend` 类型与展示）
统一在 **Data Gate-2** 处理，**本轮不动任何文件。**

### 6.6 明确禁止的两个方案

> 以下两条**任何情况下都不允许**：

1. ❌ **只保存第一个 segment**（丢弃其他时间段）—— 直接**丢失真实排课信息**，
   使冲突检测产生**假阴性**（漏检冲突），Planner 会输出**不可执行的方案**；
2. ❌ **把一个教学班拆成多个可独立选择的 `CourseOffering`** —— 会凭空造出**学校并不存在的可选教学班**，
   学生"替换教学班"时会选到一个实际不存在的班，属**捏造数据**。

### 6.7 与 `meetings[]` 的关系：已裁决并已实施

`REAL_TO_SCHEMA_GAP_REPORT.md` 记录的是 **Data Gate-1 之前**的状态：
当时**未设计 `meetings[]`、未修改 Schema**。

**现在（Data Gate-2 之后）**：架构裁决采纳的方案 A 已经**落地实施** ——
`schemas/course_offering.schema.json` 已按 §6.8 的目标结构改为嵌套 `meetings[]`。
契约真源以该 Schema 文件为准。

### 6.8 目标结构（架构裁决锁定 · 已实施）

> **结构已经定了：教学班 ≠ 时间段。**（字段级实现已按此落地，见 §16。）

```text
CourseOffering
├─ course_id
├─ course_name
├─ class_id
├─ semester
├─ teacher?              # MVP 暂保留：教学班汇总 / 展示字段
├─ credit?
├─ capacity?
├─ remaining_capacity?
├─ source?
├─ data_source
└─ meetings[]
     ├─ weekday
     ├─ start_section
     ├─ end_section
     ├─ weeks[]
     ├─ campus?
     └─ classroom?
```

**关系**：

```text
CourseOffering   1
                 ↓
                 N
Meeting
```

**每段 meeting 的 MVP 排课字段**：`weekday` / `start_section` / `end_section` /
`weeks[]` / `campus` / `classroom`。

**⚠️ 不得由 Agent 自行调整的地方（实施后仍然适用）**：

- 不得新增 meeting 级教师字段（见 §6.4，已登记为 **known deferred representation gap**）；
- 不得把 `teacher` 下放到 meeting；
- 不得改变 `CourseOffering` 与 `Meeting` 的 **1 — N** 关系；
- ✅ **上述结构已在 Data Gate-2 落地**；契约文本以 `schemas/course_offering.schema.json` 为准
  （见 §16）。后续如需再调整，仍须走 `【接口变更请求】`。

---

## 7. Curriculum → Planner 契约分析

### 7.1 模块边界的权威来源：`/AGENTS.md` 第 5 节

| 模块 | 负责 |
|---|---|
| **Curriculum / 学业路径** | 培养方案解析；已修课程结构化；新旧方案差异分析；课程匹配与 MakeupTask 生成；**课程依赖图**；**补修风险与优先级**；**跨学期补修路径建议** |
| **Planner / Path Repair** | 时间 / 节次 / 周次**冲突检测**；当前课表冲突分析；**替代教学班搜索**；硬 / 软约束建模；确定性约束求解；**Path Repair**；无解 / 部分可行处理；PlanResult 生成 |

`/AGENTS.md` 第 5 节进一步规定：

> Planner 应**消费** Curriculum 模块提供的**补修任务、课程依赖结果和已确认优先级**，
> **不得为求解方便自行重写课程认定或学业优先级规则**。

### 7.2 接口文档债务：`docs/interfaces/planner.md` 与 `/AGENTS.md` 冲突

`docs/interfaces/planner.md` 现状（第 7–13 行"本模块负责"）把以下内容列为 **Planner 的职责**：

- **课程依赖图**；
- **补修优先级与风险**；
- 跨学期补修路径的 MVP 规划。

并在"建议接口"中列出：

```text
build_dependency_graph(courses)
calculate_priority(makeup_tasks, context)
```

**这与 `/AGENTS.md` 第 5 节直接冲突**：课程依赖图与补修优先级/风险属 **Curriculum** 的职责，
Planner 只是**消费方**。而 `/AGENTS.md` 第 17 节规定：**当两者冲突时，先遵守 `AGENTS.md`**。

**风险**：Planner 成员若照 `planner.md` 实现，就会**自建依赖图与优先级**，
等于绕过 Curriculum 的业务规则 —— 这正是 `/AGENTS.md` 第 5 节明令禁止的行为。

**处置**：登记为**接口文档债务**，修正请求见 **DG-06**。

**裁决（DG-06 APPROVED）**：**Data Gate-2 允许修正 `docs/interfaces/planner.md`**，
并根据需要同步 `docs/interfaces/curriculum.md`，使其与 `/AGENTS.md` 第 5 节一致。

⚠️ **本轮仍然不修改 interfaces** —— 本轮只**落档裁决**（`/AGENTS.md` 第 4 节）。

### 7.3 `MakeupTask.prerequisites[]` 是否已足够？（重点分析）

**现有字段**（`makeup_task.schema.json`）：`course_id` · `course_name` · `credit` · `status`（枚举 4 值）·
`deadline_semester?` · `recommended_semester?` · **`prerequisites[]?`** · `reason?` · `source_evidence?`

| 问题 | 分析 |
|---|---|
| Planner MVP 需要什么依赖信息？ | ① "补修 A 之前必须先补 B"的**先后关系**（跨学期路径排序）；② 冲突检测**不需要**依赖图（冲突只需时间 / 周次信息） |
| `prerequisites[]` 能表达什么？ | 它是**课程号字符串数组**，可表达"这门课的**直接**先修课程集合" → 足以构成**直接的依赖边** |
| 是否足够？ | **裁决：足够，不新增 `DependencyGraph`。**<br>① **不需要新增 `DependencyGraph` 公共 Schema** —— Planner 可由 `MakeupTask[]` 中每条任务的 `prerequisites[]` 构造**本地**邻接表示（只要相关课程都在同一 `MakeupTask[]` 中）；<br>② 它是**已存在的公共字段**，无需任何契约变更；<br>③ `recommended_semester` / `deadline_semester` 已可承载"时间先后"的粗粒度约束 |
| 可能的不足 | ① 只有**一级邻接**，不表达传递闭包（但可由**本地**图计算得到）；② **无"依赖类型"**（强先修 / 建议先修 / 并修），当前**无真实证据**支持需要区分；③ 无**优先级**（另见 7.4，**裁决为暂不新增**）；④ ⚠️ **最重要**：真实培养方案样本中**未发现明确的先修字段**，因此 `prerequisites[]` **能否被真实数据填充，目前尚无证据** |
| **裁决（DG-05）** | **不新增 `DependencyGraph` 公共 Schema。** MVP 由 `MakeupTask[]` + **已有** `prerequisites[]` 承载依赖边；权威边界见 §7.3.1 |

#### 7.3.1 权威边界（架构裁决，DG-05）

> 原草案写作"依赖图的**构建**（闭包 / 拓扑序）留在 Planner 内部"，
> **该表述不够精确，容易重新越界**。裁决后的准确边界如下：

```text
Curriculum：
  负责认定 / 产出 authoritative dependency edges（先修关系）

Planner：
  可以把已经收到的 prerequisites[]
  转换成本地 adjacency / topological representation
  供确定性求解使用

Planner：
  不得新增、猜测、重写任何 prerequisite edge
```

| 角色 | 允许 | 不允许 |
|---|---|---|
| **Curriculum** | **认定**先修关系，产出 dependency edges / `prerequisites[]` | —— |
| **Planner** | 把**已经收到的** `prerequisites[]` 构造成求解所需的**本地** adjacency / topology | **新增 / 猜测 / 重写**任何 prerequisite edge |
| **Planner** | 在**本地表示**上做确定性图计算（闭包 / 拓扑序 / 邻接查询） | 自行认定"哪门课应当是先修" —— 那是**学业规则**，属 Curriculum |
| **任何人** | 真实来源**无法提供** prerequisite 时，标记 **未知 / 待人工确认** | **自动补齐**，或用推断填补缺失的先修关系 |

> ⚠️ 这与 `/AGENTS.md` 第 5 节一致：Planner **消费** Curriculum 的依赖结果，
> **不得为求解方便自行重写课程认定或学业优先级规则**。

### 7.4 "已确认优先级"是否需要进入公共契约？

**事实**：`/AGENTS.md` 第 5 节要求 Planner 消费 Curriculum 的"**已确认优先级**"，
但 `makeup_task.schema.json` **没有 priority 字段**，`/schemas/` 下也**没有**优先级对象。

| 候选 | 分析 |
|---|---|
| **① 新增 `priority` 一类字段（方向性建议）** | 最能直接满足 `/AGENTS.md` 第 5 节。<br>⛔ **裁决：MVP 暂不新增**。字段名、类型、取值范围、枚举取值、是否必填**均未被定义**，将来须由负责人裁决（见 DG-05） |
| **② 用 `MakeupTask[]` 的数组顺序承载优先级** | 不改 Schema。但 **Schema 从未定义数组顺序的语义**，属**隐式约定**；`/AGENTS.md` 第 5 节禁止"只有两边懂的私有格式"，且下游可能重排数组 → **不可靠** |
| **③ 用 `recommended_semester` + `deadline_semester` 承载** | 不改 Schema。能表达"时间紧迫性"，但**不能表达学业优先级**（两门课可以同一学期、同一 deadline，优先级不同） |
| **④ 用 `reason` 自由文本承载** | **不可用于求解** —— `/AGENTS.md` 要求确定性判断不得交给 LLM / 自由文本，违反第 1、5 节 |
| **⑤ 优先级留在 Curriculum 内部，Planner 不做排序** | **不改任何接口**，可能符合 MVP。前提是负责人确认 **Planner MVP 是否真的需要跨模块优先级**；若 Planner 只需按 Curriculum 给出的顺序求解，则该字段可以暂不引入 |

**裁决（DG-05：NO NEW PUBLIC CONTRACT FOR MVP）**：

- ⛔ **暂不新增 `priority` 字段**，也**不新增** `PriorityResult` 一类对象；
- ⛔ **没有正式 priority 数据时，Planner 不得自行生成优先级** ——
  不得用启发式打分、LLM 判断或自定义排序替代 Curriculum 的学业优先级；
- ✅ 候选 ⑤（**优先级留在 Curriculum 内部**）**被采纳为 MVP 现状**；
- ✅ **后续 Curriculum 真正实现明确的优先级规则时，再走 `【接口变更请求】`**。

---

## 8. 当前 Schema / Interface 缺口

| 编号 | 缺口 | 证据等级 | 影响模块 | 处置 |
|---|---|---|---|---|
| **G1** | 培养方案 / 版本 / 课程分组**无正式表示** | **已由 `CURR-OLD-003` / `CURR-NEW-004` 确认** | Curriculum（+ Course Data / Planner 间接） | **DG-04** → 裁决：**MVP 暂留 Curriculum 内部，不新增公共 Schema** |
| **G2** | 已完成课程 / 修读事实**无正式表示** | **已由 `TRANSCRIPT-001` 验证** | Curriculum、Agent / Frontend | **DG-02** → 裁决：**MVP 不新增公共 Schema**，作为 **Curriculum 内部规范化对象** |
| **G3** | 学分差额无结构化表达 | **未验证** | Curriculum / Agent | 本轮不处理，留缺口报告 |
| **G4** | "当前课表"`planner.md` 列为输入，但无 Schema；`CourseOffering` ≠ 学生已选 | **文档级事实**（未用真实样本验证） | Planner、Integration | **DG-03** → 裁决：**不新增 Schema**；Planner 的 `current_schedule` **复用 `CourseOffering[]`** |
| **G5** | `PlanResult` 无冲突对象（只能从 `changes[].reason` 文本读出） | **未验证** | Planner / Agent | 本轮不处理，留缺口报告 |
| **G6** | `StudentProfile` | **已裁决**（不是可用契约，不得依赖） | 全部 | 已关闭（见缺口报告 §4.1） |
| **G7** | `CourseOffering` 无课程类别 / 开课单位 | **已由 `OFFERING-001` 验证** | Course Data / Planner | 见 §10 → 裁决：**均不进入公共契约** |
| **G8** | `Preference` 无法表达"已经有什么" | **未验证** | Agent / Planner | 本轮不处理；⚠️ 裁决后 `CompletedCourse` / `CurrentEnrollment` **不作为公共契约**，但明确 **不得用 `Preference.avoid_times[]` 冒充当前课表**（DG-03） |
| **G9** | **一个教学班多个 segment 无法无损表达** | **已由 `OFFERING-001` 验证** | Course Data / Planner | **DG-01** → 裁决：**APPROVED WITH MODIFICATION**，采用 `CourseOffering.meetings[]`，**Data Gate-2 实施** |
| **G10** | D5 另有多个字段无表示 | **已由 `OFFERING-001` 验证** | Course Data / Planner | 见 §10 → 裁决：**均不进入公共契约** |
| **新-1** | `docs/interfaces/planner.md` 职责描述与 `/AGENTS.md` 第 5 节**冲突** | **文档级事实**（可立即核实） | Planner / Curriculum | **DG-06** → 裁决：**APPROVED**，Data Gate-2 修正 `planner.md`，必要时同步 `curriculum.md` |
| **新-2** | "已确认优先级"无承载位置 | `/AGENTS.md` 第 5 节要求 + Schema 无字段 | Curriculum / Planner | **DG-05** → 裁决：**MVP 暂不新增 `priority` 字段**；**Planner 不得自行生成优先级** |
| **新-3** | 课程依赖结果无正式公共对象 | `/AGENTS.md` 第 5 节要求 + 无 Schema | Curriculum / Planner | **DG-05** → 裁决：**不新增 `DependencyGraph`**；权威边界见 §7.3.1 |
| **新-4** | `Course` 上的 `course_type` / `recommended_semester` **位置不当**（带方案上下文） | 2B-0C Review 已改判 | Curriculum | **DG-04** → 裁决：**MVP 暂留 Curriculum 内部**；两者是**现有兼容字段**，**不得被解释为课程全局固有属性** |
| **新-5** | 推荐学期**跨学期区间**无法用单个整数表达 | `CURR-OLD-003` / `CURR-NEW-004` | Curriculum | 并入 **DG-04** → 裁决：由 **Curriculum 内部结构**保留；现有 `recommended_semester` **不能无损表示** |

**⚠️ 缺口 ≠ 必须新增 Schema。** 每条都可能是：数据侧转换 / 模块内部输入 / 数据不应进系统 /
确属契约承载不了。§13 的每项请求都单独回答"是否存在不修改接口的替代方案"。

---

## 9. 最小接口变更集合（裁决后）

> **最小化原则**：能用现有字段表达的，不新增字段；能作为模块内部输入消化的，不进公共契约；
> 只有确属"契约承载不了"的，才进入变更请求。
>
> **裁决让这个集合比原草案更小**：真实联调真正被阻塞的只有 **多 segment 建模**，
> 外加一项**纯文档职责修正**。

### 9.1 进入 Data Gate-2 实施的契约变更（**2 项 · 均已完成**）

| 项 | 变更对象 | 性质 | 为什么必须 | 状态 |
|---|---|---|---|---|
| **DG-01** | `schemas/course_offering.schema.json` | **结构性 / breaking migration** | 真实教学班数据**无法无损进入系统**；冲突检测、教学班替换、Path Repair 全部建立在教学班的时间占用上。旧契约下只能丢信息或造数据 | ✅ **已实施** |
| **DG-06** | `docs/interfaces/planner.md`＋`docs/interfaces/curriculum.md` | **纯文档，无字段变更** | 消除接口文档与 `/AGENTS.md` 第 5 节的冲突，防止 Planner 成员越界自建依赖图与优先级 | ✅ **已实施** |

**连带影响（已随 DG-01 一并处理，不算新增契约）**：
`mock_data/course_offerings.json`、`backend/app/models/contracts.py`（启动自检按 JSON Schema 校验原始 JSON）、
`frontend` 类型与展示 —— 全部已同步，后端 `pytest` 与前端 `npm run build` 均通过（见 §16）。

### 9.2 裁决为"不产生公共契约变更"的项（**4 项**）

| DG | 裁决 | MVP 形态 |
|---|---|---|
| **DG-02** `CompletedCourse` | DEFER PUBLIC CONTRACT | **Curriculum 内部规范化对象**；D4 Sanitized Sample 由负责人经**非公开位置**交 Curriculum；对外**仍只输出 `MakeupTask[]`** |
| **DG-03** `CurrentEnrollment` | REUSE EXISTING CONTRACT | Planner 的 `current_schedule` **复用现有公共类型 `CourseOffering[]`**，语义 = 学生已选中的教学班子集 |
| **DG-04** `CurriculumVersion` / `CurriculumCourse` | DEFER PUBLIC CONTRACT | **Curriculum 内部模型**；`Course.course_type` / `recommended_semester` 保持为**现有兼容字段**，**不得被解释为课程全局固有属性** |
| **DG-05** dependency / priority | NO NEW PUBLIC CONTRACT | **不新增** `DependencyGraph` / `priority` / `PriorityResult`；Planner 只消费 `MakeupTask.prerequisites[]` |

### 9.3 本轮不进入变更集合的项

- **G3 学分差额**（未验证）；
- **G5 `PlanResult` 冲突对象**（未验证；MVP 可由 `changes[].reason` + `unresolved[]` 粗略承载，但**不足以计数 / 分类**，留待验证）；
- **G7 / G10 的暂缓字段**（见 §10）；
- **`StudentProfile`**（已裁决，不得依赖）；
- **`Preference` / `PlanResult` / `Course` 的字段本身**（本轮无变更请求）。

---

## 10. 暂缓字段（不进入公共契约）

> 分类口径：
> **A. MVP 跨模块必须** ｜ **B. Course Data 内部即可** ｜ **C. 当前不进入系统** ｜ **D. 语义未知，继续待确认**

| 真实 D5 字段 | 分类 | 去向 / 处置 | 依据 |
|---|---|---|---|
| `selectedNumber`（已选人数） | **B** | **不要求直接进公共契约**；`remaining_capacity` 作为**派生结果**（`limitNumber - selectedNumber`）。⚠️ **不得声称学校接口直接提供剩余容量** | 现有 `remaining_capacity` 已能满足 Planner 对"还有没有名额"的需求，无需暴露原始计数 |
| `openingUnitName`（开课单位） | **B** | **不因真实存在就自动进公共 Schema**。若 Course Data 内部需要（数据质量 / 去重 / 归属判断）可内部保留；**MVP 无跨模块消费者** | G7 已验证其存在，但"存在"≠"公共契约需要" |
| `courseCategoryName`（课程类别，样本"专必"） | **B（且归属需转移）** | **培养方案上下文属性，不能当课程全局属性** → **裁决：MVP 随 DG-04 暂留 Curriculum 内部模型**，**不进入 `CourseOffering`**。⚠️ 取值体系与粒度**待人工确认** | 与 D4 的 `course_type` **同源问题**；真实培养方案中该信息以**分区标题 / 行内"课程性质"列**形态出现 |
| `examMode`（考核方式） | **C** | 当前不进入系统 | **Planner MVP 当前非必需** |
| `readObj`（修读对象） | **C（＋待确认）** | 当前不进入系统。⚠️ **未来可能影响"可选资格"**（学生能否选这个教学班），但**当前规则不足**，不得据此判断资格；**完整文本不入库** | 语义已知、**规则不足**；需人工确认后才能升级 |
| `teachProgressSubmitState` | **D** | **语义未知，继续待确认** | ⚠️ **不得根据 0/1 值自行解释** |
| `openClass` | **D** | **语义未知，继续待确认** | 同上 |
| `outlineTypeNum` | **D** | **语义未知，继续待确认** | 同上 |
| `class_ID` / `sumClassesID` / `sumClassesNum` / `courseId` / `outLineId` / `timePlaceId`（内部 ID / 计数） | **C** | 当前不进入系统；**不等于**公共 `course_id` / `class_id`；**不记录其值** | 后台内部标识 |
| `teachingTimePlaceStr`（原始时间地点串） | **B（转换层）** | 属**数据转换层能力**（Course Data 内部解析为 segment 量）；**原始串不入库、不进契约** | 单个 segment 可解析；整个教学班落入 **G9 / DG-01** |
| `openingSchoolName`（开课校区 / 学校） | **D（转换关系待确认）** | 与 `campus` **有关联**，**具体转换关系待确认**；**不猜** | 侦察记录已标记待确认 |
| `weekDay`（星期） | **D（对应关系待确认）** | 与 `weekday` **有关联**；**它与 segment 的对应关系待确认**（多 segment 时如何取值不明） | 多 segment 场景下的映射关系未确认 |
| **D4 侧** `offering_unit`（开课单位） | **B** | 同 `openingUnitName`：**不因真实存在自动进公共契约**；归属**待确认** | 2B-0C 已登记为"归属待确认" |
| **D4 侧** `cultivation_type`（培养类别，样本"主修"） | **D** | **归属与完整取值域待确认**；⚠️ **不得把 `cultivation_type` 强行当成 `course_type`** | 二者**不是同一语义** |

### 10.1 暂缓字段的三条纪律

1. **真实存在 ≠ 公共契约需要。** 字段在真实 JSON 里出现，只说明"学校有这个量"，
   不说明"MVP 跨模块必须传递它"。
2. **语义未确认的字段一律不得正式化。** `teachProgressSubmitState` / `openClass` / `outlineTypeNum`
   保持"字段存在，业务语义待确认"，**不解释 0/1**。
3. **上下文属性不得下放到全局对象。** `courseCategoryName` / `course_type` 属培养方案上下文。

### 10.2 裁决确认

本节全部字段的**"不进入公共契约"处置已随 DG-01 – DG-06 裁决一并确认**：

- ⛔ 这些字段**不因真实存在**而自动进入任何公共 Schema；
- ⛔ **不得**用 `Preference.avoid_times[]` 冒充"当前课表"（DG-03）——
  `avoid_times` 是**偏好回避**，**不是**学生已选教学班的事实表达；
- ⛔ **D 类字段**（`teachProgressSubmitState` / `openClass` / `outlineTypeNum` /
  `openingSchoolName` / `weekDay` / `cultivation_type`）在**语义确认前**一律不得正式化。

---

## 11. Course Data 获取边界

### 11.1 未来链路（**本轮不实现任何一环**）

```text
SYSU authenticated source          （负责人本人正常登录、已有权限范围内的人工 / 授权访问）
        ↓
Course Data Adapter / Importer     （Course Data 模块）
        ↓
Normalizer                         （周次 / 节次 / 星期 / 校区标准化；字符串数字 → number）
        ↓
Semester Offering Snapshot         （某学期开课快照，带抓取时间与 Mock / Real 标记）
        ↓
CourseDataProvider                 （对上游统一的读取入口）
        ↓
Integration                        （编排）
        ↓
Planner                            （冲突检测 / 替换 / 求解）
```

### 11.2 边界红线

| 角色 | 必须 | 不得 |
|---|---|---|
| **Planner** | 消费符合 `course_offering.schema.json` 的 `CourseOffering[]` | **不接触学校接口**；不知道 Cookie / 认证方式 / endpoint / 分页参数 |
| **Integration** | 通过 `CourseDataProvider` 读取标准化结果 | **不知道 Cookie、SYSU endpoint、分页规则**等实现细节 |
| **Course Data** | 在授权范围内获取、清洗、标准化、去重、记录来源与 `data_source` | 不判断学生是否需要补修；不决定补修优先级；不越过 `docs/interfaces/course_data.md` 的安全边界 |
| **任何人** | —— | 不绕过登录、不破解验证码、不越权访问、不枚举未授权数据、不保存密码 / Cookie / Session / Token、不提交 HAR |

### 11.3 C9 裁决：目标与获取边界（Architecture Lead 已确认 ✅）

**目标**：**2026-1 semester offering snapshot**（某学期的完整开课快照）。

**获取边界（硬性）**：

- ✅ 用户**本人正常登录**；
- ✅ **已有权限**（只取本人有权查看的数据）；
- ✅ **用户明确触发**的授权导入；
- ⛔ **不保存**密码 / Cookie / Session / Token；
- ⛔ **不绕过**认证 / CAPTCHA；
- ⛔ **不越权**；
- ⛔ **不在未确认请求规模前进行高频批量调用**。

**角色分工（C9 明确）**：

```text
Course Data：
  获取 / 导入 → 解析 → 标准化 → 去重
  → 记录 source / data_source → semester snapshot

Integration：
  只通过 CourseDataProvider 使用标准化结果
  不知道 SYSU endpoint / Cookie / pagination

Planner：
  只消费标准化 CourseOffering[]
```

> ⚠️ **`pageSize` / 请求规模**：**批量导入实现时必须确认合理的 `pageSize` 与请求规模**，
> 不得在未确认规模前发起批量抓取。

**⚠️ Completeness（完整性）纪律**：

- **"目标是一学期完整 Snapshot" ≠ "当前已取得完整数据"**；
- 当前实际只有 **D5 小规模人工侦察**（`CSE202` / `2026-1` → 2 个教学班），
  **远不是**完整快照；
- 若批量导入**只能取得部分范围**，**必须显式记录 completeness**
  （例如覆盖的课程数 / 是否全量 / 截断原因）；
- ⛔ **不得把 partial snapshot 宣称为 complete。**

### 11.4 本轮明确不做

- ❌ **不实现** Course Data Adapter / Importer / Normalizer / Provider；
- ❌ **不写** crawler / 抓取脚本；
- ❌ **不调用** SYSU 接口（本轮**零请求**）；
- ❌ **不建**数据库、**不写** ORM / migration；
- ❌ **不进入** Integration。

### 11.5 完整 2026-1 开课数据获取的定位

**完整 2026-1 开课数据获取属于 Data Gate 之后的 Course Data MVP，不在本轮范围。**

当前 D5 只有**小规模人工侦察**（`CSE202` / `2026-1` → 2 个教学班）。
正式获取必须等：① ~~DG-01 的表示方式定了~~ → **已裁决（嵌套 `meetings[]`）**，
待 **Data Gate-2 实施契约变更**；② 采集范围经负责人批准；③ 合规边界确认（**C9 已确认方向**）。
（人工技术侦察**已到此结束**，不再继续查询更多课程。）

---

## 12. Data Gate 通过条件

> **本节共 11 条：C1 – C11。**
> 以下条件**全部满足**，才视为通过 Data Gate，可以恢复 Phase 2B Integration / Course Data MVP。
> 任一条未满足，**Phase 2B Integration 保持暂停编码**。
>
> **当前进度（Architecture Lead 已确认）**：
> **C1 / C2 / C3 / C4 / C6 / C7 / C8 / C9 / C10 / C11 已确认**；
> **仅 C5 待 Data Gate-2 执行**（契约变更流程与连带回归范围）。

| # | 条件 | 当前状态 | 判定方 |
|---|---|---|---|
| **C1** | **DG-01 – DG-06 逐项裁决完毕**（批准 / 驳回 / 修改），且裁决结论**书面记录**在本文件 | ✅ **已确认**（Architecture Lead） | 负责人 |
| **C2** | **实体边界与所有者无异议**：Curriculum / Course Data / Planner / Integration / Frontend 五方对 §3 / §4 的划分达成一致 | ✅ **已确认**（实体边界与所有者确认） | 负责人 + 各模块 |
| **C3** | **Shared / Private / Derived 分类确认**（§5），特别是"用户适用的 `CurriculumVersion` reference 属私有"这一条 | ✅ **已确认**（分类确认；⚠️ 注意 §5.1：**School-shared ≠ 可以公开**，**不得把教师信息归为 Student-private**） | 负责人 |
| **C4** | **多 segment 表示方式确定**（§6 / DG-01），且明确**未**采用"只保留第一段"与"拆成多个可独立选择的 `CourseOffering`"两个被禁方案 | ✅ **已完成**：**嵌套 `meetings[]`（方案 A）已实施**（见 §16） | 负责人 + Course Data + Planner |
| **C5** | **契约变更已走完流程**：`/AGENTS.md` 第 4 节的 `【接口变更请求】` → 人工确认 → **才**修改 `/schemas/` 与 `/docs/interfaces/`；并**同步**评估对 `mock_data/`、`backend/app/models/contracts.py`（启动自检）、`frontend` 类型与展示的影响与回归测试范围 | ✅ **已完成**（DG-01 / DG-06 均已实施，后端 `pytest` 与前端 `npm run build` 通过；见 §16） | 负责人 + 各模块 |
| **C6** | **暂缓字段清单确认**（§10）：`teachProgressSubmitState` / `openClass` / `outlineTypeNum` 等**不进入公共契约**，保持待确认 | ✅ **已确认**（随裁决一并确认；实施时**未**加入任何暂缓字段） | 负责人 |
| **C7** | **Curriculum → Planner 契约确定**（§7 / DG-05）：优先级**不新增字段**、Planner 不得自行生成；依赖由 `MakeupTask.prerequisites[]` 承载，权威边界见 §7.3.1 | ✅ **已完成**（`planner.md` / `curriculum.md` 已按此修正） | 负责人 + Curriculum + Planner |
| **C8** | **接口文档债务修正决定**（DG-06）：`docs/interfaces/planner.md` 按 `/AGENTS.md` 第 5 节修正，并同步 `curriculum.md` | ✅ **已完成** | 负责人 |
| **C9** | **Course Data 获取边界与合规方向确认**（§11.3）：目标 **2026-1 semester offering snapshot**；边界 = 本人正常登录 / 已有权限 / 用户明确触发授权导入 / 不保存密码·Cookie·Session·Token / 不绕过认证·CAPTCHA / 不越权 / 未确认请求规模前不高频批量调用；Course Data 负责 获取→解析→标准化→去重→`source`/`data_source`→snapshot，Integration 只经 `CourseDataProvider`，Planner 只消费标准化 `CourseOffering[]`；**必须确认合理 `pageSize` / 请求规模**；**partial snapshot 必须显式记录 completeness，不得宣称 complete** | ✅ **已确认**（获取边界与合规方向） | 负责人 + Course Data |
| **C10** | **数据交接方式确认**：`MEMBER_DATA_HANDOFF.md` 已更新为当前状态（GitHub 可直接共享 / 非公开按需交接 / 禁止交接三层），且**真实逐行数据的交接次数如实记录**（DG-02 已允许 D4 Sanitized Sample 经非公开位置交 Curriculum） | ✅ **已确认**；**真实逐行数据交接次数 = 0**（不变） | 负责人 |
| **C11** | **真实数据未使用的字段风险已知悉**：① `prerequisites[]` **暂无真实来源证据**；② `weekDay` 对应关系**待确认**；③ `openingSchoolName → campus` **待确认**；④ **meeting-level teacher 为 known deferred representation gap** | ✅ **已确认**；⛔ **不允许实现层自行补齐** | 负责人 |

### 12.1 Gate 关闭后的约束

> Data Gate 已 **PASSED / CLOSED**。以下约束在关闭后**依然适用**：

- **修改 `/schemas/` 或 `/docs/interfaces/` 仍须走** `/AGENTS.md` 第 4 节的
  `【接口变更请求】` → 人工确认流程（C5 的做法不变，只是本次已获授权并执行完毕）；
- **仍不得**写 Course Data Adapter / Normalizer / `CourseDataProvider`
  —— 它们属于 Data Gate 关闭后的 **Course Data MVP**，需等新一轮任务书明确授权；
- **仍不得**进入 Phase 2B Integration / Orchestrator 编码（同样等授权）；
- 不得在代码中定义"只有两边懂"的私有跨模块结构来绕过公共契约（`/AGENTS.md` 第 5 节）；
- 不得把 Mock 数据当作 Real，或把 Real 数据当作 Mock。

### 12.2 Data Gate 结论

```text
C1  ✅   C2  ✅   C3  ✅   C4  ✅   C5  ✅   C6  ✅
C7  ✅   C8  ✅   C9  ✅   C10 ✅   C11 ✅

Data Gate-1 + Data Gate-2：PASSED / CLOSED
```

**唯一被阻塞的真实联调契约问题（G9 多 segment）已修复**，
实施记录见 **§16**。下一步是 **Course Data MVP**（真实 2026-1 semester offering snapshot），
**不在本轮范围内**，须等新一轮任务书。

### 12.3 Data Gate Reopen（2026-10-01，**仅 DG-07**）

```text
原状态：Data Gate-1 + Data Gate-2：PASSED / CLOSED（C1–C11 全部完成）
新证据：G11 —— 真实 2026-1「全校开设课程」第 1 页存在
        39 / 200 条 row 缺少 teachingTimePlaceStr（C1B / C1C）+ 2 条人工 UI 核验（C1D）
处置：  Reopened narrowly for DG-07 only
当前：  ⚠️ 仍保持 Reopened（DG-07 已批准，但尚未实施 / 尚未回归 / 尚未验收）
DG-07： APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING
```

- ✅ **只**为 **DG-07**（`CourseOffering` 空 `meetings` / 未知排课信息）重新开启；
- ⛔ **DG-01 – DG-06 不重新打开**，其裁决与实施结果**保持不变**；
- ⛔ 不重新讨论其它已经裁决完成的问题（多 segment 选型、`CompletedCourse` /
  `CurrentEnrollment` / `CurriculumVersion` / dependency / priority / 接口文档债务）；
- ✅ **DG-07 已获批准（2026-10-01）**：
  **`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**（见 §17.5.1 裁决）；
- ⛔ **本轮仍未修改** `schemas/` 与 `docs/interfaces/`：
  **批准 ≠ 实施**；实施须等**单独的 Implementation 任务书**；
- ⚠️ **Data Gate 只有在下述全部完成并经 Reviewer 验收后，才允许回到 CLOSED**
  （并登记 **DG-07 IMPLEMENTED**）：
  1. **DG-07 Contract Migration**（`schemas/` + `docs/interfaces/` + `contracts.py` + Mock）；
  2. **Course Data**（fail-closed 不变量落地：仅"属性不存在"可映射为 `[]`）；
  3. **Planner safety**（`meetings = []` ≠ conflict-free，含 `current_schedule`）；
  4. **Frontend / Mock**（类型与展示，文案候选「排课信息暂缺」）；
  5. **tests**（含迁移既有"`meetings: []` 必须失败"的回归用例）；
- ⚠️ §12.1 的三条约束（含"改契约仍须走 `【接口变更请求】` → 人工确认"）**继续适用**；
- ⚠️ 以上为**完成条件**，**不是**实施授权：⛔ **不得**在本轮开始任何实施阶段
  （也不得自行命名 / 拆分实施阶段，交由 Architecture Lead 在实施任务书中规定）。

---

## 13. 接口变更请求与裁决（DG-01 – DG-06）

> 本节保留 Data Gate-1 提交的**原始请求文本**（便于追溯），并在每项之后附上
> **裁决（Architecture Lead，2026-09-30）**。
> ⚠️ **裁决 ≠ 实施**：公共契约**尚未修改**，实施统一在 **Data Gate-2**。
> ⚠️ 格式遵循 `/AGENTS.md` 第 4 节。

### DG-01 `CourseOffering` multi-segment（G9）

```text
【接口变更请求】
当前设计：
  `schemas/course_offering.schema.json` 用**一组**字段表达教学班的时间地点：
  `weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom`
  （其中 `weekday` / `start_section` / `end_section` / `weeks` 为**必填**）。
  隐含假设：**一个 CourseOffering = 一个时间段**。

建议修改：
  方向性建议：**让一个教学班能够承载多个独立的 schedule segment**，即承认
  `CourseOffering 1 — N ScheduleSegment` 的概念关系（见 §6.2）。
  候选形态（**均待裁决，本文档不选型**）：
    A. 在教学班内引入 segment 数组；
    B. 保留现有单段字段，另加可选 segment 数组（兼容旧数据，但存在双份表示）；
    C. 同一 `class_id` 多行扁平化（不改 Schema，代价见 §6.5）；
    D. Course Data 内部保留 segment、对外只暴露合并后的时间占用（会丢失 segment 身份）。
  每个 segment 至少需要表达：`weekday` / `start_section` / `end_section` /
  `weeks[]` / `campus` / `classroom`（§6.3）。
  ⚠️ 字段名、类型、是否必填、数组命名（`meetings` / `segments` / 其它）**全部待裁决**。

原因：
  真实 D5 样本 `OFFERING-001` 已确认：**一个教学班可以拥有多个独立的上课时间 / 地点 segment**，
  而当前 `CourseOffering` **无法在一个对象中无损表达**（G9）。
  若不解决，只有两种坏结果：丢失 segment（冲突检测假阴性 → 输出不可执行方案），
  或把一个教学班拆成多个可独立选择的 `CourseOffering`（捏造学校不存在的教学班）——
  这两条都已被明确禁止。

影响模块：
  Course Data（生产方）、Planner（冲突检测 / 教学班替换 / Path Repair）、Agent / Integration、
  Frontend（课表展示）；同时波及 `mock_data/course_offerings.json`、
  `backend/app/models/contracts.py`（启动自检按 JSON Schema 校验原始 JSON）与前端类型。

是否为破坏性修改：
  **取决于选型**：
    方案 A → **是**（现有 4 个必填字段的语义与位置改变，Mock 数据、后端契约层、前端类型
             与展示均需同步，且会触发启动自检失败）；
    方案 B → **兼容性扩展**（旧数据仍合法），但引入"同一信息两处存放"的**一致性风险**；
    方案 C / D → **不改 Schema（非破坏性）**，但代价见 §6.5。
  ⚠️ 最终由负责人裁决；**本轮不实施任何变更**。

是否存在不修改接口的替代方案：
  有，但都不满足"无损"要求（详见 §6.5）：
    ① 同一 `class_id` 多行扁平化：不改 Schema，但与"一个 `class_id` 标识一个教学班"的现有
       隐含假设冲突；且 `PlanResult.selected_classes[]` 只引用 `course_id` + `class_id`，
       **无法区分同一教学班的哪一段**；等于把契约问题推给每个下游；
    ② 只在 Course Data 内部保留完整 segment、对外暴露合并后的时间占用：不改 Schema，
       但**丢失 segment 身份**，Planner 无法精确比较"换掉这一段是否解决冲突"；
    ③ 只保存第一段 ❌ **明确禁止**（丢失真实排课信息，导致冲突漏检）；
    ④ 拆成多个可独立选择的 `CourseOffering` ❌ **明确禁止**（捏造不存在的教学班）。
  → 结论：存在"不改接口"的方案，但都有实质代价，需负责人权衡后裁决。
```

#### 裁决（Architecture Lead，2026-09-30）：**DG-01 = APPROVED WITH MODIFICATION**

- ✅ 采用方案 A：**`CourseOffering` 1 — N `Meeting` / `ScheduleSegment`**；
  **Data Gate-2 将正式修改 `schemas/course_offering.schema.json`**；
- ⛔ **不再保留 B / C / D 为待选方案** —— 三者作为**已评估但驳回**的方案记录（见 §6.5）；
- ✅ **最终选择 = 嵌套 segment 数组方案**；目标结构见 **§6.8**；
- ✅ 每个 segment 的 MVP 排课字段：`weekday` / `start_section` / `end_section` /
  `weeks[]` / `campus` / `classroom`；
- ✅ 现有**教学班级 `teacher` MVP 暂保留**（教学班汇总 / 展示字段）；
- ⚠️ **修正教师证据**：**不得**再写"没有证据表明教师存在 meeting-level 语义"。
  真实 D5 的 `teachingTimePlaceStr` **segment 本身包含教师项**，且**已有样本表明 segment 与教师存在关联**。
  裁决为：**meeting-level teacher association = 已知真实语义**，但 **Planner MVP 不依赖它**，
  因此**暂不纳入本轮 meeting 最小公共字段**；登记为 **known deferred representation gap**（见 §6.4）；
- ⚠️ 这是一次**有意的 breaking contract migration**；实施与回归范围在 **Data Gate-2** 处理。

### DG-02 `CompletedCourse`

```text
【接口变更请求】
当前设计：
  `/schemas/` 下**没有**"已完成课程 / 修读事实"的对象。
  D4 的 8 个字段中，`course_id` / `course_name` / `credit` 可落到 `Course`，
  但 `semester`（实际修读学期）与 `passed`（该次修读是否通过）**在 `Course` 中没有任何承载位置**。
  `docs/interfaces/curriculum.md` 把"已修课程记录"列为 Curriculum 的输入，
  但没有规定其结构化形态。

建议修改：
  方向性建议：**正式化一个"某学生已经修过某门课的事实"的公共对象**（名称待裁决）。
  至少需要承载真实 D4 已确认的：`course_id` / `course_name` / `credit` / `semester` / `passed`。
  ⚠️ 字段名、类型（尤其是 `semester` 的表示与 `passed` 的 boolean 语义）、
     是否必填、是否需要 `offering_unit` / `cultivation_type`，**全部待裁决**。
  ⚠️ 归属上属**用户私有数据**（§5.2），不得进入 public 仓库。

原因：
  G2 已由真实 D4 样本 `TRANSCRIPT-001`（24 条、8 字段 100% 覆盖）验证：
  学生修读事实**无法由 `Course` 完整表达**。
  两条红线必须坚持：**`semester` 不得映射到 `recommended_semester`**
  （实际修读学期 ≠ 培养方案建议学期）；
  **`passed` 不得塞入 `Course`**（学生修读事实 ≠ 课程固有属性）。

影响模块：
  Curriculum（生产方）、Agent / Integration（消费 / 展示）、Frontend（已修课程展示）；
  Planner **间接受影响**（Curriculum 据此生成 `MakeupTask[]`）。

是否为破坏性修改：
  **否**（新增对象；`Course` / `MakeupTask` 等现有 Schema 不变）。
  ⚠️ 但如果裁决同时要求**从 `Course` 移除**某些字段，则该部分为破坏性，需另行登记。

是否存在不修改接口的替代方案：
  **有，且是真实可行的方案**：
    ① 作为 **Curriculum 模块内部结构**，不进公共契约 —— `/AGENTS.md` 明确允许
       "缺口最终以模块内部输入存在"；且 Curriculum → Planner 只需交付 `MakeupTask[]`，
       `CompletedCourse` 未必需要跨模块传递；
    ② 作为 **Integration DTO**（集成层临时结构）。
  代价：下游（Agent / Frontend）**无法独立验证或展示"已修课程"**；
  "已修课程"这一事实**只能以 `MakeupTask` 的派生形式间接可见**；
  且 Curriculum 内部的私有结构**不得**被当作跨模块契约传递（`/AGENTS.md` 第 5 节）。
  → 是否正式化，取决于负责人对"已修课程是否需要跨模块可见"的裁决。
```

#### 裁决（Architecture Lead，2026-09-30）：**DG-02 = DEFER PUBLIC CONTRACT**

- ✅ **概念成立**：`CompletedCourse` 表示"某学生已经修过某门课的事实"；
- ⛔ **MVP 不新增** `schemas/completed_course.schema.json`；
- ✅ **先作为 Curriculum 内部规范化对象**存在；
- ✅ **真实 D4 Sanitized Sample 可以由负责人通过非公开位置交给 Curriculum 成员**
  （仍须走 `MEMBER_DATA_HANDOFF.md` 的交接 Checklist；**不得进入 public 仓库**）；
- ✅ Curriculum **对外继续只输出 `MakeupTask[]`**；
- 🔁 **后续若 Integration / Frontend 确实需要跨模块消费 `CompletedCourse`，再重新走接口变更。**
- ⚠️ 红线不变：**`semester` / `passed` 绝不塞回 `Course`**。

### DG-03 `CurrentEnrollment`

```text
【接口变更请求】
当前设计：
  `/schemas/` 下**没有**"学生当前已选 / 在读教学班"的对象。
  `docs/interfaces/planner.md` 把"当前课表"列为 Planner 的**对外输入**，
  但没有规定其结构（G4）。
  现有最接近的对象是 `CourseOffering`，但它表示的是"**学校开设什么**"（供给），
  **不等于**"学生已选什么"。

建议修改：
  方向性建议：**引入一个独立的"学生当前已选 / 正在修读的教学班"对象**（名称待裁决），
  明确区别于 `CompletedCourse`（已修完）、`CourseOffering`（供给）、`Preference`（意愿）。
  至少需要能让 Planner 得到"当前已占用的时间 / 教学班"。
  ⚠️ 字段名、类型、是否含 segment 级信息、是否复用 `class_id` 引用，**全部待裁决**。
  ⚠️ 归属上属**用户私有数据**（§5.2）。

原因：
  Planner 的核心职责之一是**当前课表冲突检测** —— 没有"学生当前占用"的概念，
  冲突检测就**没有输入**。
  若用 `CourseOffering` 代替，等于把"学校开设的全部教学班"当成"我的课表"，
  冲突检测会**完全失真**。

影响模块：
  Integration / Agent（获取用户本人课表并转换）、Planner（消费）、Frontend（课表展示）；
  Course Data **可能**在授权范围内参与获取，但**归属仍是用户私有**。

是否为破坏性修改：
  **否**（新增对象；现有 Schema 不变）。

是否存在不修改接口的替代方案：
  **有（MVP 降级方案）**：
    ① 用**已存在的** `Preference.avoid_times[]`（每项 `weekday` / `start_section` / `end_section`）
       近似表达"这些时间不能排课" —— 用户把当前课表时间填入 `avoid_times`，**完全不改接口**。
  代价：**语义扭曲**（`avoid_times` 是"偏好回避"还是"硬占用"在 Schema 中并不明确）、
       **丢失课程 / 教学班身份**（无法区分"被必修课占用"与"单纯不想排课"）、
       **无法做教学班替换**（不知道占用来自哪个班，也就无法"换掉它"）、
       且与 `Preference.avoid_cross_campus` 等偏好语义混在一起。
    ② Planner 直接接收 Integration 传入的私有结构 —— ❌ **违反** `/AGENTS.md` 第 5 节
       （禁止私有的跨模块格式）。
  → 结论：`avoid_times` 可作为 MVP 降级方案，但语义不足；需负责人裁决。
```

#### 裁决（Architecture Lead，2026-09-30）：**DG-03 = APPROVE CONCEPT, REUSE EXISTING CONTRACT**

- ✅ **概念保留**：`CurrentEnrollment` 表示"学生当前已选 / 正在修读的教学班"；
- ⛔ **MVP 不新增 `CurrentEnrollment` Schema**，**避免重复一套等价结构**；
- ✅ Planner 接口中的 **`current_schedule` 直接使用现有公共类型 `CourseOffering[]`**，
  语义上表示"**学生已选中的教学班子集**"；
- ⚠️ **接口文档中必须明确区分**：

  ```text
  CourseOffering[]                     —— 学校全部供给
  current_schedule: CourseOffering[]   —— 学生已经选择的子集
  ```

  两者**类型相同、语义不同**，**不得混用**；
- ⛔ **不允许使用 `Preference.avoid_times[]` 冒充当前课表** ——
  该字段是**偏好回避**，不是"已选教学班"的事实表达（因此 §13 原"降级替代方案"**被驳回**）；
- ✅ 该语义区分应在 **Data Gate-2 的 `planner.md` 修正**中写清（DG-06）。

### DG-04 `CurriculumVersion` / `CurriculumCourse`

```text
【接口变更请求】
当前设计：
  `/schemas/` 下**没有**培养方案 / 版本 / 课程分组对象（G1）。
  "某门课在某份培养方案中的要求"**没有承载位置**：
    培养方案级总量（总学分 147.0 / 153.0、实践教学学分 37.1 / 38.5）、
    适用年级（"25级"）、专业、课程分组 / 模块、
    以及**跨学期区间**形态的推荐学期（如 `2025-1~2025-2`）**均无表示**。
  同时，带**方案上下文**语义的 `course_type` 与 `recommended_semester` **当前挂在 `Course` 上**，
  位置不当（2B-0C Review 已把 `course_type` 改判为"培养方案 / 上下文属性"）。

建议修改：
  方向性建议：
    ① 引入 **`CurriculumVersion`**：表示"某专业、某年级、某版本的一份培养方案"；
    ② 引入 **`CurriculumCourse`**：表示"某门 `Course` 在某个 `CurriculumVersion` 中的要求"，
       用于承载 `course_type`、推荐修读学期、**课程分组**、先修要求等**上下文属性**；
    ③ 现有 `Course` 上 `course_type` / `recommended_semester` 的**最终处置**
       （保留兼容 / 迁移 / 废弃）**待裁决**。
  ⚠️ 对象命名、字段名、类型、是否必填、跨学期区间如何表示、分组如何建模
     （独立对象 / 枚举 / 字符串）**全部待裁决**，本文档不锁定任何一项。

原因：
  G1 已由 `CURR-OLD-003`（25级 遥感）与 `CURR-NEW-004`（25级 网安）两份真实培养方案确认存在：
  培养方案**按专业与年级版本化**，且带有**方案级**的总量与模块口径。
  更重要的是**语义正确性**：同一门课在不同专业 / 培养方案下可能被归入不同类别
  （专业 A 专必、专业 B 专选、某方案公选）—— 把 `course_type` 当课程全局属性，
  在本项目处理的**转专业场景**中会**直接产生错误结论**。
  另有表达限制：`recommended_semester` 只能存**单个整数**，
  装不下"跨若干学期"的语义（§3.1 记为 C）。

影响模块：
  Curriculum（主要生产方）、Planner（消费推荐学期 / 先修）、Course Data
  （`courseCategoryName` 的归属对齐）、Agent / Integration、Frontend（培养方案结构展示）；
  ⚠️ 若涉及 `Course` 字段的语义变化，还会波及 `mock_data/`（4 个文件）、
  `backend/app/models/contracts.py`（启动自检按 JSON Schema 校验，不通过则进程启动失败）
  与前端类型 / 展示。

是否为破坏性修改：
  **取决于裁决**：
    仅新增对象、保留 `Course` 现有字段 → **非破坏性**（兼容性新增）；
    改变 `Course.course_type` / `recommended_semester` 的含义或移除字段 → **是**，
      且必须同步 `mock_data/`、后端契约层、前端类型与展示，并更新回归测试。
  ⚠️ **兼容 / 迁移策略必须由负责人决定；本轮不实施任何变更。**

是否存在不修改接口的替代方案：
  **有，且相当有力**：
    ① 培养方案解析结果**全部留在 Curriculum 模块内部**（模块内部输入），不进公共契约。
       `/AGENTS.md` 明确允许这种处置，且 **Curriculum → Planner 只需交付 `MakeupTask[]`**，
       而 `MakeupTask` 中**已有** `recommended_semester` / `deadline_semester` /
       `prerequisites[]` —— 从 Planner 的 MVP 需求看，**可能确实不需要** `CurriculumCourse`
       进入公共契约。
  代价：
    - `Course.course_type` / `recommended_semester` 的**位置不当问题无法解决**，
      跨专业场景下仍有被误当作"课程全局属性"的风险；
    - Course Data 侧的 `courseCategoryName` **无法与 Curriculum 侧对齐**（同一语义两处各自解释）；
    - 前端**无法展示培养方案结构**（总学分、课程分组、方案级口径）。
  → 结论：存在不改接口的方案，但它把"方案上下文归属"这一问题留在了系统里；
     是否正式化，取决于负责人对 MVP 范围与语义正确性的权衡。
```

#### 裁决（Architecture Lead，2026-09-30）：**DG-04 = DEFER PUBLIC CONTRACT**

- ✅ **概念边界成立**：`CurriculumVersion`（某专业 / 年级 / 版本的一份方案）与
  `CurriculumCourse`（某门课在该方案中的**要求**）的划分被确认；
- ⛔ **MVP 不新增这两个公共 Schema**，**暂作为 Curriculum 内部模型**；
- ✅ **同时明确记录**：`Course.course_type` 与 `Course.recommended_semester` 是
  **现有兼容字段**，**不能被解释为课程全局固有属性**；
- ✅ **跨学期区间**（如 `2025-1~2025-2`）**仍不能由现有 `recommended_semester` 无损表示**，
  应由 **Curriculum 内部结构**保留；
- 🔁 若将来需要跨模块消费培养方案结构，再重新走接口变更。

### DG-05 Curriculum → Planner 的 priority / dependency

```text
【接口变更请求】
当前设计：
  `/AGENTS.md` 第 5 节要求 "Planner 应消费 Curriculum 模块提供的补修任务、
  **课程依赖结果**和**已确认优先级**"。
  但：
    ① 依赖方面 —— `MakeupTask.prerequisites[]`（课程号字符串数组）**已存在**，
       可表达直接先修关系；
    ② 优先级方面 —— `makeup_task.schema.json` **没有 priority 字段**，
       `/schemas/` 下**也没有**优先级对象；
    ③ **依赖图**方面 —— 没有 `DependencyGraph` 类公共对象；
    ④ `docs/interfaces/planner.md` 反而把"课程依赖图 / 补修优先级与风险"写成
       **Planner 自己的职责**，与 `/AGENTS.md` 第 5 节冲突（另见 DG-06）。

建议修改：
  ① **依赖：优先不新增 `DependencyGraph` 公共 Schema。**
     MVP 由 `MakeupTask[]` + 现有 `prerequisites[]` 承载依赖边；
     依赖图的构建（闭包 / 拓扑序）属**确定性算法**，留在 Planner 内部实现。
  ② **优先级：提出 `priority` 一类方向**（因为 `/AGENTS.md` 第 5 节明确要求该信息跨模块传递）。
     ⚠️ **字段名、类型（整数 / 序数 / 枚举）、取值范围、枚举取值、是否必填、
       放在 `MakeupTask` 上还是独立对象上 —— 一律不得由 Agent 决定，全部待裁决。**
  ⚠️ 本文档**不修改任何 Schema**，仅提出方向。

原因：
  依赖：Planner 的跨学期路径排序需要"先修 B 才能修 A"的先后关系；
        `prerequisites[]` **已存在且形状可承载**，新增 `DependencyGraph` 会**超出 MVP 需要**
        （`/AGENTS.md` 第 9 节：MVP 阶段避免过度设计）。
  优先级：`/AGENTS.md` 第 5 节要求 Planner 消费"已确认优先级"，但当前**无任何承载位置**；
        且 `status`（认定状态枚举）与 `recommended_semester` / `deadline_semester`（时间）
        **都不能表达学业优先级**。

影响模块：
  Curriculum（生产方）、Planner（消费）、Agent / Integration（解释与展示）、Frontend。

是否为破坏性修改：
  新增**可选**字段 → **否**；
  若定义为**必填**或改变 `MakeupTask` 现有字段语义 → **是**。
  ⚠️ 由负责人裁决；本轮不实施。

是否存在不修改接口的替代方案：
  **有，且部分方案相当可行**：
    ① **优先级留在 Curriculum 内部，Planner 不做排序** —— 完全不改接口；
       前提是负责人确认 Planner MVP **不需要**跨模块优先级
       （例如 Planner 只按 Curriculum 给定的任务集合求解冲突）。**这是最保守的方案。**
    ② 用 `MakeupTask[]` 的**数组顺序**承载优先级 —— 不改 Schema，但
       **Schema 从未定义数组顺序语义**，属**隐式约定**；`/AGENTS.md` 第 5 节禁止
       "只有两边懂的私有格式"，且下游可能重排数组 → **不可靠，不推荐**。
    ③ 用 `recommended_semester` + `deadline_semester` 表达时间紧迫性 —— 不改 Schema，
       但**不等于学业优先级**（两门课可同学期、同 deadline 而优先级不同）。
    ④ 用 `reason` 自由文本承载 —— **不可用于确定性求解**，违反 `/AGENTS.md`
       第 1、5、7 节（不得用 LLM / 自由文本替代确定性判断）→ **不可接受**。
    ⑤ 依赖：直接使用现有 `prerequisites[]`（本身就是"不改接口"方案，故 ① 项建议即此方案）。
  ⚠️ **另有一条重要限制必须同时裁决**：真实培养方案样本中**未发现明确的先修字段**
     （`REAL_TO_SCHEMA_GAP_REPORT.md` §3.1），因此 `prerequisites[]` 的
     **"可被真实数据填充"目前尚无证据**（这不构成"学校无先修制度"的结论）。
     若最终依赖信息无处可得，Planner 的依赖排序将只能基于**人工确认**的输入。
```

#### 裁决（Architecture Lead，2026-09-30）：**DG-05 = NO NEW PUBLIC CONTRACT FOR MVP**

- ⛔ **不新增** `DependencyGraph` Schema；
- ⛔ **不新增** `priority` 字段；
- ⛔ **不新增** `PriorityResult`（或同类对象）；
- ✅ 权威边界（**必须按此表述**）：

  ```text
  Curriculum：
    负责认定 / 产出 authoritative dependency edges（先修关系）

  Planner：
    可以把已经收到的 prerequisites[]
    转换成本地 adjacency / topological representation
    供确定性求解使用

  Planner：
    不得新增、猜测、重写任何 prerequisite edge
  ```

- ✅ 若真实来源**无法提供** prerequisite → 标记 **未知 / 待人工确认**，**不得自动补齐**；
- ⛔ **目前没有正式 priority 数据时，Planner 不得自行生成 priority**；
- 🔁 **后续 Curriculum 真正实现明确的优先级规则时，再走接口变更。**
- ⚠️ §7.3.1 给出同一权威边界的完整表格版本。

### DG-06 `docs/interfaces/planner.md` 与 `/AGENTS.md` 职责冲突修正

```text
【接口变更请求】
当前设计：
  `docs/interfaces/planner.md`：
    - "本模块负责"（第 7–13 行）列出：**课程依赖图**；**补修优先级与风险**；
      时间 / 周次冲突；教学班替换；Path Repair；跨学期补修路径的 MVP 规划；
    - "建议接口"列出：`build_dependency_graph(courses)`、
      `calculate_priority(makeup_tasks, context)` 等；
    - "对外输入"只列：`MakeupTask[]`（来自 Curriculum）、`CourseOffering[]`（来自 Course Data）、
      当前课表、`Preference`（来自用户）。

建议修改：
  按 `/AGENTS.md` 第 5 节修正 `docs/interfaces/planner.md`：
    ① "本模块负责"改为：时间 / 节次 / 周次**冲突检测**、当前课表冲突分析、
       **替代教学班搜索**、硬 / 软约束建模、确定性约束求解、**Path Repair**、
       无解 / 部分可行处理、`PlanResult` 生成；
    ② **课程依赖图、补修风险与优先级**改列为**来自 Curriculum 的输入**（消费方，不是生产方）；
    ③ 删除或改写 `build_dependency_graph(courses)` / `calculate_priority(...)` 这两个**越界**接口名
       （改为"消费 Curriculum 提供的依赖结果与已确认优先级"，具体函数名待裁决）；
    ④ 在"对外输入"中补明依赖与优先级**来自 Curriculum**，而**不是** Planner 自行推导。
  ⚠️ 具体措辞与是否同时补充 `docs/interfaces/curriculum.md` 的"给 Planner 的交付"一节，
     **待负责人裁决**。⚠️ **本轮不修改该文件**（`/docs/interfaces/` 属公共契约，`/AGENTS.md` 第 4 节）。

原因：
  `/AGENTS.md` 第 5 节明确：课程依赖图与补修风险 / 优先级属 **Curriculum** 职责，
  Planner 只是**消费方**，且"不得为求解方便自行重写课程认定或学业优先级规则"。
  `planner.md` 现行描述与之**直接冲突**。
  `/AGENTS.md` 第 17 节规定：两者冲突时**先遵守 `AGENTS.md`**，并停止冲突部分、向负责人说明。
  若不修正，Planner 成员可能照文档**自建依赖图与优先级**，绕过 Curriculum 的业务规则 ——
  这正是本项目最需要避免的"下游复制 / 猜测 / 重写上游逻辑"（第 19 节）。

影响模块：
  Planner、Curriculum、Agent / Integration，以及**所有阅读该接口文档的成员**（含 QA）。

是否为破坏性修改：
  **否**（**文档修正，不涉及任何字段 / API 路径变更**）；
  但会**改变成员对模块职责的理解**，因此必须由负责人确认后才能执行。

是否存在不修改接口的替代方案：
  有：**在 `planner.md` 中仅加一条注记** —— "本文件与 `/AGENTS.md` 第 5 节冲突处，
  以 `/AGENTS.md` 为准"。代价：**双份职责描述继续并存**，仍会误导新成员；
  且 `AGENTS.md` 第 17 节要求的是"停止冲突部分并说明"，仅加注记**未真正消除冲突**。
  → 建议按上述 ①–④ 修正，但**由负责人裁决**。
```

#### 裁决（Architecture Lead，2026-09-30）：**DG-06 = APPROVED**

- ✅ **下一阶段允许修正** `docs/interfaces/planner.md`；
- ✅ 并根据需要**同步** `docs/interfaces/curriculum.md`，使其与 `/AGENTS.md` 第 5 节一致；
- ⚠️ **本轮仍然不要改 `docs/interfaces/`** —— 本轮只**落档裁决**；
- ✅ 执行窗口：**Data Gate-2**（与 DG-01 的 Schema 变更一并处理）。

---

## 14. 本文件不做什么

> ⚠️ 本节描述的是 **Data Gate-1 整理阶段**的自我约束（历史记录）。
> 契约实施已在 **Data Gate-2** 按裁决完成，实施清单见 **§16**。

- 整理阶段**不修改** `/schemas/`、`/docs/interfaces/`、`/AGENTS.md`；
- 整理阶段**不修改** `backend/`、`frontend/`、`mock_data/`；
- **不写** parser、crawler、Adapter、Normalizer、`CourseDataProvider`、Integration；
- **不建**数据库、**不写** ORM / migration、**不设计** PostgreSQL 表；
- **不调用** SYSU 接口（Data Gate-1 与 Data Gate-2 均为**零请求**）；
- **不自行增删字段、不改变字段含义**（字段级细节以裁决给出的**目标结构**为准）；
- **不提前实施**已裁决的变更。

> **持续适用的约束**见 §12.1。

---

## 15. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-30 | **建立本文件（Data Gate-1）** | 依据 D1–D5 真实证据与 `REAL_TO_SCHEMA_GAP_REPORT.md`（G1–G10）：① 整理 7 个核心实体边界（`Course` / `CurriculumVersion` / `CurriculumCourse` / `CompletedCourse` / `CurrentEnrollment` / `CourseOffering` / `ScheduleSegment`）；② 给出实体所有者、Shared / Private / Derived 分类与 Course Data 获取边界；③ 对 **G9 多 segment** 给出概念关系、6 项 segment 量、`teacher` 层级结论与 4 个候选方案（含明确禁止的 2 个方案）；④ 分析 `Curriculum → Planner` 契约（`prerequisites[]` 是否足够、"已确认优先级"是否进契约）并登记 `docs/interfaces/planner.md` 的**接口文档债务**；⑤ 提交 **DG-01 – DG-06** 六项 `【接口变更请求】` **草案**与 **11 条 Data Gate 通过条件（C1–C11）**。**未修改 Schema / Interface / 代码，未调用 SYSU 接口；当时尚未裁决任何一项。** |
| 2026-09-30 | **架构裁决落档（Architecture Lead）** | ① 新增**架构裁决总表**：**DG-01 APPROVED WITH MODIFICATION**（采用 `CourseOffering` 1 — N `Meeting`，Data Gate-2 改契约；方案 B/C/D 转为"已评估但驳回"）、**DG-02 DEFER PUBLIC CONTRACT**（Curriculum 内部规范化对象，D4 经非公开位置交接）、**DG-03 APPROVE CONCEPT, REUSE EXISTING CONTRACT**（`current_schedule` 复用 `CourseOffering[]`）、**DG-04 DEFER PUBLIC CONTRACT**（Curriculum 内部模型；`Course.course_type` / `recommended_semester` 不得解释为全局固有属性）、**DG-05 NO NEW PUBLIC CONTRACT FOR MVP**（不新增 `DependencyGraph` / `priority` / `PriorityResult`）、**DG-06 APPROVED**（Data Gate-2 修正 `planner.md`，必要时同步 `curriculum.md`）；② **进入 Data Gate-2 实施的契约变更只有 DG-01 与 DG-06 两项**（§9 重写）；③ **修正教师证据**：删除"没有证据表明教师存在 meeting-level 语义"的说法，改为"**meeting-level teacher association = 已知真实语义**，但 Planner MVP 不依赖它"，并登记为 **known deferred representation gap**（§6.4）；④ **§6.8 锁定目标结构**（`meetings[]`：`weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom`）；⑤ **修正 DG-05 权威边界表述**：Curriculum 认定 / 产出 edges，Planner 只做**本地** adjacency / topology 转换，**不得新增 / 猜测 / 重写 edge**（§7.3.1）；⑥ **修正通过条件计数**：由"12 条"更正为 **11 条（C1–C11）**；⑦ §12 增加逐条**当前状态**。**仍未修改 Schema / Interface / 代码，未调用 SYSU 接口（零请求），未进入 Data Gate-2。** |
| 2026-09-30 | **最终同步修复（Data Gate-1 收尾）** | ① **§5.1 隐私措辞收紧**：删除过强的"来源为学校侧，**不含个人身份信息**，原则上可跨成员共享"，改为 **School-shared = "可在同一学校用户场景中复用的学校侧数据"**，并明确**不代表天然不含人员信息、不代表可以公开发布**；补注 `CourseOffering` 等**可能包含教师等人员信息**、Real / Raw 仍须遵守**数据最小化 / 来源授权 / 非公开处理**，以及 **"是否 School-shared" 与 "是否可以公开" 是两个独立问题**；⚠️ **不得把教师信息归为 Student-private**。② **新增 §11.3 C9 裁决**：目标 **2026-1 semester offering snapshot**；7 条获取边界；Course Data / Integration / Planner 三方分工；**批量导入须先确认合理 `pageSize` / 请求规模**；**completeness 纪律** —— "目标是完整 Snapshot"**≠**"已取得完整数据"，**partial snapshot 必须显式记录完整性，不得宣称 complete**（§11.4 / §11.5 顺延）。③ **§12 同步**：**C2 / C3 / C9 / C10 / C11 全部标记为 ✅ 已确认**，进度更新为"**仅 C5 待 Data Gate-2 执行**"；C10 保留 **真实逐行数据交接次数 = 0**；C11 明确四项风险（`prerequisites[]` 暂无真实来源证据、`weekDay` 待确认、`openingSchoolName → campus` 待确认、meeting-level teacher 为 known deferred representation gap），并写明 **不允许实现层自行补齐**。**仍未修改 Schema / Interface / 代码，未调用 SYSU 接口（零请求），未进入 Data Gate-2。** |
| 2026-09-30 | **Data Gate-2 实施完成 → Data Gate PASSED / CLOSED** | ① **DG-01 已实施**：`schemas/course_offering.schema.json` 顶层删除 `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom`，新增 **`meetings[]`（`minItems: 1`）**；顶层 `required` = `course_id` / `course_name` / `class_id` / `semester` / `meetings`；每个 `Meeting` = `weekday` / `start_section` / `end_section` / `weeks[]` / `campus?` / `classroom?`（`additionalProperties: false`）；**未新增任何暂缓字段，未给 `Meeting` 加 `teacher`**。② **DG-06 已实施**：`docs/interfaces/planner.md` 与 `docs/interfaces/curriculum.md` 已按 `/AGENTS.md` 第 5 节修正（Planner 不再负责依赖认定 / 风险 / 优先级 / Curriculum Diff；删除 `build_dependency_graph` 与 `calculate_priority`；写明 `current_schedule: CourseOffering[]` 的语义与"学校全部供给 ≠ 学生已选子集"；写明优先级当前**无**公共契约）。③ **同步范围**：`mock_data/course_offerings.json` 全量迁移（**9 个教学班，其中 1 个含 2 段 meeting**）、`backend/app/models/contracts.py`（新增 `Meeting`）、后端测试、`frontend` 类型与展示（上课安排逐段展示）。④ **验证**：后端 `pytest` **133 passed / 2 skipped**；前端 `npm run build`（含 `vue-tsc --noEmit`）**成功**。⑤ **C5 完成，C1–C11 全部完成 → Data Gate PASSED / CLOSED**（§12.2、§16）。⑥ **G9 更新为「已通过 DG-01 / Data Gate-2 完成公共契约修复」**，原缺口描述在缺口报告中**原样保留**。⚠️ **全程零 SYSU 请求；未写 crawler / Adapter / Provider / Integration；未建数据库；未进入 Course Data MVP。** |
| 2026-10-01 | **Data Gate Reopen（仅 DG-07）+ DG-07 草案提交** | 因 **G11** 新真实证据（真实 2026-1「全校开设课程」第 1 页：**39 / 200 条 row 缺少 `teachingTimePlaceStr`**；C1C 相关性诊断显示结构差异集中在排课相关字段；**C1D** 人工 UI 核验 **n = 2** 两条典型候选均为普通教学班行、时间 / 周次 / 地点空白且无状态文字）：① **Data Gate 仅在 DG-07 范围内临时 Reopen**（**Reopened narrowly for DG-07 only**，§12.3），⛔ **DG-01 – DG-06 不重新打开**、其它已裁决问题不重新讨论；② **新增 §17**，按 `/AGENTS.md` 第 4 节格式提交 **DG-07 `CourseOffering` Empty Meetings / Unknown Schedule** 草案 —— 建议把 `meetings` 的 **`minItems: 1` 放宽为 `0`**，使 `"meetings": []` 合法，并锁定其**精确定义**（仅表示"当前来源快照没有可用排课信息"，⛔ 不表示无课 / 异步 / 时间自由 / **无冲突** / 学校确认未排课）；③ **比较 4 个替代方案**（A 过滤、**B `minItems = 0`（推荐）**、C 新增 `schedule_status`、D 独立 DTO），并说明**暂不新增业务状态枚举**的理由（无官方语义证据，易把"未知"伪装成"已知状态"）；④ **写入核心安全不变量 `meetings = []` ≠ conflict-free**，Planner 不得将其视为"已验证无冲突"的普通候选；保守 MVP 行为仅作 Proposal，`PlanResult.unresolved[].type` 的 `missing_schedule` 标为 **candidate convention only**，⛔ 不武断规定 `partially_feasible` / `infeasible`；⑤ **Breaking 分析分两层**：Schema validation 层面为**兼容性放宽**，消费者语义层面为**语义性 breaking change**（依赖 `meetings` 非空不变量的消费者需同步迁移）；⑥ 明确**术语纪律**（推荐中性术语 `schedule information unavailable in current source snapshot`；⛔ 不得使用"未排课课程 / 异步课程 / 时间待定"等学校未提供的标签），并声明**只有边际计数、无逐 row 交叉证据**、C1D **n = 2 不得外推**、39/200 **不得外推到 6892**。⑦ **DG-07 状态 = `PROPOSED / WAITING FOR ARCHITECTURE REVIEW`**（**未批准**）。⚠️ **本轮未修改** `schemas/` / `docs/interfaces/` / 任何代码 / 任何测试；**未实施** `minItems = 0`；**未认定 G11 resolved**；**Builder 实际 SYSU 请求数 = 0**。 |
| 2026-10-01 | **DG-07 Reviewer 架构修复（3 项，docs-only）** | ① **删除"真实可选教学班"的过度表述**：C1D 只证明**真实教学班 / 开课记录存在**，**不证明**对当前学生**可选**；`过滤可能丢失真实可选教学班` → **`过滤可能丢失真实教学班记录`**（§17.5 / §17.6 共 4 处）。**"是否属于有效可选教学班"与"是否应进入 Planner"继续保留为未确认项**。② **新增 §17.12.1「Course Data fail-closed 不变量」**：明确 **`meetings = []` 只能表示来源层没有提供可形成 `Meeting` 的排课信息，⛔ 不得作为 parser / importer / normalizer 解析失败的 fallback**；**初始实施边界按现有证据写死** —— ✅ **已确认可映射为 `[]` 的来源形态只有一种：`teachingTimePlaceStr` 属性不存在**；⛔ `null` / `empty_string` / `other_type` / 非空但格式无法解析 / malformed segment / parser / normalization 异常**一律继续 fail closed**，除非将来有**独立真实证据 + 架构裁决**。③ **Planner 安全规则显式覆盖 `current_schedule`**（§17.9）：因 `offerings` 与 `current_schedule` **同为公共类型 `CourseOffering[]`**，故**对两者中任何 `meetings = []` 的 `CourseOffering`，schedule 都视为 unknown**；**若 `current_schedule` 中存在 `meetings = []`，Planner 不得把其它候选声明为"已验证与当前课表无时间冲突"**（最多只能说"与**已知**时段不冲突"）。④ **§17.5 建议修改**同步声明：**本提案的批准必须与上述两条不变量同时成立**，否则等于放行静默降级。⑤ `PlanResult.status` / `unresolved` 命名**仍留待 Planner implementation review**，⛔ 本轮不决定；**DG-07 状态仍为 `PROPOSED / WAITING FOR ARCHITECTURE REVIEW`**（⛔ 未写 APPROVED）。⚠️ **仅修改现有 7 个 docs 文件**；**未修改** `schemas/` / `docs/interfaces/` / 代码 / 测试；**未实施** `minItems = 0`；**Builder 实际 SYSU 请求数 = 0**。 |
| 2026-10-01 | **DG-07 架构裁决落档（项目负责人）**：**APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING** | ① **DG-07 由 `PROPOSED / WAITING FOR ARCHITECTURE REVIEW` 更新为 `APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**（新增 §17.5.1 裁决块；§12.3 与文件头同步）。② **批准方向（仅记录，未实施）**：`CourseOffering.meetings` **`required` 保持不变**、`type: array`、**`minItems: 1 → 0`** → 未来允许 `"meetings": []`；⛔ **本轮未修改** `schemas/`。③ **"WITH MODIFICATION" 的准确含义**：**不是**只批准 `minItems: 1 → 0`，而是 **Schema 放宽** 与 **§17.12.1 Course Data fail-closed 不变量**、**§17.9 Planner 安全不变量（含 `current_schedule`）** **必须同时成立**。④ **批准的精确定义**：`meetings = []` **仅**表示"当前来源快照没有提供能够形成公共 `Meeting` 的可用排课信息"；⛔ 不表示无上课时间 / 异步课程 / 时间自由 / 无时间冲突 / 学校确认尚未排课 / 无效教学班 / 应过滤。⑤ **批准的 fail-closed 不变量**：初始阶段**唯一**可生成 `[]` 的来源形态 = **`teachingTimePlaceStr` 属性不存在**；`null` / `empty_string` / `other_type` / 非空但无法解析 / malformed segment / **parser / importer / normalization 异常**一律**继续 fail closed**；⛔ 禁止 `try: parse schedule … except: meetings = []`。⑥ **批准的 Planner 不变量**：**`meetings = []` ≠ conflict-free**；`offerings` 与 `current_schedule` **同一规则**（任意 `meetings = []` → schedule unknown）；`current_schedule` 含 `meetings = []` 时⛔ **不得**声明其它候选"已验证与当前课表无时间冲突"，最多只能判断"**与已知时间段未发现冲突**"，**整体时间冲突状态仍含未知部分**。⑦ **本轮未批准**：不新增 `schedule_status` / `schedule_known` / `schedule_state`。⑧ **仍 deferred 到 Planner Implementation Review**：`PlanResult.status` 取值、`unresolved[].type` 最终命名、`missing_schedule` 是否正式采用 → 当前 **`missing_schedule` = candidate convention only**。⑨ **Data Gate 仍保持 Reopened**（**未 CLOSED**）：新增 §17.15 关闭前置条件（Contract Migration + Course Data + Planner safety + Frontend/Mock + tests，且须经 Reviewer 验收）；⛔ 本轮**未开始任何实施阶段**，也**未自行命名**实施阶段。⑩ **G11 状态更新为 `contract decision approved; implementation pending; school-side business cause still unknown`**（⛔ **不写 resolved**；"契约方向已裁决" ≠ "学校业务原因已查明"）。⚠️ **仅修改现有 7 个 docs 文件**（本轮实际改动其中 5 个，另 2 个无需变化）；**未修改** `schemas/` / `docs/interfaces/` / 代码 / 测试；**Builder 实际 SYSU 请求数 = 0**。 |

---

## 16. Data Gate 关闭记录（Data Gate-2 实施）

**结论：Data Gate-1 架构裁决 + Data Gate-2 实施全部完成 → Data Gate PASSED / CLOSED。**

### 16.1 DG-01 实施内容（`CourseOffering` 1 — N `Meeting`）

| 项 | 实施结果 |
|---|---|
| **契约真源** | `schemas/course_offering.schema.json` 已改写 |
| **顶层删除** | `weekday`、`start_section`、`end_section`、`weeks`、`campus`、`classroom`（**彻底移除，不保留兼容字段**） |
| **顶层 `required`** | `course_id`、`course_name`、`class_id`、`semester`、`meetings` |
| **新增 `meetings`** | `type: array`，`minItems: 1`；`items` 为对象（`additionalProperties: false`） |
| **`Meeting` 必填** | `weekday`（1–7）、`start_section`（≥1）、`end_section`（≥1）、`weeks`（整数数组，`minItems: 1`，`uniqueItems: true`） |
| **`Meeting` 可选** | `campus`（string\|null）、`classroom`（string\|null） |
| **未新增** | `selectedNumber` / `openingUnitName` / `courseCategoryName` / `examMode` / `readObj` / `teachProgressSubmitState` / `openClass` / **`meeting.teacher`** 一律**未加入** |
| **性质** | **有意的 breaking migration**：旧结构被 JSON Schema 与 Pydantic **双重拒绝** |

**同步实施范围**：

- `backend/app/models/contracts.py`：新增 `Meeting` 模型，`CourseOffering.meetings: list[Meeting]`（至少 1 项），
  删除顶层六个排课字段，`__all__` 加入 `Meeting`；`weeks` 的 `uniqueItems` 仍在运行时真实拒绝重复项；
- `mock_data/course_offerings.json`：**9 个教学班**全部迁移，其中 **1 个教学班含 2 段 meeting**
  （第二段为**人工构造的 Mock**，未复制任何真实 SYSU 响应或真实教师信息）；
- `backend/tests/`：`test_contracts.py`、`test_mock_data_schema.py` 已迁移并在新位置加严
  （所有时间 / 地点检查改为**逐 meeting** 遍历，不再只看第一段）；
- `frontend/src/`：`types/contracts.ts`（新增 `Meeting`）、`CourseOfferingList.vue`
  （"上课安排"列**逐段**展示）、`utils/labels.ts`（新增纯展示函数 `formatMeetingLine`）、`styles/base.css`。

**明确保留的表达损失**：**meeting 级教师关联**仍是
**known deferred representation gap** —— `teacher` 保持在教学班顶层作汇总 / 展示。

### 16.2 DG-06 实施内容

| 文件 | 实施结果 |
|---|---|
| `docs/interfaces/planner.md` | 职责改为冲突检测 / 当前课表冲突分析 / 替代教学班搜索 / 硬软约束建模 / 确定性求解 / Path Repair / 无解处理 / `PlanResult`；**删除** `build_dependency_graph` 与 `calculate_priority`；写明依赖与优先级的权威边界、`current_schedule: CourseOffering[]` 的语义、冲突检测必须遍历全部 `meetings` |
| `docs/interfaces/curriculum.md` | 补上**课程依赖认定**、**补修风险 / 学业优先级的所有权**、**跨学期补修路径建议**；明确**优先级当前没有公共契约**，**不得假装可以跨模块传 priority** |

### 16.3 验证结果

```text
cd backend  && python -m pytest      →  133 passed / 2 skipped（全部通过）
cd frontend && npm run build         →  成功（含 vue-tsc --noEmit 类型检查）
```

启动自检（"先按公共 JSON Schema 校验原始 JSON，再用 Pydantic 解析"）**未被破坏**，
并有回归测试锁定：旧格式教学班、`meetings: []`、`meeting.weekday=8`、
`meeting.weeks=[1,1]`、`Meeting` 额外字段均被拒绝。

### 16.4 本轮未做（等待新一轮任务书）

- ❌ SYSU API 请求（本轮**零请求**）
- ❌ 抓取 6892 条课程数据 / crawler
- ❌ Course Data Adapter / Normalizer / `CourseDataProvider`
- ❌ Integration / Orchestrator
- ❌ 数据库 / ORM / migration
- ❌ Curriculum 实际算法 / Planner 实际求解器
- ❌ 任何新增 Schema（`CompletedCourse` / `CurrentEnrollment` / `CurriculumVersion` /
  `CurriculumCourse` / `DependencyGraph` / `priority`）

**真实 2026-1 semester offering snapshot 属于 Data Gate 关闭后的 Course Data MVP，本轮不做。**

---

## 17. DG-07 `CourseOffering` Empty Meetings / Unknown Schedule（G11）

> **状态：`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**
> （**2026-10-01 由项目负责人批准**；裁决见 **§17.5.1**）
> ✅ **已批准的是"方向 + 两条不变量必须同时成立"**，⛔ **不是**已实施：
> 本轮**未修改** `schemas/`、`docs/interfaces/`、任何代码、任何测试。
> ⛔ **IMPLEMENTATION PENDING**：实施须等**单独的 Implementation 任务书**，
> 且完成回归与 Reviewer 验收后才允许登记 `DG-07 IMPLEMENTED` / 关闭 Data Gate（§12.3）。

### 17.1 为什么 Data Gate 需要为这一项 Reopen

- Data Gate 此前 **PASSED / CLOSED**（C1–C11 全部完成，见 §12.2 / §16）；
- 此后产生了**新的真实证据**：真实 2026-1「全校开设课程」第 1 页中，
  **39 / 200 条 row 完全没有 `teachingTimePlaceStr`**（C1B），
  C1C 相关性诊断显示**结构差异集中在排课相关字段**（C1C），
  并由 Architecture Lead 指导负责人完成 **2 条典型候选的人工 UI 核验**（C1D）；
- 现有契约要求 **`CourseOffering.meetings` `minItems: 1`**，
  **无法表示**"官方教学班记录存在，但**当前来源快照没有可用排课信息**"这一**已观察状态**；
- 因此以 **DG-07** 的形式提出契约表达问题，**Reopened narrowly for DG-07 only**（见 §12.3）。

### 17.2 术语与引用约定（**本文档的用词纪律**）

- ✅ **推荐中性术语**：
  **`schedule information unavailable in current source snapshot`**（英文）/
  **「当前来源快照中没有可用排课信息」**（中文）。
  这是**本系统的数据状态描述**，**不是学校官方业务状态**；
- ⛔ **不得**把这些记录称为：**未排课课程 / 未排课教学班 / 时间待定课程 / 异步课程 /
  无需排课课程 / 停开课程 / 无效教学班 / 自由时间教学班** ——
  学校 UI **没有提供**这些标签，我们也**没有**官方证据；
- ⚠️ **只能按"边际计数"引用 C1B / C1C**：`timePlaceId` 38/39 缺失与 `weekDay` 38/39 缺失
  是**两个独立边际计数**；⛔ **不得**写成"同样的 38 条**同时**缺两个字段"
  （**没有逐 row 交叉证据**）；
- ⚠️ **C1D 的样本量是 n = 2**，⛔ **不得**写成"39 条全部如此"；
- ⚠️ **39 / 200 = 19.5% 只描述第 1 页样本**，⛔ **不得外推**到 6892 条整体。

### 17.3 真实证据基础（截至本轮）

**来源**：`OFFERING-002`（`DATA_SOURCE_REGISTRY.md`，**未创建新 `source_id`**）——
学期 **2026-1**、模块「**全校开设课程**」、**第 1 页**、`pageSize = 200`、
`reported_total = 6892`、`Authenticated Official`、证据等级 `Confirmed`。

**C1B（第 1 页结构诊断，负责人手动执行）**

```text
total_rows = 200
teachingTimePlaceStr:  missing 39 | null 0 | empty_string 0 | non_empty_string 161 | other_type 0
```

**C1C（第 1 页相关性诊断，负责人手动执行）**

| 字段 | `missing` 组（39 条） | `non_empty_string` 组（161 条） |
|---|---|---|
| `timePlaceId` | `missing 38` / `non_empty_string 1` | `non_empty_string 161` |
| `weekDay` | `missing 38` / `scalar_count 1` | `missing 12` / `scalar_count 149` |
| `limitNumber` | `number 39` | `number 161` |
| `selectedNumber` | `number 39` | `number 161` |

其它 C1C 观察（⛔ 不登记任何真实 categorical 取值）：

- `openClass`：两组**实际取值完全一致** → **无法区分** missing / present；
- `teachProgressSubmitState`：两组**共享相同的 2 个分类值**，分布不同，
  **没有 missing 组独占值**；
- `examMode`：两组**共享相同的 2 个分类值**，分布不同，**没有 missing 组独占值**；
- `courseCategoryName`：`missing` 组的 **3 个分类全部也存在于 present 组**；
- `openingUnitName`：`missing` distinct = **11**，present distinct = **27**。

**C1D（人工业务界面核验，负责人本人完成；Architecture Lead 指导定位候选）**

- 候选条件：**`teachingTimePlaceStr` 不存在 + `weekDay` 不存在 + `timePlaceId` 不存在**；
- 从第 1 页本地定位 **2 条**典型候选（**candidate A / candidate B**，`n = 2`）；
- 两条候选**均由负责人在「全校开设课程」UI 中人工检查**，结果一致：

| 人工检查项 | candidate A | candidate B |
|---|---|---|
| UI 中能够正常找到 | 是 | 是 |
| 上课时间 / 周次 / 地点 | **完全空白** | **完全空白** |
| 明确状态文字 | **无** | **无** |
| 容量 / 已选人数等普通教学班信息 | 正常显示 | 正常显示 |
| 与普通教学班为同一种表格行 | 是 | 是 |
| 详情 / tooltip 解释空白原因 | **无** | **无** |

- ⚠️ **范围限制**：**只人工检查了 2 条候选** → 只能说
  「**已人工核验的 2 条典型候选，在学校 UI 中均作为普通教学班记录展示，
  但时间 / 周次 / 地点位置为空**」；
  ⛔ **不得**说"39 条全部如此"；
- ⛔ **不登记**候选的课程名 / 课程号 / 教学班号，也不登记截图中的任何具体课程身份。

### 17.4 由证据支持的事实判断（**只写事实**）

- 当前真实证据**已经不足以支持**"缺 schedule 字段的记录都是**无效记录**，
  应**直接过滤**"的简单处理。理由是事实层面的：
  1. **39 条记录仍具有完整的容量 / 已选人数等教学班信息**（`limitNumber` / `selectedNumber`
     在 39 条中均为数值型且完整存在）；
  2. **`openClass` 无法区分两组**（实际取值完全一致）；
  3. 其它观察到的 categorical 字段（`teachProgressSubmitState` / `examMode` /
     `courseCategoryName`）**也没有发现 `missing` 组独占分类**；
  4. **已人工核验的 2 条典型候选均在官方 UI 中作为普通教学班行正常存在**
     （时间 / 周次 / 地点区域空白，且无任何状态文字解释）。
- 现有 `CourseOffering` **强制至少一个 `Meeting`** 的契约，
  **无法表示**"**官方教学班记录存在，但当前来源快照没有可用排课信息**"这一**已观察状态**。

> ⚠️ **必须同时注明**：以上是**基于当前已观察真实样本**提出的**契约表达问题**，
> **不是对学校业务状态的命名**。学校侧"为什么为空"**仍然未知**。

### 17.5 `【接口变更请求】` 草案（DG-07，按 `/AGENTS.md` 第 4 节格式）

```text
【接口变更请求】
当前设计：
  `schemas/course_offering.schema.json` 中：
    "meetings": { "type": "array", "minItems": 1, "items": { ...Meeting... } }
  且顶层 `required` 包含 `meetings`。
  即：**一个 `CourseOffering` 必须至少包含 1 个 `Meeting`**；
  `"meetings": []` 目前**不是合法表示**（会被 JSON Schema 与
  `backend/app/models/contracts.py` 的 `min_length=1` 拒绝，
  并有回归测试锁定这一行为）。

建议修改：
  ⭐ **推荐方案（本轮草案）**：把 `minItems` 由 **1 放宽为 0**
      "meetings": { "type": "array", "minItems": 0, "items": { ...Meeting... } }
  即允许 `"meetings": []` 成为**合法**表示。
  ⛔ 不新增字段、不改 `Meeting` 结构、不改 `required` 列表
     （`meetings` 仍为必填，只是**允许为空数组**）。
  ⛔ 不新增 `schedule_status` / `schedule_known` / `schedule_state`（理由见 §17.7）。
  ⛔ 字段名、最终语义措辞、是否同时调整文档与测试，**均待 Architecture Lead 裁决**。
  ⚠️ **本提案的批准必须与下面两条不变量同时成立**（否则等于放行静默降级）：
     · **§17.12.1 fail-closed 不变量**：`meetings = []` **只能**表示来源层确实没有提供
       可形成 `Meeting` 的排课信息（**初始证据边界**＝**仅 `teachingTimePlaceStr` 属性不存在**），
       ⛔ **不得**作为 parser / importer / normalizer **解析失败的 fallback**；
     · **§17.9 Planner 安全规则**：`meetings = []` **≠ conflict-free**，
       且该规则**同时适用于 `offerings` 与 `current_schedule`**（两者同为 `CourseOffering[]`）。

原因：
  真实证据（§17.3）显示：真实来源中存在**官方教学班记录存在、
  但当前来源快照没有可用排课信息**的已观察状态（第 1 页 39/200；其中 2 条已人工核验）。
  现有契约**强制至少一个 Meeting**，导致 Course Data 只有两种坏选择：
    ① 为这样的教学班**伪造** `Meeting`（凭空造排课信息 → 冲突检测假阴性）；
    ② **静默过滤**掉这些真实教学班（可能丢失真实教学班记录）。
  两者都与"不得猜测 / 不得伪造 / 不得静默丢数据"的项目纪律冲突（`/AGENTS.md` 第 8、18 节）。
  因此需要一种**不伪造、不丢弃**的合法表示。

影响模块：
  Course Data（生产方：可规范化为 `meetings = []`，**不得**过滤或伪造）；
  Planner（**核心安全影响**：`meetings = []` 表示 schedule unknown / unavailable，
            ⛔ **绝不能**被当作"已验证无冲突"，见 §17.9）；
  Integration（透明传递，**不解释、不补 Meeting、不过滤**，见 §17.10）；
  Frontend（需要能显示"排课信息暂缺"，见 §17.11）；
  连带影响：`mock_data/`、`backend/app/models/contracts.py`（启动自检按 JSON Schema 校验）、
            `backend/tests/`（**已存在锁定 `meetings: []` 必须失败的回归测试**）、
            `frontend` 类型与展示、`docs/interfaces/course_data.md` 的
            "`meetings` 必须至少包含 1 个 `Meeting`"表述。
  ⚠️ 以上均为**影响范围说明**，**本轮不实施**。

是否为破坏性修改：
  **分两层看，不能简单写"non-breaking"**：
    · **Schema validation 层面**：是**兼容性放宽**（放宽输入约束，
      原本非法的 `meetings: []` 变为合法；原本合法的数据仍然合法）；
    · **消费者语义层面**：对**依赖"`meetings` 非空不变量"的消费者**而言，
      属于**语义性 breaking change** —— 过去所有消费者可以假设
      `offering.meetings[0]` 一定存在，未来**不能**。
      需要 Planner / Frontend / tests / mock_data 等**同步迁移**，
      并且必须先确立 §17.9 的安全规则，否则会产生**严重错误**
      （把"排课信息未知"当成"无时间冲突"）。
  ⚠️ 最终定性由 Architecture Lead 裁决；**本轮不实施任何变更**。

是否存在不修改接口的替代方案：
  有，但都有实质代价（详见 §17.6）：
    Alternative A（保持 `minItems = 1`，由 Course Data 过滤缺 schedule 的 row）：
      ⛔ 当前证据**不足以**证明这些 row 无效；已人工核验的 2 条候选在官方 UI 中
         仍是**普通教学班记录**；过滤可能**丢失真实教学班记录**。
    Alternative C（新增显式 `schedule_status` 枚举）：
      ⛔ 当前**没有官方业务语义证据**支撑枚举设计（pending / asynchronous /
         cancelled / unscheduled / not_required 均无证据），
         容易把"未知"**误建模成已知状态**；修改范围更大。
    Alternative D（新建未知排课专用 DTO）：
      ⛔ MVP **过重**，会扩大跨模块契约，当前证据不足以支持拆分实体。
  → 结论：**存在不改接口的方案，但都需要付出"伪造 / 丢数据 / 猜语义"的代价**，
    因此建议由 Architecture Lead 在 A / B / C / D 之间裁决。
```

#### 17.5.1 裁决（项目负责人，2026-10-01）：**DG-07 = APPROVED WITH MODIFICATION**

**状态：`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**

- ✅ **批准的公共契约方向**（**本轮只记录，不实施**）：

  ```text
  CourseOffering.meetings:
    required: 保持不变（meetings 仍为必填）
    type: array
    minItems: 1 → 0
  ```

  即**未来允许** `"meetings": []`；⛔ **本轮不得**修改 `schemas/`。
- ⚠️ **"WITH MODIFICATION" 的准确含义**：**不是**只批准 `meetings` 的
  `minItems: 1 → 0`，而是 **Schema 放宽** 与
  **§17.12.1 Course Data fail-closed 不变量**、
  **§17.9 Planner 安全不变量（含 `current_schedule`）** **必须同时成立**。
- ✅ **批准的精确定义**：`meetings = []` **仅**表示
  "**当前来源快照没有提供能够形成公共 `Meeting` 的可用排课信息**"；
  ⛔ 它**不表示**：无上课时间 / 异步课程 / 时间自由 / 无时间冲突 /
  学校确认尚未排课 / 无效教学班 / 应过滤（见 §17.8）。
- ✅ **批准的 Course Data fail-closed 不变量**（§17.12.1）：初始实施阶段**唯一**已批准
  可生成 `meetings = []` 的来源形态 = **`teachingTimePlaceStr` 属性不存在**；
  `null` / `empty_string` / `other_type` / 非空但格式无法解析 / malformed segment /
  **parser / importer / normalization 异常**一律**继续 fail closed**；
  ⛔ **明确禁止** `try: parse schedule` … `except: meetings = []` 这类"解析失败 → 空数组"的写法 ——
  **`meetings = []` 绝不能成为解析错误的 fallback**。
- ✅ **批准的 Planner 核心不变量**：**`meetings = []` ≠ conflict-free**；
  对 `offerings` 与 `current_schedule` **使用同一规则**
  （任意 `CourseOffering.meetings = []` → **schedule unknown**）；
  若 `current_schedule` 中存在 `meetings = []`，⛔ **不得**声明其它候选
  "**已验证与当前课表无时间冲突**"，最多只能判断
  "**与已知时间段未发现冲突**"，且**整体时间冲突状态仍含未知部分**。
- ⛔ **本轮未批准的内容**：**不新增** `schedule_status` / `schedule_known` /
  `schedule_state` —— 当前**不需要**额外公共状态字段。
- ⏳ **仍留到 Planner Implementation Review**：`PlanResult.status` 如何取值、
  `unresolved[].type` 的**最终命名**、`missing_schedule` 是否正式采用；
  因此当前 **`missing_schedule` = `candidate convention only`**。
- ⚠️ **裁决 ≠ 实施**：`schemas/` / `docs/interfaces/` **仍未被修改**；
  实施须走**单独的 Implementation 任务书**，完成回归与 Reviewer 验收后
  才允许登记 `DG-07 IMPLEMENTED` 并关闭 Data Gate（§12.3）。

### 17.6 替代方案比较（**至少三项，含推荐项**）

**Alternative A — 保持 `minItems = 1`，由 Course Data 过滤缺 schedule 的 row**

- 优点：不改公共 Schema；Planner **无需**处理 schedule unknown；
- 风险：**当前证据不足以证明这些 row 无效**；已人工核验的 2 条候选在官方 UI 中
  仍是普通教学班记录；**过滤可能丢失真实教学班记录**（与项目"不得静默丢数据"纪律冲突）；
- 评估：**本轮不推荐**（但作为**保留方案**记录，最终由 Architecture Lead 权衡）。

**Alternative B — `meetings` `minItems = 0`（⭐ DG-07 推荐方案）**

- 优点：**最小 Schema 改动**；**保留真实教学班**；**不伪造 Meeting**；
  **不需要猜学校业务状态**（只表达"当前快照没有可用排课信息"）；
- 风险：Planner / Frontend / tests / mock_data / parser / importer **均需同步**；
  ⚠️ **若 Planner 错把 `[]` 当"无冲突"，会产生严重错误** ——
  这是本方案**必须配套的安全规则**（§17.9）。

**Alternative C — 新增显式 `schedule_status`（概念上 `schedule_status` + `meetings[]`）**

- 优点：状态表达**显式**（读起来比空数组更清楚）；
- 风险：**当前没有官方业务语义证据**支撑枚举设计；很容易把"未知"**误建模成"已知状态"**；
  修改范围更大（新增字段 + 枚举取值定义 + 全链路迁移）；
- 评估：**本轮不推荐立即新增**（详见 §17.7）。

**Alternative D — 新建另一类 Offering DTO / `UnknownScheduleOffering`**

- 评价：**MVP 过重**；会**扩大跨模块契约**（增加实体与转换层）；
  当前证据**不足以支持拆分实体**；
- ⛔ **不得擅自选 D**。

**汇总**

| 方案 | 是否改公共契约 | 是否保留真实教学班 | 是否需猜学校语义 | 主要风险 |
|---|---|---|---|---|
| A 过滤 | 否 | ❌ 会丢 | 否（但隐含"这些是无效记录"的判断） | 丢失真实教学班记录 |
| **B `minItems = 0`（推荐）** | 是（放宽） | ✅ | 否 | Planner 误判为无冲突（须配套安全规则） |
| C `schedule_status` | 是（新增字段） | ✅ | ⚠️ 很可能 | 把"未知"伪装成"已知状态" |
| D 独立 DTO | 是（新增实体） | ✅ | 否 | MVP 过重、跨模块契约扩大 |

### 17.7 为什么**暂不**新增 `schedule_status` / `schedule_known` / `schedule_state`

- 当前真实来源**只**证明：**当前快照缺少可用排课信息**；
- **没有**任何官方证据支持这些枚举取值：`pending` / `asynchronous` / `cancelled` /
  `unscheduled` / `not_required`；
- 如果现在设计枚举，**很容易把未知业务语义伪装成已知状态**，
  下游（Planner / 前端 / 用户）会误以为这是一个**学校确认过的状态**；
- 因此本轮推荐：**用 `meetings = []` 表达"排课信息不可用"，不新增业务状态枚举**；
- ⚠️ 但必须把"**显式状态字段**"作为**替代方案**列入比较（见 §17.6 Alternative C），
  供 Architecture Lead 权衡。
- ✅ **裁决结果（2026-10-01）**：**本轮不批准新增** `schedule_status` /
  `schedule_known` / `schedule_state` —— **当前不需要额外公共状态字段**
  （见 §17.5.1）。⛔ 未来若要新增，须走**新的 `【接口变更请求】`**。

### 17.8 `meetings = []` 的**精确定义**（必须随契约一起写明）

**`meetings = []` 仅表示：**

> **当前来源快照没有提供能够形成公共 `Meeting` 的可用排课信息。**

**它不表示（逐条禁止）：**

- ⛔ 课程实际上**没有**上课时间；
- ⛔ **异步**教学；
- ⛔ **时间自由** / 可以任意排入任何时间；
- ⛔ **没有冲突** / **可以视为已验证无冲突**；
- ⛔ 学校确认"**尚未排课**"；
- ⛔ 该教学班**无效** / **应被过滤** / **不应进入 Planner**。

> ✅ **本定义已随 DG-07 一并获批**（§17.5.1）；实施时必须**逐字**保持这一语义，
> ⛔ 不得在实现或前端文案中改写成任何**业务状态**名称。

### 17.9 Planner 影响（**DG-07 的核心安全影响**）

> **核心不变量（必须写入接口变更影响分析）：`meetings = []` ≠ conflict-free。**
>
> ✅ **本不变量已随 DG-07 正式获批**（§17.5.1），**实施时必须落地**。

- ⛔ Planner **绝不能**因为"没有 `Meeting` 对象"就推导出"**没有任何时间冲突**"；
- ✅ 正确描述：`meetings = []` 表示 **schedule unknown / unavailable**，
  因此 Planner **不能**将该教学班视为"**已经验证无冲突**"的普通候选；
- **`offerings` 与 `current_schedule` 必须使用同一条规则**：
  - ⚠️ 两者都是公共类型 `CourseOffering[]`
    （见 `docs/interfaces/planner.md` / `docs/interfaces/integration.md`），
    **因此 `meetings = []` 的风险在两侧都存在**；
  - ✅ **对 `offerings` 和 `current_schedule` 中任何 `meetings = []` 的 `CourseOffering`，
    schedule 都视为 unknown**；
  - ⛔ **若 `current_schedule` 中存在 `meetings = []`**：Planner **不得**把其它候选声明为
    "**已验证与当前课表无时间冲突**" —— 因为"当前课表"本身有一段**时间占用未知**，
    任何"无冲突"结论都**不成立**（最多只能说"与**已知**时段不冲突"）；
- **保守 MVP 行为（✅ **已批准方向**；**具体实现细节待 Planner Implementation Review**）**：
  - 若 Planner 面对 `CourseOffering.meetings = []`（无论来自 `offerings` 还是
    `current_schedule`），**不自动**把它作为 **conflict-free candidate**
    选入最终确定性课表；
  - 若某个**必须处理**的 `MakeupTask` **只有** `meetings = []` 的候选教学班，
    方案应**显式进入 unresolved / 人工确认路径**，而**不是**静默选入或静默丢弃；
  - 若 `current_schedule` 含 `meetings = []`，相关"无冲突"断言应**整体降级为未知**，
    并**显式**进入 unresolved / 人工确认路径（⛔ 不得静默按"无冲突"处理）；
- **`PlanResult.unresolved[].type` 的候选约定**：
  - 现状：`plan_result.schema.json` 中 `unresolved[].type` 是**开放字符串**
    （`{"type": "string"}`），因此**无需改 Schema** 即可承载新类型；
  - 候选值（**candidate convention only**）：**`missing_schedule`**；
  - ⏳ **是否正式采用该命名，留到 Planner Implementation Review**（**本轮未批准**）；
    在正式定名之前，任何实现**不得**把它当作**已定的公共约定**；
- ⏳ **`PlanResult.status` 如何取值同样留到 Planner Implementation Review**：
  ⛔ 本轮**不批准**整体 `status` 必须是 `partially_feasible` 或 `infeasible`；
  最终 `status` 还要结合 Planner 现有状态语义
  （`plan_result.schema.json` 的 `feasible` / `partially_feasible` / `infeasible`）
  与 `unresolved[]` 的具体内容，由 Planner 实施评审决定。
  ⚠️ **已批准且不可协商的只有不变量本身**：`meetings = []` **不得**被当成
  "已验证无冲突"（含 `current_schedule` 一侧）。

### 17.10 Integration 影响

- 当前 `PlanningOrchestrator` **应保持透明传递**；
- ⛔ DG-07 **不建议改变**方法签名：
  `PlannerProvider.plan(...)`、`CourseDataProvider.get_course_offerings(...)`
  的签名**保持不变**（见 `docs/interfaces/integration.md`）；
- 若未来 Schema 被批准修改，Integration 应：
  - ⛔ **不解释** `meetings = []`（不做业务语义推断）；
  - ⛔ **不补** `Meeting`；
  - ⛔ **不**过滤；
  - ⛔ **不改变** `PlanResult`；
- 因此预期结果是：**Provider 方法签名不变，数据契约语义发生变化**。

### 17.11 Frontend 影响

- 若未来批准 DG-07，前端需要能够显示 `meetings = []` 的教学班；
- **建议产品文案候选**：**「排课信息暂缺」**；
- ⚠️ **必须注明**：这是"学航·转衔"对**数据状态**的说明，
  **不是**中山大学教务系统官方状态文字；
- ⛔ **本轮不得修改前端**（含类型与展示）。

### 17.12 Course Data 影响（DG-07 已批准，**实施待任务书**）

Course Data **应**（**实施阶段**落地）：

- **保留真实教学班记录**；
- **不仅因为缺 schedule 字段就静默过滤**；
- **不构造 fake `Meeting`**；
- **不从 `weekDay` / `timePlaceId` 猜 `Meeting`**；
- **可以**规范化为 `meetings = []`（**仅在 §17.12.1 允许的来源形态下**）；
- **必须保留**真实来源 / snapshot / `data_source` 边界
  （`data_source` 仍须明确 `mock` / `real`）。

> ⛔ **本轮仍未实施**：**不得修改** `importer` / `parser` / `normalizer` /
> `snapshot` / `collector` 的任何代码；⛔ 也**不得**在本轮实施 `minItems = 0`。

#### 17.12.1 **fail-closed 不变量**（DG-07 必须与本条一起批准）

> ✅ **本条已随 DG-07 正式获批**（§17.5.1）：**批准 `minItems = 0` 与批准本条是一个整体**，
> ⛔ **不允许**只实施 Schema 放宽而跳过本条。
>
> **`meetings = []` 只能表示「来源层没有提供可形成 `Meeting` 的排课信息」，
> ⛔ 绝不能作为 parser / importer / normalizer 解析失败的 fallback。**

- ⛔ **解析失败必须继续 fail closed**：不得把异常、畸形输入或"看不懂的格式"
  转写成 `meetings = []`；那会把**我们的解析缺陷**伪装成**学校的数据状态**；
- 这条不变量是 DG-07 的**组成部分**：**只批准 `minItems = 0` 而不批准本条，
  等于放行静默降级**。

**初始实施边界（按现有证据写死）**

✅ **已确认可映射为 `meetings = []` 的来源形态（唯一一种）**：

- **`teachingTimePlaceStr` 属性不存在**（字段缺失）。

⛔ **以下情况一律不得自动映射为 `[]`，必须继续 fail closed**
（除非将来有**独立真实证据 + 架构裁决**）：

| 来源形态 | 处置 |
|---|---|
| `teachingTimePlaceStr = null` | ⛔ **fail closed**（**不**映射为 `[]`） |
| `teachingTimePlaceStr` 为空字符串（`empty_string`） | ⛔ **fail closed** |
| `teachingTimePlaceStr` 为其它类型（`other_type`） | ⛔ **fail closed** |
| **非空但格式无法解析** | ⛔ **fail closed** |
| **malformed segment**（字段数 / 分隔符 / 结构异常） | ⛔ **fail closed** |
| **parser / normalization 抛异常** | ⛔ **fail closed**（异常原样向上，不吞掉） |

> ⚠️ 依据：C1B 的真实第 1 页样本中，`null` / `empty_string` / `other_type` **均为 0**，
> 即**现有证据只覆盖"属性不存在"这一种形态**；
> 其余形态**没有真实样本**支持"它们也应被视为排课信息不可用"，
> 因此**不得**顺手放宽（与 §10.1 的暂缓字段纪律、`/AGENTS.md` 第 18 节
> "不将推测写成真实事实"一致）。
>
> ⛔ 本边界的**扩大**（例如把 `empty_string` 也纳入）必须走
> **新的真实证据 + 架构裁决**，不得由实现层自行决定。

### 17.13 G11 状态（**不得升级为 resolved**）

```text
contract decision approved;
implementation pending;
school-side business cause still unknown
```

- ✅ **结构证据已收窄**（C1C）：差异集中在**排课相关字段**，
  而容量 / 已选人数字段完整、分类字段无 missing 组独占值；
- ✅ **业务语义获得部分界面证据**（C1D，**n = 2**）：
  两条候选在官方 UI 中作为普通教学班行存在、时间区域空白且无状态文字；
- ✅ **契约缺口候选已识别 → 契约处理方向已裁决**：**DG-07 =
  `APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**（§17.5.1）；
- ⏳ **implementation pending**：`schemas/` / `docs/interfaces/` / 代码 / 测试
  **尚未迁移**，Data Gate **仍未回到 CLOSED**（§12.3）；
- ⛔ **school-side business cause still unknown**：**学校侧为什么为空仍未查明**；
  「契约处理方向已裁决」**≠**「学校业务原因已经查明」；
- ⛔ **G11 仍不能写 resolved**；⛔ 也**不得**推断学校业务状态。

### 17.14 DG-07 本轮未做（明确边界）

- ❌ 修改 `schemas/`（含把 `minItems` 改为 0）
- ❌ 修改 `docs/interfaces/`（含 `course_data.md` 的 "`meetings` 至少 1 个"表述）
- ❌ 修改任何代码（Course Data / Planner / Integration / Frontend / `mock_data/`）
- ❌ 修改任何测试（含已锁定 `meetings: []` 必须失败的回归测试）
- ❌ 实施 `meetings = []` 的任何 workaround
- ❌ 决定 Planner 最终行为（`status` / `unresolved[].type` 正式取值）
- ❌ 认定 G11 resolved
- ❌ 新增 SYSU 请求（**Builder 实际请求数 = 0**）
- ❌ 开始任何实施阶段（**DG-07 仍为 `IMPLEMENTATION PENDING`**）

### 17.15 关闭 Data Gate 的前置条件（**未完成前不得 CLOSED**）

> ⚠️ 下列条件**全部**完成并经 **Reviewer 验收**后，才允许登记 **`DG-07 IMPLEMENTED`**
> 并把 Data Gate 回到 **CLOSED**。**本轮只登记条件，不开始任何一项。**

1. **DG-07 Contract Migration**：`schemas/course_offering.schema.json`
   （`meetings` `minItems: 1 → 0`，`required` 不变）、`docs/interfaces/course_data.md`
   同步，`backend/app/models/contracts.py`（`min_length`）与 `mock_data/` 迁移；
2. **Course Data**：§17.12.1 fail-closed 不变量落地
   （**仅 `teachingTimePlaceStr` 属性不存在**可映射为 `[]`）；
3. **Planner safety**：§17.9 不变量落地（`meetings = []` ≠ conflict-free，
   **含 `current_schedule` 一侧**）；
4. **Frontend / Mock**：类型与展示支持 `meetings = []`（文案候选「排课信息暂缺」）；
5. **tests**：新增/迁移回归用例（含既有"`meetings: []` 必须失败"用例的迁移）。

⛔ **在以上完成之前**：不得声称 DG-07 IMPLEMENTED、不得关闭 Data Gate、
不得把 `meetings = []` 当作已生效的公共契约。
