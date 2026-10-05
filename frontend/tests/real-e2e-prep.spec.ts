/**
 * Real E2E 接线准备：错误状态、成功状态与 Real 提交开关。
 *
 * 覆盖本轮要求：
 * - **503 `real_pipeline_not_configured`** → 显示"真实规划运行时尚未完成装配"→ **不 fallback Mock**；
 * - **422** → 显示输入 / provenance 类错误（不笼统写成"系统错误"）；
 * - **500** → 显示服务端错误；
 * - **network error** → 显示网络错误；
 * - **Real success** → 展示 real PlanResult 且 source = Real；
 * - `VITE_PLAN_API_ENABLED` false → Real submit disabled；true + provenance 合法 → 允许 submit。
 *
 * ⚠️ 全部使用 mocked fetch，不依赖真实后端；不构造 Fake Real 数据以外的任何后端行为。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'
import SubmissionActions from '@/components/SubmissionActions.vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import {
  PlanApiError,
  REAL_PIPELINE_NOT_CONFIGURED,
  classifyPlanError,
  fetchRealPlan,
  parsePlanErrorBody,
} from '@/api/plan'
import { PLAN_ENDPOINT } from '@/config'
import { createDefaultUserInputForm, describePlanError } from '@/state/userInput'

/** 后端已知的 503 未装配响应体（与 `backend/app/main.py` 的 handler 一致）。 */
const NOT_CONFIGURED_BODY = {
  detail: {
    error: REAL_PIPELINE_NOT_CONFIGURED,
    message: '真实规划链路尚未配置。',
  },
}

/** FastAPI 标准 422 校验响应体。 */
const VALIDATION_BODY = {
  detail: [
    {
      type: 'value_error',
      loc: ['body', 'current_schedule'],
      msg: 'Value error, current_schedule 中所有教学班的 data_source 必须为 real',
    },
  ],
}

const REAL_PLAN_RESULT = {
  status: 'feasible',
  selected_classes: [{ course_id: 'CSE201', class_id: 'CSE201-01' }],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: 'REAL_PLAN_RESULT_MARKER',
}

const DEMO_PAYLOAD = {
  makeup_tasks: [
    { course_id: 'MAR103', course_name: 'MOCK_TASK_NAME', credit: 3, status: 'satisfied' },
  ],
  course_offerings: [
    {
      course_id: 'CSE201',
      course_name: 'MOCK_OFFERING_NAME',
      class_id: 'CSE201-01',
      semester: '2026-1',
      credit: 3,
      meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2] }],
      data_source: 'mock',
    },
  ],
  preference: { max_credit: 20, avoid_cross_campus: true, preferred_courses: [], avoid_times: [] },
  plan_result: {
    status: 'infeasible',
    selected_classes: [],
    changes: [],
    risks: [],
    unresolved: [],
    objective_summary: 'MOCK_DEMO_PLAN_MARKER',
  },
}

function jsonResponse(body: unknown, status = 200, statusText = ''): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** mock 通道正常、plan 通道按给定方式失败/成功的路由 fetch。 */
function routedFetch(planHandler: () => Promise<Response> | Response) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/v1/plan')) {
      return Promise.resolve(planHandler())
    }
    return Promise.resolve(jsonResponse(DEMO_PAYLOAD))
  })
}

