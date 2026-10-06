# Runtime / Frontend 兼容性审计（Course Data → Runtime → Real E2E 前置）

> 只做**兼容性分析与结论**；⛔ 不改 runtime architecture、⛔ 不改 frozen Provider contract、
> ⛔ 不改 public Schema。所有判断都给出可复核的文件/行证据。

## 0. 结论速览

| 阶段 | 结论 |
| --- | --- |
| Phase 6 runtime 兼容性 | **B —— PR #39 需要小改**（不是可直接复用，也不是必须重写） |
| Phase 7 synthetic dry-run | ✅ 结构 dry-run 的**语义**已被现有测试覆盖并锁定（见 §2 证据）；真实 E2E 仍需真实 artifact |
| Phase 8 frontend | ✅ 全部兼容（见 §3，逐条给证据）；发现 **1 处 API 层标识缺口**（非显示 bug） |
| 诊断代码分类（Phase 9） | ✅ development-only / safe-to-remove-after-final-East-acceptance |

---

## 1. Phase 6 —— runtime 兼容性（结论 **B**）

### 1.1 PR #39 的装载模型（证据）

- PR #39（`feature/case-a-runtime-wiring`，commit `a4dc48ce…`，**open / 未合并**，
  base = `main` `21f558f`）标题与描述：
  *"Real Case A runtime wiring + approved snapshot SHA-256 gate"*；
  它把 `CurriculumCaseProvider` + `SnapshotCourseDataProvider` + `RestrictedPlannerProvider`
  装进 runtime，并**在解析前**校验**单个** artifact
  `APP_COURSE_SNAPSHOT_PATH` 的原始字节 SHA-256 是否等于 `APP_COURSE_SNAPSHOT_SHA256`。
- 因此 PR #39 的装载模型 = **一个 Capture Bundle + 一个 SHA-256 + 一个内存快照**。
- 现在 Course Data 侧已经变成：

  ```text
  collectApprovedShard()  → 每校区一个标准 bundle（campus-scoped）
        ↓ load_capture_bundle + import_offering_snapshot(scope=campus:xxxx)
  SQLite store（artifact/scope 审计 + capacity provider）
        ↓ merge_offering_snapshots() / collect_sharded_capture_set()
  合并后的 full-semester OfferingSnapshot（**要求五个已批准 shard 齐备**）
  ```

### 1.2 为什么是 B（而不是 A / C）

- **不是 A**：单 SHA gate 只能锁**一个** artifact；而真实数据现在是
  **每校区一份 artifact**（4 份可采集 + North suspended）。
  用单 gate 装一份 campus artifact 会得到一个**仅覆盖该校区的快照**，
  却会被 `SnapshotCourseDataProvider.get_course_offerings(semester)` 当作
  "该学期的教学班"返回（`snapshot.py`：学期匹配即整表返回，⛔ 无 scope 标记），
  对下游是**静默不完整**。
- **不是 C**：`CourseDataProvider` 的 frozen contract
  `get_course_offerings(semester) -> list[CourseOffering]` **不需要改**；
  store 侧也已经能按学期读出 offerings（`load_course_offerings`）。
  缺的只是"**装载范围声明 + 多 artifact 入口**"这一层薄封装。
- **所以是 B**：需要**小改**（新增声明与入口，不动 contract、不动 Schema）：

  ```text
  ① 装载范围必须显式声明（不得推断）：
     APP_COURSE_SNAPSHOT_SCOPE = "campus:5063559" | "full_semester:2026-1"
     ⇒ 与 SnapshotScope 的语义一致；⛔ 不从文件名 / source label / 校区数推断
  ② 多 artifact 支持（二选一，均不改变 frozen contract）：
     (a) 运行期把 N 份 campus artifact 合并成一份 snapshot 后再构造 provider；或
     (b) 允许把所有 artifact 先经 store 落库，再由一个
         StoreBackedCourseDataProvider 调 load_course_offerings(semester) 供数
  ③ 若范围是 campus：必须在 API 响应 / provenance 中**如实标注**
     "本次只覆盖该校区"，⛔ 不得声称 semester complete
  ```

