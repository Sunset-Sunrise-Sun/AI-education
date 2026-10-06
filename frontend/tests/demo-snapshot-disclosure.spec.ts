/**
 * 比赛演示披露与演示路线（Demo Closure）。
 *
 * 覆盖两件事：
 * 1. **教学班演示快照披露**：逐字标签 + 随规划结果来源切换的说明文案
 *    （⛔ 模式 1 下不得复用模式 2 的“仍通过实际系统链路执行”口径）；
 * 2. **8 场景演示路线**：纯导航，锚点必须指向页面真实存在的区块。
 *
 * ⛔ 这里不复制组件内的判断逻辑，直接挂真实组件 / 真实 App。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'
import DemoSceneGuide from '@/components/DemoSceneGuide.vue'
import SyntheticSnapshotNotice from '@/components/SyntheticSnapshotNotice.vue'
import {
  DEMO_DATA_DISCLOSURE_UI,
  SYNTHETIC_SNAPSHOT_LABEL,
  SYNTHETIC_SNAPSHOT_LIMITATION,
  SYNTHETIC_SNAPSHOT_NOTE_MOCK,
  SYNTHETIC_SNAPSHOT_NOTE_REAL,
} from '@/utils/labels'

const DEMO_PAYLOAD = {
  makeup_tasks: [
    {
      course_id: 'CSE201',
      course_name: '演示课程',
      credit: 3,
      status: 'manual_confirmation',
      reason: '演示数据',
      source_evidence: 'mock://curriculum/diff/CSE201（演示数据）',
    },
  ],
  course_offerings: [
    {
      course_id: 'CSE201',
      course_name: '演示课程',
      class_id: 'DEMO-CSE201-1',
      semester: '2026-1',
      credit: 3,
      meetings: [],
      data_source: 'mock',
    },
  ],
  preference: { max_credit: 20, avoid_cross_campus: true, preferred_courses: [], avoid_times: [] },
  plan_result: {
    status: 'partially_feasible',
    selected_classes: [{ course_id: 'CSE201', class_id: 'DEMO-CSE201-1' }],
    changes: [],
    risks: [],
    unresolved: [{ type: 'manual_confirmation', message: '演示：需要人工确认。' }],
    objective_summary: 'MOCK_DEMO_PLAN_MARKER',
  },
}

const REAL_PLAN_RESULT = {
  status: 'partially_feasible',
  selected_classes: [],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: 'REAL_PLAN_ENDPOINT_MARKER',
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json', 'X-Data-Source': 'mock' },
  })
}

async function mountApp() {
  const wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('教学班演示快照披露（Synthetic）', () => {
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

  it('页面加载后逐字渲染披露标签，且标签不在折叠区里（始终可见）', async () => {
    const wrapper = await mountApp()

    const label = wrapper.find('[data-testid="synthetic-snapshot-label"]')
    expect(label.exists()).toBe(true)
    expect(label.text()).toBe(SYNTHETIC_SNAPSHOT_LABEL)
    // ⛔ 主标签不得位于 <details> 内（只有背景说明可以折叠）
    expect(label.element.closest('details')).toBeNull()

    // 与模式无关的 UI 披露逐字可见
    expect(wrapper.find('[data-testid="demo-data-disclosure"]').text()).toBe(
      DEMO_DATA_DISCLOSURE_UI,
    )

    expect(wrapper.find('[data-testid="synthetic-snapshot-limitation"]').text()).toBe(
      SYNTHETIC_SNAPSHOT_LIMITATION,
    )
  })

  it('回放模式使用如实说明：预置样例 + 未执行本次求解，⛔ 不声称其余链路已执行', async () => {
    const wrapper = await mountApp()

    const note = wrapper.find('[data-testid="synthetic-snapshot-note"]').text()
    expect(note).toBe(SYNTHETIC_SNAPSHOT_NOTE_MOCK)
    expect(note).not.toBe(SYNTHETIC_SNAPSHOT_NOTE_REAL)
    expect(note).toContain('未执行本次 Planner 求解')
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Mock')
  })

  it('计算模式（实际提交成功后）切换到「实际代码计算」口径，并声明实际执行 ≠ 输入真实', async () => {
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Real')
    const note = wrapper.find('[data-testid="synthetic-snapshot-note"]').text()
    expect(note).toBe(SYNTHETIC_SNAPSHOT_NOTE_REAL)
    expect(note).toContain('Actual API computation')
    expect(note).toContain('不等于输入数据已获得真实学校来源认证')
    // 教学班区块本身仍标 Mock 演示数据，披露标签持续可见
    expect(wrapper.find('[data-testid="synthetic-snapshot-label"]').text()).toBe(
      SYNTHETIC_SNAPSHOT_LABEL,
    )
  })

  it('⛔ 披露文案不含"已选课 / 可直接执行 / 无冲突 / 尚未排课"类表述', async () => {
    const wrapper = mount(SyntheticSnapshotNotice, {
      props: { planResultMode: 'real' },
    })
    const text = wrapper.text()

    for (const forbidden of ['已选课', '可直接执行', '无冲突', '尚未排课', '无课', '异步课程']) {
      expect(text).not.toContain(forbidden)
    }
  })

  it('⛔ 页面不把「教学班是 Synthetic」写成「其余输入都真实」', async () => {
    const wrapper = await mountApp()
    const text = wrapper.text()

    for (const forbidden of ['其余全部真实', '其余数据均为真实', '只有教学班是 Synthetic，其余']) {
      expect(text).not.toContain(forbidden)
    }
    expect(text).toContain('输入来源需逐项核验')
  })
})

describe('8 场景演示路线', () => {
  it('恰好渲染 8 个场景，锚点指向真实区块 id', () => {
    const wrapper = mount(DemoSceneGuide, { attachTo: document.body })

    const links = wrapper.findAll('.scene-guide__link')
    expect(links).toHaveLength(8)

    const hrefs = links.map((link) => link.attributes('href'))
    expect(hrefs).toEqual([
      '#section-user-input',
      '#section-makeup',
      '#section-makeup',
      '#section-offerings',
      '#section-plan-risks',
      '#section-plan-changes',
      '#section-plan-selected',
      '#section-plan-unresolved',
    ])
  })

  it('纯导航：⛔ 不发起任何请求', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    mount(DemoSceneGuide)
    await flushPromises()

    expect(fetchMock).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('App 级：8 场景与第 4 区四个子块锚点同时存在于页面', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(DEMO_PAYLOAD))),
    )

    const wrapper = await mountApp()

    expect(wrapper.find('[data-testid="demo-scene-guide"]').exists()).toBe(true)
    for (const sectionId of [
      'section-user-input',
      'section-makeup',
      'section-offerings',
      'section-plan-selected',
      'section-plan-changes',
      'section-plan-risks',
      'section-plan-unresolved',
    ]) {
      expect(wrapper.find(`#${sectionId}`).exists()).toBe(true)
    }

    vi.unstubAllGlobals()
  })
})
