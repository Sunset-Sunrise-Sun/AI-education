# Second-pass Integration Audit（Gate G）

> 审计对象（stack，按顺序）：
> `main @ 1cd08e0` + **PR #42** `831c0e3` + **PR #43** `ec8ab6f` + **PR #44** `b0931d7`
> + **PR #45** `8fc18b9` + **Gate E** `19970db` + **Gate F** `58e0d29`（+ 路由白名单 `33812dd`）。
> ⛔ 未 merge main；⛔ 未改 public Schema / frozen Provider contract；⛔ 无真实学生数据。
> 全部结论来自**可重跑的命令**（见 §21），⛔ 不是叙述。

## 1. public Schema diff

```text
git diff --stat main -- schemas        → 空
```

✅ **零改动**。Gate F 的新接口响应模型定义在 `backend/app/api/completed_courses.py` 内部，
⛔ 未新增 / 未修改 `/schemas/*.schema.json`（新增公共 Schema 属接口面变更，本 Gate 未擅自扩）。

## 2. frozen Provider contract diff

```text
git diff --stat main -- backend/app/integration/ports.py docs/interfaces/integration.md backend/app/models/contracts.py
→ 空
```

✅ `CourseDataProvider` / `CurriculumProvider` / `PlannerProvider` 三个 Protocol 与
`PlanningOrchestrator` 签名**未变**；`StoreBackedCourseDataProvider` 仍只是**结构化满足**、⛔ 不继承。

## 3. accidental Mock fallback

- 生产链路（`planning_runtime.py` / `api/plan.py` / Gate F 适配器）里对 Mock 的引用**只有否定式文档陈述**；
- `main.py` 对 `mock_service` 的引用仅用于 **Mock 通道自身的错误处理**与
  `X-Data-Source: mock` 标记中间件（仅对 `/api/v1/mock/*` 生效，有既有测试锁定）；
- Gate F 失败路径⛔ 不回退任何演示数据（`docs/data/XLSX_COMPLETED_COURSES_IMPORT.md` §2/§6）。

✅ 无意外 Mock fallback。

## 4. stale Course Data semantics

- `load_course_offerings_for_acceptance()` 在代码与文档中均明确标注为**非权威诊断查询**
  （`store.py` 函数 docstring + `docs/status/course_data.md`）；
- 权威路径只有 `load_accepted_offerings()`（R-SNAPSHOT 单一读快照），
  `StoreBackedCourseDataProvider` ⛔ 不缓存 rows / metadata；
- 文档中"两个平面 / membership / immutable acceptance"表述与实现一致（B3/B4/B5 记录齐全）。

✅ 无残留旧语义。

## 5. frontend business-rule leakage

```text
grep frontend/src: hasConflict|detectConflict|computeConflict|isFeasible|solveSchedule|repairPlan|pathRepair|priorityScore|recognizeCredit
→ 0 命中（注释里的禁令除外）
```

✅ 前端只做展示与接线（Gate E 的静态守卫已把该结论固化为测试）。

## 6. duplicate validation logic

- Gate F 适配器**不**重复实现 worksheet 布局 / 表头 / 单元格类型校验（无 `_HEADERS`、无列名校验）；
  只做字节长度 / 媒体类型 / 空文件 / 条数上限，然后调用既有 `load_completed_courses_xlsx`；
- 归一化仍由既有 `normalize_completed_courses` 完成（适配器只**投影**已归一化字段）；
- 唯一新增的 HTTP 响应模型不参与业务判定。

✅ 无重复校验。

## 7. privacy

- Gate F 错误响应经测试断言⛔ 不含：单元格取值、原生 XML、`Traceback`、本地路径、`.xlsx` 文件名、临时文件名；
- 成功响应⛔ 不回传 `备注` 自由文本（只回传 `notes_present_count`）；
- 新模块⛔ 无 `print` / `logging`（⛔ 不打整份成绩单 / 课程表）；
- 既有 Course Data 侧（`normalization.py` 等）保持"不回显 raw token"的既有约束。

✅ 隐私边界与既有实践一致。

## 8. committed real artifacts

```text
git ls-files | grep -E '\.(xlsx|xls|xlsm|docx|doc|pdf|csv|zip|png|jpg)$'   → 空
```

✅ 仓库内**没有任何** Office / 二进制 / 真实材料文件（Gate F 的 fixture 全部由代码生成）。

