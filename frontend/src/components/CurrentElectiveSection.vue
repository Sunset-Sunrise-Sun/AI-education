<script setup lang="ts">
import { computed, ref } from 'vue'
import type {
  AppliedElectiveItem,
  CurrentElectiveItem,
  CurrentSemesterLoad,
  RejectedOverrideItem,
} from '../api/caseADemo'
import type { CourseOffering } from '../types/contracts'

/**
 * 本学期专业选修建议 —— **可加入方案**的交互区。
 *
 * 语义（替代含糊的"加入考虑"）：
 *
 * - `[加入本学期方案]` 只会提交**用户意图**（精确 `semester + course_id + class_id`），
 *   由页面走同一条 recompute 管线；⛔ 前端不自己加学分、不改课表；
 * - 加入后显示 `✓ 已加入本学期方案` + `[撤销]`；
 * - **唯一 CLEAR 教学班**：可直接作为建议教学班加入（仍需显式点击）；
 * - **多个 CLEAR 教学班**：必须由用户显式选择教学班，⛔ 绝不自动挑一个；
 * - **只有 UNKNOWN / CONFLICT**：⛔ 不提供任何加入按钮，并说明原因；
 * - 只按精确 `course_id` 匹配培养方案选修组，⛔ 不做名称/模糊/等同推断。
 */
const props = withDefaults(
  defineProps<{
    recommendations?: CurrentElectiveItem[] | null
    load?: CurrentSemesterLoad | null
    /** 本轮已加入方案的选修（来自服务端 recompute 结果）。 */
    applied?: AppliedElectiveItem[] | null
    /** 已接受教学班（用于"多个 CLEAR"时让用户挑教学班）。 */
    offerings?: CourseOffering[]
    /** 服务端拒绝的选修选择（如实展示）。 */
    rejected?: RejectedOverrideItem[] | null
    /** 正在重算（禁用交互，⛔ 不做乐观更新）。 */
    pending?: boolean
    /** 默认学期（用于提交精确身份）。 */
    semester?: string
  }>(),
  {
    recommendations: null,
    load: null,
    applied: null,
    offerings: () => [],
    rejected: null,
    pending: false,
    semester: '',
  },
)

const emit = defineEmits<{
  (event: 'add', payload: { courseId: string; classId: string; semester: string }): void
  (event: 'remove', payload: { courseId: string; classId: string; semester: string }): void
}>()

const items = computed(() => props.recommendations ?? [])
const appliedItems = computed(() => props.applied ?? [])
const rejections = computed(() => props.rejected ?? [])
const appliedIds = computed(() => new Set(appliedItems.value.map((i) => i.course_id)))

/** 用户为"多个 CLEAR"课程显式选定的教学班。 */
const chosenSections = ref<Record<string, string>>({})

/** 该课程在本学期的已接受教学班，且服务端判定为无冲突（用于显式选择）。 */
function clearSections(courseId: string): CourseOffering[] {
  return props.offerings.filter((o) => o.course_id === courseId && o.meetings.length > 0)
}

function chooseSection(courseId: string, classId: string): void {
  chosenSections.value = { ...chosenSections.value, [courseId]: classId }
}

/** 可加入吗？唯一 CLEAR ⇒ 用它；多个 CLEAR ⇒ 必须已显式选班。 */
function canAdd(item: CurrentElectiveItem): boolean {
  if (item.clear_class_count === 0) return false
  if (item.unique_clear_class_id) return true
  return Boolean(chosenSections.value[item.course_id])
}

function targetClassId(item: CurrentElectiveItem): string {
  return item.unique_clear_class_id ?? chosenSections.value[item.course_id] ?? ''
}

function onAdd(item: CurrentElectiveItem): void {
  const classId = targetClassId(item)
  if (!classId) return
  emit('add', { courseId: item.course_id, classId, semester: props.semester })
}

function onRemove(item: AppliedElectiveItem): void {
  emit('remove', {
    courseId: item.course_id,
    classId: item.class_id,
    semester: props.semester,
  })
}

const loadLine = computed(() => {
  const load = props.load
  if (!load) return ''
  return [
    `当前已选 ${load.selected_credit} 学分`,
    `建议新增补修 ${load.suggested_makeup_credit} 学分`,
    `已加入选修 ${appliedItems.value.reduce((sum, i) => sum + i.credit, 0)} 学分`,
    `预计合计 ${load.projected_total_credit} 学分`,
  ].join(' · ')
})
</script>

