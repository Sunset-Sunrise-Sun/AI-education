<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import CourseOfferingList from './components/CourseOfferingList.vue'
import MakeupTaskList from './components/MakeupTaskList.vue'
import PlanResultPanel from './components/PlanResultPanel.vue'
import PreferencePanel from './components/PreferencePanel.vue'
import SectionCard from './components/SectionCard.vue'
import TopStatusBar from './components/TopStatusBar.vue'
import UserInputPanel from './components/UserInputPanel.vue'
import { useDemoData } from './composables/useDemoData'
import { DEMO_ENDPOINT, PLAN_API_ENABLED, initialDataMode } from './config'
import { buildRealPlanRequest, createDefaultUserInputForm, evaluatePlanSubmission, isScheduleSubmittableToRealPlanning } from './state/userInput'
import type { UserInputForm } from './state/userInput'
import { fetchRealPlan } from './api/plan'
import type { PlanResult } from './types/contracts'
import { PLAN_STATUS_LABEL } from './utils/labels'

const { state, data, dataSource, errorMessage, load } = useDemoData()

/**
 * 用户输入（Frontend User Input Gate, Phase 1）。
 *
 * 这里保存的唯一真源只是**用户录入的输入**，与 Mock Demo 数据无关：
 * 即使 Mock 通道加载失败，输入区仍然可用。
 */
const userInput = ref<UserInputForm>(createDefaultUserInputForm())
const dataMode = ref(initialDataMode())

/**
 * Real Planning 结果。
 *
 * 只有**成功调用** `POST /api/v1/plan` 后才会被赋值；
 * 失败时保持 `null` 并如实显示错误 —— 既不复用 Mock 数据，也不生成任何替代结果。
 */
const realPlanResult = ref<PlanResult | null>(null)
const planErrorMessage = ref('')
const planSubmitting = ref(false)

/**
 * Real 提交是否被 **provenance 门禁**阻止。
 *
 * 在真实教学班接入前，Mock 教学班不得进入 Real Planning。
 */
const realPlanScheduleBlocked = computed(
  () => !isScheduleSubmittableToRealPlanning(userInput.value),
)

/**
 * **规划结果**的 provenance —— 只看规划结果本身，不冒充整页数据来源。
 *
 * ⚠️ `/api/v1/plan` 当前只返回 `PlanResult`：
 * MakeupTask / CourseOffering / Preference 仍全部来自 Mock Demo，
 * 因此**绝不能**把整个页面统一标成 Real。
 */
const planResultMode = computed<'mock' | 'real'>(() =>
  realPlanResult.value ? 'real' : 'mock',
)

/** 当前实际渲染的规划结果：Real 成功后展示 Real，否则展示 Mock Demo 的结果。 */
const displayedPlanResult = computed<PlanResult | null>(
  () => realPlanResult.value ?? data.value?.plan_result ?? null,
)

async function submitRealPlan(): Promise<void> {
  if (planSubmitting.value) {
    return
  }

  // 提交前的最后一道守卫（纯函数，见 `evaluatePlanSubmission`）：
  // 任一条件不满足时**一个请求也不发**。
  // 按钮的 disabled 只是界面提示，不能作为唯一防线（程序化调用 / 事件顺序异常都可能绕过它）。
  const gate = evaluatePlanSubmission(userInput.value)
  if (!gate.allowed) {
    planErrorMessage.value = gate.reason
    return
  }

  planSubmitting.value = true
  planErrorMessage.value = ''

  try {
    realPlanResult.value = await fetchRealPlan(buildRealPlanRequest(userInput.value))
    dataMode.value = 'real'
  } catch (error) {
    realPlanResult.value = null
    dataMode.value = 'mock'
    planErrorMessage.value =
      error instanceof Error ? error.message : '发生了未知错误，请查看浏览器控制台。'
  } finally {
    planSubmitting.value = false
  }
}

/**
 * 课程号 -> 课程名映射表。
 *
 * 仅用于让界面中单纯携带 course_id 的对象（如 changes / preferred_courses）
 * 呈现更直观的课程名，不承担业务比对或等价逻辑。
 */
