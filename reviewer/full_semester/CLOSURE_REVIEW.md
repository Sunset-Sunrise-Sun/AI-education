# Blocker Closure + Runtime Readiness Audit

2026-10-06 (Asia/Shanghai). Reviewer baseline `f6dfd09f3c19090212b46b971ca1db91bb6eaf88`.
This report supersedes the original four-block status for the specific HEADs below;
it does not overwrite the historical reproduction report.

## 1. Latest Builder branches / HEADs

| Target | Exact reviewed HEAD |
|---|---|
| fix/full-semester-acceptance-blocks | 831c0e35d6396f5e6071de86c3782fcd81914b22 |
| fix/store-provider-continuous-verification | cb585c1f623ce30c9b9bb5afd3ccc1995f957f41 |
| feature/case-a-runtime-wiring-store | 3e0a7c3b585e8fb250aeeb4b95128fb014b1d982 |
| feature/synthetic-production-e2e | d097f510a4f8d139d8452601516c1d43f925e8c6 |

All four are in the cumulative d097f51 history. Reviewed source was extracted by `git archive`
into `/tmp/ai-education-closure-d097f51`; no worktree, reset, or Builder checkout edits.
Course Data implementation is unchanged between cb585c1 and d097f51.
Old feature heads c01b7c9 / 13c5556 remain visible but are superseded by these fix branches.
main remains `1cd08e043b89a6da0a5f04a1b8981b59fae3b035`.
PR #39 `a4dc48c` remains frozen, not a successor merge candidate.
Explicit wildcard fetch was necessary because default Git fetch refspec did not cover all heads.

## 2. Four original blocker status

| Original invariant | Closure verdict | Independent evidence |
|---|---|---|
| exact bytes hashed == parsed | PASS | parser receives original A bytes even while path contains valid B; restored A after parse; result payload and raw digest both A |
| campus binding | PASS within approved-inventory/campus-record trust boundary | swap East/South files, reused bytes, wrong record scope_id, wrong digest, missing campus record all rejected |
| exact dataset content binding | PARTIAL / BLOCK | direct SQL substitution of 8 fields/identity rejected, but same-count reimport under the same approved manifest SHA refreshes every expected digest and succeeds; R-CONTENT below |
| continuous Provider validation | sequential next-read requirement PASS; transaction requirement BLOCK | acceptance/import deletion, SHA/scope/set-digest/member changes all reject next read; multi-SELECT read is not one snapshot transaction, R-SNAPSHOT below |

Frozen public Schemas, models, Provider protocols and generic Orchestrator have no diff against main.
`offering_digest.py` uses all current public CourseOffering fields via model_dump(mode='json'),
canonical JSON with allow_nan=False; identities sorted by (semester, course_id, class_id).
Manifest now includes merged_offering_count + merged_offering_set_sha256 and per-campus bindings.
Raw bytes, manifest identity and normalized offering-set digest remain distinct.
Inventory/campus records do not prove actual acquisition authenticity or human approval;
this is an explicit external trust prerequisite, not a new school-data claim.

## 3. Full-semester Gate

Structural five-shard orchestration PASS; end-to-end persisted acceptance Gate **BLOCK** (R-CONTENT).
`_read_shard_bundle_once()` hashes and parses the same raw byte object. Optional later re-read
only detects changes. `_require_campus_acceptance()` matches raw digest, campus scope/id,
canonical source, completeness, loaded/reported/offering counts and normalized content digest.
Manifest carries inventory SHA, fixed five IDs/numbers and all requested content fields.
Equivalent validated manifest key ordering/whitespace preserves canonical SHA in independent probe;
changed merged content digest changes manifest SHA. Generator fixes shard ordering;
external strict validator normalizes shard array ordering.

