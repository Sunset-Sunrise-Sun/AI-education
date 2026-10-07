<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { MakeupStatus, MakeupTask } from '../types/contracts'
import type { PlanningOnlyDisclosure } from '../api/caseADemo'
import {
  MAKEUP_STATUS_HINT,
  MAKEUP_STATUS_LABEL,
  displayOrDash,
} from '../utils/labels'

/**
 * 补修缺口分析 —— 含**规划确认**交互。
 *
 * 核心边界（与独立 Review 结论一致）：
 *
 * - 表格主体永远展示**来源可核验的基础评估**（12 satisfied / 11 manual_confirmation）；
 *   ⛔ 用户确认**不会**改写它，也不会把 `manual_confirmation` 变成官方认定；
 * - 用户勾选后只是提交一个 **run-local 的规划意图**（`course_id`），
 *   由页面走同一条 recompute 管线重算；
 * - 已确认的项在下方「本次规划已确认满足」区域展示，并**同时**给出三项披露：
 *   基于你的确认 / 仅用于本次规划 / 不是学校官方认定结果；
 * - `撤销确认` 只是移除该 key 并重新规划，⛔ 不产生"官方已满足"的副作用；
 * - 计数为 0 的筛选按钮**不渲染**（例如没有任何「需要补修」时不显示该 tab）。
 */
const props = withDefaults(
  defineProps<{
    /** 来源可核验的基础评估（⛔ 前端不修改它）。 */
    tasks: MakeupTask[]
    /** 本轮实际生效的规划确认（精确 `course_id`）。 */
    confirmedKeys?: string[]
    /** 三项披露文案（由服务端提供，保证措辞一致）。 */
    disclosure?: PlanningOnlyDisclosure | null
    /** 正在重算（禁用交互，⛔ 不做乐观更新）。 */
    pending?: boolean
  }>(),
  { confirmedKeys: () => [], disclosure: null, pending: false },
)

const emit = defineEmits<{
  /** 提交新的确认集合（⛔ 只提交意图，结论由服务端重算）。 */
  (event: 'confirm', payload: { courseIds: string[] }): void
  /** 撤销一条确认（同样触发重算）。 */
  (event: 'undo', payload: { courseId: string }): void
}>()

const activeFilter = ref<'all' | MakeupStatus>('all')
const evidenceOpen = ref<Set<string>>(new Set())
/** 当前正在提交的单行操作，只用于即时 pending 文案。 */
const activeCourseId = ref<string | null>(null)

watch(
  () => props.pending,
  (pending, wasPending) => {
    if (wasPending && !pending) activeCourseId.value = null
  },
)

const DEFAULT_DISCLOSURE: PlanningOnlyDisclosure = {
  basis: '基于你的确认',
  scope: '仅用于本次规划',
  authority: '不是学校官方认定结果',
}
const disclosureText = computed(() => props.disclosure ?? DEFAULT_DISCLOSURE)

const confirmedSet = computed(() => new Set(props.confirmedKeys))

const stats = computed(() => {
  const counts: Record<MakeupStatus, number> = {
    required: 0,
    possibly_equivalent: 0,
    manual_confirmation: 0,
    satisfied: 0,
  }
  for (const t of props.tasks) {
    if (counts[t.status] !== undefined) counts[t.status]++
  }
  return counts
})

/** 可勾选的项：只有**未确认的** `manual_confirmation`。 */
const selectableTasks = computed(() =>
  props.tasks.filter(
    (t) => t.status === 'manual_confirmation' && !confirmedSet.value.has(t.course_id),
  ),
)

/**
 * 表格行 = 基础评估 + 本轮确认状态。
 *
 * ⚠️ 被确认的项在**本次规划**里按已满足呈现，但会带上"基于你的确认"标记，
 *    与来源可核验的 `satisfied` 在视觉上区分开，⛔ 不混为一谈。
 */
interface Row {
  task: MakeupTask
  confirmedByUser: boolean
  displayStatus: MakeupStatus
}

const rows = computed<Row[]>(() =>
  props.tasks.map((task) => {
    const confirmedByUser = confirmedSet.value.has(task.course_id)
    return {
      task,
      confirmedByUser,
      displayStatus: confirmedByUser ? 'satisfied' : task.status,
    }
  }),
)

