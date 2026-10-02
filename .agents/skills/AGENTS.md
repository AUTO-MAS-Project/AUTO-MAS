# AI 助手入口

本目录是 AUTO-MAS 主程序仓库的附属 Agent Skills。开发文档、分支、提交、
版本记录、Issue/PR 正文规范由文档站维护：<https://doc.auto-mas.top/developer/>。

## 工作规则

- 修改 Skill 前先读 `README.md` 和对应 `SKILL.md`。
- `SKILL.md` 保持短而可执行；长规则放入 `references/`。
- `description` 要写清触发场景，便于 Agent 自动选择。
- 不要把主程序仓库的完整实现细节复制进 Skill；稳定规则沉淀为清单、表格或反模式。
- 与贡献流程、分支、提交或 PR/Issue 正文有关的规则，优先链接文档站；PR 正文的写法见 `pr` Skill。
- 跨 Skill 引用只指向本仓库内的 Skill，或 AUTO-MAS 项目组织下的仓库与文档站（`AUTO-MAS-Project/*`、`doc.auto-mas.top`）；不要指向第三方仓库、个人主页等外部地址。引入第三方素材时用纯文本署名，并随附其版权与许可声明，不保留可抓取的来源链接。
- 本目录随主程序仓库一起维护；修改 Skill 时保持最小必要变更，并遵守根目录 `AGENTS.md` 的分支、提交和 PR 规则。
