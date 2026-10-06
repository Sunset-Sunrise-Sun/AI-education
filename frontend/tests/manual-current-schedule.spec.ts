/**
 * 当前课表**手工结构化录入** + **用户级 attestation**测试（Case A 今晚可用路径）。
 *
 * 覆盖：
 * - 结构化字段 → 公共 `CourseOffering`（⛔ 不要求用户写裸 JSON）；
 * - 周次文本展开（`1-16` / `1-8,10` / 中文标点），非法输入整条拒绝；
 * - 缺失 / 非法字段一律**不产出对象、不修改课表**（全有或全无）；
 * - 同一 identity / 同一课程重复加入被明确阻止（⛔ 不静默去重、⛔ 不静默取一个）；
 * - **attestation 门禁**：默认（未勾选）⇒ `data_source = mock` ⇒ 阻断提交 Real Planning；
 *   用户显式勾选 ⇒ 允许进入 plan 请求；取消勾选 ⇒ 立即重新阻断；
 *   课表被改动 ⇒ 既有确认作废，必须重新确认；
 * - 组件层面：新增行 / 填表 / 加入课表 / 移除课表 / 勾选确认 的真实交互。
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import UserInputPanel from '@/components/UserInputPanel.vue'
import { MANUAL_SCHEDULE_ENTRY_LABEL } from '@/config'
import {
  MANUAL_SCHEDULE_ATTESTATION_NOTE,
  UNATTESTED_MANUAL_SCHEDULE_BLOCK_REASON,
  addManualScheduleEntry,
  addManualScheduleEntryToSchedule,
  applyManualAttestation,
  buildRealPlanRequest,
  createDefaultUserInputForm,
  evaluatePlanSubmission,
  invalidateManualAttestation,
  isScheduleSubmittableToRealPlanning,
  removeCurrentScheduleOffering,
  scheduleProvenanceBlockReason,
  updateManualScheduleEntry,
} from '@/state/userInput'
import {
  MANUAL_SCHEDULE_SOURCE,
  buildOfferingFromManualEntry,
  createManualScheduleEntry,
  isManualScheduleOffering,
  parseWeeksInput,
  setManualScheduleProvenance,
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
    const { offering } = buildOfferingFromManualEntry(filledEntry())

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
    const { offering } = buildOfferingFromManualEntry(filledEntry({ campus: '', classroom: '  ' }))
    expect(offering!.meetings[0].campus).toBeNull()
    expect(offering!.meetings[0].classroom).toBeNull()
  })

  it('构造出的条目 data_source 恒为 mock，且 source 如实标明是手工录入', () => {
    const { offering } = buildOfferingFromManualEntry(filledEntry())
    // ⛔ 不冒充学校系统来源：既不是 real，来源字符串也明说是手工录入。
    expect(offering!.data_source).toBe('mock')
    expect(offering!.source).toBe(MANUAL_SCHEDULE_SOURCE)
    expect(MANUAL_SCHEDULE_ENTRY_LABEL).toContain('未经学校系统核验')
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
      const { offering, errors } = buildOfferingFromManualEntry(filledEntry(override))
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

describe('attestation：默认 fail-closed，只有用户显式确认才放行', () => {
  /** 造一个"含 1 个手工条目"的表单（默认未确认）。 */
  function formWithManualEntry(): UserInputForm {
    const form = createDefaultUserInputForm()
    const result = addManualScheduleEntryToSchedule([], filledEntry())
    expect(result.added).toBe(true)
    form.currentSchedule = result.currentSchedule
    return form
  }

  it('1) 默认（未确认）⇒ 阻止提交，evaluatePlanSubmission 不允许、原因明确', () => {
    const form = formWithManualEntry()

    expect(form.manualAttestation.attested).toBe(false)
    expect(form.currentSchedule[0].data_source).toBe('mock')
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(false)
    expect(scheduleProvenanceBlockReason(form)).toBe(UNATTESTED_MANUAL_SCHEDULE_BLOCK_REASON)
    expect(evaluatePlanSubmission(form).allowed).toBe(false)
    // ⛔ 原因必须说清"本人填写 / 非学校来源"
    expect(UNATTESTED_MANUAL_SCHEDULE_BLOCK_REASON).toContain('本人填写')
    expect(UNATTESTED_MANUAL_SCHEDULE_BLOCK_REASON).toContain('不是学校系统来源')
  })

  it('2) 用户显式确认 ⇒ 手工条目切到 real 且门禁放行', () => {
    const form = applyManualAttestation(formWithManualEntry(), true)

    expect(form.manualAttestation.attested).toBe(true)
    expect(form.manualAttestation.confirmedAt).not.toBeNull()
    expect(form.currentSchedule[0].data_source).toBe('real')
    // ⛔ source 仍然如实标明是手工录入（不是学校来源伪装）
    expect(form.currentSchedule[0].source).toBe(MANUAL_SCHEDULE_SOURCE)
    expect(isScheduleSubmittableToRealPlanning(form)).toBe(true)
    expect(scheduleProvenanceBlockReason(form)).toBeNull()
    expect(evaluatePlanSubmission(form).allowed).toBe(true)
  })

  it('3) 撤销确认 ⇒ 立即重新阻断', () => {
    const attested = applyManualAttestation(formWithManualEntry(), true)
    expect(evaluatePlanSubmission(attested).allowed).toBe(true)

    const revoked = applyManualAttestation(attested, false)
    expect(revoked.manualAttestation.attested).toBe(false)
    expect(revoked.manualAttestation.confirmedAt).toBeNull()
    expect(revoked.currentSchedule[0].data_source).toBe('mock')
    expect(evaluatePlanSubmission(revoked).allowed).toBe(false)
  })

  it('4) 确认后课表被改动 ⇒ 确认作废，必须重新确认', () => {
    const attested = applyManualAttestation(formWithManualEntry(), true)
    expect(evaluatePlanSubmission(attested).allowed).toBe(true)

    // 加入第二条手工条目
    const secondEntry = filledEntry({ courseId: 'SEC1002', classId: '02' })
    const added = addManualScheduleEntryToSchedule(attested.currentSchedule, secondEntry)
    expect(added.added).toBe(true)
    const { form, invalidated } = invalidateManualAttestation(attested, added.currentSchedule)

    expect(invalidated).toBe(true)
    expect(form.manualAttestation.attested).toBe(false)
    // "已作废"是**持续**状态：用户还会继续编辑，提示不消失
    expect(form.manualAttestation.invalidated).toBe(true)
    // 新加入的条目必须是 mock，且旧条目也被切回 mock（不能残留 real）
    expect(form.currentSchedule.map((item) => item.data_source)).toEqual(['mock', 'mock'])
    expect(evaluatePlanSubmission(form).allowed).toBe(false)

    // 重新确认后恢复，且"已作废"提示清零
    const reconfirmed = applyManualAttestation(form, true)
    expect(reconfirmed.manualAttestation.invalidated).toBe(false)
    expect(evaluatePlanSubmission(reconfirmed).allowed).toBe(true)
  })

  it('4b) 移除条目同样作废确认', () => {
    const attested = applyManualAttestation(formWithManualEntry(), true)
    const removed = removeCurrentScheduleOffering(
      attested.currentSchedule,
      attested.currentSchedule[0],
    )
    const { form, invalidated } = invalidateManualAttestation(attested, removed)

    expect(invalidated).toBe(true)
    expect(form.currentSchedule).toEqual([])
    expect(form.manualAttestation.attested).toBe(false)
    expect(form.manualAttestation.invalidated).toBe(true)
  })

  it('确认不会"顺带"改动条目本身：除 data_source 外逐字段相同', () => {
    const form = formWithManualEntry()
    const before = form.currentSchedule[0]
    const attested = applyManualAttestation(form, true)
    const after = attested.currentSchedule[0]

    expect(after).toEqual({ ...before, data_source: 'real' })
    expect(after.meetings).toEqual(before.meetings)
    expect(after.course_id).toBe(before.course_id)
    expect(after.class_id).toBe(before.class_id)
  })

  it('只有手工录入条目被切换：其它来源的条目原样保留', () => {
    const real: CourseOffering = {
      course_id: 'CSE202',
      course_name: '学校来源示例课程',
      class_id: 'CSE202-01',
      semester: '2026-1',
      meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2] }],
      data_source: 'real',
      source: 'capture://sysu/2026-1/campus/5062201',
    }
    const schedule = [real, buildOfferingFromManualEntry(filledEntry()).offering!]

    const toMock = setManualScheduleProvenance(schedule, 'mock')
    expect(toMock[0]).toBe(real) // 未被改写（同一引用）
    expect(toMock[1].data_source).toBe('mock')

    const toReal = setManualScheduleProvenance(schedule, 'real')
    expect(toReal[0]).toBe(real)
    expect(toReal[1].data_source).toBe('real')
    expect(isManualScheduleOffering(toReal[1])).toBe(true)
    expect(isManualScheduleOffering(real)).toBe(false)
  })

  it('6) 手工课表不进入 Course Data acceptance/store（前端侧无此通路）', () => {
    // ⛔ 前端的 attestation 只改 `current_schedule` 条目的 data_source；
    //    它不调用任何后端导入/接受接口。这里锁住"来源标记"这一唯一载体。
    const attested = applyManualAttestation(formWithManualEntry(), true)
    expect(Object.keys(attested.currentSchedule[0]).sort()).toEqual(
      ['class_id', 'course_id', 'course_name', 'data_source', 'meetings', 'semester', 'source'].sort(),
    )
    // 确认状态本身不进入请求体（见下方 plan request 断言）
    expect(attested.manualAttestation).toHaveProperty('attested')
  })

  it('7) 确认后构造的 plan 请求：严格三键，且确认状态**不**泄漏进请求体', () => {
    const before = buildRealPlanRequest(formWithManualEntry())
    // 未确认时不带任何手工条目进入 real 请求（它们是 mock，门禁禁止提交）
    expect(Object.keys(before).sort()).toEqual(['current_schedule', 'preference', 'semester'])

    const after = buildRealPlanRequest(applyManualAttestation(formWithManualEntry(), true))
    // ⛔ 请求体仍然只有三个公共字段：没有 attestation / manualAttestation 之类的自造字段
    expect(Object.keys(after).sort()).toEqual(['current_schedule', 'preference', 'semester'])
    expect(after.current_schedule).toHaveLength(1)
    expect(after.current_schedule[0].data_source).toBe('real')
    expect(after.current_schedule[0].source).toBe(MANUAL_SCHEDULE_SOURCE)
    expect(JSON.stringify(after)).not.toContain('attested')
    expect(JSON.stringify(after)).not.toContain('confirmedAt')
  })
})

