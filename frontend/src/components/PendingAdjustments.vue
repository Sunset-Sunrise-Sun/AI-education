<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RepairProposal, RepairProposalSet } from '../types/caseAPlanning'
import type { CourseOffering, PlanResult } from '../types/contracts'
import {
  EMPTY_MEETINGS_DATA_TEXT,
  displayOrDash,
  formatMeetingLine,
} from '../utils/labels'

/**
 * 待你确认的调整。
 *
 * 数据来源与边界（⛔ 不得越界）：
 *
 * - **结构化换班建议**来自后端 `repair_proposals`；本组件**不做**任何换班算法；
 * - ⛔ 不从 `plan_result.unresolved[].message` / `reason` 里解析 `class_id` 等业务字段：
 *   身份一律取自结构化字段（`course_id` / `current_class_id` / `candidate_class_id`）；
 * - ⛔ 生成建议**不等于**应用建议：只有用户点击「采用调整」才会 emit `apply`，
 *   由页面调用后端 repair apply 接口；
 * - ⛔ 本组件不修改 `current_schedule`，也不自行判定替换是否成功；
 * - 「暂不调整」只是**本地视图**收起（⛔ 不改后端状态、⛔ 不删建议）。
 */
const props = withDefaults(
  defineProps<{
    planResult: PlanResult | null
    /** ⛔ 缺失时视为"后端未提供结构化候选" ⇒ 不显示任何「采用调整」按钮。 */
    repairProposals?: RepairProposalSet | null
    courseNameById: Record<string, string>
    /** 已接受的教学班（用于按 identity join 出时间 / 校区 / 教室 / 教师）。 */
    offerings?: CourseOffering[]
    /** 正在提交某条建议（按钮禁用，⛔ 不乐观更新）。 */
    applying?: boolean
  }>(),
  { repairProposals: null, offerings: () => [], applying: false },
)

const emit = defineEmits<{
  (
    event: 'apply',
    payload: { semester: string; courseId: string; fromClassId: string; toClassId: string },
  ): void
}>()

const SELECTION_REQUIRED_TITLE = '发现可调整的教学班'
const SELECTION_REQUIRED_BODY =
  '系统找到了其他无时间冲突的教学班，当前版本需要你确认后才能调整。'

/** 用户本地"暂不调整"的建议 id（纯视图状态）。 */
const dismissed = ref<Set<string>>(new Set())

function dismiss(proposalId: string): void {
  const next = new Set(dismissed.value)
  next.add(proposalId)
  dismissed.value = next
}

const changes = computed(() => props.planResult?.changes ?? [])

const allProposals = computed<RepairProposal[]>(() => props.repairProposals?.proposals ?? [])
const visibleProposals = computed(() =>
  allProposals.value.filter((item) => !dismissed.value.has(item.proposal_id)),
)

const selectionRequired = computed(
  () => (props.planResult?.unresolved ?? []).filter((item) => item.type === 'selection_required'),
)

const otherUnresolved = computed(
  () => (props.planResult?.unresolved ?? []).filter((item) => item.type !== 'selection_required'),
)

const proposalUnresolved = computed(() => props.repairProposals?.unresolved ?? [])

/**
 * 只有**没有**任何结构化候选时，才退回"只有提示、没有候选"的说明。
 * ⛔ 这**不是**失败：它表示当前输入里没有可确认无冲突的候选。
 */
const showSelectionNotice = computed(
  () => allProposals.value.length === 0 && selectionRequired.value.length > 0,
)

const hasAnything = computed(
  () =>
    changes.value.length > 0 ||
    visibleProposals.value.length > 0 ||
    showSelectionNotice.value ||
    proposalUnresolved.value.length > 0 ||
    otherUnresolved.value.length > 0,
)

const offeringByKey = computed(() => {
  const map = new Map<string, CourseOffering>()
  for (const item of props.offerings) {
    map.set(`${item.semester}::${item.course_id}::${item.class_id}`, item)
  }
  return map
})

function offeringOf(proposal: RepairProposal, classId: string): CourseOffering | null {
  return offeringByKey.value.get(`${proposal.semester}::${proposal.course_id}::${classId}`) ?? null
}

function courseLabel(courseId: string): string {
  const name = props.courseNameById[courseId]
  return name ? `${courseId} · ${name}` : courseId
}

/** 任课教师：缺数据时如实显示"待核验"，⛔ 不编造。 */
function teacherText(offering: CourseOffering | null): string {
  const value = offering?.teacher?.trim()
  if (!value) return '任课教师：待核验'
  if (value.toLowerCase() === 'redacted') return '任课教师：信息已脱敏'
  return `任课教师：${value}`
}

