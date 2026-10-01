# Agent / Frontend 当前状态

> 最后更新：2026-09-30（**Phase 2B-0D：教学班技术侦察**完成，等待 Reviewer）
> 数据状态：**核心业务数据仍全部为 Mock**；已取得 Case A 两份 **2025 级真实培养方案**、
> **D4 已修课程脱敏样本** 与 **D5 教学班侦察样本**（均为认证来源），
> 但**原始材料、逐行记录与 Raw 响应均不进入 public Git**

## 当前阶段

**Phase 2B-0：真实数据准备与数据源技术侦察**

```text
2B-0A ✅ 数据规划  →  2B-0B ✅ 公开政策 / 培养方案  →  2B-0B+ ✅ 认证来源培养方案
                   →  2B-0C ✅ 已修课程最小脱敏样本  →  2B-0D ← 本轮（教学班技术侦察）
                   →  数据 Gate  →  恢复 Phase 2B Integration / Orchestrator
```

- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待真实样本通过 **数据 Gate** 后恢复；
  Phase 1 与 Phase 2A 成果不受影响。

## 2B-0D 当前结果（Case A：2025级 遥感科学与技术 → 网络空间安全）

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

## 当前接口
- 读取：`MakeupTask[]`、`CourseOffering[]`、`Preference`、`PlanResult`（当前来自 Mock）
- 前端唯一数据来源：`GET /api/v1/mock/demo`
- 业务接口统一前缀 `/api/v1`；全部响应带 `X-Data-Source: mock`
- 公共契约真源仍是 `/schemas/*.schema.json`，本轮**未修改**

## 当前使用数据
- **业务数据仍全部为 Mock**：仓库根目录 `/mock_data/`（人工虚构的演示数据）
- 本轮取得的是**公开官方政策 URL / 事实**、**Case A 两份 2025 级真实培养方案的结构化事实**、
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
- **G9 结构缺口待架构裁决**：一个教学班可有**多个上课时间 / 地点 segment**，
  当前 `CourseOffering` **无法无损表达**；**最终表示方式留给 Data Gate**
- 上游 Curriculum / Course Data / Planner 均未产出真实结果，前端只能展示 Mock
- **集成骨架尚未建立**：上游模块暂时没有正式的接入点
- **五类真实样本已齐备，但尚未通过数据 Gate**：Phase 2B Integration 仍暂停编码

## 下一步
- **2B-0D 完成，等待 Reviewer 验收**
- **Review 通过后进入 Data Gate**（处理 G9 多 segment 建模、`Course` / `CurriculumCourse` /
  `CompletedCourse` 的架构边界等真实数据暴露出的问题）。
  ⚠️ **本轮不得自行开始**，必须等新一轮任务书
- 2B-0 全程遵守 `docs/data/DATA_ACQUISITION_PLAN.md` 的三层数据模型与红线：
  **Raw 不进 Git；D4 的 Raw 与逐行脱敏样本均不得进入 public 仓库；`/mock_data/` 保持人工虚构**
- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待**真实样本通过数据 Gate**后恢复
- 比赛 Demo 故事线**不属于当前开发主线**，推迟到后续产品展示阶段再评估
- 在真实 Curriculum / Planner / Course Data 稳定之前，不接 Agent / LLM
