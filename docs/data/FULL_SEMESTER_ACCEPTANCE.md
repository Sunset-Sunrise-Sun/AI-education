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
共同证明。因此这是一个**独立**入口，⛔ 不是把 campus CLI 加一个开关扩宽出来的。

## 使用

```bash
python tools/accept_full_semester_course_data.py \
  --semester 2026-1 \
  --baseline-before 6880 \
  --baseline-after 6880 \
  --east     ./east-campus.capture.json \
  --south    ./south-campus.capture.json \
  --shenzhen ./shenzhen-campus.capture.json \
  --zhuhai   ./zhuhai-campus.capture.json \
  --north    ./north-campus.capture.json \
  [--expected-manifest-sha256 <64 位小写 hex>] \
  [--output-manifest ./full-semester-acceptance-manifest.json] \
  [--sqlite ./course-data.sqlite]
```

成功时 stdout 输出**一个** JSON 对象（只含聚合字段）；失败时 stderr 输出
**一个** JSON 对象（`status` / `stage` / `category` / `exception_type`，可归因到
某个 shard 时附**结构性** `shard_id` slug），并以非零退出码结束。

## 契约

| 项 | 规则 |
| --- | --- |
| scope | **固定** `scope_kind = full_semester`、`scope_id = <semester>`；⛔ 没有 `--scope-kind` 选项 |
| source | **由 semester 完全决定**：`capture://sysu/<semester>/full-semester/<semester>`；⛔ 没有 `--source` 选项；它只是 audit label，⛔ 不是 provenance proof |
| shard 集合 | **exact five-shard**：`east-campus` / `south-campus` / `shenzhen-campus` / `zhuhai-campus` / `north-campus`；⛔ 缺 / 多 / 重复 / 别名（含中文校区名、大小写、空格变体）一律 reject |
| 逃生参数 | ⛔ **没有** `--skip-north` / `--allow-partial-semester` / `--force-complete` |
| baseline | `baseline_before` / `baseline_after` = collector 报告的**全学期总数**（⛔ 不是 baseline `OfferingSnapshot`）；必须相等 |
| completeness | 只由**现有**分页证据链判定；⛔ **不得**用 `page_count` 推导 completeness |
| identity | `(semester, course_id, class_id)`；⛔ 不按 `course_id` 去重 |
| manifest SHA-256 | canonical manifest **文件字节**的 SHA-256 = acceptance identity / integrity；⛔ **不是** acquisition provenance proof |

## 正式流程

```text
5 份 raw campus artifact
      ↓  每个 raw-byte SHA-256（exact-byte identity；可选 `expected_sha256` gate）
      ↓  load_capture_bundle() + collect_captured_pages_snapshot()（现有入口）
5 个 campus OfferingSnapshot（各自必须 complete 且非空）
      ↓  baseline_before == baseline_after        （否则 snapshot_window_unstable）
      ↓  Σ shard reported_total == 稳定 baseline  （否则 shard_coverage_mismatch）
      ↓  跨 shard identity：无重复 / 无冲突
      ↓  merge_offering_snapshots(...)            （低层通用函数，语义未改）
   merged complete OfferingSnapshot
      ↓  物化后**重新计数**（不采信下层自报数字）
      ↓  canonical manifest + manifest SHA-256
      ↓  （可选）SQLite full_semester import + provenance read-back
```

## 失败类别 ⇄ 退出码

| 退出码 | 阶段 | 类别（节选） |
| --- | --- | --- |
| 2 | `arguments` | `invalid_semester` / `invalid_baseline` / `invalid_arguments` |
| 3 | `artifact_read` | `bundle_read_failed` / `bundle_digest_mismatch` / `bundle_changed_during_acceptance` |
| 4 | `baseline_validation` | `snapshot_window_unstable` / `shard_coverage_mismatch` |
| 5 | `shard_set_validation` / `bundle_validation` / `merge_validation` | `missing_shard` / `duplicate_shard` / `unknown_shard` / `invalid_capture_bundle` / `semester_mismatch` / `duplicate_identity_across_shards` / `conflicting_identity_across_shards` / `merge_failed` / `merged_count_mismatch` |
| 6 | `completeness_validation` | `shard_not_complete` / `empty_shard` |
| 7 | `sqlite_import_and_readback` | `store_error` / `provenance_readback_mismatch` / `reconciliation_mismatch` |
| 8 | `manifest_write` / `manifest_identity` | `manifest_already_exists_with_different_content` / `manifest_sha256_mismatch` / `manifest_write_error` |

⛔ CLI **不解析错误文本**：类别是机器可读字段，文本永不外泄。

## canonical manifest

