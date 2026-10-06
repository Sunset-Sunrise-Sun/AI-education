# Forward Integration Red-Team / Pre-Review

审查日期：2026-10-06。main baseline：`1cd08e043b89a6da0a5f04a1b8981b59fae3b035`。
Builder reviewed：`feature/full-semester-course-data-acceptance`，HEAD
`c01b7c9944c44cc2c7c28c80f22ecfaedc8734b7`。
PR #39 HEAD `a4dc48ce0e28e1f1473dd822b3671f9ce525770d` 仅作为 frozen 反例。
没有改 production code、public Schema、Provider contract 或数据库结构；没有学校网络访问。
全部 probe 输入人工生成，模型里的 `data_source=real` 仅用于 exercise production 类型门禁。
Formal Real E2E 仍为 LEVEL0。本文 synthetic E2E 是方案，尚未运行 successor E2E。

## 1. Critical risks

### BLOCK B1：digest 与解析结果没有绑定同一批字节

Builder `backend/app/course_data/full_semester_acceptance.py:426` 的 `_read_shard_bundle()`
先 `read_bytes()` / hash，再 `load_capture_bundle(path)`，最后复读。
若文件在 loader 读取时由 A 变 B，随后恢复 A，首尾检查通过，但 acceptance rows 来自 B，
manifest raw digest 来自 A。相同 manifest SHA 对应不同 normalized payload。
`test_builder_probes.py::test_digest_and_parsed_rows_can_describe_different_bytes`
通过 monkeypatch 模拟精确读写交错，不 mock normalizer 或 acceptance。
复现结果：两个 acceptance 的 SHA 完全相同，课程名不同。
最小修复：只读取一次 raw bytes，严格 JSON decode 该 bytes，复用
`validate_capture_bundle()` 和 `collect_captured_pages_snapshot()`；不再为了 parse 重开路径。
若仍要检测文件变动，额外复读不能取代 parse 与 hash 同源。

### BLOCK B2：approved shard label 不证明 artifact 实际 campus scope

Builder `accept_full_semester_capture_set()` 在约 :555 解析各 bundle；约 :642
将 `approved.opening_school_number` 写入 record。Capture Bundle v1 不含实际采集
`openingSchoolNumber` / shard identity，`captured_pages._parse_capture_bundle()` 不校验这些。
交换 East/South 的原始文件、保持全部字节与 counts 不变，仍 accepted；新 manifest 将
South bytes 声明为 East。这不是“hash 算错”，是没有 independently approved scope binding。
`test_shard_labels_are_not_bound_to_actual_capture_scope` 已复现。
最小内部方案：独立受批准 capture inventory，绑定
`(semester, shard_id, openingSchoolNumber, raw_bundle_sha256)`，验收前逐项匹配。
inventory 必须在 acquisition 审核时形成；CLI 同时传 label 和 digest 不构成独立证明。
无需改变 public Schema；若现有 raw artifact 没有 scope 证据，fail closed，交负责人确认。
可允许 synthetic structural acceptance，但不能据此签发正式 Real acceptance。

### BLOCK R1：未来 runtime 不能读取整个 semester

当前 `store.load_course_offerings()` :732 / :748 / :773 只按 semester / course_ids
过滤；`import_offering_snapshot()` :627 upsert 更新交集 provenance，不清除旧差集。
这不是 low-level Store 对已有文档承诺的违约；是直接将它作为 accepted Provider 的 blocker。
import record 长期存在，不证明当前 rows 仍等于 accepted set。

## 2. Full-semester invariants

分类：BLOCK = 违反后阻止正式 acceptance / runtime merge；FAIL CLOSED = 具体运行结果，
拒绝验收、不写 accepted 状态，runtime 返回 503；NON-BLOCKING = 等价变化按 canonical 规则处理。