<template>
  <div class="elective" data-testid="case-a-current-electives">
    <!-- 已加入方案的选修 -->
    <section v-if="appliedItems.length > 0" class="elective__applied" data-testid="elective-applied">
      <h4 class="elective__applied-title">已加入本学期方案（{{ appliedItems.length }} 门）</h4>
      <ul class="elective__list">
        <li
          v-for="item in appliedItems"
          :key="`${item.course_id}-${item.class_id}`"
          class="elective__item elective__item--applied"
          data-testid="elective-applied-item"
        >
          <div class="elective__head">
            <span class="elective__check">✓</span>
            <strong data-testid="elective-applied-name">{{ item.course_name }}</strong>
            <span class="mono elective__code">{{ item.course_id }}</span>
            <span class="mono elective__code">教学班 {{ item.class_id }}</span>
            <span class="tag">{{ item.credit }} 学分</span>
          </div>
          <p class="elective__meta" data-testid="elective-applied-state">
            已加入本学期方案（规划草稿，⛔ 不代表已完成教务选课）
          </p>
          <div class="elective__actions">
            <button
              class="button button--small button--ghost"
              type="button"
              :disabled="pending"
              :data-testid="`elective-remove-${item.course_id}`"
              @click="onRemove(item)"
            >
              撤销
            </button>
          </div>
        </li>
      </ul>
      <p v-if="loadLine" class="elective__load" data-testid="case-a-credit-load">{{ loadLine }}</p>
      <p v-if="load" class="elective__policy" data-testid="case-a-credit-policy">
        {{ load.policy_note }}
      </p>
    </section>

    <!-- 服务端拒绝的选择：如实展示原因，⛔ 不静默丢弃 -->
    <ul v-if="rejections.length > 0" class="elective__rejections" data-testid="elective-rejections">
      <li v-for="item in rejections" :key="`${item.course_id}-${item.reason}`">
        {{ item.course_id }}：{{ item.reason }}
      </li>
    </ul>

    <p v-if="items.length === 0" class="elective__empty" data-testid="case-a-current-electives-empty">
      本学期在已接受的教学班中，暂时没有可加入方案的专业选修课程。
    </p>

    <template v-else>
      <p class="elective__intro" data-testid="elective-intro">
        以下为本学期<strong>可加入方案</strong>的专业选修；⛔ 系统不会替你选课，
        加入后仅是规划草稿，不代表已完成教务选课。
      </p>

      <ul class="elective__list">
        <li
          v-for="item in items"
          :key="item.course_id"
          class="elective__item"
          data-testid="case-a-elective-item"
        >
          <div class="elective__head">
            <strong data-testid="case-a-elective-name">{{ item.course_name }}</strong>
            <span class="mono elective__code">{{ item.course_id }}</span>
            <span class="tag">{{ item.credit }} 学分</span>
          </div>
          <p class="elective__meta" data-testid="case-a-elective-status">
            {{ item.conflict_label }}
          </p>
          <p class="elective__meta">
            本学期可用教学班 {{ item.available_class_count }} 个
            <template v-if="item.unknown_schedule_class_count > 0">
              · {{ item.unknown_schedule_class_count }} 个排课信息待核验
            </template>
          </p>

          <!-- 唯一 CLEAR：可以直接加入（仍必须显式点击） -->
          <p
            v-if="item.unique_clear_class_id"
            class="elective__clear"
            data-testid="case-a-elective-unique-class"
          >
            建议教学班：<span class="mono">{{ item.unique_clear_class_id }}</span>
          </p>

          <!-- 多个 CLEAR：必须由用户显式选择教学班 -->
          <template v-else-if="item.clear_class_count > 1">
            <p class="elective__meta" data-testid="elective-multi-clear-hint">
              有 {{ item.clear_class_count }} 个可用教学班，请选择其中一个：
            </p>
            <ul class="elective__sections">
              <li
                v-for="section in clearSections(item.course_id)"
                :key="section.class_id"
                class="elective__section"
              >
                <label :data-testid="`elective-section-${item.course_id}-${section.class_id}`">
                  <input
                    type="radio"
                    :name="`elective-section-${item.course_id}`"
                    :value="section.class_id"
                    :checked="chosenSections[item.course_id] === section.class_id"
                    @change="chooseSection(item.course_id, section.class_id)"
                  />
                  <span class="mono">{{ section.class_id }}</span>
                </label>
              </li>
            </ul>
          </template>

          <!-- 只有 UNKNOWN / CONFLICT：⛔ 不提供任何加入动作 -->
          <p v-else class="elective__blocked" data-testid="elective-blocked-reason">
            该课程当前没有已确认无冲突的教学班，因此<strong>无法加入本学期方案</strong>。
            系统不会替你选择一个可能冲突或排课信息未知的教学班。
          </p>

          <div v-if="item.clear_class_count > 0" class="elective__actions">
            <button
              class="button button--small"
              type="button"
              :disabled="!canAdd(item) || pending || appliedIds.has(item.course_id)"
              :data-testid="`elective-add-${item.course_id}`"
              @click="onAdd(item)"
            >
              {{ appliedIds.has(item.course_id) ? '✓ 已加入本学期方案' : '加入本学期方案' }}
            </button>
          </div>
        </li>
      </ul>

      <p v-if="loadLine" class="elective__load" data-testid="case-a-credit-load">{{ loadLine }}</p>
      <p v-if="load" class="elective__policy" data-testid="case-a-credit-policy">
        {{ load.policy_note }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.elective {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.elective__empty,
.elective__intro,
.elective__meta,
.elective__clear,
.elective__load,
.elective__policy,
.elective__applied-title,
.elective__blocked {
  margin: 0;
}

.elective__empty,
.elective__intro,
.elective__policy {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.elective__applied {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: var(--radius);
}

.elective__applied-title {
  font-size: 14px;
  color: #166534;
}

.elective__item--applied {
  border-color: #bbf7d0;
  background: #fff;
}

.elective__check {
  color: #16a34a;
  font-weight: 700;
}

.elective__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.elective__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.elective__head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.elective__code {
  color: var(--text-muted);
  font-size: 12px;
}

.elective__meta {
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
}

.elective__clear {
  color: #166534;
  font-size: 12px;
}

.elective__blocked {
  color: #b45309;
  font-size: 12px;
  line-height: 1.7;
}

.elective__sections {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.elective__section label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  cursor: pointer;
}

.elective__load {
  font-size: 13px;
  font-weight: 700;
}

.elective__rejections {
  margin: 0;
  padding-left: 18px;
  color: #b45309;
  font-size: 12px;
}

.elective__actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
</style>
