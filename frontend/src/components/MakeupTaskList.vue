<script setup lang="ts">
import { computed, ref } from 'vue'
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
const selected = ref<Set<string>>(new Set())
const evidenceOpen = ref<Set<string>>(new Set())

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

function toggleSelect(courseId: string): void {
  const next = new Set(selected.value)
  if (next.has(courseId)) next.delete(courseId)
  else next.add(courseId)
  selected.value = next
}

function toggleEvidence(courseId: string): void {
  const next = new Set(evidenceOpen.value)
  if (next.has(courseId)) next.delete(courseId)
  else next.add(courseId)
  evidenceOpen.value = next
}

function selectAll(): void {
  selected.value = new Set(selectableTasks.value.map((t) => t.course_id))
}

function clearSelection(): void {
  selected.value = new Set()
}

function submitConfirm(): void {
  const courseIds = [...selected.value].sort()
  if (courseIds.length === 0) return
  // ⛔ 提交后**不本地改状态**：结论等服务端 recompute 返回。
  emit('confirm', { courseIds })
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

    <!-- 规划确认操作区（只在有可确认项、或已有确认时出现） -->
    <section
      v-if="selectableTasks.length > 0 || confirmedKeys.length > 0"
      class="confirm-panel"
      data-testid="makeup-confirm-panel"
    >
      <p class="confirm-panel__lead" data-testid="makeup-confirm-disclosure">
        勾选后可标记为<strong>本次规划按已满足处理</strong>：
        {{ disclosureText.basis }}、{{ disclosureText.scope }}；{{ disclosureText.authority }}。
      </p>

      <div v-if="selectableTasks.length > 0" class="confirm-panel__actions">
        <button
          type="button"
          class="button button--small button--ghost"
          data-testid="makeup-select-all"
          @click="selectAll"
        >
          全选可确认项
        </button>
        <button
          type="button"
          class="button button--small button--ghost"
          :disabled="selected.size === 0"
          data-testid="makeup-clear-selection"
          @click="clearSelection"
        >
          清空选择
        </button>
        <button
          type="button"
          class="button button--small"
          :disabled="selected.size === 0 || pending"
          data-testid="makeup-confirm-submit"
          :aria-busy="pending"
          @click="submitConfirm"
        >
          {{ pending ? '正在重新规划…' : `确认所选并重新规划（${selected.size}）` }}
        </button>
      </div>

      <div v-if="confirmedKeys.length > 0" class="confirm-panel__confirmed">
        <p class="confirm-panel__confirmed-title" data-testid="makeup-confirmed-title">
          本次规划已确认满足（{{ confirmedKeys.length }} 项）—— {{ disclosureText.basis }}、
          {{ disclosureText.scope }}；{{ disclosureText.authority }}
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
              @click="emit('undo', { courseId: key })"
            >
              撤销确认
            </button>
          </li>
        </ul>
      </div>
    </section>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th scope="col" style="width: 34px;">选择</th>
            <th scope="col" style="width: 220px;">课程名称与编号</th>
            <th scope="col" style="width: 70px;">学分</th>
            <th scope="col" style="width: 190px;">判定状态</th>
            <th scope="col" style="width: 130px;">学期建议</th>
            <th scope="col" style="width: 120px;">先修依赖</th>
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
            <td>
              <input
                v-if="row.task.status === 'manual_confirmation' && !row.confirmedByUser"
                type="checkbox"
                :checked="selected.has(row.task.course_id)"
                :data-testid="`makeup-select-${row.task.course_id}`"
                :aria-label="`确认 ${row.task.course_name}`"
                @change="toggleSelect(row.task.course_id)"
              />
              <span v-else class="text-muted">—</span>
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
