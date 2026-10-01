# 成员数据交接说明（Data Handoff）

> **状态：交接规则 + 当前清单 + 清单模板。**
>
> ⚠️ **「已有真实证据」≠「已经向组员交付了真实逐行数据」。**
> 截至本文件更新：D1–D5 的**汇总事实已进入 public 仓库**（可直接共享），
> 但**逐行真实数据的交接次数仍为 0**（见第 11 节）。
>
> **本文件最重要的两条规则：**
> ## 1. 不得把 Raw 个人数据直接交给其他成员。
> ## 2. 当前 GitHub 仓库是 public 仓库，真实个人数据（含脱敏样本）一律不得进入。
>
> 所有跨成员的真实数据交付，都必须经过**脱敏**、**由负责人执行或批准**、
> 并**在 `DATA_SOURCE_REGISTRY.md` 中有对应登记**，且通过**非公开位置**进行。

---

## 1. 目的

真实数据一旦进入协作流程，风险就不再是"某个人拿到了什么"，而是"**谁在什么时候把什么交给了谁**"。
本文件把这件事写清楚，避免出现：

- 直接把未脱敏成绩单发到群里；
- 把脱敏样本顺手提交进 public 仓库；
- 用真实数据覆盖 `/mock_data/`；
- 下游成员拿到的数据说不清来源，最后被当成"真实结论"写进产品。

---

## 2. 当前数据清单：可直接共享 / 按需交接 / 禁止交接

> 本节回答一个此前不清晰的问题：**现在到底有什么、能怎么给。**
> 分类口径与 `DATA_GATE_DECISIONS.md` 第 5 节（Shared / Private / Derived）一致。
>
> ⚠️ **关键区分：**「**已有真实证据**」记录的是"**我们确认了什么事实**"；
> 「**交付真实数据**」指"**把逐行数据交给某个成员**"。**两者不是一回事。**

### 2.1 GitHub public 仓库可直接共享（无需额外交接）

以下内容**已经在 public 仓库中**，且**本身不含逐行真实数据 / 个人信息 / Raw 材料**，
任何成员**可以直接读取**：

| 内容 | 位置 | 说明 |
|---|---|---|
| **D1 公开政策证据** | `docs/data/SYSU_CASE_A_PUBLIC_EVIDENCE.md` | 公开官方来源与条款摘录 |
| **D2 / D3 培养方案证据** | `docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md` | 认证来源的**汇总事实**（总学分、实践学分、课程号单元格数等） |
| **D4 已修课程证据** | `docs/data/SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md` | 字段名、覆盖率、归属判定；**不含逐行记录** |
| **D5 教学班侦察证据** | `docs/data/SYSU_COURSE_OFFERING_RECON.md` | 字段名、语义、映射结论、汇总事实；**不含 Raw JSON** |
| **来源登记** | `docs/data/DATA_SOURCE_REGISTRY.md` | `source_id` / 证据等级 / 访问类型 |
| **缺口登记** | `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` | G1–G10 与 A/B/C 映射结论 |
| **Data Gate 决策草案** | `docs/data/DATA_GATE_DECISIONS.md` | 实体边界、所有权、DG-01 – DG-06 草案 |
| **Mock 数据** | `/mock_data/` | **人工虚构**、面向全项目共享的演示数据 |
| **公共契约** | `/schemas/`、`/docs/interfaces/` | 与数据共享无关，列出以便成员定位 |

**共享的前提**：这些文件记录的是"**结论与来源性质**"，**不是数据本身**。
仓库内**不含**完整课程表、不含任何具体成绩 / GPA、不含教师姓名、不含内部长 ID 取值、
不含完整教学班逐行记录。

> ⚠️ **认证来源（Authenticated Official）限制**：`CURR-OLD-003` / `CURR-NEW-004` /
> `TRANSCRIPT-001` / `OFFERING-001` 均为**认证来源**，
> **外部访问者无法通过公开 URL 独立复核**。共享这些**结论**时，必须同时说明这一限制，
> 不得让接收方误以为可以自行公开验证。

### 2.2 负责人控制的非公开位置，按需交接

以下数据**可以**交付给确实需要的成员，但必须满足第 9 节的 Checklist，
并**通过负责人控制的非公开位置**交付，**一律不得进入 public 仓库**：

