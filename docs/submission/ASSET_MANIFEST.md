# 学航·转衔 · 素材清单（ASSET MANIFEST）

> 用途：说明 `docs/submission/` 下每份材料是干什么的、谁可以改、当前是什么状态。
> 状态取值：`READY`（可直接使用） / `LOCKED`（不得随意修改） / `WAITING`（等待定稿或素材） / `DRAFT`（可继续打磨）。
>
> **事实基线：最终产品 HEAD = 最终 RC HEAD = `695834a45905166321422eeeef0d8f46c83add0d`**（2026-10-07）。

## 主材料（11 份，商科交接包使用的就是这些）

| 文件 | 用途 | 谁修改 | 当前状态 |
|---|---|---|---|
| `HANDOFF_INDEX.md` | 商科同学的第一入口，说明先看什么、怎么改 | 商科可补充 | READY |
| `OPC_PROJECT_BRIEF.md` | 1–2 页项目简介草稿 | 商科可重写表达 | READY |
| `OPC_NARRATIVE.md` | 完整比赛叙事母本 | 商科可重写表达 | READY |
| `PITCH_DECK_OUTLINE.md` | 10 页 PPT 结构规划 | 商科可自由排版 | READY |
| `PDF_ONE_PAGER_CONTENT.md` | 项目说明 PDF / 宣传页文案 | 商科可自由排版 | READY |
| `DEMO_SCRIPT_3MIN.md` | 3 分钟演示与答辩脚本 | 商科可改语气，⛔ 禁语清单不可删 | READY |
| `MATERIAL_FACT_CHECK.md` | 全量主张事实核对（VERIFIED / CONDITIONAL / DO NOT CLAIM） | ⛔ 不允许随意修改 | LOCKED |
| `FINAL_FACT_SHEET.md` | 一页事实数字与能力边界 | ⛔ 不允许随意修改 | LOCKED |
| `SCREENSHOT_PLAN.md` | 最终截图计划与配文 | 等界面定稿后执行 | READY（已执行，保留为重拍依据） |
| `screenshots/SCREENSHOT_INDEX.md` | 最终截图目录的逐张索引与隐私核对 | 材料维护者 | READY |
| `screenshots/*.png` | 17 张最终 RC 界面真实截图（基于 `695834a` 重拍） | 界面变化时必须重拍 | READY |
| `support/*.pdf` | 面向评委的 8 份支撑材料 PDF | 事实变化时必须重新生成 | READY |
| `ASSET_MANIFEST.md` | 本文件，素材说明 | 材料维护者 | READY |
| `BUSINESS_TEAM_HANDOFF.md` | 给商科同学的完整交接说明 | 商科可补充提问 | READY |

## 已归档的旧材料（`legacy/`，不在商科交接包里）

这些是早前一轮提交材料，已移到 `docs/submission/legacy/` 作为历史记录。
它们的口径基于更早的演示快照（`51eaccb` 与更早），**与当前产品事实不一致**，
⛔ 不要直接发给商科同学，⛔ 不要用它们里面的截图或数字。

| 文件 | 说明 | 当前状态 |
|---|---|---|
| `legacy/OPC_FINAL_4MIN_DEMO.md` | 早前 4 分钟演示稿 | 已归档 |
| `legacy/OPC_FINAL_SLIDES_CONTENT.md` | 早前幻灯片内容 | 已归档 |
| `legacy/OPC_PITCH_PACK.md` | 早前路演包 | 已归档 |
| `legacy/OPC_JUDGE_QA_SHORT.md` | 早前评委问答速查 | 已归档（部分内容仍可参考，但须按新事实复核） |
| `legacy/OPC_PORTAL_INFO_TEMPLATE.md` | 门户信息模板 | 已归档 |
| `legacy/FINAL_CLAIM_MATRIX.md` | 早前跨材料一致性矩阵 | 已归档 |
| `legacy/FINAL_SUBMISSION_CHECKLIST.md` | 早前提交清单 | 已归档 |
| `legacy/DEMO_VERSION_LOCK.md` | 早前演示版本锁定 | 已归档 |
| `legacy/OFFICIAL_RULE_CHECK.md` | 赛事规则核对 | 已归档 |
| `legacy/REHEARSAL_LOG.md` | 排练记录 | 已归档 |
| `legacy/VIDEO_RECORDING_PLAN.md` | 视频录制计划 | 已归档 |
| `legacy/SCREENSHOT_INDEX.md` | 早前截图索引（对应旧界面） | 已归档 |
| `legacy/assets/*.png` | 早前界面截图（旧界面） | 已归档 |
| `legacy/学航转衔_OPC_答辩稿.pptx` | 早前答辩稿 | 已归档 |
| `tools/*.html` | 架构图与取景工具 | 可参考复用 |

> ⚠️ 当前有效的截图索引在 `screenshots/SCREENSHOT_INDEX.md`，不要与 `legacy/SCREENSHOT_INDEX.md` 混淆。

## 依赖的仓库内事实文档（只读参考，不修改）

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 项目目标与模块边界 |
| `docs/ARCHITECTURE.md` | 系统架构与 MVP 范围 |
| `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` | 当前学期 / 未来学期粒度与换班语义 |
| `docs/curriculum/PDF_TRANSCRIPT_INPUT.md` | 成绩单导入能力与隐私边界 |
| `docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md` | 演示流程与口径红线 |
| `docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` | 人工验收清单 |
| `docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` | 数据范围与课表确认机制 |
| `docs/status/curriculum.md` | 23 / 12 / 11 与选修 23 学分的出处 |
| `docs/status/integration.md` | 4069 条数据、教师字段审计、学分上限 |

## 状态说明

- **READY**：内容已完成事实核对，可以直接进入排版与润色；
- **LOCKED**：事实口径文件，任何修改都必须回到产品基线重新核对；
- **WAITING**：等界面定稿或素材就绪才能完成。

## 更新规则

1. 产品 HEAD 变化时，`MATERIAL_FACT_CHECK.md` 与 `FINAL_FACT_SHEET.md` 必须同步更新；
2. 新增对外材料时，在本清单登记一行；
3. ⛔ 不把旧版材料当成当前事实来源；
4. ⛔ 不把仓库外的私有材料（成绩单、SQLite、原始教务数据）写进任何对外文件。
