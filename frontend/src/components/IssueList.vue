<script setup lang="ts">
import { ref } from 'vue'
import { issueLabel, type NormalizedIssue } from '../utils/studentIssues'

/**
 * 某个产品区块内展示**归属该区块**的议题。
 *
 * 背景：最终产品形态**没有**独立的「需要你处理」区块，
 * 每个议题都要落到所属区块（补修 / 选修 / 课表 / 未来 / 详细依据）。
 *
 * 边界：
 * - ⛔ 本组件不解析后端 raw 文本：只渲染已归一化的中文 `message`；
 * - raw 取值（`rawCode` / 后端原文）只在**默认折叠**的「查看技术详情」里；
 * - 每类默认最多 3 条，其余折叠（渐进披露）。
 */
const props = withDefaults(
  defineProps<{
    issues: NormalizedIssue[]
    /** 所属区块名（用于标题，例如"本学期排课"）。 */
    ownerLabel?: string
    /** 默认展示条数。 */
    limit?: number
  }>(),
  { ownerLabel: '', limit: 3 },
)

const expanded = ref(false)
const techOpen = ref<Set<string>>(new Set())

function toggleTech(id: string): void {
  const next = new Set(techOpen.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  techOpen.value = next
}

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
  <div class="issue-list" data-testid="case-a-issue-list">
    <h4 class="issue-list__title" data-testid="case-a-issue-list-title">
      与本区块相关的待确认事项（{{ issues.length }} 项<span v-if="ownerLabel"> · {{ ownerLabel }}</span>）
    </h4>
    <ul class="issue-list__items">
      <li
        v-for="issue in expanded ? issues : issues.slice(0, limit)"
        :key="issue.id"
        class="issue-list__item"
        data-testid="case-a-issue"
      >
        <div class="issue-list__head">
          <strong data-testid="case-a-issue-title">{{ issue.title }}</strong>
          <span v-if="issue.detail" class="mono issue-list__code">{{ issue.detail }}</span>
          <span class="tag issue-list__kind">{{ issueLabel(issue.kind) }}</span>
        </div>
        <!-- 主文案：已归一化中文，⛔ 不含机器码 -->
        <p class="issue-list__message" data-testid="case-a-issue-message">{{ issue.message }}</p>

        <details class="issue-list__tech">
          <summary
            data-testid="case-a-issue-tech-toggle"
            @click.prevent="toggleTech(issue.id)"
          >
            查看技术详情
          </summary>
          <ul class="issue-list__raw" data-testid="case-a-issue-tech">
            <li v-for="(line, index) in rawLines(issue)" :key="index">{{ line }}</li>
          </ul>
        </details>
      </li>
    </ul>

    <button
      v-if="issues.length > limit && !expanded"
      class="button button--small button--ghost"
      type="button"
      data-testid="case-a-issue-list-expand"
      @click="expanded = true"
    >
      查看其余 {{ issues.length - limit }} 项
    </button>
  </div>
</template>

<style scoped>
.issue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}

.issue-list__title {
  margin: 0;
  font-size: 13px;
  color: #92400e;
}

.issue-list__items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.issue-list__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: var(--radius-sm);
}

.issue-list__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.issue-list__code {
  color: var(--text-muted);
  font-size: 12px;
}

.issue-list__kind {
  font-size: 11px;
}

.issue-list__message {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.issue-list__tech {
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
}

.issue-list__raw {
  margin: 4px 0 0;
  padding-left: 18px;
  color: #64748b;
  overflow-wrap: anywhere;
}
</style>