async function mountAppWith(planHandler: () => Promise<Response> | Response) {
  vi.stubGlobal('fetch', routedFetch(planHandler))
  const wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

/* -------------------------------------------------------------------------- */
/* 1. 错误模型：fetchRealPlan 的分类                                            */
/* -------------------------------------------------------------------------- */

describe('Real API 错误模型', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const request = { semester: '2026-1', current_schedule: [], preference: {} }

  it('503 + real_pipeline_not_configured → kind = not_configured，并保留 code', async () => {
    fetchMock.mockResolvedValue(jsonResponse(NOT_CONFIGURED_BODY, 503, 'Service Unavailable'))

    const error = await fetchRealPlan(request).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(PlanApiError)
    const apiError = error as PlanApiError
    expect(apiError.kind).toBe('not_configured')
    expect(apiError.status).toBe(503)
    expect(apiError.code).toBe(REAL_PIPELINE_NOT_CONFIGURED)
    expect(apiError.detail).toContain('真实规划链路尚未配置')
    // 不得被笼统写成"请求失败"
    expect(apiError.message).toContain('尚未完成装配')
  })

  it('503 但 body 不可解析 → 仍归为 not_configured（宁可如实说未装配）', async () => {
    fetchMock.mockResolvedValue(new Response('<html>502 Bad Gateway</html>', { status: 503 }))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('not_configured')
    expect(error.status).toBe(503)
    expect(error.code).toBe(null)
    expect(error.detail).toBe(null)
  })

  it('503 但 body 可解析却无可识别信息 → 仍归为 not_configured', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ unexpected: true }, 503))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('not_configured')
    expect(error.status).toBe(503)
    expect(error.code).toBe(null)
  })

  it('503 但明确给出其它错误码 → kind = server，**不误报"未装配"**', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { error: 'planner_unavailable', message: 'planner 崩溃' } }, 503),
    )

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('server')
    expect(error.status).toBe(503)
    expect(error.code).toBe('planner_unavailable')
    // 消息必须说清这不是"未装配"
    expect(error.message).toContain('服务端错误')
    expect(error.message).not.toContain('尚未完成装配')
  })

  it('503 且只给出可识别 detail 文本（无 code）→ 也归为 server', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: '上游超时' } }, 503))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('server')
    expect(error.detail).toBe('上游超时')
    expect(error.message).not.toContain('尚未完成装配')
  })

  it('503 + real_pipeline_not_configured 优先于"其它错误"判断', async () => {
    // 同一个 body 里的 code 就是权威的未装配信号
    fetchMock.mockResolvedValue(jsonResponse(NOT_CONFIGURED_BODY, 503))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('not_configured')
  })

  it('classifyPlanError：503 三态分类矩阵', () => {
    // 1) 未装配的权威信号
    expect(
      classifyPlanError({ status: 503, code: REAL_PIPELINE_NOT_CONFIGURED, detail: null }),
    ).toBe('not_configured')
    // 2) 无可识别信息 → not_configured
    expect(classifyPlanError({ status: 503, code: null, detail: null })).toBe('not_configured')
    expect(classifyPlanError({ status: 503, code: '  ', detail: '  ' })).toBe('not_configured')
    // 3) 明确其它错误 → server
    expect(classifyPlanError({ status: 503, code: 'planner_unavailable', detail: null })).toBe(
      'server',
    )
    expect(classifyPlanError({ status: 503, code: null, detail: '上游超时' })).toBe('server')
    // code 权威性优先于状态码：即使状态码不是 503
    expect(
      classifyPlanError({ status: 500, code: REAL_PIPELINE_NOT_CONFIGURED, detail: null }),
    ).toBe('not_configured')
    // 其它状态码不受影响
    expect(classifyPlanError({ status: 422, code: null, detail: null })).toBe('input')
    expect(classifyPlanError({ status: 500, code: null, detail: null })).toBe('server')
    expect(classifyPlanError({ status: 404, code: null, detail: null })).toBe('http')
  })

  it('422 → kind = input，并提取 FastAPI 校验信息', async () => {
    fetchMock.mockResolvedValue(jsonResponse(VALIDATION_BODY, 422, 'Unprocessable Entity'))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('input')
    expect(error.status).toBe(422)
    expect(error.code).toBe('value_error')
    expect(error.detail).toContain('data_source 必须为 real')
    expect(error.message).toContain('不满足 Real Planning 的要求')
  })

  it('500 → kind = server', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'boom' }, 500, 'Internal Server Error'))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('server')
    expect(error.status).toBe(500)
    expect(error.message).toContain('服务端错误')
  })

  it('network error → kind = network 且 status = null', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('network')
    expect(error.status).toBe(null)
    expect(error.message).toContain('无法连接')
  })

  it('404 → kind = http（其它非 2xx）', async () => {
    fetchMock.mockResolvedValue(new Response('Not Found', { status: 404 }))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('http')
    expect(error.status).toBe(404)
  })

  it('2xx 但响应体不是对象 → kind = unexpected', async () => {
    fetchMock.mockResolvedValue(jsonResponse([1, 2, 3]))

    const error = (await fetchRealPlan(request).catch((e: unknown) => e)) as PlanApiError
    expect(error.kind).toBe('unexpected')
  })

  it('错误分类不 fallback 到 Mock 通道：请求地址只有 /api/v1/plan', async () => {
    fetchMock.mockResolvedValue(jsonResponse(NOT_CONFIGURED_BODY, 503))

    await fetchRealPlan(request).catch(() => undefined)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toBe(PLAN_ENDPOINT)
    expect(url).not.toContain('/mock/')
  })

  it('parsePlanErrorBody 对未知形状保持宽容（不假设统一 schema）', () => {
    // 已知 503 形状
    expect(parsePlanErrorBody(NOT_CONFIGURED_BODY)).toEqual({
      code: REAL_PIPELINE_NOT_CONFIGURED,
      detail: '真实规划链路尚未配置。',
    })
    // FastAPI 数组形状
    expect(parsePlanErrorBody(VALIDATION_BODY).code).toBe('value_error')
    // 字符串 detail
    expect(parsePlanErrorBody({ detail: 'plain text' })).toEqual({
      code: null,
      detail: 'plain text',
    })
    // 完全未知形状 / 非对象 → 不抛错
    expect(parsePlanErrorBody({ unexpected: true })).toEqual({ code: null, detail: null })
    expect(parsePlanErrorBody(null)).toEqual({ code: null, detail: null })
    expect(parsePlanErrorBody(42)).toEqual({ code: null, detail: '42' })
  })

  it('describePlanError：503 是"未装配"而不是系统故障', () => {
    const notConfigured = describePlanError('not_configured', 503)
    expect(notConfigured.title).toContain('真实规划运行时尚未完成装配')
    expect(notConfigured.hint).toContain('可继续使用 Mock Demo')
    expect(notConfigured.hint).toContain('不会自动回退到 Mock')

    expect(describePlanError('input', 422).title).toContain('输入来源不满足')
    expect(describePlanError('server', 500).title).toContain('服务端错误')
    expect(describePlanError('network', null).title).toContain('无法连接')

    // 503 被归为 server 时必须导向服务端排查，且不得出现"尚未完成装配"这一未装配措辞
    const server503 = describePlanError('server', 503)
    expect(server503.title).toContain('服务端错误')
    expect(server503.hint).toContain('服务端故障')
    expect(server503.hint).not.toContain('尚未完成装配')

    // "未装配"这一措辞只属于 not_configured
    expect(describePlanError('not_configured', 503).title).toContain('尚未完成装配')

    // 三类不得互相混同
    const titles = ['not_configured', 'input', 'server', 'network'].map(
      (kind) => describePlanError(kind, null).title,
    )
    expect(new Set(titles).size).toBe(titles.length)
  })
})

