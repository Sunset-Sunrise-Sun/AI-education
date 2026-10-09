<script setup lang="ts">
import { computed } from 'vue'
import CourseOfferingList from '../CourseOfferingList.vue'
import ExplanationPanel from '../ExplanationPanel.vue'
import MakeupTaskList from '../MakeupTaskList.vue'
import PlanResultPanel from '../PlanResultPanel.vue'
import PreferencePanel from '../PreferencePanel.vue'
import SectionCard from '../SectionCard.vue'
import UserInputPanel from '../UserInputPanel.vue'
import type { E2EDebugInfo } from '../E2EDebugPanel.vue'
import type {
  CourseOffering,
  MakeupTask,
  PlanResult,
  Preference,
} from '../../types/contracts'
import type { UserInputForm } from '../../state/userInput'
import { PLAN_STATUS_LABEL } from '../../utils/labels'

/**
 * `补修路径` 视图：当前学期精确课表 + 后续学期课程级条件路径 + 风险 / 人工确认。
 *
 * 边界：
 * - 所有数据都来自后端（个人规划 / Real Planning / Mock 演示通道），前端**不计算**冲突、
 *   不生成 MakeupTask、不改写 PlanResult；
 * - 保留旧 Case A 的四区块 + 解释入口，保证旧演示继续可用；
 * - AI 调整入口只负责打开抽屉，调整逻辑在抽屉内（两次确认后才可能刷新方案）。
 */
const props = defineProps<{
  state: 'loading' | 'success' | 'error'
  data: {
    makeup_tasks: MakeupTask[]
    course_offerings: CourseOffering[]
    preference: Preference
    plan_result: PlanResult
  } | null
  dataSource: string | null
  demoErrorMessage: string
  userInput: UserInputForm
  dataMode: 'mock' | 'real'
  planApiEnabled: boolean
  planSubmitting: boolean
  planErrorMessage: string
  planErrorKind: string | null
  planErrorStatus: number | null
  planErrorCode: string | null
  planErrorDetail: string | null
  debugInfo: E2EDebugInfo
  dev: boolean
  scheduleBlockReason: string | null
  explanationApiEnabled: boolean
  explanationOpen: boolean
  explanationFocusCourseId: string | null
  explanationRequestSeq: number
  displayedPlanResult: PlanResult | null
  planResultMode: 'mock' | 'real'
  planResultCourseNameById: Record<string, string>
  courseNameById: Record<string, string>
  /** 后端个人规划结果是否被用作当前方案。 */
  personalPlanApplied: boolean
  personalPlanNotice: string | null
}>()

const emit = defineEmits<{
  (event: 'update:form', form: UserInputForm): void
  (event: 'submit-real-plan'): void
  (event: 'reload-demo'): void
  (event: 'open-explanation', courseId: string | null): void
  (event: 'close-explanation'): void
  (event: 'open-ai-drawer', focusCourseId: string | null): void
}>()

/** 当前学期课表：直接来自方案的建议教学班（前端不重排）。 */
const semesterClasses = computed(() => props.displayedPlanResult?.selected_classes ?? [])

const offeringByKey = computed(() => {
  const map = new Map<string, CourseOffering>()
  for (const offering of props.data?.course_offerings ?? []) {
    map.set(`${offering.course_id}::${offering.class_id}`, offering)
  }
  return map
})

function classMeetingsLabel(courseId: string, classId: string): string {
  const offering = offeringByKey.value.get(`${courseId}::${classId}`)
  if (offering === undefined) {
    return '当前上下文没有该教学班的排课信息'
  }
  if (offering.meetings.length === 0) {
    return '当前数据中无排课信息（仅表示来源快照没有可用排课信息，不作其它推断）'
  }
  return offering.meetings
    .map(
      (meeting) =>
        `周${meeting.weekday} 第 ${meeting.start_section}-${meeting.end_section} 节 · ${
          meeting.weeks.length
        } 周 · ${meeting.campus ?? '地点未提供'}`,
    )
    .join(' / ')
}

