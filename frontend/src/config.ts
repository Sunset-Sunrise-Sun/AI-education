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

/**
 * 解释接口：`POST /api/v1/explanation/plan`（Final Upgrade · Agent B）。
 *
 * 这是**新增的私有解释接口**：只读消费已有的 `PlanResult`（可选附带 MakeupTask / CourseOffering
 * 上下文），返回带来源字段与证据强度的解释；⛔ 不改既有路径、⛔ 不改公共 Schema、⛔ 不参与计算。
 */
export const EXPLANATION_ENDPOINT = `${API_BASE_URL}/api/v1/explanation/plan`

/**
 * 解释通道开关。
 *
 * 默认 **关闭**：解释是**可选**能力，关闭时页面不会发出任何解释请求，
 * 并明确显示"解释功能未启用"，⛔ **不会**在前端自行合成解释文本。
 * 打开方式：在 `.env.local` 中设置 `VITE_EXPLANATION_API_ENABLED=true`。
 */
export const EXPLANATION_API_ENABLED: boolean =
  import.meta.env.VITE_EXPLANATION_API_ENABLED === 'true'

/**
 * AI 规划适配层（`GET /status` + `POST /{interpret,solve,adopt}`）。
 *
 * ⚠️ 后端已在分支 `feature/deepseek-planning-controller` 实现这四个路径，
 * 契约见该分支的 `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`
 * （与 `backend/app/api/ai_planning.py` 同一提交）。
 * 但**本分支部署的后端未必包含它**，因此前端把它当成**明确可能不可用**的能力：
 * - 默认**关闭** ⇒ 面板显示「AI 调整不可用」，**一个请求也不发**；
 * - 打开后真实调用；失败如实报错，⛔ **绝不**回退到前端预览 fixture；
 * - 可用性以 `GET /status` 为准（`enabled` / `api_key_configured`）。
 */
export const AI_PLANNING_ENDPOINTS = {
  status: `${API_BASE_URL}/api/v1/ai-planning/status`,
  interpret: `${API_BASE_URL}/api/v1/ai-planning/interpret`,
  solve: `${API_BASE_URL}/api/v1/ai-planning/solve`,
  adopt: `${API_BASE_URL}/api/v1/ai-planning/adopt`,
} as const

/** 真实 AI 规划通道开关；默认关闭。 */
export const AI_PLANNING_API_ENABLED: boolean =
  import.meta.env.VITE_AI_PLANNING_API_ENABLED === 'true'

/**
 * **前端预览模式**开关（离线演示 / 界面评审）。
 *
 * 打开后只使用 `src/api/aiPlanningFixtures.ts`，界面必须显示
 * 「仅前端预览 / 非真实模型 / 未调用 Planner」。⛔ 与本开关无关的真实请求失败
 * 不会回退到 fixture。
 */
export const AI_PLANNING_PREVIEW: boolean =
  import.meta.env.VITE_AI_PLANNING_PREVIEW === 'true'

/**
 * 个人规划接口（**已存在**，Agent A 实现）。
 *
 * ⚠️ 未配置已核验目录时后端返回 503 `personal_catalog_not_configured`；
 * 前端按真实 readiness 展示"没有已核验版本目录"，
 * ⛔ **不退回固定 Case A 冒充个人结果**。
 */
export const PERSONAL_PLANNING_ENDPOINTS = {
  versions: `${API_BASE_URL}/api/v1/personal-planning/curriculum-versions`,
  plan: `${API_BASE_URL}/api/v1/personal-planning/plan`,
} as const

/** 个人规划通道开关；默认关闭（未配置目录时后端 503，不必默认打扰用户）。 */
export const PERSONAL_PLANNING_API_ENABLED: boolean =
  import.meta.env.VITE_PERSONAL_PLANNING_API_ENABLED === 'true'

/**
 * 培养方案 PDF 导入接口（**本轮新增**）。
 *
 * ⚠️ 这条路径**只**产出一份**待组长审核**的草稿：
 * - ⛔ 不写 `APP_PERSONAL_CATALOG_DIR`；
 * - ⛔ 不写批准锚点；
 * - ⛔ 上传成功 / 解析成功 / 用户点击确认，都**不构成**来源核验。
 *
 * 上传用**原始字节**（⛔ 不用 multipart）：与既有已修课程 XLSX 入口同一范式。
 */
export const CURRICULUM_IMPORT_ENDPOINTS = {
  parsePdf: `${API_BASE_URL}/api/v1/curriculum-import/parse-pdf`,
  /**
   * ⚠️ **已验收文档类型清单**：前端只能从这里选择用哪份声明解析。
   * ⛔ 前端⛔ 不能提交课程列位映射 —— profile 由后端注册表给出。
   */
  documentTypes: `${API_BASE_URL}/api/v1/curriculum-import/document-types`,
} as const

/**
 * 培养方案导入开关；默认关闭。
 *
 * ⛔ 关闭时不渲染上传入口，也⛔ 不回退到任何"演示用的假解析结果"。
 */
export const CURRICULUM_IMPORT_API_ENABLED: boolean =
  import.meta.env.VITE_CURRICULUM_IMPORT_API_ENABLED === 'true'

export const APP_TITLE = '学航·转衔'
export const APP_SUBTITLE = '面向转专业学生的 AI 学业路径重构 Agent'

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
