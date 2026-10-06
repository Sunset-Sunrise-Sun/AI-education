# Real Capture Checklist（R3）· Runtime Startup Pack（R7）· Frontend Real-run Checklist（R8）

> ⛔ 本文件不含、也不得包含任何真实学生数据、成绩单、cookie / token / 凭据。
> ⛔ 不做认证绕过、不做 cookie 抽取、不做 token 收集、不做凭据存储。

## 1. 用户需要做的事（R3，仅此 6 步）

```text
1. 正常登录 SYSU（用你自己的账号与浏览器）
2. 如系统要求，完成 MFA
3. 打开**已批准**的浏览器上下文：
   - 已登录 SYSU 的同一浏览器
   - 打开开课查询页面（采集器与页面同源，`credentials: "same-origin"`）
   - 打开开发者工具 Console
4. 加载并运行已批准的采集脚本（见 §1.1）
5. 保存采集结果：五个 shard 的 raw bundle + 一份 diagnostics（见 §1.2）
6. 把五个文件交回项目工作流（见 §1.3）
```

⛔ 你**不需要**（也不应该）做这些 —— 它们全部由仓库工具自动完成：

```text
⛔ 手工编辑 JSON
⛔ 手工计算 SHA-256
⛔ 手工合并文件
⛔ 手工改写 source label
⛔ 直接修改 SQLite
⛔ 执行 SQL
⛔ 自行判断"是否 complete / 完整性"
```

### 1.1 运行采集器

在 Console 里加载 `tools/sysu_course_offering_collector.js`（粘贴内容或通过已批准方式注入），然后：

```javascript
await window.XuehangSysuCollector.collectSharded({ semester: "2026-1", maxPages: 20 })
```

说明：

- 请求顺序固定为 `baseline_before → 五个校区（串行，已批准顺序）→ baseline_after`；
- 全局 pacing：相邻请求至少 30 秒；每累计 5 个成功请求冷却 5 分钟（脚本自动执行，⛔ 不要手动狂点）；
- `maxPages` 超过默认值时会弹确认框；
- 脚本**不会**读取 / 保存 / 打印 / 导出任何浏览器认证状态；
- 失败即整个 run fail closed（⛔ 不要反复重试；把错误信息交给项目侧分析）。

### 1.2 保存结果（五个 shard + 一份 diagnostics）

```javascript
// 每个校区各存一份（校区名必须是下列五个之一）
window.XuehangSysuCollector.toShardJson(sharded, "东校园")     // → 存为 east-campus.json
window.XuehangSysuCollector.toShardJson(sharded, "南校园")     // → 存为 south-campus.json
window.XuehangSysuCollector.toShardJson(sharded, "深圳校区")   // → 存为 shenzhen-campus.json
window.XuehangSysuCollector.toShardJson(sharded, "珠海校区")   // → 存为 zhuhai-campus.json
window.XuehangSysuCollector.toShardJson(sharded, "北校园")     // → 存为 north-campus.json（North 未解决前预期失败）

// 外层 diagnostics（含 baseline_before / baseline_after / 各 shard reported_total）
window.XuehangSysuCollector.toDiagnosticsJson(sharded)        // → 存为 diagnostics.json
```

⚠️ 保存建议（⛔ 不是硬性要求，工具不依赖文件名）：

```text
把六个文件放在仓库**之外**的受控本地目录（真实 artifact ⛔ 不入 Git）
文件名任意，但请保持一致，便于你自己核对
```

### 1.3 交回项目工作流

把六个文件的**路径**交给下一步（§2）。工具会自己：

```text
读取五个 bundle → 逐校区 exact-byte 校验 → campus acceptance → inventory 草稿
（草稿需要你/Reviewer 明确批准）→ full-semester acceptance → 新 SQLite → provider read-back → env 值
```

## 2. 采集之后的一条命令（对齐 R2/R4）

```powershell
# 第一步：逐校区校验 + campus acceptance + inventory 草稿（不产出 acceptance）
python tools/prepare_real_case_a_runtime.py `
  --semester 2026-1 `
  --baseline-before <diagnostics.baseline_before> `
  --baseline-after  <diagnostics.baseline_after> `
  --east  <east-campus.json>  --south <south-campus.json> `
  --shenzhen <shenzhen-campus.json> --zhuhai <zhuhai-campus.json> `
  --north <north-campus.json> `
  --campus-store <本地目录>/campus-acceptances.sqlite3 `
  --sqlite       <本地目录>/course-data.sqlite3 `
  --draft-inventory-out <本地目录>/inventory.draft.json
