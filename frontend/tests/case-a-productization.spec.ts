/**
 * 人工验收产品化修整 —— 必测项。
 *
 * 覆盖任务书第 15 节列出的 UX / Confirmation / Current elective / Future roadmap
 * 要求中属于**前端**的部分（后端的学分上限与选修推荐由 backend/tests 覆盖）。
 */

import { describe, expect, it } from 'vitest'
import {
  MAX_INITIAL_CANDIDATES,
  buildRepairView,
  type RawRepairProposal,
} from '@/utils/repairView'
import { humanizeIssueCode, normalizedIssues, summarizeByKind } from '@/utils/studentIssues'
import {
  CURRENT_HARD_MAX_CREDIT,
  FUTURE_HARD_MAX_CREDIT,
  FUTURE_SOFT_TARGET_CREDIT,
  loadLabel,
} from '@/utils/creditPolicy'

describe('issue humanization — ⛔ 机器码不得作为主文案', () => {
  it('translates known internal codes into Chinese', () => {
    expect(humanizeIssueCode('schedule_unknown')).toContain('排课信息')
    expect(humanizeIssueCode('UNKNOWN')).toContain('排课信息')
    expect(humanizeIssueCode('no_alternatives')).toBe('暂未找到可替代的同课程教学班')
    expect(humanizeIssueCode('all_conflict')).toContain('冲突')
    expect(humanizeIssueCode('manual_confirmation')).toContain('人工确认')
    expect(humanizeIssueCode('possibly_equivalent')).toContain('人工确认')
  })

  it('never echoes an unknown machine code back to the user', () => {
    const output = humanizeIssueCode('some_new_internal_code')
    expect(output).not.toContain('some_new_internal_code')
    expect(output).toBe('该事项需要进一步确认')
  })

  it('keeps the raw code out of the displayed message', () => {
    const issues = normalizedIssues({
      planUnresolved: [{ type: 'schedule_unknown', course_id: 'CSE204', message: 'raw text' }],
      courseNameById: { CSE204: '数据结构' },
    })
    expect(issues).toHaveLength(1)
    const issue = issues[0]
    // 主文案是中文；机器码只留在 rawCode 里（技术详情）
    expect(issue.message).not.toContain('schedule_unknown')
    expect(issue.message).toContain('排课信息')
    expect(issue.rawCode).toBe('schedule_unknown')
    // 课程名是主标题，课程号是次级信息
    expect(issue.title).toBe('数据结构')
    expect(issue.detail).toBe('CSE204')
  })
})

describe('unified issue list — 去重与分组', () => {
  it('deduplicates the same issue reported by several backend lists', () => {
    const issues = normalizedIssues({
      planUnresolved: [
        { type: 'schedule_unknown', course_id: 'MAR202', message: '排课信息缺失' },
      ],
      roadmapUnresolved: ['排课信息尚未同步，暂时无法判断是否冲突'],
      repairUnresolved: ['课程 MAR202 的当前教学班状态为 CONFLICT（no_alternatives）。'],
      courseNameById: { MAR202: '马克思主义基本原理' },
    })
    // 同一门课 + 同一类问题 ⇒ 只出现一次
    const unknown = issues.filter(
      (issue) => issue.kind === 'schedule_unknown' && issue.courseId === 'MAR202',
    )
    expect(unknown).toHaveLength(1)
  })

  it('drops selection_required when a real confirmable repair exists for the course', () => {
    const issues = normalizedIssues({
      planUnresolved: [
        { type: 'selection_required', course_id: 'PUB178', message: '有多个可选教学班' },
      ],
      repairProposals: [
        {
          proposal_id: 'p1',
          course_id: 'PUB178',
          current_class_id: '01',
          candidate_class_id: '02',
          reason: 'ok',
          candidate_state: 'CLEAR',
        },
      ],
      courseNameById: { PUB178: '劳动教育' },
    })
    expect(issues.some((issue) => issue.kind === 'selection_required')).toBe(false)
    expect(issues.some((issue) => issue.kind === 'repair_choice')).toBe(true)
  })

  it('sorts actionable issues first and summarizes by kind', () => {
    const issues = normalizedIssues({
      planUnresolved: [
        { type: 'schedule_unknown', course_id: 'AAA101', message: '' },
      ],
      repairProposals: [
        {
          proposal_id: 'p1',
          course_id: 'ZZZ999',
          current_class_id: '01',
          candidate_class_id: '02',
          reason: '',
          candidate_state: 'CLEAR',
        },
      ],
      courseNameById: {},
    })
    expect(issues[0].actionable).toBe(true)
    const summary = summarizeByKind(issues)
    expect(summary.reduce((sum, row) => sum + row.count, 0)).toBe(issues.length)
  })
})