const courseNameById = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}

  for (const task of data.value?.makeup_tasks ?? []) {
    map[task.course_id] = task.course_name
  }
  for (const offering of data.value?.course_offerings ?? []) {
    if (!map[offering.course_id]) {
      map[offering.course_id] = offering.course_name
    }
  }

  return map
})

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="page">
    <TopStatusBar :data-source="dataSource" />

    <!-- 业务数据流转全景步骤示意（极佳的参赛 Demo 讲解引导条） -->
    <div class="pipeline-guide">
      <div class="pipeline-step">
        <div class="pipeline-step__num">1</div>
        <div class="pipeline-step__content">
          <strong>培养方案对比</strong>
          <span>Curriculum 缺什么课</span>
        </div>
      </div>
      <div class="pipeline-arrow">➔</div>
      <div class="pipeline-step">
        <div class="pipeline-step__num">2</div>
        <div class="pipeline-step__content">
          <strong>教学班供给获取</strong>
          <span>Course Data 开了哪些班</span>
        </div>
      </div>
      <div class="pipeline-arrow">➔</div>
      <div class="pipeline-step">
        <div class="pipeline-step__num">3</div>
        <div class="pipeline-step__content">
          <strong>偏好约束注入</strong>
          <span>Agent 用户意图解析</span>
        </div>
      </div>
      <div class="pipeline-arrow">➔</div>
      <div class="pipeline-step pipeline-step--accent">
        <div class="pipeline-step__num">4</div>
        <div class="pipeline-step__content">
          <strong>课表求解与调班</strong>
          <span>Planner Path Repair</span>
        </div>
      </div>
    </div>

    <main class="page__main">
      <!--
        阶段 0：用户输入区（Frontend User Input Gate, Phase 1）

        ⚠️ 与 Mock Demo 数据完全解耦：即使 Mock 通道加载失败，用户输入区仍然可用。
        输入区自身**不产生任何业务结论**，也不调用 Mock 接口。
      -->
      <SectionCard
        section-id="section-user-input"
        title="0. 用户输入（目标学期、转专业上下文、当前课表与偏好）"
        subtitle="收集生成规划所需的用户输入：目标学期、学生转专业上下文、当前课表与个性化偏好，以及成绩单文件选择。本区块只组织输入，不做冲突检测、不生成补修任务。"
      >
        <UserInputPanel
          :form="userInput"
          :offerings="data?.course_offerings ?? []"
          :plan-api-enabled="PLAN_API_ENABLED"
          :submitting="planSubmitting"
          :mode="dataMode"
          :data-source-label="dataSource"
          :plan-error-message="planErrorMessage"
          :schedule-provenance-blocked="realPlanScheduleBlocked"
          @update:form="userInput = $event"
          @submit-real="submitRealPlan"
        />
      </SectionCard>

      <!-- 状态一：加载中 -->
      <SectionCard
        v-if="state === 'loading'"
        title="正在加载演示数据"
        subtitle="页面仅调用后端 Mock 聚合接口，不包含任何客户端预设或合成数据。"
      >
        <div class="loading-wrap">
          <div class="spinner"></div>
          <p class="state state--loading">
            正在向 <code class="mono">{{ DEMO_ENDPOINT }}</code> 发送数据请求...
          </p>
        </div>
      </SectionCard>

      <!-- 状态二：请求失败。诚实报错，严禁在前端自己合成数据顶替 -->
      <SectionCard
        v-else-if="state === 'error'"
        title="Demo 数据加载失败"
        subtitle="页面不会自动生成替代数据，也严禁展示未经后端正式响应的内容。"
        tone="attention"
      >
        <div class="error-box">
          <p class="state state--error">后端接口连接异常</p>
          <p class="state__detail">{{ errorMessage }}</p>
          <p class="state__hint">
            请检查本地 FastAPI 后端服务是否已在 8000 端口启动：<br />
            <code class="mono">cd backend &amp;&amp; python -m uvicorn app.main:app --reload</code>
          </p>
          <button class="button" type="button" @click="load">
            🔄 重新尝试连接
          </button>
        </div>
      </SectionCard>

      <!-- 状态三：加载成功 -->
      <template v-else-if="data">
        <!-- 概览状态卡片 -->
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

        <!-- 1. 历史培养要求评估（MakeupTask 的中性表述） -->
        <SectionCard
          mock
          section-id="section-makeup"
          title="1. 历史培养要求评估（MakeupTask）"
          subtitle="Curriculum 模块依据目标培养方案要求与学生已修记录逐条评估后的结果，含“已满足 / 待课程认定 / 已确认需补修”等不同状态。逐条状态以每行的判定列与认定说明为准，前端不作汇总改写。"
          :badge-count="data.makeup_tasks.length"
        >
          <MakeupTaskList :tasks="data.makeup_tasks" />
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
          <PreferencePanel
            :preference="data.preference"
            :course-name-by-id="courseNameById"
          />
        </SectionCard>

        <!--
          4. 规划结果与建议课表

          ⚠️ provenance 必须精确：
          `POST /api/v1/plan` **只返回 PlanResult**，MakeupTask / CourseOffering / Preference
          仍全部来自 Mock Demo。因此这里只把**规划结果**标成 Real，绝不把整页标成 Real。
        -->
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
            :course-name-by-id="courseNameById"
          />
        </SectionCard>
      </template>
    </main>

    <footer class="page__footer">
      <div class="footer-content">
        <p class="footer-brand">
          <strong>学航·转衔</strong> —— 面向高校转专业学生的 AI 学业路径重构 Agent 系统
        </p>
        <p class="footer-compliance">
          数据声明：基础演示数据（培养要求评估、教学班、偏好）均由后端
          <code class="mono">GET /api/v1/mock/demo</code> 通道提供。
          <template v-if="planResultMode === 'real'">
            <br />
            <strong>规划结果</strong>来自 <code class="mono">POST /api/v1/plan</code>（Real），
            但其输入中的教学班仍是上述 Mock 演示数据，因此该方案<strong>不代表真实教务系统正式指令</strong>。
          </template>
          <template v-else>
            全部课程信息、教师、教学班、学生偏好与求解方案均属<strong>演示数据</strong>，非真实教务系统正式指令。
          </template>
        </p>
      </div>
    </footer>
  </div>
</template>