const filteredRows = computed(() => {
  if (activeFilter.value === 'all') return rows.value
  return rows.value.filter((row) => row.displayStatus === activeFilter.value)
})

/** 按显示状态计数（确认后从"待人工确认"移到"已满足"）。 */
const displayStats = computed(() => {
  const counts: Record<MakeupStatus, number> = {
    required: 0,
    possibly_equivalent: 0,
    manual_confirmation: 0,
    satisfied: 0,
  }
  for (const row of rows.value) counts[row.displayStatus]++
  return counts
})

function toggleEvidence(courseId: string): void {
  const next = new Set(evidenceOpen.value)
  if (next.has(courseId)) next.delete(courseId)
  else next.add(courseId)
  evidenceOpen.value = next
}

/**
 * 单项确认（"确认可转换"）。
 *
 * ⚠️ 提交的是**完整期望状态**（已有确认 + 本项），与服务端"整体采用"的语义一致。
 * ⛔ 提交后不本地改状态：结论等服务端 recompute 返回。
 */
function confirmOne(courseId: string): void {
  activeCourseId.value = courseId
  emit('confirm', { courseIds: [...new Set([...props.confirmedKeys, courseId])].sort() })
}

/** 单项撤销（"撤销确认"）：从完整期望状态里移除本项。 */
function undoOne(courseId: string): void {
  activeCourseId.value = courseId
  emit('undo', { courseId })
}

function toggleConfirmation(row: Row): void {
  if (row.confirmedByUser) undoOne(row.task.course_id)
  else confirmOne(row.task.course_id)
}

function confirmationLabel(row: Row): string {
  if (props.pending && activeCourseId.value === row.task.course_id) {
    return row.confirmedByUser ? '正在撤销…' : '确认中…'
  }
  return row.confirmedByUser ? '✓ 已确认' : '确认可转换'
}
</script>

