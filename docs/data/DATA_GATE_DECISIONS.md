# Data Gate-1 架构决策草案

> **状态：草案（DRAFT）。**
> 本文档**不是**裁决结果，**不是**已批准的接口变更，也**不是**公共契约的一部分。
> 其中的每一项都需要 **Reviewer + 负责人**逐条裁决（批准 / 驳回 / 修改）后才可能生效。
>
> ## 本文件的三条红线
>
> 1. **不修改 `/schemas/`、不修改 `/docs/interfaces/`。** 本文档只是**提出请求**。
> 2. **不自行决定字段名、字段类型、取值域与枚举。** 凡涉及具体字段形状的地方，一律标记
>    **待裁决**，由负责人决定。
> 3. **不自行进入 Data Gate-2。** 本轮只做整理，不做实施。
>
> 配套文档：
> `DATA_SOURCE_REGISTRY.md`（来源登记）、`REAL_TO_SCHEMA_GAP_REPORT.md`（缺口登记）、
> `SYSU_CASE_A_PUBLIC_EVIDENCE.md` / `SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md` /
> `SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md` / `SYSU_COURSE_OFFERING_RECON.md`（D1–D5 证据）。

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
| **不做** | 不改 Schema、不改接口文档、不写代码、不写 parser / crawler / Adapter / CourseDataProvider / Integration、不建数据库、不调 SYSU 接口、不裁决 |

### 1.3 本轮性质

```text
D1–D5 真实证据  →  缺口登记（REAL_TO_SCHEMA_GAP_REPORT）
                →  【本轮】Data Gate-1：决策草案 + 接口变更请求草案
                →  负责人裁决
                →  （若批准）契约更新  →  恢复 Phase 2B Integration / Course Data MVP
```

**只有负责人裁决通过的项，才可能在后续轮次实施。本文档本身不产生任何生效变更。**

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
> **不定义字段清单** —— 字段级设计一律待裁决。
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

### 3.5 `CurrentEnrollment` —— 学生当前已选 / 正在修读的教学班

| 项 | 内容 |
|---|---|
| **表示** | 学生**当前**已经选择 / 正在修读的**教学班**（"我的课表里现在有什么"） |
| **必须与之分开** | `CompletedCourse`（那是**已经修完**的）／`CourseOffering`（那是**学校开设的供给**）／`Preference`（那是**想要什么**） |
| **为什么必须要这个概念** | Planner 的**当前课表冲突检测**需要的正是"学生现在已占用哪些时间段"。若用 `CourseOffering` 代替，就等于把"学校开设的全部教学班"当成"我的课表"，冲突检测会**完全失真** |
| **当前承载** | **无** → **G4**（`docs/interfaces/planner.md` 把"当前课表"列为 Planner 输入，但 `/schemas/` 下没有对应文件）。⚠️ G4 **尚未用真实样本验证**，目前是"接口文档与 Schema 不一致"这一**文档级事实** |
| **数据所有权** | **用户私有数据**（见 §5） |

### 3.6 `CourseOffering` —— 某学期的一个教学班（供给）

| 项 | 内容 |
|---|---|
| **表示** | **学校在某学期开设的一个教学班**："现实中当前学期有哪些可用教学班" |
| **不表示** | 学生是否选了它；学生是否修过它；课程在培养方案中的身份（`courseCategoryName` 带方案上下文，**不得**当成课程全局属性） |
| **当前承载** | `schemas/course_offering.schema.json` |
| **真实证据** | `courseNum → course_id`、`courseName → course_name`、`classNumber → class_id`、`yearTerm → semester`、`limitNumber → capacity` 为 **A**；`score → credit` 为 **B**（字符串数字）；`remaining_capacity` 为 **B 派生值** |
| **已知结构缺口** | **G9：一个教学班可有多个上课时间 / 地点 segment，当前一个 `CourseOffering` 只能表达一组 → 无法无损表达**（见 §6 / DG-01） |

### 3.7 `ScheduleSegment` / `Meeting` —— 教学班下的一段上课时间 / 地点

