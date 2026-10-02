# AUTO-MAS Skills

本目录是 AUTO-MAS 主程序仓库的附属 Agent Skills，用于沉淀本项目的 Agent
执行规则、工程约束和任务路由。主入口为仓库根目录 `AGENTS.md`，工程规则入口为
`mas-skills/SKILL.md`。

## 规则分工

- 开发文档与贡献规范：<https://doc.auto-mas.top/developer/>
- Agent Skill 与工程规则：本目录 `.agents/skills`

分支、提交信息、版本记录、Issue/PR 正文规范以文档站为准。代码风格、模块边界、
数据模型、API 契约、前端规范、专项适配等 Agent 执行规则以本目录的 `mas-*` Skill 为准。

其中 `cherry-pick` 到已发行分支只允许改动小的纯后端修复，带前端逻辑的摘取属于违规操作
（相关 PR 应 close、相关 commit 应 revert）；该规则在文档站与 `mas-skills` 中同步维护。

## 已有 Skill

- `mas-skills`：统一入口，用于按任务类型分发并组合工程规范类 Skill。
- `mas-frontend-standards`：用于约束 Vue 3、TypeScript、Vite、Electron renderer、路由、API composable、状态、样式、表单与前端验证。
- `mas-frontend-ui`：用于约束 Ant Design Vue UI、桌面端业务布局、视觉 token、表单、表格、弹窗、反馈、拖拽与深色模式。
- `mas-api-contract`：用于约束 FastAPI 接口与 WebSocket 的请求、响应和错误契约。
- `mas-data-model`：用于规范后端数据模型的结构、类型、默认值和兼容性演进。
- `mas-function-design`：用于规范后端函数的职责划分、参数设计、返回约定和副作用控制。
- `mas-module-boundary`：用于约束后端模块分层、依赖方向和代码归属边界。
- `mas-code-standards`：用于应用 AUTO-MAS 的代码规范，规范内容主要从当前 `dev` 的代表性提交和现有模块中提炼，尤其适用于 Electron 初始化与服务层代码。
- `mas-schema-naming`：用于统一后端 schema 的命名方式，减少字段语义漂移。
- `mas-script-specialized-adapter`：用于新增或维护专项脚本适配，按脚本前端架构线完成问诊、前端表面与后端任务接入。
- `mas-plan-schedule`：用于新增、重构或审查计划表类型与调度配置。
- `mas-game-sign`：用于新增、重构或审查游戏社区签到，涵盖平台注册表、凭据加密与登录路由、签到锁与触发路径、结果与通知契约。
- `grill-me`：对方案做高强度问诊的入口，仅作指针指向 `grilling`；不属于 AUTO-MAS 工程规则 hub 的默认路由。
- `grilling`：承载方案盘问逻辑，按设计树与前沿轮次推进，直到与用户达成共识；由 `grill-me` 指向，也可独立触发。
- `code-review`：从固定点（commit、分支、tag 或 merge-base）对变更做规范与规格双轴审查，两条轴线在并行子 agent 中运行；本地另把上游译词「气味基线」统一写作「可疑写法基线」，下次同步后需重新施加。
- `pr`：撰写 PR 正文时的写作辅助（摘要视图 / 证据 / 合并风险）；PR 正文规范仍以文档站为准。

## 使用方式

1. AUTO-MAS 开发任务先读 `mas-skills/SKILL.md`。
2. 按任务意图选择最小必要的子 Skill。
3. 若任务涉及贡献流程、分支、提交、PR/Issue 正文或版本记录，回到文档站确认。
4. 若任务涉及主程序代码，仍需在主程序仓库中查看相邻实现并遵守本地风格。

## 来源与许可

`grill-me`、`grilling`、`code-review`、`pr` 取自第三方简体中文汉化仓库 devcxl/mattpocock-skills-zh（原作 Matt Pocock 的技能集），按上游 MIT 许可使用（MIT License，Copyright (c) 2026 Matt Pocock）；导入时仅按本仓库文档站的贡献流程改动其中的流程引用。本目录其余内容随主程序以 AGPL-3.0 分发。按本目录约定，第三方来源只保留纯文本署名与许可声明，不留外部链接；`pr` 的摘要视图部分复制自 Humanlayer 的 show-me 技能（作者 Dex Horthy，MIT License，Copyright (c) 2026 HumanLayer，全文见 `pr/CREDITS.md`）。

## Claude Code 接入

本目录采用 `.agents/skills` 约定，Codex 一侧通过各 Skill 的 `agents/openai.yaml` 直接识别。
Claude Code 只扫描 `.claude/skills`，且 `.claude/` 已在 `.gitignore` 中忽略，因此需要在本地
建立一次目录联接，让两侧共用同一份 Skill 源：

```powershell
cmd /c "mklink /J .claude\skills .agents\skills"
```

联接是本地开发环境配置，不纳入版本库，也不会产生 `git status` 变更。未建立联接时
Claude Code 无法自动发现 `mas-*` Skill，只能按根目录 `AGENTS.md` 手动读取
`mas-skills/SKILL.md`。不要改为复制目录，避免出现第二份会漂移的 Skill 源。
