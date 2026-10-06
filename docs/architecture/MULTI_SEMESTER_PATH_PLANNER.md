# 多学期学业路径规划（Multi-Semester Path Planner）

> 状态：**Phase 1 已实现**（分支 `feature/path-planner-core`）。
> 位置：`backend/app/path_planner/`。
> ⛔ 本模块**不改**任何冻结契约：`PlannerProvider` 四参数签名、
> `CourseOffering` / `Meeting` / `Preference` / `PlanResult` 公共 Schema 一律未动。

## 0. 一句话规则（本文件的核心）

```text
当前学期 = 教学班级（section-level）规划
未来学期 = 培养方案课程级（course-level）规划
```

这两件事**必须分开**：当前学期有真实教学班数据，未来学期**没有**、也**不允许预测**。

## 1. 为什么这样切分

教务系统**只提供本学期真实开课信息**。未来学期我们能依赖的事实只有培养方案：

```text
每学期开设 / 建议课程
+ 课程学分
+ 培养要求（必修 / 选修 / 先修 / 截止学期）
```

因此未来学期**不可能**知道教学班号、任课教师、上课时间、校区、教室、容量。
把它们编出来就是伪造数据。所以：

> **不需要任何未来 Course Data 采集。**
> ⛔ 不新增校区抓取、⛔ 不扩展 Course Data、⛔ 不预测未来课表。

## 2. 两条路径与各自的输入

```text
                       ┌───────────────────────────────────────────────┐
 当前学期              │ RestrictedPlanner + 真实 CourseOffering          │
 (section-level)       │ 输入：makeup_tasks / offerings / current_schedule │
                       │       / preference                              │
                       │ 输出：PlanResult（建议课表 / changes / risks …）  │
                       └───────────────────────────────────────────────┘
                                        │ 确认后的当前学期课程摘要
                                        ▼
                       ┌───────────────────────────────────────────────┐
 未来学期              │ app.path_planner.future_roadmap                 │
 (course-level)        │ 输入：CurriculumVersion / CompletedCourse[]      │
                       │       / 当前学期课程摘要 / 学期序列 / 学分预算     │
                       │ 输出：AcademicRoadmap                            │
                       └───────────────────────────────────────────────┘
```

⛔ 未来规划器**不**重新决定当前学期选哪些教学班 —— 那是 `RestrictedPlanner` 的职责；
它只把"当前学期已经规划好的课"当作**摘要输入**，避免重复安排。

## 3. 当前学期：换班**建议**，不是自动换班

位置：`app/path_planner/repair_proposals.py`

```text
current_schedule + offerings
        ↓ generate_repair_proposals()      只读；⛔ 不动课表
RepairProposalSet（每条只含 identity +ConflictState + reason）
        ↓ 调用方 / 用户**显式选择**一条
apply_repair_proposal(...)                 校验 + 重新评估 + 应用
        ↓
RepairApplicationResult（新 schedule + changes + 重校验）
```

- ⛔ **生成 ≠ 应用**：`generate_*` 永远不替调用方挑候选；
- ⛔ 不重复实现冲突判定：复用 `planner.section_repair` / `planner.conflicts` 的既有原语；
- 建议里**不复制** `CourseOffering` 取值（只给 identity），前端自行 join；
- 显式选择必须完整给出 `(semester, course_id, from_class_id, to_class_id)`，任一不成立即拒绝；
- 应用后按新课表**重新**做内部冲突复核，残留冲突如实列出（⛔ 不伪装成"已验证无冲突"）。

### 与 DG-07（`meetings = []`）的关系

`meetings = []` = **当前来源快照没有可用排课信息**（schedule UNKNOWN），
⛔ **不表示无冲突**。因此 UNKNOWN 与"已确认冲突"在建议里**分开**表达
（`original_state`），也⛔ 不因 UNKNOWN 就自动换班。

### 当前课表保留策略

"哪门课能动"目前**没有**公共字段，本轮**不新增**。
设计提案见 [CURRENT_SCHEDULE_RETENTION_POLICY.md](./CURRENT_SCHEDULE_RETENTION_POLICY.md)；
在它被批准之前，运行时保持既有行为：**当前课表课程一律保留**，直到用户显式确认换班。

## 4. 未来学期：课程级路线图