describe('repair grouping — 一门课一张卡片', () => {
  function proposalsFor(courseId: string, count: number): RawRepairProposal[] {
    return Array.from({ length: count }, (_, index) => ({
      proposal_id: `${courseId}-${index}`,
      course_id: courseId,
      current_class_id: '202616253',
      candidate_class_id: `2026162${String(index).padStart(2, '0')}`,
      candidate_state: index === 0 ? 'CLEAR' : 'UNKNOWN',
      reason: 'raw backend reason mentioning schedule_unknown',
    }))
  }

  it('collapses 60 same-course candidates into ONE course card', () => {
    const view = buildRepairView(proposalsFor('PUB178', 60), [], { PUB178: '劳动教育' })
    expect(view.groups).toHaveLength(1)
    expect(view.groups[0].courseId).toBe('PUB178')
    expect(view.groups[0].courseName).toBe('劳动教育')
    expect(view.groups[0].candidates).toHaveLength(60)
  })

  it('sorts candidates CLEAR > UNKNOWN > CONFLICT, then by class id', () => {
    const raw: RawRepairProposal[] = [
      { proposal_id: 'c', course_id: 'X1', current_class_id: '0', candidate_class_id: '300', candidate_state: 'CONFLICT' },
      { proposal_id: 'u', course_id: 'X1', current_class_id: '0', candidate_class_id: '200', candidate_state: 'UNKNOWN' },
      { proposal_id: 'k', course_id: 'X1', current_class_id: '0', candidate_class_id: '100', candidate_state: 'CLEAR' },
    ]
    const candidates = buildRepairView(raw, []).groups[0].candidates
    expect(candidates.map((c) => c.state)).toEqual(['CLEAR', 'UNKNOWN', 'CONFLICT'])
    expect(candidates.map((c) => c.classId)).toEqual(['100', '200', '300'])
  })

  it('does NOT call it "可确认" when there is no CLEAR candidate', () => {
    const raw: RawRepairProposal[] = [
      { proposal_id: 'u', course_id: 'X1', current_class_id: '0', candidate_class_id: '200', candidate_state: 'UNKNOWN' },
    ]
    const group = buildRepairView(raw, []).groups[0]
    expect(group.hasConfirmableCandidate).toBe(false)
    expect(group.headline).not.toContain('可确认')
    expect(group.headline).toBe('可考虑的替代教学班')
    expect(group.note).toContain('仍需核验')
  })

  it('uses the "可确认" wording only when a CLEAR candidate exists', () => {
    const raw: RawRepairProposal[] = [
      { proposal_id: 'k', course_id: 'X1', current_class_id: '0', candidate_class_id: '100', candidate_state: 'CLEAR' },
    ]
    const group = buildRepairView(raw, []).groups[0]
    expect(group.hasConfirmableCandidate).toBe(true)
    expect(group.headline).toBe('可以换班')
  })

  it('summarizes unrepairable courses by reason instead of listing them flat', () => {
    const unresolved = [
      ...Array.from({ length: 7 }, (_, i) => `课程 C${i} 的当前教学班状态为 CONFLICT，本次输入没有可确认无冲突的同课程候选（no_alternatives）；需要人工核验。`),
      ...Array.from({ length: 3 }, (_, i) => `课程 D${i} 的当前教学班 20261670${i} 状态为 CONFLICT（all_conflict）；需要人工核验。`),
    ]
    const view = buildRepairView([], unresolved)
    expect(view.blockers).toHaveLength(10)
    const summary = new Map(view.blockerSummary.map((row) => [row.kind, row.count]))
    expect(summary.get('no_alternatives')).toBe(7)
    expect(summary.get('all_conflict')).toBe(3)
    // 中文原因，⛔ 不含机器码
    for (const row of view.blockerSummary) {
      expect(row.label).not.toContain('_')
    }
    // 教学班号只作为次级信息提取出来
    expect(view.blockers.some((b) => b.currentClassId !== null)).toBe(true)
  })

  it('exposes the default initial candidate count used by the UI', () => {
    expect(MAX_INITIAL_CANDIDATES).toBe(3)
  })
})

