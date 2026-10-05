# 比赛 Demo 运行手册（Demo Runbook）

> **用途**：比赛 / 现场演示时的**启动顺序、检查点与应急策略**。
> 目标：**演示过程不说假话** —— Mock 就是 Mock，Real 就是 Real。
>
> 状态：**验收标准已准备**。⛔ 本文件不声明 Real E2E 已完成。
> 当前 main 的运行时状态是 **LEVEL 0**（`/api/v1/plan` → 503），
> 因此**默认演示方案是 Mock Demo**，见 §7。

---

## 0. 一句话策略

```text
Real 可用 → 展示 Real，并明确"基础演示数据仍为 Mock"
Real 不可用 → 明确切回 Mock Demo，provenance 显示 Mock
⛔ 任何情况下都不把 Mock 说成 Real
```

---

## 1. 赛前启动顺序

⛔ **严格按顺序**，每步通过后再做下一步。

```text
① 后端启动        → python -m uvicorn app.main:app --reload   （在 backend/ 目录）
② 后端健康检查    → GET /health
③ 后端 Mock 自检  → GET /api/v1/mock/demo（应 200 且带 X-Data-Source: mock）
④ 前端启动        → npm run dev（开发）或 npm run build && npm run preview（演示）
⑤ 页面加载检查    → 打开页面，确认数据出现、无报错
⑥ provenance 检查 → 确认页面显示的来源文案与真实情况一致
⑦ （可选）Real 冒烟 → 仅在 runtime 已装配时执行 §5
```

### 具体命令

```bash
# ① 后端（工作目录：backend/）
python -m uvicorn app.main:app --reload
# 监听 http://127.0.0.1:8000

# ④ 前端（工作目录：frontend/）
npm install          # 首次
npm run dev          # http://127.0.0.1:5173
# 或演示用构建产物：
npm run build && npm run preview   # http://127.0.0.1:4173
```

⚠️ 前端**不直连**后端：`/api` 由 Vite 代转发到 `http://127.0.0.1:8000`
（可用 `VITE_PROXY_TARGET` 覆盖）。因此**必须**通过 Vite 的 dev/preview 地址打开页面，
⛔ 不要直接双击 `dist/index.html`。

---

## 2. backend health check

```bash
curl -s http://127.0.0.1:8000/health
```

期望：`200` + JSON（服务存活）。同一路由也挂在 `/api/v1/health`。

---

## 3. 后端 Mock 通道自检

```bash
curl -i -s http://127.0.0.1:8000/api/v1/mock/demo | head -20
```

必须确认：

- 状态 `200`；
- 响应头含 **`X-Data-Source: mock`**；
- body 含四类对象：`makeup_tasks` / `course_offerings` / `preference` / `plan_result`。

⚠️ 后端**启动时会按公共 JSON Schema 自检** Mock 数据；
若 Mock 数据损坏，进程会**直接启动失败**（这是有意的，避免带坏数据演示）。

---

## 4. 前端启动与 `VITE_PLAN_API_ENABLED`

| 取值 | 行为 |
|---|---|
| 未设置 / 非 `true` | Real 提交按钮 **disabled**；⛔ 不会发 `/api/v1/plan`；**推荐比赛默认** |
| `true` | Real 提交按钮开放（仍需输入合法 + provenance 合法） |

设置方式（前端目录下）：

```bash
# frontend/.env.local
VITE_PLAN_API_ENABLED=true
```

⚠️ **仅**控制 Real submit 是否开放：
⛔ 不改变 Mock 数据获取、⛔ 不触发任何自动请求、⛔ 不改变 provenance gate。

> ⚠️ **已知文档缺口（action item，非本轮修改范围）**：
> `VITE_PLAN_API_ENABLED` **未**列在 `frontend/.env.example` 中
> （代码 `frontend/src/config.ts` 说明应写进 `.env.local`）。
> 建议后续补充到 `.env.example`；本轮不动 frontend。

---

## 5. runtime 是否已加载 / complete snapshot 是否存在

### 5.1 runtime 是否已装配

```bash
curl -i -s -X POST http://127.0.0.1:8000/api/v1/plan \
  -H 'Content-Type: application/json' \
  -d '{"semester":"2026-1","current_schedule":[],"preference":{}}'
```

| 观察 | 含义 |
|---|---|
| **503** + `real_pipeline_not_configured` | **runtime 未装配** → 按 §7 切回 Mock Demo |
| **200** + `PlanResult` | runtime 已装配 → 仍需确认数据来源（§5.2 / checklist） |

