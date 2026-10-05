/**
 * 用户输入表单纯逻辑层的测试。
 *
 * 这些测试**不接触 DOM / 组件 / 网络**，只锁定字段规则、序列化与请求形状。
 * 关键红线：前端不猜业务事实、不生成 MakeupTask、请求体只有约定的三个字段。
 */

import { describe, expect, it } from 'vitest'
import {
  GRADE_FILE_PENDING_NOTICE,
  XLSX_EXTENSION,
  addAvoidTime,
  addPreferredCourse,
  buildCurrentSchedule,
  buildPreference,
  buildRealPlanRequest,
  createDefaultUserInputForm,
  isSupportedGradeFile,
  isValidSemester,
  parseMaxCredit,
  removeAvoidTime,
  removePreferredCourse,
  toggleCurrentScheduleOffering,
  updateAvoidTime,
} from '@/state/userInput'
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

describe('学期输入', () => {
  it('只接受 YYYY-1 / YYYY-2，不猜测其它写法', () => {
    expect(isValidSemester('2026-1')).toBe(true)
    expect(isValidSemester('2028-2')).toBe(true)
    expect(isValidSemester('2026-3')).toBe(false)
    expect(isValidSemester('2026年1学期')).toBe(false)
    expect(isValidSemester('')).toBe(false)
    expect(isValidSemester(' 2026-1 ')).toBe(false)
  })

  it('默认表单使用 Case A 的学期与转专业上下文，但不含任何学生身份信息', () => {
    const form = createDefaultUserInputForm()
    expect(form.semester).toBe('2026-1')
    expect(form.studentContext).toEqual({
      originMajor: '遥感科学与技术',
      targetMajor: '网络空间安全',
      transferTerm: '2026-1',
    })
    expect(Object.keys(form)).not.toContain('studentName')
    expect(Object.keys(form)).not.toContain('studentId')
  })
})

describe('max_credit 字段', () => {
  it('空输入表示未设定（null），非法输入不猜测', () => {
    expect(parseMaxCredit('')).toBe(null)
    expect(parseMaxCredit('   ')).toBe(null)
    expect(parseMaxCredit('24')).toBe(24)
    expect(parseMaxCredit('22.5')).toBe(22.5)
    expect(parseMaxCredit('0')).toBe(0)
    expect(parseMaxCredit('abc')).toBe('invalid')
    expect(parseMaxCredit('-3')).toBe('invalid')
  })

  it('序列化为公共 Preference 的 max_credit', () => {
    const form = createDefaultUserInputForm()
    form.preference.maxCredit = 24
    expect(buildPreference(form).max_credit).toBe(24)

    form.preference.maxCredit = null
    expect(buildPreference(form).max_credit).toBe(null)
  })
})

describe('avoid_times 增删改', () => {
  it('新增不产生重复时段', () => {
    const first = addAvoidTime([])
    expect(first).toHaveLength(1)

    const second = addAvoidTime(first)
    expect(second).toHaveLength(2)
    expect(second[1]).not.toEqual(second[0])
  })

  it('按 key 删除，且不修改原数组', () => {
    const rows = addAvoidTime(addAvoidTime([]))
    const removed = removeAvoidTime(rows, rows[0].key)
    expect(removed).toHaveLength(1)
    expect(rows).toHaveLength(2)
  })

  it('更新字段只影响目标行', () => {
    const rows = addAvoidTime(addAvoidTime([]))
    const updated = updateAvoidTime(rows, rows[1].key, { weekday: 5, start_section: 3, end_section: 4 })
    expect(updated[1]).toMatchObject({ weekday: 5, start_section: 3, end_section: 4 })
    expect(updated[0]).toEqual(rows[0])
  })

  it('序列化时丢掉前端 key，只保留三个公共字段', () => {
    const form = createDefaultUserInputForm()
    form.preference.avoidTimes = addAvoidTime([])
    const [block] = buildPreference(form).avoid_times ?? []
    expect(Object.keys(block).sort()).toEqual(['end_section', 'start_section', 'weekday'])
  })
})

describe('preferred_courses 维护', () => {
  it('空串与重复项都不产生新条目', () => {
    expect(addPreferredCourse([], '   ')).toEqual([])
    expect(addPreferredCourse(['CSE201'], 'CSE201')).toEqual(['CSE201'])
    expect(addPreferredCourse(['CSE201'], ' CSE209 ')).toEqual(['CSE201', 'CSE209'])
  })

  it('删除只移除目标课程号', () => {
    expect(removePreferredCourse(['A', 'B', 'A'], 'A')).toEqual(['B'])
    expect(removePreferredCourse(['A'], 'X')).toEqual(['A'])
  })
})

