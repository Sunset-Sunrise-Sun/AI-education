<script setup lang="ts">
import { APP_SUBTITLE, APP_TITLE } from '../config'

defineProps<{
  /** 后端响应头 X-Data-Source 的值；请求失败时为 null。 */
  dataSource: string | null
}>()
</script>

<template>
  <header class="topbar">
    <div class="topbar__brand">
      <h1 class="topbar__title">{{ APP_TITLE }}</h1>
      <p class="topbar__subtitle">{{ APP_SUBTITLE }}</p>
    </div>

    <dl class="topbar__meta">
      <div class="topbar__meta-item">
        <dt>当前数据</dt>
        <dd>Mock Demo</dd>
      </div>
      <div class="topbar__meta-item">
        <dt>当前状态</dt>
        <dd>演示环境</dd>
      </div>
      <div class="topbar__meta-item">
        <dt>后端来源标记</dt>
        <dd class="mono">{{ dataSource ?? '未获取到' }}</dd>
      </div>
    </dl>
  </header>

  <p class="mock-banner" role="alert">
    <strong>当前展示的是 Mock 演示数据，不是真实教务数据。</strong>
    页面中的课程、教学班、教师、培养方案与最终方案<strong>全部为人工虚构</strong>，
    仅用于演示系统能力，<strong>不能作为真实选课或补修决策的依据</strong>。
  </p>
</template>
