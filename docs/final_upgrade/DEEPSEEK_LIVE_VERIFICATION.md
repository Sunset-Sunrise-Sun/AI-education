# 真实 DeepSeek 在线验证说明（可直接执行）

> **当前状态：`BLOCKED — NEW DEEPSEEK_API_KEY NOT AVAILABLE`**
>
> 本轮任务执行时的实测结果（2026-10-09）：
>
> | 环境变量 | 进程 | 用户级 | 机器级 |
> | --- | --- | --- | --- |
> | `AI_PLANNING_ENABLED` | unset | unset | unset |
> | `DEEPSEEK_API_KEY` | **unset** | **unset** | **unset** |
> | `DEEPSEEK_BASE_URL` | unset | unset | unset |
> | `DEEPSEEK_MODEL` | unset | unset | unset |
>
> ⛔ 本文件**不包含**、⛔ 也不要求任何历史对话中出现过的旧密钥；
> 旧 `sk-` 前缀密钥已作废，**禁止使用**。
> ⛔ 在拿到新的有效密钥之前，本项目**不会**把注入式测试模型的结果说成真实 DeepSeek 调用。
>
> 因此本轮：**真实在线路径 = NOT VERIFIED**（如实标注，不冒充）。

---

## 1. 默认模型名核验（可在线确认，已完成）

`backend/.env.example` 的默认值是 `DEEPSEEK_MODEL=deepseek-flash`。

**核验结论：与供应商当前文档一致（已在线确认）。**

- 依据：DeepSeek 官方 *Models & Pricing* 页面把当前模型列为
  **`deepseek-flash`** 与 **`deepseek-v4-pro`**，并明确说明
  "Use `deepseek-flash` as the model name"；旧名 `deepseek-v4-flash` /
  `deepseek-v4-flash-vision-exp` 仍被接受，但对应模型已下线，请求由
  DeepSeek-V4.1-Flash 承接并按 Flash 价格计费。
  见 <https://api-docs.deepseek.com/quick_start/pricing>。
- 核验日期：2026-10-09。

⚠️ **边界（⛔ 不要把"名字对"当成"可用"）**：

- ⛔ 文档一致 ≠ 你的账号有权限、≠ 有余额、≠ 在线鉴权通过；
- ⛔ `GET /status` 返回 `live_model_available=true` **只**表示"开关已开 + 密钥已配置"，
  **不是**在线调用成功证明（这一点已写进 UI 的技术详情与 README）；
- 只有一次**受控** `POST /interpret` 真正返回 `generator_kind=deepseek_live`，
  才算在线路径可用。

建议在真实验证时顺手跑一次 `GET /models`（见 §4 步骤 2），
把**当次**返回的 `id` 列表记进报告——那才是你账号实际可用的模型清单。

---

## 2. 前置条件与安全要求

### 必须

1. **新密钥**，由负责人通过安全渠道提供；⛔ 不使用历史对话中的旧密钥；
2. 密钥只注入**后端进程环境**（服务器 / 本地终端会话）；
   ⛔ 不写入 `.env` 提交、⛔ 不写入前端、⛔ 不写入日志、⛔ 不贴进聊天或 issue；
3. 验证用的场景必须是**合成数据**（本项目已有合成夹具，见 §4）；
   ⛔ 不使用任何真实学生成绩、姓名、学号；
4. 明确本次预算与超时（服务端会夹到硬上界内）。

### 环境变量

```text
AI_PLANNING_ENABLED=true
DEEPSEEK_API_KEY=<由安全渠道注入，不写入任何文件>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash          # 或 /models 当次返回的 id

# 有界成本 / 延迟（服务端会夹到硬上界）
AI_PLANNING_MAX_OUTPUT_TOKENS=1200
AI_PLANNING_REQUEST_TIMEOUT=20
AI_PLANNING_MAX_CALLS_PER_REQUEST=3
AI_PLANNING_MAX_SESSIONS=200
AI_PLANNING_ADOPT_TTL_SECONDS=900
```

**成本控制建议**：`AI_PLANNING_MAX_CALLS_PER_REQUEST=3`（默认值）意味着
"一次 `/interpret` 最多 3 次模型调用"；把 `AI_PLANNING_REQUEST_TIMEOUT` 保持在 20 秒内。
本说明的完整流程最多产生 **3–4 次模型调用**（步骤 3 一次、步骤 5 一次、步骤 7 两次失败注入）。

### PowerShell 注入示例（⛔ 不要写进文件）

```powershell
# 只在当前终端会话内有效；关闭终端即消失
$env:AI_PLANNING_ENABLED = 'true'
$env:DEEPSEEK_MODEL = 'deepseek-flash'
$env:DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
$env:DEEPSEEK_API_KEY = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText
# ⛔ 不要 Echo、不要重定向到文件、不要放进 .env
```

