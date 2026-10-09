# AI Planning 前后端联合验收报告（PR #67）

- **分支**：`feature/ai-planning-joint-e2e`（起点 `c60bf209b3b46ab9540e70515b6a98185f52f06c`）
- **集成内容**：后端 PR #66（DeepSeek Planning Controller）+ 前端 PR #65（AI 调整三入口与抽屉）
- **执行环境**：Windows + PowerShell；Python 3.14.7（`PYTHONUTF8=1`）；Node v24.19.0 / npm 11.17.0；Vitest 3.2.7 / vue-tsc 3.3.11 / Vite 8.3.1
- **DeepSeek 密钥**：**未注入** ⇒ 真实在线调用仍为 **NOT VERIFIED**（见 §6）
- **使用数据**：**Mock**（人工构造的合成教学班与补修任务）；⛔ 未使用任何真实学生隐私数据
- **公共契约**：**未修改** `/schemas/**` 与 `/docs/interfaces/**`（已用 `git status` 核对为空）

---

## 1. 逐项验收结果总览

| # | 验收项 | 命令 | 结果 |
| --- | --- | --- | --- |
| 1a | 后端完整 pytest | `python -m pytest -q` | **3188 passed / 2 failed / 2 skipped**（2 项为既有环境差异，见 §5） |
| 1b | 前端 Vitest | `npx vitest run` | **274 passed / 0 failed**（18 个测试文件） |
| 1c | 前端 TypeCheck | `npx vue-tsc --noEmit` | **exit 0** |
| 1d | 前端 Build | `npm run build` | **exit 0**（`dist/index.html` + CSS 35.59 kB + JS 236.02 kB） |
| 2 | 真实 HTTP：`GET /status` | 见 §3 | **PASS** |
| 2 | 真实 HTTP：`POST /interpret` | 见 §3 | **PASS** |
| 2 | 真实 HTTP：`POST /solve` | 见 §3 | **PASS** |
| 2 | 真实 HTTP：`POST /adopt` | 见 §3 | **PASS** |
| 3 | 两次用户确认 | `test_full_two_confirmation_flow_over_real_http` | **PASS** |
| 3 | 候选生成 | 同上（`candidate_ready` + 确定性 `diff`） | **PASS** |
| 3 | 拒绝候选 | `test_rejecting_a_candidate_over_real_http_keeps_the_original_plan` | **PASS** |
| 3 | 方案过期 | `test_candidate_expiry_is_rejected_over_real_http`、`test_stale_plan_digest_is_rejected_over_real_http` | **PASS** |
| 3 | 模型不可用 | `test_unavailable_model_is_reported_over_real_http` | **PASS** |
| 3 | 原方案不变 | 拒绝 / 过期 / 冲突 / 未确认四条路径均有断言 | **PASS** |
| 4 | 修复集成兼容性问题 | §4 两处真实形状错配 + 回归测试 | **FIXED** |
| 5 | 无隐私数据 / 无密钥用工注入式模型并如实标记 | 全部用例 `generator_kind=test_double`，`data_source=mock/unknown` | **PASS** |

新增测试：后端 **+14**（`tests/test_ai_planning_joint_e2e.py`）、前端 **+6**（`tests/ai-planning-joint-contract-fix.spec.ts`）。

---

## 2. 验收项 1：完整测试命令与结果

### 2.1 后端

```powershell
cd backend
$env:PYTHONUTF8 = "1"
python -m pytest -q
```

```text
3188 passed, 2 failed, 2 skipped
```

- 本轮基线（未改动前，同一命令同一环境）：**3174 passed / 2 failed / 2 skipped**；
- 新增 14 项全部通过；
- 2 项失败**不是本轮引入**，见 §5；
- 2 项 skip 为既有跳过。

### 2.2 前端

```powershell
cd frontend
npm ci                      # 首次需要；exit 0
npx vitest run              # 274 passed (18 files)
npx vue-tsc --noEmit        # exit 0
npm run build               # exit 0
```

`npm ci` 报告 **4 个依赖漏洞（1 moderate / 1 high / 2 critical）** 与
`esbuild@0.28.2` 的 postinstall 未被 allowScripts 覆盖的警告。
两者都是**既有依赖树**情况，本轮⛔ 未改 `package.json` / `package-lock.json`，
也不属于本联调分支引入。

---

## 3. 验收项 2–3：真实 HTTP 闭环

### 3.1 怎么做的（不是 mocked fetch）