| 项 | 内容 |
|---|---|
| **表示** | 一个教学班**内部**的一段独立排课："第几周（哪些周）、星期几、第几节到第几节、在哪个校区 / 教室" |
| **概念关系** | `CourseOffering` **1 —— N** `ScheduleSegment` |
| **至少需要表达（真实 D5 已存在的量）** | `weekday`、`start_section`、`end_section`、`weeks[]`、`campus`、`classroom` |
| **当前承载** | **无独立对象** —— 这 6 项目前是 `CourseOffering` 的**直接字段**，一个对象只能装一组 |
| **注意** | 这是一个**概念**。它是否成为**公共契约对象**、以什么形态存在，**待裁决**（见 DG-01）。⚠️ **不得理解为本文档已经设计了该对象。** |

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

---

## 4. 实体所有者

> "所有者"= **负责定义并生产该数据**的模块。所有者为 Curriculum / Course Data 的实体，
> 其他模块**只消费**，不得自行重写（`/AGENTS.md` 第 5 节）。

| 实体 | 所有者模块 | 消费方 | 当前是否公共契约 | 本文档建议（待裁决） |
|---|---|---|---|---|
| `Course` | **Curriculum**（课程基础身份可视为共享基础） | Course Data、Planner、Agent / Frontend | **是**（`course.schema.json`） | 保留为公共契约；`course_type` / `recommended_semester` 的归属见 DG-04 |
| `CurriculumVersion` | **Curriculum** | Planner（间接）、Agent / Frontend | **否**（G1） | 见 DG-04 |
| `CurriculumCourse` | **Curriculum** | Planner（间接）、Course Data（`courseCategoryName` 对齐）、Agent / Frontend | **否**（G1） | 见 DG-04 |
| `CompletedCourse` | **Curriculum**（由负责人私密侧产出的脱敏样本派生） | Agent / Frontend | **否**（G2） | 见 DG-02 |
| `CurrentEnrollment` | **Integration / Agent**（用户侧课表）× **Planner**（消费） | Planner | **否**（G4） | 见 DG-03 |
| `CourseOffering` | **Course Data** | Planner、Agent / Frontend | **是**（`course_offering.schema.json`） | 多 segment 表示见 DG-01 |
| `ScheduleSegment` / `Meeting` | **Course Data** | Planner | **否** | 见 DG-01 |
| `Preference` | **Agent / Integration**（由用户真实需求转换） | Planner | **是**（`preference.schema.json`） | 本轮不变 |
| `MakeupTask` | **Curriculum** | Planner、Agent / Frontend | **是**（`makeup_task.schema.json`） | 依赖 / 优先级见 DG-05 |
| `PlanResult` | **Planner** | Agent / Frontend | **是**（`plan_result.schema.json`） | 本轮不变（G5 未验证，暂不处理） |
| 学业优先级 / 风险 | **Curriculum** | Planner（消费，不得自行重算） | **否** | 见 DG-05 |
| 课程依赖结果 | **Curriculum** | Planner | **否**（但 `MakeupTask.prerequisites[]` 已存在） | 见 DG-05 |

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

来源为学校侧，**不含个人身份信息**，原则上可跨成员共享。

| 数据 | 说明 |
|---|---|
| `Course` | 课程基础身份与基础属性 |
| `CurriculumVersion` | 培养方案（专业 / 年级 / 版本） |
| `CurriculumCourse` | 课程在该方案中的要求（类别 / 推荐学期 / 分组 / 先修） |
| `CourseOffering` | 某学期教学班（供给） |
| **semester offering snapshot** | 某学期的**开课快照**（"这一学期学校开了什么"的时点切片） |

⚠️ 即使属共享数据，**认证来源的原始材料（docx、Raw JSON）仍不进入 public Git**，
仓库内只保留 `source_id`、来源性质、**汇总事实**与缺口结论。

### 5.2 用户私有数据（User-private）

**归属具体学生**，只能在授权范围内使用，**不得进入 public 仓库**（含脱敏逐行样本）。

| 数据 | 说明 |
|---|---|
| `CompletedCourse` | 已修课程事实（含实际修读学期、是否通过） |
| `CurrentEnrollment` | 当前已选 / 在读教学班 |
| `Preference` | 用户偏好与约束意愿 |
| **用户适用的 `CurriculumVersion` reference** | "**这个学生**适用哪一版培养方案"是一个**指向共享数据的私有引用**：培养方案本身是共享的，**但"该生适用哪一版"是私有信息**（由学籍异动时点、年级、专业决定，见 D1 政策） |

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

