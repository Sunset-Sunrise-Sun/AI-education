/**
 * `buildWeeklySchedule` 的**合并绘制**测试（P0 修复）。
 *
 * 背景：「生成后的规划课表」原先只读 `PlanResult.selected_classes`，
 * 导致学生**已经加入当前课表**的真实教学班在生成后的课表里看不到。
 * 现在「当前课表」与「规划建议」两块都绘制，并用 `origin` 如实区分。
 */

import { describe, expect, it } from 'vitest'

import { buildWeeklySchedule, teachingClassIdentity } from '@/utils/weeklySchedule'
import type { CourseOffering, PlanResult } from '@/types/contracts'

const SEMESTER = '2026-1'

function offering(
  courseId: string,
  classId: string,
  weekday: number,
  from: number,
  to: number,
  name = `课程${courseId}`,
): CourseOffering {
  return {
    course_id: courseId,
    course_name: name,
    class_id: classId,
    semester: SEMESTER,
    meetings: [
      {
        weekday,
        start_section: from,
        end_section: to,
        weeks: [1, 2, 3, 4],
        campus: '深圳校区',
        classroom: 'A101',
      },
    ],
    source: 'capture://sysu/2026-1',
    data_source: 'real',
  }
}

function plan(selected: { course_id: string; class_id: string }[]): PlanResult {
  return {
    status: 'partially_feasible',
    selected_classes: selected,
    changes: [],
    risks: [],
    unresolved: [],
  } as unknown as PlanResult
}

/** 收集所有课块（含节次去重后的原块）。 */
function allBlocks(view: ReturnType<typeof buildWeeklySchedule>) {
  const seen = new Set<string>()
  const out: { courseId: string; origin: string }[] = []
  for (const day of view.days) {
    for (const block of day.blocks) {
      const key = `${day.weekday}-${block.courseId}-${block.classId}-${block.startSection}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push({ courseId: block.courseId, origin: block.origin })
    }
  }
  return out
}

describe('buildWeeklySchedule：当前课表 + 规划建议都绘制', () => {
  it('当前课表的课程会出现在课表里（origin=current）', () => {
    const mine = offering('CSE337', '202616239', 5, 1, 4, '数据库系统实验')
    const view = buildWeeklySchedule(plan([]), [mine], SEMESTER, [mine])

    const blocks = allBlocks(view)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].courseId).toBe('CSE337')
    expect(blocks[0].origin).toBe('current')
  })

  it('规划建议的课程也会绘制（origin=selected）', () => {
    const suggested = offering('CSE335', '202616238', 4, 9, 10, '数据库系统原理')
    const view = buildWeeklySchedule(
      plan([{ course_id: 'CSE335', class_id: '202616238' }]),
      [suggested],
      SEMESTER,
      [],
    )

    const blocks = allBlocks(view)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].origin).toBe('selected')
  })

  it('两类同时存在时**都**出现（P0 回归）', () => {
    const mine = offering('CSE337', '202616239', 5, 1, 4, '数据库系统实验')
    const suggested = offering('CSE335', '202616238', 4, 9, 10, '数据库系统原理')
    const view = buildWeeklySchedule(
      plan([{ course_id: 'CSE335', class_id: '202616238' }]),
      [mine, suggested],
      SEMESTER,
      [mine],
    )

    const blocks = allBlocks(view)
    expect(blocks).toHaveLength(2)
    const byId = Object.fromEntries(blocks.map((b) => [b.courseId, b.origin]))
    expect(byId['CSE337']).toBe('current')
    expect(byId['CSE335']).toBe('selected')
  })

  it('同一教学班不会因两块来源而被重复绘制', () => {
    const both = offering('AA1006', '202615612', 3, 5, 6)
    const view = buildWeeklySchedule(
      plan([{ course_id: 'AA1006', class_id: '202615612' }]),
      [both],
      SEMESTER,
      [both],
    )

    const blocks = allBlocks(view)
    expect(blocks).toHaveLength(1)
    // 先画当前课表，因此优先标为 current
    expect(blocks[0].origin).toBe('current')
  })

  it('⛔ 非 real 来源的当前课表条目不会进入课表（不伪造课程）', () => {
    const demo = { ...offering('DEMO1', 'X', 1, 1, 2), data_source: 'mock' } as CourseOffering
    const view = buildWeeklySchedule(plan([]), [demo], SEMESTER, [demo])
    expect(allBlocks(view)).toHaveLength(0)
  })

  it('⛔ 当前课表里的班若不在本学期教学班数据中，也不绘制', () => {
    const ghost = offering('GHOST', 'NOPE', 1, 1, 2)
    const view = buildWeeklySchedule(plan([]), [], SEMESTER, [ghost])
    expect(allBlocks(view)).toHaveLength(0)
  })

  it('匹配不到的规划建议仍如实记入 unmatched', () => {
    const view = buildWeeklySchedule(
      plan([{ course_id: 'NOPE', class_id: 'X' }]),
      [],
      SEMESTER,
      [],
    )
    expect(view.unmatched).toEqual([{ courseId: 'NOPE', classId: 'X' }])
  })

  it('教学班身份含学期：不同学期的同名课程互不混同', () => {
    expect(teachingClassIdentity('2026-1', 'C', 'X')).not.toBe(
      teachingClassIdentity('2026-2', 'C', 'X'),
    )

    // 当前课表里是 **2026-2** 的班，而本学期是 2026-1：
    // 它会被如实绘制（它确实是学生的当前课表条目），
    // 但**不会**被 `selected_classes`（本学期）那条按身份误匹配成同一个班。
    const other = { ...offering('C', 'X', 1, 1, 2), semester: '2026-2' } as CourseOffering
    const view = buildWeeklySchedule(
      plan([{ course_id: 'C', class_id: 'X' }]),
      [other],
      SEMESTER,
      [other],
    )

    const blocks = allBlocks(view)
    expect(blocks).toHaveLength(1)
    // 命中的是"当前课表"那条；`selected_classes` 用的是 2026-1 身份，匹配不到 other
    expect(blocks[0].origin).toBe('current')
    expect(view.unmatched).toEqual([{ courseId: 'C', classId: 'X' }])
  })
})
