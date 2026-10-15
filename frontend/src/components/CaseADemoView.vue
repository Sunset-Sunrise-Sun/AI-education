<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  CaseAApiError,
  loadCaseAOfferings,
  runCaseADemo,
  type CaseADemoResponse,
} from '../api/caseADemo'
import {
  addManualScheduleEntry,
  addPreferredCourse,
  applyManualAttestation,
  buildRealPlanRequest,
  createDefaultUserInputForm,
  invalidateManualAttestation,
  manualScheduleOfferingCount,
  removeCurrentScheduleOffering,
  removePreferredCourse,
  type ManualScheduleEntry,
} from '../state/userInput'
import { studentText } from '../utils/displayLanguage'
import { SAMPLE_MAJOR_OPTIONS, type MajorOption } from '../config'
import { loadMajors as loadMajorsApi, loadStudyPlan as loadStudyPlanApi } from '../api/studyPlan'
import { StudyPlanApiError, type MajorSummary, type StudyPlan } from '../types/studyPlan'
import {
  bothPlanYearsSupported,
  describePlanYearPair,
  describePlanYearScope,
  deriveTransferType,
  FUTURE_PLAN_YEARS,
  isSupportedPlanYear,
  SUPPORTED_PLAN_YEARS,
} from '../utils/planYear'
import type { CourseOffering } from '../types/contracts'
import CurrentScheduleEditor from './CurrentScheduleEditor.vue'
import CurrentScheduleList from './CurrentScheduleList.vue'
import TimetableImageImport from './TimetableImageImport.vue'
import FutureRoadmapView from './FutureRoadmapView.vue'
import IntentCourseSearch from './IntentCourseSearch.vue'
import ManualScheduleForm from './ManualScheduleForm.vue'
import MakeupGapAnalysis from './MakeupGapAnalysis.vue'
import RecommendedCourses from './RecommendedCourses.vue'
import StudyPlanPanel from './StudyPlanPanel.vue'
import TranscriptImageImport from './TranscriptImageImport.vue'
import type { ConfirmedCompletedCourseRecord } from '../api/transcriptImages'
import { ACCEPTED_IMAGE_TYPES } from '../api/transcriptImages'
import { DEMO_RECOGNIZED_BLOCKS } from '../mock/demoTimetableRecognition'
import { deriveFutureRoadmap, termLabel } from '../utils/futureRoadmap'
import type {
  CompletedCourseRecord,
  CourseState,
  FutureRoadmapResult,
} from '../utils/futureRoadmap'
import { loadCompletedCourses as loadCompletedCoursesApi } from '../api/completedCourses'
import {
  isCrossCampus,
  isEarlyMorning,
} from '../config/caseAStudyPlan'
import {
  groupByStatus,
  missingCourseIds,
  toMakeupAnalysis,
  type MakeupAnalysisItem,
} from '../utils/makeupAnalysis'
import PreferenceForm from './PreferenceForm.vue'
import PreferencePanel from './PreferencePanel.vue'
import SectionCard from './SectionCard.vue'
import WeeklyScheduleView from './WeeklyScheduleView.vue'

/** 说明卡的固定内容：⛔ 不承诺"系统会自动替换课程"，真实语义是"找候选 → 提建议 → 用户确认"。 */
const PLANNING_STEPS = [
  '分析你的培养要求和已有课程',
  '找出可能需要补修的课程',
  '根据时间、校区和课程安排推荐方案',
  '结合你的选课偏好完善本学期安排',
  '帮助你了解后续学期的学习路径',
] as const

const form = ref(createDefaultUserInputForm())

/**
 * 两个样本专业（组长本轮指定的范围）。
 * ⛔ 只作为下拉选项；组件内⛔ 不按专业名分叉做任何业务判断。
 */
const MAJOR_CHOICES = SAMPLE_MAJOR_OPTIONS

/**
 * ⚠️ 原专业与目标专业**不得相同**。
 *
 * 做法：把"对方已选中的那个"在该下拉框里标为 `disabled`，
 * 因此**无法通过界面**选成相同专业；若父级传入的历史值恰好相同，
 * 这里只**如实提示**，⛔ 不静默改写用户数据。
 */
const sameMajorSelected = computed(
  () => form.value.studentContext.originMajor === form.value.studentContext.targetMajor,
)

function isMajorDisabled(field: 'originMajor' | 'targetMajor', value: string): boolean {
  const context = form.value.studentContext
  const other = field === 'originMajor' ? context.targetMajor : context.originMajor
  // 只有“选中该值就会与对方撞车”时才禁用（即该值正好等于对方当前值）。
  // 不能反过来写“把对方的选择禁用”：那样在两者已经相同时会把两个选项同时禁用，
  // 用户无法改回，页面会卡死。
  return value === other
}

/**
 * 可选培养方案年级。
 *
 * ⚠️ 本轮**只有 2025 级有数据支持**（样本均为 2025 平转 2025）。
 * `2026级` 只登记在 `FUTURE_PLAN_YEARS` 里作将来扩充用，⛔ 不作为可选项渲染。
 */
const PLAN_YEAR_CHOICES = SUPPORTED_PLAN_YEARS

/** 尚未有数据支持的年级（仅用于如实提示，⛔ 不可选）。 */
const PENDING_PLAN_YEARS = FUTURE_PLAN_YEARS

/** 年级选项是否可选：必须有数据支持。 */
function isPlanYearDisabled(value: string): boolean {
  return !isSupportedPlanYear(value)
}

function onPlanYearChange(field: 'originPlanYear' | 'targetPlanYear', event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  form.value = {
    ...form.value,
    studentContext: { ...form.value.studentContext, [field]: value },
  }
}

/** 当前转专业类型（仅展示用归类，⛔ 不参与任何业务规则）。 */
const transferType = computed(() =>
  deriveTransferType(
    form.value.studentContext.originPlanYear,
    form.value.studentContext.targetPlanYear,
  ),
)

/** 卡片底部简短摘要，例如 `2025 平转 2025`。 */
const planYearPairLabel = computed(() =>
  describePlanYearPair(
    form.value.studentContext.originPlanYear,
    form.value.studentContext.targetPlanYear,
  ),
)

/** 例如 `2025 → 2025：遥感科学与技术 → 网络空间安全`。 */
const planYearScopeLabel = computed(() =>
  describePlanYearScope(
    form.value.studentContext.originPlanYear,
    form.value.studentContext.targetPlanYear,
    form.value.studentContext.originMajor,
    form.value.studentContext.targetMajor,
  ),
)

/**
 * 所选年级是否**都有数据支持**。
 *
 * ⚠️ 若为 false，页面**如实说明**实际规划仍使用 2025 级样本，
 *    并且**不把所选年级送进任何请求**（后端本来也不接收该字段）。
 */
const planYearsSupported = computed(() =>
  bothPlanYearsSupported(
    form.value.studentContext.originPlanYear,
    form.value.studentContext.targetPlanYear,
  ),
)

function onMajorChange(field: 'originMajor' | 'targetMajor', event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  form.value = {
    ...form.value,
    studentContext: { ...form.value.studentContext, [field]: value },
  }
}
const offerings = ref<CourseOffering[]>([])
const transcript = ref<File | null>(null)
/**
 * **用户已在确认页确认**的成绩单图片课程记录（Phase 5）。
 *
 * ⚠️ 与成绩单 PDF **二选一**（后端强制）：
 *   - 上传 PDF ⇒ 走 `transcript_pdf_base64`；
 *   - 只上传图片并确认 ⇒ 走 `confirmed_completed_courses`；
 *   - ⛔ 两者同时提供会被后端拒绝（`case_a_demo_transcript_input_ambiguous`）。
 * ⛔ 未确认的 OCR 候选**不会**出现在这里。
 */
const confirmedImageCourses = ref<ConfirmedCompletedCourseRecord[]>([])
const result = ref<CaseADemoResponse | null>(null)
// 学生已核对的课程作为页面级输入状态保存；只用于前端连续规划体验，不改写 API 请求。
const confirmedPlanInputKeys = ref<string[]>([])
const loading = ref(false)
const error = ref('')

// 编辑规划输入后旧结果作废；课程核对状态保留，供下一次生成结果恢复展示。
// ⚠️ 修复：此前 `watch(form, …, { deep: true })` 会在**任何**深层变化时清空
//   `result` —— 包括学生点「加入当前课表 / 移除」。那会让补修分析、推荐选课、
//   课表一起消失，动态交互链路直接断掉。
// 现在只有**会改变后端请求语义**的字段变化才作废结果。
const resultInvalidatingInputs = computed(() => ({
  studentContext: form.value.studentContext,
  semester: form.value.semester,
  preference: form.value.preference,
  manualScheduleEntries: form.value.manualScheduleEntries,
}))
watch(resultInvalidatingInputs, () => { result.value = null }, { deep: true })
// 转专业上下文本身变化时，之前目标专业下的课程核对不再沿用。
watch(() => form.value.studentContext, () => { confirmedPlanInputKeys.value = [] }, { deep: true })

/**
 * 教学班（offerings）的**真实加载状态**。
 *
 * ⚠️ 存在的理由（R1 修复）：页面此前**无条件**显示「真实教学班数据」，
 * 而该数据来自 `/api/v1/case-a-demo/offerings`，其运行时由环境变量开关控制，
 * 未配置时返回 503 ⇒ 会出现「已加载真实教学班数据 0 条」+ 报错的自相矛盾展示。
 *
 * 现在按状态如实展示：
 *   `idle`      尚未请求
 *   `loading`   请求中
 *   `success`   拿到 HTTP 200（列表可能为空，空列表**不等于**不可用）
 *   `error`     其它失败（网络 / 未知状态码）
 *   `not_configured` 后端 503 + `case_a_demo_not_configured`（运行时未配置）
 */
type OfferingsStatus = 'idle' | 'loading' | 'success' | 'error' | 'not_configured'
const offeringsStatus = ref<OfferingsStatus>('idle')

/**
 * 来源说明文案。
 *
 * ⚠️ 关键约束：`loadCaseAOfferings` 的响应是**裸数组** `CourseOffering[]`，
 * **不携带任何来源字段**。因此前端**没有证据**对这一批数据做来源认证，
 * 只能给出中性表述；⛔ 不得声称"真实""已核验"。
 * （规划结果 `/plan` 的响应**有** `provenance`，那部分按实际字段展示。）
 */
const OFFERINGS_SOURCE_NOTE =
  '请搜索并选择你的教学班，核对时间和地点后加入当前课表。'
const manualOpen = ref(false)

const manualCount = computed(() => manualScheduleOfferingCount(form.value))

/**
 * 当前课表被改动后，如果之前确认过的手工信息被作废，如实提示需要重新确认。
 * ⛔ 不暗示"学校已核验"，也⛔ 不把作废状态藏起来。
 */
const attestationNotice = computed(() =>
  form.value.manualAttestation.invalidated
    ? '当前课表在上次确认之后被改动，之前的确认已作废；请重新确认手工录入信息后再提交。'
    : '',
)

