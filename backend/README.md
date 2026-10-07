# 后端集成底座（组长模块 · Agent / Integration）— Phase 1

> **当前状态（不得夸大）**：
>
> - `/api/v1/mock/*` 是**永久 Mock 通道**，只有该路径携带 `X-Data-Source: mock`；
> - `/api/v1/plan` 是**真实入口**，由 `app/services/planning_runtime.py` 环境驱动装配；
>   **未装配时明确返回 `503 real_pipeline_not_configured`**，
>   ⛔ **绝不回退到 Mock**（有测试锁定 Integration 层不引用 `mock_service`）；
> - **Case A 私有演示通道**：`/api/v1/case-a-demo/*`
>   （`offerings` / `plan` / `repair/apply`），来源标记
>   `case-scoped:south+shenzhen`、`is_full_semester=false`；
>   它消费**真实的**南校园 + 深圳校区 scoped Course Data 与用户上传的成绩单，
>   ⛔ 不使用 Mock、⛔ 不接入 North 校区、⛔ 不抓取新数据。
>
> 本阶段的目标是先立好一块地基：一个能启动的 FastAPI 服务、
> 一套与 `/schemas/` 公共契约一致的校验层、一套可演示的 Mock 接口、一组自动测试。

---

## 1. 这一层负责什么，不负责什么

**负责**（集成层的本职）：

- 接收前端 / Agent 的请求；
- 用公共契约校验进入和离开的数据；
- 调用上游模块（**Mock 通道读 `mock_data/`；真实入口在装配后调用真实 Provider，未装配即 503**）；
- 统一返回格式与统一错误处理；
- 提供一个可被真实模块替换、而不必推翻前端的数据来源边界。

**不负责**（按 `/AGENTS.md` 第 5 节的模块边界）：

- 培养方案解析、已修课程结构化；
- 课程等价判定、课程正式认定；
- MakeupTask 的业务生成算法；
- 课程依赖、补修优先级；
- 时间冲突核心算法、CP-SAT / ILP 求解、Path Repair；
- 真实教务数据抓取。

> 换句话说：**别人算出来的结果，本层只负责"读、校验、转出去"。**
> 上面这些算法一旦出现在 `backend/` 里，就属于越界实现，应当被 Review 打回。
>
> ⚠️ **实际实现口径**：Planner 目前是**确定性启发式**（先修拓扑序 + 截止学期硬约束 +
> 建议学期偏好 + 每学期学分预算），⛔ **不是** CP-SAT / ILP 全局最优求解。

---

## 2. 目录结构

```text
backend/
  app/
    __init__.py              # 版本号 __version__
    main.py                  # 应用组装：路由挂载、/api/v1 前缀、启动自检、错误处理
    api/
      health.py              # GET /health（探针，根路径 + /api/v1 各挂一次）
      mock.py                # /api/v1/mock/* 五个接口
    models/
      contracts.py           # 与 /schemas/*.schema.json 一一对应的 Pydantic 模型
    services/
      mock_service.py        # 只做「读 mock_data/*.json + 契约校验」，真实模块接入的唯一替换点
  tests/
    conftest.py              # 测试客户端 + 读取真实 Schema / Mock 文件的夹具
    test_health.py
    test_contracts.py        # 行为测试 + 模型与公共 Schema 的防漂移比对
    test_mock_api.py
    test_mock_data_schema.py
  pyproject.toml             # pytest 配置
  requirements.txt
  README.md
```

---

## 3. 环境要求

- **实测通过的运行环境：Python 3.14（Windows）。**
  本项目**未在其他 Python 版本上验证过**，其他版本能否运行请自行确认后再写进文档。
- 运行服务只需要：`fastapi>=0.115`、`uvicorn[standard]>=0.30`。
- 运行测试额外需要：`pytest>=8.0`、`httpx>=0.27`、`jsonschema>=4.20`。

依赖版本刻意不锁补丁号（见 `requirements.txt` 顶部说明），MVP 阶段优先保证其他成员装得上。

---

## 4. 安装依赖

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

> 如果你不想用虚拟环境，也可以直接 `python -m pip install -r requirements.txt`，
> 但那会污染全局环境，多人协作时不推荐。

