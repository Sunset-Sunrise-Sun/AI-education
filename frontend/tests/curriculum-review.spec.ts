/**
 * 课程分类审核的**前端契约与交互**测试（本轮指令 §二.C、§二.D）。
 *
 * 重点覆盖边界：
 * 1. ⛔ 前端不提交证据 / 课程原文 / SHA-256；
 * 2. ⛔ 无证据 / 冲突项不能一键确认（按钮禁用 + 服务端拒绝映射成固定文案）；
 * 3. 人工修改必须填理由；
 * 4. ⛔ 拒绝 = 暂缓，不自动改判；
 * 5. ⛔ 页面不出现"已认证 / 已完成课程认定"这类不实结论。
 */

import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import {
  CANDIDATE_STATUS_LABEL,
  REVIEW_ERROR_LABEL,
  ReviewApiError,
  exportReviewDraft,
  fetchReviewSession,
  parseReviewSession,
  submitReviewDecisions,
} from '../src/api/curriculumReview'
import CurriculumReviewPanel from '../src/components/CurriculumReviewPanel.vue'

function _sessionPayload(overrides: Record<string, unknown> = {}) {
  return {
    review_id: 'rid-abc',
    document: {
      key: 'yuangan-2025',
      major: '遥感科学与技术',
      cohort: '2025',
      role: 'origin',
      file_name: 'curriculum.pdf',
      source_id: 'pdf-upload:sha256:abc',
      source_sha256: 'a'.repeat(64),
    },
    candidates: [
      {
        course_id: 'GST101',
        source_record: 'page:5!table:2!row:2',
        proposed_requirement: 'required',
        proposed_category_code: '专必',
        status: 'single_source',
        evidence_complete: true,
        evidence: [
          {
            kind: 'practice_appendix',
            category_code: '专必',
            requirement: 'required',
            source_record: 'page:8!table:1!row:1',
            raw_text: 'GST101 | 专必',
            minimum_credit: null,
          },
        ],
        decision: null,
        resubmissions: 0,
      },
      {
        course_id: 'GST999',
        source_record: 'page:6!table:1!row:5',
        proposed_requirement: 'unknown',
        proposed_category_code: null,
        status: 'no_evidence',
        evidence_complete: false,
        evidence: [],
        decision: null,
        resubmissions: 0,
      },
      {
        course_id: 'GST213',
        source_record: 'page:4!table:1!row:2',
        proposed_requirement: 'unknown',
        proposed_category_code: null,
        status: 'conflicting',
        evidence_complete: false,
        evidence: [
          {
            kind: 'practice_appendix', category_code: '专必', requirement: 'required',
            source_record: 'page:8!table:1!row:3', raw_text: 'GST213 | 专必',
            minimum_credit: null,
          },
          {
            kind: 'practice_appendix', category_code: '专选', requirement: 'elective',
            source_record: 'page:8!table:1!row:9', raw_text: 'GST213 | 专选',
            minimum_credit: null,
          },
        ],
        decision: null,
        resubmissions: 0,
      },
    ],
    category_requirements: [
      {
        category_code: '专必',
        requirement: 'required',
        minimum_credit: 78,
        source_record: 'page:1!table:1!row:3',
        raw_text: '专必 | 78',
      },
    ],
    section_rows: [{ source_record: 'page:5!table:2!row:1', raw_text: '专业选修课模块' }],
    unmapped_category_codes: ['荣誉课程'],
    progress: {
      total_candidates: 3,
      confirmed: 0,
      overridden: 0,
      deferred: 0,
      undecided: 3,
      by_status: { single_source: 1, conflicting: 1, no_evidence: 1 },
      conflicting: 1,
      no_evidence: 1,
      section_rows: 1,
      unmapped_category_codes: ['荣誉课程'],
      verification_verified: false,
      conclusion: 'pending_group_lead_review',
    },
    expires_in_seconds: 7200,
    notes: ['本页的审核决定是**内部草稿**。'],
    ...overrides,
  }
}

describe('parseReviewSession（契约）', () => {
  it('解析合法响应', () => {
    const session = parseReviewSession(_sessionPayload())
    expect(session.review_id).toBe('rid-abc')
    expect(session.candidates).toHaveLength(3)
    expect(session.progress.undecided).toBe(3)
  })

  it('缺 review_id / candidates / progress ⇒ 契约错误（⛔ 不当成空结果）', () => {
    expect(() => parseReviewSession({})).toThrow(ReviewApiError)
    expect(() =>
      parseReviewSession({ ..._sessionPayload(), review_id: undefined }),
    ).toThrow()
    expect(() =>
      parseReviewSession({ ..._sessionPayload(), candidates: undefined }),
    ).toThrow()
    expect(() =>
      parseReviewSession({ ..._sessionPayload(), progress: undefined }),
    ).toThrow()
  })
})

