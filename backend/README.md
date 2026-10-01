# 后端集成底座（组长模块 · Agent / Integration）— Phase 1

> **当前状态：全部数据均为 Mock 演示数据，尚未接入真实教务数据。**
>
> 本阶段的目标不是"做出产品"，而是先立好一块地基：一个能启动的 FastAPI 服务、
> 一套与 `/schemas/` 公共契约一致的校验层、一套可演示的 Mock 接口、一组自动测试。
> 这样即使 Curriculum / Course Data / Planner 还没写完，整条数据链路也能先跑起来。

---

## 1. 这一层负责什么，不负责什么

**负责**（集成层的本职）：

- 接收前端 / Agent 的请求；
- 用公共契约校验进入和离开的数据；
- 调用上游模块（**当前调用的是 Mock 数据**）；
- 统一返回格式与统一错误处理；
- 提供一个可被真实模块替换、而不必推翻前端的数据来源边界。

**不负责**（按 `/AGENTS.md` 第 5 节的模块边界）：

- 培养方案解析、已修课程结构化；
- 课程等价判定、课程正式认定；
- MakeupTask 的业务生成算法；
- 课程依赖、补修优先级；
- 时间冲突核心算法、OR-Tools CP-SAT 求解、Path Repair；
- 真实教务数据抓取。

> 换句话说：**别人算出来的结果，本层只负责"读、校验、转出去"。**
> 上面这些算法一旦出现在 `backend/` 里，就属于越界实现，应当被 Review 打回。

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
| GET | `/api/v1/mock/course-offerings` | `CourseOffering[]` | **Course Data 模块本应输出**的教学班，全部 `data_source = "mock"` |
| GET | `/api/v1/mock/preference` | `Preference` | **Agent 解析自然语言后本应产出**的偏好 |
| GET | `/api/v1/mock/plan-result` | `PlanResult` | **Planner 本应输出**的排课结果 |
| GET | `/api/v1/mock/demo` | 上述四个对象的聚合 | 前端原型阶段只调一个接口用，属附加能力 |

**所有响应都带 `X-Data-Source: mock` 响应头。** 这是刻意的：调用方不可能把演示数据误认成真实教务数据。

> ⚠️ `/api/v1/mock/*` 是**永久只读的 Mock 通道**：不是计算，也不会变成真实数据接口。
> 它只回放 `/mock_data/` 下的演示数据，任何阶段都不会返回真实教务数据；
> 例如 `/mock/plan-result` 返回的方案**不是求解器算出来的**，而是人工写好的演示结果。

---

## 8. Mock / Real 边界（重要）

- 本阶段**全部数据**来自仓库根目录的 `/mock_data/`，均为人工虚构的演示数据，
  **不是任何学校的真实教务数据**。详见 `/mock_data/README.md`。
- `CourseOffering` 的公共 Schema 中有 `data_source` 字段，本目录全部取值为 `"mock"`。
- `MakeupTask` / `Preference` / `PlanResult` 的公共 Schema **没有** `data_source` 字段，
  且声明了 `additionalProperties: false`。因此本项目**不在这三个对象上私自增加来源字段**
  （那属于未获批准的公共接口变更），改为通过响应头 `X-Data-Source: mock` 与文档明确标记。
- **`/api/v1/mock/*` 与 `app/services/mock_service.py` 永远只服务 Mock**：
  它们不会在将来被“原地替换”成真实数据源（见第 9 节）。
- 真实数据接入必须等用户完成教务页面的技术侦察，并在**本人正常登录、已有权限查看**的范围内获取。
  任何绕过登录、破解验证码、越权访问的做法都禁止（`/AGENTS.md` 第 8 节）。

---

## 9. 未来真实模块如何接入（Phase 1 不做实现）

**先说清楚三条不会变的事：**

1. `app/services/mock_service.py` **永远是 Mock-only**。
   它只读 `/mock_data/` 下的演示数据，永远不会读取真实教务数据，也不会被"原地改造成"真实数据源。
2. `/api/v1/mock/*` **永远只返回 Mock 数据**，永远带 `X-Data-Source: mock`。
   它不会被改造成真实数据接口，任何人都不应把这条通道的结果当成真实结果。
3. **Phase 1 不实现任何 Real Provider，也不在本阶段设计新的正式 API。**
   真实接入的接口形状，要等上游模块（Curriculum / Course Data / Planner）产出稳定结果之后，
   由负责人与相关模块一起确认；如需改动公共契约，走 `/AGENTS.md` 第 4 节的流程。

**方向性说明（不是本阶段的承诺，也不是本阶段要做的设计）：**

真实数据将通过**新增独立的 adapter / provider** 进入系统，而不是改写 `mock_service`。
Mock 通道与将来的真实通道是两条并行路径，互不影响：

```text
Mock 通道（始终存在）:  /api/v1/mock/course-offerings  ->  mock_service  ->  mock_data/*.json
真实通道（未来新增）:   路径与形状待定                  ->  新增 adapter / provider  ->  Course Data 模块
```

无论走哪条通道，对外返回的都必须是符合 `/schemas/*.schema.json` 的公共对象；
契约层与前端因此不需要因为"数据来源变了"而重写。

**本阶段的下游影响：** 以上都属于后续阶段的决策，当前不实现，也不需要其他模块现在就配合改动。

## 10. 手动验收步骤

1. 按第 5 节启动服务（看到 `Uvicorn running on http://127.0.0.1:8000` 即为启动成功）；
2. 浏览器打开 http://127.0.0.1:8000/docs ；
3. 调 `GET /health`，确认返回 `status: ok` 且 `data_source: mock`；
4. 调 `GET /api/v1/mock/demo`，确认返回四个键：
   `makeup_tasks`、`course_offerings`、`preference`、`plan_result`；
5. 在浏览器开发者工具的 Network 面板里确认响应头包含 `X-Data-Source: mock`；
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

- 没有数据库。本阶段不需要，且 Mock 数据体量极小，直接读文件更利于排查。
- 没有前端页面。前端框架尚未最终确定（见 `/docs/ARCHITECTURE.md`），本阶段只保证后端可被调用。
- 没有 LLM / Agent Tool Calling。属于后续阶段。
- 没有 `courses.json`。`Course` 对象应由 Curriculum 模块在真实培养方案接入后产出，本次不预造。
- 没有真实数据通道。本阶段只有 Mock 通道；真实 adapter / provider 属于后续阶段，尚未设计。
- `app/models/contracts.py` 与 `/schemas/*.schema.json` 的一致性靠测试维护，
  而不是代码生成。若未来 Schema 频繁变动，应改为从 Schema 生成模型，避免人工同步漂移。
