/**
 * 用户输入表单的**纯逻辑层**（不含任何 Vue 组件、DOM 或网络代码）。
 *
 * 为什么单独抽出来：
 * - 组件只负责渲染与事件绑定，字段规则、序列化与校验集中在这里，便于测试；
 * - 这里**不做任何业务判断**：不判定课程等价、不算学分、不做冲突检测、不生成 MakeupTask；
 * - 输出的 `Preference` 对象严格符合 `schemas/preference.schema.json`，
 *   **不新增字段**；`current_schedule` 严格是 `CourseOffering[]`。
 */

import type { AvoidTime, CourseOffering, Preference } from '../types/contracts'
import { CASE_A_CONTEXT } from '../config'

/** 学生转专业上下文（本轮只作为 Case context 展示与输入，不声称已影响后端 Planner）。 */
export interface StudentContext {
  originMajor: string
  targetMajor: string
  transferTerm: string
}

/** 回避时段表单行；`key` 只用于前端列表渲染，不进入公共契约。 */
export interface AvoidTimeRow {
  key: number
  weekday: number
  start_section: number
  end_section: number
}

/** 允许的学期文本形式：`YYYY-1` / `YYYY-2`（与项目既有学期口径一致）。 */
export const SEMESTER_PATTERN = '^\\d{4}-[12]$'

/** 允许上传的成绩文件扩展名（本轮只保存文件对象/文件名，不上传、不解析）。 */
export const XLSX_EXTENSION = '.xlsx'

/** 成绩文件上传分析的提示文案（必须在页面上明确显示）。 */
export const GRADE_FILE_PENDING_NOTICE =
  '成绩文件上传分析将在真实 Curriculum User Input API 接入后启用。'

/** 页面必须明确显示的 Mock / Real 数据模式文案。 */
export const DATA_MODE_LABEL: Record<'mock' | 'real', string> = {
  mock: '当前数据模式：Mock',
  real: '当前数据模式：Real',
}

const SEMESTER_RE = new RegExp(SEMESTER_PATTERN)

let nextAvoidTimeKey = 1

export function createAvoidTimeRow(
  values: Partial<Omit<AvoidTimeRow, 'key'>> = {},
): AvoidTimeRow {
  return {
    key: nextAvoidTimeKey++,
    weekday: values.weekday ?? 1,
    start_section: values.start_section ?? 1,
    end_section: values.end_section ?? 2,
  }
}

/** 可能处于"用户输入了非法值"状态的字段。 */
export type InvalidatableField = 'maxCredit'

/** 用户输入表单的完整状态。 */
export interface UserInputForm {
  semester: string
  studentContext: StudentContext
  preference: {
    maxCredit: number | null
    avoidCrossCampus: boolean
    preferredCourses: string[]
    avoidTimes: AvoidTimeRow[]
    notes: string | null
  }
  currentSchedule: CourseOffering[]
  /**
   * 当前处于"用户输入了非法值"状态的字段。
   *
   * ⚠️ 这是区分两种情况的**必要条件**：
   * - **未被触碰 / 主动留空** → 按 `null`（default）序列化，**允许提交**；
   * - **用户确实输入了非法值** → 保留在 `null` 的同时记入本数组 → 表单 invalid → **禁止提交**。
   *
   * 只靠归一化后的 `null` 无法区分二者，因此必须有这个显式标记。
   * 该字段**不是**公共 `Preference` 的一部分，序列化时不会进入请求体。
   */
  invalidFields: InvalidatableField[]
}

/** 按 Case A 默认值创建表单状态。 */
export function createDefaultUserInputForm(): UserInputForm {
  return {
    semester: CASE_A_CONTEXT.semester,
    studentContext: {
      originMajor: CASE_A_CONTEXT.originMajor,
      targetMajor: CASE_A_CONTEXT.targetMajor,
      transferTerm: CASE_A_CONTEXT.transferTerm,
    },
    preference: {
      maxCredit: null,
      avoidCrossCampus: false,
      preferredCourses: [],
      avoidTimes: [],
      notes: null,
    },
    currentSchedule: [],
    invalidFields: [],
  }
}