---

## 5. 启动服务

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

启动后可访问：

| 地址 | 用途 |
|---|---|
| http://127.0.0.1:8000/health | 服务存活探针 |
| http://127.0.0.1:8000/docs | 交互式 API 文档（可直接点按钮调接口） |
| http://127.0.0.1:8000/openapi.json | 机器可读的接口描述 |

**启动时会自动做一次数据自检**：把 `mock_data/` 下四个 JSON 全部读一遍并按公共契约校验。
如果数据坏了，进程会直接启动失败，而不是带着坏数据对外提供服务。报错示例：

```text
启动自检失败：Mock 数据不符合公共契约。Mock 数据不符合公共契约：...\mock_data\course_offerings.json -> CourseOffering[]。校验错误：[...]
```

这条报错会明确写出**哪个文件、哪个字段**不合法，方便不熟悉代码的成员自己定位。

---

## 6. 运行测试

```powershell
cd backend
python -m pytest
```

**当前结果：125 passed, 1 skipped。**

那 1 个 skip 不是失败：`tests/test_contracts.py` 里有一条用例专门验证
「公共 Schema 声明 `uniqueItems: true` 的数组，模型必须在运行时真的拒绝重复项」。
`PlanResult` 的公共 Schema 中没有任何 `uniqueItems` 字段，这条用例对它主动跳过，属于设计内行为。

按文件单独跑（例如只验证 Mock 数据是否合法）：

```powershell
python -m pytest tests/test_mock_data_schema.py -v
```

---

## 7. 当前 API

业务接口统一在 `/api/v1` 下；`/health` 作为探针额外挂在根路径。

| 方法 | 路径 | 返回 | 说明 |
|---|---|---|---|
| GET | `/health` | `{"status": "ok", ...}` | 服务存活。不检查数据库或上游模块（尚未接入） |
| GET | `/api/v1/health` | 同上 | 带版本前缀的同一探针 |
| GET | `/api/v1/mock/makeup-tasks` | `MakeupTask[]` | **Curriculum 模块本应输出**的补修任务 |
| GET | `/api/v1/mock/course-offerings` | `CourseOffering[]` | **Course Data 模块本应输出**的教学班；该 Mock 通道内 `data_source` 全部为 `"mock"` |
| GET | `/api/v1/mock/preference` | `Preference` | **Agent 解析自然语言后本应产出**的偏好 |
| GET | `/api/v1/mock/plan-result` | `PlanResult` | **Planner 本应输出**的排课结果 |
| GET | `/api/v1/mock/demo` | 上述四个对象的聚合 | 前端原型阶段只调一个接口用，属附加能力 |
| POST | `/api/v1/plan` | `PlanResult` | **生产真实入口**。未装配时 `503 real_pipeline_not_configured`，⛔ 不回退 Mock |
| POST | `/api/v1/completed-courses/import` | 摄取结果 | 通用已修课程 XLSX 摄取（次要兼容路径） |
| POST | `/api/v1/completed-courses/import-pdf` | 摄取结果 | 成绩单 PDF 摄取（Case A 主路径） |
| GET | `/api/v1/case-a-demo/offerings` | `CourseOffering[]` | Case A 演示：已验收的**南 + 深圳** scoped 教学班 |
| POST | `/api/v1/case-a-demo/plan` | Case A 加法式响应 | Case A 闭环：补修 / 建议换班 / 路线图 / 选修账 |
| POST | `/api/v1/case-a-demo/repair/apply` | 应用结果 | **显式确认**换班；⛔ 生成建议时绝不自动应用 |

**只有 `/api/v1/mock/*` 路径的响应带 `X-Data-Source: mock` 响应头**（由
`app/main.py` 的中间件按路径前缀添加）。真实入口与 Case A 演示通道**不带**该响应头，
且 ⛔ **不会**被标记成 Mock；`CourseOffering.data_source` 在 Case A 演示通道取值为 `"real"`。
这样调用方既不可能把演示数据误认成真实教务数据，也不可能把真实数据误认成 Mock。