| Case | 必须结果 / 现有定位 |
|---|---|
| 1 四 shard 假 full | BLOCK / FAIL CLOSED；`_ordered_artifacts()` exact set |
| 2 North missing | BLOCK / FAIL CLOSED；无 skip-north，North suspended 不用虚构输入补齐 |
| 3 duplicate shard id | BLOCK / FAIL CLOSED；先查重再转 dict |
| 4 同 artifact 换 label | BLOCK / FAIL CLOSED；原样复用因 identity duplicate 被拒绝；改 label / 分割互异 rows 还需独立 scope binding |
| 5 unknown shard | BLOCK / FAIL CLOSED；拒绝 extra 与 alias |
| 6 wrong openingSchoolNumber | BLOCK / FAIL CLOSED；目前只从 label 生成号码，B2 未覆盖 |
| 7 semester mismatch | BLOCK / FAIL CLOSED；bundle / snapshot / each offering / config / request 全部 exact |
| 8 complete shard + baseline drift | BLOCK / FAIL CLOSED；before == after；相同总数不证明集合未变，不能夸大 acquisition proof |
| 9 sum < baseline | BLOCK / FAIL CLOSED；coverage mismatch |
| 10 sum > baseline | BLOCK / FAIL CLOSED；coverage mismatch |
| 11 duplicate identity | BLOCK / FAIL CLOSED；`(semester, course_id, class_id)`，非仅 course_id |
| 12 identity 内容一致 | BLOCK / FAIL CLOSED；分片应互斥，不允许 silent dedup |
| 13 identity 内容冲突 | BLOCK / FAIL CLOSED；不采用 last-wins / first-wins |
| 14 input shard 顺序变化 | NON-BLOCKING；按批准顺序 materialize，SHA 不变 |
| 15 raw bytes 变化 | 新 acceptance identity；若 pinned digest 不符则 BLOCK / FAIL CLOSED，即使只变 whitespace |
| 16 manifest object keys / whitespace | semantic canonical digest 不变；原 manifest shard array 重排应按批准身份规范化，再校验 exact set |
| 17 source label vs actual scope | BLOCK / FAIL CLOSED；source 为 label，不能替代 B2 binding |
| 18 empty shard | BLOCK / FAIL CLOSED；当前政策 >0，未来若学校正式允许 0 需显式裁决，不能偷偷跳过 |
| 19 partial shard | BLOCK / FAIL CLOSED；page_count 不证明 complete |
| 20 campus 冒充 full provenance | BLOCK / FAIL CLOSED；Store 显式 scope 是声明，不是 acceptance verifier |

现有低层 `sharded_capture.collect_sharded_capture_set()` 接受 complete baseline snapshot；
它不检查采集前后 baseline，也不证明 label->artifact campus mapping。
`snapshot.merge_offering_snapshots()` 只验证 complete / count / identity，不验证 exact five set。
未来必须走高层 gate，不将低层函数的成功当正式 acceptance。
Builder 新高层 correctly 使用两个 total，而不是人为造 complete baseline snapshot。
canonical 批准顺序：east-campus, south-campus, shenzhen-campus, zhuhai-campus, north-campus；
这些是实现实际 slug，对应任务中的 east/south/shenzhen/zhuhai/north，不增加别名入口。
numbers：5063559 / 5062201 / 333291143 / 5062203 / 5062202。

## 3. Canonical manifest recommendation

最小内部字段：`format`, `manifest_version`, `semester`, `scope_kind=full_semester`,
`scope_id=semester`, `baseline_before`, `baseline_after`, `merged_offering_count`, ordered `shards`。
每 shard：`shard_id`, `openingSchoolNumber`（Builder 用 `scope_id`，必须文档明确映射），
`raw_bundle_sha256`, `loaded_count`, `reported_total`。
`page_count` / tool version 可作为内部审计扩展，不作为 completeness proof。
禁止 raw rows、teacher、private extension、credentials；拒绝未知字段和 duplicate JSON keys；
所有 count 是 nonnegative integer，拒绝 bool / float / NaN / Infinity；semester 不自动 trim 为其它输入。
推荐 manifest digest 对 **validated canonical reserialization** 算 SHA-256：
UTF-8，无 BOM / newline，`ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False`，
先以固定批准顺序规范化 shard array。仅 keys 排序不会规范化 array。
这样 JSON pretty-print / key reorder 不改变 acceptance identity。
若读取外部 manifest，先 strict parse、exact schema / shard set 验证，再 canonical；
不能 hash 任意 dict 后把“digest matched”当 valid acceptance。
Writer 可以要求已存在文件 exact canonical bytes（Builder 当前行为）；这是写入策略，
不要混同未来 runtime 对合法等价 manifest 的 semantic identity。
raw bundle digest 继续对 **raw bytes**，不可改为 canonical JSON。
manifest 不包含自身 digest；不包含 wall-clock timestamp / local path 等非确定性值。
manifest SHA 仅代表 acceptance identity/integrity；baseline 与 SHA 均不证明 acquisition authenticity。
Builder serialization 基本符合 recommendation；外部 manifest reader 的 strict checks 尚未实现。

## 4. Stale-row verdict

复现：A East={e_current,e_obsolete}，B South={s_current}，旧 C East={e_old_extra}；
D full={e_current,s_current,d_new}。D import 后 semester loader 返回 **5 rows**，不是 D 的 3 rows。
交集 2 rows 的 provenance 改指 D；e_obsolete / e_old_extra 仍保留 campus provenance。
再导入 campus E={e_current}，D import record 仍写 count=3，但按 D digest 筛选只剩 2 rows。
两个 probe 在 main Store 上复现，另一个证明 Store 可将 campus snapshot 声明 full scope。
row-level `(digest, scope_kind, scope_id)` 适合选择当前 D rows，但单独不足以证明 immutable membership
或抵御同 cardinality 的 row replacement / payload tamper。
Builder CLI :505 读整个 semester 仅报告明确命名的 audit total；不把它宣称 accepted count，
因此 stale total 本身不是该 CLI 的独立 bug。但 CLI provenance readback 不等于 exact row set 验证。