### 6.4 `teacher` 是否存在 meeting-level 语义 —— 本轮结论

| 检查项 | 本轮可确认的事实 | 结论 |
|---|---|---|
| 真实 D5 样本中 `teachingName`（授课教师）出现的位置 | 出现在**教学班层级**，未观察到 segment 级的教师字段 | **没有证据**表明教师是 meeting 级语义 |
| 一个教学班内不同 segment 是否可能由不同教师授课 | **未观察到**，也未做进一步侦察 | **无法确认**；属**语义待确认** |
| `weekDay`（星期）与 segment 的对应关系 | 侦察记录已标记为**待确认** | 不猜 |

**本轮建议（待裁决）**：

- **MVP 阶段 `teacher` 保持在教学班级**（沿用现有公共字段），**不将其下放到 segment**；
- **不新增 segment 级教师字段**；
- 若将来证实"同一教学班内不同 segment 由不同教师授课"，再按 `/AGENTS.md` 第 4 节走
  `【接口变更请求】`。

### 6.5 候选方案与权衡（**本轮不作最终决定**）

| 方案 | 形态 | 优点 | 代价 / 风险 |
|---|---|---|---|
| **A. 在教学班内引入 segment 数组** | `CourseOffering` 增加一个 segment 数组（字段名 / 类型待裁决），原 6 个单值字段退役或改为"兼容视图" | 概念最清晰，与 6.2 的关系一致；Planner 可精确比较两个教学班的**全部**时间占用 | **破坏性**：现有 `course_offering.schema.json` 的 `weekday` / `start_section` / `end_section` / `weeks` 是**必填**；`mock_data/course_offerings.json`、`backend/app/models/contracts.py`、`frontend` 类型与展示、启动自检都会受影响 |
| **B. 保留单段字段，另加可选的段数组** | 原字段保留（作为"第一段"或"合并视图"），新增可选 segment 数组 | 对旧数据向后兼容（旧数据仍合法） | **双份表示**：同一信息两处存放，容易出现"字段与数组不一致"；Planner 必须同时读两处，语义不清晰 |
| **C. 同一 `class_id` 多行（扁平化）** | 一个 segment 一行，多行共享同一 `class_id` | **完全不改 Schema** | ① 与"`class_id` 标识一个教学班"的现有隐含假设冲突；② `PlanResult.selected_classes[]` 只引用 `course_id` + `class_id`，**无法区分同一教学班的哪一段**；③ 消费方必须自行聚合，等于把契约问题推给每个下游 |
| **D. Course Data 内部保留完整 segment，对外只暴露合并后的时间占用** | 公共契约不变 | 完全不改 Schema | **丢失 segment 身份**：Planner 做"教学班替换"时无法精确比较"换掉这一段是否解决冲突"，Path Repair 质量下降 |

### 6.6 明确禁止的两个方案

> 以下两条是**负责人已经明确禁止**的，本轮不得作为候选方案：

1. ❌ **只保存第一个 segment**（丢弃其他时间段）—— 直接**丢失真实排课信息**，
   使冲突检测产生**假阴性**（漏检冲突），Planner 会输出**不可执行的方案**；
2. ❌ **把一个教学班拆成多个可独立选择的 `CourseOffering`** —— 会凭空造出**学校并不存在的可选教学班**，
   学生"替换教学班"时会选到一个实际不存在的班，属**捏造数据**。

### 6.7 与"是否引入 `meetings[]`"的关系

`REAL_TO_SCHEMA_GAP_REPORT.md` 明确记录：本轮**未设计 `meetings[]`、未修改 Schema**。
本文件同样**不设计 `meetings[]`** —— §6.5 的方案 A 只是**候选方向**，
**字段名、类型、是否必填、命名（`meetings` / `segments` / 其它）一律待裁决**。
**最终表示方式由负责人裁决，见 DG-01。**

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
⚠️ **本轮不修改 `docs/interfaces/planner.md`**（该目录属公共契约，`/AGENTS.md` 第 4 节）。

