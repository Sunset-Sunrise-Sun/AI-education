# Five-shard Full-Semester Acceptance

> 内部工具：`tools/accept_full_semester_course_data.py`
> 内部 orchestration：`backend/app/course_data/full_semester_acceptance.py`
> ⛔ 零网络、⛔ 不读认证、⛔ 不改 Capture Bundle 格式、⛔ 不改公共 Schema、
> ⛔ 不让单 campus CLI 表达 `full_semester`。

## 为什么需要独立入口

`tools/validate_course_data_artifact.py`（single-bundle campus CLI）**只**能产生
`campus` acceptance：裸 Capture Bundle 不携带可验证 scope，而

```text
campus complete != full semester complete
```

`full_semester` 只能由**五个已批准校区**的 raw artifact + **采集窗口的总量证据**
+ **独立批准的 capture inventory** 共同证明。因此这是一个**独立**入口。

## 四个 BLOCK 的修复（Forward Red-Team，2026-10-06）

| BLOCK | 风险 | 修复 |
| --- | --- | --- |
| **B1** | digest 对 bytes A 计算，parser 又重开路径读 bytes B | **只读一次**：digest 与 JSON 解析吃**同一批** bytes（`load_capture_bundle_bytes()`）；复读只作为额外变动探测 |
| **B2** | 调用方自称 "这是 East" 就被当成 East | 正式 acceptance 消费**已批准 capture inventory** + **已导入的 campus acceptance 记录**，逐项核对 digest / scope_id / source / counts / 内容 digest |
| **B3** | 同数量 / 同身份的**内容替换**可逃过 gate | `merged_offering_set_sha256`（规范化内容的确定性 SHA-256）+ 逐行 `offering_payload_sha256` |
| **B4** | Provider 构造成功后 acceptance 失效仍继续服务 | 每一次读取都在**一致读事务**里重新核对两个平面 + membership + 逐行内容指纹（见 `STORE_BACKED_COURSE_DATA_PROVIDER.md`） |

## 使用（正式 acceptance）

```bash
# ① 每个校区先跑 campus CLI（产生独立的 campus acceptance 记录）
python tools/validate_course_data_artifact.py \
  --bundle ./east-campus.capture.json --expected-semester 2026-1 \
  --scope-id 5063559 --source capture://sysu/2026-1/campus/5063559 \
  --sqlite ./campus-acceptances.sqlite
# …南 / 深圳 / 珠海 / 北各一次

# ② （可选）生成 inventory **草稿**：只是记录 digest，⛔ 不是批准
python tools/accept_full_semester_course_data.py \
  --semester 2026-1 --east … --south … --shenzhen … --zhuhai … --north … \
  --draft-inventory ./capture-inventory.json

# ③ 由人 / Review 审核该 inventory（本工具无法证明它被批准过）

# ④ 正式 acceptance
python tools/accept_full_semester_course_data.py \
  --semester 2026-1 \
  --baseline-before 6880 --baseline-after 6880 \
  --east ./east-campus.capture.json --south ./south-campus.capture.json \
  --shenzhen ./shenzhen-campus.capture.json --zhuhai ./zhuhai-campus.capture.json \
  --north ./north-campus.capture.json \
  --inventory ./capture-inventory.json \
  --campus-store ./campus-acceptances.sqlite \
  [--output-manifest ./full-semester-acceptance-manifest.json] \
  [--expected-manifest-sha256 <64 hex>] \
  [--sqlite ./course-data.sqlite]
```

## capture inventory（B2 的独立信任来源）

```json
{"format":"sysu-course-data-capture-inventory-v1","inventory_version":1,
 "semester":"2026-1",
 "shards":[
   {"shard_id":"east-campus","openingSchoolNumber":"5063559","raw_bundle_sha256":"<64 hex>"},
   {"shard_id":"south-campus","openingSchoolNumber":"5062201","raw_bundle_sha256":"<64 hex>"},
   {"shard_id":"shenzhen-campus","openingSchoolNumber":"333291143","raw_bundle_sha256":"<64 hex>"},
   {"shard_id":"zhuhai-campus","openingSchoolNumber":"5062203","raw_bundle_sha256":"<64 hex>"},
   {"shard_id":"north-campus","openingSchoolNumber":"5062202","raw_bundle_sha256":"<64 hex>"}]}
```

