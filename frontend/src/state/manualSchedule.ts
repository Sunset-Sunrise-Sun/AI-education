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
 * ## 关于 `data_source`（**重要，不得简化**）
 *
 * 手工录入**不是**学校系统的授权查询结果，因此它**不能**默认声称 `data_source="real"`。
 * `data_source` 是**契约 / 来源声明**（`mock` 与 `real` 两种取值），不是 provenance 证明。
 * 所以：
 *
 * - 默认（`MANUAL_SCHEDULE_PROVENANCE = 'unverified'`）→ 记 `mock`：
 *   provenance 门禁会**阻止**把它提交到 Real Planning（这是**正确**行为）；
 * - 只有负责人**显式**在 `.env.local` 里设置
 *   `VITE_MANUAL_SCHEDULE_PROVENANCE=student_attested_real`
 *   （= 明确声明"这些条目由学生本人提供、代表其真实已选课程"）时才记 `real`。
 *   ⛔ 这**不是**静默 fallback：默认关闭、必须显式设置、且在页面上如实标注。
 */

import type { CourseOffering, DataSource, Meeting } from '../types/contracts'

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
 * - 空白可选字段（campus / classroom）归一为 `null`（公共 Schema 允许 `null`）。
 */
export function buildOfferingFromManualEntry(
  entry: ManualScheduleEntry,
  provenance: DataSource,
): { offering: CourseOffering | null; errors: ManualScheduleFieldError[] } {
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
      // ⛔ 手工录入不声明任何"学校系统已查询"的含义；来源由调用方显式决定。
      source: 'manual-entry://current-schedule',
      data_source: provenance,
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
