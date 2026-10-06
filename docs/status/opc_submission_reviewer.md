# OPC submission reviewer

2026-10-06；main c75b6da。独立judge-facing审计，仅docs，无production修改/merge/学校网络。
交付：docs/reviewer/OPC_SUBMISSION_READINESS_AUDIT.md、OPC_PRESENTATION_PACK.md、OPC_JUDGE_QA.md。
SUBMISSION READY=NO。P0：官方规则与AI要求核对、owner批准能力/来源口径、根README/slides/截图、固定合成演示彩排与视频/备份、团队/portal材料与隐私检查。
重要边界：无运行LLM/RAG/GraphRAG证据；Planner非OR-Tools/全局优化；XLSX generic未进入UI/fixed runtime；Synthetic E2E含合成Curriculum，不能只披露教学班合成。
本轮main preflight=partial_ready/LEVEL1/eligibilityfalse；synthetic suite20pass。近期同内容HEAD回归2979+2skip/frontend134记录可复用但非真实效果数据。已有Case A统计注明文档记录/未独立读取私有材料。
本轮草稿不是已提交比赛文件。建议10/08前完成，不推定官方截止日期。

## PR51/PR52 truth consistency update

2026-10-06；已核GitHub base main与PR51 28d2c1f/PR52原始90abb5c HEAD。
权威矩阵 docs/reviewer/OPC_CROSS_PR_TRUTH_TABLE.md 覆盖14组件、两轴real logic vs realdata、AI/Planner/模式/披露/canonical/最小修正/更新库存。
DEMO READY truthNO/SUBMISSIONNO/PR51wordingmergeBLOCK：场景6把Mock偏好调班说成本次Planner执行；STARTUP已批准Curriculum⇒LEVEL2错误；partial补变量启动/模式披露及AI当前未来边界需统一。
README/脚本/图/启动/恢复PR51已具备不再缺失。截图/slides/video/正式规则核对/团队表/portal/彩排仍待。
仅少量actual TestClient/CLI验证：Mock200 factory0精确JSON回放；synthetic plan200 factory3；ready可仍eligibilityfalse。无fullreg重复、生产修改/merge/学校访问。
