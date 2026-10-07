import {
  CASE_A_DEMO_OFFERINGS_ENDPOINT,
  CASE_A_DEMO_PLAN_ENDPOINT,
  CASE_A_DEMO_REPAIR_APPLY_ENDPOINT,
} from '../config'
// ⚠️ roadmap / repair 是**前端集成类型**（见 caseAPlanning.ts），⛔ 不是公共契约。
import type { AcademicRoadmap, RepairProposalSet } from '../types/caseAPlanning'
import type { CourseOffering, MakeupTask, PlanResult, Preference } from '../types/contracts'

export interface CaseADemoResponse {
  transcript: {
    source_id: string
    artifact_sha256: string
    record_count: number
    term_count: number
    terms: string[]
    pending_course_id_count: number
  }
  makeup_tasks: MakeupTask[]
  course_offerings: CourseOffering[]
  preference: Preference
  plan_result: PlanResult
  provenance: {
    transcript: string
    curriculum: string
    course_data: string
    current_schedule: string
    planner: string
    is_full_semester: boolean
  }
  /**
   * 当前学期**结构化**换班建议（⛔ 生成 ≠ 应用）。
   *
   * ⛔ 前端不从 `reason` / `unresolved[].message` 里解析任何业务字段：
   * 身份一律取自结构化字段。
   */
  repair_proposals: RepairProposalSet
  /** 未来学期课程级路线图；`null` 表示后端无法构建（⛔ 不补假数据）。 */
  roadmap: AcademicRoadmap | null
  /** `roadmap === null` 时的结构性说明。 */
  roadmap_note: string | null
  /**
   * 上传成绩单与**已确认**已修事实的绑定结果。
   *
   * - `not_bound` —— 上传行没有官方课程号，因此本次**未采用**上传行做满足判定，
   *   培养方案已确认的满足事实原样保留。⛔ 必须向用户**可见地**说明，
   *   否则用户会误以为上传的 PDF 参与了 satisfaction 判定。
   * - `bound` —— 预留取值；当前后端**按设计**不会返回它
   *   （见 `backend/app/services/case_a_demo.py::_completed_binding`：
   *    改写已确认满足事实需要伪造 provenance，因此一律 fail closed）。
   *
   * ⚠️ 前端把除 `bound` 以外的任何取值都当作"未绑定"来**如实展示**，
   * ⛔ 不会因为出现未知取值就静默不提示。
   */
  completed_binding: string
  /** 面向用户的绑定说明（`bound` 时为 `null`）。 */
  completed_binding_note: string | null
}

/** 显式换班的响应：应用后的课表 + 重新计算的建议。 */
export interface CaseADemoRepairApplyResponse {
  status: string
  applied: boolean
  schedule: CourseOffering[]
  changes: { course_id: string; from_class?: string | null; to_class?: string | null; reason: string }[]
  reason: string
  revalidated: boolean
  remaining_conflicts: string[]
  repair_proposals: RepairProposalSet
}

async function checkedJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(`Case A demo request failed (HTTP ${response.status}).`)
  }
  return body as T
}

export async function loadCaseAOfferings(semester: string): Promise<CourseOffering[]> {
  const url = `${CASE_A_DEMO_OFFERINGS_ENDPOINT}?semester=${encodeURIComponent(semester)}`
  return checkedJson<CourseOffering[]>(await fetch(url, { headers: { Accept: 'application/json' } }))
}

async function fileBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  const chunk = 0x8000
  for (let start = 0; start < bytes.length; start += chunk) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunk))
  }
  return btoa(binary)
}

export async function runCaseADemo(input: {
  file: File
  semester: string
  currentSchedule: CourseOffering[]
  manualScheduleAttested: boolean
  preference: Preference
}): Promise<CaseADemoResponse> {
  return checkedJson<CaseADemoResponse>(
    await fetch(CASE_A_DEMO_PLAN_ENDPOINT, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({
        semester: input.semester,
        transcript_pdf_base64: await fileBase64(input.file),
        current_schedule: input.currentSchedule,
        manual_schedule_attested: input.manualScheduleAttested,
        preference: input.preference,
      }),
    }),
  )
}

/**
 * **显式确认**一条换班建议后才调用（⛔ 绝不在生成建议时自动调用）。
 *
 * 必须给出完整身份：`semester` / `course_id` / `from_class_id` / `to_class_id`。
 * 服务端会重新校验（同课程、同学期、`from` 在课表内、`to` 在已接受教学班内、
 * 候选重新确认 CLEAR），任一不成立即拒绝，⛔ 前端不做任何替代判定。
 */
export async function applyCaseARepair(input: {
  semester: string
  courseId: string
  fromClassId: string
  toClassId: string
  currentSchedule: CourseOffering[]
  manualScheduleAttested: boolean
}): Promise<CaseADemoRepairApplyResponse> {
  return checkedJson<CaseADemoRepairApplyResponse>(
    await fetch(CASE_A_DEMO_REPAIR_APPLY_ENDPOINT, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({
        semester: input.semester,
        course_id: input.courseId,
        from_class_id: input.fromClassId,
        to_class_id: input.toClassId,
        current_schedule: input.currentSchedule,
        manual_schedule_attested: input.manualScheduleAttested,
      }),
    }),
  )
}
