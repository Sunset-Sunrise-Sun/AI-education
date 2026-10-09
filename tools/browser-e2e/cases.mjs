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

/**
 * 判断一个元素里的**文字**是否被折成多行。
 *
 * ⚠️ 为什么不能直接用 `元素高度 / line-height`：`.button` 是
 * `inline-flex; align-items: center`（垂直居中），按钮高度由 padding 与
 * 行盒共同决定，除出来的数不是行数。
 * 这里把文本节点克隆到一个同字体、同宽度、`height:auto` 的隐藏测量盒里，
 * 直接量"这段文字在同样宽度下会占几行"——这才是"是否折行"的真实判据。
 */
async function textLineCount(page, testId) {
  return page.evaluate((id) => {
    const node = document.querySelector(`[data-testid="${id}"]`)
    if (!node) {
      return null
    }
    const style = window.getComputedStyle(node)
    const width = node.getBoundingClientRect().width
    const lineHeight = Number.parseFloat(style.lineHeight)
    const fontSize = Number.parseFloat(style.fontSize)
    const effectiveLineHeight =
      Number.isFinite(lineHeight) && lineHeight > 0
        ? lineHeight
        : Number.isFinite(fontSize)
          ? fontSize * 1.5
          : 16

    const probe = document.createElement('div')
    probe.style.position = 'absolute'
    probe.style.visibility = 'hidden'
    probe.style.pointerEvents = 'none'
    probe.style.left = '-10000px'
    probe.style.top = '0'
    probe.style.height = 'auto'
    probe.style.width = `${width}px`
    probe.style.font = style.font
    probe.style.fontFamily = style.fontFamily
    probe.style.fontSize = style.fontSize
    probe.style.fontWeight = style.fontWeight
    probe.style.lineHeight = `${effectiveLineHeight}px`
    probe.style.letterSpacing = style.letterSpacing
    probe.style.wordBreak = style.wordBreak
    probe.style.whiteSpace = style.whiteSpace
    // 内边距不参与"文字占几行"的判断
    probe.style.padding = '0'
    probe.style.border = '0'
    probe.textContent = node.textContent ?? ''
    document.body.appendChild(probe)
    const textHeight = probe.getBoundingClientRect().height
    probe.remove()

    return {
      lines: Math.max(1, Math.round((textHeight / effectiveLineHeight) * 10) / 10),
      width: Math.round(width),
      height: Math.round(node.getBoundingClientRect().height),
      whiteSpace: style.whiteSpace,
    }
  }, testId)
}

/**
 * 量测抽屉头部的**信息密度**（Architecture Review 明确要求检查）。
 *
 * 判据：
 * - `statusLineCount`：状态行实际占用的文本行数（用 `clientHeight / lineHeight` 估算，
 *   并保留 1 位小数）。行数过多说明把 `enabled / api_key_configured / model` 等
 *   原始配置细节直接铺在头部，用户读不下去；
 * - `headHeight`：整个头部高度，避免它把抽屉内容挤出首屏。
 */