<template>
  <div class="makeup-container">
    <div class="section-toolbar">
      <div class="stats-pills">
        <!-- "全部任务"是**导航**入口：只要还有任务就必须保留，
             ⛔ 不要因为它没有专属状态就跟着计数隐藏。 -->
        <button
          type="button"
          class="filter-chip"
          :class="{ 'filter-chip--active': activeFilter === 'all' }"
          data-testid="makeup-filter-all"
          @click="activeFilter = 'all'"
        >
          全部任务 ({{ tasks.length }})
        </button>
        <!-- ⛔ 计数为 0 的**状态**筛选不渲染（避免出现永远为空的 tab） -->
        <button
          v-if="displayStats.required > 0"
          type="button"
          class="filter-chip filter-chip--required"
          :class="{ 'filter-chip--active': activeFilter === 'required' }"
          data-testid="makeup-filter-required"
          @click="activeFilter = 'required'"
        >
          需要补修 ({{ displayStats.required }})
        </button>
        <button
          v-if="displayStats.manual_confirmation > 0"
          type="button"
          class="filter-chip filter-chip--manual"
          :class="{ 'filter-chip--active': activeFilter === 'manual_confirmation' }"
          data-testid="makeup-filter-manual"
          @click="activeFilter = 'manual_confirmation'"
        >
          待人工确认 ({{ displayStats.manual_confirmation }})
        </button>
        <button
          v-if="displayStats.possibly_equivalent > 0"
          type="button"
          class="filter-chip filter-chip--equivalent"
          :class="{ 'filter-chip--active': activeFilter === 'possibly_equivalent' }"
          @click="activeFilter = 'possibly_equivalent'"
        >
          可能等价 ({{ displayStats.possibly_equivalent }})
        </button>
        <button
          v-if="displayStats.satisfied > 0"
          type="button"
          class="filter-chip filter-chip--satisfied"
          :class="{ 'filter-chip--active': activeFilter === 'satisfied' }"
          data-testid="makeup-filter-satisfied"
          @click="activeFilter = 'satisfied'"
        >
          已满足 ({{ displayStats.satisfied }})
        </button>
      </div>
    </div>

    <!-- 披露（⛔ 每次出现都必须完整口径） -->
    <p
      v-if="selectableTasks.length > 0 || confirmedKeys.length > 0"
      class="confirm-panel__lead"
      data-testid="makeup-confirm-disclosure"
    >
      下表「待人工确认」项可逐条选择<strong>确认可转换</strong>（{{ disclosureText.basis }}、{{
        disclosureText.scope
      }}；{{ disclosureText.authority }}，也<strong>不会修改学校教务系统记录</strong>）。
    </p>

    <div v-if="confirmedKeys.length > 0" class="confirm-panel__confirmed">
      <p class="confirm-panel__confirmed-title" data-testid="makeup-confirmed-title">
        已按你的确认移入「已满足」（{{ confirmedKeys.length }} 项）—— {{ disclosureText.basis }}、{{
          disclosureText.scope
        }}；{{ disclosureText.authority }}
      </p>
      <ul class="confirm-panel__list">
        <li
          v-for="key in confirmedKeys"
          :key="key"
          class="confirm-panel__item"
          data-testid="makeup-confirmed-item"
        >
          <span class="mono">{{ key }}</span>
          <span class="confirm-panel__badge">{{ disclosureText.basis }}</span>
          <button
            type="button"
            class="button button--small button--ghost"
            :disabled="pending"
            :data-testid="`makeup-undo-${key}`"
            @click="undoOne(key)"
          >
            撤销确认
          </button>
        </li>
      </ul>
    </div>

    <div class="table-wrap makeup-table-wrap">
      <table class="table makeup-task-table" data-testid="makeup-task-table">
        <colgroup>
          <col class="makeup-col makeup-col--action" />
          <col class="makeup-col makeup-col--course" />
          <col class="makeup-col makeup-col--credit" />
          <col class="makeup-col makeup-col--status" />
          <col class="makeup-col makeup-col--semester" />
          <col class="makeup-col makeup-col--prerequisite" />
          <col class="makeup-col makeup-col--reason" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">本次规划操作</th>
            <th scope="col">课程名称与编号</th>
            <th scope="col">学分</th>
            <th scope="col">判定状态</th>
            <th scope="col">学期建议</th>
            <th scope="col">先修依赖</th>
            <th scope="col">认定说明与证据</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRows"
            :key="row.task.course_id"
            class="task-row"
            :data-testid="`makeup-row-${row.task.course_id}`"
          >
            <td class="makeup-actions-cell">
              <div
                class="makeup-action-region"
                :data-testid="`makeup-action-region-${row.task.course_id}`"
              >
                <!-- 单一主操作：成功态仍由服务端 confirmedKeys 决定，同一按钮可撤销。 -->
                <button
                  v-if="row.task.status === 'manual_confirmation'"
                  type="button"
                  class="button button--small makeup-confirm-toggle"
                  :class="{ 'makeup-confirm-toggle--confirmed': row.confirmedByUser }"
                  :disabled="pending"
                  :aria-pressed="row.confirmedByUser"
                  :data-testid="row.confirmedByUser
                    ? `makeup-undo-${row.task.course_id}`
                    : `makeup-confirm-${row.task.course_id}`"
                  @click="toggleConfirmation(row)"
                >
                  {{ confirmationLabel(row) }}
                </button>
                <span v-else class="text-muted">—</span>
              </div>
            </td>
            <td>
              <div class="course-cell">
                <span class="cell-strong">{{ row.task.course_name }}</span>
                <span class="mono cell-sub-id">{{ row.task.course_id }}</span>
              </div>
            </td>
            <td class="num cell-credit">
              <strong>{{ row.task.credit }}</strong>
            </td>
            <td>
              <div class="status-cell">
                <span class="tag" :class="`tag--status-${row.displayStatus}`">
                  {{ MAKEUP_STATUS_LABEL[row.displayStatus] }}
                </span>
                <span
                  v-if="row.confirmedByUser"
                  class="tag tag--user-confirmed"
                  :data-testid="`makeup-user-confirmed-${row.task.course_id}`"
                >
                  {{ disclosureText.basis }}
                </span>
                <span v-else class="cell-hint">{{ MAKEUP_STATUS_HINT[row.displayStatus] }}</span>
              </div>
            </td>
            <td>
              <div class="semester-cell">
                <span v-if="row.task.recommended_semester">
                  建议第 <strong>{{ row.task.recommended_semester }}</strong> 学期
                </span>
                <span v-else class="text-muted">—</span>
                <span v-if="row.task.deadline_semester" class="deadline-hint">
                  (最迟第 {{ row.task.deadline_semester }} 学期)
                </span>
              </div>
            </td>
            <td>
              <div v-if="row.task.prerequisites && row.task.prerequisites.length > 0" class="prereq-list">
                <span
                  v-for="prereq in row.task.prerequisites"
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
              <p class="reason-text">{{ displayOrDash(row.task.reason) }}</p>
              <!-- 依据默认折叠：主界面只给入口，⛔ 不把长证据铺开 -->
              <button
                v-if="row.task.source_evidence"
                type="button"
                class="evidence-toggle"
                :data-testid="`makeup-evidence-${row.task.course_id}`"
                @click="toggleEvidence(row.task.course_id)"
              >
                {{ evidenceOpen.has(row.task.course_id) ? '收起依据' : '查看依据' }}
              </button>
              <p
                v-if="row.task.source_evidence && evidenceOpen.has(row.task.course_id)"
                class="evidence-text"
                :data-testid="`makeup-evidence-body-${row.task.course_id}`"
              >
                {{ row.task.source_evidence }}
              </p>
            </td>
          </tr>
          <tr v-if="filteredRows.length === 0">
            <td colspan="7" class="empty-state">
              <p>暂无符合当前筛选条件的补修任务。</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ⛔ 来源可核验的基础评估：必须始终如实说明它没有被用户确认改写 -->
    <p class="makeup-source-note" data-testid="makeup-source-note">
      上表「已满足 / 待人工确认」来自培养方案与已确认的已修事实（来源可核验），
      ⛔ 你的规划确认不会修改这份评估，也不会变成学校的官方认定。
    </p>

    <!-- 错误/拒绝反馈（服务端拒绝的确认项如实展示） -->
    <ul v-if="$slots.rejections" class="makeup-rejections">
      <slot name="rejections" />
    </ul>
  </div>
