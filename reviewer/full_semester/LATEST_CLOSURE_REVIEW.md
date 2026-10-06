# Latest focused closure review

2026-10-06 (Asia/Shanghai). Latest fetched targets, not old reproduction baselines:

| Target | Exact HEAD |
|---|---|
| Provider fix/store-provider-continuous-verification | ec8ab6f761d42b0855b543d5995da231de7a9910 |
| Runtime feature/case-a-runtime-wiring-store | eb135a87b35d25c15cd9ab1bdbbfd786d4059fb3 |
| Synthetic E2E feature/synthetic-production-e2e | 6fa155cc2d685c6493450e3c4b9b216702b4195f |
| Acceptance fix/full-semester-acceptance-blocks | 831c0e35d6396f5e6071de86c3782fcd81914b22 |

Executed git fetch --all --prune and wildcard branch refresh; force-updated runtime/E2E refs refreshed.
Separate git archives of Provider and Runtime HEADs used for actual commands. No old cb585c1/ef910e3
implementation was treated as current. No production code, public contract, Builder branch, merge,
credentials or school network activity.

## R-CONTENT: PASS

Our independently generated five campus artifacts + campus acceptance DB + exact inventory produce
Dataset A / canonical full-semester manifest SHA X. Import includes canonical_manifest and constructs
actual StoreBackedCourseDataProvider. Eighteen Dataset B attack variants keep SHA, identities and row
count while changing course_name, teacher, credit, capacity, remaining_capacity or meetings; with original,
rewritten or omitted manifest. Every second import rejects atomically, including unchanged rows/audit
records after rollback. Both existing and reconstructed Provider return only A.

Stored manifest canonical reserialization SHA equals configured X; exact same-content reimport succeeds
under SQLite instrumentation triggers forbidding semantic acceptance UPDATE/member UPDATE/member DELETE.
Semantic rows and original accepted timestamps stay unchanged. Stored semantic/whitespace/duplicate-key/
unknown-field/non-JSON mutations reject on next read. No semantic UPSERT/member rebuild is used for
existing acceptance identity. These passing checks are execution evidence, not Builder assertions.

## R-SNAPSHOT: PASS

Independent WAL-mode two-connection/two-thread probes use Event barriers, no sleeps. Reader pauses
before membership SELECT after acceptance and manifest reads; Writer commits while paused.
Actual production _open_read_snapshot used, real validators delegated without replacing their results.
Trace and validation instrumentation observe transaction status through the full authority path.

| Writer commit | Reader result | acceptance/import/member/row SELECT transaction states | digest validators | finish |
|---|---|---|---|---|
| delete acceptance | complete epoch A | True / True / True / True | active | ROLLBACK |
| replace accepted row | complete epoch A | True / True / True / True | active | ROLLBACK |
| mutate membership | complete epoch A | True / True / True / True | active | ROLLBACK |

Reader transaction is already active at helper yield before first authoritative SELECT, remains active
through manifest, per-row and dataset digest verification, and closes with explicit ROLLBACK.
Writer commits confirmed; original payloads returned exactly, no mixed epoch.
Builder test_course_data_read_snapshot.py also executed: **8 passed**.

## STORE TRUST CHAIN: PASS / PROVIDER GATE: PASS

Independent Provider probes: **27 passed**, exit 0.
Existing Provider/Store targeted suite on ec8ab6f: **163 passed**, exit 0.
The three concurrent probes were separately rerun with observed state printing to record actual epoch A
outcomes, **3 passed / 24 deselected** (not three additional unique tests).
No public protocol/Schema changes made by reviewer. Provider branch is ready for its Gate PR review;
this does not approve downstream Runtime or authorize merging main.

## Runtime Gate: BLOCK

Provider passed first; then Runtime eb135a8 was actually exercised through real FastAPI dependency,
real CurriculumCaseProvider, accepted synthetic SQLite, real Store Provider and RestrictedPlannerProvider.
No dependency_overrides. Synthetic Curriculum payload factory is fixture-only reuse from Builder tests;
capture artifacts, acceptance, attack inputs and assertions are independently generated.

Independent Runtime probes: **14 passed / 1 failed**, exit 1.
PASS: missing/deleted acceptance, wrong SHA, campus-only DB, tampered canonical manifest/membership/row
all return 503 detail.error=real_pipeline_not_configured. Stale extra non-member is excluded from
the recorded actual Planner inputs. Mock planning loaders are instrumented to fail if called; no call.
Request-time CourseDataAcceptanceError is translated to required 503.
Unexpected RuntimeError/TypeError remain 500 both during assembly and request; request-time ValueError
also remains 500. No raw-bundle/campus/Mock/PR #39 fallback found.

### R-ERROR-CLASSIFICATION — unrelated construction ValueError is swallowed as readiness