/* -------------------------------------------------------------------------- */
/* 2. App 级：失败与成功时的 UI 行为                                             */
/* -------------------------------------------------------------------------- */

describe('App 级：Real 失败状态展示', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('503 → 显示"真实规划运行时尚未完成装配"，且不 fallback 到 Mock 结果', async () => {
    const wrapper = await mountAppWith(() => jsonResponse(NOT_CONFIGURED_BODY, 503))

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="real-plan-error-title"]').text()).toContain(
      '真实规划运行时尚未完成装配',
    )
    expect(wrapper.find('[data-testid="real-plan-error-meta"]').text()).toContain('503')
    expect(wrapper.find('[data-testid="real-plan-error-meta"]').text()).toContain(
      REAL_PIPELINE_NOT_CONFIGURED,
    )
    // 仍是 Mock 结果 + Mock provenance（没有把 Mock 冒充成 Real）
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Mock')
    expect(wrapper.text()).toContain('MOCK_DEMO_PLAN_MARKER')
    // 也没有多余的 /mock/demo 请求被触发（只有首屏那一次）
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    const demoCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/mock/demo'))
    expect(demoCalls).toHaveLength(1)
  })

  it('503 但明确是其它错误 → 显示服务端错误，不误报"未装配"', async () => {
    const wrapper = await mountAppWith(() =>
      jsonResponse({ detail: { error: 'planner_unavailable', message: 'planner 崩溃' } }, 503),
    )

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const title = wrapper.find('[data-testid="real-plan-error-title"]').text()
    expect(title).toContain('服务端错误')
    expect(title).not.toContain('尚未完成装配')
    expect(wrapper.find('[data-testid="real-plan-error-code"]').text()).toBe('planner_unavailable')
    expect(wrapper.find('[data-testid="debug-error-kind"]').text()).toBe('server')
  })

  it('422 → 显示输入 / provenance 类错误，不写成"系统错误"', async () => {
    const wrapper = await mountAppWith(() => jsonResponse(VALIDATION_BODY, 422))

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const title = wrapper.find('[data-testid="real-plan-error-title"]').text()
    expect(title).toContain('输入来源不满足')
    expect(title).not.toContain('系统错误')
    expect(wrapper.find('[data-testid="real-plan-error-meta"]').text()).toContain('422')
  })

  it('500 → 显示服务端错误', async () => {
    const wrapper = await mountAppWith(() => jsonResponse({ detail: 'boom' }, 500))

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="real-plan-error-title"]').text()).toContain('服务端错误')
  })

  it('network error → 显示网络错误', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).includes('/api/v1/plan')) {
          return Promise.reject(new TypeError('Failed to fetch'))
        }
        return Promise.resolve(jsonResponse(DEMO_PAYLOAD))
      }),
    )
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="real-plan-error-title"]').text()).toContain('无法连接')

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).includes('/mock/'))).toHaveLength(1)
  })

  it('Real success → 展示 real PlanResult 且 source = Real', async () => {
    const wrapper = await mountAppWith(() => jsonResponse(REAL_PLAN_RESULT))

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('REAL_PLAN_RESULT_MARKER')
    expect(wrapper.text()).not.toContain('MOCK_DEMO_PLAN_MARKER')
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Real')
    expect(wrapper.find('[data-testid="data-mode-tag"]').text()).toContain('规划结果来源：Real')
    // 基础展示数据仍标 Mock，未被冒充成 Real
    expect(wrapper.text()).toContain('MOCK_TASK_NAME')
    expect(wrapper.findAll('.tag--mock').length).toBeGreaterThan(0)
  })
})

