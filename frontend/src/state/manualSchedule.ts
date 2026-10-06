/**
 * `current_schedule` **手工结构化录入**的纯逻辑层（不含 Vue 组件 / DOM / 网络）。
 *
 * ## 为什么需要它
 *
 * 原先的当前课表输入**只能勾选已加载的教学班**（`CurrentScheduleInput`）。
 * 但 Case A 的真实场景是：学生要录入自己**已经在选课系统里选中的班**，
 * 而这些班不一定恰好出现在当前页面加载的教学班列表里（尤其是演示快照只覆盖
 * 部分校区时）。要求用户手写裸 JSON 既不可用、也容易出错，因此这里提供
 * **结构化字段 → 公共 `CourseOffering`** 的确定性转换。
 *
 * ## 硬边界（⛔ 不得越界）
 *
 * - 只做"把用户填的字段拼成公共 `CourseOffering`"，⛔ **不做**课程等价判定；
 * - ⛔ **不做**冲突检测、⛔ 不判断 feasible、⛔ 不做 Path Repair、⛔ 不计算学分；
 * - ⛔ **不新增字段**：输出对象严格是 `schemas/course_offering.schema.json` 的形状；
 * - ⛔ 不猜测缺失取值：日期 / 节次 / 周次缺失或非法 → 明确报错，**不静默补默认值**；
 * - `meetings` 至少 1 段（用户确实知道自己的上课时间）；"排课信息未知"属于
 *   Course Data 侧的真实数据状态，⛔ 不由手工表单伪造。
 *
 * ## 关于 `data_source` 与**用户级 attestation**（⛔ 不得简化）
 *
 * 手工录入**不是**学校系统的授权查询结果，因此它**不能**天然具有
 * `data_source="real"`。`data_source` 是**契约 / 来源声明**（只有 `mock` / `real`
 * 两个取值），⛔ 不是 provenance 证明。本模块的规则是：
 *
 * ```text
 * 录入 / 加入课表          → 一律 mock（⛔ 不声称学校来源）
 * 用户在 UI 上**显式确认**  → 才把这批手工条目切换成 real（学生自述输入）
 * 用户取消确认            → 立即切回 mock（门禁重新阻断）
 * 手工课表被改动          → 确认作废（⛔ 旧确认不得覆盖被修改过的数据）
 * ```
 *
 * ⛔ 这与"把手工录入冒充学校数据"是两件事：`source` 始终是
 * `manual-entry://current-schedule`，页面也逐字说明"本人填写、未经学校系统核验"。
 * ⛔ 唯一的解锁入口是**用户勾选**；⛔ 不存在任何构建期环境变量旁路。
 */

import type { CourseOffering, DataSource, Meeting } from '../types/contracts'

/**
 * 手工录入条目在公共 `source` 字段上的**唯一**标记。
 *
 * ⚠️ 这是**真实**的来源标签（不是"学校来源"的伪装），因此可以用来识别
 * "哪些 `current_schedule` 条目来自手工录入、需要用户确认"。
 */
export const MANUAL_SCHEDULE_SOURCE = 'manual-entry://current-schedule'

/** 手工录入的一行（前端内部结构，⛔ 不进入公共契约）。 */
export interface ManualScheduleEntry {
  /** 仅用于前端列表渲染，⛔ 不进入公共契约。 */
  key: number
  courseId: string
  courseName: string
  classId: string
  semester: string
  /** 1=周一 … 7=周日；`null` 表示未填。 */
  weekday: number | null
  startSection: number | null
  endSection: number | null
  /** 原始周次文本，例如 `1-16`、`1-16,18`；由 `parseWeeksInput` 展开。 */
  weeksText: string
  campus: string
  classroom: string
}

/** 字段级错误标识（⛔ 只报字段名，不回显用户输入的整行内容）。 */
export type ManualScheduleField =
  | 'courseId'
  | 'courseName'
  | 'classId'
  | 'semester'
  | 'weekday'
  | 'sections'
  | 'weeks'

export interface ManualScheduleFieldError {
  field: ManualScheduleField
  message: string
}

/** 展开后的公共 `Meeting` 取值 + 供展示的字段错误。 */
export interface ManualScheduleResult {
  meeting: Meeting | null
  errors: ManualScheduleFieldError[]
}

/**
 * **手工录入课表的 attestation 状态**（前端内部结构，⛔ 不进入任何请求体）。
 *
 * 语义（⛔ 与"学校核验"无关，不得混同）：
 *
 * - `attested === false`（**默认**）⇒ 手工条目保持 `data_source="mock"`
 *   ⇒ 既有 provenance 门禁**阻断**提交到 Real Planning；
 * - `attested === true` ⇒ 手工条目切换成 `data_source="real"`，
 *   含义是**学生本人自述**"这些是我本学期已选的课"，⛔ 不是学校系统已核验。
 */