### 1.3 必须保持不变（frozen / 禁止改动）

- `CourseDataProvider.get_course_offerings(semester)` —— **签名与语义不变**；
- `CurriculumProvider` / `PlannerProvider` —— 不变；
- `503 real_pipeline_not_configured` 契约 —— 不变（未装配即 503，⛔ 不 Mock fallback）；
- public Schema / `data_source` 语义 —— 不变；
- ⛔ **不把 PR #39 直接 merge 进本分支**（跨分支 runtime 变更属于 Review 决定项）。

### 1.4 需要 Review 裁定的一件事

在 North suspended 的前提下，runtime 允许装载的**最高范围**是什么：
`campus`（每校区一份 artifact）还是 `full_semester`（必须等 North 可采集）？
本文**不替** Review 决定；在此之前 runtime 一律保持未装配（503）——
这正是当前 production 的实际状态。

### 1.5 Gate C 落地（2026-10-06，本文写于其之前，保留原文以存证）

上文 §1.2 的**方案 (b)** 已按既有 runtime 决定落地：

```text
production runtime 只接受 **显式 full_semester acceptance**（SQLite + manifest SHA-256）
⛔ campus 不作为可装载范围（campus-only 库 ⇒ course_data_not_ready ⇒ 503）
```

- 实现：`backend/app/services/planning_runtime.py` +
  `StoreBackedCourseDataProvider`（见 `docs/data/CASE_A_RUNTIME_WIRING.md`）；
- **PR #39 = FROZEN / DO NOT MERGE**（其单 bundle 装载模型已被取代）；
- ⛔ 本文 §3.1 的 `X-Data-Source: real` 建议**仍未实施**（接口面变更仍需裁定）；
- ⛔ §1.4 的"campus 是否可作为最高范围"已由**既有决定**回答：**否**；
  若 Review 日后要放宽，必须走新的 Gate（本 Gate 未提供任何 campus 路径）。

---

## 2. Phase 7 —— synthetic 结构 dry-run（证据，不是真实 E2E）

⛔ 本文**不声明** Real E2E / LEVEL2 / LEVEL3 已通过；以下是**结构**语义的现有测试证据：

| 要求 | 证据 |
| --- | --- |
| 无 Mock fallback | `backend/tests/test_real_plan_api.py::test_provider_error_propagates_without_mock_fallback`、`::test_mock_demo_remains_separate_and_marked` |
| 未装配 → 503 | `::test_unconfigured_runtime_returns_503_without_mock_plan`（断言 `detail.error == "real_pipeline_not_configured"`） |
| provider 异常向上传播 | `::test_provider_error_propagates_without_mock_fallback`（`pytest.raises(ProviderBoom)`） |
| `meetings=[] → Planner UNKNOWN` | `backend/app/planner/conflicts.py:85`：`CLEAR if offering.meetings else UNKNOWN`；`planner/feasibility.py:13/45/57` 同样按 UNKNOWN 处理 |
| Layout A/B 不被误当 CLEAR | 同上：Layout A/B 产出 `meetings=[]` ⇒ 只能是 UNKNOWN；`backend/tests/test_planner_conflicts.py` / `test_planner_section_repair.py` |
| `selected > capacity` / `remaining_capacity=None` 不破坏 Planner | `backend/tests/test_planner_conflicts.py`、`test_planner_provider.py`；Course Data 侧 `remaining_capacity=None` 由 `test_course_data_normalization.py` 锁定 |
| provider 只被调用一次且数据保真 | `::test_configured_pipeline_calls_each_provider_once_and_preserves_data` |
| 真实/ Mock 不混用 | `::test_real_plan_rejects_mock_or_missing_current_schedule_source`、`::test_real_api_and_runtime_do_not_import_mock_replay` |

⚠️ 因此 Phase 7 的**结构**子集已满足；真正未满足的只有
"用**真实 2026-1 artifact** 跑一次端到端"，它被 North suspended + 需要真实登录阻塞。

---

## 3. Phase 8 —— frontend 兼容性审计（全部 ✅，1 处 API 层缺口）