describe('current_schedule 输出为 CourseOffering[]', () => {
  it('只接受来源列表中的教学班（fail closed）', () => {
    const source = [offering()]
    const unknown = offering({ course_id: 'NOT-IN-SOURCE' })
    expect(toggleCurrentScheduleOffering([], unknown, source)).toEqual([])
  })

  it('可勾选与取消，且不修改原数组', () => {
    const source = [offering()]
    const selected = toggleCurrentScheduleOffering([], source[0], source)
    expect(selected).toHaveLength(1)

    const unselected = toggleCurrentScheduleOffering(selected, source[0], source)
    expect(unselected).toEqual([])
    expect(selected).toHaveLength(1)
  })

  it('输出的每个元素都保持 CourseOffering 形状（含 meetings）', () => {
    const form = createDefaultUserInputForm()
    const source = [offering()]
    form.currentSchedule = toggleCurrentScheduleOffering([], source[0], source)
    const schedule = buildCurrentSchedule(form)
    expect(schedule).toHaveLength(1)
    expect(schedule[0]).toHaveProperty('course_id')
    expect(schedule[0]).toHaveProperty('class_id')
    expect(schedule[0]).toHaveProperty('meetings')
    // 原样传递来源对象，不加工、不补字段
    expect(schedule[0]).toBe(source[0])
  })

  it('允许为空数组', () => {
    expect(buildCurrentSchedule(createDefaultUserInputForm())).toEqual([])
  })
})

describe('成绩文件选择门（本轮不解析）', () => {
  it('只接受 .xlsx（大小写不敏感）', () => {
    expect(isSupportedGradeFile('grades.xlsx')).toBe(true)
    expect(isSupportedGradeFile('GRADES.XLSX')).toBe(true)
    expect(isSupportedGradeFile('grades.xls')).toBe(false)
    expect(isSupportedGradeFile('grades.csv')).toBe(false)
    expect(isSupportedGradeFile('grades.xlsx.exe')).toBe(false)
    expect(isSupportedGradeFile('')).toBe(false)
  })

  it('提示文案明确说明分析尚未启用，且扩展名常量为 .xlsx', () => {
    expect(XLSX_EXTENSION).toBe('.xlsx')
    expect(GRADE_FILE_PENDING_NOTICE).toContain('真实 Curriculum User Input API')
  })
})

describe('POST /api/v1/plan 请求形状', () => {
  it('严格只包含 semester / current_schedule / preference', () => {
    const form = createDefaultUserInputForm()
    form.preference.maxCredit = 24
    const request = buildRealPlanRequest(form)

    expect(Object.keys(request).sort()).toEqual(['current_schedule', 'preference', 'semester'])
    expect(request.semester).toBe('2026-1')
    expect(request.current_schedule).toEqual([])
  })

  it('preference 不新增字段，且允许未设定值', () => {
    const request = buildRealPlanRequest(createDefaultUserInputForm())
    expect(Object.keys(request.preference).sort()).toEqual([
      'avoid_cross_campus',
      'avoid_times',
      'max_credit',
      'notes',
      'preferred_courses',
    ])
    expect(request.preference.max_credit).toBe(null)
    expect(request.preference.notes).toBe(null)
    expect(request.preference.avoid_cross_campus).toBe(false)
    expect(request.preference.preferred_courses).toEqual([])
    expect(request.preference.avoid_times).toEqual([])
  })

  it('不把学生上下文塞进请求（本轮不声称影响 Planner）', () => {
    const form = createDefaultUserInputForm()
    form.studentContext.targetMajor = '网络空间安全'
    const request = buildRealPlanRequest(form)
    expect(JSON.stringify(request)).not.toContain('网络空间安全')
  })

  it('空备注归一为 null，纯空白备注同样归一为 null', () => {
    const form = createDefaultUserInputForm()
    form.preference.notes = ''
    expect(buildPreference(form).notes).toBe(null)
    form.preference.notes = '   '
    expect(buildPreference(form).notes).toBe(null)
    form.preference.notes = '希望集中在上午'
    expect(buildPreference(form).notes).toBe('希望集中在上午')
  })
})