| 数据 | 层级 | 交付形态与限制 |
|---|---|---|
| **D4 Sanitized Sample**（已修课程脱敏**逐行**记录） | Sanitized Sample | 仅课程号 / 课程名 / 学分 / 修读学期 / 是否通过 / 必要课程性质；**必须先脱敏**并经负责人确认标准；**仅可用于 Schema 承载能力与 Curriculum 逻辑验证，不得对外展示**。<br>✅ **DG-02 裁决：可以由负责人通过非公开位置交给 Curriculum 成员**（`CompletedCourse` 作为 **Curriculum 内部规范化对象**，不进公共契约） |
| **后续 D5 normalized / sanitized sample** | Sanitized Sample | **DG-01 已裁决**为 `CourseOffering` 1 — N `Meeting`（嵌套 `meetings[]`）；**交付形态待 Data Gate-2 实施契约变更后再确定**，否则下游会各自发挥 |
| **培养方案结构化输出** | Sanitized Sample 或**模块内部输入** | **DG-04 裁决：MVP 作为 Curriculum 内部模型**（不新增公共 Schema）；由负责人决定交付形态与方式；⚠️ **不得**被当作跨模块公共契约使用 |

> ⚠️ **截至本文件更新，上述逐行样本的交接次数仍为 `0`。**
> 已有的是"**汇总事实**"（在 public 仓库），**不是"已交付的逐行数据"**。
> ⚠️ **"裁决允许按需交付" ≠ "已经交付"** —— DG-02 只是**打开了交付通道**，
> 是否交付、何时交付仍由负责人决定，并须走第 9 节 Checklist。

### 2.3 禁止交接（任何情况下都不得交付）

| 类别 | 具体内容 |
|---|---|
| **Raw 个人数据** | **Raw transcript**（原始成绩单）、**Raw D5 response**（原始教学班 JSON 响应） |
| **凭据类** | **password**、**Cookie**、**Session**、**Token**、API Key、验证码 |
| **流量记录** | **HAR**、完整 Request Headers |
| **他人数据** | 其他学生的成绩单、选课名单、任何非本人授权的数据 |
| **未脱敏内容** | 姓名、学号、身份证、联系方式等直接身份标识 |
| **内部标识取值** | `courseId` / `class_ID` / `timePlaceId` 等后台内部长 ID 的**取值** |
| **受限文本** | 教师姓名、`readObj`（修读对象）**完整文本**、`teachingTimePlaceStr` 原始串 |

**一句话原则**：**不确定时一律按"不可交付"处理，先问负责人。**

---

## 3. 三层数据与交接原则

数据分层定义见 `DATA_ACQUISITION_PLAN.md` 第 5.1 节（Raw → Sanitized Sample → Mock）。
就"交接"而言，规则是：

| 层级 | 能否跨成员交付 | 条件 |
|---|---|---|
| **Raw**（原始） | **禁止** | 只保存在负责人控制的受控位置；任何情况下不得直接交给其他成员 |
| **Sanitized Sample**（脱敏样本） | **可以**，但需批准且**不得入库** | ① 已完成脱敏且符合负责人确认的标准；② 由负责人执行或批准交付；③ 已在数据源登记表登记；④ **通过负责人控制的非公开位置交付，不得进入当前 public GitHub 仓库** |
| **Mock**（`/mock_data/`） | 可以 | 本来就是人工虚构、面向全项目共享；**但不得被真实数据覆盖**，也不得被冒充为真实数据 |

**补充规则**：

- 交接必须**可追溯**：接收方要能说出"这份数据来自哪个 `source_id`"；
- 交接必须**说明限制**：例如"仅可用于验证 Schema 承载能力，不得对外展示"；
- **脱敏不等于可以公开**：成绩单类数据即使去掉姓名学号仍属敏感，
  因此在 public 仓库中**同样不得存在**；
- 不确定时一律按"不可交付"处理，先问负责人。

---

## 4. Curriculum 成员将来需要的数据

| 编号 | 数据 | 对应规划编号 | 交付形态 | 前置条件 |
|---|---|---|---|---|
| C-1 | **原专业培养方案** | D2 | 脱敏后的文件或结构化 `Course` 列表 | 负责人指定 Demo 专业与年级 / 培养版本；来源已登记；确认可交付形态 |
| C-2 | **新专业培养方案** | D3 | 同上 | 必须与 C-1 属**同一转专业案例的适用专业与培养版本** |
| C-3 | **脱敏已修课程记录** | D4 | Sanitized Sample：**仅**课程号 / 课程名 / 学分 / 修读学期 / 是否通过 / 必要课程性质 | **必须先脱敏**并通过负责人确认的标准；**通过非公开位置交付，不得入库** |
| C-4 | **正式补修 / 课程认定规则** | D1 | 政策文件的出处 + 条款摘录 | 负责人确认可引用的文件清单；**不得把解读当作正式规则** |

**交付时必须同时说明**：

