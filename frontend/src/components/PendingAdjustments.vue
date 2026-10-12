<script setup lang="ts">
import { computed } from 'vue'
import { displayOrDash } from '../utils/labels'
import { studentText } from '../utils/displayLanguage'
import type { PlanResult } from '../types/contracts'

const props = defineProps<{ planResult: PlanResult | null; courseNameById: Record<string, string> }>()
const changes = computed(() => props.planResult?.changes ?? [])
function courseLabel(id: string): string {
  return props.courseNameById[id] ? `${props.courseNameById[id]}（${id}）` : id
}
</script>
<template>
  <div class="adjust" data-testid="case-a-pending-adjustments">
    <p v-if="!changes.length" class="adjust__empty" data-testid="case-a-adjustments-empty">本次未返回调整建议。</p>
    <section v-else class="adjust__group">
      <h3 class="adjust__title">系统提出的调整建议（{{ changes.length }} 项，尚未应用）</h3>
      <p class="adjust__hint">以下为建议安排，尚未应用到你的当前课表。需要核对的事项请在推荐方案中确认。</p>
      <ul class="adjust__list">
        <li v-for="change in changes" :key="`${change.course_id}-${change.from_class}-${change.to_class}`" class="adjust__item" data-testid="case-a-adjustment-change">
          <div class="adjust__item-head">
            <strong>{{ courseLabel(change.course_id) }}</strong>
            <span class="mono adjust__flow">{{ displayOrDash(change.from_class) }} → {{ displayOrDash(change.to_class) }}</span>
          </div>
          <p class="adjust__reason">{{ studentText(change.reason, '请核对教学班调整。') }}</p>
        </li>
      </ul>
    </section>
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
</style>
