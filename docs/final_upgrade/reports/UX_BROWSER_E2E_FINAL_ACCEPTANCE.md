# 最终验收报告：PR #70（`01fc7b5`）—— CSS 修复后的复跑

- **验收对象**：PR #70 `qa/final-upgrade-ux-browser-e2e`，HEAD **`01fc7b5`**
  （`fix(ux): prevent AI drawer close button from wrapping on mobile`，仅 `frontend/src/styles/base.css` +5 行）
- **PR base**：`feature/final-upgrade`
- **执行环境**：Windows；Python 3.14.7（`PYTHONUTF8=1`）；Node v24.19.0；
  **系统 Microsoft Edge**（`playwright-core` `channel=msedge`，⛔ 未下载浏览器二进制）；
  真实 FastAPI（uvicorn 随机端口）+ 真实 Vite dev server
- **使用数据**：**Mock**（人工构造演示数据）+ **注入式测试模型**（`test_double`）
- **真实 DeepSeek / 真实教务数据**：**NOT VERIFIED**（不在本次范围，且 PR 已如实标注）
- **结论**：**达到合并条件**（本报告 §6 给出逐条门槛核验；仍有 2 项非阻塞备注）

---

## 1. 本次要求的 5 项，逐条结果

| # | 要求 | 结果 |
| --- | --- | --- |
| 1 | `QA_STRICT_HEADER_BUTTON=1` 跑 `--filter=R-375`，确认手机端关闭按钮不再竖向换行 | ✅ **通过**：关闭按钮 **85×39px、标签 1 行**（修复前 61×77px、标签被折行） |
| 2 | 重跑全部 23 项真实 Edge 浏览器 E2E | ✅ **23 passed / 0 failed / 0 skipped**（3 分 26 秒） |
| 3 | 前端 Vitest、`vue-tsc`、Build | ✅ **303 passed**、`vue-tsc` **exit 0**、`build` **exit 0** |
| 4 | 检查 375/768/1440 关键截图（横向溢出、按钮遮挡） | ✅ 6 张关键截图逐一目视核对，**无横向溢出、无遮挡**（§4） |
| 5 | 提交结果、说明是否达到合并条件 | ✅ 本报告 + STATUS/WORKLOG 已更新（§6 结论：**达到**） |

---

## 2. 第 1 项：严格开关下的 R-375（缺陷 K-1 的收口验证）

命令（与 PR #70 正文里要求的一致）：

```powershell
$env:QA_STRICT_HEADER_BUTTON=1
node tools/browser-e2e/run_browser_e2e.mjs --filter=R-375
```

实测输出：

```text
✅ R-375-layout — 375px 视口：三入口、抽屉、按钮与长文本可用且无横向溢出
=== 结果：1 passed / 0 failed / 0 skipped / 共 1 ===
```

量测对比：

| 指标 | 修复前（`a38c9cd`） | 修复后（`01fc7b5`） | 判定 |
| --- | --- | --- | --- |
| 关闭按钮外框 | 61 × 77 px | **85 × 39 px** | ✅ 不再是竖长条 |
| 按钮内文本盒 | 14 × 54 px（被折行） | **43 × 16 px（1 行）** | ✅ 不再换行 |
| 标签行数 | 多行 | **1 行** | ✅ |
| `white-space` | `normal` | `nowrap`（由新规则提供） | ✅ |

> 同一断言在 768px 与 1440px 也一并核验为 **85×39px、1 行**。
> 严格开关（`QA_STRICT_HEADER_BUTTON=1`）现在**全绿**，说明修复真实生效。

---

## 3. 第 2 项：全部 23 项真实浏览器 E2E

| 组 | 用例数 | 结果 |
| --- | --- | --- |
| P0 主流程（L01–L10） | 10 | ✅ 全通过 |
| 联合验收：规则解释（X01–X02） | 2 | ✅ 全通过 |
| 联合验收：UX 结构（U01–U03） | 3 | ✅ 全通过 |
| P1 响应式布局（R-375/768/1440） | 3 | ✅ 全通过 |
| P1 异常与并发（E01–E03） | 3 | ✅ 全通过 |
| 未启用档（D01） | 1 | ✅ 通过 |
| 预览档（P01） | 1 | ✅ 通过 |
| **合计** | **23** | **23 passed / 0 failed / 0 skipped** |

关键行为断言（均基于**浏览器实际发出的 HTTP 请求**，非模拟）：

- `L04`：`GET /status` → `POST /interpret` → `POST /solve` → `POST /adopt` 四接口齐全；
  第一次确认前 `/solve` 调用数为 **0**；
