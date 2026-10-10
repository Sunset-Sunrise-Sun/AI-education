# 来源可信性缺口修复报告（F-01 / F-02 / F-03 / F-05 / F-08 收口）

> 分支：`feature/verified-provenance-gate`（基线 `feature/final-upgrade`）
> 审计来源：`REAL_DATA_ISOLATION_AUDIT.md`（PR #72 合入）
> 设计：`TRUST_ANCHOR_DESIGN.md`
> 代码：`backend/app/provenance/__init__.py`

---

## 0. 一句话结论

> **"已核验"不再是数据里的一句话，而是运行时必须在带外批准锚点里找到匹配记录。**

修复前：合成数据可以**纯自动**获得 `data_source=real` 或 `verification.verified=true`。
修复后：这些自述字段⛔ **不再单独生效**——装配期必须通过
"批准记录存在 + 摘要一致 + 身份一致 + 非自签 + 未过期"五道检查，否则 **fail closed**。

---

## 1. 逐条收口

### F-01 摄取链无条件标 real、运行时无真实性不变式 ⇒ 已加运行时不变式

| 修复点 | 内容 |
| --- | --- |
| `app/services/planning_runtime.py::build_planning_runtime` | 新增**先决**检查：读不到 `APP_TRUST_ANCHOR_PATH` 批准锚点 ⇒ `provenance_not_verified`，⛔ 不再往下装配 |
| `app/services/planning_runtime.py::build_course_data_provider` | 新增 `approved_manifest_sha256`（来自锚点）；⛔ 空集合 ⇒ 构造期拒绝 |
| `app/course_data/store_provider.py::StoreBackedCourseDataProvider` | 新增 `approved_manifest_sha256` + `require_approval`；构造期与**每次读取**都走同一条批准门 |
| `app/course_data/store.py::load_accepted_offerings` | 新增第 0b 步：`SHA256(canonical stored manifest)` 必须∈批准摘要集合。⛔ 只"摘要自洽"不够 |

**为什么绑在 manifest 摘要上**：`canonical_manifest_sha256` 是 store 在**每次读取**时
从库里已持久化的 canonical manifest **重算**出来的（`_require_manifest_trust_chain`）。
因此"批准摘要 == 重算摘要"这一等式同时证明了：

- 内容与人工批准的那一份**完全一致**（改一个字节就失败）；
- 即使把 DB 里的 acceptance 记录与 manifest **一起**改写，也会因为重算值与批准值不符而失败。

> ⚠️ 这就是任务书要求的"**必须同时存在独立批准依据**"：
> SHA-256 单独只证明"输入与摘要一致"，批准锚点才提供"谁批准了什么"。

**产出工具的边界**：`tools/prepare_real_case_a_runtime.py`、
`tools/accept_full_semester_course_data.py`、`tools/validate_course_data_artifact.py`
在**人工批准之前**的自洽回读显式传 `require_approval=False`
（⛔ 不伪造批准摘要）。production 读取路径（runtime → Planner）**永远**是默认 `True`。

### F-02 唯一的 real 守卫是 `mock://` 子串扫描 ⇒ 已改为摘要 + 身份绑定

| 修复点 | 内容 |
| --- | --- |
| `build_curriculum_provider(case_path, *, anchor=...)` | 新增第 7 项检查：**case 文件字节**的 SHA-256 必须与锚点里 `curriculum_case` 记录的 `artifact_sha256` 一致，且身份（`target_version_id` / `as_of_term`）与 case 内容一致 |
| `anchor=None` | ⛔ 直接 `_RuntimeSourceUnavailable`（fail closed），⛔ **不**退回"只看 `data_source`" |

⚠️ **明确的范围声明**：`curriculum/case.py:147` 的 `mock://` 子串守卫**本轮未删除**——
它是 loader 的**声明侧**守卫，不是运行时门。真正的拒绝发生在**装配门**，
即"数据进入生产链路的唯一入口"。改 `case.py` 的既有契约会影响
`load_demo_case` 等路径，属另一个模块的接口决策，本轮⛔ 未擅自改动。

### F-03 catalog 的 `verified=true` 纯自述 ⇒ 已要求锚点列出该版本

| 修复点 | 内容 |
| --- | --- |
| 新拒绝码 `provenance_not_verified` | 与 `not_verified` **分开**：后者是"文件自己说没核验"，前者是"文件自称核验却拿不出独立依据"——后者才是安全事件 |
| `catalog.load_curriculum_catalog(..., approved_versions=...)` | 新增可选参数；条目 `version_id` ∉ 批准集合 ⇒ `provenance_not_verified`（空集合 ⇒ 全部拒绝） |
| `services/personal_runtime.py::load_personal_catalog` | production 路径**必须**读锚点；缺锚点 ⇒ `provenance_not_verified`；锚点无 `curriculum_catalog` 记录 ⇒ `catalog_provenance_empty` |
| `api/personal_plan.py::_require_catalog` | 来源失败使用**独立** HTTP 错误码 `personal_catalog_provenance_not_verified`，与 `personal_catalog_not_configured` 区分 |

