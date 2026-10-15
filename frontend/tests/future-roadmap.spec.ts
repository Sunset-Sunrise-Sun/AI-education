/**
 * 未来学习路径派生（Phase 7 任务 2 · Review 修正版）单元测试。
 *
 * 🔴 本文件的核心回归用例：**已满足课程禁止进入未来规划**。
 *    Review 发现的业务错误是"线性代数 / 体育 / 军事课等已修课再次出现在未来规划"，
 *    根因是旧实现只看后端 `makeup_tasks`，没有扣除成绩单已修课程。
 *
 * 覆盖：正常、空输入、边界（无推荐学期 / 推荐学期已过期 / 无法解析的学期）、
 *      以及"⛔ 不是未来选课预测"的硬约束。
 *
 * ⛔ 全部离线：不发网络请求、不依赖真实后端。
 */

import { describe, expect, it } from 'vitest'

import {
  MAX_CREDIT_PER_TERM,
  courseTierOf,
  deriveFutureRoadmap,
  normalizeCourseName,
  satisfiedNamesOf,
  termLabel,
  type CompletedCourseRecord,
} from '@/utils/futureRoadmap'
import type { MakeupTask } from '@/types/contracts'
import type { StudyPlan, StudyPlanRequirement } from '@/types/studyPlan'

function requirement(
  courseId: string,
  courseName: string,
  credit: number,
  term: string | null,
  type: 'required' | 'elective' = 'required',
): StudyPlanRequirement {
  return {
    course_id: courseId,
    course_name: courseName,
    credit,
    requirement: type,
    course_type: '公必',
    group_id: type === 'elective' ? 'CSE-ELECTIVE-POOL' : null,
    recommended_term_text: term,
    prerequisites: null,
    prerequisites_known: false,
    source_record: `table:1!row:${courseId}`,
  }
}

function plan(requirements: StudyPlanRequirement[], electiveMinimum: number | null = null): StudyPlan {
  return {
    major_id: 'network-security',
    name: '网络空间安全',
    cohort: '2025',
    version_id: 'major-network-security',
    source_id: 'case-owner-confirmed://majors/network-security/plan',
    complete: true,
    completeness_evidence: null,
    total_credit: null,
    counts: {
      total: requirements.length,
      required: requirements.filter((item) => item.requirement === 'required').length,
      elective: requirements.filter((item) => item.requirement === 'elective').length,
      unknown: 0,
      prerequisites_unknown: requirements.length,
    },
    requirements,
    elective_pool: {
      groups:
        electiveMinimum === null
          ? []
          : [
              {
                group_id: 'CSE-ELECTIVE-POOL',
                name: '专业选修课',
                minimum_credit: electiveMinimum,
                source_record: 'table:7!row:2',
              },
            ],
      courses: [],
    },
  }
}

function task(
  courseId: string,
  courseName: string,
  credit: number,
  status: MakeupTask['status'] = 'required',
): MakeupTask {
  return {
    course_id: courseId,
    course_name: courseName,
    credit,
    status,
    reason: '图片/PDF 不含官方课程号',
    source_evidence: 'upload:pdf:sha256:test',
  }
}

/** 成绩单已修记录（默认通过）。 */
function completed(courseName: string, passed = true): CompletedCourseRecord {
  return { course_name: courseName, credit: 3, passed }
}

/**
 * 所有**已排入**未来学期的课程名。
 *
 * ⚠️ 含 `required`（后端判定明确缺口）与 `pendingCoverage`（培养要求待覆盖，已排期）两组 ——
 *   两组都在学期路径里，只是分开标注来源。
 */
function allCourseNames(roadmap: ReturnType<typeof deriveFutureRoadmap>): string[] {
  return roadmap.semesters.flatMap((semester) => [
    ...(semester.required ?? []).map((item) => item.course_name),
    ...(semester.pendingCoverage ?? []).map((item) => item.course_name),
  ])
}

/** 取某个五状态分类的统计（找不到返回 0，避免测试里到处写 `!`）。 */
function stateOf(
  roadmap: ReturnType<typeof deriveFutureRoadmap>,
  state: 'completed' | 'in_progress' | 'missing' | 'need_confirmation' | 'pending_coverage',
) {
  return (
    roadmap.states.find((item) => item.state === state) ?? {
      state,
      courseCount: 0,
      credit: 0,
      unknownCreditCount: 0,
      scheduled: false,
    }
  )
}

/** 取某个分类别统计。 */
function categoryOf(
  roadmap: ReturnType<typeof deriveFutureRoadmap>,
  key: 'required' | 'elective' | 'general',
) {
  return roadmap.categories.find((item) => item.key === key)
}

describe('termLabel：学期代码 → 中文标签', () => {
  it('1 为春季、2 为秋季', () => {
    expect(termLabel('2026-1')).toBe('2026春')
    expect(termLabel('2026-2')).toBe('2026秋')
  })

  it('⛔ 无法解析的学期原样返回（不猜）', () => {
    expect(termLabel('2025-1~2025-2')).toBe('2025-1~2025-2')
    expect(termLabel('')).toBe('')
  })
})

/* -------------------------------------------------------------------------- *
 * 🔴 Review 要求的核心回归：已满足课程禁止进入未来规划
 * -------------------------------------------------------------------------- */

