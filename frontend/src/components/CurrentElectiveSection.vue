<script setup lang="ts">
import { computed } from 'vue'
import type { CurrentElectiveItem, CurrentSemesterLoad } from '../api/caseADemo'

/**
 * 本学期可考虑的专业选修（**候选**，⛔ 不自动加入方案）。
 *
 * 人工验收发现的缺口：专业选修还缺学分时，本学期方案里可能一门选修都没有，
 * 页面静默显示"选修 = 0"，像系统没注意到一样。
 *
 * 边界（⛔ 不得越界）：
 * - 候选只来自 Curriculum 选修组成员 ∩ **已接受**教学班的精确 `course_id`；
 * - 本组件**不做**匹配、不做冲突计算，只展示后端已给出的计数与中文说明；
 * - ⛔ 不自动加入方案、⛔ 不自动选教学班；用户点「加入备选」后才 emit；
 * - 上限超限时如实提示，⛔ 不静默忽略。
 */
/**
 * ⚠️ 两个 prop 都带默认值：早期 fixture / 旧响应可能没有这两个新增字段，
 * 缺字段时应退化为「暂无推荐」而不是让 Vue 抛 prop 类型警告。
 */
const props = withDefaults(
  defineProps<{
    recommendations?: CurrentElectiveItem[] | null
    load?: CurrentSemesterLoad | null
  }>(),
  { recommendations: null, load: null },
)

const emit = defineEmits<{
  (event: 'add', payload: { courseId: string }): void
}>()

const items = computed(() => props.recommendations ?? [])
const hasItems = computed(() => items.value.length > 0)

/** 学分负荷说明（⛔ 不说成学校政策）。 */
const loadLine = computed(() => {
  const load = props.load
  if (!load) return ''
  const parts = [
    `当前已选 ${load.selected_credit} 学分`,
    `建议新增补修 ${load.suggested_makeup_credit} 学分`,
    `建议专业选修 ${load.suggested_elective_credit} 学分`,
    `预计合计 ${load.projected_total_credit} 学分`,
  ]
  return parts.join(' · ')
})
</script>

<template>
  <div class="elective" data-testid="case-a-current-electives">
    <p v-if="!hasItems" class="elective__empty" data-testid="case-a-current-electives-empty">
      本学期在已接受的教学班中，暂时没有可推荐的专业选修课程。
    </p>

    <template v-else>
      <p class="elective__intro" data-testid="case-a-electives-intro">
        你的专业选修还差学分。以下是本学期<strong>可以选修</strong>的专业课程
        （最多显示 3 门）；⛔ 系统不会替你选课。
      </p>

      <ul class="elective__list">
        <li
          v-for="item in items"
          :key="item.course_id"
          class="elective__item"
          data-testid="case-a-elective-item"
        >
          <div class="elective__head">
            <strong data-testid="case-a-elective-name">{{ item.course_name }}</strong>
            <span class="mono elective__code">{{ item.course_id }}</span>
            <span class="tag">{{ item.credit }} 学分</span>
          </div>
          <p class="elective__meta" data-testid="case-a-elective-status">
            {{ item.conflict_label }}
          </p>
          <p class="elective__meta">
            本学期可用教学班 {{ item.available_class_count }} 个
            <template v-if="item.unknown_schedule_class_count > 0">
              · {{ item.unknown_schedule_class_count }} 个排课信息待核验
            </template>
          </p>
          <p
            v-if="item.unique_clear_class_id"
            class="elective__clear"
            data-testid="case-a-elective-unique-class"
          >
            可直接选择的教学班：<span class="mono">{{ item.unique_clear_class_id }}</span>
          </p>
          <div class="elective__actions">
            <button
              class="button button--small"
              type="button"
              :data-testid="`case-a-elective-add-${item.course_id}`"
              @click="emit('add', { courseId: item.course_id })"
            >
              加入考虑
            </button>
          </div>
        </li>
      </ul>

      <p v-if="loadLine" class="elective__load" data-testid="case-a-credit-load">
        {{ loadLine }}
        <template v-if="load && load.exceeds_max">
          <strong class="elective__warn">（超过本学期学分上限 {{ load.max_credit }}）</strong>
        </template>
      </p>
      <p v-if="load" class="elective__policy" data-testid="case-a-credit-policy">
        {{ load.policy_note }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.elective {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.elective__empty,
.elective__intro,
.elective__meta,
.elective__clear,
.elective__load,
.elective__policy {
  margin: 0;
}

.elective__empty,
.elective__intro,
.elective__policy {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.elective__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.elective__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.elective__head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.elective__code {
  color: var(--text-muted);
  font-size: 12px;
}

.elective__meta {
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
}

.elective__clear {
  color: #166534;
  font-size: 12px;
}

.elective__load {
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
}

.elective__warn {
  color: #b45309;
}

.elective__actions {
  display: flex;
  gap: 8px;
}
</style>
