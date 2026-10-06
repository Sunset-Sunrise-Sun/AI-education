# Focused Architecture Review — ef910e3

2026-10-06 (Asia/Shanghai). This report supersedes cb585c1 conclusions for the HEADs below.

## Latest fetched HEADs

| Branch | HEAD |
|---|---|
| fix/store-provider-continuous-verification | ef910e3fd3c68b10d9d9ed42a39698f5e8a21f36 |
| feature/case-a-runtime-wiring-store | a67ba96d59a54e1dbf0396398e7608fa2b48c26f |
| feature/synthetic-production-e2e | f8675e2975a87dbe9c1f13db6f08bf16e5abd4d6 |

Ran git fetch --all --prune and explicit wildcard branch refresh. Provider is newer than cb585c1;
runtime/E2E forced updates were fetched rather than treating stale refs as authoritative.
Phase 1 executed on an independent git archive of ef910e3 at /tmp/ai-education-provider-ef910e3.
No production changes, Builder checkout edits, worktree, merge or school network activity.

## R-CONTENT: PASS

Independent synthetic five-shard artifacts, campus acceptances and inventory generate Dataset A and
manifest X. Import now supplies canonical_manifest=result.manifest, then constructs Provider pinned to X.
Six changed fields (course_name, teacher, credit, capacity, remaining_capacity, meetings) are tested
with three submission variants: original manifest, changed content-digest manifest under X, omitted manifest.
All **18** second-import attacks reject. All DB rows, semantic records and audit timestamps equal
the pre-attack snapshot afterward; existing and newly constructed Providers both return exact Dataset A.

Stored canonical_manifest_json round-trips to canonical bytes, recomputed SHA256 equals configured X.
Identical reimport succeeds with test-only SQLite triggers forbidding acceptance UPDATE/member UPDATE/
member DELETE: semantic acceptance and membership including initial timestamp remain unchanged.
Changed stored manifest content, whitespace, duplicate key, unknown field and invalid JSON all cause
next Provider read to fail closed. No semantic acceptance UPSERT/member delete-reinsert path remains
in the existing-identity import path; offering row repair/upsert is distinct and rollback-verified.

This closes the prior supported-import same-SHA content rebinding attack. It does not establish a
snapshot transaction or independent real acquisition approval.

## R-SNAPSHOT: BLOCK

Relevant code at this new HEAD:
- backend/app/course_data/store.py:823 opens sqlite3.connect with legacy defaults;
- :806-837 _open_store performs schema checks, yields connection and commits at exit, no explicit BEGIN;
- :1485-1493 load_accepted_offerings starts authoritative acceptance SELECT without opening a read transaction.

Independent probe uses actual SQLite WAL mode, two OS threads, separate connections and threading.Event
barriers (no sleeps). Reader starts Provider authoritative read, reads acceptance and pauses just before
real manifest validation. Writer commits one mutation; Reader continues the unchanged production validators.
SQL tracing records connection.in_transaction at the authoritative acceptance SELECT.

| Writer commit while Reader paused | Reader outcome | Transaction state at first authoritative SELECT |
|---|---|---|
| DELETE acceptance | complete original Dataset A | False |
| replace an accepted row payload | typed CourseDataAcceptanceError / fail closed | False |
| delete one membership row | typed CourseDataAcceptanceError / fail closed | False |

All threads complete and writer commits; no mocked validation result, no cached fixture returned.
The three probes **fail** the required explicit-transaction assertion. These cases do **not** establish
that mixed payloads were returned: the observed results were epoch A or refusal. The BLOCK is precise:
the required single explicit read transaction does not exist, and the claimed snapshot guarantee is unproven.
One connection/contextmanager plus commit-at-exit does not implicitly BEGIN for SELECT under the
validated Python 3.12 sqlite3 legacy transaction mode.

Minimal fix: start a supported explicit read transaction before the first validation SELECT, including
authoritative acceptance/manifest/member/row checks, retain it through payload/set digest validation and
materialization, then close/commit or rollback on failure. A dedicated read transaction path avoids
interfering with imports. Re-run the actual WAL/barrier probes: transaction state must be active and
outcomes must be one full epoch or typed refusal/legitimate locking. Do not use BEGIN IMMEDIATE for
this read-only validation path or infer readiness from source labels.

Exact comment text for applicable Builder Draft PR:

```text
Architecture Review: BLOCK

File / area: backend/app/course_data/store.py:806-837 and load_accepted_offerings():1485 onward, HEAD ef910e3.
Invariant: authoritative acceptance, stored canonical manifest, membership, rows, payload hashes and set hash must be read/validated in one explicit SQLite read transaction beginning before the first SELECT.
Independent reproduction: reviewer/full_semester/test_focused_provider_gate.py runs actual two-connection WAL probes. Reader pauses after acceptance read; Writer commits acceptance deletion, accepted-row replacement or membership mutation. All three log in_transaction=False at authoritative SELECT. Reader returns A for acceptance deletion and fails closed for row/member changes. These results do not prove a mixed dataset leak, but they fail the mandatory explicit snapshot-transaction gate.
Impact: R-CONTENT is closed, but R-SNAPSHOT and consequently Provider trust-chain gate remain BLOCK. A connection context and commit at exit do not BEGIN SELECT transactions in Python sqlite3 legacy mode.
Minimal fix: explicitly begin and hold a read transaction before validation's first SELECT through full materialization; rollback/close reliably. Re-run the WAL Event-barrier probes with active transaction and one-epoch/refusal outcomes. Do not proceed to Runtime/E2E gate approval until Provider passes.
```

No PR comment posted in this audit; the prior GitHub API Forbidden blocker remains, no credentials handled.

## Provider: BLOCK

R-CONTENT PASS + R-SNAPSHOT BLOCK => STORE TRUST CHAIN and PROVIDER GATE cannot be called PASS.
Public Schema/models/Provider protocols have no diff against main.

## Runtime: BLOCK / NOT EXECUTED

Fetched a67ba96; Phase 2 deliberately not run because Phase 1 Provider prerequisite failed.
This is a gate dependency BLOCK, not a claimed newly reproduced defect in a67ba96.

## E2E: BLOCK / NOT EXECUTED

Fetched f8675e2; Phase 3 deliberately not run because Provider/Runtime prerequisites have not passed.
No new-version LEVEL1 success asserted. Formal Real E2E stays LEVEL0; no Real LEVEL2/LEVEL3 claim.

## Independent probe evidence

```bash
cd /tmp/ai-education-provider-ef910e3/backend
PYTHONPATH=/tmp/ai-education-provider-ef910e3/backend \
  /workspace/.venvs/ai-education/bin/python -m pytest -o addopts='' -q \
  /workspace/AI-education/reviewer/full_semester/test_focused_provider_gate.py
```

**24 passed / 3 failed**, exit 1. The 3 actual failures are the 3 mandatory concurrent transaction gates;
no xfail masks and no default-suite changes. Expected-failure reviewer tests stay on reviewer branch.
Existing Store/Provider targeted suite on ef910e3: **163 passed**, exit 0. Passing Builder suite does
not replace the failed independent snapshot probes. No full backend/frontend rerun or later-phase tests.

## Remaining blocker / ready-for-PR branches

Remaining implementation blocker: R-SNAPSHOT, explicit authoritative read transaction.
No complete Provider/Runtime/E2E branch has a passing Merge Gate in this audit. R-CONTENT is a passing
subcheck only. Reviewer docs/probes are saved on review/full-semester-runtime-redteam; no production PR
approval or main merge. Final remote discovery checks for newer target HEADs before reporting.