/* -------------------------------------------------------------------------- */
/* 字段级校验（纯函数）                                                        */
/* -------------------------------------------------------------------------- */

/** 学期是否形如 `YYYY-1` / `YYYY-2`。不猜测、不自动补全。 */
export function isValidSemester(value: string): boolean {
  return SEMESTER_RE.test(value)
}

/**
 * 解析用户输入的学分上限。
 *
 * 返回 `null` 表示**未设定**；返回 `'invalid'` 表示输入不合法，此时**不得**猜测取值。
 */
export function parseMaxCredit(raw: string): number | null | 'invalid' {
  const text = raw.trim()
  if (text === '') {
    return null
  }
  if (!/^\d+(\.\d+)?$/.test(text)) {
    return 'invalid'
  }
  const value = Number(text)
  if (!Number.isFinite(value) || value < 0) {
    return 'invalid'
  }
  return value
}

/**
 * 把 `max_credit` 的原始输入归一化为"可序列化值 + 是否非法"。
 *
 * 这个区分是本文件最关键的守卫之一：
 * - **空串（未触碰 / 主动留空）** → `value: null`、`invalid: false` → 允许提交（按 default 序列化）；
 * - **非法值（负数 / 非数字 / 科学计数等）** → `value: null`、**`invalid: true`** → 表单一律 invalid，
 *   **禁止提交**；⛔ 既**不猜测**取值，也**不把非法输入静默降级成"未设定"**。
 */
export function normalizeMaxCreditInput(raw: string): {
  value: number | null
  invalid: boolean
} {
  const parsed = parseMaxCredit(raw)
  if (parsed === 'invalid') {
    return { value: null, invalid: true }
  }
  return { value: parsed, invalid: false }
}

/** 把 `'HH:MM'` 形式的节次输入解析为正整数；空串或非法输入返回 `null`。 */
export function parseSectionValue(raw: string): number | null {
  const text = raw.trim()
  if (!/^\d+$/.test(text)) {
    return null
  }
  const value = Number(text)
  return Number.isSafeInteger(value) && value >= 1 ? value : null
}

/**
 * 当前课表只能由**已加载的教学班**组成。
 *
 * ⚠️ 这里只做"是否为来源教学班"的身份校验，
 * **不研判冲突、不判断可行性、不做 Path Repair**。
 */
export function isScheduleOffering(
  value: unknown,
  offerings: readonly CourseOffering[],
): value is CourseOffering {
  if (value === null || typeof value !== 'object') {
    return false
  }
  const candidate = value as CourseOffering
  return offerings.some(
    (offering) =>
      offering.course_id === candidate.course_id &&
      offering.class_id === candidate.class_id &&
      offering.semester === candidate.semester,
  )
}

/* -------------------------------------------------------------------------- */
/* 单向操作                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * 切换一个教学班的"已选 / 未选"状态。
 *
 * 返回**新数组**，不修改入参；顺序稳定：新增项追加在末尾，便于测试与展示。
 * 未在来源列表中的教学班一律不接收（fail closed）。
 */
export function toggleCurrentScheduleOffering(
  current: readonly CourseOffering[],
  offering: CourseOffering,
  offerings: readonly CourseOffering[],
): CourseOffering[] {
  if (!isScheduleOffering(offering, offerings)) {
    return [...current]
  }

  const exists = current.some(
    (item) =>
      item.course_id === offering.course_id &&
      item.class_id === offering.class_id &&
      item.semester === offering.semester,
  )

  if (exists) {
    return current.filter(
      (item) =>
        !(
          item.course_id === offering.course_id &&
          item.class_id === offering.class_id &&
          item.semester === offering.semester
        ),
    )
  }

  return [...current, offering]
}

/**
 * 增加一条回避时段。
 *
 * 若未显式给出取值，则取一个**不与现有条目重复**的默认值；
 * 全部候选均被占用时仍返回一条新条目（不静默丢弃用户操作）。
 */
