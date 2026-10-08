# 学航·转衔 — 前端最小 Demo 壳层（Phase 2A）

> **本页展示的全部内容是 Mock 演示数据，不是真实教务数据，不能作为真实选课或补修决策的依据。**

这一层目前只做一件事：把后端 Mock 通道
`GET /api/v1/mock/demo` 返回的四类公共对象**清楚地展示出来**。

它**不是**完整前端，也**不包含**任何业务算法。

---

## 1. 技术栈（已由负责人确认）

```text
Vue 3 + TypeScript + Vite
```

本阶段**刻意不引入**：Vue Router、Pinia、Element Plus 等 UI 组件库、图表库、复杂状态管理。
样式是原生 CSS，目的只有一个：把结构讲清楚。

---

## 2. 目录结构

```text
frontend/
  index.html
  package.json
  tsconfig.json
  vite.config.ts          # 含开发/预览代理配置（后端地址集中在这里）
  .env.example            # 环境变量示例（真实的 .env 不提交）
  README.md
  src/
    main.ts               # 挂载入口
    App.vue               # 页面骨架 + 加载/成功/失败三种状态
    config.ts             # 后端地址集中配置（只在这里出现一次）
    vite-env.d.ts
    api/
      demo.ts             # 唯一的数据来源：GET /api/v1/mock/demo
    composables/
      useDemoData.ts      # loading / success / error 状态机
    types/
      contracts.ts        # 与 /schemas/ 手工对齐的 TS 类型（只读，不改契约）
    utils/
      labels.ts           # 纯展示用的中文标签与格式化
    components/
      TopStatusBar.vue        # A. 顶部状态 + Mock 警示
      SectionCard.vue         # 区块外壳（标题 + Mock 标记）
      MakeupTaskList.vue      # B. 补修任务
      CourseOfferingList.vue  # C. 教学班（按课程分组）
      PreferencePanel.vue     # D. 用户偏好
      PlanResultPanel.vue     # E. 最终方案（status/changes/risks/unresolved…）
    styles/
      base.css
```

---

## 3. 运行前：先启动后端

前端只消费后端 Mock 通道，所以**必须先有后端**：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

后端默认监听 `http://127.0.0.1:8000`。可以先自测一下：

- <http://127.0.0.1:8000/health>
- <http://127.0.0.1:8000/api/v1/mock/demo>

---

## 4. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

然后打开终端里提示的地址（默认 <http://127.0.0.1:5173>）。

构建生产产物：

```powershell
npm run build      # 类型检查 + 打包，产物在 frontend/dist/
npm run preview    # 本地预览构建产物（默认 http://127.0.0.1:4173）
```

只做类型检查：

```powershell
npm run typecheck
```

---

## 5. 后端地址怎么配（重要）

后端地址**只在一处**配置，不散落在组件里：`vite.config.ts` + 可选的环境变量。

默认行为是**同源 + Vite 代理**：

```text
浏览器  →  http://127.0.0.1:5173/api/v1/mock/demo
                    ↓（Vite 开发/预览服务器转发）
后端    →  http://127.0.0.1:8000/api/v1/mock/demo
```

这样做的好处是：**本地联调完全不需要后端开启 CORS**，因此**不用改动 Phase 1 的后端代码**。

要改后端地址，复制 `.env.example` 为 `.env` 再改：

```ini
# 代理目标：Vite 把 /api 请求转发到这里
VITE_PROXY_TARGET=http://127.0.0.1:8000

# 可选：让浏览器直连后端。留空（默认）就走上面的代理。
# 一旦填写，请求变成跨域，需要后端自行开启 CORS。
VITE_API_BASE_URL=
```

> `.env` 不提交；`.env.example` 可以提交，且**不含任何真实密钥**。

---

## 6. Mock / Real 边界

- 本页面**只**调用 `/api/v1/mock/demo`，这是后端的**永久 Mock 通道**。
- 顶部有醒目的黄色警示条，每个区块都带 `Mock` 标记，并显示后端响应头
  `X-Data-Source` 的实际取值（正常应为 `mock`）。
- 页面文案刻意避免"推荐你实际选择这些课程"这类会让人误以为可用于真实选课的表述；
  方案区标注为演示方案。
- 请求失败时页面**只显示错误**，**不会**在本地编造一份数据继续展示——
  这条红线在 `useDemoData.ts` 里用「错误时 `data` 置为 `null`」来保证。

---

## 7. 本阶段包含 / 不包含

**包含**：顶部 Mock 状态标识；四个带顶层标题与 `Mock` 标记的明确区域——
**补修任务 / 教学班 / 用户偏好 / 最终方案**（最终方案内含
`status` / `selected_classes` / `changes` / `risks` / `unresolved` / `objective_summary`）；
以及加载中与请求失败两种状态。