> 若用 `Read-Host -AsSecureString` 不可用，也可以直接由负责人设置，
> 但⛔ 任何情况下都不要把密钥值粘进命令历史可保存的地方。

---

## 3. 验收标准（逐条可判定）

| # | 检查项 | 通过判据 | 失败判据 |
| --- | --- | --- | --- |
| 1 | 配置状态 | `GET /status` → `enabled=true`、`api_key_configured=true`、`live_model_available=true` | 任一为 false ⇒ 配置问题，**不是**在线验证 |
| 2 | 模型名有效 | `GET /models` 的 `id` 列表包含 `DEEPSEEK_MODEL` 的值 | 不含 ⇒ 模型名/权限问题，换名重试**一次** |
| 3 | 真实在线路径 | `POST /interpret` → HTTP 200 且 **`generator_kind="deepseek_live"`** | 返回 `test_double` / `unavailable` ⇒ **不算通过** |
| 4 | 结构校验 | 响应通过前端/后端契约解析；白名单外课程号**不出现**在 `parsed_intent` | 出现白名单外课程号 ⇒ 视为校验失效，**必须报告** |
| 5 | 模糊意图机制 | 不含学分数字的消息 ⇒ `can_confirm=false` 且有 `ambiguities` | `can_confirm=true` ⇒ 模型越权替用户决定，**必须报告** |
| 6 | 方案由 Planner 决定 | `/solve` 的候选与 `diff` 可由本地冻结 Planner 复算一致 | 候选含模型自创课程/班次 ⇒ **严重问题**，停止演示 |
| 7 | 失败不虚构 | 断开密钥 / 超时 / 注入非法输出 ⇒ 后端返回明确错误，⛔ 不返回编造结果 | 返回了可用候选 ⇒ **严重问题** |
| 8 | 不泄露 | 任何响应、日志、截图都不含密钥值 | 出现 ⇒ 立即停止并按安全事件处理 |

---

## 4. 执行步骤（受控、最小成本）

```powershell
# 0) 起后端（在已注入环境变量的同一终端里）
cd backend
$env:PYTHONUTF8 = '1'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 步骤 1 — 配置状态（不产生模型费用）

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/ai-planning/status
```

期望：`enabled=true` / `api_key_configured=true` / `live_model_available=true`。
**记录**：这三个布尔值与 `model`、`base_url`（⛔ 不记录密钥）。

### 步骤 2 — 模型清单（不产生模型费用）

```powershell
curl.exe -s -H "Authorization: Bearer $env:DEEPSEEK_API_KEY" https://api.deepseek.com/models
```

期望：`data[].id` 包含 `$env:DEEPSEEK_MODEL`。
**记录**：当次返回的 `id` 列表（这是"你这个账号能用什么"的唯一现场证据）。

### 步骤 3 — 真实 `/interpret`（**第 1 次模型调用**）

用**合成**的课程场景（不要用真实学生数据）：

```powershell
$body = @{
  context = @{
    semester = '2026-1'
    base_plan = @{
      status = 'partially_feasible'
      selected_classes = @(
        @{ course_id = '62001001'; class_id = '6200100120260101' },
        @{ course_id = '62001002'; class_id = '6200100220260101' }
      )
      changes = @(); risks = @(); unresolved = @()
      objective_summary = '合成场景：已选 2 个教学班'
    }
    makeup_tasks = @(
      @{ course_id = '62001001'; course_name = '离散数学'; credit = 3; status = 'required'; prerequisites = @() },
      @{ course_id = '62001002'; course_name = '数据结构与算法'; credit = 4; status = 'required'; prerequisites = @('62001001') },
      @{ course_id = '62004005'; course_name = '编译原理'; credit = 3; status = 'required'; prerequisites = @() }
    )
    course_offerings = @(
      @{ course_id = '62004005'; course_name = '编译原理'; class_id = '6200400520260101'; semester = '2026-1'; credit = 3;
         meetings = @(@{ weekday = 5; start_section = 3; end_section = 4; weeks = @(1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16) });
         data_source = 'mock' }
    )
    preference = @{ max_credit = 12; avoid_cross_campus = $false; preferred_courses = @(); avoid_times = @(); notes = $null }
  }
  user_message = '尽量别在周五上课，最多 12 学分'
} | ConvertTo-Json -Depth 8

curl.exe -s -X POST http://127.0.0.1:8000/api/v1/ai-planning/interpret `
  -H "Content-Type: application/json" -d $body
