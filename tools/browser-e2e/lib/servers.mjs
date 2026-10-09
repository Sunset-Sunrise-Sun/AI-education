/**
 * 本地服务编排：真实 FastAPI（QA 注入式测试模型）+ Vite 前端（多档环境）。
 *
 * 三条硬边界：
 * 1. ⛔ 不修改任何生产代码或环境变量清单：后端用 `backend/tests/qa_browser_e2e/qa_app.py`
 *    作为**测试专用** ASGI 入口，注入方式与既有后端测试一致（`app.dependency_overrides`）；
 * 2. ⛔ 不把测试替身说成真实模型：`/status` 会返回 `live_model_available=false`，
 *    E2E 断言里明确要求 `generator_kind=test_double`；
 * 3. ✅ 前端档位只通过 `VITE_*` 进程环境给出，不写入仓库的 `.env*` 文件。
 *
 * ⚠️ 已知环境限制：DSH 沙箱下 Node 的 `child_process.spawn` 若使用 **piped** stdio
 * 会因命名管道限制失败。因此这里统一用 `stdio: 'ignore'`，
 * 日志改为重定向到 `tools/browser-e2e/artifacts/logs/*.log`。
 */

import { spawn, spawnSync } from 'node:child_process'
import { closeSync, mkdirSync, openSync, readFileSync } from 'node:fs'
import { mkdir } from 'node:fs/promises'
import { createServer } from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const LIB_DIR = dirname(fileURLToPath(import.meta.url))
/** `tools/browser-e2e`（本套件的根，含 cases / dispatchers / package.json）。 */
export const E2E_DIR = join(LIB_DIR, '..')
export const REPO_ROOT = join(E2E_DIR, '..', '..')
export const LOG_DIR = join(E2E_DIR, 'artifacts', 'logs')
export const DISPATCHER = join(E2E_DIR, 'dispatchers', 'stdio_inherit.mjs')

/** 找一个空闲端口（避免固定端口在并发/残留进程下冲突）。 */
export async function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}

/**
 * 打开一个日志文件描述符。
 *
 * ⚠️ 必须传 **fd 数字**（而不是 WriteStream 对象）给 `stdio`：
 * Node 的 `child_process` 只接受 Stream 实例，而流对象在沙箱下不可用，
 * fd 数字同时满足"子进程输出不经过命名管道"与"日志落盘"两个要求。
 */
function openLogFd(name) {
  mkdirSync(LOG_DIR, { recursive: true })
  return openSync(join(LOG_DIR, `${name}.log`), 'a')
}

/** 包装器把真实子进程 PID 写进日志文件时使用的标记。 */
const PID_PREFIX = '__E2E_CHILD_PID__'

/**
 * 从日志文件里解析包装器汇报的真实子进程 PID。
 *
 * 为什么需要：Windows 上 `shell: true` 会多出 `cmd.exe` → `node/python` 两层，
 * 只 kill 包装器会留下孤儿 Vite / uvicorn 常驻（实测累积上百个，拖垮后续运行）。
 */
function readChildPid(name) {
  try {
    const text = readFileSync(join(LOG_DIR, `${name}.log`), 'utf-8')
    const matches = [...text.matchAll(new RegExp(`${PID_PREFIX}\\s+(\\d+)`, 'g'))]
    if (matches.length === 0) {
      return null
    }
    return Number.parseInt(matches[matches.length - 1][1], 10)
  } catch {
    return null
  }
}

/**
 * 停掉一个服务：**整棵进程树**。
 *
 * Windows 用 `taskkill /T /F`（带走 cmd.exe 与真正的服务进程），
 * 其它平台退回信号。
 */
function killTree(pid, name) {
  if (!pid) {
    return
  }
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    })
    return
  }
  try {
    process.kill(pid, 'SIGTERM')
  } catch {
    // 已经退出
  }
}

/**
 * 启动真实后端（uvicorn + QA 注入式 app）。返回 { process, baseUrl, stop }。
 */
export async function startBackend({
  python = process.env.QA_PYTHON ?? 'python',
  port = null,
  env = {},
  name = 'backend',
} = {}) {
  const resolvedPort = port ?? (await freePort())
  const logFd = openLogFd(name)
  const child = spawn(
    process.execPath,
    [
      DISPATCHER,
      join(REPO_ROOT, 'backend'),
      python,
      '-m', 'uvicorn', 'tests.qa_browser_e2e.qa_app:app',
      '--host', '127.0.0.1', '--port', String(resolvedPort), '--log-level', 'warning',
      `--pid-prefix=${PID_PREFIX}`,
    ],
    {
      cwd: join(REPO_ROOT, 'backend'),
      env: {
        ...process.env,
        PYTHONUTF8: '1',
        PYTHONPATH: join(REPO_ROOT, 'backend'),
        ...env,
      },
      stdio: ['ignore', logFd, logFd],
      windowsHide: true,
    },
  )
  const baseUrl = `http://127.0.0.1:${resolvedPort}`
  await waitForHttp(`${baseUrl}/health`)
  return {
    process: child,
    baseUrl,
    port: resolvedPort,
    stop: async () => {
      killTree(child.pid, name)
      killTree(readChildPid(name), name)
      closeSync(logFd)
    },
  }
}

async function waitForHttp(url, { timeoutMs = 60000, intervalMs = 250 } = {}) {
  const deadline = Date.now() + timeoutMs
  let lastError = 'unknown'
  while (Date.now() < deadline) {
    try {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 3000)
      const response = await fetch(url, { signal: controller.signal })
      clearTimeout(timer)
      if (response.status < 500) {
        return true
      }
      lastError = `HTTP ${response.status}`
    } catch (error) {
      lastError = error.message
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  throw new Error(`等待 ${url} 就绪超时（最后错误：${lastError}）`)
}


/**
 * 启动 Vite 开发服务器。`env` 里的 `VITE_*` 决定前端档位。
 */
export async function startFrontend({
  port = null,
  proxyTarget,
  env = {},
  name = 'frontend',
  npm = process.env.QA_NPM ?? 'npm',
} = {}) {
  const resolvedPort = port ?? (await freePort())
  const logFd = openLogFd(name)
  const child = spawn(
    process.execPath,
    [
      DISPATCHER,
      join(REPO_ROOT, 'frontend'),
      npm,
      'run', 'dev', '--', '--port', String(resolvedPort), '--strictPort',
      `--pid-prefix=${PID_PREFIX}`,
    ],
    {
      cwd: join(REPO_ROOT, 'frontend'),
      env: {
        ...process.env,
        VITE_PROXY_TARGET: proxyTarget ?? 'http://127.0.0.1:9',
        ...env,
      },
      stdio: ['ignore', logFd, logFd],
      windowsHide: true,
    },
  )
  const baseUrl = `http://127.0.0.1:${resolvedPort}`
  await waitForHttp(`${baseUrl}/`)
  return {
    process: child,
    baseUrl,
    port: resolvedPort,
    stop: async () => {
      killTree(child.pid, name)
      killTree(readChildPid(name), name)
      closeSync(logFd)
    },
  }
}

/** 尽力停止一组服务（忽略已经退出的情况）。 */
export async function stopAll(services) {
  for (const service of services) {
    try {
      await service.stop()
    } catch {
      // 忽略停止失败：进程可能已经退出
    }
  }
}
