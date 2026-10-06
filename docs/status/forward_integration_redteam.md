# Forward Integration Red-Team status

2026-10-06：审查 main `1cd08e0` 与 Builder full-semester acceptance `c01b7c9`。
独立 reviewer branch；没有 production / contract / DB implementation 修改。
完整证据与 acceptance matrices：`reviewer/full_semester/REVIEW.md`。

- BLOCK B1：hash 与 parsed payload 可不同源，A/B/A synthetic probe 已复现。
- BLOCK B2：artifact scope 未与独立受批准 campus binding 核对，swapped artifacts probe 已复现。
- successor 必须隔离 exact accepted set，semester-wide loader 不可直接用于 runtime。
- main backend 2489 passed / 2 skipped；Builder focused suite 88 passed；reviewer diagnostic probes 5 passed。
- frontend build passed，113 tests passed；本地 backend / mock / frontend 请求通过，unconfigured plan 正确 503。
- Formal Real E2E LEVEL0，North operationally suspended；successor synthetic LEVEL1 E2E 是设计，未执行。
- GitHub PR API Forbidden；未发表 PR 评论，未 merge main。

收尾追加 focused review：Store-backed Builder `13c5556e02c845429c3ff2320a7e07a51e07630f`。
102 existing tests passed；5 additional probes passed（含 4 风险复现）。
PASS：排除 stale campus extras、后续 provenance overwrite 导致缺行时拒绝。
BLOCK B3：same-count identity / valid payload mutation 被接受。
BLOCK B4：构造后删除 acceptance record，旧 Provider 仍返回 rows。
总 reviewer probes 10 passed，含诊断复现，不代表正式 gate PASS。

环境使用 `/workspace/.venvs/ai-education`，额外 synthetic document 依赖 python-docx / openpyxl；
前端使用 workspace npm cache。安装和启动说明已保存为云环境 draft，未发布新环境。

## Blocker Closure / immutable identity audit（更新）

审查最新 stack：acceptance fix 831c0e3、Provider fix cb585c1、runtime 3e0a7c3、E2E d097f51。
详细新结论：`reviewer/full_semester/CLOSURE_REVIEW.md`（优先于上方旧 HEAD 结论）。

- B1 exact bytes PASS；B2 campus inventory/record binding PASS。
- B3 direct SQL 内容篡改会拒绝，但 same SHA + same count/identities + changed payload 的
  supported reimport 仍能刷新 expected digest/membership：IMMUTABLE IDENTITY **BLOCK**。
- B4 sequential deletion next-read PASS；一致读事务未显式 BEGIN，另有 concurrent snapshot BLOCK。
- 最新 focused 241 passed；targeted 483 passed / 2 skipped；独立 closure probes 42 passed，
  其中 3 个 passing diagnostics 复现剩余 BLOCK，不代表 readiness PASS。
- reviewer-only immutable strict gates：3 failed（预期旧版本失败，无 xfail mask，不进默认 suite）。
  包括 reject changed-content reimport、禁止 semantic UPDATE、stored canonical manifest hash binding。
- 新 HEAD 搜索中：Provider 远端仍 cb585c1；用户要求 immutable identity PASS 前不继续新版本
  runtime/E2E 审查。此前旧 HEAD 证据仅供诊断。
- GitHub API Forbidden，未留评论；exact BLOCK comment text 已写入 CLOSURE_REVIEW.md。
- 没有 merge、production/Schema/protocol 改动，Formal Real E2E LEVEL0。

## Focused Architecture Review — refreshed targets

Provider ef910e3fd3c68b10d9d9ed42a39698f5e8a21f36；Runtime a67ba96；E2E f8675e2 已刷新。
最新报告：`reviewer/full_semester/FOCUSED_PROVIDER_REVIEW.md`，优先于旧 cb585c1 结论。

- R-CONTENT PASS：18 changed-payload import attacks rejected atomically；manifest SHA 重算、
  exact-content idempotency/no semantic UPDATE、5 stored-manifest tamper cases passed。
- R-SNAPSHOT BLOCK：双连接 WAL + Event barrier 的 acceptance delete / row replace /
  membership mutation 三例均记录 authoritative SELECT in_transaction=False；无显式 BEGIN。
  观察到 epoch A 或 typed refusal，没有声称这些 probes 已返回 mixed payload。
- 独立 probes 24 passed / 3 failed；existing Store/Provider suite 163 passed。
- Provider BLOCK；按用户 phase 顺序，本轮新 Runtime/E2E 未执行，dependency gate BLOCK。
- 不接受旧 suite PASS 替代本次 transaction gate；不 merge、不改 Builder code。

## Latest closure — ec8ab6f / eb135a8 / 6fa155c

新结论优先于以上旧HEAD记录：`reviewer/full_semester/LATEST_CLOSURE_REVIEW.md`。
- Provider ec8ab6f：R-CONTENT PASS、R-SNAPSHOT PASS、STORE TRUST CHAIN / PROVIDER GATE PASS。
  独立27 passed；snapshot8 passed；Store/Provider163 passed。WAL三变体Reader均完整epochA，
  authoritative SELECT/digest验证全程active，最后ROLLBACK。
- Runtime eb135a8：BLOCK R-ERROR-CLASSIFICATION。所有数据门禁503/stale隔离通过，
  但construction无关ValueError被宽泛catch转503，期望500。独立14passed/1failed；targeted65passed。
- E2E6fa155c：已fetch，因Runtime未PASS本轮未执行。Full backend/compileall条件不成立未运行。
- Provider branch可进入其Gate PR review；Runtime/E2E没有完整PASS。未merge、未改production。

## Final Runtime/E2E closure — b0931d7 / 8fc18b9

