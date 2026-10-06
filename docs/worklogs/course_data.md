# Course Data 工作日志

> 仅追加历史记录。新的 Agent 优先阅读 docs/status/course_data.md。

## 模板
### YYYY-MM-DD - 功能
- 本次目标：
- 已完成：
- 修改文件：
- 测试：
- 使用数据：Mock / Real
- 已知问题：
- 需要人工确认：
- 对其他模块影响：
- 下一步：

---

### 2026-09-30 - Phase 2B-2A：Course Data Normalization Core
- 本次目标：实现"**已确认 SYSU 字段 → 确定性转换 / 校验 → `CourseOffering` →
  带 completeness 的内部 snapshot → `CourseDataProvider.get_course_offerings(semester)`**"
  这条**纯本地、零网络**链路。**不抓数据、不猜未确认字段格式。**
- 起点：`main` = `aff6438c400731dd94e66a3d884ee45c774c4051`（Phase 2B-1 已合入）；
  新建 `feature/course-data-normalization-core`。
- 已完成：
  - 新增 Course Data 内部包 `backend/app/course_data/`（**不是跨模块公共契约**）：
    - `errors.py`：`CourseDataNormalizationError(ValueError)` —— 单一异常，不建层级；
    - `normalization.py`：
      - `build_course_offering(raw, *, meetings, source)`：
        只读取 `courseNum` / `courseName` / `classNumber` / `yearTerm` / `score` /
        `teachingName` / `limitNumber` / `selectedNumber`；
        输出 `data_source` **强制 `real`**，`source` **必须由调用方显式传入**；
        **`remaining_capacity = limitNumber - selectedNumber`（派生值）**；
        返回对象再由 `CourseOffering`（Pydantic）校验一次；
      - `expand_weeks(text)`：只支持 `1-17周` →
        `[1..17]`、`1-17单周` → `[1,3,…,17]`；其余格式一律拒绝。
  - 新增 `snapshot.py`：
    - `OfferingSnapshot(semester, offerings, completeness, reported_total=None)`：
      构造即校验 —— `semester` 一致、`data_source == real`、
      `(semester, course_id, class_id)` 不得重复（**不静默保留第一条、不按 `course_id` 去重**）、
      `partial` 可无 `reported_total`（若有须 `>= loaded_count`）、
      `complete` 必须有且 `== loaded_count`；传入 list 会被固化成 tuple；
    - `SnapshotCourseDataProvider`：持有快照；学期匹配返回列表，否则返回 `[]`；
      **零网络、无 Mock fallback**；结构上满足 Phase 2B-1 冻结的 `CourseDataProvider`，
      **不继承、不修改** Protocol。
- **本轮明确不做**（故意的阶段边界，不是功能遗漏）：
  - ⛔ **不解析 `teachingTimePlaceStr`**：public Git 没有真实脱敏 Raw string，
    猜分隔符 / 猜 segment 分隔 / 猜字段位置都属臆测；
    `meetings` 只能由**已经解析好的** `Meeting` 传入（传原始 dict 会被拒绝）；
  - ⛔ **`weekDay → Meeting.weekday` 一律不做**（C11 待确认）；
  - ⛔ **`openingSchoolName → Meeting.campus` 一律不做**（C11 待确认）；
  - ⛔ **不映射任何内部 ID**：`courseId` ≠ `course_id`、`class_ID` ≠ `class_id`；
    公共标识只取 `courseNum` / `classNumber`；
  - ⛔ 不映射 `courseCategoryName` / `openingUnitName` / `examMode` / `readObj` /
    `teachProgressSubmitState` / `openClass` / `outlineTypeNum`（暂缓字段）；
  - ⛔ meeting 级教师关联仍为 **known deferred representation gap**（`Meeting` 不含 `teacher`）。
- 修改文件：
  - 新增 `backend/app/course_data/{__init__.py,errors.py,normalization.py,snapshot.py}`
  - 新增 `backend/tests/test_course_data_normalization.py`、
    `backend/tests/test_course_data_snapshot.py`
  - 重写 `docs/status/course_data.md`（原"尚未完成真实教务页面技术侦察"已过时）
  - 本文件（**仅追加**）
  - 同步 `docs/status/agent_frontend.md`（最小阶段同步）、`docs/worklogs/agent_frontend.md`（追加）
- 测试：`cd backend && python -m pytest` → **237 passed / 2 skipped**
  （本轮前为 147 passed / 2 skipped，**新增 90 个测试全部通过**；
  原测试全部继续通过，**未删除旧测试、未新增 skip、未放宽 Schema**）。
  覆盖：字段映射、`remaining_capacity` 派生、multi-meeting 不丢失、`data_source` 强制 real、
  `source` 由调用方传入、缺字段 / 非法 `score` / `selectedNumber > limitNumber` / `meetings=[]` 失败、
  两种周次格式通过 + 未确认格式失败、内部 ID 与暂缓字段不进入 `CourseOffering`、
  `weekDay` / `openingSchoolName` / `teachingTimePlaceStr` 不被自动映射、
  duplicate key 失败、completeness 四类规则、Provider 结构一致性 / 学期匹配 / 空返回 /
  新鲜 list、以及**代码边界检查**（Course Data 包不导入任何网络 / 抓取 / Mock 回放依赖，
  代码字符串字面量中不出现 endpoint / 凭据痕迹）。
- 使用数据：**Mock**（测试全部使用人工虚构的 source-shaped dict 与占位教师名 `"示例教师A"`）
- 已知问题：`selectedNumber` 本轮按**必要字段**处理（缺失即失败）；
  理由是它是已确认真实字段且 `remaining_capacity` 需要它 —— 若真实数据存在缺失情形，
  需在取得脱敏样本后重新确认（**不自行放宽**）。
- 需要人工确认：① `weekDay → weekday`；② `openingSchoolName → campus`；
  ③ `teachingTimePlaceStr` 的真实格式；④ meeting 级教师关联（均为 C11 待确认项）
- 对其他模块影响：**无公共接口变化** —— `schemas/`、`docs/interfaces/`、
  `integration/ports.py`、`orchestrator.py` **一律未改**；
  `SnapshotCourseDataProvider` 只是**结构上**满足已冻结的 `CourseDataProvider`。
- 下一步：等待 Reviewer 验收 Phase 2B-2A。
  之后是**真实 `teachingTimePlaceStr` parser** 与**授权 import adapter**（Phase 2B-2B），
  ⚠️ **须等新一轮任务书，不自行开始**。

---

### 2026-09-30 - Phase 2B-2A Reviewer 证据边界修复
- 本次目标：只修"**实现能力超过真实证据**"的三处，**不扩大范围**。
  起点：同一分支，head `e87d3af8dc546ed26258366bd68878343221680d`。
- **修复 1：`score` 只接受字符串数字**
  - 真实证据（`SYSU_COURSE_OFFERING_RECON.md`）只确认 `score = 字符串数字`；
  - `_parse_credit()` 现在**只接受 `str`**：`"3"` / `"3.0"` / `" 3 "`；
  - ⛔ **不再接受 `3` / `3.0`（数值型）** —— 数值型 `score` **尚无真实来源证据**，当前拒绝；
  - bool / 负数 / 空串 / 非数字文本继续拒绝；
  - 测试相应调整：`3`、`3.0` 移入"非法"参数集，并新增专用用例
    `test_numeric_score_is_rejected_without_evidence` 明确说明"数值型 score 尚无真实来源证据"。
- **修复 2：周次保持最窄实现**
  - 继续支持 `expand_weeks("1-17周")` 与 `expand_weeks("1-17单周")`；
  - ⛔ **删除"`3-3周` 为已确认合法格式"这一说法与用例**；
    区间现在**必须满足「结束 > 开始」**（真区间），
    退化区间（`3-3周`、`5-5单周`）以及其它未经真实样本确认的范围泛化**统一抛
    `CourseDataNormalizationError`**；
  - 新增 `test_degenerate_week_range_is_rejected_without_evidence`；
    原 `test_single_week_range_is_expanded` 改用真区间 `3-4周`；
    `3-3周` 也加入"未确认格式"参数集；
  - 后续 2B-2B 依**真实脱敏样本**再扩 parser。
- **修复 3：不虚构 SYSU 格式字符串**
  - 测试中原来使用的 `"周一第3-4节{第1-17周};周三第5-6节{第1-17单周}"` **看起来像真实 SYSU 格式**，
    已删除；
  - 改为不携带任何格式假设的占位常量 `UNPARSED_SCHEDULE_TEXT`；
    用例目的不变 —— 仍然只是证明 `build_course_offering` **不读取** `teachingTimePlaceStr`。
- **修复 4：`selectedNumber` 表述收紧（保留必填，不改行为）**
  - 在 `normalization.py` 与 `docs/status/course_data.md` 中删除任何可被读成
    "SYSU 所有记录必然都有 `selectedNumber`" 的说法；
  - 准确表述为：**当前 2B-2A 的 narrow normalizer 基于已观察到的 D5 字段要求 `selectedNumber`；
    该字段是否总是存在目前没有证据；若后续真实脱敏样本出现缺失，再据实调整内部实现。**
- **明确未改**（守住禁止项）：snapshot completeness 规则、duplicate key 判定、
  `SnapshotCourseDataProvider` 行为、`schemas/`、`docs/interfaces/`、Integration、API、网络代码
  **一律未修改**。
- 修改文件：
  - `backend/app/course_data/normalization.py`（`_parse_credit` / `_week_range_bounds` /
    `expand_weeks` 文档与 `_REQUIRED_RAW_FIELDS` 注释）
  - `backend/tests/test_course_data_normalization.py`
  - `docs/status/course_data.md`（补"证据边界"与"周次最窄实现"说明）
  - `docs/status/agent_frontend.md`（Phase 2B-2A 小节补证据边界一句）
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **243 passed / 2 skipped**
  （修复前 237 passed / 2 skipped；原测试全部继续通过，**未删除旧测试、未新增 skip**）。
- 使用数据：**Mock**（人工虚构的 source-shaped dict 与占位教师名 `"示例教师A"`）
- 下一步：等待 Reviewer 复验。⚠️ **不 merge，不自行进入 2B-2B**。

---

### 2026-09-30 - Phase 2B-2A Reviewer 修复：`expand_weeks` 改为精确匹配
- 本次目标：修掉最后一个代码 blocker —— `expand_weeks()` 仍然接受**任意** `x-y周` / `x-y单周`，
  超过了现有真实证据。Reviewer 已确认 `score` / `selectedNumber` / `teachingTimePlaceStr` 三处修复通过。
  起点：同一分支，head `ee88ffca68426a8fe475af5f3fad94f23215980b`。
- **修改内容**：
  - `expand_weeks()` 从"区间形状匹配"改为**精确匹配已观察取值**：
    删除 `_PLAIN_WEEK_RANGE` / `_ODD_WEEK_RANGE` 两个正则与 `_week_range_bounds()`，
    新增 `_OBSERVED_WEEK_TEXTS = {"1-17周": (1, 17, False), "1-17单周": (1, 17, True)}`，
    以 `dict.get()` 精确命中；未命中即抛 `CourseDataNormalizationError`；
  - 错误信息写明："Phase 2B-2A 只接受已经观察到的两个取值：`1-17周`、`1-17单周`；
    其它范围**即使形状相似也暂时拒绝**（不猜）"；
  - 删除"`3-4周` 属已确认语法"的错误假设（原 `test_single_week_range_is_expanded`）。
- **测试调整**：
  - ✅ `1-17周` PASS、✅ `1-17单周` PASS（两个独立正向用例）；
  - ⛔ 新增 `test_similar_shaped_week_ranges_are_rejected_without_evidence`，
    参数含 **`3-4周` / `3-15单周` / `3-3周` / `2-18周`**；
  - 原"未确认格式"参数集补入 `17-1周`、`0-17周`；
  - 删除已不成立的 `test_week_range_bounds_are_checked`（边界校验随形状泛化一起移除）。
- **文档同步**：
  - `docs/status/course_data.md`：周次一节改写为"**只接受两个已观察取值，精确匹配，不做形状泛化**"，
    删掉"必须满足结束 > 开始（真区间）"这一已被取代的表述；
  - `docs/status/agent_frontend.md`：同步周次口径；
    并把旧统计「90 个测试」「237 passed / 2 skipped」更新为当前实际值
    「**99 个测试**」「**246 passed / 2 skipped**」。
- **明确未改**：`snapshot.py`、`SnapshotCourseDataProvider`、`schemas/`、`docs/interfaces/`、
  Integration、API、网络代码 —— 一律未修改。
- 修改文件：
  - `backend/app/course_data/normalization.py`
  - `backend/tests/test_course_data_normalization.py`
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **246 passed / 2 skipped**
  （修复前 243 passed / 2 skipped；原测试全部继续通过，**未删除旧测试、未新增 skip**）。
- 下一步：等待 Reviewer 复验。⚠️ **不 merge，不自行进入 2B-2B**。

---

### 2026-09-30 - Phase 2B-2B：Schedule Parser + Local Import Adapter
- 本次目标：用负责人单独提供的**私密脱敏样本**作为**唯一证据**，实现
  `teachingTimePlaceStr` parser 与**纯本地** Raw-response import adapter：
  `Raw → ParsedScheduleSegment[] → Meeting[] → build_course_offering() → CourseOffering[] → OfferingSnapshot`。
  **不联网、不登录、不写 fetch client、不写 Cookie / Session / Token、不做分页请求、不接 API / 前端。**
- 起点：`main` = `266b11908ae47131e686a395f709dd4c46a60c5c`；
  新建 `feature/course-data-schedule-import-core`。
- **私密证据处理（重点合规项）**：
  - 负责人提供的**私密脱敏样本**（Sanitized Sample，`source_id = OFFERING-001`）
    仅在**本地**阅读；**未 `git add`、未提交、未复制进 tests fixture、未复制进 docs、未复制进 worklog**
    （本文件也**不记录该样本的文件名**）；
  - `git status` 与最终提交中**不含**该文件；
  - 测试全部使用**人工虚构的结构等价样本**（`示例教师A` / `示例校区` / `示例教学楼-2108` 等）；
  - 文档只记录**结构性汇总结论**（分隔符、字段数、是否存在地点、周次/节次形态），
    **不含** Raw string、教师姓名、教室、内部 ID、`readObj`。
- **新增 `backend/app/course_data/schedule_parser.py`**：
  - `ParsedScheduleSegment(meeting, teacher, activity)`（frozen dataclass，**内部对象**）；
  - `parse_teaching_time_place(text) -> list[ParsedScheduleSegment]`：
    - `segment separator = ","`、`field separator = "/"`；
    - 无地点 **5 字段**（weeks/weekday/sections/teacher/activity）；
      有地点 **6 字段**（weeks/weekday/sections/**location**/teacher/activity）；
    - **最多一个**末尾逗号：单个末尾逗号产生的空 segment 忽略；
      ⛔ 多个末尾逗号（`seg,,` / `seg,,,`）**失败**（不再用 `while` 静默吞）；
      **中间空 segment**（`seg1,,seg2`）→ `CourseDataNormalizationError`（不静默忽略）；
    - 字段数非 5/6 → fail closed；
    - 输出顺序 == Raw 顺序（**不排序、不丢段、不合并**）；
  - `parse_weekday()`：只接受 `星期一` … `星期日`；未知 token（`星期天` / `周一` / `Monday` / 空）失败；
  - `parse_sections()`：`第N-M节`，`N ≥ 1` 且 **`M ≥ N`**（**允许 `M == N`**，`第4-4节` 合法）；
  - 地点：只按**第一个 `-`** 切 → `campus` = 第一段、`classroom` = 其余完整文本；
    缺 `-` / campus 空 / 教室空 → 失败；**不进一步猜 building / room**；
  - `extract_meetings()`：只把 `Meeting[]` 投影给公共契约，丢弃 `teacher` / `activity`；
  - ⛔ **`weekDay` 完全不参与**：`weekday` 一律来自 segment 自身
    （样本显示 Raw `weekDay` 顺序**不能安全假设**与 segment 顺序一致，更不得按位置 zip）；
  - ⛔ **`openingSchoolName` 不是 `campus` 的 fallback**（无地点 segment → `campus=None` / `classroom=None`）；
  - **隐私卫生**：错误信息**不回显** location / teacher / activity 取值（只回显段序号、
    字段数与 weeks/weekday/sections 这类非个人 token）。
- **修改 `backend/app/course_data/normalization.py`**：
  - `expand_weeks()` 依据**新证据**从"两个精确取值"扩为
    **普通连续周次 `N-M周`（`N ≥ 1`、`M ≥ N`，含 `M == N`）** + **单周仍只允许 `1-17单周`**；
  - ⛔ **单周不泛化**为任意 `N-M单周`（尚无证据）；
  - 仍拒绝：双周、`1,3,5周`、`第1-17周`、`1~17周`、全角数字、`M < N`、`N < 1`、单个周次号等；
  - 模块 docstring 同步（`teachingTimePlaceStr` 的解析位置指向 `schedule_parser.py`）。
- **新增 `backend/app/course_data/importer.py`**：
  - `import_opening_courses_response(payload, *, semester, source, completeness) -> OfferingSnapshot`；
  - 校验 `code == 200`（整型、非 bool）、`data` 为对象、`data.total` 为非负整数（非 bool）、
    `data.rows` 为对象数组（str/bytes 不算）；
  - 逐行 `teachingTimePlaceStr` → `Meeting[]` → `build_course_offering()`；按 Raw 顺序；
  - **任意一行失败 → 整体失败**（⛔ 不 fallback、不重试、不"尽力解析"、不跳过坏 row）；
  - **`completeness` 由调用方明确给出**：**不因 `len(rows) == total` 自称 complete**；
  - semester 一致性 / real-only / duplicate key / completeness **全部交由 `OfferingSnapshot`**，
    adapter **不重复实现**；
  - 错误信息不回显 Raw row 内容。
- **`backend/app/course_data/__init__.py`**：导出新增符号并更新包说明（含 2B-2B 阶段边界）。
- **新增测试**：
  - `backend/tests/test_course_data_schedule_parser.py`：5/6 字段、多 segment 全保留且顺序不变、
    末尾逗号（最多一个）忽略、**中间空段 FAIL**、字段数异常 FAIL、
    周次 `1-5周` / `1-6周` / `1-8周` / `6-6周` / `7-8周` / `10-17周` / `1-17单周`、
    单周不泛化 FAIL、星期映射与未知 token FAIL、`第1-2节`/`第4-4节` 合法与非法节次 FAIL、
    地点切分 / 无地点 `None` / location 缺 `-` FAIL、teacher & activity 内部保留、
    **公共 `Meeting` 无 `teacher`**、错误信息不回显敏感字段；
  - `backend/tests/test_course_data_importer.py`：partial / complete、顺序保留、同课多班保留、
    `data_source == real` 与 `source` 透传、多 segment 保留、
    **`weekDay` 不用于 weekday**、**`openingSchoolName` 不用于 campus**、内部 ID / 暂缓字段不泄漏、
    code / data / total / rows 各类畸形 FAIL、缺 `teachingTimePlaceStr` FAIL、
    **坏 row 导致整体失败**、completeness 交由 `OfferingSnapshot`（不猜）、
    duplicate key FAIL、semester mismatch FAIL、无 Mock fallback；
  - `backend/tests/test_course_data_normalization.py`：周次测试按新证据重写。
- 修改文件：
  - 新增 `backend/app/course_data/schedule_parser.py`、`backend/app/course_data/importer.py`
  - 修改 `backend/app/course_data/normalization.py`、`backend/app/course_data/__init__.py`
  - 新增 `backend/tests/test_course_data_schedule_parser.py`、`backend/tests/test_course_data_importer.py`
  - 修改 `backend/tests/test_course_data_normalization.py`
  - 更新 `docs/data/SYSU_COURSE_OFFERING_RECON.md`（**新增 §7A 脱敏汇总结论**，无 Raw 内容）
  - 更新 `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **355 passed / 2 skipped**
  （本轮前 246 passed / 2 skipped；**旧测试全部继续通过，未删除旧测试、未新增 skip、未放宽校验**）。
  `test_course_data_snapshot.py` 里的**包边界检查会自动覆盖新增模块**（零网络、无 endpoint、无凭据痕迹）。
- 使用数据：**Mock**（测试全部为人工虚构样本）；真实证据只以**脱敏汇总**形式进入文档
- 已知问题：**真实受控获取仍未实现**（Phase 2B-2C）；完整 2026-1 snapshot 未取得
- 需要人工确认：无（未发现公共契约不足，本轮**无需**【接口变更请求】）
- 对其他模块影响：**无公共接口变化**
- 下一步：等待 Reviewer 验收 Phase 2B-2B。之后是 **Phase 2B-2C 真实受控获取**，
  ⚠️ **须等新一轮任务书，不自行开始**。

---

### 2026-09-30 - Phase 2B-2C0：Course Data Pagination Core
- 本次目标：新增**零网络**分页采集核心，把多页 Raw 逐页交给**已审核通过的** importer 标准化，
  再按**证据链**判定最终 `completeness`。`fetch_page` 本轮**只能由测试 Fake 提供**；**不实现真实 HTTP**。
- 起点：`main` = `6485dd15491a1f971927f853ffb032f3f8e71c4b`；
  新建 `feature/course-data-pagination-core`。
- **新增 `backend/app/course_data/pagination.py`**：
  - 内部 Protocol `OpeningCoursesPageFetcher.fetch_page(*, semester, page_no, page_size) -> Mapping`
    （`@runtime_checkable`）—— **Course Data 内部接口**，**不进** `/docs/interfaces`、**不加入** Integration；
  - `collect_opening_courses_snapshot(fetcher, *, semester, source, page_size, first_page_no, max_pages)
    -> OfferingSnapshot`：
    - **严格串行**取页：`first_page_no`、`first_page_no + 1`、…；⛔ 不并发、⛔ 不预取下一页；
    - 每页**复用** `import_opening_courses_response(..., completeness="partial")`，
      **不重写** Raw parser / normalizer；
    - **total 一致性**：第一页 `reported_total` 记为 `expected_total`，
      后续每页必须**完全相等**；⛔ 不采用最新 / 最大 / 最小值（变化即 FAIL）；
    - **complete 证据链**：所有页成功解析 + 每页 total 一致 + 累计 `loaded_count == expected_total`
      + 无重复教学班（交给 `OfferingSnapshot`）+ 无中途空页 + 无请求错误；
    - **partial**：达到 `max_pages`（**安全阀**）仍未取满 → `completeness="partial"`，
      `reported_total` 如实记录；
    - **提前空页**（`loaded_count == 0` 且累计 < total）→ FAIL；**累计超限** → FAIL；
    - **跨页重复**：分页器**不自行去重**（不 `set()` / 不建 dict / 不留第一条或最后一条），
      交由 `OfferingSnapshot` 的 `(semester, course_id, class_id)` 判定 → FAIL；
    - 按**原页序 + 原行序**累积，不重排；
    - fetcher 异常 / 任一行解析失败 → **原样向上抛**（⛔ 不 retry / fallback / 跳页 /
      不返回"看起来差不多"的 complete）；
    - 参数校验：`semester` / `source` 非空字符串；`page_size ≥ 1`；`first_page_no ≥ 0`；`max_pages ≥ 1`
      （`bool` 不算整数）；**非法即 fail closed 且不调用 fetcher**；
    - **分页参数无默认值**，且**不假定 `page_no` 从 1 开始**（真实取值尚未人工验证）；
    - 取满后**不再请求下一页**；`total == 0` + 空 rows → **complete**（`loaded_count = 0`）且不多请求。
- **`backend/app/course_data/__init__.py`**：导出 `OpeningCoursesPageFetcher` 与
  `collect_opening_courses_snapshot`，并更新包说明（含 2B-2C0 阶段边界与 `partial` 使用限制）。
- **新增 `backend/tests/test_course_data_pagination.py`**（54 个测试，全部使用测试内 Fake Fetcher）：
  单页 / 两页 / 三页 complete、`first_page_no=1` 与 `first_page_no=0` 的**调用序列**、
  `semester` / `page_size` 透传、`total=0` 立即 complete 且不再请求、
  `max_pages` 截断 → partial（`reported_total` 正确）、`max_pages` 是安全阀而非页数、
  **第二页 total 变化（减少 / 增加）→ FAIL**、**达到 total 前空页 → FAIL**、
  累计超限 → FAIL、单页行数超 total → FAIL、
  **跨页重复 → FAIL**（同课不同班保留）、页序与行序保持、
  fetcher 异常（首页 / 第二页）原样上抛、某页 parser 失败 / 畸形响应 → 整体 FAIL、
  semester 不一致 FAIL、`data_source == real` 与 `source` 透传、
  非法 `page_size` / `first_page_no` / `max_pages` / `semester` / `source` → FAIL 且**未调用 fetcher**、
  分页核心**无网络 import**、**不导入 / 不构造 Provider**（AST 检查）、
  `partial` 不被包装成生产 Provider。
- 修改文件：
  - 新增 `backend/app/course_data/pagination.py`
  - 修改 `backend/app/course_data/__init__.py`
  - 新增 `backend/tests/test_course_data_pagination.py`
  - 更新 `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **420 passed / 2 skipped**
  （本轮基线 366 passed / 2 skipped；**旧测试全部继续通过，未删除旧测试、未新增 skip、未放宽校验**）。
  `test_course_data_snapshot.py` 里的**包边界检查自动覆盖了 `pagination.py`**（零网络 / 无 endpoint / 无凭据痕迹）。
- 使用数据：**Mock**（测试全部为人工虚构 page / row）
- 已知问题：**真实网络 Transport 未实现**（2B-2C1）；分页参数未经人工验证；完整 2026-1 snapshot 未取得
- 需要人工确认：`page_size` / `first_page_no` / `max_pages` 的真实取值（**因此代码不写默认值、不假定起点**）
- 对其他模块影响：**无公共接口变化**；`SnapshotCourseDataProvider` **未修改**；
  `partial` snapshot **未接入** Integration / Planner
- 下一步：等待 Reviewer 验收 Phase 2B-2C0。之后是 **Phase 2B-2C1 真实网络 Transport**，
  ⚠️ **须等新一轮任务书，不自行开始**。

---

### 2026-10-01 - Phase 2B-2C1A：SYSU Authorized Browser Transport + Capture Bridge
- 本次目标：实现 **浏览器端「显式触发」授权采集器**（same-origin 串行取页、最小字段、教师脱敏）
  与 **Python Capture Bridge**（本地 Capture Bundle → 复用分页核心 → `OfferingSnapshot`）。
  ⛔ **不实现**后端直连学校认证的 HTTP client；⛔ **不接** Integration / Planner / API / 前端产品 UI。
- 起点：`main` = `3ba7cc4a7c2db3bcd255e8ad8c7f6bc8b8fecc2d`；
  新建 `feature/course-data-sysu-authorized-transport`。
- **架构口径**：认证完全交给浏览器既有登录状态（`credentials: "same-origin"`），
  代码**不读取 / 不保存 / 不打印 / 不导出**任何浏览器端认证状态；
  **未要求负责人提供认证信息 / HAR**。
- **新增 `tools/sysu_course_offering_collector.js`（SYSU-specific Transport）**
  - IIFE 包装，**加载脚本不发任何请求**：无顶层调用、无定时轮询、无并发；
    唯一入口 `window.XuehangSysuCollector.collect({...})`，必须由用户显式调用；
  - **hostname guard**：`window.location.hostname` 必须是 `jwxt.sysu.edu.cn`，否则直接失败；
  - **参数（SYSU 已验证）**：`FIRST_PAGE_NO = 1`、`MAX_PAGE_SIZE = 200`、`DEFAULT_PAGE_SIZE = 200`；
    `pageSize` 越界即失败（SYSU 专有取值**不写进通用 pagination.py**）；
  - **限速与安全阀**：`DEFAULT_DELAY_MS = 1500`、`MIN_DELAY_MS = 1000`；
    `DEFAULT_MAX_PAGES = 2`、`ABSOLUTE_MAX_PAGES = 50`（客户端安全上限，非学校限制）；
    `maxPages > 2` 时 `window.confirm()` 明确确认，取消则 **0 个请求**；
  - **严格串行**：`for` + `await sleep(delayMs)`，不并发、不预取；
  - **请求形状**：`POST` 已确认路径 + `?_t=Date.now()`（仅复现已观察形态，不赋予业务语义），
    body = `{pageNo, pageSize, total: true, param: {yearTerm}}`；
  - **响应校验**：HTTP 成功、`content-type` 含 JSON（否则视为疑似登录页）、JSON 可解析、
    `code === 200`、`data` 是对象、`total` 非负整数、`rows` 是数组；
    **401 / 403 立即停止并标记 BLOCKED**；
  - **停止规则**：首页记 `expectedTotal`；后续 `total` 变化 → 失败；
    达到 total 前出现空页 → 失败；累计 > total → 失败；累计 == total → 不再请求；
    达到 `maxPages` 仍未取满 → 正常停止；**不自行声称 complete**（`claimedComplete: false`）；
  - **数据最小化**：每条 row 只保留 8 字段
    （`courseNum` / `courseName` / `classNumber` / `yearTerm` / `score` / `limitNumber` /
    `selectedNumber` / `teachingTimePlaceStr`）；内部 ID 与暂缓字段全部丢弃；
  - **教师脱敏**：segment 内 teacher → `REDACTED`（5 字段第 4 项 / 6 字段第 5 项）；
    保持 segment 顺序、`/`、`,`、**最多一个** trailing comma、location 等原文；
    非 5/6 字段 / 多个 trailing comma / 中间空 segment → **整体失败，不生成 bundle**；
  - 产出 Capture Bundle：`{format, semester, first_page_no, page_size, pages}`；
    **不含** source / 认证 / 用户标识 / 姓名学号 / 内部 ID / 教师。
- **新增 `backend/app/course_data/captured_pages.py`（零网络 Bridge）**
  - `CapturedPagesFetcher`：**只回放** bundle 中已捕获的页；结构上满足 `OpeningCoursesPageFetcher`，
    **不继承、不修改** Protocol；请求的 `semester` / `page_size` / `page_no` 与 bundle 不一致即失败；
  - bundle 校验：`format` 匹配、`semester` 非空、`first_page_no ≥ 0`、`page_size ≥ 1`、
    `pages` 非空数组、每个 `page_no` 唯一且**从 `first_page_no` 起连续**（`1,3` / `2,3` / 重复 → 失败，**不排序修复**）；
  - `collect_captured_pages_snapshot(bundle, *, source)`：**复用** `collect_opening_courses_snapshot()`，
    `max_pages = len(pages)`，**不重新实现** completeness
    （2 页 smoke capture 未取满 → **partial**；累计 == total → **complete**）；
  - `load_capture_bundle(path)`：只读**调用方显式给出**的本地 UTF-8 JSON（stdlib `json`，**无新依赖**），
    **无默认路径、不扫描目录、不复制进仓库**；
  - 错误信息只输出结构性信息，**不回显** Raw row / `teachingTimePlaceStr` 原文 / teacher。
- **`backend/app/course_data/__init__.py`**：最小导出新符号并更新包说明（含 2B-2C1A 阶段边界）。
- **新增测试**
  - `backend/tests/test_course_data_captured_pages.py`：2 页 → partial、完整 → complete、
    `first_page_no` / `page_size` / 页码连续性、重复 page_no / 缺页 / 乱序 / 元数据不符 → FAIL、
    格式 / semester / 元数据 / pages 容器 / response 类型非法 → FAIL、第二页 total 变化 → FAIL、
    跨页重复 → FAIL、parser 失败整体 FAIL、空页 → FAIL、非法 source → FAIL、
    回放器三态不一致 → FAIL、`load_capture_bundle` 用 **tmp_path 人工虚构 JSON**
    （有效 / 缺文件 / 非 JSON / 非法 bundle / 必须显式传 path）、
    Bridge **零网络且不 import Integration / 不构造 Provider**（AST 检查）、
    错误信息不回显 Raw row；
  - `backend/tests/test_sysu_collector_guard.py`：采集器**静态安全守卫** ——
    不得出现读取认证状态 / 导出认证头 / 后端 HTTP 客户端的写法；
    IIFE 包装、`fetch(` 仅 1 处且在 `await` 内、无 `setInterval`、无 `Promise.all` /
    `allSettled` / `race`、挂载后不自动调用 `collect()`；
    必须存在 hostname guard、`pageSize ≤ 200` 校验、最小延迟、默认 / 绝对页数、
    超过 smoke 页数的 `confirm()`、`same-origin`、请求形状、逐页校验、停止规则、
    `claimedComplete: false`、8 字段白名单（且 16 个禁止字段不出现）、教师脱敏与 5/6 字段判定。
