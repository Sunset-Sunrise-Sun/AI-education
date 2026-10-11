/**
 * 课程标签（当前 / 补修 / 意向）——**只依据已有输入的事实**。
 *
 * 判定来源（每一项都必须是后端或用户已经提交的事实）：
 *
 * | 标签 | 依据 |
 * | --- | --- |
 * | 当前 | 教学班身份（**`semester + course_id + class_id`**）出现在**已提交**的 `current_schedule` 中 |
 * | 意向 | `course_id` 出现在 `Preference.preferredCourses` 中 |
 * | 补修 | `course_id` 命中 `MakeupTask[]`，且该任务状态**严格为 `required`** |
 *
 * ⚠️ 教学班身份必须带 `semester`：`(course_id, class_id)` 在不同学期可能完全相同，
 * 只按后两者匹配会把别的学期的教学班误当成"当前课表里的那个班"。
 *
 * ⛔ 只有 `MakeupStatus.REQUIRED` 才配 `补修` 标签：
 * `possibly_equivalent` / `manual_confirmation` 都是"待确认"，`satisfied` 是"已满足"，
 * 三者都**不得**被呈现为已确认的补修。
 *
 * ⛔ 来源无法唯一确定时**不给标签**；同一门课同时满足多个条件时如实给多个标签，
 * 而不是猜一个。⛔ 不新增业务分类、⛔ 不做等价/优先级推断。
 */

import type { CourseOffering, MakeupTask } from '../types/contracts'

export type CourseTag = 'current' | 'makeup' | 'preferred'

export const COURSE_TAG_LABEL: Record<CourseTag, string> = {
  current: '当前',
  makeup: '补修',
  preferred: '意向',
}

/** 唯一可标注为"补修"的状态：Curriculum 明确输出 `required`。 */
const CONFIRMED_MAKEUP_STATUS = 'required'

export interface CourseTagInput {
  /** 该课程 / 教学班所属学期（教学班身份的一部分）。 */
  semester: string
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

/** `semester + course_id + class_id` —— 与 `weeklySchedule.ts` 使用同一身份口径。 */
function identity(semester: string, courseId: string, classId: string): string {
  return `${semester}::${courseId}::${classId}`
}

function currentIdentities(currentSchedule: readonly CourseOffering[] | undefined): Set<string> {
  const keys = new Set<string>()
  for (const offering of currentSchedule ?? []) {
    keys.add(identity(offering.semester, offering.course_id, offering.class_id))
  }
  return keys
}

/**
 * 返回这门课**确实成立**的标签集合。
 */
export function courseTags(input: CourseTagInput): CourseTag[] {
  const tags: CourseTag[] = []

  const identities = currentIdentities(input.currentSchedule)
  if (input.classId && identities.has(identity(input.semester, input.courseId, input.classId))) {
    tags.push('current')
  }

  if ((input.preferredCourses ?? []).includes(input.courseId)) {
    tags.push('preferred')
  }

  // ⛔ 只有 `required` 才是已确认的补修要求；其余状态一律不加此标签。
  const isConfirmedMakeup = (input.makeupTasks ?? []).some(
    (task) => task.course_id === input.courseId && task.status === CONFIRMED_MAKEUP_STATUS,
  )
  if (isConfirmedMakeup) {
    tags.push('makeup')
  }

  return tags
}

/** 为一批课程 / 教学班批量求标签（课表块 / 列表可共用）。 */
export function courseTagMap(
  entries: readonly { semester: string; courseId: string; classId?: string }[],
  context: Omit<CourseTagInput, 'semester' | 'courseId' | 'classId'>,
): Map<string, CourseTag[]> {
  const result = new Map<string, CourseTag[]>()
  for (const entry of entries) {
    result.set(
      identity(entry.semester, entry.courseId, entry.classId ?? ''),
      courseTags({ ...context, ...entry }),
    )
  }
  return result
}
