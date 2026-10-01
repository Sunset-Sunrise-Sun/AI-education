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

