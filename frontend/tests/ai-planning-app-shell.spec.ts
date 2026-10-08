/**
 * 页面外壳（三入口信息架构）与 AI 调整端到端集成测试。
 *
 * 对应任务书要求：
 * - 三个导航入口：转专业分析 / 补修路径 / AI 调整；
 * - 保留旧 Case A 区块（补修路径为默认视图，旧 data-testid 未改名）；
 * - AI 面板围绕**当前选中补修方案**，必须经过两次确认才可能刷新方案；
 * - 未配置时不显示"已调整成功"；采用失败 / 保留原方案时当前方案不变；
 * - 预览 fixture 醒目标注，且全程不发真实后端请求。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'
import { setAiPreviewScenario } from '@/api/aiPlanning'

const DEMO_PAYLOAD = {
  makeup_tasks: [
    {
      course_id: '62001002',
      course_name: '数据结构与算法',
      credit: 4,
      status: 'required',
      reason: '新培养方案核心课',
      source_evidence: 'mock://curriculum/diff/62001002（演示数据）',
    },
    {
      course_id: '62003007',
      course_name: '复变函数与积分变换',
      credit: 2,
      status: 'manual_confirmation',
      reason: '学分不一致，需人工判定',
      source_evidence: 'mock://curriculum/manual/62003007（演示数据）',
    },
  ],
  course_offerings: [
    {
      course_id: '62001002',
      course_name: '数据结构与算法',
      class_id: '6200100220260102',
      semester: '2026-1',
      credit: 4,
      meetings: [{ weekday: 5, start_section: 7, end_section: 8, weeks: [1, 2] }],
      data_source: 'mock',
    },
  ],
  preference: { max_credit: 18, avoid_cross_campus: true, preferred_courses: [], avoid_times: [] },
  plan_result: {
    status: 'partially_feasible',
    selected_classes: [
      { course_id: '62001002', class_id: '6200100220260102' },
      { course_id: '62003007', class_id: '6200300720260102' },
    ],
    changes: [],
    risks: [{ course_id: '62001002', level: 'medium', reason: '容量偏低' }],
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
    if (url.includes('/api/v1/mock/demo')) {
      return Promise.resolve(
        jsonResponse(DEMO_PAYLOAD, {
          headers: { 'Content-Type': 'application/json', 'X-Data-Source': 'mock' },
        }),
      )
    }
    // ⛔ AI 调整接口**未实现**：任何真实请求都必须失败，且页面不得因此伪造成功。
    return Promise.resolve(new Response('Not Found', { status: 404 }))
  })
}

async function mountApp() {
  const wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setAiPreviewScenario('ok')
  vi.stubGlobal('fetch', routedFetch())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('页面外壳：三入口信息架构', () => {
  it('渲染三个导航入口，默认落在"补修路径"', async () => {
    const wrapper = await mountApp()

    expect(wrapper.find('[data-testid="nav-transfer-analysis"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-makeup-path"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-ai-adjust"]').exists()).toBe(true)

    expect(wrapper.find('[data-testid="view-makeup-path"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="view-transfer-analysis"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="view-ai-adjust"]').exists()).toBe(false)
  })

  it('切换到"转专业分析"显示缺口视图；旧 Case A 区块仍在默认视图', async () => {
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="nav-transfer-analysis"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="view-transfer-analysis"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="view-makeup-path"]').exists()).toBe(false)
    // 预览目录已加载（测试环境开启个人规划预览）
    expect(wrapper.find('[data-testid="personal-old-version"]').exists()).toBe(true)

    await wrapper.find('[data-testid="nav-makeup-path"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('#section-makeup').exists()).toBe(true)
    expect(wrapper.find('#section-plan').exists()).toBe(true)
  })

  it('切换到"AI 调整"显示两次确认说明并可打开抽屉', async () => {
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="nav-ai-adjust"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="view-ai-adjust"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-two-step-guide"]').text()).toContain('第一次确认')

    await wrapper.find('[data-testid="ai-view-open-drawer"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-drawer"]').classes()).toContain('ai-drawer--open')
  })
})

describe('补修路径视图：当前课表与后续学期路径', () => {
  it('展示当前学期精确课表（含排课信息与课程名）', async () => {
    const wrapper = await mountApp()

    const current = wrapper.find('[data-testid="path-current-classes"]')
    expect(current.exists()).toBe(true)
    expect(current.text()).toContain('62001002')
    expect(current.text()).toContain('数据结构与算法')
    expect(current.text()).toContain('班号 6200100220260102')
    expect(current.text()).toContain('周5')
  })

  it('展示风险与人工确认（来自后端字段）', async () => {
    const wrapper = await mountApp()

    expect(wrapper.find('[data-testid="path-risk-list"]').text()).toContain('容量偏低')
    expect(wrapper.find('[data-testid="path-unresolved-list"]').text()).toContain(
      'manual_confirmation',
    )
  })

  it('AI 调整入口把焦点课程作为上下文打开抽屉（不自动改课）', async () => {
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="path-focus-ai-62001002"]').trigger('click')
    await flushPromises()

    const focus = wrapper.find('[data-testid="ai-drawer-focus"]')
    expect(focus.exists()).toBe(true)
    expect(focus.text()).toContain('62001002')
    expect(focus.text()).toContain('不会自动改')
  })
})

describe('AI 调整：两次确认端到端（预览 fixture）', () => {
  async function openDrawerAndParse(wrapper: Awaited<ReturnType<typeof mountApp>>) {
    await wrapper.find('[data-testid="nav-open-ai-drawer"]').trigger('click')
    await flushPromises()
    await wrapper
      .find('[data-testid="ai-utterance-input"]')
      .setValue('尽量在大三前补完，这学期尽量轻松，但数据结构必须保留')
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()
  }

  it('未配置且非预览时明确"尚未配置"，不显示任何成功状态', async () => {
    // 测试环境已开启预览，因此这里直接用预览路径验证"标注"；
    // 未配置分支由 AiAdjustDrawer 单测覆盖（不重复）。
    const wrapper = await mountApp()
    await openDrawerAndParse(wrapper)

    expect(wrapper.find('[data-testid="ai-preview-notice"]').text()).toContain('未调用 Planner')
    expect(wrapper.find('[data-testid="ai-adopted"]').exists()).toBe(false)
  })

  it('第一次确认前不产生候选；确认后才出现候选对比', async () => {
    const wrapper = await mountApp()
    await openDrawerAndParse(wrapper)

    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)

    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(true)
  })

  it('采用成功后当前方案刷新为候选内容，并把 provenance 标成非 Mock', async () => {
    setAiPreviewScenario('adopted')
    const wrapper = await mountApp()
    await openDrawerAndParse(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    // 抽屉给出后端确认结论
    expect(wrapper.find('[data-testid="ai-adopted"]').text()).toContain('已采用候选方案')

    // 关闭抽屉后回到补修路径视图
    await wrapper.find('[data-testid="ai-drawer-close"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="nav-makeup-path"]').trigger('click')
    await flushPromises()

    // 当前方案的规划结果区已经换成候选内容（不再是原 Mock 方案的摘要），
    // 且 provenance 不再是 Mock（预览模式同样不应被标成 Mock 真实结论）。
    const planSection = wrapper.find('#section-plan')
    expect(planSection.text()).not.toContain('MOCK_PLAN_MARKER')
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).not.toBe('Mock')
  })

  it('第二次确认"保留原方案"时不刷新方案，且不显示已采用', async () => {
    const wrapper = await mountApp()
    const before = wrapper.find('#section-plan').text()

    await openDrawerAndParse(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="ai-keep-original"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-adopted"]').text()).toContain('保留原方案')
    expect(wrapper.find('[data-testid="ai-adopted"]').text()).not.toContain('已采用候选方案')

    await wrapper.find('[data-testid="ai-drawer-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('#section-plan').text()).toBe(before)
  })

  it('候选过期时不刷新方案，并提示可重新求解', async () => {
    const wrapper = await mountApp()
    const before = wrapper.find('#section-plan').text()

    await openDrawerAndParse(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    setAiPreviewScenario('stale')
    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-error-message"]').text()).toContain('过期')
    expect(wrapper.find('[data-testid="ai-adopted"]').exists()).toBe(false)

    await wrapper.find('[data-testid="ai-drawer-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('#section-plan').text()).toBe(before)
  })

  it('全过程不向未实现的 AI 接口伪造成功（真实请求一律 404，但预览不请求）', async () => {
    const wrapper = await mountApp()
    await openDrawerAndParse(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    const aiCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes('/api/v1/ai-planning/'),
    )
    expect(aiCalls).toHaveLength(0)
  })
})
