<script setup lang="ts">
/**
 * 所有展示区块共用的外壳容器：标题 + 副标题 + Mock 标记 + 内容插槽。
 * 保持设计统一与信息层级分明，无业务判断。
 */
withDefaults(
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
  }>(),
  {
    subtitle: '',
    mock: true,
    tone: 'default',
    sectionId: '',
    badgeCount: undefined,
  },
)
</script>

<template>
  <section
    :id="sectionId"
    class="card"
    :class="`card--${tone}`"
  >
    <header class="card__head">
      <div class="card__title-wrap">
        <h2 class="card__title">{{ title }}</h2>
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

    <div class="card__body">
      <slot />
    </div>
  </section>
</template>