export interface ManualScheduleAttestationState {
  /** 用户是否已**显式确认**本人填写的手工课表。 */
  attested: boolean
  /** 用户确认时点（ISO 文本；仅用于审计展示，⛔ 不进入请求体）。 */
  confirmedAt: string | null
  /**
   * 确认是否**因课表被改动而作废**（⛔ 旧确认不得覆盖被修改过的数据）。
   *
   * ⚠️ 这是**持续**状态，不是一次性提示：只要用户还没重新确认，
   * 界面就应该继续显示"需要重新确认"，⛔ 不因后续继续编辑而消失。
   * 用户重新勾选确认时清零。
   */
  invalidated: boolean
}

/** 默认（**未确认**）状态：手工课表不可提交 Real Planning。 */
export function createManualScheduleAttestation(): ManualScheduleAttestationState {
  return { attested: false, confirmedAt: null, invalidated: false }
}

/**
 * 该课表条目是否来自**手工录入**。
 *
 * 判据是公共 `source` 字段上的真实标记（⛔ 不是猜测、⛔ 不是学校来源伪装）。
 */
export function isManualScheduleOffering(offering: CourseOffering): boolean {
  return offering.source === MANUAL_SCHEDULE_SOURCE
}

/** 课表里是否存在手工录入条目（用于决定是否需要展示确认控件）。 */
export function hasManualScheduleOffering(schedule: readonly CourseOffering[]): boolean {
  return schedule.some(isManualScheduleOffering)
}

/**
 * 把 `current_schedule` 中的**手工录入条目**统一切换来源标记。
 *
 * - `dataSource = 'real'` ⇒ 用户已确认：这些条目进入 Real Planning 作为**学生自述**输入；
 * - `dataSource = 'mock'` ⇒ 未确认 / 已撤销 / 已作废：门禁重新阻断；
 *
 * ⛔ 只改手工条目的 `data_source`：学校/其它来源的条目**原样保留**，
 * ⛔ 不触碰 `meetings` / 课程身份 / 其它任何字段（除 `data_source` 外逐字段相同）。
 */
export function setManualScheduleProvenance(
  schedule: readonly CourseOffering[],
  dataSource: DataSource,
): CourseOffering[] {
  return schedule.map((item) =>
    isManualScheduleOffering(item) && item.data_source !== dataSource
      ? { ...item, data_source: dataSource }
      : item,
  )
}

/**
 * 应用一次 attestation 变更（**唯一**的状态转移入口）。
 *
 * ```text
 * attested = true   → 手工条目 data_source = real（允许提交），清除"已作废"标记
 * attested = false  → 手工条目 data_source = mock（门禁阻断）
 * ```
 *
 * ⛔ 该函数不校验表单、不发请求、不写库；它只做这一个确定性的标记切换。
 */
export function applyManualScheduleAttestation(
  schedule: readonly CourseOffering[],
  attested: boolean,
  now: string | null = null,
): { schedule: CourseOffering[]; attestation: ManualScheduleAttestationState } {
  return {
    schedule: setManualScheduleProvenance(schedule, attested ? 'real' : 'mock'),
    attestation: {
      attested,
      confirmedAt: attested ? (now ?? new Date().toISOString()) : null,
      invalidated: false,
    },
  }
}

/**
 * 课表被改动 ⇒ 把既有确认标记为**已作废**（⛔ 不静默继续沿用旧确认）。
 *
 * - 原先已确认 ⇒ 手工条目切回 `mock`，并置 `invalidated = true`；
 * - 原先未确认 ⇒ 状态不变（⛔ 不因为"编辑了一下"就产生一个假的"曾确认过"提示）。
 */
export function invalidateManualScheduleAttestation(
  schedule: readonly CourseOffering[],
  attestation: ManualScheduleAttestationState,
): { schedule: CourseOffering[]; attestation: ManualScheduleAttestationState; invalidated: boolean } {
  if (!attestation.attested) {
    return { schedule: [...schedule], attestation, invalidated: false }
  }

  return {
    schedule: setManualScheduleProvenance(schedule, 'mock'),
    attestation: { attested: false, confirmedAt: null, invalidated: true },
    invalidated: true,
  }
}

/** 学期文本形式：与项目既有口径一致（`YYYY-1` / `YYYY-2`）。 */
const SEMESTER_RE = /^\d{4}-[12]$/

let nextEntryKey = 1

/** 创建一条空白手工录入行；学期取当前表单学期，避免用户重复输入。 */
export function createManualScheduleEntry(semester: string): ManualScheduleEntry {
  return {
    key: nextEntryKey++,
    courseId: '',
    courseName: '',
    classId: '',
    semester,
    weekday: null,
    startSection: null,
    endSection: null,
    weeksText: '',
    campus: '',
    classroom: '',
  }
}

/**
 * 解析周次输入：`1-16`、`1-16,18`、`1,3,5-7`（也接受中文逗号与"周"字）。
 *
 * 返回**升序去重**的正整数数组；任何非法片段整条返回 `null`（⛔ 不部分接受、⛔ 不猜测）。
 * 纯展开计算：⛔ 不判断哪些周"实际要上课"、⛔ 不解释单双周。
 */
