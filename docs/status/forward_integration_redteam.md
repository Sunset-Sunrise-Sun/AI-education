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
