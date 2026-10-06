# PR #48 final Real E2E readiness architecture review

## Exact revision and scope

Fetched all remotes/pruned plus all-heads refspec. GitHub public PR metadata and pull/head
ref confirm base main, head feature/real-e2e-readiness-tooling, SHA
8ea5c84950acf0f7e4d60e194c17f5443bf4a335. Current main:
67c85857126ea62d898acc003768fe2c5b9b17fa (merged #47). Final head recheck unchanged.

11 changed files: new preparation tool, two readiness tests and e2e/status/worklog docs.
No production backend/frontend/Schema/Provider contract changes. Merged #42-#47 trust/runtime
semantics were not reopened. Only new orchestration and operational/evidence claims reviewed.
All inputs in independent probes were synthetic/local. No school access or credentials.

## Verdict

- PR #48: BLOCK.
- Orchestrator safety: BLOCK (env output protection).
- Synthetic preflight: PASS (data preparation chain only, LEVEL1).
- Docs/evidence protocol: BLOCK (capture binding and mandatory source evidence).
- North readiness: PASS for conservative diagnostic plan; operational North remains suspended.
- READY FOR USER REAL CAPTURE: NO (review blockers and suspended North).
- Merge readiness: not ready. No merge performed.

## Blocker R48-ENV — env output can destroy the verified store

Area: tools/prepare_real_case_a_runtime.py:432-449 and orchestration's post-readback env write.
Invariant: env overwrite must fail closed and must not destroy input/verified artifacts or
return ready after invalidating the verified SQLite trust chain.

Independent actual CLI preparation (synthetic five-shard input, no mocked acceptance/store):

```
--sqlite <local>/accepted.sqlite --env-out <local>/accepted.sqlite --force
```

Observed: exit **0**, status **ready**, but file no longer starts with SQLite magic.
Subsequent sqlite SELECT raises **DatabaseError: file is not a database**. Provider readback
was successful before `_write_env_file` replaced those bytes with environment lines.
This is the new tool's output-alias failure, not a regression in the frozen Store implementation.
The same missing destination protection can allow env output to overwrite input bundles,
inventory/manifest/curriculum input when force is supplied.

Second independently reproduced no-force failure: `Path.exists()` observes absent output,
another creator writes CONCURRENT=keep before `write_text()`; tool overwrites it without force.
Deterministic instrumentation inserts the real disk creation at that boundary, reproducing
check-then-write race; no independent OS-thread scheduling claim is made.

Strict failed probes:
- test_env_force_must_not_destroy_verified_database
- test_env_race_default_must_not_overwrite

Minimal fix: before mutations, resolve/reject env destination aliasing protected inputs and
outputs (including symlinks/hardlinks when present). Create no-force output with atomic
exclusive creation; forced replacement should write completely to a sibling temporary file
then replace safely, after alias validation. Keep the explicit force permission limited to
an independent env output. Add both regression tests; retain unexpected-error propagation.

## Blocker R48-CAPTURE-BINDING — runbook cannot export its result

Area: docs/e2e/REAL_CAPTURE_AND_RUNTIME_RUNBOOK.md:37,52-59;
REAL_DATA_EXECUTION_MAP.md capture.command/output_command.
Invariant: documented capture -> export commands must execute as written.

Capture snippet only executes `await ...collectSharded(...)`; no binding named sharded is
created. Next snippet uses `toShardJson(sharded, ...)` and `toDiagnosticsJson(sharded)`.
Independent offline Node execution of the exact two documented JavaScript blocks, with
only network-facing collector methods stubbed, raises **ReferenceError: sharded is not defined**.
This tests variable binding, not capture transport; no real request performed.

Failed probe: test_documented_capture_export_commands_have_a_result_binding.
Minimal fix: assign the result (`const sharded = await ...`) in both runbook and execution
map, check cancellation/failure before export, and test the documented snippets together.
Also clearly gate full five-campus capture on authorized North resumption; suspended North
is not a command the user should silently retry past.

Non-blocking editorial mismatches: runbook says four mandatory env values but lists the
correct five; frontend request-only wording needs to exclude initial Mock demo bootstrap
(the frozen UI loads it once). The acceptance document's old main SHA is historical and
should be labeled/updateable rather than called current main.

## Blocker R48-SOURCE-EVIDENCE — LEVEL2 evidence must prove actual origin

Area: docs/e2e/REAL_E2E_EVIDENCE_PROTOCOL.md L2-1 and L2-10, LEVEL2 decision at lines40-41;
READINESS_DECISION_NOTES.md section1.2.
Invariant: LEVEL2 requires actual real Curriculum and five real captures; schema shape,
content/manifest hashes, a `real` field, absence of Mock header, and identity subset establish
integrity/channel consistency, not real acquisition provenance.

Independent diagnostic witness on this exact head, using synthetic E2E fixtures and the
actual app/factory/provider/Planner (no dependency overrides):

```
inputs_are_synthetic: true
curriculum_data_source_real: true
runtime_constructed: true
acceptance_sha_pinned: true
accepted_count: 5
http_status: 200
no_mock_header: true
selected_count: 1
selected_subset_accepted: true
dependency_overrides_empty: true
```

Thus the concrete mechanical evidence listed by L2-1/L2-10 is reproducible with explicitly
synthetic inputs, including a nonempty selected subset. This does NOT assert that synthetic
input meets the stated abstract no-synthetic condition, or that a human actually approved
it as real. It demonstrates that the proposed evidence for that mandatory condition cannot
establish it independently. Runtime `ready` does not authenticate Curriculum acquisition;
negative Mock-header evidence does not distinguish synthetic source-shaped data.

The older acceptance definition correctly warns about this (§1.2/§4), but the new LEVEL2
mandatory checklist needs to carry that source gate explicitly rather than relying on an
implicit interpretation of inventory approval.

Minimal fix: require a sanitized out-of-band real-source/handoff review record, linked to
Curriculum input digest/version and each of the five capture byte digests. Record the
approved capture context/method/run/version, who/when verified the handoff and a positive
non-synthetic determination, without auth values, rows or student data. Missing/unverifiable
source evidence must veto LEVEL2/3. This is evidence/process clarification, not a requirement
to implement cryptographic provenance or add X-Data-Source/auth in this PR.

## Successful orchestration/preflight checks

Ran exactly `python tools/prepare_real_case_a_runtime.py --preflight --quiet` using prepared
venv on the exact archive. Exit0; synthetic true, LEVEL1-synthetic-preflight, NOT Real E2E.
Five synthetic shards x three rows =15; stable baseline15; full_semester acceptance15;
manifest SHA equals persisted canonical manifest SHA and pinned Provider acceptance SHA;
membership/readback/Provider counts15; normalized set digest present. Four tool-produced
runtime values correct; Curriculum path intentionally absent and must be independently
approved. Temporary synthetic artifacts cleaned. No LEVEL2/3 achievement claim.

Tool composes existing validate/accept CLI functions and Provider load_accepted_offerings;
no duplicated parser/business logic, no skip/synthesized real North, no network/credentials.
Existing target SQLite rejects by default. Explicit existing-store identical import remains
idempotent, immutable Store semantics preserved. Missing South/North, duplicate/conflicting
identity, wrong semester, baseline drift, invalid inventory, existing DB collision reject;
row/member/acceptance tamper independently refused by orchestration readback helper.
Unrelated injected Provider ValueError propagates, not silently normalized as readiness.
All outputs are local; no real artifact committed. Input/output paths remain caller-controlled;
docs require external controlled storage, which is not a programmatic repository-path guard.

Independent reviewer suite: **13 passed / 3 failed**, no skip/xfail. Tests saved in
`test_pr48_readiness_probes.py`; the 3 failures are exactly the env and snippet issues above.

## North and hardening

Plan says North suspended, HTTP600 not evidence of rate limiting. Authorized manual
observations O1-O6 only; >=30-second pacing, no concurrent/automatic retries, explicit
401/403/429/login/error/privacy stops, per-session request bound12. No credentials/row logging.
Four-campus success cannot produce full_semester. Plan audit PASS, actual complete real
capture remains operationally blocked pending North resolution and authorization.

XLSX auth and Real X-Data-Source remain non-blocking deployment/product items. Docs explicitly
say absent, no auth/public deployment claim. Proposed positive source handoff evidence fixes
the provenance gap without requiring either header or auth implementation here.

## Final regression

On exact 8ea5c84 archive:
- Readiness CLI/docs + full-semester acceptance/CLI + Store/Provider/read snapshot +
  Runtime/API + synthetic E2E + XLSX API/reader targeted: **609 passed**.
- Full backend: **2913 passed / 2 skipped**, no failures.
- Frontend: **134 passed**,9files; typecheck/build PASS.
- compileall backend/app, backend/tests, tools PASS.
- node --check collector and frontend scenario script PASS.
- Combined PR whitespace check PASS.
- Existing Starlette/httpx deprecation warning only. Known two platform-sensitive Curriculum
  test files unchanged from main; no Windows-only failure reproduced on this Linux host.

Passing Builder regression does not override independent3 failed strict probes.
Remaining blockers: R48-ENV, R48-CAPTURE-BINDING, R48-SOURCE-EVIDENCE.
No production edits or merge; reviewer-only test/report/status/worklog changes.
