# Agent / Frontend 当前状态

> 最后更新：2026-10-08（**Final Upgrade · Agent B：有依据的规则解释 + 最小 UI 已实现，待负责人验收**：
> 新增**只读解释服务** `backend/app/explanation/` 与**新增私有接口**
> `POST /api/v1/explanation/plan`：逐条解释已有 `PlanResult`（补修判定 / 教学班安排 / 调班原因 /
> 风险 / 未决事项 / 整体状态），每条都绑定**真实来源字段**并区分
> 「确证规则 / 学生输入或假设 / 系统建议 / 未知 / 上下文不存在」，同时列出**待人工确认**事项；
> 未配置模型时为**确定性规则模板**并明确标注 `rule_based_template`（⛔ 不声称是 AI 生成）；
> 可选模型适配层需**显式注入**，输出必须通过事实绑定校验（含数字与课程号），
> 否则降级为模板并如实记录原因（`model_unavailable_fell_back_to_template`）。
> 前端新增「查看依据 / 为什么这样安排」入口与解释面板：**只展示、不重算**，
> 未启用 / 请求失败 / 无条目 / 上下文缺失都有清楚反馈；
> ⛔ 未改 Planner / Curriculum / 计算逻辑、⛔ 未改 `/schemas/`、⛔ 未改 `docs/interfaces/`、
> ⛔ 未改任何既有 API 路径与 Provider 签名、⛔ 不引用 Mock 回放通道（有测试锁定）。
> 数据状态：解释只消费**已有**的 Mock 演示数据；**仍未有真实数据链路端到端跑通**。
> 详见 `docs/worklogs/agent_frontend.md` 与 `AGENT_B_REPORT.md`）
>
> 最后更新：2026-10-05（**Frontend Real E2E Wiring Preparation 已实现，待 Architecture Review**：
> 已把 Real Planning 的失败状态**产品化**（503 `real_pipeline_not_configured` 明确显示为
> "**真实规划运行时尚未完成装配**"，**不是**笼统的"请求失败"，且**不 fallback 到 Mock**）；
> 422 / 500 / network 分别有独立文案；`PlanApiError` 携带 `kind` / `status` / `code` / `detail`；
> 新增**仅开发环境**的 E2E 联调调试信息面板（只有计数 / 枚举 / 状态，不含成绩·姓名·学号·GPA·凭据）；
> ⛔ 未改 backend / Schema / Interface；⛔ 未做 runtime / provider wiring。
> **Frontend 已准备好 Real E2E 联调；Real E2E 尚未完成**（需 Codex runtime 真正可用并联调通过）。
> 上一轮：Frontend User Input Gate Phase 1 已实现并 merge）
> 前端新增真正的**用户输入区**（目标学期 / 转专业上下文 / 当前课表 / 可编辑 Preference / 成绩文件选择），
> 并按 DG-03 语义输出 `current_schedule: CourseOffering[]`；
> **Mock / Real 明确隔离**：页面显示**规划结果来源**（局部 provenance，非"整页数据模式"），Real Planning 在接口就绪前按钮 **disabled**，
> **绝不**回退到 Mock；`POST /api/v1/plan` client 已预留且请求体只有
> `semester` / `current_schedule` / `preference`；
> ⛔ **未改 backend / Schema / Interface**；⛔ XLSX **只选择不解析**、前端**不生成**任何 `MakeupTask`。
> 上一轮：DG-07D Frontend Presentation Safety 已 IMPLEMENTED / REVIEWED 并 merge 到 main）
> 通用 UI 与 Demo 体验 Polish 保留；empty-meeting 中性展示“当前数据中无排课信息”已实施；
> unresolved 展示覆盖 manual_confirmation / missing_data / schedule_unknown / selection_required 及通用未知 fallback；
> 已删除前端自行推断的容量阈值、Preference 执行语义、risks=[] / changes=[] / feasible 过度结论；
> **DG-07A / B / C / D 均已 IMPLEMENTED / REVIEWED，Data Gate 已恢复 PASSED / CLOSED**；
> 公共 Schema / Interface / Provider 签名未被 DG-07D 私自修改）
> 数据状态：**核心业务数据仍全部为 Mock**；真实证据（D1–D5）只以**汇总事实**形式入仓，
> **原始材料、逐行记录、Raw 响应、私密脱敏样本、截图与真实 Capture Bundle 均不进入 public Git**
> 契约状态：**`CourseOffering.meetings` = `type: array`、`minItems: 0`**（DG-07A；
> 顶层 `required` 仍含 `meetings`，缺字段 / `null` 非法）；
> **DG-01 时的 `minItems: 1` 已是历史**；**Data Gate 通过条件 C1–C11 全部完成**
> ✅ **DG-07 empty-meeting rollout safety gate 已解除**：`meetings = []` 契约合法，
> Course Data / Planner / Frontend 的安全处理均已实施并 Review。
> ⚠️ 真实产品 E2E 仍需 complete semester snapshot 与真实 Provider / Integration；
> partial snapshot 仍不得进入产品链路，`mock_data/` 仍保持永久 Mock 通道原有样本。
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
> （学校侧业务原因仍未知；DG-07A / B / C / D 已全部实施并 Review）；
> **production Curriculum / Planner provider 仍未接入**，
> 因此**没有**任何一条真实数据链路端到端跑通，**也未新增任何 API**。
>
> ⚠️ **导航纠错**：「**选课**」与「**全校开设课程**」是**两个独立模块**。
>
> 详见 `docs/status/course_data.md`。

## 当前阶段

