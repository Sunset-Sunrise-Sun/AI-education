# 比赛启动文档 · 学航·转衔（Competition Startup）

> 面向**比赛现场操作者**。目标只有两个：**一次就能启动**，并且**演示过程中不说假话**。
> 本文件只描述**当前仓库真实存在**的启动路径与开关；命令、变量名、端口均以仓库代码为准。
>
> ⚠️ **实现边界（开场必须说清）**：当前为**固定工具编排原型**；**LLM / RAG / GraphRAG 尚未接入**，
> 没有模型推理、没有检索管线、没有自然语言偏好解析（`Preference` 来自结构化表单）。

**两种演示模式（先选一种，再往下读）：**

| 模式 | 名称 | 需要什么 | 数据性质 |
|---|---|---|---|
| **模式 1（默认）** | 演示回放 | 干净检出即可运行，**零配置** | 基础数据与规划结果**全部是 Mock 演示数据**（`GET /api/v1/mock/demo` 回放预置对象，**不执行上游业务计算**） |
| **模式 2** | 计算模式 | 操作者本机**显式本地输入**：Case A manifest（来源须由批准 provenance 证明）+ 已验收的整学期 Course Data SQLite 库 | **规划结果区**由 `POST /api/v1/plan` 的**实际代码计算**；**页面基础展示区仍为 Mock 演示数据**；**教学班输入**是明确标注的 Synthetic 演示快照 |

---

## 0. 一页速查：唯一一条确定性启动路径

⛔ 不存在第二条"也行得通"的启动方式。只按这一条走，只开**两个终端**。

```text
终端 A（后端）                      终端 B（前端）
cd backend                          cd frontend
python -m uvicorn app.main:app \    npm install      （仅首次）
    --reload --port 8000            npm run dev
        ↓                                   ↓
http://127.0.0.1:8000/health        http://127.0.0.1:5173
```

**成功判据（四条同时成立才算启动成功）：**

1. 终端 A 出现 `Uvicorn running on http://127.0.0.1:8000`，且**没有**"启动自检失败"字样；
2. 浏览器打开 <http://127.0.0.1:8000/docs> 能正常显示接口文档（后端存活探针也可用：`GET /health` 返回 `{"status":"ok",...}`）；
3. 终端 B 打印出本地地址，浏览器打开 **`http://127.0.0.1:5173`** 后页面正常渲染；
4. 页面上能看到「**教学班数据：演示快照（Synthetic）**」，并且**没有**出现「**后端接口连接异常**」。

⚠️ 前端**不直连**后端：`/api` 由 Vite dev server 代转发到 `http://127.0.0.1:8000`。
因此**必须**用 Vite 的地址打开页面，⛔ 不要直接双击 `dist/index.html`。

---

## 1. 模式 1：零配置启动（比赛默认）

### 1.1 前置条件

- 已 clone 仓库，工作目录干净；
- Python 环境可用（`backend/requirements.txt` 已安装）；
- Node.js 可用（首次需要 `npm install`）；
- **不设置任何真实链路环境变量**——模式 1 就是"什么都不配"。

### 1.2 终端 A：启动后端

PowerShell（主要环境）：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

bash 变体：

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

⚠️ 必须在 `backend/` 目录下运行；否则会得到 `ModuleNotFoundError: No module named 'app'`。

### 1.3 终端 B：启动前端

PowerShell：

```powershell
cd frontend
npm install        # 仅首次
npm run dev
```

bash 变体：

```bash
cd frontend
npm install        # 仅首次
npm run dev
```

打开终端 B 提示的地址，默认 **<http://127.0.0.1:5173>**。

### 1.4 预期看到什么

- 页面标题区：`学航·转衔` / 面向转专业学生的学业路径重构**原型**（固定工具编排，AI 增强待接入）；
- 黄色警示条与区块 `Mock` 标记；页面展示后端响应头 `X-Data-Source` 的实际取值（Mock 通道为 `mock`）；
- 四个区块都有内容：补修任务 / 开课教学班 / 用户偏好 / 规划结果；
- 规划结果区显示「**规划结果来源：Mock**」（**回放预置结果，本模式不执行 Planner**）；
- 教学班区显示「**教学班数据：演示快照（Synthetic）**」以及“输入来源需逐项核验”的说明；
- 「真实规划提交」入口**默认不可用**（`VITE_PLAN_API_ENABLED` 未设置即为 false）——这是**预期行为**，不是故障。

