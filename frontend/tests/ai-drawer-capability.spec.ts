/**
 * AI 抽屉头部"能力状态文案"的**穷举**测试。
 *
 * 任务书要求（P1 修复移动端头部信息密度）：
 * 1. 改成普通用户能理解的简洁状态摘要；
 * 2. 提供可展开的"技术详情"，完整保留原始状态信息；
 * 3. **准确区分**未启用 / 未注入密钥 / 测试模型 / 真实模型 / 服务不可用；
 * 4. 不把 `live_model_available=true` 等同于"DeepSeek 在线调用已成功"；
 * 5. ⛔ 不泄露密钥。
 *
 * 这些是**文本分支**，所以这里逐档锁定，防止以后"为了简洁"把边界说模糊。
 */

import { describe, expect, it } from 'vitest'
import {
  CAPABILITY_DISABLED_SUMMARY,
  CAPABILITY_UNKNOWN_SUMMARY,
  describeCapability,
} from '@/components/ai/drawerCapability'
import type { AiPlanningStatusResponse } from '@/api/aiPlanningContract'

/** 一份"配置齐全"的 `/status` 响应（字段与后端契约一致）。 */
function status(overrides: Partial<AiPlanningStatusResponse> = {}): AiPlanningStatusResponse {
  return {
    enabled: true,
    live_model_available: true,
    api_key_configured: true,
    model: 'deepseek-flash',
    base_url: 'https://api.deepseek.com',
    max_calls_per_request: 3,
    request_timeout_seconds: 20,
    adopt_ttl_seconds: 900,
    generator_kind_when_live: 'deepseek_live',
    data_source_note: '上下文 data_source 由教学班自身的 data_source 判定。',
    ...overrides,
  }
}

describe('抽屉头部：能力状态摘要（逐档区分，⛔ 不模糊边界）', () => {
  it('通道完全不可用 ⇒ 有独立文案，且⛔ 不冒充可用', () => {
    expect(CAPABILITY_DISABLED_SUMMARY).toContain('未启用')
    expect(CAPABILITY_DISABLED_SUMMARY).toContain('不能')
  })

  it('尚未取得状态 ⇒ 明确说"尚未取得"，⛔ 不给乐观默认值', () => {
    const result = describeCapability(null, { previewEnabled: false })
    expect(result.summary).toBe(CAPABILITY_UNKNOWN_SUMMARY)
    expect(result.summary).toContain('尚未取得')
    expect(result.facts).toEqual([])
  })

  it('预览模式 ⇒ 说明状态来自 fixture，⛔ 不说成服务端能力', () => {
    // 即使"看起来"配置齐全，预览模式也必须按演示模式说明
    const result = describeCapability(status(), { previewEnabled: true })
    expect(result.summary).toContain('演示模式')
    expect(result.summary).toContain('前端预览')
    expect(result.summary).toContain('未调用后端服务')
  })

  it('服务端未启用 ⇒ 摘要说未启用、不能生成候选（⛔ 不出现"成功/候选"）', () => {
    const result = describeCapability(status({ enabled: false }), { previewEnabled: false })
    expect(result.summary).toBe('服务端未启用 AI 调整，本次不能生成候选')
    expect(result.summary).not.toContain('成功')
  })

  it('已启用但未注入密钥 ⇒ 指出缺密钥，⛔ 不暗示能解析', () => {
    const result = describeCapability(
      status({ enabled: true, api_key_configured: false, live_model_available: false }),
      { previewEnabled: false },
    )
    expect(result.summary).toBe('已启用，但服务端没有配置模型密钥，本次不能解析需求')
  })

  it('有密钥但无可用在线模型 ⇒ 与"无密钥"是**不同**的一档', () => {
    const noKey = describeCapability(status({ api_key_configured: false }), {
      previewEnabled: false,
    })
    const noModel = describeCapability(
      status({ api_key_configured: true, live_model_available: false }),
      { previewEnabled: false },
    )
    expect(noModel.summary).toBe('已启用，但当前没有可用的在线模型，本次不能解析需求')
    expect(noModel.summary).not.toBe(noKey.summary)
  })

  it('配置就绪（live_model_available=true）⇒ ⛔ 不得宣称在线调用已成功', () => {
    const result = describeCapability(status(), { previewEnabled: false })
    expect(result.summary).toContain('配置就绪')
    expect(result.summary).toContain('不代表在线调用已经成功')
    expect(result.summary).not.toContain('在线模型已接入')
    expect(result.summary).not.toContain('调用成功')
    expect(result.summary).not.toContain('DeepSeek 已接入')
  })
})

describe('抽屉头部：技术详情（完整保留原始字段）', () => {
  it('原始字段逐项保留，并解释 live_model_available 的真实含义', () => {
    const facts = describeCapability(status(), { previewEnabled: false }).facts
    const labels = facts.map((item) => item.label).join(' | ')
    for (const key of [
      'enabled',
      'api_key_configured',
      'live_model_available',
      'model',
      'base_url',
      'max_calls_per_request',
      'request_timeout_seconds',
      'adopt_ttl_seconds',
    ]) {
      expect(labels).toContain(key)
    }
    const live = facts.find((item) => item.label.includes('live_model_available'))
    expect(live?.value).toContain('true')
    expect(live?.value).toContain('不代表已成功调用')
  })

  it('⛔ 技术详情不含任何密钥形态的字符串', () => {
    const facts = describeCapability(status(), { previewEnabled: false }).facts
    const text = facts.map((item) => `${item.label}=${item.value}`).join('\n')
    expect(text).not.toMatch(/sk-[A-Za-z0-9]/)
    expect(text).not.toContain('DEEPSEEK_API_KEY=')
    expect(text).not.toMatch(/api[_-]?key\s*[:=]\s*["']?[A-Za-z0-9]{8,}/i)
  })

  it('预览模式不展示服务端技术详情（没有真实状态可展示）', () => {
    const result = describeCapability(status(), { previewEnabled: true })
    expect(result.facts).toEqual([])
  })
})
