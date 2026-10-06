# Course Data 当前状态

> 最后更新：2026-10-05（**DG-07B — Course Data Empty-Meeting Normalization 已实施 / REVIEWED**：
> **只有** Raw row **没有** `teachingTimePlaceStr` 这个 key 时才产出 `meetings = []`；
> `null` / 空串 / 其它类型 / malformed / 解析失败**继续 fail closed**；
> 缺排课信息的 row **不被跳过**（仍计入 `loaded_count`）。
> **DG-07A / B / C / D 均已实施 / REVIEWED；Data Gate 已恢复 PASSED / CLOSED。**）
>
> ✅ **DG-07 empty-meeting rollout safety gate 已解除**：
> Course Data 可以忠实产生 `meetings = []`，Planner 已按 schedule unknown 安全处理，
> Frontend 已中性展示。⚠️ 这只解除“unknown schedule 的安全处理”阶段门；
> **complete semester snapshot、真实 Provider / Integration / API / Frontend E2E
> 仍未完成，partial snapshot 仍不得进入产品链路。**
>
> ⚠️ **准确表述（不得夸大）**：
> **真实 Course Data 尚未完成**，**尚未取得 complete semester snapshot**。
> **已完成真实 smoke run + 一次真实结构诊断 + 一次真实相关性诊断 + 一次人工界面最小核验**
> （均在真正的「**全校开设课程**」独立模块内）：
> **same-origin 请求成功**、**认证不再是当前 blocker**；
> 第 1 页 **200** 条真实 row（同页 `reported_total = 6892`）中
> **39 条完全没有 `teachingTimePlaceStr`**、**161 条非空**，其余形态为 0；
> ⚠️ **39/200 = 19.5% 只描述第 1 页这 200 条样本**，**不代表** `6892` 条整体的比例、
> **不得外推**；
> C1C 的相关性结果显示：**结构差异集中在排课相关字段**
> （`timePlaceId` 38/39 缺失 vs 161/161 存在；`weekDay` 38/39 缺失 vs 12/161 缺失），
> 而 `limitNumber` / `selectedNumber` 在 39 条中**完整存在**；
> C1D 人工核验（**n = 2**）显示：两条典型候选在官方 UI 中**均作为普通教学班行存在**，
> 但**时间 / 周次 / 地点完全空白**且**无任何状态文字**；
> 因此 `collect()` **不再因"缺排课字段"而整体失败**（DG-07B 起该 row 规范化为
> `meetings = []`），**但仍未重新采集**，**尚未生成真实 Capture Bundle**。
> **G11 仍未 resolved**：契约方向与下游安全处理已经闭环
> （DG-07A / B / C / D 均已实施 / REVIEWED），但**学校侧业务原因仍未查明**。
> 不推测、不写成任何业务结论。
> 后端 Python 侧仍然**零网络**：没有 endpoint、没有认证处理、**不会自动发起 SYSU 请求**。
>
> ⚠️ **导航纠错**：「**选课**」与「**全校开设课程**」是**两个独立模块**；
> 早先"选课 → 全校开设课程"的层级描述**不正确**，已作废。

## 阶段状态

```text
D5 教学班技术侦察                                  ✅ 已完成（OFFERING-001，2026-1）
Data Gate（契约裁决 + 实施）                        ✅ 已完成（C1–C11 全通过）
Course Data normalization core（2B-2A）             ✅ 已完成
teachingTimePlaceStr parser（2B-2B）                ✅ 已完成（依据私密脱敏样本，未入 Git）
本地 Raw-response import adapter（2B-2B）            ✅ 已完成（零网络）
分页采集核心 Pagination Core（2B-2C0）              ✅ 已完成（零网络；fetch_page 由外部提供）
SYSU 分页参数人工验证（pageNo / pageSize / total）   ✅ 已完成（前两页；见下）
浏览器端授权采集器代码 + Capture Bridge（2B-2C1A）   ✅ 代码已准备
真实 smoke run（认证 + 第 1 页请求）                 ✅ 已执行（same-origin 成功；认证不再是 blocker）
结构诊断入口 schedule presence diagnostic（2B-2C1B） ✅ 已完成并**由负责人真实运行**
                                                    （第 1 页 200 条：39 missing / 161 非空 / 其余 0）
相关性诊断入口 missing schedule correlation（2B-2C1C） ✅ 代码已完成
                                                    ✅ Reviewer 已批准并 merge
                                                    ✅ **已由负责人真实运行**
                                                    ✅ **真实聚合结果已回填**（见 §4.7.1 / 下表）
G11 业务语义最小核验（2B-2C1D，人工 UI，n = 2）      ✅ **已完成**（两条候选在官方 UI 中均为普通
                                                    教学班行；时间 / 周次 / 地点空白、无状态文字）
契约缺口 DG-07（CourseOffering 空 meetings）     ✅ **IMPLEMENTED / REVIEWED**
                                                    （DG-07A / B / C / D 全部完成，
                                                    Data Gate 已恢复 CLOSED）
契约迁移 DG-07A                                 ✅ **已实施 / 已 merge**
                                                    （`meetings` `minItems: 1 → 0`，`required` 不变；
                                                    Pydantic 镜像 + 接口语义 + 契约级测试已同步）
Course Data 空 meetings 归一化 DG-07B             ✅ **已实施 / REVIEWED**
                                                    （**唯一**来源形态 = Raw row 没有
                                                    `teachingTimePlaceStr` key；解析失败仍 fail closed；
                                                    缺排课信息的 row 不被跳过）
Planner unknown-schedule safety DG-07C            ✅ **已实施 / REVIEWED**
Frontend empty-meeting 展示 DG-07D                ✅ **已实施 / REVIEWED**
真实完整学期程序化采集                              ⏳ 未完成（**尚未**重新采集；DG-07 safety gate 已解除，
                                                    但仍须取得 complete snapshot 后才能进入真实产品联调）
完整 semester snapshot                              ⏳ 未取得
```

### 真实 smoke run 已确认的事实

| 事实 | 状态 |
|---|---|
| 在真正的「**全校开设课程**」独立模块内发起 same-origin 请求 | ✅ **成功** |
| 第 1 页响应成功进入 Collector | ✅ **成功** |
| **认证不再是当前 blocker** | ✅ 已确认 |
| 第 1 页 `total_rows` | ✅ **200**（同页 `reported_total = 6892`） |
| 第 1 页 `teachingTimePlaceStr` = `missing` | ✅ **39** |
| 第 1 页 `teachingTimePlaceStr` = `non_empty_string` | ✅ **161** |
| 第 1 页 `null` / `empty_string` / `other_type` | ✅ **均为 0** |
| 第 1 页 missing 占比 | **39 / 200 = 19.5%**，⚠️ **只描述这 200 条样本，不得外推** |
| 当前 `collect()` 的处置 | ✅ **DG-07B 起可正常完成**：缺属性 → `meetings = []`；
  字段存在但不可用 → 仍 fail closed |
| 是否已生成真实 Capture Bundle | ❌ **尚未生成** |
| 是否已取得 complete semester snapshot | ❌ **尚未取得** |

### C1C 真实相关性诊断结果（已回填）

**出处**：仍为 `OFFERING-002`；**负责人手动执行**
`diagnoseMissingScheduleCorrelation({ semester: "2026-1" })`（只请求第 1 页一次）。
`total_rows = 200`；`compared_rows = 200`；`ungrouped_rows = 0`。

| 字段 | `missing` 组（39 条） | `non_empty_string` 组（161 条） |
|---|---|---|
| `timePlaceId`（A 类） | `missing 38` / `non_empty_string 1` | `non_empty_string 161` |
| `limitNumber`（A 类） | `number 39` | `number 161` |
| `selectedNumber`（A 类） | `number 39` | `number 161` |
| `weekDay`（B 类） | `missing 38` / `distinct_count 1` | `missing 12` / `distinct_count 49` / `values_suppressed = true` |
| `openClass`（B 类） | 同一取值 × 39 | **同一取值 × 161（与 missing 组完全相同）** |
| `teachProgressSubmitState`（B 类） | 2 个分类：38 / 1 | **同一组 2 个分类**：143 / 18 |
| `courseCategoryName`（B 类） | `distinct_count 3`：12 / 2 / 25 | `distinct_count 5`：68 / 19 / 68 / 3 / 3 |
| `examMode`（B 类） | 2 个分类：32 / 7 | **同一组 2 个分类**：110 / 51 |
| `openingUnitName`（B 类） | `distinct_count 11` | `distinct_count 27`（suppressed） |

**可以说的**：

- 39 条缺 `teachingTimePlaceStr` 的记录**并非整条记录普遍残缺**：
  `limitNumber` / `selectedNumber` 在 39 条中**均为数值型且完整存在**；
- **结构差异集中在排课相关字段**：`timePlaceId` 38/39 缺失 vs 161/161 存在；
  `weekDay` 38/39 缺失 vs 12/161 缺失；
- **`openClass` 两组实际取值完全一致** → 该字段**不能区分两组**；
- `teachProgressSubmitState` / `examMode` / `courseCategoryName`
  **均未发现只属于 `missing` 组的独占分类**
  （`courseCategoryName` 的 3 个分类**全部出现在** present 组，后者另有 2 个）。

**⛔ 不能说的**：

- ⛔ 只有**边际计数、无逐 row 交叉证据** → **不得**写成
  "39 条中的 38 条**同时**缺 `weekDay` 和 `timePlaceId`"；
- ⛔ **不登记任何真实 categorical 取值 / 分类名 / 单位名**（`openClass` /
  `teachProgressSubmitState` / `examMode` 的真实值**一律不落文档**）；
- ⛔ **不推断业务语义**、⛔ **不声称 G11 resolved**。

> **G11 现状**：**business semantics partially evidenced;
> contract gap candidate identified;
> architecture decision pending**
> （结构层取证已大幅收窄；业务语义获得**部分界面证据**（C1D，**n = 2**）；
> 契约缺口候选 **`DG-07`** 已提交，**待架构裁决**）。
> ⛔ **仍不得写 resolved**。

### C1D 人工界面最小核验（已回填，**n = 2**）

**取证方式**：Architecture Lead 指导定位候选 → **负责人本人**在「**全校开设课程**」UI 人工检查
（Builder **未访问学校系统**）。候选条件：`teachingTimePlaceStr` / `weekDay` / `timePlaceId`
**三者均不存在**。

| 人工检查项 | candidate A | candidate B |
|---|---|---|
| UI 中能够正常找到 | 是 | 是 |
| 上课时间 / 周次 / 地点 | **完全空白** | **完全空白** |
| 明确状态文字 | **无** | **无** |
| 容量 / 已选人数等普通教学班信息 | 正常显示 | 正常显示 |
| 与普通教学班为同一种表格行 | 是 | 是 |
| 详情 / tooltip 解释空白原因 | **无** | **无** |

**可以说的**：**已人工核验的 2 条典型候选，在学校 UI 中均作为普通教学班记录展示，
但时间 / 周次 / 地点位置为空**。

**⛔ 不能说的**：

- ⛔ 不得写成"**39 条全部如此**"（**n = 2**，不能代表全部 39 条）；
- ⛔ 不得命名为任何业务状态（**未排课课程 / 未排课教学班 / 时间待定课程 / 异步课程 /
  无需排课课程 / 停开课程 / 无效教学班 / 自由时间教学班**）；
- ⛔ 不登记候选的**课程名 / 课程号 / 教学班号**，也不外推 39/200 到 6892。

**由 C1B / C1C / C1D 支持的事实判断**：当前证据**已不足以支持**"缺 schedule 字段的记录
都是无效记录、应直接过滤"（39 条仍有完整容量 / 已选人数信息；`openClass` 无法区分两组；
其它 categorical 无 missing 组独占值；2 条候选在官方 UI 中仍是普通教学班行）
→ **契约表达问题成立**：现行强制 ≥1 `Meeting` **无法表示**"官方教学班记录存在，
但**当前来源快照没有可用排课信息**"这一已观察状态。
⚠️ 这是**契约表达问题**，**不是对学校业务状态的命名**。

