<script setup lang="ts">
/**
 * 课表截图导入确认（frontend-only demo）。
 *
 * 流程严格保持：图片识别 → 候选信息 → **用户确认** → 进入当前课表。
 *
 * ⛔ 不做：自动生成 `CourseOffering`、自动认定教学班身份、绕过人工确认、改后端数据模型。
 * ⚠️ 识别结果来自 `mock/demoTimetableRecognition.ts` 的**演示数据**，不是真实 OCR；
 *    本条链路的真实实现见 `feature/case-a-timetable-ocr`（尚未完成）。
 */

import { computed, onBeforeUnmount, ref } from 'vue'

import {
  DEMO_RECOGNIZED_BLOCKS,
  DEMO_UNRESOLVED_COURSES,
  weekdayLabel,
  type DemoRecognizedBlock,
  type DemoUnresolvedCourse,
} from '../mock/demoTimetableRecognition'
import type { CourseOffering } from '../types/contracts'

const props = defineProps<{
  semester: string
  /** 已在当前课表中的条目，用于避免重复加入。 */
  selected: readonly CourseOffering[]
}>()

const emit = defineEmits<{
  /**
   * 用户确认识别结果 → 该课程进入**待匹配**状态。
   * ⚠️ 刻意**不**发出任何 `CourseOffering`：图片识别不产生课程身份。
   */
  (event: 'recognize', block: DemoRecognizedBlock): void
  (event: 'unrecognize', block: DemoRecognizedBlock): void
  /**
   * 请求父组件把**已有**的教学班搜索定位到该课程。
   * ⚠️ 本组件⛔ 不自己实现搜索：搜索逻辑仍唯一存在于 `CurrentScheduleEditor.vue`。
   */
  (event: 'search', keyword: string): void
}>()

const ACCEPT = 'image/png,image/jpeg,image/webp'
const MAX_BYTES = 8 * 1024 * 1024

const fileName = ref('')
const previewUrl = ref('')
const error = ref('')
const scanning = ref(false)
const blocks = ref<readonly DemoRecognizedBlock[]>([])
const unresolved = ref<readonly DemoUnresolvedCourse[]>([])
const confirmedIds = ref<readonly string[]>([])

function releasePreview(): void {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

onBeforeUnmount(releasePreview)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  error.value = ''
  blocks.value = []
  unresolved.value = []
  confirmedIds.value = []
  releasePreview()

  if (!file) {
    fileName.value = ''
    return
  }
  if (!ACCEPT.split(',').includes(file.type)) {
    fileName.value = ''
    error.value = '仅支持 PNG / JPEG / WebP 图片；未选择任何文件，也未读取其内容。'
    return
  }
  if (file.size > MAX_BYTES) {
    fileName.value = ''
    error.value = '截图不得超过 8 MiB；未读取其内容。'
    return
  }

  fileName.value = file.name
  previewUrl.value = URL.createObjectURL(file)
  // 演示：本地固定数据。⛔ 不上传图片、⛔ 不调用后端。
  scanning.value = true
  window.setTimeout(() => {
    blocks.value = DEMO_RECOGNIZED_BLOCKS
    unresolved.value = DEMO_UNRESOLVED_COURSES
    scanning.value = false
  }, 320)
}

const hasResult = computed(() => blocks.value.length > 0)

function isConfirmed(block: DemoRecognizedBlock): boolean {
  return confirmedIds.value.includes(block.demoId)
}

function confirmBlock(block: DemoRecognizedBlock): void {
  if (isConfirmed(block)) {
    return
  }
  // ⚠️ 方案 A（缩小版）：确认识别结果**不写入当前课表**。
  //    只把该候选标记为「待匹配」，随后由用户去**真实教学班库**搜索并选中真实教学班。
  //    ⛔ 不产生任何 `CourseOffering`、⛔ 不让 IMAGE-RECOGNIZED-* 进入 planner。
  emit('recognize', block)
  confirmedIds.value = [...confirmedIds.value, block.demoId]
}

function undoBlock(block: DemoRecognizedBlock): void {
  if (!isConfirmed(block)) {
    return
  }
  // ⚠️ 因为确认时**没有**写入课表，撤回只是取消「待匹配」标记，⛔ 不涉及课表移除。
  emit('unrecognize', block)
  confirmedIds.value = confirmedIds.value.filter((id) => id !== block.demoId)
}

/** 请求父组件用**已有**搜索定位到该课程（⛔ 本组件不实现搜索）。 */
function requestSearch(courseName: string): void {
  emit('search', courseName)
}