```

**通过判据**：HTTP 200、`generator_kind = "deepseek_live"`。
**记录**：`generator_kind`、`model_id`、`can_confirm`、`ambiguities` 数量、耗时、`token_usage_estimate`。

### 步骤 4 — 白名单与结构校验

检查步骤 3 的响应：

- `parsed_intent.hard_constraints` / `soft_preferences` / `locked_courses` 里的课程号**只能**来自
  请求中给出的课程号；出现别的一律视为**校验失效**；
- `can_confirm` 与歧义一一对应；
- 前端契约解析器（`frontend/src/api/aiPlanningContract.ts`）能无异常解析该响应。

### 步骤 5 — 模糊意图（**第 2 次模型调用**）

把 `user_message` 换成不含数字的：

```text
这学期太累，少上一点课就行
```

**通过判据**：`can_confirm = false`，且 `ambiguities` 里有"缺少学分上限证据"这类条目。
⛔ 若 `can_confirm = true`，说明模型替用户默认了一个上限 —— 属**必须报告**的问题。

### 步骤 6 — `/solve` 与 `/adopt`（**不产生模型调用**）

用步骤 3 的 `intent_id`（在面板上点第一次确认，或直接调用）：

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/ai-planning/solve `
  -H "Content-Type: application/json" `
  -d '{"intent_id":"<来自步骤 3>","confirm":true,"semester":"2026-1"}'
```

**通过判据**：
- `status = "candidate_ready"` 时，候选里的每个 `(course_id, class_id)` 都能在**请求给出的 offerings** 里找到；
- 候选与本地冻结 Planner 对同一输入的输出**一致**（说明方案是规则算出来的，不是模型编的）；
- `no_feasible_candidate` 时 **没有** adopt 入口。

### 步骤 7 — 失败不虚构（**2 次注入失败**）

| 注入 | 期望 |
| --- | --- |
| 把 `DEEPSEEK_API_KEY` 改成无效值后重启，再 `/interpret` | 返回明确的鉴权/上游错误；⛔ 不返回候选、⛔ 不 fallback 到 fixture |
| 把 `AI_PLANNING_REQUEST_TIMEOUT` 设为 `1`（极小）后重启，再 `/interpret` | 返回超时类错误；⛔ 不返回编造结果 |

**通过判据**：两种情况都"明确失败"，且页面显示真实错误类型与可操作下一步。

### 步骤 8 — 记录（⛔ 不含密钥与个人信息）

```text
日期：
分支 / commit：
模型名（当次 /models 返回值）：
/status：enabled=… api_key_configured=… live_model_available=…
步骤 3：HTTP 状态 / generator_kind / model_id / can_confirm / 歧义数 / 耗时 / token 估计
步骤 5：can_confirm / 歧义类型
步骤 6：solve status / 候选是否可在 offerings 中找到 / 与本地 Planner 是否一致
步骤 7：两种注入的错误类型与 HTTP 状态
结论：PASS / FAIL（逐条对应 §3）
```

---

## 5. 失败处理

| 现象 | 分类 | 处置 |
| --- | --- | --- |
| `/status` 的 `enabled=false` | 配置 | 检查 `AI_PLANNING_ENABLED` 是否真的注入到**后端进程** |
| `api_key_configured=false` | 配置 | 密钥没进到后端进程；⛔ 不要为了"跑通"把密钥写进仓库文件 |
| `/models` 不含目标模型 | 权限/名字 | 换用当次返回的 id，重试**一次**；仍失败则记录并停止 |
| `/interpret` 返回 `generator_kind=test_double` | 严重 | 说明注入的仍是测试替身；**本次不算在线验证**，如实标注 |
| `/interpret` 返回 `unavailable` | 上游 | 记录 HTTP 状态与错误类型；检查余额/限流/网络出口 |
| 401/403 | 鉴权 | 密钥无效或无权限；**停止**，向负责人索取新密钥，⛔ 不要重试刷次数 |
| 429 | 限流 | 降低调用频率；本轮直接停止，不重试 |
| 超时 | 网络/上游 | 记录耗时；确认后端返回的是超时错误而**不是**编造结果 |
| 模型输出含白名单外课程号 | **严重** | 立即停止演示；按"校验失效"上报（这属安全/正确性问题，不是体验问题） |
| 响应/日志/截图里出现密钥 | **安全事件** | 立即停止、撤销该密钥、按安全流程处理；⛔ 不要把密钥内容贴进任何记录 |

---

## 6. 与演示口径的关系

在真实在线验证**通过之前**，所有演示必须使用以下口径（与 `DEMO_SCRIPT.md` 一致）：

- 页面顶部 Mock 提示、`仅前端预览` 提示、`规则模板（非 AI）` 标签必须**原样展示**；
- AI 调整若走测试替身，必须显示"测试替身模型（不是线上模型）"；
- 抽屉"技术详情"里的 `live_model_available` 必须与
  "配置就绪 ≠ 在线调用成功"的说明**同时**出现（已实现，见
  `frontend/src/components/ai/drawerCapability.ts`）；
- ⛔ 不得用测试替身结果冒充真实 DeepSeek 在线调用。
