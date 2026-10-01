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

