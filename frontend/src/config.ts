/**
 * 集中配置。
 *
 * 后端地址**只在这里出现一次**，不散落到各个组件里。
 *
 * 默认留空 = 请求同源路径，由 Vite 开发/预览服务器代理到后端
 * （代理目标见 `vite.config.ts`，可用 `VITE_PROXY_TARGET` 覆盖）。
 * 这样本地联调不需要后端开启 CORS，也就不必改动 Phase 1 的后端代码。
 */

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL ?? ''

/** 后端基地址；空字符串表示"同源，由 Vite 代理转发"。 */
export const API_BASE_URL: string = rawBaseUrl.replace(/\/+$/, '')

/** 本阶段的 Mock 演示接口。Mock 通道**永久保留**，不因 Real API 接入而删除。 */
export const DEMO_ENDPOINT = `${API_BASE_URL}/api/v1/mock/demo`

/**
 * 目标 Real 接口：`POST /api/v1/plan`。
 *
 * ✅ 该 endpoint **已经在 main 上实现**（后端 runtime wiring 已合并）；未装配时
 * 明确返回 `503 real_pipeline_not_configured`，前端按**当前正确状态**如实展示该错误，
 * ⛔ 不把它当成"接口不存在"，也⛔ **绝不**在失败时回退到 Mock 通道。
 */
export const PLAN_ENDPOINT = `${API_BASE_URL}/api/v1/plan`

/**
 * Real Planning 通道开关。
 *
 * 默认 **关闭**：这只是**演示默认值**（比赛演示不依赖后端已装配的真实输入），
 * 页面的 Real Planning 提交按钮明确显示为不可用，并且**不会**偷偷改调 Mock 接口。
 * 后端 `POST /api/v1/plan` 已存在；把它打开只需在 `.env.local` 中设置
 * `VITE_PLAN_API_ENABLED=true`（真实链路是否可用仍由后端 readiness 决定：未装配 ⇒ 503）。
 */
export const PLAN_API_ENABLED: boolean = import.meta.env.VITE_PLAN_API_ENABLED === 'true'

export const APP_TITLE = '学航·转衔'

/**
 * 副标题（用户可见标签）。
 *
 * ⚠️ 口径要求（比赛披露）：当前实现是**固定工具编排原型**，
 * ⛔ 不得让标题区给人"本版本已运行模型推理 / 检索 / 生成式解释"的印象；
 * 模型能力（LLM / RAG / GraphRAG）为后续增强方向，页面 footer 另行给出实现边界说明。
 */
export const APP_SUBTITLE = '面向转专业学生的学业路径重构原型（固定工具编排，AI 增强待接入）'

/**
 * 比赛 MVP 的 Case context：中山大学 Case A。
 *
 * ⚠️ 边界（很重要）：
 * - 这些值只是**默认展示与输入初值**，用于演示"用户如何录入自己的转专业上下文"；
 * - 它们**不参与任何判断分支**：前端不存在 `if (major === '网络空间安全')` 这类专业名分支，
 *   专业选项统一来自下面的 `MAJOR_OPTIONS` 选项层；
 * - 它们**不会被悄悄送进后端 Planner**，也不代表 Planner 已经按这些信息产出结果；
 * - 不包含任何学生姓名、学号、成绩或课程认定结果。
 */
export interface CaseContext {
  /** 目标学期（转专业后要规划的那个学期）。 */
  semester: string
  /** 原专业（Case A：遥感科学与技术）。 */
  originMajor: string
  /** 目标专业（Case A：网络空间安全）。 */
  targetMajor: string
  /** 转入学期（Case A：2026-1）。 */
  transferTerm: string
}

/** Case A 的默认上下文。 */
export const CASE_A_CONTEXT: CaseContext = {
  semester: '2026-1',
  originMajor: '遥感科学与技术',
  targetMajor: '网络空间安全',
  transferTerm: '2026-1',
}

/**
 * 专业选项层。
 *
 * 专业名只作为**下拉选项数据**存在（含一个 `label` 与 `value`），
 * 供学生选择；组件与业务逻辑都不按专业名分叉。
 */
export interface MajorOption {
  value: string
  label: string
}

export const MAJOR_OPTIONS: readonly MajorOption[] = [
  { value: '遥感科学与技术', label: '遥感科学与技术' },
  { value: '网络空间安全', label: '网络空间安全' },
  { value: '软件工程', label: '软件工程' },
  { value: '计算机科学与技术', label: '计算机科学与技术' },
  { value: '智能科学与技术', label: '智能科学与技术' },
  { value: '人工智能', label: '人工智能' },
]

/**
 * **规划结果**的来源。
 *
 * ⚠️ 这是**局部** provenance，不是"整页数据模式"：
 * `POST /api/v1/plan` 只返回 `PlanResult`，页面基础展示数据
 * （培养要求评估 / 教学班 / 偏好）仍全部来自 Mock Demo。
 * Mock 与 Real 必须能明确区分，不允许混用或静默回退。
 */
export type PlanResultSource = 'mock' | 'real'

/**
 * 读取初始的规划结果来源。
 *
 * 在 Real API 合并进 main 之前恒为 `'mock'`；
 * 只有**成功调用** `POST /api/v1/plan` 之后才会变成 `'real'`。
 */
export function initialDataMode(): PlanResultSource {
  return 'mock'
}

/**
 * **手工录入**当前课表在页面上显示的来源说明（⛔ 逐字可见，不得隐藏）。
 *
 * ⚠️ 这里**没有**任何构建期开关：手工课表能否提交 Real Planning，
 * **只**由用户在 UI 上的显式确认（attestation）决定，见
 * `state/manualSchedule.ts` 的 `ManualScheduleAttestationState`。
 * ⛔ 手写 `data_source` / 环境变量的旁路已移除：不存在两套机制互相绕过。
 *
 * ⛔ 用词必须守住：手工录入是**本人填写**、**未经学校系统核验**，
 * 它**不是** Course Data provenance，也**不是**任何学校来源证明。
 */
export const MANUAL_SCHEDULE_ENTRY_LABEL =
  '手工录入：由本人填写，未经学校系统核验（不是 Course Data 来源证明）'