/** 后续学期条件路径：只按后端给出的建议 / 截止学期分组，不推断课程先后。 */
const laterSemesters = computed(() => {
  const groups = new Map<number, MakeupTask[]>()
  for (const task of props.data?.makeup_tasks ?? []) {
    const semester = task.recommended_semester
    if (semester === null || semester === undefined) {
      continue
    }
    const bucket = groups.get(semester) ?? []
    bucket.push(task)
    groups.set(semester, bucket)
  }
  return [...groups.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([semester, tasks]) => ({ semester, tasks }))
})

const tasksWithoutPlan = computed(() =>
  (props.data?.makeup_tasks ?? []).filter(
    (task) => task.recommended_semester === null || task.recommended_semester === undefined,
  ),
)

const planRisks = computed(() => props.displayedPlanResult?.risks ?? [])
const planUnresolved = computed(() => props.displayedPlanResult?.unresolved ?? [])
const planChanges = computed(() => props.displayedPlanResult?.changes ?? [])

const selectedCreditTotal = computed(() => {
  let total = 0
  for (const selected of semesterClasses.value) {
    const offering = offeringByKey.value.get(`${selected.course_id}::${selected.class_id}`)
    total += offering?.credit ?? 0
  }
  return total
})

/** 解释区是否可见：只有存在方案时才显示入口。 */
const explanationEntryVisible = computed(() => props.displayedPlanResult !== null)
</script>

