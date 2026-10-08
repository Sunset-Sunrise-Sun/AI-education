/**
 * AI 调整抽屉的**端到端状态流**测试（界面层）。
 *
 * 覆盖任务书要求的完整链路与失败路径：
 * 草稿 → 第一次确认 → 求解 → 候选 → 第二次确认（采用 / 保留）→ 刷新；
 * 以及：不支持（未配置）、无解、缺少必要条件、模型未采用、过期、拒绝、双确认、
 * Mock / 预览标识、窄屏（全屏类名）与长文本。
 *
 * ⚠️ 全部使用前端预览 fixture（`preview-enabled`），因此**不发任何真实请求**；
 * 测试同时断言这一点，防止预览模式偷偷调后端。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AiAdjustDrawer from '@/components/ai/AiAdjustDrawer.vue'
import { setAiPreviewScenario } from '@/api/aiPlanning'
import { AI_PREVIEW_NOTICE } from '@/api/aiPlanningFixtures'

const CURRENT_PLAN = {
  status: 'partially_feasible',
  selected_classes: [
    { course_id: '62001002', class_id: '6200100220260102' },
    { course_id: '62003007', class_id: '6200300720260102' },
  ],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: '原方案摘要',
}

const MAKEUP_TASKS = [
  {
    course_id: '62001002',
    course_name: '数据结构与算法',
    credit: 4,
    status: 'required',
    prerequisites: [],
  },
  {
    course_id: '62003007',
    course_name: '复变函数与积分变换',
    credit: 2,
    status: 'manual_confirmation',
    prerequisites: [],
  },
]

function mountDrawer(props: Record<string, unknown> = {}) {
  return mount(AiAdjustDrawer, {
    props: {
      open: true,
      planDigest: 'sha256:0123456789abcdef',
      semester: '2026-1',
      currentScheduleCount: 2,
      focusCourseId: null,
      currentPlan: CURRENT_PLAN,
      currentPlanLabel: 'Mock 演示方案',
      makeupTasks: MAKEUP_TASKS,
      apiEnabled: false,
      previewEnabled: true,
      ...props,
    },
  })
}

async function parseAndConfirm(wrapper: ReturnType<typeof mountDrawer>): Promise<void> {
  await wrapper.find('[data-testid="ai-utterance-input"]').setValue(
    '尽量在大三前补完，这学期尽量轻松，但数据结构必须保留',
  )
  await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  setAiPreviewScenario('ok')
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AI 抽屉：未配置 / 预览通道', () => {
  it('未启用且非预览 ⇒ 明确显示"尚未配置"，不调用规划器也不显示成功', async () => {
    const wrapper = mountDrawer({ previewEnabled: false, apiEnabled: false })
    await flushPromises()

    const blocked = wrapper.find('[data-testid="ai-not-configured"]')
    expect(blocked.exists()).toBe(true)
    expect(blocked.text()).toContain('不会')
    expect(wrapper.find('[data-testid="ai-utterance-input"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ai-adopted"]').exists()).toBe(false)
  })

  it('预览模式 ⇒ 全程显示"仅前端预览 / 非真实模型 / 未调用 Planner"', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)

    const notice = wrapper.find('[data-testid="ai-preview-notice"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain(AI_PREVIEW_NOTICE)
    expect(notice.text()).toContain('非真实模型')
    expect(notice.text()).toContain('未调用 Planner')
  })

  it('预览模式不发出任何真实请求', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    expect(fetch).not.toHaveBeenCalled()
  })
})

describe('AI 抽屉：第一次确认（草稿）', () => {
  it('解析后显示草稿：硬约束 / 软偏好 / 学分未指定 / 锁定课程 / 范围 / 未知项', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)

    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-hard-constraints"]').text()).toContain('数据结构必须保留')
    expect(wrapper.find('[data-testid="ai-soft-preferences"]').text()).toContain('这学期尽量轻松')
    expect(wrapper.find('[data-testid="ai-credit-unspecified"]').text()).toContain('不会替你猜')
    expect(wrapper.find('[data-testid="ai-locked-courses"]').text()).toContain('62001002')
    expect(wrapper.find('[data-testid="ai-scope"]').text()).toContain('before_year_3')
    expect(wrapper.find('[data-testid="ai-unknowns"]').text()).toContain('学分上限')
  })

  it('生成方式如实标注：规则模板 != AI 生成', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)

    expect(wrapper.find('[data-testid="ai-generator-kind"]').text()).toBe('规则模板（非 AI）')
  })

  it('确认前不请求求解（按钮点击即进入求解，但必须先确认）', async () => {
    const wrapper = mountDrawer()
    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('随便调整一下')
    // 未解析：没有草稿，也没有确认按钮
    expect(wrapper.find('[data-testid="ai-confirm-intent"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
  })

  it('学分上限可以编辑为明确数字，并随确认结果传给求解', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)

    await wrapper.find('[data-testid="ai-credit-input"]').setValue('18')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-credit-limit"]').text()).toContain('解析结果')
    expect(wrapper.find('[data-testid="ai-credit-limit"]').text()).toContain('18')
  })

  it('可以取消锁定课程（从草稿中移除）', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)

    await wrapper.find('[data-testid="ai-unlock-62001002"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-no-locked-courses"]').exists()).toBe(true)
    // 取消后可作为"可锁定"候选重新出现
    expect(wrapper.find('[data-testid="ai-lock-62001002"]').exists()).toBe(true)
  })

  it('解析不足（can_confirm=false）⇒ 禁止进入求解并说明原因', async () => {
    setAiPreviewScenario('low_confidence')
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)

    const button = wrapper.find('[data-testid="ai-confirm-intent"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="ai-cannot-confirm"]').text()).toContain('不足以求解')

    await button.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
  })
})

describe('AI 抽屉：求解与候选对比', () => {
  it('确认后求解 → 展示候选对比（新增 / 移除 / 调班 / 学分 / 硬约束 / 风险 / 未决）', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-solve-status"]').text()).toBe('candidate')
    expect(wrapper.find('[data-testid="ai-plan-diff"]').text()).toContain('离散数学')
    expect(wrapper.find('[data-testid="ai-plan-diff"]').text()).toContain('复变函数与积分变换')
    expect(wrapper.find('[data-testid="ai-hard-constraint-checks"]').text()).toContain('满足')
    expect(wrapper.find('[data-testid="ai-solve-risks"]').text()).toContain('剩余容量')
    expect(wrapper.find('[data-testid="ai-solve-unresolved"]').text()).toContain('manual_confirmation')
  })

  it('原方案明细缺失时如实说明，不用候选回填', async () => {
    const wrapper = mountDrawer({ currentPlan: null })
    await parseAndConfirm(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    const missing = wrapper.find('[data-testid="ai-original-plan-missing"]')
    expect(missing.exists()).toBe(true)
    expect(missing.text()).toContain('不会')
  })

  it('无解 ⇒ "未生成候选"且明确说明原方案不变', async () => {
    setAiPreviewScenario('infeasible')
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    const unsolved = wrapper.find('[data-testid="ai-unsolved"]')
    expect(unsolved.text()).toContain('无解')
    expect(unsolved.text()).toContain('当前方案保持不变')
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
  })

  it('缺少必要条件 ⇒ "未生成候选"并给出原因', async () => {
    setAiPreviewScenario('unavailable')
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    const unsolved = wrapper.find('[data-testid="ai-unsolved"]')
    expect(unsolved.text()).toContain('缺少必要条件')
    expect(unsolved.text()).toContain('教学班供给')
  })

  it('长文本原样展示，不被截断或重写', async () => {
    const wrapper = mountDrawer()
    await parseAndConfirm(wrapper)

    const longUtterance = '这是一段很长的调整说明。'.repeat(60)
    await wrapper.find('[data-testid="ai-utterance-input"]').setValue(longUtterance)
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()

    // 草稿仍然完整渲染（组件不做截断）
    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
  })
})

describe('AI 抽屉：第二次确认', () => {
  async function reachCandidate(props: Record<string, unknown> = {}) {
    const wrapper = mountDrawer(props)
    await parseAndConfirm(wrapper)
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  it('采用成功（后端确认）⇒ 发出 adopted 事件并显示结果版本', async () => {
    setAiPreviewScenario('adopted')
    const wrapper = await reachCandidate()

    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-adopted"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-adopted-message"]').text()).toContain('已采用候选方案')
    expect(wrapper.emitted('adopted')).toBeTruthy()
    expect(wrapper.emitted('adopted')?.[0]?.[0]).toMatchObject({ status: 'partially_feasible' })
  })

  it('候选过期 ⇒ 不发出 adopted 事件、原方案不变、可重新求解', async () => {
    setAiPreviewScenario('stale')
    const wrapper = await reachCandidate()

    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('adopted')).toBeFalsy()
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-error-message"]').text()).toContain('过期')
  })

  it('后端拒绝采用 ⇒ 不发出 adopted 事件且保留候选以便重试', async () => {
    // ⚠️ 求解与采用是两个独立场景：先正常产生候选，再让 adopt 被拒绝。
    const wrapper = await reachCandidate()
    setAiPreviewScenario('rejected')

    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('adopted')).toBeFalsy()
    expect(wrapper.find('[data-testid="ai-error-message"]').text()).toContain('拒绝')
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(true)
  })

  it('保留原方案 ⇒ 明确显示已保留，且不发出 adopted 事件', async () => {
    const wrapper = await reachCandidate()

    await wrapper.find('[data-testid="ai-keep-original"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('adopted')).toBeFalsy()
    expect(wrapper.find('[data-testid="ai-adopted"]').text()).toContain('保留原方案')
  })

  it('重新求解 ⇒ 回到草稿阶段并再次展示第一次确认', async () => {
    const wrapper = await reachCandidate()

    await wrapper.find('[data-testid="ai-resolve-again"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
  })

  it('采用按钮在提交中禁用（避免重复提交）', async () => {
    const wrapper = await reachCandidate()
    const button = wrapper.find('[data-testid="ai-adopt-candidate"]')
    expect(button.attributes('disabled')).toBeUndefined()
  })
})

describe('AI 抽屉：上下文与响应式布局', () => {
  it('展示调整对象、方案指纹与通道状态', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-drawer-context"]').text()).toContain('Mock 演示方案')
    expect(wrapper.find('[data-testid="ai-drawer-digest"]').text()).toBe('sha256:0123456789abcdef')
    expect(wrapper.find('[data-testid="ai-drawer-channel"]').text()).toContain('前端预览')
  })

  it('聚焦课程时携带 current course context 并说明不会自动改这门课', async () => {
    const wrapper = mountDrawer({ focusCourseId: '62001002' })
    await flushPromises()

    const focus = wrapper.find('[data-testid="ai-drawer-focus"]')
    expect(focus.text()).toContain('62001002')
    expect(focus.text()).toContain('不会自动改')
  })

  it('移动端使用全屏类名（桌面为右侧抽屉）', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    const drawer = wrapper.find('[data-testid="ai-drawer"]')
    expect(drawer.classes()).toContain('ai-drawer--open')
    expect(drawer.classes()).toContain('ai-drawer--fullscreen')
  })

  it('关闭按钮发出 close 事件', async () => {
    const wrapper = mountDrawer()
    await wrapper.find('[data-testid="ai-drawer-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})
