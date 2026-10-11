<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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
import { SAMPLE_MAJOR_OPTIONS } from '../config'
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
import FutureRoadmapView from './FutureRoadmapView.vue'
import IntentCourseSearch from './IntentCourseSearch.vue'
import MakeupTaskList from './MakeupTaskList.vue'
import ManualScheduleForm from './ManualScheduleForm.vue'
import PendingAdjustments from './PendingAdjustments.vue'
import PlanResultPanel from './PlanResultPanel.vue'
import PreferenceForm from './PreferenceForm.vue'
import PreferencePanel from './PreferencePanel.vue'
import SectionCard from './SectionCard.vue'
import WeeklyScheduleView from './WeeklyScheduleView.vue'

/** 说明卡的固定内容：⛔ 不承诺"系统会自动替换课程"，真实语义是"找候选 → 提建议 → 用户确认"。 */
const PLANNING_STEPS = [
  '检查当前课表的时间冲突',
  '为补修课程寻找本学期开设的教学班',
  '尝试安排你选择的意向课程',
  '发现冲突时寻找同课程其他教学班',
  '无法自动确认的问题会明确提示，由你决定',
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
const result = ref<CaseADemoResponse | null>(null)
const loading = ref(false)
const error = ref('')

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
  '教学班数据来自本次响应；该接口未返回来源字段，因此本页不对其真实性作认定。'
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
  for (const item of result.value?.course_offerings ?? []) map[item.course_id] = item.course_name
  return map
})

async function loadOfferings(): Promise<void> {
  error.value = ''
  offeringsStatus.value = 'loading'
  try {
    offerings.value = await loadCaseAOfferings(form.value.semester)
    // ⚠️ 空列表也是**成功**：接口确实答复了，只是该学期没有教学班。
    //    ⛔ 不得把"空"当成"未加载/不可用"。
    offeringsStatus.value = 'success'
  } catch (cause) {
    offerings.value = []
    if (cause instanceof CaseAApiError && cause.isNotConfigured) {
      offeringsStatus.value = 'not_configured'
      error.value = '教学班数据运行时尚未配置（后端返回 503），因此当前没有可展示的教学班。'
    } else {
      offeringsStatus.value = 'error'
      error.value = cause instanceof Error ? cause.message : '教学班数据暂时不可用。'
    }
  }
}

/**
 * 规划结果里的**教学班来源**（仅当后端 `provenance` 真的给出字段时才展示）。
 *
 * ⚠️ 这是"依据已有可信响应字段展示来源"的正例：
 *     `/plan` 响应带 `provenance.course_data`（实测值 `case-scoped:south+shenzhen`），
 *     因此这里**照实显示后端给的值**，⛔ 不自行改写、⛔ 不添加"真实/已核验"等认定。
 */
const planCourseDataSource = computed(() => {
  const value = result.value?.provenance?.course_data
  return typeof value === 'string' && value.trim() ? value.trim() : ''
})

/**
 * 结果区「教学班」条目的**说明**。
 *
 * ⚠️ 有 provenance 时如实带出来源；缺失时用中性表述（⛔ 不声称真实）。
 */
const planCourseDataLabel = computed(() =>
  planCourseDataSource.value ? '教学班（来源见下）' : '教学班',
)

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
      return `教学班数据运行时未配置，当前无可展示教学班；${scope}`
    case 'error':
      return `教学班数据加载失败，当前无可展示教学班；${scope}`
    default:
      return `尚未加载教学班数据；${scope}`
  }
})