describe('🔴 已满足课程禁止进入未来规划（Review 回归）', () => {
  it('成绩单包含线性代数、体育 ⇒ 未来规划**不包含**它们', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('MA179', '线性代数', 3, '2026-2'),
        requirement('PE101', '体育', 1, '2026-2'),
        requirement('CSE301', '操作系统', 3, '2026-2'),
      ]),
      // ⚠️ 真实样本的关键特征：后端把**已修**与**未修**都标成 manual_confirmation
      [
        task('MA179', '线性代数', 3, 'manual_confirmation'),
        task('PE101', '体育', 1, 'manual_confirmation'),
        task('CSE301', '操作系统', 3, 'required'),
      ],
      [],
      '2026-1',
      [completed('线性代数'), completed('体育')],
    )

    const names = allCourseNames(roadmap)
    // ⛔ 已修课程不得出现在任何未来学期
    expect(names).not.toContain('线性代数')
    expect(names).not.toContain('体育')
    // ✅ 真正缺失的课程仍然排期
    expect(names).toContain('操作系统')
    // 统计如实反映
    expect(stateOf(roadmap, 'completed').courseCount).toBe(2)
    expect(roadmap.satisfiedCourseNames).toEqual(['线性代数', '体育'])
  })

  it('军事课（已修）不得进入未来规划', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('PUB121', '军事课', 4, '2027-1'),
        requirement('CSE301', '操作系统', 3, '2026-2'),
      ]),
      [
        task('PUB121', '军事课', 4, 'manual_confirmation'),
        task('CSE301', '操作系统', 3, 'required'),
      ],
      [],
      '2026-1',
      [completed('军事课')],
    )
    expect(allCourseNames(roadmap)).not.toContain('军事课')
  })

  it('⛔ 成绩单里**未通过**的记录不构成已满足', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('MA179', '线性代数', 3, '2026-2')]),
      [task('MA179', '线性代数', 3, 'required')],
      [],
      '2026-1',
      [completed('线性代数', false)],
    )
    expect(allCourseNames(roadmap)).toContain('线性代数')
    expect(stateOf(roadmap, 'completed').courseCount).toBe(0)
  })

  it('后端直接给 satisfied 时同样禁止进入未来规划', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('MA179', '线性代数', 3, '2026-2')]),
      [task('MA179', '线性代数', 3, 'satisfied')],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.semesters).toHaveLength(0)
    expect(stateOf(roadmap, 'completed').courseCount).toBe(1)
  })

  it('⛔ 没有成绩单明细时：待确认课程依然不得被排期', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('MA179', '线性代数', 3, '2026-2')]),
      [task('MA179', '线性代数', 3, 'manual_confirmation')],
      [],
      '2026-1',
      [],
    )
    // 无已修证据且后端未判缺失 ⇒ 归入"待人工确认"，⛔ 不安排学期
    expect(roadmap.semesters).toHaveLength(0)
    expect(roadmap.needConfirmationCourses.map((item) => item.course_name)).toEqual(['线性代数'])
    expect(stateOf(roadmap, 'need_confirmation').courseCount).toBe(1)
  })
})

/* -------------------------------------------------------------------------- *
 * 🔴 Review 第二轮回归：**正在修**（已在本学期课表里）的课不得排进未来学期
 * -------------------------------------------------------------------------- */

describe('🔴 本学期在修课程不得排进未来学期', () => {
  it('`马克思主义基本原理` 在初始课表里 ⇒ 未来规划不包含它', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('MAR202', '马克思主义基本原理', 3, '2026-1'),
        requirement('CSE301', '操作系统', 3, '2026-2'),
      ]),
      // ⚠️ 后端不为"本学期已加入课表"的课产出任务
      [task('CSE301', '操作系统', 3, 'required')],
      [],
      '2026-1',
      [],
      // 当前课表（原始课表）里正在修的课
      [{ course_id: 'MAR202', course_name: '马克思主义基本原理' }],
    )

    expect(allCourseNames(roadmap)).not.toContain('马克思主义基本原理')
    expect(allCourseNames(roadmap)).toContain('操作系统')
    expect(stateOf(roadmap, 'in_progress').courseCount).toBe(1)
    expect(roadmap.inProgressCourseNames).toEqual(['马克思主义基本原理'])
  })

  it('⛔ 在修课程不算"已满足"（两者语义分开统计）', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('MAR202', '马克思主义基本原理', 3, '2026-1')]),
      [],
      [],
      '2026-1',
      [],
      [{ course_id: 'MAR202', course_name: '马克思主义基本原理' }],
    )
    expect(stateOf(roadmap, 'completed').courseCount).toBe(0)
    expect(stateOf(roadmap, 'in_progress').courseCount).toBe(1)
    expect(roadmap.semesters).toEqual([])
  })

  it('课号缺失的历史课表数据：按课名也能排除', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('MAR202', '马克思主义基本原理', 3, '2026-1')]),
      [],
      [],
      '2026-1',
      [],
      [{ course_id: 'MANUAL-1', course_name: '马克思主义基本原理' }],
    )
    expect(roadmap.semesters).toEqual([])
    expect(stateOf(roadmap, 'in_progress').courseCount).toBe(1)
  })

  it('⛔ 在修的**选修**课不会被转成必修排期条目', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('CSE301', '操作系统', 3, '2026-2'),
        requirement('CSE335', '数据库系统原理', 3, '2026-1', 'elective'),
      ]),
      [task('CSE301', '操作系统', 3, 'required')],
      [],
      '2026-1',
      [],
      [{ course_id: 'CSE335', course_name: '数据库系统原理' }],
    )
    const names = allCourseNames(roadmap)
    expect(names).not.toContain('数据库系统原理')
    expect(names).toEqual(['操作系统'])
  })
})

describe('课程名归一化（仅用于"同名"判定）', () => {
  it('全角/半角括号、罗马数字、空白视为同名', () => {
    expect(normalizeCourseName('高等数学一（I）')).toBe(normalizeCourseName('高等数学一(I)'))
    expect(normalizeCourseName('体育')).toBe(normalizeCourseName(' 体育 '))
    expect(normalizeCourseName('程序设计I')).toBe(normalizeCourseName('程序设计Ⅰ'))
  })

  it('⛔ 不做包含匹配：不同课名不得被判为同名', () => {
    expect(normalizeCourseName('程序设计')).not.toBe(normalizeCourseName('程序设计II'))
    expect(normalizeCourseName('大学英语')).not.toBe(normalizeCourseName('英语学术读写'))
  })

  it('satisfiedNamesOf 只收通过记录', () => {
    const names = satisfiedNamesOf([completed('线性代数'), completed('体育', false)])
    expect(names.has(normalizeCourseName('线性代数'))).toBe(true)
    expect(names.has(normalizeCourseName('体育'))).toBe(false)
  })
})

