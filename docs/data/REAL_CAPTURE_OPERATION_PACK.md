# 真实开课数据采集 · 操作包（Course Data，2026-1）

> ⚠️ 本文只描述**由人类在授权登录会话中手动执行**的步骤。
> Builder ⛔ 不发真实请求、⛔ 不读 cookie / token、⛔ 不绕认证、⛔ 不猜未确证语义。
>
> 前提：已按既有方式在 `https://jwxt.sysu.edu.cn` 的「全校开设课程」模块加载
> `tools/sysu_course_offering_collector.js`。

---

## A. 用户只需要做的 9 步（极简清单）

1. 登录教务系统（人工，⛔ 不由 Agent 代做）；
2. 东校园：复制 §C.1 命令 → 导出 → 保存为本地文件；
3. 南校园：复制 §C.2 命令 → 导出 → 保存；
4. 深圳校区：复制 §C.3 命令 → 导出 → 保存；
5. 珠海校区：复制 §C.4 命令 → 导出 → 保存；
6. 把 4 个 artifact（或其路径 + SHA-256）交给 Agent；
7. Agent 执行导入 + provenance read-back（§E）；
8. 最终 Architecture Review（含 North suspended 的完整性口径，§G）；
9. 用户明确"合并"。

> 北校园（`north-campus`）**保持 suspended**，⛔ 本清单不包含它，
> 也⛔ 不得用任何其它方式补全。

---

## B. 已批准校区与内部映射（单一真源在 collector 内）

| capture `shardId` | `shard_id`（已批准中文名） | `openingSchoolNumber` | 历史基线 total | 状态 |
| --- | --- | --- | --- | --- |
| `east-campus` | 东校园 | `5063559` | 1071 | ✅ 可采集 |
| `south-campus` | 南校园 | `5062201` | 2898 | ✅ 可采集 |
| `shenzhen-campus` | 深圳校区 | `333291143` | 1171 | ✅ 可采集 |
| `zhuhai-campus` | 珠海校区 | `5062203` | 1335 | ✅ 可采集 |
| `north-campus` | 北校园 | `5062202` | 405 | ⏸ **suspended**（真实 `HTTP 600`） |

⚠️ **历史基线只作参考/交叉核对**：真实运行一律以**当次响应**的 `data.total` 为准
（⛔ 不预填、⛔ 不因为对不上基线就重试或改参数）。

---

## C. 每个校区一条可直接复制的采集命令

> ✅ 调用方**只能**传 `shardId`（白名单值）；⛔ 不能传 `openingSchoolNumber`
> —— 号码由采集器内部固定映射，冒充已批准 shard 会被拒绝。
> ⛔ `maxPages` 不要调小（必须取满当次 `data.total`）；⛔ `delayMs` 只能 ≥ 30000。
> ⚠️ 超过 smoke 上限会先弹一次确认框；取消则不发出任何请求。

### C.1 东校园

```js
const east = await window.XuehangSysuCollector.collectApprovedShard({
  semester: "2026-1", shardId: "east-campus", maxPages: 50
});
east.shard; east.requests; east.expectedTotal;   // 自检：shard_id / 请求数 / 当次 total
copy(window.XuehangSysuCollector.toJson(east));  // → 保存为 east-campus.capture.json
```

| 项 | 值 |
| --- | --- |
| 预计页数（基线口径） | 6（= `ceil(1071 / 200)`） |
| 预计请求数 | 6 |
| 预计耗时 | ≈ 2.5 分钟（5 × 30 s） |
| 成功判据 | `cancelled === false`；`stoppedReason === "reached_total"`；`accumulatedRows === expectedTotal`；`toJson` 成功 |
| scope_kind / scope_id | `campus` / `5063559` |
| canonical source label | `sysu-2026-1-east-campus` |

### C.2 南校园

```js
const south = await window.XuehangSysuCollector.collectApprovedShard({
  semester: "2026-1", shardId: "south-campus", maxPages: 50
});
south.shard; south.requests; south.expectedTotal;
copy(window.XuehangSysuCollector.toJson(south));   // → south-campus.capture.json
```

