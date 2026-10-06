# Forward Integration Red-Team：四个 BLOCK 的修复回应

> 对应 Reviewer 分支 `review/full-semester-runtime-redteam`（HEAD
> `f6dfd09f3c19090212b46b971ca1db91bb6eaf88`）里的
> `reviewer/full_semester/REVIEW.md`。
> 本文逐项给出**修复位置 / 机制 / 回归用例**，并逐条映射 Reviewer 的
> 20-case invariant 矩阵与 runtime / E2E 矩阵。
> ⛔ 本文不声明 Real E2E（LEVEL0）。

## 1. 四个 BLOCK 的关闭方式

### BLOCK B1（digest 与解析结果没有绑定同一批字节）

- **机制**：新增内部 `captured_pages.load_capture_bundle_bytes(raw)`；
  `_read_shard_bundle_once()` **只读一次** `path.read_bytes()`，
  digest 与 JSON 解析都吃这同一批 bytes（⛔ 不再为了 parse 重开路径）。
  `load_capture_bundle(path)` 也改为"读一次 → 交给 bytes loader"，⛔ 不复制 parser / validator。
- **复读**保留，但只作为**额外的变动探测**，⛔ 不再承担"同源"职责。
- **campus CLI 同样修复**：`_read_and_validate_bundle()` 用同一批 bytes 解析。
- **用例**：
  - `test_course_data_full_semester_acceptance.py::test_hashed_bytes_and_parsed_bytes_are_the_same_bytes`
    （A/B/A 交错：解析必须落在被 hash 的 A 上）；
  - `::test_bundle_changed_during_acceptance_is_rejected`（文件被换 ⇒ 整体拒绝）；
  - `::test_load_capture_bundle_bytes_rejects_bad_input`（非法 UTF-8 / JSON / bundle / 类型）；
  - `test_course_data_captured_pages.py` 既有本地读取用例。
- ⚠️ Reviewer 的 `test_digest_and_parsed_rows_can_describe_different_bytes` probe
  monkeypatch 的是 `load_capture_bundle`；修复后该名字**不再是解析路径**，
  因此该 probe 不再复现 hazard（按设计失效），替代用例见上。

### BLOCK B2（approved shard label 不证明 artifact 实际 campus scope）

- **机制**：正式 acceptance 必须同时消费两份**独立**输入：
  1. **已批准 capture inventory**：`(semester, shard_id, openingSchoolNumber, raw_bundle_sha256)`，
     exact five-shard、号码等于已批准值、canonical 形式、五个 digest 两两不同；
  2. **已导入的 campus acceptance 记录**（campus CLI 写入的 content-bound 平面）：
     `artifact_sha256 == raw digest`、`scope_kind == campus`、
     `scope_id == inventory.openingSchoolNumber`、`source == canonical campus label`、
     `loaded_count == reported_total == offering_count == 本 shard 解析计数`、
     `offering_set_sha256 == 本 shard 解析结果的整批内容 digest`。
- 调用方**单独声明 label 不再足够**：label 只能选文件，⛔ 不能定义 scope。
- **用例**：
  - `::test_relabeled_artifact_is_rejected_by_the_inventory_digest`（East/South 文件互换）；
  - `::test_relabeled_campus_acceptance_is_rejected`（East 字节被以 South scope 导入）；
  - `::test_missing_campus_acceptance_record_is_rejected`；
  - `::test_campus_acceptance_with_arbitrary_source_label_is_rejected`；
  - `::test_campus_acceptance_with_wrong_row_count_is_rejected`（"行数碰巧"）；
  - `::test_campus_acceptance_with_changed_content_digest_is_rejected`；
  - `::test_same_artifact_bytes_cannot_be_declared_as_two_campuses`；
  - `::test_inventory_requires_the_approved_numbers` / `::test_inventory_has_exact_five_shards` /
    `::test_inventory_rejects_unknown_fields_and_duplicate_keys` / `::test_inventory_must_be_canonical`；
  - CLI：`test_full_semester_acceptance_cli.py::test_changed_bytes_after_inventory_approval_are_rejected`、
    `::test_missing_campus_acceptance_is_rejected`、`::test_relabeled_campus_acceptance_is_rejected`、
    `::test_campus_cli_then_full_semester_cli_flow`（真实两步流程）。