> ⚠️ `/api/v1/mock/*` 是**永久只读的 Mock 通道**：不是计算，也不会变成真实数据接口。
> 它只回放 `/mock_data/` 下的演示数据，任何阶段都不会返回真实教务数据；
> 例如 `/mock/plan-result` 返回的方案**不是求解器算出来的**，而是人工写好的演示结果。

---

## 8. Mock / Real 边界（重要）

> ⚠️ **本节只描述 `/api/v1/mock/*` 永久 Mock 通道**。
> ⛔ 不要把它读成"整个后端只有 Mock 数据" —— 真实入口与 Case A 演示通道见本文件开头
> 与 `docs/status/integration.md`。

- **Mock 通道**的数据来自仓库根目录的 `/mock_data/`，均为人工虚构的演示数据，
  **不是任何学校的真实教务数据**。详见 `/mock_data/README.md`。
- `CourseOffering` 的公共 Schema 中有 `data_source` 字段：
  **Mock 通道**取值为 `"mock"`；
  真实 Case A 演示通道（`/api/v1/case-a-demo/*`）取值为 `"real"`。
- `MakeupTask` / `Preference` / `PlanResult` 的公共 Schema **没有** `data_source` 字段，
  且声明了 `additionalProperties: false`。因此本项目**不在这三个对象上私自增加来源字段**
  （那属于未获批准的公共接口变更），Mock 通道改为通过响应头 `X-Data-Source: mock` 与文档明确标记。
- **`/api/v1/mock/*` 与 `app/services/mock_service.py` 永远只服务 Mock**：
  它们不会在将来被“原地替换”成真实数据源（见第 9 节）。
- 真实数据接入必须在**本人正常登录、已有权限查看**的范围内获取。
  任何绕过登录、破解验证码、越权访问的做法都禁止（`/AGENTS.md` 第 8 节）。
- **真实通道现状**：`/api/v1/plan` 由 `app/services/planning_runtime.py` 环境驱动装配，
  未装配时返回 `503 real_pipeline_not_configured`（⛔ 不回退 Mock）；
  `/api/v1/case-a-demo/*` 消费**已验收的**南校园 + 深圳校区 scoped Course Data
  （`is_full_semester = false`），⛔ 不声称全校完整或完整学期覆盖。

---

## 9. 真实模块如何接入

**先说清楚三条不会变的事：**

1. `app/services/mock_service.py` **永远是 Mock-only**。
   它只读 `/mock_data/` 下的演示数据，永远不会读取真实教务数据，也不会被"原地改造成"真实数据源。
2. `/api/v1/mock/*` **永远只返回 Mock 数据**，永远带 `X-Data-Source: mock`。
   它不会被改造成真实数据接口，任何人都不应把这条通道的结果当成真实结果。
3. 真实通道**已存在**，且**不受本节第 1、2 条影响**：
   `/api/v1/plan`（生产入口）与 `/api/v1/case-a-demo/*`（Case A 私有演示入口）
   走的是**新增的独立 adapter / provider**，不是改写 `mock_service`。

```text
Mock 通道（始终存在）:  /api/v1/mock/course-offerings  ->  mock_service  ->  mock_data/*.json
生产真实通道:           /api/v1/plan                  ->  planning_runtime（环境驱动装配）
                       未装配 ⇒ 503 real_pipeline_not_configured，⛔ 不回退 Mock
Case A 演示通道:        /api/v1/case-a-demo/*          ->  已验收 scoped Course Data（南 + 深圳）
```

⚠️ **仍未完成的部分（⛔ 不得说成已完成）**：

- 真实通道**尚未**用**完整学期 / 全校**数据跑通，因此 formal Real E2E 仍为 `LEVEL 0`；
- Course Data 当前是 **case-scoped**（南校园 + 深圳校区，`is_full_semester = false`），
  ⛔ 不是全校完整、也⛔ 不是完整学期；
- production Curriculum / Planner provider 的**真实**装配仍待受控输入，未装配即 503；
- 未来学期的教学班 / 教师 / 教室 / 上课时间**不存在**，也**不预测**：
  未来学期只做**课程级**规划。

无论走哪条通道，对外返回的都必须是符合 `/schemas/*.schema.json` 的公共对象；
契约层与前端因此不需要因为"数据来源变了"而重写。

## 10. 手动验收步骤

