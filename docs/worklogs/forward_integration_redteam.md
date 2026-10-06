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

## 2026-10-06 Runtime/Synthetic final closure

刷新远端并独立审查Runtime b0931d7 / Synthetic8fc18b9。Provider ec8ab6f冻结PASS，
Course Data diff为空，因此不复审。Reviewer扩展真实HTTP异常注入矩阵，六类内部错误
在CourseData/Curriculum/Planner构造和Provider/Planner/Orchestrator请求六边界均500；
预期领域/配置失败和构造后撤销503。Runtime51 passed，旧ValueError分类BLOCK关闭。
独立Synthetic10 passed，完整A/B同SHA攻击拒绝B，随后HTTP仍为A；直接篡改503，
stale campus非member不入Planner，课表/Preference exact，UNKNOWN/manual_confirmation保留。
初始独立断言错误把SelectedClass当CourseOffering、复制stale保留accepted provenance，
按公共response形状及campus provenance修正fixture后通过，没有修改production。
传播版本Runtime+E2E61 passed。指定targeted1054 passed；full backend2823 passed/2 skipped；
compileall exit0。报告RUNTIME_E2E_FINAL_CLOSURE.md记录命令、HEAD、局限和Gate E/F/G边界。
仅tests/docs更改，未merge、未访问学校，Formal Real E2E仍LEVEL0。

## 2026-10-06 PR-level final architecture review

按上传的新任务只审Draft42→43→44→45各层最终diff。API reads Forbidden，但public PR
HTML可读，独立解析baseBranch/headBranch/headSha+Draft并与Git pull/head refs交叉确认。
每层ancestry正确、公共Schema/Protocol无diff、无真实artifact新增，后层无隐藏前层覆盖。
#43 main.py handler明确记录并只做Provider typed503适配，不是隐性runtime装配。
#42/#43逐层完整backend2628/2721 passed各2skip，#44 runtime/API98 passed；各层compileall。
Top指定CourseData/Provider/snapshot/acceptanceCLI/runtime/API/synthetic1103 passed，
full backend2823 passed/2skip，compileall和diffcheck通过。四PR及cross-stack PASS，
ready，推荐merge order42→43→44→45。尝试gh pr comment42 Forbidden；四独立comment稿保存。
没有merge/production编辑/学校访问；Formal Real E2E仍LEVEL0。

## 2026-10-06 Gate E/F/G final PR-level review

刷新Git全部分支，GitHub公开页面metadata与refs/pull确认Draft46/47 base/head精确匹配。
main faff309已合并42–45；本轮只审46/47增量，不重做旧backend threat sweep。
Frontend134pass、typecheck/build/nodecheck通过，#46PASS。#47API/ingest只新增兼容route，
Schema/ports/runtime/store/matching无diff，既有XLSX140pass、Curriculum/integration/runtime1208pass。
独立XLSX26例：24pass/2fail（超长十进制CL与非ASCII digit应用HTTP500分类错误）。
补查真实localhost Uvicorn/h11两例都先400，明确不声称上传绕过/公网500漏洞；BLOCK限定
ASGI应用自身文档化输入边界。最小修复ASCII校验+转换前有限大小比较，不改业务异常边界。
测试fixture参数初写sheet_name，按fixture真实接口selected_sheet_name修正；七个假失败消除，
剩余两个确认实现缺陷，无xfail。报告与strict reviewer test已保存；#47/cross-stackBLOCK。
按用户条件未启动最终fullbackend/compileall；Windows敏感两个reader文件相对main无diff，
本Linux targeted包含它们并全通过。无secret/artifact新增，无merge/production改动/学校访问。

## 2026-10-06 PR47 Content-Length final closure

Fetch确认GitHubPR47 base#46/head c904312。严格按用户限缩范围，不重审冻结PR46。
Independent30探针通过：实际ASGI所有非法CL411，万位decimal/max+1为413、巨型不调用int，
max恰好8MiB真实工作簿成功200，stream二块超限413且不读三块，mismatch/invalid400，隐私安全。
Parser AST明确isascii/isdigit/no strip。Schema/Provider/runtime/store/plan无diff。
指定finalreg全部完成：XLSX174，Curriculum/orchestrator/runtime1208，full2889/2skip，
frontend134，typecheck/build/compileall/nodecheck通过；Windows敏感reader测试文件未变，
本Linux没有已知两failure。PR47/cross-stack PASS ready，推荐46→47，未merge不改production。

## 2026-10-06 PR48 final readiness architecture review

Fetch+GitHubpublicmetadata确认main67c8585/PR48head8ea5c84/base main；diff限tools/tests/docs。
按用户不重审merged42–47。独立指定preflight通过5synthetic/15rows/fullaccept/membership/
Provider/env/LEVEL1链，零学校访问。Reviewer16例13pass3fail：env-out=sqlite加force
数据库被文本覆盖且CLIready exit0；no-force检查后文件竞态可被覆盖；实际docJS导出
因sharded未赋值ReferenceError（offline stub只替换collector网络）。另真实API合成证据
witness：Case real字段/runtimeReady/200/noMockheader/非空selected子集均true，不能独立证明
actualrealorigin，新LEVEL2协议需明确受控来源交接记录与case/五rawdigest绑定。报告给最小fix。
全部指定回归：targeted609、fullbackend2913/2skip、frontend134；typecheck/build/compileall/
collector+scenario nodecheckPASS。North计划不称rate-limit、有bounded manual观察/stop但仍suspended。
PR48/orchestratorsafety/docs BLOCK，synthetic PASS，NorthplanPASS，usercaptureNO/merge notready。
仅reviewer tests/docs，无production编辑/merge/realnetwork/credentials。

## 2026-10-06 — PR48 focused closure 87d9d6e

Fetched/refreshed all heads and verified PR48 base main/head87d9d6e against GitHub/public
pull ref. Single-agent review, synthetic-only local archive, production diff unchanged.
Adapted original alias probe to --overwrite-env: actual CLI exit0/ready then SQLite SELECT
DatabaseError. Publication-boundary competitor preserved: race closed. Browser Console
sloppy-script capture/export runs: binding closed; strict ESM portability nonblocking.
Actual generated handoff with only state changed approved and null approver/time gives
level2_eligible=true. Curriculum input source digest/version still absent from mandatory gate.
Recorded report and strict closure probes (15pass/2fail), no skip/xfail. Full backend2936/2skip,
targeted541, readiness47, frontend134/type/build, compileall and nodecheck pass.
PR48BLOCK/user full captureNO/merge notready; no production edits/merge/school access.
