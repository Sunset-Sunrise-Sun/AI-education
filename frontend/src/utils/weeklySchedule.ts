/**
 * 本学期周课表视图（当前学期 = 精确到教学班的规划）。
 *
 * 数据来源**只有**后端已经返回的事实：
 *
 * ```text
 * current_schedule（学生已确认加入的真实教学班）
 *        +
 * PlanResult.selected_classes  +  Case A response.course_offerings
 *            └── 通过 semester + course_id + class_id 匹配真实 CourseOffering
 * ```
 *
 * ⚠️ 修复（P0）：此前只渲染 `selected_classes`，导致"学生已加入课表的课程"
 *    在生成后的课表里**看不到**（后端 `selected_classes` 可能只含 Planner 建议的
 *    少数几个班）。现在两块都画，并用 `ScheduleBlock.origin` **如实区分**：
 *    `current` = 学生已确认加入的当前课表，`selected` = 后端返回的规划建议。
 *
 * 边界：
 * - ⛔ 不修改 `PlanResult`、⛔ 不新增字段、⛔ 不推断后端没给的课；
 * - ⛔ 不伪造课程：两块都必须是**真实 CourseOffering**（学生选的或后端给的）；
 * - `selected_classes` 是 Planner 的**建议**，⛔ 不得呈现成"已选上 / 已注册"；
 * - 匹配不到教学班时如实标记为未知，⛔ 不编造时间 / 地点 / 教师；
 * - `meetings = []` 表示"当前数据中无排课信息"，⛔ 不表示没有课、更不表示无冲突。
 */

import type { CourseOffering, Meeting, PlanResult } from '../types/contracts'
import { EMPTY_MEETINGS_DATA_TEXT, formatWeekday } from './labels'

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
  /**
   * 课块来源（**如实标注**，⛔ 不推断、⛔ 不美化）：
   * - `current`：学生**已确认加入当前课表**的真实教学班；
   * - `selected`：后端 `selected_classes` 返回的规划建议教学班。
   */
  origin: 'current' | 'selected' | 'planned'
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
 * 由**当前课表** + `PlanResult.selected_classes` + 本学期真实教学班构造周课表。
 *
 * 匹配键为 **semester + course_id + class_id**（教学班身份），**不是**课程号：
 * 同一门课可以只被建议其中一个教学班。
 *
 * `semester` 必须是**本学期的显式规划学期**（Case A 表单 / 请求上下文），
 * ⛔ 不从系统日期推断。
 *
 * ⚠️ 修复（P0）：`currentSchedule` 里的真实教学班**必须**一并绘制成 `origin: 'current'`，
 *   否则学生"已加入当前课表"的课程在生成后的课表里会凭空消失。
 */
export function buildWeeklySchedule(
  planResult: PlanResult | null,
  offerings: readonly CourseOffering[],
  semester: string,
  currentSchedule: readonly CourseOffering[] = [],
  selectedSemesterCourses: readonly CourseOffering[] = [],
): WeeklyScheduleView {
  const byIdentity = new Map<string, CourseOffering>()
  for (const offering of offerings) {
    const key = identityOf(offering)
    if (!byIdentity.has(key)) byIdentity.set(key, offering)
  }

  const blocks = new Map<number, ScheduleBlock[]>()
  const unmatched: { courseId: string; classId: string }[] = []
  /** 已经画过的教学班身份，避免同一班被两块重复绘制。 */
  const drawn = new Set<string>()

  /** 把一个真实教学班的所有 meeting 画进课表。 */
  function draw(offering: CourseOffering, origin: 'current' | 'selected' | 'planned'): void {
    const key = identityOf(offering)
    if (drawn.has(key)) {
      return
    }
    drawn.add(key)

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
        origin,
      }
      const list = blocks.get(meeting.weekday) ?? []
      list.push(block)
      blocks.set(meeting.weekday, list)
    }
  }

  // ① 学生已确认加入的当前课表（只画明确是真实来源的班，⛔ 不画演示条目）。
  for (const offering of currentSchedule) {
    if (offering.data_source !== 'real') {
      continue
    }
    if (!byIdentity.has(identityOf(offering))) {
      // 当前课表里的班也必须在**本学期教学班数据**中存在，否则不算同一班。
      continue
    }
    draw(offering, 'current')
  }

  // ② 学生本次主动加入「本学期方案」的课程（本地状态，实时生效）。
  for (const offering of selectedSemesterCourses) {
    if (offering.data_source !== 'real') {
      continue
    }
    if (!byIdentity.has(identityOf(offering))) {
      continue
    }
    draw(offering, 'planned')
  }

  // ② 后端返回的规划建议教学班。
  for (const selected of planResult?.selected_classes ?? []) {
    // 用显式本学期拼出完整身份；只有**同一学期**的教学班才算同一个班。
    const offering = byIdentity.get(
      teachingClassIdentity(semester, selected.course_id, selected.class_id),
    )

    if (!offering) {
      unmatched.push({ courseId: selected.course_id, classId: selected.class_id })
      continue
    }

    // 已被 ① 画过的班不再重复绘制（它已经是"当前课表"里的课）。
    draw(offering, 'selected')
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

/**
 * 当前课表行的**紧凑时间摘要**：`周一 3-4节；周四 5-6节`。
 *
 * 只压缩展示长度，⛔ 不合并 / 删除任何一段 meeting，也⛔ 不判断冲突。
 * `meetings = []` 时返回中性文案（⛔ 不写"无课"）。
 */
export function compactMeetingSummary(meetings: readonly Meeting[]): string {
  return compactMeetingLines(meetings).join('；')
}

/**
 * 当前课表使用的时间行。相同星期与节次只展示一次；原始 meetings 保持不变。
 */
export function compactMeetingLines(meetings: readonly Meeting[]): string[] {
  if (meetings.length === 0) return [NO_SCHEDULE_DATA_TEXT]
  return [...new Set(meetings.map(
    (meeting) => `${formatWeekday(meeting.weekday)} ${meeting.start_section}-${meeting.end_section}节`,
  ))]
}