### 1.5 规则与边界（模式 1 必须口头同步给评委）

```text
① 本模式的全部数据（含规划结果）都是仓库内 mock_data/*.json 的**人工演示数据**，
   并已按 /schemas/*.schema.json 公共契约校验；⛔ 不是真实教务数据。
② 规划结果来自 Mock 回放通道，**不是**求解器算出来的结果。
③ Mock 通道是**永久只读**通道（GET /api/v1/mock/demo，带 X-Data-Source: mock），
   任何阶段都不会返回真实教务数据，也不会被改造成真实数据接口。
④ ⛔ 不得把 Mock 数据说成真实数据。
```

---

## 2. 模式 2：计算模式启动（`POST /api/v1/plan` 实际代码计算）

> 只有**操作者本机**具备受控真实输入时才走这一节。
> 真实 Case A manifest **不在 Git 中**（受控真实输入），必须在操作者本机另行准备。

### 2.1 前置条件清单（逐项打勾，缺一不可）

```text
[ ] 1. 显式本地 Case A manifest（case JSON，data_source=real，目标版本 = Case A，
        makeup_scope.as_of_term 与已批准决策集合一致）——不在 Git 中
        ⚠️ data_source=real 只是**契约/来源声明**，不是来源证明：
        真实学校来源须由绑定该 artifact 字节的**批准 provenance 证据**另行证明
[ ] 2. 已验收的整学期（full semester）Course Data SQLite 库：包含恰好一条 full_semester
        acceptance 记录，complete、计数自洽（⚠️ 通过验收只证明完整性与一致性，
        不证明数据来自学校；比赛演示的这份供给是 Synthetic 快照）
[ ] 3. 该 acceptance 的 manifest SHA-256（64 位十六进制）
[ ] 4. 明确标注的 Synthetic 演示快照，作为本次的**教学班输入**
[ ] 5. 后端依赖已安装（backend/requirements.txt）
[ ] 6. 前端依赖已安装（frontend 下 npm install）
```

**前置条件 1 / 2 的存在性检查命令（PowerShell，只检查文件在不在，不做任何判定）：**

```powershell
# 已批准的真实 Case A manifest
Test-Path -PathType Leaf 'C:\受控目录\case-a.json'

# 已验收的整学期 Course Data SQLite 库
Test-Path -PathType Leaf 'C:\受控目录\course-data.sqlite3'

# 确认拿到的是 64 位十六进制 acceptance digest 形态（不是 64 位以下、也不是含非 hex 字符）
$sha = '<full-semester manifest sha256>'
$sha -match '^[0-9a-fA-F]{64}$'      # True 才继续
```

bash 变体：

```bash
test -f /path/to/case-a.json && echo manifest-ok
test -f /path/to/course-data.sqlite3 && echo store-ok
printf '%s' '<full-semester manifest sha256>' | grep -Eq '^[0-9a-fA-F]{64}$' && echo sha-shape-ok
```

⚠️ 上述命令**只验证文件存在与 digest 形态**。真正的就绪性判定由后端在每次请求时执行（见 §2.3）。

### 2.1.1 教学班演示快照（Synthetic）与本地验收库的准备路径

比赛演示的教学班输入是**明确标识的 Synthetic 演示快照**（⛔ 不是真实教务数据）。
它必须先经过**既有整学期验收链路**写成 SQLite，之后才会被运行时读取：

```text
tools/generate_competition_demo_snapshot.py     确定性合成 5 个 campus bundle + 披露文件
        ↓  （既有、未修改的验收链路；两步流程）
tools/prepare_real_case_a_runtime.py 第 1 步     草稿 capture inventory
tools/prepare_real_case_a_runtime.py 第 2 步     正式 acceptance → SQLite（+ 可选 runtime.env）
        ↓
运行时 5 个环境变量（第 2 个由操作者显式给出：已批准的真实 Case A manifest 路径）
```

PowerShell（在仓库根目录执行）：

