# 比赛现场恢复指南（DEMO RECOVERY）

> **用途**：比赛 / 现场演示过程中**已经出问题**时，按本文逐条排查并当场恢复。
> 本文与 `docs/e2e/DEMO_RUNBOOK.md` 分工：Runbook 管「赛前按顺序启动 + 检查点」，
> 本文管「启动之后坏了怎么办」。
>
> **最高原则（任何场景都不得破例）**：
>
> ```text
> 如实显示错误 → 不生成替代结果 → 不把 Mock 冒充 Real → 不假装成功
> ```
>
> ⛔ 本文件不声明 Real E2E 已完成。当前正式 Real E2E 证据等级仍是 **LEVEL 0**。
> ⛔ 本文件不包含任何真实学生数据、成绩单、cookie / token / 凭据、本地真实 artifact 路径。

---

## 0. 怎么用这份文档

**四步查法**（每一条故障都按同一结构写）：

```text
① 现象      界面上 / 终端上**实际**看到什么（错误标题、状态码、错误码、终端报错形状）
② 判断依据  凭什么确认就是这一个原因（而不是别的原因）
③ 处理步骤  可以直接执行的命令（标明是 PowerShell 还是 bash）
④ 演示如何继续  修好 / 修不好时，对评委**如实**怎么说
   + 不要做什么  明确列出禁止的操作与禁止的说法
```

**现场决策顺序（前 4 步都通过才需要往下走）**：

```text
页面打不开？      → §3
页面打开了没数据？ → §1
数据有了但不能提交 Real？ → §6（多半是**预期行为**，不是故障）
```

⚠️ 现场时间紧张时，直接跳到文末 **§13 最小可信演示路径（2 分钟兜底）**。

---

## 1. 两种演示模式与运行时契约（恢复判断的事实基础）

### 1.1 两种模式

| | **模式 1：演示快照回放**（默认、干净检出即可运行） | **模式 2：真实规划链路** |
|---|---|---|
| 前置条件 | 无。不需要任何环境变量 | ① 操作者本机**已批准**的真实 Case A manifest（`APP_CASE_A_CURRICULUM_CASE_PATH`）② **已验收**的整学期 Course Data SQLite 库 |
| 基础数据（培养要求评估 / 教学班 / 偏好） | 来自 `GET /api/v1/mock/demo`（仓库内 `mock_data/*.json`） | 同上，**仍来自 Mock Demo** |
| 规划结果 | 同样来自 `GET /api/v1/mock/demo` 的 `plan_result` | `POST /api/v1/plan` 走真实链路：Curriculum Case A → Diff → MakeupTask → Planner → Path Repair → PlanResult |
| 必须标注 | **演示数据 / Mock** | 规划结果标 **Real**；教学班输入是**明确标注的 Synthetic 演示快照** |
| 数据等级声明 | Mock | 真实链路 + Synthetic 教学班快照；正式 Real E2E 证据等级仍为 **LEVEL 0** |

⚠️ **真实 Case A manifest 不在 Git 中**，它是模式 2 的**显式前置条件**：没有它就只能走模式 1。
⚠️ 模式 2 的教学班输入是**明确标注的 Synthetic 演示快照**，⛔ 不等于真实教务在线数据。

### 1.2 运行时环境变量（**恰好 5 个**）

```text
APP_REAL_CASE_A_ENABLED=1                      # 开关：只认 "1"；未设置或 "0" = 关闭；其它值 = 配置非法
APP_CASE_A_CURRICULUM_CASE_PATH=<已批准的真实 Case A manifest 本地路径>
APP_COURSE_DATA_SQLITE_PATH=<已验收的 Course Data SQLite 库本地路径>
APP_COURSE_DATA_SEMESTER=<该 acceptance 绑定的学期，例如 2026-1>
APP_COURSE_DATA_ACCEPTANCE_SHA256=<full-semester acceptance 的 manifest SHA-256，64 位十六进制，大小写均可>
```

⛔ 不存在其它 runtime 变量，也不存在 campus / 单 bundle 的降级开关。

前端变量（**不属于**上面 5 个）：

```text
VITE_PLAN_API_ENABLED=true        # 只有它控制 Real 提交按钮是否可用；不设置 = 按钮不可用（默认，推荐）
VITE_PROXY_TARGET=http://127.0.0.1:8000   # 可选；默认就是它
VITE_API_BASE_URL=                # 留空 = 走同源 Vite 代理；一旦填值浏览器直连后端（本仓库未开 CORS）
```

### 1.3 fail-closed 语义（**这是设计，不是崩溃**）

```text
任何一步未就绪（开关没开 / case 不可用 / 库或 acceptance 不可用 / semester 不匹配）
        ⇒ POST /api/v1/plan 返回 503，响应体 {"detail": {"error": "real_pipeline_not_configured", ...}}
        ⇒ ⛔ 不回退到 Mock，⛔ 不返回空列表，⛔ 不返回任何替代结果

程序缺陷（不是领域 / 配置失败）
        ⇒ 500，⛔ 不会伪装成 503

Mock 通道 GET /api/v1/mock/demo
        ⇒ 始终独立可用，响应带 X-Data-Source: mock
```

### 1.4 启动方式（统一口径）

```powershell
# 后端（工作目录 backend/）
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 前端（工作目录 frontend/）
cd frontend
npm install          # 首次
npm run dev          # Vite 默认 127.0.0.1:5173
```

```bash
# bash（macOS / Linux / Git Bash）等价命令
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

- 页面必须通过 **Vite 地址**打开（`http://127.0.0.1:5173`，构建预览是 `:4173`）；
  ⛔ 不要直接双击 `dist/index.html`。
- Vite 默认把 `/api` 代理到 `http://127.0.0.1:8000`。

### 1.5 改环境变量后必须重启后端（本文多处依赖这一条）

```text
python -m uvicorn ... --reload 只在**源码变化**时重载进程；
环境变量属于**进程环境**，改完必须 Ctrl+C 重启后端才生效。
```

---

## 2. 一分钟速查表