function clearAll(): void {
  // ⚠️ 确认态只是「待匹配」标记，未写入课表，因此清空时**不需要**移除任何课表条目。
  for (const block of blocks.value) {
    if (isConfirmed(block)) {
      emit('unrecognize', block)
    }
  }
  fileName.value = ''
  blocks.value = []
  unresolved.value = []
  confirmedIds.value = []
  error.value = ''
  releasePreview()
}
</script>

<template>
  <section class="tti" data-testid="case-a-image-import">
    <h4 class="tti__title">上传我的课表截图</h4>
    <p class="tti__hint">
      课表截图导入当前使用演示识别候选。确认识别后，请搜索并选择对应教学班加入当前课表。
      图片仅在本机预览，不会上传到第三方服务。
    </p>

    <label class="tti__file">
      <span>选择课表截图</span>
      <input
        type="file"
        :accept="ACCEPT"
        data-testid="case-a-image-input"
        @change="onFileChange"
      />
    </label>

    <p v-if="error" class="tti__error" role="alert" data-testid="case-a-image-error">{{ error }}</p>

    <p v-if="fileName && !error" class="tti__ok" data-testid="case-a-image-uploaded">
      ✓ 上传成功：<code class="mono">{{ fileName }}</code>
    </p>

    <div v-if="previewUrl" class="tti__preview" data-testid="case-a-image-preview">
      <img :src="previewUrl" alt="课表截图预览" />
    </div>

    <p v-if="scanning" class="tti__scanning" data-testid="case-a-image-scanning">
      正在本地识别课表网格…
    </p>

    <div v-if="hasResult" class="tti__result" data-testid="case-a-image-result">
      <p class="tti__result-head" data-testid="case-a-image-summary">
        识别成功：约 <strong>{{ blocks.length }}</strong> 门课程
      </p>

      <article
        v-for="block in blocks"
        :key="block.demoId"
        class="tti__block"
        data-testid="case-a-image-block"
      >
        <dl class="tti__fields">
          <div>
            <dt>课程</dt>
            <dd data-testid="case-a-image-course">{{ block.courseName }}</dd>
          </div>
          <div>
            <dt>时间</dt>
            <dd data-testid="case-a-image-time">
              {{ weekdayLabel(block.weekday) }}
              {{ block.startSection }}-{{ block.endSection }}节
            </dd>
          </div>
          <div>
            <dt>地点</dt>
            <dd data-testid="case-a-image-place">
              {{ block.campus ?? '待确认' }}
            </dd>
          </div>
        </dl>

        <p class="tti__block-note">
          以上为识别候选，请核对后选择对应教学班。
        </p>
        <ul class="tti__block-unconfirmed">
          <li v-for="reason in block.unconfirmed" :key="reason">{{ reason }}</li>
        </ul>

        <div class="tti__block-actions">
          <template v-if="!isConfirmed(block)">
            <button
              class="button button--small"
              type="button"
              data-testid="case-a-image-confirm"
              @click="confirmBlock(block)"
            >
              确认识别结果
            </button>
            <span class="tti__pending">待确认</span>
          </template>
          <template v-else>
            <span class="tti__confirmed" data-testid="case-a-image-confirmed">
              ✓ 已确认识别结果 · 待匹配教学班
            </span>
            <!--
              ⚠️ 方案 A：确认识别结果后**不写入课表**，而是引导用户去真实教学班库选择。
                 ⛔ 本组件不产生 CourseOffering、⛔ 不让 IMAGE-RECOGNIZED-* 进入 planner。
            -->
            <button
              class="button button--small"
              type="button"
              data-testid="case-a-image-match"
              @click="requestSearch(block.courseName)"
            >
              搜索教学班
            </button>
          </template>
          <!-- 忽略：未确认时略过该候选；已确认时取消「待匹配」标记（⛔ 不涉及课表移除）。 -->
          <button
            class="button button--small button--ghost"
            type="button"
            data-testid="case-a-image-ignore"
            @click="undoBlock(block)"
          >
            {{ isConfirmed(block) ? '撤回' : '忽略' }}
          </button>
        </div>
      </article>
    </div>

    <!--
      ⚠️ 布局插槽（最终展示优化）：父级把「已确认加入的当前课表」插在这里，
         形成 识别结果 → 当前课表 → 未识别/搜索教学班 的顺序。
         ⚠️ 刻意放在 `hasResult` 区块**之外**：当前课表与是否上传图片无关，
            任何时刻（含未上传时）都必须可见。
         ⛔ 本组件不渲染当前课表，也不改任何数据流。
    -->
    <slot name="between" />

    <!--
      未识别 / 无法自动确认的课程。
      ⚠️ 这里⛔ 不猜课程身份、⛔ 不自动选教学班：只如实说明原因，
         并把用户引导到**已有**的教学班搜索（CurrentScheduleEditor 里的搜索逻辑）。
    -->
    <section
      v-if="unresolved.length > 0"
      class="tti__unresolved"
      data-testid="case-a-image-unresolved"
    >
        <p class="tti__unresolved-head" data-testid="case-a-image-unresolved-summary">
          未识别：<strong>{{ unresolved.length }}</strong> 门课程
        </p>
        <p class="tti__unresolved-lead">部分课程无法自动确认，请通过教学班搜索完成选择。</p>

        <article
          v-for="course in unresolved"
          :key="course.demoId"
          class="tti__unresolved-item"
          data-testid="case-a-image-unresolved-item"
        >
          <div class="tti__unresolved-main">
            <strong data-testid="case-a-image-unresolved-course">{{ course.courseName }}</strong>
            <p class="tti__unresolved-reason" data-testid="case-a-image-unresolved-reason">
              原因：{{ course.reason }}
            </p>
          </div>
          <button
            class="button button--small"
            type="button"
            data-testid="case-a-image-search"
            @click="requestSearch(course.courseName)"
          >
            搜索教学班
          </button>
        </article>
    </section>

    <p v-if="hasResult" class="tti__hint">
      ⛔ 未确认的识别结果不会进入当前课表，也不会参与生成方案。
      <button
        class="case-a-link-button"
        type="button"
        data-testid="case-a-image-clear"
        @click="clearAll"
      >
        重新选择图片
      </button>
    </p>
  </section>