位置：`app/path_planner/future_roadmap.py`

### 4.1 输出模型

```text
AcademicRoadmap
  current_semester                       当前学期标签（由 RestrictedPlanner 负责）
  current_semester_planned_course_ids    已确认的当前学期课程（摘要，⛔ 不重排）
  future_semesters: SemesterPlan[]
  elective_requirement_credit            选修组最低学分（读自 CurriculumGroup）
  elective_completed_credit              已确认完成的选修学分（证据不足则 null）
  elective_planned_credit                本次规划的选修学分
  elective_remaining_credit              仍缺学分（证据不足则 null）
  unresolved[] / warnings[]              如实报告，⛔ 不猜测

SemesterPlan
  semester_index / semester_label
  courses: SemesterCoursePlan[]
  required_credit / elective_credit / total_credit
  warnings[]

SemesterCoursePlan                 ← ⛔ 字段集刻意最小
  course_id / course_name / credit / requirement_kind / reason / placement
```

⛔ `SemesterCoursePlan` **没有** `class_id` / `teacher` / `weekday` /
`start_section` / `end_section` / `weeks` / `campus` / `classroom` /
`capacity` / `meetings`：未来学期不允许输出教学班级信息，这是**结构上的保证**，
有专门测试锁定（字段集 + AST import 检查）。

### 4.2 确定性放置策略

```text
1. 必修课优先于选修填充
2. 先修顺序：拓扑序（同层按 deadline → recommended → course_id），⛔ 不破环、不猜环
3. deadline_semester 是**硬约束**（宁可留 unresolved，⛔ 也不违反）
4. recommended_semester 是**排课偏好**（可被先修 / 预算推迟）
5. per_semester_credit_budget 生效；缺省则不设上限并在 warnings 中如实说明
6. 选修学分按 group 最低学分**补足即止**
7. ⛔ 不编造先修；先修不在方案事实中 ⇒ 报 unresolved
8. ⛔ 不用本学期开课情况推断未来是否有教学班
```

⛔ 这里**不是** CP-SAT / ILP 全局最优求解，也⛔ 没有评分权重：
它是一条**确定性启发式**，只保证上述约束与可复现性。

### 4.3 选修学分规划

```text
CurriculumGroup.minimum_credit        ← 唯一真源（⛔ 算法内无硬编码学分）
- 已确认完成的选修学分（调用方显式提供课程号）
= 仍需补足的选修学分
```

- ⛔ **不**把选修池里每门课都当必修：只为满足最低学分**选够**学分即停止；
- 调用方**未**确认"哪些已修课程归属该组" ⇒ 证据不足 ⇒
  `elective_completed_credit = null`、不规划选修、写入 `unresolved`（⛔ 不猜测）；
- `minimum_credit` 在方案中未知 ⇒ 同样进 `unresolved`；
- 培养方案成员不足以补足 ⇒ 如实报告缺口（⛔ 不编造课程）。

## 5. 扩展层如何与冻结契约共存

```text
冻结契约（未改）                 Phase 1 新增（内部 / 加法）
─────────────────────────       ─────────────────────────────────────
PlannerProvider.plan(...)   ←→  path_planner 编排层调用它，不改签名
PlanResult                  ←→  保持不变；路线图是**独立**输出模型
CourseOffering / Meeting    ←→  未来学期完全不产生它们
Preference                  ←→  未新增任何字段
```

⛔ 路线图模型**没有**加进 `/schemas/`。如果将来要把它作为对外接口，
必须走独立的《接口变更请求》并获 Architecture Lead 批准。

## 6. 测试锚点

`backend/tests/test_path_planner_core.py`（33 项）覆盖：

- 换班：单/多候选、生成不改课表、非法选择拒绝、显式选择才应用、
  换课程/跨学期拒绝、应用后重新校验、同班选择为 no-op、重复 identity 拒绝；
- 路线图：必修落位、先修顺序、截止学期、建议学期作为偏好、学分预算、
  选修最低学分（读自 group，非硬编码）、选修池非全必修、证据不足 unresolved、
  group 未知、未来输出无 section/teacher/时间地点字段、不 import Course Data、
  当前学期仅作摘要、deadline 越界不猜、先修环、缺失先修不编造、确定性。
