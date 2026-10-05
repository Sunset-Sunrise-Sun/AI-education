/**
 * App 级：Mock 教学班进入 current_schedule 后，真实 App.vue 的提交守卫必须阻止请求。
 *
 * ⚠️ 这里**不复制** App.vue 的守卫逻辑，直接挂真实 App 组件，
 * 因此它验证的是生产代码里的 provenance 门禁本身。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'

const DEMO_PAYLOAD = {
  makeup_tasks: [],
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

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json', 'X-Data-Source': 'mock' },
  })
}

const REAL_PLAN_RESULT = {
  status: 'feasible',
  selected_classes: [],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: 'REAL_PLAN_ENDPOINT_MARKER',
}

describe('App 级 provenance 门禁', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/v1/plan')) {
        return Promise.resolve(jsonResponse(REAL_PLAN_RESULT))
      }
      return Promise.resolve(jsonResponse(DEMO_PAYLOAD))
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('勾选 Mock 教学班 → 真实 App 阻止提交（按钮禁用 + 明确提示），不发 /api/v1/plan', async () => {
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()

    // 勾选一个 Mock 教学班
    await wrapper.find('[data-testid="schedule-checkbox-CSE201-CSE201-01"]').setValue(true)
    await flushPromises()

    // 明确提示 + 按钮禁用（真实 App 的 provenance 门禁生效）
    const hint = wrapper.find('[data-testid="schedule-provenance-blocked-hint"]')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain('当前课表来源为 Mock 教学班，不能提交到 Real Planning')
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()

    // 点击不应发出任何请求
    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const planCalls = fetchMock.mock.calls.filter((call) => String(call[0]).includes('/api/v1/plan'))
    expect(planCalls).toHaveLength(0)
    expect(wrapper.text()).not.toContain('REAL_PLAN_ENDPOINT_MARKER')
  })

  it('空 current_schedule → 真实 App 允许提交（能到达 /api/v1/plan）', async () => {
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const planCalls = fetchMock.mock.calls.filter((call) => String(call[0]).includes('/api/v1/plan'))
    expect(planCalls).toHaveLength(1)
    expect(wrapper.text()).toContain('REAL_PLAN_ENDPOINT_MARKER')
  })
})
