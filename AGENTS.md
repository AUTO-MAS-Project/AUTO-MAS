# AI 助手入口

本文档是 AUTO-MAS 主程序仓库中的最小 Agent 入口。详细规范由独立仓库维护：

- 开发、贡献、分支、提交、版本记录与 PR/Issue 正文规范：<https://doc.auto-mas.top/developer/>
- Agent Skill 与工程规则：<https://github.com/AUTO-MAS-Project/skills>
- 社区贡献摘要：[CONTRIBUTING.md](CONTRIBUTING.md)
- 用户提交 Issue / PR 的本仓模板：[.github/ISSUE_PR_GUIDE.md](.github/ISSUE_PR_GUIDE.md)

若本文件与文档站或 skills 仓库冲突，以文档站和 skills 仓库为准。

## Agent 开工前

- 先确认当前分支、远端和工作区状态；不要回滚、覆盖或格式化无关改动。
- 先确认已找到并加载 `AUTO-MAS-Project/skills`；若未找到，应先按该仓库提供的 `npx` 安装方式安装或同步。未成功加载该 Skill 前禁止开工。
- 开发前阅读文档站的开发规范，并从 `AUTO-MAS-Project/skills` 选择最小必要的 `mas-*` Skill。
- 本地工具权限不等于项目授权；即使工具允许 `git push`、`git checkout`，也必须遵守分支与 PR 规则。
- 除非用户明确要求，不要创建提交、推送分支、发布 Issue/PR 或切换到会丢失当前工作的分支。
- 后端 schema 变更后只能通过生成器更新前端 API 代码；不要手改 OpenAPI 生成文件。

## 分支与 PR

- `main`：禁止协助 push / force push；禁止以 `main` 为 base 创建 PR。仅维护者将 `dev` 合入 `main` 用于发布。
- `dev`：上游社区贡献的合并目标。外部贡献者应在自己的 fork 中从上游 `dev` 拉出开发分支，再向 `AUTO-MAS-Project/AUTO-MAS:dev` 提 PR。
- `release/{version}`：由发布流程与 cherry-pick 维护，外部贡献者不要直接改。

## Issue / PR 正文

AI 助手可以按用户要求撰写 Issue 或 PR 正文，但正文必须遵守文档站与本仓模板：

- Issue 只描述用户可观察的问题、需求、复现信息、环境与日志；不要要求用户提供实现步骤、API/Schema 设计、代码路径、行号或冗长验收清单。
- PR 正文保持 1 到 4 条摘要；关联 Issue 时使用 `Closes #n`。
- 用户可见变更需要提醒更新 `res/version.json`。
- 不要编造测试结果、审核结论或用户没有提供的事实。