20-case coverage: valid five; missing North/any shard; duplicate ID; reused bytes; unknown/alias;
wrong approved number; semester mismatch; partial/empty; baseline drift; below/above baseline;
duplicate/conflicting identity; independently recounted unique merged count; artifact mismatch;
campus record digest mismatch; normalized payload substitution; manifest tamper.
These checks executed in the actual focused suites, supplemented by the independent key probes.
No skip/force/partial escape route found. A zero-count shard remains rejected under current policy.
North is allowlisted but operationally suspended: no real full-semester acceptance issued.

## 4. Provider Gate

**BLOCK**, despite the following passing checks:
exact requested semester, explicit full scope/SHA, deterministic row order, membership counts,
identity matching, individual payload hashes, dataset hash, later record deletion and stale-row exclusion.
It revalidates using load_accepted_offerings() on every call; no init-only rows cache/fallback.
However, its expected content digest comes from a mutable acceptance row that a supported import can
replace under the same pinned SHA; its claimed snapshot transaction is not actually started.

### R-CONTENT — same SHA can be rebound to a different accepted dataset

Locations (831c0e3/cb585c1/d097f51 shared Store):
`backend/app/course_data/store.py:820-865`, especially `:830-837`.
`import_offering_snapshot()` updates acceptance.offering_set_sha256 and replaces membership on
conflict, while course_data_import retains only the first counts, not the first content digest.
Same-cardinality replacement leaves the two metadata planes' compared fields equal.

Independent reproduction uses a real five-shard acceptance, not a forged declaration:

1. Produce valid synthetic full acceptance D, import its merged rows, construct Provider pinned to D SHA.
2. Keep all five identities, count, source and scope unchanged; change only the first course_name.
3. Call supported import_offering_snapshot(path, changed_snapshot, artifact_sha256=D SHA, scope=D scope).
4. Normalized offering digest differs from D.manifest['merged_offering_set_sha256'].
5. Existing Provider returns the replacement; actual runtime factory + POST returns **200** under D SHA.

Probes: `test_diagnostic_same_count_reimport_still_rebinds_approved_sha` and
`test_diagnostic_real_api_serves_reimported_content_under_old_sha`.
Builder's `test_reimport_with_different_content_under_one_identity_fails_closed` changes
cardinality from 1 to 2, so it only detects metadata count drift; it does not cover this case.

Minimal fix: before any rows/membership write, preserve and compare the original acceptance content
binding for the full `(SHA, semester, scope)` identity. Identical content reimport may repair rows;
different content under an existing identity must reject atomically. New content requires a new
full-semester acceptance/manifest SHA. Pin the immutable original offering-set/membership association,
not a newly computed expectation from current rows. Ensure initial issuance is tied to the validated
manifest; importing arbitrary full snapshots must not manufacture formal acceptance.
No public contract change is needed. Add same-count, same-identity reimport regression at Store,
long-lived Provider, newly constructed Provider and HTTP runtime levels.

### R-SNAPSHOT — one connection is not a consistent multi-SELECT read transaction

Locations: `backend/app/course_data/store.py:623-636` and `:1078-1200`.
`sqlite3.connect()` uses default legacy transaction control; SELECT does not implicitly BEGIN.
The `_open_store()` context and commit() at exit do not start a transaction for these reads.

Independent trace callback fires before provenance SELECT, after acceptance metadata was fetched.
It records `connection.in_transaction == False`. A second native SQLite connection commits
DELETE FROM course_data_acceptance before remaining member/row queries; this read still returns five rows.
Probe: `test_diagnostic_selects_have_no_snapshot_transaction`.
Sequential next read correctly fails, so this is a concurrent consistency gap, not a repeat of
the old init-only cache bug. A valid result must come from one defined read snapshot.

Minimal fix: explicitly begin a read transaction before validation's first SELECT and hold it through
all metadata/member/content queries and materialization; reliably rollback/close on failures.
Use supported transaction control for the supported Python versions. Test WAL-mode competing commits
with barriers, not sleeps: all reads must use one snapshot, never a mixture of metadata epochs.
Do not start BEGIN IMMEDIATE for a read-only path or mutate database state to claim validation.

## 5. Runtime Gate