### BLOCK B3（exact accepted dataset 必须 content-bound）

- **机制**：新增内部 `offering_digest.py`：

  ```text
  offering_payload_sha256 = SHA256(canonical offering payload)
      canonical = json.dumps(CourseOffering.model_dump(mode="json"),
                             sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False)
  offering_set_sha256     = SHA256(按 (semester, course_id, class_id) 稳定排序后的逐行 digest)
  ```

  manifest 记录 `merged_offering_count` + `merged_offering_set_sha256`；
  每个 shard 记录 `campus_offering_set_sha256`；
  store 的 content-bound 平面记录整批 digest + 逐行 payload digest（membership）。
  字段覆盖 `CourseOffering` **现有全部公共字段**（含 `source` / `data_source` / `meetings[]`），
  ⛔ 未新增任何公共 Schema 字段。
- **用例**：
  - `::test_manifest_digest_changes_when_only_the_content_changes`（同数量 / 同身份换内容）；
  - `::test_offering_set_digest_is_order_independent_and_content_bound`；
  - `test_course_data_store.py::test_same_count_content_substitution_is_detected`
    （course_name / course_id / class_id / source / meetings_json / credit 六种替换）；
  - CLI：`::test_content_tampering_is_detected_on_read_and_repaired_by_reimport`。

### BLOCK B4（Provider 必须持续验证 acceptance）

- **机制**：`StoreBackedCourseDataProvider` **不再缓存** metadata / rows；
  每次 `get_course_offerings(semester)` 都在**一个一致读事务**里调用
  `store.load_accepted_offerings()`，重新核对：
  两个平面同时存在且计数一致 → scope / semester / completeness / counts →
  membership 数量与 identity 集合 → 逐行 `offering_payload_sha256` →
  重算整批 `offering_set_sha256` → 每行的行级 provenance 仍指向本 acceptance。
- ⛔ 未采用"init-only 校验 + 永久缓存 rows"。
- **用例**：`test_course_data_store_provider.py` 全部用例（含
  `test_deleted_acceptance_record_is_not_rechecked_on_request` 的修复版
  `test_acceptance_record_removed_after_construction_fails_closed`、
  同数量替换、payload 篡改、membership 篡改、陈旧行隔离、跨学期隔离），
  以及 `test_course_data_store.py::test_accepted_read_requires_the_acceptance_record` 等。

## 2. Reviewer 20-case invariant 矩阵映射

| # | Case | 结果 | 用例 / 说明 |
| --- | --- | --- | --- |
| 1 | 四 shard 假 full | reject | `test_missing_north_shard_is_rejected`、`test_missing_any_single_shard_is_rejected` |
| 2 | North missing | reject | 同上（⛔ 无 skip-north / 无虚构输入）；`test_north_bundle_is_a_mandatory_argument` |
| 3 | duplicate shard id | reject | `test_duplicate_shard_is_rejected` |
| 4 | 同 artifact 换 label | reject | `test_same_artifact_bytes_cannot_be_declared_as_two_campuses`、`test_relabeled_campus_acceptance_is_rejected` |
| 5 | unknown shard / alias | reject | `test_unknown_or_aliased_shard_is_rejected`（含中文名 / 大小写 / 空格变体） |
| 6 | wrong openingSchoolNumber | reject | `test_inventory_requires_the_approved_numbers`、`campus_acceptance_mismatch` 用例 |
| 7 | semester mismatch | reject | `test_semester_mismatch_in_one_shard_is_rejected`、`test_inventory_for_another_semester_is_rejected`、runtime + E2E 用例 |
| 8 | baseline drift | reject | `test_baseline_drift_is_rejected`、`test_missing_baseline_is_rejected` |
| 9 | sum < baseline | reject | `test_sum_below_baseline_is_rejected` |
| 10 | sum > baseline | reject | `test_sum_above_baseline_is_rejected` |
| 11 | duplicate identity | reject | `test_duplicate_identity_across_shards_is_rejected` |
| 12 | identity 内容一致 | reject | 同上（B2 后每 shard 带自己的 campus label，故 `source` 归一化后判为重复） |
| 13 | identity 内容冲突 | reject | `test_conflicting_identity_across_shards_is_rejected` |
| 14 | input shard 顺序变化 | NON-BLOCKING | `test_artifact_order_does_not_change_the_manifest` |
| 15 | raw bytes 变化 | reject（pinned digest 不符） | `test_raw_bytes_change_does_not_change_the_identity`（whitespace-only 也拒绝） |
| 16 | manifest keys / whitespace | NON-BLOCKING | `test_manifest_validator_rejects_unknown_fields_and_bad_counts`（shard 数组语义规范化）、`test_manifest_is_deterministic_across_runs` |
| 17 | source label vs actual scope | reject | `test_campus_acceptance_with_arbitrary_source_label_is_rejected` |
| 18 | empty shard | reject | `test_empty_shard_is_rejected`；⚠️ 五个**完全相同**的空 artifact 会更早在 inventory 被拒（`test_five_identical_empty_artifacts_are_rejected`） |
| 19 | partial shard | reject | `test_partial_shard_is_rejected_even_when_the_totals_still_add_up`、`test_partial_shard_with_mismatched_sum_is_rejected` |
| 20 | campus 冒充 full provenance | reject（runtime 侧） | Provider 只按 `full_semester` acceptance 读取；`test_campus_only_store_is_rejected` / `test_accepted_read_is_scope_parameterized` |