const resultCourseNames = computed(() => {
  const map: Record<string, string> = {}
  for (const task of result.value?.makeup_tasks ?? []) map[task.course_id] = task.course_name
  for (const item of result.value?.course_offerings ?? []) map[item.course_id] = item.course_name
  return map
})

/* ====================================================================== *
 * 动态交互状态链（**后端驱动**）
 *
 * 后端 `makeup_tasks`（真实匹配结果：status + reason + source_evidence）
 *   ↓ toMakeupAnalysis(..., confirmedMakeupCourses)   [utils/makeupAnalysis.ts]
 * makeupAnalysis（satisfied / need_confirmation / missing）
 *   ↓ 用户点【确认可转换】
 * confirmedMakeupCourses（学生本人确认，⛔ 不是系统自动认定）
 *   ↓ 重新分组 + 推荐池重算
 * recommendedCandidates
 *   ↓ 用户点【加入本学期方案】
 * selectedSemesterCourses
 *   ↓
 * 课表 = currentSchedule + selectedSemesterCourses
 *
 * ⚠️ 与旧实现的区别（本轮修正）：
 *   旧实现用前端 `caseAStudyPlan.ts` 的演示培养方案 + 硬编码成绩单课程名
 *   自行计算三状态。那套配置里的课程号/学分与学校真实培养方案并不一致，
 *   因此页面展示的"已满足/缺失"是与后端真实判定无关的另一套结果。
 *   现在三状态**完全来自后端**，前端只做 `status → 分组` 的映射。
 * ====================================================================== */

/** 推荐池大小上限。 */
const RECOMMEND_POOL_SIZE = 8

/** 本学期**确实有教学班**的课程号集合（由真实教学班数据算出，⛔ 不硬编码）。 */
const offeredCourseIds = computed(
  () => new Set((result.value?.course_offerings ?? []).map((offering) => offering.course_id)),
)

/** 当前课表的主校区（用于"避免跨校区"偏好判断）。 */
const primaryCampus = computed<string | null>(() => {
  for (const offering of form.value.currentSchedule) {
    for (const meeting of offering.meetings) {
      if (meeting.campus) return meeting.campus
    }
  }
  return null
})

/** 当前课表已占用的 (weekday, section) 集合，用于**时间冲突**判断。 */
const occupiedSlots = computed<Set<string>>(() => {
  const slots = new Set<string>()
  for (const offering of form.value.currentSchedule) {
    for (const meeting of offering.meetings) {
      for (let section = meeting.start_section; section <= meeting.end_section; section += 1) {
        slots.add(`${meeting.weekday}:${section}`)
      }
    }
  }
  return slots
})

/** 教学班是否与当前课表时间冲突。 */
function conflictsWithSchedule(offering: CourseOffering): boolean {
  for (const meeting of offering.meetings) {
    for (let section = meeting.start_section; section <= meeting.end_section; section += 1) {
      if (occupiedSlots.value.has(`${meeting.weekday}:${section}`)) return true
    }
  }
  return false
}

/** 用户已确认「可转换」的补修课程号（核心状态 ①，**学生本人确认**）。 */
const confirmedMakeupCourses = ref<string[]>([])

/**
 * **补修分析条目** —— 完全由后端真实 `makeup_tasks` 派生。
 *
 * ⛔ 组件内不做匹配、⛔ 不读前端演示培养方案；
 *   三状态映射集中在 `utils/makeupAnalysis.ts` 的 `toViewStatus()`。
 *
 * ⚠️ `confirmedMakeupCourses` 变化会重新映射：学生已确认的课程归入 `satisfied`，
 *   于是从待确认列表与推荐列表中同时消失（⛔ 不重新请求后端）。
 */
const makeupAnalysis = computed<MakeupAnalysisItem[]>(() =>
  toMakeupAnalysis(
    result.value?.makeup_tasks ?? [],
    offeredCourseIds.value,
    confirmedMakeupCourses.value,
  ),
)

/** 按三状态分组。 */
const analysisGroups = computed(() => groupByStatus(makeupAnalysis.value))

/** 已满足 —— ⛔ 不进推荐。 */
const satisfiedMatches = computed(() => analysisGroups.value.satisfied)

/** 待确认。 */
const confirmationMatches = computed(() => analysisGroups.value.needConfirmation)

/** 缺失（后端 `status === 'required'`）—— 推荐的**唯一**补修来源。 */
const missingMatches = computed(() => analysisGroups.value.missing)

/**
 * 推荐选课的候选池 —— 来源（⛔ 不是任意课程列表）：
 *   1. **缺失（missing）** 的培养要求 —— 必须补修；
 *   2. 目标的专业选修池 —— 本轮未接入（见报告「未完成」）。
 *
 * 过滤：时间冲突、已在当前课表、同课程只留一个教学班；
 * 排序：先补修、再按偏好（不早课 / 不跨校区），无排课信息排最后。
 *
 * ⛔ `satisfied`、`need_confirmation`（确认前）**绝不进入**推荐；
 * ⛔ 每个候选项都是**真实 CourseOffering 对象**。
 */

/* ---------------------------------------------------------------------- *
 * 推荐的两个来源（⛔ 严格分离，不混为一个列表）
 *
 *   A. 必须补修   来源 = 后端 makeup_tasks 中 status='required'（缺失）
 *                 含义 = 培养方案要求尚未完成 → 必须补
 *   B. 专业选修   来源 = 培养方案选修池（GET /api/v1/study-plans/{id}）
 *                 含义 = 属于目标专业选修池，帮助完成培养方向
 *
 * ⛔ B 不得被标成"补修课程"；⛔ 两者不得合并渲染。
 * ---------------------------------------------------------------------- */

/** 某课程号是否在本学期教学班数据中（真实教学班的课程号集合）。 */
function isOffered(courseId: string): boolean {
  return offeredCourseIds.value.has(courseId)
}

/** 教学班是否可用作推荐候选（未进当前课表 + 不冲突 + 本学期确实有班）。 */
function isUsableCandidate(offering: CourseOffering): boolean {
  const key = `${offering.course_id}::${offering.class_id}`
  if (inCurrentSchedule.value.has(key)) return false
  if (!isOffered(offering.course_id)) return false
  if (conflictsWithSchedule(offering)) return false
  return true
}

/** 当前课表里已占用的教学班身份。 */
const inCurrentSchedule = computed(
  () => new Set(form.value.currentSchedule.map((item) => `${item.course_id}::${item.class_id}`)),
)

/** 按偏好打分（越小越靠前；无排课信息排最后）。 */
function preferenceScore(offering: CourseOffering): number {
  if (offering.meetings.length === 0) return 99
  const meeting = offering.meetings[0]
  let value = 0
  if (isEarlyMorning(meeting.start_section)) value += 1
  if (isCrossCampus(meeting.campus ?? null, primaryCampus.value)) value += 1
  return value
}

/**
 * 从**指定课程号集合**里挑出推荐教学班（每个课程号只保留一个）。
 *
 * ⚠️ 只做"教学班层面的可用性筛选与排序"，
 *   ⛔ 不决定哪些课程号该进推荐 —— 那由调用方按来源给出。
 */
function pickOfferings(courseIds: ReadonlySet<string>): CourseOffering[] {
  if (courseIds.size === 0) return []
  const candidates = (result.value?.course_offerings ?? [])
    .filter((offering) => courseIds.has(offering.course_id))
    .filter(isUsableCandidate)
    .sort((left, right) => preferenceScore(left) - preferenceScore(right))

  const chosen = new Map<string, CourseOffering>()
  for (const offering of candidates) {
    if (chosen.size >= RECOMMEND_POOL_SIZE) break
    if (!chosen.has(offering.course_id)) chosen.set(offering.course_id, offering)
  }
  return [...chosen.values()]
}

/** A. 必须补修：只来自后端 `missing`。 */
const requiredMakeupRecommendations = computed<CourseOffering[]>(() =>
  pickOfferings(new Set(missingCourseIds(makeupAnalysis.value))),
)

/**
 * B. 专业选修推荐：只来自**培养方案选修池**。
 *
 * ⚠️ 仅当该培养方案确实提供了选修池时才给出；⛔ 不用演示配置补一份。
 * ⛔ 这些课程**不是**补修要求，页面必须分开标注。
 */
const electivePoolRecommendations = computed<CourseOffering[]>(() => {
  const plan = studyPlan.value
  if (!plan) return []
  const poolIds = new Set(plan.elective_pool.courses.map((course) => course.course_id))
  // 已满足 / 已在推荐 A 中出现的课程不重复出现在选修里。
  for (const item of makeupAnalysis.value) {
    if (item.status === 'satisfied') poolIds.delete(item.courseId)
  }
  for (const courseId of missingCourseIds(makeupAnalysis.value)) poolIds.delete(courseId)
  return pickOfferings(poolIds)
})

/** 兼容旧命名：推荐主列表 = 必须补修。 */
const recommendedCandidates = requiredMakeupRecommendations

/**
 * **合并后的推荐列表**（Phase 6，任务 2）。
 *
 * ⚠️ 只是把两个**已经算好**的列表拼在一起并保持顺序：
 *   A 必须补修在前，B 建议选修在后。
 * ⛔ 不改变任何来源、过滤条件或排序算法。
 */
const mergedRecommendations = computed<CourseOffering[]>(() => [
  ...requiredMakeupRecommendations.value,
  ...electivePoolRecommendations.value,
])

/** 某门推荐课的来源标签（供子组件渲染 A / B 标签，⛔ 子组件不猜）。 */
function recommendationTagOf(offering: CourseOffering): 'required' | 'elective' {
  return requiredMakeupRecommendations.value.some(
    (item) => item.course_id === offering.course_id && item.class_id === offering.class_id,
  )
    ? 'required'
    : 'elective'
}

/** 当前培养方案选修池的课程号集合（⛔ 不是"缺口"，只是"池子里有什么"）。 */
const electivePoolCourseIds = computed(
  () => new Set((studyPlan.value?.elective_pool.courses ?? []).map((course) => course.course_id)),
)

/** 用户已加入本学期方案的真实教学班（核心状态 ③）。 */
const selectedSemesterCourses = ref<CourseOffering[]>([])

/**
 * **已修课程**（成绩单事实）—— 未来路径判定 `satisfied` 的**唯一**依据。
 *
 * ⚠️ 存在的理由（Phase 7 Review 修正）：`/case-a-demo/plan` 只返回成绩单**摘要**，
 *   不返回已修课程明细；不读这份明细，已修课就会**重复出现在未来规划**里。
 * 数据来自**既有**接口 `POST /api/v1/completed-courses/import-pdf`（⛔ 未新增后端能力）。
 */
const completedCourses = ref<CompletedCourseRecord[]>([])
const completedStatus = ref<'idle' | 'loading' | 'success' | 'error'>('idle')

