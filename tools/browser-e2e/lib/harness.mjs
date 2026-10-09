/**
 * 浏览器 E2E 的最小测试骨架（**只用 playwright-core，复用系统 Edge**）。
 *
 * 为什么不用 `@playwright/test`：
 * - 它默认期望 `playwright` 包与 `npx playwright install` 下载的浏览器（≈数百 MB），
 *   而本机已有 Microsoft Edge，`chromium.launch({ channel: 'msedge' })` 可直接复用；
 * - 因此只需**一个** devDependency（`playwright-core`，无浏览器下载），
 *   依赖风险与安装成本最小；
 * - 代价：需要自己提供断言、超时与结果汇总 —— 本文件就是那部分（约 100 行）。
 *
 * ⛔ 本文件只做测试基础设施，不触碰任何生产代码。
 */

import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

export const HERE = dirname(fileURLToPath(import.meta.url))
export const REPO_ROOT = join(HERE, '..', '..', '..')
/** `tools/browser-e2e`：本套件根目录（截图与结果 JSON 都放这里）。 */
export const E2E_DIR = join(HERE, '..')
export const ARTIFACT_DIR = join(E2E_DIR, 'artifacts')

/** 一个用例的断言失败（区别于基础设施异常）。 */
export class AssertionFailure extends Error {
  constructor(message) {
    super(message)
    this.name = 'AssertionFailure'
  }
}

export function assert(condition, message) {
  if (!condition) {
    throw new AssertionFailure(message)
  }
}

export function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new AssertionFailure(`${message}（实际 ${JSON.stringify(actual)}，期望 ${JSON.stringify(expected)}）`)
  }
}

export function assertIncludes(haystack, needle, message) {
  if (typeof haystack !== 'string' || !haystack.includes(needle)) {
    throw new AssertionFailure(`${message}（未找到 ${JSON.stringify(needle)}）`)
  }
}

export function assertNotIncludes(haystack, needle, message) {
  if (typeof haystack === 'string' && haystack.includes(needle)) {
    throw new AssertionFailure(`${message}（不应出现 ${JSON.stringify(needle)}）`)
  }
}

export async function ensureArtifactDir(sub = '') {
  const dir = sub ? join(ARTIFACT_DIR, sub) : ARTIFACT_DIR
  await mkdir(dir, { recursive: true })
  return dir
}

/** 启动系统 Edge（headless 可切换），返回 browser。 */
export async function launchBrowser({ headless = true } = {}) {
  return chromium.launch({ channel: 'msedge', headless })
}

/**
 * 打开一个页面，并绑定请求记录 / 控制台错误记录。
 *
 * `requests` 会记录**浏览器实际发出的每一次 HTTP 请求**（url / method / resourceType），
 * `responses` 记录状态码，`consoleErrors` 记录 console error 与 pageerror。
 */
export async function openPage(browser, { viewport = { width: 1440, height: 900 } } = {}) {
  const context = await browser.newContext({ viewport, locale: 'zh-CN' })
  const page = await context.newPage()
  const requests = []
  const responses = []
  const apiBodies = []
  const consoleErrors = []

  page.on('request', (request) => {
    requests.push({
      method: request.method(),
      url: request.url(),
      resourceType: request.resourceType(),
      postData: request.postData() ?? null,
    })
  })
  page.on('response', (response) => {
    responses.push({ status: response.status(), url: response.url() })
    // 只抓 API 响应体（含错误体），用于在报告里给出"浏览器实际收到什么"
    if (response.url().includes('/api/') && !response.url().includes('/@vite')) {
      response
        .text()
        .then((text) => {
          apiBodies.push({
            status: response.status(),
            url: response.url(),
            body: text.length > 2000 ? `${text.slice(0, 2000)}…` : text,
          })
        })
        .catch(() => {
          apiBodies.push({ status: response.status(), url: response.url(), body: '<unreadable>' })
        })
    }
  })
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })
  page.on('pageerror', (error) => {
    consoleErrors.push(`pageerror: ${error.message}`)
  })

  return { context, page, requests, responses, apiBodies, consoleErrors }
}

/** 只统计 API 请求（排除静态资源与 Vite 内部请求）。 */
export function apiRequests(requests, needle = '/api/') {
  return requests.filter((item) => item.url.includes(needle) && !item.url.includes('/@vite'))
}

export function requestsFor(requests, pathFragment) {
  return apiRequests(requests).filter((item) => item.url.includes(pathFragment))
}

/**
 * 截图：默认只截**视口**（抽屉是 fixed 面板，fullPage 会把页面拉长导致抽屉被压扁）。
 * 需要整页证据时传 `{ fullPage: true }`。
 */
export async function shot(page, name, sub = '', { fullPage = false } = {}) {
  const dir = await ensureArtifactDir(sub)
  const file = join(dir, `${name}.png`)
  await page.screenshot({ path: file, fullPage })
  return `artifacts/${sub ? `${sub}/` : ''}${name}.png`
}

export async function waitForState(page, testId, { timeout = 15000, state = 'visible' } = {}) {
  const locator = page.locator(`[data-testid="${testId}"]`)
  await locator.first().waitFor({ state, timeout })
  return locator.first()
}

export async function textOf(page, testId) {
  const locator = page.locator(`[data-testid="${testId}"]`).first()
  return (await locator.textContent())?.trim() ?? ''
}

export function uniqueSorted(values) {
  return [...new Set(values)].sort()
}

/**
 * 极简 runner：顺序执行用例，收集结果，产出 JSON 结果供报告生成使用。
 *
 * `testCase.skip === true` 的用例会被**跳过并记录为 skipped**（不计入 passed/failed），
 * 用于"只重跑某个 PR 原有用例"的对照验证。
 */
export async function runCases(cases, { filter = null, onResult = null } = {}) {
  const results = []
  for (const testCase of cases) {
    if (filter && !testCase.id.includes(filter)) {
      continue
    }
    if (testCase.skip === true) {
      console.log(`  ⏭️  ${testCase.id} — ${testCase.title}（本变体跳过）`)
      results.push({
        id: testCase.id,
        title: testCase.title,
        priority: testCase.priority ?? 'P0',
        phase: testCase.phase ?? 'live',
        status: 'skipped',
        error: null,
        notes: ['该用例不属于本次验证范围，已跳过'],
        evidence: [],
        httpRequests: [],
        durationMs: 0,
      })
      continue
    }
    const started = Date.now()
    const record = {
      id: testCase.id,
      title: testCase.title,
      priority: testCase.priority ?? 'P0',
      phase: testCase.phase ?? 'live',
      status: 'passed',
      error: null,
      notes: [],
      evidence: [],
      httpRequests: [],
      durationMs: 0,
    }
    try {
      const output = await testCase.run()
      if (output && typeof output === 'object') {
        record.notes = output.notes ?? []
        record.evidence = output.evidence ?? []
        record.httpRequests = output.httpRequests ?? []
      }
      console.log(`  ✅ ${testCase.id} — ${testCase.title}`)
    } catch (error) {
      record.status = error instanceof AssertionFailure ? 'failed' : 'error'
      record.error = `${error.name}: ${error.message}`
      console.log(`  ❌ ${testCase.id} — ${testCase.title}\n     ${record.error}`)
    }
    record.durationMs = Date.now() - started
    results.push(record)
    if (onResult) {
      await onResult(record)
    }
  }
  return results
}

export async function writeJson(path, value) {
  await mkdir(dirname(path), { recursive: true })
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, 'utf-8')
}