新建 `backend/tests/test_ai_planning_joint_e2e.py`，用 **uvicorn 在随机空闲端口真实监听**，
再用 `urllib` 发**真实 HTTP 请求**（`http_json()` 会读取真实状态码与响应体）：

```text
LiveServer(uvicorn) + app.dependency_overrides[get_ai_planning_service]
        ↓  http://127.0.0.1:<随机端口>
GET  /api/v1/ai-planning/status
POST /api/v1/ai-planning/interpret
POST /api/v1/ai-planning/solve
POST /api/v1/ai-planning/adopt
GET  /openapi.json , GET /api/v1/mock/preference   （既有路由不受影响）
```

**模型来源如实标注**：环境没有 `DEEPSEEK_API_KEY`，因此通过依赖注入使用
`RuleFakeIntentModel` / `UnavailableIntentModel` / `ScriptedIntentModel`；
响应里 `generator_kind` 只能是 `test_double` 或 `unavailable`，
⛔ 没有任何一条断言把测试替身当成线上模型。

### 3.2 逐条结果

| 用例 | 断言要点 | 结果 |
| --- | --- | --- |
| `test_status_over_real_http_reports_test_double_without_exposing_a_key` | 200；`live_model_available=false`；响应里没有 `sk-`、没有 `api_key` 字段 | PASS |
| `test_status_reports_disabled_when_switch_is_off` | `enabled=false`；`POST /interpret` → 503 `ai_planning_disabled` | PASS |
| `test_full_two_confirmation_flow_over_real_http` | 见 §3.3 | PASS |
| `test_rejecting_a_candidate_over_real_http_keeps_the_original_plan` | `accept=false` → `rejected` / `adopted_version=0` / `original_plan_unchanged=true`；再次采用 → 409 | PASS |
| `test_ambiguous_intent_cannot_be_solved_over_real_http` | 未声明学分上限 → `can_confirm=false` + `credit_limit_missing_evidence`；求解 → 409 `ai_planning_intent_not_confirmable` | PASS |
| `test_stale_plan_digest_is_rejected_over_real_http` | 指纹不符 → 410 `ai_planning_session_expired` | PASS |
| `test_candidate_expiry_is_rejected_over_real_http` | TTL=1s，sleep 1.6s 后采用 → 410，且提示"有效期" | PASS |
| `test_unavailable_model_is_reported_over_real_http` | 503 `ai_planning_model_unavailable`，原因码 `missing_api_key` 如实透出 | PASS |
| `test_no_selected_classes_still_reports_no_feasible_candidate` | 无教学班 ⇒ `data_source=unknown`（⛔ 不默认 real）；`missing_data` 原因如实透出 | PASS |
| `test_personal_information_in_message_is_refused_before_any_model_call` | 含学号的消息 → **400**，不发给模型 | PASS |
| `test_scripted_model_with_hallucinated_course_is_rejected_over_real_http` | 幻觉课程号 → **422** `ai_planning_model_output_invalid`，且错误体不回显该课程号 | PASS |
| `test_existing_routes_still_answer_over_real_http` | `/api/v1/plan`、`/mock/*`、`/personal-planning/*`、`/explanation/plan`、`/completed-courses/import` 与 4 条新路由同时在 OpenAPI 中 | PASS |

### 3.3 两次确认闭环的实际观测

```text
1) POST /interpret  {"context": …, "user_message": "这学期太累，数据结构必须保留，尽量别在周五上课"}
   → 200 · generator_kind=test_double · data_source=mock · can_confirm=true
     state=intent_draft · plan_digest=<64 hex>
     parsed_intent.locked_courses=[DS101/ds-01]（reason 非空）
     ⛔ 响应里没有 candidate_plan（只读，不求解）

2) POST /solve      {"intent_id":…, "plan_digest":…, "confirmed_intent":{"plan_digest":…}}   ← 故意残缺
   → 422 ai_planning_intent_invalid（未确认不得求解）

3) POST /solve      {"intent_id":…, "plan_digest":…, "confirmed_intent":{…完整确认…}}
   → 200 · status=candidate_ready · plan_kind=PlanResult
     diff.added   包含 ALGO201/algo-02（唯一 CLEAR 新增）
     diff.added   **不含** ALGO201/algo-01（与已选班同段冲突，未被自动加入）
     diff.kept    包含 DS101/ds-01（用户锁定课程被保留）
     blocked_reason=null · generator_kind=test_double · data_source=mock

4) POST /adopt      {"candidate_id":…, "plan_digest":…, "accept":true}
   → 200 · accepted=true · state=adopted · adopted_version=1
     adopted_version_scope=process_local_session
     original_plan_unchanged=false
     ⛔ 响应里没有 adopted_plan / candidate_plan（方案体只能来自第 3 步的候选）

5) POST /adopt      同一 candidate_id 再次 accept=true
   → 409 ai_planning_adoption_conflict（不重复推进版本）
```

