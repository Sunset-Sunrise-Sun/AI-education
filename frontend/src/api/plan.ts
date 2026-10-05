/**
 * 目标 Real 接口 `POST /api/v1/plan` 的客户端。
 *
 * 边界（本轮的硬要求）：
 * - 请求体**只有** `semester` / `current_schedule` / `preference` 三个字段；
 * - 响应按公共 `PlanResult` 处理，严格符合 `schemas/plan_result.schema.json`；
 * - ⛔ **绝不 fallback 到 `/api/v1/mock/demo`**：
 *   这个文件不 import 任何 Mock 通道代码，失败时只如实抛出错误；
 * - 本轮**不解析 XLSX、不做 Curriculum Diff、不做课程等价判定、不做冲突求解**：
 *   它只是把用户已经录入的输入交给后端。
 */

import { PLAN_ENDPOINT } from '../config'
import type { CourseOffering, PlanResult, Preference } from '../types/contracts'

/** Real Planning 请求体；字段与后端约定一一对应，不含任何额外键。 */
export interface RealPlanRequest {
  semester: string
  current_schedule: CourseOffering[]
  preference: Preference
}

/** 请求失败时抛出的错误；消息面向非专业用户，不含堆栈或敏感信息。 */
export class PlanApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'PlanApiError'
  }
}

/** Real Planning 尚未接入时抛出的错误（**不会**回退到 Mock）。 */
export class PlanApiUnavailableError extends PlanApiError {
  constructor(message: string) {
    super(message)
    this.name = 'PlanApiUnavailableError'
  }
}

/**
 * 调用 Real Planning 接口。
 *
 * 只做三件事：发请求、判断 HTTP 状态、把 JSON 原样返回。
 * 不做数据加工、不补默认值、失败时**不返回兜底方案**。
 */
export async function fetchRealPlan(
  request: RealPlanRequest,
  signal?: AbortSignal,
): Promise<PlanResult> {
  let response: Response

  try {
    response = await fetch(PLAN_ENDPOINT, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new PlanApiError(
      `无法连接 Real Planning 接口（请求地址：${PLAN_ENDPOINT}）。` +
        '请确认后端已提供该接口，且前端是通过 npm run dev / npm run preview 打开的。',
    )
  }

  if (!response.ok) {
    throw new PlanApiError(
      `Real Planning 接口返回 HTTP ${response.status}` +
        `${response.statusText ? ` ${response.statusText}` : ''}。` +
        '这通常意味着该接口尚未在当前后端版本中启用。',
    )
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new PlanApiError('Real Planning 接口返回的内容不是合法 JSON，无法解析为 PlanResult。')
  }

  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new PlanApiError('Real Planning 接口返回的数据结构不是预期对象，已停止渲染。')
  }

  return payload as PlanResult
}
