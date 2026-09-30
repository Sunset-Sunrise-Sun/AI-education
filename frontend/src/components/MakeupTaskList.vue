<script setup lang="ts">
import type { MakeupTask } from '../types/contracts'
import { MAKEUP_STATUS_HINT, MAKEUP_STATUS_LABEL, displayOrDash } from '../utils/labels'

/**
 * 只是把 Curriculum 模块本应输出的 MakeupTask 原样展示出来。
 * 前端不做任何补修判定，也不新增/推断补修结论。
 */
defineProps<{
  tasks: MakeupTask[]
}>()
</script>

<template>
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th scope="col">课程名称</th>
          <th scope="col">课程号</th>
          <th scope="col">学分</th>
          <th scope="col">状态</th>
          <th scope="col">建议学期</th>
          <th scope="col">判定说明</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="task in tasks" :key="task.course_id">
          <td class="cell-strong">{{ task.course_name }}</td>
          <td class="mono">{{ task.course_id }}</td>
          <td class="num">{{ task.credit }}</td>
          <td>
            <span class="tag" :class="`tag--status-${task.status}`">
              {{ MAKEUP_STATUS_LABEL[task.status] }}
            </span>
            <span class="cell-hint">{{ MAKEUP_STATUS_HINT[task.status] }}</span>
          </td>
          <td class="num">{{ displayOrDash(task.recommended_semester) }}</td>
          <td class="cell-reason">{{ displayOrDash(task.reason) }}</td>
        </tr>
        <tr v-if="tasks.length === 0">
          <td colspan="6" class="empty">后端返回的补修任务列表为空。</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
