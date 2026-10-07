/**
 * 学期学分负荷标签（**产品级**口径，⛔ 不是学校政策声明）。
 *
 * ```text
 * <= 26     正常
 * 26 – 30   较满
 * 30 – 35   很满
 * > 35      ⛔ 不应产生（后端未来学期硬上限为 35）
 * ```
 *
 * ⚠️ 当前学期与未来学期的上限**不同**：
 * 当前学期 section-level 上限 30，未来学期硬上限 35。⛔ 不要混用两个阈值。
 */

export type LoadTone = 'normal' | 'full' | 'heavy' | 'over'

export interface LoadLabel {
  text: string
  tone: LoadTone
}

export const FUTURE_SOFT_TARGET_CREDIT = 26
export const FUTURE_HARD_MAX_CREDIT = 35
export const CURRENT_HARD_MAX_CREDIT = 30

export function loadLabel(total: number): LoadLabel {
  if (total <= FUTURE_SOFT_TARGET_CREDIT) return { text: '正常', tone: 'normal' }
  if (total <= 30) return { text: '较满', tone: 'full' }
  if (total <= FUTURE_HARD_MAX_CREDIT) return { text: '很满', tone: 'heavy' }
  return { text: '超出上限', tone: 'over' }
}
