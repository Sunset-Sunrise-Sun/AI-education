<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { loadCaseAOfferings, applyCaseARepair, runCaseADemo, type CaseADemoResponse } from '../api/caseADemo'
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
import CurrentElectiveSection from './CurrentElectiveSection.vue'
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
const offerings = ref<CourseOffering[]>([])
const transcript = ref<File | null>(null)
const result = ref<CaseADemoResponse | null>(null)
const loading = ref(false)
const error = ref('')
const manualOpen = ref(false)

/* ---- 显式换班确认（⛔ 只有用户点击「采用调整」才会走这里） ---- */
const applying = ref(false)
const applyError = ref('')
const applyNotice = ref('')
/**
 * 换班已应用、但**重新规划尚未返回**：此时 `result.plan_result` 描述的是
 * **换班前**的课表，与已经改变的当前课表互相矛盾。
 *
 * ⛔ 不得把这种"半新半旧"的结果当作当前方案展示：
 *    - ⛔ 不清空 `unresolved` 里与换班无关的警告（那等于**静默丢掉**必须人工复核的事实）；
 *    - ⛔ 也不继续按旧结果渲染课表/建议/路线图。
 * 因此改为**整块标记为待刷新并暂停展示**，直到重新规划真正成功。
 */
const planStale = ref(false)

/**
 * 应用一条换班建议：**唯一**可信来源是后端。
 *
 * 边界：
 * - 请求带**完整身份**（semester / course_id / from_class_id / to_class_id）；
 * - 课表只采用**后端返回的 schedule**，⛔ 前端不自行拼一张"看起来对"的课表；
 * - 后端拒绝时如实显示原因，⛔ 不假装替换成功、⛔ 不自动重试别的候选；
 * - 应用成功后把旧方案标记为**待刷新**（见 `planStale`），
 *   ⛔ 不修改、也不隐藏旧方案里的 unresolved 事实。
 */
async function applyRepair(payload: {
  semester: string
  courseId: string
  fromClassId: string
  toClassId: string
}): Promise<void> {
  if (applying.value) return
  applying.value = true
  applyError.value = ''
  applyNotice.value = ''
  try {
    const applied = await applyCaseARepair({
      semester: payload.semester,
      courseId: payload.courseId,
      fromClassId: payload.fromClassId,
      toClassId: payload.toClassId,
      currentSchedule: form.value.currentSchedule,
      manualScheduleAttested: form.value.manualAttestation.attested,
    })
    // 课表只采用后端返回结果（⛔ 不本地推断）。
    form.value = invalidateManualAttestation(form.value, applied.schedule).form
    if (!applied.applied) {
      // 未生效 ⇒ 课表没变 ⇒ 原方案仍然有效，保持原样并如实说明。
      applyError.value = applied.reason
      applyNotice.value = `该调整未生效：${applied.reason}`
      return
    }
    // 生效 ⇒ 旧方案立刻失效。
    planStale.value = true
    applyNotice.value = `已按你的确认把 ${payload.courseId} 从 ${payload.fromClassId} 调整为 ${payload.toClassId}。`
    // 重新规划（后端计算）；成功后统一用新结果替换旧方案。
    if (transcript.value) {
      try {
        await submit({ silent: true })
      } catch {
        applyError.value =
          '换班已生效，但重新生成方案失败：下方方案已标记为待刷新，请重新点击「生成并优化我的转专业学业方案」。'
      }
    }
  } catch (cause) {
    applyError.value = cause instanceof Error ? cause.message : '换班请求失败。'
  } finally {
    applying.value = false
  }
}

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

/**
 * 上传成绩单是否**真的**参与了满足判定。
 *
 * ⛔ 这里**没有**"已绑定 ⇒ 不提示"的分支：后端只有 `not_bound` 一种受支持语义
 *    （见 `backend/app/services/case_a_demo.py::_completed_binding`），
 *    因此这条 provenance 提示**始终**展示 —— 没有任何取值可以抑制它。
 */
const bindingNotice = computed(() => {
  const current = result.value
  if (!current) return ''
  return (
    current.completed_binding_note ||
    '上传的成绩单没有参与「已修完 / 已满足」的判定，培养方案已确认的事实原样保留。'
  )
})