</template>

<style scoped>
.makeup-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.confirm-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: var(--radius);
}

.confirm-panel__lead,
.confirm-panel__confirmed-title,
.makeup-source-note {
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
  color: #475569;
}

.confirm-panel__lead strong {
  color: #b45309;
}

.confirm-panel__confirmed-title {
  font-weight: 700;
  color: #166534;
}

.confirm-panel__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.confirm-panel__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}

.confirm-panel__item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}

.confirm-panel__badge {
  padding: 1px 6px;
  font-size: 11px;
  color: #166534;
  background: #dcfce7;
  border-radius: 999px;
}

.makeup-table-wrap {
  border-radius: var(--radius);
}

.makeup-task-table {
  min-width: 1160px;
  table-layout: fixed;
}

.makeup-col--action { width: 160px; }
.makeup-col--course { width: 205px; }
.makeup-col--credit { width: 70px; }
.makeup-col--status { width: 180px; }
.makeup-col--semester { width: 135px; }
.makeup-col--prerequisite { width: 120px; }
.makeup-col--reason { width: 290px; }

.makeup-task-table th,
.makeup-task-table td {
  box-sizing: border-box;
}

.makeup-task-table tbody tr {
  border-bottom: 1px solid var(--border);
}

.makeup-task-table tbody tr:last-child {
  border-bottom: 0;
}

.makeup-task-table tbody td {
  height: 72px;
  border-bottom: 0;
  vertical-align: middle;
}

.makeup-action-region {
  display: flex;
  min-height: 34px;
  align-items: flex-start;
  justify-content: center;
  flex-direction: column;
}

.makeup-confirm-toggle {
  width: 124px;
  justify-content: center;
}

.makeup-confirm-toggle--confirmed {
  color: #166534;
  background: #dcfce7;
  border-color: #86efac;
  box-shadow: inset 0 0 0 1px #bbf7d0;
}

.tag--user-confirmed {
  color: #166534;
  background: #dcfce7;
  border-color: #86efac;
}

.evidence-toggle {
  margin-top: 4px;
  padding: 0;
  color: #2563eb;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
}

.evidence-text {
  margin: 4px 0 0;
  font-size: 12px;
  color: #64748b;
  overflow-wrap: anywhere;
}

.makeup-source-note {
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.makeup-rejections {
  margin: 0;
  padding-left: 18px;
  color: #b45309;
  font-size: 12px;
}
</style>