- 哪些字段是原始数据里的、哪些是成员自己补充的；
- 哪些结论属于"确定规则"，哪些属于"待人工确认"；
- 数据适用的学年、专业与培养版本范围。

---

## 5. Planner 成员将来需要的数据

| 编号 | 数据 | 对应规划编号 | 交付形态 | 前置条件 |
|---|---|---|---|---|
| P-1 | **CourseOffering 脱敏真实样本** | D5 | Sanitized Sample（符合 `course_offering.schema.json`） | 已完成页面技术侦察；采集范围经负责人批准；**Raw 按潜在含个人信息处理并已实际检查**；当前**不得进入 public Git**；⚠️ **多 segment 表示方式需先按 `DATA_GATE_DECISIONS.md` DG-01 裁决** |
| P-2 | **Curriculum 最终输出的正式结构化结果** | D2+D3+D4 的产出 | `MakeupTask[]`（符合 `makeup_task.schema.json`） | Curriculum 侧已确认输出稳定；确认哪些条目是 `manual_confirmation` |
| P-3 | **Preference 样本** | 用户需求 | 符合 `preference.schema.json` 的对象 | 来自真实问卷 / 访谈 / 负责人确认，**不得由 Agent 编造** |

**交付时必须同时说明**：

- 优先级结论**来自 Curriculum**，Planner 不得为求解方便自行重写课程认定或学业优先级规则
  （`/AGENTS.md` 第 5 节）；
- 哪些 `MakeupTask` 是 `manual_confirmation` / `possibly_equivalent` 一类需要人工确认的条目，
  在确认前不得直接参与求解。

---

## 6. Curriculum → Planner 的边界与当前缺口

这一节专门说明"目前能交什么、不能交什么"，避免下游成员去猜或自己造格式。

### 6.1 现在就可以交付的

- **`MakeupTask[]` 是当前已存在的稳定公共对象**（`schemas/makeup_task.schema.json`），
  Curriculum 产出后可以直接交付给 Planner 使用。

### 6.2 目前没有正式表示的

- `/AGENTS.md` 第 5 节要求 **Planner 消费 Curriculum 提供的"课程依赖结果"与"已确认优先级"**；
- 但这两者**没有正式的公共 Schema**（`/schemas/` 下没有对应文件），
  在 `docs/interfaces/planner.md` 中它们也只以"来自 Curriculum"的方式被提及。
- ⚠️ 另外，`docs/interfaces/planner.md` 目前把"课程依赖图 / 补修优先级与风险"写成
  **Planner 自己的职责**，**与 `/AGENTS.md` 第 5 节冲突** ——
  该**接口文档债务**已登记为 **DG-06**，**裁决结果：APPROVED**，
  由 **Data Gate-2 修正** `planner.md`（必要时同步 `curriculum.md`）。
- **DG-05 裁决（NO NEW PUBLIC CONTRACT FOR MVP）**：
  - ⛔ **不新增** `DependencyGraph` Schema、**不新增** `priority` 字段、**不新增** `PriorityResult`；
  - 依赖方面：`MakeupTask.prerequisites[]` **已存在且承认为 MVP 依据**
    （见 `DATA_GATE_DECISIONS.md` §7.3 / §7.3.1）；
  - ✅ **Curriculum 负责认定 / 产出 dependency edges**；
    **Planner 只能把已经收到的 `prerequisites[]` 转成求解所需的本地 adjacency / topology**，
    ⛔ **不得新增、猜测、重写任何 prerequisite edge**；
  - ⛔ **没有正式 priority 数据时，Planner 不得自行生成优先级**。

### 6.3 因此当前的硬性约束

- 依赖与优先级**仍不作为独立公共对象交付**（裁决明确不新增）；
  Planner 只消费 `MakeupTask[]` 中**已经存在**的字段；
- **任何成员都不得自行设计私有的跨模块格式**（例如在代码里定义一套只有两边懂的中间结构，
  再私下传递）——那等于绕过公共契约；
- 处理方式：该缺口已登记在 `REAL_TO_SCHEMA_GAP_REPORT.md`，
  裁决记录见 `DATA_GATE_DECISIONS.md`；
  如后续确需成为正式契约（例如 Curriculum 真正实现明确的优先级规则），
  由负责人决定是否发起新的 `【接口变更请求】`；
- **Planner 只能依赖 `MakeupTask[]` 中已存在的字段**，
  不得依赖任何未定义的私有结构。

---

## 7. 数据生产方（供交接方向参考）

为避免"谁给谁"说不清，明确各数据的**产出方**：

