<script setup lang="ts">
/**
 * 所有展示区块共用的外壳：标题 + Mock 标记 + 内容插槽。
 * 存在的意义只是让四个区块的样式和行为保持一致，不含任何业务逻辑。
 */
withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    /** 是否在标题旁显示 Mock 标记（本 Demo 中四个区块都是 Mock）。 */
    mock?: boolean
    /** 需要强调"这里有必须人工确认的内容"时使用。 */
    tone?: 'default' | 'attention'
  }>(),
  {
    subtitle: '',
    mock: true,
    tone: 'default',
  },
)
</script>

<template>
  <section class="card" :class="`card--${tone}`">
    <header class="card__head">
      <h2 class="card__title">{{ title }}</h2>
      <span v-if="mock" class="tag tag--mock" title="本条数据来自后端 Mock 通道，非真实教务数据">
        Mock
      </span>
    </header>

    <p v-if="subtitle" class="card__subtitle">{{ subtitle }}</p>

    <div class="card__body">
      <slot />
    </div>
  </section>
</template>