**不包含**（属于后续阶段，本轮明确不做）：

- 任何 Curriculum / 课程等价 / 冲突检测 / Planner / Path Repair / 风险等级计算；
- 前端自行修改或重算 PlanResult；
- 真实教务数据、登录、Cookie / Token、浏览器插件、数据库；
- LLM / Agent Tool Calling；
- 课程依赖图、复杂图表、动画、完整比赛视觉设计、多页面路由。

前端只做三件事：**发请求、按后端给的枚举显示、对失败诚实报错。**

---

## 8. 手动验收步骤

1. 启动后端（第 3 节），确认 `/api/v1/mock/demo` 有返回；
2. 启动前端（第 4 节），打开页面；
3. 顶部确认看到：`学航·转衔` / `当前数据 Mock Demo` / `当前状态 演示环境`，
   以及黄色警示条与 `后端来源标记 mock`；
4. 依次确认四个区块都在：补修任务、教学班、用户偏好、最终方案；
5. 在最终方案里确认：
   - `changes` 能看懂「原教学班 ↓ 修改为 新教学班 + 原因」；
   - `risks` 显示了 `低 / 中 / 高` 等级（等级来自后端，前端不重算）；
   - `unresolved`（未解决事项）区块显眼：每条显示由 `type` 翻译出的标签
     （`manual_confirmation` → 待人工确认，`missing_data` → 缺少数据，未知类型原样显示），
     并同时保留原始 `type` 以便追溯；
6. **失败路径**：停掉后端，刷新页面 → 应看到「Demo 数据加载失败」+ 非敏感错误说明 + 重新加载按钮，
   且页面上**没有**任何编造的数据。

---

## 9.5 「查看依据 / 为什么这样安排」解释功能（Final Upgrade · Agent B）

新增的第 5 区块提供**只读解释**：点某项补修判定 / 某个建议教学班 / 某条调班 /
某条风险 / 某条未决事项旁边的「🔍 查看依据」，即可看到后端给出的解释、
**来源字段与原始取值**、证据强度，以及**仍需人工确认**的事项。

### 打开方式

解释通道默认**关闭**（关闭时页面不会发出任何解释请求，只显示"未启用"）：

```ini
# frontend/.env.local
VITE_EXPLANATION_API_ENABLED=true
```

### 三条必须知道的边界

1. **解释不参与计算**：它只读消费已有的 `PlanResult`（可选附带 `MakeupTask` /
   `CourseOffering` 上下文），打开 / 关闭都不会改变方案、判定或输入；
   面板会显示被解释方案的指纹（`plan_result_digest`）供核对。
2. **生成方式如实标注**：当前未配置任何模型服务，因此所有解释都是
   **确定性规则模板**，界面上明确显示「规则模板（非 AI）」。
   只有后端明确返回模型生成时，界面才会显示「AI 模型生成」；
   模型输出未通过事实绑定校验时会降级并显示降级原因。
3. **只发送必要对象**：请求体只有 `plan_result` / `makeup_tasks` / `course_offerings`，
   ⛔ 不发送成绩单、姓名、学号或个人身份信息；失败时只如实报错，不伪造解释。

### 手动验收步骤

1. 启动后端与前端（第 3、4 节），设置 `VITE_EXPLANATION_API_ENABLED=true` 后重启 `npm run dev`；
2. 页面第 5 区块显示「解释对象：Mock 演示结果 / 解释通道：已启用」；
3. 点击「🔍 查看依据 / 为什么这样安排」→ 面板列出全部解释条目；
4. 在补修任务表点击某一行的「🔍 查看依据」→ 面板只显示该课程的条目；
5. 确认每条解释都带「直接依据」的来源字段与原始取值，且「仍需人工确认」非空；
6. **失败路径**：停掉后端后点击入口 → 面板显示错误类型与"不会伪造解释"的说明。

---

## 10. 已知限制（有意保留）

- 只有一个页面，没有路由；没有单元测试（本阶段不强制）。
- 前端类型是与 `/schemas/*.schema.json` **手工对齐**的，不是代码生成；
  若契约变更，需要同步 `src/types/contracts.ts`，但它**不是**契约真源。
- `changes` / `selected_classes` 里只有课程号，页面为了可读性做了一个
  「课程号 → 课程名」的显示查找（见 `App.vue` 的 `courseNameById`）。
  这**只是显示辅助**，不参与任何判定。
- 生产构建产物是纯静态文件，部署时必须由能转发 `/api` 的服务器提供，
  或给后端配上 CORS 并设置 `VITE_API_BASE_URL`。