**DG-07D 已 IMPLEMENTED / REVIEWED / MERGED
→ 下一步：进入真实数据与 Integration 联调准备，不再等待 DG-07 实施**

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
                   →  ✅  DG-07A — Contract Migration IMPLEMENTED / REVIEWED
                      meetings minItems 1 → 0（required 不变）；接口语义 + 契约级测试已同步
                   →  ✅  DG-07B — Course Data Empty-Meeting Normalization IMPLEMENTED / REVIEWED
                   →  ✅  DG-07C — Planner Unknown-Schedule Safety IMPLEMENTED / REVIEWED
                   →  ✅  DG-07D — Frontend Presentation Safety IMPLEMENTED / REVIEWED / MERGED
                   →  ✅  DG-07 overall — IMPLEMENTED / REVIEWED
                   →  ✅  Data Gate — PASSED / CLOSED
                   →  之后：完整真实 snapshot → Phase 2B Integration 接真实 Provider → Case A E2E
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

## Frontend User Input Gate Phase 1 结果（用户输入区 + Real API 预留）

**只做前端输入体验，不伪造后端能力**：⛔ 不改 backend；⛔ 不解析 XLSX；
⛔ 不生成 `MakeupTask`；⛔ 不做冲突 / feasible / Path Repair 计算。

分支 `feature/frontend-user-input-gate`，base = `main = 1a740b2d960bb4bb78771d56aa1ec9f0424a12e1`。

| 产出 | 内容 |
|---|---|
| `frontend/src/components/UserInputPanel.vue` | 输入区容器，按产品顺序组织 ① 学生信息 ② 已修课程文件 ③ 当前课表 ④ 个性化偏好 ⑤ 生成规划 |
| `frontend/src/components/StudentContextForm.vue` | 目标学期 `semester` + 转专业上下文（原专业 / 目标专业 / 转入学期） |
| `frontend/src/components/PreferenceForm.vue` | **可编辑** Preference（与只读的 `PreferencePanel.vue` 分工，后者未修改） |
| `frontend/src/components/CurrentScheduleInput.vue` | 从已加载教学班勾选"当前已选"，输出 `CourseOffering[]` |
| `frontend/src/components/SubmissionActions.vue` | 规划结果来源显示 + Real Planning 提交（接口就绪前 **disabled**） |
| `frontend/src/state/userInput.ts` | **纯逻辑层**：字段规则 / 序列化 / 校验 / 请求组装（无 Vue、无 DOM、无网络） |
| `frontend/src/api/plan.ts` | Real client：`POST /api/v1/plan`，**不 fallback 到 Mock** |
| `frontend/src/config.ts` | 新增 `PLAN_ENDPOINT` / `PLAN_API_ENABLED` / Case context / `MAJOR_OPTIONS` 选项层 / `PlanResultSource` |
| `frontend/vitest.config.ts`、`frontend/tests/*.spec.ts` | 新增前端单元与交互测试（Vitest + @vue/test-utils + jsdom） |

**关键边界（已落地并有测试锁定）**：

- **专业信息只作为选项层**：专业名来自 `MAJOR_OPTIONS`（`datalist` 候选 + 允许自由填写），
  ⛔ **不存在** `if (major === '网络空间安全')` 这类按专业名分叉的代码；
  Case A（遥感科学与技术 → 网络空间安全、转入学期 2026-1）只作**默认 Case context**，
  页面明确标注这些信息**尚未影响后端 Planner**；
- **不写死学生身份**：⛔ 不含姓名 / 学号 / 成绩 / 课程认定结果；
  `buildRealPlanRequest()` 的序列化断言请求体中**不出现**专业名；
- **Preference 严格对齐公共 Schema**：只编辑 `max_credit` / `avoid_cross_campus` /
  `preferred_courses` / `avoid_times` / `notes`，**不新增字段**；
  空备注归一为 `null`，非法学分上限**不猜测**（按"未设定"处理）；
  `avoid_times[]` 序列化时丢掉前端 `key`，只保留三个公共字段；
- **`current_schedule` 严格是 `CourseOffering[]`**：只接受**来源列表内**的教学班（fail closed），
  原样传递来源对象、不加工；**允许为空**；⛔ 不用 `avoid_times` 冒充当前课表（DG-03）；
  对 `meetings = []` 的教学班沿用 DG-07D 中性文案，不推断无冲突；
- **XLSX 只选择不解析**：`<input type="file" accept=".xlsx">`，只保存 `File` 对象与文件名，
  ⛔ 不上传、不解析、不伪造分析结果；非 `.xlsx` 一律拒绝；
  页面**必须**显示"成绩文件上传分析将在真实 Curriculum User Input API 接入后启用"，
  并声明本页**不会**在前端生成任何补修任务（有测试断言选择文件后 `fetch` **零调用**）；
- **Mock / Real 明确隔离**：页面显示"**规划结果来源：Mock / Real**"（**局部** provenance，不是整页数据模式）；
  `VITE_PLAN_API_ENABLED !== 'true'` 时 Real Planning 按钮 **disabled**；
  ⛔ 不在失败时回退到 `/api/v1/mock/demo`（有测试断言失败请求地址**不含** `/mock/`，
  且 client 源码不 import Mock 通道）；
- **Real 请求形状固定**：请求体**只有** `semester` / `current_schedule` / `preference`；
  学生上下文本轮**不进请求**；
- **业务展示中性化**：`App.vue` 把会把全部 MakeupTask 统称为"补修课"的表述改为
  "**历史培养要求评估**"，并写明含"已满足 / 待课程认定 / 已确认需补修"，
  以逐行判定列为准（`MakeupTaskList.vue` 的"需要补修 (N)"本就只统计 `required`，未改）；
- **未重构**：`MakeupTaskList` / `CourseOfferingList` / `PlanResultPanel` / `PreferencePanel` / `SectionCard`
  均未修改；`TopStatusBar` 仅改导航标签并新增一个锚点；
- ⛔ **未实现**：XLSX 解析、Curriculum Diff、课程等价、Planner 冲突、Path Repair、real provider。