/* -------------------------------------------------------------------------- */
/* 3. E2E 调试信息（仅开发环境）                                                 */
/* -------------------------------------------------------------------------- */

describe('E2E 调试信息', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('开发环境显示调试信息，且只含结构 / 状态字段', async () => {
    const wrapper = await mountAppWith(() => jsonResponse(NOT_CONFIGURED_BODY, 503))

    const debug = wrapper.find('[data-testid="e2e-debug"]')
    expect(debug.exists()).toBe(true)

    expect(wrapper.find('[data-testid="debug-endpoint"]').text()).toContain('/api/v1/plan')
    expect(wrapper.find('[data-testid="debug-semester"]').text()).toBe('2026-1')
    expect(wrapper.find('[data-testid="debug-schedule-count"]').text()).toBe('0')
    expect(wrapper.find('[data-testid="debug-schedule-provenance"]').text()).toBe('empty')
    expect(wrapper.find('[data-testid="debug-result-source"]').text()).toBe('mock')

    // 提交失败后记录最近状态与错误类型
    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="debug-status"]').text()).toBe('503')
    expect(wrapper.find('[data-testid="debug-error-kind"]').text()).toBe('not_configured')

    // ⛔ 不泄漏私密数据 / 凭据。
    // 注意：面板底部的**固定免责声明**本身写着"不含成绩内容、姓名、学号、GPA"，
    // 因此这里只检查**展示出来的取值**（每个 dd），而不是整段文本。
    const values = debug.findAll('dd').map((node) => node.text())
    expect(values.length).toBeGreaterThan(0)
    for (const value of values) {
      for (const forbidden of ['学号', '姓名', 'GPA', '成绩', 'Bearer', 'cookie', 'token']) {
        expect(value).not.toContain(forbidden)
      }
      // 更关键：取值里不得出现任何学生身份 / 成绩类内容
      expect(value).not.toMatch(/\d{8,}/) // 学号 / 长数字 ID
    }
    // ⛔ 不 dump 整个请求 / 响应
    expect(debug.text()).not.toContain('MOCK_DEMO_PLAN_MARKER')
    expect(debug.text()).not.toContain('objective_summary')
    expect(debug.text()).not.toContain('MOCK_OFFERING_NAME')
    expect(debug.text()).not.toContain('MOCK_TASK_NAME')
  })

  it('dev = false 时不渲染调试面板（生产构建行为）', () => {
    const info = {
      planEndpoint: '/api/v1/plan',
      semester: '2026-1',
      scheduleCount: 0,
      scheduleProvenance: 'empty',
      preferencePresent: false,
      planApiEnabled: false,
      lastHttpStatus: null,
      lastErrorKind: null,
      planResultSource: 'mock',
    }

    const off = mount(UserInputPanel, {
      props: { form: createDefaultUserInputForm(), offerings: [], planApiEnabled: false, submitting: false, mode: 'mock' as const, debugInfo: info, dev: false },
    })
    expect(off.find('[data-testid="e2e-debug"]').exists()).toBe(false)

    const on = mount(UserInputPanel, {
      props: { form: createDefaultUserInputForm(), offerings: [], planApiEnabled: false, submitting: false, mode: 'mock' as const, debugInfo: info, dev: true },
    })
    expect(on.find('[data-testid="e2e-debug"]').exists()).toBe(true)
  })
})

