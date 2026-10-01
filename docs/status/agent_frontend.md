# Agent / Frontend 当前状态

> 最后更新：2026-09-30（**Data Gate-1 最终同步修复**完成 —— 架构内容已通过 Reviewer；等待 Reviewer 收尾确认）
> 数据状态：**核心业务数据仍全部为 Mock**；已取得 Case A 两份 **2025 级真实培养方案**、
> **D4 已修课程脱敏样本** 与 **D5 教学班侦察样本**（均为认证来源），
> 但**原始材料、逐行记录与 Raw 响应均不进入 public Git**
> 裁决状态：**Architecture Lead 已完成 DG-01 – DG-06 裁决**（见 `docs/data/DATA_GATE_DECISIONS.md`）；
> **通过条件 C1–C11 中已有 10 项确认**（**C1 / C2 / C3 / C4 / C6 / C7 / C8 / C9 / C10 / C11**），
> **仅 C5 待 Data Gate-2 执行**；
> **公共契约尚未实施** —— `/schemas/` 与 `/docs/interfaces/` 仍未修改

## 当前阶段

**Phase 2B-0：真实数据准备与数据源技术侦察**

```text
2B-0A ✅ 数据规划  →  2B-0B ✅ 公开政策 / 培养方案  →  2B-0B+ ✅ 认证来源培养方案
                   →  2B-0C ✅ 已修课程最小脱敏样本  →  2B-0D ✅ 教学班技术侦察
                   →  Data Gate-1 ✅ 架构决策草案 + 架构裁决落档
                   →  Data Gate-2（实施 DG-01 契约变更 + DG-06 文档修正）
                   →  恢复 Phase 2B Integration / Orchestrator
```

- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待 **Data Gate** 通过后恢复；
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
- **G9 已裁决，待 Data Gate-2 实施**：一个教学班可有**多个上课时间 / 地点 segment**，
  当前 `CourseOffering` **无法无损表达**；**DG-01 裁决为 `CourseOffering` 1 — N `Meeting`（嵌套 `meetings[]`，方案 A）**，
  **Data Gate-2 正式修改 `course_offering.schema.json`**（**有意的 breaking migration**）
- **DG-01 – DG-06 已全部裁决，尚未实施**：本轮只**落档裁决**，**未修改任何契约**；
  进入 Data Gate-2 实施的只有 **DG-01（Schema）** 与 **DG-06（接口文档）**
- **上游 Curriculum / Course Data / Planner 均未产出真实结果**，前端只能展示 Mock
- **集成骨架尚未建立**：上游模块暂时没有正式的接入点
- **五类真实样本已齐备，但尚未通过 Data Gate**：Phase 2B Integration 仍暂停编码
- **接口文档债务已批准修正**：`docs/interfaces/planner.md` 的职责描述与 `/AGENTS.md` 第 5 节冲突（DG-06），
  **Data Gate-2 执行修正**；本轮**仍未修改**该文件
- **`prerequisites[]` 尚无真实证据**：真实培养方案样本中**未发现明确的先修字段**，
  该字段"可被真实数据填充"目前**无证据**（不构成"学校无先修制度"的结论）；
  裁决要求：来源无法提供时**标记未知 / 待人工确认，不得自动补齐**
- **meeting 级教师关联为已知的表达损失**：`teachingTimePlaceStr` 的 segment **本身包含教师项**，
  但 **MVP 的 `meetings[]` 不承载教师**；`teacher` 暂留教学班级作为汇总 / 展示字段，
  登记为 **known deferred representation gap**（**不是"无证据"**）

## 下一步
- **Data Gate-1 最终同步完成，等待 Reviewer 收尾确认**
- **随后进入 Data Gate-2**：实施 **DG-01**（`course_offering.schema.json` 改为
  `CourseOffering` 1 — N `Meeting`，**有意的 breaking migration**，需同步
  `mock_data/course_offerings.json`、`backend/app/models/contracts.py`、`frontend` 类型与展示）
  与 **DG-06**（修正 `docs/interfaces/planner.md`，必要时同步 `curriculum.md`），
  即完成 **C5**（**C1–C11 中唯一未完成项**）
- **DG-02 / DG-03 / DG-04 / DG-05 本阶段不产生契约变更**（分别留 Curriculum 内部 / 复用
  `CourseOffering[]` / 留 Curriculum 内部 / 不新增对象）
- **C9 落地时**：批量导入前必须先确认合理 `pageSize` / 请求规模；
  只能取得部分范围时**必须显式记录 completeness**，**不得宣称 complete**
- **C11 落地时**：`prerequisites[]` / `weekDay` / `openingSchoolName → campus` /
  meeting-level teacher 四项风险保持"待确认"或"已知暂缓"，**不允许实现层自行补齐**
- ⚠️ **在 Reviewer 复验与新一轮任务书之前不得实施任何变更**：不得改 `/schemas/` 或 `/docs/interfaces/`、
  不得写 Course Data Adapter / `CourseDataProvider`、不得进入 Integration。
  **不得自行进入 Data Gate-2**
- 2B-0 全程遵守 `docs/data/DATA_ACQUISITION_PLAN.md` 的三层数据模型与红线：
  **Raw 不进 Git；D4 的 Raw 与逐行脱敏样本均不得进入 public 仓库；`/mock_data/` 保持人工虚构**
- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待**Data Gate 通过**后恢复
- 比赛 Demo 故事线**不属于当前开发主线**，推迟到后续产品展示阶段再评估
- 在真实 Curriculum / Planner / Course Data 稳定之前，不接 Agent / LLM