describe('deriveFutureRoadmap：正常情况', () => {
  it('按剩余学分**重新分配**学期（⛔ 不复制培养方案推荐学期）', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('CSE301', '操作系统', 3, '2026-2'),
        requirement('CSE302', '计算机网络', 3, '2026-2'),
        requirement('CSE303', '编译原理', 2, '2027-1'),
      ]),
      [
        task('CSE301', '操作系统', 3),
        task('CSE302', '计算机网络', 3),
        task('CSE303', '编译原理', 2),
      ],
      [],
      '2026-1',
      [],
    )

    // ⚠️ 共 8 学分 ⇒ 最少学期数 = 1（⛔ 不再按推荐学期拆成 2026-2 / 2027-1 两个学期）
    expect(roadmap.semesters).toHaveLength(1)
    const [autumn] = roadmap.semesters
    expect(autumn.semester).toBe('2026-2')
    expect(autumn.required?.map((item) => item.course_id).sort()).toEqual([
      'CSE301',
      'CSE302',
      'CSE303',
    ])
    expect(autumn.expected_credit).toBe(8)
    expect(autumn.completion_goals?.join()).toContain('完成 3 门培养要求课程')
    expect(autumn.completion_goals?.join()).toContain('修读约 8 学分')
  })

  it('学分足够多时学期数按 上限 推导（45 学分 ⇒ 2 学期，每学期 >= 15）', () => {
    const requirements = Array.from({ length: 9 }, (_, index) =>
      requirement(`C${index}`, `课程${index}`, 5, '2027-1'),
    )
    const roadmap = deriveFutureRoadmap(
      plan(requirements),
      requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
    )
    expect(roadmap.semesters).toHaveLength(2)
    for (const semester of roadmap.semesters) {
      expect(semester.expected_credit!).toBeGreaterThanOrEqual(15)
      expect(semester.expected_credit!).toBeLessThanOrEqual(35)
    }
  })

  it('专业选修不进入必修排期（按剩余学分要求单独体现）', () => {
    const roadmap = deriveFutureRoadmap(
      plan(
        [
          requirement('CSE301', '操作系统', 3, '2026-2'),
          requirement('CSE401', '专业选修甲', 3, '2026-2', 'elective'),
        ],
        23,
      ),
      [task('CSE301', '操作系统', 3)],
      [],
      '2026-1',
      [],
    )
    const names = allCourseNames(roadmap)
    expect(names).toEqual(['操作系统'])
    const last = roadmap.semesters[roadmap.semesters.length - 1]
    expect(last.completion_goals?.join()).toContain('专业选修组累计达到 23 学分')
  })

  it('专业选修目标在**最后一个学期**作为完成目标出现，且按 目标 − 已修 计算尚缺', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')], 23),
      [task('CSE301', '操作系统', 3)],
      [
        {
          group_id: 'CSE-ELECTIVE-POOL',
          group_name: '专业选修课',
          // ⚠️ 真实转专业样本就是这三个 0（该组全部安排在转专业时点之后）
          required_credit: 0,
          earned_credit: 0,
          remaining_credit: 0,
          undecided: false,
        },
      ],
      '2026-1',
      [],
    )
    const last = roadmap.semesters[roadmap.semesters.length - 1]
    expect(last.completion_goals?.join()).toContain('专业选修组累计达到 23 学分')
    expect(last.completion_goals?.join()).toContain('尚缺 23 学分')
  })
})

describe('deriveFutureRoadmap：边界与降级', () => {
  it('⛔ 没有培养方案时不造数据', () => {
    expect(deriveFutureRoadmap(null, [task('CSE301', '操作系统', 3)], [], '2026-1', []).semesters).toEqual([])
  })

  it('⛔ 当前学期无法解析时不造数据', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')]),
      [task('CSE301', '操作系统', 3)],
      [],
      '2025-2026学年第一学期',
      [],
    )
    expect(roadmap.semesters).toEqual([])
  })

  it('全部培养要求都已满足 ⇒ 无任何学期排期', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('MA179', '线性代数', 3, '2026-2'),
        requirement('PE101', '体育', 1, '2026-2'),
      ]),
      [task('MA179', '线性代数', 3, 'manual_confirmation'), task('PE101', '体育', 1, 'manual_confirmation')],
      [],
      '2026-1',
      [completed('线性代数'), completed('体育')],
    )
    expect(roadmap.semesters).toEqual([])
    expect(stateOf(roadmap, 'completed').courseCount).toBe(2)
    expect(stateOf(roadmap, 'missing').courseCount).toBe(0)
  })

  it('推荐学期已过期 ⇒ 铺进未来学期（不是丢弃）', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('FL101', '大学外语（I）', 2, '2025-1')]),
      [task('FL101', '大学外语（I）', 2)],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.semesters).toHaveLength(1)
    expect(roadmap.semesters[0].semester).toBe('2026-2')
    expect(roadmap.semesters[0].required?.map((item) => item.course_id)).toEqual(['FL101'])
  })

  it('推荐学期是区间（`2025-1~2025-2`）⇒ 视为过期并铺开', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('PSY199', '心理健康教育', 2, '2025-1~2025-2')]),
      [task('PSY199', '心理健康教育', 2)],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.semesters[0].required?.map((item) => item.course_id)).toEqual(['PSY199'])
  })

  it('⛔ 每学期不超过 35 学分', () => {
    const requirements = Array.from({ length: 40 }, (_, index) =>
      requirement(`C${index}`, `课程${index}`, 4, '2025-1'),
    )
    const roadmap = deriveFutureRoadmap(
      plan(requirements),
      requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
    )
    for (const semester of roadmap.semesters) {
      expect(semester.expected_credit).toBeLessThanOrEqual(MAX_CREDIT_PER_TERM)
    }
  })

  it('学分未知 ⇒ ⛔ 不排期（⛔ 不猜学分、⛔ 不用 0 冒充已知）', () => {
    const unknownCredit = { ...task('CSE301', '操作系统', 3), credit: null as unknown as number }
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')]),
      [unknownCredit],
      [],
      '2026-1',
      [],
    )
    // ⛔ 学分待核验的课程不进学期，也不冒充 0 学分
    expect(roadmap.semesters).toEqual([])
    expect(stateOf(roadmap, 'missing').unknownCreditCount).toBe(1)
    expect(stateOf(roadmap, 'missing').credit).toBeNull()
  })
})