describe('credit policy — 26 / 30 / 35 三档（当前学期与未来学期不同）', () => {
  it('labels future semesters by the product thresholds', () => {
    expect(loadLabel(20).text).toBe('正常')
    expect(loadLabel(26).text).toBe('正常')
    expect(loadLabel(26.5).text).toBe('较满')
    expect(loadLabel(30).text).toBe('较满')
    expect(loadLabel(30.5).text).toBe('很满')
    expect(loadLabel(35).text).toBe('很满')
  })

  it('treats 30–35 as VALID (very heavy), not forbidden', () => {
    for (const value of [31, 33.5, 34, 35]) {
      const label = loadLabel(value)
      expect(label.tone, `${value} must not be treated as invalid`).not.toBe('over')
      expect(label.text).toBe('很满')
    }
  })

  it('flags anything above the hard max so a >35 semester cannot pass unnoticed', () => {
    expect(loadLabel(35.5).tone).toBe('over')
    expect(loadLabel(53.5).text).toBe('超出上限')
  })

  it('keeps the current-semester cap separate from the future hard max', () => {
    expect(CURRENT_HARD_MAX_CREDIT).toBe(30)
    expect(FUTURE_HARD_MAX_CREDIT).toBe(35)
    expect(CURRENT_HARD_MAX_CREDIT).not.toBe(FUTURE_HARD_MAX_CREDIT)
    expect(FUTURE_SOFT_TARGET_CREDIT).toBe(26)
  })
})

describe('issue dedup — ⛔ 不得合并不同的教学班问题', () => {
  it('keeps two DIFFERENT classes of the same course as two issues', () => {
    const issues = normalizedIssues({
      repairUnresolved: [
        '课程 PUB178 的当前教学班 202616253 状态为 CONFLICT，没有可确认无冲突的同课程候选（no_alternatives）；需要人工核验。',
        '课程 PUB178 的当前教学班 202616999 状态为 CONFLICT，没有可确认无冲突的同课程候选（no_alternatives）；需要人工核验。',
      ],
      courseNameById: { PUB178: '劳动教育' },
    })
    // 同一门课的**不同教学班**是不同待办 ⇒ 必须保留两条
    expect(issues).toHaveLength(2)
    expect(issues.every((issue) => issue.courseId === 'PUB178')).toBe(true)
    const details = issues.map((issue) => issue.detail).sort()
    expect(details[0]).toContain('202616253')
    expect(details[1]).toContain('202616999')
  })

  it('still collapses the SAME class reported by different backend lists', () => {
    const sameClass = '课程 PUB178 的当前教学班 202616253 状态为 CONFLICT（no_alternatives）；需要人工核验。'
    const issues = normalizedIssues({
      repairUnresolved: [sameClass, sameClass],
      courseNameById: { PUB178: '劳动教育' },
    })
    expect(issues).toHaveLength(1)
  })

  it('never echoes an unknown machine code in the primary message', () => {
    const issues = normalizedIssues({
      planUnresolved: [
        { type: 'brand_new_internal_state', course_id: 'X1', message: '' },
      ],
      courseNameById: { X1: '示例课程' },
    })
    expect(issues).toHaveLength(1)
    expect(issues[0].message).not.toContain('brand_new_internal_state')
    expect(issues[0].message).toBe('该事项需要进一步确认')
  })
})