/* ---- 学业方案总览（用户第一眼看到的东西） ---- */
const overviewCredit = computed(() => {
  const load = result.value?.current_load
  return load ? `${load.projected_total_credit} 学分` : '—'
})
const overviewMakeup = computed(() => {
  const tasks = result.value?.makeup_tasks ?? []
  const required = tasks.filter((task) => task.status === 'required').length
  const pending = tasks.filter(
    (task) => task.status === 'manual_confirmation' || task.status === 'possibly_equivalent',
  ).length
  if (required === 0 && pending === 0) return '暂无'
  return pending > 0 ? `${required} 门（${pending} 门待确认）` : `${required} 门`
})
const overviewElective = computed(() => {
  const load = result.value?.current_load
  return load ? `${load.suggested_elective_credit} 学分` : '—'
})
const overviewActionCount = computed(() => {
  const proposals = result.value?.repair_proposals
  if (!proposals) return '0 项'
  const courses = new Set(proposals.proposals.map((item) => item.course_id))
  return `${courses.size + proposals.unresolved.length} 项`
})
const overviewTermCount = computed(() => {
  const terms = result.value?.roadmap?.future_semesters ?? []
  return terms.length > 0 ? `${terms.length} 个` : '暂无'
})

/** 最多两条最关键的提示（⛔ 不把 21 条 unresolved 堆给用户）。 */
const overviewHints = computed(() => {
  const hints: string[] = []
  const current = result.value
  if (!current) return hints
  const load = current.current_load
  if (load?.exceeds_max) {
    hints.push(
      `本学期预计 ${load.projected_total_credit} 学分，超过你设置的上限 ${load.max_credit} 学分，建议减少选课。`,
    )
  }
  const courses = new Set((current.repair_proposals?.proposals ?? []).map((p) => p.course_id))
  if (courses.size > 0) {
    hints.push(`有 ${courses.size} 门课程可以换到与你课表不冲突的教学班，需要你确认后才会生效。`)
  }
  const elective = current.current_elective_recommendations ?? []
  if (elective.length > 0 && hints.length < 2) {
    hints.push(
      `你的专业选修还差学分，本学期有 ${elective.length} 门可选专业课程（见下方「本学期专业选修建议」）。`,
    )
  }
  const blockers = current.repair_proposals?.unresolved ?? []
  if (blockers.length > 0 && hints.length < 2) {
    hints.push(`另有 ${blockers.length} 门课程暂时无法给出可靠的换班建议，可在「需要你处理」里查看原因。`)
  }
  return hints.slice(0, 2)
})

async function loadOfferings(): Promise<void> {
  error.value = ''
  try {
    offerings.value = await loadCaseAOfferings(form.value.semester)
  } catch (cause) {
    offerings.value = []
    error.value = cause instanceof Error ? cause.message : '教学班数据暂时不可用。'
  }
}

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

/**
 * 「加入考虑」= 把该课程写入意向课程（`preference.preferredCourses`）。
 *
 * ⛔ 只是**偏好**，⛔ 不是选课，也⛔ 不代表学校已认定；
 * 用户点「生成并优化我的转专业学业方案」后才会重新规划。
 */
function addElectiveToIntent(payload: { courseId: string }): void {
  addPreferred(payload.courseId)
}

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

async function submit(options: { silent?: boolean } = {}): Promise<void> {
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
  if (!options.silent) result.value = null
  try {
    const request = buildRealPlanRequest(form.value)
    result.value = await runCaseADemo({
      file: transcript.value,
      semester: request.semester,
      currentSchedule: request.current_schedule,
      manualScheduleAttested: form.value.manualAttestation.attested,
      preference: request.preference,
    })
    // 只有**重新规划成功**才解除"待刷新"状态。
    planStale.value = false
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '方案生成失败，请检查输入后重试。'
    // silent 调用（换班后的自动重算）失败时向上抛，让调用方如实说明；
    // 同时保留 planStale = true，⛔ 不把旧方案伪装成当前方案。
    if (options.silent) throw cause
  } finally {
    loading.value = false
  }
}