| 项 | 值 |
| --- | --- |
| 预计页数（基线口径） | 15（= `ceil(2898 / 200)`） |
| 预计请求数 | 15 |
| 预计耗时 | ≈ 16 分钟（12 × 30 s + 2 次批次冷却 × 300 s） |
| scope_kind / scope_id | `campus` / `5062201` |
| canonical source label | `sysu-2026-1-south-campus` |

### C.3 深圳校区

```js
const shenzhen = await window.XuehangSysuCollector.collectApprovedShard({
  semester: "2026-1", shardId: "shenzhen-campus", maxPages: 50
});
shenzhen.shard; shenzhen.requests; shenzhen.expectedTotal;
copy(window.XuehangSysuCollector.toJson(shenzhen)); // → shenzhen-campus.capture.json
```

| 项 | 值 |
| --- | --- |
| 预计页数（基线口径） | 6（= `ceil(1171 / 200)`） |
| 预计请求数 | 6 |
| 预计耗时 | ≈ 2.5 分钟 |
| scope_kind / scope_id | `campus` / `333291143` |
| canonical source label | `sysu-2026-1-shenzhen-campus` |

### C.4 珠海校区

```js
const zhuhai = await window.XuehangSysuCollector.collectApprovedShard({
  semester: "2026-1", shardId: "zhuhai-campus", maxPages: 50
});
zhuhai.shard; zhuhai.requests; zhuhai.expectedTotal;
copy(window.XuehangSysuCollector.toJson(zhuhai));   // → zhuhai-campus.capture.json
```

| 项 | 值 |
| --- | --- |
| 预计页数（基线口径） | 7（= `ceil(1335 / 200)`） |
| 预计请求数 | 7 |
| 预计耗时 | ≈ 3 分钟 |
| scope_kind / scope_id | `campus` / `5062203` |
| canonical source label | `sysu-2026-1-zhuhai-campus` |

---

## D. 导出的 bundle 是什么（⛔ 不得人工编辑）

- `toJson(...)` 输出**标准裸 Capture Bundle**：
  `format` / `semester` / `first_page_no` / `page_size` / `pages`；
  ⛔ **不含** source label、校区号或诊断元数据（它们只出现在 JS 返回值里）。
- ⛔ **不得人工编辑 artifact**（不得改字段、不得把原始 opaque 取值改成占位符、
  不得补页 / 删页 / 改页码）—— 那是伪造采集证据。
- 保存后计算 SHA-256 并记录：

```powershell
Get-FileHash .\east-campus.capture.json -Algorithm SHA256
```

```bash
sha256sum east-campus.capture.json
```

---

## E. 导入 + provenance read-back（Agent 执行；现有库函数，⛔ 不新增 wiring）

```python
from app.course_data.captured_pages import load_capture_bundle
from app.course_data.store import (
    SnapshotScope, import_offering_snapshot,
    load_course_data_provenance, load_course_offerings,
    compute_artifact_sha256,
)

raw = open("east-campus.capture.json", "rb").read()
digest = compute_artifact_sha256(raw)          # 与 §D 的 SHA-256 核对
snapshot = load_capture_bundle("east-campus.capture.json")

import_offering_snapshot(
    "course-data.sqlite", snapshot,
    artifact_sha256=digest,
    scope=SnapshotScope(scope_kind="campus", scope_id="5063559"),
)

load_course_offerings("course-data.sqlite", semester="2026-1")   # 读回
load_course_data_provenance("course-data.sqlite")                # 审计记录
```

⛔ 不完整（`partial`）快照**不入库**；⛔ 导入失败后**不得**假设数据库零写入
（事务边界见 `backend/tests/test_course_data_store.py`）。

> 单 campus CLI（`tools/validate_course_data_artifact.py`）**只能**声明
> `scope_kind = campus`；这四份 artifact 导入后得到的是**四个 campus acceptance**，
> **不是** full-semester acceptance。

---

## E2. 五 shard → full-semester acceptance（Agent 执行；⛔ 五份齐备才可能）

