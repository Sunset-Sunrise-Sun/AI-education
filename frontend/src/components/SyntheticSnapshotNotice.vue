<script setup lang="ts">
import { computed } from 'vue'
import {
  SYNTHETIC_SNAPSHOT_LABEL,
  SYNTHETIC_SNAPSHOT_LIMITATION,
  SYNTHETIC_SNAPSHOT_NOTE_MOCK,
  SYNTHETIC_SNAPSHOT_NOTE_REAL,
} from '../utils/labels'

/**
 * 教学班演示快照的**强制披露**（比赛演示）。
 *
 * 边界：
 * - 只做展示：不判断数据真伪、不参与任何业务分支、不请求任何接口；
 * - 说明文案随**规划结果来源**切换：
 *   `real` ⇒ 逐字口径“其余链路仍通过实际系统链路执行”；
 *   `mock` ⇒ 如实说明“尚未提交真实规划请求，规划结果同样来自 Mock 演示通道”；
 * - ⛔ 不隐藏、不折叠主标签（`<details>` 只承载额外背景说明）。
 */
const props = defineProps<{
  /** 规划结果来源：`real` = 本次已成功提交真实规划，`mock` = 仍为演示通道结果。 */
  planResultMode: 'mock' | 'real'
}>()

const note = computed(() =>
  props.planResultMode === 'real' ? SYNTHETIC_SNAPSHOT_NOTE_REAL : SYNTHETIC_SNAPSHOT_NOTE_MOCK,
)
</script>

<template>
  <div class="snapshot-notice" data-testid="synthetic-snapshot-notice">
    <p class="snapshot-notice__head">
      <strong class="snapshot-notice__label" data-testid="synthetic-snapshot-label">
        {{ SYNTHETIC_SNAPSHOT_LABEL }}
      </strong>
      <span class="snapshot-notice__note" data-testid="synthetic-snapshot-note">{{ note }}</span>
    </p>
    <details class="snapshot-notice__details">
      <summary>为什么教学班使用演示快照？</summary>
      <p class="snapshot-notice__limitation" data-testid="synthetic-snapshot-limitation">
        {{ SYNTHETIC_SNAPSHOT_LIMITATION }}
      </p>
    </details>
  </div>
</template>