/** 上课时间：`meetings = []` 表示**排课信息未知**，⛔ 不得说成"无课/无冲突"。 */
function meetingText(offering: CourseOffering | null): string {
  if (!offering) return '上课信息待核验'
  if (offering.meetings.length === 0) return EMPTY_MEETINGS_DATA_TEXT
  return offering.meetings.map((item) => formatMeetingLine(item)).join('；')
}

function placeText(offering: CourseOffering | null): string {
  if (!offering || offering.meetings.length === 0) return '校区 / 教室待核验'
  const parts = offering.meetings
    .map((item) => [item.campus, item.classroom].filter(Boolean).join(' / '))
    .filter((value) => value.length > 0)
  return parts.length > 0 ? parts.join('；') : '校区 / 教室待核验'
}

/** 原班状态：`UNKNOWN` = 排课信息待核验，⛔ 不写成"已确认冲突"。 */
function stateLabel(state: string): string {
  if (state === 'CONFLICT') return '已确认时间冲突'
  if (state === 'UNKNOWN') return '排课信息待核验'
  return state
}

function stateTagClass(state: string): string {
  return state === 'CONFLICT' ? 'tag--unresolved-manual' : 'tag--unresolved-schedule'
}

function onApply(proposal: RepairProposal): void {
  emit('apply', {
    semester: proposal.semester,
    courseId: proposal.course_id,
    fromClassId: proposal.current_class_id,
    toClassId: proposal.candidate_class_id,
  })
}
</script>

