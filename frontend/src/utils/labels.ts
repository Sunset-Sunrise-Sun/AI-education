import type { MakeupStatus, Meeting, PlanStatus, RiskLevel } from '../types/contracts'

/**
 * 纯展示用的文案映射与格式化工具。
 *
 * 重要原则：
 * - 这些工具仅用于在前端清晰呈现后端与公共 Schema 已经给出的数据。
 * - 前端不做任何业务推断、课程等价判定、冲突检测或优先级计算。
 */

export const MAKEUP_STATUS_LABEL: Record<MakeupStatus, string> = {
  required: '需要补修',
  possibly_equivalent: '可能等价（待人工确认）',
  manual_confirmation: '需要你的确认',
  satisfied: '已满足',
}

/** 与补修状态标签配套的说明，帮助观众理解该结论的来源责任主体。 */
export const MAKEUP_STATUS_HINT: Record<MakeupStatus, string> = {
  required: '请按建议学期安排补修。',
  possibly_equivalent: '可能与已修课程对应，请核实课程认定要求。',
  manual_confirmation: '请到推荐方案中核对这门课程。',
  satisfied: '当前记录已满足该课程要求。',
}

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = {
  feasible: '规划建议已生成',
  partially_feasible: '规划建议已生成，仍需确认',
  infeasible: '暂未找到合适方案',
}

export const PLAN_STATUS_DESCRIPTION: Record<PlanStatus, string> = {
  feasible: '已根据当前信息生成推荐方案，最终选课结果请以学校教务系统为准。',
  partially_feasible: '已生成当前可用的推荐方案，请完成下方课程信息确认。',
  infeasible: '根据目前提供的信息，暂时无法生成完整安排。你可以调整选课需求后重试。',
}

export const RISK_LEVEL_LABEL: Record<RiskLevel, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
}

/**
 * `unresolved[].type` 的展示翻译映射表。
 *
 * 公共 Schema 中 `unresolved[].type` 是开放字符串（没有 enum 约束），
 * 上游随时可能产生新的类型。因此：
 * - 登记已知取值与 DG-07C 预留的 schedule_unknown 类型；
 * - 未知类型由 `unresolvedTypeLabel` 安全 fallback，使用中性用户语言，
 *   ⛔ 不把后端原始取值当作界面文案展示；
 * - 严禁把所有类型统一硬编码为单一的“待人工确认”。
 *
 * ⚠️ 展示层改造（Architecture Decision · Option 1）：取值改为**用户语言**。
 *   后端原始 type 仍完整保留在数据里，不在学生页面渲染，
 *   ⛔ 数据结构与 API 未改动。
 */
export const UNRESOLVED_TYPE_LABEL: Record<string, string> = {
  manual_confirmation: '需要你的确认',
  missing_data: '缺少必要信息',
  schedule_unknown: '时间安排待确认',
  selection_required: '请选择课程',
  conflict: '时间冲突待解决',
  unmatched_course: '未找到匹配课程',
}

/**
 * 把 `unresolved[].type` 翻译为适合界面阅读的中文；
 * 未知类型使用中性用户语言，⛔ 不把原始技术取值当作文案。
 */
export function unresolvedTypeLabel(type: string): string {
  const known = UNRESOLVED_TYPE_LABEL[type]
  if (known) {
    return known
  }
  return '需要进一步确认'
}

/**
 * 根据 unresolved[].type 返回对应的视觉语气样式。
 */
export function unresolvedTypeTagClass(type: string): string {
  switch (type) {
    case 'manual_confirmation':
      return 'tag--unresolved-manual'
    case 'missing_data':
      return 'tag--unresolved-data'
    case 'schedule_unknown':
      return 'tag--unresolved-schedule'
    case 'selection_required':
      return 'tag--unresolved-selection'
    default:
      return 'tag--unresolved-other'
  }
}

const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

/** weekday: 1=周一 … 7=周日（与公共 Schema 一致）。 */
export function formatWeekday(weekday: number): string {
  return WEEKDAY_NAMES[weekday - 1] ?? `星期${weekday}`
}

/** 节次显示成 "3-4 节"。 */
export function formatSections(startSection: number, endSection: number): string {
  return startSection === endSection ? `第 ${startSection} 节` : `第 ${startSection}-${endSection} 节`
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

/**
 * DG-07D 规范：当 meetings=[] 时必须使用的中性数据状态表述。
 * 严禁使用“无课”、“无需上课”、“异步课程”、“尚未排课”、“无冲突”等推断性词汇。
 */
export const EMPTY_MEETINGS_DATA_TEXT = '当前数据中无排课信息'

/**
 * 把一段 meeting 拼成一行可读文本，例如：
 * `周一 · 第 3-4 节 · 1-16 周 · 东校园 / 东B305`。
 *
 * 纯展示拼接：不判断冲突、不比较优劣、不筛选、不合并 / 删除任何一段。
 */
export function formatMeetingLine(meeting: Meeting): string {
  const place = [meeting.campus, meeting.classroom]
    .filter((value): value is string => value !== null && value !== undefined && value !== '')
    .join(' / ')

  return [
    formatWeekday(meeting.weekday),
    formatSections(meeting.start_section, meeting.end_section),
    formatWeeks(meeting.weeks),
    place || '当前数据中无地点信息',
  ].join(' · ')
}