</template>

<style scoped>
.tti {
  margin-top: 14px;
  padding: 14px;
  border: 1px dashed #c7d2e0;
  border-radius: 10px;
  background: #fbfcfe;
}

.tti__title {
  margin: 0 0 6px;
  font-size: 15px;
}

.tti__hint {
  margin: 0 0 10px;
  color: #55606e;
  font-size: 13px;
  line-height: 1.6;
}

.tti__file {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.tti__ok {
  margin: 10px 0 0;
  color: #1b5e20;
  font-size: 13px;
}

.tti__error {
  margin: 10px 0 0;
  color: #b3261e;
  font-size: 13px;
}

.tti__scanning {
  margin: 10px 0 0;
  color: #55606e;
  font-size: 13px;
}

.tti__preview {
  margin-top: 10px;
  max-width: 420px;
}

.tti__preview img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid #dde3ea;
  border-radius: 8px;
}

.tti__unresolved {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #f0c36d;
  border-radius: 8px;
  background: #fffaf0;
}

.tti__unresolved-head {
  margin: 0 0 4px;
  font-size: 14px;
}

.tti__unresolved-lead {
  margin: 0 0 10px;
  color: #6b7683;
  font-size: 13px;
}

.tti__unresolved-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px dashed #e6d3ab;
}

.tti__unresolved-main strong {
  font-size: 14px;
}

.tti__unresolved-reason {
  margin: 4px 0 0;
  color: #8a5a00;
  font-size: 12px;
}

.tti__result {
  margin-top: 12px;
}

.tti__result-head {
  margin: 0 0 8px;
  font-weight: 600;
  font-size: 14px;
}

.tti__block {
  margin-bottom: 10px;
  padding: 12px;
  border: 1px solid #dde3ea;
  border-radius: 8px;
  background: #fff;
}

.tti__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 6px 16px;
  margin: 0;
}

.tti__fields dt {
  color: #6b7683;
  font-size: 12px;
}

.tti__fields dd {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 600;
}

.tti__block-note {
  margin: 10px 0 4px;
  color: #8a5a00;
  font-size: 12px;
}

.tti__block-unconfirmed {
  margin: 0 0 10px;
  padding-left: 18px;
  color: #6b7683;
  font-size: 12px;
  line-height: 1.6;
}

.tti__block-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tti__pending {
  color: #8a5a00;
  font-size: 13px;
}

.tti__confirmed {
  padding: 4px 10px;
  border: 1px solid #2e7d32;
  border-radius: 6px;
  background: #e8f5e9;
  color: #1b5e20;
  font-size: 13px;
  font-weight: 600;
}
</style>
