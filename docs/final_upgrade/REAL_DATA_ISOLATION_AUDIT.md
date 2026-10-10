# 真实数据隔离审计（任务 C）与最小修复建议

> 审计对象：`feature/real-capability-readiness`（基线 `f537bee`）
> 结论口径：**只有**在"无需任何技术证据校验、且该边界上无需人工批准"时，才标记为**真实漏洞**。

---

## 1. 一句话结论

**主张成立（CONFIRMED）**：完全合成的数据可以**纯自动地**获得
`data_source = real` 或用户可见的 "Real" 标签。

根因不是某个字段写错，而是一个**结构性**事实：

> `real` 在所有**产出侧**都是被强制赋值或自述的，
> 而在所有**消费侧**从不被证明。

因此本轮**不**擅自修改运行时不变式（那会把"真实来源"的定义权握在 Agent 手里，
属本任务书明确要求人工批准的事项），而是：

1. 把审计结论**变成可执行断言**（`backend/tests/test_real_data_isolation.py`）；
2. 明确列出最小修复方案与**为什么需要人工批准**。

---

## 2. 已核实的缺口（含可执行证据）

### F-01（最高）摄取链无条件标记 real，运行时无"合成 / 真实"不变式

| 位置 | 事实 |
| --- | --- |
| `backend/app/course_data/normalization.py:501` | `build_course_offering` **无条件**写 `data_source = REAL`（`:515-516` 同源） |
| `backend/app/course_data/store.py:1060-1081, 1329-1336, 1371` | 落库时按 real 写；读回时**硬编码** REAL |
| `backend/app/course_data/snapshot.py:152-156` | 只挡 mock→real 污染方向，**不**验证来源真伪 |
| `backend/app/services/planning_runtime.py:244-300` | 只检查开关、四个配置项非空、SHA-256 是 64 位十六进制、`case.data_source is REAL`、目标版本号 / 学期 / 已批准决策三项与 `case_a_decisions.py` 相等 |

**可执行反例（仓库自带）**：`backend/tests/test_synthetic_production_e2e.py`
自述 `"Claim level: synthetic production wiring / LEVEL1 capability only"`，
却完整跑通：合成原始行 → 五校区 Capture Bundle → 校区验收 → 全学期验收 →
SQLite → `APP_REAL_CASE_A_ENABLED=1` → `POST /api/v1/plan` 返回 200，
并断言 real 路径上**不出现** `X-Data-Source: mock` 头。

⇒ 这不是"可能"，而是**已被测试固化的事实**。

### F-02 唯一的 real 守卫是字面量子串扫描

`backend/app/curriculum/case.py:147-148`：

```python
if self.data_source is DataSource.REAL and any("mock://" in value.lower() for value in sources + evidence):
    raise CurriculumNormalizationError("case: explicit Mock sources cannot be labeled real")
```

被扫描的集合（`:127-146`）**不含**：`CourseOffering.source`、catalog `verification`、
任何字节摘要、交付方身份。

**后果**：只要来源标签避开 `mock://`（例如用 `verified-source://…`），
整份**合成** case 就会被接受为 `data_source = real`。

**已固化为可执行断言**：
`test_KNOWN_GAP_real_label_survives_without_mock_marker`。

### F-03 catalog 的 `verification` 是纯自述布尔

`backend/app/curriculum/catalog.py:119-120, 359-369, 387-390, 405-408`：
`verified` 只做 `type(value) is bool` 检查，`evidence` 只要求"非空字符串"。
`CatalogEntry`（`:196-213`）**根本没有** `verified` 字段——能进入可选列表的必然已 `verified=true`。

`requirements.py:157` 自认：`"Completeness evidence is supplied by the caller; counts do not prove it."`

**已固化为可执行断言**：
`test_catalog_verification_is_a_self_declared_boolean`（断言"任意非空文本即可入选"这一现状）。

### F-05 AI 上下文的 `data_source` 由请求体推导并回显

