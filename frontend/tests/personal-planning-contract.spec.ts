/**
 * 个人规划接口契约测试（**已实现的后端接口**）。
 *
 * 契约来源：`backend/app/api/personal_plan.py`
 * （`PersonalPlanBody` / `PersonalPlanResponse` / `CurriculumVersionListResponse`）。
 *
 * 覆盖 Review 关心的边界：
 * - 目录未配置 503 `personal_catalog_not_configured` ⇒ **不退回固定 Case A**；
 * - `planning = null` ⇒ 显示跳过原因码，⛔ 不显示"已排好课"；
 * - 请求体只含已声明字段（⛔ 不含身份信息）；
 * - `shouldApplyPersonalPlan` 只在**后端真的给出 planning** 时才允许接管当前方案。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  PERSONAL_CATALOG_NOT_CONFIGURED,
  PersonalPlanningApiError,
  fetchCurriculumVersions,
  parsePersonalPlanResult,
  shouldApplyPersonalPlan,
  submitPersonalPlan,
  type PersonalPlanResult,
} from '@/api/personalPlanning'

const VERSION = {
  version_id: 'v-2025-cs',
  major: '网络空间安全',
  cohort: '2025',
  campus: '东校园',
  track: null,
  source_id: 'CURR-NEW-004',
  verification_evidence: 'authenticated official',
  verified_by: 'owner',
  complete: true,
  completeness_evidence: 'manifest sha256',
  total_credit: 153,
  practice_credit: 38.5,
  study_years: 4,
  course_count: 42,
  group_count: 6,
}

const PLAN_RESULT = {
  status: 'partially_feasible',
  selected_classes: [{ course_id: 'DS101', class_id: 'ds-01' }],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: '受限 Planner 建议课表',
}

const PERSONAL_PLAN_RESPONSE = {
  old_version: { ...VERSION, version_id: 'v-2025-remote' },
  target_version: VERSION,
  data_source: 'mock',
  completed_source_id: 'personal-upload://sha256:abc',
  completed_record_count: 3,
  input_summary: { completed_record_count: 3, makeup_task_count: 2 },
  makeup_tasks: [
    {
      course_id: 'DS101',
      course_name: '数据结构',
      credit: 3,
      status: 'required',
      prerequisites: [],
    },
  ],
  status_counts: { required: 1 },
  planning: PLAN_RESULT,
  planning_skipped_reason: null,
  planning_skipped_code: null,
  assuming_course_ids: [],
  notes: [],
}

const PERSONAL_PLAN_SKIPPED = {
  ...PERSONAL_PLAN_RESPONSE,
  planning: null,
  planning_skipped_code: 'no_course_data',
  planning_skipped_reason: 'no_course_data: 当前没有已装配的真实教学班供给，因此没有调用 Planner。',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 打开真实通道（个人规划开关在测试环境默认关闭）。 */
async function loadRealPersonalPlanning() {
  vi.stubEnv('VITE_PERSONAL_PLANNING_API_ENABLED', 'true')
  vi.resetModules()
  return import('@/api/personalPlanning')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('个人规划：通道启用与目录 readiness', () => {
  it('通道未启用 ⇒ disabled，且不发请求（⛔ 不用演示数据顶替）', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchCurriculumVersions()).rejects.toMatchObject({ kind: 'disabled' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('目录未配置（503 personal_catalog_not_configured）⇒ not_configured 且带错误码', async () => {
    const adapter = await loadRealPersonalPlanning()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        jsonResponse(
          {
            detail: {
              error: 'personal_catalog_not_configured',
              message: '当前没有已核验的培养方案版本目录。',
            },
          },
          503,
        ),
      ),
    )

    const error = await adapter.fetchCurriculumVersions().catch((reason: unknown) => reason)
    expect(error).toBeInstanceOf(adapter.PersonalPlanningApiError)
    expect((error as PersonalPlanningApiError).kind).toBe('not_configured')
    expect((error as PersonalPlanningApiError).code).toBe(PERSONAL_CATALOG_NOT_CONFIGURED)
    expect((error as PersonalPlanningApiError).message).toContain('不会退回固定 Case A')
  })

  it('目录正常 ⇒ 返回可选版本与被拒条目', async () => {
    const adapter = await loadRealPersonalPlanning()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        jsonResponse({
          catalog_ready: true,
          catalog_reason: 'catalog_ready',
          selectable_count: 1,
          versions: [VERSION],
          rejected: [{ version_id: 'bad', code: 'not_verified', detail: '缺核验依据' }],
        }),
      ),
    )

    const list = await adapter.fetchCurriculumVersions()
    expect(list.versions).toHaveLength(1)
    expect(list.rejected[0]?.code).toBe('not_verified')
  })
})

