<script setup lang="ts">
import { computed } from 'vue'
import { displayOrDash } from '../utils/labels'
import type { PlanResult } from '../types/contracts'

/**
 * 待你确认的调整。
 *
 * ⛔ 本组件**不实现任何 repair / 换班算法**：
 * - 只展示后端 `PlanResult` 已经返回的事实（`changes` 与 `unresolved`）；
 * - ⛔ 不从 `unresolved[].message` 里解析 class_id；
 * - ⛔ 不自己计算替代教学班、⛔ 不修改 current_schedule；
 * - ⛔ 不提供假的"确认调整"按钮（真正可交互的 repair 需要后端结构化 proposal 契约）。
 */
const props = defineProps<{
  planResult: PlanResult | null
  courseNameById: Record<string, string>
}>()

const SELECTION_REQUIRED_TITLE = '发现可调整的教学班'
const SELECTION_REQUIRED_BODY =
  '系统找到了其他无时间冲突的教学班，当前版本需要你确认后才能调整。'

const changes = computed(() => props.planResult?.changes ?? [])

/**
 * `selection_required` = 需要人工确认才能调整。
 * ⚠️ 这是**提示卡**，不是已经完成的调整。
 */
const selectionRequired = computed(
  () => (props.planResult?.unresolved ?? []).filter((item) => item.type === 'selection_required'),
)

/** 其他未决事项原样呈现（未知类型也不丢）。 */
const otherUnresolved = computed(
  () => (props.planResult?.unresolved ?? []).filter((item) => item.type !== 'selection_required'),
)

const hasAnything = computed(
  () => changes.value.length > 0 || selectionRequired.value.length > 0 || otherUnresolved.value.length > 0,
)

function courseLabel(courseId: string): string {
  const name = props.courseNameById[courseId]
  return name ? `${courseId} · ${name}` : courseId
}
</script>

<template>
  <div class="adjust" data-testid="case-a-pending-adjustments">
    <p v-if="!hasAnything" class="adjust__empty" data-testid="case-a-adjustments-empty">
      本次方案没有需要你确认的调整项。
    </p>

    <template v-else>
      <!-- 提出来但**尚未应用**的调整建议 -->
      <section v-if="changes.length > 0" class="adjust__group">
        <h3 class="adjust__title">系统提出的调整建议（{{ changes.length }} 项，尚未应用）</h3>
        <p class="adjust__hint">
          以下调整由后端返回；系统<strong>不会自行改变</strong>你的当前课表，需要你确认后才会生效。
        </p>
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

      <!-- 需要用户确认的候选调整（只有提示，没有候选结构化数据） -->
      <section v-if="selectionRequired.length > 0" class="adjust__group">
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
              ⛔ 当前版本只提供此提示：后端尚未返回结构化的候选教学班，因此系统不会替你决定，也不会改动课表。
            </p>
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
