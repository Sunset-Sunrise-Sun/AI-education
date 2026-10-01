# Course Data 当前状态

> 最后更新：2026-10-01（**DG-07 架构裁决已落档**：**APPROVED WITH MODIFICATION /
> IMPLEMENTATION PENDING**（**契约方向已批准，尚未实施**）；
> **Data Gate 仍保持 Reopened**）
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
> 因此当前 `collect()` 仍**按设计 fail closed**，**尚未生成真实 Capture Bundle**。
> **G11 仍未 resolved**：业务语义仅有**部分界面证据**，**契约缺口候选 DG-07 待架构裁决**。
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
契约缺口 DG-07（CourseOffering 空 meetings）     ✅ **APPROVED WITH MODIFICATION**
                                                    （**2026-10-01 批准**；⛔ **IMPLEMENTATION
                                                    PENDING**，本轮未实施；Data Gate 仍 Reopened）
真实完整学期程序化采集                              ⏳ 未完成（因缺字段 fail closed 而中止）
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
| 当前 `collect()` 的处置 | **按设计 fail closed**（缺字段即整体失败） |
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
- ✅ **限速与安全阀**：`DEFAULT_DELAY_MS=1500` / `MIN_DELAY_MS=1000`；`DEFAULT_MAX_PAGES=2`、`ABSOLUTE_MAX_PAGES=50`
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
- Data Gate-2（**DG-01**）已把 `CourseOffering` 改为 **1 — N `meetings[]`**：
  一个教学班 = 一个 `CourseOffering`，`meetings[]` = 它的**全部**上课时间 / 地点段。

### Schedule parser + local import adapter（Phase 2B-2B，本轮）
位置：`backend/app/course_data/`（**内部实现，不是跨模块公共契约**）

| 模块 | 内容 |
|---|---|
| `schedule_parser.py` | `parse_teaching_time_place(text)`、`ParsedScheduleSegment`、`extract_meetings()`、`parse_weekday()`、`parse_sections()` |
| `importer.py` | `import_opening_courses_response(payload, *, semester, source, completeness)` |

**parser（依据私密脱敏样本，样本本身不入 Git）**：

```text
segment separator = ","      field separator = "/"
无地点（5 字段）：weeks / weekday / sections / teacher / activity
有地点（6 字段）：weeks / weekday / sections / location / teacher / activity
```

- ✅ **最多一个**末尾逗号：单个末尾逗号产生的空 segment **忽略**；
  ⛔ `seg,,` / `seg,,,`（多个末尾逗号）**失败**；
- ⛔ 中间空 segment（`seg1,,seg2`）**失败**，不静默忽略；
- ⛔ 字段数只接受 **5 或 6**，其它 fail closed；
- **星期**：只接受 `星期一` … `星期日`；⛔ **`weekday` 一律来自 segment 自身**——
  样本显示 Raw `weekDay` 的顺序**不能安全假设**与 segment 一致，因此**完全不使用**它；
- **节次**：`第N-M节`，要求 `N ≥ 1` 且 **`M ≥ N`**（允许 `M == N`，如 `第4-4节`）；
- **地点**：只按**第一个 `-`** 切 → `campus` = 第一段、`classroom` = 其余完整文本；
  ⛔ 不进一步猜 building / room；⛔ **`openingSchoolName` 不是 `campus` 的 fallback**；
- **teacher / activity**：必须为非空字符串，**保留在内部 `ParsedScheduleSegment`**；
  `extract_meetings()` 只把 `Meeting[]` 交给公共契约；
  ⛔ **meeting 级教师关联仍是 known deferred representation gap**，**未修改任何 Schema**；
