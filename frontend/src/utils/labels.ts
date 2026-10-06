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
  manual_confirmation: '待人工确认',
  satisfied: '已满足',
}

/** 与补修状态标签配套的说明，帮助观众理解该结论的来源责任主体。 */
export const MAKEUP_STATUS_HINT: Record<MakeupStatus, string> = {
  required: 'Curriculum 当前输出为“需要补修”；具体依据见认定说明与 source_evidence',
  possibly_equivalent: 'Curriculum 当前输出为“可能等价”；需要进一步确认，具体依据见认定说明',
  manual_confirmation: 'Curriculum 当前要求人工确认；具体原因见认定说明',
  satisfied: 'Curriculum 当前输出为“已满足”；具体依据见认定说明',
}

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = {
  feasible: '可行',
  partially_feasible: '部分可确认',
  infeasible: '当前范围内不可行',
}

export const PLAN_STATUS_DESCRIPTION: Record<PlanStatus, string> = {
  feasible: '当前建议方案成立所依赖的确定性条件已完成认证，且不存在影响该方案成立的未决事项；不代表学校已经完成正式选课或审批。',
  partially_feasible: '当前仍存在排课信息未知、人工选择、输入不足或尚未完成认证的事项，现有证据尚不能证明完整目标无解。',
  infeasible: '在当前明确目标、当前输入域和已确认硬约束范围内，Planner 已证明不存在可行组合；不代表学校全部真实供给或未来学期均无解。',
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
 * - 未知类型由 `unresolvedTypeLabel` 安全 fallback，原样显示并保留原始类型标识；
 * - 严禁把所有类型统一硬编码为单一的“待人工确认”。
 */
export const UNRESOLVED_TYPE_LABEL: Record<string, string> = {
  manual_confirmation: '待人工确认',
  missing_data: '缺少数据',
  schedule_unknown: '排课信息未知',
  selection_required: '需要明确选择',
}

/**
 * 把 `unresolved[].type` 翻译为适合界面阅读的中文；
 * 未知类型原样呈现并提供通用 fallback。
 */
export function unresolvedTypeLabel(type: string): string {
  const known = UNRESOLVED_TYPE_LABEL[type]
  if (known) {
    return known
  }
  return type ? `未分类事项 (${type})` : '未解决事项'
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

/* -------------------------------------------------------------------------- */
/* 教学班演示快照的披露口径（比赛演示，⛔ 必须逐字可见）                        */
/* -------------------------------------------------------------------------- */

/**
 * 教学班演示快照的强制披露标签。
 *
 * 为什么需要它：被验收的 Course Data 行在**代码层**会被统一标记为 `data_source = real`
 * （已记录的 OPEN ITEM），因此页面上的这个标签是**唯一**的 Synthetic 披露面。
 * ⛔ 任何情况下都不得隐藏、折叠或改写该标签。
 */
export const SYNTHETIC_SNAPSHOT_LABEL = '教学班数据：演示快照（Synthetic）'

/**
 * 披露说明（**模式 2**：规划结果来自真实链路 `POST /api/v1/plan`）。
 *
 * 逐字口径：只声明“教学班是 Synthetic 演示快照”，其余链路仍在正式架构上执行。
 */
export const SYNTHETIC_SNAPSHOT_NOTE_REAL =
  '用于比赛演示；培养方案分析、约束规划、Path Repair 与风险解释仍通过实际系统链路执行。'

/**
 * 披露说明（**模式 1**：尚未提交真实规划，规划结果同样来自 Mock 演示通道）。
 *
 * ⛔ 不得在模式 1 下复用模式 2 的说明：那会把 Mock 规划结果说成正式链路产出。
 */
export const SYNTHETIC_SNAPSHOT_NOTE_MOCK =
  '用于比赛演示；当前尚未提交真实规划请求，培养要求评估、教学班与规划结果均来自 Mock 演示通道。'

/**
 * 教学班演示快照的限制说明（与 README / 启动文档同一口径，逐字）。
 */
export const SYNTHETIC_SNAPSHOT_LIMITATION =
  '由于学校教务系统北校园开课查询存在稳定的深分页异常，当前比赛版本的教学班演示使用经过明确标识的 Synthetic 快照。系统的培养方案解析、补修判定、约束规划、Path Repair、风险解释与前后端运行链路仍按正式架构执行。'


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