describe('个人规划：提交与响应语义', () => {
  it('请求体只含已声明字段，且不含任何身份信息', async () => {
    const adapter = await loadRealPersonalPlanning()
    const mock = vi.fn(() => Promise.resolve(jsonResponse(PERSONAL_PLAN_RESPONSE)))
    vi.stubGlobal('fetch', mock)

    await adapter.submitPersonalPlan({
      old_version_id: 'v-2025-remote',
      target_version_id: 'v-2025-cs',
      semester: '2026-1',
      student: {
        completed: {
          records: [
            {
              course_id: 'MATH101',
              course_name: '高等数学',
              credit: 5,
              semester: '2024-1',
              passed: true,
            },
          ],
        },
      },
      current_schedule: [],
    })

    const [, init] = mock.mock.calls[0] as unknown as [string, RequestInit]
    const body = JSON.parse(init.body as string)
    expect(Object.keys(body).sort()).toEqual([
      'current_schedule',
      'old_version_id',
      'semester',
      'student',
      'target_version_id',
    ])

    const keys = new Set<string>()
    const collect = (value: unknown): void => {
      if (Array.isArray(value)) {
        value.forEach(collect)
        return
      }
      if (value !== null && typeof value === 'object') {
        for (const [key, child] of Object.entries(value)) {
          keys.add(key)
          collect(child)
        }
      }
    }
    collect(body)
    for (const banned of ['student_id', 'student_name', 'name', 'id_card', 'gpa']) {
      expect([...keys]).not.toContain(banned)
    }
  })

  it('planning = null 是**合法结果**：带 planning_skipped_code，⛔ 不报错也不显示"已排好课"', async () => {
    const adapter = await loadRealPersonalPlanning()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse(PERSONAL_PLAN_SKIPPED))))

    const result = await adapter.submitPersonalPlan({
      old_version_id: 'v-2025-remote',
      target_version_id: 'v-2025-cs',
      semester: '2026-1',
      student: {},
    })

    expect(result.planning).toBeNull()
    expect(result.planning_skipped_code).toBe('no_course_data')
    expect(result.makeup_tasks).toHaveLength(1)
    // ⛔ 补修任务仍然有效，但不能当作可执行课表
    expect(adapter.shouldApplyPersonalPlan(result)).toBe(false)
  })

  it('planning 非 null ⇒ 才允许接管当前方案', async () => {
    const adapter = await loadRealPersonalPlanning()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse(PERSONAL_PLAN_RESPONSE))))

    const result = await adapter.submitPersonalPlan({
      old_version_id: 'v-2025-remote',
      target_version_id: 'v-2025-cs',
      semester: '2026-1',
      student: {},
    })

    expect(result.planning?.selected_classes).toHaveLength(1)
    expect(adapter.shouldApplyPersonalPlan(result)).toBe(true)
  })

  it('422 personal_plan_not_projectable ⇒ not_projectable（既有 Curriculum 规则的结论）', async () => {
    const adapter = await loadRealPersonalPlanning()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        jsonResponse(
          { detail: { error: 'personal_plan_not_projectable', message: '组学分不足' } },
          422,
        ),
      ),
    )

    await expect(
      adapter.submitPersonalPlan({
        old_version_id: 'v-2025-remote',
        target_version_id: 'v-2025-cs',
        student: {},
      }),
    ).rejects.toMatchObject({ kind: 'not_projectable' })
  })

  it('503 personal_plan_course_data_unavailable ⇒ unavailable（不回退 Mock）', async () => {
    const adapter = await loadRealPersonalPlanning()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        jsonResponse(
          {
            detail: {
              error: 'personal_plan_course_data_unavailable',
              message: 'acceptance 已失效',
            },
          },
          503,
        ),
      ),
    )

    const error = await adapter.submitPersonalPlan({
      old_version_id: 'v-2025-remote',
      target_version_id: 'v-2025-cs',
      student: {},
    }).catch((reason: unknown) => reason)

    expect((error as PersonalPlanningApiError).kind).toBe('unavailable')
    expect((error as PersonalPlanningApiError).message).toContain('不返回任何规划结果')
  })
})

describe('个人规划：响应形状解析', () => {
  it('shouldApplyPersonalPlan 只认 planning 非 null（防御性纯函数）', () => {
    const withPlan = PERSONAL_PLAN_RESPONSE as unknown as PersonalPlanResult
    const withoutPlan = PERSONAL_PLAN_SKIPPED as unknown as PersonalPlanResult
    expect(shouldApplyPersonalPlan(withPlan)).toBe(true)
    expect(shouldApplyPersonalPlan(withoutPlan)).toBe(false)
  })

  it('parsePersonalPlanResult 拒绝缺 planning 字段的响应', () => {
    const { planning: _omitted, ...withoutPlanning } = PERSONAL_PLAN_RESPONSE
    expect(() => parsePersonalPlanResult(withoutPlanning)).toThrow()
  })
})
