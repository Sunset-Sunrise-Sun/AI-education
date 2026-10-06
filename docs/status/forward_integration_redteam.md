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
