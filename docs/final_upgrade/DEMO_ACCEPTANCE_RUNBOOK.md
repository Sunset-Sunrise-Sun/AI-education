# Final Upgrade｜产品演示与验收操作指南（2026-10-09）

适用分支：`feature/final-upgrade`。这份文档覆盖新三入口网页、个人规划、规则解释和 AI 调整；早期 `frontend/README.md` 和 `backend/README.md` 的 Phase 1 / 2A 描述属于历史阶段，不能据此判断本分支现有功能。

## 1. 演示边界

| 模式 | 使用的数据及计算 | 应标注 |
| --- | --- | --- |
| Case A / Mock 页面 | 既有 Mock 数据与演示结果 | Mock，不能称作真实教务数据 |
| 个人规划前端预览 | 前端 fixture | 仅前端预览、未读取真实目录 |
| AI 调整前端预览 | 前端 fixture，不调用后端 Planner 或 DeepSeek | 仅前端预览 / 非真实模型 / 未调用 Planner |
| AI 后端真实请求 | 后端依赖装配与来源决定；缺配置时应失败而非造结果 | 如实展示 `generator_kind` 与 `data_source` |
| 真实教务端到端 | 当前尚未接入可核验完整输入 | NOT VERIFIED |

`adopted_version_scope=process_local_session` 只代表进程内临时采用，并非学校教务选课、持久化存档或跨设备同步。

## 2. 本地启动（PowerShell）

```powershell
git fetch origin
git switch feature/final-upgrade
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

打开第二个终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问终端提示的前端 URL（通常为 `http://127.0.0.1:5173`）。后端探针：`http://127.0.0.1:8000/health`；OpenAPI：`http://127.0.0.1:8000/openapi.json`；默认 Vite 代理把 `/api` 请求发往 `127.0.0.1:8000`。

**后端 `backend/.env.example` 仅作环境变量清单，不代表 Python 会自动加载 `.env`。** 本地如需配置，应通过启动进程的环境变量或已经核实的环境注入机制，且密钥只放在服务器环境，不要写入前端、Git、日志或聊天。

## 3. 推荐的三个演示档位

### A. 不需要任何 API Key：安全展示页面

在 `frontend/.env.local` 配置：

```ini
VITE_EXPLANATION_API_ENABLED=true
VITE_PERSONAL_PLANNING_API_ENABLED=false
VITE_PERSONAL_PLANNING_PREVIEW=true
VITE_AI_PLANNING_API_ENABLED=false
VITE_AI_PLANNING_PREVIEW=true
```

修改 Vite 环境文件后重启前端。检查三个入口：转专业分析、补修路径、AI 调整。所有预览必须出现“仅前端预览”提示，不得将其演示成调用了 DeepSeek 或 Planner。解释接口是规则模板，应标明“规则模板（非 AI）”。

### B. 真实后端，但不使用 DeepSeek

```ini
VITE_EXPLANATION_API_ENABLED=true
VITE_PERSONAL_PLANNING_API_ENABLED=true
VITE_PERSONAL_PLANNING_PREVIEW=false
VITE_AI_PLANNING_API_ENABLED=true
VITE_AI_PLANNING_PREVIEW=false
```

后台默认 `AI_PLANNING_ENABLED=false`，`GET /api/v1/ai-planning/status` 应报告 `enabled=false`；正常页面应如实提示“未启用”，不能显示成功候选。

个人规划版本目录若未配置，应提示“没有已核验版本目录”；`planning=null` 时不显示“已排好课”。后端不存在真实输入时不能自动切换 Mock 结果冒充真实方案。

### C. 后端真实 DeepSeek：仅受控在线验收

**此档位尚未验证成功。** 必须在服务器侧使用新的有效密钥，并显式设置：

```text
AI_PLANNING_ENABLED=true
DEEPSEEK_API_KEY=(通过安全的进程环境注入，不写入文档)
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=(以已验证的可用模型为准)
```

注意：`GET /status` 返回 `live_model_available=true` 仅表示开关启用且密钥已配置，**不是**在线鉴权或模型调用成功证明。只有一次受控 `POST /interpret` 实际成功且响应 `generator_kind=deepseek_live`，结合服务端非敏感调用日志，才可以确认 DeepSeek 在线路径可用。

## 4. 浏览器人工验收（按用户路径）

- **初始页面**：三入口可切换，Mock/Real/预览提示明确；导航与旧补修列表没有丢失。
- **转专业分析**：无真实目录时明确不可用；缺学期/教学班时，不显示已经排好课的假状态。
- **补修路径**：补修任务四状态不混淆，来源、风险、未决事项及“查看依据”可查看。
- **AI 调整**：输入“这学期太累，数据结构必须保留，尽量别在周五上课”；不凭“太累”猜学分上限。第一次确认意图；后端有求解能力时才展示候选。
- **候选对比**：只有 `candidate_ready` 能采用；换班显示旧班 → 新班；`no_feasible_candidate` 和 `blocked` 不应出现采用按钮。
- **二次确认**：`accept=true` 且后端确认 `state=adopted` 才刷新；明确显示临时会话版本。拒绝、410、409、503 保持原方案。
- **移动端**：抽屉全屏、长课程名称、长风险文本、窄屏滚动和确认按钮应可操作。
- **网络失败**：关闭后端或断网，应显示错误而不是回退 fixture。

只有使用真实浏览器并记录实际结果后，才能将浏览器端到端状态从 NOT VERIFIED 改为 PASS。

## 5. 自动测试基线与遗留风险

开发 Agent 上轮报告：后端 `3188 passed / 2 failed / 2 skipped`；前端 `274 passed`；类型检查及构建通过；使用 uvicorn + urllib 的后端真实 HTTP E2E 通过。上述数字**不是本指南提交时重新运行**的测试结果。两项后端失败为已记录的 Windows / Python 3.14 路径语义差异。

依赖安全：`vitest@3.2.7` 测试链的 `tinypool` / `@vitest/mocker` 和构建链的 `source-map-js` 已被报告存在漏洞。此前审计认为不进入当前静态前端交付产物，但**漏洞尚未修复**；执行不可信提交的测试或公开部署开发服务前，仍须先完成依赖升级、安全复核和隔离策略。

## 6. 本阶段明确未完成

- 新密钥的真实 DeepSeek 在线调用与模型可用性验证；
- 已核验真实培养方案、真实教学班快照、真实个人成绩数据 E2E；
- 浏览器级自动化 E2E；
- 持久方案版本、跨进程/跨设备会话；
- `exclude_course`、跨学期自动重排、可行子集多候选优化；
- 修复上述测试/构建依赖漏洞。

以上不能通过 Mock 截图、前端预览或测试替身模型代替。
