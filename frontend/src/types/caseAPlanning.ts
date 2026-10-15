/**
 * Case A 前端集成类型 —— **加法式 / 前端侧类型，不是公共后端契约**。
 *
 * 重要边界：
 *
 * - ⛔ 本文件的类型**不在** `/schemas/` 中，**不是** frozen public backend contract；
 * - ⛔ 后端目前**不返回**这些字段；它们只是让前端在 Builder B 的契约落地后能直接接线；
 * - 因此这些类型刻意**不放进** `types/contracts.ts`（那个文件与 `/schemas/*.schema.json`
 *   手工一一对齐，只登记**已存在**的公共对象）；
 * - 一旦该结构成为公共契约，应先在 `/schemas/` 中定义，并把它**移回** `contracts.ts`；
 * - ⛔ 前端不使用这些类型推导任何业务结论，也不在缺数据时补造数据。
 */

/**
 * 未来学期修读路径中的**一门课**（课程级）。
 *
 * ⚠️ 未来学期只做课程级规划，因此本类型刻意**不含** `class_id` / `teacher` /
 * `weekday` / `section` / `classroom` / `capacity`：
 * 具体教学班需以届时教务系统实际开课为准。
 */
export interface FutureRoadmapCourse {
  course_id: string
  course_name: string
  credit?: number | null
}

/** 未来某一个学期的课程级修读路径。 */
export interface FutureRoadmapSemester {
  semester: string
  required?: FutureRoadmapCourse[]
  makeup?: FutureRoadmapCourse[]
  /**
   * **培养要求待覆盖**的课程。
   *
   * ⚠️ 语义（严格）：培养方案要求存在，但当前成绩单 / 课表 / 匹配结果
   *   **不足以判断是否需要补修**。⛔ 不代表系统已判断缺课，
   *   因此⛔ 不能与 `required`（后端明确判定缺口）混为一谈。
   */
  pendingCoverage?: FutureRoadmapCourse[]
  elective?: FutureRoadmapCourse[]
  expected_credit?: number | null
  /**
   * 该学期的**完成目标**（Phase 7 任务 2）。
   *
   * ⚠️ 由前端按"本学期条目 + 培养方案剩余要求"确定性派生（见 `utils/futureRoadmap.ts`），
   *   ⛔ 不是学校的学期考核要求，页面必须配合免责说明展示。
   */
  completion_goals?: string[]
}

/**
 * `POST /api/v1/case-a-demo/plan` 响应中**可选**的 roadmap 字段。
 *
 * ⛔ 字段缺失时前端整块不渲染（不显示占位假数据）。
 */
export interface FutureRoadmap {
  semesters: FutureRoadmapSemester[]
}