严格要求：

- **exact five-shard**、号码必须等于已批准值、digest 必须 64 位小写 hex；
- ⛔ 无未知字段、⛔ 无重复 JSON key、⛔ 无 NaN / Infinity、⛔ 无 BOM；
- 五个 digest **两两不同**（同一批字节不得声明成两个校区）；
- 必须**已经是 canonical 形式**（键排序 + 紧凑分隔符 + 批准顺序）；
  ⛔ 非 canonical ⇒ fail closed（inventory 是审核产物，其 SHA-256 必须稳定）。

## 正式流程

```text
已批准 inventory + 5 份 raw artifact + 5 份 campus acceptance 记录
      ↓  只读一次：raw bytes → SHA-256 → load_capture_bundle_bytes(**同一批 bytes**)
      ↓  raw digest == inventory digest（⛔ 含 whitespace-only 变化）
      ↓  五个 raw digest 两两不同
      ↓  collect_captured_pages_snapshot(source = 该校区 campus label)
      ↓  快照 complete 且非空
      ↓  campus acceptance 核对：
           artifact_sha256 == raw digest
           scope_kind == campus；scope_id == inventory.openingSchoolNumber
           source == capture://sysu/<semester>/campus/<openingSchoolNumber>
           loaded_count == reported_total == offering_count == 本 shard 解析计数
           offering_set_sha256 == 本 shard 解析结果的整批内容 digest
      ↓  跨 shard identity 无重复 / 无冲突
      ↓  baseline_before == baseline_after；Σ reported_total == baseline
      ↓  merge_offering_snapshots(...)（低层通用函数，语义未改）
   merged complete OfferingSnapshot（source 统一改写为 full-semester label）
      ↓  物化后重新计数 + merged_offering_set_sha256
      ↓  canonical manifest + manifest SHA-256
      ↓  （可选）SQLite full_semester import + content-bound read-back
```

### 内容绑定的口径（B3）

```text
offering_payload_sha256 = SHA256(canonical offering payload)
    canonical = json.dumps(model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    ⛔ 只用 CourseOffering 现有公共字段（含 source / data_source / meetings[]）

offering_set_sha256 = SHA256(按 identity 稳定排序后逐行 payload digest 连接)
```

⇒ 同数量 / 同身份的内容替换、字段级改写、`meetings` 变化都会改变 digest。

## 失败类别 ⇄ 退出码

| 退出码 | 阶段 | 类别（节选） |
| --- | --- | --- |
| 2 | `arguments` | `invalid_semester` / `invalid_baseline` / `inventory_invalid` / `campus_acceptance_missing`（缺参数） |
| 3 | `artifact_read` | `bundle_read_failed` / `bundle_digest_mismatch` / `bundle_changed_during_acceptance` |
| 4 | `baseline_validation` | `snapshot_window_unstable` / `shard_coverage_mismatch` |
| 5 | `shard_set_validation` / `bundle_validation` / `merge_validation` | `missing_shard` / `duplicate_shard` / `unknown_shard` / `duplicate_artifact_bytes` / `invalid_capture_bundle` / `semester_mismatch` / `duplicate_identity_across_shards` / `conflicting_identity_across_shards` / `merge_failed` / `merged_count_mismatch` |
| 6 | `completeness_validation` | `shard_not_complete` / `empty_shard` |
| 7 | `sqlite_import_and_readback` | `store_error` / `provenance_readback_mismatch` / `reconciliation_mismatch` |
| 8 | `manifest_write` / `manifest_identity` | `manifest_already_exists_with_different_content` / `manifest_sha256_mismatch` / `write_error` / `manifest_invalid` |
| 9 | `inventory_validation` / `inventory_binding` | `inventory_invalid` / `inventory_digest_mismatch` |
| 10 | `campus_binding` | `campus_acceptance_missing` / `campus_acceptance_mismatch` |

⛔ CLI **不解析错误文本**：类别是机器可读字段，文本永不外泄。

## canonical manifest（v2）

