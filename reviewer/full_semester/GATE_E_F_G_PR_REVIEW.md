# Gate E/F/G final PR-level architecture review

## Exact stack

Fetched all remotes/pruned, then explicit all-branch refspec. Public GitHub PR pages
(baseBranch/headBranch/headSha and Draft state) and Git `refs/pull/*/head` independently agree:

- main: faff3093a60e9205443366944bdce60039956cd6 (merged PR #45).
- Draft #46: base main; head feature/frontend-real-path-readiness-final,
  19970db49d571c34a50a5717c52ea2ed754a813e.
- Draft #47: base feature/frontend-real-path-readiness-final;
  head feature/xlsx-completed-courses-import,
  0727902930532722f23df6f5d2494544b37bc00e.

Both ancestor checks pass. Reviewed main -> #46 and #46 -> #47 only.
No Course Data/Provider/Runtime/plan API implementation changes. main.py changes only
import/register the new router; existing middleware/error handlers unchanged.
No merged #42-#45 red-team sweep repeated.

## PR #46: Architecture Review PASS

Six-file diff: three frontend source files, new 647-line readiness suite, status/worklog.
Real plan URL remains /api/v1/plan, no Real -> Mock request fallback. Error UI distinguishes
readiness 503 from 500 server failures, loading and success transitions covered by mounted
App with fetch assertions. Mock baseline and Real result provenance are shown separately.
Real channel labeling denotes the endpoint path, not a claim of independent real-artifact
verification or backend X-Data-Source: real header.

Neutral meetings/location labels preserved; selected classes presented as suggested classes,
feasible not described as immediately executable. changes/risks/unresolved empty arrays only
state absent records; this PR removes the old resolved/no-problem assertion for unresolved.
Preferences presented as input with backend result responsibility, not fully enforced rules.
No frontend conflict/recognition/priority algorithm or capacity threshold introduced.
UNKNOWN/manual_confirmation types/messages retained in rendered output.

Readiness suite is not just test names: real App mounting, actual click/deferred fetch state,
response markers and request counts assert 200/503/500 behavior; component tests assert empty
array and UNKNOWN wording; code checks supplement these rather than replacing them.
Tests enable the Real flag only in Vitest; production default remains demo-disabled.
User-facing stale API-not-implemented text removed. A historical stale comment remains in
vitest.config.ts ("接口未合并前"), not rendered UI or changed production behavior; editorial
cleanup is non-blocking. Status quotes obsolete wording explicitly as obsolete.

Independent commands on the exact #46 archive:
- npm test: **134 passed**, 9 files, readiness **21 passed**.
- npm run typecheck: PASS.
- npm run build: PASS.
- node --check verify_all_scenarios.mjs: PASS.

## PR #47: Architecture Review BLOCK

### Blocker F-LENGTH-CLASSIFICATION

Area: backend/app/api/completed_courses.py:130-139, especially line 136.
Invariant: input-length boundary documents missing/invalid Content-Length -> 411 and
oversized declared length -> 413, before consuming body. Invalid upload metadata must not
escape this boundary as an unrelated internal 500.

Reproduction on the actual FastAPI app/router, without dependency overrides:

1. POST /api/v1/completed-courses/import, Content-Type application/octet-stream,
   Content-Length = 4301 ASCII '9' digits, body b'abc'. TestClient with
   raise_server_exceptions=False: **HTTP 500 Internal Server Error**, expected 413.
   Python's integer-string conversion digit limit raises ValueError at int(raw.strip()).
2. ASGI HTTP scope Content-Length raw b'\xb2' (Latin-1 superscript digit), no body consumed:
   **HTTP 500**, expected invalid-length 411. str.isdigit() accepts it, int() rejects it.

Strict independent probe file test_xlsx_pr47_gate.py: **24 passed / 2 failed**. No xfail/skip.
The two failed nodes are test_declared_length_boundary_http[4301-digit-oversized] and
 test_non_ascii_digit_content_length_is_client_error.

Important scope/evidence limit: a separate real localhost Uvicorn/h11 listener probe
returned **HTTP 400 Bad Request for both inputs before the app**. Therefore this is an
application/ASGI error-classification and documented-contract blocker, not evidence of an
upload-size bypass, file parsing on oversized input, secret leakage, or public Uvicorn
500 exploit. Transport validation does not make the app's explicit boundary correct across
ASGI hosts/tests. Ordinary oversized declared length and lying oversized actual stream
both correctly return 413, as independently verified.

Minimal fix: validate ASCII decimal syntax explicitly; strip leading zeroes and compare
significant digit count/value lexically with MAX_UPLOAD_BYTES before bounded int conversion.
Map invalid syntax to ERROR_LENGTH_REQUIRED (411) and oversize to ERROR_TOO_LARGE (413).
Catch conversion errors only at this input-parser boundary if needed; do not add broad
exception swallowing around runtime or workbook processing. Add both regression cases.

### Other #47 checks: passed

- New additive POST endpoint; unchanged plan request/response/public schemas/Provider ports.
  Route guard still exact set equality, registering only the new endpoint.
- Two explicit media types; no filename-based path/identity. Declared and streamed caps,
  empty/malformed/wrong-header/formula/unexpected-sheet refusal independently exercised.
- Existing xlsx_reader reused; it calls existing normalize_completed_courses. No matching,
  equivalence, Curriculum Diff, prerequisite or fixed Case A mutation/reimplementation.
- Duplicate course attempts retained with distinct source_record; duplicate sequence refused;
  missing course identity remains pending, never invented; Unicode preserved.
- Macro .bin parts not read, confirmed with ZipFile.read guard on successful input;
  XML formulas rejected, never evaluated.
- Real temp file observed deleted after success, domain parse rejection, unexpected reader
  RuntimeError. Response omits notes, path/raw XML/private markers, including error 500.
- Actual streaming ASGI chunks cross 8MiB on second chunk -> 413; third chunk never read.
  Missing length -> 411 without any body read.
- Valid API fragment round-trips through existing normalization. No Mock planning loads.
- No schema/contract/backend-core diff, committed binary/Office material or secret literals.
  Only secret-pattern scan text in audit docs matched PRIVATE KEY regex, not an actual key.
- Gate G audit aligns with unchanged core semantics, PR #39 supersession, LEVEL1 synthetic
  versus formal Real E2E LEVEL0. Its regression section is a Builder snapshot, not substituted
  for this independent run. It missed the two input-length application-boundary cases above.

## Cross-stack: BLOCK (PR #47 blocker)

Bases/ancestry/scope are correct; no dependency cycle or frozen backend overwrite. Gate E
can progress independently. Whole stack is not ready until F-LENGTH-CLASSIFICATION closes.

## Backend/XLSX verification

On exact #47 archive:
- Existing XLSX API + reader targeted: **140 passed**.
- Curriculum targeted + integration orchestrator + runtime/API: **1208 passed**.
- Independent reviewer XLSX probes: **24 passed / 2 failed** as above.
- No frontend diff between #46/#47, so #46 frontend verification applies to stack top.
- Existing two platform-sensitive Curriculum reader tests and implementation files unchanged
  from main; both test files were included in targeted run, with no failures on this Linux
  environment. No skip/xfail added to hide those known Windows behavior differences.
- Full backend/final compileall regression not run: user condition requires both PRs to have
  no blocker. These checks remain pending after #47 fix. Node syntax check passed with #46.

## Non-blocking hardening and readiness

- real /api/v1/plan lacks X-Data-Source: real: deployment/product provenance decision,
  not automatic blocker; frontend labels the channel and does not claim header verification.
- XLSX endpoint lacks auth: explicit documentation says unimplemented and required for real
  deployment; this is synthetic/local Demo ingestion, not claimed production-ready public API.

**Merge readiness: not ready**. Expected order after closure remains #46 -> #47.
No merge, no production edit, no school access. Reviewer test/docs only. No PR comments
published in this round (task requests review output, not comment publication).