describe('⛔ 不是未来选课预测', () => {
  it('条目只含课程号 / 课程名 / 学分，⛔ 不含任何教学班或排课字段', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')]),
      [task('CSE301', '操作系统', 3)],
      [],
      '2026-1',
      [],
    )
    const entry = roadmap.semesters[0].required![0]
    expect(Object.keys(entry).sort()).toEqual(['course_id', 'course_name', 'credit'])
  })

  it('生成的学期序列连续且都在当前学期之后', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('A1', '课一', 1, '2026-2'),
        requirement('A2', '课二', 1, '2027-1'),
      ]),
      [task('A1', '课一', 1), task('A2', '课二', 1)],
      [],
      '2026-1',
      [],
    )
    const terms = roadmap.semesters.map((item) => item.semester)
    // 共 2 学分 ⇒ 1 个学期；且必须晚于当前学期
    expect(terms).toEqual(['2026-2'])
    for (const term of terms) expect(term > '2026-1').toBe(true)
  })
})

/* -------------------------------------------------------------------------- *
 * Task 1：状态闭环 —— 用户确认后未来路径必须重算
 * -------------------------------------------------------------------------- */

describe('Task 1 状态闭环：确认 / 拒绝后路径重算', () => {
  const threeCourses = () =>
    plan([
      requirement('FL101', '大学外语（I）', 2, '2026-2'),
      requirement('CSE301', '操作系统', 3, '2026-2'),
    ])

  const tasks = () => [
    // 待确认：成绩单里有记录但无法自动确认
    task('FL101', '大学外语（I）', 2, 'manual_confirmation'),
    // 明确缺失
    task('CSE301', '操作系统', 3, 'required'),
  ]

  it('初始：待确认课程**不进入**未来规划', () => {
    const roadmap = deriveFutureRoadmap(threeCourses(), tasks(), [], '2026-1', [])
    expect(allCourseNames(roadmap)).not.toContain('大学外语（I）')
    expect(allCourseNames(roadmap)).toContain('操作系统')
    expect(stateOf(roadmap, 'need_confirmation').courseCount).toBe(1)
  })

  it('用户**确认**（need_confirmation → satisfied）⇒ 路径重算且仍不包含该课', () => {
    const roadmap = deriveFutureRoadmap(
      threeCourses(),
      tasks(),
      [],
      '2026-1',
      [],
      [],
      // 学生在「补修缺口分析」里确认可转换
      ['FL101'],
    )
    expect(allCourseNames(roadmap)).not.toContain('大学外语（I）')
    // ⚠️ 状态从"待确认"移到"已完成"（⛔ 不是凭空消失）
    expect(stateOf(roadmap, 'need_confirmation').courseCount).toBe(0)
    expect(stateOf(roadmap, 'completed').courseCount).toBe(1)
  })

  it('用户**拒绝**（后端随后判 required）⇒ 该课进入未来规划', () => {
    // 拒绝后后端把 status 从 manual_confirmation 改成 required
    const afterReject = [
      task('FL101', '大学外语（I）', 2, 'required'),
      task('CSE301', '操作系统', 3, 'required'),
    ]
    const roadmap = deriveFutureRoadmap(threeCourses(), afterReject, [], '2026-1', [])
    expect(allCourseNames(roadmap)).toContain('大学外语（I）')
    expect(stateOf(roadmap, 'missing').courseCount).toBe(2)
  })

  it('⛔ 确认状态变化会改变排期学分（⇒ 计算的依赖链是活的）', () => {
    const before = deriveFutureRoadmap(threeCourses(), tasks(), [], '2026-1', [])
    const after = deriveFutureRoadmap(threeCourses(), tasks(), [], '2026-1', [], [], ['FL101'])
    // 确认前：只有操作系统在排期；确认后：大学外语（I）被排除，排期学分不变
    expect(before.reconciliation.plannedCredit).toBe(3)
    expect(after.reconciliation.plannedCredit).toBe(3)
    // 但"待确认"学分变成了"已完成"学分 ⇒ 对账各分量确实变了
    expect(before.reconciliation.needConfirmationCredit).toBe(2)
    expect(after.reconciliation.needConfirmationCredit).toBe(0)
    expect(after.reconciliation.completedCredit).toBe(2)
  })
})

/* -------------------------------------------------------------------------- *
 * Task 3：五状态分类（进行中 ≠ 已完成）
 * -------------------------------------------------------------------------- */