describe('确认控件文案：不得暗示"学校已核验"', () => {
  it('确认说明明确写出"本人提供 / 未经学校系统核验"', () => {
    expect(MANUAL_SCHEDULE_ATTESTATION_NOTE).toContain('本人提供')
    expect(MANUAL_SCHEDULE_ATTESTATION_NOTE).toContain('未经学校系统核验')
    expect(MANUAL_SCHEDULE_ATTESTATION_NOTE).toContain('不构成 Course Data 来源证明')
  })

  it('录入区来源说明同样不声称学校来源', () => {
    expect(MANUAL_SCHEDULE_ENTRY_LABEL).toContain('本人填写')
    expect(MANUAL_SCHEDULE_ENTRY_LABEL).toContain('未经学校系统核验')
  })

  it('5) 页面文案不含"学校已核验 / 教务系统已确认"这类断言', () => {
    const wording = [
      MANUAL_SCHEDULE_ATTESTATION_NOTE,
      MANUAL_SCHEDULE_ENTRY_LABEL,
      UNATTESTED_MANUAL_SCHEDULE_BLOCK_REASON,
    ].join('\n')
    for (const forbidden of ['学校已核验', '教务系统已确认', '学校已确认', '学校来源证明']) {
      expect(wording).not.toContain(forbidden)
    }
  })
})

