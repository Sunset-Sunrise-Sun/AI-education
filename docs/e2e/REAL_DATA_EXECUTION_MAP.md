# Real Data Execution Map（R1）· Five-shard Operation Pack（R2）· Synthetic Preflight（R5）

> 本文件是**当前实现**的审计结果（⛔ 不引用旧 worklog 作为结论）。
> 每个步骤都给出：command / input / output / expected invariant / failure mode / 是否需人工。
> ⛔ 不接真实学校网络、⛔ 不提交真实 artifact、⛔ 不存凭据、⛔ 不弱化任何验收规则。
> 当前等级：**LEVEL 0**（真实数据尚未采集）；R5 的 preflight 属 **LEVEL 1**（合成，⛔ 不是 Real E2E）。

## 0. 权威来源（本文件的每个事实都可在这些文件里核对）

| 事实 | 权威文件 |
| --- | --- |
| 已批准五校区 slug / `openingSchoolNumber` | `backend/app/course_data/full_semester_acceptance.py` → `APPROVED_FULL_SEMESTER_SHARDS`（并由测试与 collector 表交叉锁定） |
| 采集器入口与输出 | `tools/sysu_course_offering_collector.js`（`collectSharded` / `toShardJson` / `toDiagnosticsJson`） |
| 单校区校验 + campus acceptance + 导入 | `tools/validate_course_data_artifact.py` |
| full-semester acceptance + manifest + 导入 + read-back | `tools/accept_full_semester_course_data.py` |
| 编排（一条命令跑完整条链） | `tools/prepare_real_case_a_runtime.py` |
| runtime 装配与 env 变量 | `backend/app/services/planning_runtime.py` |
| Provider 读取与 trust chain | `backend/app/course_data/store_provider.py`、`store.py` |
| 前端 Real 入口与开关 | `frontend/src/config.ts`、`frontend/src/api/plan.ts`、`frontend/vite.config.ts` |
| 等级定义 | `docs/e2e/REAL_CASE_A_ACCEPTANCE.md` |

## 1. 执行链（capture → validate → accept → import → configure → start → probe → frontend）

