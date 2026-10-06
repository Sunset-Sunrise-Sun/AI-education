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
import CourseOfferingList from './CourseOfferingList.vue'
import MakeupTaskList from './MakeupTaskList.vue'
import ManualScheduleForm from './ManualScheduleForm.vue'
import PlanResultPanel from './PlanResultPanel.vue'
import PreferenceForm from './PreferenceForm.vue'
import PreferencePanel from './PreferencePanel.vue'
import SectionCard from './SectionCard.vue'

const form = ref(createDefaultUserInputForm())
const offerings = ref<CourseOffering[]>([])
const transcript = ref<File | null>(null)
const result = ref<CaseADemoResponse | null>(null)
const loading = ref(false)
const error = ref('')

const manualCount = computed(() => manualScheduleOfferingCount(form.value))

async function loadOfferings(): Promise<void> {
  error.value = ''
  try {
    offerings.value = await loadCaseAOfferings(form.value.semester)
  } catch (cause) {
    offerings.value = []
    error.value = cause instanceof Error ? cause.message : 'Case A teaching classes are unavailable.'
  }
}

function chooseTranscript(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  transcript.value = file && file.name.toLowerCase().endsWith('.pdf') ? file : null
  error.value = file && transcript.value === null ? 'Only a SYSU transcript PDF is accepted.' : ''
  result.value = null
}

function toggleOffering(offering: CourseOffering): void {
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

async function submit(): Promise<void> {
  if (!transcript.value) {
    error.value = 'Select the SYSU transcript PDF first.'
    return
  }
  if (manualCount.value > 0 && !form.value.manualAttestation.attested) {
    error.value = 'Manual current schedule requires explicit student confirmation.'
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
    error.value = cause instanceof Error ? cause.message : 'Case A planning failed.'
  } finally {
    loading.value = false
  }
}

onMounted(loadOfferings)
</script>

<template>
  <div class="page" data-testid="case-a-demo-view">
    <main class="page__main">
      <SectionCard :mock="false" title="Case A closed-loop demo" subtitle="A distinct demo path; production full-semester runtime is unchanged.">
        <p><strong>Transcript:</strong> user-uploaded SYSU transcript PDF</p>
        <p><strong>Curriculum:</strong> Case A target curriculum</p>
        <p><strong>Course Data:</strong> Case A scoped South+Shenzhen accepted campus data (not full semester)</p>
        <p><strong>Planner:</strong> actual RestrictedPlanner execution; selected classes are recommendations only.</p>
        <label>Transcript PDF <input data-testid="case-a-pdf" type="file" accept="application/pdf,.pdf" @change="chooseTranscript" /></label>
        <p v-if="transcript">Selected: {{ transcript.name }}</p>
      </SectionCard>

      <SectionCard :mock="false" title="Accepted Case A offerings" :badge-count="offerings.length" subtitle="South + Shenzhen case scope; never whole-school or full-semester completeness.">
        <div v-for="item in offerings" :key="`${item.course_id}:${item.class_id}`">
          <label>
            <input type="checkbox" :checked="form.currentSchedule.some(value => value.course_id === item.course_id && value.class_id === item.class_id)" @change="toggleOffering(item)" />
            {{ item.course_name }} · {{ item.course_id }} · {{ item.class_id }}
          </label>
        </div>
        <CourseOfferingList :offerings="offerings" />
      </SectionCard>

      <SectionCard :mock="false" title="Current schedule" subtitle="Accepted offering selection or explicitly student-attested manual input.">
        <ManualScheduleForm
          :entries="form.manualScheduleEntries"
          :selected="form.currentSchedule"
          :semester="form.semester"
          :current-semester="form.semester"
          provenance-label="Manual entry: student supplied, not school verified"
          :attested="form.manualAttestation.attested"
          :manual-count="manualCount"
          :attestation-invalidated="form.manualAttestation.invalidated"
          @update:entries="updateEntries"
          @add-row="form.manualScheduleEntries = addManualScheduleEntry(form.manualScheduleEntries, $event)"
          @add-confirmed="addManual"
          @remove="removeOffering"
          @update:attested="form = applyManualAttestation(form, $event)"
        />
      </SectionCard>

      <SectionCard :mock="false" title="Preference">
        <PreferenceForm :form="form" @update:form="form = $event" />
      </SectionCard>

      <button class="button" type="button" :disabled="loading" data-testid="case-a-submit" @click="submit">
        {{ loading ? 'Planning…' : 'Run actual Case A plan' }}
      </button>
      <p v-if="error" class="state state--error" role="alert">{{ error }}</p>

      <template v-if="result">
        <SectionCard :mock="false" title="Transcript import" :badge-count="result.transcript.record_count">
          <p>Parsed {{ result.transcript.record_count }} completed courses across {{ result.transcript.term_count }} terms; all course IDs remain pending unless explicitly evidenced.</p>
        </SectionCard>
        <SectionCard :mock="false" title="Case A assessment" :badge-count="result.makeup_tasks.length">
          <MakeupTaskList :tasks="result.makeup_tasks" />
        </SectionCard>
        <SectionCard :mock="false" title="Same-run Course Data" :badge-count="result.course_offerings.length">
          <CourseOfferingList :offerings="result.course_offerings" />
        </SectionCard>
        <SectionCard :mock="false" title="Same-run Preference"><PreferencePanel :preference="result.preference" :course-name-by-id="{}" /></SectionCard>
        <SectionCard :mock="false" title="Actual PlanResult" tone="primary">
          <PlanResultPanel :plan-result="result.plan_result" :course-name-by-id="{}" />
          <p>{{ result.provenance.transcript }} · {{ result.provenance.curriculum }} · {{ result.provenance.course_data }} · {{ result.provenance.current_schedule }} · {{ result.provenance.planner }}</p>
        </SectionCard>
      </template>
    </main>
  </div>
</template>
