# 学航·转衔｜CI 方案（可审查，默认最小权限）

> 状态：**新增但未在真实 GitHub Actions 上运行过** —— 本仓库此前**没有任何 CI**
> （`.github/` 不存在）。本文件给出一个**可审查、默认只读**的最小工作流；
> 是否能通过取决于 GitHub 侧 Runner 环境，**尚未在云端验证**（见 §4）。

---

## 1. 设计原则（与任务书要求逐条对应）

| 要求 | 本方案的做法 |
| --- | --- |
| 不在不可信 PR 环境中执行具有写权限或生产密钥的任务 | 顶层 `permissions: contents: read`；⛔ 不用 `pull_request_target`；⛔ 不注入任何 secret |
| 不向 Fork PR 暴露密钥 | 工作流里**没有任何** `secrets.*` 引用；后端测试默认 `AI_PLANNING_ENABLED=false` |
| 不允许安全扫描自动修改依赖 | `npm audit` **只报告**：`--audit-level=high` 非零退出即失败；⛔ 不运行 `npm audit fix`，⛔ 不自动提交 |
| 不未经审批启用高权限自动合并 | ⛔ 无 auto-merge、⛔ 无 `gh pr merge`、⛔ 无 dependabot 自动合并配置 |
| 可审查 | 单文件，步骤全部是标准命令；无第三方 Action（只用 `actions/checkout` 与 `actions/setup-*`） |

**额外边界**：

- ⛔ 不在 CI 里跑浏览器 E2E（需要下载浏览器 / 复用 Runner 上的 Edge，成本与稳定性都不可控）；
  浏览器 E2E 仍是**本地受控步骤**（见 `docs/final_upgrade/DEMO_ACCEPTANCE_RUNBOOK.md`）。
- ⛔ 不在 CI 里访问任何学校系统、真实教务数据或真实模型。
- `PYTHONUTF8=1` 是硬性要求（Windows/GBK 环境；Linux 上无副作用）。

---

## 2. 工作流内容

文件：`.github/workflows/ci.yml`

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main, feature/final-upgrade]

permissions:
  contents: read

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -r requirements.txt
      - run: python -m pytest -q
        env:
          PYTHONUTF8: '1'

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '24'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npx vitest run
      - run: npx vue-tsc --noEmit
      - run: npm run build

  dependencies:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '24'
      - run: npm ci
      - name: 依赖审计（只报告，不自动修复）
        run: npm audit --audit-level=high
```

---

## 3. 为什么"依赖审计"这一步不会自动改依赖

`npm audit` 是**只读**命令：它查询 advisory 数据库并打印结果，
⛔ 不写 `package.json`、⛔ 不写 `package-lock.json`、⛔ 不安装任何东西。
只有 `npm audit fix` / `npm audit fix --force` 才会改依赖，而这两个命令
**没有出现在工作流里**（任务书明确禁止 `--force`，本方案连非 force 版也不放进 CI，
以免"扫描器自动改依赖"）。

修复依赖的动作始终是**人工发起、单独提交、单独评审**。

---

## 4. 未验证事项（如实声明）

| 项 | 状态 |
| --- | --- |
| 该工作流是否能在 GitHub 侧成功运行 | **NOT VERIFIED**（本地无 GitHub Runner，仓库此前无 CI 历史） |
| `backend/requirements.txt` 在 Linux + Python 3.12 下是否可安装 | **NOT VERIFIED**（本项目一直在 Windows + Python 3.14 上开发） |
| 后端 2 项已知 Windows 平台差异失败在 Linux 上是否消失 | **UNVERIFIED**（预期消失，因为二者都是 Windows/Python 3.14 语义差异） |
| `npm ci` 在 Linux 上的 `esbuild` postinstall | **UNVERIFIED**（本机 npm 已提示 esbuild 有 install script） |

**建议**：合并该工作流后，先只让 `frontend` 与 `dependencies` 两个 job 生效
（后端 job 用 `continue-on-error: false` 但先观察一次），确认稳定后再作为合并门槛。

---

## 5. 本地等价命令（无需 CI 也能复现）

```powershell
# 后端（Windows；PYTHONUTF8 必设）
cd backend; $env:PYTHONUTF8='1'; python -m pytest -q

# 前端
cd frontend
npm ci
npx vitest run
npx vue-tsc --noEmit
npm run build

# 依赖审计（只报告）
npm audit --audit-level=high
```
