/**
 * Real Planning 客户端（`POST /api/v1/plan`）的测试。
 *
 * ⚠️ 这些测试**不依赖真实后端**：`fetch` 全部被替换为 mocked fetch。
 * 核心红线：请求形状只有三个字段，且**绝不**回退到 Mock 通道。
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PlanApiError, fetchRealPlan } from '@/api/plan'
import { PLAN_ENDPOINT } from '@/config'
import { buildRealPlanRequest, createDefaultUserInputForm } from '@/state/userInput'
import type { PlanResult } from '@/types/contracts'

const PLAN_RESULT: PlanResult = {
  status: 'partially_feasible',
  selected_classes: [{ course_id: 'CSE201', class_id: 'CSE201-01' }],
  changes: [],
  risks: [],
  unresolved: [{ type: 'schedule_unknown', message: '排课信息未知' }],
  objective_summary: '测试用方案（mocked fetch，非真实后端）',
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('Real Planning 客户端', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('调用固定的 POST /api/v1/plan 并把 PlanResult 原样返回', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PLAN_RESULT))

    const request = buildRealPlanRequest(createDefaultUserInputForm())
    const result = await fetchRealPlan(request)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${PLAN_ENDPOINT}`)
    expect(url).toContain('/api/v1/plan')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(result).toEqual(PLAN_RESULT)
  })

  it('请求体只有 semester / current_schedule / preference 三个字段', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PLAN_RESULT))

    await fetchRealPlan(buildRealPlanRequest(createDefaultUserInputForm()))

    const [, init] = fetchMock.mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(Object.keys(body).sort()).toEqual(['current_schedule', 'preference', 'semester'])
    expect(Array.isArray(body.current_schedule)).toBe(true)
    expect(typeof body.preference).toBe('object')
    expect(Object.keys(body.preference).sort()).toEqual([
      'avoid_cross_campus',
      'avoid_times',
      'max_credit',
      'notes',
      'preferred_courses',
    ])
  })

  it('接口不可用（404）时如实抛错，且**不**回退到 Mock 通道', async () => {
    fetchMock.mockResolvedValue(new Response('Not Found', { status: 404 }))

    await expect(
      fetchRealPlan(buildRealPlanRequest(createDefaultUserInputForm())),
    ).rejects.toBeInstanceOf(PlanApiError)

    // 唯一一次请求必须是 Real 接口
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(url).not.toContain('/mock/')
    expect(url).not.toContain('demo')
  })

  it('网络失败时抛错，且不尝试任何 Mock 请求', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(
      fetchRealPlan(buildRealPlanRequest(createDefaultUserInputForm())),
    ).rejects.toBeInstanceOf(PlanApiError)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/mock/')
  })

  it('非 JSON 响应被拒绝', async () => {
    fetchMock.mockResolvedValue(new Response('<html>oops</html>', { status: 200 }))

    await expect(
      fetchRealPlan(buildRealPlanRequest(createDefaultUserInputForm())),
    ).rejects.toBeInstanceOf(PlanApiError)
  })

  it('数组响应被拒绝（PlanResult 必须是对象）', async () => {
    fetchMock.mockResolvedValue(jsonResponse([PLAN_RESULT]))

    await expect(
      fetchRealPlan(buildRealPlanRequest(createDefaultUserInputForm())),
    ).rejects.toBeInstanceOf(PlanApiError)
  })

  it('静态保证：Real client 源码不引用 Mock 通道', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/api/plan.ts'), 'utf-8')

    // 注释里出现 "mock/demo" 是**说明"绝不回退到 Mock"**，属于合规文档；
    // 因此这里去掉注释后再检查**可执行代码**中是否存在 Mock 通道引用。
    const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')

    expect(code).not.toContain('mock/demo')
    expect(code).not.toContain('DEMO_ENDPOINT')
    expect(code).not.toContain("from './demo'")
    expect(code).not.toContain('fetchDemo')
    // 只允许调用 Real 接口
    expect(code).toContain('PLAN_ENDPOINT')
  })
})