## 5. Recommended Provider design

**短期最小方案 A + binding + fail closed**：只读事务中校验 one approved acceptance，
读取 exact `(semester, artifact_sha256, full_semester, scope_id=semester)` rows，
独立复核 counts / identities / row content binding；materialize validated snapshot，
Provider 只返回该 snapshot。manifest-only count 不能提供 content binding；
零网络重放 manifest pinned 的五 raw artifacts，按 identity 比较所有规范化公共字段，
或采用经审批的独立 normalized row-set digest/immutable accepted snapshot。
后者是内部设计建议，没有私改 DB / Schema。
后续 campus import 导致 accepted row 不足必须 503，不能悄悄读其它 artifact 补齐。
请求期间使用一致 materialized snapshot；避免验证后再无约束读 live DB 的 TOCTOU。

**长期 B**：versioned acceptance membership + immutable/versioned row payload。只新增 membership
指向当前 mutable identity table 仍会使 accepted row 内容被后来 campus import 改写，不够。
此方案涉及 DB architecture decision，需负责人批准再实施。
**C transactional replacement** 可对专用 acceptance-only DB 安全，写数据与 acceptance 状态同事务，
但共享 DB 清空 semester 会破坏历史/campus审计，不推荐默认方案。
**D dedicated immutable SQLite per acceptance**：无需共享库新 Schema，验证 exact artifact/snapshot，
只读连接；仍需批准 digest->content binding，不能只相信 filename。
不推荐：semester loader、source prefix、仅 import record exists、仅总数相等、仅 row digest filter。
必需 tests：A/B/C/D 导入；E 后写；same count swapped identities；same identity changed payload；
two full acceptances；reimport D；transaction failure；read-only/no schema creation；restart/cache invalidation；
missing DB、wrong schema、malformed meetings、concurrent writer；semester cross-read。
不改变 frozen `get_course_offerings(semester)->list[CourseOffering]`。

## 6. Runtime successor acceptance matrix

配置入口：APP_REAL_CASE_A_ENABLED / APP_CASE_A_CURRICULUM_CASE_PATH /
APP_COURSE_DATA_SQLITE_PATH / APP_COURSE_DATA_SEMESTER / APP_COURSE_DATA_ACCEPTANCE_SHA256。
valid HTTP envelope 前提下，下表负例统一 POST /api/v1/plan ->
503 `detail.error=real_pipeline_not_configured`，不泄漏路径或 raw fields。
malformed API envelope 仍按已有契约 422，不将其混同 readiness failure。

| Dimension | 正例 | 必须负例 |
|---|---|---|
| activation | explicit 1 | disabled/missing/invalid enable；missing each required config |
| curriculum | synthetic valid Case A projection | absent/malformed/wrong case/unconfirmed scope |
| acceptance identity | pinned exact lowercase SHA | missing, truncated, wrong SHA, multiple/ambiguous record |
| acceptance semantics | semester exact, full scope, scope_id=semester | campus, Case-A scoped, source-only real label, wrong scope_id |
| completeness | complete; all counts equal accepted unique materialized set | partial, null count, bool count, zero, count drift |
| artifacts / manifest | B1/B2 resolved; strict format/version/pinned bindings | changed bytes, duplicate key, unknown format/version, synthetic promoted Real |
| rows | exact accepted identities and public payloads | stale campus extra, accepted missing, same count substitute, payload corruption |
| DB mutation | one consistent transaction/snapshot | concurrent overwrite, post-verification read, stale cached readiness |
| request semester | exact configured semester | other semester, whitespace suffix, wildcard-like input |
| fallback isolation | only accepted Store provider | Mock, campus, raw bundle, DB-has-rows enabling |
| errors | existing typed readiness failure translated to 503 | uncaught SQLite/normalization error becomes 500; broad catch silently returns plan |

request semester mismatch gate belongs concrete provider/runtime (raise existing readiness error),
not generic Orchestrator contract. Do not return [] and let Planner interpret mismatch as valid empty supply.
PR #39 `build_course_data_provider()` accepts any complete single bundle with approved bytes and label,
does not enforce full scope, and Provider wrong semester returns []; frozen implementation must not be reused as gate.

## 7. Synthetic production E2E test matrix