/**
 * **未来学习路径规划**（Phase 7 任务 2）—— 由**已有后端数据前端派生**。
 *
 * 数据来源（⛔ 前端不新增任何判定）：
 *   - 培养方案 `studyPlan`（含 `requirements[].recommended_term_text` 推荐学期）
 *   - 后端匹配结果 `result.makeup_tasks`（status）
 *   - **学生已修课程 `completedCourses`**（成绩单明细；⛔ 缺失时不排期）
 *   - 后端选修组进度 `result.elective_progress`（专业选修学分要求）
 *   - 当前学期 `form.semester`
 *
 * ⛔ 不是未来选课预测：不含教师 / 时间 / 地点 / 教学班。
 * ⛔ 不改 `matching` / `recommendation` / OCR，⛔ 不改后端 schema。
 */
const futureRoadmap = computed<FutureRoadmapResult>(() =>
  deriveFutureRoadmap(
    studyPlan.value,
    result.value?.makeup_tasks ?? [],
    result.value?.elective_progress ?? [],
    form.value.semester,
    completedCourses.value,
    // ⛔ 正在修（已在本学期课表里）的课不得排进未来学期 —— 实测踩过
    form.value.currentSchedule,
    // ✅ 状态闭环：学生在「补修缺口分析」里确认可转换后，未来路径**立即重算**
    //    （与 `makeupAnalysis` 共用**同一个**本地确认状态源，⛔ 不重新请求后端）
    confirmedMakeupCourses.value,
  ),
)

/**
 * 未来路径是否可以展示。
 *
 * ⚠️ **没有成绩单明细就不排期**：否则会把学生已修的课排进未来学期
 *   —— 那正是 Review 发现的错误。宁可如实说"读不到已修课程"。
 */
const futureRoadmapReady = computed(
  () =>
    completedStatus.value === 'success' &&
    studyPlan.value !== null &&
    futureRoadmap.value.semesters.length > 0,
)

/**
 * 是否已具备**完成度分析**的前提（成绩单明细 + 培养方案）。
 *
 * ⚠️ 与 `futureRoadmapReady` 分开：即使**一个学期都排不出来**
 *   （例如所有未确定课程都还在"待确认"），也必须显示"已完成什么 / 正在修什么 /
 *   还缺什么"——这正是本次要解决的"用户不知道整体完成到哪一步"的问题。
 */
const futureRoadmapAnalysed = computed(
  () => completedStatus.value === 'success' && studyPlan.value !== null,
)

/** 五状态里的某一类课程数（⛔ 组件内不判定，只读派生结果）。 */
function stateCount(state: CourseState): number {
  return futureRoadmap.value.states.find((item) => item.state === state)?.courseCount ?? 0
}

/** 学分展示：`null` 表示**学分待核验**，⛔ 不用 0 冒充。 */
function formatCredit(value: number | null): string {
  return value === null ? '待核验' : String(value)
}

/** 培养方案里是否列出了毕业设计（决定摘要那一行怎么措辞）。 */
const hasGraduationProject = computed(() =>
  (studyPlan.value?.requirements ?? []).some((item) => item.course_name.includes('毕业论文')),
)

/**
 * 图片路径下的"已修课程"= 用户**逐条确认**的记录（⛔ 不用 OCR 原始候选）。
 *
 * ⚠️ 与 PDF 路径共用同一份 `completedCourses`，未来路径因此对两条入口一致地扣除已修课程。
 */
watch(confirmedImageCourses, (records) => {
  if (transcript.value) return
  completedCourses.value = records.map((record) => ({
    course_name: record.course_name,
    credit: record.credit,
    passed: record.passed,
  }))
  completedStatus.value = records.length > 0 ? 'success' : 'idle'
})

/** 读取已修课程明细（仅供未来路径扣除已满足课程）。 */
async function loadCompletedCoursesFor(file: File): Promise<void> {
  completedStatus.value = 'loading'
  try {
    completedCourses.value = await loadCompletedCoursesApi(file)
    completedStatus.value = 'success'
  } catch {
    // ⛔ 失败时不猜测、⛔ 不用演示数据顶替：清空并按"读不到"如实降级。
    completedCourses.value = []
    completedStatus.value = 'error'
  }
}

/**
 * 确认补修可转换（核心交互 ①）。
 * ⛔ 只更新前端状态；⛔ 不写 currentSchedule、⛔ 不发请求、⛔ 不做课程认定。
 */
function confirmMakeupConversion(courseIds: readonly string[]): void {
  if (courseIds.length === 0) return
  confirmedMakeupCourses.value = [...new Set([...confirmedMakeupCourses.value, ...courseIds])]
}

/** 撤销补修确认（课程回到待确认列表）。 */
function undoMakeupConversion(courseId: string): void {
  confirmedMakeupCourses.value = confirmedMakeupCourses.value.filter((id) => id !== courseId)
}

/**
 * 确认「加入本学期方案」（核心交互 ②）。
 * ⚠️ 存入真实 CourseOffering；⛔ **不写入** `form.currentSchedule`。
 */
function confirmSemesterCourses(items: readonly CourseOffering[]): void {
  if (items.length === 0) return
  const existing = new Set(
    selectedSemesterCourses.value.map((item) => `${item.course_id}::${item.class_id}`),
  )
  const merged = [...selectedSemesterCourses.value]
  for (const item of items) {
    const key = `${item.course_id}::${item.class_id}`
    if (existing.has(key)) continue
    existing.add(key)
    merged.push(item)
  }
  selectedSemesterCourses.value = merged
}

/** 取消某门已加入本学期方案的课程（课表同步移除）。 */
function removeSemesterCourse(offering: CourseOffering): void {
  const key = `${offering.course_id}::${offering.class_id}`
  selectedSemesterCourses.value = selectedSemesterCourses.value.filter(
    (item) => `${item.course_id}::${item.class_id}` !== key,
  )
}

/**
 * 某门推荐课的推荐理由 —— 按**事实**生成，并引用后端给出的缺口理由。
 *
 * ⚠️ 两类来源的措辞必须不同（⛔ 不得把选修说成补修）：
 *   - 必修缺口：引用后端对该缺口的判定说明；
 *   - 专业选修：说明它来自培养方案选修池。
 */
function reasonFor(offering: CourseOffering): string {
  const item = missingMatches.value.find((entry) => entry.courseId === offering.course_id)
  const inElectivePool = electivePoolCourseIds.value.has(offering.course_id)
  const meeting = offering.meetings[0]
  const parts: string[] = []

  if (item) {
    parts.push('该课程属于目标专业培养要求中你尚未完成的缺口')
  } else if (inElectivePool) {
    parts.push('该课程属于目标专业培养方案的专业选修池，可用于完成选修学分方向')
  } else {
    parts.push('该课程已纳入本学期规划候选')
  }
  parts.push(
    isOffered(offering.course_id) ? '本学期已有可用教学班' : '本学期暂无可用教学班',
  )
  if (meeting && isEarlyMorning(meeting.start_section)) {
    parts.push('⚠️ 该教学班为第 1-2 节，与你"避免早课"的偏好不一致')
  }
  if (meeting && isCrossCampus(meeting.campus ?? null, primaryCampus.value)) {
    parts.push('⚠️ 该教学班在其他校区，与你"避免跨校区"的偏好不一致')
  }
  const base = `${parts.join('；')}。`
  // 必修缺口附带后端原始判定说明，便于学生核对为什么必须补修。
  return item?.reason ? `${base}培养方案判定说明：${item.reason}` : base
}

/* ====================================================================== *
 * 专业选择链（MajorSelector → 加载 StudyPlan → 决定匹配上下文）
 *
 * `GET /api/v1/majors`           → 下拉选项（专业名 + major_id）
 * `GET /api/v1/study-plans/{id}` → 该专业培养方案（要求 + 选修池）
 *
 * ⚠️ 这两个接口**不属于 case-a-demo**，也⛔ 不读前端演示配置。
 *   组件内⛔ 不按专业名分叉；专业名 → major_id 的对应关系由后端列表给出。
 * ====================================================================== */

/** 后端可用专业列表。 */
const majors = ref<MajorSummary[]>([])
/** 专业列表的加载状态（用于如实展示"未配置"）。 */
const majorsStatus = ref<'idle' | 'loading' | 'success' | 'error' | 'not_configured'>('idle')

/** 当前已加载的培养方案。 */
const studyPlan = ref<StudyPlan | null>(null)
const studyPlanStatus = ref<'idle' | 'loading' | 'success' | 'error' | 'not_configured'>('idle')
const studyPlanError = ref('')

/**
 * 下拉选项。
 *
 * ⚠️ 优先使用后端返回的专业；后端不可用时**回退到静态选项层**
 *   （`SAMPLE_MAJOR_OPTIONS`，仅用于离线演示），并如实提示。
 */
const majorChoices = computed<readonly MajorOption[]>(() =>
  majors.value.length > 0
    ? majors.value.map((m) => ({ value: m.name, label: m.name, majorId: m.major_id }))
    : MAJOR_CHOICES,
)

/** 把专业名解析为 `major_id`；找不到返回 `null`（⛔ 不猜测）。 */
function majorIdOf(majorName: string): string | null {
  return majorChoices.value.find((option) => option.value === majorName)?.majorId ?? null
}

/** 当前目标专业对应的 `major_id`。 */
const selectedMajorId = computed(() => majorIdOf(form.value.studentContext.targetMajor))

/** 当前所选专业是否有后端培养方案支撑。 */
const studyPlanAvailable = computed(() => studyPlan.value !== null)

/** 专业列表是否来自后端（用于页面上如实标注来源）。 */
const majorsFromBackend = computed(() => majors.value.length > 0)

/** 把专业/培养方案接口失败翻译为学生可读文案（⛔ 不隐藏、⛔ 不兜底到演示数据）。 */
function describeStudyPlanError(cause: unknown, subject: string): string {
  if (cause instanceof StudyPlanApiError) {
    if (cause.isNotConfigured) {
      return `${subject}尚未准备好（后端未配置专业注册表）。当前仅提供离线演示选项，不会用演示数据参与匹配。`
    }
    if (cause.isUnknownMajor) {
      return `该专业不在后端可用专业列表中，无法加载${subject}。`
    }
    if (cause.isNetworkFailure) {
      return `暂时无法连接后端，未能加载${subject}。`
    }
    return `${subject}加载失败：${cause.message}`
  }
  return `${subject}加载失败。`
}

async function loadMajors(): Promise<void> {
  majorsStatus.value = 'loading'
  try {
    // ⚠️ 防御：接口理论上返回数组，但⛔ 不让异常形状把渲染打崩。
    const loaded = await loadMajorsApi()
    majors.value = Array.isArray(loaded) ? loaded : []
    majorsStatus.value = 'success'
  } catch {
    majors.value = []
    majorsStatus.value = 'error'
  }
}

