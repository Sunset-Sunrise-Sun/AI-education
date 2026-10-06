# Forward Integration Red-Team worklog

## 2026-10-06

读取 AGENTS、Course Data / Integration status、接口、public model、Store、capture、merge、
collector、Planner、runtime/API；main baseline 与用户指定 SHA 一致。
发现 Builder branch `c01b7c9` 后 focused review，仅在 /tmp git archive 上运行其 tests，
不建立 worktree、不修改 Builder code。PR #39 仅作为反例阅读。
新增 3 main Store diagnostic probes、2 Builder diagnostic probes，全部成功复现目标风险；
没有 expected-to-fail tests 混入 main default suite。REVIEW.md 含全部 20 adversarial cases，
manifest、stale-row、Provider recommendation、runtime matrix 与 synthetic E2E matrix。

环境安装：Python 3.12 venv，requirements + python-docx/openpyxl；npm ci 保持 lockfile。
首次 pytest collection 缺 docx，补齐 optional parser test deps 后 main 2489 passed / 2 skipped。
首次 npm 默认缓存不可写，workspace cache 重试通过。frontend build + 113 tests passed。
Builder 88 tests passed；diagnostic 5 passed；服务 GET health/mock/frontend/entry 200，
POST production plan 503 real_pipeline_not_configured。没有真实学校请求、数据、凭据处理。
GitHub Git read 正常；gh PR API 返回 Forbidden，无评论权限可用，不索取 token。
安装/startup draft 保存不等于执行、应用、发布或新任务 restoration 验证。

首次 push 收尾发现 Store Provider branch `13c5556`，继续审查，不修改其实现。
独立 archive 下 102 Provider/Store existing tests passed；新增 5 probes 验证 stale 隔离
并复现同数量 identity substitution、valid payload mutation、假 full 声明和 cached record deletion。
REVIEW.md 追加 B3/B4 finding、复现与最小修复方向。总 probes 10 passed。

## Blocker Closure + Runtime Readiness audit

发现新 Builder stack 831c0e3 / cb585c1 / 3e0a7c3 / d097f51。隔离 archive 读取，
focused 241 passed，targeted 483 passed / 2 skipped；没有重跑 full backend/frontend Merge Gate。
独立 42 closure probes验证 exact-byte/campus binding、continuous next-read refusal、
真实 runtime 503 与 Planner exact payload/pass-through；3 diagnostics 复现 same-SHA rebind、
actual API 200 after rebind、SELECT 没有 consistent transaction。
报告 CLOSURE_REVIEW.md 给出 exact manual PR BLOCK comments；gh GraphQL Forbidden，不请求凭据。

用户进一步明确 immutable identity-first 顺序：新增 reviewer-only strict gates
test_immutable_identity_gate.py。旧实现 3 failed，已知且明确 expected-to-fail-until-fix；
不加 xfail，不进入 main-ready/default suite。搜索 Provider 新 HEAD，目前仍 cb585c1。
要求 same-count changed-content 第二次 import 原子拒绝，旧 Provider 返回 A；stored canonical
manifest SHA 等于 configured acceptance SHA；semantic acceptance/member 禁止 UPDATE。
此 gate 通过后才继续新 HEAD runtime/E2E，不接受 Builder 自称修复。

## Focused Architecture Reviewer role reset

fetch --all --prune + wildcard refresh，确认 ef910e3 / a67ba96 / f8675e2；runtime/E2E 远端
force-update已正确刷新。Phase 1 仅在 Provider ef910e3 archive 执行。
独立 test_focused_provider_gate.py：24 passed / 3 failed；18同SHA/same count/same identity
changed payload attacks全部原子拒绝，stored manifestSHA/幂等/禁止语义UPDATE通过，R-CONTENT PASS。
实际 WAL 双连接线程+Event在acceptance read后暂停Reader，Writer commits三个变体；
authoritative SELECT全部in_transaction=False，R-SNAPSHOT BLOCK。Reader结果为A或拒绝，
没有混合payload泄露的夸大声明。Existing Store/Provider 163 passed。
按用户gate依赖未执行新版Runtime/E2E，不跑full backend/frontend。精确BLOCK评论文本与
修复要求保存在FOCUSED_PROVIDER_REVIEW.md。没有production/Schema/protocol/Builder code修改或merge。

## Latest HEAD closure update

fetch并确认ec8ab6f/eb135a8/6fa155c及acceptance831c0e3。按阶段顺序，独立Provider27passed；
adapted instrumentation跟随新的_open_read_snapshot，会员查询前Event暂停，真实WAL writer
commit acceptance deletion/row replacement/member mutation。Reader三例均A，4个authoritative
SELECT以及所有manifest/payload/set验证txn active，结束ROLLBACK。Snapshot suite8passed，
Store/Provider163passed：R-CONTENT/R-SNAPSHOT/PROVIDER GATE PASS。

再进入Runtime eb135a8；独立14passed/1failed，API targeted65passed。负例数据门禁503和
stale非成员不进实际Planner均通过；无关construction ValueError被factory广泛catch吞为503，
违反用户内部程序错误非503要求。R-ERROR-CLASSIFICATION BLOCK，exact reproduction/comment
保存LATEST_CLOSURE_REVIEW.md。未进入Phase3新E2E；不运行allGatesPASS前提下的finalfullbackend/
compileall/前端回归。只有reviewer docs/tests修改，无production或merge。