describe('Task 3 五状态分类', () => {
  it('五种状态各自归位，且只有「待确认」不排期', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('MA179', '线性代数', 3, '2026-2'),
        requirement('MAR202', '马克思主义基本原理', 3, '2026-1'),
        requirement('CSE301', '操作系统', 3, '2026-2'),
        requirement('FL101', '大学外语（I）', 2, '2026-2'),
        requirement('CSE999', '未判定课程', 2, '2026-2'),
      ]),
      [
        task('CSE301', '操作系统', 3, 'required'),
        task('FL101', '大学外语（I）', 2, 'manual_confirmation'),
      ],
      [],
      '2026-1',
      [completed('线性代数')],
      [{ course_id: 'MAR202', course_name: '马克思主义基本原理' }],
    )

    expect(stateOf(roadmap, 'completed').courseCount).toBe(1)
    expect(stateOf(roadmap, 'in_progress').courseCount).toBe(1)
    expect(stateOf(roadmap, 'missing').courseCount).toBe(1)
    expect(stateOf(roadmap, 'need_confirmation').courseCount).toBe(1)
    expect(stateOf(roadmap, 'pending_coverage').courseCount).toBe(1)

    // ⛔ 只有"待确认"不进入排期（没有依据，不能替学生决定）
    expect(stateOf(roadmap, 'need_confirmation').scheduled).toBe(false)
    // ✅ 其余"未完成"类别都排期：明确缺口（后端判定）+ 培养要求待覆盖
    for (const state of ['missing', 'pending_coverage'] as const) {
      expect(stateOf(roadmap, state).scheduled).toBe(true)
    }
    for (const state of ['completed', 'in_progress'] as const) {
      expect(stateOf(roadmap, state).scheduled).toBe(false)
    }

    // 「培养要求待覆盖」单独列出（透明），但已排入学期
    expect(roadmap.pendingCoverageCourses.map((item) => item.course_name)).toEqual(['未判定课程'])
    const scheduled = allCourseNames(roadmap)
    expect(scheduled).toContain('操作系统')
    expect(scheduled).toContain('未判定课程')
    // ⚠️ 学期内两组**分开标注**：明确缺口在 required，待覆盖在 pendingCoverage
    const term = roadmap.semesters[0]
    expect((term.required ?? []).map((item) => item.course_name)).toEqual(['操作系统'])
    expect((term.pendingCoverage ?? []).map((item) => item.course_name)).toEqual(['未判定课程'])
    // ⛔ 待确认与已完成/在修都不得出现
    expect(scheduled).not.toContain('大学外语（I）')
    expect(scheduled).not.toContain('线性代数')
    expect(scheduled).not.toContain('马克思主义基本原理')
  })

  it('⛔ 进行中 ≠ 已完成（分别计数，不合并）', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('MAR202', '马克思主义基本原理', 3, '2026-1'),
        requirement('MA179', '线性代数', 3, '2026-2'),
      ]),
      [],
      [],
      '2026-1',
      [completed('线性代数')],
      [{ course_id: 'MAR202', course_name: '马克思主义基本原理' }],
    )
    expect(stateOf(roadmap, 'completed').courseCount).toBe(1)
    expect(stateOf(roadmap, 'completed').credit).toBe(3)
    expect(stateOf(roadmap, 'in_progress').courseCount).toBe(1)
    expect(stateOf(roadmap, 'in_progress').credit).toBe(3)
  })

  it('学分未知的课程⛔ 不排期（不猜学分），但仍计入缺口学分口径', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')]),
      [{ ...task('CSE301', '操作系统', 3), credit: null as unknown as number }],
      [],
      '2026-1',
      [],
    )
    // ⛔ 学分为 null 的"明确缺口"课程不排期
    expect(roadmap.semesters).toEqual([])
    expect(stateOf(roadmap, 'missing').unknownCreditCount).toBe(1)
    expect(roadmap.reconciliation.plannedCredit).toBe(0)
  })
})

/* -------------------------------------------------------------------------- *
 * Task 2：学分对账 + 分类别统计
 * -------------------------------------------------------------------------- */

describe('Task 2 学分对账与分类别统计', () => {
  it('完成 + 进行中 + 明确缺口 + 待确认 + 待覆盖 = 培养要求总量', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('MA179', '线性代数', 3, '2026-2'),
        requirement('MAR202', '马克思主义基本原理', 3, '2026-1'),
        requirement('CSE301', '操作系统', 3, '2026-2'),
        requirement('FL101', '大学外语（I）', 2, '2026-2'),
        requirement('CSE999', '未判定课程', 2, '2026-2'),
      ]),
      [
        task('CSE301', '操作系统', 3, 'required'),
        task('FL101', '大学外语（I）', 2, 'manual_confirmation'),
      ],
      [],
      '2026-1',
      [completed('线性代数')],
      [{ course_id: 'MAR202', course_name: '马克思主义基本原理' }],
    )
    const r = roadmap.reconciliation
    expect(r.requiredTotalCredit).toBe(13)
    expect(r.completedCredit).toBe(3)
    expect(r.inProgressCredit).toBe(3)
    expect(r.missingCredit).toBe(3)
    expect(r.needConfirmationCredit).toBe(2)
    expect(r.pendingCoverageCredit).toBe(2)
    // ⚠️ 未来计划 = 明确缺口(3) + 待覆盖(2) —— 两者都已排期
    expect(r.plannedCredit).toBe(5)
    expect(r.accountedCredit).toBe(13)
    expect(r.balanced).toBe(true)
    expect(r.note).toBeNull()
  })

  it('⛔ 数据不足时如实说明，不用 0 补齐', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')]),
      [{ ...task('CSE301', '操作系统', 3), credit: null as unknown as number }],
      [],
      '2026-1',
      [],
    )
    const r = roadmap.reconciliation
    expect(r.accountedCredit).toBeNull()
    expect(r.balanced).toBe(false)
    expect(r.note).toContain('学分待核验')
  })

  it('分类别统计：专业必修 / 公共必修按门数，专业选修按学分', () => {
    const planWithTypes = plan([
      { ...requirement('CSE301', '操作系统', 3, '2026-2'), course_type: '专业课' },
      { ...requirement('MA179', '线性代数', 3, '2026-2'), course_type: '公必' },
      { ...requirement('CSE401', '专业选修甲', 2, '2026-2', 'elective'), course_type: '专业选修课模块' },
    ], 23) as ReturnType<typeof plan>
    // 补上选修池课程，让"专业选修"门数可核对
    planWithTypes.elective_pool.courses.push(
      planWithTypes.requirements[2],
    )

    const roadmap = deriveFutureRoadmap(
      planWithTypes,
      [task('CSE301', '操作系统', 3, 'required')],
      [
        {
          group_id: 'CSE-ELECTIVE-POOL',
          group_name: '专业选修课',
          required_credit: 0,
          earned_credit: 4,
          remaining_credit: 19,
          undecided: false,
        },
      ],
      '2026-1',
      [completed('线性代数')],
    )

    expect(categoryOf(roadmap, 'required')?.totalCount).toBe(1)
    expect(categoryOf(roadmap, 'required')?.completedCount).toBe(0)
    expect(categoryOf(roadmap, 'general')?.totalCount).toBe(1)
    expect(categoryOf(roadmap, 'general')?.completedCount).toBe(1)
    // ⚠️ 选修按学分：要求来自培养方案下限 23，已完成来自后端 elective_progress
    expect(categoryOf(roadmap, 'elective')?.requiredCredit).toBe(23)
    expect(categoryOf(roadmap, 'elective')?.completedCredit).toBe(4)
  })

  it('⛔ 后端未提供选修进度时 completedCredit 为 null（不冒充 0）', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE401', '专业选修甲', 2, '2026-2', 'elective')], 23),
      [],
      [],
      '2026-1',
      [],
    )
    expect(categoryOf(roadmap, 'elective')?.requiredCredit).toBe(23)
    expect(categoryOf(roadmap, 'elective')?.completedCredit).toBeNull()
  })

  it('预计完成学期 = 最后一个有排期的学期', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('A1', '课一', 20, null),
        requirement('A2', '课二', 20, null),
      ]),
      [task('A1', '课一', 20), task('A2', '课二', 20)],
      [],
      '2026-1',
      [],
    )
    // 40 学分 ⇒ 2 个学期（每学期 20）
    expect(roadmap.semesters).toHaveLength(2)
    expect(roadmap.expectedCompletionTerm).toBe('2027-1')
  })
})