**原方案不变的证据**：拒绝（`original_plan_unchanged=true`）、
过期（410 且没有版本推进）、冲突（409）、未确认（422）四条路径都**没有**改变候选/版本；
所有候选都是独立对象，只有第 4 步的成功采用才推进 `adopted_version`。

---

## 4. 验收项 4：修复的集成兼容性问题

两处都是**真实形状错配**（由 §3 的真实 HTTP 响应核出，不是猜测），
且都用"先让测试在未修复代码上失败"验证过（revert 修复后 6 项里 4 项失败）。

### 4.1 `diff.replaced[]` 的键是 `from_class` / `to_class`

| 项 | 内容 |
| --- | --- |
| 现象 | 后端换班行是 `{course_id, from_class, to_class}`；前端 `parseDiffEntry` 读 `class_id` ⇒ 一旦出现换班，解析抛 `ContractViolation`；对比面板显示 `班号 undefined` |
| 影响 | "换班"是本轮真实场景（用户要求保留某课 / 换替代班），不是理论分支 |
| 修复 | `frontend/src/api/aiPlanningContract.ts`：`AiPlanDiffEntry.class_id` 改为可选并新增 `from_class` / `to_class`；`parseDiffEntry` 按"有 `class_id` 走普通行，否则要求 `from_class`+`to_class`"解析 |
| 修复 | `frontend/src/components/ai/CandidateComparePanel.vue`：替换区改用 `formatReplaced()` 显示 `from → to`，`key` 改用 from/to，并新增 `data-testid="ai-replaced-note"` 提示"同一次换班在班次集合语义里也会出现在新增/移除，请以替换为准" |
| 未放宽契约 | `replaced` 行**缺** `class_id` 且**缺** `from_class`/`to_class` 时**仍然抛错**（有测试锁定） |

### 4.2 `parsed_intent.locked_courses[].reason` 在后端可空

| 项 | 内容 |
| --- | --- |
| 现象 | 后端 `reason` 是**可选**字段（模型可以不给出保留原因，返回 `null`）；前端要求必须是字符串 ⇒ 拒绝整份合法草稿 |
| 修复 | `parseLockedCourse` 把 `null` / 缺省规范成 `''`，并在类型上注明该字段可空 |
| 未放宽契约 | `reason` 是数字等非法类型时**仍然抛错**（有测试锁定） |

### 4.3 记录但**未**修改的后端形状（供 Reviewer 裁决）

| 形状 | 现状 | 为什么没动 |
| --- | --- | --- |
| `no_feasible_candidate` 仍返回非空 `candidate_id` | 后端会为该次结果创建候选记录并返回 id；前端 `canDecideCandidate` 要求 `status==='candidate_ready'`，因此**不会**用这个 id 去采用，也**不会**伪造方案体 | 属 PR #66 已发布的私有契约；HANDOFF 只给了 `blocked` 的示例（`candidate_id: null`），前端已安全处理 ⇒ 改动收益低、风险高。**建议**后端后续显式写明该字段语义 |
| 一次换班**同时**出现在 `replaced` 与 `added`/`removed` | `added`/`removed` 是**教学班键**的集合差，`replaced` 是按课程看的结果 | 前端已在替换区加显式提示；后端语义本身自洽，属文档问题（HANDOFF §4 未说明）⇒ 建议补一句说明 |
| `diff.replaced[]` 在 HANDOFF 文档里被描述成与 `added` 相同的行形状 | 文档示例里 `replaced: []` 为空数组，没有展示非空行 | 已在 HANDOFF 侧发现并写进本报告；本分支**未**改 HANDOFF（属 PR #66 的文件） |

---

## 5. 失败与环境差异（逐条说明）

### 5.1 后端 2 项失败（**既有，与本轮无关**）

```text
FAILED tests/test_curriculum_docx_reader.py::test_duplicate_or_unsafe_archive_members_are_rejected[word\\DEMO-PRIVATE-PART]
FAILED tests/test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]
```

