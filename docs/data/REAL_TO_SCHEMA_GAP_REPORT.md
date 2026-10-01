# 真实数据 → 公共 Schema 承载能力分析（框架）

> **状态：分析框架 ＋ 四轮真实材料验证。**
> Phase 2B-0B 取得部分公开官方材料（见 `SYSU_CASE_A_PUBLIC_EVIDENCE.md`）；
> **Phase 2B-0B+ 取得 Case A 两份 2025 级真实培养方案（认证来源，见
> `SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`）** → **G1 升级为「由 Case A 两份
> 2025 级真实培养方案确认存在」**（见 4.3），`Course` 字段映射按样本逐项判定 A/B/C（见 3.1）；
> **Phase 2B-0C 取得 D4 真实已修课程脱敏样本（见 `SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md`）**
> → **G2 更新为「已由 Case A 真实 D4 样本验证」**（见 4.4），D4 的 8 个字段逐项判定 A/B/C（见 3.6）；
> **Phase 2B-0D 取得 D5 真实教学班侦察样本（见 `SYSU_COURSE_OFFERING_RECON.md`）**
> → **G7 升级为「已由真实 D5 样本验证」**（见 4.5），
> **新增 G9**（一个教学班多个上课时间 / 地点 segment 无法无损表达）与
> **G10**（D5 另有多个字段无表示）；`CourseOffering` 字段映射逐项判定 A/B/C（见 3.2）；
> 其余观察（G3 / G4 / G5 / G8）**仍未验证**，保持「待验证」。
>
> ## 红线（本文件最重要的两条）
>
> 1. **真实字段无法映射时，只记录潜在缺口，不修改公共 Schema。**
> 2. **禁止在本文件中自行设计新的正式公共字段。** 任何新增 / 修改 / 删除公共字段的提议，
>    都必须走 `/AGENTS.md` 第 4 节的 `【接口变更请求】`，并由负责人确认后才可能实施。
>
> 本文件的产物是"**问题清单**"，不是"**字段方案**"。
>
> 另需注意：**发现缺口不等于最终一定要新增 Schema。** 有些缺口可能通过模块内部输入、
> 数据侧转换或流程调整解决。本文件**不预设**解法。

---

## 1. 目的

Phase 1 建立的公共 Schema 是**在没有真实数据的情况下设计的**。
在投入真实 Curriculum / Planner 开发之前，必须回答一个问题：

> 学校真实数据的形态，能否被现有 5 个公共 Schema 承载？

如果不能，就必须**在写代码之前**发现，而不是等到模块写完才回头改契约。
本文件就是做这件事的登记处。

**适用范围**：`course` / `course_offering` / `makeup_task` / `preference` / `plan_result` 五个 Schema。
`/schemas/` 与 `/docs/interfaces/` 在本阶段**一律不改**。

---

## 2. 分析方法（四步）

对每一份真实样本，逐字段执行：

```text
① 抽取：真实数据里到底有哪些字段？（只抽取，不加工）
        ↓
② 映射：每个真实字段能否落到现有 Schema 的某个字段上？
        ↓
③ 分类：
     A 完全可映射      —— 字段名可能不同，但语义与取值都能对上
     B 可映射但需转换  —— 例如"1-16周"→ weeks[]、"星期一"→ weekday=1
     C 无法映射 / 当前无正式表示 —— 现有 Schema 中找不到对应位置
        ↓
④ 登记：A / B 记录转换规则；C 只登记为"潜在缺口"，附真实样本出处
```

**登记要求**：

- 每条缺口必须附**样本出处**（`source_id`，见 `DATA_SOURCE_REGISTRY.md`），不允许凭印象登记；
- 只描述"**缺什么**"，不描述"**应该加什么字段**"；
- 若某条缺口可能影响多个模块，在"影响模块"列写全；
- 若某条缺口可能只是"模块内部输入"而不需要公共契约，也要如实记录这种可能性。

---

## 3. 逐 Schema 分析框架

> 下表的"真实字段"列在拿到样本前保持「待填写」。字段清单来自 `/schemas/*.schema.json` 的**现状**，如有变更以文件为准。

### 3.1 `course.schema.json`（Course）

**当前字段**：`course_id`(必填) · `course_name`(必填) · `credit`(必填) ·
`course_type?` · `recommended_semester?` · `prerequisites[]?` · `source?`
（`additionalProperties: false`）

