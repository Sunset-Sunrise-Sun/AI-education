# Git 工作流

## 1. 基本原则
- `main` 只保存稳定版本。
- 除仓库首次 bootstrap 外，不直接在 `main` 开发。
- 一个分支原则上只处理一类任务。
- Agent 不得未经明确授权直接 Merge 到 `main`。

## 2. 开工
```bash
git status
git branch
git log --oneline -5
git pull
git switch -c feature/<module>-<feature>
```

## 3. Commit
推荐格式：
```text
feat(module): ...
fix(module): ...
test(module): ...
docs(module): ...
refactor(module): ...
```

提交前检查：
1. `git diff`；
2. 测试结果；
3. 无敏感信息；
4. 无意外公共接口修改；
5. STATUS 已更新；
6. 必要时 WORKLOG 已更新。

## 4. Pull Request
PR 至少写明：
- 完成内容；
- 修改范围；
- 输入/输出；
- 公共接口是否变化；
- 新增依赖；
- 测试方法与结果；
- Mock/Real 数据状态；
- 已知问题；
- 对其他模块影响；
- 需要人工确认的内容。

## 5. Merge Conflict
发生冲突时不得猜测其他成员意图。先阅读相关 STATUS、最近 Commit 和必要的 WORKLOG；仍无法判断时标记 BLOCKED。
