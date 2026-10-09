/**
 * 浏览器 E2E 测试用例（真实 Edge + 真实 FastAPI + 真实 Vite 前端）。
 *
 * 三类档位，报告里分开标注：
 * - `live`    ：`VITE_AI_PLANNING_API_ENABLED=true`，后端 enabled=true 且
 *               **注入式测试模型**（`generator_kind=test_double`，⛔ 不是 DeepSeek 在线）；
 * - `disabled`：后端 `AI_PLANNING_ENABLED=false`（未启用态）；
 * - `preview` ：`VITE_AI_PLANNING_PREVIEW=true`（纯前端 fixture，⛔ 不调用后端 Planner）。
 *
 * 每个用例都断言**浏览器实际发出的 HTTP 请求**，而不是只看界面文案。
 */

import {
  assert,
  assertEqual,
  assertIncludes,
  apiRequests,
  openPage,
  requestsFor,
  shot,
  textOf,
  waitForState,
} from './lib/harness.mjs'

/* ------------------------------------------------------------------ *
 * 选择器与常量
 * ------------------------------------------------------------------ */

const VIEW_KEYS = ['transfer-analysis', 'makeup-path', 'ai-adjust']
const AI_PATHS = {
  status: '/api/v1/ai-planning/status',
  interpret: '/api/v1/ai-planning/interpret',
  solve: '/api/v1/ai-planning/solve',
  adopt: '/api/v1/ai-planning/adopt',
}
const NEW_COURSE = '62004005'
/**
 * 通用"可确认"意图。
 *
 * ⚠️ 学分上限必须**小于等于上下文已声明的上限**（mock demo 的
 * `preference.max_credit=12`），否则后端的
 * `credit_limit_conflicts_with_declared_max` 会正确地禁止确认——
 * 那属于"后端正确行为"，但会让"候选对比"路径无法执行。
 */
const CREDIT_SUFFIX = '最多 12 学分'
const GENEROUS_MESSAGE = `尽量别在周五上课，${CREDIT_SUFFIX}`
const LOCK_MESSAGE = `数据结构必须保留，尽量别在周五上课，${CREDIT_SUFFIX}`

/* ------------------------------------------------------------------ *
 * 公共动作
 * ------------------------------------------------------------------ */

export async function gotoHome(page, baseUrl) {
  await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' })
  await waitForState(page, 'app-nav')
}

export async function switchView(page, key) {
  await page.locator(`[data-testid="nav-${key}"]`).first().click()
  await waitForState(page, `view-${key}`)
}

export async function openDrawer(page) {
  const fromPath = page.locator('[data-testid="path-open-ai-drawer"]').first()
  if (await fromPath.count()) {
    await switchView(page, 'makeup-path')
    await fromPath.click()
  } else {
    await switchView(page, 'ai-adjust')
    await page.locator('[data-testid="ai-view-open-drawer"]').first().click()
  }
  await waitForState(page, 'ai-drawer')
}

export async function fillAndParse(page, message) {
  const input = page.locator('[data-testid="ai-utterance-input"]').first()
  await input.fill(message)
  await page.locator('[data-testid="ai-parse-intent"]').first().click()
}

export async function confirmIntent(page) {
  await waitForState(page, 'ai-confirm-intent', { timeout: 25000 })
  await page.locator('[data-testid="ai-confirm-intent"]').first().click()
}

export async function reachCandidate(page) {
  await openDrawer(page)
  await fillAndParse(page, GENEROUS_MESSAGE)
  await confirmIntent(page)
  await waitForCandidatePanel(page)
}