**验证结果**：

```text
cd frontend && npm test              →  82 passed / 82（7 个测试文件）
cd frontend && npm run build         →  成功（含 vue-tsc --noEmit 类型检查）
cd frontend && npm run test:scenarios →  既有 14 项 SSR 场景全部通过（Mock 通道未回归）
```

⚠️ **新增 devDependencies**：`vitest` / `@vue/test-utils` / `jsdom`（`package-lock.json` 随之变更）。
此前前端只有 `verify_all_scenarios.mjs`（SSR 渲染断言），**无法**覆盖表单交互
（输入 / 勾选 / 增删行），因此为满足本轮测试要求引入标准 Vue 测试栈；**待人工确认**。

## 缺陷修复：invalid 表单必须阻止提交（同分支 `feature/frontend-user-input-gate`）

**Review 发现的真实缺陷（已复现、已修复、已加测试锁定）**：

> 当 `max_credit` 被输入为**负数或非数字**时，表单**仍被判为合法**，Real Planning 按钮**可点**，
> 请求会被发出。

**根因（两层）**：

1. `PreferenceForm` 把非法输入**归一化成 `null`**（"不猜测"这一半是对的），
   但归一化后它与"**未触碰 / 主动留空**"**无法区分**，而 `isFormValid` 只看归一化后的
   `form.preference.maxCredit` → 非法输入被当成"未设定" → 表单 valid；
2. 提交入口只有按钮 `disabled` 一道防线，`submitRealPlan()` 内部**没有**二次校验。

**修复（最小改动，仅前端）**：

- `state/userInput.ts`：新增 `invalidFields: InvalidatableField[]`（**不是**公共 `Preference` 字段，
  不进入请求体）与 `normalizeMaxCreditInput(raw) → { value, invalid }`；
  `isFormValid()` **首条**即判断 `invalidFields.length > 0 → invalid`；
- `components/PreferenceForm.vue`：用 `normalizeMaxCreditInput` 归一化；
  非法时把 `maxCredit` 记入 `invalidFields`（取值仍不猜测，按 `null` 保留），
  修正后自动清除该标记；`max_credit` 输入框由 `type="number"` 改为
  `type="text" inputmode="decimal"` —— 浏览器会对 number 输入静默丢弃非数字，
  校验必须由组件自己负责；
- `App.vue` `submitRealPlan()`：新增**提交前守卫** `if (!isFormValid(...)) return`，
  不满足时**一个请求也不发**（按钮 `disabled` 只作界面提示，不作为唯一防线）。

**修复过程中同时发现并修掉一个自身引入的回归**：`onMaxCreditInput` 原先**分两次 emit**
（先 `patchPreference` 再 `setFieldInvalid`），第二次展开的是**过期的 `props.form`**，
会把刚写入的取值覆盖回 `null`（表现为输入 `24` 后值变 `null`）。
现已改为**一次性发出同一个新状态**。

**成功标准（逐条测试锁定，见 `tests/form-validation-gate.spec.ts`）**：

| 场景 | 期望 | 结果 |
|---|---|---|
| untouched / 主动留空 | 按 `null` / default 序列化，**允许**提交 | ✅ |
| `max_credit = -5` | invalid → 禁止提交 → **fetch 0 次** | ✅ |
| `max_credit = abc` | invalid → 禁止提交 → **fetch 0 次** | ✅ |
| `semester = 2026-9` | invalid → 禁止提交 → **fetch 0 次** | ✅ |
| `avoid_times` end < start | invalid → 禁止提交 → **fetch 0 次** | ✅ |
| **程序化触发提交（绕过 disabled 按钮）** | 守卫拦截 → **fetch 0 次** | ✅ |
| 修正非法输入后 | 恢复可提交 | ✅ |

**验证**：`npm test` → **55 passed / 55**（4 文件）；`npm run build` → 成功；
`npm run test:scenarios` → 既有 14 项全部通过。

## provenance 修复：Real 结果实际渲染 + Mock 课表禁止进入 Real（同分支）

**Review 发现的第二个 blocker 组（已修复、已加测试）**：

| # | 缺陷 | 修复 | 锁定测试 |
|---|---|---|---|
| **1** | `realPlanResult` 只被赋值、**从未渲染**：Real 提交成功后页面 4 号区块仍展示 `GET /api/v1/mock/demo` 的 `plan_result` → "**Real 标签 + Mock 结果**" | 新增 `planResultMode` / `displayedPlanResult`，4 号区块与概览状态改用后者；区块内新增 provenance 行「基础演示数据：Mock · 规划结果：Mock/Real」 | `tests/plan-result-provenance.spec.ts`（5 项） |
| **2** | Mock `current_schedule` 可进入 Real Planning：勾选 Mock Demo 教学班即可提交，会把演示用假教学班当成真实已选课程 | 新增 provenance 门禁 `hasMockSchedule()` / `isScheduleSubmittableToRealPlanning()`，并由 `evaluatePlanSubmission()` 统一守卫；UI 禁用提交并明确提示 | `tests/schedule-provenance-gate.spec.ts`（13 项）、`tests/app-provenance-guard.spec.ts`（2 项） |

**Blocker 1 — provenance 表达（精确到区块，不冒充整页）**：

```text
基础演示数据：Mock   ·   规划结果：Mock / Real
```

- ⚠️ `/api/v1/plan` 当前**只返回 `PlanResult`**，因此**不得**把整页
  MakeupTask / CourseOffering / Preference 统一标成 Real；
- 测试断言：Real 成功后 ① 实际渲染 Real 返回结果（`objective_summary` 可辨识）、
  ② Mock 的 `plan_result` 不再被当作结果显示、
  ③ 培养要求评估 / 教学班仍为 Mock 且仍带 `Mock` 标记、
  ④ Real 失败时保持 Mock 结果与 Mock provenance（不回退、不冒充）。