export function parseWeeksInput(raw: string): number[] | null {
  const text = raw
    .replace(/[周週]/g, '')
    .replace(/[，、]/g, ',')
    .trim()
  if (text === '') {
    return null
  }

  const weeks = new Set<number>()
  for (const chunk of text.split(',')) {
    const part = chunk.trim()
    if (part === '') {
      return null
    }

    const range = /^(\d+)\s*-\s*(\d+)$/.exec(part)
    if (range) {
      const start = Number(range[1])
      const end = Number(range[2])
      if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 1 || end < start) {
        return null
      }
      if (end - start > 60) {
        // 单个区间过宽：几乎一定是输入错误（学期没有这么多周）。
        return null
      }
      for (let week = start; week <= end; week += 1) {
        weeks.add(week)
      }
      continue
    }

    if (!/^\d+$/.test(part)) {
      return null
    }
    const single = Number(part)
    if (!Number.isSafeInteger(single) || single < 1 || single > 60) {
      return null
    }
    weeks.add(single)
  }

  return [...weeks].sort((left, right) => left - right)
}

/**
 * 把一行手工录入转成公共 `CourseOffering`。
 *
 * 返回 `{ offering, errors }`：
 * - `errors` 非空 ⇒ `offering` 为 `null`，⛔ **不产出半个对象**、⛔ 不补默认值；
 * - 空白可选字段（campus / classroom）归一为 `null`（公共 Schema 允许 `null`）；
 * - `data_source` **恒为 `mock`**：未经用户显式确认的手工录入
 *   ⛔ **不**声称任何真实来源；确认后由 `applyManualScheduleAttestation()` 统一切换。
 */
export function buildOfferingFromManualEntry(entry: ManualScheduleEntry): {
  offering: CourseOffering | null
  errors: ManualScheduleFieldError[]
} {
  const errors: ManualScheduleFieldError[] = []

  const courseId = entry.courseId.trim()
  if (courseId === '') {
    errors.push({ field: 'courseId', message: '请填写课程号' })
  }

  const courseName = entry.courseName.trim()
  if (courseName === '') {
    errors.push({ field: 'courseName', message: '请填写课程名称' })
  }

  const classId = entry.classId.trim()
  if (classId === '') {
    errors.push({ field: 'classId', message: '请填写教学班号' })
  }

  const semester = entry.semester.trim()
  if (!SEMESTER_RE.test(semester)) {
    errors.push({ field: 'semester', message: '学期需形如 2026-1 / 2026-2' })
  }

  const weekday = entry.weekday
  if (weekday === null || !Number.isInteger(weekday) || weekday < 1 || weekday > 7) {
    errors.push({ field: 'weekday', message: '请选择星期（周一至周日）' })
  }

  const startSection = entry.startSection
  const endSection = entry.endSection
  if (
    startSection === null ||
    endSection === null ||
    !Number.isInteger(startSection) ||
    !Number.isInteger(endSection) ||
    startSection < 1 ||
    endSection < 1
  ) {
    errors.push({ field: 'sections', message: '请填写节次（第几节到第几节）' })
  } else if (endSection < startSection) {
    errors.push({ field: 'sections', message: '结束节次不能小于开始节次' })
  }

  const weeks = parseWeeksInput(entry.weeksText)
  if (weeks === null || weeks.length === 0) {
    errors.push({ field: 'weeks', message: '请填写周次，例如 1-16 或 1-16,18' })
  }

  if (errors.length > 0) {
    return { offering: null, errors }
  }

  const campus = entry.campus.trim()
  const classroom = entry.classroom.trim()

  return {
    offering: {
      course_id: courseId,
      course_name: courseName,
      class_id: classId,
      semester,
      meetings: [
        {
          weekday: weekday as number,
          start_section: startSection as number,
          end_section: endSection as number,
          weeks: weeks as number[],
          campus: campus === '' ? null : campus,
          classroom: classroom === '' ? null : classroom,
        },
      ],
      // ⛔ 这里刻意**不**声称学校来源：`source` 如实标明是手工录入，
      //    `data_source` 在用户显式确认之前恒为 `mock`。
      source: MANUAL_SCHEDULE_SOURCE,
      data_source: 'mock',
    },
    errors: [],
  }
}

/** 判断某个字段是否报错（供表单逐字段显示）。 */
export function hasFieldError(
  errors: readonly ManualScheduleFieldError[],
  field: ManualScheduleField,
): boolean {
  return errors.some((item) => item.field === field)
}

/** 手工录入行是否**已经填了任何内容**（用于决定"添加"是新增还是提示）。 */
export function isEmptyManualEntry(entry: ManualScheduleEntry): boolean {
  return (
    entry.courseId.trim() === '' &&
    entry.courseName.trim() === '' &&
    entry.classId.trim() === '' &&
    entry.weeksText.trim() === '' &&
    entry.campus.trim() === '' &&
    entry.classroom.trim() === '' &&
    entry.weekday === null &&
    entry.startSection === null &&
    entry.endSection === null
  )
}
