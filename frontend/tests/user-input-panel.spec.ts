/**
 * 用户输入区的组件测试（jsdom + @vue/test-utils，真实交互）。
 *
 * ⚠️ 不依赖真实后端：没有任何测试会命中网络。
 * `UserInputPanel` 是**受控组件**（不自己保存用户输入），
 * 因此这里用一个极小的宿主组件持有状态，模拟页面的真实用法。
 */

import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import CurrentScheduleInput from '@/components/CurrentScheduleInput.vue'
import PreferenceForm from '@/components/PreferenceForm.vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import { createDefaultUserInputForm } from '@/state/userInput'
import type { UserInputForm } from '@/state/userInput'
import type { CourseOffering } from '@/types/contracts'

const OFFERINGS: CourseOffering[] = [
  {
    course_id: 'CSE201',
    course_name: '数据结构',
    class_id: 'CSE201-01',
    semester: '2026-1',
    credit: 3,
    meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2, 3] }],
    data_source: 'mock',
  },
  {
    course_id: 'CSE209',
    course_name: '计算机网络',
    class_id: 'CSE209-02',
    semester: '2026-1',
    credit: 3,
    meetings: [],
    data_source: 'mock',
  },
]

/**
 * 宿主组件：持有表单真源，把面板的事件写回状态（与 `App.vue` 用法一致）。
 * 同时把最新状态暴露到 `wrapper.vm.form`，便于断言"编辑是否真的生效"。
 */
function mountPanel(overrides: Partial<UserInputForm> = {}) {
  const form = ref<UserInputForm>({ ...createDefaultUserInputForm(), ...overrides })

  const Host = defineComponent({
    setup() {
      return () =>
        h(UserInputPanel, {
          form: form.value,
          offerings: OFFERINGS,
          planApiEnabled: false,
          submitting: false,
          mode: 'mock',
          dataSourceLabel: 'Mock',
          'onUpdate:form': (value: UserInputForm) => {
            form.value = value
          },
        })
    },
  })

  const wrapper = mount(Host, { attachTo: document.body })
  return { wrapper, form }
}

describe('UserInputPanel 渲染', () => {
  it('渲染四个输入区块与提交区', () => {
    const { wrapper } = mountPanel()

    for (const id of [
      'uig-section-student',
      'uig-section-grades',
      'uig-section-schedule',
      'uig-section-preference',
    ]) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(true)
    }

    expect(wrapper.find('[data-testid="semester-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="max-credit-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="avoid-cross-campus-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grade-file-input"]').exists()).toBe(true)
  })

  it('明确显示当前数据模式：Mock', () => {
    const { wrapper } = mountPanel()
    expect(wrapper.find('[data-testid="data-mode-tag"]').text()).toContain('当前数据模式：Mock')
  })

  it('显示 Case A 默认的转专业上下文，且不出现学生身份信息', () => {
    const { wrapper } = mountPanel()
    expect(
      (wrapper.find('[data-testid="origin-major-input"]').element as HTMLInputElement).value,
    ).toBe('遥感科学与技术')
    expect(
      (wrapper.find('[data-testid="target-major-input"]').element as HTMLInputElement).value,
    ).toBe('网络空间安全')
    expect(wrapper.text()).not.toContain('学号')
    expect(wrapper.text()).not.toContain('姓名')
  })

  it('Real Planning 在接口未启用时按钮 disabled', () => {
    const { wrapper } = mountPanel()
    const button = wrapper.find('[data-testid="real-plan-submit"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="real-plan-disabled-hint"]').exists()).toBe(true)
  })
})

describe('学期与偏好字段可编辑', () => {
  it('semester 可修改并写回状态', async () => {
    const { wrapper, form } = mountPanel()
    const input = wrapper.find('[data-testid="semester-input"]')

    await input.setValue('2027-2')

    expect(form.value.semester).toBe('2027-2')
    expect((input.element as HTMLInputElement).value).toBe('2027-2')
  })

  it('非法学期给出提示（不自动修正）', async () => {
    const { wrapper, form } = mountPanel()
    await wrapper.find('[data-testid="semester-input"]').setValue('2027-9')
    expect(form.value.semester).toBe('2027-9')
    expect(wrapper.find('[data-testid="semester-error"]').exists()).toBe(true)
  })

  it('max_credit 可编辑并写入 preference', async () => {
    const { wrapper, form } = mountPanel()
    await wrapper.find('[data-testid="max-credit-input"]').setValue('24')
    expect(form.value.preference.maxCredit).toBe(24)
  })

  it('avoid_cross_campus 可编辑', async () => {
    const { wrapper, form } = mountPanel()
    const checkbox = wrapper.find('[data-testid="avoid-cross-campus-input"]')

    await checkbox.setValue(true)
    expect(form.value.preference.avoidCrossCampus).toBe(true)

    await checkbox.setValue(false)
    expect(form.value.preference.avoidCrossCampus).toBe(false)
  })

  it('avoid_times 可增删', async () => {
    const { wrapper, form } = mountPanel()

    await wrapper.find('[data-testid="avoid-time-add"]').trigger('click')
    expect(form.value.preference.avoidTimes).toHaveLength(1)

    await wrapper.find('[data-testid="avoid-time-add"]').trigger('click')
    expect(form.value.preference.avoidTimes).toHaveLength(2)
    expect(wrapper.findAll('[data-testid="avoid-time-row"]')).toHaveLength(2)

    await wrapper.findAll('[data-testid="avoid-time-remove"]')[0].trigger('click')
    expect(form.value.preference.avoidTimes).toHaveLength(1)
  })

  it('preferred_courses 可维护（加 / 去重 / 删）', async () => {
    const { wrapper, form } = mountPanel()

    await wrapper.find('[data-testid="preferred-course-input"]').setValue('CSE201')
    await wrapper.find('[data-testid="preferred-course-add"]').trigger('click')
    expect(form.value.preference.preferredCourses).toEqual(['CSE201'])

    // 重复添加不产生第二条
    await wrapper.find('[data-testid="preferred-course-input"]').setValue('CSE201')
    await wrapper.find('[data-testid="preferred-course-add"]').trigger('click')
    expect(form.value.preference.preferredCourses).toEqual(['CSE201'])

    await wrapper.find('[data-testid="preferred-course-input"]').setValue('MAR108')
    await wrapper.find('[data-testid="preferred-course-add"]').trigger('click')
    expect(form.value.preference.preferredCourses).toEqual(['CSE201', 'MAR108'])
    expect(wrapper.findAll('[data-testid="preferred-course-chip"]')).toHaveLength(2)

    await wrapper.findAll('.uig-chip-remove')[0].trigger('click')
    expect(form.value.preference.preferredCourses).toEqual(['MAR108'])
  })
})