**BLOCK** on inherited R-CONTENT/R-SNAPSHOT; normal refusal/wiring paths PASS.
Uses explicit five config variables and actual CurriculumCaseProvider, StoreBackedCourseDataProvider,
RestrictedPlannerProvider. No raw bundle/campus/Mock fallback found.
Actual API independent probes: missing DB, wrong pinned SHA, wrong configured/request semester,
deleted acceptance/import, wrong scope/hash, missing/fake member, missing accepted row ->
503 detail.error=real_pipeline_not_configured.
Actual API counterexample: same-count reimport changed content -> **200**, not required fail closed.
Provider readiness exceptions have explicit 503 mapping; API input errors preserve normal 422 semantics.
No request for credentials or school access was made.

## 6. Synthetic Production E2E

Happy-path **LEVEL1 synthetic production wiring capability verified**; complete safety Gate **BLOCK**.
Builder E2E uses real runtime dependency without dependency_overrides, real Curriculum files,
accepted synthetic SQLite and real RestrictedPlannerProvider. Existing suites pass.
Independent E2E uses our own synthetic capture/store acceptance, only reuses the Builder's
synthetic Curriculum document factory (no Builder gate assertions), and records actual Planner
arguments while delegating to the real Planner implementation.

Verified exact all-and-only accepted offering payloads, current_schedule and every nondefault
Preference value pass-through, UNKNOWN meetings preserved, partially_feasible/manual_confirmation,
no Mock offering loader call, and multiple real 503 mutation paths.
Builder E2E additionally covers a matching Curriculum course that gets an actual suggested class.
No Real LEVEL2/LEVEL3 claim. No blanket E2E PASS while R-CONTENT counterexample returns 200.

## 7. Independent probes / execution evidence

Run from the selected Builder archive/backend:

```bash
PYTHONPATH=/tmp/ai-education-closure-d097f51/backend \
  /workspace/.venvs/ai-education/bin/python -m pytest -o addopts='' -q \
  /workspace/AI-education/reviewer/full_semester/test_closure_probes.py
```

**42 executed / passed**; 39 passing behavior checks + 3 diagnostic counterexamples.
Passing diagnostic tests explicitly reproduce remaining BLOCKs, not production readiness.
No silent xfail, no assertions disabled, no expected-failure tests added to backend default testpaths.

Focused Builder suite: acceptance module + full CLI + Provider + runtime + synthetic E2E:
**241 passed**, exit 0.
Targeted Store/captured-pages/campus CLI/contracts/Orchestrator/Planner/API suite:
**483 passed / 2 skipped**, exit 0; optional reader-dependent skips are not passes.
All new-HEAD tests ran against d097f51, whose ancestor stack contains the reviewed fix heads.
Main full backend was not rerun; no full backend/compileall/frontend merge-gate run was warranted
because focused independent counterexamples prevent merge readiness.
Known unrelated warning: installed FastAPI/Starlette TestClient warns about future httpx2 support.

## 8. PR comments

`gh pr list --state open --limit 30 --json number,title,headRefName,isDraft`:
GitHub GraphQL returned Forbidden. No credentials inspected/requested; no PR comments left.
Read-only Git pull refs did not identify a PR for these four latest HEADs at audit time.
Exact comment text for the applicable Builder Draft PRs follows.

```text
Architecture Review: BLOCK

File / area: backend/app/course_data/store.py:830-837 and :854-865; acceptance import / Provider / runtime.
Invariant: a pinned full-semester manifest SHA must identify the exact originally accepted dataset, including every public payload field.
Independent reproduction: generate and import a valid five-shard synthetic acceptance D; change only course_name in one offering, keeping identities/count/source unchanged; reimport with D's existing manifest SHA. The stored offering-set hash and members are refreshed. The existing Provider returns the changed offering and actual POST /api/v1/plan returns 200 under unchanged D SHA. See reviewer/full_semester/test_closure_probes.py diagnostic_same_count_reimport and diagnostic_real_api tests.
Impact: same-cardinality content substitution is treated as approved data; the original B3 is only partially closed. The existing changed-content reimport test changes count, so misses this case.
Minimal fix: make the original acceptance identity-to-content/membership association immutable; compare prior content binding before any writes and atomically reject different content under the same SHA. Permit exact-content repair only. Add same-count/same-identity regression tests through Store, both Provider lifetimes, and actual runtime API. New content requires a new validated manifest SHA.
```