<template>
  <section class="view view--path" data-testid="view-makeup-path">
    <header class="view__head">
      <h2>补修路径</h2>
      <p>
        当前学期看<strong>精确到教学班的课表</strong>，后续学期看<strong>课程级条件路径</strong>。
        路径、风险与待确认项都来自后端结果；前端不重排、不优化、不生成课程。
      </p>
    </header>

    <p v-if="personalPlanNotice" class="ai-preview" data-testid="path-personal-notice">
      ⚠️ {{ personalPlanNotice }}
    </p>

    <!-- AI 调整入口：只打开抽屉，不在本视图计算 -->
    <div class="path-ai-bar" data-testid="path-ai-bar">
      <div>
        <strong>想调整这个方案？</strong>
        <span class="ai-block__hint">
          打开 AI 调整面板，用一句自然语言说明目标；需要<strong>两次确认</strong>才会改动方案。
        </span>
      </div>
      <button
        type="button"
        class="button"
        data-testid="path-open-ai-drawer"
        :disabled="displayedPlanResult === null"
        @click="emit('open-ai-drawer', null)"
      >
        💬 AI 调整当前方案
      </button>
    </div>

    <!-- 状态一：加载中 -->
    <SectionCard
      v-if="state === 'loading'"
      title="正在加载演示数据"
      subtitle="页面仅调用后端 Mock 聚合接口，不包含任何客户端预设或合成数据。"
    >
      <div class="loading-wrap">
        <div class="spinner"></div>
        <p class="state state--loading">正在向后端发送数据请求…</p>
      </div>
    </SectionCard>

    <!-- 状态二：请求失败 -->
    <SectionCard
      v-else-if="state === 'error'"
      title="Demo 数据加载失败"
      subtitle="页面不会自动生成替代数据，也严禁展示未经后端正式响应的内容。"
      tone="attention"
    >
      <div class="error-box">
        <p class="state state--error">后端接口连接异常</p>
        <p class="state__detail">{{ demoErrorMessage }}</p>
        <p class="state__hint">
          请检查本地 FastAPI 后端服务是否已在 8000 端口启动：<br />
          <code class="mono">cd backend &amp;&amp; python -m uvicorn app.main:app --reload</code>
        </p>
        <button class="button" type="button" @click="emit('reload-demo')">🔄 重新尝试连接</button>
      </div>
    </SectionCard>

    <template v-else-if="data">
      <!-- 当前学期精确课表 -->
      <SectionCard
        section-id="section-current-semester"
        tone="primary"
        title="当前学期精确课表"
        subtitle="来自方案 selected_classes 与教学班供给的排课信息；前端只展示，不做冲突检测，也不改选教学班。"
      >
        <div class="path-summary" data-testid="path-current-summary">
          <span>建议教学班：<strong class="num">{{ semesterClasses.length }}</strong> 个</span>
          <span>可统计学分合计：<strong class="num">{{ selectedCreditTotal }}</strong> 学分</span>
          <span>
            Planner 状态：
            <span
              v-if="displayedPlanResult"
              class="tag tag--plan"
              :class="`tag--plan-${displayedPlanResult.status}`"
            >
              {{ PLAN_STATUS_LABEL[displayedPlanResult.status] }}
            </span>
            <span v-else class="text-muted">—</span>
          </span>
        </div>

        <ul v-if="semesterClasses.length > 0" class="path-table" data-testid="path-current-classes">
          <li v-for="item in semesterClasses" :key="`${item.course_id}-${item.class_id}`">
            <span class="mono">{{ item.course_id }}</span>
            <span>{{ courseNameById[item.course_id] ?? '（课程名未在当前上下文提供）' }}</span>
            <span class="mono">班号 {{ item.class_id }}</span>
            <span class="ai-block__hint">{{ classMeetingsLabel(item.course_id, item.class_id) }}</span>
            <button
              type="button"
              class="button button--ghost button--small"
              :data-testid="`path-focus-ai-${item.course_id}`"
              @click="emit('open-ai-drawer', item.course_id)"
            >
              💬 就这门课调整
            </button>
          </li>
        </ul>
        <p v-else class="empty-state" data-testid="path-current-empty">
          当前方案没有建议教学班。这只表示<strong>没有选中条目</strong>，
          不构成"已经排好课"或"不需要补修"的结论。
        </p>
      </SectionCard>

      <!-- 后续学期课程级条件路径 -->
      <SectionCard
        section-id="section-later-semesters"
        title="后续学期课程级条件路径"
        subtitle="按后端给出的 recommended_semester 分组展示补修课程；先修关系只转述 prerequisites，前端不新增、不猜测先修边。"
      >
        <div v-if="laterSemesters.length > 0" class="path-terms" data-testid="path-later-terms">
          <article v-for="group in laterSemesters" :key="group.semester" class="path-term">
            <h4>第 {{ group.semester }} 学期（{{ group.tasks.length }} 门）</h4>
            <ul>
              <li v-for="task in group.tasks" :key="task.course_id">
                <span class="mono">{{ task.course_id }}</span> {{ task.course_name }}
                · {{ task.credit }} 学分 · {{ task.status }}
                <span v-if="task.deadline_semester" class="ai-block__hint">
                  最迟第 {{ task.deadline_semester }} 学期
                </span>
                <span v-if="(task.prerequisites?.length ?? 0) > 0" class="ai-block__hint">
                  先修：{{ (task.prerequisites ?? []).join('、') }}
                </span>
              </li>
            </ul>
          </article>
        </div>
        <p v-else class="empty-state" data-testid="path-later-empty">
          当前没有带建议学期的补修课程。
        </p>

        <p v-if="tasksWithoutPlan.length > 0" class="ai-block__hint" data-testid="path-no-semester">
          另有 {{ tasksWithoutPlan.length }} 门补修课程<strong>没有建议学期</strong>：
          后端未给出学期安排，页面不会替你排。
        </p>
      </SectionCard>

      <!-- 补修优先级说明 / 风险 / 人工确认 -->
      <SectionCard
        section-id="section-priority-risk"
        tone="attention"
        title="补修优先级说明、风险与人工确认"
        subtitle="优先级与风险一律来自后端字段（deadline_semester / risks / unresolved）；前端不作排名或风险判定。"
      >
        <div class="path-risk-grid">
          <div class="ai-block">
            <h5>优先级线索（后端字段）</h5>
            <ul data-testid="path-priority-list">
              <li v-for="task in data.makeup_tasks" :key="`p-${task.course_id}`">
                <span class="mono">{{ task.course_id }}</span>
                <span v-if="task.deadline_semester">最迟第 {{ task.deadline_semester }} 学期</span>
                <span v-else class="text-muted">未给出截止学期</span>
              </li>
            </ul>
          </div>

          <div class="ai-block">
            <h5>方案风险（{{ planRisks.length }}）</h5>
            <ul v-if="planRisks.length > 0" data-testid="path-risk-list">
              <li v-for="(risk, index) in planRisks" :key="`r-${index}`">
                <span class="tag tag--risk" :class="`tag--risk-${risk.level}`">{{ risk.level }}</span>
                {{ risk.course_id ? `${risk.course_id}：` : '' }}{{ risk.reason }}
              </li>
            </ul>
            <p v-else class="empty-state">后端未返回风险项。</p>
          </div>

          <div class="ai-block">
            <h5>待人工确认 / 未决（{{ planUnresolved.length }}）</h5>
            <ul v-if="planUnresolved.length > 0" data-testid="path-unresolved-list">
              <li v-for="(item, index) in planUnresolved" :key="`u-${index}`">
                <span class="mono">{{ item.type }}</span> {{ item.message }}
              </li>
            </ul>
            <p v-else class="empty-state">后端未返回未决事项。</p>
          </div>
        </div>
      </SectionCard>

      <!-- 用户输入区（保留旧 Case A 输入体验） -->
      <SectionCard
        section-id="section-user-input"
        title="0. 用户输入（目标学期、转专业上下文、当前课表与偏好）"
        subtitle="收集生成规划所需的用户输入：目标学期、学生转专业上下文、当前课表与个性化偏好，以及成绩单文件选择。本区块只组织输入，不做冲突检测、不生成补修任务。"
      >
        <UserInputPanel
          :form="userInput"
          :offerings="data?.course_offerings ?? []"
          :plan-api-enabled="planApiEnabled"
          :submitting="planSubmitting"
          :mode="dataMode"
          :data-source-label="dataSource"
          :plan-error-message="planErrorMessage"
          :plan-error-kind="planErrorKind"
          :plan-error-status="planErrorStatus"
          :plan-error-code="planErrorCode"
          :plan-error-detail="planErrorDetail"
          :debug-info="debugInfo"
          :dev="dev"
          :schedule-block-reason="scheduleBlockReason"
          @update:form="emit('update:form', $event)"
          @submit-real="emit('submit-real-plan')"
        />
      </SectionCard>

      <!-- 概览 -->
      <div class="overview-bar">
        <div class="overview-metric">
          <span class="overview-metric__label">历史培养要求评估项</span>
          <span class="overview-metric__val num">{{ data.makeup_tasks.length }} <small>条</small></span>
        </div>
        <div class="overview-metric">
          <span class="overview-metric__label">教学班记录</span>
          <span class="overview-metric__val num">{{ data.course_offerings.length }} <small>个</small></span>
        </div>
        <div class="overview-metric">
          <span class="overview-metric__label">单学期学分上限</span>
          <span class="overview-metric__val num">{{ data.preference.max_credit ?? '—' }} <small>学分</small></span>
        </div>
        <div class="overview-metric">
          <span class="overview-metric__label">规划结果状态</span>
          <span
            v-if="displayedPlanResult"
            class="tag tag--plan"
            :class="`tag--plan-${displayedPlanResult.status}`"
          >
            {{ PLAN_STATUS_LABEL[displayedPlanResult.status] }}
          </span>
          <span v-else class="text-muted">—</span>
        </div>
      </div>

      <!-- 1. 历史培养要求评估 -->
      <SectionCard
        mock
        section-id="section-makeup"
        title="1. 历史培养要求评估（MakeupTask）"
        subtitle="Curriculum 模块依据目标培养方案要求与学生已修记录逐条评估后的结果，含“已满足 / 待课程认定 / 已确认需补修”等不同状态。逐条状态以每行的判定列与认定说明为准，前端不作汇总改写。"
        :badge-count="data.makeup_tasks.length"
      >
        <MakeupTaskList
          :tasks="data.makeup_tasks"
          :evidence-enabled="explanationApiEnabled"
          @explain-course="emit('open-explanation', $event)"
        />
      </SectionCard>

      <!-- 2. 开课教学班 -->
      <SectionCard
        mock
        section-id="section-offerings"
        title="2. 开课教学班供给 (CourseOffering)"
        subtitle="Course Data 模块从教务系统中抓取并标准化的目标学期开课清单：支持多段排课及中性无排课数据状态（DG-01 / DG-07D）。"
        :badge-count="data.course_offerings.length"
      >
        <CourseOfferingList :offerings="data.course_offerings" />
      </SectionCard>

      <!-- 3. 用户偏好 -->
      <SectionCard
        mock
        section-id="section-preference"
        title="3. 学生个性化偏好 (Preference)"
        subtitle="Agent 模块解析学生自然语言输入所形成的约束条件：包含学分上限控制、避免跨校区、回避特定时段及意向课程。"
      >
        <PreferencePanel :preference="data.preference" :course-name-by-id="courseNameById" />
      </SectionCard>

      <!-- 4. 规划结果 -->
      <SectionCard
        section-id="section-plan"
        tone="primary"
        title="4. 规划结果与建议课表 (PlanResult)"
        subtitle="展示 Planner 输出的 PlanResult：包含建议课表、方案变更、风险项与未决事项；前端不补充业务判断。"
      >
        <div class="uig-provenance" data-testid="plan-provenance">
          <span class="uig-provenance__item">
            基础演示数据：<strong class="uig-provenance__mock">Mock</strong>
          </span>
          <span class="uig-provenance__sep" aria-hidden="true">·</span>
          <span class="uig-provenance__item">
            规划结果：<strong
              :class="planResultMode === 'real' ? 'uig-provenance__real' : 'uig-provenance__mock'"
              data-testid="plan-result-provenance"
            >{{ planResultMode === 'real' ? 'Real' : 'Mock' }}</strong>
          </span>
          <span v-if="personalPlanApplied" class="uig-provenance__item" data-testid="plan-personal-applied">
            · 来源：后端个人规划结果
          </span>
          <span class="uig-provenance__note">
            <template v-if="planResultMode === 'real'">
              本区块方案来自 <code class="mono">POST /api/v1/plan</code>；
              其余区块（MakeupTask / 教学班 / Preference）仍为 Mock 演示数据。
            </template>
            <template v-else>
              本区块方案来自 <code class="mono">GET /api/v1/mock/demo</code>；尚未提交 Real Planning。
            </template>
          </span>
        </div>

        <PlanResultPanel
          v-if="displayedPlanResult"
          :plan-result="displayedPlanResult"
          :course-name-by-id="planResultCourseNameById"
          :evidence-enabled="explanationApiEnabled"
          @explain-result="emit('open-explanation', $event)"
        />
      </SectionCard>

      <!-- 5. 解释与依据 -->
      <SectionCard
        v-if="explanationEntryVisible"
        section-id="section-explanation"
        title="5. 解释与依据（为什么这样判定 / 这样安排）"
        subtitle="只读解释：逐条说明补修判定、教学班安排、调班原因、风险与未决事项的依据来源，并列出仍需人工确认的事项。前端不生成解释、不重算方案。"
      >
        <div class="uig-provenance" data-testid="explanation-provenance">
          <span class="uig-provenance__item">
            解释对象：<strong
              :class="planResultMode === 'real' ? 'uig-provenance__real' : 'uig-provenance__mock'"
              data-testid="explanation-target-provenance"
            >{{ planResultMode === 'real' ? 'Real 规划结果' : 'Mock 演示结果' }}</strong>
          </span>
          <span class="uig-provenance__sep" aria-hidden="true">·</span>
          <span class="uig-provenance__item">
            解释通道：<strong
              :class="explanationApiEnabled ? 'uig-provenance__real' : 'uig-provenance__mock'"
              data-testid="explanation-channel-state"
            >{{ explanationApiEnabled ? '已启用' : '未启用' }}</strong>
          </span>
          <span class="uig-provenance__note">
            解释请求只发送 <code class="mono">PlanResult</code> 与被解释条目所需的
            <code class="mono">MakeupTask</code> / <code class="mono">CourseOffering</code> 上下文；
            ⛔ 不发送成绩单、姓名、学号或个人身份信息。
          </span>
        </div>

        <button
          v-if="!explanationOpen"
          type="button"
          class="button"
          data-testid="explanation-open"
          @click="emit('open-explanation', null)"
        >
          🔍 查看依据 / 为什么这样安排
        </button>

        <ExplanationPanel
          v-else
          :key="`explanation-${explanationRequestSeq}-${explanationFocusCourseId ?? 'all'}`"
          :plan-result="displayedPlanResult!"
          :makeup-tasks="data.makeup_tasks"
          :course-offerings="data.course_offerings"
          :enabled="explanationApiEnabled"
          :focus-course-id="explanationFocusCourseId"
          :plan-result-source="planResultMode"
          @close="emit('close-explanation')"
        />
      </SectionCard>
    </template>
  </section>
</template>