| 真实字段（来自 Case A 两份 25 级培养方案） | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| 课程号（如 `FL101`、`MAR110`） | **A 可直接映射** | `course_id` | —— | Curriculum | `CURR-OLD-003` / `CURR-NEW-004` | 字母前缀 + 数字，Schema 只要求非空字符串，兼容 |
| 课程名（中文） | **A 可直接映射** | `course_name` | —— | Curriculum | 同上 | 文档中每门课另有**英文名一行** |
| 学分 | **A 可直接映射** | `credit` | —— | Curriculum | 同上 | 数值型 |
| 课程类别 / 模块（公共必修课 / 专业必修课 / 专业选修课 / 荣誉课程；附表三另有行内"课程性质"列如"公必"） | **B 可转换后映射** | `course_type` | 模块在文档中是**分区标题**（如"（公共必修课）"），**不是每门课的行内列**；需解析时按分区回填。只有附表三提供行内"课程性质" | Curriculum | 同上 | 取值粒度需人工确认。⚠️ 该字段带**培养方案上下文**，**不得**视为课程的全局固有属性；归属见 §3.6 的分类说明 |
| 推荐修读学期 — **单一学期值**（如 `2025-1`） | **B 可转换后映射** | `recommended_semester` | 可映射，**前提是**按 **2025 级培养进程**把"学年-学期"转换为**整数学期序号**；**具体转换规则仍待确认**（进程起点、是否含夏季学期等） | Curriculum | `CURR-OLD-003` / `CURR-NEW-004` | 转换规则需人工确认 |
| 推荐修读学期 — **跨学期区间**（如 `2025-1~2025-2`、`2025-1~2028-2`） | **C 当前无法无损表示** | ——（`recommended_semester` 只能存**单个 integer**） | 区间信息**无法无损表示**：现有字段只能存一个整数，装不下"跨若干学期"的语义 | Curriculum | `CURR-OLD-003` / `CURR-NEW-004` | **不设计新字段、不修改 Schema** |
| 学时 | **C 当前没有正式表示** | —— | `Course` 无学时字段 | Curriculum | 同上 | —— |
| 实验 / 实践学时、实践类型（附表一第三个数值列；附表三"实践类型"如"理论+实践""其他集中性实践"） | **C 当前没有正式表示** | —— | 无对应字段 | Curriculum | 同上 | 附表一该列的**列名未出现在提取文本中**，语义待人工确认 |
| 培养方案总学分（147.0 / 153.0） | **C 当前没有正式表示** | —— | 属**培养方案级总量**，不是单门课属性 | Curriculum | 同上 | —— |
| 实践教学学分要求（37.1 / 38.5） | **C 当前没有正式表示** | —— | 同上，培养方案级 | Curriculum | 同上 | —— |
| 培养方案适用年级（"25级"） | **C 当前没有正式表示** | —— | 年级只出现在文档标题中；Schema 无版本 / 年级字段 | Curriculum | 同上 | —— |
| 专业（遥感科学与技术 / 网络空间安全） | **C 当前没有正式表示** | —— | `Course` 无"所属专业"字段，培养方案的专业归属无处承载 | Curriculum | 同上 | —— |
| 课程分组 / 模块归属（作为独立对象） | **C 当前没有正式表示** | ——（部分可由 `course_type` 近似承载） | 没有"培养方案课程分组 / 模块"这类对象 | Curriculum | 同上 | 与"课程类别"同源 |
| 英文课程名 | **C 当前没有正式表示** | —— | 无对应字段 | Curriculum | 同上 | —— |

**本次材料中未能检索到、因此无法验证映射的信息**（不是 Schema 缺口，是**本样本的覆盖缺口**）：

- **先修 / 前置课程关系**：`Course.prerequisites` 字段存在，但
  **本次可检索文本中未发现明确的先修 / 前置课程字段或条款**，因此**无法用本样本验证该字段的映射**。
  ⚠️ **这只是对本次两份材料的观察，不构成"学校制度中没有先修要求"的结论。**
- 授课教师、考核方式、开课单位：**本次可检索文本中未发现**对应字段或条款
  （同样**不构成**对学校制度的结论）。

### 3.2 `course_offering.schema.json`（CourseOffering）

> ⚠️ **本节记录的是 Data Gate-1 当时（DG-01 实施前）的字段形态。**
> **Data Gate-2 已实施 DG-01**：`CourseOffering` 顶层不再有排课字段，
> 改为 `meetings[]`（1 — N）。**历史分析保留在下方表格中，未删改**；
> 当前真实字段见 `schemas/course_offering.schema.json`。

**Data Gate-1 当时的字段**（保留为历史记录）：`course_id` · `course_name` · `class_id` · `semester` ·
`teacher?` · `credit?` · `weekday` · `start_section` · `end_section` · `weeks[]` ·
`campus?` · `classroom?` · `capacity?` · `remaining_capacity?` · `source?` · `data_source`

**Data Gate-2 之后的字段**：`course_id` · `course_name` · `class_id` · `semester` ·
`teacher?` · `credit?` · **`meetings[]`（必填，`minItems: 1`）** · `capacity?` ·
`remaining_capacity?` · `source?` · `data_source`；
每个 `Meeting` = `weekday` · `start_section` · `end_section` · `weeks[]` · `campus?` · `classroom?`。