```text
Architecture Review: BLOCK

File / area: backend/app/course_data/store.py:623-636 and load_accepted_offerings():1078 onward.
Invariant: metadata, membership and rows must be validated in one consistent SQLite read snapshot.
Independent reproduction: trace the SELECTs during load_accepted_offerings on valid synthetic data. Before provenance SELECT, connection.in_transaction is False. A second SQLite connection commits deletion of the acceptance row after the first metadata SELECT; the current read still returns all five offerings. See test_diagnostic_selects_have_no_snapshot_transaction.
Impact: the claimed consistent read transaction does not exist with default legacy sqlite3 transaction control; sequential deletion tests pass but concurrent metadata/row epochs can be mixed.
Minimal fix: explicitly begin and retain a read transaction before the first validation SELECT, through complete materialization, with rollback/close on failure. Add a WAL-mode two-connection barrier test proving one snapshot. Do not rely on a contextmanager/commit-at-exit to begin SELECT transactions.
```

## 9. Remaining blockers

R-CONTENT: same approved SHA accepts changed dataset via supported reimport (original B3 incomplete).
R-SNAPSHOT: consistency is documented but no explicit SQLite read transaction (new concurrent gap).
North suspension remains an external operational blocker for actual acquisition; no synthetic input
can replace it. No further public signature/Schema changes required to fix these two code issues.

## 10. Which Gate is ready to merge

No complete Full-semester/Provider/Runtime/Synthetic-E2E Merge Gate is ready at these HEADs.
Exact-byte and campus-binding **subchecks PASS**, direct corruption and sequential revocation checks PASS.
This is not permission to merge the cumulative branch with outstanding R-CONTENT/R-SNAPSHOT.
Reviewer branch only contains docs and test probes; no production/Builder code edits or merges.

## 11. What still requires real school data

North restored under authorized operational workflow; all five real campus artifacts independently
accepted with reviewed inventory/digest/scope; window-stable real baseline; accepted full-semester data;
approved real Curriculum/student inputs and representative real E2E. We performed none of these
network/data activities. Formal Real E2E remains **LEVEL0**; the verified synthetic happy path proves
only **LEVEL1 wiring capability**. Final discovery is repeated before reporting; unchanged HEADs
are not grounds for expensive reruns.

## Latest steering: immutable identity first

用户明确要求：等待 `fix/store-provider-continuous-verification` 的新 HEAD，先独立验证
same SHA X + Dataset A -> Provider -> same identities/count but changed Dataset B 的第二次 import
必须 fail closed 且不能影响 Provider 返回 A；此外 stored canonical manifest 重算 SHA 必须等于
配置 acceptance SHA，semantic acceptance/member records 不允许 UPDATE。
仅此 gate PASS 后才继续新 HEAD 的 Runtime/E2E。上文 Runtime/E2E 是 steering 前已完成的
旧 HEAD 证据，不能当作绕过此顺序的许可。

新增严格 gate `test_immutable_identity_gate.py`，明确为 reviewer-only / expected-to-fail-until-fix，
无 xfail mask、不进 default backend suite。已在旧实现上确认：
1. changed payload 重导入不抛错，严格 rejection assertion 失败；
2. test-only SQLite trigger 直接观测 semantic acceptance UPDATE，即使 exact-content reimport；
3. 旧 acceptance schema 不存 canonical manifest，无法执行 stored manifest -> SHA -> configured SHA 校验。
等新 HEAD 后先适配其正式 manifest storage/import 路径，再执行此 gate，不接受 Builder 自称修复。
