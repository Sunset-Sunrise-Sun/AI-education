# Planner 模块接口

> ⚠️ **本文件的职责划分以 `/AGENTS.md` 第 5 节为最高依据。**
> Data Gate-2（**DG-06**）已修正本文件此前与 `/AGENTS.md` 第 5 节冲突的描述：
> 「课程依赖图」「补修优先级与风险」**属 Curriculum**，Planner 只是**消费方**。

## 职责

回答：**在现实约束下，这些课怎么排进去？**

本模块负责：

- 时间 / 节次 / 周次**冲突检测**；
- **当前课表冲突分析**；
- **替代教学班搜索**；
- 硬约束 / 软约束建模；
- 确定性约束求解；
- **Path Repair**；
- 无解 / 部分可行处理；
- `PlanResult` 生成。

本模块**不负责**（这些属于 Curriculum / 学业路径模块）：

- **认定课程依赖 / 先修关系**；
- **生成补修风险**；
- **生成学业优先级**；
- **Curriculum Diff**（新旧培养方案差异分析）。

## 对外输入

来自 Curriculum：

- `MakeupTask[]`（其中 `prerequisites[]` 是**由 Curriculum 认定的**先修边）

来自 Course Data：

- `CourseOffering[]`

来自用户：

- `current_schedule: CourseOffering[]`
- `Preference`

### `current_schedule` 的准确语义（Data Gate-1 / DG-03）

```text
CourseOffering[]                     —— 学校**全部供给**（Course Data 输出）
current_schedule: CourseOffering[]   —— 学生**已经选择**的教学班子集
```

两者**类型相同、语义不同**，**不得混用**：

- 冲突检测的一侧是 `current_schedule`（学生已选），
  **不是**学校开设的全部教学班；
- 若把"学校开设的全部教学班"当成"学生当前课表"，冲突检测会**完全失真**；
- ⛔ **不允许**用 `Preference.avoid_times[]` 冒充当前课表 ——
  `avoid_times` 表达的是**偏好上的回避**，不是"已经选中了哪些课"这一事实。

> 说明：DG-03 的裁决是**复用现有公共类型**，不新增 `CurrentEnrollment` Schema。

## 课程依赖与优先级：权威边界（Data Gate-1 / DG-05）

```text
Curriculum：
  负责认定 prerequisite edges（先修关系）

Planner：
  可以把已经收到的 MakeupTask.prerequisites[]
  转换成本地 adjacency / topological representation
  供确定性求解使用

Planner：
  不得新增、猜测、重写任何 prerequisite edge
```

具体含义：

| 角色 | 允许 | 不允许 |
|---|---|---|
| **Curriculum** | **认定**先修关系，产出 `prerequisites[]` | —— |
| **Planner** | 把**已经收到的** `prerequisites[]` 构造成求解所需的**本地**邻接 / 拓扑表示 | **新增 / 猜测 / 重写**任何 prerequisite edge |
| **Planner** | 在本地表示上做确定性图计算（邻接查询、拓扑序、闭包） | 自行认定"哪门课应当是先修" —— 那是**学业规则**，属 Curriculum |
| **任何人** | 真实来源无法提供 prerequisite 时，标记 **未知 / 待人工确认** | **自动补齐**，或用推断填补缺失的先修关系 |

**关于 `priority`（MVP 现状）**：

- **当前不存在公共 `priority` 字段**，也不存在 `PriorityResult` 或任何等效对象
  （DG-05 裁决：MVP 不新增）；
- ⛔ **没有正式 priority 数据时，Planner 不得自行生成优先级** ——
  不得用启发式打分、LLM 判断或自定义排序替代 Curriculum 的学业优先级；
- 后续 Curriculum 真正实现明确的优先级规则时，再走 `【接口变更请求】`。

## 对外输出

必须符合：

- `schemas/plan_result.schema.json`

建议接口：

```text
check_conflict(offering_a, offering_b)
find_alternative_sections(course_id, offerings, current_schedule)
optimize_path(makeup_tasks, offerings, current_schedule, preferences) -> PlanResult
```

> ⚠️ 已删除原 `build_dependency_graph(courses)` 与 `calculate_priority(makeup_tasks, context)`：
> 它们把 **Curriculum 的职责**写成了 Planner 的对外接口，与 `/AGENTS.md` 第 5 节直接冲突。
> 依赖与优先级现在只作为**输入**消费（见上一节）。

