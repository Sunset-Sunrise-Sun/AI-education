<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CourseOffering } from '../types/contracts'
import {
  EMPTY_MEETINGS_DATA_TEXT,
  displayOrDash,
  formatMeetingLine,
} from '../utils/labels'

/**
 * 展示 Course Data 模块输出的开课教学班数据，按课程进行结构化分组。
 *
 * 核心设计边界：
 * - 支持 DG-01 多段排课（meetings[]），逐段如实展示；
 * - 满足 DG-07D 规范：当 meetings=[] 时，中性显示“当前数据中无排课信息”，
 *   严禁使用“无课”、“无需上课”、“异步课程”、“尚未排课”、“无冲突”等推断词；
 * - 前端不执行冲突判断、不筛选教学班、不评价优劣。
 */
const props = defineProps<{
  offerings: CourseOffering[]
}>()

const searchQuery = ref('')

interface CourseGroup {
  courseId: string
  courseName: string
  credit: number | null
  offerings: CourseOffering[]
}

const allGroups = computed<CourseGroup[]>(() => {
  const byCourse = new Map<string, CourseGroup>()

  for (const offering of props.offerings) {
    const existing = byCourse.get(offering.course_id)
    if (existing) {
      existing.offerings.push(offering)
      if (existing.credit === null && offering.credit !== undefined && offering.credit !== null) {
        existing.credit = offering.credit
      }
      continue
    }
    byCourse.set(offering.course_id, {
      courseId: offering.course_id,
      courseName: offering.course_name,
      credit: offering.credit ?? null,
      offerings: [offering],
    })
  }

  return [...byCourse.values()]
})

const filteredGroups = computed<CourseGroup[]>(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) {
    return allGroups.value
  }

  return allGroups.value
    .map((group) => {
      const matchGroup =
        group.courseName.toLowerCase().includes(q) ||
        group.courseId.toLowerCase().includes(q)

      if (matchGroup) {
        return group
      }

      // 搜索教学班号或教师
      const matchedOfferings = group.offerings.filter(
        (o) =>
          o.class_id.toLowerCase().includes(q) ||
          (o.teacher && o.teacher.toLowerCase().includes(q)),
      )

      if (matchedOfferings.length > 0) {
        return {
          ...group,
          offerings: matchedOfferings,
        }
      }

      return null
    })
    .filter((g): g is CourseGroup => g !== null)
})

const totalOfferingsCount = computed(() => props.offerings.length)
</script>

<template>
  <div class="offering-container">
    <!-- 顶部概览与快速筛选 -->
    <div class="section-toolbar">
      <div class="stats-pills">
        <span class="stat-pill">
          覆盖课程 <strong class="num">{{ allGroups.length }}</strong> 门
        </span>
        <span class="stat-pill">
          候选教学班 <strong class="num">{{ totalOfferingsCount }}</strong> 个
        </span>
      </div>

      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索课程名称 / 课程号 / 教师 / 教学班..."
          class="input-text"
        />
        <button
          v-if="searchQuery"
          class="btn-clear"
          type="button"
          title="清除搜索"
          @click="searchQuery = ''"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- 课程分组列表 -->
    <div class="group-list">
      <article
        v-for="group in filteredGroups"
        :key="group.courseId"
        class="group-card"
      >
        <header class="group-card__header">
          <div class="group-card__meta">
            <h3 class="group-card__title">{{ group.courseName }}</h3>
            <span class="mono group-card__id">{{ group.courseId }}</span>
            <span v-if="group.credit !== null" class="badge-credit">
              {{ group.credit }} 学分
            </span>
          </div>
          <span class="group-card__badge">
            {{ group.offerings.length }} 个开设教学班
          </span>
        </header>

        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th scope="col" style="width: 140px;">教学班号</th>
                <th scope="col" style="width: 100px;">授课教师</th>
                <th scope="col">排课与时间地点安排</th>
                <th scope="col" style="width: 120px;">容量情况</th>
                <th scope="col" style="width: 90px;">数据源</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="offering in group.offerings"
                :key="offering.class_id"
                class="offering-row"
              >
                <td class="mono cell-class-id">
                  {{ offering.class_id }}
                </td>
                <td class="cell-teacher">
                  {{ displayOrDash(offering.teacher) }}
                </td>
                <td class="cell-schedule">
                  <!-- 满足 DG-07D：当 meetings 为空时使用中性表述 -->
                  <div
                    v-if="offering.meetings && offering.meetings.length > 0"
                    class="meeting-list"
                  >
                    <div
                      v-for="(meeting, idx) in offering.meetings"
                      :key="idx"
                      class="meeting-item"
                    >
                      <span class="meeting-bullet">•</span>
                      <span class="meeting-text">{{ formatMeetingLine(meeting) }}</span>
                    </div>
                  </div>
                  <div v-else class="meeting-empty-wrapper">
                    <span class="tag tag--neutral-data" title="当前数据源快照中无时间地点字段">
                      {{ EMPTY_MEETINGS_DATA_TEXT }}
                    </span>
                  </div>
                </td>
                <td class="num cell-capacity">
                  <div class="capacity-box">
                    <span
                      class="capacity-remain"
                      :class="{
                        'capacity-remain--low':
                          offering.remaining_capacity !== null &&
                          offering.remaining_capacity !== undefined &&
                          offering.remaining_capacity <= 5,
                      }"
                    >
                      {{ displayOrDash(offering.remaining_capacity) }}
                    </span>
                    <span class="capacity-total">/ {{ displayOrDash(offering.capacity) }}</span>
                  </div>
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

      <div v-if="filteredGroups.length === 0 && searchQuery" class="empty-state">
        <p>未找到匹配 “{{ searchQuery }}” 的课程或教学班。</p>
        <button class="button button--small" type="button" @click="searchQuery = ''">
          清除筛选条件
        </button>
      </div>

      <div v-else-if="allGroups.length === 0" class="empty-state">
        <p>后端返回的教学班列表为空。</p>
      </div>
    </div>
  </div>
</template>