| 现象（界面 / 终端） | 判断 | 去哪里 |
|---|---|---|
| 页面区块标题「Demo 数据加载失败」+「后端接口连接异常」 | 后端没起来 / 端口不对 / 不是从 Vite 打开 | §3 |
| `uvicorn` 报 `[Errno 10048]` / `error while attempting to bind` | 8000 被占用 | §4 |
| `vite` 提示端口被占用后换成别的端口 | 5173 被占用 | §4 |
| `npm run dev` 没反应 / 浏览器 `ERR_CONNECTION_REFUSED` | 前端进程没起来 | §5 |
| `npm install` 报 `ERESOLVE` / `ETIMEDOUT` | 依赖未装 / 网络问题 | §6 |
| `vue-tsc` 报 `error TS####` 后 `npm run build` 退出 | 类型检查失败，构建不会产出 | §6 |
| 页面能开，Network 里 `/api/v1/mock/demo` 是 404 | 代理没生效 / 代理目标错 | §7 |
| 点 Real 提交：错误区「真实规划运行时尚未完成装配」+ 503 `real_pipeline_not_configured` | **预期的 fail-closed**，不是崩溃 | §8 |
| 点 Real 提交：HTTP 500 | 程序缺陷，**不会**被伪装成 503 | §9 |
| 五个变量有的对有的错、上次演示的残留值还在 | 环境变量配错 / 残留 | §10 |
| 页面还停在上一轮的 Real 结果 | 前端内存状态没清 | §11 |
| 找不到「教学班数据：演示快照（Synthetic）」标签 | 披露面缺失，**必须当场如实说明** | §12 |
| 后端中途重启过 | 每请求重新装配；需重新提交规划 | §12.2 |

---

## 3. 后端未启动（页面「Demo 数据加载失败 / 后端接口连接异常」）

### ① 现象

- 页面第 1 个状态卡标题：**「Demo 数据加载失败」**；
- 副标题：「页面不会自动生成替代数据，也严禁展示未经后端正式响应的内容。」；
- 卡内正文：**「后端接口连接异常」**，下面一行详细消息形如
  **「无法连接后端（请求地址：/api/v1/mock/demo）。请确认 FastAPI 已在 http://127.0.0.1:8000 启动，并且前端是通过 npm run dev / npm run preview 打开的。」**；
- 底部有「🔄 重新尝试连接」按钮；顶部「后端数据源标头」显示 **`等待连接`**。

⚠️ 页面**不会**在旁边自己编一份数据出来 —— 这是设计红线，不是缺陷。

### ② 判断依据

```powershell
# 后端是否活着（应返回 200 + {"status":"ok", ...}）
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/health
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
```

- 返回 `000` / 连接被拒 → 后端确实没起来（或不在 8000）；
- 返回 `200` → 后端活着，问题在**前端侧**：多半不是通过 Vite 地址打开的页面（见 §7）；
- 浏览器 Console / Network 面板里该请求是 `Failed to fetch` / `net::ERR_CONNECTION_REFUSED` → 请求根本没到后端。

### ③ 处理步骤

```powershell
# 1) 另开一个终端启动后端（必须在 backend/ 目录下）
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 2) 健康检查
curl.exe -s http://127.0.0.1:8000/health

# 3) Mock 通道自检（必须 200 且带 X-Data-Source: mock）
curl.exe -i -s http://127.0.0.1:8000/api/v1/mock/demo | Select-String -Pattern "HTTP/|X-Data-Source"
```

```bash
# bash 等价
cd backend && python -m uvicorn app.main:app --reload --port 8000
curl -s http://127.0.0.1:8000/health
curl -i -s http://127.0.0.1:8000/api/v1/mock/demo | head -20
```

- 后端确认 OK 后，回到页面点「🔄 重新尝试连接」（不需要刷新页面）；
- 若后端启动时**直接退出**：这是有意的 Mock 数据自检失败 —— 后端启动时按公共 JSON Schema 校验 Mock 数据，坏数据不会带着去演示。此时不要改数据文件，改用**干净检出**（模式 1）继续。

### ④ 演示如何继续

- 后端起来后正常继续：页面会显示 Mock 演示数据，规划结果来源为 **Mock**。
- 若暂时起不来，对评委可以照实说：
  > 「后端本地服务当前没有起来，页面已经明确显示『后端接口连接异常』，
  > 而且它不会自己编一份数据顶上。我先启动后端，再点『重新尝试连接』。」

### 不要做什么

- ⛔ 不要在前端手工伪造 / 硬编码一份数据让页面"看起来正常"；
- ⛔ 不要把「后端没起来」说成「网络波动」「马上就好」这类含糊话术；
- ⛔ 不要临时改后端路由或 Mock 数据去绕过启动自检。

---

## 4. 端口被占用（8000 或 5173）

### ① 现象

- 后端终端：`ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): 通常每个套接字地址…只允许使用一次。`
  （Linux / macOS 为 `[Errno 98] Address already in use`）。
- 前端终端：`Port 5173 is in use, trying another one...`，随后 `Local: http://127.0.0.1:5174/`。

⚠️ 前端换成 5174 **本身不影响代理**（`/api` 代理配置跟着服务走），
但如果页面/文档/口播里说的是 5173，就会出现"按文档打不开"的假象。

### ② 判断依据

```powershell
# 看谁占了端口（Windows）
netstat -ano | Select-String ":8000"
netstat -ano | Select-String ":5173"
Get-Process -Id <上面最后一列的 PID> | Select-Object Id, ProcessName, Path
```

```bash
# bash（macOS / Linux）
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

### ③ 处理步骤

```powershell
# 最安全：先优雅结束自己上一轮遗留的进程
Get-Process -Name python, node -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime
Stop-Process -Id <确认是自己启动的 PID>

# 确认是自己的残留进程后再强杀（不要动不认识的进程）
Stop-Process -Id <PID> -Force
```

```bash
# bash
kill <PID>          # 先优雅终止
kill -9 <PID>       # 仍不退时才强杀
```

⚠️ **换端口是最后手段，而且代价明确**：后端换端口后必须同步设置
`VITE_PROXY_TARGET`（默认是 `http://127.0.0.1:8000`），否则前端代理指向空气 → 页面报 §3 的错。