describe('fetchReviewSession / submitReviewDecisions', () => {
  it('关闭开关时直接拒绝，⛔ 不发请求', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
    await expect(fetchReviewSession('rid', { enabled: false })).rejects.toMatchObject({
      kind: 'disabled',
    })
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('GET 用 review_id 拼路径并做 URL 编码', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(_sessionPayload()), { status: 200 }),
    )
    await fetchReviewSession('a/b c', { enabled: true })
    const [url] = spy.mock.calls[0] as [string]
    expect(url).toContain('/api/v1/curriculum-review/a%2Fb%20c')
    spy.mockRestore()
  })

  it('⛔ 只提交 source_record / action / requirement / reason', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(_sessionPayload()), { status: 200 }),
    )
    await submitReviewDecisions(
      'rid',
      [{ source_record: 'page:5!table:2!row:2', action: 'confirm' }],
      { enabled: true },
    )
    const [, init] = spy.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(String(init.body)) as { decisions: Record<string, unknown>[] }
    expect(Object.keys(body.decisions[0]!).sort()).toEqual(['action', 'source_record'])
    // ⛔ 绝不能出现证据 / 摘要 / 课程原文
    const text = String(init.body)
    for (const forbidden of ['evidence', 'source_sha256', 'raw_text', 'course_name']) {
      expect(text).not.toContain(forbidden)
    }
    spy.mockRestore()
  })

  it('服务端固定错误码映射成固定文案（⛔ 不回显后端细节）', async () => {
    for (const [code, kind] of [
      ['review_confirm_not_allowed', 'confirm_not_allowed'],
      ['review_override_requires_reason', 'override_requires_reason'],
      ['review_unknown_source_record', 'unknown_source_record'],
      ['review_not_found', 'not_found'],
      ['review_capacity_reached', 'capacity'],
    ] as const) {
      const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify({ detail: { error: code, message: '内部细节' } }), {
          status: 400,
        }),
      )
      await expect(
        submitReviewDecisions('rid', [
          { source_record: 'x', action: 'confirm' },
        ], { enabled: true }),
      ).rejects.toMatchObject({ kind })
      spy.mockRestore()
    }
  })

  it('导出返回原始对象，⛔ 前端不改写', async () => {
    const record = {
      conclusion: 'pending_group_lead_review',
      verification: { verified: false, evidence: null },
      unresolved_items: [],
    }
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(record), { status: 200 }),
    )
    const out = await exportReviewDraft('rid', { enabled: true })
    expect(out).toEqual(record)
    spy.mockRestore()
  })
})