/** 模板点击入口：⛔ 不把 PointerEvent 当作 submit 的选项对象。 */
function submitFromClick(): void {
  void submit()
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
            上传成绩单后，系统将结合目标专业培养方案、真实教学班数据和你的当前课表，
            生成补修与排课建议。
          </p>
        </div>
        <div class="case-a-tags" aria-label="数据与计算范围">
          <span class="tag tag--source-real">真实教学班数据</span>
          <span class="tag">南校园 + 深圳校区</span>
          <span class="tag">RestrictedPlanner</span>
        </div>
      </section>

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
        :subtitle="`已加载真实教学班数据 ${offerings.length} 条；数据范围为南校园 + 深圳校区。`"
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
        <button class="button case-a-submit" type="button" :disabled="loading" data-testid="case-a-submit" @click="submitFromClick">
          {{ loading ? '正在规划你的学业路径…' : '生成并优化我的转专业学业方案' }}
        </button>
        <p>系统仅提供规划建议，不执行实际选课操作。</p>
      </div>
      <p v-if="error" class="state state--error" role="alert">{{ error }}</p>

      <p v-if="applyNotice" class="case-a-apply-notice" data-testid="case-a-repair-notice">
        {{ applyNotice }}
      </p>
      <p v-if="applyError" class="case-a-error" data-testid="case-a-repair-error">
        {{ applyError }}
      </p>
      <p v-if="planStale" class="case-a-stale" data-testid="case-a-plan-stale">
        课表已按你的确认更新，但下方方案还是<strong>换班之前</strong>的结果，因此暂停展示，
        正在用新的当前课表重新生成；你也可以直接重新点击「生成并优化我的转专业学业方案」。
      </p>

      <template v-if="result && !planStale">
        <!-- ① 学业方案总览：用户第一眼要知道"这学期怎么上、我要处理什么、未来怎么走" -->
        <section class="overview" data-testid="case-a-overview">
          <h2 class="overview__title">我的转专业方案</h2>
          <div class="overview__grid">
            <div>
              <strong data-testid="case-a-overview-credit">{{ overviewCredit }}</strong>
              <span>本学期预计学分</span>
            </div>
            <div>
              <strong data-testid="case-a-overview-makeup">{{ overviewMakeup }}</strong>
              <span>补修课程</span>
            </div>
            <div>
              <strong data-testid="case-a-overview-elective">{{ overviewElective }}</strong>
              <span>专业选修学分</span>
            </div>
            <div>
              <strong data-testid="case-a-overview-actions">{{ overviewActionCount }}</strong>
              <span>需要我确认</span>
            </div>
            <div>
              <strong data-testid="case-a-overview-terms">{{ overviewTermCount }}</strong>
              <span>未来学期</span>
            </div>
          </div>
          <ul v-if="overviewHints.length > 0" class="overview__hints" data-testid="case-a-overview-hints">
            <li v-for="(hint, index) in overviewHints" :key="index">{{ hint }}</li>
          </ul>
        </section>

        <!-- ⛔ 必须在下方的方案结果**之前**如实说明：上传的成绩单有没有参与满足判定 -->
        <p v-if="bindingNotice" class="case-a-binding" data-testid="case-a-binding-notice">
          <strong>上传的成绩单未参与「已修完 / 已满足」判定。</strong>
          {{ bindingNotice }}
        </p>

        <SectionCard :mock="false" title="成绩单识别结果" :badge-count="result.transcript.record_count">
          <p>
            已识别 {{ result.transcript.record_count }} 门已修课程，覆盖 {{ result.transcript.term_count }} 个学期。
            成绩单未提供官方课程号时，系统不会自动伪造或强行认定课程身份。
          </p>
          <p
            v-if="bindingNotice"
            class="case-a-secondary"
            data-testid="case-a-transcript-binding-note"
          >
            本次未使用上传行推导满足状态；下方「补修缺口分析」中的已满足课程来自培养方案
            已确认的事实，而不是来自你上传的 PDF。
          </p>
        </SectionCard>

        <SectionCard :mock="false" title="补修缺口分析" :badge-count="result.makeup_tasks.length">
          <MakeupTaskList :tasks="result.makeup_tasks" />
        </SectionCard>

        <SectionCard :mock="false" title="本学期推荐课表" subtitle="按真实教学班绘制；这是 Planner 的建议，不代表已经选上课。">
          <WeeklyScheduleView
            :plan-result="result.plan_result"
            :offerings="result.course_offerings"
            :semester="form.semester"
            :current-schedule="form.currentSchedule"
            :makeup-tasks="result.makeup_tasks"
            :preferred-courses="preferredCourses"
          />
        </SectionCard>

        <SectionCard
          :mock="false"
          title="本学期专业选修建议"
          subtitle="候选来自培养方案选修组 ∩ 本学期已接受教学班；⛔ 系统不会替你选课。"
        >
          <CurrentElectiveSection
            :recommendations="result.current_elective_recommendations"
            :load="result.current_load"
            @add="addElectiveToIntent"
          />
        </SectionCard>

        <SectionCard :mock="false" title="待你确认的调整" subtitle="系统只提出建议；你确认后才会生效。">
          <PendingAdjustments
            :plan-result="result.plan_result"
            :repair-proposals="result.repair_proposals"
            :course-name-by-id="resultCourseNames"
            :offerings="result.course_offerings"
            :applying="applying"
            @apply="applyRepair"
          />
        </SectionCard>

        <SectionCard
          v-if="result.roadmap && result.roadmap.future_semesters.length > 0"
          :mock="false"
          title="未来学期修读路径"
          subtitle="课程级规划，不含具体教学班。"
        >
          <FutureRoadmapView :roadmap="result.roadmap" />
        </SectionCard>

        <!-- 后端明确说明无法构建路线图时如实展示（⛔ 不补假数据） -->
        <SectionCard
          v-else-if="result.roadmap_note"
          :mock="false"
          title="未来学期修读路径"
          subtitle="当前无法生成。"
        >
          <p class="case-a-secondary" data-testid="case-a-roadmap-note">{{ result.roadmap_note }}</p>
        </SectionCard>

        <SectionCard :mock="false" title="本次规划数据">
          <div class="case-a-coverage" data-testid="case-a-coverage-summary">
            <div><strong>{{ result.transcript.record_count }}</strong><span>成绩单课程</span></div>
            <div><strong>{{ result.course_offerings.length }}</strong><span>真实教学班</span></div>
            <div><strong>南 + 深</strong><span>数据范围</span></div>
            <div><strong>否</strong><span>全校完整学期数据</span></div>
          </div>
          <p class="case-a-secondary">
            4069 条教学班仅作为规划候选池使用，不在页面中逐条铺开。
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
.case-a-stale,
.case-a-binding,
.case-a-apply-notice,
.case-a-error,
.case-a-submit-wrap p,
.case-a-selected-item p,
.case-a-class-main p {
  margin: 0;
}

/* 换班已生效、方案待重新生成：明确说明"下方不是当前方案"。 */
.case-a-stale {
  padding: 12px 14px;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #f3d9a4;
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.7;
}

/* 上传成绩单未参与满足判定：provenance 说明必须显眼且在下文结果之前。 */
.case-a-binding {
  padding: 12px 14px;
  color: #1e40af;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.7;
}

/* 学业方案总览：页面第一屏，先回答"这学期怎么样、我要做什么"。 */
.overview {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 18px;
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.overview__title {
  margin: 0;
  font-size: 18px;
  color: var(--text);
}

.overview__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}

.overview__grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.overview__grid strong {
  font-size: 18px;
  color: #3276df;
}

.overview__grid span {
  color: var(--text-muted);
  font-size: 11px;
}

.overview__hints {
  margin: 0;
  padding-left: 20px;
  color: #475569;
  font-size: 13px;
  line-height: 1.8;
}

.case-a-apply-notice {
  padding: 10px 12px;
  color: #166534;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.7;
}

.case-a-error {
  padding: 10px 12px;
  color: #991b1b;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.7;
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
