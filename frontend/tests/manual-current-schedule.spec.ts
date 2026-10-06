/**
 * 当前课表**手工结构化录入**测试（Case A 今晚可用路径）。
 *
 * 覆盖：
 * - 结构化字段 → 公共 `CourseOffering`（⛔ 不要求用户写裸 JSON）；
 * - 周次文本展开（`1-16` / `1-8,10` / 中文标点），非法输入整条拒绝；
 * - 缺失 / 非法字段一律**不产出对象、不修改课表**（全有或全无）；
 * - 同一 identity / 同一课程重复加入被明确阻止（⛔ 不静默去重、⛔ 不静默取一个）；
 * - 默认 `data_source = mock` ⇒ provenance 门禁**仍然阻止**提交 Real Planning
 *   （⛔ 手工录入不得冒充学校系统来源）；
 * - 组件层面：新增行 / 填表 / 加入课表 / 移除课表 的真实交互。
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import { MANUAL_SCHEDULE_PROVENANCE, MANUAL_SCHEDULE_PROVENANCE_LABEL } from '@/config'
import {
  addManualScheduleEntry,
  addManualScheduleEntryToSchedule,
  createDefaultUserInputForm,
  removeCurrentScheduleOffering,
  scheduleProvenanceBlockReason,
  updateManualScheduleEntry,
} from '@/state/userInput'
import {
  buildOfferingFromManualEntry,
  createManualScheduleEntry,
  parseWeeksInput,
} from '@/state/manualSchedule'
import type { UserInputForm } from '@/state/userInput'
import type { CourseOffering } from '@/types/contracts'

function filledEntry(overrides: Partial<ReturnType<typeof createManualScheduleEntry>> = {}) {
  return {
    ...createManualScheduleEntry('2026-1'),
    courseId: 'SEC1001',
    courseName: '信息安全导论',
    classId: '01',
    weekday: 2,
    startSection: 3,
    endSection: 4,
    weeksText: '1-16',
    campus: '深圳校区',
    classroom: '教学楼A305',
    ...overrides,
  }
}

describe('周次文本展开（纯函数）', () => {
  it('展开区间、单周与混合写法', () => {
    expect(parseWeeksInput('1-3')).toEqual([1, 2, 3])
    expect(parseWeeksInput('1,3,5')).toEqual([1, 3, 5])
    expect(parseWeeksInput('1-3,6,8-9')).toEqual([1, 2, 3, 6, 8, 9])
    // 升序去重：重复与乱序都不影响结果
    expect(parseWeeksInput('3-5,1-2,3')).toEqual([1, 2, 3, 4, 5])
  })

  it('接受"周"字与中文标点，但不接受其它修饰词', () => {
    expect(parseWeeksInput('1-16周')).toEqual(Array.from({ length: 16 }, (_, i) => i + 1))
    expect(parseWeeksInput('1，3、5周')).toEqual([1, 3, 5])
    // ⛔ 不解释单双周：未确认的写法一律拒绝，不猜测
    expect(parseWeeksInput('1-16周(单周)')).toBeNull()
  })

  it('非法输入整条拒绝（不做部分接受）', () => {
    for (const value of ['', '   ', '0', 'abc', '1-', '-3', '5-3', '1,,3', '1-100', '99']) {
      expect(parseWeeksInput(value), value).toBeNull()
    }
  })
})

describe('结构化字段 → 公共 CourseOffering', () => {
  it('构造出的对象严格是公共 Schema 的形状', () => {
    const { offering } = buildOfferingFromManualEntry(
      filledEntry(),
      MANUAL_SCHEDULE_PROVENANCE,
    )

    expect(offering).not.toBeNull()
    expect(Object.keys(offering!).sort()).toEqual(
      ['class_id', 'course_id', 'course_name', 'data_source', 'meetings', 'semester', 'source'].sort(),
    )
    expect(offering!.meetings).toHaveLength(1)
    expect(offering!.meetings[0]).toEqual({
      weekday: 2,
      start_section: 3,
      end_section: 4,
      weeks: Array.from({ length: 16 }, (_, i) => i + 1),
      campus: '深圳校区',
      classroom: '教学楼A305',
    })
  })

  it('可留空的校区 / 教室归一为 null，不伪造取值', () => {
    const { offering } = buildOfferingFromManualEntry(
      filledEntry({ campus: '', classroom: '  ' }),
      MANUAL_SCHEDULE_PROVENANCE,
    )
    expect(offering!.meetings[0].campus).toBeNull()
    expect(offering!.meetings[0].classroom).toBeNull()
  })

  it('默认 data_source 是 mock（手工录入不冒充学校系统来源）', () => {
    expect(MANUAL_SCHEDULE_PROVENANCE).toBe('mock')
    const { offering } = buildOfferingFromManualEntry(filledEntry(), MANUAL_SCHEDULE_PROVENANCE)
    expect(offering!.data_source).toBe('mock')
    expect(MANUAL_SCHEDULE_PROVENANCE_LABEL).toContain('不能提交 Real Planning')
  })

  it('字段缺失 / 非法 ⇒ 不产出对象，且逐字段报错', () => {
    const cases: Array<[string, Partial<ReturnType<typeof createManualScheduleEntry>>, string]> = [
      ['courseId', { courseId: '  ' }, 'courseId'],
      ['courseName', { courseName: '' }, 'courseName'],
      ['classId', { classId: '' }, 'classId'],
      ['semester', { semester: '2026' }, 'semester'],
      ['weekday', { weekday: null }, 'weekday'],
      ['weekday', { weekday: 9 }, 'weekday'],
      ['sections', { startSection: null }, 'sections'],
      ['sections', { startSection: 5, endSection: 4 }, 'sections'],
      ['weeks', { weeksText: '' }, 'weeks'],
      ['weeks', { weeksText: '1-99' }, 'weeks'],
    ]

    for (const [label, override, expectedField] of cases) {
      const { offering, errors } = buildOfferingFromManualEntry(
        filledEntry(override),
        MANUAL_SCHEDULE_PROVENANCE,
      )
      expect(offering, label).toBeNull()
      expect(errors.map((item) => item.field), label).toContain(expectedField)
    }
  })
})

describe('加入当前课表：全有或全无', () => {
  it('成功加入一个合法条目', () => {
    const result = addManualScheduleEntryToSchedule([], filledEntry())

    expect(result.added).toBe(true)
    expect(result.error).toBe('')
    expect(result.currentSchedule).toHaveLength(1)
    expect(result.currentSchedule[0].course_id).toBe('SEC1001')
  })

  it('非法条目 ⇒ 课表**不被修改**，并给出字段级原因', () => {
    const before: CourseOffering[] = []
    const result = addManualScheduleEntryToSchedule(before, filledEntry({ weeksText: 'abc' }))

    expect(result.added).toBe(false)
    expect(result.currentSchedule).toEqual([])
    expect(result.error).toContain('周次')
  })

  it('同一 identity（学期 + 课程号 + 教学班号）重复 ⇒ 明确拒绝，不静默去重', () => {
    const first = addManualScheduleEntryToSchedule([], filledEntry())
    const second = addManualScheduleEntryToSchedule(first.currentSchedule, filledEntry())

    expect(second.added).toBe(false)
    expect(second.currentSchedule).toHaveLength(1)
    expect(second.error).toContain('已经在当前课表中')
  })

  it('同一课程的不同教学班 ⇒ 明确拒绝（Planner 要求同一课程只有一个已选班）', () => {
    const first = addManualScheduleEntryToSchedule([], filledEntry())
    const second = addManualScheduleEntryToSchedule(
      first.currentSchedule,
      filledEntry({ classId: '02' }),
    )

    expect(second.added).toBe(false)
    expect(second.currentSchedule).toHaveLength(1)
    expect(second.error).toContain('只能有一个已选班')
  })

  it('移除已加入的条目', () => {
    const { currentSchedule } = addManualScheduleEntryToSchedule([], filledEntry())
    expect(removeCurrentScheduleOffering(currentSchedule, currentSchedule[0])).toEqual([])
  })
})

describe('手工录入行状态操作', () => {
  it('新增行带入当前学期，其余字段为空', () => {
    const entries = addManualScheduleEntry([], '2026-1')
    expect(entries).toHaveLength(1)
    expect(entries[0].semester).toBe('2026-1')
    expect(entries[0].courseId).toBe('')
    expect(entries[0].weekday).toBeNull()
  })

  it('更新单行字段不影响其它行', () => {
    const entries = addManualScheduleEntry(addManualScheduleEntry([], '2026-1'), '2026-1')
    const updated = updateManualScheduleEntry(entries, entries[0].key, { courseId: 'SEC1001' })

    expect(updated[0].courseId).toBe('SEC1001')
    expect(updated[1].courseId).toBe('')
    expect(entries[0].courseId).toBe('')
  })
})

describe('provenance：手工录入默认不得提交 Real Planning', () => {
  it('默认创建的课表为空 ⇒ 门禁放行；加入手工条目 ⇒ 门禁阻止', () => {
    const form = createDefaultUserInputForm()
    expect(scheduleProvenanceBlockReason(form)).toBeNull()

    const result = addManualScheduleEntryToSchedule([], filledEntry())
    form.currentSchedule = result.currentSchedule

    // 默认 data_source = mock ⇒ 如实阻止（⛔ 不静默放行）
    expect(scheduleProvenanceBlockReason(form)).toContain('Mock')
  })
})

describe('组件交互：不需要用户写 JSON', () => {
  function mountPanel() {
    const form = ref<UserInputForm>(createDefaultUserInputForm())
    const Host = defineComponent({
      setup() {
        return () =>
          h(UserInputPanel, {
            form: form.value,
            offerings: [],
            planApiEnabled: false,
            submitting: false,
            mode: 'mock',
            scheduleBlockReason: scheduleProvenanceBlockReason(form.value),
            'onUpdate:form': (value: UserInputForm) => {
              form.value = value
            },
          })
      },
    })
    return { wrapper: mount(Host), form }
  }

  it('空列表时给出手工录入入口，并如实标注来源', async () => {
    const { wrapper } = mountPanel()
    expect(wrapper.find('[data-testid="manual-schedule-add-row"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="manual-schedule-provenance"]').text()).toContain('手工录入')
  })

  it('新增行 → 填表 → 加入当前课表 → 出现在已选列表', async () => {
    const { wrapper, form } = mountPanel()

    await wrapper.find('[data-testid="manual-schedule-add-row"]').trigger('click')
    const key = form.value.manualScheduleEntries[0].key

    await wrapper.find(`[data-testid="manual-course-id-${key}"]`).setValue('SEC1001')
    await wrapper.find(`[data-testid="manual-course-name-${key}"]`).setValue('信息安全导论')
    await wrapper.find(`[data-testid="manual-class-id-${key}"]`).setValue('01')
    await wrapper.find(`[data-testid="manual-weekday-${key}"]`).setValue('2')
    await wrapper.find(`[data-testid="manual-start-section-${key}"]`).setValue('3')
    await wrapper.find(`[data-testid="manual-end-section-${key}"]`).setValue('4')
    await wrapper.find(`[data-testid="manual-weeks-${key}"]`).setValue('1-16')

    await wrapper.find(`[data-testid="manual-add-${key}"]`).trigger('click')

    expect(form.value.currentSchedule).toHaveLength(1)
    expect(form.value.currentSchedule[0]).toMatchObject({
      course_id: 'SEC1001',
      course_name: '信息安全导论',
      class_id: '01',
      semester: '2026-1',
      data_source: 'mock',
    })
    expect(form.value.currentSchedule[0].meetings[0].weeks).toHaveLength(16)
    expect(wrapper.find('[data-testid="manual-schedule-added"]').text()).toContain('SEC1001')
  })

  it('字段不全时点加入 ⇒ 明确错误提示，课表不变', async () => {
    const { wrapper, form } = mountPanel()

    await wrapper.find('[data-testid="manual-schedule-add-row"]').trigger('click')
    const key = form.value.manualScheduleEntries[0].key

    // 只填课程号，其余留空
    await wrapper.find(`[data-testid="manual-course-id-${key}"]`).setValue('SEC1001')
    await wrapper.find(`[data-testid="manual-add-${key}"]`).trigger('click')

    expect(form.value.currentSchedule).toEqual([])
    expect(wrapper.find(`[data-testid="manual-error-${key}"]`).text()).toContain('课程名称')
  })

  it('从已选列表移除条目', async () => {
    const { wrapper, form } = mountPanel()

    await wrapper.find('[data-testid="manual-schedule-add-row"]').trigger('click')
    const key = form.value.manualScheduleEntries[0].key
    await wrapper.find(`[data-testid="manual-course-id-${key}"]`).setValue('SEC1001')
    await wrapper.find(`[data-testid="manual-course-name-${key}"]`).setValue('信息安全导论')
    await wrapper.find(`[data-testid="manual-class-id-${key}"]`).setValue('01')
    await wrapper.find(`[data-testid="manual-weekday-${key}"]`).setValue('2')
    await wrapper.find(`[data-testid="manual-start-section-${key}"]`).setValue('3')
    await wrapper.find(`[data-testid="manual-end-section-${key}"]`).setValue('4')
    await wrapper.find(`[data-testid="manual-weeks-${key}"]`).setValue('1-16')
    await wrapper.find(`[data-testid="manual-add-${key}"]`).trigger('click')
    expect(form.value.currentSchedule).toHaveLength(1)

    await wrapper.find('[data-testid="manual-schedule-remove-selected-SEC1001-01"]').trigger('click')
    expect(form.value.currentSchedule).toEqual([])
  })
})
