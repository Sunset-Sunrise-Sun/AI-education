<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import type { CourseOffering } from '../types/contracts'
import { EMPTY_MEETINGS_DATA_TEXT, formatMeetingLine } from '../utils/labels'

/** 允许的截图类型（只做**本地预览**，⛔ 不上传、⛔ 不解析）。 */
const SHOT_ACCEPT = 'image/png,image/jpeg,image/webp'

/** 截图大小上限：8 MiB（仅本地校验，⛔ 不代表后端限制）。 */
const SHOT_MAX_BYTES = 8 * 1024 * 1024

/**
 * 课表截图识别的**通道状态**。
 *
 * ⚠️ 这是本模块最重要的诚实声明：本项目**尚未接入任何图片识别服务**，
 * 因此这里只有"待识别"，⛔ 不存在"识别成功"这种状态。
 * ⇒ 页面⛔ 永远不会显示任何据称来自截图解析的课程。
 */
const SHOT_RECOGNITION_AVAILABLE = false

/**
 * 当前课表输入（`current_schedule: CourseOffering[]`）。
 *
 * 边界（DG-03 语义 + 本轮范围）：
 * - 只做一件事：让用户从**已加载的教学班**里勾选"我当前已选的班"；
 * - 勾选结果严格是 `CourseOffering[]`（复用公共类型，不新增 Schema）；
 * - ⛔ **不做冲突检测、不判断 feasible、不做 Path Repair、不计算学分**；
 * - ⛔ 不用 `Preference.avoid_times[]` 冒充当前课表；
 * - 允许为空：空数组是合法输入，是否需要更多信息由后端决定。
 */
const props = defineProps<{
  /** 来源教学班（学校供给），当前来自 Mock 演示通道。 */
  offerings: CourseOffering[]
  /** 用户已勾选的当前课表。 */
  selected: CourseOffering[]
  /** 数据来源标记，用于如实说明当前是 Mock 还是 Real。 */
  dataSourceLabel?: string | null
}>()

const emit = defineEmits<{
  (event: 'toggle', offering: CourseOffering): void
}>()

/* --------------------------------------------------------------------- *
 * 课表截图：上传 / 预览 / 待识别（本轮新增）
 *
 * ⚠️ 与手动勾选**并存**：下面这些状态完全不参与 `current_schedule` 的产出，
 *    勾选仍然是写入 `current_schedule` 的**唯一**途径。
 * --------------------------------------------------------------------- */

/** 已选择的截图文件（⛔ 不读取其内容）。 */
const shotFile = ref<File | null>(null)
/** 本地预览 URL（`URL.createObjectURL`，组件卸载或换图时释放）。 */
const shotPreviewUrl = ref('')
/** 校验错误（只针对类型与大小）。 */
const shotError = ref('')

const shotFileName = (): string => shotFile.value?.name ?? ''

function releasePreview(): void {
  if (shotPreviewUrl.value) {
    URL.revokeObjectURL(shotPreviewUrl.value)
    shotPreviewUrl.value = ''
  }
}

/**
 * 选择/更换截图。
 *
 * `event.target.value` 会被清空：否则连续选择**同一张图**不会触发 `change`。
 */
function onShotChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  shotError.value = ''

  if (!file) {
    return
  }
  if (!SHOT_ACCEPT.split(',').includes(file.type)) {
    // 只接受明确列出的图片类型；⛔ 不做扩展名猜测
    shotFile.value = null
    releasePreview()
    shotError.value = `仅支持 PNG / JPEG / WebP 图片；未选择任何文件，也未读取其内容。`
    return
  }
  if (file.size > SHOT_MAX_BYTES) {
    shotFile.value = null
    releasePreview()
    shotError.value = `截图不得超过 8 MiB；未读取其内容。`
    return
  }

  releasePreview()
  shotFile.value = file
  // ⚠️ 预览只用浏览器本地对象 URL：⛔ 不发送到任何后端。
  shotPreviewUrl.value = URL.createObjectURL(file)
}

