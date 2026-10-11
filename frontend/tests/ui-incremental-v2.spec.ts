/**
 * 本轮两处新增功能的测试：
 *   A. 当前课表模块的**课表截图上传 + 待识别**
 *   B. 「上传成绩单」前的**原专业 / 目标专业下拉框**（仅两个样本专业）
 *
 * ⚠️ 重点覆盖：正常路径、空输入、错误输入、边界与主要失败路径（AGENTS.md §10）。
 * ⛔ 本文件不允许出现任何"识别结果"断言 —— 因为本轮**没有**识别服务。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import CurrentScheduleInput from '@/components/CurrentScheduleInput.vue'
import StudentContextForm from '@/components/StudentContextForm.vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import { MAJOR_OPTIONS, SAMPLE_MAJOR_OPTIONS } from '@/config'
import { createDefaultUserInputForm } from '@/state/userInput'
import type { UserInputForm } from '@/state/userInput'
import type { CourseOffering } from '@/types/contracts'

const OFFERINGS: CourseOffering[] = [
  {
    semester: '2026-1',
    course_id: '62001001',
    course_name: '离散数学',
    class_id: '62001001202601',
    credits: 3,
    teachers: ['何示例'],
    meetings: [
      { day_of_week: 1, start_period: 1, end_period: 2, weeks: '1-16', campus: '东校园', room: '东D101' },
    ],
    capacity: 60,
    enrolled: 0,
    data_source: 'mock',
  },
  {
    semester: '2026-1',
    course_id: '62001002',
    course_name: '数据结构与算法',
    class_id: '62001002202601',
    credits: 4,
    teachers: ['李示例'],
    meetings: [
      { day_of_week: 3, start_period: 3, end_period: 4, weeks: '1-16', campus: '东校园', room: '东D201' },
    ],
    capacity: 60,
    enrolled: 0,
    data_source: 'mock',
  },
]

/** 造一个**合法的 PNG 文件**（用最小 PNG 头，jsdom 不校验内容）。 */
function makePng(name = 'schedule.png', bytes = 1024): File {
  const file = new File([new Uint8Array(bytes)], name, { type: 'image/png' })
  Object.defineProperty(file, 'size', { value: bytes, configurable: true })
  return file
}

function makeFile(name: string, type: string, size: number): File {
  const file = new File([new Uint8Array(1)], name, { type })
  Object.defineProperty(file, 'size', { value: size, configurable: true })
  return file
}