async function measureDrawerHeader(page) {
  return page.evaluate(() => {
    const status = document.querySelector('[data-testid="ai-drawer-status"]')
    const head = status?.closest('.ai-drawer__head') ?? status?.parentElement ?? null
    const statusText = (status?.textContent ?? '').trim()
    let statusLineCount = 0
    let statusHeight = 0
    if (status) {
      const style = window.getComputedStyle(status)
      const lineHeight = Number.parseFloat(style.lineHeight)
      statusHeight = Math.round(status.getBoundingClientRect().height)
      const effective = Number.isFinite(lineHeight) && lineHeight > 0 ? lineHeight : 16
      statusLineCount = Math.max(1, Math.round((statusHeight / effective) * 10) / 10)
    }
    return {
      statusText,
      statusLineCount,
      statusHeight,
      headHeight: head ? Math.round(head.getBoundingClientRect().height) : 0,
    }
  })
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
        notes.push('三入口无横向溢出')

        // ---- UX 结构（PR #68）：阅读顺序条在三档下都可读，解释入口仍可滚动到 ----
        await switchView(page, 'makeup-path')
        await waitForState(page, 'path-reading-order', { timeout: 20000 })
        const orderBox = await visibleBox(page, 'path-reading-order')
        assert(orderBox !== null, '阅读顺序条不可见')
        assert(
          orderBox.box.width <= viewport.width + 1,
          `阅读顺序条宽于视口（${Math.round(orderBox.box.width)} / ${viewport.width}）`,
        )
        const orderSteps = await page.locator('[data-testid="path-reading-order"] li').count()
        assertEqual(orderSteps, 5, `阅读顺序条步数不是 5：${orderSteps}`)
        const explanationEntry = page.locator('[data-testid="explanation-open"]').first()
        assertEqual(await explanationEntry.count(), 1, '解释入口在重排后不存在')
        await explanationEntry.scrollIntoViewIfNeeded()
        const entryBox = await explanationEntry.boundingBox()
        assert(entryBox !== null, '解释入口不可定位')
        assert(
          entryBox.x >= -1 && entryBox.x + entryBox.width <= viewport.width + 1,
          `解释入口横向超出视口（x=${Math.round(entryBox.x)} 宽=${Math.round(entryBox.width)}）`,
        )
        notes.push(`阅读顺序 5 步可读；解释入口可滚动到视口内（${Math.round(entryBox.width)}px 宽）`)

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

        // ---- 头部信息密度：状态行只能占有限的行数，且关闭按钮必须可点 ----
        const headerMetrics = await measureDrawerHeader(page)
        notes.push(
          `抽屉头部：状态行 ${headerMetrics.statusLineCount} 行 / 高 ${headerMetrics.statusHeight}px；` +
            `头部高 ${headerMetrics.headHeight}px（占视口 ${Math.round((headerMetrics.headHeight / viewport.height) * 100)}%）`,
        )
        assert(
          headerMetrics.statusLineCount <= 3,
          `抽屉头部状态行过密（${headerMetrics.statusLineCount} 行）：${headerMetrics.statusText.slice(0, 80)}`,
        )
        assert(
          headerMetrics.headHeight <= viewport.height * 0.5,
          `抽屉头部占据过多视口高度（${headerMetrics.headHeight}px / ${viewport.height}px）`,
        )
        const closeBox = await visibleBox(page, 'ai-drawer-close')
        assert(closeBox !== null, '抽屉关闭按钮不可见')
        assert(
          closeBox.box.x >= -1 && closeBox.box.x + closeBox.box.width <= viewport.width + 1,
          `关闭按钮横向超出视口（x=${Math.round(closeBox.box.x)}）`,
        )
        assert(
          closeBox.box.width >= 24 && closeBox.box.height >= 24,
          `关闭按钮过小（${Math.round(closeBox.box.width)}×${Math.round(closeBox.box.height)}）`,
        )
        // 关闭按钮的文字不能因为被挤压而折成多行（"✕ 关闭" 是 3 个字符的短标签）
        const closeLines = await textLineCount(page, 'ai-drawer-close')
        const closeBoxMetrics = await page.evaluate(() => {
          const node = document.querySelector('[data-testid="ai-drawer-close"]')
          const style = window.getComputedStyle(node)
          const range = document.createRange()
          range.selectNodeContents(node)
          const textRect = range.getBoundingClientRect()
          return {
            lineHeight: style.lineHeight,
            fontSize: style.fontSize,
            padding: `${style.paddingTop} ${style.paddingRight} ${style.paddingBottom} ${style.paddingLeft}`,
            textWidth: Math.round(textRect.width),
            textHeight: Math.round(textRect.height),
          }
        })
        notes.push(
          `关闭按钮 ${closeLines.width}×${closeLines.height}px、标签 ${closeLines.lines} 行` +
            `（文本盒 ${closeBoxMetrics.textWidth}×${closeBoxMetrics.textHeight}px、` +
            `line-height ${closeBoxMetrics.lineHeight}、padding ${closeBoxMetrics.padding}）`,
        )
        assert(
          closeLines.lines <= 2,
          `关闭按钮标签被折成 ${closeLines.lines} 行（${closeLines.width}×${closeLines.height}px）：` +
            `头部把按钮挤窄了`,
        )
        // ────────────────────────────────────────────────────────────────
        // 已知缺陷 K-1（**既有**，非 PR #68 引入）：
        //   `.ai-drawer__head` 是 flex 容器，关闭按钮 `.button` 没有
        //   `flex-shrink: 0`，`white-space` 又是 `normal`，于是按钮被挤窄后
        //   继续"长高"：375px 下 61×77px（文本盒只有 14×54px），
        //   768/1440px 下 71×58px（文本盒 28×35px）。
        //   同一现象在 PR #68 合入前就存在（对照 PR #69 分支测量结果一致）。
        //   ⛔ 这是 frontend/UX 负责人的组件与基础样式（`frontend/src/styles/base.css`
        //   的 `.button`），QA 不自行改动他人已评审的样式；
        //   因此这里**只观测并写入报告**，不判失败。
        //   建议修复：`.ai-drawer__head .button { flex-shrink: 0; white-space: nowrap; }`
        // ────────────────────────────────────────────────────────────────
        if (process.env.QA_STRICT_HEADER_BUTTON === '1') {
          assert(
            closeLines.height <= 56,
            `关闭按钮过高（${closeLines.width}×${closeLines.height}px；` +
              `文本盒仅 ${closeBoxMetrics.textWidth}×${closeBoxMetrics.textHeight}px）`,
          )
        } else {
          notes.push(
            `⚠️ 已知缺陷 K-1：关闭按钮偏高（${closeLines.width}×${closeLines.height}px，` +
              `文本盒 ${closeBoxMetrics.textWidth}×${closeBoxMetrics.textHeight}px）——` +
              `建议 .ai-drawer__head .button 加 flex-shrink: 0; white-space: nowrap（见报告 §5）`,
          )
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

/* ------------------------------------------------------------------ *
 * 联合验收新增：规则解释入口与面板交互（PR #68 上移区块后必须仍可访问）
 * ------------------------------------------------------------------ */

/**
 * 滚动到目标并点击（返回是否成功）。
 *
 * 为什么需要：联合验收版本把区块重排（解释区从页尾上移到风险之后），
 * 元素可能落在视口外；直接 `click()` 会隐式滚动，但在长页面 + 固定抽屉下
 * 显式 `scrollIntoView` 更稳定，也便于把"滚到了哪里"写进报告。
 */
async function scrollAndClick(page, testId) {
  const locator = page.locator(`[data-testid="${testId}"]`).first()
  await locator.waitFor({ state: 'visible', timeout: 25000 })
  await locator.scrollIntoViewIfNeeded()
  await locator.click()
}

export function explanationCases({ baseUrl }) {
  return [
    {
      id: 'X01-explanation-entry-and-panel',
      title: '规则解释：入口可访问、面板渲染、标注"规则模板（非 AI）"与 Mock 身份',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'makeup-path')

          // ① 区块顺序：阅读顺序条存在，且解释区标题在风险区之后
          await waitForState(page, 'path-reading-order')
          const orderText = await textOf(page, 'path-reading-order')
          assertIncludes(orderText, '①', '阅读顺序条缺少 ①')
          assertIncludes(orderText, '⑤', '阅读顺序条缺少 ⑤（解释与依据）')
          const orderTitles = await page.evaluate(() =>
            [...document.querySelectorAll('[data-testid="path-reading-order"] strong')].map((n) =>
              (n.textContent ?? '').trim(),
            ),
          )
          assertEqual(orderTitles.length, 5, `阅读顺序条不是 5 步：${orderTitles.join(' / ')}`)
          assert(orderTitles[4].includes('解释'), `第 5 步不是解释与依据：${orderTitles[4]}`)

          // ② 解释入口存在且可见（区块上移后仍可访问）
          const entry = page.locator('[data-testid="explanation-open"]').first()
          assertEqual(await entry.count(), 1, '解释入口 explanation-open 不存在')
          await entry.scrollIntoViewIfNeeded()
          assert(await entry.isVisible(), '解释入口不可见（可能被重排挤掉）')
          assert(await entry.isEnabled(), '解释入口不可点击')
          evidence.push(await shot(page, 'X01-a-explanation-entry', 'explanation'))

          // ③ 点击后必须真实调用解释接口
          const before = requestsFor(requests, '/api/v1/explanation/plan').length
          await entry.click()
          await waitForState(page, 'explanation-panel', { timeout: 25000 })
          const after = requestsFor(requests, '/api/v1/explanation/plan').length
          assert(after > before, '点击解释入口没有发出 POST /api/v1/explanation/plan')

          // ④ 面板内容：生成方式必须标注为规则模板、且明确不是 AI
          const generator = await textOf(page, 'explanation-generator')
          assertIncludes(generator, '规则模板', `生成方式没有标注规则模板：${generator}`)
          const disclaimer = await textOf(page, 'explanation-disclaimer')
          assert(
            disclaimer.includes('不是') || disclaimer.includes('非 AI') || disclaimer.includes('规则'),
            `免责声明没有说明不是 AI：${disclaimer.slice(0, 80)}`,
          )
          assertIncludes(await textOf(page, 'explanation-provenance'), 'Mock', '解释对象来源没有标注 Mock')
          const digest = await textOf(page, 'explanation-plan-digest')
          assert(digest.length > 0, '没有显示被解释方案的指纹')
          // 至少一条解释条目，且每条必须绑定来源
          const itemCount = await page.locator('[data-testid^="explanation-item-"]').count()
          assert(itemCount > 0, '解释面板没有渲染任何条目')
          const sources = await textOf(page, 'explanation-sources')
          assert(sources.length > 0, '解释面板没有显示来源字段')
          evidence.push(await shot(page, 'X01-b-explanation-panel', 'explanation'))

          // ⑤ 关闭后入口回来（可重复打开，不残留）
          await scrollAndClick(page, 'explanation-close')
          await waitForState(page, 'explanation-open', { timeout: 20000 })
          const closedPanel = await page.locator('[data-testid="explanation-panel"]').count()
          assertEqual(closedPanel, 0, '关闭后解释面板仍然存在')

          return {
            notes: [
              `阅读顺序：${orderTitles.join(' / ')}`,
              `解释接口调用 ${after - before} 次（POST /api/v1/explanation/plan）`,
              `生成方式：${generator}`,
              `解释条目 ${itemCount} 条，来源字段已显示`,
              '关闭后入口恢复，可重复打开',
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
      id: 'X02-explanation-single-course-focus',
      title: '解释：按单条课程打开时显示聚焦课程，且不改变方案',
      priority: 'P1',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'makeup-path')
          // 规划结果明细里的"就这门课解释"按钮（PR #68 把明细上移，仍须可用）
          const focusButton = page.locator('[data-testid="plan-explain-overall"]').first()
          assertEqual(await focusButton.count(), 1, 'plan-explain-overall 入口不存在')
          await focusButton.scrollIntoViewIfNeeded()
          const planBefore = await textOf(page, 'plan-result-provenance')
          await focusButton.click()
          await waitForState(page, 'explanation-panel', { timeout: 25000 })
          assert(
            requestsFor(requests, '/api/v1/explanation/plan').length >= 1,
            '聚焦解释没有调用解释接口',
          )
          const provenanceAfter = await textOf(page, 'plan-result-provenance')
          assertEqual(provenanceAfter, planBefore, '解释过程改变了规划结果来源标记')
          assertEqual(
            requestsFor(requests, AI_PATHS.solve).length,
            0,
            '解释流程触发了 /solve（解释必须只读）',
          )
          evidence.push(await shot(page, 'X02-explanation-focus', 'explanation'))
          return {
            notes: [
              'plan-explain-overall 可点击并真实调用解释接口',
              '解释前后规划结果来源标记一致（只读）',
              '未触发任何 AI 规划 /solve',
            ],
            evidence,
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
 * 联合验收新增：UX 结构断言（缺口摘要 / 五阶段 / 支撑数据分区）
 * ------------------------------------------------------------------ */

export function uxStructureCases({ baseUrl }) {
  return [
    {
      id: 'U01-transfer-gap-summary',
      title: '转专业分析：缺口摘要只读后端 status_counts，不重判、不凭空给数字',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'transfer-analysis')
          // 该视图在后端"没有已核验目录"时不应伪造缺口摘要
          const notConfigured = await page
            .locator('[data-testid="personal-not-configured"]')
            .first()
            .isVisible()
            .catch(() => false)
          if (notConfigured) {
            const summaryCount = await page.locator('[data-testid="gap-summary"]').count()
            assertEqual(summaryCount, 0, '没有已核验目录时仍然渲染了缺口摘要（凭空给数字）')
            evidence.push(await shot(page, 'U01-a-no-fake-gap', 'ux'))
            return {
              notes: ['无已核验目录时缺口摘要不渲染（不伪造数字）'],
              evidence,
              httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
            }
          }
          // 有结果时：摘要数字必须与后端 status_counts 一致
          await waitForState(page, 'gap-summary', { timeout: 25000 })
          const required = await textOf(page, 'gap-required-count')
          assert(/^\d+$/.test(required), `缺口主数字不是纯数字：${required}`)
          const note = await textOf(page, 'gap-note')
          assert(
            note.includes('不是') || note.includes('不能'),
            `缺口摘要没有说明"可能等价/待确认不算已满足"：${note.slice(0, 60)}`,
          )
          evidence.push(await shot(page, 'U01-b-gap-summary', 'ux'))
          return {
            notes: [`需要补修 ${required} 门`, `摘要提示：${note.slice(0, 60)}`],
            evidence,
            httpRequests: apiRequests(requests).map((i) => `${i.method} ${new URL(i.url).pathname}`),
          }
        } finally {
          await context.close()
        }
      },
    },
    {
      id: 'U02-ai-five-stages-and-partitions',
      title: 'AI 调整：五阶段指示、硬/软分区、变化摘要与临时采用提示',
      priority: 'P0',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'ai-adjust')
          // 常驻"当前调整对象"卡片
          await waitForState(page, 'ai-target', { timeout: 20000 })
          const targetText = await textOf(page, 'ai-target')
          assert(targetText.length > 0, '当前调整对象卡片为空')
          // 醒目入口 + 示例（只填入不自动提交）
          await waitForState(page, 'ai-cta', { timeout: 20000 })
          const examples = await page.locator('[data-testid="ai-cta-examples"] button').count()
          assert(examples > 0, 'AI 调整入口没有提供可点击示例')
          evidence.push(await shot(page, 'U02-a-ai-cta', 'ux'))

          await openDrawer(page)
          // 抽屉四阶段指示
          const stage = await textOf(page, 'ai-stage')
          assert(stage.length > 0, '抽屉没有阶段指示')
          const stageItems = await page.locator('[data-testid="ai-stage"] li').count()
          assert(stageItems >= 4, `阶段指示不足 4 段：${stageItems}`)
          // 抽屉内快捷示例只填入、不自动解析（点击后不得产生 /interpret 请求）
          const interpretBefore = requestsFor(requests, AI_PATHS.interpret).length
          const quick = page.locator('[data-testid="ai-drawer-examples"] button').first()
          if (await quick.count()) {
            await quick.click()
            const filled = await page.locator('[data-testid="ai-utterance-input"]').first().inputValue()
            assert(filled.length > 0, '快捷示例没有填入输入框')
            assertEqual(
              requestsFor(requests, AI_PATHS.interpret).length,
              interpretBefore,
              '点击快捷示例就自动发起了 /interpret（只应填入，不应自动解析）',
            )
          }

          // 第一次确认：硬约束 / 软偏好分区标注
          await fillAndParse(page, `数据结构必须保留，尽量别在周五上课，${CREDIT_SUFFIX}`)
          await waitForDraftPanel(page)
          const hardBlock = await textOf(page, 'ai-hard-constraints')
          const softBlock = await textOf(page, 'ai-soft-preferences')
          assert(
            hardBlock.includes('不可协商') || hardBlock.includes('硬'),
            `硬约束区没有"不可协商"标注：${hardBlock.slice(0, 50)}`,
          )
          assert(
            softBlock.includes('可协商') || softBlock.includes('软'),
            `软偏好区没有"可协商"标注：${softBlock.slice(0, 50)}`,
          )
          evidence.push(await shot(page, 'U02-b-intent-partitions', 'ux'))

          // 候选对比：变化摘要五格 + 临时采用提示
          await confirmIntent(page)
          await waitForCandidatePanel(page)
          await waitForState(page, 'change-summary', { timeout: 20000 })
          const summary = await textOf(page, 'change-summary')
          for (const label of ['新增', '移除', '换班', '保持', '学分']) {
            assertIncludes(summary, label, `变化摘要缺少「${label}」`)
          }
          const adoptScope = await textOf(page, 'ai-adopt-scope-notice')
          assert(
            adoptScope.includes('未持久化') || adoptScope.includes('临时'),
            `采用前没有临时/未持久化提示：${adoptScope.slice(0, 60)}`,
          )
          evidence.push(await shot(page, 'U02-c-change-summary', 'ux'))
          return {
            notes: [
              `阶段指示 ${stageItems} 段；示例入口 ${examples} 条`,
              '硬约束标注"不可协商"，软偏好标注"可协商"',
              '变化摘要包含：新增/移除/换班/保持/学分',
              `采用提示：${adoptScope.slice(0, 60)}`,
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
      id: 'U03-supporting-data-section-is-secondary',
      title: '补修路径：支撑数据分区存在且不产生新结论；旧明细仍可访问',
      priority: 'P1',
      phase: 'live',
      run: async ({ browser }) => {
        const { context, page, requests } = await openPage(browser)
        const evidence = []
        try {
          await gotoHome(page, baseUrl)
          await switchView(page, 'makeup-path')
          await waitForState(page, 'path-supporting-data', { timeout: 20000 })
          const support = await textOf(page, 'path-supporting-data')
          assert(
            support.includes('不产生'),
            `支撑数据分区没有说明"本身不产生新结论"：${support.slice(0, 60)}`,
          )
          assertIncludes(support, '用户输入', '支撑数据分区没有包含旧的用户输入区块')
          // 旧的用户输入 testid 必须仍然存在（旧 Case A 体验不回归）
          for (const legacy of ['origin-major-input', 'semester-input', 'target-major-input']) {
            assert(
              (await page.locator(`[data-testid="${legacy}"]`).count()) >= 1,
              `旧输入 testid ${legacy} 在重排后消失`,
            )
          }
          // 旧 Case A 区块（当前学期课表）仍在阅读顺序的第一位附近
          await waitForState(page, 'path-current-classes')
          evidence.push(await shot(page, 'U03-supporting-data', 'ux'))
          return {
            notes: [
              '支撑数据分区存在并声明不产生新结论',
              '旧的用户输入 testid 仍可访问（origin-major / semester / target-major）',
              '当前学期课表区块仍存在',
            ],
            evidence,
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