```powershell
$OUT = "demo_runtime"   # 该目录已在 .gitignore 中；⛔ 不要把演示快照提交进仓库

# 1) 合成演示快照：课程号来自**已批准 Case A manifest 的补修判定投影**；
#    同一组输入 ⇒ 逐字节相同的五个 campus bundle
python tools/generate_competition_demo_snapshot.py --out-dir $OUT --semester 2026-1 --case 'C:\受控目录\case-a.json'
```

命令会打印**可直接复制**的后续两步（含真实路径）：
第 0 步（可选）逐个校区离线校验、第 1 步生成草稿 inventory、第 2 步跑正式 acceptance 并写出 `runtime.env`。
`$OUT\DEMO_SNAPSHOT_DISCLOSURE.json` 用 `<OUT_DIR>` 占位符记录了同一组命令，并记录
`bundle_sha256`、各校区行数、`baseline_total` 与 `synthetic: true` 披露。

只有本机离线自检（⛔ 不接任何真实 Case）时才使用显式课程号模式：

```powershell
python tools/generate_competition_demo_snapshot.py --out-dir $OUT --semester 2026-1 `
  --course-id CSE101 --course-id CSE102 --course-id CSE103 --course-id CSE104 --course-id CSE105
```

⚠️ 必须知道的五点：

1. 第 2 步产出的 `runtime.env` 在**没有**已批准 Curriculum provenance 时只包含 4 个变量
   （工具状态为 `partial_ready`，`level2_eligible=false`）：此时**⛔ 不得启动计算链路**——
   ⛔ 不允许"手工把 `APP_CASE_A_CURRICULUM_CASE_PATH` 补进环境变量就直接跑 Real runtime"来绕过 gate。
   正确做法：提供**与之匹配的已批准 Curriculum provenance 记录**，用同一组输入**重跑一次就绪性验证**
   （最终 Store + Curriculum 双复验），只有状态为 `ready` 时该 runtime 路径才可启动。
2. **`ready` ⛔ 不等于 LEVEL2**：
   - `ready` = 运行时输入通过了 Store + Curriculum 的**最终复验**（可装配、可读取、逐请求重校验）；
   - `ready` **不证明**：真实学校 Course Data provenance、LEVEL 2、LEVEL 3；
   - **Synthetic 教学班供给同样可以产出 runtime-ready 的本地计算 demo**，但它不会因此成为真实学校数据；
   - **LEVEL 2 额外要求**：已批准的真实 Course Data provenance / handoff、与之精确对应的已验收整学期证据、
     已批准的真实 Curriculum provenance，且**不得有 synthetic 替代**。
   - ⛔ 禁止表述："补齐 approved Curriculum 之后就能达到 LEVEL2"或任何等价说法。
3. 演示快照的每一行都带 `DEMO-` 教学班号前缀与 `DEMO` 场地标记，并且每第 4 行**省略排课字段**
   （规范化后 `meetings = []`，用于演示「当前数据中无排课信息」这一中性状态）。
4. ⛔ 不得为了让演示更"完整"而放宽验收规则、跳过任一已批准校区、改写 acceptance 记录或伪造 provenance；
   五个校区都必须有行，且必须通过既有 acceptance 才会被运行时读取。
5. ⛔ 不得把 synthetic handoff / synthetic Curriculum 证据改写成 non-synthetic，也不得把演示数据
   送入"真实来源资格"声明（`level2_eligible` 必须如实保持 `false`）。

### 2.2 启动顺序

**第 1 步：终端 A —— 先设置 5 个环境变量，再启动后端**

运行时环境变量**恰好 5 个**（全部只在模式 2 需要）：

| # | 变量 | 取值 |
|---|---|---|
| 1 | `APP_REAL_CASE_A_ENABLED` | `1` |
| 2 | `APP_CASE_A_CURRICULUM_CASE_PATH` | 已批准真实 Case A manifest 的本地路径 |
| 3 | `APP_COURSE_DATA_SQLITE_PATH` | 已验收整学期 Course Data SQLite 库路径（建议绝对路径） |
| 4 | `APP_COURSE_DATA_SEMESTER` | 与 acceptance 绑定的学期**精确相等**（例如 `2026-1`） |
| 5 | `APP_COURSE_DATA_ACCEPTANCE_SHA256` | 整学期 acceptance 的 manifest SHA-256（64 hex） |

PowerShell：

```powershell
cd backend
$env:APP_REAL_CASE_A_ENABLED="1"
$env:APP_CASE_A_CURRICULUM_CASE_PATH="C:\受控目录\case-a.json"
$env:APP_COURSE_DATA_SQLITE_PATH="C:\受控目录\course-data.sqlite3"
$env:APP_COURSE_DATA_SEMESTER="2026-1"
$env:APP_COURSE_DATA_ACCEPTANCE_SHA256="<full-semester manifest sha256，64 hex>"
python -m uvicorn app.main:app --reload --port 8000
```

bash：

```bash
cd backend
export APP_REAL_CASE_A_ENABLED=1
export APP_CASE_A_CURRICULUM_CASE_PATH="/path/to/case-a.json"
export APP_COURSE_DATA_SQLITE_PATH="/path/to/course-data.sqlite3"
export APP_COURSE_DATA_SEMESTER="2026-1"
export APP_COURSE_DATA_ACCEPTANCE_SHA256="<full-semester manifest sha256，64 hex>"
python -m uvicorn app.main:app --reload --port 8000
```

**第 2 步：终端 B —— 打开前端真实规划提交入口**

```powershell
cd frontend
$env:VITE_PLAN_API_ENABLED="true"
npm run dev
```

bash：

```bash
cd frontend
export VITE_PLAN_API_ENABLED=true
npm run dev
```

前端变量（与运行时变量是两套，不要混）：

| 变量 | 作用 | 取值 |
|---|---|---|
| `VITE_PLAN_API_ENABLED` | 是否显示/启用真实规划提交 | 必须为字符串 `true` 才启用 |
| `VITE_PROXY_TARGET` | Vite 代理目标 | 默认 `http://127.0.0.1:8000` |
| `VITE_API_BASE_URL` | 后端基地址 | 留空 = 走同源 Vite 代理（推荐） |