**Blocker 2 — provenance 门禁（只看数据自身来源，fail closed）**：

- 判定依据是教学班自身的 `data_source`，与"页面当前处于哪个模式"**无关**；
- **只放行两种情况**：**空课表**，或**每一项都明确为 `real`**；
- 含 Mock、real 与 mock **混合**、或**来源未经确认**（缺 `data_source` / 取值异常）→ **一律阻止**；
  ⛔ 不因"看起来像真实数据"而放行，必须**显式**确认为 `real`；
- 阻止原因**区分**两类并给出不同提示：
  含 Mock → "当前课表来源为 Mock 教学班，不能提交到 Real Planning。"；
  来源未经确认 → "当前课表包含来源未经确认的教学班，不能提交到 Real Planning。"；
- 阻止时 **`fetch` 0 次调用**；守卫是**纯函数**
  `scheduleProvenanceBlockReason()` / `evaluatePlanSubmission(form) → { allowed, reason }`，
  同时被 `App.submitRealPlan()` 与测试使用（避免"测试自造守卫"的空转断言）。

**Blocker 3（patch Review 第二轮补充）— Real 结果区不得使用 Mock 课程名**：

- `courseNameById` 来自 Mock 教学班 / 补修任务，属**页面基础展示数据**；
- 当**规划结果来自 Real** 时，传给 `PlanResultPanel` 的映射表一律为空（`{}`），
  否则会出现"Real 结果 + Mock 课程名"的 provenance 污染；
- 测试断言：Real 成功后结果区**不再出现** Mock 课程名，只显示 Real 返回的课程号本身。

**文案修正（同一轮）**：

- 全局式"当前数据模式：Mock / Real" → 改为**局部** provenance
  "**规划结果来源：Mock / Real**"（`PLAN_RESULT_SOURCE_LABEL`，`DataMode` 更名 `PlanResultSource`）；
  理由：`POST /api/v1/plan` 只返回 `PlanResult`，不能用全局说法；
- 页脚删除"Real 规划输入中的教学班仍是 Mock"这一**不准确**表述，
  改为区分「**页面基础展示数据**（`GET /api/v1/mock/demo`）」与「**规划结果**（`POST /api/v1/plan` 或 Mock 通道）」
  两类来源，并说明两者来源相互独立。

**验证**：`npm test` → **82 passed / 82**（7 文件）；`npm run build` → 成功；
`npm run test:scenarios` → 既有 14 项全部通过。
**测试有效性已实测**：回退 4 号区块渲染 → 渲染用例失败；禁用 provenance 分支 → 门禁用例失败（2 项）。

## Frontend Real E2E Wiring Preparation 结果（错误产品化 + 成功收口 + 联调信息）

**目标**：让前端从"已经有 Real client"提升到"**Codex runtime 一旦可用即可直接完成第一轮真实联调**"，
但本轮**不伪造任何真实数据**，也**不碰 backend / runtime / provider wiring**。

分支 `feature/frontend-real-e2e-prep`，base = `main = d7e17eedcf8d25c20b8a31e01a2e3ec3711ec32f`
（该 main 已含 Real Case A Curriculum、Frontend User Input Gate、Real Planning API Boundary）。

| 产出 | 内容 |
|---|---|
| `frontend/src/api/plan.ts` | 错误模型：`PlanApiError` 携带 **`kind` / `status` / `code` / `detail`**；导出 `parsePlanErrorBody()` 与 `REAL_PIPELINE_NOT_CONFIGURED` |
| `frontend/src/components/E2EDebugPanel.vue` | **仅开发环境**渲染的联调调试面板 |
| `frontend/src/state/userInput.ts` | 新增 `describePlanError()`、`describeScheduleProvenance()`、`isPreferencePresent()` |
| `frontend/src/components/SubmissionActions.vue` | 按错误**类型**分类展示（标题 + 说明 + HTTP 状态 + 后端错误码） |
| `frontend/src/App.vue` | 记录 `planErrorKind` / `planErrorStatus` / `planErrorCode` / `lastHttpStatus`，组合调试信息 |

**错误模型（`PlanErrorKind`，语义互斥且穷尽；UI 只按 `kind` 分支）**：

| `kind` | 触发条件 | 界面标题 |
|---|---|---|
| `not_configured` | **HTTP 503 且 `detail.error === "real_pipeline_not_configured"`**，或 503 但响应体**无法解析 / 无可识别信息** | **真实规划运行时尚未完成装配** |
| `input` | 422 | **Real Planning 输入未通过校验** |
| `server` | 5xx（503 之外）；**或 503 但响应体明确给出其它错误** | Real Planning 服务端错误 |
| `network` | 请求未能完成（连不上 / 连接被重置） | 无法连接 Real Planning 接口 |
| `http` | 其它非 2xx | Real Planning 调用失败 |
| `unexpected` | 2xx 但响应体不是合法 `PlanResult` 对象 | 返回了无法解析的结果 |

- ⚠️ **503 三态收紧**（`classifyPlanError()`，纯函数，有分类矩阵测试）：
  ① **只有 HTTP 503 且** `real_pipeline_not_configured` → `not_configured`
  （该 code 出现在其它状态码上**不具备**"未装配"含义：500 + 该 code → `server`、404 + 该 code → `http`）；
  ② 503 且**无法解析 / 无可识别信息** → `not_configured`（宁可如实说"未装配"）；
  ③ 503 但 body **明确给出其它错误**（有可识别 code 或 detail）→ **`server`**，
  ⛔ **不误报成"运行时尚未装配"**，且文案导向服务端排查；

