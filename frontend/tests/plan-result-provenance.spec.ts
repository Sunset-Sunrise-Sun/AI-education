/**
 * Real Planning 结果的**渲染与 provenance**（App 级集成测试）。
 *
 * 本轮修掉的 blocker：
 * `POST /api/v1/plan` 成功后设置了 `dataMode = 'real'`，
 * 但页面仍然渲染 `/api/v1/mock/demo` 的 `plan_result` → 出现"**Real 标签 + Mock 结果**"。
 *
 * 要求：
 * - Real 成功后**实际展示**后端返回的 `PlanResult`；
 * - **不得**把整页 MakeupTask / CourseOffering / Preference 冒充 Real；
 * - provenance 必须精确表达为「基础演示数据：Mock / 规划结果：Real」。
 *
 * ⚠️ 全部使用 mocked fetch：mock 通道与 real 通道各由一条 URL 路由区分，不依赖真实后端。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'

/** Mock Demo 通道返回的 PlanResult（必须可被识别为"演示结果"）。 */
const MOCK_PLAN_RESULT = {
  status: 'infeasible',
  // 刻意引用与 Mock teaching class 同号的 CSE201：用于验证
  // "Mock 的 courseNameById 只允许用于 Mock 结果"。
  selected_classes: [{ course_id: 'CSE201', class_id: 'CSE201-01' }],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: 'MOCK_DEMO_PLAN_MARKER',
}

/** Real 接口返回的 PlanResult（必须可被识别为"真实结果"）。 */
const REAL_PLAN_RESULT = {
  status: 'feasible',
  selected_classes: [{ course_id: 'CSE201', class_id: 'CSE201-01' }],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: 'REAL_PLAN_ENDPOINT_MARKER',
}

const DEMO_PAYLOAD = {
  makeup_tasks: [
    {
      course_id: 'MAR103',
      course_name: 'MOCK_TASK_NAME',
      credit: 3,
      status: 'satisfied',
    },
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
  plan_result: MOCK_PLAN_RESULT,
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

/** 按 URL 路由：/api/v1/plan → Real；其余 → Mock Demo。 */
function routedFetch(planResult: unknown = REAL_PLAN_RESULT) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/v1/plan')) {
      return Promise.resolve(jsonResponse(planResult))
    }
    return Promise.resolve(
      jsonResponse(DEMO_PAYLOAD, { headers: { 'Content-Type': 'application/json', 'X-Data-Source': 'mock' } }),
    )
  })
}

async function mountApp() {
  const wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('Real Planning 结果渲染与 provenance', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', routedFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('初始状态：规划结果 provenance 为 Mock，展示的是 Mock Demo 的结果', async () => {
    const wrapper = await mountApp()

    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Mock')
    expect(wrapper.text()).toContain('MOCK_DEMO_PLAN_MARKER')
    expect(wrapper.text()).not.toContain('REAL_PLAN_ENDPOINT_MARKER')
  })

  it('Real API 成功 → PlanResultPanel 实际展示 realPlanResult；Mock 结果不再显示', async () => {
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    // 1) 实际渲染的是 Real 返回结果
    expect(wrapper.text()).toContain('REAL_PLAN_ENDPOINT_MARKER')
    // 2) Mock 的规划结果不再被当作结果展示
    expect(wrapper.text()).not.toContain('MOCK_DEMO_PLAN_MARKER')
    // 3) provenance 精确到"规划结果"
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Real')
  })

  it('Real 结果区不使用 Mock 的 courseNameById：Mock 课程名不泄漏', async () => {
    const wrapper = await mountApp()

    // Real 返回的 selected_classes 引用了 Mock 教学班同号课程 CSE201
    expect(REAL_PLAN_RESULT.selected_classes[0].course_id).toBe('CSE201')

    const planSection = () => wrapper.find('#section-plan')

    // 提交前（Mock 结果）：结果区**可以**用 Mock 课程名做显示查找
    expect(planSection().text()).toContain('MOCK_OFFERING_NAME')

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    // 提交后（Real 结果）：结果区**不得**出现 Mock 课程名，
    // 只显示 Real 返回的课程号本身（courseNameById 被传空表）
    expect(planSection().text()).not.toContain('MOCK_OFFERING_NAME')
    expect(planSection().text()).toContain('CSE201')
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Real')
  })

  it('Real 提交后，输入区 provenance 标记显示"规划结果来源：Real"（局部文案）', async () => {
    const wrapper = await mountApp()

    expect(wrapper.find('[data-testid="data-mode-tag"]').text()).toContain('规划结果来源：Mock')

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const tag = wrapper.find('[data-testid="data-mode-tag"]').text()
    expect(tag).toContain('规划结果来源：Real')
    expect(tag).not.toContain('当前数据模式')
  })

  it('Real 请求体中的 current_schedule 为空（Mock 教学班未被提交）', async () => {
    const wrapper = await mountApp()
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const planCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/api/v1/plan'))
    expect(planCall).toBeDefined()
    const body = JSON.parse((planCall![1] as RequestInit).body as string)
    expect(body.current_schedule).toEqual([])
  })

  it('provenance 精确：基础演示数据仍标 Mock，不整页冒充 Real', async () => {
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const provenance = wrapper.find('[data-testid="plan-provenance"]').text()
    expect(provenance).toContain('基础演示数据：Mock')
    expect(provenance).toContain('规划结果：Real')

    // 基础数据没有被冒充成 Real：Mock 教学内容仍在，且仍标注 Mock 来源
    expect(wrapper.text()).toContain('MOCK_TASK_NAME')
    expect(wrapper.text()).toContain('MOCK_OFFERING_NAME')
    expect(wrapper.text()).toContain('mock')
    // 区块标题仍带 Mock 标记（MakeupTask / 教学班 / Preference 未变成 Real）
    expect(wrapper.findAll('.tag--mock').length).toBeGreaterThan(0)
  })

  it('Real 成功后提交内容仍只含三个字段，且请求打到 /api/v1/plan', async () => {
    const wrapper = await mountApp()
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const planCalls = fetchMock.mock.calls.filter((call) => String(call[0]).includes('/api/v1/plan'))
    expect(planCalls).toHaveLength(1)

    const init = planCalls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(Object.keys(JSON.parse(init.body as string)).sort()).toEqual([
      'current_schedule',
      'preference',
      'semester',
    ])
  })

  it('Real 失败 → 保持 Mock 结果与 Mock provenance，不回退也不冒充', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/v1/plan')) {
          return Promise.resolve(new Response('Not Found', { status: 404 }))
        }
        return Promise.resolve(jsonResponse(DEMO_PAYLOAD))
      }),
    )

    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Mock')
    expect(wrapper.find('[data-testid="real-plan-error"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('REAL_PLAN_ENDPOINT_MARKER')
  })
})