**→ 契约缺口 `DG-07`**（`docs/data/DATA_GATE_DECISIONS.md` §17）：
状态 **`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**
（**2026-10-01 由项目负责人批准**；⛔ **本轮未实施** —— 见 §17.5.1 裁决）。

⚠️ **"WITH MODIFICATION" 的含义**：**不是**只批准把 `meetings` 的 `minItems: 1 → 0`，
而是 **Schema 放宽** 与下面两条不变量**必须同时成立**：

1. **fail-closed 不变量**（§17.12.1）：`meetings = []` **只能**表示**来源层没有提供**
   可形成 `Meeting` 的排课信息，⛔ **不得**作为 parser / importer / normalizer
   **解析失败的 fallback**；**初始边界按现有证据写死** —— ✅ 唯一可映射为 `[]` 的形态是
   **`teachingTimePlaceStr` 属性不存在**；⛔ `null` / `empty_string` / `other_type` /
   非空但格式无法解析 / malformed segment / parser / importer / normalization 异常
   **一律继续 fail closed**；⛔ 禁止 `try: parse … except: meetings = []`；
2. **Planner 安全规则覆盖 `offerings` 与 `current_schedule`**（§17.9）：
   两者同为公共类型 `CourseOffering[]`；**对其中任何 `meetings = []` 的 `CourseOffering`，
   schedule 都视为 unknown**；**若 `current_schedule` 中存在 `meetings = []`，
   不得把其它候选声明为"已验证与当前课表无时间冲突"**，
   最多只能判断"**与已知时间段未发现冲突**"，**整体时间冲突状态仍含未知部分**。

**⛔ 本轮未批准 / 仍 deferred**：不新增 `schedule_status` / `schedule_known` /
`schedule_state`；`PlanResult.status` 取值、`unresolved[].type` 最终命名、
`missing_schedule` 是否正式采用**仍留到 Planner Implementation Review**
（当前 **`missing_schedule` = `candidate convention only`**）。

**⛔ Data Gate 仍保持 Reopened（未 CLOSED）**：关闭前置条件见
`DATA_GATE_DECISIONS.md` §17.15（Contract Migration + Course Data + Planner safety +
Frontend / Mock + tests，且须经 Reviewer 验收）；**本轮未开始任何实施阶段**。

> ⚠️ **缺失字段的业务含义尚未确认**：现有证据**只**证明"第 1 页存在 39 条这样的 row"，
> 且说明它**不是单条孤立现象**。
> **不得**据此写成"缺排课""未排课课程""未排课教学班""时间待定""异步课程""无需排课"
> "异常数据""暂无教室"等任何业务结论。
> ⚠️ **39/200 不可外推**：不得写成"全校 19.5%""6892 条中约有多少条"。
>
> ⚠️ **模块导航**：「**选课**」与「**全校开设课程**」是**两个独立模块**，
> 不存在"选课 → 全校开设课程"的层级关系。

### SYSU 分页参数人工验证结论（已验证事实）

| 项 | 已验证结果 |
|---|---|
| `pageNo=1` | 请求成功（`code=200`，`total=6892`） |
| `pageNo=2` | 请求成功（`code=200`，`total=6892`） |
| `pageSize=200` | 请求成功 |
| 单页上限 | 负责人确认 **SYSU 单页最大支持 200** |
| `total` 稳定性 | **已验证前两页** `total` 均为 **6892**（即在这两页范围内保持稳定） |

> ⚠️ **以上仅覆盖已验证的前两页**，**不代表**整学期分页已经跑完。
> ⚠️ 本次**未单独记录** `rows.length`（单页实际返回行数），因此**不声称**已确认每页满 200 行。
> ⚠️ 这些是 **SYSU 专有取值**，属于**后续 Transport 的配置**，
> **不会硬编码进 Pagination Core**（核心保持与具体学校无关、无默认值）。

## 已完成

### 结构诊断入口（Phase 2B-2C1B，已完成并由负责人真实运行）
位置：`tools/sysu_course_offering_collector.js`（在**现有**采集器内新增，不新建 Transport 文件）

| 项 | 内容 |
|---|---|
| 入口 | `window.XuehangSysuCollector.diagnoseSchedulePresence({ semester: "2026-1" })` —— **必须由用户显式调用** |
| 纯函数 | `window.XuehangSysuCollector.summarizeSchedulePresence(rows)`（便于源码级测试） |
| 请求范围 | **固定** `pageNo = DIAGNOSTIC_PAGE_NO`（**1**）、`pageSize = DIAGNOSTIC_PAGE_SIZE`（**200**）、`total = true`；**只发 1 次请求** |
| 不具备的能力 | ⛔ 无 `maxPages`、⛔ 无 `firstPageNo`、⛔ 无循环分页、⛔ 无重试、⛔ 无并发 |
| 复用 | hostname guard / same-origin 请求 / 既有取页函数的 HTTP · JSON · code · total · rows 校验（**不复制认证逻辑**） |
| 统计口径 | 每条 row 归入**互斥且穷尽**的一类：`missing`（字段不存在）/ `null` / `empty_string`（trim 后为空）/ `non_empty_string` / `other_type`（存在但既非 null 也非字符串）；**五类之和 == `total_rows`** |
| 返回值 | 只有聚合统计：`semester` / `page_no` / `page_size` / `reported_total` / `total_rows`（= `data.rows.length`，**不写死**）/ `teachingTimePlaceStr{...}` |
| ⛔ 不返回 | rows、row 下标、`courseNum` / `courseName` / `classNumber` / 教师 / 教室 / 原文 / 内部 ID |
| ⛔ 不产生 | **不生成 Capture Bundle**、不做字段最小化、不做教师脱敏、不调用 `toJson` |
| ⛔ 不改行为 | `collect()` 遇缺字段仍 **fail closed**；诊断**不**跳过、**不**补空、**不**造占位 `Meeting`、**不**标记 complete |
| ⛔ 本轮不改契约 | `CourseOffering.meetings` 的 `minItems = 1` **保持不变**；诊断结果**不**触发任何 Schema 变更 |

> **定位**：诊断是**取证**，**不是** workaround。若结论表明现有契约覆盖不了真实数据，
> **下一轮再走正式 `【接口变更请求】`**。

#### Reviewer 修复（2026-10-01，6 项）

| # | 修复 | 结果 |
|---|---|---|
| 1 | 把「全校开设课程」独立模块的真实结构 smoke **登记为 `OFFERING-002`** | `docs/data/DATA_SOURCE_REGISTRY.md`：新增登记表行、**新增 §4.1 明细块**、§6 汇总同步为 **已登记 18 ｜ Authenticated Official 5 ｜ Confirmed 8**（最近更新 2026-10-01）、追加变更记录；**只登记汇总事实，无 Raw row** |
| 2 | **删除"第 1 页第 N 条"这类不成立的精确条数表述**（原写法来自 JS 0-based `rowIndex`） | 全部改为"**第 1 页至少 1 条** row 缺少 `teachingTimePlaceStr`"，并显式注明**只登记"至少 1 条"、不登记精确条数**（`status/*`、`worklogs/*`、缺口报告） |
| 3 | 给 **G11** 补**样本出处** | G11 表行与 **§4.7** 均写明 **样本出处：`OFFERING-002`** |
| 4 | 缺口报告表头补齐证据阶段 | `分析框架 ＋ 四轮真实材料验证` → `分析框架 ＋ 四轮真实材料验证 ＋ **Phase 2B-2C1B 真实 smoke 结构证据**` |
| 5 | **错误信息行号口径改为 1-based** | `collect()` 调用点改为 `minimizeRow(row, currentPageNo, rowIndex + 1)`；`minimizeRow` / `redactTeachingTimePlace` / `redactSegmentTeacher` 的第三参数统一改名为 `humanRowNo`，JSDoc 写明"**从 1 开始的人类行号**，只用于错误信息"（`map` 的 0-based 下标 **+ 1**）。⛔ **未改** fail-closed 行为、字段检查、数据行为、诊断统计 |
| 6 | 新增守卫测试锁住行号口径 | `test_collector_reports_one_based_human_row_numbers`（调用点必须含 `rowIndex + 1`、不得出现裸下标透传、文档必须写明"从 1 开始"）与 `test_collector_row_number_is_only_for_messages`（行号**不得**进入最小化结果 / 数据字段） |

- 回归：`cd backend && python -m pytest` → **526 collected / 2 skipped（= 524 passed）**，exit 0；
  `node --check tools/sysu_course_offering_collector.js` → exit 0；
- ⛔ 本轮修复**未改**任何公共契约（`schemas/` / `docs/interfaces/` 未修改），
  **未发起任何真实 SYSU 请求**（实际请求数：**0**），**未生成真实 Capture Bundle**。

### 相关性诊断入口（Phase 2B-2C1C，本轮）
位置：`tools/sysu_course_offering_collector.js`（在**现有**采集器内新增，**不新建** Transport 文件）

**唯一目标**：在**第 1 页同一份样本**内，对 `missing` 组与 `non_empty_string` 组
做**已有真实字段**的**聚合结构对照**，用来判断"缺该字段的 row 是否表现出**一致的结构特征**"。
⛔ **不判断业务含义**、⛔ **不是 workaround**、⛔ **不改契约**。

| 项 | 内容 |
|---|---|
| 入口 | `window.XuehangSysuCollector.diagnoseMissingScheduleCorrelation({ semester: "2026-1" })` —— **必须由用户显式调用**，也是 C1C **唯一**暴露到全局的入口 |
| 内部纯函数（**不暴露**） | `classifySchedulePresence` / `summarizeFieldShape` / `summarizeCategoricalValues` 均为 **IIFE 内部实现**，**不出现在 `window.XuehangSysuCollector`**（`summarizeCategoricalValues` 是**任意字段**的 generic summarizer，公开即可绕过 C1C 字段 allowlist） |
| 请求范围 | **固定** `pageNo = CORRELATION_PAGE_NO`（= `DIAGNOSTIC_PAGE_NO` = **1**）、`pageSize = CORRELATION_PAGE_SIZE`（= `DIAGNOSTIC_PAGE_SIZE` = **200**）；**只发 1 次请求** |
| 参数限制 | **严格白名单**：`Object.keys(opts)` 里**只允许** `semester`；任何其它 own key（`pageSize` / `pageNo` / `firstPageNo` / `maxPages` / `delayMs` / `retry` 或任意未知字段如 `foo` / `fields`）都在**发请求之前** fail closed；⛔ 不采用"已知参数黑名单"；⛔ 失败信息**不回显**调用方提供的键名 |
| 不具备的能力 | ⛔ 无分页循环、⛔ 无重试、⛔ 无并发、⛔ 无第二次请求、⛔ 不复制 `fetch()` |
| 复用 | hostname guard / same-origin 请求 / 既有 `requestPage()` 的 HTTP · JSON · code · total · rows 校验 |
| 分组 | `schedule_presence` 保留**五桶**；只比较 `missing` 与 `non_empty_string`；`ungrouped_rows = null + empty_string + other_type`，⛔ **不**塞进任何一组 |
| A 类字段（Structural-only） | `timePlaceId` / `limitNumber` / `selectedNumber`；**只做存在性 / 类型统计，不返回具体值**（无 value list、无 distinct 计数） |
| B 类字段（Categorical） | `weekDay` / `openClass` / `teachProgressSubmitState` / `courseCategoryName` / `examMode` / `openingUnitName` |
| 值的安全格式 | `{ type: "number", value: "0", count: 32 }`：**值序列化为字符串、保留原始类型**；`missing` / `null` / `empty_string` / `other_type` **单独归类，不进入 value list** |
| 分类值的返回口径（⚠️ 注意） | **distinct ≤ 20 时**：**会返回聚合后的原始标量分类值 + 出现次数**（`values[]`）—— 这是本诊断**有意**返回的信息，用于观察两组是否分群；**distinct > 20 时**：`values_suppressed = true`、**`values` 全部 suppression**（`values = []`） |
| 高基数安全阀 | `MAX_DISTINCT_VALUES = 20`（**诊断输出安全阀，不是 SYSU 参数**）：⛔ **不返回前 N 个 / 随机 N 个 / 最常见 N 个**（排序与出现次数无关） |
| 计数不变量 | 五桶之和 == `total_rows`；两组之和 == `compared_rows`；`compared_rows + ungrouped_rows == total_rows`；每个字段自身的统计加总 == 该组 `total`；⛔ **任一不成立即整体失败，绝不静默丢 row** |
| ⛔ 不返回 | **Raw row**、逐行数据、row 下标、课程 / 教学班标识（`courseNum` / `courseName` / `classNumber`）、教师、教室、`teachingTimePlaceStr` **原文**、内部 ID / `readObj` |
| ⛔ 不产生 | **不生成 Capture Bundle**、不落盘、不写 `localStorage` / `IndexedDB`、不调用 `toJson` |
| ⛔ 不改行为 | `collect()` 遇缺字段仍 **fail closed**；2B-2C1B 的 `diagnoseSchedulePresence()` **行为保持不变**（两个入口**并列**，职责不同） |
| ⛔ 本轮不改契约 | `CourseOffering.meetings` 的 `minItems = 1` **保持不变**；诊断结果**不**触发任何 Schema 变更 |

> ⚠️ **返回内容的准确口径（不得写成"只含计数与类型、不含取值"）**：
>
> 1. **不返回** Raw row / 逐行数据 / 课程与教学班标识 / 教师 / 教室 /
>    `teachingTimePlaceStr` 原文；
> 2. **Structural-only 字段不返回具体值**（只有存在性 / 类型计数）；
> 3. **Categorical 字段在 `distinct <= 20` 时，会返回聚合后的原始标量分类值 + `count`**
>    （例如 `{ type: "number", value: "0", count: 32 }`）；
> 4. **`distinct > 20` 时 `values` 全部 suppression**（`values = []`）。
>
> ✅ **真实结果已由负责人手动执行并回填**（见上方「C1C 真实相关性诊断结果」与
> `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` §4.7.1）；
> **Builder 本轮实际 SYSU 请求数 = 0**（本轮仅为**文档证据同步**）。
>
> ⚠️ 对 `openClass` / `teachProgressSubmitState` / `weekDay` 等字段，
> 只允许写"**原始值 X 在 missing 组出现 N 次 / 在 non_empty_string 组出现 M 次**"，
> ⛔ **禁止解释**它们的业务含义（例如"0 表示…"），也⛔ **禁止**据此补 `Meeting`、
> 推断地点、判断是否应排除或是否应进入 Planner。
>
> ⚠️ **2B-2C1B 的"不登记精确条数"限制由本轮解除**（负责人已手动取得并给出第 1 页聚合计数），
> 但**范围仍严格限定在第 1 页 200 条样本**，**不得外推**。

### 浏览器端授权采集器 + Capture Bridge（Phase 2B-2C1A）
**只做"显式触发的浏览器采集 + 本地回放桥"，不接 Integration / Planner / API / 前端产品 UI。**

| 产出 | 内容 |
|---|---|
| `tools/sysu_course_offering_collector.js` | 浏览器端采集器：`window.XuehangSysuCollector.collect({...})` **必须由用户显式调用** |
| `backend/app/course_data/captured_pages.py` | `CapturedPagesFetcher`、`collect_captured_pages_snapshot()`、`load_capture_bundle()`、`validate_capture_bundle()` |
| `backend/tests/test_course_data_captured_pages.py` | Capture Bridge 测试（人工虚构 bundle） |
| `backend/tests/test_sysu_collector_guard.py` | 采集器**静态安全守卫**（源码级检查） |

**浏览器端采集器（SYSU-specific Transport）**：

- ⛔ **加载脚本不自动请求**：无顶层调用、无定时轮询、无并发；唯一入口是显式 `collect()`
- ✅ **hostname guard**：`window.location.hostname` 必须是 `jwxt.sysu.edu.cn`，否则直接失败
- ✅ **分页参数（SYSU 已验证）**：`firstPageNo` **锁定为 `1`**（传入其它起始页**在发请求之前**直接失败；
  通用多起始页能力留在 backend 分页核心，不在这里放开）、`pageSize=200`（单页上限 200，有校验）
- ✅ **限速与安全阀**：`DEFAULT_DELAY_MS=30000` / `MIN_DELAY_MS=30000`
  （**同一 endpoint 的所有相邻请求**下限）+ **全局 batch pacing**
  `MAX_REQUESTS_PER_BATCH=5` / `BATCH_COOLDOWN_MS=300000`
  （见下方"全局 batch pacing"小节）；
  `DEFAULT_MAX_PAGES=2`、`ABSOLUTE_MAX_PAGES=50`
  （50 是**客户端安全上限**，不是学校系统限制）；`maxPages > 2` 时必须 `window.confirm()` 确认，取消则 **0 个请求**
- ✅ **严格串行**：一页一页取；⛔ 不并发、⛔ 不预取
- ✅ **认证边界**：`credentials: "same-origin"`，认证状态完全交给浏览器；
  ⛔ 不读取 / 不保存 / 不打印 / 不导出任何浏览器端认证状态；遇到 401 / 403 / 非 JSON（疑似登录页）立即停止
- ✅ **每页校验**：HTTP 成功、JSON 可解析、`code === 200`、`data` 是对象、`total` 非负整数、`rows` 是数组
- ✅ **停止规则**：第一页记 `expectedTotal`；后续 `total` 变化 → 停止失败；累计 > total → 失败；
  达到 total 前出现空页 → 失败；累计 == total → 不再请求；达到 `maxPages` 仍未取满 → 正常停止（**不自行声称 complete**）
- ✅ **数据最小化**：每条 row **只保留 8 个字段**（`courseNum` / `courseName` / `classNumber` / `yearTerm` /
  `score` / `limitNumber` / `selectedNumber` / `teachingTimePlaceStr`）；
  ⛔ 明确丢弃内部 ID 与暂缓字段（`class_ID` / `sumClassesID` / `sumClassesNum` / `courseId` /
  `outLineId` / `outlineTypeNum` / `openingUnitName` / `courseCategoryName` / `teachingName` /
  `examMode` / `openingSchoolName` / `readObj` / `teachProgressSubmitState` / `weekDay` /
  `timePlaceId` / `openClass`）
- ✅ **教师脱敏**：`teachingTimePlaceStr` 内 segment 的 teacher 替换为 `REDACTED`
  （5 字段取第 4 项、6 字段取第 5 项）；保持 segment 顺序、`/`、`,`、**最多一个** trailing comma、
  location / weeks / weekday / sections / activity 原文；
  ⛔ **替换前必须验证原 teacher 非空**：空 / 非字符串 teacher → **整体失败**，
  **不得**用 `REDACTED` 静默掩盖（那会让下游 Python parser 误以为记录合法）；
  错误信息**不回显** teacher 取值；
  ⛔ 非 5/6 字段、多个 trailing comma、中间空 segment → **整体失败，不生成 bundle**
- ✅ **opaque 槽位脱敏（4 字段 non-concrete layout B；Architecture Review 裁定）**：
  已批准 `weeks | location | **opaque** | activity` 中的第 3 项替换为 `REDACTED_OPAQUE`；
  ⛔ **只**对**精确** Layout B（f2 是**严格** location：`>= 3` 个非空 `-` 分段）生效，
  ⛔ **不泛化**到所有 4 字段（concrete `weeks/weekday/sections/activity` 与未归类 4 字段**保持原状**）；
  ⛔ **不解释** opaque 槽位（⛔ 不称其为 teacher / 地点 / 活动 / 其它业务字段），
  ⛔ 不做姓名 / CJK / 长度启发式，⛔ 不注入 row 级 `teachingName`；
  ⛔ **替换前必须验证原 opaque 非空**（空 / 非字符串 → **整体失败**，⛔ 不用占位符掩盖）；
  错误信息**不回显**该取值；
  ⚠️ 两个占位符**互相独立**：`REDACTED`（teacher）与 `REDACTED_OPAQUE`（opaque），
  ⛔ 不可互相替代、⛔ 不可前缀包含
- ✅ **结果导出**：`toJson(result)` 输出的**顶层就是裸 Capture Bundle**
  （`format` / `semester` / `first_page_no` / `page_size` / `pages`），
  可直接交给 Python 的 `load_capture_bundle(...)`；
  ⛔ 采集被取消（`cancelled=true`）或没有 bundle 时 `toJson()` **失败，不生成伪 bundle**

**Capture Bundle（Course Data 内部交换格式，v1）**：

```text
{
  "format": "sysu-opening-courses-capture-v1",
  "semester": "2026-1",
  "first_page_no": 1,
  "page_size": 200,
  "pages": [ { "page_no": 1, "response": { "code": 200, "data": { "total": ..., "rows": [...] } } } ]
}
```

- ⛔ 不是公共 Schema（不进 `/schemas/`、不进 `/docs/interfaces/`）；
- ⛔ **不含** `source`（由 Python 调用方显式给出）、**不含**认证 / 会话信息、
  **不含**用户标识、**不含**姓名学号、**不含**内部长 ID、**不含**教师姓名；
- ⚠️ 即使已脱敏，它仍是 **Real Sanitized Capture**：
  **不得提交 Git、不得放入 `mock_data/`、不得作为测试 fixture、不得复制进 docs / worklog**。
  采集器**代码**可以进 Git；采集器**实际产出的 JSON 绝不进 Git**。

**Python Capture Bridge（零网络）**：

- `CapturedPagesFetcher`：**只回放** bundle 中已捕获的页；结构上满足 `OpeningCoursesPageFetcher`，
  **不继承、不修改** Protocol；请求的 `semester` / `page_size` / `page_no` 与 bundle 不一致时直接失败；
- bundle 校验：`format` 必须匹配、`semester` 非空、`first_page_no ≥ 0`、`page_size ≥ 1`、`pages` 非空数组、
  每个 `page_no` 唯一且**从 `first_page_no` 起连续**（`1,3` / `2,3` / 重复 → **失败，不排序修复**）；
- `collect_captured_pages_snapshot(bundle, *, source)`：
  **复用** `collect_opening_courses_snapshot()`，`max_pages = len(pages)`；
  **不重新实现** completeness —— 2 页 smoke capture 在未取满时必然是 **partial**，
  累计 == total 时才是 **complete**；
- `load_capture_bundle(path)`：只读**调用方显式给出**的本地 UTF-8 JSON（stdlib `json`，**无新依赖**），
  **无默认路径、不扫描目录、不复制进仓库**；
- 错误信息只输出**结构性**信息（page_no / 字段名），**不回显** Raw row、`teachingTimePlaceStr` 原文或 teacher。

> ⚠️ **本轮 Builder 未执行任何真实采集**：采集器只由**静态守卫测试**检查，
> Python 侧只由**人工虚构 bundle** 驱动；**未登录 SYSU、未发任何真实请求、未生成任何真实数据文件**。

### 分页采集核心（Phase 2B-2C0）
位置：`backend/app/course_data/pagination.py`（**内部实现 / 内部接口**）

| 项 | 内容 |
|---|---|
| 内部 Protocol | `OpeningCoursesPageFetcher.fetch_page(*, semester, page_no, page_size) -> Mapping`<br>⛔ **不是** `/docs/interfaces` 公共接口，**不加入** Integration |
| 核心函数 | `collect_opening_courses_snapshot(fetcher, *, semester, source, page_size, first_page_no, max_pages) -> OfferingSnapshot` |
| 取页方式 | **严格串行**：`first_page_no`、`first_page_no + 1`、…；⛔ 不并发、⛔ 不预取下一页 |
| 逐页处理 | 复用**已审核通过的** `import_opening_courses_response(..., completeness="partial")`；**不重写** parser / normalizer |
| total 一致性 | 第一页的 `reported_total` 记为 `expected_total`；后续每页必须**完全相等**；<br>⛔ 不采用最新 / 最大 / 最小值（变化即 FAIL） |
| complete 条件 | 所有页成功解析 + 每页 total 一致 + 累计 `loaded_count == expected_total` + 无重复教学班（由 `OfferingSnapshot` 判定）+ 无中途空页 + 无请求错误 |
| partial 条件 | 达到 `max_pages`（**安全阀**，不是"完整页数"）仍未取满 → `completeness="partial"`，`reported_total` 如实记录 |
| 提前空页 | 在达到 `expected_total` 之前出现 `loaded_count == 0` → **FAIL**（分页提前停滞） |
| 累计超限 | `accumulated_count > expected_total` → **FAIL** |
| 跨页重复 | 分页器**不自行去重**（不 `set()` / 不建 dict / 不留第一条或最后一条）→ 交由 `OfferingSnapshot` 的 `(semester, course_id, class_id)` 判定 → **FAIL** |
| 顺序 | 按**原页序 + 原行序**累积，不重排 |
| 错误策略 | fetcher 异常 / 某页解析失败 **原样向上抛**；⛔ 不 retry、⛔ 不 fallback、⛔ 不跳页、⛔ 不返回"看起来差不多"的 complete |
| 参数 | `semester` / `source` 非空字符串；`page_size ≥ 1`；`first_page_no ≥ 0`；`max_pages ≥ 1`（`bool` 不算整数）；**非法即 fail closed** |
| 分页参数默认值 | ⛔ **本核心不提供默认值**（保持与具体学校无关），全部由调用方显式传入；<br>SYSU 的实际取值（起始页码 1、单页上限 200）属**后续 Transport 配置**，**不硬编码进核心** |
| 取满后 | **不再**请求下一页 |
| `total == 0` | 第一页 `total=0` + 空 rows → **complete**（`loaded_count = 0`），且**不再**请求下一页 |
| `partial` 用途限制 | ⛔ **禁止**把 `partial` 包成生产 `SnapshotCourseDataProvider` 接进 Integration；<br>`partial` 仅用于**获取规模验证 / 小范围验证 / parser 与 normalizer 验证**，**不进入 Planner 产品链路** |

### D5 技术侦察（Phase 2B-0D）
- 记录见 `docs/data/SYSU_COURSE_OFFERING_RECON.md`（`OFFERING-001`）；
- 确认了查询入口的**结构**与一个课程的真实多 segment 现象；
- **Raw 响应、教师姓名、内部长 ID 取值一律不入库**。

### 契约（Data Gate）
- 公共输出为 `schemas/course_offering.schema.json`；
- **DG-01** 建立了 `CourseOffering.meetings[]` 的**嵌套结构**（一个教学班不再等于一个时间段）；
- **DG-07A 起**，**每个 `CourseOffering` 可以包含 0..N 个 `Meeting`**
  （`meetings` 仍必填，`minItems: 0`）；
- 一个教学班 = 一个 `CourseOffering`；
  `meetings[]` = **当前来源快照中能够形成公共 `Meeting` 的全部已知排课段**；
- `meetings = []` **仅**表示**当前来源快照没有可用排课信息**：
  ⛔ **不表示无时间占用**，⛔ **也不表示 conflict-free**；

### Schedule parser + local import adapter（Phase 2B-2B，本轮）
位置：`backend/app/course_data/`（**内部实现，不是跨模块公共契约**）

| 模块 | 内容 |
|---|---|
| `schedule_parser.py` | `parse_teaching_time_place(text)`、`ParsedScheduleSegment`、`extract_meetings()`、`parse_weekday()`、`parse_sections()` |
| `importer.py` | `import_opening_courses_response(payload, *, semester, source, completeness)` |

**parser（依据私密脱敏样本 + **2026-1 全量采集首轮真实报错证据**；样本本身不入 Git）**：

```text
segment separator = ","      field separator = "/"

4 字段（无地点、无教师）：weeks / weekday / sections / activity
5 字段 A（有地点、无教师）：weeks / weekday / sections / location / activity
5 字段 B（无地点、有教师）：weeks / weekday / sections / teacher / activity
6 字段（有地点、有教师）：weeks / weekday / sections / location / teacher / activity
4 字段 layout B（**opaque**；Architecture Review 裁定）：
                          weeks / location / REDACTED_OPAQUE / activity
                          第 2 项是 **location**（不是 weekday），第 3 项是 **opaque / unmodeled**
                          ⇒ 没有 weekday / sections ⇒ **不生成 Meeting**（`meetings = []`）
```

⚠️ **2026-1 真实证据确认：teacher 并不总是在 `teachingTimePlaceStr` 中出现**
（某条真实记录由 3 个 segment 组成：5 字段 A / 4 字段 / 5 字段 A）。
教师信息可能存在于 row 的其它独立字段中，因此
⛔ **不得再把第 4 / 5 字段无条件当成 teacher** —— 那会把 location 静默错读成 teacher，
使 `Meeting.campus / classroom` 变成 `None`（**静默错误解释**）。

**5 字段的判别规则**（**严格三态**，唯一允许的判别方式）：只看 `fields[3]`——

```text
无 "-"                → teacher   → 5 字段 B（无地点、有教师）
>= 3 个非空 "-" 分段   → location  → 5 字段 A（有地点、无教师）
其余二义形态           → 一律 fail closed（⛔ 不猜）
```

⛔ 不根据 `courseName` / 学院 / `teachingName` 猜；⛔ 不引入模糊匹配；
⛔ 二义形态**既不默认当 teacher、也不默认当 location**。
⚠️ **不复用**宽松的通用 grammar：`_is_location_token()` 只要"非空园区 + `-` + 非空教室"
就成立，会把 `A-B` 这种两段 token 判成 location，而那同样可能是含 `-` 的 teacher。
⚠️ **本轮未收紧 6 字段**（其语义已由字段数确定），因此 5 / 6 字段存在已知不对称性。

- ✅ **最多一个**末尾逗号：单个末尾逗号产生的空 segment **忽略**；
  ⛔ `seg,,` / `seg,,,`（多个末尾逗号）**失败**；
- ⛔ 中间空 segment（`seg1,,seg2`）**失败**，不静默忽略；
- ⛔ 字段数只接受 **4 / 5 / 6**，其它（3、7+）fail closed；
- **星期**：只接受 `星期一` … `星期日`；⛔ **`weekday` 一律来自 segment 自身**——
  样本显示 Raw `weekDay` 的顺序**不能安全假设**与 segment 一致，因此**完全不使用**它；
  **错误只给安全稳定分类**（⛔ 不回显 raw token，2026-10-05 裁定）：
  `unsupported_weekday_type` / `unsupported_weekday_shape` / `unsupported_weekday_value`
  （非字符串 → `type`；去空白后为空 → `shape`；不在白名单 → `value`）；
  ⛔ **未重构全局异常系统**（分类写在 message 的稳定 token 里）；
- **节次**：`第N-M节` 或 `第N-M节` + **已批准 suffix**，要求 `N ≥ 1` 且 **`M ≥ N`**
  （允许 `M == N`，如 `第4-4节`）：

  ```text
  已批准（Architecture Review 裁定，2026-1 east artifact 聚合证据）：
    第N-M节
    第N-M节校内(户外)     （east artifact 出现 173 次）
    第N-M节校外           （1 次）
    第N-M节线上           （11 次，**新确认**）
  ```

  - suffix 必须**精确命中**白名单字面量 + 整段锚定：⛔ 不用 `startswith`、⛔ 不用 `.*`、
    ⛔ 不把 `节` 之后的字符无条件 strip（`第5-6节校` / `第5-6节线上教学` /
    `第5-6节校内(户外)X` 一律拒绝）；
  - **sections suffix 是独立白名单**：⛔ `线上` **只**被批准出现在 sections 字段上，
    **weeks 字段的限定词白名单不被放宽**（仍只有 `校外` / `校内(户外)`）；
  - ⚠️ suffix **只用于白名单校验**：公共 `Meeting` 没有 qualifier 字段，
    因此⛔ 不新增公共字段、⛔ 也不存进内部 `schedule_qualifier`（校验后丢弃）；
  - ⛔ **未确证的 sections 形状仍保持 fail closed**（east artifact 上聚合计数 **49**，
    三个匿名模板 `C-CAC-CAN` × 30 / `C` × 10 / `C-C-CAN` × 9）；
  - **production 错误只给安全分类**（⛔ 不回显原始 token）：
    `unsupported_sections_suffix` / `unsupported_sections_shape` /
    `unsupported_sections_range`；
- **地点**：只按**第一个 `-`** 切 → `campus` = 第一段、`classroom` = 其余完整文本；
  ⛔ 不进一步猜 building / room；⛔ **`openingSchoolName` 不是 `campus` 的 fallback**；
- **teacher / activity**：`ParsedScheduleSegment.teacher` 类型为 **`str | None`**
  （真实证据已证明 segment 中 teacher 可以不存在，⛔ **不自动补占位 teacher**）；
  teacher 存在时仍必须为非空字符串，**保留在内部 `ParsedScheduleSegment`**；
  `extract_meetings()` 只把 `Meeting[]` 交给公共契约；
  ⛔ **meeting 级教师关联仍是 known deferred representation gap**，**未修改任何 Schema**；
- **⛔ 不自动补 teacher / location**：缺失就是缺失，保持 `None`；
- **不丢段、不合并、不排序**：输出顺序 == Raw 顺序。

**non-concrete segment（2026-1 真实证据确认）**：

```text
2 字段 plain    ：<weeks token> / activity               例如 1-17周 / 实验实践环节
2 字段 qualified：<weeks token><qualifier> / activity     例如 12-19周校外 / 实验实践环节
3 字段 plain    ：<weeks token> / teacher / activity      例如 1-17周 / 龙霞 / 实验实践环节
3 字段 qualified：<weeks token><qualifier> / teacher / activity
                                                        例如 16-16周校内(户外) / 龙霞 / 实验实践环节
5 字段 layout A ：weeks / weekday / location / REDACTED / activity（Architecture Review 裁定）
                ⚠️ 第 3 个字段是 **location** 而不是 sections ⇒ **没有 concrete sections**
```

**5 字段 non-concrete layout A**（Architecture Review 裁定；east artifact **39/39**）：

```text
weeks | weekday | location | REDACTED | activity
```

- **精确准入（五条全部满足才走这条路，否则落回原有路径继续 fail closed）**：

  ```text
  f1：现有 weeks parser（expand_weeks）成功
  f2：现有 weekday parser（parse_weekday）成功
  f3：现有 location 判别器（_classify_five_field_token）判定为 location（>= 3 个非空 '-' 分段）
  f4：**精确等于** collector 的 `REDACTED` 占位符（⛔ 无 startswith / 包含 / 通配 / 空白容忍）
  f5：现有 activity 规则（非空）通过
  ```

- ⛔ **不泛化**为"任意 5 字段不含 sections"；⛔ 不猜 teacher / location 语义；
  ⛔ **不重排字段**；⛔ 不新增公共 Schema；
- ⛔ **不生成 `Meeting`**（`meeting = None`）：该 layout **没有** concrete sections，
  公共 `Meeting` 需要的 `start_section` / `end_section` 无从取得；
- ✅ 复用**现有** `build_course_offering_from_non_concrete_schedule()` → `meetings = []`
  （⛔ **未新增** empty-meeting 路径）；✅ `schedule_weeks` / `teacher`（占位符）/ `activity` 保留；
- ⚠️ **语义仍是 `meetings = []` = schedule UNKNOWN**，⛔ **不表示** conflict-free、
  ⛔ 不表示无课、⛔ 不表示异步；
- ✅ **Layout B（4 字段 opaque）已按裁定实现 production 收口**（parser 侧，见下节）。

**4 字段 non-concrete layout B（opaque；Architecture Review 裁定；✅ 已实现）**：

```text
weeks | location | REDACTED_OPAQUE | activity
```

- **精确准入（四条全部满足才走这条路，否则落回原有 concrete 路径继续 fail closed）**：

  ```text
  f1：现有 weeks parser（expand_weeks）成功
  f2：现有**严格** location 判别器（_classify_five_field_token）判定为 location（>= 3 个非空 '-' 分段）
  f3：**精确等于** collector 的 REDACTED_OPAQUE 占位符（⛔ 无 strip / 前缀 / 通配 / 空白容忍）
  f4：现有 activity 规则（非空）通过
  ```

- ⛔ **不解释 opaque 槽位**：它**不是** teacher、**不是**地点、**不是**活动、
  **不是**任何其它业务字段；⛔ 不注入 row 级 `teachingName`；
  ⛔ 不做姓名 / CJK / 长度启发式；
- ⛔ **未脱敏的原始 opaque 取值不被接受**（只有采集器已吐出的 `REDACTED_OPAQUE` 才匹配）
  ⇒ 旧 artifact（含原始取值）在本 parser 下**必然**在 Layout B 处 fail closed ⇒ 需要 **East 重抓**；
- ⛔ **不生成 `Meeting`**（`meeting = None`）：该 layout 没有 weekday / sections；
- ✅ 复用**现有** `build_course_offering_from_non_concrete_schedule()` → `meetings = []`
  （⛔ **未新增** empty-meeting 路径）；✅ `schedule_weeks` / `activity` 保留；
  ⛔ `teacher` 保持 `None`（⛔ 不塞占位符冒充 teacher）；⛔ `schedule_qualifier` 保持 `None`；
- ⚠️ **语义仍是 `meetings = []` = schedule UNKNOWN**，⛔ **不表示** conflict-free、
  ⛔ 不表示无课、⛔ 不表示异步、⛔ 不表示可直接执行；
- ✅ **Layout A（5 字段）冻结**：⛔ 未改动其任何准入条件；
- ✅ **concrete 4 / 5 / 6 字段不变**：仍正常生成 `Meeting`；
- ⛔ **public Schema 未改**：`meetings` 仍复用既有 `minItems = 0` 契约。

**一次性 Layout B 诊断（零留存；Architecture Review 裁定 2026-10-05）**：

- **目的**：回答字段**角色**问题——Layout B 的 `f3` / `f4` 各自是什么；
- **真实运行历史**（负责人执行，east-campus 授权会话；Builder 不代跑）：

  ```text
  第 1 次：candidate = 10 / comparable = 10 / f3 == teachingName = 0 / f4_activity = 10
  第 2 次：candidate = 10 / comparable = 10
           f3 == teachingName = 0      f4 == teachingName = 0
           f3 ∈ 已确认 activity = 0     f4 ∈ 已确认 activity = 10
  ```

- ✅ **Architecture Review 正式确认：`f4 = activity`；`f3 = unknown`**（暂不修改 parser）；
- **位置**：`tools/sysu_course_offering_collector.js` 的 `diagnoseLayoutBCandidates()`，
  在 collector 对 raw response 做 `minimizeRow()` **之前**直接读 raw rows（⛔ 不经过脱敏 / 最小化）；
- **候选结构判定**（全部只看结构，⛔ 不比对课程名 / 教师名 / 学院，⛔ 无模糊匹配）：

  ```text
  4 fields
  f1 = 已确认 weeks（plain / 单周 / 双周 / 校外 / 校内(户外)）
  f2 = 已确认 location（复用现有判别器：>= 3 个非空 '-' 分段 ⇒ 同时排除 weekday）
  f3 ≠ 已确认 sections
  ```

- **已确认 activity 集合**（成员判定的唯一依据）：

  ```text
  2 字段：weeks(plain|+已确认 qualifier) / activity                     → 槽位 1
  3 字段：weeks(plain|+已确认 qualifier) / teacher / activity           → 槽位 2
  4 字段：weeks / weekday / sections / activity                        → 槽位 3
  5 字段 layout A：weeks / weekday / location / REDACTED / activity    → 槽位 4
  5 字段 concrete：weeks / weekday / sections / location-or-teacher / activity → 槽位 4
  6 字段：weeks / weekday / sections / location / teacher / activity   → 槽位 5
  ```

  - ✅ 集合取值**只在内存中构造**（⛔ 不返回 / ⛔ 不落盘 / ⛔ 不进 bundle / ⛔ 不写日志）；
  - ⛔ **不使用**"非空字符串 = activity"作为**字段角色**证据（它只保留为**语法**检查）；
  - ⛔ 无姓名启发式、⛔ 无 CJK 长度猜测、⛔ 不按 token 长度判断；
  - ⛔ 未确认 layout（含 Layout B 自身、未批准 suffix / 非法 weeks 数值 / 二义 5 字段 /
    `REDACTED` 前缀变体 / parity 过滤后为空）**一律不进入集合**；
  - ⚠️ 成员判定**顺序无关**：候选 f3 / f4 先计入两个**极小的内存多重集**，全部页扫完后才求交
    （否则"provider 出现在候选之后"会被误判为不在集合中）；
  - ⚠️ 扫完仍**没有任何**已确认 activity 槽位 → **fail closed**（⛔ 不返回会被误读的 0）。

- **f3 的原始字段名命中统计**（本轮新增；用于定位 `f3 = unknown` 究竟是什么）：

  ```text
  对每个 Layout B 候选：遍历该 raw row 的**字符串类型字段**，
  统计 `f3` **严格等于** 该字段取值的候选数
  ⇒ 只输出 f3_matching_raw_fields: { 字段名 → 命中候选数 }（只含 **>= 1** 次命中的字段名）
  ```

  - ⛔ **只输出字段名**与计数（⛔ 不输出 raw value / f3 原文 / teacher name / 课程与教学班标识）；
  - ⛔ **只做严格字符串相等**：⛔ 无模糊匹配、⛔ 无 substring、⛔ 无分词、⛔ 无大小写折叠
    （⚠️ 唯一例外：**字段名**的内部 ID 规则里对**裸 `id`** 做大小写无关比较，
    ⛔ 与**取值**匹配无关）；
  - **排除字段**（Architecture Review 清单；⛔ 不参与统计）：

    ```text
    精确字段名：courseNum / classNumber / teachingTimePlaceStr
                courseId / class_ID / sumClassesID / outLineId / timePlaceId
    内部 ID 词法形状（**必须有 ID 词法边界**）：
      id / ID / Id …（整个字段名就是 id，忽略大小写）
      xxxId   （驼峰后缀）
      xxxID   （全大写后缀）
      xxx_id / xxx_ID / xxx_Id …（下划线 + id，忽略大小写）
    ```

  - ⛔ **不再使用"任意以 `id` 两个字符结尾"的过宽规则**（它会错误排除普通单词，
    造成 false negative、降低诊断证明力）：`valid` / `invalid` / `hybrid` 这类普通字段名
    **必须参与**统计；
    ⚠️ 按词法边界要求，全小写无分隔符的 `xxxid`（如 `courseid`）**没有** ID 边界 ⇒ 不排除
    （若要覆盖该形态，需要 Architecture Review 给出明确规则）；
  - ⚠️ 多个字段同时命中 → **全部保留计数**（⛔ 不自行裁定哪一个才是答案）；
  - ⚠️ 字段名按码点**排序**输出（结果稳定）；映射用 `Object.fromEntries` 构造
    （⛔ 字段名 `__proto__` 不会污染原型）；
  - ✅ **合成验收矩阵**（node 测试）：单字段 10/10、多字段同时命中、部分命中、无字段命中、
    excluded fields 不参与（`courseNum` / `classNumber` / `courseId` / `class_ID` /
    `sumClassesID` / `outLineId` / `timePlaceId` / `id` / `xxxId` / `xxxID` /
    `xxx_id` 逐个覆盖）、`valid` / `invalid` / `hybrid` **必须命中**、
    non-string fields 不参与、只看 f3（f4 不参与 / 候选自身不污染证据）、
    跨页累计（页序不影响）、返回值与序列化中不出现任何输入**取值**
    （字段名作为映射键按裁定允许）。

- **输出**（单位 = 候选 segment；⛔ 无 rows / 无标识 / 无任何取值）：

  ```text
  candidate_count
  comparable_teaching_name_count       raw row **带** teachingName 属性者
  f3_equals_teaching_name_count        其中 f3 === row.teachingName 者
  f4_equals_teaching_name_count        其中 f4 === row.teachingName 者
  f4_activity_count                    其中 f4 非空（**仅语法检查**）
  f3_in_confirmed_activity_set_count   其中 f3 ∈ 已确认 activity 集合者
  f4_in_confirmed_activity_set_count   其中 f4 ∈ 已确认 activity 集合者
  f3_matching_raw_fields               字段名 → f3 严格等于该字段的候选数（只含 >= 1 命中）
  ```

- ⛔ **raw row 没有 `teachingName` 属性 → `comparable` / 两个 `*_equals_*` 都不推进**
  （不猜、不用其它字段顶替）；
- ⛔ 不产出 bundle、⛔ 不落盘、⛔ 不写日志文件、⛔ 不保存 raw response、⛔ 不修改 raw row；
- ✅ 复用**同一** hostname guard / **同一** `requestPage()` / **同一**全局 pacing controller
  （多页请求 ⇒ **必须**受同一批次冷却约束）；✅ 参数严格白名单
  `semester` / `openingSchoolNumber` / `maxPages`；
- ⛔ **不参与生产链路**：`collect()` / `collectSharded()` 都不调用它；
- ⚠️ **本诊断保留为 development-only，且不再是前置条件**：Layout B 的字段语义已按裁定
  确认为 `weeks | location | opaque | activity`（见上文），诊断只在将来需要复核字段来源时使用；
- ⚠️ **真实 east-campus 诊断必须由负责人在其授权登录会话中手动执行**（Builder 不代跑）；
- ⚠️ **解释边界（必须与 Review 一起读）**：集合是从**本次扫描的语料**里枚举出来的，
  因此 `*_in_confirmed_activity_set_count = 0` 只表示"该 token 没有出现在本次已确认的
  activity 槽位中"，**不**等于"已证明它不是 activity"（可能是语料未覆盖该 token）；
  判定时必须与两个 `*_equals_teaching_name_count` 一起看，⛔ 不得单独用 0 下结论。
- ⚠️ **`f3_matching_raw_fields` 为空映射**同样**不**等于"f3 不是任何字段的值"：
  只表示"在本次 10 个候选所在 raw row 的（未被排除的）字符串字段中，没有严格相等的取值"。

**分段续跑（safe segmented resume）：❌ 未实现 —— fail closed，等 Architecture Review 裁定**

- **触发**：负责人报告 —— 连续两次真实诊断都在**第 6 页**返回 `401 Unauthorized`；
  现有行为正确（立即整体停止，⛔ 不重试 / ⛔ 不读认证 / ⛔ 不绕过登录）。
  根因是**一次 6 页扫描的耗时可能超过会话寿命**：第 6 个请求必然落在
  5 请求批次冷却（300 s）之后 ⇒ 整轮约 7–8 分钟。
- **结论**：在"checkpoint 零敏感 + 不重读 + 语义不变"三条约束下，
  **分段结果不可能与 one-shot 完全等价** ⇒ 按裁定 **fail closed**：
  ⛔ 未新增任何 API、⛔ 未实现近似结果、⛔ 未降低语义。
- **证明（机器校验）**：`prove_segmented_impossibility.mjs`（工作区脚本，⛔ 未入 Git）
  用**真实实现**构造两个世界：

  ```text
  世界 A：part1 候选 f3 == 第 6 页 provider token      → one-shot f3_in_set = 1
  世界 B：part1 候选 f3 在语料中不存在                  → one-shot f3_in_set = 0
  两世界的 part1 **安全聚合投影逐字节相同**      : true
  两世界的第 6 页 rows **逐字节相同**            : true
  ```

  ⇒ `finalize(state1, rows6)` 在两个世界中**输入完全相同、正确答案不同**
  ⇒ **任何**确定性 finalize 都不可能同时正确。
  即：token 级 join（候选 token ↔ provider token）必须跨会话存在，
  而"零敏感 checkpoint"按定义不能携带它。
- **另一半（重读路线同样不成立）**：集合需要**全语料**的已确认 activity 槽位，
  而 1071 行 / `pageSize <= 200` ⇒ **至少 6 页**；
  无法在不读某页的前提下证明该页没有 provider ⇒ 任何精确评估都必须让
  **provider 与 candidate 在同一会话内存中共存**，即该会话要读完整个语料
  （≥ 6 次请求，仍然越过 401 窗口）⇒ 重读方案**不解决** 401，只是换一种扫全量。
- **可选项（均需裁定，⛔ 未擅自实施）**：

  ```text
  A. HMAC 摘要 + **密钥不放进 checkpoint**（用户另行保管/粘贴）
     → 语义可精确 ✓；但密钥与摘要若同处一个本地文件，短 CJK activity token
       可被离线枚举 ⇒ 无法证明"不可逆字典"，与裁定默认不接受的条件冲突；
       ⚠️ 还需要 async crypto.subtle 与"用户携带 256-bit 秘密"的新交互。
  B. 重读式分段 → 见上：不解决 401 ✗。
  C. 调整**诊断专用**的 pacing / 批次冷却（运营策略变更，需批准）
     → 6 次请求 @30 s ≈ 3 分钟，落在"30 s 间隔连续 7 次成功后才出现 HTTP 600"
       的已观测包络内；但这是对既有安全常量的修改 ⇒ 只能由 Review 决定。
  D. 分段模式**省略**两个 activity-membership 计数（⛔ 不是近似值，而是不提供）
     → checkpoint 零敏感且精确；但"降低诊断语义"同样需要 Review 明确批准；
       对**当前**问题（f3 的 raw 字段来源）而言，`f3_matching_raw_fields` 与
       两个 `*_equals_teaching_name` 都是**逐行本地**计数，本身可精确分段。
  ```

**分段式 f3 字段来源诊断（Architecture Review 方案 D；✅ 已实现）**

- **定位**：**只**回答"`f3` 来自哪个 raw 字段"，用于跨登录会话的两段式运行；
  ⛔ **不提供** activity-membership 计数（⛔ 不计算、⛔ 也**不用 0 / null 占位**）；
  完整 `diagnoseLayoutBCandidates()` **保持不变**，其历史 membership 结果继续作为历史证据。

  ```js
  // 第 1 段（pages 1..5）
  const part1 = await window.XuehangSysuCollector.diagnoseLayoutBFieldSourcePart({
    semester: "2026-1", openingSchoolNumber: "5063559", startPage: 1, endPage: 5
  });
  // → 复制 JSON.stringify(part1) 保存到本地文本；重新登录后：
  const part2 = await window.XuehangSysuCollector.diagnoseLayoutBFieldSourcePart({
    semester: "2026-1", openingSchoolNumber: "5063559", startPage: 6, endPage: 6,
    previousState: JSON.parse(<粘贴的 part1>)
  });
  const final = window.XuehangSysuCollector.finalizeLayoutBFieldSource(part2);
  ```

- **契约（恰好六个输出）**：

  ```text
  candidate_count
  comparable_teaching_name_count
  f3_equals_teaching_name_count
  f4_equals_teaching_name_count
  f4_activity_count
  f3_matching_raw_fields    字段名 → 命中候选数（只含 >= 1 命中）
  ```

  ⛔ `f3_in_confirmed_activity_set_count` / `f4_in_confirmed_activity_set_count`
  **不存在**于本接口（不是 0 / null，而是没有这两个字段）。

- **checkpoint schema（零敏感，可 `JSON.stringify` + 复制粘贴）**：

  ```text
  version / semester / openingSchoolNumber / page_size / expected_total
  processed_pages: [ { page_no, row_count } … ]        （仅安全数字）
  上面五个数值计数 + f3_matching_raw_fields: { 字段名 → 计数 }
  ```

  ⛔ 不含任何 raw value / 原文 / 标识 / 认证材料；⛔ 键集合**封闭**（多一个键即 fail closed）。
  ⚠️ `processed_pages` 保存每页**行数**（安全数字），用于在 finalize 证明"已取满"。

- **覆盖与绑定校验（全部 fail closed，⛔ 不静默覆盖）**：
  重复 / 重叠页（在发请求**之前**拒绝）、缺页（页码必须恰好 `1..N` 无洞）、
  `Σ row_count >= expected_total`（取满）、**页数与 `expected_total` 自洽**
  （`N == ceil(total / page_size)`，防止把 total 改小伪造"已完成"）、
  `semester` / `openingSchoolNumber` / `page_size` / `version` 全部绑定并逐段校验。
- **请求行为**：完全复用 `requireAllowedHost()` / `requestPage()` / 全局 pacer /
  页校验 / total 一致性；⛔ 不开放 `pageSize` / `delayMs`（恒用已验证默认值）；
  ⛔ 不改 batch / cooldown；401 / 403 / 600 / malformed / total 漂移 → **立即整体停止**。
- **顺序无关**：允许无序合并（`6 + 1..5`、`4..6 + 1..3` 都已测试）；
  `startPage` 可以是 6（连同 `previousState`）；段内命中计数**累加**而非覆盖。
- **等价性（已测试）**：`finalize(part(1..6))` == `finalize(part(1..5) + part(6))`
  == `1..3 + 4..6` == 逐页 1+2+3+4+5+6 == 无序合并，六个字段逐项完全相等；
  且这六个字段与完整 `diagnoseLayoutBCandidates()` 的对应六个字段**完全一致**
  （防口径漂移的差分测试）。
- ⚠️ **隐私**：`JSON.stringify(checkpoint)` 与结果序列化中**不出现任何取值**
  （已用 synthetic secret 逐项断言）；与 one-shot 的**空映射**解释边界相同：
  空映射只表示"本次允许比较的 raw string fields 中没有严格相等的取值"，
  ⛔ **不**表示"f3 不来自任何 raw 字段"。
- ⛔ **仍不支持**：分段式接口**不含** activity-membership 计数（方案 D 的明确取舍）；
  ⚠️ 两个诊断**都已保留为 development-only**，且**不再是采集 / 导入的前置条件**
  （Layout B 语义已裁定为 `weeks | location | opaque | activity`）。

**2 字段（无 teacher）**：

真实证据：`1-17周/实验实践环节`（**plain**）与 `12-19周校外/实验实践环节`（**qualified**）。

⛔ **不得把 row 级 `teachingName` 注入 `segment.teacher`**：
`teachingName` 是 **row 级**信息，与该 segment 内是否有 teacher **没有对应关系**；
注入等于凭空造事实。⇒ 2 字段两种形态的 `teacher` **一律为 `None`**。


- ✅ 这两种 segment **没有** weekday / sections / 具体地点 / teacher；
- ⛔ **不制造** `Meeting`：`ParsedScheduleSegment.meeting = None`
  （⛔ 不得把 `weekday=None` / `sections=None` 塞进公共 `Meeting`；⛔ 不猜星期 / 节次）；
- ⛔ **不把 qualifier 伪装成 `campus`**：`"校外"` / `"校内(户外)"` 都不是具体校区
  （与 `openingSchoolName → campus` 是两回事）→ 单独存入
  `ParsedScheduleSegment.schedule_qualifier`；
- ⚠️ **不能整串**把 `12-19周校外` 交给 `expand_weeks()` —— 它只认识 `<weeks token>`：
  必须先拆成 `weeks_token = "12-19周"`（→ `expand_weeks`）与 `qualifier = "校外"`；
- ✅ **展开后的周次必须保存在内部字段 `schedule_weeks`**（例如 `12-19周校外` → `[12..19]`）：
  因为 `meeting is None`，`meeting.weeks` 不存在，若不在此保存，
  周次信息会**永久丢失**，后续无法回答"这门见习课排在第几周"。
  ⛔ concrete segment 的 `schedule_weeks` 保持 `None`（其周次仍在 `meeting.weeks`）；
- ⛔ qualifier 是**白名单**（当前 `校外`、`校内(户外)`）：`12-19周未知词` 一律拒绝；
  后续按新真实证据逐个加入，⛔ **不预先泛化**；
- `extract_meetings()` **不投影** non-concrete segment，但
  `ParsedScheduleSegment` **仍保留**（⛔ 不是静默丢弃）；
- ⛔ 因此**字段数只接受 2 / 3 / 4 / 5 / 6**，7+ 仍 fail closed。
- ⚠️ **qualifier 白名单**（当前两项）：`校外`、`校内(户外)`。新增需真实证据。

**3 字段（non-concrete 带 teacher，2026-1 真实证据）**：

真实证据：`1-17周/龙霞/实验实践环节` 与 **`16-16周校内(户外)/龙霞/实验实践环节`**
（同行 `row.teachingName` 均为同一教师姓名）⇒ `fields[1]` 是 **teacher**，
⛔ **不是** location，⛔ **不是**未知 qualifier。

- **两种已确认形态**：
  - **plain**（`1-17周/教师/环节`）→ `schedule_qualifier = None`；
  - **qualified**（`16-16周校内(户外)/教师/环节`）→ `schedule_qualifier = "校内(户外)"`；
- ⚠️ **必须先拆开**：`16-16周校内(户外)` → `weeks_token = "16-16周"` +
  `qualifier = "校内(户外)"`，⛔ **只把 weeks token 交给 `expand_weeks()`**（整串会失败）；
- `meeting = None`（没有 weekday / sections / 具体地点）；⛔ 不生成 `Meeting`；
  ⛔ **不把 `校内(户外)` 当作 `campus`**；
- `teacher = fields[1]`（保留在内部字段；**脱敏由 collector 负责**）；
- `schedule_weeks = expand_weeks(weeks_token)`；
- ⛔ weeks 必须是合法 `N-M周`；⛔ teacher / activity 必须非空；
- ⛔ **qualifier 是白名单**（当前 `校外`、`校内(户外)`）：
  `16-16周未知文本` / `16-16周线上` / `16-16周医院` 一律拒绝；
- ⛔ **不放开为"任意 3 字段 / 任意 suffix"**。

**importer 的三类状态（严格分开）**：

| 状态 | 结果 |
|---|---|
| `teachingTimePlaceStr` **属性不存在** | 窄语义路径 → `meetings = []`（DG-07B） |
| 属性存在、**解析成功但无 concrete segment**（仅 non-concrete） | 另一条窄语义路径 → `meetings = []`（**schedule UNKNOWN**） |
| 属性存在但**解析失败**（`null` / 空串 / 畸形 / 字段数不支持） | **整体失败**（⛔ 不吞成 `meetings = []`） |

⚠️ 前两种都产出 `meetings == []`，但**是两条不同路径**，⛔ 不得混用。
⚠️ 若某 `CourseOffering` 最终 `meetings == []`，按现有 **DG-07** 视为 **schedule UNKNOWN**
（有课程安排信息，但不足以判断时间冲突）。⛔ **本轮未修改 DG-07 / Planner**。


**collector 脱敏同步（`tools/sysu_course_offering_collector.js`）**：

- 新规则与 parser **一致**：
  `2 字段` → **只有**已确认的两种形态才通过：
  plain（`<weeks token>`）与 qualified（`<weeks token><已确认 qualifier>`）；
  两者都**无 teacher**，⛔ 不做脱敏；activity 为空 / weeks 非法 / 未知 qualifier → fail closed；
  其余任意 2 字段结构 fail closed；
  `3 字段` → non-concrete 带 teacher，**两种形态**：
  plain（`<weeks>`）与 qualified（`<weeks><已确认 qualifier>`）；
  `fields[1]`（teacher）**一律**替换为 `REDACTED`（⛔ 不因第一个字段带 qualifier 而跳过），
  weeks（含 qualifier）与 activity 原样保留；
  weeks 非法 / 未确认 qualifier / teacher 空 / activity 空 → fail closed；
  `4 字段` → 无 teacher，原样保留；`5 字段` → 按**同一严格三态规则**判别
  （无 `-` → teacher 则 `fields[3] = REDACTED`；`>= 3` 个非空 `-` 分段 → location 则原样保留；
  其余二义 → fail closed）；
  `6 字段` → `fields[4]` 置为 `REDACTED`；
- ⛔ 未知字段数（7+）继续 `fail()`；
- ⛔ 空 teacher 仍**不得**被写成 `REDACTED`（不静默修复原始数据问题）；
- JS 侧 `classifyFiveFieldToken()` 与 Python `_classify_five_field_token()` **同规则**
  （含同一门槛常量 `MIN_LOCATION_SEGMENTS = 3`）；
- JS 侧 `NON_CONCRETE_FIRST_FIELD` 与 Python `_NON_CONCRETE_FIRST_FIELD` **同规则**
  （整段匹配 + qualifier 白名单，⛔ 不通配）。

**importer（零网络）**：

- 只消费**已 decode** 的 Raw response：`{"code": 200, "data": {"total": ..., "rows": [...]}}`；
- 校验 `code == 200`、`data` 为对象、`total` 为非负整数、`rows` 为对象数组；
- 逐行 `teachingTimePlaceStr` → `Meeting[]` → `build_course_offering()`；
- **任意一行失败 → 本次 import 整体失败**（⛔ 不 fallback、不重试、不跳过坏 row）；
- **`completeness` 必须由调用方明确给出**：adapter **不因为 `len(rows) == total` 就自称 complete**；
- semester 一致性 / real-only / duplicate key / completeness 规则**全部交给 `OfferingSnapshot`**，
  adapter 不重复实现；
- 错误信息**不回显** Raw 字符串或其中任何字段取值。

### Course Data normalization core（Phase 2B-2A）
位置：`backend/app/course_data/`（**内部实现，不是跨模块公共契约**）

| 模块 | 内容 |
|---|---|
| `errors.py` | `CourseDataNormalizationError(ValueError)`（单一异常，不建层级） |
| `normalization.py` | `build_course_offering(raw, *, meetings, source)` 与 `expand_weeks(text)` |
| `snapshot.py` | `OfferingSnapshot`（带 completeness）与 `SnapshotCourseDataProvider` |

**已实现的字段映射**（仅有真实证据的）：

```text
courseNum    → course_id
courseName   → course_name
classNumber  → class_id
yearTerm     → semester
score        → credit            （字符串数字 → number）
teachingName → teacher           （可选；教师姓名不入库）
limitNumber  → capacity                          （来源原始字段，⛔ 不改写）
limitNumber / selectedNumber → remaining_capacity ⚠️ 派生值（三分支规则）
data_source  → "real"            （强制）
source       → 必须由调用方显式传入
```

> ⚠️ **`remaining_capacity` 是派生值**：学校接口**没有直接提供**剩余容量。
> 真实 2026-1 east artifact 已证明来源里**确实存在** `selectedNumber > limitNumber`
> （超员状态），因此**不得**再因这一关系拒绝整条教学班；
> 但该状态下减法**无法**可靠产出符合公共契约的非负剩余容量。裁定后的规则：
>
> ```text
> selectedNumber <  limitNumber → remaining_capacity = limitNumber - selectedNumber
> selectedNumber == limitNumber → remaining_capacity = 0
> selectedNumber >  limitNumber → remaining_capacity = None（unknown）
> ```
>
> - ⛔ **不 clamp 到 0**、⛔ **不修改 `capacity`**（保持来源原值）、⛔ **不新增 `selected_count`**、
>   ⛔ **不修改公共 Schema**、⛔ **不猜学校为何超额**；
> - `None` = "该派生值不可用"，⛔ 不表示"已满"，⛔ 也不表示"无剩余"。

**证据边界（实现能力不得超过真实证据）**：

- **`score`**：真实 2026-1 east artifact 已确认存在 **98 个 `.N` 形式**（小数点前无数字），
  因此 `_parse_credit()` 按裁定接受**三种形状**：

  ```text
  [0-9]+            例如 "3"   → 3.0
  [0-9]+\.[0-9]+    例如 "3.0" → 3.0 / "0.5" → 0.5
  \.[0-9]+          例如 ".5"  → 0.5 / ".0"  → 0.0
  ```

  - ⛔ **不用宽松 `float()` 替代语法校验**（否则会接受符号位 / 指数 / `nan` / `inf`）；
  - ⛔ 继续拒绝：`"."`、`"3."`、`"-.5"`、`"+.5"`、`"..5"`、`"1.2.3"`、全角数字、
    带单位文本（`"3学分"`）、`int` / `float` / `bool`；
  - ⛔ **数值型 `score` 仍无真实来源证据，继续拒绝**；
  - 错误只给**安全稳定分类**：`unsupported_credit_type` / `unsupported_credit_format`，
    ⛔ 不回显 raw score。
- **`selectedNumber` 的处理口径**：当前 2B-2A 的 **narrow normalizer 基于已观察到的 D5 字段**
  把它作为必要字段（缺失即失败），因为 `remaining_capacity` 需要它（三分支规则见上）。
  这**不等于**"SYSU 所有记录必然都有 `selectedNumber`" —— 该字段是否**总是**存在目前**没有**证据；
  若后续真实脱敏样本出现缺失，**再据实调整内部实现**。
- ⚠️ **`selectedNumber > limitNumber` 不再是错误**（架构裁定）：该状态**在来源中真实存在**，
  按上面的三分支规则降级 `remaining_capacity = None`，⛔ 不拒绝整条教学班。
- ⛔ **错误信息不回显 raw row 取值**：`normalization.py` 的错误只给**字段名 + 类型**，
  ⛔ 不得回显 `classNumber` / `courseName` / `score` / 教师姓名等 raw 值
  （此前 `_require_text` / `_require_count` / `_parse_credit` / `_optional_teacher`
  都会带出 `{value!r}`，已在本轮一并移除）。

**明确未映射**（本模块不读取、不映射）：

- 内部 ID / 计数：`courseId`、`class_ID`、`sumClassesID`、`sumClassesNum`、
  `outLineId`、`timePlaceId` —— **`courseId` ≠ `course_id`、`class_ID` ≠ `class_id`**；
- 暂缓业务字段：`courseCategoryName`、`openingUnitName`、`examMode`、`readObj`、
  `teachProgressSubmitState`、`openClass`、`outlineTypeNum`。

**周次**（Architecture Review 裁定；2026-1 east artifact 聚合证据见下）：

```text
普通连续周次 `N-M周`        → 连续全部周次         （N ≥ 1 且 M ≥ N，允许 M == N）
单周 `N-M单周`              → 区间内**奇数周**
双周 `N-M双周`              → 区间内**偶数周**
`N-M周` + 已批准 qualifier  → **与 `N-M周` 完全相同**（qualifier 只做白名单校验）
```

- ✅ 已批准 **weeks qualifier 白名单本轮只有 `校外` / `校内(户外)`**；
  qualifier ⛔ **不改变 weeks 数学含义**、⛔ **不写入公共 `Meeting`**（公共 Schema 无该字段）；
- ⛔ **`N-M周线上` 继续 fail closed**：sections 的 `线上` ⛔ **不迁移**到 weeks
  （三处白名单——weeks qualifier / sections suffix / parser non-concrete qualifier——**互相独立**）；
- ⛔ **单/双周过滤后为空 → fail closed**（⛔ 不生成空 weeks，例如 `3-3双周`）；
- ⛔ 其余一律拒绝：任意其它 suffix、`N-M周单周`、`N-M单双周`、`N,M周`、`第N-M周`、
  `N~M周`、全角数字、多段组合、`M < N`、`N < 1`；
- ⛔ 实现上**不用 `.*` / `startswith` / 无条件 strip qualifier**：
  qualifier 由白名单字面量 + 整段锚定校验；
- **错误只给安全稳定分类**（⛔ 不回显 raw weeks token）：
  `unsupported_week_type` / `unsupported_week_shape` / `unsupported_week_range` /
  `unsupported_week_qualifier` / `unsupported_week_parity_range`
  （含逗号的多段组合归入 `shape`，因为那是形状问题而非 qualifier 问题）。

> **2026-1 east artifact 聚合证据（3475 个 weeks token）**：
> `N-M周` 3382（全部接受）、`N-M周校外` 54、`N-M双周` 15、`N-M单周` 13、
> `N-M周校内(户外)` 11 —— 本轮扩展后 **rejected = 0**（此前 93 个 blocker 全部消失）。

> ✅ **`teachingTimePlaceStr` 已由 `schedule_parser.py` 解析**（Phase 2B-2B，依据私密脱敏样本）；
> `normalization.py` 本身仍然**不解析**原始串，只接收**已解析好的** `Meeting`。

**Snapshot completeness（Data Gate C9 落代码）**：

```text
loaded_count = len(offerings)
partial  ：可无 reported_total；若有，reported_total >= loaded_count
complete ：必须有 reported_total，且 reported_total == loaded_count
```

并要求：所有 offering 的 `semester` 与快照一致、`data_source == real`；
`(semester, course_id, class_id)` 重复即失败（**不静默保留第一条**，也不按 `course_id` 去重）。

**Provider**：`SnapshotCourseDataProvider` —— 结构上满足 Phase 2B-1 冻结的
`CourseDataProvider`（**不继承、不修改** Protocol）；学期匹配返回列表，否则返回 `[]`；
**零网络、无 Mock fallback**。

## 2026-1 深分页异常与五校区分片合并（Architecture Review 裁定方案 B）

### 真实证据：offset >= 6500 稳定异常

| 请求 | 结果 |
|---|---|
| `pageSize=100, pageNo=65`（offset 6400） | HTTP 200 |
| `pageSize=100, pageNo=66`（offset 6500） | **HTTP 600** |
| `pageSize=50, pageNo=130`（offset 6450） | HTTP 200 |
| `pageSize=50, pageNo=131`（offset 6500） | **HTTP 600** |
| `pageSize=50, pageNo=132`（offset 6550） | **HTTP 600** |

`HTTP 600` body：`{"code":50015000,"message":"系统异常"}`。
⇒ 学校侧在 **offset >= 6500** 的**稳定**深分页异常。

### 正式确认的校区 shard（UI 取证）

接口支持 `param: { yearTerm, openingSchoolNumber }`。五个完整校区：

| 校区 | `openingSchoolNumber` |
|---|---|
| 东校园 | `5063559` |
| 北校园 | `5062202` |
| 南校园 | `5062201` |
| 深圳校区 | `333291143` |
| 珠海校区 | `5062203` |

⚠️ 各校区**人工记录的 total**（1071 / 405 / 2898 / 1171 / 1335）**只作验收参考**，
⛔ **不得写进 production completeness 逻辑**；真实判定一律以**本次响应**为准。

### 方案 B：每 shard 一个 bundle + 内部合并

```text
五个独立 shard bundle（各自 pages 就是真实抓到的页，⛔ 不重编号、不重切分）
        ↓  各自走【现有】collect_captured_pages_snapshot()
   五个 OfferingSnapshot（各自必须 is_complete）
        ↓  merge_offering_snapshots([...], baseline_total=<baseline>)
   合并后的 complete OfferingSnapshot
```

- ✅ **零 Capture Bundle format 改动**；
- ✅ **零伪造分页来源**（方案 A 的"重切分为单一全局流"已被**明确否决**）；
- ✅ 合并结果可直接交给**现有** `SnapshotCourseDataProvider`（不改 Provider）。

### 为什么不能只用一个 bundle（结构事实）

1. `_parse_capture_bundle()` 要求 **page_no 全局唯一且严格连续**
   （`page_no == first_page_no + index`）；
2. `pages` 是**扁平数组**，只有一个全局 `first_page_no` / `page_size`，**没有 shard 维度**；
3. `CapturedPagesFetcher` 把 `page_no → response` 建成**扁平 dict**，重复 page_no 会覆盖。
4. 分页核心要求**每页 `data.total` 互相相等**，而各 shard 的 total 天然不同。

⇒ 五个 shard 的原始 pages **无法**合法共存于一个 bundle。

### `merge_offering_snapshots()` 的八个必要条件（缺一即 fail closed）

```text
1. 至少一个 shard
2. 所有 shard semester 一致
3. 每个 shard is_complete == True
4. 每个 shard loaded_count == reported_total
5. sum_shard_reported_total == baseline_total
6. total_loaded_rows == sum_shard_reported_total
7. duplicate_identity_count == 0
8. unique_identity_count == baseline_total
```

- **identity** = `(semester, courseNum, classNumber)`
  = 公共 `(semester, course_id, class_id)`；⛔ **不得只按 `course_id` 去重**；
- ⛔ **任一 shard partial → 整体失败**，不允许"其余校区先算成功"；
- ⛔ **跨 shard 重复 → fail closed**，⛔ **不静默去重后声称 complete**；
  错误信息只报告**最小 identity + 两个 shard 名**（⛔ 不回显课程名等无关内容）；
- 合并成功时 `loaded_count == baseline_total == reported_total`，`complete` 不变量自然成立。

### baseline sandwich（编排层职责）

```text
baseline_before（不带 openingSchoolNumber）→ 采五个 shard → baseline_after
baseline_before != baseline_after → 整体不得标 complete，fail closed
```

⚠️ 该校 `total` **会漂移**（历史 6892 → 现 6880），因此三次读取必须落在**同一采集窗口**内。

### Python 侧 sharded 编排（已实现 + synthetic 验证）

`backend/app/course_data/sharded_capture.py`（**Course Data 内部模块**，
⛔ 不进 `schemas/`、⛔ 不进 `docs/interfaces/`）：

```text
5 个 ShardSource（shard_id + 已加载 bundle 或本地路径，必须**显式**逐个给出）
        ↓  load_capture_bundle() → collect_captured_pages_snapshot()   （【现有】入口）
   5 个 OfferingSnapshot（各自 complete）
        ↓  校验 shard 集合 / 各 shard 自洽 / 覆盖一致性
        ↓  merge_offering_snapshots(...)                                （已 Review 通过）
   ShardedCaptureSet{merged, shards, 计数…}
```

- `APPROVED_SHARD_IDS` = 上表五个校区的**固定顺序**（顺序即合并顺序，保证可复现；
  ⛔ 不猜其它校区、⛔ 不自动读取下拉框、⛔ 不扫描目录发现 bundle）；
- 公开的内部符号：`collect_sharded_capture_set` / `ShardSource` / `ShardedCaptureSet` /
  `ShardedCaptureError` / `APPROVED_SHARD_IDS` / `SHARDED_CAPTURE_SOURCE`
  （已并入 `app.course_data.__all__`，与 `merge_offering_snapshots` 一致）；
- 编排层**自己负责**的 fail-closed 条件（任一不满足 → `ShardedCaptureError`，
  ⛔ 不静默跳过、⛔ 不静默去重）：

  1. baseline 恰好一个快照，且自身 complete / 计数自洽 / semester 匹配；
  2. shard 集合**恰好等于**已批准五校区：**无缺 shard、无多余 shard、无重复 shard**；
  3. 每个 bundle **独立** complete（各自 `loaded_count == reported_total`）；
  4. 每个 shard `semester == expected_semester`（与 3 同一处强制，便于定位到 shard）；
  5. 每个 shard **内部**无重复 identity（`OfferingSnapshot` 构造已强制，本层显式重申）；
  6. `Σ shard reported_total == baseline reported_total`（分片覆盖全体、与基线一致）；
  7. 合并结果**物化后重新计数**仍须 complete：行数 == Σ 各 shard 已加载行数 == baseline，
     且 unique identity 数 == baseline（⛔ **不采信下层自报数字**：数的是最终交给
     runtime 的那份数据）。

- ⛔ **零网络**；⛔ 不重编号 / 不重切分页码；⛔ 不 retry；⛔ 不跳页；
- `baseline_before == baseline_after` 的**对拍发生在调用方**（采集编排层）：
  本函数只接受**一个**已确认的 baseline；
- 隐私：⛔ 不读取 / 不记录课程、教师、教室、学生任何取值；错误信息只含 shard 名、
  **最小 identity**（`semester` + `course_id` + `class_id`）、计数、bundle **文件名**
  （⛔ 不含完整路径）；下层 `captured_pages.py` 错误信息里可能带的本地路径会被
  **擦成文件名**（`_scrub_paths()`）。合并失败时附上 `shard[i]=校区名` 顺序表，
  因为下层只报位置下标。
- 测试：`backend/tests/test_course_data_sharded_capture.py`（**31 个 synthetic 测试**，
  ⛔ 零网络、⛔ 零真实采集中间件；真实分片数字 1071/405/… ⛔ 不进测试常量）。
- non-vacuity：11 个 mutation 逐一改坏一条检查后确认**至少一个测试变红**
  （缺 shard / 多余 shard / 重复 shard / baseline 计数 / baseline 自洽 /
  单 shard 自洽 / 路径擦除 / shard 名还原 / 错误类型统一）；
  **唯一被下层掩盖**的是"同 shard 内重复"的显式重申
  （`OfferingSnapshot.__post_init__` 已先拦下，移除它不会有测试变红 ——
  已在代码注释里如实标注为**刻意的冗余重申**，而非独立检查）。

### JS 侧 sharded 采集编排（已实现 + synthetic Node 验证）

`tools/sysu_course_offering_collector.js` 新增入口 `collectSharded()`
（⛔ 加载脚本仍**不自动发请求**，必须由用户在控制台显式调用）：

```text
① baseline_before（1 次请求：param 只有 { yearTerm }，只读 data.total）
        ↓
② 五个 shard **串行**采集（顺序 = 已批准顺序；每个 shard 从 pageNo=1 起、
   pageSize=200、expectedTotal 取**本 shard 第一页**真实 total、
   accumulatedRows == expectedTotal 时以 reached_total 停止）
        ↓（任一 shard 未取满 → **立即** fail-fast，⛔ 不请求 baseline_after）
③ baseline_after（五个 shard **全部完整成功后无条件请求**；同 baseline_before）
        ↓
④ baseline 稳定性：baseline_before == baseline_after？
        ↓（不等 → `snapshot window unstable`，整体失败）
⑤ shard 覆盖性：Σ shard expectedTotal == baseline_before？
        ↓（不等 → `shard coverage mismatch`，整体失败）
外层 diagnostics 对象
```

⚠️ **判定顺序是硬要求**（Architecture Review Blocker 修正）：
五个 shard 全部完整成功后必须**无条件**先取 `baseline_after` 并判**稳定性**，
**只有** baseline 稳定之后才允许判**覆盖性** ——
否则会拿一个未确认的 snapshot window 去解释覆盖差异。
（此前实现把覆盖性判在 `baseline_after` 之前，已修正。）

- shard 请求：`param: { yearTerm, openingSchoolNumber }`；
  baseline 请求：`param: { yearTerm }`（⛔ 不带 `openingSchoolNumber` 键）；
- 五个已批准校区（源码常量 `APPROVED_SHARDS`，顺序即请求顺序，⛔ 不猜、⛔ 不自动发现）：

  | 校区 | `openingSchoolNumber` |
  |---|---|
  | 东校园 | `5063559` |
  | 北校园 | `5062202` |
  | 南校园 | `5062201` |
  | 深圳校区 | `333291143` |
  | 珠海校区 | `5062203` |

- **严格白名单参数**：只接受 `semester` / `maxPages` / `delayMs`；
  ⛔ `pageSize`（固定 200）/ `firstPageNo`（固定 1）/ 自定义 shard 列表**都不接受覆盖**，
  且拒绝时**不回显**调用方给出的参数名；
- **整体失败（抛出，⛔ 不产出任何 bundle）**：
  1. 任一 shard 未取满（`stoppedReason !== "reached_total"`）→ **立即**停止，
     ⛔ 不再请求后面的校区、⛔ 也不请求 `baseline_after`（fail fast，减少对学校接口的压力）；
  2. `baseline_before !== baseline_after` → **`snapshot window unstable`**；
  3. Σ shard `expectedTotal` != `baseline_before` → **`shard coverage mismatch`**
     （**只在 2 通过之后**才判；与 Python 侧编排同一口径）。
  失败时错误对象带 `.diagnostics`（已采集到的结构化计数），便于控制台排查；
- **输出**：`result.shards[i].bundle` = **5 个独立裸 Capture Bundle**
  （顶层仍只有 `format` / `semester` / `first_page_no` / `page_size` / `pages`，
  ⛔ **diagnostics 不进入 bundle**）+ `result.diagnostics` = 1 个外层对象；
  取用方式：`shardBundle(result, "东校园")` / `toShardJson(...)` / `toDiagnosticsJson(...)`；
  ⛔ 既有的 `toJson(result)` **拒绝**五校区结果（它不是单个裸 bundle）；
- **diagnostics 字段**（照 Review 清单）：
  `baseline_before`、`baseline_after`、`shard_total_sum`、`expected_pages_total`、
  `semester`、`page_size`、`shard_count`，以及每个 shard 的
  `shard_id` / `openingSchoolNumber` / `expectedTotal` / `accumulatedRows` /
  `stoppedReason` / `page_count` / `expected_pages`；
  ⛔ diagnostics **只有结构化计数**：不含任何 row、课程、教师、教室或原文；
- **`expected_pages = ceil(total / page_size)`：⛔ 只允许作 diagnostics**，
  **不得**参与任何 complete / 完整性判定 —— 判据只有 `accumulatedRows == expectedTotal`
  （静止断言 + 行为用例：学校返回"半页"导致 `page_count != expected_pages` 时**仍然必须成功**）；
- **复用同一份分页实现**：五个 shard 与 baseline 都走同一个取页核心
  （`pageNo` 从 1 起、`pageSize`、total 中途变化即失败、hostname guard、
  same-origin、⛔ 不重试、⛔ 不并发）；
- **全局 batch pacing（保守运营策略）**：本文件有**唯一**一个 pacing controller
  （`createRequestPacer()`），等待与批次计数**只存在于它内部**；
  `baseline_before` / `collectPages()` / shard 循环 / `baseline_after`
  **都不再各自 sleep、也不各自计数**，它们只是把同一个 controller 交给
  `requestPage()`（发请求前 `beforeRequest()`、校验成功后 `noteSuccess()`）：

  ```text
  第 1 个请求（= baseline_before）  → 立即发送
  其它相邻请求                     → 先等 delayMs（= 下限 = 30000ms）
  全局已累计 5 个**成功**请求时     → 改为先等 max(BATCH_COOLDOWN_MS, delayMs)
                                     = 300000ms（冷却本身 > 普通间隔，⛔ 不叠加）
  ```

  ⛔ 计数是**整个 sharded collection 的全局请求数**
  （`baseline_before` + 所有 shard 的每一页 + `baseline_after`）：
  ⛔ **不是 per-shard**，⛔ **不会在 shard 边界重置**
  （行为用例：全局第 5 个请求落在同一个校区的页间时，冷却同样发生）；
  ⛔ `baseline_before` 与 `baseline_after` 都算请求、都走同一 controller；
  ⛔ 调用方只能把 `delayMs` **调大**，调小（< 30000，含 0 / 1 / 999 / 1500 / 9999 / 29999）
  在**发请求之前**被拒绝；⛔ 也**不接受**覆盖 batch 大小 / 冷却时长；
  ⛔ 一次性诊断（2C1B / 2C1C）只发 1 次请求，不传 controller、不参与批次计数；
  ⚠️ **30 秒 + 5-request batch + 5-minute cooldown 是当前保守运营策略**，
  来源是**人工实测**（`pageSize=50` + 30 秒间隔：连续 7 次成功后第 8 次即
  `HTTP 600 / code=50015000 / 系统异常`），
  ⛔ **不声称**是学校公开阈值，也不据此推断任何服务端限流实现；
  ⛔ `HTTP 600` 仍然只是 **fail closed**：⛔ 不重试、⛔ 不 backoff 重试、⛔ 不跳页、
  ⛔ 不续采、⛔ 不做任何认证绕行（行为用例：某页 600 → 该页**只请求过一次**、
  不再请求其它校区、不发 `baseline_after`、不产出任何 bundle；batch 未满时
  ⛔ 不额外等 5 分钟）；
- 测试：`tools/sysu_course_offering_collector.test.mjs`（**92 个 `node:test` 用例**，
  其中 47 个覆盖五校区：正常链路 / 请求顺序与形态 / 多页 shard / 半页 `expected_pages` /
  baseline 漂移两个方向 / 未取满 fail fast / 覆盖性 / **判定顺序三例**
  （`before=6880, Σ=6881, after=6881` → unstable 且确认 `baseline_after` 确实被请求；
  `before=6880, Σ=6879, after=6880` → coverage mismatch；
  只有 shard 失败才允许跳过 `baseline_after`）/ 取消 / 白名单 /
  **batch pacing 九例**（全序列等待逐步核对 / request 1–5 普通 30 秒 /
  request5→6 冷却 / request10→11 再次冷却 / shard 边界不重置计数 /
  baseline_before 与 baseline_after 都计入 / batch 未满不额外等待 /
  `collect()` 也走同一 controller / 下限 30000 且只允许调大）/
  shard 内解析失败（单一前缀 + 附 diagnostics）/
  裸 bundle 与 diagnostics 分离 / 隐私）。
  ⛔ 全程零网络（假 `fetch` + 假 `setTimeout` 记录请求的延迟），
  ⛔ 所有 row 均为人工虚构；真实分片数字不进测试常量；
- non-vacuity：**18** 个 mutation 逐一改坏一条行为（sandwich / 未取满 / 覆盖性 / 白名单 /
  `expected_pages` 变判据 / baseline 请求形态 / shard 名回显 / diagnostics 夹带 row /
  取消语义 / 普通间隔压到 1 秒 / 回退成旧判定顺序 / 下限退回旧值 /
  **冷却永不触发** / **批次计数不重置** /
  **per-shard 各建一个 pacer（= shard 边界重置）** / **baseline 绕过 pacer** /
  **批次未满也强制冷却** / **冷却不取 max(delayMs)**）
  → **18 / 18** 都至少一个 Node 用例变红；
  其中 **16 / 18** 同时被 `backend/tests/test_sysu_collector_guard.py` 的静态守卫抓到
  （只有"取消语义"与"批次计数不重置"是纯行为用例覆盖）。

### 本地持久化层（SQLite，MVP 课程数据库，已实现 + synthetic 验证）

`backend/app/course_data/store.py`（**内部模块**，标准库 `sqlite3`，⛔ 零网络、⛔ 无新依赖）：

```text
Capture Bundle
        ↓  （现有入口，本模块⛔不碰）
OfferingSnapshot（completeness 已由上游判定）
        ↓  import_offering_snapshot(path, snapshot, *, artifact_sha256, scope)
本地 SQLite Course Data 库
        ↓  load_course_offerings(path, semester, course_ids=[...])
list[CourseOffering]（公共契约对象）
```

### scope：`complete` **只在声明的 scope 内**成立（⛔ 不得改成全局含义）

同一份 `is_complete == True` 可能是三种完全不同的东西，
所以 import **必须由调用方显式声明 `SnapshotScope`**：

```text
campus        / <openingSchoolNumber>   某个校区 shard（例如 5062202）
full_semester / <semester>              整个学期（例如 2026-1）

is_complete == complete **within the declared scope**
```

- ⛔ `complete` **不得**被解释为"全学期完整"：`campus` 快照完整只说明**那个校区**
  在本次采集内取满了；
- ⛔ **不从 `source` / 文件名 / rows 推断 scope**，也⛔ 不产生任何 global completeness 暗示；
  声明什么就记什么（行为用例：`source` 里写着 `campus/…` 也不会改变声明值）；
- ⛔ scope 参数**必填**（省略 → `TypeError`；显式 `None` / 字符串 → `CourseDataStoreError`）；
- `full_semester` 的 `scope_id` **必须等于**快照 semester，否则该审计记录自相矛盾 → 拒绝；
- `campus` 的 `scope_id` = 校区 `openingSchoolNumber`：本层⛔ **不保存 / 不校验**那张校区号表
  （唯一真源在采集侧），只要求它是非空 id；
- ⚠️ **Case-A-scoped 暂不在白名单内**：它的 `scope_id` 取形尚未确证，
  因此这类快照当前被**明确拒绝**，而不是被塞进一个含糊的 kind
  （需要时先给出 id 语义，再按流程加入 `ALLOWED_SCOPE_KINDS`）。

**DB schema（两张表）**

```text
course_offering（identity = 主键，⛔ 不允许按 course_id 覆盖不同教学班）
  semester, course_id, class_id,            ← PRIMARY KEY (semester, course_id, class_id)
  course_name, teacher, credit,
  capacity, remaining_capacity, source, data_source,
  meetings_json,                            ← 稳定 JSON（键排序 + 紧凑分隔符）
  artifact_sha256, imported_at,             ← 行级 provenance
  scope_kind, scope_id                      ← 行级 scope（否则"这份 provenance 属于哪个 scope"有歧义）

course_data_import（artifact 级审计；同一 (artifact, semester, scope) 只记**首次**导入）
  artifact_sha256, semester,
  scope_kind, scope_id,                     ← PRIMARY KEY (artifact_sha256, semester, scope_kind, scope_id)
  source, imported_at, completeness,
  loaded_count, reported_total, offering_count
```

⚠️ scope 参与审计表主键：同一份 artifact 若以**不同 scope** 声明，
会各自留一条记录，⛔ 而不是被静默合并成一条含义不明的记录。

**能力（内部 API）**

| 函数 | 作用 |
|---|---|
| `initialize_course_data_store(path)` | 建立 / 复用本地库（幂等；⛔ 不自动建父目录） |
| `import_offering_snapshot(path, snapshot, *, artifact_sha256, scope)` | upsert 一份**在声明 scope 内 complete** 的快照 |
| `load_course_offerings(path, semester, *, course_ids=None)` | 按学期取全部 / 按 `course_id` 集合取候选教学班 |
| `load_course_data_provenance(path, *, semester=None)` | 读回 artifact 级 provenance（含 scope，审计用） |
| `SnapshotScope(scope_kind, scope_id)` | 调用方声明的 scope（构造即白名单校验） |
| `compute_artifact_sha256(data)` | 对 artifact **原始字节**算 SHA-256（十六进制小写） |

- **identity / upsert**：`(semester, course_id, class_id)`（⛔ 与 scope 无关）；
  同一 `(artifact, semester, scope)` 重复导入**幂等**（第二次 `inserted=0 / updated=0 / unchanged=N`），
  ⛔ **不同 `class_id` 的同一门课各自成行**；
  数据列一致时仍刷新 provenance（`artifact_sha256` / `imported_at` / scope 指向**本次**导入）；
- **查询**：`course_ids=None` → 该学期全部；`course_ids=[]` → **空集合 ⇒ 空列表**（⛔ 不是"不筛"）；
  返回顺序由 SQL 显式保证（`ORDER BY course_id, class_id`）；
- **completeness**：⛔ 本层**不判断完整性**，`is_complete == False` **拒绝写入 approved 路径**；
  库里也⛔ 不写任何"自封完整" / "全学期完整"的列，导入记录只**如实转述**上游 `completeness` + 声明 scope；
- **schema 版本**：库里若缺少 scope 列（更早 schema）→ **明确提示重建**，⛔ 不自动迁移、⛔ 不静默降级读取；
- **`artifact_sha256` 口径（⛔ 不得改动）**：
  `SHA-256 = artifact identity / integrity ≠ acquisition provenance proof`；
  本层只是如实记录调用方给出的这个值，⛔ 不据此声称任何采集时间 / 采集者 / 授权状态；
- **数据边界**：只存已标准化的公共 `CourseOffering`；
  ⛔ 不存 Cookie / token / 登录信息 / 原始完整 response / 教师隐私扩展字段 / 学生信息
  （schema 级断言：两张表的列名不得命中这些 token）；
  加载时若发现 `data_source != 'real'` 或 `meetings` 被外部改坏 → fail closed；
- ⚠️ **公共模型没有 `selected_count`**：公共 `CourseOffering` 上只有
  `capacity` / `remaining_capacity`，因此本层持久化这两个字段，
  ⛔ **不新增** `selected_count` 列（那需要先走公共 Schema 变更流程）；
- ⚠️ **未接 Provider**：⛔ 未改 `SnapshotCourseDataProvider` / `CourseDataProvider` 公共边界；
  "是否把 Provider 接到 SQLite" 是后续独立的 Architecture 决策；
- 测试：`backend/tests/test_course_data_store.py`（**61 项，纯 synthetic、零网络、零真实数据**）：
  complete 导入成功 / partial 拒绝且**不写任何行** / 重复导入幂等 /
  identity 变更原地更新 / 同学期不同 `class_id` 各自保留 / 跨学期隔离 /
  `course_ids` 过滤（含空集合）/ 读回顺序（SQL 级）/ meetings 5 种形态 round-trip /
  稳定 JSON / 可空公共字段 / 混合来源不猜 /
  provenance 字段 round-trip（含行级列）/ 首次导入记录不被改写 / artifact 口径 /
  `artifact_sha256` 形状校验 / 非法输入 / 路径与 SQLite 文件损坏 / 外部库识别 /
  被篡改的 `meetings` 与 `data_source` / schema 数据边界断言 /
  **scope 十二例**（campus 可导入 / campus round-trip / full_semester round-trip /
  scope 缺失拒绝 / 非法 kind 与 id 拒绝 / `full_semester` id 必须等于 semester /
  `source` 与文件名不改变声明 scope / 同 semester 不同 campus 各自审计 /
  同一 artifact 两个 scope 两条记录且重复导入仍幂等 / 行级 scope 跟随后一次导入 /
  过旧 schema 明确报错 / 库中无"全局完整"列）；
- non-vacuity：**19 个 mutation 全部变红**（去掉 partial 拒绝 / identity 丢掉 `class_id` /
  不校验 `data_source` / 去掉 `ORDER BY` / JSON 不排序 / 不写 `teacher` /
  `already_imported` 恒 False / 空 `course_ids` 不短路 / 不校验 hash 形状 /
  导入记录改 OR REPLACE / hash 不归一化 / 不检查外部库 /
  **审计记录不写 scope** / **审计主键不含 scope** / **不做 full_semester 交叉校验** /
  **scope_kind 白名单失效** / **scope 从 source 推断** / **不检查过旧 schema** /
  **行级 scope 写死**）——
  其中"去掉 `ORDER BY`"由 **SQL 级断言**抓到（纯行为用例无法区分"有保证"与"恰好一致"）。

### 尚未实现（待 Review 通过后）

- **runtime manifest / provenance 格式**与 **exact-artifact SHA-256 gate**
  （属 PR #39；本轮**刻意未设计**，避免在编排能力尚未 Review 前先定格式）；
- **把 `SnapshotCourseDataProvider` 接到 SQLite**（本轮刻意未做，等 Architecture 决策）；
- ⛔ 本轮**未跑真实五校区采集**、⛔ **未改 Capture Bundle format**、
  ⛔ **未改** `backend/app/course_data/sharded_capture.py`、⛔ **未改 collector**。

## 当前接口

- 输出：`CourseOffering[]`（符合 `schemas/course_offering.schema.json`）；
  `meetings` **必填**，**允许 0..N 段**（DG-07A 起 `minItems: 0`）——
  `meetings = []` 表示**当前来源快照没有可用排课信息**（⛔ 不表示无课 / 异步 / 无冲突）；
  ✅ **DG-07B 起本模块已能忠实产生该状态**（**唯一**来源形态：Raw row **没有**
  `teachingTimePlaceStr` 这个 key）；⛔ 但空数组**仍不得接入真实产品链路**（新 rollout gate）；
- 跨模块公共边界：`CourseDataProvider.get_course_offerings(semester) -> list[CourseOffering]`
  （见 `docs/interfaces/integration.md`，**已冻结**，不得私自修改）；
- **内部接口（非公共契约）**：`OpeningCoursesPageFetcher`（2B-2C0）——
  只用于 Course Data 内部分页采集，**不加入 Integration**；
- **尚未暴露任何真实 API**：`/api/v1/mock/*` 仍是独立的永久 Mock 回放通道。

## 当前阻塞

- **当前主 blocker = G11 下游实现（DG-07C / DG-07D）**
  （不是继续扩大结构诊断）：
  - **结构层取证已完成**：第 1 页 200 条中 **39 条完全没有 `teachingTimePlaceStr`**
    （161 条非空，其余形态 0）；C1C 相关性诊断进一步显示
    **结构差异集中在排课相关字段**（`timePlaceId` 38/39 缺失 vs 161/161 存在；
    `weekDay` 38/39 缺失 vs 12/161 缺失），而 `limitNumber` / `selectedNumber`
    在 39 条中**完整存在**，分类字段**未发现 `missing` 组独占值**
    （见 §4.7.1；**只有边际计数，无逐 row 交叉证据**）；
  - **业务语义已获得部分界面证据**（C1D，**n = 2**）：两条典型候选在官方 UI 中
    **均为普通教学班行**、时间 / 周次 / 地点**完全空白**且**无状态文字**
    （⚠️ **n = 2 不能代表全部 39 条**）；
  - ✅ **契约方向已裁决**：**DG-07A Contract Migration 已实施 / 已 merge**
    （`meetings` `minItems: 1 → 0`，`required` 不变）；
  - ✅ **Course Data 侧归一化已实施（待 Reviewer）**：**DG-07B** ——
    仅"Raw row 没有 `teachingTimePlaceStr` key"可产出 `meetings = []`；
    解析失败继续 fail closed；缺排课信息的 row **不被跳过**；Collector 已同步；
  - **仍未解决**：缺 schedule 字段的**学校侧业务原因** / 这些记录的**业务类型** /
    是否属于**有效可选教学班** / 是否应**最终被 Planner 选择** / **全学期缺失比例**；
  - **当前 blocker = DG-07C（Planner unknown-schedule safety）与
    DG-07D（Frontend 展示）尚未开始**；
    ⛔ **不继续扩大结构诊断**，也⛔ **不实施**任何 workaround；
  - ⛔ **empty-meeting Offering 仍不得接入真实产品端到端链路**：
    不新增真实 API、不接 `PlanningOrchestrator`、不交 Planner、不送前端、
    不改 Mock 让 Demo 提前出现 `[]`（新 rollout gate）；
  - ⚠️ **39/200 只描述第 1 页样本，不得外推**；**C1D 的 n = 2 同样不得外推**；
  - ⛔ **不声称 G11 resolved**（**contract migration implemented; Course Data
    empty-meeting normalization implemented; Planner / Frontend downstream handling
    pending; school-side business cause still unknown**）；
- **DG-07A 与 DG-07B 已改变契约与 Course Data 能力**：`DG-07` =
  **`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**，
  其中 **DG-07A 契约迁移已 merge**、**DG-07B Course Data 归一化已实施（待 Reviewer）**；
  ✅ `meetings = []` 现在**在契约层合法、且本模块内部可忠实产生**；
  ⛔ 但 `mock_data/` **未修改**（每班仍 ≥1 段），
  ⛔ **在 DG-07C / DG-07D 完成前，不得把 empty-meeting Offering 接入产品链路**；
- **真实完整学期程序化采集未完成**：**尚未**在 DG-07B 之后重新采集；
  ✅ **"缺排课字段"不再是 fail-closed blocker**（DG-07B 起可规范化为 `meetings = []`），
  但 ⛔ **DG-07C / DG-07D 完成前**，empty-meeting Offering **不得接入真实产品链路**；
  后端 Python 侧仍然**零网络**（没有 endpoint、没有认证处理、不会自动发起请求）；
  ✅ 另：**认证不再是 blocker**（same-origin 请求已在「全校开设课程」模块内成功）；
- **完整 semester snapshot 未取得**：当前只有 D5 小规模侦察、私密脱敏样本
  和**前两页人工分页参数验证**，**尚未进行程序化完整学期采集**，因此**不是**完整 snapshot；
- ⛔ **`partial` snapshot 不得接入 Integration / Planner 产品链路**（本阶段限制）；
- ⛔ **`weekDay → weekday` 与 `openingSchoolName → campus` 仍然不做**（C11 待确认项）：
  `weekday` 一律来自 segment 自身，`campus` 只来自 segment 的 location 字段，
  代码中**没有**这类 fallback；
- ⛔ **meeting 级教师关联为 known deferred representation gap**：
  parser **内部保留** `ParsedScheduleSegment.teacher`，
  但 `Meeting` 不承载教师，`teacher` 仍是 `CourseOffering` 顶层汇总 / 展示字段。

## 当前使用数据

- **业务数据仍全部为 Mock**：`/mock_data/course_offerings.json`（人工虚构，`data_source = "mock"`）；
- 本轮的**测试**只使用**人工虚构**的结构等价样本与占位名（如 `"示例教师A"`、`"示例校区"`）；
- 负责人提供的**私密脱敏样本**（`OFFERING-001`）**只在本地阅读**，
  **未进入 Git**（未 `git add` / 未进测试 fixture / 未进 docs / 未进 worklog；
  本文件**不记录该样本的文件名**）；
- **`OFFERING-002`** 只登记**汇总事实**（「全校开设课程」独立模块内 same-origin 请求成功、
  第 1 页响应成功进入采集器、第 1 页 `total_rows = 200` 且
  `missing = 39` / `non_empty_string = 161` / 其余形态 0、**C1C 两组字段的聚合分布**，
  以及 **C1D 两条人工 UI 核验的汇总事实（n = 2）**；
  ⚠️ **仅第 1 页，不得外推**）；
  **不含任何 Raw row**、不含课程 / 教学班信息、**课程名 / 课程号 / 教学班号**、教师、教室、
  内部 ID、`readObj`，不含任何逐行信息，**也不含任何真实 categorical 取值 / 分类名 / 单位名**；
  **Raw 响应 / Capture Bundle / 截图均未进入 Git**；
- **本轮未生成任何真实 Capture Bundle**：仓库内**不含**真实采集产物；
  本地若产生，也属 **Real Sanitized Capture**，**不得进入 Git**；
- 仓库内**不含**真实教师姓名、真实教室、内部长 ID 取值、`readObj`、Raw JSON、
  Cookie / Session / Token、endpoint。

### 单校区采集（single-approved-campus capture；✅ 已实现）

- `collectApprovedShard({ semester, shardId, maxPages, delayMs })`：
  只采**一个已批准校区**，产出**标准裸 Capture Bundle**
  （`format` / `semester` / `first_page_no` / `page_size` / `pages`）；
  ⛔ 不新增 wrapper schema、⛔ 不做 fake global page renumbering、⛔ 不改五校区编排。
- **固定白名单**（顺序即已批准顺序）：`east-campus` / `south-campus` / `shenzhen-campus` /
  `zhuhai-campus` / `north-campus`；`shardId → openingSchoolNumber` **内部固定映射**，
  ⛔ 调用方不能传 `openingSchoolNumber`（不在 options 白名单内 ⇒ 先于任何请求拒绝）；
  ⛔ 号码不重复（唯一真源仍是 `APPROVED_SHARDS`）。
- **pacing**：单校区路径 `>= 30 s` 间隔 + **batch ceiling 7**；
  ordinary / 五校区路径继续 **5**；⛔ 未全局改 pacing（`MIN_DELAY_MS` / `BATCH_COOLDOWN_MS` 未动）。
- **北校园**：白名单保留、`operational: false` ⇒ **发请求之前** fail closed（⛔ 不绕过）；
  未取满 ⇒ fail closed、⛔ 不产出 bundle；401/403/600/malformed/total 漂移 ⇒ 立即整体停止。
- ⚠️ **完整性口径**：East+South+Shenzhen+Zhuhai 四个校区 complete
  **≠ full semester complete**；campus artifact 必须以 `scope_kind = campus` 导入；
  ⛔ 不得把 North 缺失伪装成学期完整（见 `docs/data/REAL_CAPTURE_OPERATION_PACK.md` §G）。

### Runtime / Frontend 兼容性结论（✅ 已审计）

- **Phase 6 结论 = B（PR #39 需要小改）**：PR #39 的装载模型是
  "一个 Capture Bundle + 一个 SHA-256 + 一个内存快照"，而真实数据已变为
  每校区 artifact + SQLite store + 需五 shard 齐备的 merge ⇒ 需要
  ① 装载范围显式声明 ② 多 artifact 入口 ③ campus 范围如实标注；
  ⛔ frozen `CourseDataProvider.get_course_offerings(semester)` 不变。
  ⛔ 本轮未合并 PR #39、未改 runtime architecture；详见
  `docs/data/RUNTIME_AND_FRONTEND_COMPATIBILITY_REVIEW.md`。
- **Phase 8 frontend = 全部 ✅**（`meetings=[]` 中性文案、⛔ 无 conflict-free、
  `remaining_capacity=None → 破折号`、Real/Mock 清晰、503 不 Mock fallback）；
  唯一发现：`X-Data-Source` 响应头只由 mock API 设置 ⇒ 建议真实接口也返回
  `X-Data-Source: real`（需 Review 裁定，⛔ 未擅自改接口面）。
- **诊断分类（Phase 9）**：2C1B / 2C1C / `diagnoseLayoutBCandidates` /
  分段式字段来源诊断 = **development-only / safe-to-remove-after-final-East-acceptance**；
  `collectApprovedShard` = **production-needed**。

## 下一步

- **不再等待 DG-07C / DG-07D**：DG-07A / B / C / D 已全部 IMPLEMENTED / REVIEWED，
  Data Gate 已恢复 **PASSED / CLOSED**；
- **Course Data 当前主任务转为真实数据完备化**：在负责人正常授权会话中取得
  **完整 2026-1 semester snapshot**，并以 `OfferingSnapshot` 明确记录 completeness；
- ⛔ **partial snapshot 仍不得进入 Integration / Planner 产品链路**，不得把已验证的前两页或
  第 1 页诊断结果冒充完整学期数据；
- 完整 snapshot 准备好后，由 `SnapshotCourseDataProvider` 交给 Integration，
  再与 Curriculum / Planner 做真实 Case A E2E；
- **G11 仍保留为学校侧业务原因未知**：DG-07 已解决“如何安全表示和处理”，
  但没有解决“学校为什么缺少 schedule”；
- ⚠️ **当前真实数据链路的首要阻塞项：没有"单校区采集"入口**。
  唯一入口 `collectSharded()` 是**五个 shard（含北校园）的一次性、全有或全无事务**，
  调用方**不能选择 shard**；北校园按裁定保持 **suspended**（真实 `HTTP 600` 证据）
  ⇒ 五 shard 运行**预期必然失败** ⇒ East / South / Shenzhen / Zhuhai **目前无法单独取得
  bundle**。⛔ 未擅自改 `APPROVED_SHARDS` / ⛔ 未新增入口 / ⛔ 未跳过失败 shard；
  需要 Review 在 **(A) 批准单校区采集入口** 与 **(B) 允许 suspended 期间跳过该 shard** 中裁定。
  操作细节见 `docs/data/REAL_CAPTURE_OPERATION_PACK.md`；
- ⚠️ **Layout B 重抓**：本轮起 collector 对精确 Layout B 输出 `REDACTED_OPAQUE`，
  parser 只接受该占位符 ⇒ **旧东校园 artifact（含原始 opaque）必然 fail closed**，
  必须通过真实采集重抓；⛔ 不得手工编辑旧 artifact 或把原始取值改成占位符；
- ⚠️ **artifact acceptance CLI 未集成**：指定的 commit
  `1bb8bfdbaddbaac7280702942ba0783c29722ec8` 在本地与远端都不存在（已 fetch 全部远端 ref 核实）
  ⇒ 需要用户提供该 commit；
- 公共契约、fail-closed 边界、Raw / Capture 隐私规则继续保持不变。