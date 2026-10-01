/**
 * 与仓库 `/schemas/*.schema.json` **手工对齐**的 TypeScript 类型。
 *
 * 重要边界：
 * - 契约真源永远是 `/schemas/*.schema.json`，不是本文件；本文件只用于让前端读代码时有类型提示。
 * - 本文件**不新增、不修改、不删除**任何字段。若认为 Schema 不够用，应先提出【接口变更请求】。
 * - 前端不使用这些类型推导任何业务结论：不做课程等价判定、不做冲突检测、不改写 Planner 结果。
 * - `Course` 对象不在本轮 `/api/v1/mock/demo` 的返回中，因此这里不定义，避免定义一份用不到的类型。
 */

/** `course_offering.schema.json` 中的 `data_source` 取值。 */
export type DataSource = 'mock' | 'real'

/** `makeup_task.schema.json` 中的 `status` 取值。 */
export type MakeupStatus =
  | 'required'
  | 'possibly_equivalent'
  | 'manual_confirmation'
  | 'satisfied'

/** `plan_result.schema.json` 中的 `status` 取值。 */
export type PlanStatus = 'feasible' | 'partially_feasible' | 'infeasible'

/** `plan_result.schema.json` 中 `risks[].level` 的取值。 */
export type RiskLevel = 'low' | 'medium' | 'high'

/** 对应 `makeup_task.schema.json`。 */
export interface MakeupTask {
  course_id: string
  course_name: string
  credit: number
  status: MakeupStatus
  deadline_semester?: number | null
  recommended_semester?: number | null
  prerequisites?: string[]
  reason?: string | null
  source_evidence?: string | null
}

/**
 * 对应 `course_offering.schema.json` 中 `meetings[]` 的元素：**一段**上课时间 / 地点。
 *
 * Data Gate-2（DG-01）后，一个教学班可以有多个独立的上课时间 / 地点段
 * （**`CourseOffering` 1 → 0..N `Meeting`**：每个 `CourseOffering` 可以包含 0 个或多个
 * `Meeting`；DG-07A 起允许 0 段），因此排课信息不再挂在教学班顶层。
 *
 * ⚠️ 这里**没有** `teacher`：meeting 级教师关联是已登记的
 * known deferred representation gap，本轮不进入公共契约。
 */
export interface Meeting {
  weekday: number
  start_section: number
  end_section: number
  weeks: number[]
  campus?: string | null
  classroom?: string | null
}

/**
 * 对应 `course_offering.schema.json`。
 *
 * `meetings` 的公共表示允许 **0..N** 个 `Meeting`（DG-07A 起 `minItems: 0`）：
 * - 非空 → 来源提供了可用排课信息；
 * - `[]` → **仅**表示当前来源快照没有能够形成公共 `Meeting` 的可用排课信息；
 *   ⛔ 不表示没有上课时间、异步教学、时间自由，**更不表示没有时间冲突**。
 *
 * ⚠️ 契约层允许空数组 ≠ 产品链路可以产生：前端 empty-meeting 展示属 DG-07D，
 * 在 DG-07B / DG-07C / DG-07D 完成前，界面不应收到 `meetings = []` 的数据
 * （rollout gate，见 `docs/status/agent_frontend.md`）。
 */
export interface CourseOffering {
  course_id: string
  course_name: string
  class_id: string
  semester: string
  teacher?: string | null
  credit?: number | null
  meetings: Meeting[]
  capacity?: number | null
  remaining_capacity?: number | null
  source?: string | null
  data_source: DataSource
}

/** 对应 `preference.schema.json` 中 `avoid_times[]` 的元素。 */
export interface AvoidTime {
  weekday: number
  start_section: number
  end_section: number
}

/** 对应 `preference.schema.json`。所有字段都是可选的。 */
export interface Preference {
  max_credit?: number | null
  avoid_cross_campus?: boolean
  preferred_courses?: string[]
  avoid_times?: AvoidTime[]
  notes?: string | null
}

/** 对应 `plan_result.schema.json` 中 `selected_classes[]` 的元素。 */
export interface SelectedClass {
  course_id: string
  class_id: string
}

/** 对应 `plan_result.schema.json` 中 `changes[]` 的元素。 */
export interface PlanChange {
  course_id: string
  from_class?: string | null
  to_class?: string | null
  reason: string
}

/** 对应 `plan_result.schema.json` 中 `risks[]` 的元素。 */
export interface PlanRisk {
  course_id?: string | null
  level: RiskLevel
  reason: string
}

/** 对应 `plan_result.schema.json` 中 `unresolved[]` 的元素。 */
export interface PlanUnresolved {
  type: string
  message: string
}

/** 对应 `plan_result.schema.json`。 */
export interface PlanResult {
  status: PlanStatus
  selected_classes: SelectedClass[]
  changes: PlanChange[]
  risks: PlanRisk[]
  unresolved: PlanUnresolved[]
  objective_summary?: string | null
}

/** `GET /api/v1/mock/demo` 的响应体：四类公共对象的聚合。 */
export interface DemoPayload {
  makeup_tasks: MakeupTask[]
  course_offerings: CourseOffering[]
  preference: Preference
  plan_result: PlanResult
}
