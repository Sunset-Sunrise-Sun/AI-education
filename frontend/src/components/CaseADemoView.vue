<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { loadCaseAOfferings, runCaseADemo, type CaseADemoResponse } from '../api/caseADemo'
import {
  addManualScheduleEntry,
  applyManualAttestation,
  buildRealPlanRequest,
  createDefaultUserInputForm,
  invalidateManualAttestation,
  manualScheduleOfferingCount,
  removeCurrentScheduleOffering,
  toggleCurrentScheduleOffering,
  type ManualScheduleEntry,
} from '../state/userInput'
import type { CourseOffering } from '../types/contracts'
import MakeupTaskList from './MakeupTaskList.vue'
import ManualScheduleForm from './ManualScheduleForm.vue'
import PlanResultPanel from './PlanResultPanel.vue'
import PreferenceForm from './PreferenceForm.vue'
import PreferencePanel from './PreferencePanel.vue'
import SectionCard from './SectionCard.vue'

const SEARCH_LIMIT = 20
const form = ref(createDefaultUserInputForm())
const offerings = ref<CourseOffering[]>([])
const transcript = ref<File | null>(null)
const result = ref<CaseADemoResponse | null>(null)
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const campusFilter = ref('')
const weekdayFilter = ref('')
const manualOpen = ref(false)

const manualCount = computed(() => manualScheduleOfferingCount(form.value))
const normalizedQuery = computed(() => searchQuery.value.trim().toLocaleLowerCase())

const campusOptions = computed(() => {
  const campuses = new Set<string>()
  for (const item of offerings.value) {
    for (const meeting of item.meetings) {
      if (meeting.campus?.trim()) campuses.add(meeting.campus.trim())
    }
  }
  return [...campuses].sort((a, b) => a.localeCompare(b, 'zh-CN'))
})

const filteredOfferings = computed(() => {
  const query = normalizedQuery.value
  if (!query) return []

  return offerings.value
    .filter((item) => {
      const haystack = [
        item.course_name,
        item.course_id,
        item.class_id,
        item.teacher ?? '',
      ].join(' ').toLocaleLowerCase()

      if (!haystack.includes(query)) return false
      if (
        campusFilter.value &&
        !item.meetings.some((meeting) => meeting.campus === campusFilter.value)
      ) {
        return false
      }
      if (
        weekdayFilter.value &&
        !item.meetings.some((meeting) => String(meeting.weekday) === weekdayFilter.value)
      ) {
        return false
      }
      return true
    })
    .slice(0, SEARCH_LIMIT)
})

const groupedOfferings = computed(() => {
  const groups = new Map<string, { key: string; courseId: string; courseName: string; credit: number | null; items: CourseOffering[] }>()
  for (const item of filteredOfferings.value) {
    const key = `${item.course_id}::${item.course_name}`
    const existing = groups.get(key)
    if (existing) {
      existing.items.push(item)
      continue
    }
    groups.set(key, {
      key,
      courseId: item.course_id,
      courseName: item.course_name,
      credit: item.credit ?? null,
      items: [item],
    })
  }
  return [...groups.values()]
})

const resultCourseNames = computed(() => {
  const map: Record<string, string> = {}
  for (const item of result.value?.course_offerings ?? []) map[item.course_id] = item.course_name
  return map
})

async function loadOfferings(): Promise<void> {
  error.value = ''
  try {
    offerings.value = await loadCaseAOfferings(form.value.semester)
  } catch (cause) {
    offerings.value = []
    error.value = cause instanceof Error ? cause.message : '教学班数据暂时不可用。'
  }
}

function chooseTranscript(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  transcript.value = file && file.name.toLowerCase().endsWith('.pdf') ? file : null
  error.value = file && transcript.value === null ? '请上传 PDF 格式的中山大学成绩单。' : ''
  result.value = null
}

function keyOf(offering: CourseOffering): string {
  return `${offering.semester}::${offering.course_id}::${offering.class_id}`
}

function isSelected(offering: CourseOffering): boolean {
  return form.value.currentSchedule.some((item) => keyOf(item) === keyOf(offering))
}