低层函数仍**不是** acceptance gate：`merge_offering_snapshots()` 与
`collect_sharded_capture_set()` 的成功 **不构成** 正式 acceptance（高层 gate 才是）。

## 3. Reviewer runtime / E2E 矩阵映射

| Dimension | 正例 | 负例用例 |
| --- | --- | --- |
| activation | `APP_REAL_CASE_A_ENABLED=1` → ready | `test_runtime_is_disabled_when_not_configured`、`test_explicit_disable_values`、`test_non_binary_switch_values_are_invalid`、`test_*_configuration_is_required` |
| curriculum | synthetic valid Case A | `test_missing_or_mock_curriculum_case_is_not_ready`、`test_case_marked_mock_but_otherwise_valid_is_not_ready`、`test_case_with_wrong_scope_cut_off_is_not_ready`、`test_case_with_unapproved_scope_decision_is_not_ready` |
| acceptance identity | pinned SHA | `test_malformed_acceptance_digest_is_invalid`、`test_wrong_acceptance_digest_is_not_ready`、`test_uppercase_acceptance_digest_is_accepted` |
| acceptance semantics | full scope / semester exact | `test_campus_only_store_is_not_ready`、`test_wrong_semester_is_not_ready` |
| completeness | counts == accepted set | `test_store_with_inconsistent_counts_is_not_ready`、`test_store_with_zero_rows_is_not_ready` |
| artifacts / manifest | inventory + campus binding | `test_store_acceptance_missing_is_not_ready`（acceptance 记录被删除）、`test_store_with_tampered_content_is_not_ready` |
| rows | exact identities + payloads | `test_store_with_tampered_membership_is_not_ready`、`test_stale_campus_rows_are_not_served` |
| DB mutation | 一致读事务 | `test_provider_failure_propagates_without_fallback`、`test_tampered_store_is_not_served_and_does_not_fall_back`（E2E） |
| request semester | exact configured | `test_requesting_another_semester_never_falls_back` |
| fallback isolation | only accepted Store provider | `test_module_has_no_mock_or_single_bundle_fallback`、`test_unconfigured_runtime_never_serves_mock_data` |
| errors | typed readiness → 503 | `test_missing_acceptance_returns_the_frontend_503_contract`、`test_store_errors_are_reported_without_exception_text` |

E2E 矩阵（Reviewer §7）逐条覆盖见
`backend/tests/test_synthetic_production_e2e.py` 与
`docs/data/CASE_A_RUNTIME_WIRING.md`。

## 4. 仍未做 / 未声称

- ⛔ realistic immutability（专用 immutable acceptance DB / versioned row payload）
  属**后续 Architecture Decision**：本轮的机制是"membership + 内容指纹 + 任何
  篡改即 fail closed"，而**不是**物理不可变；
- ⛔ 未处理任何真实 artifact；⛔ 未 merge main；⛔ 未改 public Schema /
  frozen Provider contract；**PR #39 = frozen**；formal Real E2E = **LEVEL0**；
- ⛔ 本工具**无法**证明某个 inventory 真的经过人工批准：它只能保证
  "正式 acceptance 必须消费一个 inventory 产物，且与字节 / campus acceptance 逐项一致"。