```powershell
# 只在无法释放 8000 时才这么做（前端目录下，设完必须重启前端）
$env:VITE_PROXY_TARGET="http://127.0.0.1:8001"
npm run dev
```

### ④ 演示如何继续

- 释放端口、按原端口重启后照常演示。
- 若确实换了端口：口播必须同步 ——
  > 「后端临时起在 8001，前端代理目标已经一并改成 8001，两边是一致的。」

### 不要做什么

- ⛔ 不要盲目 `taskkill /F /IM node.exe` / 杀所有 `python.exe`：可能杀掉别的评审工具或你自己的编辑器后端；
- ⛔ 不要"起两个后端"指望其中一个生效（先绑定的那个才是生效的，另一个必然失败）；
- ⛔ 不要在后端换端口后**忘记**改 `VITE_PROXY_TARGET`，那会把一个简单问题变成 §7 的疑难问题。

---

## 5. 前端未启动 / 页面打不开

### ① 现象

- 浏览器：`ERR_CONNECTION_REFUSED`、页面打不开；
- 或前端终端里 `npm run dev` 已经退出（`Ctrl+C`、终端被关、`vite` 报错后退出）；
- 或打开的是 `file:///.../dist/index.html`：页面**样式/脚本异常**或请求 `file:///api/...` 失败。

### ② 判断依据

```powershell
# 前端是否在监听（以及到底监听哪个端口）
netstat -ano | Select-String ":5173|:4173"
# 直接探一次
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:5173/
```

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/
```

- 200 → 前端在跑，改用这个地址打开；
- 000 → 前端没起，按 ③ 启动。

⚠️ Windows 上 `localhost` 可能被解析成 IPv6 `::1` 而连不上：本仓库 Vite 已**显式绑定 127.0.0.1**。
统一用 `http://127.0.0.1:5173`，⛔ 不要混用 `localhost`。

### ③ 处理步骤

```powershell
cd frontend
npm install      # 首次或依赖缺失时
npm run dev      # 看到 Local: http://127.0.0.1:5173/ 才算成功
```

```bash
cd frontend && npm install && npm run dev
```

演示（非开发）模式用构建产物：

```powershell
cd frontend
npm run build
npm run preview   # http://127.0.0.1:4173
```

### ④ 演示如何继续

- 打开正确的 Vite 地址后，页面会重新走一次 `GET /api/v1/mock/demo`，照常演示模式 1。
- 若前端一时起不来：让页面留在后端可用状态，先讲**后端契约**（`/health`、`/api/v1/mock/demo` 带 `X-Data-Source: mock`、`/api/v1/plan` 的 503 fail-closed 语义），再回到界面。

### 不要做什么

- ⛔ 不要双击 `dist/index.html` 当演示入口（同源代理不会生效）；
- ⛔ 不要用别的静态服务器顶替（`python -m http.server` 之类没有 `/api` 代理）；
- ⛔ 不要为了"能打开"而把 `VITE_API_BASE_URL` 填成后端地址：那会变成浏览器直连、跨域，本仓库后端未开 CORS。

---

## 6. 前端依赖未安装或构建失败（`npm install` / `npm run build` / TypeScript）

### ① 现象

- `npm run dev` 报 `Cannot find module 'vite'` / `'vue'`；
- `npm install` 报 `npm ERR! code ERESOLVE` / `ETIMEDOUT` / `ECONNRESET`；
- `npm run build`（先跑 `vue-tsc --noEmit`）报 `error TS2307: Cannot find module ...`、`error TS2339: Property ... does not exist on type ...` 后**非零退出**（vite build 不会执行）。

### ② 判断依据

```powershell
cd frontend
Test-Path node_modules         # False ⇒ 依赖没装
Get-ChildItem node_modules -ErrorAction SilentlyContinue | Measure-Object   # 数量很少 ⇒ 半装
npm run typecheck              # 单独复现类型错误：vue-tsc --noEmit
```

- 报错文件名与行号指向**本仓库源码**（`frontend/src/...`）→ 真实类型问题，不是环境问题；
- 报错指向 `node_modules` 缺失 / 版本 → 环境问题。

### ③ 处理步骤

```powershell
cd frontend

# 1) 先试标准安装
npm install

# 2) 如果报 ERESOLVE（peer 依赖冲突），**先读报错**再决定；不要顺手升级依赖
npm install --no-audit --no-fund

# 3) 严格复现类型错误（不改代码，只看结论）
npm run typecheck
```

```bash
cd frontend && npm install && npm run typecheck
```

⚠️ 现场若确实无法修好构建：
- **不要**为了跳过类型检查去删 `vue-tsc`、改 `package.json` 的 `build` 脚本或加 `// @ts-ignore` 掩盖错误；
- 用**开发模式**演示（`npm run dev`）：Vite dev server 不做完整类型检查，页面仍可运行；
- 在讲述中明确区分「演示可用」与「构建门禁未通过」，⛔ 不要声称构建通过。

### ④ 演示如何继续

- 开发模式跑起来就按模式 1 演示。
- 若被问到构建状态，如实回答：
  > 「构建脚本里含 TypeScript 类型检查，当前这一步没有通过，所以我用开发模式演示页面。
  > 这是一个未解决的问题，不影响我接下来演示的数据来源标注与 fail-closed 行为。」

### 不要做什么

- ⛔ 不要修改 `frontend/**` 任何文件来"让构建过"（本次演示准备不动前端源码）；
- ⛔ 不要删除 `tsconfig` / 关闭 `strict`；
- ⛔ 不要说「构建已经通过」（未验证就不说）。

---

## 7. 前端能开但接口 404 / 代理不生效

### ① 现象

- 页面进入「Demo 数据加载失败」，这次详细消息不是"无法连接"，而是形如
  **「后端返回 HTTP 404。这通常意味着后端服务异常，或接口路径发生了变化。」**；
