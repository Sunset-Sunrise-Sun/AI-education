/**
 * 意向课程搜索（**课程级**）。
 *
 * 边界：
 * - 数据源只有现有的真实 `CourseOffering[]`，⛔ 不新增数据源、⛔ 不联网；
 * - 这是**字面子串搜索**，不是语义 / 向量 / AI 推荐：
 *   查询词必须真的出现在 `course_name` 或 `course_id` 里才算命中；
 *   ⛔ 不得把没有字面命中的课程（例如输入 Python 却返回“机器学习”）当作相关结果；
 * - 结果**去重到课程级**：同一 `course_id` 只出现一条，教学班数量只是一个计数；
 * - ⛔ 不做冲突检测、不判断能否排下、不生成任何认定结论。
 */

import type { CourseOffering } from '../types/contracts'

/** 一条课程级搜索结果：一门课 + 它在本学期可见的教学班数量。 */
export interface CourseLevelMatch {
  courseId: string
  courseName: string
  credit: number | null
  /** 本学期可见教学班数量（来自真实教学班数据，仅作计数展示）。 */
  classCount: number
}

/**
 * 按课程级去重：同一 `course_id` 只保留一条。
 *
 * `course_name` 取该课程在数据中**首次出现**的名称（⛔ 不拼接、不推断别名）；
 * `credit` 取首次出现的非空学分，缺省为 `null`（⛔ 不猜测学分）。
 */
export function courseLevelMatches(offerings: readonly CourseOffering[]): CourseLevelMatch[] {
  const byCourse = new Map<string, CourseLevelMatch>()
  for (const offering of offerings) {
    const existing = byCourse.get(offering.course_id)
    if (existing) {
      existing.classCount += 1
      if (existing.credit === null && typeof offering.credit === 'number') {
        existing.credit = offering.credit
      }
      continue
    }
    byCourse.set(offering.course_id, {
      courseId: offering.course_id,
      courseName: offering.course_name,
      credit: typeof offering.credit === 'number' ? offering.credit : null,
      classCount: 1,
    })
  }
  return [...byCourse.values()]
}

/**
 * 课程级字面搜索：`course_name` 或 `course_id` 包含查询词即命中（大小写不敏感）。
 *
 * 空查询返回空数组（与既有教学班搜索一致：不输入就不铺开任何结果）。
 */
export function searchCourses(
  offerings: readonly CourseOffering[],
  query: string,
): CourseLevelMatch[] {
  const needle = query.trim().toLocaleLowerCase()
  if (!needle) return []

  return courseLevelMatches(offerings)
    .filter((match) => {
      const haystack = `${match.courseName} ${match.courseId}`.toLocaleLowerCase()
      return haystack.includes(needle)
    })
    .sort((left, right) => {
      const byName = left.courseName.localeCompare(right.courseName, 'zh-CN')
      return byName !== 0 ? byName : left.courseId.localeCompare(right.courseId)
    })
}

/** 一门课程在数据中可见的教学班（用于“加入当前课表”的后续选择）。 */
export function classesOfCourse(
  offerings: readonly CourseOffering[],
  courseId: string,
): CourseOffering[] {
  return offerings.filter((offering) => offering.course_id === courseId)
}
