/**
 * 培养方案年级（Plan year）——**纯前端状态**。
 *
 * ## ⚠️ 诚实声明（很重要）
 *
 * 当前后端**不支持**提交培养方案年级：`buildRealPlanRequest` 只发送
 * `semester` / `current_schedule` / `preference`，没有年级字段。
 * 因此本模块只负责**前端展示与状态管理**，
 * ⛔ 不私改接口，⛔ 也不声称规划已按所选年级完成计算。
 *
 * ## 本轮只启用 2025 级
 *
 * 本轮提供的样本都是 **2025 平转 2025**，所以只有 `2025级` 是**有数据支持**的年份。
 * `2026级` 只作为**未来扩展占位**登记在 `FUTURE_PLAN_YEARS` 里，
 * ⛔ 不会被渲染成可选下拉项 —— 因为让用户选中一个没有培养方案数据的年级，
 * 再"继续生成结果"，等于假装数据存在。
 */

/** 培养方案年级的取值形状，例如 `2025级`。 */
export type PlanYearValue = `${number}级`

/** 本轮**唯一有数据支持**的培养方案年级。 */
export const SUPPORTED_PLAN_YEARS = ['2025级'] as const
export type SupportedPlanYear = (typeof SUPPORTED_PLAN_YEARS)[number]

/** 默认培养方案年级（两个字段独立使用同一个默认值，⛔ 不共用同一个字段）。 */
export const DEFAULT_PLAN_YEAR: SupportedPlanYear = '2025级'

/**
 * 未来可扩充的年级（**占位，⛔ 尚未有数据**）。
 *
 * ⚠️ 刻意与 `SUPPORTED_PLAN_YEARS` 分开：
 * 需要真正支持某一年时，把它**移入** `SUPPORTED_PLAN_YEARS`，
 * 并同时补齐该年的培养方案数据；⛔ 不得只改这里就让它可选。
 */
export const FUTURE_PLAN_YEARS: readonly PlanYearValue[] = ['2026级']

/** 转专业类型。 */
export type TransferType = '同级转专业' | '降级转专业' | '升级转专业'

/** 年级是否**有数据支持**（⛔ 渲染下拉项与生成结果都必须先过这一关）。 */
export function isSupportedPlanYear(value: string): value is SupportedPlanYear {
  return (SUPPORTED_PLAN_YEARS as readonly string[]).includes(value)
}

/**
 * 由两个年级推出转专业类型。
 *
 * ⚠️ 这只是**展示用的归类**，⛔ 不参与任何业务规则、⛔ 不改判定。
 */
export function deriveTransferType(originYear: string, targetYear: string): TransferType {
  const origin = Number.parseInt(originYear, 10)
  const target = Number.parseInt(targetYear, 10)
  if (!Number.isFinite(origin) || !Number.isFinite(target)) {
    return '同级转专业'
  }
  if (origin === target) {
    return '同级转专业'
  }
  // 目标年级更晚 ⇒ 需要补更多课 ⇒ 降级转专业
  return target > origin ? '降级转专业' : '升级转专业'
}

/** 卡片底部的简短摘要，例如 `2025 平转 2025`。 */
export function describePlanYearPair(originYear: string, targetYear: string): string {
  const origin = Number.parseInt(originYear, 10)
  const target = Number.parseInt(targetYear, 10)
  const flat = Number.isFinite(origin) && Number.isFinite(target) && origin === target
  const verb = flat ? '平转' : target > origin ? '降转' : '升转'
  return `${originYear} ${verb} ${targetYear}`
}

/** 一行说明，用于卡片底部（含"其它年级需补数据"的如实说明）。 */
export function describePlanYearScope(
  originYear: string, targetYear: string, originMajor: string, targetMajor: string,
): string {
  const origin = Number.parseInt(originYear, 10)
  const target = Number.parseInt(targetYear, 10)
  return `${origin} → ${target}：${originMajor} → ${targetMajor}`
}

/** 两个年级是否**都**有数据支持（两个字段分别判定，⛔ 不共用）。 */
export function bothPlanYearsSupported(originYear: string, targetYear: string): boolean {
  return isSupportedPlanYear(originYear) && isSupportedPlanYear(targetYear)
}