```

```text
→ 人工/Reviewer 批准 inventory.draft.json（out-of-band；工具无法证明任何批准）
```

```powershell
# 第二步：acceptance + 导入 + provider read-back + env 输出
python tools/prepare_real_case_a_runtime.py `
  --semester 2026-1 `
  --baseline-before <N> --baseline-after <N> `
  --east <east-campus.json> --south <south-campus.json> `
  --shenzhen <shenzhen-campus.json> --zhuhai <zhuhai-campus.json> --north <north-campus.json> `
  --campus-store <本地目录>/campus-acceptances.sqlite3 `
  --sqlite       <本地目录>/course-data.sqlite3 `
  --inventory <本地目录>/inventory.draft.json `
  --output-manifest <本地目录>/manifest.json `
  --env-out <本地目录>/runtime.env `
  --curriculum-case <已批准的 case-a.json>
```

期望最后一行是 `{"status": "ready", ...}`，其中 `provider_read_back.provider_offering_count`
等于 `acceptance.merged_offering_count`。

## 3. Runtime Startup Pack（R7）

### 3.1 环境变量（权威定义见 `backend/app/services/planning_runtime.py`）

**必填（四个）**

| 变量 | 期望值 | 说明 |
| --- | --- | --- |
| `APP_REAL_CASE_A_ENABLED` | `1` | 缺省或 `0` ⇒ `runtime_disabled`（503）；其它值 ⇒ `invalid_runtime_configuration`（503） |
| `APP_CASE_A_CURRICULUM_CASE_PATH` | 已批准的 Case A case JSON 的本地路径 | 必须是 `data_source=real`、目标版本 = Case A、`as_of_term` 与已批准决策集合一致的 case |
| `APP_COURSE_DATA_SQLITE_PATH` | 上面产出的 **Course Data SQLite**（建议绝对路径） | 该库必须包含本次 full-semester acceptance |
| `APP_COURSE_DATA_SEMESTER` | 例如 `2026-1` | 必须**精确等于** acceptance 绑定的学期 |
| `APP_COURSE_DATA_ACCEPTANCE_SHA256` | 64 位十六进制 | **full-semester manifest / acceptance digest**（见 §3.2） |

**可选**：无其它 runtime 变量；`VITE_*` 属前端侧（见 §4）。

### 3.2 三种 digest 的**明确**命名（⛔ 不要再笼统说 "SHA"）

| 名称 | 是什么 | 从哪里得到 | 用在哪里 |
| --- | --- | --- | --- |
| **raw campus bundle digest** | 某个校区 raw Capture Bundle 的**原始字节** SHA-256 | `validate` 输出的 `artifact_sha256`；也是该 campus acceptance 的 identity | 只用于 campus scope 绑定 / inventory 逐条比对；⛔ **不要**填进 `APP_COURSE_DATA_ACCEPTANCE_SHA256` |
| **campus acceptance digest** | 一个 campus acceptance 记录的 identity（= 该 artifact 的原始字节摘要） | `validate` 输出的 `campus_acceptance_sha256` | 只用于 full-semester acceptance 的 campus 绑定 |
| **full-semester manifest / acceptance digest** | canonical manifest 的 SHA-256（= full-semester acceptance identity） | `accept` 输出的 `manifest_sha256`（= 编排 CLI 的 `acceptance.manifest_sha256`） | ✅ **这个**才是 `APP_COURSE_DATA_ACCEPTANCE_SHA256` |

### 3.3 启动与探针

```powershell
cd backend
$env:APP_REAL_CASE_A_ENABLED="1"
$env:APP_CASE_A_CURRICULUM_CASE_PATH="<已批准 case-a.json>"
$env:APP_COURSE_DATA_SQLITE_PATH="<course-data.sqlite3>"
$env:APP_COURSE_DATA_SEMESTER="2026-1"
$env:APP_COURSE_DATA_ACCEPTANCE_SHA256="<full-semester manifest sha256>"
python -m uvicorn app.main:app --port 8000
```

```powershell
curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/api/v1/plan `
  -H 'Content-Type: application/json' `
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
# 已装配且数据一致 → 200；未装配 / 数据失效 → 503
```

### 3.4 失败矩阵（与当前实现一致；均由既有测试锁定）

| 情形 | 期望结果 | 判定类别 |
| --- | --- | --- |
| 成功启动（五变量齐全且一致） | `POST /api/v1/plan` → **200** + PlanResult | — |
| 缺 `APP_COURSE_DATA_SQLITE_PATH` / 文件不存在 | **503** `real_pipeline_not_configured` | `course_data_not_ready` |
| 库存在但没有该 acceptance 记录 | **503** | `course_data_not_ready` |
| `APP_COURSE_DATA_ACCEPTANCE_SHA256` 与库中 acceptance 不一致 | **503** | `course_data_not_ready` |
| campus-only 库（无 full_semester acceptance） | **503**（⛔ 不降级成 campus 数据） | `course_data_not_ready` |
| 库被篡改（行内容被替换） | 构造期即 **503**；请求期发现 ⇒ 同一个 **503** | readiness 失败 |
| acceptance 记录被删除（启动后） | 请求期 **503** | readiness 失败 |
| 陈旧行（某行 provenance 被后来的 campus import 覆盖） | **503**（⛔ 不返回陈旧行） | readiness 失败 |
| 请求 `semester` 与绑定学期不一致 | **503** | readiness 失败 |
| 与就绪性**无关**的内部错误（程序缺陷） | **500**（⛔ 不伪装成 503） | 未预期异常 |

⚠️ 真实 `POST /api/v1/plan` **不返回** `X-Data-Source` 头（接口面变更待裁定，见 decision notes）。

## 4. Frontend Real-run Checklist（R8）

### 4.1 启动

```powershell
cd frontend
$env:VITE_PLAN_API_ENABLED="true"      # 或 .env.local 里 VITE_PLAN_API_ENABLED=true
$env:VITE_PROXY_TARGET="http://127.0.0.1:8000"   # 默认值即此，可不设
npm run dev
```

- `VITE_API_BASE_URL` 留空（默认走同源代理 `/api` → `VITE_PROXY_TARGET`）；
  一旦填值则浏览器**直连**后端，需要后端自行开 CORS（本仓库未开）。

### 4.2 逐项核对（全部有自动化回归锁定：`frontend/tests/real-path-readiness.spec.ts`）

| # | 要核对的行为 | 期望 |
| --- | --- | --- |
| 1 | Real / Mock 明确区分 | Real 结果区 provenance = **Real**；基础展示数据（培养要求 / 教学班 / 偏好）仍标 **Mock** |
| 2 | Real 请求走真实 `/api/v1/plan` | 网络面板里只有 `POST /api/v1/plan`；⛔ 不出现 `/api/v1/mock/*` |
| 3 | 未装配（503） | 错误区标题"尚未完成装配" + HTTP 503 + 错误码 `real_pipeline_not_configured` |
| 4 | ⛔ 无 Real → Mock fallback | 503 之后页面**仍显示 Mock 规划结果**（来源标注仍为 Mock），plan 请求数不增加、Mock 请求数不增加 |
| 5 | 成功（200） | 展示 Real PlanResult（`objective_summary` 等来自响应） |
| 6 | provenance 展示 | 只有"规划结果"标 Real；⛔ 不把整页标成 Real |
| 7 | `meetings=[]` | 中性文案"当前数据中无排课信息"；⛔ 不出现"无冲突 / 无需上课 / 异步课程" |
| 8 | `remaining_capacity=null` | 显示破折号 `—`（⛔ 不显示 0 / null） |
| 9 | 未决事项为空 | "本次返回的未决事项为空（仅表示没有未决条目，不构成可执行性或排课结论）" |
| 10 | ⛔ 不宣称可直接执行 | 页面不出现"可直接执行 / 已选课 / 已成功选中" |
| 11 | ⛔ 不自造容量阈值 | 余量低也只按 `remaining / capacity` 原样显示 |
| 12 | generic 500 | 归为 server 类错误（⛔ 不写成"未装配"） |

### 4.3 自动化复核（无需人工判断）

```powershell
cd frontend && npm test          # 134 passed（9 文件；含 readiness 21）
cd frontend && npm run typecheck # vue-tsc --noEmit
cd frontend && npm run build
```

⛔ 本 Run **未**修改前端（Gate E 已 PASS；除非发现真实 readiness bug）。