| 要求 | 结论 | 证据 |
| --- | --- | --- |
| `meetings=[]` 用中性文案 | ✅ | `frontend/src/utils/labels.ts:142` `EMPTY_MEETINGS_DATA_TEXT = '当前数据中无排课信息'`；`CourseOfferingList.vue:169-175` 仅在 `meetings.length > 0` 时渲染具体排课 |
| 不显示 conflict-free | ✅ | `labels.ts:139-140` 与 `CourseOfferingList.vue:15-16` **明文禁止**"无课 / 无需上课 / 异步课程 / 尚未排课 / 无冲突"等推断词；全仓 grep 无 `conflict-free` 文案 |
| `remaining_capacity=None` 不显示 0 | ✅ | `CourseOfferingList.vue:192` 用 `displayOrDash()`；`labels.ts:131-136`：`null/undefined/''` → `'—'` |
| Real vs Mock 标识清晰 | ✅ | `App.vue:78-82` `planResultMode = real \| mock`；`App.vue:90-93` 规定 Real 结果**必须**传空课程名映射（防止 Mock 课程名污染 Real 结果） |
| `selected_classes` 不写成"已选课" | ✅ | 全仓 grep **无** `已选课` 文案 |
| `feasible` 不写成"可直接执行" | ✅ | 全仓 grep **无** `可直接执行` 文案 |
| source/audit label 不当作 provenance proof | ✅（前端侧） | `TopStatusBar.vue:36-42` 显示的是**后端响应标头**（"后端数据源标头"），不是 artifact 的 source label |
| 503 不触发 Mock fallback | ✅ | `frontend/src/api/plan.ts:7` 明文"绝不 fallback 到 `/api/v1/mock/demo`"；`:32-37` 只有 503 且 `detail.error === 'real_pipeline_not_configured'`（或 503 无法解析）才判为未装配，其它 5xx 归 `server` |

### 3.1 发现（非显示 bug，属 API 层标识）

- `X-Data-Source` 响应头**只由 mock API 设置**
  （`backend/app/api/mock.py:37` `MOCK_DATA_SOURCE_HEADER = "X-Data-Source"`），
  真实的 `POST /api/v1/plan` **不返回**该头。
- 影响：调用方无法从**响应本身**区分"真实链路结果"与"未标记结果"，
  只能依赖 UI 模式（`planResultMode`）。
- ⛔ 本文**不擅自**给真实 API 加响应头（那是接口面变更，需 Review）。
  **建议（需裁定）**：真实 `POST /api/v1/plan` 返回 `X-Data-Source: real`
  （或等价机器可读标记），与 mock 的 `mock` 对称；
  这与 Phase 7 的"`X-Data-Source` 语义正确"要求直接相关。

---

## 4. Phase 9 —— 诊断代码分类

| 入口 | 分类 | 依据 |
| --- | --- | --- |
| `diagnoseSchedulePresence` / `diagnoseMissingScheduleCorrelation`（2C1B / 2C1C） | development-only，safe-to-remove-after-final-East-acceptance | 不被 production 引用；只读第 1 页；不落盘 |
| `diagnoseLayoutBCandidates`（七计数 + 字段来源直方图） | **safe-to-remove-after-final-East-acceptance** | Layout B 语义已裁定（`weeks \| location \| opaque \| activity`），其使命完成；仍保留以便将来复核字段来源 |
| `diagnoseLayoutBFieldSourcePart` + `finalizeLayoutBFieldSource`（方案 D 分段诊断） | 同上（development-only） | 六字段契约、零敏感 checkpoint；⛔ 不含 activity-membership 计数 |
| `collectApprovedShard`（单校区采集） | **production-needed** | 真实数据获取的唯一可用入口（五校区编排被 North suspended 阻塞） |

共同保证（已由静态守卫锁定）：⛔ 不被 production 引用、⛔ 不自动运行、⛔ 不读认证、
⛔ 不泄露 raw value、⛔ 不污染 Capture Bundle、bundle 输出不依赖任何 diagnostic state。