/* -------------------------------------------------------------------------- *
 * Phase 7 语义收敛：状态表达（不改变算法与数据来源）
 * -------------------------------------------------------------------------- */

describe('Phase 7 语义收敛：状态表达', () => {
  it('① 状态类型不再叫 unresolved，改为 pending_coverage（待覆盖）', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE999', '某课', 2, '2026-2')]),
      [],
      [],
      '2026-1',
      [],
    )
    const states = roadmap.states.map((item) => item.state)
    expect(states).toContain('pending_coverage')
    // ⛔ 不得再出现旧的 unresolved 语义
    expect(states).not.toContain('unresolved' as never)
  })

  it('② 三种"未完成"状态各自独立，⛔ 不合并', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('A1', '明确缺口课', 3, '2026-2'),
        requirement('A2', '待确认课', 2, '2026-2'),
        requirement('A3', '待覆盖课', 1, '2026-2'),
      ]),
      [task('A1', '明确缺口课', 3, 'required'), task('A2', '待确认课', 2, 'manual_confirmation')],
      [],
      '2026-1',
      [],
    )
    expect(stateOf(roadmap, 'missing').courseCount).toBe(1)
    expect(stateOf(roadmap, 'need_confirmation').courseCount).toBe(1)
    expect(stateOf(roadmap, 'pending_coverage').courseCount).toBe(1)
  })

  it('③ 学分摘要：待确认与待覆盖**分开计数**，⛔ 不合并成一个数字', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('A1', '待确认课', 2, '2026-2'),
        requirement('A2', '待覆盖课', 5, '2026-2'),
      ]),
      [task('A1', '待确认课', 2, 'manual_confirmation')],
      [],
      '2026-1',
      [],
    )
    const r = roadmap.reconciliation
    expect(r.needConfirmationCredit).toBe(2)
    expect(r.pendingCoverageCredit).toBe(5)
    // ⛔ 不能再有一个把两者合起来的字段
    expect('undeterminedCredit' in r).toBe(false)
    // 只有待覆盖已排期
    expect(r.plannedCredit).toBe(5)
  })

  it('④ 待覆盖的说明语逐字可用（页面直接引用同一措辞）', () => {
    // ⚠️ 该说明是**页面固定文案**，此处校验派生结果里不含任何"系统已判定缺课"的措辞
    const roadmap = deriveFutureRoadmap(
      plan([requirement('A3', '待覆盖课', 1, '2026-2')]),
      [],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.pendingCoverageCourses.map((item) => item.course_name)).toEqual(['待覆盖课'])
    // 待覆盖课程**不在**明确缺口列表里
    expect(roadmap.semesters[0].required ?? []).toEqual([])
    expect((roadmap.semesters[0].pendingCoverage ?? []).map((i) => i.course_name)).toEqual(['待覆盖课'])
  })

  it('⑤ 未来规划起点 = 当前学期之后的第一学期；⛔ 当前学期不作为普通未来学期重复规划', () => {
    // 当前学期 2026-1（春），未来应从 2026-2（秋）起
    const roadmap = deriveFutureRoadmap(
      plan([requirement('A1', '某课', 3, '2026-1')]),
      [task('A1', '某课', 3, 'required')],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.currentTerm).toBe('2026-1')
    expect(roadmap.startsFromTerm).toBe('2026-2')
    // ⛔ 任何学期都不得早于/等于当前学期
    for (const semester of roadmap.semesters) {
      expect(semester.semester > '2026-1').toBe(true)
    }
    expect(roadmap.semesters.map((s) => s.semester)).not.toContain('2026-1')
  })

  it('⑤ 推荐学期 = 当前学期（2026-1）的课程**不会**被排回当前学期', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('A1', '某课', 3, '2026-1')]),
      [task('A1', '某课', 3, 'required')],
      [],
      '2026-1',
      [],
    )
    // 推荐学期已"过期"（不晚于当前学期）⇒ 交给未来学期，⛔ 不排回 2026-1
    expect(roadmap.semesters[0].semester).toBe('2026-2')
  })
})

/* -------------------------------------------------------------------------- *
 * 🔴 Review：排期逻辑重新设计（不复制培养方案推荐学期）
 * -------------------------------------------------------------------------- */

