<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MakeupStatus, MakeupTask } from '../types/contracts'
import {
  MAKEUP_STATUS_HINT,
  MAKEUP_STATUS_LABEL,
  displayOrDash,
} from '../utils/labels'

/**
 * 展示 Curriculum 模块输出的补修任务（MakeupTask）。
 *
 * 核心设计边界：
 * - 原样呈现课程学分、建议学期、截止学期、先修关系与认定依据；
 * - 前端不做补修判定，不推断课程等价关系；
 * - 提供友好的状态过滤与统计便于 Demo 演示交流。
 */
const props = defineProps<{
  tasks: MakeupTask[]
}>()

const activeFilter = ref<'all' | MakeupStatus>('all')

const stats = computed(() => {
  const counts: Record<MakeupStatus, number> = {
    required: 0,
    possibly_equivalent: 0,
    manual_confirmation: 0,
    satisfied: 0,
  }
  for (const t of props.tasks) {
    if (counts[t.status] !== undefined) {
      counts[t.status]++
    }
  }
  return counts
})

const filteredTasks = computed(() => {
  if (activeFilter.value === 'all') {
    return props.tasks
  }
  return props.tasks.filter((t) => t.status === activeFilter.value)
})
</script>

<template>
  <div class="makeup-container">
    <!-- 统计与过滤栏 -->
    <div class="section-toolbar">
      <div class="stats-pills">
        <button
          type="button"
          class="filter-chip"
          :class="{ 'filter-chip--active': activeFilter === 'all' }"
          @click="activeFilter = 'all'"
        >
          全部任务 ({{ tasks.length }})
        </button>
        <button
          type="button"
          class="filter-chip filter-chip--required"
          :class="{ 'filter-chip--active': activeFilter === 'required' }"
          @click="activeFilter = 'required'"
        >
          需要补修 ({{ stats.required }})
        </button>
        <button
          type="button"
          class="filter-chip filter-chip--manual"
          :class="{ 'filter-chip--active': activeFilter === 'manual_confirmation' }"
          @click="activeFilter = 'manual_confirmation'"
        >
          待人工确认 ({{ stats.manual_confirmation }})
        </button>
        <button
          v-if="stats.possibly_equivalent > 0"
          type="button"
          class="filter-chip filter-chip--equivalent"
          :class="{ 'filter-chip--active': activeFilter === 'possibly_equivalent' }"
          @click="activeFilter = 'possibly_equivalent'"
        >
          可能等价 ({{ stats.possibly_equivalent }})
        </button>
        <button
          v-if="stats.satisfied > 0"
          type="button"
          class="filter-chip filter-chip--satisfied"
          :class="{ 'filter-chip--active': activeFilter === 'satisfied' }"
          @click="activeFilter = 'satisfied'"
        >
          已满足 ({{ stats.satisfied }})
        </button>
      </div>
    </div>

    <!-- 任务表格 -->
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th scope="col" style="width: 220px;">课程名称与编号</th>
            <th scope="col" style="width: 70px;">学分</th>
            <th scope="col" style="width: 170px;">判定状态</th>
            <th scope="col" style="width: 130px;">学期建议</th>
            <th scope="col" style="width: 130px;">先修依赖</th>
            <th scope="col">认定说明与证据</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in filteredTasks" :key="task.course_id" class="task-row">
            <td>
              <div class="course-cell">
                <span class="cell-strong">{{ task.course_name }}</span>
                <span class="mono cell-sub-id">{{ task.course_id }}</span>
              </div>
            </td>
            <td class="num cell-credit">
              <strong>{{ task.credit }}</strong>
            </td>
            <td>
              <div class="status-cell">
                <span class="tag" :class="`tag--status-${task.status}`">
                  {{ MAKEUP_STATUS_LABEL[task.status] }}
                </span>
                <span class="cell-hint">{{ MAKEUP_STATUS_HINT[task.status] }}</span>
              </div>
            </td>
            <td>
              <div class="semester-cell">
                <span v-if="task.recommended_semester">
                  建议第 <strong>{{ task.recommended_semester }}</strong> 学期
                </span>
                <span v-else class="text-muted">—</span>
                <span v-if="task.deadline_semester" class="deadline-hint">
                  (最迟第 {{ task.deadline_semester }} 学期)
                </span>
              </div>
            </td>
            <td>
              <div v-if="task.prerequisites && task.prerequisites.length > 0" class="prereq-list">
                <span
                  v-for="prereq in task.prerequisites"
                  :key="prereq"
                  class="chip chip--prereq mono"
                  title="先修课程"
                >
                  {{ prereq }}
                </span>
              </div>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="cell-reason">
              <p class="reason-text">{{ displayOrDash(task.reason) }}</p>
              <p v-if="task.source_evidence" class="evidence-text">
                <span class="evidence-icon">📋 依据：</span>
                {{ task.source_evidence }}
              </p>
            </td>
          </tr>
          <tr v-if="filteredTasks.length === 0">
            <td colspan="6" class="empty-state">
              <p>暂无符合当前筛选条件的补修任务。</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
