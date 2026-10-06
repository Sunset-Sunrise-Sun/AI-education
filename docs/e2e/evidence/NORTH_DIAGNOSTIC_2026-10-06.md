# North Campus diagnostic evidence — 2026-10-06

## Status

- Semester: `2026-1`
- Campus: North
- `openingSchoolNumber`: `5062202`
- Diagnostic mode: bounded manual/browser-session probe
- Result: **North remains suspended**
- Real full-semester acceptance: **not available**
- Formal Real E2E: **LEVEL 0**

## Safe observations

### O1 — baseline

This request did **not** include `openingSchoolNumber`.

- pageNo: `1`
- pageSize: `200`
- HTTP: `200`
- response code: `200`
- reported total: `6875`
- returned rows: `200`

### O2 — North filtered request

- openingSchoolNumber: `5062202`
- pageNo: `2`
- pageSize: `200`
- HTTP: `600`
- response code: `50015000`
- reported total: unavailable
- returned rows: `0`

### O3 — same-session repeat

The same North page was retried after at least 30 seconds.

- openingSchoolNumber: `5062202`
- pageNo: `2`
- pageSize: `200`
- HTTP: `600`
- response code: `50015000`

## Decision

The same filtered North page reproducibly returned HTTP 600 / application code 50015000 in the same authorized session. This satisfies the pre-declared diagnostic stop condition.

Therefore:

- stop further North probing;
- keep North **suspended**;
- do not perform a five-shard production capture yet;
- do not produce or claim a real full-semester acceptance;
- do not claim LEVEL2 / LEVEL3 Real E2E.

This observation is **not** evidence of rate limiting. No HTTP 429 or other explicit rate-limit signal was observed. The correct description is an abnormal response on North filtered pagination; root cause remains unknown.

## Important diagnostic note

The test script skipped North page 1 because it treated the baseline page-1 request as equivalent. They are not equivalent:

- baseline: no `openingSchoolNumber`
- North page 1: `openingSchoolNumber=5062202`

No additional request should be made merely to fill this gap, because the repeated North page-2 failure already triggered the frozen stop condition.

## Baseline interpretation

The observed baseline total was `6875`. This must not be described as in-window total drift by itself because this diagnostic did not run a full `baseline_before -> capture -> baseline_after` acceptance window.

Historical totals are not authoritative for current acceptance. Future real acceptance must use current validated baseline-before/baseline-after evidence.

## Privacy / security

This evidence intentionally excludes:

- cookies;
- Set-Cookie;
- Authorization headers;
- tokens or credentials;
- full raw response bodies;
- student personal information.

Only non-sensitive diagnostic metadata is retained.


## Fresh-session follow-up

A later fresh authorized session closed the remaining page-1 evidence gap.

### North page 1

- openingSchoolNumber: `5062202`
- pageNo: `1`
- pageSize: `200`
- HTTP: `200`
- response code: `200`
- reported total: `405`

### North page 2

- openingSchoolNumber: `5062202`
- pageNo: `2`
- pageSize: `200`
- HTTP: `600`
- response code: `50015000`
- reported total: unavailable
- message: `系统异常`

The diagnostic stopped immediately after page 2 failed.

## Updated conclusion

North page 1 is reachable and reports a current filtered total of `405`, while page 2 fails immediately with HTTP 600 / application code 50015000 in a fresh authorized session.

The supported classification is therefore:

- North first page: available;
- North filtered pagination beyond the first page: blocked at `pageNo=2` for `pageSize=200`;
- root cause: unknown;
- this is **not** classified as rate limiting;
- North remains **suspended**;
- no real full-semester acceptance can be produced from the current five-shard path;
- Formal Real E2E remains **LEVEL 0**.

No further North probing is required to establish this operational classification.
