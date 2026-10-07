<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RepairProposalSet } from '../types/caseAPlanning'
import type { CourseOffering, PlanResult } from '../types/contracts'
import { EMPTY_MEETINGS_DATA_TEXT, formatMeetingLine } from '../utils/labels'
import {
  MAX_INITIAL_CANDIDATES,
  buildRepairView,
  type CourseRepairGroup,
} from '../utils/repairView'

/**
 * 换班候选区：只负责**可执行**的换班（⛔ 没有独立待处理区块）。
 *
 * 人工验收发现的问题与本组件的修复（⛔ 不得回退）：
 *
 * 1. 同一门课的 N 个候选教学班曾被铺成 N 张卡片（劳动教育 PUB178 × 60）
 *    ⇒ 现在按 `semester + course_id` 分组成**一门课一张卡片**；
 * 2. 每门课默认只显示前 `MAX_INITIAL_CANDIDATES`（3）个候选，其余折叠为
 *    「查看其余 N 个」；
 * 3. 「无法给出换班建议」曾铺 11 张大卡片、主文案还是 `UNKNOWN` / `schedule_unknown`
 *    ⇒ 现在只显示**一条摘要**（按原因分类计数），详情默认折叠；
 * 4. 机器码只出现在「技术详情」里，⛔ 不作为主文案；
 * 5. ⛔ 没有 CLEAR 候选时不使用「可确认」字样，改称「可考虑的替代教学班」。
 *
 * 其余边界保持不变：
 * - ⛔ 不做任何换班算法；身份一律取自结构化字段；
 * - ⛔ 生成建议 ≠ 应用建议：只有用户点击「采用调整」才 emit `apply`；
 * - ⛔ 不自行判定替换是否成功；「暂不调整」只是本地收起。
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

/** 已接受「保留当前班」的课程号（纯视图状态）。 */
const dismissedCourses = ref<Set<string>>(new Set())
/** 已展开全部候选的课程号。 */
const expandedCourses = ref<Set<string>>(new Set())

function toggleExpand(courseId: string): void {
  const next = new Set(expandedCourses.value)
  if (next.has(courseId)) next.delete(courseId)
  else next.add(courseId)
  expandedCourses.value = next
}

function dismiss(courseId: string): void {
  const next = new Set(dismissedCourses.value)
  next.add(courseId)
  dismissedCourses.value = next
}

const repairView = computed(() =>
  buildRepairView(
    props.repairProposals?.proposals ?? [],
    props.repairProposals?.unresolved ?? [],
    props.courseNameById,
    MAX_INITIAL_CANDIDATES,
  ),
)

/**
 * 本组件只负责**真正可执行**的换班：至少有一个已确认无冲突（CLEAR）候选。
 *
 * ⚠️ 只有 UNKNOWN/CONFLICT 候选的课程不是"可执行动作"（用户点下去也没有可靠结果），
 * 它们会由页面「需要你处理」里的归一化条目以中文说明，⛔ 不在这里重复。
 */
const actionableGroups = computed(() =>
  repairView.value.groups.filter(
    (group) => group.hasConfirmableCandidate && !dismissedCourses.value.has(group.courseId),
  ),
)

/**
 * ⛔ 非可执行的候选组与「无法生成建议」清单**不在这里**渲染：
 * 它们已由 `normalizedIssues` 归一化为中文条目，归属区块内展示。
 * 本组件只保留可点击的换班卡片，避免同一门课在两处出现。
 */
const hasAnything = computed(() => actionableGroups.value.length > 0)

const offeringByKey = computed(() => {
  const map = new Map<string, CourseOffering>()
  for (const item of props.offerings) {
    map.set(`${item.semester}::${item.course_id}::${item.class_id}`, item)
  }
  return map
})

function offeringOf(courseId: string, classId: string): CourseOffering | null {
  const semester = props.repairProposals?.semester ?? ''
  return offeringByKey.value.get(`${semester}::${courseId}::${classId}`) ?? null
}

/** 折叠后仍可见的候选 / 是否还有更多。 */
function visibleCandidates(group: CourseRepairGroup) {
  if (expandedCourses.value.has(group.courseId)) return group.candidates
  return group.candidates.slice(0, MAX_INITIAL_CANDIDATES)
}

function hiddenCount(group: CourseRepairGroup): number {
  return Math.max(0, group.candidates.length - MAX_INITIAL_CANDIDATES)
}

/** 任课教师：缺数据时如实说明"暂未同步"，⛔ 不编造。 */
function teacherText(offering: CourseOffering | null): string {
  const value = offering?.teacher?.trim()
  if (!value) return '教师信息暂未同步'
  if (value.toLowerCase() === 'redacted') return '教师信息暂未同步'
  return `任课教师：${value}`
}

/** 上课时间：`meetings = []` 表示**排课信息未知**，⛔ 不得说成"无课/无冲突"。 */
function meetingText(offering: CourseOffering | null): string {
  if (!offering) return '排课信息尚未同步'
  if (offering.meetings.length === 0) return EMPTY_MEETINGS_DATA_TEXT
  return offering.meetings.map((item) => formatMeetingLine(item)).join('；')
}

function placeText(offering: CourseOffering | null): string {
  if (!offering || offering.meetings.length === 0) return '校区 / 教室尚未同步'
  const parts = offering.meetings
    .map((item) => [item.campus, item.classroom].filter(Boolean).join(' / '))
    .filter((value) => value.length > 0)
  return parts.length > 0 ? parts.join('；') : '校区 / 教室尚未同步'
}

