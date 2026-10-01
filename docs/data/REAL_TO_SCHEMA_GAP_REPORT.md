# 真实数据 → 公共 Schema 承载能力分析（框架）

> **状态：分析框架。** 目前**尚未获得任何真实样本**，因此本文件只有框架、字段清单与"待验证的初步观察"。
>
> ## 红线（本文件最重要的两条）
>
> 1. **真实字段无法映射时，只记录潜在缺口，不修改公共 Schema。**
> 2. **禁止在本文件中自行设计新的正式公共字段。** 任何新增 / 修改 / 删除公共字段的提议，
>    都必须走 `/AGENTS.md` 第 4 节的 `【接口变更请求】`，并由负责人确认后才可能实施。
>
> 本文件的产物是"**问题清单**"，不是"字段方案"。

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
     C 无法映射 / 无承载对象 —— 现有 Schema 中找不到对应位置
        ↓
④ 登记：A / B 记录转换规则；C 只登记为"潜在缺口"，附真实样本出处
```

**登记要求**：

- 每条缺口必须附**样本出处**（`source_id`，见 `DATA_SOURCE_REGISTRY.md`），不允许凭印象登记；
- 只描述"**缺什么**"，不描述"**应该加什么字段**"；
- 若某条缺口可能影响多个模块，在"影响模块"列写全。

---

## 3. 逐 Schema 分析框架

> 下表的"真实字段"列在拿到样本前保持「待填写」。字段清单来自 `/schemas/*.schema.json` 的**现状**，如有变更以文件为准。

### 3.1 `course.schema.json`（Course）

**当前字段**：`course_id`(必填) · `course_name`(必填) · `credit`(必填) ·
`course_type?` · `recommended_semester?` · `prerequisites[]?` · `source?`
（`additionalProperties: false`）

| 真实字段（待填写） | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | Curriculum | 待填写 | |

### 3.2 `course_offering.schema.json`（CourseOffering）

**当前字段**：`course_id` · `course_name` · `class_id` · `semester` · `teacher?` · `credit?` ·
`weekday` · `start_section` · `end_section` · `weeks[]` · `campus?` · `classroom?` ·
`capacity?` · `remaining_capacity?` · `source?` · `data_source`（全部必填项见 Schema）

| 真实字段（待填写） | 映射结论 A/B/C | 目标 Schema 字段 | 潜在缺口（只描述缺什么） | 影响模块 | 样本出处 | 备注 |
|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | Course Data / Planner | 待填写 | |

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

---

## 4. 待验证的初步观察（**仅记录，未经真实样本验证**）

> ⚠️ 以下是在**通读现有 Schema 与接口文档**后发现的"可能承载不了"的地方。
> **它们不是结论**：必须等真实样本到位后逐条验证。
> 本节**只描述缺口，不提出字段设计**。

| 编号 | 观察 | 依据 | 影响模块 | 状态 |
|---|---|---|---|---|
| G1 | **培养方案本身没有承载对象**：现有 Schema 只能表达单门 `Course`，没有"培养方案版本 / 适用专业 / 适用年级 / 学分结构 / 课程分组（必修·选修·通识）"的对象或字段 | `course.schema.json` 字段清单 | Curriculum | 待验证 |
| G2 | **已修课程 / 成绩没有承载对象**：Curriculum 要把"已修课程记录"变成 `MakeupTask`，但 `/schemas/` 下没有成绩单或"已完成课程"的对象；`Course` 也无法表达成绩、修读学期、是否通过 | `/schemas/` 目录清单 + `docs/interfaces/curriculum.md` 的输入描述 | Curriculum | 待验证 |
| G3 | **学分差额没有结构化表达**：现有 Mock 的 `MakeupTask.reason` 文本里出现"原 3 学分 / 新 2 学分"，但 Schema 中没有可承载"学分差额"的位置 | `mock_data/makeup_tasks.json` 62003007 + `makeup_task.schema.json` | Curriculum / Agent | 待验证 |
| G4 | **没有"当前课表"对象**：`docs/interfaces/planner.md` 把"当前课表"列为 Planner 的输入，但 `/schemas/` 下没有对应文件；`CourseOffering` 表示"学校开设什么"，不等于"学生已选什么" | `docs/interfaces/planner.md` 对外输入 | Planner | 待验证 |
| G5 | **`PlanResult` 没有冲突对象**：冲突只能从 `changes[].reason` 的文本读出，无法计数或分类 | `plan_result.schema.json` 字段清单 | Planner / Agent | 待验证 |
| G6 | **`AGENTS.md` 第 4 节把 `StudentProfile` 列为公共契约，但 `/schemas/` 下没有 `student_profile.schema.json`** | `AGENTS.md` 第 4 节 vs `/schemas/` 目录 | 全部 | **需负责人确认是"待建契约"还是笔误** |
| G7 | **`CourseOffering` 没有课程类别 / 开课学院**：`course_type` 只存在于 `Course`，教学班级别没有 | 两个 Schema 字段对比 | Course Data / Planner | 待验证 |
| G8 | **`Preference` 无法表达"已经有什么"**：偏好只表达"想要什么"，不表达已修学分 / 已修课程 | `preference.schema.json` 字段清单 | Agent / Planner | 待验证 |

**再次强调**：上表不构成任何字段变更建议。是否变更、如何变更，由负责人决定。

---

## 5. 缺口处理流程

```text
发现真实字段无法映射（A/B/C 中的 C）
        ↓
登记到本文件第 3 节的分析表（附 source_id）
        ↓
由负责人判断：
   ├─ 属于"数据侧可以转换"  → 记录转换规则，不动 Schema，交由对应模块实现
   ├─ 属于"数据不应进系统"  → 记录并关闭
   └─ 确属"契约承载不了"    → 由负责人决定是否发起
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
- 不代替 Curriculum / Course Data / Planner 成员做他们模块内的数据加工设计。

---

## 7. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-30 | 建立本文件 | Phase 2B-0A 分析框架；含 8 条待验证初步观察；尚无真实样本 |