async function loadStudyPlanFor(majorName: string): Promise<void> {
  // ⚠️ 后端专业注册表不可用时**没有 major_id 可用**，因此直接进入 error 态。
  //    这一步必须显式发生，否则面板会停在"请先选择目标专业"的空状态，
  //    掩盖"后端未配置"这一真实原因。
  if (majorsStatus.value !== 'success') {
    studyPlan.value = null
    studyPlanStatus.value = 'error'
    studyPlanError.value = '后端专业注册表不可用，无法加载培养方案；⛔ 离线演示选项不参与匹配。'
    return
  }
  const majorId = majorIdOf(majorName)
  if (!majorId) {
    // ⛔ 没有对应 major_id 时**不猜测、不伪造**培养方案。
    studyPlan.value = null
    studyPlanStatus.value = 'error'
    studyPlanError.value = `「${majorName}」没有对应的培养方案数据，无法加载要求列表。`
    return
  }
  studyPlanStatus.value = 'loading'
  studyPlanError.value = ''
  try {
    studyPlan.value = await loadStudyPlanApi(majorId)
    studyPlanStatus.value = 'success'
  } catch (cause) {
    studyPlan.value = null
    studyPlanStatus.value = 'error'
    studyPlanError.value = describeStudyPlanError(cause, '培养方案')
  }
}

// 切换目标专业 → 重新加载培养方案（匹配上下文随之改变）。
watch(
  () => form.value.studentContext.targetMajor,
  (name) => { void loadStudyPlanFor(name) },
)

async function loadOfferings(): Promise<void> {
  error.value = ''
  offeringsStatus.value = 'loading'
  try {
    offerings.value = await loadCaseAOfferings(form.value.semester)
    // ⚠️ 空列表也是**成功**：接口确实答复了，只是该学期没有教学班。
    //    ⛔ 不得把"空"当成"未加载/不可用"。
    offeringsStatus.value = 'success'
    // ✅ 教学班数据一到就载入「原始课表」：让课表开页即包含学生已有的课程，
    //    ⛔ 不要求用户先点一次"生成方案"。
    loadOriginalSchedule()
  } catch (cause) {
    offerings.value = []
    if (cause instanceof CaseAApiError && cause.isNotConfigured) {
      offeringsStatus.value = 'not_configured'
      error.value = '教学班数据尚未准备好，请稍后重试。'
    } else {
      offeringsStatus.value = 'error'
      error.value = '暂时无法加载教学班，请检查服务连接后刷新页面。'
    }
  }
}

/** 教学班数据是否**已成功加载**（唯一允许展示"已加载"字样的依据）。 */
const offeringsLoaded = computed(() => offeringsStatus.value === 'success')

/** 顶部来源标签：只按真实状态表述，⛔ 不做无条件真实性认证。 */
const offeringsTagLabel = computed(() => {
  switch (offeringsStatus.value) {
    case 'loading':
      return '教学班数据加载中'
    case 'success':
      return '已加载教学班数据'
    case 'not_configured':
      return '教学班数据未配置'
    case 'error':
      return '教学班数据不可用'
    default:
      return '教学班数据待加载'
  }
})

/** 标签是否可用"已加载"的强调样式（仅在确实成功时）。 */
const offeringsTagEmphasized = computed(() => offeringsStatus.value === 'success')

/** 第二步副标题：按状态如实描述，⛔ 未成功时⛔ 不出现"已加载真实…"。 */
const scheduleSubtitle = computed(() => {
  const scope = '数据范围为南校园 + 深圳校区。'
  switch (offeringsStatus.value) {
    case 'loading':
      return `正在加载教学班数据；${scope}`
    case 'success':
      return `已加载教学班数据 ${offerings.value.length} 条；${scope}`
    case 'not_configured':
      return `教学班数据尚未准备好；${scope}`
    case 'error':
      return `教学班数据加载失败，当前无可展示教学班；${scope}`
    default:
      return `尚未加载教学班数据；${scope}`
  }
})

/** 统一入口的 file input 引用（用于清空 / 重新选择）。 */
const transcriptFileInput = ref<HTMLInputElement | null>(null)
/** 图片识别子组件引用（把图片文件派发给它，复用其唯一识别路径）。 */
const transcriptImageImport = ref<InstanceType<typeof TranscriptImageImport> | null>(null)

/**
 * **统一成绩单入口**（Phase 6）：一个控件同时接受 PDF 与图片。
 *
 * ```text
 * 选择文件
 *   ├─ PDF   → 原流程（transcript_pdf_base64）
 *   └─ 图片  → 派发给图片识别组件（本机预览 → OCR → 确认页）
 * ```
 *
 * ⚠️ 后端接口与匹配逻辑**完全未改**：两条分支只是各自填写自己的输入字段。
 */

/* ====================================================================== *
 * 原始课表（demo：来自课表截图识别演示数据）
 *
 * ## 需求
 *
 * 课表必须包含**用户上传的原始课表**里的课程 —— 也就是「上传我的课表截图」
 * 识别出来的那些格位。此前那条链路只把识别结果挂成"待匹配候选"，
 * **从不写进 `currentSchedule`**，所以课表里看不到原始课表。
 *
 * ## 做法
 *
 * 把识别块的**课程名 + 星期**匹配到 `offerings`（后端下发的真实教学班）：
 *
 * ```text
 * 识别块 courseName + weekday
 *   ↓ 在 offerings 中找 course_name 完全同名、且有一个 meeting 落在该星期的教学班
 *   ↓ 命不中（该课本学期无教学班 / 多义）⇒ **跳过并如实记录**，⛔ 不猜
 * 真实 CourseOffering（原样使用，⛔ 一个字段都不改）
 *   ↓
 * currentSchedule（课表即可绘制，来源标注为"当前课表"）
 * ```
 *
 * ⚠️ 边界：
 *   - 课程对象**全部是后端下发的真实教学班**，⛔ 不伪造课号/时间/地点/教师；
 *   - 识别数据本身是**演示固定数据**（`mock/demoTimetableRecognition.ts`），
 *     页面上如实标注，⛔ 不冒充真实 OCR；
 *   - 匹配不上的课**不猜**：列在"未能定位"里交回用户；
 *   - ⛔ 不改断任何课程对象字段（后端会做逐字段一致性校验）。
 * ====================================================================== */

/** 是否已载入原始课表（只做一次，⛔ 不覆盖用户操作）。 */
const originalScheduleLoaded = ref(false)
/** 原始课表中**未能定位到真实教学班**的课程名（如实展示，⛔ 不猜）。 */
const unresolvedOriginalCourses = ref<string[]>([])

/**
 * 把「原始课表」写入 `currentSchedule`（开页执行一次）。
 *
 * ## 匹配口径（重要）
 *
 * 原始课表里**同一门课可能占多个格位**（例：`数据结构与算法`
 * 既在周一 3-4 又在周三 5-6）。因此不能"一个格位挑一个教学班"——
 * 那会给同一课程号挑出**两个不同教学班**，课表就画错了。
 *
 * 正确做法：先按**课程名**把格位合并成"这门课要占哪些时段"，
 * 再在 `offerings` 里挑**覆盖这些时段最多**的那个教学班：
 *
 * ```text
 * 课程名 → 需要的时段集合 {(weekday, start, end), …}
 *   ↓ 对每个同名教学班计算覆盖数（meeting 与所需时段重叠）
 *   ↓ 取覆盖数最大、且课程号唯一者
 * 该课程号的一个真实教学班（原样使用，⛔ 一个字段都不改）
 * ```
 *
 * ⛔ 不做课程号推断、⛔ 不做等价性判断；同名课程号不唯一时**不猜**，交回用户。
 *
 * ⚠️ 用**就地追加**而不是 `invalidateManualAttestation()`：
 *   后者会生成新 form 对象，触发 `resultInvalidatingInputs` 侦听器把结果清空。
 */
function loadOriginalSchedule(): void {
  if (originalScheduleLoaded.value) return
  if (form.value.currentSchedule.length > 0) return
  if (offerings.value.length === 0) return

  // ① 按课程名合并格位 → 「这门课需要占哪些时段」
  const wanted = new Map<string, { weekday: number; start: number; end: number }[]>()
  for (const block of DEMO_RECOGNIZED_BLOCKS) {
    const list = wanted.get(block.courseName) ?? []
    list.push({ weekday: block.weekday, start: block.startSection, end: block.endSection })
    wanted.set(block.courseName, list)
  }

  const picked: CourseOffering[] = []
  const unresolved: string[] = []

  for (const [courseName, slots] of wanted) {
    const sameName = offerings.value.filter((item) => item.course_name === courseName)
    if (sameName.length === 0) {
      unresolved.push(courseName)
      continue
    }

    /** 该教学班的 meetings 覆盖了几个所需时段。 */
    const coverage = (offering: CourseOffering): number =>
      slots.filter((slot) =>
        offering.meetings.some(
          (meeting) =>
            meeting.weekday === slot.weekday &&
            !(meeting.end_section < slot.start || meeting.start_section > slot.end),
        ),
      ).length

    const scored = sameName
      .map((offering) => ({ offering, score: coverage(offering) }))
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)

    if (scored.length === 0) {
      // 该课名在本学期教学班库中存在，但没有任何班落在图上的时段 ⇒ ⛔ 不猜
      unresolved.push(courseName)
      continue
    }

    const best = scored[0].offering
    // 同一课程号只保留一个教学班（同一门课的多个班不可同时选）
    if (picked.some((item) => item.course_id === best.course_id)) continue
    picked.push(best)
  }

  originalScheduleLoaded.value = true
  unresolvedOriginalCourses.value = unresolved
  if (picked.length === 0) return
  form.value.currentSchedule = [...form.value.currentSchedule, ...picked]
}

async function chooseTranscript(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  error.value = ''
  result.value = null
  confirmedPlanInputKeys.value = []

  if (!file) {
    transcript.value = null
    // 清空输入 ⇒ 已修课程也随之清空（⛔ 不让上一次的成绩单残留影响未来路径）
    completedCourses.value = []
    completedStatus.value = 'idle'
    return
  }

  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  if (isPdf) {
    transcript.value = file
    // 切到 PDF 路径：清掉图片侧状态，避免两种输入同时存在
    await transcriptImageImport.value?.acceptFile(null)
    // ✅ 读取**已修课程明细**（未来路径扣除已满足课程的唯一依据）。
    //    ⚠️ 与 `/plan` 请求并行，⛔ 不阻塞生成；失败时如实降级（不排期）。
    void loadCompletedCoursesFor(file)
    return
  }

  const isImage = ACCEPTED_IMAGE_TYPES.split(',').includes(file.type)
  if (!isImage) {
    transcript.value = null
    error.value = '请上传 PDF 或 PNG / JPEG / WebP 格式的成绩单。'
    return
  }

  // 图片路径：清掉 PDF 状态，交给图片组件走它唯一的识别链路
  transcript.value = null
  // 图片路径下的已修课程 = 用户**逐条确认**的记录（⛔ 不用 OCR 原始候选）
  completedCourses.value = []
  completedStatus.value = 'idle'
  await transcriptImageImport.value?.acceptFile(file)
}