/* -------------------------------------------------------------------------- */
/* 4. Real 提交开关                                                             */
/* -------------------------------------------------------------------------- */

describe('Real 提交开关（VITE_PLAN_API_ENABLED）', () => {
  it('false → Real submit disabled，且提示接口未开放', () => {
    const wrapper = mount(SubmissionActions, {
      props: {
        mode: 'mock' as const,
        planApiEnabled: false,
        inputValid: true,
        submitting: false,
      },
    })

    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="real-plan-disabled-hint"]').exists()).toBe(true)
  })

  it('true → provenance 合法时允许 submit', () => {
    const wrapper = mount(SubmissionActions, {
      props: {
        mode: 'mock' as const,
        planApiEnabled: true,
        inputValid: true,
        submitting: false,
      },
    })

    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="real-plan-disabled-hint"]').exists()).toBe(false)
  })

  it('true 但课表 provenance 不合法 → 仍被门禁阻止', () => {
    const wrapper = mount(SubmissionActions, {
      props: {
        mode: 'mock' as const,
        planApiEnabled: true,
        inputValid: false,
        submitting: false,
        scheduleBlockReason: '当前课表来源为 Mock 教学班，不能提交到 Real Planning。',
      },
    })

    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="schedule-provenance-blocked-hint"]').exists()).toBe(true)
  })

  it('开启开关不会自动发起任何 Real 请求', async () => {
    const fetchMock = routedFetch(() => jsonResponse(REAL_PLAN_RESULT))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()

    expect(
      fetchMock.mock.calls.filter((c) => String(c[0]).includes('/api/v1/plan')),
    ).toHaveLength(0)

    vi.unstubAllGlobals()
  })
})
