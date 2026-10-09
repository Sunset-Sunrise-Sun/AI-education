/**
 * 浏览器 E2E 运行器。
 *
 * 编排五组服务（每组都含真实后端 + 真实 Vite 前端）：
 *
 * | 组 | 后端 | 前端档位 | 用途 |
 * | --- | --- | --- | --- |
 * | live | QA 注入式测试模型，TTL 默认 | AI 真实通道开、预览关 | P0 主流程 / 响应式 / 并发 |
 * | shortTtl | 同上，`QA_ADOPT_TTL_SECONDS=2` | 同 live | 候选过期 410 |
 * | disabled | QA app + `QA_AI_PLANNING_ENABLED=0`（不注入模型） | 同 live | AI 未启用档 |
 * | preview | live 后端（只为 Demo 数据） | `VITE_AI_PLANNING_PREVIEW=true`、真实通道关 | 纯前端预览标注 |
 * | deadBackend | 端口不监听（前端代理指向空端口） | 同 live | 后端不可用 |
 *
 * 用法（仓库根目录）：
 *   node tools/browser-e2e/run_browser_e2e.mjs                # 全部用例
 *   node tools/browser-e2e/run_browser_e2e.mjs --filter=L04   # 只跑匹配的用例
 *   node tools/browser-e2e/run_browser_e2e.mjs --headed       # 显示浏览器窗口
 */

import { existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import {
  ARTIFACT_DIR,
  REPO_ROOT,
  launchBrowser,
  runCases,
  writeJson,
} from './lib/harness.mjs'
import { freePort, startBackend, startFrontend, stopAll } from './lib/servers.mjs'

const args = process.argv.slice(2)
const filter = args.find((item) => item.startsWith('--filter='))?.slice('--filter='.length) ?? null
const headed = args.includes('--headed')
/**
 * `--cases=<文件名>`：换一个用例文件（默认 `cases.mjs`）。
 * 用途：只用**某个 PR 原有的用例集**重跑一次做对照验证。
 */
const casesArg = args.find((item) => item.startsWith('--cases='))?.slice('--cases='.length) ?? 'cases.mjs'

const caseModule = await import(pathToFileURL(join(import.meta.dirname, casesArg)).href)
const {
  disabledCases,
  explanationCases,
  liveBaselineCases,
  previewCases,
  resilienceCases,
  responsiveCases,
  uxStructureCases,
} = caseModule

/** 找一个可用的 Python 解释器（优先环境变量 QA_PYTHON）。 */
function detectPython() {
  if (process.env.QA_PYTHON) {
    return process.env.QA_PYTHON
  }
  const candidates = [
    process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python314', 'python.exe'),
    process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python313', 'python.exe'),
    process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python312', 'python.exe'),
    'python',
  ].filter(Boolean)
  for (const candidate of candidates) {
    if (candidate === 'python' || existsSync(candidate)) {
      return candidate
    }
  }
  return 'python'
}

/** 列出仓库根与 frontend 下会影响档位的 `.env*` 文件（只报告，不修改）。 */
function envFileInventory() {
  const files = []
  for (const dir of [REPO_ROOT, join(REPO_ROOT, 'frontend')]) {
    if (!existsSync(dir)) {
      continue
    }
    for (const name of readdirSync(dir)) {
      if (name === '.env' || name.startsWith('.env.')) {
        files.push(join(dir.replace(`${REPO_ROOT}\\`, ''), name).replace(/\\/g, '/'))
      }
    }
  }
  return files
}

const LIVE_FRONTEND_ENV = {
  VITE_PLAN_API_ENABLED: 'false',
  VITE_EXPLANATION_API_ENABLED: 'true',
  VITE_PERSONAL_PLANNING_API_ENABLED: 'true',
  VITE_PERSONAL_PLANNING_PREVIEW: 'false',
  VITE_AI_PLANNING_API_ENABLED: 'true',
  VITE_AI_PLANNING_PREVIEW: 'false',
}

const PREVIEW_FRONTEND_ENV = {
  ...LIVE_FRONTEND_ENV,
  VITE_AI_PLANNING_API_ENABLED: 'false',
  VITE_AI_PLANNING_PREVIEW: 'true',
}

async function main() {
  const python = detectPython()
  const startedAt = new Date()
  process.stdout.write(`\n=== 浏览器 E2E（${headed ? 'headed' : 'headless'} Edge）===\n`)
  process.stdout.write(`python: ${python}\n`)

  const envFiles = envFileInventory()
  const services = []
  const results = []
  let browser = null

  try {
    // --- 组 1：live ---
    const liveBackend = await startBackend({ python, name: 'backend-live' })
    const liveFrontend = await startFrontend({
      proxyTarget: liveBackend.baseUrl,
      env: LIVE_FRONTEND_ENV,
      name: 'frontend-live',
    })
    services.push(liveBackend, liveFrontend)

    // --- 组 2：shortTtl（候选过期）---
    const shortTtlBackend = await startBackend({
      python,
      name: 'backend-short-ttl',
      env: { QA_ADOPT_TTL_SECONDS: '2' },
    })
    const shortTtlFrontend = await startFrontend({
      proxyTarget: shortTtlBackend.baseUrl,
      env: LIVE_FRONTEND_ENV,
      name: 'frontend-short-ttl',
    })
    services.push(shortTtlBackend, shortTtlFrontend)

    // --- 组 3：disabled（后端关闭 AI 控制器，前端仍开启真实通道）---
    const disabledBackend = await startBackend({
      python,
      name: 'backend-disabled',
      env: { QA_AI_PLANNING_ENABLED: '0' },
    })
    const disabledFrontend = await startFrontend({
      proxyTarget: disabledBackend.baseUrl,
      env: LIVE_FRONTEND_ENV,
      name: 'frontend-disabled',
    })
    services.push(disabledBackend, disabledFrontend)

    // --- 组 4：preview（真实 demo 数据 + 前端预览开关，AI 真实通道关闭）---
    // ⚠️ 预览档仍然指向**可用后端**：这样首屏 Demo 数据能加载（页面才 ready），
    // 而 `VITE_AI_PLANNING_API_ENABLED=false` 保证一个 ai-planning 请求都不会发。
    const previewFrontend = await startFrontend({
      proxyTarget: liveBackend.baseUrl,
      env: PREVIEW_FRONTEND_ENV,
      name: 'frontend-preview',
    })
    services.push(previewFrontend)

    // --- 组 5：deadBackend（后端不可用：代理指向未监听端口）---
    const deadPort = await freePort()
    const deadBackendFrontend = await startFrontend({
      proxyTarget: `http://127.0.0.1:${deadPort}`,
      env: LIVE_FRONTEND_ENV,
      name: 'frontend-dead-backend',
    })
    services.push(deadBackendFrontend)

    process.stdout.write(`live 后端        : ${liveBackend.baseUrl}\n`)
    process.stdout.write(`live 前端        : ${liveFrontend.baseUrl}\n`)
    process.stdout.write(`短 TTL 前端      : ${shortTtlFrontend.baseUrl}\n`)
    process.stdout.write(`未启用档前端     : ${disabledFrontend.baseUrl}（后端 ${disabledBackend.baseUrl}）\n`)
    process.stdout.write(`预览档前端       : ${previewFrontend.baseUrl}（demo 来自 ${liveBackend.baseUrl}）\n`)
    process.stdout.write(`后端不监听端口   : ${deadPort}\n\n`)

    browser = await launchBrowser({ headless: !headed })
    const context = { browser }

    const groups = [
      ['P0 主流程（live）', liveBaselineCases({ baseUrl: liveFrontend.baseUrl })],
      ['联合验收：规则解释入口与面板', explanationCases({ baseUrl: liveFrontend.baseUrl })],
      ['联合验收：UX 结构（缺口摘要 / 五阶段 / 支撑数据）', uxStructureCases({ baseUrl: liveFrontend.baseUrl })],
      ['P1 响应式布局', responsiveCases({ baseUrl: liveFrontend.baseUrl })],
      ['P1 异常与并发', resilienceCases({ baseUrl: liveFrontend.baseUrl })],
      ['未启用档（disabled）', disabledCases({ baseUrl: disabledFrontend.baseUrl })],
      ['预览档（preview）', previewCases({ baseUrl: previewFrontend.baseUrl })],
    ]

    for (const [title, cases] of groups) {
      process.stdout.write(`\n--- ${title} ---\n`)
      const decorated = cases.map((item) => ({
        ...item,
        run: () =>
          item.run({
            ...context,
            shortTtl: { frontend: shortTtlFrontend, backend: shortTtlBackend },
            deadBackendFrontend,
          }),
      }))
      const groupResults = await runCases(decorated, { filter })
      results.push(...groupResults)
    }
  } finally {
    if (browser) {
      await browser.close().catch(() => {})
    }
    await stopAll(services)
  }

  const passed = results.filter((item) => item.status === 'passed').length
  const skipped = results.filter((item) => item.status === 'skipped').length
  const failed = results.filter((item) => item.status !== 'passed' && item.status !== 'skipped').length
  const summary = {
    startedAt: startedAt.toISOString(),
    finishedAt: new Date().toISOString(),
    browser: 'Microsoft Edge（playwright-core channel=msedge）',
    headed,
    python,
    casesModule: casesArg,
    envFilesDetected: envFiles,
    total: results.length,
    passed,
    failed,
    skipped,
  }

  await writeJson(join(ARTIFACT_DIR, `browser-e2e-results${casesArg === 'cases.mjs' ? '' : `-${casesArg.replace(/\.mjs$/, '')}`}.json`), {
    summary,
    results,
  })
  process.stdout.write(
    `\n=== 结果：${passed} passed / ${failed} failed / ${skipped} skipped / 共 ${results.length} ===\n`,
  )
  process.stdout.write(`JSON: tools/browser-e2e/artifacts/browser-e2e-results.json\n`)
  if (failed > 0) {
    process.exitCode = 1
  }
}

main().catch((error) => {
  process.stderr.write(`运行器异常：${error.stack ?? error.message}\n`)
  process.exitCode = 2
})
