# PR48 final closure review — 2e76e04

## Exact HEAD / scope

Authoritative/fetched branch and refs/pull/48/head:
2e76e044744a572d815f7fcc43331c8a0f77dd4a. GitHub PR metadata independently confirms
base main, head feature/real-e2e-readiness-tooling, same full SHA. Final ref recheck unchanged.
main67c85857126ea62d898acc003768fe2c5b9b17fa. Fetched all/pruned and all-heads refspec.
Used /tmp/ai-pr48-2e76e04 archive. No production edits or merge. No school/network capture,
credentials or real student data. Single-agent independent review.

Diff against main is empty for public schemas, backend/app and frontend. Frozen Provider,
Store, runtime semantics unchanged. Closed capture binding/race issues not reopened.

## Requested gates

- PR48: BLOCK.
- ENV READY INVARIANT: PASS.
- HANDOFF APPROVAL GATE: PASS.
- CURRICULUM PROVENANCE GATE: BLOCK.
- COMBINED LEVEL2 GATE: BLOCK.
- READY FOR USER REAL CAPTURE: NO.
- merge readiness: not ready.

## ENV / READY — independently PASS

Actual production CLI rejects --overwrite-env, --force and --overwrite; options absent
from parser. Existing env output preserved byte-for-byte; no ready. Using accepted DB itself
as env destination rejects, leaves actual accepted SQLite readable (one acceptance).
No independent DB path/SHA input to _runtime_environment: signature store + curriculum_case.

Independent successful CLI observes _provider_read_back twice: before env exists, and
again after publication, using identical resolved store path + exact acceptance SHA.
Read emitted env bytes: path == verified store; SHA == returned acceptance SHA == SHA256
persisted canonical_manifest_json. Final verification parses emitted env, resolves its DB
path and invokes actual authoritative Provider/readback again before returning ready.

Deterministic publication-boundary adversaries mutate accepted row, membership, delete
acceptance, corrupt file, unlink DB, redirect emitted DB path or SHA. All reject/no ready.
Only the hook scheduling is instrumented; actual SQLite mutations and authoritative reads
are real, not mocked results. An env file can remain after fail-closed final verification;
this does not count as readiness or authorize startup.

## Handoff approval — independently PASS

With independently valid Curriculum evidence, actual CLI probes approved_by empty/blank,
approved_at empty/malformed/naive timezone: level2_eligible=false, explicit blockers.
Valid nonempty approver + 2026-10-06T20:00:00+08:00 passes. Synthetic handoff and draft
handoff fail closed. Synthetic preflight remains LEVEL1 / synthetic=true / eligibility=false.
No cryptographic/human-authentication claim is inferred from local approval metadata.

## Curriculum — static negative matrix PASS, final consumed-file binding BLOCK

Actual CLI checks local case bytes against independently computed hashlib SHA256 evidence.
Valid approved case evidence passes together with valid Course Data evidence. Stable local
format/version IDs exist, no public Schema. Missing provenance/digest, malformed digest,
digest mismatch, synthetic, draft approval, approver empty/blank, timestamp empty/malformed/
no timezone, missing --curriculum-case, wrong case file and unsupported format/version
all prevent eligibility. Missing file exits nonzero/no ready; it currently raises a raw
FileNotFoundError traceback rather than structured domain output (hardening observation).

Remaining blocker is specifically binding provenance to the exact runtime input AFTER env
publication, as required by section C; this does not reopen frozen runtime semantics.

Actual CLI with five synthetic captures, real import/readback, correctly approved synthetic
local handoff metadata and provenance for Case A file A. Files are synthetic test material;
marking metadata approved/non-synthetic tests the gate, not actual school acquisition.
At _write_env_file boundary, first publish the real env, then perform one local disk mutation:

1. Replace A's bytes with valid Case A payload B (only a course-name payload changed).
2. Or leave A untouched, change emitted APP_CASE_A_CURRICULUM_CASE_PATH to another valid
   Case A file B with different byte digest.

In BOTH cases:

```
CLI exit: 0
status: ready
level2_eligible: true
level2_blockers: []
SHA256(file referenced by emitted Curriculum env) != approved Curriculum digest
build_planning_runtime(actual emitted env).reason: ready
```

This is an actual runtime-consumable substitute, not malformed input that runtime refuses.
The probe uses frozen build_planning_runtime with no dependency override; it does not
claim Real LEVEL2 or make a real HTTP/school request.

Cause: _validate_curriculum_provenance at tool lines1649-1651 runs before env publication
1665-1666. _final_readiness_verification checks emitted DB path/SHA/semester and reopens
Store, but never checks emitted Curriculum path or rehashes that case. level2_eligible at
1684 uses stale pre-publication curriculum_blockers/summary.

Minimal closure, confined to orchestration tool: in final readiness/evidence step, parse
actual emitted Curriculum path (or resolved configured path when env is not emitted),
require equality with the evidence-bound approved case path, hash those current bytes,
and rerun Curriculum provenance approval/digest checks. Use refreshed blockers/summary
for combined eligibility. Missing/changed/unreadable case must fail closed or veto eligibility.
Retain Store revalidation and no-overwrite behavior. Add BOTH strict actual CLI regression
probes. No public Schema or runtime semantic changes required.

## Combined gate / inheritance

Normal static matrix proves valid Course Data + invalid Curriculum => false; invalid
Course Data + valid Curriculum => false; both valid => true; preflight LEVEL1 => false.
However the publication-boundary Curriculum substitutions above wrongly satisfy both
validity gates, so final COMBINED LEVEL2 cannot PASS. Docs explicitly require LEVEL3 to
inherit full LEVEL2 Course Data AND Curriculum provenance; that inheritance wording PASS,
but stale eligibility must be fixed before the combined gate is trustworthy.

## Independent probes / final regression

reviewer/full_semester/test_pr48_final_invariants.py: 37 PASS, 2 strict FAIL (replacement
case bytes; redirected emitted Curriculum path). No skip/xfail conceals these failures.

Run using exact archive backend/tests on PYTHONPATH:

```
PYTHONPATH=/tmp/ai-pr48-2e76e04/backend:/tmp/ai-pr48-2e76e04/backend/tests python -m pytest -o addopts='' -q reviewer/full_semester/test_pr48_final_invariants.py
```

Specified Course Data acceptance/full-semester/store/provider/read-snapshot/runtime/API/
synthetic/XLSX/readiness CLI/docs targeted regression: 565 PASS.
Full backend: 2960 PASS, 2 skipped, no failures on Linux. Historical Windows-only
Curriculum failures do not appear on this Linux runner; Curriculum production/tests
are unchanged in PR48. Frontend134 PASS/9 files, typecheck and build PASS.
compileall backend/app/backend/tests/tools PASS; collector + frontend scenario node --check PASS.
Passing repository regression does not override independent failing invariants.

North operational readiness remains unresolved/suspended; no resumption or real-source
capture was authorized/performed by this review. Fix final Curriculum binding, obtain new
HEAD and independently close these two strict probes before merge/capture readiness.