async function chooseShot(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.find('[data-testid="schedule-shot-input"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  // jsdom 的 `input.value` 可写；组件内部会把它清空
  Object.defineProperty(input.element, 'value', { value: '', writable: true, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

function mountSchedule(selected: CourseOffering[] = []) {
  return mount(CurrentScheduleInput, {
    props: { offerings: OFFERINGS, selected, dataSourceLabel: 'Mock 演示通道' },
  })
}

afterEach(() => {
  // `URL.createObjectURL` 在 jsdom 里可能不存在，统一兜底
  if (!('createObjectURL' in URL)) {
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
  }
})

/* ------------------------------------------------------------------ *
 * A. 课表截图上传 + 待识别
 * ------------------------------------------------------------------ */

describe('A 课表截图：上传 / 预览 / 待识别', () => {
  it('未选择截图时显示提示，且⛔ 不显示预览与状态', () => {
    const wrapper = mountSchedule()
    expect(wrapper.find('[data-testid="schedule-shot"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('尚未选择截图')
    expect(wrapper.find('[data-testid="schedule-shot-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-shot-status"]').exists()).toBe(false)
  })

  it('选择合法 PNG 后：显示文件名、大小、预览与「待识别」状态', async () => {
    if (!('createObjectURL' in URL)) {
      Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', configurable: true })
      Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
    }
    const wrapper = mountSchedule()
    await chooseShot(wrapper, makePng('my-schedule.png', 2048))

    const name = wrapper.find('[data-testid="schedule-shot-name"]')
    expect(name.exists()).toBe(true)
    expect(name.text()).toContain('my-schedule.png')
    expect(name.text()).toContain('未上传、未解析')

    expect(wrapper.find('[data-testid="schedule-shot-preview"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-shot-preview"] img').exists()).toBe(true)

    const status = wrapper.find('[data-testid="schedule-shot-status"]')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('待识别')
    expect(status.text()).toContain('尚未接入图片识别服务')
  })

  it('⛔ 绝不显示任何"识别结果"或据称来自截图的课程', async () => {
    if (!('createObjectURL' in URL)) {
      Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', configurable: true })
      Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
    }
    const wrapper = mountSchedule()
    await chooseShot(wrapper, makePng())

    const text = wrapper.text()
    for (const forbidden of ['识别成功', '已识别出', '解析完成', '识别结果：']) {
      expect(text, `出现了不应有的识别结论：${forbidden}`).not.toContain(forbidden)
    }
    // 选截图⛔ 不会自动勾选任何教学班
    expect(wrapper.find('[data-testid="schedule-summary"]').text()).toContain('已选 0 个教学班')
  })

  it('错误输入：非图片类型被拒绝，且不产生预览与状态', async () => {
    const wrapper = mountSchedule()
    await chooseShot(wrapper, makeFile('grades.xlsx', 'application/vnd.ms-excel', 100))

    const error = wrapper.find('[data-testid="schedule-shot-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('仅支持 PNG / JPEG / WebP')
    expect(wrapper.find('[data-testid="schedule-shot-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-shot-status"]').exists()).toBe(false)
  })

  it('边界：超过 8 MiB 的图片被拒绝', async () => {
    const wrapper = mountSchedule()
    await chooseShot(wrapper, makeFile('huge.png', 'image/png', 9 * 1024 * 1024))
    const error = wrapper.find('[data-testid="schedule-shot-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('8 MiB')
  })

  it('可以移除已选截图，回到初始状态', async () => {
    if (!('createObjectURL' in URL)) {
      Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', configurable: true })
      Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
    }
    const wrapper = mountSchedule()
    await chooseShot(wrapper, makePng())
    expect(wrapper.find('[data-testid="schedule-shot-status"]').exists()).toBe(true)

    await wrapper.find('[data-testid="schedule-shot-clear"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="schedule-shot-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-shot-status"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('尚未选择截图')
  })

  it('手动勾选仍然可用（⛔ 未被截图功能削弱）', async () => {
    const wrapper = mountSchedule()
    expect(wrapper.findAll('[data-testid="schedule-option"]')).toHaveLength(2)
    await wrapper.find('[data-testid="schedule-checkbox-62001001-62001001202601"]').trigger('change')
    expect(wrapper.emitted('toggle')).toBeTruthy()
    expect(wrapper.find('[data-testid="schedule-manual-heading"]').exists()).toBe(true)
  })

  it('空输入：没有教学班时仍可上传截图（课表允许为空）', async () => {
    const wrapper = mount(CurrentScheduleInput, {
      props: { offerings: [], selected: [], dataSourceLabel: 'Mock 演示通道' },
    })
    expect(wrapper.find('[data-testid="schedule-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-shot-input"]').exists()).toBe(true)
  })
})

/* ------------------------------------------------------------------ *
 * B. 原专业 / 目标专业下拉框
 * ------------------------------------------------------------------ */

describe('B 原专业 / 目标专业下拉框（仅两个样本专业）', () => {
  function mountPanel(form: UserInputForm = createDefaultUserInputForm()) {
    return mount(UserInputPanel, {
      props: {
        form,
        offerings: OFFERINGS,
        planApiEnabled: false,
        submitting: false,
        mode: 'mock' as const,
        dataSourceLabel: 'Mock 演示通道',
      },
    })
  }

  it('两个专业都是 <select>，且只提供两个样本专业', () => {
    const wrapper = mountPanel()

    for (const testid of ['origin-major-input', 'target-major-input']) {
      const el = wrapper.find(`[data-testid="${testid}"]`)
      expect(el.exists(), `${testid} 不存在`).toBe(true)
      expect(el.element.tagName).toBe('SELECT')

      const values = el.findAll('option').map((option) => option.attributes('value'))
      expect(values).toEqual(['网络空间安全', '遥感科学与技术'])
      expect(el.findAll('option')).toHaveLength(2)
    }
  })

  it('下拉框位于「上传成绩单」区域之内，且在成绩文件之前', () => {
    const wrapper = mountPanel()
    const html = wrapper.html()
    const sectionIndex = html.indexOf('uig-section-grades')
    const selectsIndex = html.indexOf('grade-major-selects')
    const gradeInputIndex = html.indexOf('grade-file-input')

    expect(sectionIndex).toBeGreaterThan(-1)
    expect(selectsIndex).toBeGreaterThan(sectionIndex)
    // 「在上传成绩单区域前」= 同一区块内、成绩文件输入之前
    expect(gradeInputIndex).toBeGreaterThan(selectsIndex)
  })

  it('默认值与旧版 Case A 上下文一致', () => {
    const wrapper = mountPanel()
    expect(
      (wrapper.find('[data-testid="origin-major-input"]').element as HTMLSelectElement).value,
    ).toBe('遥感科学与技术')
    expect(
      (wrapper.find('[data-testid="target-major-input"]').element as HTMLSelectElement).value,
    ).toBe('网络空间安全')
  })

  it('切换原专业会发出 update:form，且只改该字段', async () => {
    const form = createDefaultUserInputForm()
    const wrapper = mountPanel(form)
    await wrapper.find('[data-testid="origin-major-input"]').setValue('网络空间安全')

    const emitted = wrapper.emitted('update:form')
    expect(emitted).toBeTruthy()
    const next = emitted![0]![0] as UserInputForm
    expect(next.studentContext.originMajor).toBe('网络空间安全')
    // ⛔ 其它字段不受影响
    expect(next.studentContext.targetMajor).toBe(form.studentContext.targetMajor)
    expect(next.studentContext.transferTerm).toBe(form.studentContext.transferTerm)
    expect(next.semester).toBe(form.semester)
  })

  it('切换目标专业会发出 update:form', async () => {
    const wrapper = mountPanel()
    await wrapper.find('[data-testid="target-major-input"]').setValue('遥感科学与技术')
    const next = wrapper.emitted('update:form')![0]![0] as UserInputForm
    expect(next.studentContext.targetMajor).toBe('遥感科学与技术')
  })

  it('范围提示如实说明只有两个样本专业', () => {
    const wrapper = mountPanel()
    const note = wrapper.find('[data-testid="grade-major-scope-note"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('两个样本专业')
    expect(note.text()).toContain('后续增量补充')
  })

  it('⛔ 组件内不存在按专业名分叉的判断分支', async () => {
    // 真正读源码做静态检查：专业名⛔ 不得出现在条件表达式里。
    // ⚠️ 必须先剥掉注释与文档字符串 —— 否则"禁止这样写"的说明本身会被误判
    //    （`StudentContextForm.vue` 的文档里就有 `if (major === '网络空间安全')` 的反例说明）。
    const fs = await import('node:fs/promises')
    const path = await import('node:path')
    const files = ['UserInputPanel.vue', 'StudentContextForm.vue', 'CurrentScheduleInput.vue']

    const stripComments = (source: string): string =>
      source
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/(^|[^:])\/\/[^\n]*/g, '$1')

    for (const name of files) {
      const file = path.resolve(process.cwd(), 'src/components', name)
      const code = stripComments(await fs.readFile(file, 'utf-8'))
      for (const major of ['网络空间安全', '遥感科学与技术']) {
        const conditional = new RegExp(
          `(if\\s*\\([^)]*${major}|${major}\\s*===\\s*['"\`]|===\\s*['"\`]${major})`,
        )
        expect(
          conditional.test(code),
          `${name} 出现按专业名分叉的判断：${major}`,
        ).toBe(false)
      }
    }
  })

  it('既有候选项层 MAJOR_OPTIONS 未被改动（⛔ 不破坏旧版自由输入）', () => {
    expect(MAJOR_OPTIONS.length).toBeGreaterThanOrEqual(6)
    expect(MAJOR_OPTIONS.map((m) => m.value)).toContain('遥感科学与技术')
    expect(MAJOR_OPTIONS.map((m) => m.value)).toContain('网络空间安全')
  })

  it('StudentContextForm 仍保留目标学期与转入学期（⛔ 未误删）', () => {
    const wrapper = mount(StudentContextForm, {
      props: {
        semester: '2026-1',
        context: createDefaultUserInputForm().studentContext,
        majors: MAJOR_OPTIONS,
      },
    })
    expect(wrapper.find('[data-testid="semester-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="transfer-term-input"]').exists()).toBe(true)
    // 专业字段已移出本组件（改由 ② 区块的下拉框承担）
    expect(wrapper.find('[data-testid="origin-major-input"]').exists()).toBe(false)
  })

  it('SAMPLE_MAJOR_OPTIONS 恰好是两个样本专业', () => {
    expect(SAMPLE_MAJOR_OPTIONS.map((m) => m.value)).toEqual([
      '网络空间安全',
      '遥感科学与技术',
    ])
  })
})