## 实现约束

- 时间冲突、学分计算、先修关系等确定性逻辑不得交给 LLM 判断；
- **冲突检测必须按状态分别处理（DG-07A 契约语义）**：

  | `CourseOffering.meetings` | 语义 | Planner 必须做什么 |
  |---|---|---|
  | **非空** | 来源提供了可用排课信息 | **遍历全部 `Meeting`**，逐段比较时间占用 |
  | **`[]`** | **schedule unknown**（当前来源快照没有可用排课信息） | ⛔ **绝不能**解释为"没有时间占用"；⛔ **绝不能**解释为 **conflict-free** |

  - Data Gate-2（DG-01）后，一个教学班可有**多个**上课时间 / 地点段，
    只看第一段会**漏检冲突**并输出**不可执行的方案**；
    任何"这个教学班占用了哪些时间"的判断都必须基于全部 meeting；
  - ⚠️ **同一条规则同时适用于 `offerings` 与 `current_schedule`**
    （两者都是公共类型 `CourseOffering[]`）：
    **任意 `CourseOffering.meetings = []` → 该教学班的 schedule 视为 unknown**；
  - ⛔ **若 `current_schedule` 中存在 `meetings = []`**：
    Planner **不得**输出"**已验证与当前课表无时间冲突**"这类结论 ——
    因为"当前课表"本身有一段**时间占用未知**；
    最多只能判断"**与当前课表中已知时间段未发现冲突**"，
    且**整体时间冲突状态仍含未知部分**（必须显式表达为未知 / 待人工确认）；
- **DG-07C 已实现并完成项目 Architecture Review 的代码审查**：Planner 内部正式使用
  `CONFLICT / UNKNOWN / CLEAR` 三态，安全优先级为 **CONFLICT > UNKNOWN > CLEAR**。
  已发现确定冲突时返回 `CONFLICT`；没有已知冲突但任意相关教学班 schedule unknown
  时返回 `UNKNOWN`；只有相关 schedule 全部已知并遍历全部 `Meeting` 后无冲突，
  才能返回 `CLEAR`。
- **DG-07C 正式采用的 `unresolved[].type` 运行语义**（公共 Schema 仍保持开放字符串，
  不新增 enum）：
  - `schedule_unknown`：当前来源快照没有足够的可用排课信息，无法完成完整时间冲突认证。
    ⛔ 不表示学校尚未排课、异步课程、无课、无时间占用或 conflict-free。
  - `selection_required`：存在需要调用方 / 用户明确选择的 CLEAR 候选；
    Planner 不自动代替用户作决定，例如多个 CLEAR 教学班或已有班存在明确可替换方案。
  - `missing_data`：当前输入数据不足以完成判断；⛔ 不表示学校没有开课，也不构成无解证明。
  - `manual_confirmation`：涉及尚未冻结的非时间业务规则、课程认定、先修证明、
    相对学期映射等，需要人工确认；未确认规则不据此筛班、评分或证明无解。
- **历史沿革**：DG-07A 阶段 `missing_schedule` 曾作为 `candidate convention only`；
  DG-07C Implementation Review 后正式采用 `schedule_unknown`，前者不再作为当前 Planner 输出约定。
- **`PlanResult.status` 当前语义**：
  - `feasible`：影响当前建议方案成立的确定性条件已经认证，且不存在影响该方案成立的 unresolved；
    不代表学校已经替学生选课成功。
  - `partially_feasible`：存在 schedule unknown、人工决策、输入不足或尚未完成认证的条件，
    但当前证据不能证明完整目标无解。
  - `infeasible`：仅在当前明确目标、当前输入域和已确认硬约束范围内，
    Planner 已完成必要搜索 / 证明并确认没有可行组合；不表示学校所有真实教学班、
    所有未来学期均无解，也不表示信息缺失。
  - 总体不变量：**UNKNOWN != INFEASIBLE**。
- 优化器第一版可继续评估 Google OR-Tools CP-SAT；图关系可评估 NetworkX，
  但当前受限 Provider 不因这些建议而宣称已实现完整 Planner MVP。

## 人工确认边界

以下内容需人工确认后才能作为规则写死：

- 跨校区最小通勤时间；
- 硬约束 / 软约束定义；
- 特殊培养政策。

> **补修优先级权重不在本模块的确认范围内** —— 它属于 Curriculum 的学业规则。
