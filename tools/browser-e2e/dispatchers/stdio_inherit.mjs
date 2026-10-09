/**
 * 服务启动包装器：把 stdout/stderr **继承**给父进程的日志文件。
 *
 * 为什么需要这一层（环境限制，不是设计偏好）：
 * DSH 沙箱下 `child_process.spawn` 的 `stdio` 只能用 `pipe` / `inherit` / `ignore`；
 * 传文件描述符会得到 `ENOENT`，传 Stream 对象会被判定为非法参数。
 * 但只传 `inherit` 又无法把日志分开落盘，所以这里多一层 Node 包装：
 *
 * ```text
 * runner --spawn--> wrappers/server.mjs (stdio 继承给日志 fd)
 *                        └─ spawn 真实命令 (stdio: 'inherit')
 * ```
 *
 * 用法：`node dispatchers/stdio_inherit.mjs <cwd> <program> [args...]`
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'

const [cwd, program, ...rest] = process.argv.slice(2)

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

child.on('exit', (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0))
})

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    try {
      child.kill(signal)
    } catch {
      // 忽略：子进程可能已退出
    }
  })
}
