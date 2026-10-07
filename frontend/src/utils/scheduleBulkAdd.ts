/**
 * 当前课表的**批量加入**逻辑（纯函数，⛔ 不碰网络、不碰 Vue）。
 *
 * 复用既有的 `toggleCurrentScheduleOffering`（同一套校验 + 去重），
 * 额外只加一层"同一门课不能同时占用两个教学班"的**前端 fail-closed** 检查。
 *
 * 教学班身份一律是 **semester + course_id + class_id**（与 `weeklySchedule.ts` 一致）。
 */

import type { CourseOffering } from '../types/contracts'
import { toggleCurrentScheduleOffering } from '../state/userInput'

export interface DuplicateCourseConflict {
  courseId: string
  semester: string
  /** 已在课表中的教学班（课表里原本没有则为 `null`）。 */
  keptClassId: string | null
  /** 本次选择里冲突的教学班。 */
  rejectedClassIds: string[]
}

export interface BatchAddEvaluation {
  /** 可直接加入的教学班（已按输入顺序、已去重）。 */
  acceptable: CourseOffering[]
  /**
   * 同课程冲突。
   *
   * 冲突同时覆盖两种情况：
   * - 批量选择里同一门课出现多个不同教学班；
   * - 某门课已在课表中，而本次又选了它的**另一个**教学班。
   *
   * ⚠️ 分组键是 **semester + course_id**：不同学期的同名课程号互不影响。
   */
  conflicts: DuplicateCourseConflict[]
  /** 已经在课表中的（跳过，不算错、不重复加入）。 */
  alreadyPresent: CourseOffering[]
}

function identity(offering: CourseOffering): string {
  return `${offering.semester}::${offering.course_id}::${offering.class_id}`
}

/** 同一门课的判定口径：**同一学期内的同一课程号**。 */
function courseKey(offering: CourseOffering): string {
  return `${offering.semester}::${offering.course_id}`
}

/**
 * 评估一批选择能否批量加入。
 *
 * 规则：
 * - 已在课表中的教学班 → `alreadyPresent`（⛔ 不重复加入、不报错）；
 * - 同一门课在批次内选了多个不同教学班 → 该课程**整门** fail closed（进 `conflicts`）；
 * - 某门课已在课表中且本次又选它的另一个教学班 → 同样 fail closed；
 * - 其余照常可加入。
 */
export function evaluateBatchAdd(
  current: readonly CourseOffering[],
  selections: readonly CourseOffering[],
): BatchAddEvaluation {
  const currentIdentities = new Set(current.map(identity))
  const currentClassByCourse = new Map<string, string>()
  for (const offering of current) {
    const key = courseKey(offering)
    if (!currentClassByCourse.has(key)) {
      currentClassByCourse.set(key, offering.class_id)
    }
  }

  const alreadyPresent: CourseOffering[] = []
  const seen = new Set<string>()
  // (semester::course_id) -> (class_id -> offering)，仅本批次
  const batchByCourse = new Map<string, Map<string, CourseOffering>>()

  for (const offering of selections) {
    const key = identity(offering)
    if (currentIdentities.has(key)) {
      alreadyPresent.push(offering)
      continue
    }
    if (seen.has(key)) continue
    seen.add(key)

    const byClass = batchByCourse.get(courseKey(offering)) ?? new Map<string, CourseOffering>()
    byClass.set(offering.class_id, offering)
    batchByCourse.set(courseKey(offering), byClass)
  }

  const conflicts: DuplicateCourseConflict[] = []
  const conflictedKeys = new Set<string>()

  for (const [key, byClass] of batchByCourse) {
    const existingClass = currentClassByCourse.get(key)
    const distinctClasses = [...byClass.keys()]
    const first = byClass.get(distinctClasses[0])
    if (!first) continue

    if (distinctClasses.length > 1) {
      // 批次内同课程多班：整门 fail closed（⛔ 不替用户挑一个）
      conflicts.push({
        courseId: first.course_id,
        semester: first.semester,
        keptClassId: existingClass ?? null,
        rejectedClassIds: distinctClasses,
      })
      conflictedKeys.add(key)
      continue
    }

    if (existingClass !== undefined && existingClass !== distinctClasses[0]) {
      conflicts.push({
        courseId: first.course_id,
        semester: first.semester,
        keptClassId: existingClass,
        rejectedClassIds: distinctClasses,
      })
      conflictedKeys.add(key)
    }
  }

  const acceptable: CourseOffering[] = []
  for (const [key, byClass] of batchByCourse) {
    if (conflictedKeys.has(key)) continue
    for (const offering of byClass.values()) acceptable.push(offering)
  }

  // 保持用户选择顺序
  const order = new Map<string, number>()
  selections.forEach((offering, index) => {
    const key = identity(offering)
    if (!order.has(key)) order.set(key, index)
  })
  acceptable.sort(
    (left, right) => (order.get(identity(left)) ?? 0) - (order.get(identity(right)) ?? 0),
  )

  return { acceptable, conflicts, alreadyPresent }
}

/**
 * 执行批量加入：复用既有 `toggleCurrentScheduleOffering`，⛔ 不绕过它的去重与校验。
 *
 * ⚠️ 调用方在 `conflicts` 非空时应**不执行**本函数（fail closed），
 * 把冲突原样交给用户先解决。
 */
export function applyBatchAdd(
  current: readonly CourseOffering[],
  acceptable: readonly CourseOffering[],
  offerings: readonly CourseOffering[],
): CourseOffering[] {
  let next = [...current]
  for (const offering of acceptable) {
    next = toggleCurrentScheduleOffering(next, offering, offerings)
  }
  return next
}

/** 把冲突转成给用户看的中文提示（⛔ 不自动替用户选择保留哪一个）。 */
export function describeConflicts(conflicts: readonly DuplicateCourseConflict[]): string {
  if (conflicts.length === 0) return ''
  const parts = conflicts.map((conflict) => {
    const kept = conflict.keptClassId === null ? '' : `（当前课表已保留教学班 ${conflict.keptClassId}）`
    return (
      `${conflict.courseId} 选择了 ${conflict.rejectedClassIds.length} 个教学班` +
      `（${conflict.rejectedClassIds.join(' / ')}）${kept}`
    )
  })
  return `同一门课只能保留一个教学班：${parts.join('；')}。请先只保留一个教学班，再批量加入。`
}
