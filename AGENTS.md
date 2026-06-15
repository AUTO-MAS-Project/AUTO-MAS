# AI 助手入口

本文档是 AUTO-MAS 主程序仓库的最小 Agent 入口。详细规范见：

- 开发、贡献、分支、提交、版本记录、Issue/PR 正文：<https://doc.auto-mas.top/developer/>
- 项目附属 Agent Skills：[.agents/skills](.agents/skills)

若本文件与文档站或 [.agents/skills](.agents/skills) 冲突，以文档站和 [.agents/skills](.agents/skills) 为准。

## 开工前

- 先确认当前分支、远端和工作区状态；不要回滚、覆盖或格式化无关改动。
- 必须确认存在并加载 `.agents/skills/mas-skills/SKILL.md`；若不存在，明确提示用户缺少项目附属 Skills，并拒绝开工。
- 加载 `mas-skills` 后，再按任务选择最小必要的 `mas-*` Skill。
- `frontend` 指本仓库前端目录和前端任务；涉及 `frontend`、Vue、UI、组件、路由或前端 API 时，按 `.agents/skills` 中的前端 Skill 执行。
- 除非用户明确要求，不要创建提交、推送分支、发布 Issue/PR，或切换到会丢失当前工作的分支。
- 后端 schema 变更后只能通过生成器更新前端 API 代码；不要手改 OpenAPI 生成文件。

## 写作约束

- Issue 只描述用户可观察的问题、需求、复现信息、环境与日志。
- PR 正文保持 1 到 4 条摘要；关联 Issue 时使用 `Closes #n`。
- 用户可见变更需要提醒更新 `res/version.json`。
- 不要编造测试结果、审核结论或用户没有提供的事实。
