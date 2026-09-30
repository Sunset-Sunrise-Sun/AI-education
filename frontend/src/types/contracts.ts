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

/** 对应 `course_offering.schema.json`。 */
export interface CourseOffering {
  course_id: string
  course_name: string
  class_id: string
  semester: string
  teacher?: string | null
  credit?: number | null
  weekday: number
  start_section: number
  end_section: number
  weeks: number[]
  campus?: string | null
  classroom?: string | null
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