```json
{
  "format": "sysu-course-data-full-semester-acceptance-v1",
  "manifest_version": 1,
  "tool": "tools/accept_full_semester_course_data.py",
  "semester": "2026-1",
  "scope_kind": "full_semester",
  "scope_id": "2026-1",
  "source": "capture://sysu/2026-1/full-semester/2026-1",
  "baseline_before": 6880,
  "baseline_after": 6880,
  "merged_offering_count": 6880,
  "shards": [
    {
      "shard_id": "east-campus",
      "scope_id": "5063559",
      "raw_bundle_sha256": "<64 hex>",
      "page_count": 6,
      "loaded_count": 1071,
      "reported_total": 1071
    }
  ],
  "..._semantics": "..."
}
```

- 序列化固定：`sort_keys=True` + `ensure_ascii=False` + 分隔符 `(",", ":")` + UTF-8；
- 传入顺序**不影响** manifest（shard 顺序固定为已批准顺序）；
- 文件**原子写入**（临时文件 + `os.replace`）；已存在且内容不同 ⇒ fail closed；
  内容相同 ⇒ 幂等重写。落盘后**复算**文件字节 SHA-256，必须等于 acceptance identity；
- manifest **只含**结构性计数与摘要：⛔ 无认证 token、⛔ 无用户信息、⛔ 无 raw row、
  ⛔ 无课程 / 教师 / 教室取值。

### 口径（⛔ 不得混用）

```text
raw_bundle_sha256   = 那份校区 artifact 的**原始字节**（采集证据的完整性）
manifest_sha256     = acceptance record identity / integrity（把五份绑在一起）
source label        = audit label only
三者都 ≠ acquisition provenance proof
```

## SQLite acceptance / read-back

导入后必须**全部**成立（任一不满足 ⇒ 非零退出）：

```text
provenance.artifact_sha256 == manifest SHA-256
provenance.semester        == --semester
provenance.scope_kind      == full_semester
provenance.scope_id        == --semester
provenance.source          == capture://sysu/<semester>/full-semester/<semester>
provenance.completeness    == complete
provenance.loaded_count    == merged.loaded_count
provenance.reported_total  == merged.reported_total
provenance.offering_count  == merged offering 数
inserted + updated + unchanged == provenance.offering_count
```

⚠️ **输出字段语义区分**：`merged_offering_count` = 本次 acceptance 的 offering 数；
`db_semester_offering_count` = 该学期当前库里的**全部** offering 数
（可能包含旧 campus import 或其它 artifact）⇒ ⛔ 不得混用。

## ⚠️ 事务 caveat（必须明确）

SQLite **import commit** 与 **provenance read-back** **不是同一个事务**：

```text
⛔ 不得声称"非零退出 == SQLite 零变化"
```

失败发生在**任何 store 调用之前**（shard 集合、baseline、artifact read/hash、
bundle、completeness、identity、manifest 写入）时，只能说明**该次调用未发生**；
read-back 阶段的失败发生在 commit **之后**，数据库可能已经变化。

## North / suspended 的处理方式

North 当前 `allowlisted` 但 `operationally suspended`（HTTP 600 未解决）：
**真实数据阶段拿不到第五份 artifact**，因此**当前不可能**产生真实 full-semester
acceptance。

- 本工具**不知道**"谁 suspended"：它只认「五份都有且都合格」这一件事。
  代码本身**可以**接受一份未来合法取得的 North artifact；
- ⛔ 但"现在没有 North"**不是**加逃生参数的理由 —— 缺第五份输入就是缺，fail closed；
- ⛔ 单 campus CLI 也**无法**伪造 full_semester（`scope_kind` 固定为 campus）。

## 非空泛性（mutation sweep）

`mutate_full_semester_acceptance.py`（development-only，⛔ 不入库）对
module + CLI 施加 **34** 处文本变异，每次只改一个目标文件、锚点必须唯一，
且必须让 targeted suite 变红；随后按字节还原并核对 SHA-256。

```text
killed = 29 / 34
survived = 5 → 全部为**可证等价**的冗余防御子句（已在代码内注明）：
  A04 complete 快照的 `reported_total == loaded_count`（由 OfferingSnapshot 不变量保证）
  A05 `merged_loaded != stable_baseline`（在各 shard loaded == reported 已成立时等价）
  A06 unique identity 数复核（底层 merge 条件 8 + 快照去重不变量已保证）
  A07 `merged.is_complete`（merge_offering_snapshots 必返回 complete）
  A14 `str/bytes` 显式拦截（去掉后仍以同一 category 拒绝）
```

⛔ 未为了"数字好看"删除这些防御子句，也⛔ 未把等价变异算作 killed。

## 当前状态

- Gate A 完成：five-shard full-semester acceptance + SQLite full_semester import；
- ⛔ 尚未处理任何真实 artifact（全部测试为 synthetic / zero-network）；
- **North 未解决 ⇒ 真实 full-semester acceptance 仍不可产出**；
- PR #39 = **frozen / do not merge**；formal Real E2E = **LEVEL0**。