- **不丢段、不合并、不排序**：输出顺序 == Raw 顺序。

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
limitNumber  → capacity
limitNumber - selectedNumber → remaining_capacity   ⚠️ 派生值
data_source  → "real"            （强制）
source       → 必须由调用方显式传入
```

> ⚠️ **`remaining_capacity` 是派生值**：学校接口**没有直接提供**剩余容量，
> 它是 `limitNumber - selectedNumber` 相减得到的。**不得**描述成接口直接给的字段。

**证据边界（实现能力不得超过真实证据）**：

- **`score`**：真实证据只确认它是**字符串数字**，因此当前**只接受字符串数字**
  （`"3"` / `"3.0"` / `" 3 "`）；
  ⛔ **数值型 `score`（`3` / `3.0`）尚无真实来源证据，当前一律拒绝**；
  bool / 负数 / 空串 / 非数字文本继续拒绝。若后续脱敏样本显示它也可是 JSON number，再据实放宽。
- **`selectedNumber` 的处理口径**：当前 2B-2A 的 **narrow normalizer 基于已观察到的 D5 字段**
  把它作为必要字段（缺失即失败），因为 `remaining_capacity` 需要它。
  这**不等于**"SYSU 所有记录必然都有 `selectedNumber`" —— 该字段是否**总是**存在目前**没有**证据；
  若后续真实脱敏样本出现缺失，**再据实调整内部实现**。

**明确未映射**（本模块不读取、不映射）：

- 内部 ID / 计数：`courseId`、`class_ID`、`sumClassesID`、`sumClassesNum`、
  `outLineId`、`timePlaceId` —— **`courseId` ≠ `course_id`、`class_ID` ≠ `class_id`**；
- 暂缓业务字段：`courseCategoryName`、`openingUnitName`、`examMode`、`readObj`、
  `teachProgressSubmitState`、`openClass`、`outlineTypeNum`。

**周次**（Phase 2B-2B 依据脱敏真实样本重新界定）：

```text
普通连续周次 `N-M周`：N ≥ 1 且 M ≥ N（**允许 M == N**）
  → 样本中已观察到多种范围（含退化区间）