```bash
python tools/accept_full_semester_course_data.py \
  --semester 2026-1 \
  --baseline-before <采集窗口前的 total> \
  --baseline-after  <采集窗口后的 total> \
  --east east-campus.capture.json --south south-campus.capture.json \
  --shenzhen shenzhen-campus.capture.json --zhuhai zhuhai-campus.capture.json \
  --north north-campus.capture.json \
  --inventory ./capture-inventory.json \
  --campus-store ./campus-acceptances.sqlite \
  --output-manifest ./full-semester-acceptance-manifest.json \
  --sqlite ./course-data.sqlite
```

- **五个 `--<campus>` 参数全部必填**：⛔ 没有 `--skip-north` /
  `--allow-partial-semester` / `--force-complete`；
- **`--campus-store` 必填**：五个校区必须先各自跑一次 **campus CLI**
  （§E）把 artifact 以 `campus` scope 正式入库 —— 这是 B2 的独立 scope 绑定来源，
  ⛔ "调用方说这是 East" 本身不是证据；
- **`--inventory` 必填**：一份**经审核**的 capture inventory
  （`(semester, shard_id, openingSchoolNumber, raw_bundle_sha256)`）。
  可以先让本工具生成**草稿**（⛔ 草稿不是批准，只记录 digest）：

  ```bash
  python tools/accept_full_semester_course_data.py \
    --semester 2026-1 --east … --south … --shenzhen … --zhuhai … --north … \
    --draft-inventory ./capture-inventory.json
  ```

  草稿由人 / Review 核对（对照 §D 手工记录的 SHA-256）后再用于正式 acceptance；
  ⛔ 工具无法证明某个 inventory 被批准过；
- `baseline-before` / `baseline-after` = collector 报告的**全学期总数**（⛔ 不是快照）；
  两者必须相等，且必须等于**五份** shard 的 `reported_total` 之和；
- 成功输出 `manifest_sha256`（acceptance identity）与 `merged_offering_set_sha256`
  （规范化内容的确定性 digest）；manifest 文件字节的 SHA-256 **就是** acceptance identity；
- ⛔ **North 当前拿不到** ⇒ 这一步**现在无法完成**；
- 细节与失败类别（退出码 2–10）：`docs/data/FULL_SEMESTER_ACCEPTANCE.md`。

---

## F. 401 / 403 / HTTP 600 / malformed / total 漂移 时如何停止

- **401 / 403**：立即整体停止（错误标注 `【BLOCKED】`）。⛔ 不重试、⛔ 不刷新认证、
  ⛔ 不读 cookie/token、⛔ 不换 endpoint、⛔ 不降级参数。
  **唯一恢复动作 = 人工重新登录**后重新运行该校区命令。
- **HTTP 600**：立即整体停止（北校园即因此 suspended）。⛔ 不绕过、⛔ 不自动等待重试。
- **malformed / total 漂移 / 未取满**：立即整体停止，**不产出 bundle**；⛔ 不要手工拼造。

---

## G. 完整性口径（⛔ 不得混淆）

```text
East + South + Shenzhen + Zhuhai 四个校区 complete
      ≠  full semester complete
```

- 北校园仍是**已批准 shard 之一**；Python 侧入口 `collect_sharded_capture_set()` **没有**
  "跳过 / suspended"概念 ⇒ 缺任一已批准 shard 一律 fail closed
  （见 `backend/tests/test_course_data_campus_scope_completeness.py`）。
- 因此单校区采集得到的都是 **campus-scoped** artifact：
  导入时必须声明 `scope_kind="campus"`；⛔ **不得**声称为 `full_semester`。
- ⛔ **不得**把 North 缺失伪装成 full-semester complete；
  如需学期级 complete，只能等 North 可采集，或由 Architecture Review 正式裁定口径。
- **full_semester 的唯一入口** = `tools/accept_full_semester_course_data.py`
  （五个 `--<campus>` 全必填；⛔ 无逃生参数）；单 campus CLI 无法表达 `full_semester`。

---

## H. 可选（development-only，非采集/导入前置条件）

- 一次性 Layout B 诊断（`diagnoseLayoutBCandidates`）与分段式 f3 字段来源诊断
  （`diagnoseLayoutBFieldSourcePart` + `finalizeLayoutBFieldSource`）分类为
  **development-only / safe-to-remove-after-final-East-acceptance**：
  ⛔ 不被 production 引用、⛔ 不自动运行、⛔ 不读认证、⛔ 不污染 bundle。