- 或 Direct 打开 `dist/index.html` 时请求路径变成 `file:///api/v1/mock/demo`；
- Network 面板里 `/api/v1/mock/demo` 状态 404，而 `http://127.0.0.1:8000/api/v1/mock/demo` 直接访问是 200。

### ② 判断依据

```powershell
# A) 直接打后端（绕过代理）：应为 200 且带 X-Data-Source: mock
curl.exe -i -s http://127.0.0.1:8000/api/v1/mock/demo | Select-String -Pattern "HTTP/|X-Data-Source"

# B) 打前端同源路径（经 Vite 代理）：也应为 200
curl.exe -i -s http://127.0.0.1:5173/api/v1/mock/demo | Select-String -Pattern "HTTP/|X-Data-Source"

# C) 看 Vite 到底把 /api 代到哪（终端启动日志；或检查是否设置了代理目标）
Get-ChildItem Env:VITE_PROXY_TARGET -ErrorAction SilentlyContinue
```

- A 通、B 404 → 代理没生效：多半页面不是从 Vite 打开，或 `VITE_PROXY_TARGET` 指错了；
- A 也 404 → 后端路由问题（后端不是本仓库的应用，或版本不对）；
- `VITE_PROXY_TARGET` 指到了别的端口 / 别的服务 → 代理把请求发给了"另一个后端"。

### ③ 处理步骤

```powershell
# 1) 确认代理目标正确（默认即 8000，一般不需要设）
Remove-Item Env:VITE_PROXY_TARGET -ErrorAction SilentlyContinue
$env:VITE_PROXY_TARGET="http://127.0.0.1:8000"

# 2) 确认 VITE_API_BASE_URL 留空（留空 = 同源代理）
Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue

# 3) 改完环境变量必须重启前端
#    Ctrl+C 停掉 npm run dev，然后：
cd frontend
npm run dev

# 4) 用同一个地址打开页面（必须是 Vite 打印的 Local 地址）
```

```bash
# bash 等价
unset VITE_PROXY_TARGET VITE_API_BASE_URL
export VITE_PROXY_TARGET=http://127.0.0.1:8000
cd frontend && npm run dev
```

⚠️ `VITE_*` 是**构建期 / 启动期**读取的：改了 `.env.local` 或环境变量后必须重启 Vite，热更新不会重新读。

### ④ 演示如何继续

- 代理修好后页面自动恢复正常（点「🔄 重新尝试连接」）。
- 若一条命令就能证明代理与后端都正常，可以把它当成**加分项**讲：
  > 「前端不直连后端，页面只请求同源 `/api`，由 Vite 代理到 127.0.0.1:8000；
  > 这样本地联调不需要给后端开 CORS。刚才 404 是因为页面不是从这个 Vite 地址打开的。」

### 不要做什么

- ⛔ 不要把 `VITE_API_BASE_URL` 填成 `http://127.0.0.1:8000` 来"绕过代理"（会跨域，后端未开 CORS，问题只会换一种形式出现）；
- ⛔ 不要在后端加 CORS 中间件来救场（本次演示准备不改后端）；
- ⛔ 不要说"接口不存在"：`POST /api/v1/plan` 与 `GET /api/v1/mock/demo` 都是已实现的路由。

---

## 8. `POST /api/v1/plan` 返回 503 `real_pipeline_not_configured`

> **这一条最重要的是：它是预期的 fail-closed，不是崩溃，也不是"接口没写"。**

### ① 现象

界面（前端对 503 + `real_pipeline_not_configured` 有专门文案）：

- 错误区标题：**「真实规划运行时尚未完成装配」**；
- 提示：「真实 Curriculum / Course Data / Planner 尚未接入（后端返回 503 real_pipeline_not_configured）。当前页面可继续使用 Mock Demo；Real Planning 暂不可用，前端也不会自动回退到 Mock。」；
- 页面**仍然显示 Mock 规划结果**，且「规划结果」的来源标注仍是 **Mock**（没有变成 Real，也不会凭空多出一次 Mock 请求）。

终端：

```text
HTTP/1.1 503 Service Unavailable
{"detail":{"error":"real_pipeline_not_configured","message":"真实规划链路尚未配置。"}}
```

⚠️ 若后端中途发现 acceptance 失效，`message` 可能是
「真实规划链路当前不可用：Course Data acceptance 已失效或不再匹配。」——**错误码相同**。

### ② 判断依据

```powershell
# 复现一次（应看到 503 + real_pipeline_not_configured）
curl.exe -i -s -X POST http://127.0.0.1:8000/api/v1/plan `
  -H "Content-Type: application/json" `
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'

# 确认 Mock 通道仍然独立可用（这是判断"是不是整体崩了"的关键对照）
curl.exe -i -s http://127.0.0.1:8000/api/v1/mock/demo | Select-String -Pattern "HTTP/|X-Data-Source"
```

```bash
curl -i -s -X POST http://127.0.0.1:8000/api/v1/plan \
  -H 'Content-Type: application/json' \
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
curl -i -s http://127.0.0.1:8000/api/v1/mock/demo | head -20
```

**判定规则**：

- 503 + `real_pipeline_not_configured` + Mock 通道 200 → **预期的 fail-closed**（本条）；
- 5xx（非 503）→ 程序缺陷（见 §9）；
- 422 → 输入没通过校验（见下方"额外分支"）。

**五个变量缺哪个 / 哪个不对**（后端诊断码，按代码实际分支）：