/** 当前课表变更的唯一入口：改课表 + 作废既有手工确认（⛔ 旧确认不得覆盖新数据）。 */
function updateSchedule(next: CourseOffering[]): void {
  form.value = invalidateManualAttestation(form.value, next).form
}

function updateEntries(entries: ManualScheduleEntry[]): void {
  form.value = invalidateManualAttestation(form.value, undefined, entries).form
}

function addManual(payload: { offering: CourseOffering; entries: ManualScheduleEntry[] }): void {
  form.value = invalidateManualAttestation(
    form.value,
    [...form.value.currentSchedule, payload.offering],
    payload.entries,
  ).form
}

/**
 * 把**已有**的教学班搜索定位到图片识别中未识别的课程。
 * ⚠️ 复用 `CurrentScheduleEditor` 暴露的 `focusSearch`，⛔ 不新建第二套搜索逻辑。
 */
const scheduleEditor = ref<{ focusSearch: (keyword: string) => void } | null>(null)

function focusOfferingSearch(keyword: string): void {
  scheduleEditor.value?.focusSearch(keyword)
}

function removeOffering(offering: CourseOffering): void {
  const next = removeCurrentScheduleOffering(form.value.currentSchedule, offering)
  form.value = invalidateManualAttestation(form.value, next).form
}

/** 清空当前课表（由 `CurrentScheduleList` / 编辑器的二次确认后触发，复用既有作废逻辑）。 */
function clearSchedule(): void {
  form.value = invalidateManualAttestation(form.value, []).form
}

/* 意向课程（课程级，写入 Preference.preferredCourses；重复课程不会重复加入） */
const preferredCourses = computed(() => form.value.preference.preferredCourses)

function addPreferred(courseId: string): void {
  form.value = {
    ...form.value,
    preference: {
      ...form.value.preference,
      preferredCourses: addPreferredCourse(form.value.preference.preferredCourses, courseId),
    },
  }
}

function removePreferred(courseId: string): void {
  form.value = {
    ...form.value,
    preference: {
      ...form.value.preference,
      preferredCourses: removePreferredCourse(form.value.preference.preferredCourses, courseId),
    },
  }
}

async function submit(): Promise<void> {
  const hasPdf = transcript.value !== null
  const hasConfirmed = confirmedImageCourses.value.length > 0
  // ⚠️ 成绩单输入二选一（后端强制）。这里先给出可操作的前端提示。
  if (hasPdf && hasConfirmed) {
    error.value =
      '请只提供一种成绩单输入：上传 PDF，或使用图片识别的确认结果（二者不能同时提交）。'
    return
  }
  if (!hasPdf && !hasConfirmed) {
    error.value = '请先上传成绩单 PDF，或上传成绩单图片并确认识别结果。'
    return
  }
  if (manualCount.value > 0 && !form.value.manualAttestation.attested) {
    error.value = '手工录入的当前课表需要你先明确确认信息由本人提供。'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const request = buildRealPlanRequest(form.value)
    result.value = await runCaseADemo({
      // ⛔ 两条入口互斥：只填其中一条。
      file: hasPdf ? transcript.value : null,
      confirmedCourses: hasPdf ? null : confirmedImageCourses.value,
      semester: request.semester,
      currentSchedule: request.current_schedule,
      manualScheduleAttested: form.value.manualAttestation.attested,
      preference: request.preference,
    })
  } catch (cause) {
    error.value = cause instanceof CaseAApiError && cause.status !== null && cause.status >= 500 ? '方案暂时无法生成，请稍后重试。' : studentText(cause instanceof Error ? cause.message : '', '方案生成失败，请检查输入后重试。')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // 专业列表必须先于培养方案加载：它是 major_id 的唯一来源。
  // 两者都 await，使错误态在挂载后即确定（不依赖 watcher 的刷新时机）。
  await loadMajors()
  await loadStudyPlanFor(form.value.studentContext.targetMajor)
  await loadOfferings()
})
</script>