```json
{
  "chain_version": 1,
  "semester_placeholder": "<e.g. 2026-1>",
  "steps": [
    {
      "id": "capture",
      "actor": "user",
      "tool": "tools/sysu_course_offering_collector.js",
      "command": "await window.XuehangSysuCollector.collectSharded({ semester: \"<semester>\", maxPages: 20 })",
      "output_command": "window.XuehangSysuCollector.toShardJson(sharded, \"东校园\")  ×5  +  toDiagnosticsJson(sharded)",
      "inputs": [
        "用户自己的 SYSU 已登录浏览器会话（含 MFA）",
        "已批准的五校区 openingSchoolNumber 表（脚本内置）"
      ],
      "outputs": [
        "5 个各校区的 raw Capture Bundle JSON",
        "1 个 diagnostics JSON（baseline_before/after + 各 shard total）"
      ],
      "invariant": "请求顺序 baseline → 五个 shard（串行，已批准顺序）→ baseline；diagnostics 不进入任何 raw bundle",
      "failure_mode": "任一页非 200 / 结构不符 ⇒ 整个 run fail closed（⛔ 不重试风暴、⛔ 不降级）；North 深分页历史问题见 North 诊断计划",
      "user_interaction": "required"
    },
    {
      "id": "validate",
      "actor": "tool",
      "tool": "tools/validate_course_data_artifact.py",
      "command": "python tools/validate_course_data_artifact.py --bundle <shard.json> --expected-semester <semester> --scope-id <openingSchoolNumber> --source capture://sysu/<semester>/campus/<openingSchoolNumber> --sqlite <campus-store>",
      "inputs": [
        "一个校区的 raw bundle",
        "已批准校区号（决定 campus scope 与 canonical source label）"
      ],
      "outputs": [
        "聚合 JSON：artifact_sha256 / loaded_count / reported_total / offering_count / snapshot.is_complete / campus_acceptance_sha256"
      ],
      "invariant": "exact-byte digest 与解析吃同一批 bytes；`complete` 只在**该校区 scope** 内成立（campus complete ≠ full semester complete）",
      "failure_mode": "exit 2 参数 / 3 artifact 读取 / 4 scope 或 source label / 5 normalization / 6 incomplete / 7 sqlite / 8 empty —— 全部 fail closed",
      "user_interaction": "none",
      "user_interaction_note": "由编排 CLI 调用"
    },
    {
      "id": "campus_acceptance",
      "actor": "tool",
      "tool": "tools/validate_course_data_artifact.py",
      "command": "（同上，`--sqlite <campus-store>` 触发导入）",
      "inputs": [
        "五份 raw bundle（逐校区串行）"
      ],
      "outputs": [
        "campus store 中五条 campus acceptance（identity = 该 artifact 的 raw bytes digest，scope = campus/<number>）"
      ],
      "invariant": "每个校区一条独立 acceptance；同一 artifact 重复导入幂等（unchanged）；同 scope 不同字节产生**另一条**记录（后续由 inventory 摘要强制绑定）",
      "failure_mode": "任一校区失败 ⇒ 编排 CLI 立即停止（exit 4），⛔ 不继续 acceptance",
      "user_interaction": "none"
    },
    {
      "id": "draft_inventory",
      "actor": "tool + user",
      "tool": "tools/prepare_real_case_a_runtime.py",
      "command": "python tools/prepare_real_case_a_runtime.py ... --draft-inventory-out <inventory.draft.json>",
      "inputs": [
        "五份 raw bundle",
        "--baseline-before/--baseline-after（来自 diagnostics）"
      ],
      "outputs": [
        "canonical inventory **草稿**（semester + 五条 shard_id/openingSchoolNumber/raw_bundle_sha256）"
      ],
      "invariant": "草稿只是文档 identity；⛔ 工具无法证明任何 inventory 被批准（`inventory_sha256_semantics = draft_document_identity_not_an_approval`）",
      "failure_mode": "任一 bundle 不可读 / 结构不符 ⇒ exit 5（底层 category 原样保留）",
      "user_interaction": "required",
      "user_interaction_note": "人工**批准** inventory 草稿：out-of-band 审查后作为 `--inventory` 交回"
    },
    {
      "id": "handoff",
      "actor": "tool + user",
      "tool": "tools/prepare_real_case_a_runtime.py",
      "command": "python tools/prepare_real_case_a_runtime.py ... --draft-handoff-out <handoff.draft.json>",
      "inputs": [
        "五份 raw bundle（只读其 SHA-256）",
        "diagnostics（可选：--capture-window-start/--capture-window-end、--collector-commit）"
      ],
      "outputs": [
        "real-capture handoff 草稿（只有安全元数据：semester / 五校区号 / 五个 raw bundle SHA-256 / baseline / 采集窗口 / collector commit / 本地 session id / authorized_user_session）"
      ],
      "invariant": "handoff 只含 digest / 计数 / 枚举 / 时间；⛔ 不含凭据 / 会话标识 / auth header / 原始响应体 / 学生个人数据；未知键一律拒绝",
      "failure_mode": "handoff 未被批准（draft/synthetic）、semester 不符、shard 集合不是已批准五校区、digest 与磁盘或 acceptance 不符、出现未知键 ⇒ fail closed（exit 9）",
      "user_interaction": "required",
      "user_interaction_note": "人工批准：把 handoff_state 改成 approved 并填 approved_by/approved_at（唯一的必要人工编辑；SHA 由工具计算）"
    },
    {
      "id": "accept",
      "actor": "tool",
      "tool": "tools/accept_full_semester_course_data.py",
      "command": "python tools/accept_full_semester_course_data.py --semester <semester> --baseline-before <N> --baseline-after <N> --east <e> --south <s> --shenzhen <sz> --zhuhai <z> --north <n> --inventory <approved.json> --campus-store <campus-store> [--sqlite <new.sqlite3>] [--output-manifest <manifest.json>]",
      "inputs": [
        "五份 raw bundle",
        "**已批准** inventory",
        "campus store（五条 campus acceptance）",
        "baseline before/after（诊断证据，⛔ 不是快照）"
      ],
      "outputs": [
        "full-semester acceptance（manifest SHA-256 = acceptance identity）+ 可选 canonical manifest 文件"
      ],
      "invariant": "exact five-shard；Σ shard reported_total == baseline 且 baseline_before == baseline_after；每 shard 与 inventory 摘要、campus 记录逐项一致；merged offering set digest 可重算",
      "failure_mode": "exit 4 baseline / 5 shard set / 6 completeness / 8 manifest / 9 inventory / 10 campus binding —— 全部 fail closed；⛔ 不跳过 North、⛔ 不把四校区当 full_semester",
      "user_interaction": "none"
    },
    {
      "id": "import",
      "actor": "tool",
      "tool": "tools/accept_full_semester_course_data.py",
      "command": "（同上，`--sqlite <new.sqlite3>`）",
      "inputs": [
        "acceptance 成功后的同一批 rows"
      ],
      "outputs": [
        "新的本地 Course Data SQLite：course_data_import + course_data_acceptance（canonical manifest）+ membership + rows"
      ],
      "invariant": "acceptance 与 rows 在**同一事务**落库；read-back 必须读回同一条 acceptance（same manifest SHA）；immutable acceptance：同 identity 幂等、不同内容 fail closed",
      "failure_mode": "exit 7 sqlite；⛔ acceptance 失败时**不**导入（编排 CLI 断言库未产生）",
      "user_interaction": "none"
    },
    {
      "id": "provenance_verification",
      "actor": "tool",
      "tool": "tools/prepare_real_case_a_runtime.py",
      "command": "（编排 CLI 在导入后自动执行 provider 级 read-back）",
      "inputs": [
        "新 SQLite",
        "manifest SHA-256",
        "semester"
      ],
      "outputs": [
        "provider_offering_count / readback_member_count / readback_offering_set_sha256 / provider_acceptance_sha256"
      ],
      "invariant": "`StoreBackedCourseDataProvider.get_course_offerings()` 返回的行数 == merged_offering_count == membership 行数；trust chain（configured SHA → stored canonical manifest → 重算 SHA → 语义字段 → 集合 digest → 逐行 digest）全部通过",
      "failure_mode": "exit 6 provider_readback（领域失败）；⛔ 其它异常原样上抛（程序缺陷不伪装成「未就绪」）",
      "user_interaction": "none"
    },
    {
      "id": "configure",
      "actor": "tool + user",
      "tool": "tools/prepare_real_case_a_runtime.py",
      "command": "python tools/prepare_real_case_a_runtime.py ... --env-out <runtime.env>",
      "inputs": [
        "SQLite 路径（绝对路径）",
        "semester",
        "manifest SHA-256",
        "（可选）已批准的 curriculum case 路径"
      ],
      "outputs": [
        "APP_REAL_CASE_A_ENABLED=1 / APP_COURSE_DATA_SQLITE_PATH / APP_COURSE_DATA_SEMESTER / APP_COURSE_DATA_ACCEPTANCE_SHA256（+ 可选 APP_CASE_A_CURRICULUM_CASE_PATH）"
      ],
      "invariant": "`APP_COURSE_DATA_ACCEPTANCE_SHA256` **必须**是 full-semester manifest/acceptance digest（⛔ 不是 campus artifact digest）",
      "failure_mode": "env 文件已存在且未 `--force` ⇒ exit 7（⛔ 不静默覆盖）",
      "user_interaction": "required",
      "user_interaction_note": "把 env 值放进 backend 启动环境；curriculum case 路径由用户提供"
    },
    {
      "id": "start",
      "actor": "user",
      "tool": "backend/app/main.py",
      "command": "cd backend && python -m uvicorn app.main:app --port 8000",
      "inputs": [
        "上面五个环境变量（含已批准的 curriculum case）"
      ],
      "outputs": [
        "运行中的 FastAPI（每次请求重新装配 runtime，⛔ 不缓存 orchestrator）"
      ],
      "invariant": "五个变量齐全且一致 ⇒ `ready`；任一缺失 / 不一致 ⇒ orchestrator=None ⇒ 503",
      "failure_mode": "未装配或 acceptance 失效 ⇒ `POST /api/v1/plan` 503 `real_pipeline_not_configured`；未预期内部异常 ⇒ 500",
      "user_interaction": "required",
      "user_interaction_note": "启动进程"
    },
    {
      "id": "probe",
      "actor": "user",
      "tool": "backend/app/api/plan.py",
      "command": "curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/api/v1/plan -H 'Content-Type: application/json' -d '{\"semester\":\"<semester>\",\"current_schedule\":[],\"preference\":{}}'",
      "inputs": [
        "运行中的 backend",
        "semester 必须等于 acceptance 绑定的学期"
      ],
      "outputs": [
        "HTTP 200 + PlanResult（真实数据）或 503 real_pipeline_not_configured"
      ],
      "invariant": "真实数据 + 已装配 ⇒ 200；`selected_classes` 只能来自被接受的行；⛔ 不回退 Mock、⛔ 不返回空列表代替错误",
      "failure_mode": "503 = readiness/领域失败；500 = 未预期内部错误；422 = 请求体不符合公共契约",
      "user_interaction": "required",
      "user_interaction_note": "执行探针"
    },
    {
      "id": "frontend",
      "actor": "user",
      "tool": "frontend/src/api/plan.ts",
      "command": "cd frontend && VITE_PLAN_API_ENABLED=true npm run dev  （代理目标默认 http://127.0.0.1:8000）",
      "inputs": [
        "同一份 backend",
        "`VITE_PLAN_API_ENABLED=true`"
      ],
      "outputs": [
        "前端 Real 结果区（provenance=Real；基础展示数据仍标 Mock）"
      ],
      "invariant": "Real 请求只走 `/api/v1/plan`；⛔ 失败不回退 Mock；⛔ 不重算冲突 / 可执行性",
      "failure_mode": "503 ⇒ 明确「尚未完成装配」错误态；500 ⇒ server 态；⛔ 二者都不显示 Mock 结果",
      "user_interaction": "required",
      "user_interaction_note": "浏览器验证"
    },
    {
      "id": "evidence",
      "actor": "user",
      "tool": "docs/e2e/REAL_E2E_EVIDENCE_PROTOCOL.md",
      "command": "按证据协议收集 LEVEL2 / LEVEL3 证据（digest / 计数 / 状态码 / 枚举 / 布尔）",
      "inputs": [
        "编排 CLI 的 JSON 输出（acceptance + provider read-back + real_source_provenance + level2_eligible）",
        "后端探针状态码",
        "前端截图/核对清单"
      ],
      "outputs": [
        "LEVEL2 证据包（后端专有）",
        "LEVEL3 证据包（+ 前端链路）"
      ],
      "invariant": "LEVEL2 必须 `level2_eligible == true`（= approved real-capture handoff 的五个 digest 与 campus acceptance 输入逐条一致）；⛔ 证据不含个人数据；⛔ 跳级不允许",
      "failure_mode": "无 approved handoff / handoff 与 acceptance 不匹配 ⇒ `level2_eligible = false` ⇒ LEVEL2 不能通过（LEVEL3 继承）",
      "user_interaction": "required"
    }
  ]
}
```

