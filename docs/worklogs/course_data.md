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

