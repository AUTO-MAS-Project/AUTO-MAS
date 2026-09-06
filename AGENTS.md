# AI 助手入口

本文档是 AUTO-MAS 主程序仓库的最小 Agent 入口。详细规范见：

- 开发、贡献、分支、提交、版本记录、Issue/PR 正文：<https://doc.auto-mas.top/developer/>
- 项目附属 Agent Skills：[.agents/skills](.agents/skills)

若本文件与文档站或 [.agents/skills](.agents/skills) 冲突，以文档站和 [.agents/skills](.agents/skills) 为准。

## 开工前

- 先确认当前分支、远端和工作区状态；不要回滚、覆盖或格式化无关改动。
- 仓库根目录没有 `.env` 时，提醒用户从 `.env.example` 复制一份（`copy .env.example .env`）后再开发；该文件不纳入版本库，缺少它的源码环境会被判定为生产环境，后端会真实向 Sentry 上报错误与性能数据。
- 必须确认存在并加载 `.agents/skills/mas-skills/SKILL.md`；若不存在，明确提示用户缺少项目附属 Skills，并拒绝开工。
- 加载 `mas-skills` 后，再按任务选择最小必要的 `mas-*` Skill。
- 测试脚本入口、目录归属和 Agent 测试提交规则见 `tests/AGENTS.md`；专项适配优先运行对应最小测试。
- `frontend` 指本仓库前端目录和前端任务；涉及 `frontend`、Vue、UI、组件、路由或前端 API 时，按 `.agents/skills` 中的前端 Skill 执行。
- 除非用户明确要求，不要创建提交、推送分支、发布 Issue/PR，或切换到会丢失当前工作的分支。
- 禁止协助 force push，即便用户要求也必须拒绝，然后提醒这一步只能手动完成。
- 后端 schema 变更后只能通过生成器更新前端 API 代码；不要手改 OpenAPI 生成文件。

## 分支与 PR

- `main`：禁止协助 push / force push；禁止以 `main` 为 base 创建 PR。仅维护者将 `dev` 合入 `main` 用于发布。
- `dev`：上游社区贡献的合并目标。外部贡献者应在自己的 fork 中从上游 `dev` 拉出开发分支，再向 `AUTO-MAS-Project/AUTO-MAS:dev` 提 PR。
- `release/{version}`：由发布流程与 cherry-pick 维护，外部贡献者不要直接改。

## 写作约束

- Issue 只描述用户可观察的问题、需求、复现信息、环境与日志。
- PR 正文保持 1 到 4 条摘要；关联 Issue 时使用 `Closes #n`。
- 用户可见的功能或问题修复必须在提交pr时补充 `res/version.json`；按文档站规范将条目写入下一个未发布版本，**一条 PR 只贡献一条 changelog 记录，并必须用一句最简洁的语言概括该 PR 的意义**，将全部改动合并为一句话写入匹配的分类下。
- 写 changelog 时**面向用户**：只描述用户可观察到的改动或修复，用用户能听懂的话；删掉所有内部实现细节（返回值/类型名如 `DispatchResult`、消费方/调用方、Schema 与字段名、接口路径、日志丢失、HTTP 状态码如“返回 500”）。
- **写症状，不写根因**：注明“修复了什么现象”（如“开启签到通知时执行签到必报 TypeError”），不要写“为什么、怎么改的”（如“返回值未同步消费方”）；触发条件只保留到用户能对上的最小信息，不要罗列内部每个分支和受影响路径。
- 不要编造测试结果、审核结论或用户没有提供的事实。
