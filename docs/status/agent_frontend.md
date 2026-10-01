# Agent / Frontend 当前状态

> 最后更新：2026-09-30（**Phase 2B-0B：中山大学公开官方材料获取**完成，等待 Reviewer）
> 数据状态：**核心业务数据仍全部为 Mock**；本轮只取得少量**公开官方支持材料**，未取得任何真实培养方案

## 当前阶段

**Phase 2B-0：真实数据准备与数据源技术侦察**

```text
2B-0A ✅ 数据规划  →  2B-0B ← 本轮（公开政策 / 培养方案）
                   →  2B-0C 已修课程脱敏  →  2B-0D 教学班技术侦察
                   →  数据 Gate  →  恢复 Phase 2B Integration / Orchestrator
```

- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待真实样本通过 **数据 Gate** 后恢复；
  Phase 1 与 Phase 2A 成果不受影响。

## 2B-0B 当前结果（Case A：2025级 遥感科学与技术 → 网络空间安全）

| 目标 | 状态 | 说明 |
|---|---|---|
| **D1 政策** | **Partial（部分确认）** | 2 项 Confirmed；4 项 Partial；1 项 Historical；上级通知原文与校级课程认定专门制度 **Not Found** |
| **D2 2025级 遥感科学与技术 正式培养方案** | **Not Found** | 只有 **2019 级**正式方案与 **2021 年白皮书**，均**不能**替代 2025 级 |
| **D3 2025级 网络空间安全 本科正式培养方案** | **Not Found** | 学院「培养方案」栏目下只有**课程表**；找到的"2025 年方案"是**硕士**方案（明确排除） |

**Confirmed（2）**：
- `POLICY-001` 中山大学本科生学籍管理规定（中大教务〔2026〕62号），教务部现行收录，2026-08-16
- `POLICY-003` 网络空间安全学院 2026 年本科生转院系专业考核通知，2026-04-20

**Partial（7）**：`POLICY-002`（转专业实施办法，现行性未确认）、`POLICY-004`、`POLICY-005`、
`POLICY-006`（学分成绩转换操作指南，学院站点发布）、`CURR-OLD-001`（2019 级培养方案）、
`CURR-OLD-002`（专业白皮书，非培养方案）、`CURR-NEW-003`（本科生课程表，非培养方案）

**Not Found（1）**：`CURR-NEW-001`（2025 级网络空间安全本科培养方案）

**Historical（1）**：`POLICY-007`（学籍管理规定〔2022〕52号，已被〔2026〕62号取代）

**不适用（1）**：`CURR-NEW-002`（网络空间安全 0839 **硕士**培养方案，与本科 Case A 无关）

> ⚠️ **不得因为"找到了相关网页"就认为培养方案已获取。** D2 / D3 的 2025 级正式培养方案
> **均未找到**，本轮**没有**用旧版本或白皮书顶替。

## 已完成
- 模块边界和依赖接口已定义
- **前端技术栈已由负责人确认：Vue 3 + TypeScript + Vite**（`/docs/ARCHITECTURE.md` 已同步）
- 后端集成底座可启动：`backend/app/main.py`
- 与 `/schemas/` 一致的 Pydantic 校验层：`backend/app/models/contracts.py`（含 `uniqueItems` 的运行时强制）
- Mock 回放接口：`GET /api/v1/mock/{makeup-tasks, course-offerings, preference, plan-result, demo}`
- 健康检查：`GET /health`（另挂 `/api/v1/health`）
- 启动数据自检：**先按公共 JSON Schema 校验原始 JSON**（不依赖 Pydantic 的类型转换），不合契约时进程直接启动失败
- 后端自动测试：125 passed / 1 skipped（`cd backend && python -m pytest`）
- **前端最小 Demo 壳层已建立**：`frontend/`（Vue 3 + TypeScript + Vite，单页面，原生 CSS）
  - 唯一数据来源：`GET /api/v1/mock/demo`；同源请求，由 Vite 开发/预览服务器代理转发到后端
  - 顶部醒目 Mock 标识，四个区块各有 `Mock` 标记，并显示后端 `X-Data-Source` 实际取值
  - 四个展示区块：补修任务 / 教学班（按课程分组）/ 用户偏好 / 最终方案
  - loading / success / error 三态；请求失败时只报错，**绝不生成替代数据**
- 运行与验收说明：`backend/README.md`、`frontend/README.md`
- **2B-0A 数据获取规划**：`docs/data/` 四份规划文档（已 merge 进 `main`）
- **2B-0B 公开官方材料获取**：新增 `docs/data/SYSU_CASE_A_PUBLIC_EVIDENCE.md`；
  `docs/data/DATA_SOURCE_REGISTRY.md` 已登记 12 条真实官方来源并新增「证据等级」字段；
  `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` 中 **G1 更新为「已由真实材料部分验证」**

## 当前接口
- 读取：`MakeupTask[]`、`CourseOffering[]`、`Preference`、`PlanResult`（当前来自 Mock）
- 前端唯一数据来源：`GET /api/v1/mock/demo`
- 业务接口统一前缀 `/api/v1`；全部响应带 `X-Data-Source: mock`
- 公共契约真源仍是 `/schemas/*.schema.json`，本轮**未修改**

## 当前使用数据
- **业务数据仍全部为 Mock**：仓库根目录 `/mock_data/`（人工虚构的演示数据）
- 本轮取得的仅为**公开官方政策与培养方案的 URL / 事实**，**未下载任何文件进仓库**
- **真实培养方案尚未取得**（D2 / D3 均为 Not Found），真实数据链路尚未验证
- 「当前功能仅使用 Mock 数据验证，尚未完成真实数据验证」

## 当前阻塞
- **D2 / D3 的 2025 级正式培养方案在公开来源未找到**：需要负责人决定补充路径
  （用户本人从教务系统导出 / 咨询学院教务 / 暂缓）
- **政策版本冲突待人工确认**：学籍管理规定存在〔2026〕62号（现行）与〔2022〕52号（旧版）；
  转专业实施办法（`POLICY-002`）现行性未确认；Case A 转专业时点适用哪一版需人工判定
- 上游 Curriculum / Course Data / Planner 均未产出真实结果，前端只能展示 Mock
- **集成骨架尚未建立**：上游模块暂时没有正式的接入点
- **真实数据尚未通过数据 Gate**：2B-0C / 0D 均未开始，Phase 2B Integration 因此暂停编码

## 下一步
- **2B-0B 等待 Reviewer 验收**；同时等待负责人就 D2 / D3 的 `Not Found` 给出补充路径
- 负责人确认后进入 **2B-0C：已修课程脱敏**（D4；Raw 与脱敏样本均不得进入 public 仓库）
- 2B-0 全程遵守 `docs/data/DATA_ACQUISITION_PLAN.md` 的三层数据模型与红线：
  **Raw 不进 Git；D4 的 Raw 与脱敏样本均不得进入 public 仓库；`/mock_data/` 保持人工虚构**
- **Phase 2B（Integration / Orchestrator 集成骨架）暂停编码**，待**真实样本通过数据 Gate**后恢复
- 比赛 Demo 故事线**不属于当前开发主线**，推迟到后续产品展示阶段再评估
- 在真实 Curriculum / Planner / Course Data 稳定之前，不接 Agent / LLM
