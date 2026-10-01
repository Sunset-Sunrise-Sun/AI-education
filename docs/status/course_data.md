# Course Data 当前状态

> 最后更新：2026-09-30（**Phase 2B-2A：Course Data Normalization Core** 完成，等待 Reviewer）
>
> ⚠️ **准确表述（不得夸大）**：
> **真实 Course Data 尚未完成**，**2026-1 全量 snapshot 尚未取得**。
> 本轮完成的是"**已确认字段 → `CourseOffering`**"的**本地标准化内核**与**带 completeness 的内部快照**，
> 是**零网络**实现。

## 阶段状态

```text
D5 教学班技术侦察                                  ✅ 已完成（OFFERING-001，2026-1，CSE202 → 2 个教学班）
Data Gate（契约裁决 + 实施）                        ✅ 已完成（C1–C11 全通过）
Course Data normalization core（本轮）              ✅ 已完成
真实 teachingTimePlaceStr parser                    ⏳ 未实现（缺真实脱敏 Raw string）
授权 import adapter（正常登录 / 已授权范围内导入）    ⏳ 未实现
完整 semester snapshot                              ⏳ 未取得
```

## 已完成

### D5 技术侦察（Phase 2B-0D）
- 记录见 `docs/data/SYSU_COURSE_OFFERING_RECON.md`（`OFFERING-001`）；
- 确认了查询入口的**结构**与一个课程的真实多 segment 现象；
- **Raw 响应、教师姓名、内部长 ID 取值一律不入库**。

### 契约（Data Gate）
- 公共输出为 `schemas/course_offering.schema.json`；
- Data Gate-2（**DG-01**）已把 `CourseOffering` 改为 **1 — N `meetings[]`**：
  一个教学班 = 一个 `CourseOffering`，`meetings[]` = 它的**全部**上课时间 / 地点段。

### Course Data normalization core（Phase 2B-2A，本轮）
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

**周次**：Phase 2B-2A **只接受已经观察到的两个具体取值**（**精确匹配，不做形状泛化**）：

```text
1-17周    ✅
1-17单周  ✅
```

其它一律 `CourseDataNormalizationError` —— 既包括形状不同的形式
（双周 / 逗号组合 / 多段组合 / 单个周次号 / 带"第"字前缀 / 全角数字等），
也包括**形状相似但未被观察过**的区间（`3-4周`、`3-15单周`、`3-3周`、`2-18周` …）。
**"形状相似"不等于"已确认"**；后续 2B-2B 依真实脱敏样本再扩。

> ⛔ **`teachingTimePlaceStr` 本轮不解析**：仓库中**不虚构**任何"看起来像真实 SYSU 格式"的字符串，
> 测试只用不携带格式假设的占位值。`meetings` 只能由调用方传入**已解析好的** `Meeting`。

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
- **尚未暴露任何真实 API**：`/api/v1/mock/*` 仍是独立的永久 Mock 回放通道。

## 当前阻塞

- **真实 `teachingTimePlaceStr` parser 未实现**：public Git 没有真实脱敏 Raw string，
  猜分隔符 / 猜 segment 分隔 / 猜字段位置都属于臆测 → **本轮故意不做**；
- **授权 import adapter 未实现**：尚未有"用户明确触发授权导入"的落地通道；
- **完整 semester snapshot 未取得**：当前只有 D5 小规模侦察（2 个教学班），
  **不是**完整快照；
- ⛔ **`weekDay → weekday` 与 `openingSchoolName → campus` 映射未确认**（C11 待确认项），
  代码中**没有**这类 fallback；
- ⛔ **meeting 级教师关联为 known deferred representation gap**：
  `Meeting` 不承载教师，`teacher` 仍是 `CourseOffering` 顶层汇总 / 展示字段。

## 当前使用数据

- **业务数据仍全部为 Mock**：`/mock_data/course_offerings.json`（人工虚构，`data_source = "mock"`）；
- 本轮的**测试**只使用人工虚构的 source-shaped dict 与占位教师名 `"示例教师A"`；
- 仓库内**不含**真实教师姓名、内部长 ID 取值、`readObj`、Raw JSON、Cookie / Session / Token。

## 下一步

- **真实 `teachingTimePlaceStr` parser**：需先取得**脱敏后的真实 Raw string**，
  再据实实现（不预先猜格式）；
- **授权 import adapter**：用户本人正常登录、已有权限、**用户明确触发**的授权导入；
  批量导入前**必须先确认合理 `pageSize` / 请求规模**，
  只能取得部分范围时**必须显式记录 completeness**，**不得宣称 complete**（C9）；
- **完整 semester snapshot**：目标为 **2026-1**，取得后以 `OfferingSnapshot` 表达，
  并由 `SnapshotCourseDataProvider` 供 Integration 消费；
- ⛔ 这些都属于后续任务书范围，**本轮不得自行开始**。