⚠️ `approved_versions=None` 仍保留"只按自述"的行为，**仅供单元测试**；
production 调用点已全部传集合。

### F-05 AI 上下文来源由请求体推导 ⇒ 已降级为未核验并强制风险提示

| 修复点 | 内容 |
| --- | --- |
| `ai_planning/context.py` | 新增 `CONTEXT_SOURCE_REAL_UNVERIFIED = "real_unverified"` 与 `source_verified: bool = False`；`__post_init__` 里的**不变量**：`real` + `source_verified=False` ⇒ 一律降级为 `real_unverified` |
| `api/ai_planning.py` | `build_context(..., source_verified=False)` **硬编码**；请求模型 `extra="forbid"` ⇒ ⛔ 无法通过请求体打开这一档；响应新增 `context_source_verified` |
| `ai_planning/service.py` | 风险提示判据从 `data_source != "real"` 改为 `not context.source_verified` ⇒ 自述 real **再也不能**抑制风险提示 |

### F-08 工具层 synthetic 闸门可选且自述 ⇒ 已变成硬门且不再自签

| 修复点 | 内容 |
| --- | --- |
| `_resolve_readiness_status(..., handoff_ok=False)` | `ready` 现在要求 **store + curriculum + 独立 handoff** 三方都通过；缺 handoff ⇒ ⛔ `partial_ready` |
| `_orchestrate` | 新增 `handoff_ok`（handoff 存在、无 approval blocker、且 `synthetic is False`）并传入状态判定 |
| `_build_handoff(..., authorized_user_session=None)` | ⛔ **不再硬编码 `True`**。工具无法证明"存在已授权用户会话"，因此缺省 `None` ⇒ 落盘 `null` ⇒ 授权门不成立 |

⚠️ **诚实声明**：`_build_curriculum_provenance` 里仍有 `"synthetic": False` 字面量
（审计 §F-08 的第二处）。本轮**未改**它，因为该函数产出的是一份**证据记录**，
而"这份证据是不是合成"只能由填写证据的人回答；把它改成参数只会把同一个字面量
搬到调用方。**这是一个仍未修的残留点**，列入 §4 待人工确认。

---

## 2. 新增 / 修改的批准门一览

| 门 | 位置 | 缺依据时的结果 |
| --- | --- | --- |
| 锚点装载 | `build_planning_runtime` 第一步 | `provenance_not_verified`（503） |
| Curriculum case | `build_curriculum_provider` | `curriculum_not_ready` |
| Course Data manifest | `load_accepted_offerings` 第 0b 步 | `course_data_not_ready` |
| 个人规划目录 | `load_personal_catalog` | `personal_catalog_provenance_not_verified`（503） |
| AI 上下文 | `build_context(source_verified=False)` | 来源标 `real_unverified` + 风险提示 |
| 工具就绪态 | `_resolve_readiness_status` | `partial_ready`（⛔ 不给 ready） |

诊断码**不含路径、不含配置取值、不含 artifact 内容**（沿用既有约定）。

---

## 3. 负向测试（任务书 §四 九类）

| # | 绕过尝试 | 用例 |
| --- | --- | --- |
| 1 | 合成数据改写成 `real` | `test_provenance_gate_bypass.py::test_synthetic_data_relabelled_real_cannot_reach_the_planner` |
| 2 | 删除 `mock://` 标记 | `::test_removing_the_mock_marker_does_not_earn_a_real_runtime` |
| 3 | 伪造 `verification.verified=true` | `::test_forged_catalog_verified_flag_is_rejected`、`::..._cannot_use_the_personal_api` |
| 4 | 伪造 / 篡改 SHA-256 | `::test_forged_manifest_digest_is_rejected`、`::test_tampered_case_after_approval_is_rejected` |
| 5 | 修改已批准文档 / 教学班 / 学期 | `::test_modified_approved_case_is_rejected`、`::test_wrong_semester_approval_is_rejected` |
| 6 | 缺少核验人授权依据 | `::test_approval_without_authorization_is_rejected`、`::test_self_issued_approval_is_rejected` |
| 7 | AI 请求体自述 `data_source=real` | `::test_ai_request_cannot_self_declare_real` + `test_ai_planning_provenance.py` |
| 8 | 未核验输入试图进入正式 Planner | `::test_unverified_input_never_reaches_the_planner` |
| 9 | 正常 Mock 演示 / 合成 E2E | `::test_mock_demo_path_still_works`；`test_synthetic_production_e2e.py`（全绿） |

锚点自身另有 **31 项**回归：`tests/test_provenance_anchor.py`。

### `test_KNOWN_GAP_*` 的处置（任务书明确要求）