本节优先于以上历史 BLOCK：`reviewer/full_semester/RUNTIME_E2E_FINAL_CLOSURE.md`。
- Provider ec8ab6f frozen PASS；Runtime 未改 Course Data，不复审。
- RUNTIME GATE PASS：独立HTTP51 passed，六类无关错误跨六边界均500；领域/配置失败503。
- SYNTHETIC E2E GATE PASS：独立10 passed；传播版本重跑Runtime51 passed。
  精确课表/Preference传递、UNKNOWN/manual_confirmation保留、stale隔离、篡改503。
- 指定targeted1054 passed；full backend2823 passed/2 skipped；compileall通过。
- Runtime/E2E可进入formal PR review；Gate E/F/G可恢复各自准备与验收，不代表它们PASS。
- LEVEL1 synthetic wiring only；Formal Real E2E仍LEVEL0。未merge、未改production、未访问学校。

## PR-level final review — Draft #42/#43/#44/#45

`reviewer/full_semester/PR_STACK_FINAL_REVIEW.md`：四PR Architecture PASS；cross-stack PASS。
GitHub公开页面base/head/Draft与指定stack一致，Git pull refs+ancestry确认；API Forbidden。
每层diff边界通过，#43显式typed503 handler属已文档化Provider适配，无隐藏装配依赖。
#42 full2628/2skip；#43 full2721/2skip；#44 runtime/API98；top targeted1103、full2823/2skip。
compileall与diff检查通过。不重复旧HEAD sweep。merge readiness ready，顺序42→43→44→45。
四份评论稿独立保存pr_comments/；发布尝试Forbidden，未发表。未merge、未改production。

## Gate E/F/G PR-level review — #46 / #47

Report: `reviewer/full_semester/GATE_E_F_G_PR_REVIEW.md`。
GitHub Draft/base/head核实：#46 19970db base main；#47 0727902 base #46；main已merge42–45。
- #46 Architecture PASS：frontend134 passed，typecheck/build/nodecheck PASS。
- #47 BLOCK F-LENGTH-CLASSIFICATION：API Content-Length .isdigit/int不匹配；4301位ASCII数字
  和superscript digit在ASGI应用返回500，文档要求413/411。Uvicorn/h11先拒400，未发现bypass。
- 独立XLSX24pass/2fail；existing XLSX140pass；Curriculum/orchestrator/runtime/API1208pass。
- Cross-stack BLOCK；full backend/compileall按用户条件等修复后运行；不merge不改production。
- Auth与Real X-Data-Source仅non-blocking hardening；Formal Real E2E仍LEVEL0。

## PR #47 focused closure — c904312

Latest report `reviewer/full_semester/PR47_CONTENT_LENGTH_CLOSURE.md` supersedes prior47BLOCK。
PR46仍frozen PASS，未复审。PR47新HEAD c904312只复查Content-Length修复。
独立30passed：missing/empty/Unicode/空白/符号格式411；max+1/万位ASCII413且不进int；
真实8MiB workbook200；streamoverflow413；mismatch/invalid400；直接ASGI无transport依赖。
Final XLSX174、Curriculum/integration/runtime1208、fullbackend2889/2skip、frontend134passed；
typecheck/build/compileall/nodecheck PASS。PR47/cross-stack PASS，ready，顺序46→47，未merge。

## PR48 Real E2E readiness — 8ea5c84

Report `reviewer/full_semester/PR48_REAL_READINESS_REVIEW.md`。main67c8585、PR48base/head核实。
PR48BLOCK：env output可在force下覆盖已验证SQLite仍返回ready；默认env覆盖存在TOCTOU；
runbook缺sharded赋值；LEVEL2机械证据不足证明real来源，需明确digest绑定真实交接证明。
Synthetic preflightPASS（5shards/15rows/LEVEL1）；North保守计划PASS但operational仍suspended。
Reviewer13pass/3fail；targeted609pass；full2913/2skip；frontend134/typecheck/build/compile/nodePASS。
READY FOR USER REAL CAPTURE=NO；merge not ready；未merge、不改production、不访问学校。

## PR48 closure — 87d9d6e

Single-line DeepSeek builder / independent reviewer. GitHub base/head and pull ref verified.
PR48 still BLOCK: --overwrite-env destination alias overwrites verified SQLite and returns
ready; handoff with approved_by/approved_at null nevertheless sets level2_eligible=true.
Curriculum real-source digest/version mandatory evidence remains missing. Report:
reviewer/full_semester/PR48_CLOSURE_87d9d6e.md. Default publication race and browser Console
capture/export binding now PASS. Reviewer15PASS/2strictFAIL; readiness47; targeted541;
full backend2936PASS/2skip; frontend134/typecheck/build/compileall/nodecheck PASS.
LEVEL1 preflight PASS; no Real LEVEL2/3 claim. North remains suspended, merge not ready.

## PR48 final closure — 2e76e04

Fetched PR48 base/head/pull ref exact2e76e044744a572d815f7fcc43331c8a0f77dd4a.
ENV READY and HANDOFF APPROVAL gates PASS. Curriculum/static matrix now implemented,
but after publication replacing case bytes or redirecting emitted case path still yields
ready/level2_eligible=true for digest-mismatched, actual runtime-loadable input.
CURRICULUM PROVENANCE / COMBINED LEVEL2 / PR48 BLOCK. Report:
reviewer/full_semester/PR48_FINAL_2e76e04.md. Independent37PASS/2strictFAIL;
targeted565PASS; fullbackend2960PASS/2skip; frontend134/type/build/compile/nodePASS.
No frozen production/public Schema diff. North suspended; user captureNO; merge not ready.
