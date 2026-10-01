# Course Data 当前状态

> 最后更新：2026-10-01（**Phase 2B-2C1A：SYSU Authorized Browser Transport + Capture Bridge** 完成，等待 Reviewer）
>
> ⚠️ **准确表述（不得夸大）**：
> **真实 Course Data 尚未完成**，**尚未取得 complete semester snapshot**。
> **SYSU 浏览器端授权采集器代码已准备**（用户显式触发、串行、same-origin、
> 只保留最小字段并把 segment 内教师脱敏为 `REDACTED`）；
> **Capture Bridge 已完成**（本地 Capture Bundle → 复用分页核心 → `OfferingSnapshot`）。
> **尚未执行真实完整学期程序化采集** —— 真实 smoke run 由负责人在 Reviewer 合并后**手动**执行。
> 后端 Python 侧仍然**零网络**：没有 endpoint、没有认证处理、**不会自动发起 SYSU 请求**。

## 阶段状态

```text
D5 教学班技术侦察                                  ✅ 已完成（OFFERING-001，2026-1）
Data Gate（契约裁决 + 实施）                        ✅ 已完成（C1–C11 全通过）
Course Data normalization core（2B-2A）             ✅ 已完成
teachingTimePlaceStr parser（2B-2B）                ✅ 已完成（依据私密脱敏样本，未入 Git）
本地 Raw-response import adapter（2B-2B）            ✅ 已完成（零网络）
分页采集核心 Pagination Core（2B-2C0）              ✅ 已完成（零网络；fetch_page 由外部提供）
SYSU 分页参数人工验证（pageNo / pageSize / total）   ✅ 已完成（前两页；见下）
浏览器端授权采集器代码 + Capture Bridge（2B-2C1A）   ✅ 代码已准备（未执行真实采集）
真实完整学期程序化采集                              ⏳ 未执行（负责人手动 smoke run）
完整 semester snapshot                              ⏳ 未取得
```

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

### 浏览器端授权采集器 + Capture Bridge（Phase 2B-2C1A，本轮）
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

- **真实完整学期程序化采集尚未执行**：浏览器端采集器**代码已准备**，
  但**尚未对真实系统运行**；真实 smoke run 由负责人在 Reviewer 合并后**手动**执行；
  后端 Python 侧仍然**零网络**（没有 endpoint、没有认证处理、不会自动发起请求）；
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
- **本轮未生成任何真实 Capture Bundle**：仓库内**不含**真实采集产物；
  本地若产生，也属 **Real Sanitized Capture**，**不得进入 Git**；
- 仓库内**不含**真实教师姓名、真实教室、内部长 ID 取值、`readObj`、Raw JSON、
  Cookie / Session / Token、endpoint。

## 下一步

- **负责人手动 smoke run**（Reviewer 合并后）：在本人已登录、已有权限的教务页面加载
  `tools/sysu_course_offering_collector.js`，显式调用
  `await window.XuehangSysuCollector.collect({ semester: "2026-1" })`（默认 2 页），
  把产出的 Capture Bundle 保存到**非公开位置**，
  再用 `collect_captured_pages_snapshot(bundle, source=...)` 在本地验证；
  该 smoke run 预期得到 **partial**（2 页不可能覆盖整学期）；
- 采集器与 Capture Bridge 目前**不接入** Integration / Planner / API / 前端产品 UI
  （真实 Capture Bundle 的导入 UI 属后续步骤）；
- `max_pages` 是**内部安全阀**，不是学校侧参数；
  只能取得部分范围时**必须显式记录 completeness**，**不得宣称 complete**（C9）；
- **完整 semester snapshot**：目标为 **2026-1**，取得后以 `OfferingSnapshot` 表达，
  并由 `SnapshotCourseDataProvider` 供 Integration 消费；
- ⛔ 上述 smoke run 与后续导入 UI 都属于后续任务书范围，**本轮不得自行开始**；
  ⛔ **本轮 Builder 未登录 SYSU、未发任何真实请求、未生成真实数据**，
  也**不**把 `partial` snapshot 接入 Integration。
