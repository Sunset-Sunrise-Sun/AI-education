/**
 * 表单错误必须**阻止 Real Planning 请求**。
 *
 * 成功标准（本文件逐条锁定）：
 * - **untouched empty field** → 按 `null` / default 序列化，**允许**提交；
 * - **invalid user-entered field** → 表单 invalid → **禁止提交** → `fetch` **0 次调用**。
 *
 * 覆盖的非法输入：`max_credit` 负数 / 非数字、`semester` 非法、`avoid_times` 的 end < start。
 */

import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import {
  buildRealPlanRequest,
  createDefaultUserInputForm,
  isFormValid,
  normalizeMaxCreditInput,
} from '@/state/userInput'
import type { UserInputForm } from '@/state/userInput'

/**
 * 宿主组件 = App.vue 的实际用法 + `submitRealPlan()` 的守卫逻辑。
 *
 * ⚠️ 这里刻意包含与 `App.vue` 相同的 `isFormValid` 守卫，用来证明：
 * **即使提交被程序化触发**（绕过按钮 disabled），非法的表单也不会发出任何请求。
 */
function mountPanel() {
  const form = ref<UserInputForm>(createDefaultUserInputForm())

  /** 与 `App.vue` 的 `submitRealPlan()` 相同的守卫逻辑。 */
  function submitRealPlan(): void {
    if (!isFormValid(form.value)) {
      return
    }
    void fetchRealPlan(buildRealPlanRequest(form.value))
  }

  const fetchRealPlan = vi.fn(() => Promise.resolve({}))

  const Host = defineComponent({
    setup() {
      return () =>
        h(UserInputPanel, {
          form: form.value,
          offerings: [],
          planApiEnabled: true,
          submitting: false,
          mode: 'mock',
          onSubmitReal: submitRealPlan,
          'onUpdate:form': (value: UserInputForm) => {
            form.value = value
          },
        })
    },
  })

  return { wrapper: mount(Host), form, fetchRealPlan, submitRealPlan }
}

