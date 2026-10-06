import { CASE_A_DEMO_OFFERINGS_ENDPOINT, CASE_A_DEMO_PLAN_ENDPOINT } from '../config'
// ⚠️ roadmap 是**前端集成类型**（见 caseAPlanning.ts），⛔ 不是公共契约。
import type { FutureRoadmap } from '../types/caseAPlanning'
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
   * 未来学期修读路径（**可选**）。
   *
   * ⚠️ 后端当前**不返回**该字段。前端只在它真的存在且含学期数据时渲染，
   * ⛔ 缺省时整块不渲染、⛔ 不补任何假数据。
   */
  roadmap?: FutureRoadmap | null
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
