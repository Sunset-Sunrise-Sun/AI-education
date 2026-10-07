/**
 * Case A 前端集成类型 —— **加法式 / 前端侧类型，不是公共后端契约**。
 *
 * 重要边界：
 *
 * - ⛔ 本文件的类型**不在** `/schemas/` 中，**不是** frozen public backend contract；
 * - 它们与 `POST /api/v1/case-a-demo/plan` 的**加法式**响应字段一一对应
 *   （见 `backend/app/api/case_a_demo.py`）；
 * - 因此这些类型刻意**不放进** `types/contracts.ts`（那个文件与 `/schemas/*.schema.json`
 *   手工一一对齐，只登记**已存在**的公共对象）；
 * - 一旦该结构成为公共契约，应先在 `/schemas/` 中定义，并把它**移回** `contracts.ts`；
 * - ⛔ 前端不使用这些类型推导任何业务结论，也不在缺数据时补造数据。
 *
 * ⚠️ 字段名沿用后端响应原样（`snake_case`），与 `contracts.ts` 的处理方式一致。
 */

/**
 * 未来学期修读路径中的**一门课**（课程级）。
 *
 * ⚠️ 未来学期只做课程级规划，因此本类型刻意**不含** `class_id` / `teacher` /
 * `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom` /
 * `capacity` / `remaining_capacity` / `meetings`：
 * 具体教学班需以届时教务系统实际开课为准。
 */
export interface RoadmapCourse {
  course_id: string
  course_name: string
  credit: number
  requirement_kind: string
  requirement_label: string
  placement: string
  reason: string
}

/** 未来某一个学期的课程级修读路径。 */
export interface RoadmapSemester {
  semester_label: string
  /** 该学期在培养方案中的学期号（⛔ 不是"列表第几项"）。 */
  curriculum_semester: number
  /** 该学期在本次未来学期序列中的位置（从 1 开始，仅用于先后）。 */
  semester_index: number
  courses: RoadmapCourse[]
  required_credit: number
  elective_credit: number
  total_credit: number
  warnings: string[]
}

/**
 * 选修学分进度。
 *
 * 恒等式（后端保证）：`requirement − completed − current
 * = planned + remaining`；`gap_credit` 是**规划前**的缺口。
 */
export interface ElectiveAccounting {
  requirement_credit: number | null
  completed_credit: number | null
  current_semester_credit: number
  planned_credit: number
  remaining_credit: number | null
  gap_credit: number | null
  group_id: string | null
}

/** 未来学期课程级路线图（后端`satisfied only` 事实推导）。 */
export interface AcademicRoadmap {
  current_semester: string | null
  current_semester_planned_course_ids: string[]
  future_semesters: RoadmapSemester[]
  elective: ElectiveAccounting
  unresolved: string[]
  warnings: string[]
}

/**
 * 一条**待用户确认**的同课程换班建议。
 *
 * ⚠️ 只携带 identity 与判定结果：⛔ 不含课程名 / 教师 / 时间地点。
 * 前端用 `(semester, course_id, candidate_class_id)` 自行与 `CourseOffering[]` join。
 * ⛔ **生成 ≠ 应用**：只有用户显式点击"采用调整"并调用 repair apply 才会生效。
 */
export interface RepairProposal {
  proposal_id: string
  semester: string
  course_id: string
  current_class_id: string
  candidate_class_id: string
  /** `CONFLICT` / `UNKNOWN`（原班状态；UNKNOWN = 排课信息待核验）。 */
  original_state: string
  /** 候选状态；只有 `CLEAR` 的候选才会出现在建议里。 */
  candidate_state: string
  reason: string
}

/** 换班建议集合（含"N 个教学班无法给出建议"的结构化说明）。 */
export interface RepairProposalSet {
  semester: string
  proposals: RepairProposal[]
  unresolved: string[]
}