## 9. credentials / secrets

```text
grep -E 'ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN .*PRIVATE KEY|password\s*=\s*["'"'"']'  → 0 命中
git ls-files | grep -E '(^|/)\.env|credential|secret|\.pem$|\.key$'          → 只有 .env.example
```

✅ 无凭据 / 密钥入库。

## 10. raw school payload

- 仓库内无 raw 教务响应、无完整课程表、无成绩 / GPA / 姓名 / 学号；
- 真实 artifact 相关文档继续标注"外部访问者无法独立复核""原始材料不入库"；
- Gate F ⛔ 不引入任何真实材料，只新增 synthetic 生成器。

✅ 无 raw payload。

## 11. status / docs consistency

- 修正了**过时表述**：`docs/status/agent_frontend.md` 中
  "`POST /api/v1/plan` 由并行开发中的 `feature/real-plan-api` 提供、当前 main 上并不存在"
  → 改为"✅ 已实现；未装配时返回 503，属当前正确状态"；
- `frontend/src/config.ts` / `SubmissionActions.vue` 的展示文案同步修正；
- Gate F 前端未接线的边界写进 `docs/status/agent_frontend.md`（避免"后端能力 = 前端已接线"的误读）；
- 历史 worklog 中仍保留 `feature/real-plan-api` 字样（**append-only 历史记录**，非当前状态陈述）。

⚠️ 保留项：历史 worklog 不改写（append-only 原则）。

## 12. LEVEL0 / LEVEL1 / LEVEL2 / LEVEL3 terminology

- 全仓库只声明 **LEVEL1 synthetic production wiring capability**（Gate D）；
- 所有相关文档都显式写了 "⛔ 不声明 Real LEVEL2 / LEVEL3"；
- formal Real E2E 继续 **LEVEL0**（无真实 artifact / 未真实登录 / North suspended）。

✅ 术语一致，无越级声明。

## 13. tests non-vacuity

- 新增测试全部断言**真实 HTTP 状态码 / 真实返回值 / 真实库状态**（⛔ 不断言内部 reason code 就算通过）；
- Gate F：`test_formula_cells_are_rejected_and_never_evaluated` 同时断言"拒绝"与"标记不回显"；
  `test_temp_file_is_removed_after_success_and_failure` 断言临时文件**真的不存在**；
  `test_imported_records_drive_the_existing_curriculum_pipeline` 与原生 `records` **逐条比对**；
- 新增测试中⛔ 无 `skip` / `xfail` / `todo`；
- 上一轮已做的变异探针（R-SNAPSHOT 2 killed / 1 可证等价；R-EXC 5 killed）继续有效。

✅ 非空泛。

## 14. dead branches / obsolete runtime docs

- 当前 stack **线性**且已全部 push：`831c0e3 → ec8ab6f → b0931d7 → 8fc18b9 → 19970db → 58e0d29 → 33812dd`；
- 历史分支（`feature/case-a-runtime-wiring`（PR #39）、`feature/frontend-real-e2e-prep`、
  `feature/store-backed-course-data-provider`、`feature/full-semester-course-data-acceptance` 等）
  ⛔ 未删除、⛔ 未 merge —— 它们是被审计基线或历史产物；
- `docs/data/RUNTIME_AND_FRONTEND_COMPATIBILITY_REVIEW.md`（Phase 6 "PR #39 需要小改"）
  已在文内标注 PR #39 = FROZEN / DO NOT MERGE，与当前 successor 实现不冲突。

✅ 无"能跑到生产"的死代码路径；⛔ 未擅自删除他人分支。

## 15. PR #39 superseded 表述

```text
grep 'PR #39' docs → 59 处，全部为 "FROZEN / DO NOT MERGE / superseded" 语境的记录
```

✅ `docs/data/CASE_A_RUNTIME_WIRING.md` 首节即给出 **结论：PR #39 被取代（superseded），⛔ 不合并**。

## 16. old capture path 是否还能被 production runtime 意外调用

```text
grep planning_runtime.py: CapturedPages|SnapshotCourseDataProvider|load_capture_bundle
→ 仅 docstring 提及（"单 bundle 装载模型已冻结停用"）
```