/** 视口下的横向溢出检测（返回 documentElement.scrollWidth - clientWidth）。 */
async function horizontalOverflow(page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

/**
 * 读取可能"不存在"的 testid 文本（不存在时返回空串，不抛超时）。
 *
 * 用途：某些元素是条件渲染的（例如生成方式备注只在草稿态出现），
 * 直接 `textContent()` 会在元素缺席时抛出 30 秒超时并掩盖真正的断言。
 */
async function safeText(page, testId) {
  const locator = page.locator(`[data-testid="${testId}"]`).first()
  if ((await locator.count()) === 0) {
    return ''
  }
  return ((await locator.textContent()) ?? '').trim()
}

/**
 * 收集抽屉里当前**已挂载**的 `ai-*` testid。
 *
 * ⚠️ 为什么用"已挂载"而不是 `getClientRects()` 的"可见"：
 * 抽屉在窄屏与长内容下会出现内部滚动，滚动容器外的元素 `getClientRects()`
 * 可能为空，但元素确实已经渲染（`textContent` 可读）。
 * 挂载判据更贴近本用例的真实意图，也避免把"渲染完成"误判成"失败"。
 */
async function attachedAiTestIds(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('[data-testid]')]
      .map((node) => node.getAttribute('data-testid'))
      .filter((id) => (id ?? '').startsWith('ai-')),
  )
}

/**
 * 等待"面板真正渲染完成"。
 *
 * ⚠️ 为什么不能只等容器：`v-if` 让容器与子元素在不同 tick 挂载，
 * 只等 `ai-intent-draft` 会出现"容器在、子元素还没在"的竞态。
 */
async function waitForDraftPanel(page, timeout = 25000) {
  await waitForState(page, 'ai-intent-draft', { timeout })
  await waitForState(page, 'ai-generator-kind', { timeout })
  await waitForState(page, 'ai-data-source', { timeout })
}

async function waitForCandidatePanel(page, timeout = 25000) {
  await waitForState(page, 'ai-candidate-compare', { timeout })
  await waitForState(page, 'ai-plan-diff', { timeout })
}

/** 元素是否在视口内且尺寸为正（"可见且可交互"的粗判据）。 */
async function visibleBox(page, testId) {
  const box = await page.locator(`[data-testid="${testId}"]`).first().boundingBox()
  if (!box) {
    return null
  }
  const viewport = page.viewportSize()
  const inside =
    box.x >= -1 &&
    box.y >= -1 &&
    box.x + box.width <= viewport.width + 1 &&
    box.y + box.height <= viewport.height + 1
  return { box, inside, viewport }
}

/* ------------------------------------------------------------------ *
 * live 档用例
 * ------------------------------------------------------------------ */

