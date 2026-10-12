/**
 * 课表截图识别的**演示数据**（frontend-only demo · 最终展示版）。
 *
 * ⚠️ 这是**演示用固定数据**，不是真实 OCR 结果，也不代表识别能力已实现：
 *   - 它只把「图片识别 → 候选信息 → 用户确认」这一步在演示中呈现出来；
 *   - ⛔ 不联网、⛔ 不调用后端、⛔ 不上传图片到任何第三方服务；
 *   - ⛔ 不产生 `CourseOffering`、⛔ 不认定教学班身份、⛔ 不推导课程号/教学班号。
 *
 * 真实 OCR 接入见 `feature/case-a-timetable-ocr` 分支的审计结论（表格结构识别尚未达标）。
 */

import type { CourseOffering } from '../types/contracts'

/** 识别出的一个候选课块。⛔ 全部字段都是**候选**，需用户确认。 */
export interface DemoRecognizedBlock {
  /** 稳定的演示标识，用于确认后生成课表条目的 `class_id`。 */
  readonly demoId: string
  readonly courseName: string
  readonly weekday: number
  readonly startSection: number
  readonly endSection: number
  readonly campus: string | null
  readonly classroom: string | null
  /** 置信度仅作展示；⛔ 不参与任何判定。 */
  readonly confidence: number
  /** 为什么仍需确认（例如教师/周次在图中无依据）。 */
  readonly unconfirmed: readonly string[]
}

/** 图片信息不足以唯一确定教学班的课程。⛔ 需用户去教学班搜索里自行选择。 */
export interface DemoUnresolvedCourse {
  readonly demoId: string
  readonly courseName: string
  /** 如实说明**为什么**无法自动确认。 */
  readonly reason: string
}

const WEEKDAY_LABELS: Record<number, string> = {
  1: '星期一',
  2: '星期二',
  3: '星期三',
  4: '星期四',
  5: '星期五',
  6: '星期六',
  7: '星期日',
}

export function weekdayLabel(weekday: number): string {
  return WEEKDAY_LABELS[weekday] ?? `星期${weekday}`
}

/**
 * 演示用识别结果：与本仓库真实课表样例（`中山大学课程表.png`）核对过的 10 个格位。
 *
 * ⚠️ 这些**不是**学校教学班身份：没有课程号、没有教学班号，因此既不自动匹配真实教学班，
 *    也不会被写成 `data_source="real"`。
 */
export const DEMO_RECOGNIZED_BLOCKS: readonly DemoRecognizedBlock[] = [
  {
    demoId: 'demo-block-01',
    courseName: '网络空间安全导论',
    weekday: 2,
    startSection: 7,
    endSection: 8,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.94,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。', '教室在图中无可靠文字依据，保持待确认。'],
  },
  {
    demoId: 'demo-block-02',
    courseName: '网络空间安全导论',
    weekday: 4,
    startSection: 1,
    endSection: 2,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.93,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。', '同一门课出现两个时段，需分别确认。'],
  },
  {
    demoId: 'demo-block-03',
    courseName: '数据结构与算法',
    weekday: 1,
    startSection: 3,
    endSection: 4,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.95,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。', '周次在图中无文字依据，保持待确认。'],
  },
  {
    demoId: 'demo-block-04',
    courseName: '数据结构与算法实验',
    weekday: 1,
    startSection: 7,
    endSection: 8,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.92,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。'],
  },
  {
    demoId: 'demo-block-05',
    courseName: '数字电路与逻辑设计',
    weekday: 4,
    startSection: 3,
    endSection: 4,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.93,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。'],
  },
  {
    demoId: 'demo-block-06',
    courseName: '数字电路与逻辑设计实验',
    weekday: 3,
    startSection: 3,
    endSection: 4,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.91,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。'],
  },
  {
    demoId: 'demo-block-07',
    courseName: '数据库系统原理',
    weekday: 4,
    startSection: 9,
    endSection: 10,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.93,
    unconfirmed: [
      '图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。',
      '⚠️ 教学班库中同一门课记为第9-11节，与图片的第9-10节不一致，需人工裁定。',
    ],
  },
  {
    demoId: 'demo-block-08',
    courseName: '英语学术交流',
    weekday: 3,
    startSection: 7,
    endSection: 8,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.9,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。'],
  },
  {
    demoId: 'demo-block-09',
    courseName: '网络空间安全科学讲座(上)',
    weekday: 5,
    startSection: 7,
    endSection: 8,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.89,
    unconfirmed: ['图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。'],
  },
  {
    demoId: 'demo-block-10',
    courseName: '马克思主义基本原理',
    weekday: 4,
    startSection: 5,
    endSection: 6,
    campus: '深圳校区',
    classroom: null,
    confidence: 0.9,
    unconfirmed: [
      '图片不含官方课程号与教学班号，需与教学班库比对后才能确定教学班身份。',
      '任课教师在图中未识别到可靠文字，保持待确认。',
    ],
  },
]

/**
 * 演示用「无法自动确认」列表。
 *
 * ⛔ 不猜测课程身份、⛔ 不自动选教学班；只如实说明原因，并把用户引导到**已有**的教学班搜索。
 */
export const DEMO_UNRESOLVED_COURSES: readonly DemoUnresolvedCourse[] = [
  {
    demoId: 'demo-unresolved-01',
    courseName: '数据库系统实验',
    reason: '图片信息不足，无法唯一匹配教学班',
  },
  {
    demoId: 'demo-unresolved-02',
    courseName: '形势与政策（二）',
    reason: '存在多个教学安排，需要人工选择',
  },
]

/**
 * 把一条**已由用户确认**的识别候选转成可加入当前课表的条目。
 *
 * ⚠️ 刻意与手工录入完全同构：
 *   - `source` 如实标明来自图片识别，⛔ 不冒充学校来源；
 *   - `data_source` 恒为 `'mock'`，因此**必须**走人工确认（attestation）才能提交，
 *     ⛔ 不会被当作已核验的真实教学班；
 *   - `course_id` / `class_id` 用演示标识占位，⛔ 不代表任何真实课程号或教学班号。
 */
export function blockToUnverifiedOffering(
  block: DemoRecognizedBlock,
  semester: string,
): CourseOffering {
  return {
    course_id: `IMAGE-RECOGNIZED-${block.demoId}`,
    course_name: block.courseName,
    class_id: `IMAGE-RECOGNIZED-${block.demoId}`,
    semester,
    meetings: [
      {
        weekday: block.weekday,
        start_section: block.startSection,
        end_section: block.endSection,
        weeks: [1, 2, 3, 4, 5, 6, 7, 8],
        campus: block.campus,
        classroom: block.classroom,
      },
    ],
    source: 'image-recognition://timetable-screenshot',
    data_source: 'mock',
  }
}