目标：temp synthetic Curriculum Case A -> real file-based Curriculum provider ->
synthetic five-shard accepted temp SQLite -> successor Store provider ->
RestrictedPlannerProvider -> actual runtime factory -> actual FastAPI POST。
用 synthetic paths/config 替代输入；不得 dependency override production factory / acceptance verifier。
spy Planner 可记录参数但必须 delegate 真 RestrictedPlannerProvider，禁止 canned result。
仅允许 synthetic, zero-school-network，最大结论 LEVEL1 wiring capability；非 Real LEVEL2/LEVEL3。

| Test | Assert |
|---|---|
| valid exact set | Planner receives all and only D accepted rows，payload、identity 与 fixture exact |
| current_schedule | HTTP input validated 后原值 / 内部 same list pass-through，保留已选班 |
| Preference | every nondefault field passes unchanged；未知执行语义产生 manual_confirmation |
| unknown offering | meetings=[] 仍在 supply，不被过滤、不自动认 CLEAR |
| unknown current | 不能认证整体无时间冲突，current 保留，manual_confirmation/unknown unresolved |
| no Mock fallback | mock-service planning methods spy fail if called；不禁 app 的文档化启动 Mock schema self-check |
| missing acceptance | 503 exact error；Planner not called |
| wrong pinned SHA | 503；不读取 alternate acceptance |
| campus-only DB | 503 即使 counts 正好相等、source 写 full-semester |
| A/B/C then D | accepted D only 或 strict dedicated DB 模式拒绝；绝不 semester union |
| later campus E | 若破坏 D membership/payload 则 503，immutable design 可继续准确返回 D |
| same-count substitution | 503，不能只断言 len |
| malformed/unreadable DB | 503 typed readiness path；没有 schema creation 或 writes |
| request mismatch | 503；不得空 supply/mock/other semester |
| restart/reimport | readiness、digest、exact set一致；缓存不能掩盖变更 |

当前 main 没有 Store-backed Provider/runtime successor；上述 E2E 不冒充已执行。
现有 real-plan API、Planner、Integration 测试可验证各 seam，但不能替代 successor E2E。

## 8. Reviewer branch / reproduction

branch：review/full-semester-runtime-redteam，基于 main，只有本目录测试/文档与 reviewer status/worklog。
主仓库运行：`cd backend && /workspace/.venvs/ai-education/bin/python -m pytest ../reviewer/full_semester/test_store_probes.py`。
Builder probes 不在 default tests 目录、不引入未来 failing test；用 archive 的 app：
`PYTHONPATH=/tmp/ai-education-builder-review/backend /workspace/.venvs/ai-education/bin/python -m pytest /workspace/AI-education/reviewer/full_semester/test_builder_probes.py`。
重建 archive：`git archive c01b7c9944c44cc2c7c28c80f22ecfaedc8734b7 | tar -x -C <existing-empty-review-dir>`。
这不是 Git worktree，且不改变 Builder checkout。所有 5 probes **passing means hazard reproduced**，不是 gate PASS。

## 9. Builder PR reviewed

focused branch review c01b7c9；远端 refs/pull 当次未发现该 HEAD 对应 PR。
GitHub PR API `gh pr list` 返回 Forbidden，无法发布对应 PR 评论；不请求 token、不处理 credentials。
PR #39 仅 read-only 反例；未 merge / modify。收尾再次检查 successor branches。

## 10. BLOCK / PASS findings

PASS structural coverage：Builder 两个现有测试文件 **88 passed**；exact set、drift、coverage、partial、
empty、duplicate/conflict、canonical determinism、raw-byte sensitivity、scope 常量有覆盖。
BLOCK：B1 相同 acceptance digest 不同 payload；B2 缺独立 campus artifact scope binding。
R1 runtime acceptance isolation 是 successor 必须解决的 BLOCK，非当前 Store 自称违反承诺。
manifest key排序/whitespace等价 NON-BLOCKING；North suspended remains external operational gate。
没有 formal Real artifacts / acceptance；没有 successor LEVEL1 E2E 通过声明。

## 11. What Builder should fix before merge

1. B1：parse hashed bytes，加入 A/B/A 交错回归测试（应 rejected 或解析到 A，不能接受 B rows + A hash）。
2. B2：正式 acceptance 校验受批准 digest-to-campus inventory；否则明确只提供 structural result，
   不将用户自填 labels 作为正式 acquisition scope 证据。新增 swapped files / wrong campus binding tests。
3. successor：实现 exact accepted set/content gate、事务一致读取与 mismatch->503，不能使用 semester loader。
4. CLI import success 不应被 runtime 当 readiness；readback acceptance metadata 不能替代 row validation。
5. 合并前完成本报告 runtime/E2E matrix；North 未恢复不生成正式 full acceptance。
