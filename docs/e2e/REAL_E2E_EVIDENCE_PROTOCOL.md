# LEVEL 2 / LEVEL 3 Evidence Protocol（R6）

> 等级定义见 `docs/e2e/REAL_CASE_A_ACCEPTANCE.md` §2（⛔ 不得跳级）。
> ⛔ 本文件**不**声称 LEVEL 2 / LEVEL 3 已经达到；它只定义**需要哪些证据**。
> ⛔ 证据中**不得**包含任何真实学生个人数据（姓名 / 学号 / 成绩 / GPA / 逐行原始记录）。
> 证据里可以出现：**摘要值、计数、枚举、状态码、布尔判定**。

## 0. 一般规则

```text
✅ 允许：SHA-256 digest · 计数（loaded/reported/merged）· semester · shard slug + openingSchoolNumber
        · HTTP 状态码 · 枚举（status / category / scope_kind）· 命令与版本 · 布尔判定
⛔ 禁止：任何课程逐行内容 · 学生姓名 / 学号 / 成绩 / GPA · 原始 worksheet / cell dump
        · cookie / token / 会话内容 · 本地绝对路径（可写成 <local>/... ）
```

所有证据必须**可重跑**：命令 + 期望输出形状 + 实际观测（截断到摘要级）。

---

## 1. LEVEL 2 证据清单（Real data path verified，后端专有）

> ⛔ **HARD GATE — REAL-SOURCE-PROVENANCE**（不满足则 LEVEL 2 **不能通过**，LEVEL 3 继承）：

```text
必须全部成立：
 (1) 存在**已批准**的 real-capture handoff（`handoff_state = "approved"` 且 `synthetic = false`）
 (2) handoff.semester == acceptance.semester
 (3) handoff 恰好包含**已批准的五个 shard**（shard_id + openingSchoolNumber 逐条一致）
 (4) handoff 的五个 raw bundle SHA-256 == 本次 acceptance 消费的五个 campus artifact digest
 (5) handoff 标记为 approved / non-synthetic（draft 与 synthetic 一律不满足）
 (6) 没有跳过 North（五 shard 是 exact 集合；缺一 ⇒ acceptance 本身就不可能成功）

机器可读判据：编排 CLI 输出 `level2_eligible == true`（且 `level2_blockers == []`）。
若 `--handoff` 缺失 / 未批准 / 是 synthetic / digest 不匹配 ⇒ `level2_eligible = false` ⇒ LEVEL 2 = FAIL。
```

> ⚠️ 该 handoff ⛔ 不是"数据自证来源"：它是**人工批准**的本地证据记录，工具只能把它与
> 被接受的 artifact digest 对账（`handoff_bundle_digest_mismatch` /
> `handoff_acceptance_digest_mismatch` / `handoff_not_approved` 全部 fail closed）。
> ⛔ handoff 中不含凭据 / 会话标识 / auth header / 原始响应体 / 学生个人数据；
> 未知键一律拒绝（防止夹带）。

| # | 需要证明的事 | 证据形态 | 采集命令 / 来源 |
| --- | --- | --- | --- |
| L2-0 | **REAL-SOURCE-PROVENANCE 门**（上框六条） | handoff 记录本身（安全元数据）+ `level2_eligible == true` | `real_source_provenance` 段 + `level2_gate_conditions` |
| L2-1 | Curriculum 路径是**真实**的 | `data_source == "real"`、目标版本 = Case A、`as_of_term` = 已批准值、决策集合 = 已批准集合 | 启动日志 / `inspect_planning_runtime().reason == "ready"`；case 文件路径只记 `<local>/...` |
| L2-2 | 五份 raw bundle 的 **exact-byte digest** | 5 条 `raw_bundle_sha256` | `acceptance.shards[].raw_bundle_sha256`（应与 handoff 逐条一致） |
| L2-3 | **已批准 inventory** 及其文档 identity | 1 条 `inventory_sha256` | `acceptance.inventory_sha256`（+ 批准记录 out-of-band） |
| L2-4 | **full-semester acceptance** 存在且 identity 明确 | `manifest_sha256`（64 hex）、`manifest_format`、`manifest_version` | `acceptance.manifest_sha256`（= `--output-manifest` 写出的 canonical manifest 的 SHA） |
| L2-5 | acceptance 的 scope / semester 精确 | `scope_kind == "full_semester"`、`scope_id == <semester>`、`semester == <semester>` | `acceptance.*` / `load_course_data_acceptances` |
| L2-6 | 计数自洽 | 每 shard `loaded_count == reported_total`；`Σ reported_total == baseline`；`baseline_before == baseline_after`；`merged_offering_count` > 0 | `acceptance.shards[]`、`acceptance.baseline_*`、`acceptance.merged_offering_count` |
| L2-7 | **SQLite 里就是这一条 acceptance**（不是别的） | 库中 `course_data_acceptance.artifact_sha256 == manifest_sha256`，且 canonical manifest 重算一致 | `load_accepted_offerings(sqlite, semester, acceptance_sha256=<manifest>)` 成功 + `readback_manifest_sha256` |
| L2-8 | Store-backed Provider **只返回被接受的行** | `provider_offering_count == merged_offering_count == membership 行数`；`readback_offering_set_sha256` 可重算 | 编排 CLI 的 `provider_read_back` 段 |
| L2-9 | runtime **消费该 acceptance**（而不是别的数据） | `APP_COURSE_DATA_ACCEPTANCE_SHA256 == manifest_sha256` 且 `/api/v1/plan` 返回 **200**；env 里的 DB 路径 == `store_binding.resolved_verified_store_path` | env 值 + `store_binding` 段 + `curl` 状态码 + `PlanResult` 的 `status` / 计数 |
| L2-10 | **没有 synthetic / Mock Course Data 参与** | ⛔ 响应不带 `X-Data-Source: mock`；⛔ 请求不经过 `/api/v1/mock/*`；`selected_classes` 的 `(course_id, class_id)` ⊆ 被接受行的 identity 集合 | 响应头 + 网络记录 + 与 `load_accepted_offerings` 的 identity 集合比对 |
| L2-11 | 负例仍然 fail closed（防止"一次通过"掩盖脆弱性） | 缺 acceptance / 错 digest / campus-only / 篡改行各自的 503；handoff 未批准 / digest 不符各自的 fail closed | `REAL_CAPTURE_AND_RUNTIME_RUNBOOK.md` §3.4 + 编排 CLI 的 exit 9 |