describe('CurriculumReviewPanel（界面）', () => {
  async function mounted() {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(_sessionPayload()), { status: 200 }),
    )
    const wrapper = mount(CurriculumReviewPanel, { props: { reviewId: 'rid-abc' } })
    await wrapper.find('[data-testid="review-load"]').trigger('click')
    await vi.waitFor(() => {
      expect(wrapper.find('[data-testid="review-candidates"]').exists()).toBe(true)
    })
    return { wrapper, spy }
  }

  it('声明这是未认证、未批准的**草稿**', async () => {
    const { wrapper, spy } = await mounted()
    const text = wrapper.find('[data-testid="review-boundary"]').text()
    expect(text).toContain('未')
    expect(text).toContain('草稿')
    expect(text).toContain('不作为正式个人补修规划的放行依据')
    spy.mockRestore()
  })

  it('⛔ 不出现"已获学校认证 / 已完成正式课程认定"这类不实结论', async () => {
    const { wrapper, spy } = await mounted()
    const text = wrapper.text()
    for (const forbidden of ['已获学校认证', '已完成正式课程认定', '来源已核验', '已批准']) {
      expect(text).not.toContain(forbidden)
    }
    spy.mockRestore()
  })

  it('展示候选、状态与来源定位', async () => {
    const { wrapper, spy } = await mounted()
    const row = wrapper.find('[data-testid="review-row-page:5!table:2!row:2"]')
    expect(row.exists()).toBe(true)
    expect(row.text()).toContain('GST101')
    expect(row.text()).toContain(CANDIDATE_STATUS_LABEL.single_source)
    spy.mockRestore()
  })

  it('无证据 / 冲突项**不能**一键确认（按钮禁用）', async () => {
    const { wrapper, spy } = await mounted()
    const noEvidence = wrapper.find('[data-testid="review-confirm-page:6!table:1!row:5"]')
    const conflicting = wrapper.find('[data-testid="review-confirm-page:4!table:1!row:2"]')
    expect(noEvidence.attributes('disabled')).toBeDefined()
    expect(conflicting.attributes('disabled')).toBeDefined()
    // 有明确依据的可以确认
    const ok = wrapper.find('[data-testid="review-confirm-page:5!table:2!row:2"]')
    expect(ok.attributes('disabled')).toBeUndefined()
    spy.mockRestore()
  })

  it('冲突项的两条证据都展示（⛔ 不取舍）', async () => {
    const { wrapper, spy } = await mounted()
    const block = wrapper.find('[data-testid="review-evidence-page:4!table:1!row:2"]')
    expect(block.exists()).toBe(true)
    const html = block.html()
    expect(html).toContain('GST213 | 专必')
    expect(html).toContain('GST213 | 专选')
    spy.mockRestore()
  })

  it('人工修改缺理由时被前端拦下（不发请求）', async () => {
    const { wrapper, spy } = await mounted()
    await wrapper.find('[data-testid="review-override-page:6!table:1!row:5"]').trigger('click')
    await wrapper.find('[data-testid="review-edit-save-page:6!table:1!row:5"]').trigger('click')
    await vi.waitFor(() => {
      expect(wrapper.find('[data-testid="review-error"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-testid="review-error"]').text()).toContain('理由')
    // 只有载入那一次请求
    expect(spy.mock.calls.filter((c) => (c[1] as RequestInit)?.method === 'POST')).toHaveLength(0)
    spy.mockRestore()
  })

  it('填了理由后提交 override（带 requirement 与 reason）', async () => {
    const { wrapper, spy } = await mounted()
    await wrapper.find('[data-testid="review-override-page:6!table:1!row:5"]').trigger('click')
    await wrapper.find('[data-testid="review-edit-requirement"]').setValue('elective')
    await wrapper.find('[data-testid="review-edit-reason"]').setValue('按学院口径为选修')
    await wrapper.find('[data-testid="review-edit-save-page:6!table:1!row:5"]').trigger('click')
    await vi.waitFor(() => {
      const posts = spy.mock.calls.filter(
        (c) => (c[1] as RequestInit)?.method === 'POST',
      )
      expect(posts.length).toBe(1)
    })
    const post = spy.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'POST')!
    const body = JSON.parse(String((post[1] as RequestInit).body))
    expect(body.decisions[0]).toEqual({
      source_record: 'page:6!table:1!row:5',
      action: 'override',
      requirement: 'elective',
      reason: '按学院口径为选修',
    })
    spy.mockRestore()
  })

  it('暂缓按钮提交 defer，且**不带** requirement（⛔ 不自动改判）', async () => {
    const { wrapper, spy } = await mounted()
    await wrapper.find('[data-testid="review-defer-page:4!table:1!row:2"]').trigger('click')
    await vi.waitFor(() => {
      expect(
        spy.mock.calls.filter((c) => (c[1] as RequestInit)?.method === 'POST').length,
      ).toBe(1)
    })
    const post = spy.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'POST')!
    const body = JSON.parse(String((post[1] as RequestInit).body))
    expect(body.decisions[0].action).toBe('defer')
    expect(body.decisions[0].requirement).toBeUndefined()
    spy.mockRestore()
  })

  it('展示类别最低学分的**原文与定位**（⛔ 非成员学分求和）', async () => {
    const { wrapper, spy } = await mounted()
    const block = wrapper.find('[data-testid="review-category-requirements"]')
    expect(block.text()).toContain('专必')
    expect(block.text()).toContain('78')
    expect(block.text()).toContain('专必 | 78')
    expect(block.html()).toContain('page:1!table:1!row:3')
    expect(block.text()).toContain('非成员学分求和')
    spy.mockRestore()
  })

  it('展示未解决统计与模块标题行（⛔ 不当成课程）', async () => {
    const { wrapper, spy } = await mounted()
    const block = wrapper.find('[data-testid="review-unresolved"]')
    expect(wrapper.find('[data-testid="review-no-evidence-count"]').text()).toBe('1')
    expect(wrapper.find('[data-testid="review-section-rows"]').text()).toBe('1')
    expect(block.text()).toContain('荣誉课程')
    spy.mockRestore()
  })

  it('导出预览只回显草稿状态与摘要绑定', async () => {
    const { wrapper, spy } = await mounted()
    spy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conclusion: 'pending_group_lead_review',
          verification: { verified: false, evidence: null },
          identity_authentication: 'not_performed',
          source: { source_sha256: 'a'.repeat(64) },
          unresolved_items: [{ kind: 'no_evidence' }],
        }),
        { status: 200 },
      ),
    )
    await wrapper.find('[data-testid="review-export"]').trigger('click')
    await vi.waitFor(() => {
      expect(wrapper.find('[data-testid="review-export-preview"]').exists()).toBe(true)
    })
    const text = wrapper.find('[data-testid="review-export-preview"]').text()
    expect(text).toContain('pending_group_lead_review')
    expect(text).toContain('"verified": false')
    expect(text).toContain('not_performed')
    spy.mockRestore()
  })

  it('⛔ 没有 review_id 时不渲染面板（由父组件控制）', () => {
    const wrapper = mount(CurriculumReviewPanel, { props: { reviewId: '' } })
    expect(wrapper.find('[data-testid="review-load"]').exists()).toBe(true)
    // 未载入时不应声称任何审核结论
    expect(wrapper.text()).not.toContain('已确认')
  })

  it('错误文案全部来自固定表（⛔ 不回显后端 message）', () => {
    const labels = Object.values(REVIEW_ERROR_LABEL).join(' ')
    expect(labels).not.toContain('内部细节')
    expect(REVIEW_ERROR_LABEL.confirm_not_allowed).toContain('不能一键确认')
    expect(REVIEW_ERROR_LABEL.override_requires_reason).toContain('理由')
  })
})