- ⚠️ **422 只表示"输入未通过校验"**：标题统一为"Real Planning 输入未通过校验"，
  ⛔ **不声称**所有 422 都是"当前课表来源问题"（也可能是 `semester` 非法或 `preference` 形状错误）；
  具体原因**由后端返回**，前端原样展示 `code` 与 `detail`，⛔ 不推断具体是哪一项；
- ⚠️ **不假设后端一定有统一 error schema**：`parsePlanErrorBody()` 能识别已知的
  503 形状（`{detail:{error,message}}`）与 FastAPI 422 形状（`{detail:[{loc,msg,type}]}`），
  对未知形状**宽容处理**（返回 `null`，由状态码兜底），⛔ 不解析不存在的字段；
- ⚠️ **503 是"当前正确状态"，不是系统故障**：文案明确说明
  "当前页面可继续使用 Mock Demo；Real Planning 暂不可用"，并声明**不会自动回退到 Mock**。

**成功状态收口**：Real 成功后继续 `规划结果来源：Real`；
培养要求评估 / 教学班 / 偏好仍标 Mock；⛔ 不重新出现"当前数据模式：Real"这类全局说法。

**E2E 调试信息（`E2EDebugPanel.vue`，⛔ 仅 `import.meta.env.DEV`）**：
显示 `plan endpoint` / `request semester` / `current_schedule count` / provenance 摘要 /
`preference present`（只报布尔）/ `plan api enabled` / `last HTTP status` / `last error kind` / `plan result source`。
⛔ 不显示成绩内容、姓名、学号、GPA；⛔ 不 dump 请求 / 响应；⛔ 不显示 token / cookie / header。

**Real 提交开关**：`VITE_PLAN_API_ENABLED` **只**控制 Real submit 是否开放；
不改变 Mock Demo 获取、**不触发自动请求**（有测试断言首屏 0 次 `/api/v1/plan`）、不改变 provenance gate。

**验证**：

```text
cd frontend && npm test              →  113 passed / 113（8 个测试文件）
cd frontend && npm run build         →  成功（含 vue-tsc --noEmit）
cd frontend && npm run test:scenarios →  既有 14 项全部通过
```

**明确状态表述**：**Frontend 已准备好 Real E2E 联调**；
⛔ **不得**写成"Real E2E 已完成" —— Codex 的 Real Runtime Wiring 尚未可用，后续真实联调尚未进行。

## 当前接口
- 读取：`MakeupTask[]`、`CourseOffering[]`（**含 `meetings[]`**）、`Preference`、`PlanResult`
  （**规划结果**在 Real 成功前来自 Mock；成功后来自 `POST /api/v1/plan`）
- 前端 Mock 数据来源：`GET /api/v1/mock/demo`（**永久保留**，本轮未修改）
- **前端已预留 Real 接口 client（本轮）**：`POST /api/v1/plan`，
  请求体**只有** `semester` / `current_schedule` / `preference`，响应按 `PlanResult` 处理；
  ✅ **该 endpoint 已经实现**（integration/runtime 侧已提供；Gate E 更新，此前"由并行开发中的
  `feature/real-plan-api` 提供、当前 main 上并不存在"的表述**已过时**）；
  未装配时后端**明确返回 `503 real_pipeline_not_configured`** —— 这是**当前正确状态**，
  前端单独的错误态展示它（⛔ 不写成"接口不存在"、⛔ 不 fallback 到 Mock）；
  `VITE_PLAN_API_ENABLED` 默认关闭只是**演示默认值**，Real 提交按钮 disabled，且**不 fallback 到 Mock**；
  ⚠️ 该接口**只返回 `PlanResult`**（不含 MakeupTask / CourseOffering / Preference），
  因此前端只把**规划结果**标为 Real，其余区块仍为 Mock（见上方 provenance 修复）；
  ⚠️ 提交受 **课表 provenance 门禁**约束（**fail closed**）：只有**空课表**或**每项都明确为
  `data_source = "real"`** 才放行；含 Mock、来源混合或来源未经确认时**禁止提交**（`fetch` 0 次）
- 业务接口统一前缀 `/api/v1`；Mock 响应带 `X-Data-Source: mock`
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
- **本轮新增的是"用户输入"，不是真实数据**：目标学期 / 转专业上下文 / 当前课表 / 偏好
  都是**用户自己录入**的输入；成绩文件在**前端**仍只选择、不解析、不上传；
  ⚠️ Gate F 之后**后端**已具备通用 XLSX 摄取入口
  （`POST /api/v1/completed-courses/import`，见 `docs/data/XLSX_COMPLETED_COURSES_IMPORT.md`），
  但**前端尚未接线**到该入口 —— 两者不要混淆；
  页面显示的数据模式在 Real 接口接通前**始终为 Mock**
- 「当前功能仅使用 Mock 数据验证，尚未完成真实数据验证」

## Gate E：Frontend Real-path Readiness（✅ 已收口）

**前提**：`POST /api/v1/plan` 已在后端实现（integration/runtime 侧）；本 Gate ⛔ 不改前端业务规则、
⛔ 不改 API contract / public Schema、⛔ 未新增任何判断逻辑。

回归锁定：`frontend/tests/real-path-readiness.spec.ts`（**21 用例**，全 mocked fetch）。
逐条对应本轮 mandate 的 15 项要求：