- `L08`：存在歧义时**不调用** `/solve`；`D01`：AI 请求 **0** 次；`P01`：`/ai-planning/*` **0** 次；
- `X01`：点击解释入口**真实调用** `POST /api/v1/explanation/plan`，面板标注"规则模板（非 AI）"、"解释对象：Mock"、11 条条目；
- `X02`：解释只读 —— 解释前后方案来源一致，且 `/solve` **0** 次；
- `R-*`：三档横向溢出 **0px**；关闭按钮、采用按钮、解释入口均落在视口内且可点。

---

## 4. 第 4 项：关键截图目视核对（375 / 768 / 1440）

| 截图 | 核对结论 |
| --- | --- |
| `responsive/R-375-drawer.png` | 抽屉近似全屏；标题两行；**关闭按钮单行**"✕ 关闭"位于右上，未与标题重叠；无横向溢出 |
| `responsive/R-768-drawer.png` | 右侧 520px 面板；关闭按钮单行落在面板内；左侧页面内容未被遮挡（仅面板本身覆盖，属设计） |
| `responsive/R-1440-drawer.png` | 同上；面板与页面内容边界清晰，无重叠 |
| `responsive/R-375-candidate.png` | 候选按钮**纵向堆叠**：采用 / 保留原方案 / 重新求解 / 回到意图草稿，全部完整可见、未被裁切 |
| `responsive/R-768-candidate.png` | 同 375px 的纵向堆叠；"学分变化 原方案 12 · 候选 15 · 总学分 +3" 完整 |
| `responsive/R-1440-candidate.png` | 采用 / 保留原方案**并排**，其余按钮另起一行；无重叠、无遮挡、无横向滚动 |

截图目录：`tools/browser-e2e/artifacts/responsive/`（本次运行重新生成，共 26 张，其中 responsive 6 张）。

**关于头部高度的变化（如实说明，不是回归）**：
修复后 375px 抽屉头部由 117px 变为 **137px**（占视口由 14% 变 17%）。
原因是修复**让标题与状态行拿回了完整宽度**，状态行因此多占一行（2.8 → 3 行附近）；
原先的 117px 是被关闭按钮"撑高"造成的错觉。137px 仍远低于 50% 视口阈值（断言上限），
且不影响任何操作；若后续要进一步压缩，办法是收窄状态行文案（见 §6 备注 B）。

---

## 5. 第 3 项与回归：全量测试结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 浏览器 E2E（23 项） | `node tools/browser-e2e/run_browser_e2e.mjs` | **23 passed / 0 failed / 0 skipped**（205.9s） |
| 严格开关 R-375 | `QA_STRICT_HEADER_BUTTON=1 … --filter=R-375` | **1 passed / 0 failed** |
| 前端 Vitest | `npx vitest run` | **303 passed / 0 failed**（19 文件） |
| 前端类型检查 | `npx vue-tsc --noEmit` | **exit 0** |
| 前端构建 | `npm run build` | **exit 0**（JS 247.21 kB / gzip 79.82 kB；CSS 41.25 kB / gzip 7.48 kB） |
| 后端 pytest | `python -m pytest -q`（`PYTHONUTF8=1`） | **3188 passed / 2 failed / 2 skipped** |

**2 项后端失败**为既有平台差异，与本次改动无关，⛔ 未修改其实现或测试：

```text
tests/test_curriculum_docx_reader.py::test_duplicate_or_unsafe_archive_members_are_rejected[word\\DEMO-PRIVATE-PART]
tests/test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]
```

（Python 3.14 下 `Path("bad\x00path")` 不再抛错；Windows ZIP 成员名反斜杠语义差异。）

**无新回归。**

---

## 6. 是否达到合并条件 — 逐条核验

PR #70 正文列出的合并前门槛，逐条对照：

| 门槛 | 要求 | 状态 | 证据 |
| --- | --- | --- | --- |
| a | `QA_STRICT_HEADER_BUTTON=1 … --filter=R-375` 或等效验证 | ✅ **满足** | §2：1 passed；关闭按钮 85×39px、1 行 |
| b | 全量 23 项 E2E | ✅ **满足** | §3：23/23 |
| c | Vitest / typecheck / build | ✅ **满足** | §5：303 passed、exit 0、exit 0 |
| d | 检查截图 | ✅ **满足** | §4：6 张关键截图逐一核对，无溢出、无遮挡 |

**结论：达到合并条件（merge-ready）。**

### 6.1 非阻塞备注（不需要再改代码即可合并）

**备注 A — 后端 2 项既有平台差异失败**
与本 PR 无关，历史各分支同样失败。建议单独开 issue 跟踪，不阻塞合并。

