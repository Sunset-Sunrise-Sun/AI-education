<script setup lang="ts">
import { computed, ref } from 'vue'
import IssueList from './IssueList.vue'
import { issueLabel, type NormalizedIssue } from '../utils/studentIssues'

/**
 * **统一提醒区**（页面底部，唯一一处汇总）。
 *
 * 背景：早期把每个模块的待确认事项都在模块内部铺成一个大卡片区
 * （"与本区块相关的待确认事项"×4），页面因此冗长且重复。
 *
 * 现在的口径：
 *
 * - 各模块**只保留自己的可操作交互**（补修确认、选修加入、换班采用）；
 * - 页面**底部只有这一个**提醒区，默认折叠，只做汇总；
 * - ⛔ 不在这里重复渲染一整套大卡片：展开后才列出明细；
 * - ⛔ 任何议题都不得因此消失（归属不变式仍由 `issueRouting` 保证）。
 */
const props = withDefaults(
  defineProps<{
    issues: NormalizedIssue[]
    /** 默认是否展开（默认折叠）。 */
    defaultOpen?: boolean
  }>(),
  { defaultOpen: false },
)

const open = ref(props.defaultOpen)
const hasIssues = computed(() => props.issues.length > 0)

/** 按类别汇总（一行一条，稳定排序）。 */
const summary = computed(() => {
  const counts = new Map<string, number>()
  for (const issue of props.issues) {
    const label = issueLabel(issue.kind)
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
})
</script>

<template>
  <div class="reminders" data-testid="case-a-reminders">
    <p v-if="!hasIssues" class="reminders__none" data-testid="case-a-reminders-none">
      当前没有需要你确认的事项。
    </p>

    <template v-else>
      <div class="reminders__head">
        <h3 class="reminders__title" data-testid="case-a-reminders-title">
          待确认与提醒（{{ issues.length }} 项）
        </h3>
        <button
          class="button button--small button--ghost"
          type="button"
          :aria-expanded="open"
          data-testid="case-a-reminders-toggle"
          @click="open = !open"
        >
          {{ open ? '收起明细' : '查看明细' }}
        </button>
      </div>

      <!-- 默认只给一行汇总（⛔ 不铺开大卡片） -->
      <ul class="reminders__summary" data-testid="case-a-reminders-summary">
        <li v-for="row in summary" :key="row.label">
          {{ row.count }} 项：{{ row.label }}
        </li>
      </ul>

      <p class="reminders__hint" data-testid="case-a-reminders-hint">
        可操作的确认在各自模块内完成（补修缺口分析 / 专业选修 / 推荐课表）；
        这里只做汇总，不会自动替你决定任何事项。
      </p>

      <IssueList v-if="open" :issues="issues" owner-label="全部" :limit="5" />
    </template>
  </div>
</template>

<style scoped>
.reminders {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reminders__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.reminders__title {
  margin: 0;
  font-size: 15px;
}

.reminders__none,
.reminders__hint {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.reminders__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin: 0;
  padding-left: 18px;
  color: #475569;
  font-size: 13px;
}
</style>