⚠️ `frontend/.env.example` **已存在**，且**目前只含 `VITE_PROXY_TARGET` 与 `VITE_API_BASE_URL`，不含 `VITE_PLAN_API_ENABLED`**。
因此请把 `VITE_PLAN_API_ENABLED=true` 写进 `frontend/.env.local`，或用上面的 `$env:` / `export` 方式设置。
⚠️ Vite 只在启动时读取这些变量，改完必须**重启** `npm run dev`。
⛔ 本文件不覆盖已有的 `frontend/.env.example`。

**第 3 步：确认后端是否真的就绪（唯一可靠的判据）**

```powershell
curl.exe -i -s -X POST http://127.0.0.1:8000/api/v1/plan `
  -H 'Content-Type: application/json' `
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

bash：

```bash
curl -i -s -X POST http://127.0.0.1:8000/api/v1/plan \
  -H 'Content-Type: application/json' \
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

| 观察 | 含义 | 该做什么 |
|---|---|---|
| **503** + `"error": "real_pipeline_not_configured"` | 就绪条件未满足（未装配 / 输入缺失 / 失配 / 失效） | 检查 5 个变量与两项真实输入；**这是设计上的诚实拒绝，不是崩溃** |
| **200** + 合法 `PlanResult` | 5 个变量齐全且一致，链路已装配并返回方案 | 可以进入模式 2 演示 |

进一步确认：

- 后端 Mock 通道**始终独立可用**：`GET /api/v1/mock/demo` 仍返回 200 且带 `X-Data-Source: mock`；
- ⛔ 真实 `POST /api/v1/plan` **不返回** `X-Data-Source` 响应头（不要用它判断来源）；
- ⛔ **fail-closed**：任一就绪条件不满足 ⇒ 503，**绝不回退 Mock**；
- ⛔ 出现 503 时，页面上「Mock 规划结果」仍以来源标注 `Mock` 展示，请求数不会增加——这是**正确行为**，不是"静默替代"。

### 2.3 模式 2 下必须如实说明的三件事