export function liveBaselineCases({ baseUrl }) {
  return [
    {
      id: 'L01-home-three-entries',
      title: '首页加载并可在三个入口之间切换',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests, consoleErrors } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          for (const key of VIEW_KEYS) {
            await switchView(page, key)
            assert(
              await page.locator(`[data-testid="view-${key}"]`).first().isVisible(),
              `切换到 ${key} 后视图不可见`,
            )
          }
          const demoCall = requestsFor(requests, '/api/v1/mock/demo')
          assert(demoCall.length >= 1, '首页没有请求 /api/v1/mock/demo')
          return {
            notes: [`三个入口切换正常；/api/v1/mock/demo 调用 ${demoCall.length} 次`],
            evidence: [await shot(page, 'L01-home-ai-adjust', 'live')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
            consoleErrors,
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L02-transfer-analysis-readiness',
      title: '转专业分析：无已核验目录时如实报告，不伪造个人结果',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'transfer-analysis')
          assert(
            requestsFor(requests, '/api/v1/personal-planning/curriculum-versions').length >= 1,
            '没有请求版本目录接口',
          )
          const notConfigured = await page
            .locator('[data-testid="personal-not-configured"]')
            .first()
            .isVisible()
            .catch(() => false)
          const disabled = await page
            .locator('[data-testid="personal-disabled"]')
            .first()
            .isVisible()
            .catch(() => false)
          const emptyVersions = await page
            .locator('[data-testid="personal-empty"]')
            .first()
            .isVisible()
            .catch(() => false)
          assert(
            notConfigured || disabled || emptyVersions,
            '既没有显示"没有已核验版本目录"，也没有显示"未启用/无版本"——可能伪造了可用状态',
          )
          const detailText = await page
            .locator('[data-testid="personal-error-detail"]')
            .first()
            .textContent()
            .catch(() => null)
          const detail = notConfigured
            ? `未配置：${(detailText ?? '').trim().slice(0, 80)}`
            : disabled
              ? '通道未启用（如实显示）'
              : '目录为空（如实显示）'
          // ⛔ 不得伪造版本：未配置时版本下拉不能出现任何可选版本
          const versionOptions = await page
            .locator('[data-testid="personal-target-version"] option')
            .count()
            .catch(() => 0)
          if (notConfigured) {
            assertEqual(versionOptions, 0, '未配置目录时仍然出现了可选版本（疑似伪造）')
          }
          return {
            notes: [`转专业分析就绪态：${detail}`],
            evidence: [await shot(page, 'L02-transfer-analysis', 'live')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L03-makeup-path-structure',
      title: '补修路径：四状态、教学班、风险/未决与 Mock 标识可见',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'makeup-path')
          await waitForState(page, 'path-priority-list')
          const body = await page.locator('body').innerText()
          for (const label of ['需要补修', '已满足']) {
            assertIncludes(body, label, `补修路径缺少状态说明「${label}」`)
          }
          assertIncludes(body, NEW_COURSE, '补修路径没有显示尚未选班的必修课 62004005')
          const modeTag = await textOf(page, 'data-mode-tag')
          assert(modeTag.length > 0, '没有数据来源标记')
          return {
            notes: [`数据来源标记：${modeTag}`, `教学班列表与未决项均已渲染`],
            evidence: [await shot(page, 'L03-makeup-path', 'live')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L04-ai-full-two-confirmations',
      title: 'AI 调整闭环：解析 → 第一次确认 → 求解 → 候选对比 → 第二次确认采用',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests, apiBodies } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'makeup-path')
          await page.locator('[data-testid="path-open-ai-drawer"]').first().click()
          await waitForState(page, 'ai-drawer')
          assert(
            requestsFor(requests, AI_PATHS.status).length >= 1,
            '抽屉打开后没有请求 /api/v1/ai-planning/status',
          )
          const channel = await textOf(page, 'ai-drawer-channel')
          assertIncludes(channel, '真实接口', `通道说明没有如实标注真实接口：${channel}`)

          await fillAndParse(page, `数据结构必须保留，尽量别在周五上课，${CREDIT_SUFFIX}`)
          await waitForDraftPanel(page)
          const interpretCall = requestsFor(requests, AI_PATHS.interpret)
          assert(interpretCall.length >= 1, '没有调用 /interpret')
          assertEqual(
            requestsFor(requests, AI_PATHS.solve).length,
            0,
            '第一次确认之前就调用了 /solve',
          )
          const generatorKindLabel = await textOf(page, 'ai-generator-kind')
          const dataSource = await textOf(page, 'ai-data-source')
          const generatorNote = await safeText(page, 'ai-generator-note')
          const visibleIds = await attachedAiTestIds(page)
          // ⚠️ 界面上的 `ai-generator-kind` 是**面向用户的标签**（"测试替身模型（不是线上模型）"），
          // 不是后端原始枚举；原始枚举 `test_double` 由后端 HTTP 层测试锁定
          // （backend/tests/test_ai_planning_joint_e2e.py）。
          // 这里断言**浏览器界面如实标注**：明确说测试替身 + 明确说不是线上模型。
          assertIncludes(
            generatorKindLabel,
            '测试替身',
            `生成方式标签没有标明测试替身：${generatorKindLabel}`,
          )
          assertIncludes(
            generatorNote,
            '不是线上模型',
            `生成方式备注没有说明不是线上模型：${generatorNote}`,
          )
          assertIncludes(dataSource, 'mock', `data_source 未如实展示：${dataSource}`)
          // ⛔ 不得把测试替身说成线上模型
          const panelText = await safeText(page, 'ai-intent-draft')
          assert(
            !panelText.includes('deepseek_live') && !panelText.includes('已接入'),
            `草稿面板把测试替身说成了线上模型：${panelText.slice(0, 80)}`,
          )
          assert(
            visibleIds.includes('ai-generator-kind') && visibleIds.includes('ai-data-source'),
            `草稿面板缺少生成方式 / 数据来源标记：${visibleIds.join(',')}`,
          )
          evidence.push(await shot(page, 'L04-a-intent-draft', 'live'))

          await confirmIntent(page)
          assert(
            requestsFor(requests, AI_PATHS.solve).length >= 1,
            '确认之后没有调用 /solve',
          )
          await waitForCandidatePanel(page)
          assertEqual(await textOf(page, 'ai-solve-status'), 'candidate_ready', '求解状态不是 candidate_ready')
          const diffText = await textOf(page, 'ai-plan-diff')
          assertIncludes(diffText, NEW_COURSE, `候选差异里没有新增课程 ${NEW_COURSE}`)
          evidence.push(await shot(page, 'L04-b-candidate-compare', 'live'))

          await page.locator('[data-testid="ai-adopt-candidate"]').first().click()
          await waitForState(page, 'ai-adopted', { timeout: 25000 })
          assert(requestsFor(requests, AI_PATHS.adopt).length >= 1, '采用时没有调用 /adopt')
          const scope = await textOf(page, 'ai-adopted-scope')
          assertIncludes(scope, 'process_local_session', '采用范围没有如实标注进程内会话')
          assertEqual(await textOf(page, 'ai-adopted-version'), '1', 'adopted_version 不是 1')
          evidence.push(await shot(page, 'L04-c-adopted', 'live'))

          return {
            notes: [
              `generator_kind 标签=${generatorKindLabel}`,
              `generator_note=${generatorNote}`,
              `data_source=${dataSource}`,
              `候选差异包含新增 ${NEW_COURSE}`,
              `adopted_version=1，scope=${scope.slice(0, 44)}…`,
            ],
            evidence,
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L05-adopted-plan-refreshes-view',
      title: '采用成功后：页面用后端候选刷新展示方案（含导航切换后）',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await reachCandidate(page)
          await page.locator('[data-testid="ai-adopt-candidate"]').first().click()
          await waitForState(page, 'ai-adopted', { timeout: 25000 })
          await page.locator('[data-testid="ai-drawer-close"]').first().click()

          await switchView(page, 'ai-adjust')
          const tag = await textOf(page, 'ai-view-adopted-version')
          assertIncludes(tag, '进程内会话版本', 'AI 调整视图没有显示采用后的会话版本标记')
          evidence.push(await shot(page, 'L05-a-ai-view-after-adopt', 'live'))

          await switchView(page, 'makeup-path')
          const pathText = await page.locator('body').innerText()
          assertIncludes(pathText, NEW_COURSE, '切换视图后展示的方案里看不到新增课程')
          evidence.push(await shot(page, 'L05-b-makeup-path-after-adopt', 'live'))

          return {
            notes: ['采用后 AI 调整视图显示会话版本', '导航切换后展示方案仍包含后端候选的新增课程'],
            evidence,
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L06-reject-keeps-original',
      title: '拒绝候选：原方案不变，不推进版本',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await reachCandidate(page)
          await page.locator('[data-testid="ai-keep-original"]').first().click()
          await waitForState(page, 'ai-kept', { timeout: 25000 })
          const keptMessage = await textOf(page, 'ai-kept-message')
          assertEqual(
            requestsFor(requests, AI_PATHS.adopt).length,
            1,
            '拒绝路径的 /adopt 调用次数异常',
          )
          assert(
            !(await page.locator('[data-testid="ai-adopted"]').first().isVisible().catch(() => false)),
            '拒绝之后仍然显示"已采用"',
          )
          evidence.push(await shot(page, 'L06-rejected', 'live'))

          await page.locator('[data-testid="ai-drawer-close"]').first().click()
          await switchView(page, 'ai-adjust')
          assertEqual(
            await page.locator('[data-testid="ai-view-adopted-version"]').count(),
            0,
            '拒绝后 AI 调整视图仍显示会话版本标记',
          )
          return {
            notes: [`拒绝提示：${keptMessage.slice(0, 48)}…`, '拒绝后当前方案保持原样'],
            evidence,
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L07-drawer-reopen-and-navigation',
      title: '关闭抽屉/重新打开/切换导航：状态不产生误导',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await reachCandidate(page)
          const solveCount = requestsFor(requests, AI_PATHS.solve).length

          await page.locator('[data-testid="ai-drawer-close"]').first().click()
          await openDrawer(page)
          assert(
            !(await page.locator('[data-testid="ai-adopted"]').first().isVisible().catch(() => false)),
            '重新打开抽屉后仍显示上一次的"已采用"',
          )
          assertEqual(requestsFor(requests, AI_PATHS.adopt).length, 0, '仅打开抽屉就调用了 /adopt')
          assertEqual(
            requestsFor(requests, AI_PATHS.solve).length,
            solveCount,
            '打开抽屉时重复调用了 /solve',
          )
          evidence.push(await shot(page, 'L07-reopened-drawer', 'live'))

          await page.locator('[data-testid="ai-drawer-close"]').first().click()
          await switchView(page, 'transfer-analysis')
          await switchView(page, 'makeup-path')
          await switchView(page, 'ai-adjust')
          assertEqual(
            requestsFor(requests, AI_PATHS.solve).length,
            solveCount,
            '切换导航触发了新的 /solve',
          )
          evidence.push(await shot(page, 'L07-after-nav', 'live'))

          return {
            notes: ['关闭/重开抽屉不残留采用状态', '切换导航不触发新的 AI 请求'],
            evidence,
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L08-ambiguity-blocks-solve',
      title: '模糊意图（"太累"没有学分数字）：禁止求解，须由用户消解',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          await openDrawer(page)
          await fillAndParse(page, '这学期太累，少上一点课就行')
          await waitForDraftPanel(page)
          // 后端 can_confirm=false ⇒ 面板必须显示"不能确认"并给出待确认项
          await waitForState(page, 'ai-cannot-confirm', { timeout: 25000 })
          const blocked = await textOf(page, 'ai-cannot-confirm')
          const creditUnknown = await textOf(page, 'ai-credit-unspecified')
          assert(
            blocked.includes('学分') || blocked.includes('确认') || creditUnknown.includes('学分'),
            `没有把"学分上限缺失"作为待确认项展示：${blocked.slice(0, 60)}`,
          )
          assertEqual(
            requestsFor(requests, AI_PATHS.solve).length,
            0,
            '存在歧义时仍调用了 /solve',
          )
          const disabled = await page.locator('[data-testid="ai-confirm-intent"]').first().isDisabled()
          assert(disabled, '存在未消解歧义时"确认"按钮仍可点击')
          return {
            notes: [
              '后端 can_confirm=false（"太累"没有被换算成学分数字）',
              `面板提示：${blocked.slice(0, 70)}`,
              '前端禁用确认按钮且未调用 /solve',
            ],
            evidence: [await shot(page, 'L08-ambiguity', 'live')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L09-locked-course-explicit-lock',
      title: '锁定课程：用户显式锁定后，候选必须保留该班次',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await openDrawer(page)
          // 明确说出"必须保留"（软偏好）+ 一个可确认的学分上限
          await fillAndParse(page, LOCK_MESSAGE)
          await waitForDraftPanel(page)

          // 用户在前端**显式**锁定数据结构（62001002）——这才是硬锁定
          const lockButton = page.locator('[data-testid="ai-lock-62001002"]').first()
          if (await lockButton.count()) {
            await lockButton.click()
          }
          const lockedBefore = await safeText(page, 'ai-locked-courses')
          assert(
            lockedBefore.includes('62001002') || lockedBefore.includes('数据结构'),
            `锁定后锁定列表没有显示 62001002：${lockedBefore.slice(0, 60) || '(空)'}`,
          )
          evidence.push(await shot(page, 'L09-a-locked-before-solve', 'live'))

          await confirmIntent(page)
          await waitForCandidatePanel(page)
          const diffText = await textOf(page, 'ai-plan-diff')
          assertIncludes(diffText, '62001002', '候选差异里看不到被锁定的数据结构课')
          const candidatePlan = await textOf(page, 'ai-candidate-plan')
          assertIncludes(candidatePlan, '62001002', '候选方案里缺少被锁定的数据结构课')
          evidence.push(await shot(page, 'L09-b-candidate-keeps-lock', 'live'))

          return {
            notes: [
              `锁定列表：${lockedBefore.slice(0, 50)}`,
              '候选方案与差异都保留了被锁定的 62001002',
            ],
            evidence,
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'L10-candidate-expiry-410',
      title: '候选过期（TTL=2s）：采用被后端拒绝，原方案不变',
      priority: 'P0',
      phase: 'live',
      shortTtl: true,
      run: async ({ browser, shortTtl }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, shortTtl.frontend.baseUrl)
          await reachCandidate(page)
          await page.waitForTimeout(2600)
          await page.locator('[data-testid="ai-adopt-candidate"]').first().click()
          await waitForState(page, 'ai-error', { timeout: 25000 })
          const kind = await textOf(page, 'ai-error-kind')
          const message = await textOf(page, 'ai-error-message')
          assert(
            requestsFor(requests, AI_PATHS.adopt).length >= 1,
            '过期路径没有发出 /adopt 请求',
          )
          assert(
            !(await page.locator('[data-testid="ai-adopted"]').first().isVisible().catch(() => false)),
            '候选过期却显示了"已采用"',
          )
          return {
            notes: [`错误类型=${kind}`, `错误信息=${message.slice(0, 70)}`],
            evidence: [await shot(page, 'L10-expired-candidate', 'live')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
  ]
}

/* ------------------------------------------------------------------ *
 * P1：响应式布局
 * ------------------------------------------------------------------ */

export function responsiveCases({ baseUrl }) {
  const viewports = [
    { label: '375', width: 375, height: 812 },
    { label: '768', width: 768, height: 1024 },
    { label: '1440', width: 1440, height: 900 },
  ]
  return viewports.map((viewport) => ({
    id: `R-${viewport.label}-layout`,
    title: `${viewport.width}px 视口：三入口、抽屉、按钮与长文本可用且无横向溢出`,
    priority: 'P1',
    phase: 'live',
    run: async ({ browser }) => {
      const { context, page, requests } = await openPage(browser, {
        viewport: { width: viewport.width, height: viewport.height },
      })
      const evidence = []
      const notes = []
      try {
        await gotoHome(page, baseUrl)
        for (const key of VIEW_KEYS) {
          await switchView(page, key)
          const overflow = await horizontalOverflow(page)
          assert(overflow <= 1, `${key} 视图在 ${viewport.width}px 下横向溢出 ${overflow}px`)
        }
        notes.push('三个入口无横向溢出')

        await openDrawer(page)
        const drawerBox = await visibleBox(page, 'ai-drawer')
        assert(drawerBox !== null, '抽屉不可见')
        assert(
          drawerBox.box.width <= viewport.width + 1,
          `抽屉宽于视口（宽 ${Math.round(drawerBox.box.width)} / 视口 ${viewport.width}）`,
        )
        if (viewport.width <= 420) {
          // 手机宽度：抽屉应近似全屏（CSS: min(520px, 96vw)）
          assert(
            drawerBox.box.width >= viewport.width * 0.9,
            `手机宽度下抽屉未近似全屏（宽 ${Math.round(drawerBox.box.width)} / 视口 ${viewport.width}）`,
          )
          notes.push('手机宽度下抽屉近似全屏')
        } else {
          // 桌面/平板：抽屉是**右侧面板**（不是全屏），但必须落在视口内且可操作
          assert(
            drawerBox.box.x >= -1 && drawerBox.box.x + drawerBox.box.width <= viewport.width + 1,
            `抽屉没有落在视口内（x=${Math.round(drawerBox.box.x)}）`,
          )
          notes.push(`右侧面板宽 ${Math.round(drawerBox.box.width)}px（未全屏，符合桌面设计）`)
        }
        const inputBox = await visibleBox(page, 'ai-utterance-input')
        assert(inputBox !== null, '抽屉输入框不可见')
        assert(inputBox.box.width > 40, '抽屉输入框宽度异常')
        evidence.push(await shot(page, `R-${viewport.label}-drawer`, 'responsive'))

        await fillAndParse(page, GENEROUS_MESSAGE)
        await confirmIntent(page)
        await waitForCandidatePanel(page)
        const overflowAfter = await horizontalOverflow(page)
        assert(overflowAfter <= 1, `候选对比在 ${viewport.width}px 下横向溢出 ${overflowAfter}px`)
        const adoptBox = await visibleBox(page, 'ai-adopt-candidate')
        assert(adoptBox !== null, '采用按钮不可见')
        // 横向必须落在视口内；纵向可能在抽屉内部滚动区，需 scrollIntoView 后才可点
        assert(
          adoptBox.box.x >= -1 && adoptBox.box.x + adoptBox.box.width <= viewport.width + 1,
          `采用按钮横向超出视口（x=${Math.round(adoptBox.box.x)} 宽=${Math.round(adoptBox.box.width)}）`,
        )
        const adoptButton = page.locator('[data-testid="ai-adopt-candidate"]').first()
        await adoptButton.scrollIntoViewIfNeeded()
        const afterScroll = await adoptButton.boundingBox()
        assert(afterScroll !== null, '滚动后采用按钮不可定位')
        assert(
          afterScroll.y >= -1 && afterScroll.y + afterScroll.height <= viewport.height + 1,
          `滚动后采用按钮仍不可见（y=${Math.round(afterScroll.y)} 高=${Math.round(afterScroll.height)}）`,
        )
        notes.push('采用按钮可滚动到视口内（可操作）')
        const riskText = await textOf(page, 'ai-solve-risks')
        notes.push(`候选风险文本长度 ${riskText.length}（长文本已渲染）`)
        evidence.push(await shot(page, `R-${viewport.label}-candidate`, 'responsive'))

        // 禁用态按钮仍需可读：草稿态下"确认"按钮在歧义场景被禁用，这里检查其可读文本
        await page.locator('[data-testid="ai-edit-again"]').first().click().catch(() => {})
        const draftButtonText = await safeText(page, 'ai-confirm-intent')
        if (draftButtonText) {
          notes.push(`确认按钮文案可读：${draftButtonText.slice(0, 30)}`)
        }
        return {
          notes,
          evidence,
          httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
        }
      } finally {
        await context.close()
      }
    },
  }))
}

/* ------------------------------------------------------------------ *
 * P1：异常场景
 * ------------------------------------------------------------------ */

export function resilienceCases({ baseUrl }) {
  return [
    {
      id: 'E01-double-click-confirm-single-solve',
      title: '连续点击"确认意图"只发出一次 /solve',
      priority: 'P1',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          await openDrawer(page)
          await fillAndParse(page, GENEROUS_MESSAGE)
          // 必须等草稿面板真正就绪（按钮才有可能可点）
          await waitForDraftPanel(page)
          const button = page.locator('[data-testid="ai-confirm-intent"]').first()
          await button.waitFor({ state: 'visible', timeout: 25000 })
          assert(!(await button.isDisabled()), '意图已可确认，但"确认"按钮仍是禁用状态')
          // 连续点击：验证"提交期间禁用"这一并发保护
          await Promise.all([
            button.click({ noWaitAfter: true }).catch(() => {}),
            button.click({ force: true }).catch(() => {}),
            button.click({ force: true }).catch(() => {}),
          ])
          await waitForCandidatePanel(page)
          await page.waitForTimeout(600)
          const solveCount = requestsFor(requests, AI_PATHS.solve).length
          assertEqual(solveCount, 1, `连续点击导致 /solve 被调用 ${solveCount} 次`)
          return {
            notes: [
              '按钮在提交期间被禁用',
              `连续 3 次点击只产生 ${solveCount} 次 /solve`,
            ],
            evidence: [await shot(page, 'E01-double-click', 'resilience')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'E02-double-click-adopt-single-request',
      title: '连续点击"采用候选"只发出一次 /adopt',
      priority: 'P1',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          await reachCandidate(page)
          const button = page.locator('[data-testid="ai-adopt-candidate"]').first()
          assert(!(await button.isDisabled()), '候选已就绪，但"采用"按钮仍是禁用状态')
          await Promise.all([
            button.click({ noWaitAfter: true }).catch(() => {}),
            button.click({ force: true }).catch(() => {}),
          ])
          await waitForState(page, 'ai-adopted', { timeout: 25000 })
          await page.waitForTimeout(600)
          const adoptCount = requestsFor(requests, AI_PATHS.adopt).length
          assertEqual(adoptCount, 1, `连续点击导致 /adopt 被调用 ${adoptCount} 次`)
          return {
            notes: ['采用按钮在提交期间被禁用；连续点击只产生 1 次采用'],
            evidence: [await shot(page, 'E02-double-adopt', 'resilience')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'E03-backend-down-shows-error-not-fixture',
      title: '后端不可用：页面报错且不回退到任何 fixture',
      priority: 'P1',
      phase: 'live',
      run: async ({ browser, deadBackendFrontend }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await page.goto(`${deadBackendFrontend.baseUrl}/`, { waitUntil: 'domcontentloaded' })
          await waitForState(page, 'app-nav', { timeout: 20000 })
          await page.waitForTimeout(2500)
          const body = await page.locator('body').innerText()
          const hasErrorState =
            body.includes('失败') || body.includes('错误') || body.includes('无法')
          assert(hasErrorState, '后端不可用时页面没有显示错误状态')
          assert(
            !body.includes('（前端预览）') && !body.includes('仅前端预览 / 非真实模型'),
            '后端不可用时页面显示了预览 fixture 内容',
          )
          return {
            notes: ['后端不可用 ⇒ 明确错误态，未出现预览/替代数据'],
            evidence: [await shot(page, 'E03-backend-down', 'resilience')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
  ]
}

/* ------------------------------------------------------------------ *
 * disabled / preview 档
 * ------------------------------------------------------------------ */

export function disabledCases({ baseUrl }) {
  return [
    {
      id: 'D01-ai-disabled-state',
      title: 'AI 未启用：如实显示未启用，且不发任何 AI 请求',
      priority: 'P0',
      phase: 'disabled',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          await openDrawer(page)
          const unavailable = await page
            .locator('[data-testid="ai-unavailable"]')
            .first()
            .waitFor({ state: 'visible', timeout: 20000 })
            .then(() => true)
            .catch(() => false)
          assert(unavailable, '后端未启用时没有显示"不可用"状态')
          const reason = await textOf(page, 'ai-unavailable-reason')
          assert(reason.length > 0, '不可用状态没有给出原因')
          for (const path of [AI_PATHS.interpret, AI_PATHS.solve, AI_PATHS.adopt]) {
            assertEqual(requestsFor(requests, path).length, 0, `未启用时仍调用了 ${path}`)
          }
          return {
            notes: [`未启用原因：${reason.slice(0, 60)}`],
            evidence: [await shot(page, 'D01-ai-disabled', 'disabled')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
  ]
}

export function previewCases({ baseUrl }) {
  return [
    {
      id: 'P01-preview-fully-labelled',
      title: '前端预览档：必须标注"仅前端预览 / 非真实模型 / 未调用 Planner"',
      priority: 'P0',
      phase: 'preview',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        try {
          await gotoHome(page, baseUrl)
          await openDrawer(page)
          // 抽屉级通道标签：必须是"前端预览（只读 fixture）"
          const channel = await textOf(page, 'ai-drawer-channel')
          assert(
            channel.includes('预览'),
            `通道说明没有标明预览：${channel}`,
          )
          // 预览档同样走一次"解析"：解析结果来自 fixture，必须带醒目标注
          await fillAndParse(page, '尽量别在周五上课，最多 12 学分')
          await waitForDraftPanel(page)
          const notice = await textOf(page, 'ai-preview-notice')
          assertIncludes(notice, '仅前端预览', `预览标注缺失：${notice}`)
          assertIncludes(notice, '非真实模型', `预览标注未说明不是真实模型：${notice}`)
          assertIncludes(notice, '未调用 Planner', `预览标注未说明未调用 Planner：${notice}`)
          // ⛔ 预览档不得对 ai-planning 发出任何真实请求
          const backendCalls = apiRequests(requests).filter((i) => i.url.includes('/ai-planning/'))
          assertEqual(backendCalls.length, 0, '预览档对 ai-planning 发出了真实请求')
          return {
            notes: [
              `通道：${channel}`,
              `预览标注：${notice}`,
              '本轮未对 /ai-planning/* 发出任何请求',
            ],
            evidence: [await shot(page, 'P01-preview-notice', 'preview')],
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
  ]
}

export { AI_PATHS, GENEROUS_MESSAGE, NEW_COURSE }
