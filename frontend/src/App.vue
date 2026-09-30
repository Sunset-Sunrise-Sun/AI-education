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

const { state, data, dataSource, errorMessage, load } = useDemoData()

/**
 * 课程号 -> 课程名。
 *
 * 纯粹为了让 changes / selected_classes 里的课程号更好读（它们只带 course_id）。
 * 这里**不做**任何比对、等价判定、优劣判断或结论推导。
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

    <main class="page__main">
      <!-- 状态一：加载中 -->
      <SectionCard
        v-if="state === 'loading'"
        title="正在加载 Demo 数据"
        subtitle="页面只会调用后端 Mock 通道的聚合接口，不做任何本地计算。"
      >
        <p class="state state--loading">
          正在请求 <code class="mono">{{ DEMO_ENDPOINT }}</code> …
        </p>
      </SectionCard>

      <!-- 状态二：请求失败。诚实报错，绝不自己造一份数据继续展示。 -->
      <SectionCard
        v-else-if="state === 'error'"
        title="Demo 数据加载失败"
        subtitle="页面不会生成替代数据，也不会展示任何未经后端返回的内容。"
        tone="attention"
      >
        <p class="state state--error">Demo 数据加载失败</p>
        <p class="state__detail">{{ errorMessage }}</p>
        <p class="state__hint">
          请确认后端已启动：
          <code class="mono">cd backend &amp;&amp; python -m uvicorn app.main:app --reload</code>
        </p>
        <button class="button" type="button" @click="load">重新加载</button>
      </SectionCard>

      <!-- 状态三：加载成功。
           四个展示组件分别放进 SectionCard，形成四个明确区域：
           补修任务 / 教学班 / 用户偏好 / 最终方案。
           数据全部来自后端 Mock 通道，所以每个区域都带 Mock 标记（SectionCard 的 mock 默认为 true，
           这里显式写出，便于阅读时确认标记确实存在）。 -->
      <template v-else-if="data">
        <SectionCard
          mock
          title="补修任务"
          subtitle="Curriculum 模块本应输出的 MakeupTask：转专业后需要补什么。"
        >
          <MakeupTaskList :tasks="data.makeup_tasks" />
        </SectionCard>

        <SectionCard
          mock
          title="教学班"
          subtitle="Course Data 模块本应输出的 CourseOffering：这些课现实中开了哪些班。"
        >
          <CourseOfferingList :offerings="data.course_offerings" />
        </SectionCard>

        <SectionCard
          mock
          title="用户偏好"
          subtitle="Agent 解析后本应产出的 Preference：学分上限与需要避开的时段。"
        >
          <PreferencePanel :preference="data.preference" />
        </SectionCard>

        <SectionCard
          mock
          title="最终方案"
          subtitle="Planner 模块本应输出的 PlanResult：换了哪些班、有哪些风险、还有什么没解决。"
        >
          <PlanResultPanel
            :plan-result="data.plan_result"
            :course-name-by-id="courseNameById"
          />
        </SectionCard>
      </template>
    </main>

    <footer class="page__footer">
      <p>
        本页全部数据来自后端 Mock 通道 <code class="mono">GET /api/v1/mock/demo</code>，
        为人工虚构的演示数据，<strong>不是真实教务数据</strong>。
      </p>
      <p>补修任务 · 教学班 · 用户偏好 · 最终方案（含 changes / risks / unresolved）</p>
    </footer>
  </div>
</template>