```json
{
  "format": "sysu-course-data-full-semester-acceptance-v1",
  "manifest_version": 2,
  "tool": "tools/accept_full_semester_course_data.py",
  "semester": "2026-1",
  "scope_kind": "full_semester",
  "scope_id": "2026-1",
  "source": "capture://sysu/2026-1/full-semester/2026-1",
  "inventory_sha256": "<64 hex>",
  "baseline_before": 6880,
  "baseline_after": 6880,
  "merged_offering_count": 6880,
  "merged_offering_set_sha256": "<64 hex>",
  "shards": [
    {
      "shard_id": "east-campus",
      "openingSchoolNumber": "5063559",
      "raw_bundle_sha256": "<64 hex>",
      "campus_acceptance_sha256": "<64 hex>",
      "campus_source": "capture://sysu/2026-1/campus/5063559",
      "campus_offering_set_sha256": "<64 hex>",
      "page_count": 6,
      "loaded_count": 1071,
      "reported_total": 1071
    }
  ],
  "..._semantics": "..."
}
```

- 序列化固定：`sort_keys=True` + `ensure_ascii=False` + `(",", ":")` + `allow_nan=False`；
- 传入顺序**不影响** manifest（shard 顺序固定为已批准顺序）；
- 文件**原子写入**；已存在且内容不同 ⇒ fail closed；相同 ⇒ 幂等重写；
- 落盘后**用严格校验器回读**：⛔ 未知字段 / 重复 JSON key / 非整数计数 / 未知 shard /
  非 64 位小写 digest 一律拒绝；shard 数组按批准顺序**语义规范化**
  （合法等价的重排不改变 identity，而写出策略仍要求字节一致）；
- manifest **只含**结构性计数与摘要：⛔ 无认证 token、⛔ 无用户信息、⛔ 无 raw row、
  ⛔ 无课程 / 教师 / 教室取值。

### 四类 digest（⛔ 不得混用）

```text
raw_bundle_sha256        = 那份校区 artifact 的**原始字节**
campus_acceptance_sha256 = 同一批字节的 campus acceptance identity（= raw digest）
offering_set_sha256      = **规范化后的教学班内容**
manifest_sha256          = acceptance record identity / integrity
四者都不是 acquisition provenance proof
```

## SQLite acceptance / read-back

导入后必须**全部**成立（任一不满足 ⇒ 非零退出）：

```text
两个平面同时存在且计数一致（course_data_import / course_data_acceptance）
provenance.artifact_sha256 == manifest SHA-256
scope_kind == full_semester；scope_id == --semester
provenance.source          == capture://sysu/<semester>/full-semester/<semester>
completeness == complete；loaded_count == reported_total == offering_count
offering_set_sha256        == manifest.merged_offering_set_sha256
membership identity 集合   == 实际读到的行集合（既不少也不多）
逐行 offering_payload_sha256 == membership 记录
inserted + updated + unchanged == offering_count
```

⚠️ **输出字段语义区分**：`merged_offering_count` / `accepted_row_count` = 本次 acceptance 的
行数；`db_semester_offering_count` = 该学期当前库里的**全部**行
（可能含陈旧 campus 行）⇒ ⛔ 不得混用。

## ⚠️ 事务 caveat（必须明确）

SQLite **import commit** 与 **read-back** **不是同一个事务**：

```text
⛔ 不得声称"非零退出 == SQLite 零变化"
```

失败发生在**任何 store 调用之前**时，只能说明**该次调用未发生**；
read-back 阶段的失败发生在 commit **之后**，数据库可能已经变化。
⚠️ 因此 CLI 的 import 成功**不等于** production readiness —— 只有 Provider
在**每次读取**时重新验证（B4）才能保证"现在这批行仍然是被接受的那批"。

## North / suspended 的处理方式

North 当前 `allowlisted` 但 `operationally suspended`（HTTP 600 未解决）：
**真实数据阶段拿不到第五份 artifact**，因此**当前不可能**产生真实 full-semester acceptance。

- 本工具**不知道**"谁 suspended"：它只认「五份都有且都合格」；
- ⛔ 没有 `--skip-north` / `--allow-partial-semester` / `--force-complete`；
- ⛔ 单 campus CLI 也**无法**伪造 full_semester。

## 当前状态

- BLOCK B1 / B2 / B3 已修复（本轮）；B4 见 Provider 侧；
- ⛔ 尚未处理任何真实 artifact（全部测试为 synthetic / zero-network）；
- **North 未解决 ⇒ 真实 full-semester acceptance 仍不可产出**；
- PR #39 = **frozen / do not merge**；formal Real E2E = **LEVEL0**。
