# PR #47 focused Content-Length closure

## Target and boundaries

Fetched/pruned all remotes plus all-heads refspec. GitHub public PR #47 metadata confirms
base feature/frontend-real-path-readiness-final, head feature/xlsx-completed-courses-import,
SHA c9043121c06b3cca353c235143b4cfe928ac27ec. Final Git pull/head reference agrees.
PR #46 remains frozen PASS; no architectural re-review of #46 or merged #42-#45.

Only new fix and its input boundary reviewed. Diff from prior #47 snapshot: API adapter,
ingest parser, tests and docs. Across #46 -> latest #47: no frontend, public schemas,
frozen contracts/models/integration, course_data/Store/Provider, planning_runtime or plan API
implementation change. main router registration remains the previously reviewed additive
endpoint. Existing HTTP 503/500 handlers not altered.

## Independent production-boundary probes: 30 passed

File: test_xlsx_content_length_closure.py. Actual FastAPI TestClient and direct HTTP ASGI
scopes (without Uvicorn/h11), real router/loader, no dependency overrides. Independent
fixture helpers generate only synthetic workbook bytes. Cases:

- Missing and empty Content-Length -> 411; no body consumed.
- Full-width/Arabic-Indic/superscript numerals -> 411. Unicode values additionally checked
  directly against the actual production parser; raw non-ASCII HTTP header bytes tested
  against real ASGI route (Starlette header decoding applies).
- Whitespace, padded digits/tab, +123/-1/1.0/1e3/0x20/1_000/1,000 -> 411; no body consumed.
- Normal ASCII decimals <= maximum accepted by production parser; valid workbook HTTP 200.
- Exactly 8 MiB real, valid stored ZIP workbook -> HTTP 200, all three records imported.
  Fixture expands an ignored synthetic padding part; no parser/factory success fake used.
- MAX+1 and 10000-digit decimal strings -> 413 before body read.
  Module-local int instrumentation confirms giant input never calls int; bounded input
  can only convert up to seven digits. Docs intentionally reject excessive digit length
  even for long leading-zero strings; that policy independently verified as 413.
- Actual streamed bytes cross maximum on second chunk -> 413; third chunk never consumed.
- Declared/actual length mismatch -> documented 400 mismatch.
- Malformed workbook -> documented 400 invalid.
- Error bodies omit private header/body markers, paths, stack traces and raw XML.
- Parser AST confirms explicit isascii/isdigit and no strip call.

All requested refusal paths never return 500. No large integer conversion, no dependence
on transport rejecting first, and no upload limit bypass observed. Prior app error mapping
blocker F-LENGTH-CLASSIFICATION is closed; old BLOCK report is historical, not current.

Command:

```
PYTHONPATH=<c904312 archive>/backend:<c904312 archive>/backend/tests:<reviewer directory> \
  python -m pytest reviewer/full_semester/test_xlsx_content_length_closure.py \
  -q -o addopts='' --tb=short
```

## Final regression on c904312

- XLSX API + existing XLSX reader: **174 passed**.
- Relevant Curriculum + integration orchestrator + Runtime/API: **1208 passed**.
- Full backend: **2889 passed / 2 skipped**, no failed tests.
- Frontend tests: **134 passed**, 9 files.
- Frontend typecheck: PASS.
- Frontend build: PASS.
- compileall backend/app, backend/tests and tools: PASS.
- node --check frontend/verify_all_scenarios.mjs: PASS.
- Combined PR diff whitespace check: PASS.

Commands:

```
python -m pytest tests/test_completed_courses_import_api.py \
  tests/test_curriculum_xlsx_reader.py -q -o addopts='' --tb=short
python -m pytest tests/test_curriculum*.py tests/test_integration_orchestrator.py \
  tests/test_planning_runtime.py tests/test_real_plan_api.py -q -o addopts='' --tb=short
python -m pytest -q -o addopts='' --tb=short
npm test
npm run typecheck
npm run build
python -m compileall -q backend/app backend/tests tools
node --check frontend/verify_all_scenarios.mjs
```

Two pre-existing platform-sensitive Curriculum reader files are unchanged from merged main
and included in this run. Neither known Windows-only failure reproduced on this Linux host;
no new skips/xfails introduced by the fix. Existing Starlette/httpx deprecation warning only.
Frontend run is requested final regression, not reopening frozen #46 review.

## Verdict

PR #47: PASS
cross-stack: PASS
merge readiness: ready

Recommended merge order: #46 -> #47.

Auth and Real X-Data-Source remain the already accepted deployment/product hardening items;
this review does not upgrade the local/synthetic Demo to a public deployment or Real E2E.
No production edits, no school access, no merge. Reviewer only tests/docs saved.
