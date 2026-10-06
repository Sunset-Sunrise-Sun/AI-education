# 真实开课数据采集 · 操作包（Course Data，2026-1）

> ⚠️ 本文只描述**由人类在授权登录会话中手动执行**的步骤。
> Builder ⛔ 不发真实请求、⛔ 不读取 cookie / token、⛔ 不绕认证、⛔ 不猜测未确证语义。
> 所有命令都是**可直接复制运行**的浏览器控制台片段（前提：已按既有方式加载
> `tools/sysu_course_offering_collector.js`，且当前页面为
> `https://jwxt.sysu.edu.cn` 的「全校开设课程」模块）。

## 0. 已批准的分片（`APPROVED_SHARDS`）

| 校区 | `openingSchoolNumber`（= `scope_id`） | `shard_id`（导出用名字） | 状态 |
| --- | --- | --- | --- |
| 东校园 | `5063559` | `东校园` | ✅ 可采集（已有旧 artifact，见 §4） |
| 南校园 | `5062201` | `南校园` | ✅ 可采集 |
| 深圳校区 | `333291143` | `深圳校区` | ✅ 可采集 |
| 珠海校区 | `5062203` | `珠海校区` | ✅ 可采集 |
| 北校园 | `5062202` | `北校园` | ⏸ **suspended**（真实证据为 `HTTP 600`；⛔ 不绕过、⛔ 不自行设计规避） |

## 1. ⚠️ 现状：**当前没有"单校区采集"入口**（必须由 Review 裁定）

现有唯一采集入口是：

```js
await window.XuehangSysuCollector.collectSharded({ semester, maxPages, delayMs })
```

它是**五个已批准 shard 的一次性、全有或全无事务**：

- `APPROVED_SHARDS` 固定为**五个**校区（含**北校园**），调用方**不能选择 shard**
  （options 白名单只有 `semester` / `maxPages` / `delayMs`）；
- 任一 shard 失败（含北校园已确证的 `HTTP 600`）⇒ **整体失败、不产出任何 bundle、不续采、不跳页**。

⇒ 因为**北校园按裁定保持 suspended**，一个五 shard 运行**预期会在北校园失败**，
因此 **East / South / Shenzhen / Zhuhai 目前无法通过现有入口单独取得 bundle**。

**这是当前真实数据链路的首要阻塞项（非 Builder 可自行解决）**，需要 Architecture Review 二选一：

| 选项 | 内容 | Builder 立场 |
| --- | --- | --- |
| A | 批准**新增一个已批准的"单校区采集"入口**（例如只接受一个已批准 `openingSchoolNumber`，产出**单个** campus bundle；不动五 shard 编排） | ⛔ 未获批准前**不实现** |
| B | 明确**允许在北校园 suspended 期间跳过该 shard**（等价于放宽"全有或全无"语义） | ⛔ 未获批准前**不改** `APPROVED_SHARDS` / 不跳过 |

⛔ 在获得上述任一裁定之前，**不要**运行五 shard 命令去"碰运气"（那会浪费一次真实请求配额，
且必然 fail closed）；也⛔ **不要**手工改动常量或绕过失败 shard。

## 2. 一旦获批（命令形态，供 Review 参考）

```js
// 选项 A 落地后的形态（名称以实际批准为准；⛔ 现在尚不存在）
const east = await window.XuehangSysuCollector.collectCampus({
  semester: "2026-1",
  openingSchoolNumber: "5063559",
  maxPages: 50,
  delayMs: 30000
});
```

| 校区 | `openingSchoolNumber` | 已知 `data.total` | 页数（= `ceil(total/200)`） | 预计耗时 |
| --- | --- | --- | --- | --- |
| 东校园 | `5063559` | **1071**（已有证据） | 6 | ≈ 3 分钟（5 次普通间隔 + 1 次批次冷却） |
| 南校园 | `5062201` | 运行时读出（⛔ 不预填） | 运行时决定 | 同上量级 |
| 深圳校区 | `333291143` | 运行时读出（⛔ 不预填） | 运行时决定 | 同上量级 |
| 珠海校区 | `5062203` | 运行时读出（⛔ 不预填） | 运行时决定 | 同上量级 |

pacing 仍为：相邻请求 ≥ 30 s；每 5 个成功请求后冷却 300 s（策略未改，⛔ 不可调小）。

**成功判据（单校区）**：`cancelled === false`；`accumulatedRows >= expectedTotal`；
`stoppedReason === "reached_total"`；导出成功（⛔ 拒绝未完成结果）。

## 3. 单校区导出命令（每个 shard 单独导出为裸 Capture Bundle）