**LEVEL 2 判定**：L2-0 … L2-11 **全部**成立，才可写 "Real data path verified (LEVEL 2)"；
其中 **L2-0（real-source gate）与 L2-10（无 Mock 参与）是关键否决项**。

## 2. LEVEL 3 证据清单（Real Case A E2E passed）

> 在 LEVEL 2 全部证据之上，**追加**前端链路与 `REAL_CASE_A_ACCEPTANCE.md` §1 的 **10 条**。

| # | 需要证明的事 | 证据形态 |
| --- | --- | --- |
| L3-1 | LEVEL 2 的 L2-0 … L2-11 全部成立（含 real-source gate） | 同 §1 的证据集合 |
| L3-2 | 请求**真的经过 production runtime factory**（⛔ 无 `dependency_overrides`、⛔ 无 Fake） | 后端启动命令 + 未打补丁的进程 + 响应证据（§1 第 1 条） |
| L3-3 | 三个 Provider 都是**真实实现类** | `CurriculumCaseProvider` / `StoreBackedCourseDataProvider` / `RestrictedPlannerProvider`（§1 第 2–4 条） |
| L3-4 | 前端 **Real 模式**与请求形状 | `VITE_PLAN_API_ENABLED=true`；网络面板只出现 `POST /api/v1/plan`（§1 第 2 条） |
| L3-5 | 前端展示 **Real 结果 + provenance** | 结果区 provenance = Real；基础展示数据仍标 Mock；截图/记录（⛔ 不含个人数据） |
| L3-6 | 前端**无 Mock fallback** | 503 之后仍显示 Mock 来源、`/api/v1/plan` 只请求一次、Mock 通道请求数不变（Gate E 回归已锁定同样行为） |
| L3-7 | 前端文案不越界 | 不出现"可直接执行 / 已选课 / 无冲突"；`meetings=[]` 用中性文案；空数组只表示"无记录" |
| L3-8 | `current_schedule` provenance 合法 | 空数组，或每一项 `data_source == "real"`（§1 第 8 条） |
| L3-9 | 响应 = 合法 `PlanResult` 且**不带** `X-Data-Source: mock` | 通过 `schemas/plan_result.schema.json` + 响应头（§1 第 9/10 条） |
| L3-10 | 前端回归在**同一提交**上通过 | `npm test` / `npm run typecheck` / `npm run build` 输出（摘要） |

**LEVEL 3 判定**：L3-1 … L3-10 全部成立 ⇒ 才可写 "Real Case A E2E PASSED"。

## 3. 证据包建议结构（不含个人数据）

```text
evidence/
  00-environment.md           # 采集日期、semester、命令与版本（⛔ 无凭据、无会话标识）
  01-capture.md               # 5 条 raw_bundle_sha256 + diagnostics 的 baseline/各 shard total
  02-inventory-approval.md    # inventory_sha256 + 批准记录（谁/何时，out-of-band）
  02b-handoff-approval.md     # real-capture handoff（安全元数据）+ 批准记录 + level2_eligible 判定
  03-acceptance.md            # manifest_sha256 + scope + 计数（loaded/reported/merged）
  04-sqlite-readback.md       # provider_offering_count / membership / offering_set_sha256 + store_binding
  05-runtime.md               # env 变量名（⛔ 不含 secret；路径写 <local>/…）+ 启动命令 + reason=ready
  06-api.md                   # HTTP 状态码 + PlanResult 摘要（status / 计数）+ 响应头
  07-frontend.md              # 前端截图/记录 + 文案核对清单（⛔ 不含个人数据）
  08-negative.md              # 失败矩阵负例结果（503/500 分类 + handoff fail closed）
```

⚠️ `evidence/` ⛔ **不入 Git**（真实 artifact 与其摘要的同现也应按受控材料处理）。
