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

### 4.0 学期号映射（⛔ 关键，不得回退）

`recommended_semester` / `deadline_semester` 是**培养方案相对学期号**
（某专业第 3 学期 = `2026-1`），**不是**本次未来学期列表里的第几项。
因此调用方必须**显式**给出映射，三种形式皆可：

```python
# ① 映射（推荐）
semesters={"2026-2": 4, "2027-1": 5, "2027-2": 6}

# ② 显式对象
semesters=[FutureSemester("2026-2", 4, 1), FutureSemester("2027-1", 5, 2)]

# ③ 纯标签 + 显式起始学期号
semesters=("2026-2", "2027-1", "2027-2"), from_curriculum_semester=4
```

```text
当前真实学期 2026-1 == 培养方案第 3 学期
未来：2026-2 -> 4   2027-1 -> 5   2027-2 -> 6

recommended_semester = 4  ⇒  2026-2（第一个未来学期）
                            ⛔ 不是"列表第 4 项"
```

- ⛔ **不存在"未来学期一律从 1 重新编号"** 的隐式语义；
- ⛔ 只给学期标签而不给映射 ⇒ **fail closed**；
- ⛔ 同时给出映射与 `from_curriculum_semester`（两套编号来源）⇒ 拒绝；
- 先修先后按**培养方案学期号**（同一条时间轴）判断，列表顺序不影响结论。

### 4.0.1 已满足事实的来源（⛔ 不得只依赖原始 `course_id`）

真实成绩单 PDF **不提供官方课程号**，因此已满足事实主要由 Curriculum 层给出：

```text
confirmed_satisfied_course_ids   ← Curriculum 已确认满足的目标课程号
makeup_tasks                     ← 只采纳 status == "satisfied"
completed                        ← 次要来源（原始已修事实，course_id 可为 None）
```

- ⛔ 本模块**不做任何识别**：不按课程名匹配、不从成绩单推断、不做等价判定；
- ⛔ `manual_confirmation` / `possibly_equivalent` **绝不**被提升为"已满足"
  （会被列入 `warnings` 并按"未满足"处理）；
- ⛔ `course_id=None`（pending）的已修记录**不得**被当成已满足；
- 已满足的课程**绝不**再出现在 `future_course_ids` 中。

### 4.0.2 选修学分账（含本学期）

```text
elective_requirement_credit        读自 CurriculumGroup.minimum_credit（⛔ 无硬编码）
− elective_completed_credit        已确认完成的选修学分
− elective_current_semester_credit 本学期已确认的选修学分（必须归属该组）
= 规划前缺口
        ↓ 只选"装得进缺口"的课程（⛔ 不超额规划）
elective_planned_credit + elective_remaining_credit = 规划前缺口
```

- 只有**确认**归属该选修组的本学期课程才计入；证据不足 ⇒ `0.0` + `unresolved`；
- 不属于该组的课程声明 ⇒ ⛔ 不计入，并如实报告；
- 已计入"已完成学分"的课程**不会**再被规划一次。

### 4.1 输出模型

```text
AcademicRoadmap
  current_semester                       当前学期标签（由 RestrictedPlanner 负责）
  current_semester_planned_course_ids    已确认的当前学期课程（摘要，⛔ 不重排）
  future_semesters: SemesterPlan[]
  elective_requirement_credit            选修组最低学分（读自 CurriculumGroup）
  elective_completed_credit              已确认完成的选修学分（证据不足则 null）
  elective_current_semester_credit       本学期已确认的选修学分
  elective_planned_credit                本次规划的选修学分
  elective_remaining_credit              规划**之后**仍缺学分（证据不足则 null）
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
4. recommended_semester 是**排课偏好**：优先建议学期；没有可行的建议学期时
   退到**截止学期**（在截止前完成即可）；两者都没有才用最早可行学期
5. per_semester_credit_budget 生效；缺省则不设上限并在 warnings 中如实说明
6. 选修学分按 group 最低学分**补足即止**（⛔ 不超额规划）
7. ⛔ 不编造先修；先修不在方案事实中 ⇒ 报 unresolved
8. ⛔ 不用本学期开课情况推断未来是否有教学班
```

⛔ 学期号一律按 `curriculum_semester` 比较（见 §4.0），
⛔ 不按未来学期列表位置比较。

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

`backend/tests/test_path_planner_core.py`（**51 项**）覆盖：

- 换班：单/多候选、生成不改课表、非法选择拒绝、显式选择才应用、
  换课程/跨学期拒绝、应用后重新校验、同班选择为 no-op、重复 identity 拒绝；
- 路线图：必修落位、先修顺序、截止学期、建议学期作为偏好、学分预算、
  选修最低学分（读自 group，非硬编码）、选修池非全必修、证据不足 unresolved、
  group 未知、未来输出无 section/teacher/时间地点字段、不 import Course Data、
  当前学期仅作摘要、deadline 越界不猜、先修环、缺失先修不编造、确定性；
- **培养方案学期号映射**：显式映射三形态、`recommended` 按学期号命中、
  乱序标签不影响先修先后、缺映射 fail closed、双编号来源冲突拒绝、重复学期号拒绝；
- **已确认满足事实**：`confirmed_satisfied_course_ids`、
  `MakeupTask.status == satisfied` 才算满足、`manual_confirmation` /
  `possibly_equivalent` 绝不提升、`course_id=None` 的 pending 记录不算满足、
  已满足课程绝不再规划；
- **选修学分账**：本学期已确认选修学分计入、证据不足计 0 并报 unresolved、
  组外课程不计入、**不超额规划**、账目恒等式
  `requirement − completed − current == planned + remaining`。

`backend/tests/test_case_a_roadmap.py`（18 项）覆盖 Case A 的接线层：
学期号链推导、未来学期起点/上界、单学期与区间文本解析、
区间无裁决时不猜方向、historical 区间既不规划也不误报、
选修最低学分随培养方案变化（⛔ 无硬编码）、组外 satisfied 不计入选修学分、
未知选修组 fail closed。

`backend/tests/test_case_a_demo_e2e.py` 覆盖 API 层：
路线图字段恒存在（不可构建时 `roadmap=null` + 结构性说明）、
未来学期无任何教学班字段、修复接口需要完整身份、跨课程替换被拒且不改课表。
