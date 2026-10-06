/**
 * 课程标签（当前 / 补修 / 意向）——**只依据已有输入的事实**。
 *
 * 判定来源（每一项都必须是后端或用户已经提交的事实）：
 *
 * | 标签 | 依据 |
 * | --- | --- |
 * | 当前 | 教学班身份（`course_id + class_id`）出现在**已提交**的 `current_schedule` 中 |
 * | 意向 | `course_id` 出现在 `Preference.preferredCourses` 中 |
 * | 补修 | `course_id` 出现在 `MakeupTask[]` 中，且该任务可明确识别为补修要求 |
 *
 * ⛔ 来源无法唯一确定时**不给标签**（例如同一门课既是补修又是意向 → 两个标签都成立，
 * 这时如实给两个，而不是猜一个）；⛔ 不新增业务分类、⛔ 不做等价/优先级推断。
 */

import type { CourseOffering, MakeupTask } from '../types/contracts'

export type CourseTag = 'current' | 'makeup' | 'preferred'

export const COURSE_TAG_LABEL: Record<CourseTag, string> = {
  current: '当前',
  makeup: '补修',
  preferred: '意向',
}

/** 可明确识别为"需要补修"的 MakeupTask 状态（⛔ 不改写该语义，仅读）。 */
const MAKEUP_REQUIREMENT_STATUSES = new Set(['required', 'possibly_equivalent', 'manual_confirmation'])

export interface CourseTagInput {
  /** `selected_classes` / 教学班所属的课程号。 */
  courseId: string
  /** 该课程对应的教学班号；判断"当前"时需要（课表按教学班记录）。 */
  classId?: string
  /** 已提交的当前课表（用户确认过的教学班身份）。 */
  currentSchedule?: readonly CourseOffering[]
  /** 后端返回的补修任务。 */
  makeupTasks?: readonly MakeupTask[]
  /** 用户在 Preference 中选择的意向课程号。 */
  preferredCourses?: readonly string[]
}

function currentIdentities(currentSchedule: readonly CourseOffering[] | undefined): Set<string> {
  const keys = new Set<string>()
  for (const offering of currentSchedule ?? []) {
    keys.add(`${offering.course_id}::${offering.class_id}`)
  }
  return keys
}

/**
 * 返回这门课**确实成立**的标签集合。
 *
 * 判定顺序与来源：
 * - 当前：教学班身份命中已提交课表；
 * - 意向：课程号命中所选意向课程；
 * - 补修：课程号命中后端 `MakeupTask[]` 中状态属于"需要补修"的条目
 *   （`satisfied` 表示已满足，⛔ 不算补修要求）。
 */
export function courseTags(input: CourseTagInput): CourseTag[] {
  const tags: CourseTag[] = []

  const identities = currentIdentities(input.currentSchedule)
  if (input.classId && identities.has(`${input.courseId}::${input.classId}`)) {
    tags.push('current')
  }

  if ((input.preferredCourses ?? []).includes(input.courseId)) {
    tags.push('preferred')
  }

  const isMakeup = (input.makeupTasks ?? []).some(
    (task) => task.course_id === input.courseId && MAKEUP_REQUIREMENT_STATUSES.has(task.status),
  )
  if (isMakeup) {
    tags.push('makeup')
  }

  return tags
}

/** 为一批课程号批量求标签（课表块 / 列表可共用）。 */
export function courseTagMap(
  entries: readonly { courseId: string; classId?: string }[],
  context: Omit<CourseTagInput, 'courseId' | 'classId'>,
): Map<string, CourseTag[]> {
  const result = new Map<string, CourseTag[]>()
  for (const entry of entries) {
    result.set(
      `${entry.courseId}::${entry.classId ?? ''}`,
      courseTags({ ...context, courseId: entry.courseId, classId: entry.classId }),
    )
  }
  return result
}