function chooseTranscript(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  transcript.value = file && file.name.toLowerCase().endsWith('.pdf') ? file : null
  error.value = file && transcript.value === null ? '请上传 PDF 格式的中山大学成绩单。' : ''
  result.value = null
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

function removeOffering(offering: CourseOffering): void {
  const next = removeCurrentScheduleOffering(form.value.currentSchedule, offering)
  form.value = invalidateManualAttestation(form.value, next).form
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
  if (!transcript.value) {
    error.value = '请先上传成绩单 PDF。'
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
      file: transcript.value,
      semester: request.semester,
      currentSchedule: request.current_schedule,
      manualScheduleAttested: form.value.manualAttestation.attested,
      preference: request.preference,
    })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '方案生成失败，请检查输入后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(loadOfferings)
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
          <span class="tag">RestrictedPlanner</span>
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
                v-for="major in MAJOR_CHOICES"
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
                v-for="major in MAJOR_CHOICES"
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
          当前仅提供<strong>两个样本专业</strong>（网络空间安全 / 遥感科学与技术）；
          <strong>原专业与目标专业不能相同</strong>。
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
      </SectionCard>

      <SectionCard
        :mock="false"
        title="第一步：上传成绩单"
        subtitle="上传中山大学成绩单 PDF，用于识别已修课程。"
      >
        <div class="case-a-upload">
          <label class="case-a-file">
            <span>选择成绩单 PDF</span>
            <input data-testid="case-a-pdf" type="file" accept="application/pdf,.pdf" @change="chooseTranscript" />
          </label>
          <p v-if="transcript" class="case-a-success">✓ 已选择：{{ transcript.name }}</p>
          <p class="case-a-secondary">Transcript source: user-uploaded SYSU transcript PDF</p>
        </div>
      </SectionCard>

      <SectionCard
        :mock="false"
        title="第二步：填写当前课表"
        :subtitle="scheduleSubtitle"
      >
        <div class="case-a-schedule">
          <CurrentScheduleEditor
            :offerings="offerings"
            :current-schedule="form.currentSchedule"
            :semester="form.semester"
            :attestation-notice="attestationNotice"
            @update:current-schedule="updateSchedule"
          />

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
        <h2 class="case-a-explainer__title">系统将如何帮你规划</h2>
        <ul class="case-a-explainer__list">
          <li v-for="step in PLANNING_STEPS" :key="step">✓ {{ step }}</li>
        </ul>
        <p class="case-a-explainer__note">
          调整只会以<strong>建议</strong>形式给出：系统找到候选教学班后需要你确认，⛔ 不会自动替换你的课程。
        </p>
      </div>

      <div class="case-a-submit-wrap">
        <button class="button case-a-submit" type="button" :disabled="loading" data-testid="case-a-submit" @click="submit">
          {{ loading ? '正在规划你的学业路径…' : '生成并优化我的转专业学业方案' }}
        </button>
        <p>系统仅提供规划建议，不执行实际选课操作。</p>
      </div>
      <p v-if="error" class="state state--error" role="alert">{{ error }}</p>

      <template v-if="result">
        <SectionCard :mock="false" title="成绩单识别结果" :badge-count="result.transcript.record_count">
          <p>
            已识别 {{ result.transcript.record_count }} 门已修课程，覆盖 {{ result.transcript.term_count }} 个学期。
            成绩单未提供官方课程号时，系统不会自动伪造或强行认定课程身份。
          </p>
        </SectionCard>

        <SectionCard :mock="false" title="补修缺口分析" :badge-count="result.makeup_tasks.length">
          <MakeupTaskList :tasks="result.makeup_tasks" />
        </SectionCard>

        <SectionCard :mock="false" :title="'本学期推荐课表'" subtitle="按本次响应返回的教学班绘制；这是 Planner 的建议，不代表已经选上课。">
          <WeeklyScheduleView
            :plan-result="result.plan_result"
            :offerings="result.course_offerings"
            :semester="form.semester"
            :current-schedule="form.currentSchedule"
            :makeup-tasks="result.makeup_tasks"
            :preferred-courses="preferredCourses"
          />
        </SectionCard>

        <SectionCard :mock="false" title="待你确认的调整" subtitle="系统只提出建议；确认后才会生效。">
          <PendingAdjustments :plan-result="result.plan_result" :course-name-by-id="resultCourseNames" />
        </SectionCard>

        <!-- 未来学期：只有后端真的返回 roadmap 时才渲染（⛔ 不补假数据） -->
        <SectionCard
          v-if="result.roadmap && result.roadmap.semesters.length > 0"
          :mock="false"
          title="未来学期修读路径"
          subtitle="课程级规划，不含具体教学班。"
        >
          <FutureRoadmapView :roadmap="result.roadmap" />
        </SectionCard>

        <SectionCard :mock="false" title="本次规划数据">
          <div class="case-a-coverage" data-testid="case-a-coverage-summary">
            <div><strong>{{ result.transcript.record_count }}</strong><span>成绩单课程</span></div>
            <div><strong>{{ result.course_offerings.length }}</strong><span>{{ planCourseDataLabel }}</span></div>
            <div><strong>南 + 深</strong><span>数据范围</span></div>
            <div><strong>{{ result.provenance?.is_full_semester ? '是' : '否' }}</strong><span>全校完整学期数据</span></div>
          </div>
          <!--
            ⚠️ 此前这里写死「4069 条教学班」——那是**神秘数字**，且与响应无关。
            现在如实说明"候选池"这一语义，条数见上方由响应计算出的数字。
          -->
          <p class="case-a-secondary">
            响应中的教学班仅作为规划候选池使用，不在页面中逐条铺开。
          </p>
          <!-- 来源照实展示后端 provenance（缺失时整行不渲染） -->
          <p
            v-if="planCourseDataSource"
            class="case-a-secondary"
            data-testid="case-a-plan-course-data-source"
          >
            教学班来源：<code class="mono">{{ planCourseDataSource }}</code>
          </p>
        </SectionCard>

        <SectionCard :mock="false" title="我的选课需求">
          <PreferencePanel :preference="result.preference" :course-name-by-id="resultCourseNames" />
        </SectionCard>

        <SectionCard :mock="false" title="推荐方案" tone="primary">
          <PlanResultPanel :plan-result="result.plan_result" :course-name-by-id="resultCourseNames" />
        </SectionCard>

        <SectionCard :mock="false" title="数据与计算说明">
          <ul class="case-a-provenance">
            <li>成绩单：用户上传的中山大学成绩单 PDF</li>
            <li>培养方案：Case A 目标专业培养方案</li>
            <li>教学班：南校园 + 深圳校区范围数据</li>
            <li>规划器：RestrictedPlanner 实际执行</li>
            <li>完整学期数据：否</li>
          </ul>
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
.case-a-schedule,
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

.case-a-coverage {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.case-a-coverage div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #f8fafc;
}

.case-a-coverage strong {
  font-size: 22px;
  color: var(--text);
}

.case-a-coverage span {
  color: var(--text-muted);
  font-size: 12px;
}

.case-a-provenance {
  margin: 0;
  padding-left: 20px;
  color: #475569;
  line-height: 1.9;
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

  .case-a-coverage {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
</style>
