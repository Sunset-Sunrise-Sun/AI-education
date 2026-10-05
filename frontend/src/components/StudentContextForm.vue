<script setup lang="ts">
import { CASE_A_CONTEXT } from '../config'
import type { MajorOption } from '../config'
import type { StudentContext } from '../state/userInput'
import { SEMESTER_PATTERN, isValidSemester } from '../state/userInput'

/**
 * 学生转专业上下文 + 目标学期输入。
 *
 * 边界：
 * - 专业只作为**选项**存在（`datalist` 提供候选项，同时允许自由填写）；
 * - ⛔ 组件内不存在任何按专业名分叉的分支（例如 `if (major === '网络空间安全')`）；
 * - 这些信息本轮只是 **Case context**，页面会明确说明它们尚未影响后端 Planner。
 */
const props = defineProps<{
  /** 目标学期。 */
  semester: string
  /** 转专业上下文。 */
  context: StudentContext
  /** 专业选项层。 */
  majors: readonly MajorOption[]
}>()

const emit = defineEmits<{
  (event: 'update:semester', value: string): void
  (event: 'update:context', value: StudentContext): void
}>()

function onSemesterInput(event: Event): void {
  emit('update:semester', (event.target as HTMLInputElement).value)
}

function onContextInput(field: keyof StudentContext, event: Event): void {
  emit('update:context', {
    ...props.context,
    [field]: (event.target as HTMLInputElement).value,
  })
}
</script>

<template>
  <div class="uig-form">
    <p class="uig-form__note">
      以下信息本轮仅作为<strong>转专业上下文（Case context）展示与输入</strong>使用，
      <strong>尚未影响后端 Planner</strong>，也不代表已经产生任何补修或选课结论。
    </p>

    <div class="uig-grid">
      <!-- 目标学期 -->
      <label class="uig-field">
        <span class="uig-field__label">
          目标学期 <code class="mono">semester</code>
        </span>
        <input
          class="input-text"
          data-testid="semester-input"
          type="text"
          :value="semester"
          :pattern="SEMESTER_PATTERN"
          placeholder="例如 2026-1"
          autocomplete="off"
          @input="onSemesterInput"
        />
        <span
          v-if="!isValidSemester(semester.trim())"
          class="uig-field__error"
          data-testid="semester-error"
        >
          学期需形如 <code class="mono">YYYY-1</code> 或 <code class="mono">YYYY-2</code>；
          前端不会自行猜测或补全学期。
        </span>
        <span v-else class="uig-field__hint">规划针对的目标学期。默认 {{ CASE_A_CONTEXT.semester }}。</span>
      </label>

      <!-- 原专业 -->
      <label class="uig-field">
        <span class="uig-field__label">原专业</span>
        <input
          class="input-text"
          data-testid="origin-major-input"
          type="text"
          list="uig-major-options"
          :value="context.originMajor"
          autocomplete="off"
          @input="onContextInput('originMajor', $event)"
        />
      </label>

      <!-- 目标专业 -->
      <label class="uig-field">
        <span class="uig-field__label">目标专业</span>
        <input
          class="input-text"
          data-testid="target-major-input"
          type="text"
          list="uig-major-options"
          :value="context.targetMajor"
          autocomplete="off"
          @input="onContextInput('targetMajor', $event)"
        />
      </label>

      <!-- 转入学期 -->
      <label class="uig-field">
        <span class="uig-field__label">转入学期</span>
        <input
          class="input-text"
          data-testid="transfer-term-input"
          type="text"
          :value="context.transferTerm"
          autocomplete="off"
          placeholder="例如 2026-1"
          @input="onContextInput('transferTerm', $event)"
        />
      </label>
    </div>

    <!-- 专业候选项：只提供选项，不承担任何业务判断 -->
    <datalist id="uig-major-options">
      <option v-for="major in majors" :key="major.value" :value="major.value">
        {{ major.label }}
      </option>
    </datalist>
  </div>
</template>