| 情形 | 内部诊断码 | 典型操作者错误 |
|---|---|---|
| `APP_REAL_CASE_A_ENABLED` 未设置或 `0` | `runtime_disabled` | 忘了设，或上次演示后清掉了 |
| 开关值不是 `0` / `1`（如 `true` / `yes` / `01`） | `invalid_runtime_configuration` | 用 `true` 而不是 `1` |
| `APP_CASE_A_CURRICULUM_CASE_PATH` 缺失 | `curriculum_not_ready` | 没配 case 路径 |
| case 文件不存在 / 不可读 / 不是合法 case / `data_source` **不是 real** / 目标版本不是 Case A / scope 决策未获批准 | `curriculum_not_ready` | 拿的是 Mock case，或换过版本，或批准信息失效 |
| `APP_COURSE_DATA_SQLITE_PATH` / `APP_COURSE_DATA_SEMESTER` / `APP_COURSE_DATA_ACCEPTANCE_SHA256` 任一缺失 | `course_data_not_ready` | 只设了库路径，忘了学期或 digest |
| `APP_COURSE_DATA_ACCEPTANCE_SHA256` 形态非法（不是 64 位十六进制） | `invalid_runtime_configuration` | 填了 raw bundle digest / campus digest / 手工截断的串 |
| 库文件不存在 / 不是 Course Data 库 / 库里**没有**匹配的 `full_semester` acceptance / 计数不符 / 行被覆盖 | `course_data_not_ready` | 用了 campus-only 库，或 digest 与库里 acceptance 不一致 |
| 请求里的 `semester` 与 acceptance 绑定学期不一致 | `course_data_not_ready` | 前端学期输成了别的学期 |

⚠️ 这些诊断码**不会出现在 HTTP 响应里**（响应只有统一的 `real_pipeline_not_configured`）：
用下面的本地探针才能拿到原因码（在 `backend/` 目录、**用启动后端时的同一套环境变量**执行）：

```powershell
cd backend
python -c "from app.services.planning_runtime import inspect_planning_runtime as i; r=i(); print(r.reason, r.ready)"
# 期望 ready True；否则打印上面表格里的诊断码
```

```bash
cd backend && python -c "from app.services.planning_runtime import inspect_planning_runtime as i; r=i(); print(r.reason, r.ready)"
```

⚠️ 该探针只打印诊断码，不打印路径 / 配置取值 / 输入内容 —— 可以直接在评委面前跑。

### ③ 处理步骤

**分两种现场策略，二选一，都要明说。**

**策略 A（推荐，默认）：确认这是预期状态 → 回到模式 1，什么都不改。**

```powershell
# 不要设置任何 APP_* 变量；如果残留过，先清掉（见 §10）
Get-ChildItem Env:APP_REAL_CASE_A_ENABLED -ErrorAction SilentlyContinue
# 不设置 = Real 按钮不可用，页面明确解释原因
```

**策略 B：确实要跑模式 2（只有本机已批准的真实 Case A manifest + 已验收整学期库都齐了才做）**

```powershell
# 0) 先清干净，避免残留值混进来
Remove-Item Env:APP_REAL_CASE_A_ENABLED, Env:APP_CASE_A_CURRICULUM_CASE_PATH, `
  Env:APP_COURSE_DATA_SQLITE_PATH, Env:APP_COURSE_DATA_SEMESTER, `
  Env:APP_COURSE_DATA_ACCEPTANCE_SHA256 -ErrorAction SilentlyContinue

# 1) 用编排工具产出的 runtime env 文件承载这 5 个变量（文件由操作者本地生成，不入 Git）
Get-Content <本地目录>\runtime.env | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object {
  $name, $value = $_ -split '=', 2
  Set-Item -Path "Env:$name" -Value $value
}

# 2) 核对（只打印"有没有设置"，不回显路径内容）
Get-ChildItem Env:APP_ | Select-Object Name

# 3) 用同一套环境变量**重启**后端（环境变量属于进程环境，必须重启）
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 4) 本地探针：必须打印 ready True
python -c "from app.services.planning_runtime import inspect_planning_runtime as i; r=i(); print(r.reason, r.ready)"
```

```bash
# bash 等价（runtime.env 每行形如 NAME=value，可被 shell 直接 source）
set -a; . <本地目录>/runtime.env; set +a
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

**额外分支：422（不是 503）** ——说明请求本身没通过校验：

- 请求体**只允许** `semester` / `current_schedule` / `preference` 三个键，多余键会被拒；
- `semester` 不能是空白串；`current_schedule` 里每一项的 `data_source` 必须是 `real`（空数组合法）。
- 页面侧还有一道更早的门禁：**当前课表含 Mock 教学班时，一个请求都不会发出**，提示为
  「当前课表来源为 Mock 教学班，不能提交到 Real Planning。真实教学班接入前，请先清空当前课表中的 Mock 教学班。」
  ——这是**前端门禁**，不是后端 422，判断依据就是 Network 面板里**没有任何请求**。

### ④ 演示如何继续

**这是可以坦然展示、甚至是加分项的一段话术**（照实说，不要绕）：

> 「当前后端返回 503 `real_pipeline_not_configured`。这是我们**刻意设计的 fail-closed**：
> 真实链路需要本机已批准的真实 Case A manifest 与已验收的整学期 Course Data 库，
> 这两个都不在 Git 里，是显式前置条件。任何一步没就绪，`POST /api/v1/plan` 就明确拒绝，
> **不会**回退到 Mock，也**不会**给一个看起来成功的替代结果。
> 页面把这件事单独标出来了：规划结果仍然是 Mock，并且说明了原因。」

⚠️ 模式 2 若成功显示 Real 结果，口播必须同时说清两件事：
1. **规划结果**来自 `POST /api/v1/plan`（Real）；
2. **基础数据**（培养要求评估 / 教学班 / 偏好）**仍为 Mock 演示数据**；
   教学班输入是**明确标注的 Synthetic 演示快照**。

### 不要做什么

- ⛔ 不要把 503 说成"接口没写 / 后端崩了 / 网络问题"；
- ⛔ 不要用 Mock 的 `PlanResult` 去顶替 Real 结果，也不要手工把页面文案改成 Real；
- ⛔ 不要用 `APP_COURSE_DATA_ACCEPTANCE_SHA256` 填**其它** digest
  （raw campus bundle digest 或 campus acceptance digest 都不行）；
- ⛔ 不要用 campus-only 库"先跑起来"（只会得到同一个 503，且属于错误用法）；
- ⛔ 不要手工改库、删行、改 acceptance 记录来"让它过"。

---

## 9. 接口 500（程序缺陷）

### ① 现象

- 前端错误区标题：**「Real Planning 服务端错误」**；
- 状态码 **500**（或其它非 503 的 5xx）；
- 后端终端打印 Python 堆栈（`Traceback (most recent call last)` … 以异常类型和消息结尾）。

### ② 判断依据

```powershell
curl.exe -i -s -X POST http://127.0.0.1:8000/api/v1/plan `
  -H "Content-Type: application/json" `
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

- `HTTP/1.1 500` 且**没有** `real_pipeline_not_configured` → 程序缺陷；
- 后端终端同时出现堆栈 → 确认是内部错误。

**关键契约（必须记住，用来反驳误判）**：

```text
503 只给**显式领域 / 配置失败**（未装配、acceptance 失效等）；
与就绪性无关的内部错误（程序缺陷）必须是 500，⛔ 不会被伪装成 503。
```

前端也按这条分类：只有 `503 + real_pipeline_not_configured`（或 503 且响应体完全无法解析）
才显示"尚未完成装配"；503 但响应体明确给出其它原因时归为**服务端错误**。

### ③ 处理步骤

```powershell
# 1) 保留证据：把后端终端的堆栈原样留下（截图或复制文本）
# 2) 不要改代码；先记录"哪个请求、什么输入、什么堆栈"
# 3) 复现最小请求（空课表 + 空 preference），确认是否稳定复现
curl.exe -i -s -X POST http://127.0.0.1:8000/api/v1/plan `
  -H "Content-Type: application/json" `
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

```bash
curl -i -s -X POST http://127.0.0.1:8000/api/v1/plan \
  -H 'Content-Type: application/json' \
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