describe('组件交互：不需要用户写 JSON', () => {
  function mountPanel() {
    const form = ref<UserInputForm>(createDefaultUserInputForm())
    /** 真实提交守卫（与 App.vue 同源）：被阻止时**一个请求也不发**。 */
    const planCalls = { count: 0 }
    function submitRealPlan(): void {
      if (!evaluatePlanSubmission(form.value).allowed) {
        return
      }
      planCalls.count += 1
    }

    const Host = defineComponent({
      setup() {
        return () =>
          h(UserInputPanel, {
            form: form.value,
            offerings: [],
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
    return { wrapper: mount(Host), form, planCalls, submitRealPlan }
  }

  /** 填一行并加入课表（组件路径）。 */
  async function fillAndAdd(
    wrapper: ReturnType<typeof mountPanel>['wrapper'],
    form: ReturnType<typeof mountPanel>['form'],
  ): Promise<number> {
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
    return key
  }

  it('空列表时给出手工录入入口，并如实标注来源', async () => {
    const { wrapper } = mountPanel()
    expect(wrapper.find('[data-testid="manual-schedule-add-row"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="manual-schedule-provenance"]').text()).toContain('手工录入')
  })

  it('新增行 → 填表 → 加入当前课表 → 出现在已选列表', async () => {
    const { wrapper, form } = mountPanel()
    await fillAndAdd(wrapper, form)

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
    await fillAndAdd(wrapper, form)
    expect(form.value.currentSchedule).toHaveLength(1)

    await wrapper.find('[data-testid="manual-schedule-remove-selected-SEC1001-01"]').trigger('click')
    expect(form.value.currentSchedule).toEqual([])
  })

  it('1) 组件层：手工课表未确认 ⇒ 提交被阻止且零请求', async () => {
    const { wrapper, form, planCalls, submitRealPlan } = mountPanel()
    await fillAndAdd(wrapper, form)

    // 确认控件存在且默认**未勾选**
    const checkbox = wrapper.find('[data-testid="manual-attestation-checkbox"]')
    expect(checkbox.exists()).toBe(true)
    expect((checkbox.element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.find('[data-testid="manual-attestation-state-off"]').exists()).toBe(true)

    // 门禁给出的原因确实指向"未确认的手工课表"（纯函数层）
    expect(scheduleProvenanceBlockReason(form.value)).toBe(UNATTESTED_MANUAL_SCHEDULE_BLOCK_REASON)

    submitRealPlan()
    expect(planCalls.count).toBe(0)
  })

  it('2) 组件层：勾选确认 ⇒ 提交被允许且发出 1 次请求', async () => {
    const { wrapper, form, planCalls, submitRealPlan } = mountPanel()
    await fillAndAdd(wrapper, form)

    await wrapper.find('[data-testid="manual-attestation-checkbox"]').setValue(true)

    expect(form.value.manualAttestation.attested).toBe(true)
    expect(form.value.currentSchedule[0].data_source).toBe('real')
    expect(wrapper.find('[data-testid="manual-attestation-state-on"]').exists()).toBe(true)
    expect(scheduleProvenanceBlockReason(form.value)).toBeNull()

    submitRealPlan()
    expect(planCalls.count).toBe(1)
  })

  it('3) 组件层：取消勾选 ⇒ 重新阻断且零请求', async () => {
    const { wrapper, form, planCalls, submitRealPlan } = mountPanel()
    await fillAndAdd(wrapper, form)
    const checkbox = wrapper.find('[data-testid="manual-attestation-checkbox"]')

    await checkbox.setValue(true)
    submitRealPlan()
    expect(planCalls.count).toBe(1)

    await checkbox.setValue(false)
    expect(form.value.manualAttestation.attested).toBe(false)
    expect(form.value.currentSchedule[0].data_source).toBe('mock')

    submitRealPlan()
    expect(planCalls.count).toBe(1) // ⛔ 没有新增请求
  })

  it('4) 组件层：确认后课表被改动 ⇒ 提示重新确认且阻断', async () => {
    const { wrapper, form, planCalls, submitRealPlan } = mountPanel()
    const key = await fillAndAdd(wrapper, form)

    await wrapper.find('[data-testid="manual-attestation-checkbox"]').setValue(true)
    expect(form.value.manualAttestation.attested).toBe(true)

    // 新加入第二条手工条目（课表被改动）
    await wrapper.find(`[data-testid="manual-course-id-${key}"]`).setValue('SEC1002')
    await wrapper.find(`[data-testid="manual-course-name-${key}"]`).setValue('密码学基础')
    await wrapper.find(`[data-testid="manual-class-id-${key}"]`).setValue('02')
    await wrapper.find(`[data-testid="manual-weekday-${key}"]`).setValue('3')
    await wrapper.find(`[data-testid="manual-start-section-${key}"]`).setValue('1')
    await wrapper.find(`[data-testid="manual-end-section-${key}"]`).setValue('2')
    await wrapper.find(`[data-testid="manual-weeks-${key}"]`).setValue('1-16')
    await wrapper.find(`[data-testid="manual-add-${key}"]`).trigger('click')

    expect(form.value.currentSchedule).toHaveLength(2)
    expect(form.value.manualAttestation.attested).toBe(false)
    // 提示是**持续**状态：继续编辑下一行也不会消失
    expect(form.value.manualAttestation.invalidated).toBe(true)
    expect(form.value.currentSchedule.map((item) => item.data_source)).toEqual(['mock', 'mock'])
    expect(wrapper.find('[data-testid="manual-attestation-invalidated"]').exists()).toBe(true)

    submitRealPlan()
    expect(planCalls.count).toBe(0)

    // 重新确认后恢复，提示消失
    await wrapper.find('[data-testid="manual-attestation-checkbox"]').setValue(true)
    expect(form.value.manualAttestation.invalidated).toBe(false)
    expect(wrapper.find('[data-testid="manual-attestation-invalidated"]').exists()).toBe(false)
    submitRealPlan()
    expect(planCalls.count).toBe(1)
  })
})