```text
① 规划结果区的方案来自 `POST /api/v1/plan` 的**实际代码计算**（Actual API computation）；
   页面基础展示数据（培养要求评估 / 教学班 / 偏好）**仍来自 Mock 演示通道**，两者必须分别标注；
   ⛔ 实际代码执行**不等于**输入数据已获得真实学校来源认证。
② 教学班输入明确标注为 Synthetic 演示快照；Curriculum 输入是否真实须由该次批准证据逐项核验。
③ 正式 Real E2E 证据等级仍是 **LEVEL 0**；⛔ 不得声称 LEVEL1 / LEVEL2 / LEVEL3。
```

评委若问「教学班数据是怎么来的」，**逐字**使用下面这段：

> 由于学校教务系统北校园开课查询存在稳定的深分页异常，当前比赛版本的教学班演示使用经过明确标识的 Synthetic 快照。系统的培养方案解析、补修判定、约束规划、Path Repair、风险解释与前后端运行链路仍按正式架构执行。

⚠️ 北校园开课查询采集为**外部系统阻塞**、已挂起：⛔ 不要在演示中建议探测、也不得声称可用。

⚠️ 已验收 Course Data 行的 `data_source` 会被代码置为 **REAL**（已记录 OPEN ITEM）。
该字段是**契约 / 来源声明**，⛔ **不是** provenance 证明：形状正确的 Synthetic 输入经 adapter 后同样可能带上 `real` 枚举值，
因此 **不得**据此判定为真实学校来源。模式 2 下前端「**教学班数据：演示快照（Synthetic）**」标签必须整场保持可见，
同时按上面的口径说明"输入来源需逐项核验"（⛔ 不把它当成全页 provenance 的"唯一披露面"的说法，
也不得由此推出"其余输入都真实"）。

---

## 3. 验证清单（演示前逐条做一遍）

| # | 检查项 | 可执行检查方法 | 期望结果 |
|---|---|---|---|
| 1 | 干净刷新 | 浏览器硬刷新（Ctrl+F5）后重新加载页面 | 页面正常渲染；**无**「后端接口连接异常」；「教学班数据：演示快照（Synthetic）」可见 |
| 2 | 后端重启 | 终端 A `Ctrl+C`，再执行同一条 uvicorn 命令；随后在浏览器硬刷新 | 后端重新出现 `Uvicorn running on http://127.0.0.1:8000`；刷新后页面恢复正常；Mock 通道 `GET /api/v1/mock/demo` 仍 200 |
| 3 | 重复生成规划 | 连续提交两次相同输入的真实规划请求 | 两次响应的状态码与来源标注一致；不出现"第二次偷偷换成 Mock"或来源标注翻转 |
| 4 | 错误状态 | 停掉后端（终端 A `Ctrl+C`），再在页面触发一次数据加载 | 页面**只显示错误**（如「后端接口连接异常」），页面上**没有**任何编造/替代的方案数据；重新启动后端后可恢复 |
| 5 | ⛔ 不得出现静默替代结果（no silent substitute） | 模式 2 下故意改错 `APP_COURSE_DATA_ACCEPTANCE_SHA256` 后重新提交；并在浏览器 Network 面板观察请求 | 只出现 `POST /api/v1/plan` → **503** `real_pipeline_not_configured`；⛔ **不出现**新增的 `/api/v1/mock/*` 请求；⛔ 失败后不生成任何替代方案 |
| 6 | Synthetic 标签整场持续可见 | 演示过程中每换一个展示区块就回看教学班区标题 | 自始至终显示「**教学班数据：演示快照（Synthetic）**」，全程不被折叠、不被覆盖、不被改写 |

补充自查（模式 2，对失败要"因类型而异"而不是笼统一句"请求失败"）：

- 503 未装配 → 页面显示"尚未完成装配"类文案 + HTTP 503 + 错误码 `real_pipeline_not_configured`；
- 服务端其它错误 → 归为 server 类错误，⛔ **不写成**"未装配"；
- 排课信息缺失（`meetings` 为空）→ 中性文案「**当前数据中无排课信息**」；
  ⛔ 不出现「无冲突」「无需上课」「可直接执行」「已选课」「已注册」等断言。

---

## 4. 环境变量速查表