function clearShot(): void {
  releasePreview()
  shotFile.value = null
  shotError.value = ''
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KiB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

onBeforeUnmount(releasePreview)

function keyOf(offering: CourseOffering): string {
  return `${offering.semester}::${offering.course_id}::${offering.class_id}`
}

function isSelected(offering: CourseOffering): boolean {
  return props.selected.some((item) => keyOf(item) === keyOf(offering))
}

function onToggle(offering: CourseOffering): void {
  emit('toggle', offering)
}

function firstMeetingText(offering: CourseOffering): string {
  if (offering.meetings.length === 0) {
    return EMPTY_MEETINGS_DATA_TEXT
  }
  return formatMeetingLine(offering.meetings[0])
}
</script>

<template>
  <div class="uig-form">
    <p class="uig-form__note">
      勾选你<strong>当前已选</strong>的教学班。本区块只负责组织输入，<strong>不进行冲突检测、不判断可行性</strong>；
      教学班供给当前来自{{ dataSourceLabel ? ` ${dataSourceLabel} ` : '当前数据源' }}。
    </p>

    <!-- 手动勾选（原有功能，⛔ 未改动） -->
    <h4 class="uig-field__label" data-testid="schedule-manual-heading">
      手动勾选已有课程
    </h4>

    <div v-if="offerings.length === 0" class="uig-empty" data-testid="schedule-empty">
      当前没有可勾选的教学班记录（教学班数 0）。当前课表可以留空继续。
    </div>

    <div v-else class="uig-schedule-list">
      <label
        v-for="offering in offerings"
        :key="keyOf(offering)"
        class="uig-schedule-row"
        data-testid="schedule-option"
      >
        <input
          type="checkbox"
          :data-testid="`schedule-checkbox-${offering.course_id}-${offering.class_id}`"
          :checked="isSelected(offering)"
          @change="onToggle(offering)"
        />
        <span class="uig-schedule-main">
          <strong>{{ offering.course_name }}</strong>
          <span class="mono uig-schedule-id">{{ offering.course_id }} · {{ offering.class_id }}</span>
        </span>
        <span class="uig-schedule-meta">{{ offering.semester }}</span>
        <span class="uig-schedule-meta">{{ firstMeetingText(offering) }}</span>
      </label>
    </div>

    <p class="uig-field__hint" data-testid="schedule-summary">
      已选 {{ selected.length }} 个教学班（<code class="mono">current_schedule</code> 将以
      <code class="mono">CourseOffering[]</code> 原样输出）。
    </p>

    <!-- ================= 课表截图上传（本轮新增） ================= -->
    <div class="uig-shot" data-testid="schedule-shot">
      <h4 class="uig-field__label">上传课表截图</h4>
      <p class="uig-form__note">
        也可以上传<strong>课表截图</strong>，由后续接入的识别能力读取课程。
        本轮只实现<strong>上传、预览与待识别状态</strong>。
      </p>

      <div class="uig-field">
        <span class="uig-field__label">课表截图（PNG / JPEG / WebP）</span>
        <input
          class="input-text"
          data-testid="schedule-shot-input"
          type="file"
          :accept="SHOT_ACCEPT"
          @change="onShotChange"
        />
        <span v-if="shotError" class="uig-field__error" data-testid="schedule-shot-error">
          {{ shotError }}
        </span>
        <span
          v-else-if="shotFile"
          class="uig-field__hint"
          data-testid="schedule-shot-name"
        >
          已选择：<code class="mono">{{ shotFileName() }}</code>
          （{{ formatBytes(shotFile.size) }}；仅本地预览，未上传、未解析）
        </span>
        <span v-else class="uig-field__hint">尚未选择截图。</span>

        <button
          v-if="shotFile"
          class="button button--small"
          type="button"
          data-testid="schedule-shot-clear"
          @click="clearShot"
        >
          移除截图
        </button>
      </div>

      <!-- 预览：只用本地对象 URL，⛔ 不经过后端 -->
      <div v-if="shotPreviewUrl" class="uig-shot__preview" data-testid="schedule-shot-preview">
        <img :src="shotPreviewUrl" :alt="`课表截图预览：${shotFileName()}`" />
      </div>

      <!--
        ⚠️ 识别状态：本项目**尚未接入图片识别服务** ⇒ 只有"待识别"，
        ⛔ 页面不会出现任何据称来自截图解析的课程，⛔ 也不会自动勾选任何教学班。
      -->
      <p
        v-if="shotFile"
        class="uig-pending"
        data-testid="schedule-shot-status"
        role="note"
      >
        <template v-if="!SHOT_RECOGNITION_AVAILABLE">
          <strong>状态：待识别。</strong>
          当前<strong>尚未接入图片识别服务</strong>，因此不会从截图中读出任何课程。
          请继续使用上方<strong>手动勾选</strong>录入当前课表；
          ⛔ 本页不会用任何写死数据冒充识别结果。
        </template>
        <template v-else>
          <strong>状态：识别通道已启用。</strong>
        </template>
      </p>
    </div>
  </div>
</template>
