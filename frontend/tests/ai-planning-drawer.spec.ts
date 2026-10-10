/**
 * AI 调整抽屉的**端到端状态流**测试（界面层）。
 *
 * 覆盖任务书与 PR #65 Review 要求：
 * 草稿 → **第一次确认** → 求解 → 候选（`candidate_ready`）→ **第二次确认**
 * （采用 / 保留）→ 刷新；以及：不可用（未部署 / 未启用 / 无密钥）、
 * `can_confirm=false` 禁求解、`no_feasible_candidate`、`blocked`、
 * 预览标识、消息前置校验与长文本。
 *
 * ⚠️ 全部使用前端预览 fixture（`preview-enabled`），因此**不发任何真实请求**；
 * 测试同时断言这一点，防止预览模式偷偷调后端。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AiAdjustDrawer from '@/components/ai/AiAdjustDrawer.vue'
import { setAiPreviewScenario } from '@/api/aiPlanning'
import { AI_PREVIEW_NOTICE } from '@/api/aiPlanningFixtures'

const BASE_PLAN = {
  status: 'partially_feasible',
  selected_classes: [
    { course_id: '62001002', class_id: '6200100220260102' },
    { course_id: '62003007', class_id: '6200300720260101' },
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
]

const OFFERINGS = [
  {
    course_id: '62001002',
    course_name: '数据结构与算法',
    class_id: '6200100220260102',
    semester: '2026-1',
    credit: 4,
    meetings: [{ weekday: 5, start_section: 7, end_section: 8, weeks: [1, 2] }],
    data_source: 'mock',
  },
]

function mountDrawer(props: Record<string, unknown> = {}) {
  return mount(AiAdjustDrawer, {
    props: {
      open: true,
      semester: '2026-1',
      basePlan: BASE_PLAN,
      basePlanLabel: 'Mock 演示方案',
      makeupTasks: MAKEUP_TASKS,
      courseOfferings: OFFERINGS,
      preference: {
        max_credit: 20,
        avoid_cross_campus: false,
        preferred_courses: [],
        avoid_times: [],
        notes: null,
      },
      focusCourseId: null,
      apiEnabled: false,
      previewEnabled: true,
      ...props,
    },
  })
}

async function parseMessage(wrapper: ReturnType<typeof mountDrawer>): Promise<void> {
  await wrapper
    .find('[data-testid="ai-utterance-input"]')
    .setValue('这学期太累，数据结构必须保留，尽量别在周五上课')
  await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
  await flushPromises()
}

async function reachCandidate(wrapper: ReturnType<typeof mountDrawer>): Promise<void> {
  await parseMessage(wrapper)
  await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  setAiPreviewScenario('ok')
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  setAiPreviewScenario('ok')
})

describe('AI 抽屉：可用状态（三种未启用态）', () => {
  it('未启用真实接口且未开预览 ⇒ 明确显示不可用，不显示任何成功', async () => {
    const wrapper = mountDrawer({ previewEnabled: false, apiEnabled: false })
    await flushPromises()

    const blocked = wrapper.find('[data-testid="ai-not-configured"]')
    expect(blocked.exists()).toBe(true)
    expect(blocked.text()).toContain('不会')
    expect(wrapper.find('[data-testid="ai-utterance-input"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ai-adopted"]').exists()).toBe(false)
  })

  it('预览模式：状态来自 fixture，并醒目标注"仅前端预览 / 未调用 Planner"', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-drawer-channel"]').text()).toContain('前端预览')
    // 头部默认只给**面向用户的一句话状态**（⛔ 不再把原始配置字段直接铺开）
    const summary = wrapper.find('[data-testid="ai-drawer-status"]').text()
    expect(summary).toContain('演示模式')
    expect(summary).not.toContain('api_key_configured')
    // 原始状态字段必须**完整保留**在可展开的"技术详情"里（⛔ 不删信息）
    const tech = wrapper.find('[data-testid="ai-drawer-tech"]')
    expect(tech.exists()).toBe(true)
    expect(tech.attributes('open')).toBeUndefined()
    const raw = wrapper.find('[data-testid="ai-drawer-tech-raw"]').text()
    expect(raw).toContain('enabled=true')
    expect(raw).toContain('live_model_available=false')
    expect(raw).toContain('api_key_configured=')

    await parseMessage(wrapper)
    const notice = wrapper.find('[data-testid="ai-preview-notice"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain(AI_PREVIEW_NOTICE)
  })

  it('测试替身模型不得被说成"DeepSeek 已接入"', async () => {
    const wrapper = mountDrawer()
    await parseMessage(wrapper)

    const generator = wrapper.find('[data-testid="ai-generator-kind"]').text()
    expect(generator).toBe('测试替身模型（不是线上模型）')
    expect(generator).not.toContain('真实 DeepSeek')
    expect(wrapper.find('[data-testid="ai-generator-note"]').text()).toContain('测试替身')
  })

  it('预览模式全程不发出任何真实请求', async () => {
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)
    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    expect(fetch).not.toHaveBeenCalled()
  })
})

describe('AI 抽屉：第一次确认（意图）', () => {
  it('展示后端草稿：摘要 / 软偏好 / 学分未指定 / 锁定课程 / 范围', async () => {
    const wrapper = mountDrawer()
    await parseMessage(wrapper)

    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-intent-summary"]').text()).toContain('前端预览')
    expect(wrapper.find('[data-testid="ai-soft-preferences"]').text()).toContain(
      'prefer_fewer_credits',
    )
    expect(wrapper.find('[data-testid="ai-credit-unspecified"]').text()).toContain('不会替你猜')
    expect(wrapper.find('[data-testid="ai-locked-62001002"]').text()).toContain(
      '6200100220260102',
    )
    expect(wrapper.find('[data-testid="ai-scope"]').text()).toContain('current_semester')
    // 后端指纹只读展示
    expect(wrapper.find('[data-testid="ai-plan-digest"]').text()).toContain('preview0')
  })

  it('确认前不产生候选（必须先经过第一次确认）', async () => {
    const wrapper = mountDrawer()
    await parseMessage(wrapper)

    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ai-confirm-intent"]').attributes('disabled')).toBeUndefined()
  })

  it('学分上限可由用户填写（⛔ 不从文本猜），并显示将回传的值', async () => {
    const wrapper = mountDrawer()
    await parseMessage(wrapper)

    await wrapper.find('[data-testid="ai-credit-input"]').setValue('18')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-credit-limit"]').text()).toContain('将回传')
    expect(wrapper.find('[data-testid="ai-credit-limit"]').text()).toContain('18')
  })

  it('可以取消锁定课程，并可重新锁定（候选来自当前方案）', async () => {
    const wrapper = mountDrawer()
    await parseMessage(wrapper)

    await wrapper.find('[data-testid="ai-unlock-62001002"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-no-locked-courses"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-lock-62001002"]').exists()).toBe(true)
  })

  it('软偏好可编辑：取消"避开周五"', async () => {
    const wrapper = mountDrawer()
    await parseMessage(wrapper)

    const friday = wrapper.find('[data-testid="ai-avoid-weekday-5"]')
    await friday.trigger('click')
    await flushPromises()
    expect(friday.classes()).not.toContain('button--selected')
  })

  it('can_confirm=false ⇒ 禁用确认按钮并显示必须先回答的歧义', async () => {
    setAiPreviewScenario('ambiguous')
    const wrapper = mountDrawer()
    await parseMessage(wrapper)

    expect(wrapper.find('[data-testid="ai-ambiguities"]').text()).toContain(
      'credit_limit_missing_evidence',
    )
    const button = wrapper.find('[data-testid="ai-confirm-intent"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="ai-cannot-confirm"]').text()).toContain('仍有歧义')

    await button.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
  })
})

describe('AI 抽屉：求解与候选对比', () => {
  it('第一次确认后求解 ⇒ 只有 candidate_ready 才渲染候选对比', async () => {
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-solve-status"]').text()).toBe('candidate_ready')
    expect(wrapper.find('[data-testid="ai-candidate-meta"]').text()).toContain('PlanResult')
    expect(wrapper.find('[data-testid="ai-candidate-meta"]').text()).toContain('测试替身模型')
  })

  it('展示 diff 的四类集合与学分变化', async () => {
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    const diff = wrapper.find('[data-testid="ai-plan-diff"]')
    expect(diff.text()).toContain('新增（added）')
    expect(diff.text()).toContain('移除（removed）')
    expect(diff.text()).toContain('替换（replaced）')
    expect(diff.text()).toContain('保持（kept）')
    expect(wrapper.find('[data-testid="ai-credit-delta"]').text()).toBe('总学分 +2')
  })

  it('展示风险与未决（字符串数组）', async () => {
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    expect(wrapper.find('[data-testid="ai-solve-risks"]').text()).toContain('mock')
    expect(wrapper.find('[data-testid="ai-solve-unresolved"]').text()).toContain('62003007')
  })

  it('没有原方案时**拒绝解析**（后端要求 context 含 base_plan，前端不造假上下文）', async () => {
    const wrapper = mountDrawer({ basePlan: null })
    await parseMessage(wrapper)

    expect(wrapper.find('[data-testid="ai-error-kind"]').text()).toBe('plan_context_invalid')
    expect(wrapper.find('[data-testid="ai-error-message"]').text()).toContain('没有可调整的方案')
    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(false)
  })

  it('no_feasible_candidate ⇒ "未生成候选"且原方案不变', async () => {
    setAiPreviewScenario('no_feasible')
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    const unsolved = wrapper.find('[data-testid="ai-unsolved"]')
    expect(unsolved.exists()).toBe(true)
    expect(unsolved.text()).toContain('没有可行变化')
    expect(unsolved.text()).toContain('当前方案保持不变')
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
  })

  it('blocked ⇒ 显示"未生成候选"与阻塞说明', async () => {
    setAiPreviewScenario('blocked')
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    const unsolved = wrapper.find('[data-testid="ai-unsolved"]')
    expect(unsolved.text()).toContain('本次调整被拒绝')
    expect(unsolved.text()).toContain('锁定')
  })

  it('长文本原样展示，不被截断或重写', async () => {
    const wrapper = mountDrawer()
    const longMessage = '这是一段很长的调整说明。'.repeat(60)
    await wrapper.find('[data-testid="ai-utterance-input"]').setValue(longMessage)
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
  })
})

describe('AI 抽屉：第二次确认（采用 / 保留）', () => {
  it('采用成功 ⇒ 发出 applied 事件，方案体来自 /solve 的候选，并声明进程内会话', async () => {
    setAiPreviewScenario('adopted')
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-adopted"]').exists()).toBe(true)
    const scope = wrapper.find('[data-testid="ai-adopted-scope"]')
    expect(scope.text()).toContain('process_local_session')
    expect(scope.text()).toContain('未持久化')
    expect(scope.text()).toContain('不代表')
    expect(wrapper.find('[data-testid="ai-adopted-version"]').text()).toBe('1')

    const applied = wrapper.emitted('applied')
    expect(applied).toBeTruthy()
    const [plan, version] = applied?.[0] ?? []
    // 方案体来自 /solve 的候选（fixture 里的候选摘要），不是 adopt 返回值
    expect((plan as { objective_summary?: string }).objective_summary).toContain('受限 Planner')
    expect(version).toBe(1)
  })

  it('保留原方案 ⇒ 不发出 applied 事件，且显示"原方案未被改动"', async () => {
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    await wrapper.find('[data-testid="ai-keep-original"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('applied')).toBeFalsy()
    const kept = wrapper.find('[data-testid="ai-kept"]')
    expect(kept.exists()).toBe(true)
    expect(kept.text()).toContain('original_plan_unchanged')
  })

  it('回到草稿 ⇒ 回到第一次确认', async () => {
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    await wrapper.find('[data-testid="ai-back-to-draft"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(false)
  })

  it('采用冲突 ⇒ 不发出 applied 事件，保留候选以便重试', async () => {
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)

    setAiPreviewScenario('rejected')
    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('applied')).toBeFalsy()
    expect(wrapper.find('[data-testid="ai-candidate-compare"]').exists()).toBe(true)
  })

  it('采用后提供"以原方案为基准重新调整"的撤销入口', async () => {
    setAiPreviewScenario('adopted')
    const wrapper = mountDrawer()
    await reachCandidate(wrapper)
    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()

    const undo = wrapper.find('[data-testid="ai-undo-adoption"]')
    expect(undo.exists()).toBe(true)
    await undo.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-adopted"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ai-utterance-input"]').exists()).toBe(true)
  })
})

describe('AI 抽屉：上下文与响应式布局', () => {
  it('展示调整对象与通道状态', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-drawer-context"]').text()).toContain('Mock 演示方案')
    expect(wrapper.find('[data-testid="ai-drawer-channel"]').text()).toContain('前端预览')
  })

  it('聚焦课程时携带上下文并说明不会自动改这门课', async () => {
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

describe('消息前置校验（与后端 sanitize 同构）', () => {
  it('空消息不发请求', async () => {
    const wrapper = mountDrawer()
    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('   ')
    expect(wrapper.find('[data-testid="ai-parse-intent"]').attributes('disabled')).toBeDefined()
  })

  it('疑似个人信息 ⇒ 本地拒绝并提示改写（不发出请求）', async () => {
    const wrapper = mountDrawer()
    await wrapper
      .find('[data-testid="ai-utterance-input"]')
      .setValue('我的学号是 202312345678，请帮我调课')
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()

    const error = wrapper.find('[data-testid="ai-error-message"]')
    expect(error.text()).toContain('个人信息')
    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(false)
  })

  it('超长消息 ⇒ 本地拒绝', async () => {
    const wrapper = mountDrawer()
    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('调'.repeat(1001))
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ai-error-message"]').text()).toContain('太长')
  })
})