function addAcceptedOffering(offering: CourseOffering): void {
  if (isSelected(offering)) return
  const next = toggleCurrentScheduleOffering(form.value.currentSchedule, offering, offerings.value)
  form.value = invalidateManualAttestation(form.value, next).form
}

function updateEntries(entries: ManualScheduleEntry[]): void {
  form.value = invalidateManualAttestation(form.value, undefined, entries).form
}

function addManual(payload: { offering: CourseOffering; entries: ManualScheduleEntry[] }): void {
  form.value = invalidateManualAttestation(
    form.value,
    [...form.value.currentSchedule, payload.offering],
    payload.entries,
  ).form
}

function removeOffering(offering: CourseOffering): void {
  const next = removeCurrentScheduleOffering(form.value.currentSchedule, offering)
  form.value = invalidateManualAttestation(form.value, next).form
}

function teacherText(offering: CourseOffering): string {
  const value = offering.teacher?.trim()
  if (!value) return '任课教师：待核验'
  if (value.toLocaleLowerCase() === 'redacted') return '任课教师：信息已脱敏'
  return `任课教师：${value}`
}

function meetingText(offering: CourseOffering): string {
  if (offering.meetings.length === 0) return '上课时间待核验'
  return offering.meetings.map((meeting) => {
    const weeks = meeting.weeks.length > 0 ? `${meeting.weeks[0]}-${meeting.weeks[meeting.weeks.length - 1]}周` : '周次待核验'
    const campus = meeting.campus ? ` · ${meeting.campus}` : ''
    const classroom = meeting.classroom ? ` · ${meeting.classroom}` : ''
    return `周${meeting.weekday} 第${meeting.start_section}-${meeting.end_section}节 · ${weeks}${campus}${classroom}`
  }).join('；')
}