**现场降级（唯一允许的动作）**：

```text
① 停止使用模式 2 的 Real 提交；
② 明确切回模式 1（Mock Demo，全链路仍然完整可演示）；
③ 如实说明遇到的是一个未修复的服务端错误。
```

### ④ 演示如何继续

> 「刚才这次请求返回了 500，这是服务端的未预期错误，和我们前面讲的 fail-closed 503 是两回事：
> 就绪性问题会明确返回 503 并说明原因，程序缺陷则是 500，**不会被包装成"未配置"糊过去**。
> 我现在切回 Mock 演示通道继续演示完整交互。」

### 不要做什么

- ⛔ 不要为了"让演示继续"去捕获异常、把 500 改成 503 或改成 200；
- ⛔ 不要用 Mock 结果顶替这次失败的结果；
- ⛔ 不要说"这是配置问题" —— 500 说明配置门已经过了，是程序缺陷；
- ⛔ 不要在现场改后端源码（本次演示准备的质量门禁由另一个流程负责）。

---

## 10. 演示环境变量配错或残留

### ① 现象

- 上一次演示/调试留下的 `APP_*` 变量还在：本次启动后端时"莫名"不带 Mock 默认行为；
- 开关值写成 `true` / `yes` / `01` / 全角字符；
- 路径变量指向**不存在**的文件（往往因为换了机器 / 换了目录）；
- digest 形态非法：长度不是 64、混入非十六进制字符、误填了 raw campus bundle digest；
- 前端 `VITE_PLAN_API_ENABLED` 留在 `true`，Real 提交按钮一直可用（演示时容易被误点）。

### ② 判断依据

```powershell
# 只看"有没有设置"，不要回显真实路径
Get-ChildItem Env:APP_ | Select-Object Name
Get-ChildItem Env:VITE_ | Select-Object Name
```

```bash
env | grep -E '^(APP_|VITE_)' | cut -d= -f1
```

```powershell
# 形态检查（不打印真实值，只返回 布尔/长度）
$env:APP_REAL_CASE_A_ENABLED -in @('','0','1')                 # False ⇒ 开关值非法
$env:APP_COURSE_DATA_ACCEPTANCE_SHA256 -match '^[0-9a-fA-F]{64}$'   # False ⇒ digest 形态非法
Test-Path $env:APP_CASE_A_CURRICULUM_CASE_PATH                 # False ⇒ 路径不存在
Test-Path $env:APP_COURSE_DATA_SQLITE_PATH                     # False ⇒ 库不存在
```

### ③ 处理步骤

**安全清空并回到模式 1（推荐做法）**：

```powershell
# 1) 清掉全部 5 个 runtime 变量（先备份到本地受控文件再清，便于以后恢复模式 2）
Get-ChildItem Env:APP_ | Select-Object Name, Value | Out-File <本地目录>\app-env.backup.txt

Remove-Item Env:APP_REAL_CASE_A_ENABLED, Env:APP_CASE_A_CURRICULUM_CASE_PATH, `
  Env:APP_COURSE_DATA_SQLITE_PATH, Env:APP_COURSE_DATA_SEMESTER, `
  Env:APP_COURSE_DATA_ACCEPTANCE_SHA256 -ErrorAction SilentlyContinue

# 2) 前端开关回到默认（按钮不可用 = 推荐比赛默认）
Remove-Item Env:VITE_PLAN_API_ENABLED -ErrorAction SilentlyContinue
# 若写在 frontend/.env.local 里，也需要一并清掉（该文件不入 Git）
```

```bash
# bash 等价
unset APP_REAL_CASE_A_ENABLED APP_CASE_A_CURRICULUM_CASE_PATH \
      APP_COURSE_DATA_SQLITE_PATH APP_COURSE_DATA_SEMESTER \
      APP_COURSE_DATA_ACCEPTANCE_SHA256 VITE_PLAN_API_ENABLED
```

```powershell
# 3) 重启后端与前端（环境变量改了必须重启）
cd backend ; python -m uvicorn app.main:app --reload --port 8000
cd frontend ; npm run dev

# 4) 验证已回到模式 1
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/api/v1/mock/demo   # 期望 200
```

### ④ 演示如何继续

- 清空后就是干净的模式 1：基础数据与规划结果**全部标注 Mock**，一切如实。
- 口播：
  > 「真实链路需要 5 个显式环境变量，缺一个都只会有 503，不会有任何降级。
  > 现在环境里没有这些变量，所以系统处于默认的演示快照回放模式。」

### 不要做什么