`backend/app/ai_planning/context.py:91-99` 的 `_source_of`：
全 real→real、全 mock→mock、混合→mixed、**零教学班→unknown**（这一档行为**正确**，⛔ 不默认成 real）。

但 "real" 完全来自**请求体里教学班对象自己的** `data_source` 字段。
`ai_planning/service.py:834-835` 在 real 时**抑制**"不代表真实教务开课"的风险提示，
前端 `useAiPlanning.ts:666-679` 也据此显示"上下文全部为 real 教学班"。

**已固化为可执行断言**：`test_KNOWN_GAP_ai_context_source_is_caller_declared`。

### F-08 工具层唯一的 synthetic 闸门是自述布尔且**可选**

`tools/prepare_real_case_a_runtime.py`：

- `:837-850` 的 `handoff["synthetic"] is not False` ⇒ 退出 9；
- 但 `--handoff` 是**可选**参数（`:1819-1836`）；
- 缺失时只写报告字段（`:1944-1947` `blockers.append("real_source_handoff_missing")`、
  `:1951-1953` `level2_eligible`），**不阻止** `status == "ready"` 与完整
  `runtime_environment` 输出（`:1965-1972, 2009`）；
- `:980` 的 `_build_curriculum_provenance()` **硬编码** `"synthetic": False`，
  使 `:1044` 的 synthetic 判断**空转**；`:751` 同样硬编码 `"authorized_user_session": True`；
- 后端**不读** `level2_eligible`。

⇒ 这个闸门**自身自述、且默认不生效**。

### F-07 前端 "Real" 标签只依据 HTTP 成功（F-01/F-02 的下游）

`frontend/src/App.vue:94-102`：`realPlanResult !== null` ⇒ `'real'`；
`:117-126` 标签"Real Planning 结果"；`state/userInput.ts:47-49`"规划结果来源：Real"。
`TopStatusBar.vue:40,72-80` 的横幅**硬编码**"当前展示的是 Mock 演示通道数据"，
与 `real` 标签**互相矛盾**（这一侧是过度告警，不是误标 real）。

---

## 3. 已检查并判定 **SAFE**（覆盖范围，避免读者以为漏审）

| 项 | 依据 |
| --- | --- |
| 契约默认 `data_source = MOCK`，缺字段永不变 real | `models/contracts.py:239` + `extra="forbid"` |
| 个人规划请求的 `data_source` 自述分支**HTTP 不可达** | `personal/student_input.py:65-77, 293-294`（声明 real ⇒ 422；不声明 ⇒ mock） |
| snapshot 挡 mock→real 混入 | `course_data/snapshot.py:152-156` |
| 库内非 real 行拒载 | `course_data/store.py:1329-1336` |
| acceptance 完整性 / 防篡改链（9 条逐次重校验 + 503） | `course_data/store.py:1479-1709`、`store_provider.py:184-206`、`main.py:78-80` |
| 五校区精确匹配、inventory 摘要绑定、基线相等、Σ shard == baseline、跨 shard 重复 fail closed | `course_data/full_semester_acceptance.py:1225-1444` |
| 运行时 fail-closed、无 Mock / campus 回退、每次请求重新装配 | `planning_runtime.py:36, 309-318`、`api/plan.py:72-73`、`api/personal_plan.py:408-416` |
| Mock 通道身份标注（按路径前缀打头 + 双重校验） | `api/mock.py:37-38`、`main.py:46-58`、`mock_service.py:144-210` |
| 前端**不**回退 Mock | `api/plan.ts:2-13`、`useDemoData.ts:12`、`useUserInput.ts:64-108` |
| AI 上下文其余校验（学期一致、重复身份拒绝、白名单仅来自输入） | `ai_planning/context.py` |

---

## 4. 最小修复建议（**均需人工批准**，本轮未实施）

按优先级，且都**不修改公共 Schema**：