单周 `1-17单周`：**只此一个取值**
```

- ✅ 普通区间按 `N-M周` 展开；退化区间（`M == N`）合法并展开为单个周次；
- ⛔ **单周不泛化**为任意 `N-M单周`（那一形态尚无证据）；
- ⛔ 其余一律 `CourseDataNormalizationError`：双周、逗号组合、多段组合、单个周次号、
  带"第"字前缀、波浪号、全角数字、`M < N`、`N < 1` 等。

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

## 当前接口

- 输出：`CourseOffering[]`（符合 `schemas/course_offering.schema.json`，`meetings[]` 至少 1 段）；
- 跨模块公共边界：`CourseDataProvider.get_course_offerings(semester) -> list[CourseOffering]`
  （见 `docs/interfaces/integration.md`，**已冻结**，不得私自修改）；
- **内部接口（非公共契约）**：`OpeningCoursesPageFetcher`（2B-2C0）——
  只用于 Course Data 内部分页采集，**不加入 Integration**；
- **尚未暴露任何真实 API**：`/api/v1/mock/*` 仍是独立的永久 Mock 回放通道。

## 当前阻塞

- **当前主 blocker = G11 的业务语义确认**（不是继续扩大结构诊断）：
  - **结构层取证已完成**：第 1 页 200 条中 **39 条完全没有 `teachingTimePlaceStr`**
    （161 条非空，其余形态 0）；C1C 相关性诊断进一步显示
    **结构差异集中在排课相关字段**（`timePlaceId` 38/39 缺失 vs 161/161 存在；
    `weekDay` 38/39 缺失 vs 12/161 缺失），而 `limitNumber` / `selectedNumber`
    在 39 条中**完整存在**，分类字段**未发现 `missing` 组独占值**
    （见 §4.7.1；**只有边际计数，无逐 row 交叉证据**）；
  - **业务语义已获得部分界面证据**（C1D，**n = 2**）：两条典型候选在官方 UI 中
    **均为普通教学班行**、时间 / 周次 / 地点**完全空白**且**无状态文字**
    （⚠️ **n = 2 不能代表全部 39 条**）；
  - **仍未解决 / 仍待裁决**：缺 schedule 字段的**业务原因** / 这些记录的**业务类型** /
    是否属于**有效可选教学班** / 是否应进入 Planner / **全学期缺失比例** /
    是否应修改 `CourseOffering` 公共契约（→ 已形成 **`DG-07` 草案**，**待架构裁决**）；
  - **当前 blocker = `DG-07` 待 Architecture Lead 裁决**；
    ⛔ **不继续扩大结构诊断**，也⛔ **不实施**任何 workaround；
  - 在**实施**落地之前，`collect()` 仍 **按设计 fail closed**
    （公共契约 `CourseOffering.meetings` `minItems = 1`），
    ⛔ **本轮未实施 DG-07**，也**未修改**任何 Schema；
  - ⚠️ **39/200 只描述第 1 页样本，不得外推**；**C1D 的 n = 2 同样不得外推**；
  - ⛔ **不声称 G11 resolved**（**contract decision approved;
    implementation pending; school-side business cause still unknown**）；
- **DG-07 已批准、但契约本身仍未改变**：`DG-07` =
  **`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**，
  **公共契约（`schemas/` / `docs/interfaces/`）本轮未被修改**，
  `backend/app/models/contracts.py` 的 `min_length=1` 与既有回归测试
  （锁定 `meetings: []` 必须失败）**均保持不变**，
  ⛔ **在实施任务书下达前，任何代码都不得按 `meetings = []` 已生效来写**；
- **真实完整学期程序化采集未完成**：因上述数据阻塞而中止；
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

## 下一步

- ✅ **1 页结构诊断已完成**（2B-2C1B，由**负责人手动执行**）：
  `diagnoseSchedulePresence({ semester: "2026-1" })` 已返回第 1 页聚合计数
  （`total_rows = 200`，`missing = 39`，`non_empty_string = 161`，其余形态 0）；
- ✅ **1 页相关性诊断已完成**（2B-2C1C，由**负责人手动执行**）：
  `diagnoseMissingScheduleCorrelation({ semester: "2026-1" })` 的真实聚合结果
  **已回填**（见本文「C1C 真实相关性诊断结果」与缺口报告 §4.7.1）；
  ⛔ **不再需要重复运行**这两个诊断；
- ✅ **G11 业务语义最小核验已完成**（2B-2C1D，**人工 UI，n = 2**，由**负责人本人**完成）：
  两条典型候选在官方 UI 中**均为普通教学班行**，时间 / 周次 / 地点**完全空白**、
  **无状态文字**；**契约缺口 `DG-07`** 已形成并获批
  （`docs/data/DATA_GATE_DECISIONS.md` §17）；⛔ **不再要求重复人工核验**；
- ✅ **DG-07 架构裁决已落档**（2026-10-01）：
  **`APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**
  —— **契约处理方向已批准**（`meetings` `minItems: 1 → 0`，`required` 不变），
  ⛔ **本轮未实施**（`schemas/` / `docs/interfaces/` **未被修改**）；
- **下一步：等待 DG-07 的实施任务书**（**IMPLEMENTATION PENDING**）；
  ⛔ **本模块不自行实施** DG-07（不改 Schema / Interface / 代码 / 测试），
  也⛔ **不自行拆分或命名实施阶段**；
  Data Gate **仍保持 Reopened**（⛔ **未 CLOSED**；⛔ **DG-01 – DG-06 不重新打开**），
  关闭前置条件见 `DATA_GATE_DECISIONS.md` §17.15；
- **G11 仍未解决**（见 `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` §4.7.2）：
  **学校侧业务原因仍未查明**；缺失原因 / 这些记录的业务类型 /
  是否属于有效可选教学班 / 是否应进入 Planner / 全学期缺失比例 仍**未确认**；
  ⛔ **不声称 G11 resolved**（**contract decision approved; implementation pending;
  school-side business cause still unknown**）、⛔ **不推断学校业务状态**；
- 采集器与 Capture Bridge 目前**不接入** Integration / Planner / API / 前端产品 UI
  （真实 Capture Bundle 的导入 UI 属后续步骤）；
- `max_pages` 是**内部安全阀**，不是学校侧参数；
  只能取得部分范围时**必须显式记录 completeness**，**不得宣称 complete**（C9）；
- **完整 semester snapshot**：目标为 **2026-1**，取得后以 `OfferingSnapshot` 表达，
  并由 `SnapshotCourseDataProvider` 供 Integration 消费；
- ⛔ 上述后续步骤（含 **DG-07 实施**）都属于后续任务书范围，**本轮不得自行开始**；
  ⛔ **本轮 Builder 未登录 SYSU、未发任何真实请求、未生成真实数据、未修改任何代码**，
  也**不**把 `partial` snapshot 接入 Integration；
  ⛔ **DG-07 仍为 `IMPLEMENTATION PENDING`**：在实施任务书下达前，
  **不得**在代码中把 `meetings = []` 当作**已生效**的公共契约。
- ⛔ **不得开始**任何实施阶段（亦**不得**自行命名 / 拆分实施阶段）。
