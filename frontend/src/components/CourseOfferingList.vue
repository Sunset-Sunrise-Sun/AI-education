<script setup lang="ts">
import { computed } from 'vue'
import type { CourseOffering } from '../types/contracts'
import { displayOrDash, formatSections, formatWeekday, formatWeeks } from '../utils/labels'

/**
 * 只展示 Course Data 模块本应输出的教学班，按课程分组。
 *
 * 前端**不做**冲突检测、不比较教学班优劣、不推荐选哪个班——
 * 那些属于 Planner 模块。"同课多个教学班"只是如实并排列出。
 */
const props = defineProps<{
  offerings: CourseOffering[]
}>()

interface CourseGroup {
  courseId: string
  courseName: string
  offerings: CourseOffering[]
}

const groups = computed<CourseGroup[]>(() => {
  const byCourse = new Map<string, CourseGroup>()

  for (const offering of props.offerings) {
    const existing = byCourse.get(offering.course_id)
    if (existing) {
      existing.offerings.push(offering)
      continue
    }
    byCourse.set(offering.course_id, {
      courseId: offering.course_id,
      courseName: offering.course_name,
      offerings: [offering],
    })
  }

  return [...byCourse.values()]
})
</script>

<template>
  <div class="group-list">
    <article v-for="group in groups" :key="group.courseId" class="group">
      <h3 class="group__title">
        {{ group.courseName }}
        <span class="mono group__id">{{ group.courseId }}</span>
        <span class="group__count">{{ group.offerings.length }} 个教学班</span>
      </h3>

      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th scope="col">教学班号</th>
              <th scope="col">教师</th>
              <th scope="col">上课时间</th>
              <th scope="col">节次</th>
              <th scope="col">周次</th>
              <th scope="col">校区 / 教室</th>
              <th scope="col">剩余容量</th>
              <th scope="col">数据来源</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="offering in group.offerings" :key="offering.class_id">
              <td class="mono">{{ offering.class_id }}</td>
              <td>{{ displayOrDash(offering.teacher) }}</td>
              <td>{{ formatWeekday(offering.weekday) }}</td>
              <td class="num">{{ formatSections(offering.start_section, offering.end_section) }}</td>
              <td>{{ formatWeeks(offering.weeks) }}</td>
              <td>
                {{ displayOrDash(offering.campus) }}
                <span class="cell-hint">{{ displayOrDash(offering.classroom) }}</span>
              </td>
              <td class="num">
                {{ displayOrDash(offering.remaining_capacity) }}
                <span class="cell-hint">/ {{ displayOrDash(offering.capacity) }}</span>
              </td>
              <td>
                <span class="tag" :class="`tag--source-${offering.data_source}`">
                  {{ offering.data_source }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <p v-if="groups.length === 0" class="empty">后端返回的教学班列表为空。</p>
  </div>
</template>