### 7.3 `MakeupTask.prerequisites[]` 是否已足够？（重点分析）

**现有字段**（`makeup_task.schema.json`）：`course_id` · `course_name` · `credit` · `status`（枚举 4 值）·
`deadline_semester?` · `recommended_semester?` · **`prerequisites[]?`** · `reason?` · `source_evidence?`

| 问题 | 分析 |
|---|---|
| Planner MVP 需要什么依赖信息？ | ① "补修 A 之前必须先补 B"的**先后关系**（跨学期路径排序）；② 冲突检测**不需要**依赖图（冲突只需时间 / 周次信息） |
| `prerequisites[]` 能表达什么？ | 它是**课程号字符串数组**，可表达"这门课的**直接**先修课程集合" → 足以构成**直接的依赖边** |
| 是否足够？ | **很可能足够**（待裁决）：<br>① **不需要新增 `DependencyGraph` 公共 Schema** —— Planner 可由 `MakeupTask[]` 中每条任务的 `prerequisites[]` **自行重建**邻接关系（只要相关课程都在同一 `MakeupTask[]` 中）；<br>② 它是**已存在的公共字段**，无需任何契约变更；<br>③ `recommended_semester` / `deadline_semester` 已可承载"时间先后"的粗粒度约束 |
| 可能的不足 | ① 只有**一级邻接**，不表达传递闭包（但可由消费方计算）；② **无"依赖类型"**（强先修 / 建议先修 / 并修），当前**无真实证据**支持需要区分；③ 无**优先级**（另见 7.4）；④ ⚠️ **最重要**：真实培养方案样本中**未发现明确的先修字段**，因此 `prerequisites[]` **能否被真实数据填充，目前尚无证据** |
| **本轮建议方向（待裁决）** | **优先不新增 `DependencyGraph` 公共 Schema。** MVP 由 `MakeupTask[]` + `prerequisites[]` 承载依赖；依赖图的**构建**留在 Planner 内部（消费 Curriculum 已给定的先修关系），**不新增跨模块对象** |

> ⚠️ **区分两件事**：Planner **自己计算依赖图的闭包 / 拓扑序** ≠ Planner **自行认定哪些课是先修**。
> 前者是确定性算法，属 Planner；后者是**学业规则**，属 Curriculum。`/AGENTS.md` 禁止的是后者。

### 7.4 "已确认优先级"是否需要进入公共契约？

**事实**：`/AGENTS.md` 第 5 节要求 Planner 消费 Curriculum 的"**已确认优先级**"，
但 `makeup_task.schema.json` **没有 priority 字段**，`/schemas/` 下也**没有**优先级对象。

| 候选 | 分析 |
|---|---|
| **① 新增 `priority` 一类字段（方向性建议）** | 最能直接满足 `/AGENTS.md` 第 5 节。<br>⚠️ **字段名、类型（整数 / 枚举 / 序数）、取值范围、枚举取值、是否必填 —— 一律不得由 Agent 决定，全部待裁决**（见 DG-05） |
| **② 用 `MakeupTask[]` 的数组顺序承载优先级** | 不改 Schema。但 **Schema 从未定义数组顺序的语义**，属**隐式约定**；`/AGENTS.md` 第 5 节禁止"只有两边懂的私有格式"，且下游可能重排数组 → **不可靠** |
| **③ 用 `recommended_semester` + `deadline_semester` 承载** | 不改 Schema。能表达"时间紧迫性"，但**不能表达学业优先级**（两门课可以同一学期、同一 deadline，优先级不同） |
| **④ 用 `reason` 自由文本承载** | **不可用于求解** —— `/AGENTS.md` 要求确定性判断不得交给 LLM / 自由文本，违反第 1、5 节 |
| **⑤ 优先级留在 Curriculum 内部，Planner 不做排序** | **不改任何接口**，可能符合 MVP。前提是负责人确认 **Planner MVP 是否真的需要跨模块优先级**；若 Planner 只需按 Curriculum 给出的顺序求解，则该字段可以暂不引入 |

**本轮建议方向（待裁决）**：把 ① 作为**方向**提交（DG-05），
但**明确保留 ⑤ 这一"不改接口"的替代方案** ——
是否需要该字段，本质上取决于**负责人对 Planner MVP 职责范围的确认**。

