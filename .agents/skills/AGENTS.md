# AI 助手入口

本仓库是 AUTO-MAS Agent Skill 的权威来源。开发文档、分支、提交、版本记录、
Issue/PR 正文规范由文档站维护：<https://doc.auto-mas.top/developer/>。

## 工作规则

- 修改 Skill 前先读 `README.md` 和对应 `SKILL.md`。
- `SKILL.md` 保持短而可执行；长规则放入 `references/`。
- `description` 要写清触发场景，便于 Agent 自动选择。
- 不要把主程序仓库的完整实现细节复制进 Skill；稳定规则沉淀为清单、表格或反模式。
- 与贡献流程、分支、提交或 PR/Issue 正文有关的规则，优先链接文档站。
- 不要替主程序仓库维护完整 Skill 副本；主程序仓库只保留最小入口并指向本仓库。

## PR 方向

外部贡献者在 fork 中从本仓 `main` 拉出分支，向 `AUTO-MAS-Project/skills:main`
发起 PR。不要把针对主程序仓库的 PR 发到本仓。
