/**
 * 专业 / 培养方案接口调用（`/api/v1/majors`、`/api/v1/study-plans/{major_id}`）。
 *
 * ⚠️ 与 `api/caseADemo.ts` 分开：这两个接口**不属于 case-a-demo**，
 *   它们是通用的只读资源，不依赖任何 case 配置（除了专业注册表本身）。
 *
 * ⛔ 失败时**不回退到演示数据**：调用方必须如实展示 503 / 404 / 网络错误。
 */

import { MAJORS_ENDPOINT, STUDY_PLANS_ENDPOINT } from '../config'
import {
  StudyPlanApiError,
  type MajorSummary,
  type StudyPlan,
  type StudyPlanRequirement,
} from '../types/studyPlan'

async function checkedJson<T>(response: Response, hint: string): Promise<T> {
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail
    const code =
      detail && typeof detail === 'object' && 'error' in detail
        ? String((detail as { error?: unknown }).error ?? '') || null
        : null
    const message =
      detail && typeof detail === 'object' && 'message' in detail
        ? String((detail as { message?: unknown }).message ?? '')
        : `${hint}（HTTP ${response.status}）`
    throw new StudyPlanApiError(message, response.status, code)
  }
  return body as T
}

/** 读取可用专业列表。 */
export async function loadMajors(): Promise<MajorSummary[]> {
  let response: Response
  try {
    response = await fetch(MAJORS_ENDPOINT, { headers: { Accept: 'application/json' } })
  } catch {
    throw new StudyPlanApiError('专业列表请求失败：无法连接后端。', null, null)
  }
  const payload = await checkedJson<unknown>(response, '专业列表读取失败')
  if (!Array.isArray(payload)) {
    throw new StudyPlanApiError('专业列表返回格式异常。', response.status, 'invalid_payload')
  }
  return payload as MajorSummary[]
}

/** 读取某专业的培养方案。 */
export async function loadStudyPlan(majorId: string): Promise<StudyPlan> {
  const url = `${STUDY_PLANS_ENDPOINT}/${encodeURIComponent(majorId)}`
  let response: Response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' } })
  } catch {
    throw new StudyPlanApiError('培养方案请求失败：无法连接后端。', null, null)
  }
  const payload = await checkedJson<StudyPlan>(response, '培养方案读取失败')
  const requirements = (payload as StudyPlan).requirements
  if (!Array.isArray(requirements)) {
    throw new StudyPlanApiError('培养方案返回格式异常。', response.status, 'invalid_payload')
  }
  return payload
}

/* -------------------------------------------------------------------------- *
 * 纯派生工具（⛔ 不判定课程等价、⛔ 不算缺口）
 * -------------------------------------------------------------------------- */

/**
 * 从培养方案里取**专业选修池**课程。
 *
 * ⚠️ 选修池是"可以选什么"，⛔ 不是"缺什么"；
 *   是否真的需要选修由后端匹配结果（选修组缺口）决定。
 */
export function electivePoolOf(plan: StudyPlan): readonly StudyPlanRequirement[] {
  return plan.elective_pool.courses
}

/** 必修要求列表。 */
export function requiredOf(plan: StudyPlan): readonly StudyPlanRequirement[] {
  return plan.requirements.filter((item) => item.requirement === 'required')
}

/**
 * 培养方案里**先修关系未知**的条目占比说明。
 *
 * ⚠️ 存在的理由：真实培养方案 docx 没有先修列，因此所有条目的先修都是未知。
 *   这直接解释了"为什么匹配结果全部需要人工确认"，必须如实展示，
 *   ⛔ 不能让用户以为是系统判定错了。
 */
export function prerequisitesNote(plan: StudyPlan): string {
  const unknown = plan.counts.prerequisites_unknown
  const total = plan.counts.total
  if (total === 0) return ''
  if (unknown === 0) {
    return '培养方案已提供全部课程的先修关系。'
  }
  if (unknown === total) {
    return `培养方案未提供先修关系（${unknown}/${total} 门课程的先修未知），因此系统不会自动断定缺课。`
  }
  return `培养方案中有 ${unknown}/${total} 门课程的先修关系未知。`
}