- ⛔ 不要在演示中"试着配一下"真实链路变量——这不属于现场应急，且需要已批准的真实前置条件；
- ⛔ 不要用假路径 / 假 digest 让某个分支"过去"（结果只是同一个 503，还会留下错误印象）；
- ⛔ 不要把 `.env` / 真实路径写进仓库或提交（真实 artifact 与本地路径都不入库）。

---

## 11. 浏览器状态异常（页面停留在上一次 Real 结果）

### ① 现象

- 页面「规划结果」区块的来源标注仍是 **Real**，展示的是**上一轮**提交的结果；
- 或者你先在模式 2 提交过 Real，之后切回模式 1，页面却还显示旧内容；
- 或者输入区显示上一次填写的课表 / 偏好。

### ② 判断依据

- 前端把 Real 结果保存在**内存**里：只有**成功调用** `POST /api/v1/plan` 才置为 Real，
  失败时立刻回到 Mock，且**不会**回退去调 Mock 通道；
- 页面刷新 = 重新挂载：`规划结果来源` 初始值就是 **Mock**（`initialDataMode()` 恒返回 `'mock'`）；
- 因此「刷新后还是 Real」在正常情况下**不应该出现**；如果出现，说明你刷新的是一个**没有重新加载**的标签页（或多标签页里另一个旧标签）。

### ③ 处理步骤

```text
1) 硬刷新当前标签页：Ctrl+F5（Windows）/ Cmd+Shift+R（macOS）
2) 仍有残留 → 关掉这个标签页，重新打开 http://127.0.0.1:5173
3) 只保留一个演示标签页（避免多标签页各自是不同状态）
```

验证已回到干净状态：

```text
- 「规划结果」来源标注 = Mock
- 未决事项 / 建议课表 / 风险项都来自 Mock Demo
- Network 面板：只有 GET /api/v1/mock/demo（没有 POST /api/v1/plan）
```

### ④ 演示如何继续

> 「刷新之后，规划结果回到 Mock 演示通道 —— 因为 Real 结果只存在于本页内存里，
> 页面不会把它缓存到任何地方，也不会在下一次打开时假装还有效。
> 要看 Real 结果，需要用当前配置重新提交一次。」

### 不要做什么

- ⛔ 不要为了消除"看起来对不上"的观感去隐藏 provenance 标注；
- ⛔ 不要说页面"缓存了真实结果"（它只保存在当前页面内存里）；
- ⛔ 不要在演示中途把模式 1 / 模式 2 来回切换而不重新提交、不重新说明来源。

---

## 12. 后端的两个"每次都会重新来一遍"的行为

### 12.1 每请求重新装配

```text
POST /api/v1/plan 的每次请求都会**重新装配** runtime：
重新校验 acceptance 绑定、行数、case 就绪状态。
⛔ 不存在"启动时验证过就一直有效"的缓存。
```

**现场含义**：演示前如果你改过库、换过 case、动过环境变量，
上一次的成功**不能**作为这一次仍然可用的依据 —— 必须重新提交、重新看结果与 provenance。

🛠 复现检查（如实展示，不需要掩饰）：

```powershell
# 提交 → 200（Real）；然后在另一个终端让 acceptance 失效，再提交 → 503
curl.exe -i -s -X POST http://127.0.0.1:8000/api/v1/plan `
  -H "Content-Type: application/json" -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

### 12.2 后端重启之后

- 后端进程重启后，**前端页面不会自动重新提交**：Real 结果区还停在上一次的内存状态；
- 需要：① 重新点一次 Real 提交；② 或硬刷新页面回到 Mock（见 §11）。

```powershell
# 重启后按顺序确认
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/health        # 200
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/api/v1/mock/demo   # 200
# 回到页面 → 硬刷新 → 重新提交（若需要 Real）
```

### ④ 演示如何继续

> 「后端不缓存规划状态：每次提交都是重新校验、重新求解。
> 所以刚才重启后端之后，页面上的旧结果不算数，我重新提交一次。」

### 不要做什么

- ⛔ 不要说"结果被缓存了，所以刚才那个 200 还有效"；
- ⛔ 不要把"重启后页面还显示旧结果"解释成"数据持久化"；
- ⛔ 不要在没重新提交的情况下，指着旧结果说它反映了当前配置。

---

## 12.3 教学班演示快照不可用 / Synthetic 标签看不到

### ① 现象

- 「2. 开课教学班供给 (CourseOffering)」区块为空或数量为 0；
- 页面**看不到**教学班数据的来源标注。

### ② 判断依据

- 教学班数据来自 `GET /api/v1/mock/demo`（`mock_data/course_offerings.json`）；
  区块为空 ⇒ Mock 通道这一项没回来（先回到 §3 / §7 查通道本身）；
- 页面必须能明确看到 **「教学班数据：演示快照（Synthetic）」** 这一标注。
  **这是模式 2 下教学班数据的唯一披露面**：
  代码会把已验收 Course Data 行的 `data_source` 置为 **REAL**（已记录的 OPEN ITEM），
  因此**如果这个标签不可见，页面上就没有任何东西能说明教学班是 Synthetic 快照** —— 必须当场口头更正并停止展示该区块。

```powershell
# 通道侧自检（200 且带 X-Data-Source: mock）
curl.exe -i -s http://127.0.0.1:8000/api/v1/mock/demo | Select-String -Pattern "HTTP/|X-Data-Source"
```

### ③ 处理步骤

```text
1) 先确认 Mock 通道可用（§3 / §7）；通道不可用就先修通道，不要动教学内容；
2) 通道可用但区块为空 → 不要手填数据；如实说明"本次未取到教学班演示快照"；
3) 看不到 Synthetic 标注 → 按下面第 ④ 点当场如实说明，并跳过教学班区块的细节讲解。
```

### ④ 演示如何继续

必须逐字使用下面这段既定表述（不可改写、不可省略）：

> 「教学班数据：演示快照（Synthetic）」
>
> 「由于学校教务系统北校园开课查询存在稳定的深分页异常，当前比赛版本的教学班演示使用经过明确标识的 Synthetic 快照。系统的培养方案解析、补修判定、约束规划、Path Repair、风险解释与前后端运行链路仍按正式架构执行。」

