<script setup lang="ts">
import type { Preference } from '../types/contracts'
import { displayOrDash, formatSections, formatWeekday } from '../utils/labels'

/**
 * 只把 Preference 原样显示出来。
 * 前端不做自然语言解析，也不因为偏好而改动方案——偏好的解读与求解都是后端/Planner 的事。
 */
defineProps<{
  preference: Preference
}>()
</script>

<template>
  <dl class="kv">
    <div class="kv__row">
      <dt>学分上限（max_credit）</dt>
      <dd class="num">{{ displayOrDash(preference.max_credit) }}</dd>
    </div>

    <div class="kv__row">
      <dt>避免跨校区（avoid_cross_campus）</dt>
      <dd>{{ preference.avoid_cross_campus ? '是' : '否' }}</dd>
    </div>

    <div class="kv__row">
      <dt>优先课程（preferred_courses）</dt>
      <dd>
        <template v-if="preference.preferred_courses && preference.preferred_courses.length">
          <span v-for="courseId in preference.preferred_courses" :key="courseId" class="chip mono">
            {{ courseId }}
          </span>
        </template>
        <span v-else>—</span>
      </dd>
    </div>

    <div class="kv__row">
      <dt>避开时段（avoid_times）</dt>
      <dd>
        <template v-if="preference.avoid_times && preference.avoid_times.length">
          <span
            v-for="(block, index) in preference.avoid_times"
            :key="`${block.weekday}-${block.start_section}-${index}`"
            class="chip"
          >
            {{ formatWeekday(block.weekday) }}
            {{ formatSections(block.start_section, block.end_section) }}
          </span>
        </template>
        <span v-else>—</span>
      </dd>
    </div>

    <div class="kv__row">
      <dt>备注（notes）</dt>
      <dd class="cell-reason">{{ displayOrDash(preference.notes) }}</dd>
    </div>
  </dl>
</template>