---

## 8. 当前 Schema / Interface 缺口

| 编号 | 缺口 | 证据等级 | 影响模块 | 处置 |
|---|---|---|---|---|
| **G1** | 培养方案 / 版本 / 课程分组**无正式表示** | **已由 `CURR-OLD-003` / `CURR-NEW-004` 确认** | Curriculum（+ Course Data / Planner 间接） | **DG-04** |
| **G2** | 已完成课程 / 修读事实**无正式表示** | **已由 `TRANSCRIPT-001` 验证** | Curriculum、Agent / Frontend | **DG-02** |
| **G3** | 学分差额无结构化表达 | **未验证** | Curriculum / Agent | 本轮不处理，留缺口报告 |
| **G4** | "当前课表"`planner.md` 列为输入，但无 Schema；`CourseOffering` ≠ 学生已选 | **文档级事实**（未用真实样本验证） | Planner、Integration | **DG-03** |
| **G5** | `PlanResult` 无冲突对象（只能从 `changes[].reason` 文本读出） | **未验证** | Planner / Agent | 本轮不处理，留缺口报告 |
| **G6** | `StudentProfile` | **已裁决**（不是可用契约，不得依赖） | 全部 | 已关闭（见缺口报告 §4.1） |
| **G7** | `CourseOffering` 无课程类别 / 开课单位 | **已由 `OFFERING-001` 验证** | Course Data / Planner | 见 §10（暂缓字段） |
| **G8** | `Preference` 无法表达"已经有什么" | **未验证** | Agent / Planner | 本轮不处理；⚠️ 若 DG-02 / DG-03 通过，该缺口可能**自然缓解**（"已有什么"由 `CompletedCourse` / `CurrentEnrollment` 表达，不再压到 `Preference` 上） |
| **G9** | **一个教学班多个 segment 无法无损表达** | **已由 `OFFERING-001` 验证** | Course Data / Planner | **DG-01**（本轮最重要） |
| **G10** | D5 另有多个字段无表示 | **已由 `OFFERING-001` 验证** | Course Data / Planner | 见 §10 |
| **新-1** | `docs/interfaces/planner.md` 职责描述与 `/AGENTS.md` 第 5 节**冲突** | **文档级事实**（可立即核实） | Planner / Curriculum | **DG-06** |
| **新-2** | "已确认优先级"无承载位置 | `/AGENTS.md` 第 5 节要求 + Schema 无字段 | Curriculum / Planner | **DG-05** |
| **新-3** | 课程依赖结果无正式公共对象 | `/AGENTS.md` 第 5 节要求 + 无 Schema | Curriculum / Planner | **DG-05**（倾向**不新增**，见 7.3） |
| **新-4** | `Course` 上的 `course_type` / `recommended_semester` **位置不当**（带方案上下文） | 2B-0C Review 已改判 | Curriculum | **DG-04**（兼容 / 迁移策略待裁决） |
| **新-5** | 推荐学期**跨学期区间**无法用单个整数表达 | `CURR-OLD-003` / `CURR-NEW-004` | Curriculum | 并入 **DG-04** |

**⚠️ 缺口 ≠ 必须新增 Schema。** 每条都可能是：数据侧转换 / 模块内部输入 / 数据不应进系统 /
确属契约承载不了。§13 的每项请求都单独回答"是否存在不修改接口的替代方案"。

---

## 9. 最小接口变更集合

> **最小化原则**：能用现有字段表达的，不新增字段；能作为模块内部输入消化的，不进公共契约；
> 只有确属"契约承载不了"的，才进入变更请求。

