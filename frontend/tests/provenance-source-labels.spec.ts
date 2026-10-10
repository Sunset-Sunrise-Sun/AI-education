/**
 * 来源可信性文案契约（⚠️ 本轮新增，F-05 / F-07）。
 *
 * 这两条要求必须在**前端**也成立：
 *
 * 1. `real_unverified`（自述 real、服务端未核验）⛔ 不得显示成"已核验真实教务数据"；
 * 2. "真实 HTTP 请求成功"与"使用了已核验真实教务数据"必须能区分。
 */

import { describe, expect, it } from 'vitest'

import { DATA_SOURCES, parseDataSource, parseInterpretResponse } from '../src/api/aiPlanningContract'
import { dataSourceLabel } from '../src/composables/useAiPlanning'
import { PREVIEW_INTERPRET_OK } from '../src/api/aiPlanningFixtures'

describe('data_source 取值域', () => {
  it('包含服务端新增的 real_unverified', () => {
    expect(DATA_SOURCES).toContain('real_unverified')
  })

  it('接受 real_unverified（⛔ 不能把它当成未知取值拒绝）', () => {
    expect(parseDataSource('real_unverified')).toBe('real_unverified')
  })

  it('仍然拒绝未知取值（fail closed）', () => {
    expect(() => parseDataSource('real_looking')).toThrow()
  })
})

describe('dataSourceLabel', () => {
  it('real_unverified 必须明确写出"未经服务端独立核验"', () => {
    const label = dataSourceLabel('real_unverified')
    expect(label).toContain('未经服务端独立核验')
    // ⛔ 不得与"已核验"的说法混淆
    expect(label).not.toContain('服务端已核验来源')
  })

  it('real 才允许出现"服务端已核验来源"', () => {
    expect(dataSourceLabel('real')).toContain('服务端已核验来源')
  })

  it('unknown 仍然明确"不代表 real"', () => {
    expect(dataSourceLabel('unknown')).toContain('不代表 real')
  })

  it('mock 不受影响', () => {
    expect(dataSourceLabel('mock')).toContain('mock')
  })
})

describe('interpret 响应解析', () => {
  it('context_source_verified 缺字段一律按未核验（fail closed）', () => {
    const payload = { ...PREVIEW_INTERPRET_OK } as Record<string, unknown>
    delete payload['context_source_verified']

    expect(parseInterpretResponse(payload).context_source_verified).toBe(false)
  })

  it('显式 false / true 原样保留', () => {
    expect(
      parseInterpretResponse({ ...PREVIEW_INTERPRET_OK, context_source_verified: false })
        .context_source_verified,
    ).toBe(false)
    expect(
      parseInterpretResponse({ ...PREVIEW_INTERPRET_OK, context_source_verified: true })
        .context_source_verified,
    ).toBe(true)
  })

  it('非布尔值被拒绝', () => {
    expect(() =>
      parseInterpretResponse({ ...PREVIEW_INTERPRET_OK, context_source_verified: 'true' }),
    ).toThrow()
  })
})
