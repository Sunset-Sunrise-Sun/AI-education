/**
 * **成绩单图片识别的演示数据**（frontend-only demo）。
 *
 * ⚠️ 与 `demoTimetableRecognition.ts` 同构，如实说明边界：
 *   - 这是**演示用固定数据**，不是真实 OCR 结果，也不代表识别能力已实现；
 *   - ⛔ 不联网、⛔ 不调用后端、⛔ 不上传图片到任何第三方服务；
 *   - 它只把「图片识别 → 课程候选 → 用户确认」这一步在演示中呈现出来。
 *
 * ⚠️ 与课表识别的**关键差异**：
 *   课表识别产出的是"课块"，无法确定教学班身份 → 只能进待确认区。
 *   成绩单识别产出的是"已修课程名"，**必须能进入培养方案匹配链**
 *   （`matchStudyPlan` 消费的是课程名列表）。
 *
 * ✅ 真实 OCR 接入方式：把真实识别结果构造成 `RecognizedTranscriptCourse[]`
 *   传给同一个 `toTranscriptCourseNames()` 即可，**匹配逻辑无需改动**。
 */

/** 识别出的一门已修课程。⛔ 全部字段都是**候选**，需用户确认。 */
export interface RecognizedTranscriptCourse {
  /** 稳定的演示标识。 */
  readonly demoId: string
  /** 识别出的课程名（成绩单上的写法）。 */
  readonly courseName: string
  /** 识别出的成绩/学分（可空，仅作展示）。 */
  readonly credit: number | null
  readonly score: number | null
  /** 置信度仅作展示；⛔ 不参与任何判定。 */
  readonly confidence: number
  /** 为什么仍需用户确认。 */
  readonly unconfirmed: readonly string[]
}

/**
 * 演示用识别结果：与当前 Demo 样本成绩单一致的已修课程。
 *
 * ⚠️ 课程名与成绩单原文一致；与培养方案的**别名映射**由
 *   `config/caseAStudyPlan.ts` 的 `TRANSCRIPT_COURSE_ALIASES` 负责，
 *   ⛔ 本文件不做任何课程号判断。
 */
export const DEMO_RECOGNIZED_TRANSCRIPT_COURSES: readonly RecognizedTranscriptCourse[] = [
  { demoId: 'ts-01', courseName: '大学英语', credit: 4, score: 88, confidence: 0.96, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-02', courseName: '大学英语（II）', credit: 4, score: 85, confidence: 0.95, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-03', courseName: '线性代数', credit: 3, score: 91, confidence: 0.97, unconfirmed: ['图片未包含官方课程号；且与目标专业要求存在等价性差异，需人工确认。'] },
  { demoId: 'ts-04', courseName: '高等数学（I）', credit: 5, score: 82, confidence: 0.96, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-05', courseName: '高等数学（II）', credit: 5, score: 79, confidence: 0.95, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-06', courseName: '概率统计（理工类）', credit: 3, score: 86, confidence: 0.94, unconfirmed: ['图片未包含官方课程号；课程名与目标专业要求接近但不完全一致。'] },
  { demoId: 'ts-07', courseName: '大学物理（工）上', credit: 4, score: 84, confidence: 0.93, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-08', courseName: '大学物理（工）下', credit: 4, score: 81, confidence: 0.93, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-09', courseName: '程序设计I', credit: 3, score: 90, confidence: 0.95, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-10', courseName: '程序设计I实验', credit: 1, score: 92, confidence: 0.94, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-11', courseName: '程序设计II', credit: 3, score: 87, confidence: 0.95, unconfirmed: ['图片未包含官方课程号；⚠️ 该课程本学期未开课，是否需重学需人工判断。'] },
  { demoId: 'ts-12', courseName: '程序设计II实验', credit: 1, score: 89, confidence: 0.94, unconfirmed: ['图片未包含官方课程号；⚠️ 该课程本学期未开课，是否需重学需人工判断。'] },
  { demoId: 'ts-13', courseName: '离散数学', credit: 3, score: 83, confidence: 0.93, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-14', courseName: '体育', credit: 1, score: 85, confidence: 0.97, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-15', courseName: '军事课', credit: 4, score: 86, confidence: 0.96, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-16', courseName: '国家安全教育', credit: 1, score: 88, confidence: 0.96, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-17', courseName: '心理健康教育', credit: 2, score: 90, confidence: 0.95, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-18', courseName: '中国近现代史纲要', credit: 3, score: 84, confidence: 0.94, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
  { demoId: 'ts-19', courseName: '习近平新时代中国特色社会主义思想概论', credit: 3, score: 87, confidence: 0.92, unconfirmed: ['课程名较长，识别可能存在截断，需人工确认。'] },
  { demoId: 'ts-20', courseName: '思想道德与法治', credit: 3, score: 86, confidence: 0.94, unconfirmed: ['图片未包含官方课程号，需人工确认课程身份。'] },
]

/** 图片信息不足、无法识别为课程条目的行。⛔ 不猜测，交给用户手工补充。 */
export const DEMO_UNRECOGNIZED_TRANSCRIPT_ROWS: readonly string[] = [
  '第 3 行：表格线遮挡，课程名不完整',
]

/**
 * 把识别结果转为**成绩单课程名列表**（`matchStudyPlan` 的输入）。
 *
 * ⛔ 不做课程号判断、⛔ 不做等价性认定 —— 只做"课程名列表"这一层转换。
 */
export function toTranscriptCourseNames(
  courses: readonly RecognizedTranscriptCourse[],
): string[] {
  return [...new Set(courses.map((course) => course.courseName.trim()).filter(Boolean))]
}