export function addAvoidTime(rows: readonly AvoidTimeRow[]): AvoidTimeRow[] {
  const exists = (weekday: number, start: number, end: number): boolean =>
    rows.some(
      (row) =>
        row.weekday === weekday && row.start_section === start && row.end_section === end,
    )

  for (let weekday = 1; weekday <= 7; weekday += 1) {
    if (!exists(weekday, 1, 2)) {
      return [...rows, createAvoidTimeRow({ weekday, start_section: 1, end_section: 2 })]
    }
  }

  return [...rows, createAvoidTimeRow({ weekday: 1, start_section: 1, end_section: 2 })]
}

/** 按 `key` 删除一条回避时段；`key` 不存在时返回等值新数组。 */
export function removeAvoidTime(rows: readonly AvoidTimeRow[], key: number): AvoidTimeRow[] {
  return rows.filter((row) => row.key !== key)
}

/** 更新一条回避时段的部分字段；`key` 不存在时返回等值新数组。 */
export function updateAvoidTime(
  rows: readonly AvoidTimeRow[],
  key: number,
  patch: Partial<Omit<AvoidTimeRow, 'key'>>,
): AvoidTimeRow[] {
  return rows.map((row) => (row.key === key ? { ...row, ...patch } : row))
}

/**
 * 维护意向课程（`preferred_courses`）。
 *
 * 与本项目既有口令一致：空白字符串不产生条目（`''` 语义是"清空"），
 * 重复项不产生第二条（`uniqueItems`）。
 */
export function addPreferredCourse(
  courses: readonly string[],
  courseId: string,
): string[] {
  const value = courseId.trim()
  if (value === '' || courses.includes(value)) {
    return [...courses]
  }
  return [...courses, value]
}

/** 删除一个意向课程；不存在时返回等值新数组。 */
export function removePreferredCourse(
  courses: readonly string[],
  courseId: string,
): string[] {
  return courses.filter((item) => item !== courseId)
}

/* -------------------------------------------------------------------------- */
/* 序列化（严格对齐公共 Schema）                                                */
/* -------------------------------------------------------------------------- */

/**
 * 把表单状态序列化为公共 `Preference`。
 *
 * 规则（严格对齐 `schemas/preference.schema.json`）：
 * - 只输出 `max_credit` / `avoid_cross_campus` / `preferred_courses` / `avoid_times` / `notes`；
 * - 空备注归一为 `null`；未设定学分上限为 `null`；
 * - `avoid_times[]` 只含 `weekday` / `start_section` / `end_section`（丢掉前端用的 `key`）。
 *
 * ⚠️ 不合法（`null` 或 `< 0`）的学分上限**不会被猜测**：按"未设定"处理。
 */
export function buildPreference(form: UserInputForm): Preference {
  const maxCredit = form.preference.maxCredit
  const normalizedMaxCredit =
    maxCredit === null || maxCredit === undefined || !Number.isFinite(maxCredit) || maxCredit < 0
      ? null
      : maxCredit

  const notes = form.preference.notes
  const normalizedNotes =
    notes === null || notes === undefined || notes.trim() === '' ? null : notes

  return {
    max_credit: normalizedMaxCredit,
    avoid_cross_campus: form.preference.avoidCrossCampus,
    preferred_courses: [...form.preference.preferredCourses],
    avoid_times: form.preference.avoidTimes.map(
      (row): AvoidTime => ({
        weekday: row.weekday,
        start_section: row.start_section,
        end_section: row.end_section,
      }),
    ),
    notes: normalizedNotes,
  }
}

/** 当前课表严格是 `CourseOffering[]`（原样传递来源对象，不加工、不裁剪）。 */
export function buildCurrentSchedule(form: UserInputForm): CourseOffering[] {
  return [...form.currentSchedule]
}

/**
 * 失败原因：当前课表里含有 **Mock 来源**（`data_source === 'mock'`）的教学班。
 *
 * 在真实 `CourseOffering` 接入之前，Mock 教学班不得进入 Real Planning ——
 * 否则会把"演示用假教学班"当成学生真实已选课程提交给真实求解链路。
 */
export const MOCK_SCHEDULE_BLOCK_REASON =
  '当前课表来源为 Mock 教学班，不能提交到 Real Planning。真实教学班接入前，请先清空当前课表中的 Mock 教学班。'

/**
 * 当前课表是否含有 Mock 来源的教学班。
 *
 * ⚠️ 只看 `data_source`，与"页面当前处于哪个模式"无关：
 * provenance 是**数据自身**的属性，不因界面模式而改变。
 */