/** 候选状态的中文说明（⛔ 不显示 CLEAR / UNKNOWN 等机器取值）。 */
function stateLabel(state: string): string {
  if (state === 'CLEAR') return '已确认与你的课表不冲突'
  if (state === 'CONFLICT') return '与你的课表冲突'
  if (state === 'UNKNOWN') return '排课信息待核验'
  return '状态待核验'
}

function onApply(courseId: string, fromClassId: string, toClassId: string): void {
  emit('apply', {
    semester: props.repairProposals?.semester ?? '',
    courseId,
    fromClassId,
    toClassId,
  })
}
</script>

<template>
  <div class="adjust" data-testid="case-a-pending-adjustments">
    <p v-if="!hasAnything" class="adjust__empty" data-testid="case-a-adjustments-empty">
      本学期推荐课表里没有等待你确认的换班。
    </p>

    <template v-else>
      <p class="adjust__hint" data-testid="case-a-adjustments-policy">
        系统<strong>不会自行改变</strong>你的课表；只有你点击「采用调整」之后才会生效。
      </p>

      <!-- ① 可执行的换班：一门课一张卡片（⛔ 只有已确认无冲突的候选才在这里） -->
      <section v-if="actionableGroups.length > 0" class="adjust__group">
        <h3 class="adjust__title">可以换班（{{ actionableGroups.length }} 门课程）</h3>
        <ul class="adjust__list">
          <li
            v-for="group in actionableGroups"
            :key="group.courseId"
            class="adjust__item"
            data-testid="case-a-repair-course"
          >
            <div class="adjust__item-head">
              <strong data-testid="case-a-repair-course-name">{{ group.courseName }}</strong>
              <span class="mono adjust__code">{{ group.courseId }}</span>
              <span class="tag">{{ group.headline }}</span>
            </div>
            <p class="adjust__reason">{{ group.note }}</p>
            <p class="adjust__meta">
              当前教学班：<span class="mono">{{ group.currentClassId ?? '—' }}</span>
            </p>

            <ul class="adjust__candidates">
              <li
                v-for="candidate in visibleCandidates(group)"
                :key="candidate.classId"
                class="adjust__candidate"
                data-testid="case-a-repair-candidate"
              >
                <div class="adjust__candidate-head">
                  <span class="mono">{{ candidate.classId }}</span>
                  <span
                    class="tag"
                    :class="candidate.confirmedClear ? '' : 'tag--unresolved-schedule'"
                  >{{ stateLabel(candidate.state) }}</span>
                </div>
                <p class="adjust__candidate-detail">
                  {{ meetingText(offeringOf(group.courseId, candidate.classId)) }}
                  · {{ placeText(offeringOf(group.courseId, candidate.classId)) }}
                  · {{ teacherText(offeringOf(group.courseId, candidate.classId)) }}
                </p>
                <div class="adjust__actions">
                  <!-- ⛔ 只有**已确认无冲突（CLEAR）**的候选才给可执行按钮。
                       UNKNOWN / CONFLICT 的兄弟候选只是信息展示：点下去没有可靠结果。 -->
                  <button
                    v-if="candidate.confirmedClear"
                    class="button button--small"
                    type="button"
                    :disabled="applying"
                    :data-testid="`case-a-repair-apply-${group.courseId}-${candidate.classId}`"
                    @click="onApply(group.courseId, group.currentClassId ?? '', candidate.classId)"
                  >
                    采用调整
                  </button>
                  <span
                    v-else
                    class="adjust__not-actionable"
                    :data-testid="`case-a-repair-not-actionable-${group.courseId}-${candidate.classId}`"
                  >
                    暂不可调整：{{ stateLabel(candidate.state) }}
                  </span>
                </div>
              </li>
            </ul>

            <div class="adjust__actions">
              <button
                v-if="hiddenCount(group) > 0 && !expandedCourses.has(group.courseId)"
                class="button button--small button--ghost"
                type="button"
                :data-testid="`case-a-repair-expand-${group.courseId}`"
                @click="toggleExpand(group.courseId)"
              >
                查看其余 {{ hiddenCount(group) }} 个候选
              </button>
              <button
                class="button button--small button--ghost"
                type="button"
                :data-testid="`case-a-repair-dismiss-${group.courseId}`"
                @click="dismiss(group.courseId)"
              >
                保留当前班
              </button>
            </div>
          </li>
        </ul>
      </section>

      <!-- ⛔ 非可执行的候选与「无法生成建议」清单不在这里渲染：
           它们已由 `normalizedIssues` 归一化为中文，在归属区块内展示。 -->
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
.adjust__meta,
.adjust__candidate-detail,
.adjust__raw {
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

.adjust__list,
.adjust__candidates,
.adjust__summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.adjust__summary {
  color: #475569;
  font-size: 13px;
  line-height: 1.8;
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

.adjust__item-head,
.adjust__candidate-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.adjust__code {
  color: var(--text-muted);
  font-size: 12px;
}

.adjust__meta {
  color: #475569;
  font-size: 12px;
}

.adjust__candidate {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-left: 3px solid #dbeafe;
  background: #f8fafc;
  border-radius: var(--radius-sm);
}

.adjust__candidate-detail {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.adjust__reason {
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.adjust__tech {
  font-size: 12px;
  color: var(--text-muted);
}

.adjust__raw {
  margin-top: 4px;
  color: #64748b;
  overflow-wrap: anywhere;
}

.adjust__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

/* 非 CLEAR 候选：只说明状态，不提供可执行按钮。 */
.adjust__not-actionable {
  color: var(--text-muted);
  font-size: 12px;
}
</style>