describe('invalid 表单禁止提交（fetch 0 次调用）', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(() => Promise.resolve({}))
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /* ---------- 单元层面：isFormValid 的判定 ---------- */

  it('normalizeMaxCreditInput：空串 = 合法未设定；负数 / 非数字 = 非法', () => {
    // untouched / 主动留空 → null 且**不**非法
    expect(normalizeMaxCreditInput('')).toEqual({ value: null, invalid: false })
    expect(normalizeMaxCreditInput('   ')).toEqual({ value: null, invalid: false })
    // 合法值原样接受
    expect(normalizeMaxCreditInput('24')).toEqual({ value: 24, invalid: false })
    expect(normalizeMaxCreditInput('22.5')).toEqual({ value: 22.5, invalid: false })
    expect(normalizeMaxCreditInput('0')).toEqual({ value: 0, invalid: false })
    // 非法输入：取值不猜测（null），但必须标记非法
    expect(normalizeMaxCreditInput('-5')).toEqual({ value: null, invalid: true })
    expect(normalizeMaxCreditInput('abc')).toEqual({ value: null, invalid: true })
    expect(normalizeMaxCreditInput('1e3')).toEqual({ value: null, invalid: true })
  })

  it('max_credit 为负数 → 表单 invalid（不猜测为未设定）', () => {
    const form = createDefaultUserInputForm()
    form.preference.maxCredit = null
    form.invalidFields = ['maxCredit']
    // 归一化后是 null，但仍必须 invalid —— 否则与"未触碰"无法区分
    expect(form.preference.maxCredit).toBe(null)
    expect(isFormValid(form)).toBe(false)
  })

  it('invalidFields 非空 → 一律 invalid；清空后恢复 valid', () => {
    const form = createDefaultUserInputForm()
    expect(isFormValid(form)).toBe(true)

    form.invalidFields = ['maxCredit']
    expect(isFormValid(form)).toBe(false)

    form.invalidFields = []
    expect(isFormValid(form)).toBe(true)
  })

  /* ---------- 真实交互：invalid 后禁止提交，fetch 0 调用 ---------- */

  it('max_credit = -5（负数）→ 表单 invalid → 按钮 disabled → fetch 0 调用', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel()

    await wrapper.find('[data-testid="max-credit-input"]').setValue('-5')

    expect(form.value.invalidFields).toContain('maxCredit')
    expect(isFormValid(form.value)).toBe(false)
    expect(wrapper.find('[data-testid="max-credit-error"]').exists()).toBe(true)

    const submit = wrapper.find('[data-testid="real-plan-submit"]')
    expect(submit.attributes('disabled')).toBeDefined()

    await submit.trigger('click')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(fetchRealPlan).not.toHaveBeenCalled()
  })

  it('max_credit = abc（非数字）→ 表单 invalid → fetch 0 调用', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel()

    await wrapper.find('[data-testid="max-credit-input"]').setValue('abc')

    expect(form.value.invalidFields).toContain('maxCredit')
    expect(isFormValid(form.value)).toBe(false)
    expect(wrapper.find('[data-testid="max-credit-error"]').exists()).toBe(true)

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(fetchRealPlan).not.toHaveBeenCalled()
  })

  it('程序化触发提交（绕过 disabled 按钮）时，守卫仍然拦截 → fetch 0 调用', async () => {
    const { wrapper, form, submitRealPlan, fetchRealPlan } = mountPanel()

    await wrapper.find('[data-testid="max-credit-input"]').setValue('-5')
    expect(isFormValid(form.value)).toBe(false)

    // 直接调用提交逻辑，模拟"按钮 disabled 被绕过"
    submitRealPlan()

    expect(fetchRealPlan).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('semester 非法 → 表单 invalid → 按钮 disabled → fetch 0 调用', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel()

    await wrapper.find('[data-testid="semester-input"]').setValue('2026-9')

    expect(isFormValid(form.value)).toBe(false)
    expect(wrapper.find('[data-testid="semester-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(fetchRealPlan).not.toHaveBeenCalled()
  })

  it('avoid_times 的 end < start → 表单 invalid → fetch 0 调用', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel()

    await wrapper.find('[data-testid="avoid-time-add"]').trigger('click')
    await wrapper.findAll('[data-testid="avoid-time-start"]')[0].setValue('5')
    await wrapper.findAll('[data-testid="avoid-time-end"]')[0].setValue('1')

    expect(form.value.preference.avoidTimes[0]).toMatchObject({
      start_section: 5,
      end_section: 1,
    })
    expect(isFormValid(form.value)).toBe(false)
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(fetchRealPlan).not.toHaveBeenCalled()
  })

  /* ---------- 反向：合法输入必须仍然可以提交，且空字段按 default 序列化 ---------- */

  it('untouched empty field → 按 null/default 序列化，允许提交', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel()

    // 未触碰任何字段：max_credit / notes 均为空
    const request = buildRealPlanRequest(form.value)
    expect(request.preference.max_credit).toBe(null)
    expect(request.preference.notes).toBe(null)
    expect(request.preference.avoid_cross_campus).toBe(false)
    expect(isFormValid(form.value)).toBe(true)
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchRealPlan).toHaveBeenCalledTimes(1)
  })

  it('修正非法输入后恢复可提交', async () => {
    const { wrapper, form, fetchRealPlan } = mountPanel()
    const input = wrapper.find('[data-testid="max-credit-input"]')

    await input.setValue('-5')
    expect(isFormValid(form.value)).toBe(false)

    await input.setValue('24')
    expect(form.value.invalidFields).not.toContain('maxCredit')
    expect(form.value.preference.maxCredit).toBe(24)
    expect(isFormValid(form.value)).toBe(true)
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    expect(fetchRealPlan).toHaveBeenCalledTimes(1)
  })

  it('清空非法输入（主动留空）后恢复可提交，并按 null 序列化', async () => {
    const { wrapper, form } = mountPanel()
    const input = wrapper.find('[data-testid="max-credit-input"]')

    await input.setValue('abc')
    expect(isFormValid(form.value)).toBe(false)

    await input.setValue('')
    expect(isFormValid(form.value)).toBe(true)
    expect(buildRealPlanRequest(form.value).preference.max_credit).toBe(null)
  })
})
