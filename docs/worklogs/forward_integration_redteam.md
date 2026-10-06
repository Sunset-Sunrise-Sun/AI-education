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