async function submit(): Promise<void> {
  if (!transcript.value) {
    error.value = '请先上传成绩单 PDF。'
    return
  }
  if (manualCount.value > 0 && !form.value.manualAttestation.attested) {
    error.value = '手工录入的当前课表需要你先明确确认信息由本人提供。'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const request = buildRealPlanRequest(form.value)
    result.value = await runCaseADemo({
      file: transcript.value,
      semester: request.semester,
      currentSchedule: request.current_schedule,
      manualScheduleAttested: form.value.manualAttestation.attested,
      preference: request.preference,
    })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '方案生成失败，请检查输入后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(loadOfferings)
</script>

<template>
  <div class="page case-a-page" data-testid="case-a-demo-view">
    <main class="page__main">
      <section class="case-a-hero">
        <div>
          <p class="case-a-eyebrow">AI 学业路径重构 Agent</p>
          <h1>学航·转衔</h1>
          <p class="case-a-subtitle">面向转专业学生的学业路径重构</p>
          <p class="case-a-lead">
            上传成绩单后，系统将结合目标专业培养方案、真实教学班数据和你的当前课表，
            生成补修与排课建议。
          </p>
        </div>
        <div class="case-a-tags" aria-label="数据与计算范围">
          <span class="tag tag--source-real">真实教学班数据</span>
          <span class="tag">南校园 + 深圳校区</span>
          <span class="tag">RestrictedPlanner</span>
        </div>
      </section>

      <SectionCard
        :mock="false"
        title="第一步：上传成绩单"
        subtitle="上传中山大学成绩单 PDF，用于识别已修课程。"
      >
        <div class="case-a-upload">
          <label class="case-a-file">
            <span>选择成绩单 PDF</span>
            <input data-testid="case-a-pdf" type="file" accept="application/pdf,.pdf" @change="chooseTranscript" />
          </label>
          <p v-if="transcript" class="case-a-success">✓ 已选择：{{ transcript.name }}</p>
          <p class="case-a-secondary">Transcript source: user-uploaded SYSU transcript PDF</p>
        </div>
      </SectionCard>

      <SectionCard
        :mock="false"
        title="第二步：填写当前课表"
        :subtitle="`已加载真实教学班数据 ${offerings.length} 条；数据范围为南校园 + 深圳校区。`"
      >
        <div class="case-a-schedule">
          <div class="case-a-search-panel">
            <label class="case-a-search">
              <span>搜索你已经选中的课程</span>
              <input
                v-model="searchQuery"
                data-testid="case-a-offering-search"
                class="input-text"
                type="search"
                placeholder="搜索课程名称、课程号、任课教师或教学班号"
              />
            </label>

            <div class="case-a-filters">
              <label>
                <span>校区</span>
                <select v-model="campusFilter" data-testid="case-a-campus-filter" class="input-text">
                  <option value="">全部校区</option>
                  <option v-for="campus in campusOptions" :key="campus" :value="campus">{{ campus }}</option>
                </select>
              </label>
              <label>
                <span>上课日</span>
                <select v-model="weekdayFilter" data-testid="case-a-weekday-filter" class="input-text">
                  <option value="">全部上课日</option>
                  <option value="1">周一</option>
                  <option value="2">周二</option>
                  <option value="3">周三</option>
                  <option value="4">周四</option>
                  <option value="5">周五</option>
                  <option value="6">周六</option>
                  <option value="7">周日</option>
                </select>
              </label>
            </div>
          </div>

          <p v-if="!normalizedQuery" class="case-a-empty">请输入课程名称、课程号或任课教师开始搜索，不需要浏览全部教学班。</p>
          <p v-else-if="filteredOfferings.length === 0" class="case-a-empty">没有找到匹配的教学班，可调整筛选条件或手工添加。</p>

          <div v-if="groupedOfferings.length > 0" class="case-a-course-groups">
            <section
              v-for="group in groupedOfferings"
              :key="group.key"
              class="case-a-course-group"
              data-testid="case-a-course-group"
            >
              <header class="case-a-course-group__head">
                <div>
                  <h3>{{ group.courseName }}</h3>
                  <div class="case-a-course-meta">
                    <span>{{ group.courseId }}</span>
                    <span v-if="group.credit !== null">{{ group.credit }} 学分</span>
                    <span>{{ group.items.length }} 个匹配教学班</span>
                  </div>
                </div>
              </header>

              <article
                v-for="item in group.items"
                :key="keyOf(item)"
                class="case-a-class-row"
                data-testid="case-a-search-result"
              >
                <div class="case-a-class-main">
                  <div class="case-a-class-title">
                    <strong>教学班 {{ item.class_id }}</strong>
                    <span class="case-a-teacher">{{ teacherText(item) }}</span>
                  </div>
                  <p>{{ meetingText(item) }}</p>
                  <div class="case-a-class-extra">
                    <span v-if="item.remaining_capacity !== null && item.remaining_capacity !== undefined">
                      剩余容量：{{ item.remaining_capacity }}
                    </span>
                    <span v-if="item.capacity !== null && item.capacity !== undefined">
                      容量：{{ item.capacity }}
                    </span>
                  </div>
                </div>
                <button
                  class="button button--small"
                  type="button"
                  :disabled="isSelected(item)"
                  @click="addAcceptedOffering(item)"
                >
                  {{ isSelected(item) ? '已加入' : '加入当前课表' }}
                </button>
              </article>
            </section>
            <p class="case-a-secondary">最多显示 {{ SEARCH_LIMIT }} 个匹配教学班，请继续输入关键词缩小范围。</p>
          </div>

          <div class="case-a-selected">
            <div class="case-a-selected__head">
              <h3>我的当前课表（{{ form.currentSchedule.length }}）</h3>
            </div>
            <p v-if="form.currentSchedule.length === 0" class="case-a-empty">尚未添加当前课程。</p>
            <article
              v-for="item in form.currentSchedule"
              :key="keyOf(item)"
              class="case-a-selected-item"
              data-testid="case-a-current-schedule-item"
            >
              <div>
                <strong>{{ item.course_name }}</strong>
                <p>{{ item.course_id }} · 教学班 {{ item.class_id }}</p>
                <p>{{ teacherText(item) }}</p>
                <p>{{ meetingText(item) }}</p>
                <p v-if="item.source === 'manual-entry://current-schedule'" class="case-a-warning">
                  该课程信息由你本人填写，未经学校系统核验。
                </p>
              </div>
              <button class="button button--small case-a-remove" type="button" @click="removeOffering(item)">移除</button>
            </article>
          </div>

          <div class="case-a-manual">
            <button
              class="case-a-link-button"
              type="button"
              data-testid="case-a-manual-toggle"
              @click="manualOpen = !manualOpen"
            >
              {{ manualOpen ? '收起手工添加' : '找不到你的教学班？手工添加课程' }}
            </button>

            <div v-if="manualOpen" data-testid="case-a-manual-form">
              <ManualScheduleForm
                :entries="form.manualScheduleEntries"
                :selected="form.currentSchedule"
                :semester="form.semester"
                :current-semester="form.semester"
                provenance-label="本人填写，未经学校系统核验"
                :attested="form.manualAttestation.attested"
                :manual-count="manualCount"
                :attestation-invalidated="form.manualAttestation.invalidated"
                @update:entries="updateEntries"
                @add-row="form.manualScheduleEntries = addManualScheduleEntry(form.manualScheduleEntries, $event)"
                @add-confirmed="addManual"
                @remove="removeOffering"
                @update:attested="form = applyManualAttestation(form, $event)"
              />
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard :mock="false" title="第三步：设置排课偏好" subtitle="根据你的时间、校区和学分偏好调整推荐方案。">
        <PreferenceForm :form="form" @update:form="form = $event" />
      </SectionCard>

      <div class="case-a-submit-wrap">
        <button class="button case-a-submit" type="button" :disabled="loading" data-testid="case-a-submit" @click="submit">
          {{ loading ? '正在生成方案…' : '生成我的转专业补修方案' }}
        </button>
        <p>系统仅提供规划建议，不执行实际选课操作。</p>
      </div>
      <p v-if="error" class="state state--error" role="alert">{{ error }}</p>

      <template v-if="result">
        <SectionCard :mock="false" title="成绩单识别结果" :badge-count="result.transcript.record_count">
          <p>
            已识别 {{ result.transcript.record_count }} 门已修课程，覆盖 {{ result.transcript.term_count }} 个学期。
            成绩单未提供官方课程号时，系统不会自动伪造或强行认定课程身份。
          </p>
        </SectionCard>

        <SectionCard :mock="false" title="补修缺口分析" :badge-count="result.makeup_tasks.length">
          <MakeupTaskList :tasks="result.makeup_tasks" />
        </SectionCard>

        <SectionCard :mock="false" title="本次规划数据">
          <div class="case-a-coverage" data-testid="case-a-coverage-summary">
            <div><strong>{{ result.transcript.record_count }}</strong><span>成绩单课程</span></div>
            <div><strong>{{ result.course_offerings.length }}</strong><span>真实教学班</span></div>
            <div><strong>南 + 深</strong><span>数据范围</span></div>
            <div><strong>否</strong><span>全校完整学期数据</span></div>
          </div>
          <p class="case-a-secondary">
            4069 条教学班仅作为规划候选池使用，不在页面中逐条铺开。
          </p>
        </SectionCard>

        <SectionCard :mock="false" title="排课偏好">
          <PreferencePanel :preference="result.preference" :course-name-by-id="resultCourseNames" />
        </SectionCard>

        <SectionCard :mock="false" title="推荐方案" tone="primary">
          <PlanResultPanel :plan-result="result.plan_result" :course-name-by-id="resultCourseNames" />
        </SectionCard>

        <SectionCard :mock="false" title="数据与计算说明">
          <ul class="case-a-provenance">
            <li>成绩单：用户上传的中山大学成绩单 PDF</li>
            <li>培养方案：Case A 目标专业培养方案</li>
            <li>教学班：南校园 + 深圳校区范围数据</li>
            <li>规划器：RestrictedPlanner 实际执行</li>
            <li>完整学期数据：否</li>
          </ul>
        </SectionCard>
      </template>
    </main>
  </div>
</template>

<style scoped>
.case-a-page {
  background: #f4f7fb;
}

.case-a-hero {
  display: flex;
  justify-content: space-between;
  gap: 28px;
  padding: 30px 32px;
  border: 1px solid #dbe6f5;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, #ffffff 0%, #eef5ff 100%);
  box-shadow: var(--shadow-sm);
}

.case-a-hero h1 {
  margin: 4px 0 6px;
  font-size: 34px;
  color: var(--text);
}

.case-a-eyebrow,
.case-a-subtitle,
.case-a-lead,
.case-a-secondary,
.case-a-empty,
.case-a-submit-wrap p,
.case-a-selected-item p,
.case-a-class-main p {
  margin: 0;
}

.case-a-eyebrow {
  color: #2f72dc;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
}

.case-a-subtitle {
  font-size: 18px;
  font-weight: 600;
  color: #334155;
}

.case-a-lead {
  max-width: 720px;
  margin-top: 12px;
  color: var(--text-muted);
  line-height: 1.7;
}

.case-a-tags {
  display: flex;
  align-content: flex-start;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 320px;
}

.case-a-upload,
.case-a-schedule,
.case-a-manual,
.case-a-selected {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.case-a-file {
  display: flex;
  align-items: center;
  gap: 14px;
  font-weight: 600;
}

.case-a-success {
  margin: 0;
  color: #15803d;
  font-weight: 600;
}

.case-a-secondary {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.case-a-search-panel {
  display: flex;
  align-items: end;
  gap: 14px;
  flex-wrap: wrap;
  padding: 14px;
  background: #f8fbff;
  border: 1px solid #d9e6f7;
  border-radius: var(--radius);
}

.case-a-search {
  display: flex;
  flex: 1 1 520px;
  flex-direction: column;
  gap: 8px;
  font-weight: 600;
}

.case-a-search .input-text {
  width: 100%;
  padding: 11px 14px;
  font-size: 14px;
}

.case-a-filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.case-a-filters label {
  display: flex;
  min-width: 130px;
  flex-direction: column;
  gap: 6px;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.case-a-filters .input-text {
  padding: 9px 30px 9px 10px;
}

.case-a-empty {
  padding: 14px 16px;
  color: var(--text-muted);
  background: #f8fafc;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
}

.case-a-course-groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.case-a-course-group {
  overflow: hidden;
  border: 1px solid #d8e3f0;
  border-radius: var(--radius);
  background: #fff;
}

.case-a-course-group__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 16px;
  background: #f6f9fd;
  border-bottom: 1px solid #e2e8f0;
}

.case-a-course-group__head h3 {
  margin: 0;
  color: #3276df;
  font-size: 17px;
  font-weight: 700;
}

.case-a-course-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.case-a-course-meta span {
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef4fd;
  color: #64748b;
  font-size: 11px;
}

.case-a-class-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 13px 16px;
  border-bottom: 1px solid #edf1f6;
}

.case-a-class-row:last-child {
  border-bottom: 0;
}

.case-a-class-row:hover {
  background: #fbfdff;
}

.case-a-class-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 6px;
}

.case-a-class-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.case-a-class-title strong {
  color: #1e293b;
}

.case-a-teacher {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.case-a-class-main p {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.case-a-class-extra {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 11px;
}

.case-a-selected {
  margin-top: 8px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.case-a-selected__head h3 {
  margin: 0;
  font-size: 16px;
}

.case-a-selected-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.case-a-selected-item p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.case-a-warning {
  color: #b45309 !important;
  font-weight: 600;
}

.case-a-remove {
  background: #64748b;
}

.case-a-link-button {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-weight: 600;
  cursor: pointer;
}

.case-a-submit-wrap {
  display: flex;
  align-items: center;
  gap: 16px;
}

.case-a-submit {
  padding: 12px 24px;
  font-size: 15px;
}

.case-a-submit-wrap p {
  color: var(--text-muted);
  font-size: 12px;
}

.case-a-coverage {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.case-a-coverage div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #f8fafc;
}

.case-a-coverage strong {
  font-size: 22px;
  color: var(--text);
}

.case-a-coverage span {
  color: var(--text-muted);
  font-size: 12px;
}

.case-a-provenance {
  margin: 0;
  padding-left: 20px;
  color: #475569;
  line-height: 1.9;
}

@media (max-width: 760px) {
  .case-a-hero,
  .case-a-class-row,
  .case-a-selected-item,
  .case-a-submit-wrap {
    align-items: flex-start;
    flex-direction: column;
  }

  .case-a-search-panel {
    align-items: stretch;
  }

  .case-a-filters {
    width: 100%;
  }

  .case-a-filters label {
    flex: 1 1 130px;
  }

  .case-a-coverage {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
</style>