| 优先级 | 项 | 为什么属于"最小必要" |
|---|---|---|
| **P0（不解决则无法进入真实联调）** | **DG-01 `CourseOffering` multi-segment** | 真实教学班数据**无法无损进入系统**；冲突检测、教学班替换、Path Repair 全部建立在教学班的时间占用上。当前契约下只能丢信息或造数据 |
| **P0** | **DG-03 `CurrentEnrollment`** | Planner 的**核心功能就是冲突检测**；没有"学生当前占用"的概念，冲突检测无输入（DG-03 另有"不改接口"的降级替代方案，见 §13） |
| **P1（Curriculum 真实输出所必需）** | **DG-02 `CompletedCourse`** | Curriculum 要把"已修课程"变成 `MakeupTask`；`semester` / `passed` 在 `Course` 中**无位置**，且**严禁**塞回 `Course` |
| **P1** | **DG-04 `CurriculumVersion` / `CurriculumCourse`** | 培养方案级总量、课程分组、方案上下文 `course_type`、跨学期区间**都无承载位置**；且直接决定 `Course.course_type` 的归属 |
| **P1** | **DG-05 依赖 / 优先级** | `/AGENTS.md` 第 5 节要求 Planner 消费"课程依赖结果"与"已确认优先级"；依赖**倾向不新增对象**，优先级**可能可暂不引入** |
| **P2（文档一致性，无字段变更）** | **DG-06 `planner.md` 职责修正** | 不改 Schema，只消除接口文档与 `/AGENTS.md` 的冲突，防止 Planner 成员越界实现 |

### 9.1 本轮不进入变更集合的项

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
| `courseCategoryName`（课程类别，样本"专必"） | **B（且归属需转移）** | **培养方案上下文属性，不能当课程全局属性** → 归属见 **DG-04**（`CurriculumCourse`），**不进入 `CourseOffering`**。⚠️ 取值体系与粒度**待人工确认** | 与 D4 的 `course_type` **同源问题**；真实培养方案中该信息以**分区标题 / 行内"课程性质"列**形态出现 |
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
| **Planner** | 消费符合 `course_offering.schema.json` 的 `CourseOffering` | **不接触学校接口**；不知道 Cookie / 认证方式 / endpoint / 分页参数 |
| **Integration** | 通过 `CourseDataProvider` 读取标准化结果 | **不知道 Cookie、SYSU endpoint、分页规则**等实现细节 |
| **Course Data** | 在授权范围内获取、清洗、标准化、去重、记录来源与 `data_source` | 不判断学生是否需要补修；不决定补修优先级；不越过 `docs/interfaces/course_data.md` 的安全边界 |
| **任何人** | —— | 不绕过登录、不破解验证码、不越权访问、不枚举未授权数据、不保存密码 / Cookie / Session / Token、不提交 HAR |

### 11.3 本轮明确不做

- ❌ **不实现** Course Data Adapter / Importer / Normalizer / Provider；
- ❌ **不写** crawler / 抓取脚本；
- ❌ **不调用** SYSU 接口（本轮**零请求**）；
- ❌ **不建**数据库、**不写** ORM / migration；
- ❌ **不进入** Integration。

### 11.4 完整 2026-1 开课数据获取的定位

**完整 2026-1 开课数据获取属于 Data Gate 之后的 Course Data MVP，不在本轮范围。**

当前 D5 只有**小规模人工侦察**（`CSE202` / `2026-1` → 2 个教学班）。
正式获取必须等：① DG-01 的表示方式定了；② 采集范围经负责人批准；③ 合规边界确认。
（人工技术侦察**已到此结束**，不再继续查询更多课程。）

---

## 12. Data Gate 通过条件

> 以下条件**全部满足**，才视为通过 Data Gate，可以恢复 Phase 2B Integration / Course Data MVP。
> 任一条未满足，**Phase 2B Integration 保持暂停编码**。