| # | 要求 | 证据 |
| --- | --- | --- |
| 1 | Real / Mock 明确区分 | 成功路径：`plan-result-provenance` = Real，基础区块仍标 Mock |
| 2 | Real 请求仍走真实 `/api/v1/plan` | `api/plan.ts` 只用 `PLAN_ENDPOINT`；⛔ 不 import Mock 通道 |
| 3 | 503 `real_pipeline_not_configured` 有明确错误态 | `real-plan-error-title` = "尚未完成装配" + HTTP 503 + 错误码 |
| 4 | ⛔ 无 Real → Mock fallback | 503 后 `plan` 请求数仍为 1、Mock 请求数不变、结果仍为 Mock |
| 5 | `meetings=[]` 中性文案 | `EMPTY_MEETINGS_DATA_TEXT` = "当前数据中无排课信息" |
| 6 | 缺地点中性文案 | `formatMeetingLine` 在无 campus/classroom 时 = "当前数据中无地点信息" |
| 7 | `selected_classes` ⛔ 不写成"已选课 / 已成功选中" | 渲染文本 + 源码静态守卫 |
| 8 | `feasible` ⛔ 不写成"可直接执行" | 源码静态守卫 + 空 `unresolved` 文案 |
| 9 | `changes` / `risks` / `unresolved` 空数组只表示"无记录" | "未返回方案变更记录 / 未返回风险项 / 未决事项为空"，⛔ 无"无风险 / 无需调整" |
| 10 | Preference ⛔ 不声称已被求解器执行 | "以 PlanResult 输出为准"；⛔ "已按偏好求解 / 偏好已全部满足" |
| 11 | 前端 ⛔ 不重算冲突 / 课程认定 / 优先级 | 静态：⛔ 无 `hasConflict` / `isFeasible` / `repairPlan` … |
| 12 | ⛔ 无自造容量阈值 | 余量极低（4 / 90）仍原样展示；⛔ "余量紧张 / 即将满员 / 阈值" |
| 13 | UNKNOWN / `manual_confirmation` 语义保留 | `schedule_unknown` / `manual_confirmation` / `missing_data` 原样展示 + 原始 `type` 字段 |
| 14 | Real 结果 provenance 展示正确 | 只有规划结果标 Real，其余区块仍标 Mock |
| 15 | loading / success / 503 / generic 500 状态稳定 | 进行中 disabled + "正在请求 Real Planning…"；500 ⇒ "server"，⛔ 不写成"未装配" |

```text
frontend: npm test（9 文件 134 用例）· npm run typecheck（vue-tsc --noEmit）· npm run build  全部 exit 0
```

⚠️ 唯一未变更的接口面事实：真实 `POST /api/v1/plan` **不返回 `X-Data-Source`** 头
（⛔ 属接口面变更，本 Gate 未擅自扩 API）；前端全仓库只有 Mock 客户端读取该标记。

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
- **本轮产出等待 Architecture Review**：Frontend User Input Gate Phase 1
  （输入区 / Mock-Real 隔离 / Real client 预留），以及**新增前端测试依赖**是否批准；
- ✅ **Gate E（Frontend Real-path Readiness）已完成**：`POST /api/v1/plan` 已在后端实现，
  前端按"未装配 ⇒ 503 `real_pipeline_not_configured`"这一**当前正确状态**展示；
  readiness 回归锁定在 `frontend/tests/real-path-readiness.spec.ts`（**21 用例**）。
  打开真实链路只需 `VITE_PLAN_API_ENABLED=true`（是否可用仍由后端 readiness 决定）；
  在此之前 Real 按钮保持 disabled，**不得**用 Mock 冒充 Real；
- **下一步的候选工作**（需另行确认，本轮未做）：
  ① 把预填的转专业上下文作为**显式请求字段**扩展进 `POST /api/v1/plan`（属**接口变更**，须走 `【接口变更请求】`）；
  ② 已修课程 XLSX 的真实上传与 Curriculum User Input API 对接（依赖上游；
  ⛔ 前端**不得**自行解析成绩或生成补修任务）；
  ③ 展示层继续承接 PlanResult；
- **不再等待 DG-07B / DG-07C / DG-07D**：DG-07A / B / C / D 已全部 IMPLEMENTED / REVIEWED / MERGED，
  Data Gate 已恢复 **PASSED / CLOSED**；
- 前端继续保持展示层边界，不新增容量阈值、课程优先级、冲突推断或 Preference 执行推断；
- 真实产品联调的前置条件转为：**complete semester snapshot + 真实 CurriculumProvider +
  真实 PlannerProvider + Integration 接线**；
- `partial` snapshot 仍不得进入产品链路，真实 Capture Bundle 仍不得进入 public Git；
- G11 学校侧业务原因仍未知；前端只展示 `meetings=[]` 的中性数据状态，不命名学校业务状态；
- 完成真实 Provider 联调后，再做 Case A 端到端 Demo 与比赛展示收尾。

## 浏览器 E2E 验收（2026-10-09，分支 `test/final-upgrade-browser-e2e`）

- 用**真实浏览器**（系统 Microsoft Edge，`playwright-core` `channel=msedge`，⛔ 未下载浏览器）
  对真实 FastAPI + 真实 Vite 前端跑通三入口与 AI 调整两次确认闭环：**18 / 18 通过**。
- 断言的是**浏览器实际发出的 HTTP 请求**：完整闭环四接口全部真实调用；
  未确认时 `/solve` 调用数为 0；未启用档 AI 请求为 0；预览档 `/ai-planning/*` 请求为 0。
- 覆盖：三入口切换、转专业分析如实显示"没有已核验版本目录"、补修路径四状态与 Mock 标识、
  候选对比（真实 Planner 新增一门课）、采用后刷新展示方案、拒绝/过期/冲突保持原方案、
  抽屉重开与导航切换不误导、375/768/1440 三档布局、连点只发一次请求、后端不可用不回退 fixture。
- 本轮**未改任何生产代码、公共 Schema、接口或 Planner 算法**；
  新增内容全部在 `backend/tests/qa_browser_e2e/` 与 `tools/browser-e2e/`（测试基础设施）。
- 回归：后端 3188 passed / 2 failed（既有平台差异）/ 2 skipped；前端 274 passed；
  `vue-tsc` exit 0；`npm run build` exit 0。**无新回归。**