- 修改文件：
  - 新增 `tools/sysu_course_offering_collector.js`
  - 新增 `backend/app/course_data/captured_pages.py`
  - 修改 `backend/app/course_data/__init__.py`
  - 新增 `backend/tests/test_course_data_captured_pages.py`、`backend/tests/test_sysu_collector_guard.py`
  - 更新 `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **509 passed / 2 skipped**
  （本轮基线 420 passed / 2 skipped；**旧测试全部继续通过，未删除旧测试、未新增 skip、未放宽校验**）。
- 使用数据：**Mock / 人工虚构**（Capture Bundle 与 Raw row 全部人工虚构）；
  **本轮未生成任何真实 Capture Bundle**，仓库内不含真实采集产物
- 需要人工确认：无（未发现公共契约不足，**无需**【接口变更请求】）
- 对其他模块影响：**无公共接口变化**；`SnapshotCourseDataProvider` **未修改**；
  采集器与 Bridge **未接入** Integration / Planner / API / 前端
- **实际 SYSU 请求数：0**（未登录、未运行采集器、未发任何真实请求、未生成 6892 条数据）
- 下一步：等待 Reviewer 验收 Phase 2B-2C1A。之后由**负责人手动 smoke run**（2 页，**预期 partial**）
  与真实 Capture Bundle 的导入 UI，⚠️ **须等新一轮任务书，不自行开始**。

---

### 2026-10-01 - Phase 2B-2C1A Reviewer 修复（3 项）
- 本次目标：只修 Reviewer 指出的 3 个必须修复项，**不进入真实 SYSU smoke run**。
  起点：同一分支，head `cd15dec59a7c7e13ed7ef1c1f7b3c94e42126fba`。
- **修复 1：SYSU `firstPageNo` 锁定为已验证的 1**
  - 问题：Collector 原来允许调用方传 `firstPageNo=0/2/...`，会对 SYSU 发起**未经验证**的页码请求；
  - 处理：`FIRST_PAGE_NO = 1` 保持不变；若 `options.firstPageNo` 被提供且 `!= 1` →
    **在任何取页调用之前**直接失败；实际使用的一律是常量
    （删除了"取调用方值 / 默认值"的三元回退写法）；
  - ⛔ **未修改** 通用 `backend/app/course_data/pagination.py`：
    它仍允许 generic `first_page_no >= 0`（SYSU 专有约束只属于本 Transport）。
- **修复 2：teacher 脱敏前必须验证原 teacher 非空**
  - 问题：原来空 teacher 也会被写成 `REDACTED`，等于**静默修复 Raw**，
    会让下游 Python parser 误以为该记录合法；
  - 处理：`redactSegmentTeacher()` 在替换前要求 teacher 是**非空字符串**；
    空 / 非字符串 → **整体失败**；错误信息**不回显** teacher 取值；
  - ⛔ **未修改** Python parser 的现有规则。
- **修复 3：Collector → Capture Bridge 序列化闭环**
  - 问题：`collect()` 返回 wrapper，但 Python Bridge 需要的是**裸 bundle**；
  - 处理：`toJson(result)` 改为 `JSON.stringify(result.bundle, null, 2)`，
    输出顶层即 `format` / `semester` / `first_page_no` / `page_size` / `pages`，
    可直接被 `load_capture_bundle(...)` 接受；
  - ⛔ `cancelled === true` 或没有 bundle 时 `toJson()` **失败，不生成伪 bundle**。
- 测试：`backend/tests/test_sysu_collector_guard.py` 新增 6 条静态守卫 ——
  `firstPageNo` 锁死（且校验早于取页调用）、空 teacher 不得被 REDACTED 修复
  （校验早于赋值）、teacher 错误信息不回显取值、`toJson` 输出裸 bundle
  （且不再序列化 wrapper）、取消 / 空结果时 `toJson` 失败、bundle 顶层键与 Python Bridge 一致。
- 修改文件：
  - `tools/sysu_course_offering_collector.js`
  - `backend/tests/test_sysu_collector_guard.py`
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **515 passed / 2 skipped**
  （修复前 509 passed / 2 skipped；旧测试全部继续通过，未删除旧测试、未新增 skip）。
  另用 `node --check` 仅做**语法解析**确认 Collector 源码合法（**未执行**该文件）。
- 使用数据：**Mock / 人工虚构**；**本轮未生成真实 Capture Bundle**
- **实际 SYSU 请求数：0**
- 未修改：`schemas/`、`docs/interfaces/`、`integration/`、`pagination.py`、`importer.py`、
  `schedule_parser.py`（parser）、`normalization.py`、`snapshot.py`、`main.py`、`api/`、
  `frontend/`、`mock_data/`
- 下一步：等待 Reviewer 复验。⚠️ **不 merge，不自行开始手动 smoke run**。

---

### 2026-10-01 - Phase 2B-2C1B：Schedule Presence Diagnostic
- 本次目标：新增一个**显式触发、只请求第 1 页一次**的**结构诊断**入口，
  为"真实 row 缺 `teachingTimePlaceStr`"这一新事实**取证**。
  **只取证、不裁决、不改 Schema**；Builder **不运行**诊断、**不发起任何真实请求**。
- 起点：`main` = `b0c4c751063ba2f93d6d10637470aaab2d68ea27`；
  新建 `feature/course-data-schedule-presence-diagnostic`。
- **背景（负责人已确认的真实事实）**：
  - 真实 smoke run 在真正的「**全校开设课程**」独立模块内完成；
  - **same-origin 请求成功**，第 1 页响应成功进入采集器；**认证不再是当前 blocker**；
  - **第 1 页至少 1 条 row 缺少 `teachingTimePlaceStr`**（**只登记"至少 1 条"，不登记精确条数**）；
  - 当前 `collect()` 因此 **按设计 fail closed**；**尚未生成真实 Capture Bundle**、
    **尚未取得 complete semester snapshot**；
  - ⚠️ **纠正导航描述**：「**选课**」与「**全校开设课程**」是**两个独立模块**。
- **`tools/sysu_course_offering_collector.js` 新增（在现有采集器内，不新建 Transport 文件）**：
  - 纯函数 `summarizeSchedulePresence(rows)`：把每条 row 归入**互斥且穷尽**的五类
    （`missing` / `null` / `empty_string` / `non_empty_string` / `other_type`），
    返回 `{ total_rows: rows.length, teachingTimePlaceStr: {...} }`；
  - `diagnoseSchedulePresence({ semester })`：
    - ✅ 复用现有 hostname guard 与取页函数（**不复制认证逻辑**）；
    - 固定 `DIAGNOSTIC_PAGE_NO = 1`、`DIAGNOSTIC_PAGE_SIZE = 200`、`total = true`，**只发 1 次请求**；
    - ⛔ 不接受 `maxPages` / `firstPageNo`，无循环、无重试、无并发；
    - 返回值只有聚合统计（`semester` / `page_no` / `page_size` / `reported_total` /
      `total_rows` / `teachingTimePlaceStr{...}`）；`total_rows` 取 `data.rows.length`（**不写死**）；
    - ⛔ 不返回 rows / row 下标 / 课程号 / 课程名 / 教学班号 / 教师 / 教室 / 原文 / 内部 ID；
    - ⛔ **不生成 Capture Bundle**、不做字段最小化、不做教师脱敏、不调用 `toJson`；
  - 顶部文档补充"诊断的定位：**取证**，不是 workaround"。
- **⛔ `collect()` 行为未变**：`minimizeRow` 仍要求 8 个必要字段齐备，
  缺 `teachingTimePlaceStr` **仍整体失败** —— 未改成跳过 / `meetings=[]` / 占位 `Meeting` / 标记 complete。
- **⛔ 本轮不决定如何修复**：`schemas/`、`docs/interfaces/`、`captured_pages.py`、`pagination.py`、
  `importer.py`、`schedule_parser.py`、`normalization.py`、`snapshot.py`、`integration/`、
  `main.py`、`api/`、`mock_data/`、`frontend/` **一律未修改**；
  `CourseOffering.meetings` 的 **`minItems = 1` 保持不变**。
- **新增缺口登记 G11**（`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`）：
  - **已确认**：至少一条真实 row 缺该字段；
  - **当前影响**：当前 importer / parser 无法构造 `meetings[minItems=1]`；
  - **未确认**：缺失原因 / 记录类型 / 是否应进入 Planner / 是否普遍 / 是否需要修改公共契约；
  - **§4.7** 明确写出"**只记录事实，不做任何 Schema 裁决**"，并禁止写成
    "缺排课 / 未排课课程 / 异步课程 / 暂无教室"等业务结论。
- **测试**：`backend/tests/test_sysu_collector_guard.py` 新增 7 条静态守卫 ——
  诊断已暴露且加载时不被自动调用；复用既有取页函数（`requestPage(` 3 处、`await requestPage(` 2 处）；
  固定 `pageNo=1` / `pageSize=200` 且只调一次、无分页选项与循环；
  不产出 bundle / 不做最小化 / 脱敏 / 序列化；返回值只有聚合键且不含 rows / 下标 / 业务字段；
  纯函数五桶穷尽；`collect()` 的 fail-closed 未改动（`minimizeRow` 内无 workaround）。
- 修改文件：
  - `tools/sysu_course_offering_collector.js`
  - `backend/tests/test_sysu_collector_guard.py`
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`（新增 G11 + §4.7 + 变更记录）
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **522 passed / 2 skipped**
  （本轮基线 515 passed / 2 skipped；旧测试全部继续通过，未删除旧测试、未新增 skip）；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**（仅语法解析，**未执行**该文件）。
- 使用数据：**Mock / 人工虚构**；**本轮未生成真实 Capture Bundle**
- 需要人工确认：缺字段的**业务含义**（本轮不推测）；后续是否发起【接口变更请求】
- **实际 SYSU 请求数：0**（Builder 未登录、未运行诊断）
- 下一步：等待 Reviewer 验收 Phase 2B-2C1B；之后由**负责人手动执行 1 页诊断**，
  再依据结果走正式【接口变更请求】。⚠️ **不 merge，不自行开始**。

### 2026-10-01 - Phase 2B-2C1B Reviewer 修复（6 项）
- 本次目标：按 Reviewer 意见做**证据边界与口径**修正，**不新增能力、不改契约**。
- 起点：`feature/course-data-schedule-presence-diagnostic`，HEAD `39d5f1d`（未 merge）。
- **① 来源登记**：`docs/data/DATA_SOURCE_REGISTRY.md` 新增 **`OFFERING-002`**
  （D5「全校开设课程」独立模块第 1 页真实结构 smoke，**Authenticated Official**，
  **Confirmed**）：新增登记表行、**新增 §4.1 明细块**、§6 汇总同步
  （已登记 **17 → 18**、Authenticated Official **4 → 5**、Confirmed **7 → 8**、
  来源清单 `OFFERING-001/002`、最近更新 **2026-10-01**）、追加变更记录。
  **只登记汇总事实，无 Raw row**；Cookie / Session / Token / Headers / HAR / Capture Bundle 不入库。
- **② 删除不成立的精确条数**：删除全部"**第 1 页第 N 条**"式表述（来自 JS 0-based `rowIndex`，
  该说法本身不成立），统一为"**第 1 页至少 1 条 row 缺少 `teachingTimePlaceStr`**"，
  并在 `status/course_data.md`、`status/agent_frontend.md`、缺口报告、两个 worklog 中显式注明
  **只登记"至少 1 条"，不登记精确条数**。
- **③ G11 补样本出处**：`REAL_TO_SCHEMA_GAP_REPORT.md` 的 G11 表行与 **§4.7** 均写明
  **样本出处：`OFFERING-002`**。
- **④ 缺口报告表头**：`分析框架 ＋ 四轮真实材料验证` →
  `分析框架 ＋ 四轮真实材料验证 ＋ Phase 2B-2C1B 真实 smoke 结构证据`。
- **⑤ 行号口径 1-based**（`tools/sysu_course_offering_collector.js`）：
  - 调用点改为 `minimizeRow(row, currentPageNo, rowIndex + 1)`
    （`data.rows.map` 的回调下标是 **0-based**；直接透传会把第 1 条报成"第 0 条"）；
  - `minimizeRow` / `redactTeachingTimePlace` / `redactSegmentTeacher` 的第三参数
    统一改名 `rowIndex → humanRowNo`，并写入 JSDoc：**从 1 开始的人类行号，只用于错误信息**；
  - ⛔ **未改** fail-closed 行为、字段存在性检查、数据最小化结果、脱敏规则、诊断统计；
    ⛔ 未改任何 Schema / Interface。
- **⑥ 新增守卫**（`backend/tests/test_sysu_collector_guard.py`，42 条）：
  - `test_collector_reports_one_based_human_row_numbers`：断言调用点必须是
    `minimizeRow(row, currentPageNo, rowIndex + 1)`、**不得**出现裸下标透传
    `minimizeRow(row, currentPageNo, rowIndex)`、文档必须写明"从 1 开始"；
  - `test_collector_row_number_is_only_for_messages`：行号**不得**进入最小化结果 / 数据字段
    （`minimized[humanRowNo]`、`row_no` 均不得出现）。
- 修改文件：
  - `tools/sysu_course_offering_collector.js`
  - `backend/tests/test_sysu_collector_guard.py`
  - `docs/data/DATA_SOURCE_REGISTRY.md`（`OFFERING-002` 登记 + §6 汇总 + 变更记录）
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`（表头 / G11 出处 / §4.7 措辞）
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **526 collected / 2 skipped（= 524 passed）**，exit 0
  （上一轮基线 522 passed / 2 skipped；未删除任何旧测试、未新增 skip）；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**（仅语法解析，**未执行**）。
- 使用数据：**Mock / 人工虚构**；**仍未生成真实 Capture Bundle**；仓库内 0 个真实数据文件。
- **实际 SYSU 请求数：0**；Builder **未登录**、**未运行诊断**。
- 下一步：等待 Reviewer 复核本修复，之后由**负责人手动执行 1 页诊断**。
  ⚠️ **不 merge，不自行开始下一阶段**。

### 2026-10-01 - Phase 2B-2C1C：Missing Schedule Correlation Diagnostic
- 本次目标：新增一个**同样只取第 1 页一次**的**相关性诊断**入口，
  对 `missing` 组与 `non_empty_string` 组做**已有真实字段**的**聚合结构对照**，
  用来判断"缺 `teachingTimePlaceStr` 的 row 是否表现出一致的结构特征"。
  ⛔ **只做相关性取证、不判断业务含义、不是 workaround、不改契约**。
- 起点：`main` = `e43f0effca8ce424fe83da4eb8311024affe2123`；
  新建 `feature/course-data-missing-schedule-correlation`（**base 已核对一致**）。
- **负责人手动执行的真实证据（本轮回填，非 Builder 取得）**：
  `diagnoseSchedulePresence({ semester: "2026-1" })`：
  `reported_total = 6892`、第 1 页 `total_rows = 200`、
  `teachingTimePlaceStr` 五桶 = `missing 39` / `null 0` / `empty_string 0` /
  `non_empty_string 161` / `other_type 0`（第 1 页 **39/200 = 19.5%**）。
  ⚠️ **范围限定**：该比例**只代表第 1 页这 200 条样本**，
  ⛔ **不外推**为"全校 19.5%""6892 条中约有多少条""整学期约有多少无排课课程"。
  可确认的形态事实：第 1 页只出现 `missing` 与 `non_empty_string` 两种形态，
  **不是单条孤立现象**；但**业务含义仍未知**。
- **来源登记**：`OFFERING-002` **补录**上述聚合证据（`docs/data/DATA_SOURCE_REGISTRY.md` §4.1 + §6 + 变更记录）；
  ⛔ **不创建新 `source_id`**（同一数据源 / 同一学期 / 同一模块 / 同一页 / 同一取证目的）；
  仍**不登记任何 Raw row**、不登记逐行信息、不登记字段取值。
- **`tools/sysu_course_offering_collector.js` 新增（在现有采集器内，不新建 Transport 文件）**：
  - `diagnoseMissingScheduleCorrelation({ semester })`：**固定**
    `pageNo = CORRELATION_PAGE_NO`（= `DIAGNOSTIC_PAGE_NO` = **1**）、
    `pageSize = CORRELATION_PAGE_SIZE`（= `DIAGNOSTIC_PAGE_SIZE` = **200**）；
    **只调一次** `await requestPage(...)`；复用既有 hostname guard / same-origin / 全部校验；
    用户**只允许提供 `semester`**，`pageNo` / `pageSize` / `firstPageNo` / `maxPages` /
    `delayMs` / `retry` **一律显式拒绝**；⛔ 无分页循环（用 `Array.prototype.filter` 做参数校验，
    函数体内**没有 `for` / `while`**）、⛔ 无重试、⛔ 无并发、⛔ 无第二次请求；
  - 纯函数：`classifySchedulePresence`（与 2C1B **同口径**五桶）、
    `summarizePresenceBuckets`、`splitRowsForCorrelation`（只分 `missing` /
    `non_empty_string` 两组，其余形态只计 `other_rows`，⛔ **不并入任何一组**）、
    `summarizeFieldShape`（A 类：只做存在性 / 类型统计，**无 value 列表**）、
    `summarizeCategoricalValues`（B 类：有限分类值计数 + 高基数 suppression）、
    `summarizeCorrelationGroup`、`assertFieldTotals`、`assertCorrelationInvariants`；
  - 返回结构：`semester` / `page_no` / `page_size` / `reported_total` / `total_rows` /
    `schedule_presence{五桶}` / `compared_rows` / `ungrouped_rows` /
    `groups{missing, non_empty_string}`（每组含 `total` + `structural_fields` + `categorical_fields`）；
  - **安全格式**：分类值一律 `{ type, value: String(value), count }`；
    ⛔ **不用真实取值当 object / Map / Set key**（用数组线性扫描累加）；
    `missing` / `null` / `empty_string` / `other_type` 单独归类，不进入 value 列表；
    ⛔ **A 类字段（含 `timePlaceId`）绝不输出具体取值**；
  - **高基数安全阀**：`MAX_DISTINCT_VALUES = 20`（**诊断输出安全阀，不是 SYSU 参数**）；
    distinct **> 20** → `values_suppressed = true`、`values = []`；
    ⛔ **不返回前 N 个 / 随机 N 个 / 最常见 N 个**；排序只按「类型 + 序列化文本」，**与出现次数无关**；
  - **计数不变量**：五桶之和 == `total_rows`；两组之和 == `compared_rows`；
    `compared_rows + ungrouped_rows == total_rows`；每个字段自身统计加总 == 该组 `total`；
    ⛔ **任一不成立即整体失败，绝不静默丢 row**；不变量校验在 `return` **之前**调用；
  - ⛔ **不生成 Capture Bundle**、不落盘、不写 `localStorage` / `IndexedDB`、不调用 `toJson`；
  - ⛔ **完全未改** 2C1B 的 `diagnoseSchedulePresence()`，也**未改** `collect()` 的 fail-closed 行为。
- **本地合成校验（非入库、非真实请求）**：用**人工虚构** fixtures（含五桶、
  25 个 distinct 的高基数字段、缺字段 / 空串 / 非字符串等形态）在本地 Node 里加载采集器、
  stub `fetch` 跑通诊断：五桶之和 == `total_rows`、`compared_rows + ungrouped_rows == total_rows`、
  高基数字段 `distinct_count = 25` → `values_suppressed = true` / `values = []`、
  A 类字段只输出 shape 计数、返回 JSON 内**无** `courseNum` / `courseName` / `classNumber` /
  `readObj` / `class_ID` / 教师 / 教室 / 原文，6 个禁止参数**全部被拒绝**。
  ⚠️ 该脚本是**临时**校验（**未入库**），**未**访问任何真实系统。
- **缺口报告**：G11 与 §4.7 补录第 1 页真实聚合证据，并把**未确认**清单细化为
  「为什么缺失 / 缺失 row 的业务类型 / 是否属于有效可选教学班 / 是否应进入 Planner /
  全学期缺失比例 / 是否需要修改公共契约」；明确⛔ **不得**写成
  "缺排课 / 未排课课程 / 未排课教学班 / 时间待定 / 异步课程 / 无需排课 / 异常数据 / 暂无教室"。
- 修改文件：
  - `tools/sysu_course_offering_collector.js`
  - `backend/tests/test_sysu_collector_guard.py`（新增 13 条 C1C 守卫；
    把「暂缓字段名全文不得出现」的旧断言**作用域收窄**到 `KEPT_ROW_FIELDS` / 最小化路径，
    **未删除**该断言；更新 `requestPage(` 调用点计数为 4 / `await requestPage(` 为 3）
  - `docs/data/DATA_SOURCE_REGISTRY.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **537 passed / 2 skipped**，exit 0
  （baseline **524 passed / 2 skipped**；**未删除任何旧测试、未新增 skip**；
  `test_sysu_collector_guard.py` 由 42 → **55** 条）；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**（仅语法解析，**Builder 未执行**浏览器脚本）。
- ⛔ **未修改** `schemas/` / `docs/interfaces/` / `backend/app/models/contracts.py` /
  `backend/app/course_data/*.py` / `integration/` / `planner/` / `curriculum/` / `main.py` /
  `api/` / `frontend/` / `mock_data/`；
  `CourseOffering.meetings` 的 **`minItems = 1` 保持不变**；本轮**不存在**【接口变更请求】。
- 使用数据：**Mock / 人工虚构**；**未生成真实 Capture Bundle**；仓库内 0 个真实数据文件。
- **实际 SYSU 请求数：0**（Builder 未登录、未运行任何诊断）。
- 下一步：等待 Reviewer 验收 Phase 2B-2C1C；之后由**负责人手动运行相关性诊断**，
  真实结果回填后再决定是否走正式【接口变更请求】。⚠️ **不 merge，不自行开始下一阶段**。

### 2026-10-01 - Phase 2B-2C1C Reviewer 修复（3 项）
- 本次目标：按 Reviewer 意见收紧**暴露面 / 参数面 / 文档口径**，**不新增能力、不改契约**。
- 起点：`feature/course-data-missing-schedule-correlation`，HEAD `1177dab`（未 merge）。
- **① 收口 C1C helper 暴露面**（`tools/sysu_course_offering_collector.js`）：
  - 从 `window.XuehangSysuCollector` **删除** `classifySchedulePresence` /
    `summarizeFieldShape` / `summarizeCategoricalValues` 三个键；
  - 原因：`summarizeCategoricalValues` 是**任意字段**的 generic summarizer，
    一旦公开，调用方就能绕过 C1C 的字段 allowlist（对 `timePlaceId` / 课程名等
    字段直接产生具体 value counts）；
  - C1C 现在**只暴露** `diagnoseMissingScheduleCorrelation` 一个入口；
    三个 helper 仍为 IIFE 内部实现，并在暴露段上方写明"不暴露 + 原因"；
  - 新增守卫 `test_correlation_helpers_are_internal_only`：
    在**全局 exposure 切片**中断言三者均不出现、断言不存在 `函数名: 函数名` 暴露写法。
- **② options 改为严格白名单**：
  - 删除 `CORRELATION_FORBIDDEN_OPTIONS`（"已知参数黑名单"可绕过）；
  - 改为 `var optionNames = Object.keys(opts);` +
    `optionNames.filter(function (name) { return name !== "semester"; })`；
    任何额外 own key（`pageSize` / `pageNo` / `firstPageNo` / `maxPages` / `delayMs` /
    `retry`，以及 `foo` / `fields` 等**任意未知字段**）都在**发请求之前** fail closed；
  - ⛔ 失败信息**不回显**调用方提供的键名（只报额外参数个数），
    避免把任意字符串带进日志；
  - 守卫：`test_correlation_diagnostic_rejects_any_option_other_than_semester`（白名单逻辑 +
    **时序早于 `await requestPage(`** + 旧黑名单常量已消失 + 不回显键名），
    并在 `test_correlation_diagnostic_page_and_size_are_locked` 中增加
    `slice_.count("opts.") == 1`（唯一被读取的 options 字段就是 `semester`）。
- **③ 修正文档输出口径**：全部删除"只含计数与类型 / 不含取值原文"这类**不准确**说法，
  统一改为四点口径：
  1. **不返回** Raw row / 逐行数据 / 课程与教学班标识 / 教师 / 教室 /
     `teachingTimePlaceStr` 原文；
  2. **Structural-only 字段不返回具体值**；
  3. **Categorical 字段 `distinct <= 20` 时会返回聚合后的原始标量分类值 + `count`**；
  4. **`distinct > 20` 时 `values` 全部 suppression**。
  同步位置：`docs/status/course_data.md`（C1C 表格 + 新增"返回内容的准确口径"引用块 + 「下一步」）、
  `docs/status/agent_frontend.md`（C1C 关键边界）、本文件；
  另在 JS 的 `diagnoseMissingScheduleCorrelation` JSDoc 中写明同一口径。
- 修改文件：
  - `tools/sysu_course_offering_collector.js`
  - `backend/tests/test_sysu_collector_guard.py`（C1C 守卫 13 → **15** 条）
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **539 passed / 2 skipped**，exit 0
  （上一轮 537 passed / 2 skipped；**未删除任何旧测试、未新增 skip**）；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**。
- **本地合成校验（临时脚本、未入库、非真实请求）**：加载采集器并 stub `fetch`，
  确认 ① 暴露键中 `summarizeCategoricalValues` / `summarizeFieldShape` /
  `classifySchedulePresence` 均为 `undefined`；
  ② `{semester}` 放行且只发 1 次请求，`{semester, pageSize}` / `{semester, foo}` /
  `{semester, fields}` / `{semester, pageNo}` / `{semester, retry}` **全部被拒且 0 次额外请求**；
  ③ `openClass`（2 个 distinct）返回聚合分类值 + count，
  `openingUnitName`（25 个 distinct）`values_suppressed = true` / `values = []`，
  `timePlaceId` 只返回 shape 计数；返回 JSON 内无课程 / 教师 / 教室 / 原文。
- ⛔ **未修改** `schemas/` / `docs/interfaces/` / Python 数据链路 / `collect()` / 2C1B 诊断入口；
  `CourseOffering.meetings` 的 **`minItems = 1` 保持不变**。
- 使用数据：**Mock / 人工虚构**；**未生成真实 Capture Bundle**。
- **实际 SYSU 请求数：0**。
- 下一步：等待 Reviewer 复核本修复。⚠️ **不 merge，不自行开始下一阶段**。

### 2026-10-01 - Phase 2B-2C1C：Real Correlation Evidence Sync（docs-only）
- 本次目标：把**负责人本人已经手动取得**的 C1C 真实聚合结果**回填到文档**
  （证据 / 状态 / worklog）。⛔ **本轮不写诊断代码、不改 Schema / Interface、
  不改 Python 数据链路、不改 `collect()`、不新增诊断函数、不发起任何真实请求**。
- 起点：`main` = `e3686bbee5c8638c54f1edcc946e0315870ddf52`；
  新建 `docs/course-data-c1c-real-correlation-evidence`（**base 已核对一致**）。
- **真实请求由负责人本人显式执行**：在本人已登录、已有权限的
  「**全校开设课程**」模块页面显式调用
  `diagnoseMissingScheduleCorrelation({ semester: "2026-1" })`（**只请求第 1 页一次**）；
  **Builder 本轮实际 SYSU 请求数 = 0**（本轮只是**文档回填**）。
- **来源登记**：继续复用 **`OFFERING-002`**，**未创建新的 `source_id`** ——
  仍是同一学期（**2026-1**）/ 同一模块 / **同一第 1 页** / 同一 `pageSize = 200` /
  同一 `reported_total = 6892`。
- **回填的真实 C1C 结果**（`docs/data/DATA_SOURCE_REGISTRY.md` §4.1、
  `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` §4.7.1）：
  - `total_rows = 200`；五桶 = `missing 39` / `null 0` / `empty_string 0` /
    `non_empty_string 161` / `other_type 0`；`compared_rows = 200`、`ungrouped_rows = 0`；
  - **A 类（只登记存在性 / 类型计数）**：`missing` 组 `timePlaceId` = `missing 38` /
    `non_empty_string 1`，`limitNumber` / `selectedNumber` = `number 39`；
    `non_empty_string` 组三字段 = `non_empty_string 161` / `number 161` / `number 161`；
  - **B 类（只登记聚合分布，⛔ 不登记真实取值 / 分类名 / 单位名）**：
    `weekDay` 两组 `missing 38` vs `12`（present 组 `distinct_count 49`、suppressed）；
    `openClass` 两组**实际取值完全一致** → 该字段**不能区分两组**；
    `teachProgressSubmitState` 两组**共享同一组 2 个分类**（38/1 vs 143/18）；
    `courseCategoryName` `missing` 组 3 个分类（12/2/25）**全部出现在** present 组
    （后者 5 个分类：68/19/68/3/3）；`examMode` 两组**共享同一组 2 个分类**（32/7 vs 110/51）；
    `openingUnitName` **只登记 `distinct_count`**（11 vs 27）。
- **G11 口径（本轮更新）**：
  - **可以写**：39 条缺 `teachingTimePlaceStr` 的记录**并非整条记录普遍残缺**
    （`limitNumber` / `selectedNumber` 在 39 条中均为数值型且完整存在）；
    **结构差异集中在排课相关字段**（`timePlaceId` 38/39 缺失 vs 161/161 存在；
    `weekDay` 38/39 缺失 vs 12/161 缺失）；`openClass` 不能区分两组；
    `teachProgressSubmitState` / `examMode` / `courseCategoryName`
    **均未发现只属于 `missing` 组的独占分类**；
    但仍**不能据此确认业务类型或 Planner 适用性**；
  - **⛔ 不得写**："38 条**同时**缺 `weekDay` 和 `timePlaceId`"（**只有边际计数、
    无逐 row 交叉证据**）；也不得写"未排课教学班 / 无排课课程 / 时间待定 /
    暂未安排时间 / 异步课程 / 无需排课 / 无教室 / 异常数据 / 无效教学班 / 应过滤 /
    应进入 Planner / 不应进入 Planner"；
  - **⛔ 不声称 G11 resolved**：统一写
    **"G11 structural evidence substantially narrowed — business semantics still unresolved"**。
- **STATUS 同步**：`course_data.md` 阶段状态标为「代码已完成 / Reviewer 已批准并 merge /
  **已由负责人真实运行** / **真实聚合结果已回填**」，**当前 blocker 改为
  「G11 业务语义确认」**（下一步进入**业务语义确认**，**而不是继续扩大结构诊断**）；
  `agent_frontend.md` 只同步"浏览器诊断已真实执行完成"，人工下一步改为
  **Phase 2B-2C1D — G11 Business Semantics Verification**，且**只写"待 Architecture Lead
  下达人工验证步骤"，不自行设计或实施 C1D**。
- 修改文件（**仅 6 个 docs 文件**）：
  - `docs/data/DATA_SOURCE_REGISTRY.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - `docs/worklogs/course_data.md`、`docs/worklogs/agent_frontend.md`（**仅追加**）
- ⛔ **未修改** 代码 / 测试 / `schemas/` / `docs/interfaces/` / Python Course Data 链路 /
  `collect()`；⛔ **未新增任何诊断函数**；⛔ **未生成真实 Capture Bundle**；
  ⛔ **不登记任何 Raw row / 课程与教学班标识 / 教师 / 教室 / 内部 ID / 真实 categorical 取值**。
- 回归（仅确认无副作用，**未为本轮修改任何测试**）：
  `cd backend && python -m pytest` → **539 passed / 2 skipped**；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**。
- 使用数据：**Mock / 人工虚构**（文档登记的是**汇总事实**）。
- **Builder 实际 SYSU 请求数：0**。
- 下一步：**Phase 2B-2C1D — G11 Business Semantics Verification**
  （**待 Architecture Lead 下达人工验证步骤**）。⚠️ **不 merge，不自行开始下一阶段**。

### 2026-10-01 - Data Gate Reopen — DG-07 Proposal（docs-only）
- 本次目标：基于**已确认的真实证据**起草 **DG-07【接口变更请求】**
  （`CourseOffering` Empty Meetings / Unknown Schedule）。
  ⛔ **本轮是 Proposal，不是 Implementation**：不改 `schemas/`、不改 `docs/interfaces/`、
  不改任何代码 / 测试 / `mock_data/`，**不实施** `minItems = 0`，
  **不**决定 Planner 最终行为，**不**认定 G11 resolved，**不**发起任何真实请求。
- 起点：`main` = `de161440aac19ad0947b7605b23ddaf16de5baee`；
  新建 `docs/data-gate-dg07-empty-meetings-proposal`（**base 已核对一致**）。
- **本轮的新证据（C1D，人工界面核验）**：由 **Architecture Lead 指导负责人**从第 1 页本地定位
  **2 条**典型候选（条件：`teachingTimePlaceStr` / `weekDay` / `timePlaceId` 三者均不存在），
  由**负责人本人**在「**全校开设课程**」UI 人工检查：两条候选**均可在 UI 中正常找到**、
  **时间 / 周次 / 地点完全空白**、**无明确状态文字**、**容量 / 已选人数等普通教学班信息正常显示**、
  **与普通教学班为同一种表格行**、**无解释空白原因的详情 / tooltip**。
  ⚠️ **n = 2**，⛔ 不能代表全部 39 条；⛔ **只登记 `candidate A` / `candidate B`**，
  **不登记课程名 / 课程号 / 教学班号**，也不登记截图；**Builder 实际 SYSU 请求数 = 0**。
- **新增 `DATA_GATE_DECISIONS.md` §17（DG-07 草案）**：
  - **状态：`PROPOSED / WAITING FOR ARCHITECTURE REVIEW`**（⛔ **不写 APPROVED**）；
  - 按 `/AGENTS.md` 第 4 节完整格式给出：**当前设计**（`meetings` `minItems: 1`，
    `"meetings": []` 非法）→ **建议修改**（`minItems: 1 → 0`，`"meetings": []` 合法；
    ⛔ 不新增字段、不改 `Meeting`、不改 `required`）→ **原因**（真实来源存在
    "官方教学班记录存在但当前快照没有可用排课信息"的已观察状态；现有契约只剩
    "伪造 `Meeting`" 或 "静默过滤" 两种坏选择）→ **影响模块** → **是否为破坏性修改** →
    **是否存在不修改接口的替代方案**；
  - **`meetings = []` 的精确定义**：仅表示
    "**当前来源快照没有提供能够形成公共 `Meeting` 的可用排课信息**"；
    ⛔ 不表示无课 / 异步 / 时间自由 / **无冲突** / 学校确认未排课 / 应被过滤；
  - **核心安全不变量**：**`meetings = []` ≠ conflict-free** ——
    Planner **绝不能**因为"没有 `Meeting` 对象"就推导"没有任何时间冲突"；
    保守 MVP 行为**只作 Proposal**（不自动选入 conflict-free 候选；
    必须处理的 `MakeupTask` 若只有空 meetings 候选 → 显式进入 unresolved / 人工确认路径）；
    `PlanResult.unresolved[].type` 为**开放字符串**，候选值 **`missing_schedule`**
    标为 **candidate convention only**（最终命名 **requires Planner implementation review**）；
    ⛔ **本轮不武断规定** `partially_feasible` / `infeasible`；
  - **4 个替代方案比较**：A（保持 `minItems = 1` + 过滤）、
    **B（`minItems = 0`，⭐ 推荐）**、C（新增 `schedule_status` 枚举）、
    D（独立 DTO / `UnknownScheduleOffering`，评价为 **MVP 过重**，⛔ 不擅自选 D）；
    并说明**暂不新增业务状态枚举**的理由（无官方语义证据，易把"未知"伪装成"已知状态"）；
  - **Breaking 分析分两层**：Schema validation 层面 = **兼容性放宽**；
    对依赖 `meetings` 非空不变量的消费者 = **语义性 breaking change**
    （Planner / Frontend / tests / `mock_data` 需同步迁移）；
  - **术语纪律**：推荐中性术语
    `schedule information unavailable in current source snapshot` /
    「当前来源快照中没有可用排课信息」；⛔ 不得使用"未排课课程 / 未排课教学班 /
    时间待定课程 / 异步课程 / 无需排课课程 / 停开课程 / 无效教学班 / 自由时间教学班"；
    并写明**只有边际计数、无逐 row 交叉证据**（⛔ 不得写"38 条**同时**缺两个字段"）、
    **n = 2 不得外推**、**39/200 不得外推到 6892**。
- **新增 `DATA_GATE_DECISIONS.md` §12.3**：明确
  **原 Data Gate = PASSED / CLOSED**，因 G11 新证据
  **Reopened narrowly for DG-07 only**；⛔ **DG-01 – DG-06 不重新打开**；
  其它已裁决问题不重新讨论；DG-07 **未经批准不得实施**。
- **缺口报告 `REAL_TO_SCHEMA_GAP_REPORT.md`**：新增 **§4.7.2 C1D 人工业务界面核验**（n = 2，
  只登记 candidate A / B 与 6 项检查结果），写明"**已人工核验的 2 条典型候选在学校 UI 中
  均作为普通教学班记录展示，但时间 / 周次 / 地点位置为空**"，并更新 G11 现状为
  **business semantics partially evidenced; contract gap candidate identified;
  architecture decision pending**（⛔ **不写 resolved**）。
- **来源登记 `DATA_SOURCE_REGISTRY.md`**：`OFFERING-002` **补 C1D 汇总事实（n = 2）**，
  继续复用同一 `source_id`；明确**不登记**课程名 / 课程号 / 教学班号与任何截图身份，
  **不登记任何真实 categorical 取值**；约束中增补"HAR / 截图均不得进入 Git"。
- **本地已确认的既存约束（只引用、未修改）**：
  `backend/app/models/contracts.py` 的 `CourseOffering.meetings` 仍是 `min_length=1`；
  `backend/tests/test_contracts.py` 有**明确锁定 `meetings: []` 必须失败**的回归用例
  → 若 DG-07 将来获批，这些位置**需要同步迁移**（本轮**一字未改**）。
- 修改文件（**仅 7 个 docs 文件**）：
  - `docs/data/DATA_GATE_DECISIONS.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`、
    `docs/data/DATA_SOURCE_REGISTRY.md`
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - `docs/worklogs/course_data.md`、`docs/worklogs/agent_frontend.md`（**仅追加**）
- ⛔ **未修改** `schemas/`、`docs/interfaces/`、任何代码、任何测试、`mock_data/`；
  ⛔ **未实施** `minItems = 0`；⛔ **未新增** diagnostic / workaround；
  ⛔ **未认定** G11 resolved；⛔ **未推断**学校业务状态。
- 回归（仅确认无副作用，**未为本轮修改任何测试**）：
  `cd backend && python -m pytest` → **539 passed / 2 skipped**；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**。
- **Builder 实际 SYSU 请求数：0**。
- 下一步：等待 **Architecture Lead** 对 **DG-07** 的裁决。
  ⚠️ **不 merge，不自行开始 DG-07 实施**。

### 2026-10-01 - DG-07 Reviewer 架构修复（3 项，docs-only）
- 本次目标：按 Reviewer 意见做**架构性收口**，⛔ **仍不实施** DG-07、
  ⛔ **不改**代码 / 测试 / Schema / Interface。起点：HEAD `2d95b0c`（未 merge）。
- **① 删除"真实可选教学班"的过度表述**：C1D 只证明**真实教学班 / 开课记录存在**，
  **不证明**对当前学生**可选**；把 `过滤可能丢失真实可选教学班`
  统一改为 **`过滤可能丢失真实教学班记录`**（`DATA_GATE_DECISIONS.md` §17.5 / §17.6 共 4 处）。
  **"是否属于有效可选教学班"与"是否应进入 Planner"继续保留为未确认项**（口径未改）。
- **② 新增 `DATA_GATE_DECISIONS.md` §17.12.1「Course Data fail-closed 不变量」**：
  - **`meetings = []` 只能表示"来源层没有提供可形成 `Meeting` 的排课信息"**，
    ⛔ **绝不能作为 parser / importer / normalizer 解析失败的 fallback**；
  - 否则等于把**我们的解析缺陷**伪装成**学校的数据状态**；
  - **初始实施边界按现有证据写死**：✅ **唯一已确认可映射为 `[]` 的来源形态 =
    `teachingTimePlaceStr` 属性不存在**；
  - ⛔ **`null` / `empty_string` / `other_type` / 非空但格式无法解析 / malformed segment /
    parser / normalization 异常 一律继续 fail closed**，
    除非将来有**独立真实证据 + 架构裁决**；
  - 依据：C1B 真实第 1 页样本中 `null` / `empty_string` / `other_type` **均为 0**，
    现有证据**只覆盖"属性不存在"**这一种形态。
- **③ Planner 安全规则显式覆盖 `current_schedule`**（`DATA_GATE_DECISIONS.md` §17.9）：
  - 因 `offerings` 与 `current_schedule` **同为公共类型 `CourseOffering[]`**
    （`docs/interfaces/planner.md` / `integration.md`），**两侧都存在 `meetings = []` 风险**；
  - **对两者中任何 `meetings = []` 的 `CourseOffering`，schedule 都视为 unknown**；
  - **若 `current_schedule` 中存在 `meetings = []`**：Planner **不得**把其它候选声明为
    "**已验证与当前课表无时间冲突**"（最多只能说"与**已知**时段不冲突"）；
    相关"无冲突"断言应**整体降级为未知**并显式进入 unresolved / 人工确认路径；
  - `PlanResult.status` / `unresolved` 命名**仍留待 Planner implementation review**，
    ⛔ 本轮不决定。
- **④ §17.5 建议修改**同步声明：**本提案的批准必须与上述两条不变量同时成立**
  （只批准 `minItems = 0` 而不批准不变量 = 放行静默降级）。
- **同步**：`docs/status/course_data.md`、`docs/status/agent_frontend.md` 增补两条不变量要点；
  `DATA_GATE_DECISIONS.md` §15 变更记录追加本条。
- 修改文件（**仅既有 7 个 docs 文件**）：
  - `docs/data/DATA_GATE_DECISIONS.md`
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - 本文件（**仅追加**）；其余 docs 文件**未改**
- ⛔ **未修改** `schemas/` / `docs/interfaces/` / 任何代码 / 任何测试 / `mock_data/`；
  ⛔ **未实施** `minItems = 0`；⛔ **DG-07 未改为 APPROVED**；
  ⛔ **未认定** G11 resolved；⛔ **未推断**学校业务状态。
- 回归（仅确认无副作用，**未修改任何测试**）：
  `cd backend && python -m pytest` → **539 passed / 2 skipped**；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**。
- **Builder 实际 SYSU 请求数：0**。
- 下一步：等待 **Architecture Lead** 对 **DG-07** 的裁决。
  ⚠️ **不 merge，不自行开始 DG-07 实施**。

### 2026-10-01 - DG-07 Architecture Decision Sync（docs-only）
- 本次目标：把项目负责人的**正式裁决**回写文档：
  **DG-07 = `APPROVED WITH MODIFICATION / IMPLEMENTATION PENDING`**
  （由 `PROPOSED / WAITING FOR ARCHITECTURE REVIEW` 更新）。
  ⛔ **本轮只写文档，不开始 Implementation**；起点：HEAD `7a11781`（未 merge）。
- **"WITH MODIFICATION" 的准确含义（已写明）**：**不是**只批准
  `meetings` 的 `minItems: 1 → 0`，而是 **Schema 放宽** 与
  **Course Data fail-closed 不变量**、**Planner 安全不变量（含 `current_schedule`）**
  **必须同时成立**。
- **已批准的公共契约方向（仅记录，未实施）**：
  `CourseOffering.meetings`：`required` **保持不变**、`type: array`、
  **`minItems: 1 → 0`** → 未来允许 `"meetings": []`；
  ⛔ **本轮未修改** `schemas/`（`schemas/course_offering.schema.json` 仍是 `minItems: 1`）。
- **已批准的精确定义**：`meetings = []` **仅**表示"当前来源快照没有提供能够形成
  公共 `Meeting` 的可用排课信息"；⛔ 不表示：无上课时间 / 异步课程 / 时间自由 /
  无时间冲突 / 学校确认尚未排课 / 无效教学班 / 应过滤。
- **已批准的 Course Data fail-closed 不变量**：初始实施阶段**唯一**可生成 `meetings = []`
  的来源形态 = **`teachingTimePlaceStr` 属性不存在**；
  `null` / `empty_string` / `other_type` / 非空但格式无法解析 / malformed segment /
  **parser / importer / normalization 异常** 一律**继续 fail closed**；
  ⛔ **明确禁止** `try: parse schedule … except: meetings = []` ——
  **`meetings = []` 绝不能成为解析错误的 fallback**。
- **已批准的 Planner 核心不变量**：**`meetings = []` ≠ conflict-free**；
  对 `offerings` 与 `current_schedule` **使用同一规则**（任意 `meetings = []`
  → schedule unknown）；若 `current_schedule` 中存在 `meetings = []`，
  ⛔ **不得**声明其它候选"**已验证与当前课表无时间冲突**"，
  最多只能判断"**与已知时间段未发现冲突**"，整体时间冲突状态**仍含未知部分**。
- **本轮未批准**：**不新增** `schedule_status` / `schedule_known` / `schedule_state`。
- **仍 deferred 到 Planner Implementation Review**：`PlanResult.status` 如何取值、
  `unresolved[].type` 最终命名、`missing_schedule` 是否正式采用 →
  当前 **`missing_schedule` = candidate convention only**。
- **G11 状态更新为**：**`contract decision approved; implementation pending;
  school-side business cause still unknown`** ——
  **契约处理方向已裁决 ≠ 学校业务原因已查明**；⛔ **仍不写 resolved**。
- **Data Gate 状态**：**仍保持 Reopened**（⛔ **未 CLOSED**）；
  新增 **§17.15「关闭 Data Gate 的前置条件」**：
  **DG-07 Contract Migration + Course Data + Planner safety + Frontend / Mock + tests**
  全部完成并经 **Reviewer 验收**后，才允许登记 `DG-07 IMPLEMENTED` 并回到 CLOSED；
  ⛔ 本轮**未开始**任何实施阶段，也**未自行命名 / 拆分**实施阶段。
- 修改文件（**仅既有 7 个 docs 文件**，本轮实际改动 6 个）：
  - `docs/data/DATA_GATE_DECISIONS.md`（文件头 / 架构裁决总表指针 / §12.3 / §15 /
    §17 头部 / 新增 **§17.5.1 裁决** / §17.7 / §17.8 / §17.9 / §17.12 / §17.12.1 /
    §17.13 / §17.14 / 新增 **§17.15**）
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`（文件头 / G11 行 / §4.7.2 尾 / 变更记录）
  - `docs/data/DATA_SOURCE_REGISTRY.md`（OFFERING-002 备注 + 变更记录行）
  - `docs/status/course_data.md`、`docs/status/agent_frontend.md`
  - `docs/worklogs/agent_frontend.md`（阶段同步，**仅追加**）
  - 本文件（**仅追加**）
- ⛔ **未修改** `schemas/` / `docs/interfaces/` / 任何代码 / 任何测试 / `mock_data/`；
  ⛔ **未实施** `minItems = 0`；⛔ **未开始** DG-07 的任何实施阶段
  （⛔ 也未开始 / 命名 `DG-07A`–`DG-07D` 等阶段）；
  ⛔ **未认定** G11 resolved；⛔ **未推断**学校业务状态。
- 回归（仅确认无副作用，**未修改任何测试**）：
  `cd backend && python -m pytest` → **539 passed / 2 skipped**；
  `node --check tools/sysu_course_offering_collector.js` → **exit 0**。
- **Builder 实际 SYSU 请求数：0**。
- 下一步：等待 **DG-07 实施任务书**（**IMPLEMENTATION PENDING**）。
  ⚠️ **不 merge，不自行开始 DG-07 实施**。

### 2026-10-01 - DG-07A — Contract Migration（第一阶段实施）
- 本次目标：按已批准裁决实施 **DG-07A — Contract Migration**：
  **只做**公共契约 + 契约直接镜像 + 公共接口语义文档 + 契约级测试。
  ⛔ **不实施** Course Data 归一化（DG-07B）、Planner safety（DG-07C）、
  前端展示（DG-07D）。起点：`main` = `184bbd6e…`；
  新建 `feature/dg07a-contract-migration`（**base 已核对一致**）。
- **① Schema（唯一字段级修改）**：`schemas/course_offering.schema.json`
  的 `meetings.minItems` 由 **1 → 0**；**`required` 保持不变**（`meetings` 仍必填）；
  **未新增 / 未删除任何字段**、**`Meeting` 结构未变**、
  **未新增 `schedule_status` / `schedule_known` / `schedule_state`**；
  为 `meetings` 增加**非校验性 `description`**（空数组 **仅**表示当前来源快照
  没有能够形成公共 `Meeting` 的可用排课信息；不表示无课 / 异步 / 时间自由 / **无冲突**）；
  **公共 Schema 中未出现 `teachingTimePlaceStr`**（SYSU 来源字段不属公共业务 Schema）。
  合法 / 非法边界：缺 `meetings` → 非法；`null` → 非法；`[]` → **合法**；`[Meeting]` → 合法。
- **② Pydantic 镜像**：`backend/app/models/contracts.py` 的
  `CourseOffering.meetings` 改为 **`min_length=0`**；
  **实测 Pydantic 2.13.5 生成 `minItems: 0`**，与公共 Schema **精确对齐**，
  因此防漂移测试（逐约束键比对，含 `minItems`）**通过** ——
  ⛔ **未删除** drift test、⛔ **未放宽**比较规则、⛔ **未特判** `CourseOffering`、
  ⛔ **未跳过** `minItems`；同步更新 `CourseOffering` 注释
  （0..N、空数组语义、非 conflict-free、rollout gate）。
- **③ 公共接口语义**：
  - `docs/interfaces/course_data.md`：`meetings[]` = 当前来源快照中能够形成公共
    `Meeting` 的**全部已知排课段**；写明**两种合法状态**；删除过时的
    "`meetings` 必须至少包含 1 个 `Meeting`"；正式写入**已批准的 fail-closed 边界**
    （`meetings=[]` **不能**作为解析失败 fallback；DG-07B 初始唯一允许来源形态 =
    **`teachingTimePlaceStr` 属性不存在**；`null` / 空串 / 其它类型 / 无法解析 /
    malformed segment / parser / importer / normalizer 异常**继续 fail closed**）；
  - `docs/interfaces/planner.md`：`meetings` 非空 → **遍历全部 `Meeting`**；
    `meetings = []` → **schedule unknown**、⛔ 绝不"没有时间占用"、⛔ 绝不 **conflict-free**；
    **同一条规则覆盖 `offerings` 与 `current_schedule`**；⛔ 若 `current_schedule`
    含 `meetings = []`，**不得**声明"已验证与当前课表无时间冲突"，
    最多只能判断"与当前课表中**已知时间段**未发现冲突"，**整体状态仍含未知部分**；
    `PlanResult.status` 取值 / `unresolved[].type` 最终命名 / `missing_schedule`
    是否正式采用**仍 deferred**（**candidate convention only**）；
  - `docs/interfaces/integration.md`：**Provider 签名一字不改**；
    `meetings = []` **原样透明传递**（⛔ 不过滤 / ⛔ 不补 `Meeting` / ⛔ 不转换 /
    ⛔ 不推断原因）。
- **④ 前端**：`frontend/src/types/contracts.ts` **仅注释**同步
  （`meetings: Meeting[]` 类型形状**未变**，`Meeting` 注释由"1 — N"改为"0 — N"）；
  ⛔ **未修改**任何 Vue 组件 / CSS / 展示文案 / 业务行为。
- **⑤ 契约级测试**：
  - `backend/tests/test_contracts.py`：把"`meetings: []` **必须失败**"**翻转为
    "必须通过"**（`test_empty_meetings_is_accepted`）；新增 `meetings: null` 拒绝、
    数组内**非法 `Meeting`** 拒绝（`{}` / `weekday=0` / 缺 `weeks` / `weeks=[]`）、
    未批准字段（`schedule_status` / `schedule_known` / `schedule_state`）拒绝；
    **保留**缺 `meetings` 拒绝、旧顶层格式拒绝、`Meeting` 额外字段拒绝、
    `weeks` 重复拒绝等全部既有严格性用例；
  - `backend/tests/test_mock_data_schema.py`：新增 **Schema 层**用例
    （`meetings: []` 合法；缺字段 / `null` / 非法元素 / 额外字段非法；
    `meetings.minItems == 0` 锁定；`meetings` 仍在 `required`）与
    **rollout-gate** 用例（产品 Mock 每班必须 ≥1 段）；
    `_meetings_of` 的"非空"断言改为明确标注**这是 Mock / rollout-gate 要求**，
    **不是**公共契约最小值；**未删除任何用例、未新增 skip**。
- **⑥ rollout gate（本阶段关键）**：`meetings = []` **已成为契约合法状态**，
  但在 **DG-07B / DG-07C / DG-07D 完成前**，
  **生产真实数据链路不得主动产生或接入 empty-meeting `CourseOffering`**：
  ✅ `mock_data/course_offerings.json` **未修改**（9 个教学班仍全部 ≥1 段）；
  ✅ `backend/app/course_data/normalization.py` 的"至少 1 段"**仍然有效**
  （DG-07B 之前本模块继续 fail closed）；
  ⛔ 不把 `meetings = []` 送进产品链路。
- 修改文件（**仅允许清单内**）：
  - `schemas/course_offering.schema.json`
  - `backend/app/models/contracts.py`
  - `backend/tests/test_contracts.py`、`backend/tests/test_mock_data_schema.py`
  - `docs/interfaces/course_data.md`、`docs/interfaces/planner.md`、`docs/interfaces/integration.md`
  - `frontend/src/types/contracts.ts`（**仅注释**）
  - `docs/data/DATA_GATE_DECISIONS.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - `docs/status/{course_data,planner,agent_frontend}.md`
  - `docs/worklogs/{course_data,planner,agent_frontend}.md`
- ⛔ **未修改**：`backend/app/course_data/*`、`backend/app/integration/*`、
  Planner 实现、Vue 组件 / CSS、`mock_data/*`、
  `tools/sysu_course_offering_collector.js`、API / `main.py`；
  ⛔ **未实现** `teachingTimePlaceStr` 缺失 → `[]`；⛔ **未实现** `missing_schedule`；
  ⛔ **未修改** `PlanResult` Schema；⛔ **未新增** `schedule_status`。
- 测试：`cd backend && python -m pytest` → **550 passed / 2 skipped**
  （基线 **539 passed / 2 skipped**；**未新增 skip、未删除测试换通过**）；
  `cd frontend && npm run build`（含 `vue-tsc --noEmit`）→ **成功**。
  特别核对：JSON Schema 与 Pydantic 对 **`minItems = 0`** 一致（防漂移测试通过）。
- 使用数据：**Mock / 人工虚构**；**未生成真实 Capture Bundle**。
- **Builder 实际 SYSU 请求数：0**。
- 下一步：等待 Reviewer；之后等待 **DG-07B** 任务书。
  ⚠️ **不 merge，不自行开始 DG-07B / C / D**。

### 2026-10-01 - DG-07B — Course Data Empty-Meeting Normalization
- 本次目标：实施 DG-07B —— **唯一**新增业务能力：
  SYSU Raw row 的 `teachingTimePlaceStr` **属性真正不存在** → `CourseOffering.meetings = []`。
  这是**数据可用性状态转换**，**不是**学校业务状态判断。
  起点：`main` = `d330d1f1…`；新建 `feature/dg07b-course-data-empty-meetings`
  （**base 已核对一致**）。
- **`normalization.py`**：
  - 抽出 private helper **`_build_common_offering_fields(raw, *, source)`**：
    `courseNum` / `courseName` / `classNumber` / `yearTerm` / `score` /
    `limitNumber` / `selectedNumber`（+ `teachingName` → `teacher`、`remaining_capacity` 派生值）
    的构造**只有一份**；两条路径**共用** → ⛔ **未复制字段映射**；
  - **普通 `build_course_offering()` 仍拒绝任意空 `meetings`**（`_require_meetings` 保留非空要求）；
  - **新增窄语义 `build_course_offering_from_missing_schedule_field(raw, *, source)`**：
    内部**再验证** `"teachingTimePlaceStr" not in raw`；key 存在（无论取值）→ **拒绝**
    且**不回显取值**；成功时 `meetings = []`，`data_source` 仍为 `real`、`source` 仍由调用方给出；
  - `__all__` 增加该内部函数名（**仍是 Course Data 内部实现**，不进 `docs/interfaces/` /
    Provider / API / 公共 Schema）。
- **`importer.py`**：`_build_offering_from_row()` 改为按 **key 是否存在**分流：
  - key **不存在** → 窄语义 normalizer → `meetings = []`；
  - key **存在** → **原样** `parse_teaching_time_place()` → `extract_meetings()` →
    普通 `build_course_offering()`（`null` / 空串 / 非字符串 / 畸形 → **整体失败**）；
  - ⛔ **没有** `try/except`；⛔ **没有** "parser 返回空 / 报错 → 自动认为 schedule unavailable"；
  - ⛔ **不跳过**任何 row（缺排课信息的 row 仍参与 `loaded_count`）。
- **`tools/sysu_course_offering_collector.js`**（Transport 同步，否则真实链路仍会在前端失败）：
  - `KEPT_ROW_FIELDS` **仍为 8 个字段**（Capture row 允许出现的全集，**未新增字段**）；
  - 新增 **`REQUIRED_ROW_FIELDS`（7 个基础字段）**，最小化循环改用它 ——
    缺任意一个基础字段仍 **FAIL**；
  - `teachingTimePlaceStr`：`hasOwnProperty` 为 false → **最小化对象中也不创建该 key**
    （⛔ 不写 `null` / `""` / `UNKNOWN` / `N/A` / `[]`）；属性存在 → 仍调用原
    `redactTeachingTimePlace()`（present + null / 空 / 非字符串 / 畸形 → **FAIL**）；
  - **Capture 格式不升级**：仍是 `sysu-opening-courses-capture-v1`（顶层结构未变，
    旧 v1 bundle 仍可读）。
- **0 diff 实现**：`schedule_parser.py`、`pagination.py`、`captured_pages.py`、`snapshot.py`
  **均未修改**（`git diff --name-only` 核对）；Provider 签名未变；
  **未新增** `schedule_unknown_count` / `has_unknown_schedule` / `filter_unknown`。
- **测试**（5 个文件，**未新增 skip**）：
  - `test_course_data_normalization.py`：普通路径仍拒绝空数组；narrow path
    A 缺 key → 成功且 `meetings == []`、B–E key 存在（`null` / `""` / `"   "` /
    number / object / list）→ 拒绝、F 合法文本 → **仍不得**走 empty path；
    另加"两条路径其它字段完全一致"、"窄路径仍校验 source 与基础字段"；
  - `test_course_data_importer.py`：**翻转**原 `test_missing_schedule_field_is_rejected`
    → `test_missing_schedule_field_produces_empty_meetings`；
    新增 normal/missing/normal 三条全保留 + 顺序 + `loaded_count == 3` + `complete`；
    present 不可用（8 种取值）→ FAIL；malformed → FAIL；
    **parser 异常不被吞**（混入坏 row → 整批失败）；
  - `test_course_data_pagination.py`：缺排课 row **计入 `loaded_count`**、order 保持、
    `complete` / `partial` 判定不受破坏；present 不可用仍整批失败；
  - `test_course_data_captured_pages.py`：**test-only** bundle 中 key absent →
    `meetings == []` 且 row 数不减、`complete` 正常；跨页不丢 row；
    present 不可用（6 种取值）→ FAIL；
  - `test_sysu_collector_guard.py`：**翻转替代**原
    `test_collect_still_fails_closed_on_missing_schedule_field` →
    `test_collect_allows_only_missing_schedule_field`（A 基础字段恰好 7 个且不含排课字段、
    B 循环用 `REQUIRED_ROW_FIELDS`、C 仅 absent 提前返回、D present 必脱敏、
    E 无占位写法、F 无 catch/fallback/skip）+ 新增"7 个基础字段仍 fail closed"与
    "未扩大采集字段集合 / Capture 格式未升级"两条守卫。
- **本地合成校验（临时脚本、未入库、非真实请求）**：加载 Collector 并 stub `fetch` ——
  三条 row（normal / missing / normal）全部保留；missing row 的输出**不含该 key**；
  present row 仍 `REDACTED`；7 个基础字段逐个删除均 **FAIL**；
  present + `null` / `""` / `"   "` / number / object / malformed **全部 FAIL**。
- **修改文件（仅允许清单内）**：
  - `backend/app/course_data/normalization.py`、`backend/app/course_data/importer.py`
  - `tools/sysu_course_offering_collector.js`
  - `backend/tests/test_course_data_{normalization,importer,pagination,captured_pages}.py`、
    `backend/tests/test_sysu_collector_guard.py`
  - `docs/interfaces/course_data.md`（**仅实现状态同步**）、
    `docs/data/DATA_GATE_DECISIONS.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`、
    `docs/status/course_data.md`、本文件
- ⛔ **未修改**：`schemas/`（两个 schema 均未动）、`docs/interfaces/{planner,integration}.md`、
  `schedule_parser.py` / `pagination.py` / `captured_pages.py` / `snapshot.py`（**0 diff**）、
  Planner 实现、Integration 实现、API / `main.py`、`frontend/`、`mock_data/`；
  ⛔ **未实现** `missing_schedule` / `unresolved` / `partially_feasible` / `infeasible` 规则；
  ⛔ **未**新增 `schedule_status` / `schedule_known` / `schedule_state`。
- 测试：目标 5 个文件全通过；`cd backend && python -m pytest` → **596 passed / 2 skipped**
  （基线 **550 passed / 2 skipped**）；`node --check tools/sysu_course_offering_collector.js`
  → **exit 0**。**新增 skip = 0**。
- **新的 rollout gate（DG-07B 后）**：Course Data **内部**已可忠实表示 `meetings = []`，
  但 **DG-07C（Planner safety）/ DG-07D（Frontend 展示）未完成前**，
  **empty-meeting Offering 仍不得接入真实产品端到端链路**：
  ⛔ 不新增真实 API、⛔ 不接 `PlanningOrchestrator`、⛔ 不交 Planner、⛔ 不送前端、
  ⛔ 不改 Mock 让 Demo 提前出现 `[]`。
- **G11**：更新为 **`contract migration implemented; Course Data empty-meeting
  normalization implemented; Planner / Frontend downstream handling pending;
  school-side business cause still unknown`** —— ⛔ **仍不写 resolved**；
  「**支持保存 `meetings = []` ≠ 已经知道学校为什么没有 schedule**」；
  仍不知道：是否属于有效可选教学班 / 是否应最终被 Planner 选择 / **全学期缺失比例**。
- **Data Gate**：仍 **Reopened**（⛔ 未 CLOSED）；DG-07C / DG-07D **未开始**。
- 使用数据：**Mock / 人工虚构**；**未生成真实 Capture Bundle / Raw JSON / 截图**。
- **Builder 实际 SYSU 请求数：0**。
- 下一步：等待 Reviewer；之后等待 **DG-07C** 任务书。
  ⚠️ **不 merge，不自行开始 DG-07C / DG-07D**。

### 2026-10-05 - 扩展 teachingTimePlaceStr 合法结构（teacher 可缺失），保持 fail closed

- 触发：**2026-1 全量真实采集首轮失败**，浏览器报错
  「第 1 页第 25 条记录的 teachingTimePlaceStr 出现不支持的字段数（4）」。
  认证与接口请求**均已成功**，blocker 是 **collector / parser 的结构覆盖不足**。
- **新的真实证据**（负责人提供）：某条真实 2026-1 记录的 `teachingTimePlaceStr`
  由 3 个 segment 构成，结构为
  `5 字段 A（location/activity）` / `4 字段（activity）` / `5 字段 A（location/activity）`。
  ⇒ 真实系统证明：**teacher 并不总是在 `teachingTimePlaceStr` 中出现**
  （教师信息可能在 row 的其它独立字段中）。
- **旧实现的两个问题**：
  - **问题 A**：4 字段直接 fail（真实数据被拒）；
  - **问题 B（更严重）**：真实 5 字段 `weeks/weekday/sections/location/activity`
    被旧 parser 把 **location 当成 teacher**，导致 `Meeting.campus / classroom = None`
    —— **静默错误解释**。
- **本轮支持的四种结构**（其余继续 fail closed）：
  ```text
  4 字段：weeks / weekday / sections / activity                     （无地点无教师）
  5 字段 A：weeks / weekday / sections / location / activity         （有地点无教师）
  5 字段 B：weeks / weekday / sections / teacher / activity          （无地点有教师）
  6 字段：weeks / weekday / sections / location / teacher / activity （有地点有教师）
  ```
- **5 字段判别规则**：只看 `fields[3]`，满足 **location grammar**
  （非空园区 + 至少一个 `-` + 非空教室，与 `_parse_location()` **同规则**）→ 5 字段 A，
  否则 → 5 字段 B。⛔ 不按 courseName / 学院 / teachingName 猜；⛔ 无模糊匹配；
  ⛔ 不自动补 teacher / location。
  ⚠️ 如实记录既有 grammar 边界：只要「非空园区 + `-` + 非空教室」成立即算 location
  （例如 `示例-教师A` 会被解释为 campus=`示例`、classroom=`教师A`）——
  **本轮不扩大也不收窄该 grammar**，只是把它固定在测试里。
- **Python parser**（`backend/app/course_data/schedule_parser.py`）：
  `ParsedScheduleSegment.teacher` 由 `str` 改为 **`str | None`**；
  新增常量 `FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER = 4` / `FIELDS_FIVE = 5` /
  `FIELDS_WITH_LOCATION_AND_TEACHER = 6`；新增纯结构判别 `_is_location_token()`（不抛异常）。
  ⛔ **未修改**公共 `Meeting` / `CourseOffering` / `schemas` / Provider contracts。
- **Collector**（`tools/sysu_course_offering_collector.js`）：同步同一规则；
  新增 `isLocationToken()`（与 Python 同规则，按**首个** `-` 切分）；
  4 字段 → 原样保留；5 字段 → 是 location 则原样保留、否则 `fields[3] = REDACTED`；
  6 字段 → `fields[4] = REDACTED`；⛔ 3 / 7+ 继续 `fail()`；
  ⛔ 空 teacher 仍不得被写成 `REDACTED`。
- 修改文件：`backend/app/course_data/schedule_parser.py`、
  `tools/sysu_course_offering_collector.js`、
  `backend/tests/test_course_data_schedule_parser.py`（新增 4/5/6 字段与回归用例）、
  `backend/tests/test_sysu_collector_guard.py`（3 个源码级 guard 同步新规则 +
  1 个新增 grammar 一致性 guard）、
  新增 `tools/sysu_course_offering_collector.test.mjs`（**可执行**脱敏行为测试）、
  `docs/status/course_data.md`、本文件。
- 测试：
  - `test_course_data_schedule_parser.py` → **71 passed**
    （含新增：4 字段无 teacher/location、5 字段 A 解析 location、
    **5 字段 location 不得被当成 teacher 的回归测试**、5 字段 B 保留旧行为、
    非 location token 仍走 teacher、混合三 segment 真实形状、3/7+ 继续拒绝）；
  - `tools/sysu_course_offering_collector.test.mjs` → **10 passed**
    （Node 内建 `node:test` + `vm`，假 `fetch`，零网络）；
  - 非空测试验证：把 5 字段判别回退为"无条件当 teacher"后，
    parser **失败 4 项**（`campus=None` 复现），还原后全部通过。
- **数据来源**：本轮**未发起任何真实请求**，全部使用**人工虚构**数据；
  ⛔ **未生成 / 未提交任何真实 Capture Bundle**。
- 是否修改 runtime / provenance：**否**（⛔ 未动 `planning_runtime.py`、⛔ 未加 `APP_*` env）。
- **明确边界**：本轮**只修结构覆盖**，⛔ **不声称** trusted provenance solved；
  ⛔ **不在修完后自动继续全量采集** —— 等 Architecture Review 通过后由负责人重新执行。
- 下一步：等待 Architecture Review。

### 2026-10-05 - 收紧 5 字段判别为严格三态（二义一律 fail closed）

- 触发：Review 指出上一版 5 字段判别**仍不够严格** ——
  它复用通用 grammar（"非空园区 + `-` + 非空教室"），
  于是 `A-B`（**只有两段**、含 `-`）会被判成 location，
  而那同样可能是一个**含 `-` 的 teacher**，会重现"teacher / location 互相静默错读"。
- **收紧后的规则**（只看 `fields[3]`，**严格三态**）：
  ```text
  无 "-"                → teacher   → 5 字段 B（无地点、有教师）
  >= 3 个非空 "-" 分段   → location  → 5 字段 A（有地点、无教师）
  其余二义形态           → 一律 fail closed（⛔ 不猜）
  ```
- **实现**：
  - Python 新增 `_classify_five_field_token()`（三态）+ `_count_non_empty_dash_segments()`，
    门槛常量 `_MIN_LOCATION_SEGMENTS = 3`；
    `_is_location_token()` **保留**（供 6 字段等**已由字段数确定语义**的位置使用）——
    ⛔ **未修改** `_parse_location()` 的通用解析规则；
  - 5 字段分支改为按三态分流：`ambiguous` → `CourseDataNormalizationError`
    （错误信息说明"不猜语义"且**不回显**该字段取值）；
  - Collector 新增 `classifyFiveFieldToken()` + `countNonEmptyDashSegments()` +
    `MIN_LOCATION_SEGMENTS = 3`，与 Python 同规则；
    5 字段的 `ambiguous` → `fail()`。
- **本轮未扩结构**：仍只支持 4 / 5 / 6 字段；⛔ 3 / 7+ 继续 fail closed；
  ⛔ **未收紧 6 字段**（语义已由字段数确定）。
- 测试：
  - `test_course_data_schedule_parser.py` → **75 passed**
    （新增：无 `-` → teacher；`>= 3` 个非空分段 → location；
    **5 类二义形态 → fail closed**（含"三段但末段为空"→ 非空仅 2 段）；
    **回归：`A-B` 不得再被静默当成 location**）；
  - `tools/sysu_course_offering_collector.test.mjs` → **16 passed**
    （新增同一组三态用例 + 二义 fail closed + 回归）；
  - `test_sysu_collector_guard.py` → **61 passed**
    （同步 5 字段 guard 到 `classifyFiveFieldToken`；
    新增"⛔ 不得复用 `isLocationToken(fields[3])`"守卫）；
  - 非空测试验证：把 `ambiguous` 分支改成不 fail（静默当 teacher）→ parser **失败 6 项**，
    还原后全部通过。
- 修改文件：`backend/app/course_data/schedule_parser.py`、
  `tools/sysu_course_offering_collector.js`、
  `backend/tests/test_course_data_schedule_parser.py`、
  `backend/tests/test_sysu_collector_guard.py`、
  `tools/sysu_course_offering_collector.test.mjs`、
  `docs/status/course_data.md`、本文件。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ 按指示**未重新执行真实 35 页采集**。
- 下一步：等待 Architecture Review。

### 2026-10-05 - non-concrete schedule segment（2 字段）支持，保持 fail closed

- 触发：**新真实证据**确认一个合法 2 字段 `teachingTimePlaceStr` segment：
  `12-19周校外/实验实践环节`（见习类课程）。
  该 segment **没有** weekday / sections / 具体地点 / teacher。
- **架构决定**：⛔ **不为它制造 `Meeting`**；作为 Course Data **内部**的
  **non-concrete schedule segment** 表示。
- **解析规则**（⛔ 白名单，不是通配）：
  ```text
  2 字段：<weeks token><qualifier> / <non-empty activity>
          目前唯一已确认 qualifier = 校外
  ```
  - ✅ 先**分别**取得 `weeks_token = "12-19周"` 与 `qualifier = "校外"`，
    ⛔ **不把整串** `12-19周校外` 送进 `expand_weeks()`（它只认识 `<weeks token>`）；
  - 结果：`meeting = None`、`teacher = None`、
    `schedule_qualifier = "校外"`、`activity` 保留、周次正常展开；
  - ⛔ 不把 `校外` 伪装成 `Meeting.campus`（`"校外"` 不是具体校区，
    与 `openingSchoolName → campus` 是两回事）；
  - ⛔ `12-19周未知词` / `12-19周线上` / `12-19周医院` / `12-19周实践基地` 等
    **尚无证据**的 qualifier 一律拒绝；后续按新证据逐个加入。
- **内部对象**：`ParsedScheduleSegment.meeting` 改为 **`Meeting | None`**；
  新增 **`schedule_qualifier: str | None = None`**。
  ⛔ **未修改**公共 `Meeting` / `CourseOffering` / `schemas` / Provider contracts。
- **⚠️ Review 追加修复（周次丢失）**：初版 2 字段分支**只计算不保存**周次 ——
  `weeks = expand_weeks(weeks_token)` 的结果没有传入 `ParsedScheduleSegment`，
  于是 `meeting is None` 时周次**永久丢失**（`meeting.weeks` 不存在，
  `schedule_qualifier` 里也没有周次）。现已新增内部字段
  **`schedule_weeks: list[int] | None = None`** 并真正保存
  （`12-19周校外` → `[12..19]`）；concrete segment 该字段保持 `None`。
  新增 5 项测试锁定（含"周次在 `extract_meetings()` 之后仍存在"与混合场景）；
  非空验证：移除保存语句后 **失败 3 项**。
- **`extract_meetings()`**：只投影 `meeting is not None` 的 segment；
  ⛔ **不是静默丢弃** —— `ParsedScheduleSegment` 仍完整保留在解析结果中。
- **importer 三类状态**（严格分开，⛔ 不混用）：
  1. 属性**不存在** → 窄语义路径 → `meetings = []`（DG-07B，未变）；
  2. 属性存在、**解析成功但无 concrete segment** → **新增**窄语义路径
     `build_course_offering_from_non_concrete_schedule()` → `meetings = []`；
  3. 属性存在但**解析失败** → **整体失败**（⛔ 不吞成 `meetings = []`）。
  ⚠️ 新增的第 2 条路径是必需的：否则含该形态的真实 row 会在普通路径
  （`_require_meetings` 拒绝空数组）**整体失败**，使真实全量采集无法完成。
- **Collector**：`redactSegmentTeacher()` 对 2 字段先做
  `NON_CONCRETE_FIRST_FIELD` 整段匹配（与 Python 同规则）；命中 → 原样保留
  （无 teacher，⛔ 不做脱敏）；未命中 → `fail()`（⛔ 不放开为任意 2 字段）。
  字段数错误信息更新为"只接受 2（non-concrete）/ 4 / 5 / 6"。
- **保留既有规则**：4 字段 / 5 字段 teacher / 5 字段 location /
  5 字段二义 fail closed / 6 字段 —— 全部保持。
- **DG-07**：⛔ **未修改**；Planner ⛔ **未修改**。
  只有 non-concrete segment 的 `CourseOffering` → `meetings == []` →
  由现有 Planner 语义视为 **schedule UNKNOWN**（正好合理：
  有课程安排信息，但没有足够信息判断时间冲突）。
- 修改文件：`backend/app/course_data/schedule_parser.py`、
  `backend/app/course_data/normalization.py`（新增窄语义构造函数）、
  `backend/app/course_data/importer.py`（第三类状态分流）、
  `tools/sysu_course_offering_collector.js`、
  `backend/tests/test_course_data_schedule_parser.py`、
  `backend/tests/test_course_data_importer.py`、
  `backend/tests/test_sysu_collector_guard.py`、
  `tools/sysu_course_offering_collector.test.mjs`、
  `docs/status/course_data.md`、本文件。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ 按指示**未重新执行真实 35 页采集**。
- 下一步：等待 Architecture Review。

### 2026-10-05 - 新增 3 字段 non-concrete（`weeks / teacher / activity`）

- 触发：**新真实证据** `1-17周/龙霞/实验实践环节`，同行 `row.teachingName` 亦为同一教师姓名。
  ⇒ 该 3 字段是 **`weeks / teacher / activity`**：
  ⛔ **不是** location，⛔ **不是**未知 qualifier。
- **只支持这一个已确认结构**：
  - `fields[0]` 合法 `N-M周`（`N >= 1`、`M >= N`）→ `expand_weeks()` → `schedule_weeks`；
  - `fields[1]` 非空 **teacher**（⛔ 不塞进 `Meeting`、⛔ 不猜成 location）；
  - `fields[2]` 非空 activity；
  - `meeting = None`、`schedule_qualifier = None`；
  - ⛔ weeks 非法 / teacher 空 / activity 空 → fail closed；⛔ **不放开为任意 3 字段**。
- **Python**：新增 `FIELDS_NON_CONCRETE_WITH_TEACHER = 3`、
  `_try_parse_non_concrete_with_teacher_fields()`；`_ALLOWED_FIELD_COUNTS` 加入 3。
  `normalization.py` 新增**结构判别**辅助 `is_plain_week_range()`（⛔ 不扩大
  `expand_weeks()` 本身接受的语法集合），供 parser 与规则说明共用。
- **Collector**：`redactSegmentTeacher()` 新增 3 字段分支 ——
  `fields[1]`（teacher）替换为 `REDACTED`，weeks / activity 原样保留；
  新增 `PLAIN_WEEK_RANGE` 常量与 Python **同规则**；空 teacher → fail closed。
- **Importer**：⛔ **未新增第二套逻辑** —— 3 字段 non-concrete 与 2 字段一样
  `meeting = None`，因此**复用已有的** narrow non-concrete path →
  `meetings = []`（已验证）。
- **现有 2 字段 `weeks+校外/activity` 规则保持不变**（含既有测试）。
- **既有测试修正**：原先把"3 字段"当作非法字段数的 3 处断言
  （parser 字段数用例、importer malformed 用例、node 字段数用例）
  已按新证据更新为 7+ 字段或其它真正非法输入。
- **⚠️ 顺带发现的既有隐私缺口（本轮未修）**：
  4 字段结构是 `weeks / weekday / sections / activity`，
  当含教师姓名的文本被误当作 4 字段时，`fields[1]` 会作为 weekday token
  被 `parse_weekday()` **回显**到错误信息里。这是**既有行为**（非本轮引入），
  已登记为测试 `test_known_gap_weekday_error_echoes_token` 固定事实，
  ⛔ **未在本轮修改** `parse_weekday`（会牵动既有契约与测试）。
- 修改文件：`backend/app/course_data/schedule_parser.py`、
  `backend/app/course_data/normalization.py`、
  `tools/sysu_course_offering_collector.js`、
  `backend/tests/test_course_data_schedule_parser.py`、
  `backend/tests/test_course_data_importer.py`、
  `backend/tests/test_sysu_collector_guard.py`、
  `tools/sysu_course_offering_collector.test.mjs`、
  `docs/status/course_data.md`、本文件。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ 按指示**未重新执行真实 35 页采集**。
- 下一步：等待 Architecture Review。

### 2026-10-05 - 3 字段支持已确认 qualifier（`16-16周校内(户外)/教师/activity`）

- 触发：**新真实证据** `16-16周校内(户外)/<教师>/实验实践环节`，
  `<教师>` 已通过该 row 的 `teachingName` 交叉确认。
- **新增形态**：3 字段 **qualified** non-concrete
  `<weeks><qualifier> / teacher / activity`；
  ⛔ **只白名单已确认 qualifier**，⛔ 不泛化为任意 suffix。
- **qualifier 白名单**（当前两项）：`校外`、`校内(户外)`。
- **解析要求（关键）**：必须先把 `16-16周校内(户外)` 拆成
  `weeks_token = "16-16周"` 与 `qualifier = "校内(户外)"`，
  ⛔ **只把 weeks token 传给 `expand_weeks()`**（整串会直接失败）。
- **3 字段分支现在分两种**：
  - `N-M周 / teacher / activity` → plain，`schedule_qualifier = None`；
  - `N-M周<已确认 qualifier> / teacher / activity` → qualified，
    `schedule_qualifier = "…"`；
  - 其它 suffix（`16-16周未知文本` / `16-16周线上` / `16-16周医院`）→ **fail closed**。
- **结果**：`meeting = None`、`schedule_weeks = [16]`、
  `schedule_qualifier = "校内(户外)"`、`teacher`、`activity`；
  ⛔ 不生成 `Meeting`；⛔ 不把 `校内(户外)` 当 `campus`；⛔ 不猜 weekday / sections。
- **实现**：Python 侧把 qualifier 与 weeks 的拆分改成**通用形状 + 白名单校验**
  （regex 只负责拆，白名单负责"是否已确认"），新增常量
  `SCHEDULE_QUALIFIER_ON_CAMPUS_OUTDOOR = "校内(户外)"`；
  `_NON_CONCRETE_FIRST_FIELD` 更名为 `_QUALIFIED_WEEKS_ONLY`。
  Collector 同步：`KNOWN_QUALIFIER_EXACT` 白名单 + `WEEKS_WITH_OPTIONAL_QUALIFIER` 拆分，
  teacher **仍在 `fields[1]` 脱敏**（⛔ 不因第一个字段带 qualifier 而跳过）。
- **Importer**：⛔ **未新增路径** —— qualified 与 plain 一样 `meeting = None`，
  继续复用已有 narrow non-concrete path → `meetings = []`。
- **Planner / DG-07**：⛔ **未修改**；`meetings == []` 仍按现有 **DG-07** 视为 **UNKNOWN**。
- 测试：parser **116 passed**；importer **73 passed**；collector guard **65 passed**；
  collector node **38 passed**；Course Data 相关 **509 passed**。
  新增覆盖：qualified 解析 4 项、未知 qualifier 4 项、collector qualified 脱敏与
  "不得跳过脱敏"、非法输入 5 项，以及**混合测试（6 字段 concrete + plain 3 字段 +
  qualified 3 字段）**，断言段数全保留、Meeting 只来自 concrete、
  两种 non-concrete 的 weeks 正确、**qualifier 只出现在 qualified 那一段**。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ 按指示**未重新执行真实 35 页采集**。
- 下一步：等待 Architecture Review。

### 2026-10-05 - 新增 2 字段 plain non-concrete（`1-17周/实验实践环节`）

- 触发：**新真实证据** `1-17周/实验实践环节`：该 segment 内**没有** teacher 字段
  （虽然 row 级 `teachingName` 存在）。
- **架构决定**：新增 2 字段 **plain** non-concrete `<weeks token> / activity`；
  ⛔ **不得把 row 级 `teachingName` 注入 `segment.teacher`** ——
  `teachingName` 是 **row 级**信息，与该 segment 内是否有 teacher **没有对应关系**，
  注入等于**凭空造事实**。⇒ 2 字段两种形态的 `teacher` **一律为 `None`**。
- **2 字段现在区分两种已确认形态**：
  - **plain**：`1-17周/实验实践环节` → `schedule_qualifier = None`；
  - **qualified**：`12-19周校外/实验实践环节` → `schedule_qualifier = "校外"`（保持不变）；
  - 其它 suffix（`1-17周未知词`）→ **fail closed**。
- **解析结果**（plain）：`meeting = None`、`schedule_weeks = [1..17]`、
  `schedule_qualifier = None`、`teacher = None`、`activity = fields[1]`。
- **实现**：`_try_parse_non_concrete_fields()` 改为先判 plain（`is_plain_week_range`），
  否则再走 qualified 白名单（`_QUALIFIED_WEEKS_ONLY`）；⛔ 不放开为"任意 2 字段"。
- **Collector**：2 字段分支接受 plain 或 qualified 两种**已确认**形态 → **原样保留、
  不插入 `REDACTED`**（没有 teacher）；⛔ 也不注入 row 级 `teachingName`。
  ⚠️ 顺带补齐一处**与 parser 的不一致**：原先 collector 会放过
  `1-17周/`（activity 为空）而 parser 拒绝；现已在 collector 补上 activity 非空校验，
  两边一致 **fail closed**。
- **Importer**：⛔ **未新增路径** —— plain 与 qualified 2 字段都 `meeting = None`，
  继续复用已有 narrow non-concrete path → `meetings = []`。
- **Planner / DG-07**：⛔ **未修改**。
- 测试：parser **127 passed**；importer **76 passed**；collector guard **65 passed**；
  collector node **45 passed**；Course Data 相关 **523 passed**。
  新增覆盖：plain 2 字段解析（含"不得注入 teachingName"专项断言）、
  weeks 展开、qualified 保持不变、非法输入 6 项（weeks 非法 / activity 空与全空白 /
  未知 qualifier / 带"第"字 / 随机文本）、collector 原样保留与 5 项非法 fail closed，
  以及**五形态混合测试**（concrete + plain 2 字段 + qualified 2 字段 + plain 3 字段 +
  qualified 3 字段）：断言段数全保留（5）、**只有 concrete 生成 Meeting**（1）。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ 按指示**未重新执行真实 35 页采集**。
- 下一步：等待 Architecture Review。

### 2026-10-05 - 五校区分片合并（方案 B）：merge_offering_snapshots()

- 触发：**2026-1 真实采集发现稳定深分页异常** ——
  学校接口在 **offset >= 6500** 返回 `HTTP 600 {"code":50015000,"message":"系统异常"}`；
  已由真实证据确认（`pageSize=100/pageNo=66`、`pageSize=50/pageNo=131/132` 均 600）。
- **正式确认的分片维度**（负责人 UI 取证）：`param.openingSchoolNumber`，五个完整校区
  （东 5063559 / 北 5062202 / 南 5062201 / 深圳 333291143 / 珠海 5062203）；
  `baseline_before == baseline_after == 6880 == Σ shard total`。
  ⚠️ 人工 total **只作验收参考**，⛔ 不进 production completeness 逻辑。
- **Architecture Review 裁决：方案 B** ——
  五个独立 shard bundle + 内部合并；⛔ **不重编号 / 不重切分 / 不生成伪连续全局 pages**
  （方案 A 已明确否决）；⛔ **不改 Capture Bundle format**。
- **先做的前置检查（任务 11）**：结论为现有 bundle/page model
  **无法**合法承载多个 shard ——
  ① `page_no` 必须全局唯一且严格连续；
  ② `pages` 是扁平数组，无 shard 维度；
  ③ `CapturedPagesFetcher` 用扁平的 `page_no → response` dict；
  ④ 分页核心要求每页 `data.total` 互相相等，而各 shard total 天然不同。
  ⇒ 先回报、后实施（未私改 format）。
- **本轮实现**（仅 Course Data 内部）：
  - 新增 `merge_offering_snapshots(snapshots, *, baseline_total)`（`snapshot.py`）；
  - 并入 `course_data.__all__`；
  - 八个必要条件全部 fail closed（见 `docs/status/course_data.md`）；
  - identity = `(semester, courseNum, classNumber)`，⛔ 不按 `course_id` 单独去重；
  - 跨 shard 重复 → fail closed，只报告**最小 identity + 两个 shard 名**，⛔ 不静默去重；
  - 合并成功时 `loaded_count == baseline_total == reported_total` → `complete` 不变量自然成立，
    可直接交给**现有** `SnapshotCourseDataProvider`。
- **新增测试**（`backend/tests/test_course_data_snapshot_merge.py`，**23 项，纯 synthetic、零网络**）：
  五 shard 全成功 / 行序与不丢行 / 单 shard；baseline 漂移（Σ>baseline 与 Σ<baseline）；
  任一 shard partial（含"四个 complete + 一个 partial"）；shard 计数不自洽 /
  total 中途变化；semester 不一致；跨 shard 重复（含"只报 identity、不回显课程名"、
  "同课不同班不算重复"）；merged unique < / > baseline；输入与 baseline 参数校验；
  合并结果可被现有 Provider 持有。
- **非空测试验证**：把跨 shard 重复检查关闭（静默去重）后**失败 1 项**，还原后 23 项全通过。
- 测试结果：merge **23 passed**；Course Data 相关 **546 passed**；
  full backend **2 failed / 2154 passed / 2 skipped**（两个为既有 Windows Curriculum 用例）；
  `compileall` exit 0；`node --check` exit 0；collector node **45 passed**。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ **未跑真实五校区采集**。
- **本轮未做**：⛔ 未改 `planning_runtime.py`、⛔ 未改 PR #39、⛔ 未改 Capture Bundle format、
  ⛔ JS 侧 orchestration **尚未实现**（待 Review 通过）。
- 下一步：等待 Architecture Review。

### 2026-10-05 - 五校区分片合并（方案 B）：sharded capture-set 编排模块（Python 侧）

- 触发：Architecture Review 对上一轮 `merge_offering_snapshots()` 的裁定 ——
  **批准新增一个 Course Data 内部 sharded capture-set orchestration 模块**，
  ⛔ **不得写在 README 里**、⛔ **不得只做临时运维脚本**；目标链路：
  `5 个独立 Capture Bundle 文件 → 各自 load_capture_bundle() →
  collect_captured_pages_snapshot() → 校验五个预期 shard → baseline_before == baseline_after
  → merge_offering_snapshots(...) → merged OfferingSnapshot`。
- **新增模块**：`backend/app/course_data/sharded_capture.py`（Course Data **内部**，
  ⛔ 不进 `schemas/`、⛔ 不进 `docs/interfaces/`）：
  - `APPROVED_SHARD_IDS = (东校园, 北校园, 南校园, 深圳校区, 珠海校区)` ——
    顺序即**合并顺序**（与调用方传入顺序无关，保证可复现）；
  - `ShardSource(shard_id, bundle)`：`bundle` 是**已加载的 bundle** 或**本地路径**；
    ⛔ **不提供目录扫描自动发现** —— 每一份必须由调用方**显式**给出；
  - `collect_sharded_capture_set(*, shard_sources, baseline, expected_semester)
    -> ShardedCaptureSet`；
  - `ShardedCaptureSet` 记录 `merged` / 各 shard 快照 / 四个对账计数
    （⛔ 不含任何课程、教师、学生取值）；
  - 公开符号并入 `app.course_data.__all__`（与 `merge_offering_snapshots` 一致），
    `__init__.py` 的流水线图补上"五 shard → 合并"这条真实路径。
- **编排层自己负责的 fail-closed 条件**（任一不满足 → `ShardedCaptureError`，
  `CourseDataNormalizationError` 子类，调用方**一处捕获**）：
  1. baseline **恰好一个**快照，且自身 complete / `loaded_count == reported_total` /
     semester 匹配；
  2. shard 集合**恰好等于**五个已批准校区：**无缺 / 无多余 / 无重复**；
  3. 每个 bundle **独立** complete（各自计数自洽）；
  4. 每个 shard `semester == expected_semester`（与 3 同一处强制，便于定位到 shard）；
  5. 每个 shard **内部**无重复 identity（`OfferingSnapshot.__post_init__` 已强制，
     本层**显式重申**，与"跨 shard 重复"共用同一 identity 口径）；
  6. `Σ shard reported_total == baseline reported_total`（覆盖一致）；
  7. 合并结果**物化后重新计数**仍须 complete：行数 == Σ 各 shard 已加载行数 == baseline，
     且 unique identity 数 == baseline（⛔ **不采信下层自报数字**）。
- **本次修正（自查发现）**：
  - 原先"shard semester 集合 == [expected]"的**聚合**检查是**不可达死代码**
    （每 shard 已由条件 4 拦下）→ **删除**；
  - 原先 `assert` 用于类型收敛 → 改为 `_require_single_snapshot()` **返回**已确认的
    `reported_total`，⛔ 生产代码不留 `assert`；
  - 下层 `captured_pages.py` 的"文件不存在 / JSON 非法"错误信息**含本地绝对路径**
    （那是给本地读取场景的）→ 转述前用 `_scrub_paths()` 擦成**文件名**；
  - 合并失败时下层只报**位置下标**（`shard[0]` / `shard[1]`）→ 本层附上
    `shard[i]=校区名` 顺序表，并统一包装成 `ShardedCaptureError`。
- **新增测试**：`backend/tests/test_course_data_sharded_capture.py`
  （**31 项，纯 synthetic、零网络、零真实采集**）；
  ⚠️ 真实分片数字（1071/405/2898/1171/1335）⛔ **不进测试文件、不作断言常量**。
  覆盖：五 shard 全成功 / 合并顺序固定 / 结果可被现有 Provider 持有；
  缺 shard、多余 shard、重复 shard、空列表；任一 bundle partial（含"四 complete + 一 partial"）、
  bundle 结构非法；shard 与 baseline 的 semester 不一致；baseline 漂移两个方向、
  baseline 非恰好一个、baseline partial；**同 shard 内重复**与**跨 shard 重复**
  （含"不回显课程名"、"同课不同班不算重复"）；输入类型校验；
  显式文件路径入口、文件不存在、文件 JSON 非法（**均只暴露文件名**）；
  Capture Bundle format 常量未变。
- **non-vacuity（mutation 验证，脚本在 repo 外，未入库）**：11 个 mutation 逐一改坏一条检查
  → 确认**至少一个测试变红**：
  缺 shard（2 红）/ 多余 shard（1）/ 重复 shard（1）/ baseline 恰好一个（1）/
  baseline 自洽（7）/ 单 shard 自洽（1）/ Σ shard == baseline（2，**先加强断言**：
  必须**归因于覆盖性**而非被下游 merge 顺手拦下）/ 路径擦除（2）/ shard 名还原（1）/
  错误类型统一（2）。
  **唯一被下层掩盖**：同 shard 内重复的显式重申（`OfferingSnapshot` 已先拦下，
  移除它不会有测试变红）—— 已在代码注释中**如实标注为刻意的冗余重申**，
  不谎称是独立检查。
- 测试结果：sharded **29 passed**；merge **23 passed**；parser **127 passed**；
  importer **76 passed**；collector guard **65 passed**；上述合并 320 passed；
  full backend **2 failed / 2183 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）；
  `compileall` exit 0；`node --check` exit 0；collector node **45 passed**。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ **未跑真实五校区采集**。
- **本轮未做**：⛔ 未改 Capture Bundle format；⛔ 未改 `planning_runtime.py`；
  ⛔ 未改 PR #39；⛔ 未设计 runtime manifest / provenance 格式；⛔ 未碰 SHA-256 gate；
  ⛔ JS 侧五校区 orchestration **仍未实现**。
- 下一步：等待 Architecture Review（之后再决定如何接入 PR #39 的 exact-artifact gate）。

### 2026-10-05 - 五校区分片合并（方案 B）：JS 侧 sharded collector orchestration

- 触发：Architecture Review **通过**上一轮的 Python 侧 sharded 编排，批准下一阶段实现
  **JS 侧 sharded collector orchestration**，目标链路：
  `baseline_before → 五校区串行 collect → baseline_after → 外层 diagnostics`，
  输出 **5 个独立裸 Capture Bundle + 1 个外层 diagnostics 对象**（⛔ diagnostics 不进裸 bundle）。
- **五个已批准 shard（源码常量 `APPROVED_SHARDS`，顺序 = 请求顺序）**：
  东校园 `5063559` / 北校园 `5062202` / 南校园 `5062201` /
  深圳校区 `333291143` / 珠海校区 `5062203`；
  ⛔ 不猜其它校区、⛔ 不自动读下拉框、⛔ 不接受调用方传入 shard 列表。
- **新增入口 `collectSharded({ semester, maxPages, delayMs })`**（必须显式调用）：
  - baseline 请求 `param: { yearTerm }`（**只有** `yearTerm`，⛔ 不带校区维度），
    只取第 1 页一次、**只读 `data.total`**（⛔ 不最小化 / 不脱敏 / 不产出 bundle）；
  - shard 请求 `param: { yearTerm, openingSchoolNumber }`；
  - 每个 shard：`pageNo` 从 **1** 起、`pageSize` 固定 **200**、
    `expectedTotal` 取**本 shard 第一页**真实 total、`accumulatedRows == expectedTotal`
    时以 `reached_total` 停止；
  - 全程严格串行：每个 shard 的第一个请求也与前一个请求至少间隔 `delayMs`
    （下限仍是既有的 1000ms），⛔ 无并发 / 无预取 / 无重试 / ⛔ 不跳页。
- **重构（⛔ 不改行为）**：把 `collect()` 的分页循环抽成 **唯一**的 `collectPages()`，
  `collect()` 与每个 shard 都复用它 —— 因此 `pageNo` 锁 1、`pageSize` 校验、
  total 中途变化即失败、`minimizeRow` + 教师脱敏、串行 sleep 全部是**同一份实现**；
  共用选项校验抽成 `resolvePagingOptions()`；新增 `buildRequestParam()` 决定 `param` 形态。
  ⛔ 既有 45 个 Node 用例**全部继续通过**（行为未变）。
- **整体失败（抛出，⛔ 不产出任何 bundle）**：
  1. `baseline_before !== baseline_after`；
  2. 任一 shard 未取满 → **立即**停止（不再请求后面的校区，fail fast，少打学校接口）；
  3. Σ shard `expectedTotal` != baseline（与 Python 侧 C6 同一口径，只是**提前**失败；
     完整性权威仍在 Python）。
  失败时错误对象带 `.diagnostics`（已采集到的结构化计数），便于控制台排查。
- **严格白名单**：只接受 `semester` / `maxPages` / `delayMs`；
  ⛔ `pageSize`（固定 200）/ `firstPageNo`（固定 1）/ 自定义 shard 列表都不接受覆盖；
  拒绝时**不回显**调用方给出的参数名；⛔ 校验早于任何请求。
- **外层 diagnostics**（照 Review 清单）：
  `baseline_before` / `baseline_after` / `shard_total_sum` / `expected_pages_total` /
  `semester` / `page_size` / `shard_count` / `approved_shard_count`，以及每个 shard 的
  `shard_id` / `openingSchoolNumber` / `expectedTotal` / `accumulatedRows` /
  `stoppedReason` / `page_count` / `expected_pages`；
  ⛔ 只有结构化计数：**不含**任何 row / 课程号 / 课程名 / 教学班号 / 教师 / 教室 / 原文。
- **`expected_pages = ceil(total / page_size)` 只作 diagnostics**：
  ⛔ 不参与任何 complete / 完整性判定（判据只有 `accumulatedRows == expectedTotal`）；
  静止断言锁死"`Math.ceil` 只出现在写 diagnostics 的那一处"，行为用例锁死
  "学校返回半页、`page_count != expected_pages` 时**仍然必须成功**"。
- **取值方式**：`shardBundle(result, shardId)` / `toShardJson(result, shardId)` /
  `toDiagnosticsJson(result)`；⛔ 既有的 `toJson(result)` **拒绝**五校区结果
  （它不是单个裸 bundle），取消 / 未完成时所有序列化入口一律失败。
- **新增 Node 测试**：`tools/sysu_course_offering_collector.test.mjs` **45 → 70 项**
  （新增 25 项：正常链路 / 请求顺序与请求体形态 / 多页 shard / 半页 `expected_pages` /
  baseline 漂移两个方向 / 未取满 fail fast（断言**没有**请求后续校区）/
  覆盖性（断言**没有**发 baseline_after）/ 取消 / 白名单 4 项 / 限速 / semester 校验 /
  裸 bundle 与 diagnostics 分离 / 取消结果不可序列化 / shard 内解析失败（带 shard 名、
  **单一前缀**、附 diagnostics、不回显字段取值）/ shard 内 teacher 仍脱敏 /
  diagnostics 无 row 内容）。
  ⛔ 零网络：假 `fetch` 按请求体路由 + 假 `setTimeout`（**立即 resolve 但记录延迟**，
  因此"串行最小间隔"是被断言的，不是被跳过的）；
  ⛔ 所有 row 人工虚构；真实分片数字不进测试常量。
- **新增 / 调整静态守卫**：`backend/tests/test_sysu_collector_guard.py` **65 → 78 项**
  （13 项新增：五校区常量恰好是已批准五个、入口暴露且不自动调用、严格白名单、
  baseline 探针无校区维度、校区请求取自源码常量、baseline sandwich 顺序与整体失败、
  未取满 fail fast、覆盖性、**只有一个分页核心**（`collectPages`）且无并发/重试、
  `expected_pages` 只作 diagnostics、diagnostics 无 row 内容、裸 bundle 恰好 5 个键
  且不含 diagnostics、序列化入口拒绝未完成结果）。
  ⚠️ **本轮如实调整了 3 处既有守卫的作用域**（都不是放宽）：
  1. `test_diagnostic_uses_the_shared_request_path`：`await requestPage(` 计数
     3 → 4（新增了 baseline 探针这一条**共用**取页路径），并补上"`fetch(` 仍只有 1 处"；
  2. `test_collector_bundle_keys_match_python_bridge_expectation`：原来的**全文子串**
     断言 `"firstPageNo: firstPageNo" not in source` 改为**逐个 bundle 字面量**检查
     顶层键是否 snake_case（现在源码里合法地存在 camelCase 的 JS 局部对象）；
     对"bundle 元数据不得用 camelCase 请求参数名"这一**原意**而言更严格；
  3. `test_correlation_diagnostic_does_not_touch_collect_or_2c1b`：`collect()` 切片
     终点收窄到五校区段落标记，避免把新段落误算进 `collect()`。
- **non-vacuity（JS mutation 10 项，脚本在 repo 外，未入库）**：逐一改坏
  sandwich / 未取满 fail-closed / 覆盖性 / 严格白名单 / `expected_pages` 变判据 /
  baseline 请求形态 / `shardBundle` 回显名字 / diagnostics 夹带 row / 取消语义 /
  最小间隔 → **每一个都至少 1 个 Node 用例变红**（未取满 fail-fast 与"不再请求后续校区"
  也是被断言的）；其中白名单、`expected_pages`、diagnostics 夹带 row 三项
  **同时**被静态守卫抓到（J5 显示改了判定后守卫与 Node 用例同时红）。
- 测试结果：collector node **69 passed**；collector guard **78 passed**；
  full backend **2 failed / 2198 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）；
  `node --check` exit 0；`compileall` exit 0；Python sharded 编排 **31 passed**（未改代码）。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ **未跑真实五校区全量采集**（只跑假 `fetch` 的 synthetic 用例）。
- **本轮未做**：⛔ 未改 Capture Bundle format；⛔ 未改
  `backend/app/course_data/sharded_capture.py`；⛔ 未改 `planning_runtime.py`；
  ⛔ 未改 PR #39；⛔ 未设计 runtime manifest / provenance 格式；⛔ 未碰 SHA-256 gate。
- 下一步：等待 Architecture Review。

### 2026-10-05 - 修正（Review Blocker）：五校区判定顺序 —— 先 baseline 稳定性，再 shard 覆盖性

- 触发：Architecture Review **基本通过，仅 1 个 Blocker** —— 原实现把
  **Σ shard total 覆盖性**判在 `baseline_after` **之前**，等于拿一个**未确认的
  snapshot window** 去解释覆盖差异。
- **裁定后的顺序（硬要求，已照此实现）**：

  ```text
  ① baseline_before
  ② 五个 shard 串行采集
       └ 任一 shard 未取满 → 立即 fail-fast（⛔ 不请求 baseline_after）
  ③ baseline_after（五个 shard **全部完整成功后无条件请求**）
  ④ baseline 稳定性：baseline_before == baseline_after？
       └ 不等 → snapshot window unstable（整体失败）
  ⑤ shard 覆盖性：Σ shard expectedTotal == baseline_before？
       └ 不等 → shard coverage mismatch（整体失败）
  ```
- **改动**：把覆盖性判定块整体**移到** baseline 稳定性判定之后；
  `baseline_after` 在五个 shard 全部完整成功后**无条件**请求（此前覆盖性失败会提前返回，
  导致第 6 个请求被省掉）。两条失败信息改为**可区分的**、带 Review 术语的文案：
  - `...：snapshot window unstable —— ...`
  - `...：shard coverage mismatch —— ...`
  ⛔ 未改任何判定**口径**（仍然是 `==` 比较），⛔ 未改 Capture Bundle format，
  ⛔ 未改 Python、⛔ 未改 runtime。shard 级 fail-fast **保留**（Review 明确允许）。
- **新增 Node 用例 3 项**（`collector node` 70 → **73**）：
  1. `before=6880, Σ shard=6881, after=6881` → 报 **snapshot window unstable**，
     且断言 ① 不报 coverage mismatch、② `baseline_after` **确实被请求**（baseline 类请求恰 2 次、
     且是最后一次）、③ 五个 shard 都 `reached_total`；
  2. `before=6880, Σ shard=6879, after=6880` → 报 **shard coverage mismatch**，
     且断言不报 unstable、`baseline_after` 已被请求、`shard_total_sum == 6879`；
  3. 只有 shard 本身失败时才允许跳过 `baseline_after`（显式锁住这条例外）。
  ⚠️ 这三个用例里的 6880/6881/6879 是 **Review 指定的场景计数**，只作为假 `fetch` 的输入；
  真实的各校区人工 total（1071/405/…）⛔ 仍不进测试、⛔ 不进任何 production 判定。
- **既有用例修正**：原「Σ shard total != baseline：整体失败（**不再发 baseline_after**）」
  的断言已随裁定反转 —— 现在**必须**发 `baseline_after`，并改名为
  「baseline 稳定后报 coverage mismatch（after 必须已请求）」。
- **新增静态守卫 1 项**（`collector guard` 78 → **79**）：
  `test_sharded_requests_baseline_after_before_any_coverage_judgement` ——
  锁死 `baseline_after` 请求 < 稳定性判定 < 覆盖性判定的**源码顺序**，
  并锁死两条文案互不夹带。
- **non-vacuity（新增 mutation J11）**：把判定顺序**回退成旧顺序**（覆盖性抢跑）后，
  **3 个 Node 用例 + 1 个静态守卫同时变红**；还原后 73 项全通过。
- 测试结果：collector node **73 passed**；collector guard **79 passed**；
  Python sharded 编排 **31 passed**（未改）；
  full backend **2 failed / 2199 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）；
  `node --check` exit 0；`compileall` exit 0。
- **数据来源**：⛔ **未发起任何真实请求**；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ **未跑真实五校区全量采集**。
- **本轮未做**：⛔ 未改 Capture Bundle format；⛔ 未改 Python（含
  `backend/app/course_data/sharded_capture.py`）；⛔ 未改 runtime / `planning_runtime.py`；
  ⛔ 未碰 PR #39；⛔ 未 push / 未开 PR / 未 merge。
- 下一步：等待 Architecture Review 复验。

### 2026-10-05 - 保守节流（conservative pacing）：相邻请求下限 = 10000ms

- 触发：**真实人工验证结果** —— 北校园 `pageSize=50`：
  `page1 → HTTP 200` → **等待 10 秒** → `page2 → HTTP 200`；
  而此前**短间隔连续请求多次稳定出现** `HTTP 600 / code=50015000 / message=系统异常`。
  ⇒ Architecture 决定采用**保守节流策略**。
- **本轮只改请求 pacing**：
  - `DEFAULT_DELAY_MS = 10000`、`MIN_DELAY_MS = 10000`（原 1500 / 1000）；
  - ⚠️ 文档只记录：**10 秒是当前 conservative operational minimum，来源是人工实测**；
    ⛔ **不声称**是学校官方公布的阈值，也不据此推断任何服务端限流实现；
  - `delayMs` **仍可由调用方配置，但只能调大**：`< 10000`（含 `0 / 1 / 999 / 1500 / 9999`）
    在**发请求之前**被拒绝；⛔ 其它配置面未扩大（白名单仍是
    `semester` / `maxPages` / `delayMs`）。
- **间隔适用于同一 endpoint 的所有连续请求**（⛔ 不再允许"只在同 shard 页间 sleep"）：

  ```text
  baseline_before → first shard    ：shard 循环顶部 sleep
  shard page      → shard next page：collectPages() 内部 sleep
  one shard       → next shard     ：shard 循环顶部 sleep（含上一 shard 最后一页）
  last shard      → baseline_after ：baseline_after 之前的显式 sleep
  ```

  实现上仍是**唯一**的分页核心 + shard 循环顶部 / baseline_after 之前的两处 sleep，
  但三处 sleep **全部**取 `delayMs`（由 `resolvePagingOptions()` 单点下限把关），
  且代码/JSDoc 明确写出四类间隔归属。
- **保持不变**：`HTTP 600` → **fail closed**；⛔ 不重试；⛔ 不 backoff 重试；⛔ 不跳页；
  ⛔ 不续采（no resume）；⛔ 不做任何认证绕行。判定顺序（baseline 稳定性 → shard 覆盖性）不变。
- **新增 Node 用例 6 项**（`collector node` 73 → **82**）：
  1. **pacing 不变量**：`timers.length === calls.length - 1` 且每个 timer `>= 10000`
     （任何新增请求路径若没有配套 sleep 会立刻变红）；
  2. **四类相邻间隔**同时存在且各自计数被锁死：
     `baseline→first shard = 1` / `page→next page = 1` / `shard→next shard = 4` /
     `last shard→baseline_after = 1`；
  3. **下限即 10000**：暴露的 `MIN_DELAY_MS` / `DEFAULT_DELAY_MS` 均为 10000，
     且不传 `delayMs` 时按 10000 pacing；
  4. **低于下限被拒绝**：`0 / 1 / 999 / 1500 / 9999` 五个取值全部被拒且**零请求**；
  5. **只允许调大**：`delayMs=20000` 被接受且按 20000 pacing；
  6. **`HTTP 600` fail closed**：东校园第 2 页返回 `600 / code=50015000` →
     整体失败；**该页只请求过一次**（证不重试 / 不 backoff）、
     不再请求其它校区、不发 `baseline_after`、不产出任何 bundle。
  ⛔ 全程零网络：假 `fetch`（新增 `http600` 形态复现真实证据）+ 假 `setTimeout`
  （立即 resolve 但**记录延迟**，因此 10 秒间隔是被**断言**的而不是真的等 10 秒，
  整套 82 项仍在 0.4 秒内跑完）。
- **新增 / 更新静态守卫 3 项**（`collector guard` 79 → **81**）：
  - `test_collector_enforces_minimum_delay`：下限/默认 = 10000，且旧值（1000 / 1500）不得残留；
  - `test_collector_paces_every_consecutive_request`（新增）：恰好三处 `await sleep(`，
    分别位于分页核心内部、shard 循环顶部、`baseline_after` 之前；
    ⛔ `sleep` 不得传字面量（正则 `await sleep\(\s*[0-9]` 为 None）；
  - `test_collector_does_not_add_retry_backoff_skip_or_resume`（新增）：
    非注释代码里不得出现 `retry` / `backoff` / `resume` / `skip` / `attempt` / `setInterval`。
- **non-vacuity（新增 3 个 mutation，累计 14）**：
  - J12「下限退回 1 秒」→ Node 6 项红 + 守卫 `test_collector_enforces_minimum_delay` 红；
  - J13「只在同 shard 页间 sleep」→ Node 6 项红 + 守卫
    `test_collector_paces_every_consecutive_request` 红；
  - J14「去掉 last shard→baseline_after 的 pacing」→ Node 5 项红 + 同一守卫红。
  另旧 mutation J10（`sleep(0)`）现在同时使 2 个守卫变红。
- 测试结果：collector node **82 passed**；collector guard **81 passed**；
  Python sharded 编排 **31 passed**（未改）；targeted 合计 **336 passed**（改动前基线）；
  full backend **2 failed / 2201 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）；
  `node --check` exit 0；`compileall` exit 0。
- **数据来源**：⛔ **未发起任何真实请求**（10 秒这一取值来自**负责人已完成的**人工实测记录，
  本轮只是把该下限写进代码与测试）；⛔ **未生成 / 未提交任何真实 Capture Bundle**；
  ⛔ **未跑真实五校区全量采集**。
- **本轮未做**：⛔ 未改 Capture Bundle format；⛔ 未改 Python；
  ⛔ 未改 runtime / `planning_runtime.py`；⛔ 未碰 PR #39；⛔ 未 push / 未开 PR / 未 merge。
- 下一步：等待 Architecture Review 复验。

### 2026-10-05 - 全局 batch pacing：30 秒间隔 + 每 5 个成功请求冷却 5 分钟

- 触发：**最新人工 sustained pacing 实验** —— `pageSize=50` + `interval=30000ms`：
  request 1～7 全部 200，**request 8 → `HTTP 600 / code 50015000`**。
  ⇒ Architecture 决定：**停止继续增加单一 delayMs**，改为**全局 batch pacing**。
- **常量**：`MIN_DELAY_MS = 30000`、`DEFAULT_DELAY_MS = 30000`、
  `MAX_REQUESTS_PER_BATCH = 5`、`BATCH_COOLDOWN_MS = 300000`。
- **一个全局 request pacing controller**（`createRequestPacer()`）：
  - 等待与批次计数**只存在于它内部**：`beforeRequest()`（发请求前）与
    `noteSuccess()`（在 `requestPage()` 里，**HTTP 200 + code 200 + 结构合法**之后才调用）；
  - ⛔ `baseline_before` / `collectPages()` / shard 循环 / `baseline_after`
    **不再各自 sleep、也不各自计数**：它们只是把**同一个** controller 交给
    `requestPage()`；
  - 规则：第 1 个请求立即发送；其它相邻请求先等 `delayMs`；
    **全局**已累计 5 个成功请求时改为先等 `max(BATCH_COOLDOWN_MS, delayMs)`
    （冷却本身 > 普通间隔，⛔ 不叠加；若调用方把 `delayMs` 调大则取较大者）；
  - ⛔ 计数是整个 sharded collection 的**全局**请求数
    （`baseline_before` + 所有 shard 的每一页 + `baseline_after`），
    ⛔ **不是 per-shard**、⛔ **不在 shard 边界重置**；
  - ⛔ 一次性诊断（2C1B / 2C1C）各自只发 1 次请求，不传 controller、不参与批次计数。
- **保持不变**：`HTTP 非 200` → **fail closed**；⛔ 不重试；⛔ 不 backoff 重试；
  ⛔ 不跳页；⛔ 不续采（no resume）；⛔ 不做认证绕行；判定顺序
  （baseline 稳定性 → shard 覆盖性）不变；⛔ 未扩任何配置面
  （白名单仍 `semester` / `maxPages` / `delayMs`，⛔ 不接受覆盖 batch 大小 / 冷却时长）。
- **Node 测试 82 → 92**（新增/改写 10 项）：
  1. 默认策略下**逐步核对整条等待序列** `[30s,30s,30s,30s,300s,30s]`；
  2. request 1～5 为普通 `>=30s`；
  3. **request5 → request6 `>=300000ms`**；
  4. **request10 → request11 再次 `>=300000ms`**（12 个请求的场景；两次冷却之间仍是 30 秒）；
  5. **shard 边界不重置计数**：东校园 6 页，全局第 5 个请求落在**同一个 shard 的页间**，
     冷却必须在那里发生；
  6. **baseline_before 算请求**（冷却位置可反推）+ **baseline_after 走同一 controller**；
  7. **batch 未满时不额外等 5 分钟**（失败场景只有 2 个请求 → 只有一次 30 秒等待）；
  8. `collect()` 也走**同一个** controller（6 请求 → 1 次冷却）；
  9. 下限/默认 = 30000 且 batch 常量已暴露；
  10. `delayMs` 只允许调大（45000 的整条序列），以及
      **`delayMs` 大于冷却时批次边界取较大者**（600000 不被缩短）。
  公共断言 `assertBatchPacingInvariant()`：`timers.length === calls.length - 1`，
  且第 R 个请求前的等待严格等于"`R-1` 是否为 batch 边界"对应的值 ——
  任何"漏等待 / 另起一套计数"都会立刻变红。
- **静态守卫 81 → 84**（新增 3 项、改写 2 项）：
  `test_collector_enforces_minimum_delay` 改为 30000（旧值 1000 / 1500 / 10000 不得残留）；
  新增 `test_collector_enforces_global_batch_pacing_constants`（5 / 300000，
  且⛔ `opts.maxRequestsPerBatch` / `opts.batchCooldownMs` 不存在）、
  `test_collector_has_exactly_one_global_pacing_controller`
  （代码里 `createRequestPacer(` 恰好 3 处 = 定义 + 两个入口；全文件只有 2 处 `await sleep(`；
  第 1 个请求立即发送；批次分支用 `max(...)`）、
  `test_collector_does_not_duplicate_pacing_outside_the_controller`
  （`collectPages` / `requestReportedTotal` / `collectSharded` 都不得出现
  `await sleep(` 或 `successfulInBatch`）、
  `test_collector_every_paced_request_goes_through_the_controller`
  （`pacer.beforeRequest()` / `pacer.noteSuccess()` 各 1 处；
  `requestReportedTotal(resolved.semester, pacer)` 恰好 2 处；
  两个分页调用点都带 pacer）；
  并新增助手 `_collector_code_only()`（注释里也会提到这些名字，计数断言只看非注释代码行）。
- **non-vacuity（mutation 18 项，脚本在 repo 外）**：
  **18 / 18** 都至少一个 Node 用例变红；**16 / 18** 同时被静态守卫抓到
  （只有"取消语义"与"批次计数不重置"是纯行为用例覆盖）。
  本轮新增 7 项：冷却永不触发 / 批次计数不重置 /
  **per-shard 各建一个 pacer（= shard 边界重置：24 个 Node 用例 + 2 个守卫变红）** /
  baseline 绕过 pacer / 批次未满也强制冷却 / 冷却不取 `max(delayMs)` / 下限退回 10 秒。
- 测试结果：collector node **92 passed**；collector guard **84 passed**；
  Python sharded 编排 **31 passed**（未改）；
  full backend **2 failed / 2204 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）；
  `node --check` exit 0；`compileall` exit 0。
- **数据来源**：⛔ **未发起任何真实请求**（30 秒 / 5+5min 取值来自负责人已完成的人工实测）；
  ⛔ **未生成 / 未提交任何真实 Capture Bundle**；⛔ **未跑真实五校区全量采集**。
- **本轮未做**：⛔ 未改 Capture Bundle format；⛔ 未改 Python；⛔ 未改 runtime /
  `planning_runtime.py`；⛔ 未碰 PR #39；⛔ 未 push / 未开 PR / 未 merge。
- 文档口径：**30 秒连续 7 次成功后第 8 次被风控，因此
  "5-request batch + 5-minute cooldown" 是当前保守运营策略，⛔ 不是学校公开阈值。**
- 下一步：等待 Architecture Review。

### 2026-10-05 - 本地持久化层（SQLite MVP 课程数据库）

- 触发：并行任务 —— 建立 **Capture Bundle → 现有 `collect_captured_pages_snapshot()`
  → `OfferingSnapshot` → SQLite → 读回** 的本地链路（比赛 MVP 的本地课程数据库，
  ⛔ 不是实时爬虫）。另一路（单 approved campus 采集入口）由 Codex 负责，
  ⛔ **本轮未改 collector、未处理浏览器抓取**。
- **新增模块**：`backend/app/course_data/store.py`（Course Data **内部**，
  标准库 `sqlite3`，⛔ 无新依赖、⛔ 零网络）+ 符号并入 `app.course_data.__all__`。
- **DB schema（两张表）**：

  ```text
  course_offering      PRIMARY KEY (semester, course_id, class_id)
                       + course_name / teacher / credit / capacity / remaining_capacity
                       / source / data_source / meetings_json
                       + artifact_sha256 / imported_at（行级 provenance）
  course_data_import   PRIMARY KEY (artifact_sha256, semester)
                       + source / imported_at / completeness / loaded_count
                       / reported_total / offering_count（artifact 级审计）
  ```
- **API**：`initialize_course_data_store(path)` /
  `import_offering_snapshot(path, snapshot, *, artifact_sha256)` /
  `load_course_offerings(path, semester, *, course_ids=None)` /
  `load_course_data_provenance(path, *, semester=None)` /
  `compute_artifact_sha256(bytes)`。
- **identity / upsert**：`(semester, course_id, class_id)`；
  同一 artifact 重复导入**幂等**（第二次 `inserted=0 / updated=0 / unchanged=N`，
  ⛔ 不产生新行）；⛔ **不按 `course_id` 覆盖不同教学班**；
  数据列一致时仍刷新 provenance；数据列变化时**原地更新**（identity 不变）。
- **provenance**：行级 `artifact_sha256` / `imported_at` / `source` / `data_source`；
  artifact 级记录（同一 artifact + semester **只记首次导入**，⛔ 不覆盖原始时间）。
  ⚠️ 口径未变：**`SHA-256 = artifact identity/integrity ≠ acquisition provenance proof`**，
  库中⛔ 没有任何"采集时间 / 采集者 / 授权状态"字段。
- **completeness 边界**：⛔ 本层**不判断完整性**；`is_complete == False`
  **拒绝写入 approved 路径**（fail closed，且**不写任何行**）；
  库里⛔ 没有"自封完整"的列，导入记录只如实转述上游 `completeness`。
- **查询**：`course_ids=None` → 全部；`course_ids=[]` → **空集合 ⇒ 空列表**
  （⛔ 不是"不筛"）；顺序由 SQL 显式 `ORDER BY course_id, class_id` 保证。
- **meetings**：公共结构化对象 → **稳定 JSON**（键排序 + 紧凑分隔符，可重复比对）；
  读回用 `Meeting.model_validate` 还原，⛔ 不擅自新增公共 Schema。
- **数据边界**：只存已标准化的公共 `CourseOffering`；
  ⛔ 不存 Cookie / token / 登录信息 / 原始完整 response / 教师隐私扩展字段 / 学生信息
  （schema 级断言：两张表列名不得命中这些 token）；
  加载时 `data_source != 'real'` 或 `meetings` 被外部改坏 → fail closed；
  外部 SQLite（缺表）→ 明确报"不是 Course Data 本地库"。
- ⚠️ **公共模型没有 `selected_count`**：公共 `CourseOffering` 只有
  `capacity` / `remaining_capacity`，故持久化这两个字段，
  ⛔ **不新增** `selected_count`（需先走公共 Schema 变更流程）——**待 Review 确认口径**。
- **新增测试**：`backend/tests/test_course_data_store.py`（**49 项，纯 synthetic**）：
  complete 导入 round-trip / partial 拒绝且零写入 / 重复导入幂等 /
  内容变更原地更新 / 同学期不同 `class_id` 各自保留 / 跨学期隔离 /
  `course_ids` 过滤（含空集合）/ 读回顺序（SQL 级断言）/ meetings 5 形态 round-trip /
  稳定 JSON / 可空字段 / 混合来源不猜 / 行级与 artifact 级 provenance round-trip /
  首次导入记录不被改写 / artifact 口径字段集 / hash 形状校验 / 非法 semester 与
  course_ids / 父子路径与目录 / 垃圾文件 / 外部库 / 被篡改 meetings 与 data_source /
  schema 列清单与数据边界。
  ⛔ 所有 course_id / 课程名 / 教学班号 / 教室均为**人工虚构**；⛔ 未导入任何真实数据。
- **non-vacuity（12 个 mutation，脚本在 repo 外）**：**12 / 12 全部变红**
  （去掉 partial 拒绝 / identity 丢 `class_id`（27 项红）/ 不校验 `data_source` /
  去掉 `ORDER BY` / JSON 不排序 / 不写 `teacher` / `already_imported` 恒 False /
  空 `course_ids` 不短路 / 不校验 hash 形状 / 导入记录 OR REPLACE / hash 不归一化 /
  不检查外部库）。⚠️ 其中「去掉 `ORDER BY`」由**SQL 级源码断言**抓到
  （`WHERE semester = ?` 命中主键索引，当前查询计划下行为用例区分不出
  "有保证"与"恰好一致"），已在测试里写明理由。
- 测试结果：store **49 passed**；full backend **2 failed / 2253 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）；
  `compileall` exit 0。
- **数据来源**：⛔ 未导入任何真实数据、⛔ 未读取任何 Capture Bundle、
  ⛔ 未跑真实五校区采集。
- **本轮未做**：⛔ 未改 collector；⛔ 未改 `captured_pages.py` / Capture Bundle format /
  `sharded_capture.py` / `planning_runtime.py` / PR #39 / `schemas/**` / Planner /
  Curriculum / frontend；⛔ **未接** `SnapshotCourseDataProvider`（等 Architecture 决策）；
  ⛔ 未 push / 未开 PR / 未 merge。
- 下一步：先做 Architecture Review，再决定是否把 `SnapshotCourseDataProvider` 接到 SQLite。

### 2026-10-05 - 修正（Review Blocker）：store 增加**显式 scope**（campus / full_semester）

- 触发：Architecture Review **基本通过，仅 1 个 Blocker** —— store 无法显式区分
  `full semester snapshot` / `campus shard snapshot` / Case-A-scoped snapshot，
  而 `snapshot.is_complete` 只表示"**在它自己的采集 scope 内**完整"，
  ⛔ 不得被解释成全学期完整。
- **新增 `SnapshotScope(scope_kind, scope_id)`**（frozen dataclass，构造即白名单校验）：

  ```text
  campus        / <openingSchoolNumber>   例如 campus / 5062202
  full_semester / <semester>              例如 full_semester / 2026-1

  is_complete == complete **within the declared scope**
  ```
- **调用方必须显式传入**（`import_offering_snapshot(..., scope=...)` 为**必填** kwarg）：
  省略 → `TypeError`；显式 `None` / 字符串 / tuple / dict → `CourseDataStoreError`；
  ⛔ **不从 `source` / 文件名 / rows 推断**（行为用例：`source` 写成 `campus/5062202/...`
  也不会改变声明 scope；`source` 只原样保留为来源标注）。
- **校验**：`scope_kind` 必须在 `ALLOWED_SCOPE_KINDS = ("campus", "full_semester")` 内；
  `scope_id` 非空字符串；
  `full_semester` 的 `scope_id` **必须等于**快照 semester（否则该审计记录自相矛盾）。
  ⚠️ **Case-A-scoped 暂不在白名单**（其 `scope_id` 取形尚未确证）→ 当前明确拒绝，
  ⛔ 不塞进一个含糊的 kind；需要时先给出 id 语义再按流程加入。
- **DB schema 变更**：
  - `course_data_import` 增加 `scope_kind` / `scope_id`，且**加入主键**
    `PRIMARY KEY (artifact_sha256, semester, scope_kind, scope_id)`
    —— 同一份 artifact 以不同 scope 声明时各自留一条审计记录，⛔ 不静默合并；
  - `course_offering` 增加 `scope_kind` / `scope_id` 作为**行级** provenance
    （否则"这条行的 provenance 属于哪个 scope"有歧义）；
    identity 仍是 `(semester, course_id, class_id)`（⛔ 与 scope 无关），
    行级 scope 跟随后一次导入；
  - 新增 schema 自检：库里**缺 scope 列**（更早 schema）→ 明确提示重建，
    ⛔ 不自动迁移、⛔ 不静默降级读取（读写两条路径都检查）。
- **API**：`CourseDataImport` / `CourseDataProvenance` 增加 `scope_kind` / `scope_id`；
  `load_course_data_provenance` 的排序改为
  `ORDER BY imported_at, artifact_sha256, scope_kind, scope_id`（仍确定、可复现）；
  `__all__` 增加 `SnapshotScope` / `ALLOWED_SCOPE_KINDS` / `SCOPE_KIND_CAMPUS` /
  `SCOPE_KIND_FULL_SEMESTER`。
- **语义边界（写进模块文档）**：⛔ 库里没有任何"全局 / 全学期完整"的列，
  导入记录只如实转述上游 `completeness` + **声明的 scope**；
  查询读回的仍是公共 `CourseOffering`（⛔ 不新增公共 Schema）。
- **测试 49 → 61**（新增 scope 十二例）：campus complete 可导入 / campus round-trip /
  full_semester round-trip / **scope 缺失拒绝**（省略 + 显式 None 等四种形态）/
  **非法 scope 拒绝**（非法 kind 与 id、`case_a` 不在白名单）/
  `full_semester` id 必须等于 semester / **不从 source 与文件名推断** /
  **同 semester 不同 campus artifact 各自审计** /
  同一 artifact 两个 scope → 两条记录且同 scope 重复导入仍幂等 /
  行级 scope 跟随后一次导入 / 过旧 schema 明确报错 / 库中无"全局完整"列。
- **non-vacuity（mutation 12 → 19，脚本在 repo 外）**：**19 / 19 全部变红**；
  新增 7 项针对 scope：审计记录不写 scope / 审计主键不含 scope /
  不做 `full_semester` 交叉校验 / `scope_kind` 白名单失效 /
  **scope 从 `source` 推断**（10 项红）/ 不检查过旧 schema / 行级 scope 写死。
- 测试结果：store **61 passed**；full backend **2 failed / 2265 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）；`compileall` exit 0。
- **数据来源**：⛔ 未导入任何真实数据、⛔ 未读取任何 Capture Bundle、
  ⛔ 未跑真实采集。
- **本轮未做**：⛔ 未接 Provider；⛔ 未改公共 Schema；⛔ 未改 collector；
  ⛔ 未改 `captured_pages.py` / Capture Bundle format / `sharded_capture.py` /
  `planning_runtime.py` / PR #39 / Planner / Curriculum / frontend；
  ⛔ 未 push / 未开 PR / 未 merge。
- 下一步：等待 Architecture Review。

### 2026-10-05 - parser 窄扩展：sections suffix 白名单 + 安全错误分类（真实 artifact 验收）

- 触发：Architecture Review 裁定（依据 east campus artifact 的只读聚合扫描：
  `校内(户外)` × 173、`线上` × 11、`校外` × 1）。
- **批准的窄扩展**（`backend/app/course_data/schedule_parser.py`）：

  ```text
  第N-M节
  第N-M节校内(户外)
  第N-M节校外
  第N-M节线上
  ```

  - `N ≥ 1` 且 `M ≥ N`（`M == N` 仍合法）；
  - ⛔ **不用 `startswith`**、⛔ **不用 `.*`**、⛔ **不把 `节` 后字符无条件 strip**：
    实现是"白名单字面量逐个 `re.escape` + 整段锚定 `^...$`"的**单一正则**，
    suffix 从不被抓出来做字符串比较；
  - **sections suffix 是独立白名单**（`_KNOWN_SECTIONS_SUFFIXES`）：
    ⛔ **weeks 白名单未放宽**（仍 `校外` / `校内(户外)`）——
    `12-19周线上/...` 与 `16-16周线上/教师/活动` 仍 fail closed（有专项用例 +
    mutation 锁）。
- **qualifier 只做校验**：公共 `Meeting` 没有 qualifier 字段 ⇒ ⛔ 未新增公共字段、
  ⛔ 未写进内部 `schedule_qualifier`（校验后丢弃）；`Meeting` Schema 未变。
- **production 错误改为安全分类**（⛔ 不回显原始 token）：
  `unsupported_sections_suffix` / `unsupported_sections_shape` /
  `unsupported_sections_range`；区间非法时也**不再回显 start/end**。
- 49 个 `other` 形态（`C-CAC-CAN` / `C` / `C-C-CAN`）**本轮按要求不处理**，仍 fail closed。
- **新增 synthetic 用例 32 项**（parser 127 → **159**）：
  已批准形态 6 例（strict ×3 + 三个 suffix）/ 未知 suffix 9 例 / 形状非法 8 例 /
  区间非法 5 例 / **错误信息不回显 raw token**（13 个被拒 token 逐个断言 token 与 suffix
  原文都不出现在 message，且必须带安全分类）/ suffix 仅校验不落库（含 `Meeting` 无
  qualifier 字段）/ **weeks 白名单未被放宽** / 白名单必须整段命中。
- **non-vacuity（mutation 5 项，脚本在 repo 外）：5/5 变红**
  （回退成只接受 `第N-M节` → 6 红；suffix 改 `.*` 通配 → 12 红；
  错误信息重新回显 token → 1 红；区间校验失效 → 8 红；
  把 `线上` 塞进 weeks 白名单 → 3 红）。
  ⚠️ **自查纠正**：第一次 sweep 只统计 `^FAILED `，而 P5 那个 mutation 因把常量写在定义之前
  触发了 **import-time NameError**（pytest 报 collection error 而非 FAILED）⇒ 被误记为 0 红。
  已把 mutation 改为字面量并让计数同时统计 `ERROR`，重跑后 5/5 红。
- **对固定真实 artifact 重新验收**（`D:\webDownload\sysu-2026-1-east-campus.capture.json`，
  SHA-256 `daafdb18…a31b` 实测一致；⛔ 未建 SQLite、⛔ 未跳过任何 row）：
  - `load_capture_bundle` ✅（6 页 / 每页 total 1071 / rows 合计 1071）；
  - `collect_captured_pages_snapshot` **仍然 fail closed，但 blocker 已换**：
    sections 形态**全部通过**，新的失败是**另一条**既有校验
    （`normalization.py`：`selectedNumber > limitNumber`）；
  - **只读聚合复核**（对 3182 个 sections 位置 token 逐个调 `parse_sections`）：
    **accepted 3133 / rejected 49**，且 49 个**全部**是 `unsupported_sections_shape`
    （= 那三个未确证模板），对账 `3133 + 49 = 3182` ✅
    ⇒ 扩展对该 artifact **完整且未越界**；⛔ 没有 `unsupported_sections_suffix`、
    ⛔ 没有 `unclassified`。
  - ⚠️ **新 blocker 细节 + 隐私缺口（需 Review 裁定）**：
    该错误信息回显 **`class_id`（`classNumber`）** 与两个计数 —— 即**行级标识符**，
    与刚裁定的"不回显 raw token"属同一类问题，但**不在本轮授权范围内**，
    故⛔ **未擅自修改**；已按最小化结构信息上报（⛔ 未把该 classNumber 写入任何文件）。
- 测试结果：parser **159 passed**；full backend **2 failed / 2297 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例，未修、未 skip、未删）。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未建 SQLite；⛔ 未改公共 Schema；
  ⛔ 未改 collector / `captured_pages.py` / Capture Bundle format / `sharded_capture.py` /
  `planning_runtime.py` / PR #39 / Planner / Curriculum / frontend / store。
- 下一步：等待 Architecture Review 对(a)新 blocker `selectedNumber > limitNumber` 与
  (b)该错误路径的 `class_id` 回显给出裁定。

### 2026-10-05 - `remaining_capacity` 三分支规则 + 错误信息去 raw 取值（真实 artifact 再验收）

- 触发：Architecture Review 裁定 —— 真实数据已证明 `selectedNumber > limitNumber`
  **是来源中实际存在的状态**，因此**不得**再因这一关系拒绝整条 `CourseOffering`。
- **`_build_common_offering_fields()` 变更**（唯一实现，两条路径共用）：

  ```text
  selectedNumber <  limitNumber → remaining_capacity = limitNumber - selectedNumber
  selectedNumber == limitNumber → remaining_capacity = 0
  selectedNumber >  limitNumber → remaining_capacity = None（unknown）
  ```

  ⛔ 不 clamp 到 0、⛔ 不改写 `capacity`（保持来源 `limitNumber` 原值）、
  ⛔ 不新增 `selected_count`、⛔ 不改公共 Schema、⛔ 不猜学校为何超额；
  `None` = 派生值不可用（⛔ 不表示"已满"、⛔ 不表示"无剩余"）。
- **normalization 文档说明同步**（模块 docstring 字段表 + `_REQUIRED_RAW_FIELDS` 注释 +
  `docs/status/course_data.md` 对应小节）。
- **错误信息去 raw 取值**：`_require_text` / `_require_count` / `_parse_credit` /
  `_optional_teacher` 原先都会带出 `{value!r}`（可能含 `classNumber`、课程名、
  `score` 原文、教师姓名）→ 现改为**只给字段名 + 实际类型**，
  「新的/修改后的 production error 不得回显 `class_id` 或 raw row 值」已满足；
  连带删除了 `selectedNumber(...) 不能大于 limitNumber(...)：{class_id}` 这条会回显
  `class_id` 的错误（该分支已不存在）。
- **测试**（`test_course_data_normalization.py`）：
  - `selected < limit` → 正常差值（含 90/75→15、150/40→110）；
  - `selected == limit` → 0；
  - `selected > limit` → `None`，且**不再抛异常**（10/11 与 10/49 两组）；
  - `capacity` 保持来源 `limitNumber`（4 组组合）；
  - ⛔ 不 clamp、⛔ 不新增 `selected_count`（`hasattr` 断言）；
  - **错误信息不回显 raw 取值**（9 个非法输入 × 多个敏感串断言，含伪造的"机密"课程名/教学班号）；
  - ⚠️ **既有用例 `test_selected_greater_than_limit_is_rejected` 已按其裁定删除**
    （它断言的旧行为正是本次被推翻的行为）。
- **真实 artifact 再验收**（`daafdb18…a31b` 实测一致；⛔ 未建 SQLite；⛔ 未 skip）：
  - `load_capture_bundle` ✅（6 页 / total 1071 / rows 合计 1071）；
  - `collect_captured_pages_snapshot`：**前两个 blocker 已清除、但第三个 fail closed 出现**：
    1. ✅ sections suffix（上一轮）已通过；
    2. ✅ `selectedNumber > limitNumber`（本轮）已通过；
    3. ❌ **新 blocker：`score` 不是合法的字符串数字** ——
       既有校验 `_parse_credit`（regex `^[0-9]+(\.[0-9]+)?$` 要求小数点前至少一位数字）；
       错误信息**已不含任何 raw 取值**（符合本轮要求），但**尚无机器可读的安全分类码**。
  - **只读聚合扫描 `score` 形态**（1071 行，⛔ 只输出匿名模板 + 计数）：

    ```text
    numeric_string      : 973
    non_numeric_string  : 98
    anonymous template  : `.N`（长度 2）× 98      ← 小数点前无数字
    accounting_ok       : True
    ```

    ⇒ 即真实来源里存在 `.N` 形态的学分字符串（98 处）；解析规则是否放宽由 Review 裁定。
  - ⚠️ 49 个 `unsupported_sections_shape` **本轮按要求未处理**（仍是潜在 fail-closed 项）。
- 测试结果：normalization **106 passed**；parser+importer+normalization 合并 **341 passed**；
  full backend **2 failed / 2301 passed / 2 skipped**（两个为**既有** Windows Curriculum 用例）；
  `compileall` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未建 SQLite；⛔ 未改公共 Schema；
  ⛔ 未改 collector / `captured_pages.py` / Capture Bundle format / `sharded_capture.py` /
  store / `planning_runtime.py` / PR #39 / Planner / Curriculum / frontend。
- 下一步：等待 Architecture Review 对(a)`score` 的 `.N` 形态与
  (b)是否给该错误加安全分类码给出裁定。

### 2026-10-05 - `score` 窄扩展（`.N` 形式）+ credit 安全分类（真实 artifact 再验收）

- 触发：Architecture Review 裁定 —— 真实 artifact 已确认 **98 个 `.N` 形式** `score` 字符串，
  批准窄扩展。
- **`_parse_credit()` 批准形状**（语法校验，⛔ 不用宽松 `float()` 替代）：

  ```text
  [0-9]+            例如 "3"   → 3.0
  [0-9]+\.[0-9]+    例如 "3.0" → 3.0 / "0.5" → 0.5
  \.[0-9]+          例如 ".5"  → 0.5 / ".0"  → 0.0
  ```

  继续拒绝：`"."` / `"3."` / `"-.5"` / `"+.5"` / `"..5"` / `"1.2.3"` / 全角数字 /
  带单位文本 / `int` / `float` / `bool`；⛔ **数值型 `score` 仍拒绝**（无真实来源证据）。
- **credit 错误安全稳定分类**：`unsupported_credit_type` / `unsupported_credit_format`，
  ⛔ **不回显 raw score**；⛔ 未重构全局异常系统。
- ⚠️ 自查修正：`_parse_credit` 的**非 raw docstring** 里写了 `\.` 触发
  `SyntaxWarning: invalid escape sequence` → 已改为 raw docstring（`r"""`），
  并确认 `-W error::SyntaxWarning` 下全量测试无告警。
- **测试**（`test_course_data_normalization.py` 106 → **141**）：
  9 个已批准形状（含 `.5` / `.0` / `.25` / `" 3 "`）/ 18 个非法形状（含全角数字、`1e3`、
  `nan`、`inf`、`3 5`）/ 7 种非法类型（含 `bool` / 容器）→ 分类码断言 /
  **不回显 raw score**（6 个有区分度取值，含伪造"机密学分文本"）；既有数值型拒绝用例保留。
  ⚠️ 断言只用**有区分度**的取值：`"."` 本身会出现在文法说明 `[0-9]+.[0-9]+` 里，
  用它做子串断言会假阳性（已记录该理由）。
- **真实 artifact 再验收**（`daafdb18…a31b` 实测一致；⛔ 未建 SQLite；⛔ 未 skip）：
  - `load_capture_bundle` ✅（6 页 / total 1071 / rows 合计 1071）；
  - `collect_captured_pages_snapshot`：**第 3 个 blocker（`score`）已清除**，
    但第 **4** 个 fail closed 出现：
    **`expand_weeks` 拒绝 `N-M单周` 形态**（既有窄白名单只接受精确 `1-17单周`）。
  - ⚠️ **该错误信息回显了 raw weeks token**（既有实现，属"不回显 raw 取值"的同类问题），
    且**无机器可读分类码** → 均**未擅自修改**，作为待裁定项上报。
  - **只读聚合扫描 `weeks`（field[0]）形态**（3475 个 token，⛔ 只输出分类计数 + 匿名模板）：

    ```text
    expand_weeks_accepted : 3382   （全部是 plain `N-M周`）
    expand_weeks_rejected :   93
      1) `N-M周` + `校外`      : 54
      2) `N-M双周`（无「周」字）: 15
      3) `N-M单周`（无「周」字）: 13
      4) `N-M周` + `校内(户外)` : 11
    匿名模板: `N-NC` × 82（= 54+15+13）、`N-NC(C)` × 11
    accounting_ok : True
    ```

  - ⚠️ 49 个 `unsupported_sections_shape` **仍未处理**（按要求），仍是潜在 fail-closed 项。
- 测试结果：normalization **141 passed**；normalization+parser+importer+pagination 合并
  **433 passed**；full backend **2 failed / 2336 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例）；`compileall` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未建 SQLite；⛔ 未改公共 Schema；
  ⛔ 未改 collector / `captured_pages.py` / Capture Bundle format / `sharded_capture.py` /
  store / `planning_runtime.py` / PR #39 / Planner / Curriculum / frontend。
- 下一步：等待 Architecture Review 对(a)`weeks` 的四个未确认形态与
  (b)weeks 错误的安全分类 / 去 raw 回显给出裁定。

### 2026-10-05 - weeks 窄 grammar（单/双周 + 已批准 qualifier）+ weeks 错误安全化

- 触发：Architecture Review 裁定 —— 批准 `expand_weeks()` 精确支持
  `N-M周` / `N-M单周` / `N-M双周` / `N-M周校外` / `N-M周校内(户外)`。
- **实现**（`backend/app/course_data/normalization.py`）：
  - `N-M单周` → 区间内**奇数周**；`N-M双周` → 区间内**偶数周**；
    `N >= 1` 且 `M >= N`；**过滤后为空 → fail closed**（⛔ 不生成空 weeks，如 `3-3双周`）；
  - `N-M周` + 已批准 qualifier → **与 `N-M周` 完全相同**（qualifier 只做白名单校验，
    ⛔ 不改数学含义、⛔ 不写入公共 `Meeting`、⛔ 未新增公共字段）；
  - **weeks qualifier 白名单本轮只有 `校外` / `校内(户外)`**：这是**第三张独立白名单**
    （另两张：sections suffix / parser non-concrete qualifier）；
    ⛔ `N-M周线上` **继续 fail closed**（sections 的 `线上` ⛔ 不迁移到 weeks）；
  - ⛔ **不用 `.*` / `startswith` / 无条件 strip qualifier**：qualifier 由白名单字面量 +
    整段锚定校验；
  - ⛔ 未顺便加入 `N-M周单双周` / `N,M周` / `第N-M周` / `N~M周` 等无证据形态。
- **错误安全化（本轮批准）**：`expand_weeks()` 不再回显 `{text!r}`，改为**稳定分类 token**：
  `unsupported_week_type` / `unsupported_week_shape` / `unsupported_week_range` /
  `unsupported_week_qualifier` / `unsupported_week_parity_range`
  （含逗号的多段组合归 `shape`，因为那是形状问题，不是 qualifier 问题）；
  ⛔ 未重构全局异常系统（分类写在 message 的稳定 token 里）。
- **测试**（`test_course_data_normalization.py`）：
  plain / odd / even / **非 1 起点**（`3-15单周`、`10-17单周`、`10-11单周`、`3-4双周`）/
  `校外` / `校内(户外)`（并与去 qualifier 的同一区间逐项相等）/ parity 过滤为空拒绝 /
  未知 qualifier 拒绝 / **`线上` qualifier 拒绝** / 非法区间 / 未确认形状（逗号组合、
  多段、`N-M周单周`、`第N-M周`、`N~M周`、全角）/ **raw token 不出现在错误信息中**
  （10 个被拒取值逐个断言 + 必须带安全分类）/ 非字符串类型分类。
  ⚠️ **两个既有用例按其裁定改写**：`test_unobserved_odd_week_ranges_are_rejected`
  （原断言"单周不泛化"）→ 改为 `test_parity_week_ranges_are_expanded`；
  `1-17双周` 从"未确认"列表移出（现为已批准形态）。
- **真实 artifact 再验收**（`daafdb18…a31b` 实测一致；⛔ 未建 SQLite；⛔ 未 skip）：
  - `load_capture_bundle` ✅（6 页 / total 1071 / rows 合计 1071）；
  - **第 5 个 blocker（weeks grammar）已清除**：只读聚合复核显示
    `expand_weeks_rejected = 0`（3475 个 token 全接受：
    plain 3382 + `校外` 54 + `双周` 15 + `单周` 13 + `校内(户外)` 11）⇒
    **此前 93 个 weeks blocker 全部消失**；
  - ❌ **第 6 个 fail closed 出现，且正如预期撞到那 49 个之一**：
    **安全错误类别 = `unsupported_sections_shape`**（⛔ 未回显 raw token，证明上一轮
    的安全化在真实链路上生效）；
  - **匿名结构**（只读诊断镜像 + 全量聚合，⛔ 无字面值）：
    49 个 = `C-CAC-CAN` × 30（5 字段）+ `C` × 10（4 字段）+ `C-C-CAN` × 9（5 字段）；
    **本次首个失败类别 = `C-C-CAN`（5 字段，该模板共 9 处）**；
  - ⛔ 那 49 个**按要求完全不动**，等待单独的 segment layout 裁定。
- 测试结果：normalization+parser+importer+pagination 合并 **454 passed**；
  full backend **2 failed / 2357 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例）；`compileall` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未建 SQLite；⛔ 未改公共 Schema；
  ⛔ 未改 collector / `captured_pages.py` / Capture Bundle format / `sharded_capture.py` /
  store / `planning_runtime.py` / PR #39 / Planner / Curriculum / frontend。
- 下一步：等待 Architecture Review 对 49 个 `unsupported_sections_shape`
  （segment layout）单独裁定。

### 2026-10-05 - 5 字段 non-concrete **layout A**（精确准入）+ 真实 artifact 到 Layout B 停止

- 触发：Architecture Review 正式批准 ——
  `Layout A: weeks | weekday | location | REDACTED | activity` 为 **5 字段 non-concrete**；
  **Layout B 本轮禁止处理**，继续 fail closed。
- **实现**（`backend/app/course_data/schedule_parser.py`，新增私有 helper
  `_try_parse_five_field_non_concrete_layout_a()`）：
  - **五条精确准入**（全部满足才接受，任一不满足 → 返回 `None` 落回原有 concrete 路径）：
    `f1` 现有 weeks parser 成功 / `f2` 现有 weekday parser 成功 /
    `f3` 现有 **location 判别器**（`_classify_five_field_token`，>= 3 个非空 `-` 分段）判定 location /
    `f4` **精确等于** collector 的 `REDACTED` 占位符 / `f5` 现有 activity 非空规则通过；
  - 判定位置在 `parse_sections(fields[2])` **之前**（该 layout 的第 3 字段是 location，不是 sections）；
  - 成功时 `meeting = None`，✅ 保留 `schedule_weeks`（走**现有** weeks parser）/ `teacher`（占位符）/
    `activity`，`schedule_qualifier = None`；⛔ 不生成 `Meeting`；
  - ⛔ 未新增 public Schema、⛔ 未新增 empty-meeting 路径：
    仍复用**现有** `build_course_offering_from_non_concrete_schedule()` → `meetings = []`；
  - 新增 parser 侧常量 `_REDACTED_TEACHER_PLACEHOLDER = "REDACTED"`
    （单一真源仍是 collector 的 `REDACTED_TEACHER`；⛔ 不放宽为包含 / 前缀 / 通配 / 空白容忍）。
- **synthetic 测试新增 20 项**（parser 159 → **183**，importer 76 → **78**）：
  layout A 成功（`meeting=None`、weeks 保留、teacher=占位符、activity 保留、`extract_meetings` 为空）/
  已批准 5 种 weeks 形态（plain / 单周 / 双周 / 校外 / 校内(户外)）在 layout A 下均可用 /
  混排不丢段 / **16 个近邻形态逐个 fail closed**
  （f1 非 weeks、f1 缺周字、f2 非 weekday、f2 空、f3 两段、f3 无连字符、
  f4 真实教师、f4 占位符前缀、f4 小写、f4 带空白、f4 空、f5 空、f5 全空白、
  字段重排、6 字段近似、Layout B）/ `Meeting` 字段集合不变 /
  已确认 concrete 5 字段（f3 是 sections）**不受影响** /
  importer 端到端 `meetings == []`（含与 concrete row 共存）。
  ⚠️ 自查纠正：两个**测试期望**写错并已修正（`f3 = 第5-6节` 其实是**合法 concrete** 形态，
  不属于近邻；Layout B 的失败点在 **weekday** 而不是 sections）。
- **真实 artifact 再验收**（`daafdb18…a31b` 实测一致；⛔ 未建 SQLite；⛔ 未 skip）：
  - `load_capture_bundle` ✅（6 页 / total 1071 / rows 合计 1071）；
  - ✅ **Layout A 39 条全部通过**（此前 blocker 清除）；
  - ❌ **随后在 Layout B 安全 fail closed**（与预期一致，已立即停止）：
    - 失败点：4 字段近邻的 `f2` 被当作 weekday 解析 → 现有 `parse_weekday` 拒绝；
    - 异常类型：`app.course_data.errors.CourseDataNormalizationError`；
    - ⚠️ **该错误信息回显了 raw location token**（真实校区 / 院系 / 教室文本）——
      属"不回显 raw 取值"的同类问题，但**不在本轮授权范围**（本轮仅授权 layout A + 不处理 B），
      故⛔ **未擅自修改**；本轮回报中已对该取值做 redact，⛔ 未写入任何文件；
  - ⛔ 未建 SQLite、⛔ 未 skip、⛔ 未把 B 降级为 `meetings=[]`。
- 测试结果：parser+normalization+importer+pagination 合并 **479 passed**；
  full backend **2 failed / 2384 passed / 2 skipped**（两个为**既有** Windows Curriculum 用例）；
  `compileall` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未建 SQLite；⛔ 未改公共 Schema；
  ⛔ 未改 collector（4 字段 teacher 脱敏仍未修，等下一轮裁定）/ ⛔ 未改 `captured_pages.py` /
  Capture Bundle format / `sharded_capture.py` / store / `planning_runtime.py` / PR #39 /
  Planner / Curriculum / frontend。
- 下一步：等待 Architecture Review 对(a)Layout B 的 segment layout 与
  (b)4 字段 teacher 脱敏修复 / 重抓，以及 (c) weekday 错误信息去 raw 回显 给出裁定。

### 2026-10-05 - weekday 错误安全化（A）+ 一次性零留存 Layout B 诊断（B）

- 触发：Architecture Review 本轮**只**批准两件事 ——
  **(A)** `parse_weekday()` 错误安全化（⛔ 不重构全局异常系统）；
  **(B)** 新增**一次性、零留存**的 Layout B 诊断能力（必须在 collector 做 minimize **之前**）。
  本轮明确**不做**：⛔ 不修改 Layout B parser、⛔ 不做 4 字段 teacher 脱敏、
  ⛔ 不建 SQLite、⛔ 不 push / 不 PR / 不 merge。
- **A. `parse_weekday()` 安全化**（`backend/app/course_data/schedule_parser.py`）：
  - ⛔ 不再回显 raw token；改为**稳定安全分类**：
    `unsupported_weekday_type`（非字符串，另附类型名）/ `unsupported_weekday_shape`
    （去空白后为空）/ `unsupported_weekday_value`（不在白名单）；
  - 白名单本身**未改**（仍只有 `星期一` … `星期日` → 1..7）；
  - ⛔ 未重构全局异常系统（分类写在 message 的稳定 token 里，与既有
    `unsupported_sections_*` / `unsupported_week_*` 同风格）。
- **测试（A）**（`test_course_data_schedule_parser.py`）：
  原 `test_known_gap_weekday_error_echoes_token`（**锁定 raw 回显**）按裁定替换为
  `test_weekday_error_no_longer_echoes_token`；新增
  `test_weekday_errors_are_classified_and_do_not_echo`（5 组：teacher 当 weekday、
  location 当 weekday、`星期天`、`周一`、空串 —— 逐个断言**分类存在**且**取值不出现在
  message 中**）与 `test_weekday_non_string_is_classified`（`None` / `5` / list / dict）。
- **B. 一次性零留存 Layout B 诊断**（`tools/sysu_course_offering_collector.js` 新增
  `diagnoseLayoutBCandidates()`；⛔ 未改 `collect()` / `collectSharded()` / 任何生产路径）：
  - 候选条件（**只看结构**，⛔ 不比对课程名 / 教师名 / 学院 / 不做模糊匹配）：
    `4 fields` + `f1` 已确认 weeks（plain / 单周 / 双周 / 校外 / 校内(户外)）+
    `f2` 已确认 location（复用 `countNonEmptyDashSegments() >= MIN_LOCATION_SEGMENTS`
    ⇒ 同时排除 weekday）+ `f3` 不是已确认 sections；
  - **在 minimize 之前**直接读 raw rows：`row[SCHEDULE_FIELD]` → 切段 → 内存比较
    `f3 === row.teachingName`（⛔ 不调用 `minimizeRow()`、⛔ 不脱敏、⛔ 不序列化）；
  - **只返回四个聚合计数**（单位 = 候选 segment）：
    `candidate_count` / `comparable_teaching_name_count` /
    `f3_equals_teaching_name_count` / `f4_activity_count`；
  - `teachingName` 用**属性存在性**判定（`Object.prototype.hasOwnProperty.call`）：
    **没有该属性 → `comparable` 不推进**（⛔ 不猜、⛔ 不用 `courseName` / `teacher` 顶替）；
  - ⛔ 不输出 teachingName / f3 / f4 / 课程号 / 教学班号 / 原文；⛔ 不产出 bundle、
    ⛔ 不落盘、⛔ 不写日志文件（⛔ 无 `console.*` / `JSON.stringify` / `Blob` / `download`）、
    ⛔ 不修改 raw row（测试断言 raw rows 前后序列化一致）；
  - ✅ 复用**同一** `requireAllowedHost()` / **同一** `requestPage()` /
    **同一** `createRequestPacer()`：诊断是**多页**的，⛔ 不得绕开全局批次冷却
    （测试断言相邻请求等待 `>= 30000ms`）；✅ 参数严格白名单
    `semester` / `openingSchoolNumber` / `maxPages`（⛔ 不放开 `pageSize` / `firstPageNo` /
    `delayMs`），且校验发生在**任何取页调用之前**；`maxPages > DEFAULT_MAX_PAGES` 时先确认，
    **取消 → fail closed（⛔ 不返回伪造的 0 计数）**；
  - ✅ 诊断内部 `data.total` 中途变化 → 整体 fail closed（⛔ 不重试 / 不跳页）。
- **测试（B）**（`tools/sysu_course_offering_collector.test.mjs`：92 → **107**）：
  15 项新增，全部为**人工虚构**合成数据 —— 4 真候选 + 5 近邻（f2 两段 / f3 是 sections /
  f1 非 weeks / 5 字段 / 6 字段）计数正确；**不泄露输入取值**
  （`Object.keys` 恰好四个 + `JSON.stringify(result)` 不含教师 / 活动 / 地点 / 班级号等合成值）；
  无 `teachingName` 时 `comparable = 0`；属性存在但非字符串 → 可比较但不等；
  四种已批准 weeks 形态计入、`1-8周线上` 不计入；f4 空白 / 空 → 不计 activity；
  **多页**跨页累计 + 第二页仍受 pacing（`calls === [1, 2]`）；未批准参数在请求前被拒；
  缺 `semester` 被拒；确认框行为（超 smoke 上限先确认、取消不发请求、默认不弹）；
  `data.total` 漂移 → 整体 fail closed；仅加载**不自动调用**（`calls.length === 0`）。
- **静态守卫（新增 11 项；`test_sysu_collector_guard.py` 84 → 95）**：
  Layout B 诊断暴露但**不自动调用**；⛔ 不在任何生产路径（`collect` / `collectSharded` /
  `collectPages` / `requestReportedTotal`）；返回值**恰好**四个计数（⛔ 无 rows / 标识 /
  分页元数据 / f3 / f4 / teachingName）；整段无打印 / 落盘 / 序列化；
  ⛔ 无 `bundle` / `minimizeRow` / `redactSegmentTeacher` / `CAPTURE_FORMAT`；
  比较在 minimize 之前（直接读 `row[SCHEDULE_FIELD]`）；复用同一 pacer 与页码边界；
  参数白名单严格且**先于**请求；候选 grammar **整段锚定 + 白名单**
  （⛔ 无 `.*` / `startswith` / `toLowerCase` / `includes`）；缺 `teachingName` **不猜**；
  f4 与 Python `_require_non_empty_token` 同规则。
  ⚠️ **两处既有守卫计数按其新事实更新**（⛔ 不是放宽）：
  `await requestPage(` 4 → **5**、`createRequestPacer(` 3 → **4**，并在注释里写明
  新增的第五个取页入口是**多页诊断**，因此必须传 pacer。
- **变异扫描（非真空性证明）**：`mutate_layout_b_diagnostic.py`（工作区脚本，⛔ 未入 Git）
  注入 **7 个 Node 行为变异 + 5 个静态守卫变异**，**12/12 全部变红**，采集器 SHA-256
  前后一致（`44ca7fdd…fbcf`，⛔ 文件已完整还原）。
  ⚠️ 自查纠正：第一次 P3 变异锚点 `var pacer = createRequestPacer(resolved.delayMs);`
  在 `collectSharded` 里也出现 → 变异误改到生产入口，出现**假绿灯**；
  改用诊断内部独有锚点后变红（已在脚本注释中记录该坑）。
- **A 的合成测试先行验证**（按要求）：诊断测试全部用人工虚构数据，
  先证明"只返回计数、不泄露输入值"，再交给负责人跑真实诊断。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未改公共 Schema / `schemas/` /
  `docs/interfaces/` / `mock_data/`；⛔ 未改 Layout B parser、⛔ 未做 4 字段 teacher 脱敏、
  ⛔ 未重抓、⛔ 未建 SQLite、⛔ 未改 `captured_pages.py` / Capture Bundle format /
  `sharded_capture.py` / store / `planning_runtime.py` / PR #39 / Planner / Curriculum /
  frontend；⛔ 真实材料（artifact / Capture Bundle / raw rows）未进入 Git。
- **真实请求数：0**（真实 east-campus 诊断由负责人在其授权会话中手动执行）。
- 下一步：由负责人在授权登录会话中执行一次性 Layout B 诊断；只有当
  `candidate = 10 / comparable = 10 / f3_equals_teaching_name = 10 / f4_activity = 10`
  时，才请求下一轮批准（Layout B parser + 4 字段 teacher 脱敏 + 重抓）。

### 2026-10-05 - Layout B 诊断第 2 轮：**只扩展一次性零留存诊断**（新增三个计数）

- **真实运行结果（负责人执行，east-campus 授权会话）**：

  ```text
  candidate_count                = 10
  comparable_teaching_name_count = 10
  f3_equals_teaching_name_count  = 0
  f4_activity_count              = 10
  ```

  ⇒ **`f3 = teacher` 假设被正式否决**（若成立应为 10/10）。
- **Architecture Review 裁定**：⛔ **禁止**实现 Layout B parser / 4 字段 teacher 脱敏；
  ✅ **只**扩展一次性零留存诊断，新增三个聚合计数：
  `f4_equals_teaching_name_count`、`f3_in_confirmed_activity_set_count`、
  `f4_in_confirmed_activity_set_count`；`confirmed_activity_set` **只能**来自"已有明确 layout 中
  已经确定为 activity 的固定槽位"；⛔ 不得再用"非空字符串 = activity"作为**字段角色证据**
  （可保留为**语法**检查）。
- **实现**（`tools/sysu_course_offering_collector.js`；⛔ 仍不碰生产链路）：
  - 新增 `confirmedActivitySlotIndex(segment)`：**字段角色只由 layout 结构确定**，
    与 production parser 的已确认 grammar 同规则 ——
    2 字段（`weeks(plain|+已确认 qualifier) / activity` → 槽位 1）、
    3 字段（`… / teacher / activity` → 槽位 2）、
    4 字段 concrete（`weeks / weekday / sections / activity` → 槽位 3）、
    5 字段 layout A（`… / location / REDACTED / activity`）与 5 字段 concrete
    （`… / sections / location-or-teacher / activity`）→ 槽位 4、6 字段 → 槽位 5；
  - 严格镜像 parser 的 grammar：weekday **七 token 白名单**（⛔ 无 `星期天`）、
    sections 白名单 + **数值规则**（`N >= 1`、`M >= N`）、weeks **数值规则**
    （`N >= 1`、`M >= N`、单/双周过滤后不得为空）、
    **non-concrete 2/3 字段的 f1 不含 parity**（Python 那两条路径只认 `N-M周`）、
    layout A 的 `REDACTED` **精确相等**（⛔ 无前缀 / 包含 / 折叠）、
    5 字段 f4 **二义 → 不算已确认**、6 字段用**通用** location grammar；
  - 集合**只在内存中构造**（`Set`）；候选 f3 / f4 先计入两个**极小的内存多重集**（`Map`），
    **全部页扫完后**才与集合求交 —— 保证**顺序无关**（否则 provider 出现在候选之后会被漏判，
    可能得出错误的字段角色结论）；三个结构 ⛔ 不返回 / ⛔ 不落盘 / ⛔ 不进 bundle / ⛔ 不写日志；
  - 扫完集合仍为空 → **fail closed**（⛔ 不返回会被误读为"不是 activity"的 0）；
  - ⛔ 无姓名启发式、⛔ 无 CJK 长度猜测、⛔ 不按 token 长度判断角色；
  - 返回值恰好**七个**计数（新增 `f4_equals_teaching_name_count`）；
    `f4_activity_count` 明确降级为**语法**检查（⛔ 不再作为角色证据）。
- **合成测试**（`sysu_course_offering_collector.test.mjs`：107 → **113**）：
  主场景七计数；**目标形态**（`f3 = activity`、`f4 = teacher` ⇒ `f3_in_set = 1`、
  `f4_equals = 1`）；**七种已确认 layout 的槽位都进入集合**（2 / 3 / 4 / 5-location /
  5-teacher / 5-layoutA / 6 字段逐个覆盖）；**候选自身不污染集合**（非循环）；
  **顺序无关**（候选在第 1 页、provider 在第 2 页仍命中）；
  **未确认 layout 一律不入集合**（parity 2 字段、`0-3周`、`5-3周`、`3-3双周`（layout A）、
  `星期天`、未批准 sections suffix、`REDACTED` 前缀变体、二义 5 字段，共 9 例）；
  **集合为空 → fail closed**；不泄露断言扩展到"集合取值也不得出现在输出中"
  （`Object.keys` 恰好七个 + 序列化里不得含任何 activity token / 教师 / 地点 / 标识）。
- **静态守卫**（`test_sysu_collector_guard.py`：95 → **100**）：返回值恰好七个计数且
  ⛔ 不含集合 / 多重集 / rows / 标识；集合**只来自已确认槽位**（七 token weekday 白名单、
  non-concrete 不含 parity、weeks / sections 数值规则、`REDACTED` 精确相等、二义排除、
  通用 location）；集合与多重集**只在内存**（⛔ 不挂全局 / ⛔ 不出现在返回值）；
  成员判定**只有一个实现且发生在分页循环之后**（⛔ 不得就地判定）；
  集合为空必须 fail closed；⛔ 无姓名启发式 / ⛔ 无 CJK 长度猜测 / `teachingName` 只出现 3 次。
- **变异扫描**（`mutate_layout_b_diagnostic.py`：**24 个变异 24/24 全部变红**，
  采集器 SHA-256 前后一致 `b46a35a1…cca1`，⛔ 文件已完整还原）：
  新增 Node 变异 N8–N15（成员判定恒真 / 破坏顺序无关 / 去掉 weeks 数值规则 /
  去掉 parity 非空规则 / `REDACTED` 前缀匹配 / 二义不排除 / 4 字段不校验 weekday /
  空集合不 fail closed）与守卫变异 P6–P9（返回值塞集合 / 集合挂全局 /
  注入 token 长度启发式 / 去掉 sections 数值规则）。
  ⚠️ 自查纠正：N11（去掉 parity 非空规则）第一次**假绿灯** —— 因为排除用例只覆盖了
  2 字段 parity（那条路径在形状白名单处就被挡住），已补上"layout A + `3-3双周`"用例后变红。
- **测试结果**：collector node **113 passed**；守卫 **100 passed**；
  parser+normalization+importer+pagination+guard 合并 **590 passed**
  （`-W error::SyntaxWarning`）；full backend **2 failed / 2409 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例）；`node --check` exit 0；`compileall app` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未改 Layout B parser、⛔ 未做 4 字段 teacher 脱敏、
  ⛔ 未重抓正式 artifact、⛔ 未建 SQLite、⛔ 未改公共 Schema / mock_data /
  `captured_pages.py` / Capture Bundle format / `sharded_capture.py` / store /
  `planning_runtime.py` / PR #39 / Planner / Curriculum / frontend；
  ⛔ 真实材料（artifact / raw rows / 任何 activity token）未进入 Git。
- **真实请求数：0**（第二次真实诊断仍由负责人在其授权会话中手动执行）。
- 下一步：负责人再跑一次同一诊断（同一命令），回报七个计数；
  只有在 `f3_equals_teacher = 0/10`、`f4_equals_teacher = 10/10`、
  `f3_known_activity = 10/10`、`f4_known_activity = 0/10` 全部成立时才请求正式裁定
  "Layout B = weeks | location | activity | teacher" 与后续 4 字段 f4 脱敏 / parser / 重抓。
- ⚠️ **解释边界（已在回报中明确）**：集合由**本次语料**枚举得到，
  `*_in_confirmed_activity_set_count = 0` ≠ "已证明不是 activity"
  （可能只是该 token 未出现在已确认槽位里）；必须与两个 `*_equals_teaching_name_count`
  一起读，⛔ 不得单独据 0 下结论。

### 2026-10-05 - Layout B 诊断第 3 轮：`f3` 的**原始字段名命中**统计（零留存）

- **第 2 次真实运行结果**（负责人执行，east-campus 授权会话）：

  ```text
  candidate = 10        comparable teachingName = 10
  f3 == teachingName = 0        f4 == teachingName = 0
  f3 ∈ 已确认 activity = 0      f4 ∈ 已确认 activity = 10
  ```

- **Architecture Review 正式裁定**：✅ **`f4 = activity` 确认**；⚠️ **`f3 = unknown`**；
  ⛔ **暂不修改 Layout B production parser**；✅ 只扩展一次性零留存诊断：
  对每个 Layout B candidate，在 raw row 中遍历**字符串类型字段**，统计 `f3 == raw[fieldName]`，
  最终只返回 `fieldName -> matched_candidate_count`（**只返回至少 1 次命中的字段名**）。
- **实现**（`tools/sysu_course_offering_collector.js`；⛔ 仍不碰生产链路）：
  - 新增第 8 个输出键 `f3_matching_raw_fields`（字段名 → 命中候选数）；
  - **严格字符串相等**：`thirdField === row[fieldName]`（⛔ 无模糊匹配 / ⛔ 无 substring /
    ⛔ 无分词 / ⛔ 无大小写折叠）；只遍历 `Object.keys(row)` 中 `typeof === "string"` 的字段；
  - **排除**：`courseNum` / `classNumber` / `teachingTimePlaceStr`（字面量）
    + **内部 ID**：具名 `timePlaceId` 与**形状规则** `/[Ii][Dd]$/`（字段**名**的机械规则，
    ⛔ **不是**对取值的模糊匹配）；
    ⚠️ **该形状规则随后被 Architecture Review 判为过宽（Blocker），已在下一轮收紧为
    "必须有 ID 词法边界" —— 见本文件后面的 Blocker 修复条目；此处保留当时的历史记录。**
  - ⛔ **只输出字段名**与计数（映射里不写入任何 raw 取值；`row[fieldName]` 在代码中
    只出现两次：类型判定 + 严格相等）；⛔ 多个字段同时命中 → **全部保留**（不自行裁定）；
  - ⚠️ 字段名按**码点排序**输出（结果稳定）；用 `Object.fromEntries` 构造映射
    ⇒ 字段名为 `__proto__` 时也**不污染原型**（已加合成测试）；
  - 该统计**不需要跨页集合**，因此天然顺序无关；其余七个计数与集合逻辑**未改动**。
- **合成测试**（`sysu_course_offering_collector.test.mjs`：113 → **118**）：
  严格相等命中 `courseName` / `yearTerm` / `score` 且 `limitNumber`（数字）**不**命中；
  按候选累计 + 多字段同时命中全部保留；`courseNum` / `classNumber` / `timePlaceId` /
  `someInternalId` / `internalID` 全部**不出现**在映射里；**substring 不命中**（超串 / 子串两例）；
  `__proto__` 字段名不污染原型；不泄露断言扩展到"任何取值都不得出现在输出中"
  （字段名本身是映射的键，按本轮裁定允许）。
- **静态守卫**（`test_sysu_collector_guard.py`：100 → **102**）：返回值恰好七个计数
  + 一个字段名映射；命中循环只遍历字符串字段、只做严格相等、`row[fieldName]` 只出现 2 次、
  映射只写字段名与计数（+1）、⛔ 无 `indexOf(` / `includes(` / `startsWith` / `toLowerCase` /
  `split(` / `substring`；排除清单四名字段 + 形状规则 + 调用点；`teachingTimePlaceStr`
  只作为排除清单字面量出现一次；映射构建不引用 `row[`。
- **变异扫描**（`mutate_layout_b_diagnostic.py`：**34 个变异 34/34 全部变红**，
  采集器 SHA-256 前后一致 `aef446ff…f670`，⛔ 文件已完整还原）：新增 N16 排除失效 /
  N17 substring 匹配 / N19 不再要求相等 / N20 映射写入 raw 取值 / N21 不再排序；
  P10 映射写入取值 / P11 去掉排除调用 / P12 不再排序 / P13 直接返回 Map /
  P14 去掉类型判定。
  ⚠️ **两处自查纠正（都曾造成假信号）**：
  (1) `P12` 第一次报 **MISS** —— 变异脚本对真实文件用 `read_bytes().decode()`，
  锚点是多行的而文件是 **CRLF** ⇒ 多行锚点永不命中；已改成"先归一化 LF 再写回 CRLF"；
  (2) `P11` 第一次 **假绿灯** —— 守卫只断言函数名，被**函数定义处**满足；
  已改为断言 `if (isExcludedMatchFieldName(fieldName)) {` 整个调用点。
- **测试结果**：collector node **118 passed**；守卫 **102 passed**；
  full backend **2 failed / 2411 passed / 2 skipped**（两个为**既有** Windows Curriculum 用例）；
  `node --check` exit 0；`compileall app` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未改 Layout B parser、⛔ 未做 4 字段 redaction、
  ⛔ 未重抓正式 artifact、⛔ 未建 SQLite、⛔ 未改公共 Schema / mock_data /
  `captured_pages.py` / Capture Bundle format / `sharded_capture.py` / store /
  `planning_runtime.py` / PR #39 / Planner / Curriculum / frontend；
  ⛔ 真实材料（artifact / raw rows / 任何取值）未进入 Git。
- **真实请求数：0**。
- 下一步：负责人再跑一次同一诊断（同一命令），把 `fieldName -> count` 发回；
  ⛔ 在此之前不裁定 `f3` 角色、不改 parser、不做 redaction、不重抓。

### 2026-10-05 - 无人值守收口：`f3` 命中统计的**验收矩阵**补齐（⛔ 无实现变更）

- 背景：裁定要求的 `f3_matching_raw_fields` **已在上一轮实现并提交**（`77d9977`）；
  本轮只补齐"自主验收"清单里尚未**逐条**覆盖的合成用例，并重跑全部验收；
  ⛔ **未改动任何实现语义**（诊断代码零改动）。
- **新增 4 项合成测试**（`sysu_course_offering_collector.test.mjs`：118 → **122**）：
  1. **单个字段 10/10**（10 个候选全部 `f3 == courseName` → `{ courseName: 10 }`）；
  2. **只统计 f3**（该行 `f4` 等于 `examMode` 的取值 → ⛔ 不产生任何条目；
     候选自身字段不污染证据）；
  3. **跨页累计**（候选分布在第 1 / 第 2 页 → `{ courseName: 2 }`，且页序 `[1, 2]` 不跳页）；
  4. **序列化不泄露**（专门构造 `courseName` / `yearTerm` / `score` / `examMode` /
     `openingUnitName` 五个唯一取值 → 映射里只出现**字段名**，⛔ 五个取值都不出现在
     `JSON.stringify(result)` 中）。
- **排除用例扩充**：新增裸 `id` 字段与**保守过度排除**用例 `valid`（以 `id` 结尾 →
  按机械形状规则一并排除，已在测试注释中写明"宁可少报"），
  排除用例总数 5 → **7**。
  ⚠️ **该"保守过度排除"随后被 Architecture Review 判为不可接受（false negative），
  已在下一轮收紧为词法边界并改为"`valid` 必须命中"的正向用例。**
- **新增 2 个变异**（`mutate_layout_b_diagnostic.py`：34 → **36 个变异，36/36 全部变红**）：
  `N22` 命中统计改成比较 **f4**（⛔ f4 不得参与）；`P15` 去掉**内部 ID 形状规则**。
- **验收矩阵（逐条）**：单字段 10/10 ✅ / 多字段同时命中 ✅ / 部分命中 ✅ / 无字段命中 ✅ /
  excluded fields 不参与 ✅ / non-string fields 不参与 ✅ / candidate 自身不污染证据 ✅ /
  跨页顺序不影响 ✅ / 返回值与序列化不含任何输入 token ✅。
  ⚠️ **本轮没有发现实现自身的 bug**（新增用例全部一次通过），因此**没有**任何实现改动。
- **测试结果**：`node --check` exit 0；collector node **122 passed**；
  守卫 **102 passed**；targeted（parser+normalization+importer+pagination+guard，
  `-W error::SyntaxWarning`）**592 passed**；full backend
  **2 failed / 2411 passed / 2 skipped**（两个为**既有** Windows Curriculum 用例）；
  `compileall app` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未改 Layout B parser / 4 字段 redaction /
  Capture Bundle format / 公共 Schema / store / runtime wiring / Planner / Curriculum /
  frontend；⛔ 真实材料未入 Git；**真实请求数 0**。
- 下一步：等负责人明天跑一次真实诊断并回传 `fieldName -> count`；
  ⛔ 在此之前不裁定 `f3` 角色、不改 parser、不做 redaction、不重抓。

### 2026-10-05 - Blocker 修复：内部 ID 字段判定收紧为**词法边界**

- **Architecture Review 裁定（真实运行前的 Blocker）**：`/[Ii][Dd]$/` 对内部 ID 字段的排除
  **过宽** —— 会把普通字段名（`valid` / `invalid` / `hybrid`）当成 ID 排除，
  造成 **false negative、降低诊断证明力**；不接受"保守过度排除"。
- **修复**（`tools/sysu_course_offering_collector.js`；⛔ 只改这一处判定）：
  - **精确字段名排除**（继续排除）：`courseNum` / `classNumber` / `teachingTimePlaceStr` +
    Review 清单 `courseId` / `class_ID` / `sumClassesID` / `outLineId` / `timePlaceId`；
  - **ID 词法形状**（必须有边界）：`fieldName.toLowerCase() === "id"`（裸 `id`，忽略大小写）、
    `endsWith("Id")`、`endsWith("ID")`、`/_id$/i`（下划线 + id）；
  - ⛔ **删除** `/[Ii][Dd]$/` 这条过宽规则（守卫断言其**不得**再出现）；
  - ⚠️ 由此 `valid` / `invalid` / `hybrid` **重新参与**统计；
    全小写无分隔符的 `xxxid`（如 `courseid`）按词法边界要求**不排除**
    （已在文档与测试中写明：若要覆盖需 Review 给出明确规则）；
  - ⚠️ **唯一** `toLowerCase` 出现在**字段名**规则处；取值 / 候选 grammar 仍**零大小写折叠**
    （守卫改为精确断言：全 section 只有 1 处 `toLowerCase`，且不得出现在
    `row[fieldName]` / `thirdField` / `fourthField` 上）。
- **测试**（`sysu_course_offering_collector.test.mjs`：122 → **124**）：
  排除清单用例扩充为 10 个候选（`courseNum` / `classNumber` / `id` / `timePlaceId` /
  `someInternalId` / `internalID` / `courseId` / `class_ID` / `sumClassesID` / `outLineId`）；
  新增"**词法边界正例**"用例（`id` / `lessonId` / `lessonID` / `lesson_id` / `lesson_ID` /
  裸 `ID` 全部排除）；新增"**普通单词必须命中**"用例
  （`valid` / `invalid` / `hybrid` / 无边界 `courseid` → 映射为
  `{ courseid: 1, hybrid: 1, invalid: 1, valid: 1 }`）。
- **守卫**（`test_sysu_collector_guard.py`：仍 **102 passed**，断言内容更新）：
  精确清单九名 + 词法形状四条（裸 `id` 大小写无关 / `Id` / `ID` / `_id` 忽略大小写）+
  调用点；⛔ `[Ii][Dd]$` 与旧常量**不得**再出现；`toLowerCase` 仅字段名规则处 1 次。
- **变异**（`mutate_layout_b_diagnostic.py`：36 → **39 个变异，39/39 全部变红**，
  采集器 SHA-256 前后一致、文件已字节级还原）：新增
  `N23` 回到过宽 ID 规则（被"`valid` 必须命中"用例抓住）、`N24` 不再判定 ID 后缀、
  `P15` 去掉下划线规则、`P16` 回到过宽规则、`P17` 去掉后缀判定、`P18` 去掉裸 `id` 判定。
- **测试结果**：`node --check` exit 0；collector node **124 passed**；守卫 **102 passed**；
  targeted（parser+normalization+importer+pagination+guard，`-W error::SyntaxWarning`）
  **592 passed**；full backend **2 failed / 2411 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例）；`compileall app` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未改 Layout B parser / collector production path /
  4 字段 redaction / Capture Bundle format / 公共 Schema / store / runtime wiring /
  Planner / Curriculum / frontend；⛔ 真实材料未入 Git；**真实请求数 0**。
- 下一步：真实运行前的 Blocker 已清除 ⇒ 等负责人明天跑那条唯一真实命令并回传
  `f3_matching_raw_fields`。

### 2026-10-05 - 分段续跑（safe segmented resume）：**判定为不可实现，fail closed**

- **触发**：负责人报告 —— 连续**两次**真实诊断都在**第 6 页**返回 `401 Unauthorized`。
  现有行为正确（立刻整体停止：⛔ 不重试 / ⛔ 不读认证 / ⛔ 不绕过登录）；
  根因是**一次 6 页扫描的耗时超过会话寿命**：第 6 个请求必然落在 5 请求批次冷却
  （300 s）之后 ⇒ 整轮约 7–8 分钟。
- **裁定要求的方案与其结论**：
  - **方案 A（keyed digest）**：语义可精确，但按裁定"checkpoint 同时含 key + 摘要 ⇒
    短 CJK token 可被离线枚举 ⇒ 默认不接受"；把 key 移出 checkpoint 又需要
    "用户额外保管 256-bit 秘密"的新交互与 async `crypto.subtle` 路径 ⇒ **未实施，需裁定**；
  - **方案 B（避免持久化 token-equivalence state）**：经分析与机器校验**不成立**（见下），
    重读式分段只是换一种扫全量，**不解决** 401 ⇒ 拒绝实施。
- **不可能性证明（机器校验，`prove_segmented_impossibility.mjs`，工作区脚本 ⛔ 未入 Git）**：
  用**真实实现**构造两个世界（第 1..5 页只差"候选 f3 的取值"、第 6 页完全一致）：
  - 世界 A：part1 候选 `f3` == 第 6 页 provider token → one-shot `f3_in_set = 1`；
  - 世界 B：part1 候选 `f3` 在语料中不存在 → one-shot `f3_in_set = 0`；
  - 两世界的 **part1 安全聚合投影逐字节相同**（`true`）、**第 6 页 rows 逐字节相同**（`true`）。
  ⇒ `finalize(state1, rows6)` 在两个世界中**输入相同、正确答案不同**
  ⇒ 任何确定性 finalize 都不可能同时正确 ⇒ **token-free checkpoint 无法与 one-shot 等价**。
- **重读路线的对称论证**：集合需要**全语料**的已确认 activity 槽位；1071 行 /
  `pageSize <= 200` ⇒ 至少 6 页，且无法在不读某页的前提下证明该页没有 provider
  ⇒ 任何精确评估都必须让 provider 与 candidate 在同一会话内存中共存 ⇒ 该会话需要读完
  整个语料（≥ 6 请求，仍越过 401 窗口）。
- **本轮交付**：⛔ **没有新增任何 API / 代码 / 测试**（没有实现就没有可测对象，
  裁定所列的分段等价性 / merge 顺序 / tamper / 隐私 / mutation 用例**无法**编写）；
  ✅ 只记录 fail-closed 结论、证明与可选项（A / B / C / D 见 `docs/status/course_data.md`）。
  ⛔ **未做任何近似实现**，⛔ **未降低任何诊断语义**。
- **回归（本轮零代码改动）**：`node --check` exit 0；collector node **124 passed**；
  守卫 **102 passed**；targeted **592 passed**；full backend
  **2 failed / 2411 passed / 2 skipped**（两个为**既有** Windows Curriculum 用例）；
  `compileall app` exit 0；mutation **39/39 变红**（沿用上轮结果，脚本未改）。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未改 Layout B parser / 4 字段 redaction /
  production collect·collectApprovedShard·collectSharded / Capture Bundle format /
  `captured_pages.py` / store / public Schema / runtime wiring / Planner / Curriculum /
  frontend；⛔ 真实材料未入 Git；**真实请求数 0**。
- 下一步：等待 Architecture Review 对 A / C / D 中任一路线（或"接受不续跑"）的裁定；
  ⛔ 在此之前不实现分段诊断。

### 2026-10-05 - 方案 D 实现：**分段式 f3 字段来源诊断**（六字段契约 + 零敏感 checkpoint）

- **裁定**：Architecture Review 选择 **方案 D** ——
  ⛔ 不改 pacing / cooldown、⛔ 不做 token / digest checkpoint、
  ✅ **保留现有完整 `diagnoseLayoutBCandidates()` 不动**，
  新增**仅用于 f3 raw-field 来源确认**的分段式诊断。
- **新增 API**（`tools/sysu_course_offering_collector.js`；⛔ 生产链路零引用）：

  ```js
  const part1 = await window.XuehangSysuCollector.diagnoseLayoutBFieldSourcePart({
    semester, openingSchoolNumber, startPage: 1, endPage: 5
  });
  const part2 = await window.XuehangSysuCollector.diagnoseLayoutBFieldSourcePart({
    semester, openingSchoolNumber, startPage: 6, endPage: 6, previousState: part1
  });
  const final = window.XuehangSysuCollector.finalizeLayoutBFieldSource(part2);
  ```

- **契约恰好六个输出**：`candidate_count` / `comparable_teaching_name_count` /
  `f3_equals_teaching_name_count` / `f4_equals_teaching_name_count` /
  `f4_activity_count` / `f3_matching_raw_fields`；
  ⛔ **不含** `f3_in_confirmed_activity_set_count` /
  `f4_in_confirmed_activity_set_count`（不是 0 / null，而是**不存在**于本接口契约）。
- **checkpoint schema（封闭键集合）**：`version` / `semester` / `openingSchoolNumber` /
  `page_size` / `expected_total` / `processed_pages: [{page_no, row_count}]` /
  五个数值计数 / `f3_matching_raw_fields: {字段名 → 计数}`；
  ⛔ 无任何 raw value；多一个键或版本不符 → fail closed。
- **校验（全部 fail closed）**：重复 / 重叠页（**发请求之前**拒绝，⛔ 不静默覆盖）、
  缺页（页码恰好 1..N 无洞）、`Σ row_count >= expected_total`（取满）、
  **页数与 total 自洽**（`N == ceil(total / page_size)`，防止改小 total 伪造完成）、
  `semester` / `shard` / `page_size` / `version` 绑定。
- **顺序无关**：支持无序合并（`6 + 1..5`、`4..6 + 1..3`），段间命中计数**累加**。
- **请求行为完全复用**：`requireAllowedHost()` / `requestPage()` / 全局 pacer / 页校验 /
  total 一致性；⛔ 不开放 `pageSize` / `delayMs`；⛔ 不改 batch / cooldown；
  401 / 403 / 600 / malformed / total 漂移 → 立即整体停止。
- **等价性（Node 测试逐项断言）**：`finalize(part(1..6))` == `1..5 + 6` == `1..3 + 4..6`
  == 逐页 `1+2+3+4+5+6` == 无序合并；另外与完整诊断的**六个重叠字段**逐项相等（防口径漂移）。
- **测试规模**：Node **124 → 145**（+21）；守卫 **102 → 109**（+7）；
  变异 **39 → 64**（+25）**64/64 全部变红**，采集器 SHA-256 前后一致并字节级还原。
- **⚠️ 三处自查纠正（都曾产生假信号）**：
  1. 变异脚本的 `-k layout_b` **把新守卫 `field_source` 整批 deselect** ⇒ P19–P24
     出现**假绿灯**；已改为 `-k "layout_b or field_source"`；
  2. 分段实现与完整诊断有**同形代码**（缩进不同），旧锚点按"第一处"替换会改到**另一处**
     ⇒ `N27`（total 漂移防护）出现**假绿灯**；已给 runner 加**锚点唯一性强制**
     （>1 处即报 `AMB` 视同失败），并给全部 64 个锚点标注 `[full]` / `[seg]`；
  3. 新测试里 VM realm 对象直接 `deepStrictEqual` 会因跨 realm 原型不同而失败、
     同步函数误用 `assert.rejects` ⇒ 已改为 `plain()` 摊平 + 对 `finalize` 用 `assert.throws`。
- **测试结果**：`node --check` exit 0；collector node **145 passed**；守卫 **109 passed**；
  targeted（parser+normalization+importer+pagination+guard，`-W error::SyntaxWarning`）
  **599 passed**；full backend **2 failed / 2418 passed / 2 skipped**
  （两个为**既有** Windows Curriculum 用例）；`compileall app` exit 0。
- **边界**：⛔ 未 push / 未 PR / 未 merge；⛔ 未改 Layout B parser / 4 字段 redaction /
  production `collect`·`collectSharded` / Capture Bundle format / `captured_pages.py` /
  store / public Schema / runtime wiring / Planner / Curriculum / frontend；
  ⛔ 真实材料未入 Git；**真实请求数 0**。
- 下一步：负责人按两段流程跑真实诊断（pages 1..5 → 重新登录 → page 6 + previousState）
  并回传六个结果字段。

### 2026-10-05 - Phase 1-2：Layout B（4 字段 opaque）production 收口 + 完整回归

- **裁定**：Layout B = `weeks | location | **opaque** | activity`；
  f3 是 **opaque / unmodeled** 槽位（⛔ 不得解释成 teacher / 地点 / 活动 / 其它业务字段）；
  collector 侧脱敏为 `REDACTED_OPAQUE`，parser 侧精确识别 → `meeting = None` → `meetings = []`
  （schedule UNKNOWN）。**Layout A 冻结**、concrete layout 不变、public Schema 不变。
- **Collector（`tools/sysu_course_offering_collector.js`）**：
  - 新增常量 `REDACTED_OPAQUE = "REDACTED_OPAQUE"`（与 teacher 的 `REDACTED` **互相独立**）；
  - 4 字段分支新增**精确** Layout B 判定：`f2` 是**严格** location
    （复用既有 `countNonEmptyDashSegments(...) >= MIN_LOCATION_SEGMENTS`）时，
    把 `fields[2]` 写为 `REDACTED_OPAQUE`；
  - ⛔ **不泛化**：concrete 4 字段与未归类 4 字段**保持原状**（⛔ 不新增 fail closed 分支）；
  - ⛔ 替换**前**校验 opaque 非空（空 / 非字符串 → 整体失败，⛔ 不用占位符掩盖），错误不回显取值；
  - ⛔ 无姓名 / CJK / 长度启发式，⛔ 不注入 `teachingName`。
- **Parser（`backend/app/course_data/schedule_parser.py`）**：
  - 新增 `_REDACTED_OPAQUE_PLACEHOLDER` / `_LAYOUT_B_NON_CONCRETE_FIELD_COUNT = 4` /
    `_try_parse_four_field_non_concrete_layout_b()`：四条精确准入
    （weeks / 严格 location / **精确** `REDACTED_OPAQUE` / activity 非空）；
  - 判定插在 `parse_weekday(fields[1])` **之前**（否则永远到不了）；返回
    `ParsedScheduleSegment(meeting=None, teacher=None, activity=..., schedule_weeks=weeks)`；
  - ⛔ **不解释 opaque**；⛔ 原始（未脱敏）取值**不被接受** ⇒ fail closed；
  - ✅ 复用既有 `build_course_offering_from_non_concrete_schedule()` → `meetings = []`；
  - ✅ Layout A / concrete 路径**未改动**。
- **测试**：parser **183 → 222**（layout B 合法 / 已批准 weeks 五形态 / 混排不丢段 /
  **20 个近邻形态 fail closed**：未脱敏原始取值、占位符前后缀 / 小写 / 前后空白 / 空、
  f1 非 weeks / 区间非法、f2 非 location / 两段 / weekday / sections / 空、
  f4 空 / 全空白、字段换位 ×2、5 字段近似、占位符互不通用 / concrete 4 字段不受影响）；
  importer **78 → 81**（`meetings == []` 端到端 + 与 concrete 共存 + 原始 opaque 整体失败）；
  collector node **145 → 150**（opaque 脱敏 / 只对精确 Layout B / 混排 / 空槽位 fail closed /
  序列化 bundle 不含 synthetic opaque secret）；守卫 **109 → 114**（占位符两侧一致、
  只对精确 Layout B 脱敏、parser 四条准入且不解释 opaque、判定早于 concrete 路径、
  Layout A / concrete 未变）。
- ⚠️ **自查纠正**：`test_layout_b_near_misses` 初版把"3 字段 `weeks/location/activity`"
  当成 Layout B 近邻 —— 它其实是**另一条已确认** layout（有自己的 grammar）⇒ 已从近邻清单移除
  并加注说明（⛔ 不改实现）。
- **Phase 2 完整回归**：`node --check` exit 0；collector node **150 passed**；
  守卫 **114 passed**；targeted（parser+normalization+importer+pagination+guard，
  `-W error::SyntaxWarning`）**636 passed**；full backend
  **2 failed / 2455 passed / 2 skipped**（两个为**既有** Windows-only Curriculum 用例，
  按要求⛔ 不修不 skip）；`compileall app` exit 0；mutation **64 → 72 个变异 72/72 全部变红**
  （新增 N40 泛化脱敏 / N41 不脱敏 / N42 去除空值校验；P27 接受任意 f3 / P28 放宽 f2 /
  P29 把 opaque 当 teacher / P30 放宽 Layout A / P31 两侧占位符漂移），
  collector 与 parser 两个文件 SHA-256 前后一致并字节级还原。
- ⚠️ **变异脚本扩展**：为 parser 侧变异新增**按文件定位**（target = collector / parser），
  并继续强制**锚点唯一**（>1 处即 `AMB`）。
- **边界**：⛔ **未 merge main**；⛔ 未改 public Schema / frozen Provider contract /
  Planner / Curriculum 语义 / runtime 架构；⛔ 未做真实登录或教务请求；⛔ 真实材料未入 Git。
- 下一步：Phase 3 consolidation、Phase 4 CLI 集成、Phase 5 真实操作包、Phase 6 push + PR。

### 2026-10-05 - Phase 3-5：consolidation 审计、CLI 集成现状、真实数据操作包

- **Phase 3（consolidation 审计，只读脚本 `audit_course_data_consolidation.py`，⛔ 未入 Git）**：
  六项清单全部通过 ——
  1. **diagnostics 不污染 production**：`collectPages` / `requestReportedTotal` / `collect` /
     `collectSharded` / `minimizeRow` / `requestPage` 六个 production 切片 + `importer` /
     `normalization` / `store` / `captured_pages` 四个模块，对 7 个 diagnostic 标记**零引用**；
  2. **无新增 raw-value 回显**：`schedule_parser.py` / `normalization.py` / `importer.py` /
     collector 的全部错误信息**不回显**捕获取值；
  3. **`meetings=[]` 唯一路径**：`normalization.py` 的
     `build_course_offering_from_non_concrete_schedule()` 定义**唯一**，
     `importer.py` 只调用**一次**，⛔ 无内联 `meetings=[]` 构造；
  4. **grammar / 占位符清单完整**：non-concrete 2 / 3 字段、layout B、layout A、
     concrete 4/5/6 字段、两侧 teacher 与 opaque 占位符全部在位；
  5. **fail-closed 标记完整**：opaque / Layout A 精确匹配、严格 location、
     weekday / sections / weeks / credit 四组安全错误分类；
  6. **Layout A 未泛化、Layout B 只按已批准 grammar 工作**。
  ⚠️ **审计自身修正**（首轮 4 个"问题"经逐条核实**全部为假阳性**）：
  (a) `{source!r}` 回显的是**调用方配置标签**（importer / normalization 入参，
  非学校返回值）⇒ 已列入允许清单；(b) `meetings = []` 在 `importer.py` 只出现在
  **docstring / 注释**中 ⇒ 已改为用 `ast` 精确剔除 docstring；
  (c) weeks / credit 的错误码定义在 `normalization.py`，首轮查错了文件 ⇒ 已修正。
  ⛔ **未发现真实隐私或 fail-closed 缺陷**。
- **Phase 4（CLI 集成）**：⛔ **无法执行** —— 指定的 commit
  `1bb8bfdbaddbaac7280702942ba0783c29722ec8` **在本地与远端都不存在**：
  - `git cat-file -t` → `could not get object info`；
  - `git fetch origin --prune`（经代理）拉取全部远端分支后，
    `git branch -a --contains 1bb8bfd` → 无结果；`git rev-list --all` 中无该前缀对象；
  - 全仓（所有 ref）按 `CLI` / `acceptance` / `artifact` 检索提交，只有 Curriculum CLI /
    Real Case A acceptance pack，**没有** Course Data artifact acceptance CLI。
  ⇒ 该项**未集成**（⛔ 不猜测等价提交、⛔ 不自行编写替代 CLI）。
  **需要用户提供该 commit（push 到远端或给出所在分支）**。
- **Phase 5（真实数据操作包）**：新增 `docs/data/REAL_CAPTURE_OPERATION_PACK.md`，
  含既有已批准分片表、导出命令（`toShardJson` / `toDiagnosticsJson`）、
  各校区 `scope_kind=campus` / `scope_id` / `source` 标签 / `expected_total` 口径、
  成功判据、`401` / `403` / `HTTP 600` / malformed 的停止说明，
  以及 **Layout B 重抓要求**（旧东校园 artifact 含原始 opaque ⇒ 必须重抓，⛔ 不得手工改写）。
  ⚠️ **Phase 5 暴露一个真实数据链路的首要阻塞项**：现有唯一采集入口 `collectSharded()`
  是**五个 shard（含北校园）的一次性、全有或全无事务**，调用方**不能选择 shard**；
  而北校园按裁定**保持 suspended**（真实 `HTTP 600` 证据）⇒ 五 shard 运行**预期必然失败**，
  因此 **East / South / Shenzhen / Zhuhai 目前无法单独取得 bundle**。
  ⛔ Builder **未**改动 `APPROVED_SHARDS`、⛔ 未新增单校区采集入口、⛔ 未跳过失败 shard
  —— 需要 Review 在两项中选择：**(A)** 批准一个"单校区采集"新入口；
  **(B)** 明确允许在北校园 suspended 期间跳过该 shard。
- **边界**：⛔ **未 merge main**；⛔ 未改 public Schema / frozen Provider contract /
  Planner / Curriculum 语义 / runtime 架构；⛔ 未做真实登录或教务请求；⛔ 真实材料未入 Git。
- 下一步：等 Review 对 (A)/(B) 与 CLI commit 给出裁定；随后 push + PR（PR 描述见下条）。

### 2026-10-06 - Autonomous Closeout（Phase 1-12）：单校区采集 + 审计 + 集成准备

- **Phase 1（single-approved-campus capture，✅ 已实现）**
  （`tools/sysu_course_offering_collector.js`）：
  - `collectApprovedShard({ semester, shardId, maxPages, delayMs })`：只采**一个已批准校区**，
    产出**标准裸 Capture Bundle**（⛔ 无 wrapper schema、⛔ 无 fake global page renumbering、
    ⛔ 不改五校区编排、⛔ 不改 public Schema）；
  - 固定白名单 `east-campus / south-campus / shenzhen-campus / zhuhai-campus / north-campus`
    （顺序即已批准顺序）；`shardId → openingSchoolNumber` 映射**内部固定**，
    且**不重复任何校区号**（号码只在 `APPROVED_SHARDS` 出现一次 = 单一真源）；
    ⛔ 调用方**不能**传 `openingSchoolNumber`（不在 options 白名单里 ⇒ 先于任何请求拒绝）；
  - **pacing**：单校区路径 `request interval >= 30 s` + **batch ceiling = 7**
    （依据已观测包络："30 s 间隔连续 7 次成功后第 8 次 `HTTP 600`" ⇒ 第 8 个请求必须落在冷却之后）；
    ordinary / 五校区路径**继续 = 5**；⛔ 未全局改 pacing（`MIN_DELAY_MS` / `BATCH_COOLDOWN_MS` 未动）；
    `createRequestPacer(delayMs, batchCeiling)` 的**默认值仍是** `MAX_REQUESTS_PER_BATCH`（守卫锁定）；
  - `semester` 显式绑定；`source_label` **不写入 bundle**（只作为导入时的审计标签）；
  - **北校园**：白名单保留、`operational: false` ⇒ 在**发请求之前** fail closed
    （⛔ 不重试、⛔ 不降级参数、⛔ 不换 endpoint、⛔ 不做任何绕过）；
  - 未取满（`stoppedReason !== "reached_total"`）⇒ fail closed，⛔ 不产出 bundle；
    401 / 403 / HTTP 600 / malformed / total 漂移 ⇒ 由 `requestPage()` 立即整体停止。
- **Phase 2（操作包完整化）**：`docs/data/REAL_CAPTURE_OPERATION_PACK.md` 重写：
  用户 9 步极简清单、四校区各自一条可复制命令、历史基线
  （East 1071 / South 2898 / Shenzhen 1171 / Zhuhai 1335 / North 405-suspended，
  ⚠️ 仅作参考，真实运行以当次 `data.total` 为准）、预计页数 / 请求数 / 耗时、
  成功判据、导出与 SHA-256 计算、导入 + provenance read-back、`scope_kind=campus` 口径、
  401/403/600 停止说明、⛔ 不得人工编辑 artifact、⛔ 不得把 North 缺失伪装成学期完整。
- **Phase 3（CLI 集成）**：再次 fetch 全部远端 ref 后，commit
  `1bb8bfdbaddbaac7280702942ba0783c29722ec8` **仍不存在**（`git cat-file -t` 失败、
  `--contains` 无结果、全仓无等价 Course Data acceptance CLI）⇒ **记录 blocker，未重建、未替代**，
  并按要求继续后续阶段。
- **Phase 4（SQLite / store 深度审计）**：逐条核对 16 项清单
  （campus / full_semester scope 语义、scope_id 校验、artifact_sha256 绑定、import history、
  current-row provenance、幂等重入、同 digest 不同 scope、不同 digest 同 identity 更新、
  事务边界、失败回滚、provenance read-back、重复 identity、source 首次值语义、
  db 计数 vs artifact 计数）⇒ **全部已由既有 `test_course_data_store.py`（51 项）覆盖**，
  ⛔ 未发现实现缺陷（本轮**未**为"覆盖已足"的项重复造测试）。
- **Phase 5（campus merge / completeness 审计）**：新增
  `backend/tests/test_course_data_campus_scope_completeness.py`（5 项）锁定语义边界：
  ① **低层** `merge_offering_snapshots()` **信任调用方 baseline**（四校区 + Σ(4) 会被接受）
  ⇒ "四校区 = 完整学期"⛔ 不能靠低层把关，必须走已批准五 shard 入口；
  ② `sharded_capture.py` **没有** "跳过 / suspended" 概念（静态断言）；
  ③ campus-scoped artifact 的 `complete` **只对该校区成立**，provenance 无学期级声明；
  ④ 四校区 artifact 并排入库后**仍无**任何 full-semester 声明；
  ⑤ `full_semester` 只能是**显式声明**（⛔ 不从 source / 文件名 / 校区数推断）。
- **Phase 6（runtime 兼容性）**：结论 **B —— PR #39 需要小改**（写入
  `docs/data/RUNTIME_AND_FRONTEND_COMPATIBILITY_REVIEW.md`）：
  PR #39（`feature/case-a-runtime-wiring`，commit `a4dc48ce…`，**open/未合并**）的装载模型是
  "**一个** Capture Bundle + **一个** SHA-256 + 一个内存快照"，而真实数据已变成
  **每校区 artifact + SQLite store + 需五 shard 齐备的 merge**；
  ⛔ 不是 A（单 gate 装一份 campus artifact 会被 `SnapshotCourseDataProvider` 当作整学期返回 ⇒ 静默不完整）、
  ⛔ 不是 C（frozen `CourseDataProvider.get_course_offerings(semester)` 不需改、store 已能按学期读）；
  ⇒ 需要**小改**：① 装载范围显式声明（`campus:<id>` / `full_semester:<semester>`，⛔ 不推断）；
  ② 多 artifact 入口（运行期合并 **或** store-backed provider）；③ campus 范围必须如实标注。
  ⛔ 本轮**未**合并 PR #39、⛔ 未改 runtime architecture；需要 Review 裁定
  "North suspended 期间 runtime 允许装载的最高范围"。
- **Phase 7（synthetic 结构 dry-run）**：逐条核对并给出证据（同文档 §2）——
  无 Mock fallback、未装配 503（`real_pipeline_not_configured`）、provider 异常向上传播、
  `meetings = [] → Planner UNKNOWN`（`planner/conflicts.py:85`、`feasibility.py:13/45/57`）、
  Layout A/B 不被当 CLEAR、`remaining_capacity=None` 不破坏 Planner、provider 只被调用一次。
  ⚠️ **不声明** Real E2E / LEVEL2 / LEVEL3 已通过。
- **Phase 8（frontend 兼容性审计）**：全部 ✅（同文档 §3，逐条 file:line 证据）：
  `meetings=[]` 中性文案（`labels.ts:142`）、⛔ 无 conflict-free 文案、
  `remaining_capacity=None → '—'`（`labels.ts:131-136`、`CourseOfferingList.vue:192`）、
  Real/Mock 模式清晰（`App.vue:78-82`，且 Real 结果禁用 Mock 课程名映射 `:90-93`）、
  ⛔ 无"已选课" / ⛔ 无"可直接执行"文案、503 不触发 Mock fallback（`api/plan.ts:7/32-37`）。
  ⚠️ **发现 1 处 API 层缺口（非显示 bug）**：`X-Data-Source` 响应头**只由 mock API 设置**
  （`api/mock.py:37`），真实 `POST /api/v1/plan` **不返回**该头 ⇒ 建议（需裁定）真实接口也返回
  `X-Data-Source: real`；⛔ 本轮未擅自改接口面。
- **Phase 9（诊断代码分类）**：2C1B / 2C1C / `diagnoseLayoutBCandidates` /
  分段式字段来源诊断 ⇒ **development-only，safe-to-remove-after-final-East-acceptance**；
  `collectApprovedShard` ⇒ **production-needed**。⛔ 不被 production 引用、⛔ 不自动运行、
  ⛔ 不读认证、⛔ 不泄露 raw value、⛔ 不污染 bundle（守卫锁定）。
- **Phase 10（PR #40 整理）**：PR #40 状态经 GitHub 公开 API 核实 ——
  `open` / **draft** / base `main`(`21f558f`) / head `fix/course-data-schedule-no-teacher`，
  `mergeable: true`、`mergeable_state: clean`；PR **head 会随 push 自动更新**。
  ⛔ 本机无 `gh`、⛔ 未读取任何凭据 ⇒ **PR 描述更新未执行**（已备好新描述文本，见 PR 包文件）。
- **Phase 11（第二轮审计）**：`git diff` / 隐私（raw-value 回显 grep + AST docstring 剔除）/
  parser over-generalization / mutation adequacy（锚点唯一性强制）/
  dead code / docs-code 一致性 / branch vs main 对比 / 最终测试重跑 —— 见下方回归数字。
- **Phase 12（release 包）**：极简用户清单写入操作包 §A（登录 → 四条命令 → 交 artifact →
  导入/read-back → Review → 明确合并）。
- **回归（本轮）**：`node --check` exit 0；collector node **159 passed**（150 → 159）；
  守卫 **121 passed**（114 → 121）；targeted（parser+normalization+importer+pagination+
  store+snapshot_merge+sharded_capture+campus_scope+guard，`-W error::SyntaxWarning`）
  **763 passed**；full backend 见提交说明；`compileall app` exit 0；
  mutation **78 个变异**（44 Node + 34 Python，含 Phase 1 新增：suspended 绕过 / options 放开 /
  批次上限改错 / 白名单重复号码 / 北校园标记可采集）—— 结果见提交说明。
- ⚠️ **自查纠正**：① 两条新变异（未取满 / source label 进 bundle）锚点与五校区**同形代码**冲突
  ⇒ 按"锚点必须唯一"的既有纪律**删除**这两条变异（其语义仍由 node 测试与静态守卫覆盖），
  ⛔ 不留假绿；② JSDoc 里的示意写法 `bundle: { … }` 会被 bundle-literal 守卫当成构造点
  ⇒ 已改写文案（守卫计数恢复 3）；③ `first_page_no:` 合法包含 `page_no:` 子串 ⇒ 守卫改为剔除后检查。
- **边界**：⛔ **未 merge main**；⛔ 未改 public Schema / frozen Provider contract /
  Planner / Curriculum 语义 / runtime architecture；⛔ 未自动登录、⛔ 未读 cookie/token、
  ⛔ 未发真实教务请求；⛔ 真实材料未入 Git。




### 2026-10-06 - PR #40 BLOCK 修复（Codex Architecture Review P1 + 3 项）

- **触发**：Codex Architecture Review 对 PR #40（HEAD `7d04b77`）给出 **BLOCK**；
  本轮**只**修 blocker，⛔ 不扩展新功能、⛔ 不改 runtime、⛔ 不集成 CLI、
  ⛔ 不改 full_semester acceptance、⛔ 不 merge。
- **P1（Layout B redaction admission 不够 exact）** —— collector 4 字段分支原先**只**检查
  `countNonEmptyDashSegments(fields[1]) >= MIN_LOCATION_SEGMENTS` 就脱敏；
  现改为与 **parser 四条准入逐条一致**：
  `f1 = isConfirmedWeeksToken（= expand_weeks 的接受集合，含 plain/单双周/已批准 qualifier）`
  / `f2 = 严格 location` / `f3 = non-empty opaque` / `f4 = non-empty activity` / `恰好 4 字段`；
  ⛔ 任一不满足 ⇒ **fail closed**（⛔ 不放行到 bundle：那会把 opaque 原文带出去），
  且三个校验都**早于**脱敏写入。⛔ 未泛化 Python parser、⛔ 未改 Layout A、⛔ 未改 public Schema。
  - 新增 node 用例：`NOT-WEEKS/location/SECRET/activity` 与 `1-5周/location/SECRET/`（空 activity）
    都 fail closed 且**不回显取值**；已批准 parity / qualifier weeks（单/双周 / 校外 / 校内(户外)）
    **仍必须**被脱敏（⛔ 不得因收紧而误杀合法 Layout B）。
- **② 单校区 401/403/600 测试**：原用例虽写 `[401,403,600]` 循环，但**始终**配置 `http600`
  ⇒ 三个状态并未真实分别执行。已新增专用 `loadStatusCollector(rows, status)` 并在
  三个状态上**各自真实**断言（每个状态 1 次请求 + 立即停止）。⛔ 未改共享 helper。
- **③ production 错误反射**：
  - `payload.code` 不再原样进错误消息 ⇒ 稳定安全分类 `code_not_200`；
  - fetch catch 不再拼接 `error.message` ⇒ 稳定安全分类 `network_error`；
  - `unwrapErrorMessage()` 改为**只信任自有错误**（message 以 `ERROR_PREFIX` 开头），
    其它来源（fetch / 运行时 / 第三方）一律折叠为 `unexpected_error`；
    ⛔ 不再 `String(error)`、⛔ 不回显 `error.message` / `error.name`。
  - 新增 node 用例：任意 `payload.code`（`SECRET-CODE-ALPHA`）与任意
    `error.message`（`SECRET-NET-ALPHA`）都**不出现在**错误消息中，且分类存在。
- **④ development-only 分段 state**：`validateLayoutBFieldSourceState()` 原先**只**逐项比较
  排序后的键数组 ⇒ **多出来的键若排序靠后会被漏过**；现改为**先比键数量、再逐项校验**
  （state 顶层 + `processed_pages` 元素各一处）。新增 node 用例断言
  `zzz_extra`（排序最后）与 `processed_pages[0].zzz` 都被拒绝。
- **⑤ CLI 事实更新**：远端已可见
  `feature/course-data-artifact-acceptance-cli` 与 commit
  `1bb8bfdbaddbaac7280702942ba0783c29722ec8`（"feat(course-data): add artifact acceptance CLI"），
  已 fetch 确认可达；⛔ **本轮按要求未集成**（记录事实，留待后续裁定）。
- **回归**：`node --check` exit 0；collector node **166 passed**（159 → 166）；
  守卫 **124 passed**（121 → 124）；targeted（parser+normalization+importer+pagination+
  store+snapshot_merge+sharded_capture+campus_scope+guard，`-W error::SyntaxWarning`）
  **766 passed**；full backend **2 failed / 2470 passed / 2 skipped**（两个既有
  Windows-only Curriculum 用例，⛔ 未修未 skip）；`compileall app` exit 0；
  mutation **87 个变异全部变红**（50 Node + 37 Python；collector 与 parser SHA-256 前后一致、
  字节级还原）。新增变异：`N48/N49` 去掉 weeks / activity 准入、`N50/N51` 重新反射
  code / message、`N52` 去掉 state 键数量检查；守卫层 `P35–P38` 同主题。
  ⚠️ **自查**：另有一条 `N53`（去掉 page entry 键数量检查）**不可观测** ——
  逐项循环边界是 `entryKeys.length`，多出的键必然在逐项比较中失败 ⇒
  该长度检查对 entry 属**冗余防御**；按"⛔ 不留假绿、也不造无意义测试"的纪律**删除**该变异，
  保留长度检查本身（defence in depth）。
- **边界**：⛔ 未 merge；⛔ 未改 public Schema / frozen Provider contract / runtime /
  Planner·Curriculum 语义；⛔ 未自动登录、⛔ 未读 cookie/token、⛔ 未发真实教务请求；
  ⛔ 真实材料未入 Git。
- 下一步：push 同一 branch + 更新 PR #40 描述（本机无 `gh` ⇒ 提供可粘贴文本），
  之后等 Codex/Architecture Review 重新评审。

### 2026-10-06 - PR #40 Blocker Fix Round（定点补强 + 过期事实修正）

- **基线澄清（事实）**：本轮开工时仓库 HEAD 已是 `957aaaf`
  （上一轮 "PR #40 BLOCK 修复"），**不是** 报告里写的 `7d04b77`；
  P1（Layout B 精确准入）与 error-reflection / diagnostic extra-key 三项
  **已在 `957aaaf` 修完并 push**。本轮在此之上补齐**adversarial 断言**、**未覆盖的
  weeks 形态**、**过期文档**与**runtime 决定记录**，并重跑全量验证。
- **P1 最终逻辑（collector 4 字段分支）** —— 五条全部满足才把 `fields[2]` 写为
  `REDACTED_OPAQUE`：

  ```text
  恰好 4 字段
  f1 = isConfirmedWeeksToken（镜像 parser 侧 expand_weeks 的接受集合）
  f2 = countNonEmptyDashSegments(fields[1].trim()) >= MIN_LOCATION_SEGMENTS（严格 location）
  f3 = non-empty opaque
  f4 = non-empty activity
  ```

  ⛔ 任一不满足 ⇒ fail closed 且**不产出 bundle**；三处校验都早于脱敏写入；
  ⛔ 未泛化 parser、⛔ Layout A 未改、⛔ public Schema 未改、⛔ 无 CJK/name 启发式。
- **① 新增 adversarial Node 用例（本轮到 169 项）**：
  - `NOT-WEEKS/...` 与空 activity ⇒ fail closed 且**不回显取值**；
  - **malformed / 未批准 weeks 七形态**（`5-3周` / `0-3周` / `1-5` / `第1-5周` / `abc周` /
    `1-5周单周` / **`1-5周线上`**）⇒ collector 侧 fail closed（⛔ 不依赖 parser 事后拒绝），
    且错误文案不回显 raw token；
  - 严格 location 之外的 4 字段近邻（两段 `-`）⇒ **不得误 redact**；
  - 精确 Layout B（含 parity / qualifier weeks）⇒ f3 精确替换为 `REDACTED_OPAQUE`、
    raw opaque 不出现在 bundle JSON（既有用例 + 本轮保持）。
- **② 401 / 403 / 600 真实分别覆盖**：新增专用 status harness，**每个状态**断言
  对应 status 确实被触发（错误文案含该状态码）、**恰好一次失败请求**（`calls === [1]`）、
  无重试 / 无下一页 / 无后续 shard 请求、**不产出 bundle**。
- **③ error reflection**（`957aaaf` 已修，本轮复核）：`payload.code` → `code_not_200`；
  fetch `error.message` → `network_error`；`unwrapErrorMessage()` 只信任自有
  `ERROR_PREFIX` 错误，其余折叠为 `unexpected_error`；adversarial 用例断言
  `SECRET-CODE-ALPHA` / `SECRET-NET-ALPHA` 不出现在最终错误字符串中。
- **④ diagnostic exact-key**（`957aaaf` 已修，本轮复核）：`validateLayoutBFieldSourceState()`
  **先比键数量、再逐项校验**（state 顶层 + `processed_pages` 元素）；
  用例断言 `zzz_extra`（排序最后）与 `processed_pages[0].zzz` 都被拒绝；
  ⛔ 未改 production bundle format。
- **⑤ 过期文档修正（本轮）**：
  - 删除"**没有单校区采集入口**"（已过期）⇒ 改为"✅ 单校区采集入口已实现"，
    并写明白名单 / 内部映射 / 单校区 batch ceiling **7** vs 五校区 **5** /
    北校园 suspended fail closed / 未取满 fail closed；
  - 删除"**CLI commit 在本地与远端都不存在**"（已过期）⇒ 改为"✅ CLI 已在远端可见：
    `feature/course-data-artifact-acceptance-cli` / `1bb8bfd…`；⚠️ 本轮未集成"；
  - 新增 **runtime 正式决定**记录（只记录、⛔ 不改实现）：PR #39 as-is **FROZEN /
    DO NOT MERGE**、`campus complete != full semester complete`、
    production runtime 后续必须依赖 SQLite 中的**显式 full_semester acceptance/provenance**、
    North suspended 期间**不得**产生 full_semester acceptance、formal Real E2E 继续 **LEVEL0**。
- **⑥ 回归（串行执行，mutation 与 full backend 不并发）**：
  `node --check` exit 0；collector node **169 passed**；守卫 **124 passed**；
  targeted（parser+normalization+importer+pagination+store+snapshot_merge+
  sharded_capture+campus_scope+guard，`-W error::SyntaxWarning`）**766 passed**；
  full backend **2 failed / 2473 passed / 2 skipped**（两个既有 Windows-only
  Curriculum 用例，⛔ 未修未 skip）；`compileall app` exit 0；
  mutation **87 个变异全部变红**（50 Node + 37 Python），
  collector 与 parser SHA-256 前后一致、字节级还原。
- **边界**：⛔ 未 merge main；⛔ 未 cherry-pick CLI；⛔ 未改 PR #39；⛔ 未改 runtime
  implementation / public Schema / frozen Provider contract；⛔ 未自动登录、
  ⛔ 未读 cookie/token、⛔ 未发真实教务请求、⛔ 未抓 East/South/Shenzhen/Zhuhai。

### 2026-10-06 - Course Data Real Artifact Acceptance CLI（campus-only Gate）

- 新增内部 CLI `tools/validate_course_data_artifact.py`：把本地 Capture Bundle 的
  exact-byte SHA-256、现有 bundle validation、snapshot normalization/completeness、
  campus scope 绑定与可选 SQLite import / provenance read-back 串成确定性流程；
- **scope 收紧（本 Gate）**：单 artifact acceptance **只允许** `scope_kind = campus` +
  `scope_id = <openingSchoolNumber>`；⛔ `full_semester` 一律 reject（不提供该选项）；
  ⛔ missing scope / unknown scope kind / blank scope_id 一律 reject；
- **source 绑定（本 Gate）**：必须精确等于
  `capture://sysu/<semester>/campus/<scope_id>`（semester / scope_id 双重一致）；
  `source` 只是 audit label，⛔ 不构成 provenance proof；
- **SQLite read-back 强化（本 Gate）**：导入后逐项核对 `artifact_sha256` / `semester` /
  `scope_kind == campus` / `scope_id` / `completeness` / `loaded_count` / `reported_total` /
  offering 计数，并要求 `inserted + updated + unchanged == offering_count`；
  ⛔ **不把** `db_offering_count` 当成当前 artifact 的 offering count（summary 文案已明确区分）；
- ⚠️ **事务 caveat（写入 docs）**：import commit 与 provenance read-back **不是同一事务**
  ⇒ ⛔ 不得声称"CLI 非零退出 == SQLite 零变化"；
- fail-closed：read/hash、malformed bundle、normalization、semester mismatch、scope、source、
  incomplete/empty snapshot 均非零退出；normalization/parser 异常不 skip / continue，
  CLI ⛔ 不打印异常消息（避免回显原始 schedule token）；失败前不调用 SQLite；
- 测试（synthetic / zero-network）：valid campus artifact、full_semester reject、
  arbitrary source reject、source 中 semester/campus 错配 reject、raw-byte hash 正确、
  错误 digest reject、incomplete reject、empty reject、SQLite import 成功、
  provenance 精确 read-back、inserted+updated+unchanged 对账、db_offering_count 文案、
  normalization secret 不泄露、异常文本不泄露；
- ⛔ 未改 schedule parser / collector / Capture Bundle format / public schemas / runtime /
  Planner / Curriculum / frontend / PR #39；⛔ 未发网络请求、⛔ 未处理真实 artifact。

### 2026-10-06 - Acceptance CLI Integration Gate（campus-only）

- **分支**：从 main `d3a451b` 新建 `feature/course-data-acceptance-cli-integration`（⛔ 不用旧分支）；
  **cherry-pick** CLI commit `1bb8bfd`（来源 `feature/course-data-artifact-acceptance-cli`）：
  代码文件干净落地；`docs/status/course_data.md` 与 `docs/worklogs/course_data.md`
  **冲突手工解决** —— 保留 main 中 PR #40 的最新事实，再追加 CLI 的 campus-only Gate 说明
  （⛔ 不整文件覆盖、⛔ 未带回旧 parser / collector / store 实现）；
- **Phase 2 收紧**：`--scope-kind` **移除**，CLI 固定 `scope_kind = campus`；
  ⛔ `full_semester` 无表达路径（传 `--scope-kind` 即 `invalid_arguments`）；
  ⛔ missing scope / blank scope_id / unknown scope kind 均 reject；
- **Phase 3 source**：精确等于 `capture://sysu/<semester>/campus/<scope_id>`
  （semester 与 scope_id 双重一致）；仍只是 audit label，⛔ 不是 provenance proof；
- **Phase 4 链路保持**：raw bytes → SHA-256 → `load_capture_bundle` →
  `collect_captured_pages_snapshot` → campus completeness → `SnapshotScope(campus, scope_id)`
  → 可选 SQLite import → provenance read-back；新增**可选** `--expected-sha256` gate；
- **Phase 5 read-back 强化**：逐项核对 digest / semester / campus scope / source /
  completeness / loaded_count / reported_total / offering_count +
  `inserted + updated + unchanged == offering_count`；
  `db_offering_count` 更名为 `db_semester_offering_count` 并加 `*_semantics` 标注
  （⛔ 不改公共 store API，只改 summary 文案）；
  新增 **empty（0 offering）snapshot** fail closed（独立退出码 `EXIT_EMPTY_SNAPSHOT = 8`）；
- ⚠️ **事务 caveat 明确写入 docs**：import commit 与 read-back 非同一事务 ⇒
  ⛔ 不得声称"非零退出 == SQLite 零变化"；
- **测试**：CLI targeted **10 → 17 passed**（新增：full_semester 不可表达、
  arbitrary source、source semester / campus 错配、`--expected-sha256` 错 digest、
  empty snapshot、幂等重入对账 + 学期级/artifact 级计数区分、异常文本不泄露）；
- **回归**：CLI targeted 17；Course Data targeted（parser/normalization/importer/
  store/snapshot/sharded/campus-scope/guards）；full backend；compileall —— 见提交说明；
  两个既有 Windows-only Curriculum failure ⛔ 不修不 skip；
- **边界**：⛔ 未 merge main、⛔ 未改 PR #39、⛔ 未改 runtime / public Schema /
  frozen Provider contract、⛔ 未发真实教务请求、⛔ 未读 cookie/token、⛔ 未处理真实 artifact。

### 2026-10-06 - Gate A：Five-shard Full-Semester Acceptance

- **分支**：从 main `1cd08e0`（PR #41 merge）新建
  `feature/full-semester-course-data-acceptance`；⛔ 未 merge main、⛔ 未改 PR #39；
- **新增内部模块** `backend/app/course_data/full_semester_acceptance.py`：
  `accept_full_semester_capture_set(...)` + `ShardArtifact` + `FullSemesterShardRecord`
  + `FullSemesterAcceptance` + `canonical_manifest_bytes()` / `compute_manifest_sha256()` /
  `full_semester_scope()` / `full_semester_source()`；
  ⛔ **未改** `merge_offering_snapshots()` / Capture Bundle format / public Schema /
  frozen Provider contract；
- **A1 baseline**：真实采集侧只有**总量证据** ⇒ 不要求 baseline `OfferingSnapshot`；
  `baseline_before == baseline_after`（否则 `snapshot_window_unstable`）+
  `Σ shard reported_total == 稳定 baseline`（否则 `shard_coverage_mismatch`）；
  ⛔ 未用 `page_count` 推导 completeness；
- **A2 exact five-shard**：slug 白名单 + `openingSchoolNumber` 单一真源；
  缺 / 多 / 重复 / 别名一律 reject；⛔ 未提供任何逃生参数；
  与 collector `APPROVED_SHARDS` 的一致性由测试逐项强制（东 5063559 / 南 5062201 /
  深圳 333291143 / 珠海 5062203 / 北 5062202）；
- **A3 merge**：identity `(semester, course_id, class_id)`；先做**跨 shard 独立扫描**，
  载荷一致 ⇒ `duplicate_identity_across_shards`，载荷不一致 ⇒
  `conflicting_identity_across_shards`；之后仍调用已 Review 的底层 merge，
  并对**物化结果**重新计数（行数 / unique identity）；
- **A4 manifest**：canonical（`sort_keys` + `(",", ":")` + UTF-8）+ manifest SHA-256
  作为 acceptance identity；`shards[]` 只含结构性计数与 raw bundle SHA-256；
  ⛔ 无 token / 用户信息 / raw row / 课程取值；
  顺序固定为已批准顺序 ⇒ 传入顺序不影响 digest（有测试）；
- **A5 SQLite**：`SnapshotScope(full_semester, semester)` + manifest SHA →
  `import_offering_snapshot` → provenance read-back 逐项核对 +
  `inserted+updated+unchanged` 对账；⛔ 单 campus CLI 不能表达 `full_semester`；
- **A6 CLI** `tools/accept_full_semester_course_data.py`：
  `--semester` / `--baseline-before` / `--baseline-after` /
  `--east|--south|--shenzhen|--zhuhai|--north`（全部 **required**）/
  `--expected-manifest-sha256` / `--output-manifest` / `--sqlite`；
  ⛔ 无 `--scope-kind` / `--source`（source 由 semester 完全决定 ⇒ 调用方无法自选）；
  失败输出只含 `status / stage / category / exception_type`（+ 结构性 `shard_id`），
  ⛔ 不打印异常文本 / 路径 / 文件名 / 取值；manifest 原子写入 + 落盘后复算 digest；
  事务 caveat 写入模块 docstring（import commit 与 read-back 非同一事务）；
- **A7 tests**：`test_course_data_full_semester_acceptance.py` +
  `test_full_semester_acceptance_cli.py` = **88 passed**，覆盖
  happy path / 缺任一 shard / 缺两个 / 重复 shard / 6 个 shard / 别名 /
  baseline 漂移 / 和小于与大于 baseline / 非整数 baseline / 零 baseline /
  缺文件 / digest gate（错误 digest 与非字符串）/ 非法 bundle / semester 错配 /
  partial shard（含"总和仍等式"变体）/ empty shard / 跨 shard 重复与冲突 identity /
  merge 失败 / 物化计数复核 / 验收期间 artifact 被改写 / manifest 确定性（含传入顺序无关）/
  canonical 形式 / digest 随 raw bytes 变化 /
  SQLite import + read-back + 幂等重入 + 失败前不写库 / 既有库不产生 full_semester 记录 /
  逃生参数不存在 / campus scope 不可表达 / 失败阶段与退出码一一对应 /
  shard 表与 collector 表一致 / 隐私（manifest 与错误均不含取值）；
- **mutation sweep**（workspace-only `mutate_full_semester_acceptance.py`，
  34 处唯一锚点变异、逐文件、按字节还原并核对 SHA-256）：**29 killed / 5 survived**；
  5 个 survivor = **可证等价**的冗余防御子句（A04 / A05 / A06 / A07 / A14），
  已在代码内逐条注明"冗余但保留"，⛔ 未删除、⛔ 未计为 killed；
- **边界**：⛔ 未 merge main、⛔ 未改 PR #39 / runtime / public Schema /
  frozen Provider contract、⛔ 未发真实教务请求、⛔ 未读 cookie/token、
  ⛔ 未处理真实 artifact、⛔ 未声明 Real E2E（继续 **LEVEL0**）。

### 2026-10-06 - Forward Red-Team BLOCK 修复（B1 / B2 / B3）

- **分支**：从 Gate A tip `c01b7c9` 新建 `fix/full-semester-acceptance-blocks`
  （Reviewer 审计的正是该 HEAD）；
- **B1 同源字节**：`captured_pages.load_capture_bundle_bytes()`；
  `_read_shard_bundle_once()` 只读一次 ⇒ digest / parse 同源；复读降级为额外探测；
  campus CLI 同样改为解析被 hash 的 bytes；
- **B2 独立 scope 绑定**：新增 `CaptureInventory` + `load_capture_inventory()` +
  `build_capture_inventory()`（草稿）+ `capture_inventory_bytes()`；
  正式 acceptance 逐 shard 核对 inventory digest、approved openingSchoolNumber、
  campus acceptance 记录的 digest / scope / canonical source / counts /
  内容 digest；⛔ 无 inventory / ⛔ 无 campus-store 直接 fail closed；
  ⛔ 同一批字节两个校区在 inventory 阶段即被拒；
- **B3 内容绑定**：新增 `offering_digest.py`；manifest v2 增加
  `inventory_sha256` / `merged_offering_set_sha256` / 每 shard
  `campus_acceptance_sha256` / `campus_source` / `campus_offering_set_sha256`；
  新增严格 manifest 校验器（未知字段 / 重复键 / NaN / bool 计数 / 非批准 shard 全部拒绝，
  shard 数组按批准顺序语义规范化）；
- **store content-bound 平面**：`course_data_acceptance` +
  `course_data_acceptance_member`；`import_offering_snapshot()` 在同一事务写两个平面 +
  逐行内容指纹；新增 `load_course_data_acceptances()` 与 `load_accepted_offerings()`
  （一次一致读事务内核对两个平面 / membership / 逐行指纹 / 整批 digest / 行级 provenance）；
- **CLI**：`--inventory` 与 `--campus-store` 必填；新增 `--draft-inventory`
  （只写 canonical 草稿、⛔ 不做 acceptance、⛔ 不写库）；退出码 9（inventory）/
  10（campus binding）；回读改用 content-bound 平面并核对整批 digest；
- **测试**：module `test_course_data_full_semester_acceptance.py` **70 passed**
  （含 A/B/A 交错同源、inventory 校验矩阵、campus 绑定矩阵、内容 digest 敏感性、
  manifest 校验器）；CLI **49 passed**（含草稿模式、绑定失败、真实 campus→full 两步流程、
  内容篡改读回检测）；store **78 passed**（含 6 种同数量内容替换、
  两个平面一致性、删除 acceptance、scope 参数化、陈旧行隔离）；
  full backend **2623 passed**（2 个既有 Windows-only Curriculum failure）；
- **文档**：`docs/data/FORWARD_REDTEAM_RESPONSE.md`（BLOCK 关闭方式 + 20-case 矩阵映射）、
  `FULL_SEMESTER_ACCEPTANCE.md`（v2 契约 / inventory / 内容绑定 / 退出码）、
  `ARTIFACT_ACCEPTANCE_CLI.md`（B1 + content-bound 回读 + 字段语义）、
  `REAL_CAPTURE_OPERATION_PACK.md`（§E2 两步流程 + 草稿 inventory）；
- **边界**：⛔ 未 merge main、⛔ 未改 PR #39 / public Schema / frozen Provider contract、
  ⛔ 未处理真实 artifact、⛔ 未发真实网络请求；formal Real E2E 继续 **LEVEL0**。