| # | 条件 | 判定方 |
|---|---|---|
| **C1** | **DG-01 – DG-06 逐项裁决完毕**（批准 / 驳回 / 修改），且裁决结论**书面记录**在本文件或负责人指定的位置 | 负责人 |
| **C2** | **实体边界与所有者无异议**：Curriculum / Course Data / Planner / Integration / Frontend 五方对 §3 / §4 的划分达成一致 | 负责人 + 各模块 |
| **C3** | **Shared / Private / Derived 分类确认**（§5），特别是"用户适用的 `CurriculumVersion` reference 属私有"这一条 | 负责人 |
| **C4** | **多 segment 表示方式确定**（§6 / DG-01），且明确**未**采用"只保留第一段"与"拆成多个可独立选择的 `CourseOffering`"两个被禁方案 | 负责人 + Course Data + Planner |
| **C5** | **契约变更（如有）已走完流程**：`/AGENTS.md` 第 4 节的 `【接口变更请求】` → 人工确认 → **才**修改 `/schemas/` 与 `/docs/interfaces/`；并**同步**评估对 `mock_data/`、`backend/app/models/contracts.py`（启动自检）、`frontend` 类型与展示的影响与回归测试范围 | 负责人 + 各模块 |
| **C6** | **暂缓字段清单确认**（§10）：`teachProgressSubmitState` / `openClass` / `outlineTypeNum` 等**不进入公共契约**，保持待确认 | 负责人 |
| **C7** | **Curriculum → Planner 契约确定**（§7 / DG-05）：明确 Planner MVP 是否引入优先级；明确依赖信息由 `MakeupTask.prerequisites[]` 承载（或另有裁决） | 负责人 + Curriculum + Planner |
| **C8** | **接口文档债务修正决定**（DG-06）：`docs/interfaces/planner.md` 是否按 `/AGENTS.md` 第 5 节修正，及由谁执行 | 负责人 |
| **C9** | **Course Data 获取边界与合规确认**（§11）：采集范围、授权方式、标准化责任、`data_source` 标记规则 | 负责人 + Course Data |
| **C10** | **数据交接方式确认**：`MEMBER_DATA_HANDOFF.md` 已更新为当前状态（GitHub 可直接共享 / 非公开按需交接 / 禁止交接三层），且**真实逐行数据的交接次数如实记录** | 负责人 |
| **C11** | **真实数据未使用的字段风险已知悉**：`prerequisites[]` 无真实证据支持可填充（§2.2）、`weekDay` / `openingSchoolName` 映射待确认 | 负责人 |

### 12.1 通过 Gate 之前，任何模块不得

- 修改 `/schemas/` 或 `/docs/interfaces/`（除非按 C5 走完流程）；
- 写 Course Data Adapter / Normalizer / `CourseDataProvider`；
- 进入 Phase 2B Integration / Orchestrator 编码；
- 在代码中定义"只有两边懂"的私有跨模块结构来绕过公共契约（`/AGENTS.md` 第 5 节）；
- 把 Mock 数据当作 Real，或把 Real 数据当作 Mock。

---

## 13. 接口变更请求草案（DG-01 – DG-06）

> ⚠️ **以下全部是草案，不代表批准。**
> ⚠️ **凡涉及字段名 / 类型 / 取值域 / 枚举 / 是否必填，一律不在此处锁定**，由负责人裁决。
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

---

## 14. 本文件不做什么

- 不修改 `/schemas/`、`/docs/interfaces/`、`/AGENTS.md`；
- 不修改 `backend/`、`frontend/`、`mock_data/`；
- 不写 parser、crawler、Adapter、Normalizer、`CourseDataProvider`、Integration；
- 不建数据库、不写 ORM / migration、不设计 PostgreSQL 表；
- 不调用 SYSU 接口（本轮**零请求**）;
- 不锁定任何字段名 / 类型 / 取值域 / 枚举；
- 不代替负责人做最终裁决；
- 不自行进入 Data Gate-2。

---

## 15. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-30 | **建立本文件（Data Gate-1）** | 依据 D1–D5 真实证据与 `REAL_TO_SCHEMA_GAP_REPORT.md`（G1–G10）：① 整理 7 个核心实体边界（`Course` / `CurriculumVersion` / `CurriculumCourse` / `CompletedCourse` / `CurrentEnrollment` / `CourseOffering` / `ScheduleSegment`）；② 给出实体所有者、Shared / Private / Derived 分类与 Course Data 获取边界；③ 对 **G9 多 segment** 给出概念关系、6 项 segment 量、`teacher` 层级结论与 4 个候选方案（含明确禁止的 2 个方案）；④ 分析 `Curriculum → Planner` 契约（`prerequisites[]` 是否足够、"已确认优先级"是否进契约）并登记 `docs/interfaces/planner.md` 的**接口文档债务**；⑤ 提交 **DG-01 – DG-06** 六项 `【接口变更请求】` **草案**与 **12 条 Data Gate 通过条件**。**未修改 Schema / Interface / 代码，未调用 SYSU 接口，未裁决任何一项。** |