1. 按第 5 节启动服务（看到 `Uvicorn running on http://127.0.0.1:8000` 即为启动成功）；
2. 浏览器打开 http://127.0.0.1:8000/docs ；
3. 调 `GET /health`，确认返回 `status: ok`（该探针的 `data_source` 字段仅表示
   **默认装配**为 Mock 通道，⛔ 不代表其它接口的来源）；
4. 调 `GET /api/v1/mock/demo`，确认返回四个键：
   `makeup_tasks`、`course_offerings`、`preference`、`plan_result`；
5. 在浏览器开发者工具的 Network 面板里，确认**该 `/api/v1/mock/*` 请求**的响应头
   包含 `X-Data-Source: mock`；若同时调了 `/api/v1/plan` 或 `/api/v1/case-a-demo/*`，
   确认它们的响应头里**没有**该标记；
6. 调 `GET /api/v1/mock/plan-result`，确认 `unresolved` 里有 `manual_confirmation` 项
   ——系统应当**诚实暴露待人工确认的部分**，而不是假装已经全部解决；
7. （可选）把 `mock_data/course_offerings.json` 里某个教学班的
   `meetings[0].weekday` 改成 `9`，重启服务，
   确认进程启动失败并给出指向该字段的报错；改回后恢复正常。

---

## 11. 出问题先检查什么

| 现象 | 先查这里 |
|---|---|
| 一启动就报「启动自检失败：Mock 数据不符合公共契约」 | `mock_data/` 下的 JSON 被改坏了。报错信息里有文件名和字段名 |
| 接口 404 | 业务接口是否漏了 `/api/v1` 前缀；`/mock/...` 直接挂在根路径是不存在的 |
| 改了 JSON 但接口还是旧数据 | 本层**不缓存**数据，改完下一次请求即生效；请确认改的是仓库根目录的 `mock_data/`，并强制刷新浏览器缓存 |
| 启动自检没有重新跑 | 自检只在进程启动时执行一次，改完数据需要重启服务才会重新自检 |
| `ModuleNotFoundError: No module named 'app'` | 必须在 `backend/` 目录下运行命令（`pyproject.toml` 里配置了 `pythonpath = ["."]`） |
| `--reload` 改了 JSON 没反应 | 热重载只监听 `.py` 文件，不监听 `.json` |

---

## 12. 相关文档

- `/AGENTS.md` —— 所有 Agent 的最高层协作约束（模块边界、Git、Schema、安全）
- `/schemas/*.schema.json` —— **公共契约的唯一真源**，`app/models/contracts.py` 只是它的映射
- `/mock_data/README.md` —— Mock 数据的清单与来源声明
- `/docs/interfaces/agent_frontend.md`、`/docs/interfaces/course_data.md` —— 上下游接口定义
- `/docs/status/agent_frontend.md` —— 本模块当前状态（新成员优先读这个）
- `/docs/worklogs/agent_frontend.md` —— 本模块历史工作记录

---

## 13. 已知限制（有意保留，不是缺陷）

- 没有生产数据库。Course Data 的**本地** SQLite 是 Case A 验收 artifact 的载体，
  ⛔ 不是服务端持久层；Mock 数据体量极小，直接读文件更利于排查。
- 前端页面**已存在**（`frontend/`，Vue 3 + TypeScript + Vite），
  本后端模块仍只保证接口可被调用。
- 没有 LLM / Agent Tool Calling。Case A 的编排是**固定工具编排**，AI 增强待接入。
- 没有 `courses.json`。`Course` 对象应由 Curriculum 模块在真实培养方案接入后产出，本次不预造。
- 真实通道**已存在但尚未全覆盖**：`/api/v1/plan` 未装配时为 503；
  Case A 演示通道是 **case-scoped**（南 + 深圳，`is_full_semester = false`），
  ⛔ 不是全校完整 / 完整学期。
- 未来学期**没有**教学班 / 教师 / 教室 / 上课时间，也**不预测**这些信息。
- `app/models/contracts.py` 与 `/schemas/*.schema.json` 的一致性靠测试维护，
  而不是代码生成。若未来 Schema 频繁变动，应改为从 Schema 生成模型，避免人工同步漂移。