describe('🔴 排期重新设计：后续学期不得出现个位数（毕业学期除外）', () => {
  /** 构造一份"推荐学期很分散"的方案，验证规划**不再照抄**它。 */
  function spreadPlan() {
    return plan([
      requirement('A1', '现代密码学', 3, '2027-2'),
      requirement('A2', '信号与系统', 3, '2027-2'),
      requirement('A3', '计算机组成原理', 3, '2027-2'),
      requirement('A4', '毛泽东思想概论', 3, '2027-2'),
      requirement('A5', '大学外语（IV）', 2, '2028-1'),
      requirement('A6', '程序设计I', 3, '2028-1'),
      requirement('A7', '操作系统', 3, '2027-1'),
      requirement('A8', '计算机网络', 3, '2027-1'),
      requirement('A9', '软件安全', 3, '2027-1'),
      requirement('A10', '数据安全与隐私保护', 2, '2028-1'),
      requirement('A11', '系统安全', 3, '2027-2'),
      requirement('A12', '网络空间安全综合实践', 1, '2027-2'),
      requirement('A13', '大学外语（III）', 2, '2028-1'),
      requirement('A14', '劳动教育', 1, '2028-2'),
      requirement('A15', '形势与政策（三）', 0.5, '2028-2'),
      requirement('A16', '形势与政策（四）', 0.5, '2028-2'),
      requirement('GRAD', '毕业论文', 6, '2028-2'),
    ])
  }

  it('⛔ 后续学期不能出现个位数学分（除毕业学期）', () => {
    const p = spreadPlan()
    const roadmap = deriveFutureRoadmap(
      p,
      p.requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
    )

    const terms = roadmap.semesters
    expect(terms.length).toBeGreaterThan(1)
    for (const semester of terms) {
      const credit = semester.expected_credit ?? 0
      const isGraduationTerm = (semester.required ?? []).some((item) =>
        item.course_name.includes('毕业论文'),
      )
      if (isGraduationTerm) continue
      // 🔴 核心断言：非毕业学期必须 >= 15 学分
      expect(credit).toBeGreaterThanOrEqual(15)
      expect(credit).toBeLessThanOrEqual(35)
    }
  })

  it('毕业论文固定最后一个学期，且该学期只放毕业课', () => {
    const p = spreadPlan()
    const roadmap = deriveFutureRoadmap(
      p,
      p.requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
    )
    const last = roadmap.semesters[roadmap.semesters.length - 1]
    const names = (last.required ?? []).map((item) => item.course_name)
    expect(names).toContain('毕业论文')
    expect(names).toHaveLength(1)
    // 其他学期都不得含毕业课
    for (const semester of roadmap.semesters.slice(0, -1)) {
      expect((semester.required ?? []).some((i) => i.course_name.includes('毕业论文'))).toBe(false)
    }
  })

  it('已修课程不能重新出现', () => {
    const p = spreadPlan()
    const roadmap = deriveFutureRoadmap(
      p,
      p.requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [completed('操作系统'), completed('软件安全')],
    )
    const scheduled = allCourseNames(roadmap)
    expect(scheduled).not.toContain('操作系统')
    expect(scheduled).not.toContain('软件安全')
  })

  it('在修课程不能重新出现', () => {
    const p = spreadPlan()
    const roadmap = deriveFutureRoadmap(
      p,
      p.requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
      [
        { course_id: 'A2', course_name: '信号与系统' },
        { course_id: 'A11', course_name: '系统安全' },
      ],
    )
    const scheduled = allCourseNames(roadmap)
    expect(scheduled).not.toContain('信号与系统')
    expect(scheduled).not.toContain('系统安全')
  })

  it('待确认课程不自动排期', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('A1', '待确认课', 20, '2026-2'),
        requirement('A2', '待覆盖课', 20, '2026-2'),
      ]),
      [task('A1', '待确认课', 20, 'manual_confirmation')],
      [],
      '2026-1',
      [],
    )
    const scheduled = allCourseNames(roadmap)
    expect(scheduled).not.toContain('待确认课')
    expect(scheduled).toContain('待覆盖课')
  })

  it('🔴 总剩余学分守恒：完成 + 在修 + 排期 + 待确认 = 必修总量', () => {
    const p = spreadPlan()
    const roadmap = deriveFutureRoadmap(
      p,
      p.requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [completed('操作系统')],
      [{ course_id: 'A2', course_name: '信号与系统' }],
    )

    const scheduledCredit = roadmap.semesters.reduce(
      (sum, semester) => sum + (semester.expected_credit ?? 0),
      0,
    )
    const r = roadmap.reconciliation
    // 排入学期 = 明确缺口 + 待覆盖
    expect(scheduledCredit).toBe(r.plannedCredit)
    expect(r.accountedCredit).toBe(r.requiredTotalCredit)
    expect(r.balanced).toBe(true)
  })

  it('⛔ 不复制推荐学期：同一推荐学期的大批课程会被摊到多个学期', () => {
    // 全部 14 门课推荐学期都是 2027-1，但总学分 42 ⇒ 至少 2 个学期，且都 >= 15
    const requirements = Array.from({ length: 14 }, (_, index) =>
      requirement(`C${index}`, `课程${index}`, 3, '2027-1'),
    )
    const roadmap = deriveFutureRoadmap(
      plan(requirements),
      requirements.map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
    )
    // ⚠️ 旧实现会把它们全塞进 2027-1 那一个学期；新实现按学分总量摊开
    expect(roadmap.semesters.length).toBeGreaterThanOrEqual(2)
    for (const semester of roadmap.semesters) {
      expect(semester.expected_credit!).toBeGreaterThanOrEqual(15)
      expect(semester.expected_credit!).toBeLessThanOrEqual(35)
    }
    // 学期序列从当前学期之后开始
    expect(roadmap.semesters[0].semester).toBe('2026-2')
  })
})

/* -------------------------------------------------------------------------- *
 * Review 优化：语义细化 + 弱课程排序
 * -------------------------------------------------------------------------- */

