<script setup lang="ts">
import { computed, ref } from 'vue'
import { searchCourses, type CourseLevelMatch } from '../utils/courseSearch'
import type { CourseOffering } from '../types/contracts'

/**
 * 意向课程搜索（课程级）。
 *
 * 交互边界：
 * - 搜索是**字面子串匹配**（课程名 / 课程号），⛔ 不是语义推荐、⛔ 不是 AI 智能推荐；
 * - 结果**去重到课程级**：同一 course_id 只出现一条，教学班数量仅作计数；
 * - 加入后只写入 `Preference.preferredCourses`（course_id 数组），⛔ 不改公共 Schema、
 *   ⛔ 不表示"已经选上"这门课。
 */
const props = defineProps<{
  offerings: readonly CourseOffering[]
  selectedCourseIds: readonly string[]
}>()

const emit = defineEmits<{
  (event: 'add', courseId: string): void
  (event: 'remove', courseId: string): void
}>()

/** 搜索结果上限：课程级结果远小于教学班级，但仍设上限避免长列表。 */
const RESULT_LIMIT = 30

const query = ref('')
const normalizedQuery = computed(() => query.value.trim())

const matches = computed(() => searchCourses(props.offerings, query.value).slice(0, RESULT_LIMIT))
const selectedSet = computed(() => new Set(props.selectedCourseIds))

function creditText(match: CourseLevelMatch): string {
  return match.credit === null ? '学分待核验' : `${match.credit} 学分`
}

function add(match: CourseLevelMatch): void {
  if (selectedSet.value.has(match.courseId)) return
  emit('add', match.courseId)
}
</script>

<template>
  <div class="intent" data-testid="case-a-intent-search">
    <label class="intent__field">
      <span class="intent__label">你还想学习哪些课程？</span>
      <input
        v-model="query"
        class="input-text"
        data-testid="case-a-intent-input"
        type="search"
        autocomplete="off"
        placeholder="搜索课程名称、课程号或关键词，例如 Python、人工智能"
      />
      <span class="intent__hint">
        按课程名称或课程号的<strong>字面关键词</strong>搜索（不是智能语义推荐）；同一门课只显示一条结果。
      </span>
    </label>

    <p v-if="normalizedQuery && matches.length === 0" class="intent__empty" data-testid="case-a-intent-empty">
      没有课程的名称或课程号包含「{{ normalizedQuery }}」。可以换个关键词再试，或直接跳过这一项。
    </p>

    <ul v-if="matches.length > 0" class="intent__results">
      <li
        v-for="match in matches"
        :key="match.courseId"
        class="intent__row"
        data-testid="case-a-intent-result"
      >
        <div class="intent__row-main">
          <strong>{{ match.courseName }}</strong>
          <p class="intent__meta">
            <span class="mono">{{ match.courseId }}</span>
            <span>·</span>
            <span>{{ creditText(match) }}</span>
          </p>
          <p class="intent__meta">本学期有 {{ match.classCount }} 个教学班</p>
        </div>
        <button
          class="button button--small"
          type="button"
          data-testid="case-a-intent-add"
          :disabled="selectedSet.has(match.courseId)"
          @click="add(match)"
        >
          {{ selectedSet.has(match.courseId) ? '已加入意向' : '加入意向课程' }}
        </button>
      </li>
    </ul>

    <div v-if="selectedCourseIds.length > 0" class="intent__selected">
      <span class="intent__label">已加入的意向课程（{{ selectedCourseIds.length }}）</span>
      <div class="chip-group">
        <span
          v-for="courseId in selectedCourseIds"
          :key="courseId"
          class="chip chip--pref mono"
          data-testid="case-a-intent-chip"
        >
          {{ courseId }}
          <button
            class="intent__chip-remove"
            type="button"
            :aria-label="`移除 ${courseId}`"
            @click="emit('remove', courseId)"
          >
            ×
          </button>
        </span>
      </div>
      <span class="intent__hint">
        意向课程只表达"你想学"；是否排得下、是否与补修冲突，以生成后的方案与待确认事项为准。
      </span>
    </div>
  </div>
</template>

<style scoped>
.intent {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.intent__field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.intent__label {
  font-weight: 700;
  color: var(--text);
}

.intent__hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.intent__empty {
  margin: 0;
  padding: 12px 14px;
  color: var(--text-muted);
  background: #f8fafc;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
}

.intent__results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.intent__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid #d8e3f0;
  border-radius: var(--radius);
  background: #fff;
}

.intent__row-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.intent__row-main strong {
  color: #1e293b;
}

.intent__meta {
  display: flex;
  gap: 6px;
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.intent__selected {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.intent__chip-remove {
  margin-left: 6px;
  border: 0;
  background: transparent;
  color: inherit;
  font-weight: 700;
  cursor: pointer;
}
</style>