| 真实 D5 字段 | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| `courseNum`（课程号） | **A 可直接映射** | `course_id` | —— | Course Data / Planner | `OFFERING-001` | 公共标识优先采用它，而非后台 `courseId` |
| `courseName`（课程名称） | **A 可直接映射** | `course_name` | —— | 同上 | 同上 | —— |
| `classNumber`（教学班号） | **A 可直接映射** | `class_id` | —— | 同上 | 同上 | 优先采用它，而非后台 `class_ID` |
| `yearTerm`（学年-学期） | **A 可直接映射** | `semester` | —— | 同上 | 同上 | —— |
| `score`（学分，**字符串数字**） | **B 可转换后映射** | `credit` | 需字符串 → number 转换 | 同上 | 同上 | —— |
| `teachingName`（授课教师） | **A/B** | `teacher` | 语义可对应；**教师姓名不入库** | 同上 | 同上 | —— |
| `limitNumber`（容量上限） | **A 可直接映射** | `capacity` | —— | 同上 | 同上 | —— |
| `selectedNumber`（已选人数） | **C 当前无直接字段** | —— | `CourseOffering` 没有"已选人数"字段 | 同上 | 同上 | 见 G10 |
| `limitNumber - selectedNumber`（剩余容量） | **B 派生值** | `remaining_capacity` | **必须有明确说明：学校接口并未直接提供 `remaining_capacity`，它是两个字段相减得到的派生值** | 同上 | 同上 | **不得声称接口直接提供该字段** |
| `teachingTimePlaceStr`（上课时间地点**原始文本串**） | **单个 segment：B 可转换后映射**；**整个教学班：C 无法无损映射** | 单个 segment → `weeks` / `weekday` / `start_section` / `end_section` / `campus` / `classroom` | **必须分两层看（见下方说明）**：<br>① **单个 schedule segment** 可解析为 `weeks` / `weekday` / `start_section` / `end_section` / `campus` / `classroom` → 属**数据转换层能力（B）**；<br>② **整个教学班**：该字段**可包含多个 segment**，而当前一个 `CourseOffering` **只能表达一组** → **无法无损映射（C）→ G9** | Course Data / Planner | `OFFERING-001` | **本轮不实现 parser**；**原始串不入库** |
| `openingSchoolName`（开课校区 / 学校） | **B 待确认** | 与 `campus` 相关 | **字段真实存在**，与 `campus` **有关联**；**具体转换关系待确认** | 同上 | 同上 | **不猜** |
| `weekDay`（星期） | **B 待确认** | 与 `weekday` 相关 | **字段真实存在**，与 `weekday` **有关联**；**它与 segment 的对应关系待确认**（多 segment 时如何取值不明） | 同上 | 同上 | **不猜** |
| `openingUnitName`（开课单位） | **C 当前无正式表示** | —— | `CourseOffering` 无"开课单位"字段 | 同上 | 同上 | 见 **G7**（本轮升级）与 G10 |
| `courseCategoryName`（课程类别） | **C 当前无正式表示** | —— | 无对应字段；⚠️ **且带培养方案 / 上下文语义**（与 D4 的 `course_type` 同源问题），**不得认定为课程全局固有属性** | 同上 | 同上 | 见 G10 |
| `examMode`（考核方式） | **C 当前无正式表示** | —— | 无对应字段 | 同上 | 同上 | 见 G10 |
| `readObj`（修读对象） | **C 当前无正式表示** | —— | 无对应字段；**完整文本不入库** | 同上 | 同上 | 见 G10 |
| `teachProgressSubmitState` / `openClass` | **C 当前无正式表示** | —— | 无对应字段；**业务语义待确认** | 同上 | 同上 | **不根据 0/1 自行解释** |
| 内部 ID / 计数：`class_ID`、`sumClassesID`、`sumClassesNum`、`courseId`、`outLineId`、`outlineTypeNum`、`timePlaceId` | **不映射** | —— | **不等于**公共 `course_id` / `class_id`；**只记录其存在**，本轮**不设计对应字段**，**不记录其值** | 同上 | 同上 | —— |

> ⚠️ **本表「真实 D5 字段」列的填写纪律**：该列**只列 SYSU Response 中实际出现的字段**。
> `weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom` 是
> **公共 `CourseOffering` 的目标字段**，**不是** Response 的真实字段，因此**不得**出现在该列
> （早期版本曾误列，**已删除**）。
>
> **`teachingTimePlaceStr` 的两层区分（重要）**：
>
> 1. **单个 schedule segment** → 可解析为 `weeks` / `weekday` / `start_section` / `end_section` /
>    `campus` / `classroom`，**属数据转换层能力**；
> 2. **整个教学班** → 该字段**可包含多个 segment**，而**当时**一个 `CourseOffering` **只能表达一组**
>    → **无法无损映射**（**G9**）。
>    ✅ **该限制已由 Data Gate-2（DG-01）解除**：`CourseOffering` 现为 1 — N `meetings[]`（见 4.6）。
>
> ⚠️ **不得**把 `weekday` / `weeks` / `campus` 等写成"当前无正式表示" ——
> 这些字段**在 Schema 中一直存在**（Data Gate-2 后位于 `meetings[]` 内）；
> **历史上**真正的缺口是**多 segment 无法在一个 `CourseOffering` 中容纳**，现已修复。

### 3.3 `makeup_task.schema.json`（MakeupTask）

**当前字段**：`course_id` · `course_name` · `credit` · `status`（枚举 4 值）·
`deadline_semester?` · `recommended_semester?` · `prerequisites[]?` · `reason?` · `source_evidence?`

| 真实字段（待填写） | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | Curriculum / Planner | 待填写 | |

### 3.4 `preference.schema.json`（Preference）

**当前字段**：`max_credit?` · `avoid_cross_campus?` · `preferred_courses[]?` ·
`avoid_times[]?`（每项 `weekday` / `start_section` / `end_section`）· `notes?`
（全部字段可选）

| 真实字段（待填写） | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | Agent / Planner | 待填写 | |

### 3.5 `plan_result.schema.json`（PlanResult）

**当前字段**：`status`（枚举 3 值）· `selected_classes[]` · `changes[]` · `risks[]` ·
`unresolved[]` · `objective_summary?`

| 真实字段（待填写） | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | Planner / Agent | 待填写 | |

### 3.6 D4 真实样本对 `Course` 的字段映射验证（Phase 2B-0C）

**样本**：`TRANSCRIPT-001`（中山大学本科教务系统，"申请成绩转换 → 实修课程成绩" ＋ "本科生成绩单"，
由负责人在私密侧完成合并与脱敏），**24 条**记录，8 个字段覆盖率**均为 100%**。

