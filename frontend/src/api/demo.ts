import { DEMO_ENDPOINT } from '../config'
import type { DemoPayload } from '../types/contracts'

/** 请求失败时抛出的错误。消息面向非专业用户，不包含堆栈或任何敏感信息。 */
export class DemoApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'DemoApiError'
  }
}

export interface DemoResponse {
  /** 后端返回的四类公共对象。 */
  data: DemoPayload
  /**
   * 后端响应头 `X-Data-Source` 的值。
   *
   * 公共 Schema 中只有 `CourseOffering` 带 `data_source` 字段，
   * 所以后端用响应头标记整条 Mock 通道。这里把它读出来展示，
   * 让"当前是 Mock"这件事在后端和前端两侧都看得见。
   */
  dataSource: string | null
}

/**
 * 本阶段**唯一**的数据来源：`GET /api/v1/mock/demo`。
 *
 * 这个函数只做三件事：发请求、判断 HTTP 状态、把 JSON 原样返回。
 * 它**不做**任何数据加工、不补默认值、不在失败时返回兜底数据——
 * 后端失败时必须让页面诚实地显示失败，而不是展示一份编出来的方案。
 */
export async function fetchDemo(signal?: AbortSignal): Promise<DemoResponse> {
  let response: Response

  try {
    response = await fetch(DEMO_ENDPOINT, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new DemoApiError(
      `无法连接后端（请求地址：${DEMO_ENDPOINT}）。` +
        '请确认 FastAPI 已在 http://127.0.0.1:8000 启动，并且前端是通过 npm run dev / npm run preview 打开的。',
    )
  }

  if (!response.ok) {
    throw new DemoApiError(
      `后端返回 HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ''}。` +
        '这通常意味着后端服务异常，或接口路径发生了变化。',
    )
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new DemoApiError('后端返回的内容不是合法 JSON，无法解析为 Demo 数据。')
  }

  if (payload === null || typeof payload !== 'object') {
    throw new DemoApiError('后端返回的数据结构不是预期对象，已停止渲染。')
  }

  return {
    data: payload as DemoPayload,
    dataSource: response.headers.get('X-Data-Source'),
  }
}
