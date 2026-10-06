/**
 * 本学期周课表视图（当前学期 = 精确到教学班的规划）。
 *
 * 数据来源**只有**后端已经返回的事实：
 *
 * ```text
 * PlanResult.selected_classes  +  Case A response.course_offerings
 *            └── 通过 semester + course_id + class_id 匹配真实 CourseOffering
 * ```
 *
 * 边界：
 * - ⛔ 不修改 `PlanResult`、⛔ 不新增字段、⛔ 不推断后端没给的课；
 * - `selected_classes` 是 Planner 的**建议**，⛔ 不得呈现成"已选上 / 已注册"；
 * - 匹配不到教学班时如实标记为未知，⛔ 不编造时间 / 地点 / 教师；
 * - `meetings = []` 表示"当前数据中无排课信息"，⛔ 不表示没有课、更不表示无冲突。
 */

import type { CourseOffering, PlanResult } from '../types/contracts'
import { EMPTY_MEETINGS_DATA_TEXT } from './labels'

/** 一天的节次数量上界（用于绘制节次轴；仅排版用，⛔ 不代表真实作息表）。 */
export const SECTION_AXIS_MAX = 13

export interface ScheduleBlock {
  courseId: string
  courseName: string
  classId: string
  /** `null` 表示 meeting 未提供校区（⛔ 不猜）。 */
  campus: string | null
  /** `null` 表示 meeting 未提供教室（⛔ 不猜）。 */
  classroom: string | null
  /** `null` 表示后端没有提供任课教师 → 界面显示"待核验"。 */
  teacher: string | null
  startSection: number
  endSection: number
  departureWarning: boolean
}

export interface ScheduleDay {
  /** 1=周一 … 7=周日（与公共 Schema 一致）。 */
  weekday: number
  blocks: ScheduleBlock[]
}

export interface ScheduleSlot {
  weekday: number
  section: number
  block: ScheduleBlock | null
}

export interface WeeklyScheduleView {
  days: ScheduleDay[]
  sectionNumbers: number[]
  slots: ScheduleSlot[]
  /** `selected_classes` 里无法在本学期教学班数据中匹配到教学班的条目。 */
  unmatched: { courseId: string; classId: string }[]
}

function identityOf(offering: CourseOffering): string {
  return teachingClassIdentity(offering.semester, offering.course_id, offering.class_id)
}

/**
 * 教学班身份 = **semester + course_id + class_id**。
 *
 * ⚠️ 必须带 `semester`：`(course_id, class_id)` 在不同学期可以完全相同，
 * 只按后两者匹配会把**别的学期的教学班**误当成同一门课。
 * 公共 `SelectedClass` 没有 `semester` 字段，因此调用方必须显式传入
 * 本学期（Case A 当前的规划学期）。
 */
export function teachingClassIdentity(
  semester: string,
  courseId: string,
  classId: string,
): string {
  return `${semester}::${courseId}::${classId}`
}

/**
 * 由 `PlanResult.selected_classes` 与本学期真实教学班构造周课表。
 *
 * 匹配键为 **semester + course_id + class_id**（教学班身份），**不是**课程号：
 * 同一门课可以只被建议其中一个教学班。
 *
 * `semester` 必须是**本学期的显式规划学期**（Case A 表单 / 请求上下文），
 * ⛔ 不从系统日期推断。
 */
export function buildWeeklySchedule(
  planResult: PlanResult | null,
  offerings: readonly CourseOffering[],
  semester: string,
): WeeklyScheduleView {
  const byIdentity = new Map<string, CourseOffering>()
  for (const offering of offerings) {
    const key = identityOf(offering)
    if (!byIdentity.has(key)) byIdentity.set(key, offering)
  }

  const blocks = new Map<number, ScheduleBlock[]>()
  const unmatched: { courseId: string; classId: string }[] = []

  for (const selected of planResult?.selected_classes ?? []) {
    // 用显式本学期拼出完整身份；只有**同一学期**的教学班才算同一个班。
    const offering = byIdentity.get(
      teachingClassIdentity(semester, selected.course_id, selected.class_id),
    )

    if (!offering) {
      unmatched.push({ courseId: selected.course_id, classId: selected.class_id })
      continue
    }

    // 一个教学班可以有多段 meeting；必须全部绘制，⛔ 不能只看第一段。
    for (const meeting of offering.meetings) {
      const campus = meeting.campus ?? null
      const block: ScheduleBlock = {
        courseId: offering.course_id,
        courseName: offering.course_name,
        classId: offering.class_id,
        campus,
        classroom: meeting.classroom ?? null,
        teacher: offering.teacher ?? null,
        startSection: meeting.start_section,
        endSection: meeting.end_section,
        // 跨校区提醒是**纯事实比较**（同一门课的多段在不同校区），
        // ⛔ 不是冲突判定、⛔ 不是 Planner 结论。
        departureWarning: false,
      }
      const list = blocks.get(meeting.weekday) ?? []
      list.push(block)
      blocks.set(meeting.weekday, list)
    }
  }

  // 同一天内：若同一门课的不同 meeting 落在不同校区，标记为需要注意的通勤点。
  for (const list of blocks.values()) {
    const campuses = new Set(list.map((block) => block.campus).filter((value): value is string => !!value))
    if (campuses.size > 1) {
      for (const block of list) block.departureWarning = true
    }
    list.sort((left, right) =>
      left.startSection - right.startSection || left.classId.localeCompare(right.classId),
    )
  }

  const maxSection = SECTION_AXIS_MAX
  const days: ScheduleDay[] = []
  const slots: ScheduleSlot[] = []
  for (let weekday = 1; weekday <= 7; weekday += 1) {
    const dayBlocks = blocks.get(weekday) ?? []
    days.push({ weekday, blocks: dayBlocks })
    for (let section = 1; section <= maxSection; section += 1) {
      const block =
        dayBlocks.find(
          (item) => section >= item.startSection && section <= item.endSection,
        ) ?? null
      slots.push({ weekday, section, block })
    }
  }

  return {
    days,
    sectionNumbers: Array.from({ length: maxSection }, (_, index) => index + 1),
    slots,
    unmatched,
  }
}

/** 周课表是否没有任何可绘制内容（用于决定是否显示空状态）。 */
export function weeklyScheduleIsEmpty(view: WeeklyScheduleView): boolean {
  return view.days.every((day) => day.blocks.length === 0)
}

/** 与既有教学班列表相同的中性文案（DG-07D）：`meetings=[]` 不等于没有课。 */
export const NO_SCHEDULE_DATA_TEXT = EMPTY_MEETINGS_DATA_TEXT
