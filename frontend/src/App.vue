<script setup lang="ts">
import { computed, onMounted } from 'vue'
import CourseOfferingList from './components/CourseOfferingList.vue'
import MakeupTaskList from './components/MakeupTaskList.vue'
import PlanResultPanel from './components/PlanResultPanel.vue'
import PreferencePanel from './components/PreferencePanel.vue'
import SectionCard from './components/SectionCard.vue'
import TopStatusBar from './components/TopStatusBar.vue'
import { useDemoData } from './composables/useDemoData'
import { DEMO_ENDPOINT } from './config'
import { PLAN_STATUS_LABEL } from './utils/labels'

const { state, data, dataSource, errorMessage, load } = useDemoData()

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
            <span class="overview-metric__label">识别补修任务</span>
            <span class="overview-metric__val num">{{ data.makeup_tasks.length }} <small>门</small></span>
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
              class="tag tag--plan"
              :class="`tag--plan-${data.plan_result.status}`"
            >
              {{ PLAN_STATUS_LABEL[data.plan_result.status] }}
            </span>
          </div>
        </div>

        <!-- 1. 补修任务 -->
        <SectionCard
          mock
          section-id="section-makeup"
          title="1. 补修任务清单 (MakeupTask)"
          subtitle="Curriculum 模块根据新旧培养方案与已修成绩单差分所得：转入新专业后需要补修的课程与学分。"
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

        <!-- 4. 重构方案与求解结果 -->
        <SectionCard
          mock
          section-id="section-plan"
          tone="primary"
          title="4. 规划结果与建议课表 (PlanResult)"
          subtitle="展示 Planner 输出的 PlanResult：包含建议课表、方案变更、风险项与未决事项；前端不补充业务判断。"
        >
          <PlanResultPanel
            :plan-result="data.plan_result"
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
          数据声明：当前页面所有数据均由后端 <code class="mono">GET /api/v1/mock/demo</code> 通道提供。
          全部课程信息、教师、教学班、学生偏好与求解方案均属<strong>演示数据</strong>，非真实教务系统正式指令。
        </p>
      </div>
    </footer>
  </div>
</template>