| 项 | 说明 |
| --- | --- |
| 性质 | **Windows 路径语义差异**，不是本次集成或 AI 规划引入 |
| 证据 1 | 本轮**未改动文件**上先跑一次基线，同一命令同一环境就是这两个失败（3174 passed / 2 failed） |
| 证据 2 | 两份失败涉及的模块是 Curriculum 的 `docx_reader` / `json_reader`；本分支⛔ 未修改 `app/curriculum/**` |
| 证据 3 | Python 3.14 起 `Path("bad\x00path")` 不再抛 `ValueError`；另一项是 Windows 上 ZIP 成员名里字面反斜杠的语义差异 |
| 处置 | ⛔ 未修改实现或测试，⛔ 未为了让它们变绿而放宽断言；作为**遗留基线失败**上报 |

### 5.2 真实 DeepSeek 在线调用：**NOT VERIFIED**

| 项 | 说明 |
| --- | --- |
| 现状 | 运行环境**没有** `DEEPSEEK_API_KEY`；`GET /status` 返回 `live_model_available=false`、`api_key_configured=false` |
| 本轮做法 | 按任务要求使用**注入式测试模型**，响应 `generator_kind=test_double`，`generator_note` 明确写"注入的测试替身模型（不是线上模型）" |
| ⛔ 未声称 | 没有任何测试、文档或报告声称已完成真实 DeepSeek 在线调用 |
| 在线验证方式（由运行方执行） | ① 服务器注入**新的安全密钥** + `AI_PLANNING_ENABLED=1`；② `GET /status` 应 `live_model_available=true`；③ `POST /interpret` 应 `generator_kind=deepseek_live`、`model_id = DEEPSEEK_MODEL`；④ 401/402 只会返回固定原因码 |
| 密钥纪律 | 历史对话里出现过的 `sk-` 旧密钥**已作废**；本轮⛔ 未使用、⛔ 未引用、⛔ 未写入任何文件 |

### 5.3 其它环境差异

| 项 | 说明 |
| --- | --- |
| `PYTHONUTF8=1` 必需 | 宿主为 Windows + GBK（cp936）；不开 UTF-8 时既有 Curriculum 用例会因解码失败而报错，这不是本轮问题 |
| 无前端 E2E 浏览器 | 本轮前端验证是 Vitest + `@vue/test-utils` + jsdom 的组件级测试 + 构建，**不是**真实浏览器端到端；真实浏览器联调仍待运行方在有后端的环境执行 |
| `npm ci` 漏洞报告 | 既有依赖树的 4 个漏洞；本轮⛔ 未改依赖清单 |
| 会话仅进程内 | `adopted_version_scope=process_local_session`；重启即失效（404/410），⛔ 不等于持久化、⛔ 不等于教务选课成功 |
| 未装配真实供给 | 真实已核验培养方案目录与真实教学班 acceptance 仍未装配；`data_source` 如实为 `mock` / `unknown` |

---

## 6. 仍未完成（沿用并更新前一轮结论）

| 项 | 状态 |
| --- | --- |
| DeepSeek 真实在线调用 | **NOT VERIFIED**（需运行方注入新密钥） |
| 真实已核验培养方案 / 真实教学班供给 / 真实数据 E2E | **BLOCKED**（未装配） |
| 真实浏览器端到端（前端 ↔ 真实后端） | **未执行**（本轮为组件级 + 真实 HTTP 后端） |
| 会话持久化 / 多实例共享 | **不支持**（进程内存储，需负责人裁决是否引入数据库） |
| `exclude_course` / 跨学期自动重排 | **不支持**（后端明确 `blocked` + 固定原因） |
| 可行子集搜索 / 多候选排序 | **未实现**（超限按保守拒绝，不等于最优补修路径） |

---

## 7. 结论

```text
INTEGRATED / EXECUTABLE GATE PASSED (with documented caveats)
```

- 后端与前端测试、类型检查、构建**全部执行**且结果如上；
- 四个 AI 规划接口的**真实 HTTP** 闭环（两次确认、候选、拒绝、过期、模型不可用、原方案不变）
  **全部通过**；
- 发现并修复 **2 处真实形状错配**，并新增 **20 项**回归测试（后端 14 + 前端 6）；
- 2 项后端失败为**既有 Windows 路径语义差异**，与本轮无关，已如实上报；
- 真实 DeepSeek 在线调用与真实数据 E2E 仍需运行方在具备密钥与已核验数据的**受控环境**执行。

⛔ **不得**据此合并到 `feature/final-upgrade-integration-qa` 或 `main`：
本分支只以 **Draft PR** 呈现，等待项目 Reviewer 与负责人验收。