<template>
  <div class="adjust" data-testid="case-a-pending-adjustments">
    <p v-if="!hasAnything" class="adjust__empty" data-testid="case-a-adjustments-empty">
      本次方案没有需要你确认的调整项。
    </p>

    <template v-else>
      <!-- 提醒：换班必须由你确认 -->
      <p class="adjust__hint" data-testid="case-a-adjustments-policy">
        以下调整由后端返回；系统<strong>不会自行改变</strong>你的当前课表，
        只有你点击「采用调整」之后才会生效。
      </p>

      <!-- 已提出但**尚未应用**的调整建议 -->
      <section v-if="changes.length > 0" class="adjust__group">
        <h3 class="adjust__title">系统提出的调整建议（{{ changes.length }} 项，尚未应用）</h3>
        <ul class="adjust__list">
          <li
            v-for="change in changes"
            :key="`${change.course_id}-${change.from_class}-${change.to_class}`"
            class="adjust__item"
            data-testid="case-a-adjustment-change"
          >
            <div class="adjust__item-head">
              <strong>{{ courseLabel(change.course_id) }}</strong>
              <span class="mono adjust__flow">
                {{ displayOrDash(change.from_class) }} → {{ displayOrDash(change.to_class) }}
              </span>
            </div>
            <p class="adjust__reason">{{ change.reason }}</p>
          </li>
        </ul>
      </section>

      <!-- 结构化换班建议（可确认执行） -->
      <section v-if="visibleProposals.length > 0" class="adjust__group">
        <h3 class="adjust__title">
          可确认的换班建议（{{ visibleProposals.length }} 项，尚未应用）
        </h3>
        <p class="adjust__hint">
          每条建议都给出了具体的候选教学班。确认后系统只会把该课程的当前教学班
          替换为你选择的那一个，并重新校验整份课表。
        </p>
        <ul class="adjust__list">
          <li
            v-for="proposal in visibleProposals"
            :key="proposal.proposal_id"
            class="adjust__item"
            data-testid="case-a-repair-proposal"
          >
            <div class="adjust__item-head">
              <strong>{{ courseLabel(proposal.course_id) }}</strong>
              <span class="mono adjust__flow" data-testid="case-a-repair-flow">
                {{ proposal.current_class_id }} → {{ proposal.candidate_class_id }}
              </span>
              <span class="tag" :class="stateTagClass(proposal.original_state)">
                {{ stateLabel(proposal.original_state) }}
              </span>
            </div>

            <dl class="adjust__detail">
              <div class="adjust__detail-row">
                <dt>当前教学班</dt>
                <dd class="mono">{{ proposal.current_class_id }}</dd>
              </div>
              <div class="adjust__detail-row">
                <dt>候选教学班</dt>
                <dd class="mono">{{ proposal.candidate_class_id }}</dd>
              </div>
              <div class="adjust__detail-row">
                <dt>候选上课时间</dt>
                <dd>{{ meetingText(offeringOf(proposal, proposal.candidate_class_id)) }}</dd>
              </div>
              <div class="adjust__detail-row">
                <dt>候选校区 / 教室</dt>
                <dd>{{ placeText(offeringOf(proposal, proposal.candidate_class_id)) }}</dd>
              </div>
              <div class="adjust__detail-row">
                <dt>候选任课教师</dt>
                <dd>{{ teacherText(offeringOf(proposal, proposal.candidate_class_id)) }}</dd>
              </div>
              <div class="adjust__detail-row">
                <dt>当前班任课教师</dt>
                <dd>{{ teacherText(offeringOf(proposal, proposal.current_class_id)) }}</dd>
              </div>
            </dl>

            <p class="adjust__reason">{{ proposal.reason }}</p>

            <div class="adjust__actions">
              <button
                class="button button--small"
                type="button"
                :disabled="applying"
                :data-testid="`case-a-repair-apply-${proposal.course_id}-${proposal.candidate_class_id}`"
                @click="onApply(proposal)"
              >
                采用调整
              </button>
              <button
                class="button button--small"
                type="button"
                :data-testid="`case-a-repair-dismiss-${proposal.course_id}-${proposal.candidate_class_id}`"
                @click="dismiss(proposal.proposal_id)"
              >
                暂不调整
              </button>
            </div>
          </li>
        </ul>
      </section>

      <!-- 没有可确认候选时的中性说明（⛔ 不是失败，也不替用户决定） -->
      <section v-if="showSelectionNotice" class="adjust__group">
        <h3 class="adjust__title">{{ SELECTION_REQUIRED_TITLE }}（{{ selectionRequired.length }} 项）</h3>
        <p class="adjust__hint">{{ SELECTION_REQUIRED_BODY }}</p>
        <ul class="adjust__list">
          <li
            v-for="(item, index) in selectionRequired"
            :key="`selection-required-${index}`"
            class="adjust__item adjust__item--pending"
            data-testid="case-a-selection-required"
          >
            <div class="adjust__item-head">
              <span class="tag tag--unresolved-selection">需要明确选择</span>
            </div>
            <p class="adjust__reason">{{ item.message }}</p>
            <p class="adjust__note">
              当前输入里没有可确认无冲突的候选教学班，因此系统不会替你决定，也不会改动课表。
            </p>
          </li>
        </ul>
      </section>

      <!-- 无法给出建议的教学班（结构化原因） -->
      <section v-if="proposalUnresolved.length > 0" class="adjust__group">
        <h3 class="adjust__title">无法给出换班建议的课程（{{ proposalUnresolved.length }} 项）</h3>
        <ul class="adjust__list">
          <li
            v-for="(item, index) in proposalUnresolved"
            :key="`proposal-unresolved-${index}`"
            class="adjust__item adjust__item--pending"
            data-testid="case-a-repair-unresolved"
          >
            <p class="adjust__reason">{{ item }}</p>
          </li>
        </ul>
      </section>

      <!-- 其他未决事项 -->
      <section v-if="otherUnresolved.length > 0" class="adjust__group">
        <h3 class="adjust__title">其他待确认事项（{{ otherUnresolved.length }} 项）</h3>
        <ul class="adjust__list">
          <li
            v-for="(item, index) in otherUnresolved"
            :key="`${item.type}-${index}`"
            class="adjust__item"
            data-testid="case-a-adjustment-unresolved"
          >
            <div class="adjust__item-head">
              <span class="mono">{{ item.type }}</span>
            </div>
            <p class="adjust__reason">{{ item.message }}</p>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.adjust {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.adjust__empty,
.adjust__hint,
.adjust__reason,
.adjust__note {
  margin: 0;
}

.adjust__empty {
  padding: 14px 16px;
  color: var(--text-muted);
  background: #f8fafc;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
}

.adjust__group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.adjust__title {
  margin: 0;
  font-size: 15px;
  color: var(--text);
}

.adjust__hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.adjust__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.adjust__item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.adjust__item--pending {
  border-color: #f3d9a4;
  background: #fffdf5;
}

.adjust__item-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.adjust__flow {
  color: #475569;
  font-size: 12px;
}

.adjust__detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
}

.adjust__detail-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 8px;
  font-size: 12px;
  line-height: 1.7;
}

.adjust__detail-row dt {
  color: var(--text-muted);
}

.adjust__detail-row dd {
  margin: 0;
  color: #334155;
  overflow-wrap: anywhere;
}

.adjust__reason {
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.adjust__note {
  color: #b45309;
  font-size: 12px;
  line-height: 1.7;
}

.adjust__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