| 真实 D4 字段 | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| `course_id`（课程号） | **A 可直接映射** | `Course.course_id` | —— | Curriculum | `TRANSCRIPT-001` | 均为唯一值 |
| `course_name`（课程名称） | **A 可直接映射** | `Course.course_name` | —— | Curriculum | 同上 | —— |
| `credit`（学分） | **A 可直接映射** | `Course.credit` | —— | Curriculum | 同上 | 取值 1–5，无 0 / 负值 |
| `course_type`（公必 / 专必 / 专选 / 公选） | **B 可转换后映射** | `Course.course_type` | 现有 `course_type` 是**自由字符串、无枚举**；**取值体系需人工确认** | Curriculum | 同上 | ⚠️ **这里只表示"现有契约能够承载该字符串值"**，**不证明**"公必 / 专必 / 专选 / 公选"是课程的**全局固有属性** —— 它可能依赖**具体培养方案 / 专业 / 年级上下文**，其**最终数据归属本轮不作架构裁决**（见下方归属分类） |
| `semester`（学生**实际修读**学期） | **C 当前无正式表示**（**且不得映射到 `recommended_semester`**） | —— | `Course` 中**没有**"学生实际修读学期"的位置；`recommended_semester` 是**培养方案建议学期**，**两者语义完全不同**，不可互相替代 | Curriculum | 同上 | 类型为字符串；**覆盖两个学期** |
| `passed`（**某个学生的一次修读结果**） | **C 当前无正式表示**（**且不得塞入 `Course`**） | —— | `passed` 是**学生的修读事实**，**不是课程固有属性**；`Course` 中没有任何承载位置 | Curriculum | 同上 | **覆盖率 24/24**；类型 / 语义 = **boolean**，表示"某学生一次修读**是否通过**"；**本轮不公开通过 / 未通过分布** |
| `offering_unit`（开课单位） | **C 当前无正式表示** | —— | 现有 Schema 中**没有任何"开课单位 / 院系"字段**（`Course` 与 `CourseOffering` 均无） | Curriculum / Course Data | 同上 | 观察到**多个不同开课单位**。⚠️ **本轮不据此升级 G7**：D4 只能证明"**已修记录**里有这个字段"，**不能证明教学班页面也提供同样字段**，须等 **2B-0D** 用真实教学班验证 |
| `cultivation_type`（培养类别，样本为"主修"） | **C 当前无正式表示** | —— | 它与 `course_type`（公必 / 专必 / 专选 / 公选）**不是同一语义**；**不得把 `cultivation_type` 强行当成 `course_type`** | Curriculum | 同上 | 样本内为单一取值，**完整取值域未知** |

**归属分类（本轮要回答的问题 ③④）**：

| 类别 | 字段 | 说明 |
|---|---|---|
| **课程核心标识 / 基础属性** | `course_id`、`course_name`、`credit` | 与具体培养方案、具体学生无关的课程标识与基础量 |
| **学生修读事实** | `semester`（实际修读学期）、`passed`（该次修读是否通过） | 同一门课由不同学生、在不同学期修读，结果可能不同 |
| **培养方案 / 上下文属性** | `course_type`（公必 / 专必 / 专选 / 公选） | **同一门课在不同专业 / 培养方案下可能被归入不同类别**（例如在专业 A 属专必、在专业 B 属专选、在某培养方案属公选）。<br>现有 `Course.course_type` 可以**承载其字符串值**，但这**不证明它是课程的全局固有属性** —— 它带有明显的**培养方案上下文**；**最终数据归属本轮不作架构裁决** |
| **归属待确认（本轮不下结论）** | `offering_unit`、`cultivation_type` | `offering_unit` 更像"开课侧"信息；`cultivation_type` 与培养方案语境相关，**本轮不判断其确切语义与完整取值域** |

> ⚠️ **不允许再把 `course_type` 描述为"与谁修读无关的课程固有属性"。**
> 本轮对 `course_type` 只得出一个结论：**真实 `course_type` 在字段形状上可以映射到现有 `Course.course_type`**（故记为 B）。
> 这与"该字段的归属已经正确建模"是**两回事**。

> ⚠️ **本轮未做任何课程等价判断**：即使样本与培养方案中出现名称相近的课程，
> 也**不判断**任何两门课等价、**不判断**任何课程可抵认或转换。
> 这些属于后续 Curriculum 逻辑 + 正式人工规则。

---

## 4. 待验证的初步观察（**仅记录，未经真实样本验证**）

> ⚠️ 以下是在**通读现有 Schema 与接口文档**后发现的"可能承载不了"的地方。
> **它们不是结论**：必须等真实样本到位后逐条验证。
>
> 本节**只描述缺口，不提出字段设计**，也**不预设**最终一定要新增 Schema ——
> 有些缺口可能最终只是"模块内部输入"或"数据侧转换"，无需进入公共契约。

