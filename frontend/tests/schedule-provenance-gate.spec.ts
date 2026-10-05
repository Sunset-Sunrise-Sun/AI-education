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
import { defineComponent, h, nextTick, ref } from 'vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import { PLAN_ENDPOINT } from '@/config'
import {
  MOCK_SCHEDULE_BLOCK_REASON,
  UNVERIFIED_SCHEDULE_BLOCK_REASON,
  createDefaultUserInputForm,
  evaluatePlanSubmission,
  hasMockSchedule,
  isRealSourceOffering,
  isScheduleSubmittableToRealPlanning,
  scheduleProvenanceBlockReason,
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
 * 传 `scheduleBlockReason`（生产用的纯函数），并用 `evaluatePlanSubmission` 做提交守卫。
 *
 * 额外提供 `select(offering)`：用于注入**来源未经确认**或**不在来源列表中**的教学班
 * （`CurrentScheduleInput` 只能勾选已加载的教学班，无法直接构造这种状态）。
 */
function mountPanel(offerings: CourseOffering[]) {
  const form = ref<UserInputForm>(createDefaultUserInputForm())
  const fetchRealPlan = vi.fn(() => Promise.resolve({}))

  function submitRealPlan(): void {
    const gate = evaluatePlanSubmission(form.value)
    if (!gate.allowed) {
      return
    }
    void fetchRealPlan({ semester: form.value.semester })
  }

  /**
   * 直接构造当前课表（用于 unknown 来源等面板无法表达的边界）。
   *
   * ⚠️ 不走 `toggleCurrentScheduleOffering`：那个函数会拒绝不在来源列表中的教学班
   * （它自己也是 fail closed），因此这里直接写状态。
   */
  function select(offering: CourseOffering): void {
    const already = form.value.currentSchedule.some(
      (item) => item.course_id === offering.course_id && item.class_id === offering.class_id,
    )
    form.value = {
      ...form.value,
      currentSchedule: already
        ? form.value.currentSchedule.filter(
            (item) =>
              !(
                item.course_id === offering.course_id && item.class_id === offering.class_id
              ),
          )
        : [...form.value.currentSchedule, offering],
    }
  }

  const Host = defineComponent({
    setup() {
      return () =>
        h(UserInputPanel, {
          form: form.value,
          offerings,
          planApiEnabled: true,
          submitting: false,
          mode: 'mock',
          scheduleBlockReason: scheduleProvenanceBlockReason(form.value),
          onSubmitReal: submitRealPlan,
          'onUpdate:form': (value: UserInputForm) => {
            form.value = value
          },
        })
    },
  })

  return { wrapper: mount(Host), form, fetchRealPlan, submitRealPlan, select }
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

  it('isScheduleSubmittableToRealPlanning 是 fail closed 的：只放行"空"或"每项 real"', () => {
    const form = createDefaultUserInputForm()
    // 空 → 放行
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(true)

    // 每项 real → 放行
    form.currentSchedule = [REAL_OFFERING]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(true)
    form.currentSchedule = [REAL_OFFERING, offering({ class_id: 'CSE202-02', data_source: 'real' })]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(true)

    // 含 mock → 拒绝
    form.currentSchedule = [MOCK_OFFERING]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(false)

    // real + mock 混合 → 拒绝
    form.currentSchedule = [REAL_OFFERING, MOCK_OFFERING]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(false)

    // 来源未经确认（缺字段 / 其它取值）→ **拒绝**（不是放行）
    form.currentSchedule = [offering({ data_source: undefined as unknown as 'mock' })]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(false)
    form.currentSchedule = [offering({ data_source: 'unknown' as unknown as 'mock' })]
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(false)
  })

  it('isRealSourceOffering 只认显式 real', () => {
    expect(isRealSourceOffering(REAL_OFFERING)).toBe(true)
    expect(isRealSourceOffering(MOCK_OFFERING)).toBe(false)
    expect(isRealSourceOffering(offering({ data_source: undefined as unknown as 'mock' }))).toBe(false)
  })

  it('阻止原因区分"含 Mock"与"来源未经确认"', () => {
    const form = createDefaultUserInputForm()
    expect(scheduleProvenanceBlockReason(form)).toBe(null)

    form.currentSchedule = [MOCK_OFFERING]
    expect(scheduleProvenanceBlockReason(form)).toBe(MOCK_SCHEDULE_BLOCK_REASON)

    form.currentSchedule = [offering({ data_source: undefined as unknown as 'mock' })]
    expect(scheduleProvenanceBlockReason(form)).toBe(UNVERIFIED_SCHEDULE_BLOCK_REASON)

    // 混合（real + 未知）也归入"来源未经确认"
    form.currentSchedule = [REAL_OFFERING, offering({ class_id: 'X-01', data_source: undefined as unknown as 'mock' })]
    expect(scheduleProvenanceBlockReason(form)).toBe(UNVERIFIED_SCHEDULE_BLOCK_REASON)
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

  it('来源未经确认（缺 data_source）→ fail closed 阻止提交 → fetch 0 调用', async () => {
    const unknown = offering({
      course_id: 'CSE999',
      class_id: 'CSE999-01',
      data_source: undefined as unknown as 'mock',
    })
    const { wrapper, form, fetchRealPlan, submitRealPlan, select } = mountPanel([])

    select(unknown)
    await nextTick()

    expect(form.value.currentSchedule).toHaveLength(1)
    expect(isScheduleSubmittableToRealPlanning(form.value)).toBe(false)

    // 提示是"来源未经确认"，不是"含 Mock"
    const hint = wrapper.find('[data-testid="schedule-provenance-blocked-hint"]')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain('来源未经确认')

    submitRealPlan()
    expect(fetchRealPlan).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('real 与 mock 混合 → 拒绝（不因含 real 而放行）→ fetch 0 调用', async () => {
    const { form, fetchRealPlan, submitRealPlan, select } = mountPanel([])

    select(REAL_OFFERING)
    select(MOCK_OFFERING)

    expect(form.value.currentSchedule).toHaveLength(2)
    expect(isScheduleSubmittableToRealPlanning(form.value)).toBe(false)

    submitRealPlan()
    expect(fetchRealPlan).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
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
