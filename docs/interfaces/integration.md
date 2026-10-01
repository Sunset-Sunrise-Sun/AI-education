# Integration 模块接口

> ⚠️ **本文件位于 `/docs/interfaces/`，因此它属于项目的公共跨模块接口**
> （`/AGENTS.md` 第 4 节把 `/schemas/` 与 `/docs/interfaces/` 一并列为公共契约）。
>
> 必须区分两件事：
>
> - 本文件**不新增业务对象 Schema**，也**不修改** `/schemas/` 中的公共数据结构；
> - 但本文件定义的 **Provider 调用边界属于项目的公共跨模块接口**。
>
> 它回答的是："**谁按什么顺序调用谁**"。
>
> 后续模块**不得自行修改** Provider 方法名、参数语义或返回类型；
> 如需变更，仍必须按 `/AGENTS.md` 第 4 节提交 `【接口变更请求】` 并经负责人确认。

## 1. Integration 职责

**Integration = 调用 / 编排**，不是业务算法。

```text
CurriculumProvider ─────┐
                        │
CourseDataProvider ─────┼──> PlanningOrchestrator ───> PlannerProvider
                        │
current_schedule ───────┤
Preference ─────────────┘
```

Integration **只做三件事**：

1. 从 Curriculum 取 `MakeupTask[]`；
2. 从 Course Data 取某学期的 `CourseOffering[]`；
3. 把两者与 `current_schedule`、`Preference` 一起交给 Planner，并**原样**返回 `PlanResult`。

Integration **不得**：

- ❌ 判断学生缺什么课；
- ❌ 判断课程是否等价；
- ❌ 认定 prerequisite；
- ❌ 生成 priority；
- ❌ 检测时间冲突；
- ❌ 选择教学班；
- ❌ 执行 Path Repair；
- ❌ 修改 `PlanResult`；
- ❌ 排序 / 筛掉 / 去重 / 补默认值 / 计算派生值。

> 代码位置：`backend/app/integration/`（`ports.py` = 插座，`orchestrator.py` = 顺序）。
> 这些**不是新的业务对象 Schema**，但它们是**已确认的 Integration 公共接口边界** ——
> 四个调用签名见 §3.1「接口冻结」。

## 2. 三个 Provider

用 `typing.Protocol` 声明**最小形状**（结构类型，不要求继承基类）。

### 2.1 `CurriculumProvider`

```python
class CurriculumProvider(Protocol):
    def get_makeup_tasks(self) -> list[MakeupTask]: ...
```

- Integration **只**消费 Curriculum **已经产生的** `MakeupTask[]`；
- **不知道**：培养方案文件形态、`CompletedCourse` 内部结构、`CurriculumVersion` /
  `CurriculumCourse`、课程匹配实现；
- 具体实现将来可以在**构造时**绑定用户 / case 上下文 —— 那是实现内部输入，本接口不表达。

### 2.2 `CourseDataProvider`

```python
class CourseDataProvider(Protocol):
    def get_course_offerings(self, semester: str) -> list[CourseOffering]: ...
```

- Integration **只**知道：`semester` → `CourseOffering[]`；
- **绝不能**知道：`jwxt.sysu.edu.cn`、POST endpoint、`pageNo` / `pageSize`、
  Cookie / Session / Token、`teachingTimePlaceStr`、`class_ID`、`courseNumber`；
- 这些全部属于 **Course Data Adapter** 的实现细节（见 `docs/interfaces/course_data.md`）。

> 这是 **Phase 2B-2 Course Data MVP** 将真正实现的插座。**当前只有 Protocol，没有实现。**

### 2.3 `PlannerProvider`

```python
class PlannerProvider(Protocol):
    def plan(
        self,
        *,
        makeup_tasks: list[MakeupTask],
        offerings: list[CourseOffering],
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult: ...
```

- 入参**不包含** `priority` / `dependency_graph` / `risk_scores`（见第 5 节）；
- 是否 `feasible` / `partially_feasible` / `infeasible` **由 Planner 决定**，
  Integration **不得**代替 Planner 判断，也不得改写返回的 `PlanResult`。

## 3. `PlanningOrchestrator` 调用顺序

```python
@dataclass(frozen=True)
class PlanningOrchestrator:
    curriculum: CurriculumProvider
    course_data: CourseDataProvider
    planner: PlannerProvider

    def build_plan(
        self,
        *,
        semester: str,
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult: ...
```

内部流程**严格固定**为：

```text
CurriculumProvider.get_makeup_tasks()
            ↓
CourseDataProvider.get_course_offerings(semester)
            ↓
PlannerProvider.plan(
    makeup_tasks=...,
    offerings=...,
    current_schedule=...,
    preference=...
)
            ↓
原样返回 PlanResult（同一个对象）
```

- Orchestrator **只持有**三个 Provider，不持有状态 / 缓存 / 会话 / 上下文；
- `semester` **原样**传给 Course Data（不改写、不规整、不补默认值）。

