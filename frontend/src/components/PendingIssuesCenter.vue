<script setup lang="ts">
import { computed, ref } from 'vue'
import { groupIssues, type NormalizedIssue } from '../utils/studentIssues'

/**
 * ⚠️ **已退役（不再由页面挂载）**：最终产品形态取消了独立的待处理区块，
 * 议题改为归属到各自的产品区块（见 `utils/issueRouting.ts` + `IssueList.vue`）。
 *
 * 本组件仅保留给单元测试与历史对照，⛔ 不要再把它接回主流程。
 *
 * 原设计：「需要你处理」—— 统一的待确认事项列表。
 *
 * 数据来源：`CaseADemoView` 里**唯一**的 `normalizedIssues`（统合
 * `plan_result.unresolved` + `roadmap.unresolved` + `roadmap.warnings` +
 * `repair_proposals.unresolved`）。
 *
 * ⛔ 本组件不得自行解析后端 raw 文本：只渲染已归一化的中文 `message`，
 *    原始取值一律放进**默认折叠**的「查看技术详情」。
 * ⛔ 可执行的换班候选与「无法生成建议」摘要不在这里渲染
 *    （由 `PendingAdjustments` 负责），否则同一件事会出现两次。
 *
 * 渐进披露：每个分组默认最多 `limit`（3）条，其余折叠为「查看其余 N 项」。
 */
const props = withDefaults(
  defineProps<{
    issues: NormalizedIssue[]
    /** 每个分组默认展示条数（产品要求：默认最多 3 条）。 */
    limit?: number
  }>(),
  { limit: 3 },
)

/** 已展开全部条目的分组。 */
const expanded = ref<Set<string>>(new Set())
/** 已展开技术详情的条目 id。 */
const techExpanded = ref<Set<string>>(new Set())

function toggle(group: string): void {
  const next = new Set(expanded.value)
  if (next.has(group)) next.delete(group)
  else next.add(group)
  expanded.value = next
}

function toggleTech(id: string): void {
  const next = new Set(techExpanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  techExpanded.value = next
}

const SECTIONS = [
  { key: 'actionable', title: '需要你决定', hint: '这些事项需要你确认后才会生效。' },
  { key: 'needsConfirmation', title: '需要进一步确认', hint: '系统不会替你下结论，需要人工确认。' },
  { key: 'incompleteData', title: '数据暂不完整', hint: '数据不足时系统不会猜测，因此暂时无法判断。' },
] as const

type SectionKey = (typeof SECTIONS)[number]['key']

/** 某个分组属于哪一类（与 `groupIssues` 的分类口径保持一致）。 */
function belongs(issue: NormalizedIssue, key: SectionKey): boolean {
  if (issue.actionable) return key === 'actionable'
  const isConfirm = issue.kind === 'makeup_confirmation' || issue.kind === 'binding_provenance'
  return key === (isConfirm ? 'needsConfirmation' : 'incompleteData')
}

const capped = computed(() => groupIssues(props.issues, props.limit))

function visibleOf(key: SectionKey): NormalizedIssue[] {
  return capped.value[key]
}

function totalOf(key: SectionKey): number {
  return props.issues.filter((issue) => belongs(issue, key)).length
}

function hiddenOf(key: SectionKey): number {
  return Math.max(0, totalOf(key) - props.limit)
}

/** 展开后要额外显示的条目（即被上限截掉的那些）。 */
function remainderOf(key: SectionKey): NormalizedIssue[] {
  return props.issues.filter((issue) => belongs(issue, key)).slice(props.limit)
}

/** 技术详情里可以展示的原始依据（⛔ 只在折叠区内）。 */
function rawLines(issue: NormalizedIssue): string[] {
  const lines: string[] = []
  if (issue.rawCode) lines.push(`原始类型：${issue.rawCode}`)
  if (issue.rawMessage && issue.rawMessage !== issue.message) {
    lines.push(`后端原文：${issue.rawMessage}`)
  }
  if (issue.courseId) lines.push(`课程号：${issue.courseId}`)
  if (issue.classId) lines.push(`教学班：${issue.classId}`)
  for (const item of issue.sourceEvidence) lines.push(`依据：${item}`)
  return lines
}
</script>

<template>
  <div class="issues" data-testid="case-a-pending-center">
    <p v-if="issues.length === 0" class="issues__empty" data-testid="case-a-issues-empty">
      目前没有需要你处理的事项：本学期方案里没有等待你确认的内容。
    </p>

    <template v-else>
      <section
        v-for="section in SECTIONS"
        v-show="totalOf(section.key) > 0"
        :key="section.key"
        class="issues__group"
        :data-testid="`case-a-issues-group-${section.key}`"
      >
        <h3 class="issues__title">{{ section.title }}（{{ totalOf(section.key) }} 项）</h3>
        <p class="issues__hint">{{ section.hint }}</p>

        <ul class="issues__list">
          <li
            v-for="issue in [
              ...visibleOf(section.key),
              ...(expanded.has(section.key) ? remainderOf(section.key) : []),
            ]"
            :key="issue.id"
            class="issues__item"
            data-testid="case-a-issue"
          >
            <div class="issues__head">
              <strong data-testid="case-a-issue-title">{{ issue.title }}</strong>
              <span v-if="issue.detail" class="mono issues__code">{{ issue.detail }}</span>
            </div>
            <!-- 主文案：已归一化中文，⛔ 不含机器码 -->
            <p class="issues__message" data-testid="case-a-issue-message">{{ issue.message }}</p>

            <details class="issues__tech">
              <summary data-testid="case-a-issue-tech-toggle" @click.prevent="toggleTech(issue.id)">
                查看技术详情
              </summary>
              <ul class="issues__raw" data-testid="case-a-issue-tech">
                <li v-for="(line, index) in rawLines(issue)" :key="index">{{ line }}</li>
              </ul>
            </details>
          </li>
        </ul>

        <button
          v-if="hiddenOf(section.key) > 0 && !expanded.has(section.key)"
          class="button button--small button--ghost"
          type="button"
          :data-testid="`case-a-issues-expand-${section.key}`"
          @click="toggle(section.key)"
        >
          查看其余 {{ hiddenOf(section.key) }} 项
        </button>
      </section>
    </template>
  </div>
</template>

<style scoped>
.issues {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.issues__empty,
.issues__hint,
.issues__message {
  margin: 0;
}

.issues__empty,
.issues__hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.issues__group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.issues__title {
  margin: 0;
  font-size: 15px;
  color: var(--text);
}

.issues__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.issues__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.issues__head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.issues__code {
  color: var(--text-muted);
  font-size: 12px;
}

.issues__message {
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.issues__tech {
  font-size: 12px;
  color: var(--text-muted);
}

.issues__raw {
  margin: 4px 0 0;
  padding-left: 18px;
  color: #64748b;
  overflow-wrap: anywhere;
}
</style>
