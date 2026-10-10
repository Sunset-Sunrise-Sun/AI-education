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

> 上面是**要点摘录**；真正生效的是 `.github/workflows/ci.yml`（含 `name:` 步骤标签）。
> 后端安装命令与实际文件一致，都是 `python -m pip install -r requirements.txt`
> —— 也正是那条曾经缺 `python-docx` 的命令（见 §4.1）。

---

## 3. 为什么"依赖审计"这一步不会自动改依赖

`npm audit` 是**只读**命令：它查询 advisory 数据库并打印结果，
⛔ 不写 `package.json`、⛔ 不写 `package-lock.json`、⛔ 不安装任何东西。
只有 `npm audit fix` / `npm audit fix --force` 才会改依赖，而这两个命令
**没有出现在工作流里**（任务书明确禁止 `--force`，本方案连非 force 版也不放进 CI，
以免"扫描器自动改依赖"）。

修复依赖的动作始终是**人工发起、单独提交、单独评审**。

---

## 4. 实际运行情况（已修正：本节原为"尚未运行"）

### 4.1 第 1 次运行 —— 后端 Job 失败（已修复）

| 项 | 值 |
| --- | --- |
| Run | [#37948975531](https://github.com/Sunset-Sunrise-Sun/AI-education/actions/runs/37948975531) |
| 触发提交 | `af6a5cb` |
| Frontend tests / typecheck / build | ✅ **SUCCESS** |
| Dependency audit（只报告） | ✅ **SUCCESS** |
| Backend pytest | ❌ **FAILURE** |

**根因**（从该 Run 的后端 Job 日志逐行确认）：

```text
ERROR collecting tests/test_curriculum_elective_group.py
    from docx import Document
E   ModuleNotFoundError: No module named 'docx'
ERROR collecting tests/test_curriculum_positional_docx.py
    from docx import Document
E   ModuleNotFoundError: No module named 'docx'
!!! Interrupted: 2 errors during collection !!!
Process completed with exit code 2.
```

**性质**：这是**依赖声明缺失**，不是测试本身的问题。
`python-docx` 只装在我的开发机上（未进 `requirements.txt`），
所以 Windows 本地一直绿、干净的 Linux Runner 一装就缺。

**判定与修复**：`python-docx` 属**测试依赖**（判定依据见 `backend/requirements.txt`
中新增的注释：`app/curriculum/docx_reader.py` 用标准库 `zipfile` + `ElementTree`
直接读 OOXML，**不 import docx**；只有 2 个测试文件用它来**构造** .docx）。
按本文件顶部"一条 `pip install -r requirements.txt` 就能跑测试"的既有约定，
把声明加进同一文件的**测试依赖段**，而**不是**新建 `requirements-dev.txt`
（那会同时失效 README / RUNBOOK / CI 三处既有安装命令）。

**⛔ 未做的事**：没有跳过这两个测试文件，没有给后端 Job 加 `continue-on-error`，
没有 `xfail` 标记。

### 4.2 修复后的本地等价验证（在 CI 之前先自证）

新建**空白虚拟环境**，只安装 `requirements.txt`，再跑全量 pytest：

```text
venv create exit=0
pip install -r requirements.txt exit=0
python-docx 1.2.0（已随 requirements.txt 装上）
pytest totals: 3188 passed / 2 failed / 2 skipped  ← 与开发机基线完全一致
```

⇒ 说明"只装 `requirements.txt`"已经足够收集并运行**全部**测试，
两个 `test_curriculum_*` 文件不再缺失依赖。

### 4.3 第 2 次运行（修复后）—— 三个 Job 全部通过

| 项 | 值 |
| --- | --- |
| Run | [#38006322656](https://github.com/Sunset-Sunrise-Sun/AI-education/actions/runs/38006322656) |
| 触发提交 | **`decc84b`**（`fix(backend): declare python-docx as a test dependency …`） |
| 工作流结论 | ✅ **success** |
| Backend pytest | ✅ **success**（Job id `114075845916`；步骤级 checkout / setup-python / 安装依赖 / pytest 全部 success） |
| Frontend tests / typecheck / build | ✅ **success**（Job id `114075845865`） |
| Dependency audit（只报告） | ✅ **success**（Job id `114075845748`） |

**后端 Job 的关键日志证据**：

```text
Collecting python-docx>=1.1 (from -r requirements.txt (line 37))      ← 修复生效
Collecting lxml>=3.1.0 (from python-docx>=1.1->-r requirements.txt (line 37))
Installing collected packages: … python-docx …
Successfully installed … python-docx-1.2.0 …
（pytest 进度输出到 100%）
=============================== warnings summary ===============================
（随后直接进入 Post job cleanup —— 没有 failures / short test summary 段）
```

- 日志里**没有** `ModuleNotFoundError`，也**没有** `FAILED` / `short test summary` 段
  ⇒ 依赖缺失已解决，且没有任何测试失败；
- 全程**没有** `SKIPPED` / `xfail` / `continue-on-error` 标记。

**关于测试计数（如实说明）**：GitHub 的 Job 日志接口在本机读取时**按尾部截断**
（只返回最后一段，32977 字符），`===== N passed in Xs =====` 那一行**不在可见日志里**，
因此我**没有**取到 Linux 上的准确数字。可确证的是：
**收集成功、跑到 100%、无失败、Job 通过**。
作为对照，同一条命令在 Windows + Python 3.14 上实测为
**3188 passed / 2 failed / 2 skipped**（那 2 项失败是 Windows/Python 3.14 语义差异，
在 Linux 上不出现，与"日志中无失败"一致）。

### 4.4 仍未验证（如实声明）

| 项 | 状态 |
| --- | --- |
| Linux 上的准确测试计数 | **未取到**（日志被截断，见 §4.3） |
| Windows 上是否会出现 Linux 没有的失败 | 已实测：Windows 3188 / 2 / 2，与基线一致 |
| `npm ci` 在 Linux 上的 `esbuild` postinstall | ✅ 已被第 2 次运行覆盖（前端 Job success） |
| 两个 Job 的 Node 20 弃用告警 | 存在但**不影响结论**（Actions 已自动落到 Node 24；Job success） |

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
