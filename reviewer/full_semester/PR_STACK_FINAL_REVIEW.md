# Draft PR stack final architecture review

## PR identity and bases

`git fetch --all --prune` plus explicit all-heads refspec refreshed remote branches.
GitHub GraphQL/REST reads returned Forbidden. Public GitHub PR HTML returned HTTP 200:
embedded baseBranch/headBranch/headSha metadata and Draft state independently verified;
`git ls-remote origin refs/pull/{42,43,44,45}/head` independently confirms exact heads.

| PR | Actual GitHub base | Actual GitHub head | SHA | Verdict |
| --- | --- | --- | --- | --- |
| #42 | main | fix/full-semester-acceptance-blocks | 831c0e35d6396f5e6071de86c3782fcd81914b22 | PASS |
| #43 | fix/full-semester-acceptance-blocks | fix/store-provider-continuous-verification | ec8ab6f761d42b0855b543d5995da231de7a9910 | PASS |
| #44 | fix/store-provider-continuous-verification | feature/case-a-runtime-wiring-store | b0931d7cc05f3627644f4781c05bf5c0a657065d | PASS |
| #45 | feature/case-a-runtime-wiring-store | feature/synthetic-production-e2e | 8fc18b9b44fc705fb777498e737632751b7be50c | PASS |

All four are Draft. Current main: 1cd08e043b89a6da0a5f04a1b8981b59fae3b035.
Each adjacent ancestor relationship confirmed. No old-head threat-model sweep performed.
Prior frozen trust-chain and independent Runtime/E2E findings retained at identical SHAs.

## Per-PR scope

### #42 — Acceptance: Architecture Review PASS

16 changed files; production changes limited to Course Data acceptance/content digests,
byte-based bundle parser/store acceptance plane and acceptance CLI. No runtime/frontend
behavior mixed in. Exact five approved shards (North mandatory), stable total, independent
campus acceptance record/inventory scope binding, per-row/set content digests, deterministic
canonical manifest and strict validation intact. `_read_shard_bundle_once` hashes/parses the
same bytes; second read is stability detection only. Raw artifact bytes vs canonical manifest
identity vs normalized offering content digest semantics clearly separated. No skip/force flag.
Diff contains no real captured artifact/data additions. Public Schema/frozen contracts unchanged.
This PR provides content-bound acceptance; stronger immutability/read snapshot is explicitly
introduced by #43, not assumed as a prerequisite for #42 acceptance to run.

### #43 — Provider: Architecture Review PASS

13 changed files. Immutable acceptance/member semantics, canonical manifest hash/metadata
binding, exact membership, every-read verification and stale exclusion intact. Offering rows
remain mutable/upsertable storage; semantic acceptance records/member sets cannot be rebound,
and rejected same-SHA imports roll back. No Provider data/cache bypass. `_open_read_snapshot`
begins before first authoritative SELECT; all manifest/metadata/member/row/set validation
stays inside context; final ROLLBACK precedes returning materialized result. Internal DB
column and scope-aware membership key changes documented in provider docs and worklog.

Explicit scope exception reviewed: main.py adds 28 lines for typed request-time
CourseDataAcceptanceError -> 503 mapping. This is documented error integration for the
Provider, not hidden runtime assembly/Planner behavior. It references only prior main
readiness/API definitions and the new Provider type, so #43 builds without future #44.
CLI is updated to supply canonical manifest and verify its digest, preserving #42 flow.
Provider Protocol/public Schema unchanged.

### #44 — Runtime: Architecture Review PASS

7 changed files, only one production file (planning_runtime.py). Direct accepted Store
Provider assembly with explicit full_semester digest; no raw bundle/campus/Mock alternative.
PR #39 frozen/superseded clearly documented (main originally has unavailable runtime seam,
not PR #39's unmerged production implementation). Typed domain/config/readiness handling only;
generic defects remain 500, request-time acceptance error mapped 503 by #43. No Course Data
or shared Provider/Orchestrator semantic changes. Prior 51 independent HTTP PASS retained.

### #45 — Synthetic: Architecture Review PASS

5 files: new synthetic tests and docs changes only. Earlier tests/production left intact;
existing response-doc changes correct a test-name reference/explain a historical test name,
not silently change trust semantics. Valid 200, fail-closed tamper/deletion/campus,
stale exclusion, exact inputs, UNKNOWN/manual confirmation, no Mock fallback covered by
prior independent 10 HTTP probes at this same SHA. LEVEL1 synthetic wiring only;
formal Real E2E LEVEL0, no Real LEVEL2/LEVEL3 success claim.

## Cross-stack: PASS

Linear ancestor stack, actual GitHub bases correct, no circular/future production dependency
or duplicate conflicting commit series found. Later layers do not alter frozen earlier
production semantics except #43's declared store strengthening and #44's runtime wiring.
No PR #39 code merged/reintroduced. Subsequent docs append/correct references; tests aren't
silently replaced by later layers. Each tested as its own archive, not by loading the top's
production package into lower-layer tests.

Per-layer verification:
- #42 full backend: 2628 passed / 2 skipped; compileall passed.
- #43 full backend: 2721 passed / 2 skipped; compileall passed.
- #44 Runtime/API: 98 passed; compileall passed. Prior independent Runtime 51 passed.
- #45 final regression below; prior independent Synthetic 10 + Runtime 51 passed.

## Final regression on latest top 8fc18b9

```
python -m pytest tests/test_course_data*.py tests/test_full_semester_acceptance_cli.py \
  tests/test_planning_runtime.py tests/test_real_plan_api.py \
  tests/test_synthetic_production_e2e.py -q -o addopts='' --tb=short
python -m pytest -q -o addopts='' --tb=short
python -m compileall -q backend/app backend/tests tools
```

- Targeted (Course Data, Provider, read snapshot, acceptance CLI, Runtime/API, Synthetic):
  **1103 passed**.
- Full backend: **2823 passed / 2 skipped**.
- compileall: passed (correct archive-root paths used).
- Combined final stack diff whitespace check passed.
- Existing Starlette/httpx deprecation warning only. Frontend not rerun.

## GitHub comments and merge readiness

Separate exact comments: `pr_comments/PR42.md`, `PR43.md`, `PR44.md`, `PR45.md`.
Attempt `gh pr comment 42 --body-file ...` returned GraphQL Forbidden. No comments published;
remaining comments saved individually rather than retrying the same forbidden API. Public
read access does not grant comment-write authorization. This tool permission limit is not a
production architecture blocker, and PR base/head were verified through public metadata.

**Merge readiness: ready**, from architecture/validated-stack perspective.
Recommended order **#42 -> #43 -> #44 -> #45**. No merge performed; no production changes.
School access/Real E2E not performed or implied by readiness. Only reviewer docs updated.
