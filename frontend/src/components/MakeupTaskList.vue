<script setup lang="ts">
import { computed, ref } from 'vue'
import { studentText } from '../utils/displayLanguage'
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
  compactConfirmations?: boolean
  /**
   * 已确认的课程键（与「推荐方案」共用同一份状态）。
   *
   * ⚠️ 产品流程合并：需要确认的课程**在本表直接勾选**，不再要求用户去推荐方案里找同一动作。
   *   键格式与 `PlanResultPanel` 完全一致（`course:<courseId>`），因此两处显示同一份确认状态。
   *   ⛔ 确认只表示「用户已核对该课程」，⛔ 不代表系统自动认定已修读或已满足要求。
   */
  confirmedKeys?: readonly string[]
}>()

const emit = defineEmits<{
  'update:confirmedKeys': [keys: string[]]
}>()

/** 与 `PlanResultPanel` 一致的确认键。 */
function taskKey(task: MakeupTask): string {
  return `course:${task.course_id}`
}

const selected = ref<string[]>([])
const localConfirmedKeys = ref<string[]>([])

/** 父级未受控时退回本地状态（向后兼容既有用法与测试）。 */
const effectiveConfirmedKeys = computed(() => props.confirmedKeys ?? localConfirmedKeys.value)
const confirmedSet = computed(() => new Set(effectiveConfirmedKeys.value))

const confirmableTasks = computed(() =>
  visibleTasks.value.filter((task) => task.status === 'manual_confirmation'),
)
const hasConfirmableTasks = computed(() => confirmableTasks.value.length > 0)
const confirmedCount = computed(
  () => confirmableTasks.value.filter((task) => confirmedSet.value.has(taskKey(task))).length,
)

/** 用户主动确认：只记录「已核对」，⛔ 不改判定状态、⛔ 不自动认定。 */
function confirmSelection(): void {
  const next = [...new Set([...effectiveConfirmedKeys.value, ...selected.value])]
  if (props.confirmedKeys === undefined) {
    localConfirmedKeys.value = next
  }
  emit('update:confirmedKeys', next)
  selected.value = []
}

const visibleTasks = computed(() => props.tasks)

const activeFilter = ref<'all' | MakeupStatus>('all')

const stats = computed(() => {
  const counts: Record<MakeupStatus, number> = {
    required: 0,
    possibly_equivalent: 0,
    manual_confirmation: 0,
    satisfied: 0,
  }
  for (const t of visibleTasks.value) {
    if (counts[t.status] !== undefined) {
      counts[t.status]++
    }
  }
  return counts
})

const filteredTasks = computed(() => {
  if (activeFilter.value === 'all') {
    return visibleTasks.value
  }
  return visibleTasks.value.filter((t) => t.status === activeFilter.value)
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
          全部任务 ({{ visibleTasks.length }})
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
          v-if="!compactConfirmations"
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

    <!--
      ⚠️ 产品流程合并：需要确认的课程**直接在这里勾选确认**，
         不再让用户跳到「推荐方案」里找同一个动作（此前两处重复、用户不清楚区别）。
    -->
    <p v-if="hasConfirmableTasks" class="section-desc">
      下列课程需要你核对。<strong>勾选后点「确认选择」</strong>：确认只表示你已核对该课程，
      系统不会因此自动认定你已修读或已满足培养要求。
    </p>
    <!-- 任务表格 -->
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th scope="col" style="width: 220px;">课程名称与编号</th>
            <th scope="col" style="width: 70px;">学分</th>
            <th scope="col" style="width: 170px;">判定状态</th>
            <th scope="col" style="width: 200px;">需要你确认</th>
            <th scope="col" style="width: 130px;">学期建议</th>
            <th scope="col" style="width: 130px;">先修依赖</th>
            <th scope="col">课程说明</th>
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
                <span v-if="!compactConfirmations || task.status !== 'manual_confirmation'" class="cell-hint">{{ MAKEUP_STATUS_HINT[task.status] }}</span>
              </div>
            </td>
            <!-- 需要确认列：仅 `manual_confirmation` 任务可勾选，其余留空 -->
            <td class="cell-confirm">
              <template v-if="task.status === 'manual_confirmation'">
                <span
                  v-if="confirmedSet.has(taskKey(task))"
                  class="task-confirm__done"
                  data-testid="case-a-makeup-confirmed"
                >
                  已确认
                </span>
                <label v-else class="task-confirm__label">
                  <input
                    v-model="selected"
                    type="checkbox"
                    :value="taskKey(task)"
                    :aria-label="`确认核对 ${task.course_name}`"
                    data-testid="case-a-makeup-checkbox"
                  />
                  <span>需要确认</span>
                </label>
              </template>
              <span v-else class="text-muted">—</span>
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
              <!--
                ⚠️ 产品流程合并：不再提示「请到推荐方案核对」——
                   确认动作就在本表「需要你确认」列里完成。
              -->
              <p class="reason-text">{{ studentText(task.reason, MAKEUP_STATUS_HINT[task.status]) }}</p>
              <details v-if="studentText(task.source_evidence)">
                <summary>查看详情</summary>
                <p>系统判断依据：{{ studentText(task.source_evidence) }}</p>
              </details>
            </td>
          </tr>
          <tr v-if="filteredTasks.length === 0">
            <td colspan="7" class="empty-state">
              <p>暂无符合当前筛选条件的补修任务。</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 确认动作：与「推荐方案」共用同一份确认状态 -->
    <div v-if="hasConfirmableTasks" class="task-confirm-footer">
      <span role="status" aria-live="polite" data-testid="case-a-makeup-confirm-count">
        已选择 {{ selected.length }} 项 · 已确认 {{ confirmedCount }} / {{ confirmableTasks.length }} 项
      </span>
      <button
        class="button"
        type="button"
        :disabled="!selected.length"
        data-testid="case-a-makeup-confirm-selection"
        @click="confirmSelection"
      >
        确认选择
      </button>
      <span class="task-confirm-note">
        确认只表示你已核对这些课程，系统<strong>不会</strong>因此自动认定你已修读或已满足培养要求。
      </span>
    </div>
  </div>
</template>