| 编号 | 观察 | 依据 | 影响模块 | 状态 |
|---|---|---|---|---|
| G1 | **培养方案本身当前没有明确的跨模块公共 Schema / 正式表示**：现有 Schema 只能表达单门 `Course`，没有"培养方案版本 / 适用专业 / 适用年级 / 学分结构 / 课程分组（必修·选修·通识）"的正式表示 | `course.schema.json` 字段清单 ＋ **Case A 两份 2025 级真实培养方案 `CURR-OLD-003` / `CURR-NEW-004`**（认证来源） | Curriculum | **已由 Case A 两份 2025 级真实培养方案确认存在**（见 4.3） |
| G2 | **已修课程 / 成绩当前没有明确的跨模块公共 Schema / 正式表示**：Curriculum 要把"已修课程记录"变成 `MakeupTask`，但 `/schemas/` 下没有成绩单或"已完成课程"的对象；`Course` 也无法表达成绩、修读学期、是否通过 | `/schemas/` 目录清单 ＋ `docs/interfaces/curriculum.md` 的输入描述 ＋ **真实 D4 样本 `TRANSCRIPT-001`** | Curriculum | **已由 Case A 真实 D4 样本验证**（见 4.4） |
| G3 | **学分差额没有结构化表达**：现有 Mock 的 `MakeupTask.reason` 文本里出现"原 3 学分 / 新 2 学分"，但 Schema 中没有可承载"学分差额"的位置 | `mock_data/makeup_tasks.json` 62003007 + `makeup_task.schema.json` | Curriculum / Agent | 待验证 |
| G4 | **"当前课表"当前没有明确的跨模块公共 Schema / 正式表示**：`docs/interfaces/planner.md` 把"当前课表"列为 Planner 的输入，但 `/schemas/` 下没有对应文件；`CourseOffering` 表示"学校开设什么"，不等于"学生已选什么" | `docs/interfaces/planner.md` 对外输入 | Planner | 待验证 |
| G5 | **`PlanResult` 没有冲突对象**：冲突只能从 `changes[].reason` 的文本读出，无法计数或分类 | `plan_result.schema.json` 字段清单 | Planner / Agent | 待验证 |
| G6 | **`StudentProfile`：`AGENTS.md` 第 4 节列出了该名称，但 `/schemas/` 下没有对应文件** | `AGENTS.md` 第 4 节 vs `/schemas/` 目录 | 全部 | **已裁决（见 4.1）** |
| G7 | **`CourseOffering` 没有课程类别 / 开课单位**：`course_type` 只存在于 `Course`，教学班级别没有；`CourseOffering` 也没有"开课单位"字段 | 两个 Schema 字段对比 ＋ **真实 D5 样本 `OFFERING-001`**（出现 `courseCategoryName` 与 `openingUnitName`） | Course Data / Planner | **已由真实 D5 样本验证**（见 4.5） |
| G8 | **`Preference` 无法表达"已经有什么"**：偏好只表达"想要什么"，不表达已修学分 / 已修课程 | `preference.schema.json` 字段清单 | Agent / Planner | 待验证 |
| **G9** | **一个教学班可以拥有多个独立的上课时间 / 地点 segment，当前 `CourseOffering` 无法在一个对象中无损表达**：真实接口中 `CSE202` 的**每个教学班都有多个 schedule segment**（例如"1-17周 星期一 第 3-4 节 某教室" ＋ "1-17单周 星期三 第 5-6 节 某教室"），而 `CourseOffering` 只有一组 `weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom` | **真实 D5 样本 `OFFERING-001`** | Course Data / Planner | **已由真实 D5 样本验证**（见 4.5）。⚠️ **原缺口描述保留如上**（历史上 `CourseOffering` 确实无法表达多 segment）。**Data Gate-2 已按 DG-01 完成公共契约修复**：`CourseOffering` 改为 1 — N `meetings[]`（见 4.6） |
| **G10** | **D5 还有多个真实字段在现有 `CourseOffering` 中没有任何表示**：`selectedNumber`（已选人数）、`openingUnitName`（开课单位）、`courseCategoryName`（课程类别）、`examMode`（考核方式）、`readObj`（修读对象）、`teachProgressSubmitState` / `openClass`（**业务语义待确认**） | **真实 D5 样本 `OFFERING-001`** | Course Data / Planner | **已由真实 D5 样本验证**（见 4.5）。**只登记、不设计字段**；`teachProgressSubmitState` / `openClass` **不根据 0/1 值自行解释** |

> 对 G1 / G2 / G4 的补充说明：这三条说的是"**当前没有明确的跨模块公共 Schema / 正式表示**"，
> 而**不是**"一定要新增公共 Schema"。
> 它们也可能最终作为**模块内部输入**（例如培养方案解析过程中的中间结构）存在，
> 或由**数据侧转换**消化掉。具体如何处置，等真实样本到位后再判断，并由负责人决定。

### 4.2 G1 的真实材料验证（Phase 2B-0B）

**验证结论：G1 已由真实材料「部分验证」，但仍未完全解决。**

| 观察 | 真实材料证据（source_id） | 验证到什么程度 |
|---|---|---|
| 真实培养方案确实承载"培养方案级"的信息，而不只是单门课 | `CURR-OLD-001`《测绘学院-2019级遥感科学与技术专业培养方案》——含课程号 / 课程名 / 学分 / 学时 / 开课学期 / 课程性质等**成体系的课程表** | 证实"培养方案"是一份**成体系的课程集合**，而不是若干门孤立的 `Course` |
| 存在培养方案级的总量与模块口径 | `CURR-OLD-002`《遥感科学与技术专业白皮书》——学制 4 年、毕业总学分 **170**、实践实验 ≥47 学分、专业基础课 72.5 / 专业核心课 23.5 / 专业提升课 29 学分 | 证实存在**培养方案级的总学分与课程模块口径**，而当前公共 Schema 中**没有任何字段**可以承载 |

**仍然未验证、保持"待验证"的部分**：

- 这些培养方案级信息最终**是否必须进入跨模块公共契约**，还是可以作为 Curriculum 的
  **模块内部输入**存在 —— 本轮**不作判断**，也不设计字段；
- 培养方案的**版本 / 生效范围**如何表达：本轮只看到材料上标注的"年级"，
  **未看到统一的版本号机制**。

**未获真实证据、维持「待验证」的观察**：G2、G3、G4、G5、G7、G8。

> 补充：4.2 的验证依据是 2019 级方案与 2021 年白皮书，当时 D3 方向没有真实培养方案。
> **Phase 2B-0B+ 已通过认证来源取得 Case A 的两份 2025 级真实培养方案，见 4.3（更强的证据）。**

### 4.3 G1 的升级验证（Phase 2B-0B+，依据 2025 级真实样本）

**验证结论：G1 由「部分验证」升级为「已由 Case A 两份 2025 级真实培养方案确认存在」。**

| 观察 | 真实材料证据（source_id） | 验证到什么程度 |
|---|---|---|
| 存在"培养方案级"的总量与模块口径 | `CURR-OLD-003`：毕业总学分 **147.0**、实践教学学分要求 **37.1**、培养类别 公必 39 / 专必 78 / 专选 22 / 公选 8 | 培养方案级总量**确实存在**，而当前 Schema **无字段可承载** |
| 同上 | `CURR-NEW-004`：毕业总学分 **153.0**、实践教学学分要求 **38.5**、公必 39 / 专必 83 / 专选 23 / 公选 8 | 同上 |
| 存在"培养方案版本 / 适用年级"概念 | 两份文档标题分别写明"**25级**遥感科学与技术…"与"**25级**网络空间安全…" | 方案**按年级版本化**确实存在；Schema 无版本 / 年级字段 |
| 存在"课程分组 / 模块"结构 | 两份附表一均按（公共必修课）（专业必修课）（专业选修课）（荣誉课程）分区 | 分组结构确实存在；**无独立对象承载** |
| 课程表可支撑 `Course` 的核心字段 | 两份附表一合计 **128 + 138** 个课程号单元格，含课程号 / 课程名 / 学分 / 学时 / 学期 | `course_id` / `course_name` / `credit` 可 **A 直接映射**（见 3.1） |