## 2. Five-shard Operation Pack（R2）

已批准 inventory（**权威来源 = 代码常量**，本表只是它的可读副本）：

| shard slug | 校区 | `openingSchoolNumber` | 操作 |
| --- | --- | --- | --- |
| `east-campus` | 东校园 | `5063559` | 采集 |
| `south-campus` | 南校园 | `5062201` | 采集 |
| `shenzhen-campus` | 深圳校区 | `333291143` | 采集 |
| `zhuhai-campus` | 珠海校区 | `5062203` | 采集 |
| `north-campus` | 北校园 | `5062202` | **suspended**（见 §5） |

历史观测基线（⛔ **仅作参考，不得硬编码为真值**）：

```text
East 1071 · North 405 · South 2898 · Shenzhen 1171 · Zhuhai 1335 · Total 6880
```

⚠️ 正式 acceptance **必须**使用本次采集 diagnostics 给出的 `baseline_before` / `baseline_after`：
计数随选课窗口变化，写死历史数字会让 `shard_coverage_mismatch` / `snapshot_window_unstable` 直接 fail closed
（这是**特性**：它防止把变化中的快照当成一次一致观测）。

North 处理规则（⛔ 不可协商）：

```text
⛔ 不跳过 North（五 shard 是 exact 集合，缺一 ⇒ missing_shard，fail closed）
⛔ 不合成 North（synthetic 数据永不进入真实 acceptance）
⛔ 不推断 North 完整性
⛔ 不把"四校区 complete"当作 full_semester complete
⛔ 不放宽任何验收规则来绕过 North
```