| # | 修复 | 影响面 | 为什么需要批准 |
| --- | --- | --- | --- |
| 1 | 在 `build_planning_runtime` 增加**运行时不变式**：acceptance 必须绑定到运行时可达、非本地产物的 provenance（签名 handoff / 采集会话凭据），否则 `course_data_not_ready`——即把 `level2_eligible` 从"报告字段"变成"装配前置" | `services/planning_runtime.py` | 改变"什么算真实来源"的**业务定义** |
| 2 | 用等价性检查替代 `case.py:147` 的子串启发式：case 的 source / evidence 必须能解析到含 case 文件 SHA-256 的**已批准 provenance** | `curriculum/case.py` | 同上；且会拒绝现在被接受的输入 |
| 3 | `synthetic` / `authorized_user_session` 不得由同一工具写入，须来自独立证据；`--handoff` 缺失应**阻止** `ready` | `tools/prepare_real_case_a_runtime.py` | 会改变现有工作流与退出码 |
| 4 | AI 上下文不采信请求体的 `data_source`，改由后端 provider / 签名令牌注入，且 real 时附加**不可抑制**的来源提示 | `api/ai_planning.py`、`ai_planning/context.py` | 改变用户可见的风险提示语义 |
| 5 | catalog 的 `verification.evidence` 强制解析到带 SHA-256 的核验记录 | `curriculum/catalog.py` | 改变目录 artifact 的**验收口径**（属公共 artifact 语义） |
| 6 | 前端 "Real" 标签改为依据**后端来源标记**而非 HTTP 成功；并修掉与横幅的矛盾 | `frontend/src/App.vue`、`state/userInput.ts` | 改变用户可见标签语义 |
| 7 | 修正 `prepare_real_case_a_runtime.py` docstring 与实现的矛盾（自认"不读取、不校验"，实际会重算 SHA 并校验批准门） | 纯文档 | 属他人模块文档，最小、但仍建议由负责人确认 |

---

## 5. 本轮**做了什么**、**没做什么**

**做了**（可执行、可复现、⛔ 不改生产行为）：

- 新增 `backend/tests/test_real_data_isolation.py`：
  - 4 项**回归护栏**：契约默认 mock、`mock://` 守卫、catalog 未核验拒选、
    catalog `verified` 是自述布尔；
  - 2 项**已知缺口断言**（`test_KNOWN_GAP_*`）：F-02 与 F-05 —— 让缺口**不能被悄悄忽略**、
    也**不能冒充成已修复**；
  - 1 项 AI 上下文三态断言：零教学班 ⇒ `unknown`（正确行为，⛔ 不默认成 real）。

**没做**（并说明原因）：

- ⛔ 未修改 `normalization.py` / `store.py` / `planning_runtime.py` / `case.py` / `catalog.py`：
  它们分别是 Course Data、Planner 装配、Curriculum 的**核心规则**，
  本任务书明确要求"需人工批准"，且"缺少业务审核时记录 BLOCKED"；
- ⛔ 未"用改写来源字段让 Mock 变 Real"，也未做相反的掩盖式"修复"；
- ⛔ 未新增任何课程认定规则。

---

## 6. 【BLOCKED】运行时真实性不变式

```text
【BLOCKED】
阻塞原因：F-01 / F-02 / F-03 / F-08 的修复都需要决定"什么才算真实来源"这一
          业务/架构定义（签名 provenance、批准链、摘要绑定），属人工决策范围。
已经确认：合成数据可纯自动获得 data_source=real 与前端 Real 标签；
          唯一守卫是 mock:// 子串启发式；verification 是自述布尔；
          工具层 synthetic 闸门默认不生效。
无法确认：真实已核验 catalog / 真实 Case A case 是否已在仓库外产出；
          五个已批准校区编号与学校当前系统是否一致。
需要人工提供：① 是否采纳 §4 的第 1–3 项运行时不变式；② 由谁签发 provenance；
          ③ 现有合成 E2E（test_synthetic_production_e2e.py）在改动后应如何标注。
在确认前不会修改：course_data / planning_runtime / case / catalog 的任何生产逻辑。
```
