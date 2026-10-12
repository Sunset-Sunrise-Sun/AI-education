/** 展示文案转换。原始响应不变，技术引用不渲染到学生页面。 */
/* 类型名称统一复用 labels，不修改原始响应。 */
import { unresolvedTypeLabel as labelForType } from './labels'

/** 用户语言的补充说明（告诉用户**该做什么**，而不是后端为什么这么判定）。 */
const UNRESOLVED_TYPE_HINT: Record<string, string> = {
  manual_confirmation: '系统发现该课程可能需要补修，请确认是否纳入规划。',
  selection_required: '请选择对应课程或教学班后重新生成方案。',
  missing_data: '课程信息不完整，请补充后再生成方案。',
  schedule_unknown: '上课时间尚未确定，请核实后再生成方案。',
  conflict: '存在时间冲突，请调整后重新生成方案。',
  unmatched_course: '尚未找到对应课程，请通过教学班搜索选择。',
}

export function unresolvedTypeLabel(type: string | null | undefined): string {
  const key = (type ?? '').trim()
  return labelForType(key)
}

export function unresolvedTypeHint(type: string | null | undefined): string {
  const key = (type ?? '').trim()
  return UNRESOLVED_TYPE_HINT[key] ?? '请查看详情并核实相关信息。'
}

/**
 * 是否为**技术性**证据字符串。
 *
 * 判定依据只看「是不是后端内部引用 / 定位信息」：
 * URL scheme（`xxx://`）、内容摘要（`sha256:` / `sha1:`）、表格坐标（`table:N,row:N`）、
 * 上传引用（`upload:` / `capture:`）。
 * ⛔ 不按"看起来像不像技术词"做模糊判断。
 */
export function isTechnicalEvidence(value: string): boolean {
  const text = value.trim()
  if (text === '') {
    return false
  }
  return (
    /[a-z][a-z0-9+.-]*:\/\//i.test(text)
    || /\b(sha256|sha1|md5)\s*:/i.test(text)
    || /\btable:\s*\d+\s*,\s*row:\s*\d+/i.test(text)
    || /\bupload:/i.test(text)
    || /\bcapture:/i.test(text)
  )
}

/** 一条待确认事项的**展示用**形状。 */
export interface DisplayUnresolvedItem {
  readonly type: string
  readonly label: string
  readonly hint: string
  /** 已过滤掉纯技术引用后的可见说明；仍为空则渲染回落文案。 */
  readonly message: string
  /** 被折叠的技术证据（用户点「查看详情」才展示）。 */
  readonly technicalEvidence: readonly string[]
  /** 原始 type，仅供折叠区与排障，⛔ 不在主文案里出现。 */
  readonly rawType: string
}

/**
 * 把 Planner 的 `unresolved` 列表转成**用户语言**。
 *
 * ⚠️ 幂等：可以安全地对同一份数据重复调用。
 * ⛔ 不改动机字段，只做文案映射与证据分流。
 */
export function toDisplayUnresolved(
  unresolved: readonly {
    type?: string
    message?: string
    evidence?: readonly string[]
  }[] | null | undefined,
): DisplayUnresolvedItem[] {
  return (unresolved ?? []).map((item) => {
    const rawType = (item.type ?? '').trim()
    const evidence = item.evidence ?? []
    const technicalEvidence = evidence.filter(isTechnicalEvidence)
    const readable = evidence.filter((value) => !isTechnicalEvidence(value))

    // 说明文案优先用 message（后端已给人类可读描述），
    // 但若 message 本身是技术引用则不展示，改用类型对应的用户语言说明。
    const message = (item.message ?? '').trim()
    const safeMessage = isTechnicalEvidence(message)
      ? ''
      : message.length > 0
        ? message
        : readable.join('；')

    return {
      type: rawType,
      label: unresolvedTypeLabel(rawType),
      hint: unresolvedTypeHint(rawType),
      message: safeMessage,
      technicalEvidence,
      rawType,
    }
  })
}

/** 仅用于页面文本。技术引用不进入 DOM，原始响应保持不变。 */
export function studentText(value: string | null | undefined, fallback = ''): string {
  const text = value?.trim() ?? ''
  if (!text || isTechnicalEvidence(text)
    || /\b(?:type|unresolved|provenance|data_source|source_evidence|manual_confirmation|selection_required|missing_data|selected_classes|RestrictedPlanner|PlanResult)\b|\b[a-f0-9]{32,64}\b|\btable\s+row\b|(?:[A-Z]:\\|\/(?:home|tmp|Users)\/)/i.test(text)) return fallback
  return text
}