**备注 B — 375px 抽屉头部状态行仍偏密（观察 O-1，未修）**

```text
375px：状态行 2.8 行 / 高 54px；头部 137px（占视口 17%）
状态行文本：enabled=true · api_key_configured=false · live_model_available=false · model=qa-test-double
```

该文案**被前端自身的测试锁定**（`frontend/tests/ai-planning-drawer.spec.ts` 断言必须包含
`enabled=true` 与 `live_model_available=false`），属于"面向开发者的能力事实披露"的有意设计，
因此本轮**未改**。若产品希望手机上更简洁，建议：把 4 个字段折叠为一行摘要 + 可展开"技术细节"，
并同步修改该 Vitest 断言 —— 属独立的小改动，不阻塞本 PR。

### 6.2 仍属"单独验收"的范围（不构成本 PR 的合并门槛）

- **真实 DeepSeek 在线调用：NOT VERIFIED**（无密钥，`live_model_available=false`）；
  全部 AI 结果来自注入式测试模型（`generator_kind=test_double`），⛔ 未冒充在线模型。
- **真实已核验培养方案目录 / 真实教学班 / 真实成绩数据：BLOCKED**；页面如实显示"没有已核验版本目录"。
- 真机浏览器与触屏手势、无障碍专项（屏幕阅读器 / 键盘 Tab 序）：**未执行**（本轮为视口尺寸模拟）。
- 持久化方案版本：**不存在**（`adopted_version_scope=process_local_session`）。

---

## 7. 本轮为让验收可复现而修的基础设施问题（重要）

复跑过程中发现了**测试基础设施自身的缺陷**，已修复；⛔ 未触碰任何业务逻辑：

### 7.1 服务进程泄漏（导致复跑卡死的根因）

**现象**：复跑时 runner 长时间不结束（>18 分钟），后续运行越来越慢直至超时。

**根因**：Windows 下包装器用 `shell: true` 启动服务，实际进程链是
`node(wrapper) → cmd.exe → node(vite) / python(uvicorn)`。
`child.kill()` 只杀掉包装器，**Vite 与 uvicorn 变成孤儿常驻**。
实测累积到 **317 个 node / 97 个 python / 23 个 msedge** 进程；它们继续占用端口，
使新一轮运行既慢又可能失败。

**修复**（`tools/browser-e2e/`，仅测试基础设施）：

1. `dispatchers/stdio_inherit.mjs`：子进程起来后把真实 PID 以 `__E2E_CHILD_PID__ <pid>`
   写入 stderr（= 日志文件），并在收到 `SIGTERM`/父进程断开时用
   `taskkill /PID <pid> /T /F` **整棵树**清理；
2. `lib/servers.mjs`：`stop()` 解析日志中的 PID，对**包装器与真实子进程**都做树级清理；
3. `run_browser_e2e.mjs`：跑完显式 `process.exit(code)`，避免句柄未关导致挂住。

**验证**：单例运行 **19.6s**、全量 **205.9s**，运行后残留服务进程 **0 个**；
清理用的是按路径精确匹配（`ux-e2e-qa` / `qa_browser_e2e`），
你自己的非 headless Edge（DSH Web GUI）**未被触碰**。

### 7.2 K-1 的观测项改为"自动判定"

`cases.mjs` 里原来无论修没修都会打印"⚠️ 已知缺陷 K-1"。
现改为：高度 > 56px 才提示缺陷；否则打印 `✅ 缺陷 K-1 已修复`。
这样报告不会在修复后继续留下误导性文字。

---

## 8. 截图与结果文件位置

| 产物 | 位置 |
| --- | --- |
| 截图（26 张） | `tools/browser-e2e/artifacts/{live,explanation,ux,responsive,resilience,disabled,preview}/` |
| 全量结果 JSON | `tools/browser-e2e/artifacts/browser-e2e-results.json` |
| 对照 18 项结果 JSON | `tools/browser-e2e/artifacts/browser-e2e-results-_cases_baseline18.json` |
| 服务启动日志 | `tools/browser-e2e/artifacts/logs/*.log` |

---

## 9. 合并建议

1. **PR #70 可以合并**（Draft → Ready 由负责人决定；⛔ 不自动合并）；
2. 合并后建议在 `feature/final-upgrade` 上再跑一次本套件（23 项）作为合并后冒烟；
3. PR #68 / PR #69 的源分支保持不动；合并顺序仍建议 #69 → #68，或直接以本 QA 分支为合并载体；
4. 备注 A（后端 2 项既有失败）与备注 B（头部文案密度）各开一个独立小任务，不阻塞本 PR。
