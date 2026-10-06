# Case A Production Runtime Wiring（Gate C）

> 实现：`backend/app/services/planning_runtime.py`
> ⛔ 不改 frozen Provider contract、⛔ 不改 public Schema、⛔ 不改 `PlanningOrchestrator`、
> ⛔ 零网络、⛔ 不读认证材料、⛔ 不复用 PR #39 的单 bundle 装载模型。

## 结论：PR #39 被**取代**（superseded），⛔ 不合并

`feature/case-a-runtime-wiring`（PR #39）的 Course Data 侧模型是

```text
一个 Capture Bundle 路径 + 一个 raw bytes SHA-256  →  SnapshotCourseDataProvider（内存快照）
```

真实数据现在已经是

```text
五校区 raw artifact → full-semester acceptance（manifest SHA-256）→ SQLite → 按 acceptance 绑定的行
```

而单份 campus bundle **不能**证明 whole-semester 完整性
（`campus complete != full semester complete`），把它当成"该学期教学班"返回属于**静默不完整**。
因此本 Gate 按 `docs/data/RUNTIME_AND_FRONTEND_COMPATIBILITY_REVIEW.md` §1.2 的**方案 (b)** 落地：

```text
PR #39 as-is = FROZEN / DO NOT MERGE
本模块       = 其 successor（Curriculum / Planner 侧沿用同一套受控校验）
```

## 环境契约（五个变量，全部显式）

| 变量 | 语义 |
| --- | --- |
| `APP_REAL_CASE_A_ENABLED` | `1` = 启用；未设置或 `0` = 关闭；其它取值 ⇒ `invalid_runtime_configuration` |
| `APP_CASE_A_CURRICULUM_CASE_PATH` | **真实** Case A manifest 的本地路径 |
| `APP_COURSE_DATA_SQLITE_PATH` | 本地 Course Data SQLite 库路径 |
| `APP_COURSE_DATA_SEMESTER` | 该 acceptance 绑定的学期 |
| `APP_COURSE_DATA_ACCEPTANCE_SHA256` | **正式** full-semester acceptance 的 manifest SHA-256（64 hex，大小写均可） |

⛔ 单 bundle 的旧变量名（`APP_COURSE_SNAPSHOT_*`）**不存在**，也没有 `--campus` 之类的降级开关。

## 装配结果

```text
CurriculumCaseProvider（受控 Case A 校验）
   + StoreBackedCourseDataProvider（full_semester acceptance 绑定）
   + RestrictedPlannerProvider（deterministic restricted planner）
        ↓
PlanningOrchestrator
```

Curriculum 侧校验（与 PR #39 同一套，未放宽）：

```text
case.data_source               == real
case.new.version_id            == case-a-new
case.makeup_scope.as_of_term   == 2025-2
case.confirmed_scope_decisions == 已批准决策集合
provider.get_makeup_tasks()     构造期即可成功
```

Course Data 侧校验：全部由 `StoreBackedCourseDataProvider` 在构造期完成
（恰好一条 `full_semester` provenance + `complete` + 计数自洽 + **实际绑定行数 == offering_count**）。

## fail closed 与诊断码

`build_planning_runtime(environment)` 返回
`PlanningRuntimeInspection(orchestrator, reason)`；诊断码**不含路径 / 配置取值 / 输入内容**：

| reason | 含义 |
| --- | --- |
| `runtime_disabled` | 未启用（缺省即关闭） |
| `invalid_runtime_configuration` | 开关值非 `0`/`1`，或 digest 形态非法 |
| `curriculum_not_ready` | case 缺失 / 非法 / 未标记 real / 不是 Case A / 决策未获批准 / projection 失败 |
| `course_data_not_ready` | 库缺失 / 非 Course Data 库 / 无匹配的 full_semester acceptance / 计数不符 / 行被覆盖 / semester 不匹配 |
| `ready` | production runtime 可用 |

⛔ **没有 Mock fallback**：任何一步失败 ⇒ `get_planning_orchestrator()` 返回 `None`
⇒ `POST /api/v1/plan` 明确 `503 real_pipeline_not_configured`（⛔ 不回退到 `/api/v1/mock/*`）。
⛔ **没有 campus fallback**：campus-only 库 / 单校区数据一律 `course_data_not_ready`。

⚠️ **每次请求重新装配**（不缓存 orchestrator）：acceptance 绑定、行数与 case 就绪状态在每个请求上
重新验证 ⇒ 启动之后被改写 / 被覆盖的库不会继续被使用。

## `POST /api/v1/plan` 的真实语义

- 未装配（含全部 fail-closed 情形）⇒ `503 real_pipeline_not_configured`，且**不带**
  `X-Data-Source` 头；
- 已装配 ⇒ 200 `PlanResult`（公共 Schema 校验通过），同样**不带** `X-Data-Source` 头；
- 请求里的 `semester` 与所绑定学期不一致时，Provider 会 fail closed（异常上抛，⛔ 不返回空列表、
  ⛔ 不 fallback）。⚠️ 该情形的 HTTP 状态码映射（4xx/5xx）属于 **API 决策，本 Gate 未改**；
- Provider 运行期异常继续上抛，⛔ 不被吞成 200 / Mock 结果。

## 测试

`backend/tests/test_planning_runtime.py`（**47 passed**，synthetic / zero-network）
+ `test_real_plan_api.py` / `test_mock_api.py` / `test_integration_orchestrator.py` /
`test_planner_provider.py` 回归（合计 **307 passed**）：

```text
缺省关闭 / 显式关闭 / 非 0-1 开关值
缺 curriculum 路径 / 缺任一 course data 变量 / digest 形态非法 / 大写 digest 归一化
case 缺失 / 被标记 mock / 目标版本不符 / scope 截止学期不符 / 决策与已批准集合不符
库缺失 / 非 Course Data 库 / campus-only 库 / 错 digest / 错 semester
ready：三个 Provider 类型与绑定学期、Curriculum 投影出 makeup task
planner 收到**恰好**绑定行 + preference / current_schedule 原样传递
启动后库被改写 ⇒ fail closed，且重新装配同样失败
未装配 ⇒ 503（无 X-Data-Source）；campus-only 库 ⇒ 503
已装配 ⇒ 200 + PlanResult 通过公共 Schema；mock 通道仍带 X-Data-Source: mock
源码级：⛔ 不 import mock 通道 / 快照 Provider / 网络库；⛔ 无旧单 bundle 变量名
```

mutation sweep（`mutate_planning_runtime.py`，development-only）：**16 killed / 1 可证等价 / 0 survived**；
等价项 = "版本必须等于 Case A 目标版本"，其**冗余性由 test 证明**
（已批准决策绑定在 `case-a-new` 上，换版本后 Curriculum 层自身就会拒绝）。

## 仍未做 / 未声称

- ⛔ 未处理任何真实 artifact / 未真实登录 ⇒ formal Real E2E 继续 **LEVEL0**；
- ⛔ 未 merge PR #39（只在文档中标记 superseded）；
- ⛔ 未给真实 API 增加 `X-Data-Source: real` 响应头（属接口面变更，仍需裁定）；
- ⛔ 未在 runtime 中硬编码 "Case A 的计划学期"：学期由 `APP_COURSE_DATA_SEMESTER` 显式给出，
  并由 acceptance 绑定强制（operator 必须配置与已批准 acceptance 一致的学期）。