- **仍未验证**：真实 DeepSeek 在线调用（NOT VERIFIED，无密钥）、真实已核验培养方案目录与
  真实教学班/成绩数据 E2E（BLOCKED）。
- 详见 `docs/final_upgrade/reports/BROWSER_E2E_REPORT.md`。

## 联合浏览器验收（2026-10-09，分支 `qa/final-upgrade-ux-browser-e2e`）

- 把 PR #68（UX，`a38c9cd`）与 PR #69（浏览器 E2E，`d7e5f7e`）合到独立 QA 分支，
  **两个原始分支均未修改**；在合并后的树上重跑真实浏览器验收。
- **PR #69 原有 18 项全部通过**（对照跑法：`--cases=_cases_baseline18.mjs`，18 passed / 5 skipped）：
  说明 PR #68 的区块重排与信息层级调整**没有破坏任何旧定位假设**。
- 新增 5 项联合验收用例（共 23 项，**23/23 通过**）：
  规则解释入口与面板（X01/X02，真实调用 `POST /api/v1/explanation/plan`，标注"规则模板（非 AI）"）、
  缺口摘要不伪造数字（U01）、五阶段/硬软分区/变化摘要/临时采用提示（U02）、
  支撑数据分区与旧 testid 未丢（U03）。
- 响应式 375/768/1440 增加 UX 结构断言与**抽屉头部信息密度量测**，三档通过。
- **发现 1 个既有缺陷 + 1 个观察项（均需人工确认，本轮未自行改前端）**：
  - **K-1（既有样式缺陷，非 PR #68 引入）**：抽屉头部关闭按钮无 `flex-shrink: 0`，
    375px 下被挤成 61×77px 的竖长条（文本盒仅 14×54px），768/1440px 为 71×58px；
    在 PR #69 分支（UX 改动前）测得完全相同，属既有基线问题。
    可用 `$env:QA_STRICT_HEADER_BUTTON=1` 一键复现为失败；
    建议 `.ai-drawer__head .button { flex-shrink: 0; white-space: nowrap; }`。
  - **O-1**：375px 下抽屉状态行折 2.8 行、头部占视口 14%，把 `enabled / api_key_configured /
    live_model_available / model` 直接铺开偏密；但该文案已被
    `frontend/tests/ai-planning-drawer.spec.ts` 锁定，属有意披露，改动需同步前端测试。
- 回归：浏览器 23/23；后端 3188 / 2（既有平台差异）/ 2；前端 **303 passed**（含 PR #68 新增用例）；
  `vue-tsc` exit 0；`npm run build` exit 0。**无新回归。**
- 仍未验证：真实 DeepSeek 在线调用（NOT VERIFIED）、真实培养方案/教学班数据（BLOCKED）、
  真机浏览器与无障碍专项（未执行）。
- 详见 `docs/final_upgrade/reports/UX_BROWSER_E2E_JOINT_REPORT.md`。

## PR #70 最终验收（2026-10-09，`01fc7b5` 复跑）

- 在 PR #70 远端 HEAD `01fc7b5`（仅 `frontend/src/styles/base.css` +5 行的 CSS 修复）上完成最后一轮验收。
- **缺陷 K-1 已收口**：`QA_STRICT_HEADER_BUTTON=1` 严格模式下 R-375 **通过**；
  手机端关闭按钮 **85×39px、标签 1 行**（修复前 61×77px、文字被折行），768/1440px 同样为 85×39px 单行。
- **全量 23 项真实 Edge 浏览器 E2E：23 passed / 0 failed / 0 skipped**（205.9s）。
- 前端 **Vitest 303 passed**、`vue-tsc` **exit 0**、`npm run build` **exit 0**；
  后端 **3188 passed / 2 failed（既有平台差异）/ 2 skipped**。**无新回归。**
- 375 / 768 / 1440 关键截图逐一目视核对：**无横向溢出、无按钮遮挡**。
- **结论：达到合并条件（merge-ready）**；⛔ 未自动合并，Draft 状态由负责人决定是否转 Ready。
- 非阻塞备注：① 后端 2 项既有平台差异失败（与本 PR 无关）；
  ② 375px 下抽屉头部状态行仍偏密（2.8 行 / 头部占视口 17%），该文案被前端自身
  `frontend/tests/ai-planning-drawer.spec.ts` 锁定，属有意披露，未改。
- 仍未验证（属单独验收）：真实 DeepSeek 在线调用（NOT VERIFIED）、真实培养方案/教学班数据（BLOCKED）、
  真机浏览器与无障碍专项（未执行）。
- 顺带修复**测试基础设施缺陷**：Windows 下服务进程树未被清理，导致孤儿 Vite/uvicorn 累积
  （实测 317 node / 97 python）并拖垮后续运行。现改用真实子进程 PID + `taskkill /T /F` 树级清理，
  运行后残留进程 **0**，单例 19.6s、全量 205.9s。⛔ 未触碰业务逻辑。
- 详见 `docs/final_upgrade/reports/UX_BROWSER_E2E_FINAL_ACCEPTANCE.md`。

## 最终交付冲刺（2026-10-09，分支 `release/final-upgrade-demo-readiness`）

- 基线：`origin/feature/final-upgrade` = `85152e9`（PR #70 合并提交，已核实其父链含 `ed82794` 与 `01fc7b5`）。
- **P0 合并后回归（现场实测）**：后端 **3188 passed / 2 failed（既有 Windows+Py3.14 平台差异）/ 2 skipped**；
  前端 **313 passed**（含新增 10 项）、`vue-tsc` exit 0、`npm run build` exit 0；
  浏览器 **24 passed / 0 failed**；`QA_STRICT_HEADER_BUTTON=1` 三档 **3 passed**；
  运行后遗留 `node`/`python`/headless Edge 进程 **0**（未触碰开发者自己的浏览器）。