- runtime 只按**五个显式环境变量**装配 `CurriculumCaseProvider + StoreBackedCourseDataProvider
  + RestrictedPlannerProvider`；⛔ 无 campus / 单 bundle / 内存快照分支；
- 既有结构测试锁定 runtime 模块⛔ 不 import Mock 通道 / 快照 Provider / 网络库。

✅ 旧 capture 路径**不可**被 production runtime 调用。

## 17. XLSX 是否能绕过 Curriculum normalization

```text
grep 'ZipFile|openpyxl|load_workbook' backend/app → 只有既有 xlsx_reader.py（与 docx_reader.py）
```

- Gate F 的适配器**只**调用 `load_completed_courses_xlsx` → `normalize_completed_courses`；
- 无第二套 XLSX 解析、无"直接构造 CompletedCourse"的旁路（`case_records()` 只投影已归一化结果）；
- 回归测试断言"API 结果 == 既有路径版 reader 结果"。

✅ 无法绕过。

## 18. frontend 是否误称 preference fully enforced

- `PreferencePanel.vue`：本区块仅展示输入 + "以 PlanResult 输出为准"；
- Gate E 新增测试断言⛔ 不出现"已按偏好求解 / 偏好已全部满足 / 已作为硬约束执行"。

✅ 无误称。

## 19. unknown schedule 语义

- `labels.ts`：`schedule_unknown → "排课信息未知"`；`meetings=[] → "当前数据中无排课信息"`（单一常量）；
- 缺地点 → "当前数据中无地点信息"；
- 禁令词（无课 / 无需上课 / 异步课程 / 尚未排课 / 无冲突）在前端代码与测试中被显式排除。

✅ 语义保留。

## 20. error-classification 503 vs 500

- 显式领域失败 ⇒ 503 `real_pipeline_not_configured`
  （`_RuntimeSourceUnavailable` / `_RuntimeConfigurationInvalid` / `CurriculumNormalizationError` /
  `CourseDataStoreError`，含 `CourseDataAcceptanceError` 与 `ImmutableAcceptanceConflictError`）；
- 未预期内部错误 ⇒ **500**（⛔ 不捕获 `ValueError` / `RuntimeError` / `OSError` / `Exception`）；
  AST 断言 runtime 模块每个 `except` 目标都在显式白名单内；
- Gate F 的 4xx 分类**只**针对上传面（415/411/413/400 + 明确错误码），
  ⛔ 不影响 `/api/v1/plan` 的 503/500 语义。

✅ 分类一致，且不越过既有不变量。

## 21. Full regression（本轮实测）

```text
backend full suite                2853 passed / 2 failed / 2 skipped
  2 个失败 = 既有 Windows-only（test_curriculum_docx_reader.py 的 ZIP 成员名字面反斜杠、
  test_curriculum_json_reader.py 的 \x00 路径）；⛔ 未修、⛔ 未 skip、⛔ 未 xfail
Course Data targeted               936 passed
Curriculum targeted                498 passed (+2 上述既有失败)
Planner targeted                   342 passed
runtime / API                      137 passed
synthetic production E2E            20 passed
XLSX targeted                      140 passed（Gate F 新增 32 + 既有 reader 108）
frontend npm test                  134 passed（9 文件，含 readiness 21）
frontend typecheck (vue-tsc)       exit 0
frontend build (vite build)        exit 0
python -m compileall app tests     exit 0
node --check verify_all_scenarios  exit 0
secret scan                        0 命中
```

### 本轮 Gate G 发现的真实回归（已修）

```text
tests/test_integration_orchestrator.py::test_real_plan_endpoint_is_the_only_new_integration_api
  → 该守卫用**精确路由集合**断言 API 面；Gate F 新增路由触发了它（守卫按设计工作）。
  处理：逐条登记新路由并注明授权来源；**仍保持精确集合相等**（⛔ 未放宽为子集断言）。
  修复后：tests/test_integration_orchestrator.py 14 passed。
```

## 22. Gate G 结论

- ✅ 上述 20 项全部通过（其中 §11 保留"历史 worklog 不改写"、§14 保留"历史分支不删除"两项**有意保留项**）；
- ⛔ 未发现需要改动 PR #42–#45 冻结语义的问题；
- 唯一真实回归（§21）是**测试侧白名单**，已按设计修复并保持守卫强度；
- 剩余阻塞**只**与真实学校数据 / 授权有关（见最终报告第 8 项）。