describe('current_schedule 输出为 CourseOffering[]', () => {
  it('勾选教学班后 current_schedule 是 CourseOffering 数组', async () => {
    const { wrapper, form } = mountPanel()

    await wrapper.find('[data-testid="schedule-checkbox-CSE201-CSE201-01"]').setValue(true)

    expect(form.value.currentSchedule).toHaveLength(1)
    expect(form.value.currentSchedule[0]).toMatchObject({
      course_id: 'CSE201',
      class_id: 'CSE201-01',
      semester: '2026-1',
    })
    expect(Array.isArray(form.value.currentSchedule[0].meetings)).toBe(true)
  })

  it('取消勾选后 current_schedule 恢复为空', async () => {
    const { wrapper, form } = mountPanel()
    const checkbox = wrapper.find('[data-testid="schedule-checkbox-CSE201-CSE201-01"]')

    await checkbox.setValue(true)
    await checkbox.setValue(false)

    expect(form.value.currentSchedule).toEqual([])
  })

  it('空课表合法，且给出中性空状态', () => {
    const wrapper = mount(CurrentScheduleInput, {
      props: { offerings: [], selected: [], dataSourceLabel: 'Mock' },
    })
    expect(wrapper.find('[data-testid="schedule-empty"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前课表可以留空继续')
  })

  it('meetings=[] 的教学班沿用 DG-07D 中性文案，不推断无冲突', () => {
    const wrapper = mount(CurrentScheduleInput, {
      props: { offerings: OFFERINGS, selected: [], dataSourceLabel: 'Mock' },
    })
    expect(wrapper.text()).toContain('当前数据中无排课信息')
    for (const forbidden of ['无冲突', '无需上课', '异步课程', '尚未排课']) {
      expect(wrapper.text()).not.toContain(forbidden)
    }
  })
})

describe('XLSX 文件选择门', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('只接受 .xlsx：非 xlsx 文件被拒绝并提示', async () => {
    const { wrapper } = mountPanel()
    const input = wrapper.find('[data-testid="grade-file-input"]')

    // accept 属性声明只接受 .xlsx
    expect(input.attributes('accept')).toBe('.xlsx')

    const csv = new File(['a,b'], 'grades.csv', { type: 'text/csv' })
    Object.defineProperty(input.element, 'files', { value: [csv], configurable: true })
    await input.trigger('change')

    expect(wrapper.find('[data-testid="grade-file-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grade-file-name"]').exists()).toBe(false)
  })

  it('选择 .xlsx 只保存文件名，不上传、不解析、不生成 MakeupTask', async () => {
    const { wrapper } = mountPanel()
    const input = wrapper.find('[data-testid="grade-file-input"]')

    const xlsx = new File(['binary'], 'completed.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', { value: [xlsx], configurable: true })
    await input.trigger('change')

    expect(wrapper.find('[data-testid="grade-file-name"]').text()).toContain('completed.xlsx')

    // 明确显示：分析将在真实 Curriculum User Input API 接入后启用
    expect(wrapper.find('[data-testid="grade-file-pending-notice"]').text()).toContain(
      '成绩文件上传分析将在真实 Curriculum User Input API 接入后启用',
    )
    // 明确声明不会在前端生成补修任务
    expect(wrapper.find('[data-testid="grade-file-no-makeup-notice"]').text()).toContain('MakeupTask')

    // 选择文件不产生任何网络请求
    expect(fetch).not.toHaveBeenCalled()

    // 也不会冒出一个补修任务清单
    expect(wrapper.text()).not.toContain('需要补修 (')

    // 清除选择
    await wrapper.find('[data-testid="grade-file-clear"]').trigger('click')
    expect(wrapper.find('[data-testid="grade-file-name"]').exists()).toBe(false)
  })
})

describe('PreferenceForm 与只读展示分离', () => {
  it('表单只编辑 5 个公共字段，不新增字段名', () => {
    const wrapper = mount(PreferenceForm, {
      props: { form: createDefaultUserInputForm() },
    })
    const text = wrapper.text()
    for (const field of [
      'max_credit',
      'avoid_cross_campus',
      'preferred_courses',
      'avoid_times',
      'notes',
    ]) {
      expect(text).toContain(field)
    }
  })
})