**仍然不得自行下结论的部分**：

- **"是否必须新增公共 Schema"本轮仍不做判断** —— 上述培养方案级信息也可能最终作为
  Curriculum 的**模块内部输入**存在，或由数据侧转换消化；
- 培养方案的**版本号机制**（除标题中的"25级"外）本轮仍未见到；
- 本轮**未做任何课程等价判断**，也**未做课程差分**、**未生成 MakeupTask**。

**再次强调**：上表不构成任何字段变更建议。是否变更、如何变更，由负责人决定。

### 4.1 负责人裁决记录

**G6 — `StudentProfile`（2026-09-30 裁决）**

- `StudentProfile` **当前不是已实现、可使用的公共契约**；
- `AGENTS.md` 中的该名称视为**受公共契约规则保护的保留 / 候选概念**；
- **当前任何模块不得依赖它**（不得据此设计输入输出、不得写进实现）；
- 后续如确有必要，必须走 `【接口变更请求】`，由负责人决定是否将其正式化。

> 该裁决同步记录在 `DATA_ACQUISITION_PLAN.md` 第 7 节的 Q8。

---

### 4.4 G2 的真实数据验证（Phase 2B-0C，依据 D4 真实样本）

**验证结论：G2 已由 Case A 真实 D4 样本验证。**

| 观察 | 真实材料证据（source_id） | 验证到什么程度 |
|---|---|---|
| **学生的修读事实无法由 `Course` 完整表达** | `TRANSCRIPT-001`：`semester`（学生**实际修读**学期）与 `passed`（该次修读结果）**在 `Course` 中都没有承载位置** | 证实"某学生在某学期修了某门课、结果如何"这类**修读事实**，确实**无法只靠 `Course` 表达** |
| 另有真实字段在现有 Schema 中**完全无表示** | `TRANSCRIPT-001`：`offering_unit`（开课单位，样本含 11 个取值）、`cultivation_type`（培养类别，样本恒为"主修"） | 证实除修读事实外，还有**开课侧 / 培养语境**的信息无处承载 |
| `Course` 能承载的部分 | `course_id` / `course_name` / `credit` 为 **A 直接映射**；`course_type` 为 **B 可转换后映射**（仅表示**契约可承载该字符串值**） | `Course` 能承载的是**课程核心标识 / 基础属性**；它**覆盖不到"学生的修读事实"**（`semester` / `passed`），也**不能据此认定** `course_type` 是课程的全局固有属性 |

**本轮明确不做的判断**：

- **不自行决定新增 `CompletedCourse`（或任何）Schema** —— 本文件**只记录问题**；
- 该信息最终以何种形态存在（**Curriculum 内部模型** ／ **Integration DTO** ／ **正式公共契约**），
  由**架构负责人**决定；
- 若最终要成为正式公共契约，须走 `【接口变更请求】`。

---

### 4.5 D5 的真实数据验证（Phase 2B-0D，依据教学班侦察样本）

**验证结论：G7 / G9 / G10 已由真实 D5 样本验证**（详见 `SYSU_COURSE_OFFERING_RECON.md`）。

**样本范围**：单一课程、单一学期的**小规模人工侦察** —— `CSE202` 在 `2026-1` 返回
**2 个真实教学班**；**不含** Raw JSON、教师姓名、内部长 ID 取值、完整逐行记录。

| 观察 | 真实材料证据 | 验证到什么程度 |
|---|---|---|
| 课程 / 教学班 / 学期标识可直接对应公共字段 | `OFFERING-001` | `courseNum → course_id`、`courseName → course_name`、`classNumber → class_id`、`yearTerm → semester` 均为 **A**；**后台 `courseId` / `class_ID` 不等于**公共标识 |
| `score`（学分）是**字符串数字** | `OFFERING-001` | `credit` 需做字符串 → number 转换（**B**） |
| **`remaining_capacity` 不是接口直接提供的** | `OFFERING-001` | 它由 `limitNumber - selectedNumber` **派生**（**B**）。**不得声称学校接口直接提供剩余容量** |
| **一个教学班可有多个上课时间 / 地点 segment** | `OFFERING-001`：`CSE202` 的每个教学班都有多个 segment | **G9 成立**：当前 `CourseOffering` **无法在一个对象中无损表达** |
| `openingUnitName` / `courseCategoryName` 真实存在 | `OFFERING-001` | **G7 升级为「已由真实 D5 样本验证」** |
| 另有多个字段在现有 Schema 中无表示 | `OFFERING-001` | **G10 成立**：`selectedNumber` / `openingUnitName` / `courseCategoryName` / `examMode` / `readObj` / `teachProgressSubmitState` / `openClass` |

**⚠️ `courseCategoryName` 的语义警告**：样本中出现"**专必**"。
它与 D4 的 `course_type` 属**同一类问题** —— **带培养方案 / 上下文语义**，
**不得**自动认定为课程的**全局固有属性**（参见 §3.6 的归属分类）。

**⚠️ 语义待确认字段**：`teachProgressSubmitState`、`openClass`、`outlineTypeNum` ——
**字段存在，业务语义待确认**，**不根据 0/1 值自行解释**。

**本轮明确不做**：

