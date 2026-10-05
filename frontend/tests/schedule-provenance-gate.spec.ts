/**
 * provenance 门禁：**Mock 教学班不得进入 Real Planning**。
 *
 * 规则（本轮要求）：
 * - `current_schedule` 中任意 item 的 `data_source === 'mock'` → Real submit **必须被阻止** → `fetch` 0 次；
 * - **空** `current_schedule` → 允许提交；
 * - **全 real** 的 `current_schedule` → 允许通过 provenance 门禁。
 *
 * ⚠️ provenance 是**数据自身**的属性，与"页面当前处于哪个模式"无关。
 */

import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import { PLAN_ENDPOINT } from '@/config'
import {
  MOCK_SCHEDULE_BLOCK_REASON,
  createDefaultUserInputForm,
  evaluatePlanSubmission,
  hasMockSchedule,
  isScheduleSubmittableToRealPlanning,
  toggleCurrentScheduleOffering,
} from '@/state/userInput'
import type { UserInputForm } from '@/state/userInput'
import type { CourseOffering } from '@/types/contracts'

function offering(overrides: Partial<CourseOffering> = {}): CourseOffering {
  return {
    course_id: 'CSE201',
    course_name: '数据结构',
    class_id: 'CSE201-01',
    semester: '2026-1',
    credit: 3,
    meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2] }],
    data_source: 'mock',
    ...overrides,
  }
}

const MOCK_OFFERING = offering()
const REAL_OFFERING = offering({
  course_id: 'CSE202',
  class_id: 'CSE202-01',
  data_source: 'real',
})

/** 生产代码里 Real 提交真正会打的地址。 */
const MOCK_PLAN_ENDPOINT = PLAN_ENDPOINT

/**
 * 宿主组件 = `App.vue` 的真实用法：
 * 把 provenance 门禁结果传给面板，并复制 `submitRealPlan()` 的两道守卫。
 */
function mountPanel(offerings: CourseOffering[]) {
  const form = ref<UserInputForm>(createDefaultUserInputForm())

  function submitRealPlan(): void {
    if (!isScheduleSubmittableToRealPlanning(form.value)) {
      return
    }
    void fetchRealPlan(buildRequest())
  }

  const buildRequest = () => ({ semester: form.value.semester })
  const fetchRealPlan = vi.fn(() => Promise.resolve({}))

  const Host = defineComponent({
    setup() {
      return () =>
        h(UserInputPanel, {
          form: form.value,
          offerings,
          planApiEnabled: true,
          submitting: false,
          mode: 'mock',
          scheduleProvenanceBlocked: !isScheduleSubmittableToRealPlanning(form.value),
          onSubmitReal: submitRealPlan,
          'onUpdate:form': (value: UserInputForm) => {
            form.value = value
          },
        })
    },
  })

  return { wrapper: mount(Host), form, fetchRealPlan, submitRealPlan }
}

