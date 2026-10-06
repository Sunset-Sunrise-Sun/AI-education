# PR48 final Curriculum closure — e684b87

Fetched all/pruned/all-heads refspec. Branch and PR48 pull/head:
e684b87ee663c3550725a2ff689dd38fcecff548. GitHub metadata independently agrees,
base main / feature/real-e2e-readiness-tooling; final recheck unchanged.
main67c85857126ea62d898acc003768fe2c5b9b17fa. Exact archive /tmp/ai-pr48-e684b87.
No production/public Schema/frontend diff against main. Review scope only final Curriculum
TOCTOU and resulting readiness. Single-agent, synthetic/local fixtures, no production
edits, merge, real school access or credentials.

## Verdict

PR48: BLOCK.
CURRICULUM FINAL REVERIFICATION: BLOCK for unconditional READY semantics; the actual
verified-Curriculum TOCTOU attacks are closed.
COMBINED LEVEL2 GATE: PASS.
READY FOR USER REAL CAPTURE: NO. Merge readiness: not ready.

## Closed final Curriculum attacks

Actual CLI and real import/Provider/readback, with synthetic test inputs and metadata that
exercise approval gates (not an assertion of actual non-synthetic school acquisition).
VerifiedCurriculum is frozen/slots dataclass, canonical resolved path, approved digest,
case/target-version/term, format/version, loader commit, approval state/by/at, synthetic.
Observed _runtime_environment only accepts store + curriculum and derives case path
from the verified object; attempting field reassignment raises FrozenInstanceError.

Unchanged valid input: status ready, both final_store_reverified and
final_curriculum_reverified true, level2_eligible true.

After real env publication, deterministic instrumented scheduling performs real filesystem
mutations. Byte replacement at same path, deletion, env case path changed to another
file (including identical bytes), replacement by directory, symlink rebinding, directory
symlink rebinding all fail closed/no ready. Symlinks actually created on Linux; no simulation
needed. Corrupted Store with valid Curriculum also fails closed/no ready. Injecting invalid
approval metadata into a replacement frozen verified object at final boundary fails closed.
Actual validation/hash/filesystem/provider functions not mocked; hook only inserts mutation.

Final verifier rereads emitted path, resolves/compares canonical target, checks is_file,
hashes current bytes, compares approved digest and reevaluates approval metadata before
setting final_curriculum_reverified. Previous two publication-boundary attacks are closed.

## Remaining blocker: status ready does not require both reverifications

User section B explicitly requires:

```
READY requires final_store_reverified == true AND final_curriculum_reverified == true
```

Independent actual CLI probe: start from otherwise valid inputs, remove only
--curriculum-provenance; keep actual --curriculum-case and valid Course Data evidence.
Observed:

```
exit: 0
status: ready
final_store_reverified: true
final_curriculum_reverified: false
readiness_scope: course_data_only
level2_eligible: false
APP_CASE_A_CURRICULUM_CASE_PATH: absent from emitted env
```

Suppressing the unverified case path and denying LEVEL2 are correct, and satisfy section
C11/D. However readiness_scope does not override the explicit universal status=ready
requirement. Tool still unconditionally returns status ready at line1857, including no
VerifiedCurriculum. This is the sole remaining blocker; do not reopen repaired TOCTOU paths.

Minimal closure: reserve status ready for both final flags true. For missing/invalid
Curriculum provenance return a clearly distinct partial preparation status (or fail closed),
without unverified case path and with level2_eligible false. Synthetic preflight can retain
LEVEL1 evidence without claiming complete readiness. Update readiness CLI/docs assertions
accordingly. No public Schema, Store, Provider or runtime semantic changes required.

## Combined provenance gate PASS

Independent actual CLI: Course Data approval invalid + valid Curriculum => eligibilityfalse;
valid Course Data + invalid/missing Curriculum => eligibilityfalse; both valid => true.
Missing provenance never emits verified case path. Synthetic preflight LEVEL1-only,
synthetictrue, eligibilityfalse. Docs L3-1 explicitly inherit full LEVEL2 Course Data AND
Curriculum evidence requirements. This PASS is eligibility logic, not actual Real LEVEL2/3.

## Regression / evidence

reviewer/full_semester/test_pr48_curriculum_final_closure.py: 13 PASS, 1 strict FAIL
(test_ready_always_requires_both_final_reverifications); no skip/xfail conceals it.
Reuses independently constructed inputs from reviewer test_pr48_final_invariants.py.

```
PYTHONPATH=/tmp/ai-pr48-e684b87/backend:/tmp/ai-pr48-e684b87/backend/tests:/workspace/AI-education/reviewer/full_semester python -m pytest -o addopts='' -q reviewer/full_semester/test_pr48_curriculum_final_closure.py
```

Readiness CLI/docs, full-semester/artifact acceptance, Store/Provider/read-snapshot,
runtime/API, synthetic E2E and XLSX targeted: 576 PASS. Full backend: 2971 PASS, 2 skipped,
no failures on Linux. No new failures; historical Windows-only Curriculum failures not
observed on this platform, production Curriculum/tests unchanged by PR48.
Frontend134 PASS/9files; typecheck/build PASS. compileall backend/app/backend/tests/tools
PASS; collector and frontend scenario node --check PASS. All independent filesystem
mutations are local synthetic material. No actual capture or HTTP acquisition performed.

North operational readiness remains suspended; this code review does not authorize resumption.
Fix only partial preparation vs complete ready status, return new HEAD for focused recheck.