- **不修改 Schema**、**不新增 `meetings[]`**、**不新增任何字段**；
- **不实现正式 parser**（周次转换只做**结构记录**）；
- **不把同一教学班拆成多个可独立选择的 `CourseOffering`**；
- **不写** crawler、**不建**数据库、**不写** Course Data Adapter；
- **不进入** Integration。

**最终表示方式（多 segment 如何建模）留给 Data Gate。**

> **Data Gate-1 引用（状态已同步）**：上述 G9 与 G10（以及 G1 / G2 / G4 等）已在
> `docs/data/DATA_GATE_DECISIONS.md` 中整理为实体边界、
> Shared / Private / Derived 分类与 **DG-01 – DG-06 接口变更请求**。
>
> **状态：Data Gate-1 架构裁决已完成；DG-01 与 DG-06 已在 Data Gate-2 实施。**
>
> ⚠️ 该文件**没有修改任何 Schema / Interface**；
> 本报告的**缺口状态与 G1–G10 历史分析不因该文件而改变**（唯一的实际契约变更见 4.6）。

---

### 4.6 G9 的契约修复（Data Gate-2，DG-01）

> **本节只记录"G9 已经被修好"这一事实与形态。§4.5 的原缺口描述与历史分析保持原样。**

| 项 | 内容 |
|---|---|
| **变更** | `schemas/course_offering.schema.json`：顶层删除 `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom`，新增 **`meetings[]`**（`type: array`，`minItems: 1`） |
| **新关系** | **`CourseOffering` 1 —— N `Meeting`**；每个 `Meeting` 必填 `weekday` / `start_section` / `end_section` / `weeks`，可选 `campus` / `classroom` |
| **顶层 `required`** | `course_id` · `course_name` · `class_id` · `semester` · **`meetings`** |
| **性质** | **有意的 breaking migration**：不保留兼容字段，旧结构被 Schema 与 Pydantic **双重拒绝** |
| **同步范围** | `mock_data/course_offerings.json`（全部教学班迁移，且至少 1 个教学班含 **2 段** meeting）、`backend/app/models/contracts.py`（新增 `Meeting`）、后端测试、`frontend` 类型与展示 |
| **明确的表达损失** | **meeting 级教师关联**仍是 **known deferred representation gap**：`teacher` 保留在教学班顶层作汇总 / 展示，`Meeting` **不含** `teacher` |
| **未新增的字段** | `selectedNumber` / `openingUnitName` / `courseCategoryName` / `examMode` / `readObj` / `teachProgressSubmitState` / `openClass` 一律**未进入**公共契约（见 §10 暂缓字段） |

**因此 G9 的状态更新为**：

> **已通过 DG-01 / Data Gate-2 完成公共契约修复。**
> （原始问题——"一个教学班无法在一个 `CourseOffering` 中表达多个时间段"——已经消除；
> 该问题的历史记录保留在 §4.5 与第 4 节观察表中。）

---

## 5. 缺口处理流程

```text
发现真实字段无法映射（A/B/C 中的 C）
        ↓
登记到本文件第 3 节的分析表（附 source_id）
        ↓
由负责人判断：
   ├─ 属于"数据侧可以转换"   → 记录转换规则，不动 Schema，交由对应模块实现
   ├─ 属于"模块内部输入"     → 不动 Schema，由该模块自行处理，不跨模块传递私有格式
   ├─ 属于"数据不应进系统"   → 记录并关闭
   └─ 确属"契约承载不了"     → 由负责人决定是否发起
                               【接口变更请求】（/AGENTS.md 第 4 节）
                                    ↓
                               人工确认后才可能修改 /schemas/
```

**Agent 不得跳过第 4 步自行改 Schema，也不得在代码里"绕过"契约另存一份私有结构后
再对外宣称符合公共契约。**

---

## 6. 本文件不做什么

- 不修改 `/schemas/`、`/docs/interfaces/`；
- 不设计新的正式公共字段；
- 不把观察当作结论；
- 不预设缺口一定要靠新增 Schema 解决；
- 不代替 Curriculum / Course Data / Planner 成员做他们模块内的数据加工设计。

---

