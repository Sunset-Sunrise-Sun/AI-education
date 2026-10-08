/**
 * 解释面板的**纯展示**文案映射。
 *
 * 重要原则：
 * - 前端只翻译后端已经给出的字段，**不新增**任何业务判断；
 * - `rule_based_template` 必须显示为「规则模板」而不是「AI」，
 *   只有后端明确说 `model` 时才显示模型生成；
 * - 未知取值一律安全 fallback（原样显示），不猜测含义。
 */

import type {
  EvidenceKind,
  EvidenceStrength,
  ExplanationItemKind,
  GeneratorKind,
} from '../api/explanation'

/** 证据性质：对应任务书的「确证规则 / 学生输入或假设 / 系统建议 / 未知」。 */
export const EVIDENCE_KIND_LABEL: Record<EvidenceKind, string> = {
  confirmed_rule: '确证规则',
  student_input_or_assumption: '学生输入或假设',
  system_suggestion: '系统建议',
  unknown: '未知',
  absent: '上下文不存在',
}

export const EVIDENCE_KIND_HINT: Record<EvidenceKind, string> = {
  confirmed_rule: '来自模块给出的判定字段；本解释只转述，不代替人工确认学校正式规则。',
  student_input_or_assumption: '来自学生输入或输入中的假设 / 演示数据。',
  system_suggestion: '来自系统或算法的建议（例如 Planner 的调班原因），不是学校规则。',
  unknown: '当前来源无法支持该关系，需要人工确认。',
  absent: '该字段在当前上下文中根本不存在——这与「值为空」不是一回事。',
}

export const EVIDENCE_STRENGTH_LABEL: Record<EvidenceStrength, string> = {
  confirmed: '已确证',
  partial: '部分确证',
  unknown: '未知',
  absent: '不存在',
}

export const ITEM_KIND_LABEL: Record<ExplanationItemKind, string> = {
  plan_status: '整体方案',
  makeup_task: '补修判定',
  selected_class: '教学班安排',
  change: '调班原因',
  risk: '风险提示',
  unresolved: '未解决事项',
}

/**
 * 生成方式的展示标签。
 *
 * ⚠️ 这是**最容易误导用户**的一处，因此：
 * - 只有后端明确返回 `model` 才显示「AI 模型」；
 * - `rule_based_template` 显示「规则模板（非 AI）」；
 * - 降级情况显示「规则模板（模型未采用）」并展示降级原因。
 */
export function generatorKindLabel(kind: GeneratorKind | string): string {
  switch (kind) {
    case 'model':
      return 'AI 模型生成'
    case 'rule_based_template':
      return '规则模板（非 AI）'
    case 'model_unavailable_fell_back_to_template':
      return '规则模板（模型未采用）'
    default:
      return `未知生成方式（${kind}）`
  }
}

export function generatorKindTagClass(kind: GeneratorKind | string): string {
  switch (kind) {
    case 'model':
      return 'tag--generator-model'
    case 'rule_based_template':
      return 'tag--generator-template'
    case 'model_unavailable_fell_back_to_template':
      return 'tag--generator-fallback'
    default:
      return 'tag--generator-unknown'
  }
}

/** 事实目录里的字段来源展示成 `对象.字段`。 */
export function evidenceSourceLabel(sourceObject: string, sourceField: string): string {
  return `${sourceObject}.${sourceField}`
}

/** `raw_value` 为空时区分「不存在」与「空字符串」，避免把两者混为一谈。 */
export function evidenceValueLabel(kind: EvidenceKind | string, rawValue: string): string {
  if (rawValue !== '') {
    return rawValue
  }
  return kind === 'absent' ? '（该字段在当前上下文中不存在）' : '（空字符串）'
}
