/**
 * AI 抽屉头部的**能力状态文案**（纯函数，便于穷举测试）。
 *
 * ## 为什么单独抽出来
 *
 * 头部原来把 `enabled / api_key_configured / live_model_available / model`
 * 直接铺在一行，375px 下会挤成两三行、普通用户读不懂。
 * 现在的做法是：**一句话摘要**给普通用户，**原始字段**收进可展开的"技术详情"。
 *
 * 由此产生的硬要求是"文案不能因为简洁而变得不准确"，尤其是：
 *
 * - `live_model_available=true` **只**表示"开关已开 + 密钥已配置"，
 *   ⛔ 不等于在线鉴权成功、⛔ 不等于模型调用成功；
 * - 通道为**前端预览**时状态来自 fixture，⛔ 不能说成服务端能力；
 * - "未启用 / 无密钥 / 无可用模型 / 状态未知"必须**逐档区分**，⛔ 不合并、不美化。
 *
 * 这些都是**穷举文本分支**，所以抽成纯函数后可以逐一锁定。
 * ⛔ 本模块只读布尔与模型名，⛔ 不接触、不拼接、不记录任何密钥值。
 */

import type { AiPlanningStatusResponse } from '../../api/aiPlanningContract'

export interface CapabilityFact {
  label: string
  value: string
}

export interface CapabilityDescription {
  /** 面向普通用户的一句话状态。 */
  summary: string
  /** 技术详情里的原始字段（逐项说明）。 */
  facts: CapabilityFact[]
}

/**
 * 通道完全不可用（既没开真实接口，也没开预览）时的说明。
 *
 * 此时**不会**发起 `/status` 请求，因此没有任何状态可展示——
 * ⛔ 不能显示"看起来可用"的默认文案。
 */
export const CAPABILITY_DISABLED_SUMMARY =
  '未启用 AI 调整接口，也没有可用的演示数据；本次不能进行任何调整'

/** 状态尚未取得时的说明。 */
export const CAPABILITY_UNKNOWN_SUMMARY = '尚未取得服务端状态'

/**
 * 把后端 `/status` 响应（或"没有响应"）翻译成一句人话 + 技术详情。
 *
 * @param status  `/status` 的解析结果；`null` 表示尚未取得（请求中 / 失败 / 未发请求）
 * @param options `previewEnabled=true` 表示状态来自前端 fixture，不是服务端能力
 */
export function describeCapability(
  status: AiPlanningStatusResponse | null,
  options: { previewEnabled: boolean },
): CapabilityDescription {
  if (options.previewEnabled) {
    return {
      summary: '当前为演示模式：状态与结果都是前端预览 fixture，未调用后端服务',
      facts: [],
    }
  }
  if (status === null) {
    return { summary: CAPABILITY_UNKNOWN_SUMMARY, facts: [] }
  }
  return { summary: summarizeEnabledState(status), facts: buildFacts(status) }
}

/** 后端已返回状态时的摘要（⛔ 四档互不混淆）。 */
function summarizeEnabledState(status: AiPlanningStatusResponse): string {
  if (!status.enabled) {
    return '服务端未启用 AI 调整，本次不能生成候选'
  }
  if (!status.api_key_configured) {
    return '已启用，但服务端没有配置模型密钥，本次不能解析需求'
  }
  if (status.live_model_available) {
    return '服务端已启用且已注入模型密钥；配置就绪不代表在线调用已经成功'
  }
  return '已启用，但当前没有可用的在线模型，本次不能解析需求'
}

/**
 * 技术详情：完整保留原始字段，并逐条写明含义（⛔ 不含密钥内容）。
 *
 * 标签采用"中文说明（原始字段名）"的形式：
 * 普通用户看得懂中文，需要排障的人一眼能对上后端的字段名。
 */
function buildFacts(status: AiPlanningStatusResponse): CapabilityFact[] {
  return [
    { label: '服务端开关（enabled）', value: String(status.enabled) },
    { label: '已注入模型密钥（api_key_configured）', value: String(status.api_key_configured) },
    {
      label: '在线模型可用（live_model_available）',
      value: `${String(status.live_model_available)}（仅表示开关与密钥就绪，不代表已成功调用）`,
    },
    { label: '模型名（model）', value: status.model },
    { label: '接口地址（base_url）', value: status.base_url },
    {
      label: '单次请求最大模型调用次数（max_calls_per_request）',
      value: String(status.max_calls_per_request),
    },
    {
      label: '单次调用超时秒数（request_timeout_seconds）',
      value: String(status.request_timeout_seconds),
    },
    { label: '候选采用有效期秒数（adopt_ttl_seconds）', value: String(status.adopt_ttl_seconds) },
  ]
}
