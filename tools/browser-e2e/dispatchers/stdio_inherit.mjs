/**
 * 服务启动包装器：把 stdout/stderr **继承**给父进程的日志文件，并汇报子进程 PID。
 *
 * 为什么需要这一层（环境限制，不是设计偏好）：
 * DSH 沙箱下 `child_process.spawn` 的 `stdio` 只能用 `pipe` / `inherit` / `ignore`；
 * 传文件描述符会得到 `ENOENT`，传 Stream 对象会被判定为非法参数。
 * 但只传 `inherit` 又无法把日志分开落盘，所以这里多一层 Node 包装：
 *
 * ```text
 * runner --spawn--> dispatchers/stdio_inherit.mjs (stdio 继承给日志 fd)
 *                        └─ spawn 真实命令 (stdio: 'inherit')
 * ```
 *
 * ## 子进程 PID 汇报（重要）
 *
 * 在 Windows 上 `shell: true` 会先起 `cmd.exe`，再由它起真正的 `node` / `python`。
 * runner 直接 `kill()` 包装器进程**不会**带走这一串孙进程，Vite 与 uvicorn 会变成
 * 孤儿常驻（真实踩到过：连续几轮后累积上百个残留监听进程，把后续运行拖到超时）。
 *
 * 所以包装器在子进程起来后，把 `<prefix> <pid>` 写到 stderr（日志文件里），
 * runner 解析出 PID 后用 `taskkill /PID <pid> /T /F` 整棵树带走。
 * `--pid-prefix` 由 runner 传入，默认 `__E2E_CHILD_PID__`。
 *
 * 用法：`node dispatchers/stdio_inherit.mjs <cwd> <program> [args...] [--pid-prefix=X]`
 */

import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'

const rawArgs = process.argv.slice(2)
let pidPrefix = '__E2E_CHILD_PID__'
const positional = []
for (const arg of rawArgs) {
  if (arg.startsWith('--pid-prefix=')) {
    pidPrefix = arg.slice('--pid-prefix='.length)
  } else {
    positional.push(arg)
  }
}

const [cwd, program, ...rest] = positional

if (!cwd || !program) {
  process.stderr.write('用法：node dispatchers/stdio_inherit.mjs <cwd> <program> [args...]\n')
  process.exit(2)
}

if (!existsSync(cwd)) {
  process.stderr.write(`工作目录不存在：${cwd}\n`)
  process.exit(2)
}

const child = spawn(program, rest, {
  cwd,
  stdio: 'inherit',
  windowsHide: true,
  shell: process.platform === 'win32',
})

child.on('error', (error) => {
  process.stderr.write(`启动子进程失败：${program} → ${error.message}\n`)
  process.exit(3)
})

// 把真实子进程 PID 写进 stderr（= runner 的日志文件），供 runner 精确清场。
if (child.pid) {
  process.stderr.write(`${pidPrefix} ${child.pid}\n`)
}

child.on('exit', (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0))
})

/** 整棵进程树退出（Windows 用 taskkill /T，其它平台杀进程组）。 */
function killTree(signal) {
  if (process.platform === 'win32' && child.pid) {
    spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    })
    return
  }
  try {
    process.kill(-child.pid, signal)
  } catch {
    try {
      child.kill(signal)
    } catch {
      // 忽略：子进程可能已退出
    }
  }
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    killTree(signal)
    process.exit(0)
  })
}

// 父进程消失（含被强杀）时也清理，避免留下孤儿服务。
process.on('disconnect', () => {
  killTree('SIGTERM')
  process.exit(0)
})