- **P1 移动端头部信息密度（观察项 O-1）已修复**：头部改为"一句话能力状态" +
  可展开的"技术详情（配置与限额）"，**原始字段完整保留**；
  375px 状态行 **2.8 行 → 2 行**，768/1440px **1.8 行 → 1 行**；
  五档能力状态（未配置通道/状态未知/前端预览/未启用/无密钥/无在线模型/配置就绪）逐档区分，
  明写"配置就绪不代表在线调用已经成功"，并有 10 项穷举测试锁定；⛔ 未删任何状态信息、⛔ 不泄露密钥。
- **P1 依赖安全已清零**：`npm audit` **0 漏洞**。低风险补丁 `source-map-js 1.2.1 → 1.2.2`；
  `vitest` **3.2.7 → 4.1.11**（依据 advisory 明确"3.x 不再修复"、且 `4.1.11` 为首个含全部修复的版本；
  升级前已核验 Vite 8.3.1 / Node 24 满足前提，且本项目**零 `vi.spyOn`**，避开 v4 的 mock 语义变更）。
  升级后前端 313 passed、类型检查与构建通过、浏览器 24/24。
- **P1 CI**：新增 `.github/workflows/ci.yml`（`contents: read`、零 secret、⛔ 无 audit fix、⛔ 无 auto-merge）
  与 `docs/final_upgrade/CI_PLAN.md`。**已在 GitHub Actions 真实运行**（Run #37948975531，提交 `af6a5cb`）：
  前端 Job 与依赖审计 Job **SUCCESS**；后端 Job **FAILURE** —— 原因是**缺少测试依赖 `python-docx`**
  （只存在于开发机、未写进 `requirements.txt`），Linux+Py3.12 收集阶段 `ModuleNotFoundError: No module named 'docx'`。
  已判定它为**测试依赖**（`docx_reader.py` 用标准库 zipfile+ElementTree 读 OOXML，不 import docx；
  只有 2 个测试文件用它构造 .docx），补进 `backend/requirements.txt` 测试依赖段，
  并在**空白虚拟环境**中自证：`pip install -r requirements.txt` 后全量 pytest **3188/2/2**，与基线一致。
  ⛔ 未跳过测试、⛔ 未加 continue-on-error。
  **修复后第 2 次运行（Run #38006322656，提交 `decc84b`）三个 Job 全部 SUCCESS**：
  Backend pytest / Frontend tests / Dependency audit 均通过；后端日志确认
  `Collecting python-docx>=1.1 (from -r requirements.txt (line 37))` 且无 `FAILED` 段。
  ⚠️ 如实说明：该 Job 日志本地读取时被尾部截断，**Linux 上的准确测试计数未取到**
  （可确证收集成功、跑到 100%、无失败）。
- **P1 真实 DeepSeek 在线验证：BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE**
  （实测四个环境变量全部 unset，未打印任何值、未使用历史旧密钥）。
  已交付可直接执行的说明 `docs/final_upgrade/DEEPSEEK_LIVE_VERIFICATION.md`（8 条验收标准 + 8 步流程 + 失败处理表）。
  另：`DEEPSEEK_MODEL=deepseek-flash` 已按官方 *Models & Pricing* 在线核验为**当前有效模型名**（2026-10-09）。
- **P1 真实数据接入准备**：`docs/final_upgrade/REAL_DATA_READINESS.md`（缺口清单 D1–D5、逐字段说明、
  五层校验流程、接入指南、合成夹具清单、已知风险）；新增可直接执行的验收脚本
  `backend/tests/verify_real_data_e2e.py`（合成模式已实测：目录 → 已修记录 → MakeupTask 通，教学班缺失时如实 `no_course_data`）。
- **P2 演示剧本已彩排并自动化**：新增浏览器用例 `DMO01-demo-script-rehearsal`，按剧本 11 步实测全通；
  `DEMO_SCRIPT.md` 追加 §7 彩排记录与"哪一步是什么数据"对照表。
- 修改文件与未验证项详见 `docs/final_upgrade/reports/FINAL_DELIVERY_READINESS_REPORT.md`。
- ⛔ 未改 `main`、公共 Schema、`docs/interfaces/`、Planner 核心算法；⛔ 未自动合并。

### 第 6 轮（旧版 UI 增量整合 · Phase 2 第一轮）
- **区块顺序恢复**（`MakeupPathView.vue`）：旧版优先 —— 概览 → 用户输入 → 历史培养要求评估 →
  教学班 → 偏好 → 规划工作区（当前学期 → 后续学期 → 风险 → 结果 → 解释）→ 支撑数据。
- **恢复旧版四步流程引导** `pipeline-guide`（放规划工作区内，⛔ 非功能导航）；
  复用既有 CSS（base.css:301-366），⛔ 未新增样式。
- **修复 `PlanResultPanel` 视觉回归**：wrapper 也绑定 `evidenceEnabled`，
  关闭时 DOM 与旧版一致（`<span>` 直接是 `.selected-card` 的子元素）。
- **修复 `E2EDebugPanel` 重复渲染**：⛔ 不再向下传 `debug-info`，只保留 shell 层一个
  （实测 `[data-testid="e2e-debug"]` 由 2 → 1）。
- 阅读顺序提示由 5 步更新为 7 步（与真实 DOM 顺序一致）。
- 测试：前端 **372 passed**（+1）；`vue-tsc` 0；`build` 0；浏览器 E2E **27/27**。
- 页面高度：旧版 6635px → 新版 8440px（+1805px，含 5 个新增区块）。
- ⚠️ 「成绩截图样本导入」样本未提供 ⇒ ⛔ 未实现，也⛔ 不假装已实现识别。