| 数据 | 产出 / 提供方 | 消费方 |
|---|---|---|
| D1 政策 | 负责人 / 用户（人工获取） | Curriculum、QA |
| D2 / D3 培养方案 | 负责人 / 用户（人工获取） | Curriculum |
| D4 已修课程 | 学生本人提供 → 负责人脱敏（非公开位置） | Curriculum |
| D5 教学班数据 | **Course Data 成员**（在负责人批准的范围内采集） | Planner、Agent/Frontend |
| `MakeupTask[]` | **Curriculum 成员** | Planner、Agent/Frontend |
| `Preference` | Agent / 负责人（用户真实需求） | Planner |
| `PlanResult` | **Planner 成员** | Agent/Frontend |

> 实体级所有者与 Shared / Private / Derived 分类见 `DATA_GATE_DECISIONS.md` 第 4、5 节。

---

## 8. 交接清单模板

每次真实数据交付，按下表填写（交接记录保存在负责人处，**不进入仓库**）：

```text
【数据交接记录】
交接日期：
交接人 / 接收人：
source_id（对应 DATA_SOURCE_REGISTRY）：
数据类别（D1–D5）：
数据层级：Raw / Sanitized Sample / Mock
内容说明（含字段范围）：
脱敏方式与确认人：
交付位置（非公开位置，不得是 public 仓库）：
适用范围（学年 / 专业 / 培养版本 / 案例）：
使用限制（例如：仅用于 Schema 承载能力验证，不得对外展示）：
接收方确认：
```

---

## 9. 交接前置条件（Checklist）

交付**之前**逐条确认，任一条不满足则不得交付：

- [ ] 数据已在 `DATA_SOURCE_REGISTRY.md` 登记，`source_id` 明确
- [ ] 属于 Sanitized Sample 或 Mock（**不是 Raw**）
- [ ] 已去除姓名、学号、身份证、联系方式等直接身份标识
- [ ] D4 类数据已按第一版范围收窄（不含具体成绩 / GPA / 排名）
- [ ] 不含密码 / Cookie / Session / Token
- [ ] 不含他人数据（例如其他学生的选课名单）
- [ ] **确认不会进入 public 仓库**，交付走的是负责人控制的非公开位置
- [ ] 负责人已批准本次交付
- [ ] 已写明使用限制与适用范围
- [ ] 接收方已知悉"不得把数据再转交给第三方"

---

## 10. 禁止事项

对**所有成员**一律适用（与 `/AGENTS.md` 第 7、8、11、18 节及 `/docs/SECURITY.md` 一致）：

- 把 Raw 个人数据直接交给其他成员；
- 把真实数据（含脱敏样本）提交进 **public** 仓库；
- 自行设计私有的跨模块数据格式来绕过公共契约；
- 用真实数据覆盖 `/mock_data/`；
- 把 Mock 数据说成真实数据，或把真实数据说成 Mock；
- 把推测、猜测写成学校正式政策；
- 保存密码、Cookie、Session、Token；
- 绕过登录、破解验证码、越权获取、高频批量请求。

发现无法判断的情况，**先停下问负责人**，不要"先做了再说"。

---

## 11. 当前状态

```text
已发生的真实数据交接：0
已取得真实证据的数据类别：D1 / D2 / D3 / D4 / D5
已在 public 仓库可直接共享：
  - D1–D5 Evidence 汇总（SYSU_CASE_A_* 与 SYSU_COURSE_OFFERING_RECON）
  - DATA_SOURCE_REGISTRY.md
  - REAL_TO_SCHEMA_GAP_REPORT.md
  - DATA_GATE_DECISIONS.md
  - /mock_data/（人工虚构）
已向组员交付的逐行真实数据：无
  - D4 Sanitized Sample：DG-02 已裁决允许由负责人经非公开位置交 Curriculum；
    实际交付仍待负责人决定（交接次数 0）
  - D5 normalized / sanitized sample：DG-01 已裁决为 CourseOffering 1—N Meeting，
    交付形态待 Data Gate-2 实施契约后确定（交接次数 0）
  - 培养方案结构化输出：DG-04 裁决为 Curriculum 内部模型，不进公共契约
已交付 Curriculum 的真实数据：无
已交付 Planner 的真实数据：无
Data Gate-1 架构裁决：DG-01 – DG-06 已全部裁决；公共契约尚未实施
最近更新：2026-09-30（Data Gate-1 架构裁决落档：同步 DG-02 / DG-03 / DG-04 / DG-05
          对交接的影响；明确「裁决允许按需交付」≠「已经交付」，交接次数仍为 0）
```

> Phase 2B-0A 只做规划，**不获取、不交接任何真实数据**；
> Phase 2B-0B – 2B-0D 取得的真实材料**只产出汇总事实与结论**，
> **逐行数据一律不进入 public 仓库**。
