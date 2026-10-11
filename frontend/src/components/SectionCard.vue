<script setup lang="ts">
/**
 * 所有展示区块共用的外壳容器：标题 + 副标题 + Mock 标记 + 内容插槽。
 * 保持设计统一与信息层级分明，无业务判断。
 */

import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    /** 是否在标题旁显示 Mock 标记（本 Demo 中四个区块都是 Mock）。 */
    mock?: boolean
    /** 需要强调时使用。 */
    tone?: 'default' | 'attention' | 'primary'
    /** 用于锚点定位与快捷跳转。 */
    sectionId?: string
    /** 数量徽章。 */
    badgeCount?: number
    /**
     * 是否可折叠。
     * ⚠️ 默认 `false` ⇒ **既有调用方的行为一字不变**（内容始终展开）。
     */
    collapsible?: boolean
    /**
     * 可折叠时的初始展开状态（默认展开）。
     * ⚠️ 仅在 `collapsible` 为真时有意义。
     */
    defaultOpen?: boolean
  }>(),
  {
    subtitle: '',
    mock: true,
    tone: 'default',
    sectionId: '',
    badgeCount: undefined,
    collapsible: false,
    defaultOpen: true,
  },
)

// ⚠️ 折叠只影响**展示**：⛔ 不改数据、⛔ 不触发请求、⛔ 不影响任何业务判断。
const open = ref(props.collapsible ? props.defaultOpen : true)

function toggle(): void {
  if (!props.collapsible) {
    return
  }
  open.value = !open.value
}
</script>

<template>
  <section
    :id="sectionId"
    class="card"
    :class="[`card--${tone}`, collapsible ? 'card--collapsible' : '']"
    :data-collapsible="collapsible ? 'true' : undefined"
    :data-open="collapsible ? String(open) : undefined"
  >
    <header class="card__head">
      <div class="card__title-wrap">
        <!--
          折叠开关：⛔ 不是业务按钮，只切换本区块的可见性。
          用 `<button>` 保证键盘可达（`aria-expanded` 同步）。
        -->
        <button
          v-if="collapsible"
          type="button"
          class="card__toggle"
          :aria-expanded="open"
          :data-testid="sectionId ? `${sectionId}-toggle` : undefined"
          @click="toggle"
        >
          <span class="card__toggle-icon" aria-hidden="true">{{ open ? '▾' : '▸' }}</span>
          <h2 class="card__title">{{ title }}</h2>
        </button>
        <h2 v-else class="card__title">{{ title }}</h2>
        <span v-if="badgeCount !== undefined" class="card__count-badge">
          {{ badgeCount }}
        </span>
      </div>
      <span
        v-if="mock"
        class="tag tag--mock"
        title="本区块数据由后端 Mock 通道提供，非教务系统真实快照"
      >
        Mock 数据
      </span>
    </header>

    <p v-if="subtitle" class="card__subtitle">{{ subtitle }}</p>

    <div v-show="open" class="card__body">
      <slot />
    </div>
  </section>
</template>