## 3. 一条命令跑完整条链（编排 CLI，可选但推荐）

```powershell
# 第一步：逐校区 campus acceptance + inventory 草稿（不做 acceptance）
python tools/prepare_real_case_a_runtime.py `
  --semester 2026-1 `
  --baseline-before <诊断 N> --baseline-after <诊断 N> `
  --east <east.json> --south <south.json> --shenzhen <shenzhen.json> `
  --zhuhai <zhuhai.json> --north <north.json> `
  --campus-store <campus-acceptances.sqlite3> --sqlite <course-data.sqlite3> `
  --draft-inventory-out <inventory.draft.json>

# 第二步（人工批准草稿之后）：acceptance + 导入 + read-back + env
python tools/prepare_real_case_a_runtime.py `
  --semester 2026-1 --baseline-before <N> --baseline-after <N> `
  --east <east.json> --south <south.json> --shenzhen <shenzhen.json> `
  --zhuhai <zhuhai.json> --north <north.json> `
  --campus-store <campus-acceptances.sqlite3> --sqlite <course-data.sqlite3> `
  --inventory <inventory.draft.json> --output-manifest <manifest.json> `
  --env-out <runtime.env> --curriculum-case <approved case-a.json>
```

安全行为：

- 目标 `--sqlite` **已存在** ⇒ 默认拒绝（exit 3）；显式 `--allow-existing-store` 才复用，
  且 `immutable acceptance` 规则照旧（同 identity 幂等 / 不同内容 fail closed）；