File: backend/app/services/planning_runtime.py:254-261 at eb135a8.
The blanket `except (CourseDataStoreError, OSError, ValueError)` around Course Data construction turns
any ValueError into course_data_not_ready. Curriculum construction has the same broad class at :246-251.

Independent reproduction, with valid configured synthetic inputs and real API dependency:

1. Normal request returns 200.
2. Inject `ValueError('synthetic unrelated programming defect')` at build_course_data_provider.
   This is a fault-injection seam, not an invalid manifest/config/payload or typed readiness failure.
3. POST /api/v1/plan returns **503 real_pipeline_not_configured**, while the task explicitly requires
   unrelated programming/internal errors not be swallowed as 503 (expected 500).
4. Same non-readiness error at request-time Provider method returns 500; classification depends on stage.

Failing independent test:
`test_runtime_final_gate.py::test_unrelated_internal_error_is_not_swallowed_as_readiness[construction-ValueError]`.
Other five construction/request error cases pass, so the test distinguishes broad catch behavior from
global API exception mapping. No claim is made that this hides a particular known application bug;
fault injection demonstrates that the required error-classification invariant is violated.

Minimal fix: catch explicit readiness/normalization exception types. Translate expected document/DB/
Pydantic validation failures into typed readiness exceptions at their source, or catch precise validation
classes; do not classify arbitrary ValueError from Provider factory implementation as missing configuration.
Preserve current invalid-input 503 behavior and add construction-level unrelated ValueError regressions
for both factory boundaries. Do not merely remove existing invalid-source checks or fall back to Mock.

Exact review comment:

```text
Architecture Review: BLOCK

File / area: backend/app/services/planning_runtime.py:260 (and analogous Curriculum catch :246-251), HEAD eb135a8.
Invariant: CourseDataAcceptanceError/typed readiness failures map to 503 real_pipeline_not_configured; unrelated programming/internal errors must not be swallowed as 503.
Independent reproduction: with valid real factory configuration backed by our accepted synthetic DB, inject ValueError('synthetic unrelated programming defect') at build_course_data_provider, then POST /api/v1/plan through the actual dependency without overrides. Response is 503, expected 500. RuntimeError/TypeError at construction and ValueError at request time remain 500. See reviewer/full_semester/test_runtime_final_gate.py construction-ValueError case.
Impact: Runtime Gate's explicit error-classification requirement fails; a Provider assembly programming defect can appear as normal configuration/readiness failure.
Minimal fix: narrow the blanket ValueError catches to explicit expected normalization/validation types, converting expected invalid-source errors into typed readiness exceptions at their source. Add unrelated construction ValueError regression for Course Data and Curriculum while preserving invalid-data 503 behavior. No production change or merge made by Reviewer.
```

Existing targeted runtime/API suite: **65 passed**. Its passing tests do not cover this construction-level
counterexample. No PR comment posted; exact text is preserved here, no credentials handled.

## Synthetic E2E Gate: BLOCK / NOT EXECUTED

6fa155c was fetched, but Phase 3 was not executed because Runtime Gate failed. This is a prerequisite
BLOCK, not a claimed newly reproduced E2E defect. No current E2E LEVEL1 PASS asserted, and no Real
LEVEL2/LEVEL3 claim. Real E2E remains LEVEL0 with North operationally suspended.

## Final regression status

The user conditioned full backend/compileall/final E2E regression on all three Gates passing.
That condition is false; those final regressions were not run. No unrelated frontend rerun.
Only relevant Provider/snapshot and Runtime/API tests above were executed.

## Reproduction commands / ready branches

```bash
# Phase 1
cd /tmp/ai-education-provider-ec8ab6f/backend
PYTHONPATH=$PWD /workspace/.venvs/ai-education/bin/python -m pytest -o addopts='' -q \
  /workspace/AI-education/reviewer/full_semester/test_focused_provider_gate.py

# Phase 2 (only after Provider passes)
cd /tmp/ai-education-runtime-eb135a8/backend
PYTHONPATH=$PWD /workspace/.venvs/ai-education/bin/python -m pytest -o addopts='' -q \
  /workspace/AI-education/reviewer/full_semester/test_runtime_final_gate.py
```

Ready for Provider Gate PR review: fix/store-provider-continuous-verification at ec8ab6f.
Not ready for Runtime Gate approval: feature/case-a-runtime-wiring-store at eb135a8.
E2E Gate deferred: feature/synthetic-production-e2e at 6fa155c.
Remaining blocker: R-ERROR-CLASSIFICATION; prior R-CONTENT/R-SNAPSHOT are closed at these Provider HEADs.
Reviewer docs/tests remain on review/full-semester-runtime-redteam. No main merge.