describe('Review 优化：弱课程排序（基础 > 核心 > 高级选修 > 毕业环节）', () => {
  /** 带 course_type 的方案：公必 / 专业课 / 专业选修课模块 + 毕业论文。 */
  function tieredPlan() {
    return plan([
      { ...requirement('B1', '中国近现代史纲要', 3, null), course_type: '公必' },
      { ...requirement('B2', '大学外语（I）', 2, null), course_type: '公必' },
      { ...requirement('C1', '操作系统', 3, null), course_type: '专业课' },
      { ...requirement('C2', '计算机网络', 3, null), course_type: '专业课' },
      { ...requirement('C3', '数据结构与算法', 3, null), course_type: '专业课' },
      { ...requirement('C4', '软件安全', 3, null), course_type: '专业课' },
      {
        ...requirement('E1', '数字图像处理', 3, null, 'elective'),
        course_type: '专业选修课模块',
      },
      {
        ...requirement('E2', '模式识别与计算机视觉', 3, null, 'elective'),
        course_type: '专业选修课模块',
      },
      { ...requirement('G1', '毕业论文', 6, null), course_type: '专业课' },
    ])
  }

  function build() {
    const p = tieredPlan()
    return deriveFutureRoadmap(
      p,
      p.requirements
        .filter((item) => item.requirement !== 'elective')
        .map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
    )
  }

  it('同一学期内：基础课程排在核心专业课之前', () => {
    const roadmap = build()
    const first = roadmap.semesters[0]
    const names = (first.required ?? []).map((item) => item.course_name)
    const foreignIdx = names.indexOf('大学外语（I）')
    const historyIdx = names.indexOf('中国近现代史纲要')
    const osIdx = names.indexOf('操作系统')
    expect(foreignIdx).toBeGreaterThanOrEqual(0)
    expect(historyIdx).toBeGreaterThanOrEqual(0)
    expect(osIdx).toBeGreaterThanOrEqual(0)
    // 公必（基础）在前，专业课（核心）在后
    expect(Math.max(foreignIdx, historyIdx)).toBeLessThan(osIdx)
  })

  it('🔴 排序稳定：同一输入重复派生，学期与课程顺序完全一致', () => {
    const a = build()
    const b = build()
    expect(JSON.stringify(a.semesters)).toBe(JSON.stringify(b.semesters))
  })

  it('🔴 毕业论文仍然固定在最后一个学期，且是毕业环节', () => {
    const roadmap = build()
    const last = roadmap.semesters[roadmap.semesters.length - 1]
    const names = (last.required ?? []).map((item) => item.course_name)
    expect(names).toEqual(['毕业论文'])
    for (const semester of roadmap.semesters.slice(0, -1)) {
      expect((semester.required ?? []).some((i) => i.course_name.includes('毕业论文'))).toBe(false)
    }
  })

  it('课程层级只按培养方案字段判定（⛔ 不含先修假设）', () => {
    expect(courseTierOf('中国近现代史纲要', '公必', false)).toBe('foundation')
    expect(courseTierOf('操作系统', '专业课', false)).toBe('core')
    expect(courseTierOf('数字图像处理', '专业选修课模块', true)).toBe('advanced')
    expect(courseTierOf('毕业论文', '专业课', false)).toBe('graduation')
    // ⛔ 毕业课优先于其它判定
    expect(courseTierOf('毕业设计', '公必', false)).toBe('graduation')
  })
})

describe('Review 优化：文案与学分口径', () => {
  it('⛔ 排序说明不出现"预计毕业"字样', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')]),
      [task('CSE301', '操作系统', 3)],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.orderingNote).not.toContain('预计毕业')
  })

  it('0.5 学分课程存在时，学分说明如实解释精确值来源', () => {
    const roadmap = deriveFutureRoadmap(
      plan([
        requirement('PE201', '体育', 0.5, null),
        requirement('MAR117', '形势与政策（二）', 0.5, null),
        requirement('CSE301', '操作系统', 3, null),
      ]),
      [
        task('PE201', '体育', 0.5),
        task('MAR117', '形势与政策（二）', 0.5),
        task('CSE301', '操作系统', 3),
      ],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.creditNote).toContain('0.5 学分')
    expect(roadmap.creditNote).toContain('未做四舍五入')
    // ⚠️ 保留精确值（3 + 0.5 + 0.5 = 4）
    expect(roadmap.semesters[0].expected_credit).toBe(4)
  })

  it('没有 0.5 学分课程时，学分说明仍声明使用精确值', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, null)]),
      [task('CSE301', '操作系统', 3)],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.creditNote).toContain('未做四舍五入')
    expect(roadmap.creditNote).not.toContain('0.5 学分')
  })
})

/* -------------------------------------------------------------------------- *
 * Task 5：排序口径与先修信息缺失的如实说明
 * -------------------------------------------------------------------------- */

describe('Task 5 排序口径', () => {
  it('⛔ 培养方案没有先修信息时，必须如实说明只按课程类型排序', () => {
    const roadmap = deriveFutureRoadmap(
      plan([requirement('CSE301', '操作系统', 3, '2026-2')]),
      [task('CSE301', '操作系统', 3)],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.orderingNote).toContain('未提供先修关系')
    expect(roadmap.orderingNote).toContain('仅按课程类型优化顺序')
    // 四层顺序必须写明
    expect(roadmap.orderingNote).toContain('基础课程')
    expect(roadmap.orderingNote).toContain('核心专业课')
    expect(roadmap.orderingNote).toContain('高级选修')
    expect(roadmap.orderingNote).toContain('毕业环节')
  })

  it('培养方案提供先修信息时，说明改为参考先修关系', () => {
    const withPrereq = plan([
      { ...requirement('CSE301', '操作系统', 3, '2026-2'), prerequisites_known: true, prerequisites: ['CSE101'] },
    ]) as ReturnType<typeof plan>
    const roadmap = deriveFutureRoadmap(
      withPrereq,
      [task('CSE301', '操作系统', 3)],
      [],
      '2026-1',
      [],
    )
    expect(roadmap.orderingNote).toContain('先修关系')
    expect(roadmap.orderingNote).not.toContain('未提供先修关系')
  })

  it('大学分优先：小课不会把学期塞满而挤掉大课', () => {
    const small = Array.from({ length: 8 }, (_, index) =>
      requirement(`S${index}`, `小课${index}`, 4, null),
    )
    const big = requirement('BIG', '大学分课', 20, null)
    const roadmap = deriveFutureRoadmap(
      plan([...small, big]),
      [...small, big].map((item) => task(item.course_id, item.course_name, item.credit)),
      [],
      '2026-1',
      [],
    )
    // 每学期上限 35 ⇒ 20 学分的大课必须能进第一个学期
    const first = roadmap.semesters[0]
    expect(first.required?.some((item) => item.course_id === 'BIG')).toBe(true)
    for (const semester of roadmap.semesters) {
      expect(semester.expected_credit!).toBeLessThanOrEqual(35)
    }
  })
})
