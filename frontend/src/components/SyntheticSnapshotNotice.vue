<script setup lang="ts">
import { computed } from 'vue'
import {
  DEMO_DATA_DISCLOSURE_UI,
  SYNTHETIC_SNAPSHOT_LABEL,
  SYNTHETIC_SNAPSHOT_LIMITATION,
  SYNTHETIC_SNAPSHOT_NOTE_MOCK,
  SYNTHETIC_SNAPSHOT_NOTE_REAL,
} from '../utils/labels'

/**
 * 演示数据与来源披露（比赛演示，⛔ 强制可见）。
 *
 * 边界：
 * - 只做展示：不判断数据真伪、不参与任何业务分支、不请求任何接口；
 * - **两行结构**：
 *   ① 与模式无关的逐字披露（`DEMO_DATA_DISCLOSURE_UI`）：说明 Mock 回放 / 计算模式 / 输入来源需逐项核验；
 *   ② 随**规划结果来源**切换的精确说明：
 *      `real` ⇒ "实际代码计算（Actual API computation）"，并明确⛔ 实际执行 ≠ 输入真实；
 *      `mock` ⇒ 如实说明"预置样例、未执行本次求解"；
 * - ⛔ 不隐藏、不折叠主标签（`<details>` 只承载额外背景说明）；
 * - ⛔ 不把"教学班是 Synthetic"读成"其余输入都真实"。
 */
const props = defineProps<{
  /** 规划结果来源：`real` = 本页已成功提交 `POST /api/v1/plan`；`mock` = 仍为回放结果。 */
  planResultMode: 'mock' | 'real'
}>()

const modeNote = computed(() =>
  props.planResultMode === 'real' ? SYNTHETIC_SNAPSHOT_NOTE_REAL : SYNTHETIC_SNAPSHOT_NOTE_MOCK,
)
</script>

<template>
  <div class="snapshot-notice" data-testid="synthetic-snapshot-notice">
    <p class="snapshot-notice__head">
      <strong class="snapshot-notice__label" data-testid="synthetic-snapshot-label">
        {{ SYNTHETIC_SNAPSHOT_LABEL }}
      </strong>
      <span class="snapshot-notice__note" data-testid="demo-data-disclosure">
        {{ DEMO_DATA_DISCLOSURE_UI }}
      </span>
    </p>
    <p class="snapshot-notice__mode" data-testid="synthetic-snapshot-note">{{ modeNote }}</p>
    <details class="snapshot-notice__details">
      <summary>为什么教学班使用演示快照？</summary>
      <p class="snapshot-notice__limitation" data-testid="synthetic-snapshot-limitation">
        {{ SYNTHETIC_SNAPSHOT_LIMITATION }}
      </p>
    </details>
  </div>
</template>