- `--campus-store` 是中间产物，可被两步流程复用（campus 记录最终由 inventory 摘要强制绑定）；
- `--env-out` 已存在 ⇒ 默认拒绝（exit 7），需 `--force`；
- ⛔ 不自动创建父目录（与 store 层"⛔ 不猜路径"一致）。

退出码：`0` ok · `2` 参数 · `3` 目标库已存在 · `4` campus 阶段 · `5` acceptance 阶段 · `6` provider read-back · `7` env 输出。

## 4. Synthetic Preflight（R5，LEVEL 1）

在任何真实采集**之前**，先用合成五 shard 证明整条链可用：

```powershell
python tools/prepare_real_case_a_runtime.py --preflight            # 默认跑完即清理临时目录
python tools/prepare_real_case_a_runtime.py --preflight --keep-dir # 保留产物供检查
```

它做的事情（全部走**真实**代码路径）：

```text
5 个合成 campus bundle（semester=2099-1，⛔ 不是真实学期）
  → 逐校区 validate + campus acceptance + 导入
  → inventory 草稿 → 用它做 full-semester acceptance（+ manifest）
  → 导入 SQLite
  → StoreBackedCourseDataProvider read-back（行数 == membership == merged_offering_count）
  → 打印 runtime env 值
```

输出 JSON 带 `"level": "LEVEL1-synthetic-preflight"` 与 `"synthetic": true`，
并明确写 `"NOT Real E2E"`；⛔ 不得据此声称 LEVEL 2 / LEVEL 3。

Runtime + API + 前端那一段（LEVEL 1 的剩余部分）用既有回归命令复核：

```powershell
cd backend && python -m pytest tests/test_synthetic_production_e2e.py -q   # runtime → API → PlanResult（合成）
cd frontend && npm test                                                    # 前端 readiness（含 503 / 无 Mock fallback）
```

## 5. 与 North 的关系（摘要）

North 仍 **suspended**：五 shard 缺一不可，因此**真实 full-semester acceptance 在 North 解决前不可产出**。
North 的保守诊断计划见 `docs/e2e/READINESS_DECISION_NOTES.md` §2。
⛔ 本文件所在分支**未**访问真实网络，也**未**采集任何真实数据。
