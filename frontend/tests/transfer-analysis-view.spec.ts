/**
 * `转专业分析` 视图测试：版本目录 readiness、缺口展示与"不冒充"边界。
 *
 * 对应任务书要求：
 * - 有真实核验时展示版本与认定状态；**无真实核验时显式"待配置 / Mock"**；
 * - 目录未配置（503）⇒ 明确"没有已核验版本目录"，⛔ 不退回固定 Case A；
 * - `planning = null`（没有排课能力）⇒ 明确显示跳过原因，⛔ 不显示"已排好课"；
 * - 预览 fixture 必须醒目标注，且**不是**模型输出。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TransferAnalysisView from '@/components/views/TransferAnalysisView.vue'
import {
  PERSONAL_PREVIEW_NOTICE,
  PREVIEW_PERSONAL_PLAN,
  PREVIEW_VERSION_LIST,
} from '@/api/personalPlanningFixtures'

type Phase = 'disabled' | 'loading' | 'ready' | 'not_configured' | 'empty' | 'error' | 'submitting' | 'planned'

function mountView(props: Record<string, unknown> = {}) {
  return mount(TransferAnalysisView, {
    props: {
      phase: 'ready' as Phase,
      selectableVersions: PREVIEW_VERSION_LIST.versions,
      rejectedVersions: PREVIEW_VERSION_LIST.rejected,
      catalogReason: 'ready',
      result: null,
      errorMessage: '',
      errorKind: null,
      errorCode: null,
      previewNotice: null,
      apiEnabled: false,
      currentSemester: '2026-1',
      currentScheduleCount: 2,
      ...props,
    },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('转专业分析：目录 readiness', () => {
  it('目录未配置（503）⇒ 明确说明没有已核验目录，且不提供任何版本选择', async () => {
    const wrapper = mountView({
      phase: 'not_configured',
      errorMessage: '当前没有已核验的培养方案版本目录',
      errorKind: 'not_configured',
      errorCode: 'personal_catalog_not_configured',
    })
    await flushPromises()

    const blocked = wrapper.find('[data-testid="personal-not-configured"]')
    expect(blocked.exists()).toBe(true)
    expect(blocked.text()).toContain('没有已核验的培养方案版本目录')
    expect(blocked.text()).toContain('不会')
    // ⛔ 没有可选版本时不得渲染版本选择
    expect(wrapper.find('[data-testid="personal-old-version"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="personal-submit"]').exists()).toBe(false)
  })

  it('目录为空 ⇒ 列出被拒条目与固定原因码，不猜测版本', async () => {
    const wrapper = mountView({ phase: 'empty', catalogReason: 'catalog_empty' })
    await flushPromises()

    expect(wrapper.find('[data-testid="personal-empty"]').exists()).toBe(true)
    const rejected = wrapper.find('[data-testid="personal-rejected"]')
    expect(rejected.text()).toContain('not_verified')
    expect(wrapper.find('[data-testid="personal-submit"]').exists()).toBe(false)
  })

  it('通道未启用 ⇒ 显示启用方式，不发请求也不显示版本', async () => {
    const wrapper = mountView({ phase: 'disabled' })
    await flushPromises()

    expect(wrapper.find('[data-testid="personal-disabled"]').text()).toContain(
      'VITE_PERSONAL_PLANNING_API_ENABLED',
    )
    expect(wrapper.find('[data-testid="personal-submit"]').exists()).toBe(false)
  })

  it('读取失败 ⇒ 显示失败类型，并明确不会用演示数据顶替', async () => {
    const wrapper = mountView({
      phase: 'error',
      errorMessage: '个人规划服务端错误',
      errorKind: 'server',
      errorCode: null,
    })
    await flushPromises()

    const error = wrapper.find('[data-testid="personal-error"]')
    expect(error.text()).toContain('服务端错误')
    expect(error.text()).toContain('不会用演示数据顶替')
    expect(wrapper.find('[data-testid="personal-error-kind"]').text()).toBe('server')
  })
})

describe('转专业分析：版本选择与提交', () => {
  it('未选版本时提交按钮禁用；选同一版本也禁用', async () => {
    const wrapper = mountView()
    const button = wrapper.find('[data-testid="personal-submit"]')
    expect(button.attributes('disabled')).toBeDefined()

    await wrapper.find('[data-testid="personal-old-version"]').setValue('preview-old-version')
    await wrapper.find('[data-testid="personal-target-version"]').setValue('preview-old-version')
    expect(wrapper.find('[data-testid="personal-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-testid="personal-target-version"]').setValue('preview-target-version')
    expect(wrapper.find('[data-testid="personal-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('提交时只发出两个版本 id（不携带任何个人信息字段）', async () => {
    const wrapper = mountView()
    await wrapper.find('[data-testid="personal-old-version"]').setValue('preview-old-version')
    await wrapper.find('[data-testid="personal-target-version"]').setValue('preview-target-version')
    await wrapper.find('[data-testid="personal-submit"]').trigger('click')
    await flushPromises()

    const emitted = wrapper.emitted('submit')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]?.[0]).toEqual({
      oldVersionId: 'preview-old-version',
      targetVersionId: 'preview-target-version',
    })
  })

  it('预览模式 ⇒ 醒目标注"仅前端预览 / 未读取已核验目录"', async () => {
    const wrapper = mountView({ previewNotice: PERSONAL_PREVIEW_NOTICE })
    await flushPromises()

    const notice = wrapper.find('[data-testid="personal-preview-notice"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain('仅前端预览')
    expect(notice.text()).toContain('未读取已核验目录')
  })
})

describe('转专业分析：结果与缺口', () => {
  it('planning = null ⇒ 明确"本次没有生成排课结果"并给出原因码含义', async () => {
    const wrapper = mountView({ phase: 'planned', result: PREVIEW_PERSONAL_PLAN })
    await flushPromises()

    const skipped = wrapper.find('[data-testid="personal-planning-skipped"]')
    expect(skipped.exists()).toBe(true)
    expect(skipped.text()).toContain('本次没有生成排课结果')
    expect(skipped.text()).toContain('没有调用 Planner')

    // ⛔ 不得出现"已排好课"这类结论
    expect(wrapper.text()).not.toContain('已排好课')
    expect(wrapper.find('[data-testid="personal-use-results"]').exists()).toBe(false)
  })

  it('展示认定状态分布与已修记录条数（全部来自后端字段）', async () => {
    const wrapper = mountView({ phase: 'planned', result: PREVIEW_PERSONAL_PLAN })
    await flushPromises()

    const counts = wrapper.find('[data-testid="personal-status-counts"]').text()
    expect(counts).toContain('需要补修：2')
    expect(counts).toContain('待人工确认：1')
    expect(wrapper.find('[data-testid="personal-data-source"]').text()).toBe('mock')
  })

  it('缺口逐条来自后端 MakeupTask（含判定说明与来源）', async () => {
    const wrapper = mountView({ phase: 'planned', result: PREVIEW_PERSONAL_PLAN })
    await flushPromises()

    const result = wrapper.find('[data-testid="personal-result"]')
    expect(result.text()).toContain('离散数学')
    expect(result.text()).toContain('可能等价')
    expect(result.text()).toContain('preview://fixture/diff/62001001')
  })

  it('只有后端给出 planning 时才提供"用作当前补修方案"', async () => {
    const withPlanning = {
      ...PREVIEW_PERSONAL_PLAN,
      planning: {
        status: 'partially_feasible',
        selected_classes: [{ course_id: '62001001', class_id: 'C1' }],
        changes: [],
        risks: [],
        unresolved: [],
        objective_summary: 'preview',
      },
      planning_skipped_code: null,
      planning_skipped_reason: null,
    }
    const wrapper = mountView({ phase: 'planned', result: withPlanning })
    await flushPromises()

    const button = wrapper.find('[data-testid="personal-use-results"]')
    expect(button.exists()).toBe(true)
    await button.trigger('click')
    expect(wrapper.emitted('use-results')).toBeTruthy()
  })
})
