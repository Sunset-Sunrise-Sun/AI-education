/**
 * 个人规划的**前端预览 fixture**（离线演示 / 组件测试专用）。
 *
 * ⛔ 只是人工构造的界面预览数据：
 * - 不是已核验培养方案，也不是任何学生的真实成绩；
 * - 只在 `VITE_PERSONAL_PLANNING_PREVIEW=true` 时使用，界面必须显示
 *   `PERSONAL_PREVIEW_NOTICE`；
 * - ⛔ 真实请求失败时**绝不** fallback 到本文件。
 */

import type { CurriculumVersionList, PersonalPlanResult } from '../api/personalPlanning'

export const PERSONAL_PREVIEW_NOTICE =
  '仅前端预览 / 未读取已核验目录 / 不代表真实个人规划结果'

/** 预览用版本目录：刻意标注 `preview` 来源，避免被误读为已核验版本。 */
export const PREVIEW_VERSION_LIST: CurriculumVersionList = {
  catalog_ready: true,
  catalog_reason: 'preview_fixture',
  selectable_count: 2,
  versions: [
    {
      version_id: 'preview-old-version',
      major: '遥感科学与技术（预览）',
      cohort: '2025',
      campus: '东校园',
      track: null,
      source_id: 'preview://fixture/old',
      verification_evidence: '前端预览构造，未核验',
      verified_by: null,
      complete: false,
      completeness_evidence: null,
      total_credit: null,
      practice_credit: null,
      study_years: null,
      course_count: 0,
      group_count: 0,
    },
    {
      version_id: 'preview-target-version',
      major: '网络空间安全（预览）',
      cohort: '2025',
      campus: '东校园',
      track: null,
      source_id: 'preview://fixture/target',
      verification_evidence: '前端预览构造，未核验',
      verified_by: null,
      complete: false,
      completeness_evidence: null,
      total_credit: null,
      practice_credit: null,
      study_years: null,
      course_count: 0,
      group_count: 0,
    },
  ],
  rejected: [
    {
      version_id: 'preview-unverified-version',
      code: 'not_verified',
      detail: '（前端预览）该条目缺少核验依据，因此不可选。',
    },
  ],
}

/** 预览用个人规划结果：`planning = null` 且带明确的跳过原因。 */
export const PREVIEW_PERSONAL_PLAN: PersonalPlanResult = {
  old_version: PREVIEW_VERSION_LIST.versions[0],
  target_version: PREVIEW_VERSION_LIST.versions[1],
  data_source: 'mock',
  completed_source_id: 'preview://completed/fixture',
  completed_record_count: 3,
  input_summary: { completed_record_count: 3, makeup_task_count: 4 },
  makeup_tasks: [
    {
      course_id: '62001001',
      course_name: '离散数学',
      credit: 3,
      status: 'required',
      deadline_semester: 5,
      recommended_semester: 4,
      prerequisites: [],
      reason: '（前端预览）转专业后新培养方案必修，原专业无对应课程记录。',
      source_evidence: 'preview://fixture/diff/62001001（前端预览，非真实培养方案）',
    },
    {
      course_id: '62001002',
      course_name: '数据结构与算法',
      credit: 4,
      status: 'required',
      deadline_semester: 6,
      recommended_semester: 4,
      prerequisites: ['62001001'],
      reason: '（前端预览）新培养方案专业核心课。',
      source_evidence: 'preview://fixture/diff/62001002（前端预览）',
    },
    {
      course_id: '62002031',
      course_name: '概率论与数理统计',
      credit: 3,
      status: 'possibly_equivalent',
      deadline_semester: 6,
      recommended_semester: 5,
      prerequisites: [],
      reason: '（前端预览）与原专业课程名称相近，是否互认需要教务确认。',
      source_evidence: 'preview://fixture/equivalence/62002031（前端预览）',
    },
    {
      course_id: '62003007',
      course_name: '复变函数与积分变换',
      credit: 2,
      status: 'manual_confirmation',
      deadline_semester: 7,
      recommended_semester: 5,
      prerequisites: [],
      reason: '（前端预览）新旧方案学分不一致，需要人工判定。',
      source_evidence: 'preview://fixture/manual/62003007（前端预览）',
    },
  ],
  status_counts: {
    required: 2,
    possibly_equivalent: 1,
    manual_confirmation: 1,
  },
  // ⚠️ 刻意保持 null：预览也不伪造"已排好课"。
  planning: null,
  planning_skipped_reason:
    'no_course_data: （前端预览）当前没有已装配的真实教学班供给，因此没有调用 Planner。',
  planning_skipped_code: 'no_course_data',
  assuming_course_ids: [],
  notes: ['（前端预览）该结果由前端 fixture 提供，未经过任何后端计算。'],
}