### 4.1 运行时（后端，模式 2 才需要；**恰好 5 个**）

| 变量 | 必需 | 取值 | 缺失/非法时的行为 |
|---|---|---|---|
| `APP_REAL_CASE_A_ENABLED` | 模式 2 必需 | `1` | 未设置或 `0` ⇒ 链路关闭，`POST /api/v1/plan` 返回 **503** `real_pipeline_not_configured`；其它取值 ⇒ 配置非法，同样 **503** |
| `APP_CASE_A_CURRICULUM_CASE_PATH` | 模式 2 必需 | 已批准 Case A manifest 本地路径 | 缺失 / 非法 / 未标记 real / 非 Case A / 决策未获批准 ⇒ **503** |
| `APP_COURSE_DATA_SQLITE_PATH` | 模式 2 必需 | 已验收整学期 Course Data SQLite 库 | 缺失 / 文件不存在 / 非 Course Data 库 ⇒ **503** |
| `APP_COURSE_DATA_SEMESTER` | 模式 2 必需 | 与 acceptance 绑定的学期（如 `2026-1`） | 缺失或与绑定学期不一致 ⇒ **503** |
| `APP_COURSE_DATA_ACCEPTANCE_SHA256` | 模式 2 必需 | 整学期 acceptance 的 manifest SHA-256（64 hex） | 缺失 / 形态非法 / 与库中 acceptance 不一致 ⇒ **503** |

### 4.2 前端（Vite，`VITE_` 前缀）

| 变量 | 必需 | 取值 | 缺失时的行为 |
|---|---|---|---|
| `VITE_PLAN_API_ENABLED` | 模式 2 需要 | 字符串 `true` | 缺省/非 `true` ⇒ 真实规划提交入口显示为不可用，且**不会**改调 Mock 接口 |
| `VITE_PROXY_TARGET` | 可选 | 默认 `http://127.0.0.1:8000` | 使用默认值（推荐不动） |
| `VITE_API_BASE_URL` | 可选 | 留空 = 同源 Vite 代理 | 留空即走代理；一旦填值则浏览器直连后端，需要后端开 CORS（本仓库未开） |

⚠️ 两套变量互不替代：**前端开关只决定"能不能点提交"**；真实链路是否可用**永远由后端 readiness 决定**。

---

## 5. 关闭 / 清理

**演示结束后（两个终端）**

```text
终端 A：Ctrl+C  停止 uvicorn
终端 B：Ctrl+C  停止 vite
```

**从模式 2 回到模式 1（清空真实链路变量）**

PowerShell（当前终端会话内清空）：

```powershell
Remove-Item Env:APP_REAL_CASE_A_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:APP_CASE_A_CURRICULUM_CASE_PATH -ErrorAction SilentlyContinue
Remove-Item Env:APP_COURSE_DATA_SQLITE_PATH -ErrorAction SilentlyContinue
Remove-Item Env:APP_COURSE_DATA_SEMESTER -ErrorAction SilentlyContinue
Remove-Item Env:APP_COURSE_DATA_ACCEPTANCE_SHA256 -ErrorAction SilentlyContinue
```

bash：

```bash
unset APP_REAL_CASE_A_ENABLED
unset APP_CASE_A_CURRICULUM_CASE_PATH
unset APP_COURSE_DATA_SQLITE_PATH
unset APP_COURSE_DATA_SEMESTER
unset APP_COURSE_DATA_ACCEPTANCE_SHA256
```

然后**重启后端**（环境变量只在进程启动时读取）：清空后再起 uvicorn，`POST /api/v1/plan` 应回到 **503** `real_pipeline_not_configured`，此时即已回到模式 1。

⛔ **不要**把真实路径 / acceptance SHA 长期写进 shell 配置文件（`$PROFILE`、`~/.bashrc`、`~/.zshrc`）或提交进 Git。
⛔ 真实 artifact、成绩单、培养方案原件、cookie / token / session 一律不入 Git；收尾时确认 `git status` 干净。

---

## 6. 常见启动失败

