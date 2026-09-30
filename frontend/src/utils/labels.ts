import type { MakeupStatus, PlanStatus, RiskLevel } from '../types/contracts'

/**
 * 纯展示用的文案映射。
 *
 * 注意：这些只是把后端已经给出的枚举"翻成中文"，**不代表前端做了任何判定**。
 * 例如 `possibly_equivalent` 显示成"可能等价（待人工确认）"，
 * 是把后端结论如实呈现，而不是前端自己判断两门课是否等价。
 */

export const MAKEUP_STATUS_LABEL: Record<MakeupStatus, string> = {
  required: '需要补修',
  possibly_equivalent: '可能等价（待人工确认）',
  manual_confirmation: '待人工确认',
  satisfied: '已满足',
}

/** 与状态标签配套的一句话说明，帮助观众理解这个状态是谁给的结论。 */
export const MAKEUP_STATUS_HINT: Record<MakeupStatus, string> = {
  required: 'Curriculum 模块判定为必须补修',
  possibly_equivalent: '是否可认定为同一门课，需人工确认',
  manual_confirmation: '需要教务人工判定，系统不自行下结论',
  satisfied: '已修课程可直接抵认，无需补修',
}

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = {
  feasible: '可行',
  partially_feasible: '部分可行',
  infeasible: '不可行',
}

export const RISK_LEVEL_LABEL: Record<RiskLevel, string> = {
  low: '低',
  medium: '中',
  high: '高',
}

const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

/** weekday: 1=周一 … 7=周日（与公共 Schema 一致）。 */
export function formatWeekday(weekday: number): string {
  return WEEKDAY_NAMES[weekday - 1] ?? `星期${weekday}`
}

/** 节次显示成 "3-4 节"。 */
export function formatSections(startSection: number, endSection: number): string {
  return startSection === endSection ? `${startSection} 节` : `${startSection}-${endSection} 节`
}

/**
 * 周次数组压成可读文本，例如 [1,2,3,5] -> "1-3、5 周"。
 * 纯显示格式化：不筛选、不推断哪些周"实际要上课"。
 */
export function formatWeeks(weeks: number[]): string {
  if (!weeks || weeks.length === 0) {
    return '—'
  }

  const sorted = [...new Set(weeks)].sort((a, b) => a - b)
  const parts: string[] = []
  let runStart = sorted[0]
  let previous = sorted[0]

  for (const week of sorted.slice(1)) {
    if (week === previous + 1) {
      previous = week
      continue
    }
    parts.push(runStart === previous ? `${runStart}` : `${runStart}-${previous}`)
    runStart = week
    previous = week
  }
  parts.push(runStart === previous ? `${runStart}` : `${runStart}-${previous}`)

  return `${parts.join('、')} 周`
}

/** 空值统一显示成破折号，避免页面上出现 "null" / "undefined"。 */
export function displayOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return String(value)
}