⛔ 503 **不是故障**，是"尚未装配"这一**正确状态**。
⛔ **禁止**因为看到 503 就改用 Mock 数据去"充当"Real 结果。

### 5.2 complete snapshot 是否存在

按 `COURSE_DATA_SNAPSHOT_CHECKLIST.md` 逐项确认，核心是：

```text
semester == "2026-1"
reported_total 存在
loaded_count == reported_total
is_complete == true
不是 partial 两页样本
不含 mock:// source
```

⛔ 任一不满足 → **不得**装配进 Real pipeline（fail closed）。

---

## 6. 页面 provenance 检查（演示前最后一道）

打开页面后逐项确认：

| 检查点 | 期望 |
|---|---|
| 顶部数据来源标头 | 显示后端 `X-Data-Source` 的实际取值（Mock 通道为 `mock`） |
| 区块 Mock 标记 | 培养要求评估 / 教学班 / 偏好 等区块带 `Mock` 标记 |
| 规划结果来源 | 未提交过 Real ⇒ **`规划结果来源：Mock`** |
| 提交过 Real 且成功 | **`规划结果来源：Real`**，且**基础数据仍标 Mock** |
| ⛔ 禁止出现的说法 | "当前数据模式：Real" 这类**全局**说法 |

---

## 7. 🚨 如果 Real runtime 临场不可用怎么办？

**这是最可能发生的情况**（当前 main 即如此）。正确处理：

```text
① 明确切回 Mock Demo（不要尝试隐藏或绕过）
② 页面 provenance 必须显示 Mock
③ 口头 / 文案说明："当前展示的是 Mock 演示通道数据，真实规划运行时尚未装配"
④ ⛔ 绝不说成 Real；⛔ 绝不用 Mock 结果冒充 Real 结果
```

**具体做法**：

1. **不要**把 `VITE_PLAN_API_ENABLED` 打开去"试一下"—— 打开后按钮可用但点击只会得到 503；
   演示中更干净的做法是**保持默认关闭**，按钮显示为不可用并解释原因；
2. 页面会显示"**真实规划运行时尚未完成装配**"以及"当前页面可继续使用 Mock Demo"——
   **这正是要展示的内容**：说明我们的隔离设计是诚实的；
3. 演示话术建议：
   > "真实规划链路目前尚未装配（后端返回 503 `real_pipeline_not_configured`）。
   > 页面**明确显示**这一点，并且**不会**把 Mock 数据伪装成真实结果。
   > 我们现在展示的是 Mock 演示通道的完整交互。"

**绝对禁止**（会被验收判为失败）：

- ⛔ 把 Mock 的 `PlanResult` 说成 Real 结果；
- ⛔ 手工改页面文案把 Mock 标成 Real；
- ⛔ 用"看起来像真实数据"的 synthetic 产物声称 Real E2E 已通过。

---

## 8. 演示后 / 收尾

- 关闭后端与前端进程；
- 确认**没有**真实材料被写进仓库：`git status` 应干净（真实 capture bundle / 成绩单 / 培养方案 docx 均不入 public Git）；
- 若演示中产生了 Real 结果，记录证据（响应头 + provenance 截图）以备验收。

---

## 9. 常见故障速查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 页面一直 loading | 后端未启动 / 端口不是 8000 | 起后端；确认 `VITE_PROXY_TARGET` |
| 页面报"后端接口连接异常" | 未通过 Vite dev/preview 打开 | 用 `http://127.0.0.1:5173` 或 `:4173` |
| Real 按钮是灰的 | `VITE_PLAN_API_ENABLED` 未开 | 这是**预期默认行为**，见 §4 |
| 点 Real 得到 503 | runtime 未装配 | **预期行为**，见 §7 |
| `127.0.0.1` 连不上但 `localhost` 可以 | Node 在 Windows 上优先解析 IPv6 | Vite 已显式绑 `127.0.0.1`，请统一用 `127.0.0.1` |

---

## 10. 相关文档

- `docs/e2e/REAL_CASE_A_ACCEPTANCE.md` —— Real E2E 正式定义与验收等级
- `docs/e2e/COURSE_DATA_SNAPSHOT_CHECKLIST.md` —— 快照验收清单 + provenance OPEN ITEM
- `docs/e2e/REAL_E2E_TEST_MATRIX.md` —— 验收矩阵
- `frontend/README.md`、`backend/README.md` —— 各自运行说明