| 现象 | 快速处理 |
|---|---|
| 页面一直 loading / 一直转圈 | 后端没起或没在 8000 端口；先起终端 A，再确认 `VITE_PROXY_TARGET` |
| 页面显示「后端接口连接异常」 | 没通过 Vite 地址打开页面；改用 `http://127.0.0.1:5173` |
| `ModuleNotFoundError: No module named 'app'` | 没在 `backend/` 目录下运行 uvicorn |
| 后端一启动就报「启动自检失败：Mock 数据不符合公共契约」 | `mock_data/` 下 JSON 被改坏；按报错里的文件名/字段名恢复 |
| `127.0.0.1` 连不上但 `localhost` 可以 | Node 在 Windows 上优先解析 IPv6；统一用 `127.0.0.1`（Vite 已显式绑该地址） |
| 真实规划提交得到 503 | 就绪条件未满足（预期内的诚实拒绝）；按 §2.1 逐条核对 5 个变量与两项真实输入 |

> 更细的排障与恢复步骤见 `docs/demo/DEMO_RECOVERY.md`（由另一位同事维护，本文件不重复其内容）。

---

## 7. 数据来源标注口径（Mock vs Real / Synthetic）

| 展示对象 | 模式 1（回放） | 模式 2（计算模式） |
|---|---|---|
| 页面基础数据（培养要求评估 / 教学班 / 偏好） | Mock 演示数据 | **仍为 Mock 演示数据**（页面基础区不会变成真实） |
| 教学班数据标签 | 「教学班数据：演示快照（Synthetic）」 | 「教学班数据：演示快照（Synthetic）」（**必须持续可见**；⛔ 它不是全页 provenance 的唯一披露面，Curriculum 来源须**逐项**核验） |
| 规划结果来源 | Mock（`GET /api/v1/mock/demo` **回放预置结果**，不执行 Planner） | **实际代码计算**（`POST /api/v1/plan` 成功；Actual API computation）；失败时仍为 Mock。⛔ 实际执行 ≠ 输入真实 |
| 风险 / 变更的来源 | `risks` / `changes` 为**人工构造的演示样例** | 以实际 Planner 输出为准（当前主要输出 `unresolved`，`risks` 可能为空） |
| 正式 Real E2E 证据等级 | **LEVEL 0** | **LEVEL 0**（不得声称 LEVEL1 / LEVEL2 / LEVEL3）；`ready` ⛔ ≠ LEVEL2 |

```text
⛔ 允许出现的说法：Mock 演示数据 · Synthetic 演示快照 · 实际代码计算 · 当前数据中无排课信息 · 待人工确认
⛔ 禁止出现的说法：已连接实时教务系统 · 实时教务数据 · 全部数据均为真实 ·
⛔ 禁止出现的说法：Real E2E completed · 可直接执行 · 已选课 · 已注册 · 无冲突 ·
⛔ 禁止出现的说法：官方已批准 · 完全无风险 ·
⛔ 禁止出现的说法：全局最优 · 自动调班 · 自动选课 · 偏好全部生效 · LLM / RAG / GraphRAG 已接入
```

---

## 8. 本文件引用的事实来源

- `AGENTS.md`（模块边界、Mock 规则、敏感信息与环境变量约定）
- `frontend/package.json`、`frontend/vite.config.ts`、`frontend/src/config.ts`（端口 5173、代理默认 `http://127.0.0.1:8000`、前端三个变量语义）
- `frontend/.env.example`（已存在；确认其当前内容不含 `VITE_PLAN_API_ENABLED`）
- `frontend/README.md`（前端运行方式与 Mock 边界）
- `backend/README.md`、`backend/app/main.py`、`backend/app/api/health.py`、`backend/app/api/mock.py`、`backend/app/services/mock_service.py`（uvicorn 启动方式、`/health`、`/api/v1/mock/demo`、`X-Data-Source: mock`、按 `/schemas/*.schema.json` 校验）
- `docs/e2e/DEMO_RUNBOOK.md`、`docs/e2e/REAL_CAPTURE_AND_RUNTIME_RUNBOOK.md`（5 个运行时变量、失败矩阵、前端逐项核对）
- `docs/data/CASE_A_RUNTIME_WIRING.md`（fail-closed 语义、503 `real_pipeline_not_configured` 与 `X-Data-Source` 头边界）