```js
// 东校园（其余校区把名字换成 "南校园" / "深圳校区" / "珠海校区"）
copy(window.XuehangSysuCollector.toShardJson(result, "东校园"));
// 结构诊断（无 row 内容，可一并留存）
copy(window.XuehangSysuCollector.toDiagnosticsJson(result));
```

⚠️ `toShardJson(result, shardId)` 的 `shardId` 是**已批准校区名**（`东校园` 等）；
⛔ 只接受成功完成的采集结果；⛔ 找不到该 shard 时失败且不回显调用方给的名字。

⛔ 导出物**不得进入 Git**（真实材料规则）；保存在本地并记录其 SHA-256。

## 4. 各校区的导入元数据（`scope_kind` / `scope_id` / `source`）

| 校区 | `scope_kind` | `scope_id` | 建议 `source` 标签 | `expected_total` |
| --- | --- | --- | --- | --- |
| 东校园 | `campus` | `5063559` | `sysu-2026-1-east-campus` | 1071（**已有证据**：固定 artifact `daafdb18…a31b`） |
| 南校园 | `campus` | `5062201` | `sysu-2026-1-south-campus` | 运行时读出 |
| 深圳校区 | `campus` | `333291143` | `sysu-2026-1-shenzhen-campus` | 运行时读出 |
| 珠海校区 | `campus` | `5062203` | `sysu-2026-1-zhuhai-campus` | 运行时读出 |

导入（现有库函数，⛔ 不新增 wiring）：

```python
from app.course_data.captured_pages import load_capture_bundle
from app.course_data.store import SnapshotScope, import_offering_snapshot

snapshot = load_capture_bundle("east-campus.capture.json")
import_offering_snapshot(
    "course-data.sqlite",
    snapshot,
    artifact_sha256="<导出物的 SHA-256>",
    scope=SnapshotScope(scope_kind="campus", scope_id="5063559"),
)
```

## 5. 成功判据（逐条）

单校区（选项 A 落地后）：

1. `result.cancelled === false`；
2. `accumulatedRows >= expectedTotal`（取满）且 `stoppedReason === "reached_total"`；
3. 导出的 bundle 能被 `load_capture_bundle` 接受；
4. 若该校区是东校园：`Σ rows === 1071` 且 `pages === 6`（已有证据的口径）。

五 shard 运行（选项 B 落地后）：

1. `result.cancelled === false` 且 `result.shards.length === 5`；
2. 每个 shard 取满且 `stoppedReason === "reached_total"`；
3. `Σ shard expectedTotal === baseline_after 的 total`（覆盖一致；不一致即整体失败）；
4. `toShardJson(...)` 对每个校区都能成功导出（⛔ 拒绝未完成结果）。

## 6. `401` / `403` / `HTTP 600` / malformed 的停止说明

- 任一页返回 `401` / `403`：**立即整体停止**，错误信息标注 `【BLOCKED】`；
  ⛔ 不重试、⛔ 不刷新认证、⛔ 不读取 cookie/token、⛔ 不寻找其它 endpoint；
  **人工重新登录**后重新运行（这是唯一的恢复动作）。
- `HTTP 600`（真实证据：短间隔连续请求触发）：**立即整体停止**；
  ⛔ 不绕过、⛔ 不降级参数、⛔ 不自动等待重试。北校园即因此保持 suspended。
- 返回非 JSON（可能被重定向到登录页）/ JSON 结构不合法 / `data.total` 中途漂移：
  **立即整体停止**，不生成 bundle。
- 失败后 `result` 不存在 ⇒ ⛔ 不要手工拼造 bundle。

## 7. 与 Layout B 相关的**必须重抓**说明

- 本轮 collector 已对**精确 Layout B**（`weeks | location | opaque | activity`）
  把第 3 项脱敏为 `REDACTED_OPAQUE`；parser 只接受这个占位符。
- **旧的东校园 artifact 含原始 opaque 取值** ⇒ 在本 parser 下会在 Layout B 处 fail closed
  ⇒ **必须重抓东校园**（§1 命令已包含东校园；导出后替换旧 artifact）。
- ⛔ 不要手工编辑旧 artifact、⛔ 不要把原始取值改成占位符 —— 那是伪造采集证据。

## 8. 可选（development-only，非必需）

- 「一次性 Layout B 诊断」与「分段式 f3 字段来源诊断」**保留但非必需**：
  裁定已确认 Layout B 的字段语义为 `weeks | location | opaque | activity`，
  因此这两个诊断**不再是采集或导入的前置条件**，仅在将来需要复核字段来源时使用。
- 两个诊断都**只发读取请求**、不落盘、不进 bundle；⛔ 不得用于替代正式采集。