export function hasMockSchedule(form: UserInputForm): boolean {
  return form.currentSchedule.some((offering) => offering.data_source === 'mock')
}

/**
 * provenance 门禁：当前课表是否**允许**提交到 Real Planning。
 *
 * - **空课表** → 允许（没有 provenance 不明的数据）；
 * - **全部为 real 教学班** → 允许；
 * - **含任意 mock 教学班** → **禁止**（`fetch` 0 次调用）。
 *
 * ⚠️ 这是**数据来源**校验，不是学业 / 排课可行性判断。
 */
export function isScheduleSubmittableToRealPlanning(form: UserInputForm): boolean {
  return !hasMockSchedule(form)
}

/**
 * 表单是否完整、可提交。
 *
 * ⚠️ 这是**输入完整性**校验（学期格式、学分范围、节次范围、时段先后），
 * **不是**学业或排课可行性判断。
 *
 * 关键区分：
 * - **未被触碰 / 主动留空**的字段 → 合法（按 `null` / default 序列化）；
 * - **用户输入过非法值**的字段 → 记在 `invalidFields` 中 → 一律 invalid，**禁止提交**。
 */
export function isFormValid(form: UserInputForm): boolean {
  // 用户确实输入过非法值（例如负数 / 非数字学分）→ 直接 invalid。
  // 这条不能省：归一化后 max_credit 也是 null，与"未设定"无法区分。
  if (form.invalidFields.length > 0) {
    return false
  }

  if (!isValidSemester(form.semester.trim())) {
    return false
  }

  const maxCredit = form.preference.maxCredit
  if (maxCredit !== null && (!Number.isFinite(maxCredit) || maxCredit < 0)) {
    return false
  }

  for (const row of form.preference.avoidTimes) {
    const validWeekday = Number.isInteger(row.weekday) && row.weekday >= 1 && row.weekday <= 7
    const validStart = Number.isInteger(row.start_section) && row.start_section >= 1
    const validEnd = Number.isInteger(row.end_section) && row.end_section >= 1
    if (!validWeekday || !validStart || !validEnd || row.end_section < row.start_section) {
      return false
    }
  }

  return true
}

/**
 * 提交到 Real Planning 前的综合门禁（**纯函数**，可直接测试）。
 *
 * 两道**独立**条件，任一不满足都**不得发出请求**：
 * 1. 输入完整性（`isFormValid`）；
 * 2. provenance：当前课表不得含 Mock 教学班。
 *
 * ⚠️ 这不是学业 / 排课可行性判断，只是"能不能发这个请求"。
 */
export function evaluatePlanSubmission(form: UserInputForm): {
  allowed: boolean
  reason: string
} {
  if (!isFormValid(form)) {
    return { allowed: false, reason: '表单存在未修正的输入问题，已阻止提交；未发出任何请求。' }
  }

  if (!isScheduleSubmittableToRealPlanning(form)) {
    return { allowed: false, reason: MOCK_SCHEDULE_BLOCK_REASON }
  }

  return { allowed: true, reason: '' }
}

/** 提交目标 Real 接口所需的三个字段（**只有**这三个）。 */
export interface RealPlanRequestInput {
  semester: string
  current_schedule: CourseOffering[]
  preference: Preference
}

/**
 * 组装 `POST /api/v1/plan` 的请求体。
 *
 * ⚠️ 严格只有 `semester` / `current_schedule` / `preference` 三个键。
 * 学生上下文（原专业 / 目标专业 / 转入学期）本轮**不进入请求**，
 * 也不存在任何额外的前端自造字段。
 */
export function buildRealPlanRequest(form: UserInputForm): RealPlanRequestInput {
  return {
    semester: form.semester.trim(),
    current_schedule: buildCurrentSchedule(form),
    preference: buildPreference(form),
  }
}

/** 校验成绩单文件是否为受支持的 `.xlsx`（大小写不敏感）；其余一律拒绝。 */
export function isSupportedGradeFile(fileName: string): boolean {
  return fileName.trim().toLowerCase().endsWith(XLSX_EXTENSION)
}