## 7. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-30 | 建立本文件 | Phase 2B-0A 分析框架；含 8 条待验证初步观察；尚无真实样本 |
| 2026-09-30 | 第一轮 Review 修订 | ① G1 / G2 / G4 措辞由"没有承载对象"改为"当前没有明确的跨模块公共 Schema / 正式表示"，并补充"不预设一定新增 Schema，可能是模块内部输入"；② G6 记录负责人裁决（见 4.1） |
| 2026-09-30 | **Phase 2B-0B 验证** | 依据中山大学公开官方材料，**G1 更新为「已由真实材料部分验证」**（依据 `CURR-OLD-001` / `CURR-OLD-002`，见 4.2）；G2 / G3 / G4 / G5 / G7 / G8 因缺乏真实证据**维持「待验证」**；**未修改任何公共 Schema** |
| 2026-09-30 | **Phase 2B-0B+ 验证（认证来源）** | 依据 Case A 两份 **2025 级**真实培养方案（`CURR-OLD-003` / `CURR-NEW-004`，认证来源）：① **G1 升级为「已由 Case A 两份 2025 级真实培养方案确认存在」**（见 4.3）；② **§3.1 `Course` 字段映射按真实样本逐项判定 A/B/C**（A：课程号/课程名/学分；B：课程类别/推荐学期；C：学时、实验实践学时、培养方案总学分、实践教学学分、适用年级、专业、课程分组、英文名）；③ 记录**本次可检索文本中未发现**明确的先修 / 前置课程字段或条款（不构成对学校制度的结论）。**未设计新字段、未修改 Schema、未做课程等价判断** |
| 2026-09-30 | **Phase 2B-0C 验证（D4 真实样本）** | 依据 `TRANSCRIPT-001`（D4，认证来源 + 负责人私密侧脱敏，24 条、8 字段 100% 覆盖）：① 新增 **§3.6**，把 `course_id` / `course_name` / `credit` / `course_type` / `semester` / `passed` / `offering_unit` / `cultivation_type` **逐项判定 A/B/C**；② 明确 **`semester` 不得映射到 `recommended_semester`**（实际修读学期 ≠ 培养方案建议学期）、**`passed` 不得塞入 `Course`**（学生修读事实 ≠ 课程固有属性）、**`cultivation_type` 不得当成 `course_type`**；③ **G2 更新为「已由 Case A 真实 D4 样本验证」**（见 4.4）。**只记录问题，未自行决定新增任何 Schema，未修改公共 Schema，未做课程等价判断** |
| 2026-09-30 | **Reviewer 修复（`course_type` 归属 + 隐私口径）** | ① **修正 `course_type` 的语义归属**：由"课程固有属性"改为 **培养方案 / 上下文属性**，并明确"`Course.course_type` 能承载该字符串值"**不等于**"该字段归属已正确建模"。新的四类归属：**课程核心标识 / 基础属性**（`course_id` / `course_name` / `credit`）、**学生修读事实**（`semester` / `passed`）、**培养方案 / 上下文属性**（`course_type`）、**归属待确认**（`offering_unit` / `cultivation_type`）；§3.1 同步补注；② **收紧隐私口径**：不再记录 `passed` 的通过 / 未通过分布，只保留"覆盖率 24/24 + 类型 / 语义 = boolean"；`semester` 改为"覆盖两个学期"、`course_type` 只列取值种类不列数量；③ 明确 **G7 本轮不升级**（`offering_unit` 的存在**不能**证明教学班页面也提供该字段，须等 2B-0D） |
| 2026-09-30 | **Phase 2B-0D 验证（D5 真实样本）** | 依据 `OFFERING-001`（D5，认证来源，**小规模人工侦察**；`CSE202` / `2026-1` 返回 **2 个真实教学班**）：① **§3.2 `CourseOffering` 字段映射逐项判定 A/B/C** —— A：`courseNum` / `courseName` / `classNumber` / `yearTerm` / `limitNumber`；B：`score` → `credit`（字符串数字转换）、`remaining_capacity` 为 `limitNumber - selectedNumber` 的**派生值**；C：`selectedNumber` / `openingUnitName` / `courseCategoryName` / `examMode` / `readObj` / `teachProgressSubmitState` / `openClass`；② **新增 G9**：一个教学班可有**多个上课时间 / 地点 segment**，当前 `CourseOffering` **无法在一个对象中无损表达**；③ **新增 G10**：D5 另有多个真实字段在现有 Schema 中无表示；④ **G7 升级为「已由真实 D5 样本验证」**（2B-0C 预留的"须等 2B-0D"条件已满足）。**未修改 Schema、未新增 `meetings[]`、未实现 parser、未写 crawler / DB / Adapter、未进入 Integration**。⚠️ **不得声称学校接口直接提供 `remaining_capacity`**；⚠️ `courseCategoryName`（样本为"专必"）**带培养方案边界上下文，不得认定为课程全局固有属性** |
| 2026-09-30 | **Data Gate-1 引用（不改缺口状态）** | 新增 `docs/data/DATA_GATE_DECISIONS.md`（当时为**草案，未经批准**），把 G1 / G2 / G4 / G9 / G10 等整理为实体边界、Shared / Private / Derived 分类与 **DG-01 – DG-06 接口变更请求草案**；并在 §4.5 末尾加入 Data Gate 引用。**本报告的缺口状态与 A/B/C 映射结论一律不变**；**未修改 Schema / Interface / 代码**，**未调用 SYSU 接口**，当时**未做任何裁决** |
| 2026-09-30 | **Data Gate-1 状态同步（Reviewer 认可后）** | 仅同步 **Data Gate 状态措辞**（§4.5 引用块 + 本表）：`DATA_GATE_DECISIONS.md` 的标注由"**草案，未经批准**"改为 **「Data Gate-1 架构裁决已完成；公共契约尚未实施，实施进入 Data Gate-2」**。**只同步状态**：**G1–G10 的历史分析与 A/B/C 映射结论一字未改**；**未修改 Schema / Interface / 代码**，**未调用 SYSU 接口**，**未进入 Data Gate-2** |
| 2026-09-30 | **Data Gate-2：G9 契约修复（DG-01 / DG-06 实施）** | ① **G9 更新为「已通过 DG-01 / Data Gate-2 完成公共契约修复」**：`schemas/course_offering.schema.json` 顶层删除 `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom`，改为 **`meetings[]`（`minItems: 1`）**，即 **`CourseOffering` 1 —— N `Meeting`**，顶层 `required` = `course_id` / `course_name` / `class_id` / `semester` / `meetings`；② **新增 §4.6** 记录修复形态与同步范围（Mock 全量迁移且 ≥1 个教学班含 2 段、后端新增 `Meeting` 模型、前端类型与展示同步）；③ **§3.2 补注「Data Gate-1 当时的字段 / Data Gate-2 之后的字段」并在历史分析表上方标明时点**；④ **历史一律保留**：原缺口描述"一个教学班无法在一个 `CourseOffering` 中表达多个时间段"**未删除**，只在原处加注"已修复并指向 §4.6"；⑤ **未新增任何暂缓字段**（`selectedNumber` / `openingUnitName` / `courseCategoryName` / `examMode` / `readObj` / `teachProgressSubmitState` / `openClass` 仍不进公共契约）；⑥ **meeting 级教师关联仍为 known deferred representation gap**。⚠️ **未调用 SYSU 接口、未写 crawler / Adapter / Provider、未进入 Integration、未建数据库** |