⚠️ 若标签在页面上不可见：**先口头说出上面这段**，再决定是否继续讲教学班细节。
⛔ 标签不可见时，**不得**让评委以为教学班是真实教务数据。

### 不要做什么

- ⛔ 不要建议现场去"探测 / 试一下"北校园开课查询（这是**外部系统阻塞**，已挂起）；
- ⛔ 不要声称教学班数据可用 / 已接通教务；
- ⛔ 不要手填一份教学班列表补上；
- ⛔ 不要说"教学班就是真实的，只是没显示标注"。

---

## 12.4 时间不够 / 某个场景无法展示

### ① 现象

- 评委时间被压缩到 2–3 分钟；
- 某个场景（例如模式 2 的 Real 提交）**当场跑不起来**。

### ② 判断依据

```text
不是所有场景都必须现场跑通才算完成演示。
**能讲清"数据来源 + 系统边界 + fail-closed 行为"** 比跑通一个可疑的成功更有说服力。
```

### ③ 处理步骤（缩减原则）

```text
保留：数据来源标注（Mock / Real / Synthetic）、fail-closed 的 503 与页面文案、
      前端"不生成替代结果、不回退 Mock"的证据（Network 面板）。
砍掉：逐字段讲解、逐页面滚动、非关键交互、模式 2 的完整重配置。
```

### ④ 演示如何继续

> 「时间有限，我聚焦三件事：① 这条链路每一段的数据来源是什么；
> ② 未就绪时系统会怎么拒绝；③ 页面绝不生成替代结果。」

### 不要做什么

- ⛔ 不要为了"演示成功"跳过标注、简化成"数据都是真的"这类话；
- ⛔ 不要把没跑通的场景说成"刚才已经验证过"；
- ⛔ 不要用 Mock 数据讲成 Real 结果来"节省时间"。

---

## 13. 最小可信演示路径（2 分钟兜底）

**目标**：在最短时间内，把「系统能做什么」与「数据到底是什么」同时讲清楚，且**一句话都不假**。

### 13.1 只演示这些区块（按顺序）

| 顺序 | 区块 / 动作 | 只说这一句关键话 |
|---|---|---|
| 1 | 顶栏「后端数据源标头」= `mock` | 「页面所有数据的来源标头由后端给出，现在是 Mock。」 |
| 2 | 1. 历史培养要求评估（MakeupTask） | 「这是 Curriculum 侧按培养方案与学生已修记录逐条评估的结果，属**演示数据**。」 |
| 3 | 2. 开课教学班供给 | 「教学班数据：演示快照（Synthetic）」+ 深分页异常那段既定表述 |
| 4 | 3. 学生个性化偏好 | 「偏好来自 Agent 对自然语言的解析，同样标注为演示数据。」 |
| 5 | 4. 规划结果来源标注 | 「基础演示数据是 Mock；规划结果当前也是 Mock（来自 `GET /api/v1/mock/demo`）。」 |
| 6 | 若时间允许：后端一条 503 探针 | 「真实链路未配置时返回 503 `real_pipeline_not_configured`，**不回退 Mock**。」 |

```powershell
# 第 6 步的那一条命令（可选）
curl.exe -i -s -X POST http://127.0.0.1:8000/api/v1/plan `
  -H "Content-Type: application/json" -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

### 13.2 必须说清的 5 个事实（一个字都不能省）

```text
1. 基础数据（培养要求评估 / 教学班 / 偏好）来自 GET /api/v1/mock/demo，是**演示数据 / Mock**；
2. 教学班输入是**明确标注的 Synthetic 演示快照**：教学班数据：演示快照（Synthetic）；
3. 真实规划链路需要**本机已批准的真实 Case A manifest** + **已验收的整学期 Course Data 库**，
   二者都不在 Git 中，是显式前置条件；
4. 任何一步未就绪 ⇒ POST /api/v1/plan 返回 503 real_pipeline_not_configured，
   **不回退到 Mock、不生成替代结果**；程序缺陷是 500，不会伪装成 503；
5. 正式 Real E2E 证据等级仍是 **LEVEL 0**（尚未达成 LEVEL1 / LEVEL2 / LEVEL3）。
```

### 13.3 兜底话术（可直接照读）

> 「本次演示的是**演示快照回放**模式：基础数据与规划结果都来自后端的 Mock 聚合接口，
> 页面上每一处来源都标注了 Mock。
> 教学班数据：演示快照（Synthetic）。
> 由于学校教务系统北校园开课查询存在稳定的深分页异常，当前比赛版本的教学班演示使用经过明确标识的 Synthetic 快照。系统的培养方案解析、补修判定、约束规划、Path Repair、风险解释与前后端运行链路仍按正式架构执行。
> 真实规划链路需要本机已批准的真实 Case A manifest 与已验收的整学期 Course Data 库，
> 这两个前置条件不在仓库里；未就绪时接口明确返回 503，不会回退成 Mock，也不会给一个看起来成功的替代结果。
> 正式 Real E2E 的证据等级目前是 LEVEL 0。」

### 13.4 绝对不要说的（现场红线）

```text
⛔ 已连接实时教务系统 / 实时教务数据
⛔ 全部数据均为真实
⛔ Real E2E completed
⛔ 可直接执行 / 已选课 / 已注册
⛔ 无冲突（排课信息未知时只能说「当前数据中无排课信息」）
⛔ 官方已批准 / 完全无风险
⛔ 任何"假装成功"的兜底说法
```

---

## 14. 相关文档

- `docs/e2e/DEMO_RUNBOOK.md` —— 赛前启动顺序、检查点与 Real 不可用时的标准做法；
- `docs/e2e/REAL_CAPTURE_AND_RUNTIME_RUNBOOK.md` —— runtime 5 个变量、三种 digest 的命名、状态语义与失败矩阵；
- `docs/data/CASE_A_RUNTIME_WIRING.md` —— 真实链路装配、诊断码与 503 / 500 的异常边界；
- `frontend/README.md`、`backend/README.md` —— 各自运行说明。
