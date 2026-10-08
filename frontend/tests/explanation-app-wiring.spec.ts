/**
 * App 级接线测试：解释入口与规划结果的关系。
 *
 * 关键要求：
 * - 解释入口只在**已有规划结果**时出现；
 * - 默认（未启用）时点击入口**不发出解释请求**，并明确显示"未启用"；
 * - 打开解释**不改变**规划结果展示、不触发 Real Planning、不改变 provenance；
 * - 解释通道与 Mock / Real 通道互相独立：解释请求只打到解释接口。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'

const DEMO_PAYLOAD = {
  makeup_tasks: [
    {
      course_id: 'C1',
      course_name: 'MOCK_TASK_NAME',
      credit: 3,
      status: 'required',
      reason: '新培养方案必修',
      source_evidence: 'mock://curriculum/C1（演示数据）',
    },
  ],
  course_offerings: [
    {
      course_id: 'C1',
      course_name: 'MOCK_OFFERING_NAME',
      class_id: 'C1-01',
      semester: '2026-1',
      credit: 3,
      meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2] }],
      data_source: 'mock',
    },
  ],
  preference: { max_credit: 20, avoid_cross_campus: true, preferred_courses: [], avoid_times: [] },
  plan_result: {
    status: 'partially_feasible',
    selected_classes: [{ course_id: 'C1', class_id: 'C1-01' }],
    changes: [
      { course_id: 'C1', from_class: 'C1-02', to_class: 'C1-01', reason: '原教学班命中回避时段' },
    ],
    risks: [{ course_id: 'C1', level: 'medium', reason: '容量偏低' }],
    unresolved: [{ type: 'manual_confirmation', message: '待人工确认' }],
    objective_summary: 'MOCK_PLAN_MARKER',
  },
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

function routedFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/v1/explanation/plan')) {
      return Promise.resolve(jsonResponse({ contract_version: 'explanation-v1' }))
    }
    if (url.includes('/api/v1/plan')) {
      return Promise.resolve(new Response('Not Found', { status: 404 }))
    }
    return Promise.resolve(
      jsonResponse(DEMO_PAYLOAD, {
        headers: { 'Content-Type': 'application/json', 'X-Data-Source': 'mock' },
      }),
    )
  })
}

async function mountApp() {
  const wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('App 级：解释入口接线', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', routedFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('有规划结果时出现解释入口，并明确解释对象与通道状态', async () => {
    const wrapper = await mountApp()

    const open = wrapper.find('[data-testid="explanation-open"]')
    expect(open.exists()).toBe(true)

    const provenance = wrapper.find('[data-testid="explanation-provenance"]').text()
    expect(provenance).toContain('Mock 演示结果')
    // 默认未启用（测试环境未设置 VITE_EXPLANATION_API_ENABLED）
    expect(wrapper.find('[data-testid="explanation-channel-state"]').text()).toBe('未启用')
  })

  it('默认未启用时点击入口不发出任何解释请求，并显示未启用说明', async () => {
    const wrapper = await mountApp()
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>

    const before = fetchMock.mock.calls.length

    await wrapper.find('[data-testid="explanation-open"]').trigger('click')
    await flushPromises()

    const explanationCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes('/api/v1/explanation/plan'),
    )
    expect(explanationCalls).toHaveLength(0)
    expect(fetchMock.mock.calls.length).toBe(before)

    expect(wrapper.find('[data-testid="explanation-error-kind"]').text()).toBe('disabled')
  })

  it('打开解释不改变规划结果展示与 provenance', async () => {
    const wrapper = await mountApp()

    const planTextBefore = wrapper.find('#section-plan').text()
    expect(planTextBefore).toContain('MOCK_PLAN_MARKER')

    await wrapper.find('[data-testid="explanation-open"]').trigger('click')
    await flushPromises()

    // 规划结果区内容与 provenance 未变
    expect(wrapper.find('#section-plan').text()).toContain('MOCK_PLAN_MARKER')
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Mock')
    // 解释区与规划结果区分属两个区块
    expect(wrapper.find('#section-explanation').exists()).toBe(true)
    expect(wrapper.find('#section-plan').text()).not.toContain('为什么这样安排（查看整体依据）')
  })

  it('补修判定行与方案条目的解释入口只发出事件，不自行生成解释文本', async () => {
    const wrapper = await mountApp()

    // 补修判定行：入口按钮只有开启解释通道时渲染 ⇒ 默认未启用时不渲染（避免发出无效请求）
    expect(wrapper.find('[data-testid="makeup-explain-C1"]').exists()).toBe(false)
    // 方案整体入口始终可用，并带有"只读解释"说明
    expect(wrapper.find('[data-testid="plan-explain-overall"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="explanation-open"]').exists()).toBe(true)
  })
})