### 3.1 接口冻结（Phase 2B-1 已确认）

**以下四个调用签名已经是 Phase 2B-1 确认的 Integration 公共接口**：

```python
# CurriculumProvider
def get_makeup_tasks(self) -> list[MakeupTask]: ...

# CourseDataProvider
def get_course_offerings(self, semester: str) -> list[CourseOffering]: ...

# PlannerProvider
def plan(
    self,
    *,
    makeup_tasks: list[MakeupTask],
    offerings: list[CourseOffering],
    current_schedule: list[CourseOffering],
    preference: Preference,
) -> PlanResult: ...

# PlanningOrchestrator
def build_plan(
    self,
    *,
    semester: str,
    current_schedule: list[CourseOffering],
    preference: Preference,
) -> PlanResult: ...
```

- 它们是**代码侧的事实接口**（`backend/app/integration/ports.py` 与 `orchestrator.py`），
  与本文件一一对应；
- 后续模块**不得自行修改**方法名、参数语义或返回类型；
- 如需变更，仍必须按 `/AGENTS.md` 第 4 节提交 `【接口变更请求】` 并经负责人确认；
- 特别地：`PlannerProvider.plan()` 的参数集合**恰为四个**，
  不得私自添加 `priority` / `dependency_graph` / `risk_scores` 等（见第 5 节）。

## 4. `current_schedule` 的语义

按 Data Gate **DG-03**：**复用现有公共类型，不新增 `CurrentEnrollment` Schema**。

```text
CourseOffering[]                     —— 学校**全部供给**（Course Data 输出）
current_schedule: CourseOffering[]   —— 学生**已经选择**的教学班子集
```

两者**类型相同、语义不同**，**不得混用**：

- 冲突检测的一侧是 `current_schedule`，**不是**学校开设的全部教学班；
- ⛔ **不允许**用 `Preference.avoid_times[]` 冒充当前课表 ——
  `avoid_times` 是**偏好上的回避**，不是"已经选中了哪些课"这一事实；
- `current_schedule=[]`（空列表）是**合法输入**：Integration 不得因此报错，
  应原样下传，由 Planner 处理。

## 5. dependency / priority 边界

按 Data Gate **DG-05**：

- Planner 唯一可消费的公开依赖信息是 **`MakeupTask.prerequisites[]`**；
- **Curriculum** 负责认定 / 产出 dependency edges；
- **Planner** 可以把**已经收到的** `prerequisites[]` 转换成本地 adjacency / topology
  供确定性求解使用，但**不得新增、猜测、重写**任何 prerequisite edge；
- 真实来源无法提供 prerequisite 时标记 **未知 / 待人工确认**，**不得自动补齐**；
- **MVP 当前不存在公共 `priority` 字段**，也不存在 `DependencyGraph` / `PriorityResult`；
- ⛔ **没有正式 priority 数据时，Planner 不得自行生成优先级**；
- ⛔ 因此 `PlannerProvider.plan()` **不接收** `priority` / `dependency_graph` / `risk_scores`。

**在正式接口变更之前，不得声称 Integration 或 Planner 已经消费跨模块 priority。**

## 6. 错误处理原则

- Provider 报错时：**异常原样向上传递**；
- ⛔ Integration **不吞异常**、**不返回 fallback**、**不自动切换到 Mock**；
- ⛔ 不允许"Planner 出错时返回一份 Mock `PlanResult`"这种兜底；
- 本轮**不设计复杂异常体系**：没有自定义异常层级、没有重试、没有降级策略。

## 7. Mock 与 Real 不自动 fallback

- `/api/v1/mock/*` 与 `backend/app/services/mock_service.py` 是**独立的永久 Mock 回放通道**，
  继续保持 **permanent Mock-only**，语义不变；
- **Integration 层不引用 `mock_service`**，也不会在真实 Provider 缺失时回退到它
  （该约束由 `backend/tests/test_integration_orchestrator.py` 的 AST 检查锁定）；
- ⛔ 本轮**不创建** `MockCurriculumProvider` / `MockCourseDataProvider` / `MockPlannerProvider` ——
  那会造成一种假的"完整 Integration 已经跑通"的错觉；
- Integration 的测试**只使用 test-only Fake / Spy Provider**。

## 8. 当前尚未开放真实 API

- ⛔ 本轮**不新增任何 API**：没有 `POST /plan`、没有 `POST /integration`、没有 `GET /real/...`；
- 原因：**production Curriculum / Course Data / Planner Provider 三件都还没有**，
  现在暴露 API 只会得到一个**无法真实工作的壳**；
- `backend/app/main.py` 本轮**未修改**，路由集合与 Phase 1 完全一致。

**当前 Integration 的真实状态**：

> Provider 边界与 Orchestrator skeleton 已完成；
> **production Curriculum / Course Data / Planner provider 尚未接入**，
> 因此还没有任何一条真实（非 Mock）的数据链路可以端到端跑通。