| 原用例 | 处置 |
| --- | --- |
| `test_KNOWN_GAP_real_label_survives_without_mock_marker` | **删除**，替换为 `test_synthetic_case_cannot_be_labelled_real_by_avoiding_mock_marker`（断言**必须拒绝**） |
| `test_KNOWN_GAP_ai_context_source_is_caller_declared` | **删除**，替换为 `test_caller_declared_real_ai_context_is_downgraded_not_trusted`（断言**必须降级**） |
| `test_catalog_verification_is_a_self_declared_boolean` | **删除**，替换为 `test_self_declared_verified_catalog_is_rejected_without_anchor`（断言**必须拒绝**） |

⛔ 现在文件里**不再存在**断言不安全行为是正确结果的用例。

---

## 4. 迁移影响（谁会受影响）

| 受影响方 | 影响 | 需要做什么 |
| --- | --- | --- |
| 任何启用 `APP_REAL_CASE_A_ENABLED=1` 的部署 | ⛔ **必然** 503，直到提供锚点 | 由负责人写 `APP_TRUST_ANCHOR_PATH` 指向的批准锚点 |
| `tools/prepare_real_case_a_runtime.py` 的 `ready` | 只有 handoff 真正批准时才可能出现 | 传入**已批准**的 `--handoff`；`--draft-handoff-out` 产出的是 draft |
| 依赖 `_build_handoff` 默认值的调用方 | `authorized_user_session` 由 `True` 变 `None` | 若确实观察到授权会话，显式传 `authorized_user_session=True` |
| catalog artifact 的既有使用者 | 自述 `verified=true` 的文件**不再可选** | 把 `version_id` 写进批准锚点 |
| AI 规划前端 | `data_source` 出现新取值 `real_unverified` | 已在 `aiPlanningContract.ts` / `useAiPlanning.ts` 处理；未知取值仍按 fail closed 拒绝 |
| Mock 演示 | ⛔ **无影响**（不经过真实批准门） | —— |

---

## 5. 【BLOCKED】仍需人工完成的签发环节

```text
【BLOCKED】
阻塞原因：本仓库内没有可信身份与信任锚，⛔ 无"谁有权批准"的技术依据。
          因此 Agent 只实现了**安全的拒绝路径**与**证据记录接口**，
          ⛔ 没有、也不能自创一个伪安全签名方案。
已经确认：① SHA-256 只证明"输入与摘要一致"，单独不证明来源真实；
          ② 锚点文件本身无防篡改能力，真正的边界是文件权限；
          ③ authorization 字段不被机器验证，只作可追责依据；
          ④ 自签检测是启发式，能挡明显自签，挡不住有意伪装；
          ⑤ 因此没有任何 Agent 可以自己完成签发。
无法确认：批准锚点的实际路径与文件权限、approver 的真实身份口径、
          authorization 的依据形式、是否设 expires_at 及有效期、
          是否引入真正的签名机制（离线私钥）。
需要人工提供：① 锚点文件的位置与写权限归属；② approver 身份口径；
          ③ authorization 依据形式；④ 是否签名；⑤ 真实 artifact
          （培养方案 DOCX / 教务开课数据）。
在确认前不会修改：course_data 摄取链的"无条件标 real"本身、
          `case.py` 的 `mock://` 声明侧守卫契约、公共 Schema。
```

### 仍未修的残留点（诚实列出）

| # | 残留 | 位置 | 为什么没修 |
| --- | --- | --- | --- |
| 1 | `"synthetic": False` 仍是字面量 | `tools/prepare_real_case_a_runtime.py::_build_curriculum_provenance` | 改成参数只是把字面量搬到调用方；需要先定义"这份证据由谁签署" |
| 2 | `case.py:147` 仍是 `mock://` 子串扫描 | `app/curriculum/case.py` | 它是**声明侧**守卫，运行时门已在 `planning_runtime` 建立；改它会动 loader 契约 |
| 3 | `normalization.py:501` 仍无条件写 `real` | `app/course_data/normalization.py` | 该字段是**摄取期**的声明标记；真正的门已下沉到读取期（`load_accepted_offerings` 第 0b 步） |
| 4 | 锚点无防篡改 | `app/provenance/__init__.py` | ⛔ 不自创签名方案；属 §5 人工决策 |
| 5 | 前端 `usesVerifiedSource` 恒为 `false` | `frontend/src/App.vue` | 真实 `POST /api/v1/plan` 响应里**没有**来源核验字段；需要后端新增信号，属跨模块接口决策 |

---

## 6. 与"学业结论"的边界（⛔ 不可推定）

通过来源核验**只**说明"这份数据的来源与内容与批准记录一致"。
它⛔ **不**说明、也⛔ **不得**被用来推定：课程等价、毕业要求已满足、选课资格已获得、
或任何学分 / 期限 / 先修 / 跨校区规则已获学校正式解释。
这些仍然是既有模块里的 `possibly_equivalent` / `manual_confirmation` / 未决事项。