describe('provenance 门禁：Mock 课表禁止提交 Real Planning', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(() => Promise.resolve({}))
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /* ---------- 纯函数层面 ---------- */

  it('hasMockSchedule 只看 data_source，与模式无关', () => {
    const form = createDefaultUserInputForm()
    expect(hasMockSchedule(form)).toBe(false)

    form.currentSchedule = [MOCK_OFFERING]
    expect(hasMockSchedule(form)).toBe(true)

    form.currentSchedule = [REAL_OFFERING]
    expect(hasMockSchedule(form)).toBe(false)

    form.currentSchedule = [REAL_OFFERING, MOCK_OFFERING]
    expect(hasMockSchedule(form)).toBe(true)
  })

  it('isScheduleSubmittableToRealPlanning：空 / 全 real → 允许；含 mock → 禁止', () => {
    const form = createDefaultUserInputForm()
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(true)

    form.currentSchedule = [REAL_OFFERING]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(true)

    form.currentSchedule = [MOCK_OFFERING]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(false)
  })

  /* ---------- 交互层面：阻止提交且 fetch 0 次 ---------- */

  it('勾选 Mock 教学班 → 门禁阻止 → 按钮 disabled → fetch 0 调用 + 明确提示', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel([MOCK_OFFERING])

    await wrapper.find('[data-testid="schedule-checkbox-CSE201-CSE201-01"]').setValue(true)

    // 课表里确实有了一个 mock 教学班
    expect(form.value.currentSchedule).toHaveLength(1)
    expect(form.value.currentSchedule[0].data_source).toBe('mock')

    // 门禁生效
    expect(isScheduleSubmittableToRealPlanning(form.value)).toBe(false)
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()

    // 明确提示
    const hint = wrapper.find('[data-testid="schedule-provenance-blocked-hint"]')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain('当前课表来源为 Mock 教学班，不能提交到 Real Planning')

    // 点也点不动
    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(fetchRealPlan).not.toHaveBeenCalled()
  })

  it('程序化触发提交（绕过 disabled）同样被 provenance 守卫拦截 → fetch 0 调用', async () => {
    const { wrapper, submitRealPlan, fetchRealPlan } = mountPanel([MOCK_OFFERING])

    await wrapper.find('[data-testid="schedule-checkbox-CSE201-CSE201-01"]').setValue(true)
    submitRealPlan()

    expect(fetchRealPlan).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('empty current_schedule → 不因 provenance 门禁被阻断', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel([MOCK_OFFERING])

    // 一个都没勾
    expect(form.value.currentSchedule).toEqual([])
    expect(hasMockSchedule(form.value)).toBe(false)

    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="schedule-provenance-blocked-hint"]').exists()).toBe(false)

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchRealPlan).toHaveBeenCalledTimes(1)
  })

  it('real CourseOffering 的 current_schedule → 允许通过 provenance 门禁', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel([REAL_OFFERING])

    await wrapper.find('[data-testid="schedule-checkbox-CSE202-CSE202-01"]').setValue(true)

    expect(form.value.currentSchedule[0].data_source).toBe('real')
    expect(isScheduleSubmittableToRealPlanning(form.value)).toBe(true)
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="schedule-provenance-blocked-hint"]').exists()).toBe(false)

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchRealPlan).toHaveBeenCalledTimes(1)
  })

  it('取消勾选 Mock 教学班后门禁解除', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel([MOCK_OFFERING])
    const checkbox = wrapper.find('[data-testid="schedule-checkbox-CSE201-CSE201-01"]')

    await checkbox.setValue(true)
    expect(isScheduleSubmittableToRealPlanning(form.value)).toBe(false)

    await checkbox.setValue(false)
    expect(form.value.currentSchedule).toEqual([])
    expect(isScheduleSubmittableToRealPlanning(form.value)).toBe(true)
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchRealPlan).toHaveBeenCalledTimes(1)
  })

  it('toggleCurrentScheduleOffering 保留来源对象（含 data_source）', () => {
    const form = createDefaultUserInputForm()
    form.currentSchedule = toggleCurrentScheduleOffering([], MOCK_OFFERING, [MOCK_OFFERING])
    expect(form.currentSchedule[0].data_source).toBe('mock')
    expect(hasMockSchedule(form)).toBe(true)
  })

  /* ---------- 真实守卫（纯函数）：被阻止时一个请求也不发 ---------- */

  it('evaluatePlanSubmission：Mock 课表 → 不允许提交，且给出明确原因', () => {
    const form = createDefaultUserInputForm()
    form.currentSchedule = [MOCK_OFFERING]

    const gate = evaluatePlanSubmission(form)
    expect(gate.allowed).toBe(false)
    // 提示必须明确说明"Mock 课表不能提交到 Real Planning"
    expect(gate.reason).toContain('当前课表来源为 Mock 教学班，不能提交到 Real Planning')
    expect(gate.reason).toBe(MOCK_SCHEDULE_BLOCK_REASON)
  })

  it('evaluatePlanSubmission：空课表 / 全 real 课表 → 允许提交', () => {
    const empty = createDefaultUserInputForm()
    expect(evaluatePlanSubmission(empty).allowed).toBe(true)

    const real = createDefaultUserInputForm()
    real.currentSchedule = [REAL_OFFERING]
    expect(evaluatePlanSubmission(real).allowed).toBe(true)
  })

  it('evaluatePlanSubmission：表单非法（与 provenance 无关）同样被阻止', () => {
    const form = createDefaultUserInputForm()
    form.preference.maxCredit = null
    form.invalidFields = ['maxCredit']

    const gate = evaluatePlanSubmission(form)
    expect(gate.allowed).toBe(false)
    expect(gate.reason).toContain('表单存在未修正的输入问题')
  })

  it('真实守卫被阻止时：一个 /api/v1/plan 请求也不发（fetch 0 次）', () => {
    const form = createDefaultUserInputForm()
    form.currentSchedule = [MOCK_OFFERING]

    // 用生产代码的守卫驱动提交（而不是测试内自造的守卫）
    const submitRealPlan = () => {
      const gate = evaluatePlanSubmission(form)
      if (!gate.allowed) {
        return
      }
      void fetch(MOCK_PLAN_ENDPOINT, { method: 'POST' })
    }

    submitRealPlan()

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('真实守卫放行时：确实发出 /api/v1/plan 请求', () => {
    const form = createDefaultUserInputForm() // 空课表

    const submitRealPlan = () => {
      const gate = evaluatePlanSubmission(form)
      if (!gate.allowed) {
        return
      }
      void fetch(MOCK_PLAN_ENDPOINT, { method: 'POST' })
    }

    submitRealPlan()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toBe(MOCK_PLAN_ENDPOINT)
  })
})
