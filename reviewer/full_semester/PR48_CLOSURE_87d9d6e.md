# PR48 focused closure review — 87d9d6e

## Revision / scope

Fetched `--all --prune` and explicit all-heads refspec. GitHub PR48 metadata:
base main, head feature/real-e2e-readiness-tooling,
87d9d6e26d7ab1678833448e9cbdfa082ce2d98b. Branch and refs/pull/48/head
independently agree; final recheck unchanged. main67c85857126ea62d898acc003768fe2c5b9b17fa.
Review only previous PR48 blockers, using archive /tmp/ai-pr48-87d9d6e.
Diff against main is empty for schemas, backend/app and frontend.
No production edits, merge, real school access, credentials, or subagents.

## Verdict

PR48: BLOCK. Orchestrator safety: BLOCK. Docs/evidence: BLOCK.
Synthetic preflight: PASS (LEVEL1 only). Capture/export binding: PASS for intended
browser Console execution. Default env publication concurrency protection: PASS.
North operational readiness remains suspended; this review does not resume it.
READY FOR USER FULL REAL CAPTURE: NO. Merge readiness: not ready.

## R48-ENV remains BLOCK — original destructive attack still works

Real CLI, generated five synthetic bundles, actual campus/full-semester acceptance,
SQLite import and Provider readback; no store/acceptance mocks:

```
--sqlite <local>/accepted.sqlite --env-out <local>/accepted.sqlite --overwrite-env
```

Observed exit0, status ready, SQLite magic false; subsequent actual SELECT raises
sqlite3.DatabaseError: file is not a database. Renaming force to overwrite-env and
validating env content bindings does not protect the output destination.
_assert_ready_binding validates the database BEFORE the env write, while
_assert_env_file_binding validates env text, not database readability afterward.

Required closure: reject env output aliases to protected inputs/outputs before writing
(including verified/campus DB, bundles, inventory/handoff, curriculum input and other
critical local artifacts; resolve symlinks and existing hardlink identities). Explicit
overwrite applies only to a separate env destination. Never return ready after destroying
verified artifacts. Add the actual CLI alias regression, not only injected env-value tests.

Fixed portion: deterministic competing creation at os.link publication boundary rejects
and preserves CONCURRENT=keep. Atomic exclusive publication PASS. VerifiedStore-derived
env values/binding checks are useful, but do not close destination aliasing.

## R48-SOURCE-EVIDENCE remains BLOCK — empty approval can authorize eligibility

Actual CLI generated inventory + handoff drafts from synthetic test bundles. Independently
changed ONLY handoff_state from draft to approved; approved_by and approved_at remained
null. Re-ran actual acceptance/import/readback with that handoff.

Observed exit0, level2_eligible=true, level2_blockers=[], despite no approval identity/time.
_validate_handoff does not validate those fields, collector commit, or capture timestamps;
returned summary merely echoes them. This demonstrates a missing mandatory evidence check,
not a claim that synthetic input was truly acquired or human-approved as real.

The new human handoff/digest reconciliation is a useful partial fix. However, the mandatory
record still does not link the independently approved real Curriculum input digest/version;
L2-1 still relies on data_source=real/runtime ready. The original requirement explicitly
covered both Curriculum origin and five capture digests. CLI states curriculum is only
echoed and never checked; its eligibility must not substitute for that missing evidence.

Required closure: require nonempty validated approval identity/time and acquisition
metadata appropriate to the documented controlled handoff; reject incomplete/invalid
records. Make a sanitized, independently reviewed real Curriculum source record with
input digest/version mandatory for LEVEL2/3, along with five capture digests and positive
non-synthetic review. The CLI need not validate Curriculum business logic or authenticate
humans cryptographically; docs must not treat its partial gate as sufficient real origin.
No credentials, raw rows, student data or private free text should be required/reported.

## Capture commands closed

Runbook now assigns `sharded = await ...` before exports. Exact first two JS blocks
execute successfully in a Node vm sloppy-script context matching intended browser Console
binding semantics, with only collector network methods replaced by offline stubs.
They fail in strict ESM due to undeclared assignment; that portability concern is nonblocking
for browser Console. `const sharded = await ...` is a clearer optional improvement.
This replaces the old strict-only blocker verdict; no actual capture traffic performed.

## Independent evidence / regression

Repro suite: reviewer/full_semester/test_pr48_closure_probes.py.
Run from exact archive with PYTHONPATH=backend:backend/tests:

```
python -m pytest -o addopts='' -q /workspace/AI-education/reviewer/full_semester/test_pr48_closure_probes.py
```

15 PASS, 2 strict failures: database destination alias and null approval eligibility.
No xfail or skip hides these failures. Additional independent SELECT probe confirms
physical database destruction (not merely a claimed status inconsistency).

Builder readiness CLI/docs tests: 47 PASS.
Course Data acceptance/store/provider/snapshot + runtime/API + synthetic + XLSX +
readiness targeted: 541 PASS. Full backend: 2936 PASS, 2 skipped, no failures on Linux.
Known Windows-only Curriculum failures were not reproduced on this platform; Curriculum
production/tests unchanged by PR48. Frontend: 134 PASS / 9 files; typecheck and build PASS.
compileall backend/app, backend/tests, tools PASS; collector and scenario node --check PASS.

Actual --preflight --quiet: ready, LEVEL1-synthetic-preflight, synthetic=true,
level2_eligible=false, blockers synthetic_preflight_handoff/not_a_real_capture.
Five synthetic shards / fifteen rows remain synthetic preparation evidence only.
Passing Builder/full regression does not override the two independent failing probes.

## Single-line handoff

DeepSeek fixes only the two remaining blocker areas and returns new PR48 HEAD.
Reviewer independently reruns these strict probes and relevant regression. Do not merge,
change frozen contracts, access schools, or resume North without authorized prerequisites.