<template>
  <div class="page case-a-page" data-testid="case-a-demo-view">
    <main class="page__main">
      <section class="case-a-hero">
        <div>
          <p class="case-a-eyebrow">AI 学业路径重构 Agent</p>
          <h1>学航·转衔</h1>
          <p class="case-a-subtitle">面向转专业学生的学业路径重构</p>
          <p class="case-a-lead">
            上传成绩单后，系统将结合目标专业培养方案、教学班数据和你的当前课表，
            生成补修与排课建议。
          </p>
        </div>
        <!--
          ⚠️ 来源标签按**真实加载状态**渲染（R1 修复）：
          此前无条件写死「真实教学班数据」，在运行时未配置（503）或加载失败时
          会与同一屏的报错自相矛盾。现在只有 `success` 才用强调样式。
        -->
        <div class="case-a-tags" aria-label="数据与计算范围">
          <span
            class="tag"
            :class="offeringsTagEmphasized ? 'tag--source-real' : ''"
            data-testid="case-a-offerings-tag"
          >
            {{ offeringsTagLabel }}
          </span>
          <span class="tag">南校园 + 深圳校区</span>

        </div>
      </section>

      <!--
        转专业方向（本轮扩展：在原有两个专业下拉之下，各加一个**培养方案年级**）
        ⚠️ 两个年级字段**各自独立保存**，⛔ 不共用；
        ⚠️ 与「转入学期」是不同概念，⛔ 本卡片不展示也不改动转入学期；
        ⚠️ 本轮**只有 2025 级有数据支持**，⛔ 2026 级不作为可选项（不假装数据存在）。
      -->
      <SectionCard
        :mock="false"
        title="转专业方向"
        subtitle="请选择转出与转入专业，以及对应的培养方案年级。"
      >
        <div class="case-a-majors" data-testid="case-a-majors">
          <label class="case-a-majors__field">
            <span class="case-a-majors__label">原专业</span>
            <select
              class="case-a-majors__select"
              data-testid="case-a-origin-major"
              :value="form.studentContext.originMajor"
              @change="onMajorChange('originMajor', $event)"
            >
              <option
                v-for="major in majorChoices"
                :key="major.value"
                :value="major.value"
                :disabled="isMajorDisabled('originMajor', major.value)"
              >
                {{ major.label }}
              </option>
            </select>
          </label>

          <label class="case-a-majors__field">
            <span class="case-a-majors__label">目标专业</span>
            <select
              class="case-a-majors__select"
              data-testid="case-a-target-major"
              :value="form.studentContext.targetMajor"
              @change="onMajorChange('targetMajor', $event)"
            >
              <option
                v-for="major in majorChoices"
                :key="major.value"
                :value="major.value"
                :disabled="isMajorDisabled('targetMajor', major.value)"
              >
                {{ major.label }}
              </option>
            </select>
          </label>

          <!-- 两个年级字段分别独立保存 -->
          <label class="case-a-majors__field">
            <span class="case-a-majors__label">原专业培养方案年级</span>
            <select
              class="case-a-majors__select"
              data-testid="case-a-origin-plan-year"
              :value="form.studentContext.originPlanYear"
              @change="onPlanYearChange('originPlanYear', $event)"
            >
              <option
                v-for="year in PLAN_YEAR_CHOICES"
                :key="year"
                :value="year"
                :disabled="isPlanYearDisabled(year)"
              >
                {{ year }}
              </option>
            </select>
          </label>

          <label class="case-a-majors__field">
            <span class="case-a-majors__label">目标专业培养方案年级</span>
            <select
              class="case-a-majors__select"
              data-testid="case-a-target-plan-year"
              :value="form.studentContext.targetPlanYear"
              @change="onPlanYearChange('targetPlanYear', $event)"
            >
              <option
                v-for="year in PLAN_YEAR_CHOICES"
                :key="year"
                :value="year"
                :disabled="isPlanYearDisabled(year)"
              >
                {{ year }}
              </option>
            </select>
          </label>
        </div>

        <p class="case-a-majors__hint" data-testid="case-a-majors-scope">
          专业选项来自后端专业注册表（当前 {{ majorChoices.length }} 个）；
          <strong>原专业与目标专业不能相同</strong>。
          ⛔ 演示或离线选项不参与匹配。
        </p>
        <p
          v-if="sameMajorSelected"
          class="case-a-majors__warn"
          data-testid="case-a-majors-same-warning"
          role="alert"
        >
          ⚠️ 原专业与目标专业当前相同，请改选其中一个（被对方占用的选项不可选）。
        </p>

        <!-- 当前转专业类型（仅展示用归类） -->
        <div class="case-a-transfer-type" data-testid="case-a-transfer-type">
          <div class="case-a-transfer-type__head">
            <h4 class="case-a-transfer-type__title">当前转专业类型</h4>
            <span class="case-a-transfer-type__badge" data-testid="case-a-transfer-type-label">
              {{ transferType }}
            </span>
          </div>
          <p class="case-a-transfer-type__path" data-testid="case-a-plan-year-scope">
            {{ planYearScopeLabel }}
          </p>
          <p class="case-a-transfer-type__pair" data-testid="case-a-plan-year-pair">
            {{ planYearPairLabel }}
          </p>
          <p class="case-a-transfer-type__note" data-testid="case-a-plan-year-note">
            当前演示数据仅支持 <strong>2025 级</strong> 对应的培养方案。
            其他年级（{{ PENDING_PLAN_YEARS.join('、') }}）需要补充相应数据后才能进行真实对比。
          </p>
          <p
            v-if="!planYearsSupported"
            class="case-a-majors__warn"
            data-testid="case-a-plan-year-unsupported"
            role="alert"
          >
            ⚠️ 所选年级缺少培养方案数据。实际规划仍使用 <strong>2025 级</strong> 样本，
            ⛔ 不会按所选年级生成结果。
          </p>
        </div>

        <!--
          ⚠️ 专业选择链：MajorSelector（上方目标专业下拉）
             → 加载 StudyPlan（本面板）
             → 匹配（下方「补修缺口分析」，由后端在 /plan 中执行）
          ⛔ 面板只呈现培养方案**要求**，不判定谁该补修。
        -->
        <div class="case-a-study-plan-wrap">
          <h4 class="case-a-study-plan-title">目标专业培养方案</h4>
          <p class="case-a-secondary" data-testid="case-a-majors-source">
            <template v-if="majorsFromBackend">
              专业选项来自后端专业注册表（{{ majors.length }} 个专业）。
            </template>
            <template v-else>
              后端专业注册表不可用，当前仅显示离线演示选项；⛔ 演示选项不参与匹配。
            </template>
          </p>
          <StudyPlanPanel
            :plan="studyPlan"
            :loading="studyPlanStatus === 'loading'"
            :error="studyPlanError"
            :major-name="form.studentContext.targetMajor"
            :elective-progress="result?.elective_progress ?? []"
          />
        </div>
      </SectionCard>

      <!--
        ⚠️ **统一成绩单入口**（Phase 6，任务 1）：
           原来 PDF 与图片是两个并列入口，用户要在两处各选一次。
           现在只有**一个**「上传成绩单」控件，按文件类型自动分流：
             · PDF   → 原流程（后端 `transcript_pdf_base64`）
             · 图片  → 本机 OCR → 确认页（后端 `confirmed_completed_courses`）
           ⛔ 后端接口未改；⛔ 匹配逻辑未改。
      -->
      <SectionCard
        :mock="false"
        title="第一步：上传成绩单"
        subtitle="支持 PDF 成绩单，或成绩单图片（图片在本机识别，需你确认识别结果）。"
      >
        <div class="case-a-upload">
          <label class="case-a-file">
            <span>选择成绩单文件</span>
            <input
              ref="transcriptFileInput"
              data-testid="case-a-pdf"
              type="file"
              :accept="`application/pdf,.pdf,${ACCEPTED_IMAGE_TYPES}`"
              @change="chooseTranscript"
            />
          </label>
          <p v-if="transcript" class="case-a-success" data-testid="case-a-transcript-pdf-selected">
            ✓ 已选择 PDF：{{ transcript.name }}
          </p>
          <p
            v-else-if="confirmedImageCourses.length === 0"
            class="case-a-secondary"
            data-testid="case-a-transcript-hint"
          >
            选择 PDF 将直接读取成绩单；选择图片会先在本机识别，再由你逐条确认。
          </p>
        </div>

        <!-- 图片识别结果与确认页：只在选择了图片时展开 -->
        <TranscriptImageImport
          ref="transcriptImageImport"
          @update:confirmed="confirmedImageCourses = $event"
        />

        <p
          v-if="confirmedImageCourses.length > 0 && !transcript"
          class="case-a-secondary"
          data-testid="case-a-transcript-image-confirmed-count"
        >
          已确认为成绩单课程 <strong>{{ confirmedImageCourses.length }}</strong> 门，
          将用于生成方案。
        </p>
      </SectionCard>

      <SectionCard
        :mock="false"
        title="第二步：填写当前课表"
        :subtitle="scheduleSubtitle"
      >
        <div class="case-a-schedule">
          <!--
            ⚠️ 布局调整（最终展示优化）：编辑器的「当前课表」区块在此隐藏
               （`show-current-schedule=false`），改由下方在「图片导入 + 识别结果」之后渲染，
               让「识别 → 用户确认 → 课表实时更新 → 剩余未识别」形成可感知闭环。
               ⛔ 不改数据流：`currentSchedule` 仍是唯一数据源，事件仍回到既有处理函数。
          -->
          <CurrentScheduleEditor
            ref="scheduleEditor"
            :offerings="offerings"
            :current-schedule="form.currentSchedule"
            :semester="form.semester"
            :attestation-notice="attestationNotice"
            :show-current-schedule="false"
            @update:current-schedule="updateSchedule"
            @remove="removeOffering"
            @clear="clearSchedule"
          />

          <!-- 候选只进入待匹配列表；搜索并选择教学班后才加入当前课表。 -->
          <TimetableImageImport
            :semester="form.semester"
            :selected="form.currentSchedule"
            @search="focusOfferingSearch"
          >
            <!--
              已确认加入的当前课表（实时状态）。
              ⚠️ 插在「识别结果」与「未识别/搜索教学班」之间，让用户确认后立即可见。
            -->
            <template #between>
              <!-- 已确认加入的当前课表（实时状态）——只含 data_source=real 的真实教学班 -->
              <CurrentScheduleList
                :current-schedule="form.currentSchedule"
                :attestation-notice="attestationNotice"
                :unresolved-course-names="unresolvedOriginalCourses"
                @remove="removeOffering"
                @clear="clearSchedule"
              />
            </template>
          </TimetableImageImport>

          <div class="case-a-manual">
            <button
              class="case-a-link-button"
              type="button"
              data-testid="case-a-manual-toggle"
              @click="manualOpen = !manualOpen"
            >
              {{ manualOpen ? '收起手工添加' : '找不到你的教学班？手工添加课程' }}
            </button>

            <div v-if="manualOpen" data-testid="case-a-manual-form">
              <ManualScheduleForm
                :entries="form.manualScheduleEntries"
                :selected="form.currentSchedule"
                :semester="form.semester"
                :current-semester="form.semester"
                provenance-label="本人填写，未经学校系统核验"
                :attested="form.manualAttestation.attested"
                :manual-count="manualCount"
                :attestation-invalidated="form.manualAttestation.invalidated"
                @update:entries="updateEntries"
                @add-row="form.manualScheduleEntries = addManualScheduleEntry(form.manualScheduleEntries, $event)"
                @add-confirmed="addManual"
                @remove="removeOffering"
                @update:attested="form = applyManualAttestation(form, $event)"
              />
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard :mock="false" title="第三步：告诉我你的选课需求" subtitle="这些信息会用于本学期排课与补修安排，不会改变学校规则。">
        <div class="case-a-needs">
          <IntentCourseSearch
            :offerings="offerings"
            :selected-course-ids="preferredCourses"
            @add="addPreferred"
            @remove="removePreferred"
          />
          <PreferenceForm
            :form="form"
            :preferred-courses="preferredCourses"
            @update:form="form = $event"
            @remove-preferred="removePreferred"
          />
        </div>
      </SectionCard>

      <div class="case-a-explainer" data-testid="case-a-planning-explainer">
        <h2 class="case-a-explainer__title">AI 如何帮助你规划</h2>
        <ul class="case-a-explainer__list">
          <li v-for="step in PLANNING_STEPS" :key="step">✓ {{ step }}</li>
        </ul>
        <p class="case-a-explainer__note">系统会给出清晰的课程建议，需要你确认的内容会单独标出。</p>
      </div>

      <div class="case-a-submit-wrap">
        <button class="button case-a-submit" type="button" :disabled="loading" data-testid="case-a-submit" @click="submit">
          {{ loading ? '正在规划你的学业路径…' : '生成并优化我的转专业学业方案' }}
        </button>
        <p>系统仅提供规划建议，不执行实际选课操作。</p>
      </div>
      <p v-if="error" class="state state--error" role="alert">{{ error }}</p>

      <!--
        ⚠️ 补修确认流程（P1）：提示学生本轮有若干条需要**人工确认**，
           并说明确认会带来什么变化（→ 已满足 → 从推荐消失），
           以及确认**不会**重新请求规划服务。⛔ 不伪造"缺失"。
      -->
      <p
        v-if="result && confirmationMatches.length > 0"
        class="case-a-confirm-notice"
        data-testid="case-a-confirm-notice"
      >
        本次匹配有 <strong>{{ confirmationMatches.length }}</strong> 条培养要求需要你人工确认：
        请核对它们在「补修缺口分析」中给出的判定理由，判断能否用成绩单课程抵扣。
        确认后该要求会转为<strong>已满足</strong>并从推荐中移除；
        ⛔ 确认只更新本页状态，不会重新请求规划服务。
      </p>
      <p
        v-else-if="result && makeupAnalysis.length > 0"
        class="case-a-confirm-done"
        data-testid="case-a-confirm-done"
      >
        ✓ 本次匹配没有待确认项。
      </p>

      <template v-if="result">
        <!--
          ⚠️ 数据来源如实标注（本轮）。
             「补修缺口分析」的三状态与推荐候选**全部来自后端真实匹配结果**，
             不再是前端演示配置。这里把该事实明确写在页面上，便于答辩时核对。
        -->
        <p class="case-a-source-note" data-testid="case-a-analysis-source">
          补修分析与推荐基于<strong>学校培养方案匹配结果</strong>生成：
          {{ result.makeup_tasks?.length ?? 0 }} 条培养要求判定，每条均附带判定理由与可审计依据
          （培养方案表格行号 + 成绩单行号）。
        </p>

        <SectionCard :mock="false" title="成绩单识别结果" :badge-count="result.transcript.record_count">
          <p>
            已识别 {{ result.transcript.record_count }} 门已修课程，覆盖 {{ result.transcript.term_count }} 个学期。
            需要你核对的课程已列在下方「补修缺口分析」中。
          </p>
        </SectionCard>

        <!--
          ⚠️ 信息架构调整（本次）：
            原来「补修缺口分析」是一张后台式大表格，与「课程建议与确认」功能重复
            （同一门课两处出现、学生不知道该在哪操作）。
            现在**合并为一个卡片式入口**：一门课程一张卡片，
            卡片内含「课程识别 / 为什么需要确认 / 纳入后续规划」。
            ⛔ 不再有重复的补修课程列表；⛔ 不改任何数据结构与接口。
        -->
        <!--
          ⚠️ 信息架构：拆成三个**独立阶段**，全部位于课表之前。
            ① 补修缺口分析 —— 我转专业后哪些课需要补修 / 哪些历史课能转换
            ② 推荐选课     —— 根据剩余培养要求，本学期应该学哪些课程
            ③ 生成后的规划课表 —— 当前课表 + 本学期方案课程，实时合并
          ⛔ 两者都需要用户操作，但含义完全不同，不再混在一个模块里。
        -->
        <SectionCard
          :mock="false"
          title="补修缺口分析"
          subtitle="系统根据培养方案和成绩单，判断哪些课程可能需要补修、哪些历史课程可以转换。"
          :badge-count="result.makeup_tasks.length"
        >
          <MakeupGapAnalysis
            :items="makeupAnalysis"
            :confirmed-courses="confirmedMakeupCourses"
            @confirm="confirmMakeupConversion"
            @undo="undoMakeupConversion"
          />
        </SectionCard>

        <!--
          ⚠️ **推荐选课（合并）**（Phase 6，任务 2）：
             原来拆成「必须补修」与「专业选修」两张卡，用户要来回看两处。
             现在合并为**一个**列表，内部用标签 + 颜色区分来源：
               A 必须补修 = 后端 `missing`
               B 建议选修 = 培养方案 `elective_pool`
             ⛔ 推荐算法、来源、过滤条件**一行未改**；只是展示层合并。
        -->
        <SectionCard
          :mock="false"
          title="推荐选课"
          subtitle="按来源分为两类：A 必须补修（培养要求缺口）与 B 建议选修（专业选修池）。"
          :badge-count="mergedRecommendations.length"
        >
          <RecommendedCourses
            :courses="mergedRecommendations"
            :selected-courses="selectedSemesterCourses"
            :reason-for="reasonFor"
            :tag-for="recommendationTagOf"
            @confirm="confirmSemesterCourses"
            @remove="removeSemesterCourse"
          />
        </SectionCard>

        <!--
          ⚠️ 顺序调整：先确认输入，再看规划结果。
             用户勾选的课程（`confirmedPlanInputKeys`）会传给本区域读取，
             用于展示「已选择课程将用于后续规划」。
        -->
        <SectionCard :mock="false" :title="'生成后的规划课表'" subtitle="根据培养要求、课程安排和你的选课偏好生成。最终选课结果请以学校教务系统为准。">
          <p
            v-if="selectedSemesterCourses.length > 0"
            class="case-a-plan-linkage"
            data-testid="case-a-plan-linkage"
          >
            已加入本学期方案 <strong>{{ selectedSemesterCourses.length }}</strong> 门课程，
            课表已实时更新（⛔ 不需要重新生成方案）。
          </p>
          <WeeklyScheduleView
            :plan-result="result.plan_result"
            :offerings="result.course_offerings"
            :semester="form.semester"
            :current-schedule="form.currentSchedule"
            :selected-semester-courses="selectedSemesterCourses"
            :makeup-tasks="result.makeup_tasks"
            :preferred-courses="preferredCourses"
          />
        </SectionCard>

        <!--
          ⛔ Phase 7 任务 1：**已删除**「调整建议」展示模块。
             原因：当前版本**没有实现**教学班调整 / 冲突修复建议
             （实测 `plan_result.changes` 恒为空 ⇒ 该区块只会显示"本次未返回调整建议"），
             留着会让评委以为存在未实现的能力。
             ⚠️ 只删前端展示：⛔ 后端能力（`plan_result.changes` / Path Repair）一行未动，
             也⛔ 不删 `PendingAdjustments.vue` 组件本身（仍可被其它面板复用）。
        -->

        <!--
          未来学习路径规划（Phase 7 任务 2 · Review 修正）：
          ⚠️ 由**培养方案推荐学期 + 匹配结果 + 成绩单已修课程**在前端派生
             （`deriveFutureRoadmap`）。
          ⛔ 不是未来选课预测：不含教师 / 时间 / 地点 / 教学班。
          ⛔ 已满足课程**禁止**进入本区块（Review 修正的业务规则）。
        -->
        <SectionCard
          :mock="false"
          title="未来学习路径规划（基于培养方案）"
          subtitle="根据目标专业培养要求和当前学习状态生成建议修读顺序。不代表未来实际开课安排，不预测教师、时间和教学班。"
        >
          <!-- 已修课程读取失败 ⇒ ⛔ 不排期，如实说明（否则会把已修课排进未来） -->
          <p
            v-if="completedStatus === 'error'"
            class="case-a-secondary"
            data-testid="case-a-roadmap-completed-unavailable"
          >
            ⛔ 未能读取成绩单中的<strong>已修课程明细</strong>，因此无法判断哪些培养要求已满足。
            为避免把已修课程重复排进未来学期，本区块<strong>暂不生成排期</strong>。
          </p>

          <p
            v-else-if="completedStatus === 'loading'"
            class="case-a-secondary"
            data-testid="case-a-roadmap-completed-loading"
          >
            正在读取成绩单中的已修课程…
          </p>

          <template v-else-if="futureRoadmapAnalysed">
            <!--
              ⚠️ 课程完成度五状态（Task 3）。
                 数字全部来自 `deriveFutureRoadmap` 的状态分类，⛔ 组件内不再判定。
                 ⚠️ 「进行中」与「已完成」**必须分开**：正在修 ≠ 已经修完。
            -->
            <div class="case-a-roadmap-states" data-testid="case-a-roadmap-states">
              <span class="case-a-roadmap-state case-a-roadmap-state--completed">
                已完成 <strong>{{ stateCount('completed') }}</strong> 门
              </span>
              <span class="case-a-roadmap-state case-a-roadmap-state--in-progress">
                进行中 <strong>{{ stateCount('in_progress') }}</strong> 门
              </span>
              <span class="case-a-roadmap-state case-a-roadmap-state--missing">
                明确缺口 <strong>{{ stateCount('missing') }}</strong> 门
              </span>
              <span class="case-a-roadmap-state case-a-roadmap-state--confirm">
                待确认 <strong>{{ stateCount('need_confirmation') }}</strong> 门
              </span>
              <span class="case-a-roadmap-state case-a-roadmap-state--coverage">
                培养要求待覆盖 <strong>{{ stateCount('pending_coverage') }}</strong> 门
              </span>
            </div>

            <!--
              ⚠️ 语义收敛（本轮）：以下说明必须逐字展示，避免用户把"待覆盖"误解为
                 "系统已判断我缺这些课"。
            -->
            <p class="case-a-secondary" data-testid="case-a-roadmap-coverage-explain">
              <strong>培养要求待覆盖</strong>：目标培养方案要求存在，
              但当前成绩单 / 课表 / 匹配结果<strong>不足以判断是否需要补修</strong>。
              ⛔ 这不代表系统已判断你缺这些课。
            </p>
            <p class="case-a-secondary" data-testid="case-a-roadmap-term-scope">
              未来规划从 <strong>{{ termLabel(futureRoadmap.startsFromTerm ?? '') }}</strong> 起
              （当前学期 {{ termLabel(futureRoadmap.currentTerm) }} 已在修课程按「进行中」处理，
              ⛔ 不重复排入未来学期）。
            </p>

            <!--
              毕业要求闭环摘要（Task 2）。
              ⚠️ 「专业选修」按**学分**给（培养方案给的是学分下限）；
                 「专业必修 / 公共必修」按**门数 + 学分**给。
              ⛔ 数字全部来自后端已有字段，前端只做分组统计，⛔ 不计算毕业缺口。
            -->
            <div class="case-a-roadmap-summary" data-testid="case-a-roadmap-summary">
              <p class="case-a-roadmap-summary__title">培养完成情况（依据后端培养方案与匹配结果）</p>
              <ul class="case-a-roadmap-summary__list">
                <li
                  v-for="category in futureRoadmap.categories"
                  :key="category.key"
                  :data-testid="`case-a-roadmap-category-${category.key}`"
                >
                  <span class="case-a-roadmap-summary__label">{{ category.label }}</span>
                  <span v-if="category.key === 'elective'">
                    已完成
                    <strong>{{ formatCredit(category.completedCredit) }}</strong> 学分 /
                    要求 <strong>{{ formatCredit(category.requiredCredit) }}</strong> 学分
                    <span v-if="category.requiredCredit === null" class="case-a-secondary">
                      （后端未提供选修学分要求）
                    </span>
                  </span>
                  <span v-else>
                    已完成 <strong>{{ category.completedCount }}</strong> /
                    总要求 <strong>{{ category.totalCount }}</strong> 门
                    <span class="case-a-secondary">
                      （学分 {{ formatCredit(category.completedCredit) }} /
                      {{ formatCredit(category.requiredCredit) }}）
                    </span>
                  </span>
                </li>
                <li data-testid="case-a-roadmap-graduation">
                  <span class="case-a-roadmap-summary__label">毕业设计</span>
                  <span v-if="hasGraduationProject">待安排（已列入下方学期路径）</span>
                  <span v-else class="case-a-secondary">培养方案未列出毕业设计</span>
                </li>
                <li data-testid="case-a-roadmap-expected-term">
                  <span class="case-a-roadmap-summary__label">预计培养要求完成时间</span>
                  <span v-if="futureRoadmap.expectedCompletionTerm">
                    <strong>{{ termLabel(futureRoadmap.expectedCompletionTerm) }}</strong>
                    <span class="case-a-secondary">
                      （按当前培养要求排完的学期估算，⛔ 不是毕业时间预测、
                      ⛔ 不代表学校实际开课安排）
                    </span>
                  </span>
                  <span v-else class="case-a-secondary">无可排期的培养要求</span>
                </li>
              </ul>
              <p class="case-a-secondary" data-testid="case-a-roadmap-reconciliation">
                学分对账（仅内部一致性核对，⛔ 不代表学校认可的毕业结论）：
                必修总量 {{ formatCredit(futureRoadmap.reconciliation.requiredTotalCredit) }} ·
                已完成 {{ formatCredit(futureRoadmap.reconciliation.completedCredit) }} ·
                进行中 {{ formatCredit(futureRoadmap.reconciliation.inProgressCredit) }} ·
                明确缺口 {{ formatCredit(futureRoadmap.reconciliation.missingCredit) }} ·
                待确认 {{ formatCredit(futureRoadmap.reconciliation.needConfirmationCredit) }} ·
                培养要求待覆盖 {{ formatCredit(futureRoadmap.reconciliation.pendingCoverageCredit) }}
                <template v-if="futureRoadmap.reconciliation.balanced">✔ 对账一致</template>
                <template v-else-if="futureRoadmap.reconciliation.note">
                  · {{ futureRoadmap.reconciliation.note }}
                </template>
                <br />
                其中本轮已排入未来学期：{{ formatCredit(futureRoadmap.reconciliation.plannedCredit) }} 学分
                （明确缺口 + 培养要求待覆盖；⛔ 待确认不排期）。
              </p>
              <p class="case-a-secondary" data-testid="case-a-roadmap-ordering-note">
                {{ futureRoadmap.orderingNote }}
              </p>
              <p class="case-a-secondary" data-testid="case-a-roadmap-credit-note">
                {{ futureRoadmap.creditNote }}
              </p>
            </div>

            <FutureRoadmapView v-if="futureRoadmapReady" :roadmap="futureRoadmap" />

            <p
              v-else
              class="case-a-secondary"
              data-testid="case-a-roadmap-no-term"
            >
              当前没有可排入未来学期的培养要求（未完成的条目都在「待确认」或「待判定」中，
              需先确认课程认定结果）。
            </p>

            <!--
              ⛔ 规则 2：待人工确认的课程**标注但不安排学期**。
                 这些课既没有成绩单"已通过"证据，后端也没判定为缺失，
                 因此不能替学生排进任何一个学期。
            -->
            <div
              v-if="futureRoadmap.needConfirmationCourses.length > 0"
              class="case-a-roadmap-pending"
              data-testid="case-a-roadmap-need-confirmation"
            >
              <p class="case-a-roadmap-pending__head">
                待人工确认 {{ futureRoadmap.needConfirmationCourses.length }} 门
                （⛔ 暂不安排学期，需先确认课程认定结果）
              </p>
              <ul class="case-a-roadmap-pending__list">
                <li
                  v-for="course in futureRoadmap.needConfirmationCourses"
                  :key="course.course_id"
                >
                  {{ course.course_name }}
                  <span v-if="course.credit !== null">· {{ course.credit }} 学分</span>
                </li>
              </ul>
            </div>

            <!--
              「培养要求待覆盖」：培养方案要求存在，但依据不足以判断是否需要补修。
              ⚠️ 这些课**已排入**下方学期路径（需按方案完成），
                 这里单独列出来是为了让"尚无依据"这件事**保持可见**。
            -->
            <div
              v-if="futureRoadmap.pendingCoverageCourses.length > 0"
              class="case-a-roadmap-pending case-a-roadmap-pending--coverage"
              data-testid="case-a-roadmap-pending-coverage"
            >
              <p class="case-a-roadmap-pending__head">
                培养要求待覆盖 {{ futureRoadmap.pendingCoverageCourses.length }} 门
              </p>
              <p class="case-a-roadmap-pending__note">
                目标培养方案要求存在，但当前成绩单 / 课表 / 匹配结果不足以判断是否需要补修。
                已按培养方案排入下方学期；⛔ 不代表系统已判断你缺这些课。
              </p>
              <ul class="case-a-roadmap-pending__list">
                <li
                  v-for="course in futureRoadmap.pendingCoverageCourses"
                  :key="course.course_id"
                >
                  {{ course.course_name }}
                  <span v-if="course.credit !== null">· {{ course.credit }} 学分</span>
                </li>
              </ul>
            </div>
          </template>

          <p v-else class="case-a-secondary" data-testid="case-a-roadmap-empty">
            暂无未来学期排期依据（未上传成绩单，或培养方案无可排期的培养要求）。
          </p>
        </SectionCard>

        <SectionCard :mock="false" title="本次规划依据">
          <ul class="case-a-planning-basis" data-testid="case-a-planning-basis">
            <li>✓ 我的成绩记录</li>
            <li>✓ 目标专业培养方案</li>
            <li>✓ 当前教学安排</li>
            <li>✓ 可选教学班信息</li>
          </ul>
          <p class="case-a-secondary">具体课程认定与选课结果请以学校教务系统为准。</p>
        </SectionCard>

        <SectionCard :mock="false" title="我的选课需求">
          <PreferencePanel :preference="result.preference" :course-name-by-id="resultCourseNames" />
        </SectionCard>
      </template>
    </main>
  </div>
</template>

<style scoped>
/* ---- 原专业 / 目标专业（本轮新增；两列栅格，沿用 Case A 既有配色与圆角） ---- */
/* 2×2 栅格：原专业/目标专业 一行，两个培养方案年级 一行（与验收稿一致） */
.case-a-majors {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 20px;
}

@media (max-width: 720px) {
  .case-a-majors {
    grid-template-columns: minmax(0, 1fr);
  }
}

.case-a-majors__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.case-a-majors__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.case-a-majors__select {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  font-size: 14px;
  color: var(--text);
}

.case-a-majors__hint {
  margin: 10px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

/* ---- 当前转专业类型（本轮新增；仅展示用归类） ---- */
.case-a-transfer-type {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.case-a-transfer-type__head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.case-a-transfer-type__title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.case-a-transfer-type__badge {
  padding: 2px 10px;
  border-radius: 999px;
  background: #eef2f7;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

.case-a-transfer-type__path {
  margin: 8px 0 0;
  font-size: 14px;
  color: var(--text);
}

.case-a-transfer-type__pair {
  margin: 4px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
}

.case-a-transfer-type__note {
  margin: 8px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.case-a-majors__warn {
  margin: 8px 0 0;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #f3d9a4;
  border-radius: var(--radius);
  padding: 8px 10px;
  font-size: 12px;
}

/* 数据来源如实标注（本轮）：说明补修分析来自后端真实匹配结果 */
/* 专业选择链：目标专业培养方案面板 */
.case-a-study-plan-wrap {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.case-a-study-plan-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.case-a-source-note,
.case-a-confirm-notice {
  margin: 0;
  padding: 10px 14px;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius);
  background: #f2f7ff;
  color: #1e293b;
  font-size: 13px;
  line-height: 1.7;
}

/* 补修确认提示：需要用户操作的项，用暖色与"来源说明"区分开 */
.case-a-confirm-notice {
  border-color: #f3d9a4;
  background: #fffbeb;
  color: #7c4a03;
}

.case-a-confirm-done {
  margin: 0;
  color: #15803d;
  font-size: 13px;
  font-weight: 600;
}

/* 推荐来源说明：让"必须补修"与"专业选修"在视觉上不可混淆 */
.case-a-recommend-scope {
  margin: 0 0 12px;
  padding: 8px 12px;
  border-left: 3px solid #3276df;
  border-radius: 6px;
  background: #f7f9fc;
  color: #33404f;
  font-size: 12px;
  line-height: 1.6;
}

.case-a-page {
  background: #f4f7fb;
}

.case-a-hero {
  display: flex;
  justify-content: space-between;
  gap: 28px;
  padding: 30px 32px;
  border: 1px solid #dbe6f5;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, #ffffff 0%, #eef5ff 100%);
  box-shadow: var(--shadow-sm);
}

.case-a-hero h1 {
  margin: 4px 0 6px;
  font-size: 34px;
  color: var(--text);
}

.case-a-eyebrow,
.case-a-subtitle,
.case-a-lead,
.case-a-secondary,
.case-a-empty,
.case-a-submit-wrap p,
.case-a-selected-item p,
.case-a-class-main p {
  margin: 0;
}

.case-a-eyebrow {
  color: #2f72dc;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
}

.case-a-subtitle {
  font-size: 18px;
  font-weight: 600;
  color: #334155;
}

.case-a-lead {
  max-width: 720px;
  margin-top: 12px;
  color: var(--text-muted);
  line-height: 1.7;
}

.case-a-tags {
  display: flex;
  align-content: flex-start;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 320px;
}

.case-a-upload,
.case-a-schedule {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #c7d2e0;
  border-radius: 8px;
  background: #f7f9fc;
}

/* 课程确认 → 规划课表的联动提示（只说明选择已传递，⛔ 不伪造算法结果） */
.case-a-plan-linkage {
  margin: 0 0 12px;
  padding: 8px 12px;
  border: 1px solid #c7d2e0;
  border-radius: 8px;
  background: #f7f9fc;
  color: #33404f;
  font-size: 13px;
}

.case-a-manual,
.case-a-selected {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.case-a-file {
  display: flex;
  align-items: center;
  gap: 14px;
  font-weight: 600;
}

.case-a-success {
  margin: 0;
  color: #15803d;
  font-weight: 600;
}

.case-a-secondary {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.case-a-search-panel {
  display: flex;
  align-items: end;
  gap: 14px;
  flex-wrap: wrap;
  padding: 14px;
  background: #f8fbff;
  border: 1px solid #d9e6f7;
  border-radius: var(--radius);
}

.case-a-search {
  display: flex;
  flex: 1 1 520px;
  flex-direction: column;
  gap: 8px;
  font-weight: 600;
}

.case-a-search .input-text {
  width: 100%;
  padding: 11px 14px;
  font-size: 14px;
}

.case-a-filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.case-a-filters label {
  display: flex;
  min-width: 130px;
  flex-direction: column;
  gap: 6px;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.case-a-filters .input-text {
  padding: 9px 30px 9px 10px;
}

.case-a-empty {
  padding: 14px 16px;
  color: var(--text-muted);
  background: #f8fafc;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
}

.case-a-course-groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.case-a-course-group {
  overflow: hidden;
  border: 1px solid #d8e3f0;
  border-radius: var(--radius);
  background: #fff;
}

.case-a-course-group__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 16px;
  background: #f6f9fd;
  border-bottom: 1px solid #e2e8f0;
}

.case-a-course-group__head h3 {
  margin: 0;
  color: #3276df;
  font-size: 17px;
  font-weight: 700;
}

.case-a-course-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.case-a-course-meta span {
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef4fd;
  color: #64748b;
  font-size: 11px;
}

.case-a-class-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 13px 16px;
  border-bottom: 1px solid #edf1f6;
}

.case-a-class-row:last-child {
  border-bottom: 0;
}

.case-a-class-row:hover {
  background: #fbfdff;
}

.case-a-class-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 6px;
}

.case-a-class-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.case-a-class-title strong {
  color: #1e293b;
}

.case-a-teacher {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.case-a-class-main p {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.case-a-class-extra {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 11px;
}

.case-a-selected {
  margin-top: 8px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.case-a-selected__head h3 {
  margin: 0;
  font-size: 16px;
}

.case-a-selected-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.case-a-selected-item p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.case-a-warning {
  color: #b45309 !important;
  font-weight: 600;
}

.case-a-remove {
  background: #64748b;
}

.case-a-link-button {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-weight: 600;
  cursor: pointer;
}

.case-a-submit-wrap {
  display: flex;
  align-items: center;
  gap: 16px;
}

.case-a-needs {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.case-a-explainer {
  padding: 20px 24px;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius-lg);
  background: #f2f7ff;
}

.case-a-explainer__title {
  margin: 0 0 12px;
  font-size: 17px;
  color: #1e40af;
}

.case-a-explainer__list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
  color: #1e293b;
  line-height: 1.7;
}

.case-a-explainer__note {
  margin: 12px 0 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
}

.case-a-submit {
  padding: 12px 24px;
  font-size: 15px;
}

.case-a-submit-wrap p {
  color: var(--text-muted);
  font-size: 12px;
}

/* 「待人工确认」/「待判定」清单（Phase 7）：⛔ 不安排学期，只如实列出 */
.case-a-roadmap-states {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.case-a-roadmap-state {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 12px;
}

.case-a-roadmap-state--completed {
  color: #166534;
  background: #f0fdf4;
  border-color: #bbf7d0;
}

.case-a-roadmap-state--in-progress {
  color: #1e40af;
  background: #eff6ff;
  border-color: #bfdbfe;
}

.case-a-roadmap-state--missing {
  color: #9a3412;
  background: #fff7ed;
  border-color: #fed7aa;
}

.case-a-roadmap-state--confirm,
.case-a-roadmap-state--coverage {
  color: #7c4a03;
  background: #fffbeb;
  border-color: #f3d9a4;
}

.case-a-roadmap-summary {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #f8fafc;
}

.case-a-roadmap-summary__title {
  margin: 0 0 8px;
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
}

.case-a-roadmap-summary__list {
  margin: 0 0 8px;
  padding-left: 0;
  list-style: none;
  color: #334155;
  font-size: 12px;
  line-height: 1.9;
}

.case-a-roadmap-summary__label {
  display: inline-block;
  min-width: 72px;
  color: #475569;
  font-weight: 700;
}

.case-a-roadmap-pending {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid #f3d9a4;
  border-radius: var(--radius-sm);
  background: #fffbeb;
}

.case-a-roadmap-pending--coverage {
  border-color: var(--border);
  background: #f8fafc;
}

.case-a-roadmap-pending__head {
  margin: 0 0 6px;
  color: #7c4a03;
  font-size: 12px;
  font-weight: 700;
}

.case-a-roadmap-pending__note {
  margin: 0 0 6px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.7;
}

.case-a-roadmap-pending--coverage .case-a-roadmap-pending__head {
  color: #475569;
}

.case-a-roadmap-pending__list {
  margin: 0;
  padding-left: 20px;
  color: #7c4a03;
  font-size: 12px;
  line-height: 1.8;
}

.case-a-roadmap-pending--coverage .case-a-roadmap-pending__list {
  color: #475569;
}

.case-a-planning-basis {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 10px 18px;
  margin: 0 0 12px;
  padding: 0;
  color: #334155;
  list-style: none;
}

@media (max-width: 760px) {
  .case-a-hero,
  .case-a-class-row,
  .case-a-selected-item,
  .case-a-submit-wrap {
    align-items: flex-start;
    flex-direction: column;
  }

  .case-a-search-panel {
    align-items: stretch;
  }

  .case-a-filters {
    width: 100%;
  }

  .case-a-filters label {
    flex: 1 1 130px;
  }

  .case-a-planning-basis {
    grid-template-columns: 1fr;
  }
}
</style>
